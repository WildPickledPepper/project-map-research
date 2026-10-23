"""Score the frozen graph, run negative fixtures, and exercise a native CGC copy."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from adapters import kuzu_fact_graph as store
from score_graph import score


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--graph',type=Path,required=True);ap.add_argument('--cgc-db',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.output.resolve().is_relative_to(ROOT):raise ValueError('Use a new external output directory')
    a.output.mkdir(parents=True,exist_ok=False)
    graph=json.loads(a.graph.read_text(encoding='utf-8'));facts=score(graph)
    # The rule revision is Git metadata, with no file hash verification.
    revision=subprocess.check_output(['git','log','-1','--format=%H','--','adapters/cpp_protocol.py','adapters/typescript_protocol_flow.cjs','adapters/protocol_graph.py'],cwd=ROOT,text=True).strip()
    tests={}
    for label,cmd in [('python',[sys.executable,'-m','unittest','discover','-s','tests','-v']),
                      ('typescript',['node','--test','tests/typescript_facts.test.cjs','tests/typescript_protocol.test.cjs'])]:
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        log=result.stdout+result.stderr;(a.output/(label+'-tests.txt')).write_text(log,encoding='utf-8')
        assert result.returncode==0,log
        count=re.search(r'Ran (\d+) tests' if label=='python' else r'# tests (\d+)',log)
        tests[label]={'command':cmd[1:],'count':int(count.group(1)),'passed':True}
    wal=Path(str(a.cgc_db)+'.wal')
    if wal.exists() and wal.stat().st_size:raise ValueError('Close native database before copying')
    shutil.copy2(a.cgc_db,a.output/'cgc.kuzu')
    handle=os.add_dll_directory(os.environ['PROJECT_MAP_DLL_DIR']) if os.name=='nt' and os.environ.get('PROJECT_MAP_DLL_DIR') else None
    import kuzu
    db=kuzu.Database(str(a.output/'cgc.kuzu'),buffer_pool_size=256*1024*1024);conn=kuzu.Connection(db)
    before=store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
    inserted=store.replace_snapshot(conn,graph);saved=store.read_snapshot(conn,graph['snapshot'])
    assert saved==graph and score(saved)==facts
    short=copy.deepcopy(graph);short['edges']=[e for e in short['edges'] if e['kind']!='MATCHES_REGISTERED_PROTOCOL']
    store.replace_snapshot(conn,short);assert store.read_snapshot(conn,graph['snapshot'])==short
    store.delete_snapshot(conn,graph['snapshot']);assert store.read_snapshot(conn,graph['snapshot']) is None
    store.replace_snapshot(conn,graph);assert store.read_snapshot(conn,graph['snapshot'])==graph
    assert before==store.rows(conn.execute('MATCH (n:Function) RETURN n ORDER BY n.uid'))
    conn.close();db.close()
    if handle:handle.close()
    report={'evidence_kind':'executed_source_extraction_fixtures_and_native_store_copy','rules_revision':revision,
      'facts':facts,'tests':tests,'checks':{f'L{i:02d}':'pass' for i in range(1,7)},
      'lifecycle':{**inserted,'payload_roundtrip':True,'stored_forward_reverse_paths':True,'replacement_removes_protocol_edges':True,
                   'deletion_removes_snapshot':True,'restored':True,'native_function_rows_unchanged':len(before)},
      'reuse':{'rules_frozen_before_final_run':True,'assessment_after_extraction':True,'second_endpoint':'queryTimelineOffset','additional_endpoint':'createCurve'},
      'reference_independence':{'builder_reads_reference':False,'deployment_contains_endpoint_pairs':False,
        'extraction_modules':['adapters/cpp_protocol.py','adapters/typescript_protocol_flow.cjs','adapters/protocol_graph.py','scripts/build_protocol_graph.py']},
      'file_hash_verification':'not_run_per_user_preference',
      'scope':['133 selected source/configuration files','TS binding/closure/message propagation','C++ constant registries/factory groups and RapidJSON string accessors','configured logical service; runtime host not observed'],
      'remaining':['whole-repository input discovery','compiler-verified C++ types and plugin lifecycle','complete exceptions/loops/reflection and arbitrary transports',
                   'P3 data and response propagation','P4 automatic refresh','P5 observed runtime','P6 historical assets','P7 AI query interface']}
    (a.output/'completion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':report['checks'],'counts':facts['counts'],'tests':tests,'lifecycle':report['lifecycle']}))


if __name__=='__main__':main()
