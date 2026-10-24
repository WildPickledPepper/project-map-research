import unittest
import tests.test_cpp_data as data_tests
from adapters.cpp_data import analyze_data


class ValueTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data_tests.CppDataTests.setUpClass();cls.parser=data_tests.CppDataTests.parser

    def graph(self,source):
        return analyze_data({'a.cpp':source.encode()},self.parser)

    @staticmethod
    def call(graph,spelling):
        return next(c for s in graph['data']['summaries'] for c in s['calls'] if c['expression']==spelling)

    def targets(self,graph,spelling):
        nodes={n['id']:n for n in graph['facts']['nodes']}
        return [nodes[t]['name'] for t in self.call(graph,spelling)['targets']]

    def test_map_iterator_to_nested_template_method_and_substituted_return(self):
        g=self.graph('struct Item{void work(){}};template<typename V>struct Holder{std::shared_ptr<V> take(){return {};}};struct M{std::map<int,std::shared_ptr<Holder<Item>>> data;void use(int key){auto it=data.find(key);auto ptr=it->second->take();ptr->work();}};')
        self.assertEqual(self.targets(g,'it->second->take()'),['Holder::take'])
        self.assertEqual(self.targets(g,'ptr->work()'),['Item::work'])
        binding=self.call(g,'it->second->take()')['resolution']['candidates'][0]['template_bindings']['V']
        self.assertEqual(binding['names'],['Item'])

    def test_find_if_preserves_iterator_type(self):
        g=self.graph('struct Item{void work(){}};struct M{std::map<int,std::unique_ptr<Item>> data;void use(){auto it=std::find_if(data.begin(),data.end(),[](auto& x){return true;});it->second->work();}};')
        self.assertEqual(self.targets(g,'it->second->work()'),['Item::work'])

    def test_unknown_unconditional_reassignment_does_not_restore_old_iterator(self):
        g=self.graph('struct Item{void work(){}};struct M{std::map<int,std::shared_ptr<Item>> data;void use(int key){auto it=data.find(key);it=external();it->second->work();}};')
        self.assertEqual(self.targets(g,'it->second->work()'),[])
        self.assertIn('receiver_type_unknown',self.call(g,'it->second->work()')['resolution']['gaps'])

    def test_conditional_iterator_sources_keep_both_types_and_unknown_branch(self):
        g=self.graph('struct One{void work(){}};struct Two{void work(){}};struct M{std::map<int,One*> first;std::map<int,Two*> second;void use(int k,bool b){auto it=first.find(k);if(b){it=second.find(k);}if(external()){it=other();}it->second->work();}};')
        self.assertEqual(set(self.targets(g,'it->second->work()')),{'One::work','Two::work'})
        self.assertIn('receiver_type_unknown',self.call(g,'it->second->work()')['resolution']['gaps'])

    def test_direct_map_value_lookup_and_smart_pointer_get(self):
        g=self.graph('struct Thing{void work(){}};struct M{std::map<int,std::shared_ptr<Thing>> entries;void use(){entries.at(1)->work();entries[2].get()->work();}};')
        self.assertEqual(self.targets(g,'entries.at(1)->work()'),['Thing::work'])
        self.assertEqual(self.targets(g,'entries[2].get()->work()'),['Thing::work'])

    def test_project_identifiers_and_template_parameters_can_be_renamed(self):
        source='struct X{void go(){}};template<typename T>struct Pool{T* open(){return nullptr;}};struct M{std::map<int,Pool<X>*> table;void use(){auto it=table.find(1);it->second->open()->go();}};'
        for a,b in [('X','Payload'),('T','Element'),('Pool','Bucket'),('open','acquire'),('table','registry'),('go','act')]:
            import re
            source=re.sub(r'\b'+a+r'\b',b,source)
        g=self.graph(source);self.assertEqual(self.targets(g,'it->second->acquire()->act()'),['Payload::act'])

    def test_generic_body_is_not_chosen_for_an_unresolved_specialization(self):
        g=self.graph('template<typename T>struct Box{void open(){}};template<>struct Box<int>{void close(){}};struct M{std::map<int,Box<int>*> m;void use(){auto it=m.find(1);it->second->open();}};')
        self.assertEqual(self.targets(g,'it->second->open()'),[])

    def test_same_method_on_unrelated_class_is_not_a_target(self):
        g=self.graph('struct A{void act(){}};struct B{void act(){}};struct M{std::map<int,A*> table;void use(){auto it=table.find(1);it->second->act();}};')
        self.assertEqual(self.targets(g,'it->second->act()'),['A::act'])

    def test_structured_map_range_and_sequence_range_resolve_element_types(self):
        g=self.graph('struct Item{void work(){}};struct M{std::map<int,std::unique_ptr<Item>> data;std::vector<Item*> values;void use(){for(const auto &[key,item]:data){item->work();}for(auto value:values){value->work();}}};')
        self.assertEqual(self.targets(g,'item->work()'),['Item::work'])
        self.assertEqual(self.targets(g,'value->work()'),['Item::work'])

    def test_reassigned_range_binding_keeps_unknown_receiver(self):
        g=self.graph('struct Item{void work(){}};struct M{std::vector<Item*> data;void use(){for(auto item:data){item=external();item->work();}}};')
        self.assertEqual(self.targets(g,'item->work()'),[])
