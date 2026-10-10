import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_delta import DeltaConfig, build_delta_candidate
from terrain_pipeline.surface_rivers.metric_delta_product import (
    build_delta_candidate_product,
    load_delta_candidate_product,
    validate_delta_candidate_product,
)
from terrain_pipeline.td_basin_source import PRIMARY_PATH, load_td_source


class DeltaCandidateProductTests(unittest.TestCase):
    def setUp(self):
        height = np.zeros((5, 7), dtype=np.float64)
        self.terrain = TerrainGrid(height, np.ones_like(height, dtype=bool), 0., 0., 2., 3.,
                                   "diagnostic_dem_proxy", "fixture", "a" * 64)
        self.land = np.zeros((5, 7), dtype=bool)
        self.land[:, :2] = True
        self.water = np.zeros((5, 7), dtype=bool)
        self.water[:, 2:6] = True
        self.water[0, 6] = True
        self.path = ((2, 0), (2, 1), (2, 2))
        self.config = DeltaConfig(max_radius_cells=3, max_deposit_depth_m=.2,
                                  porosity=.25, seed=7,
                                  max_distributary_candidates=3)

    def test_candidate_event_does_not_claim_graph_edges(self):
        result = build_delta_candidate(self.terrain, self.land, self.water, self.path, 3.,
                                       "b" * 64, "c" * 64, self.config)
        self.assertEqual(result["event"].added_edges, ())
        self.assertEqual(result["event"].retired_edges, ())
        self.assertEqual(result["event"].parameters["topology_status"], "candidate_geometry_only")

    def test_weighted_capacity_allocation_conserves_when_capacity_allows(self):
        result = build_delta_candidate(self.terrain, self.land, self.water, self.path, 3.,
                                       "b" * 64, "c" * 64, self.config)
        ledger = result["material_ledger"]
        self.assertAlmostEqual(ledger["deposited_solid_m3"] + ledger["unresolved_solid_m3"], 3.)
        self.assertAlmostEqual(ledger["unresolved_solid_m3"], 0.)

    def test_product_validates_and_cold_reads(self):
        product = build_delta_candidate_product(self.terrain, self.land, self.water, self.path, 100.,
                                                 "b" * 64, "c" * 64, self.config)
        self.assertTrue(validate_delta_candidate_product(product))
        self.assertFalse(product["metadata"]["capabilities"]["topology_mutation"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delta.npz"
            from terrain_pipeline.surface_rivers.metric_delta_product import save_delta_candidate_product
            save_delta_candidate_product(path, product)
            restored = load_delta_candidate_product(path, expected_sha256=file_sha256(path))
            self.assertEqual(restored["identity_sha256"], product["identity_sha256"])
            np.testing.assert_array_equal(restored["arrays"]["height_delta_m"], product["arrays"]["height_delta_m"])

    def test_product_rejects_tampered_event(self):
        product = build_delta_candidate_product(self.terrain, self.land, self.water, self.path, 10.,
                                                 "b" * 64, "c" * 64, self.config)
        changed = copy.deepcopy(product)
        changed["metadata"]["event_record"]["parameters"]["candidate_count"] = 0
        with self.assertRaises(ValueError):
            validate_delta_candidate_product(changed)
        changed = copy.deepcopy(product)
        changed["metadata"]["capabilities"]["publishable"] = True
        with self.assertRaises(ValueError):
            validate_delta_candidate_product(changed)

    def test_zero_candidate_paths_cold_read(self):
        land = np.zeros((2, 2), dtype=bool)
        water = np.zeros((2, 2), dtype=bool)
        land[0, 0] = True
        water[0, 1] = True
        terrain = TerrainGrid(np.zeros((2, 2), dtype=np.float64), np.ones((2, 2), bool),
                              0., 0., 2., 2., "diagnostic_dem_proxy", "one-water-cell", "a" * 64)
        product = build_delta_candidate_product(terrain, land, water, ((0, 0), (0, 1)), 5.,
                                                "b" * 64, "c" * 64)
        self.assertEqual(product["arrays"]["candidate_polylines"].shape, (0, 2, 2))
        self.assertEqual(product["metadata"]["candidate_edge_ids"], [])
        self.assertAlmostEqual(product["metadata"]["material_ledger"]["unresolved_solid_m3"], 2.4)
        self.assertAlmostEqual(product["metadata"]["material_ledger"]["deposited_solid_m3"], 2.6)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zero-candidates.npz"
            from terrain_pipeline.surface_rivers.metric_delta_product import save_delta_candidate_product
            save_delta_candidate_product(path, product)
            restored = load_delta_candidate_product(path, expected_sha256=file_sha256(path))
            self.assertEqual(restored["identity_sha256"], product["identity_sha256"])

    def test_rehashed_tampering_and_unknown_cells_rejected(self):
        product = build_delta_candidate_product(self.terrain, self.land, self.water, self.path, 10.,
                                                "b" * 64, "c" * 64, self.config)
        for field, value in (("revalidation_required", []), ("units", {"elevation": "km"}),
                             ("extra", "forbidden")):
            with self.subTest(field=field):
                changed = copy.deepcopy(product)
                changed["metadata"][field] = value
                changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
                with self.assertRaises(ValueError):
                    validate_delta_candidate_product(changed)
        changed = copy.deepcopy(product)
        changed["arrays"]["deposit_mask"][2, 2] = False
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_delta_candidate_product(changed)
        valid = self.terrain.valid_mask.copy()
        valid[0, 0] = False
        masked = TerrainGrid(self.terrain.elevation_m.copy(), valid, 0., 0., 2., 3.,
                             "diagnostic_dem_proxy", "unknown", "a" * 64)
        with self.assertRaises(ValueError):
            build_delta_candidate(masked, self.land, self.water, self.path, 1.,
                                  "b" * 64, "c" * 64)

    @unittest.skipUnless(PRIMARY_PATH.is_file(), "pinned TD terrain source unavailable")
    def test_pinned_real_td_terrain_with_explicit_local_interpretation(self):
        source = load_td_source()
        self.assertEqual(source["metadata"]["source_sha256"], file_sha256(PRIMARY_PATH))
        height = source["arrays"]["height_m"]
        valid = source["arrays"]["valid_mask"]
        spacing = source["metadata"]["spacing_m"]
        origin_x, origin_z = source["metadata"]["origin_m_xz"]
        # This is an explicitly imposed local land/water interpretation over an
        # authentic TD elevation source, NOT evidence of a certified TD estuary.
        row, column = height.shape[0] // 2, height.shape[1] // 2
        window = (slice(row - 5, row + 6), slice(column - 5, column + 6))
        terrain = TerrainGrid(height[window].copy(), valid[window].copy(),
                              origin_x + (column - 5) * spacing,
                              origin_z + (row - 5) * spacing, spacing, spacing,
                              "generated_terrain", "td-local-imposed-mouth", source["identity_sha256"],
                              vertical_datum="sea_zero_m", source_path=str(PRIMARY_PATH))
        land = np.zeros((11, 11), dtype=bool)
        water = np.zeros((11, 11), dtype=bool)
        land[:, :5] = valid[window][:, :5]
        water[:, 5:] = valid[window][:, 5:]
        self.assertTrue(land[5, 4] and water[5, 5])
        product = build_delta_candidate_product(terrain, land, water,
                                                ((5, 3), (5, 4), (5, 5)), 1200.,
                                                "b" * 64, "c" * 64,
                                                DeltaConfig(max_radius_cells=4, seed=17))
        self.assertEqual(product["metadata"]["terrain_metadata"]["source_sha256"],
                         source["identity_sha256"])
        self.assertEqual(product["metadata"]["terrain_metadata"]["source_path"], str(PRIMARY_PATH))
        self.assertEqual(product["metadata"]["mouth_cell"], [5, 5])
        self.assertEqual(product["metadata"]["status"], "candidate")
        self.assertFalse(product["metadata"]["capabilities"]["natural_outlet"])
        self.assertFalse(product["metadata"]["capabilities"]["publishable"])
        ledger = product["metadata"]["material_ledger"]
        self.assertGreater(ledger["deposited_solid_m3"], 0.)
        self.assertAlmostEqual(ledger["deposited_solid_m3"] + ledger["unresolved_solid_m3"], 1200.)
        self.assertFalse(np.any(product["arrays"]["deposit_mask"] & ~water))
        self.assertTrue(validate_delta_candidate_product(product))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "td-local-candidate.npz"
            from terrain_pipeline.surface_rivers.metric_delta_product import save_delta_candidate_product
            save_delta_candidate_product(path, product)
            restored = load_delta_candidate_product(path, expected_sha256=file_sha256(path))
            self.assertEqual(restored["identity_sha256"], product["identity_sha256"])
            self.assertTrue(validate_delta_candidate_product(restored))
            np.testing.assert_array_equal(restored["arrays"]["height_delta_m"],
                                          product["arrays"]["height_delta_m"])


if __name__ == "__main__":
    unittest.main()
