"""Produce portable, compact evidence from completed P1 runs; no graph invention."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from run_native import RESEARCH, write


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('native', 'codegraph', 'facts', 'integration', 'parser-cache', 'output'):
        ap.add_argument('--'+key,type=Path,required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise ValueError('Use a new evidence directory')
    manifest = args.native/'input-manifest.json'
    if manifest.read_bytes() != (args.codegraph/'input-manifest.json').read_bytes():
        raise ValueError('Tools did not receive identical input manifests')
    facts = read(args.facts)
    if facts['manifest_sha256'] != digest(manifest):
        raise ValueError('Syntax facts describe different input')
    integration = read(args.integration/'integration-evidence.json')
    env = read(args.native/'environment.json')
    if integration['native_versions'] != env:
        raise ValueError('Integrated graph describes another native run')
    cbm = read(args.native/'cbm-evidence.json')
    cbm = {k:v for k,v in cbm.items() if not k.endswith('_schema')}
    cgc = read(args.native/'cgc-evidence.json')
    for scope in cgc['scopes'].values():
        scope.pop('parser',None)
    cg = read(args.codegraph/'codegraph-evidence.json')
    selected = []
    names = {'QueryUnitFlows','HandleRequest','getUnitFlows','createRequest','send','fetch'}
    for record in facts['records']:
        symbols = [s for s in record['symbols'] if s['name'] in names]
        calls = [c for c in record['calls'] if c['callee_spelling'] in ('window.requestData','database->QueryUnitFlows')]
        bindings = [b for b in record['bindings'] if b['left_spelling']=='window.requestData']
        if symbols or calls or bindings:
            selected.append({k:record[k] for k in ('path','language','sha256_lf_utf8','evidence_kind')} |
                            {'symbols':symbols,'calls':calls,'bindings':bindings})
    syntax = {k:facts[k] for k in ('schema_version','source_commit','extractor_version','packages','manifest_sha256','coverage')}
    syntax['counts'] = {'files':len(facts['coverage']), 'parsed_records':len(facts['records']),
                        **{key:sum(len(r[key]) for r in facts['records']) for key in ('symbols','calls','bindings')},
                        'coverage_statuses':dict(Counter(f['status'] for f in facts['coverage']))}
    syntax['selected_facts'] = selected
    syntax['selection'] = 'Named source observations for review; full facts remain in the external run directory'
    implementation = ['adapters/syntax_supplement.py','adapters/kuzu_fact_store.py',
                      'scripts/extract_syntax_facts.py','scripts/integrate_syntax_facts.py',
                      'requirements-facts.txt','requirements-store.txt']
    implementation += [p.relative_to(RESEARCH).as_posix() for p in sorted(Path(__file__).parent.glob('*.py'))]
    implementation += [p.relative_to(RESEARCH).as_posix() for p in sorted((Path(__file__).parent/'fixtures').iterdir())]
    provenance = {'schema_version':1,'evidence_kind':'executed_tools_and_source_syntax_supplement',
                  'source_commit':facts['source_commit'],'identical_input_manifest_sha256':digest(manifest),
                  'implementation_sha256':{p:digest(RESEARCH/p) for p in implementation},
                  'parser_cache_files':[{ 'path':p.relative_to(args.parser_cache).as_posix(), 'sha256':digest(p)}
                                        for p in sorted(args.parser_cache.rglob('*'))
                                        if p.is_file() and p.suffix in ('.dll','.so','.json')],
                  'raw_artifacts':'external: original logs, native databases, full syntax facts and source copies'}
    payloads = {'input-manifest.json':read(manifest),'environment.json':env,
                'cbm.json':cbm,'cgc.json':cgc,'codegraph.json':cg,
                'syntax.json':syntax,'integration.json':integration,'provenance.json':provenance}
    # Public evidence may contain source-relative locations, never personal paths.
    for name, payload in payloads.items():
        encoded = json.dumps(payload,ensure_ascii=False)
        if re.search(r'[A-Za-z]:[\\/]+(?:Users|workspace)[\\/]',encoded):
            raise ValueError(f'Personal path in {name}')
    for name,payload in payloads.items():
        write(out/name,payload)
    print(json.dumps({'files':len(payloads),'syntax_counts':syntax['counts']}))


if __name__ == '__main__':
    main()
