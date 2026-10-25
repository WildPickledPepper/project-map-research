"""Build version-pinned module and boundary scope ledgers; no inferred semantic edges."""
from collections import Counter,defaultdict
from contextlib import contextmanager
import json
from pathlib import Path,PurePosixPath
import re
import subprocess
import tomllib

from adapters.mechanism_inventory import MECHANISMS, signals
from adapters.repository_discovery import discover
from adapters.snapshot_inputs import commit
from adapters.snapshot_refresh import atomic_json
from adapters.source_scope import script_role_evidence, source_scope

SCHEMA='project-scope/1'
CONTAINERS={'modules','plugins','packages','services','apps','scripts'}
CODE={'.ts':'typescript','.tsx':'tsx','.mts':'typescript','.cts':'typescript','.js':'javascript','.jsx':'javascript',
    '.mjs':'javascript','.cjs':'javascript','.py':'python','.rs':'rust','.cpp':'cpp','.cc':'cpp','.cxx':'cpp',
    '.h':'cpp','.hpp':'cpp','.hh':'cpp','.hxx':'cpp','.c':'c','.sh':'shell','.ps1':'powershell','.bat':'batch',
    '.go':'go','.java':'java','.cs':'csharp','.kt':'kotlin','.kts':'kotlin','.swift':'swift',
    '.rb':'ruby','.php':'php','.lua':'lua','.ex':'elixir','.exs':'elixir','.scala':'scala'}
TEXT={'.json','.toml','.yaml','.yml','.ini','.cfg','.conf','.config','.cmake','.sql','.css','.scss','.sass','.less','.html','.htm','.txt'}
MANIFESTS={'package.json','Cargo.toml','pyproject.toml','setup.py','setup.cfg','CMakeLists.txt','Dockerfile'}


def parent(path):return str(PurePosixPath(path).parent)
def underneath(path,root):return root=='.' or path==root or path.startswith(root+'/')
def source_role(path,old_role):
    parts=PurePosixPath(path).parts
    if old_role in {'third_party','generated','test'}:return old_role
    if any('fuzz' in re.split(r'[-_.]',part.lower()) for part in parts[:-1]):return 'test'
    if parts[0] in {'docs','assets'}:return 'documentation_or_resource'
    if parts[0] in {'build','pre-commit','.github','.gitcode'} or 'build' in parts[:-1]:return 'build_support'
    if parts[0]=='docker':return 'deployment_support'
    return 'first_party'


def has_program_entry(text,language):
    if language=='python':
        return bool(source_scope(text,'<entry-review>',language)[0])
    if language=='rust':return bool(re.search(r'(?m)^\s*(?:pub\s+)?fn\s+main\s*\(',text))
    if language in {'cpp','c'}:return bool(re.search(r'(?m)^\s*(?:int|void)\s+main\s*\(',text))
    if language=='javascript':return bool(re.search(r'require\.main\s*===?\s*module|import\.meta\.main',text))
    return False


