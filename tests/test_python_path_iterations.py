import unittest
from tests import test_python_path_values as fixtures
from adapters.path_patterns import match,instantiate
from adapters.path_values import literal,normalize


class PythonPathIterationTests(unittest.TestCase):
    graph=fixtures.PythonPathValueTests.graph
    values=fixtures.PythonPathValueTests.values

    def test_nested_directory_source_matches_full_path_and_renamed_output(self):
        g=self.graph({'assemble.py':'''import os,shutil
for variant in os.listdir('compiled'):
 for name in os.listdir(os.path.join('compiled',variant,'bin')):
  shutil.copyfile(os.path.join('compiled',variant,'bin',name),os.path.join('release','engine',name))
'''})
        source=self.values(g)[0];destination=self.values(g,'destination')[0]
        self.assertEqual(source['value']['resolution'],'pattern')
        actual=normalize(literal('compiled/unrelated-target/bin/renamed-worker'),'posix')[0]
        result=match(source['value'],actual)
        self.assertEqual(instantiate(destination['value'],result['bindings'])['path'],'release/engine/renamed-worker')
        self.assertEqual(len([n for n in g['nodes'] if n['kind']=='path_iteration' and n['path_style']=='posix']),2)
        self.assertTrue(any(e['kind']=='PATH_ITERATION_SOURCE' for e in g['edges']))

    def test_same_name_in_sequential_loops_has_distinct_directory_and_variable_identity(self):
        g=self.graph({'assemble.py':'''import os,shutil
for name in os.listdir('left'):
 shutil.copyfile(os.path.join('left',name),os.path.join('ship-a',name))
for name in os.listdir('right'):
 shutil.copyfile(os.path.join('right',name),os.path.join('ship-b',name))
'''})
        values=self.values(g);self.assertEqual(len(values),2)
        self.assertNotEqual(values[0]['value']['segments'][-1]['variable'],values[1]['value']['segments'][-1]['variable'])
        self.assertIsNone(match(values[0]['value'],normalize(literal('right/same'),'posix')[0]))

    def test_direct_capture_uses_directory_at_iteration_creation_not_later_mutation(self):
        g=self.graph({'assemble.py':'''import os,shutil
def package():
 root='before'
 for name in os.listdir(root):
  root='after'
  def transfer(): shutil.copyfile(os.path.join(root,name),'ship')
  transfer()
package()
'''})
        value=self.values(g)[0]['value'];entry=value['segments'][-1]
        self.assertEqual(value['segments'][0],'after')
        self.assertEqual(entry['directory']['segments'],['before'])
        self.assertIsNone(match(value,normalize(literal('after/file'),'posix')[0]))
        self.assertEqual(match(value,normalize(literal('after/file'),'posix')[0],allow_unverified_membership=True)['membership_conditions'][0]['basis'],
                         'requires_directory_enumeration_evidence')

    def test_read_outside_loop_and_unknown_iterator_remain_required_gaps(self):
        g=self.graph({'assemble.py':'''import os,shutil
for name in os.listdir('compiled'): pass
shutil.copyfile(name,'ship')
def unknown(): pass
for other in unknown(): shutil.copyfile(other,'ship')
'''})
        reasons={r['reason'] for v in self.values(g) for r in v['value']['unresolved']}
        self.assertIn('python_loop_binding_read_outside_iteration',reasons)
        self.assertIn('python_iteration_source_not_modeled',reasons)

    def test_literal_iteration_preserves_item_index_for_pairing(self):
        g=self.graph({'assemble.py':'''import os,shutil
for name in ['first','second']:
 shutil.copyfile(os.path.join('compiled',name),os.path.join('ship',name))
'''})
        self.assertEqual({v['value']['path'] for v in self.values(g)},{'compiled/first','compiled/second'})
        self.assertEqual({next(c['index'] for c in v['value']['conditions'] if c['kind']=='literal_iteration_item') for v in self.values(g)},{0,1})

    def test_custom_listdir_and_parameter_named_os_are_not_directory_apis(self):
        g=self.graph({'assemble.py':'''import shutil
class Other:
 def listdir(self,root): return ['fake']
def package(os):
 for name in os.listdir('compiled'):
  shutil.copyfile(name,'ship')
package(Other())
'''})
        self.assertFalse([n for n in g['nodes'] if n['kind']=='path_iteration'])
        self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))

    def test_implicit_cwd_and_tuple_projection_are_explicit(self):
        g=self.graph({'assemble.py':'''import os,shutil
for name in os.listdir(): shutil.copyfile(name,'ship')
for root,names in [('native',['one'])]: shutil.copyfile(root,'ship')
'''})
        reasons={r['reason'] for v in self.values(g) for r in v['value']['unresolved']}
        self.assertIn('python_listdir_default_cwd_or_argument_shape_not_bound',reasons)
        self.assertIn('python_iteration_binding_projection_not_expanded',reasons)


if __name__=='__main__':unittest.main()
