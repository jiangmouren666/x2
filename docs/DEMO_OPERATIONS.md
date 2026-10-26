# 终端操作工作流

在仓库根目录操作。这个入口包装现有功能，每步打印实际命令和结果，失败即停；不启动 ROS、连接机器人或发布动作。源码统一维护在 `scripts/demo_workflow.py`。离线基线与安装步骤见 [README](../README.md)。

## 1. 离线检查与目标预览

激活按 README 安装的 Python 3.12 环境：

```sh
source .venv/bin/activate
python scripts/demo_workflow.py offline
```

执行顺序：环境与依赖 → 源码和资产完整性 → 单元／回归检查 → 已知缺陷复现 → 合成样本右肘预览 → 摘要。

预期生成 189 帧、3.76 秒、右肘目标变化 1°；`executable=false`。输出目录在终端打印，包含 `check.json`、`preview.json`、两份日志和 `workflow.json`。这是离线数值预览，不是实时播放或抓取成功证明。`REPRODUCED_KNOWN_DEFECT` 是成功复现已有缺陷，不是控制器验收通过。

默认使用脚本所在仓库；可用 `offline --project-root /path/to/checkout` 指定另一份公开工程，但解释器必须已安装对应 checkout 的包，否则检查会失败。

## 2. 从已有采集文件提取图片

此步骤只需要 Python 标准库，不需要相机连接。把自己持有的诊断文本路径传入：

```sh
python3 scripts/demo_workflow.py images --capture /path/to/images.txt
```

输入文本必须恰好有一行 `HAND_REVIEW=`，等号后是 JSON，结构如下（占位符需替换成实际 JPEG 的 Base64）：

```text
HAND_REVIEW={"provenance":{"kind":"recorded_capture","recorded_at":"实际采集时间及时区"},"jpeg_base64":{"head":"头部JPEG的Base64","wrist":"腕部JPEG的Base64"}}
```

输出 `head.jpg`、`wrist.jpg` 和报告，终端打印路径，使用本机图片查看器打开即可。报告记录输入文件 SHA256 和提供的来源说明；未提供采集时间时不会推断时间。缺少任一路图片则返回失败，已经提取的文件保留。

此工具是提取器，只检查 Base64 和 JPEG 文件头，不进行完整图像质量验证，也不保证两幅图同步。仓库不附带现场图片或采集记录，不把历史图片显示为实时画面。内部验证曾用历史 JPEG 重新封装输入，输出与原图逐一哈希相同；这不是新相机采集验证。

## 3. MuJoCo 场景检查

按 [仿真环境说明](ENV_MUJOCO.md) 建立独立环境，获取有权使用的完整场景资源。公开仓库不包含厂商网格、完整客户端包或模型权重。

```sh
source .venv-sim/bin/activate
export X2_SIM_ROOT=/path/to/your/x2_live
python scripts/demo_workflow.py scene --simulation-root "$X2_SIM_ROOT"
```

执行顺序：仿真依赖和资产检查 → 场景编译 → 十步物理 → head/wrist 两路 224×224 RGB 渲染检查。输出包含环境日志、渲染检查日志和报告；目前不保存渲染图、视频或训练数据，不连接推理服务。

本机 MuJoCo 3.2.3 实测完成上述步骤；其他机器仍需各自运行验收。遇到 `CGLError: invalid CoreGraphics connection`，检查 macOS 桌面会话和图形访问权限；Linux 无显示器环境需配置 EGL 或 OSMesa。不能以依赖检查成功替代渲染成功。场景可渲染不代表模型推理可用或训练相机约定一致。

## 输出、中断与定位失败

三个入口都创建新的输出目录，不覆盖旧结果。自定义输出根目录的全局参数放在子命令之前：

```sh
python scripts/demo_workflow.py --output-root /path/to/results offline
```

`workflow.json` 记录状态、UTC 起止时间、解释器和工作流源码 SHA256；离线 `check.json` 另外记录 Git 版本、工作区修改、依赖和资产哈希。图片报告记录输入哈希；仿真日志记录场景源码哈希。

| 状态 | 退出码 | 排查方式 |
|---|---|---|
| PASS | 0 | 所选工作流完成，仍需查看其适用范围 |
| FAIL | 1 | 查看 error 和最后一步日志，修复后重新运行 |
| INTERRUPTED | 130 | 操作者按 Ctrl+C 中断，保留已有输出 |

子步骤尚无统一总时限，需要有人值守；强制结束、断电等情况下可能没有完整报告。不要把不完整输出当成功。报告可能含本机路径或用户提供的来源信息，`runs/` 已被 Git 忽略，分享前另行审查。

## 当前未包含的功能

实时图片采集、连续同步数采、episode 录制、数据集转换、策略回合和真机控制没有包含在这个公开工作流中。后续应在各功能具有明确输入、输出和独立验收后再增加入口。控制器测试片段不能部署为完整机器人控制程序。
