import unittest
from tests import test_python_path_values as fixtures


class PythonPathContextTests(unittest.TestCase):
    graph=fixtures.PythonPathValueTests.graph
    values=fixtures.PythonPathValueTests.values

    def pairs(self,g):
        pairs={}
        for role in ('source','destination'):
            for value in self.values(g,role):pairs.setdefault(value['operation_context'],{})[role]=value['value']['path']
        return {(p['source'],p['destination']) for p in pairs.values()}

    def test_cross_file_nested_callers_and_return_helper_preserve_paired_paths(self):
        g=self.graph({'ops.py':'''from os.path import join
from shutil import copytree
def transfer(source,destination):
 copytree(join(source,'bin'),join(destination,'engine'))
''','build.py':'''import os
from ops import transfer as perform
def location(root): return os.path.join(root,'plugin')
def package(source,destination): perform(source,location(destination))
package('native-one','bundle')
package('native-two','package')
'''})
        self.assertEqual(self.pairs(g),{('native-one/bin','bundle/plugin/engine'),('native-two/bin','package/plugin/engine')})
        self.assertTrue(all(len(v['call_stack'])==2 for v in self.values(g)))
        self.assertTrue(any(e['kind']=='PATH_CALL_CONTEXT' for e in g['edges']))
        self.assertEqual(len([n for n in g['nodes'] if n['kind']=='file_operation_context']),2)

    def test_keyword_and_literal_default_arguments_are_not_combined_across_calls(self):
        g=self.graph({'make.py':'''import shutil
def transfer(destination,*,source='native'):
 shutil.copyfile(source,destination)
transfer('ship')
transfer(destination='other',source='different')
'''})
        self.assertEqual(self.pairs(g),{('native','ship'),('different','other')})
        self.assertTrue(any(c['kind']=='literal_default_argument' for v in self.values(g) for c in v['value']['conditions']))

    def test_nonliteral_defaults_preserve_definition_time_gap(self):
        g=self.graph({'make.py':'''import shutil
ROOT='native'
def transfer(destination,source=ROOT): shutil.copyfile(source,destination)
ROOT='changed-after-definition'
transfer('ship')
'''})
        values=self.values(g)
        self.assertTrue(all(v['value']['resolution']=='unresolved' for v in values))
        self.assertTrue(any(r['reason']=='python_default_definition_context_not_expanded' for v in values for r in v['value']['unresolved']))

    def test_uncalled_functions_keep_their_own_symbolic_parameters(self):
        g=self.graph({'make.py':'''import shutil
def first(left,right): shutil.copytree(left,right)
def second(left,right): shutil.copytree(left,right)
'''})
        values=self.values(g)
        self.assertEqual(len(values),2)
        self.assertTrue(all(v['value']['resolution']=='symbolic_base' and v['value']['base']['kind']=='parameter' for v in values))
        self.assertNotEqual(values[0]['value']['base']['source'],values[1]['value']['base']['source'])

    def test_library_parameter_is_verified_per_call_context(self):
        g=self.graph({'make.py':'''import shutil
class Other:
 def copyfile(self,src,dst): pass
def transfer(lib,src,dst): lib.copyfile(src,dst)
transfer(shutil,'real','ship')
transfer(Other(),'fake','elsewhere')
'''})
        self.assertEqual(self.pairs(g),{('real','ship')})
        self.assertTrue(any(d['kind']=='python_file_operation_api_not_bound_in_call_context' and d['required'] for d in g['diagnostics']))

    def test_direct_nested_function_capture_uses_matching_outer_call(self):
        g=self.graph({'make.py':'''import shutil
def package(source):
 def transfer(destination): shutil.copyfile(source,destination)
 transfer('ship')
package('first')
package('second')
'''})
        self.assertEqual(self.pairs(g),{('first','ship'),('second','ship')})

    def test_recursive_source_path_helper_reports_gap(self):
        g=self.graph({'make.py':'''import shutil
def location(root): return location(root)
shutil.copyfile(location('native'),'ship')
'''})
        self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))
        self.assertTrue(any(r['reason']=='recursive_python_path_call' for v in self.values(g) for r in v['value']['unresolved']))

    def test_source_star_arguments_are_not_guessed(self):
        g=self.graph({'make.py':'''import shutil
def transfer(src,dst): shutil.copyfile(src,dst)
transfer(*('native','ship'))
'''})
        self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))
        self.assertTrue(any(r['reason']=='python_path_call_arguments_not_explicitly_bound' for v in self.values(g) for r in v['value']['unresolved']))

    def test_multiple_returns_remain_explicit_until_control_flow_is_expanded(self):
        g=self.graph({'make.py':'''import shutil
def location(flag):
 if flag: return 'native'
 return 'other'
shutil.copyfile(location(True),'ship')
'''})
        self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))
        self.assertTrue(any(r['reason']=='python_multiple_return_control_flow_not_expanded' for v in self.values(g) for r in v['value']['unresolved']))

    def test_caller_context_budget_keeps_required_remainder(self):
        body='import shutil\ndef transfer(src,dst): shutil.copyfile(src,dst)\n'
        body+='\n'.join(f'transfer("native-{i}","ship-{i}")' for i in range(35))
        g=self.graph({'make.py':body});values=self.values(g)
        self.assertEqual(len([v for v in values if v['value']['resolution']=='constant']),32)
        self.assertTrue(any(r['reason']=='python_path_caller_context_budget' for v in values for r in v['value']['unresolved']))

    def test_early_return_at_caller_and_continue_at_consumer_keep_source_predicates(self):
        g=self.graph({'make.py':'''import os,shutil
def transfer(root):
 for name in os.listdir(root):
  if name.endswith('.a'): continue
  shutil.copyfile(os.path.join(root,name),'ship')
def package(enabled):
 if not enabled: return
 transfer('native')
package(True)
'''})
        node=self.values(g)[0];ns={n['id']:n for n in g['nodes']}
        guards=[c for c in node['value']['conditions'] if c['kind']=='preceding_control_transfer_not_taken']
        self.assertEqual({c['transfer'] for c in guards},{'Return','Continue'})
        expressions={ns[c['when'][0]['test']]['name'] for c in guards}
        self.assertEqual(expressions,{"name.endswith",'not enabled'})
        linked={e['target'] for e in g['edges'] if e['source']==node['id'] and e['kind']=='PATH_GUARD_SOURCE'}
        self.assertTrue({c['when'][0]['test'] for c in guards}<=linked)

    def test_break_in_completed_prior_loop_does_not_become_consumer_exclusion(self):
        g=self.graph({'make.py':'''import shutil
for name in ['one']:
 break
shutil.copyfile('native','ship')
'''})
        self.assertFalse([c for c in self.values(g)[0]['value']['conditions'] if c.get('transfer')=='Break'])

    def test_module_global_is_read_at_each_invocation_position(self):
        g=self.graph({'make.py':'''import shutil
ROOT='first'
def transfer(): shutil.copyfile(ROOT,'ship')
transfer()
ROOT='second'
transfer()
'''})
        self.assertEqual(self.pairs(g),{('first','ship'),('second','ship')})

    def test_assignment_rhs_reads_previous_value_before_new_binding_is_written(self):
        g=self.graph({'make.py':'''import os,shutil
def transfer():
 root='native'
 root=os.path.join(root,'bin')
 shutil.copyfile(root,'ship')
 root='changed-after-consumption'
transfer()
'''})
        self.assertEqual(self.pairs(g),{('native/bin','ship')})

    def test_unknown_entry_with_multiple_global_writes_keeps_context_gap(self):
        g=self.graph({'make.py':'''import shutil
ROOT='first'
def transfer(): shutil.copyfile(ROOT,'ship')
ROOT='second'
'''})
        self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))
        self.assertTrue(any(r['reason']=='python_storage_read_context_not_bound' for v in self.values(g) for r in v['value']['unresolved']))

    def test_library_global_reassignment_does_not_classify_later_fake_call_as_copy(self):
        g=self.graph({'make.py':'''import shutil
class Other:
 def copyfile(self,src,dst): pass
lib=shutil
def transfer(): lib.copyfile('native','ship')
transfer()
lib=Other()
transfer()
'''})
        self.assertEqual(len(self.values(g)),1)
        self.assertEqual(self.pairs(g),{('native','ship')})


if __name__=='__main__':unittest.main()
