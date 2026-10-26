"""Post-extraction source and navigation checks for Insight's literal switch."""
import argparse
from collections import Counter
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
    process=trial['schema']=='process-literal-switch-control/1'
    def check(name,value):checks.append({'id':name,'passed':bool(value)})
    check('same_pinned_source',trial['source_commit']==graph['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('expected_input_scope',trial['input_count']==(1471 if process else 1323))
    matches=[n for n in nodes.values() if n['kind']=='string_key_decoder' and n['key']=='--notStrict' and
        n['path']=='server/msinsight/src/base/ParamsParser.cpp']
    check('one_source_literal_switch',len(matches)==1)
    if len(matches)!=1:raise ValueError('Independent source reference expects one literal switch')
    switch=matches[0];check('equality_operator_and_branch',switch['match_mode']=='string_equality' and switch['comparison_operator']=='==' and switch['equality_branch']=='consequence')
    check('source_comparison_location',switch['line']==66 and nodes[switch['source_symbol']]['name']=='Dic::Server::ParamsParser::ParseField')
    check('no_invented_decoded_value_target',switch['targets']==[])
    check('one_controlled_assignment',len(switch['controlled_member_effects'])==1)
    write=nodes[switch['controlled_member_effects'][0]];member=nodes[write['member']]
    check('write_is_false_assignment',write['role']=='write' and write['operation']=='=' and write['value']['expression']=='false')
    check('write_source_location',write['path']==switch['path'] and write['line']==67 and write['source_symbol']==switch['source_symbol'])
    check('member_declaration_identity',member['owner']=='Dic::Server::ParamsOption' and member['name']=='Dic::Server::ParamsOption::strictMode' and member['type']=='bool')
    check('member_source_location',member['path']=='server/msinsight/src/base/ParamsParser.h' and member['line']==41)
    check('object_instance_remains_unselected',write['instance_identity']=='unresolved' and not trial['member_effect_summary']['object_instances_selected'])
    check('comparison_condition_preserved',any(c.get('kind')=='branch' and 'symbolNotStrict' in c.get('expression','') and c['when'] for c in write['conditions']))
    bindings=[n for n in nodes.values() if n['kind']=='cpp_argv_decoder_binding' and n['decoder']==switch['id']]
    check('one_entry_argument_binding',len(bindings)==1)
    if len(bindings)!=1:raise ValueError('Independent entry reference expects one argv binding')
    binding=bindings[0];entry=nodes[binding['entry']]
    check('cpp_main_identity',entry['name']=='main' and entry['path']=='server/src/entry/server/bin/main.cpp')
    check('argv_origin_complete',binding['origin_complete'] and binding['value']['origins'] and not binding['value']['gaps'])
    check('same_entry_for_all_origins',all(o['entry']==entry['id'] for o in binding['value']['origins']))
    check('two_source_call_frames',len(binding['call_stack'])==2)
    preparation=[s for s in binding['value']['steps'] if s['kind']=='standard_string_append']
    check('conditional_preparation_preserved',len(preparation)==2 and all(any(c['kind']=='branch' for c in s['conditions']) for s in preparation))
    check('source_member_effect_count_matches',sum(n['kind']=='source_member_effect' for n in nodes.values())==trial['member_effect_summary']['effects'])
    cases=[('entry_member',entry['id'],member['id'],['CPP_ENTRY_ARGV','ARGV_FLOW_CANDIDATE','BINDS_ARGV_DECODER_CANDIDATE',
        'STRING_BRANCH_MEMBER_WRITE_CANDIDATE','WRITES_SOURCE_MEMBER_CANDIDATE']),
        ('decoder_member',switch['id'],member['id'],['STRING_BRANCH_MEMBER_WRITE_CANDIDATE','WRITES_SOURCE_MEMBER_CANDIDATE'])]
    gaps=[d for d in graph['diagnostics'] if d['kind']=='cpp_string_switch_unresolved' and d['required']]
    type_gaps=[d for d in graph['diagnostics'] if d['kind']=='cpp_value_type_unresolved' and d['required']]
    check('bounded_type_gaps_keep_source_locations',all(d.get('path') and d.get('line') and d.get('reason') for d in type_gaps))
    if process:
        paired=[n for n in nodes.values() if n['kind']=='process_argument_binding'];check('three_sourced_words_paired',len(paired)==3 and
            {n['name'] for n in paired}=={'--wsPort=','--logPath=','--notStrict'})
        pair=next(n for n in paired if n['name']=='--notStrict');template=nodes[pair['template']];provider=nodes[pair['provider']]
        check('literal_switch_template_location',template['path']=='platform/src/default.rs' and template['line']==178)
        check('whole_word_matching',pair['word_match_basis']=='full_source_word' and pair['literal_prefix']=='--notStrict' and pair['payload_source_complete'])
        check('same_cpp_switch_and_argv',pair['decoder']==switch['id'] and pair['argv_binding']==binding['id'])
        check('selected_native_provider',provider['name']=='profiler_server' and provider['target_type']=='EXECUTABLE')
        check('prepared_value_equality_not_assumed',pair['payload_equivalence']=='not_established' and
            any(c.get('kind')=='prepared_input_equals_literal_switch_key' for c in pair['conditions']))
        argument_gaps=[d for d in graph['diagnostics'] if d['kind']=='process_argument_binding_unresolved' and d['required']]
        check('only_log_payload_gap_remains_in_word_pairing',len(argument_gaps)==1 and argument_gaps[0]['reason']=='argument_payload_source_unresolved' and argument_gaps[0]['line']==177)
        kinds=['BOUNDARY_ARGUMENT_TEMPLATE','BIND_PROCESS_ARGUMENT','MATCHES_ARGV_DECODER_CANDIDATE','BINDS_ARGV_DECODER_CANDIDATE',
            'STRING_BRANCH_MEMBER_WRITE_CANDIDATE','WRITES_SOURCE_MEMBER_CANDIDATE']
        cases.extend([('template_member',template['id'],member['id'],kinds),('spawn_member',template['consumer'],member['id'],kinds)])
    workspace=Workspace(args.trial/'workspace');navigation=[]
    for label,left,right,kinds in cases:
        for direction,start,end in [('out',left,right),('in',right,left)]:
            proof=workspace.query('path',start=start,target=end,direction=direction,kinds=kinds,depth=10,nodes=150,edges=220,output_bytes=1048576)
            row={'id':label+'_'+direction,'found':proof['found'],'stop_reason':proof.get('stop_reason'),
                'snapshot_matches':proof['snapshot']==graph['snapshot'],'witness_edges':len(proof['items'])}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    for label,node in [('switch',switch),('write',write),('member',member)]:
        proof=workspace.query('source',start=node['id'])
        check('versioned_source_'+label,proof['path']==node['path'] and proof['source_commit']==trial['source_commit'] and not proof['working_tree_read'])
    check('no_runtime_listener_or_whole_gate_claim',not any(trial[k] for k in ('runtime_execution','backend_listener_connected','whole_G03_accepted','original_checkout_modified')))
    check('no_file_hash_verification',trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':('process' if process else 'cpp')+'-literal-switch-control-score/1','passed':all(c['passed'] for c in checks),'checks':checks,
        'selected_switch':{'key':switch['key'],'path':switch['path'],'line':switch['line'],'write_line':write['line'],
            'member_path':member['path'],'member_line':member['line'],'member_name':member['name']},
        'required_switch_gap_counts':{reason:sum(d['reason']==reason for d in gaps) for reason in sorted({d['reason'] for d in gaps})},
        'required_value_type_gap_counts':{reason:sum(d['reason']==reason for d in type_gaps) for reason in sorted({d['reason'] for d in type_gaps})},
        'required_gap_counts_by_kind':{kind:dict(Counter(d.get('reason','unclassified') for d in graph['diagnostics']
            if d.get('required') and d['kind']==kind)) for kind in sorted({d['kind'] for d in graph['diagnostics'] if d.get('required')})},
        'argv_summary':graph['cpp_argv_origins'],'navigation':navigation}
    args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':score['passed'],'checks':len(checks),'navigation':navigation,'switch_gaps':score['required_switch_gap_counts']}))
    if not score['passed']:raise SystemExit('Literal-switch source control failed; inspect saved score')


if __name__=='__main__':main()
