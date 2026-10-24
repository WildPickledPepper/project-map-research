import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class WorkbenchTests(unittest.TestCase):
    def test_query_flags_unicode_and_usage_logging(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);shutil.copyfile(root/'experiments/2026-10-24-p7/workbench.py',p/'workbench.py')
            q=p/'experiments/2026-10-24-p7/query.py';q.parent.mkdir(parents=True)
            q.write_text('import json,sys\nprint(json.dumps({"text":"曲线状态","args":sys.argv[1:]},ensure_ascii=False))\n',encoding='utf-8')
            def run(*args):return subprocess.run([sys.executable,'-X','utf8',str(p/'workbench.py'),*args],cwd=p,capture_output=True,text=True,encoding='utf-8',check=True)
            run('begin','T01');result=run('--select','text','query','--limit','1','overview');run('end','T01')
            self.assertEqual(json.loads(result.stdout),'曲线状态')
            logs=[json.loads(s) for s in (p/'output/usage.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([l['action'] for l in logs],['begin','query','end'])
            self.assertEqual(logs[1]['arguments']['args'],['--limit','1','overview'])
            self.assertGreater(logs[1]['result_bytes'],0);self.assertEqual(logs[-1]['tokens'],'not_exposed')
