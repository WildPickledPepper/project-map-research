import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from adapters.cargo_file_api import normalize,link_source_symbols
from adapters.cargo_native import capture,read_messages
from adapters.rust_project import available,binary,tool_output
from adapters.sqlite_fact_graph import validate_graph


class BuildConfigurationTests(unittest.TestCase):
    def test_cmake_defaults_stay_compatible_and_cargo_contexts_are_detached_and_sorted(self):
        from adapters.build_configuration import configuration
        from adapters.cmake_project import configuration as cmake_configuration
        self.assertEqual(configuration(),cmake_configuration())
        contexts=[{'directory':str(Path.cwd()/'z'),'source_commit':'a'*40,'context_key':'z'},
                  {'directory':str(Path.cwd()/'a'),'source_commit':'b'*40,'context_key':'a'}]
        value={'version':1,'cargo':{'captures':contexts}};normalized=configuration(value)
        self.assertEqual([c['context_key'] for c in normalized['cargo']['captures']],['a','z'])
        contexts[0]['context_key']='changed';self.assertEqual(normalized['cargo']['captures'][1]['context_key'],'z')

    def test_invalid_capture_scope_and_ambiguous_identity_are_rejected(self):
        from adapters.snapshot_inputs import normalize_config
        base={'directory':str(Path.cwd()/'native'),'source_commit':'a'*40,'context_key':'native'}
        for captures in ([{**base,'directory':'relative'}],[{**base,'source_commit':'HEAD'}],
                         [base,base],[{**base,'extra':'field'}],[],[base]):
            with self.subTest(captures=captures):
                value={'version':1,'scope':{},'deployment':{},'build':{'version':1,'cargo':{'captures':captures}}}
                if captures in ([],[base]):self.assertIn('cargo',normalize_config(value)['build'])
                else:
                    with self.assertRaises(ValueError):normalize_config(value)


def native_fixture_environment():
    if os.name!='nt':return {},'fn main() {}\n'
    sysroot=Path(tool_output([binary('rustc'),'--print','sysroot'],Path.cwd()).strip())
    host=next(l[6:].strip() for l in tool_output([binary('rustc'),'-vV'],Path.cwd()).splitlines() if l.startswith('host: '))
    linker=sysroot/'lib/rustlib'/host/'bin/rust-lld.exe'
    if not linker.is_file():raise unittest.SkipTest('Bundled rust-lld needed for the SDK-independent Windows fixture')
    flags=['-C','linker='+str(linker),'-C','link-arg=/ENTRY:mainCRTStartup','-C','link-arg=/SUBSYSTEM:CONSOLE','-C','link-arg=/NODEFAULTLIB']
    return {'CARGO_ENCODED_RUSTFLAGS':'\x1f'.join(flags)},'''#![no_std]
#![no_main]
#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {loop {}}
#[no_mangle]
pub extern "C" fn mainCRTStartup() -> ! {loop {}}
pub fn main() {}
'''


def fixture_files(second=False):
    environment,code=native_fixture_environment()
    manifest='engine/Cargo.toml' if second else 'Cargo.toml'
    src='programs/boot.rs' if second else 'code/start.rs'
    name='renamed-tool' if second else 'neutral-worker'
    source_path='../programs/boot.rs' if second else 'code/start.rs'
    body=f'''[package]
name="neutral_package"
version="0.1.0"
edition="2021"
[[bin]]
name="{name}"
path="{source_path}"
[features]
default=["base"]
base=[]
extra=[]
[profile.dev]
panic="abort"
[profile.release]
panic="abort"
[profile.inspect]
inherits="release"
debug-assertions=true
'''
    return {manifest:body,src:code},environment,manifest,name


