"""Cargo-owned crate discovery and explicit source-only rust-analyzer contexts.

Cargo metadata supplies targets and local dependencies. No dependency downloads,
build scripts, proc macros or analyzed binaries are executed by this module.
"""
from __future__ import annotations

import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def binary(name, explicit=None):
    value=explicit or os.environ.get('PROJECT_MAP_'+name.upper().replace('-','_')) or shutil.which(name)
    return str(Path(value).resolve()) if value else None


def tool_output(command,root,timeout=45):
    result=subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
    if result.returncode:raise ValueError(result.stderr.strip() or 'Tool command failed')
    return result.stdout


def relative(path,root):
    target=Path(path).resolve()
    if not target.is_relative_to(root):raise ValueError('Cargo target/dependency outside committed export')
    return target.relative_to(root).as_posix()


def discover(root,paths,*,cargo=None):
    root=Path(root).resolve();paths=set(paths);cargo=binary('cargo',cargo)
    manifests=sorted(p for p in paths if Path(p).name=='Cargo.toml')
    result={'packages':[],'diagnostics':[],'metadata_mode':'offline_no_deps',
        'external_dependency_graph_resolved':False,'build_scripts_executed':False,'workspaces':[]}
    if not cargo:
        result['diagnostics'].append({'kind':'rust_cargo_missing','required':True});return result
    result['cargo_version']=tool_output([cargo,'--version'],root).strip()
    packages={};covered=set()
    for manifest in manifests:
        if manifest in covered:continue
        relative(root/manifest,root)
        try:
            metadata=json.loads(tool_output([cargo,'metadata','--format-version','1','--no-deps','--offline',
                '--manifest-path',str(root/manifest)],(root/manifest).parent))
            workspace=relative(Path(metadata['workspace_root'])/'Cargo.toml',root)
            if workspace not in paths:raise ValueError('Cargo workspace manifest was not selected')
            if workspace not in result['workspaces']:result['workspaces'].append(workspace)
            covered.add(workspace)
            for package in metadata['packages']:
                item={k:package.get(k) for k in ('name','version','edition','features')}
                item['manifest']=relative(package['manifest_path'],root)
                if item['manifest'] not in paths:raise ValueError('Cargo package manifest was not selected')
                item['targets']=[];item['dependencies']=[]
                for target in package['targets']:
                    location=relative(target['src_path'],root)
                    item['targets'].append({'name':target['name'],'path':location,'edition':target['edition'],
                        'kind':target['kind'],'required_features':target.get('required-features',[]),
                        'input':location in paths})
                for dependency in package['dependencies']:
                    row={k:dependency.get(k) for k in ('name','rename','req','kind','optional','uses_default_features','features','target','source')}
                    if dependency.get('path'):row['path']=relative(dependency['path'],root)
                    item['dependencies'].append(row)
                packages[item['manifest']]=item;covered.add(item['manifest'])
        except (ValueError,OSError,subprocess.TimeoutExpired) as error:
            result['diagnostics'].append({'kind':'rust_cargo_metadata_error','path':manifest,'message':str(error),'required':True})
    result['packages']=[packages[p] for p in sorted(packages)]
    return result


def cargo_options(context, *, sysroot=None, no_deps=False, locked=False):
    """Delegate feature/dependency/cfg resolution to rust-analyzer's Cargo loader."""
    result={'buildScripts':{'enable':False},'noDeps':no_deps,
        'noDefaultFeatures':True,'features':context['features'],'target':context['target'],
        'cfgs':['debug_assertions' if context['debug_assertions'] else '!debug_assertions','!miri'],
        'metadataExtraArgs':['--offline']+(['--locked'] if locked else [])}
    if sysroot:result['sysroot']=str(Path(sysroot).resolve())
    return result


