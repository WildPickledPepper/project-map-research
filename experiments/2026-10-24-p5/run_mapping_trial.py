"""Exercise R06 with real captures, two extracted graphs and negative projections."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from adapters.snapshot_refresh import read_snapshot
from link_runtime import git, import_run, read, validate_receipt
from runtime_records import query_runtime


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def run_trial(args):
    args.output.mkdir(parents=True, exist_ok=False)
    producer = git(ROOT, 'rev-parse', 'HEAD')
    receipts = {kind: validate_receipt(args.source, read(HERE/f'evidence/build-{kind}.json'), args.results)
                for kind in ('normal', 'fault')}
    records, summaries = {}, []
    runs = [('normal', 'p5-r06-normal-01', args.normal_snapshot, 'normal'),
            ('late', 'p5-r06-late-01', args.normal_snapshot, 'normal'),
            ('parallel', 'p5-r06-parallel-01', args.normal_snapshot, 'normal'),
            ('fault_control', 'p5-fault-control-01', args.fault_snapshot, 'fault'),
            ('fault', 'p5-fault-01', args.fault_snapshot, 'fault')]
    for label, run_id, snapshot, kind in runs:
        record = import_run(args.store, snapshot, args.results/run_id, receipts[kind], args.demangler, producer)
        payload = record['payload']; context = payload['execution_context']
        same = query_runtime(args.store, record['id'], snapshot_id=snapshot, context=context)
        assert same['eligible_for_direct_overlay']
        assert any(a['status'] == 'unmapped' for a in same['anchors'])
        assert payload['outcome']['scenario_passed'] == (label != 'fault')
        assert not same['verification_carried_forward']
        stage_counts = Counter(e['stage'] for e in payload['events'])
        targets = [m['node'] for m in payload['mappings'] if m.get('role') == 'observed_dispatch_target' and m['status'] == 'mapped']
        assert any(n['name'].endswith('TextTraceDatabase::QueryUnitFlows') for n in targets)
        if label == 'fault':
            assert stage_counts['state.applied'] and stage_counts['response.delivered'] and stage_counts['fault.activated']
            assert any(d['code'] == 'unexpected_adoption_of_late_response' for d in payload['diagnostics'])
        if label == 'late':
            assert stage_counts['response.discarded'] == 1 and not stage_counts['state.applied']
        write(args.output/(label+'-record.json'), record)
        write(args.output/(label+'-context.json'), context)
        write(args.output/(label+'-same-context.json'), same)
        records[label] = record
        summaries.append({'label': label, 'run': run_id, 'record_id': record['id'], 'snapshot_id': snapshot,
            'source_commit': context['source_commit'], 'scenario_passed': payload['outcome']['scenario_passed'],
            'capture_complete': payload['outcome']['capture_complete'], 'stage_counts': dict(stage_counts),
            'anchors': dict(Counter(a['status'] for a in record['anchors'])),
            'unmapped_stages': sorted({e['stage'] for e in payload['events'] for m in payload['mappings']
                                      if m['event_id'] == e['id'] and m['status'] == 'unmapped'}),
            'observed_dispatch_targets': sorted({n['name'] for n in targets}),
            'same_context_direct_overlay': same['eligible_for_direct_overlay']})
    normal = records['normal']; original = read(args.store/'records'/normal['id']/'record.json')
    original_context = normal['payload']['execution_context']
    cross_source = query_runtime(args.store, normal['id'], snapshot_id=args.fault_snapshot, context=original_context)
    assert not cross_source['eligible_for_direct_overlay'] and 'source_commit' in cross_source['version_differences']
    assert any(a['status'] == 'candidate' for a in cross_source['anchors'])
    wrong_config = deepcopy(original_context); wrong_config['runtime_config']['strict_mode'] = False
    cross_config = query_runtime(args.store, normal['id'], snapshot_id=args.normal_snapshot, context=wrong_config)
    assert not cross_config['eligible_for_direct_overlay'] and cross_config['runtime_context_differences'] == ['runtime_config']
    control_context = deepcopy(records['fault_control']['payload']['execution_context'])
    control_context['runtime_config']['fault_injection']['allow_stale_response'] = True
    cross_flag = query_runtime(args.store, records['fault_control']['id'], snapshot_id=args.fault_snapshot, context=control_context)
    assert not cross_flag['eligible_for_direct_overlay'] and cross_flag['graph_eligible_for_direct_overlay']
    write(args.output/'cross-source.json', cross_source)
    write(args.output/'cross-runtime-config.json', cross_config)
    write(args.output/'cross-fault-flag.json', cross_flag)
    assert read(args.store/'records'/normal['id']/'record.json') == original
    try:
        import_run(args.store, args.fault_snapshot, args.results/'p5-r06-normal-01', receipts['normal'], args.demangler, producer)
    except ValueError as error:
        assert 'Runtime source differs' in str(error)
        wrong_source_rejected = True
    else:
        raise AssertionError('Importer accepted a different source version')
    graphs = []
    for snapshot in (args.normal_snapshot, args.fault_snapshot):
        resolved = read_snapshot(args.store, snapshot); graph = read(Path(resolved['directory'])/'graph.json')
        graphs.append({'snapshot_id': snapshot, 'source_commit': graph['source_commit'], 'nodes': len(graph['nodes']),
                       'edges': len(graph['edges']), 'input_files': len(graph['input_paths']),
                       'builder_version': graph['version']['build_version'], 'storage': 'kuzu',
                       'storage_roundtrip': resolved['receipt']['result']['storage_roundtrip']})
    summary = {'evidence_kind': 'executed_real_captures_and_extracted_graph_projection', 'acceptance': 'R06',
               'status': 'passed', 'producer_version': producer, 'graphs': graphs, 'records': summaries,
               'checks': {'same_context_overlay': True, 'cross_source_overlay_rejected': True,
                          'cross_runtime_config_overlay_rejected': True, 'cross_fault_flag_overlay_rejected': True,
                          'wrong_source_import_rejected': wrong_source_rejected, 'unmapped_real_events_retained': True,
                          'historical_record_unchanged': True, 'fault_failure_and_adoption_retained': True,
                          'normal_and_late_paths_differ_but_both_assertions_pass': True},
               'path_difference_interpretation': 'Normal adopts the result; late discards A after switching to B. Both match their scenario assertions.',
               'scope': 'Capture-hook adapter maps real events onto automatically extracted nodes; identity links and static edges remain separate.',
               'build_provenance': 'Reconstructed from executed build logs and source commits; component source differences checked by scoped git diff, no file hash verification.'}
    write(args.output/'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'store', 'results', 'output', 'demangler'):
        ap.add_argument('--'+name, type=Path, required=True)
    for name in ('normal-snapshot', 'fault-snapshot'): ap.add_argument('--'+name, required=True)
    args = ap.parse_args()
    if args.output.resolve().is_relative_to(ROOT): raise ValueError('Keep raw trial outputs outside Git')
    run_trial(args)
