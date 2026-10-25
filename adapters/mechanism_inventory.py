"""Source signals for scope review, never semantic graph edges."""
import re

MECHANISMS={
 'protocol_transport':r'WebSocket|postMessage\s*\(|fetch\s*\(|XMLHttpRequest|\b(?:send|recv|accept|serve|listen)\s*\(',
 'registration_dispatch':r'[Rr]egister|[Rr]outer|[Hh]andlerMap|[Pp]rotocol|[Cc]allback|autoStart\s*:',
 'frontend_state':r'\b(?:useState|useReducer|useEffect|useRef|makeAutoObservable|runInAction)\b|className\s*=|\.css[\'"]',
 'promise_callback':r'\bPromise\b|\.then\s*\(|\.catch\s*\(|std::function|\bcallback\b|\basync\s+def\b|\basync\s+fn\b',
 'event_subscription':r'addEventListener|removeEventListener|\b(?:subscribe|unsubscribe|emit|publish)\s*\(',
 'database_sql':r'\b(?:SELECT\s|INSERT\s|UPDATE\s|DELETE\s|sqlite3_|ExecuteQuery|ExecuteSql|CREATE TABLE)',
 'cache_shared_state':r'\b(?:cache|Cache|singleton|Instance)\b|std::(?:unordered_)?map\s*<|\blru_cache\b',
 'field_transform_serialization':r'JSON\.(?:parse|stringify)|AddMember\s*\(|rapidjson|serializ|deserializ|json\.(?:loads|dumps)',
 'threads_tasks':r'std::thread|ThreadPool|threadPool|\bSubmit\s*\(|std::async|QThread|\bWorker\s*\(|create_task\s*\(|thread::spawn|asyncio\.',
 'locks_concurrency':r'std::(?:mutex|shared_mutex|unique_lock|lock_guard|atomic)|condition_variable|\b(?:Mutex|RwLock|Semaphore|Lock)\b',
 'lifetime_cleanup':r'\b(?:delete|free)\b|\.reset\s*\(|\b(?:Close|Shutdown|Dispose|Release|Clear)\s*\(|\.terminate\s*\(|\.kill\s*\(|\bimpl\s+Drop',
 'cancellation_timeout':r'AbortController|AbortSignal|\b(?:cancel|Cancel|timeout|Timeout)\b|setTimeout|clearTimeout|CancelledError',
 'errors_retries':r'\b(?:throw|catch|retry|Retry|except|raise)\b|Promise\.reject|set_exception|\bResult\s*<',
 'files_external_process':r'\b(?:fopen|ifstream|ofstream|popen|fork|exec|spawn|subprocess)\b|Command::new|\.read_text\s*\(|\.write_text\s*\(',
 'configuration_build':r'process\.env|\bgetenv\b|#if|CMAKE_|\boption\s*\(|cfg\s*!?\(|os\.environ|add_argument\s*\(',
 'ffi_native_plugin':r'extern\s+"C"|ctypes|cffi|pybind|napi_|FFI|dlopen|LoadLibrary|\b(?:tauri|JupyterFrontEndPlugin)\b|_jupyter_.*extension',
 'background_entry':r'\bmain\s*\(|__main__|\b(?:schedule|setInterval|cron)\b|jupyter_server_extension|createRoot\s*\(',
 'tests_assertions':r'\b(?:assert|ASSERT_[A-Z_]+|EXPECT_[A-Z_]+|describe|test|it|expect)\s*\('
}

