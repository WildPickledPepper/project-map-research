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
python_installed=json.loads((ROOT/'evidence/python-installed.json').read_text(encoding='utf-8'))
assert python_installed['passed'] and len(python_installed['checks'])==23 and all(c['passed'] for c in python_installed['checks'])
assert python_installed['installed_rules_commit']=='81e97f21d37b0fe70a0a3739859c0bea68590ccf'
assert not python_installed['source_modified_by_tool'] and not python_installed['historical_assets_enabled']
assert {'namespace_uses_importing_entry_root','nearby_namespace_decoy_not_connected',
    'new_module_connected','renamed_module_connected','deleted_definition_removed',
    'missing_import_remains_queryable','runtime_evidence_not_fabricated'}<={c['id'] for c in python_installed['checks']}
python_rules=python_installed['installed_rules_commit']
probe=json.loads((ROOT/'evidence/python-resolver-probe.json').read_text(encoding='utf-8'))
assert probe['passed'] and len(probe['checks'])==7 and all(c['passed'] for c in probe['checks'])
assert probe['jedi']=='0.19.2' and probe['parso']=='0.8.5' and probe['cgc']==data['upstream']['commit']
assert not probe['product_code_executed'] and not probe['graph_generated']
expected_python={r['path'] for r in data['files'] if r['language']=='python'}
for name,file_count,check_count in [('python-proxy.json',23,41),('python-repository.json',119,137)]:
    score=json.loads((ROOT/'evidence'/name).read_text(encoding='utf-8'))
    assert score['passed'] and len(score['checks'])==check_count and all(c['passed'] for c in score['checks'])
    assert score['source_commit']==data['source_commit'] and score['build_version']['rules_commit']==python_rules
    assert len(score['files'])==file_count and score['python_node_counts']['code_module']==file_count
    assert all(r['graph_input'] and r['graph_coverage']['status']=='parsed' for r in score['files'])
    expected=expected_python if file_count==119 else {p for p in expected_python if p.startswith('plugins/ProfilerServerProxy/')}
    assert {r['path'] for r in score['files']}==expected
    assert sum(score['call_resolutions'].values())==score['python_node_counts']['call_site']
    assert sum(score['unresolved_call_reasons'].values())==score['call_resolutions']['unresolved']
    assert {'network_listener','route_registration','network_client','process_start','process_stop'}<=set(score['boundary_families'])
    assert not score['whole_G02_accepted'] and not score['runtime_execution']
    assert score['backend_counterpart_status']=='pending_artifact_and_instance_identity'
    for check in score['checks']:
        if check['id'].startswith('navigation.'):
            assert check['evidence']['found'] and check['evidence']['stop_reason'] is None
rust_probe=json.loads((ROOT/'evidence/rust-resolver-probe.json').read_text(encoding='utf-8'))
assert rust_probe['passed'] and len(rust_probe['checks'])==12 and all(c['passed'] for c in rust_probe['checks'])
assert rust_probe['cgc']==data['upstream']['commit']
assert rust_probe['rust_analyzer']=='rust-analyzer 0.3.3089-standalone (5ec20d044d 2026-10-18)'
assert all(c['server_health']=='ok' for c in rust_probe['checks'])
assert not any(rust_probe[k] for k in ('product_code_executed','graph_generated','cargo_invoked','build_scripts_enabled','proc_macros_enabled'))
rust_context=json.loads((ROOT/'evidence/rust-project-context.json').read_text(encoding='utf-8'))
assert rust_context['passed'] and len(rust_context['checks'])==7 and all(c['passed'] for c in rust_context['checks'])
assert rust_context['tools']['rust-analyzer']==rust_probe['rust_analyzer']
assert rust_context['tools']['cargo'].startswith('cargo 1.94.0 ') and rust_context['tools']['rustc'].startswith('rustc 1.94.0 ')
assert rust_context['native_loader_control']==[{'noDeps':True,'targets':[],'health':'ok'},
    {'noDeps':False,'targets':['worker/code/engine.rs'],'health':'ok'}]
assert not any(rust_context[k] for k in ('product_code_executed','build_scripts_executed','production_graph_generated','whole_G02_accepted'))
print('OK: native 185-file baseline; JS evidence; Python 7/41/137/23 checks; Rust 12 component and 7 Cargo context checks; G02 remains pending.')
