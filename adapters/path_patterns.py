"""Match full lexical paths against directory-domain variables, never basenames."""
from pathlib import PurePosixPath,PureWindowsPath


def root_identity(value):
    base=value.get('base')
    if base is None:return ('relative',)
    if base['kind'] in {'source_root','canonical_source_root'}:return ('source',)
    if base['kind']=='literal_anchor':return ('literal_anchor',base['value'])
    # Other symbolic roots require explicit context bindings; their spelling
    # does not establish a shared deployment/build directory.
    return (base['kind'],str(base))


def match(pattern,concrete,*,prefix=False,bindings=None,allow_unverified_membership=False):
    if pattern.get('unresolved') or concrete.get('unresolved') or pattern['style']!=concrete['style']:return None
    if root_identity(pattern)!=root_identity(concrete):return None
    expected=pattern['segments'];actual=concrete['segments'];environment=dict(bindings or {});domains={}
    if any(not isinstance(p,str) for p in actual) or len(expected)>len(actual) or not prefix and len(expected)!=len(actual):return None
    for index,(piece,text) in enumerate(zip(expected,actual)):
        if isinstance(piece,str):
            if piece!=text:return None
        elif piece.get('kind')=='directory_entry_name':
            if text in {'.','..',''} or '/' in text or concrete['style']=='windows' and '\\' in text:return None
            variable=piece['variable']
            if variable in environment and environment[variable]!=text:return None
            domains[variable]={**piece['directory'],'style':pattern['style'],'unresolved':[]}
            environment[variable]=text
        else:return None
    membership=[]
    for variable,domain in domains.items():
        directory=instantiate(domain,environment)
        member=directory['segments']+[environment[variable]] if directory else None
        proven=directory is not None and root_identity(directory)==root_identity(concrete) and actual[:len(member)]==member
        if not proven and not allow_unverified_membership:return None
        membership.append({'kind':'directory_entry_membership','variable':variable,'value':environment[variable],
            'directory':directory or domain,'basis':'artifact_path_prefix' if proven else 'requires_directory_enumeration_evidence'})
    return {'bindings':environment,'suffix':actual[len(expected):],'membership_conditions':membership}


def instantiate(pattern,bindings,*,suffix=()):
    segments=[]
    for piece in pattern['segments']:
        if isinstance(piece,str):segments.append(piece)
        elif piece.get('kind')=='directory_entry_name' and piece['variable'] in bindings:
            segments.append(bindings[piece['variable']])
        else:return None
    value={**pattern,'segments':segments+list(suffix)};value.pop('display_path',None)
    if value.get('unresolved'):return None
    value['relative_path']='/'.join(value['segments'])
    base=value.get('base');value['resolution']='symbolic_base' if base and base['kind']!='literal_anchor' else 'constant';value['path']=None
    if value['resolution']=='constant':
        cls=PureWindowsPath if value['style']=='windows' else PurePosixPath
        anchor=base['value'] if base else '';value['path']=str(cls(anchor,*value['segments'])) if anchor or value['segments'] else ''
    return value
