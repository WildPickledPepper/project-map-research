from pathlib import Path
import tempfile
import unittest

from adapters.python_boundaries import augment
from adapters.python_facts import analyze


class PythonBoundaryTests(unittest.TestCase):
    def graph(self,files):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,body in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
            return augment(analyze(root,list(files)))

    def test_aiohttp_application_runner_listener_route_and_partial_handler(self):
        g=self.graph({'handlers.py':'async def handle(request): return request\n',
            'start.py':'''from aiohttp import web as network
from functools import partial
from handlers import handle
def start(host,port):
 app=network.Application()
 app.router.add_route('*','/{rest:.*}',partial(handle))
 runner=network.AppRunner(app)
 listener=network.TCPSite(runner,host,port)
'''})
        nodes={n['id']:n for n in g['nodes']};boundaries=[n for n in g['nodes'] if n['kind']=='python_boundary']
        self.assertEqual({n['family'] for n in boundaries},{'network_listener','route_registration'})
        self.assertEqual(len([e for e in g['edges'] if e['kind']=='EXPOSES_ROUTE']),1)
        dispatch=[e for e in g['edges'] if e['kind']=='CAN_DISPATCH_TO']
        self.assertEqual([nodes[e['target']]['name'] for e in dispatch],['handle'])
        listener=next(n for n in boundaries if n['family']=='network_listener')
        self.assertTrue(listener['host_values'] and listener['port_values'])

    def test_identical_routes_in_different_apps_remain_separate(self):
        g=self.graph({'start.py':'''from aiohttp import web
async def first(request): pass
async def second(request): pass
one=web.Application()
two=web.Application()
one.router.add_get('/same',first)
two.router.add_get('/same',second)
runner=web.AppRunner(one)
site=web.TCPSite(runner,'127.0.0.1',8000)
'''})
        nodes={n['id']:n for n in g['nodes']}
        exposed=[e for e in g['edges'] if e['kind']=='EXPOSES_ROUTE']
        self.assertEqual(len(exposed),1)
        handlers=[nodes[e['target']]['name'] for e in g['edges'] if e['kind']=='CAN_DISPATCH_TO' and e['source']==exposed[0]['target']]
        self.assertEqual(handlers,['first'])

    def test_session_context_preserves_client_address_value(self):
        g=self.graph({'client.py':'''from aiohttp import ClientSession as Session
async def connect(address):
 async with Session() as session:
  async with session.ws_connect(address) as peer:
   pass
'''})
        clients=[n for n in g['nodes'] if n.get('family')=='network_client']
        self.assertEqual(len(clients),1);self.assertTrue(clients[0]['address_values'])
        self.assertEqual(clients[0]['api_candidates'],['aiohttp.ClientSession.ws_connect'])
        self.assertEqual(clients[0]['counterpart_status'],'pending_identity_and_context')

    def test_imported_library_name_shadowed_by_local_module_is_not_external_api(self):
        g=self.graph({'aiohttp.py':'class Web:\n def Application(self): return None\nweb=Web()\n',
            'start.py':'from aiohttp import web\napp=web.Application()\napp.router.add_get("/same",None)\n'})
        self.assertFalse([n for n in g['nodes'] if n['kind']=='python_boundary'])

    def test_parameter_named_library_does_not_create_boundary(self):
        g=self.graph({'start.py':'def start(subprocess): return subprocess.Popen(["not-proven"])\n'})
        self.assertFalse([n for n in g['nodes'] if n['kind']=='python_boundary'])

    def test_process_handle_teardown_keeps_two_launches_separate(self):
        g=self.graph({'start.py':'''import subprocess as process
def launch(left,right):
 first=process.Popen(left)
 second=process.Popen(right)
 first.terminate()
 second.wait()
'''})
        nodes={n['id']:n for n in g['nodes']}
        starts=[n for n in g['nodes'] if n.get('family')=='process_start']
        links=[e for e in g['edges'] if e['kind']=='USES_PROCESS_HANDLE']
        self.assertEqual(len(starts),2);self.assertEqual(len(links),2)
        self.assertEqual({(nodes[e['source']]['name'],nodes[e['target']]['line']) for e in links},{('first.terminate',3),('second.wait',4)})
        self.assertTrue(all(e['status']=='candidate' and e['runtime_execution']=='not_observed' for e in links))

    def test_async_listener_callback_is_a_source_relation(self):
        g=self.graph({'start.py':'import asyncio\nasync def serve(reader,writer): pass\nasync def start():\n return await asyncio.start_server(serve,"localhost",8800)\n'})
        nodes={n['id']:n for n in g['nodes']}
        dispatch=[e for e in g['edges'] if e['kind']=='CAN_DISPATCH_TO']
        self.assertEqual([nodes[e['target']]['name'] for e in dispatch],['serve'])


if __name__=='__main__':unittest.main()
