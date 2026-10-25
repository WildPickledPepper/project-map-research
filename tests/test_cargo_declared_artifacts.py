import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from adapters.cargo_declared_artifacts import augment
from adapters.cargo_native import capture
from adapters.cargo_source_bindings import augment as bind_sources
from adapters.artifact_copy_graph import augment as copy_artifacts
from adapters.rust_project import available
from adapters.sqlite_fact_graph import validate_graph
from tests import test_cargo_file_api as native_fixtures
from tests import test_python_path_values as python_fixtures


@unittest.skipUnless(available('cargo') and available('rustc'),'Native Cargo and rustc required')
class CargoDeclaredArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tree_sitter_language_pack as pack
        if os.environ.get('PROJECT_MAP_PARSER_CACHE'):pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
        cls.parser=pack.get_parser('rust');cls.temp=tempfile.TemporaryDirectory(prefix='cargo declared outputs ')
        cls.addClassCleanup(cls.temp.cleanup);cls.root=Path(cls.temp.name);cls.cases=[]
        for second in (False,True):
            files,env,manifest,name=native_fixtures.fixture_files(second);source=cls.root/('other' if second else 'first');source.mkdir()
            suffix='.exe' if os.name=='nt' else '';directory='engine/generated' if second else 'objects'
            script='automation/assemble.py' if second else 'assemble.py';levels=2 if second else 1
            base='os.path.realpath(__file__)'
            for _ in range(levels):base='os.path.dirname('+base+')'
            argv="['cargo','build','--profile','inspect','--no-default-features','-F','extra']" if second else "['cargo','build','--release']"
            cwd="os.path.join(ROOT,'engine')" if second else 'ROOT';profile='inspect' if second else 'release'
            files[script]=f'''import os,shutil,subprocess
ROOT={base}
os.putenv('CARGO_TARGET_DIR',os.path.join(ROOT,'{directory}'))
subprocess.run({argv},cwd={cwd})
shutil.copyfile(os.path.join(ROOT,'{directory}','{profile}','{name}{suffix}'),os.path.join(ROOT,'ship','renamed{suffix}'))
'''
            for path,body in files.items():
                dest=source/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
            native,receipt=capture(source,list(files),output=cls.root/('other-native' if second else 'native'),
                source_commit='authored-cargo-declared',expected_commit='authored-cargo-declared',context_key='native-'+str(second),
                cwd='engine' if second else '.',manifest=manifest,profile=profile,features=['extra'] if second else (),
                no_default_features=second,target_directory='generated' if second else 'objects',environment=env)
            if native['native_context']['status']!='built':raise AssertionError('Independent native oracle did not build')
            cls.cases.append((source,files,native,receipt,script))

    def graph(self,files):
        from adapters.rust_facts import Extractor
        g=python_fixtures.PythonPathValueTests().graph({p:s for p,s in files.items() if p.endswith('.py')})
        rust=Extractor({p:s.encode() for p,s in files.items() if p.endswith('.rs')},self.parser).build()
        for key in ('nodes','edges','diagnostics'):g[key].extend(rust[key])
        g.update(source_commit='authored-cargo-declared',input_paths=list(files));return g

    def project(self,source,files,output,graph=None,**kwargs):
        g=augment(graph or self.graph(files),root=source,paths=list(files),output=output,parser=self.parser,**kwargs)
        validate_graph(g);return g

    def test_two_layouts_and_renamed_targets_match_actual_native_compiler_outputs(self):
        for i,(source,files,native,receipt,_) in enumerate(self.cases):
            with self.subTest(layout=i):
                graph=self.project(source,files,self.root/('query-'+str(i)))
                expected=[n for n in graph['nodes'] if n['kind']=='build_artifact'];actual=[n for n in native['nodes'] if n['kind']=='build_artifact' and n['native_executable']]
                self.assertEqual([n['location'] for n in expected],[n['location'] for n in actual])
                target=next(n for n in graph['nodes'] if n['kind']=='build_target')
                self.assertEqual(target['profile']['debug_assertions'],bool(i))
                self.assertEqual(target['features_requested'],['extra'] if i else [])
                self.assertEqual(expected[0]['materialization'],'expected_output_not_built')
                self.assertFalse((self.root/('query-'+str(i))/'source'/expected[0]['location']['path']).exists())
                self.assertFalse((source/'Cargo.lock').exists())
                self.assertTrue(any(e['kind']=='CARGO_TARGET_SOURCE' for e in graph['edges']))
                if os.name!='nt':self.assertTrue(any(e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' for e in graph['edges']))
                queries=json.loads((self.root/('query-'+str(i))/'receipt.json').read_text())
                self.assertFalse(queries['product_compiled']);self.assertFalse(queries['build_scripts_executed'])
                self.assertTrue(any('--print' in c['command'] and 'file-names' in c['command'] for c in queries['commands']))

    def test_declared_source_to_packaging_chain_carries_configuration_conditions(self):
        source,files,_,_,_=self.cases[0]
        graph=copy_artifacts(bind_sources(self.project(source,files,self.root/'packaging')));validate_graph(graph)
        self.assertEqual(graph['cargo_source_bindings']['candidate_bindings'],1)
        shipped=[n for n in graph['nodes'] if n['kind']=='copied_artifact'];self.assertEqual(len(shipped),1)
        kinds={c['kind'] for c in shipped[0]['conditions']}
        self.assertIn('source_build_target_selection_equals_projection',kinds)
        self.assertIn('source_compiler_flags_preserve_cargo_binary_output_contract',kinds)
        self.assertIn('canonical_source_layout_required',kinds)
        self.assertTrue(any(e['kind']=='SOURCE_BUILD_REQUEST' for e in graph['edges']))

    def test_matching_native_capture_prevents_duplicate_expected_artifacts(self):
        source,files,native,receipt,_=self.cases[0];g=self.graph(files)
        native=copy.deepcopy(native)
        next(n for n in native['nodes'] if n['kind']=='build_configuration')['source_request']=receipt['source_request']
        for key in ('nodes','edges','diagnostics'):g[key].extend(native[key])
        graph=self.project(source,files,self.root/'native-present',graph=g)
        self.assertEqual(graph['cargo_declared_artifacts']['contexts'],[])
        self.assertFalse(any(n.get('materialization')=='expected_output_not_built' for n in graph['nodes']))
        self.assertEqual(len([n for n in graph['nodes'] if n['kind']=='build_artifact' and n['native_executable']]),1)

    def test_local_target_configuration_uses_the_explicit_target_directory_layout(self):
        source,files,_,old,_=self.cases[0];files=dict(files);files['.cargo/config.toml']='[build]\ntarget="'+old['host_target']+'"\n'
        # Keep authored source immutable; write this variant to its own copy.
        other=self.root/'configured';other.mkdir()
        for path,body in files.items():
            dest=other/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
        graph=self.project(other,files,self.root/'configured-query');context=graph['cargo_declared_artifacts']['contexts'][0]
        self.assertEqual(context['target_mode'],'explicit')
        output=next(n for n in graph['nodes'] if n['kind']=='build_artifact')
        self.assertIn('/'+old['host_target']+'/release/',output['location']['path'])
        env,_=native_fixtures.native_fixture_environment()
        actual,_=capture(other,list(files),output=self.root/'configured-native',source_commit='authored-cargo-declared',
            expected_commit='authored-cargo-declared',context_key='configured',target=old['host_target'],target_directory='objects',environment=env)
        native=next(n for n in actual['nodes'] if n['kind']=='build_artifact' and n['native_executable'])
        self.assertEqual(output['location'],native['location'])

    def test_unexpanded_configuration_and_missing_compiler_keep_required_gaps(self):
        source,files,_,_,_=self.cases[0]
        graph=self.project(source,files,self.root/'missing-rustc',rustc=str(self.root/'not-installed'))
        self.assertFalse(any(n['kind']=='build_artifact' for n in graph['nodes']))
        self.assertTrue(any(d['kind']=='cargo_declared_artifact_gap' and d['required'] for d in graph['diagnostics']))
        files=dict(files);files['.cargo/config.toml']='include=["extra.toml"]\n'
        other=self.root/'include-input';other.mkdir()
        for path,body in files.items():
            dest=other/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
        graph=self.project(other,files,self.root/'include-query')
        self.assertFalse(any(n['kind']=='build_artifact' for n in graph['nodes']))
        self.assertTrue(any('include requires native' in d.get('reason','') for d in graph['diagnostics']))

    def test_configuration_arrays_merge_and_extensionless_file_takes_precedence(self):
        source,files,_,native,_=self.cases[0];files=dict(files);triple=native['host_target']
        files['.cargo/config']='[build]\ntarget=["'+triple+'"]\n'
        files['.cargo/config.toml']='this is deliberately invalid and ignored\n'
        files['launch/.cargo/config.toml']='[build]\ntarget=["'+triple+'"]\n'
        files['assemble.py']=files['assemble.py'].replace('cwd=ROOT)',"cwd=os.path.join(ROOT,'launch'))")
        other=self.root/'config-arrays';other.mkdir()
        for path,body in files.items():
            dest=other/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
        graph=self.project(other,files,self.root/'config-arrays-query')
        self.assertEqual(len(graph['cargo_declared_artifacts']['contexts']),1)
        config=next(n for n in graph['nodes'] if n['kind']=='build_configuration')
        self.assertEqual(config['local_configurations'],['.cargo/config','launch/.cargo/config.toml'])

    def test_workspace_default_members_and_module_add_rename_delete_are_discovered(self):
        files={'Cargo.toml':'[workspace]\nmembers=["first","second"]\ndefault-members=["first"]\nresolver="2"\n',
            'first/Cargo.toml':'[package]\nname="original"\nversion="0.1.0"\n', 'first/src/main.rs':'fn main() {}\n',
            'second/Cargo.toml':'[package]\nname="other"\nversion="0.1.0"\n', 'second/src/main.rs':'fn main() {}\n',
            'build.py':"import os,subprocess\nROOT=os.path.dirname(os.path.realpath(__file__))\nsubprocess.run(['cargo','build'],cwd=ROOT)\n"}
        for step in range(4):
            source=self.root/('workspace-input-'+str(step));source.mkdir()
            for path,body in files.items():
                dest=source/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
            graph=self.project(source,files,self.root/('workspace-query-'+str(step)))
            names={n['name'] for n in graph['nodes'] if n['kind']=='build_target'}
            self.assertEqual(names,[{'original'},{'renamed'},{'renamed','added'},{'added'}][step])
            if step==0:files['first/Cargo.toml']=files['first/Cargo.toml'].replace('original','renamed')
            elif step==1:
                files['Cargo.toml']='[workspace]\nmembers=["first","second","third"]\ndefault-members=["first","third"]\nresolver="2"\n'
                files['third/Cargo.toml']='[package]\nname="added"\nversion="0.1.0"\n';files['third/src/main.rs']='fn main() {}\n'
            elif step==2:
                files['Cargo.toml']='[workspace]\nmembers=["second","third"]\ndefault-members=["third"]\nresolver="2"\n'
                del files['first/Cargo.toml'];del files['first/src/main.rs']


if __name__=='__main__':unittest.main()
