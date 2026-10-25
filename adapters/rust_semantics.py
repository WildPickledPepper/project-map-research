"""Normalize native rust-analyzer definitions in separately retained Cargo contexts."""
from collections import defaultdict
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import quote,urlparse
from urllib.request import url2pathname

from adapters.rust_analyzer import Client
from adapters.rust_project import available,binary,cargo_options,configuration_matrix,discover,tool_output
from adapters.rust_facts import Extractor,CALLABLES,TYPES
from adapters.syntax_supplement import walk,text,parents


class Linker:
    def __init__(self,root,paths,parser,output):
        self.root=Path(root).resolve();self.paths=set(paths);self.parser=parser;self.output=Path(output)
        self.x=Extractor({p:(self.root/p).read_bytes() for p in paths if p.endswith('.rs')},parser)
        self.external_cache={};self.bindings=defaultdict(set);self.calls=defaultdict(dict);self.context_ids=[]
        self.edge_groups={};self.flow=defaultdict(set);self.returned=defaultdict(set)
        for edge in self.x.edges:
            if edge['kind'] in {'VALUE_SOURCE','PATTERN_VALUE_SOURCE','VALUE_COMPONENT'}:self.flow[edge['source']].add(edge['target'])
            if edge['kind']=='RETURNS_VALUE':self.returned[edge['source']].add(edge['target'])

    def edge(self,source,target,kind,context,*,status='inferred_in_context',**fields):
        key=(source,target,kind,status,json.dumps(fields,sort_keys=True))
        if key not in self.edge_groups:
            path,node=self.x.syntax[source]
            self.x.edge(source,target,kind,node,path,status=status,analysis_contexts=[],**fields)
            self.edge_groups[key]=self.x.edges[-1]
        if context not in self.edge_groups[key]['analysis_contexts']:self.edge_groups[key]['analysis_contexts'].append(context)

    def external(self,path,selection,source):
        """Read declaration structure in toolchain/cache sources; never import it."""
        if path not in self.external_cache:
            records={};parts=path.parts;package='unknown';version=None;module=path.name
            if 'library' in parts:
                index=len(parts)-1-list(reversed(parts)).index('library')
                if index+1<len(parts):package=parts[index+1];module='/'.join(parts[index+2:])
            elif 'registry' in parts and 'src' in parts:
                for i,part in enumerate(parts):
                    match=re.fullmatch(r'(.+)-(\d+\.\d+\.\d+.*)',part)
                    if match:
                        package=match[1].replace('-','_');version=match[2];module='/'.join(parts[i+1:]);break
            try:
                raw=path.read_bytes();lines=raw.splitlines();tree=self.parser.parse(raw)
                for node in walk(tree.root_node):
                    name=node.child_by_field_name('name')
                    if name is None or node.type not in CALLABLES|TYPES|{'macro_definition','field_declaration','enum_variant'}:continue
                    prefix=lines[name.start_point[0]][:name.start_point[1]].decode('utf-8')
                    point=(name.start_point[0],len(prefix.encode('utf-16-le'))//2)
                    containers=[text(a.child_by_field_name('type' if a.type=='impl_item' else 'name')) for a in reversed(list(parents(node)))
                        if a.type in TYPES|{'mod_item','impl_item'}]
                    name_text=text(name);scopes=[p for p in module.removesuffix('.rs').split('/') if p not in {'src','lib','mod'}]
                    canonical='::'.join([package,*scopes,*filter(None,containers),name_text])
                    records[point]={'package':package,'version':version,'module':module,'name':name_text,
                        'container':next((text(a.child_by_field_name('type')) for a in parents(node) if a.type=='impl_item'),None),
                        'declaration_kind':node.type,'canonical':canonical}
            except (OSError,UnicodeError):pass
            self.external_cache[path]=(package,version,module,records)
        package,version,module,records=self.external_cache[path];point=(selection['start']['line'],selection['start']['character'])
        record=records.get(point,{'package':package,'version':version,'module':module,'declaration_kind':'unindexed_external_declaration',
            'name':'<external>','canonical':package+'::'+module})
        if record['declaration_kind']=='unindexed_external_declaration':
            # New compiler syntax can exceed the grammar's coverage. Retain the
            # exact identifier selected by the native server, without inventing
            # an impl/container or using the spelling of the source call.
            try:
                lines=path.read_text(encoding='utf-8').splitlines();start=selection['start'];end=selection['end']
                if start['line']==end['line']:
                    raw=lines[start['line']].encode('utf-16-le')
                    token=raw[start['character']*2:end['character']*2].decode('utf-16-le')
                    if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',token):
                        record={**record,'name':token,'declaration_kind':'native_selection_token',
                            'canonical':package+'::'+module+'::<native_selection>::'+token,
                            'declaration_structure':'not_parsed_by_grammar','basis':'rust_analyzer_selection_and_external_source_token'}
            except (OSError,UnicodeError,IndexError,KeyError):pass
        uid='rust:external:'+quote(json.dumps([package,version,module,*point],separators=(',',':')),safe='')
        if uid not in self.x.nodes:
            origin=self.x.nodes[source]
            self.x.nodes[uid]={'id':uid,'kind':'external_symbol','name':record['canonical'],'path':origin['path'],
                'line':origin['line'],'language':'rust','external_declaration':record,
                'runtime_execution':'not_observed','source_anchor':'using_reference_location'}
        return uid

    def targets(self,values,source):
        result=[]
        for value in values if isinstance(values,list) else [values] if values else []:
            path=Path(url2pathname(urlparse(value.get('targetUri',value.get('uri'))).path)).resolve()
            selected=value.get('targetSelectionRange',value.get('range'))
            if path.is_relative_to(self.root):
                relative=path.relative_to(self.root).as_posix();pos=selected['start']
                ids=self.x.points.get((relative,pos['line'],pos['character']),set())
                if ids:result.extend(ids);continue
                # Preserve generated/unselected source locations without pretending
                # the origin position is an indexed callable.
                uid='rust:origin:'+quote(relative,safe='/')+f":{pos['line']}:{pos['character']}"
                if uid not in self.x.nodes:
                    self.x.nodes[uid]={'id':uid,'kind':'definition_origin','name':relative,'path':relative,
                        'line':pos['line']+1,'utf16_column':pos['character']+1,'language':'rust',
                        'resolution':'macro_or_unindexed_input_declaration','runtime_execution':'not_observed'}
                result.append(uid)
            else:result.append(self.external(path,selected,source))
        return sorted(set(result))

    def origins(self,uid,context):
        found=set();seen=set();pending=[uid]
        while pending and len(seen)<200:
            current=pending.pop()
            if current in seen:continue
            seen.add(current);node=self.x.nodes[current]
            if node['kind'] in {'callable','external_symbol'}:found.add(current);continue
            pending.extend(self.flow.get(current,set())|self.bindings.get((context,current),set()))
        return found

    def context(self,workspace,configuration,index):
        uid='rust:context:'+quote(json.dumps([workspace,configuration],sort_keys=True,separators=(',',':')),safe='')
        self.x.nodes[uid]={'id':uid,'kind':'analysis_context','name':configuration['target'],
            'path':workspace,'line':1,'language':'rust','workspace':workspace,**configuration,
            'runtime_execution':'not_observed'}
        self.context_ids.append(uid);return uid

    def link_context(self,client,context):
        call_results={}
        for uid,(path,token) in list(self.x.references.items()):
            record=self.x.nodes[uid]
            try:
                targets=self.targets(client.at('textDocument/definition',path,self.x.position(path,token)),uid)
            except (RuntimeError,TimeoutError) as error:
                record.setdefault('native_errors',[]).append({'context':context,'message':str(error)});targets=[]
            if record['kind']=='call_site':
                call_results[uid]=targets;continue
            for target in targets:
                kind=self.x.nodes[target]['kind']
                if record['kind']=='module_reference':
                    self.edge(uid,target,'IMPORTS_SYMBOL',context)
                    target_path=self.x.nodes[target]['path']
                    module=next((n['id'] for n in self.x.nodes.values() if n['kind']=='code_module' and n['path']==target_path),None)
                    if module and kind!='external_symbol':self.edge(uid,module,'IMPORTS_MODULE',context)
                elif record['kind']=='macro_site':
                    self.edge(uid,target,'MACRO_DEFINITION_ORIGIN',context)
                    declaration=self.x.nodes[target].get('external_declaration',{})
                    if declaration.get('package') in {'alloc','std','core'} and declaration.get('name') in {'format','format_args'}:
                        self.format_arguments(client,uid,context)
                else:
                    self.bindings[(context,uid)].add(target);self.edge(uid,target,'READS_BINDING',context)
        # Writes are potential source values, not an assumed last assignment.
        for edge in list(self.x.edges):
            if edge['kind']=='WRITES_VALUE':
                for binding in self.bindings.get((context,edge['source']),()):
                    self.flow[binding].add(edge['target'])
        for uid,targets in call_results.items():
            node=self.x.nodes[uid];possible=set();external=set();traits=set();origin_only=[]
            for target in targets:
                target_node=self.x.nodes[target]
                if target_node.get('trait_member'):
                    traits.add(target);self.edge(uid,target,'DISPATCHES_TRAIT_MEMBER',context,status='candidate')
                    if target_node.get('definition'):possible.add(target)
                    path,token=self.x.references[uid]
                    implementations=self.targets(client.at('textDocument/implementation',path,self.x.position(path,token)),uid)
                    possible.update(t for t in implementations if self.x.nodes[t]['kind']=='callable')
                elif target_node['kind']=='external_symbol':external.add(target)
                elif target_node['kind']=='callable':possible.add(target)
                elif target_node['kind'] in {'binding','parameter','value'}:
                    self.edge(uid,target,'CALLS_BOUND_VALUE',context,status='candidate')
                    possible.update(t for t in self.origins(target,context) if self.x.nodes[t]['kind']=='callable')
                else:origin_only.append(target);self.edge(uid,target,'DEFINITION_ORIGIN',context,status='requires_expansion_or_input')
            self.calls[uid][context]={'targets':sorted(possible),'external':sorted(external),'trait_dispatch':bool(traits),
                'reason':None if possible or external else 'macro_or_unindexed_definition' if origin_only else
                    'no_callable_in_analysis_context_or_dynamic_binding'}
            for target in external:self.edge(uid,target,'EXTERNAL_CALL_REFERENCE',context,status='external_declaration')
            for argument in node['arguments']:
                for target in self.origins(argument,context):
                    if self.x.nodes[target]['kind']=='callable':self.edge(uid,target,'PASSES_CALLBACK',context,status='source_callback_reference',argument=argument)

    def format_arguments(self,client,uid,context):
        """Only native-bound standard format macros give tokens value semantics."""
        for edge in list(self.x.edges):
            if edge['source']!=uid or edge['kind']!='MACRO_TOKEN':continue
            value=edge['target'];node=self.x.nodes[value]
            self.edge(uid,value,'FORMAT_ARGUMENT',context,status='verified_standard_format_reference')
            if node['syntax'] not in {'string_literal','raw_string_literal'}:continue
            path,literal=self.x.syntax[value];source=text(literal)
            for match in re.finditer(r'\{([A-Za-z_][A-Za-z_0-9]*)(?:[^{}]*)\}',source):
                if match.start()>0 and source[match.start()-1]=='{' or match.end()<len(source) and source[match.end()]=='}':continue
                offset=literal.start_byte+len(source[:match.start(1)].encode('utf-8'));raw=self.x.units[path]['raw']
                line=raw[:offset].count(b'\n');prefix=raw[raw.rfind(b'\n',0,offset)+1:offset].decode('utf-8')
                position={'line':line,'character':len(prefix.encode('utf-16-le'))//2}
                capture=uid+':capture:'+str(offset)
                if capture not in self.x.nodes:
                    self.x.nodes[capture]={'id':capture,'kind':'value','name':match[1],'expression':match[1],
                        'path':path,'line':line+1,'column':len(prefix)+1,'language':'rust','syntax':'format_capture',
                        'runtime_execution':'not_observed','resolution':'native_standard_format_capture'}
                    self.x.syntax[capture]=(path,literal)
                self.edge(uid,capture,'FORMAT_ARGUMENT',context,status='verified_standard_format_reference')
                targets=self.targets(client.at('textDocument/definition',path,position),capture)
                for target in targets:
                    self.bindings[(context,capture)].add(target);self.edge(capture,target,'READS_BINDING',context)

    def finalize_calls(self):
        for uid,node in list(self.x.nodes.items()):
            if node['kind']!='call_site':continue
            results=self.calls.get(uid,{})
            target_sets={tuple(row['targets']) for row in results.values()}
            unique=(len(results)==len(self.context_ids) and len(target_sets)==1 and len(next(iter(target_sets),()))==1
                and not any(r['trait_dispatch'] for r in results.values()))
            node['resolutions']=[{'context':context,**row} for context,row in results.items()]
            node['resolution']=('inferred_unique' if unique else 'candidate' if any(r['targets'] for r in results.values()) else
                'external_reference' if any(r['external'] for r in results.values()) else 'unresolved')
            if node['resolution']=='unresolved':node['reason']='rust_native_context_unavailable' if not results else 'no_callable_in_analysis_context_or_dynamic_binding'
            for context,row in results.items():
                for target in row['targets']:
                    self.edge(uid,target,'STATIC_CALL_TARGET' if unique else 'STATIC_CALL_CANDIDATE',context,
                        status='inferred' if unique else 'candidate',basis='rust_analyzer_definition_and_bound_value')
                    parameters=self.x.parameters.get(target,[]);arguments=list(node['arguments'])
                    if node.get('receiver') and parameters and self.x.nodes[parameters[0]].get('self_parameter'):
                        arguments.insert(0,node['receiver'])
                    for argument,parameter in zip(arguments,parameters):
                        self.edge(argument,parameter,'BINDS_ARGUMENT',context,status='candidate' if not unique else 'inferred',call=uid)
                    for returned in self.returned.get(target,()):
                        self.edge(uid,returned,'CALL_RETURN_SOURCE',context,status='candidate',call=uid)

    def run(self,emit=None,contexts=None):
        metadata=discover(self.root,self.paths);self.x.diagnostics.extend(metadata['diagnostics'])
        if not metadata['workspaces']:
            self.x.diagnostics.append({'kind':'rust_crate_context_missing','paths':sorted(self.x.units),'required':True})
        components={name:tool_output([binary(name),'--version'],self.root).strip() for name in ('cargo','rustc','rust-analyzer') if available(name)}
        if contexts is None:
            contexts=[]
            for workspace in metadata['workspaces']:
                local={**metadata,'packages':[p for p in metadata['packages'] if p['workspace']==workspace]}
                matrix,diagnostics=configuration_matrix(self.root,self.paths,local)
                self.x.diagnostics.extend({**d,'workspace':workspace} for d in diagnostics)
                contexts.extend((workspace,c) for c in matrix)
        if not available('rust-analyzer'):
            self.x.diagnostics.append({'kind':'rust_analyzer_missing','required':True});contexts=[]
        self.output.mkdir(parents=True,exist_ok=True)
        for index,(workspace,configuration) in enumerate(contexts):
            context=self.context(workspace,configuration,index)
            try:
                with Client(binary('rust-analyzer'),self.root,str(self.root/workspace),self.output/f'rust-{index:03}.log',
                        cargo=cargo_options(configuration,locked=any(Path(p).name=='Cargo.lock' for p in self.paths))) as client:
                    self.link_context(client,context)
                    states=[e['params'] for e in client.events if e.get('method')=='experimental/serverStatus']
                    self.x.nodes[context]['server_health']=states[-1]['health'] if states else 'not_reported'
                    if states and states[-1]['health']!='ok':
                        self.x.diagnostics.append({'kind':'rust_context_incomplete','context':context,'required':True})
            except (ValueError,OSError,EOFError,RuntimeError,TimeoutError) as error:
                self.x.diagnostics.append({'kind':'rust_context_failed','workspace':workspace,'context':context,'message':str(error),'required':True})
            if emit:emit({'workspace':workspace,'context':index,'nodes':len(self.x.nodes),'edges':len(self.x.edges)})
        self.finalize_calls();result=self.x.build();result.update(extractor='rust_tree_sitter_rust_analyzer',components=components,cargo=metadata)
        result['limits'].extend(['source_context_matrix_is_not_supported_build_matrix','native_missing_definitions_do_not_prove_independence'])
        return result


def analyze(root,paths,parser,*,output=None,emit=None,contexts=None):
    if output is not None:return Linker(root,paths,parser,output).run(emit,contexts)
    with tempfile.TemporaryDirectory(prefix='rust-analysis-') as directory:
        return Linker(root,paths,parser,directory).run(emit,contexts)
