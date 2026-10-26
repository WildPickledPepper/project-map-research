from copy import deepcopy
import unittest

from adapters.process_argument_bindings import augment
from adapters.sqlite_fact_graph import validate_graph


def fixture():
    rows=[]
    def node(uid,kind,path='src/service.cpp',**fields):
        rows.append({'id':uid,'kind':kind,'name':uid,'path':path,'line':2,**fields})
    node('cppcfg','build_configuration','build/CMakeLists.txt')
    node('program','build_target','build/CMakeLists.txt',target_type='EXECUTABLE',build_context='cppcfg')
    node('unit','build_source',location={'root':'source','path':'src/service.cpp'})
    for uid in ('entry','parse','receive'):node(uid,'callable')
    node('cppcall','call_site')
    node('argv','cpp_entry_argv',entry='entry')
    node('decoder','string_key_decoder',key='--option=',source_symbol='parse',targets=['receive'],match_mode='substring_search',
        conditions=[],evidence=[{'path':'src/service.cpp','line':2}])
    node('input','cpp_argv_decoder_binding',entry='entry',decoder='decoder',argv_source='argv',origin_complete=True,call_stack=['cppcall'],
        value={'origins':[{'entry':'entry','source':'argv','selectors':[]}],'gaps':[],
            'steps':[{'kind':'formal_argument_source','source_symbol':'parse','evidence':{'path':'src/service.cpp','line':2}}]},conditions=[])
    node('rustmain','callable','front/launch.rs')
    node('rustcall','call_site','front/launch.rs')
    node('constructor','rust_boundary','front/launch.rs',family='command_constructor')
    node('spawn','rust_boundary','front/launch.rs',family='process_start')
    node('value','source_scalar_value','front/launch.rs')
    node('raw','path_value','front/launch.rs',root_function='rustmain',call_stack=['rustcall'])
    node('deployed','deployed_path_candidate','front/launch.rs',consumer='constructor',source_path_value='raw',analysis_context='rustcfg')
    node('template','boundary_argument_template','front/launch.rs',role='process_argument',consumer='spawn',analysis_context='rustcfg',
        root_function='rustmain',call_stack=['rustcall'],parts=[{'literal':'--option='},{'slot':'value','format_spec':''}],
        complete=True,gaps=[],conditions=[])
    edges=[]
    def edge(a,b,kind,**fields):edges.append({'source':a,'target':b,'kind':kind,'status':'source_candidate','evidence':[],**fields})
    edge('program','unit','COMPILES_SOURCE',build_context='cppcfg')
    edge('program','entry','EXECUTABLE_ENTRY_CANDIDATE',build_context='cppcfg')
    edge('deployed','program','RESOLVES_EXECUTABLE_TARGET_CANDIDATE',conditions=[{'kind':'running_process_image_matches_deployment'}])
    edge('spawn','constructor','USES_COMMAND',analysis_contexts=['rustcfg'])
    edge('entry','argv','CPP_ENTRY_ARGV');edge('argv','input','ARGV_FLOW_CANDIDATE')
    edge('input','decoder','BINDS_ARGV_DECODER_CANDIDATE');edge('decoder','receive','DECODED_VALUE_TARGET_CANDIDATE')
    return {'schema_version':1,'source_commit':'authored-command-binding','snapshot':'authored-command-binding',
        'nodes':rows,'edges':edges,'diagnostics':[],'coverage':[],'limits':[],'input_paths':['src/service.cpp','front/launch.rs']}


