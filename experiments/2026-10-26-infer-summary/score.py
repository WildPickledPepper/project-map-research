"""Check frozen effects by reading upstream values; never compose or solve them."""
import argparse
import json
from pathlib import Path


def walk(value):
    yield value
    if isinstance(value,dict):
        for item in value.values():yield from walk(item)
    elif isinstance(value,list):
        for item in value:yield from walk(item)


def score(filename):
    records=json.loads(filename.read_text());procedures={}
    for proc,payload in records:
        if proc[0]!='C':continue
        name=proc[1]['c_name'][0]
        if name in procedures:raise ValueError('Overloaded fixture procedure needs exact native identity')
        procedures[name]=dict(payload)['pulse']['main']['pre_post_list']
    def states(name):
        return [state for kind,state in procedures[name] if kind=='ContinueProgram']
    def binding(state,phase,name):
        return next(value[1] for variable,value in state[phase]['stack']
                    if variable[0]=='ProgramVar' and variable[1]['plain']==name)
    def step(state,phase,address,kind,field=None):
        values=[value[0] for access,value in dict(state[phase]['heap']).get(address,[])
                if access[0]==kind and (field is None or access[1]['field_name']==field)]
        if len(values)!=1:raise ValueError('Expected one native heap edge in the frozen fixture')
        return values[0]
    def read(state,phase,name):return step(state,phase,binding(state,phase,name),'Dereference')
    def clean(state):
        return not state['unknown_values'] and not state['skipped_calls'] and not any(
            isinstance(item,list) and item and item[0]=='UnknownEffect' for item in walk(state))
    checks=[]
    def check(name,relation):
        try:
            cases=states(name);passed=bool(cases) and all(relation(s) for s in cases)
            details={'states':len(cases),'unknown_states':sum(not clean(s) for s in cases)}
        except (ValueError,KeyError,StopIteration,TypeError) as error:
            passed=False;details={'error':type(error).__name__}
        checks.append({'case':name,'passed':passed,**details})
    for name in ('direct','composed','through_global'):
        check(name,lambda s:clean(s) and read(s,'post','return')==read(s,'pre','input'))
    check('borrow',lambda s:clean(s) and read(s,'post','return')==read(s,'pre','state'))
    check('write',lambda s:clean(s) and
          step(s,'post',step(s,'post',read(s,'post','state'),'FieldAccess','value'),'Dereference')==read(s,'pre','input'))
    check('read',lambda s:clean(s) and read(s,'post','return')==
          step(s,'pre',step(s,'pre',read(s,'pre','state'),'FieldAccess','value'),'Dereference'))
    def zero_return(state):
        target=read(state,'post','return')
        return clean(state) and any(value==target and const==['Const',{'num':'0','den':'1'}]
                                    for const,value in state['path_condition']['phi']['term_eqs'])
    for name in ('isolated','after_copy'):check(name,zero_return)
    selected=states('select')
    checks.append({'case':'select','passed':len(selected)==2 and
        {read(s,'post','return')==read(s,'pre','first') for s in selected}=={False,True} and
        all(clean(s) and s['path_condition']['conditions'] and
            read(s,'post','return') in {read(s,'pre','first'),read(s,'pre','second')} for s in selected),
        'states':len(selected)})
    callback=states('through_callback')
    checks.append({'case':'callback_unknown_preserved','passed':bool(callback) and all(any(
        isinstance(item,list) and item and item[0]=='UnknownEffect' for item in walk(s)) for s in callback)})
    return {'schema':'infer-frozen-effect-checks/1','checks':checks,'passed':all(c['passed'] for c in checks),
            'scope':'fixture native summaries only; not original SVF value-flow equivalence or whole-project acceptance'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=score(args.input);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
