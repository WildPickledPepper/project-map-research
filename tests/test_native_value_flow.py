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
        self.assertEqual(self.normalize(raw)['nodes'][0]['path'],'')

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
