import hashlib
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.surface_rivers.metric_bank_braiding import (
    BankPointbarConfig, BraidedConfig, build_bank_pointbar_candidate,
    build_braided_candidate)
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_cutoff import CutoffConfig, find_cutoff_candidate
from terrain_pipeline.surface_rivers.metric_delta import DeltaConfig
from terrain_pipeline.surface_rivers.metric_delta_product import (
    build_delta_candidate_product, validate_delta_candidate_product)
from terrain_pipeline.surface_rivers.metric_fan_floodplain import (
    FanFloodplainConfig, build_alluvial_fan_candidate, build_floodplain_candidate)
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256, load_td_source


def _terrain_window():
    source = load_td_source()
    arrays, metadata = source["arrays"], source["metadata"]
    rows, columns = arrays["height_m"].shape
    center_row, center_column = rows // 2, columns // 2
    window = (slice(center_row - 16, center_row + 17), slice(center_column - 16, center_column + 17))
    spacing = metadata["spacing_m"]
    origin_x, origin_z = metadata["origin_m_xz"]
    terrain = TerrainGrid(
        arrays["height_m"][window].copy(), arrays["valid_mask"][window].copy(),
        origin_x + (center_column - 16) * spacing,
        origin_z + (center_row - 16) * spacing,
        spacing, spacing, "generated_terrain", source["identity_sha256"], PRIMARY_SHA256,
        vertical_datum="sea_zero_m", model_version="Terrain Diffusion",
        generation_seed=20261001, condition_summary="pinned TD source window",
        source_path=str(PRIMARY_PATH))
    return source, terrain


def _local_points(terrain):
    def point(row, column):
        return [terrain.x0_m + column * terrain.dx_m, terrain.z0_m + row * terrain.dz_m]
    return np.asarray([point(5, 5), point(5, 14), point(10, 20), point(20, 20),
                       point(27, 14), point(27, 5)], dtype=np.float64)


@unittest.skipUnless(PRIMARY_PATH.is_file(), "pinned TD source unavailable")
class RealTDMorphologyCandidateTests(unittest.TestCase):
    def setUp(self):
        self.source, self.terrain = _terrain_window()
        shape = self.terrain.elevation_m.shape
        self.land = np.zeros(shape, dtype=bool)
        self.water = np.zeros(shape, dtype=bool)
        self.land[:, :16] = self.terrain.valid_mask[:, :16]
        self.water[:, 16:] = self.terrain.valid_mask[:, 16:]
        self.delta_path = tuple((16, column) for column in range(12, 18))
        self.parent_graph = self.source["identity_sha256"]
        self.parent_geometry = hashlib.sha256(b"td256-local-morphology-candidate-v1").hexdigest()

    def test_real_td_window_runs_all_six_candidate_families(self):
        delta = build_delta_candidate_product(
            self.terrain, self.land, self.water, self.delta_path, 1200.,
            self.parent_graph, self.parent_geometry,
            DeltaConfig(max_radius_cells=4, max_deposit_depth_m=.8, seed=17))
        self.assertTrue(validate_delta_candidate_product(delta))
        self.assertEqual(delta["metadata"]["terrain_metadata"]["source_sha256"], PRIMARY_SHA256)

        centerline = _local_points(self.terrain)
        edge_ids = tuple("td-edge-%02d" % index for index in range(len(centerline) - 1))
        cutoff = find_cutoff_candidate(
            self.terrain, centerline, edge_ids, self.parent_graph, self.parent_geometry,
            12., 4., CutoffConfig(neck_distance_m=900., min_loop_length_m=60.,
                                   max_bed_rise_m=10000.))
        self.assertEqual(cutoff["status"], "candidate")
        bank = build_bank_pointbar_candidate(
            self.terrain, centerline, self.parent_graph, self.parent_geometry, 20.,
            BankPointbarConfig(max_erosion_depth_m=.05, max_deposit_depth_m=.05))
        self.assertEqual(bank["status"], "candidate")

        water = np.zeros(self.terrain.elevation_m.shape, dtype=bool)
        for row, column in self.delta_path:
            for water_row in range(max(0, row - 1), min(water.shape[0], row + 2)):
                water[water_row, column] = self.terrain.valid_mask[water_row, column]
        braided = build_braided_candidate(
            self.terrain, self.delta_path, water, self.parent_graph, self.parent_geometry,
            8., 12., BraidedConfig(max_candidates=3, branch_fraction=.2))
        self.assertIn(len(braided["candidate_paths"]), (2, 3))

        fan = build_alluvial_fan_candidate(
            self.terrain, [self.terrain.x0_m + 16 * self.terrain.dx_m,
                           self.terrain.z0_m + 16 * self.terrain.dz_m], [1., 0.], 1200.,
            self.parent_graph, self.parent_geometry,
            FanFloodplainConfig(max_fan_radius_m=180., max_deposit_depth_m=.5))
        self.assertEqual(fan["status"], "candidate")

        floodplain = build_floodplain_candidate(
            self.terrain, centerline, 20., self.parent_graph, self.parent_geometry,
            FanFloodplainConfig(bank_height_m=30., max_floodplain_half_width_m=180.))
        self.assertEqual(floodplain["status"], "candidate")
        self.assertGreater(floodplain["storage_proxy_m3"], 0.)
        for candidate in (cutoff, bank, braided, fan, floodplain):
            self.assertFalse(candidate.get("hydraulic", False))
            self.assertFalse(candidate.get("publishable", False))

    def test_source_identity_is_pinned(self):
        self.assertEqual(file_sha256(PRIMARY_PATH), PRIMARY_SHA256)
        self.assertEqual(self.terrain.source_id, self.source["identity_sha256"])
        self.assertEqual(self.terrain.source_sha256, PRIMARY_SHA256)


if __name__ == "__main__":
    unittest.main()
