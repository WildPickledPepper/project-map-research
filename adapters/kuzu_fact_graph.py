"""Persist the portable fact contract alongside CGC's native Kuzu tables.

Owns PMGraph* only. Each replacement/deletion commits one complete snapshot.
The shared validator preserves all JSON fields and rejects dangling endpoints.
"""
import json

from adapters.sqlite_fact_graph import _prepare
from adapters.kuzu_fact_store import rows

SCHEMA = (
    'CREATE NODE TABLE IF NOT EXISTS PMGraphSnapshot(id STRING, payload STRING, PRIMARY KEY(id))',
    'CREATE NODE TABLE IF NOT EXISTS PMGraphNode(key STRING, snapshot STRING, id STRING, ordinal INT64, kind STRING, path STRING, line INT64, name STRING, payload STRING, PRIMARY KEY(key))',
    'CREATE REL TABLE IF NOT EXISTS PMGraphEdge(FROM PMGraphNode TO PMGraphNode, snapshot STRING, ordinal INT64, kind STRING, status STRING, payload STRING)',
)


def key(snapshot, uid):
    return json.dumps([snapshot,uid],ensure_ascii=False,separators=(',',':'))


def initialize(connection):
    for ddl in SCHEMA:connection.execute(ddl)


def _delete(connection,snapshot):
    connection.execute('MATCH (n:PMGraphNode {snapshot:$s}) DETACH DELETE n',{'s':snapshot})
    connection.execute('MATCH (n:PMGraphSnapshot {id:$s}) DELETE n',{'s':snapshot})


def _rollback_after_failure(connection,error):
    try:
        connection.execute('ROLLBACK')
    except Exception as cleanup_error:
        # Kuzu may already have aborted the transaction after a commit failure.
        error.add_note(f'Rollback also failed: {cleanup_error}')


def replace_snapshot(connection,graph):
    snapshot,metadata,node_rows,edge_rows = _prepare(graph)
    nodes = [{'key':key(snapshot,n[1]),'snapshot':snapshot,'id':n[1],'ordinal':i,
              'kind':n[2],'path':n[3],'line':n[4],'name':n[5],'payload':n[6]} for i,n in enumerate(node_rows)]
    edges = [{'source':key(snapshot,e[2]),'target':key(snapshot,e[3]),'snapshot':snapshot,
              'ordinal':e[1],'kind':e[4],'status':e[5],'payload':e[6]} for e in edge_rows]
    initialize(connection)
    connection.execute('BEGIN TRANSACTION')
    try:
        _delete(connection,snapshot)
        connection.execute('CREATE (:PMGraphSnapshot {id:$s,payload:$p})',{'s':snapshot,'p':metadata})
        for start in range(0,len(nodes),200):
            connection.execute('UNWIND $items AS i CREATE (:PMGraphNode {key:i.key,snapshot:i.snapshot,id:i.id,ordinal:i.ordinal,kind:i.kind,path:i.path,line:i.line,name:i.name,payload:i.payload})',{'items':nodes[start:start+200]})
        for start in range(0,len(edges),200):
            connection.execute('UNWIND $items AS i MATCH (a:PMGraphNode {key:i.source}),(b:PMGraphNode {key:i.target}) CREATE (a)-[:PMGraphEdge {snapshot:i.snapshot,ordinal:i.ordinal,kind:i.kind,status:i.status,payload:i.payload}]->(b)',{'items':edges[start:start+200]})
        connection.execute('COMMIT')
    except BaseException as error:
        _rollback_after_failure(connection,error)
        raise
    return {'snapshot':snapshot,'nodes':len(nodes),'edges':len(edges)}


def delete_snapshot(connection,snapshot):
    if not isinstance(snapshot,str) or not snapshot:raise ValueError('snapshot must be a nonempty string')
    initialize(connection)
    connection.execute('BEGIN TRANSACTION')
    try:
        _delete(connection,snapshot)
        connection.execute('COMMIT')
    except BaseException as error:
        _rollback_after_failure(connection,error)
        raise


def read_snapshot(connection,snapshot):
    metadata = rows(connection.execute('MATCH (s:PMGraphSnapshot {id:$s}) RETURN s.payload AS payload',{'s':snapshot}))
    if not metadata:return None
    graph = json.loads(metadata[0]['payload'])
    graph['nodes'] = [json.loads(r['payload']) for r in rows(connection.execute(
        'MATCH (n:PMGraphNode {snapshot:$s}) RETURN n.payload AS payload ORDER BY n.ordinal',{'s':snapshot}))]
    graph['edges'] = [json.loads(r['payload']) for r in rows(connection.execute(
        'MATCH ()-[e:PMGraphEdge]->() WHERE e.snapshot=$s RETURN e.payload AS payload ORDER BY e.ordinal',{'s':snapshot}))]
    return graph
