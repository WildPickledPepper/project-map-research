import os
import unittest

from adapters.rust_facts import Extractor,syntax_facts
from adapters.sqlite_fact_graph import validate_graph


class RustSyntaxFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tree_sitter_language_pack as pack
        if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
        cls.parser=pack.get_parser('rust')

    def graph(self,files):
        x=Extractor({p:s.encode('utf-8') for p,s in files.items()},self.parser);g=x.build()
        validate_graph({'snapshot':'authored-rust-syntax',**g});return x,g

    def pairs(self,g,kind):
        nodes={n['id']:n for n in g['nodes']}
        return [(nodes[e['source']],nodes[e['target']],e) for e in g['edges'] if e['kind']==kind]

    def test_trait_signatures_impl_closure_and_self_parameter_have_separate_identities(self):
        x,g=self.graph({'src/lib.rs':'trait Go {fn run(&self, x:u8);} struct Unit{value:u8} impl Go for Unit {fn run(&self,x:u8){let f=|y:u8| helper(y); f(x);}} fn helper(x:u8){}'})
        functions=[n for n in g['nodes'] if n['kind']=='callable']
        self.assertEqual(len(functions),4)
        self.assertEqual({n['name'] for n in functions if n['syntax']!='closure_expression'},{'Go::run','Unit::run','helper'})
        self.assertTrue(any(n['trait_signature'] for n in functions))
        self.assertTrue(any(b['name']=='self' for a,b,e in self.pairs(g,'HAS_PARAMETER')))
        self.assertTrue(any(n['name']=='value' and n.get('binding_kind')=='field_declaration' for n in g['nodes']))

    def test_nested_scopes_and_same_line_calls_do_not_merge(self):
        x,g=self.graph({'x.rs':'fn run(){} mod inner{fn run(){}} fn entry(){run();run();}'})
        calls=[n for n in g['nodes'] if n['kind']=='call_site']
        self.assertEqual(len(calls),2);self.assertNotEqual(calls[0]['id'],calls[1]['id'])
        self.assertNotEqual(calls[0]['column'],calls[1]['column'])
        self.assertEqual({n['name'] for n in g['nodes'] if n['kind']=='callable'},{'run','inner::run','entry'})

    def test_cfg_and_branch_conditions_survive(self):
        x,g=self.graph({'x.rs':'#[cfg(unix)] fn entry(flag:bool){if flag {left();} else {right();}}'})
        calls={n['name']:n for n in g['nodes'] if n['kind']=='call_site'}
        self.assertTrue(any(c['kind']=='rust_attribute' and 'unix' in c['expression'] for c in calls['left']['conditions']))
        self.assertTrue(any(c.get('polarity') is True for c in calls['left']['conditions']))
        self.assertTrue(any(c.get('polarity') is False for c in calls['right']['conditions']))

    def test_local_bindings_assignment_and_pattern_projection_remain_explicit(self):
        x,g=self.graph({'x.rs':'fn entry(){let Some(path)=find() else{return;};let mut command=path;command=other();}'})
        bindings={n['name']:n for n in g['nodes'] if n['kind']=='binding'}
        self.assertEqual(set(bindings),{'path','command'})
        self.assertTrue(self.pairs(g,'PATTERN_VALUE_SOURCE'));self.assertTrue(self.pairs(g,'VALUE_SOURCE'))
        self.assertTrue(self.pairs(g,'WRITES_VALUE'))

    def test_for_patterns_have_distinct_scopes_and_iterated_source(self):
        code='fn entry(){let piece="outer";for piece in ["a","b"] {use_it(piece);}for (piece,index) in pairs(){use_it(piece);}use_it(piece);}'
        _,g=self.graph({'source.rs':code})
        loops=[n for n in g['nodes'] if n['kind']=='iteration']
        self.assertEqual(len(loops),2)
        bindings=[n for n in g['nodes'] if n.get('binding_kind')=='for_pattern']
        self.assertEqual(len(bindings),3)
        self.assertEqual(len({n['id'] for n in g['nodes'] if n['kind']=='binding' and n['name']=='piece'}),3)
        self.assertTrue(all(b['scope_range']['start_byte']>b['end_byte'] for b in bindings))
        projected=self.pairs(g,'ITERATES_VALUE')
        self.assertEqual(len(projected),3)
        self.assertTrue(any(b.get('collection_kind')=='array' and not e['projection'] for a,b,e in projected))
        self.assertEqual(sum(e['projection'] for a,b,e in projected),2)

    def test_array_order_and_repeat_length_have_separate_roles(self):
        _,g=self.graph({'x.rs':'const PARTS:[&str;3]=["assets","server","worker"];fn go(){for item in PARTS {}for item in ["x";2] {}}'})
        components=self.pairs(g,'VALUE_COMPONENT')
        arrays={n['id']:n for n in g['nodes'] if n.get('collection_kind') in {'array','array_repeat'}}
        normal=next(n for n in arrays.values() if n['collection_kind']=='array')
        self.assertEqual([(e['index'],b['expression']) for a,b,e in components if a['id']==normal['id']],[(0,'"assets"'),(1,'"server"'),(2,'"worker"')])
        repeated=next(n for n in arrays.values() if n['collection_kind']=='array_repeat')
        self.assertEqual([(b['expression'],e['collection_role']) for a,b,e in components if a['id']==repeated['id']],
                         [('"x"','element'),('2','repeat_count')])

    def test_call_argument_and_builder_receiver_structure(self):
        x,g=self.graph({'x.rs':'fn entry(){Command::new("tool").arg("--port").spawn();}'})
        receivers=self.pairs(g,'CALL_RECEIVER')
        self.assertEqual(len(receivers),2)
        self.assertTrue(any(b['name']=='Command::new' for a,b,e in receivers))
        self.assertEqual({b['expression'] for a,b,e in self.pairs(g,'CALL_ARGUMENT')},{'"tool"','"--port"'})

    def test_closure_owns_body_call_and_returns_value(self):
        x,g=self.graph({'x.rs':'fn entry(){let callback=|x| compute(x);callback(3);} fn compute(x:u8)->u8{x}'})
        observations=self.pairs(g,'OBSERVES_CALL')
        self.assertTrue(any(a['syntax']=='closure_expression' and b['name']=='compute' for a,b,e in observations))
        self.assertFalse(any(a['name']=='entry' and b['name']=='compute' for a,b,e in observations))
        self.assertTrue(any(a['syntax']=='closure_expression' for a,b,e in self.pairs(g,'RETURNS_VALUE')))

    def test_grouped_alias_imports_and_wildcard_are_source_references(self):
        x,g=self.graph({'x.rs':'use crate::{left::run as invoke, right::Unit}; use crate::left::*;'})
        refs=[n for n in g['nodes'] if n['kind']=='module_reference']
        self.assertEqual(len(refs),3)
        self.assertTrue(any(n.get('module_expression')=='crate::left::run' and n['name']=='invoke' for n in refs))
        self.assertEqual(len(self.pairs(g,'CONTAINS_IMPORT')),3)

    def test_macro_tokens_do_not_become_resolved_calls(self):
        x,g=self.graph({'x.rs':'fn entry(port:u16){let arg=format!("--port={port}"); log!(port);}'})
        self.assertEqual(len([n for n in g['nodes'] if n['kind']=='macro_site']),2)
        self.assertFalse(self.pairs(g,'STATIC_CALL_TARGET'))
        self.assertTrue(self.pairs(g,'MACRO_TOKEN'))

    def test_unicode_character_and_lsp_positions_are_distinct_encodings(self):
        code='fn entry(){let x="\U0001f9ed";run();}'
        x,g=self.graph({'x.rs':code});call=next(n for n in g['nodes'] if n['kind']=='call_site')
        token=x.references[call['id']][1]
        self.assertEqual(call['column'],code.index('run')+1)
        self.assertEqual(x.position('x.rs',token)['character'],code.index('run')+1)

    def test_invalid_file_has_local_diagnostic_and_other_file_survives(self):
        x,g=self.graph({'bad.rs':'fn broken( {','good.rs':'fn valid(){}'})
        self.assertEqual({r['path']:r['status'] for r in g['coverage']},{'bad.rs':'syntax_errors','good.rs':'parsed'})
        self.assertTrue(any(n['name']=='valid' for n in g['nodes']))
        self.assertTrue(all(d['path']=='bad.rs' for d in g['diagnostics']))

    def test_discovery_projection_includes_main_and_trait_signature(self):
        facts=syntax_facts(b'trait Go{fn run();}fn main(){}','x.rs',self.parser)
        self.assertEqual(facts['status'],'parsed');self.assertEqual(len(facts['symbols']),2)
        self.assertEqual(len(facts['entries']),1)
