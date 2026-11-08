import unittest

import numpy as np

from terrain_pipeline.fine_subgrid import coarsen_cell_field
from terrain_pipeline.shallow_water import _single_domain_shallow_water_support_mechanism_6_reconstruct as _reconstruct, single_domain_shallow_water_support_mechanism_6_shallow_water_rhs as shallow_water_rhs
from terrain_pipeline.shallow_water import single_domain_shallow_water_mechanism_6_advance_shallow_water as advance_shallow_water
from terrain_pipeline.surface_hydraulics import SurfaceBudget
from tests import test_single_domain_shallow_water_v3 as v3_tests


class ShallowWaterV6Tests(unittest.TestCase):
    def test_dry_neighbor_has_no_free_surface_constraint_and_positivity(self):
        canonical = np.full((4, 8), 2.)
        canonical[:, -1] = 0.
        geometry, support, _ = v3_tests.ShallowWaterV3Tests().geometry(canonical, 1)
        bed = geometry["arrays"]["H2_m"]
        stage = bed.ravel().copy()
        stage.reshape(bed.shape)[:, -1] = 1.
        depth = np.maximum(stage-bed.ravel(), 0.)
        kind = np.zeros(24, np.int64)
        kind[4:8] = 2
        tail = np.full(24, 1.5)
        faces = _reconstruct(stage, np.zeros((bed.size, 2)), depth, bed, support, kind, tail)
        np.testing.assert_allclose(faces[1].reshape(4, 8, 3)[:, -1, 0], 1.5, rtol=0., atol=1e-14)
        tail[4:8] = 10.
        faces = _reconstruct(stage, np.zeros((bed.size, 2)), depth, bed, support, kind, tail)
        for face in faces:
            self.assertTrue(np.all(face[depth > 0, 0] >= 0))
        state = np.column_stack((depth, np.zeros((bed.size, 2))))
        rhs, _ = shallow_water_rhs(state, bed, support=support, spacing=1., gravity=9.81,
            boundary_kind=kind, tailwater=tail, roughness=.035, dt=.01)
        self.assertTrue(np.all((state+.01*rhs)[:, 0] >= 0))

    def test_reservoir_stage_is_a_face_value_for_linear_reconstruction(self):
        geometry, support, _ = v3_tests.ShallowWaterV3Tests().geometry(np.zeros((4, 8)), 1)
        bed = geometry["arrays"]["H2_m"]
        stage = np.tile(1.+.01*(np.arange(8)+.5), (4, 1)).ravel()
        kind = np.zeros(24, np.int64)
        kind[:8] = 2
        tail = np.ones(24)
        tail[4:8] = 1.08
        faces = _reconstruct(stage, np.zeros((bed.size, 2)), stage, bed, support, kind, tail)
        np.testing.assert_allclose(faces[0].reshape(4, 8, 3)[:, 0, 0], 1., rtol=0., atol=1e-14)
        np.testing.assert_allclose(faces[1].reshape(4, 8, 3)[:, -1, 0], 1.08, rtol=0., atol=1e-14)

    def test_open_half_wet_lake_and_flat_arbitrary_state_source(self):
        canonical = 1350.+np.tile(np.arange(16)*.1, (12, 1))+.05*np.arange(12)[:, None]
        fine_depth = np.maximum(1350.8-canonical, 0.)
        helper = v3_tests.ShallowWaterV3Tests()
        for factor in (1, 2, 4):
            geometry, support, datum = helper.geometry(canonical, factor)
            bed = geometry["arrays"]["H2_m"]
            depth = fine_depth if factor == 1 else coarsen_cell_field(fine_depth, factor=factor)
            state = np.column_stack((depth.ravel(), np.zeros((bed.size, 2))))
            kind = np.full(2*sum(bed.shape), 2, np.int64)
            args = dict(support=support, spacing=float(factor), gravity=9.81, boundary_kind=kind,
                tailwater=np.full(len(kind), 1350.8-datum), roughness=.035, dt=.01)
            rhs, _ = shallow_water_rhs(state, bed-datum, **args)
            np.testing.assert_allclose(rhs, 0., rtol=0., atol=2e-12)
            geometry, support, _ = helper.geometry(np.zeros_like(canonical), factor)
            bed = geometry["arrays"]["H2_m"]
            rng = np.random.default_rng(24)
            state = np.column_stack((rng.uniform(.1, 2., bed.size), rng.uniform(-.2, .2, (bed.size, 2))))
            args["support"] = support
            args["tailwater"] = np.ones(len(kind))
            rhs, witness = shallow_water_rhs(state, bed, **args)
            np.testing.assert_allclose(witness["bed_source"], 0., rtol=0., atol=1e-14)
            self.assertTrue(np.all((state+.01*rhs)[:, 0] >= 0))

    def test_reservoir_pulse_wave_enters_interior_and_conserves_import(self):
        geometry, _, _ = v3_tests.ShallowWaterV3Tests().geometry(np.zeros((8, 80)), 2)
        bed = geometry["arrays"]["H2_m"]
        rows, columns = bed.shape
        geometry["arrays"]["boundary_kind"][rows:2*rows] = 2
        tail = np.ones(2*(rows+columns))
        tail[rows:2*rows] = 1.5
        result = advance_shallow_water(geometry, initial_depth_m=np.ones_like(bed), forcing_interval_s=2., intervals=1,
            forcing_provider=lambda i: np.zeros_like(bed), boundary_stage_provider=lambda i: tail,
            source_identity="synthetic", forcing_identity="reservoir-pulse",
            budget=SurfaceBudget(max_dt_s=.025, max_snapshots=3, max_duration_s=2.), snapshot_interval_s=2.,
            interval_observer=lambda packet: None, momentum_observer=lambda packet: None)
        final = result["arrays"]["depth_m"][-1]
        self.assertGreater(float(final[:, -2].min()), 1.01)
        self.assertLess(float(result["arrays"]["momentum_x_m2_s"][-1, :, -2].max()), -.01)
        np.testing.assert_allclose(final[:, :columns//2], 1., rtol=0., atol=1e-12)
        self.assertGreater(result["metadata"]["boundary_input_m3"], 0.)
        self.assertLess(abs(result["arrays"]["ledger"][-1, -1]), 1e-9)


if __name__ == "__main__":
    unittest.main()


