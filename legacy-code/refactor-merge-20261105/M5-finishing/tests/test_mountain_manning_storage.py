"""Real source sections and bounded engineering diffusive flow gates."""

from copy import deepcopy
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline.lake import load_mountain_geometry as load_mountain_geometry
from terrain_pipeline.channel_geometry import prepare_tributary_geometry, section_hydraulics
from terrain_pipeline import channel_geometry as storage
from terrain_pipeline.common_infra import load_legacy_source
from terrain_pipeline.common_infra import file_sha256


class MountainManningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_legacy_source("pressure_mountain", boundary_policy="all_edges_open")
        path = Path("verification/mountain-lake-coupling/frozen-20261001-A-v3/pressure_mountain-geometry.npz")
        cls.geometry = load_mountain_geometry(path, trusted_height=source["arrays"]["height_m"],
            source_binding={"source_identity": source["identity_sha256"]})
        cls.record = prepare_tributary_geometry(cls.geometry)

    def run_case(self, q=0., tail_raise=0., dt=30., steps=20):
        initial = self.record["arrays"]["min_bed_m"].copy()
        return storage.prepare_manning_storage(self.record, self.geometry, initial_stage_m=initial,
            inlet_q_m3_s=np.full(steps, q), lateral_q_m3_s=np.zeros((steps, 4)),
            tailwater_stage_m=np.full(steps + 1, initial[-1] + tail_raise), dt_s=dt)

    def test_analytical_v_section(self):
        result = section_hydraulics(np.array([-1., 0., 1.]), np.array([1., 0., 1.]), .5)
        self.assertAlmostEqual(result["area_m2"], .25)
        self.assertAlmostEqual(result["wetted_perimeter_m"], np.sqrt(2))
        self.assertAlmostEqual(result["top_width_m"], 1.)

    def test_dry_no_creation_and_static_validation_no_solver(self):
        saved = self.run_case()
        self.assertEqual(saved["metadata"]["status"], "completed")
        self.assertEqual(saved["arrays"]["storage_m3"].sum(), 0.)
        with patch.object(storage, "prepare_manning_storage", side_effect=AssertionError), patch.object(storage, '_i11_least_squares', side_effect=AssertionError):
            storage.validate_manning_storage(saved, self.record, self.geometry)

    def test_true_backflow(self):
        saved = self.run_case(tail_raise=.08)
        self.assertEqual(saved["metadata"]["status"], "completed")
        self.assertLess(saved["arrays"]["qedges_m3_s"][:, -1].sum(), 0.)
        self.assertGreater(saved["arrays"]["storage_m3"][-1].sum(), 0.)

    def test_partial_wet_equilibrium_exact(self):
        level = float(self.record["arrays"]["max_stage_m"].min() - .02)
        initial = np.maximum(level, self.record["arrays"]["min_bed_m"])
        saved = storage.prepare_manning_storage(self.record, self.geometry, initial_stage_m=initial,
            inlet_q_m3_s=np.zeros(20), lateral_q_m3_s=np.zeros((20, 4)),
            tailwater_stage_m=np.full(21, level), dt_s=30.)
        self.assertEqual(saved["metadata"]["status"], "completed")
        self.assertEqual(np.abs(saved["arrays"]["qedges_m3_s"]).sum(), 0.)
        np.testing.assert_array_equal(saved["arrays"]["stage_m"], np.tile(initial, (21, 1)))
        self.assertTrue((saved["arrays"]["storage_m3"][0] == 0).any())
        self.assertTrue((saved["arrays"]["storage_m3"][0] > 0).any())

    def test_bank_refusal_and_budget_prefix(self):
        saved = self.run_case(q=2.)
        self.assertEqual(saved["metadata"]["status"], "refused")
        with patch.object(storage, "MAX_EVALUATIONS", 10):
            saved = self.run_case()
            self.assertEqual(saved["metadata"]["committed_steps"], 5)
            self.assertEqual(saved["metadata"]["failure"]["reason"], "residual_evaluation_budget_exhausted")

    def test_forgeries_and_negative_forcing(self):
        saved = self.run_case()
        for mutate in (lambda item: item["metadata"].update(status="unknown"),
                       lambda item: item["arrays"]["inlet_q_m3_s"].fill(-1.),
                       lambda item: item["arrays"]["qedges_m3_s"].fill(.1)):
            forged = deepcopy(saved)
            mutate(forged)
            with self.assertRaises(ValueError):
                storage.validate_manning_storage(forged, self.record, self.geometry)

    def test_dt_sensitivity_same_input_volume(self):
        coarse = self.run_case(q=.01, steps=40)
        fine = self.run_case(q=.01, dt=15., steps=80)
        self.assertEqual(coarse["metadata"]["status"], "completed")
        self.assertEqual(fine["metadata"]["status"], "completed")
        self.assertLess(abs(coarse["arrays"]["storage_m3"][-1].sum() - fine["arrays"]["storage_m3"][-1].sum()), .01)

    def test_archive_cold_load_no_clobber_and_external_forcing(self):
        saved = self.run_case(q=.01)
        forcing = {key: saved["arrays"][key] for key in
            ("initial_stage_m", "inlet_q_m3_s", "lateral_q_m3_s", "tailwater_stage_m")}
        forcing["dt_s"] = 30.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.npz"
            storage.save_manning_storage(path, saved, self.record, self.geometry)
            with self.assertRaises(FileExistsError):
                storage.save_manning_storage(path, saved, self.record, self.geometry)
            with patch.object(storage, "prepare_manning_storage", side_effect=AssertionError), patch.object(storage, '_i11_least_squares', side_effect=AssertionError):
                storage.load_manning_storage(path, self.record, self.geometry,
                    expected_sha256=file_sha256(path), trusted_forcing=forcing)
            changed = deepcopy(forcing)
            changed["inlet_q_m3_s"] *= 2
            with self.assertRaises(ValueError):
                storage.load_manning_storage(path, self.record, self.geometry,
                    expected_sha256=file_sha256(path), trusted_forcing=changed)

    def test_mesh_saved_water_and_forgery(self):
        from terrain_pipeline.channel_geometry import export_manning_mesh, validate_manning_mesh
        saved = self.run_case(tail_raise=.08)
        mesh = export_manning_mesh(self.record, saved, self.geometry)
        stats = validate_manning_mesh(mesh, self.record, saved, self.geometry)
        self.assertEqual(stats["minimum_normal_Y"], 1.)
        forged = deepcopy(mesh)
        forged["arrays"]["water_depth_m"] += .01
        with self.assertRaises(ValueError):
            validate_manning_mesh(forged, self.record, saved, self.geometry)

    def test_any_interval_capacity_detects_overload_after_early_dry_credit(self):
        initial = self.record["arrays"]["min_bed_m"]
        q = np.r_[np.zeros(30), np.full(30, 2.)]
        limit = storage.capacity_bound(self.record, inlet_q_m3_s=q, lateral_q_m3_s=np.zeros((60, 4)),
            tailwater_stage_m=np.full(61, initial[-1]), dt_s=30.)
        self.assertIsNotNone(limit["any_interval_first_exceed_step"])
        self.assertGreater(limit["any_interval_drawup_m3"].max(), limit["capacity_m3"].sum())


if __name__ == "__main__":
    unittest.main()
