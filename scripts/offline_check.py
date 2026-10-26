"""Reproducible offline baseline check. No ROS, robot, SSH, or model service."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from environment_doctor import collect, project_path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv, root, timeout=120):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               PIP_NO_INDEX='1', UV_OFFLINE='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    try:
        p = subprocess.run(argv, cwd=root, env=env, capture_output=True,
                           text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return dict(returncode=p.returncode, stdout=p.stdout[-24000:], stderr=p.stderr[-24000:])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(returncode=124, stdout='', stderr=str(exc))


def assets_check(root):
    manifest = json.loads((root/'assets/manifest.json').read_text())
    if manifest['schema_version'] != 1 or not manifest['assets']:
        raise ValueError('Invalid or empty asset manifest')
    rows = []
    for entry in manifest['assets']:
        if not entry['required_for_offline']:
            rows.append(dict(name=entry['name'], status='SKIP', reason='Outside offline baseline',
                             availability=entry.get('status', 'external')))
            continue
        path = project_path(root, entry['path'])
        actual = sha(path) if path.is_file() else None
        ok = isinstance(entry.get('sha256'), str) and len(entry['sha256']) == 64 and actual == entry['sha256']
        rows.append(dict(name=entry['name'], path=entry['path'], status='PASS' if ok else 'FAIL',
                         expected_sha256=entry.get('sha256'), actual_sha256=actual))
    if not any(x['status'] != 'SKIP' for x in rows):
        raise ValueError('No required offline fixture declared')
    return rows


def snapshot(root):
    entries = json.loads((root/'config/baseline-files.json').read_text())['files']
    if not entries or len(set(entries)) != len(entries):
        raise ValueError('Empty or duplicate baseline source list')
    hashes = {name: sha(project_path(root, name)) for name in entries}
    hashes['config/baseline-files.json'] = sha(root/'config/baseline-files.json')
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(sha256=fingerprint, files=hashes)


def execute(root, output=None):
    root = Path(root).resolve()
    report = dict(schema_version=1, version='0.1.0', profile='offline',
                  created_utc=datetime.now(timezone.utc).isoformat(), root=str(root),
                  platform=dict(system=platform.system(), machine=platform.machine(), python=platform.python_version()),
                  scope='Offline arithmetic, previews, candidate AST regressions and environment diagnostics',
                  robot_access=False, hardware_approved=False, phases=[])
    phases = report['phases']
    commit = run(['git','rev-parse','--verify','HEAD'], root)
    status = run(['git','status','--porcelain','--untracked-files=normal'], root)
    report['git'] = dict(commit=commit['stdout'].strip() if commit['returncode']==0 else None,
                         dirty=bool(status['stdout']) if status['returncode']==0 else None,
                         status=status['stdout'] if status['returncode']==0 else 'Not a Git checkout')
    report['dependencies'] = sorted([dict(name=d.metadata['Name'], version=d.version)
                                     for d in importlib.metadata.distributions()], key=lambda d:d['name'].lower())
    report['numeric_tolerances'] = dict(budget_mm_abs=1e-9, preview_rate_deg_s_abs=1e-9,
                                        preview_angle_deg_abs=1e-7, file_sha256='exact')
    try:
        report['source_snapshot'] = snapshot(root)
        phases.append(dict(name='source_inventory', status='PASS'))
    except (OSError, ValueError, KeyError) as exc:
        phases.append(dict(name='source_inventory', status='FAIL', reason=str(exc)))
    environment = collect(root, 'offline', explicit_project=True)
    report['environment'] = environment
    phases.append(dict(name='environment', status='PASS' if environment['ok'] else 'FAIL'))
    try:
        locked = json.loads((root/'assets/offline-wheels.json').read_text())
        mismatches = {name: dict(expected=entry['version'], actual=importlib.metadata.version(name))
                      for name, entry in locked.items()
                      if importlib.metadata.version(name) != entry['version']}
        phases.append(dict(name='locked_runtime_and_build_tools', status='FAIL' if mismatches else 'PASS',
                           mismatches=mismatches))
    except (OSError, ValueError, KeyError, importlib.metadata.PackageNotFoundError) as exc:
        phases.append(dict(name='locked_runtime_and_build_tools', status='FAIL', reason=str(exc)))
    # Ensure the installed package is this checkout, not a stale copy in another path.
    probe = run([sys.executable, '-c',
                 'import x2, pathlib, sys; '
                 'p=pathlib.Path(x2.__file__).resolve(); print(p); '
                 'sys.exit(0 if p==pathlib.Path(sys.argv[1]).resolve() else 1)',
                 str(root/'src/x2/__init__.py')], root)
    phases.append(dict(name='installed_project', status='PASS' if probe['returncode']==0 else 'FAIL', **probe))
    try:
        report['assets'] = assets_check(root)
        ok = all(x['status'] != 'FAIL' for x in report['assets'])
        phases.append(dict(name='required_assets', status='PASS' if ok else 'FAIL'))
    except (OSError, ValueError, KeyError) as exc:
        phases.append(dict(name='required_assets', status='FAIL', reason=str(exc)))
    prerequisite_ok = all(x['status']=='PASS' for x in phases)
    suites = [('unit_environment_and_fixed_regressions', ['-m','unittest','discover','-s','tests','-p','test_*.py','-v'])]
    # One discovery includes unit and fixed-fixture regression suites; tests are never duplicated here.
    for name, argv in suites:
        if not prerequisite_ok:
            phases.append(dict(name=name,status='SKIP',reason='Prerequisite failed'))
            continue
        result = run([sys.executable, *argv],root)
        phases.append(dict(name=name,status='PASS' if result['returncode']==0 else 'FAIL', **result))
    report['known_defect_characterizations'] = []
    for script in ('audit_stop_contract.py', 'audit_arm_only_hand_hold.py'):
        if not prerequisite_ok:
            result = dict(status='SKIP', reason='Prerequisite failed')
        else:
            result = run([sys.executable, str(root/'scripts'/script)], root)
            result['status'] = 'REPRODUCED_KNOWN_DEFECT' if result['returncode']==0 else 'FAIL_REVIEW_REQUIRED'
        report['known_defect_characterizations'].append(dict(script=script, **result))
    report['ok'] = all(x['status']=='PASS' for x in phases) and all(
        x['status']=='REPRODUCED_KNOWN_DEFECT' for x in report['known_defect_characterizations'])
    report['result'] = 'OFFLINE_BASELINE_PASS_WITH_KNOWN_CONTROLLER_DEFECTS' if report['ok'] else 'OFFLINE_BASELINE_FAIL'
    # Exclusive creation keeps old evidence intact.
    if output is None:
        output = root/'runs'/('check-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write('\n')
    for phase in phases:
        print(phase['status'], phase['name'])
        if phase['status']=='FAIL':
            print(phase.get('reason') or phase.get('stderr') or 'See detailed report')
    for row in report['known_defect_characterizations']:
        print(row['status'], row['script'])
    print(report['result'])
    print('REPORT', output.resolve())
    return 0 if report['ok'] else 1
