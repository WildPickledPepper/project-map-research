"""Execute the installed native SVF distribution on compiler capture receipts."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def analyze(receipt_file,*,bounded=False):
    receipt=json.loads(receipt_file.read_text());folder=receipt_file.parent
    if receipt['schema']!='cargo-svf-capture/1':raise ValueError('Expected native compiler receipt')
    bitcode=(folder/receipt['bitcode']).resolve()
    if not bitcode.is_relative_to(folder.resolve()):raise ValueError('Bitcode escaped capture')
    command=[sys.executable,'-m','adapters.svf_export','--bitcode',str(bitcode),
            '--single-process-points','--output',str(folder/'native.json'),
            '--source-root',receipt['source_root'],'--source-directory',receipt['source_directory'],
            '--source-commit',receipt['source_commit'],'--context',receipt['context'],
            '--module',receipt['module'],'--language',receipt['language'],'--compiler-receipt',str(receipt_file)]
    if bounded:
        path=Path(__file__).resolve().parents[1]/'experiments/2026-10-26-native-budget/diagnose.py'
        spec=importlib.util.spec_from_file_location('native_budget',path)
        monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)
        resource=monitor.bounded(command,folder/'native-run',seconds=600,memory_gib=13)
        if resource['exit_code']:raise RuntimeError('Native analysis stopped: '+str(resource['stop_reason']))
        receipt['native_resource_receipt']='native-run/resources.json'
    else:
        with (folder/'export.log').open('w') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    native=json.loads((folder/'native.json').read_text())
    if any(native.get(key)!=receipt[key] for key in ('source_commit','context','module','language')):
        raise ValueError('Native export differs from its compiler receipt')
    if native.get('points_to_identity_status')!='same_process_native_ids' or not native.get('same_process_endpoints_checked'):
        raise ValueError('Native export has not verified same-process endpoints')
    receipt['analysis_executed']=True
    receipt['native_analysis_runs']=1
    receipt['points_to_identity_status']='same_process_native_ids'
    (folder/'analysis-receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps({'module':receipt['module'],'context':receipt['context'],'native_export':'ready'}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--bounded',action='store_true')
    args=p.parse_args();receipts=sorted(args.input.rglob('receipt.json'))
    if not receipts:raise ValueError('No native compiler receipts')
    for receipt in receipts:analyze(receipt,bounded=args.bounded)


if __name__=='__main__':main()
