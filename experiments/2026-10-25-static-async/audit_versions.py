"""Record extraction and query versions without recomputing file hashes."""
import argparse
import ast
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def functions(revision):
    tree=ast.parse(git('show',revision+':adapters/return_bridge_queries.py'))
    return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--facts-rule',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();facts=git('rev-parse',a.facts_rule);query=git('rev-parse','HEAD')
    paths=git('diff','--name-only',facts,query,'--','adapters','scripts').splitlines()
    before,after=map(functions,[facts,query]);changed=sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))
    assert paths==['adapters/return_bridge_queries.py'],paths
    assert changed==['explain_return_bridge'],changed
    result={'evidence_kind':'executed_component_source_AST_delta_audit','facts_rule':facts,'query_rule':query,
        'changed_modules':paths,'changed_functions':changed,'extracted_iframe_links_unchanged':before['iframe_links']==after['iframe_links'],
        'facts_extraction_changed':False,'file_hash_verification':'not_run_per_user_preference'}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
