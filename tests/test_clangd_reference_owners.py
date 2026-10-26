import unittest

from adapters.clangd_provider import diagnostic_precision


def bounds(start, end):
    return {'start': {'line': 0, 'character': start}, 'end': {'line': 0, 'character': end}}


class NativeReferenceOwnerTests(unittest.TestCase):
    def graph(self):
        nodes=[{'id': uid, 'kind': kind, 'name': uid, 'path': path, 'line': 1, 'column': start+1,
                'native_range': bounds(start,end), 'provenance': {'context': context}}
            for uid,kind,path,start,end,context in [
                ('outer','callable','a.cpp',0,100,'release'),
                ('inner','callable','a.cpp',20,40,'release'),
                ('neighbor','callable','a.cpp',100,140,'release'),
                ('other-file','callable','b.cpp',20,40,'release'),
                ('other-context','callable','a.cpp',20,40,'debug'),
                ('nested','symbol_reference','a.cpp',25,30,'release'),
                ('plain','symbol_reference','a.cpp',50,55,'release'),
                ('outside','symbol_reference','a.cpp',150,155,'release')]]
        return {'nodes':nodes,'edges':[],'coverage':[{'path':'a.cpp','status':'parsed'}],
                'components':{'context':'release'}}

    def test_innermost_native_range_keeps_file_context_and_sibling_isolation(self):
        facts=self.graph();diagnostic_precision(facts)
        self.assertEqual({(e['source'],e['target']) for e in facts['edges']},
                         {('inner','nested'),('outer','plain')})
        self.assertEqual(next(n for n in facts['nodes'] if n['id']=='outside')['native_owner_status'],
                         'outside_callable_range')
        self.assertTrue(all('CALLS' not in e['kind'] for e in facts['edges']))
        diagnostic_precision(facts)
        self.assertEqual(len(facts['edges']),2)

    def test_identical_range_ambiguity_and_diagnostics_preserve_uncertainty(self):
        facts=self.graph()
        facts['nodes'].append({**facts['nodes'][1],'id':'same-range'})
        facts['coverage'][0]['status']='parsed_with_diagnostics'
        diagnostic_precision(facts)
        self.assertEqual([(e['source'],e['target']) for e in facts['edges']],[('outer','plain')])
        self.assertEqual(facts['edges'][0]['status'],'candidate')
        self.assertEqual(next(n for n in facts['nodes'] if n['id']=='nested')['native_owner_status'],'ambiguous')
