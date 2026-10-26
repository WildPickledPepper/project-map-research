"""Verify native identity, context and source isolation at the interchange boundary."""
import json
from pathlib import Path
import tempfile
import unittest

from adapters.native_provider_graph import configuration,read_capture
from adapters.native_value_flow import normalize
from scripts.collect_native_value_flow import collect


class NativeValueFlowTests(unittest.TestCase):
    def native(self,**changes):
        return {'schema':'svf-native-export/1','source_commit':'a'*40,'context':'linux/release',
            'source_root':'/native/root','module':'one','package_version':'1.0.0.50',
            'points_to_identity_status':'same_process_native_ids',
            'nodes':[{'id':1,'kind':'FormalParmVFGNode','text':'native value','function':'f',
                      'source_location':{'fl':'/native/root/lib/a.cpp','ln':4,'cl':2},
                      'function_location':{'fl':'/native/root/lib/a.cpp','ln':3},'value':2}],
            'variables':[{'id':2,'kind':'ValVar','name':'argument','text':'native variable'},
                         {'id':3,'kind':'ObjVar','name':'object','text':'native object'}],
            'edges':[],'points_to':[{'source':2,'target':3}],**changes}

    def normalize(self,data):
        return normalize(data,provider='svf',paths=['lib/a.cpp'],source_commit='a'*40,context='linux/release')

    def test_revision_context_and_path_guards(self):
        for key,value in [('source_commit','b'*40),('context','windows/debug'),('schema','rapx-native-export/1')]:
            with self.assertRaises(ValueError):self.normalize(self.native(**{key:value}))
        with self.assertRaises(ValueError):
            normalize(self.native(),provider='svf',paths=['../escaped.cpp'],source_commit='a'*40,context='linux/release')
        raw=self.native();raw['nodes'][0]['source_location']={'fl':'/other/project/lib/a.cpp','ln':9}
        raw['nodes'][0]['function_location']=None
        facts=self.normalize(raw)
        self.assertFalse(any(n['path'] for n in facts['nodes']))
        self.assertEqual(facts['diagnostics'][0]['project_and_boundary_value_nodes'],0)

    def test_project_projection_preserves_native_boundary_ports_and_reports_omitted_bodies(self):
        raw=self.native();first=raw['nodes'][0]
        for uid in (4,5):
            raw['nodes'].append({**first,'id':uid,'source_location':None,'function_location':None,'value':None})
        raw['edges']=[{'source':1,'target':4},{'source':4,'target':5}]
        facts=self.normalize(raw);ids={n['native_id'] for n in facts['nodes'] if n['kind']=='value'}
        self.assertEqual(ids,{1,4})
        self.assertEqual(sum(e['kind']=='SVF_VALUE_FLOW' for e in facts['edges']),1)
        self.assertTrue(next(n for n in facts['nodes'] if n.get('native_id')==4)['external_boundary_value'])
        self.assertEqual(facts['diagnostics'][0]['native_counts']['nodes'],3)

    def test_cross_process_points_ids_are_not_assumed_equal(self):
        facts=self.normalize(self.native(points_to_identity_status='unverified_cross_process_ids'))
        self.assertFalse(any(e['kind']=='SVF_POINTS_TO' for e in facts['edges']))
        self.assertTrue(any(d['kind']=='native_points_to_identity_not_verified' for d in facts['diagnostics']))

    def test_native_module_identity_and_candidate_precision_survive_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inputs=[]
            for i,module in enumerate(('one','renamed/other')):
                filename=root/f'{i}.json';filename.write_text(json.dumps(self.native(module=module)));inputs.append(filename)
            result=collect(inputs,paths=['lib/a.cpp'],source_commit='a'*40,output=root/'capture')
            capture=result['captures'][0];capture['directory']=str((root/'capture'/capture['directory']).resolve())
            configuration({'captures':[capture]})
            facts=read_capture(capture,paths=['lib/a.cpp'],source_commit='a'*40)
            values=[n for n in facts['nodes'] if n['kind']=='value']
            self.assertEqual(len({n['id'] for n in values}),2)
            self.assertTrue(all(e['status']=='candidate' for e in facts['edges']))
            self.assertTrue(all(e['runtime_execution']=='not_observed' for e in facts['edges']))
            self.assertEqual(sum(e['kind']=='SVF_POINTS_TO' for e in facts['edges']),2)
            with self.assertRaisesRegex(ValueError,'Duplicate native module'):
                collect([inputs[0],inputs[0]],paths=['lib/a.cpp'],source_commit='a'*40,output=root/'duplicate')


if __name__=='__main__':unittest.main()
