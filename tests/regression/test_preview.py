import copy
import json
import math
from pathlib import Path
import unittest
from x2.planning.right_arm_preview import build_preview


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/synthetic-preflight.json').read_text())

    def test_only_right_elbow_changes_and_preserves_commands(self):
        original = copy.deepcopy(self.snapshot)
        p = build_preview(self.snapshot, 1, .5)
        first, last = p['frames'][0]['arm_targets_rad'], p['frames'][-1]['arm_targets_rad']
        self.assertEqual(self.snapshot, original)
        self.assertAlmostEqual(math.degrees(last[10]-first[10]), 1)
        for row in p['frames']:
            self.assertEqual(row['arm_targets_rad'][:10], first[:10])
            self.assertEqual(row['arm_targets_rad'][11:], first[11:])
        commands = [j['position'] for s in ('left', 'right')
                    for j in original['raw']['hand_cmd'][s+'_hands']]
        self.assertEqual(p['unchanged_hand_targets_rad'], commands)
        self.assertFalse(p['executable'])

    def test_both_directions_respect_rate(self):
        for delta in (-1, 1):
            p = build_preview(self.snapshot, delta, .5)
            for a, b in zip(p['frames'], p['frames'][1:]):
                rate = abs(math.degrees(b['arm_targets_rad'][10]-a['arm_targets_rad'][10]))/(b['time_s']-a['time_s'])
                self.assertLessEqual(rate, .5 + 1e-9)

    def test_fault_in_either_hand_refused(self):
        for side in ('left', 'right'):
            s = copy.deepcopy(self.snapshot)
            s['raw']['hand'][side+'_hands'][1]['faultcode'] = 4
            with self.assertRaises(ValueError):
                build_preview(s, 1, .5)

    def test_malformed_inputs_refused(self):
        s = copy.deepcopy(self.snapshot)
        s['raw']['arm_cmd']['joints'][0]['position'] = float('nan')
        with self.assertRaises(ValueError): build_preview(s, 1, .5)
        s = copy.deepcopy(self.snapshot)
        s['raw']['arm_cmd']['joints'][0]['name'] = 'wrong_joint'
        with self.assertRaises(ValueError): build_preview(s, 1, .5)
        for delta, rate in [(float('nan'), .5), (2, .5), (0, .5), (1, 0), (1, 1)]:
            with self.assertRaises(ValueError): build_preview(self.snapshot, delta, rate)


if __name__ == '__main__':
    unittest.main()
