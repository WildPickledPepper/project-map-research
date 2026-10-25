"""Whole-tree discovery, parser failures and resumable execution on authored Git fixtures."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from adapters.repository_discovery import discover, generated_config, policy
from adapters.snapshot_inputs import select_inputs, normalize_config
from scripts.discover_repository import run, Worker

ROOT = Path(__file__).resolve().parents[1]


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.repo = self.base/'repo'; self.repo.mkdir()
        self.git('init', '-q'); self.git('config', 'user.name', 'Discovery fixture')
        self.git('config', 'user.email', 'test@example.invalid'); self.git('config', 'core.autocrlf', 'false')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE)

    def save(self, files):
        for name, body in files.items():
            target = self.repo/name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body.encode('utf-8') if isinstance(body, str) else body)
        self.git('add', '-A'); self.git('commit', '-qm', 'authored fixture')
        return self.git('rev-parse', 'HEAD').decode().strip()

class DiscoveryTests(FixtureCase):
    def test_scope_roles_modules_and_unsupported_files_are_accounted_for(self):
        revision = self.save({'package.json':'{}','src/a.ts':'export function entry(){}',
            'backend/CMakeLists.txt':'project(service)', 'backend/a.h':'struct Q {};',
            'backend/main.cxx':'int main() {}','tests/a.test.ts':'let test=1;',
            'scripts/codegen.ts':'let gen=1;', 'vendor/lib.cpp':'int external;',
            'generated/a.ts':'let generated=1;', 'tools/check.py':'pass', 'platform/main.rs':'fn main(){}',
            'src/legacy.js':'const x=1;', 'docs/readme.md':'doc'})
        d = discover(self.repo, revision); rows = {r['path']:r for r in d['files']}
        self.assertEqual(len(rows),13)
        self.assertEqual(rows['backend/a.h']['module'],'backend')
        self.assertEqual(rows['tests/a.test.ts']['role'],'test')
        self.assertEqual(rows['scripts/codegen.ts']['role'],'build_tool')
        self.assertTrue(rows['src/legacy.js']['eligible'])
        self.assertTrue(rows['tools/check.py']['eligible'])
        for name in ('vendor/lib.cpp','generated/a.ts','platform/main.rs','docs/readme.md'):
            self.assertEqual(rows[name]['status'],'excluded')
            self.assertTrue(rows[name]['reason'])
        config = normalize_config(generated_config(d))
        selected = select_inputs(self.repo, revision, config)
        self.assertEqual({r['path'] for r in selected['files']},{r['path'] for r in d['files'] if r['eligible']})

    def test_new_module_rename_and_delete_are_discovered_without_changing_policy(self):
        old = self.save({'src/old.ts':'export interface Before{}'})
        self.save({'new-module/package.json':'{"name":"fresh"}','new-module/src/entry.ts':'export function fresh(){}'})
        self.git('mv','src/old.ts','src/renamed.ts'); self.git('commit','-qm','rename')
        changed = discover(self.repo)
        paths = {r['path']:r for r in changed['files']}
        self.assertIn('new-module/src/entry.ts', paths)
        self.assertEqual(paths['new-module/src/entry.ts']['module'],'new-module')
        self.assertNotIn('src/old.ts', paths)
        self.assertIn('src/old.ts',{r['path'] for r in discover(self.repo,old)['files']})
        self.git('rm','src/renamed.ts');self.git('commit','-qm','delete')
        self.assertNotIn('src/renamed.ts',{r['path'] for r in discover(self.repo)['files']})

    def test_dirty_worktree_and_archive_attributes_do_not_change_fixed_input(self):
        old = self.save({'src/a.ts':'old', '.gitattributes':'src/a.ts export-ignore\n'})
        self.save({'src/a.ts':'new','src/new.ts':'new'})
        (self.repo/'src/a.ts').write_text('dirty',encoding='utf-8')
        d = discover(self.repo, old)
        self.assertEqual([r['path'] for r in d['files'] if r['eligible']],['src/a.ts'])
        self.assertFalse(d['provenance']['working_tree_included'])

    def test_policy_exclusions_size_limit_and_git_symlinks_have_reasons(self):
        self.save({'a.ts':'x'*12,'b.cpp':'int n;', 'scripts/tool.ts':'let n=1;', 'blob':'../../external'})
        blob=self.git('rev-parse','HEAD:blob').decode().strip()
        self.git('update-index','--add','--cacheinfo',f'120000,{blob},link.ts');self.git('commit','-qm','link')
        d=discover(self.repo,configuration={'max_file_bytes':10,'exclude':['b.cpp'],'roles':['product']})
        rows={r['path']:r for r in d['files']}
        self.assertEqual(rows['a.ts']['reason'],'file_size_budget')
        self.assertEqual(rows['b.cpp']['reason'],'excluded_by_policy')
        self.assertEqual(rows['scripts/tool.ts']['reason'],'excluded_role:build_tool')
        self.assertEqual(rows['link.ts']['reason'],'unsupported_git_mode')
        for bad in ({'unknown':1},{'max_file_bytes':0},{'roles':['guess']},{'exclude':'*'}):
            with self.assertRaises(ValueError):policy(bad)


class ExtractionTests(FixtureCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ts=Path(subprocess.check_output(['node','-p','require.resolve("typescript")'],cwd=ROOT,
                stderr=subprocess.PIPE,text=True).strip())
        except (OSError,subprocess.CalledProcessError):
            raise unittest.SkipTest('Pinned TypeScript installation required')

    def execute(self, output='out', **kwargs):
        return run(self.repo,'HEAD',self.base/output,self.ts,version={'rules':'authored-test'},**kwargs)

    def fixture(self):
        return self.save({'package.json':'{"name":"fixture","main":"src/main.ts"}',
            'tsconfig.json':'{ // config\n "compilerOptions":{"strict":true},"include":["src"],}',
            'src/main.ts':'''// function fake() { registry.register("fake", f); }
                export interface Payload { key: string; }
                export function entry(p:Payload){ registry.register('alpha',p); }
                const text="function fake2(){}";''',
            'native/CMakeLists.txt':'project(service)\nfile(GLOB SOURCES "*.cpp")\nadd_executable(service ${SOURCES})',
            'native/query.h':'namespace other { struct Store { virtual bool query(int key)=0; int cached; }; }',
            'native/main.cpp':'int main() { registry.emplace("alpha", target); }'})

    def facts(self, path, output='out'):
        d=json.loads((self.base/output/'discovery.json').read_text(encoding='utf-8'))
        row=next(r for r in d['files'] if r['path']==path)
        return row,json.loads((self.base/output/row['facts']).read_text(encoding='utf-8'))['facts']

    def test_existing_parsers_recover_interfaces_candidates_and_build_metadata(self):
        self.fixture(); result=self.execute()
        self.assertEqual(result['status'],'complete_with_diagnostics')
        row,facts=self.facts('src/main.ts')
        self.assertEqual(row['build_context']['build_membership'],'included_in_config_file_set')
        self.assertIn('Payload',{s['name'] for s in facts['interfaces']})
        self.assertEqual([c['callee'] for c in facts['registrations']],['registry.register'])
        self.assertNotIn('fake',{s['name'] for s in facts['symbols']})
        row,cpp=self.facts('native/query.h')
        self.assertTrue(any(s['pure_virtual'] for s in cpp['interfaces']))
        self.assertTrue(cpp['resources']);self.assertIsNone(cpp['sha256_lf_utf8'])
        self.assertEqual(row['build_context']['compile_commands_status'],'missing')
        self.assertTrue(self.facts('native/main.cpp')[1]['entries'])
        cmake=self.facts('native/CMakeLists.txt')[1]
        self.assertTrue(any(c['command']=='file' for c in cmake['commands']))

    def test_python_sources_use_the_python_worker_and_keep_main_guard(self):
        self.save({'unit/pyproject.toml':'[project]\nname="standalone"\nversion="1"',
            'unit/run.py':'from . import helper\nasync def start(value): return await helper.run(value)\nif __name__ == "__main__":\n start(2)\n',
            'unit/helper.pyi':'async def run(value:int)->int: ...\n'})
        result=self.execute();self.assertEqual(result['status'],'complete_with_diagnostics')
        row,facts=self.facts('unit/run.py')
        self.assertEqual(row['status'],'parsed');self.assertEqual(facts['language'],'python')
        self.assertEqual([r['name'] for r in facts['symbols']],['start'])
        self.assertEqual(facts['entries'][0]['kind'],'python_main_guard')
        self.assertEqual(row['build_context']['manifests'],['unit/pyproject.toml'])
        self.assertEqual(row['build_context']['build_membership'],'python_source_context_not_package_install_proof')
        self.assertEqual(self.facts('unit/helper.pyi')[1]['status'],'parsed')

    def test_javascript_variants_are_exported_and_parsed_with_correct_grammar(self):
        self.save({'package.json':'{"name":"mixed-fixture"}',
            'src/entry.jsx':'export function View(){return <section/>;}',
            'src/worker.mjs':'export async function load(){return import("./lib.cjs");}',
            'src/lib.cjs':'exports.run = function run(){return 1;};'})
        result=self.execute();self.assertEqual(result['status'],'complete_with_diagnostics')
        for name in ('src/entry.jsx','src/worker.mjs','src/lib.cjs'):
            row,facts=self.facts(name)
            self.assertEqual(row['language'],'javascript');self.assertEqual(row['status'],'parsed')
            self.assertTrue(facts['symbols']);self.assertFalse(facts['diagnostics'])
            self.assertTrue((self.base/'out/source'/name).is_file())

    def test_budget_resume_preserves_facts_and_rejects_changed_input(self):
        self.fixture(); first=self.execute(max_files=2)
        self.assertEqual(first['status'],'partial')
        self.assertTrue(first['statuses'].get('pending_budget'))
        records=list((self.base/'out/facts').glob('*.json'))
        before={p.name:p.read_bytes() for p in records}
        second=self.execute(resume=True)
        self.assertEqual(second['status'],'complete_with_diagnostics')
        for name,body in before.items():self.assertEqual((self.base/'out/facts'/name).read_bytes(),body)
        self.save({'new/entry.ts':'export function next(){}'})
        with self.assertRaisesRegex(ValueError,'Source/rules version changed'):self.execute(resume=True)

    def test_errors_are_per_file_and_intact_files_still_extract(self):
        self.save({'broken.ts':'export function {', 'bad.ts':b'\xff', 'binary.cpp':b'\0',
            'good.ts':'export function alive(){}','bad/package.json':'{"oops":'})
        result=self.execute()
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['statuses']['syntax_errors'],1)
        self.assertEqual(result['statuses']['invalid_encoding'],1)
        self.assertEqual(result['statuses']['binary_input'],1)
        self.assertEqual(result['statuses']['manifest_error'],1)
        self.assertEqual(self.facts('good.ts')[1]['symbols'][0]['name'],'alive')

    def test_worker_timeout_and_exit_are_explicit_and_retryable(self):
        self.save({'a.cpp':'int alive() {return 1;}'})
        class FailedWorker:
            def __init__(self,*args):pass
            def request(self,*args):raise TimeoutError()
            def close(self):pass
        result=self.execute(worker_factory=FailedWorker)
        self.assertEqual(result['statuses']['worker_timeout'],1)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(self.execute(resume=True)['statuses']['worker_timeout'],1)
        result=self.execute(resume=True,retry_errors=True)
        self.assertEqual(result['statuses']['parsed'],1)
        self.assertEqual(self.facts('a.cpp')[1]['symbols'][0]['name'],'alive')
        class ExitedWorker(FailedWorker):
            def request(self,*args):raise ChildProcessError()
        exited=self.execute(output='exited',worker_factory=ExitedWorker)
        self.assertEqual(exited['statuses']['worker_exit'],1)

    def test_added_interface_is_extracted_on_next_automatic_plan(self):
        self.fixture(); self.execute()
        self.save({'fresh/package.json':'{"name":"unseen"}',
                   'fresh/src/provider.ts':'export interface NewPayload{value:number}; export function added(){hub.subscribe("new",handler)}'})
        result=self.execute(output='new-version')
        self.assertEqual(result['eligible_sources'],4)
        row,facts=self.facts('fresh/src/provider.ts','new-version')
        self.assertEqual(row['module'],'fresh')
        self.assertIn('NewPayload',{i['name'] for i in facts['interfaces']})
        self.assertEqual(facts['registrations'][0]['callee'],'hub.subscribe')
        self.assertEqual(row['build_context']['build_membership'],'outside_or_unresolved_config_file_sets')

    def test_real_worker_deadline_kills_blocking_process(self):
        with (self.base/'errors.log').open('w') as errors:
            worker=Worker([os.sys.executable,'-u','-c','import sys,time;sys.stdin.readline();time.sleep(10)'],errors)
            with self.assertRaises(TimeoutError):worker.request({'path':'slow'},0.1)
            self.assertIsNotNone(worker.process.poll())
            worker.close()


if __name__=='__main__':unittest.main()