class ProcessArgumentBindingTests(unittest.TestCase):
    def node(self,g,uid):return next(n for n in g['nodes'] if n['id']==uid)
    def matches(self,g):return [n for n in g['nodes'] if n['kind']=='process_argument_binding']
    def reasons(self,g):return {d['reason'] for d in g['diagnostics'] if d['kind']=='process_argument_binding_unresolved'}

    def test_deployment_entry_context_and_native_file_scope_join_the_word(self):
        g=augment(fixture());validate_graph(g);row,=self.matches(g)
        self.assertEqual(row['provider'],'program');self.assertEqual(row['argv_binding'],'input')
        self.assertEqual(row['source_scope'],{'src/service.cpp':['src/service.cpp']})
        self.assertEqual(row['payload_equivalence'],'not_established');self.assertEqual(row['runtime_execution'],'not_observed')
        self.assertEqual(row['match_status'],'single_conditional_decoder');self.assertEqual(g['process_argument_bindings']['required_gaps'],0)
        self.assertIn('running_process_image_matches_deployment',{c['kind'] for c in row['conditions']})

    def test_same_key_without_a_deployment_provider_does_not_pair(self):
        g=fixture();g['edges']=[e for e in g['edges'] if e['kind']!='RESOLVES_EXECUTABLE_TARGET_CANDIDATE']
        augment(g);self.assertEqual(self.matches(g),[]);self.assertIn('command_provider_not_bound_in_this_graph',self.reasons(g))

    def test_different_command_instance_and_call_or_cfg_do_not_borrow_a_provider(self):
        for field,value in [('consumer','other-constructor'),('analysis_context','other-cfg')]:
            g=fixture();self.node(g,'deployed')[field]=value;augment(g);self.assertEqual(self.matches(g),[])
        for field,value in [('root_function','other-root'),('call_stack',['another-call'])]:
            g=fixture();self.node(g,'raw')[field]=value;augment(g);self.assertEqual(self.matches(g),[])

    def test_same_key_in_another_entry_is_not_the_selected_process(self):
        g=fixture();self.node(g,'input')['entry']='elsewhere';augment(g)
        self.assertEqual(self.matches(g),[]);self.assertIn('provider_argv_decoder_entry_unavailable',self.reasons(g))

    def linked(self,command='target_link_libraries',context='cppcfg',kind='SHARED_LIBRARY'):
        g=fixture();self.node(g,'parse')['path']=self.node(g,'receive')['path']=self.node(g,'cppcall')['path']='lib/parser.cpp'
        g['nodes'].extend([{'id':'library','kind':'build_target','name':'library','path':'lib/CMakeLists.txt','line':1,
            'target_type':kind,'build_context':context},{'id':'libunit','kind':'build_source','name':'libunit','path':'lib/parser.cpp','line':1,
            'location':{'root':'source','path':'lib/parser.cpp'}}])
        g['edges'].extend([{'source':'program','target':'library','kind':'LINKS_BUILD_TARGET','build_context':'cppcfg','evidence':[{'command':command}]},
            {'source':'library','target':'libunit','kind':'COMPILES_SOURCE','build_context':context,'evidence':[]}])
        return g

    def test_linked_library_code_and_header_visibility_have_native_unit_evidence(self):
        g=augment(self.linked());self.assertEqual(len(self.matches(g)),1)
        g=fixture();self.node(g,'parse')['path']=self.node(g,'receive')['path']='include/api.h'
        augment(g,visibility={'src/service.cpp':{'src/service.cpp','include/api.h'}})
        self.assertEqual(self.matches(g)[0]['source_scope']['include/api.h'],['src/service.cpp'])

    def test_build_only_dependencies_executables_and_other_configs_do_not_supply_code(self):
        for g in (self.linked('add_dependencies'),self.linked(context='other-context'),self.linked(kind='EXECUTABLE')):
            augment(g);self.assertEqual(self.matches(g),[])
            self.assertIn('decoder_sources_outside_selected_native_link_scope',self.reasons(g))

    def test_dependency_creation_command_is_not_inferred_from_an_outer_wrapper_name(self):
        g=self.linked('add_dependencies');edge=next(e for e in g['edges'] if e['kind']=='LINKS_BUILD_TARGET')
        edge['evidence'].append({'command':'target_link_libraries'});augment(g);self.assertEqual(self.matches(g),[])

    def test_unknown_header_scope_and_scope_budget_remain_explicit(self):
        g=fixture();self.node(g,'parse')['path']='include/api.h';augment(g);self.assertEqual(self.matches(g),[])
        g=augment(self.linked(),max_scope_targets=1);self.assertEqual(self.matches(g),[]);self.assertIn('native_source_scope_budget',self.reasons(g))

    def test_incomplete_origin_foreign_entry_and_unmodeled_preparation_cannot_pair(self):
        for change in ('incomplete','foreign','unknown','append'):
            g=fixture();row=self.node(g,'input')
            if change=='incomplete':row['origin_complete']=False;row['value']['gaps']=['mutation']
            elif change=='foreign':row['value']['origins'][0]['entry']='foreign'
            else:row['value']['steps'].append({'kind':'unmodeled_replace' if change=='unknown' else 'standard_string_append','source_symbol':'parse'})
            augment(g);self.assertEqual(self.matches(g),[])

    def test_partial_payload_retains_known_key_and_its_required_gap(self):
        g=fixture();self.node(g,'template').update(complete=False,gaps=['unknown-display'])
        augment(g);row,=self.matches(g);self.assertFalse(row['payload_source_complete'])
        self.assertIn('argument_payload_source_unresolved',self.reasons(g))

    def test_known_string_format_capture_can_supply_a_literal_prefix(self):
        g=fixture();self.node(g,'value')['literal']='--option='
        self.node(g,'template')['parts']=[{'slot':'value','format_spec':''},{'slot':'runtime','format_spec':''}]
        augment(g);self.assertEqual(self.matches(g)[0]['literal_prefix'],'--option=')

    def test_unknown_prefix_sequence_and_missing_key_are_explicit(self):
        for change in ('prefix','sequence','key'):
            g=fixture();template=self.node(g,'template')
            if change=='prefix':template['parts']=[{'slot':'value','format_spec':''}]
            elif change=='sequence':template['role']='process_argument_sequence_unexpanded'
            else:template['parts']=[{'literal':'--new='}]
            augment(g);self.assertEqual(self.matches(g),[]);self.assertTrue(g['process_argument_bindings']['required_gaps'])

    def test_multiple_scoped_decoders_remain_multiple_conditional_matches(self):
        g=fixture();second=deepcopy(self.node(g,'input'));second['id']='second';g['nodes'].append(second)
        augment(g);self.assertEqual(len(self.matches(g)),2)
        self.assertTrue(all(n['match_status']=='multiple_conditional_matches' for n in self.matches(g)))

    def test_duplicate_native_edges_and_binding_budget_do_not_duplicate_nodes(self):
        g=fixture();g['edges'].append(deepcopy(next(e for e in g['edges'] if e['kind']=='RESOLVES_EXECUTABLE_TARGET_CANDIDATE')))
        augment(g);validate_graph(g);self.assertEqual(len(self.matches(g)),1)
        g=augment(fixture(),max_bindings=0);self.assertEqual(self.matches(g),[]);self.assertIn('process_argument_binding_budget',self.reasons(g))

    def test_duplicate_projection_is_rejected(self):
        g=augment(fixture())
        with self.assertRaisesRegex(ValueError,'already present'):augment(g)

    def test_equality_switch_requires_the_entire_known_source_word(self):
        g=fixture();self.node(g,'decoder').update(match_mode='string_equality',key='--relaxed',targets=[])
        self.node(g,'template')['parts']=[{'literal':'--relaxed'}]
        augment(g);row,=self.matches(g);self.assertEqual(row['word_match_basis'],'full_source_word')
        self.assertEqual(row['payload_equivalence'],'not_established')
        self.assertIn('prepared_input_equals_literal_switch_key',{c['kind'] for c in row['conditions']})
        for parts in ([{'literal':'--relaxed=1'}],[{'literal':'before--relaxed'}],[{'literal':'--relaxed'},{'slot':'value','format_spec':''}]):
            g=fixture();self.node(g,'decoder').update(match_mode='string_equality',key='--relaxed',targets=[])
            self.node(g,'template')['parts']=parts;augment(g);self.assertEqual(self.matches(g),[])

    def test_known_literal_capture_can_supply_the_whole_switch_word(self):
        g=fixture();self.node(g,'decoder').update(match_mode='string_equality',key='--changed',targets=[])
        self.node(g,'value')['literal']='--changed';self.node(g,'template')['parts']=[{'slot':'value','format_spec':''}]
        augment(g);self.assertEqual(len(self.matches(g)),1)

    def test_equality_unknown_suffix_keeps_a_specific_required_gap(self):
        g=fixture();self.node(g,'decoder').update(match_mode='string_equality',key='--relaxed',targets=[])
        self.node(g,'template').update(parts=[{'literal':'--relaxed'},{'slot':'value','format_spec':''}],complete=False,gaps=['dynamic_suffix'])
        augment(g);self.assertEqual(self.matches(g),[])
        self.assertIn('argument_equality_word_value_unresolved',self.reasons(g))

    def test_equality_rejects_a_proven_nonempty_unconditional_append(self):
        for literal,conditions,expected in [('=',[],0),('',[],1),('=',[{'kind':'branch','when':True}],1)]:
            g=fixture();self.node(g,'decoder').update(match_mode='string_equality',key='--relaxed',targets=[])
            self.node(g,'template')['parts']=[{'literal':'--relaxed'}]
            self.node(g,'input')['value']['steps'].append({'kind':'standard_string_append','source_symbol':'parse',
                'operand':{'literal':literal},'conditions':conditions,'preserves_existing_prefix':True})
            augment(g);self.assertEqual(len(self.matches(g)),expected)
            if not expected:self.assertIn('literal_switch_changed_by_unconditional_append',self.reasons(g))


if __name__=='__main__':unittest.main()
