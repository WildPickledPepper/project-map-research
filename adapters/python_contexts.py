"""Propagate main-guard source-root contexts through unchanged Jedi import inference."""
import ast
from collections import defaultdict,deque
from pathlib import Path


def main_guard(tree):
    for node in ast.walk(tree):
        if not isinstance(node,ast.If) or not isinstance(node.test,ast.Compare):continue
        test=node.test
        if len(test.ops)!=1 or not isinstance(test.ops[0],ast.Eq):continue
        values=[test.left,*test.comparators]
        if any(isinstance(v,ast.Name) and v.id=='__name__' for v in values) and any(isinstance(v,ast.Constant) and v.value=='__main__' for v in values):return True
    return False


def discover_contexts(root,units,environment):
    import jedi
    root=Path(root);origins=defaultdict(lambda:defaultdict(set));seen=set();cached={};diagnostics=[]
    queue=deque((path,tuple(unit['roots']),path) for path,unit in sorted(units.items()) if main_guard(unit['tree']))
    while queue:
        path,roots,entry=queue.popleft();key=(path,roots,entry)
        if key in seen:continue
        seen.add(key);origins[path][roots].add(entry)
        import_key=(path,roots)
        if import_key not in cached:
            unit=units[path];project=jedi.Project(root,sys_path=[str(root/r) for r in roots],smart_sys_path=False,load_unsafe_extensions=False)
            script=jedi.Script(unit['code'],path=unit['path'],project=project,environment=environment);targets=set()
            for node in ast.walk(unit['tree']):
                if not isinstance(node,(ast.Import,ast.ImportFrom)):continue
                for alias in node.names:
                    line=alias.end_lineno;column=len(unit['lines'][line-1].encode('utf-8')[:alias.end_col_offset].decode('utf-8'))
                    try:
                        for target in script.infer(line,column):
                            if target.module_path:
                                actual=target.module_path.resolve()
                                relative=actual.relative_to(root).as_posix() if actual.is_relative_to(root) else None
                                if relative in units:targets.add(relative)
                    except Exception as error:
                        diagnostics.append({'kind':'python_context_import_error','path':path,'line':line,'error_type':type(error).__name__,'message':str(error)})
            cached[import_key]=targets
        for target in sorted(cached[import_key]):queue.append((target,roots,entry))
    contexts={path:[{'roots':list(roots),'entry_paths':sorted(entries),'basis':'main_guard_imports'} for roots,entries in sorted(origins[path].items())]
              or [{'roots':unit['roots'],'entry_paths':[],'basis':'package_ancestors_and_repository'}] for path,unit in units.items()}
    return contexts,diagnostics


