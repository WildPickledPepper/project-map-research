"""Generate committed project-scope ledgers without modifying the source repository."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.project_inventory import build_inventory,write_inventory
from projectmap.version import rules_version


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--revision',default='HEAD')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--development',action='store_true')
    a=p.parse_args();output=a.output.resolve();source=a.source.resolve()
    if output.is_relative_to(ROOT) or output.is_relative_to(source):p.error('Keep inventory artifacts outside both repositories')
    version='uncommitted_development' if a.development else rules_version(require_clean=True)
    result=build_inventory(source,a.revision,rules_version=version)
    baseline=write_inventory(result,output)
    print(json.dumps({'output':str(output),**baseline},ensure_ascii=False))


if __name__=='__main__':main()
