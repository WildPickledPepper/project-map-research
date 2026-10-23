"""Read public Insight fixture structure without modifying DBs or calculating hashes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import subprocess

DB = 'test/data/pytorch/db/level0/rank0_ascend_pt/ASCEND_PROFILER_OUTPUT/ascend_pytorch_profiler_0.db'
TRACE = 'test/data/pytorch/text/level0/rank0_ascend_pt/ASCEND_PROFILER_OUTPUT/trace_view.json'
DEPENDENCIES = ('libuv', 'uSockets', 'uWebSockets', 'rapidjson')


def inspect(source):
    source = Path(source).resolve()
    revision = lambda p: subprocess.check_output(['git', '-C', str(p), 'rev-parse', 'HEAD'], text=True).strip()
    db = source/DB
    with sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        counts = {name: connection.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                  for name in ('TASK', 'CANN_API', 'PYTORCH_API', 'STRING_IDS') if name in tables}
    trace = source/TRACE; document = json.loads(trace.read_text(encoding='utf-8'))
    events = document['traceEvents'] if isinstance(document, dict) else document
    return {'evidence_kind': 'executed_fixture_inventory', 'source_commit': revision(source),
            'dependencies': {name: revision(source/'server/third_party'/name) for name in DEPENDENCIES},
            'db': {'path': DB, 'bytes': db.stat().st_size, 'tables': tables, 'selected_row_counts': counts},
            'trace': {'path': TRACE, 'bytes': trace.stat().st_size, 'event_count': len(events),
                      'phase_counts': dict(Counter(e.get('ph', 'missing') for e in events))},
            'scope': 'Presence and structure; actual import, query results and state behavior are separate checks',
            'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True); ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args(); result = inspect(a.source)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'tables': len(result['db']['tables']), 'trace_events': result['trace']['event_count']}))
