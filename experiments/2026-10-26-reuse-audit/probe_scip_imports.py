"""Probe existing SCIP import components with an authored index, not compiler output."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


SOURCE='''int target(int value) { return value; }
template<class T> T generic(T value) { return value; }
void plain() { target(1); }
void spaced() { target (1); }
void callback() { auto saved = &target; }
void templated() { generic<int>(1); }
struct Box { int field; };
void reads() { Box box; int result = box.field; }
'''


def run(args):
    if args.output.exists():raise ValueError('Choose a new audit output directory')
    args.output.mkdir(parents=True);root=args.output/'fixture';root.mkdir()
    (root/'main.cpp').write_text(SOURCE,encoding='utf-8')
    sys.path.insert(0,str(args.cgc/'src'))
    from codegraphcontext.tools import scip_pb2 as p
    from codegraphcontext.tools.scip_indexer import ScipIndexParser
    index=p.Index();doc=index.documents.add();doc.relative_path='main.cpp'
    symbols={};lines=SOURCE.splitlines()
    definitions=[('target',0,p.SymbolInformation.Function),('generic',1,p.SymbolInformation.Function),
        ('plain',2,p.SymbolInformation.Function),('spaced',3,p.SymbolInformation.Function),
        ('callback',4,p.SymbolInformation.Function),('templated',5,p.SymbolInformation.Function),
        ('Box',6,p.SymbolInformation.Struct),('field',6,p.SymbolInformation.Field),('reads',7,p.SymbolInformation.Function)]
    for name,line,kind in definitions:
        symbol='cxx . . $ '+name+('().' if kind==p.SymbolInformation.Function else '#')
        symbols[name]=symbol;start=lines[line].index(name)
        occ=doc.occurrences.add(symbol=symbol,symbol_roles=1);occ.range.extend([line,start,start+len(name)])
        occ.enclosing_range.extend([line,0,line,len(lines[line])]);doc.symbols.add(symbol=symbol,kind=kind,display_name=name)
    references=[('plain','target',2),('spaced','target',3),('callback','target',4),('templated','generic',5),('reads','field',7)]
    for caller,callee,line in references:
        start=lines[line].rindex(callee);occ=doc.occurrences.add(symbol=symbols[callee])
        occ.range.extend([line,start,start+len(callee)])
    idx=root/'index.scip';idx.write_bytes(index.SerializeToString())
    parsed=ScipIndexParser().parse(idx,root)
    (args.output/'cgc-native.json').write_text(json.dumps(parsed,indent=2),encoding='utf-8')
    data=parsed['files'][str((root/'main.cpp').resolve())]
    reverse={v:k for k,v in symbols.items()}
    cgc_pairs=[(reverse.get(c['caller_symbol']),c['callee_name']) for c in data['function_calls_scip']]
    env={**os.environ,'CODEGRAPH_CACHE_DIR':str(args.output/'codegraph-cache'),'CODEGRAPH_AUTO_SCIP':'0'}
    start=time.perf_counter()
    command=[str(args.codegraph),'index','--full','--scip',str(idx),str(root)]
    proc=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    (args.output/'codegraph.log').write_text(proc.stdout+proc.stderr,encoding='utf-8')
    codegraph_pairs=[];tables={};elapsed=round(time.perf_counter()-start,3)
    if proc.returncode==0:
        databases=list((args.output/'codegraph-cache').rglob('graph.db'))+list(root.rglob('graph.db'))
        if len(databases)!=1:raise ValueError(f'Expected one native graph, got {len(databases)}')
        with sqlite3.connect(databases[0].as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            for table in ('nodes','edges'):
                tables[table]=[dict(r) for r in db.execute('SELECT * FROM '+table)]
        (args.output/'codegraph-native.json').write_text(json.dumps(tables,indent=2),encoding='utf-8')
        names={n['id']:n['name'] for n in tables['nodes']}
        for e in tables['edges']:
            if 'Scip' in json.dumps(e):codegraph_pairs.append([names.get(e.get('src')),names.get(e.get('dst')),e.get('relation')])
    checks=[]
    for caller,callee,line in references:
        expected=caller!='callback' and callee!='field'
        checks.append({'caller':caller,'target':callee,'source_line':line+1,'expected_direct_call':expected,
            'cgc_direct_call':(caller,callee) in cgc_pairs,
            'codegraph_scip_relations':[r for r in codegraph_pairs if r[:2]==[caller,callee]]})
    result={'schema':'reuse-scip-component-audit/1','input_origin':'authored_scip_index_not_compiler_output',
        'source_fixture':SOURCE,'cgc_revision':'93c9685bff9151f50a3121e9913e5ba2d27c1191',
        'codegraph_revision':'7bac941c1916d34fae0e93dd0ffeaef360d741fb',
        'codegraph_exit_code':proc.returncode,'codegraph_seconds':elapsed,'checks':checks,
        'cgc_field_definition_retained':any(v['name']=='field' for v in data['variables']),
        'cgc_field_read_reference_in_projected_calls':any(c['callee_symbol']==symbols['field'] for c in data['function_calls_scip']),
        'cgc_retains_symbol_table':bool(parsed['symbol_table']),
        'scope':'SCIP_component_import_only_no_product_or_native_cpp_indexer_execution',
        'file_hash_verification':'not_run_per_user_preference'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('cgc','codegraph','output'):ap.add_argument('--'+name,type=Path,required=True)
    run(ap.parse_args())
