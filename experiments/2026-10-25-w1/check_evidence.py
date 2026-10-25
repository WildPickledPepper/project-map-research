"""Check native component evidence without promoting it to language acceptance."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'evidence/native-summary.json').read_text(encoding='utf-8'))
assert data['upstream']['commit']=='93c9685bff9151f50a3121e9913e5ba2d27c1191'
assert data['upstream']['version']=='0.6.13' and not data['upstream']['tracked_files_modified']
assert len(data['files'])==185 and data['errors']==0
assert all(r['status']=='parsed' for r in data['files'])
assert {language:sum(r['language']==language for r in data['files']) for language in ('javascript','python','rust')}=={'javascript':53,'python':119,'rust':13}
for language,counts in data['counts_by_language'].items():
    for key,total in counts.items():
        assert sum(r['counts'].get(key,0) for r in data['files'] if r['language']==language)==total
assert not data['cross_file_resolution_executed'] and not data['normalized_graph_produced']
assert data['G02']=='not_accepted' and not data['historical_assets_enabled']
scope=json.loads((ROOT/'evidence/javascript-repository-scope.json').read_text(encoding='utf-8'))
rules='7fbd29bd03dcc7f19c524d90e15612ac74757a55'
assert scope['passed'] and scope['checks']['total']==scope['checks']['passed']==1218 and not scope['checks']['failed']
expected_js={r['path'] for r in data['files'] if r['language']=='javascript'}
assert len(scope['files'])==53 and {r['path'] for r in scope['files']}==expected_js
assert all(r['graph_input'] and r['coverage']['status']=='parsed' and r['node_counts']['code_module']==1 for r in scope['files'])
assert scope['index_counts']['input_files']==2363 and scope['index_counts']['nodes']==289504 and scope['index_counts']['edges']==422496
assert scope['call_resolutions']=={'unresolved':880,'static_declaration':182,'ambiguous_callable_type':1}
assert sum(scope['unresolved_call_reasons'].values())==880
assert len(scope['unresolved_modules'])==66 and sum(scope['module_resolution_states'].values())==99
for name in ('javascript-chain.json','javascript-repository-chain.json'):
    score=json.loads((ROOT/'evidence'/name).read_text(encoding='utf-8'))
    assert score['source_commit']==data['source_commit']==scope['source_commit']
    assert score['build_version']['rules_commit']==scope['build_version']['rules_commit']==rules
    assert score['passed'] and len(score['checks'])==14 and all(c['passed'] for c in score['checks'])
    assert not score['runtime_execution'] and not score['whole_G02_accepted']
    dynamic=next(c for c in score['checks'] if c['id']=='dynamic_selection_retained')
    assert set(dynamic['candidates'])=={'Mark.wrapMatches','Mark.wrapMatchesAcrossElements'}
    for check in score['checks']:
        if 'result' in check:assert check['result']['found'] and check['result']['stop_reason'] is None
installed=json.loads((ROOT/'evidence/javascript-installed.json').read_text(encoding='utf-8'))
assert installed['passed'] and len(installed['checks'])==22 and all(c['passed'] for c in installed['checks'])
assert installed['installed_rules_commit']==rules and not installed['source_modified_by_tool'] and not installed['historical_assets_enabled']
assert {'added_module_connected','renamed_module_connected','deleted_definition_removed','same_name_decoy_not_connected'}<={c['id'] for c in installed['checks']}
assert not scope['whole_G02_accepted'] and not scope['runtime_execution']
print('OK: native 185-file baseline; JS 53-file coverage, two 14-check chains and 22 installed CLI checks; G02 remains pending.')
