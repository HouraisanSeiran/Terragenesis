"""External checks for immutable-source lowland evidence and cold verification."""
import copy
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.runoff import LowlandRunoffConfig as LowlandRunoffConfig
from terrain_pipeline.runoff import classify_and_route as classify_and_route
from tools.review_td_lowland_runoff import cold_audit, cold_weather_audit, generate_weather, network_metrics, product_identity, sample_monthly_precipitation
from tools.review_large_td_confluence import accumulate, topology


class LowlandReviewTests(unittest.TestCase):
    def candidate(self):
        rec = np.array([1, 2, -1, 4, 5, -1, 7, 8, -1], np.int64)
        order, _ = topology(rec)
        height = np.array([[3., 2., 1.]] * 3)
        raises = np.zeros_like(height)
        raises[1, 1] = .1
        area = accumulate(rec, order, np.full(9, 900.))
        local = np.full((12, 3, 3), 10.)
        config = LowlandRunoffConfig(upland_initiation_area_m2=900., lowland_initiation_area_m2=900.,
                                    channel_q_threshold_m3_s=1e-8, simulation_years=1)
        result = classify_and_route(height, raises, rec, order, area, 30., local, config=config)
        source = dict(original_td_m=height, working_raise_m=raises, receiver=rec,
                      topological_order=order, contributing_area_m2=area, selected_edge_source_ids=np.flatnonzero(rec >= 0))
        arrays = {**source, **result["arrays"], "monthly_local_runoff_m3": local,
                  "monthly_precipitation_mm": local * 1000. / 450.}
        arrays.pop("selected_edge_source_ids")
        metadata = dict(spacing_m=30., source_identity="source", native_planning_identity_sha256="plan",
                        classification=result["metadata"])
        source_metadata = dict(source_identity="source", native_planning_identity_sha256="plan")
        metadata["product_identity_sha256"] = product_identity(arrays, metadata)
        return arrays, metadata, source, source_metadata

    def test_cold_product_passes_independent_replay(self):
        arrays, metadata, source, source_metadata = self.candidate()
        report = cold_audit(arrays, metadata, source, source_metadata)
        self.assertTrue(report["passed"], report["gates"])

    def test_tampered_first_receiver_rejected_even_with_rebound_identity(self):
        arrays, metadata, source, source_metadata = self.candidate()
        arrays["first_receiving_object_id"] = arrays["first_receiving_object_id"].copy()
        arrays["first_receiving_object_id"][0, 0] = 2
        metadata["product_identity_sha256"] = product_identity(arrays, metadata)
        report = cold_audit(arrays, metadata, source, source_metadata)
        self.assertFalse(report["gates"]["first_receiver_reachable_and_first"])

    def test_balanced_but_fabricated_ledger_rejected_by_replay(self):
        arrays, metadata, source, source_metadata = self.candidate()
        metadata = copy.deepcopy(metadata)
        month = metadata["classification"]["month_ledger"][0]
        month["evaporation_m3"] += 1.
        month["unknown_boundary_export_m3"] -= 1.
        metadata["product_identity_sha256"] = product_identity(arrays, metadata)
        report = cold_audit(arrays, metadata, source, source_metadata)
        self.assertTrue(report["gates"]["monthly_balance"])
        self.assertFalse(report["gates"]["independent_month_ledger_replay"])

    def test_lowland_density_uses_lowland_area(self):
        rec = np.array([1, 2, -1, 4, 5, -1])
        metrics = network_metrics(rec, np.ones(6, bool), [1, 1, 1, 0, 0, 0], (2, 3), 30.)
        self.assertAlmostEqual(metrics["lowland_length_km"], .06)
        self.assertAlmostEqual(metrics["lowland_area_km2"], .0027)
        self.assertAlmostEqual(metrics["lowland_drainage_density_km_per_km2"], .06/.0027)

    def test_climate_stripes_keep_absolute_position_and_elevation(self):
        metadata = dict(seed=3, origin_xz_m=[1200., -900.], spacing_m=30.)
        height = np.arange(24.).reshape(6, 4)
        striped, _ = sample_monthly_precipitation(metadata, height, stripe_rows=2)
        whole, _ = sample_monthly_precipitation(metadata, height, stripe_rows=128)
        np.testing.assert_array_equal(striped, whole)

    def weather_candidate(self):
        source, metadata, _, _ = self.candidate()
        metadata.update(seed=3, origin_xz_m=[0., 0.])
        arrays, event_metadata = generate_weather(source, metadata, Path("source.npz"), "pinned", hours=48)
        return arrays, event_metadata, source

    def test_hourly_event_cold_budget_and_fixed_candidates(self):
        arrays, metadata, source = self.weather_candidate()
        report = cold_weather_audit(arrays, metadata, source)
        self.assertTrue(report["passed"], report["gates"])
        self.assertEqual(len(metadata["step_ledger"]), 48)
        self.assertTrue(all(row["storm_rain_volume_m3"] == 0. for row in metadata["step_ledger"][:12]))
        self.assertTrue(all(row["storm_rain_volume_m3"] == 0. for row in metadata["step_ledger"][36:]))
        self.assertNotIn("monthly_precipitation_mm", arrays)
        self.assertNotIn("original_td_m", arrays)

    def test_global_balanced_cell_water_disappearance_rejected_after_identity_rebind(self):
        arrays, metadata, source = self.weather_candidate()
        arrays["cumulative_evaporation_m3"].flat[0] += .001
        arrays["cumulative_evaporation_m3"].flat[1] -= .001
        metadata["product_identity_sha256"] = product_identity(arrays, metadata)
        report = cold_weather_audit(arrays, metadata, source)
        self.assertTrue(report["gates"]["hourly_event_water_balance"])
        self.assertTrue(report["gates"]["cumulative_et_matches_steps"])
        self.assertFalse(report["gates"]["independent_per_cell_water_balance"])


if __name__ == "__main__":
    unittest.main()
