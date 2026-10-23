"""Capture a graph basis, append a versioned record, or query its applicability."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.snapshot_records import KINDS, append_record, query_record, query_records, snapshot_basis


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--store', type=Path, required=True)
    sub = ap.add_subparsers(dest='command', required=True)
    basis = sub.add_parser('basis'); basis.add_argument('--snapshot')
    append = sub.add_parser('append'); append.add_argument('--input', type=Path, required=True)
    query = sub.add_parser('query'); query.add_argument('--id'); query.add_argument('--snapshot')
    query.add_argument('--kind', choices=sorted(KINDS)); query.add_argument('--only-snapshot', action='store_true')
    args = ap.parse_args()
    if args.command == 'basis': result = snapshot_basis(args.store, args.snapshot)
    elif args.command == 'append':
        if args.store.resolve().is_relative_to(ROOT): raise ValueError('Keep records outside the research repository')
        result = append_record(args.store, json.loads(args.input.read_text(encoding='utf-8')))
    elif args.id:
        if args.kind or args.only_snapshot: ap.error('--id cannot be combined with list filters')
        result = query_record(args.store, args.id, snapshot_id=args.snapshot)
    else:
        result = query_records(args.store, snapshot_id=args.snapshot, kind=args.kind, include_history=not args.only_snapshot)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__': main()
