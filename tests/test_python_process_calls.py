import unittest
from tests import test_python_path_values as fixtures
from adapters.python_process_values import resolve,environment_value


class PythonProcessCallTests(unittest.TestCase):
    graph=fixtures.PythonPathValueTests.graph
    host={'name':'Linux','path_style':'posix'}

    def invocations(self,g,style='posix'):return [n for n in g['nodes'] if n['kind']=='python_process_invocation' and n['path_style']==style]
    def effects(self,g):return [n for n in g['nodes'] if n['kind']=='python_environment_effect']
    def argv(self,v,host=None):
        resolved=resolve(v,host or self.host)
        return [a[0]['text'] if len(a)==1 else None for a in resolved.get('argv',[])]

    def test_readonly_wrapper_preserves_argv_cwd_and_call_pairing(self):
        g=self.graph({'tools.py':'''import subprocess as sp
def execute(words,folder):
 sp.run(words,cwd=folder)
 if False: print(' '.join(words))
''','pack.py':'''from tools import execute
execute(['cargo','build','--release'],'one/crate')
execute(['other','inspect'],'two/crate')
'''})
        values=self.invocations(g)
        self.assertEqual([self.argv(v) for v in values],[['cargo','build','--release'],['other','inspect']])
        self.assertEqual([resolve(v,self.host)['cwd'][0]['text'] for v in values],['one/crate','two/crate'])
        self.assertTrue(all(resolve(v,self.host)['status']=='conditional_candidate' for v in values))
        self.assertTrue(any(e['kind']=='PROCESS_ARGUMENT_COMPONENT' for e in g['edges']))
        self.assertTrue(any(e['kind']=='PROCESS_CALL_STACK' for e in g['edges']))

    def test_exact_argument_strings_preserve_empty_and_dot_segments(self):
        g=self.graph({'make.py':"import subprocess\nsubprocess.run(['runner','','./file','--map=a//b'],cwd='.')\n"})
        self.assertEqual(self.argv(self.invocations(g)[0]),['runner','','./file','--map=a//b'])

    def test_host_branches_select_whole_command_arrays(self):
        g=self.graph({'make.py':'''import platform,subprocess
if platform.system()=='Windows': args=['cargo.exe','build','--release']
else: args=['cargo','build']
subprocess.run(args,cwd='work')
'''})
        values=[v for v in self.invocations(g) if resolve(v,self.host)['status']=='conditional_candidate']
        self.assertEqual([self.argv(v) for v in values],[['cargo','build']])
        host={'name':'Windows','path_style':'windows'}
        win=[v for v in self.invocations(g,'windows') if resolve(v,host)['status']=='conditional_candidate']
        self.assertEqual([self.argv(v,host) for v in win],[['cargo.exe','build','--release']])

    def test_list_alias_mutation_unknown_escape_and_nested_source_mutation_are_gaps(self):
        for effect in ("alias=words\nalias.append('--other')",'unknown(words)',
                       'def mutate(x): x.clear()\nmutate(words)'):
            with self.subTest(effect=effect):
                g=self.graph({'make.py':"import subprocess\nwords=['cargo','build']\n"+effect+"\nsubprocess.run(words)\n"})
                resolved=resolve(self.invocations(g)[0],self.host)
                self.assertEqual(resolved['status'],'gap')
                self.assertIn('python_process_sequence_mutation_or_escape_not_expanded',resolved['gaps'])

    def test_direct_putenv_binds_process_environment_and_keeps_mapping_distinction(self):
        g=self.graph({'make.py':'''import os,subprocess
os.putenv('CARGO_TARGET_DIR','objects')
subprocess.run(['cargo','build'])
'''})
        invocation=self.invocations(g)[0];effects=self.effects(g)
        value=environment_value(invocation,effects,'CARGO_TARGET_DIR',self.host)
        self.assertTrue(value['known']);self.assertEqual(value['value']['text'],'objects')
        self.assertFalse(next(e for e in effects if e['id']==value['writer'])['also_updates_os_environ'])
        self.assertTrue(any(e['kind']=='PROCESS_ENVIRONMENT_EFFECT' for e in g['edges']))

    def test_source_root_environment_and_working_directory_remain_symbolic_paths(self):
        g=self.graph({'make.py':'''import os,subprocess
ROOT=os.path.dirname(os.path.realpath(__file__))
os.putenv('CARGO_TARGET_DIR',os.path.join(ROOT,'objects'))
subprocess.run(['cargo','build'],cwd=os.path.join(ROOT,'crate'))
'''})
        invocation=self.invocations(g)[0];resolved=resolve(invocation,self.host)
        self.assertEqual(resolved['cwd'][0]['path_value']['relative_path'],'crate')
        value=environment_value(invocation,self.effects(g),'CARGO_TARGET_DIR',self.host)
        self.assertTrue(value['known']);self.assertIsNone(value['value']['text'])
        self.assertEqual(value['value']['path_value']['relative_path'],'objects')

    def test_environ_item_set_and_delete_update_process_and_mapping(self):
        g=self.graph({'make.py':'''import os,subprocess
def first():
 os.environ['OUTPUT']='objects'
 subprocess.run(['first'])
 del os.environ['OUTPUT']
 subprocess.run(['second'])
first()
'''})
        values=self.invocations(g);effects=self.effects(g)
        one=environment_value(values[0],effects,'OUTPUT',self.host);two=environment_value(values[1],effects,'OUTPUT',self.host)
        self.assertTrue(one['known']);self.assertEqual(one['value']['text'],'objects')
        self.assertTrue(two['known']);self.assertIsNone(two['value'])
        self.assertTrue(all(e['also_updates_os_environ'] for e in effects))

    def test_late_write_does_not_affect_previous_process_and_latest_write_wins(self):
        g=self.graph({'make.py':'''import os,subprocess
os.putenv('OUT','first')
os.putenv('OUT','second')
subprocess.run(['runner'])
os.putenv('OUT','later')
'''})
        value=environment_value(self.invocations(g)[0],self.effects(g),'OUT',self.host)
        self.assertTrue(value['known']);self.assertEqual(value['value']['text'],'second')

    def test_conditional_write_shared_with_invocation_is_retained_as_precondition(self):
        g=self.graph({'make.py':'''import os,subprocess
if os.getenv('PACKAGE'):
 os.putenv('OUT','objects')
 subprocess.run(['runner'])
'''})
        invocation=self.invocations(g)[0]
        self.assertTrue(resolve(invocation,self.host)['guards']['residual'])
        value=environment_value(invocation,self.effects(g),'OUT',self.host)
        self.assertTrue(value['known']);self.assertEqual(value['value']['text'],'objects')

    def test_optional_later_write_and_unknown_mapping_mutation_remain_unknown(self):
        for extra in ("if os.getenv('CUSTOM'): os.putenv('OUT','other')",'os.environ.update(external)'):
            with self.subTest(extra=extra):
                g=self.graph({'make.py':"import os,subprocess\nos.putenv('OUT','objects')\n"+extra+"\nsubprocess.run(['runner'])\n"})
                value=environment_value(self.invocations(g)[0],self.effects(g),'OUT',self.host)
                self.assertFalse(value['known'])

    def test_explicit_environment_does_not_inherit_putenv_or_analysis_environment(self):
        g=self.graph({'make.py':"import os,subprocess\nos.putenv('OUT','objects')\nsubprocess.run(['runner'],env={})\n"})
        value=environment_value(self.invocations(g)[0],self.effects(g),'OUT',self.host)
        self.assertFalse(value['known']);self.assertEqual(value['reason'],'explicit_child_environment_mapping_not_expanded')
        g=self.graph({'make.py':"import subprocess\nsubprocess.run(['runner'])\n"})
        value=environment_value(self.invocations(g)[0],[],'OUT',self.host)
        self.assertFalse(value['known'])

    def test_two_caller_environments_are_not_merged(self):
        g=self.graph({'make.py':'''import os,subprocess
def execute(folder):
 os.putenv('OUT',folder)
 subprocess.run(['runner'])
execute('first')
execute('second')
'''})
        self.assertEqual([environment_value(n,self.effects(g),'OUT',self.host)['value']['text'] for n in self.invocations(g)],['first','second'])

    def test_windows_environment_keys_are_case_insensitive(self):
        g=self.graph({'make.py':"import os,subprocess\nos.putenv('cargo_target_dir','objects')\nsubprocess.run(['cargo'])\n"})
        host={'name':'Windows','path_style':'windows'}
        self.assertEqual(environment_value(self.invocations(g,'windows')[0],self.effects(g),'CARGO_TARGET_DIR',host)['value']['text'],'objects')

    def test_loop_order_and_unrelated_root_do_not_bind_environment(self):
        g=self.graph({'make.py':'''import os,subprocess
def unrelated(): os.putenv('OUT','other')
def execute(): subprocess.run(['runner'])
'''})
        self.assertFalse(environment_value(self.invocations(g)[0],self.effects(g),'OUT',self.host)['known'])
        g=self.graph({'make.py':"import os,subprocess\nfor name in ['a','b']:\n os.putenv('OUT','objects')\n subprocess.run(['runner'])\n"})
        self.assertFalse(environment_value(self.invocations(g)[0],self.effects(g),'OUT',self.host)['known'])

    def test_direct_library_member_replacement_cannot_resolve_as_std_process(self):
        g=self.graph({'make.py':'''import subprocess
def other(args): return None
subprocess.run=other
subprocess.run(['cargo'])
'''})
        self.assertTrue(all(resolve(n,self.host)['status']=='gap' for n in self.invocations(g)))

    def test_replaced_environment_api_may_affect_keys_other_than_its_argument(self):
        g=self.graph({'make.py':'''import os,subprocess
os.putenv('OUT','objects')
def custom(key,value): return None
os.putenv=custom
os.putenv('OTHER','value')
subprocess.run(['runner'])
'''})
        value=environment_value(self.invocations(g)[0],self.effects(g),'OUT',self.host)
        self.assertFalse(value['known'])

    def test_string_shell_override_and_preexec_keep_execution_gaps(self):
        for body,style,host in [("subprocess.run('cargo build')",'windows',{'name':'Windows','path_style':'windows'}),
                    ("subprocess.run(['cargo','build'],shell=True)",'posix',self.host),
                    ("subprocess.run(['cargo','build'],executable='other')",'posix',self.host),
                    ("subprocess.run(['cargo','build'],preexec_fn=setup)",'posix',self.host)]:
            with self.subTest(body=body):
                g=self.graph({'make.py':'import subprocess\n'+body+'\n'})
                self.assertEqual(resolve(self.invocations(g,style)[0],host)['status'],'gap')

    def test_async_exec_arguments_and_keyword_cwd_are_distinct_from_shell(self):
        g=self.graph({'make.py':"import asyncio\nasyncio.create_subprocess_exec('cargo','build',cwd='work')\n"})
        invocation=self.invocations(g)[0]
        self.assertEqual(self.argv(invocation),['cargo','build'])
        self.assertEqual(resolve(invocation,self.host)['status'],'conditional_candidate')

    def test_explicit_none_working_directory_keeps_inherited_mode(self):
        g=self.graph({'make.py':'''import subprocess
def execute(words,cwd=None): subprocess.run(words,cwd=cwd)
execute(['runner'])
'''})
        invocation=self.invocations(g)[0]
        self.assertEqual(invocation['working_directory_mode'],'inherited')
        self.assertEqual(resolve(invocation,self.host)['status'],'conditional_candidate')

    def test_empty_command_and_argument_expansion_are_gaps(self):
        for body in ('subprocess.run([])','subprocess.run(*external)',"subprocess.run(['cargo'],**options)"):
            with self.subTest(body=body):
                g=self.graph({'make.py':'import subprocess\n'+body+'\n'})
                self.assertEqual(resolve(self.invocations(g)[0],self.host)['status'],'gap')

    def test_custom_subprocess_module_and_shadowed_parameter_are_not_library_calls(self):
        g=self.graph({'subprocess.py':'def run(*args,**kwargs): return None\n','make.py':"import subprocess\nsubprocess.run(['cargo'])\n"})
        self.assertFalse(self.invocations(g))


if __name__=='__main__':unittest.main()
