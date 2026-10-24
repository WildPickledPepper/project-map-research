"""Query the project map, typed paths, resources, changes and runtime evidence."""
import argparse
import json
from pathlib import Path
from project_query import ProjectQuery, render_markdown


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--graph', type=Path, required=True)
    ap.add_argument('--inventory', type=Path)
    ap.add_argument('--catalog', type=Path)
    ap.add_argument('--format', choices=('json', 'markdown'), default='json')
    ap.add_argument('--offset', type=int, default=0); ap.add_argument('--limit', type=int, default=30)
    sub = ap.add_subparsers(dest='command', required=True)
    p=sub.add_parser('overview'); p.add_argument('--scope', default='')
    p=sub.add_parser('coverage');p.add_argument('--capability')
    p=sub.add_parser('search'); p.add_argument('text', nargs='?', default=''); p.add_argument('--kind')
    p=sub.add_parser('trace'); p.add_argument('name'); p.add_argument('--target'); p.add_argument('--reverse', action='store_true')
    p.add_argument('--depth', type=int, default=16); p.add_argument('--field', type=json.loads); p.add_argument('--details', action='store_true')
    p=sub.add_parser('resource'); p.add_argument('name')
    p=sub.add_parser('impact'); p.add_argument('--name'); p.add_argument('--changed-path', action='append', default=[])
    p.add_argument('--diff', type=Path); p.add_argument('--depth', type=int, default=20)
    p=sub.add_parser('explain'); p.add_argument('--node'); p.add_argument('--gap');p.add_argument('--edge',type=json.loads)
    p=sub.add_parser('assets'); p.add_argument('--target')
    p=sub.add_parser('runs'); p.add_argument('--store', type=Path, required=True); p.add_argument('--scenario')
    args=ap.parse_args(); read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    model=ProjectQuery(read(args.graph), read(args.inventory) if args.inventory else None,read(args.catalog) if args.catalog else None)
    page={'offset':args.offset,'limit':args.limit}
    if args.command=='overview': result=model.overview(args.scope,**page)
    elif args.command=='coverage':result=model.coverage(args.capability,**page)
    elif args.command=='search': result=model.search(args.text,args.kind,**page)
    elif args.command=='trace': result=model.trace(args.name,target=args.target,reverse=args.reverse,depth=args.depth,field=args.field,details=args.details,**page)
    elif args.command=='resource': result=model.resource(args.name,**page)
    elif args.command=='impact':
        changed=args.changed_path
        if args.diff:
            diff=read(args.diff)
            if diff['source_after_commit']!=model.graph['source_commit']: raise ValueError('Diff target and graph source differ')
            changed+=diff['changed_paths']
        result=model.impact(name=args.name,changed_paths=changed,depth=args.depth,**page)
    elif args.command=='explain': result=model.explain(args.node,args.gap,args.edge,**page)
    elif args.command=='assets': result=model.assets(args.target,**page)
    else: result=model.runs(args.store,args.scenario,**page)
    print(render_markdown(result) if args.format=='markdown' else json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
