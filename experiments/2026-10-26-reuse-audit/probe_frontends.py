"""Exercise native language-server, SQL lineage and endpoint component contracts."""
import argparse
import asyncio
import importlib.metadata
import json
from pathlib import Path
import subprocess
import time


HEADER='''struct State { int value; };
struct Box {
  State state;
  State copy() const { return state; }
  const State& borrow() const { return state; }
  State* address() { return &state; }
  int choose(int v) { return v; }
  int choose(double v) { return int(v); }
};
namespace left { inline int named() { return 1; } }
namespace right { inline int named() { return 2; } }
'''
MAIN='''#include "objects.h"
int main() {
  Box first, second;
  auto copy = first.copy();
  const auto& borrow = first.borrow();
  auto* ptr = first.address();
  int a = first.choose(1);
  int b = second.choose(1.5);
  return left::named() + right::named() + borrow.value + copy.value + ptr->value + a + b;
}
'''


def sql_probe():
    import sqlglot
    from sqlglot.lineage import lineage
    cases=[('alias','SELECT a.value AS result FROM readings a','result',{'readings.value'}),
        ('cte','WITH b AS (SELECT value FROM readings) SELECT b.value AS result FROM b','result',{'readings.value'}),
        ('join','SELECT a.value + b.extra AS result FROM readings a JOIN adjustments b ON a.id=b.id',
            'result',{'readings.value','adjustments.extra'})]
    rows=[]
    for name,query,column,expected in cases:
        graph=lineage(column,query,schema={'readings':{'id':'INT','value':'INT'},'adjustments':{'id':'INT','extra':'INT'}},dialect='sqlite')
        native=[n for n in graph.walk() if not n.downstream]
        leaves={n.expression.name+'.'+sqlglot.parse_one(n.name,read='sqlite').name for n in native
            if isinstance(n.expression,sqlglot.exp.Table)}
        rows.append({'case':name,'sql':query,'expected':sorted(expected),'actual':sorted(leaves),
            'native_leaves':[{'name':n.name,'expression':n.expression.sql(),'kind':type(n.expression).__name__} for n in native],
            'passed':leaves==expected})
    query=sqlglot.parse_one('SELECT value FROM readings WHERE id = ?',read='sqlite')
    placeholders=list(query.find_all(sqlglot.exp.Placeholder))
    rows.append({'case':'parameter_ast','expected':1,'actual':len(placeholders),'passed':len(placeholders)==1})
    try:
        lineage('value','UPDATE readings SET value = ?',schema={'readings':{'value':'INT'}},dialect='sqlite')
        rejected=False
    except sqlglot.errors.SqlglotError:rejected=True
    rows.append({'case':'update_not_misrepresented_as_select_lineage','passed':rejected})
    return {'version':sqlglot.__version__,'checks':rows,'host_connection_identity_and_dynamic_sql_not_supplied':True}


async def clang_probe(root,binary):
    from multilspy import LanguageServer
    from multilspy.multilspy_config import MultilspyConfig
    from multilspy.multilspy_logger import MultilspyLogger
    root.mkdir();(root/'objects.h').write_text(HEADER,encoding='utf-8');(root/'main.cpp').write_text(MAIN,encoding='utf-8')
    (root/'compile_commands.json').write_text(json.dumps([{'directory':str(root),'file':str(root/'main.cpp'),
        'arguments':['clang++','-std=c++17','-c',str(root/'main.cpp')]}]),encoding='utf-8')
    config=MultilspyConfig.from_dict({'code_language':'cpp','server_binary':str(binary)})
    lsp=LanguageServer.create(config,MultilspyLogger(),str(root));rows=[]
    def position(line,token):return line,MAIN.splitlines()[line].index(token)
    async with lsp.start_server():
        for name,line,token,expected_line in [('copy',3,'copy()',3),('borrow',4,'borrow()',4),('address',5,'address()',5),
            ('int_overload',6,'choose',6),('double_overload',7,'choose',7),('left_scope',8,'left::named',9),('right_scope',8,'right::named',10)]:
            row,col=position(line,token)
            if 'scope' in name:col+=token.index('named')
            targets=await lsp.request_definition('main.cpp',row,col)
            actual=[{'path':t.get('relativePath'),'line':t['range']['start']['line']} for t in targets]
            rows.append({'case':name,'expected_header_line_zero_based':expected_line,'actual':actual,
                'passed':len(actual)==1 and actual[0]['path']=='objects.h' and actual[0]['line']==expected_line})
        hovers={}
        for name,line in [('copy',3),('borrow',4),('address',5)]:
            col=HEADER.splitlines()[line].index(name)
            hovers[name]=await lsp.request_hover('objects.h',line,col)
        with lsp.open_file('main.cpp'):
            ast=await lsp.server.send_request('textDocument/ast',{'textDocument':{'uri':(root/'main.cpp').as_uri()}})
        for name,mode in [('copy','State copy()'),('borrow','State &borrow()'),('address','State *address()')]:
            value=hovers[name]['contents']['value']
            rows.append({'case':'hover_'+name,'expected_signature_fragment':mode,'passed':mode in value})
        rows.append({'case':'semantic_ast','passed':bool(ast) and ast.get('kind')=='TranslationUnit'})
        return {'multilspy_version':importlib.metadata.version('multilspy'),'multilspy_revision':'62acb3cf2d7a0746992ca08767d8a4fded402ebb',
            'checks':rows,'return_mode_hovers':hovers,'semantic_ast_root':ast,'object_aliases_not_selected':True}


def endpoints_probe(repository,node):
    script='''import {pathToFileURL} from 'node:url';
const root=process.argv[1];
const {Graph}=await import(pathToFileURL(root+'/src/core/graph.mjs'));
const m=await import(pathToFileURL(root+'/src/core/endpoints.mjs'));
const g=new Graph();
const first=m.addEndpoint(g,'/api/items','GET','first-service');
const second=m.addEndpoint(g,'/api/items','GET','second-service');
console.log(JSON.stringify({non_api_path:m.normalizeEndpoint('/timeline/items'),
  normalized:m.normalizeEndpoint('/api//items/'),
  parameter_paths_match:m.endpointCompatible('/api/items/${id}','/api/items/{key}'),
  same_path_different_modules_have_distinct_ids:first!==second,node_count:g.allNodes().length}));'''
    result=subprocess.run([str(node),'--input-type=module','-e',script,str(repository)],capture_output=True,text=True,
        encoding='utf-8',errors='replace',timeout=30)
    return {'exit_code':result.returncode,'result':json.loads(result.stdout) if result.returncode==0 else None,'stderr':result.stderr}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('clangd','code-map','node','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():raise ValueError('Choose a new output')
    args.output.mkdir(parents=True);started=time.perf_counter()
    result={'schema':'reuse-native-frontends-audit/1','input_origin':'authored_generic_source_no_product_or_issue_answers',
        'sqlglot':sql_probe(),'code_map':endpoints_probe(args.code_map,args.node),'file_hash_verification':'not_run_per_user_preference'}
    (args.output/'partial.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    try:result['clangd']=asyncio.run(asyncio.wait_for(clang_probe(args.output/'cpp',args.clangd),timeout=60))
    except Exception as exc:result['clangd']={'error':type(exc).__name__,'message':str(exc)}
    (args.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'sqlglot':result['sqlglot'],'code_map':result['code_map'],
        'clangd':{k:v for k,v in result['clangd'].items() if k not in {'semantic_ast_root','return_mode_hovers'}},
        'seconds':round(time.perf_counter()-started,3)},ensure_ascii=False))


if __name__=='__main__':main()
