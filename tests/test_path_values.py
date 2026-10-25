import unittest

from adapters.path_values import expression_dag, literal, normalize, operation, symbol, unknown


class SymbolicPathValueTests(unittest.TestCase):
    def one(self, term, style='posix'):
        rows=normalize(term,style);self.assertEqual(len(rows),1);return rows[0]

    def test_symbolic_base_and_literal_suffix_stay_separate(self):
        term=operation('join',operation('join',symbol('parameter-id'),literal('assets')),literal('worker'))
        value=self.one(term)
        self.assertEqual(value['base'],{'kind':'parameter','source':'parameter-id'})
        self.assertEqual(value['relative_path'],'assets/worker');self.assertIsNone(value['path'])
        self.assertEqual(value['resolution'],'symbolic_base')

    def test_absolute_component_replaces_previous_unknown_base(self):
        for style,path in [('posix','/absolute/worker'),('windows',r'R:\absolute\worker')]:
            value=self.one(operation('join',symbol('base'),literal(path)),style)
            self.assertEqual(value['resolution'],'constant');self.assertEqual(value['segments'],['absolute','worker'])
            self.assertIsNotNone(value['path'])

    def test_windows_drive_relative_does_not_become_a_false_absolute_path(self):
        for path in [r'Q:worker',r'\rooted']:
            value=self.one(operation('join',symbol('base'),literal(path)),'windows')
            self.assertEqual(value['resolution'],'unresolved');self.assertIsNone(value['relative_path'])

    def test_rust_extension_rules_include_hidden_and_trailing_dot_names(self):
        for name,extension,expected in [('worker','exe','worker.exe'),('worker.old','exe','worker.exe'),
            ('worker.','exe','worker.exe'),('.hidden','exe','.hidden.exe'),('worker.old','','worker'),('a.tar.gz','x','a.tar.x')]:
            self.assertEqual(self.one(operation('set_extension',literal(name),literal(extension)))['path'],expected)

    def test_dynamic_component_prevents_matching_a_complete_suffix(self):
        term=operation('set_extension',operation('join',literal('assets'),unknown('input','runtime_name')),literal('exe'))
        value=self.one(term);self.assertEqual(value['resolution'],'unresolved')
        self.assertIsNone(value['path']);self.assertIsNone(value['relative_path'])
        self.assertIn({'reason':'dynamic_path_component','source':'input'},value['unresolved'])

    def test_executable_parent_and_root_parent_have_different_results(self):
        term={'op':'current_executable','source':'call','workspace':'Cargo.toml','call_stack':['caller']}
        value=self.one(operation('parent',term))
        self.assertEqual(value['base']['kind'],'current_executable_directory')
        self.assertEqual(value['base']['call_stack'],['caller'])
        self.assertFalse(normalize(operation('parent',literal('/')),'posix'))

    def test_choices_retain_conditions_without_concatenating_branch_effects(self):
        term={'op':'choice','choices':[{'value':literal('a'),'conditions':[{'source':'flag','polarity':True}]},
            {'value':literal('b'),'conditions':[{'source':'flag','polarity':False}]}]}
        rows=normalize(operation('join',term,literal('worker')),'posix')
        self.assertEqual({r['path'] for r in rows},{'a/worker','b/worker'})
        self.assertEqual({r['conditions'][0]['polarity'] for r in rows},{False,True})

    def test_parent_preserves_dot_dot_without_filesystem_canonicalization(self):
        value=self.one(operation('join',literal('root'),literal('dir/../worker')))
        self.assertEqual(value['segments'],['root','dir','..','worker'])

    def test_unknown_operation_and_candidate_budget_are_explicit(self):
        self.assertEqual(self.one({'op':'unmodeled'})['resolution'],'unresolved')
        term={'op':'choice','choices':[{'value':literal(str(i))} for i in range(5)]}
        result=normalize(term,'posix',max_candidates=2)
        self.assertEqual(result[0]['resolution'],'unresolved')

    def test_shared_branch_prefix_is_serialized_once(self):
        term=literal('root')
        for i in range(12):term={'op':'choice','choices':[{'value':operation('join',term,literal('a'))},{'value':operation('join',term,literal('b'))}]}
        dag=expression_dag(term)
        self.assertLess(len(dag['terms']),70)
        self.assertTrue(all(r['resolution']=='unresolved' for r in normalize(term,'posix',max_candidates=4)))

    def test_constant_extension_return_choice_keeps_its_condition(self):
        extension={'op':'choice','choices':[{'value':literal('exe'),'conditions':[{'kind':'return'}]}]}
        row=self.one(operation('set_extension',literal('worker'),extension))
        self.assertEqual(row['path'],'worker.exe');self.assertEqual(row['conditions'],[{'kind':'return'}])


if __name__=='__main__':unittest.main()
