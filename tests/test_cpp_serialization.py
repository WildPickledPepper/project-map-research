import re
import unittest

from adapters.cpp_data import DataExtractor
from adapters.cpp_serialization import Serialization
import tests.test_cpp_data as data_tests


class SerializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):data_tests.CppDataTests.setUpClass();cls.parser=data_tests.CppDataTests.parser

    def analyze(self,source=None,files=None):
        d=DataExtractor({p:s.encode() for p,s in (files or {'a.cpp':source}).items()},self.parser)
        return Serialization(d).build()

    @staticmethod
    def function(result,name):return next(f for f in result['functions'] if f['name']==name)

    def test_source_wrapper_and_key_rename(self):
        r=self.analyze('using J=rapidjson::Value;struct R{int count;};'
            'void wrap(J& out,std::string_view key,int value){out.AddMember(rapidjson::StringRef(key.data()),value,a);}'
            'J encode(const R& r){J out(rapidjson::kObjectType);wrap(out,"renamed",r.count);return out;}')
        m,=self.function(r,'encode')['field_mappings']
        self.assertEqual(m['wire_path'],['renamed']);self.assertEqual(m['source']['selectors'],['member:count'])
        self.assertTrue(any('wrap(' in e['expression'] for e in m['evidence']))
        self.assertTrue(any('AddMember(' in e['expression'] for e in m['evidence']))

    def test_virtual_json_receiver_keeps_concrete_type_and_implicit_fields(self):
        r=self.analyze('using J=rapidjson::Value;struct Base{virtual J encode()const=0;};'
            'struct A:Base{int count;J encode()const override{J j;j.AddMember("rows",count,a);return j;}};'
            'struct B:Base{int size;J encode()const override{J j;j.AddMember("other",size,a);return j;}};'
            'J relay(const Base& value){try{const auto& ref=dynamic_cast<const Base&>(value);return ref.encode();}catch(...){return {};}}')
        f=self.function(r,'relay');self.assertEqual({tuple(m['wire_path']) for m in f['field_mappings']},{('rows',),('other',)})
        self.assertEqual({tuple(m['source']['root_types']) for m in f['field_mappings']},{('A',),('B',)})

    def test_nested_collection_and_returning_json_helper(self):
        r=self.analyze('using J=rapidjson::Value;struct Item{int count;};struct R{std::vector<Item> entries;};'
            'J itemJson(const Item& x){J j;j.AddMember("total",x.count,a);return j;}'
            'J encode(const R& r){J j;J body;J arr;for(const auto& item:r.entries){arr.PushBack(itemJson(item),a);}'
            'body.AddMember("records",arr,a);j.AddMember("payload",body,a);return std::optional<J>{std::move(j)};}')
        mappings=self.function(r,'encode')['field_mappings']
        item=next(m for m in mappings if m['relation']=='value_dependency')
        self.assertEqual(item['wire_path'],['payload','records','*','total'])
        self.assertEqual(item['source']['selectors'],['member:entries','element','member:count'])
        collection=next(m for m in mappings if m['relation']=='array_iteration_source')
        self.assertEqual(collection['wire_path'],['payload','records'])
        self.assertEqual(collection['source']['selectors'],['member:entries'])

    def test_template_specialization_forwarder_preserves_cast(self):
        r=self.analyze('using J=rapidjson::Value;struct Base{};struct R:Base{int count;};'
            'template<class T>J convert(const T&);template<>J convert<R>(const R& x){J j;j.AddMember("n",x.count,a);return j;}'
            'J wrapper(const Base& x){return convert<R>(dynamic_cast<const R&>(x));}')
        m,=self.function(r,'wrapper')['field_mappings'];self.assertEqual(m['source']['selectors'],['member:count'])
        self.assertIn('R',m['source']['cast_type'])

    def test_same_method_name_on_custom_class_is_not_json(self):
        r=self.analyze('struct Fake{void AddMember(const char*,int,int);};Fake encode(int x){Fake j;j.AddMember("n",x,1);return j;}')
        self.assertEqual(r['functions'],[])

    def test_alias_visibility_and_local_alias_do_not_leak(self):
        r=self.analyze(files={'json.h':'using J=rapidjson::Value;',
            'good.cpp':'#include "json.h"\nJ encode(int x){J j;j.AddMember("n",x,a);return j;}',
            'bad.cpp':'struct J{};J other(int x){J j;j.AddMember("n",x,a);return j;}'})
        self.assertEqual([f['name'] for f in r['functions']],['encode'])
        local=self.analyze('void local(){using J=rapidjson::Value;} J other(int x){J j;j.AddMember("n",x,a);return j;}')
        self.assertEqual(local['functions'],[])

    def test_branch_reassignment_is_unknown_instead_of_stale_source(self):
        r=self.analyze('using J=rapidjson::Value;struct R{int first;int second;};J encode(const R& r,bool mode){'
            'auto value=r.first;if(mode)value=r.second;J j;j.AddMember("n",value,a);return j;}')
        f=self.function(r,'encode');self.assertEqual(f['field_mappings'],[])
        self.assertTrue(any(g.get('reason')=='branch_assignment_unresolved' for g in f['gaps']))

    def test_local_assignment_replaces_source_and_conditional_field_keeps_guard(self):
        r=self.analyze('using J=rapidjson::Value;struct R{int first;int second;};J encode(const R& r,bool mode){'
            'auto value=r.first;value=r.second;J j;if(mode){j.AddMember("n",value,a);}return j;}')
        m,=self.function(r,'encode')['field_mappings'];self.assertEqual(m['source']['selectors'],['member:second'])
        self.assertTrue(any(c.get('kind')=='branch' for c in m['conditions']))

    def test_different_wrapper_invocations_do_not_mix_arguments(self):
        r=self.analyze('using J=rapidjson::Value;void wrap(J& dst,std::string_view key,int value){dst.AddMember(rapidjson::StringRef(key.data()),value,a);}'
            'J encode(int first,int second){J j;wrap(j,"one",first);wrap(j,"two",second);return j;}')
        self.assertEqual({(tuple(m['wire_path']),m['source']['parameter']) for m in self.function(r,'encode')['field_mappings']},{(('one',),0),(('two',),1)})

    def test_unknown_mutation_is_visible(self):
        r=self.analyze('using J=rapidjson::Value;void opaque(J&);J encode(int x){J j;j.AddMember("n",x,a);opaque(j);j.Clear();return j;}')
        f=self.function(r,'encode');self.assertTrue({'unknown_call_may_mutate_json','json_operation_unmodeled'}<={g['kind'] for g in f['gaps']})

    def test_source_registration_is_retained(self):
        r=self.analyze('using J=rapidjson::Value;const std::string CMD="example/run";J encode(int x){J j;j.AddMember("n",x,a);return j;}'
            'struct Router{std::map<std::string,Fn> callbacks;void init(){callbacks.emplace(CMD,encode);}};')
        registration,=r['registrations'];self.assertEqual(registration['key'],'example/run')
        self.assertIn(self.function(r,'encode')['source_symbol'],registration['functions'])

    def test_overload_requirements_survive_generic_forwarder(self):
        r=self.analyze('using J=rapidjson::Value;'
            'template<class T> void put(J& dst,std::string_view key,T& value){dst.AddMember(rapidjson::StringRef(key.data()),value,a);}'
            'template<class T> void put(J& dst,std::string_view key,std::vector<T>& value){J arr(kArrayType);'
            'for(const auto& item:value)arr.PushBack(item,a);dst.AddMember(rapidjson::StringRef(key.data()),arr,a);}'
            'void put(J& dst,std::string_view key,std::string& value){dst.AddMember(rapidjson::StringRef(key.data()),J().SetString(value.c_str(),a),a);}'
            'template<class T> void relay(J& dst,std::string_view key,T& value){put(dst,key,value);}'
            'J encode(int count,std::string title,std::vector<int> values){J j;'
            'relay(j,"total",count);relay(j,"title",title);relay(j,"values",values);return j;}')
        f=self.function(r,'encode');mappings=f['field_mappings']
        paths={tuple(m['wire_path']) for m in mappings}
        self.assertEqual(paths,{('total',),('title',),('values',),('values','*')})
        self.assertTrue(all(m['source']['parameter']==0 for m in mappings if m['wire_path']==['total']))
        self.assertLess(len(mappings),10)
        self.assertFalse(any(c.get('kind')=='unresolved_overload_requirement' for m in mappings for c in m['conditions']))

    def test_application_renaming_retains_mechanism(self):
        s='using J=rapidjson::Value;struct R{int count;};J encode(const R& r){J j;j.AddMember("wire",r.count,a);return j;}'
        for a,b in [('J','DocumentAlias'),('R','Payload'),('count','quantity'),('encode','serialize'),('r','input'),('j','output'),('wire','external')]:s=re.sub(r'\b'+a+r'\b',b,s)
        m,=self.function(self.analyze(s),'serialize')['field_mappings']
        self.assertEqual(m['wire_path'],['external']);self.assertEqual(m['source']['selectors'],['member:quantity'])

    def test_optional_field_and_type_declaring_scope_are_preserved(self):
        r=self.analyze('using J=rapidjson::Value;namespace Model{struct Detail{unsigned int code;};'
            'struct Base{std::optional<Detail> detail;};struct R:Base{};}'
            'J encode(const Model::R& r){J j;j.AddMember("first",r.detail.value().code,a);'
            'j.AddMember("second",r.detail->code,a);return j;}')
        mappings=self.function(r,'encode')['field_mappings'];self.assertEqual(len(mappings),2)
        for m in mappings:
            self.assertEqual(m['source']['selectors'],['member:detail','member:code'])
            self.assertEqual(m['source']['value_type'],'unsigned int')

    def test_same_wire_key_in_opposite_branches_keeps_distinct_sources(self):
        r=self.analyze('using J=rapidjson::Value;J encode(bool mode,int x,int y){J j;'
            'if(mode)j.AddMember("n",x,a);else j.AddMember("n",y,a);return j;}')
        mappings=self.function(r,'encode')['field_mappings'];self.assertEqual(len(mappings),2)
        self.assertEqual({(m['source']['parameter'],next(c['when'] for c in m['conditions'] if c.get('kind')=='branch')) for m in mappings},{(1,True),(2,False)})

    def test_budget_exhaustion_remains_visible_when_return_is_unresolved(self):
        d=DataExtractor({'a.cpp':b'using J=rapidjson::Value;J encode(int x){J j;j.AddMember("n",x,a);return j;}'},self.parser)
        r=Serialization(d,max_steps=4).build()
        f=self.function(r,'encode');self.assertTrue(any(g['kind']=='analysis_budget_exhausted' for g in f['gaps']))
