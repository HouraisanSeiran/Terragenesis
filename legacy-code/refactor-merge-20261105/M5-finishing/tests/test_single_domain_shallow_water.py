import unittest

import numpy as np

from terrain_pipeline.shallow_water import hydrostatic_hll, single_domain_shallow_water_support_shallow_water_rhs as shallow_water_rhs
from terrain_pipeline.shallow_water import advance_shallow_water
from terrain_pipeline.surface_hydraulics import prepare_surface_geometry, SurfaceBudget


class ShallowWaterTests(unittest.TestCase):
    def execute(self,bed,depth):
        geometry=prepare_surface_geometry(bed,spacing_m=1.,origin_m_xz=[0.,0.],source_identity="synthetic")
        intervals=[]
        momenta=[]
        result=advance_shallow_water(geometry,initial_depth_m=depth,forcing_interval_s=.1,intervals=2,
            forcing_provider=lambda i:np.zeros_like(bed),boundary_stage_provider=lambda i:np.zeros(2*sum(bed.shape)),
            source_identity="synthetic",forcing_identity="synthetic",budget=SurfaceBudget(max_dt_s=.01,max_snapshots=4),
            snapshot_interval_s=.1,interval_observer=intervals.append,momentum_observer=momenta.append)
        return result,geometry,intervals,momenta

    def test_1350m_sloped_lake_execution_and_interval_momentum_closure(self):
        bed=1350.+np.array([[0.,.1,.2],[.05,.15,.25]])
        depth=1350.4-bed
        result,g,intervals,_=self.execute(bed,depth)
        np.testing.assert_allclose(result["arrays"]["depth_m"][-1],depth,rtol=0.,atol=1e-12)
        for packet in intervals:
            net=np.zeros((bed.size,2))
            np.add.at(net,g["arrays"]["face_left"],-packet["internal_momentum_transfer"])
            np.add.at(net,g["arrays"]["face_right"],packet["internal_momentum_transfer"])
            np.add.at(net,g["arrays"]["boundary_cell"],-packet["boundary_momentum_transfer"])
            expected=net+packet["bed_momentum_change"]+packet["manning_momentum_change"]
            np.testing.assert_allclose(packet["momentum_after"]-packet["momentum_before"],expected,rtol=0.,atol=1e-14)

    def test_flat_uniform_advective_momentum_flux(self):
        state=np.array([[2.,6.,4.]])
        flux,cl,cr,speed=hydrostatic_hll(state,state,np.array([0.]),np.array([0.]),gravity=9.81,axis=0)
        np.testing.assert_allclose(flux,[[6.,18.+19.62,12.]],rtol=0.,atol=1e-12)
        self.assertEqual(cl[0],0.)
        self.assertEqual(cr[0],0.)

    def test_sloped_bed_uniform_stage_well_balanced(self):
        bed=np.array([[0.,.1,.2],[.05,.15,.25]])
        depth=.4-bed
        state=np.column_stack((depth.ravel(),np.zeros((6,2))))
        rhs,witness=shallow_water_rhs(state,bed,spacing=1.,gravity=9.81,
            boundary_kind=np.zeros(10,np.int64),tailwater=np.full(10,.4),roughness=.035,dt=.01)
        np.testing.assert_allclose(rhs,0.,rtol=0.,atol=1e-14)

    def test_partially_dry_lake_uniform_stage_well_balanced(self):
        bed=np.array([[0.,.1,.2],[.05,.15,.25]])
        depth=np.maximum(.13-bed,0.)
        state=np.column_stack((depth.ravel(),np.zeros((6,2))))
        rhs,_=shallow_water_rhs(state,bed,spacing=1.,gravity=9.81,
            boundary_kind=np.zeros(10,np.int64),tailwater=np.full(10,.13),roughness=.035,dt=.01)
        np.testing.assert_allclose(rhs,0.,rtol=0.,atol=1e-14)

    def test_dam_front_mass_conservation_and_positive_forward_euler(self):
        bed=np.zeros((2,8))
        depth=np.zeros_like(bed)
        depth[:,:4]=1.
        state=np.column_stack((depth.ravel(),np.zeros((16,2))))
        rhs,w=shallow_water_rhs(state,bed,spacing=1.,gravity=9.81,
            boundary_kind=np.zeros(20,np.int64),tailwater=np.zeros(20),roughness=.035,dt=.01)
        self.assertAlmostEqual(rhs[:,0].sum(),0.,places=13)
        self.assertTrue(np.all((state+.01*rhs)[:,0] >= 0))
        self.assertGreater(np.max(w["internal_flux"][:,0]),0.)


if __name__ == "__main__":
    unittest.main()
