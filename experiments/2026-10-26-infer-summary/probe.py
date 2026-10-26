"""Execute one upstream compositional candidate and inspect its exported schema."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('bounded_native',ROOT/'experiments/2026-10-26-native-budget/diagnose.py')
MONITOR=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MONITOR)


def walk(value):
    yield value
    if isinstance(value,dict):
        for item in value.values():yield from walk(item)
    elif isinstance(value,list):
        for item in value:yield from walk(item)


def inspect_summaries(filename):
    data=json.loads(filename.read_text())
    if not isinstance(data,list):raise ValueError('Expected upstream procedure summary list')
    records=[]
    for raw in data:
        if not isinstance(raw,list) or len(raw)!=2:raise ValueError('Unexpected procedure record')
        payload=dict(raw[1]);pulse=payload.get('pulse')
        states=[item for item in walk(pulse) if isinstance(item,dict) and {'pre','post'}<=item.keys()]
        records.append({'procedure':raw[0],'pulse_summary_present':pulse is not None,
                        'pre_post_states':len(states),
                        'state_fields':sorted({k for state in states for k in state}),
                        'opaque_values':sum(v=='<opaque>' for v in walk(pulse) if isinstance(v,str))})
    return {'schema':'infer-summary-schema-probe/1','procedures':records,'procedure_count':len(records),
            'procedures_with_states':sum(r['pre_post_states']>0 for r in records),
            'generic_valueflow_admitted':False,'schema_presence_is_not_semantic_acceptance':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--infer',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    infer=str(args.infer.resolve());results=[]
    def execute(command,folder):
        receipt=MONITOR.bounded(command,folder,seconds=300,memory_gib=4)
        receipt['phase_scope']='external Infer command; process-tree sampling, no internal stage markers'
        (folder/'resources.json').write_text(json.dumps(receipt,indent=2))
        if receipt['exit_code']:raise RuntimeError('Candidate command failed: '+folder.name)
        return receipt
    execute([infer,'--version'],args.output/'version')
    for layout,header,sources in [('separated','include','src'),('nested','packages/common/api','packages/worker/impl')]:
        folder=args.output/layout;folder.mkdir();workspace=folder/'workspace';workspace.mkdir()
        (workspace/header).mkdir(parents=True);(workspace/sources).mkdir(parents=True)
        for name in ('effects.hpp','effects.cpp','client.cpp'):
            destination=workspace/(header if name.endswith('.hpp') else sources)/name
            shutil.copyfile(Path(__file__).with_name(name),destination)
        commands=[{'directory':str(workspace.resolve()),'file':str((workspace/sources/name).resolve()),
                   'arguments':['clang++','-std=c++17','-I'+str((workspace/header).resolve()),'-c',
                                str((workspace/sources/name).resolve()),'-o',str((workspace/(name+'.o')).resolve())]}
                  for name in ('effects.cpp','client.cpp')]
        database=workspace/'compile_commands.json';database.write_text(json.dumps(commands,indent=2))
        captured=folder/'infer-out'
        execute([infer,'capture','--results-dir',str(captured),'--compilation-database',str(database),'--jobs','1'],folder/'capture')
        execute([infer,'analyze','--results-dir',str(captured),'--pulse-only','--jobs','1'],folder/'analyze')
        execute([infer,'debug','--results-dir',str(captured),'--procedures','--procedures-summary-json','--dump-json-summaries'],folder/'export')
        result=inspect_summaries(captured/'all_summaries.json');result['layout']=layout
        (folder/'schema-result.json').write_text(json.dumps(result,indent=2));results.append(result)
    (args.output/'result.json').write_text(json.dumps({'layouts':results,'whole_R0_R1_accepted':False},indent=2))
    print(json.dumps({'layouts':[{k:r[k] for k in ('layout','procedure_count','procedures_with_states')} for r in results]}))


if __name__=='__main__':main()
