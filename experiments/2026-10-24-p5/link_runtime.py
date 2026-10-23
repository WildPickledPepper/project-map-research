"""Import one real P5 capture into its published static snapshot; preserve gaps."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.snapshot_records import snapshot_basis
from runtime_records import append_runtime, query_runtime
from verify_capture import verify

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()


def make_context(run, receipt):
    inputs = read(run/'input.json'); boot = read(run/'boot-result.json')
    return {'source_commit': inputs['source_commit'], 'build': receipt,
            'runtime_config': {k: inputs[k] for k in ('listen_host', 'frontend_port', 'backend_port',
                                                     'strict_mode', 'fault_injection')} | {'browser': boot['browser']},
            'data': {k: inputs[k] for k in ('sample', 'sample_bytes', 'dataset_copy', 'additional_dataset_copies')},
            'scenario': {'name': inputs['scenario'], 'driver_version': receipt['capture_driver_version'],
                         'run_id': run.name}}


def rules_for_events(events, demangler):
    rules = []
    api = 'modules/timeline/src/api/request.ts'
    connection = 'modules/framework/src/centralServer/websocket/connection.ts'
    for stage in ('api.begin', 'api.resolved'):
        rules.append({'stage': stage, 'role': 'API', 'selector': {'kind': 'callable', 'path': api, 'name': 'getUnitFlows'}})
    for stage in ('response.classified', 'response.discarded', 'response.delivered'):
        rules.append({'stage': stage, 'role': 'capture_hook',
                      'selector': {'kind': 'call_site', 'path': connection, 'name': '(globalThis as any).__projectMapProbe?.event'},
                      'first_argument': repr(stage)})
    for stage, path in [('request.decoded', 'server/src/modules/ProtocolManager.cpp'),
                        ('handler.invoke', 'server/msinsight/src/base/ModuleRequestHandler.cpp'),
                        ('handler.complete', 'server/msinsight/src/base/ModuleRequestHandler.cpp'),
                        ('database.call', 'server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp'),
                        ('database.return', 'server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp')]:
        rules.append({'stage': stage, 'role': 'capture_hook', 'first_argument': json.dumps(stage),
                      'selector': {'kind': 'call_site', 'path': path, 'name': 'ProjectMapProbe::Emit'}})
    for stage in ('handler.invoke', 'handler.complete', 'database.call', 'database.return'):
        implementations = {e['observation'].get('implementation') for e in events if e['stage'] == stage}
        for implementation in sorted(x for x in implementations if x):
            typename = subprocess.check_output([str(demangler), '-t', implementation], text=True).strip()
            if typename == implementation: continue  # The hook remains; the unknown dynamic type is retained in the event.
            method = 'QueryUnitFlows' if stage.startswith('database.') else 'HandleRequest'
            rules.append({'stage': stage, 'role': 'observed_dispatch_target', 'when': {'implementation': implementation},
                          'selector': {'kind': 'callable', 'name': typename + '::' + method, 'definition': True}})
    for source, path in [('AscendUnit.onClick', 'modules/timeline/src/insight/units/AscendUnit.tsx'),
                         ('FilterLinkLine.getSingleFlow', 'modules/timeline/src/components/FilterLinkLine.tsx')]:
        rules.append({'stage': 'state.applied', 'role': 'state_assignment', 'when': {'source': source},
                      'selector': {'kind': 'frontend_state_write', 'path': path, 'name': 'singleLinkLine'}})
    return rules


def import_run(store, snapshot, run, receipt, demangler, producer_version):
    run = Path(run); basis = snapshot_basis(store, snapshot)
    correlation = verify(run); context = make_context(run, receipt)
    events, links = [], []
    frames = read(run/'browser-probe.json'); wire = read(run/'browser-events.json')
    for trace in correlation['traces']:
        key, trace_id = trace['request_key'], trace['trace_id']
        observations = deepcopy(trace['observations'])
        # The verifier expects a discard for the late scenario. Retain real adoption
        # events even when they violate that expectation, especially in R05.
        request_id = int(key.rsplit(':', 1)[1])
        for frame in frames:
            for event in frame.get('events', []):
                if event['stage'] in observations: continue
                if (event.get('trace_id') == trace_id or
                        event.get('requestId') == request_id and event.get('command') == trace['command']):
                    observations[event['stage']] = event
        sent = [e for e in wire['events'] if e['direction'] == 'framesent' and
                e['message'].get('params', {}).get('__projectMapTrace') == trace_id]
        if len(sent) == 1: observations['wire.request'] = sent[0]
        for stage, observation in observations.items():
            event_id = key + ':' + stage
            events.append({'id': event_id, 'request_key': key, 'stage': stage, 'observation': observation})
            links.append({'source': key, 'target': event_id, 'kind': 'explicit_request_or_trace_identity'})
    # Global fault activation is real but has no product source node: preserve it.
    for frame in frames:
        for event in frame.get('events', []):
            if event['stage'] == 'fault.activated':
                events.append({'id': event['event_id'], 'stage': event['stage'], 'observation': event})
    boot, scenario = read(run/'boot-result.json'), read(run/'scenario-result.json')
    diagnostics = correlation['diagnostics'] + [d for t in correlation['traces'] for d in t['diagnostics']]
    outcome = {'scenario_passed': scenario['passed'], 'browser_passed': boot['passed'],
               'failure': boot['failure'], 'capture_complete': correlation['complete'],
               'fault_injection': context['runtime_config']['fault_injection'],
               'assertion_source': 'scenario-result.json and boot-result.json',
               'assertions': scenario,
               'other_wire_messages': 'retained in original browser-events.json; outside this unit/flows record'}
    return append_runtime(store, basis, context, events, links, rules_for_events(events, demangler),
        {'evidence_kind': 'executed_real_UI_capture_mapped_to_extracted_graph',
         'source_ref': 'external-results:' + run.name,
         'producer': {'name': 'p5/link_runtime', 'version': producer_version}}, outcome, diagnostics)


def validate_receipt(source, receipt, results):
    """Validate declared build provenance against commits and retained build logs.

    Receipts are reconstructed from executed build records; this is source/build
    provenance, not binary attestation. No file hashes are recomputed.
    """
    if receipt.get('evidence_kind') != 'reconstructed_from_executed_build_logs_and_commits':
        raise ValueError('Explicit build provenance kind required')
    target = receipt['source_commit']
    for component in receipt['components']:
        log = results/component['log_ref']
        if not log.is_file() or not log.stat().st_size: raise ValueError('Missing component build log')
        if component['success_marker'] not in log.read_text(encoding='utf-8', errors='replace'):
            raise ValueError('Build log does not contain the recorded success marker')
        origin = component['source_commit']
        git(source, 'cat-file', '-e', origin + '^{commit}')
        if origin != target:
            eq = component['source_equivalence']
            changed = git(source, 'diff', '--name-only', origin, target, '--', *eq['scope']).splitlines()
            if changed or eq['changed_paths'] != changed or eq['against_commit'] != target:
                raise ValueError('Component source differs within its declared build input scope')
    return receipt


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('store', 'run', 'receipt', 'source', 'results', 'demangler', 'output'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--snapshot', required=True)
    args = ap.parse_args()
    if args.output.resolve().is_relative_to(ROOT): raise ValueError('Keep raw runtime records outside Git')
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = validate_receipt(args.source, read(args.receipt), args.results)
    record = import_run(args.store, args.snapshot, args.run, receipt, args.demangler, git(ROOT, 'rev-parse', 'HEAD'))
    query = query_runtime(args.store, record['id'], snapshot_id=args.snapshot, context=record['payload']['execution_context'])
    (args.output/'record.json').write_text(json.dumps(record, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    (args.output/'query.json').write_text(json.dumps(query, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({'record': record['id'], 'events': len(record['payload']['events']),
                      'mapped': sum(a['status'] == 'mapped' for a in record['anchors']),
                      'unmapped': sum(a['status'] == 'unmapped' for a in record['anchors']),
                      'eligible_for_direct_overlay': query['eligible_for_direct_overlay']}))
