import unittest
from tests import test_cpp_data as fixtures
from adapters.cpp_data import DataExtractor
from adapters.cpp_source_conditions import extract_conditions
from adapters.data_graph import augment
from adapters.sqlite_fact_graph import validate_graph


class CppMemberDeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CppDataTests.setUpClass();cls.parser=fixtures.CppDataTests.parser

    def extractor(self,source=None,files=None):
        return DataExtractor({p:s.encode() for p,s in (files or {'src/choices.cpp':source}).items()},self.parser)

    def field(self,data,name,owner='Options',path='src/choices.cpp'):return data.field(name,owner,path=path)

    def test_if_else_declarations_keep_both_initializers_and_opposite_guards(self):
        data=self.extractor('''struct Options{
#ifdef NARROW_HOST
 int value=1;
#else
 int value=2;
#endif
};''')
        field=self.field(data,'value');self.assertEqual(field['type'],'int');self.assertEqual(len(field['declarations']),2)
        self.assertEqual([d['default_expression'] for d in field['declarations']],['1','2'])
        self.assertEqual([[(g['expression'],g['when']) for g in d['conditions']] for d in field['declarations']],
            [[('defined(NARROW_HOST)',True)],[('defined(NARROW_HOST)',False)]])

    def test_elif_else_nested_and_ifndef_retain_all_enclosing_choices(self):
        data=self.extractor('''struct Options{
#ifndef FIRST
#if SECOND
 int value=1;
#elif THIRD
 int value=2;
#else
 int value=3;
#endif
#endif
};''')
        declarations=self.field(data,'value')['declarations']
        self.assertEqual([[(g['expression'],g['when']) for g in d['conditions']] for d in declarations],
            [[('defined(FIRST)',False),('SECOND',True)],
             [('defined(FIRST)',False),('SECOND',False),('THIRD',True)],
             [('defined(FIRST)',False),('SECOND',False),('THIRD',False)]])

    def test_type_changes_are_explicit_and_never_selected_by_source_order(self):
        data=self.extractor('''struct A{int x;};struct B{int x;};struct Options{
#if FLAG
A value;
#else
B value;
#endif
};''')
        field=self.field(data,'value');self.assertEqual(field['type'],'');self.assertEqual(field['type_status'],'configuration_dependent')
        self.assertTrue(any(d['reason']=='member_type_selection_requires_configuration' and d['required'] for d in data.diagnostics))

    def test_pointer_and_value_declarators_do_not_become_the_same_type(self):
        data=self.extractor('''struct Target{};struct Options{
#if FLAG
Target *value;
#else
Target value;
#endif
};''')
        self.assertEqual(self.field(data,'value')['type'],'')

    def test_nested_class_fields_and_function_prototypes_are_not_outer_data(self):
        data=self.extractor('struct Options{struct Inner{int inner;};int outer;bool run() const;void (*callback)(int);};')
        self.assertIsNone(self.field(data,'inner'));self.assertIsNone(self.field(data,'run'))
        self.assertIsNotNone(self.field(data,'callback'));self.assertIsNotNone(self.field(data,'inner','Options::Inner'))

    def test_multiple_declarators_have_distinct_ids_and_defaults(self):
        data=self.extractor('struct Options{int first=1,second=2;};')
        first=self.field(data,'first');second=self.field(data,'second')
        self.assertNotEqual(first['id'],second['id']);self.assertEqual(first['declarations'][0]['default_expression'],'1')
        self.assertEqual(second['declarations'][0]['default_expression'],'2')

    def test_function_returning_a_pointer_is_a_method_while_pointer_storage_is_a_member(self):
        data=self.extractor('struct Options{void (*callback)(int);void (*get())(int);};')
        self.assertIsNotNone(self.field(data,'callback'));self.assertIsNone(self.field(data,'get'))

    def test_same_named_classes_in_separate_translation_units_keep_their_members(self):
        files={'left.cpp':'struct Options{int field;};void left(){Options x;x.field=1;}',
            'right.cpp':'struct Options{bool field;};void right(){Options x;x.field=false;}'}
        data=self.extractor(files=files)
        self.assertEqual(data.field('field','Options',path='left.cpp')['type'],'int')
        self.assertEqual(data.field('field','Options',path='right.cpp')['type'],'bool')
        self.assertIsNone(data.field('field','Options'))
        self.assertTrue(any(d['reason']=='member_owner_definition_not_selected' for d in data.diagnostics))

    def test_member_write_retains_a_disjunction_of_declaration_conditions(self):
        data=self.extractor('''struct Options{
#if FLAG
int field;
#else
int field;
#endif
};void update(Options& x){x.field=1;}''')
        graph=data.build();effect=next(e for e in graph['data']['member_effects']['effects'] if e['role']=='write')
        selected=next(c for c in effect['conditions'] if c['kind']=='member_declaration_selected')
        self.assertEqual(len(selected['alternatives']),2)
        self.assertEqual({a['conditions'][0]['when'] for a in selected['alternatives']},{True,False})

    def test_conditional_const_bool_is_not_resolved_from_the_first_initializer(self):
        data=self.extractor('''struct Options{
#if FLAG
const bool enabled=true;
#else
const bool enabled=false;
#endif
bool run(){if(enabled){return true;}return false;}};''')
        result=extract_conditions(data);self.assertEqual(len(result['constants']),1)
        self.assertEqual(result['constants'][0]['status'],'configuration_dependent');self.assertIsNone(result['constants'][0]['value'])
        self.assertTrue(all(g['value'] is None for g in result['guards']))

    def test_all_declarations_are_in_the_portable_graph_with_source_edges(self):
        data=self.extractor('''struct Options{
#if FLAG
int unused=1;
#else
int unused=2;
#endif
};''');cpp=data.build()
        base={**cpp['facts'],'source_commit':'authored-conditional-members','snapshot':'authored-conditional-members',
            'input_paths':['src/choices.cpp'],'extractors':{},'provenance':{}}
        graph=augment(base,cpp,base['input_paths']);validate_graph(graph)
        self.assertEqual(len([n for n in graph['nodes'] if n['kind']=='cpp_member_declaration']),2)
        self.assertEqual(len([e for e in graph['edges'] if e['kind']=='DECLARES_SOURCE_MEMBER']),1)
        self.assertEqual(len([e for e in graph['edges'] if e['kind']=='HAS_MEMBER_DECLARATION']),2)

    def test_anonymous_and_union_scopes_surface_as_required_gaps(self):
        data=self.extractor('struct Options{union{int value;float other;} choice;struct{int hidden;} anonymous;};')
        self.assertTrue(any(d['reason']=='anonymous_or_union_member_scope_not_expanded' and d['required'] for d in data.diagnostics))

    def test_use_sites_inside_else_keep_the_negative_preprocessor_condition(self):
        data=self.extractor('''struct Options{int value;void set(){
#ifdef MODE
value=1;
#else
value=2;
#endif
}};''')
        writes=[e for e in data.build()['data']['member_effects']['effects'] if e['role']=='write']
        self.assertEqual([[(c['expression'],c['when']) for c in w['conditions'] if c['kind']=='preprocessor'] for w in writes],
            [[('defined(MODE)',True)],[('defined(MODE)',False)]])


if __name__=='__main__':unittest.main()
