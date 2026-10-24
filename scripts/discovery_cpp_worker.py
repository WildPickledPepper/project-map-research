"""Persistent, replaceable worker for file-local C++ facts."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import tree_sitter_language_pack as pack
    from adapters.discovery_facts import cpp_facts
    if os.environ.get('PROJECT_MAP_PARSER_CACHE'):
        pack.configure(pack.PackConfig(cache_dir=os.environ['PROJECT_MAP_PARSER_CACHE']))
    parser = pack.get_parser('cpp'); root = Path(sys.argv[1]).resolve()
    for line in sys.stdin:
        try:
            request = json.loads(line); file = (root/request['path']).resolve()
            if not file.is_relative_to(root): raise ValueError('Unsafe input')
            facts = cpp_facts(file.read_bytes(), request['path'], parser)
            result = {'ok': True, 'facts': facts}
        except Exception as error:
            result = {'ok': False, 'error': type(error).__name__ + ': ' + str(error)}
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
