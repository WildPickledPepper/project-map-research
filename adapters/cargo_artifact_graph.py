"""Import immutable, revision-bound Cargo captures into the production graph."""
import json
from pathlib import Path
from adapters.cargo_file_api import normalize,link_source_symbols
from adapters.cargo_native import read_messages


ADAPTER_VERSION='cargo_compiler_artifact_capture_import/0.1.0'


def augment(graph,*,root,captures,parser):
    nodes=[];edges=[];diagnostics=[];contexts=[];existing={n['id'] for n in graph['nodes']}
    for expected in captures:
        directory=Path(expected['directory']);receipt=json.loads((directory/'receipt.json').read_text(encoding='utf-8'))
        if (receipt.get('schema')!='cargo-native-capture/1' or receipt.get('source_commit')!=graph['source_commit'] or
            receipt.get('source_commit')!=expected['source_commit'] or receipt.get('context_key')!=expected['context_key']):
            raise ValueError('Cargo capture source/context differs from requested snapshot')
        selected=receipt.get('selected_paths')
        if not isinstance(selected,list) or not selected or not set(selected)<=set(graph['input_paths']):
            raise ValueError('Cargo capture inputs are outside requested snapshot scope')
        fields={k:receipt[k] for k in ('source_commit','returncode','context_key','host_target','target','host_cfg','target_cfg','cargo_version','rustc_version')}
        native=normalize(json.loads((directory/'metadata.stdout').read_text(encoding='utf-8')),read_messages(directory/'build.stdout'),
            repository=root,recorded_repository=receipt['recorded_repository'],expected_commit=graph['source_commit'],**fields)
        if native['native_context']['status']!='built':raise ValueError('Cargo capture failed validation; source graph remains unchanged')
        for node in native['nodes']:
            if node['kind']=='build_configuration':node['source_request']=receipt.get('source_request')
        ids={n['id'] for n in native['nodes']}
        if ids&existing:raise ValueError('Cargo context is already present in the graph')
        joins,gaps=link_source_symbols(native,graph,root=root,parser=parser)
        nodes.extend(native['nodes']);edges.extend(native['edges']+joins);diagnostics.extend(native['diagnostics']+gaps)
        contexts.append(native['native_context']);existing.update(ids)
    # Validate all requested inputs before mutating the supplied source graph.
    graph['nodes'].extend(nodes);graph['edges'].extend(edges);graph['diagnostics'].extend(diagnostics)
    graph.setdefault('native_build',{}).setdefault('cargo_contexts',[]).extend(contexts)
    graph.setdefault('extractors',{})['cargo']=ADAPTER_VERSION
    return graph
