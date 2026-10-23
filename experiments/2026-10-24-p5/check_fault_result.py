"""Validate that an opt-in product fault causes the real final-state assertion to fail."""
import argparse
import json
from pathlib import Path
from verify_capture import read_json, verify


def check(control, fault):
    control, fault = Path(control), Path(fault)
    healthy = verify(control)
    assert healthy['complete'], 'Guard-active control must pass full late-response checks'
    normal_input, fault_input = read_json(control/'input.json'), read_json(fault/'input.json')
    assert normal_input['source_commit'] == fault_input['source_commit'], 'Compare the same experimental source/build'
    assert not normal_input['fault_injection']['allow_stale_response']
    assert fault_input['fault_injection']['allow_stale_response']
    for field in ('scenario', 'sample', 'sample_bytes', 'strict_mode', 'listen_host'):
        assert normal_input[field] == fault_input[field], field
    boot = read_json(fault/'boot-result.json')
    state = read_json(fault/'scenario-result.json')
    assert boot['passed'] is False and state['passed'] is False
    assert 'Late A response must not change B flow lines' in boot['failure'], 'Require the intended state assertion, not a timeout'
    assert state['before']['singleLinkLine'] == {}
    assert state['after']['project'] == state['projectB']
    after_lines = [line for group in state['after']['singleLinkLine'].values() for line in group]
    assert after_lines, 'The injected stale callback must actually contaminate B state'
    assert all(line['cardId'] == state['projectA'] for line in after_lines)
    frames = read_json(fault/'browser-probe.json')
    events = [event for frame in frames for event in frame.get('events', [])]
    assert any(event['stage'] == 'fault.activated' for event in events)
    assert any(event['stage'] == 'response.delivered' and event.get('requestId') == state['request_id'] for event in events)
    assert any(event['stage'] == 'state.applied' and event.get('trace_id') == state['trace_id'] and
               event['state']['project'] == state['projectB'] for event in events)
    analyzed = verify(fault)
    assert not analyzed['complete']
    diagnostics = analyzed['diagnostics'] + [item for trace in analyzed['traces'] for item in trace['diagnostics']]
    assert any(item['code'] == 'late_response_changed_B_state' and item['field'] == 'singleLinkLine' for item in diagnostics)
    assert any(item['code'] == 'unexpected_adoption_of_late_response' for item in diagnostics)
    assert len(analyzed['traces']) == 1
    native = analyzed['traces'][0]['observations']
    assert native['database.return']['implementation'] == healthy['traces'][0]['observations']['database.return']['implementation']
    (fault/'correlation.json').write_text(json.dumps(analyzed, indent=2) + '\n', encoding='utf-8')
    result = {'evidence_kind': 'executed_product_fault_with_real_UI_state_failure', 'acceptance': 'R05', 'passed': True,
              'source_commit': fault_input['source_commit'], 'control_run': control.name, 'fault_run': fault.name,
              'control_scenario_passed': True, 'fault_scenario_passed': False,
              'expected_failure': 'Late A response must not change B flow lines',
              'observed_violation': 'Project B remains active but its flow state contains A rank data',
              'faulty_final_flow_count': len(after_lines), 'request_id': state['request_id'], 'trace_id': state['trace_id'],
              'diagnostics': diagnostics,
              'file_hash_verification': 'not_run_per_user_preference'}
    (fault/'fault-validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--control', required=True, type=Path)
    ap.add_argument('--fault', required=True, type=Path)
    args = ap.parse_args(); print(json.dumps(check(args.control, args.fault)))
