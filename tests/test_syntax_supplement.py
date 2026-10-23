import os
from pathlib import Path
import unittest

import tree_sitter_language_pack as pack
from adapters.syntax_supplement import extract

if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
    pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))


class SyntaxSupplementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp=pack.get_parser('cpp')
        cls.ts=pack.get_parser('typescript')

    def cpp_facts(self,source):
        return extract(source.encode('utf-8'),'sample.h','cpp',self.cpp)

    def ts_facts(self,source):
        return extract(source.encode('utf-8'),'sample.ts','typescript',self.ts)

    def test_virtual_declarations_and_overloads_are_distinct(self):
        result=self.cpp_facts('namespace a { class Store { public: virtual bool query(int key)=0; virtual bool query(const char* key)=0; }; }')
        symbols=result['symbols']
        self.assertEqual(len(symbols),2)
        self.assertTrue(all(s['qualified_name']=='a::Store::query' for s in symbols))
        self.assertTrue(all(s['pure_virtual'] and not s['definition'] for s in symbols))
        self.assertEqual(len({s['id'] for s in symbols}),2)
        self.assertIn('(const char* key)',{s['parameters'] for s in symbols})

    def test_qualified_definition_and_namespace_are_preserved(self):
        result=self.cpp_facts('namespace a { bool Live::query(int key) { return true; } }')
        self.assertEqual(result['symbols'][0]['qualified_name'],'a::Live::query')
        self.assertTrue(result['symbols'][0]['definition'])

    def test_same_name_in_other_namespace_stays_separate(self):
        result=self.cpp_facts('namespace a { class Store { bool query(int); }; } namespace b { class Store { bool query(int); }; }')
        self.assertEqual({s['qualified_name'] for s in result['symbols']},{'a::Store::query','b::Store::query'})

    def test_return_expression_is_a_call_not_a_method(self):
        result=self.cpp_facts('int f() { return std::move(value); }')
        self.assertEqual([s['name'] for s in result['symbols']],['f'])
        self.assertEqual(result['calls'][0]['callee_spelling'],'std::move')
        self.assertEqual(result['calls'][0]['resolution'],'unresolved')

    def test_function_pointer_is_not_a_method(self):
        result=self.cpp_facts('struct State { int (*callback)(int); };')
        self.assertFalse(result['symbols'])

    def test_const_reference_and_noexcept_preserved(self):
        result=self.cpp_facts('struct Store { const Value& query(const Key& key) const noexcept; };')
        signature=result['symbols'][0]['signature_spelling']
        for spelling in ('const Value&','const Key&','const noexcept'):
            self.assertIn(spelling,signature)

    def test_abstract_class_and_generic_method_owner(self):
        result=self.ts_facts('abstract class Base { send<T>(x:T):T { return x; } } class Child extends Base { send<T>(x:T):T { return super.send(x); } }')
        self.assertEqual({s['qualified_name'] for s in result['symbols']},{'Base.send','Child.send'})
        self.assertTrue(all(s['type_parameters']=='<T>' for s in result['symbols']))

    def test_callback_keeps_lexical_owner(self):
        result=self.ts_facts('class Client { fetch() { const callback = () => this.send(); return callback(); } send() {} }')
        call=next(c for c in result['calls'] if c['callee_spelling']=='this.send')
        self.assertEqual(call['owner_name'],'Client.fetch.callback')
        self.assertEqual(call['resolution'],'unresolved')

    def test_property_binding_is_observed_not_resolved(self):
        result=self.ts_facts("window.requestData = createRequest(connector);")
        binding=result['bindings'][0]
        self.assertEqual(binding['left_spelling'],'window.requestData')
        self.assertEqual(binding['right_spelling'],'createRequest(connector)')
        self.assertEqual(binding['execution_condition'],'not_evaluated')

    def test_comments_and_strings_do_not_create_symbols(self):
        result=self.cpp_facts('// virtual bool fake() = 0;\nconst char* s="void fake() {}";')
        self.assertFalse(result['symbols'])

    def test_error_region_is_visible(self):
        result=self.cpp_facts('class Broken { virtual bool query( = ;')
        self.assertTrue(result['diagnostics'])

    def test_deletion_does_not_retain_previous_facts(self):
        self.assertEqual(len(self.cpp_facts('void old() {}')['symbols']),1)
        self.assertEqual(self.cpp_facts('')['symbols'],[])

    def test_crlf_and_lf_have_same_facts(self):
        self.assertEqual(self.cpp_facts('void f() {}\r\n'),self.cpp_facts('void f() {}\n'))

    def test_paths_are_portable(self):
        for path in ('../other.cpp','/root/file.cpp','C:/file.cpp','x\\y.cpp'):
            with self.assertRaises(ValueError):extract(b'',path,'cpp',self.cpp)

    def test_self_authored_fixture_has_seven_query_occurrences(self):
        root=Path(__file__).resolve().parents[1]/'experiments/2026-10-23-p1/fixtures'
        results=[extract((root/p).read_bytes(),p,'cpp',self.cpp) for p in ('contracts.h','contracts.cpp')]
        symbols=[s for r in results for s in r['symbols'] if s['name']=='query']
        self.assertEqual(len(symbols),7)
        self.assertEqual(sum(s['pure_virtual'] for s in symbols),2)


if __name__=='__main__':unittest.main()
