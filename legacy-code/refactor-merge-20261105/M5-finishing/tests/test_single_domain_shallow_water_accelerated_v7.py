import unittest

import numpy as np

from tests import test_single_domain_shallow_water_v3 as fixtures
from terrain_pipeline.surface_hydraulics import SurfaceBudget
from terrain_pipeline.shallow_water import single_domain_shallow_water_support_mechanism_3_shallow_water_rhs as reference_rhs, single_domain_shallow_water_support_mechanism_7_manning_damping as reference_drag
from terrain_pipeline.shallow_water import single_domain_shallow_water_mechanism_7_advance_shallow_water as reference_advance
from terrain_pipeline.shallow_water import shallow_water_rhs as accelerated_rhs, manning_damping as accelerated_drag, single_domain_shallow_water_accelerated_mechanism_7_advance_shallow_water as accelerated_advance


class AcceleratedV7Tests(unittest.TestCase):
    def test_extreme_thin_and_dry_states_remain_finite_and_equivalent(self):
        geometry,support,_ = fixtures.ShallowWaterV3Tests().geometry(np.zeros((12,16)),1)
        bed = geometry["arrays"]["H2_m"]
        depth = np.resize(np.array([0.,1e-300,1e-100,1e-20,.1,1.]),bed.size)
        state = np.column_stack((depth,.01*depth,-.02*depth))
        args = dict(support=support,spacing=1.,gravity=9.81,boundary_kind=geometry["arrays"]["boundary_kind"],
            tailwater=np.zeros(2*sum(bed.shape)),roughness=.035,dt=.01)
        expected,_ = reference_rhs(state,bed,**args)
        actual,_ = accelerated_rhs(state,bed,**args)
        self.assertTrue(np.isfinite(actual).all())
        np.testing.assert_allclose(actual,expected,atol=2e-12,rtol=2e-12)
        for actual_value,expected_value in zip(accelerated_drag(state,.01,9.81,.035,support=support),reference_drag(state,.01,9.81,.035,support=support)):
            self.assertTrue(np.isfinite(actual_value).all())
            np.testing.assert_allclose(actual_value,expected_value,atol=2e-12,rtol=2e-12)

    def test_explicit_fine_backend_binding_and_independent_physical_audit(self):
        from tests.test_single_domain_fine_geometry import fixture
        from terrain_pipeline.fine_subgrid import build_fine_geometry
        from terrain_pipeline.fine_subgrid import run_fine_hydraulics
        from terrain_pipeline.fine_subgrid import validate_fine_states, validate_fine_interval, validate_fine_momentum
        from tools.single_domain_shallow_water_audit import audit_momentum
        hierarchy,_ = fixture()
        bed = build_fine_geometry(hierarchy,native_window=[0,2,0,2],source_hierarchy_sha256="a"*64,spacing_m=2.)
        shape = bed["arrays"]["bed_center_m"].shape
        options = dict(rain_mm_h=np.zeros((2,*shape)),boundary_kind=np.zeros(2*sum(shape),np.int64),
            boundary_stage_m=np.zeros((2,2*sum(shape))),forcing_interval_s=.05,initial_depth_m=np.full(shape,.1),
            budget=SurfaceBudget(max_dt_s=.01,max_snapshots=4,max_wall_s=1800.))
        reference = run_fine_hydraulics(bed,backend="shallow_water_subgrid_manning",**options)
        actual = run_fine_hydraulics(bed,backend="shallow_water_subgrid_manning_accelerated",**options)
        self.assertEqual(reference["geometry"]["identity_sha256"],actual["geometry"]["identity_sha256"])
        for name,values in reference["states"]["arrays"].items():
            np.testing.assert_allclose(actual["states"]["arrays"][name],values,atol=2e-11,rtol=2e-12)
        self.assertIn("numba",actual["states"]["metadata"]["solver_metadata"]["execution_backend"])
        validate_fine_states(actual["states"],bed=bed,geometry=actual["geometry"],forcing=actual["forcing"])
        raw_geometry = dict(actual["geometry"]["arrays"],hydraulic_datum_m=actual["geometry"]["metadata"]["hydraulic_datum_m"])
        previous = None
        for number,packet in enumerate(actual["intervals"]):
            validate_fine_interval(packet,bed=bed,geometry=actual["geometry"],forcing=actual["forcing"],interval=number,previous=previous)
            validate_fine_momentum(actual["momenta"][number],bed=bed,geometry=actual["geometry"],forcing=actual["forcing"],states=actual["states"],interval=number,interval_packet=packet)
            momentum = actual["momenta"][number]
            audit_momentum(momentum["arrays"],momentum["metadata"],raw_geometry,2.,actual["states"]["metadata"]["solver_metadata"]["budget"],
                actual["forcing"]["arrays"]["local_q_m3_s"][number],actual["forcing"]["arrays"]["boundary_stage_m"][number])
            previous = packet

    def test_random_flat_partial_wet_boundaries_and_limiter_equivalence(self):
        rng = np.random.default_rng(718)
        limited_cases = 0
        for factor in (1,2,4):
            for flat in (False,True):
                canonical = np.zeros((12,16)) if flat else rng.uniform(0.,2.,(12,16))
                geometry,support,datum = fixtures.ShallowWaterV3Tests().geometry(canonical,factor)
                arrays = geometry["arrays"]
                bed = arrays["H2_m"]
                depth = rng.uniform(.001,.3,bed.size)
                depth[rng.random(bed.size)<.3] = 0
                state = np.column_stack((depth,depth[:,None]*rng.uniform(-3.,3.,(bed.size,2))))
                kinds = np.arange(len(arrays["boundary_kind"]),dtype=np.int64)%3
                tailwater = rng.uniform(0.,2.,len(kinds))
                for dt in (0.,.01,5.):
                    args = dict(support=support,spacing=float(factor),gravity=9.81,boundary_kind=kinds,tailwater=tailwater,
                        roughness=.035,dt=dt,boundary_crest=arrays["boundary_crest_m"]-datum+.05)
                    expected,witness = reference_rhs(state,bed-datum,**args)
                    actual,jit_witness = accelerated_rhs(state,bed-datum,**args)
                    np.testing.assert_allclose(actual,expected,atol=2e-11,rtol=2e-12)
                    for name in ("internal_flux","boundary_flux","bed_source"):
                        np.testing.assert_allclose(jit_witness[name],witness[name],atol=2e-11,rtol=2e-12)
                    for name in ("maximum_wave_speed","minimum_limiter_factor"):
                        self.assertAlmostEqual(jit_witness[name],witness[name],places=12)
                    self.assertEqual(jit_witness["limited_donors"],witness["limited_donors"])
                    limited_cases += witness["limited_donors"]>0
                    expected_drag = reference_drag(state,dt,9.81,.035,support=support)
                    actual_drag = accelerated_drag(state,dt,9.81,.035,support=support)
                    for a,b in zip(actual_drag,expected_drag):
                        np.testing.assert_allclose(a,b,atol=2e-12,rtol=2e-12)
        self.assertGreater(limited_cases,0)

    def test_closed_half_wet_lake_and_flat_dam_pressure_equivalence(self):
        canonical = 1350.+np.tile(np.arange(16)*.1,(12,1))+.05*np.arange(12)[:,None]
        for factor in (1,2,4):
            geometry,support,datum = fixtures.ShallowWaterV3Tests().geometry(canonical,factor)
            bed = geometry["arrays"]["H2_m"]
            h = np.maximum(1350.8-canonical,0).reshape(12//factor,factor,16//factor,factor).mean(axis=(1,3))
            state = np.column_stack((h.ravel(),np.zeros((h.size,2))))
            rhs,_ = accelerated_rhs(state,bed-datum,support=support,spacing=float(factor),gravity=9.81,
                boundary_kind=geometry["arrays"]["boundary_kind"],tailwater=np.zeros(2*sum(bed.shape)),roughness=.035,dt=.01)
            np.testing.assert_allclose(rhs,0,atol=2e-12,rtol=0)
        geometry,support,_ = fixtures.ShallowWaterV3Tests().geometry(np.zeros((12,16)),2)
        bed = geometry["arrays"]["H2_m"]
        h = np.ones_like(bed)
        h[:,:4] = 2
        rhs,witness = accelerated_rhs(np.column_stack((h.ravel(),np.zeros((h.size,2)))),bed,support=support,spacing=2.,gravity=9.81,
            boundary_kind=geometry["arrays"]["boundary_kind"],tailwater=np.zeros(2*sum(bed.shape)),roughness=.035,dt=.01)
        np.testing.assert_allclose(witness["bed_source"],0,atol=1e-14,rtol=0)
        self.assertGreater(rhs[:,1].max(),1.)

    def test_short_evolution_and_saved_witness_equivalence(self):
        canonical = np.random.default_rng(720).uniform(0.,.3,(12,16))
        geometry,_,_ = fixtures.ShallowWaterV3Tests().geometry(canonical,2)
        arrays = geometry["arrays"]
        bed = arrays["H2_m"]
        arrays["boundary_kind"][6:12] = 2
        packets = []
        outputs = []
        for advance in (reference_advance,accelerated_advance):
            intervals,momenta = [],[]
            output = advance(geometry,initial_depth_m=np.full(bed.shape,.2),forcing_interval_s=.1,intervals=3,
                forcing_provider=lambda i:np.full(bed.shape,.0001),boundary_stage_provider=lambda i:np.full(2*sum(bed.shape),.7+i*.1),
                source_identity="equivalence",forcing_identity="equivalence",budget=SurfaceBudget(max_dt_s=.01,max_snapshots=5),
                snapshot_interval_s=.1,interval_observer=intervals.append,momentum_observer=momenta.append)
            outputs.append(output)
            packets.append((intervals,momenta))
        for name,expected in outputs[0]["arrays"].items():
            np.testing.assert_allclose(outputs[1]["arrays"][name],expected,atol=2e-11,rtol=2e-12)
        for field in ("substeps","face_evaluations"):
            self.assertEqual(outputs[0]["metadata"][field],outputs[1]["metadata"][field])
        for expected_group,actual_group in zip(packets[0],packets[1]):
            for expected,actual in zip(expected_group,actual_group):
                self.assertEqual(set(expected),set(actual))
                for name in expected:
                    np.testing.assert_allclose(actual[name],expected[name],atol=2e-11,rtol=2e-12)


if __name__=="__main__":
    unittest.main()
