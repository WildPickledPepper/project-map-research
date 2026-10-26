"""A successful process must not publish stale or unverified native output."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.analyze_svf_captures import analyze


class SVFCaptureAnalysisTests(unittest.TestCase):
    def test_unverified_or_wrong_context_output_does_not_publish_success(self):
        for changes in ({'context':'different/config'},{'same_process_endpoints_checked':False}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                receipt={'schema':'cargo-svf-capture/1','bitcode':'program.bc','source_commit':'a'*40,
                         'context':'test/config','module':'neutral','language':'rust',
                         'source_root':'/fixture','source_directory':'src'}
                (root/'receipt.json').write_text(json.dumps(receipt))
                data={**receipt,'points_to_identity_status':'same_process_native_ids',
                      'same_process_endpoints_checked':True,**changes}
                (root/'native.json').write_text(json.dumps(data))
                with patch('scripts.analyze_svf_captures.subprocess.run') as call:
                    with self.assertRaises(ValueError):analyze(root/'receipt.json')
                    self.assertEqual(call.call_count,1)
                self.assertFalse((root/'analysis-receipt.json').exists())


if __name__=='__main__':unittest.main()
