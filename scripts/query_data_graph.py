"""Query implementation/impact paths or explain one C++ receiver's sources."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.data_graph import END_TO_END_KINDS,RESOURCE_IMPACT_KINDS,INSTANCE_IMPACT_KINDS
from adapters.data_queries import explain_receiver
from adapters.field_queries import explain_writes
from adapters.serialization_queries import explain_serialization
from adapters.response_queries import explain_response
from adapters.fact_queries import find_path
from scripts.query_protocol_graph import resolve


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('graph',type=Path)
    ap.add_argument('--from',dest='start');ap.add_argument('--to',dest='target');ap.add_argument('--reverse',action='store_true')
    ap.add_argument('--impact',action='store_true');ap.add_argument('--receiver',help='exact C++ call-site ID')
    ap.add_argument('--writes',help='callable ID or unique name for source field effects')
    ap.add_argument('--serialization',help='serializer callback ID or unique name')
    ap.add_argument('--response-provider',help='exact P2 provider ID for object-scoped response routing')
    ap.add_argument('--instance-impact',action='store_true',help='use source receiver-instance contexts')
    ap.add_argument('--depth',type=int,default=16);a=ap.parse_args();graph=json.loads(a.graph.read_text(encoding='utf-8'))
    if a.receiver:result=explain_receiver(graph,a.receiver)
    elif a.writes:result=explain_writes(graph,resolve(graph,a.writes),max_depth=a.depth)
    elif a.serialization:result=explain_serialization(graph,resolve(graph,a.serialization))
    elif a.response_provider:result=explain_response(graph,a.response_provider,max_depth=a.depth)
    else:result=find_path(graph,resolve(graph,a.start),resolve(graph,a.target),INSTANCE_IMPACT_KINDS if a.instance_impact else RESOURCE_IMPACT_KINDS if a.impact else END_TO_END_KINDS,
                          reverse=a.reverse,max_depth=a.depth)
    print(json.dumps(result,ensure_ascii=False,indent=2))
