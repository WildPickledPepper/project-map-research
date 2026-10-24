import os
from pathlib import Path
import unittest

import tree_sitter_language_pack as pack
from adapters.cpp_facts import analyze

if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
    pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))


class CppFactsTests(unittest.TestCase):
    def test_relative_using_namespace_resolves_from_declaration_scope(self):
        g=self.graph({'a.h':'namespace world { namespace implementation { struct Worker { void act(); }; } using namespace implementation; void run(Worker& value) { value.act(); } }'})
        pairs=self.relations(g,'MEMBER_TARGET_CANDIDATE')
        self.assertEqual([(a['name'],b['name']) for a,b in pairs],[('value.act','world::implementation::Worker::act')])

    def test_nearest_empty_namespace_does_not_fall_back_to_outer_type(self):
        g=self.graph({'a.h':'namespace implementation { struct Worker { void act(); }; } namespace world { namespace implementation {} using namespace implementation; void run(Worker& value) { value.act(); } }'})
        self.assertFalse(self.relations(g,'MEMBER_TARGET_CANDIDATE'))

    def test_explicit_global_using_namespace_keeps_global_target(self):
        g=self.graph({'a.h':'namespace implementation { struct Worker { void act(); }; } namespace world { namespace implementation {struct Worker {void act();};} using namespace ::implementation; void run(Worker& value) { value.act(); } }'})
        self.assertEqual([b['name'] for _,b in self.relations(g,'MEMBER_TARGET_CANDIDATE')],['implementation::Worker::act'])

    @classmethod
    def setUpClass(cls):
        cls.parser=pack.get_parser('cpp')

    def graph(self,files):
        graph=analyze({p:s.encode() for p,s in files.items()},self.parser)
        self.nodes={n['id']:n for n in graph['nodes']}
        return graph

    def relations(self,g,kind):
        return [(self.nodes[e['source']],self.nodes[e['target']]) for e in g['edges'] if e['kind']==kind]

    def test_header_declarations_join_only_matching_overload(self):
        g=self.graph({'a.hpp':'namespace a { class Store { public: bool get(int x); bool get(const char* x); }; }',
                      'a.cpp':'#include "a.hpp"\nnamespace a { bool Store::get(int value) { return true; } bool Store::get(const char* value) { return true; } }'})
        pairs=self.relations(g,'DECLARES_DEFINITION')
        self.assertEqual(len(pairs),2)
        self.assertTrue(all(a['parameters']==b['parameters'] for a,b in pairs))
        self.assertEqual({a['parameters'][0] for a,b in pairs},{'int','constchar*'})

    def test_cross_file_spelling_join_retains_unknown_build_and_type_identity(self):
        graph=self.graph({'one/api.h':'namespace product { int read(int); }',
                          'two/impl.cpp':'namespace product { int read(int value){return value;} }'})
        links=[e for e in graph['edges'] if e['kind']=='DECLARES_DEFINITION']
        self.assertEqual(len(links),1)
        self.assertEqual(links[0]['status'],'candidate')
        self.assertEqual(links[0]['build_linkage'],'not_validated')
        self.assertEqual(links[0]['identity_condition'],'same_program_and_compatible_types')
        self.assertFalse(links[0]['types_checked'])

    def test_fixture_preserves_namespace_and_excludes_pointer_mismatch(self):
        folder=Path(__file__).resolve().parents[1]/'experiments/2026-10-23-p1/fixtures'
        g=self.graph({p.name:p.read_text(encoding='utf-8') for p in folder.glob('contracts.*')})
        pairs=self.relations(g,'MEMBER_TARGET_CANDIDATE')
        at16=[b for a,b in pairs if a['path']=='contracts.h' and a['line']==16]
        at21=[b for a,b in pairs if a['path']=='contracts.h' and a['line']==21]
        self.assertEqual([(n['name'],n['parameters']) for n in at16],[('alpha::Store::query',['int'])])
        self.assertEqual([n['name'] for n in at21],['beta::Store::query'])
        self.assertFalse(any(a['name']=='db.get' and b['name'].endswith('CacheGuard::get') for a,b in pairs))
        get=next(n for n in g['nodes'] if n['kind']=='call_site' and n['name']=='db.get')
        self.assertEqual(get['reason'],'standard_smart_pointer_member_no_project_target')
        owned=[b for a,b in pairs if a['name']=='db.get()->query']
        self.assertEqual([n['name'] for n in owned],['alpha::Store::query'])

    def test_two_implementations_are_candidates_not_runtime_choice(self):
        g=self.graph({'a.h':'namespace a { class Base { public: virtual bool run(int)=0; }; class X: public Base { bool run(int) override; }; class Y: public Base { bool run(int) override; }; }'})
        pairs=self.relations(g,'OVERRIDE_CANDIDATE')
        self.assertEqual({b['name'] for a,b in pairs},{'a::X::run','a::Y::run'})
        self.assertTrue(all(e['status']=='candidate' and e['runtime_selection']=='unknown' for e in g['edges'] if e['kind']=='OVERRIDE_CANDIDATE'))

    def test_const_method_does_not_override_nonconst(self):
        g=self.graph({'a.h':'struct A { virtual void run()=0; }; struct B:A { void run() const; };'})
        self.assertFalse(self.relations(g,'OVERRIDE_CANDIDATE'))

    def test_both_ternary_branches_support_receiver_type(self):
        g=self.graph({'a.h':'namespace a { struct Base { virtual void run()=0; }; struct Manager { static Manager& instance(); std::shared_ptr<Base> left(); std::shared_ptr<Base> right(); }; void use(bool flag) { auto db=flag?Manager::instance().left():Manager::instance().right(); db->run(); } }'})
        targets=[b['name'] for a,b in self.relations(g,'MEMBER_TARGET_CANDIDATE') if a['name']=='db->run']
        self.assertEqual(targets,['a::Base::run'])

    def test_unknown_ternary_branch_does_not_invent_type(self):
        g=self.graph({'a.h':'struct Base { void run(); }; struct M { static Base* known(); }; void use(bool flag) { auto db=flag?M::known():unknown(); db->run(); }'})
        self.assertFalse([b for a,b in self.relations(g,'MEMBER_TARGET_CANDIDATE') if a['name']=='db->run'])

    def test_reassignment_drops_stale_initializer_type(self):
        g=self.graph({'a.h':'struct A { void run(); }; struct B { void run(); }; struct M { static A* a(); static B* b(); }; void use() { auto db=M::a(); db=M::b(); db->run(); }'})
        self.assertFalse([b for a,b in self.relations(g,'MEMBER_TARGET_CANDIDATE') if a['name']=='db->run'])

    def test_local_shadowing_uses_nearest_declaration(self):
        g=self.graph({'a.h':'struct A { void run(); }; struct B { void run(); }; void use(A* db) { { B* db; db->run(); } db->run(); }'})
        pairs=[b['name'] for a,b in self.relations(g,'MEMBER_TARGET_CANDIDATE') if a['name']=='db->run']
        self.assertEqual(pairs,['B::run','A::run'])

    def test_unrelated_class_with_same_method_stays_unconnected(self):
        g=self.graph({'a.h':'struct A { virtual void run()=0; }; struct B { void run(); };'})
        self.assertFalse(self.relations(g,'OVERRIDE_CANDIDATE'))

    def test_unincluded_header_is_not_lexical_type_evidence(self):
        g=self.graph({'a.h':'struct A { void run(); };','a.cpp':'void use(A* db) { db->run(); }'})
        self.assertFalse(self.relations(g,'MEMBER_TARGET_CANDIDATE'))

    def test_renamed_method_works_without_business_names(self):
        g=self.graph({'a.h':'namespace other { struct Port { void dispatch(); }; void use(Port& p){p.dispatch();} }'})
        self.assertEqual([(a['name'],b['name']) for a,b in self.relations(g,'MEMBER_TARGET_CANDIDATE')],[('p.dispatch','other::Port::dispatch')])

    def test_deleted_definition_removes_relation(self):
        g=self.graph({'a.h':'struct A { void run(); };','a.cpp':'#include "a.h"\nvoid A::run() {}'})
        self.assertEqual(len(self.relations(g,'DECLARES_DEFINITION')),1)
        g=self.graph({'a.h':'struct A { void run(); };'})
        self.assertFalse(self.relations(g,'DECLARES_DEFINITION'))

    def test_parse_error_remains_visible(self):
        g=self.graph({'bad.h':'struct Broken { void run( = ;'})
        self.assertTrue(g['diagnostics'])
        self.assertEqual(g['coverage'][0]['status'],'syntax_errors')

    def test_local_using_does_not_leak_into_another_function(self):
        g=self.graph({'a.cpp':'namespace a { struct A { void run(); }; } void f(){using namespace a;} void g(A* x){x->run();}'})
        self.assertFalse(self.relations(g,'MEMBER_TARGET_CANDIDATE'))
        self.assertTrue(any(d['kind']=='local_using_namespace_not_resolved' for d in g['diagnostics']))

    def test_anonymous_namespaces_in_different_files_do_not_join(self):
        g=self.graph({'a.cpp':'namespace { struct A { void run(); }; }',
                      'b.cpp':'namespace { void A::run() {} }'})
        self.assertFalse(self.relations(g,'DECLARES_DEFINITION'))

    def test_missing_and_ambiguous_local_includes_are_reported(self):
        g=self.graph({'a.cpp':'#include "a.h"\n#include "missing.h"\n', 'x/a.h':'struct A {};','y/a.h':'struct A {};'})
        self.assertEqual({d['kind'] for d in g['diagnostics']},{'include_ambiguous','include_outside_input'})


if __name__=='__main__':unittest.main()
