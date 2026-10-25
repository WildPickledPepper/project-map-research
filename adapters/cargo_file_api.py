"""Normalize successful Cargo compiler-artifact JSON with bound native context.

Metadata supplies package/target identity. A compiler stream supplies actual
output paths and profile/features. No output name is inferred from a package name.
"""
from collections import Counter,defaultdict
import json
import ntpath
import posixpath
from pathlib import Path,PureWindowsPath,PurePosixPath
from urllib.parse import quote


def identity(*parts):return 'cargo:'+':'.join(quote(str(p),safe='') for p in parts)


def system(cfg):
    values={}
    for item in cfg:
        key,separator,value=item.partition('=')
        if separator:
            try:values.setdefault(key,[]).append(json.loads(value))
            except ValueError:raise ValueError('Invalid rustc cfg literal')
    os_name=values.get('target_os',[]);arch=values.get('target_arch',[])
    if len(os_name)!=1 or not isinstance(os_name[0],str):raise ValueError('Native target_os is not unique')
    if len(arch)!=1 or not isinstance(arch[0],str):raise ValueError('Native target_arch is not unique')
    style='windows' if 'windows' in cfg or 'windows' in values.get('target_family',[]) else 'posix' if 'unix' in cfg or 'unix' in values.get('target_family',[]) else None
    return {'name':{'windows':'Windows','linux':'Linux','macos':'Darwin'}.get(os_name[0],os_name[0]),
        'path_style':style,'arch':arch[0],'target_os':os_name[0]}