def configuration_matrix(root,paths,metadata,*,rustc=None,max_feature_sets=32,max_contexts=256):
    """Enumerate source-mentioned OS and package features within explicit budgets.

    Enumeration is an analysis matrix, not a list of supported product builds.
    Non-OS cfg predicates and budget omissions remain required gaps.
    """
    root=Path(root).resolve();rustc=binary('rustc',rustc);diagnostics=[]
    if not rustc:return [],[{'kind':'rust_compiler_context_missing','required':True}]
    version=tool_output([rustc,'-vV'],root)
    host=re.search(r'(?m)^host: (.+)$',version)[1];arch=host.split('-')[0]
    texts='\n'.join((root/p).read_text(encoding='utf-8') for p in paths if p.endswith('.rs') or Path(p).name=='Cargo.toml')
    mentioned=set(re.findall(r'target_os\s*=\s*["\']([^"\']+)',texts))
    triples=tool_output([rustc,'--print','target-list'],root).splitlines()
    targets=[host]
    for operating_system in sorted(mentioned):
        # rustc validates cfg below. Prefer the host arch and common ABI, keeping
        # every source-mentioned OS represented without business names.
        options=[t for t in triples if t.startswith(arch+'-') and
            (operating_system in t.split('-') or operating_system=='macos' and 'darwin' in t)]
        choice=host if host in options else next((t for t in options if t.endswith(('gnu','msvc','darwin'))),options[0] if options else None)
        if choice and choice not in targets:targets.append(choice)
        if not choice:diagnostics.append({'kind':'rust_source_os_context_unavailable','target_os':operating_system,'required':True})
    observed_features=set(re.findall(r'feature\s*=\s*["\']([^"\']+)',texts))
    features=sorted({p['name']+'/'+f for p in metadata['packages'] for f in (p.get('features') or {})
        if f in observed_features or any(f in t['required_features'] for t in p['targets'])})
    omitted=[p['name']+'/'+f for p in metadata['packages'] for f in (p.get('features') or {})
        if p['name']+'/'+f not in features]
    if omitted:diagnostics.append({'kind':'rust_manifest_features_not_individually_varied','features':omitted,'required':True})
    total=2**len(features)
    if total>max_feature_sets:
        feature_sets=[[]]+[[f] for f in features]+[features]
        diagnostics.append({'kind':'rust_feature_context_budget','total_feature_sets':total,'required':True})
    else:feature_sets=[list(c) for n in range(len(features)+1) for c in itertools.combinations(features,n)]
    contexts=[]
    for target in targets:
        flags=tool_output([rustc,'--print','cfg','--target',target],root).splitlines()
        for debug in (False,True):
            cfg=[f for f in flags if f!='debug_assertions']+(['debug_assertions'] if debug else [])
            for selected in feature_sets:
                if len(contexts)>=max_contexts:
                    diagnostics.append({'kind':'rust_analysis_context_budget','required':True});return contexts,diagnostics
                contexts.append({'target':target,'debug_assertions':debug,'features':selected,'cfg':cfg,
                    'basis':'rustc_target_cfg_and_enumerated_package_features','supported_product_mode':'not_proven'})
    for package in metadata['packages']:
        for target in package['targets']:
            if 'custom-build' in target['kind']:
                diagnostics.append({'kind':'rust_build_script_outputs_not_replayed','path':target['path'],'required':True})
    for path in paths:
        if not path.endswith('.rs'):continue
        source=(root/path).read_text(encoding='utf-8')
        for match in re.finditer(r'\b(target_arch|target_env|target_feature|target_pointer_width)\s*=\s*"([^"]+)"',source):
            diagnostics.append({'kind':'rust_non_os_cfg_value_not_varied','path':path,'line':source[:match.start()].count('\n')+1,
                'predicate':match[1],'value':match[2],'required':True})
        if re.search(r'#\s*\[\s*cfg_attr\b',source):
            diagnostics.append({'kind':'rust_cfg_attr_context_requires_expansion','path':path,'required':True})
    return contexts,diagnostics
