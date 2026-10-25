"""Check the installed skill tool against the existing A5 map; no extraction or runtime recapture."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('python','workspace','output','context'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--record',required=True);a=p.parse_args();a.context=a.context.resolve()
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    checks=[];timings=[]
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append({'name':name,'passed':True})
    def cli(label,*arguments):
        started=time.monotonic()
        result=subprocess.run([str(a.python.resolve()),'-I','-X','utf8','-m','projectmap','--workspace',str(a.workspace.resolve()),
            *map(str,arguments)],cwd=output,capture_output=True,encoding='utf-8',timeout=180)
        (output/(label+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
        if result.returncode:raise RuntimeError(label+': '+result.stderr[-2000:])
        (output/(label+'.json')).write_text(result.stdout,encoding='utf-8')
        data=json.loads(result.stdout);timings.append({'label':label,'seconds':round(time.monotonic()-started,4),'bytes':len(result.stdout.encode('utf-8'))})
        return data
    status=cli('status','status');basis=status['active'];snapshot=basis['snapshot']
    check('source_current_for_selected_commit',status['freshness']=='current_for_selected_commit')
    check('historical_assets_disabled',status['historical_assets']=={'enabled':False})
    for view in ('overview','links','entries','providers','diagnostics'):
        result=cli(view,'query',view,'--limit',3)
        check(view+'_same_snapshot',result['snapshot']==snapshot)
    nodes=cli('search','query','search','--text','getUnitFlows','--kind','callable')['items'];check('entry_discovered',bool(nodes))
    uid=nodes[0]['id']
    source=cli('source','query','source','--start',uid);check('source_pinned',source['source_commit']==basis['source_commit'] and not source['working_tree_read'])
    neighbors=cli('neighbors','query','neighbors','--start',uid);check('neighbors_have_evidence',bool(neighbors['items']))
    target=cli('target','query','search','--text','QueryFlowsBySliceInfoHandler::HandleRequest')['items']
    target=next(row['id'] for row in target if row['path'].endswith('.cpp'))
    protocol_kinds=['EMITS_MESSAGE','MATCHES_REGISTERED_PROTOCOL','DECODES_MESSAGE','DISPATCHES_REGISTERED_HANDLER','RESOLVES_HANDLER']
    path=cli('path','query','path','--start',uid,'--target',target,'--depth',12,'--kinds',','.join(protocol_kinds))
    check('frontend_to_registered_handler_path',path['found'])
    impact=cli('impact','query','impact','--start',target,'--depth',6)
    check('reverse_impact_with_unknown_policy',bool(impact['items']) and impact['missing_relation_meaning']=='unknown')
    detail=cli('detail','query','detail','--entity','node','--id',target)
    check('evidence_expandable',bool(detail['items']))
    field=cli('field-chain','explain','getUnitFlows','--field','unitAllFlows','--limit',5,'--seconds',120)
    check('field_chain_ledger',field.get('query')=='trace_chain' and bool(field['items']))
    second=cli('field-page-two','explain','getUnitFlows','--field','unitAllFlows','--limit',5,'--offset',5,'--snapshot',snapshot,'--seconds',120)
    check('field_chain_second_page_same_snapshot',second['snapshot']==field['snapshot'] and second['total']==field['total'] and second['items']!=field['items'])
    runs=cli('runtime-list','runtime');check('runtime_list_does_not_imply_overlay',bool(runs['items']) and not any(r['eligible_for_direct_overlay'] for r in runs['items']))
    matched=cli('runtime-match','runtime','--id',a.record,'--context',a.context,'--limit',2)
    check('matching_record_context_accepted',matched['eligible_for_direct_overlay'])
    changed=json.loads(a.context.read_text(encoding='utf-8'));changed['scenario']={'name':'another-context'}
    mismatch=output/'mismatched-context.json';mismatch.write_text(json.dumps(changed),encoding='utf-8')
    rejected=cli('runtime-mismatch','runtime','--id',a.record,'--context',mismatch,'--limit',2)
    check('different_context_rejected',not rejected['eligible_for_direct_overlay'] and 'scenario' in rejected['runtime_context_differences'])
    async def mcp():
        from mcp import Client,StdioServerParameters
        transport=StdioServerParameters(command=str(a.python.resolve()),args=['-I','-X','utf8','-m','projectmap',
            '--workspace',str(a.workspace.resolve()),'serve'],cwd=str(output))
        async with Client(transport) as client:
            listing=await client.list_tools();check('mcp_four_readonly_tools',len(listing.tools)==4 and all(t.annotations.read_only_hint for t in listing.tools))
            response=await client.call_tool('map_query',{'view':'path','start':uid,'target':target,'depth':12,'kinds':protocol_kinds})
            check('installed_mcp_same_path',not response.is_error and response.structured_content['found'] and response.structured_content['snapshot']==snapshot)
    asyncio.run(mcp())
    summary={'evidence_kind':'executed_installed_wheel_on_existing_a5_extraction','source_commit':basis['source_commit'],
        'snapshot':snapshot,'extraction_rules':basis['build_version']['rules_commit'],
        'navigation_rules':source['navigation_version']['rules_commit'],'installed_rules':status['installed_rules_commit'],
        'runtime_recaptured':False,'accuracy_experiment':'not_run','checks':checks,'timings':timings,
        'protocol_path_kinds':[edge['kind'] for edge in path['items']],
        'field_chain_summary':{'returned_relations':len(field['items']),'total':field.get('total'),'extraction_truncated':field.get('extraction_truncated')},
        'runtime_records_listed':runs['total']}
    (output/'result.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':len(checks),'result':str(output/'result.json')}))


if __name__=='__main__':main()
