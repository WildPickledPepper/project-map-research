import json
import os
from pathlib import Path
import tempfile
import unittest

from adapters.rust_project import available,binary,tool_output
from adapters.rust_semantics import analyze
from adapters.sqlite_fact_graph import validate_graph


@unittest.skipUnless(available('cargo') and available('rustc') and available('rust-analyzer'),'Native Rust analysis tools required')
class RustSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tree_sitter_language_pack as pack
        if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
        cls.parser=pack.get_parser('rust')
        cls.target=next(s.removeprefix('host: ') for s in tool_output([binary('rustc'),'-vV'],Path.cwd()).splitlines() if s.startswith('host: '))

    def graph(self,files,*,configurations=None):
        with tempfile.TemporaryDirectory(prefix='rust semantic ') as directory:
            root=Path(directory)
            files={'Cargo.toml':'[package]\nname="independent"\nversion="0.1.0"\nedition="2021"\n',**files}
            for path,body in files.items():
                file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(body,encoding='utf-8')
            contexts=[('Cargo.toml',{'target':self.target,'features':features,'debug_assertions':False})
                for features in (configurations or [[]])]
            g=analyze(root,list(files),self.parser,contexts=contexts)
            self.assertFalse(list(root.rglob('EXECUTED')))
            validate_graph({'snapshot':'native-rust-fixture',**g})
            self.assertFalse([d for d in g['diagnostics'] if d['kind']=='rust_context_failed'])
            json.dumps(g,allow_nan=False);return g

    def pairs(self,g,kind):
        nodes={n['id']:n for n in g['nodes']}
        return [(nodes[e['source']],nodes[e['target']],e) for e in g['edges'] if e['kind']==kind]

    def test_alias_reexport_module_and_same_name_decoy(self):
        g=self.graph({'src/lib.rs':'mod left;mod right;mod api{pub use crate::left::run as invoke;}pub fn entry(){api::invoke();}',
            'src/left.rs':'pub fn run(){}','src/right.rs':'pub fn run(){}'})
        pairs=self.pairs(g,'STATIC_CALL_TARGET')
        self.assertEqual({(a['name'],b['path'],b['name']) for a,b,e in pairs},{('api::invoke','src/left.rs','run')})
        self.assertTrue(any(b['path']=='src/left.rs' for a,b,e in self.pairs(g,'IMPORTS_MODULE')))

    def test_receiver_impl_self_parameter_and_call_arguments(self):
        g=self.graph({'src/lib.rs':'struct A;struct B;impl A{fn run(&self,value:u8){}}impl B{fn run(&self,value:u8){}}fn entry(){let a=A;a.run(3);}'})
        self.assertEqual({b['name'] for a,b,e in self.pairs(g,'STATIC_CALL_TARGET')},{'A::run'})
        bound=self.pairs(g,'BINDS_ARGUMENT')
        self.assertEqual({b['name'] for a,b,e in bound},{'self','value'})

    def test_trait_object_keeps_implementations_as_candidates(self):
        g=self.graph({'src/lib.rs':'trait Go{fn run(&self);}struct A;struct B;impl Go for A{fn run(&self){}}impl Go for B{fn run(&self){}}fn entry(x:&dyn Go){x.run();}'})
        self.assertFalse(self.pairs(g,'STATIC_CALL_TARGET'))
        self.assertEqual({b['name'] for a,b,e in self.pairs(g,'STATIC_CALL_CANDIDATE')},{'A::run','B::run'})
        self.assertTrue(self.pairs(g,'DISPATCHES_TRAIT_MEMBER'))

    def test_closure_alias_call_and_callback_argument(self):
        g=self.graph({'src/lib.rs':'fn action(x:u8)->u8{x}fn register(f:fn(u8)->u8){}fn entry(){let callback=|x|action(x);callback(1);register(action);}'})
        targets=self.pairs(g,'STATIC_CALL_TARGET')
        self.assertTrue(any(a['name']=='callback' and b['syntax']=='closure_expression' for a,b,e in targets))
        self.assertTrue(any(a['name']=='action' and b['name']=='action' for a,b,e in targets))
        self.assertTrue(any(a['name']=='register' and b['name']=='action' for a,b,e in self.pairs(g,'PASSES_CALLBACK')))

    def test_function_parameter_does_not_bind_to_global_homonym(self):
        g=self.graph({'src/lib.rs':'fn action(){}fn entry(action:fn()){action();}'})
        self.assertFalse(self.pairs(g,'STATIC_CALL_TARGET'))
        self.assertTrue(self.pairs(g,'CALLS_BOUND_VALUE'))
        self.assertTrue(any(n.get('reason') for n in g['nodes'] if n['kind']=='call_site'))

    def test_cfg_paths_are_context_candidates_without_combining_alternatives(self):
        g=self.graph({'Cargo.toml':'[package]\nname="independent"\nversion="0.1.0"\nedition="2021"\n[features]\nui=[]\n',
            'src/lib.rs':'#[cfg(feature="ui")]#[path="gui.rs"]mod worker;#[cfg(not(feature="ui"))]#[path="remote.rs"]mod worker;fn entry(){worker::run();}',
            'src/gui.rs':'pub fn run(){}','src/remote.rs':'pub fn run(){}'},configurations=[[],['independent/ui']])
        candidates=self.pairs(g,'STATIC_CALL_CANDIDATE')
        self.assertEqual({b['path'] for a,b,e in candidates},{'src/gui.rs','src/remote.rs'})
        self.assertEqual(len(candidates),2);self.assertTrue(all(len(e['analysis_contexts'])==1 for a,b,e in candidates))
        self.assertNotEqual(candidates[0][2]['analysis_contexts'],candidates[1][2]['analysis_contexts'])

    def test_external_command_is_declaration_bound_and_local_homonym_is_not_external(self):
        g=self.graph({'src/lib.rs':'use std::process::Command as Run;mod decoy{pub struct Command;impl Command{pub fn new(){}}}fn entry(){let _=Run::new("never-run");decoy::Command::new();}'})
        external=self.pairs(g,'EXTERNAL_CALL_REFERENCE')
        self.assertTrue(any(b['external_declaration'].get('container')=='Command' and b['external_declaration']['name']=='new' for a,b,e in external))
        self.assertFalse(any(a['name']=='decoy::Command::new' for a,b,e in external))
        self.assertTrue(any(a['name']=='decoy::Command::new' and b['name']=='decoy::Command::new' for a,b,e in self.pairs(g,'STATIC_CALL_TARGET')))

    def test_macro_definition_origin_is_not_a_fake_callable(self):
        g=self.graph({'src/lib.rs':'macro_rules! make{()=>{fn generated(){}}}make!();fn entry(){generated();}'})
        self.assertFalse(self.pairs(g,'STATIC_CALL_TARGET'))
        self.assertTrue(self.pairs(g,'DEFINITION_ORIGIN'))
        self.assertTrue(any(n.get('reason') for n in g['nodes'] if n['kind']=='call_site'))
