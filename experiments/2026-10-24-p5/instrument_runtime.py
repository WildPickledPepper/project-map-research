"""Add explicit P5 capture points to the isolated, push-disabled product clone."""
import argparse
import json
from pathlib import Path
import subprocess

BASE = 'd4e8d1cf9f90208bcbe5371c127088f6fd66c688'
HERE = Path(__file__).resolve().parent


def instrument(source, *, dry_run=False):
    source = Path(source).resolve()
    git = lambda *args: subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    if git('remote', 'get-url', '--push', 'origin') != 'disabled://p5-local-experiment':
        raise ValueError('Instrumentation requires the isolated push-disabled P5 clone')
    if git('rev-parse', 'HEAD') != BASE: raise ValueError('Expected pinned product baseline before applying capture')
    if git('status', '--porcelain', '--untracked-files=no'): raise ValueError('Experimental source already has tracked changes')
    changes = {}

    def replace(path, old, new):
        current = changes.get(path, (source/path).read_text(encoding='utf-8'))
        if current.count(old) != 1: raise ValueError('Expected exactly one capture insertion point: ' + path + ': ' + old[:60])
        changes[path] = current.replace(old, new)

    manager = 'server/src/modules/ProtocolManager.cpp'
    replace(manager, '#include "ProtocolManager.h"', '#include "ProtocolManager.h"\n#include "ProjectMapProbe.h"')
    replace(manager, 'return protocolMap.at(moduleName)->FromJson(requestJson.value(), error);',
        'auto parsed = protocolMap.at(moduleName)->FromJson(requestJson.value(), error);\n'
        '    if (parsed) {\n'
        '        auto traceId = ProjectMapProbe::TraceId(requestJson.value());\n'
        '        ProjectMapProbe::Emit("request.decoded", ProjectMapProbe::Capture(*parsed), "", -1, traceId.c_str());\n'
        '    }\n    return parsed;')
    handler = 'server/msinsight/src/base/ModuleRequestHandler.cpp'
    replace(handler, '#include "RequestFilter.h"', '#include "RequestFilter.h"\n#include "ProjectMapProbe.h"')
    replace(handler, 'bool res = HandleRequest(std::move(requestPtr));',
        'const auto probeIdentity = ProjectMapProbe::Capture(*requestPtr);\n'
        '    ProjectMapProbe::Emit("handler.invoke", probeIdentity, typeid(*this).name());\n'
        '    bool res = HandleRequest(std::move(requestPtr));\n'
        '    ProjectMapProbe::Emit("handler.complete", probeIdentity, typeid(*this).name(), res ? 1 : 0);')
    flow = 'server/src/modules/timeline/handler/QueryFlowsBySliceInfoHandler.cpp'
    replace(flow, '#include "QueryFlowsBySliceInfoHandler.h"', '#include "QueryFlowsBySliceInfoHandler.h"\n#include "ProjectMapProbe.h"')
    replace(flow, 'database->QueryUnitFlows(queryParams, response.body, minTimestamp, trackId);',
        'ProjectMapProbe::Emit("database.call", ProjectMapProbe::Capture(request), typeid(*database).name());\n'
        '        database->QueryUnitFlows(queryParams, response.body, minTimestamp, trackId);\n'
        '        ProjectMapProbe::Emit("database.return", ProjectMapProbe::Capture(request), typeid(*database).name(),\n'
        '            static_cast<int>(response.body.unitAllFlows.size()));')
    api = 'modules/timeline/src/api/request.ts'
    replace(api, "return window.requestData('unit/flows', params, 'timeline');",
        "const probe = (globalThis as any).__projectMapProbe;\n"
        "    const traceId = probe?.begin(params);\n"
        "    const sentParams = traceId ? { ...params, __projectMapTrace: traceId } : params;\n"
        "    const result = await window.requestData('unit/flows', sentParams, 'timeline');\n"
        "    probe?.resolved(traceId, result);\n"
        "    return result;")
    connection = 'modules/framework/src/centralServer/websocket/connection.ts'
    replace(connection, "if (!isImport && isOldRequest) {",
        "(globalThis as any).__projectMapProbe?.event('response.classified', { requestId: reqId, command: msg.command,\n"
        "            requestProject: requestMsg?.projectName, currentProject: currentProjectName, isOldRequest });\n"
        "        if (!isImport && isOldRequest) {\n"
        "            (globalThis as any).__projectMapProbe?.event('response.discarded', { requestId: reqId, command: msg.command });")
    replace(connection, 'callback(msg);',
        "(globalThis as any).__projectMapProbe?.event('response.delivered', { requestId: reqId, command: msg.command });\n"
        "        callback(msg);")
    unit = 'modules/timeline/src/insight/units/AscendUnit.tsx'
    # Anchor to the full update block so unrelated render toggles remain untouched.
    old = """session.drawLineMode = 'single';
                session.linkLines = {};
                session.singleLinkLine = newLines;
                session.renderTrigger = !session.renderTrigger;
            });"""
    replace(unit, old, old + "\n            (globalThis as any).__projectMapProbe?.stateApplied(raw, session, 'AscendUnit.onClick');")
    filter_path = 'modules/timeline/src/components/FilterLinkLine.tsx'
    old = """session.singleLinkLine = newLines;
            session.renderTrigger = !session.renderTrigger;
        });"""
    replace(filter_path, old, old + "\n        (globalThis as any).__projectMapProbe?.stateApplied(raw, session, 'FilterLinkLine.getSingleFlow');")
    # Read-only access for independent assertions. The driver never changes state through these readers.
    for module in ('framework', 'timeline'):
        store = 'modules/' + module + '/src/store/session.ts'
        replace(store, 'makeAutoObservable(this);',
            'makeAutoObservable(this);\n        (globalThis as any).__projectMapReadSession = () => this._activeSession;')
    helper = 'server/msinsight/include/base/ProjectMapProbe.h'
    if (source/helper).exists(): raise ValueError('Capture helper already exists')
    changes[helper] = (HERE/'ProjectMapProbe.h').read_text(encoding='utf-8')
    # All locations are validated before the first write; originals remain in the pinned Git commit.
    if not dry_run:
        for path, content in changes.items(): (source/path).write_text(content, encoding='utf-8', newline='\n')
    return {'base_commit': BASE, 'files': list(changes), 'effect': 'capture plus optional trace metadata in request params',
            'applied': not dry_run, 'source_is_experimental': True, 'fault_injection': False,
            'file_hash_verification': 'not_run_per_user_preference'}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(); print(json.dumps(instrument(a.source, dry_run=a.dry_run), ensure_ascii=False, indent=2))
