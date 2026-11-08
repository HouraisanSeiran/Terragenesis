import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.surface_rivers.metric_fluvial_delta import simulate_fluvial_delta
from tools.verify_fluvial_channel_remobilization import audit_archive, channel_evidence, refine, refined_origin, save_archive, synthetic_input


class RemobilizationArchiveTests(unittest.TestCase):
    def fixture(self, path):
        terrain, boundary, forcing, config, source, raw = synthetic_input()
        result = simulate_fluvial_delta(terrain, boundary, forcing, config)
        save_archive(path, terrain, boundary, forcing, result, source, raw)
        return result

    def test_cold_audit_independent_inventory_and_material_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"delta.npz"
            result = self.fixture(path)
            self.assertGreater(result["reentrained_solid_m3"].sum(), 0.)
            with patch("tools.verify_fluvial_channel_remobilization.simulate_fluvial_delta", side_effect=AssertionError("generator called")):
                report = audit_archive(path)
            self.assertTrue(report["passed"])
            completed = subprocess.run([sys.executable, "tools/verify_fluvial_channel_remobilization.py", "--audit", str(path)], capture_output=True, text=True, check=True)
            self.assertTrue(json.loads(completed.stdout)["passed"])

    def test_tampered_inventory_bed_flux_erosion_and_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"delta.npz"
            self.fixture(path)
            with np.load(path, allow_pickle=False) as archive:
                original = {key: archive[key].copy() for key in archive.files}
            for key in ("storage", "beds_m", "height_delta_m", "reentrainment", "reentrained_solid_m3", "water", "sediment", "edge_volumes", "stored_solid_m3"):
                arrays = {name: value.copy() for name, value in original.items()}
                arrays[key].flat[0] += 1.
                bad = Path(directory)/(key+".npz")
                np.savez_compressed(bad, **arrays)
                with self.subTest(key=key), self.assertRaises((ValueError, AssertionError)):
                    audit_archive(bad)
            arrays = {name: value.copy() for name, value in original.items()}
            meta = json.loads(str(arrays["metadata_json"].item()))
            meta["solid_ledger"]["reentrained_solid_m3"] += 1.
            arrays["metadata_json"] = np.array(json.dumps(meta))
            bad = Path(directory)/"ledger.npz"
            np.savez_compressed(bad, **arrays)
            with self.assertRaises(AssertionError):
                audit_archive(bad)

    def test_refinement_preserves_classification_and_original_support_range(self):
        bed = np.array([[2., -10.], [3., -20.]])
        ocean = bed < 0.
        fine, labels = refine(bed, ocean, 6)
        np.testing.assert_array_equal(labels, np.repeat(np.repeat(ocean, 6, axis=0), 6, axis=1))
        self.assertTrue(np.all(fine[labels] <= -10.))
        self.assertTrue(np.all(fine[~labels] >= 2.))
        self.assertEqual(fine.shape, (12,12))

    def test_refined_sample_coordinates_match_interpolation_positions(self):
        x0, z0 = refined_origin((100., 200.), (2, 4, 3, 5), 6)
        self.assertEqual((x0, z0), (177.5, 247.5))
        for fine_index in (0, 3, 6, 11):
            coarse_position = (fine_index+.5)/6-.5
            self.assertAlmostEqual(x0+fine_index*5., 190.+coarse_position*30.)

    def test_closed_zero_water_deposition_forgery_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            terrain, boundary, forcing, config, source, raw = synthetic_input()
            forcing = (replace(forcing[0], water_volume_m3=0.),)
            result = simulate_fluvial_delta(terrain, boundary, forcing, config)
            path = Path(directory)/"zero.npz"
            save_archive(path, terrain, boundary, forcing, result, source, raw)
            self.assertTrue(audit_archive(path)["passed"])
            with np.load(path, allow_pickle=False) as archive:
                a = {key: archive[key].copy() for key in archive.files}
            cell = forcing[0].inlet_cell
            for key in ("deposited_solid_m3", "stored_solid_m3"):
                a[key][cell] += .1
            for key in ("deposits", "storage"):
                a[key][(0,)+cell] += .1
            for key in ("final_bed_m", "height_delta_m"):
                a[key][cell] += .1/.65
            a["beds_m"][(0,)+cell] += .1/.65
            meta = json.loads(str(a["metadata_json"].item()))
            for ledger in (meta["solid_ledger"], meta["interval_ledgers"][0]["solid"]):
                ledger.update(deposited_solid_m3=.1, stored_solid_m3=.1, deposit_bulk_m3=.1/.65, stored_bulk_m3=.1/.65, unresolved_solid_m3=7.9)
            a["metadata_json"] = np.array(json.dumps(meta))
            bad = Path(directory)/"forged.npz"
            np.savez_compressed(bad, **a)
            with self.assertRaises(AssertionError):
                audit_archive(bad)

    def test_alternating_ridges_are_not_transverse_channel_evidence(self):
        final = np.array([[2.,-1.,2.,-1.,2.], [1.,0.,1.,0.,1.], [2.,-1.,2.,-1.,2.]])
        ocean, water = np.zeros(final.shape, bool), np.zeros((2,)+final.shape)
        ocean[1,4], water[1,1,:] = True, 1.
        a = {"initial_bed_m": final-.1, "final_bed_m": final, "beds_m": np.stack([final+.02,final]), "water": water, "ocean_mask": ocean}
        m = {"forcing": [{"inlet_cell": [1,0], "sediment_solid_m3": 1.}, {"inlet_cell": [1,0], "sediment_solid_m3": 0.}]}
        self.assertFalse(channel_evidence(a,m)["continuous_incised_channel"])

    def test_zero_input_cyclic_ghost_flux_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            terrain, boundary, forcing, config, source, raw = synthetic_input()
            forcing = (replace(forcing[0], water_volume_m3=0., sediment_solid_m3=0.),)
            result = simulate_fluvial_delta(terrain, boundary, forcing, config)
            path = Path(directory)/"zero.npz"
            save_archive(path, terrain, boundary, forcing, result, source, raw)
            with np.load(path, allow_pickle=False) as archive:
                a = {key: archive[key].copy() for key in archive.files}
            a.update(edge_cells=np.array([[6,0,6,1], [6,1,6,0]]), edge_volumes=np.array([[1.,0.],[1.,0.]]), edge_offsets=np.array([0,2]))
            a["water"][0,6,0:2] = 1.
            bad = Path(directory)/"cycle.npz"
            np.savez_compressed(bad, **a)
            with self.assertRaises(ValueError):
                audit_archive(bad)


if __name__ == "__main__":
    unittest.main()
