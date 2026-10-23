"""Check published P1 evidence consistency; does not rerun third-party tools."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'experiments/2026-10-23-p1/evidence'


def read(name):
    path = BASE/(name+'.json')
    text = path.read_text(encoding='utf-8')
    assert not re.search(r'[A-Za-z]:[\\/]+(?:Users|workspace)[\\/]',text), name
    return json.loads(text)


def check():
    manifest = read('input-manifest')
    provenance = read('provenance')
    assert manifest['source_commit'] == provenance['source_commit']
    # Historical hashes remain in the evidence. Per user preference, routine
    # checks use versions, paths and behavior instead of re-hashing files.
    for path in provenance['implementation_sha256']:
        assert (ROOT/path).is_file(), path
    for row in manifest['fixtures']:
        assert (BASE.parent/'fixtures'/row['path']).is_file()
    paths = {row['path'] for row in manifest['files']}
    assert len(paths) == len(manifest['files']) == 65
    syntax = read('syntax')
    assert syntax['source_commit'] == manifest['source_commit']
    assert {r['path'] for r in syntax['coverage']} == paths
    for record in syntax['selected_facts']:
        assert all(c['resolution']=='unresolved' for c in record['calls'])
    symbols = [s for r in syntax['selected_facts'] for s in r['symbols']]
    assert any(s['name']=='QueryUnitFlows' and s.get('pure_virtual') for s in symbols)
    assert sum(s['name']=='QueryUnitFlows' and s['definition'] for s in symbols) == 2
    assert any(s['qualified_name']=='BaseConnector.send' for s in symbols)
    cbm = read('cbm')
    for scope in ('source','fixtures'):
        coverage = cbm[scope+'_coverage']['result']
        assert not coverage['path_has_more']
        for key in ('files','symbols','calls'):
            result = cbm[scope+'_'+key]['result']
            assert not result.get('truncated') and not result.get('has_more')
    cgc = read('cgc')
    assert cgc['extension_probe']['passed']
    cg = read('codegraph')
    assert cg['source_commit'] == manifest['source_commit']
    native_q = cgc['scopes']['source']['queries']['symbols']['rows']
    assert sum(s['name']=='QueryUnitFlows' for s in native_q) == 2
    assert not any(s['name']=='QueryUnitFlows' for s in cg['scopes']['source']['queries']['symbols']['rows'])
    integration = read('integration')
    assert integration['native_versions'] == read('environment')
    lifecycle = integration['lifecycle']
    assert lifecycle['remaining_after_delete'] == 0
    assert lifecycle['native_before'] == lifecycle['native_after']
    assert all(lifecycle['restored_same_counts'].values())
    assert integration['facts'] == sum(syntax['counts'][k] for k in ('symbols','calls','bindings'))
    assert len(integration['queries']['database_call_observation']['rows']) == 1
    print('OK: P1 versions, paths, source evidence, untruncated queries and storage lifecycle; no file hash verification.')


if __name__ == '__main__':
    check()
