import importlib
import unittest
from unittest.mock import patch

module=importlib.import_module('experiments.2026-10-24-p7.project_query')
ProjectQuery=module.ProjectQuery


def fixture():
    nodes=[{'id':'api','name':'fetch','kind':'callable','definition':True,'path':'ui/api.ts','line':2},
           {'id':'message','name':'fetch message','kind':'protocol_message','payload':{'fields':{'op':{'state':'constant','value':'changed/name'}}}},
           {'id':'message:p:registration','kind':'protocol_registration','name':'register'},
           {'id':'handler','kind':'callable','name':'handle','definition':True,'path':'server/a.cpp','line':3}]
    edges=[{'source':a,'target':b,'kind':k,'evidence':[{'path':'server/a.cpp','line':3}],'conditions':['service_selected']} for a,b,k in
           [('api','message','EMITS_MESSAGE'),('message','message:p:registration','MATCHES_REGISTERED_PROTOCOL'),('message:p:registration','handler','RESOLVES_HANDLER')]]
    return {'nodes':nodes,'edges':edges,'source_commit':'commit','snapshot':'snapshot','version':{},
        'input_paths':['ui/api.ts','server/a.cpp'],'coverage':[{'path':'ui/api.ts','status':'parsed'}],
        'protocol':{'providers':[{'id':'p','command_fields':['op']}],
            'results':[{'name':'fetch','message':'message','status':'matched_conditional','matches':[{'provider':'p','conditions':['service_selected']}]},
                       {'name':'no_socket','matches':[],'status':'unresolved'}]},
        'data':{'storages':[],'accesses':[],'summaries':[],'field_flow':{}},'diagnostics':[]}


class P7QueryTests(unittest.TestCase):
    def test_coverage_signals_stay_separate_and_versioned(self):
        catalog={'source_commit':'commit','snapshot':'snapshot','languages':[],
                 'capabilities':[{'id':'ffi','support':'inventory_only','evidence':[{'path':'a.rs','line':1},{'path':'b.py','line':2}]}]}
        q=ProjectQuery(fixture(),catalog=catalog);r=q.coverage('ffi',limit=1)
        self.assertEqual(r['evidence_kind'],'lexical_candidate_not_semantic_relation')
        self.assertTrue(r['truncated']);self.assertEqual(r['next_offset'],1)
        self.assertEqual(q.coverage()['items'][0]['support'],'inventory_only')
        catalog['snapshot']='other'
        with self.assertRaises(ValueError):ProjectQuery(fixture(),catalog=catalog)

    def test_protocol_provider_record_is_not_graph_node_and_new_command_is_discovered(self):
        q=ProjectQuery(fixture());r=q.trace('changed/name')
        self.assertEqual(r['items'][0]['provider']['id'],'p')
        self.assertEqual(r['items'][0]['handlers'][0]['id'],'handler')
        self.assertEqual(r['items'][0]['conditions'],['service_selected'])
        self.assertTrue(q.trace('fetch',depth=0)['items'][0]['depth_limit_reached'])

    def test_pagination_and_unexpanded_inventory_and_stale_source(self):
        q=ProjectQuery(fixture(),{'source_commit':'commit','modules':[{'path':'missing','file_count':3}]})
        self.assertEqual(q.overview()['items'][0]['semantic_coverage'],'not_expanded')
        r=q.search(limit=1);self.assertTrue(r['truncated']);self.assertEqual(r['next_offset'],1)
        self.assertEqual(q.search(offset=1,limit=1)['items'][0]['id'],'message')
        q.inventory['source_commit']='other'
        with self.assertRaises(ValueError):q.overview()

    def test_reverse_impact_has_path_and_never_proves_absence(self):
        q=ProjectQuery(fixture());r=q.impact(name='handle')
        self.assertEqual(r['items'][0]['name'],'fetch');self.assertTrue(r['items'][0]['witness_paths'][0]['found'])
        self.assertTrue(q.impact(name='handle',depth=0)['depth_limit_reached'])
        self.assertEqual(q.trace('handle',reverse=True)['items'][0]['name'],'fetch')
        self.assertEqual(q.trace('absent')['missing_path_meaning'],'unknown')
        self.assertEqual(q.assets()['risk_assessment'],'not_performed')
        edge=q.graph['edges'][0];selector={k:edge[k] for k in ('source','target','kind')}
        self.assertEqual(q.explain(edge=selector)['items'],[edge])

    def test_unmatched_provider_is_kept_and_invalid_limits_rejected(self):
        g=fixture();g['protocol']['results'][0].update(matches=[],status='unmatched');q=ProjectQuery(g)
        self.assertEqual(q.trace('fetch')['items'][0]['status'],'unmatched')
        for limit in (0,501):
            with self.assertRaises(ValueError):q.search(limit=limit)
        with self.assertRaises(ValueError):q.trace('fetch',depth=65)

    def test_old_runtime_never_carries_verification_forward(self):
        q=ProjectQuery(fixture())
        record={'id':'run','basis':{'snapshot':'older','source_commit':'commit'},'provenance':{},
                'payload':{'execution_context':{'scenario':{'name':'normal'}},'events':[{'stage':'send'}],'outcome':{'status':'pass'},
                           'mappings':[{'role':'observed_dispatch_target','status':'mapped','node':{'name':'SelectedImplementation'}},
                                       {'role':'capture_hook','status':'mapped','node':{'name':'NotAnObservedTarget'}}]}}
        with patch.object(module,'query_records',return_value={'items':[{'record':record}]}):r=q.runs('unused')
        row=r['items'][0];self.assertFalse(row['eligible_for_direct_overlay']);self.assertFalse(row['verification_carried_forward'])
        self.assertEqual(row['reason'],'different_graph_snapshot')
        self.assertEqual(row['observed_dispatch_targets'],['SelectedImplementation'])
