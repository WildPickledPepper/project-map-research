"""Bind current_exe paths to Cargo images and full, conditional package paths.

This is static deployment reasoning. It does not identify a running PID, start
a process, inspect the host filesystem or equate unrelated equal basenames.
"""
from collections import defaultdict,Counter
import json
import posixpath
from pathlib import PurePosixPath
from urllib.parse import quote


ADAPTER_VERSION='cargo_image_current_exe_artifact_binding/0.1.0'


def identity(*items):return 'deployment:'+':'.join(quote(str(p),safe='') for p in items)


def source_path(node):
    if node['kind']=='build_artifact':
        loc=node['location'];return loc['path'] if loc['root']=='source' else None
    if node['kind']=='copied_artifact':
        value=node['value'];base=value.get('base') or {}
        if base.get('kind') in {'source_root','canonical_source_root'} and not value['unresolved'] and all(isinstance(s,str) for s in value['segments']):
            return '/'.join(value['segments'])
    return None


def executable_base(base,image):
    if not isinstance(base,dict):return None
    if base.get('kind')=='current_executable':return image
    if base.get('kind')=='current_executable_directory':return posixpath.dirname(image)
    if base.get('kind')=='parent_of':
        parent=executable_base(base.get('base'),image)
        return posixpath.dirname(parent) if parent is not None else None
    return None


def context_matches(target,configuration,analysis):
    workspace=configuration.get('workspace')
    workspace=workspace.get('path') if isinstance(workspace,dict) else configuration['path']
    if workspace!=analysis['workspace'] or configuration['target_system'].get('target')!=analysis['target']:return False
    if bool(target.get('profile',{}).get('test'))!=('test' in analysis.get('cfg',[])):return False
    assertions=target.get('profile',{}).get('debug_assertions')
    if type(assertions) is not bool or assertions!=analysis.get('debug_assertions'):return False
    package=target.get('package',{}).get('name');prefix=(package or '')+'/'
    selected={f[len(prefix):] for f in analysis.get('features',[]) if f.startswith(prefix)}
    if 'features_requested' in target:
        expected={f.split('/',1)[1] if f.startswith(prefix) else f for f in target['features_requested']}
        if target['default_features_requested'] and 'default' in target.get('declared_features',[]):expected.add('default')
        return selected==expected
    # Native compiler features include the expanded set; direct analysis
    # requests may omit features enabled transitively by default.
    actual=set(target.get('features',[]))
    return selected<=actual and ('default' in selected)==('default' in actual)


