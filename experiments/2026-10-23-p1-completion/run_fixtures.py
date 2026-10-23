"""Evaluate the new extractors on the same three fixtures used by native tools."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.cpp_facts import analyze


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--typescript',type=Path,default=ROOT/'node_modules/typescript/lib/typescript.js')
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.resolve().is_relative_to(ROOT):raise ValueError('Use an external output directory')
    args.output.mkdir(parents=True,exist_ok=False)
    fixture=ROOT/'experiments/2026-10-23-p1/fixtures'
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
        pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    cpp=analyze({p.name:p.read_bytes() for p in fixture.glob('contracts.*')},pack.get_parser('cpp'))
    manifest=args.output/'manifest.json'
    manifest.write_text(json.dumps({'files':[{'path':p.name} for p in sorted(fixture.iterdir())]}),encoding='utf-8')
    subprocess.run(['node',str(ROOT/'adapters/typescript_facts.cjs'),str(fixture),str(manifest.resolve()),
                    str(args.typescript.resolve()),str((args.output/'typescript.json').resolve())],check=True)
    ts=json.loads((args.output/'typescript.json').read_text(encoding='utf-8'))
    nodes={n['id']:n for g in (cpp,ts) for n in g['nodes']}
    all_edges=cpp['edges']+ts['edges']
    def pairs(kind):return [(nodes[e['source']],nodes[e['target']]) for e in all_edges if e['kind']==kind]
    q=[n for n in cpp['nodes'] if n['kind']=='callable' and n['name'].endswith('::query')]
    assert len(q)==7
    assert len([e for e in cpp['edges'] if e['kind']=='DECLARES_DEFINITION'])==2
    assert {n['parameters'][0] for n in q if n['name']=='alpha::Store::query'}=={'int','constchar*'}
    member=pairs('MEMBER_TARGET_CANDIDATE')
    assert [b['name'] for a,b in member if a['line']==21 and a['path']=='contracts.h']==['beta::Store::query']
    assert [b['parameters'] for a,b in member if a['line']==16 and a['path']=='contracts.h']==[['int']]
    assert not any(a['name']=='db.get' for a,b in member)
    static=pairs('STATIC_CALL_TARGET')
    assert any(a['name']=='this.send' and b['name']=='ClientConnector.send' for a,b in static)
    assert any(a['name']=='super.send' and b['name']=='BaseConnector.send' for a,b in static)
    assert len(pairs('USES_BINDING'))==1 and len(pairs('BINDS_CALLABLE'))==1
    report={'input_kind':'same_three_authored_fixtures_as_native_tools','files':['contracts.cpp','contracts.h','transport.ts'],
            'checks':{'cpp_query_occurrences':7,'overloads_distinct':True,'namespace_targets_correct':True,
                      'smart_pointer_get_not_project_get':True,'ts_override_correct':True,'ts_binding_with_returned_callable':True},
            'counts':{name:{'nodes':len(g['nodes']),'edges':len(g['edges']),'diagnostics':len(g['diagnostics'])} for name,g in [('cpp',cpp),('typescript',ts)]},
            'graphs':{'cpp':cpp,'typescript':ts}}
    (args.output/'fixtures-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report['checks']))


if __name__=='__main__':main()
