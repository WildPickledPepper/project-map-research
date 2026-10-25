"""Evaluate named source consumers on the complete graph; no graph mutation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.return_bridge_queries import explain_return_bridge

CASES=[
    ('iterations-helper','queryIterations',['iterationOrRankId'],'getiterationOptions','helper_return',None),
    ('stages-helper','queryStages',['data'],'getStageOptions','helper_return',None),
    ('memscope-worker','getBlocksGraphData',['blocks'],'getBarNewData','source_argument_handoff','workerSetMemoryBlockData'),
    ('snapshot-pagination','getSnapshotBlocks',['blocks'],'fetchSnapshotViewBlocksPaginated','helper_return',None),
    ('snapshot-worker','getSnapshotBlocks',['blocks'],'getBarNewData','source_argument_handoff','workerSetMemoryBlockData'),
]

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--callback-facts',type=Path,help='Diagnostic only: evaluate an unpublished callback component substitution')
    a=p.parse_args();started=time.monotonic()
    g=json.loads(a.graph.read_text(encoding='utf-8'));nodes={n['id']:n for n in g['nodes']}
    if a.callback_facts:
        from adapters.callback_graph import augment_callbacks
        facts=json.loads(a.callback_facts.read_text(encoding='utf-8'))
        component=augment_callbacks({'snapshot':g['snapshot'],'source_commit':g['source_commit'],'nodes':[],
            'edges':[],'provenance':{},'extractors':{},'diagnostics':[]},facts)
        g['response_callbacks']=component['response_callbacks']
        del component,facts
    result={'evidence_kind':'executed_source_development_chain_replay','source_commit':g['source_commit'],
        'snapshot':g['snapshot'],
        'facts_version':g['version']['build_version'],
        'query_version':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'independent_holdout':False,'runtime_scenarios_executed':0,'cases':[],
        'unpublished_callback_component_substitution':bool(a.callback_facts),
        'graph_counts':{'nodes':len(g['nodes']),'edges':len(g['edges']),'inputs':len(g['input_paths']),
            'providers':len(g['protocol']['providers']),'frontend_api_symbols':len(g['frontend']['api_symbols']),
            'protocol_results':dict(Counter(r['status'] for r in g['protocol']['results']))}}
    cache={}
    for identity,api,field,consumer_name,mode,callee in CASES:
        protocols=[r for r in g['protocol']['results'] if r['name']==api]
        providers=sorted({m['provider'] for r in protocols for m in r['matches']})
        found=[];statuses=[]
        for provider in providers:
            key=(provider,tuple(field))
            if key not in cache:cache[key]=explain_return_bridge(g,provider,field_path=field)
            query=cache[key];statuses.append({'provider':provider,'status':query['status'],'truncated':query['truncated'],
                'gaps':sorted({d['kind'] for d in query['gaps']})})
            for link in query['links']:
                for entry in link.get('consumers',[]):
                    consumer=entry['consumer'];symbol=nodes[consumer['source_symbol']]
                    if symbol['name']!=consumer_name or consumer['mode']!=mode or callee and consumer.get('callee')!=callee:continue
                    found.append({'source':{k:symbol[k] for k in ['id','name','path','line']},'mode':mode,
                        'callee':consumer.get('callee'),'evidence':consumer['evidence'],
                        'field_paths':sorted({tuple(d['path']) for d in consumer['matching_dependencies']}),
                        'field_mappings':sorted({tuple(m['wire_path']) for m in entry['value_mappings']}),
                        'condition_kinds':sorted({c.get('kind','source_guard') for d in consumer['matching_dependencies'] for c in d.get('conditions',[])})})
        result['cases'].append({'id':identity,'api':api,'field':field,'consumer':consumer_name,'expected_mode':mode,
            'protocol_statuses':sorted({r['status'] for r in protocols}),'providers':providers,'queries':statuses,
            'connected':bool(found),'consumers':found})
        result['elapsed_seconds']=round(time.monotonic()-started,3)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'case':identity,'connected':bool(found),'consumers':len(found),'queries':statuses}),flush=True)
    result['all_five_connections']=all(r['connected'] for r in result['cases'])
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
