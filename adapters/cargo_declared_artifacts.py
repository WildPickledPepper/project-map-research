"""Project source Cargo builds onto metadata-owned, conditional binary outputs.

Cargo metadata and rustc print queries run in a selected-input copy. This pass
never compiles a product, executes build scripts or runs proc macros. Output
locations combine Cargo's public profile layout with compiler-reported binary
prefix/suffix and metadata target names; native build reports remain separate.
"""
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import tomllib

from adapters.cargo_file_api import identity,system,link_source_symbols
from adapters.cargo_source_bindings import interpret
from adapters.python_process_values import environment_value
from adapters.rust_project import binary
from adapters.snapshot_inputs import validate_path


ADAPTER_VERSION='source_cargo_declared_binary_projection/0.2.0'
PROBE='__project_map_binary_name_probe'


def merge(left,right,*,join_arrays=False):
    result=dict(left)
    for key,value in right.items():
        if isinstance(value,dict) and isinstance(result.get(key),dict):result[key]=merge(result[key],value,join_arrays=join_arrays)
        elif join_arrays and isinstance(value,list) and isinstance(result.get(key),list):result[key]=result[key]+value
        else:result[key]=value
    return result


def local_configuration(root,cwd,paths):
    """Cargo searches cwd ancestors; extensionless config wins over config.toml."""
    configs=[];value={}
    for directory in reversed([cwd,*cwd.parents]):
        if not directory.is_relative_to(root):continue
        selected=next((p for p in (directory/'.cargo/config',directory/'.cargo/config.toml') if p.is_file()),None)
        if selected is None:continue
        path=selected.relative_to(root).as_posix()
        if path not in paths:raise ValueError('Cargo local configuration outside selected inputs')
        data=tomllib.loads(selected.read_text(encoding='utf-8'))
        if 'include' in data:raise ValueError('Cargo configuration include requires native configuration resolution')
        configs.append(path);value=merge(value,data,join_arrays=True)
    return value,configs


def planned_profile(root,workspace,package,name,configuration):
    profiles=merge(tomllib.loads((root/workspace).read_text(encoding='utf-8')).get('profile',{}),configuration.get('profile',{}))
    defaults={'dev':True,'release':False,'test':True,'bench':False};seen=set()
    def resolve(profile):
        if profile in seen:raise ValueError('Cargo profile inheritance cycle')
        seen.add(profile);data=profiles.get(profile,{})
        if not isinstance(data,dict):raise ValueError('Invalid Cargo profile')
        if profile in defaults:assertions=defaults[profile]
        else:
            parent=data.get('inherits')
            if not isinstance(parent,str):raise ValueError('Custom Cargo profile inheritance unavailable')
            assertions=resolve(parent)
        overrides=data.get('package',{})
        if set(overrides)-{'*',package['name']}:raise ValueError('Cargo package profile override requires package-id resolution')
        merged=merge(merge(data,overrides.get('*',{})),overrides.get(package['name'],{}))
        assertions=merged.get('debug-assertions',assertions)
        if type(assertions) is not bool:raise ValueError('Cargo debug-assertions is not boolean')
        return assertions
    if not re.fullmatch(r'[A-Za-z0-9_-]+',name):raise ValueError('Cargo profile directory is not a simple name')
    return ({'name':name,'test':False,'debug_assertions':resolve(name),'basis':'declared_profile_conditional_on_configuration'},
        {'dev':'debug','test':'debug','bench':'release'}.get(name,name))


