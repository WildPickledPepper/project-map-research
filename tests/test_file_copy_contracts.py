import unittest
from tests import test_python_path_values as fixtures
from adapters.path_values import normalize,literal
from adapters.file_copy_contracts import map_member


class FileCopyContractTests(unittest.TestCase):
    graph=fixtures.PythonPathValueTests.graph

    def mappings(self,body,path,style='posix',**extra):
        graph=self.graph({'make.py':'import os,shutil,platform\n'+body});nodes={n['id']:n for n in graph['nodes']}
        values=[n for n in graph['nodes'] if n['kind']=='path_value' and n['value']['style']==style]
        results=[]
        for src in values:
            if src['role']!='source':continue
            for dst in values:
                if dst['role']=='destination' and dst['operation_context']==src['operation_context']:
                    result=map_member(nodes[src['operation_context']],src,dst,normalize(literal(path),style)[0],
                        host_system={'name':'Windows' if style=='windows' else 'Linux','path_style':style},**extra)
                    results.append(result)
        return results

    def destinations(self,results):return [m['destination']['path'] for r in results for m in r['mappings']]

    def test_exact_copy_and_directory_tree_preserve_distinct_members(self):
        exact=self.mappings("shutil.copyfile('raw/worker','release/renamed')\n",'raw/worker')
        tree=self.mappings("shutil.copytree('raw','release')\n",'raw/lib/sub/worker')
        self.assertEqual(self.destinations(exact),['release/renamed'])
        self.assertEqual(self.destinations(tree),['release/lib/sub/worker'])
        self.assertTrue(tree[0]['mappings'][0]['conditions'])
        self.assertEqual(self.destinations(self.mappings("shutil.copytree('raw','release')\n",'raw')),[])

    def test_same_basename_in_another_root_never_matches(self):
        results=self.mappings("shutil.copyfile('one/worker','ship/worker')\n",'two/worker')
        self.assertEqual(self.destinations(results),[]);self.assertEqual(results[0]['status'],'not_matched')

    def test_iteration_suffix_and_directory_branch_are_applied(self):
        body="""for item in os.listdir('native'):
 if os.path.isdir(os.path.join('native',item)):
  shutil.copytree(os.path.join('native',item),os.path.join('ship',item))
  continue
 if item.endswith('.a'): continue
 shutil.copyfile(os.path.join('native',item),os.path.join('ship',item))
"""
        self.assertEqual(self.destinations(self.mappings(body,'native/worker')),['ship/worker'])
        self.assertEqual(self.destinations(self.mappings(body,'native/archive.a')),[])

    def test_ignore_patterns_apply_to_each_basename_including_ancestors(self):
        body="shutil.copytree('raw','ship',ignore=shutil.ignore_patterns('*.a','private'))\n"
        for path in ('raw/archive.a','raw/private/worker','raw/lib/private/worker'):
            with self.subTest(path=path):self.assertEqual(self.destinations(self.mappings(body,path)),[])
        self.assertEqual(self.destinations(self.mappings(body,'raw/lib/worker')),['ship/lib/worker'])

    def test_pattern_case_rules_use_the_supplied_host(self):
        body="shutil.copytree('raw','ship',ignore=shutil.ignore_patterns('*.A'))\n"
        self.assertEqual(self.destinations(self.mappings(body,'raw/archive.a',style='windows')),[])
        self.assertEqual(self.destinations(self.mappings(body,'raw/archive.a')),['ship/archive.a'])

    def test_custom_callbacks_do_not_infer_unchanged_content(self):
        for option in ('ignore=callback','copy_function=callback'):
            with self.subTest(option=option):
                results=self.mappings('def callback(*args): pass\nshutil.copytree(\'raw\',\'ship\','+option+')\n','raw/worker')
                self.assertEqual(results[0]['status'],'gap');self.assertEqual(self.destinations(results),[])

    def test_copy_and_copy2_keep_both_destination_state_conditions(self):
        results=self.mappings("shutil.copy2('raw/worker','ship')\n",'raw/worker')
        self.assertEqual(self.destinations(results),['ship','ship/worker'])
        self.assertEqual([m['conditions'][-1]['value'] for m in results[0]['mappings']],[False,True])

    def test_positional_tree_options_are_not_assigned_by_keyword_order(self):
        results=self.mappings("shutil.copytree('raw','ship',False,shutil.ignore_patterns('*.a'),shutil.copyfile,False,True)\n",'raw/worker')
        self.assertEqual(self.destinations(results),['ship/worker'])
        self.assertTrue(results[0]['mappings'][0]['options']['dirs_exist_ok'])
        self.assertEqual(results[0]['mappings'][0]['options']['copy_function']['api'],['shutil.copyfile'])

    def test_different_calls_and_literal_iterations_keep_pairs(self):
        body="""def cp(src,dst): shutil.copyfile(src,dst)
cp('one/worker','first/renamed')
cp('two/worker','second/renamed')
for part in ['a','b']: shutil.copyfile(os.path.join('raw',part),os.path.join('ship',part))
"""
        self.assertEqual(self.destinations(self.mappings(body,'one/worker')),['first/renamed'])
        self.assertEqual(self.destinations(self.mappings(body,'raw/a')),['ship/a'])

    def test_conditional_overwrite_keeps_static_selection_gap(self):
        body="source='raw/old'\nif platform.system()=='Linux': source='raw/new'\nshutil.copyfile(source,'ship')\n"
        results=self.mappings(body,'raw/old')
        self.assertEqual(self.destinations(results),[])
        self.assertTrue(any(r['reason']=='copy_guard_static_context_incomplete' for r in results))

    def test_unset_runtime_environment_remains_a_condition(self):
        body="if os.getenv('ENABLED','')=='yes': shutil.copyfile('raw/worker','ship/worker')\n"
        results=self.mappings(body,'raw/worker')
        self.assertTrue(results[0]['mappings'][0]['guards']['residual'])
        self.assertEqual(self.destinations(self.mappings(body,'raw/worker',environment={'ENABLED':None})),[])

    def test_moves_have_a_named_contract_gap(self):
        results=self.mappings("shutil.move('raw/worker','ship/worker')\n",'raw/worker')
        self.assertEqual(results[0]['reason'],'file_operation_contract_not_supported')


if __name__=='__main__':unittest.main()
