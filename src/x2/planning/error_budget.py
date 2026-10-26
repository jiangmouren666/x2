"""Offline arithmetic only. Bounds are supplied assumptions, not measured accuracy.

Pure arithmetic with explicitly supplied uncertainty bounds.
No geometry, calibration, collision proof or robot authorization is implied.
"""
import numpy as np


def budget_terms(b):
    keys = ('table_height_mm', 'pelvis_translation_mm', 'pelvis_rotation_deg',
            'pelvis_radius_m', 'joint_error_deg', 'joint_radius_m',
            'model_residual_mm', 'box_translation_mm', 'box_dimension_mm')
    missing = [k for k in keys if b.get(k) is None]
    if missing:
        return None, missing
    for k in keys:
        a = np.asarray(b[k], dtype=float)
        if not np.isfinite(a).all() or (a < 0).any():
            raise ValueError('invalid nonnegative finite budget: ' + k)
        if a.shape != ((7,) if k in ('joint_error_deg', 'joint_radius_m') else ()):
            raise ValueError('wrong shape: ' + k)
    # Arc-length upper bound, conditional on supplied global lever-arm bounds.
    joint = float(np.dot(np.radians(b['joint_error_deg']), b['joint_radius_m']) * 1000)
    pelvis = float(np.radians(b['pelvis_rotation_deg']) * b['pelvis_radius_m'] * 1000)
    common = b['pelvis_translation_mm'] + pelvis + joint + b['model_residual_mm']
    return dict(joint_mm=joint, pelvis_rotation_mm=pelvis,
                table_mm=common + b['table_height_mm'],
                wall_mm=common + b['table_height_mm'] + b['box_translation_mm'] + b['box_dimension_mm']), []
