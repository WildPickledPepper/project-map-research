"""Freeze independently reviewed scope and acceptance tasks; never construct semantic edges."""
import argparse
import ast
from collections import Counter
import itertools
import json
from pathlib import Path, PurePosixPath
import re

from verify_scope import git, verify

ROOT = Path(__file__).resolve().parent


def freeze(source, inventory):
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    reference = load(ROOT / 'scope-reference.json')
    audit = load(ROOT / 'scope-audit-reference.json')
    boundary = load(ROOT / 'boundary-reference.json')
    result = verify(source, inventory, reference)
    checks = result['checks']
    revision = reference['source_commit']
    modules_doc = load(inventory / 'module-inventory.json')
    modules = {m['id']: m for m in modules_doc['modules']}
    files = {f['path']: f for f in modules_doc['files']}
    paths = set(git(source, 'ls-tree', '-r', '--name-only', '-z', revision).decode().split('\0')) - {''}
    texts = {}

    def check(name, passed, detail=None):
        checks.append({'id': name, 'passed': bool(passed), 'detail': detail})

    def text(path):
        if path not in texts:
            texts[path] = git(source, 'show', revision + ':' + path).decode('utf-8')
        return texts[path]

    def evidence(spec):
        lines = [i for i, body in enumerate(text(spec['path']).splitlines(), 1)
                 if spec['contains'] in body] if spec['path'] in paths else []
        return {**spec, 'lines': lines, 'present': bool(lines)}

    check('reference_versions', audit['source_commit'] == boundary['source_commit'] == revision)
    check('no_borrowed_gate_passes', all(set(m['gate_status']) == {f'G{i:02}' for i in range(2,9)} and
          set(m['gate_status'].values()) == {'not_executed'} for m in modules.values()))
    for spec in audit['additional_source_checks']:
        found = evidence(spec)
        check('build_mode_source.' + spec['id'], found['present'], found)
    for profile in audit['profiles']:
        found = evidence(profile['evidence'])
        check('role_profile.' + profile['prefix'] + ('.exact' if profile.get('exact') else ''), found['present'], found)

    audited = []
    for module in modules.values():
        if not (module['required_runtime_review'] or module['required_support_review']):
            continue
        choices = [p for p in audit['profiles'] if module['id'] == p['prefix'] or
                   (not p.get('exact') and module['id'].startswith(p['prefix'] + '/'))]
        check('module_profile.' + module['id'], bool(choices))
        if not choices:
            continue
        profile = max(choices, key=lambda p: (len(p['prefix']), bool(p.get('exact'))))
        support = profile['role'] in {'build_and_packaging_support', 'deployment_support', 'build_support',
                                      'frontend_build_and_workspace_support', 'backend_build_and_configuration_support'}
        check('module_scope_record.' + module['id'], module['discovery_evidence'] and
              module['resource_scope']['semantic_ownership'] == 'pending_W3' and
              module['upstream_downstream_status'] == 'pending_semantic_boundary_analysis')
        audited.append({'id': module['id'], 'parent': module['parent'], 'role': profile['role'],
                        'required_runtime_component': not support, 'required_support_component': support,
                        'source_file_count': module['file_count'], 'language_counts': module['language_counts'],
                        'responsibility': profile['responsibility'], 'responsibility_evidence': profile['evidence'],
                        'discovery_evidence': module['discovery_evidence'],
                        'resource_review_obligations': profile['resources'],
                        'resource_source_candidates': module['resource_scope']['declaration_sources'],
                        'gates': module['gate_status'], 'runtime_executed': False})

    independent_boundaries = []
    for spec in boundary['families'] + boundary['additional_required_interfaces']:
        found = [evidence(spec['source'])]
        if 'target' in spec:
            found.append(evidence(spec['target']))
        check('boundary_source.' + spec['id'], all(e['present'] for e in found), found)
        if 'missing_target' in spec:
            check('declared_missing_target.' + spec['id'], spec['missing_target'] not in paths)
        independent_boundaries.append({**spec, 'source_evidence': found,
                                       'status': 'required_reference_not_accepted', 'required_gate': 'G03'})
    expected_families = {'process_start', 'process_stop', 'network_client', 'network_server', 'network_send',
                         'network_receive', 'window_message', 'worker_start', 'worker_entry', 'webview_load',
                         'registration', 'event_subscription', 'file_access', 'database_operation', 'native_plugin'}
    check('all_boundary_family_references', {s['id'] for s in boundary['families']} == expected_families)
    check('all_boundary_families_have_validation_design', all(s.get('negative') and s.get('runtime') and
          s.get('expectation') for s in boundary['families']))

    modes = []

    def mode(identifier, module, conditions, source_evidence, **extra):
        modes.append({'id': identifier, 'module': module, 'conditions': conditions, 'evidence': source_evidence,
                      'execution_status': 'not_executed', 'required_gate': 'G06', **extra})

    desktop = audit['mode_axes']['desktop']
    check('complete_platform_axes', set(desktop['target_os']) == {'windows','linux','macos'} and
          all(values == [False, True] for values in (desktop['debug_assertions'], desktop['feature_default'], desktop['feature_http'])))
    check('complete_deployment_axes', audit['mode_axes']['docker'] == {'distribution':['ubuntu','openEuler'],
          'tls':['http','https_mtls'],'host_port':['explicit','allocated']} and
          audit['mode_axes']['streamer_start'] == {'mode':['http','mtls','auto'],
          'certificate_input':['absent','valid_triplet','partial_or_invalid'],'host_port':['explicit','allocated']} and
          audit['mode_axes']['streamer_stop']['selection'] == ['name','port','image'])
    for os_name, debug, default, http in itertools.product(desktop['target_os'], desktop['debug_assertions'],
                                                         desktop['feature_default'], desktop['feature_http']):
        values = {'target_os': os_name, 'debug_assertions': debug, 'feature_default': default, 'feature_http': http,
                  'manifest': desktop['manifest_by_os'][os_name]}
        implementation = ('dev_legacy.rs' if os_name == 'linux' else 'dev.rs') if debug else 'default.rs'
        if not default:
            implementation = 'http.rs'
        mode(f'platform.{os_name}.debug{int(debug)}.default{int(default)}.http{int(http)}', 'platform', values,
             [{'path': 'platform/src/main.rs'}, {'path': values['manifest']}, {'path': 'platform/src/' + implementation}],
             dependencies=['python3_and_startup_script'] if not default else ['frontend_backend_artifacts', 'OS_webview_dependencies'],
             required_branches=['normal', 'startup_failure', 'shutdown_cleanup'] +
                               (['linux_root_rejected', 'linux_allow_root'] if os_name == 'linux' else []))
    for distro, tls, port in itertools.product(*audit['mode_axes']['docker'].values()):
        mode(f'docker.{distro}.{tls}.{port}', 'docker', {'distribution': distro, 'tls': tls, 'host_port': port},
             [{'path': 'docker/Dockerfile.' + distro}, {'path': 'docker/entrypoint.sh'}, {'path': 'docker/supervisord.conf'}],
             dependencies=['container_runtime', 'image_artifacts'] + (['certificate_triplet'] if tls != 'http' else []),
             required_branches=['normal', 'partial_certificate_fallback', 'configuration_failure', 'service_stop_cleanup'])
    for tls, certificate, port in itertools.product(*audit['mode_axes']['streamer_start'].values()):
        mode(f'streamer.start.{tls}.{certificate}.{port}', 'streamer', {'mode': tls, 'certificate_input': certificate, 'host_port': port},
             [{'path': 'streamer/run_insight_streamer.py'}], dependencies=['container_runtime', 'image_artifacts'],
             required_branches=['accept_or_reject_configuration', 'image_or_port_failure', 'volume_and_certificate_selection',
                                'launcher_port_and_container_TLS_consistency'])
    for selection in audit['mode_axes']['streamer_stop']['selection']:
        mode('streamer.stop.' + selection, 'streamer', {'selection': selection},
             [{'path': 'streamer/stop_insight_streamer.py'}], dependencies=['container_runtime'],
             required_branches=['matching_container', 'no_match', 'selection_isolation', 'cleanup'])
    for transport in ('http', 'websocket'):
        mode('proxy.' + transport, 'plugins/ProfilerServerProxy', {'transport': transport},
             [{'path': 'plugins/ProfilerServerProxy/core/proxy/multi_aio_proxy_server.py'}],
             dependencies=['proxy_python_dependencies', 'backend_artifact'],
             required_branches=['normal', 'two_pair_isolation', 'backend_selection_failure', 'disconnect_cleanup'])
    mode('jupyterlab.extension', 'plugins/jupyterlab', {'host': 'jupyterlab4'},
         [{'path': 'plugins/jupyterlab/src/index.ts'}, {'path': 'plugins/jupyterlab/mindstudio_insight_jupyterlab/__init__.py'}],
         dependencies=['jupyterlab4', 'built_extension_and_packaged_resources'],
         required_branches=['activation', 'main_interaction', 'two_session_isolation', 'shutdown_cleanup'])
    mode('jupyterlab.declared_console', 'plugins/jupyterlab', {'entry': 'console_scripts'},
         [{'path': 'plugins/jupyterlab/setup.py'}], dependencies=['unresolved_console_module_target'],
         required_branches=['resolve_declared_target_or_surface_dependency_failure'])

    # Independently enumerate actual Python program guards from committed source.
    programs = [];configuration_axes = []
    for path in sorted(paths):
        if not path.endswith('.py') or not path.startswith(('scripts/', 'build/', 'server/build/', 'modules/build/')):
            continue
        if any(p.lower() in {'test', 'tests', '__tests__', 'fixtures'} for p in PurePosixPath(path).parts):
            continue
        tree = ast.parse(text(path))
        guards = [n for n in ast.walk(tree) if isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and
                  len(n.test.ops) == 1 and isinstance(n.test.ops[0], ast.Eq) and
                  re.fullmatch(r"(?:__name__ == ['\"]__main__['\"]|['\"]__main__['\"] == __name__)", ast.unparse(n.test))]
        if not guards:
            continue
        programs.append({'path': path, 'lines': [n.lineno for n in guards]})
        check('program_scope.' + path, path in files and files[path]['module'] in modules)
        mode('program.' + path, files[path]['module'], {'entry': path}, [programs[-1]],
             dependencies=['declared_python_and_external_inputs'],
             required_branches=['normal', 'invalid_input_or_failure', 'output_or_process_cleanup'],
             isolation='dedicated_execution_copy; host/kernel/device examples require an isolated suitable environment')
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 'add_argument'):
                continue
            names = [arg.value for arg in call.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
            if not names:
                continue
            configuration_axes.append({'path':path,'line':call.lineno,'option_names':names,
                'keyword_expressions':{k.arg:ast.unparse(k.value) for k in call.keywords if k.arg},
                'handling':'Required option/value and interaction review for this program; not all combinations are statically valid',
                'receiver_type':'not_proven_by_scope_audit'})

    # Library/frontend/backend components are verified through real consumer scenarios.
    required_module_modes = []
    for module in audited:
        relevant = [m['id'] for m in modes if m['module'] == module['id'] or module['id'].startswith(m['module'] + '/')]
        if not relevant:
            identifier = 'consumer.' + module['id']
            mode(identifier, module['id'], {'consumer_scenario_required': True}, module['discovery_evidence'],
                 dependencies=['real_consumer_entry_and_public_input'],
                 required_branches=['normal', 'applicable_error_or_switch', 'applicable_cleanup'],
                 scenario_status='input_and_assertion_preparation_required')
            relevant = [identifier]
        required_module_modes.append({'module': module['id'], 'mode_ids': relevant})
    check('all_required_modules_have_runtime_obligations', len(required_module_modes) == len(audited) and
          all(m['mode_ids'] for m in required_module_modes))
    check('runtime_mode_ids_unique', len({m['id'] for m in modes}) == len(modes))
    check('no_mode_merges_or_executed_claims', all(m['execution_status'] == 'not_executed' for m in modes))
    unresolved = []
    check('required_unresolved_dependencies_retained', {d['id'] for d in audit['unresolved_dependencies']} ==
          {'headless_start_script','jupyter_console_entry'})
    for spec in audit['unresolved_dependencies']:
        found = evidence(spec)
        check('unresolved_dependency.' + spec['id'], found['present'] and spec['missing_path'] not in paths, found)
        unresolved.append({**spec, 'source_evidence': found, 'status': 'required_dependency_not_resolved'})
    check('no_scope_parse_or_manifest_errors', not modules_doc['diagnostics'], modules_doc['diagnostics'])
    passed = all(c['passed'] for c in checks)
    repository = Path(__file__).resolve().parents[2]
    dirty = git(repository,'status','--porcelain','--','experiments/2026-10-25-w0').decode().strip()
    audit_version = 'uncommitted_development' if dirty else git(repository,'rev-parse','HEAD').decode().strip()
    return {'schema': 'reviewed-project-scope/1', 'source_commit': revision, 'rules_version': result['rules_version'],
            'audit_version':audit_version,
            'origin': 'automatic_inventory_plus_separate_source_audit', 'checks': checks,
            'G01': 'passed' if passed else 'failed', 'overall_technical_acceptance': 'not_passed',
            'modules': audited, 'boundary_references': independent_boundaries,
            'runtime_modes': modes, 'required_module_modes': required_module_modes,
            'programs': programs, 'configuration_axes':configuration_axes,
            'unresolved_dependencies': unresolved, 'freeze_policy': audit['freeze_policy'],
            'summary': {**result['summary'], 'reviewed_required_components': len(audited),
                        'reviewed_runtime_components': sum(m['required_runtime_component'] for m in audited),
                        'reviewed_support_components': sum(m['required_support_component'] for m in audited),
                        'independent_boundary_families': len(boundary['families']),
                        'independent_boundary_references': len(independent_boundaries), 'required_modes': len(modes),
                        'independent_python_programs': len(programs),'independent_configuration_declarations':len(configuration_axes)},
            'semantic_boundary_denominator': 'source_signals_and_independent_references_separate; refine identities in W1/W2 with revision log',
            'gates_G02_G08': 'not_accepted', 'runtime_executed': False, 'historical_assets_enabled': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new freeze output directory')
    result = freeze(args.source, args.inventory)
    args.output.mkdir(parents=True)
    (args.output / 'reviewed-scope.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    # Keep the automated inventory and independently reviewed additions visibly separate.
    for name in ('module-inventory','boundary-inventory','mechanism-matrix','runtime-modes','coverage-baseline'):
        document = json.loads((args.inventory/(name+'.json')).read_text(encoding='utf-8'))
        document['scope_review']={'status':result['G01'],'artifact':'reviewed-scope.json',
            'origin':result['origin'],'audit_version':result['audit_version'],
            'manual_references_used_for_review':True,'semantic_connections_accepted':False}
        if name=='runtime-modes':
            document.update(required_modes=result['runtime_modes'],freeze_status='reviewed_scope_frozen' if result['G01']=='passed' else 'review_failed')
        if name=='coverage-baseline':
            document.update(G01=result['G01'],reviewed_summary=result['summary'])
        (args.output/(name+'.json')).write_text(json.dumps(document,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'G01': result['G01'], 'summary': result['summary'], 'checks': len(result['checks']),
                      'failed': [c for c in result['checks'] if not c['passed']]}, ensure_ascii=False))
    if result['G01'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
