"""Inspect the existing CBM release on a small container/process/environment fixture."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time


FILES={
 'app.py':'''import os
import subprocess
def read_port():
    return os.getenv("APP_PORT")
def launch():
    return subprocess.Popen(["backend", "--port", read_port()])
''',
 'launch.sh':'''#!/bin/sh
ROOT=$(dirname "$0")
python "$ROOT/app.py"
''',
 'Dockerfile':'''FROM python:3.11
WORKDIR /app
COPY app.py /app/app.py
ENV APP_PORT=8000
CMD ["python", "/app/app.py"]
''',
 'compose.yaml':'''services:
  frontend:
    build: .
    environment:
      APP_PORT: "9000"
'''}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('binary','output'):ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():raise ValueError('Choose a new audit output')
    source=args.output/'source';source.mkdir(parents=True)
    (args.output/'cache').mkdir()
    for path,content in FILES.items():(source/path).write_text(content,encoding='utf-8')
    env={**os.environ,'CBM_CACHE_DIR':str(args.output/'cache')}
    started=time.perf_counter()
    p=subprocess.run([str(args.binary),'cli','--json','index_repository','--repo-path',str(source),'--name','reuse-audit',
        '--mode','full','--persistence','false','--doc-candidates','false'],env=env,cwd=source,capture_output=True,
        text=True,encoding='utf-8',errors='replace',timeout=90)
    (args.output/'index.log').write_text(p.stdout+p.stderr,encoding='utf-8')
    schema={};rows={};databases=list((args.output/'cache').rglob('*.db'))
    for path in databases:
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            tables=[r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in ('nodes','edges'):
                if table in tables:
                    schema[table]=[dict(r) for r in db.execute('PRAGMA table_info('+table+')')]
                    rows[table]=[dict(r) for r in db.execute('SELECT * FROM '+table)]
    (args.output/'native.json').write_text(json.dumps({'schema':schema,'rows':rows},indent=2),encoding='utf-8')
    result={'schema':'reuse-cbm-boundary-audit/1','binary_version':'0.12.1',
        'binary_release_commit':'a7158ac2f48ca646b4527341b76f930f2aeff87e',
        'inspected_source_commit':'10ab613de30dfd573d0b251cd0ad648e1c7e5204',
        'input_origin':'authored_container_python_shell_source','exit_code':p.returncode,'seconds':round(time.perf_counter()-started,3),
        'database_count':len(databases),'node_count':len(rows.get('nodes',[])),'edge_count':len(rows.get('edges',[])),
        'label_counts':{},'relation_counts':{},'file_hash_verification':'not_run_per_user_preference'}
    for name,column,key in [('nodes','label','label_counts'),('edges','type','relation_counts')]:
        for row in rows.get(name,[]):
            value=row.get(column,'unknown');result[key][value]=result[key].get(value,0)+1
    (args.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
