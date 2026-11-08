# -*- coding: utf-8 -*-
"""Contract tests for the bounded multi-year ice body (G7 ice item).

Everything here is a 3..9 cell synthetic flowline: no TD page, no saved product, no climate
model, no real-world glacier. The point is the SIA flux algebra, the explicit CFL refusal, the
three separate ledgers (ice / liquid / rock), and the declared limits.
"""
import unittest

import numpy as np

from terrain_pipeline import environment_processes as glacier

DAY = 86400.0
YEAR = 365.0 * DAY

#: A declared 6 h step. The explicit SIA stability limit for these fixtures is a few thousand
#: seconds, so a daily/monthly step would be refused by design — the tests use a step the model
#: can actually take instead of weakening the CFL bound or shrinking A / slope / thickness.
STEP_S = 6.0 * 3600.0


def flowline(cells=5):
    x = np.arange(cells, dtype=np.float64) * glacier.NATIVE_SPACING_M + 1000.0
    return x


def linear_bed(cells=5, drop_m=180.0):
    """A bed that descends along the flowline, so the ice surface has a slope."""
    return np.linspace(drop_m, 0.0, cells)


class ParameterTests(unittest.TestCase):
    def test_the_creep_parameter_is_dimensional_and_enters_the_identity(self):
        parameters = glacier.GlacierParameters()
        identity = parameters.identity()
        # the declared A is a Glen value in Pa^-n s^-1, and the identity says which unit
        self.assertAlmostEqual(identity["creep_parameter_pa_n_s"], 2.4e-24, places=30)
        self.assertEqual(identity["glen_exponent"], 3)
        # the unit is a declared **structural** field, not a sentence to pattern-match
        self.assertEqual(identity["creep_parameter_unit"], glacier.CREEP_PARAMETER_UNIT)
        self.assertIn("Pa^-n s^-1", identity["creep_parameter_unit"])
        self.assertIn("dimensionless", identity["creep_parameter_semantics"])
        self.assertAlmostEqual(identity["densification"], 1000.0 / 917.0, places=12)
        self.assertNotAlmostEqual(identity["densification"], 1.0, places=6)

    def test_a_lumped_coefficient_cannot_be_passed_as_a(self):
        with self.assertRaises(ValueError):
            glacier.GlacierParameters(creep_parameter_pa_n_s=0.0)
        with self.assertRaises(ValueError):
            glacier.GlacierParameters(glen_exponent=0)

    def test_the_thickness_cutoff_defaults_to_zero_so_small_samples_move(self):
        self.assertEqual(glacier.GlacierParameters().min_flow_thickness_m, 0.0)


