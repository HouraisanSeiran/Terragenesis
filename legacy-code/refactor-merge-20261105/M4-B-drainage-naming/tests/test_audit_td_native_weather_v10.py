import copy
import unittest

import numpy as np

from tools.audit_td_native_weather_v10 import audit_accounts


class IndependentV10AccountTests(unittest.TestCase):
    def setUp(self):
        self.arrays = dict(height_m=np.zeros((1, 2)), valid_mask=np.ones((1, 2), bool),
                           face_cells=np.array([[0, 1]], np.int64), boundary_cells=np.empty(0, np.int64),
                           receiver=np.array([1, -1], np.int64), depth_m=np.array([[0., 0.], [0., 0.]]),
                           soil_mm=np.array([[30., 30.], [31., 32.]]), fast_mm=np.zeros((2, 2)), slow_mm=np.zeros((2, 2)),
                           rain_mm_h=np.array([[1., 2.]]), face_forward_m3=np.zeros(1), face_reverse_m3=np.zeros(1),
                           active_forward_s=np.zeros(1), active_reverse_s=np.zeros(1), routed_volume_m3=np.zeros(2),
                           wet_duration_s=np.zeros(2))
        self.arrays.update({name: np.zeros((1, 2)) for name in ("rain_volume_m3", "rain_infiltration_m3",
            "surface_infiltration_m3", "rain_excess_m3", "soil_et_m3", "surface_et_m3", "local_release_m3",
            "percolation_m3", "internal_net_m3", "boundary_outflow_m3", "storage_change_m3",
            "balance_residual_m3", "infiltration_capacity_m3")})
        for name in ("rain_volume_m3", "rain_infiltration_m3", "storage_change_m3"):
            self.arrays[name] = np.array([[.001, .002]])
        self.arrays["infiltration_capacity_m3"][:] = .015

    def audit(self, arrays=None):
        return audit_accounts(self.arrays if arrays is None else arrays, 1., np.array([[1., 2.]]))

    def test_explicit_compartments_accept(self):
        self.assertTrue(self.audit()["budget_passed"])

    def test_total_conserved_wrong_rain_allocation_rejected(self):
        changed = copy.deepcopy(self.arrays)
        changed["rain_excess_m3"] = changed["rain_infiltration_m3"].copy()
        changed["rain_infiltration_m3"][:] = 0.
        with self.assertRaisesRegex(ValueError, "soil water"):
            self.audit(changed)

    def test_rain_cell_permutation_rejected(self):
        changed = copy.deepcopy(self.arrays)
        changed["rain_mm_h"] = changed["rain_mm_h"][:, ::-1]
        with self.assertRaisesRegex(ValueError, "rainfall slice"):
            self.audit(changed)

    def test_capacity_forgery_rejected(self):
        changed = copy.deepcopy(self.arrays)
        changed["infiltration_capacity_m3"][:] = 1.
        with self.assertRaisesRegex(ValueError, "capacity"):
            self.audit(changed)

    def test_export_off_boundary_rejected(self):
        changed = copy.deepcopy(self.arrays)
        changed["boundary_outflow_m3"][0, 0] = .001
        changed["depth_m"][0, 0] = .001
        changed["storage_change_m3"][0, 0] -= .001
        with self.assertRaisesRegex(ValueError, "undeclared export"):
            self.audit(changed)


if __name__ == "__main__":
    unittest.main()
