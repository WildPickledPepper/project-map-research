"""Install the bundled tool into a dedicated environment, without global pip changes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--environment',type=Path,default=Path(os.environ.get('PROJECT_MAP_ENV',Path.home()/'.cache/project-map-assistant/venv')))
    p.add_argument('--wheel',type=Path)
    p.add_argument('--query-only',action='store_true',help='Install without optional extraction/MCP dependencies')
    a=p.parse_args();bundled=list((Path(__file__).resolve().parents[1]/'assets').glob('project_map_tool-*.whl'))
    wheel=a.wheel or (bundled[0] if len(bundled)==1 else None)
    if wheel is None or not wheel.is_file():p.error('Supply --wheel PATH.whl or use the complete skill distribution')
    environment=a.environment.expanduser().resolve()
    if environment==Path(sys.prefix).resolve():p.error('Choose a dedicated virtual environment')
    if environment.exists() and any(environment.iterdir()) and not (environment/'pyvenv.cfg').is_file():
        p.error('Environment directory is nonempty and is not a virtual environment')
    venv.EnvBuilder(with_pip=True).create(environment)
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    spec=str(wheel.resolve())+('' if a.query_only else '[all]')
    result=subprocess.run([str(python),'-I','-m','pip','install','--disable-pip-version-check',spec],stdout=sys.stderr,stderr=sys.stderr)
    if result.returncode:return result.returncode
    print(json.dumps({'environment':str(environment),'python':str(python),'installed':True}))
    return 0


if __name__=='__main__':raise SystemExit(main())
