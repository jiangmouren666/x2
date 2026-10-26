# ROS / AimDK 二次开发环境

项目检查面向 Ubuntu 22.04、系统 Python 3.10、ROS 2 Humble，以及匹配 CPU 架构的厂商 AimDK。离线基线的 Python 3.12 环境不能用来加载 Humble 的 Python 3.10 原生模块。

按 [ROS 官方安装文档](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html)安装 ROS、colcon、rosdep 和编译工具。SDK 从厂商授权渠道获取，按其对应版本文档构建；不要从不明来源安装同名消息包。

将 `X2_SDK_ROOT` 设置为自己构建的 SDK 工作区。在项目根目录、新 shell 中执行：

```sh
source /opt/ros/humble/setup.bash
source "$X2_SDK_ROOT/install/local_setup.bash"
python3 scripts/project.py doctor --profile ros
```

检查消息字段、原生类型支持、Python ABI 和环境目录，不创建 ROS 节点或连接机器人。ROS_DOMAIN_ID、RMW 和 DDS 配置由使用者依据自己的设备设置，仓库不包含现场默认地址。

环境通过不能代替 SDK 与实际固件的接口验收、现场测量及停止机制验证。本公开版本没有完整真机控制入口。