def augment(graph,*,root,paths,output,parser,cargo=None,rustc=None,timeout=45):
    if 'cargo_declared_artifacts' in graph:raise ValueError('Cargo declared artifact projection already present')
    root=Path(root).resolve();output=Path(output).resolve();paths=list(paths)
    result={'adapter':ADAPTER_VERSION,'contexts':[],'product_compiled':False,'build_scripts_executed':False,'proc_macros_executed':False}
    graph['cargo_declared_artifacts']=result
    if not any(Path(p).name=='Cargo.toml' for p in paths):return graph
    cargo=binary('cargo',cargo);rustc=binary('rustc',rustc)
    def gap(reason,source=None,**extra):
        graph['diagnostics'].append({'kind':'cargo_declared_artifact_gap','reason':reason,'source':source,'required':True,**extra})
    if not cargo or not rustc:gap('cargo_or_rustc_unavailable');return graph
    if output.exists() or output.is_relative_to(root):raise ValueError('Choose a new Cargo query output outside input tree')
    output.mkdir(parents=True);copy=output/'source';copy.mkdir()
    for p in paths:
        validate_path(p);source=(root/p).resolve()
        if not source.is_relative_to(root) or not source.is_file():raise ValueError('Missing or unsafe Cargo projection input')
        target=copy/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    for parent in copy.parents:
        if any((parent/'.cargo'/p).is_file() for p in ('config','config.toml')):
            gap('external_ancestor_cargo_configuration');return graph
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(('CARGO','RUST'))}
    env.update({k:os.environ[k] for k in ('RUSTUP_HOME','RUSTUP_TOOLCHAIN') if k in os.environ})
    env.update(CARGO_HOME=str(output/'cargo-home'),RUSTC=rustc,RUSTC_WRAPPER='',RUSTC_WORKSPACE_WRAPPER='',CARGO_TERM_COLOR='never')
    commands=[]
    def query(label,command,cwd=copy,environment=env,stdin=None):
        completed=subprocess.run(command,cwd=cwd,env=environment,input=stdin,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
        (output/(label+'.stdout')).write_text(completed.stdout,encoding='utf-8')
        (output/(label+'.stderr')).write_text(completed.stderr,encoding='utf-8')
        commands.append({'label':label,'command':command,'returncode':completed.returncode})
        if completed.returncode:raise ValueError('Native query failed: '+label)
        return completed.stdout
    try:
        cargo_version=query('cargo-version',[cargo,'--version']).strip();rustc_version=query('rustc-version',[rustc,'-vV']).strip()
        host=next((l[6:].strip() for l in rustc_version.splitlines() if l.startswith('host: ')),None)
        if not host:raise ValueError('Native compiler host not reported')
        host_cfg=query('host-cfg',[rustc,'--print','cfg','--target',host]).splitlines();host_system=system(host_cfg)
    except (ValueError,OSError,subprocess.SubprocessError) as error:gap(str(error));return graph
    query_host=host
    hosts={host:(host_cfg,host_system)}
    for analysis in graph['nodes']:
        if (analysis['kind']!='analysis_context' or analysis.get('language')!='rust' or
                analysis.get('basis')!='rustc_target_cfg_and_enumerated_package_features'):continue
        target=analysis.get('target')
        if target in hosts:continue
        try:
            if not isinstance(target,str) or not target:raise ValueError('Source host target unavailable')
            selected_system=system(analysis['cfg'])
            if not selected_system['path_style']:raise ValueError('Source host path style unavailable')
            hosts[target]=(analysis['cfg'],selected_system)
        except (KeyError,ValueError) as error:gap('source_host_context_unavailable',analysis['id'],detail=str(error))
    result['source_host_targets']=list(hosts)
    result['native_query_host_target']=query_host
    effects=[n for n in graph['nodes'] if n['kind']=='python_environment_effect'];cached_targets={};metadata_cache={};covered=set()
    native_configs=[n for n in graph['nodes'] if n['kind']=='build_configuration' and n.get('language')=='cargo' and n.get('state')=='native_build_succeeded']
    from adapters.cargo_source_bindings import mismatches
    def location(path):
        value=Path(path).resolve()
        if not value.is_relative_to(copy):raise ValueError('Cargo query path outside selected source copy')
        return {'root':'source','path':value.relative_to(copy).as_posix()}
    invocations=[n for n in graph['nodes'] if n['kind']=='python_process_invocation']
    work=[(n,t,cfg,sys) for t,(cfg,sys) in hosts.items() for n in invocations]
    for invocation,host,host_cfg,host_system in work:
        host_selection={'name':host_system['name'],'path_style':host_system['path_style']}
        spec=interpret(invocation,effects,host_system=host_selection,input_paths=paths)
        if spec is None:continue
        if len(spec['argv'])>1 and spec['argv'][1]!='build':
            result.setdefault('unprojected_subcommands',[]).append({'source':invocation['id'],
                'command':spec['argv'][1],'source_host_target':host})
            if spec['argv'][1]!='fetch':gap('cargo_subcommand_output_requires_native_capture',invocation['id'],
                command=spec['argv'][1],source_host_target=host)
            continue
        if spec['gaps']:gap('source_build_request_unresolved',invocation['id'],reasons=spec['gaps'],source_host_target=host);continue
        if any(not mismatches(spec,c) for c in native_configs if c.get('source_request') and
               c['target_system']['host_target']==host):
            covered.add(spec['manifest']);continue
        number=len(result['contexts']);request_env=dict(env);cwd=copy/spec['cwd'];conditions=list(spec['conditions'])
        try:
            configuration,configs=local_configuration(copy,cwd,set(paths))
            # Cargo metadata applies selected local target-dir configuration. The
            # known CLI/source value is rebased into this independent copy.
            if spec['target_directory'] is not None:request_env['CARGO_TARGET_DIR']=str(copy/spec['target_directory'])
            alias=environment_value(invocation,effects,'CARGO_BUILD_TARGET_DIR',host_selection)
            if alias['known'] and alias['value'] is not None:raise ValueError('CARGO_BUILD_TARGET_DIR source alias requires native precedence resolution')
            conditions.append({'kind':'source_target_directory_alias_absent_or_nonoverriding','variable':'CARGO_BUILD_TARGET_DIR'})
            cargo_home=environment_value(invocation,effects,'CARGO_HOME',host_selection)
            if cargo_home['known'] and cargo_home['value'] is not None:raise ValueError('Source CARGO_HOME requires explicit configuration context')
            cache_key=(spec['cwd'],spec['manifest'],request_env.get('CARGO_TARGET_DIR'))
            if cache_key not in metadata_cache:
                metadata_cache[cache_key]=json.loads(query('metadata-'+str(len(metadata_cache)),[cargo,'metadata','--format-version','1','--no-deps','--offline',
                    '--manifest-path',str(copy/spec['manifest'])],cwd,request_env))
            metadata=metadata_cache[cache_key];workspace=location(Path(metadata['workspace_root'])/'Cargo.toml')['path']
            covered.update(location(p['manifest_path'])['path'] for p in metadata['packages'])
            covered.add(workspace)
            directory=location(metadata['target_directory'])
            if workspace not in paths:raise ValueError('Cargo workspace manifest outside selected inputs')
            if spec['manifest']==workspace:selected=set(metadata['workspace_default_members'])
            else:selected={p['id'] for p in metadata['packages'] if location(p['manifest_path'])['path']==spec['manifest']}
            if not selected:raise ValueError('Cargo selected package identity unavailable')
            requested=spec['target'] or configuration.get('build',{}).get('target')
            target_mode='explicit' if requested else 'default';targets=requested if isinstance(requested,list) else [requested or host]
            if not all(isinstance(t,str) for t in targets):raise ValueError('Cargo build target is not a string')
            for target in dict.fromkeys(targets):
                if '/' in target or '\\' in target or target.endswith('.json'):raise ValueError('Custom Cargo target requires explicit native target context')
                if target=='host-tuple':target=host
                if target not in cached_targets:
                    index=len(cached_targets);cfg=query('target-cfg-'+str(index),[rustc,'--print','cfg','--target',target]).splitlines()
                    filenames=query('binary-template-'+str(index),[rustc,'--print','file-names','--crate-name',PROBE,'--crate-type','bin','--target',target,'-'],stdin='').splitlines()
                    if len(filenames)!=1 or filenames[0].count(PROBE)!=1 or '/' in filenames[0] or '\\' in filenames[0]:raise ValueError('Native binary filename template unavailable')
                    cached_targets[target]=(system(cfg),filenames[0].split(PROBE))
                target_system,template=cached_targets[target]
                context=identity('source-projection',invocation['id'],host,target,spec['profile'])
                constraints=conditions+[{'kind':'source_build_target_selection_equals_projection','target':target,'target_mode':target_mode},
                    {'kind':'source_build_host_toolchain_matches_projection','host_target':host,'native_query_host_target':query_host},
                    {'kind':'source_compiler_flags_preserve_cargo_binary_output_contract'},
                    {'kind':'source_profile_environment_and_build_script_cfg_match_declared_plan'}]
                system_info={'status':'available','name':target_system['name'],'host_name':host_system['name'],
                    'host_path_style':host_system['path_style'],'target_path_style':target_system['path_style'],
                    'target_arch':target_system['arch'],'host_arch':host_system['arch'],'target':target,'host_target':host,
                    'cross_compiling':host!=target,'basis':'native_rustc_query_with_source_configuration_conditions',
                    'source_host_execution':'not_observed','native_query_host_target':query_host}
                row={'id':context,'kind':'build_configuration','name':'Cargo source build '+spec['profile'],'language':'cargo',
                    'path':spec['manifest'],'line':1,'source_commit':graph['source_commit'],'target_system':system_info,
                    'target_directory':directory,'state':'declared_output_plan','conditions':constraints,
                    'workspace':{'root':'source','path':workspace},
                    'cargo_version':cargo_version,'rustc_version':rustc_version,'runtime_execution':'not_observed',
                    'source_request':{k:spec[k] for k in ('cwd','manifest','profile','features','no_default_features')},'local_configurations':configs}
                row['source_request'].update(target_mode=target_mode,target=target if target_mode=='explicit' else None)
                graph['nodes'].append(row);result['contexts'].append({'key':context,'source_invocation':invocation['id'],
                    'target':target,'target_mode':target_mode,'status':'declared_output_plan'})
                for package in metadata['packages']:
                    if package['id'] not in selected:continue
                    manifest=location(package['manifest_path'])['path']
                    if manifest not in paths:raise ValueError('Cargo package manifest outside selected inputs')
                    profile,profile_directory=planned_profile(copy,workspace,package,spec['profile'],configuration)
                    for native in package['targets']:
                        if set(native['kind'])&{'example','test','bench'}:continue
                        if native['kind']==['custom-build']:
                            gap('build_script_outputs_require_native_build_evidence',context,path=location(native['src_path'])['path']);continue
                        if native['kind']!=['bin']:
                            gap('non_binary_target_output_not_projected',context,target_kind=native['kind']);continue
                        source=location(native['src_path'])
                        if source['path'] not in paths:raise ValueError('Cargo target source outside selected inputs')
                        uid=identity(context,'target',manifest,native['name'],source['path'])
                        guards=constraints+[{'kind':'cargo_target_required_features_satisfied','features':native.get('required-features',[]),
                            'package_manifest':manifest}]
                        evidence=[{'path':manifest,'line':1},{'path':source['path'],'line':1}]
                        graph['nodes'].append({'id':uid,'kind':'build_target','name':native['name'],'language':'cargo','path':manifest,'line':1,
                            'source_commit':graph['source_commit'],'build_context':context,'target_type':'EXECUTABLE','native_target_kind':native['kind'],
                            'root_source':source,'package':{'name':package['name'],'version':package['version'],'manifest':{'root':'source','path':manifest}},
                            'profile':profile,'features_requested':spec['features'],'default_features_requested':not spec['no_default_features'],
                            'declared_features':sorted(package.get('features',{})),
                            'conditions':guards,'runtime_execution':'not_observed'})
                        graph['edges'].append({'source':context,'target':uid,'kind':'CONFIGURES_BUILD_TARGET','status':'declared_output_plan',
                            'evidence':evidence,'conditions':guards,'runtime_execution':'not_observed'})
                        filename=template[0]+native['name']+template[1]
                        path=(PurePosixPath(directory['path'])/target/profile_directory/filename if target_mode=='explicit' else
                            PurePosixPath(directory['path'])/profile_directory/filename).as_posix()
                        artifact=identity(uid,'expected-artifact',path)
                        graph['nodes'].append({'id':artifact,'kind':'build_artifact','name':filename,'path':path,'line':0,'language':'cargo',
                            'source_commit':graph['source_commit'],'build_context':context,'native_target':uid,'native_executable':True,
                            'location':{'root':'source','path':path},'profile':profile,'conditions':guards,
                            'materialization':'expected_output_not_built','runtime_execution':'not_observed'})
                        graph['edges'].append({'source':uid,'target':artifact,'kind':'PRODUCES_ARTIFACT','status':'declared_output_plan',
                            'evidence':evidence,'artifact_role':'primary','conditions':guards,'runtime_execution':'not_observed'})
        except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as error:gap(str(error),invocation['id'])
    for manifest in sorted(p for p in paths if Path(p).name=='Cargo.toml' and p not in covered):
        gap('cargo_manifest_without_selected_build_context',path=manifest)
    build={'nodes':[n for n in graph['nodes'] if n.get('language')=='cargo' and n['kind']=='build_target' and 'features_requested' in n]}
    if build['nodes']:
        joins,diagnostics=link_source_symbols(build,graph,root=root,parser=parser)
        graph['edges'].extend(joins);graph['diagnostics'].extend(diagnostics)
    (output/'receipt.json').write_text(json.dumps({'schema':'cargo-declared-query/1','source_commit':graph['source_commit'],
        'cargo_version':cargo_version,'rustc_version':rustc_version,'commands':commands,**result},indent=2)+'\n',encoding='utf-8')
    return graph
