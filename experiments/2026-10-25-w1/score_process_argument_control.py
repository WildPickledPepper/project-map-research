"""Post-extraction checks of Insight's deployed command words to C++ argv decode."""
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
    matches=[n for n in nodes.values() if n['kind']=='process_argument_binding']
    check('same_pinned_source',trial['source_commit']==graph['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('startup_input_scope',trial['input_count']==1471 and trial['cached_argument_input_counts']=={'rust_arguments':16,'cpp_argv':1323})
    check('two_sourced_word_candidates',{m['name'] for m in matches}=={'--wsPort=','--logPath='} and len(matches)==2)
    if len(matches)!=2:raise ValueError('Reference expects two word-to-decoder candidates')
    port=next(m for m in matches if m['name']=='--wsPort=');log=next(m for m in matches if m['name']=='--logPath=')
    template=nodes[port['template']];binding=nodes[port['argv_binding']];decoder=nodes[port['decoder']]
    target=nodes[decoder['targets'][0]];provider=nodes[port['provider']];path=nodes[port['deployment_path']]
    raw=nodes[path['source_path_value']];argv_entry=nodes[binding['entry']]
    check('provider_native_target',provider['name']=='profiler_server' and provider['target_type']=='EXECUTABLE')
    check('full_deployed_backend_path',path['location']=={'root':'source','path':'platform/preview/resources/profiler/server/profiler_server.exe'})
    check('source_template_location',template['path']=='platform/src/default.rs' and template['line']==176 and port['literal_prefix']=='--wsPort=')
    check('source_command_and_context',port['command']==path['consumer'] and port['analysis_context']==template['analysis_context']==path['analysis_context'])
    check('same_rust_call_context',raw['root_function']==template['root_function'] and raw['call_stack']==template['call_stack'])
    check('source_decoder_location',decoder['path']=='server/msinsight/src/base/ParamsParser.cpp' and decoder['line']==38 and decoder['key']=='--wsPort=')
    check('argv_entry_matches_native_provider',argv_entry['path']=='server/src/entry/server/bin/main.cpp' and
        any(e['source']==provider['id'] and e['target']==argv_entry['id'] and e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' for e in graph['edges']))
    check('argv_origin_stays_complete',binding['origin_complete'] and not binding['value']['gaps'])
    check('parse_value_target',target['name']=='Dic::Server::ParamsParser::ParseWsPort' and target['path']==decoder['path'])
    check('native_file_scope',{*port['source_scope']}=={'server/src/entry/server/bin/main.cpp','server/msinsight/src/base/ParamsParser.cpp'})
    check('native_context_carried',port['provider_context']==provider['build_context'])
    check('port_payload_source_complete',port['payload_source_complete'] and not port['payload_source_gaps'])
    check('log_payload_unknown_preserved',not log['payload_source_complete'] and log['payload_source_gaps'])
    check('static_word_contribution_not_payload_equality',all(m['runtime_execution']=='not_observed' and m['payload_equivalence']=='not_established' and
        m['prepared_value_relation']=='argument_word_may_contribute_to_decoded_input' and m['match_status']=='single_conditional_decoder' for m in matches))
    conditions={c['kind'] for c in port['conditions']}
    for condition in ('running_process_image_matches_deployment','deployment_artifact_lineage_matches_recorded_producer',
        'target_os_loader_accepts_provider_image','selected_cpp_argv_occurrence_supplied_by_command_template','os_argv_encoding_preserves_sourced_literal_key',
        'configured_cpp_preprocessor_and_source_type_context_applies','recorded_native_link_dependencies_supply_decoder_code','decoder_branch_reached_for_selected_prepared_word'):
        check('condition_'+condition,condition in conditions)
    slots=[p['slot'] for p in template['parts'] if 'slot' in p]
    scalar=nodes[slots[0]];source=nodes[scalar['source']]
    check('port_scalar_stays_symbolic',len(slots)==1 and scalar['value']['kind']=='binding_projection' and 'literal' not in scalar and
        source['path']=='platform/src/default.rs' and source['line']==393)
    gaps=[d for d in graph['diagnostics'] if d['kind']=='process_argument_binding_unresolved' and d['required']]
    check('two_known_required_gaps',len(gaps)==2 and {d['reason'] for d in gaps}=={'argument_payload_source_unresolved','no_decoder_for_sourced_word_in_bound_program'})
    missing=next(d for d in gaps if d['reason']=='no_decoder_for_sourced_word_in_bound_program')
    check('literal_switch_missing_decoder_recorded',missing['literal_prefix']=='--notStrict' and missing['path']=='platform/src/default.rs' and missing['line']==178)
    workspace=Workspace(args.trial/'workspace');navigation=[]
    kinds=['BOUNDARY_ARGUMENT_TEMPLATE','BIND_PROCESS_ARGUMENT','MATCHES_ARGV_DECODER_CANDIDATE','BINDS_ARGV_DECODER_CANDIDATE','DECODED_VALUE_TARGET_CANDIDATE']
    for label,left,right,relations in [('template_parse',template['id'],target['id'],kinds),('spawn_parse',template['consumer'],target['id'],kinds),
        ('binding_native_target',port['id'],provider['id'],['ARGUMENT_PROVIDER_TARGET'])]:
        for direction,start,end in [('out',left,right),('in',right,left)]:
            proof=workspace.query('path',start=start,target=end,direction=direction,kinds=relations,depth=8,nodes=120,edges=200,output_bytes=1048576)
            row={'id':label+'_'+direction,'found':proof['found'],'stop_reason':proof.get('stop_reason'),
                'snapshot_matches':proof['snapshot']==graph['snapshot'],'witness_edges':len(proof['items'])}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    for label,node in [('template',template),('binding',port),('target',target)]:
        proof=workspace.query('source',start=node['id'])
        check('versioned_source_'+label,proof['source_commit']==trial['source_commit'] and proof['path']==node['path'] and not proof['working_tree_read'])
    proof=workspace.query('path',start=template['id'],target=target['id'],kinds=kinds,depth=8)
    default_navigation={'found':proof['found'],'stop_reason':proof.get('stop_reason'),'witness_edges':len(proof['items']),
        'output_bytes':len(json.dumps(proof,ensure_ascii=False).encode('utf-8')),'snapshot_matches':proof['snapshot']==graph['snapshot']}
    check('selected_path_with_default_query_budget',default_navigation['found'] and default_navigation['stop_reason'] is None and
        default_navigation['witness_edges']==4 and default_navigation['snapshot_matches'] and default_navigation['output_bytes']<=131072)
    check('current_projection_cached_native_facts',trial['current_argument_binding_executed_again'] and not trial['language_semantics_executed_again'])
    check('no_runtime_or_whole_gate_claim',not any(trial[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild','installed_tool_tested',
        'product_compiled','runtime_execution','payload_value_equivalence_established','backend_listener_connected','whole_G03_accepted','original_checkout_modified')))
    check('no_hash_verification',trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':'process-argument-control-score/1','passed':all(c['passed'] for c in checks),'checks':checks,
        'selected_chain':{'template':{'path':template['path'],'line':template['line']},'decoder':{'path':decoder['path'],'line':decoder['line']},
            'target':target['name'],'provider':provider['name'],'backend_path':path['location']['path'],'source_scope':port['source_scope'],
            'word_relation':port['prepared_value_relation'],'payload_equivalence':port['payload_equivalence']},
        'required_binding_gaps':[{k:v for k,v in gap.items() if k not in {'source','argv_binding'}} for gap in gaps],'navigation':navigation,
        'default_navigation':default_navigation}
    args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':score['passed'],'checks':len(checks),'matches':len(matches),'required_binding_gaps':score['required_binding_gaps'],'navigation':navigation}))
    if not score['passed']:raise SystemExit('Process argument control failed; inspect saved score')


if __name__=='__main__':main()
