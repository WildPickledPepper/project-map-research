"""Prepare a controlled late-response fault in the push-disabled experimental clone."""
import argparse
import json
from pathlib import Path
import subprocess


def inject(source):
    source = Path(source).resolve()
    git = lambda *args: subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    if git('remote', 'get-url', '--push', 'origin') != 'disabled://p5-local-experiment':
        raise ValueError('Fault injection requires the isolated push-disabled P5 clone')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Commit experimental source before preparing a fault')
    filename = 'modules/framework/src/centralServer/websocket/connection.ts'
    file = source/filename
    content = file.read_text(encoding='utf-8')
    if "__projectMapProbe?.event('response.classified'" not in content:
        raise ValueError('Apply the runtime capture points first')
    old = 'if (!isImport && isOldRequest) {'
    if content.count(old) != 1: raise ValueError('Expected one original late-project response guard')
    new = ('// P5 controlled fault: the browser driver explicitly enables stale response adoption.\n'
           '        if (!isImport && isOldRequest && !(globalThis as any).__projectMapAllowStaleResponse) {')
    file.write_text(content.replace(old, new), encoding='utf-8', newline='\n')
    return {'base_commit': git('rev-parse', 'HEAD'), 'files': [filename],
            'fault': 'Allow an old-project response through the real framework callback guard',
            'activation': 'The isolated test browser sets __projectMapAllowStaleResponse=true',
            'default': 'Original project guard remains active when the test flag is absent',
            'required_next_steps': 'Commit locally and rebuild Framework before running fault scenario'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True, type=Path)
    args = ap.parse_args(); print(json.dumps(inject(args.source), indent=2))
