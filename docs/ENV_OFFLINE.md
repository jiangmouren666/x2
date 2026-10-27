# 离线开发环境：从安装到运行

先完成[公共准备](ENVIRONMENTS.md)，在仓库根目录操作。支持 Python 3.12；不需要机器人、ROS、GPU、SDK 或模型。Ubuntu 系统 Python 不必改成 3.12。

## 安装

```sh
cd "$X2_PROJECT_ROOT"
uv python install 3.12
uv venv --python 3.12 --seed .venv
uv pip install --python .venv/bin/python --require-hashes -r requirements-offline.lock
uv pip install --python .venv/bin/python --no-deps --no-build-isolation -e .
source .venv/bin/activate
python --version
python -m pip check
```

首次创建时 `.venv` 应不存在；已有环境则直接激活，不删除或覆盖。`--seed` 提供 pip（安装工具版本未锁定）；锁文件固定 setuptools、wheel 和 NumPy，安装项目时无需额外解析依赖。已安装 Python 3.12 的用户也可按 README 用 `python3.12 -m venv .venv`，后续安装同一锁文件。

## 配置与检查

无需设置机器人地址。确认正在使用项目的解释器及源码：

```sh
python -c 'import sys, x2; print(sys.executable); print(x2.__file__)'
python scripts/project.py doctor --profile offline
python scripts/demo_workflow.py offline
```

最后一条命令同时运行完整检查和预览；成功输出 189 帧、3.76 秒、右肘目标变化 1°。它不连接机器人。完整检查的已知缺陷复现结果不表示控制器已安全验收。

## 每次使用与更新

新终端先进入仓库，再运行：

```sh
source .venv/bin/activate
python scripts/demo_workflow.py offline
```

无本地改动时更新源码和锁定依赖：

```sh
git status --short
git pull --ff-only
python -m pip install --require-hashes -r requirements-offline.lock
python -m pip install --no-deps --no-build-isolation -e .
python scripts/demo_workflow.py offline
```

有修改时先提交自己的分支，不使用强制重置。切换到另一套环境前 `deactivate` 并新开终端。不要复制 `.venv` 到另一台电脑。

## 常见问题

| 现象 | 处理 |
|---|---|
| 显示 Python 3.9 / 3.10 | 激活 `.venv`，检查 `command -v python` |
| `No module named x2` | 在当前解释器重新执行 editable 安装 |
| `installed_project` FAIL | 安装到了另一份 checkout；核对 x2.__file__ |
| NumPy 或构建工具版本不符 | 按锁文件恢复当前虚拟环境，不修改检查阈值 |
| 网络下载失败 | 检查代理／网络，不能删掉哈希校验来解决 |
| Git 署名 WARN | 不影响运行；需要提交时自行配置真实姓名和邮箱 |

Ubuntu 和 macOS 的自动检查使用同一离线工作流；uv 下载／安装过程没有被该 CI 覆盖。测试报告在 `runs/`，安装和资产获取完成后离线工作流无需网络。
