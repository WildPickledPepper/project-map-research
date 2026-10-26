"""Execute the installed native SVF distribution on compiler capture receipts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def analyze(receipt_file):
    receipt=json.loads(receipt_file.read_text());folder=receipt_file.parent
    if receipt['schema']!='cargo-svf-capture/1':raise ValueError('Expected native compiler receipt')
    bitcode=(folder/receipt['bitcode']).resolve()
    if not bitcode.is_relative_to(folder.resolve()):raise ValueError('Bitcode escaped capture')
    import pysvf
    wpa=next((Path(pysvf.__file__).parent).rglob('wpa'))
    with (folder/'analysis.log').open('w') as log:
        subprocess.run([str(wpa),'-ander','-svfg','-write-ander='+str(folder/'points-to.txt'),str(bitcode)],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    with (folder/'export.log').open('w') as log:
        subprocess.run([sys.executable,'-m','adapters.svf_export','--bitcode',str(bitcode),
            '--native-points',str(folder/'points-to.txt'),'--output',str(folder/'native.json'),
            '--source-root',receipt['source_root'],'--source-directory',receipt['source_directory'],
            '--source-commit',receipt['source_commit'],'--context',receipt['context'],
            '--module',receipt['module'],'--language',receipt['language']],
            stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    receipt['analysis_executed']=True
    (folder/'analysis-receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps({'module':receipt['module'],'context':receipt['context'],'native_export':'ready'}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    args=p.parse_args();receipts=sorted(args.input.rglob('receipt.json'))
    if not receipts:raise ValueError('No native compiler receipts')
    for receipt in receipts:analyze(receipt)


if __name__=='__main__':main()
