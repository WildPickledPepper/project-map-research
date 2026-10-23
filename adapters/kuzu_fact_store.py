"""Store syntax supplements alongside CGC nodes using its Kuzu backend.

Tables are owned by this adapter. Native CGC nodes/edges remain unchanged.
Each namespace is a snapshot; replacement is atomic and keeps other snapshots.
"""
from __future__ import annotations

import hashlib
import json
import re

SCHEMA = (
    'CREATE NODE TABLE IF NOT EXISTS PMFact(id STRING, snapshot STRING, kind STRING, path STRING, line INT64, qualified_name STRING, payload STRING, PRIMARY KEY(id))',
    'CREATE REL TABLE IF NOT EXISTS PMSyntaxEdge(FROM PMFact TO PMFact, kind STRING, snapshot STRING)',
    'CREATE REL TABLE IF NOT EXISTS PMRefines(FROM Function TO PMFact, snapshot STRING, evidence STRING)',
)


def rows(result):
    columns = result.get_column_names()
    output=[]
    while result.has_next():
        output.append(dict(zip(columns,result.get_next())))
    return output


def prepare(facts):
    commit=facts['source_commit']
    if not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('A full source commit is required')
    # The source manifest and extractor version define the snapshot boundary.
    fingerprint=hashlib.sha256(json.dumps([commit,facts['manifest_sha256'],facts['extractor_version']],separators=(',',':')).encode()).hexdigest()[:16]
    snapshot=f'{commit}:{fingerprint}'
    nodes=[]
    edges=[]
    ids=set()
    for record in facts['records']:
        path=record['path']
        callable_ids={s['id'] for s in record['symbols']}
        for key,kind in (('symbols','callable'),('calls','call_site'),('bindings','binding')):
            for item in record[key]:
                uid=snapshot+':'+item['id']
                if uid in ids:raise ValueError('Duplicate fact id')
                ids.add(uid)
                if key=='calls' and item['resolution']!='unresolved':
                    raise ValueError('Syntax call observations must remain unresolved')
                nodes.append({'id':uid,'snapshot':snapshot,'kind':kind,'path':path,
                              'line':item['line'],'qualified_name':item.get('qualified_name',''),
                              'payload':json.dumps({'source_sha256_lf_utf8':record['sha256_lf_utf8'],
                                        'evidence_kind':record['evidence_kind'],'fact':item},ensure_ascii=False,sort_keys=True)})
                if key=='calls' and item.get('owner_id'):
                    if item['owner_id'] not in callable_ids:
                        raise ValueError('Call owner is absent from its source file')
                    edges.append({'source':snapshot+':'+item['owner_id'],'target':uid,
                                  'snapshot':snapshot,'kind':'OBSERVES_CALL'})
    return snapshot,nodes,edges


def replace_snapshot(connection,facts,native_root=None):
    snapshot,nodes,edges=prepare(facts)
    for ddl in SCHEMA:
        connection.execute(ddl)
    connection.execute('BEGIN TRANSACTION')
    try:
        connection.execute('MATCH (n:PMFact {snapshot:$snapshot}) DETACH DELETE n',{'snapshot':snapshot})
        for start in range(0,len(nodes),200):
            connection.execute('UNWIND $items AS item CREATE (:PMFact {id:item.id,snapshot:item.snapshot,kind:item.kind,path:item.path,line:item.line,qualified_name:item.qualified_name,payload:item.payload})',{'items':nodes[start:start+200]})
        for start in range(0,len(edges),200):
            connection.execute('UNWIND $items AS item MATCH (a:PMFact {id:item.source}),(b:PMFact {id:item.target}) CREATE (a)-[:PMSyntaxEdge {snapshot:item.snapshot,kind:item.kind}]->(b)',{'items':edges[start:start+200]})
        refined=0
        ambiguous=[]
        if native_root is not None:
            native_root=native_root.resolve().as_posix().rstrip('/')+'/'
            native=rows(connection.execute('MATCH (f:Function) WHERE f.path STARTS WITH $root RETURN f.uid AS uid,f.path AS path,f.line_number AS line',{'root':native_root}))
            index={}
            for item in native:
                index.setdefault((item['path'][len(native_root):],item['line']),[]).append(item['uid'])
            supplements={}
            for node in nodes:
                if node['kind']=='callable':supplements.setdefault((node['path'],node['line']),[]).append(node)
            links=[]
            for key,items in supplements.items():
                matches=index.get(key,[])
                if len(items)==1 and len(matches)==1:
                    links.append({'native':matches[0],'fact':items[0]['id'],'snapshot':snapshot})
                elif matches:
                    ambiguous.append({'path':key[0],'line':key[1],'native_count':len(matches),'supplement_count':len(items)})
            for start in range(0,len(links),200):
                connection.execute("UNWIND $items AS item MATCH (f:Function {uid:item.native}),(p:PMFact {id:item.fact}) CREATE (f)-[:PMRefines {snapshot:item.snapshot,evidence:'unique_path_and_line_in_same_verified_source'}]->(p)",{'items':links[start:start+200]})
            refined=len(links)
        connection.execute('COMMIT')
    except Exception:
        connection.execute('ROLLBACK')
        raise
    return {'snapshot':snapshot,'facts':len(nodes),'observed_call_relations':len(edges),
            'native_refinements':refined,'ambiguous_native_refinements':ambiguous}


def delete_snapshot(connection,snapshot):
    connection.execute('MATCH (n:PMFact {snapshot:$snapshot}) DETACH DELETE n',{'snapshot':snapshot})
