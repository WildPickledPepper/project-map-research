"""Publish portable Python trial results without raw graphs, logs or local paths."""
import argparse
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--only',nargs='+',choices=['resolver','proxy','repository','installed'],
                    help='Publish completed items separately; existing records are never overwritten.')
    args=ap.parse_args()
    sources={'python-resolver-probe.json':'w1-python-resolver-probe-01/result.json',
        'python-proxy.json':'w1-python-proxy-score-02.json',
        'python-repository.json':'w1-python-repository-score-02.json',
        'python-installed.json':'w1-python-installed-smoke-02/result.json'}
    selected={'resolver':'python-resolver-probe.json','proxy':'python-proxy.json',
              'repository':'python-repository.json','installed':'python-installed.json'}
    if args.only:sources={name:source for name,source in sources.items() if name in {selected[item] for item in args.only}}
    values={name:json.loads((args.results/source).read_text(encoding='utf-8')) for name,source in sources.items()}
    for name in values:
        if (args.output/name).exists():raise ValueError('Evidence already exists: '+name)
    for name,value in values.items():
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'Published {len(values)} portable Python evidence records; raw source exports and logs remain outside Git.')


if __name__=='__main__':main()
