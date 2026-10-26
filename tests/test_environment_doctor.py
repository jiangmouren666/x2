"""Doctor failure paths; mocks have no ROS, network, package install or robot calls."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import environment_doctor as d

ROOT = Path(__file__).resolve().parents[1]


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='x2 doctor space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('config/environment.json', 'requirements-dev.txt', 'scripts/project.py', 'scripts/environment_doctor.py'):
            p = self.root / name
            p.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(ROOT / name, p)
        (self.root / 'ENVIRONMENT_KIT.json').write_text('{"scope":"environment-only"}')
        self.probe_error = None
        self.pip_error = None
        self.calls = []

    def fake_run(self, argv, cwd, timeout=20):
        self.calls.append(argv)
        if argv[0] == 'nvidia-smi':
            return 0, 'Mock GPU, 580.126.09, 49140 MiB, 0 MiB', ''
        if argv[0] == 'git':
            return 1, '', ''
        if argv[1:3] == ['-m', 'pip'] or argv[:3] == ['uv', 'pip', 'check']:
            return (1, 'broken dependency', '') if self.pip_error else (0, 'No broken requirements found.', '')
        modules = json.loads(argv[3])
        if self.probe_error == 'timeout':
            return 124, '', 'Timed out'
        items = [dict(module=m, ok=True, version='2.3.5' if m == 'numpy' else None) for m in modules]
        if self.probe_error:
            items.append(dict(module='SDK native type support / fields / ament index', ok=False, error=self.probe_error))
        return 0, 'DOCTOR_PROBE=' + json.dumps(items), ''

    def collect(self, profile='offline', **kwargs):
        with patch.object(d, 'run_local', side_effect=self.fake_run), \
             patch.object(d.platform, 'system', return_value='Linux' if profile == 'ros' else 'Darwin'), \
             patch.object(d.platform, 'machine', return_value='arm64'), \
             patch.object(d.platform, 'python_version', return_value='3.10.12' if profile == 'ros' else '3.12.14'), \
             patch.object(d.sys, 'version_info', (3, 10) if profile == 'ros' else (3, 12)), \
             patch.object(d.shutil, 'which', side_effect=lambda cmd: '/usr/bin/' + cmd), \
             patch.object(d.importlib.metadata, 'version', return_value='2.3.5'), \
             patch.object(d, 'os_release', return_value={'ID':'ubuntu','VERSION_ID':'22.04'}):
            return d.collect(self.root, profile, **kwargs)

    def test_offline_kit_skips_ros_and_project_resources(self):
        r = self.collect()
        self.assertTrue(r['ok'])
        self.assertFalse(r['project_resources_checked'])
        self.assertTrue(any(x['check'] == 'ROS 开发环境' and x['status'] == 'SKIP' for x in r['checks']))
        self.assertTrue(any(x['check'] == 'Git user.email' and x['status'] == 'WARN' for x in r['checks']))
        probes = [argv for argv in self.calls if '-c' in argv]
        self.assertEqual(json.loads(probes[0][3]), ['numpy'])

    def test_ros_missing_environment_and_native_library_fail(self):
        self.probe_error = 'ImportError: native SDK library not found'
        with patch.dict(d.os.environ, {}, clear=True):
            r = self.collect('ros')
        failed = [x['check'] for x in r['checks'] if x['status'] == 'FAIL']
        self.assertIn('ROS_DISTRO', failed)
        self.assertIn('AMENT_PREFIX_PATH', failed)
        self.assertIn('导入 SDK native type support / fields / ament index', failed)
        self.assertFalse(r['ok'])

    def test_ros_matching_local_environment(self):
        with patch.dict(d.os.environ, {'ROS_DISTRO':'humble', 'ROS_VERSION':'2', 'AMENT_PREFIX_PATH':str(self.root)}, clear=True):
            self.assertTrue(self.collect('ros')['ok'])

    def test_import_timeout_is_failure(self):
        self.probe_error = 'timeout'
        self.assertFalse(self.collect()['ok'])

    def test_pip_conflict_is_failure(self):
        self.pip_error = True
        self.assertFalse(self.collect()['ok'])

    def test_wrong_required_package_version_is_failure(self):
        (self.root / 'requirements-dev.txt').write_text('numpy==9.9.9\n')
        self.assertFalse(self.collect()['ok'])

    def test_explicit_full_project_cannot_skip_missing_lock(self):
        r = self.collect(explicit_project=True)
        self.assertFalse(r['ok'])
        self.assertTrue(r['project_resources_checked'])

    def test_changed_project_resource_fails(self):
        (self.root / 'config/source-lock.json').write_text(json.dumps({'files':[{'path':'requirements-dev.txt','sha256':'0'*64}]}))
        r = self.collect()
        self.assertFalse(r['ok'])
        self.assertTrue(r['project_resources_checked'])

    def test_malformed_manifest_returns_failure(self):
        (self.root / 'config/environment.json').write_text('{broken')
        self.assertFalse(d.collect(self.root)['ok'])

    def test_version_range_boundaries_and_prerelease(self):
        self.assertTrue(d.version_satisfies('1.26.4', '>=1.26,<3'))
        self.assertTrue(d.version_satisfies('2.4.6', '>=1.26,<3'))
        self.assertFalse(d.version_satisfies('3.0.0', '>=1.26,<3'))
        self.assertFalse(d.version_satisfies('1.25.9', '>=1.26,<3'))
        self.assertFalse(d.version_satisfies('3.0rc1', '>=1.26,<3'))
        self.assertTrue(d.version_satisfies('2.7.1+cu128', '==2.7.1'))

    def test_uv_check_targets_same_interpreter_when_pip_missing(self):
        old = self.fake_run
        def run(argv, cwd, timeout=20):
            if argv[:3] == ['uv', 'pip', 'check']:
                self.assertEqual(argv[3:], ['--python', sys.executable])
                return 0, 'All installed packages are compatible', ''
            return old(argv, cwd, timeout)
        self.fake_run = run
        with patch.object(d.importlib.util, 'find_spec', return_value=None):
            r = self.collect()
        self.assertTrue(r['ok'])
        self.assertTrue(any(x['check'].startswith('uv pip check') and x['status']=='PASS' for x in r['checks']))

    def test_explicit_missing_simulation_assets_fail(self):
        shutil.copyfile(ROOT/'requirements-mujoco.txt', self.root/'requirements-mujoco.txt')
        r = self.collect('mujoco', simulation_root=self.root/'missing-client')
        self.assertTrue(any(x['check'].startswith('仿真资源') and x['status']=='FAIL' for x in r['checks']))

    def test_inference_missing_checkpoint_and_config_fail(self):
        shutil.copyfile(ROOT/'requirements-inference-check.txt', self.root/'requirements-inference-check.txt')
        r = self.collect('inference', inference_root=self.root/'no-openpi',
                         checkpoint=self.root/'no-checkpoint', policy_config='pi05_x2_tube_lora')
        failed = {x['check'] for x in r['checks'] if x['status']=='FAIL'}
        self.assertTrue({'策略配置名','checkpoint 权重结构','checkpoint 归一化文件'} <= failed)


if __name__ == '__main__':
    unittest.main()
