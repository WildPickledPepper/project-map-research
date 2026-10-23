import unittest
import tests.test_cpp_data as data_tests
from adapters.cpp_control import predicates
from adapters.syntax_supplement import walk,text


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):data_tests.CppDataTests.setUpClass();cls.parser=data_tests.CppDataTests.parser

    def conditions(self,source,spelling='work()'):
        tree=self.parser.parse(source.encode());call=next(n for n in walk(tree.root_node) if n.type=='call_expression' and text(n)==spelling)
        return predicates(call)

    def test_early_return_keeps_negative_branch(self):
        p=self.conditions('void f(bool missing){if(missing){log();return;}work();}')
        self.assertEqual([(x['kind'],x['expression'],x['when']) for x in p],[('early_exit_guard','(missing)',False)])

    def test_only_one_returning_nested_branch_does_not_prove_an_exit(self):
        self.assertEqual(self.conditions('void f(bool a,bool b){if(a){if(b)return;}work();}'),[])

    def test_else_return_means_true_path_reaches_later_statement(self):
        p=self.conditions('void f(bool ok){if(ok){log();}else{return;}work();}')
        self.assertTrue(p[0]['when'])

    def test_empty_case_labels_and_default_form_entry_alternatives(self):
        p=self.conditions('void f(int mode){switch(mode){case 1:stop();break;case 2:default:work();}}')
        self.assertEqual(p[0]['entry_labels'],['2','default']);self.assertEqual(p[0]['default_excludes'],['1','2'])

    def test_fallthrough_does_not_cross_a_guaranteed_break(self):
        p=self.conditions('void f(int x){switch(x){case 1:a();case 2:b();break;case 3:work();}}')
        self.assertEqual(p[0]['entry_labels'],['3'])

    def test_conditional_break_keeps_an_unresolved_extra_condition(self):
        p=self.conditions('void f(int x,bool b){switch(x){case 1:if(b)break;case 2:work();}}')
        self.assertEqual(p[0]['entry_labels'],['1','2']);self.assertEqual(p[0]['extra_conditions'],'conditional_transfer_unresolved')

    def test_loop_does_not_become_a_guaranteed_single_execution(self):
        p=self.conditions('void f(bool b){while(b){work();}}')
        self.assertEqual(p[0]['kind'],'loop');self.assertEqual(p[0]['iteration'],'runtime_unknown')
