"""Persistent worker for source-only Python discovery facts; never imports target modules."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.python_facts import syntax_facts


def main():
    root=Path(sys.argv[1]).resolve()
    for line in sys.stdin:
        try:
            request=json.loads(line);file=(root/request['path']).resolve()
            if not file.is_relative_to(root):raise ValueError('Unsafe input')
            result={'ok':True,'facts':syntax_facts(file.read_bytes(),request['path'])}
        except Exception as error:result={'ok':False,'error':type(error).__name__+': '+str(error)}
        print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
