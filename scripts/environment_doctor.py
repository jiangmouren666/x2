"""Local checks only: no ROS initialization, discovery, SSH or installation.

Imports are isolated in a bounded child process to detect native SDK/ABI errors.
No robot controller is imported. Python 3.9+ can diagnose newer requirements.
"""
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import hashlib

PROBE = r'''
import importlib, importlib.metadata, json, sys
result = []
modules = json.loads(sys.argv[1])
for name in modules:
    try:
        module = importlib.import_module(name)
        result.append({'module': name, 'ok': True, 'version': getattr(module, '__version__', None)})
    except Exception as exc:
        result.append({'module': name, 'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)})
if sys.argv[2] == 'ros':
    try:
        from rclpy.type_support import check_for_type_support
        from aimdk_msgs.msg import UpperBodyCommandArray, HandStateArray, HandState
        from aimdk_msgs.srv import GetCurrentInputSource
        for cls in (UpperBodyCommandArray, HandStateArray, HandState, GetCurrentInputSource):
            check_for_type_support(cls)
        required = {
            UpperBodyCommandArray: {'header', 'source', 'hand_sub_mode', 'head_pos', 'arm_pos', 'hand_pos'},
            HandState: {'name', 'position', 'velocity', 'effort', 'state', 'faultcode'},
            HandStateArray: {'left_hands', 'right_hands', 'left_hand_type', 'right_hand_type'},
        }
        for cls, fields in required.items():
            missing = fields - set(cls.get_fields_and_field_types())
            if missing:
                raise ValueError(cls.__name__ + ' missing fields: ' + repr(sorted(missing)))
        from ament_index_python.packages import get_package_prefix
        prefix = get_package_prefix('aimdk_msgs')
        result.append({'module': 'SDK native type support / fields / ament index', 'ok': True, 'prefix': prefix})
    except Exception as exc:
        result.append({'module': 'SDK native type support / fields / ament index', 'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)})
print('DOCTOR_PROBE=' + json.dumps(result))
'''


def run_local(argv, cwd, timeout=20):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
               UV_OFFLINE='1', XLA_PYTHON_CLIENT_PREALLOCATE='false')
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, '', str(exc)


def os_release():
    p = Path('/etc/os-release')
    if not p.is_file():
        return {}
    return {k: v.strip('"') for line in p.read_text().splitlines()
            if '=' in line for k, v in [line.split('=', 1)]}


def pinned_requirements(path):
    pins = {}
    for line in path.read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)((?:(?:==|>=|<)[0-9.]+)(?:,(?:==|>=|<)[0-9.]+)*)', line)
        if not match:
            raise ValueError('检查器仅支持 ==、>=、< 的稳定数字版本约束：' + line)
        pins[match[1]] = match[2]
    return pins


def version_satisfies(actual, constraints):
    if not actual or not re.fullmatch(r'\d+(?:\.\d+)*(?:\+[A-Za-z0-9.]+)?', actual):
        return False
    version = tuple(map(int, actual.split('+')[0].split('.')))
    for constraint in constraints.split(','):
        match = re.fullmatch(r'(==|>=|<)([0-9.]+)', constraint)
        if not match:
            return False
        op, limit = match.groups()
        expected = tuple(map(int, limit.split('.')))
        size = max(len(version), len(expected))
        a, b = version + (0,) * (size - len(version)), expected + (0,) * (size - len(expected))
        if not {'==': a == b, '>=': a >= b, '<': a < b}[op]:
            return False
    return True


def project_path(root, relative):
    p = (root / relative).resolve()
    if root.resolve() not in p.parents:
        raise ValueError('项目清单路径超出根目录：' + relative)
    return p


