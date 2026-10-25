"""Capture a native Cargo build in an independent selected-input copy.

This explicit native-build interface runs Cargo build (including its build
scripts/proc macros), captures its JSON, and never runs a product executable.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
from adapters.cargo_file_api import normalize
from adapters.rust_project import binary
from adapters.snapshot_inputs import validate_path


def read_messages(path):
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            if len(line)>16*1024*1024:raise ValueError('Cargo stdout line budget')
            if not line.lstrip().startswith('{'):continue
            try:record=json.loads(line)
            except ValueError:continue
            yield record


def capture(source,paths,*,output,source_commit,expected_commit,context_key,cwd='.',manifest=None,target=None,
            profile='release',features=(),no_default_features=False,target_directory=None,environment=None,
            cargo=None,rustc=None,timeout=180):
    source=Path(source).resolve();output=Path(output).resolve();paths=list(paths)
    if output.exists() or output.is_relative_to(source):raise ValueError('Choose a new native build output outside the input export')
    if not source_commit or source_commit!=expected_commit:raise ValueError('Native source revision mismatch')
    if not paths or len(paths)!=len(set(paths)):raise ValueError('Selected native build inputs must be unique and nonempty')
    for name in paths:
        validate_path(name);path=(source/name).resolve()
        if not path.is_relative_to(source) or not path.is_file():raise ValueError('Missing or unsafe native input')
    cargo=binary('cargo',cargo);rustc=binary('rustc',rustc)
    if not cargo or not rustc:raise ValueError('Cargo and rustc are required')
    output.mkdir(parents=True);root=output/'source';root.mkdir()
    for name in paths:
        dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,dest)
    working=(root/cwd).resolve()
    if not working.is_relative_to(root) or not working.is_dir():raise ValueError('Native working directory outside copied source')
    if manifest:
        manifest_path=(root/manifest).resolve()
        if not manifest_path.is_relative_to(root) or manifest not in paths:raise ValueError('Manifest must be a selected source input')
    else:manifest_path=None
    # Cargo searches ancestors as well as CARGO_HOME. External ancestor configs
    # would make this recorded build depend on an unrecorded machine setting.
    for parent in root.parents:
        if any((parent/'.cargo'/n).is_file() for n in ('config','config.toml')):
            raise ValueError('External Cargo ancestor configuration requires an explicit context')
    if target is None:
        for parent in [working,*working.parents]:
            if not parent.is_relative_to(root):break
            configs=[parent/'.cargo'/n for n in ('config','config.toml')]
            for config in configs:
                if config.is_file() and 'target' in tomllib.loads(config.read_text(encoding='utf-8')).get('build',{}):
                    raise ValueError('Configured build.target requires an explicit native target')
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(('CARGO','RUST'))}
    # Keep rustup's explicitly chosen toolchain/location when cargo/rustc are
    # dispatch shims. Compile flags and Cargo settings remain isolated below.
    toolchain_selector={k:os.environ[k] for k in ('RUSTUP_TOOLCHAIN','RUSTUP_HOME') if k in os.environ}
    env.update(toolchain_selector)
    supplied=dict(environment or {})
    if any(k.upper() in {'CARGO_HOME','RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTUP_TOOLCHAIN','CARGO_BUILD_TARGET'} for k in supplied):
        raise ValueError('Toolchain and target settings use explicit capture arguments')
    env.update(supplied)
    env.update(CARGO_HOME=str(output/'cargo-home'),RUSTC=rustc,RUSTC_WRAPPER='',RUSTC_WORKSPACE_WRAPPER='',CARGO_TERM_COLOR='never')
    directory=target_directory if target_directory is not None else supplied.get('CARGO_TARGET_DIR')
    if directory is not None:
        resolved=(working/directory).resolve()
        if not resolved.is_relative_to(output):raise ValueError('Native target directory outside capture workspace')
    def run(name,command,*,context_env=env):
        out=output/(name+'.stdout');err=output/(name+'.stderr')
        with out.open('w',encoding='utf-8') as stdout,err.open('w',encoding='utf-8') as stderr:
            result=subprocess.run(command,cwd=working,env=context_env,stdout=stdout,stderr=stderr,timeout=timeout)
        return result.returncode,out,err
    def query(name,command):
        status,out,err=run(name,command)
        if status:raise ValueError('Native query failed: '+name+'; see recorded stderr')
        return out.read_text(encoding='utf-8')
    cargo_version=query('cargo-version',[cargo,'--version']).strip();rustc_version=query('rustc-version',[rustc,'-vV']).strip()
    host=next((line[6:].strip() for line in rustc_version.splitlines() if line.startswith('host: ')),None)
    if not host:raise ValueError('Native rustc host not reported')
    selected_target=target or host
    host_cfg=query('host-cfg',[rustc,'--print','cfg','--target',host]).splitlines()
    target_cfg=query('target-cfg',[rustc,'--print','cfg','--target',selected_target]).splitlines()
    metadata_command=[cargo,'metadata','--format-version','1','--no-deps','--offline']
    if manifest_path:metadata_command+=['--manifest-path',str(manifest_path)]
    metadata_env=dict(env)
    if target_directory is not None:metadata_env['CARGO_TARGET_DIR']=str(target_directory)
    code,metadata_path,_=run('metadata',metadata_command,context_env=metadata_env)
    if code:raise ValueError('Native Cargo metadata failed; see recorded stderr')
    metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
    native_target_dir=Path(metadata['target_directory']).resolve()
    if not native_target_dir.is_relative_to(output):raise ValueError('Native metadata target directory outside capture workspace')
    command=[cargo,'build','--offline','--message-format=json']
    if manifest_path:command+=['--manifest-path',str(manifest_path)]
    if target:command+=['--target',target]
    if profile=='release':command+=['--release']
    elif profile not in {None,'dev'}:command+=['--profile',profile]
    if features:command+=['--features',','.join(features)]
    if no_default_features:command+=['--no-default-features']
    if target_directory is not None:command+=['--target-dir',str(target_directory)]
    status,stream,_=run('build',command)
    facts=normalize(metadata,read_messages(stream),repository=root,source_commit=source_commit,expected_commit=expected_commit,
        returncode=status,context_key=context_key,host_target=host,target=selected_target,host_cfg=host_cfg,target_cfg=target_cfg,
        cargo_version=cargo_version,rustc_version=rustc_version)
    selected_manifest=manifest_path or next((p/'Cargo.toml' for p in [working,*working.parents]
        if p.is_relative_to(root) and (p/'Cargo.toml').is_file()),None)
    source_request={'cwd':working.relative_to(root).as_posix(),
        'manifest':selected_manifest.relative_to(root).as_posix() if selected_manifest else None,
        'profile':profile or 'dev','features':sorted(set(features)),'no_default_features':no_default_features,
        'target_mode':'explicit' if target else 'default','target':target}
    receipt={'schema':'cargo-native-capture/1','source_commit':source_commit,'context_key':context_key,'command':command,
        'metadata_command':metadata_command,'selected_paths':paths,'recorded_repository':str(root),'target_directory':str(native_target_dir),
        'host_target':host,'target':selected_target,'host_cfg':host_cfg,'target_cfg':target_cfg,
        'cargo_version':cargo_version,'rustc_version':rustc_version,'returncode':status,'profile_requested':profile,
        'features_requested':list(features),'no_default_features':no_default_features,'environment':supplied,
        'target_mode':'explicit' if target else 'native_host_default_without_build_target_config_or_environment',
        'status':facts['native_context']['status'],'toolchain_selector':toolchain_selector,'source_request':source_request,
        'product_executable_run':False,'file_hash_verification':'not_run_per_user_preference'}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return facts,receipt
