import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.surface_rivers.metric_distribution_calibration import (
    calibrate_distribution, cdf_distance, evaluate_distribution,
)
from terrain_pipeline.surface_rivers.metric_naturalness_audit import channel_graph_observations
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from tools.verify_td_natural_river_baseline import boundary_for
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.common_infra import file_sha256, identity
from tools.verify_td_channel_distribution import implementation_pins, validate_reference, measure, climate_bin


class DistributionCalibrationTests(unittest.TestCase):
    def test_climate_bins_use_frozen_units_and_right_boundary(self):
        design = {"bin_edges": [[0., 10., 20., 30.], [500., 1000., 1500., 2000.],
                                [500., 1000., 2000., 3000.], [30., 60., 90.]]}
        self.assertEqual(climate_bin([20., 500., 999., 30.], design), [3, 1, 1, 1])
        with self.assertRaises(ValueError):
            climate_bin([20., float("nan"), 999., 30.], design)

    def test_runner_rejects_plan_and_implementation_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = {"implementation_pins": implementation_pins()}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            reference = {"plan_sha256": file_sha256(plan_path)}
            reference["identity_sha256"] = identity({}, reference)
            reference_path = root / "reference.json"
            reference_path.write_text(json.dumps(reference), encoding="utf-8")
            validate_reference(reference_path)
            plan["implementation_pins"]["tools/verify_td_channel_distribution.py"] = "0" * 64
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "plan pin"):
                validate_reference(reference_path)
            reference = {"plan_sha256": file_sha256(plan_path)}
            reference["identity_sha256"] = identity({}, reference)
            reference_path.write_text(json.dumps(reference), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "implementation"):
                validate_reference(reference_path)

    def test_runner_projects_both_sources_to_same_meter_precision(self):
        captured = []
        def diagnose_projected(terrain, boundary, **kwargs):
            captured.append(terrain.elevation_m.copy())
            return None, {"channel_geometry_observations": {"status": "insufficient_channel_support"}}
        with patch("tools.verify_td_channel_distribution.diagnose", diagnose_projected):
            for source_kind in ("observed_dem", "generated_terrain"):
                measure(np.array([[1.49, 1.51], [2.5, 3.5]]), np.ones((2, 2), bool),
                        spacing=90., source_kind=source_kind, source_sha="a" * 64, source_id=source_kind)
        np.testing.assert_array_equal(captured[0], [[1., 2.], [2., 4.]])
        np.testing.assert_array_equal(captured[0], captured[1])

    def test_channel_metrics_exclude_subthreshold_hillslope_edges(self):
        terrain = TerrainGrid(np.array([[9., 3., 0.], [8., 2., -1.], [7., 1., -2.]]),
                              np.ones((3, 3), bool), 0., 0., 10., 10., "diagnostic_dem_proxy", "fixture", "a" * 64)
        graph = route_diagnostic(terrain, boundary_for(terrain, "closed_wall"))
        area = accumulate_local_discharge(graph, terrain.valid_mask * terrain.cell_area_m2)["routed_q_m3_s"]
        result = channel_graph_observations(terrain, graph, area, minimum_area_m2=200.)
        self.assertTrue(all(value >= 200. for value in result["channel_support"]["area_m2"]))
        self.assertLess(result["channel_support"]["selected_edge_count"], int((graph.receiver >= 0).sum()))

    def test_central_ninety_percent_is_not_a_full_sample_acceptance_test(self):
        samples = np.arange(100., dtype=np.float64)
        lower, upper = np.quantile(samples, [.05, .95])
        self.assertEqual(int(((samples < lower) | (samples > upper)).sum()), 10)
        self.assertEqual(cdf_distance(samples, samples), 0.)

    def test_real_block_rank_calibration_accepts_distribution_and_rejects_shift(self):
        training = [{"id": "train", "metrics": {"slope": list(range(100))}}]
        calibration = [{"id": str(i), "metrics": {"slope": list(range(i, 100 + i))}}
                       for i in range(1, 6)]
        frozen = calibrate_distribution(training, calibration, alpha=.2)
        self.assertEqual(evaluate_distribution(training[0]["metrics"], frozen, conditions_match=True)["status"], "pass")
        self.assertEqual(evaluate_distribution({"slope": list(range(200, 300))}, frozen, conditions_match=True)["status"], "fail")
        self.assertEqual(evaluate_distribution(training[0]["metrics"], frozen, conditions_match=False)["status"], "not_assessed")
        changed = copy.deepcopy(frozen)
        changed["joint_cdf_cutoff"] = 1.
        with self.assertRaises(ValueError):
            evaluate_distribution(training[0]["metrics"], changed, conditions_match=True)

    def test_ties_and_nonfinite_samples_are_explicit(self):
        self.assertEqual(cdf_distance([0., 0.], [1., 1.]), 1.)
        with self.assertRaises(ValueError):
            cdf_distance([0., float("nan")], [0., 1.])
        frozen = calibrate_distribution([{"id": "train", "metrics": {"x": [0., 1.]}}],
                                        [{"id": "cal", "metrics": {"x": [0., 1.]}}], alpha=.05)
        self.assertEqual(frozen["cutoff_status"], "insufficient_calibration")
        self.assertEqual(evaluate_distribution({"x": [0., 1.]}, frozen, conditions_match=True)["status"], "not_assessed")
        with self.assertRaisesRegex(ValueError, "disjoint"):
            calibrate_distribution([{"id": "same", "metrics": {"x": [0., 1.]}}],
                                   [{"id": "same", "metrics": {"x": [0., 1.]}}])


if __name__ == "__main__":
    unittest.main()
