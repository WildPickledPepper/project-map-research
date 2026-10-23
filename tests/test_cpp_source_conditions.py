import unittest
from adapters.cpp_data import DataExtractor
from adapters.cpp_source_conditions import extract_conditions
import tests.test_cpp_data as data_tests


class SourceConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): data_tests.CppDataTests.setUpClass(); cls.parser = data_tests.CppDataTests.parser

    def extract(self, code): return extract_conditions(DataExtractor({'a.cpp': code.encode()}, self.parser))

    def test_source_const_member_and_renaming(self):
        for name in ['flag', 'renamed']:
            r = self.extract('struct S{const bool '+name+'=false;S(){} void run(){if('+name+')yes();else no();}};')
            self.assertIs(r['guards'][0]['value'], False)
            self.assertEqual(r['guards'][0]['branches'], [{'when': True, 'reachable': False}, {'when': False, 'reachable': True}])

    def test_explicit_constructor_value_overrides_default(self):
        r = self.extract('struct S{const bool f=false;S():f(true){} void run(){if(f)yes();}};')
        self.assertIs(r['guards'][0]['value'], True)

    def test_alternative_constructors_keep_unknown(self):
        r = self.extract('struct S{const bool f=false;S(){} S(int):f(true){} void run(){if(f)yes();}};')
        self.assertIsNone(r['guards'][0]['value'])

    def test_aggregate_mutable_and_shadowed_fields_are_not_constants(self):
        self.assertFalse(self.extract('struct S{bool f=false;S(){} void run(){if(f)yes();}};')['guards'])
        r = self.extract('struct S{const bool f=false;void run(){if(f)yes();}};')
        self.assertIsNone(r['guards'][0]['value'])
        self.assertFalse(self.extract('struct S{const bool f=false;S(){} void run(bool f){if(f)yes();}};')['guards'])

    def test_other_receiver_and_negation(self):
        r = self.extract('struct S{const bool f=false;S(){} static void run(S& s){if(!s.f)yes();}};')
        self.assertIs(r['guards'][0]['value'], True)


if __name__ == '__main__': unittest.main()
