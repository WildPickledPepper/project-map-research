"""Render an indexed structural module map as portable Markdown and Mermaid."""
import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.project_map import ProjectMap


def collect(call):
    items, cursor = [], None
    while True:
        result = call(limit=100, cursor=cursor)
        if result.get('stop_reason') not in {None, 'output_budget'}:
            raise ValueError(result['stop_reason'])
        items.extend(result['items'])
        cursor = result['next_cursor']
        if not cursor:
            return items


def render(index, destination):
    q = ProjectMap(index)
    try:
        modules, links = collect(q.overview), collect(q.links)
        ids = {m['path']: 'm' + str(i) for i, m in enumerate(modules)}
        pairs = Counter()
        for link in links:
            pairs[(link['source'], link['target'])] += link['edges']
        lines = ['# 自动生成的项目地图', '',
            '来源：已执行的 A3 查询；模块按最近受版本控制构建清单归属。', '',
            f"源码提交：`{q.info['source_commit']}`。快照：`{q.info['snapshot']}`。", '',
            '图中连线汇总跨模块的源码关系与条件候选；箭头沿事实边方向，数量包含不同关系类型和平行边。', '',
            '```mermaid', 'flowchart LR']
        for m in modules:
            label = m['path'].replace('"', '&quot;')
            lines.append(f'  {ids[m["path"]]}["{label}<br/>{m["graph_inputs"]} 个分析输入"]')
        for (source, target), count in sorted(pairs.items()):
            lines.append(f'  {ids[source]} -->|{count}| {ids[target]}')
        lines += ['```', '', '| 模块 | 受版本控制文件 | 分析输入 | 源码实体 |', '|---|---:|---:|---:|']
        for m in modules:
            lines.append(f'| `{m["path"]}` | {m["files"]} | {m["graph_inputs"]} | {sum(m["node_kinds"].values())} |')
        lines += ['', '逐层查询命令见 [A3 使用说明](../README.md)。无分析输入的模块仍保留在地图中，具体排除理由由 files 查询给出。', '']
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('\n'.join(lines), encoding='utf-8')
        return {'modules': len(modules), 'module_pairs': len(pairs), 'cross_module_edges': sum(pairs.values())}
    finally:
        q.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(render(a.index, a.output))
