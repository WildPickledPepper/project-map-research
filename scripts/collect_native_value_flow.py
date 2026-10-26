"""Import revision-bound native value-flow exports into provider capture groups."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from adapters.native_value_flow import normalize
from adapters.repository_discovery import discover


def collect(inputs, *, paths, source_commit, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    groups=defaultdict(list)
    for filename in inputs:
        data=json.loads(Path(filename).read_text(encoding='utf-8'))
        schemas={'svf-native-export/1':'svf','rapx-native-export/1':'rapx'}
        if data.get('schema') not in schemas:raise ValueError('Unrecognized native export')
        provider=schemas[data['schema']];context=data.get('context')
        if not context:raise ValueError('Native compilation context required')
        facts=normalize(data,provider=provider,paths=paths,source_commit=source_commit,context=context)
        groups[provider,context].append(facts)
    if not groups:raise ValueError('Native exports required')
    for (provider,context),modules in groups.items():
        reference=groups.get(('rapx',context))
        if provider=='svf' and reference and any(n['language']=='rust' for f in modules for n in f['nodes']):
            expected={n['path'] for f in reference for n in f['nodes'] if n['path']}
            actual={n['path'] for f in modules for n in f['nodes'] if n['path']}
            if actual-expected:
                raise ValueError('Native Rust providers selected different cfg sources: '+context+' '+str(sorted(actual-expected)))
    captures=[];reports=[]
    for ordinal,((provider,context),modules) in enumerate(sorted(groups.items())):
        merged={k:[] for k in ('nodes','edges','diagnostics','coverage','limits')}
        ids=set()
        for facts in modules:
            new={n['id'] for n in facts['nodes']}
            if new & ids:raise ValueError('Duplicate native module/context identity')
            ids.update(new)
            for key in merged:merged[key].extend(facts[key])
        merged['components']={'provider':provider,'adapter':'native_value_flow/1',
            'source_commit':source_commit,'context':context,'modules':[f['components'] for f in modules]}
        missing={e[k] for e in merged['edges'] for k in ('source','target')} - ids
        if missing:raise ValueError('Native edge endpoint absent: '+str(sorted(missing)[:3]))
        directory=str(ordinal)+'-'+provider;(output/directory).mkdir()
        (output/directory/'facts.json').write_text(json.dumps(merged,separators=(',',':')),encoding='utf-8')
        captures.append({'provider':provider,'context_key':context,'source_commit':source_commit,'directory':directory})
        reports.append({'provider':provider,'context':context,'modules':len(modules),'nodes':len(ids),
            'edges':dict(Counter(e['kind'] for e in merged['edges'])),
            'source_paths':sorted({n['path'] for n in merged['nodes'] if n['path']}),
            'diagnostics':len(merged['diagnostics']),'semantic_completeness':'requires_independent_checks'})
    result={'schema':'native-value-flow-captures/1','source_commit':source_commit,
        'captures':captures,'results':reports,'runtime_execution':'not_observed','whole_R0_R1_accepted':False}
    (output/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native',type=Path,action='append',required=True)
    p.add_argument('--repository',type=Path,required=True);p.add_argument('--revision',required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    discovery=discover(args.repository,args.revision)
    result=collect(args.native,paths=[r['path'] for r in discovery['files'] if r['eligible']],
                   source_commit=discovery['source_commit'],output=args.output)
    print(json.dumps(result['results']))


if __name__=='__main__':main()
