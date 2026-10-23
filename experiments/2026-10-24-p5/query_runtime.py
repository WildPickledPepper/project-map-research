"""Query a captured run against an explicit graph and execution context."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runtime_records import query_runtime


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--store', type=Path, required=True)
    ap.add_argument('--id', required=True)
    ap.add_argument('--snapshot', required=True)
    ap.add_argument('--context', type=Path, required=True)
    args = ap.parse_args()
    context = json.loads(args.context.read_text(encoding='utf-8'))
    print(json.dumps(query_runtime(args.store, args.id, snapshot_id=args.snapshot, context=context), ensure_ascii=False))
