"""Build or query the expandable project map (JSON, no server required)."""
import argparse
import json
from pathlib import Path
import sys
import sqlite3
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.project_map import Budget, ProjectMap, build_index, encoded
from adapters.repository_discovery import discover
from adapters.snapshot_inputs import git


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--graph', type=Path, required=True)
    build.add_argument('--source', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    query = sub.add_parser('query')
    query.add_argument('--index', type=Path, required=True)
    query.add_argument('view', choices=['overview', 'links', 'files', 'search', 'entries', 'status', 'neighbors',
        'trace', 'impact', 'path', 'detail', 'diagnostics', 'source', 'providers'])
    for name in ('text', 'kind', 'module', 'name', 'start', 'target', 'path', 'entity', 'id', 'snapshot', 'cursor'):
        query.add_argument('--' + name)
    query.add_argument('--pointer', default='')
    query.add_argument('--source', type=Path)
    query.add_argument('--direction', choices=['out', 'in'], default='out')
    query.add_argument('--kinds', help='Comma-separated exact edge kinds; default all indexed kinds')
    query.add_argument('--depth', type=int, default=4)
    query.add_argument('--limit', type=int, default=30)
    query.add_argument('--seconds', type=float, default=3)
    query.add_argument('--nodes', type=int, default=200)
    query.add_argument('--edges', type=int, default=500)
    query.add_argument('--output-bytes', type=int, default=131072)
    query.add_argument('--line', type=int)
    query.add_argument('--context', type=int, default=8)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            root = Path(__file__).resolve().parents[1]
            owned = ('adapters/project_map.py', 'scripts/project_map.py')
            if git(root, 'status', '--porcelain', '--', *owned).strip():
                raise ValueError('Commit navigation code before a versioned index build')
            rules = git(root, 'log', '-1', '--format=%H', '--', *owned).decode().strip()
            graph = json.loads(args.graph.read_text(encoding='utf-8'))
            result = build_index(graph, discover(args.source, graph['source_commit']), args.output,
                navigation_version={'schema': 'project-map/1', 'rules_commit': rules})
        else:
            if args.view == 'path' and not args.target:
                raise ValueError('Path queries require --target')
            q = ProjectMap(args.index, budget=Budget(args.seconds, args.nodes, args.edges, args.output_bytes),
                expected_snapshot=args.snapshot)
            page = {'limit': args.limit, 'cursor': args.cursor}
            kinds = args.kinds.split(',') if args.kinds else None
            try:
                if args.view == 'overview': result = q.overview(**page)
                elif args.view == 'links': result = q.links(args.module, **page)
                elif args.view == 'files': result = q.files(args.module, **page)
                elif args.view == 'search': result = q.search(args.text or '', args.kind, args.module, **page)
                elif args.view == 'entries': result = q.entries(args.name, **page)
                elif args.view == 'providers': result = q.providers(args.text or '', **page)
                elif args.view == 'status': result = q.status(args.start)
                elif args.view == 'neighbors': result = q.neighbors(args.start, args.direction, kinds, **page)
                elif args.view in {'trace', 'impact', 'path'}:
                    result = q.walk(args.start, direction='in' if args.view == 'impact' else args.direction,
                        depth=args.depth, target=args.target, kinds=kinds)
                elif args.view == 'detail': result = q.detail(args.entity, args.id, args.pointer, **page)
                elif args.view == 'diagnostics': result = q.diagnostics(args.path, **page)
                elif args.view == 'source': result = q.source(args.source, selector=args.start,
                    path=args.path, line=args.line, context=args.context)
            finally:
                q.close()
        print(encoded(result))
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(encoded({'error': str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
