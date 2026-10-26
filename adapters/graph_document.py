"""Read large graph documents with ijson while retaining the existing list API."""
from decimal import Decimal
import json
from pathlib import Path


def numbers(value):
    """Use JSON's ordinary Python floats and arbitrary-precision integers."""
    if isinstance(value,Decimal):return float(value)
    pending=[value]
    while pending:
        current=pending.pop()
        if isinstance(current,dict):
            for key,item in current.items():
                if isinstance(item,Decimal):current[key]=float(item)
                elif isinstance(item,(dict,list)):pending.append(item)
        elif isinstance(current,list):
            for key,item in enumerate(current):
                if isinstance(item,Decimal):current[key]=float(item)
                elif isinstance(item,(dict,list)):pending.append(item)
    return value


class StreamArray(list):
    def __init__(self,document,key,count):
        self.document,self.key,self.count=document,key,count

    def __len__(self):return self.count

    def __iter__(self):
        import ijson
        self.document.check()
        with self.document.path.open('rb') as stream:
            for value in ijson.items(stream,self.key+'.item'):yield numbers(value)
        self.document.check()


class GraphDocument(dict):
    streaming_arrays=True

    def __init__(self,path):
        import ijson
        from ijson.common import ObjectBuilder
        self.path=Path(path);self.signature=self.stat();counts={'nodes':0,'edges':0}
        metadata={};key=None;builder=None;seen=set();arrays=set()
        with self.path.open('rb') as stream:
            for prefix,event,value in ijson.parse(stream):
                if prefix=='' and event=='map_key':
                    if builder is not None:metadata[key]=numbers(builder.value)
                    if value in seen:raise ValueError('Duplicate graph document key: '+value)
                    seen.add(value);key=value;builder=None if key in counts else ObjectBuilder()
                    continue
                if key in counts:
                    if prefix==key and event=='start_array':arrays.add(key)
                    if prefix==key+'.item' and event in {'start_map','start_array','string','number','boolean','null'}:
                        counts[key]+=1
                elif builder is not None and prefix:
                    builder.event(event,value)
        if builder is not None:metadata[key]=numbers(builder.value)
        if arrays!={'nodes','edges'}:raise ValueError('Graph nodes and edges must be arrays')
        super().__init__(metadata)
        for key,count in counts.items():self[key]=StreamArray(self,key,count)
        self.check()

    def stat(self):
        value=self.path.stat();return value.st_size,value.st_mtime_ns

    def check(self):
        if self.stat()!=self.signature:raise ValueError('Graph document changed during streaming read')


def read_graph(path):
    path=Path(path)
    if path.stat().st_size>128*1024*1024:return GraphDocument(path)
    return json.loads(path.read_text(encoding='utf-8'))
