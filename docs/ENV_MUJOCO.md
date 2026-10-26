# MuJoCo 仿真环境

使用独立 Python 3.10–3.12 环境和 MuJoCo 3.2.3：

```sh
python3.11 -m venv .venv-sim
source .venv-sim/bin/activate
python -m pip install -r requirements-mujoco.txt
python scripts/project.py doctor --profile mujoco --simulation-root "$X2_SIM_ROOT"
python scripts/check_mujoco_scene.py --simulation-root "$X2_SIM_ROOT"
python scripts/check_mujoco_scene.py --simulation-root "$X2_SIM_ROOT" --render
```

`X2_SIM_ROOT` 指向使用者自行取得的完整客户端包，需包含 tube/x2_scene.py、X2_URDF-v1.3.0、omnihand 的 XML/meshes，以及 openpi_client_src。此公开仓库不再分发这些外部资源，也不包含私有获取路径。资源缺失会明确报错。

场景检查只模拟十步，可选渲染 head/wrist 两路相机，不连接推理服务或机器人。不同场景版本有不同 build 参数，工具记录调用参数和源码哈希；通过不证明与训练相机约定一致。

Linux 离屏渲染需配置 EGL 或 OSMesa；macOS 被动交互窗口使用 mjpython。依赖导入、场景编译、相机渲染、模型推理是不同验收阶段。引擎说明见 [MuJoCo 官方文档](https://mujoco.readthedocs.io/en/3.2.3/python.html)。
