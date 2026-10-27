# 环境搭建总入口

这份指南对应本仓库的环境声明，命令使用 **Bash**。macOS 默认 zsh 用户可先输入 `bash`。按用途选一套环境，每套用新终端，不在同一虚拟环境混装。先逐块执行并确认退出码为 0，再执行下一块；不要整页粘贴后忽略中途错误。

| 用途 | 系统与 Python | 安装、配置、检查与运行 |
|---|---|---|
| 离线开发 | macOS / Linux，Python 3.12 | [离线环境](ENV_OFFLINE.md) |
| ROS / AimDK 开发 | Ubuntu 22.04，系统 Python 3.10，Humble | [机器人开发](ENV_ROBOT_DEV.md) |
| 模型推理 | Linux GPU 环境，Python 3.11，匹配的 openpi 锁文件 | [推理环境](ENV_INFERENCE.md) |
| MuJoCo | macOS / Linux，建议 Python 3.11，MuJoCo 3.2.3 | [仿真环境](ENV_MUJOCO.md) |

## 每台开发机先准备工具和源码

Ubuntu 开发电脑／自己的开发容器：

```sh
sudo apt update
sudo apt install -y git curl ca-certificates openssh-client python3 python3-venv
```

macOS 没有 Git 时，先安装 Apple 命令行工具，完成弹窗安装后再继续：

```sh
xcode-select --install
```

已有项目就进入原目录，不要重复 clone。首次获取：

```sh
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/jiangmouren666/x2.git
cd x2
export X2_PROJECT_ROOT="$PWD"
git rev-parse HEAD
```

新终端需要重新设置 `X2_PROJECT_ROOT` 为自己的仓库绝对路径。后文所有 `/path/to/...`、`REPLACE_...` 均需替换；它们不是已经存在的资源。私有路径可以保存在自己机器的 `.env.local`（已忽略），只 source 自己编写并检查过的文件；不要在其中写密码或令牌。

## 安装 Python 版本管理工具

离线、仿真和推理可用 uv 安装指定 Python；ROS 使用 Ubuntu 系统 Python，不走这一步创建 ROS 解释器。按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)，下载后检查脚本再执行：

```sh
X2_UV_INSTALLER=$(mktemp)
curl --fail --location https://astral.sh/uv/install.sh --output "$X2_UV_INSTALLER"
less "$X2_UV_INSTALLER"
sh "$X2_UV_INSTALLER"
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

退出 `less` 按 q。已安装 uv 可直接检查版本。安装器和 Python 下载需要网络，记录 `uv --version`；这里不声称系统软件、uv 或所有外部包已做完整版本锁定。Python 可按 [官方命令](https://docs.astral.sh/uv/guides/install-python/) 用 `uv python install 3.12` 或 `3.11` 安装，不替换系统 Python。

## 外部资产先拿齐

| 资产 | 提供方必须交付的内容 | 缺少时能进行到哪步 |
|---|---|---|
| AimDK | 版本、适配固件、CPU 架构、源码或预编译包、README、SHA256 | 可安装 ROS，不能验收 SDK |
| X2 仿真包 | 场景 Python、机器人／手部 XML 和完整 meshes、客户端代码、版本及 SHA256 | 可安装引擎，不能运行 X2 场景 |
| 模型发布物 | 适配源码提交、pyproject.toml、uv.lock、配置名、权重、归一化统计、输入输出约定及 SHA256 | 可检查 GPU，不能提供 X2 推理 |

SDK 向设备厂商获取；项目专用场景和模型向项目维护者获取。公开仓库不包含下载权限、私有地址或这些资产。不要用上游基础模型替代 X2 微调权重，也不要将缺文件的检查项跳过后宣称完整运行成功。

对于提供方交付的单个文件，macOS 用 `shasum -a 256 文件名`，Linux 用 `sha256sum 文件名`，与提供方通过可信渠道给出的值比较。自己计算出哈希但没有参照值，只能记录文件身份，不能证明来源。

## 如何判断完成

- 离线：统一工作流返回 0，保存检查、189 帧预览及报告。
- ROS：本地 doctor 通过，另外完成与实际设备匹配的只读接口验收。
- 仿真：环境、编译、物理和相机渲染都通过；策略运行还需独立推理服务。
- 推理：环境检查通过后，还要模型实际加载、GPU 后端、请求和输出验证。

已验证范围：离线工作流在 GitHub Ubuntu 22.04 和 macOS 14 通过；现有 Mac 环境已完成 X2 场景检查。完整 ROS／AimDK 和 X2 推理尚未完成从空机器重建验收。本次文档补全不等于替代这些验收。

各 profile 使用同一入口 `scripts/project.py doctor`，`--json` 可输出诊断报告；命令返回 1 表示有 FAIL，WARN/SKIP 要结合用途理解。输出可能含机器路径，分享前检查。运行演示参见[操作手册](DEMO_OPERATIONS.md)。
