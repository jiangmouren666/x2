"""Analytic bounds, independent of scene files or physical calibration."""
import copy
import math
import unittest
from x2.planning.error_budget import budget_terms


class ErrorBudgetTests(unittest.TestCase):
    def setUp(self):
        self.budget = dict(table_height_mm=10, pelvis_translation_mm=2,
                           pelvis_rotation_deg=1, pelvis_radius_m=.5,
                           joint_error_deg=[1]*7, joint_radius_m=[.1]*7,
                           model_residual_mm=3, box_translation_mm=4, box_dimension_mm=5)

    def test_unknown_bounds_never_become_zero(self):
        self.budget['table_height_mm'] = None
        terms, missing = budget_terms(self.budget)
        self.assertIsNone(terms)
        self.assertEqual(missing, ['table_height_mm'])

    def test_analytic_arc_length_bound_and_input_unchanged(self):
        original = copy.deepcopy(self.budget)
        terms, missing = budget_terms(self.budget)
        self.assertEqual(missing, [])
        self.assertEqual(self.budget, original)
        common = 5 + math.pi/180 * 1200
        self.assertAlmostEqual(terms['table_mm'], common + 10, delta=1e-9)
        self.assertAlmostEqual(terms['wall_mm'], common + 19, delta=1e-9)

    def test_negative_nonfinite_and_wrong_shape_rejected(self):
        for key, value in [('table_height_mm', -1), ('box_translation_mm', float('nan')),
                           ('joint_error_deg', [0]*6), ('joint_radius_m', [float('inf')]*7)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                budget_terms(dict(self.budget, **{key:value}))

    def test_ten_mm_table_change_reduces_residual_by_ten_mm(self):
        first, _ = budget_terms(self.budget)
        self.budget['table_height_mm'] += 10
        second, _ = budget_terms(self.budget)
        self.assertAlmostEqual(second['table_mm'] - first['table_mm'], 10, delta=1e-9)
        self.assertAlmostEqual(second['wall_mm'] - first['wall_mm'], 10, delta=1e-9)
