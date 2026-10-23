"""Import syntax facts into a new copy of a completed native CGC trial database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.kuzu_fact_store import replace_snapshot,rows,delete_snapshot


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--native-run',type=Path,required=True)
    ap.add_argument('--facts',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--dll-dir',type=Path)
    args=ap.parse_args()
    native=args.native_run.resolve()
    output=args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(native):
        raise ValueError('Use a new external output directory')
    env=json.loads((native/'environment.json').read_text(encoding='utf-8'))
    manifest=json.loads((native/'input-manifest.json').read_text(encoding='utf-8'))
    facts=json.loads(args.facts.read_text(encoding='utf-8'))
    if env['source_commit']!=facts['source_commit'] or facts['manifest_sha256']!=hashlib.sha256((native/'input-manifest.json').read_bytes()).hexdigest():
        raise ValueError('Facts and native trial must describe the same verified input')
    expected={f['path']:f['sha256_lf_utf8'] for f in manifest['files']}
    for record in facts['records']:
        if record['sha256_lf_utf8']!=expected.get(record['path']):
            raise ValueError('Fact source hashes differ from native input manifest')
    # A closed native trial has already checkpointed its single-file database.
    if (native/'cgc.kuzu.wal').exists() and (native/'cgc.kuzu.wal').stat().st_size:
        raise ValueError('Close/checkpoint native database before copying it')
    output.mkdir(parents=True)
    shutil.copy2(native/'cgc.kuzu',output/'graph.kuzu')
    handle=os.add_dll_directory(str(args.dll_dir.resolve())) if os.name=='nt' and args.dll_dir else None
    import kuzu
    db=kuzu.Database(str(output/'graph.kuzu'),buffer_pool_size=256*1024*1024)
    connection=kuzu.Connection(db)
    report=replace_snapshot(connection,facts,native/'source')
    snapshot=report['snapshot']
    report['native_versions']=env
    report['queries']={}
    queries={
        'key_symbols':"MATCH (p:PMFact) WHERE p.snapshot=$snapshot AND p.kind='callable' AND (p.qualified_name ENDS WITH 'QueryUnitFlows' OR p.qualified_name ENDS WITH 'HandleRequest' OR p.qualified_name ENDS WITH '.send' OR p.qualified_name='getUnitFlows') RETURN p.path AS path,p.line AS line,p.qualified_name AS qualified_name,p.payload AS payload",
        'native_refined_send':"MATCH (f:Function)-[:PMRefines]->(p:PMFact) WHERE p.snapshot=$snapshot AND p.qualified_name='BaseConnector.send' RETURN f.name AS native_name,f.class_context AS native_owner,p.qualified_name AS lexical_owner,p.path AS path,p.line AS line",
        'database_call_observation':"MATCH (a:PMFact)-[r:PMSyntaxEdge]->(b:PMFact) WHERE a.snapshot=$snapshot AND a.qualified_name ENDS WITH 'QueryFlowsBySliceInfoHandler::HandleRequest' RETURN a.qualified_name AS owner,r.kind AS relationship,b.payload AS payload",
        'binding_observations':"MATCH (p:PMFact) WHERE p.snapshot=$snapshot AND p.kind='binding' AND p.path='modules/timeline/src/bootstrap.tsx' RETURN p.payload AS payload",
    }
    for name,query in queries.items():
        result=rows(connection.execute(query,{'snapshot':snapshot}))
        for item in result:
            if 'payload' in item:item['payload']=json.loads(item['payload'])
        if name=='database_call_observation':
            result=[r for r in result if 'QueryUnitFlows' in r['payload']['fact']['callee_spelling']]
        if name=='binding_observations':
            result=[r for r in result if r['payload']['fact']['left_spelling']=='window.requestData']
        report['queries'][name]={'query':query,'rows':result}
    # Real imported facts can be removed without touching native CGC functions.
    native_before=rows(connection.execute('MATCH (f:Function) RETURN count(f) AS count'))[0]['count']
    delete_snapshot(connection,snapshot)
    remaining=rows(connection.execute('MATCH (p:PMFact) WHERE p.snapshot=$snapshot RETURN count(p) AS count',{'snapshot':snapshot}))[0]['count']
    native_after=rows(connection.execute('MATCH (f:Function) RETURN count(f) AS count'))[0]['count']
    restored=replace_snapshot(connection,facts,native/'source')
    report['lifecycle']={'remaining_after_delete':remaining,'native_before':native_before,'native_after':native_after,
                         'restored_same_counts':{k:report[k]==restored[k] for k in ('facts','observed_call_relations','native_refinements')}}
    (output/'integration-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    connection.close()
    db.close()
    if handle:handle.close()
    print(json.dumps({k:report[k] for k in ('facts','observed_call_relations','native_refinements','lifecycle')}))


if __name__=='__main__':main()
