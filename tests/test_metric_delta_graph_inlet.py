import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import RoutingGraph, TerrainGrid
from terrain_pipeline.surface_rivers.metric_delta import DeltaConfig, build_delta_candidate
from terrain_pipeline.surface_rivers.metric_delta_product import (
    build_delta_candidate_product, load_delta_candidate_product, save_delta_candidate_product,
)
from terrain_pipeline.drainage import diagnostic_mesh as diagnostic_mesh


class DeltaGraphInletTests(unittest.TestCase):
    def setUp(self):
        shape = (15, 17)
        self.terrain = TerrainGrid(np.zeros(shape), np.ones(shape, bool), 3000., -900., 30., 30.,
                                   "diagnostic_dem_proxy", "inlet-fixture", "a" * 64,
                                   generation_seed=20261020)
        mesh = diagnostic_mesh(self.terrain)
        # This native irregular edge crosses three columns in this absolute world frame.
        donor, target = 5, 8
        self.assertIn(target, mesh.indices[mesh.indptr[donor]:mesh.indptr[donor + 1]])
        count = self.terrain.elevation_m.size
        receiver = np.full(count, -1, np.int64)
        receiver[donor] = target
        length = np.zeros(count)
        length[donor] = np.hypot(mesh.node_x_m[target] - mesh.node_x_m[donor],
                                 mesh.node_z_m[target] - mesh.node_z_m[donor])
        kinds = np.full(count, "unknown_boundary", dtype="U24")
        kinds[donor] = "interior"
        order = np.r_[np.delete(np.arange(count, dtype=np.int64), donor), donor]
        self.graph = RoutingGraph(receiver, order, self.terrain.valid_mask, length, np.zeros(count),
                                  kinds, np.full(count, -1, np.int64),
                                  self.terrain.identity_sha256, "b" * 64)
        self.land = np.zeros(shape, bool)
        self.land[:, :6] = True
        self.water = ~self.land
        self.path = ((0, 5), (0, 8))
        self.config = DeltaConfig(seed=20261020, max_radius_cells=3)

    def build(self, **changes):
        values = dict(terrain=self.terrain, land_mask=self.land, water_mask=self.water,
                      main_path=self.path, sediment_solid_m3=30.,
                      parent_graph_identity_sha256=self.graph.identity_sha256,
                      parent_geometry_identity_sha256="c" * 64, config=self.config,
                      source_graph=self.graph)
        values.update(changes)
        return build_delta_candidate(**values)

    def test_native_long_edge_finds_first_water_and_cold_replays(self):
        result = self.build()
        self.assertEqual(result["mouth_cell"], (0, 6))
        self.assertFalse(result["publishable"])
        product = build_delta_candidate_product(
            self.terrain, self.land, self.water, self.path, 30., self.graph.identity_sha256,
            "c" * 64, self.config, source_graph=self.graph)
        self.assertEqual(product["metadata"]["schema"], "terragenesis-delta-candidate-product-v3")
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "graph-delta.npz"
            save_delta_candidate_product(filename, product)
            restored = load_delta_candidate_product(filename, expected_sha256=file_sha256(filename))
        self.assertEqual(restored["identity_sha256"], product["identity_sha256"])
        np.testing.assert_array_equal(restored["arrays"]["height_delta_m"], result["height_delta_m"])

    def test_wrong_world_parent_and_nonedge_rejected(self):
        for terrain in (replace(self.terrain, x0_m=3030.),
                        replace(self.terrain, generation_seed=20261021)):
            with self.subTest(terrain=terrain.identity_sha256), self.assertRaisesRegex(ValueError, "identity mismatch"):
                self.build(terrain=terrain)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.build(parent_graph_identity_sha256="d" * 64)
        with self.assertRaisesRegex(ValueError, "directed source graph path"):
            self.build(main_path=((0, 5), (0, 7)))
        with self.assertRaisesRegex(ValueError, "legacy"):
            self.build(source_graph=None)

    def test_unknown_classification_and_island_on_edge_rejected(self):
        unknown_water = self.water.copy()
        unknown_water[0, 7] = False
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.build(water_mask=unknown_water)
        land, water = self.land.copy(), self.water.copy()
        land[0, 7], water[0, 7] = True, False
        with self.assertRaisesRegex(ValueError, "land after first water"):
            self.build(land_mask=land, water_mask=water)
        valid = self.terrain.valid_mask.copy()
        valid[0, 7] = False
        with self.assertRaisesRegex(ValueError, "unknown"):
            replace(self.graph, valid_mask=valid,
                    order_downstream_first=self.graph.order_downstream_first[
                        self.graph.order_downstream_first != 7])


if __name__ == "__main__":
    unittest.main()