def collect(root, profile='offline', explicit_project=False, simulation_root=None,
            inference_root=None, checkpoint=None, policy_config=None):
    root = Path(root).resolve()
    rows = []

    def add(status, check, detail, remedy=''):
        rows.append(dict(status=status, check=check, detail=detail, remedy=remedy))

    report = dict(profile=profile, root=str(root), python=sys.executable,
                  project_resources_checked=False, checks=rows)
    try:
        spec = json.loads((root / 'config/environment.json').read_text())
        if spec['schema_version'] != 1:
            raise ValueError('不支持的环境声明版本')
        cfg = spec['profiles'][profile]
        report['spec_revision'] = spec['revision']
    except (OSError, ValueError, KeyError, TypeError) as exc:
        add('FAIL', '环境声明', str(exc), '获取完整项目或共享检查包；--project-root 指向项目根目录。')
        return finish(report)

    system, arch = platform.system(), platform.machine().lower()
    add('PASS' if system in cfg['systems'] else 'FAIL', '操作系统', system,
        '此 profile 的支持范围：' + ', '.join(cfg['systems']))
    add('PASS' if arch in spec['architectures'] else 'WARN', 'CPU 架构', arch,
        'SDK 原生库也必须匹配本机架构；后续导入检查会核对是否能加载。')
    if 'os_release' in cfg:
        actual = os_release()
        ok = all(actual.get(k) == v for k, v in cfg['os_release'].items())
        add('PASS' if ok else 'FAIL', 'ROS 目标系统',
            actual.get('PRETTY_NAME', system), '当前项目 ROS profile 面向 Ubuntu 22.04 / Humble。')
    py = tuple(sys.version_info[:2])
    ok = tuple(cfg['python_min']) <= py < tuple(cfg['python_max_exclusive'])
    add('PASS' if ok else 'FAIL', 'Python 版本', platform.python_version(), cfg['python_help'])
    active = sys.prefix != sys.base_prefix or bool(os.environ.get('CONDA_PREFIX'))
    add('PASS' if active else 'WARN', '当前虚拟环境',
        sys.prefix if active else '当前是基础解释器；不是项目专用虚拟环境',
        'offline 建议使用 .venv；ros 可以使用匹配系统 ROS 的 Python，勿混入离线 Python 3.12 环境。')
    for cmd in cfg['commands']:
        found = shutil.which(cmd)
        hint = '安装该工具并确保当前 shell 的 PATH 可找到它。'
        if cmd in ('ros2', 'colcon'):
            hint = '安装 Humble/colcon 开发工具；source /opt/ros/humble/setup.bash，再加载本机 SDK overlay。'
        add('PASS' if found else 'FAIL', '命令 ' + cmd, found or '未找到', hint)
    if shutil.which('git'):
        for key in ('user.name', 'user.email'):
            rc, out, _ = run_local(['git', 'config', '--get', key], root)
            add('PASS' if rc == 0 and out.strip() else 'WARN', 'Git ' + key,
                '已配置' if rc == 0 and out.strip() else '尚未配置，不影响环境检查和离线测试',
                '准备提交版本时再配置真实署名；检查器不会代填或修改 Git。')
    for relative in spec['required_files']:
        p = project_path(root, relative)
        add('PASS' if p.is_file() else 'FAIL', '资源 ' + relative,
            '存在' if p.is_file() else '缺失', '重新获取完整检查包或项目文件。')

    pins = {}
    if cfg.get('requirements_file'):
        try:
            pins = pinned_requirements(project_path(root, cfg['requirements_file']))
            for package, expected in pins.items():
                try:
                    actual = importlib.metadata.version(package)
                except importlib.metadata.PackageNotFoundError:
                    actual = None
                add('PASS' if version_satisfies(actual, expected) else 'FAIL', '依赖 ' + package,
                    '已安装 %s；要求 %s' % (actual or '无', expected),
                    '按该 profile 的独立指南安装；inference 检查基线不是完整安装清单。')
        except (OSError, ValueError) as exc:
            add('FAIL', '依赖清单', str(exc), '恢复项目依赖清单，不通过跳过检查隐藏错误。')
    rc, out, err = run_local([sys.executable, '-c', PROBE,
                              json.dumps(cfg['imports']), profile], root)
    lines = [line for line in out.splitlines() if line.startswith('DOCTOR_PROBE=')]
    if rc != 0 or not lines:
        add('FAIL', '模块导入', (err or out or '导入探测失败')[-1200:], cfg['python_help'])
    else:
        for item in json.loads(lines[-1].split('=', 1)[1]):
            ok = item['ok']
            expected = pins.get(item['module'])
            if expected and not version_satisfies(item.get('version'), expected):
                ok = False
            detail = item.get('error') or item.get('prefix') or str(item.get('version') or '导入成功')
            add('PASS' if ok else 'FAIL', '导入 ' + item['module'], detail,
                cfg['python_help'])
    dependency_cmd = [sys.executable, '-m', 'pip', 'check']
    dependency_label = 'pip check'
    if importlib.util.find_spec('pip') is None and shutil.which('uv'):
        dependency_cmd = ['uv', 'pip', 'check', '--python', sys.executable]
        dependency_label = 'uv pip check（当前解释器）'
    rc, out, err = run_local(dependency_cmd, root, timeout=30)
    add('PASS' if rc == 0 else 'FAIL', dependency_label,
        (out or err).strip()[-2000:] or '无输出',
        '可用 python -m pip check 或 uv pip check --python 指定当前解释器；它只检查已安装包。')

    if profile == 'inference':
        if shutil.which('nvidia-smi'):
            rc, out, err = run_local(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used',
                                     '--format=csv,noheader'], root, timeout=10)
            add('PASS' if rc == 0 and out.strip() else 'FAIL', 'GPU / 驱动可见性',
                (out or err).strip()[:1200], '确认驱动和容器 GPU 映射；本检查不初始化 JAX 后端或运行模型。')
        if inference_root:
            repo = Path(inference_root).expanduser().resolve()
            for relative in ('pyproject.toml', 'uv.lock', 'scripts/serve_policy.py', 'src/openpi/training/config.py'):
                add('PASS' if (repo / relative).is_file() else 'FAIL', '推理源码 ' + relative,
                    str(repo / relative), '取得包含项目适配的完整 openpi 源码及对应锁文件。')
            if policy_config:
                config = repo / 'src/openpi/training/config.py'
                text = config.read_text() if config.is_file() else ''
                found = re.search(r'name\s*=\s*[\"\x27]' + re.escape(policy_config) + r'[\"\x27]', text) is not None
                add('WARN' if found else 'FAIL', '策略配置名', policy_config,
                    '这里只静态查找声明；还需核对配置可加载、数据适配与归一化。')
        else:
            add('SKIP', '推理源码与配置', '未提供 --inference-root，尚未检查项目适配')
        if checkpoint:
            ckpt = Path(checkpoint).expanduser().resolve()
            params = ckpt / 'params'
            weights = (ckpt / 'model.safetensors').is_file() or (params.is_dir() and any(params.iterdir()))
            stats = list((ckpt / 'assets').glob('**/norm_stats.json')) if (ckpt / 'assets').is_dir() else []
            add('PASS' if weights else 'FAIL', 'checkpoint 权重结构', str(ckpt), '需要完整 params 目录或 model.safetensors。')
            add('PASS' if stats else 'FAIL', 'checkpoint 归一化文件', str(len(stats)) + ' 个 norm_stats.json',
                '取得同一训练产物的 assets；这里只检查存在，不证明内容正确。')
        else:
            add('SKIP', 'checkpoint', '未提供 --checkpoint；不能据环境通过认定模型可启动')
        add('SKIP', '模型推理与服务连接', '未初始化 GPU 后端、加载模型、连接端口或发推理请求')

    if profile == 'mujoco':
        sim = Path(simulation_root).expanduser().resolve() if simulation_root else root / 'x2_live'
        if simulation_root or sim.is_dir():
            for relative in ('tube/x2_scene.py', 'X2_URDF-v1.3.0/x2_ultra.xml', 'omnihand/test.xml',
                             'X2_URDF-v1.3.0/meshes', 'omnihand/meshes',
                             'openpi_client_src/openpi_client/websocket_client_policy.py'):
                add('PASS' if (sim / relative).exists() else 'FAIL', '仿真资源 ' + relative,
                    str(sim / relative), '取得完整 x2_live 包；Git 中可能没有被忽略的 mesh 文件。')
        else:
            add('SKIP', 'X2 仿真资源', '未提供 --simulation-root 且当前包不含 x2_live')
        if system == 'Darwin':
            launcher = Path(sys.executable).parent / 'mjpython'
            add('PASS' if launcher.is_file() else 'FAIL', 'macOS mjpython', str(launcher),
                '安装当前虚拟环境的 mujoco；被动 viewer 由 mjpython 启动。')
        add('SKIP', '场景编译与渲染', '另运行 scripts/check_mujoco_scene.py；--headless 仍需要离屏渲染后端')

    if profile == 'ros':
        for key, expected in [('ROS_DISTRO', cfg['ros_distro']), ('ROS_VERSION', cfg['ros_version'])]:
            actual = os.environ.get(key, '')
            add('PASS' if actual == expected else 'FAIL', key, actual or '未设置', cfg['python_help'])
        for key in ('AMENT_PREFIX_PATH', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'COLCON_PREFIX_PATH'):
            value = os.environ.get(key, '')
            paths = [p for p in value.split(os.pathsep) if p]
            bad = [p for p in paths if not Path(p).exists()]
            required = key == 'AMENT_PREFIX_PATH'
            status = 'FAIL' if required and (not paths or bad) else ('WARN' if bad else ('PASS' if paths else 'SKIP'))
            add(status, key, '条目 %d；失效 %d%s' % (len(paths), len(bad), ': ' + ', '.join(bad)[:600] if bad else ''),
                '在新 shell 加载 ROS 与正确 SDK overlay；检查环境变量中的失效目录。')
        domain = os.environ.get('ROS_DOMAIN_ID', '')
        valid = not domain or (domain.isdigit() and 0 <= int(domain) <= 232)
        add('WARN' if valid else 'FAIL', 'ROS_DOMAIN_ID', domain or '未设置，使用默认值',
            '需与目标系统配置匹配；本地检查不推断网络连通，也不会自动改成 0 或 88。')
        add('WARN', 'RMW_IMPLEMENTATION', os.environ.get('RMW_IMPLEMENTATION') or '使用安装环境默认值',
            '仅记录选择，未启动 DDS 或验证中间件通信。')
    else:
        add('SKIP', 'ROS 开发环境', profile + ' profile 不要求 ROS，不导入 rclpy 或 SDK')

    lock = root / 'config/source-lock.json'
    kit = root / 'ENVIRONMENT_KIT.json'
    if lock.is_file() or explicit_project or not kit.is_file():
        report['project_resources_checked'] = True
        try:
            entries = json.loads(lock.read_text())['files']
            if not entries:
                raise ValueError('源码锁定清单为空')
            for entry in entries:
                p = project_path(root, entry['path'])
                actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
                add('PASS' if actual == entry['sha256'] else 'FAIL', '项目文件 ' + entry['path'],
                    '哈希一致' if actual == entry['sha256'] else '缺失或哈希变化',
                    '核对完整项目及其版本；不要为通过检查直接改锁文件。')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            add('FAIL', '项目资源清单', str(exc), '获取完整项目及 config/source-lock.json。')
    else:
        add('SKIP', '完整项目资源', '当前为独立环境检查包，未检查控制代码、模型或标定文件',
            '有完整项目后使用 --project-root 指向它，再运行离线测试。')
    add('SKIP', '机器人网络与控制', '本次没有创建 ROS 节点、网络探测、模式切换或运动')
    return finish(report)


def finish(report):
    report['counts'] = {s: sum(row['status'] == s for row in report['checks'])
                        for s in ('PASS', 'FAIL', 'WARN', 'SKIP')}
    report['ok'] = report['counts']['FAIL'] == 0
    return report


def doctor(root, profile='offline', json_output=False, explicit_project=False, **options):
    report = collect(root, profile, explicit_project, **options)
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('环境检查 profile=%s；项目=%s；Python=%s' % (profile, report['root'], report['python']))
        for row in report['checks']:
            print('%-4s  %s：%s' % (row['status'], row['check'], row['detail']))
            if row['status'] in ('FAIL', 'WARN', 'SKIP') and row['remedy']:
                print('      ' + row['remedy'])
        print('结果：' + ('环境检查通过' if report['ok'] else '环境检查未通过') + '；' + str(report['counts']))
        print('仅覆盖所选用途与已声明资源；不代表模型／标定齐备或真机运动获准。')
    return 0 if report['ok'] else 1
