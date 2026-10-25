"""Language-neutral symbolic filesystem paths, retaining unresolved operations.

No filesystem access, symlink resolution or analyzed-code execution occurs here.
Native-language adapters must establish library API identity before using terms.
"""
from pathlib import PurePosixPath, PureWindowsPath


def literal(value): return {'op':'literal','value':value}
def symbol(source, *, kind='parameter'): return {'op':'symbol','source':source,'kind':kind}
def unknown(source, reason): return {'op':'unknown','source':source,'reason':reason}
def operation(name, *arguments, **metadata): return {'op':name,'args':list(arguments),**metadata}


def normalize(term, style, *, max_candidates=32):
    """Expand bounded choices, yielding constant paths or paths relative to a base.

    ``segments`` are lexical components, so '..' stays explicit. Unknown values
    remain terms and cannot masquerade as an exact executable path.
    """
    path_type=PureWindowsPath if style=='windows' else PurePosixPath
    memo={};scalar_memo={}
    def incomplete(value, reason, source=None):
        value={**value,'segments':list(value['segments']),'unresolved':list(value['unresolved'])}
        item={'reason':reason}
        if source is not None:item['source']=source
        if item not in value['unresolved']:value['unresolved'].append(item)
        return value
    def blank():return {'base':None,'segments':[],'conditions':[],'unresolved':[]}
    def text_path(text):
        parsed=path_type(text);parts=list(parsed.parts);base=None
        if parsed.anchor:base={'kind':'literal_anchor','value':parsed.anchor};parts=parts[1:]
        return {**blank(),'base':base,'segments':parts}
    def bounded(rows):
        if len(rows)>max_candidates:return [incomplete(blank(),'path_candidate_budget_exhausted')]
        return rows
    def evaluate(current):
        key=id(current)
        if key not in memo:memo[key]=(current,bounded(evaluate_uncached(current)))
        return memo[key][1]
    def scalar(current):
        key=id(current)
        if key not in scalar_memo:
            values=scalar_uncached(current)
            scalar_memo[key]=(current,values if len(values)<=max_candidates else [(None,[{'kind':'path_scalar_candidate_budget'}])])
        return scalar_memo[key][1]
    def scalar_uncached(current):
        if current['op']=='literal' and isinstance(current.get('value'),str):return [(current['value'],[])]
        if current['op']=='choice':return [(value,conditions+choice.get('conditions',[])) for choice in current['choices'] for value,conditions in scalar(choice['value'])]
        if current['op'] in {'some','unwrap','borrow','clone','to_path_buf','as_path'}:return scalar(current['args'][0])
        return [(None,[])]
    def evaluate_uncached(current):
        op=current['op']
        if op=='literal':
            if not isinstance(current['value'],str):return [incomplete(blank(),'non_string_path_literal')]
            return [text_path(current['value'])]
        if op=='symbol':return [{**blank(),'base':{'kind':current['kind'],'source':current['source']}}]
        if op=='current_executable':
            return [{**blank(),'base':{'kind':'current_executable','source':current['source'],
                                      'workspace':current.get('workspace'),'call_stack':current.get('call_stack',[])}}]
        if op=='unknown':return [incomplete(blank(),current['reason'],current.get('source'))]
        if op=='choice':
            rows=[]
            for choice in current['choices']:
                for value in evaluate(choice['value']):
                    rows.append({**value,'conditions':value['conditions']+choice.get('conditions',[])})
            return bounded(rows)
        if op=='none':return []
        args=current.get('args',[])
        if op in {'some','clone','as_path','to_path_buf','borrow'}:
            return evaluate(args[0])
        if op in {'unwrap','assume_pattern'}:
            condition={'kind':'successful_unwrap' if op=='unwrap' else 'binding_pattern_selected','source':current.get('source')}
            if 'pattern' in current:condition['pattern']=current['pattern']
            return [{**v,'conditions':v['conditions']+[condition]} for v in evaluate(args[0])]
        if op in {'parent','pop'}:
            rows=[]
            for value in evaluate(args[0]):
                if value['segments']:rows.append({**value,'segments':value['segments'][:-1]})
                elif value['base'] and value['base']['kind']=='current_executable':
                    rows.append({**value,'base':{**value['base'],'kind':'current_executable_directory'}})
                elif value['base'] and value['base']['kind']!='literal_anchor':
                    rows.append({**value,'base':{'kind':'parent_of','base':value['base']}} if op=='parent' else incomplete(value,'pop_requires_known_file_name'))
                elif op=='pop':rows.append(value)
                # Root/empty paths have no parent, matching Path::parent's Option.
            return rows
        if op=='join':
            rows=[]
            for value in evaluate(args[0]):
                for piece in evaluate(args[1]):
                    current_value={**value,'conditions':value['conditions']+piece['conditions']}
                    if piece['unresolved'] or piece['base'] and piece['base']['kind']!='literal_anchor':
                        rows.append(incomplete(current_value,'dynamic_path_component',args[1].get('source')));continue
                    anchor=piece['base']['value'] if piece['base'] else ''
                    parsed=path_type(anchor,*piece['segments'])
                    if style=='windows' and (parsed.drive and not parsed.root or parsed.root and not parsed.drive):
                        rows.append(incomplete(current_value,'windows_drive_or_root_relative_component',args[1].get('source')));continue
                    if parsed.is_absolute():
                        rows.append({**piece,'conditions':current_value['conditions']});continue
                    rows.append({**current_value,'segments':value['segments']+piece['segments']})
            return bounded(rows)
        if op in {'set_extension','set_file_name'}:
            rows=[]
            combinations=[({**value,'conditions':value['conditions']+conditions},text)
                          for value in evaluate(args[0]) for text,conditions in scalar(args[1])]
            for value,text in combinations:
                if text is None:
                    rows.append(incomplete(value,'dynamic_'+op,args[1].get('source')));continue
                if value['unresolved']:
                    rows.append(incomplete(value,'operation_after_unresolved_path_component'));continue
                if op=='set_file_name':
                    if not value['segments'] and value['base'] and value['base']['kind']!='literal_anchor' and not path_type(text).is_absolute():
                        rows.append(incomplete(value,'set_file_name_requires_known_parent'));continue
                    base={**value,'segments':value['segments'][:-1] if value['segments'] else []}
                    # set_file_name accepts path fragments; use push semantics.
                    wrapped=operation('join',literal(''),literal(text))
                    pieces=evaluate(wrapped)
                    for piece in pieces:
                        rows.append({**base,'base':piece['base'] or base['base'],
                                     'segments':piece['segments'] if piece['base'] else base['segments']+piece['segments'],
                                     'unresolved':piece['unresolved']})
                    continue
                if '/' in text or style=='windows' and '\\' in text:
                    rows.append(incomplete(value,'invalid_extension_contains_separator'));continue
                if not value['segments']:
                    rows.append(value if value['base'] is None or value['base']['kind']=='literal_anchor' else incomplete(value,'extension_requires_known_file_name'));continue
                name=value['segments'][-1]
                if name in {'.','..'}:rows.append(value);continue
                dot=name.rfind('.');stem=name[:dot] if dot>0 else name
                replacement=stem+('.'+text if text else '')
                rows.append({**value,'segments':value['segments'][:-1]+[replacement]})
            return bounded(rows)
        return [incomplete(blank(),'unresolved_path_operation:'+op,current.get('source'))]
    if style not in {'windows','posix'}:return [{**blank(),'style':style,'resolution':'unresolved','relative_path':None,'path':None,
                                               'unresolved':[{'reason':'target_path_style_unavailable'}]}]
    rows=evaluate(term)
    for row in rows:
        row['style']=style
        row['resolution']='unresolved' if row['unresolved'] else 'symbolic_base' if row['base'] and row['base']['kind']!='literal_anchor' else 'constant'
        row['relative_path']='/'.join(row['segments']) if not row['unresolved'] else None
        row['path']=None
        if row['resolution']=='constant':
            anchor=row['base']['value'] if row['base'] else ''
            row['path']=str(path_type(anchor,*row['segments'])) if anchor or row['segments'] else ''
    return rows


def expression_dag(term, *, max_nodes=1024):
    """Serialize shared expression nodes once; branch merges can share prefixes."""
    terms=[];seen={}
    def visit(current):
        key=id(current)
        if key in seen:return {'ref':seen[key]}
        index=len(terms);seen[key]=index
        if index>=max_nodes:raise ValueError('path_expression_node_budget')
        terms.append(None)
        result={k:v for k,v in current.items() if k not in {'args','choices','items'}}
        if 'args' in current:result['args']=[visit(a) for a in current['args']]
        if 'choices' in current:result['choices']=[{**c,'value':visit(c['value'])} for c in current['choices']]
        if 'items' in current:result['items']=[visit(a) for a in current['items']]
        terms[index]=result
        return {'ref':index}
    root=visit(term)
    return {'schema':'path-expression-dag/1','root':root,'terms':terms}
