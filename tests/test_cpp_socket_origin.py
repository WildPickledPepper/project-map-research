import json
import unittest

from adapters.cpp_data import DataExtractor
from adapters.cpp_socket_origin import SocketOrigins
from adapters.server_channel_queries import origin_links
import tests.test_cpp_data as data_tests


SOURCE = '''
using Channel = uWS::WebSocket<false,true,int>;
struct Session { Channel* wire;
  Session(Channel* incoming):wire(incoming){}
  void respond(int message){wire->send(message);}
};
struct Registry { std::shared_ptr<Session> held;
  static Registry& global(){static Registry one;return one;}
  static Registry& other(){static Registry two;return two;}
  void put(std::shared_ptr<Session> next){if(!held){held=std::move(next);}}
  std::shared_ptr<Session> take(){return held;}
};
struct Service { std::unique_ptr<uWS::App> app;
  uWS::App::WebSocketBehavior<int> behavior(){
    uWS::App::WebSocketBehavior<int> config={.open=std::bind(&Service::accept,this,std::placeholders::_1)};
    return config;
  }
  void accept(Channel* input){if(!input)return;
    auto created=std::make_shared<Session>(input);Registry::global().put(created);
  }
  void start(){app=std::make_unique<uWS::App>();auto config=behavior();
    app->ws<int>("/*",std::move(config));app->listen("localhost",9000,unknown);
  }
};
void reply(int n){auto picked=Registry::global().take();picked->respond(n);}
'''


class SocketOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): data_tests.CppDataTests.setUpClass(); cls.parser = data_tests.CppDataTests.parser

    def analyze(self, source=SOURCE, **limits):
        self.data = DataExtractor({'a.cpp': source.encode()}, self.parser)
        result = SocketOrigins(self.data, **limits).build()
        self.assertEqual(result, json.loads(json.dumps(result)))
        return result

    def test_accept_constructor_store_getter(self):
        r = self.analyze()
        registration, = r['registrations']; listening, = r['listeners']; initial, = r['channel_initializers']
        store, = r['object_stores']; consumer, = r['member_consumers']
        self.assertEqual(registration['app']['instance'], listening['app']['instance'])
        self.assertEqual(initial['origin']['registration'], registration['id'])
        self.assertEqual(initial['allocation'], store['allocation'])
        self.assertEqual((store['member'], store['receiver_instance']), (consumer['member'], consumer['receiver_instance']))
        self.assertTrue(any('!held' in c.get('expression', '') and c['when'] for c in store['conditions']))

    def test_application_names_can_change(self):
        src = SOURCE
        for old, new in [('Service','Renamed'),('Session','Peer'),('Registry','Hub'),('held','active'),('wire','pipe'),('accept','receive'),('put','save'),('take','load')]:
            src = src.replace(old, new)
        r = self.analyze(src)
        self.assertEqual(len(r['channel_initializers']), 1); self.assertEqual(len(r['object_stores']), 1)

    def test_wrong_placeholder_does_not_create_channel_origin(self):
        r = self.analyze(SOURCE.replace('std::placeholders::_1', 'std::placeholders::_2'))
        self.assertFalse(r['channel_initializers'])

    def test_overwritten_channel_before_allocation(self):
        r = self.analyze(SOURCE.replace('auto created=', 'input=nullptr;auto created='))
        self.assertFalse(r['channel_initializers'])

    def test_constructor_overwrites_member(self):
        for body in ['wire=nullptr;', 'this->wire=nullptr;']:
            r = self.analyze(SOURCE.replace(':wire(incoming){}', ':wire(incoming){' + body + '}'))
            self.assertFalse(r['channel_initializers'])

    def test_callback_overwrite_removes_origin(self):
        r = self.analyze(SOURCE.replace('return config;', 'config.open=nullptr;return config;'))
        self.assertFalse(r['channel_initializers']); self.assertTrue(r['diagnostics'])

    def test_other_registry_keeps_distinct_identity(self):
        r = self.analyze(SOURCE.replace('picked=Registry::global()', 'picked=Registry::other()'))
        self.assertNotEqual(r['object_stores'][0]['receiver_instance'], r['member_consumers'][0]['receiver_instance'])

    def test_fake_app_is_not_native(self):
        r = self.analyze(SOURCE.replace('uWS::App', 'FakeApp'))
        self.assertFalse(r['registrations']); self.assertFalse(r['channel_initializers'])

    def test_unexpanded_lambda_field_remains_serializable(self):
        r = self.analyze(SOURCE.replace('config={.open=', 'config={.upgrade=[](auto* p){opaque(p);},.open='))
        self.assertEqual(len(r['channel_initializers']), 1)

    def test_budgets_report_truncation(self):
        r = self.analyze(max_depth=1)
        self.assertFalse(r['channel_initializers']); self.assertTrue(r['diagnostics'])

    def test_unknown_mutator_drops_callback_and_channel(self):
        for src in [SOURCE.replace('return config;', 'opaque(config);return config;'),
                    SOURCE.replace('auto created=', 'opaque(input);auto created=')]:
            r = self.analyze(src); self.assertFalse(r['channel_initializers'])
            self.assertTrue(any(d['kind'] == 'unexpanded_mutable_argument' for d in r['diagnostics']))

    def test_variadic_value_parameters_keep_channel_identity(self):
        prefix = 'template<typename... T>void note(const T... args){}\n'
        r = self.analyze(prefix + SOURCE.replace('auto created=', 'note("seen",input);auto created='))
        self.assertEqual(len(r['channel_initializers']), 1)

    def test_constructor_parameter_shadow_does_not_overwrite_member(self):
        r = self.analyze(SOURCE.replace('Session(Channel* incoming):wire(incoming){}', 'Session(Channel* wire):wire(wire){wire=nullptr;}'))
        self.assertEqual(len(r['channel_initializers']), 1)

    def test_source_mutator_rebinding_pointer_is_a_gap(self):
        r = self.analyze(SOURCE.replace('struct Session', 'void reset(Channel*& x){x=nullptr;}\nstruct Session').replace('auto created=', 'reset(input);auto created='))
        self.assertFalse(r['channel_initializers'])

    def test_behavior_copy_keeps_independent_callback(self):
        r = self.analyze(SOURCE.replace('return config;', 'auto saved=config;config.open=nullptr;return saved;'))
        self.assertEqual(len(r['channel_initializers']), 1)

    def test_listener_on_other_app_is_separate(self):
        r = self.analyze(SOURCE.replace('app->listen', 'auto other=std::make_unique<uWS::App>();other->listen'))
        links = origin_links({'server_channels': r})
        self.assertEqual(len(links), 1); self.assertFalse(links[0]['listen_candidates'])

    def test_scoped_store_getter_join_rejects_different_instance(self):
        r = self.analyze(SOURCE.replace('picked=Registry::global()', 'picked=Registry::other()'))
        self.assertFalse(origin_links({'server_channels': r}))

    def test_missing_constructor_store_or_getter_disconnects(self):
        from copy import deepcopy
        r = self.analyze(); self.assertEqual(len(origin_links({'server_channels': r})), 1)
        for group in ['channel_initializers', 'object_stores', 'member_getters']:
            changed = deepcopy(r); changed[group] = []
            self.assertFalse(origin_links({'server_channels': changed}))

    def test_reassigned_consumer_has_no_old_getter(self):
        r = self.analyze(SOURCE.replace('picked->respond', 'picked=unknown();picked->respond'))
        self.assertFalse(r['member_consumers'])

    def test_mutated_consumer_has_no_old_getter(self):
        r = self.analyze(SOURCE.replace('picked->respond', 'opaque(picked);picked->respond'))
        self.assertFalse(r['member_consumers'])

    def test_opposite_listen_branch_is_not_same_path(self):
        r = self.analyze(SOURCE.replace('app->ws<int>("/*",std::move(config));app->listen("localhost",9000,unknown);',
            'if(flag){app->ws<int>("/*",std::move(config));}else{app->listen("localhost",9000,unknown);}'))
        links = origin_links({'server_channels': r})
        self.assertEqual(len(links), 1); self.assertFalse(links[0]['listen_candidates'])

    def test_graph_roundtrip_and_traversable_origin(self):
        from adapters.server_channel_graph import augment_server_channels
        from adapters.sqlite_fact_graph import _prepare, replace_snapshot
        from tests.test_sqlite_fact_graph import read_graph
        import sqlite3
        r = self.analyze(); base = {'nodes': [], 'edges': [], 'snapshot': 'test:base', 'source_commit': 'test',
            'input_paths': ['a.cpp'], 'extractors': {}, 'provenance': {}, 'diagnostics': []}
        graph = augment_server_channels(base, self.data.facts, r, ['a.cpp']); _prepare(graph)
        with sqlite3.connect(':memory:') as conn:
            conn.execute('PRAGMA foreign_keys=ON'); replace_snapshot(conn, graph)
            saved = read_graph(conn, graph['snapshot']); self.assertEqual(saved, graph)
            self.assertEqual(origin_links(saved), origin_links(graph))
        link, = origin_links(graph)
        self.assertTrue(any(e['source'] == link['id'] and e['target'] == link['consumer']['id'] for e in graph['edges']))


if __name__ == '__main__': unittest.main()
