import unittest
import tests.test_cpp_data as data_tests
from adapters.cpp_data import analyze_data


BASE='struct Cache{std::map<int,int> data;static Cache& owner(){static Cache shared;return shared;}void put(int key){data[key]=3;}int read(int key){return data.at(key);}void wrapper(int key){read(key);}};'


class InstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):data_tests.CppDataTests.setUpClass();cls.parser=data_tests.CppDataTests.parser

    def graph(self,source):return analyze_data({'a.cpp':source.encode()},self.parser)

    def test_static_accessor_direct_calls_and_implicit_this_share_identity(self):
        g=self.graph(BASE+'void f(){Cache::owner().put(1);Cache::owner().wrapper(1);}')
        instances=g['data']['instances'];self.assertEqual(len(instances['accessors']),1)
        obj=instances['accessors'][0]['instance'];self.assertEqual({a['instance'] for a in instances['accesses']},{obj})
        names={n['id']:n['name'] for n in g['facts']['nodes']}
        self.assertEqual({names[a['source_symbol']] for a in instances['accesses']},{'Cache::put','Cache::read'})
        self.assertFalse(instances['closed_world'])

    def test_reference_alias_retains_identity_while_value_copy_is_distinct(self):
        g=self.graph(BASE+'void f(){auto& alias=Cache::owner();alias.put(1);auto copied=Cache::owner();copied.read(1);}')
        instances=g['data']['instances'];self.assertEqual({o['kind'] for o in instances['objects']},{'static_local_object','local_object'})
        self.assertEqual(len({a['instance'] for a in instances['accesses']}),2)

    def test_two_local_objects_are_distinct(self):
        g=self.graph(BASE+'void f(){Cache first;Cache second;first.put(1);second.read(1);}')
        self.assertEqual(len({a['instance'] for a in g['data']['instances']['accesses']}),2)

    def test_by_value_accessor_does_not_claim_static_identity(self):
        g=self.graph(BASE.replace('static Cache& owner()','static Cache owner()')+'void f(){Cache::owner().put(1);}')
        self.assertEqual(g['data']['instances']['accessors'],[])
        self.assertEqual(g['data']['instances']['accesses'],[])

    def test_parameter_receiver_is_unknown(self):
        g=self.graph(BASE+'void f(Cache& value){value.put(1);}')
        self.assertEqual(g['data']['instances']['accesses'],[])

    def test_different_static_accessors_do_not_merge_same_class(self):
        src=BASE.replace('void put','static Cache& another(){static Cache separate;return separate;}void put')
        g=self.graph(src+'void f(){Cache::owner().put(1);Cache::another().read(1);}')
        self.assertEqual(len(g['data']['instances']['accessors']),2)
        self.assertEqual(len({a['instance'] for a in g['data']['instances']['accesses']}),2)

    def test_renaming_accessor_object_and_members_keeps_identity_mechanism(self):
        import re
        src=BASE+'void f(){Cache::owner().put(1);Cache::owner().read(1);}'
        for a,b in [('Cache','Registry'),('owner','current'),('shared','globalObject'),('data','items'),('put','update'),('read','lookup')]:src=re.sub(r'\b'+a+r'\b',b,src)
        g=self.graph(src);self.assertEqual(len({a['instance'] for a in g['data']['instances']['accesses']}),1)
