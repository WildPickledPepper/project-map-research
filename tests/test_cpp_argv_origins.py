import os
import unittest
import tree_sitter_language_pack as pack

from adapters.cpp_data import DataExtractor
from adapters.cpp_protocol import ProtocolExtractor
from adapters.cpp_string_decoders import augment as decoders
from adapters.cpp_argv_origins import augment
from adapters.sqlite_fact_graph import validate_graph
from tests.test_cpp_string_decoders import SOURCE

if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
    pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))


VECTOR='''#include <vector>
bool consume(const std::vector<std::string>& inputs){
 for(unsigned int index=1;index<inputs.size();index++){
  std::string token=inputs.at(index);
  Reader reader;reader.decode(token);
 }
 return true;
}
int main(int count,char **words){
 std::vector<std::string> prepared;
 for(int j=0;j<count;j++){prepared.emplace_back(std::string(words[j]));}
 return consume(prepared);
}'''


class CppArgvOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parser=pack.get_parser('cpp')

    def graph(self,source=None,files=None,**budgets):
        sources={p:s.encode() for p,s in (files or {'src/neutral.cpp':source or SOURCE+VECTOR}).items()}
        data=DataExtractor(sources,self.parser)
        protocol=ProtocolExtractor({},None,extractor=data.x,facts=data.facts,value_types=data.types)
        g=decoders({**data.facts,'source_commit':'authored-argv','snapshot':'authored-argv','input_paths':list(sources)},data,protocol)
        return augment(g,data,protocol,**budgets)

    def bindings(self,g):return [n for n in g['nodes'] if n['kind']=='cpp_argv_decoder_binding']

    def test_entry_vector_loop_parameter_and_decode_keep_contextual_argv_origin(self):
        g=self.graph();validate_graph(g);rows=self.bindings(g)
        self.assertEqual(len(rows),2);self.assertTrue(all(r['origin_complete'] for r in rows),rows)
        self.assertTrue(all(len(r['call_stack'])==2 for r in rows))
        self.assertEqual(len({r['argv_source'] for r in rows}),1)
        kinds={s['kind'] for r in rows for s in r['value']['steps']}
        self.assertTrue({'standard_vector_append_word','standard_string_from_argv_word','collection_at','formal_argument_source'}<=kinds)
        self.assertTrue(all(len(o['selectors'])==2 for r in rows for o in r['value']['origins']))
        self.assertEqual(g['cpp_argv_origins']['required_gaps'],0)

    def test_direct_argv_and_array_spelling_do_not_depend_on_parameter_names(self):
        source=SOURCE+'int main(int n,const char *parameters[]){Reader r;r.decode(std::string(parameters[1]));return 0;}'
        rows=self.bindings(self.graph(source));self.assertEqual(len(rows),2);self.assertTrue(all(r['origin_complete'] for r in rows))
        self.assertTrue(all(len(r['value']['origins'][0]['selectors'])==1 for r in rows))

    def test_append_preparation_keeps_operands_conditions_and_prefix_role(self):
        source=SOURCE+VECTOR.replace('Reader reader;', 'if(token.find("=")==std::string::npos){token.append("=").append(inputs.at(++index));}\n Reader reader;')
        rows=self.bindings(self.graph(source));self.assertEqual(len(rows),2);self.assertTrue(all(r['origin_complete'] for r in rows),rows)
        for row in rows:
            ops=[s for s in row['value']['steps'] if s['kind']=='standard_string_append']
            self.assertEqual(len(ops),2);self.assertTrue(all(s['preserves_existing_prefix'] for s in ops))
            self.assertEqual(ops[0]['operand']['literal'],'=');self.assertTrue(ops[1]['operand']['origins'])
            self.assertTrue(all(any(c['kind']=='branch' for c in s['conditions']) for s in ops))

    def test_different_main_files_keep_separate_process_entry_candidates(self):
        files={'first/unit.cpp':SOURCE+VECTOR,'second/entry.cpp':SOURCE.replace('Reader','Other')+VECTOR.replace('Reader','Other')}
        rows=self.bindings(self.graph(files=files));self.assertEqual(len(rows),4)
        self.assertEqual(len({r['entry'] for r in rows}),2);self.assertEqual(len({r['argv_source'] for r in rows}),2)
        self.assertTrue(all(len({o['entry'] for o in r['value']['origins']})==1 for r in rows))

    def test_namespaced_main_and_named_argv_in_a_helper_are_not_process_entries(self):
        source=SOURCE+'namespace Fake{int main(int n,char **argv){Reader r;r.decode(std::string(argv[0]));return 0;}}'
        g=self.graph(source);self.assertEqual(self.bindings(g),[]);self.assertEqual(g['cpp_argv_origins']['entry_candidates'],0)

    def test_same_callee_called_with_two_argv_indices_keeps_separate_frames(self):
        source=SOURCE+'int main(int n,char **argv){Reader r;r.decode(std::string(argv[1]));r.decode(std::string(argv[2]));return 0;}'
        rows=self.bindings(self.graph(source));self.assertEqual(len(rows),4)
        self.assertEqual(len({tuple(r['call_stack']) for r in rows}),2)
        self.assertEqual(len({r['id'] for r in rows}),4)

    def test_aliases_and_bare_standard_vector_spelling_are_resolved_from_source(self):
        source=SOURCE+'using namespace std;using Words=std::vector<std::string>;'+VECTOR.replace('std::vector<std::string>','Words')
        rows=self.bindings(self.graph(source));self.assertEqual(len(rows),2);self.assertTrue(all(r['origin_complete'] for r in rows),rows)
        bare=SOURCE+'using namespace std;'+VECTOR.replace('std::vector<std::string>','vector<string>')
        self.assertTrue(all(r['origin_complete'] for r in self.bindings(self.graph(bare))))

    def test_constant_input_does_not_acquire_the_callers_argv_by_name(self):
        source=SOURCE+'int main(int n,char **argv){std::string word="constant";Reader r;r.decode(word);return 0;}'
        rows=self.bindings(self.graph(source));self.assertEqual(len(rows),2)
        self.assertTrue(all(not r['origin_complete'] and not r['value']['origins'] for r in rows))

    def test_string_mutation_and_unknown_collection_effects_remain_required_gaps(self):
        for source in (SOURCE+VECTOR.replace('Reader reader;','token.clear();Reader reader;'),
            SOURCE+VECTOR.replace('return consume(prepared);','prepared.clear();return consume(prepared);')):
            g=self.graph(source);rows=self.bindings(g);self.assertTrue(rows)
            self.assertTrue(all(not r['origin_complete'] for r in rows));self.assertTrue(g['cpp_argv_origins']['required_gaps'])

    def test_array_rewrite_and_collection_mixed_inputs_do_not_claim_complete_argv(self):
        direct=SOURCE+'int main(int n,char **argv){argv[1]="other";Reader r;r.decode(std::string(argv[1]));return 0;}'
        mixed=SOURCE+VECTOR.replace('return consume(prepared);','prepared.push_back("other");return consume(prepared);')
        for source in (direct,mixed):self.assertTrue(all(not r['origin_complete'] for r in self.bindings(self.graph(source))))

    def test_budget_and_duplicate_projection_are_explicit(self):
        g=self.graph(max_states=1);self.assertTrue(g['cpp_argv_origins']['required_gaps'])
        self.assertTrue(all(not r['origin_complete'] for r in self.bindings(g)))
        with self.assertRaisesRegex(ValueError,'already present'):augment(g,None,None)

    def test_later_loop_write_can_reach_the_next_argument_read(self):
        source=SOURCE+VECTOR.replace('prepared.emplace_back(std::string(words[j]));','prepared.emplace_back(std::string(words[j]));words[j]="changed";')
        rows=self.bindings(self.graph(source));self.assertTrue(rows)
        self.assertTrue(all(not r['origin_complete'] and 'loop_carried_mutation_not_expanded' in r['value']['gaps'] for r in rows))

    def test_intervening_helper_may_modify_a_collection_through_alias(self):
        source=SOURCE+'void alter(std::vector<std::string>& x){x.clear();}'+VECTOR.replace('return consume(prepared);','alter(prepared);return consume(prepared);')
        rows=self.bindings(self.graph(source));self.assertTrue(rows)
        self.assertTrue(all(not r['origin_complete'] and 'collection_may_escape_to_intervening_call' in r['value']['gaps'] for r in rows))


if __name__=='__main__':unittest.main()
