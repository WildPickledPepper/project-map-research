"""Check that real capture gaps and mismatched identities cannot certify a complete chain."""
import argparse
import copy
import json
from pathlib import Path
import shutil
from verify_capture import read_json, verify


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.is_relative_to(source) or output.is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError('Control artifacts must stay outside the source run and research repository')
    baseline = verify(source)
    if not baseline['complete']: raise ValueError('Controls require a complete real baseline capture')
    target_id = baseline['traces'][0]['observations']['request.decoded']['request_id']
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    cases = [('missing_database_return', 'missing_observation'),
                                ('wrong_decoded_trace', 'decoded_trace_mismatch'),
                                ('reused_request_id', 'duplicate_request_identity')]
    if len(baseline['traces']) > 1: cases.append(('swapped_api_results', 'api_response_payload_mismatch'))
    for name, expected_code in cases:
        target = output/name; target.mkdir()
        for filename in ('input.json', 'browser-events.json', 'browser-probe.json'):
            shutil.copyfile(source/filename, target/filename)
        for filename in ('scenario-result.json', 'delivery-control.json'):
            if (source/filename).exists(): shutil.copyfile(source/filename, target/filename)
        shutil.copytree(source/'server-log', target/'server-log', ignore=shutil.ignore_patterns('*.db', '*.db-*'))
        if name == 'reused_request_id':
            wire = read_json(target/'browser-events.json')
            sent = next(e for e in wire['events'] if e['direction'] == 'framesent' and e['message'].get('command') == 'unit/flows')
            wire['events'].append(copy.deepcopy(sent))
            (target/'browser-events.json').write_text(json.dumps(wire), encoding='utf-8')
        elif name == 'swapped_api_results':
            frames = read_json(target/'browser-probe.json')
            resolved = [event for frame in frames for event in frame['events'] if event['stage'] == 'api.resolved']
            assert len(resolved) == 2 and resolved[0]['result'] != resolved[1]['result']
            resolved[0]['result'], resolved[1]['result'] = resolved[1]['result'], resolved[0]['result']
            (target/'browser-probe.json').write_text(json.dumps(frames), encoding='utf-8')
        else:
            changed = 0
            for logfile in (target/'server-log').glob('*.log'):
                lines = []
                for line in logfile.read_text(encoding='utf-8').splitlines():
                    if 'PROJECT_MAP_EVENT ' in line:
                        prefix, payload = line.split('PROJECT_MAP_EVENT ', 1)
                        event = json.loads(payload)
                        if event['command'] == 'unit/flows' and event['request_id'] == target_id:
                            if name == 'missing_database_return' and event['stage'] == 'database.return':
                                changed += 1; continue
                            if name == 'wrong_decoded_trace' and event['stage'] == 'request.decoded':
                                event['trace_id'] = 'deliberately-unrelated-trace'; changed += 1
                                line = prefix + 'PROJECT_MAP_EVENT ' + json.dumps(event)
                    lines.append(line)
                logfile.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            if changed != 1: raise AssertionError('Expected one modified collection point, got ' + str(changed))
        result = verify(target)
        all_diagnostics = result['diagnostics'] + [d for t in result['traces'] for d in t['diagnostics']]
        assert not result['complete'], name
        assert any(d['code'] == expected_code for d in all_diagnostics), (name, all_diagnostics)
        if name == 'missing_database_return':
            assert any(d.get('stage') == 'database.return' and d.get('execution_status') == 'unknown_from_this_capture'
                       for d in all_diagnostics)
            if len(baseline['traces']) == 2:
                assert sum(trace['complete'] for trace in result['traces']) == 1, 'Unrelated complete request must remain intact'
        (target/'correlation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        rows.append({'control': name, 'expected_diagnostic': expected_code, 'passed': True,
                     'complete_chain_claim_rejected': True})
    result = {'evidence_kind': 'derived_negative_controls_on_real_capture', 'baseline': source.name,
              'source_commit': baseline['source_commit'], 'passed': True, 'controls': rows,
              'scope': 'Collector/identity checker controls; product behavior was not changed; R05 remains separate'}
    (output/'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args(); run(args.run, args.output)
