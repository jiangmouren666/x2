"""Offline witness: the shared stall helper can rewrite a held hand target.

Does not import controllers, ROS or robot dependencies. Extracts only the
reviewed _check_stall function and its numeric constants, after checking hashes.
This characterizes a code path; it does not simulate hardware or prove safety.
"""
import ast
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace as NS

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'robot_executor.py': 'f0d8acdbbd50979393377fc604464f141f86f2ad34984697ef733b07a6c571a8',
    'box_executor.py': '5bffad7bbf120f5d96a4326fec88750953ac0420cba1ec0225a9c3b1ffae4cd3',
    'executor_candidate.py': '6f3bb55431d72efec25f183e3908a6f34be643f21e7d48124540e23045ad85fd',
}


def check(name, expected):
    path = ROOT / 'tests/fixtures/controllers' / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    tree = ast.parse(path.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == '_check_stall')
    constants = next(n for n in tree.body if isinstance(n, ast.Assign)
                     and isinstance(n.targets[0], ast.Tuple)
                     and [x.id for x in n.targets[0].elts]
                     == ['STALL_ERR', 'STALL_STILL', 'STALL_S', 'STALL_PRELOAD'])
    clock = NS(now=10.0)
    env = {'np': np, 'time': NS(monotonic=lambda: clock.now)}
    exec(compile(ast.Module(body=[constants, fn], type_ignores=[]),
                 str(path), 'exec'), env)
    cases = []
    for preloaded in [False, True]:
        # Right index PIP (local index 4), initially held at 0.2 rad. Later
        # synthetic feedback is 0.1 rad and remains there for > STALL_S.
        ctl = NS(h=slice(10, 20), side='right', cmd_hand=np.full(20, .2),
                 tgt_hand=np.full(10, .2), start_hand10=np.full(10, .2),
                 preloaded=np.zeros(10, dtype=bool), stalled={},
                 stall_since=np.full(10, np.nan), stall_ref=np.zeros(10),
                 hand_lo=np.full(10, -1.), hand_hi=np.full(10, 1.),
                 stall_preload=env['STALL_PRELOAD'], lock=threading.Lock())
        ctl.preloaded[4] = preloaded
        measured = np.full(10, .2)
        measured[4] = .1
        clock.now = 10.0
        env['_check_stall'](ctl, measured, ctl.tgt_hand.copy())
        clock.now += env['STALL_S'] + .1
        env['_check_stall'](ctl, measured, ctl.tgt_hand.copy())
        after = float(ctl.cmd_hand[14])
        expected_after = .2 if preloaded else .1 + env['STALL_PRELOAD']
        assert np.isclose(after, expected_after)
        assert np.isclose(ctl.tgt_hand[4], expected_after)
        assert np.all(ctl.cmd_hand[:10] == .2)
        cases.append(dict(preloaded_at_start=preloaded, before_rad=.2,
                          feedback_rad=.1, after_rad=after,
                          changed=not np.isclose(after, .2)))
    return dict(file=name, sha256=expected, cases=cases)


if __name__ == '__main__':
    result = dict(scope='Isolated helper witness, not complete execution or hardware validation',
                  robot_access=False, publisher_created=False,
                  results=[check(name, sha) for name, sha in SOURCES.items()])
    print('HAND_HOLD_AUDIT=' + json.dumps(result, ensure_ascii=False))
