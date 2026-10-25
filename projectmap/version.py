"""Source revision identity for checkouts and isolated wheels."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
INPUTS=['adapters','scripts','projectmap','requirements-*.txt','package.json','package-lock.json','pyproject.toml','setup.py']


def rules_version(require_clean=False):
    if (ROOT/'.git').exists():
        if require_clean and subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain',
                '--untracked-files=all','--',*INPUTS],text=True).strip():
            raise ValueError('Commit tool code before recording a versioned build')
        revision=subprocess.check_output(['git','-C',str(ROOT),'log','-1','--format=%H','--',*INPUTS],text=True).strip()
        if not revision:raise ValueError('No committed tool version')
        return revision
    path=Path(__file__).with_name('_build_info.json')
    if not path.is_file():raise ValueError('Install a built wheel or run from the tool Git checkout')
    return json.loads(path.read_text(encoding='utf-8'))['rules_commit']
