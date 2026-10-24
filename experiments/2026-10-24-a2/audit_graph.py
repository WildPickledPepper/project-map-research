"""Summarize a full-scope graph; compare fresh builds without file checksums."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters.repository_discovery import role


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def summarize(graph,graph_bytes):
    nodes={n['id']:n for n in graph['nodes']}
    coverage=Counter(r['path'] for r in graph['coverage'])
    a1=ROOT/'experiments/2026-10-24-a1/evidence'
    expected={r['path'] for line in (a1/'file-status.jsonl').read_text(encoding='utf-8').splitlines()
              if (r:=json.loads(line))['eligible']}
    config=graph['version']['config']
    ts_paths={p for p in expected if p.endswith(('.ts','.tsx'))}
    unit_paths=[p for unit in graph['analysis_units'] for p in unit['root_files']]
    checks={
        'automatic_scope_equals_all_A1_eligible_paths':set(graph['input_paths'])==expected,
        'automatic_discovery_policy_enabled':bool(config['scope'].get('discovery')),
        'typescript_units_cover_each_source_once':set(unit_paths)==ts_paths and len(unit_paths)==len(ts_paths),
        'every_input_has_one_coverage_record':set(coverage)==expected and all(n==1 for n in coverage.values()),
        'no_manual_reference_used_for_extraction':graph['provenance']['reference_used_for_extraction'] is False,
        'committed_blobs_exclude_worktree':graph['provenance']['input_kind']=='git_committed_blob_export' and
            graph['provenance']['working_tree_included'] is False,
        'unique_node_identities':len(nodes)==len(graph['nodes']),
        'all_edge_endpoints_exist':all(e['source'] in nodes and e['target'] in nodes for e in graph['edges']),
        'unknown_runtime_preserved':all(e.get('runtime_execution','unknown')!='observed' for e in graph['edges']),
        'cpp_declaration_joins_are_candidates':all(e['status']=='candidate' and e.get('types_checked') is False
            and e.get('build_linkage')=='not_validated'
            for e in graph['edges'] if e['kind']=='DECLARES_DEFINITION')}
    providers={p['id']:p for p in graph['protocol']['providers']}
    interfaces=[{k:p.get(k) for k in ('id','command','command_fields','scope_values','scope_fields',
        'path','line','status','scope_identity_status','handler_methods')} for p in providers.values()]
    consumers=[{k:r.get(k) for k in ('consumer','name','message','status')}|{
        'source_path':nodes.get(r['consumer'].removeprefix('protocol:'),{}).get('path'),
        'matches':[{'provider':m['provider'],'conditions':m['conditions'],'gaps':m['gaps']} for m in r['matches']]}
        for r in graph['protocol']['results']]
    phases={name:{'entries':len(graph[name].get('entries',[])),
        'entry_records_truncated':sum(bool(e.get('truncated')) for e in graph[name].get('entries',[]) if isinstance(e,dict)),
        'diagnostic_kinds':dict(Counter(d.get('kind',d.get('code','unspecified')) for d in graph[name].get('diagnostics',[]))),
        'budgets':graph[name].get('budgets',{}),'limits':graph[name].get('limits',[])}
        for name in ('frontend','response_callbacks','socket_flow','return_flow','cpp_transmission','server_channels')}
    return {'evidence_kind':'executed_full_scope_graph_audit','source_commit':graph['source_commit'],
        'snapshot':graph['snapshot'],'build_version':graph['version']['build_version'],
        'counts':{'input_files':len(expected),'nodes':len(nodes),'edges':len(graph['edges']),'graph_json_bytes':graph_bytes,
            'coverage':dict(Counter(r['status'] for r in graph['coverage'])),
            'node_kinds':dict(Counter(n['kind'] for n in nodes.values())),
            'edge_kinds':dict(Counter(e['kind'] for e in graph['edges'])),
            'edge_status':dict(Counter(e['status'] for e in graph['edges'])),
            'call_sites_by_resolution':dict(Counter(n.get('resolution','unspecified') for n in nodes.values() if n['kind']=='call_site')),
            'cpp_unresolved_reasons':dict(Counter(n.get('reason','unspecified') for n in nodes.values() if n['kind']=='call_site' and n['id'].startswith('cpp:') and n.get('resolution')=='unresolved')),
            'diagnostic_kinds':dict(Counter(d.get('kind',d.get('code','unspecified')) for d in graph['diagnostics'])),
            'protocol_provider_candidates':len(providers),'protocol_consumer_status':dict(Counter(r['status'] for r in consumers)),
            'protocol_consumer_role_status':dict(Counter(role(r['source_path'])[0]+':'+r['status'] if r['source_path'] else 'unknown:'+r['status'] for r in consumers)),
            'protocol_match_gaps':dict(Counter(g for r in consumers for m in r['matches'] for g in m['gaps'])),
            'member_effects':len(graph['data']['member_effects']['effects'])},
        'checks':checks,'passed':all(checks.values()),'interfaces':interfaces,'consumers':consumers,
        'analysis_units':graph['analysis_units'],
        'analysis_phases':phases,
        'typescript_compiler_options_origin':graph['typescript_compiler_options_origin'],
        'confidence':'Source identities and conditional candidates; no whole-project semantic correctness or runtime coverage claim',
        'storage':'json','kuzu_full_scope_roundtrip':'not_executed',
        'historical_sample_use':'none; validation candidates untouched',
        'file_hash_verification':'not_run_per_user_preference'}


def compare(first,second):
    snapshots=[first.pop('snapshot'),second.pop('snapshot')]
    for graph in (first,second):graph['version'].pop('snapshot')
    keys=set(first)|set(second)
    differing=sorted(k for k in keys if first.get(k)!=second.get(k))
    return {'evidence_kind':'executed_fresh_full_graph_direct_comparison','passed':not differing,
        'snapshots':snapshots,'comparison':'Direct parsed JSON equality excluding only snapshot and version.snapshot; no hashes',
        'differing_top_level_keys':differing,'file_hash_verification':'not_run_per_user_preference'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph',type=Path,required=True);p.add_argument('--rebuild',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh output')
    graph=read(a.graph)
    result=compare(graph,read(a.rebuild)) if a.rebuild else summarize(graph,a.graph.stat().st_size)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k in ('passed','checks','counts','differing_top_level_keys')},ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
