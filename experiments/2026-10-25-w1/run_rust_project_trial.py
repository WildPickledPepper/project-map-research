"""Automatically discover Cargo roots and query native definitions per source cfg.

This experiment does not read the independent reference or emit a production graph.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import url2pathname

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.repository_discovery import discover as repository
from adapters.snapshot_inputs import export_inputs
from adapters.rust_project import binary,cargo_options,configuration_matrix,discover,tool_output
from adapters.rust_analyzer import Client
from adapters.syntax_supplement import walk,text,parents


def query_points(root,metadata,parser,workspace):
    points=[]
    for path in sorted({t['path'] for p in metadata['packages'] if p['workspace']==workspace for t in p['targets'] if t['input']}):
        raw=(root/path).read_bytes();tree=parser.parse(raw)
        for node in walk(tree.root_node):
            if node.type!='call_expression':continue
            function=node.child_by_field_name('function');name=function
            while name and name.type not in {'identifier','field_identifier'}:
                name=name.child_by_field_name('field') or name.child_by_field_name('name') or name.child_by_field_name('function')
            if name is None:continue
            before=raw.splitlines()[name.start_point[0]][:name.start_point[1]].decode('utf-8')
            conditions=[]
            for scope in [node,*parents(node)]:
                sibling=scope.prev_named_sibling
                while sibling and sibling.type in {'attribute_item','line_comment','block_comment'}:
                    if sibling.type=='attribute_item' and ('cfg(' in text(sibling) or 'cfg_attr(' in text(sibling)):
                        conditions.append(text(sibling))
                    sibling=sibling.prev_named_sibling
            points.append({'path':path,'line':name.start_point[0]+1,'callee':text(function),
                'position':{'line':name.start_point[0],'character':len(before.encode('utf-16-le'))//2+1},
                'source_conditions':list(dict.fromkeys(conditions))})
    return points


def locations(values,root):
    records=[]
    for value in (values if isinstance(values,list) else [values] if values else []):
        uri=value.get('targetUri',value.get('uri'));path=Path(url2pathname(urlparse(uri).path)).resolve()
        selected=value.get('targetSelectionRange',value.get('range'))
        if not path.is_relative_to(root):
            records.append({'status':'outside_input','line':selected['start']['line']+1});continue
        records.append({'path':path.relative_to(root).as_posix(),'line':selected['start']['line']+1,
            'utf16_column':selected['start']['character']+1,'status':'input_source_navigation'})
    return records


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--revision',required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--prepare-dependencies',action='store_true')
    args=ap.parse_args();args.output=args.output.resolve();args.source=args.source.resolve()
    if args.output.exists() or args.output.is_relative_to(args.source) or args.output.is_relative_to(ROOT):
        ap.error('Choose a new output directory outside source and research repositories')
    inventory=repository(args.source,args.revision)
    selected=[r for r in inventory['files'] if r['role'] not in {'generated','third_party'} and
        (r['language']=='rust' or Path(r['path']).name in {'Cargo.toml','Cargo.lock'} or '/.cargo/' in '/'+r['path'])]
    args.output.mkdir(parents=True)
    export_inputs(args.source,{'files':[{k:r[k] for k in ('path','object','mode')} for r in selected]},args.output/'source')
    root=args.output/'source';paths=[r['path'] for r in selected];metadata=discover(root,paths)
    contexts,diagnostics=configuration_matrix(root,paths,metadata)
    if metadata['diagnostics']:raise ValueError(json.dumps(metadata['diagnostics']))
    tools={name:tool_output([binary(name),'--version'],root).strip() for name in ('cargo','rustc','rust-analyzer')}
    if args.prepare_dependencies:
        for workspace in metadata['workspaces']:
            # Registry downloads/lock resolution only; no compilation or build scripts.
            print('Prepare dependencies for '+workspace,flush=True)
            raw=tool_output([binary('cargo'),'metadata','--format-version','1','--all-features',
                '--manifest-path',str(root/workspace)],(root/workspace).parent,timeout=300)
            target=args.output/(workspace+'.resolved-metadata.json');target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(raw,encoding='utf-8')
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    parser=pack.get_parser('rust');rows=[];total_queries=0
    for i,context in enumerate(contexts):
        for j,workspace in enumerate(metadata['workspaces']):
            name=f'context-{i:03}-{j:02}';responses=[]
            points=query_points(root,metadata,parser,workspace)
            with Client(binary('rust-analyzer'),root,str(root/workspace),args.output/(name+'.log'),
                    cargo=cargo_options(context)) as client:
                for point in points:
                    try:
                        response=client.at('textDocument/definition',point['path'],point['position'])
                        responses.append({**point,'definitions':locations(response,root)})
                    except RuntimeError as error:responses.append({**point,'error':str(error)})
                health=[e['params'] for e in client.events if e.get('method')=='experimental/serverStatus']
                (args.output/(name+'-events.json')).write_text(json.dumps(client.events,indent=2),encoding='utf-8')
            rows.append({'context':context,'workspace':workspace,'health':health[-1]['health'] if health else 'not_reported','queries':responses})
            total_queries+=len(responses)
            (args.output/(name+'.json')).write_text(json.dumps(rows[-1],indent=2),encoding='utf-8')
            print(json.dumps({'context':i,'workspace':workspace,'queries':len(responses),
                'health':rows[-1]['health'],'found':sum(bool(r.get('definitions')) for r in responses)}),flush=True)
    result={'schema':'rust-native-project-trial/1','source_commit':inventory['source_commit'],'tools':tools,
        'input_paths':paths,
        'rust_files':[p for p in paths if p.endswith('.rs')],'metadata':metadata,'contexts':rows,
        'context_diagnostics':diagnostics,'product_code_executed':False,'build_scripts_executed':False,
        'production_graph_generated':False,'whole_G02_accepted':False,
        'scope':'Cargo target root call definitions; source modules are loaded by native analyzer; not full Rust graph'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'contexts':len(rows),'queries':total_queries,'diagnostics':dict(Counter(d['kind'] for d in diagnostics))}))


if __name__=='__main__':main()
