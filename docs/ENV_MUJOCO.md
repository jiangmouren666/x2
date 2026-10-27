# MuJoCo 仿真环境：安装、渲染和策略回合

先完成[公共准备](ENVIRONMENTS.md)。使用独立 Python 3.11 环境（检查器支持 3.10–3.12），MuJoCo 固定 3.2.3；不安装离线项目的 NumPy 版本锁到仿真环境。

## 1. 准备完整资源

向项目维护者取得有权使用的完整 X2 仿真包及 SHA256，解压至新的个人目录，设置：

```sh
export X2_PROJECT_ROOT=/path/to/x2
export X2_SIM_ROOT=/path/to/complete/x2_live
ls "$X2_SIM_ROOT"
```

资源至少包含：

```text
x2_live/
  tube/x2_scene.py
  X2_URDF-v1.3.0/x2_ultra.xml
  X2_URDF-v1.3.0/meshes/
  omnihand/test.xml
  omnihand/meshes/
  openpi_client_src/openpi_client/
  live_policy.py                       # 运行策略回合才需要
```

公开 Git 仓库不附带这些第三方资产。缺 meshes 不能仅靠 pip 补齐。不同客户端副本的相机约定可能不同，记录资源版本和哈希，不与模型输入约定混用。

## 2. 安装依赖

```sh
cd "$X2_PROJECT_ROOT"
uv python install 3.11
uv venv --python 3.11 --seed .venv-sim
source .venv-sim/bin/activate
python -m pip install -r requirements-mujoco.txt
python -m pip check
python -c 'import sys, mujoco; print(sys.executable); print(mujoco.__version__)'
```

已有 `.venv-sim` 则先核对再激活，不覆盖。MuJoCo wheel 包含引擎库，无需安装 mujoco-py；见 [MuJoCo 3.2.3 官方说明](https://mujoco.readthedocs.io/en/3.2.3/python.html)。其他依赖目前采用版本范围，尚不是完整跨平台锁文件；保存本机 freeze，不能宣称所有平台解析出相同版本。

Ubuntu 渲染系统库（在自己的开发机／容器安装）：

```sh
sudo apt update
sudo apt install -y libgl1 libegl1 libglfw3 libosmesa6
```

macOS 使用系统图形环境，不执行 apt。Linux GPU 环境还需管理员提供兼容驱动和 EGL；以上系统库不等于安装 NVIDIA 驱动。

## 3. 检查与不依赖模型的运行

```sh
python scripts/project.py doctor --profile mujoco --simulation-root "$X2_SIM_ROOT"
python scripts/check_mujoco_scene.py --simulation-root "$X2_SIM_ROOT"
```

第一条检查依赖和资源，第二条编译并计算十步物理。再选一种渲染方式：

```sh
# macOS 或已有显示会话的 Linux
python scripts/demo_workflow.py scene --simulation-root "$X2_SIM_ROOT"
```

```sh
# Linux 无显示器且已有 GPU/EGL 支持
MUJOCO_GL=egl python scripts/demo_workflow.py scene --simulation-root "$X2_SIM_ROOT"
```

```sh
# Linux 使用软件离屏渲染，已安装 libosmesa6
MUJOCO_GL=osmesa python scripts/demo_workflow.py scene --simulation-root "$X2_SIM_ROOT"
```

不需要三条全跑，选符合机器条件的一条。后端要在 import mujoco 前设置。成功输出 head/wrist 224×224 RGB 检查结果；日志保存到独立 runs 目录，目前不保存图像或训练数据。

保存环境版本：

```sh
mkdir -p runs
X2_SIM_RECORD=$(mktemp -d "$X2_PROJECT_ROOT/runs/sim-env-XXXXXX")
python -m pip freeze > "$X2_SIM_RECORD/packages.txt"
python scripts/project.py doctor --profile mujoco --simulation-root "$X2_SIM_ROOT" --json > "$X2_SIM_RECORD/doctor.json"
```

## 4. 可选：连接已验收的模型服务

仅在[推理环境](ENV_INFERENCE.md)已成功加载匹配模型后执行。本步骤会发推理请求并推进仿真，不驱动真实机器人。先核对所交付 live_policy.py 的 `--help` 和模型的相机／动作约定。现有客户端示例属于特定任务，不能据此声称右手杯盒任务成功。

在单独本地终端建立隧道，替换 SSH 目标和管理员分配端口。示例假定服务可从该 SSH 主机的 localhost:18001 访问；容器端口尚未映射时需先由管理员完成：

```sh
export POLICY_SSH_TARGET=REPLACE_WITH_AUTHORIZED_SSH_TARGET
export POLICY_REMOTE_PORT=18001
export POLICY_LOCAL_PORT=18002
ssh -N -o ExitOnForwardFailure=yes -o ConnectTimeout=10 \
  -L "127.0.0.1:${POLICY_LOCAL_PORT}:127.0.0.1:${POLICY_REMOTE_PORT}" "$POLICY_SSH_TARGET"
```

隧道终端保持打开。另一个终端激活仿真环境并重新设置 X2_SIM_ROOT，核对参数：

```sh
source .venv-sim/bin/activate
export X2_SIM_ROOT=/path/to/complete/x2_live
export POLICY_LOCAL_PORT=18002
python "$X2_SIM_ROOT/live_policy.py" --help
```

Linux 无显示器单回合（timeout 是 GNU coreutils 命令）：

```sh
MUJOCO_GL=egl timeout --signal=INT --kill-after=5s 180s \
  python -u "$X2_SIM_ROOT/live_policy.py" --host 127.0.0.1 \
  --port "$POLICY_LOCAL_PORT" --episodes 1 --headless
```

macOS 交互窗口：

```sh
mjpython "$X2_SIM_ROOT/live_policy.py" --host 127.0.0.1 \
  --port "$POLICY_LOCAL_PORT" --episodes 1
```

macOS 的被动 viewer 需要 mjpython。没有响应时 Ctrl+C 结束自己的仿真进程；Linux timeout 返回 124 表示超时，不能当作成功。客户端可能重试，端口连通不等于模型契约匹配。结束后在隧道终端 Ctrl+C。

## 每次使用与排错

在项目根目录激活 `.venv-sim`、设置 X2_SIM_ROOT，再运行 scene 工作流。改变场景或依赖后重新检查。

| 报错 | 处理 |
|---|---|
| 缺 mesh/XML | 获取完整资源并核对路径／哈希 |
| CoreGraphics connection | 检查 macOS 桌面会话与图形访问 |
| EGL / GL context 创建失败 | 查驱动／容器映射，或选择已配置的 OSMesa |
| additional_headers 不支持 | 按 requirements-mujoco.txt 核对 websockets |
| typing_extensions 缺失 | 确认 pip 和 Python 属于当前仿真环境 |
| 模型连接等待 | 查隧道及服务日志，保留超时结果，不重复启动服务 |

现有 Mac 环境已完成依赖、编译、十步物理和两相机渲染。Linux EGL/OSMesa、干净机器安装及完整策略回合没有在本次文档更新中实测；场景渲染通过不代表模型策略已经验收。
