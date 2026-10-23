import os
import unittest
import tree_sitter_language_pack as pack
from adapters.cpp_data import analyze_data

if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
    pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))


class CppDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parser=pack.get_parser('cpp')

    def data(self,source=None,files=None):
        return analyze_data({p:s.encode() for p,s in (files or {'a.cpp':source}).items()},self.parser)

    def test_scoped_read_write_and_key_parameter_sources(self):
        g=self.data('struct S {std::map<int,int> cache;void put(int key,int value){cache[key]=value;}int read(int key){return cache[key];}};')
        storage,=g['data']['storages'];writer,reader=g['data']['accesses']
        self.assertEqual((writer['role'],reader['role']),('write','read'))
        self.assertEqual(writer['storage'],reader['storage']);self.assertEqual(writer['storage'],storage['id'])
        self.assertEqual(writer['value']['binding']['type'],'int')
        self.assertEqual(reader['alias_status'],'candidate')
        self.assertEqual(reader['runtime_key_equality'],'not_observed')

    def test_same_field_name_in_different_classes_or_anonymous_units_stays_separate(self):
        code='struct S {std::map<int,int> cache;int read(int key){return cache[key];}};'
        for files in [{'a.cpp':'namespace a {'+code+'} namespace b {'+code+'}'},
                      {'a.cpp':'namespace {'+code+'}','b.cpp':'namespace {'+code+'}'}]:
            g=self.data(files=files);accesses=g['data']['accesses']
            self.assertEqual(len({a['storage'] for a in accesses}),2)

    def test_local_shadow_and_parameter_shadow_do_not_read_member(self):
        g=self.data('struct S {std::map<int,int> cache;int local(int k){std::map<int,int> cache;return cache[k];}int param(std::map<int,int>& cache){return cache[1];}int own(){return this->cache[1];}};')
        accesses=g['data']['accesses'];self.assertEqual(len(accesses),1)
        self.assertEqual(accesses[0]['key']['expression'],'1')

    def test_conditional_receiver_retains_argument_values_and_branch_direction(self):
        g=self.data('struct B{void act();};struct S{B* left(int);B* right(int);void run(bool mode,int key){auto value=mode?left(key):right(3);value->act();} B* left(int key){return nullptr;} B* right(int key){return nullptr;}};')
        selection,=g['data']['selections'];yes,no=selection['value']['branches']
        self.assertTrue(yes['when']);self.assertFalse(no['when'])
        self.assertEqual(yes['value']['arguments'][0]['binding']['type'],'int')
        self.assertEqual(no['value']['arguments'][0]['expression'],'3')
        self.assertTrue(yes['value']['targets'] and no['value']['targets'])
        summary=next(s for s in g['data']['summaries'] if s['name']=='S::run')
        call=next(c for c in summary['calls'] if c['expression']=='value->act()')
        self.assertEqual(call['receiver']['initializer']['kind'],'conditional_expression')
        self.assertIn(call['call_site'],{n['id'] for n in g['facts']['nodes']})

    def test_reassignment_drops_stale_receiver_initialization(self):
        g=self.data('struct B{void act();};struct S{B* left();void run(){auto v=left();v=unknown();v->act();}};')
        call=next(c for s in g['data']['summaries'] for c in s['calls'] if c['expression']=='v->act()')
        self.assertEqual(call['receiver']['kind'],'unknown');self.assertNotIn('initializer',call['receiver'])

    def test_factory_callback_allocations_keep_switch_and_enclosing_factory(self):
        g=self.data('struct X{};struct Y{};template<typename T>struct Pool{};struct S{void setup(int kind){switch(kind){case 1: auto x=std::make_shared<Pool<X>>([](){return new X();});break;default: auto y=std::make_shared<Pool<Y>>([](){return new Y();});}}};')
        allocations=g['data']['allocations'];self.assertEqual(len(allocations),4)
        callbacks=[a for a in allocations if a['callback']];self.assertEqual(len(callbacks),2)
        self.assertEqual({a['type_spelling'] for a in callbacks},{'X','Y'})
        self.assertTrue(all(a['enclosing_allocation'] for a in callbacks))
        self.assertEqual({a['conditions'][0]['label'] for a in callbacks},{'1','default'})
        self.assertTrue(all(a['conditions'][0]['fallthrough']=='not_evaluated' for a in callbacks))

    def test_else_polarity_and_deletion_are_preserved(self):
        source='struct S{std::map<int,int> map;void run(bool yes){if(yes){map[1]=2;}else{map.erase(1);}}};'
        data=self.data(source)['data'];self.assertEqual([a['conditions'][0]['when'] for a in data['accesses']],[True,False])
        remaining=self.data(source.replace('map[1]=2;',''))['data']['accesses'];self.assertEqual(len(remaining),1)

    def test_project_renaming_does_not_change_mechanism(self):
        source='struct Store{std::map<int,int> states;void set(int key,int value){states[key]=value;}int get(int key){return states[key];}};'
        renamed=source.replace('Store','Things').replace('states','entries').replace('key','index').replace('value','mode').replace('set','put').replace('get','take')
        a,b=self.data(source)['data'],self.data(renamed)['data']
        self.assertEqual([x['role'] for x in a['accesses']],[x['role'] for x in b['accesses']])
        self.assertEqual(b['storages'][0]['owner'],'Things');self.assertEqual(b['accesses'][0]['value']['expression'],'mode')
