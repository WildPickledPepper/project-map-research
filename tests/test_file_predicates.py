import unittest
from tests import test_python_path_values as fixtures
from adapters.path_values import expression_dag,expression_from_dag,literal,operation,normalize
from adapters.path_patterns import match
from adapters.file_predicate_values import evaluate,conditions


class FilePredicateTests(unittest.TestCase):
    graph=fixtures.PythonPathValueTests.graph
    values=fixtures.PythonPathValueTests.values

    def permitted(self,value,path,**extra):
        actual=normalize(literal(path),'posix')[0];matched=match(value['value'],actual)
        self.assertIsNotNone(matched)
        return conditions(value['value']['conditions'],style='posix',bindings=matched['bindings'],artifact_path=actual,artifact_kind='file',**extra)

    def test_suffix_continue_is_evaluated_from_matched_directory_filename(self):
        g=self.graph({'assemble.py':'''import os,shutil
for name in os.listdir('native'):
 if name.endswith('.a'): continue
 shutil.copyfile(os.path.join('native',name),os.path.join('ship',name))
'''})
        value=self.values(g)[0]
        self.assertFalse(self.permitted(value,'native/archive.a')['permitted'])
        accepted=self.permitted(value,'native/worker.bin')
        self.assertTrue(accepted['permitted']);self.assertFalse(accepted['residual'])

    def test_directory_branch_and_prior_continue_are_separate_for_regular_artifact(self):
        g=self.graph({'assemble.py':'''import os,shutil
for name in os.listdir('native'):
 if os.path.isdir(os.path.join('native',name)):
  shutil.copytree(os.path.join('native',name),os.path.join('ship',name))
  continue
 shutil.copyfile(os.path.join('native',name),os.path.join('ship',name))
'''})
        nodes={n['id']:n for n in g['nodes']}
        values={nodes[v['consumer']]['api_candidates'][0]:v for v in self.values(g)}
        self.assertFalse(self.permitted(values['shutil.copytree'],'native/worker')['permitted'])
        self.assertTrue(self.permitted(values['shutil.copyfile'],'native/worker')['permitted'])

    def test_outer_caller_flag_uses_its_bound_value(self):
        g=self.graph({'assemble.py':'''import shutil
def transfer(source,enabled):
 if not enabled: return
 shutil.copyfile(source,'ship')
transfer('first',True)
transfer('second',False)
'''})
        decisions={v['value']['path']:conditions(v['value']['conditions'],style='posix')['permitted'] for v in self.values(g)}
        self.assertEqual(decisions,{'first':True,'second':False})

    def test_native_host_system_selects_packaging_branch(self):
        g=self.graph({'assemble.py':'''import platform,shutil
if platform.system()=='Windows': shutil.copyfile('native','ship')
'''})
        value=self.values(g)[0]
        self.assertTrue(conditions(value['value']['conditions'],style='posix',host_system={'name':'Windows','path_style':'windows'})['permitted'])
        self.assertFalse(conditions(value['value']['conditions'],style='posix',host_system={'name':'Linux','path_style':'posix'})['permitted'])

    def test_environment_is_an_explicit_input_not_the_analysis_process_environment(self):
        g=self.graph({'assemble.py':'''import os,shutil
if os.getenv('PACKAGE_ENABLED','').lower()=='yes': shutil.copyfile('native','ship')
'''})
        guards=self.values(g)[0]['value']['conditions']
        self.assertTrue(conditions(guards,style='posix')['residual'])
        self.assertTrue(conditions(guards,style='posix',environment={'PACKAGE_ENABLED':'YES'})['permitted'])
        self.assertFalse(conditions(guards,style='posix',environment={'PACKAGE_ENABLED':None})['permitted'])

    def test_same_named_custom_method_does_not_become_builtin_string_rule(self):
        g=self.graph({'assemble.py':'''import shutil
class Other:
 def endswith(self,suffix): return False
value=Other()
if value.endswith('.a'): shutil.copyfile('native','ship')
'''})
        expressions=[p['expression'] for c in self.values(g)[0]['value']['conditions'] for p in c.get('predicate_expressions',[])]
        self.assertFalse(any(t['op']=='string_endswith' for e in expressions for t in e['terms']))

    def test_copy_options_preserve_standard_ignore_and_callable_identity(self):
        g=self.graph({'assemble.py':'''import shutil
shutil.copytree('native','ship',ignore=shutil.ignore_patterns('*.a','private'),copy_function=shutil.copy2,dirs_exist_ok=True)
'''})
        options={o['keyword']:evaluate(o['expression'],style='posix') for o in self.values(g)[0]['option_expressions']}
        self.assertEqual(options['ignore']['value'],{'kind':'ignore_patterns','patterns':['*.a','private']})
        self.assertEqual(options['copy_function']['value'],{'kind':'library_callable','api':['shutil.copy2']})
        self.assertTrue(options['dirs_exist_ok']['value'])

    def test_short_circuit_and_missing_filesystem_state_preserve_truth_and_unknown(self):
        expression=operation('boolean_and',literal(False),{'op':'unknown','reason':'runtime'})
        self.assertEqual(evaluate(expression,style='posix'),{'known':True,'value':False})
        expression=operation('filesystem_test',literal('elsewhere'),test='isdir')
        self.assertFalse(evaluate(expression,style='posix')['known'])

    def test_python_boolean_operators_return_operands_and_do_not_coerce_unknowns(self):
        expression=operation('compare',operation('boolean_or',literal(''),literal('yes')),literal('yes'),operators=['Eq'])
        self.assertEqual(evaluate(expression,style='posix'),{'known':True,'value':True})
        expression=operation('boolean_and',{'op':'unknown','reason':'runtime'},literal(0))
        self.assertFalse(evaluate(expression,style='posix')['known'])

    def test_conditional_scalar_write_keeps_a_reaching_definition_gap(self):
        g=self.graph({'assemble.py':'''import platform,shutil
if platform.system()=='Windows': enabled=True
if enabled: shutil.copyfile('native','ship')
'''})
        guards=self.values(g)[0]['value']['conditions']
        result=conditions(guards,style='posix',host_system={'name':'Linux','path_style':'posix'})
        self.assertTrue(result['residual'])

    def test_expression_roundtrip_preserves_sharing_and_rejects_cycles(self):
        shared=literal(True);dag=expression_dag(operation('boolean_and',shared,shared));restored=expression_from_dag(dag)
        self.assertIs(restored['args'][0],restored['args'][1])
        self.assertEqual(evaluate(dag,style='posix')['value'],True)
        with self.assertRaises(ValueError):expression_from_dag({'schema':'path-expression-dag/1','root':{'ref':0},'terms':[{'op':'boolean_not','args':[{'ref':0}]}]})

    def test_incomplete_predicate_is_not_treated_as_a_proven_empty_condition(self):
        result=conditions([{'kind':'enclosing_source_branch','test':None,'predicate_expressions':[],'predicate_complete':False}],style='posix')
        self.assertTrue(result['residual'])

    def test_conditional_source_path_keeps_its_platform_selection(self):
        g=self.graph({'assemble.py':'''import platform,shutil
shutil.copyfile('native' if platform.system()=='Windows' else 'other','ship')
'''})
        decisions={v['value']['path']:conditions(v['value']['conditions'],style='posix',host_system={'name':'Windows','path_style':'windows'})['permitted'] for v in self.values(g)}
        self.assertEqual(decisions,{'native':True,'other':False})

    def test_conditional_assignment_keeps_its_platform_selection(self):
        g=self.graph({'assemble.py':'''import platform,shutil
if platform.system()=='Windows': source='native'
else: source='other'
shutil.copyfile(source,'ship')
'''})
        decisions={v['value']['path']:conditions(v['value']['conditions'],style='posix',host_system={'name':'Windows','path_style':'windows'})['permitted'] for v in self.values(g)}
        self.assertEqual(decisions,{'native':True,'other':False})

    def test_directory_binding_inside_branch_can_use_matched_filename(self):
        g=self.graph({'assemble.py':'''import os,platform,shutil
if platform.system()=='Windows':
 for name in os.listdir('native'):
  if name.endswith('.a'): continue
  shutil.copyfile(os.path.join('native',name),os.path.join('ship',name))
'''})
        self.assertFalse(self.permitted(self.values(g)[0],'native/archive.a',host_system={'name':'Windows','path_style':'windows'})['permitted'])

    def test_known_conditional_overwrite_excludes_old_value(self):
        g=self.graph({'assemble.py':'''import platform,shutil
source='old'
if platform.system()=='Windows': source='new'
shutil.copyfile(source,'ship')
'''})
        old=next(v for v in self.values(g) if v['value']['path']=='old')
        result=conditions(old['value']['conditions'],style='posix',host_system={'name':'Windows','path_style':'windows'})
        self.assertFalse(result['permitted'])


if __name__=='__main__':unittest.main()
