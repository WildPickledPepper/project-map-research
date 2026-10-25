"""Fault controls for the W0 scope freeze; mutations affect temporary evaluation inputs."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile

import freeze_scope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new control result path')
    root = Path(__file__).resolve().parent
    refs = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in
            (root / name for name in ('scope-reference.json','scope-audit-reference.json','boundary-reference.json'))}
    docs = {p.name:json.loads(p.read_text(encoding='utf-8')) for p in args.inventory.glob('*.json')}
    cases = [
        ('missing_module_profile','module_profile.scripts/ftrace_tools',
         lambda r,d:r['scope-audit-reference.json'].update(profiles=[p for p in r['scope-audit-reference.json']['profiles'] if p['prefix']!='scripts/ftrace_tools'])),
        ('missing_boundary_family','all_boundary_family_references',lambda r,d:r['boundary-reference.json']['families'].pop()),
        ('incorrect_boundary_source','boundary_source.process_start',lambda r,d:r['boundary-reference.json']['families'][0]['source'].update(contains='missing_source_marker')),
        ('missing_os_mode','complete_platform_axes',lambda r,d:r['scope-audit-reference.json']['mode_axes']['desktop']['target_os'].remove('macos')),
        ('hidden_dependency','required_unresolved_dependencies_retained',lambda r,d:r['scope-audit-reference.json']['unresolved_dependencies'].pop()),
        ('invented_resource_ownership','module_scope_record.platform',lambda r,d:next(m for m in d['module-inventory.json']['modules'] if m['id']=='platform')['resource_scope'].update(semantic_ownership='proven')),
        ('borrowed_semantic_gate','no_borrowed_gate_passes',lambda r,d:next(m for m in d['module-inventory.json']['modules'] if m['id']=='platform')['gate_status'].update(G02='passed')),
    ]
    results=[]
    with tempfile.TemporaryDirectory(prefix='scope-freeze-controls-') as folder:
        for name,expected,mutation in cases:
            r,d=deepcopy(refs),deepcopy(docs);mutation(r,d)
            case=Path(folder)/name;references=case/'refs';inventory=case/'inventory'
            references.mkdir(parents=True);inventory.mkdir()
            for p,v in r.items():(references/p).write_text(json.dumps(v),encoding='utf-8')
            for p,v in d.items():(inventory/p).write_text(json.dumps(v),encoding='utf-8')
            freeze_scope.ROOT=references
            result=freeze_scope.freeze(args.source,inventory)
            failures=[c['id'] for c in result['checks'] if not c['passed']]
            row={'id':name,'expected_failure':expected,'actual_failures':failures,
                 'passed':expected in failures and result['G01']=='failed'}
            results.append(row);print(json.dumps(row),flush=True)
    result={'schema':'scope-freeze-controls/1','source_commit':refs['scope-reference.json']['source_commit'],
            'source_modified':False,'controls':results,
            'passed':all(r['passed'] for r in results)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
