"""Verify explicit request identities, source observations and independent fixture assertions."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

TARGETS={'communication/duration/iterations','communication/matrix/group','Memory/snapshot/blocks','Memory/leaks/blocks'}


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_capture(inputs,wire,frames,native):
    browser=[e for frame in frames for e in frame.get('probe',[])]
    requests=[e for e in wire if e.get('direction')=='framesent' and e.get('message',{}).get('command') in TARGETS]
    if not requests:raise ValueError('No selected real requests')
    if len({e['connection'] for e in wire if e.get('direction')=='framesent'})!=1:raise ValueError('Connection generation is required for multiple sockets')
    identities=[(e['connection'],e['message']['id']) for e in requests]
    if len(set(identities))!=len(identities):raise ValueError('Duplicate request identity')
    chains=[]
    for request in requests:
        message=request['message'];rid=message['id'];command=message['command'];trace=message['params'].get('__projectMapTrace')
        begin=[e for e in browser if e['stage']=='request.begin' and e.get('trace_id')==trace]
        if len(begin)!=1 or not trace:raise ValueError('Missing or ambiguous browser request identity')
        observations=[e for e in native if e['request_id']==rid and e['command']==command]
        counts=Counter(e['stage'] for e in observations)
        for stage in ('request.decoded','handler.invoke','database.call','database.return','handler.complete'):
            if counts[stage]!=1:raise ValueError('Missing or duplicated native stage: '+stage)
        if next(e for e in observations if e['stage']=='request.decoded')['trace_id']!=trace:raise ValueError('Trace identity differs after native decoding')
        response=[e for e in wire if e.get('direction')=='framereceived' and e.get('message',{}).get('type')=='response' and e['message'].get('requestId')==rid]
        if len(response)!=1:raise ValueError('Missing or duplicated delivered response')
        client=[e for e in browser if e['stage']=='connector.response' and e['frame']==begin[0]['frame'] and e['id']==begin[0]['id']]
        if len(client)!=1:raise ValueError('Missing connector response')
        body=response[0]['message'].get('body')
        if response[0]['message']['result'] and client[0]['response'].get('body')!=body:raise ValueError('Response body changed before connector delivery')
        pages=[e for e in browser if e['stage']=='pagination.page' and e.get('trace_id')==trace]
        consumers=[e for e in browser if e['stage'].startswith('consumer.') and e.get('trace_id')==trace]
        if pages and pages[0]['blocks']!=body.get('blocks'):raise ValueError('Page body differs from transport')
        chains.append({'request_id':rid,'trace_id':trace,'connection':request['connection'],'command':command,
            'params':{k:v for k,v in message['params'].items() if k!='__projectMapTrace'},
            'native_stages':dict(counts),'handler':next(e['implementation'] for e in observations if e['stage']=='handler.invoke'),
            'database':next(e['implementation'] for e in observations if e['stage']=='database.call'),
            'delivered_result':response[0]['message']['result'],'page_consumed':bool(pages),'consumer_events':len(consumers),
            'disposition':'failed_at_delivery' if not response[0]['message']['result'] else 'page_consumed' if pages else 'consumer_resolved' if consumers else 'delivered_to_connector_no_selected_consumer',
            'observations':observations})
    # A page boundary and merge boundary are paired by the sequential helper's explicit events.
    for frame in frames:
        pages={}
        for event in frame.get('probe',[]):
            if event['stage']=='pagination.page':
                key=json.dumps(event['baseParam'],sort_keys=True);pages.setdefault(key,[]).extend(event['blocks'])
            elif event['stage']=='pagination.merged':
                key=json.dumps(event['baseParam'],sort_keys=True)
                if pages.get(key)!=event['result']['blocks']:raise ValueError('Merged block order differs from page concatenation')
                pages.pop(key,None)
            elif event['stage']=='load.error' and event.get('superseded'):
                # An interrupted earlier load can leave pages that never form a merge.
                pages={}
    return chains


def verify(run):
    run=Path(run);inputs=read(run/'input.json');wire=read(run/'wire.json');frames=read(run/'frames.json');native=read(run/'native-events.json')
    chains=verify_capture(inputs,wire,frames,native)
    events=[e for f in frames for e in f.get('probe',[])]
    handoffs=[e for e in events if e['stage']=='worker.handoff']
    checks={};expected=read(run/'expected.json')
    for e in events:
        if e['stage']=='consumer.iterations':
            if [x['value'] for x in e['compareOptions']]!=expected['communication_steps']:raise ValueError('Independent iteration expectation failed')
            if not e.get('trace_id'):raise ValueError('Consumer result identity missing')
            checks['independent_iterations']=True
    block_results=[]
    for handoff in handoffs:
        context=json.loads(handoff['blockContextKey']);device=context[2];blocks=handoff['data']['blocks']
        if context[1]=='memsnapshot':
            wanted=expected['devices'][device]
            keys=lambda b:(str(b['address']),b['alloc'],b['free'])
            actual=Counter((b['addr'],b['allocEventId'],b['freeEventId']) for b in blocks)
            correct=Counter(keys(b) for b in wanted['positive_lifetimes']+wanted['initial_lifetimes'])
        else:
            wanted=expected['memscope'][device+':'+context[3]]
            actual=Counter((b['addr'],b['size']) for b in blocks);correct=Counter((b[0],b[1]) for b in wanted)
        block_results.append({'device':device,'request_seq':handoff['requestSeq'],'expected':sum(correct.values()),
            'actual':len(blocks),'independent_multiset_equal':actual==correct,'missing':sum((correct-actual).values()),'extra':sum((actual-correct).values())})
    checks['blocks']=block_results
    sent=[e for e in events if e['stage']=='worker.sent' and e['type']=='setMemoryBlockData']
    completions=[e for e in events if e['stage']=='worker.received' and e['message'].get('type')=='renderCompleted']
    checks['worker_generations']=[{'worker_id':e.get('worker_id'),'generation':e['generation'],'transfer_bytes':e['transfer_bytes'],
        'completed':any(c.get('worker_id')==e.get('worker_id') and c['message'].get('generation')==e['generation'] for c in completions)} for e in sent]
    if not all(x['completed'] for x in checks['worker_generations']):raise ValueError('Missing matching Worker render completion')
    controls=[]
    for label,change in [('missing_database_return',lambda w,n:n.pop(next(i for i,e in enumerate(n) if e['stage']=='database.return' and e['command'] in TARGETS))),
                         ('wrong_decoded_identity',lambda w,n:next(e for e in n if e['stage']=='request.decoded' and e['command'] in TARGETS).update(trace_id='wrong')),
                         ('duplicate_request',lambda w,n:w.append(deepcopy(next(e for e in w if e.get('direction')=='framesent' and e.get('message',{}).get('command') in TARGETS))))]:
        w=deepcopy(wire);n=deepcopy(native);change(w,n)
        try:verify_capture(inputs,w,frames,n)
        except ValueError as error:controls.append({'name':label,'rejected':True,'reason':str(error)})
        else:raise ValueError('Capture corruption was accepted: '+label)
    outcome=read(run/'result.json')
    return {'run':run.name,'source_commit':inputs['source_commit'],'scenario':inputs['scenario'],'browser_passed':outcome['passed'],
        'capture_complete':True,'chains':chains,'checks':checks,'capture_negative_controls':controls,
        'independent_blocks_passed':all(x['independent_multiset_equal'] for x in block_results),
        'known_gaps':['Python subprocess has import output evidence; per-function Python runtime tracing is not collected',
                      'Worker internals are observed at messages and reported metrics; all internal calls are not traced']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=verify(a.run);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'run':result['run'],'capture_complete':result['capture_complete'],'requests':len(result['chains']),'blocks':result['checks']['blocks']}))
