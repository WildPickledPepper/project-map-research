import unittest
import tests.test_cpp_data as data_tests
from adapters.cpp_data import analyze_data
from adapters.data_graph import augment,RESOURCE_IMPACT_KINDS,INSTANCE_IMPACT_KINDS
from adapters.data_queries import explain_receiver
from adapters.fact_queries import find_path
from adapters.sqlite_fact_graph import _prepare


class DataGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data_tests.CppDataTests.setUpClass();cls.parser=data_tests.CppDataTests.parser

    def graph(self,source):
        cpp=analyze_data({'a.cpp':source.encode()},self.parser)
        base={'schema_version':1,'snapshot':'source:p2','source_commit':'source','input_paths':['a.cpp'],
              'nodes':[],'edges':[],'coverage':[{'path':'a.cpp','status':'parsed'}],'extractors':{},'provenance':{},'diagnostics':[]}
        graph=augment(base,cpp,['a.cpp']);_prepare(graph);return graph

    @staticmethod
    def symbol(graph,name):return next(n['id'] for n in graph['nodes'] if n['kind']=='callable' and n['name']==name and n['definition'])

    def test_field_effect_nodes_have_scoped_location_and_source_evidence(self):
        g=self.graph('struct R{int value;};void fill(R& out){out.value=1;}')
        write,=[n for n in g['nodes'] if n['kind']=='field_write']
        relation,=[e for e in g['edges'] if e['source']==write['id'] and e['kind']=='WRITES_OBJECT_PATH']
        location=next(n for n in g['nodes'] if n['id']==relation['target'])
        self.assertEqual(location['selectors'],['member:value'])
        self.assertTrue(relation['evidence']);self.assertEqual(g['snapshot'],'source:p3-data-v3')

    def test_shared_state_forward_reverse_and_unrelated_member_isolation(self):
        g=self.graph('struct A{std::map<int,int> state;void write(int key){state[key]=7;}int read(int key){return state.at(key);}};struct B{std::map<int,int> state;int read(int key){return state.at(key);}};')
        a,b,c=[self.symbol(g,n) for n in ['A::write','A::read','B::read']]
        self.assertTrue(find_path(g,a,b,RESOURCE_IMPACT_KINDS)['found'])
        self.assertTrue(find_path(g,b,a,RESOURCE_IMPACT_KINDS,reverse=True)['found'])
        self.assertFalse(find_path(g,a,c,RESOURCE_IMPACT_KINDS)['found'])

    def test_known_distinct_keys_do_not_share_an_impact_path(self):
        g=self.graph('struct A{std::map<int,int> state;void write(){state[1]=7;}int read(){return state.at(2);}};')
        self.assertFalse(find_path(g,self.symbol(g,'A::write'),self.symbol(g,'A::read'),RESOURCE_IMPACT_KINDS)['found'])

    def test_factory_explanation_keeps_source_candidates_and_resource_keys(self):
        g=self.graph('struct Base{virtual void run()=0;};struct One:Base{void run()override{}};struct Two:Base{void run()override{}};struct M{std::map<int,std::shared_ptr<Base>> slots;void build(){slots.emplace(1,std::make_shared<One>());slots.emplace(2,std::make_shared<Two>());}std::shared_ptr<Base> get(int key){return slots.at(key);}void use(int key){auto p=this->get(key);p->run();}};')
        call=next(c for s in g['data']['summaries'] for c in s['calls'] if c['expression']=='p->run()')
        result=explain_receiver(g,call['call_site'])
        self.assertEqual(len(result['factory_candidates']),2)
        self.assertEqual({n['name'] for n in result['implementations']},{'One::run','Two::run'})
        self.assertTrue(all(n['factory_support'] for n in result['implementations']))
        self.assertEqual(result['runtime_selection'],'unknown')
        self.assertTrue(explain_receiver(g,call['call_site'],max_functions=0)['truncated'])

    def test_removing_writer_removes_influence_edges_on_rebuild(self):
        g=self.graph('struct A{std::map<int,int> state;void write(){}int read(){return state.at(1);}};')
        self.assertFalse(any(e['kind']=='POTENTIALLY_READ_BY' for e in g['edges']))

    def test_instance_impact_rejects_two_distinct_local_receivers(self):
        from tests.test_cpp_instances import BASE
        g=self.graph(BASE+'void use(){Cache a;Cache b;a.put(1);b.read(1);}')
        self.assertFalse(find_path(g,self.symbol(g,'Cache::put'),self.symbol(g,'Cache::read'),INSTANCE_IMPACT_KINDS)['found'])

    def test_instance_impact_connects_a_shared_static_receiver(self):
        from tests.test_cpp_instances import BASE
        g=self.graph(BASE+'void use(){Cache::owner().put(1);Cache::owner().wrapper(1);}')
        path=find_path(g,self.symbol(g,'Cache::put'),self.symbol(g,'Cache::read'),INSTANCE_IMPACT_KINDS)
        self.assertTrue(path['found']);self.assertTrue(any(e['kind']=='INSTANCE_VALUE_READ_BY' for e in path['edges']))
        self.assertTrue(all('process_and_link_image' in e['conditions'] for e in path['edges']))
