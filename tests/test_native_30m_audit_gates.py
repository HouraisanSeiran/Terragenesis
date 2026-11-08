import unittest
import numpy as np
from tools.audit_native_30m_bundle import gate_ledgers

def make_case():
    metadata = {"status": "complete", "intervals": [{"start_seconds": 0, "end_seconds": 3600}]}
    metadata["sediment_0"] = {"metadata": {"material": {"porosity": 0.35}}}
    arrays = {
        "time_seconds": np.array([0.0, 3600.0]),
        "material_area_m2": np.array([2.0, 3.0]),
        "node_bed_m": np.zeros((2, 2)),
        "water_volume_m3": np.zeros((2, 2)),
        "mobile_solid_m3": np.zeros((2, 2)),
        "loose_solid_m3": np.zeros((2, 2)),
        "rock_removed_m3": np.zeros((2, 2)),
    }
    m = {k: 0.0 for k in ("initial_m3", "input_m3", "export_m3", "final_m3", "residual_m3")}
    s = {k: 0.0 for k in (
        "combined_initial_m3", "external_m3", "eroded_rock_m3", "export_m3",
        "combined_final_m3", "combined_residual_m3", "mobile_only_residual_m3",
        "loose_only_residual_m3", "rock_inventory_added_m3")}
    payload = {"water": {"per_interval": [dict(m)]}, "solid": {"per_interval": [dict(s)]}}
    return metadata, arrays, payload

class TestNative30mAuditGates(unittest.TestCase):
    def test_positive(self):
        md, arr, pl = make_case()
        out = gate_ledgers(md, arr, pl)
        self.assertIs(out['passed'], True)
        self.assertEqual(out['pointwise_bed_residual_m'], [0.0])

    def test_bed_balance(self):
        for balanced in (False, True):
            with self.subTest(balanced=balanced):
                md, arr, pl = make_case()
                arr['node_bed_m'][1, 0] = 1e-4
                if balanced:
                    arr['node_bed_m'][1, 1] = -2e-4 / 3
                self.assertIs(gate_ledgers(md, arr, pl)['passed'], False)

    def test_nan_water_residual_raises(self):
        md, arr, pl = make_case()
        pl["water"]["per_interval"][0]["residual_m3"] = float("nan")
        with self.assertRaises(ValueError):
            gate_ledgers(md, arr, pl)

    def test_negative_inventory_raises(self):
        for key in ("water_volume_m3", "mobile_solid_m3", "loose_solid_m3", "rock_removed_m3"):
            with self.subTest(key=key):
                md, arr, pl = make_case()
                arr[key][0, 0] = -1.0
                with self.assertRaises(ValueError):
                    gate_ledgers(md, arr, pl)

    def test_solid_residuals_nonzero_raises(self):
        for key in ("combined_residual_m3", "mobile_only_residual_m3", "loose_only_residual_m3"):
            with self.subTest(key=key):
                md, arr, pl = make_case()
                pl["solid"]["per_interval"][0][key] = 1e-6
                with self.assertRaises(ValueError):
                    gate_ledgers(md, arr, pl)

if __name__ == "__main__":
    unittest.main()
