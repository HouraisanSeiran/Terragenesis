import unittest

import numpy as np

from terrain_pipeline.fine_subgrid import coarsen_cell_field, stage_depths, storage_stages
from terrain_pipeline.shallow_water import single_domain_shallow_water_reconstruction_mechanism_8_prepare_support as prepare_support, reconstruct
from terrain_pipeline.shallow_water import single_domain_shallow_water_support_mechanism_8_shallow_water_rhs as shallow_water_rhs
from terrain_pipeline.surface_hydraulics import prepare_surface_geometry


class ShallowWaterV8Tests(unittest.TestCase):
    def geometry(self, canonical, factor):
        coarse = canonical if factor == 1 else coarsen_cell_field(canonical, factor=factor)
        bed = dict(arrays=dict(canonical_bed_center_m=canonical, H2_m=coarse), metadata=dict(spacing_m=float(factor)))
        support, datum = prepare_support(bed)
        geometry = prepare_surface_geometry(coarse, spacing_m=float(factor), origin_m_xz=[0., 0.], source_identity="synthetic")
        geometry["arrays"].update(support)
        geometry["metadata"]["hydraulic_datum_m"] = datum
        return geometry, support, datum

    def test_linear_stage_inversion_preserves_volume_and_momentum(self):
        canonical = np.random.default_rng(30).uniform(0., 2., (12, 16))
        geometry, support, datum = self.geometry(canonical, 2)
        bed = geometry["arrays"]["H2_m"]
        eta = np.tile(.8+.15*np.arange(8), (6, 1)).ravel()
        depth = stage_depths(eta, support["subcell_bed_relative_m"])
        velocity = np.column_stack((.2+.03*np.tile(np.arange(8), 6), -.1+.02*np.repeat(np.arange(6), 8)))
        state = np.column_stack((depth, depth[:, None]*velocity))
        kind = geometry["arrays"]["boundary_kind"]
        rec = reconstruct(state, bed-datum, support, kind, np.zeros(len(kind)))
        np.testing.assert_allclose(rec["subcell_depth"].mean(axis=(1, 2)), depth, rtol=0., atol=5e-15)
        np.testing.assert_allclose(np.mean(rec["subcell_depth"][:, :, :, None]*rec["subcell_velocity"], axis=(1, 2)), state[:, 1:], rtol=0., atol=5e-15)
        coordinate = (np.arange(2)+.5)/2-.5
        x, z = np.meshgrid(coordinate, coordinate)
        uniform_eta = storage_stages(depth, support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])
        naive = np.maximum(uniform_eta[:, None, None]+rec["slope_x"][:, 0, None, None]*x+
            rec["slope_z"][:, 0, None, None]*z-support["subcell_bed_position_relative_m"], 0.).mean(axis=(1, 2))
        self.assertGreater(float(abs(naive-depth).max()), 1e-4)

    def test_half_wet_uniform_lake_equilibrium(self):
        canonical = 1350.+np.tile(np.arange(16)*.1, (12, 1))+.05*np.arange(12)[:, None]
        fine_depth = np.maximum(1350.8-canonical, 0.)
        for factor in (1, 2, 4):
            geometry, support, datum = self.geometry(canonical, factor)
            bed = geometry["arrays"]["H2_m"]
            depth = fine_depth if factor == 1 else coarsen_cell_field(fine_depth, factor=factor)
            state = np.column_stack((depth.ravel(), np.zeros((bed.size, 2))))
            rhs, _ = shallow_water_rhs(state, bed-datum, support=support, spacing=float(factor), gravity=9.81,
                boundary_kind=geometry["arrays"]["boundary_kind"], tailwater=np.zeros(2*sum(bed.shape)), roughness=.035, dt=.01)
            np.testing.assert_allclose(rhs, 0., rtol=0., atol=2e-12)

    def test_flat_bed_arbitrary_cutoff_source_zero(self):
        for factor in (1, 2, 4):
            geometry, support, _ = self.geometry(np.zeros((12, 16)), factor)
            bed = geometry["arrays"]["H2_m"]
            rng = np.random.default_rng(34)
            depth = rng.uniform(0., .3, bed.size)
            depth[depth < .1] = 0.
            state = np.column_stack((depth, rng.uniform(-.02, .02, (bed.size, 2))*depth[:, None]))
            rhs, witness = shallow_water_rhs(state, bed, support=support, spacing=float(factor), gravity=9.81,
                boundary_kind=geometry["arrays"]["boundary_kind"], tailwater=np.zeros(2*sum(bed.shape)), roughness=.035, dt=.01)
            np.testing.assert_allclose(witness["bed_source"], 0., rtol=0., atol=1e-14)
            self.assertAlmostEqual(float(rhs[:, 0].sum()), 0., places=13)
            self.assertTrue(np.all((state+.01*rhs)[:, 0] >= 0))


if __name__ == "__main__":
    unittest.main()
