import os
import unittest
import tree_sitter_language_pack as pack

from adapters.cpp_data import DataExtractor
from adapters.cpp_protocol import ProtocolExtractor
from adapters.cpp_string_decoders import augment
from adapters.sqlite_fact_graph import validate_graph


if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
    pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))


SOURCE='''#include <string>
struct Reader {
 const std::string first="--channel=";
 const std::string second="--folder=";
 bool number(const std::string& value){return !value.empty();}
 bool folder(const std::string& value){return !value.empty();}
 bool decode(const std::string& word){
   auto position=word.find(first);
   if(position!=std::string::npos){return number(word.substr(position+first.length()));}
   position=word.find(second);
   if(position!=std::string::npos){return folder(word.substr(position+second.size()));}
   return false;
 }
};'''


class CppStringDecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parser=pack.get_parser('cpp')

    def graph(self,source=SOURCE,files=None):
        sources={p:s.encode() for p,s in (files or {'src/decoder.cpp':source}).items()}
        data=DataExtractor(sources,self.parser)
        protocol=ProtocolExtractor({},None,extractor=data.x,facts=data.facts,value_types=data.types)
        graph={**data.facts,'source_commit':'authored-string-decoder','snapshot':'authored-string-decoder','input_paths':list(sources)}
        return augment(graph,data,protocol)

    def records(self,graph):return [n for n in graph['nodes'] if n['kind']=='string_key_decoder']

    def test_class_constants_sequential_find_and_size_reach_distinct_helpers(self):
        g=self.graph();validate_graph(g);rows=self.records(g);self.assertEqual(len(rows),2)
        nodes={n['id']:n for n in g['nodes']}
        self.assertEqual({r['key']:[nodes[t]['name'] for t in r['targets']] for r in rows},
            {'--channel=':['Reader::number'],'--folder=':['Reader::folder']})
        self.assertTrue(all(r['argv_origin']=='not_bound' and r['runtime_execution']=='not_observed' for r in rows))
        self.assertEqual({r['parameter_index'] for r in rows},{0})
        self.assertFalse(g['cpp_string_decoders']['required_gaps'])

    def test_global_constant_renaming_and_commuted_offset_do_not_need_name_rules(self):
        source='''#include <string>
const std::string OPTION="choice=";
bool next(const std::string& value){return true;}
bool any(const std::string& text){auto where=text.find(OPTION);if(std::string::npos!=where){return next(text.substr(OPTION.size()+where));}return false;}
'''
        rows=self.records(self.graph(source));self.assertEqual(len(rows),1);self.assertEqual(rows[0]['key'],'choice=')

    def test_shadow_parameter_does_not_reuse_global_constant(self):
        source='''#include <string>
const std::string key="--global=";
bool next(const std::string& value){return true;}
bool any(const std::string& text,const std::string& key){auto p=text.find(key);if(p!=std::string::npos){return next(text.substr(p+key.size()));}return false;}
'''
        self.assertEqual(self.records(self.graph(source)),[])

    def test_custom_string_homonym_does_not_become_a_standard_decoder(self):
        source=SOURCE.replace('std::string','Custom')
        self.assertEqual(self.records(self.graph(source)),[])

    def test_different_input_and_different_key_length_do_not_pair(self):
        self.assertEqual(self.records(self.graph(SOURCE.replace('word.substr','other.substr').replace('const std::string& word','const std::string& word,const std::string& other'))),[])
        g=self.graph(SOURCE.replace('position+first.length()','position+second.length()'))
        self.assertEqual([r['key'] for r in self.records(g)],['--folder='])
        self.assertEqual(g['cpp_string_decoders']['required_gaps'],1)

    def test_reassigned_offset_and_mutated_input_inside_guard_remain_gaps(self):
        for effect in ('position=1;','word.clear();'):
            source=SOURCE.replace('const std::string& word','std::string word').replace('{return number(', '{'+effect+'return number(')
            g=self.graph(source);self.assertEqual([r['key'] for r in self.records(g)],['--folder='])
            self.assertTrue(any(d.get('reason')=='input_or_offset_may_change_after_search' and d['required'] for d in g['diagnostics']))

    def test_conditional_search_assignment_is_not_chosen_by_source_order(self):
        source=SOURCE.replace('position=word.find(second);','if(word.empty()){position=word.find(second);}')
        self.assertEqual([r['key'] for r in self.records(self.graph(source))],['--channel='])

    def test_input_mutation_between_search_and_guard_is_a_required_gap(self):
        source=SOURCE.replace('const std::string& word','std::string word').replace('auto position=word.find(first);','auto position=word.find(first);word.clear();')
        g=self.graph(source);self.assertEqual([r['key'] for r in self.records(g)],['--folder='])
        self.assertTrue(any(d.get('reason')=='input_or_offset_may_change_after_search' and d['required'] for d in g['diagnostics']))

    def test_constructor_override_does_not_reuse_default_member_key(self):
        source=SOURCE.replace('bool number(', 'Reader():first("--actual="){}\n bool number(')
        self.assertEqual([r['key'] for r in self.records(self.graph(source))],['--folder='])

    def test_separate_namespaces_and_files_keep_different_decoder_owners(self):
        files={'left/a.cpp':'namespace A{'+SOURCE.replace('#include <string>','')+'}',
            'right/b.cpp':'namespace B{'+SOURCE.replace('#include <string>','')+'}'}
        rows=self.records(self.graph(files=files));self.assertEqual(len(rows),4)
        self.assertEqual(len({r['source_symbol'] for r in rows}),2);self.assertEqual(len({r['id'] for r in rows}),4)

    def test_unsupported_offset_and_duplicate_projection_are_explicit(self):
        g=self.graph(SOURCE.replace('position+first.length()','position+1'))
        self.assertTrue(any(d.get('reason')=='slice_offset_not_proven_as_find_plus_key_length' and d['required'] for d in g['diagnostics']))
        with self.assertRaisesRegex(ValueError,'already present'):augment(g,None,None)


if __name__=='__main__':unittest.main()
