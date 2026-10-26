"""Exercise actual compiler references in non-self-contained headers and variants."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from adapters.libclang_provider import analyze, select_units


@unittest.skipUnless(importlib.util.find_spec('clang') and (os.environ.get('CXX') or shutil.which('g++')),
                     'optional libclang and configured C++ compiler required')
class LibclangProviderTests(unittest.TestCase):
    def test_native_header_targets_and_configuration_identity_survive_renamed_layout(self):
        compiler = os.environ.get('CXX') or shutil.which('g++')
        all_facts = []
        with tempfile.TemporaryDirectory() as temporary:
            for ordinal, folder in enumerate(('first/core','different/renamed')):
                root = Path(temporary)/str(ordinal); (root/folder).mkdir(parents=True)
                prefix = folder+'/prerequisite.hpp'; header = folder+'/logic.hpp'; source = folder+'/entry.cpp'
                (root/prefix).write_text('struct Parent {};\ninline int select_a(int n){return n;}\ninline int select_b(int n){return n+1;}\n')
                (root/header).write_text('struct Child: Parent {\nint run(int n) {\n#if FEATURE\nreturn select_a(n);\n#else\nreturn select_b(n);\n#endif\n}\n};\n')
                (root/source).write_text('#include "prerequisite.hpp"\n#include "logic.hpp"\n')
                row = {'file':str(root/source),'directory':str(root),
                       'arguments':[compiler,'-std=c++17','-DFEATURE='+str(ordinal),'-c',str(root/source)]}
                db = root/'compile_commands.json'; db.write_text(json.dumps([row]))
                facts = analyze(root,[prefix,header,source],compile_commands=db,required_headers=[header],
                    context='mode-'+str(ordinal),source_commit='c'*40,output=root/'out',query_drivers=[compiler],
                    builtin_headers=os.environ.get('PROJECT_MAP_CLANG_BUILTIN_HEADERS'),
                    import_pairs=[(source,header),(source,prefix)])
                self.assertEqual(facts['coverage'][0]['status'],'parsed')
                refs = {n['id']:n for n in facts['nodes']}
                targets = [refs[e['target']]['name'] for e in facts['edges'] if e['kind']=='CLANG_TU_REFERS_TO_DECLARATION']
                self.assertIn('select_a(int)' if ordinal else 'select_b(int)',targets)
                self.assertNotIn('select_b(int)' if ordinal else 'select_a(int)',targets)
                self.assertTrue(any(e['kind']=='CLANG_TU_CONTAINS_REFERENCE' for e in facts['edges']))
                self.assertTrue(all(n['path'] in {prefix,header,source} for n in facts['nodes']))
                all_facts.append(facts)
            self.assertFalse({n['id'] for n in all_facts[0]['nodes']} & {n['id'] for n in all_facts[1]['nodes']})

    def test_candidate_imports_only_prioritize_native_units(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [{'file':str(root/p),'directory':str(root),'arguments':['g++','-c',p]}
                    for p in ('a.cpp','z.cpp')]
            chosen = select_units(rows,root,{'hidden.hpp'},[('z.cpp','middle.hpp'),('middle.hpp','hidden.hpp')])
            self.assertEqual([r[0] for r in chosen],['z.cpp','a.cpp'])

    def test_native_library_targets_remain_queryable_without_importing_external_sources(self):
        compiler=os.environ.get('CXX') or shutil.which('g++')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'library.hpp').write_text('int outside(int);\n')
            (root/'fragment.hpp').write_text('inline int apply(int n){return outside(n);}\n')
            (root/'main.cpp').write_text('#include "library.hpp"\n#include "fragment.hpp"\n')
            row={'file':str(root/'main.cpp'),'directory':str(root),
                 'arguments':[compiler,'-std=c++17','-c',str(root/'main.cpp')]}
            (root/'compile_commands.json').write_text(json.dumps([row]))
            facts=analyze(root,['main.cpp','fragment.hpp'],compile_commands=root,
                required_headers=['fragment.hpp'],context='external-test',source_commit='c'*40,
                output=root/'out',query_drivers=[compiler],
                builtin_headers=os.environ.get('PROJECT_MAP_CLANG_BUILTIN_HEADERS'))
            nodes={n['id']:n for n in facts['nodes']}
            external=[n for n in nodes.values() if n.get('external_declaration')]
            self.assertEqual([n['name'] for n in external],['outside(int)'])
            self.assertEqual(external[0]['path'],'')
            self.assertTrue(any(e['target']==external[0]['id'] for e in facts['edges']))
            self.assertTrue(any(n.get('resolution')=='native_external_declaration_target' for n in nodes.values()))


if __name__=='__main__': unittest.main()
