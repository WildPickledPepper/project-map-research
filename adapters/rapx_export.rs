//! Export RAPx's existing graphs and alias summaries. No analysis transfer rules.
use std::{fs, path::Path};
use serde_json::{json,Value};
use rustc_middle::{mir::{Operand,TerminatorKind,Const},ty::{TyCtxt,TyKind}};
use rustc_span::{Span,FileName,def_id::LOCAL_CRATE};
use super::default::DataflowAnalyzer;
use crate::analysis::{Analysis,alias::{AliasAnalysis,mfp::MfpAliasAnalyzer}};

fn location(tcx: TyCtxt<'_>, span: Span) -> Value {
    if span.is_dummy() {return Value::Null;}
    let p=tcx.sess.source_map().lookup_char_pos(span.lo());
    let file=match &p.file.name {FileName::Real(real)=>real.local_path().map(|p|p.canonicalize().unwrap_or_else(|_|p.to_path_buf()).to_string_lossy().into_owned()),_=>None};
    json!({"file":file,"line":p.line,"column":p.col_display+1})
}

pub fn write(analyzer: &DataflowAnalyzer<'_>) {
    let Ok(directory)=std::env::var("PROJECT_MAP_RAPX_EXPORT") else {return;};
    let tcx=analyzer.tcx;
    let mut aliases=MfpAliasAnalyzer::new(tcx);aliases.run();
    let summaries=aliases.get_local_fn_alias();
    let mut functions=Vec::new();
    for (def,graph) in &analyzer.graphs {
        let body=tcx.optimized_mir(*def);
        let locals:Vec<_>=graph.nodes.iter_enumerated().map(|(idx,node)|json!({
            "id":idx.as_usize(),"location":location(tcx,node.span),
            "operations":node.ops.iter().map(|op|format!("{op:?}")).collect::<Vec<_>>(),
            "sequence":node.seq
        })).collect();
        let edges:Vec<_>=graph.edges.iter().map(|edge|json!({
            "source":edge.src.as_usize(),"target":edge.dst.as_usize(),"operation":format!("{:?}",edge.op),
            "block":edge.block,"statement":edge.statement_index,"sequence":edge.seq
        })).collect();
        let mut calls=Vec::new();
        for (block,data) in body.basic_blocks.iter_enumerated() {
            let term=data.terminator();
            let TerminatorKind::Call{func,args,destination,..}=&term.kind else {continue;};
            let callee=if let Operand::Constant(c)=func {
                if let Const::Val(_,ty)=c.const_ {
                    if let TyKind::FnDef(id,_)=ty.kind() {Some(tcx.def_path_str(*id))} else {None}
                } else {None}
            } else {None};
            let native_arguments:Vec<_>=graph.edges.iter().filter(|e|e.block==block.as_usize()
                && e.statement_index==data.statements.len() && e.dst==destination.local).collect();
            let actuals:Vec<_>=args.iter().enumerate().map(|(idx,a)| {
              let mut result=match &a.node {
                Operand::Copy(p)|Operand::Move(p)=>json!({"local":p.local.as_usize(),"projection":format!("{:?}",p.projection)}),
                Operand::Constant(c)=>json!({"constant":format!("{:?}",c.const_)}),
                _=>json!({"unresolved_operand":format!("{:?}",a.node)})
              };
              result["native_value"]=if native_arguments.len()==args.len(){json!(native_arguments[idx].src.as_usize())}else{Value::Null};
              result
            }).collect();
            calls.push(json!({"callee":callee,"block":block.as_usize(),"statement":data.statements.len(),"arguments":actuals,
                "destination":destination.local.as_usize(),"destination_projection":format!("{:?}",destination.projection),
                "location":location(tcx,term.source_info.span)}));
        }
        let summary:Vec<_>=summaries.get(def).map(|s|s.aliases().iter().map(|a|json!({
            "left":a.left_local(),"right":a.right_local(),"left_fields":a.lhs_fields(),"right_fields":a.rhs_fields()
        })).collect()).unwrap_or_default();
        let names:Vec<_>=body.var_debug_info.iter().map(|v|json!({"name":v.name.to_string(),
            "value":format!("{:?}",v.value),"location":location(tcx,v.source_info.span)})).collect();
        functions.push(json!({"name":tcx.def_path_str(*def),"native_id":format!("{def:?}"),
            "location":location(tcx,graph.span),"arguments":graph.argc,"locals":locals,
            "edges":edges,"calls":calls,"alias_summary":summary,"debug_variables":names}));
    }
    fs::create_dir_all(&directory).unwrap();
    let crate_name=tcx.crate_name(LOCAL_CRATE).to_string();
    let report=json!({"schema":"rapx-native-export/1","crate":crate_name,"functions":functions,
        "source_root":std::env::var("PROJECT_MAP_SOURCE_ROOT").ok(),
        "source_commit":std::env::var("PROJECT_MAP_SOURCE_COMMIT").ok(),
        "context":std::env::var("PROJECT_MAP_CONTEXT").ok(),
        "upstream_revision":"974eb8e7f91e186720daffdfdf1125c3daf6c8cb",
        "algorithms":["RAPx DataflowAnalyzer","RAPx MfpAliasAnalyzer"]});
    fs::write(Path::new(&directory).join(format!("{crate_name}.json")),serde_json::to_vec(&report).unwrap()).unwrap();
}
