"""Package small P7 reports from external artifacts; no raw graph, source or trace."""
import argparse
from collections import Counter
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def portable(value):
    if isinstance(value, str):
        return value.replace(str(WORKSPACE), '$WORKSPACE').replace(WORKSPACE.as_posix(), '$WORKSPACE')
    if isinstance(value, list):
        return [portable(x) for x in value]
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items()}
    return value


def write(path, value):
    path.write_text(json.dumps(portable(value), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def package(results, include_final=False):
    dest = HERE/'evidence'
    acceptance = results/'p7-upstream-acceptance-01'
    write(dest/'validation.json', read(acceptance/'validation.json'))
    catalog = read(results/'p7-upstream-01/coverage-catalog.json')
    for capability in catalog['capabilities']:
        full = capability['evidence']
        capability['evidence'] = full[:3]
        capability['evidence_total'] = len(full)
        capability['evidence_truncated'] = len(full) > 3
    catalog['publication'] = 'counts and at most three lexical examples per category; regenerate full catalog with coverage_catalog.py'
    write(dest/'coverage-summary.json', catalog)
    (dest/'project-map.md').write_text(portable((acceptance/'project-map.md').read_text(encoding='utf-8')), encoding='utf-8')
    write(dest/'inventory.json', read(results/'p7-upstream-01/inventory.json'))
    trials = [('a', 'p7-ai-a-01'), ('b', 'p7-ai-b-01')]
    if include_final:
        trials.append(('upstream', 'p7-ai-upstream-01'))
    usage = []
    for name, folder in trials:
        trial = results/folder
        answers = read(trial/'output/answers.json')
        assert {a['id'] for a in answers} == {f'T{i:02}' for i in range(1, 12)}
        write(dest/f'ai-{name}-answers.json', answers)
        metadata = read(trial/'bundle.json')
        entries = [json.loads(s) for s in (trial/'output/usage.jsonl').read_text(encoding='utf-8').splitlines()]
        entries = [e for e in entries if e.get('task') in {f'T{i:02}' for i in range(1, 12)}]
        (dest/f'ai-{name}-usage.jsonl').write_text(''.join(json.dumps(portable(e), ensure_ascii=False)+'\n' for e in entries), encoding='utf-8')
        rows = []
        for i in range(1, 12):
            task = f'T{i:02}'; selected = [e for e in entries if e['task'] == task]
            ends = [e for e in selected if e['action'] == 'end']
            assert len(ends) == 1, (name, task, ends)
            calls = [e for e in selected if e['action'] in {'read', 'query'}]
            rows.append({'task': task, 'elapsed_seconds': round(ends[0]['elapsed_seconds'], 3),
                'successful_calls': dict(Counter(e['action'] for e in calls)),
                'tool_seconds': round(sum(e['elapsed_seconds'] for e in calls), 3),
                'result_bytes': sum(e['result_bytes'] for e in calls),
                'displayed_bytes': sum(e['displayed_bytes'] for e in calls)})
        usage.append({'participant': name, 'input': metadata, 'tasks': rows})
    write(dest/'ai-usage.json', {'evidence_kind': 'executed_isolated_agent_helper_logs', 'trials': usage,
        'model': 'parent model inherited; exact model identifier not exposed by agent tool',
        'tokens': 'not_exposed', 'context_tokens': 'not_exposed', 'cost': 'not_exposed',
        'measurement': 'task begin/end intervals, not total session duration; counts and bytes are successful helper operations; errors before logging are absent; setup and answer-file writing outside task intervals excluded',
        'output_bytes': 'UTF-8 bytes, not tokens; displayed_bytes precedes any outer tool/UI truncation',
        'isolation': 'separate input/output directories and instructions; no peer results supplied; shared filesystem is not a security boundary',
        'comparison': 'graph-assisted usability only; no source-only control and no accuracy generalization'})
    print('Packaged compact P7 evidence for '+', '.join(n for n, _ in trials))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--include-final', action='store_true')
    args = parser.parse_args()
    package(args.results, args.include_final)
