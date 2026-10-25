"""Join versioned native/language control stages and run production copy flow.

Native extraction/configuration is cached. Python paths and artifact propagation
run again from committed source exports; endpoint references are not inputs.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.snapshot_inputs import git,select_inputs,export_inputs,normalize_config
from adapters.python_path_values import augment as paths,ADAPTER_VERSION
from adapters.artifact_copy_graph import augment as copies
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):
    with path.open('w',encoding='utf-8') as stream:json.dump(value,stream,separators=(',',':'));stream.write('\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('source','cpp-trial','python-trial','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args();original=args.source.resolve();output=args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(original):ap.error('Choose a new output outside both repositories')
    current=rules_version(require_clean=True);cpp=read(args.cpp_trial/'graph.json');python=read(args.python_trial/'native-base.json')
    cpp_trial=read(args.cpp_trial/'trial.json');cpp_version=cpp['version']['build_version'];py_version=python['version']['build_version']
    if cpp_version!=cpp_trial['build_version'] or cpp['source_commit']!=python['source_commit']:raise ValueError('Cached stage versions differ')
    if python.get('cached_stage')!='python_semantics_and_boundaries_before_paths' or 'artifact_copy_flow' in cpp:
        raise ValueError('Require native/language stages before the copy projection')
    revision=cpp['source_commit'];unchanged=git(original,'status','--porcelain','--untracked-files=normal')
    cpp_components=cpp_version['reused_cpp_facts']['components']
    py_components=['adapters/python_facts.py','adapters/python_contexts.py','adapters/python_boundaries.py']
    native_components=['adapters/cmake_file_api.py','adapters/cmake_project.py']
    for version,components in [(cpp_version['rules_commit'],cpp_components+native_components),(py_version['rules_commit'],py_components)]:
        if git(ROOT,'diff',version,current,'--',*components).strip():raise ValueError('Cached semantic/native stage changed; extract again')
    packages={n:importlib.metadata.version(n) for n in ('tree-sitter','tree-sitter-language-pack','jedi','parso')}
    py_runtime=sys.version.split()[0]
    if cpp_version['python']!=py_runtime or python['components']!={n:packages[n] for n in ('jedi','parso')}|{'python':py_runtime}:
        raise ValueError('Cached Python runtime/Jedi versions differ')
    if any(cpp_version['packages'][n]!=packages[n] for n in ('tree-sitter','tree-sitter-language-pack')):raise ValueError('Cached C++ parser versions differ')
    for stage in (cpp,python):
        if stage['provenance'].get('working_tree_included') is not False or stage['provenance'].get('reference_used_for_extraction') is not False:
            raise ValueError('Require committed, reference-free source stages')
        selected=select_inputs(original,revision,stage['version']['config'])
        if set(r['path'] for r in selected['files'])!=set(stage['input_paths']):raise ValueError('Cached input selection changed')
        validate_graph(stage)
    if set(cpp['input_paths'])&set(python['input_paths']):raise ValueError('Control stages overlap; require explicit reconciliation')
    config=json.loads(json.dumps(cpp['version']['config']));scope=config['scope'];py_scope=python['version']['config']['scope']
    if {k:v for k,v in scope.items() if k!='include'}!={k:v for k,v in py_scope.items() if k!='include'}:
        raise ValueError('Control discovery/exclusion scopes differ')
    scope['include']=sorted(set(scope['include']+py_scope['include']));config=normalize_config(config)
    selected=select_inputs(original,revision,config);inputs=[r['path'] for r in selected['files']]
    if set(inputs)!=set(cpp['input_paths'])|set(python['input_paths']):raise ValueError('Combined input selection is not the union')
    output.mkdir(parents=True);root=output/'source';export_inputs(original,selected,root)
    py_base={'snapshot':python['snapshot'],'rules_commit':py_version['rules_commit'],'components':py_components,
        'counts':{'nodes':len(python['nodes']),'edges':len(python['edges'])}}
    cpp_base={'snapshot':cpp['snapshot'],'rules_commit':cpp_version['rules_commit'],'components':cpp_components+native_components,
        'counts':{'nodes':len(cpp['nodes']),'edges':len(cpp['edges'])}}
    python=paths(root,python)
    for key in ('nodes','edges','diagnostics','coverage'):cpp[key].extend(python[key])
    cpp['limits']=list(dict.fromkeys(cpp['limits']+python['limits']))
    cpp['input_paths']=inputs;cpp=copies(cpp)
    cpp['extractors']['python']={'components':python['components'],'path_values':ADAPTER_VERSION}
    cpp['extractors']['artifact_copy_flow']=cpp['artifact_copy_flow']['adapter']
    snapshot=revision+':artifact-copy-control:'+uuid.uuid4().hex
    version={'rules_commit':current,'packages':packages,'python':py_runtime,'reused_cpp_cmake':cpp_base,'reused_python_semantics':py_base,
        'component_history_unchanged':True,'component_versions_unchanged':True,'input_selection_unchanged':True}
    cpp.update(snapshot=snapshot,version={'source_commit':revision,'snapshot':snapshot,'config':config,'build_version':version},
        provenance={'input_kind':'git_committed_blob_export','working_tree_included':False,'reference_used_for_extraction':False,
            'mode':'cached_native_and_language_stages_current_python_paths_and_artifact_copy_flow','file_hash_verification':'not_run_per_user_preference'})
    validate_graph(cpp);write(output/'graph.json',cpp)
    workspace=Workspace.create(output/'workspace',original,revision=revision,analysis=config)
    indexed=workspace.attach(output/'graph.json');changed=unchanged!=git(original,'status','--porcelain','--untracked-files=normal')
    trial={'scope':'cpp_cmake_and_all_selected_python_control_union','source_commit':revision,'build':indexed,'build_version':version,
        'path_adapter_executed_again':True,'artifact_copy_flow_executed':True,'native_semantic_stage_executed_again':False,
        'native_configure_executed_again':False,'native_normalizer_executed_again':False,'default_workspace_rebuild':False,
        'installed_tool_tested':False,'runtime_execution':False,'original_checkout_modified':changed,
        'file_hash_verification':'not_run_per_user_preference','whole_G02_accepted':False,'whole_G03_accepted':False}
    write(output/'trial.json',trial)
    if changed:raise ValueError('Original checkout status changed')
    print(json.dumps({'status':indexed['status'],'counts':indexed['counts'],'artifact_flow':cpp['artifact_copy_flow']}))


if __name__=='__main__':main()
