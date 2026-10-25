"""Run the existing composed field query outside the interactive navigation process."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters.project_query import ProjectQuery


def main():
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    graph=json.loads(Path(request['graph']).read_text(encoding='utf-8'))
    if graph['snapshot']!=request['snapshot'] or graph['source_commit']!=request['source_commit']:
        raise ValueError('Field query graph differs from active workspace version')
    result=ProjectQuery(graph).trace(request['start'],field=request['field'],limit=request['limit'],depth=request['depth'])
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
