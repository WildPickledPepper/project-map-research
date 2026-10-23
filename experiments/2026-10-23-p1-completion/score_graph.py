"""Independent case assertions over an already generated graph; never imported by extraction."""
from collections import Counter
from adapters.fact_queries import find_path


def score(graph):
    nodes=graph['nodes']
    def one(name,**fields):
        matches=[n for n in nodes if n['name']==name and all(n.get(k)==v for k,v in fields.items())]
        assert len(matches)==1,(name,fields,len(matches))
        return matches[0]
    start=one('getUnitFlows',kind='callable')
    end=one('ClientConnector.send',kind='callable')
    ts_kinds={'OBSERVES_CALL','USES_BINDING','BINDS_CALLABLE','STATIC_CALL_TARGET','STATIC_DECLARATION_TARGET','PASSES_CALLBACK'}
    paths={'frontend':find_path(graph,start['id'],end['id'],ts_kinds),
           'frontend_reverse':find_path(graph,end['id'],start['id'],ts_kinds,reverse=True)}
    assert paths['frontend']['found'] and paths['frontend_reverse']['found']
    assert {'USES_BINDING','BINDS_CALLABLE'} <= {e['kind'] for e in paths['frontend']['edges']}
    binding=one('window.requestData',kind='binding',path='modules/timeline/src/bootstrap.tsx')
    factory=one('createRequest',kind='callable')
    assert any(e['source']==binding['id'] and e['target']==factory['id'] and e['kind']=='BINDS_RESULT_OF' for e in graph['edges'])
    assert any(n['name']=='BaseConnector.send' and n.get('type_parameters') for n in nodes)
    send_call=one('this.send',kind='call_site',path='modules/lib/src/connection/index.ts',line=188)
    assert [e['target'] for e in graph['edges'] if e['source']==send_call['id'] and e['kind']=='STATIC_CALL_TARGET']==[end['id']]
    handler=one('Dic::Module::Timeline::QueryFlowsBySliceInfoHandler::HandleRequest',definition=True)
    virtual=one('Dic::Module::Timeline::VirtualTraceDatabase::QueryUnitFlows',kind='callable')
    assert virtual['pure_virtual']
    cpp_kinds={'OBSERVES_CALL','MEMBER_TARGET_CANDIDATE','OVERRIDE_CANDIDATE','DECLARES_DEFINITION'}
    for label,name in [('db','Dic::Module::FullDb::DbTraceDataBase::QueryUnitFlows'),('text','Dic::Module::Timeline::TextTraceDatabase::QueryUnitFlows')]:
        target=one(name,definition=True)
        paths[label]=find_path(graph,handler['id'],target['id'],cpp_kinds)
        paths[label+'_reverse']=find_path(graph,target['id'],handler['id'],cpp_kinds,reverse=True)
        assert paths[label]['found'] and paths[label+'_reverse']['found']
        assert virtual['id'] in {n['id'] for n in paths[label]['nodes']}
        assert any(e['kind']=='OVERRIDE_CANDIDATE' and e['runtime_selection']=='unknown' for e in paths[label]['edges'])
    assert all(n.get('reason') for n in nodes if n['kind']=='call_site' and n['resolution']=='unresolved')
    assert len(graph['coverage'])==len(graph['input_paths'])==65
    assert {r['path'] for r in graph['coverage']}==set(graph['input_paths'])
    return {'checks':{'F01':'pass','F02':'pass','F03':'pass'},'paths':paths,
            'counts':{'nodes':len(nodes),'edges':len(graph['edges']),
                      'node_kinds':dict(Counter(n['kind'] for n in nodes)),
                      'edge_kinds':dict(Counter(e['kind'] for e in graph['edges'])),
                      'call_resolutions':dict(Counter(n['resolution'] for n in nodes if n['kind']=='call_site')),
                      'diagnostics':dict(Counter(d.get('kind','unknown') for d in graph['diagnostics']))},
            'coverage':graph['coverage'],'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],
            'extractors':graph['extractors'],'compiler_options':graph['compiler_options'],
            'compiler_options_origin':graph['compiler_options_origin'],'limits':graph['limits'],
            'unresolved_examples':[n for n in nodes if n['kind']=='call_site' and n['resolution']=='unresolved'][:8],
            'binding_factory_edges':[e for e in graph['edges'] if e['source']==binding['id']]}
