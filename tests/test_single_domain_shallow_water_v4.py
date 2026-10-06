import unittest

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import coarsen_cell_field
from terrain_pipeline.single_domain_shallow_water_support_v4 import shallow_water_rhs
from tests import test_single_domain_shallow_water_v3 as v3_tests


class ShallowWaterV4Tests(unittest.TestCase):
    def test_half_wet_lake_and_flat_nonuniform_pressure_source(self):
        helper = v3_tests.ShallowWaterV3Tests()
        canonical = 1350.+np.tile(np.arange(16)*.1, (12, 1))+.05*np.arange(12)[:, None]
        fine_depth = np.maximum(1350.8-canonical, 0.)
        for factor in (1, 2, 4):
            geometry, support, datum = helper.geometry(canonical, factor)
            bed = geometry["arrays"]["H2_m"]
            depth = fine_depth if factor == 1 else coarsen_cell_field(fine_depth, factor=factor)
            state = np.column_stack((depth.ravel(), np.zeros((bed.size, 2))))
            args = dict(support=support, spacing=float(factor), gravity=9.81,
                boundary_kind=geometry["arrays"]["boundary_kind"], tailwater=np.zeros(2*sum(bed.shape)), roughness=.035, dt=.01)
            rhs, _ = shallow_water_rhs(state, bed-datum, **args)
            np.testing.assert_allclose(rhs, 0., rtol=0., atol=2e-12)
            geometry, support, datum = helper.geometry(np.zeros_like(canonical), factor)
            bed = geometry["arrays"]["H2_m"]
            rng = np.random.default_rng(19)
            state = np.column_stack((rng.uniform(.1, 2., bed.size), rng.uniform(-.2, .2, (bed.size, 2))))
            args["support"] = support
            rhs, witness = shallow_water_rhs(state, bed, **args)
            np.testing.assert_allclose(witness["bed_source"], 0., rtol=0., atol=1e-14)
            self.assertAlmostEqual(float(rhs[:, 0].sum()), 0., places=12)
            self.assertTrue(np.all((state+.01*rhs)[:, 0] >= 0))


if __name__ == "__main__":
    unittest.main()
