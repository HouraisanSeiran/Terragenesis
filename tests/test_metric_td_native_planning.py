import unittest

import numpy as np

from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.channel_geometry import TERMINAL_STATUS_CODES, bounded_confluence_candidate
from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_rivers.metric_td_native_planning import (
    native_planning_candidate, native_planning_identity,
)


def valley_fixture(center_height=3.):
    height = np.array([[9., 9., 9., 9., 9.], [9., 8., 7., 8., 9.],
                       [9., 5., center_height, 5., 9.], [9., 4., 4., 4., 9.],
                       [9., 9., 2., 9., 9.]])
    terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 30., 30.,
                          "generated_terrain", "native-valley-test", "a" * 64)
    kinds = np.full(height.shape, "interior", dtype="U24")
    kinds[[0, -1], :] = "unknown_boundary"
    kinds[:, [0, -1]] = "unknown_boundary"
    boundary = BoundaryGrid(kinds, np.zeros(height.shape, bool), "test", "b" * 64)
    baseline = route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")
    coarse_owner = np.zeros(height.shape, np.int64)
    coarse_owner[:, 2:] = 1
    return terrain, boundary, baseline, coarse_owner


class NativePlanningTests(unittest.TestCase):
    def test_coarse_label_wall_cannot_cut_real_td_valley_in_native_candidate(self):
        terrain, boundary, baseline, coarse_owner = valley_fixture()
        old_graph, _, _, old_arrays = bounded_confluence_candidate(
            terrain, boundary, coarse_owner, baseline_receiver=baseline.receiver)
        self.assertEqual(old_graph.receiver[6], -1)
        self.assertEqual(old_arrays["terminal_status"][6],
                         TERMINAL_STATUS_CODES["unresolved_domain_boundary"])
        graph, work, metadata, arrays = native_planning_candidate(
            terrain, boundary, coarse_owner, baseline_receiver=baseline.receiver)
        self.assertGreaterEqual(graph.receiver[6], 0)
        source = 6
        path = []
        while source >= 0:
            path.append(source)
            source = graph.receiver[source]
        self.assertIn(12, path)
        self.assertEqual(path[-1], 22)
        changed_labels = np.full(coarse_owner.shape, -2, np.int64)
        changed_labels[::2] = 45
        other_graph, other_work, other_metadata, _ = native_planning_candidate(
            terrain, boundary, changed_labels, baseline_receiver=baseline.receiver)
        np.testing.assert_array_equal(other_graph.receiver, graph.receiver)
        np.testing.assert_array_equal(other_work, work)
        self.assertEqual(other_metadata["native_planning_identity_sha256"],
                         metadata["native_planning_identity_sha256"])
        self.assertNotEqual(other_metadata["coarse_reference_identity_sha256"],
                            metadata["coarse_reference_identity_sha256"])
        self.assertEqual(metadata["artificial_internal_domain_terminal_count"], 0)
        owners = arrays["native_planning_owner_domain_id"].ravel()
        sources = np.flatnonzero(graph.receiver >= 0)
        np.testing.assert_array_equal(owners[sources], owners[graph.receiver[sources]])
        self.assertGreater(metadata["coarse_reference_diagnostics"]["cross_label_edge_count"], 0)
        self.assertFalse(metadata["independent_divide_certification"])

    def test_native_identity_is_cold_recomputable_and_deep_sink_remains_unresolved(self):
        terrain, boundary, baseline, coarse_owner = valley_fixture(center_height=-3.)
        original = terrain.elevation_m.copy()
        graph, work, metadata, arrays = native_planning_candidate(
            terrain, boundary, coarse_owner, baseline_receiver=baseline.receiver)
        owner = arrays["native_planning_owner_domain_id"]
        self.assertEqual(metadata["native_planning_identity_sha256"],
                         native_planning_identity(owner, **metadata["planning_identity_inputs"]))
        self.assertEqual(metadata["native_planning_identity_sha256"], identity(
            {"native_planning_owner_domain_id": owner}, metadata["native_planning_metadata"]))
        self.assertEqual(graph.receiver[12], -1)
        self.assertEqual(arrays["terminal_status"][12],
                         TERMINAL_STATUS_CODES["unresolved_deep_depression"])
        self.assertEqual(owner.ravel()[12], 12)
        self.assertEqual(work[2, 2], -3.)
        self.assertTrue(np.all(work - terrain.elevation_m <= 4.))
        np.testing.assert_array_equal(terrain.elevation_m, original)
        self.assertFalse(metadata["complete_hydrological_domains"])
        self.assertFalse(metadata["natural_outlet_verified"])

    def test_native_support_rejects_claimed_internal_boundaries(self):
        terrain, boundary, baseline, coarse_owner = valley_fixture()
        kinds = boundary.kind.copy()
        kinds[2, 2] = "closed_wall"
        internal_wall = BoundaryGrid(kinds, np.zeros(kinds.shape, bool), "test", "b" * 64)
        with self.assertRaisesRegex(ValueError, "no internal label boundaries"):
            native_planning_candidate(terrain, internal_wall, coarse_owner,
                                      baseline_receiver=baseline.receiver)


if __name__ == "__main__":
    unittest.main()
