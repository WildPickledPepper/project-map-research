"""Protect native endpoint identity and reject corrupted upstream records."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from adapters.svf_export import read_points,serialize_current


class SVFExportTests(unittest.TestCase):
    def test_upstream_records_preserve_empty_and_multiple_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            points=Path(directory)/'points.txt'
            points.write_text('5 1\n------\n1 -> { }\n8 -> { 9, 10 }\n')
            self.assertEqual(read_points(points),[{'source':8,'target':9},{'source':8,'target':10}])
            points.write_text('8 -> { unexpected }\n')
            with self.assertRaisesRegex(ValueError,'Malformed'):read_points(points)

    def test_same_process_file_requires_both_endpoints_in_live_pag(self):
        value=SimpleNamespace(getName=lambda:'native',__str__=lambda:'native')
        native=SimpleNamespace(getSVFG=lambda:SimpleNamespace(getNodes=lambda:[]),
                               getPAG=lambda:iter([(8,value)]),get_pta=lambda:object())
        with tempfile.TemporaryDirectory() as directory:
            points=Path(directory)/'points.txt';points.write_text('8 -> { 9 }\n')
            with self.assertRaisesRegex(ValueError,'endpoints missing'):
                serialize_current(native,points,same_process_file=True)

    def test_separate_process_capture_remains_unverified(self):
        native=SimpleNamespace(getSVFG=lambda:SimpleNamespace(getNodes=lambda:[]),
                               getPAG=lambda:iter([]),get_pta=lambda:object())
        with tempfile.TemporaryDirectory() as directory,patch('adapters.svf_export.importlib.metadata.version',return_value='test'):
            points=Path(directory)/'points.txt';points.write_text('8 -> { 9 }\n')
            data=serialize_current(native,points)
            self.assertEqual(data['points_to_identity_status'],'unverified_cross_process_ids')
            self.assertFalse(data['same_process_endpoints_checked'])


if __name__=='__main__':unittest.main()
