"""Prepare the pinned public case with the previously tested CMake experiment."""
import argparse
import io
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
REVISION='d4e8d1cf9f90208bcbe5371c127088f6fd66c688'
DEPENDENCIES=[('libuv','libuv/libuv','0c1fa696aa502eb749c2c4735005f41ba00a27b8'),
 ('uSockets','uNetworking/uSockets','8cd4cb66eb061b2594ca114b9ea1ead64613ad4b'),
 ('uWebSockets','uNetworking/uWebSockets','bc2815d95b6ff4cad0973226d0058eadaaec99ad'),
 ('rapidjson','Tencent/rapidjson','d621dc9e9c77f81e5c8a35b8dcc16dcd63351321')]


def checkout(url,revision,path):
    subprocess.run(['git','init','-q',str(path)],check=True)
    subprocess.run(['git','-C',str(path),'fetch','--depth','1',url,revision],check=True,timeout=180)
    subprocess.run(['git','-C',str(path),'checkout','--detach','-q','FETCH_HEAD'],check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    source=args.output/'repository';checkout('https://gitcode.com/Ascend/msinsight.git',REVISION,source)
    command=[sys.executable,str(ROOT/'experiments/2026-10-25-w1/run_cmake_repository.py'),
        '--source',str(source),'--revision',REVISION,'--subdir','server','--output',str(args.output/'cmake'),
        '--cmake',shutil.which('cmake'),'--make',shutil.which('ninja'),
        '--cc',shutil.which('gcc'),'--cxx',shutil.which('g++')]
    for name,repository,revision in DEPENDENCIES:
        local=args.output/name;checkout('https://github.com/'+repository+'.git',revision,local)
        command+=['--dependency-git','server/third_party/'+name,str(local),revision]
    data=urllib.request.urlopen('https://www.sqlite.org/2024/sqlite-amalgamation-3460100.zip',timeout=60).read()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in ('sqlite3.c','shell.c','sqlite3.h','sqlite3ext.h'):
            member=next(n for n in archive.namelist() if n.endswith('/'+name))
            local=args.output/name;local.write_bytes(archive.read(member))
            destination='server/third_party/sqlite/'+('include/' if name.endswith('.h') else 'src/')+name
            command+=['--dependency-file',destination,str(local)]
    subprocess.run(command,check=True,timeout=600)


if __name__=='__main__':main()
