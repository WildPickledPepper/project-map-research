import unittest

from adapters.cpp_data import DataExtractor
from adapters.cpp_transmission import Transmission
import tests.test_cpp_data as data_tests


PRELUDE = '''using J=rapidjson::Document;
J encode(int n){return J();}
std::string dump(const J& j){rapidjson::StringBuffer b;
rapidjson::Writer<rapidjson::StringBuffer> w(b);j.Accept(w);return b.GetString();}
'''


class TransmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): data_tests.CppDataTests.setUpClass(); cls.parser = data_tests.CppDataTests.parser

    def analyze(self, body, *, extra='', **limits):
        source = PRELUDE + extra + '''struct Session:std::enable_shared_from_this<Session>{
        uWS::Loop* loop;uWS::WebSocket<false,true,int>* socket;
        void deliver(const std::string& payload){if(closed)return;socket->send(payload,uWS::OpCode::TEXT);}
        void run(){J doc=encode(7);auto bytes=dump(doc);''' + body + '}};'
        d = DataExtractor({'a.cpp': source.encode()}, self.parser)
        result = Transmission(d, **limits).build()
        # Ignore helper roots when checking entry-scoped extraction.
        entry = next(u for u, n in d.x.nodes.items() if n.get('definition') and n['name'] == 'Session::run')
        return {**result, 'transmissions': [t for t in result['transmissions'] if t['entry'] == entry],
                'diagnostics': [g for g in result['diagnostics'] if g['entry'] == entry]}

    def traces(self, r): return [v for t in r['transmissions'] for v in t['traces']]

    def test_writer_capture_deferred_member_send(self):
        r = self.analyze('loop->defer([this,bytes](){if(!ready)return;deliver(bytes);});')
        t, = r['transmissions']; trace, = t['traces']
        self.assertEqual(t['transport'], 'uWS::WebSocket::send')
        self.assertEqual(t['opcode'], 'uWS::OpCode::TEXT')
        self.assertTrue({'parameter_binding', 'rapidjson_accept', 'rapidjson_buffer_string', 'lambda_capture', 'socket_send_argument'} <= {s['kind'] for s in trace['steps']})
        self.assertTrue(any('ready' in c.get('expression', '') and not c['when'] for c in trace['conditions']))
        self.assertTrue(any('closed' in c.get('expression', '') and not c['when'] for c in trace['conditions']))
        self.assertEqual(len(t['deferred']), 1)

    def test_source_rename_does_not_change_rules(self):
        r = self.analyze('auto renamed=bytes;loop->defer([this,copy=renamed](){deliver(copy);});')
        self.assertEqual(len(self.traces(r)), 1)
        self.assertTrue(any(s.get('capture') == 'copy' for s in self.traces(r)[0]['steps']))

    def test_weak_self_lock_preserves_receiver_context(self):
        r = self.analyze('std::weak_ptr<Session> guard=shared_from_this();loop->defer([guard,bytes](){auto alive=guard.lock();if(!alive)return;alive->deliver(bytes);});')
        t, = r['transmissions']; self.assertTrue(t['traces']); self.assertIn('member', t['receiver']['instance'])
        self.assertTrue(any('alive' in c.get('expression', '') and not c['when'] for c in t['traces'][0]['conditions']))

    def test_overwritten_payload_has_no_old_lineage(self):
        r = self.analyze('bytes="replacement";deliver(bytes);')
        self.assertFalse(self.traces(r))

    def test_captured_value_survives_later_assignment(self):
        r = self.analyze('auto later=[this,bytes](){deliver(bytes);};bytes="replacement";loop->defer(later);')
        self.assertEqual(len(self.traces(r)), 1)

    def test_capture_reassignment_drops_lineage(self):
        r = self.analyze('loop->defer([this,bytes]()mutable{bytes="replacement";deliver(bytes);});')
        self.assertFalse(self.traces(r))

    def test_reference_capture_remains_gap(self):
        r = self.analyze('loop->defer([this,&bytes](){deliver(bytes);});')
        self.assertFalse(self.traces(r)); self.assertTrue(any(g['kind'] == 'deferred_reference_capture_unresolved' for g in r['diagnostics']))

    def test_fake_socket_and_scheduler_names_are_not_native(self):
        for body in ['Fake scheduler;scheduler.defer([this,bytes](){deliver(bytes);});',
                     'Fake other;other.send(bytes);']:
            r = self.analyze(body, extra='struct Fake{void send(const std::string&);template<class F>void defer(F);};')
            self.assertFalse(r['transmissions'])

    def test_mutating_helper_does_not_retain_stale_payload(self):
        r = self.analyze('replace(bytes);deliver(bytes);', extra='void replace(std::string& v){v="new";}')
        self.assertFalse(self.traces(r)); self.assertTrue(any(g['kind'] == 'mutable_argument_effect_not_expanded' for g in r['diagnostics']))

    def test_scoped_shadow_does_not_replace_outer_binding(self):
        r = self.analyze('{std::string bytes="local";}deliver(bytes);')
        self.assertEqual(len(self.traces(r)), 1)

    def test_conditional_compile_returns_are_kept_separate(self):
        extra = '''std::string convert(const std::string& data){
#ifdef FEATURE
if(change)return opaque(data);
#endif
return data;
}'''
        r = self.analyze('bytes=convert(bytes);deliver(bytes);', extra=extra)
        traces = self.traces(r); self.assertEqual(len(traces), 2)
        self.assertEqual({c['when'] for t in traces for c in t['conditions'] if c.get('kind') == 'preprocessor'}, {True, False})
        self.assertTrue(any(g['kind'] == 'source_return_has_unlinked_alternative' for g in r['diagnostics']))

    def test_new_document_is_not_joined_to_previous_document(self):
        r = self.analyze('J another=encode(9);auto other=dump(another);deliver(other);')
        trace, = self.traces(r)
        source = next(s for s in r['sources'] if s['id'] == trace['source'])
        self.assertEqual(source['evidence'][0]['expression'], 'encode(9)')

    def test_budget_exhaustion_is_reported(self):
        r = self.analyze('deliver(bytes);', max_steps=1)
        self.assertFalse(self.traces(r)); self.assertTrue(any(g['kind'] == 'analysis_budget_exhausted' for g in r['diagnostics']))

    def test_reference_alias_blocks_stale_payload(self):
        r = self.analyze('auto& alias=bytes;alias="replacement";deliver(bytes);')
        self.assertFalse(self.traces(r))

    def test_condition_mutation_invalidates_payload(self):
        r = self.analyze('if(replace(bytes))return;deliver(bytes);', extra='bool replace(std::string& v){v="new";return false;}')
        self.assertFalse(self.traces(r))

    def test_uncaptured_this_cannot_supply_socket(self):
        r = self.analyze('loop->defer([bytes](){deliver(bytes);});')
        self.assertFalse(r['transmissions'])

    def test_unknown_writer_effect_invalidates_buffer(self):
        code = 'using J=rapidjson::Document;void run(const J& j,uWS::WebSocket<false,true,int>* ws){rapidjson::StringBuffer b;rapidjson::Writer<rapidjson::StringBuffer> w(b);j.Accept(w);alter(b);ws->send(b.GetString());}'
        r = Transmission(DataExtractor({'a.cpp': code.encode()}, self.parser)).build()
        self.assertFalse(self.traces(r)); self.assertTrue(any(g['kind'] == 'unmodeled_buffer_effect' for g in r['diagnostics']))


if __name__ == '__main__': unittest.main()
