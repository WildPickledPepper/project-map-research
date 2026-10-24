"""Keep historical source-version evidence separate from current-graph coverage."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.project_map import ProjectMap

VALIDATION = {4: 1026, 6: 1105, 10: 1232, 14: 937, 15: 935, 16: 957,
    17: 962, 18: 975, 19: 1121, 20: 1081, 21: 1142, 24: 1213}
BASE = 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688'


def records(path):
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(path) as z:
        strings = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', ns)] if 'xl/sharedStrings.xml' in z.namelist() else []
        for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('s:sheetData/s:row', ns):
            item = {}
            for cell in row.findall('s:c', ns):
                value = cell.find('s:v', ns)
                item[re.sub(r'\d+', '', cell.get('r'))] = (strings[int(value.text)] if cell.get('t') == 's' and value is not None else
                    ''.join(cell.find('s:is', ns).itertext()) if cell.get('t') == 'inlineStr' else value.text if value is not None else '')
            if item.get('A', '').isdigit() and int(item['A']) in VALIDATION:
                yield item


def run(source, index, output):
    output.mkdir(parents=True, exist_ok=False)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE).decode('utf-8', errors='replace')
    q = ProjectMap(index, expected_snapshot=None)
    result = []
    try:
        for original in records(ROOT/'datasets/msinsight-regressions/msinsight-24-test-candidates.xlsx'):
            number = int(original['A'])
            fixes = git('log', '--all', '--format=%H', '--grep=^!' + str(VALIDATION[number]) + ' ').splitlines()
            fixes = [f for f in fixes if subprocess.run(['git', '-C', str(source), 'merge-base', '--is-ancestor', f, BASE], capture_output=True).returncode == 0]
            if len(fixes) != 1:
                raise ValueError('Need one pinned master fix for record ' + str(number))
            fixed = fixes[0]
            before = git('rev-parse', fixed + '^1').strip()
            paths = git('diff', '--name-only', before, fixed).splitlines()
            patch = git('diff', '--unified=2', before, fixed)
            (output/(str(number) + '-fix.patch')).write_text(patch, encoding='utf-8')
            introduced = []
            for prefix in re.findall(r'\b[0-9a-f]{10,40}\b', original.get('F', '')):
                try: introduced.append({'given': prefix, 'commit': git('rev-parse', '--verify', '--end-of-options', prefix + '^{commit}').strip()})
                except subprocess.CalledProcessError: introduced.append({'given': prefix, 'status': 'not_in_local_history'})
            coverage = []
            for path in paths:
                row = q.db.execute('SELECT payload FROM pm_map_files WHERE path=?', (path,)).fetchone()
                item = json.loads(row[0]) if row else None
                counts = dict(q.db.execute('SELECT kind,count(*) FROM pm_fact_nodes WHERE path=? GROUP BY kind', (path,)))
                coverage.append({'path': path, 'tracked_at_current_source': item is not None,
                    'graph_input': item.get('graph_input', False) if item else False,
                    'coverage': item.get('graph_coverage') if item else None,
                    'exclusion_reason': item.get('reason') if item else 'path_absent_at_current_source',
                    'node_kinds': counts})
            result.append({'id': number, 'original_row': original['B'], 'fix_request': VALIDATION[number],
                'family': 'communication_details_15_18' if 15 <= number <= 18 else
                    'python_stack_19_20' if number in {19, 20} else 'leaks_shared_drawing_4_6' if number in {4, 6} else 'separate',
                'external_reference': {'fix': original['C'], 'issue': original['D'], 'introduced_request': original['E'],
                    'reported_symptom': original['G'], 'reported_cause': original['H'], 'scenario': original['I'],
                    'limits': original['J'], 'source_evidence': original['K']},
                'source_versions': {'introduced': introduced, 'pre_fix_first_parent': before, 'fixed_merge': fixed,
                    'fixed_is_ancestor_of_current': True},
                'source_diff': {'changed_paths': paths, 'added_lines': sum(l.startswith('+') and not l.startswith('+++') for l in patch.splitlines()),
                    'removed_lines': sum(l.startswith('-') and not l.startswith('---') for l in patch.splitlines()),
                    'raw_patch': str(number) + '-fix.patch'},
                'current_graph_coverage': coverage,
                'assessment': {'source_history': 'before_and_after_fix_available',
                    'current_static_localization': 'entities_present' if any(c['node_kinds'] for c in coverage) else 'no_entities_in_changed_paths',
                    'historical_graph_execution': 'not_run_for_each_bad_and_fixed_version',
                    'automatic_bug_detection': 'not_evaluated', 'runtime_reproduction': 'not_executed_A5',
                    'cause_confirmation': 'source_diff_and_external_report_only',
                    'current_graph_is_historical_bad_version': False}})
        assert {r['id'] for r in result} == set(VALIDATION)
        overlaps = set(next(r for r in result if r['id'] == 4)['source_diff']['changed_paths']) & set(next(r for r in result if r['id'] == 6)['source_diff']['changed_paths'])
        report = {'evidence_kind': 'executed_historical_git_version_and_current_graph_inventory_audit',
            'authorization': 'user requested A4; protocol frozen at 379da8d before targeted inspection',
            'source_commit': BASE, 'snapshot': q.info['snapshot'], 'records': result,
            'groups': {'communication_details': [15, 16, 17, 18], 'python_stack': [19, 20],
                'shared_drawing': [4, 6], 'shared_drawing_changed_path_overlap': sorted(overlaps)},
            'counts': {'denominator': 12, 'source_before_after_available': len(result),
                'current_entities_present': sum(r['assessment']['current_static_localization'] == 'entities_present' for r in result),
                'historical_bad_fixed_graph_pairs_executed': 0, 'runtime_reproduced': 0, 'automatic_bug_detection_scored': 0},
            'interpretation': 'current fixed-version entity coverage is separate from historical defect detection',
            'file_hash_verification': 'not_run_per_user_preference'}
        (output/'history.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(report['counts']))
    finally:
        q.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'index', 'output'): p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    run(a.source, a.index, a.output)
