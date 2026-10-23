"""Join captured runtime boundaries by explicit identities; retain missing observations."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verify(directory, command='unit/flows'):
    directory = Path(directory)
    inputs = read_json(directory/'input.json')
    late = inputs.get('scenario') == 'late'
    scenario_result = read_json(directory/'scenario-result.json') if late else None
    wire = read_json(directory/'browser-events.json')
    frames = read_json(directory/'browser-probe.json')
    browser = [event for frame in frames for event in frame.get('events', [])]
    native = []
    for path in sorted((directory/'server-log').glob('*.log')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if 'PROJECT_MAP_EVENT ' in line:
                native.append({**json.loads(line.split('PROJECT_MAP_EVENT ', 1)[1]),
                               'evidence': {'path': 'server-log/' + path.name, 'line': number}})
    diagnostics, traces = [], []
    connections = wire.get('connections', [])
    # Native captures currently describe one server process with one browser connection.
    # Multiple generations need an explicit native connection binding before joining.
    if len(connections) != 1:
        diagnostics.append({'code': 'unsupported_connection_scope', 'count': len(connections)})
        return {'complete': False, 'traces': [], 'diagnostics': diagnostics}
    if wire.get('errors'):
        diagnostics.append({'code': 'page_errors', 'errors': wire['errors']})
    for frame in frames:
        if frame.get('diagnostics') or frame.get('capture_error'):
            diagnostics.append({'code': 'browser_capture_errors', 'frame': frame.get('name')})
    connection_id = connections[0]['id']
    if connections[0].get('closed'):
        diagnostics.append({'code': 'connection_closed_before_capture_completed'})
    requests = [event for event in wire['events'] if event['direction'] == 'framesent' and
                event['message'].get('type') == 'request']
    identities = Counter((event.get('connection_id'), event['message'].get('id')) for event in requests)
    duplicates = [list(key) for key, count in identities.items() if count != 1]
    if duplicates: diagnostics.append({'code': 'duplicate_request_identity', 'identities': duplicates})
    for sent in requests:
        request = sent['message']
        if request.get('command') != command: continue
        request_id, module, project = request['id'], request['moduleName'], request['projectName']
        trace_id = request.get('params', {}).get('__projectMapTrace')
        key = f'{connection_id}:request:{request_id}'
        issues, observations, links = [], {}, []

        def one(stage, candidates):
            matches = list(candidates)
            if len(matches) != 1:
                issues.append({'code': 'missing_observation' if not matches else 'ambiguous_observation',
                               'stage': stage, 'count': len(matches),
                               'execution_status': 'unknown_from_this_capture'})
                return None
            observations[stage] = matches[0]
            links.append({'source': key, 'target': key + ':' + stage, 'kind': 'explicit_request_or_trace_identity'})
            return matches[0]

        if not trace_id: issues.append({'code': 'missing_trace_metadata'})
        if sent.get('connection_id') != connection_id: issues.append({'code': 'connection_scope_mismatch'})
        begin = one('api.begin', (e for e in browser if e['stage'] == 'api.begin' and e.get('trace_id') == trace_id))
        if begin:
            one('ui.action', (e for e in browser if e['stage'] == 'ui.action' and e['frame'] == begin['frame'] and
                             e['action'] == begin['action'] and e['run_id'] == begin['run_id']))
        for stage in ('request.decoded', 'handler.invoke', 'database.call', 'database.return', 'handler.complete'):
            point = one(stage, (e for e in native if e['stage'] == stage and e['request_id'] == request_id and
                               e['module'] == module and e['command'] == command and e['project'] == project))
            if point and stage == 'request.decoded' and point['trace_id'] != trace_id:
                issues.append({'code': 'decoded_trace_mismatch'})
        response = one('wire.response', (e for e in wire['events'] if e['direction'] == 'framereceived' and
            e.get('connection_id') == connection_id and e['message'].get('type') == 'response' and
            e['message'].get('requestId') == request_id and e['message'].get('moduleName') == module and
            e['message'].get('command') == command))
        classified = one('response.classified', (e for e in browser if e['stage'] == 'response.classified' and
                         e.get('requestId') == request_id and e.get('command') == command))
        if late:
            if classified and (not classified.get('isOldRequest') or classified.get('requestProject') != project or
                               classified.get('currentProject') != scenario_result['projectB'] or
                               project != scenario_result['projectA']):
                issues.append({'code': 'unexpected_project_decision_in_late_run'})
            one('response.discarded', (e for e in browser if e['stage'] == 'response.discarded' and
                                      e.get('requestId') == request_id and e.get('command') == command))
            for event in browser:
                if (event['stage'] == 'response.delivered' and event.get('requestId') == request_id) or (
                        event['stage'] in ('api.resolved', 'state.applied') and event.get('trace_id') == trace_id):
                    issues.append({'code': 'unexpected_adoption_of_late_response', 'stage': event['stage']})
        else:
            if classified and (classified.get('isOldRequest') or classified.get('requestProject') != project or
                               classified.get('currentProject') != project):
                issues.append({'code': 'unexpected_project_decision_in_normal_run'})
            one('response.delivered', (e for e in browser if e['stage'] == 'response.delivered' and
                                      e.get('requestId') == request_id and e.get('command') == command))
            for stage in ('api.resolved', 'state.applied'):
                one(stage, (e for e in browser if e['stage'] == stage and e.get('trace_id') == trace_id))
        if response and not response['message'].get('result'): issues.append({'code': 'request_failed'})
        resolved = observations.get('api.resolved')
        if response and resolved and resolved.get('result') != response['message'].get('body'):
            issues.append({'code': 'api_response_payload_mismatch'})
        implementation = observations.get('database.call', {}).get('implementation')
        returned_implementation = observations.get('database.return', {}).get('implementation')
        if not implementation or returned_implementation != implementation:
            issues.append({'code': 'implementation_identity_unresolved'})
        # Windows native IDs allow a DLL and executable to describe the same OS thread.
        native_points = [observations[s] for s in ('request.decoded', 'handler.invoke', 'database.call', 'database.return',
                         'handler.complete') if s in observations]
        if any(e.get('thread_source') != 'Windows GetCurrentThreadId' for e in native_points):
            issues.append({'code': 'native_thread_identity_unavailable'})
        if len({e.get('process_id') for e in native_points}) != 1:
            issues.append({'code': 'native_process_scope_mismatch'})
        traces.append({'request_key': key, 'trace_id': trace_id, 'module': module, 'command': command, 'project': project,
                       'implementation': implementation, 'complete': not issues, 'diagnostics': issues,
                       'observations': observations, 'links': links})
    if not traces: diagnostics.append({'code': 'no_target_requests'})
    if late:
        control = read_json(directory/'delivery-control.json')
        phases = [event['phase'] for event in control['audit']]
        if phases != ['armed', 'held', 'B_state_verified_before_release', 'released']:
            diagnostics.append({'code': 'late_delivery_order_unproven', 'phases': phases})
        if len(control['held']) != 1 or not control['held'][0].get('released'):
            diagnostics.append({'code': 'held_response_release_unproven'})
        before, after = scenario_result['before'], scenario_result['after']
        final_states = [frame['state'] for frame in frames if frame.get('name') == 'Timeline']
        if final_states != [after] or after.get('project') != scenario_result['projectB']:
            diagnostics.append({'code': 'final_B_state_unproven'})
        for field in ('selectedData', 'singleLinkLine', 'drawLineMode'):
            if after.get(field) != before.get(field):
                diagnostics.append({'code': 'late_response_changed_B_state', 'field': field})
        if before.get('selectedData') or before.get('singleLinkLine'):
            diagnostics.append({'code': 'B_empty_selection_precondition_unproven'})
        if not scenario_result.get('passed'): diagnostics.append({'code': 'scenario_assertions_failed'})
    return {'evidence_kind': 'identity_join_of_real_runtime_observations', 'source_commit': inputs['source_commit'],
            'connection_id': connection_id, 'scope': 'one connection; ' + ('late response discarded after project switch' if late else 'normal request adoption'),
            'complete': not diagnostics and bool(traces) and all(t['complete'] for t in traces),
            'traces': traces, 'diagnostics': diagnostics,
            'causality': 'explicit trace metadata and requestId; timestamps are not used for joining',
            'missing_observation_semantics': 'execution unknown; a missing collection point does not prove non-execution'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--command', default='unit/flows')
    args = ap.parse_args()
    result = verify(args.run, args.command)
    (args.run/'correlation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'complete': result['complete'], 'requests': len(result['traces']),
                      'diagnostics': result['diagnostics']}, ensure_ascii=False))
    raise SystemExit(0 if result['complete'] else 1)
