"""Extract syntax supplements for a pinned file manifest using Tree-sitter."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.syntax_supplement import extract, VERSION


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--parser-cache',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    source=args.source.resolve()
    output=args.output.resolve()
    if output.exists() or output.is_relative_to(source) or output.is_relative_to(ROOT):
        raise ValueError('Use a new output file outside source and research checkouts')
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    expected=manifest['source_commit']
    actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip()
    if actual!=expected or dirty:raise ValueError('Source must be at clean manifest commit')
    import tree_sitter_language_pack as pack
    pack.configure(pack.PackConfig(cache_dir=str(args.parser_cache.resolve())))
    parsers={}
    records=[]
    files=[]
    for item in manifest['files']:
        relative=item['path']
        path=(source/relative).resolve()
        if not path.is_relative_to(source):raise ValueError('Manifest path escapes source')
        data=path.read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(data).hexdigest()!=item['sha256_lf_utf8']:
            raise ValueError(f'Hash mismatch: {relative}')
        language={'.h':'cpp','.hpp':'cpp','.cpp':'cpp','.ts':'typescript','.tsx':'tsx'}.get(path.suffix)
        if language is None:
            files.append({'path':relative,'status':'outside_supported_languages'})
            continue
        if language not in parsers:parsers[language]=pack.get_parser(language)
        try:
            record=extract(data,relative,language,parsers[language])
        except UnicodeDecodeError:
            files.append({'path':relative,'status':'invalid_utf8'})
            continue
        records.append(record)
        files.append({'path':relative,'status':'syntax_errors' if record['diagnostics'] else 'parsed',
                      'diagnostics':record['diagnostics']})
    result={'schema_version':1,'source_commit':expected,'extractor_version':VERSION,
            'packages':{p:importlib.metadata.version(p) for p in ('tree-sitter','tree-sitter-language-pack')},
            'manifest_sha256':hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            'coverage':files,'records':records}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'files':len(files),'parsed_records':len(records),
           'symbols':sum(len(r['symbols']) for r in records),
           'calls_unresolved':sum(len(r['calls']) for r in records),
           'property_bindings':sum(len(r['bindings']) for r in records),
           'files_with_diagnostics':sum(bool(r['diagnostics']) for r in records)}))


if __name__=='__main__':main()
