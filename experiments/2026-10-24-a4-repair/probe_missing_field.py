"""Replay the known whole-object consumer / deleted-field counterexample."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.return_bridge_queries import explain_return_bridge

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();g=json.loads(a.graph.read_text(encoding='utf-8'))
    row=next(r for r in g['protocol']['results'] if r['name']=='memoryCurveGet' and len(r['matches'])==1)
    provider=row['matches'][0]['provider']
    before=explain_return_bridge(g,provider,field_path=['lines'])
    for f in g['data']['serialization']['functions']:
        f['field_mappings']=[m for m in f['field_mappings'] if 'lines' not in m['wire_path']]
    after=explain_return_bridge(g,provider,field_path=['lines'])
    result={'before_links':before['total_links'],'after_deleted_field_links':after['total_links'],
        'passed':before['total_links']>0 and after['total_links']==0,'scope':'in-memory extracted-fact mutation; original graph/source not changed'}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
