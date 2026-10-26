import unittest

from adapters.cpp_data import DataExtractor
from adapters.cpp_protocol import ProtocolExtractor
from adapters.cpp_string_switches import augment
from adapters.cpp_argv_origins import augment as argv_origins
from adapters.data_graph import augment as data_graph
from adapters.sqlite_fact_graph import validate_graph
from tests import test_cpp_data as fixtures


SOURCE='''#include <string>
struct Options {bool strict=true;};
struct Reader {
 const std::string flag="--relaxed";
 Options options;
 bool decode(const std::string& word){
  if(word==flag){options.strict=false;return true;}
  return false;
 }
};
int main(int count,char **incoming){Reader reader;reader.decode(std::string(incoming[1]));return 0;}
'''


class CppStringSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CppDataTests.setUpClass();cls.parser=fixtures.CppDataTests.parser

    def graph(self,source=SOURCE,files=None,argv=False):
        sources={p:s.encode() for p,s in (files or {'src/any.cpp':source}).items()};data=DataExtractor(sources,self.parser)
        cpp=data.build();base={**cpp['facts'],'source_commit':'authored-string-switch','snapshot':'authored-string-switch',
            'input_paths':list(sources),'extractors':{},'provenance':{}}
        graph=data_graph(base,cpp,list(sources))
        protocol=ProtocolExtractor({},None,extractor=data.x,facts=data.facts,value_types=data.types)
        graph=augment(graph,data,protocol)
        return argv_origins(graph,data,protocol) if argv else graph

    def decoders(self,g):return [n for n in g['nodes'] if n['kind']=='string_key_decoder']

    def test_literal_switch_reaches_typed_member_write_and_declaration(self):
        g=self.graph();validate_graph(g);decoder,=self.decoders(g);nodes={n['id']:n for n in g['nodes']}
        self.assertEqual(decoder['key'],'--relaxed');self.assertEqual(decoder['match_mode'],'string_equality')
        self.assertEqual(decoder['targets'],[]);effect,=decoder['controlled_member_effects'];write=nodes[effect]
        self.assertEqual(write['value']['expression'],'false');self.assertEqual(nodes[write['member']]['name'],'Options::strict')
        self.assertEqual(write['instance_identity'],'unresolved')
        self.assertTrue(any(e['source']==decoder['id'] and e['target']==effect and e['kind']=='STRING_BRANCH_MEMBER_WRITE_CANDIDATE' for e in g['edges']))
        self.assertTrue(any(e['source']==effect and e['target']==write['member'] and e['kind']=='WRITES_SOURCE_MEMBER_CANDIDATE' for e in g['edges']))

    def test_commuted_equality_and_inequality_else_keep_the_selected_branch(self):
        for expr,body in [('flag==word','options.strict=false;return true;'),('word!=flag','return false;}else{options.strict=false;return true;')]:
            g=self.graph(SOURCE.replace('word==flag',expr).replace('options.strict=false;return true;',body))
            decoder,=self.decoders(g);self.assertEqual(len(decoder['controlled_member_effects']),1)
            if expr=='word!=flag':
                self.assertEqual(decoder['equality_branch'],'alternative')
                self.assertTrue(any(c.get('kind')=='branch' and c['when'] is False for c in decoder['conditions']))

    def test_other_class_same_field_and_same_literal_stay_distinct(self):
        other=SOURCE.replace('Reader','Second').replace('Options','Other').replace('main','helper')
        g=self.graph(files={'one/a.cpp':SOURCE,'two/b.cpp':other});validate_graph(g)
        decoders=self.decoders(g);self.assertEqual(len(decoders),2)
        self.assertNotEqual(decoders[0]['source_symbol'],decoders[1]['source_symbol'])
        nodes={n['id']:n for n in g['nodes']}
        self.assertEqual({nodes[nodes[d['controlled_member_effects'][0]]['member']]['name'] for d in decoders},{'Options::strict','Other::strict'})

    def test_empty_comparison_literal_is_preserved_as_a_source_branch(self):
        g=self.graph(SOURCE.replace('word==flag','word==""'));validate_graph(g)
        decoder,=self.decoders(g);self.assertEqual(decoder['key'],'');self.assertTrue(decoder['controlled_member_effects'])

    def test_custom_string_shadowed_key_and_constructor_override_do_not_invent_a_literal(self):
        self.assertEqual(self.decoders(self.graph(SOURCE.replace('std::string','Custom'))),[])
        for source in [SOURCE.replace('const std::string& word','const std::string& word,const std::string& flag'),
            SOURCE.replace('Options options;','Options options; Reader():flag("--actual"){}')]:
            g=self.graph(source);self.assertEqual(self.decoders(g),[])
            self.assertTrue(any(d.get('reason')=='string_equality_input_or_key_unresolved' for d in g['diagnostics']))

    def test_nested_lambda_write_is_not_an_executed_branch_write(self):
        source=SOURCE.replace('options.strict=false;','auto later=[this](){options.strict=false;};')
        decoder,=self.decoders(self.graph(source));self.assertEqual(decoder['controlled_member_effects'],[])

    def test_controlled_calls_and_nested_write_guards_are_retained(self):
        source=SOURCE.replace('options.strict=false;','if(word.empty()){options.strict=false;}notify();').replace('Options options;','Options options; void notify(){}')
        g=self.graph(source);decoder,=self.decoders(g);self.assertTrue(decoder['controlled_calls'])
        write=next(n for n in g['nodes'] if n['id']==decoder['controlled_member_effects'][0])
        self.assertTrue(any('empty' in c.get('expression','') for c in write['conditions']))

    def test_compound_and_fallthrough_conditions_report_the_exact_gap(self):
        for condition,reason in [('word==flag || word.empty()','compound_string_condition_not_expanded'),
            ('word!=flag','equality_branch_has_no_explicit_body')]:
            g=self.graph(SOURCE.replace('word==flag',condition));self.assertEqual(self.decoders(g),[])
            self.assertTrue(any(d.get('reason')==reason and d['required'] for d in g['diagnostics']))

    def test_argv_origin_uses_the_comparison_reference_and_keeps_entry_identity(self):
        g=self.graph(argv=True);validate_graph(g)
        decoder,=self.decoders(g);bindings=[n for n in g['nodes'] if n['kind']=='cpp_argv_decoder_binding']
        self.assertEqual(len(bindings),1);binding=bindings[0];self.assertTrue(binding['origin_complete'],binding)
        self.assertEqual(binding['decoder'],decoder['id']);self.assertEqual(binding['value']['gaps'],[])
        self.assertTrue(all(o['entry']==binding['entry'] for o in binding['value']['origins']))

    def test_duplicate_switch_projection_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'already present'):augment(self.graph(),None,None)


if __name__=='__main__':unittest.main()
