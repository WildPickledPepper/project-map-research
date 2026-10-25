import unittest
from tests import test_python_path_values as fixtures
from adapters.file_predicate_values import conditions


class PythonMappingPathTests(unittest.TestCase):
    graph=fixtures.PythonPathValueTests.graph
    values=fixtures.PythonPathValueTests.values

    def selected(self,graph,host='Windows'):
        return [v for v in self.values(graph) if conditions(v['value']['conditions'],style='posix',
            host_system={'name':host,'path_style':'windows' if host=='Windows' else 'posix'})['permitted']]

    def paths(self,graph,host='Windows'):return [v['value']['path'] for v in self.selected(graph,host)]

    def test_tuple_keys_and_host_values_select_both_sides_of_renamed_copy(self):
        g=self.graph({'pack.py':'''import os,platform,shutil
names={('Windows','from'):'origin.exe',('Windows','to'):'renamed.exe',('Darwin','from'):'native'}
system=platform.system()
src=names.get((system,'from'),'runner')
dst=names.get((system,'to'),'release')
shutil.copyfile(os.path.join('target','release',src),os.path.join('ship',dst))
'''})
        self.assertEqual(self.paths(g),['target/release/origin.exe'])
        destinations=[v for v in self.values(g,role='destination') if conditions(v['value']['conditions'],style='posix',host_system={'name':'Windows'})['permitted']]
        self.assertEqual([v['value']['path'] for v in destinations],['ship/renamed.exe'])
        self.assertEqual(self.paths(g,'Linux'),['target/release/runner'])
        self.assertTrue(any(e['kind']=='PATH_LOOKUP_SOURCE' for e in g['edges']))
        self.assertTrue(any(e['kind']=='PATH_GUARD_SOURCE' and any(n['id']==e['source'] and n['kind']=='path_value' for n in g['nodes']) for e in g['edges']))

    def test_direct_subscription_and_duplicate_equal_keys_use_last_entry(self):
        g=self.graph({'pack.py':'''import shutil
names={'worker':'old','worker':'latest',True:'boolean',1:'integer'}
shutil.copyfile(names['worker'],'ship')
shutil.copyfile(names[True],'second')
'''})
        self.assertEqual(self.paths(g),['latest','integer'])

    def test_present_none_does_not_select_get_default(self):
        g=self.graph({'pack.py':'''import shutil
names={'worker':None}
shutil.copyfile(names.get('worker','fallback'),'ship')
'''})
        selected=self.selected(g)
        self.assertEqual(len(selected),1);self.assertEqual(selected[0]['value']['resolution'],'unresolved')
        self.assertNotIn('fallback',self.paths(g))

    def test_missing_subscription_retains_lookup_error_instead_of_inventing_path(self):
        g=self.graph({'pack.py':"import shutil\nnames={'one':'first'}\nshutil.copyfile(names['absent'],'ship')\n"})
        self.assertEqual(len(self.selected(g)),1)
        self.assertEqual(self.selected(g)[0]['value']['unresolved'][0]['reason'],'python_dictionary_subscription_missing_key')

    def test_empty_mapping_uses_default_and_list_key_is_not_a_tuple(self):
        g=self.graph({'pack.py':"import shutil\nnames={}\nshutil.copyfile(names.get('missing','fallback'),'ship')\n"})
        self.assertEqual(self.paths(g),['fallback'])
        g=self.graph({'pack.py':"import shutil\nnames={('a','b'):'worker'}\nshutil.copyfile(names.get(['a','b'],'fallback'),'ship')\n"})
        self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))

    def test_alias_mutations_and_unknown_escape_invalidate_literal_selection(self):
        for effect in ("alias=names\nalias['Windows']='other'", "names.update({'Windows':'other'})",'unknown(names)',
                       'def mutate(value): value.clear()\nmutate(names)'):
            with self.subTest(effect=effect):
                g=self.graph({'pack.py':"import shutil\nnames={'Windows':'worker'}\n"+effect+"\nshutil.copyfile(names.get('Windows','fallback'),'ship')\n"})
                self.assertTrue(self.values(g));self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))
                self.assertTrue(any('mutation_or_escape' in r['reason'] for v in self.values(g) for r in v['value']['unresolved']))

    def test_class_constants_import_aliases_and_readonly_source_parameter(self):
        g=self.graph({'config.py':'''class Layout:
 WIN='Windows'
 NAMES={WIN:'first', 'Linux':'second'}
''','pack.py':'''import shutil,platform
from config import Layout as Names
def choose(table): return table.get(platform.system(),'default')
shutil.copyfile(choose(Names.NAMES),'ship')
'''})
        self.assertEqual(self.paths(g),['first']);self.assertEqual(self.paths(g,'Linux'),['second'])

    def test_custom_get_method_is_not_expanded_as_builtin_dictionary(self):
        g=self.graph({'pack.py':'''import shutil
class Other:
 def get(self,*args): return 'arbitrary'
source=Other()
shutil.copyfile(source.get('key','fallback'),'ship')
'''})
        self.assertFalse(any(c['kind']=='mapping_entry_selected' for v in self.values(g) for c in v['value']['conditions']))

    def test_unpack_and_entry_budget_have_located_gaps(self):
        for initializer in ("{'one':'worker',**external}",repr({str(i):str(i) for i in range(33)})):
            with self.subTest(initializer=initializer):
                g=self.graph({'pack.py':'import shutil\nnames='+initializer+"\nshutil.copyfile(names.get('one','fallback'),'ship')\n"})
                self.assertTrue(all(v['value']['resolution']=='unresolved' for v in self.values(g)))


if __name__=='__main__':unittest.main()
