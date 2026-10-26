"""Compile and optionally render the local X2 scene. No robot or inference connection."""
import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--simulation-root', type=Path, required=True, help='Full x2_live client folder')
    ap.add_argument('--render', action='store_true', help='Also check offscreen head/wrist camera rendering')
    args = ap.parse_args()
    root = args.simulation_root.expanduser().resolve()
    os.environ['X2_ROOT'] = str(root)
    sys.path.insert(0, str(root / 'tube'))
    sys.path.insert(0, str(root / 'openpi_client_src'))
    try:
        import numpy as np
        import mujoco
        import websockets.sync.client
        from openpi_client import websocket_client_policy  # Import only; do not instantiate its network client.
        import x2_scene
        if mujoco.__version__ != '3.2.3':
            raise ValueError('This scene requires mujoco==3.2.3, found ' + mujoco.__version__)
        assert 'additional_headers' in inspect.signature(websockets.sync.client.connect).parameters
        options = dict(table_h=.8)
        if 'wrist_cam' in inspect.signature(x2_scene.build).parameters:
            options['wrist_cam'] = 'pinky'
        model = mujoco.MjModel.from_xml_string(x2_scene.build(**options))
        data = mujoco.MjData(model)
        x2_scene.setup_contacts(model)
        mujoco.mj_forward(model, data)
        for _ in range(10):
            mujoco.mj_step(model, data)
        assert np.isfinite(data.qpos).all()
        result = dict(mujoco=mujoco.__version__, nq=model.nq, nu=model.nu,
                      physics_steps=10, client_import=True, network_connected=False,
                      robot_access=False, rendered=False, scene_options=options,
                      scene_sha256=hashlib.sha256(Path(x2_scene.__file__).read_bytes()).hexdigest(),
                      camera_training_compatibility_verified=False)
        if args.render:
            renderer = mujoco.Renderer(model, 224, 224)
            try:
                cameras = {}
                for name in ('head', 'wrist'):
                    renderer.update_scene(data, camera=name)
                    frame = renderer.render()
                    assert frame.shape == (224, 224, 3) and np.isfinite(frame).all()
                    assert int(frame.max()) > int(frame.min()), 'Blank camera: ' + name
                    cameras[name] = dict(shape=list(frame.shape), dtype=str(frame.dtype))
                result.update(rendered=True, cameras=cameras)
            finally:
                renderer.close()
        print('PASS ' + json.dumps(result))
        return 0
    except Exception as exc:
        print('FAIL ' + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
