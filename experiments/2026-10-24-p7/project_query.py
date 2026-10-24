"""Unified, bounded views over an extracted project snapshot and runtime records."""
from collections import Counter, defaultdict, deque
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.fact_queries import find_path
from adapters.protocol_graph import PROTOCOL_KINDS
from adapters.data_graph import END_TO_END_KINDS
from adapters.chain_queries import explain_chain
from adapters.snapshot_records import query_records


def compact(node):
    return {k: node[k] for k in ('id', 'kind', 'name', 'path', 'line', 'definition', 'parameters') if k in node}


class ProjectQuery:
    def __init__(self, graph, inventory=None, catalog=None):
        self.graph = graph
        self.inventory = inventory
        self.catalog = catalog
        if catalog and (catalog['source_commit']!=graph['source_commit'] or catalog['snapshot']!=graph['snapshot']):
            raise ValueError('Coverage catalog and graph version differ')
        self.nodes = {n['id']: n for n in graph['nodes']}
        self.providers = {p['id']: p for p in graph['protocol']['providers']}
        self.out, self.inc = defaultdict(list), defaultdict(list)
        for edge in graph['edges']:
            self.out[edge['source']].append(edge); self.inc[edge['target']].append(edge)

    def result(self, kind, items, *, offset=0, limit=30, **extra):
        if offset < 0 or not 1 <= limit <= 500: raise ValueError('Use offset >= 0 and 1 <= limit <= 500')
        return {'query': kind, 'source_commit': self.graph['source_commit'], 'snapshot': self.graph['snapshot'],
                'graph_version': self.graph.get('version'), 'evidence_kind': 'extracted_source_facts',
                'total': len(items), 'offset': offset, 'limit': limit,
                'truncated': offset > 0 or offset+limit < len(items),
                'next_offset': offset+limit if offset+limit < len(items) else None,
                'items': items[offset:offset+limit], 'runtime_execution': 'unknown_unless_linked_run', **extra}

    def search(self, text='', kind=None, **page):
        found = [compact(n) for n in self.graph['nodes'] if
                 (not kind or n['kind'] == kind) and text.casefold() in (n.get('name', '')+' '+n.get('path', '')).casefold()]
        return self.result('search', found, **page)

    def overview(self, scope='', **page):
        inventory = self.inventory or {'modules': [], 'source_commit': self.graph['source_commit']}
        if inventory['source_commit'] != self.graph['source_commit']: raise ValueError('Inventory and graph source differ')
        modules = []
        for module in inventory['modules']:
            if scope and not module['path'].startswith(scope): continue
            item = deepcopy(module); prefix = module['path']+'/'
            nodes = [n for n in self.graph['nodes'] if n.get('path', '').startswith(prefix)]
            paths = {p for p in self.graph['input_paths'] if p.startswith(prefix)}
            entries = [compact(n) for n in nodes if n['kind'] in {'protocol_message', 'protocol_registration'}]
            item.update(analyzed_files=len(paths), node_kinds=dict(Counter(n['kind'] for n in nodes)),
                        semantic_coverage='selected_files' if paths else 'not_expanded',
                        entry_count=len(entries), entries=entries[:12], entries_truncated=len(entries)>12)
            item['observed_responsibilities']={'origin':'rule_summary_of_extracted_source_entities',
                'source_commit':self.graph['source_commit'],
                'protocol_commands':[e['name'] for e in entries],
                'storage_members':[compact(n) for n in nodes if n['kind']=='storage_member'][:12],
                'scope':'selected_source_only' if paths else 'unknown'}
            modules.append(item)
        return self.result('overview', modules, **page, repository_inventory={k: v for k, v in inventory.items() if k != 'modules'},
            coverage={'graph_input_files': len(self.graph['input_paths']), 'whole_repository_semantic_analysis': False,
                      'statuses': dict(Counter(c['status'] for c in self.graph['coverage']))},
            full_repository_catalog={k:self.catalog[k] for k in ('scan','languages','top_level_groups','limits')} if self.catalog else {'status':'not_supplied'},
            assets={'status': 'not_connected', 'dependency': 'P6'}, description_origin='package_metadata_and_source_structure')

    def coverage(self, capability=None, **page):
        if not self.catalog:return self.result('coverage',[],**page,status='not_supplied')
        if capability:
            rows=[c for c in self.catalog['capabilities'] if c['id']==capability]
            if not rows:return self.result('coverage_signals',[],**page,status='unknown_capability')
            c=rows[0]
            return self.result('coverage_signals',c['evidence'],**page,capability={k:v for k,v in c.items() if k!='evidence'},
                               evidence_kind='lexical_candidate_not_semantic_relation')
        return self.result('coverage',[{k:v for k,v in c.items() if k!='evidence'} for c in self.catalog['capabilities']],**page,
            repository={k:v for k,v in self.catalog.items() if k!='capabilities'},evidence_kind='full_tree_inventory_and_lexical_candidates')

    def resolve(self, name):
        if name in self.nodes: return name
        found = [n for n in self.graph['nodes'] if n.get('name') == name and n['kind'] == 'callable']
        defined = [n for n in found if n.get('definition')]
        if defined: found = defined
        if len(found) != 1: raise ValueError('Use an exact node ID for absent or ambiguous symbol: '+name)
        return found[0]['id']

    def protocol_results(self, name):
        results = []
        keys = {key for provider in self.graph['protocol']['providers'] for key in provider.get('command_fields', [])}
        for row in self.graph['protocol']['results']:
            if 'message' not in row: continue
            message = self.nodes[row['message']]
            fields = message.get('payload', {}).get('fields', {})
            commands = [fields[k].get('value') for k in keys if fields.get(k, {}).get('state') == 'constant']
            if name in (row['name'], message.get('name'), *commands) or name == row['message']:
                results.append(row)
        return results

    def trace(self, name, *, target=None, reverse=False, depth=16, field=None, details=False, **page):
        if not 0 <= depth <= 64: raise ValueError('Depth must be between 0 and 64')
        if target:
            path = find_path(self.graph, self.resolve(name), self.resolve(target), END_TO_END_KINDS | {'SOURCE_CALL_CANDIDATE'},
                             reverse=reverse, max_depth=depth)
            return self.result('trace_path', path['edges'], **page, path={k: v for k, v in path.items() if k != 'edges'})
        matches = self.protocol_results(name)
        if not matches:
            try:uid=self.resolve(name)
            except ValueError:return self.result('trace', [], **page, status='not_extracted_or_not_an_interface', missing_path_meaning='unknown')
            if reverse:
                result=self.impact(name=uid,depth=depth,**page);result['query']='trace_reverse';return result
            kinds=END_TO_END_KINDS | {'SOURCE_CALL_CANDIDATE'}
            reached,cut=self._reachable(uid,kinds,depth)
            return self.result('trace_forward',[compact(self.nodes[i]) for i in sorted(reached) if i!=uid],**page,
                               start=compact(self.nodes[uid]),depth_limit_reached=cut,meaning='candidate_source_reachability')
        paths, chains = [], []
        for result in matches:
            if not result['matches']:
                paths.append({'consumer': result, 'message': self.nodes[result['message']], 'provider': None,
                              'handlers': [], 'status': result['status']})
            for match in result['matches']:
                provider = match['provider']
                start = result['message']+':'+provider+':registration'
                handlers, cut = self._reachable(start, PROTOCOL_KINDS, depth)
                handler_nodes = [self.nodes[n] for n in handlers if self.nodes[n]['kind'] == 'callable' and self.nodes[n].get('definition')]
                paths.append({'consumer': result, 'message': self.nodes[result['message']],
                              'provider': self.providers[provider], 'handlers': [compact(n) for n in sorted(handler_nodes, key=lambda n:n['id'])],
                              'conditions': match['conditions'], 'depth_limit_reached': cut})
                if field:
                    chain = explain_chain(self.graph, provider, field, include_details=details)
                    chains.append(chain)
        if field:
            # Ledger pagination carries its evidence dictionary and explicit extraction gaps.
            rows = [dict(row, provider=chain['provider']) for chain in chains for row in chain['relations']]
            return self.result('trace_chain', rows, **page, protocols=paths,
                chains=[{k: v for k, v in c.items() if k != 'relations'} for c in chains],
                extraction_truncated=any(c['truncated'] for c in chains),
                direction='bidirectional_field_evidence',
                expansion_limits={'protocol_depth':depth,'field_and_transport':'extractor_and_chain_query_limits','returned_value_depth':8})
        return self.result('trace', paths, **page)

    def _reachable(self, start, kinds, depth, reverse=False):
        seen, queue, truncated = {start}, deque([(start, 0)]), False
        index = self.inc if reverse else self.out
        while queue:
            uid, d = queue.popleft()
            for edge in index[uid]:
                if edge['kind'] not in kinds: continue
                nxt = edge['source'] if reverse else edge['target']
                if nxt in seen: continue
                if d >= depth: truncated = True; continue
                seen.add(nxt); queue.append((nxt, d+1))
        return seen, truncated

    def resource(self, name, details=False, **page):
        data = self.graph['data']; members=data.get('member_effects', {})
        sources={s['id']:s for s in data['storages']+members.get('members',[])}
        selected = [s for s in sources.values() if name.casefold() in (s['owner']+'::'+s['name']).casefold()]
        results = []
        for storage in selected:
            accesses = [a for a in data['accesses'] if a['storage'] == storage['id']]
            effects=[e for e in members.get('effects',[]) if e['member']==storage['id']]
            symbols={a['source_symbol'] for a in accesses+effects}
            def brief(a):
                return {**{k:v for k,v in a.items() if k not in {'key','value'}},
                    'key_expression':(a.get('key') or {}).get('expression'),
                    'value_expression':(a.get('value') or {}).get('expression'),
                    'value_status':(a.get('value') or {}).get('reason',(a.get('value') or {}).get('kind'))}
            impacts=[{'source_symbol':i,'entries':[{'name':e['name'],'entries':e['entries'],'status':e['status']} for e in self.impact(name=i,limit=500)['items']]} for i in sorted(symbols)]
            cap=50
            results.append({'storage': storage, 'accesses': accesses if details else [brief(a) for a in accesses[:cap]],
                'member_effects':effects if details else [brief(e) for e in effects[:cap]],
                'access_count':len(accesses),'member_effect_count':len(effects),
                'relations_truncated':not details and (len(accesses)>cap or len(effects)>cap),
                'functions': [compact(self.nodes[i]) for i in sorted(symbols)],
                'reverse_impacts':impacts,
                'relationship': 'potential_shared_resource_with_instance_and_key_conditions',
                'instance_contexts': [a for a in data.get('instances', {}).get('accesses', []) if a['access'] in {x['id'] for x in accesses}],
                'runtime_occupancy_bytes': None, 'release_completion': 'not_observed'})
        return self.result('resource', results, **page)

    def impact(self, *, name=None, changed_paths=None, depth=20, **page):
        if not 0 <= depth <= 64: raise ValueError('Depth must be between 0 and 64')
        paths = set(changed_paths or [])
        seeds = {self.resolve(name)} if name else {n['id'] for n in self.graph['nodes'] if n.get('path') in paths and n['kind']=='callable'}
        if not name and not paths: raise ValueError('Supply a symbol or changed file paths')
        kinds = END_TO_END_KINDS | {'SOURCE_CALL_CANDIDATE', 'STATIC_CALL_TARGET', 'STATIC_DECLARATION_TARGET'}
        found, truncated = set(), False
        for seed in seeds:
            reached, cut = self._reachable(seed, kinds, depth, reverse=True); found.update(reached); truncated |= cut
        entries = []
        for row in self.graph['protocol']['results']:
            if 'message' not in row: continue
            apis = {e['source'] for e in self.inc[row['message']] if e['kind']=='EMITS_MESSAGE'}
            if apis & found:
                entries.append({'name': row['name'], 'message': row['message'], 'entries': [compact(self.nodes[i]) for i in sorted(apis & found)],
                    'status': 'candidate_impact', 'conditions': [m['conditions'] for m in row['matches']],
                    'witness_paths':[find_path(self.graph,seed,api,kinds,reverse=True,max_depth=depth)
                                     for seed in sorted(seeds) for api in sorted(apis & found)]})
        return self.result('impact', entries, **page, seeds=[compact(self.nodes[i]) for i in sorted(seeds)],
            changed_paths=sorted(paths), depth_limit_reached=truncated, analysis_scope='typed_source_reverse_paths',
            interpretation='candidate dependency, not a proof of changed behavior', assets={'status':'not_connected','dependency':'P6'})

    def explain(self, uid=None, gap=None, edge=None, **page):
        if edge is not None:
            if not isinstance(edge,dict) or not {'source','target','kind'}<=edge.keys():raise ValueError('Edge selector needs source, target and kind')
            return self.result('explain_edge',[e for e in self.graph['edges'] if all(e.get(k)==v for k,v in edge.items())],**page)
        if gap is not None:
            diagnostics = self.graph.get('diagnostics', []) + self.graph['protocol'].get('diagnostics', [])
            return self.result('explain_gap', [d for d in diagnostics if gap.casefold() in json.dumps(d).casefold()], **page,
                               limits=self.graph.get('limits', []))
        if uid not in self.nodes: raise ValueError('Unknown source node ID')
        data = self.graph.get('data', {})
        return self.result('explain', self.out[uid]+self.inc[uid], **page, node=self.nodes[uid],
            function_summaries=[s for s in data.get('summaries', []) if s['source_symbol']==uid],
            field_writes=[w for w in data.get('field_flow', {}).get('writes', []) if w.get('source_symbol')==uid])

    def assets(self, target=None, **page):
        return self.result('assets', [], **page, status='not_connected', dependency='P6', target=target,
                           applicability='not_evaluated', risk_assessment='not_performed')

    def runs(self, store, scenario=None, **page):
        source = query_records(store, kind='trace')
        records=[]
        for item in source['items']:
            record=item['record']; payload=record['payload']; context=payload.get('execution_context', {})
            if scenario and scenario not in (context.get('scenario', {}).get('name'), context.get('scenario', {}).get('run_id')): continue
            same = record['basis']['snapshot']==self.graph['snapshot'] and record['basis']['source_commit']==self.graph['source_commit'] and all(
                record['basis'][k]==self.graph.get('version',{}).get(k) for k in ('config','build_version'))
            records.append({'id':record['id'],'basis':record['basis'],'provenance':record['provenance'],
                'execution_context':context,'outcome':payload.get('outcome'), 'stage_counts':dict(Counter(e['stage'] for e in payload.get('events',[]))),
                'mappings':payload.get('mappings',[]),'diagnostics':payload.get('diagnostics',[]),
                'observed_dispatch_targets':sorted({m['node']['name'] for m in payload.get('mappings',[])
                    if m.get('role')=='observed_dispatch_target' and m.get('status')=='mapped' and m.get('node',{}).get('name')}),
                'same_graph_snapshot':same,'eligible_for_direct_overlay':False,
                'reason':'explicit_target_execution_context_required' if same else 'different_graph_snapshot',
                'verification_carried_forward':False})
        return self.result('runs',records,**page,evidence_kind='recorded_real_runs',runtime_execution='recorded_scenarios_only')


