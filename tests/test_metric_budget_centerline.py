import unittest

import numpy as np

from terrain_pipeline.channel_geometry import repair_budget_centerline
from terrain_pipeline.channel_geometry import controlling_upstream_nodes


class BudgetCenterlineTests(unittest.TestCase):
    def fixture(self, count=5, hotspot=2, budget=4., worsen_profile=False):
        points = np.column_stack((np.arange(count, dtype=float), np.zeros(count)))
        receiver = np.r_[np.arange(1, count), -1]

        def evaluate(candidate, profile, focus):
            required = budget + .3 - .1 * candidate[hotspot, 1] + profile
            return dict(maxima=[required, required, required],
                        counts=[int(required > budget)] * 3,
                        hotspots=[dict(category="physical_half_bottom", node_index=hotspot,
                                       maximum_required_cut_m=required)])

        def validate(candidate):
            if not np.array_equal(candidate[[0, -1]], points[[0, -1]]):
                raise ValueError("anchor moved")

        certify = lambda candidate: 10. if worsen_profile else 0.
        return points, receiver, evaluate, validate, certify

    def repair(self, fixture, budget=4.):
        points, receiver, evaluate, validate, certify = fixture
        return repair_budget_centerline(points, receiver, 0., evaluate=evaluate,
                                        validate=validate, certify=certify, max_cut_m=budget,
                                        max_trials=40, max_rounds=2)

    def test_hotspot_beyond_initial_smoothing_window_moves_and_anchors_stay_fixed(self):
        fixture = self.fixture(count=500, hotspot=450)
        repaired, _, policy = self.repair(fixture)
        self.assertGreater(repaired[450, 1], 0.)
        np.testing.assert_array_equal(repaired[[0, -1]], fixture[0][[0, -1]])
        self.assertEqual(policy["status"], "necessary_bounds_clear")

    def test_anchor_hotspot_has_no_movable_candidate(self):
        fixture = self.fixture(hotspot=0)
        repaired, _, policy = self.repair(fixture)
        np.testing.assert_array_equal(repaired, fixture[0])
        self.assertEqual(policy["attempted_trials"], 0)

    def test_local_improvement_is_refused_when_complete_profile_worsens(self):
        fixture = self.fixture(worsen_profile=True)
        repaired, _, policy = self.repair(fixture)
        np.testing.assert_array_equal(repaired, fixture[0])
        self.assertGreater(policy["complete_profile_and_budget_certificates"], 0)
        self.assertLessEqual(policy["attempted_trials"], 40)
        self.assertEqual(policy["accepted_moves"], [])

    def test_nondefault_budget_scores_excess_before_unchanged_counts(self):
        fixture = self.fixture(budget=2.)
        points, receiver, evaluate, validate, certify = fixture
        repaired, _, policy = repair_budget_centerline(
            points, receiver, 0., evaluate=evaluate, validate=validate,
            certify=certify, max_cut_m=2., max_trials=2)
        self.assertGreater(repaired[2, 1], 0.)
        self.assertEqual(policy["maximum_cut_m"], 2.)
        self.assertEqual(policy["initial_counts"], policy["final_counts"])
        self.assertLess(policy["final_maxima"][0], policy["initial_maxima"][0])

    def test_controlling_upstream_stage_recomputes_profile_before_budget_search(self):
        points = np.column_stack((np.arange(5, dtype=float), np.zeros(5)))
        receiver = np.array([1, 2, 3, 4, -1])
        def evaluate(candidate, profile, focus):
            required = 4.3 - profile
            return dict(maxima=[required] * 3, counts=[int(required > 4.)] * 3,
                        hotspots=[dict(category="physical_half_bottom", node_index=3,
                                       maximum_required_cut_m=required)])
        repaired, _, policy = repair_budget_centerline(
            points, receiver, 0., evaluate=evaluate, validate=lambda candidate: None,
            certify=lambda candidate: max(0., candidate[1, 1]), max_cut_m=4., max_trials=0,
            causal_nodes=lambda candidate, profile, evaluation: [0, 1],
            source_height=lambda point: point[1])
        self.assertEqual(policy["status"], "necessary_bounds_clear")
        np.testing.assert_array_equal(repaired[[0, -1]], points[[0, -1]])
        self.assertGreater(repaired[1, 1], 0.)

    def test_controlling_mid_edge_knot_exposes_both_endpoints(self):
        points = np.column_stack((np.arange(4, dtype=float), np.zeros(4)))
        receiver = np.array([1, 2, 3, -1])
        profile = (np.array([0, 3, 5, 7]),
                   np.array([0., .5, 1., 0., 1., 0., 1.]),
                   np.array([10., 2., 10., 10., 10., 10., 10.]), np.zeros(7))
        nodes = controlling_upstream_nodes(points, receiver, np.zeros(4), profile, [2], .01)
        self.assertEqual(nodes, [0, 1])


if __name__ == "__main__":
    unittest.main()