@unittest.skipUnless(available('cargo') and available('rustc'),'Native Cargo/rustc required')
class CargoFileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
            import tree_sitter_language_pack as pack
            pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
        cls.temp=tempfile.TemporaryDirectory(prefix='cargo native facts ');cls.addClassCleanup(cls.temp.cleanup)
        cls.root=Path(cls.temp.name);cls.cases=[]
        for second in (False,True):
            files,env,manifest,name=fixture_files(second);source=cls.root/('other-input' if second else 'input');source.mkdir()
            for path,body in files.items():
                dest=source/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(body,encoding='utf-8')
            output=cls.root/('other-native' if second else 'native')
            if second:env={**env,'CARGO_TARGET_DIR':'generated'}
            facts,receipt=capture(source,list(files),output=output,source_commit='authored-native',expected_commit='authored-native',
                context_key='second' if second else 'first',cwd='engine' if second else '.',manifest=manifest,
                profile='inspect' if second else 'release',features=['extra'] if second else (),no_default_features=second,
                target_directory=None if second else 'objects',environment=env)
            if facts['native_context']['status']!='built':raise AssertionError((output/'build.stderr').read_text()+(output/'build.stdout').read_text()[-4000:])
            cls.cases.append((source,output,facts,receipt,name,files))

    def recheck(self,metadata=None,messages=None,**overrides):
        source,output,facts,receipt,name,files=self.cases[0]
        args={k:receipt[k] for k in ('source_commit','returncode','context_key','host_target','target','host_cfg','target_cfg','cargo_version','rustc_version')}
        args.update(repository=output/'source',expected_commit='authored-native');args.update(overrides)
        return normalize(metadata or json.loads((output/'metadata.stdout').read_text()),
            messages if messages is not None else list(read_messages(output/'build.stdout')),**args)

    def test_two_native_layouts_keep_exact_filenames_features_and_profile(self):
        for index,(source,output,g,receipt,name,files) in enumerate(self.cases):
            with self.subTest(layout=index):
                validate_graph({**g,'snapshot':'authored-cargo'})
                target=next(n for n in g['nodes'] if n['kind']=='build_target');artifact=next(n for n in g['nodes'] if n['kind']=='build_artifact' and n['native_executable'])
                expected=('engine/generated/inspect/' if index else 'objects/release/')+name+('.exe' if os.name=='nt' else '')
                self.assertEqual(artifact['location'],{'root':'source','path':expected})
                self.assertTrue((output/'source'/expected).is_file());self.assertFalse((source/'objects').exists())
                self.assertEqual(target['profile']['debug_assertions'],bool(index))
                self.assertEqual(set(target['features']),{'extra'} if index else {'base','default'})
                self.assertEqual(receipt['returncode'],0);self.assertFalse(receipt['product_executable_run'])

    def test_native_target_sources_link_and_custom_entry_is_not_invented(self):
        import tree_sitter_language_pack as pack
        from adapters.rust_facts import Extractor
        source,output,g,receipt,name,files=self.cases[0];inputs={p:(source/p).read_bytes() for p in files if p.endswith('.rs')}
        source_facts=Extractor(inputs,pack.get_parser('rust')).build()
        edges,diagnostics=link_source_symbols(g,source_facts,root=source,parser=pack.get_parser('rust'))
        self.assertTrue(any(e['kind']=='CARGO_TARGET_SOURCE' for e in edges))
        if os.name=='nt':
            self.assertFalse(any(e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' for e in edges))
            self.assertTrue(any(d['kind']=='cargo_custom_entry_requires_linker_context' for d in diagnostics))
        else:self.assertTrue(any(e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' for e in edges))

    def source_graph(self,index=0):
        import tree_sitter_language_pack as pack
        from adapters.rust_facts import Extractor
        source,output,_,receipt,_,files=self.cases[index]
        inputs={p:(source/p).read_bytes() for p in files if p.endswith('.rs')}
        facts=Extractor(inputs,pack.get_parser('rust')).build()
        facts.update(source_commit=receipt['source_commit'],snapshot='authored-cargo-import',input_paths=list(files),extractors={})
        return facts,source,output

    def test_importer_binds_relocated_sources_and_validates_every_capture_before_mutation(self):
        import tree_sitter_language_pack as pack
        from adapters.cargo_artifact_graph import augment
        graph,source,output=self.source_graph();parser=pack.get_parser('rust')
        expected={'directory':str(output),'source_commit':graph['source_commit'],'context_key':'first'}
        good=augment(copy.deepcopy(graph),root=source,captures=[expected],parser=parser)
        self.assertTrue(any(e['kind']=='CARGO_TARGET_SOURCE' for e in good['edges']))
        self.assertEqual(good['native_build']['cargo_contexts'][0]['status'],'built')
        self.assertTrue(good['native_build']['cargo_contexts'][0]['root_relocated'])
        validate_graph(good)
        for changed in ({**expected,'source_commit':'other'},{**expected,'context_key':'other'}):
            trial=copy.deepcopy(graph)
            with self.assertRaisesRegex(ValueError,'differs'):augment(trial,root=source,captures=[expected,changed],parser=parser)
            self.assertEqual(trial,graph)
        trial=copy.deepcopy(graph);trial['input_paths']=[];before=copy.deepcopy(trial)
        with self.assertRaisesRegex(ValueError,'scope'):augment(trial,root=source,captures=[expected],parser=parser)
        self.assertEqual(trial,before)
        with self.assertRaisesRegex(ValueError,'already present'):augment(good,root=source,captures=[expected],parser=parser)

    def test_missing_root_and_macro_generated_default_entry_have_required_gaps(self):
        import tree_sitter_language_pack as pack
        from adapters.rust_facts import Extractor
        graph,source,output=self.source_graph();native=self.cases[0][2]
        _,gaps=link_source_symbols(native,{'nodes':[],'edges':[]},root=source,parser=pack.get_parser('rust'))
        self.assertTrue(any(g['kind']=='cargo_target_source_not_in_language_facts' and g['required'] for g in gaps))
        root=self.root/'entry-source';root.mkdir();path=next(p for p in graph['input_paths'] if p.endswith('.rs'))
        target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('macro_rules! entry { () => { fn main() {} } }\nentry!();\n')
        syntax=Extractor({path:target.read_bytes()},pack.get_parser('rust')).build()
        joins,gaps=link_source_symbols(native,syntax,root=root,parser=pack.get_parser('rust'))
        self.assertFalse(any(e['kind']=='EXECUTABLE_ENTRY_CANDIDATE' for e in joins))
        self.assertTrue(any(g['kind']=='cargo_default_entry_not_in_source_facts' for g in gaps))

    def test_failed_build_or_revision_mismatch_never_returns_partial_artifacts(self):
        for overrides in ({'returncode':1},{'expected_commit':'other'}):
            g=self.recheck(**overrides);self.assertFalse(g['nodes']);self.assertFalse(g['edges'])
            self.assertTrue(g['diagnostics'][0]['required'])

    def test_truncated_or_contradictory_stream_is_rejected(self):
        output=self.cases[0][1];messages=list(read_messages(output/'build.stdout'))
        for changed in ([m for m in messages if m.get('reason')!='build-finished'],messages+[{'reason':'build-finished','success':True}]):
            with self.subTest(records=len(changed)):self.assertEqual(self.recheck(messages=changed)['native_context']['status'],'unavailable')

    def test_target_and_package_identity_must_match_metadata(self):
        messages=list(read_messages(self.cases[0][1]/'build.stdout'))
        changed=copy.deepcopy(messages);record=next(m for m in changed if m.get('reason')=='compiler-artifact');record['target']['name']='unrelated'
        self.assertFalse(self.recheck(messages=changed)['nodes'])
        changed=copy.deepcopy(messages);record=next(m for m in changed if m.get('reason')=='compiler-artifact');record['manifest_path']=str(self.root/'other/Cargo.toml')
        self.assertFalse(self.recheck(messages=changed)['nodes'])

    def test_malformed_native_subrecords_and_cfg_do_not_publish_partial_facts(self):
        for field,value in [('profile',[]),('target',None),('filenames',None)]:
            changed=copy.deepcopy(list(read_messages(self.cases[0][1]/'build.stdout')))
            next(m for m in changed if m.get('reason')=='compiler-artifact')[field]=value
            with self.subTest(field=field):self.assertFalse(self.recheck(messages=changed)['nodes'])
        self.assertFalse(self.recheck(target_cfg=['unix','target_os="linux"'])['nodes'])

    def test_executable_must_be_present_in_native_output_list(self):
        changed=list(read_messages(self.cases[0][1]/'build.stdout'));changed=copy.deepcopy(changed)
        record=next(m for m in changed if m.get('reason')=='compiler-artifact');record['executable']=str(self.root/'unreported.exe')
        self.assertFalse(self.recheck(messages=changed)['nodes'])

    def test_unrecorded_dependency_and_message_budget_are_explicit(self):
        changed=list(read_messages(self.cases[0][1]/'build.stdout'));record=copy.deepcopy(next(m for m in changed if m.get('reason')=='compiler-artifact'))
        record['package_id']='external-dependency';changed.insert(0,record)
        g=self.recheck(messages=changed)
        self.assertEqual(g['native_context']['record_counts']['dependency_artifact_not_expanded'],1)
        self.assertFalse(self.recheck(max_records=1)['nodes'])

    def test_recorded_roots_relocate_without_changing_portable_artifact_identity(self):
        source,output,g,receipt,name,files=self.cases[0]
        relocated=self.recheck(repository=self.root/'relocated',recorded_repository=output/'source')
        self.assertEqual(relocated['nodes'],g['nodes']);self.assertTrue(relocated['native_context']['root_relocated'])

    def test_explicit_host_target_has_native_triple_subdirectory(self):
        source,_,_,old,name,files=self.cases[0];env,_=native_fixture_environment()
        facts,receipt=capture(source,list(files),output=self.root/'explicit',source_commit='authored-native',expected_commit='authored-native',
            context_key='explicit-host',profile='dev',target=old['host_target'],environment=env)
        self.assertEqual(facts['native_context']['status'],'built')
        artifact=next(n for n in facts['nodes'] if n['kind']=='build_artifact' and n['native_executable'])
        self.assertEqual(artifact['location']['path'],'target/'+old['host_target']+'/debug/'+name+('.exe' if os.name=='nt' else ''))
        self.assertEqual(receipt['target_mode'],'explicit')

    def test_failed_native_compilation_retains_receipt_without_partial_graph(self):
        source=self.root/'invalid';source.mkdir();(source/'Cargo.toml').write_text('[package]\nname="invalid"\nversion="0.1.0"\n')
        (source/'src').mkdir();(source/'src/main.rs').write_text('fn main( { syntax is invalid }')
        facts,receipt=capture(source,['Cargo.toml','src/main.rs'],output=self.root/'invalid-native',source_commit='authored-native',
            expected_commit='authored-native',context_key='invalid')
        self.assertNotEqual(receipt['returncode'],0);self.assertEqual(facts['nodes'],[]);self.assertEqual(facts['edges'],[])
        self.assertTrue((self.root/'invalid-native/build.stdout').is_file());self.assertFalse((source/'Cargo.lock').exists())

    def test_capture_rejects_outputs_outside_workspace_and_input_tree(self):
        source,_,_,_,_,files=self.cases[0]
        with self.assertRaisesRegex(ValueError,'outside the input export'):
            capture(source,list(files),output=source/'new-build',source_commit='a',expected_commit='a',context_key='unsafe')
        with self.assertRaisesRegex(ValueError,'target directory outside capture'):
            capture(source,list(files),output=self.root/'unsafe',source_commit='a',expected_commit='a',context_key='unsafe',
                target_directory='../../../escape')


if __name__=='__main__':unittest.main()
