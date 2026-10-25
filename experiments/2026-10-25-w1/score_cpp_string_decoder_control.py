"""Post-extraction reference checks for Insight's CLI field decoding operations."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from projectmap.workspace import Workspace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trial',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.exists():ap.error('Choose a new score file')
    trial=json.loads((args.trial/'trial.json').read_text(encoding='utf-8'))
    graph=json.loads((args.trial/'graph.json').read_text(encoding='utf-8'));nodes={n['id']:n for n in graph['nodes']};checks=[]
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    path='server/msinsight/src/base/ParamsParser.cpp';owner='Dic::Server::ParamsParser::'
    expected={'--wsPort=':('ParseWsPort',38),'--wsHost=':('ParseWsHost',42),'--logPath=':('ParseLogPath',46),
        '--logLevel=':('ParseLogLevel',50),'--logSize=':('ParseLogSize',54),'--eventDir=':('ParseEventDir',59),'--scanPort=':('ParseScan',63)}
    records=[n for n in nodes.values() if n['kind']=='string_key_decoder' and n['path']==path]
    check('same_pinned_source',trial['source_commit']==graph['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('same_cpp_selected_input_count',len(graph['input_paths'])==trial['input_count'])
    check('no_named_input_list',len(graph['input_paths'])>1000 and all(p.endswith(('.cpp','.cc','.cxx','.h','.hpp')) for p in graph['input_paths']))
    check('seven_reference_keys',len(records)==len(expected) and {r['key'] for r in records}==set(expected))
    if len(records)!=len(expected):raise ValueError('Reference requires seven CLI decoding records')
    workspace=Workspace(args.trial/'workspace');navigation=[];selected=[]
    for row in records:
        name,line=expected[row['key']];targets=[nodes[t] for t in row['targets']]
        check(row['key']+'_source_owner_and_slice',nodes[row['source_symbol']]['name']==owner+'ParseField' and row['line']==line)
        check(row['key']+'_one_typed_target',len(targets)==1 and targets[0]['name']==owner+name and targets[0]['path']==path)
        check(row['key']+'_first_parameter',row['parameter_index']==0)
        check(row['key']+'_conditional_source_decode',row['status']=='source_candidate' and row['argv_origin']=='not_bound' and
            row['match_mode']=='substring_search' and row['slice_mode']=='find_result_plus_key_length' and row['runtime_execution']=='not_observed')
        selected.append({'key':row['key'],'path':row['path'],'line':row['line'],'target':name,'parameter_index':row['parameter_index']})
        if row['key']!='--wsPort=':continue
        for direction,start,end in [('out',row['id'],targets[0]['id']),('in',targets[0]['id'],row['id'])]:
            result=workspace.query('path',start=start,target=end,direction=direction,kinds=['DECODED_VALUE_TARGET_CANDIDATE'],depth=2,nodes=30,edges=30)
            proof={'id':'decoder_target_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),
                'snapshot_matches':result['snapshot']==graph['snapshot'],'witness_edges':len(result['items'])}
            navigation.append(proof);check('navigation_'+proof['id'],proof['found'] and proof['stop_reason'] is None and proof['snapshot_matches'])
        for label,node in [('decoder',row),('target',targets[0])]:
            proof=workspace.query('source',start=node['id'])
            check('versioned_source_'+label,proof['source_commit']==trial['source_commit'] and proof['path']==path and not proof['working_tree_read'])
    check('all_new_decoders_static',all(n['runtime_execution']=='not_observed' and n['argv_origin']=='not_bound' for n in nodes.values() if n['kind']=='string_key_decoder'))
    check('no_full_chain_or_runtime_claim',not any(trial[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested',
        'runtime_execution','argv_origin_connected','rust_argument_paired','backend_listener_connected','whole_G03_accepted','original_checkout_modified')))
    check('current_extraction_and_no_hash_verification',trial['cpp_source_extraction_executed_again'] and trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':'cpp-string-decoder-control-score/1','passed':all(c['passed'] for c in checks),'checks':checks,
        'selected_decoders':selected,'navigation':navigation,
        'required_decoder_gaps':[d for d in graph['diagnostics'] if d['kind']=='cpp_string_decoder_unresolved' and d['required']]}
    args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':score['passed'],'checks':len(checks),'selected_decoders':len(selected),'navigation':navigation}))
    if not score['passed']:raise SystemExit('C++ string decoder control failed; inspect saved score')


if __name__=='__main__':main()
