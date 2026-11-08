import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.lake import NaturalLakeConfig as NaturalLakeConfig
from terrain_pipeline.lake import build_natural_lakes as build_natural_lakes
from terrain_pipeline.lake import load_natural_lakes as load_natural_lakes
from terrain_pipeline.lake import save_natural_lakes as save_natural_lakes
from terrain_pipeline.lake import solve_natural_lakes as solve_natural_lakes
from terrain_pipeline.lake import validate_natural_lakes as validate_natural_lakes
from terrain_pipeline.lake import lake_volume_at_stage as lake_volume_at_stage
from terrain_pipeline.lake import lake_stage_at_volume as lake_stage_at_volume


def two_lakes(*, unknown=False, boundary_kind="closed"):
    height = np.full((5, 7), 4., np.float64)
    height[2, 1:6] = [0., 1., 0., 1., 1.]
    valid = np.ones_like(height, bool)
    if unknown:
        valid[1, 2] = False
    terrain = TerrainGrid(height, valid, 0., 0., 2., 3.,
                          "observed_dem", "two original basins", "a" * 64)
    owner = np.full(height.shape, -1, np.int64)
    owner[2, 1:3] = 0
    owner[2, 3:6] = 1
    boundary = np.array([[2 * 7 + 5, 2 * 7 + 6]], np.int64)
    domain = build_natural_lakes(
        terrain, np.array([15, 17], np.int64), owner,
        max_stage_m=np.array([5., 5.]), boundary_faces=boundary,
        boundary_kinds=np.array([boundary_kind]), weir_coefficient_m3_s_m15=1.,
        source_provenance="analytical source", boundary_provenance="declared test boundary")
    return domain


def two_saddles():
    height = np.full((5, 7), 4., np.float64)
    height[1:3, 1:6] = np.array([[0., 1., 0., 2., 2.],
                                  [0., 1., 0., 2., 2.]])
    terrain = TerrainGrid(height, np.ones_like(height, bool), 0., 0., 2., 3.,
                          "observed_dem", "two saddle basin", "a" * 64)
    owner = np.full(height.shape, -1, np.int64)
    owner[1:3, 1:3] = 0
    owner[1:3, 3:6] = 1
    return build_natural_lakes(terrain, np.array([8, 10], np.int64), owner,
                               max_stage_m=np.array([5., 5.]),
                               boundary_faces=np.empty((0, 2), np.int64),
                               boundary_kinds=np.empty(0, dtype="U16"),
                               weir_coefficient_m3_s_m15=1.,
                               source_provenance="analytical bed",
                               boundary_provenance="all exterior unresolved")


