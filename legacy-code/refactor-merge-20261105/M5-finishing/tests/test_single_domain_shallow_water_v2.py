import unittest

import numpy as np

from terrain_pipeline.shallow_water import single_domain_shallow_water_support_mechanism_2_reconstruct as reconstruct, single_domain_shallow_water_support_mechanism_2_shallow_water_rhs as shallow_water_rhs
from terrain_pipeline.shallow_water import single_domain_shallow_water_mechanism_2_advance_shallow_water as advance_shallow_water
from terrain_pipeline.surface_hydraulics import prepare_surface_geometry, SurfaceBudget


class ShallowWaterV2Tests(unittest.TestCase):
    def test_execution_static_lake_and_momentum_closure(self):
        bed = 1350.+np.tile(np.arange(10)*.1, (6, 1))+.05*np.arange(6)[:, None]
        for stage in (1350.5, 1352.):
            depth = np.maximum(stage-bed, 0.)
            geometry = prepare_surface_geometry(bed, spacing_m=1., origin_m_xz=[0., 0.], source_identity="synthetic")
            packets = []
            result = advance_shallow_water(geometry, initial_depth_m=depth, forcing_interval_s=.1, intervals=2,
                forcing_provider=lambda i: np.zeros_like(bed), boundary_stage_provider=lambda i: np.zeros(2*sum(bed.shape)),
                source_identity="synthetic", forcing_identity="synthetic", budget=SurfaceBudget(max_dt_s=.01, max_snapshots=4),
                snapshot_interval_s=.1, interval_observer=packets.append, momentum_observer=lambda packet: None)
            np.testing.assert_allclose(result["arrays"]["depth_m"][-1], depth, rtol=0., atol=1e-12)
            for packet in packets:
                net = np.zeros((bed.size, 2))
                a = geometry["arrays"]
                np.add.at(net, a["face_left"], -packet["internal_momentum_transfer"])
                np.add.at(net, a["face_right"], packet["internal_momentum_transfer"])
                np.add.at(net, a["boundary_cell"], -packet["boundary_momentum_transfer"])
                expected = net+packet["bed_momentum_change"]+packet["manning_momentum_change"]
                np.testing.assert_allclose(packet["momentum_after"]-packet["momentum_before"], expected, rtol=0., atol=1e-13)

    def test_sloped_uniform_stage_and_dry_shore(self):
        bed = np.tile(np.arange(10)*.1, (6, 1))+.05*np.arange(6)[:, None]
        for stage in (.5, 2.):
            depth = np.maximum(stage-bed, 0.)
            state = np.column_stack((depth.ravel(), np.zeros((bed.size, 2))))
            rhs, witness = shallow_water_rhs(state, bed, spacing=1., gravity=9.81,
                boundary_kind=np.zeros(2*sum(bed.shape), np.int64), tailwater=np.full(2*sum(bed.shape), stage),
                roughness=.035, dt=.01)
            np.testing.assert_allclose(rhs, 0., rtol=0., atol=1e-13)

    def test_positive_reconstruction_and_closed_mass(self):
        bed = np.zeros((6, 10))
        depth = np.random.default_rng(12).random(bed.shape)
        depth[depth < .3] = 0.
        state = np.column_stack((depth.ravel(), np.zeros((bed.size, 2))))
        faces, _ = reconstruct(state, bed)
        self.assertTrue(all(np.all(face[:, 0] >= 0) for face in faces))
        rhs, _ = shallow_water_rhs(state, bed, spacing=1., gravity=9.81,
            boundary_kind=np.zeros(2*sum(bed.shape), np.int64), tailwater=np.zeros(2*sum(bed.shape)), roughness=.035, dt=.01)
        self.assertAlmostEqual(float(rhs[:, 0].sum()), 0., places=12)
        self.assertTrue(np.all((state+.01*rhs)[:, 0] >= 0))


if __name__ == "__main__":
    unittest.main()
