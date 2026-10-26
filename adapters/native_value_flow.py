"""Normalize native SVF/RAPx results; all dataflow and alias rules live upstream."""
from collections import Counter
import json
import posixpath
from urllib.parse import quote

from adapters.snapshot_inputs import validate_path


def location(value, root, selected,source_directory=''):
    if isinstance(value,str):
        try:value=json.loads(value[value.index('{'):] if '{' in value else value)
        except (ValueError,TypeError):value={}
    value=value or {}; filename=value.get('file') or value.get('fl') or ''
    filename=posixpath.normpath(filename.replace('\\','/')) if filename else ''
    prefix=(root or '').replace('\\','/').rstrip('/')+'/'
    if filename.casefold().startswith(prefix.casefold()):path=filename[len(prefix):]
    elif filename and not filename.startswith('/') and ':' not in filename:path=filename
    else:path=''
    if path not in selected and filename and not filename.startswith('/') and ':' not in filename:
        path=posixpath.normpath(source_directory+'/'+filename)
    path=path if path in selected else ''
    return {'path':path,'line':int(value.get('line') or value.get('ln') or 0),
            'column':int(value.get('column') or value.get('cl') or 0)}


def normalize(data, *, provider, paths, source_commit, context):
    if data.get('source_commit')!=source_commit:raise ValueError('Native value-flow source revision differs')
    if data.get('context')!=context:raise ValueError('Native value-flow compile context differs')
    selected=set(paths)
    for path in selected:validate_path(path)
    expected='svf-native-export/1' if provider=='svf' else 'rapx-native-export/1'
    if data.get('schema')!=expected:raise ValueError('Wrong native value-flow provider/schema')
    module=data.get('module') or data.get('crate')
    if not isinstance(module,str) or not module:raise ValueError('Native module identity required')
    prefix=provider+':'+quote(context,safe='')+':'+quote(module,safe='')+':'
    provenance={'provider':provider,'adapter':'native_value_flow/1','context':context,'source_commit':source_commit,
        'native_version':data.get('package_version') or data.get('upstream_revision'),
        'precision':'native_static_candidate'}
    nodes={};edges=[];diagnostics=[];root=data.get('source_root')
    def node(uid,kind,name,pos,**extra):
        nodes[uid]={'id':uid,'kind':kind,'name':name,**pos,'language':data.get('language','cpp') if provider=='svf' else 'rust',
            'provenance':provenance,'evidence_kind':provider+'_native_output','runtime_execution':'not_observed',**extra}
        return uid
    def edge(source,target,kind,**extra):
        origin=nodes[source];evidence=[{k:origin[k] for k in ('path','line','column')}] if origin['path'] else []
        edges.append({'source':source,'target':target,'kind':kind,'status':'candidate',
                      'evidence':evidence,'provenance':provenance,'runtime_execution':'not_observed',**extra})
    if provider=='svf':
        positions={}
        for raw in data['nodes']:
            pos=location(raw.get('source_location'),root,selected,data.get('source_directory',''))
            fallback=not pos['path']
            if fallback:pos=location(raw.get('function_location'),root,selected,data.get('source_directory',''))
            uid=prefix+'flow:'+str(raw['id'])
            node(uid,'value',raw['kind']+' '+str(raw['id']),pos,native_id=raw['id'],native_kind=raw['kind'],
                 native_description=raw['text'],native_function=raw.get('function'),
                 source_location_kind='function_fallback' if fallback else 'native_instruction')
            if raw.get('value') is not None:positions[raw['value']]=pos
        for raw in data['nodes']:
            if not raw.get('function'):continue
            uid=prefix+'function:'+quote(raw['function'],safe='')
            if uid not in nodes:
                pos=location(raw.get('function_location'),root,selected,data.get('source_directory',''))
                name=data.get('function_display_names',{}).get(raw['function'],raw['function'])
                node(uid,'callable',name,pos,native_function=raw['function'],native_function_display=name)
            edge(uid,prefix+'flow:'+str(raw['id']),'SVF_CONTAINS_VALUE')
        for raw in data['edges']:
            edge(prefix+'flow:'+str(raw['source']),prefix+'flow:'+str(raw['target']),'SVF_VALUE_FLOW',native=raw)
        for raw in data.get('variables',[]):
            node(prefix+'variable:'+str(raw['id']),'object_binding',raw['name'] or raw['kind']+' '+str(raw['id']),
                 positions.get(raw['id'],{'path':'','line':0,'column':0}),native_id=raw['id'],native_kind=raw['kind'],
                 native_description=raw['text'])
        for raw in data['nodes']:
            if raw.get('value') is not None:
                edge(prefix+'flow:'+str(raw['id']),prefix+'variable:'+str(raw['value']),'SVF_HAS_NATIVE_VALUE')
        for raw in data.get('points_to',[]):
            edge(prefix+'variable:'+str(raw['source']),prefix+'variable:'+str(raw['target']),'SVF_POINTS_TO')
        if data.get('points_to_backend')=='unavailable' or (data.get('python_points_to_binding_available') is False and not data.get('points_to_backend')):
            diagnostics.append({'path':'','kind':'svf_python_points_to_binding_unavailable',
                                'native_cli_capture_required':True})
    else:
        functions={f['name']:f for f in data['functions']}
        def fnid(name):return prefix+'function:'+quote(name,safe='')
        def localid(name,local):return fnid(name)+':local:'+str(local)
        for name,raw in functions.items():
            pos=location(raw['location'],root,selected)
            node(fnid(name),'callable',name,pos,native_id=raw['native_id'],native_arguments=raw['arguments'])
            for local in raw['locals']:
                own=location(local.get('location'),root,selected)
                if not own['path']:own=pos
                uid=localid(name,local['id'])
                node(uid,'parameter' if 0<local['id']<=raw['arguments'] else 'value',name+'::_'+str(local['id']),own,
                     native_local=local['id'],native_operations=local['operations'],native_function=name)
                edge(fnid(name),uid,'RAPX_CONTAINS_LOCAL')
            call_positions={(c['block'],c.get('statement')) for c in raw['calls']}
            for native in raw['edges']:
                role='RAPX_CALL_OPERAND' if (native['block'],native['statement']) in call_positions else 'RAPX_VALUE_FLOW'
                edge(localid(name,native['source']),localid(name,native['target']),role,native=native)
            for native in raw.get('alias_summary',[]):
                edge(localid(name,native['left']),localid(name,native['right']),'RAPX_ALIAS_SUMMARY',native=native,
                     scope='native_argument_return_summary_with_field_projections')
        for name,raw in functions.items():
            for ordinal,call in enumerate(raw['calls']):
                pos=location(call.get('location'),root,selected)
                uid=fnid(name)+':call:'+str(call['block'])+':'+str(ordinal)
                node(uid,'call_site',call['callee'] or 'indirect MIR call',pos,native_call=call,
                     native_function=name,resolution='native_direct_target' if call['callee'] else 'native_indirect_unresolved')
                edge(fnid(name),uid,'RAPX_CONTAINS_CALL')
                callee=call['callee']
                if callee in functions:
                    edge(uid,fnid(callee),'RAPX_CALLS',native_callsite=uid)
                    for i,argument in enumerate(call['arguments'],1):
                        if argument.get('native_value') is not None and i<=functions[callee]['arguments']:
                            edge(localid(name,argument['native_value']),localid(callee,i),'RAPX_ACTUAL_TO_FORMAL',
                                 native_callsite=uid,native_projection=argument.get('projection'),requires_matching_callsite=True)
                    edge(localid(callee,0),localid(name,call['destination']),'RAPX_RETURN_TO_CALLER',
                         native_callsite=uid,requires_matching_callsite=True)
                elif callee:
                    if fnid(callee) not in nodes:node(fnid(callee),'callable',callee,{'path':'','line':0,'column':0},external_declaration=True)
                    edge(uid,fnid(callee),'RAPX_CALLS_EXTERNAL',native_callsite=uid)
                else:diagnostics.append({'path':pos['path'],'line':pos['line'],'kind':'native_indirect_call_unresolved','node':uid})
    counts=Counter(n['path'] for n in nodes.values() if n['path'])
    return {'nodes':list(nodes.values()),'edges':edges,'diagnostics':diagnostics,
        'coverage':[{'path':p,'provider':provider,'context':context,'status':'provider_facts_available','nodes':c}
                    for p,c in sorted(counts.items())],
        'components':provenance,'limits':['native_candidates_preserve_upstream_approximations',
          'call_and_return_contexts_are_explicit_not_runtime_execution','unmapped_or_external_native_nodes_have_no_repository_path']}
