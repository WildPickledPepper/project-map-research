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
from adapters.frontend_queries import explain_frontend
from adapters.callback_queries import explain_callbacks
from adapters.correlation_queries import explain_correlation
from adapters.fact_queries import find_path
from scripts.query_protocol_graph import resolve


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('graph',type=Path)
    ap.add_argument('--from',dest='start');ap.add_argument('--to',dest='target');ap.add_argument('--reverse',action='store_true')
    ap.add_argument('--impact',action='store_true');ap.add_argument('--receiver',help='exact C++ call-site ID')
    ap.add_argument('--writes',help='callable ID or unique name for source field effects')
    ap.add_argument('--serialization',help='serializer callback ID or unique name')
    ap.add_argument('--response-provider',help='exact P2 provider ID for object-scoped response routing')
    ap.add_argument('--frontend-api',help='API callable ID or unique name; fulfillment boundary to consumers')
    ap.add_argument('--frontend-state',help='exact scoped state node ID; reverse lookup of API-result dependencies')
    ap.add_argument('--field-path',help='JSON array of API-result selectors, e.g. ["items","*","name"]')
    ap.add_argument('--response-requester',help='Promise-producing callable ID or unique name')
    ap.add_argument('--response-receiver',help='Registry-consuming callable ID or unique name')
    ap.add_argument('--correlation-provider',help='P2 provider ID for sent-key / response-lookup source correlation')
    ap.add_argument('--instance-impact',action='store_true',help='use source receiver-instance contexts')
    ap.add_argument('--depth',type=int,default=16);a=ap.parse_args();graph=json.loads(a.graph.read_text(encoding='utf-8'))
    if a.receiver:result=explain_receiver(graph,a.receiver)
    elif a.writes:result=explain_writes(graph,resolve(graph,a.writes),max_depth=a.depth)
    elif a.serialization:result=explain_serialization(graph,resolve(graph,a.serialization))
    elif a.response_provider:result=explain_response(graph,a.response_provider,max_depth=a.depth)
    elif a.correlation_provider:result=explain_correlation(graph,a.correlation_provider)
    elif a.response_requester or a.response_receiver:result=explain_callbacks(graph,
        requester=resolve(graph,a.response_requester) if a.response_requester else None,
        receiver=resolve(graph,a.response_receiver) if a.response_receiver else None)
    elif a.frontend_api or a.frontend_state:result=explain_frontend(graph,
        api=resolve(graph,a.frontend_api) if a.frontend_api else None,state=a.frontend_state,
        field_path=json.loads(a.field_path) if a.field_path is not None else None)
    else:result=find_path(graph,resolve(graph,a.start),resolve(graph,a.target),INSTANCE_IMPACT_KINDS if a.instance_impact else RESOURCE_IMPACT_KINDS if a.impact else END_TO_END_KINDS,
                          reverse=a.reverse,max_depth=a.depth)
    print(json.dumps(result,ensure_ascii=False,indent=2))
