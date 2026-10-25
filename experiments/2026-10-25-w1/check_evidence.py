"""Check native component evidence without promoting it to language acceptance."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'evidence/native-summary.json').read_text(encoding='utf-8'))
assert data['upstream']['commit']=='93c9685bff9151f50a3121e9913e5ba2d27c1191'
assert data['upstream']['version']=='0.6.13' and not data['upstream']['tracked_files_modified']
assert len(data['files'])==185 and data['errors']==0
assert all(r['status']=='parsed' for r in data['files'])
assert {language:sum(r['language']==language for r in data['files']) for language in ('javascript','python','rust')}=={'javascript':53,'python':119,'rust':13}
for language,counts in data['counts_by_language'].items():
    for key,total in counts.items():
        assert sum(r['counts'].get(key,0) for r in data['files'] if r['language']==language)==total
assert not data['cross_file_resolution_executed'] and not data['normalized_graph_produced']
assert data['G02']=='not_accepted' and not data['historical_assets_enabled']
print('OK: native language outputs for 185 files; semantic/cross-file/installed query acceptance remains pending.')
