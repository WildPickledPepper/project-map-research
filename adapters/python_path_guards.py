"""Source predicates needed to reach a position after structured transfers."""
import ast


class SourceGuards:
    def __init__(self,paths):self.paths=paths;self.memo={}

    def branch(self,test,polarity):
        return {'test':self.paths.ast_ids.get(id(test)),'line':test.lineno,'polarity':polarity}

    def transfers(self,statement,when=()):
        if isinstance(statement,(ast.Return,ast.Raise,ast.Break,ast.Continue)):
            return [{'kind':type(statement).__name__,'line':statement.lineno,'when':list(when)}]
        if isinstance(statement,ast.If):
            rows=[]
            for polarity,body in ((True,statement.body),(False,statement.orelse)):
                for child in body:rows.extend(self.transfers(child,when+(self.branch(statement.test,polarity),)))
            return rows
        # Transfers inside a prior loop do not necessarily skip this later
        # position. Context managers/try can also alter exception flow.
        return []

    def at(self,uid):
        if uid in self.memo:return self.memo[uid]
        path=self.paths.nodes[uid]['path'];child=self.paths.ast.get(uid);result=[]
        while child is not None:
            parent=self.paths.parents.get(id(child))
            if parent is None:break
            if isinstance(parent,(ast.If,ast.IfExp)):
                polarity=(True if child in parent.body else False if child in parent.orelse else None) if isinstance(parent,ast.If) else (
                    True if child is parent.body else False if child is parent.orelse else None)
                if polarity is not None:result.append({'kind':'enclosing_source_branch','path':path,**self.branch(parent.test,polarity)})
            for field in ('body','orelse','finalbody'):
                body=getattr(parent,field,None)
                if not isinstance(body,list) or child not in body:continue
                for prior in body[:body.index(child)]:
                    for transfer in self.transfers(prior):
                        result.append({'kind':'preceding_control_transfer_not_taken','path':path,
                            'transfer':transfer['kind'],'line':transfer['line'],'when':transfer['when']})
            if isinstance(parent,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda,ast.ClassDef)):break
            child=parent
        self.memo[uid]=result
        return result
