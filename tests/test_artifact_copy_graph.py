import unittest
from tests import test_python_path_values as fixtures
from adapters.artifact_copy_graph import augment
from adapters.sqlite_fact_graph import validate_graph


class ArtifactCopyGraphTests(unittest.TestCase):
    def graph(self,body,artifact='native/worker',script='make.py',host='Linux',target='Linux',root='source'):
        levels=len(script.split('/'));base='os.path.realpath(__file__)'
        for _ in range(levels):base='os.path.dirname('+base+')'
        g=fixtures.PythonPathValueTests().graph({script:'import os,shutil,platform\nROOT='+base+'\n'+body})
        g['nodes'].extend([
            {'id':'native-context','kind':'build_configuration','path':'CMakeLists.txt','line':0,'name':'Release',
                'target_system':{'status':'available','name':target,'host_name':host,'target_path_style':'windows' if target=='Windows' else 'posix',
                    'host_path_style':'windows' if host=='Windows' else 'posix'}},
            {'id':'native-artifact','kind':'build_artifact','path':artifact,'line':0,'name':artifact.split('/')[-1],
                'build_context':'native-context','location':{'root':root,'path':artifact},'materialization':'not_verified'}])
        return g

    def paths(self,graph):return [n['value']['relative_path'] for n in graph['nodes'] if n['kind']=='copied_artifact']

    def test_two_layouts_and_renamed_paths_use_identical_discovery(self):
        for script,native,stage,ship in [('make.py','native','stage','desktop/runtime'),('automation/tasks/build.py','objects','normalized','plugins/release')]:
            with self.subTest(script=script):
                body=f"""for item in os.listdir(os.path.join(ROOT,'{native}')):
 if item.endswith('.a'): continue
 shutil.copyfile(os.path.join(ROOT,'{native}',item),os.path.join(ROOT,'{stage}',item))
shutil.copytree(os.path.join(ROOT,'{stage}'),os.path.join(ROOT,'{ship}'))
"""
                g=augment(self.graph(body,artifact=native+'/arbitrary.bin',script=script));validate_graph(g)
                self.assertEqual(set(self.paths(g)),{stage+'/arbitrary.bin',ship+'/arbitrary.bin'})
                self.assertEqual(g['artifact_copy_flow']['copied_artifacts'],2)
                self.assertTrue(all(e['status']=='conditional_candidate' for e in g['edges'] if e['kind']=='COPIES_ARTIFACT_TO'))

    def test_archive_suffix_and_wrong_directory_do_not_propagate(self):
        body="""for item in os.listdir(os.path.join(ROOT,'native')):
 if item.endswith('.a'): continue
 shutil.copyfile(os.path.join(ROOT,'native',item),os.path.join(ROOT,'ship',item))
"""
        for path in ('native/static.a','unrelated/worker'):
            with self.subTest(path=path):self.assertEqual(self.paths(augment(self.graph(body,artifact=path))),[])

    def test_windows_host_linux_target_selects_packaging_host_and_retains_target(self):
        g=augment(self.graph("if platform.system()=='Windows': shutil.copyfile(os.path.join(ROOT,'native','worker'),os.path.join(ROOT,'ship','worker'))\n",host='Windows',target='Linux'))
        self.assertEqual(self.paths(g),['ship/worker'])
        copied=next(n for n in g['nodes'] if n['kind']=='copied_artifact')
        self.assertEqual(copied['value']['style'],'windows');self.assertEqual(copied['target_system']['name'],'Linux')
        self.assertEqual(copied['runtime_execution'],'not_observed');self.assertEqual(copied['materialization'],'not_verified')

    def test_build_root_and_missing_native_host_remain_required_gaps(self):
        body="shutil.copyfile(os.path.join(ROOT,'native','worker'),os.path.join(ROOT,'ship','worker'))\n"
        build=augment(self.graph(body,root='build'));self.assertFalse(self.paths(build))
        self.assertTrue(any(d.get('reason')=='native_artifact_root_not_bound_to_source_layout' for d in build['diagnostics']))
        g=self.graph(body);next(n for n in g['nodes'] if n['id']=='native-context')['target_system']={}
        g=augment(g);self.assertFalse(self.paths(g));self.assertTrue(any(d.get('reason')=='native_artifact_host_context_not_bound' for d in g['diagnostics']))

    def test_opposite_lexical_order_does_not_copy_new_content_into_an_earlier_consumer(self):
        body="shutil.copyfile(os.path.join(ROOT,'stage','worker'),os.path.join(ROOT,'ship','worker'))\nshutil.copyfile(os.path.join(ROOT,'native','worker'),os.path.join(ROOT,'stage','worker'))\n"
        self.assertEqual(self.paths(augment(self.graph(body))),['stage/worker'])

    def test_prior_move_blocks_copy_until_lifetime_effect_is_resolved(self):
        body="""shutil.copyfile(os.path.join(ROOT,'native','worker'),os.path.join(ROOT,'stage','worker'))
shutil.move(os.path.join(ROOT,'stage','worker'),os.path.join(ROOT,'other','worker'))
shutil.copyfile(os.path.join(ROOT,'stage','worker'),os.path.join(ROOT,'ship','worker'))
"""
        g=augment(self.graph(body));self.assertEqual(self.paths(g),['stage/worker'])
        self.assertTrue(any(d.get('reason')=='source_lifetime_requires_destructive_effect_resolution' for d in g['diagnostics']))

    def test_cycles_depth_and_attempt_budget_have_explicit_gaps(self):
        body="shutil.copyfile(os.path.join(ROOT,'native','worker'),os.path.join(ROOT,'stage','worker'))\nshutil.copyfile(os.path.join(ROOT,'stage','worker'),os.path.join(ROOT,'native','worker'))\n"
        g=augment(self.graph(body));self.assertEqual(self.paths(g),['stage/worker'])
        self.assertTrue(any(d.get('reason')=='artifact_copy_path_cycle' for d in g['diagnostics']))
        second="shutil.copyfile(os.path.join(ROOT,'stage','worker'),os.path.join(ROOT,'ship','worker'))\n"
        first=body.splitlines()[0]+'\n'
        g=augment(self.graph(first+second),max_steps=1);self.assertEqual(self.paths(g),['stage/worker'])
        self.assertTrue(any(d.get('reason')=='artifact_copy_depth_or_candidate_budget' for d in g['diagnostics']))
        g=augment(self.graph(first+second),max_attempts=0);self.assertFalse(self.paths(g))
        self.assertTrue(any(d.get('reason')=='artifact_copy_attempt_budget' for d in g['diagnostics']))

    def test_literal_iteration_order_distinguishes_single_and_later_iterations(self):
        body="""for item in ['worker']:
 shutil.copyfile(os.path.join(ROOT,'stage',item),os.path.join(ROOT,'ship',item))
 shutil.copyfile(os.path.join(ROOT,'native',item),os.path.join(ROOT,'stage',item))
"""
        g=augment(self.graph(body))
        self.assertNotIn('ship/worker',self.paths(g))
        g=augment(self.graph(body.replace("['worker']","['worker','worker']")))
        self.assertEqual(self.paths(g).count('ship/worker'),1)
        copied=next(n for n in g['nodes'] if n['kind']=='copied_artifact' and n['value']['relative_path']=='ship/worker')
        self.assertTrue(any(c['kind']=='operation_reached_after_producer_and_before_consumer' for c in copied['conditions']))


if __name__=='__main__':unittest.main()
