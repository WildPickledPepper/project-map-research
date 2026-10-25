"""Publish an immutable extracted graph through the refresher, then reuse P5 runtime records."""
import argparse
from collections import Counter
from copy import deepcopy
import gc
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE.parent/'2026-10-24-p5'))
from adapters.snapshot_refresh import Refresher,read_snapshot
from adapters.snapshot_records import snapshot_basis
from runtime_records import append_runtime,query_runtime,validate_context
from link_runtime import validate_receipt
from verify import read


def publish(source,archive,store):
    request=read(archive/'request.json');result=read(archive/'result.json')
    def reuse(_source,new_request,directory,log):
        for key in ('source_commit','config','build_version','input_paths'):
            if new_request[key]!=request[key]:raise ValueError('Archived extraction differs: '+key)
        # Publication gets its own ID; replace that exact snapshot identity throughout the archive.
        # Facts, input paths and extraction versions remain unchanged. No file hashes are computed.
        value=(archive/'graph.json').read_text(encoding='utf-8')
        value=value.replace(request['snapshot'],new_request['snapshot'])
        (directory/'graph.json').write_text(value,encoding='utf-8')
        log.write('Reuse completed immutable extraction '+request['snapshot']+'; source/config/rules/input paths equal\n')
        return result
    state=Refresher(source,store,lambda:request['config'],lambda:request['build_version'],reuse,
                    revision=request['source_commit']).run(max_builds=1)
    if state['status']!='up_to_date':raise ValueError(state.get('last_error'))
    gc.collect()
    return state['last_success']['id']


def build_receipt(source,results):
    final=read(results/'a5-frontend-build-02/result.json')['source_commit']
    native=subprocess.check_output(['git','-C',str(source),'rev-parse','4df6d68c9'],text=True).strip()
    changed=subprocess.check_output(['git','-C',str(source),'diff','--name-only',native,final,'--','server'],text=True).splitlines()
    if changed:raise ValueError('Backend scope changed after the recorded native build')
    timeline=read(results/'a5-frontend-build-03/result.json')
    if timeline['source_commit']!=final or timeline['modules']['timeline']['exit_code']!=0:raise ValueError('Timeline final build missing')
    modules=read(results/'a5-frontend-build-02/result.json')['modules']
    if not all(v['exit_code']==0 for v in modules.values()):raise ValueError('Incomplete frontend build')
    receipt={'source_commit':final,'components':[
        {'name':'backend','source_commit':native,'log_ref':'a5-backend-build-01.log','source_equivalence':{
            'against_commit':final,'scope':['server'],'changed_paths':changed,'method':'git_diff_name_only'}},
        *[{'name':module,'source_commit':final,'log_ref':'a5-frontend-build-02/'+module+'.log'} for module in modules],
        {'name':'timeline','source_commit':final,'log_ref':'a5-frontend-build-03/timeline.log'}],
        'python_importer':{'source_commit':final,'scope':'scripts/MemSnapDump','python':'3.11.9','packaging':'copied committed scripts; existing Python installation mounted into experimental runtime bin'},
        'native_build':{'database_version':'2026102400','source_date_epoch':'1792773720','target':'profiler_server'},
        'file_hash_verification':'not_run_per_user_preference'}
    verification=deepcopy(receipt)
    verification['evidence_kind']='reconstructed_from_executed_build_logs_and_commits'
    for component in verification['components']:
        component['success_marker']='Linking CXX executable' if component['name']=='backend' else 'Compiled successfully.'
    validate_receipt(source,verification,results)
    return receipt


