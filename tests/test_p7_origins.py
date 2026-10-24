import os
import unittest
import tree_sitter_language_pack as pack
from adapters.cpp_data import analyze_data
from adapters.value_origin_queries import explain_value_origins

if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
    pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))


class P7OriginsTests(unittest.TestCase):
    def graph(self, source):
        r=analyze_data({'a.cpp':source.encode()},pack.get_parser('cpp'))
        return {**r['facts'],'data':r['data']}

    def test_return_field_follows_value_call_not_arguments(self):
        g=self.graph('struct V{int lines;};int key(){return 1;} V produce(int k){V r;r.lines=k;return r;} void handle(V& out){auto v=produce(key());out.lines=v.lines;}')
        writes=[w for w in g['data']['field_flow']['writes'] if 'out.lines' in w['evidence'][0]['expression']]
        r=explain_value_origins(g,writes);nodes={n['id']:n['name'] for n in g['nodes']}
        self.assertEqual({nodes[x['source']] for x in r['relations'] if x['kind']=='RETURNED_VALUE_SOURCE'},{'produce'})
        self.assertTrue(any(x['kind']=='RETURNED_LOCAL_FIELD_WRITE' for x in r['relations']))
        other=self.graph('struct V{int lines;int other;};V produce(){V r;r.lines=1;return r;}void handle(V& out){auto v=produce();out.lines=v.other;}')
        writes=[w for w in other['data']['field_flow']['writes'] if 'out.lines' in w['evidence'][0]['expression']]
        self.assertFalse(any(x['kind']=='RETURNED_LOCAL_FIELD_WRITE' for x in explain_value_origins(other,writes)['relations']))

    def test_reassigned_result_remains_conditional_and_depth_cut_visible(self):
        g=self.graph('struct V{int lines;};V produce(){V r;r.lines=1;return r;}void handle(V& out,bool yes){V v;if(yes)v=produce();out.lines=v.lines;}')
        writes=[w for w in g['data']['field_flow']['writes'] if 'out.lines' in w['evidence'][0]['expression']]
        r=explain_value_origins(g,writes)
        self.assertTrue(any(x['kind']=='intervening_assignment' for x in r['gaps']))
        self.assertTrue(all('candidate_reaching_definition' in x['conditions'] for x in r['relations']))
        self.assertTrue(explain_value_origins(g,writes,max_depth=0)['truncated'])

    def test_returned_local_field_written_through_reference_helper(self):
        g=self.graph('struct V{int lines;};void fill(V& out){out.lines=7;}V produce(){V r;fill(r);return r;}void handle(V& out){auto v=produce();out.lines=v.lines;}')
        nodes={n['id']:n['name'] for n in g['nodes']}
        writes=[w for w in g['data']['field_flow']['writes'] if nodes[w['source_symbol']]=='handle']
        rows=[x for x in explain_value_origins(g,writes)['relations'] if x['kind']=='RETURNED_LOCAL_FIELD_WRITE']
        self.assertEqual(len(rows),1)
        self.assertEqual(nodes[rows[0]['production_calls'][0]['callee']],'fill')

    def test_member_assignment_scalar_and_local_shadow_preserve_owner(self):
        g=self.graph('struct A{int key;std::vector<int> values;void put(int k,std::vector<int> v){key=k;values=v;}int get(){return key;}int shadow(int key){return key;} };struct B{int key;int get(){return key;}};')
        d=g['data']['member_effects'];members={m['id']:m for m in d['members']};nodes={n['id']:n['name'] for n in g['nodes']}
        writes=[e for e in d['effects'] if e['role']=='write']
        self.assertEqual({members[e['member']]['name'] for e in writes},{'key','values'})
        self.assertFalse(any(nodes[e['source_symbol']]=='A::shadow' for e in d['effects']))
        reads=[e for e in d['effects'] if e['role']=='read']
        self.assertEqual({members[e['member']]['owner'] for e in reads},{'A','B'})
        self.assertTrue(all(e['instance_identity']=='unresolved' for e in d['effects']))
