"""Complete real TD contribution groups, safe static pool equations and refusals."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import terrain_pipeline.lake as geometry
import terrain_pipeline.lake as pools
from terrain_pipeline.lake import first_lake_ownership as first_lake_ownership
from tools.verify_mountain_rainfall import load_source, response_units


class MountainPoolNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_source("normal_mountain")
        cls.geometry = geometry.prepare_mountain_geometry(source["height_m"], spacing_m=30.,
            origin_m_xz=source["origin_m_xz"], source_binding={"mountain": "normal_mountain"},
            boundary_mask=geometry.window_boundary(source["height_m"].shape),
            protected_mask=np.zeros(source["height_m"].shape, dtype=bool))
        screening = geometry.screen_single_pool_lakes(cls.geometry, min_cells=1)
        cls.proposals = pools.screen_complete_pool_groups(cls.geometry, screening)
        cls.proposal = next(item for item in cls.proposals["groups"] if item["status"] == "static_complete_pool_candidate")
        owner, area, *_ = response_units(source["height_m"], 30.)
        cls.owner = owner.astype(np.int64)
        cls.area = area
        cls.forcing = np.full((48, area.size), .002, dtype=np.float64)

    def run_case(self, proposal=None, forcing=None):
        return pools.route_complete_pool_group(self.geometry, proposal or self.proposal,
            local_q_m3_s=self.forcing if forcing is None else forcing,
            cell_owner=self.owner, hru_area_m2=self.area)

    def test_complete_real_area_and_no_cut_construction_independent(self):
        result = self.run_case()
        self.assertEqual(result["status"], "complete_pool_group_feasible")
        arrays = result["arrays"]
        self.assertEqual(arrays["allocation_counts"].sum(), arrays["owned_mask"].sum())
        self.assertEqual(arrays["owned_mask"].sum() * 900, self.proposal["area_m2"])
        self.assertFalse(self.geometry["arrays"]["accepted_mask"][arrays["owned_mask"]].any())
        self.assertTrue((arrays["storage_m3"][0] == 0).all())
        evidence = pools.validate_complete_pool_group(result, self.geometry,
            local_q_m3_s=self.forcing, cell_owner=self.owner, hru_area_m2=self.area)
        self.assertLess(evidence["max_joint_residual_m3"], 1.1e-6)

    def test_weir_limit_refuses_extreme_rain_not_retuned(self):
        forcing = np.ones_like(self.forcing) * 1e5
        result = self.run_case(forcing=forcing)
        self.assertEqual(result["status"], "complete_pool_group_refused")
        self.assertEqual(result["completed_steps"], 0)
        self.assertEqual(result["failures"][0]["code"], "valid_shore_headroom_exceeded")
        self.assertEqual(result["weir_coefficient"], 1.7)

    def test_internal_cascade_release_injected_once(self):
        proposal = next(item for item in self.proposals["groups"]
                        if item["status"] == "static_complete_pool_candidate" and len(item["lake_ids"]) > 1)
        result = self.run_case(proposal=proposal)
        arrays = result["arrays"]
        expected = np.zeros_like(arrays["upstream_volume_m3"])
        for index, target in enumerate(arrays["pool_downstream"]):
            if target >= 0:
                expected[:, target] += arrays["outflow_volume_m3"][:, index]
        np.testing.assert_allclose(arrays["upstream_volume_m3"], expected, rtol=0., atol=0.)
        self.assertEqual(arrays["allocation_counts"].sum(), arrays["owned_mask"].sum())

    def test_cold_pool_load_never_advances_or_rebuilds(self):
        result = self.run_case()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pool.npz"
            pools.save_pool_group(path, result, self.geometry, local_q_m3_s=self.forcing,
                                  cell_owner=self.owner, hru_area_m2=self.area)
            with patch.object(pools, "route_complete_pool_group", side_effect=AssertionError("route")), \
                 patch.object(pools, "screen_complete_pool_groups", side_effect=AssertionError("screen")), \
                 patch.object(pools, "first_lake_ownership", side_effect=AssertionError("assemble")):
                loaded = pools.load_pool_group(path, self.geometry, local_q_m3_s=self.forcing,
                    cell_owner=self.owner, hru_area_m2=self.area)
            self.assertEqual(loaded["status"], result["status"])
            self.assertFalse(loaded["arrays"]["stage_m"].flags.writeable)
            with self.assertRaises(FileExistsError):
                pools.save_pool_group(path, result, self.geometry, local_q_m3_s=self.forcing,
                                      cell_owner=self.owner, hru_area_m2=self.area)

    def test_static_semantic_checks_refuse_compensated_water_forgery(self):
        saved = self.run_case()
        forged = deepcopy(saved)
        forged["arrays"]["storage_m3"][1, 0] += 1.
        forged["arrays"]["external_outflow_volume_m3"][0] -= 1.
        with self.assertRaises(ValueError):
            pools.validate_complete_pool_group(forged, self.geometry, local_q_m3_s=self.forcing,
                cell_owner=self.owner, hru_area_m2=self.area)
        forged = deepcopy(saved)
        forged["weir_coefficient"] = 1000.
        with self.assertRaises(ValueError):
            pools.validate_complete_pool_group(forged, self.geometry, local_q_m3_s=self.forcing,
                cell_owner=self.owner, hru_area_m2=self.area)

    def test_first_lake_mapping_contains_all_lake_and_hillslope_cells(self):
        first = first_lake_ownership(self.geometry)
        labels = self.geometry["arrays"]["lake_id"]
        np.testing.assert_array_equal(first[labels > 0], labels[labels > 0])
        receiver = self.geometry["arrays"]["receiver"]
        dry = np.flatnonzero((labels.ravel() == 0) & (receiver >= 0))
        np.testing.assert_array_equal(first.ravel()[dry], first.ravel()[receiver[dry]])

    def test_invalid_dt_area_and_complete_owner_refused(self):
        for dt in (0., -1., float("nan"), True):
            with self.assertRaises(ValueError):
                pools.route_complete_pool_group(self.geometry, self.proposal, local_q_m3_s=self.forcing,
                    cell_owner=self.owner, hru_area_m2=self.area, dt_s=dt)
        forged_area = self.area.copy()
        forged_area[0] += 900
        with self.assertRaises(ValueError):
            pools.route_complete_pool_group(self.geometry, self.proposal, local_q_m3_s=self.forcing,
                cell_owner=self.owner, hru_area_m2=forged_area)
        forged_owner = self.owner.copy()
        forged_owner[0, 0] = -1
        with self.assertRaises(ValueError):
            pools.route_complete_pool_group(self.geometry, self.proposal, local_q_m3_s=self.forcing,
                cell_owner=forged_owner, hru_area_m2=self.area)

    def test_caller_approved_shore_and_success_labels_cannot_bypass_gates(self):
        saved = self.run_case()
        forged = deepcopy(saved)
        lake = str(saved["proposal"]["lake_ids"][0])
        forged["proposal"]["max_head_m"][lake] = 1000.
        with self.assertRaises(ValueError):
            pools.validate_complete_pool_group(forged, self.geometry, local_q_m3_s=self.forcing,
                cell_owner=self.owner, hru_area_m2=self.area)
        forged = deepcopy(saved)
        forged["completed_steps"] -= 1
        with self.assertRaises(ValueError):
            pools.validate_complete_pool_group(forged, self.geometry, local_q_m3_s=self.forcing,
                cell_owner=self.owner, hru_area_m2=self.area)


if __name__ == "__main__":
    unittest.main()
