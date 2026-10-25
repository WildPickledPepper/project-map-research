import unittest

from adapters.rust_boundaries import augment as boundaries
from adapters.rust_path_values import augment, string_value
from adapters.rust_project import available
from tests import test_rust_semantics as semantic_fixtures


class RustStringValueTests(unittest.TestCase):
    def test_native_string_forms(self):
        self.assertEqual(string_value(r'r##"C:\assets\worker"##'),r'C:\assets\worker')
        self.assertEqual(string_value(r'"\u{4e2d}\x2fworker"'),'中/worker')
        self.assertEqual(string_value('"one\\\n    two"'),'onetwo')
        self.assertEqual(string_value(r'"quote\"slash\\"'),'quote"slash\\')
        self.assertEqual(string_value('"one\r\ntwo"'),'one\ntwo')


@unittest.skipUnless(all(available(n) for n in ('cargo','rustc','rust-analyzer')),'Native Rust tools required')
class RustPathValueTests(unittest.TestCase):
    setUpClass=classmethod(semantic_fixtures.RustSemanticsTests.setUpClass.__func__)
    graph=semantic_fixtures.RustSemanticsTests.graph

    def paths(self,code):
        graph=self.graph({'src/lib.rs':code},transform=lambda root,g,parser:augment(root,boundaries(g),parser))
        return graph,[n for n in graph['nodes'] if n['kind']=='path_value']

    def test_ordered_literal_loop_and_platform_extension(self):
        _,values=self.paths('''use std::{path::Path,process::Command};
const PARTS:[&str;3]=["assets","service","runner"];
fn entry(root:&Path){let mut output=root.to_path_buf();for part in PARTS {output.push(part);}
#[cfg(windows)] output.set_extension("exe");let _=Command::new(output).spawn();}''')
        self.assertEqual(len(values),1)
        self.assertEqual(values[0]['value']['relative_path'],'assets/service/runner.exe' if 'windows' in self.target else 'assets/service/runner')
        self.assertEqual(values[0]['value']['resolution'],'symbolic_base')

    def test_clone_and_same_name_values_do_not_share_later_mutations(self):
        _,values=self.paths('''use std::{path::PathBuf,process::Command};fn entry(){
let mut left=PathBuf::from("bundle");let mut right=PathBuf::from("other");left.push("before");
let saved=left.clone();right.push("decoy");left.push("after");
let _=Command::new(saved).spawn();let _=Command::new(left).spawn();}''')
        self.assertEqual({v['value']['relative_path'] for v in values},{'bundle/before','bundle/before/after'})
        self.assertTrue(all(v['value']['resolution']=='constant' for v in values))

    def test_source_helper_mutates_only_the_supplied_object(self):
        _,values=self.paths('''use std::{path::PathBuf,process::Command};
fn append(out:&mut PathBuf){out.push("worker");}
fn entry(){let mut path=PathBuf::from("bundle");append(&mut path);let _=Command::new(path).spawn();}''')
        self.assertEqual(len(values),1);self.assertEqual(values[0]['value']['relative_path'],'bundle/worker')

    def test_unmodeled_effect_through_mutable_parameter_is_not_silently_pure(self):
        _,values=self.paths('''use std::{path::PathBuf,process::Command};
fn swap_path(out:&mut PathBuf){let mut other=PathBuf::from("replacement");std::mem::swap(out,&mut other);}
fn entry(){let mut path=PathBuf::from("bundle");swap_path(&mut path);let _=Command::new(path).spawn();}''')
        self.assertTrue(values);self.assertTrue(all(v['value']['resolution']=='unresolved' for v in values))

    def test_branch_effects_are_alternatives(self):
        _,values=self.paths('''use std::{path::PathBuf,process::Command};fn entry(flag:bool){
let mut path=PathBuf::from("bundle");if flag {path.push("left");}else{path.push("right");}
let _=Command::new(path).spawn();}''')
        self.assertEqual({v['value']['relative_path'] for v in values},{'bundle/left','bundle/right'})
        self.assertTrue(all(v['value']['conditions'] for v in values))

    def test_borrowed_alias_and_capture_at_constructor_time(self):
        _,values=self.paths('''use std::{path::PathBuf,process::Command};fn entry(){
let mut path=PathBuf::from("bundle");{let alias=&mut path;alias.push("one");}
let mut command=Command::new(&path);path.push("later");let _=command.spawn();}''')
        self.assertEqual(len(values),1);self.assertEqual(values[0]['value']['relative_path'],'bundle/one')

    def test_dynamic_component_remains_unresolved(self):
        _,values=self.paths('''use std::{path::PathBuf,process::Command};fn entry(name:&str){
let mut path=PathBuf::from("bundle");path.push(name);let _=Command::new(path).spawn();}''')
        self.assertTrue(values);self.assertTrue(all(v['value']['resolution']=='unresolved' for v in values))
        self.assertTrue(all(v['value']['relative_path'] is None for v in values))

    def test_optional_helper_and_caller_binding_reach_executable_directory(self):
        graph,values=self.paths('''use std::{path::{Path,PathBuf},process::Command};
fn assemble(base:&Path)->Option<PathBuf>{let mut value=base.to_path_buf();for piece in ["resources","worker"]{value.push(piece);}
if !value.exists(){return None;}Some(value)}
fn launch(base:&Path){let Some(program)=assemble(base) else{return;};let _=Command::new(program).spawn();}
fn entry(){let location=std::env::current_exe().unwrap();let base=location.parent().unwrap();launch(base);}
''')
        self.assertEqual(len(values),1)
        self.assertEqual(values[0]['value']['base']['kind'],'current_executable_directory')
        self.assertEqual(values[0]['value']['relative_path'],'resources/worker')
        self.assertEqual(len(values[0]['call_stack']),1)

    def test_unrelated_dynamic_loop_does_not_change_path(self):
        _,values=self.paths('''use std::{path::PathBuf,process::Command};fn entry(items:Vec<u8>){
let path=PathBuf::from("bundle");for value in items {let _=value;}
let _=Command::new(path).spawn();}''')
        self.assertEqual([v['value']['relative_path'] for v in values],['bundle'])

    def test_dynamic_loop_reassignment_and_unknown_mutable_call_do_not_keep_stale_path(self):
        for body in ['while flag {path.push("one");}', 'path=PathBuf::from("replacement");',
                     'opaque(&mut path);', 'change!(path);']:
            with self.subTest(body=body):
                _,values=self.paths('''use std::{path::PathBuf,process::Command};
unsafe extern "C" {fn opaque(value:*mut PathBuf);}
macro_rules! change {($p:ident)=>{{$p.push("hidden")}}}
fn entry(flag:bool){let mut path=PathBuf::from("bundle");''' + body + '''let _=Command::new(path).spawn();}''')
                self.assertTrue(values);self.assertTrue(all(v['value']['resolution']=='unresolved' for v in values))

    def test_local_pathbuf_homonym_is_not_treated_as_standard_path_push(self):
        graph,values=self.paths('''use std::{ffi::OsStr,process::Command};
struct PathBuf;impl PathBuf{fn push(&mut self,_x:&str){}}
impl AsRef<OsStr> for PathBuf{fn as_ref(&self)->&OsStr{OsStr::new("real")}}
fn entry(){let mut value=PathBuf;value.push("other");let _=Command::new(value).spawn();}''')
        self.assertTrue(values);self.assertTrue(all(v['value']['resolution']=='unresolved' for v in values))

    def test_component_sources_are_connected_to_existing_graph_nodes(self):
        graph,values=self.paths('''use std::{path::Path,process::Command};fn entry(base:&Path){
let path=base.join("assets/worker");let _=Command::new(path).spawn();}''')
        self.assertEqual(len(values),1)
        nodes={n['id']:n for n in graph['nodes']}
        sources=[nodes[e['target']] for e in graph['edges'] if e['kind']=='PATH_COMPONENT_SOURCE' and e['source']==values[0]['id']]
        self.assertTrue(any(n.get('expression')=='"assets/worker"' for n in sources))
        self.assertTrue(any(n['kind']=='parameter' and n['name']=='base' for n in sources))


if __name__=='__main__':unittest.main()
