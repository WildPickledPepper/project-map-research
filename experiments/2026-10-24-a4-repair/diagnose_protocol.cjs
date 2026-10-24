/* Diagnostic replay: observes forwarding events without changing source rules. */
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const base=path.resolve(__dirname,'../../adapters/typescript_protocol_flow.cjs');
const source=fs.readFileSync(base,'utf8').replace("if(item.boundaries.length){item.status='transport_found';consumers.push(item);}",
  "if(item.boundaries.length){item.status='transport_found';consumers.push(item);}else if(diagnostics.filter(d=>d.kind==='forwarding_trace').length<2)diagnostics.push({kind:'forwarding_trace',consumer:item.name,events:item.events});");
const replay=new Module(base,module);replay.filename=base;replay.paths=module.paths;replay._compile(source,base);
const [root,manifest,typescript,output]=process.argv.slice(2);
const g=replay.exports.analyzeProtocol(require(path.resolve(typescript)),path.resolve(root),JSON.parse(fs.readFileSync(manifest,'utf8')).files.map(f=>f.path));
if(fs.existsSync(output))throw Error('Use a new output');fs.writeFileSync(output,JSON.stringify(g.protocol.diagnostics.filter(d=>d.kind==='forwarding_trace'),null,2));
