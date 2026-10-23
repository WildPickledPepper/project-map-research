import re
import unittest

from adapters.cpp_data import analyze_data
from adapters.field_queries import explain_writes
import tests.test_cpp_data as data_tests


class FieldFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):data_tests.CppDataTests.setUpClass();cls.parser=data_tests.CppDataTests.parser

    def extract(self,source):
        self.graph=analyze_data({'a.cpp':source.encode()},self.parser)
        self.names={n['id']:n['name'] for n in self.graph['facts']['nodes']}
        return self.graph['data']['field_flow']

    def query(self,name):
        uid=next(n['id'] for n in self.graph['facts']['nodes'] if n['kind']=='callable' and n['name']==name and n['definition'])
        return explain_writes(self.graph,uid)

    @staticmethod
    def roots(result):return {r['id']:r for r in result['roots']}

    def test_nested_reference_effects_retain_caller_object_and_conditions(self):
        self.extract('struct Body{std::vector<int> items;};struct Reply{Body payload;};'
            'void append(Body& out,bool enabled){if(enabled)out.items.push_back(3);}'
            'void produce(Body& body,bool mode){if(!mode)return;append(body,mode);}'
            'void entry(Reply& response,bool mode){produce(response.payload,mode);}')
        result=self.query('entry');effect,=result['effects'];root=self.roots(result)[effect['root']]
        self.assertEqual(root['name'],'response');self.assertEqual(effect['selectors'],['member:payload','member:items'])
        self.assertEqual([self.names[c['callee']] for c in effect['call_chain']],['produce','append'])
        self.assertTrue(any(c['kind']=='early_exit_guard' for scope in effect['condition_scopes'] for c in scope['conditions']))
        self.assertFalse(result['truncated']);self.assertEqual(effect['runtime_execution'],'unknown')

    def test_copy_write_does_not_escape_and_reference_alias_does(self):
        self.extract('struct R{int value;};void helper(R& x){auto& alias=x;alias.value=1;auto copy=x;copy.value=2;}'
            'void entry(R& y){helper(y);}')
        effect,=self.query('entry')['effects'];self.assertEqual(effect['selectors'],['member:value'])
        self.assertIn('alias.value=1',effect['evidence'][0]['expression'])

    def test_two_invocations_keep_separate_actual_roots(self):
        self.extract('struct R{int value;};void helper(R& out){out.value=1;}void entry(){R first;R second;helper(first);helper(second);}')
        result=self.query('entry');roots=self.roots(result)
        self.assertEqual({roots[e['root']]['name'] for e in result['effects']},{'first','second'})
        self.assertEqual(len({e['call_chain'][0]['call_site'] for e in result['effects']}),2)

    def test_virtual_output_candidates_bind_the_same_actual_argument(self):
        self.extract('struct R{int first;int second;};struct Base{virtual void run(R&)=0;};'
            'struct One:Base{void run(R& out)override{out.first=1;}};'
            'struct Two:Base{void run(R& out)override{out.second=2;}};'
            'void entry(Base* b,R& result){b->run(result);}')
        result=self.query('entry');self.assertEqual({tuple(e['selectors']) for e in result['effects']},{('member:first',),('member:second',)})
        self.assertEqual({self.names[e['writer']] for e in result['effects']},{'One::run','Two::run'})

    def test_pointer_pointee_write_propagates_but_pointer_rebinding_does_not(self):
        self.extract('struct R{int value;};void fill(R* out){out->value=1;out=nullptr;}'
            'void entry(R& item){fill(&item);}')
        effect,=self.query('entry')['effects'];self.assertEqual(effect['selectors'],['member:value'])

    def test_smart_pointer_reference_alias_retains_owned_value(self):
        self.extract('struct R{int value;};void fill(R& out){out.value=1;}'
            'void entry(){std::unique_ptr<R> ptr=std::make_unique<R>();R& alias=*ptr.get();fill(alias);}')
        result=self.query('entry');effect,=result['effects']
        self.assertEqual(effect['selectors'],['pointee','member:value'])
        self.assertEqual(self.roots(result)[effect['root']]['name'],'ptr')

    def test_shadowed_local_does_not_escape_parameter(self):
        self.extract('struct R{int value;};void fill(R& out){{R out;out.value=1;}}void entry(R& result){fill(result);}')
        self.assertEqual(self.query('entry')['effects'],[])

    def test_lambda_body_is_not_executed_by_declaration(self):
        self.extract('struct R{int value;};void entry(R& result){auto callback=[&](){result.value=1;};}')
        self.assertEqual(self.query('entry')['effects'],[])

    def test_unknown_call_exposes_gap_and_custom_push_back_is_not_std_mutation(self):
        self.extract('struct Custom{void push_back(int);};void unknown(Custom&);void entry(Custom& out){unknown(out);out.push_back(1);}')
        result=self.query('entry');self.assertEqual(result['effects'],[])
        self.assertTrue(any(g['kind']=='call_effects_unresolved' for g in result['gaps']))

    def test_renaming_all_application_identifiers_preserves_substitution(self):
        src='struct R{std::vector<int> entries;};void fill(R& out){out.entries.push_back(1);}void entry(R& item){fill(item);}'
        for a,b in [('R','Result'),('entries','records'),('fill','assemble'),('out','sink'),('entry','perform'),('item','reply')]:src=re.sub(r'\b'+a+r'\b',b,src)
        self.extract(src);result=self.query('perform');effect,=result['effects']
        self.assertEqual(effect['selectors'],['member:records']);self.assertEqual(self.roots(result)[effect['root']]['name'],'reply')

    def test_depth_limit_is_visible(self):
        self.extract('struct R{int value;};void recur(R& out){out.value=1;recur(out);}')
        result=self.query('recur');self.assertTrue(result['truncated'])
        self.assertTrue(any(g['kind']=='recursive_or_depth_limited' for g in result['gaps']))