class FlowTests(unittest.TestCase):
    def _run(self, *, flow_model="shallow_ice", thickness=None, cells=5, intervals=2,
             dt_s=STEP_S, accumulation=0.0, ablation=0.0, **kwargs):
        x = flowline(cells)
        bed = linear_bed(cells)
        if thickness is None:
            thickness = np.full(cells, 80.0)
        edges = np.arange(intervals + 1, dtype=np.float64) * dt_s
        return glacier.advance_glacier(
            thickness_start_m=thickness, bed_m=bed,
            accumulation_mm=np.full((intervals, cells), accumulation),
            ablation_mm=np.full((intervals, cells), ablation),
            time_edges_s=edges, x_m=x, flow_model=flow_model, **kwargs)

    def test_a_sloped_ice_body_flows_and_the_ice_ledger_closes(self):
        result = self._run()
        arrays = result["arrays"]
        thickness = arrays["thickness_edge_m"]
        # ice really moved: the down-slope end thickened, the up-slope end thinned
        self.assertGreater(thickness[-1, -1], thickness[0, -1])
        self.assertLess(thickness[-1, 0], thickness[0, 0])
        ledger = result["ledger"]
        self.assertLessEqual(abs(ledger["ice"]["max_abs_residual_m3"]), 1e-6)
        # and some face genuinely carried flux
        self.assertGreater(float(np.abs(arrays["face_flux_m3_s"]).sum()), 0.0)
        self.assertTrue((arrays["motion_state"] == glacier.MOTION_FLOWING).any())

    def test_the_none_model_is_a_static_control_with_zero_flux(self):
        static = self._run(flow_model="none")
        moved = self._run(flow_model="shallow_ice")
        self.assertTrue(np.all(static["arrays"]["face_flux_m3_s"] == 0.0))
        self.assertTrue(np.all(static["arrays"]["motion_state"] == glacier.MOTION_STATIC))
        self.assertTrue(np.allclose(static["arrays"]["thickness_edge_m"][-1],
                                    static["arrays"]["thickness_edge_m"][0], atol=1e-12))
        self.assertFalse(np.allclose(moved["arrays"]["thickness_edge_m"][-1],
                                     moved["arrays"]["thickness_edge_m"][0]))

    def test_the_surface_is_recomputed_from_bed_and_thickness(self):
        result = self._run()
        arrays = result["arrays"]
        x = flowline(5)
        bed = linear_bed(5)
        expected = arrays["thickness_edge_m"] + bed.reshape(1, -1)
        self.assertTrue(np.allclose(arrays["surface_edge_m"], expected, atol=1e-12))

    def test_a_net_negative_mass_balance_still_leaves_a_store(self):
        """A net loss over the declared period, with a store left behind.

        The period is 24 x 6 h (6 days) rather than a year: a year in one interval would exceed
        the explicit stability limit and must be refused. The water-equivalent ablation is declared
        per interval and constant, so the total mass and the physical length are both explicit.
        """
        result = self._run(thickness=np.full(5, 120.0), intervals=24, dt_s=STEP_S,
                           accumulation=0.0, ablation=50.0)
        thickness = result["arrays"]["thickness_edge_m"]
        self.assertLess(float(thickness[-1].sum()), float(thickness[0].sum()))
        self.assertGreater(float(thickness[-1].sum()), 0.0)     # a store remains
        self.assertLessEqual(abs(result["ledger"]["ice"]["max_abs_residual_m3"]), 1e-6)

    def test_an_unstable_interval_is_refused_not_clipped_into_stability(self):
        # a long interval with thick steep ice exceeds MAX_SUBSTEPS * dt_limit
        with self.assertRaises(ValueError):
            self._run(thickness=np.full(5, 300.0), intervals=1, dt_s=200.0 * YEAR)

    def test_the_thickness_ceiling_is_refused(self):
        with self.assertRaises(ValueError):
            self._run(thickness=np.full(5, 600.0))

    def test_a_non_monotone_flowline_is_refused(self):
        with self.assertRaises(ValueError):
            glacier.advance_glacier(
                thickness_start_m=np.full(3, 50.0), bed_m=np.zeros(3),
                accumulation_mm=np.zeros((1, 3)), ablation_mm=np.zeros((1, 3)),
                time_edges_s=np.asarray([0.0, DAY]),
                x_m=np.asarray([1000.0, 970.0, 1060.0]))

    def test_the_cell_count_is_bounded(self):
        with self.assertRaises(ValueError):
            glacier.advance_glacier(
                thickness_start_m=np.full(2, 50.0), bed_m=np.zeros(2),
                accumulation_mm=np.zeros((1, 2)), ablation_mm=np.zeros((1, 2)),
                time_edges_s=np.asarray([0.0, DAY]), x_m=np.asarray([1000.0, 1030.0]))


class LiquidTests(unittest.TestCase):
    def test_ablation_water_has_a_declared_destination(self):
        cells = 4
        x = flowline(cells)
        bed = linear_bed(cells)
        edges = np.asarray([0.0, 30.0 * DAY])
        result = glacier.advance_glacier(
            thickness_start_m=np.full(cells, 100.0), bed_m=bed,
            accumulation_mm=np.zeros((1, cells)),
            ablation_mm=np.full((1, cells), 50.0),
            time_edges_s=edges, x_m=x, flow_model="none",
            land_port_mask=np.asarray([True, False, True, False]))
        arrays = result["arrays"]
        liquid = result["ledger"]["liquid"]
        self.assertGreater(float(np.sum(liquid["produced_mm"])), 0.0)
        # the cell without a port still produced water; it is not silently dropped
        self.assertGreater(float(arrays["liquid_export_unresolved_mm"][0, 1]), 0.0)
        self.assertGreater(float(arrays["melt_to_land_mm"][0, 0]), 0.0)
        self.assertEqual(float(arrays["melt_to_land_mm"][0, 1]), 0.0)
        self.assertLessEqual(abs(float(np.max(np.abs(liquid["residual_mm"])))), 1e-9)
        produced = float(np.sum(liquid["produced_mm"]))
        accounted = float(np.sum(liquid["to_land_mm"])) + float(np.sum(liquid["unresolved_mm"]))
        self.assertAlmostEqual(produced, accounted, places=9)

    def test_ice_volume_and_water_volume_are_never_numerically_equal(self):
        cells = 3
        x = flowline(cells)
        bed = linear_bed(cells)
        edges = np.asarray([0.0, 30.0 * DAY])
        # 100 mm water equivalent over 900 m2, converted to ice volume through both densities
        result = glacier.advance_glacier(
            thickness_start_m=np.zeros(cells), bed_m=bed,
            accumulation_mm=np.full((1, cells), 100.0),
            ablation_mm=np.zeros((1, cells)), time_edges_s=edges, x_m=x,
            flow_model="none")
        ice = result["arrays"]["accumulation_ice_m3"][0, 0]
        water = 100.0 / 1000.0 * glacier.CELL_AREA_M2
        self.assertAlmostEqual(ice, water * 1000.0 / 917.0, places=9)
        self.assertNotAlmostEqual(ice, water, places=6)


