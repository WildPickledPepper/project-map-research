"""Compare two complete frontend phase results by parsed JSON equality."""
import argparse
import json
from pathlib import Path
import time

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['first','second','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();started=time.monotonic()
    first=json.loads(a.first.read_text(encoding='utf-8'));second=json.loads(a.second.read_text(encoding='utf-8'))
    result={'evidence_kind':'executed_complete_frontend_phase_JSON_comparison','equal':first==second,
        'differing_keys':[k for k in first.keys()|second.keys() if first.get(k)!=second.get(k)],
        'scope':'all frontend phase facts and metadata; not a second C++ or complete graph rebuild',
        'elapsed_seconds':round(time.monotonic()-started,3),'file_hash_verification':'not_run_per_user_preference'}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
    raise SystemExit(0 if result['equal'] else 1)
