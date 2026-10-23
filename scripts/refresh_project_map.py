"""Refresh a versioned project graph once, or watch Git/config changes."""
import argparse
from functools import partial
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.snapshot_refresh import Refresher, RefreshBusy
from scripts.build_project_snapshot import build, build_version


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ['source', 'config', 'store', 'typescript']: ap.add_argument('--'+key, type=Path, required=True)
    ap.add_argument('--revision', default='HEAD')
    ap.add_argument('--watch', action='store_true')
    ap.add_argument('--interval', type=float, default=2.0)
    ap.add_argument('--max-builds', type=int, default=4)
    args = ap.parse_args()
    if not 0.1 <= args.interval <= 60: ap.error('--interval must be between 0.1 and 60 seconds')
    if args.max_builds < 1: ap.error('--max-builds must be positive')
    if args.store.resolve().is_relative_to(ROOT) or ROOT.is_relative_to(args.store.resolve()):
        ap.error('Keep the store outside the research repository')
    typescript = args.typescript.resolve(); frozen_version = build_version(typescript)
    version_invalid = False

    def version():
        nonlocal version_invalid
        try:
            current = build_version(typescript)
            if current != frozen_version:
                raise ValueError('Builder changed while watcher was running; restart with the new version')
            return current
        except Exception:
            version_invalid = True
            raise

    def emit(event):
        if not (args.watch and event['event'] == 'unchanged'):
            print(json.dumps(event, ensure_ascii=False), flush=True)

    refresher = Refresher(args.source, args.store,
        lambda: json.loads(args.config.read_text(encoding='utf-8')), version,
        partial(build, typescript=typescript), revision=args.revision, on_event=emit)
    try:
        while True:
            try:
                result = refresher.run(max_builds=args.max_builds)
                if version_invalid: return 4
                if not args.watch: return 0 if result['status'] == 'up_to_date' else 2
            except RefreshBusy as error:
                emit({'event': 'busy', 'message': str(error)})
                if not args.watch: return 3
            if args.watch: time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__': raise SystemExit(main())
