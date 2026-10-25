"""Inspect native Rust path API identity before adding path-value propagation."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.rust_project import binary,tool_output
from adapters.rust_semantics import analyze
from projectmap.version import rules_version


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new output directory')
    rules=rules_version(require_clean=True)
    source=args.output/'source';source.mkdir(parents=True)
    files={'Cargo.toml':'[package]\nname="path_primitives_fixture"\nversion="0.1.0"\nedition="2021"\n',
        'src/lib.rs':'''use std::path::Path;
const PARTS:[&str;3]=["assets","services","worker"];
pub fn assemble(root:&Path){
 let mut output=root.to_path_buf();
 for piece in PARTS {output.push(piece);}
 #[cfg(windows)] output.set_extension("exe");
 let _=std::process::Command::new(output).arg("--configured").spawn();
}
mod unrelated {
 pub struct PathBuf;
 impl PathBuf {pub fn push(&self,_value:&str){}}
 pub fn entry(value:PathBuf){value.push("other");}
}
'''}
    for path,text in files.items():
        target=source/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
    host=next(s.removeprefix('host: ') for s in tool_output([binary('rustc'),'-vV'],source).splitlines() if s.startswith('host: '))
    import os
    import tree_sitter_language_pack as pack
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    graph=analyze(source,list(files),pack.get_parser('rust'),contexts=[('Cargo.toml',{'target':host,'features':[],'debug_assertions':False})],output=args.output/'native')
    (args.output/'facts.json').write_text(json.dumps(graph,indent=2)+'\n',encoding='utf-8')
    nodes={n['id']:n for n in graph['nodes']};apis={}
    for edge in graph['edges']:
        if edge['kind']=='EXTERNAL_CALL_REFERENCE':
            apis.setdefault(edge['source'],[]).append(nodes[edge['target']]['external_declaration'])
    observations=[]
    for node in graph['nodes']:
        if node['kind']=='call_site' and node['name'] in {'root.to_path_buf','output.push','output.set_extension','value.push'}:
            observations.append({'name':node['name'],'line':node['line'],'expression':node['expression'],
                'resolution':node['resolution'],'api_declarations':apis.get(node['id'],[]),'conditions':node['conditions']})
    checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    for name,canonical in [('root.to_path_buf','std::path::Path::to_path_buf'),('output.push','std::path::PathBuf::push'),
                            ('output.set_extension','std::path::PathBuf::set_extension')]:
        check('native_identity.'+name,any(n['name']==name and any(a['canonical']==canonical for a in n['api_declarations']) for n in observations))
    check('local_pathbuf_homonym_not_std',any(n['name']=='value.push' and not n['api_declarations'] and n['resolution'] in {'inferred_unique','candidate','static_declaration'} for n in observations))
    bindings=[{k:n[k] for k in ('id','path','line','name','binding_kind')} for n in graph['nodes'] if n['kind']=='binding' and n['name']=='piece']
    check('current_loop_binding_gap_observed',not bindings)
    result={'schema':'native-path-primitives-probe/1','origin':'executed_independent_native_analysis','rules_commit':rules,
        'tools':{name:tool_output([binary(name),'--version'],source).strip() for name in ('cargo','rustc','rust-analyzer')},
        'target':host,'observations':observations,'loop_pattern_bindings':bindings,
        'checks':checks,'passed':all(c['passed'] for c in checks),'interpretation':'component_identity_and_existing_gap_not_path_propagation_acceptance',
        'path_value_propagation_implemented':False,'product_executed':False,'process_counterpart_connected':False,'whole_G03_accepted':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
