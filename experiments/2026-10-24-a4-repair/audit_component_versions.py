"""Audit query/controller changes separately from the frozen extraction build."""
import argparse
import ast
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],text=True).strip()
def module(revision,path):return ast.parse(git('show',revision+':'+path))
def functions(tree):return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--facts-rule',default='573330f')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();current=git('rev-parse','HEAD');facts=git('rev-parse',a.facts_rule)
    paths=git('diff','--name-only',facts,current,'--','adapters','scripts').splitlines()
    assert set(paths)=={'adapters/return_bridge_queries.py','adapters/snapshot_refresh.py'},paths
    before,after=[functions(module(v,'adapters/return_bridge_queries.py')) for v in [facts,current]]
    changed=sorted(n for n in set(before)|set(after) if before.get(n)!=after.get(n))
    assert changed==['dependency_path','explain_return_bridge'],changed
    classes=[next(n for n in module(v,'adapters/snapshot_refresh.py').body if isinstance(n,ast.ClassDef) and n.name=='Refresher') for v in [facts,current]]
    old,new=map(functions,classes)
    methods=sorted(n for n in set(old)|set(new) if old.get(n)!=new.get(n))
    assert methods==['validate'],methods
    result={'evidence_kind':'executed_component_source_AST_delta_audit','facts_rule':facts,
        'query_controller_rule':current,'changed_source_modules':paths,'changed_query_functions':changed,
        'changed_controller_methods':methods,'extracted_iframe_links_ast_unchanged':before['iframe_links']==after['iframe_links'],
        'facts_extraction_changed':False,'complete_fact_rebuild_required_for_this_delta':False,
        'scope':'existing snapshots retain their extraction version; final query/controller checks record their own code version',
        'file_hash_verification':'not_run_per_user_preference'}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
