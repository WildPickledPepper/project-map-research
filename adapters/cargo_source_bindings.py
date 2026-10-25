"""Conditionally associate source-extracted Cargo builds with native captures.

Bindings compare working directory, manifest, options and target-directory
provenance within the same source version. No package/binary spelling join or
analysis-process environment is used.
"""
from pathlib import PurePosixPath,PureWindowsPath
import json
import posixpath
from adapters.cargo_file_api import identity
from adapters.python_process_values import resolve,environment_value


ADAPTER_VERSION='source_cargo_native_context_binding/0.1.0'
VALUE_OPTIONS={'--profile':'profile','--manifest-path':'manifest','--target-dir':'target_directory',
    '--target':'target','--features':'features','-F':'features'}
IGNORED_FLAGS={'--offline','--locked','--frozen','--quiet','-q','--verbose','-v','-vv','--ignore-rust-version'}


def parse_build(argv):
    """Interpret the supported Cargo build options; unknown options block joins."""
    if not argv or not isinstance(argv[0],str):return None
    if argv[0].replace('\\','/').rsplit('/',1)[-1] not in {'cargo','cargo.exe'}:return None
    result={'argv':argv,'profile':'dev','manifest':None,'target_directory':None,'target':None,
        'features':[],'no_default_features':False,'gaps':[]}
    if len(argv)<2 or argv[1]!='build':result['gaps']=['cargo_command_not_supported'];return result
    seen=set();index=2
    while index<len(argv):
        word=argv[index];index+=1
        if not isinstance(word,str):result['gaps'].append('cargo_argument_not_a_constant_string');continue
        if word in IGNORED_FLAGS:continue
        if word in {'--release','-r'}:
            if 'profile' in seen:result['gaps'].append('cargo_profile_option_conflict')
            seen.add('profile');result['profile']='release';continue
        if word=='--no-default-features':result['no_default_features']=True;continue
        option,separator,value=word.partition('=')
        if word.startswith('-F') and not word.startswith('-F=') and word!='-F':option='-F';separator='=';value=word[2:]
        if option not in VALUE_OPTIONS:
            result['gaps'].append('cargo_option_not_supported:'+word);continue
        key=VALUE_OPTIONS[option]
        if not separator:
            if index==len(argv):result['gaps'].append('cargo_option_value_missing:'+option);continue
            value=argv[index];index+=1
        if not isinstance(value,str) or not value or value.startswith('-'):
            result['gaps'].append('cargo_option_value_invalid:'+option);continue
        if key=='features':result[key].extend(value.replace(',',' ').split());continue
        if key in seen:result['gaps'].append('cargo_option_requires_additional_context:'+option)
        seen.add(key);result[key]=value
    result['features']=sorted(set(result['features']));result['gaps']=sorted(set(result['gaps']));return result


def source_location(value,cwd=None):
    """Convert a source-root path, or a relative path with bound cwd, lexically."""
    if value.get('unresolved') or any(not isinstance(p,str) for p in value['segments']):return None
    base=value.get('base');parts=value['segments']
    if base and base['kind'] in {'source_root','canonical_source_root'}:path='/'.join(parts)
    elif base is None and cwd is not None:path=posixpath.join(cwd,*parts)
    else:return None
    path=posixpath.normpath(path)
    return None if path=='..' or path.startswith('../') or path.startswith('/') else path


