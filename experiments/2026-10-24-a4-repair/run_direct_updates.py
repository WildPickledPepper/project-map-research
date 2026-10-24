"""Reuse actual refresh controls with direct platform sends as the entry."""
import argparse
import importlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

controls = importlib.import_module('experiments.2026-10-24-a4.run_updates')
controls.CLIENT = '''declare const channel:WebSocket;
export function entry(){channel.send(JSON.stringify({wireTag:'a4/one',space:'north'}));}
'''

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--typescript', type=Path, required=True)
    a = p.parse_args()
    result = controls.run(a.output.resolve(), a.typescript.resolve())
    result['fixture_origin'] = 'authored_direct_platform_transport_without_property_binding'
    (a.output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