BOUNDARIES={
 'process_start':('consumer',r'Command::new\s*\(|subprocess\.(?:Popen|run|call|check_output|check_call)\s*\(|\b(?:spawn|execFile|fork|popen)\s*\('),
 'process_stop':('consumer',r'\.(?:kill|terminate|wait|join)\s*\(|\bkill\s*\('),
 'network_client':('consumer',r'\b(?:WebSocket|ClientSession|XMLHttpRequest)\s*\(|websockets\.connect\s*\(|\bfetch\s*\(|\.(?:connect|ws_connect)\s*\('),
 'network_server':('provider',r'\.(?:listen|bind|route|any|ws|add_route|add_handlers)\s*\(|(?:websockets\.)?serve\s*\(|TcpListener::bind|(?:HTTPServer|TCPSite|WebSocketResponse)\s*\('),
 'network_send':('consumer',r'(?:\.|->)(?:send|send_text|send_str|send_bytes|send_json|sendall)\s*\('),
 'network_receive':('provider',r'\bonmessage\b|\.(?:recv|receive|receive_text)\s*\(|\b(?:OnMessage|OnRequest)\b|\basync\s+for\b'),
 'window_message':('unknown',r'\bpostMessage\s*\(|addEventListener\s*\(\s*[\'"]message[\'"]'),
 'worker_start':('consumer',r'\bnew\s+(?:Shared)?Worker\s*\('),
 'worker_entry':('provider',r'\bself\.onmessage\b|DedicatedWorkerGlobalScope|\bself\.addEventListener\s*\(\s*[\'"]message[\'"]'),
 'webview_load':('consumer',r'WebViewBuilder|with_url\s*\(|with_html\s*\(|loadURL\s*\(|loadFile\s*\('),
 'registration':('provider_candidate',r'\b(?:Register|register|RegisterProtocol|registerPlugin|RegisterHandler)\w*\s*\(|\bautoStart\s*:|_jupyter_.*extension|\.(?:emplace|add_route|add_handlers)\s*\('),
 'event_subscription':('provider_candidate',r'addEventListener\s*\(|\.(?:subscribe|on)\s*\('),
 'file_access':('unknown',r'\b(?:fopen|ifstream|ofstream|open)\s*\(|\.(?:readFile|writeFile|read_text|write_text|read_bytes|write_bytes)\s*\('),
 'database_operation':('unknown',MECHANISMS['database_sql']),
 'native_plugin':('unknown',MECHANISMS['ffi_native_plugin'])
}


def signals(text,path):
    mechanism={key:[] for key in MECHANISMS};boundaries=[];entries=[];conditions=[]
    regex={key:re.compile(pattern) for key,pattern in MECHANISMS.items()}
    boundary_regex={key:re.compile(spec[1]) for key,spec in BOUNDARIES.items()}
    entry=re.compile(r'\b(?:int|void|fn)\s+main\s*\(|__name__\s*==\s*[\'"]__main__[\'"]|createRoot\s*\(|ReactDOM\.render\s*\(|\bautoStart\s*:\s*true|_jupyter_.*extension')
    selector=re.compile(r'#\[cfg|#if|target_os|debug_assertions|process\.platform|sys\.platform|platform\.system|add_argument\s*\(|os\.environ|process\.env')
    for line,body in enumerate(text.splitlines(),1):
        stripped=body.strip()
        if stripped.startswith(('//','/*','* ','<!--')) or re.match(r'^#\s',stripped):continue
        evidence={'path':path,'line':line,'expression':stripped[:500]}
        for key,pattern in regex.items():
            if pattern.search(body):mechanism[key].append(evidence)
        for key,pattern in boundary_regex.items():
            if pattern.search(body):boundaries.append({'id':f'{path}:{line}:{key}','family':key,'direction':BOUNDARIES[key][0],
                'evidence':evidence,'finding_kind':'source_signal_candidate','resolution':'not_semantically_extracted',
                'counterpart':None,'service_scope':None,'conditions_status':'pending_context_analysis',
                'review_status':'pending','required_gate':'G03'})
        if entry.search(body):entries.append({**evidence,'finding_kind':'entry_source_candidate'})
        if selector.search(body):conditions.append({**evidence,'finding_kind':'configuration_source_candidate'})
    return mechanism,boundaries,entries,conditions
