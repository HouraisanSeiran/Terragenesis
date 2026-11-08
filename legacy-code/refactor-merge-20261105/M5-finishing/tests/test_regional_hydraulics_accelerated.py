"""Non-fastmath backend differential checks, including active limiter and backflow."""
from dataclasses import replace
import unittest
import numpy as np
from terrain_pipeline import surface_hydraulics as base
from terrain_pipeline import surface_hydraulics as accelerated


class RegionalAccelerationTests(unittest.TestCase):
    def test_random_faces_reverse_flow_and_active_limiter(self):
        generator = np.random.default_rng(42)
        geometry = base.prepare_surface_geometry(generator.uniform(1490., 1500., (8, 8)), spacing_m=30., origin_m_xz=[0., 0.], source_identity="test", boundary_kind=np.full(32, 2, np.int64))
        for roughness in (.035, 1e-8):
            budget = replace(base.SurfaceBudget(), roughness_s_m_third=roughness)
            args = (geometry, generator.uniform(0., .1, 64), generator.uniform(-100., 100., 112),
                generator.uniform(-100., 100., 32), np.full(32, 1495.), generator.uniform(0., .01, 64), 30., budget)
            expected = base.limited_inertial_fluxes(*args)
            actual = accelerated.regional_surface_hydraulics_accelerated_limited_inertial_fluxes(*args)
            for index in (0, 1):
                np.testing.assert_allclose(actual[index], expected[index], rtol=2e-13, atol=1e-12)
            self.assertEqual(actual[2]["limited_donors"], expected[2]["limited_donors"])
            self.assertAlmostEqual(actual[2]["removed_transfer_m3"], expected[2]["removed_transfer_m3"], places=8)

    def test_multistep_same_status_states_and_ledgers(self):
        for mode in ("mound", "backwater", "refused"):
            kinds = np.zeros(20, np.int64)
            if mode == "backwater":
                kinds[:5] = 2
            geometry = base.prepare_surface_geometry(np.zeros((5, 5)), spacing_m=30., origin_m_xz=[0., 0.], source_identity="test", boundary_kind=kinds)
            initial = np.zeros((5, 5))
            if mode == "mound":
                initial[2, 2] = 1.
            budget = replace(base.SurfaceBudget(), max_substeps=2) if mode == "refused" else base.SurfaceBudget()
            kwargs = dict(initial_depth_m=initial, forcing_interval_s=900., intervals=1,
                forcing_provider=lambda index: np.full((5, 5), .0001), boundary_stage_provider=lambda index: np.full(20, .2),
                source_identity="test", forcing_identity="test", budget=budget)
            expected = base.advance_inertial_surface(geometry, **kwargs)
            actual = accelerated.advance_accelerated_surface(geometry, **kwargs)
            self.assertEqual(actual["metadata"]["status"], expected["metadata"]["status"])
            for key in expected["arrays"]:
                np.testing.assert_allclose(actual["arrays"][key], expected["arrays"][key], rtol=1e-11, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
