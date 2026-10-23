"""Bounded traversal of typed evidence edges, with explicit candidate status."""
from collections import defaultdict,deque


def find_path(graph,start,target,kinds,reverse=False,max_depth=12):
    if max_depth<0:raise ValueError('max_depth must be nonnegative')
    nodes={n['id']:n for n in graph['nodes']}
    if start not in nodes or target not in nodes:raise ValueError('Unknown endpoint')
    outgoing=defaultdict(list)
    for e in graph['edges']:
        if e['kind'] in kinds:outgoing[e['target'] if reverse else e['source']].append(e)
    queue=deque([(start,[])])
    seen={start};truncated=False
    while queue:
        current,path=queue.popleft()
        if current==target:
            ids=[start]+[e['source'] if reverse else e['target'] for e in path]
            return {'found':True,'reverse':reverse,'max_depth':max_depth,'depth_limit_reached':truncated,
                    'nodes':[nodes[i] for i in ids],'edges':path,
                    'meaning':'structural_evidence_path_not_observed_execution'}
        for e in outgoing[current]:
            nxt=e['source'] if reverse else e['target']
            if nxt in seen:continue
            if len(path)>=max_depth:truncated=True;continue
            seen.add(nxt);queue.append((nxt,path+[e]))
    return {'found':False,'reverse':reverse,'max_depth':max_depth,'depth_limit_reached':truncated,
            'nodes':[],'edges':[],'visited':len(seen),'meaning':'missing_path_does_not_prove_independence'}