def augment(graph,*,max_bindings=2048,max_membership_nodes=20000):
    if 'executable_deployment' in graph:raise ValueError('Executable deployment projection already present')
    nodes={n['id']:n for n in graph['nodes']};out=defaultdict(list);producers=defaultdict(list)
    for e in graph['edges']:
        out[e['source']].append(e)
        if e['kind']=='PRODUCES_ARTIFACT' and e.get('artifact_role')=='primary':producers[e['target']].append(e['source'])
    added=[];edges=[];diagnostics=[];stats=Counter();gap_keys=set();membership={}
    def gap(reason,source,required=True,**extra):
        key=(reason,source,json.dumps(extra,sort_keys=True))
        if key in gap_keys:return
        gap_keys.add(key);diagnostics.append({'kind':'executable_deployment_gap','reason':reason,'source':source,'required':required,**extra})
    def link(a,b,kind,evidence,conditions,**extra):
        edges.append({'source':a,'target':b,'kind':kind,'status':'conditional_candidate','evidence':evidence,
            'conditions':conditions,'runtime_execution':'not_observed',**extra})
    def belongs(target,path,analysis):
        entries={e['target'] for e in out[target['id']] if e['kind']=='EXECUTABLE_ENTRY_CANDIDATE'}
        if path.get('root_function') in entries:return 'native_call_frames_rooted_at_cargo_entry'
        key=(target['id'],analysis['id'])
        if key not in membership:
            pending=[e['target'] for e in out[target['id']] if e['kind']=='CARGO_TARGET_SOURCE'];seen=set()
            while pending and len(seen)<max_membership_nodes:
                current=pending.pop()
                if current in seen:continue
                seen.add(current)
                for e in out[current]:
                    if e['kind'] not in {'CONTAINS_SYMBOL','IMPORTS_MODULE'}:continue
                    if e.get('analysis_contexts') and analysis['id'] not in e['analysis_contexts']:continue
                    pending.append(e['target'])
            if pending:gap('cargo_module_membership_budget',target['id'],analysis_context=analysis['id'])
            membership[key]=seen
        if path.get('root_function') in membership[key]:return 'cargo_root_module_membership_in_analysis_context'
        return None
    # Index full paths, retaining every producer/context at an equal location.
    artifacts=defaultdict(list);images=[]
    for artifact in nodes.values():
        if artifact['kind'] not in {'build_artifact','copied_artifact'}:continue
        loc=source_path(artifact)
        if loc is None:continue
        origin=nodes.get(artifact.get('origin_artifact',artifact['id']))
        owners=producers.get(origin['id'],[]) if origin else []
        for owner in owners:
            target=nodes[owner];config=nodes.get(target['build_context']);system=config.get('target_system',{}) if config else {}
            if not system.get('target_path_style') or not system.get('name'):
                gap('artifact_target_system_unavailable',artifact['id']);continue
            artifacts[(system['name'],posixpath.normpath(loc))].append((artifact,origin,target,config))
            if (target.get('language')=='cargo' and target.get('target_type')=='EXECUTABLE' and origin.get('native_executable') and
                target.get('native_target_kind')!=['custom-build']):
                uid=identity('image',target['id'],artifact['id'])
                constraints=config.get('conditions',[])+target.get('conditions',[])+artifact.get('conditions',[])+[
                    {'kind':'running_process_image_matches_deployment','deployment':uid},
                    {'kind':'deployed_layout_matches_recorded_relative_files','deployment':uid}]
                row={'id':uid,'kind':'executable_deployment','name':loc,'path':artifact['path'],'line':artifact['line'],
                    'source_commit':graph['source_commit'],'language':'cargo','artifact':artifact['id'],'origin_artifact':origin['id'],
                    'build_target':target['id'],'build_context':config['id'],'image_location':{'root':'source','path':loc},
                    'target_system':system,'conditions':constraints,'runtime_execution':'not_observed'}
                images.append((row,target,config));added.append(row)
                link(artifact['id'],uid,'DEPLOYS_EXECUTABLE_CANDIDATE',[{'path':artifact['path'],'line':artifact['line']}],constraints)
    paths=[n for n in nodes.values() if n['kind']=='path_value' and n.get('language')=='rust' and
        executable_base(n['value'].get('base'),'placeholder/image') is not None]
    for path in paths:
        value=path['value'];boundary=nodes[path['consumer']];bindings=0;matches=0
        if value['unresolved'] or any(not isinstance(p,str) for p in value['segments']):
            gap('current_exe_path_components_unresolved',path['id']);continue
        for analysis_id in path.get('analysis_contexts',[]):
            analysis=nodes[analysis_id]
            for deployment,target,config in images:
                if not context_matches(target,config,analysis):continue
                ownership=belongs(target,path,analysis)
                if ownership is None:continue
                base=executable_base(value['base'],deployment['image_location']['path'])
                if value['style']!=config['target_system']['target_path_style']:
                    gap('runtime_path_style_differs_from_cargo_target',path['id'],deployment=deployment['id']);continue
                resolved=posixpath.normpath(posixpath.join(base,*value['segments']))
                if resolved=='..' or resolved.startswith('../') or resolved.startswith('/'):
                    gap('current_exe_path_outside_recorded_layout',path['id'],deployment=deployment['id']);continue
                if stats['bindings']>=max_bindings:
                    gap('current_exe_binding_budget',path['id']);break
                uid=identity('path',deployment['id'],path['id'],analysis_id)
                constraints=deployment['conditions']+value.get('conditions',[])+boundary.get('conditions',[])+[
                    {'kind':'consumer_path_reached_in_running_binary','consumer':boundary['id'],'ownership_basis':ownership},
                    {'kind':'native_rust_cfg_and_features_equal_analysis_context','analysis_context':analysis_id},
                    {'kind':'deployed_path_resolution_has_no_symlink_or_mount_redirection'}]
                row={'id':uid,'kind':'deployed_path_candidate','name':resolved,'path':path['path'],'line':path['line'],
                    'source_commit':graph['source_commit'],'language':'rust','source_path_value':path['id'],'consumer':boundary['id'],
                    'deployment':deployment['id'],'analysis_context':analysis_id,'location':{'root':'source','path':resolved},
                    'ownership_basis':ownership,'conditions':constraints,'runtime_execution':'not_observed'}
                added.append(row);bindings+=1;stats['bindings']+=1
                evidence=[{'path':path['path'],'line':path['line']}]
                extra={'analysis_contexts':[analysis_id],'deployment':deployment['id']}
                link(path['id'],uid,'PATH_DEPLOYMENT_BINDING',evidence,constraints,**extra)
                link(deployment['id'],uid,'RESOLVES_DEPLOYED_PATH_CANDIDATE',evidence,constraints,**extra)
                candidates=artifacts.get((config['target_system']['name'],resolved),[])
                matched_artifacts=[];matched_targets=[]
                for artifact,origin,provider,provider_config in candidates:
                    if boundary['family']=='command_constructor' and provider.get('target_type')!='EXECUTABLE':continue
                    conditions=constraints+artifact.get('conditions',[])+provider_config.get('conditions',[])+[
                        {'kind':'deployment_artifact_lineage_matches_recorded_producer','artifact':artifact['id']},
                        {'kind':'target_os_loader_accepts_provider_image','provider_context':provider_config['id'],
                            'launcher_arch':config['target_system'].get('target_arch'),
                            'provider_arch':provider_config['target_system'].get('target_arch'),
                            'provider_declared_processor':provider_config['target_system'].get('declared_processor')}]
                    link(uid,artifact['id'],'MATCHES_DEPLOYED_ARTIFACT_CANDIDATE',evidence,conditions,**extra)
                    kind='RESOLVES_EXECUTABLE_TARGET_CANDIDATE' if boundary['family']=='command_constructor' else 'READS_ARTIFACT_TARGET_CANDIDATE'
                    link(uid,provider['id'],kind,evidence,conditions,artifact=artifact['id'],**extra)
                    matches+=1;stats['artifact_matches']+=1
                    matched_artifacts.append(artifact['id']);matched_targets.append(provider['id'])
                row.update(matched_artifacts=sorted(set(matched_artifacts)),matched_producer_targets=sorted(set(matched_targets)))
                row['match_status']='ambiguous_conditional_producers' if len(row['matched_producer_targets'])>1 else 'single_conditional_producer' if matched_targets else 'unmatched'
                if not matched_targets:gap('no_artifact_at_deployment_candidate_path',uid,required=False,location=resolved)
                elif len(row['matched_producer_targets'])>1:
                    gap('multiple_conditional_producers_at_deployed_path',uid,required=False,targets=row['matched_producer_targets'])
        if not bindings:gap('current_exe_owner_or_build_context_not_bound',path['id'])
        elif not matches:gap('current_exe_consumer_artifact_not_matched',path['id'])
    graph['nodes'].extend(added);graph['edges'].extend(edges);graph['diagnostics'].extend(diagnostics)
    graph['executable_deployment']={'adapter':ADAPTER_VERSION,'deployment_images':len(images),'current_exe_source_paths':len(paths),
        'counts':dict(stats),'required_gaps':sum(d['required'] for d in diagnostics),'runtime_execution':'not_observed',
        'budget':{'bindings':max_bindings,'module_membership_nodes':max_membership_nodes}}
    return graph
