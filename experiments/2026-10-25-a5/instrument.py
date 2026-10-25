"""Add A5 observation points only to the existing push-disabled runtime checkout."""
import argparse
import json
from pathlib import Path
import subprocess

BASE = 'ccd0d88080861b0c7185bcca70a85bd61f823168'


def apply(source):
    source = Path(source).resolve()
    git = lambda *args: subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    if git('remote', 'get-url', '--push', 'origin') != 'disabled://p5-local-experiment':
        raise ValueError('Requires push-disabled experimental clone')
    if git('rev-parse', 'HEAD') != BASE or git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Requires clean pinned runtime baseline')
    changes = {}

    def replace(path, old, new):
        value = changes.get(path, (source/path).read_text(encoding='utf-8'))
        if value.count(old) != 1:
            raise ValueError(f'Expected unique anchor: {path}: {old[:90]}')
        changes[path] = value.replace(old, new)

    # This is downstream of debounce key construction: observation IDs cannot defeat coalescing.
    p = 'modules/lib/src/connection/index.ts'
    replace(p, 'params.id = this._curFetchSequenceID;', '''const probe = (globalThis as any).__a5;
            const args = (params as any).args;
            if (probe && args?.params && /^(communication\/|Memory\/(snapshot|leaks)\/)/.test(args.command)) {
                const traceId = probe.begin(args.command, args.params, this._curFetchSequenceID);
                args.params = { ...args.params, __projectMapTrace: traceId };
            }
            params.id = this._curFetchSequenceID;''')
    replace(p, 'const result = this._msgSequence.get(res.data.id);', '''(globalThis as any).__a5?.event('connector.response', { id: res.data.id, response: res.data });
        const result = this._msgSequence.get(res.data.id);''')
    p = 'modules/cluster/src/components/communication/Filter.tsx'
    replace(p, 'return { compare: compareOptions, baseline: baselineOptions, diff: [] };', '''(globalThis as any).__a5?.event('consumer.iterations', { compareOptions, baselineOptions });
    return { compare: compareOptions, baseline: baselineOptions, diff: [] };''')
    replace(p, '    return options;\n};\nconst getOperatorOptions', '''    (globalThis as any).__a5?.event('consumer.groups', { options });
    return options;
};
const getOperatorOptions''')
    for module in ('cluster', 'leaks'):
        p = f'modules/{module}/src/store/session.ts'
        replace(p, 'makeAutoObservable(this);', 'makeAutoObservable(this);\n        (globalThis as any).__a5Session = () => this._activeSession;')
    p = 'modules/leaks/src/components/dataHandler.ts'
    # Query parameter override is explicit experimental configuration, with a default-size control.
    replace(p, 'let pageSize = BLOCKS_MIN_PAGE_SIZE;', 'let pageSize = (globalThis as any).__a5PageSize ?? BLOCKS_MIN_PAGE_SIZE;')
    # Keep subsequent growth aligned with the same experimental minimum.
    replace(p, 'const BLOCKS_MIN_PAGE_SIZE = 1000;', 'const BLOCKS_MIN_PAGE_SIZE = (globalThis as any).__a5PageSize ?? 1000;')
    replace(p, 'merged.blocks = merged.blocks.concat(res.blocks);', '''(globalThis as any).__a5?.event('pagination.page', { baseParam, currentPage, pageSize, blocks: res.blocks, total: res.total });
        merged.blocks = merged.blocks.concat(res.blocks);''')
    replace(p, 'return merged as RenderData;', '''(globalThis as any).__a5?.event('pagination.merged', { baseParam, result: merged });
    return merged as RenderData;''')
    replace(p, 'barDataRequestSeqMap.set(session, requestSeq);', '''barDataRequestSeqMap.set(session, requestSeq);
    (globalThis as any).__a5?.event('load.begin', { requestSeq, deviceId: session.deviceId, sliceIndex: session.selectedSliceIndex });''')
    replace(p, "if (cacheStatus === 'unavailable') {", "(globalThis as any).__a5?.event('cache.result', { requestSeq, cacheStatus, cacheFileHash, blockContextKey });\n        if (cacheStatus === 'unavailable') {")
    replace(p, 'const blockRenderTask = workerSetMemoryBlockData({ data: blockData, fileHash: cacheFileHash });', '''if ((globalThis as any).__a5FaultDropBlock) { blockData.blocks = blockData.blocks.slice(1); }
        (globalThis as any).__a5?.event('worker.handoff', { requestSeq, blockContextKey, data: blockData });
        const blockRenderTask = workerSetMemoryBlockData({ data: blockData, fileHash: cacheFileHash });''')
    replace(p, 'session.loadedMemoryBlockContextKey = blockContextKey;\n        });\n        preloadRemainingOverviews();', '''session.loadedMemoryBlockContextKey = blockContextKey;
        });
        (globalThis as any).__a5?.event('load.adopted', { requestSeq, blockContextKey, deviceId: session.deviceId, sliceIndex: session.selectedSliceIndex });
        preloadRemainingOverviews();''')
    replace(p, 'if (error === SNAPSHOT_PAGINATION_SUPERSEDED) {', '''(globalThis as any).__a5?.event('load.error', { requestSeq, superseded: error === SNAPSHOT_PAGINATION_SUPERSEDED, message: error?.message });
        if (error === SNAPSHOT_PAGINATION_SUPERSEDED) {''')
    # Explicit driver calls supplement the UI scenario; their provenance is retained in each action.
    changes[p] += '\n(globalThis as any).__a5ReloadBlocks = getBarNewData;\n'
    p = 'modules/leaks/src/leaksWorker/blockWorker/worker.ts'
    changes[p] = (source/p).read_text(encoding='utf-8') + '\n(globalThis as any).__a5RemoveCache = WorkerBackend.removeMemoryBlockCaches;\n'
    for p in ('server/src/modules/communication/core/ClusterService.cpp',
              'server/src/modules/memsnapshot/handler/QueryMemSnapshotBlockHandler.cpp',
              'server/src/modules/memscope/handler/QueryMemScopeBlockHandler.cpp'):
        value = (source/p).read_text(encoding='utf-8')
        changes[p] = '#include "ProjectMapProbe.h"\n' + value
    p = 'server/src/modules/communication/core/ClusterService.cpp'
    replace(p, 'if (database == nullptr || !database->QueryIterations(response.body.compare)) {', '''if (database) ProjectMapProbe::Emit("database.call", ProjectMapProbe::Capture(request), typeid(*database).name());
    if (database == nullptr || !database->QueryIterations(response.body.compare)) {''')
    replace(p, '    if (!request.params.isCompare) {\n        return;\n    }\n\n    auto baselineDatabase', '''    ProjectMapProbe::Emit("database.return", ProjectMapProbe::Capture(request), database ? typeid(*database).name() : "null", static_cast<int>(response.body.compare.size()));
    if (!request.params.isCompare) {
        return;
    }

    auto baselineDatabase''')
    replace(p, 'std::vector<GroupInfoDo> compareGroupList;', '''if (database) ProjectMapProbe::Emit("database.call", ProjectMapProbe::Capture(request), typeid(*database).name());
    std::vector<GroupInfoDo> compareGroupList;''')
    replace(p, 'response.body.groupList = MergeGroupInfo(request, compareGroupList, baselineGroupList);', '''response.body.groupList = MergeGroupInfo(request, compareGroupList, baselineGroupList);
    ProjectMapProbe::Emit("database.return", ProjectMapProbe::Capture(request), database ? typeid(*database).name() : "null", static_cast<int>(response.body.groupList.size()));''')
    p = 'server/src/modules/memsnapshot/handler/QueryMemSnapshotBlockHandler.cpp'
    replace(p, '    const auto slice = resolved.slice;', '    ProjectMapProbe::Emit("database.call", ProjectMapProbe::Capture(request), typeid(*database).name());\n    const auto slice = resolved.slice;')
    replace(p, '    SendResponse(std::move(responsePtr), true);', '''    ProjectMapProbe::Emit("database.return", ProjectMapProbe::Capture(request), typeid(*database).name(), static_cast<int>(response.isTable ? response.tableBlocks.size() : response.viewBlocks.size()));
    SendResponse(std::move(responsePtr), true);''')
    p = 'server/src/modules/memscope/handler/QueryMemScopeBlockHandler.cpp'
    replace(p, '    const int64_t total = memoryDatabase->QueryMemoryBlocks(request.params, request.isTable, response.blocks);', '''    ProjectMapProbe::Emit("database.call", ProjectMapProbe::Capture(request), typeid(*memoryDatabase).name());
    const int64_t total = memoryDatabase->QueryMemoryBlocks(request.params, request.isTable, response.blocks);
    ProjectMapProbe::Emit("database.return", ProjectMapProbe::Capture(request), typeid(*memoryDatabase).name(), static_cast<int>(total));''')
    for path, value in changes.items():
        (source/path).write_text(value, encoding='utf-8', newline='\n')
    return {'base': BASE, 'files': list(changes), 'observation_ids_inserted_after_debounce_key': True,
            'fault_default': False, 'page_size_default': 1000}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--source', type=Path, required=True)
    print(json.dumps(apply(p.parse_args().source), indent=2))
