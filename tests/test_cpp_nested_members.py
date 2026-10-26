import unittest
from tests import test_cpp_data as data_tests


class CppNestedMemberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):data_tests.CppDataTests.setUpClass();cls.parser=data_tests.CppDataTests.parser

    def effects(self,source):
        from adapters.cpp_data import analyze_data
        graph=analyze_data({'src/options.cpp':source.encode()},self.parser)
        data=graph['data']['member_effects'];members={m['id']:m for m in data['members']}
        return [(members[e['member']],e) for e in data['effects']]

    def writes(self,source):return [(m,e) for m,e in self.effects(source) if e['role']=='write']

    def test_nested_member_assignment_uses_the_member_receiver_type(self):
        writes=self.writes('struct Options{int endpoint;};struct Reader{Options options;void assign(int value){options.endpoint=value;}};')
        self.assertEqual([(m['owner'],m['name']) for m,e in writes],[('Options','endpoint')])
        self.assertEqual(writes[0][1]['receiver'],'options');self.assertEqual(writes[0][1]['value']['expression'],'value')

    def test_multiple_member_levels_and_inheritance_are_resolved(self):
        source='struct Base{int endpoint;};struct Options:Base{};struct State{Options options;};struct Reader{State state;void assign(int x){state.options.endpoint=x;}};'
        self.assertEqual([(m['owner'],m['name']) for m,e in self.writes(source)],[('Base','endpoint')])

    def test_raw_and_standard_pointer_members_use_arrow_dereference(self):
        for spelling in ('Options*','std::unique_ptr<Options>','std::shared_ptr<Options>'):
            source='struct Options{int endpoint;};struct Reader{'+spelling+' options;void assign(int x){options->endpoint=x;}};'
            self.assertEqual([(m['owner'],m['name']) for m,e in self.writes(source)],[('Options','endpoint')])

    def test_borrowed_getter_type_enables_field_access_without_inventing_object_identity(self):
        source='struct Options{int endpoint;};struct Reader{Options options;Options& get(){return options;}void assign(int x){get().endpoint=x;}};'
        writes=self.writes(source);self.assertEqual([(m['owner'],m['name']) for m,e in writes],[('Options','endpoint')])
        self.assertEqual(writes[0][1]['instance_identity'],'unresolved');self.assertEqual(writes[0][1]['status'],'source_member_effect_candidate')

    def test_local_shadow_and_same_member_names_keep_declared_class_owners(self):
        source='struct A{int endpoint;};struct B{int endpoint;};struct Reader{A options;void assign(int x){B options;options.endpoint=x;}void other(int x){this->options.endpoint=x;}};'
        self.assertEqual({(m['owner'],m['name']) for m,e in self.writes(source)},{('A','endpoint'),('B','endpoint')})

    def test_unknown_receiver_does_not_borrow_an_implicit_member_of_the_same_name(self):
        source='struct Reader{int endpoint;void assign(int x){auto other=unknown();other.endpoint=x;}};'
        self.assertEqual(self.writes(source),[])

    def test_auto_member_self_update_retains_the_type_inference_cycle_guard(self):
        from adapters.cpp_data import DataExtractor
        from adapters.cpp_member_effects import extract_member_effects
        source='''#include <vector>
struct Node{std::vector<Node> children;int value;};
void update(std::vector<Node>& roots){auto current=roots[0];current=current.children[0];current.value=1;}
'''
        data=DataExtractor({'src/indirect.cpp':source.encode()},self.parser)
        extract_member_effects(data)
        self.assertTrue(any(d.get('reason')=='recursive_initializer' and d['required'] for d in data.diagnostics))


if __name__=='__main__':unittest.main()
