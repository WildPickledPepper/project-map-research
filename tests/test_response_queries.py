"""Source extraction tests with a synthetic, already-resolved P2 provider input."""
import unittest
import re

import tests.test_data_graph as data_graph_tests
from adapters.response_queries import explain_response

SOURCE='''
using J=rapidjson::Value;
struct Request{std::string service;std::string op;};
void decode(const J& json,Request& r){r.service=json["service"].GetString();r.op=json["op"].GetString();}
struct Root{std::string domain;std::string code;};
struct Output:Root{int value;};
struct Codec{
 std::map<std::string,Fn> callbacks;
 std::optional<Fn> pick(const std::string& key){return callbacks[key];}
 J convert(const Root& response){auto fn=pick(response.code);return fn.value()(response);}
};
struct CodecA:Codec{
 void init(){callbacks.emplace("execute",render);}
 static J render(const Root& response){const Output& output=static_cast<const Output&>(response);J j;j.AddMember("external",output.value,a);return j;}
};
struct CodecB:Codec{
 void init(){callbacks.emplace("execute",render);}
 static J render(const Root& response){const Output& output=static_cast<const Output&>(response);J j;j.AddMember("external",output.value,a);return j;}
};
struct Manager{
 std::map<std::string,std::unique_ptr<Codec>> codecs;
 J dispatch(const Root& response){return codecs.at(response.domain)->convert(response);}
};
void seed(const Request& request,Root& response){response.domain=request.service;response.code=request.op;}
void sender(std::unique_ptr<Root> ptr,bool okay=true){Manager m;m.dispatch(*ptr.get());}
void entry(Request& q){std::unique_ptr<Output> out=std::make_unique<Output>();Output& r=*out.get();seed(q,r);r.value=1;sender(std::move(out));}
'''


class ResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):data_graph_tests.DataGraphTests.setUpClass()

    def graph(self,source=SOURCE):
        g=data_graph_tests.DataGraphTests().graph(source);uid=data_graph_tests.DataGraphTests.symbol(g,'entry')
        # This contract is the input from P2; every response relation is extracted.
        evidence=[{'path':'a.cpp','line':1,'expression':'synthetic P2 provider'}]
        g['protocol']={'providers':[{'id':'provider','handler_methods':[uid],'command':'execute',
            'scope_values':['alpha'],'command_fields':['op'],'scope_fields':['service'],
            'decoder_registration':{'owner':'CodecA','functions':[data_graph_tests.DataGraphTests.symbol(g,'decode')]},
            'scope_registrations':[{'registry':'Manager::codecs','factory_method':'getCodec'}],
            'factory_group':{'components':[{'class':'CodecA','method':'getCodec','evidence':evidence}]}}]}
        return g

    def test_source_field_renames_object_transfer_and_registry_scope(self):
        g=self.graph();r=explain_response(g,'provider');self.assertFalse(r['truncated'])
        route,=r['routes'];self.assertEqual(route['protocol_owner'],'CodecA')
        self.assertEqual(route['serializer'],data_graph_tests.DataGraphTests.symbol(g,'CodecA::render'))
        mapping,=route['field_mappings'];self.assertEqual(mapping['wire_path'],['external'])
        self.assertEqual(mapping['selectors'],['pointee','member:value'])
        link,=route['production_links'];self.assertEqual(link['selectors'],['pointee','member:value'])
        self.assertEqual(len(route['steps']),4)
        self.assertTrue(all(s['evidence'] for s in route['steps']))

    def test_wrong_module_key_is_not_joined_to_same_command(self):
        g=self.graph(SOURCE.replace('r.value=1;','r.value=1;r.domain="beta";'))
        self.assertEqual(explain_response(g,'provider')['routes'],[])

    def test_wrapper_key_rewrite_changes_selection(self):
        g=self.graph(SOURCE.replace('Manager m;m.dispatch(*ptr.get());','ptr->code="different";Manager m;m.dispatch(*ptr.get());'))
        self.assertEqual(explain_response(g,'provider')['routes'],[])

    def test_unknown_and_conditional_key_writes_remain_unknown(self):
        for expr in ['r.code=opaque();','if(mode)r.code="different";','r.code+="execute";']:
            r=explain_response(self.graph(SOURCE.replace('r.value=1;','r.value=1;'+expr)),'provider')
            self.assertEqual(r['routes'],[])
            self.assertTrue(any(g['kind']=='callback_key_unknown' for g in r['gaps']))

    def test_another_response_object_does_not_inherit_production(self):
        s=SOURCE.replace('sender(std::move(out));','std::unique_ptr<Output> other=std::make_unique<Output>();seed(q,*other.get());sender(std::move(other));')
        r=explain_response(self.graph(s),'provider')
        self.assertTrue(r['routes']);self.assertTrue(all(not route['production_links'] for route in r['routes']))

    def test_send_before_write_has_no_production_link(self):
        s=SOURCE.replace('r.value=1;sender(std::move(out));','sender(std::move(out));r.value=1;')
        route,=explain_response(self.graph(s),'provider')['routes'];self.assertFalse(route['production_links'])

    def test_unresolved_scope_does_not_select_unique_callback(self):
        s=SOURCE.replace('response.domain=request.service;','response.domain=opaque();')
        r=explain_response(self.graph(s),'provider');self.assertEqual(r['routes'],[])
        self.assertTrue(any(g['kind']=='protocol_scope_key_unknown' for g in r['gaps']))

    def test_state_budget_is_reported(self):
        r=explain_response(self.graph(),'provider',max_states=1);self.assertTrue(r['truncated'])
        with self.assertRaises(ValueError):explain_response(self.graph(),'provider',max_states=0)

    def test_unused_decoder_cannot_supply_request_identity(self):
        s=SOURCE.replace('r.service=json["service"].GetString();','r.service=opaque();')
        s+='void unused(const J& json,Request& r){r.service=json["service"].GetString();}'
        self.assertEqual(explain_response(self.graph(s),'provider')['routes'],[])

    def test_unexpanded_queue_branch_and_unknown_object_call_are_reported(self):
        s=SOURCE.replace('Manager m;m.dispatch(*ptr.get());','if(queued)queue << std::move(ptr);else{opaque(*ptr.get());Manager m;m.dispatch(*ptr.get());}')
        r=explain_response(self.graph(s),'provider');self.assertTrue(r['routes'])
        self.assertTrue({'operator_transfer_not_expanded','call_effects_unresolved'}<={g['kind'] for g in r['gaps']})

    def test_project_identifiers_can_change_without_new_rules(self):
        s=SOURCE
        for old,new in [('domain','region'),('code','routeKey'),('sender','deliver'),('seed','prepare'),('external','renamed')]:
            s=re.sub(r'\b'+old+r'\b',new,s)
        route,=explain_response(self.graph(s),'provider')['routes']
        self.assertEqual(route['field_mappings'][0]['wire_path'],['renamed'])
