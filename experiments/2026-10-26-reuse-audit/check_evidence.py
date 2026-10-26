"""Check publication of native component observations, including unresolved cases."""
import json
from pathlib import Path


r=json.loads((Path(__file__).parent/'evidence/component-results.json').read_text(encoding='utf-8'))
assert r['schema']=='reuse-component-audit/1'
assert r['product_analysis_or_acceptance_executed'] is False and r['whole_G02_G08_accepted'] is False
scip={x['caller']:x for x in r['scip_imports']['checks']}
assert scip['plain']['cgc_direct_call'] and not scip['spaced']['cgc_direct_call'] and not scip['templated']['cgc_direct_call']
assert not scip['callback']['cgc_direct_call'] and scip['callback']['codegraph_scip_relations']==[['callback','target','Calls']]
assert r['scip_imports']['cgc_field_definition_retained'] and not r['scip_imports']['cgc_field_read_reference_in_projected_calls']
assert len(r['clangd_multilspy']['checks'])==11 and all(x['passed'] for x in r['clangd_multilspy']['checks'])
assert r['clangd_multilspy']['native_ast_root_kind']=='TranslationUnit'
assert len(r['sqlglot']['checks'])==5 and all(x['passed'] for x in r['sqlglot']['checks'])
assert r['code_map']['result']['node_count']==1 and not r['code_map']['result']['same_path_different_modules_have_distinct_ids']
cpp={x['case']:x for x in r['joern_cpp']['checks']}
assert set(cpp)=={'regular','member','isolated','after_copy','borrowed','getter'}
assert cpp['borrowed']['expected_input_dependency'] and cpp['borrowed']['native_path_count']==0
assert sum(x['matches_expected'] for x in cpp.values())==5
assert len(r['joern_cpp']['independent_compiled_fixture_oracle'])==12
assert all(x['expected']==x['actual'] for x in r['joern_cpp']['independent_compiled_fixture_oracle'])
assert r['joern_rust']['directory_input_method_count']==0 and not r['joern_rust']['ready_to_replace_rust_analyzer']
assert r['joern_rust']['file_input_method_count'] is None and not r['joern_rust']['file_input_required_case_found']
assert r['cbm_current_probe']['exit_code']==1 and r['cbm_current_probe']['node_count']==0
assert r['cbm_current_probe']['binary_release_commit']!=r['cbm_current_probe']['inspected_source_commit']
assert len(r['opentelemetry_python']['checks'])==4 and all(x['passed'] for x in r['opentelemetry_python']['checks'])
assert r['file_hash_verification']=='not_run_per_user_preference' and not r['sealed_issue_material_used']
print('OK: native component contracts, limited successes, known omissions, runtime blockers and first attempts retained.')
