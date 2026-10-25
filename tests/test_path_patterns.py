import unittest
from adapters.path_values import literal,normalize,operation,symbol
from adapters.path_patterns import match,instantiate


class PathPatternTests(unittest.TestCase):
    def value(self,t):return normalize(t,'posix')[0]
    def entry(self,name,directory):
        return {'op':'entry_name','source':name,'variable':name,'iteration':'loop-'+name,'name':name,'args':[directory]}

    def test_nested_directory_domains_bind_only_corresponding_full_paths(self):
        root=literal('native');variant=self.entry('variant',root)
        folder=operation('join',operation('join',root,variant),literal('bin'));name=self.entry('file',folder)
        pattern=self.value(operation('join',folder,name));actual=self.value(literal('native/target-x/bin/renamed.exe'))
        self.assertEqual(pattern['resolution'],'pattern');self.assertIsNone(pattern['relative_path'])
        result=match(pattern,actual)
        self.assertEqual(result['bindings'],{'variant':'target-x','file':'renamed.exe'})
        destination=self.value(operation('join',literal('package/engine'),name))
        self.assertEqual(instantiate(destination,result['bindings'])['path'],'package/engine/renamed.exe')
        self.assertIsNone(match(pattern,self.value(literal('unrelated/target-x/bin/renamed.exe'))))

    def test_wrong_directory_domain_and_repeated_variable_do_not_match(self):
        entry=self.entry('name',literal('other'))
        pattern=self.value(operation('join',literal('native'),entry))
        self.assertIsNone(match(pattern,self.value(literal('native/worker'))))
        same=self.entry('name',literal('native'))
        repeated=self.value(operation('join',operation('join',literal('native'),same),same))
        self.assertIsNone(match(repeated,self.value(literal('native/a/b'))))
        self.assertIsNotNone(match(repeated,self.value(literal('native/a/a'))))
        conditional=match(pattern,self.value(literal('native/worker')),allow_unverified_membership=True)
        self.assertEqual(conditional['membership_conditions'][0]['basis'],'requires_directory_enumeration_evidence')

    def test_copy_tree_prefix_preserves_descendant_path_and_distinct_roots(self):
        source=self.value(literal('native/tree'));actual=self.value(literal('native/tree/lib/sub/worker'))
        result=match(source,actual,prefix=True)
        self.assertEqual(instantiate(self.value(literal('ship/runtime')),result['bindings'],suffix=result['suffix'])['path'],'ship/runtime/lib/sub/worker')
        self.assertIsNone(match(source,self.value(literal('native/tree-other/worker')),prefix=True))
        other={**source,'base':{'kind':'build_root','source':'context-two'}}
        self.assertIsNone(match(other,actual,prefix=True))

    def test_missing_destination_binding_and_unresolved_source_are_not_filled_in(self):
        entry=self.entry('unknown',literal('native'));value=self.value(operation('join',literal('ship'),entry))
        self.assertIsNone(instantiate(value,{}))
        self.assertIsNone(match({**value,'unresolved':[{'reason':'unknown'}]},self.value(literal('ship/worker'))))

    def test_extension_on_unknown_filename_is_an_explicit_gap(self):
        term=operation('set_extension',operation('join',literal('native'),self.entry('name',literal('native'))),literal('exe'))
        self.assertEqual(self.value(term)['resolution'],'unresolved')

    def test_source_roots_bind_but_unrelated_symbolic_roots_stay_separate(self):
        source=self.value(operation('join',{'op':'source_file','source':'left','path':'a.py'},literal('data')))
        actual={**source,'base':{'kind':'canonical_source_root','source':'right'}}
        self.assertIsNotNone(match(source,actual))
        self.assertIsNone(match(self.value(symbol('unrelated-root')),actual,prefix=True))


if __name__=='__main__':unittest.main()
