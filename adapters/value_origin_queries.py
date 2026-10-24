"""Follow returned object fields using extracted expressions and scoped local writes.

This keeps reaching-definition alternatives as candidates, including the branch
that produced them. It does not infer values from identifier similarity.
"""
from collections import defaultdict
import json
from adapters.field_queries import explain_writes


def explain_value_origins(graph, writes, max_depth=8):
    data=graph['data'];flow=data['field_flow'];nodes={n['id']:n for n in graph['nodes']}
    summaries={s['source_symbol']:s for s in data['summaries']}
    locations={l['id']:l for l in flow['locations']};roots={r['id']:r for r in flow['roots']}
    definitions=defaultdict(list)
    for e in graph['edges']:
        if e['kind']=='DECLARES_DEFINITION':definitions[e['source']].append(e['target'])
    effects_cache={}
    relations=[];gaps=[];truncated=False
    def visit(v,selectors,uid,conditions,steps,depth):
        nonlocal truncated
        if depth>max_depth:
            truncated=True;gaps.append({'kind':'value_origin_depth_limit','source_symbol':uid});return
        if not v:return
        kind=v.get('kind');e={k:v[k] for k in ('path','line','expression') if k in v}
        if kind=='field_expression' and len(v.get('parts',[]))==2:
            base,field=v['parts'];visit(base,['member:'+field['expression']]+selectors,uid,conditions,steps,depth+1)
        elif kind=='identifier' and v.get('initializer'):
            visit(v['initializer'],selectors,uid,conditions,steps,depth+1)
        elif kind=='unknown':
            gaps.append({'kind':v.get('reason','unknown_value'),'evidence':e,'source_symbol':uid})
            for candidate in v.get('write_candidates',[]):
                visit(candidate['value'],selectors,uid,conditions+candidate.get('conditions',[])+['candidate_reaching_definition'],steps,depth+1)
        elif kind=='call_expression':
            targets=set(v.get('targets',[]));resolved=set()
            for t in targets:resolved.update([t] if t in summaries else definitions[t])
            if not resolved:gaps.append({'kind':'return_target_unresolved','evidence':e})
            for target in sorted(resolved):
                step={'caller':uid,'callee':target,'evidence':e,'selectors':selectors}
                relations.append({'kind':'RETURNED_VALUE_SOURCE','source':target,'consumer':uid,'selectors':selectors,
                    'steps':steps+[step],'conditions':conditions+['runtime_target_matches_candidate'],
                    'status':'source_candidate','evidence':[e]})
                for ret in summaries[target]['returns']:
                    if not ret.get('callback_return'):
                        visit(ret['value'],selectors,target,conditions+ret['conditions'],steps+[step],depth+1)
        elif kind=='identifier' and v.get('binding'):
            matching=[r for r in roots.values() if r['source_symbol']==uid and r['name']==v['expression'] and
                any(x['path']==v['binding']['path'] and x['line']==v['binding']['line'] for x in r['evidence'])]
            if matching and uid not in effects_cache:effects_cache[uid]=explain_writes(graph,uid,max_depth=max_depth)
            expanded=effects_cache.get(uid,{'effects':[],'truncated':False,'gaps':[]})
            truncated |= expanded['truncated']
            gaps.extend(expanded['gaps'])
            for root in matching:
                for w in expanded['effects']:
                    if w['root']!=root['id']:continue
                    path=w['selectors']
                    if selectors and path[:len(selectors)]!=selectors:continue
                    at=w['call_chain'][0]['evidence'] if w['call_chain'] else w['evidence']
                    if any(x.get('line',0)>v.get('line',0) for x in at):continue
                    predicates=[c for scope in w['condition_scopes'] for c in scope['conditions']]
                    relations.append({'kind':'RETURNED_LOCAL_FIELD_WRITE','source':w['write'],'consumer':uid,'selectors':path,
                        'steps':steps,'production_calls':w['call_chain'],
                        'conditions':conditions+predicates+['write_reaches_return_without_overwrite'],
                        'status':'source_candidate','evidence':w['evidence']+at,'values':w['values']})
        elif selectors:
            gaps.append({'kind':'value_field_source_not_expanded','source_symbol':uid,'selectors':selectors,'evidence':e})
    for w in writes:
        for v in w.get('values',[]):visit(v,[],w['source_symbol'],w.get('conditions',[]),[],0)
    unique=lambda rows:list({json.dumps(r,sort_keys=True):r for r in rows}.values())
    return {'relations':unique(relations),'gaps':unique(gaps),'truncated':truncated,'max_depth':max_depth,
        'meaning':'candidate return-value lineage; argument/key equivalence and intervening mutations remain conditions'}
