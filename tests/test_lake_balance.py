import unittest
import numpy as np
from terrain_pipeline.lake import LakeBalanceRecipe as LakeBalanceRecipe
from terrain_pipeline.lake import evaluate_lake_balance as evaluate_lake_balance


def basin_fixture():
    height = np.full((7, 7), 4.)
    height[2:5, 2:5] = 1.
    height[3, 5] = 3.
    height[3, 6] = 2.
    basin = np.zeros((7, 7), bool); basin[2:5, 2:5] = True
    domain = np.ones((7, 7), bool)
    protected = np.zeros((7, 7), bool)
    legal = np.zeros((7, 7), bool); legal[3, 6] = True
    return height, basin, domain, protected, legal


class LakeBalanceTests(unittest.TestCase):
    def test_closed_basin_storage_and_finite_flux_balance(self):
        height, basin, domain, protected, legal = basin_fixture()
        result = evaluate_lake_balance(height, basin, (3, 5), 1., 1., "synthetic-basin",
            LakeBalanceRecipe(10., 2., 0., 1., 3., 2.),
            [(3,5),(3,6)], domain, protected, legal)
        self.assertEqual(result["summary"]["spill_capacity_m3"], 18.)
        self.assertEqual(result["summary"]["spill_outflow_m3_s"], 2.)
        self.assertEqual(result["summary"]["final_stage_m"], 3.)
        self.assertAlmostEqual(result["summary"]["balance_residual_m3"], 0.)
        self.assertTrue(result["summary"]["balance_valid"])

    def test_missing_spill_leak_and_excess_peak_rejected(self):
        height, basin, domain, protected, legal = basin_fixture()
        with self.assertRaises(ValueError):
            evaluate_lake_balance(height, basin, (0, 0), 1., 1., "synthetic-basin",
                LakeBalanceRecipe(10., 2., 0., 1., 3., 1.), [(0,0),(0,1)], domain, protected, legal)
        result = evaluate_lake_balance(height, basin, (3, 5), 1., 1., "synthetic-basin",
            LakeBalanceRecipe(10., 2., 0., 1., 3., 1.), [(3,5),(3,6)], domain, protected, legal)
        self.assertFalse(result["summary"]["balance_valid"])
        height[2, 5] = 2.
        with self.assertRaises(ValueError):
            evaluate_lake_balance(height, basin, (3, 5), 1., 1., "synthetic-basin",
                LakeBalanceRecipe(10., 2., 0., 1., 3., 2.), [(3,5),(3,6)], domain, protected, legal)


if __name__ == "__main__": unittest.main()
