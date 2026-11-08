import math
import unittest

import numpy as np

from tools.run_delta_forms import initial_product, sea_stage, schedule, form_report, forcing_record
from terrain_pipeline.environment_delta_fv import initialize, advance, FVDeltaConfig


class DeltaFormsTests(unittest.TestCase):
    def test_single_factor_initial_geometry_and_stock(self):
        slope, _ = initial_product("slope")
        wide, excavation = initial_product("wide_mouth")
        self.assertEqual(slope["arrays"]["bed_m"][16, 0], -1.5)
        self.assertEqual(slope["arrays"]["bed_m"][16, 35], -.5)
        self.assertEqual(np.count_nonzero(wide["arrays"]["bed_m"][:, 40] == -1.), 5)
        self.assertAlmostEqual(excavation, 5*12*900*1.8)
        for product in (slope, wide):
            self.assertEqual(product["arrays"]["inlet_cells"].tolist(), [16*48+46])
            self.assertEqual(form_report(product)["solid_budget_residual_m3"], 0.)
            self.assertEqual(form_report(product)["substrate_floor_hit_cells"], 0)

    def test_tide_endpoint_phase_and_wave_identity(self):
        tide, _ = initial_product("tide")
        metadata = dict(tide["metadata"], physical_time_s=86700.)
        self.assertAlmostEqual(sea_stage(metadata), 0., places=12)
        self.assertAlmostEqual(sea_stage(tide["metadata"]), -.3*math.sin(2*math.pi*300/43200))
        wave, _ = initial_product("wave")
        self.assertEqual(wave["metadata"]["config"]["bedload"]["wave_direction_xz"], (1, 0))
        self.assertEqual(wave["metadata"]["config"]["tide_amplitude_m"], 0.)

    def test_sampling_spans_two_full_tidal_periods_and_last_three_hours(self):
        stages = dict(schedule())
        self.assertTrue(all(type(value) is float for value in stages.values()))
        for hour in (6, 12, 18, 21, 22, 23, 24):
            self.assertEqual(stages[f"growth_{hour}h"], 300.+3600.*hour)
        times = [300.]+[t for _, t in schedule() if t > 300.]
        self.assertLessEqual(max(np.diff(times)), 5400.)

    def test_generated_growth_forcing_advances_public_solver_from_warmup_time(self):
        bed = np.full((4, 5), -.5)
        product = initialize(bed, np.ones(bed.shape, bool), [12], origin_m_xz=[0., 0.],
            source_world_identity="seed20261020", source_identity="forms-interface-test",
            initial_time_s=dict(schedule())["warmup"],
            config=FVDeltaConfig(coupling_interval_s=10., max_hydro_dt_s=3.))
        start = product["metadata"]["physical_time_s"]
        result = advance(product, [forcing_record("slope", "growth_test", start, start+10.)])
        self.assertEqual(result["metadata"]["physical_time_s"], 310.)
        self.assertEqual(result["metadata"]["ledger"]["solid_input_m3"], 10.)
        self.assertEqual(result["metadata"]["ledger"]["water_input_m3"], 1000.)


if __name__ == "__main__":
    unittest.main()