def render_markdown(result):
    lines=['# Project map', '', 'Source: `'+result['source_commit']+'`', '',
           'Query: '+result['query']+'. Items '+str(result['offset'])+'–'+str(result['offset']+len(result['items']))+' of '+str(result['total'])+'.',
           'Truncated: '+str(result['truncated']).lower()+'.', '']
    if result['query']=='overview':
        catalog=result.get('full_repository_catalog',{})
        if 'languages' in catalog:
            lines+=['## Whole repository inventory','','| Language | Tracked files | Graph input files |','|---|---:|---:|']
            for row in catalog['languages']:lines.append('| '+row['name']+' | '+str(row['tracked_files'])+' | '+str(row['graph_input_files'])+' |')
            lines+=['','Top-level directories (including unexpanded parts):','',
                '| Directory | Tracked | Graph inputs |','|---|---:|---:|']
            for row in catalog['top_level_groups']:lines.append('| '+row['path']+' | '+str(row['tracked_files'])+' | '+str(row['selected_files'])+' |')
            lines+=['','Use `coverage` for supported mechanisms and source candidates; lexical matches are not connections.','','## Selected module navigation','']
        lines+=['| Module | Tracked files | Analyzed files | Semantic coverage |','|---|---:|---:|---|']
        for m in result['items']: lines.append('| '+m['path']+' | '+str(m['file_count'])+' | '+str(m['analyzed_files'])+' | '+m['semantic_coverage']+' |')
        for m in result['items']:
            lines+=['', '## '+m['path'], '']
            for meta in m['metadata']:
                lines.append((meta.get('description') or meta.get('name') or meta.get('kind','source manifest'))+' — `'+meta['path']+':'+str(meta['line'])+'`')
                if meta.get('scripts'): lines.append('Build/run scripts: `'+json.dumps(meta['scripts'],ensure_ascii=False)+'`')
            if not m['metadata']: lines.append('Responsibility: unspecified in selected package metadata; inspect the source entries below.')
            for entry in m['entries']: lines.append('- '+entry['kind']+': '+entry['name']+' — `'+entry['path']+':'+str(entry['line'])+'`')
            if m['entries_truncated']: lines.append('Entry list truncated; use trace/search for the remaining entries.')
            if m['dependencies']:
                lines+=['', 'Dependencies declared in source:', '']
                for dep in m['dependencies']:
                    e=dep['evidence'];lines.append('- '+dep['kind']+': '+dep.get('name',dep.get('expression',''))+' '+str(dep.get('version',''))+' — `'+e['path']+':'+str(e['line'])+'`')
        lines+=['','Structure covers tracked files. Semantic coverage is limited to the selected graph inputs. P6 historical assets: not connected.']
    else:
        lines+=['```json',json.dumps(result,ensure_ascii=False,indent=2),'```']
    return '\n'.join(lines)+'\n'
