"""Small source-only rust-analyzer LSP client for isolated component experiments."""
from pathlib import Path
import json
import queue
import subprocess
import threading
import time


class Client:
    def __init__(self, executable, root, project, log, timeout=40):
        self.timeout=timeout;self.sequence=0;self.events=[];self.responses={};self.incoming=queue.Queue()
        self.root=Path(root).resolve();self.stderr=Path(log).open('wb')
        self.process=subprocess.Popen([str(executable)],cwd=self.root,stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=self.stderr)
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
        try:
            self.initialize=self.request('initialize',{'processId':None,'rootUri':self.root.as_uri(),
                'capabilities':{'experimental':{'serverStatusNotification':True},
                    'general':{'positionEncodings':['utf-16']},'textDocument':{'definition':{'linkSupport':True}}},
                'initializationOptions':{'linkedProjects':[project],'checkOnSave':False,
                    'cargo':{'buildScripts':{'enable':False}},'procMacro':{'enable':False},
                    'diagnostics':{'enable':False},'cachePriming':{'enable':False},'numThreads':2}})
            self.send({'method':'initialized','params':{}})
            deadline=time.monotonic()+timeout
            while not any(e.get('method')=='experimental/serverStatus' and e['params'].get('quiescent') for e in self.events):
                self._receive(deadline)
        except BaseException:
            self.close();raise

    def _read(self):
        try:
            while True:
                headers={}
                while True:
                    line=self.process.stdout.readline()
                    if not line:raise EOFError('rust-analyzer closed stdout')
                    if line==b'\r\n':break
                    key,value=line.decode('ascii').split(':',1);headers[key.lower()]=value.strip()
                size=int(headers['content-length'])
                if not 0<size<=16*1024*1024:raise ValueError('Unexpected LSP frame size')
                data=b''
                while len(data)<size:
                    chunk=self.process.stdout.read(size-len(data))
                    if not chunk:raise EOFError('Incomplete LSP frame')
                    data+=chunk
                self.incoming.put(json.loads(data))
        except BaseException as error:self.incoming.put(error)

    def send(self, message):
        body=json.dumps({'jsonrpc':'2.0',**message},ensure_ascii=False).encode('utf-8')
        self.process.stdin.write(f'Content-Length: {len(body)}\r\n\r\n'.encode('ascii')+body)
        self.process.stdin.flush()

    def _receive(self, deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('rust-analyzer request deadline reached')
        try:message=self.incoming.get(timeout=remaining)
        except queue.Empty as error:raise TimeoutError('rust-analyzer request deadline reached') from error
        if isinstance(message,BaseException):raise message
        if 'method' in message:
            self.events.append(message)
            if 'id' in message:
                # No edits, execution or configuration callbacks are advertised.
                self.send({'id':message['id'],'error':{'code':-32601,'message':'Client capability not advertised'}})
        elif 'id' in message:self.responses[message['id']]=message

    def request(self, method, params):
        self.sequence+=1;key=self.sequence
        self.send({'id':key,'method':method,'params':params})
        deadline=time.monotonic()+self.timeout
        while key not in self.responses:self._receive(deadline)
        result=self.responses.pop(key)
        if 'error' in result:raise RuntimeError(json.dumps(result['error']))
        return result.get('result')

    def at(self, method, path, position):
        return self.request(method,{'textDocument':{'uri':(self.root/path).as_uri()},'position':position})

    def close(self):
        try:
            if self.process.poll() is None:
                self.request('shutdown',None);self.send({'method':'exit'})
                self.process.wait(timeout=5)
        except (OSError,RuntimeError,EOFError,TimeoutError,subprocess.TimeoutExpired):
            if self.process.poll() is None:self.process.kill()
            self.process.wait()
        finally:
            for pipe in (self.process.stdin,self.process.stdout):
                if pipe:pipe.close()
            self.stderr.close()
            self.reader.join(timeout=1)

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
