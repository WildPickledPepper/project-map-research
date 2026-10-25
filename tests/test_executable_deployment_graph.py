import copy
import unittest

from adapters.executable_deployment_graph import augment
from adapters.path_values import normalize
from adapters.sqlite_fact_graph import validate_graph


class ExecutableDeploymentTests(unittest.TestCase):
    def graph(self,shipping='ship',suffix='',style='posix'):
        host='Windows' if style=='windows' else 'Linux';triple='x86_64-pc-windows-msvc' if style=='windows' else 'x86_64-unknown-linux-gnu'
        system={'status':'available','name':host,'host_name':host,'target_path_style':style,'host_path_style':style,'target':triple,'target_arch':'x86_64'}
        nodes=[];edges=[]
        def node(uid,kind,**extra):
            nodes.append({'id':uid,'kind':kind,'name':uid,'path':'manifest','line':1,**extra})
        def edge(source,target,kind,**extra):
            edges.append({'source':source,'target':target,'kind':kind,'status':'fixture_source','evidence':[],**extra})
        node('cargo-config','build_configuration',language='cargo',target_system=system,workspace={'root':'source','path':'Cargo.toml'})
        node('cargo-target','build_target',language='cargo',build_context='cargo-config',target_type='EXECUTABLE',native_target_kind=['bin'],
            package={'name':'frontend'},profile={'debug_assertions':False,'test':False},features_requested=[],default_features_requested=True,declared_features=['default'])
        node('source-module','code_module',language='rust',syntax='source_file',path='main.rs')
        node('rust-entry','callable',language='rust',path='main.rs');edge('source-module','rust-entry','CONTAINS_SYMBOL')
        edge('cargo-target','source-module','CARGO_TARGET_SOURCE');edge('cargo-target','rust-entry','EXECUTABLE_ENTRY_CANDIDATE')
        node('cargo-artifact','build_artifact',location={'root':'source','path':'objects/release/neutral'+suffix},build_context='cargo-config',native_executable=True)
        edge('cargo-target','cargo-artifact','PRODUCES_ARTIFACT',artifact_role='primary')
        for uid,path in [('launcher',shipping+'/renamed'+suffix),('server',shipping+'/assets/service/worker'+suffix)]:
            node(uid,'copied_artifact',value=normalize({'op':'source_file','source':'fixture','path':path},style)[0],
                origin_artifact='cargo-artifact' if uid=='launcher' else 'cpp-artifact',conditions=[{'kind':'fixture_copy_lineage','artifact':uid}])
        node('cpp-config','build_configuration',language='cmake',target_system={**system,'target_arch':None,'declared_processor':'AMD64'})
        node('cpp-target','build_target',language='cmake',build_context='cpp-config',target_type='EXECUTABLE')
        node('cpp-entry','callable',language='cpp',path='entry.cpp');edge('cpp-target','cpp-entry','EXECUTABLE_ENTRY_CANDIDATE')
        node('cpp-artifact','build_artifact',location={'root':'source','path':'native/worker'+suffix},build_context='cpp-config')
        edge('cpp-target','cpp-artifact','PRODUCES_ARTIFACT',artifact_role='primary')
        node('rust-context','analysis_context',language='rust',workspace='Cargo.toml',target=triple,debug_assertions=False,features=['frontend/default'],cfg=[])
        node('current-exe','call_site',language='rust',path='main.rs')
        node('program-value','value',language='rust',path='main.rs')
        node('command','rust_boundary',language='rust',path='main.rs',family='command_constructor',conditions=[])
        node('process-start','rust_boundary',language='rust',path='main.rs',family='process_start');edge('process-start','command','USES_COMMAND')
        value={'base':{'kind':'current_executable_directory','workspace':'Cargo.toml','source':'current-exe'},
            'segments':['assets','service','worker'+suffix],'style':style,'unresolved':[],'conditions':[]}
        node('path-value','path_value',language='rust',path='main.rs',value=value,consumer='command',root_function='rust-entry',analysis_contexts=['rust-context'])
        edge('command','program-value','COMMAND_PROGRAM');edge('program-value','path-value','PATH_VALUE_CANDIDATE')
        return {'snapshot':'authored-deployment','source_commit':'authored-deployment','nodes':nodes,'edges':edges,'diagnostics':[]}

    def node(self,g,uid):return next(n for n in g['nodes'] if n['id']==uid)
    def targets(self,g):return [e for e in g['edges'] if e['kind']=='RESOLVES_EXECUTABLE_TARGET_CANDIDATE']

    def test_two_layouts_and_launcher_renames_use_full_paths(self):
        for shipping,suffix,style in [('ship','','posix'),('dist/desktop/resources','.exe','windows')]:
            graph=augment(self.graph(shipping,suffix,style));validate_graph(graph)
            self.assertEqual(graph['executable_deployment']['deployment_images'],2)
            matches=self.targets(graph);self.assertEqual(len(matches),1);self.assertEqual(matches[0]['target'],'cpp-target')
            binding=self.node(graph,matches[0]['source']);self.assertEqual(binding['location']['path'],shipping+'/assets/service/worker'+suffix)
            self.assertEqual(binding['ownership_basis'],'native_call_frames_rooted_at_cargo_entry')
            self.assertEqual(binding['match_status'],'single_conditional_producer')
            self.assertFalse(any(d['required'] for d in graph['diagnostics']))
            self.assertEqual(matches[0]['runtime_execution'],'not_observed')
            kinds={c['kind'] for c in matches[0]['conditions']}
            self.assertIn('running_process_image_matches_deployment',kinds);self.assertIn('target_os_loader_accepts_provider_image',kinds)
            self.assertIn('deployed_path_resolution_has_no_symlink_or_mount_redirection',kinds)

    def test_equal_basename_in_another_directory_never_matches(self):
        graph=self.graph();self.node(graph,'server')['value']['segments'][0]='other'
        graph=augment(graph);self.assertFalse(self.targets(graph))
        self.assertTrue(any(d['reason']=='current_exe_consumer_artifact_not_matched' and d['required'] for d in graph['diagnostics']))

    def test_profile_feature_target_and_test_harness_contexts_stay_separate(self):
        for update in ({'debug_assertions':True},{'features':['frontend/http']},{'target':'another-triple'},{'cfg':['test']}):
            graph=self.graph();self.node(graph,'rust-context').update(update);graph=augment(graph)
            with self.subTest(update=update):self.assertFalse(self.targets(graph));self.assertEqual(graph['executable_deployment']['counts'].get('bindings',0),0)

    def test_other_binary_in_same_workspace_does_not_own_this_path(self):
        graph=self.graph();self.node(graph,'source-module')['id']='unrelated-module'
        self.node(graph,'rust-entry')['id']='unrelated-entry'
        for e in graph['edges']:
            if e['source']=='source-module':e['source']='unrelated-module'
            if e['target']=='source-module':e['target']='unrelated-module'
            if e['target']=='rust-entry':e['target']='unrelated-entry'
        graph['nodes'].append({'id':'rust-entry','kind':'callable','name':'outside','path':'other.rs','line':1,'language':'rust'})
        graph=augment(graph);self.assertFalse(self.targets(graph))
        self.assertTrue(any(d['reason']=='current_exe_owner_or_build_context_not_bound' for d in graph['diagnostics']))

    def test_native_module_membership_keeps_callback_reachability_conditional(self):
        graph=self.graph();self.node(graph,'path-value')['root_function']='callback'
        graph['nodes'].append({'id':'callback','kind':'callable','name':'callback','path':'main.rs','line':9,'language':'rust'})
        graph['edges'].append({'source':'source-module','target':'callback','kind':'CONTAINS_SYMBOL','status':'fixture','evidence':[]})
        graph=augment(graph);binding=self.node(graph,self.targets(graph)[0]['source'])
        self.assertEqual(binding['ownership_basis'],'cargo_root_module_membership_in_analysis_context')
        self.assertTrue(any(c['kind']=='consumer_path_reached_in_running_binary' for c in binding['conditions']))

    def test_parent_of_current_exe_and_dot_dot_require_filesystem_layout_conditions(self):
        graph=self.graph();image=self.node(graph,'launcher');image['value']['segments'].insert(1,'bin')
        path=self.node(graph,'path-value');path['value']['base']={'kind':'parent_of','base':path['value']['base']}
        path['value']['segments']=['unused','..',*path['value']['segments']]
        graph=augment(graph);self.assertEqual(len(self.targets(graph)),1)

    def test_multiple_full_path_producers_are_explicit_conditional_alternatives(self):
        graph=self.graph();original=self.node(graph,'cpp-target');other=copy.deepcopy(original);other['id']='alternative-target';graph['nodes'].append(other)
        graph['edges'].append({'source':'alternative-target','target':'cpp-artifact','kind':'PRODUCES_ARTIFACT','status':'fixture','evidence':[],'artifact_role':'primary'})
        graph=augment(graph);self.assertEqual({e['target'] for e in self.targets(graph)},{'cpp-target','alternative-target'})
        binding=self.node(graph,self.targets(graph)[0]['source']);self.assertEqual(binding['match_status'],'ambiguous_conditional_producers')
        self.assertTrue(any(d['reason']=='multiple_conditional_producers_at_deployed_path' and not d['required'] for d in graph['diagnostics']))

    def test_binding_budget_and_unresolved_path_do_not_produce_partial_matches(self):
        graph=augment(self.graph(),max_bindings=0);self.assertFalse(self.targets(graph))
        self.assertTrue(any(d['reason']=='current_exe_binding_budget' for d in graph['diagnostics']))
        graph=self.graph();self.node(graph,'path-value')['value']['unresolved']=[{'reason':'dynamic_name'}];graph=augment(graph)
        self.assertFalse(self.targets(graph));self.assertTrue(any(d['reason']=='current_exe_path_components_unresolved' for d in graph['diagnostics']))
        with self.assertRaisesRegex(ValueError,'already present'):augment(graph)


if __name__=='__main__':unittest.main()
