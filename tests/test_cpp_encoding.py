"""Encoding output lineage, aliases and mutations, using source wrappers."""
import unittest

from adapters.cpp_data import DataExtractor
from adapters.cpp_transmission import Transmission
from tests.test_cpp_transmission import PRELUDE
import tests.test_cpp_data as data_tests

WRAPPER = '''
#include <windows.h>
std::string transcode(const char* incoming){
int n=MultiByteToWideChar(936,0,incoming,-1,nullptr,0);
auto wide=std::make_unique<wchar_t[]>(n+1);
MultiByteToWideChar(936,0,incoming,-1,wide.get(),n);
n=WideCharToMultiByte(CP_UTF8,0,wide.get(),-1,nullptr,0,nullptr,nullptr);
auto output=std::make_unique<char[]>(n+1);
WideCharToMultiByte(CP_UTF8,0,wide.get(),-1,output.get(),n,nullptr,nullptr);
REPLACE
return std::string(output.get());}
'''


class EncodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): data_tests.CppDataTests.setUpClass(); cls.parser = data_tests.CppDataTests.parser

    def analyze(self, wrapper=WRAPPER, extra=''):
        code = PRELUDE + wrapper.replace('REPLACE', extra) + '''
void run(uWS::WebSocket<false,true,int>* socket){auto document=encode(2);
auto bytes=dump(document);auto converted=transcode(bytes.c_str());socket->send(converted);}
'''
        d = DataExtractor({'a.cpp': code.encode()}, self.parser); flow = Transmission(d).build()
        uid = next(i for i, f in d.x.functions_by_id.items() if f['signature'][0] == 'run')
        return [t for s in flow['transmissions'] if s['entry'] == uid for t in s['traces']]

    def test_output_buffers_connect_both_conversions(self):
        trace, = self.analyze()
        self.assertEqual([s['model'] for s in trace['steps'] if s['kind'] == 'win32_encoding_output'],
                         ['MultiByteToWideChar', 'WideCharToMultiByte'])
        self.assertEqual(len([c for c in trace['conditions'] if c['kind'] == 'library_precondition']), 2)

    def test_source_names_are_not_model_names(self):
        wrapper = WRAPPER.replace('incoming', 'text_input').replace('wide', 'intermediate').replace('output', 'bytes_out')
        self.assertEqual(len(self.analyze(wrapper)), 1)

    def test_sizing_only_does_not_produce_output(self):
        self.assertFalse(self.analyze(WRAPPER.replace('output.get(),n,', 'output.get(),0,')))

    def test_unrelated_output_buffer_is_not_joined(self):
        self.assertFalse(self.analyze(extra='output=std::make_unique<char[]>(10);'))

    def test_unknown_buffer_mutation_clears_lineage(self):
        self.assertFalse(self.analyze(extra='change(output.get());'))
        self.assertFalse(self.analyze(extra='auto alias=output.get();change(alias);'))
        self.assertFalse(self.analyze(extra='output.get()[0]=0;'))

    def test_sdk_model_requires_header_and_no_source_shadow(self):
        self.assertFalse(self.analyze(WRAPPER.replace('#include <windows.h>', '')))
        shadow = 'int MultiByteToWideChar(int,int,const char*,int,wchar_t*,int);\n'
        self.assertFalse(self.analyze(shadow + WRAPPER))


if __name__ == '__main__': unittest.main()
