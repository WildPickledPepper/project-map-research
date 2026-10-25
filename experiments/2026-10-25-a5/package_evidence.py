"""Export compact public evidence while leaving paths, traces and databases outside Git."""
import argparse
from collections import Counter
import json
import re
from pathlib import Path
import subprocess

from verify import read

HERE=Path(__file__).resolve().parent


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def package(a):
    evidence=HERE/'evidence';evidence.mkdir(exist_ok=True)
    suite=read(a.results/'a5-final-suite.json');rows=[];resource_rows=[];controls=[]
    for item in suite['runs']:
        run=a.results/item['run'];result=read(run/'result.json');capture=read(run/'verification.json')
        events=[e for frame in read(run/'frames.json') for e in frame.get('probe',[])]
        # Detailed contexts and raw responses remain in the external immutable store.
        requests=[{k:c[k] for k in ('request_id','trace_id','connection','command','native_stages','handler','database',
            'delivered_result','page_consumed','consumer_events','disposition')} for c in capture['chains']]
        pages=[{k:e[k] for k in ('trace_id','currentPage','pageSize','total')}|{'block_count':len(e['blocks']),
            'device':e['baseParam']['deviceId']} for e in events if e['stage']=='pagination.page']
        row={**item,'requests':requests,'capture_negative_controls':capture['capture_negative_controls'],
            'pages':pages,'worker_generations':capture['checks']['worker_generations'],
            'cache_statuses':result['checks'].get('cache_statuses'),
            'cache_hit_avoids_blocks_fetch':result['checks'].get('cache_hit_avoids_blocks_fetch'),
            'stale_discard':result['checks'].get('stale_discard'),'input_assertions':capture['checks'],
            'scheduling':result['checks'].get('scheduling'),'known_gaps':capture['known_gaps'],
            'page_errors':len(result['errors'])}
        rows.append(row);controls.extend(capture['capture_negative_controls'])
        samples=read(run/'process-metrics.json')['samples']
        phases=[]
        for phase in read(run/'resources.json'):
            phases.append({k:phase.get(k) for k in ('label','entry_count','file_bytes','js_heap','error') if k in phase}|
                {'persistent_cache_directories':len({f['name'].rsplit('/',1)[0] for f in phase.get('files',[]) if f['name'].endswith('/cache-manifest.json')})})
        worker_metrics=[{'message_generation':e['message']['generation'],'metrics':e['message']['metrics']} for e in events
            if e['stage']=='worker.received' and e['message'].get('type')=='memoryMetrics']
        resource_rows.append({'run':run.name,'phases':phases,'worker_metrics':worker_metrics,
            'peak_backend_working_set':max((s['backend_working_set'] or 0 for s in samples),default=0),
            'peak_browser_process_tree_working_set':max((s['browser_process_tree_working_set'] or 0 for s in samples),default=0),
            'working_set_samples':len(samples)})
    runtime={'evidence_kind':'executed_real_Insight_scenarios','source_commit':rows[0]['source_commit'],
        'accepted_scenarios':len(rows),'normal_or_restored_passes':sum(r['scenario_passed'] for r in rows),
        'controlled_product_failures':sum(not r['scenario_passed'] for r in rows),
        'selected_requests':sum(len(r['requests']) for r in rows),
        'capture_corruption_controls':len(controls),'capture_corruption_rejected':sum(c['rejected'] for c in controls),
        'runs':rows,'original_checkout_modified':False,'upstream_push':'disabled','historical_validation_used_for_rule_development':False,
        'file_hash_verification':'not_run_per_user_preference'}
    write(evidence/'runtime.json',runtime)
    config_path='modules/leaks/src/leaksWorker/tools/BlockDataOPFS.ts'
    config_source=(a.results/'a5-static-01/build/source'/config_path).read_text(encoding='utf-8')
    configured={}
    for name in ('MAX_PERSISTENT_CACHE_COUNT','MAX_HIT_TEST_CACHE_BYTES','maxParsedManifestCount','maxBatchPathPoints'):
        match=re.search(r'\b'+name+r'(?:\s*:\s*number)?\s*=\s*([^;]+);',config_source)
        if match:configured[name]=match.group(1).strip()
    write(evidence/'resources.json',{'evidence_kind':'measured_instrumented_scenarios','runs':resource_rows,
        'configured_capacity':{'evidence_kind':'source_inspection','source_commit':runtime['source_commit'],
            'path':config_path,'expressions':configured,'stress_or_eviction_validation':False},
        'method':{'disk':'OPFS file handles enumerated after each completed phase',
            'worker':'reported logical metrics and actual transfer boundary; use message_generation for live adoption',
            'heap':'performance.memory with precise-memory-info; includes capture copies',
            'working_set':'sampled Windows working sets; browser tree includes Node driver and can double-count shared pages',
            'capacity':'default source limits separate from observed logical counts; live hit-test cache usage not collected',
            'gpu_memory':'not collected','exhaustive_runtime_coverage':False}})
    mapping=read(a.mapping/'result.json');write(evidence/'mapping.json',mapping)
    build=read(a.results/'a5-static-01/result.json');write(evidence/'static-build.json',build)
    receipt_audit=read(a.results/'a5-build-receipt-audit.json');write(evidence/'build-receipt-audit.json',receipt_audit)
    targets={target for row in mapping['runs'] for target in row['mapped_targets']}
    required_targets={'Communication::IterationsHandler::HandleRequest','Communication::GroupHandler::HandleRequest',
        'TextClusterDatabase::QueryIterations','TextClusterDatabase::GetGroups',
        'MemSnapshot::QueryMemSnapshotBlockHandler::HandleRequest','MemSnapshotDatabase::QueryBlocksByPage',
        'MemScope::QueryMemScopeBlockHandler::HandleRequest','MemScopeDatabase::QueryMemoryBlocks'}
    attempts=[]
    for directory in sorted(a.results.glob('a5-*')):
        if not directory.is_dir() or not (directory/'input.json').is_file() or not (directory/'result.json').is_file():continue
        result=read(directory/'result.json');failure=result.get('failure') or ''
        reason=None
        for phrase,label in [('Connection Closed','connection_closed'),('WebSocket','connection_closed'),
            ('#Timeline','startup_frame_not_ready'),('NoModificationAllowedError','active_cache_removal_rejected'),
            ('Independent allocation-lifetime','independent_input_assertion_failed'),('Timeout','driver_wait_timeout')]:
            if phrase in failure:reason=label;break
        accepted=any(r['run']==directory.name for r in rows)
        attempts.append({'run':directory.name,'source_commit':read(directory/'input.json')['source_commit'],
            'scenario':result['scenario'],'browser_passed':result['passed'],'failure_class':reason,
            'final_acceptance_run':accepted,
            'capture_complete':read(directory/'verification.json')['capture_complete'] if (directory/'verification.json').exists() else 'not_accepted_as_complete'})
    write(evidence/'attempts.json',{'runtime_attempts':attempts,'mapping_attempts':[
        {'name':'a5-mapping-01','status':'stopped_before_acceptance','reason':'capture adapter needed communication namespace and actual TextClusterDatabase override; source graph retained'},
        {'name':'a5-mapping-02','status':'passed','source_graph_reextracted':False}]})
    gates={
        'eight_scenarios_accepted':suite['passed'] and len(rows)==8,
        'seven_pass_one_expected_failure':runtime['normal_or_restored_passes']==7 and runtime['controlled_product_failures']==1,
        'request_capture_complete':all(r['capture_complete'] for r in rows),
        'capture_corruptions_rejected':runtime['capture_corruption_controls']==24 and runtime['capture_corruption_rejected']==24,
        'independent_oracles':all(r['independent_blocks_passed'] != r['fault'] for r in rows),
        'worker_generations_complete':all(g['completed'] for r in rows for g in r['worker_generations']),
        'cache_miss_hit_rebuild':next(r for r in rows if r['label']=='cache')['cache_statuses']==['miss','hit','miss'],
        'cache_hit_avoids_network':next(r for r in rows if r['label']=='cache')['cache_hit_avoids_blocks_fetch'],
        'old_page_discarded_after_device_switch':next(r for r in rows if r['label']=='replacement')['stale_discard'],
        'default_and_small_pages_executed':{p['pageSize'] for r in rows for p in r['pages']}>={128,1000},
        'fresh_matching_full_graph':build['status']=='passed' and mapping['graph']['source_commit']==runtime['source_commit'],
        'same_context_overlays':len(mapping['runs'])==8 and all(r['same_context_overlay'] for r in mapping['runs']),
        'source_and_config_rejected':mapping['compatibility_controls']['changed_source_admission_rejected'] and not any(mapping['compatibility_controls'][k] for k in ('changed_config_overlay','changed_source_overlay','changed_fault_overlay')),
        'unmapped_retained':all(r['anchors'].get('unmapped',0)>0 for r in mapping['runs']),
        'critical_source_targets_mapped':all(any(target.endswith(suffix) for target in targets) for suffix in required_targets),
        'build_logs_and_committed_scopes_valid':receipt_audit['passed'] and receipt_audit['components']==5,
    }
    write(evidence/'validation.json',{'passed':all(gates.values()),'gates':gates,
        'research_driver_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'scope':'eight frozen scenario families; historical asset integration remains P6'})
    if not all(gates.values()):raise ValueError('Acceptance gates failed: '+str(gates))
    print(json.dumps({'passed':True,'gates':len(gates),'selected_requests':runtime['selected_requests']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--mapping',type=Path,required=True)
    package(p.parse_args())
