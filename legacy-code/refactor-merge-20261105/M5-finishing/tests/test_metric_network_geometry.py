import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.channel_geometry import NetworkGeometryConfig, build_network_geometry_plan, validate_network_geometry_plan


class NetworkGeometryPlanTests(unittest.TestCase):
    def test_resealed_continuous_edge_length_tamper_is_rejected(self):
        from dataclasses import replace
        from tools.verify_td_river_geometry import fixture
        terrain, _, _, _ = fixture("single")
        outlet = np.zeros(terrain.valid_mask.shape, bool)
        outlet[-1, -1] = True
        boundary = BoundaryGrid.from_outlet_mask(terrain, outlet,
                                                source_id="edge", source_sha256="b" * 64)
        graph = route_diagnostic(terrain, boundary)
        plan = build_network_geometry_plan(terrain, graph)
        lengths = graph.edge_length_m.copy()
        lengths[np.flatnonzero(graph.receiver >= 0)[0]] *= 1.1
        forged = replace(graph, edge_length_m=lengths)
        arrays = {key: value.copy() for key, value in plan["arrays"].items()}
        arrays["graph_edge_length_m"] = lengths
        metadata = dict(plan["metadata"], graph_identity_sha256=forged.identity_sha256)
        bad = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
        with self.assertRaisesRegex(ValueError, "continuous metric node"):
            validate_network_geometry_plan(bad)

    def test_complete_edge_partition_monotone_sections_and_native_area(self):
        row, col = np.indices((7, 7))
        terrain = TerrainGrid((100. - row - .4 * col).astype(np.float64),
                              np.ones((7, 7), bool), 0., 0., 10., 10.,
                              "observed_dem", "plane", "a" * 64)
        mask = np.zeros((7, 7), bool)
        mask[-1, -1] = True
        boundary = BoundaryGrid.from_outlet_mask(terrain, mask, source_id="edge", source_sha256="b" * 64)
        graph = route_diagnostic(terrain, boundary)
        plan = build_network_geometry_plan(terrain, graph, NetworkGeometryConfig(
            min_contributing_area_m2=100., max_patch_edges=2))
        a = plan["arrays"]
        self.assertEqual(len(a["selected_edge_source_ids"]), int((graph.receiver >= 0).sum()))
        self.assertEqual(len(np.unique(a["patch_edge_source_ids"])), len(a["patch_edge_source_ids"]))
        self.assertTrue(np.all(np.diff(a["patch_offsets"]) <= 2))
        self.assertAlmostEqual(a["contributing_area_m2"][-1], 4900.)
        for i, j in zip(a["selected_edge_source_ids"], a["selected_edge_target_ids"]):
            self.assertGreaterEqual(a["contributing_area_m2"][j], a["contributing_area_m2"][i])
        self.assertTrue(validate_network_geometry_plan(plan))
        self.assertFalse(plan["metadata"]["geometry_verified"])

    def test_resigned_duplicate_edge_is_rejected(self):
        from tools.verify_td_river_geometry import fixture
        terrain, _, _, _ = fixture("single")
        outlet = np.zeros(terrain.valid_mask.shape, bool)
        outlet[-1, -1] = True
        boundary = BoundaryGrid.from_outlet_mask(terrain, outlet, source_id="edge", source_sha256="b" * 64)
        graph = route_diagnostic(terrain, boundary)
        plan = build_network_geometry_plan(terrain, graph, NetworkGeometryConfig(min_contributing_area_m2=100.))
        arrays = {k: v.copy() for k, v in plan["arrays"].items()}
        arrays["patch_edge_source_ids"][1] = arrays["patch_edge_source_ids"][0]
        bad = dict(arrays=arrays, metadata=plan["metadata"],
                   identity_sha256=identity(arrays, plan["metadata"]))
        with self.assertRaisesRegex(ValueError, "catalogue mismatch"):
            validate_network_geometry_plan(bad)

    def test_other_source_graph_is_rejected_even_with_same_validity(self):
        from tools.verify_td_river_geometry import fixture
        terrain, _, _, _ = fixture("single")
        outlet = np.zeros(terrain.valid_mask.shape, bool)
        outlet[-1, -1] = True
        boundary = BoundaryGrid.from_outlet_mask(terrain, outlet, source_id="edge", source_sha256="b" * 64)
        graph = route_diagnostic(terrain, boundary)
        other = TerrainGrid(terrain.elevation_m + 1., terrain.valid_mask, terrain.x0_m,
                            terrain.z0_m, terrain.dx_m, terrain.dz_m,
                            terrain.source_kind, "other-source", "c" * 64)
        with self.assertRaisesRegex(ValueError, "terrain identity"):
            build_network_geometry_plan(other, graph)


if __name__ == "__main__":
    unittest.main()
