"""Inventory a complete committed tree and surface mechanism candidates.

Lexical signals guide adapter coverage review; they are never call/dataflow edges.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
import subprocess
import tarfile

LANGUAGES={'.ts':'TypeScript','.tsx':'TypeScript/React','.js':'JavaScript','.jsx':'JavaScript/React',
    '.cjs':'JavaScript','.mjs':'JavaScript','.cpp':'C++','.cc':'C++','.cxx':'C++','.h':'C/C++ header',
    '.hpp':'C++ header','.c':'C','.py':'Python','.rs':'Rust','.sh':'Shell','.ps1':'PowerShell',
    '.bat':'Batch','.cmake':'CMake','.proto':'Protobuf','.sql':'SQL'}
SIGNALS={
 'protocol_transport':r'WebSocket|postMessage\s*\(|fetch\s*\(|XMLHttpRequest|\b(?:send|recv|accept)\s*\(',
 'registration_dispatch':r'(?:[Rr]egister|[Rr]outer|[Hh]andlerMap|[Pp]rotocol|[Cc]allback)',
 'frontend_state':r'\b(?:useState|useReducer|useEffect|useRef|makeAutoObservable|runInAction)\b',
 'promise_callback':r'\bPromise\b|\.then\s*\(|\.catch\s*\(|std::function|\bcallback\b',
 'event_subscription':r'addEventListener|removeEventListener|\b(?:subscribe|unsubscribe|emit|publish)\s*\(',
 'database_sql':r'\b(?:SELECT\s|INSERT\s|UPDATE\s|DELETE\s|sqlite3_|ExecuteQuery|ExecuteSql|CREATE TABLE)',
 'cache_shared_state':r'\b(?:cache|Cache|singleton|Instance)\b|std::(?:unordered_)?map\s*<',
 'field_transform_serialization':r'JSON\.(?:parse|stringify)|AddMember\s*\(|rapidjson|serialize|deserialize',
 'threads_tasks':r'std::thread|ThreadPool|threadPool|\bSubmit\s*\(|std::async|QThread|Worker\s*\(',
 'locks_concurrency':r'std::(?:mutex|shared_mutex|unique_lock|lock_guard|atomic)|condition_variable',
 'lifetime_cleanup':r'\b(?:delete|free)\b|\.reset\s*\(|\b(?:Close|Shutdown|Dispose|Release|Clear)\s*\(',
 'cancellation_timeout':r'AbortController|AbortSignal|\b(?:cancel|Cancel|timeout|Timeout)\b|setTimeout|clearTimeout',
 'errors_retries':r'\b(?:throw|catch|retry|Retry)\b|Promise\.reject|set_exception',
 'files_external_process':r'\b(?:fopen|ifstream|ofstream|popen|fork|exec|spawn|subprocess|Command::new)\b',
 'configuration_build':r'process\.env|\bgetenv\b|#if|CMAKE_|\boption\s*\(|cfg\s*!?\(',
 'ffi_native_plugin':r'extern\s+"C"|ctypes|cffi|pybind|napi_|FFI|dlopen|LoadLibrary|\btauri\b',
 'background_entry':r'\bmain\s*\(|__main__|\b(?:schedule|setInterval|cron)\b|jupyter_server_extension',
 'tests_assertions':r'\b(?:assert|ASSERT_[A-Z_]+|EXPECT_[A-Z_]+|describe|test|it|expect)\s*\('
}
SUPPORT={
 'protocol_transport':('partial','P2/P3 custom WS and iframe mechanism; other protocols unvalidated'),
 'registration_dispatch':('partial','Source maps/factories and handler candidates; dynamic plugin registration unknown'),
 'frontend_state':('partial','Selected await/Promise.then and named React.useState; other hooks and functional updaters incomplete'),
 'promise_callback':('partial','Selected Promise delivery, C++ callbacks and captures; arbitrary callback effects incomplete'),
 'event_subscription':('partial','Selected WS/window listeners; general event buses unexpanded'),
 'database_sql':('partial','DB/Text implementation candidates and selected output fields; general SQL lineage/transactions unexpanded'),
 'cache_shared_state':('partial','Member reads/writes, selected source instances and literal-key isolation; complete alias/key/lifetime proof absent'),
 'field_transform_serialization':('partial','Selected JSON and response fields; arbitrary conversion/value equivalence unproved'),
 'threads_tasks':('partial','Selected response queue lineage and P5 request IDs; general scheduler/interleavings unexpanded'),
 'locks_concurrency':('inventory_only','Lock source locations; no happens-before or deadlock proof'),
 'lifetime_cleanup':('partial','Selected cleanup calls and member effects; ownership, capacity and RSS unmeasured'),
 'cancellation_timeout':('inventory_only','Source candidates; end-to-end cancellation/timeouts not accepted'),
 'errors_retries':('partial','Selected error/early-return and late-response guards; general retry/idempotency unvalidated'),
 'files_external_process':('inventory_only','Source candidates; file/process boundaries unconnected'),
 'configuration_build':('partial','Manifest inventory and graph deployment binding; complete variant/build graph unexpanded'),
 'ffi_native_plugin':('inventory_only','Source candidates; Rust/Python/native/plugin edges unconnected'),
 'background_entry':('inventory_only','Entry candidates; background workflows not traced'),
 'tests_assertions':('partial','P5 real unit/flows scenarios; general requirement-to-test coverage not established')
}


def scan(source,graph):
    commit=graph['source_commit'];selected=set(graph['input_paths']);stats=Counter();langs=Counter();selected_langs=Counter()
    groups=defaultdict(lambda:{'tracked_files':0,'selected_files':0,'languages':Counter()})
    signals=defaultdict(list);manifests=[];unread=[]
    compiled={k:re.compile(v) for k,v in SIGNALS.items()}
    proc=subprocess.Popen(['git','-C',str(source),'archive',commit],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
        for member in archive:
            if not member.isfile():continue
            path=member.name;stats['tracked_files']+=1;top=path.split('/')[0] if '/' in path else '<root>'
            group=groups[top];group['tracked_files']+=1;group['selected_files']+=path in selected
            suffix=Path(path).suffix.lower();language=LANGUAGES.get(suffix)
            if Path(path).name=='CMakeLists.txt':language='CMake'
            if language:
                langs[language]+=1;group['languages'][language]+=1;selected_langs[language]+=path in selected
            manifest=Path(path).name in {'package.json','Cargo.toml','pyproject.toml','requirements.txt','CMakeLists.txt'}
            if not language and not manifest:stats['not_source_or_manifest']+=1;continue
            if member.size>2*1024*1024:unread.append({'path':path,'reason':'size_limit'});continue
            raw=archive.extractfile(member).read()
            try:body=raw.decode('utf-8')
            except UnicodeDecodeError:unread.append({'path':path,'reason':'non_utf8'});continue
            if '\0' in body:unread.append({'path':path,'reason':'binary'});continue
            stats['text_scanned']+=1
            if manifest:manifests.append({'path':path,'line':1,'kind':Path(path).name,'selected':path in selected})
            for number,line in enumerate(body.splitlines(),1):
                for category,regex in compiled.items():
                    if regex.search(line):signals[category].append({'path':path,'line':number,'excerpt':line.strip()[:250],'graph_input':path in selected})
    if proc.wait():raise RuntimeError('git archive failed')
    categories=[]
    for category in SIGNALS:
        rows=signals[category];files={r['path'] for r in rows}
        categories.append({'id':category,'support':SUPPORT[category][0],'boundary':SUPPORT[category][1],
            'signal_count':len(rows),'candidate_files':len(files),'selected_candidate_files':len(files&selected),
            'evidence':rows,'signal_rule':SIGNALS[category],
            'finding_kind':'lexical_candidate_not_semantic_relation','no_signal_meaning':'unknown_not_absent'})
    return {'schema_version':'coverage-catalog/1','source_commit':commit,'snapshot':graph['snapshot'],
        'origin':'full_git_tree_inventory_and_lexical_preflight','scan':dict(stats),'unread':unread,
        'languages':[{'name':k,'tracked_files':v,'graph_input_files':selected_langs[k]} for k,v in sorted(langs.items())],
        'top_level_groups':[{'path':k,**v,'languages':dict(v['languages'])} for k,v in sorted(groups.items())],
        'manifests':manifests,'capabilities':categories,
        'limits':['lexical_signals_can_match_comments_strings_and_tests','signals_are_not_extracted_connections',
                  'no_automatic_completeness_proof_for_language_or_framework_mechanisms',
                  'runtime_coverage_only_for_recorded_P5_unit_flows_scenarios','P6_assets_not_connected']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--graph',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh output')
    result=scan(a.source,json.loads(a.graph.read_text(encoding='utf-8')))
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'scan':result['scan'],'languages':result['languages'],'capabilities':len(result['capabilities']),'unread':len(result['unread'])}))
