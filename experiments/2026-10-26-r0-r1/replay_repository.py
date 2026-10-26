"""Reuse unchanged full-repository facts and append native captures atomically.

This experiment uses Workspace/Refresher publication. It rejects base extractor
changes instead of silently treating old facts as a new extraction.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from adapters.native_provider_graph import merge,read_capture
from adapters.snapshot_inputs import git
from projectmap.workspace import Workspace
from scripts.build_project_snapshot import build_version,write_json

ALLOWED={'adapters/libclang_provider.py','adapters/native_provider_graph.py',
    'adapters/native_value_flow.py','adapters/rapx_export.rs','adapters/svf_export.py',
    'scripts/analyze_svf_captures.py','scripts/capture_cargo_value_flow.py',
    'scripts/collect_native_value_flow.py','scripts/prepare_rapx_export.py'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','header-capture','value-flow-captures','output'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Use a new output')
    base=Workspace(args.baseline/'workspace');active=base.config['active'];revision=active['source_commit']
    before=git(base.source,'status','--porcelain','--untracked-files=normal')
    changed=git(ROOT,'diff','--name-only',active['build_version']['rules_commit'],'HEAD','--',
                'adapters','scripts','projectmap').decode().splitlines()
    if set(changed)-ALLOWED:raise ValueError('Base extraction changed; require full rebuild: '+str(set(changed)-ALLOWED))
    manifest=json.loads(args.value_flow_captures.read_text())
    if manifest['source_commit']!=revision:raise ValueError('Capture revision differs from baseline')
    header=json.loads((args.header_capture/'facts.json').read_text())['components']
    captures=[{'provider':'libclang','source_commit':revision,'context_key':header['context'],
               'directory':str(args.header_capture.resolve())}]
    for capture in manifest['captures']:
        directory=(args.value_flow_captures.parent/capture['directory']).resolve()
        if not directory.is_relative_to(args.value_flow_captures.parent.resolve()):raise ValueError('Capture escaped manifest')
        captures.append({**capture,'directory':str(directory)})
    analysis=json.loads(json.dumps(base.config['analysis']))
    analysis['build']['providers']['captures'].extend(captures)
    workspace=Workspace.create(args.output/'workspace',base.source,revision=revision,
                               typescript=base.config['typescript'],analysis=analysis)
    def builder(source,request,output,log):
        print('Replay unchanged base extraction and import native captures',file=log,flush=True)
        graph=json.loads(Path(active['graph']).read_text(encoding='utf-8'))
        if graph['source_commit']!=request['source_commit'] or graph['input_paths']!=request['input_paths']:
            raise ValueError('Baseline source/input scope differs')
        graph['provenance']['base_fact_reuse']={'snapshot':graph['snapshot'],
            'original_build_version':graph['version']['build_version'],
            'unchanged_core_verified_by_git_paths':True,'changed_native_adapter_paths':changed,
            'original_source_facts_reextracted':False}
        for capture in captures:
            facts=read_capture(capture,paths=request['input_paths'],source_commit=request['source_commit'])
            merge(graph,facts,provider=capture['provider'],context=capture['context_key'])
        graph['snapshot']=request['snapshot']
        graph['version']={k:request[k] for k in ('snapshot','source_commit','config','build_version')}
        graph['provenance']['update_mode']='reuse_unchanged_source_facts_and_append_native_captures'
        write_json(output/'graph.json',graph)
        return {'nodes':len(graph['nodes']),'edges':len(graph['edges']),
            'files':len(graph['input_paths']),'storage':'json'}
    started=time.monotonic()
    version=build_version(workspace.typescript())
    with (args.output/'events.jsonl').open('w') as stream:
        result=workspace.update(builder=builder,version=version,
            emit=lambda row:(stream.write(json.dumps(row)+'\n'),stream.flush()))
    receipt={'scope':'repository','source_commit':revision,'build':result,'status':workspace.status(),
        'seconds':round(time.monotonic()-started,3),'base_fact_reuse':active['snapshot'],
        'original_checkout_modified':before!=git(base.source,'status','--porcelain','--untracked-files=normal'),
        'native_capture_reuse':True,'historical_assets_enabled':False,'whole_G02_accepted':False,
        'hash_verification':'not_run_per_user_preference'}
    (args.output/'trial.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({'build':result,'seconds':receipt['seconds']}),flush=True)
    if result['status']!='ready' or receipt['original_checkout_modified']:raise SystemExit(1)


if __name__=='__main__':main()
