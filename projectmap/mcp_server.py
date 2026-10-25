"""Read-only MCP access to the same CLI queries; no build or source-write tools."""
from typing import Any
from projectmap import __version__


def create_server(workspace):
    try:
        from mcp.server import MCPServer
        from mcp.types import ToolAnnotations
    except ImportError as error:
        raise ImportError('Install the skill wheel with the mcp extra to use serve') from error
    server=MCPServer('Project Map',version=__version__,instructions=(
        'Use map_status first. Query overview/search, then trace/impact and detail/source. '
        'Results are source facts and conditional candidates. Missing relationships mean unknown. '
        'Runtime claims require matching execution context. Historical assets are disabled.'))
    readonly=ToolAnnotations(read_only_hint=True,destructive_hint=False,idempotent_hint=True,open_world_hint=False)

    @server.tool(annotations=readonly,structured_output=True)
    def map_status()->dict[str,Any]:
        """Identify the active snapshot, selected commit and uncommitted changes before using the map."""
        return workspace.status()

    @server.tool(annotations=readonly,structured_output=True)
    def map_query(view:str,text:str='',start:str='',target:str='',kind:str='',module:str='',
                  path:str='',entity:str='',id:str='',pointer:str='',direction:str='out',
                  kinds:list[str]|None=None,depth:int=4,limit:int=20,cursor:str|None=None,
                  line:int|None=None,context:int=8,snapshot:str|None=None)->dict[str,Any]:
        """Query overview, search, entries, providers, neighbors, trace, impact, path, detail, diagnostics or source. Reuse returned snapshot and cursor for consistent pagination. Use entity=node/edge and id/pointer to inspect evidence."""
        return workspace.query(view,text=text,start=start or None,target=target or None,kind=kind or None,
            module=module or None,path=path or None,entity=entity or None,id=id or None,pointer=pointer,
            direction=direction,kinds=kinds,depth=depth,limit=limit,cursor=cursor,line=line,context=context,snapshot=snapshot)

    @server.tool(annotations=readonly,structured_output=True)
    def map_field_chain(start:str,field:list[str],limit:int=20,offset:int=0,snapshot:str|None=None,depth:int=16,seconds:float=30)->dict[str,Any]:
        """Compose request, producer, response-field and consumer evidence. field is a field path. Expensive graph expansion runs separately with a time limit; truncation is unknown coverage."""
        return workspace.explain(start,field,limit=limit,offset=offset,snapshot=snapshot,depth=depth,seconds=seconds)

    @server.tool(annotations=readonly,structured_output=True)
    def map_runtime(scenario:str|None=None,record_id:str|None=None,execution_context:dict|None=None,
                    limit:int=20,offset:int=0)->dict[str,Any]:
        """List captured scenarios. Supply record_id plus an explicit source/build/config/data/scenario context to validate overlay; listing alone cannot establish runtime applicability."""
        return workspace.runtime(record_id=record_id,context=execution_context,scenario=scenario,limit=limit,offset=offset)

    return server
