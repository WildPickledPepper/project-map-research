"""Native boundary isolation and explicit-scope checks; expected cases precede execution."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.cbm_provider import index
from adapters.sqlite_fact_graph import validate_graph

FILES = {'build/launch.sh': '#!/bin/sh\nsh ../scripts/task.sh\n',
         'scripts/task.sh': '#!/bin/sh\n./native-helper\n'}
for service in ('left', 'right'):
    FILES[service + '/app.py'] = 'import os\ndef read_port():\n    return os.getenv("SHARED_PORT")\n'
    FILES[service + '/Dockerfile'] = ('FROM python:3.11\nWORKDIR /service\nCOPY app.py /service/app.py\n'
                                    'ENV SHARED_PORT=8000\nCMD ["python", "/service/app.py"]\n')
FILES['compose.yaml'] = '''services:
  first:
    build: ./left
    environment:
      SHARED_PORT: "9100"
  second:
    build: ./right
    environment:
      SHARED_PORT: "9200"
'''
EXPECTED = ['selected_build_directory_not_silently_skipped', 'shell_script_to_script_spawn',
            'left_container_env_reaches_own_reader', 'right_container_env_reaches_own_reader',
            'same_key_env_does_not_cross_services', 'two_same_named_readers_keep_distinct_ids',
            'input_export_unchanged', 'imported_edges_keep_candidate_precision']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'binary', 'cache-dir', 'runtime-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.output / 'source'; source.mkdir()
    for path, content in FILES.items():
        target = source / path; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    (args.output / 'expected.json').write_text(json.dumps(EXPECTED), encoding='utf-8')
    facts = index(source, args.output / 'native', paths=list(FILES), source_commit='b' * 40,
                  binary=args.binary, cache_dir=args.cache_dir, runtime_dir=args.runtime_dir,
                  project='r0-isolation')
    validate_graph({'snapshot': 'authored', **facts})
    (args.output / 'facts.json').write_text(json.dumps(facts), encoding='utf-8')
    nodes = {n['id']: n for n in facts['nodes']}
    env = [(nodes[e['source']], nodes[e['target']]) for e in facts['edges']
           if e['kind'] == 'CBM_CONFIGURES' and e['native_properties'].get('strategy') == 'env_read']
    def own(side):
        return any(a['path'] == side + '/Dockerfile' and b['path'] == side + '/app.py' for a, b in env)
    checks = [
        ('selected_build_directory_not_silently_skipped', any(n['kind'] == 'code_module' and n['path'] == 'build/launch.sh' for n in nodes.values())),
        ('shell_script_to_script_spawn', any(e['kind'] == 'CBM_SPAWNS' and nodes[e['source']]['path'] == 'build/launch.sh' and nodes[e['target']]['path'] == 'scripts/task.sh' for e in facts['edges'])),
        ('left_container_env_reaches_own_reader', own('left')),
        ('right_container_env_reaches_own_reader', own('right')),
        ('same_key_env_does_not_cross_services', not any(a['path'].endswith('/Dockerfile') and a['path'].split('/')[0] != b['path'].split('/')[0] for a, b in env)),
        ('two_same_named_readers_keep_distinct_ids', len({n['id'] for n in nodes.values() if n['display_name'] == 'read_port'}) == 2),
        ('input_export_unchanged', {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()} == set(FILES)),
        ('imported_edges_keep_candidate_precision', all(e['status'] == 'candidate' for e in facts['edges'] if e['kind'] in {'CBM_SPAWNS', 'CBM_CONFIGURES'}))]
    result = {'schema': 'r0-cbm-isolation/1', 'evidence_kind': 'executed_native_component',
              'checks': [{'id': name, 'passed': bool(passed)} for name, passed in checks],
              'coverage': facts['coverage'], 'components': facts['components'],
              'passed': all(passed for _, passed in checks), 'whole_G02_accepted': False}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
