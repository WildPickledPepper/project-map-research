"""Versioned inputs for native build systems; paths name immutable captures."""
import json
from pathlib import Path
from adapters.cmake_project import configuration as cmake_configuration


def configuration(value=None):
    data=json.loads(json.dumps(value if value is not None else {'version':1,'cmake':{}}))
    if not isinstance(data,dict) or data.get('version')!=1 or set(data)-{'version','cmake','cargo','providers'}:
        raise ValueError('Expected build configuration version 1')
    providers=data.pop('providers',None)
    cargo=data.pop('cargo',None);result=cmake_configuration(data)
    if providers is not None:
        from adapters.native_provider_graph import configuration as provider_configuration
        result['providers']=provider_configuration(providers)
    if cargo is None:return result
    if not isinstance(cargo,dict) or set(cargo)!={'captures'} or not isinstance(cargo['captures'],list):
        raise ValueError('Expected cargo.captures list')
    seen=set()
    for capture in cargo['captures']:
        if not isinstance(capture,dict) or set(capture)!={'directory','source_commit','context_key'}:
            raise ValueError('Cargo captures require directory, source_commit and context_key')
        if not all(isinstance(v,str) and v for v in capture.values()) or not Path(capture['directory']).is_absolute():
            raise ValueError('Cargo capture directory must be absolute and identifiers nonempty')
        revision=capture['source_commit']
        if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise ValueError('Cargo source revision must be fixed')
        if capture['context_key'] in seen:raise ValueError('Duplicate Cargo context key')
        seen.add(capture['context_key'])
    result['cargo']={'captures':sorted(cargo['captures'],key=lambda c:c['context_key'])};return result
