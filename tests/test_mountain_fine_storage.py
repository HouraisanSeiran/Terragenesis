"""Source-bound fine storage, real interface sills and signed wet/dry flux."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import terrain_pipeline.lake as geometry
from terrain_pipeline import channel_geometry as fine
from terrain_pipeline import channel_geometry as storage
from tools.verify_mountain_rainfall import load_source


class MountainFineStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = load_source("normal_mountain")
        cls.geometry = geometry.prepare_mountain_geometry(source["height_m"], spacing_m=30.,
            origin_m_xz=source["origin_m_xz"], source_binding={"mountain": "normal_mountain"},
            boundary_mask=geometry.window_boundary(source["height_m"].shape),
            protected_mask=np.zeros(source["height_m"].shape, dtype=bool))
        cls.chain = fine.select_continuous_fine_geometry(cls.geometry)["accepted"]
        cls.support = storage.fine_storage_support(cls.chain)

    def run_case(self, *, initial=None, upstream=None, tailwater=None, dt=10., steps=60, local=None):
        level = float(self.support["max_stage_m"].min() - .02)
        if initial is None:
            initial = np.maximum(self.support["min_bed_m"], level)
        return storage.prepare_fine_storage(self.chain, self.geometry, initial_stage_m=initial,
            local_q_m3_s=np.zeros((steps, 4)) if local is None else local,
            upstream_stage_m=np.full(steps + 1, level) if upstream is None else upstream,
            tailwater_stage_m=np.full(steps + 1, level) if tailwater is None else tailwater,
            dt_s=dt)

    def test_partial_wet_static_water_is_exact_and_higher_bed_remains_dry(self):
        result = self.run_case()
        self.assertEqual(result["status"], "fine_storage_completed")
        arrays = result["arrays"]
        self.assertEqual(np.max(np.abs(arrays["qedges_m3_s"])), 0.)
        np.testing.assert_array_equal(arrays["stage_m"][-1], arrays["stage_m"][0])
        self.assertTrue((arrays["storage_m3"][0] == 0).any())
        self.assertTrue((arrays["storage_m3"][0] > 0).any())
        storage.validate_fine_storage(result, self.chain, self.geometry)

    def test_dry_sloping_bed_cannot_create_water_or_drain_empty_donor(self):
        initial = self.support["min_bed_m"].copy()
        result = self.run_case(initial=initial,
            upstream=np.full(61, initial[0]), tailwater=np.full(61, initial[-1]))
        self.assertEqual(result["status"], "fine_storage_completed")
        self.assertEqual(result["arrays"]["storage_m3"].sum(), 0.)
        self.assertEqual(np.abs(result["arrays"]["qedges_m3_s"]).sum(), 0.)
        storage.validate_fine_storage(result, self.chain, self.geometry)

    def test_raised_tailwater_really_backflows_and_conserves_volume(self):
        initial = self.support["min_bed_m"].copy()
        tailwater = np.full(61, min(self.support["max_stage_m"][-1], initial[-1] + .08))
        result = self.run_case(initial=initial,
            upstream=np.full(61, initial[0]), tailwater=tailwater)
        self.assertEqual(result["status"], "fine_storage_completed")
        self.assertTrue((result["arrays"]["qedges_m3_s"][:, -1] < 0).all())
        self.assertGreater(result["arrays"]["storage_m3"][-1].sum(), 0.)
        self.assertLess(np.abs(result["arrays"]["ledger_m3"][:, -1]).max(), 1e-10)
        storage.validate_fine_storage(result, self.chain, self.geometry)

    def test_wet_dry_source_and_dt_sensitivity(self):
        initial = self.support["min_bed_m"].copy()
        level = initial[-1]
        cases = []
        for dt, steps in ((10., 60), (5., 120)):
            local = np.zeros((steps, 4))
            local[:, -1] = .001
            case = self.run_case(initial=initial, upstream=np.full(steps + 1, initial[0]),
                tailwater=np.full(steps + 1, level), local=local, steps=steps, dt=dt)
            self.assertEqual(case["status"], "fine_storage_completed")
            self.assertGreater(case["arrays"]["storage_m3"][-1, -1], 0.)
            storage.validate_fine_storage(case, self.chain, self.geometry)
            cases.append(case)
        relative = abs(cases[0]["arrays"]["storage_m3"][-1].sum() - cases[1]["arrays"]["storage_m3"][-1].sum()) / cases[1]["arrays"]["storage_m3"][-1].sum()
        self.assertLess(relative, .02)

    def test_bank_overtopping_is_refused_with_committed_prefix(self):
        local = np.full((60, 4), 1.)
        result = self.run_case(local=local)
        self.assertEqual(result["status"], "fine_storage_refused")
        self.assertEqual(result["failure"]["reason"], "resolved_bank_overtopped")
        self.assertLess(result["committed_steps"], 60)

    def test_static_validation_never_assembles_support_or_advances(self):
        result = self.run_case()
        with patch.object(storage, "fine_storage_support", side_effect=AssertionError("assemble")), \
             patch.object(storage, "prepare_fine_storage", side_effect=AssertionError("advance")), \
             patch.object(fine, "select_continuous_fine_geometry", side_effect=AssertionError("select")), \
             patch.object(fine, "prepare_fine_segment", side_effect=AssertionError("prepare")):
            storage.validate_fine_storage(result, self.chain, self.geometry)

    def test_source_and_arbitrary_conservative_flux_forgery_refused(self):
        saved = self.run_case()
        forged = deepcopy(saved)
        forged["arrays"]["qedges_m3_s"][:] = .0001
        with self.assertRaises(ValueError):
            storage.validate_fine_storage(forged, self.chain, self.geometry)
        forged = deepcopy(saved)
        forged["support"]["interface_sill_m"][1] -= .1
        with self.assertRaises(ValueError):
            storage.validate_fine_storage(forged, self.chain, self.geometry)
        chain = deepcopy(self.chain)
        chain["arrays"]["H0_m"][0, 0] += .1
        with self.assertRaises(ValueError):
            storage.validate_fine_storage(saved, chain, self.geometry)

    def test_true_interface_sill_is_not_minima_shortcut(self):
        true_sill = self.support["interface_sill_m"][1:-1]
        minima_shortcut = np.maximum(self.support["min_bed_m"][:-1], self.support["min_bed_m"][1:])
        self.assertTrue((true_sill >= minima_shortcut).all())
        bed = self.chain["arrays"]["H2_m"]
        rows = self.support["interface_before_rows"]
        np.testing.assert_array_equal(true_sill, np.maximum(bed[rows].min(axis=1), bed[rows + 1].min(axis=1)))

    def test_atomic_cold_load_and_resigned_semantic_attack(self):
        saved = self.run_case()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fine.npz"
            storage.save_fine_storage(path, saved, self.chain, self.geometry)
            with patch.object(storage, "fine_storage_support", side_effect=AssertionError("assemble")), \
                 patch.object(storage, "prepare_fine_storage", side_effect=AssertionError("advance")):
                loaded = storage.load_fine_storage(path, self.chain, self.geometry)
            self.assertFalse(loaded["arrays"]["stage_m"].flags.writeable)
            with self.assertRaises(FileExistsError):
                storage.save_fine_storage(path, saved, self.chain, self.geometry)
            with np.load(path, allow_pickle=False) as archive:
                payload = {key: archive[key].copy() for key in archive.files}
            import json
            manifest = json.loads(payload["manifest"].tobytes().decode("ascii"))
            payload["state__ledger_m3"][0, 1] += 1.
            manifest["hashes"]["state__ledger_m3"] = storage._i7__hash(payload["state__ledger_m3"])
            payload["manifest"] = np.frombuffer(storage._i7__json(manifest).encode("ascii"), dtype=np.uint8)
            forged = Path(directory) / "resigned.npz"
            np.savez_compressed(forged, **payload)
            with self.assertRaises(ValueError):
                storage.load_fine_storage(forged, self.chain, self.geometry)

    def test_status_initial_stage_and_ledger_are_not_caller_certificates(self):
        saved = self.run_case()
        for mutation in (
            lambda item: item["arrays"]["initial_stage_m"].__setitem__(0, item["arrays"]["initial_stage_m"][0] + .01),
            lambda item: item.__setitem__("status", "fine_storage_refused"),
            lambda item: item["arrays"]["ledger_m3"].__setitem__((0, 1), 1.),
            lambda item: item["support"]["side_margin_m"].__setitem__(0, 100.),
        ):
            forged = deepcopy(saved)
            mutation(forged)
            with self.assertRaises(ValueError):
                storage.validate_fine_storage(forged, self.chain, self.geometry)


if __name__ == "__main__":
    unittest.main()
