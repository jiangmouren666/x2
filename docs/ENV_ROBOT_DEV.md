# ROS / AimDK 开发环境：Ubuntu 22.04

在自己的 Ubuntu 22.04 开发电脑／虚拟机安装，**不要把下面的系统安装命令在机器人板卡上执行**。沿用 SoC1 执行控制程序的部署架构；开发电脑负责开发和检查。Apple Silicon 虚拟机通常为 arm64，原生 SDK 必须匹配架构。

先完成[公共准备](ENVIRONMENTS.md)。ROS 使用系统 Python 3.10，不激活离线或仿真环境。以下采用 Bash，依据 [ROS Humble 官方安装说明](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html)及其[软件源配置源码](https://github.com/ros2/ros2_documentation/blob/humble/source/Installation/_Apt-Repositories.rst)。

## 1. 系统、软件源与 ROS

```sh
. /etc/os-release
printf '%s %s\n' "$ID" "$VERSION_ID"
test "$ID" = ubuntu && test "$VERSION_ID" = 22.04
uname -m
/usr/bin/python3 --version
```

必须为 Ubuntu 22.04 / Python 3.10，否则停止，不套用此流程。新安装 Ubuntu 应先更新系统包；ROS 官方特别要求早期 Jammy 的 systemd/udev 更新，下面的 upgrade 应在自己的开发系统上执行并查看变更：

```sh
sudo apt update
sudo apt upgrade
sudo apt install -y locales software-properties-common curl ca-certificates
sudo locale-gen en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
sudo add-apt-repository -y universe
```

配置官方 ros2-apt-source 包（需要 GitHub 网络；下载失败即停止）：

```sh
X2_ROS_SOURCE_VERSION=$(curl --fail --silent --show-error --location \
  https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
  | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
: "${X2_ROS_SOURCE_VERSION:?无法读取软件源版本}"
X2_ROS_DEB_DIR=$(mktemp -d)
curl --fail --location --output "$X2_ROS_DEB_DIR/ros2-apt-source.deb" \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${X2_ROS_SOURCE_VERSION}/ros2-apt-source_${X2_ROS_SOURCE_VERSION}.jammy_all.deb"
sudo dpkg -i "$X2_ROS_DEB_DIR/ros2-apt-source.deb"
sudo apt update
sudo apt install -y ros-humble-ros-base ros-dev-tools \
  python3-colcon-common-extensions python3-rosdep python3-pip \
  build-essential cmake git
source /opt/ros/humble/setup.bash
ros2 --help
colcon --help
```

apt 安装的是当前 Humble 软件包，不是固件专用版本锁。记录本机包版本，不升级厂商设备的软件来迎合本机环境。

## 2. 准备 AimDK

从[厂商文档入口](https://x2-aimdk.agibot.com/)或厂商授权渠道取得匹配固件与 CPU 的包及 README。公开仓库不提供 SDK 下载权限。需要提供方确认包是否是标准 colcon 工作区、是否需要架构选择或预编译依赖；不得以通用构建成功替代厂商兼容确认。

将完整工作区解压／获取到个人新目录，设置路径并检查：

```sh
export X2_SDK_ROOT=/path/to/your/aimdk
cd "$X2_SDK_ROOT"
ls
```

**只有包的 README 确认使用标准 src/ + colcon 布局时**，执行以下通用步骤；包要求专用脚本时执行其对应版本脚本，不猜参数：

```sh
test -d "$X2_SDK_ROOT/src"
source /opt/ros/humble/setup.bash
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
  sudo rosdep init
fi
rosdep update
rosdep install --from-paths src --ignore-src --rosdistro humble -r -y
colcon build --symlink-install
source install/local_setup.bash
```

已有已编译 SDK 可直接加载 overlay。不要 pip 安装同名消息包代替其原生类型支持。

## 3. 每次使用与本地验收

新 Bash 终端中重新设置两个路径：

```sh
export X2_PROJECT_ROOT=/path/to/x2
export X2_SDK_ROOT=/path/to/your/aimdk
source /opt/ros/humble/setup.bash
source "$X2_SDK_ROOT/install/local_setup.bash"
/usr/bin/python3 -c 'import sys, rclpy, aimdk_msgs; print(sys.version); print(aimdk_msgs.__file__)'
ros2 pkg prefix aimdk_msgs
ros2 interface show aimdk_msgs/msg/UpperBodyCommandArray
/usr/bin/python3 "$X2_PROJECT_ROOT/scripts/project.py" doctor --profile ros
```

成功要求：Python 3.10、Humble、SDK 字段和原生类型支持、依赖及环境目录检查无 FAIL。doctor 不创建 ROS 节点。保存本地记录：

```sh
mkdir -p "$X2_PROJECT_ROOT/runs"
X2_ROS_RECORD=$(mktemp -d "$X2_PROJECT_ROOT/runs/ros-env-XXXXXX")
/usr/bin/python3 "$X2_PROJECT_ROOT/scripts/project.py" doctor --profile ros --json > "$X2_ROS_RECORD/doctor.json"
dpkg-query -W 'ros-humble-*' > "$X2_ROS_RECORD/ros-packages.txt"
```

## 4. 连接配置与只读检查

向现场维护者取得 SoC1 的地址、SSH 用户、主机密钥指纹；核对指纹后再接受首次连接。不在公开仓库填写实际地址和密码：

```sh
export ROBOT_HOST=REPLACE_WITH_SOC1_HOST
export ROBOT_USER=REPLACE_WITH_AUTHORIZED_USER
ssh -o ConnectTimeout=5 "${ROBOT_USER}@${ROBOT_HOST}" 'hostname; uname -m; cat /etc/os-release'
```

在机器人 SSH shell 中，使用厂商现有环境；SDK 路径由维护者提供，**不运行 apt/colcon 部署命令**：

```sh
source /opt/ros/humble/setup.bash
export X2_ROBOT_SDK_ROOT=/path/to/installed/robot/sdk
source "$X2_ROBOT_SDK_ROOT/install/local_setup.bash"
ros2 topic list -t
ros2 topic info /mc/upper_body_command --verbose
ros2 interface show aimdk_msgs/msg/HandStateArray
timeout 8s ros2 topic echo /aima/hal/joint/hand/state \
  aimdk_msgs/msg/HandStateArray --once --qos-reliability best_effort
```

最后一条订阅状态，不发送目标；先用 topic list 确认本机实际名称／类型，接口不同则查对应 SDK，不强套命令。退出码 124 表示未在 8 秒内结束，不能当作有效反馈。`ros2 topic info` 有订阅者不代表控制源已注册，也不代表命令可执行。

如果开发电脑需要直接参加 DDS，ROS_DOMAIN_ID、RMW_IMPLEMENTATION、DDS 配置文件和网卡要由设备配置确定；不要猜值，也不要通过关闭防火墙排错。仅走 SSH/SoC1 执行时，无需让开发电脑加入实时发布网络。

## 排错与完成范围

- 缺 `aimdk_msgs`：核对 SDK overlay 和实际 install 路径。
- `.so` / 类型支持加载失败：核对 Python ABI、arm64/x86_64 和厂商依赖。
- apt 找不到 Humble：核对 Jammy 和 ros2-apt-source 安装结果。
- 本地检查通过但无状态：在 SoC1 检查设备服务、话题类型、QoS 与现场 DDS 配置。

完整干净 Ubuntu + AimDK 重建尚未由本项目验收。公开库没有完整控制发布包；本页止于环境和只读反馈，不提供未经验收的运动启动命令。
