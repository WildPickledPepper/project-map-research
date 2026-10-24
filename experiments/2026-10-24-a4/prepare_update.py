"""Create an isolated product clone with authored add/rename/delete commits."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_cpp_protocol import SOURCE

BASE = 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688'
FRONT = '''import {TAG} from './constant';
declare const channel:WebSocket;
export function entry(){channel.send(JSON.stringify({wireTag:TAG,space:'north'}));}
export function retiredEntry(){channel.send(JSON.stringify({wireTag:'a4/retired',space:'north'}));}
'''


def prepare(source, output):
    output.mkdir(parents=True, exist_ok=False)
    repo = output / 'source'
    subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout', str(source.resolve()), str(repo)], check=True, capture_output=True)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()
    git('checkout', '--detach', BASE)
    git('config', 'user.name', 'A4 authored updates')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'core.autocrlf', 'false')
    git('remote', 'set-url', '--push', 'origin', 'disabled://a4-local-experiment')
    def write(path, text):
        dest = repo / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8', newline='\n')
    def publish(message):
        git('add', '-A')
        git('commit', '-qm', message)
        return git('rev-parse', 'HEAD')
    write('a4_client/package.json', '{"name":"a4-authored-client","private":true}\n')
    write('a4_client/constant.ts', "export const TAG='a4/initial';\n")
    write('a4_client/request.ts', FRONT)
    write('a4_server/CMakeLists.txt', 'cmake_minimum_required(VERSION 3.16)\nproject(a4_source_probe LANGUAGES CXX)\n')
    write('a4_server/protocol.cpp', 'namespace A4Probe {\n' + SOURCE.replace('alpha/read', 'a4/initial') + '\n}')
    write('a4_server/obsolete.cpp', 'namespace A4Retired {\n' + SOURCE.replace('alpha/read', 'a4/retired') + '\n}')
    added = publish('A4 authored new modules and endpoints')
    git('mv', 'a4_server/protocol.cpp', 'a4_server/renamed.cpp')
    write('a4_server/renamed.cpp', (repo/'a4_server/renamed.cpp').read_text(encoding='utf-8')
        .replace('a4/initial', 'a4/final').replace('SpecificWork', 'RenamedWork'))
    write('a4_client/constant.ts', "export const TAG='a4/final';\n")
    write('a4_client/request.ts', FRONT.replace('function entry()', 'function renamedEntry()'))
    renamed = publish('A4 cross-file command, symbol and source-file rename')
    git('rm', '--', 'a4_server/obsolete.cpp')
    deleted = publish('A4 remove provider while keeping its consumer')
    config = json.loads((ROOT/'experiments/2026-10-24-a1/evidence/auto-config.json').read_text(encoding='utf-8'))
    config['deployment']['services'].append({'id': 'a4-authored', 'consumer_paths': ['a4_client'], 'provider_paths': ['a4_server']})
    (output/'config.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
    result = {'evidence_kind': 'executed_isolated_product_source_mutations', 'base': BASE,
        'commits': {'added': added, 'renamed': renamed, 'provider_deleted': deleted},
        'final_revision': deleted, 'changed_paths': git('diff', '--name-only', BASE, deleted).splitlines(),
        'fixture_origin': 'authored_protocol_fixture_not_historical_sample', 'upstream_push': 'disabled',
        'file_hash_verification': 'not_run_per_user_preference'}
    (output/'preparation.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    prepare(a.source, a.output)
