"""Full-grid surface diffusion: equilibrium, wet/dry, backwater and static faces."""

from dataclasses import replace
from copy import deepcopy
import unittest

import numpy as np

from terrain_pipeline import surface_hydraulics as surface


class RegionalHydraulicsTests(unittest.TestCase):
    def geometry(self, bed, kinds=None):
        return surface.prepare_surface_geometry(np.asarray(bed, np.float64), spacing_m=30.,
            origin_m_xz=[0., 0.], source_identity="test", boundary_kind=kinds)

    def run_case(self, geometry, initial, forcing=None, boundary=None, budget=None, duration=300.):
        shape = geometry["arrays"]["H0_m"].shape
        boundary_size = geometry["arrays"]["boundary_cell"].size
        return surface.advance_inertial_surface(geometry, initial_depth_m=np.asarray(initial, np.float64),
            forcing_interval_s=duration, intervals=1,
            forcing_provider=lambda index: np.zeros(shape) if forcing is None else forcing,
            boundary_stage_provider=lambda index: np.zeros(boundary_size) if boundary is None else boundary,
            source_identity="test", forcing_identity="test", budget=budget or surface.SurfaceBudget(),
            snapshot_interval_s=duration)

    def test_dry_slope_and_partial_wet_static_equilibrium(self):
        geometry = self.geometry([[0., 1., 2.], [0., 1., 2.]])
        dry = self.run_case(geometry, np.zeros((2, 3)))
        self.assertEqual(dry["metadata"]["final_volume_m3"], 0.)
        initial = np.maximum(.5 - geometry["arrays"]["H0_m"], 0.)
        wet = self.run_case(geometry, initial)
        np.testing.assert_array_equal(wet["arrays"]["depth_m"][-1], initial)

    def test_mound_spreads_without_lost_or_negative_water(self):
        geometry = self.geometry(np.zeros((5, 5)))
        initial = np.zeros((5, 5)); initial[2, 2] = .5
        case = self.run_case(geometry, initial)
        self.assertEqual(case["metadata"]["status"], "completed")
        self.assertAlmostEqual(case["metadata"]["final_volume_m3"], 450., places=8)
        self.assertGreater(case["arrays"]["depth_m"][-1, 2, 1], 0.)
        self.assertEqual(case["diagnostics"]["negative_water_clip_count"], 0)

    def test_tailwater_backflows_into_region(self):
        kinds = np.zeros(12, np.int64); kinds[:3] = 2
        geometry = self.geometry(np.zeros((3, 3)), kinds)
        case = self.run_case(geometry, np.zeros((3, 3)), boundary=np.full(12, .1))
        self.assertGreater(case["metadata"]["boundary_input_m3"], 0.)
        self.assertLess(abs(case["metadata"]["final_volume_m3"] - case["metadata"]["boundary_input_m3"]), 1e-7)

    def test_ridge_crest_blocks_until_wet_level_exceeds(self):
        geometry = self.geometry([[0., 1., 0.]])
        flux, *_ = surface.inertial_face_flux(np.array([.5, 1.]), np.array([1., 0.]), np.ones(2), np.zeros(2), 1., 30., 30., surface.SurfaceBudget())
        np.testing.assert_array_equal(flux, 0.)
        flux, *_ = surface.inertial_face_flux(np.array([1.2, 1.]), np.array([1., 0.]), np.ones(2), np.zeros(2), 1., 30., 30., surface.SurfaceBudget())
        self.assertGreater(flux[0], 0.)

    def test_two_pool_disconnected_fill_spill_and_recession(self):
        geometry = self.geometry([[0., 1., 0.]])
        isolated = self.run_case(geometry, [[.5, 0., 0.]], duration=14400.)
        np.testing.assert_array_equal(isolated["arrays"]["depth_m"][-1], [[.5, 0., 0.]])
        fill = surface.advance_inertial_surface(geometry, initial_depth_m=np.array([[.5, 0., 0.]]),
            forcing_interval_s=3600., intervals=4,
            forcing_provider=lambda index: np.array([[.4, 0., 0.]]) if index == 0 else np.zeros((1, 3)),
            boundary_stage_provider=lambda index: np.zeros(8), source_identity="test", forcing_identity="test",
            snapshot_interval_s=900.)
        self.assertEqual(fill["metadata"]["status"], "completed")
        self.assertAlmostEqual(fill["metadata"]["supplied_m3"], 1440., places=7)
        self.assertAlmostEqual(fill["metadata"]["final_volume_m3"], 1890., places=7)
        self.assertGreater(fill["arrays"]["depth_m"][-1, 0, 2], 1.)
        self.assertLess(np.abs(fill["arrays"]["ledger"][:, 4]).max(), 1e-8)
        kinds = np.zeros(8, np.int64)
        kinds[1] = 2
        drainage = self.geometry([[0., 1., 0.]], kinds)
        retreat = self.run_case(drainage, fill["arrays"]["depth_m"][-1], duration=14400.)
        self.assertGreater(retreat["metadata"]["boundary_output_m3"], 900.)
        self.assertGreater(retreat["arrays"]["depth_m"][-1, 0, 0], 1.)
        self.assertLess(retreat["arrays"]["depth_m"][-1, 0, 2], .01)
        self.assertLess(np.abs(retreat["arrays"]["ledger"][:, 4]).max(), 1e-8)
        self.assertEqual(retreat["diagnostics"]["negative_water_clip_count"], 0)

    def test_max_depth_and_work_refusal_save_committed_prefix(self):
        geometry = self.geometry(np.zeros((2, 2)))
        budget = replace(surface.SurfaceBudget(), max_substeps=2)
        case = self.run_case(geometry, np.zeros((2, 2)), budget=budget)
        self.assertEqual(case["metadata"]["status"], "refused")
        self.assertEqual(case["metadata"]["substeps"], 2)
        self.assertEqual(case["metadata"]["committed_time_s"], 60.)
        case = self.run_case(geometry, np.zeros((2, 2)), forcing=np.full((2, 2), 900.), budget=replace(surface.SurfaceBudget(), max_depth_m=.01))
        self.assertEqual(case["metadata"]["status"], "refused")
        self.assertEqual(case["metadata"]["final_volume_m3"], 0.)

    def test_half_dt_same_physical_mound(self):
        geometry = self.geometry(np.zeros((5, 5)))
        initial = np.zeros((5, 5)); initial[2, 2] = .05
        coarse = self.run_case(geometry, initial, budget=replace(surface.SurfaceBudget(), max_dt_s=10.))
        fine = self.run_case(geometry, initial, budget=replace(surface.SurfaceBudget(), max_dt_s=5.))
        self.assertLess(np.abs(coarse["arrays"]["depth_m"][-1] - fine["arrays"]["depth_m"][-1]).max(), .001)

    def test_implicit_drag_uniform_slope_equilibrium(self):
        budget = surface.SurfaceBudget()
        for depth in (.001, .01, 1., 20.):
            expected = 30 * depth**(5 / 3) / .035 * np.sqrt(10 / 30)
            actual, _ = surface.inertial_face_flux(np.array([1500.+depth]), np.array([1490.+depth]), np.array([1500.]), np.array([expected]), 30., 30., 30., budget)
            self.assertAlmostEqual(actual[0] / expected, 1., places=9)

    def test_inertial_dry_static_mound_tailwater_and_limiter(self):
        for mode in ("dry", "static", "mound", "tailwater"):
            kinds = np.zeros(12, np.int64)
            if mode == "tailwater":
                kinds[:3] = 2
            bed = np.zeros((3, 3))
            if mode == "static":
                bed[:, 2] = 2.
            geometry = self.geometry(bed, kinds)
            initial = np.maximum(.5 - bed, 0.) if mode == "static" else np.zeros((3, 3))
            if mode == "mound":
                initial[1, 1] = .5
            saved = surface.advance_inertial_surface(geometry, initial_depth_m=initial, forcing_interval_s=300., intervals=1,
                forcing_provider=lambda index: np.zeros((3, 3)), boundary_stage_provider=lambda index: np.full(12, .1),
                source_identity="test", forcing_identity="test", snapshot_interval_s=300.)
            self.assertEqual(saved["metadata"]["status"], "completed", mode)
            if mode in ("dry", "static"):
                np.testing.assert_array_equal(saved["arrays"]["depth_m"][-1], initial)
            if mode == "tailwater":
                self.assertGreater(saved["metadata"]["boundary_input_m3"], 0.)
            error = saved["metadata"]["final_volume_m3"] - saved["metadata"]["initial_volume_m3"] - saved["metadata"]["boundary_input_m3"] + saved["metadata"]["boundary_output_m3"]
            self.assertLess(abs(error), 1e-7)

    def test_inertial_real_stage_gradient_and_positive_limited_step(self):
        budget = surface.SurfaceBudget()
        q, _ = surface.inertial_face_flux(np.array([1500.01]), np.array([1490.01]), np.array([1500.]), np.zeros(1), .1, 30., 30., budget)
        rhs = 9.81 * .01 * .1 * 10 / 30
        drag = 9.81 * .1 * .035**2 / .01**(7 / 3)
        self.assertAlmostEqual(q[0] / 30 + drag * (q[0] / 30)**2, rhs, places=10)
        geometry = self.geometry([[0., 0.]])
        depth = np.array([.001, 0.])
        internal, boundary, stats = surface.limited_inertial_fluxes(geometry, depth, np.array([100.]), np.zeros(6), np.zeros(6), np.zeros(2), 30., replace(budget, roughness_s_m_third=1e-8))
        updated = depth + 30 * surface._net_flux(geometry, internal, boundary) / 900
        self.assertTrue((updated >= 0).all())
        self.assertGreater(stats["limited_donors"], 0)
        self.assertGreater(stats["removed_transfer_m3"], 0)


if __name__ == "__main__":
    unittest.main()
