import unittest
from scripts.build_fact_graph import remaining_coverage


class CoverageTests(unittest.TestCase):
    def test_unparsed_files_keep_explicit_reason(self):
        records=remaining_coverage(['a.cpp','a.py','package.json','tsconfig.json'],{'a.cpp'})
        self.assertEqual(records,[{'path':'a.py','status':'unsupported_extension'},
                                  {'path':'package.json','status':'workspace_package_metadata'},
                                  {'path':'tsconfig.json','status':'configuration_recorded_not_applied'}])
