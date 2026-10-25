"""Package compact evidence from external results; preserve failed attempts."""
import argparse
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def tap(path):
    text=path.read_text(encoding='utf-8')
    return {k:int(re.search(r'^# '+k+r' (\d+)',text,re.M)[1]) for k in ['tests','pass','fail']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=a.results.resolve();out=a.output;out.mkdir(parents=True,exist_ok=False)
    checks=r/'static-async-checks-02';dev=r/'static-async-01'
    build=load(r/'static-async-full-02/result.json');measured=load(checks/'result.json');chains=load(checks/'chains.json')
    replay=load(checks/'a4-replay/development-replay/first-results.json')
    protocol_replay=load(checks/'a4-replay/result.json')
    known=load(checks/'known/queries/validation.json');navigation=load(checks/'navigation/result.json')
    repeat=load(checks/'frontend-repeat.json');updates=load(r/'static-async-updates-02/result.json')
    environment=load(r/'a5-preparation-01/result.json');browser=load(r/'a5-preparation-01/browser.json')
    fixture=load(r/'a5-preparation-01/snapshot-input.json')
    tests={'typescript':tap(dev/'all-ts-06.txt'),'python':{'passed':True,'tests':345,'log':'external static-async-01/python-04.txt'}}
    python_text=(dev/'python-04.txt').read_text(encoding='utf-8')
    assert re.search(r'Ran 345 tests in [\d.]+s\s+OK\s*$',python_text),python_text[-1000:]
    failed_tap=(dev/'first-tests.txt').read_text(encoding='utf-8')
    initial={'counts':tap(dev/'first-tests.txt'),'failed_names':re.findall(r'^not ok \d+ - (.+)$',failed_tap,re.M)}
    final_names=set(re.findall(r'^ok \d+ - (.+)$',(dev/'all-ts-06.txt').read_text(encoding='utf-8'),re.M))
    initial['original_failures_pass_after_repair']=all(name in final_names for name in initial['failed_names'])
    first=load(r/'static-async-checks-01/chains.json')
    failures={'initial_authored_checks':initial,
        'initial_product_debounce_probe':[{'name':c['name'],'boundary_projection':c['hasBoundaryProjection']} for c in load(r/'static-async-source-01/result.json')],
        'first_full_build':load(r/'static-async-full-01/result.json'),
        'first_full_query_rule':first['query_version'],'first_full_facts_rule':first['facts_version'],
        'first_five_connections':[{'id':c['id'],'connected':c['connected']} for c in first['cases']],
        'first_known_checks':load(r/'static-async-checks-01/known/queries/validation.json')['checks'],
        'first_a4_scoring_budget_stop':load(r/'static-async-checks-01/result.json')['a4-replay'],
        'mechanism':'branch-copied callback alternatives were not dispatched by invokeLookup; fixed in b8eac24',
        'scope':'development history retained; first failures are not replaced by final results'}
    request=load(r/'static-async-full-02/build/request.json')
    compact_chains={**chains,'snapshot':request['snapshot'],'snapshot_identity_source':'complete_builder_request',
        'cases':[{**{k:v for k,v in c.items() if k!='consumers'},
        'consumer_count':len(c['consumers']),'consumer_samples':c['consumers'][:2]} for c in chains['cases']]}
    replay_compact={k:replay[k] for k in ['source_commit','snapshot','build_version','counts','protocol_outcomes','elapsed_seconds']}
    replay_compact.update(evidence_kind='executed_existing_A4_development_regression',independent_holdout=False,
        cases=[{k:c.get(k) for k in ['id','protocol_outcome','producer_forward','producer_reverse','serialized_field_present','expected_state_connected','query_truncated']} for c in replay['cases']])
    known_compact={k:known[k] for k in ['source_commit','snapshot','build_version','counts','checks','passed']}
    gates={
        'complete_build_passed':build['status']=='passed',
        'five_conditional_connection_targets_found':chains['all_five_connections'] and not chains['unpublished_callback_component_substitution'],
        'six_existing_protocols':replay['counts']['correct_protocol_pairs']==6 and replay['counts']['wrong_protocol_pairs']==0,
        'six_existing_producer_paths':replay['counts']['producer_forward_paths']==6 and replay['counts']['producer_reverse_paths']==6,
        'five_existing_protocol_references':protocol_replay['new_protocol_passed'] and protocol_replay['final_protocol_passed'],
        'six_existing_fields':replay['counts']['serialized_field_relations']==6,
        'two_existing_state_targets':replay['counts']['return_state_relations']==2,
        'nineteen_known_checks':known['passed'] and len(known['checks'])==19,
        'navigation_fidelity':navigation['passed'] and len(navigation['checks'])==26,
        'thirteen_refresh_checks':updates['passed'] and len(updates['checks'])==13,
        'frontend_repeat_equal':repeat['equal'],
        'python_tests':tests['python']['passed'],
        'typescript_tests':tests['typescript']['pass']==110 and tests['typescript']['fail']==0,
        'initial_mechanism_failures_repaired':initial['original_failures_pass_after_repair'],
    }
    preparation={'module_builds':all(environment['builds'][m]['status']=='passed' for m in ['cluster','leaks']),
        'headless_browser_started':bool(browser['browser_version']),
        'public_snapshot_inspected':fixture['block_records']==717 and fixture['pickle_class_loading']=='disabled',
        'isolated_checkout_clean':environment['push_disabled'] and not environment['source_dirty_after']}
    evaluation={'source_commit':chains['source_commit'],'facts_version':chains['facts_version'],'query_version':chains['query_version'],
        'static_connection_gates':gates,'static_connection_acceptance_passed':all(gates.values()),
        'runtime_preparation_gates':preparation,'a5_preparation_completed':all(preparation.values()),
        'new_product_runtime_scenarios':0,'historical_validation_records_used_for_tuning':False,
        'loop_iteration_budget':3,'scope':'five named conditional source connections; loop budget and other extraction gaps remain visible; not whole-project path completeness'}
    for name,value in [('build.json',build),('measurements.json',measured),('chains.json',compact_chains),
        ('a4-regression.json',replay_compact),('known-regression.json',known_compact),('navigation.json',navigation),
        ('protocol-regression.json',{'new_protocol_passed':protocol_replay['new_protocol_passed'],'final_protocol_passed':protocol_replay['final_protocol_passed'],
            'independent_holdout':False,'cases':[{k:c[k] for k in ['id','api','outcome']} for c in protocol_replay['new_protocol_cases']+protocol_replay['final_protocol_cases']]}),
        ('updates.json',{k:updates[k] for k in ['evidence_kind','fixture_origin','build_version','checks','passed']}),
        ('frontend-repeat.json',repeat),('tests.json',tests),('development-failures.json',failures),
        ('runtime-preparation.json',{'environment':environment,'browser':browser,'snapshot_input':fixture}),('evaluation.json',evaluation)]:
        save(out/name,value)
    status='五项指定静态连接验收通过；A5 环境准备完成' if evaluation['static_connection_acceptance_passed'] and evaluation['a5_preparation_completed'] else '复验尚有未通过项'
    rows='\n'.join('| '+c['api']+' | `'+'.'.join(c['field'])+'` | `'+c['consumer']+'` | '+('已连接' if c['connected'] else '未连接')+' |' for c in chains['cases'])
    report=f'''# 异步返回、分页连接与 A5 准备

日期：2026-10-25。**{status}。** [验收门槛](evidence/evaluation.json)和[逐项连接](evidence/chains.json)保留条件、诊断与截断状态。

| 请求 | 返回字段 | 指定前端目标 | 结果 |
|---|---|---|---|
{rows}

`getBlocksGraphData` 对应 memscope 的单次请求；`getSnapshotBlocks` 对应 snapshot 的分页请求。两个分支在 `getBarNewData` 汇合，转交 `workerSetMemoryBlockData`。Worker 入口按参数转交登记，内部数据使用和实际绘制另行验证。

## 实现

复用现有 TypeScript 编译器解释器和 Tree-sitter 类型候选，补齐本轮已确认的机制：

- 标准 Promise 的 resolve/reject、保存的回调、剩余/展开参数、局部 Map、定时任务与队列；保留首次结算、取消和调度条件。
- 有界循环、break/continue、数组累积与排序；传播字段来源，区分被覆盖的 spread 字段，保留嵌套异常守卫后的成功路径。
- 调用别名按函数身份连接；已知函数的参数转交与 helper 返回分别登记。
- 前端接口分析纳入已发现的发送方，保留未匹配接口的消费者；C++ 类型候选沿可见的多层 namespace 导入查找，并保留歧义。规则依据 [C++ using directive 条款](https://eel.is/c++draft/namespace.udir#5)，源码候选继续保留编译上下文限制。
- 组合查询同时返回前端和返回值分析的预算诊断。

## 验证

345 项 Python、110 项 TypeScript 测试通过；既有六条请求、六个响应字段和两个状态目标回归通过。13 项刷新、26 项导航、19 项 P7 检查及前端组件重复提取一致性结果分别见 [更新](evidence/updates.json)、[导航](evidence/navigation.json)、[既有链](evidence/known-regression.json)、[组件比较](evidence/frontend-repeat.json)及[测试](evidence/tests.json)。修复回调后完成完整重建并通过复验；组件比较覆盖前端阶段的全部 JSON 内容。

首次八项机制检查为 3 项通过、5 项失败。第一次完整构建完成后，五个组合查询均未连接，既有返回链也失败：分支复制产生的回调候选未被回调表读取展开。修复后重新完整构建及评分。[失败记录](evidence/development-failures.json)保留这些结果，以及 A4 评分在 6 GiB 分析预算下停止的记录；最终该评分采用明确的 8 GiB 分析预算。

完整构建用时 {build['elapsed_seconds']:.1f} 秒，峰值进程树工作集 {build['peak_tree_working_set_bytes_observed']/1024**3:.2f} GiB，构建预算 1,800 秒 / 6 GiB。最终图包含 {chains['graph_counts']['nodes']:,} 个节点、{chains['graph_counts']['edges']:,} 条关系、2,315 个输入。完整成本见 [构建](evidence/build.json)和[查询测量](evidence/measurements.json)。

源码为独立实验副本 `{chains['source_commit']}`，事实提取版本为 `{chains['facts_version']['rules_commit']}`。六条既有材料和本轮五项连接属于开发回归；历史验证候选未用于调规则。

## 覆盖与下一步

循环按 3 轮预算展开，定时回调采用显式的候选调度顺序。查询中仍有预算截断、外部调用和其他未展开路径；五项成绩表示指定连接已找到。真实分页次数、缓存命中/失效、并发处置、Worker 采用与资源指标进入 A5 场景验证。

A5 已构建 Cluster、Leaks 页面，启动 Chromium 143，并检查公开 snapshot 输入：2 个 segment、717 条原始 block、8,092 条 trace event。构建后独立副本保持干净且禁用推送。[准备证据](evidence/runtime-preparation.json)中的真实产品场景数为 0；浏览器探针运行于 about:blank，产品页面的隔离头、OPFS 与实际渲染由场景执行验证。[A5 计划](../../plans/a5-runtime-validation.md)已写明正常、异常、切换、并发、缓存与故障对照。

原 GitCode 仓库和原下载副本保持不变。历史问题契约库的真实接入继续由 P6 跟进。
'''
    (out.parent/'completion.md').write_text(report,encoding='utf-8')
    print(json.dumps(evaluation))
