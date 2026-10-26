# X2 离线开发工具

公开脱敏的开发基线 `0.1.0.dev0`：离线右臂目标预览、误差预算算术、环境诊断和控制逻辑片段回归。没有真机运行入口，也不包含现场数据、内部连接地址、原始交接文档、SDK、模型权重或设备标定。

## 安装与检查

使用 CPython 3.12。支持范围为 macOS arm64/x86_64，以及 Linux glibc 2.27+ 的 aarch64/x86_64；实际已完成的验证见检查报告，支持声明不代表所有平台都已验收。

```sh
git clone https://github.com/jiangmouren666/x2.git
cd x2
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-offline.lock
python -m pip install --no-deps --no-build-isolation -e .
python scripts/project.py check --profile offline
```

首次获取依赖需要网络；安装完成后检查可以离线执行。报告保存在忽略的 `runs/` 中，记录 Git 版本、脏状态、源码和样本哈希、平台、依赖与测试结果。报告可能含运行机器路径，公开分享前需要检查内容。

NumPy 及 editable 构建工具均锁定版本和 wheel SHA256。换电脑重新建立虚拟环境，不复制旧 .venv。只有包版本检查时，可用 `python scripts/project.py doctor --profile offline`。

## 内容与边界

| 目录 | 用途 |
|---|---|
| `src/x2/planning` | 需要继续维护的通用离线库 |
| `tests/unit` | 误差预算和完整性失败路径 |
| `tests/regression` | 预览及候选控制逻辑片段回归 |
| `tests/fixtures` | 人工生成的数值输入、经抽取的 AST 代码片段；不是现场测量 |
| `assets`、`config` | 依赖、固定样本和源码文件清单 |
| `scripts/project.py` | 统一检查入口，无机器人连接操作 |
| `.github/workflows/offline.yml` | 推送／PR 后运行相同检查；实际 CI 结果以 GitHub 为准 |

35 项单元和回归测试之外，两组审计刻意复现已知控制逻辑缺陷，结果为 `REPRODUCED_KNOWN_DEFECT`。这不表示控制器健康或已通过真机停止测试；报告中的 `hardware_approved` 始终为 false。

控制器仅保留测试所需函数和常量，供 AST 提取执行。`main` 片段只保留原来的 armed 拒绝条件与后续 init 顺序见证，不能用它判断完整控制器的其他入口。没有完整发布器、部署逻辑或可运行的硬件控制器。

预算由调用者明确提供；未知误差不会自动当成零。算术和目标预览通过，不证明标定准确、连续无碰撞、能抓住物体或可安全接触。

## 专用环境

- [ROS / AimDK 开发](docs/ENV_ROBOT_DEV.md)
- [模型推理环境](docs/ENV_INFERENCE.md)
- [MuJoCo 仿真环境](docs/ENV_MUJOCO.md)
- [公开内容与维护规则](docs/PUBLIC_SCOPE.md)

上述环境各自建立虚拟环境。最小离线基线不依赖 SDK、GPU 或外部模型资产；完整抓取流程单独验收。
