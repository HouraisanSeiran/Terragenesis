import unittest

import numpy as np

from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.channel_geometry import TERMINAL_STATUS_CODES, bounded_confluence_candidate


def fixture(center_height=3.0, base=0.0, outlet=True):
    height = np.array([[9., 9., 9., 9., 9.], [9., 8., 7., 8., 9.],
                       [9., 5., center_height, 5., 9.], [9., 4., 4., 4., 9.],
                       [9., 9., 2., 9., 9.]]) + base
    terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 30., 30.,
                          "generated_terrain", "bounded-test", "a" * 64)
    kinds = np.full(height.shape, "interior", dtype="U24")
    kinds[[0, -1], :] = "closed_wall"
    kinds[:, [0, -1]] = "closed_wall"
    if outlet:
        kinds[4, 2] = "unknown_boundary"
    boundary = BoundaryGrid(kinds, np.zeros(height.shape, bool), "test", "b" * 64)
    baseline = route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")
    return terrain, boundary, baseline


class BoundedConfluenceTests(unittest.TestCase):
    def test_unfilled_inclined_slope_uses_terrain_descent_instead_of_flood_tree(self):
        rows, columns = np.indices((7, 7))
        height = 100. - 5. * rows - .5 * columns
        terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 30., 30.,
                              "generated_terrain", "inclined-test", "a" * 64)
        kinds = np.full(height.shape, "interior", dtype="U24")
        kinds[[0, -1], :] = "unknown_boundary"
        kinds[:, [0, -1]] = "unknown_boundary"
        boundary = BoundaryGrid(kinds, np.zeros(height.shape, bool), "test", "b" * 64)
        baseline = route_diagnostic(terrain, boundary)
        graph, work, metadata, _ = bounded_confluence_candidate(
            terrain, boundary, np.zeros(height.shape, np.int64),
            baseline_receiver=baseline.receiver)
        interior = np.arange(49).reshape(height.shape)[1:-1, 1:-1].ravel()
        # Due south drops 5m over 30m. The SE neighbour drops 5.5m over
        # 42.4m, so the visible 45-degree queue tree is not steepest descent.
        from terrain_pipeline.drainage import strict_receivers as strict_receivers
        from terrain_pipeline.channel_geometry import _terrain_mesh
        expected = strict_receivers(terrain.elevation_m, _terrain_mesh(terrain))[0]
        np.testing.assert_array_equal(graph.receiver[interior], expected[interior])
        np.testing.assert_array_equal(work, height)
        self.assertEqual(metadata["backend"], "irregular_graph")
        self.assertEqual(metadata["algorithm"], "frozen_owner_bounded_confluence_candidate_v3_irregular")
        perimeter = np.r_[np.arange(7), np.arange(42, 49), np.arange(7, 42, 7),
                          np.arange(13, 42, 7)]
        self.assertTrue(np.all(graph.receiver[perimeter] == -1))

    def test_shallow_pit_connects_both_branches_to_shared_outlet_without_source_edits(self):
        terrain, boundary, baseline = fixture()
        original = terrain.elevation_m.copy()
        self.assertEqual(baseline.receiver[12], -1)
        graph, work, metadata, arrays = bounded_confluence_candidate(
            terrain, boundary, np.zeros(original.shape, np.int64),
            baseline_receiver=baseline.receiver, local_q_m3_s=np.ones(original.shape))
        # Both branches formerly feeding the closed shallow pit now share the
        # pit, its spill path and the original unknown perimeter endpoint.
        for source in (6, 8, 12):
            path = []
            while source >= 0:
                path.append(source)
                source = graph.receiver[source]
            self.assertIn(12, path)
            self.assertEqual(path[-1], 22)
        self.assertEqual(work[2, 2], 4.)
        self.assertEqual(metadata["maximum_fill_m"], 1.)
        np.testing.assert_array_equal(terrain.elevation_m, original)
        self.assertEqual(arrays["contributing_area_m2"][22], 25 * 900.)
        self.assertEqual(arrays["routed_q_m3_s"][22], 25.)
        self.assertFalse(metadata["natural_outlet_verified"])

    def test_deep_pit_stays_unresolved_and_actual_fill_respects_limit(self):
        terrain, boundary, baseline = fixture(center_height=-3.)
        graph, work, metadata, arrays = bounded_confluence_candidate(
            terrain, boundary, np.zeros(terrain.elevation_m.shape, np.int64),
            baseline_receiver=baseline.receiver)
        self.assertEqual(graph.receiver[12], -1)
        self.assertEqual(arrays["terminal_status"][12],
                         TERMINAL_STATUS_CODES["unresolved_deep_depression"])
        self.assertEqual(work[2, 2], -3.)
        self.assertLessEqual(metadata["maximum_fill_m"], 4.)
        self.assertIn("no accepted lake", metadata["graph_lake_preserved_semantics"])

    def test_only_original_cross_domain_contact_becomes_unresolved_port(self):
        height = np.array([[12., 11., 10., 9., 8., 7.],
                           [8., 7., 6., 5., 4., 3.],
                           [12., 11., 10., 9., 8., 7.]])
        terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 30., 30.,
                              "generated_terrain", "contacts-test", "a" * 64)
        kinds = np.full(height.shape, "closed_wall", dtype="U24")
        kinds[1, 5] = "unknown_boundary"
        boundary = BoundaryGrid(kinds, np.zeros(height.shape, bool), "test", "b" * 64)
        baseline = np.r_[np.arange(6, 12), np.arange(7, 12), -1,
                         np.arange(6, 12)].astype(np.int64)
        owner = np.zeros(height.shape, np.int64)
        owner[:, 3:] = 2
        graph, _, metadata, arrays = bounded_confluence_candidate(
            terrain, boundary, owner, baseline_receiver=baseline)
        self.assertEqual(metadata["baseline_cross_owner_contact_count"], 1)
        self.assertEqual(graph.receiver[8], -1)
        self.assertEqual(graph.outlet_kind[8], "unknown_boundary")
        self.assertEqual(arrays["terminal_status"][8],
                         TERMINAL_STATUS_CODES["unresolved_domain_boundary"])
        self.assertGreaterEqual(graph.receiver[2], 0)
        self.assertGreaterEqual(graph.receiver[14], 0)
        sources = np.flatnonzero(graph.receiver >= 0)
        np.testing.assert_array_equal(owner.ravel()[sources], owner.ravel()[graph.receiver[sources]])

    def test_component_without_seed_retains_baseline_and_complete_order(self):
        terrain, boundary, baseline = fixture(outlet=False)
        graph, work, metadata, arrays = bounded_confluence_candidate(
            terrain, boundary, np.zeros(terrain.elevation_m.shape, np.int64),
            baseline_receiver=baseline.receiver)
        np.testing.assert_array_equal(graph.receiver, baseline.receiver)
        np.testing.assert_array_equal(work, terrain.elevation_m)
        np.testing.assert_array_equal(np.sort(graph.order_downstream_first), np.arange(25))
        self.assertEqual(metadata["component_records"][0]["seed_count"], 0)
        self.assertEqual(arrays["terminal_status"][12],
                         TERMINAL_STATUS_CODES["unresolved_closed_domain"])

    def test_unseeded_component_preserves_a_nonsteepest_supplied_baseline(self):
        terrain, boundary, baseline = fixture(outlet=False)
        receiver = baseline.receiver.copy()
        # 6 -> 7 -> 12 descends, but 6 -> 12 would be the steepest choice.
        receiver[6] = 7
        graph, _, metadata, _ = bounded_confluence_candidate(
            terrain, boundary, np.zeros(terrain.elevation_m.shape, np.int64),
            baseline_receiver=receiver)
        np.testing.assert_array_equal(graph.receiver, receiver)
        self.assertEqual(metadata["steepest_descent_changed_edge_count"], 0)

    def test_negative_owner_keeps_routing_and_terminal_reason_without_ocean_claim(self):
        terrain, boundary, baseline = fixture(center_height=-3.)
        owner = np.full(terrain.elevation_m.shape, -1, np.int64)
        graph, _, metadata, arrays = bounded_confluence_candidate(
            terrain, boundary, owner, baseline_receiver=baseline.receiver)
        self.assertGreater(np.count_nonzero(graph.receiver >= 0), 20)
        self.assertEqual(arrays["terminal_status"][12],
                         TERMINAL_STATUS_CODES["unresolved_deep_depression"])
        self.assertFalse(arrays["terminal_owner_known"][12])
        self.assertEqual(graph.outlet_kind[12], "unknown_boundary")
        self.assertGreater(metadata["unknown_owner_terminal_count"], 0)

    def test_float32_priority_rounding_cannot_raise_above_actual_four_meter_cap(self):
        terrain, boundary, baseline = fixture(center_height=.001, base=134217728.)
        graph, work, metadata, arrays = bounded_confluence_candidate(
            terrain, boundary, np.zeros(terrain.elevation_m.shape, np.int64),
            baseline_receiver=baseline.receiver)
        self.assertTrue(np.all(work - terrain.elevation_m <= 4.))
        sources = np.flatnonzero(graph.receiver >= 0)
        self.assertTrue(np.all(work.ravel()[sources] >= work.ravel()[graph.receiver[sources]]))
        np.testing.assert_array_equal(work - terrain.elevation_m, arrays["working_raise_m"])
        self.assertLessEqual(metadata["maximum_fill_m"], 4.)


if __name__ == "__main__":
    unittest.main()
