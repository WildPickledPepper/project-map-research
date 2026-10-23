import os
import unittest
import tree_sitter_language_pack as pack
from adapters.cpp_protocol import analyze_protocol

if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
    pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))

# Authored mechanism fixture. No Insight source or interface names are copied.
SOURCE=r'''
const std::string ACTION="alpha/read";
struct Record { std::string internalTag; };
struct AbstractWork { virtual bool execute(Record& r)=0; bool enter(Record& r){ return execute(r); } };
struct SpecificWork:AbstractWork { ~SpecificWork() override=default; bool execute(Record& r) override {return true;} };
void copyKey(std::string& dest, const Json& doc, std::string_view key){dest=doc[key.data()].GetString();}
struct Workers {
 std::map<std::string,std::unique_ptr<AbstractWork>> entries;
 void install(){entries.emplace(ACTION,std::make_unique<SpecificWork>());}
 void accept(Record& r){auto &w=entries.at(r.internalTag);w->enter(r);}
};
struct Codec {
 std::map<std::string,Fn> decoders;
 static Record decode(const Json& j){Record r;copyKey(r.internalTag,j,"wireTag");return r;}
 void install(){decoders.emplace(ACTION,decode);}
 Record read(const Json& j){auto key=j["wireTag"].GetString();return decoders.at(key)(j);}
};
struct Bundle:Base {
 Bundle():Base("north"){}
 auto workers(){return std::make_unique<Workers>();}
 auto codec(){return std::make_unique<Codec>();}
};
auto activation=std::make_unique<Bundle>();
struct Manager {
 std::map<std::string,std::unique_ptr<Codec>> codecs;
 void install(Bundle* b,std::string k){auto item=b->codec();codecs.emplace(k,std::move(item));}
 Record receive(const Json& j){auto key=j["space"].GetString();return codecs.at(key)->read(j);}
};
'''

class CppProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.parser=pack.get_parser('cpp')

    def graph(self,source=SOURCE,files=None):
        return analyze_protocol({p:s.encode() for p,s in (files or {'a.cpp':source}).items()},self.parser)

    def test_registries_scope_decode_and_dispatched_override(self):
        g=self.graph();p,=g['protocol']['providers'];nodes={n['id']:n for n in g['facts']['nodes']}
        self.assertEqual((p['command'],p['command_fields'],p['scope_values'],p['scope_fields']),('alpha/read',['wireTag'],['north'],['space']))
        self.assertEqual([nodes[i]['name'] for i in p['handler_methods']],['SpecificWork::execute'])
        self.assertEqual(p['decoded_key_status'],'source_mapping_candidate')
        self.assertTrue(any(w['member']=='internalTag' and w['wire_fields']==['wireTag'] for w in p['decoded_key_mappings']))

    def test_all_project_symbols_and_wire_fields_can_change(self):
        import re
        source=SOURCE
        for a,b in {'ACTION':'CODE','Bundle':'Package','Workers':'Tasks','Codec':'Format','SpecificWork':'Job','execute':'run','entries':'dispatches','codec':'format','wireTag':'operation','internalTag':'stored','space':'tenant'}.items():
            source=re.sub(r'\b'+a+r'\b',b,source)
        g=self.graph(source);p,=g['protocol']['providers']
        self.assertEqual(p['command_fields'],['operation']);self.assertEqual(p['scope_fields'],['tenant'])
        self.assertTrue(any(w['member']=='stored' for w in p['decoded_key_mappings']))
        self.assertEqual(p['decoded_key_status'],'source_mapping_candidate')

    def test_deleted_registration_and_dynamic_key_do_not_make_a_known_provider(self):
        for source in [SOURCE.replace('entries.emplace(ACTION,std::make_unique<SpecificWork>());',''),SOURCE.replace('entries.emplace(ACTION,','entries.emplace(runtime(),')]:
            self.assertEqual(self.graph(source)['protocol']['providers'],[])

    def test_unknown_key_transformation_does_not_reuse_input_field(self):
        source=SOURCE.replace('j["wireTag"].GetString()','j["wireTag"].digest()')
        self.assertEqual(self.graph(source)['protocol']['providers'],[])

    def test_reassigned_key_does_not_use_stale_initializer(self):
        source=SOURCE.replace('return decoders.at(key)(j);','key=runtime();return decoders.at(key)(j);')
        self.assertEqual(self.graph(source)['protocol']['providers'],[])

    def test_duplicate_registration_keeps_both_candidates(self):
        source=SOURCE.replace('entries.emplace(ACTION,std::make_unique<SpecificWork>());','entries.emplace(ACTION,std::make_unique<SpecificWork>());entries.emplace(ACTION,std::make_unique<SpecificWork>());')
        self.assertEqual(len(self.graph(source)['protocol']['providers']),2)

    def test_uninstantiated_factory_is_reported(self):
        p,=self.graph(SOURCE.replace('auto activation=std::make_unique<Bundle>();',''))['protocol']['providers']
        self.assertEqual(p['status'],'factory_not_instantiated')

    def test_header_constant_requires_an_actual_include_context(self):
        files={'keys.h':'const std::string ACTION="alpha/read";', 'unit.h':SOURCE.replace('const std::string ACTION="alpha/read";',''), 'a.cpp':'#include "keys.h"\n#include "unit.h"'}
        p,=self.graph(files=files)['protocol']['providers'];self.assertEqual(p['command'],'alpha/read')
        files['a.cpp']='#include "unit.h"'
        self.assertEqual(self.graph(files=files)['protocol']['providers'],[])
