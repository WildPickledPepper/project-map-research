"""Independent, post-extraction checks of Insight's shared CLI/WebView value."""
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
    def at(kind,path,line):return [n for n in nodes.values() if n['kind']==kind and n.get('path')==path and n.get('line')==line]
    def slots(template):return [p['slot'] for p in template['parts'] if 'slot' in p]
    def edges(uid,kind):return [e for e in graph['edges'] if e['source']==uid and e['kind']==kind]
    def location(node):return {'path':node['path'],'line':node['line']}
    templates=[n for n in nodes.values() if n['kind']=='boundary_argument_template']
    commands=at('boundary_argument_template','platform/src/default.rs',176)
    urls=at('boundary_argument_template','platform/src/webview.rs',115)
    check('same_pinned_source',trial['source_commit']==graph['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('same_native_input_scope',trial['input_count']==len(graph['input_paths'])==16)
    check('single_native_context',len([n for n in nodes.values() if n['kind']=='analysis_context'])==1)
    check('one_command_and_one_active_url_template',len(commands)==len(urls)==1)
    if len(commands)!=1 or len(urls)!=1:raise ValueError('Independent reference expects one command and one active URL')
    command,url=commands[0],urls[0];context=nodes[command['analysis_context']]
    check('windows_release_default',context['workspace']=='platform/Cargo.toml' and context['target']=='x86_64-pc-windows-msvc' and
        context['debug_assertions'] is False and context['features']==['MindStudioInsight/default'])
    check('same_analysis_context',command['analysis_context']==url['analysis_context'])
    check('source_templates_complete',command['complete'] and url['complete'] and not command['gaps'] and not url['gaps'])
    check('command_word_prefix_from_source',command['parts'][0]=={'literal':'--wsPort='} and command['role']=='process_argument')
    check('url_prefix_from_source',url['parts'][0]=={'literal':'wry://localhost/resources/profiler/frontend/index.html?port='} and url['role']=='frontend_loader')
    check('one_slot_each',len(slots(command))==len(slots(url))==1)
    check('shared_contextual_value_identity',slots(command)==slots(url))
    scalar=nodes[slots(command)[0]];binding=nodes[scalar['source']]
    check('pattern_value_without_guessed_port',scalar['value']['kind']=='binding_projection' and 'literal' not in scalar and 'gap' not in scalar['value'])
    check('root_some_binding',binding['kind']=='binding' and binding['name']=='port' and binding['path']=='platform/src/default.rs' and binding['line']==393)
    origin=edges(binding['id'],'PATTERN_VALUE_SOURCE');check('pattern_has_one_origin',len(origin)==1)
    chooser=nodes[origin[0]['target']] if len(origin)==1 else {}
    check('source_selector_call',chooser.get('kind')=='call_site' and chooser.get('path')=='platform/src/default.rs' and
        chooser.get('line')==393 and chooser.get('name')=='find_first_available_port')
    root=nodes[command['root_function']]
    check('both_call_frames_rooted_at_rust_main',root['name']=='main' and root['path']=='platform/src/main.rs' and url['root_function']==root['id'])
    check('distinct_call_routes_to_consumers',len(command['call_stack'])==2 and len(url['call_stack'])==3 and command['call_stack']!=url['call_stack'])
    check('value_scope_stops_at_shared_caller',scalar['value']['scope']=={'root_function':root['id'],'calls':command['call_stack'][:1]})
    check('one_scalar_origin_edge',[e['target'] for e in edges(scalar['id'],'SCALAR_VALUE_SOURCE')]==[binding['id']])
    for label,template,family in [('command',command,'process_start'),('url',url,'frontend_loader')]:
        check(label+'_correct_boundary',nodes[template['consumer']]['family']==family)
        guards={c['kind'] for c in template['conditions']}
        for guard in ('rust_pattern_projection_selected','boundary_operation_reached_with_recorded_call_and_capture_context',
            'no_unmodeled_operand_mutation_before_evaluation','no_unmodeled_command_builder_mutation_before_start'):
            check(label+'_condition_'+guard,guard in guards)
    check('closure_capture_contexts_remain_conditional',any('closure_invoked_with_recorded_capture_environment' in
        {c['kind'] for c in t['conditions']} for t in templates))
    log=at('boundary_argument_template','platform/src/default.rs',177)
    check('log_path_unsupported_expression_retained',len(log)==1 and not log[0]['complete'] and log[0]['gaps'])
    strict=at('boundary_argument_template','platform/src/default.rs',178)
    check('literal_flag_is_its_own_word',len(strict)==1 and strict[0]['complete'] and strict[0]['parts']==[{'literal':'--notStrict'}])
    check('all_new_nodes_static',all(n['runtime_execution']=='not_observed' for n in nodes.values() if n['kind'] in {'source_scalar_value','boundary_argument_template'}))
    workspace=Workspace(args.trial/'workspace');navigation=[]
    routes=[('command_value',command['consumer'],scalar['id'],['BOUNDARY_ARGUMENT_TEMPLATE','TEMPLATE_VALUE_SLOT']),
        ('url_value',url['consumer'],scalar['id'],['BOUNDARY_ARGUMENT_TEMPLATE','TEMPLATE_VALUE_SLOT']),
        ('value_selector',scalar['id'],chooser['id'],['SCALAR_VALUE_SOURCE','PATTERN_VALUE_SOURCE'])]
    for name,left,right,kinds in routes:
        for direction,start,end in [('out',left,right),('in',right,left)]:
            result=workspace.query('path',start=start,target=end,direction=direction,kinds=kinds,depth=4,nodes=60,edges=100,output_bytes=524288)
            row={'id':name+'_'+direction,'found':result['found'],'stop_reason':result.get('stop_reason'),
                'snapshot_matches':result['snapshot']==graph['snapshot'],'witness_edges':len(result['items'])}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
    for name,node in [('command',command),('url',url),('shared_binding',binding)]:
        proof=workspace.query('source',start=node['id'])
        check('versioned_source_'+name,proof['source_commit']==trial['source_commit'] and proof['path']==node['path'] and not proof['working_tree_read'])
    check('current_templates_cached_native_facts',trial['argument_projection_executed_again'] and not trial['native_semantic_stage_executed_again'])
    check('no_runtime_or_whole_chain_claim',not any(trial[k] for k in ('default_workspace_rebuild','installed_tool_tested','runtime_execution',
        'cpp_argument_decode_connected','backend_listener_connected','whole_G03_accepted','original_checkout_modified')))
    check('no_hash_verification',trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':'rust-argument-control-score/1','passed':all(c['passed'] for c in checks),'checks':checks,
        'selected_chain':{'command':location(command),'url':location(url),'shared_binding':location(binding),'selector':location(chooser),
            'value_kind':scalar['value']['kind'],'command_prefix':command['parts'][0]['literal'],'url_prefix':url['parts'][0]['literal']},
        'required_template_gap_counts':{reason:sum(reason in t['gaps'] for t in templates) for reason in sorted({r for t in templates for r in t['gaps']})},
        'navigation':navigation}
    args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':score['passed'],'checks':len(checks),'navigation':navigation,'template_summary':trial['template_summary']}))
    if not score['passed']:raise SystemExit('Rust argument source control failed; inspect the saved score')


if __name__=='__main__':main()
