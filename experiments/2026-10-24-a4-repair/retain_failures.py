"""Retain failed development builds and their observed stop causes."""
import argparse
import json
from pathlib import Path

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    runs = []
    for name, reason, stopped in [
        ('a4-repair-full-02', 'TypeError: q.members is not iterable in external constructor inheritance', False),
        ('a4-repair-full-03', 'cancelled duplicate after same frozen rules failed in full-02', True),
    ]:
        run = json.loads((a.results/name/'result.json').read_text(encoding='utf-8'))
        request = json.loads((a.results/name/'build/request.json').read_text(encoding='utf-8'))
        runs.append({'run': name, 'build_version': request['build_version'], 'measured':run,
                     'cause':reason, 'manual_stop':stopped, 'complete_graph_published':False})
    result = {'evidence_kind':'executed_development_failures_retained', 'runs':runs,
        'return_replay':{'evidence_kind':'executed_tool_output_transcribed',
            'base_rules':'b49092d', 'uncommitted_base_class_fix':True, 'compact_guard_descriptions':False,
            'error':'RangeError: Invalid string length in uniq/guarded',
            'repair':'structural guard descriptions omit recursively embedded path conditions; value description has a finite node budget'},
        'repaired_return_replay':{'evidence_kind':'executed_uncommitted_development_replay',
            'entries':147,'boundaries':157,'returns':4462,'transmissions':55,'window_listeners':146,'handoffs':118,
            'complete_graph_published':False}}
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
