import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.channel_geometry import GeometryConfig
from terrain_pipeline.channel_geometry import TileBudget, build_tiled_monotone_union, build_tiled_refinement_pair, load_tiled_monotone_union, save_tiled_monotone_union, validate_tiled_monotone_union
from tests.test_metric_valley_incision import uphill_source


def make_union(budget=None, spacing=.5):
    terrain = uphill_source()
    shape = terrain.elevation_m.shape
    return build_tiled_monotone_union(
        terrain, np.array([30, 40], np.int64), np.array([1, -1], np.int64),
        np.array([2., 2.]), np.array([.25, .25]),
        owner_grid=np.zeros(shape, np.int64), corridor_mask=np.ones(shape, bool),
        lake_mask=np.zeros(shape, bool), source_plan_identity_sha256="b" * 64,
        config=GeometryConfig(fine_spacing_m=spacing, smoothing_iterations=0),
        budget=budget)


class TiledValleyUnionTests(unittest.TestCase):
    def test_shared_field_is_partitioned_with_unique_cells(self):
        product = make_union(TileBudget(max_cells=2, max_vertices=64))
        self.assertGreater(product["metadata"]["tile_count"], 1)
        self.assertTrue(validate_tiled_monotone_union(product))
        records = product["metadata"]["tile_records"]
        self.assertTrue(all(row["cell_count"] <= 2 for row in records))
        self.assertEqual(product["metadata"]["global_unique_cell_ownership"], True)

    def test_cold_validator_does_not_close_or_optimize(self):
        product = make_union()
        with patch('terrain_pipeline.channel_geometry._close_bed',
                   side_effect=AssertionError("cold validator ran closure")), \
             patch('terrain_pipeline.channel_geometry._i34_linprog',
                   side_effect=AssertionError("cold validator ran optimizer")):
            self.assertTrue(validate_tiled_monotone_union(product))

    def test_saved_roundtrip_and_tile_tamper_are_rejected(self):
        product = make_union(TileBudget(max_cells=2, max_vertices=64))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiled.npz"
            save_tiled_monotone_union(path, product)
            loaded = load_tiled_monotone_union(
                path, expected_sha256=file_sha256(path),
                expected_identity=product["identity_sha256"])
        self.assertEqual(loaded["identity_sha256"], product["identity_sha256"])
        forged = deepcopy(product)
        forged["arrays"]["tile_cut_depth_m"] = forged["arrays"]["tile_cut_depth_m"].copy()
        forged["arrays"]["tile_cut_depth_m"][0] += .01
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "shared corner|tile identity|global field"):
            validate_tiled_monotone_union(forged)

    def test_refinement_keeps_fixed_two_percent_gate(self):
        pair = build_tiled_refinement_pair(
            uphill_source(), np.array([30, 40], np.int64), np.array([1, -1], np.int64),
            np.array([2., 2.]), np.array([.25, .25]),
            owner_grid=np.zeros((9, 9), np.int64), corridor_mask=np.ones((9, 9), bool),
            lake_mask=np.zeros((9, 9), bool), source_plan_identity_sha256="b" * 64,
            config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0),
            budget=TileBudget(max_cells=64, max_vertices=1024))
        self.assertLessEqual(pair["spatial_refinement_relative"], .02)
        self.assertTrue(validate_tiled_monotone_union(pair["coarse"]))
        self.assertTrue(validate_tiled_monotone_union(pair["fine"]))


if __name__ == "__main__":
    unittest.main()
