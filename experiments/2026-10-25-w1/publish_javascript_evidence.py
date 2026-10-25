"""Project executed JS results into portable evidence; never used by graph generation."""
import argparse
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    def load(name):return json.loads((args.results/name).read_text(encoding='utf-8'))
    def save(name,value):
        path=args.output/name
        if path.exists():raise ValueError('Evidence already exists: '+str(path))
        path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def project_score(value):
        result={k:value[k] for k in ('schema','source_commit','snapshot','build_version','passed','runtime_execution','whole_G02_accepted')}
        result['checks']=[]
        for check in value['checks']:
            row={k:v for k,v in check.items() if k!='result'}
            if 'result' in check:
                row['result']={k:check['result'][k] for k in ('found','direction','items','stop_reason','visited_nodes','examined_edges','runtime_execution')}
            result['checks'].append(row)
        return result
    save('javascript-chain.json',project_score(load('w1-js-chain-score-01.json')))
    save('javascript-repository-chain.json',project_score(load('w1-js-repository-score-01.json')))
    save('javascript-repository-scope.json',load('w1-js-repository-scope-02.json'))
    save('javascript-installed.json',load('w1-js-installed-smoke-02/result.json'))
    print('Saved four portable projections; raw graphs and command logs remain outside Git.')


if __name__=='__main__':main()
