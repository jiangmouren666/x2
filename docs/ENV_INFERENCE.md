# 模型推理环境

推理环境与离线基线、MuJoCo 仿真分开。当前检查规范面向 Linux、Python 3.11，核心包版本见 `requirements-inference-check.txt`。这个文件只用于核对核心版本，不是完整模型环境的安装锁。

取得经过授权、与任务匹配的完整模型源码、其 pyproject.toml / uv.lock、策略配置和 checkpoint。按该源码自己的锁文件在个人工作区建立环境，例如：

```sh
cd "$OPENPI_ROOT"
export UV_PROJECT_ENVIRONMENT="$OPENPI_ROOT/.venv-inference"
uv venv --python 3.11 "$UV_PROJECT_ENVIRONMENT"
GIT_LFS_SKIP_SMUDGE=1 uv sync --frozen --no-dev --python 3.11
source "$UV_PROJECT_ENVIRONMENT/bin/activate"
python "$X2_PROJECT_ROOT/scripts/project.py" doctor --profile inference \
  --inference-root "$OPENPI_ROOT" \
  --policy-config "$POLICY_CONFIG" --checkpoint "$CHECKPOINT_ROOT"
```

先设置各变量为自己的真实路径／配置名。NVIDIA 驱动与容器 GPU 映射由环境管理员提供。不要向正在运行的共享服务环境直接补包；在新环境中解决依赖闭合问题后再单独验收。

doctor 不加载模型或发出推理请求。它检查 GPU 可见性、导入、依赖、源码及 checkpoint 结构；静态存在不证明模型可加载或任务匹配。必须取得与权重同版本的适配代码和归一化统计，不能用基础模型冒充微调产物。

没有 pip 时，检查器可用 `uv pip check --python 当前解释器`。启动和通信以取得的模型源码文档为准；本仓库不提供内部服务地址、账户或模型下载权限。