class NaturalLakeTests(unittest.TestCase):
    def test_unknown_neighbor_reaches_known_side_bed_and_fails_prefix(self):
        height = np.array([[0., 4., 4.], [4., 4., 4.]], np.float64)
        valid = np.ones_like(height, bool)
        valid[0, 1] = False
        terrain = TerrainGrid(height, valid, 0., 0., 1., 1.,
                              "observed_dem", "unknown neighbor", "a" * 64)
        owner = np.full(height.shape, -1, np.int64)
        owner[0, 0] = 0
        domain = build_natural_lakes(
            terrain, np.array([0], np.int64), owner,
            max_stage_m=np.array([5.]), boundary_faces=np.array([[0, -1]], np.int64),
            boundary_kinds=np.array(["closed"]), weir_coefficient_m3_s_m15=1.,
            source_provenance="unknown source", boundary_provenance="top perimeter closed")
        self.assertEqual(domain["arrays"]["unresolved_stage_limit_m"].tolist(), [0.])
        trace = solve_natural_lakes(domain, np.array([0., 1.]), np.array([[1.]]),
                                    np.zeros(1), np.zeros((1, 1)),
                                    forcing_provenance="unknown overtop")
        self.assertEqual(trace["metadata"]["status"], "failed_prefix")

    def test_high_owner_cells_remain_dry_and_storage_curve_is_native_prisms(self):
        source = two_lakes()
        a = source["arrays"]
        terrain = TerrainGrid(a["source_height_m"], a["source_valid_mask"], 0., 0., 2., 3.,
                              "observed_dem", "two original basins", "a" * 64)
        domain = build_natural_lakes(
            terrain, a["seed_cell_ids"], a["owner_grid"],
            max_stage_m=np.array([.5, .5]), boundary_faces=a["boundary_faces"],
            boundary_kinds=a["boundary_kinds"], weir_coefficient_m3_s_m15=1.,
            source_provenance="analytical source", boundary_provenance="declared test boundary")
        self.assertAlmostEqual(lake_volume_at_stage(domain, 0, .5), 3.)
        self.assertAlmostEqual(lake_stage_at_volume(domain, 0, 3.), .5)
        self.assertEqual(np.count_nonzero(domain["arrays"]["source_height_m"].ravel()[
            domain["arrays"]["support_cell_ids"]] < .5), 2)

    def test_perimeter_is_unresolved_exterior_and_stops_at_crest(self):
        height = np.array([[0., 4.], [4., 4.]], np.float64)
        terrain = TerrainGrid(height, np.ones_like(height, bool), 0., 0., 1., 1.,
                              "observed_dem", "perimeter", "a" * 64)
        owner = np.full(height.shape, -1, np.int64)
        owner[0, 0] = 0
        domain = build_natural_lakes(
            terrain, np.array([0], np.int64), owner,
            max_stage_m=np.array([5.]), boundary_faces=np.empty((0, 2), np.int64),
            boundary_kinds=np.empty(0, dtype="U16"),
            weir_coefficient_m3_s_m15=1., source_provenance="perimeter source",
            boundary_provenance="unresolved perimeter")
        self.assertEqual(domain["arrays"]["unresolved_stage_limit_m"].tolist(), [0.])
        trace = solve_natural_lakes(domain, np.array([0., 1.]), np.array([[1.]]),
                                    np.zeros(1), np.zeros((1, 0)),
                                    forcing_provenance="perimeter overtop")
        self.assertEqual(trace["metadata"]["status"], "failed_prefix")
        self.assertIn("unresolved exterior", trace["metadata"]["failure_reason"])

    def test_two_distinct_original_d4_saddle_witnesses(self):
        domain = two_saddles()
        self.assertEqual(domain["arrays"]["internal_faces"].tolist(), [[9, 10], [16, 17]])
        self.assertEqual(domain["arrays"]["internal_crest_m"].tolist(), [1., 1.])

    def test_wet_component_uses_each_face_cell_wetness(self):
        from scipy.ndimage import label
        from terrain_pipeline.lake import _wet_state as _wet_state
        domain = two_lakes()
        wet, labels = _wet_state(domain["arrays"], np.array([1.1, .1]))
        a = domain["arrays"]
        owner = a["owner_grid"]
        stages = np.array([1.1, .1])
        reference_wet = (owner >= 0) & (a["source_height_m"] < stages[np.maximum(owner, 0)])
        connected, _ = label(reference_wet, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
        self.assertEqual(connected[2, 2], connected[2, 3])
        np.testing.assert_array_equal(wet, reference_wet.ravel()[a["support_cell_ids"]])
        self.assertTrue(np.array_equal(labels, np.array([0, 0], np.int64)))

    def test_failure_prefix_stops_at_capacity_event(self):
        domain = two_lakes()
        trace = solve_natural_lakes(domain, np.array([0., 100.]),
                                    np.array([[100., 0.]]), np.zeros(2),
                                    np.zeros((1, 1)), forcing_provenance="overfill witness")
        self.assertEqual(trace["metadata"]["status"], "failed_prefix")
        self.assertTrue(any(token in trace["metadata"]["failure_reason"]
                            for token in ("capacity", "unresolved exterior")))
        self.assertLess(trace["arrays"]["time_seconds"][-1], 100.)
        self.assertTrue(validate_natural_lakes(trace))

    def test_original_bed_faces_prism_volume_and_unknown_block(self):
        domain = two_lakes(unknown=True)
        self.assertTrue(validate_natural_lakes(domain))
        a = domain["arrays"]
        self.assertEqual(a["internal_faces"].tolist(), [[16, 17]])
        self.assertEqual(a["internal_crest_m"].tolist(), [1.])
        self.assertGreater(domain["metadata"]["unresolved_exterior_faces"], 0)
        self.assertFalse(domain["metadata"]["natural_boundary_certified"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "domain.npz"
            save_natural_lakes(path, domain)
            loaded = load_natural_lakes(path, expected_sha256=file_sha256(path),
                                        expected_identity=domain["identity_sha256"])
        self.assertEqual(loaded["identity_sha256"], domain["identity_sha256"])

    def test_pair_transfer_merges_and_retreat_separates_without_duplicate_stock(self):
        domain = two_lakes()
        trace = solve_natural_lakes(
            domain, np.array([0., 3., 20.]),
            np.array([[7., 0.], [0., 0.]]), np.array([0., 0.]),
            np.zeros((2, 1)), config=NaturalLakeConfig(max_step_seconds=.1),
            forcing_provenance="explicit analytical inflow")
        self.assertEqual(trace["metadata"]["status"], "complete")
        self.assertTrue(validate_natural_lakes(trace))
        a = trace["arrays"]
        self.assertAlmostEqual(a["volume_m3"][-1].sum(), 21., places=6)
        self.assertGreater(a["internal_transfer_m3"][-1, 0], 0.)
        self.assertTrue(np.any(a["wet_component"][:, 0] == a["wet_component"][:, 1]))
        self.assertTrue(np.any(a["wet_component"][:, 0] != a["wet_component"][:, 1]))
        self.assertTrue(np.all(a["wet_support"] == (a["domain_source_height_m"].ravel()[a["domain_support_cell_ids"]][None, :]
                                                        < a["stage_m"][:, a["domain_owner_grid"].ravel()[a["domain_support_cell_ids"]]])))

    def test_tailwater_reversal_and_free_outflow_no_inflow(self):
        for kind in ("tailwater", "free_outflow"):
            with self.subTest(kind=kind):
                domain = two_lakes(boundary_kind=kind)
                trace = solve_natural_lakes(
                    domain, np.array([0., 2.]), np.zeros((1, 2)),
                    np.zeros(2), np.array([[6.]]),
                    config=NaturalLakeConfig(max_step_seconds=.1),
                    forcing_provenance="specified tailwater")
                if kind == "tailwater":
                    self.assertLess(trace["arrays"]["boundary_transfer_m3"][-1, 0], 0.)
                else:
                    self.assertEqual(trace["arrays"]["boundary_transfer_m3"][-1, 0], 0.)

    def test_cold_validator_rejects_rehashed_ledger_and_wet_forgery(self):
        domain = two_lakes()
        trace = solve_natural_lakes(domain, np.array([0., 1.]),
                                    np.array([[1., 0.]]), np.zeros(2),
                                    np.zeros((1, 1)), forcing_provenance="test supply")
        for field in ("volume_m3", "wet_support", "internal_q_m3_s"):
            forged = deepcopy(trace)
            forged["arrays"][field] = forged["arrays"][field].copy()
            if forged["arrays"][field].dtype == bool:
                forged["arrays"][field][-1, 0] ^= True
            else:
                forged["arrays"][field][-1, 0] += .01
            forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
            with self.assertRaises(ValueError):
                validate_natural_lakes(forged)


if __name__ == "__main__":
    unittest.main()
