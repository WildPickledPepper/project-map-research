import json
from pathlib import Path
import tempfile
import unittest

from adapters.python_facts import analyze


class PythonFactsTests(unittest.TestCase):
    def graph(self,files):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,body in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')
            result=analyze(root,list(files))
            self.assertFalse((root/'EXECUTED').exists())
            json.dumps(result,allow_nan=False)
            return result

    def pairs(self,g,kind):
        nodes={n['id']:n for n in g['nodes']}
        return [(nodes[e['source']],nodes[e['target']],e) for e in g['edges'] if e['kind']==kind]

    def test_relative_reexport_alias_and_same_name_decoy(self):
        g=self.graph({'pkg/__init__.py':'from .unit import run as alias\n','pkg/unit.py':'def run(): return 1\n',
            'client.py':'from pkg import alias\ndef entry(): return alias()\n','other.py':'def run(): return 2\n'})
        calls=self.pairs(g,'STATIC_CALL_TARGET')
        self.assertEqual([(a['name'],b['path'],b['name']) for a,b,e in calls],[('alias','pkg/unit.py','run')])
        self.assertTrue(any(b['path']=='pkg/unit.py' for a,b,e in self.pairs(g,'IMPORTS_MODULE')))

    def test_instance_inheritance_and_bound_method_parameters(self):
        g=self.graph({'base.py':'class Base:\n def run(self, value, *, mode=0): return value\n',
            'child.py':'from base import Base\nclass Child(Base): pass\n',
            'entry.py':'from child import Child\nobj=Child()\ndef start(): return obj.run(3, mode=2)\n'})
        self.assertTrue(any(a['name']=='obj.run' and b['name']=='Base.run' for a,b,e in self.pairs(g,'STATIC_CALL_TARGET')))
        bound=self.pairs(g,'BINDS_ARGUMENT')
        self.assertEqual({b['name'] for a,b,e in bound},{'value','mode'})
        self.assertTrue(self.pairs(g,'INHERITS'))

    def test_union_keeps_both_candidates(self):
        g=self.graph({'entry.py':'def left(): return 1\ndef right(): return 2\ndef start(flag):\n target=left if flag else right\n return target()\n'})
        self.assertEqual({b['name'] for a,b,e in self.pairs(g,'STATIC_CALL_CANDIDATE')},{'left','right'})
        self.assertFalse(self.pairs(g,'STATIC_CALL_TARGET'))

    def test_shadowed_parameter_does_not_connect_global_function(self):
        g=self.graph({'entry.py':'def work(): return 1\ndef start(work): return work()\n'})
        self.assertFalse(self.pairs(g,'STATIC_CALL_TARGET'))
        call=next(n for n in g['nodes'] if n['kind']=='call_site')
        self.assertEqual(call['resolution'],'unresolved');self.assertTrue(call['reason'])

    def test_identical_calls_on_same_line_have_distinct_positions(self):
        g=self.graph({'entry.py':'def run(): return 1\ndef start(): return run()+run()\n'})
        calls=[n for n in g['nodes'] if n['kind']=='call_site']
        self.assertEqual(len(calls),2);self.assertNotEqual(calls[0]['id'],calls[1]['id'])
        self.assertNotEqual(calls[0]['column'],calls[1]['column'])

    def test_async_call_callback_and_decorator_sources(self):
        g=self.graph({'entry.py':'def decorate(fn): return fn\nasync def action(): return 1\ndef register(callback): pass\n@decorate\nasync def start():\n register(action)\n return await action()\n'})
        self.assertTrue(any(b['name']=='action' for a,b,e in self.pairs(g,'PASSES_CALLBACK')))
        self.assertTrue(any(a['name']=='start' and b['name']=='action' for a,b,e in self.pairs(g,'AWAITS')))
        self.assertTrue(self.pairs(g,'USES_DECORATOR'))
        self.assertTrue(all(e['runtime_execution']=='not_observed' for e in g['edges']))

    def test_import_analysis_does_not_execute_source(self):
        g=self.graph({'unit.py':"from pathlib import Path\nPath(__file__).with_name('EXECUTED').write_text('bad')\nraise RuntimeError('do not execute')\ndef run(): return 1\n",
            'entry.py':'from unit import run\ndef start(): return run()\n'})
        self.assertTrue(any(b['path']=='unit.py' and b['name']=='run' for a,b,e in self.pairs(g,'STATIC_CALL_TARGET')))

    def test_identical_package_names_in_independent_directories(self):
        g=self.graph({'one/lib/__init__.py':'def run(): return 1\n','one/start.py':'from lib import run\nrun()\n',
            'two/lib/__init__.py':'def run(): return 2\n','two/start.py':'from lib import run\nrun()\n'})
        calls=self.pairs(g,'STATIC_CALL_TARGET')
        self.assertEqual({(a['path'],b['path']) for a,b,e in calls},{('one/start.py','one/lib/__init__.py'),('two/start.py','two/lib/__init__.py')})

    def test_non_ascii_prefix_uses_character_columns(self):
        g=self.graph({'entry.py':'def run(): return 1\ndef start():\n label="汉字"; return run()\n'})
        self.assertEqual(len(self.pairs(g,'STATIC_CALL_TARGET')),1)

    def test_syntax_error_is_file_specific_and_other_file_survives(self):
        g=self.graph({'broken.py':'def run(:\n','good.py':'def run(): return 1\nrun()\n'})
        self.assertEqual({r['path']:r['status'] for r in g['coverage']},{'broken.py':'syntax_errors','good.py':'parsed'})
        self.assertTrue(any(d['kind']=='python_parse_error' for d in g['diagnostics']))
        self.assertEqual(len(self.pairs(g,'STATIC_CALL_TARGET')),1)

    def test_values_defaults_and_conditional_write_origins(self):
        g=self.graph({'entry.py':"ROOT='base'\ndef launch(port=8000):\n command=[ROOT, '--port', port]\n if port:\n  chosen=command\n return command\n"})
        self.assertTrue(self.pairs(g,'DEFAULT_VALUE'));self.assertTrue(self.pairs(g,'RETURNS_VALUE'))
        writes=self.pairs(g,'VALUE_SOURCE')
        self.assertTrue(any(a['name']=='command' and b['expression_kind']=='List' for a,b,e in writes))
        self.assertTrue(any(e.get('conditions') for a,b,e in writes if a['name']=='chosen'))
        self.assertTrue(any(b['kind']=='parameter' and b['name']=='port' for a,b,e in self.pairs(g,'READS_BINDING')))

    def test_spread_argument_mapping_is_explicitly_unexpanded(self):
        g=self.graph({'entry.py':'def run(a,b): pass\ndef start(values): return run(*values)\n'})
        call=next(n for n in g['nodes'] if n['kind']=='call_site')
        self.assertEqual(call['argument_binding_status'],'spread_requires_value_expansion')
        self.assertFalse(self.pairs(g,'BINDS_ARGUMENT'))

    def test_unparsed_input_target_is_not_reported_as_external_library(self):
        g=self.graph({'broken.py':'def run(): return 1\ndef broken(:\n',
            'start.py':'from broken import run\nrun()\n'})
        self.assertFalse(self.pairs(g,'STATIC_CALL_TARGET'))
        call=next(n for n in g['nodes'] if n['kind']=='call_site')
        self.assertEqual(call['reason'],'input_declaration_not_indexed_or_parse_error')

    def test_new_renamed_and_deleted_provider_recompute(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'start.py').write_text('from unit import run\nrun()\n',encoding='utf-8')
            before=analyze(root,['start.py']);self.assertFalse(self.pairs(before,'STATIC_CALL_TARGET'))
            (root/'unit.py').write_text('def run(): return 1\n',encoding='utf-8')
            added=analyze(root,['start.py','unit.py']);self.assertEqual(len(self.pairs(added,'STATIC_CALL_TARGET')),1)
            (root/'unit.py').rename(root/'moved.py');(root/'start.py').write_text('from moved import run\nrun()\n',encoding='utf-8')
            renamed=analyze(root,['start.py','moved.py']);self.assertEqual(self.pairs(renamed,'STATIC_CALL_TARGET')[0][1]['path'],'moved.py')
            (root/'moved.py').unlink();deleted=analyze(root,['start.py']);self.assertFalse(self.pairs(deleted,'STATIC_CALL_TARGET'))
            self.assertFalse(any(n['path']=='moved.py' for n in deleted['nodes']))

    def test_namespace_module_uses_importing_entry_context(self):
        g=self.graph({'service/start.py':'from tools.helper import execute\nif __name__ == "__main__": execute()\n',
            'service/tools/helper.py':'import common\ndef execute(): return common.work()\n',
            'service/common.py':'def work(): return 1\n',
            'service/tools/common.py':'def work(): return 99\n'})
        calls=[(a,b,e) for a,b,e in self.pairs(g,'STATIC_CALL_TARGET') if a['path']=='service/tools/helper.py']
        self.assertEqual({b['path'] for a,b,e in calls},{'service/common.py'})

    def test_two_entry_contexts_keep_both_module_targets_as_candidates(self):
        g=self.graph({'one/start.py':'from shared.helper import execute\nif __name__ == "__main__": execute()\n',
            'two/start.py':'from shared.helper import execute\nif __name__ == "__main__": execute()\n',
            'shared/helper.py':'import common\ndef execute(): return common.work()\n',
            'one/common.py':'def work(): return 1\n','two/common.py':'def work(): return 2\n'})
        candidates=[(a,b,e) for a,b,e in self.pairs(g,'STATIC_CALL_CANDIDATE') if a['path']=='shared/helper.py']
        self.assertEqual({b['path'] for a,b,e in candidates},{'one/common.py','two/common.py'})
        self.assertFalse([(a,b,e) for a,b,e in self.pairs(g,'STATIC_CALL_TARGET') if a['path']=='shared/helper.py'])

    def test_unresolved_entry_context_prevents_unique_target_claim(self):
        g=self.graph({'one/start.py':'from shared.helper import execute\nif __name__ == "__main__": execute()\n',
            'two/start.py':'from shared.helper import execute\nif __name__ == "__main__": execute()\n',
            'shared/helper.py':'import common\ndef execute(): return common.work()\n',
            'one/common.py':'def work(): return 1\n'})
        candidates=[(a,b,e) for a,b,e in self.pairs(g,'STATIC_CALL_CANDIDATE') if a['path']=='shared/helper.py']
        self.assertEqual({b['path'] for a,b,e in candidates},{'one/common.py'})
        call=next(n for n in g['nodes'] if n['kind']=='call_site' and n['path']=='shared/helper.py')
        self.assertEqual(call['reason'],'analysis_contexts_require_selection')


if __name__=='__main__':unittest.main()
