"""Terminal workflows around implemented tools; no robot motion commands."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def step(title, argv, cwd, log):
    print('\n=== ' + title + ' ===', flush=True)
    import shlex
    print('$ ' + shlex.join(map(str, argv)), flush=True)
    with log.open('x') as stream:
        process = subprocess.Popen(list(map(str, argv)), cwd=cwd, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
                stream.write(line)
            code = process.wait()
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise
    if code:
        raise RuntimeError(f'{title} failed with exit code {code}; see {log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='workflow', required=True)
    offline = sub.add_parser('offline', help='Check baseline, generate preview, summarize output')
    offline.add_argument('--project-root', type=Path, default=ROOT)
    scene = sub.add_parser('scene', help='Compile and render existing MuJoCo scene (no policy)')
    scene.add_argument('--simulation-root', type=Path, required=True)
    pictures = sub.add_parser('images', help='Extract JPEGs from an existing HAND_REVIEW capture')
    pictures.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, default=ROOT/'runs')
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='demo-'+args.workflow+'-', dir=args.output_root)).resolve()
    report = dict(workflow=args.workflow, status='RUNNING', output=str(out), robot_motion=False,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  python=sys.executable,
                  workflow_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print('Output:', out, flush=True)
    try:
        if args.workflow == 'offline':
            root = args.project_root.resolve()
            step('1. Environment, assets and regression checks',
                 [sys.executable, root/'scripts/project.py', 'check', '--profile', 'offline',
                  '--report', out/'check.json'], root, out/'01-check.log')
            step('2. Generate right elbow preview from synthetic data',
                 [sys.executable, '-m', 'x2.planning.right_arm_preview', '--snapshot',
                  root/'tests/fixtures/synthetic-preflight.json', '--output', out/'preview.json',
                  '--delta-deg', '1', '--max-rate-deg-s', '0.5'], root, out/'02-preview.log')
            data = json.loads((out/'preview.json').read_text())
            report['summary'] = {key: data[key] for key in
                ('status', 'executable', 'changed_joint', 'duration_s', 'requested_delta_deg', 'peak_rate_deg_s')}
            report['summary']['frames'] = len(data['frames'])
            print('\n=== 3. Preview result (synthetic input, no robot) ===')
            print(json.dumps(report['summary'], indent=2, ensure_ascii=False))
        elif args.workflow == 'scene':
            step('1. MuJoCo environment', [sys.executable, ROOT/'scripts/project.py', 'doctor',
                 '--profile', 'mujoco', '--simulation-root', args.simulation_root.resolve()], ROOT, out/'01-environment.log')
            step('2. Compile, simulate ten steps and render cameras',
                 [sys.executable, ROOT/'scripts/check_mujoco_scene.py', '--simulation-root',
                  args.simulation_root.resolve(), '--render'], ROOT, out/'02-render.log')
        else:
            capture = args.capture.read_bytes()
            report['source'] = str(args.capture.resolve())
            report['source_sha256'] = hashlib.sha256(capture).hexdigest()
            rows = [line.split('=', 1)[1] for line in capture.decode().splitlines()
                    if line.startswith('HAND_REVIEW=')]
            if len(rows) != 1:
                raise ValueError('Expected exactly one HAND_REVIEW record')
            data = json.loads(rows[0])
            report['source_provenance'] = data.get('provenance', 'Unspecified; do not infer capture time')
            missing = []
            for name in ('head', 'wrist'):
                value = data.get('jpeg_base64', {}).get(name)
                if not value:
                    missing.append(name)
                    continue
                raw = base64.b64decode(value, validate=True)
                if not raw.startswith(b'\xff\xd8'):
                    raise ValueError('Not JPEG: ' + name)
                (out/(name+'.jpg')).write_bytes(raw)
                print(name, out/(name+'.jpg'))
            report['source'] = str(args.capture.resolve())
            report['note'] = 'Recorded diagnostic images, not live or synchronized training data'
            if missing:
                raise ValueError('Missing cameras: '+', '.join(missing)+'; '+str(data.get('wrist_error', '')))
        report['status'] = 'PASS'
        return 0
    except KeyboardInterrupt:
        report.update(status='INTERRUPTED', error='Interrupted by operator')
        print('INTERRUPTED', file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        report.update(status='FAIL', error=str(exc))
        print('FAIL:', exc, file=sys.stderr)
        return 1
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (out/'workflow.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
        print('Workflow report:', out/'workflow.json', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
