# GPU 服务器上的模型推理环境

使用 Linux、Python 3.11 和匹配任务的 openpi 源码／锁文件。先完成[公共准备](ENVIRONMENTS.md)，在自己的工作区安装，不向共享服务的现有虚拟环境补包。本指南是安装和运行步骤，当前尚无可供公开下载、完整验收的 X2 模型发布包。

## 1. 核对 GPU 与外部资产

在分配给自己的 GPU 主机或容器执行：

```sh
uname -m
nvidia-smi
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv
```

命令失败或 GPU 未映射时先由管理员配置。CUDA 驱动、容器 GPU 映射及显存容量取决于锁文件使用的后端和模型，不提供任意驱动一键覆盖命令。`nvidia-smi` 中 CUDA 版本不等于当前 Python 已装 CUDA runtime。安装 Python 包不能替代宿主机驱动。

必须先拿到：授权源码仓库／归档及提交号、pyproject.toml、uv.lock、X2 数据适配代码、策略配置名、checkpoint、同版本归一化统计、各资产校验清单，以及批准使用的 GPU 和端口。

[上游 openpi](https://github.com/Physical-Intelligence/openpi) 提供通用源码和基础模型，但不是本项目 X2 微调产物。不要把上游 main 当作这个项目的固定版本。提供方交付 Git 仓库时，在新目录使用：

```sh
export X2_OPENPI_URL=REPLACE_WITH_AUTHORIZED_REPOSITORY_URL
export X2_OPENPI_REF=REPLACE_WITH_RELEASE_COMMIT
export OPENPI_ROOT="$HOME/projects/openpi-x2"
git clone --recurse-submodules "$X2_OPENPI_URL" "$OPENPI_ROOT"
cd "$OPENPI_ROOT"
git checkout "$X2_OPENPI_REF"
git submodule update --init --recursive
git rev-parse HEAD
test -f pyproject.toml && test -f uv.lock
```

不要执行仍含 REPLACE_ 的命令。若获取的是归档，校验提供方 SHA256、解压到新目录并设置 OPENPI_ROOT，不需要上述 clone。下载授权地址或权重缺失时，请先取得资产，不把安装成功称为 X2 可运行。

## 2. 在新环境安装

先按总入口安装 uv，并确保当前没有其他环境激活：

```sh
cd "$OPENPI_ROOT"
uv python install 3.11
export UV_PROJECT_ENVIRONMENT="$OPENPI_ROOT/.venv-inference"
uv venv --python 3.11 "$UV_PROJECT_ENVIRONMENT"
GIT_LFS_SKIP_SMUDGE=1 uv sync --frozen --no-dev --python 3.11
source "$UV_PROJECT_ENVIRONMENT/bin/activate"
python --version
uv pip check --python "$UV_PROJECT_ENVIRONMENT/bin/python"
python -c 'import openpi, openpi_client, jax; print(openpi.__file__); print(jax.__version__)'
```

遵循所交付版本的 extras／editable 安装要求；上面以包含项目安装声明的锁定工作区为前提。sync 报 Python、系统或锁文件不兼容时停止并核对发布版本，不删锁文件自行重新解析依赖。[openpi 安装说明](https://github.com/Physical-Intelligence/openpi#installation)使用 uv 和子模块；不同版本的具体附加安装要求以其 README 为准。

本仓库 `requirements-inference-check.txt` 是历史核心版本检查基线（NumPy 1.26.4、JAX/JAXlib 0.5.3 等），**不能用 pip install -r 此文件建立完整环境**。若提供方交付新版本，应另建并审查新的环境基线，不能仅改版本号使检查通过。

## 3. 配置和静态检查

在服务器终端设置真实路径和配置名；本地缓存目录仅按所用源码支持的变量设置：

```sh
export X2_PROJECT_ROOT=/path/to/x2
export POLICY_CONFIG=REPLACE_WITH_RELEASED_CONFIG_NAME
export CHECKPOINT_ROOT=/path/to/complete/checkpoint
export OPENPI_DATA_HOME="$HOME/.cache/openpi"
export XLA_PYTHON_CLIENT_PREALLOCATE=false
python "$X2_PROJECT_ROOT/scripts/project.py" doctor --profile inference \
  --inference-root "$OPENPI_ROOT" --policy-config "$POLICY_CONFIG" \
  --checkpoint "$CHECKPOINT_ROOT"
```

检查器不加载模型；源码配置为静态查找，权重／统计仅验证结构。配置找不到、params/model.safetensors 缺失、assets 下缺 norm_stats.json 时需补齐模型发布物。核心包导入成功不代表 pip 依赖无冲突。

按实际 GPU 排期，在自己的环境进一步验证 JAX GPU 后端（这一步会初始化 GPU）：

```sh
python - <<'PY'
import jax
print(jax.devices())
assert any(device.platform == 'gpu' for device in jax.devices()), 'JAX 未发现 GPU'
PY
```

## 4. 启动模型服务

源码提供 `scripts/serve_policy.py` 且参数与[上游入口](https://github.com/Physical-Intelligence/openpi/blob/main/scripts/serve_policy.py)匹配时，在已安排的 GPU、已确认空闲的端口启动。以下 `18001` 仅为示例，需按管理员分配修改：

```sh
cd "$OPENPI_ROOT"
export POLICY_PORT=18001
python scripts/serve_policy.py --help
mkdir -p "$X2_PROJECT_ROOT/runs"
X2_INFER_RUN=$(mktemp -d "$X2_PROJECT_ROOT/runs/inference-XXXXXX")
git rev-parse HEAD > "$X2_INFER_RUN/openpi-commit.txt"
uv pip freeze --python "$UV_PROJECT_ENVIRONMENT/bin/python" > "$X2_INFER_RUN/packages.txt"
set -o pipefail
python -u scripts/serve_policy.py --port "$POLICY_PORT" policy:checkpoint \
  --policy.config "$POLICY_CONFIG" --policy.dir "$CHECKPOINT_ROOT" \
  2>&1 | tee "$X2_INFER_RUN/server.log"
```

这个命令实际加载模型并占用 GPU。成功需看到权重加载及监听完成；不能仅据进程存在判断成功。Ctrl+C 停止本终端的推理服务；不要用宽泛 pkill 停止别人服务。上游入口监听 0.0.0.0，应运行在已管理的私网／容器网络，不能直接暴露到公网。

另一个已激活相同环境的服务器终端，检查端口（只证明 TCP 可连接，不证明推理正确）：

```sh
export POLICY_PORT=18001
python - <<'PY'
import os, socket
with socket.create_connection(('127.0.0.1', int(os.environ['POLICY_PORT'])), timeout=5):
    print('TCP connected; inference output not yet verified')
PY
```

之后按[仿真指南](ENV_MUJOCO.md)做单回合请求，检查动作维度、数值、任务结果；图片顺序、状态单位、动作关节顺序必须来自同一模型发布契约，不猜测。

## 每次使用与排错

新终端设置 OPENPI_ROOT 等变量，激活 `.venv-inference`，运行 doctor；资产或源码变化后重新验收。

| 现象 | 处理 |
|---|---|
| nvidia-smi 不存在／无设备 | 管理员检查驱动和容器 GPU 映射 |
| JAX 只有 CPU | 查锁文件 GPU extras、驱动兼容及动态库，不随意 pip upgrade |
| 下载长时间无日志 | 使用 python -u、检查日志／缓存和网络，不先认定服务正常 |
| CUDA OOM | 检查并发占用和模型显存要求，协调资源，不结束他人任务 |
| 配置／权重缺失 | 向模型提供方取得匹配完整发布物 |
| doctor 版本不匹配 | 当前环境不符合已声明基线，记录差异并单独验收 |

本页未宣称已在空 GPU 主机完成安装或已提供 X2 成功抓取模型。验收记录应包含源码提交、锁文件和模型资产哈希、依赖报告、模型加载日志及请求结果。
