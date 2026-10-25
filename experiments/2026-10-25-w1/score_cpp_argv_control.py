"""Independent checks of Insight's main/argv/preparation/decoder source paths."""
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
    path='server/msinsight/src/base/ParamsParser.cpp'
    expected={'--wsPort=','--wsHost=','--logPath=','--logLevel=','--logSize=','--eventDir=','--scanPort='}
    decoders=[n for n in nodes.values() if n['kind']=='string_key_decoder' and n['path']==path]
    bindings=[n for n in nodes.values() if n['kind']=='cpp_argv_decoder_binding' and n['path']==path]
    check('same_pinned_source',trial['source_commit']==graph['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('all_cpp_inputs',trial['input_count']==len(graph['input_paths'])==1323)
    check('seven_decoders_and_seven_bindings',len(decoders)==len(bindings)==7 and {n['key'] for n in decoders}==expected)
    if len(bindings)!=7:raise ValueError('Reference expects seven argv decoder bindings')
    check('all_seven_origins_complete',all(b['origin_complete'] and not b['value']['gaps'] for b in bindings))
    check('one_shared_argv_source',len({b['argv_source'] for b in bindings})==1)
    argv=nodes[bindings[0]['argv_source']];entry=nodes[argv['entry']]
    check('backend_entry_path',entry['name']=='main' and entry['path']=='server/src/entry/server/bin/main.cpp')
    check('narrow_main_argv_parameter',argv['parameter_index']==1 and 'char' in argv['declared_type'])
    check('argv_entry_not_runtime_identity',argv['runtime_execution']=='not_observed' and argv['entry_status']=='source_main_candidate_requires_build_target_binding')
    selected=[]
    for binding in bindings:
        decoder=nodes[binding['decoder']];origins=binding['value']['origins'];steps=binding['value']['steps']
        check(decoder['key']+'_two_source_calls',len(binding['call_stack'])==2)
        check(decoder['key']+'_same_entry_origin',binding['entry']==entry['id'] and origins and all(o['entry']==entry['id'] for o in origins))
        kinds={s['kind'] for s in steps}
        check(decoder['key']+'_preparation_and_formal_sources',{'argv_index','standard_string_from_argv_word','standard_vector_append_word',
            'formal_argument_source','collection_at','standard_string_append','local_initializer_or_reaching_assignment'}<=kinds)
        appends=[s for s in steps if s['kind']=='standard_string_append']
        check(decoder['key']+'_conditional_append_operands',len(appends)==2 and appends[0]['operand'].get('literal')=='=' and
            appends[1]['operand']['origins'] and all(s['preserves_existing_prefix'] and any(c['kind']=='branch' for c in s['conditions']) for s in appends))
        check(decoder['key']+'_runtime_indices_not_invented',all(len(o['selectors'])==2 and all(s['conditions'] for s in o['selectors']) for o in origins))
        check(decoder['key']+'_source_candidate_conditions',binding['runtime_execution']=='not_observed' and
            {'recorded_source_calls_and_loop_iterations_reached','selected_argv_and_collection_elements_exist',
             'no_unmodeled_alias_effects_before_argument_consumption','entry_and_preparation_belong_to_selected_link_image'}<=
            {c['kind'] for c in binding['conditions']})
        selected.append({'key':decoder['key'],'entry':{'path':entry['path'],'name':entry['name']},'decoder':{'path':decoder['path'],'line':decoder['line']},
            'call_count':len(binding['call_stack']),'origin_complete':binding['origin_complete'],'origin_count':len(origins),
            'conditional_append_count':len(appends),'step_kinds':sorted(kinds)})
    workspace=Workspace(args.trial/'workspace');navigation=[]
    binding=next(b for b in bindings if nodes[b['decoder']]['key']=='--wsPort=');decoder=nodes[binding['decoder']]
    target=nodes[decoder['targets'][0]]
    kinds=['CPP_ENTRY_ARGV','ARGV_FLOW_CANDIDATE','BINDS_ARGV_DECODER_CANDIDATE','DECODED_VALUE_TARGET_CANDIDATE']
    for label,left,right in [('entry_decoder',entry['id'],decoder['id']),('entry_parse_value',entry['id'],target['id'])]:
        for direction,start,end in [('out',left,right),('in',right,left)]:
            proof=workspace.query('path',start=start,target=end,direction=direction,kinds=kinds,depth=5,nodes=100,edges=150,output_bytes=524288)
            row={'id':label+'_'+direction,'found':proof['found'],'stop_reason':proof.get('stop_reason'),
                'snapshot_matches':proof['snapshot']==graph['snapshot'],'witness_edges':len(proof['items'])}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    for label,node in [('entry',entry),('argv',argv),('binding',binding),('target',target)]:
        proof=workspace.query('source',start=node['id'])
        check('versioned_source_'+label,proof['source_commit']==trial['source_commit'] and proof['path']==node['path'] and not proof['working_tree_read'])
    check('no_required_argv_gaps',trial['argv_summary']['required_gaps']==0)
    check('one_prior_string_length_gap_retained',trial['decoder_summary']['required_gaps']==1)
    check('argv_source_connected',trial['argv_origin_connected'])
    check('no_runtime_or_rust_value_equality_claim',not any(trial[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild',
        'installed_tool_tested','runtime_execution','rust_argument_paired','backend_listener_connected','whole_G03_accepted','original_checkout_modified')))
    check('source_extraction_and_no_hash_verification',trial['cpp_source_extraction_executed_again'] and trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':'cpp-argv-origin-control-score/1','passed':all(c['passed'] for c in checks),'checks':checks,
        'selected_bindings':selected,'navigation':navigation,
        'required_origin_gaps':[d for d in graph['diagnostics'] if d['kind']=='cpp_argv_origin_unresolved' and d['required']]}
    args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':score['passed'],'checks':len(checks),'bindings':len(selected),'navigation':navigation}))
    if not score['passed']:raise SystemExit('Cpp argv source control failed; inspect saved score')


if __name__=='__main__':main()
