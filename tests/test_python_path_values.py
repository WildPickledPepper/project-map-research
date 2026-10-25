from pathlib import Path
import tempfile
import unittest

from adapters.python_facts import analyze
from adapters.python_path_values import augment
from adapters.sqlite_fact_graph import validate_graph


class PythonPathValueTests(unittest.TestCase):
    def graph(self,files):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,body in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
            graph=augment(root,analyze(root,list(files)))
            graph.update(snapshot='authored-python-paths',source_commit='authored-python-paths')
            validate_graph(graph)
            return graph

    def values(self,g,role='source',style='posix'):
        return [n for n in g['nodes'] if n['kind']=='path_value' and n['role']==role and n['path_context']['style']==style]

    def test_import_alias_class_constants_and_source_file_root_have_real_origins(self):
        g=self.graph({'tools/assemble.py':'''import os as filesystem
from shutil import copytree as relocate
ROOT=filesystem.path.dirname(filesystem.path.dirname(filesystem.path.realpath(__file__)))
class Layout:
 OUTPUT='build-output'
relocate(filesystem.path.join(ROOT,Layout.OUTPUT,'bin'),filesystem.path.join(ROOT,'release','engine'))
'''})
        source=self.values(g)[0];destination=self.values(g,'destination')[0]
        self.assertEqual(source['value']['base']['kind'],'canonical_source_root')
        self.assertEqual(source['value']['relative_path'],'build-output/bin')
        self.assertEqual(destination['value']['relative_path'],'release/engine')
        self.assertEqual(source['value']['conditions'][0]['kind'],'canonical_source_layout_required')
        ns={n['id']:n for n in g['nodes']}
        origins=[ns[e['target']]['name'] for e in g['edges'] if e['source']==source['id'] and e['kind']=='PATH_COMPONENT_SOURCE']
        self.assertIn('__file__',origins);self.assertIn("'build-output'",origins)

    def test_copy_file_and_copy_tree_preserve_distinct_destination_contracts(self):
        g=self.graph({'make.py':'''import shutil
shutil.copyfile(dst='package/renamed.bin',src='native/old.bin')
shutil.copytree('native/tree','package/tree',ignore=shutil.ignore_patterns('*.a'),dirs_exist_ok=True)
shutil.copy('native/worker','package')
'''})
        ops=[n for n in g['nodes'] if n['kind']=='python_file_operation']
        self.assertEqual([n['destination_semantics'] for n in ops],[['exact_path'],['directory_root'],['file_or_existing_directory']])
        self.assertEqual(self.values(g)[0]['value']['path'],'native/old.bin')
        self.assertEqual(self.values(g,'destination')[0]['value']['path'],'package/renamed.bin')
        self.assertEqual({v['keyword'] for v in ops[1]['option_values']},{'ignore','dirs_exist_ok'})
        self.assertTrue(all(n['mapping_status']=='requires_control_flow_options_and_destination_context' for n in ops))

    def test_pathlib_join_division_parent_and_chaining_require_import_identity(self):
        g=self.graph({'bundle.py':'''from pathlib import Path as Location
from shutil import copyfile
left=Location('stage').joinpath('payload').parent / 'different' / 'worker'
copyfile(left,Location('ship')/'renamed')
'''})
        self.assertEqual(self.values(g)[0]['value']['path'],'stage/different/worker')
        self.assertEqual(self.values(g,'destination')[0]['value']['path'],'ship/renamed')

    def test_two_path_styles_do_not_assume_analysis_host(self):
        g=self.graph({'make.py':"import os,shutil\nshutil.copyfile(os.path.join('R:\\\\native','worker'), 'ship/worker')\n"})
        windows=self.values(g,style='windows')[0]['value'];posix=self.values(g)[0]['value']
        self.assertEqual(windows['base'],{'kind':'literal_anchor','value':'R:\\'})
        self.assertIsNone(posix['base'])
        self.assertEqual({n['path_context']['style'] for n in g['nodes'] if n['kind']=='path_value'},{'windows','posix'})

    def test_same_named_local_modules_and_parameters_do_not_create_copy_operations(self):
        g=self.graph({'shutil.py':'def copyfile(src,dst): pass\n',
            'make.py':'''import shutil
shutil.copyfile('one','two')
def foreign(shutil): shutil.copytree('one','two')
'''})
        self.assertFalse([n for n in g['nodes'] if n['kind']=='python_file_operation'])

    def test_unrelated_path_class_does_not_gain_standard_library_join_semantics(self):
        g=self.graph({'make.py':'''import shutil
class Path:
 def __init__(self,value): pass
 def __truediv__(self,other): return self
shutil.copyfile(Path('fake')/'worker','ship')
'''})
        value=self.values(g)[0]['value']
        self.assertEqual(value['resolution'],'unresolved')
        self.assertIn('unproven_path_division_receiver',{r['reason'] for r in value['unresolved']})

    def test_independent_parameters_stay_distinct_and_callers_are_not_merged(self):
        g=self.graph({'make.py':'''import os,shutil
def bundle(left,right):
 shutil.copytree(os.path.join(left,'payload'),os.path.join(right,'resources'))
bundle('a','x')
bundle('b','y')
'''})
        pairs={}
        for role in ('source','destination'):
            for value in self.values(g,role):pairs.setdefault(value['operation_context'],{})[role]=value['value']['path']
        self.assertEqual({(p['source'],p['destination']) for p in pairs.values()},
                         {('a/payload','x/resources'),('b/payload','y/resources')})
        self.assertTrue(all(len(v['call_stack'])==1 for v in self.values(g)))

    def test_directory_iteration_and_star_args_remain_gaps_while_simple_helper_resolves(self):
        g=self.graph({'make.py':'''import os,shutil
def custom(value): return os.path.join('native',value)
for name in os.listdir('native'):
 shutil.copyfile(os.path.join('native',name),os.path.join('ship',name))
shutil.copyfile(custom('worker'),'ship/worker')
shutil.copytree(*('native','ship'))
'''})
        self.assertTrue(any(n['value']['resolution']=='unresolved' for n in self.values(g)))
        self.assertTrue(any(d['kind']=='python_path_value_unresolved' and d['required'] for d in g['diagnostics']))
        self.assertTrue(any(d['kind']=='python_file_operation_argument_expansion' and d['required'] for d in g['diagnostics']))
        self.assertTrue(any(v['value']['path']=='native/worker' for v in self.values(g)))

    def test_conditional_paths_keep_alternatives_and_enclosing_branch(self):
        g=self.graph({'make.py':'''import shutil
def bundle(flag):
 if flag:
  shutil.copyfile('first' if flag else 'second','ship')
'''})
        values=self.values(g)
        self.assertEqual({v['value']['path'] for v in values},{'first','second'})
        self.assertEqual({v['value']['conditions'][0]['branch'] for v in values},{'body','orelse'})
        self.assertTrue(all(v['conditions'][0]['expression']=='flag' and v['conditions'][0]['branch']=='body' for v in values))

    def test_overlapping_ast_positions_do_not_turn_string_addition_into_path_division(self):
        g=self.graph({'make.py':'''from pathlib import Path
import shutil
shutil.copyfile(Path('native') / 'folder' + 'tail','ship')
'''})
        self.assertEqual(self.values(g)[0]['value']['resolution'],'unresolved')

    def test_os_dirname_retains_trailing_separator_semantics_of_constant_joins(self):
        g=self.graph({'make.py':'''import os,shutil
shutil.copyfile(os.path.dirname(os.path.join('root','child/')),'ship')
'''})
        self.assertEqual(self.values(g)[0]['value']['path'],'root/child')

    def test_assignment_branch_conditions_survive_use_outside_the_branch(self):
        g=self.graph({'make.py':'''import shutil
def bundle(flag):
 if flag:
  root='first'
 else:
  root='second'
 shutil.copyfile(root,'ship')
'''})
        values=self.values(g)
        self.assertEqual({v['value']['path'] for v in values},{'first','second'})
        self.assertEqual({v['value']['conditions'][0]['branch'] for v in values},{'body','else'})


if __name__=='__main__':unittest.main()
