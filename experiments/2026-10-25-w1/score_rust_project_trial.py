"""Score native Cargo entry queries after generation; references never guide loading."""
import argparse
import itertools
import json
from pathlib import Path
import re


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();base=Path(__file__).resolve().parent
    data=json.loads((args.trial/'result.json').read_text(encoding='utf-8'))
    reference=json.loads((base/'rust-project-reference.json').read_text(encoding='utf-8'))
    baseline=json.loads((base/'evidence/native-summary.json').read_text(encoding='utf-8'))
    if args.output.exists():ap.error('Choose a new score output')
    checks=[]
    def check(name,passed,**evidence):checks.append({'id':name,'passed':bool(passed),**evidence})
    check('source_commit',data['source_commit']==reference['source_commit']==baseline['source_commit'])
    check('rust_source_input_scope',set(data['rust_files'])=={r['path'] for r in baseline['files'] if r['language']=='rust'})
    check('pinned_tools',data['tools']['rust-analyzer']=='rust-analyzer 0.3.3089-standalone (5ec20d044d 2026-10-18)' and
          data['tools']['cargo'].startswith('cargo 1.94.0 ') and data['tools']['rustc'].startswith('rustc 1.94.0 '))
    check('cargo_workspace_identities',set(data['metadata']['workspaces'])==set(reference['workspaces']) and
          {p['manifest'] for p in data['metadata']['packages']}==set(reference['workspaces']))
    check('shared_entry_target_retains_workspace',all(p['workspace']==p['manifest'] and
          any(t['path']==reference['entry_source'] and t['input'] for t in p['targets']) for p in data['metadata']['packages']))
    expected=set(itertools.product(reference['workspaces'],reference['operating_systems'],(False,True),(False,True)))
    observed=set()
    for i,row in enumerate(data['contexts']):
        context=row['context'];operating_system=next(re.fullmatch(r'target_os="(.*)"',v)[1]
            for v in context['cfg'] if v.startswith('target_os='))
        enabled=reference['default_feature'] in context['features']
        observed.add((row['workspace'],operating_system,context['debug_assertions'],enabled))
        selected=[b for b in reference['branches'] if b['feature_default']==enabled and
            ('debug_assertions' not in b or b['debug_assertions']==context['debug_assertions']) and
            ('os' not in b or operating_system in b['os'])]
        branch=selected[0] if len(selected)==1 else None
        for callee in reference['calls']:
            candidates=[q for q in row['queries'] if q['path']==reference['entry_source'] and q['callee']==callee]
            query=candidates[0] if len(candidates)==1 else {}
            active=branch is not None and branch['call']==callee
            targets=query.get('definitions',[])
            correct=(len(candidates)==1 and 'error' not in query and
                (len(targets)==1 and targets[0].get('path')==branch['target'] and targets[0]['line']==branch['line']
                 if active else not targets))
            check(f'context.{i}.{callee}',correct,workspace=row['workspace'],os=operating_system,
                debug_assertions=context['debug_assertions'],feature_default=enabled,active=active,
                query=query)
    check('complete_entry_context_matrix',observed==expected and len(data['contexts'])==len(expected),count=len(observed))
    check('native_server_health',all(r['health']=='ok' for r in data['contexts']))
    check('source_only_not_production_graph',not any(data[k] for k in ('product_code_executed','build_scripts_executed','production_graph_generated','whole_G02_accepted')))
    result={'schema':'rust-native-project-score/1','source_commit':data['source_commit'],'tools':data['tools'],
        'rust_input_files':data['rust_files'],'metadata':data['metadata'],
        'context_diagnostics':data['context_diagnostics'],'contexts':len(data['contexts']),
        'native_queries':sum(len(r['queries']) for r in data['contexts']),
        'checks':checks,'passed':all(c['passed'] for c in checks),'product_code_executed':False,
        'build_scripts_executed':False,'production_graph_generated':False,'whole_G02_accepted':False,
        'supported_product_builds_established':False,
        'tracked_lockfiles':[p for p in data['input_paths'] if Path(p).name=='Cargo.lock'] if 'input_paths' in data else reference['tracked_lockfiles'],
        'lockfile_inventory_basis':'automatic_trial_input_paths' if 'input_paths' in data else 'manual_source_audit_reference',
        'generated_analysis_lockfiles':[p.relative_to(args.trial/'source').as_posix() for p in (args.trial/'source').rglob('Cargo.lock')],
        'scope':'native Cargo entry dispatch across source-derived contexts; full Rust semantic graph and boundaries pending'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
