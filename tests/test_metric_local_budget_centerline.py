import unittest
import numpy as np
from terrain_pipeline.channel_geometry import search_local_candidates, repair_local_conflicts, worst_windows


class LocalCandidateSearchTests(unittest.TestCase):
    def setUp(self):
        self.points = np.column_stack((np.arange(6, dtype=float), np.zeros(6)))
        self.receiver = np.array([1, 2, 3, 4, 5, -1])

    def search(self, gate=lambda _: None, evaluate=lambda *_: dict(status="clear"), limit=32):
        return search_local_candidates(self.points, self.receiver, [(2, 3), (3, 4)], [0, 1],
            gate=gate, evaluate=evaluate, turn_score=lambda candidate: -candidate[3, 1],
            max_candidates=limit)

    def test_target_single_has_opportunity(self):
        _, policy = self.search()
        self.assertTrue(any(record["group"] == [3] for record in policy["records"]))

    def test_gate_refusals_count_towards_component_budget(self):
        def gate(_):
            raise ValueError("geometry refusal")
        _, policy = self.search(gate=gate, limit=7)
        self.assertEqual(policy["attempted_candidates"], 7)
        self.assertIsNone(policy["selected_index"])

    def test_previously_clear_window_damage_refuses_candidate(self):
        _, policy = self.search(evaluate=lambda candidate, window: dict(
            status="clear" if window == 0 else "infeasible", extra_cut=.1))
        self.assertIsNone(policy["selected_index"])
        self.assertTrue(all(record["status"] == "infeasible" for record in policy["records"]))

    def test_unknown_is_never_accepted(self):
        _, policy = self.search(evaluate=lambda *_: dict(status="unknown"))
        self.assertIsNone(policy["selected_index"])
        self.assertEqual(policy["status"], "no_clear_candidate")

    def test_empty_windows_cannot_claim_clear_candidates(self):
        with self.assertRaisesRegex(ValueError, "failed window"):
            search_local_candidates(self.points, self.receiver, [(2, 3)], [],
                gate=lambda _: None, evaluate=lambda *_: dict(status="clear"),
                turn_score=lambda _: 0.)



class LocalConflictFlowTests(unittest.TestCase):
    def setUp(self):
        self.points = np.column_stack((np.arange(6, dtype=float), np.zeros(6)))
        self.receiver = np.array([1, 2, 3, 4, 5, -1])

    def budget(self, *_):
        bucket = dict(worst=dict(vertex_xz_m=[2., 0.], necessary_cut_m=3.9))
        return dict(counts=[0, 0, 0], bounds={kind: {category: bucket for category in
            ("physical_half_bottom", "bottom_guard_shell", "bank")} for kind in ("edge_strip", "node_cap")})

    def run_flow(self, assess):
        return repair_local_conflicts(None, self.points, self.receiver, np.ones(6),
            np.ones(6), None, np.arange(6), validate=lambda _: None, certify=lambda _: None,
            budget_evaluate=self.budget, assess=assess, max_candidates=7,
            spacing=1., max_cut=4., bottom_slope=.02, minimum_slope=1e-5)

    def test_six_duplicate_worst_centers_are_deduplicated(self):
        self.assertEqual(len(worst_windows(self.budget())), 1)

    def test_unknown_is_reported_without_path_acceptance(self):
        result, _, policy = self.run_flow(lambda *args, **kwargs: dict(status="unknown", solver_calls=1))
        np.testing.assert_array_equal(result, self.points)
        self.assertEqual(policy["status"], "unknown_needs_full_bed")
        self.assertEqual(policy["attempted_candidates"], 0)
        self.assertEqual(policy["maximum_local_solver_calls"], 2 * (7 + 1) * 6)

    def test_gate_budget_shared_after_local_conflict(self):
        _, _, policy = self.run_flow(lambda *args, **kwargs: dict(status="infeasible", extra_cut=.1,
            contributing_edges=[(2, 3)], solver_calls=2))
        self.assertEqual(policy["attempted_candidates"], 7)
        self.assertEqual(policy["status"], "local_conflicts_remain")

    def test_spatial_windows_choose_highest_cut_and_stay_bounded(self):
        budget = self.budget()
        budget["bounds"]["node_cap"]["bank"] = dict(worst=dict(
            vertex_xz_m=[10., 0.], necessary_cut_m=4.1))
        windows = worst_windows(budget)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["center_xz_m"], [10., 0.])

    def test_physical_parameters_are_forwarded_to_local_assessor(self):
        received = []
        def assess(*args, **kwargs):
            received.append(kwargs)
            return dict(status="clear", solver_calls=1)
        _, _, policy = repair_local_conflicts(None, self.points, self.receiver,
            np.ones(6), np.ones(6), None, np.arange(6), validate=lambda _: None,
            certify=lambda _: None, budget_evaluate=self.budget, assess=assess,
            spacing=.5, max_cut=3., bottom_slope=.03, minimum_slope=2e-5)
        self.assertEqual(received, [dict(spacing=.5, max_cut=3., bottom_slope=.03, minimum_slope=2e-5)])
        self.assertEqual(policy["status"], "local_windows_clear_needs_full_bed")

    def test_repaired_window_remains_in_frozen_group(self):
        calls = []
        def budget(candidate, _):
            result = self.budget()
            result["bounds"]["node_cap"]["bank"] = dict(worst=dict(
                vertex_xz_m=[600. if np.any(candidate != self.points) else 300., 0.],
                necessary_cut_m=4.))
            return result
        def assess(candidate, receiver, width, depth, profile, terrain, window, **kwargs):
            calls.append(tuple(window["center_xz_m"]))
            if window["center_xz_m"][0] == 2. and not np.any(candidate != self.points):
                return dict(status="infeasible", extra_cut=.1, contributing_edges=[(2, 3)], solver_calls=2)
            return dict(status="clear", solver_calls=1)
        _, _, policy = repair_local_conflicts(None, self.points, self.receiver,
            np.ones(6), np.ones(6), None, np.arange(6), validate=lambda _: None,
            certify=lambda _: None, budget_evaluate=budget, assess=assess, max_candidates=7,
            spacing=1., max_cut=4., bottom_slope=.02, minimum_slope=1e-5)
        self.assertEqual(policy["status"], "local_windows_clear_needs_full_bed")
        self.assertEqual(len(policy["history"]), 2)
        self.assertEqual(policy["history"][0]["windows"], policy["history"][1]["windows"])
        self.assertNotIn((600., 0.), calls)
        self.assertLessEqual(policy["local_solver_calls"], policy["maximum_local_solver_calls"])
        self.assertLessEqual(len(policy["history"][0]["windows"]), 6)


if __name__ == "__main__":
    unittest.main()
