"""Unpack official Rust component archives without running system installers."""
import argparse
import json
from pathlib import Path
import re
import shutil
import tarfile
import urllib.request


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--version',required=True);ap.add_argument('--target',required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version) or not re.fullmatch(r'[a-z0-9_-]+',args.target):
        ap.error('Use a fixed release version and target triple')
    base=args.output.resolve()
    if base.exists():ap.error('Choose a new output directory')
    base.mkdir(parents=True);records=[]
    items=[(f'{name}-{args.version}-{args.target}',name if name!='rust-std' else f'rust-std-{args.target}')
           for name in ('cargo','rustc','rust-std')]+[(f'rust-src-{args.version}','rust-src')]
    for package,component in items:
        url='https://static.rust-lang.org/dist/'+package+'.tar.xz';archive=base/(package+'.tar.xz')
        print('Download '+package,flush=True);urllib.request.urlretrieve(url,archive);count=0
        with tarfile.open(archive,'r:xz') as tar:
            for member in tar:
                bits=Path(member.name).parts
                if len(bits)<3 or bits[0]!=package or bits[1]!=component:continue
                dest=(base/'portable'/Path(*bits[2:])).resolve()
                if not dest.is_relative_to(base/'portable'):raise ValueError('Unsafe archive path')
                if member.isdir():dest.mkdir(parents=True,exist_ok=True)
                elif member.isfile():
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    with tar.extractfile(member) as source,dest.open('wb') as output:shutil.copyfileobj(source,output)
                    if member.mode&0o111:dest.chmod(dest.stat().st_mode|0o111)
                    count+=1
                else:raise ValueError('Unexpected archive member type')
        records.append({'component':component,'url':url,'files':count});print('Extracted '+str(count)+' files',flush=True)
    (base/'installation.json').write_text(json.dumps({'version':args.version,
        'kind':'portable official component archives; no installers run','components':records},indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
