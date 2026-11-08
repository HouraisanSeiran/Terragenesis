import unittest

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import ANALYTIC_TURN_BOUND_DEGREES, METRIC_TERRAIN_CENTERLINE_ALGORITHM as ALGORITHM, SUPERSEDES_ALGORITHM, enforce_turn_ceiling, shape_centerline, path_turns, turn_ceiling, turn_summary
from terrain_pipeline.channel_geometry import _turn_energy
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import _continuous_profile


class TerrainCenterlineTests(unittest.TestCase):
    def terrain(self):
        z, x = np.indices((11, 11))
        return TerrainGrid((100 - x * 0.2 + 0.02 * np.abs(z - 5)).astype(float),
                           np.ones((11, 11), bool), 0., 0., 30., 30.,
                           "observed_dem", "fixture", "a" * 64)

    def test_real_nodes_approach_valley_and_keep_topological_anchors(self):
        points = np.array([[30., 180.], [60., 190.], [90., 180.],
                           [120., 190.], [150., 180.]])
        receiver = np.array([1, 2, 3, 4, -1])
        result, report = shape_centerline(points, receiver, self.terrain(),
                                          iterations=12, corridor_m=30., validate=lambda _: None)
        np.testing.assert_array_equal(result[[0, -1]], points[[0, -1]])
        self.assertLess(float(result[1:-1, 1].mean()), float(points[1:-1, 1].mean()))
        self.assertLessEqual(np.max(np.linalg.norm(result - points, axis=1)), 30.)
        self.assertLess(report["final_mean_source_height_m"], report["original_mean_source_height_m"])

    def test_grid_corner_turn_reduces_and_refusals_are_reported(self):
        points = np.array([[30., 120.], [60., 120.], [90., 150.], [120., 150.]])
        receiver = np.array([1, 2, 3, -1])
        result, _ = shape_centerline(points, receiver, self.terrain(),
                                    iterations=12, corridor_m=30., validate=lambda _: None)
        self.assertLess(_turn_energy(result, receiver), _turn_energy(points, receiver))
        def refuse(candidate):
            if not np.array_equal(candidate, points):
                raise ValueError("four metre continuous budget")
        result, report = shape_centerline(points, receiver, self.terrain(),
                                          iterations=2, corridor_m=30., validate=lambda _: None,
                                          certify=refuse)
        np.testing.assert_array_equal(result, points)
        self.assertTrue(report["refused_steps"])
        self.assertTrue(any("four metre" in entry["reason"] for entry in report["refused_steps"]))

    def test_all_junction_donors_are_counted_and_descend_monotonically(self):
        # Renamed with A-P0: the old name asserted the self-referential rule "must not regress
        # against the reference path". What is actually required is monotone descent from the
        # deterministic initializer under an entry-independent ceiling.
        points = np.array([[30., 120.], [30., 180.], [60., 150.],
                           [90., 150.], [120., 150.]])
        receiver = np.array([2, 2, 3, 4, -1])
        _, junction = path_turns(points, receiver)
        self.assertEqual(int(junction.sum()), 2)
        result, report = shape_centerline(points, receiver, self.terrain(),
                                          iterations=8, corridor_m=30., validate=lambda _: None,
                                          reference_points=points)
        np.testing.assert_array_equal(result[[0, 1, 2, 4]], points[[0, 1, 2, 4]])
        initial, final = turn_summary(points, receiver), turn_summary(result, receiver)
        for category in ("ordinary", "junction"):
            for metric in ("maximum_degrees", "p95_degrees"):
                self.assertLessEqual(final[category][metric], initial[category][metric] + 1e-7)

    def test_curvature_hotspots_cover_remote_nodes_and_accept_multiple_per_round(self):
        points = np.column_stack((np.arange(1., 451.), np.full(450, 5.)))
        hotspots = np.arange(400, 441, 4)
        points[hotspots, 1] = 6.
        receiver = np.r_[np.arange(1, 450), -1]
        terrain = TerrainGrid(np.full((12, 453), 100.), np.ones((12, 453), bool),
                              0., 0., 1., 1., "observed_dem", "fixture", "a" * 64)
        result, report = shape_centerline(
            points, receiver, terrain, iterations=1, corridor_m=30.,
            reference_points=points, validate=lambda _: None)
        self.assertGreater(np.count_nonzero(np.linalg.norm(result[hotspots] - points[hotspots], axis=1)), 1)
        self.assertGreater(report["accepted_steps"]["smooth"], 1)
        # A-P0: the reference path is no longer a forward-looking acceptance limit; it is recorded
        # as an acceptance-alignment diagnostic only.
        self.assertIn("reference_turns", report)
        self.assertIn("reference_turn_regression", report)
        np.testing.assert_array_equal(result[[0, -1]], points[[0, -1]])
        self.assertLessEqual(report["smooth_candidate_trials"], report["maximum_smooth_candidate_trials"])
        self.assertEqual(report["smooth_visited_node_indices"], list(range(1, 449)))
        self.assertTrue(report["smooth_complete_ordinary_coverage"])

    def test_rejected_high_turn_does_not_prevent_later_ordinary_candidates(self):
        # A-P0: the geometry refusal below is the search's own `validate` hook (crossing/geometry),
        # not the retired reference-regression gate. A refused hotspot must still not stop the
        # rest of the curvature-ordered sweep.
        points = np.column_stack((np.arange(1., 42.), np.full(41, 5.)))
        points[1::4, 1] = 6.
        points[1, 1] = 7.
        receiver = np.r_[np.arange(1, 41), -1]
        terrain = TerrainGrid(np.full((12, 44), 100.), np.ones((12, 44), bool),
                              0., 0., 1., 1., "observed_dem", "fixture", "a" * 64)
        def reject_first(candidate):
            if not np.array_equal(candidate[1], points[1]):
                raise ValueError("first hotspot geometry refusal")
        result, report = shape_centerline(
            points, receiver, terrain, iterations=2, corridor_m=30.,
            reference_points=points, validate=reject_first)
        np.testing.assert_array_equal(result[1], points[1])
        self.assertGreater(np.linalg.norm(result[37] - points[37]), 0.)
        self.assertEqual(report["smooth_visited_node_indices"], list(range(1, 40)))
        self.assertTrue(any(entry["reason"] == "first hotspot geometry refusal"
                            for entry in report["refused_steps"]))
        self.assertLessEqual(report["smooth_candidate_trials"], 8 * 39)

    def test_turn_ceiling_ignores_saved_reference_and_only_caps_strictness(self):
        points = np.array([[30., 120.], [60., 120.], [90., 150.], [120., 150.]])
        receiver = np.array([1, 2, 3, -1])
        strict = np.array([[30., 120.], [60., 121.], [90., 150.], [120., 150.]])
        loose = np.array([[30., 120.], [60., 180.], [90., 150.], [120., 150.]])
        self.assertGreater(turn_ceiling(loose, receiver)["ordinary"],
                           turn_ceiling(strict, receiver)["ordinary"])
        # The declared bound is a cap on strictness: a dirty baseline may never be tightened.
        for baseline in (strict, loose, points):
            ceiling = turn_ceiling(baseline, receiver)
            for kind, limit in ANALYTIC_TURN_BOUND_DEGREES.items():
                self.assertGreaterEqual(ceiling[kind], limit)
        with self.assertRaisesRegex(ValueError, "analytic turn ceiling"):
            enforce_turn_ceiling(points, receiver, {"ordinary": 1e-6, "junction": 90.})

    def test_two_entries_with_different_saved_references_reach_the_same_feasible_set(self):
        # The defect this replaces: the searched space used to be pinned to whatever saved
        # reference path the caller supplied. Both entries now start from the deterministic
        # initializer, so the accepted/refused accounting must be identical.
        points = np.column_stack((np.arange(1., 42.), np.full(41, 5.)))
        points[1::4, 1] = 6.
        receiver = np.r_[np.arange(1, 41), -1]
        terrain = TerrainGrid(np.full((12, 44), 100.), np.ones((12, 44), bool),
                              0., 0., 1., 1., "observed_dem", "fixture", "a" * 64)
        dirty = points.copy()
        dirty[2, 1] = 9.
        without, first = shape_centerline(points, receiver, terrain, iterations=2, corridor_m=30.,
                                         validate=lambda _: None)
        with_dirty, second = shape_centerline(points, receiver, terrain, iterations=2, corridor_m=30.,
                                             validate=lambda _: None, reference_points=dirty)
        np.testing.assert_array_equal(without, with_dirty)
        self.assertEqual(first["accepted_steps"], second["accepted_steps"])
        self.assertEqual(first["effective_turn_ceiling_degrees"],
                         second["effective_turn_ceiling_degrees"])
        self.assertNotIn("reference_turns", first)
        self.assertIn("reference_turns", second)
        self.assertEqual(first["algorithm"], ALGORITHM)
        self.assertEqual(first["supersedes_algorithm"], SUPERSEDES_ALGORITHM)

    def test_analytic_bound_is_limited_to_movable_nodes_and_anchors_are_reported(self):
        # Anchored sources/confluences/terminals cannot move, so a wide turn there is a property
        # of the immutable grid. It is reported as an exemption instead of poisoning the bound.
        points = np.array([[30., 120.], [30., 180.], [60., 150.],
                           [90., 150.], [120., 150.]])
        receiver = np.array([2, 2, 3, 4, -1])
        _, report = shape_centerline(points, receiver, self.terrain(), iterations=4,
                                     corridor_m=30., validate=lambda _: None, reference_points=points)
        exemption = report["anchor_turn_exemption"]
        self.assertGreater(exemption["exempt_turn_count"], 0)
        self.assertEqual(exemption["exempt_node_indices"], sorted(exemption["exempt_node_indices"]))

    def test_physical_corner_smoothing_can_raise_mean_source_height(self):
        heights = np.tile(np.arange(11, dtype=float) * .1, (11, 1)) + 100.
        terrain = TerrainGrid(heights, np.ones((11, 11), bool), 0., 0., 1., 1.,
                              "observed_dem", "fixture", "a" * 64)
        points = np.array([[2., 2.], [2., 4.], [4., 4.]])
        receiver = np.array([1, 2, -1])
        certificates = []
        def certify(candidate):
            _continuous_profile(candidate, receiver, np.full(3, .25), terrain, 4., 1.)
            certificates.append(candidate.copy())
        result, report = shape_centerline(
            points, receiver, terrain, iterations=1, corridor_m=1.,
            reference_points=points, validate=lambda _: None, certify=certify)
        self.assertLess(_turn_energy(result, receiver), _turn_energy(points, receiver))
        self.assertGreater(report["final_mean_source_height_m"], report["reference_mean_source_height_m"])
        self.assertLessEqual(report["final_mean_source_height_m"] - report["reference_mean_source_height_m"], .25)
        self.assertTrue(any(np.array_equal(candidate, result) for candidate in certificates))
        np.testing.assert_array_equal(result[[0, -1]], points[[0, -1]])

    def test_local_profile_failure_preserves_other_branch_smoothing(self):
        terrain = TerrainGrid(np.full((12, 12), 100.), np.ones((12, 12), bool),
                              0., 0., 1., 1., "observed_dem", "fixture", "a" * 64)
        points = np.array([[1., 1.], [1., 3.], [3., 3.],
                           [5., 1.], [5., 3.], [7., 3.]])
        receiver = np.array([1, 2, -1, 4, 5, -1])
        def certify(candidate):
            if not np.array_equal(candidate[1], points[1]):
                raise ValueError("first branch physical profile conflict")
        result, report = shape_centerline(
            points, receiver, terrain, iterations=1, corridor_m=2.,
            reference_points=points, validate=lambda _: None, certify=certify)
        np.testing.assert_array_equal(result[1], points[1])
        self.assertGreater(np.linalg.norm(result[4] - points[4]), 0.)
        self.assertEqual(report["local_final_accepted_node_indices"], [4])
        self.assertLessEqual(report["local_final_certificate_calls"], 128)
        self.assertTrue(any(entry["phase"] == "local_final_certificate"
                            for entry in report["refused_steps"]))

    def test_failed_terrain_certificate_resets_floor_to_certified_base(self):
        terrain = self.terrain()
        points = np.array([[30., 180.], [60., 190.], [90., 180.]])
        receiver = np.array([1, 2, -1])
        def certify(candidate):
            if not np.array_equal(candidate, points):
                raise ValueError("terrain or smooth physical conflict")
        result, report = shape_centerline(
            points, receiver, terrain, iterations=1, corridor_m=30.,
            reference_points=points, validate=lambda _: None, certify=certify)
        np.testing.assert_array_equal(result, points)
        self.assertTrue(any(entry["phase"] == "terrain_certificate"
                            for entry in report["refused_steps"]))