def normalize(metadata,messages,*,repository,source_commit,expected_commit,returncode,context_key,
              host_target,target,host_cfg,target_cfg,cargo_version,rustc_version,recorded_repository=None,max_records=100000):
    result={'nodes':[],'edges':[],'diagnostics':[],'coverage':[],'limits':['cargo_native_build_report_is_not_program_execution'],
        'native_context':{'key':context_key,'source_commit':source_commit,'status':'unavailable'}}
    def fail(reason):
        result['nodes']=[];result['edges']=[]
        result['diagnostics']=[{'kind':'cargo_context_unavailable','context_key':context_key,'reason':reason,'required':True}]
        return result
    if not source_commit or source_commit!=expected_commit:return fail('Source revision differs from bound native context')
    if type(returncode) is not int or returncode!=0:return fail('Cargo build did not succeed')
    if not context_key or not host_target or not target or not cargo_version or not rustc_version:return fail('Native command/toolchain identity missing')
    nodes={};edges=[];counts=Counter()
    def put(row):
        old=nodes.get(row['id'])
        if old is not None and old!=row:raise ValueError('Conflicting duplicate native unit')
        nodes[row['id']]=row;return row['id']
    def edge(a,b,kind,evidence,**extra):
        edges.append({'source':a,'target':b,'kind':kind,'status':'native_build_report','evidence':evidence,
            'runtime_execution':'not_observed',**extra})
    try:
        host_info=system(host_cfg);target_info=system(target_cfg)
        if host_info['path_style'] is None:raise ValueError('Native host filesystem style unavailable')
        def native_path(value):
            cls,mod=(PureWindowsPath,ntpath) if host_info['path_style']=='windows' else (PurePosixPath,posixpath)
            path=cls(value)
            if not path.is_absolute():raise ValueError('Native Cargo path is not absolute')
            return cls(mod.normpath(str(path)))
        root=native_path(str(recorded_repository) if recorded_repository else str(Path(repository).resolve()))
        target_dir=native_path(metadata['target_directory']);workspace=native_path(metadata['workspace_root'])
        if not workspace.is_relative_to(root):raise ValueError('Cargo workspace outside bound repository')
        target_system={'status':'available','name':target_info['name'],'host_name':host_info['name'],
            'target_path_style':target_info['path_style'],'host_path_style':host_info['path_style'],
            'target_arch':target_info['arch'],'host_arch':host_info['arch'],'target':target,'host_target':host_target,
            'cross_compiling':target!=host_target,'basis':'recorded_native_rustc_cfg_and_successful_cargo_build'}
        def location(value):
            path=native_path(str(value))
            for name,base in [('source',root),('build',target_dir)]:
                if path.is_relative_to(base):return {'root':name,'path':path.relative_to(base).as_posix()}
            return {'root':'external','path':str(path)}
        members=set(metadata['workspace_members']);packages={p['id']:p for p in metadata['packages']}
        if not members<=packages.keys():raise ValueError('Workspace package is absent from metadata')
        context=identity(context_key);manifest=location(workspace/'Cargo.toml')
        put({'id':context,'kind':'build_configuration','name':context_key,'path':manifest['path'],'line':1,'language':'cargo',
            'source_commit':source_commit,'target_system':target_system,'cargo_version':cargo_version,'rustc_version':rustc_version,
            'workspace':manifest,'target_directory':location(target_dir),'state':'native_build_succeeded','runtime_execution':'not_observed'})
        finished=False
        for ordinal,record in enumerate(messages):
            if ordinal>=max_records:raise ValueError('Cargo message record budget')
            if not isinstance(record,dict):raise ValueError('Cargo JSON message is not an object')
            reason=record.get('reason');counts[str(reason)]+=1
            if reason=='build-finished':
                if finished or record.get('success') is not True:raise ValueError('Native build-finished status is not a unique success')
                finished=True;continue
            if reason!='compiler-artifact':continue
            if finished:raise ValueError('Artifact appears after build-finished')
            package_id=record['package_id']
            if package_id not in members:counts['dependency_artifact_not_expanded']+=1;continue
            package=packages[package_id];native=record['target'];package_manifest=location(package['manifest_path'])
            if package_manifest['root']!='source':raise ValueError('Workspace manifest outside bound source')
            signature=lambda t:(t['name'],tuple(t['kind']),tuple(t['crate_types']),str(native_path(t['src_path'])))
            if not any(signature(t)==signature(native) for t in package['targets']):raise ValueError('Compiler target differs from native package metadata')
            if record.get('manifest_path') and native_path(record['manifest_path'])!=native_path(package['manifest_path']):
                raise ValueError('Compiler manifest differs from native package identity')
            profile=record['profile'];features=record['features'];filenames=record['filenames'];executable=record.get('executable')
            if type(record.get('fresh')) is not bool or type(profile.get('test')) is not bool or type(profile.get('debug_assertions')) is not bool:
                raise ValueError('Invalid native artifact/profile flags')
            if not isinstance(features,list) or not all(isinstance(f,str) for f in features):raise ValueError('Invalid native feature identity')
            if not isinstance(filenames,list) or not filenames or not all(isinstance(f,str) for f in filenames):raise ValueError('Native output filename list missing')
            if executable is not None and (not isinstance(executable,str) or executable not in filenames):raise ValueError('Executable absent from native output list')
            source=location(native['src_path'])
            if source['root']!='source':raise ValueError('Workspace target source outside bound source')
            evidence=[{'path':package_manifest['path'],'line':1},{'path':source['path'],'line':1}]
            unit_key=json.dumps([native['name'],native['kind'],source['path'],profile,sorted(features)],sort_keys=True,separators=(',',':'))
            uid=put({'id':identity(context_key,'target',package_manifest['path'],unit_key),'kind':'build_target','name':native['name'],
                'path':package_manifest['path'],'line':1,'language':'cargo','source_commit':source_commit,'build_context':context,
                'target_type':'EXECUTABLE' if executable is not None else 'CARGO_OUTPUT','native_target_kind':native['kind'],
                'package':{'name':package['name'],'version':package['version'],'manifest':package_manifest},
                'root_source':source,'profile':profile,'features':sorted(features),'fresh':record['fresh'],
                'runtime_execution':'not_observed'})
            edge(context,uid,'CONFIGURES_BUILD_TARGET',evidence,build_context=context)
            if len(filenames)!=len(set(filenames)):raise ValueError('Duplicate native output filename')
            for filename in filenames:
                loc=location(filename);primary=filename==executable
                artifact=put({'id':identity(uid,'artifact',loc['root'],loc['path']),'kind':'build_artifact','name':native_path(filename).name,
                    'path':loc['path'],'line':0,'language':'cargo','source_commit':source_commit,'location':loc,'build_context':context,
                    'native_target':uid,'native_executable':primary,'profile':profile,'features':sorted(features),
                    'materialization':'reported_by_successful_native_build','runtime_execution':'not_observed'})
                edge(uid,artifact,'PRODUCES_ARTIFACT',evidence,build_context=context,
                    artifact_role='test_executable' if primary and profile['test'] else 'primary' if primary else 'declared_output')
                if loc['root']=='external':result['diagnostics'].append({'kind':'cargo_output_outside_context','path':loc['path'],'build_context':context,'required':True})
        if not finished:raise ValueError('Native build-finished message missing')
        result['nodes']=list(nodes.values());result['edges']=edges
        result['native_context'].update(status='built',target_system=target_system,record_counts=dict(counts),
            cargo_version=cargo_version,rustc_version=rustc_version,
            root_relocated=bool(recorded_repository and str(Path(repository).resolve())!=str(root)))
        if target_info['path_style'] is None:result['diagnostics'].append({'kind':'cargo_target_runtime_path_style_unavailable','context_key':context_key,'required':True})
        return result
    except (KeyError,TypeError,ValueError,AttributeError,IndexError,OSError) as error:return fail('Invalid Cargo native records: '+str(error))


