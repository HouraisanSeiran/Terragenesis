import dataclasses
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.common_infra import RainfallForcing, TerrainGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.surface_rivers.metric_product import (
    _equal_budget_residual, build_diagnostic_product, load_diagnostic_product, validate_diagnostic_product,
)
from tools.verify_td_natural_river_baseline import (
    audit_shared_strips, boundary_for, diagnose, run_case, grid_reference_conditions_match,
)
from terrain_pipeline.surface_rivers.metric_naturalness_audit import geometry_metrics, compare_frozen_samples


class NaturalRiverBaselineTests(unittest.TestCase):
    def test_reference_grid_conditions_cannot_silently_match_other_scale_or_boundary(self):
        reference = {"conditions": {"spacing_m": 100., "domain_shape_zx": [3, 3],
                                     "boundary": "imposed_unknown",
                                     "comparison_scope": "same_scale_original_bed_diagnostic_geometry_not_hydraulic_naturalness"},
                     "metric_definition": {"channel_area_threshold_m2": 100000.}}
        self.assertTrue(grid_reference_conditions_match(reference, self.terrain))
        for field, value in (("spacing_m", 90.), ("domain_shape_zx", [4, 4]),
                             ("boundary", "imposed_open"), ("comparison_scope", "hydraulic")):
            changed = copy.deepcopy(reference)
            changed["conditions"][field] = value
            self.assertFalse(grid_reference_conditions_match(changed, self.terrain))

    def test_frozen_reference_reports_failures_and_condition_mismatch(self):
        frozen = {"schema": "metric-naturalness-frozen-reference-v1",
                  "metrics": {"slope": {"review_interval": [0., .1], "absolute_tolerance": 1e-9}}}
        observed = {"slope": {"samples": [.01, .05, .2]}}
        compared = compare_frozen_samples(observed, frozen, conditions_match=True)
        self.assertEqual(compared["comparisons"]["slope"]["outside_count"], 1)
        self.assertFalse(compared["natural_certification"])
        context = compare_frozen_samples(observed, frozen, conditions_match=False)
        self.assertEqual(context["comparisons"]["slope"]["status"], "condition_mismatch_context_only")
        for interval, tolerance in (([float("nan"), 1.], 0.), ([1., 0.], 0.), ([0., 1.], -1.)):
            bad = copy.deepcopy(frozen)
            bad["metrics"]["slope"].update(review_interval=interval, absolute_tolerance=tolerance)
            with self.assertRaises(ValueError):
                compare_frozen_samples(observed, bad, conditions_match=True)
        with self.assertRaises(ValueError):
            compare_frozen_samples({"slope": {"samples": [float("inf")]}}, frozen, conditions_match=True)

    def test_historical_invalid_water_geometry_is_expected_rejection(self):
        from terrain_pipeline.surface_rivers.metric_channel_product import load_channel_product
        path = Path("verification/td-river-channel/m3-20261008-02/acceptance.json")
        if not path.is_file():
            self.skipTest("historical rejection evidence unavailable")
        import json
        report = json.loads(path.read_text(encoding="utf-8"))
        for name in ("y_ode_coarse", "y_ode_fine", "single_characteristic", "y_characteristic"):
            pin = report["artifacts"][name]
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "strictly downhill"):
                    load_channel_product(path.parent / pin["path"], expected_sha256=pin["sha256"],
                                         expected_identity=pin["identity_sha256"])
        from terrain_pipeline.surface_rivers.metric_coupled_product import load_coupled_product
        lake_path = Path("verification/td-river-lake-coupling/m3-m4-20261008-02/acceptance.json")
        lake_pin = json.loads(lake_path.read_text(encoding="utf-8"))["artifacts"]["m3_compatibility"]
        with self.assertRaisesRegex(ValueError, "strictly downhill"):
            load_coupled_product(lake_path.parent / lake_pin["path"], expected_sha256=lake_pin["sha256"],
                                 expected_identity=lake_pin["identity_sha256"])

    def test_geometry_observes_knickpoint_turn_section_and_cross_tile_join(self):
        result = geometry_metrics(np.array([[0., 0.], [0., 1.], [1., 1.], [-1., 1.]]),
                                  np.array([3., 1., 0., 2.]), np.array([1, 2, -1, 1]),
                                  width_m=np.full(4, 2.), depth_m=np.full(4, .5),
                                  allowed_terminal=np.array([False, False, True, False]),
                                  tile_ids=np.array([0, 1, 1, 0]))
        self.assertEqual(result["width_depth_ratio"]["samples"], [4.] * 4)
        self.assertEqual(result["topology"]["cross_tile_confluence_edge_count"], 2)
        self.assertGreater(max(result["curvature_rad_per_m"]["samples"]), 0.)
        self.assertIn(1., result["signed_slope_jump_knickpoint_candidate"]["samples"])
        self.assertTrue(all(result["checks"].values()))

    def test_cycle_hanging_and_uphill_counterexamples_fail_checks(self):
        cycle = geometry_metrics(np.array([[0., 0.], [1., 0.]]), np.array([1., 0.]),
                                 np.array([1, 0]))
        self.assertFalse(cycle["checks"]["acyclic"])
        self.assertFalse(cycle["checks"]["downhill_or_flat"])
        hanging = geometry_metrics(np.array([[0., 0.], [1., 0.]]), np.array([1., 0.]),
                                   np.array([1, -1]), allowed_terminal=np.array([False, False]))
        self.assertFalse(hanging["checks"]["no_unexplained_hanging_end"])

    def test_public_validator_rejects_rehashed_material_budget_change(self):
        forcing = RainfallForcing(np.array([0., 300.]), np.full((1, 3, 3), 30.), "rain", "a" * 64)
        product = build_diagnostic_product(self.terrain, boundary_for(self.terrain, "closed_wall"), forcing)
        changed = copy.deepcopy(product)
        changed["metadata"]["water_budget_m3"]["combined_residual"] += 1e-6
        changed["identity_sha256"] = identity(changed["arrays"], changed["metadata"])
        with self.assertRaises(ValueError):
            validate_diagnostic_product(changed)

    def test_fixed_large_td_public_cold_reader(self):
        from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID
        path = TD_DIRECTORY / "product.npz"
        if not path.is_file():
            self.skipTest("fixed TD diagnostic source unavailable")
        product = load_diagnostic_product(path, expected_sha256=TD_PRODUCT_SHA, expected_identity=TD_PRODUCT_ID)
        self.assertEqual(product["identity_sha256"], TD_PRODUCT_ID)

    def test_shared_native_strip_identity_and_shift_rejection(self):
        height = np.arange(33 * 33, dtype=np.float64).reshape(33, 33)
        result = audit_shared_strips(height)
        self.assertTrue(result["exact_native_overlap"]["accepted"])
        self.assertFalse(result["synthetic_shifted_strip"]["accepted"])
        self.assertFalse(result["hydrologic_seam_certified"])

    def test_cancellation_roundoff_is_not_an_unclosed_budget(self):
        saved = {"rain_input": 2359296., "evapotranspiration": 35389.43999999996,
                 "hydrology_storage_change": 2101925.685524599,
                 "open_outflow": 6859.029189352776, "lake_retained": 215121.8452860521,
                 "unknown_pending": 0., "prescribed_boundary_candidate": 0.,
                 "combined_residual": -3.958120942115784e-9}
        current = copy.deepcopy(saved)
        current["hydrology_storage_change"] += 4.656612873077393e-10
        current["combined_residual"] = -4.423782229423523e-9
        _equal_budget_residual(saved, current)
        bad = copy.deepcopy(saved)
        bad["combined_residual"] += 1e-6
        with self.assertRaises(ValueError):
            _equal_budget_residual(bad, current)
        current["combined_residual"] += 1e-6
        with self.assertRaises(ValueError):
            _equal_budget_residual(saved, current)

    def setUp(self):
        height = np.array([[4., 3., 4.], [3., 0., 3.], [4., 3., 4.]])
        self.terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 100., 100.,
                                   "diagnostic_dem_proxy", "basin", identity({"height": height}, {}))

    def test_unknown_internal_basin_and_free_outflow_are_distinct(self):
        for policy, expected in (("unknown_boundary", "unknown_boundary"),
                                 ("closed_wall", "lake_preserved"),
                                 ("open_outflow", "open_outflow")):
            with self.subTest(policy=policy):
                _, statistics = diagnose(self.terrain, boundary_for(self.terrain, policy))
                self.assertIn(expected, statistics["terminal_kind_counts"])
                self.assertEqual(statistics["terminal_area_residual_m2"], 0.)
                if policy == "closed_wall":
                    self.assertNotIn("open_outflow", statistics["terminal_kind_counts"])

    def test_saved_slope_inconsistent_with_native_bed_is_rejected(self):
        boundary = boundary_for(self.terrain, "closed_wall")
        graph = route_diagnostic(self.terrain, boundary)
        slope = graph.edge_slope.copy()
        slope[graph.receiver >= 0] += .1
        bad = dataclasses.replace(graph, edge_slope=slope)
        with patch("tools.verify_td_natural_river_baseline.route_diagnostic", return_value=bad):
            with self.assertRaises(AssertionError):
                diagnose(self.terrain, boundary)

    def test_baseline_cold_read_and_repeat_preserve_status(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_case("basin", self.terrain, boundary_for(self.terrain, "closed_wall"),
                              {"terrain_class": "synthetic_basin"}, Path(directory))
            self.assertTrue(result["cold_read_verified"])
            self.assertTrue(result["same_source_repeatable"])
            self.assertFalse(result["natural_outlet_verified"])
            self.assertEqual(result["status"], "diagnostic")


if __name__ == "__main__":
    unittest.main()
