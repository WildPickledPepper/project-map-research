/* Automatic compiler root partitions. All supplied files remain available as
 * import dependencies; unrelated packages and test mocks are not global roots. */
const path=require('node:path');

function role(file){
  const parts=new Set(file.toLowerCase().split('/').slice(0,-1)),name=path.posix.basename(file).toLowerCase();
  if(['test','tests','__tests__','e2e','testing','fuzz','fixtures','mocks','__mocks__'].some(p=>parts.has(p)) || /[.](test|spec)[.]|^test_/.test(name))return 'test';
  if(['scripts','build','docker','ci','.github','.gitcode','pre-commit'].some(p=>parts.has(p)))return 'build_tool';
  return 'product';
}

function partition(files){
  const packages=files.filter(f=>path.posix.basename(f)==='package.json').map(f=>path.posix.dirname(f)).sort((a,b)=>b.length-a.length||a.localeCompare(b));
  const units=new Map();
  for(const file of [...files].sort())if(/\.tsx?$/.test(file)){
    const owner=packages.find(p=>p==='.'||file.startsWith(p+'/'))||'.',category=role(file),key=owner+':'+category;
    if(!units.has(key))units.set(key,{id:key,package_root:owner,role:category,root_files:[]});
    units.get(key).root_files.push(file);
  }
  return [...units.values()];
}

function merge(results,units,key){
  const first=results[0],combined={...first};
  const unique=values=>[...new Map(values.map(v=>[JSON.stringify(v),v])).values()];
  const nodes=new Map();for(const r of results)for(const n of r.nodes){
    const previous=nodes.get(n.id);if(previous&&JSON.stringify(previous)!==JSON.stringify(n))throw new Error('Conflicting node identity across analysis units: '+n.id);
    nodes.set(n.id,n);
  }
  combined.nodes=[...nodes.values()];
  for(const field of ['edges','coverage','diagnostics','limits','path_configs'])if(first[field])combined[field]=unique(results.flatMap(r=>r[field]));
  if(key){combined[key]={...first[key]};for(const field of Object.keys(first[key]))
    if(Array.isArray(first[key][field]))combined[key][field]=unique(results.flatMap(r=>r[key][field]));}
  combined.analysis_units=units;
  combined.compiler_options_origin='fixed_analysis_preset_per_package_role_not_product_tsconfig';
  combined.limits=unique([...combined.limits,'compiler_roots_partitioned_by_nearest_package_and_source_role',
    'test_files_in_one_package_not_proven_to_share_runtime','product_build_variants_not_reconstructed']);
  return combined;
}

module.exports={partition,merge};
