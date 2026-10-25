"""Invoke the isolated tool environment and forward CLI arguments and exit codes."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--environment',type=Path,default=Path(os.environ.get('PROJECT_MAP_ENV',Path.home()/'.cache/project-map-assistant/venv')))
    a,remaining=p.parse_known_args()
    python=a.environment.expanduser().resolve()/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():
        print('Run this skill scripts/bootstrap.py first, or pass --environment VENV',file=sys.stderr)
        return 2
    return subprocess.call([str(python),'-I','-X','utf8','-m','projectmap',*remaining])


if __name__=='__main__':raise SystemExit(main())
