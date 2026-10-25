import unittest

from adapters.rust_boundaries import augment
from adapters.rust_project import available
from tests import test_rust_semantics as semantic_fixtures


@unittest.skipUnless(available('cargo') and available('rustc') and available('rust-analyzer'),'Native Rust analysis tools required')
class RustBoundaryTests(unittest.TestCase):
    setUpClass=classmethod(semantic_fixtures.RustSemanticsTests.setUpClass.__func__)
    graph=semantic_fixtures.RustSemanticsTests.graph
    pairs=semantic_fixtures.RustSemanticsTests.pairs

    def test_process_command_identity_options_and_implicit_format_parameter(self):
        g=augment(self.graph({'src/lib.rs':'''use std::process::Command as Launch;
fn start(program:&str,port:u16){
 let mut left=Launch::new(program);let mut right=Launch::new("decoy");
 left.arg(format!("--listen={port}"));right.arg("--wrong");let _=left.spawn();
}'''}))
        links=self.pairs(g,'USES_COMMAND')
        self.assertEqual(len(links),1)
        program=self.pairs(g,'COMMAND_PROGRAM')
        self.assertEqual(next(b['expression'] for a,b,e in program if a['id']==links[0][1]['id']),'program')
        options=self.pairs(g,'COMMAND_OPTION_SOURCE')
        self.assertTrue(any('format!' in b.get('expression','') for a,b,e in options))
        self.assertFalse(any(b.get('expression')=='"--wrong"' for a,b,e in options))
        captures=[n for n in g['nodes'] if n.get('syntax')=='format_capture']
        self.assertEqual({n['name'] for n in captures},{'port'})
        self.assertTrue(any(a.get('syntax')=='format_capture' and b['name']=='port' for a,b,e in self.pairs(g,'READS_BINDING')))

    def test_local_command_and_webview_homonyms_are_not_library_boundaries(self):
        g=augment(self.graph({'src/lib.rs':'struct Command;impl Command{fn new()->Self{Self}fn spawn(&self){}}struct WebViewBuilder;impl WebViewBuilder{fn new()->Self{Self}fn with_url(&self,x:&str){}}fn entry(){Command::new().spawn();WebViewBuilder::new().with_url("http://local");}'}))
        self.assertFalse([n for n in g['nodes'] if n['kind']=='rust_boundary'])

    def test_native_tcp_listener_and_client_arguments_are_queryable(self):
        g=augment(self.graph({'src/lib.rs':'use std::net::{TcpListener,TcpStream};fn entry(address:&str){let _=TcpListener::bind(address);let _=TcpStream::connect(address);}'}))
        self.assertEqual({n['family'] for n in g['nodes'] if n['kind']=='rust_boundary'},{'network_listener','network_client'})
        self.assertEqual(len(self.pairs(g,'BOUNDARY_ARGUMENT')),2)
