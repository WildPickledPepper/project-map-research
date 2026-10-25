"""Resolve source aliases to explicitly modeled external library types."""
from collections import defaultdict
import re

from adapters.syntax_supplement import cpp_scope,parents,text,walk
from adapters.cpp_facts import scoped_name
from adapters.cpp_value_types import split_template


class LibraryTypes:
    JSON={'rapidjson::Value','rapidjson::Document','rapidjson::GenericValue','rapidjson::GenericDocument'}
    EXTERNAL=JSON|{'std::string','std::string_view','std::vector','rapidjson::StringBuffer','rapidjson::GenericStringBuffer',
                  'rapidjson::Writer','rapidjson::PrettyWriter','uWS::WebSocket','uWS::Loop',
                  'uWS::App','uWS::SSLApp','uWS::TemplatedApp','uWS::App::WebSocketBehavior','uWS::SSLApp::WebSocketBehavior'}

    def __init__(self,extractor):
        self.x=extractor;self.aliases=defaultdict(list)
        for path,unit in self.x.units.items():
            for node in walk(unit['tree'].root_node):
                if node.type!='alias_declaration':continue
                if any(p.type=='compound_statement' for p in parents(node)):continue
                name=text(node.child_by_field_name('name'));target=text(node.child_by_field_name('type'))
                scope=[scoped_name(s,path) for s in cpp_scope(node)]
                self.aliases['::'.join(scope+[name])].append({'path':path,'scope':scope,'target':target,'line':node.start_point[0]+1})

    def resolve(self,spelling,path,scope,seen=None):
        seen=set() if seen is None else seen
        atom=re.sub(r'\b(const|volatile|class|struct|typename)\b','',spelling).strip().strip('&* ').strip()
        head,args=split_template(atom)
        if head=='std::optional' and len(args)==1:return self.resolve(args[0],path,scope,seen)
        if head.startswith('::'):head=head[2:]
        if head in self.EXTERNAL:return {head}
        key=(head,path,tuple(scope))
        if key in seen:return set()
        seen=seen|{key};visible=self.x.visibility.get(path,{path})
        for length in range(len(scope),-1,-1):
            q='::'.join(scope[:length]+[head])
            choices=[a for a in self.aliases[q] if a['path'] in visible]
            if choices:
                values=[self.resolve(a['target'],a['path'],a['scope'],seen) for a in choices]
                # A conflicting or unresolved visible alias stays unresolved.
                return values[0] if values and values[0] and all(v==values[0] for v in values) else set()
            if q in self.x.classes:return set()
        candidates=set()
        for p in visible:
            for prefix,namespace in self.x.units[p]['using']:
                prefix='::'.join(prefix);current='::'.join(scope)
                if prefix and current!=prefix and not current.startswith(prefix+'::'):continue
                q=namespace+'::'+head
                if q in self.EXTERNAL:candidates.add(q)
        return candidates if len(candidates)==1 else set()

    def is_json(self,spelling,path,scope):return bool(self.resolve(spelling,path,scope)&self.JSON)
