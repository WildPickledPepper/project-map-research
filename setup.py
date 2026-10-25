"""Stamp wheel provenance without including research or benchmark answers."""
import json
from pathlib import Path
import subprocess
from setuptools import setup
from setuptools.command.build_py import build_py


class VersionedBuild(build_py):
    def find_package_modules(self, package, package_dir):
        modules=super().find_package_modules(package,package_dir)
        if package=='scripts':
            allowed={'build_project_snapshot','build_chain_closure_graph','build_fact_graph'}
            modules=[item for item in modules if item[1] in allowed]
        return modules

    def run(self):
        root=Path(__file__).resolve().parent
        inputs=['adapters','scripts','projectmap','requirements-*.txt','package.json','package-lock.json','pyproject.toml','setup.py']
        if (root/'.git').exists():
            dirty=subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=all','--',*inputs],text=True).strip()
            if dirty:raise RuntimeError('Commit tool code before building a versioned wheel')
            rules=subprocess.check_output(['git','-C',str(root),'log','-1','--format=%H','--',*inputs],text=True).strip()
        else:
            info=root/'projectmap/_build_info.json'
            if not info.is_file():raise RuntimeError('Build from the tool Git checkout')
            rules=json.loads(info.read_text(encoding='utf-8'))['rules_commit']
        super().run()
        target=Path(self.build_lib)/'projectmap/_build_info.json'
        target.write_text(json.dumps({'rules_commit':rules,'distribution':'project-map-tool','version':'0.2.0',
            'benchmark_materials_included':False},indent=2)+'\n',encoding='utf-8')


setup(cmdclass={'build_py':VersionedBuild})
