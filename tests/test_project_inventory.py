"""Independent authored repository tests for scope discovery and committed input isolation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from adapters.project_inventory import build_inventory,write_inventory


class ProjectInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.source=self.base/'source';self.source.mkdir()
        self.git('init','-q');self.git('config','user.name','Scope test');self.git('config','user.email','test@example.invalid')
        self.git('config','core.autocrlf','false')
        self.save({
            'package.json':'{"name":"workspace","private":true}',
            'apps/dashboard/package.json':'{"name":"dashboard","main":"src/index.js"}',
            'apps/dashboard/src/index.js':'export function launch(){ return new WebSocket("ws://local"); }',
            'apps/dashboard/src/jobs/worker.ts':'self.onmessage = (event) => self.postMessage(event.data);',
            'plugins/tunnel/run.py':'import subprocess\nif __name__ == "__main__":\n    subprocess.run(["engine"])',
            'launcher/Cargo.toml':'[package]\nname="launcher"\nversion="1.0.0"\n[features]\ndefault=[]\nhttp=[]',
            'launcher/src/main.rs':'#[cfg(target_os = "linux")]\nfn main(){Command::new("engine");}',
            'native/src/CMakeLists.txt':'aux_source_directory(${SOURCE}/network SRC)\ninclude_directories(${SOURCE}/modules/metrics)',
            'native/src/network/socket.cpp':'void accept_peer(){ peer.listen(7); }',
            'native/src/modules/metrics/service.cpp':'void serve_metrics(){ peer.send("result"); }',
            'docs/help.py':'print("document helper")',
            'assets/picture.bin':'not a code file',
            'vendor/example/run.py':'subprocess.run(["must-not-be-product"])',
            'tests/negative/test_app.py':'def test_example(): assert 1',
        })

    def git(self,*args):return subprocess.check_output(['git','-C',str(self.source),*args],stderr=subprocess.PIPE)

    def save(self,files):
        for name,text in files.items():
            path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
        self.git('add','-A');self.git('commit','-qm','fixture')

    def build(self,revision='HEAD'):return build_inventory(self.source,revision,rules_version='synthetic_scope_test')

    def test_modules_not_coalesced_into_root_and_semantics_not_claimed(self):
        result=self.build();m={row['id']:row for row in result['module-inventory']['modules']}
        for root in ('apps/dashboard','plugins/tunnel','launcher','native/src/network','native/src/modules/metrics'):
            self.assertIn(root,m);self.assertTrue(m[root]['required_runtime_review'])
        self.assertEqual(m['plugins/tunnel']['semantic_support']['python'],'not_implemented')
        self.assertFalse(result['coverage-baseline']['semantic_graph_produced'])
        self.assertEqual(result['coverage-baseline']['overall_technical_acceptance'],'not_passed')
        self.assertFalse(m['docs']['required_runtime_review'])

    def test_nested_worker_separate_but_keeps_parent_and_caller_scope(self):
        result=self.build();m={row['id']:row for row in result['module-inventory']['modules']}
        worker=m['apps/dashboard/src/jobs'];self.assertEqual(worker['kind'],'background_worker')
        self.assertEqual(worker['parent'],'apps/dashboard')
        files={r['path']:r for r in result['module-inventory']['files']}
        self.assertEqual(files['apps/dashboard/src/index.js']['module'],'apps/dashboard')

    def test_boundary_candidates_have_source_but_no_invented_targets(self):
        result=self.build();rows=result['boundary-inventory']['boundaries']
        starts=[r for r in rows if r['family']=='process_start']
        self.assertEqual({r['module'] for r in starts},{'launcher','plugins/tunnel'})
        self.assertTrue(all(r['counterpart'] is None and r['resolution']=='not_semantically_extracted' for r in rows))
        self.assertTrue(all(r['evidence']['path'] and r['evidence']['line']>0 for r in rows))

    def test_all_files_accounted_for_and_external_separate(self):
        result=self.build();rows=result['module-inventory']['files']
        expected=set(self.git('ls-tree','-r','--name-only','HEAD').decode().splitlines())
        self.assertEqual({r['path'] for r in rows},expected)
        external=next(r for r in rows if r['path']=='vendor/example/run.py')
        self.assertEqual(external['scope_role'],'third_party')
        self.assertFalse(any(r['module']=='vendor' for r in result['boundary-inventory']['boundaries']))

    def test_dirty_and_future_files_not_part_of_pinned_inventory(self):
        first=self.git('rev-parse','HEAD').decode().strip()
        (self.source/'plugins/tunnel/run.py').write_text('uncommitted replacement',encoding='utf-8')
        (self.source/'untracked.py').write_text('subprocess.run([])',encoding='utf-8')
        result=self.build(first)
        self.assertTrue(any(r['module']=='plugins/tunnel' and r['family']=='process_start' for r in result['boundary-inventory']['boundaries']))
        self.assertFalse(any(r['path']=='untracked.py' for r in result['module-inventory']['files']))
        self.assertFalse(result['module-inventory']['working_tree_included'])

    def test_new_module_rename_and_delete_change_denominator_automatically(self):
        first=self.build();self.save({'services/renamed/main.py':'if __name__ == "__main__":\n    print("new")'})
        second=self.build();self.assertGreater(second['coverage-baseline']['summary']['required_runtime_components'],first['coverage-baseline']['summary']['required_runtime_components'])
        self.git('mv','services/renamed','services/changed');self.git('commit','-qm','rename')
        third=self.build();ids={r['id'] for r in third['module-inventory']['modules']}
        self.assertIn('services/changed',ids);self.assertNotIn('services/renamed',ids)
        self.git('rm','-r','services/changed');self.git('commit','-qm','remove')
        self.assertNotIn('services/changed',{r['id'] for r in self.build()['module-inventory']['modules']})

    def test_artifacts_modes_and_eighteen_mechanisms_do_not_assert_execution(self):
        result=self.build();folder=self.base/'output';write_inventory(result,folder)
        self.assertEqual(len(list(folder.glob('*.json'))),5)
        self.assertEqual(len(result['mechanism-matrix']['mechanisms']),18)
        self.assertEqual(len(result['mechanism-matrix']['items']),18*len(result['module-inventory']['modules']))
        self.assertEqual(result['runtime-modes']['required_modes'],[])
        self.assertEqual(result['runtime-modes']['freeze_status'],'pending_independent_review')
        with self.assertRaises(ValueError):write_inventory(result,folder)

    def test_arbitrary_layout_new_entry_and_barrel_need_no_named_container(self):
        self.save({'odd_shape/extra_unit/launch.py':'if __name__ == "__main__":\n    print("entry")',
            'odd_shape/shared_widget/index.js':'export function widget(){return 1;}',
            'odd_shape/client/entry.ts':'import {widget} from "../shared_widget"; export const value=widget();'})
        result=self.build();modules={m['id']:m for m in result['module-inventory']['modules']}
        self.assertIn('odd_shape/extra_unit',modules);self.assertIn('odd_shape/shared_widget',modules)
        self.assertTrue(modules['odd_shape/extra_unit']['required_runtime_review'])
        self.assertTrue(modules['odd_shape/shared_widget']['required_runtime_review'])
        self.assertFalse(result['coverage-baseline']['independent_reference_used_for_generation'])

    def test_new_unsupported_runtime_language_is_a_required_gap(self):
        self.save({'apps/new_engine/main.go':'package main\nfunc main() { println("new") }'})
        result=self.build();modules={m['id']:m for m in result['module-inventory']['modules']}
        self.assertEqual(modules['apps/new_engine']['semantic_support']['go'],'not_implemented')
        self.assertIn('go',result['coverage-baseline']['whole_project_languages_missing'])
        self.assertEqual(result['coverage-baseline']['overall_technical_acceptance'],'not_passed')

    def test_embedded_shader_or_example_text_does_not_create_program_module(self):
        self.save({'apps/dashboard/src/shaders/vertex.ts':'export const shader = `\nvoid main() { gl_Position=vec4(0); }\n`;',
            'odd_shape/docsample.py':'example = """\nif __name__ == "__main__":\n    pass\n"""'})
        rows=self.build()['module-inventory']['modules'];modules={m['id'] for m in rows}
        self.assertNotIn('apps/dashboard/src/shaders',modules)
        self.assertFalse(any(e['kind']=='declared_program_entry' for m in rows if m['id']=='odd_shape' for e in m['discovery_evidence']))


if __name__=='__main__':unittest.main()
