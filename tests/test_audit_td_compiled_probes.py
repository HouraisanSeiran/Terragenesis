import unittest

import numpy as np

from tools.audit_td_compiled_probes import compare_fields


class IndependentCompiledProbeTests(unittest.TestCase):
    def test_physical_state_units_and_static_mapping_are_distinct(self):
        expected = dict(depth_m=np.array([1.]), soil_mm=np.array([10.]),
            receiver=np.array([-1], np.int64), face_forward_m3=np.array([100.]), active_forward_s=np.array([30.]))
        actual = {name: values.copy() for name, values in expected.items()}
        actual["soil_mm"] += 5e-10
        self.assertLess(compare_fields(actual, expected)["soil_mm"]["max_difference"], 1e-9)
        actual["receiver"][0] = 0
        with self.assertRaises(ValueError):
            compare_fields(actual, expected)

    def test_shape_dtype_nonfinite_and_omitted_field_rejected(self):
        expected = dict(depth_m=np.array([1., 2.]))
        for actual in (dict(), dict(depth_m=np.array([1.])), dict(depth_m=np.array([1., 2.], np.float32)),
                       dict(depth_m=np.array([1., np.nan]))):
            with self.assertRaises(ValueError):
                compare_fields(actual, expected)

    def test_depth_compensation_and_activity_original_thresholds(self):
        for name, difference in (("depth_m", 2e-12), ("error_soil", 2e-9), ("active_reverse_s", 2e-8)):
            with self.assertRaises(ValueError):
                compare_fields({name: np.array([1. + difference])}, {name: np.array([1.])})


if __name__ == "__main__":
    unittest.main()
