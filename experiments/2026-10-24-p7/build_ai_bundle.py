"""Build a fresh isolated AI input bundle, excluding scoring references."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from project_query import ProjectQuery,render_markdown

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def build(graph_path, inventory_path, source, runtime_store, output, catalog_path=None,tasks_path=None):
    if output.exists():raise ValueError('Use a fresh bundle directory')
    output.mkdir(parents=True)
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    graph=read(graph_path);inventory=read(inventory_path);catalog=read(catalog_path) if catalog_path else None;q=ProjectQuery(graph,inventory,catalog)
    tasks_path=tasks_path or HERE/'ai-tasks.json'
    if read(tasks_path)['source_commit']!=graph['source_commit']:raise ValueError('Task input version and graph differ')
    def portable(value):
        if isinstance(value,dict):return {k:portable(v) for k,v in value.items()}
        if isinstance(value,list):return [portable(v) for v in value]
        if isinstance(value,str):
            for path in (str(ROOT.parent),ROOT.parent.as_posix()):value=value.replace(path,'$WORKSPACE')
        return value
    def save(name,data):
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(portable(data),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('graph.json',graph);save('inventory.json',inventory)
    if catalog:save('coverage-catalog.json',catalog)
    save('runtime.json',q.runs(runtime_store,limit=500))
    save('overview.json',q.overview(limit=500))
    (output/'map.md').write_text(render_markdown(q.overview(limit=500)),encoding='utf-8')
    shutil.copytree(ROOT/'adapters',output/'adapters',ignore=shutil.ignore_patterns('__pycache__'))
    query_dir=output/'experiments/2026-10-24-p7';query_dir.mkdir(parents=True)
    for name in ('project_query.py','query.py'):shutil.copyfile(HERE/name,query_dir/name)
    shutil.copyfile(HERE/'workbench.py',output/'workbench.py')
    shutil.copyfile(tasks_path,output/'ai-tasks.json')
    paths=set(graph['input_paths'])
    for module in inventory['modules']:paths.update(m['path'] for m in module['metadata'])
    for path in sorted(paths):
        target=output/'source'/path;target.parent.mkdir(parents=True,exist_ok=True)
        content=subprocess.check_output(['git','-C',str(source),'show',graph['source_commit']+':'+path])
        target.write_bytes(content)
    save('bundle.json',{'source_commit':graph['source_commit'],'snapshot':graph['snapshot'],
        'rules':graph['version']['build_version'],'query_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip(),
        'source_files':len(paths),'questions':'ai-tasks.json','gold_included':False,
        'isolation':'separate directory and instruction-restricted reads; shared filesystem is not a security boundary',
        'runtime_origin':'P5 real records; original versions retained; not new memory-chain execution'})
    (output/'START.md').write_text('''# AI evaluation bundle

Read only this bundle. Do not read sibling bundles, the research repository, scoring references, prior agent outputs, or external sources. Do not message other agents or create subagents.

Use `python workbench.py begin T01` before each task and `python workbench.py end T01` after writing its answer. All source/query reads during a task must use workbench so elapsed time and bytes are measured. Use the same pattern for all tasks in ai-tasks.json.

Examples (run in this bundle):

```
python workbench.py --select coverage query --limit 500 overview
python workbench.py --select repository.languages query coverage
python workbench.py --select items query search QueryMemoryView --kind callable
python workbench.py --select items query trace memoryCurveGet
python workbench.py --select chains.0.summary query trace memoryCurveGet --field '["lines"]'
python workbench.py query impact --changed-path server/src/modules/memory/parser/CurveContainer.cpp
python workbench.py query impact --name 'Dic::Module::Memory::TextMemoryDataBase::QueryMemoryView'
python workbench.py query trace 'Dic::Module::Memory::TextMemoryDataBase::QueryMemoryView' --reverse
python workbench.py query resource CurveContainer
python workbench.py query assets --target memoryCurveGet
python workbench.py --select items.0.observed_dispatch_targets read runtime.json
python workbench.py --select items.0 read runtime.json
python workbench.py read source/modules/memory/src/components/DynamicLineChart.tsx --start 90 --count 60
```

`--select` selects JSON object keys/list indices. Protocol trace without --field has items; field trace has chains and items. Use `python workbench.py query impact --help` for exact CLI syntax. impact uses --name for a symbol; assets uses --target. resource defaults to a bounded summary; --details expands expressions. Source reads show original line numbers. You may inspect the entire selected-source file through successive reads. If output is large, select a narrower field. Runtime records are materialized in runtime.json from the same unified runs query; no record store is needed in this bundle. observed_dispatch_targets identifies implementations actually observed in those original runs.

Write answers.json and answers.md only under output/. For each question, include concrete findings, evidence paths with original source lines or JSON paths, and remaining unknowns. Cite query paths/conditions as well as source when tracing. Record tool issues accurately. Token/context counts are not exposed by this helper; do not estimate them. Read START.md, ai-tasks.json and bundle.json directly as setup; all subsequent evidence reads go through workbench.
''',encoding='utf-8')
    return {'directory':output.name,'source_files':len(paths),'graph_nodes':len(graph['nodes'])}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('graph','inventory','source','runtime-store','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--catalog',type=Path)
    p.add_argument('--tasks',type=Path)
    a=p.parse_args();print(json.dumps(build(a.graph,a.inventory,a.source,a.runtime_store,a.output,a.catalog,a.tasks)))
