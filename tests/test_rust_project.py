import json
import os
from pathlib import Path
import tempfile
import unittest

from adapters.rust_project import available,binary,cargo_options,configuration_matrix,discover,tool_output
from adapters.rust_analyzer import Client


class RustToolInvocationTests(unittest.TestCase):
    @unittest.skipIf(os.name=='nt','POSIX multicall executable symlinks')
    def test_multicall_executable_symlink_keeps_its_launch_name(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tool=root/'multicall'
            tool.write_text('#!/bin/sh\nbasename "$0"\n',encoding='utf-8');tool.chmod(0o755)
            (root/'cargo').symlink_to(tool)
            with patch('adapters.rust_project.shutil.which',return_value=str(root/'cargo')):
                self.assertEqual(tool_output([binary('cargo')],root).strip(),'cargo')


@unittest.skipUnless(available('cargo') and available('rustc'),'Rust Cargo metadata tools are required')
class RustProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rust project ')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def files(self,values):
        for path,body in values.items():
            dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
        return [p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()]

    def workspace(self):
        return self.files({'Cargo.toml':'[workspace]\nmembers=["shell", "worker"]\nresolver="2"\n',
            'shell/Cargo.toml':'[package]\nname="viewer"\nversion="0.1.0"\nedition="2021"\n[[bin]]\nname="window"\npath="entry/start.rs"\n[dependencies]\napi={package="engine",path="../worker"}\n',
            'shell/entry/start.rs':'fn main(){api::run();}',
            'worker/Cargo.toml':'[package]\nname="engine"\nversion="0.1.0"\nedition="2021"\n[lib]\npath="code/engine.rs"\n',
            'worker/code/engine.rs':'pub fn run(){}',
            'worker/build.rs':'fn main(){std::fs::write("EXECUTED","bad").unwrap();panic!("Do not execute build scripts");}'})

    def test_cargo_discovers_workspace_custom_targets_and_renamed_path_dependency(self):
        metadata=discover(self.root,self.workspace())
        self.assertFalse(metadata['diagnostics'])
        self.assertEqual(metadata['workspaces'],['Cargo.toml'])
        self.assertEqual({p['name'] for p in metadata['packages']},{'viewer','engine'})
        viewer=next(p for p in metadata['packages'] if p['name']=='viewer')
        self.assertEqual(viewer['targets'][0]['path'],'shell/entry/start.rs')
        self.assertEqual(viewer['dependencies'][0]['rename'],'api')
        self.assertFalse(list(self.root.rglob('EXECUTED')))

    def test_new_renamed_and_deleted_package_targets_are_rediscovered(self):
        paths=self.files({'Cargo.toml':'[package]\nname="sample"\nversion="0.1.0"\nedition="2021"\n',
            'src/lib.rs':'pub fn run(){}'})
        self.assertEqual(discover(self.root,paths)['packages'][0]['targets'][0]['path'],'src/lib.rs')
        paths=self.files({'src/bin/first.rs':'fn main(){}'})
        self.assertTrue(any(t['path']=='src/bin/first.rs' for t in discover(self.root,paths)['packages'][0]['targets']))
        (self.root/'src/bin/first.rs').rename(self.root/'src/bin/renamed.rs')
        paths=[p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()]
        targets=discover(self.root,paths)['packages'][0]['targets']
        self.assertNotIn('src/bin/first.rs',{t['path'] for t in targets})
        self.assertIn('src/bin/renamed.rs',{t['path'] for t in targets})
        (self.root/'src/bin/renamed.rs').unlink()
        paths=[p for p in paths if p!='src/bin/renamed.rs']
        self.assertEqual(len(discover(self.root,paths)['packages'][0]['targets']),1)

    def test_outside_export_dependency_is_a_required_gap(self):
        paths=self.files({'Cargo.toml':'[package]\nname="sample"\nversion="0.1.0"\n[dependencies]\nmissing={path="../outside"}\n',
            'src/lib.rs':''})
        result=discover(self.root,paths)
        self.assertTrue(result['diagnostics']);self.assertTrue(all(d['required'] for d in result['diagnostics']))

    def test_missing_compiler_is_a_required_context_gap(self):
        from unittest.mock import patch
        with patch('adapters.rust_project.binary',return_value=None):
            contexts,diagnostics=configuration_matrix(self.root,[],{'packages':[]})
        self.assertFalse(contexts);self.assertTrue(diagnostics[0]['required'])

    def test_source_conditions_generate_os_feature_and_debug_contexts(self):
        paths=self.files({'Cargo.toml':'[package]\nname="sample"\nversion="0.1.0"\nedition="2021"\n[features]\nui=[]\nextra=[]\n',
            'src/lib.rs':'#[cfg(all(feature="ui", target_os="linux"))] fn run(){}'})
        metadata=discover(self.root,paths);contexts,diagnostics=configuration_matrix(self.root,paths,metadata)
        self.assertTrue(any(c['target'].endswith('linux-gnu') for c in contexts))
        self.assertEqual({tuple(c['features']) for c in contexts},{(),('sample/ui',)})
        self.assertEqual({c['debug_assertions'] for c in contexts},{False,True})
        self.assertTrue(any(d['kind']=='rust_manifest_features_not_individually_varied' and 'sample/extra' in d['features'] for d in diagnostics))
        json.dumps(contexts,allow_nan=False)

    @unittest.skipUnless(available('rust-analyzer'),'rust-analyzer is required for Cargo/LSP integration')
    def test_native_cargo_loader_connects_renamed_workspace_dependency_without_running_build(self):
        paths=self.workspace();discover(self.root,paths)
        context={'target':'x86_64-pc-windows-msvc' if os.name=='nt' else 'x86_64-unknown-linux-gnu',
            'features':[],'debug_assertions':False}
        with Client(binary('rust-analyzer'),self.root,str(self.root/'Cargo.toml'),self.root/'lsp.log',
                cargo=cargo_options(context)) as client:
            result=client.at('textDocument/definition','shell/entry/start.rs',{'line':0,'character':16})
            self.assertTrue(result)
            self.assertTrue(any('worker/code/engine.rs' in r.get('targetUri',r.get('uri','')) for r in result))
        self.assertFalse(list(self.root.rglob('EXECUTED')))

    @unittest.skipUnless(available('rust-analyzer'),'rust-analyzer is required for Cargo/LSP integration')
    def test_native_cargo_feature_and_debug_choices_keep_alternatives_separate(self):
        self.files({'Cargo.toml':'[package]\nname="sample"\nversion="0.1.0"\nedition="2021"\n[features]\nui=[]\n',
            'src/lib.rs':'#[cfg(feature="ui")] #[path="gui.rs"] mod selected;\n'
                '#[cfg(not(feature="ui"))] #[path="headless.rs"] mod selected;\n'
                '#[cfg(debug_assertions)] #[path="debug.rs"] mod mode;\n'
                '#[cfg(not(debug_assertions))] #[path="release.rs"] mod mode;\n'
                'pub fn entry(){selected::run();mode::run();}',
            'src/gui.rs':'pub fn run(){}','src/headless.rs':'pub fn run(){}',
            'src/debug.rs':'pub fn run(){}','src/release.rs':'pub fn run(){}'})
        target='x86_64-pc-windows-msvc' if os.name=='nt' else 'x86_64-unknown-linux-gnu'
        for features,debug,implementation,mode in [([],False,'headless','release'),(['sample/ui'],True,'gui','debug')]:
            with self.subTest(features=features,debug=debug),Client(binary('rust-analyzer'),self.root,str(self.root/'Cargo.toml'),
                self.root/(implementation+'.log'),cargo=cargo_options({'target':target,'features':features,'debug_assertions':debug})) as client:
                first=client.at('textDocument/definition','src/lib.rs',{'line':4,'character':25})
                second=client.at('textDocument/definition','src/lib.rs',{'line':4,'character':37})
                self.assertEqual(len(first),1);self.assertIn('/src/'+implementation+'.rs',first[0]['targetUri'])
                self.assertEqual(len(second),1);self.assertIn('/src/'+mode+'.rs',second[0]['targetUri'])
