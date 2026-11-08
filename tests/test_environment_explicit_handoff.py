from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline import environment_product as api
from tests.test_environment_process_product import fixture
from tests.test_environment_mass_processes import rates


class ExplicitHandoffTests(unittest.TestCase):
    def initial(self, mode):
        return api.initialize(fixture()["context"], initial={
            "mass": {"bedrock_thickness_m": .1, "bed_hardness": 0.},
            "groundwater": {"surface_water_m3": 1.}}, mode=mode)

    def driving(self):
        return {"hydraulic_handoff_mask": np.ones((5, 5), bool),
                "groundwater": {"surface_conductance_m2_s": 0.},
                "mass": {"weathering_parameters": rates(.01), "transport_fraction_per_s": 1.}}

    def test_old_explicit_refuses_new_export_field(self):
        with self.assertRaisesRegex(ValueError, "unsupported product forcing"):
            api.advance(self.initial("explicit"), self.driving(), 1.)

    def test_new_explicit_debits_actual_water_solid_and_cold_loads(self):
        initial = self.initial("explicit-v2")
        result = api.advance(initial, self.driving(), 1.)
        self.assertEqual(result["algorithm"], "finite-environment-process-coupling-v2")
        self.assertNotIn("seasonal", result)
        for key in ("external_hydraulic_water_m3", "external_hydraulic_solid_m3"):
            self.assertGreater(result["last_transfers"][key].sum(), 0.)
            self.assertEqual(result["last_transfers"][key].sum(), result["cumulative_ledger"][key])
        np.testing.assert_array_equal(result["states"]["groundwater"]["surface_water_m3"], 0.)
        np.testing.assert_array_equal(result["states"]["mass"]["river_sediment_solid_m3"], 0.)
        self.assertLess(abs(result["last_budget"]["water_m3_residual"]), 1.e-8)
        self.assertLess(abs(result["last_budget"]["solid_m3_residual"]), 1.e-8)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "explicit-v2.npz"
            sha = api.save_product(result, path)
            cold = api.load_product(path, expected_sha256=sha)
            self.assertEqual(api.product_identity(result), api.product_identity(cold))