@contextmanager
def committed_text(source,revision,files,max_bytes):
    """Read selected blobs via one Git process; never execute checked-out code."""
    process=subprocess.Popen(['git','-C',str(source),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    texts={};states={}
    try:
        for row in files:
            path=row['path'];p=PurePosixPath(path)
            if row['mode'] not in {'100644','100755'}:states[path]='unsupported_git_mode';continue
            wanted=p.suffix.lower() in CODE or p.suffix.lower() in TEXT or p.name in MANIFESTS or not p.suffix
            if row['role'] in {'third_party','generated'}:states[path]='external_or_generated_inventory';continue
            if not wanted:states[path]='resource_inventory';continue
            if row['bytes'] is None or row['bytes']>max_bytes:states[path]='size_budget';continue
            process.stdin.write((revision+':'+path+'\n').encode('utf-8'));process.stdin.flush()
            header=process.stdout.readline().decode('ascii').split()
            if len(header)!=3 or header[1]!='blob':raise ValueError('Cannot read committed blob: '+path)
            raw=process.stdout.read(int(header[2]));separator=process.stdout.read(1)
            if separator!=b'\n':raise ValueError('Invalid Git blob framing')
            if b'\0' in raw:states[path]='binary_inventory';continue
            try:texts[path]=raw.decode('utf-8');states[path]='text_scanned'
            except UnicodeDecodeError:states[path]='non_utf8'
        process.stdin.close()
        if process.wait(timeout=30):raise ValueError(process.stderr.read().decode('utf-8',errors='replace'))
        yield texts,states
    finally:
        if process.poll() is None:process.kill();process.wait()
        if not process.stdin.closed:process.stdin.close()
        process.stdout.close();process.stderr.close()


def build_inventory(source,revision='HEAD',*,rules_version='unversioned',max_file_bytes=2*1024*1024):
    source=Path(source).resolve();revision=commit(source,revision);discovery=discover(source,revision)
    files=[{k:v for k,v in row.items() if k not in {'object','index','build_context'}} for row in discovery['files']]
    for row in files:
        row['structural_module']=row.pop('module');row['scope_role']=source_role(row['path'],row['role'])
        row['language']=CODE.get(PurePosixPath(row['path']).suffix.lower(),row.get('language'))
    with committed_text(source,revision,files,max_file_bytes) as (texts,states):
        return _inventory(revision,files,texts,states,rules_version)


def _inventory(revision,files,texts,states,rules_version):
    by_path={row['path']:row for row in files};paths=set(by_path);anchors=defaultdict(list);metadata=defaultdict(list);diagnostics=[]
    for path,evidence in script_role_evidence(texts).items():
        if by_path[path]['scope_role']=='first_party':
            by_path[path].update(scope_role='build_support',scope_role_evidence=evidence)
    def anchor(root,kind,path,line=1):
        evidence={'kind':kind,'path':path,'line':line}
        if evidence not in anchors[root]:anchors[root].append(evidence)
    anchor('.','repository_root','package.json' if 'package.json' in paths else min(paths))
    for row in files:
        path=row['path'];parts=PurePosixPath(path).parts
        if len(parts)>1:anchor(parts[0],'tracked_top_level',path)
        if row['scope_role'] in {'third_party','generated'}:continue
        if row['language'] in CODE.values():
            for i,part in enumerate(parts[:-2]):
                if part in CONTAINERS:anchor('/'.join(parts[:i+2]),'conventional_component_container',path)
        if PurePosixPath(path).name in MANIFESTS and path in texts:
            root=parent(path);anchor(root,'tracked_manifest',path)
            if path.endswith('package.json'):
                try:
                    package=json.loads(texts[path]);metadata[root].append({'path':path,'kind':'npm','name':package.get('name'),
                        'description':package.get('description'),'scripts':package.get('scripts',{}),
                        'main':package.get('main'),'exports':package.get('exports'),'bin':package.get('bin'),
                        'jupyterlab':package.get('jupyterlab')})
                except (ValueError,AttributeError) as error:diagnostics.append({'path':path,'reason':'invalid_package_manifest','detail':str(error)})
            elif path.endswith('Cargo.toml'):
                try:
                    cargo=tomllib.loads(texts[path]);metadata[root].append({'path':path,'kind':'cargo','package':cargo.get('package',{}),
                        'features':cargo.get('features',{}),'bin':cargo.get('bin',[]),'target':list(cargo.get('target',{}))})
                except ValueError as error:diagnostics.append({'path':path,'reason':'invalid_cargo_manifest','detail':str(error)})
    for path,text in texts.items():
        if by_path[path]['scope_role'] in {'third_party','generated'}:continue
        item=PurePosixPath(path)
        if by_path[path]['scope_role']=='first_party' and by_path[path]['language'] in CODE.values():
            enclosing=[root for root,evidence in anchors.items() if root!='.' and underneath(path,root)
                and any(e['kind'] in {'tracked_manifest','conventional_component_container'} for e in evidence)]
            owner=max(enclosing,key=len) if enclosing else None
            entry_root=owner if owner and parent(path) in {owner,owner+'/src'} else parent(path)
            if has_program_entry(text,by_path[path]['language']):
                anchor(entry_root,'declared_program_entry',path)
            if item.name=='__init__.py':anchor(parent(path),'python_package',path)
            if item.stem=='index' and item.suffix in {'.ts','.tsx','.js','.jsx','.mjs','.cjs'} and re.search(r'(?m)^\s*export\b|module\.exports\s*=',text):
                anchor(entry_root,'public_module_barrel',path)
        if PurePosixPath(path).name=='CMakeLists.txt':
            root=parent(path)
            if PurePosixPath(root).name=='src':
                for line,body in enumerate(text.splitlines(),1):
                    if body.lstrip().startswith('#'):continue
                    for match in re.finditer(r'\$\{\w+\}/([\w-]+)',body):
                        child=root+'/'+match[1]
                        if any(p.startswith(child+'/') and by_path[p]['language']=='cpp' for p in paths):
                            anchor(child,'cmake_source_component',path,line)
        if re.search(r'\bself\.onmessage\b|DedicatedWorkerGlobalScope|\bself\.addEventListener\s*\(\s*[\'"]message',text):
            if by_path[path]['language'] in {'typescript','tsx','javascript'}:
                anchor(parent(path),'worker_entry_scope',path)
    roots=sorted(anchors,key=lambda p:(len(PurePosixPath(p).parts),p),reverse=True)
    owned=defaultdict(list)
    for row in files:
        root=next(root for root in roots if underneath(row['path'],root));row['module']=root
        row['scope_scan']=states[row['path']];owned[root].append(row)
    modules=[];boundaries=[];conditions=[];matrix=[];entry_records=[]
    for root in sorted(anchors):
        own=owned[root];all_children=[r for r in files if underneath(r['path'],root)]
        counts=Counter(r['language'] for r in own if r['language']);roles=Counter(r['scope_role'] for r in own)
        required=any(r['scope_role']=='first_party' and r['language'] in CODE.values() for r in own)
        support_required=any(r['scope_role'] in {'build_support','deployment_support'} and r['language'] in CODE.values() for r in own)
        kind='runtime_or_library_component' if required else 'support_or_resource'
        if all(r['scope_role'] in {'test','third_party','generated'} for r in own) and own:kind='test_or_external'
        if required and any(e['kind']=='worker_entry_scope' for e in anchors[root]):kind='background_worker'
        entries=[];programs=[];options=[];mechanisms={key:[] for key in MECHANISMS};module_boundaries=[]
        for row in own:
            path=row['path'];text=texts.get(path)
            if text is None or row['language'] not in CODE.values() and PurePosixPath(path).suffix.lower() not in {'.sql','.css','.scss','.html','.cmake','.json','.toml'} and PurePosixPath(path).name not in MANIFESTS:continue
            found,hits,points,selectors=signals(text,path)
            declared,cli,issues=source_scope(text,path,row['language'])
            programs.extend(declared);options.extend(cli);diagnostics.extend(issues)
            for key,locations in found.items():mechanisms[key].extend(locations)
            for hit in hits:hit.update(module=root,scope_role=row['scope_role']);module_boundaries.append(hit['id'])
            boundaries.extend(hits);entries.extend(points)
            conditions.extend(dict(e,module=root) for e in selectors)
        entry_records.extend(dict(e,module=root) for e in entries)
        support={lang:('preexisting_partial_not_accepted_for_module' if lang in {'typescript','tsx','javascript','cpp'} else 'not_implemented')
            for lang in counts if lang in CODE.values()}
        parent_roots=[p for p in anchors if p!=root and underneath(root,p)]
        parent_root=max(parent_roots,key=len) if parent_roots else None
        for key,evidence in mechanisms.items():
            matrix.append({'module':root,'mechanism':key,'applicability':'source_candidate_present' if evidence else 'unknown_no_signal',
                'signal_count':len(evidence),'evidence':evidence,'status':'not_accepted','required_review':required or support_required,
                'no_signal_meaning':'unknown_not_absent','required_gate':'G05'})
        modules.append({'id':root,'parent':parent_root,'kind':kind,'required_runtime_review':required,
            'required_support_review':support_required,
            'contains_first_party_code':any(r['scope_role']=='first_party' and r['language'] in CODE.values() for r in all_children),
            'file_count':len(own),'subtree_files':len(all_children),'language_counts':dict(sorted(counts.items())),
            'role_counts':dict(sorted(roles.items())),'discovery_evidence':anchors[root],
            'responsibility':{'origin':'source_metadata_and_anchor_evidence','declared_metadata':metadata[root],
                'semantic_summary':'not_inferred'},'entry_candidates':entries,'boundary_candidates':module_boundaries,
            'declared_program_entries':programs,'configuration_declarations':options,
            'resource_scope':{'origin':'tracked_ownership_and_source_signals','semantic_ownership':'pending_W3',
                'tracked_non_code_files':[r['path'] for r in own if r['language'] not in CODE.values()],
                'declaration_sources':{key:mechanisms[key] for key in ('database_sql','cache_shared_state','files_external_process','frontend_state','configuration_build')}},
            'semantic_support':support,'upstream_downstream_status':'pending_semantic_boundary_analysis',
            'resource_ownership_status':'pending_W3','mode_applicability':'pending_mode_review',
            'gate_status':{f'G{i:02}':'not_executed' for i in range(2,9)}})
    base={'schema':SCHEMA,'source_commit':revision,'rules_version':rules_version,'working_tree_included':False,
        'evidence_kind':'committed_source_scope_inventory','semantic_graph_produced':False}
    manifests=[{'module':m['id'],**item} for m in modules for item in m['responsibility']['declared_metadata']]
    mode_families=[]
    for m in modules:
        if m['entry_candidates'] or m['declared_program_entries'] or m['responsibility']['declared_metadata']:
            mode_families.append({'module':m['id'],'entry_candidates':m['entry_candidates'],
                'declared_program_entries':m['declared_program_entries'],'configuration_declarations':m['configuration_declarations'],
                'manifest_declarations':[x for x in manifests if x['module']==m['id']],
                'conditions':[x for x in conditions if x['module']==m['id']],
                'status':'requires_independent_source_review','runtime_executed':False})
    scope={'tracked_files':len(files),'logical_components':len(modules),'required_runtime_components':sum(m['required_runtime_review'] for m in modules),
        'required_support_components':sum(m['required_support_review'] for m in modules),
        'language_counts':dict(sorted(Counter(r['language'] or 'other' for r in files).items())),
        'scan_statuses':dict(sorted(Counter(states.values()).items())),'boundary_candidates':len(boundaries),
        'mechanism_families':len(MECHANISMS),'unclassified_files':0}
    return {'module-inventory':{**base,'summary':scope,'modules':modules,'files':files,'diagnostics':diagnostics},
        'boundary-inventory':{**base,'finding_kind':'source_signal_candidates_not_edges','boundaries':sorted(boundaries,key=lambda b:b['id']),
            'limits':['signals_can_match_strings_or_inactive_code','not_a_complete_semantic_boundary_denominator','counterparts_not_resolved_in_W0']},
        'mechanism-matrix':{**base,'mechanisms':list(MECHANISMS),'items':matrix},
        'runtime-modes':{**base,'families':mode_families,'required_modes':[],
            'freeze_status':'pending_independent_review','limits':['declarations_are_not_proof_of_supported_combinations']},
        'coverage-baseline':{**base,'summary':scope,'G01':'not_executed','overall_technical_acceptance':'not_passed',
            'whole_project_languages_missing':sorted({lang for m in modules if m['required_runtime_review'] or m['required_support_review'] for lang,state in m['semantic_support'].items() if state=='not_implemented'}),
            'independent_reference_used_for_generation':False,'historical_assets_enabled':False,
            'file_hash_reverification':'not_run_per_user_preference'}}


def write_inventory(result,output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new inventory output directory')
    output.mkdir(parents=True)
    for name,value in result.items():atomic_json(output/(name+'.json'),value)
    return result['coverage-baseline']
