"""Publish compact native component observations; keep raw graphs outside Git."""
import argparse
import json
from pathlib import Path
import re


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--raw',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():raise ValueError('Choose a new evidence directory')
    def read(path):return json.loads((args.raw/path).read_text(encoding='utf-8'))
    scip=read('scip-imports-02/result.json');front=read('frontends-02/result.json');cpp=read('joern-cpp-02/result.json')
    rust=read('joern-rust-02/result.json');otel=read('otel-01.json');cbm=read('cbm-02/result.json')
    oracle=[]
    for line in (args.raw/'joern-cpp-02/oracle.log').read_text().splitlines():
        match=re.fullmatch(r'(\w+) input=(\d+) expected=(\d+) actual=(\d+)',line)
        if match:
            name,input_value,expected,actual=match.groups()
            oracle.append({'case':name,'input':int(input_value),'expected':int(expected),'actual':int(actual)})
    if len(oracle)!=12 or any(r['expected']!=r['actual'] for r in oracle):raise ValueError('Independent fixture oracle failed')
    expected={'regular':True,'member':True,'isolated':False,'after_copy':False,'borrowed':True,'getter':True}
    cpp_rows=[]
    for row in cpp['checks']:
        observed=row['path_count']>0
        cpp_rows.append({'case':row['case'],'expected_input_dependency':expected[row['case']],
            'native_path_count':row['path_count'],'matches_expected':observed==expected[row['case']]})
    if {r['case'] for r in cpp_rows}!=set(expected):raise ValueError('Missing C++ audit case')
    clang=front['clangd'];hovers={k:v['contents']['value'] for k,v in clang['return_mode_hovers'].items()}
    result={'schema':'reuse-component-audit/1','date':'2026-10-26','origin':'native_component_probes_and_retained_source_audit',
        'product_analysis_or_acceptance_executed':False,'whole_G02_G08_accepted':False,
        'scip_imports':scip,'code_map':front['code_map'],'sqlglot':front['sqlglot'],
        'clangd_multilspy':{'clangd_version':'23.1.0','multilspy_version':clang['multilspy_version'],
            'multilspy_revision':clang['multilspy_revision'],'checks':clang['checks'],'native_hovers':hovers,
            'native_ast_root_kind':clang['semantic_ast_root']['kind'],'object_instance_analysis_executed':False},
        'joern_cpp':{'version':'4.0.665','revision':'d7a5615a30cbce12986f7a0dae9a938a5b99985e','overlays':cpp['overlays'],
            'checks':cpp_rows,'independent_compiled_fixture_oracle':oracle,
            'default_engine_max_call_depth_source':4,'default_engine_depth_is_not_unbounded':True},
        'joern_rust':{'version':'4.0.665','file_input_method_count':read('joern-rust-01/result.json').get('method_count'),
            'file_input_required_case_found':bool(read('joern-rust-01/result.json')['checks']),
            'directory_input_method_count':rust['method_count'],'required_case':'regular','case_found':bool(rust['checks']),
            'ready_to_replace_rust_analyzer':False,'cause_not_determined':True},
        'opentelemetry_python':otel,'cbm_current_probe':cbm,
        'prior_successes_retained':{'cbm':'research/experiments/2026-10-23.md','rpg_codemind':'research/experiments/2026-10-23.md',
            'codegraph_code_map':'experiments/2026-10-23-unit-flows/README.md','all_p1':'experiments/2026-10-23-p1-completion/README.md'},
        'first_attempts':[
            {'component':'SCIP audit driver','issue':'Windows GBK decode failed on native CLI UTF-8 output',
                'correction':'Explicit UTF-8 decoding; first output directory retained'},
            {'component':'SQL audit driver','issue':'Leaf name contains SQL alias; first expected physical names mismatched two cases',
                'correction':'Read physical Table AST and parse Column with SQLGlot; native leaves retained'},
            {'component':'Joern audit driver','issue':'Windows launcher parameter passing failed; Scala overlay flatten produced Char values',
                'correction':'Use environment parameters and native overlay string list; first launch/compile logs retained'},
            {'component':'Joern C++ fixture','issue':'Initial negative case read an uninitialized field',
                'correction':'Value-initialize objects; re-extract and verify all six fixtures with a compiled oracle'},
            {'component':'Joern Rust','issue':'Successful file parse had no tested method',
                'correction':'Retried directory input once; still zero methods; stopped'},
            {'component':'CBM','issue':'Fresh isolated cache failed loading saved runtime settings',
                'correction':'Retried pre-created cache directory once; same error; stopped'}],
        'file_hash_verification':'not_run_per_user_preference','sealed_issue_material_used':False}
    serialized=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
    if re.search(r'[A-Za-z]:[\\/](Users|workspace)[\\/]',serialized):raise ValueError('Workspace path in publication')
    args.output.mkdir(parents=True);(args.output/'component-results.json').write_text(serialized,encoding='utf-8')
    print(json.dumps({'clangd_checks':len(clang['checks']),'sqlglot_checks':len(front['sqlglot']['checks']),
        'joern_cpp_matches':sum(r['matches_expected'] for r in cpp_rows),'joern_cpp_cases':len(cpp_rows),
        'oracle_observations':len(oracle),'otel_checks':len(otel['checks']),
        'rust_ready':False,'cbm_current_exit_code':cbm['exit_code']}))


if __name__=='__main__':main()
