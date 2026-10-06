import copy
import unittest

from tools.audit_usgs_channel_reference import reduce_measurements


class UsgsChannelReferenceTests(unittest.TestCase):
    def setUp(self):
        self.values = dict(type="FeatureCollection", features=[dict(type="Feature", geometry=dict(type="Point", coordinates=[-105., 39.]),
            properties=dict(monitoring_location_id="USGS-06719505", measurement_number="1", time="2000-01-01T00:00:00Z",
                channel_name="Main", channel_flow="100", channel_flow_unit="ft^3/s", channel_width="20", channel_width_unit="ft",
                channel_area="50", channel_area_unit="ft^2", channel_velocity="2", channel_velocity_unit="ft/s"))])

    def test_exact_si_and_derived_mean_depth(self):
        result = reduce_measurements(self.values, "USGS-06719505")
        row = result["retained_measurements"][0]
        self.assertAlmostEqual(row["measured_si"]["channel_flow"], 2.8316846592)
        self.assertAlmostEqual(row["derived_mean_depth_m"], .762)
        self.assertAlmostEqual(row["derived_area_velocity_to_discharge_ratio"], 1.)
        self.assertFalse(result["calibration_performed"])

    def test_missing_quantity_is_omitted_without_invention(self):
        self.values["features"][0]["properties"]["channel_area"] = ""
        result = reduce_measurements(self.values, "USGS-06719505")
        self.assertEqual(result["retained_measurements"], [])
        self.assertEqual(len(result["omitted_measurements"]), 1)

    def test_unit_and_station_mismatch_rejected(self):
        changed = copy.deepcopy(self.values)
        changed["features"][0]["properties"]["channel_flow_unit"] = "m3/s"
        with self.assertRaisesRegex(ValueError, "unit"):
            reduce_measurements(changed, "USGS-06719505")
        with self.assertRaisesRegex(ValueError, "station"):
            reduce_measurements(self.values, "USGS-00000000")


if __name__ == "__main__":
    unittest.main()