class ErosionTests(unittest.TestCase):
    def _run(self, stock, *, coefficient=1.0e-3):
        cells = 4
        x = flowline(cells)
        bed = linear_bed(cells)
        edges = np.arange(3, dtype=np.float64) * STEP_S
        parameters = glacier.GlacierParameters(erosion_proxy_coefficient=coefficient)
        return glacier.advance_glacier(
            thickness_start_m=np.full(cells, 90.0), bed_m=bed,
            accumulation_mm=np.zeros((2, cells)), ablation_mm=np.zeros((2, cells)),
            time_edges_s=edges, x_m=x, flow_model="shallow_ice",
            bedrock_erodible_m3=stock, parameters=parameters)

    def test_without_a_bedrock_stock_the_answer_is_not_available(self):
        result = self._run(None)
        self.assertEqual(result["metadata"]["erosion"]["status"], glacier.EROSION_NOT_AVAILABLE)
        self.assertEqual(float(result["arrays"]["erosion_rock_m3"].sum()), 0.0)
        self.assertIsNone(result["ledger"]["rock"]["supplied_m3"])

    def test_a_finite_stock_is_consumed_and_exhausts(self):
        stock = np.full(4, 1.0e-6)          # a deliberately tiny stock
        result = self._run(stock)
        rock = result["ledger"]["rock"]
        self.assertEqual(rock["status"], glacier.EROSION_PROXY_DECLARED)
        removed = float(np.sum(rock["removed_m3"]))
        self.assertGreater(removed, 0.0)
        self.assertLessEqual(removed, float(np.sum(stock)) + 1e-15)
        remaining = rock["remaining_m3"]
        self.assertTrue(all(value >= 0.0 for value in remaining))
        # the solid account closes against its own finite supply
        self.assertAlmostEqual(removed, float(np.sum(rock["exported_solid_m3"])), places=12)

    def test_the_derived_bed_delta_is_returned_and_never_written_back(self):
        result = self._run(np.full(4, 10.0))
        arrays = result["arrays"]
        self.assertIn("bed_delta_m", arrays)
        self.assertTrue(np.all(arrays["bed_delta_m"] <= 0.0))
        self.assertFalse(result["metadata"]["erosion"]["couples_back_to_bed"])
        self.assertTrue(result["metadata"]["claims_denied"]["bed_feedback_coupled"])


class ContinuationTests(unittest.TestCase):
    """同一输入：一次跑完 与 分两块传 state 续接 必须一致。"""

    def test_a_split_run_matches_a_continuous_run(self):
        cells = 5
        x = flowline(cells)
        bed = linear_bed(cells)
        accumulation = np.full((4, cells), 20.0)
        edges_all = np.arange(5, dtype=np.float64) * STEP_S
        continuous = glacier.advance_glacier(
            thickness_start_m=np.full(cells, 70.0), bed_m=bed,
            accumulation_mm=accumulation, ablation_mm=np.zeros((4, cells)),
            time_edges_s=edges_all, x_m=x)
        split_edges = edges_all[:3]
        first = glacier.advance_glacier(
            thickness_start_m=np.full(cells, 70.0), bed_m=bed,
            accumulation_mm=accumulation[:2], ablation_mm=np.zeros((2, cells)),
            time_edges_s=split_edges, x_m=x)
        second = glacier.advance_glacier(
            thickness_start_m=first["arrays"]["thickness_edge_m"][-1], bed_m=bed,
            accumulation_mm=accumulation[2:], ablation_mm=np.zeros((2, cells)),
            time_edges_s=edges_all[2:], x_m=x)
        self.assertTrue(np.allclose(second["arrays"]["thickness_edge_m"][-1],
                                    continuous["arrays"]["thickness_edge_m"][-1],
                                    rtol=0.0, atol=1e-9))
        self.assertLessEqual(abs(continuous["ledger"]["ice"]["max_abs_residual_m3"]), 1e-6)


class DescriptionTests(unittest.TestCase):
    def test_the_module_states_what_it_does_not_model(self):
        described = glacier.describe()
        self.assertEqual(described["schema"], glacier.GLACIER_SCHEMA)
        self.assertIn("basal_sliding", described["not_modelled"])
        self.assertIn("glacier_existence", described["not_modelled"])
        self.assertEqual(described["cells_bounds"], [glacier.MIN_CELLS,
                                                     glacier.MAX_CELLS])
        # the creep unit is a declared **structural** field, not prose to pattern-match
        self.assertEqual(described["creep_parameter_unit"], glacier.CREEP_PARAMETER_UNIT)
        self.assertIn("Pa^-n s^-1", described["creep_parameter_unit"])
        self.assertEqual(described["cfl"], glacier.CFL)


if __name__ == "__main__":
    unittest.main()
