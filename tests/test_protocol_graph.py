from copy import deepcopy
import unittest
from adapters.protocol_graph import augment,match_message,PROTOCOL_KINDS
from adapters.fact_queries import find_path


def provider(uid='a',module='north',path='server-a/handler.cpp'):
    evidence=[{'path':path,'line':1}]
    reg={'path':path,'line':1,'value_expression':'make_unique<Work>()','evidence':evidence,'functions':[]}
    return {'id':uid,'path':path,'line':1,'command':'read','command_fields':['verb'],'scope_values':[module],
            'scope_fields':['space'],'status':'registered_candidate','handler_methods':['handler:'+uid],
            'decoded_key_status':'source_mapping_candidate','decoded_key_mappings':[],
            'factory_group':{},'scope_lookups':[],'handler_registration':reg,'decoder_registration':reg,
            'dispatch_evidence':[{'id':'handler:'+uid,'evidence':evidence}]}


def message(module='north',path='client-a/send.ts',command='read'):
    def value(v):return {'state':'constant','value':v} if v is not None else {'state':'unknown'}
    return {'path':path,'line':8,'transport':'socket','payload':{'state':'object','fields':{'verb':value(command),'space':value(module)}},
            'events':[{'kind':'platform_send','path':path,'line':8}],'conditions':[]}


CONFIG={'services':[{'id':x,'consumer_paths':['client-'+x],'provider_paths':['server-'+x]} for x in ['a','b']]}


class ProtocolGraphTests(unittest.TestCase):
    def test_same_command_in_two_services_is_isolated(self):
        result=match_message(message(),[provider(),provider('b',path='server-b/handler.cpp')],CONFIG)
        self.assertEqual(result['status'],'matched_conditional');self.assertEqual([p['provider'] for p in result['matches']],['a'])

    def test_same_command_different_module_is_isolated(self):
        result=match_message(message(),[provider(),provider('b','south')],CONFIG)
        self.assertEqual([p['provider'] for p in result['matches']],['a'])

    def test_unknown_service_is_multiple_candidates(self):
        result=match_message(message(path='unknown/send.ts'),[provider(),provider('b',path='server-b/handler.cpp')],CONFIG)
        self.assertEqual(result['status'],'ambiguous');self.assertEqual(len(result['matches']),2)
        self.assertTrue(all('service_scope_unknown_or_ambiguous' in m['gaps'] for m in result['matches']))

    def test_unknown_module_keeps_multiple_candidates(self):
        result=match_message(message(module=None),[provider(),provider('b','south')],CONFIG)
        self.assertEqual(result['status'],'ambiguous')

    def test_unknown_command_never_claims_a_target(self):
        result=match_message(message(command=None),[provider()],CONFIG)
        self.assertEqual(result['status'],'unknown');self.assertEqual(result['matches'],[])

    def test_deleted_provider_is_unmatched(self):
        self.assertEqual(match_message(message(),[],CONFIG)['status'],'unmatched')

    def test_duplicate_provider_is_ambiguous(self):
        self.assertEqual(match_message(message(),[provider(),provider('other')],CONFIG)['status'],'ambiguous')

    def test_unresolved_decode_copy_is_visible(self):
        p=provider();p['decoded_key_status']='unresolved'
        result=match_message(message(),[p],CONFIG)
        self.assertEqual(result['status'],'candidate');self.assertIn('decoded_dispatch_key_mapping_unresolved',result['matches'][0]['gaps'])

    def test_shared_sender_does_not_connect_unrelated_requests(self):
        ps=[provider(),provider('b','south')]
        graph={'nodes':[{'id':x,'kind':'callable','name':x,'path':'a.ts','line':1} for x in ['entry-a','entry-b','handler:a','handler:b']], 'edges':[]}
        consumers=[{'id':x,'name':x,'source_owner':x,'source_call':x,'boundaries':[message(module=m)],'status':'transport_found'} for x,m in [('entry-a','north'),('entry-b','south')]]
        g=augment(graph,{'consumers':consumers,'limits':[]},{'providers':ps,'limits':[]},CONFIG)
        self.assertTrue(find_path(g,'entry-a','handler:a',PROTOCOL_KINDS)['found'])
        self.assertTrue(find_path(g,'handler:a','entry-a',PROTOCOL_KINDS,reverse=True)['found'])
        self.assertFalse(find_path(g,'entry-a','handler:b',PROTOCOL_KINDS)['found'])
        self.assertFalse(find_path(g,'handler:a','entry-b',PROTOCOL_KINDS,reverse=True)['found'])
        self.assertEqual({e['status'] for e in g['edges']},{'conditional'})
        # Deletion after rebuilding leaves no old handler edges.
        graph['nodes']=[n for n in graph['nodes'] if n['id']!='handler:a']
        g2=augment(graph,{'consumers':consumers,'limits':[]},{'providers':[ps[1]],'limits':[]},CONFIG)
        self.assertFalse(any(e['target']=='handler:a' for e in g2['edges']))