def interpret(invocation,effects,*,host_system,input_paths):
    selected=resolve(invocation,host_system)
    if selected['status'] in {'inactive_path_style','excluded'}:return None
    argv=[words[0]['text'] if len(words)==1 else None for words in selected['argv']]
    spec=parse_build(argv)
    if spec is None:return None
    spec['gaps'].extend(selected['gaps']);spec['conditions']=list(invocation['conditions'])
    spec['conditions'].append({'kind':'source_process_invocation_reached_and_succeeds'})
    spec['conditions'].append({'kind':'source_executable_resolves_to_recorded_cargo'})
    for words in selected['argv']:
        for word in words:spec['conditions'].extend(word['conditions'])
    cwd=selected['cwd'];spec['cwd']=None
    if invocation['working_directory_mode']=='explicit' and len(cwd)==1:
        spec['cwd']=source_location(cwd[0]['path_value']);spec['conditions'].extend(cwd[0]['conditions'])
    if spec['cwd'] is None:spec['gaps'].append('cargo_working_directory_not_bound_to_source')
    def relative_option(value):
        if value is None or spec['cwd'] is None:return None
        cls=PureWindowsPath if host_system['path_style']=='windows' else PurePosixPath
        parsed=cls(value)
        if parsed.anchor:return None
        return source_location({'segments':list(parsed.parts),'base':None},spec['cwd'])
    if spec['manifest'] is not None:
        manifest=relative_option(spec['manifest'])
        spec['manifest']=manifest if manifest in input_paths else None
    elif spec['cwd'] is not None:
        directory=PurePosixPath(spec['cwd'])
        spec['manifest']=next(((p/'Cargo.toml').as_posix() for p in [directory,*directory.parents]
            if (p/'Cargo.toml').as_posix() in input_paths),None)
    if spec['manifest'] is None:spec['gaps'].append('cargo_manifest_not_bound_to_selected_source')
    spec['environment_sources']={}
    for key in ('CARGO_TARGET_DIR','CARGO_BUILD_TARGET'):
        value=environment_value(invocation,effects,key,host_system)
        spec['environment_sources'][key]=value
        spec['conditions'].extend(value.get('source_conditions',[]))
        for condition in value.get('conditions',[]):spec['conditions'].append({'kind':condition,'variable':key})
    directory=spec['environment_sources']['CARGO_TARGET_DIR']
    if spec['target_directory'] is not None:
        spec['target_directory']=relative_option(spec['target_directory'])
        if spec['target_directory'] is None:spec['gaps'].append('cargo_target_directory_not_bound_to_source')
        spec['target_directory_basis']='command_line'
    elif directory['known'] and directory['value'] is not None:
        spec['target_directory']=source_location(directory['value']['path_value'],spec['cwd'])
        if spec['target_directory'] is None:spec['gaps'].append('cargo_target_directory_not_bound_to_source')
        spec['target_directory_basis']='source_environment'
    else:
        spec['target_directory_basis']='native_context_required'
        spec['conditions'].append({'kind':'source_target_directory_environment_and_config_equal_native_capture'})
    target=spec['environment_sources']['CARGO_BUILD_TARGET']
    if spec['target'] is not None:spec['target_basis']='command_line'
    elif target['known'] and target['value'] is not None:
        spec['target']=target['value']['text'];spec['target_basis']='source_environment'
        if not spec['target']:spec['gaps'].append('cargo_target_environment_not_a_constant_string')
    else:
        spec['target_basis']='native_context_required'
        spec['conditions'].append({'kind':'source_build_target_environment_and_config_equal_native_capture'})
    # External configs, compiler wrappers, profile overrides and build scripts
    # may still change compilation. Preserve the native-context precondition.
    spec['conditions'].append({'kind':'source_cargo_configuration_toolchain_and_build_inputs_equal_native_capture'})
    spec['conditions']=list({json.dumps(c,sort_keys=True):c for c in spec['conditions']}.values())
    spec['gaps']=sorted(set(spec['gaps']));return spec


def augment(graph):
    if 'cargo_source_bindings' in graph:raise ValueError('Cargo source bindings already present')
    configs=[n for n in graph['nodes'] if n['kind']=='build_configuration' and n.get('language')=='cargo']
    invocations=[n for n in graph['nodes'] if n['kind']=='python_process_invocation']
    effects=[n for n in graph['nodes'] if n['kind']=='python_environment_effect'];added=[];edges=[];gaps=[];cache={};requests={};matched=set()
    for config in configs:
        system=config['target_system'];host={'name':system['host_name'],'path_style':system['host_path_style']}
        request=config.get('source_request')
        if not request:
            gaps.append({'kind':'cargo_capture_source_request_missing','source':config['id'],'required':True});continue
        for invocation in invocations:
            key=(invocation['id'],host['name'],host['path_style'])
            if key not in cache:cache[key]=interpret(invocation,effects,host_system=host,input_paths=graph['input_paths'])
            spec=cache[key]
            if spec is None:continue
            uid=identity('source-build',config['id'],invocation['id']);evidence=[{'path':invocation['path'],'line':invocation['line']}]
            added.append({'id':uid,'kind':'cargo_build_request','name':'Cargo build request','path':invocation['path'],'line':invocation['line'],
                'source_commit':graph['source_commit'],'language':'cargo','source_invocation':invocation['id'],
                'native_context':config['id'],'host_system':host,'request':spec,'runtime_execution':'not_observed'})
            edges.append({'source':invocation['id'],'target':uid,'kind':'SOURCE_BUILD_REQUEST','status':'source_interpretation',
                'evidence':evidence,'runtime_execution':'not_observed'})
            if spec['gaps']:
                gaps.append({'kind':'cargo_source_request_unresolved','source':uid,'reasons':spec['gaps'],'required':True});continue
            requests[key]=uid
            mismatch=[key for key in ('cwd','manifest','profile','features','no_default_features') if spec[key]!=request.get(key)]
            if spec['target'] is not None and (spec['target']!=system['target'] or request.get('target_mode')!='explicit'):mismatch.append('target')
            if spec['target_directory'] is not None and config['target_directory']!={'root':'source','path':spec['target_directory']}:mismatch.append('target_directory')
            if mismatch:
                gaps.append({'kind':'cargo_source_native_context_mismatch','source':uid,'fields':mismatch,'required':False});continue
            matched.add(key)
            edges.append({'source':uid,'target':config['id'],'kind':'REQUESTS_BUILD_CONTEXT_CANDIDATE','status':'conditional_candidate',
                'evidence':evidence,'conditions':spec['conditions'],'runtime_execution':'not_observed'})
    for key in requests.keys()-matched:gaps.append({'kind':'cargo_source_context_not_matched','source':requests[key],'required':True})
    graph['nodes'].extend(added);graph['edges'].extend(edges);graph['diagnostics'].extend(gaps)
    graph['cargo_source_bindings']={'adapter':ADAPTER_VERSION,'native_contexts':len(configs),'source_request_records':len(added),
        'candidate_bindings':sum(e['kind']=='REQUESTS_BUILD_CONTEXT_CANDIDATE' for e in edges)}
    return graph
