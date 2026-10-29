"""Local application acceptance: exact ZIP, real activation, tests and authoring rules.

Never uploads, installs services, changes Core or grants permissions. Exit 0 means
local checks passed; release_ready remains separate. --require-ready also gates
unresolved platform dependencies and manual acceptance.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True


def local_path(root, value):
    path = (root / value).resolve()
    if root != path and root not in path.parents:
        raise ValueError('Project input escapes its root: ' + value)
    return path


def inventory(root, inputs):
    files = set()
    for entry in inputs:
        path = local_path(root, entry)
        if not path.exists():
            raise ValueError('Missing declared input: ' + entry)
        files.update([path] if path.is_file() else (p for p in path.rglob('*') if p.is_file()
            and not set(p.parts) & {'.runtime', 'node_modules', '__pycache__', '.pytest_cache', '.git'}))
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def authoring_findings(files):
    findings = catalog_findings(files)
    ui = {name: data.decode('utf-8') for name, data in files.items() if name.endswith(('.vue', '.ts', '.css', '.js'))}
    combined = '\n'.join(ui.values())
    if '@3mm/ui/v1' not in combined or 'UiSurface' not in combined:
        findings.append('Use the public @3mm/ui/v1 presentation components and UiSurface.')
    for name, source in ui.items():
        if re.search(r'var\(--(?:surface-color|text-color|border-color|bg-primary)\b', source):
            findings.append(name + ': obsolete theme token; use the public --ui-* surface/text/border contract.')
        if 'prefers-color-scheme' in source or re.search(r"(?:getItem|setItem)\(['\"]theme['\"]", source):
            findings.append(name + ': Core owns the theme; do not infer or store an application theme.')
        if re.search(r'(?:background(?:-color)?|color|border-color)\s*:\s*(?:#[0-9a-fA-F]{3,8}\b|(?:rgb|hsl)a?\()', source):
            findings.append(name + ': use Core palette tokens instead of hardcoded control/surface colors.')
        if re.search(r'\bauthToken\b|\bfetch\s*\(|/api/v1/', source):
            findings.append(name + ': direct credentials/HTTP; use the public application host.')
        if 'preferredLanguage' in source or 'language-changed' in source:
            findings.append(name + ': application-managed Core locale state/event; require a public host locale binding.')
    return findings


def catalog_findings(files):
    baselines = [name for name in files if name.endswith('/locales/en.json')]
    if not baselines: return ['An English source catalogue is required; Bulgarian is optional.']
    issues = []
    for baseline in baselines:
        try:
            en = json.loads(files[baseline])
            if not isinstance(en, dict) or not en or any(not isinstance(v, str) or not v for v in en.values()):
                issues.append(baseline + ': English keys must have nonempty text.')
                continue
            prefix = baseline.rsplit('/', 1)[0] + '/'
            for name, data in files.items():
                if name.startswith(prefix) and name.endswith('.json'):
                    catalog = json.loads(data)
                    if not isinstance(catalog, dict) or any(not isinstance(v, str) for v in catalog.values()):
                        issues.append(name + ': catalogue values must be strings.')
            root = prefix.removesuffix('locales/')
            for name, data in files.items():
                if name.startswith(root) and name.endswith(('.vue', '.ts')):
                    for key in re.findall(r"\bt\(['\"]([a-z0-9_]+)['\"]\)", data.decode('utf-8')):
                        if key not in en: issues.append(name + ': missing English key ' + key)
        except (ValueError, UnicodeError):
            issues.append(baseline + ': invalid locale catalogue JSON.')
    return issues


def preset_findings(definition, profile='native_sqlite'):
    # This is the tested starter preset, NOT a claim that other Core profiles
    # are unsupported. A different preset needs its own execution evidence.
    storage = definition.get('storage', {})
    commerce = profile == 'native_sqlite_interactive_commerce_events_v1'
    if profile not in ('native_sqlite', 'native_sqlite_read_connectors_v1', 'native_sqlite_read_connectors_events_v1','native_sqlite_interactive_commerce_events_v1'):
        return ['Unknown acceptance profile: ' + profile]
    forbidden = [name for name in ('jobs', 'tasks', 'command_bindings',
        'public_http_routes', 'session_bindings', 'peer_bindings') if definition.get(name)]
    forbidden += ['storage.' + name for name in ('relational', 'private_files') if storage.get(name)]
    connectors = definition.get('connectors', [])
    if connectors and profile == 'native_sqlite':
        forbidden.append('connectors')
    events = definition.get('event_subscriptions', [])
    if events and profile not in ('native_sqlite_read_connectors_events_v1','native_sqlite_interactive_commerce_events_v1'):
        forbidden.append('event_subscriptions')
    if profile in ('native_sqlite_read_connectors_v1','native_sqlite_read_connectors_events_v1','native_sqlite_interactive_commerce_events_v1'):
        scopes = {'connector:' + c['connector_id'] for c in connectors}
        if events: scopes |= {'event:' + e['subscription_id'] for e in events}
        if (not 1 <= len(connectors) <= 4 or definition.get('service', {}).get('sdk_version') != '1.3'
                or set(definition.get('optional_resources', [])) != scopes
                or any((c.get('supports_mutations', False) and not commerce) or c.get('timeout_seconds', 10) > (2 if commerce else 5)
                    or c.get('max_request_bytes', 256*1024) > 8192 or c.get('max_response_bytes', 1024*1024) > 512*1024
                    or c.get('path_prefix', '/') == '/' for c in connectors)):
            forbidden.append('bounded optional read-only connector profile')
    if profile in ('native_sqlite_read_connectors_events_v1','native_sqlite_interactive_commerce_events_v1'):
        operations = {op['operation_id']:op for op in definition.get('operations',[])}
        if (not 1 <= len(events) <= 2 or any(e.get('acknowledgement') != 'after_commit' or e.get('max_backlog',1000)>1000
                or operations.get(e['handler_operation_id'],{}).get('audiences') != ['internal']
                or operations.get(e['handler_operation_id'],{}).get('kind') != 'command'
                or operations.get(e['handler_operation_id'],{}).get('idempotency') != 'required' for e in events)):
            forbidden.append('bounded after-commit internal event profile')
    if commerce and any(op.get('kind')=='command' and op.get('idempotency')!='required' for op in definition.get('operations',[])):
        forbidden.append('durable interactive mutation identity')
    return ['Outside acceptance profile ' + profile + ': ' + ', '.join(forbidden)] if forbidden else []


def run_command(command, cwd, env, log):
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command exited {result.returncode}; see {log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--core-source', type=Path, required=True, help='Read-only current Core source')
    parser.add_argument('--frontend-root', type=Path, required=True, help='Existing Vue/Vite toolchain root')
    parser.add_argument('--node', default='node')
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    root = args.project.resolve(); core = args.core_source.resolve()
    config = json.loads((root / 'app-development.json').read_text(encoding='utf-8'))
    if config.get('contract_version') != 1:
        raise ValueError('Unsupported app-development.json contract')
    output = root / '.runtime/application-checks' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    report = {'report_version': 1, 'project': str(root), 'gates': {}, 'release_ready': False,
        'core_source': str(core),
        'manual_pending': config.get('manual_acceptance', []), 'platform_blockers': config.get('platform_blockers', []),
        'scope': 'local sources/SDK/host; no installed systemd/ARM or visual acceptance'}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(core))
    env['THREE_MM_FRONTEND_ROOT'] = str(args.frontend_root.resolve())
    env['THREE_MM_PUBLIC_HOST'] = str(core / 'frontend/src/extension-ui/application-v1.ts')
    env['THREE_MM_APP_PROJECT'] = str(root)
    env['THREE_MM_APP_STAGE'] = str(output / 'stage')
    env['THREE_MM_APP_CHECK_OUTPUT'] = str(output / 'frontend')
    sys.path.insert(0, str(core)); sys.path.insert(0, str(root))
    def gate(name, action):
        started = time.monotonic()
        try:
            value = action()
            report['gates'][name] = {'status': 'passed', 'detail': value, 'seconds': round(time.monotonic()-started, 3)}
            print(name + ': passed', flush=True)
            return value
        except Exception as error:
            report['gates'][name] = {'status': 'failed', 'detail': str(error), 'seconds': round(time.monotonic()-started, 3)}
            print(name + ': FAILED — ' + str(error), flush=True)
            return None
    try:
        before = inventory(root, config['source_inputs'])
        builder_path = local_path(root, config['builder'])
        spec = importlib.util.spec_from_file_location('checked_app_builder', builder_path)
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        files = {}
        archive = output / 'candidate.zip'
        def package():
            from backend.services.module_packages import validate_module_package
            payload = builder.build_package()
            if payload != builder.build_package():
                raise ValueError('Package is not deterministic')
            with zipfile.ZipFile(io.BytesIO(payload)) as package_archive:
                files.update({name: package_archive.read(name) for name in package_archive.namelist()})
            definition = json.loads(files['application-extension.json'])
            issues = preset_findings(definition, config.get('acceptance_profile', 'native_sqlite'))
            if issues: raise ValueError('; '.join(issues))
            validated = validate_module_package(payload)
            archive.write_bytes(payload)
            stage = output / 'stage'
            for name, data in files.items():
                target = local_path(stage.resolve(), name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            report['artifact'] = {'path': str(archive), 'sha256': hashlib.sha256(payload).hexdigest(),
                'bytes': len(payload), 'module_id': validated.manifest.module_id, 'version': validated.manifest.version}
            return report['artifact']
        if gate('package_and_preset', package):
            def activation():
                if sys.platform != 'linux': raise RuntimeError('Real AF_UNIX host check requires Linux/WSL; not a pass on Windows')
                from application_process_check import activation_smoke
                return activation_smoke(archive, output / 'activation')
            gate('standard_activation_and_restart', activation)
        def python_tests():
            tests = config.get('python_tests', [])
            if not tests: raise ValueError('No application behavior tests declared')
            for test in tests: local_path(root, test)
            xml = output / 'python.xml'
            run_command([sys.executable, '-m', 'pytest', '-q', *tests, '-p', 'no:cacheprovider',
                '--basetemp=' + str(output/'pytest'), '--junitxml=' + str(xml)], root, env, output/'python.log')
            suites = ET.parse(xml).getroot().iter('testsuite')
            totals = {key: 0 for key in ('tests', 'failures', 'errors', 'skipped')}
            for suite in suites:
                for key in totals: totals[key] += int(suite.attrib.get(key, 0))
            if totals['tests'] == 0 or totals['skipped']: raise ValueError('Required tests are empty or skipped: ' + str(totals))
            return totals
        gate('application_behavior', python_tests)
        def frontend():
            script = local_path(root, config['frontend_check'])
            run_command([args.node, str(script)], root, env, output/'frontend.log')
            result = json.loads((output/'frontend/frontend-check.json').read_text())
            if any(result.get(key) != 'passed' for key in ('typecheck', 'build', 'tests')):
                raise ValueError('Frontend checks are incomplete')
            return result
        gate('frontend', frontend)
        def presentation():
            issues = authoring_findings(files)
            if issues: raise ValueError('; '.join(issues))
            return 'Public UI components/tokens; no credential or locale-store coupling detected. Static check, not visual acceptance.'
        gate('presentation_contract', presentation)
        def unchanged():
            if inventory(root, config['source_inputs']) != before or builder.build_package() != archive.read_bytes():
                raise ValueError('Inputs changed during checks; do not reuse this evidence')
            report['source_sha256'] = before
            return 'Exact built bytes and declared inputs unchanged'
        if archive.exists(): gate('input_integrity', unchanged)
    except Exception as error:
        report['gates']['setup'] = {'status': 'failed', 'detail': str(error)}
    failed = any(item['status'] != 'passed' for item in report['gates'].values())
    report['local_checks_passed'] = not failed
    report['release_ready'] = not failed and not report['manual_pending'] and not report['platform_blockers']
    report['exit_code'] = 1 if failed else 2 if args.require_ready and not report['release_ready'] else 0
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('REPORT: ' + str(output/'report.json'))
    print('RELEASE_READY: ' + str(report['release_ready']).lower())
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
