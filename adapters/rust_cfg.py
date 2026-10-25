"""Three-valued source cfg selection within a recorded Rust analysis context."""
import json
import re


def evaluate(expression,context):
    if len(expression)>8192:return None
    tokens=[];position=0
    while position<len(expression):
        if expression[position:].isspace():break
        match=re.match(r'\s*(?:([\w]+)|("(?:[^"\\]|\\.)*")|([=(),]))',expression[position:])
        if not match:return None
        tokens.append(next(g for g in match.groups() if g is not None));position+=match.end()
        if len(tokens)>256:return None
    index=0;flags=set();values={}
    for flag in context.get('cfg',[]):
        key,sep,value=flag.partition('=')
        if not sep:flags.add(key.strip());continue
        try:values.setdefault(key.strip(),set()).add(json.loads(value))
        except (ValueError,TypeError):pass
    def parse(depth=0):
        nonlocal index
        if depth>32 or index>=len(tokens):raise ValueError('cfg expression budget')
        name=tokens[index];index+=1
        if not name.isidentifier():raise ValueError('cfg identifier')
        if index<len(tokens) and tokens[index]=='(':
            index+=1;args=[]
            while index<len(tokens) and tokens[index]!=')':
                args.append(parse(depth+1))
                if index<len(tokens) and tokens[index]==',':index+=1
                elif index<len(tokens) and tokens[index]!=')':raise ValueError('cfg separator')
            if index>=len(tokens):raise ValueError('unclosed cfg')
            index+=1
            if name=='not' and len(args)==1:return None if args[0] is None else not args[0]
            if name=='all':return False if False in args else None if None in args else True
            if name=='any':return True if True in args else None if None in args else False
            return None
        if index<len(tokens) and tokens[index]=='=':
            index+=1
            if index>=len(tokens):raise ValueError('cfg value')
            value=json.loads(tokens[index]);index+=1
            if not isinstance(value,str):return None
            if name=='feature':return True if any(f.rsplit('/',1)[-1]==value for f in context.get('features',[])) else None
            return value in values.get(name,set()) if name.startswith('target_') or name in values else None
        return True if name in flags else False if name in {'windows','unix','test','debug_assertions','proc_macro'} else None
    try:
        result=parse();return result if index==len(tokens) else None
    except (ValueError,IndexError,TypeError):return None


def conditions_active(guards,context):
    verdicts=[]
    for guard in guards:
        if guard.get('kind')!='rust_attribute':continue
        match=re.fullmatch(r'#\s*\[\s*cfg\((.*)\)\s*\]',guard['expression'],re.S)
        verdicts.append(evaluate(match[1],context) if match else None)
    return False if False in verdicts else None if None in verdicts else True
