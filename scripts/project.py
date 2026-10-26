#!/usr/bin/env python3
"""Local project tooling. No SSH, ROS nodes, deployment or motion calls."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/regression/test_candidate.py",
    "tests/regression/test_preview.py",
)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def locked_entries():
    return json.loads((ROOT / "config/source-lock.json").read_text())["files"]


def verify(verbose=True):
    failed = False
    for item in locked_entries():
        path = ROOT / item["path"]
        actual = digest(path) if path.is_file() else None
        ok = actual == item["sha256"]
        failed |= not ok
        if verbose or not ok:
            print(("OK  " if ok else "FAIL"), item["path"], flush=True)
    print("仅核对本地文件；不检查远端部署或机器人健康。", flush=True)
    return 1 if failed else 0


def inventory():
    for item in locked_entries():
        path = ROOT / item["path"]
        size = path.stat().st_size if path.is_file() else "MISSING"
        print(f"{size!s:>9}  {item['path']}  [{item['role']}]")
    print("其他本地证据和资料见 assets/manifest.json；公开范围见 README.md。")
    return 0


def test():
    # Never execute the generator or controller. Only these audited offline suites.
    if verify(verbose=False):
        print("快照与锁不一致，先审查差异；没有启动测试。")
        return 1
    if importlib.util.find_spec("numpy") is None:
        print("当前解释器缺 NumPy；请用 RUNBOOK 中的 Python 3.12 环境。")
        return 2
    failures = []
    for name in TESTS:
        print("离线回归:", name, flush=True)
        try:
            result = subprocess.run([sys.executable, str(ROOT / name)], cwd=ROOT,
                                    timeout=60, check=False)
            if result.returncode:
                failures.append(name)
        except subprocess.TimeoutExpired:
            failures.append(name + " (timeout)")
    if failures:
        print("未通过:", ", ".join(failures))
        return 1
    print("两套离线回归通过；没有 ROS 发布、网络访问或真机动作。")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    baseline = commands.add_parser('check', help='完整离线开发基线检查并保存报告')
    baseline.add_argument('--profile', choices=('offline',), default='offline')
    baseline.add_argument('--report', type=Path, help='新报告文件；不覆盖既有报告')
    check = commands.add_parser('doctor', help='本地环境和依赖检查，不连接机器人')
    check.add_argument('--profile', choices=('offline', 'ros', 'inference', 'mujoco'), default='offline')
    check.add_argument('--project-root', type=Path, help='检查另一个完整项目目录')
    check.add_argument('--json', action='store_true', help='向标准输出打印 JSON 报告')
    check.add_argument('--simulation-root', type=Path, help='完整 x2_live 客户端包目录')
    check.add_argument('--inference-root', type=Path, help='openpi 源码根目录')
    check.add_argument('--checkpoint', type=Path, help='checkpoint 目录；只检查文件结构')
    check.add_argument('--policy-config', help='在源码中静态核对的策略配置名')
    for name in ('verify', 'inventory', 'test'):
        commands.add_parser(name)
    args = parser.parse_args()
    try:
        if args.command == 'check':
            from offline_check import execute
            return execute(ROOT, args.report)
        if args.command == 'doctor':
            from environment_doctor import doctor
            return doctor(args.project_root or ROOT, args.profile, args.json,
                          explicit_project=args.project_root is not None,
                          simulation_root=args.simulation_root, inference_root=args.inference_root,
                          checkpoint=args.checkpoint, policy_config=args.policy_config)
        return {"verify": verify, "inventory": inventory,
                "test": test}[args.command]()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("本地检查失败:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
