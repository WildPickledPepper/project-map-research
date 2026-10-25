"""Score native build facts in a published production index against source audit."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new score output')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    workspace=Workspace(args.trial/'workspace');active=workspace.config['active']
    db=sqlite3.connect((workspace.directory/active['index']).as_uri()+'?mode=ro',uri=True)
    info=json.loads(db.execute('SELECT payload FROM pm_map_info').fetchone()[0]);snapshot=info['snapshot']
    nodes={n['id']:n for (raw,) in db.execute("SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND kind IN ('build_configuration','build_target','build_source','build_artifact')",(snapshot,)) if (n:=json.loads(raw))}
    edges=[json.loads(raw) for (raw,) in db.execute("SELECT payload FROM pm_fact_edges WHERE snapshot=? AND source LIKE 'cmake:%'",(snapshot,))]
    outgoing=defaultdict(list)
    for edge in edges:outgoing[edge['source']].append(edge)
    checks=[]
    def check(name,passed,**detail):checks.append({'id':name,'passed':bool(passed),**detail})
    def only(rows):return rows[0] if len(rows)==1 else None
    # Independent reference; production code never reads product endpoint names.
    reference={'source_commit':'d4e8d1cf9f90208bcbe5371c127088f6fd66c688','project':'server',
        'target':'profiler_server','entry':'server/src/entry/server/bin/main.cpp',
        'artifact':'server/output/win_mingw64/bin/profiler_server.exe',
        'declaration':'server/src/entry/server/bin/CMakeLists.txt','line':13}
    check('pinned_source',info['source_commit']==reference['source_commit'])
    check('published_snapshot',trial['build']['status']=='ready' and snapshot==active['snapshot']==trial['build']['snapshot'])
    check('controlled_build_scope_declared',trial['scope']=='cmake_cpp_control')
    selected=[json.loads(raw) for (raw,) in db.execute("SELECT payload FROM pm_map_files WHERE json_extract(payload,'$.graph_input')=1")]
    languages=Counter(row['language'] for row in selected)
    check('complete_cpp_cmake_control_scope',languages=={'cpp':1323,'cmake':13},languages=dict(languages))
    configurations=[n for n in nodes.values() if n['kind']=='build_configuration']
    check('one_real_native_configuration',len(configurations)==1)
    context=only(configurations)
    check('native_configuration_state',context and context['state']=='configured_not_built')
    check('native_project_source',context and context['project_source']=={'root':'source','path':reference['project']})
    check('release_ninja_native_context',context and context['configuration']=='Release' and context['generator']['name']=='Ninja')
    check('native_component_version',context and context['cmake_version']=='3.31.6' and context['native_codemodel_version']['major']==2)
    targets=[n for n in nodes.values() if n['kind']=='build_target'];target=only([n for n in targets if n['name']==reference['target']])
    check('native_target_count',len(targets)==33)
    check('one_executable_target',len([t for t in targets if t['target_type']=='EXECUTABLE'])==1 and target and target['target_type']=='EXECUTABLE')
    check('declaration_location',target and target['path']==reference['declaration'] and target['line']==reference['line'])
    check('declaration_backtrace',target and any(r.get('command')=='add_executable' and r['path']==reference['declaration'] for r in target['declaration']))
    produced=[e for e in outgoing[target['id']] if e['kind']=='PRODUCES_ARTIFACT'] if target else []
    primaries=[nodes[e['target']] for e in produced if e['artifact_role']=='primary']
    primary=only(primaries)
    check('unique_primary_executable_artifact',primary and primary['location']=={'root':'source','path':reference['artifact']})
    check('auxiliary_not_process_primary',any(e['artifact_role']!='primary' for e in produced) and all(not n['name'].endswith('.pdb') for n in primaries))
    linked=[nodes[e['target']]['name'] for e in outgoing[target['id']] if e['kind']=='LINKS_BUILD_TARGET'] if target else []
    check('linked_libraries_have_native_identity',set(linked)=={'uv_a','sqlite','msinsight'},targets=sorted(linked))
    sources=[nodes[e['target']] for e in outgoing[target['id']] if e['kind']=='COMPILES_SOURCE'] if target else []
    check('native_408_source_membership',len(sources)==408)
    source=only([n for n in sources if n['path']==reference['entry']])
    check('entry_compilation_unit_selected',source and source['selected_source'] and not source['generated'] and source['compile_group']['language']=='CXX')
    definitions={d['define'] for n in sources for d in n['compile_group']['definitions']}
    check('compile_definitions_retained',{'LIBUS_NO_SSL','LIBUS_USE_LIBUV','UWS_NO_ZLIB'}<=definitions and any(d.startswith('DATABASE_VERSION=') for d in definitions))
    entry_edges=[e for e in outgoing[target['id']] if e['kind']=='EXECUTABLE_ENTRY_CANDIDATE'] if target else []
    check('one_entry_candidate',len(entry_edges)==1)
    entry=None
    if len(entry_edges)==1:
        found=db.execute('SELECT payload FROM pm_fact_nodes WHERE snapshot=? AND id=?',(snapshot,entry_edges[0]['target'])).fetchone()
        entry=json.loads(found[0]) if found else None
    check('actual_global_main',entry and entry['path']==reference['entry'] and entry['name']=='main' and entry['definition'])
    check('entry_not_execution_claim',entry_edges and entry_edges[0]['status']=='candidate' and entry_edges[0]['runtime_execution']=='not_observed'
          and entry_edges[0]['condition']=='source_preprocessor_and_link_selection_not_proven')
    check('source_to_declared_entry',source and entry and any(e['kind']=='INCLUDES_SOURCE_DECLARATION' and e['target']==entry['id'] for e in outgoing[source['id']]))
    witnesses=[]
    for label,start,end,kinds in [
        ('target_entry',target,entry,['EXECUTABLE_ENTRY_CANDIDATE']),
        ('input_entry',target,entry,['COMPILES_SOURCE','INCLUDES_SOURCE_DECLARATION']),
        ('configuration_artifact',context,primary,['CONFIGURES_BUILD_TARGET','PRODUCES_ARTIFACT'])]:
        for direction in ('out','in'):
            query=workspace.query('path',start=(start if direction=='out' else end)['id'],
                target=(end if direction=='out' else start)['id'],direction=direction,kinds=kinds,
                depth=4,nodes=2000,edges=10000,seconds=10) if start and end else {}
            evidence={k:query[k] for k in ('found','direction','items','stop_reason') if k in query}
            check('navigation.'+label+'.'+direction,query.get('found') and query.get('stop_reason') is None)
            witnesses.append({'id':label+'.'+direction,**evidence})
    if entry:
        source_query=workspace.query('source',start=entry['id'])
        check('same_version_source_navigation',source_query.get('path')==reference['entry'] and source_query.get('source_commit')==reference['source_commit'])
    check('source_checkout_remains_clean',not workspace.status()['worktree_has_changes'])
    check('no_runtime_evidence_created',workspace.runtime()['total']==0)
    db.close()
    result={'schema':'cmake-production-trial-score/1','source_commit':info['source_commit'],'snapshot':snapshot,
        'build_version':info['graph_version']['build_version'],'scope':trial['scope'],'index_counts':info['counts'],
        'selected_languages':dict(languages),'native_node_counts':dict(Counter(n['kind'] for n in nodes.values())),
        'target_types':dict(Counter(t['target_type'] for t in targets)),
        'selected_target':{k:target[k] for k in ('id','name','path','line','native_id','target_type','configuration','build_context','declaration')} if target else None,
        'primary_artifact':primary,'entry':{k:entry[k] for k in ('id','path','line','name')} if entry else None,
        'selected_target_sources':{'total':len(sources),'selected_source':sum(n['selected_source'] for n in sources),
            'dependency_source':sum(n['dependency_source'] for n in sources)},
        'navigation':witnesses,'checks':checks,'passed':all(r['passed'] for r in checks),
        'runtime_execution':False,'product_compiled':False,'whole_G02_accepted':False,'whole_G03_accepted':False,
        'process_counterpart_status':'pending_packaging_path_and_runtime_program_identity'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':[c['id'] for c in checks if not c['passed']]}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
