"""Run actual refresh/navigation updates in a small authored project."""
import argparse
from functools import partial
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import build_index, ProjectMap
from adapters.repository_discovery import discover
from adapters.snapshot_refresh import Refresher, read_snapshot
from scripts.build_project_snapshot import build, build_version
from tests.test_cpp_protocol import SOURCE

CLIENT = '''declare const channel:WebSocket;declare const bridge:{invoke:(x:string)=>void};
function bind(){return (tag:string)=>channel.send(JSON.stringify({wireTag:tag,space:'north'}));}
bridge.invoke=bind();export function entry(){bridge.invoke('a4/one');}
'''


def run(output, typescript):
    output.mkdir(parents=True, exist_ok=False)
    source = output/'source'
    source.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE).decode().strip()
    git('init', '-q'); git('config', 'user.name', 'A4 updates'); git('config', 'user.email', 'test@example.invalid')
    git('config', 'core.autocrlf', 'false')
    configuration = {'version': 1, 'scope': {'discovery': {}}, 'storage': 'json', 'deployment': {'services': [
        {'id': 'one', 'consumer_paths': ['front-one'], 'provider_paths': ['back-one']},
        {'id': 'two', 'consumer_paths': ['front-two'], 'provider_paths': ['back-two']}]}}
    version = build_version(typescript)
    events, cases, checks = [], {}, {}
    refresher = Refresher(source, output/'store', lambda: configuration, lambda: version,
        partial(build, typescript=typescript), on_event=events.append)
    files = {'front-one/package.json': '{"name":"a4-one"}', 'front-one/api.ts': CLIENT,
        'back-one/CMakeLists.txt': 'project(a4_one)', 'back-one/provider.cpp': 'namespace One {\n' + SOURCE.replace('alpha/read', 'a4/one') + '\n}'}
    def commit(contents, message):
        tracked = git('ls-files', '-z').split('\0')
        for path in tracked:
            if path and path not in contents: git('rm', '--', path)
        for path, text in contents.items():
            dest = source/path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding='utf-8', newline='\n')
        git('add', '-A'); git('commit', '-qm', message)
    def step(name):
        state = refresher.run()
        if state['status'] != 'up_to_date':
            cases[name] = {'status': state['status'], 'error_type': state['last_error']['type']}
            raise ValueError('Refresh failed at ' + name)
        location = Path(read_snapshot(output/'store')['directory'])
        graph = json.loads((location/'graph.json').read_text(encoding='utf-8'))
        index = output/(name + '.sqlite')
        build_index(graph, discover(source, graph['source_commit']), index,
            navigation_version={'schema': 'project-map/1', 'experiment': 'A4 fixture'})
        q = ProjectMap(index)
        entries = q.entries(limit=100)['items']
        cases[name] = {'source_commit': graph['source_commit'], 'snapshot': graph['snapshot'],
            'inputs': graph['input_paths'], 'entries': entries, 'modules': len(q.overview(limit=100)['items']),
            'nodes': len(graph['nodes']), 'edges': len(graph['edges'])}
        return graph, q, state
    commit(files, 'baseline')
    original, q, first = step('baseline')
    old_cursor = q.search(limit=1)['next_cursor']; q.close()
    checks['baseline_protocol_matches'] = cases['baseline']['entries'][0]['status'] == 'matched_conditional'
    files.update({'front-two/package.json': '{"name":"a4-two"}',
        'front-two/api.ts': CLIENT.replace('a4/one', 'a4/two'),
        'back-two/CMakeLists.txt': 'project(a4_two)',
        'back-two/provider.cpp': 'namespace Two {\n' + SOURCE.replace('alpha/read', 'a4/two') + '\n}'})
    commit(files, 'new module and interface')
    graph, q, added = step('module_added')
    checks['new_module_and_interface_discovered'] = len(graph['input_paths']) == 8 and len(cases['module_added']['entries']) == 2 and all(
        e['status'] == 'matched_conditional' for e in cases['module_added']['entries'])
    try:
        q.search(cursor=old_cursor)
        checks['old_cursor_rejected_by_new_snapshot'] = False
    except ValueError:
        checks['old_cursor_rejected_by_new_snapshot'] = True
    q.close()
    files['front-two/client.ts'] = files.pop('front-two/api.ts').replace('function entry()', 'function renamedEntry()').replace('a4/two', 'a4/renamed')
    files['back-two/renamed.cpp'] = files.pop('back-two/provider.cpp').replace('a4/two', 'a4/renamed').replace('SpecificWork', 'ChangedWork')
    commit(files, 'rename file symbol and command')
    renamed, q, state = step('renamed')
    checks['renamed_interface_reconnects'] = any(e['name'] == 'renamedEntry' and e['status'] == 'matched_conditional' for e in cases['renamed']['entries'])
    checks['old_paths_have_no_nodes'] = not any(n['path'] in {'front-two/api.ts', 'back-two/provider.cpp'} for n in renamed['nodes'])
    q.close()
    files.pop('back-two/renamed.cpp')
    commit(files, 'delete provider keep consumer')
    deleted, q, deletion = step('provider_deleted')
    rows = cases['provider_deleted']['entries']
    checks['deleted_provider_invalidates_consumer'] = any(e['name'] == 'renamedEntry' and e['status'] == 'unmatched' for e in rows)
    checks['other_service_remains_matched'] = any(e['name'] == 'entry' and e['status'] == 'matched_conditional' for e in rows)
    checks['deleted_source_has_no_nodes'] = not any(n['path'] == 'back-two/renamed.cpp' for n in deleted['nodes'])
    before = deletion['last_success']['id']
    q.close()
    configuration['version'] = 999
    failed = refresher.run()
    checks['failed_update_retains_old_publication'] = failed['status'] == 'failed' and failed['last_success']['id'] == before
    checks['old_snapshot_readable_after_failure'] = read_snapshot(output/'store')['receipt']['id'] == before
    configuration['version'] = 1
    restored = refresher.run()
    checks['configuration_recovery_reuses_complete_snapshot'] = restored['status'] == 'up_to_date' and restored['last_success']['id'] == before
    (source/'front-two/client.ts').write_text('uncommitted invalid source', encoding='utf-8')
    unchanged = refresher.run()
    checks['dirty_worktree_not_included'] = unchanged['last_success']['id'] == before
    # A separate controller/store invokes the real builder at the same committed tree.
    fresh = Refresher(source, output/'fresh-store', lambda: configuration, lambda: version, partial(build, typescript=typescript)).run()
    directory = Path(read_snapshot(output/'fresh-store')['directory'])
    rebuilt = json.loads((directory/'graph.json').read_text(encoding='utf-8'))
    for value in (deleted, rebuilt): value.pop('snapshot'); value['version'].pop('snapshot')
    checks['fresh_rebuild_equals_updated_graph'] = deleted == rebuilt
    result = {'evidence_kind': 'executed_authored_real_refresher_and_navigation_updates',
        'fixture_origin': 'authored_existing_property_binding_mechanism', 'build_version': version,
        'checks': checks, 'passed': all(checks.values()), 'cases': cases,
        'event_counts': {name: sum(e['event'] == name for e in events) for name in {e['event'] for e in events}},
        'comparison': 'direct JSON equality excluding only snapshot and version.snapshot; no hash verification',
        'historical_candidates_used_for_rules': False}
    (output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'checks': checks}))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--typescript', type=Path, required=True)
    a = p.parse_args()
    run(a.output, a.typescript)
