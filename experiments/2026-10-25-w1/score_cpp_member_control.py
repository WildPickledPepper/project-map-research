"""Post-extraction checks of Insight conditional member declarations and navigation."""
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
    check('same_pinned_source',trial['source_commit']==graph['source_commit']=='d4e8d1cf9f90208bcbe5371c127088f6fd66c688')
    check('all_cpp_inputs',len(graph['input_paths'])==trial['input_count']==1323)
    members=[n for n in nodes.values() if n['kind']=='source_member_storage']
    declarations=[n for n in nodes.values() if n['kind']=='cpp_member_declaration']
    check('member_summary_matches_nodes',len(members)==trial['member_summary']['members'] and len(declarations)==trial['member_summary']['declarations'])
    selected=[m for m in members if m['owner']=='Dic::Server::ParamsOption' and m['name']=='Dic::Server::ParamsOption::logPath']
    check('one_conditional_log_path_member',len(selected)==1)
    if len(selected)!=1:raise ValueError('Independent reference expects one logical logPath member')
    member=selected[0];variants=member['declarations'];path='server/msinsight/src/base/ParamsParser.h'
    check('member_declared_in_expected_header',member['path']==path)
    check('two_source_variants',len(variants)==2)
    check('same_declared_source_type',member['type']=='string' and member['type_status']=='same_source_type_across_declarations')
    check('opposite_win32_guards',[[(g['expression'],g['when']) for g in d['conditions']] for d in variants]==
        [[('defined(_WIN32)',True)],[('defined(_WIN32)',False)]])
    check('both_initializer_expressions_preserved',[d['default_expression'] for d in variants]==['""','"./"'])
    check('type_does_not_select_an_initializer',trial['member_summary']['configuration_selection']=='not_performed')
    check('owner_is_an_extracted_cpp_type',nodes[member['class_source']]['kind']=='type' and nodes[member['class_source']]['name']=='Dic::Server::ParamsOption')
    check('member_instance_not_invented',member['instance_identity']=='class_member_instance_unresolved')
    emitted=[nodes[e['target']] for e in graph['edges'] if e['source']==member['id'] and e['kind']=='HAS_MEMBER_DECLARATION']
    check('both_declarations_have_graph_nodes',len(emitted)==2 and {n['default_expression'] for n in emitted}=={'""','"./"'})
    check('all_member_class_links_exist',all(m['class_source'] in nodes for m in members))
    check('full_declaration_count_preserved',sum(len(m['declarations']) for m in members)==len(declarations))
    workspace=Workspace(args.trial/'workspace');navigation=[]
    for index,declaration in enumerate(emitted):
        for direction,start,end in [('out',member['class_source'],declaration['id']),('in',declaration['id'],member['class_source'])]:
            proof=workspace.query('path',start=start,target=end,direction=direction,kinds=['DECLARES_SOURCE_MEMBER','HAS_MEMBER_DECLARATION'],
                depth=3,nodes=100,edges=120)
            row={'id':'owner_variant_'+str(index)+'_'+direction,'found':proof['found'],'stop_reason':proof.get('stop_reason'),
                'witness_edges':len(proof['items']),'snapshot_matches':proof['snapshot']==graph['snapshot']}
            navigation.append(row);check('navigation_'+row['id'],row['found'] and row['stop_reason'] is None and row['snapshot_matches'])
        proof=workspace.query('source',start=declaration['id'])
        check('versioned_source_variant_'+str(index),proof['source_commit']==trial['source_commit'] and proof['path']==path and not proof['working_tree_read'])
    required=[d for d in graph['diagnostics'] if d['kind']=='cpp_member_declaration_unresolved' and d['required']]
    check('unsupported_member_shapes_remain_visible',all(d.get('path') and d.get('reason') for d in required))
    check('no_native_configuration_runtime_or_whole_gate_claim',not any(trial[k] for k in ('cmake_configure_executed_again','default_workspace_rebuild',
        'installed_tool_tested','runtime_execution','argv_origin_connected','rust_argument_paired','backend_listener_connected','whole_G03_accepted','original_checkout_modified')))
    check('source_extraction_no_hash_verification',trial['cpp_source_extraction_executed_again'] and trial['file_hash_verification']=='not_run_per_user_preference')
    score={**trial,'schema':'cpp-member-declaration-control-score/1','passed':all(c['passed'] for c in checks),'checks':checks,
        'selected_member':{'owner':'Dic::Server::ParamsOption','name':'logPath','path':path,'type':member['type'],
            'variants':[{k:d[k] for k in ('line','default_expression','conditions')} for d in variants]},
        'required_member_gap_counts':{reason:sum(d['reason']==reason for d in required) for reason in sorted({d['reason'] for d in required})},
        'navigation':navigation}
    args.output.write_text(json.dumps(score,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':score['passed'],'checks':len(checks),'summary':trial['member_summary'],'required_member_gap_counts':score['required_member_gap_counts'],'navigation':navigation}))
    if not score['passed']:raise SystemExit('C++ member declaration control failed; inspect saved score')


if __name__=='__main__':main()
