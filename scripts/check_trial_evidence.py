"""Check published trial provenance and internal consistency, not graph completeness."""
import json
from pathlib import Path, PurePosixPath
import re

ROOT=Path(__file__).resolve().parents[1]
TRIAL=ROOT/'experiments/2026-10-23-unit-flows'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
reference=read(ROOT/'cases/unit-flows/reference.json')
commit=reference['repository']['commit']
anchors={a['path'] for a in reference['anchors']}

def require(condition,message):
    if not condition:
        raise SystemExit(message)

for tool,name in [('codegraph','slice-manifest.json'),('code-map','manifest.json')]:
    manifest=read(TRIAL/tool/name)
    require(manifest['source_commit']==commit==manifest['repository']['commit'],tool+': source commit mismatch')
    paths=[f['path'] for f in manifest['files']]
    require(len(paths)==len(set(paths)) and anchors.issubset(paths),tool+': duplicate/missing source paths')
    for row in manifest['files']:
        path=PurePosixPath(row['path'])
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in row['path'],tool+': invalid path')
        for key in ['sha256','sha256_lf_utf8']:
            require(bool(re.fullmatch('[0-9a-f]{64}',row[key])),tool+': invalid input hash')

cg=read(TRIAL/'codegraph/compact-evidence.json')
provenance=read(TRIAL/'codegraph/binary-provenance.json')
require(cg['provenance']==provenance,'CodeGraph: binary provenance mismatch')
require(provenance['sha256']==provenance['official_sha256'],'CodeGraph: official checksum mismatch')
require(provenance['release_tag_commit_matches_source'],'CodeGraph: unverified release tag correspondence')
cg_manifest=read(TRIAL/'codegraph/slice-manifest.json')
require(cg['input']['files']==len(cg_manifest['files']),'CodeGraph: file count mismatch')
require(next(int(r['n']) for r in cg['counts']['nodes_by_label'] if r['label']=='File')==len(cg_manifest['files']),
        'CodeGraph: indexed file count differs from input')
require(cg['update']['comparison']==read(TRIAL/'codegraph/update-comparison.json'),'CodeGraph: update comparison mismatch')
require(cg['update']['delta']==read(TRIAL/'codegraph/update-delta.json'),'CodeGraph: update delta mismatch')
if not cg['update']['comparison']['edges_identical']:
    require(bool(cg['update']['delta']['only_in_incremental_edges'] or cg['update']['delta']['only_in_full_edges']),
            'CodeGraph: failed equivalence must retain actual edge differences')
require(bool(cg['untested']),'CodeGraph: untested scope omitted')

cm=read(TRIAL/'code-map/evidence.compact.json')
require(cm['source']['commit']==commit,'code-map: source commit mismatch')
require(all(x['in_slice'] for x in cm['checks']['anchor_file_presence']),'code-map: missing reference anchors')
for name,scan in cm['scans'].items():
    require(sum(scan['node_types'].values())==scan['nodes'],name+': node totals mismatch')
    require(sum(scan['edge_types'].values())==scan['edges'],name+': edge totals mismatch')
require(cm['query_diagnostic']['error']['code']=='SUBMAP_SEED_NOT_FOUND','code-map: missing-seed evidence changed')
require(bool(cm['unverified']),'code-map: untested scope omitted')

rerun=read(TRIAL/'coordinator-reproduction.json')
require(rerun['source_commit']==commit,'Coordinator: source version mismatch')
for tool in ['codegraph','code-map']:
    require(all(rerun[tool]['selected_evidence_fields_identical'].values()),tool+': reproduction difference')
require(rerun['codegraph']['update_comparison']==cg['update']['comparison'],'Coordinator: update result mismatch')
print('OK: two pinned input manifests, 15 anchor coverage, native evidence consistency, and coordinator rerun record.')
