from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_coastal_delta import (
    load_coastal_delta, prepare_coastal_delta, run_coastal_delta, save_coastal_delta,
    continue_coastal_delta,
)
from terrain_pipeline.environment_product import context_from_store
from terrain_pipeline.environment_regional_hydraulics import prepare_from_context, advance, _digest


STORE = Path(__file__).resolve().parents[1] / ".scratch/river-generation-review/real-coastal"


@unittest.skipUnless((STORE / "registry.json").exists(), "saved coastal TD unavailable")
class CoastalDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = prepare_coastal_delta(STORE)
        ctx, source = context_from_store(STORE, 0, 168, 33)
        rows, cols = np.indices((33, 33))
        ids = (rows * 256 + cols + 168).astype(np.int64)
        regions = prepare_from_context(ctx, source, ids, selected_nodes=[609, 608])
        regions = advance(regions, 30.)
        mouth = next(key for key, value in regions.items() if value["metadata"]["target_node"] == 4534)
        cls.packets = regions[mouth]["metadata"]["exports"]
        second = advance(regions, 30.)
        cls.extended_packets = second[mouth]["metadata"]["exports"]
        cls.result = run_coastal_delta(cls.prepared, cls.packets)
        cls.control = run_coastal_delta(cls.prepared, cls.packets, zero_sediment_control=True)

    def test_actual_debited_solver_packet_reaches_same_mouth(self):
        p = self.packets[0]
        self.assertGreater(p["water_m3"], 0.)
        self.assertGreater(p["solid_m3"], 0.)
        self.assertEqual(p["target_node"], 4534)
        self.assertIn("hydraulic_identity", p)
        self.assertIn("sediment_identity", p)
        r = self.result
        self.assertEqual(r["metadata"]["solid_ledger"]["input_solid_m3"], p["solid_m3"])
        self.assertGreater(r["metadata"]["solid_ledger"]["deposited_solid_m3"], 0.)
        self.assertLess(abs(r["metadata"]["solid_ledger"]["residual_solid_m3"]), 1e-10)
        self.assertTrue(np.all(r["arrays"]["branch_q_m3_s"] > 0.))
        self.assertEqual(r["metadata"]["construction_budget"]["excavated_solid_m3"], 0.)

    def test_same_q_zero_solid_adds_no_bed(self):
        np.testing.assert_array_equal(self.control["arrays"]["height_delta_m"], 0.)
        self.assertEqual(self.control["metadata"]["marine_ledger"]["river_water_input_m3"],
                         self.result["metadata"]["marine_ledger"]["river_water_input_m3"])
        self.assertGreater(self.result["arrays"]["height_delta_m"].max(), 0.)
        np.testing.assert_array_equal(self.prepared["arrays"]["bed_m"], self.result["arrays"]["initial_bed_m"])

    def test_cold_bundle_preserves_derived_bed_branches_and_water_heat_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delta.npz"
            save_coastal_delta(path, self.result)
            cold = load_coastal_delta(path, expected_sha256=file_sha256(path))
            self.assertEqual(cold["identity_sha256"], self.result["identity_sha256"])
            np.testing.assert_array_equal(cold["arrays"]["final_bed_m"], self.result["arrays"]["final_bed_m"])
            with self.assertRaises(ValueError):
                cold["arrays"]["final_bed_m"].setflags(write=True)
            with self.assertRaises(FileExistsError):
                save_coastal_delta(path, self.result)
        ledger = self.result["metadata"]["marine_ledger"]
        self.assertLess(abs(ledger["water_residual_m3"]), 1e-5)
        self.assertLess(abs(ledger["heat_residual_m3_degc"]), 1e-3)

    def test_duplicate_foreign_world_and_wrong_receiver_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            run_coastal_delta(self.prepared, self.packets * 2)
        for field, value in (("source_world_identity", "foreign-world"), ("target_node", 0)):
            bad = deepcopy(self.packets[0])
            bad[field] = value
            bad["packet_id"] = _digest({key: value for key, value in bad.items() if key != "packet_id"})
            with self.assertRaises(ValueError):
                run_coastal_delta(self.prepared, [bad])

    def test_saved_continue_matches_single_batch_and_never_deposits_old_sediment_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "delta.npz"
            save_coastal_delta(path, self.result)
            cold = load_coastal_delta(path, expected_sha256=file_sha256(path))
            continued = continue_coastal_delta(cold, self.extended_packets[1:])
        whole = run_coastal_delta(self.prepared, self.extended_packets)
        self.assertEqual(continued["identity_sha256"], whole["identity_sha256"])
        np.testing.assert_array_equal(continued["arrays"]["final_bed_m"], whole["arrays"]["final_bed_m"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            continue_coastal_delta(self.result, self.packets)
        with self.assertRaisesRegex(ValueError, "diagnostic"):
            continue_coastal_delta(self.control, self.extended_packets[1:])


if __name__ == "__main__":
    unittest.main()
