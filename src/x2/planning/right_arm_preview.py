"""Offline right-elbow target preview. Contains no ROS, networking or motor API.

Preview success does NOT authorize URS entry, physical motion or execution.
The snapshot can be historical. No real-time freshness or geometry is established.
"""
import argparse
import json
import math
from pathlib import Path

ARM_NAMES = [side + '_' + joint + '_joint' for side in ('left', 'right')
             for joint in ('shoulder_pitch', 'shoulder_roll', 'shoulder_yaw',
                           'elbow', 'wrist_yaw', 'wrist_pitch', 'wrist_roll')]
RIGHT_ELBOW = 10


def finite(values, count):
    if len(values) != count or not all(isinstance(x, (int, float)) and
                                     not isinstance(x, bool) and math.isfinite(x) for x in values):
        raise ValueError('Missing, malformed or nonfinite joint values')
    return list(values)


def build_preview(snapshot, delta_deg, max_rate_deg_s, hz=50):
    # Conservative bounds on this preview utility, NOT manufacturer safety limits.
    if not math.isfinite(delta_deg) or not 0 < abs(delta_deg) <= 1:
        raise ValueError('Preview delta must be nonzero and at most 1 degree')
    if not math.isfinite(max_rate_deg_s) or not 0 < max_rate_deg_s <= .5:
        raise ValueError('Preview rate must be in (0, 0.5] degrees/s')
    if hz != 50:
        raise ValueError('This preview uses 50 Hz')
    raw = snapshot['raw']
    source = raw['arm_cmd']['joints']
    if len(source) != 14 or len({j['name'] for j in source}) != 14:
        raise ValueError('Expected fourteen uniquely named arm commands')
    by_name = {j['name']: j['position'] for j in source}
    if set(by_name) != set(ARM_NAMES):
        raise ValueError('Unexpected arm joint mapping')
    q0 = finite([by_name[n] for n in ARM_NAMES], 14)
    hands = []
    for side in ('left', 'right'):
        state = raw['hand'][side + '_hands']
        if raw['hand'][side + '_hand_type']['value'] != 1 or len(state) != 10:
            raise ValueError('Unsupported hand type or count')
        if any(j.get('faultcode') != 0 or j.get('state') is None for j in state):
            raise ValueError('Nonzero or missing hand fault/state field')
        finite([j['position'] for j in state], 10)
        # Preserve MC command values, NOT measured positions or zero-filled defaults.
        hands += finite([j['position'] for j in raw['hand_cmd'][side + '_hands']], 10)
    # Quintic smoothstep has maximum normalized derivative 1.875.
    steps = math.ceil(1.875 * abs(delta_deg) / max_rate_deg_s * hz)
    duration = steps / hz
    frames = []
    for i in range(steps + 1):
        u = i / steps
        smooth = 10*u**3 - 15*u**4 + 6*u**5
        q = q0.copy()
        q[RIGHT_ELBOW] += math.radians(delta_deg) * smooth
        frames.append({'time_s': i / hz, 'arm_targets_rad': q})
    return dict(status='OFFLINE_PREVIEW_NOT_FOR_EXECUTION', executable=False,
                ros_publisher_implemented=False, mode_switch_implemented=False,
                changed_joint=ARM_NAMES[RIGHT_ELBOW], changed_index=RIGHT_ELBOW,
                duration_s=duration, requested_delta_deg=delta_deg,
                peak_rate_deg_s=1.875*abs(delta_deg)/duration,
                unchanged_hand_targets_rad=hands, frames=frames,
                not_validated=['Physical side mapping and joint health',
                               'Current joint limits and full swept-volume clearance',
                               'Mode-entry gain changes and hold behavior',
                               'Ordinary stop, fault stop, communication loss and safe exit',
                               'Live feedback freshness and stable grasp capability'],
                note='No automatic return path. Small target changes do not prove small physical motion.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--delta-deg', type=float, required=True)
    parser.add_argument('--max-rate-deg-s', type=float, default=.5)
    args = parser.parse_args()
    preview = build_preview(json.loads(args.snapshot.read_text()), args.delta_deg, args.max_rate_deg_s)
    # Never overwrite a previous result or the source snapshot.
    with args.output.open('x') as f:
        json.dump(preview, f, indent=2, allow_nan=False)
        f.write('\n')
    print('OFFLINE ONLY:', args.output, 'No ROS or motor operation.')


if __name__ == '__main__':
    main()
