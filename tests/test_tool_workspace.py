"""Tool lifecycle tests over independent temporary sources, without benchmark inputs."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from adapters.snapshot_inputs import commit
from adapters.snapshot_refresh import atomic_json
from projectmap.workspace import Workspace
from tests.refresh_worker import synthetic_builder, VERSION
from tests.test_project_map import fixture

ROOT=Path(__file__).resolve().parents[1]


def builder(source,request,output,log):
    result=synthetic_builder(source,request,output,log)
    path=output/'graph.json';graph=json.loads(path.read_text(encoding='utf-8'))
    graph['coverage']=[{'path':p,'status':'synthetic_test'} for p in request['input_paths']]
    path.write_text(json.dumps(graph),encoding='utf-8')
    return result


class ToolWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        self.git('init','-q');self.git('config','user.name','Tool test');self.git('config','user.email','test@example.invalid')
        self.git('config','core.autocrlf','false')
        self.write_commit('ui/a.ts','export function fetch(){return "原始";}')
        self.write_commit('server/a.cpp','void handle() {}')
        self.w=Workspace.create(self.root/'map',self.source)

    def git(self,*args):return subprocess.check_output(['git','-C',str(self.source),*args],stderr=subprocess.PIPE)

    def write_commit(self,path,text):
        dest=self.source/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')
        self.git('add','-A');self.git('commit','-qm','change')
        return commit(self.source)

    def build(self):return self.w.update(builder=builder,version=VERSION)

    def attach_chain(self):
        graph,_=fixture();graph=deepcopy(graph);revision=commit(self.source)
        graph.update(source_commit=revision,snapshot='tool-test',version={'source_commit':revision,'snapshot':'tool-test',
            'config':self.w.config['analysis'],'build_version':VERSION},provenance={'working_tree_included':False})
        path=self.root/'graph.json';atomic_json(path,graph);return self.w.attach(path)

    def test_create_read_only_source_and_no_history(self):
        before=self.git('status','--porcelain');self.build()
        self.assertEqual(before,self.git('status','--porcelain'))
        self.assertEqual(self.w.status()['historical_assets'],{'enabled':False})
        self.assertEqual(self.w.runtime()['items'],[])
        with self.assertRaisesRegex(ValueError,'outside'):Workspace.create(self.source/'state',self.source)

    def test_update_reuse_dirty_worktree_and_stale_rejection(self):
        first=self.build();self.assertEqual(first['status'],'ready')
        self.assertEqual(self.build()['status'],'unchanged')
        (self.source/'ui/a.ts').write_text('dirty',encoding='utf-8')
        status=self.w.status();self.assertTrue(status['worktree_has_changes']);self.assertFalse(status['worktree_included'])
        self.assertIn('原始',json.dumps(self.w.query('source',path='ui/a.ts',line=1),ensure_ascii=False))
        self.write_commit('ui/a.ts','export const renamed=2;')
        with self.assertRaisesRegex(ValueError,'outdated'):self.w.query('overview')
        self.assertEqual(self.w.query('overview',allow_stale=True)['workspace']['freshness'],'outdated')
        self.build();self.assertNotEqual(first['snapshot'],self.w.status()['active']['snapshot'])

    def test_failed_build_preserves_active_and_recovers(self):
        self.build();active=deepcopy(self.w.config['active']);self.write_commit('new/added.ts','export const added=1;')
        def fail(*args):raise RuntimeError('controlled build failure')
        result=self.w.update(builder=fail,version=VERSION)
        self.assertTrue(result['active_preserved']);self.assertEqual(self.w.status()['active'],active)
        self.assertEqual(self.build()['status'],'ready')
        self.assertTrue(self.w.query('search',text='added')['items'])

    def test_navigation_failure_preserves_old_and_retry_publishes_graph(self):
        self.build();active=deepcopy(self.w.config['active']);self.write_commit('ui/new.ts','export const newer=1;')
        with patch('projectmap.workspace.build_index',side_effect=OSError('index failure')):
            with self.assertRaises(OSError):self.build()
        status=self.w.status();self.assertEqual(status['active'],active);self.assertTrue(status['navigation_pending'])
        self.assertEqual(self.build()['status'],'ready');self.assertFalse(self.w.status()['navigation_pending'])

    def test_forward_reverse_source_and_snapshot_binding(self):
        self.attach_chain()
        self.assertTrue(self.w.query('path',start='api',target='handler')['found'])
        result=self.w.query('impact',start='handler',depth=4)
        self.assertTrue(any(e['source']=='api' for e in result['items']))
        self.assertIn('原始',json.dumps(self.w.query('source',start='api'),ensure_ascii=False))
        with self.assertRaises(ValueError):self.w.query('search',snapshot='another-snapshot')
        with self.assertRaises(ValueError):self.w.query('source',path='../secret')

    def test_cursor_cannot_cross_updates_or_queries(self):
        self.build();page=self.w.query('search',limit=1)
        with self.assertRaises(ValueError):self.w.query('search',text='other',limit=1,cursor=page['next_cursor'])
        self.write_commit('ui/new.ts','export const added=1;');self.build()
        with self.assertRaises(ValueError):self.w.query('search',limit=1,cursor=page['next_cursor'])

    def test_history_configuration_rejected(self):
        config=self.w.reload();config['historical_assets']['enabled']=True;atomic_json(self.w.file,config)
        with self.assertRaisesRegex(ValueError,'historical'):Workspace(self.w.directory)

    def test_snapshot_read_retries_transient_windows_sharing_conflict(self):
        from adapters.snapshot_refresh import read_json
        busy=PermissionError('atomic replacement in progress');busy.winerror=32
        with patch('pathlib.Path.read_text',side_effect=[busy,'{"published":true}']),patch('adapters.snapshot_refresh.time.sleep') as sleep:
            self.assertEqual(read_json(self.root/'state.json'),{'published':True});sleep.assert_called_once()

    def test_original_experiment_imports_same_query_implementation(self):
        import importlib
        from adapters.project_query import ProjectQuery
        self.assertIs(importlib.import_module('experiments.2026-10-24-p7.project_query').ProjectQuery,ProjectQuery)

    def test_runtime_overlay_requires_explicit_context(self):
        self.build()
        with self.assertRaisesRegex(ValueError,'explicit execution context'):
            self.w.runtime(record_id='a'*32)
        with self.assertRaises(ValueError):self.w.runtime(record_id='../x',context={})

    def test_cli_utf8_and_error_exit(self):
        self.attach_chain()
        base=[sys.executable,'-m','projectmap','--workspace',str(self.w.directory)]
        result=subprocess.run([*base,'query','source','--start','api'],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('原始',result.stdout.decode('utf-8'))
        failed=subprocess.run([*base,'query','path','--start','api'],capture_output=True)
        self.assertEqual(failed.returncode,2);self.assertIn('error',json.loads(failed.stderr))

    def test_skill_wrapper_missing_environment_does_not_install(self):
        result=subprocess.run([sys.executable,str(ROOT/'skills/project-map-assistant/scripts/project_map.py'),
            '--environment',str(self.root/'missing'),'--version'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertFalse((self.root/'missing').exists())

    def test_mcp_stdio_matches_cli_and_exposes_only_queries(self):
        try:
            from mcp import Client, StdioServerParameters
        except ImportError:self.skipTest('Optional MCP 2 extra is not installed')
        import asyncio
        self.attach_chain()
        parameters=StdioServerParameters(command=sys.executable,args=['-X','utf8','-m','projectmap',
            '--workspace',str(self.w.directory),'serve'],cwd=str(ROOT))
        async def check():
            async with Client(parameters) as client:
                listing=await client.list_tools()
                self.assertEqual({t.name for t in listing.tools},{'map_status','map_query','map_field_chain','map_runtime'})
                self.assertTrue(all(t.annotations.read_only_hint for t in listing.tools))
                result=await client.call_tool('map_status',{})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content['active']['snapshot'],self.w.status()['active']['snapshot'])
                traced=await client.call_tool('map_query',{'view':'path','start':'api','target':'handler'})
                self.assertFalse(traced.is_error);self.assertTrue(traced.structured_content['found'])
                self.assertFalse(traced.structured_content['workspace']['historical_assets_enabled'])
        asyncio.run(check())


if __name__=='__main__':unittest.main()