def rules(events):
    result=[]
    manager='server/src/modules/ProtocolManager.cpp'
    native='server/msinsight/src/base/ModuleRequestHandler.cpp'
    for stage,path in [('request.decoded',manager),('handler.invoke',native),('handler.complete',native)]:
        result.append({'stage':stage,'role':'capture_hook','selector':{'kind':'call_site','path':path,'name':'ProjectMapProbe::Emit'},'first_argument':json.dumps(stage)})
    service='server/src/modules/communication/core/ClusterService.cpp'
    for command,path in [('communication/duration/iterations',service),('communication/matrix/group',service),
        ('Memory/snapshot/blocks','server/src/modules/memsnapshot/handler/QueryMemSnapshotBlockHandler.cpp'),
        ('Memory/leaks/blocks','server/src/modules/memscope/handler/QueryMemScopeBlockHandler.cpp')]:
        for stage in ('database.call','database.return'):
            if path==service:
                member='QueryIterations' if command.endswith('iterations') else 'QueryGroupInfo'
                result.append({'stage':stage,'role':'capture_function','when':{'command':command},
                    'selector':{'kind':'callable','path':path,'name_suffix':'ClusterService::'+member,'definition':True}})
            else:
                result.append({'stage':stage,'role':'capture_hook','when':{'command':command},
                    'selector':{'kind':'call_site','path':path,'name':'ProjectMapProbe::Emit'},'first_argument':json.dumps(stage)})
    methods={'communication/duration/iterations':('IterationsHandler','TextClusterDatabase','QueryIterations'),
        'communication/matrix/group':('Communication::GroupHandler','TextClusterDatabase','GetGroups'),
        'Memory/snapshot/blocks':('QueryMemSnapshotBlockHandler','MemSnapshotDatabase','QueryBlocksByPage'),
        'Memory/leaks/blocks':('QueryMemScopeBlockHandler','MemScopeDatabase','QueryMemoryBlocks')}
    for command,(handler,database,method) in methods.items():
        for stage,typename,member in [('handler.invoke',handler,'HandleRequest'),('database.call',database,method),('database.return',database,method)]:
            when={'command':command}
            if command=='Memory/snapshot/blocks' and stage.startswith('database.'):
                when['is_table']=False;when['page_mode']='paginated'
            result.append({'stage':stage,'role':'observed_dispatch_target','when':when,
                'selector':{'kind':'callable','name_suffix':typename+'::'+member,'definition':True}})
    for stage in ('database.call','database.return'):
        result.append({'stage':stage,'role':'observed_dispatch_target',
            'when':{'command':'Memory/snapshot/blocks','is_table':True},
            'selector':{'kind':'callable','name_suffix':'MemSnapshotDatabase::QueryBlocksTable','definition':True}})
    browser_stages={
        'request.begin':('modules/lib/src/connection/index.ts','fetch'),
        'consumer.iterations':('modules/cluster/src/components/communication/Filter.tsx','getiterationOptions'),
        'consumer.groups':('modules/cluster/src/components/communication/Filter.tsx','getStageOptions'),
        'pagination.page':('modules/leaks/src/components/dataHandler.ts','fetchSnapshotViewBlocksPaginated'),
        'pagination.merged':('modules/leaks/src/components/dataHandler.ts','fetchSnapshotViewBlocksPaginated'),
        'worker.handoff':('modules/leaks/src/components/dataHandler.ts','getBarNewData'),
        'load.adopted':('modules/leaks/src/components/dataHandler.ts','getBarNewData'),
        'cache.result':('modules/leaks/src/components/dataHandler.ts','getBarNewData'),
        'cache.adopted':('modules/leaks/src/components/dataHandler.ts','getBarNewData'),
        'load.error':('modules/leaks/src/components/dataHandler.ts','getBarNewData')}
    for stage,(path,name) in browser_stages.items():
        result.append({'stage':stage,'role':'observed_source','selector':{'kind':'callable','path':path,'name_suffix':name}})
    return result


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    snapshot=publish(a.source,a.archive,a.store)
    basis=snapshot_basis(a.store,snapshot)
    receipt=validate_receipt(a.source,read(a.build_receipt),a.results) if a.build_receipt else build_receipt(a.source,a.results)
    # Resolve suffix selectors once against the same extracted graph; P5's mapper accepts exact selectors.
    graph=read(Path(read_snapshot(a.store,snapshot)['directory'])/'graph.json')
    proposed=rules([]);resolved=[]
    for rule in proposed:
        selector=rule['selector'];suffix=selector.get('name_suffix')
        if suffix:
            base={k:v for k,v in selector.items() if k!='name_suffix'}
            found=[n for n in graph['nodes'] if all(n.get(k)==v for k,v in base.items()) and n.get('name','').endswith(suffix)]
            if len(found)==1:rule={**rule,'selector':{'kind':found[0]['kind'],'id':found[0]['id']}}
            else:rule={**rule,'selector':{**base,'name':'__unresolved_a5_selector__'+suffix}}
        resolved.append(rule)
    graph_info={'nodes':len(graph['nodes']),'edges':len(graph['edges']),'inputs':len(graph['input_paths']),
                'source_commit':graph['source_commit'],'snapshot_id':snapshot,'builder':graph['version']['build_version']}
    print(json.dumps({'graph':graph_info,'unresolved_source_selectors':[r for r in resolved if '__unresolved_a5_selector__' in r['selector'].get('name','')]}),flush=True)
    del graph;gc.collect()
    producer=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    rows=[];compatibility_controls=None
    for item in read(a.results/'a5-final-suite.json')['runs']:
        run=a.results/item['run'];capture=read(run/'verification.json');inputs=read(run/'input.json');result=read(run/'result.json')
        context={'source_commit':inputs['source_commit'],'build':receipt,
            'runtime_config':{k:inputs[k] for k in ('page_size','fault_drop_block','site_headers','ports')}|{'browser':result['browser']},
            'data':{'fixture_kind':inputs['scenario'].split('-')[0],'run_directory':run.name,'oracle':'expected.json'},
            'scenario':{'name':inputs['scenario'],'run_id':run.name,'driver_revision':producer}}
        events=[];links=[]
        for chain in capture['chains']:
            key=chain['connection']+':'+str(chain['request_id'])
            for i,e in enumerate(chain['observations']):
                e={**e,'is_table':chain['params'].get('isTable'),
                    'page_mode':'paginated' if chain['params'].get('pageSize',0)>0 else 'all'}
                event_id=run.name+':'+key+':native:'+str(i)
                events.append({'id':event_id,'stage':e['stage'],'observation':e})
                links.append({'source':key,'target':event_id,'kind':'explicit_request_identity'})
        for frame in read(run/'frames.json'):
            for e in frame.get('probe',[]):
                if e['stage'] in ('connector.response','schedule.call','schedule.resolved'):continue
                events.append({'id':e['event_id'],'stage':e['stage'],'observation':e})
        record=append_runtime(a.store,basis,context,events,links,resolved,
            {'producer':{'name':'a5-runtime','version':producer},'evidence_kind':'executed_real_runtime','source_ref':run.name},
            {'scenario_passed':result['passed'],'capture_complete':capture['capture_complete'],
             'independent_blocks_passed':capture['independent_blocks_passed']},capture['known_gaps'])
        same=query_runtime(a.store,record['id'],snapshot_id=snapshot,context=context)
        assert same['eligible_for_direct_overlay']
        if compatibility_controls is None:
            altered=deepcopy(context);altered['runtime_config']['page_size']+=1
            wrong_config=query_runtime(a.store,record['id'],snapshot_id=snapshot,context=altered)
            assert not wrong_config['eligible_for_direct_overlay']
            altered_source=deepcopy(context);altered_source['source_commit']='ccd0d88080861b0c7185bcca70a85bd61f823168'
            cross_source=query_runtime(a.store,record['id'],snapshot_id=snapshot,context=altered_source)
            assert not cross_source['eligible_for_direct_overlay']
            altered_fault=deepcopy(context);altered_fault['runtime_config']['fault_drop_block']=True
            cross_fault=query_runtime(a.store,record['id'],snapshot_id=snapshot,context=altered_fault)
            assert not cross_fault['eligible_for_direct_overlay']
            try:validate_context(altered_source,basis)
            except ValueError:admission_rejected=True
            else:raise AssertionError('Different runtime source accepted')
            compatibility_controls={'tested_record_id':record['id'],'changed_config_overlay':False,
                'changed_source_overlay':False,'changed_fault_overlay':False,'changed_source_admission_rejected':admission_rejected}
        mappings=record['payload']['mappings']
        row={'run':run.name,'record_id':record['id'],'anchors':dict(Counter(m['status'] for m in mappings)),
             'mapped_stages':sorted({m['rule']['stage'] for m in mappings if m['status']=='mapped'}),
             'mapped_targets':sorted({m['node']['name'] for m in mappings if m.get('role')=='observed_dispatch_target' and m['status']=='mapped'}),
             'same_context_overlay':True,
             'scenario_passed':result['passed'],'unmapped_stages':sorted({e['stage'] for e in events if any(m['event_id']==e['id'] and m['status']=='unmapped' for m in mappings)})}
        rows.append(row)
        (a.output/(item['label']+'-context.json')).write_text(json.dumps(context,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(row),flush=True)
    (a.output/'result.json').write_text(json.dumps({'passed':True,'graph':graph_info,'build_receipt':receipt,
        'compatibility_controls':compatibility_controls,'runs':rows},indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source','archive','store','results','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--build-receipt',type=Path,help='For a fresh reproduction, provide its actual component commits, build logs and success markers instead of the archived local receipt')
    main(p.parse_args())