def link_source_symbols(build_facts,source_facts,*,root,parser):
    """Bind Cargo target root files; default-main edges remain source candidates."""
    by_path=defaultdict(list);edges=[];diagnostics=[];asts={}
    for n in source_facts['nodes']:
        if n.get('language')=='rust':by_path[n['path']].append(n)
    for target in build_facts['nodes']:
        if target['kind']!='build_target':continue
        path=target['root_source']['path'];rows=by_path[path];module=next((n for n in rows if n.get('syntax')=='source_file'),None)
        evidence=[{'path':target['path'],'line':1},{'path':path,'line':1}]
        base={'build_context':target['build_context'],'evidence':evidence,'runtime_execution':'not_observed'}
        if module:edges.append({'source':target['id'],'target':module['id'],'kind':'CARGO_TARGET_SOURCE','status':'native_source_membership',**base})
        else:diagnostics.append({'kind':'cargo_target_source_not_in_language_facts','path':path,'source':target['id'],'required':True});continue
        if target['target_type']!='EXECUTABLE' or target['profile']['test']:continue
        if path not in asts:asts[path]=parser.parse((Path(root)/path).read_bytes())
        tree=asts[path];attributes=[c for c in tree.root_node.named_children if c.type=='inner_attribute_item']
        def has_no_main(node):return node.type=='identifier' and node.text==b'no_main' or any(has_no_main(c) for c in node.named_children)
        if any(has_no_main(a) for a in attributes):
            diagnostics.append({'kind':'cargo_custom_entry_requires_linker_context','path':path,'source':target['id'],'required':True});continue
        root_members={e['target'] for e in source_facts['edges'] if e['source']==module['id'] and e['kind']=='CONTAINS_SYMBOL'}
        entries=[n for n in rows if n['kind']=='callable' and n['name']=='main' and n.get('definition') and n['id'] in root_members]
        for n in entries:
            edges.append({'source':target['id'],'target':n['id'],'kind':'EXECUTABLE_ENTRY_CANDIDATE','status':'candidate',**base,
                'conditions':n.get('conditions',[]),'condition':'native_target_cfg_and_default_rust_entry_link_selection'})
        if not entries:diagnostics.append({'kind':'cargo_default_entry_not_in_source_facts','path':path,'source':target['id'],'required':True})
    return edges,diagnostics
