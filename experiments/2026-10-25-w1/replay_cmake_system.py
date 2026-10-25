"""Replay successful native replies; preserve versioned unchanged C++ facts."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.cmake_file_api import analyze,link_source_symbols
from adapters.snapshot_inputs import git,select_inputs
from adapters.sqlite_fact_graph import validate_graph
from projectmap.version import rules_version
from projectmap.workspace import Workspace


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,data):
    with path.open('w',encoding='utf-8') as stream:json.dump(data,stream,separators=(',',':'));stream.write('\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workspace',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();old=Workspace(args.workspace);output=args.output.resolve();active=old.config['active']
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(old.source):ap.error('Choose a new output outside both repositories')
    current=rules_version(require_clean=True);graph_path=Path(active['graph']);graph=read(graph_path)
    if not graph.get('native_build'):raise ValueError('Base graph has no native configuration stage')
    baseline=graph['version']['build_version']['rules_commit'];source=graph['source_commit'];prior_snapshot=graph['snapshot']
    checked=[p for p in git(ROOT,'ls-files','-z','adapters','scripts/build_chain_closure_graph.py','scripts/build_fact_graph.py').decode('utf-8').split('\0')
             if p and not p.startswith(('adapters/python_','adapters/rust_','adapters/cmake_','adapters/path_'))]
    if git(ROOT,'diff',baseline,current,'--',*checked).strip():raise ValueError('Cached language/graph components changed; rebuild source facts')
    packages={n:importlib.metadata.version(n) for n in ('tree-sitter','tree-sitter-language-pack')}
    if any(graph['version']['build_version']['packages'][n]!=v for n,v in packages.items()) or graph['version']['build_version']['python']!=sys.version.split()[0]:
        raise ValueError('Cached C++ parser/runtime versions changed')
    if graph['provenance']['working_tree_included'] is not False:raise ValueError('Require committed-source facts')
    selected=select_inputs(old.source,source,graph['version']['config'])
    if set(r['path'] for r in selected['files'])!=set(graph['input_paths']):raise ValueError('Committed input selection changed; rebuild source facts')
    before=git(old.source,'status','--porcelain','--untracked-files=normal')
    native_nodes={n['id'] for n in graph['nodes'] if n.get('language')=='cmake'}
    graph['nodes']=[n for n in graph['nodes'] if n['id'] not in native_nodes]
    graph['edges']=[e for e in graph['edges'] if e['source'] not in native_nodes and e['target'] not in native_nodes]
    graph['diagnostics']=[d for d in graph['diagnostics'] if not d.get('kind','').startswith('cmake_')]
    reused={'nodes':len(graph['nodes']),'edges':len(graph['edges'])}
    output.mkdir(parents=True);records=[];new_nodes=[];new_edges=[]
    contexts={c['key']:c for c in graph['native_build']['contexts']}
    for receipt_path in sorted((graph_path.parent/'cmake-native').glob('*/*/receipt.json')):
        receipt=read(receipt_path)
        if receipt['source_commit']!=source or receipt['returncode']!=0 or receipt['status']!='configured':raise ValueError('Require successful matching native receipt')
        command=receipt['command'];recorded_build=Path(command[command.index('-B')+1]);recorded_project=Path(command[command.index('-S')+1])
        project=Path(receipt['project'])
        if project.is_absolute() or '..' in project.parts:raise ValueError('Unsafe recorded project path')
        recorded_repository=recorded_project
        for part in project.parts:recorded_repository=recorded_repository.parent
        started=time.monotonic()
        facts=analyze(receipt_path.parent/'build',receipt_path.parent/'source',context_key=receipt['context_key'],
            source_commit=source,expected_commit=source,selected_paths=graph['input_paths'],configure_returncode=receipt['returncode'],
            index_name=receipt['reply_index'],dependency_prefixes=[r['destination'] for r in receipt['dependencies']],
            recorded_build_root=recorded_build,recorded_repository_root=recorded_repository)
        if facts['native_context']['status']!='configured':
            write(output/'failed-native-replay.json',facts);raise ValueError('Native reply replay failed; diagnostics retained')
        joins=link_source_symbols(facts,graph);new_nodes.extend(facts['nodes']);new_edges.extend(facts['edges']+joins)
        graph['diagnostics'].extend(facts['diagnostics']);contexts[receipt['context_key']].update(facts['native_context'])
        records.append({'context':facts['native_context'],'nodes':len(facts['nodes']),'edges':len(facts['edges']),
            'source_joins':len(joins),'native_configure_executed_again':False,'replay_seconds':round(time.monotonic()-started,3)})
    if not records:raise ValueError('No native receipts replayed')
    graph['nodes'].extend(new_nodes);graph['edges'].extend(new_edges)
    snapshot=source+':cmake-system-replay:'+uuid.uuid4().hex
    version={'rules_commit':current,'packages':packages,'python':sys.version.split()[0],
        'reused_cpp_facts':{'rules_commit':baseline,'snapshot':prior_snapshot,'component_history_unchanged':True,
            'component_versions_unchanged':True,'input_selection_unchanged':True,'components':checked,'counts':reused}}
    graph.update(snapshot=snapshot,version={'source_commit':source,'snapshot':snapshot,'config':selected['config'],'build_version':version})
    graph['extractors']['cmake']={'adapter':'native_cmake_file_api_system_context/0.2.0','native_reply_replayed':True}
    graph['provenance'].update(mode='unchanged_cpp_facts_native_cmake_reply_replay',reference_used_for_extraction=False,
        file_hash_verification='not_run_per_user_preference',working_tree_included=False)
    validate_graph(graph);write(output/'graph.json',graph)
    workspace=Workspace.create(output/'workspace',old.source,revision=source,analysis=selected['config'])
    indexed=workspace.attach(output/'graph.json');changed=before!=git(old.source,'status','--porcelain','--untracked-files=normal')
    write(output/'trial.json',{'scope':'cpp_cmake_control_cached_cpp_current_native_reply_normalization','source_commit':source,
        'build':indexed,'build_version':version,'native_records':records,'original_checkout_modified':changed,
        'file_hash_verification':'not_run_per_user_preference','native_configure_executed_again':False,'cpp_extraction_executed_again':False,
        'native_normalizer_executed_again':True,'default_workspace_rebuild':False,'runtime_execution':False,'whole_G03_accepted':False})
    if changed:raise ValueError('Original checkout status changed')
    print(json.dumps({'status':indexed['status'],'counts':indexed['counts'],'contexts':len(records),'replayed':True}))


if __name__=='__main__':main()
