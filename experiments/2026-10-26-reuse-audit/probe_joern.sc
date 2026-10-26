import io.shiftleft.semanticcpg.language.*
import io.joern.dataflowengineoss.language.*

@main def exec(): Unit = {
  importCpg(sys.env("PROJECT_MAP_AUDIT_CPG"))
  if (!cpg.metaData.overlays.l.contains("dataflowOss")) {
    run.ossdataflow
  }
  val cases = List("regular", "member", "isolated", "after_copy", "borrowed", "getter")
    .filter(name => cpg.method.nameExact(name).nonEmpty)
  val rows = cases.map { name =>
    val sources = cpg.method.nameExact(name).parameter.nameExact("input")
    val sinks = cpg.method.nameExact(name).call.nameExact("sink").argument(1)
    val paths = sinks.reachableByFlows(sources).l
    ujson.Obj("case" -> name, "path_count" -> paths.size,
      "paths" -> ujson.Arr.from(paths.map(p => ujson.Arr.from(p.elements.map(e => ujson.Str(e.toString))))))
  }
  val calls = cpg.call.filterNot(_.name.startsWith("<operator>")).l.map { c =>
    ujson.Obj("code" -> c.code, "target" -> c.methodFullName,
      "file" -> c.file.name.headOption.getOrElse(""), "line" -> c.lineNumber.getOrElse(0))
  }
  val result = ujson.Obj("schema" -> "reuse-joern-audit/1", "joern_version" -> "4.0.665",
    "origin" -> "native_cpg_and_oss_dataflow_on_authored_generic_source",
    "method_count" -> cpg.method.size,
    "methods" -> ujson.Arr.from(cpg.method.l.map(m => ujson.Obj("name" -> m.name, "full_name" -> m.fullName))),
    "overlays" -> ujson.Arr.from(cpg.metaData.overlays.l),
    "checks" -> ujson.Arr.from(rows), "calls" -> ujson.Arr.from(calls))
  os.write.over(os.Path(sys.env("PROJECT_MAP_AUDIT_OUTPUT")), ujson.write(result, indent = 2))
}
