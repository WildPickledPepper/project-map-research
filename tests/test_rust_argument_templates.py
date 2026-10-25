import unittest

from adapters.rust_argument_templates import augment
from adapters.rust_boundaries import augment as boundaries
from adapters.rust_project import available
from tests import test_rust_semantics as native_fixtures


@unittest.skipUnless(all(available(t) for t in ('cargo','rustc','rust-analyzer')),'Native Rust analysis tools required')
class RustArgumentTemplateTests(unittest.TestCase):
    setUpClass=classmethod(native_fixtures.RustSemanticsTests.setUpClass.__func__)
    graph=native_fixtures.RustSemanticsTests.graph

    def build(self,files):
        def transform(root,g,parser):return augment(root,boundaries(g),parser)
        return self.graph(files,transform=transform)

    def templates(self,g):return [n for n in g['nodes'] if n['kind']=='boundary_argument_template']
    def slots(self,template):return [p['slot'] for p in template['parts'] if 'slot' in p]

    def test_dynamic_projection_is_shared_across_two_callees_without_guessing_port(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn choose()->Option<u16>{std::env::var("PORT").ok()?.parse().ok()}
fn server(p:u16){let _=Command::new("one").arg(format!("--alpha={p}")).spawn();}
fn other(q:u16){let _=Command::new("two").arg(format!("--beta={q}")).spawn();}
fn entry(){let Some(selected)=choose() else{return};server(selected);other(selected);}
'''})
        templates=self.templates(g);self.assertEqual(len(templates),2);self.assertTrue(all(t['complete'] for t in templates))
        self.assertEqual(self.slots(templates[0]),self.slots(templates[1]))
        value=next(n for n in g['nodes'] if n['id']==self.slots(templates[0])[0])
        self.assertEqual(value['value']['kind'],'binding_projection');self.assertNotIn('literal',value)
        self.assertTrue(any(c['kind']=='rust_pattern_projection_selected' for c in templates[0]['conditions']))

    def test_positional_named_implicit_and_escaped_braces_keep_slot_order(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn entry(){let a=4;let b=9;let _=Command::new("never").arg(format!("{{tag}}:{1}:{}:{a}:{label}",a,b,label=b)).spawn();}
'''})
        t=self.templates(g)[0];self.assertTrue(t['complete'],t['gaps'])
        nodes={n['id']:n for n in g['nodes']}
        self.assertEqual([nodes[s]['literal'] for s in self.slots(t)],[9,4,4,9])
        self.assertEqual(''.join(p.get('literal','') for p in t['parts']),'{tag}::::')

    def test_wrapper_return_alias_and_string_borrow_preserve_template(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn word(value:u16)->String{format!("--renamed={value}")}
fn entry(){let port=7;let text=word(port);let alias=text;let _=Command::new("never").arg(alias.as_str()).spawn();}
'''})
        t=self.templates(g)[0];self.assertTrue(t['complete'],t['gaps']);self.assertEqual(t['parts'][0],{'literal':'--renamed='})
        nodes={n['id']:n for n in g['nodes']};self.assertEqual(nodes[self.slots(t)[0]]['literal'],7)

    def test_two_calls_and_same_names_in_other_scopes_keep_different_values(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn run(port:u16){let _=Command::new("never").arg(format!("--listen={port}")).spawn();}
fn first(){let port=3;run(port);}fn second(){let port=8;run(port);}
'''})
        templates=self.templates(g);self.assertEqual(len(templates),2)
        self.assertNotEqual(self.slots(templates[0]),self.slots(templates[1]))
        nodes={n['id']:n for n in g['nodes']};self.assertEqual({nodes[self.slots(t)[0]]['literal'] for t in templates},{3,8})

    def test_closure_capture_uses_outer_call_context_and_keeps_invocation_condition(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn outer(port:u16){let callback=move||{let _=Command::new("never").arg(format!("--route={port}")).spawn();};drop(callback);}
fn entry(){outer(43);}
'''})
        t=self.templates(g)[0];self.assertTrue(t['complete'],t['gaps']);nodes={n['id']:n for n in g['nodes']}
        self.assertEqual(nodes[self.slots(t)[0]]['literal'],43)
        self.assertTrue(any(c['kind']=='closure_invoked_with_recorded_capture_environment' for c in t['conditions']))

    def test_reaching_write_and_dynamic_format_options_remain_required_gaps(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn entry(){let mut port=3;port=8;let width=5;let _=Command::new("never").arg(format!("--port={port}")).arg(format!("{:width$}",port)).spawn();}
'''})
        templates=self.templates(g);self.assertEqual(len(templates),2);self.assertTrue(all(not t['complete'] for t in templates))
        reasons={r for t in templates for r in t['gaps']}
        self.assertIn('scalar_reaching_write_not_selected',reasons);self.assertIn('dynamic_format_options_not_expanded',reasons)
        self.assertEqual(len([d for d in g['diagnostics'] if d['kind']=='rust_argument_template_unresolved' and d['required']]),2)

    def test_local_homonym_and_environment_options_do_not_become_argv_words(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
macro_rules! custom {($x:expr)=>{"changed"}}
fn entry(){let _=Command::new("never").env("SECRET_NAME","unused").arg(custom!("x")).spawn();}
'''})
        templates=self.templates(g);self.assertEqual(len(templates),1);self.assertFalse(templates[0]['complete'])
        self.assertEqual(templates[0]['gaps'],['macro_not_native_standard_format'])

    def test_array_arguments_preserve_words_and_custom_formatter_spec(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn entry(){let value=3;let _=Command::new("never").args(["has a space", "next"]).arg(format!("--p={value:04}")).spawn();}
'''})
        templates=self.templates(g);self.assertEqual(len(templates),3);self.assertTrue(all(t['complete'] for t in templates))
        self.assertEqual(templates[0]['parts'],[{'literal':'has a space'}]);self.assertEqual(templates[1]['parts'],[{'literal':'next'}])
        self.assertEqual(templates[2]['parts'][-1]['format_spec'],'04')

    def test_command_and_network_templates_refer_to_the_same_dynamic_value(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;use std::net::TcpStream;
fn selected()->u16{std::env::var("PORT").unwrap().parse().unwrap()}
fn backend(port:u16){let _=Command::new("never").arg(format!("--socket={port}")).spawn();}
fn client(channel:u16){let _=TcpStream::connect(format!("127.0.0.1:{channel}"));}
fn entry(){let shared=selected();backend(shared);client(shared);}
'''})
        templates=self.templates(g);self.assertEqual({t['role'] for t in templates},{'process_argument','network_client'})
        self.assertEqual(len(templates),2);self.assertTrue(all(t['complete'] for t in templates))
        self.assertEqual(self.slots(templates[0]),self.slots(templates[1]))

    def test_inactive_compile_time_callers_do_not_create_argument_variants(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn run(value:&str){let _=Command::new("never").arg(value).spawn();}
fn entry(){#[cfg(any())]{run("inactive");}#[cfg(all())]{run("active");}}
'''})
        templates=self.templates(g);self.assertEqual(len(templates),1);self.assertEqual(templates[0]['parts'],[{'literal':'active'}])

    def test_mutating_a_string_argument_does_not_reuse_its_old_literal(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn entry(){let mut address=String::from("old");address.push_str("new");let _=Command::new("never").arg(address.as_str()).spawn();}
'''})
        template=self.templates(g)[0];self.assertFalse(template['complete']);self.assertIn('scalar_reaching_write_not_selected',template['gaps'])

    def test_loop_pattern_values_require_an_iteration_identity(self):
        g=self.build({'src/lib.rs':'''use std::process::Command;
fn choose()->Option<u16>{std::env::var("PORT").ok()?.parse().ok()}
fn entry(){for _ in 0..2{let Some(value)=choose() else{continue};let _=Command::new("never").arg(format!("--p={value}")).spawn();}}
'''})
        template=self.templates(g)[0];self.assertFalse(template['complete']);self.assertIn('scalar_iteration_instance_not_bound',template['gaps'])


class RustCfgSelectionTests(unittest.TestCase):
    def test_nested_known_predicates_and_unbound_custom_features(self):
        from adapters.rust_cfg import evaluate
        context={'cfg':['windows','target_os="windows"','target_arch="x86_64"'],'features':['sample/default']}
        self.assertIs(evaluate('all(windows,any(target_os="windows",target_os="macos"),not(unix))',context),True)
        self.assertIs(evaluate('any(target_os="linux",all())',context),True)
        self.assertIs(evaluate('all(target_os="linux",custom)',context),False)
        self.assertIsNone(evaluate('feature="possibly_transitive"',context))
        self.assertIsNone(evaluate('custom',context));self.assertIsNone(evaluate('not(windows,unix)',context))


if __name__=='__main__':unittest.main()
