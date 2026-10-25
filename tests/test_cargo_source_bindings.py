import copy
import unittest
from adapters.cargo_source_bindings import augment,interpret,parse_build
from tests import test_python_path_values as fixtures


class CargoSourceBindingTests(unittest.TestCase):
    host={'name':'Linux','path_style':'posix'}

    def graph(self,body,script='make.py',manifest='Cargo.toml'):
        g=fixtures.PythonPathValueTests().graph({script:body})
        g.update(source_commit='authored-source',input_paths=[script,manifest])
        return g

    def spec(self,g,host=None):
        host=host or self.host
        inv=next(n for n in g['nodes'] if n['kind']=='python_process_invocation' and n['path_style']==host['path_style'])
        effects=[n for n in g['nodes'] if n['kind']=='python_environment_effect']
        return interpret(inv,effects,host_system=host,input_paths=g['input_paths'])

    def source(self,extra='',argv="['cargo','build','--release']",cwd='ROOT'):
        return "import os,subprocess\nROOT=os.path.dirname(os.path.realpath(__file__))\n"+extra+f"\nsubprocess.run({argv},cwd={cwd})\n"

    def config(self,**changes):
        row={'id':'native-cargo','kind':'build_configuration','language':'cargo','name':'native','path':'Cargo.toml','line':1,
            'target_directory':{'root':'source','path':'objects'},
            'target_system':{'name':'Linux','host_name':'Linux','host_path_style':'posix','target':'actual-native-target'},
            'source_request':{'cwd':'.','manifest':'Cargo.toml','profile':'release','features':[],
                'no_default_features':False,'target_mode':'default','target':None}}
        row.update(changes);return row

    def test_command_line_features_profile_paths_and_unknown_options(self):
        spec=parse_build(['cargo.exe','build','--profile=inspect','--manifest-path','engine/Cargo.toml',
            '--target-dir=objects','--target','a-triple','--features','alpha,beta gamma','-Fdelta','-F=epsilon','--no-default-features'])
        self.assertEqual(spec['features'],['alpha','beta','delta','epsilon','gamma']);self.assertEqual(spec['profile'],'inspect')
        self.assertEqual(spec['manifest'],'engine/Cargo.toml');self.assertFalse(spec['gaps'])
        for argv in (['cargo','build','--profile'],['cargo','build','--release','--profile','inspect'],
                     ['cargo','build','--target','a','--target','b'],['cargo','build','--config','key=true'],['cargo','run']):
            with self.subTest(argv=argv):self.assertTrue(parse_build(argv)['gaps'])
        self.assertIsNone(parse_build(['unrelated','build']))

    def test_two_source_layouts_preserve_manifest_cwd_and_environment_provenance(self):
        for script,folder in [('make.py','engine'),('automation/package.py','modules/renamed')]:
            extra="os.putenv('CARGO_TARGET_DIR',os.path.join(ROOT,'objects'))"
            g=self.graph(self.source(extra,cwd=f"os.path.join(ROOT,'{folder}')"),script=script,
                manifest=('automation/' if '/' in script else '')+folder+'/Cargo.toml')
            spec=self.spec(g)
            base='automation/' if '/' in script else ''
            self.assertFalse(spec['gaps']);self.assertEqual(spec['cwd'],base+folder)
            self.assertEqual(spec['manifest'],base+folder+'/Cargo.toml');self.assertEqual(spec['target_directory'],base+'objects')
            self.assertIn('writer',spec['environment_sources']['CARGO_TARGET_DIR'])
            self.assertTrue(any(c['kind']=='canonical_source_layout_required' for c in spec['conditions']))

    def test_cli_output_directory_overrides_source_environment_and_relative_manifest_uses_cwd(self):
        g=self.graph(self.source("os.putenv('CARGO_TARGET_DIR','other')",argv="['cargo','build','--target-dir','../objects','--manifest-path','Cargo.toml']",
            cwd="os.path.join(ROOT,'engine')"),manifest='engine/Cargo.toml')
        spec=self.spec(g);self.assertFalse(spec['gaps']);self.assertEqual(spec['target_directory'],'objects')
        self.assertEqual(spec['target_directory_basis'],'command_line');self.assertEqual(spec['manifest'],'engine/Cargo.toml')

    def test_unbound_cwd_shell_and_unknown_options_block_context_edges(self):
        bodies=[self.source(cwd="'relative'"),self.source(argv="['cargo','build','--mystery']"),
            self.source().replace('cwd=ROOT','cwd=ROOT,shell=True')]
        for body in bodies:
            g=self.graph(body);g['nodes'].append(self.config());out=augment(g)
            self.assertFalse(any(e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE' for e in out['edges']))
            self.assertTrue(any(d['kind']=='cargo_source_request_unresolved' and d['required'] for d in out['diagnostics']))

    def test_capture_bindings_require_full_source_context_and_keep_conditional_unknowns(self):
        g=self.graph(self.source("os.putenv('CARGO_TARGET_DIR',os.path.join(ROOT,'objects'))"))
        g['nodes'].append(self.config());out=augment(g)
        bindings=[e for e in out['edges'] if e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE'];self.assertEqual(len(bindings),1)
        self.assertEqual(bindings[0]['status'],'conditional_candidate');self.assertEqual(bindings[0]['runtime_execution'],'not_observed')
        kinds={c['kind'] for c in bindings[0]['conditions']}
        self.assertIn('source_process_invocation_reached_and_succeeds',kinds)
        self.assertIn('source_build_target_environment_and_config_equal_native_capture',kinds)
        self.assertIn('canonical_source_layout_required',kinds)
        for change in ({'target_directory':{'root':'source','path':'other'}},
                       {'source_request':{**self.config()['source_request'],'manifest':'unrelated/Cargo.toml'}}):
            trial=self.graph(self.source("os.putenv('CARGO_TARGET_DIR',os.path.join(ROOT,'objects'))"))
            trial['nodes'].append(self.config(**change));trial=augment(trial)
            self.assertFalse(any(e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE' for e in trial['edges']))
            self.assertTrue(any(d['kind']=='cargo_source_context_not_matched' and d['required'] for d in trial['diagnostics']))

    def test_explicit_target_requires_native_explicit_mode_and_preserves_environment_selection(self):
        body=self.source("os.putenv('CARGO_BUILD_TARGET','actual-native-target')")
        g=self.graph(body);native=self.config();native['source_request'].update(target_mode='explicit',target='actual-native-target')
        g['nodes'].append(native);out=augment(g)
        self.assertTrue(any(e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE' for e in out['edges']))
        g=self.graph(body);g['nodes'].append(self.config());out=augment(g)
        self.assertFalse(any(e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE' for e in out['edges']))

    def test_multiple_native_profiles_do_not_turn_excluded_pairings_into_required_gaps(self):
        g=self.graph(self.source());g['nodes'].append(self.config())
        other=copy.deepcopy(self.config());other['id']='dev-context';other['source_request']['profile']='dev';g['nodes'].append(other)
        out=augment(g);self.assertEqual(out['cargo_source_bindings']['candidate_bindings'],1)
        self.assertFalse(any(d.get('required') for d in out['diagnostics'] if d['kind'].startswith('cargo_source')))
        with self.assertRaisesRegex(ValueError,'already present'):augment(out)

    def test_windows_host_selection_does_not_use_the_analysis_environment(self):
        body=self.source("os.putenv('cargo_target_dir',os.path.join(ROOT,'native'))",
            argv="['cargo.exe','build','--release','--manifest-path','engine\\\\Cargo.toml']")
        g=self.graph(body,manifest='engine/Cargo.toml');spec=self.spec(g,{'name':'Windows','path_style':'windows'})
        self.assertFalse(spec['gaps']);self.assertEqual(spec['manifest'],'engine/Cargo.toml')
        self.assertEqual(spec['target_directory'],'native');self.assertEqual(spec['target_directory_basis'],'source_environment')

    def test_conditional_or_replaced_environment_has_explicit_context_preconditions(self):
        extra="os.putenv('CARGO_TARGET_DIR','initial')\nif os.getenv('OTHER'): os.putenv('CARGO_TARGET_DIR','later')"
        spec=self.spec(self.graph(self.source(extra)))
        self.assertFalse(spec['environment_sources']['CARGO_TARGET_DIR']['known'])
        self.assertIsNone(spec['target_directory']);self.assertEqual(spec['target_directory_basis'],'native_context_required')
        self.assertTrue(any(c['kind']=='source_target_directory_environment_and_config_equal_native_capture' for c in spec['conditions']))


if __name__=='__main__':unittest.main()
