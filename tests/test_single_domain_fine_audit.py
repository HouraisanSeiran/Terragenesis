"""Independent mathematical audits without production geometry construction."""

import copy
import unittest
from unittest.mock import patch

import numpy as np

from tools.audit_single_domain_fine_stage import canonical_reference,audit_initial_contract,audit_bed
from terrain_pipeline.single_domain_fine_io import canonical_bed_fields,validate_canonical_bed


def sample():
    source = dict(height_m=np.ones((2,2)),receiver=np.array([-1,-1,-1,-1]),
                  valid_mask=np.ones((2,2),bool),protected_mask=np.zeros((2,2),bool))
    arrays = {"native_"+key:value.copy() for key,value in source.items()}
    arrays.update(selected_edge_cell_ids=np.empty((0,2),np.int64),native_bilinear_corner_m=np.ones((2,2)),
                  cut_corner_m=np.zeros((2,2)),bed_corner_m=np.ones((2,2)),bed_center_m=np.ones((1,1)),
                  canonical_bed_center_m=np.ones((30,30)),
                  bed_vertices_xyz_m=np.array([[0.,1.,0.],[0.,1.,30.],[30.,1.,30.],[30.,1.,0.],[15.,1.,15.]]),
                  bed_triangles=np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]],np.int64))
    metadata = dict(native_window=[0,1,0,1],spacing_m=30.)
    return source,arrays,metadata


class FineAuditTests(unittest.TestCase):
    def test_canonical_manning_uniform_velocity_contract(self):
        from tools.single_domain_shallow_water_audit import canonical_manning
        for depths in ([.5,.5],[.1,.9],[0.,1.],[0.,.1],[0.,0.]):
            h = np.asarray(depths)
            stage = float(h.max())
            subbed = np.sort((stage-h)[None,:],axis=1)
            mean = float(h.mean())
            state = np.array([[mean,.5*mean,0.]])
            damping,factor = canonical_manning(state,subbed,.1,9.81,.035)
            expected_i = sum(value**(-1/3) for value in h if value>0)/len(h)
            expected = mean/(mean+.1*9.81*.035**2*.5*expected_i) if mean>0 else 0
            self.assertAlmostEqual(factor[0],expected_i,places=12)
            self.assertAlmostEqual(damping[0],expected,places=12)

    def test_v3_independent_subgrid_pressure_storage_and_flat_invariants(self):
        from tests.test_single_domain_shallow_water_v3 import ShallowWaterV3Tests
        from tools.single_domain_shallow_water_audit import physical_witness,MODEL_V3
        from terrain_pipeline.single_domain_shallow_water_support_v3 import shallow_water_rhs
        canonical = 1350.+np.tile(np.arange(16)*.1,(12,1))+.05*np.arange(12)[:,None]
        for factor in (1,2,4):
            geometry,support,datum = ShallowWaterV3Tests().geometry(canonical,factor)
            g = dict(geometry["arrays"],hydraulic_datum_m=datum)
            h = np.maximum(1350.8-canonical,0).reshape(12//factor,factor,16//factor,factor).mean(axis=(1,3))
            state = np.column_stack((h.ravel(),np.zeros((h.size,2))))
            args = dict(spacing=float(factor),gravity=9.81,boundary_kind=g["boundary_kind"],tailwater=np.zeros(2*sum(h.shape)),roughness=.035,dt=.01)
            expected,witness = shallow_water_rhs(state,g["H2_m"]-datum,support=support,**args)
            actual = physical_witness(state,g,float(factor),9.81,args["tailwater"]+datum,.01,model=MODEL_V3)
            for a,b in zip(actual,(expected,witness["internal_flux"],witness["boundary_flux"],witness["bed_source"])):
                np.testing.assert_allclose(a,b,atol=2e-12,rtol=0)
            np.testing.assert_allclose(actual[0],0,atol=2e-12,rtol=0)
        geometry,_,datum = ShallowWaterV3Tests().geometry(np.zeros((12,16)),2)
        g = dict(geometry["arrays"],hydraulic_datum_m=datum)
        h = np.linspace(.1,1.,g["H2_m"].size)
        state = np.column_stack((h,np.zeros((len(h),2))))
        rhs,_,_,source = physical_witness(state,g,2.,9.81,np.zeros(len(g["boundary_cell"])),.01,model=MODEL_V3)
        np.testing.assert_allclose(source,0,atol=1e-14,rtol=0)
        self.assertGreater(np.linalg.norm(rhs[:,1:]),0)

    def test_flat_bed_source_zero_and_dam_break_pressure_accelerates(self):
        from tests.test_single_domain_fine_hydraulics import run_fixture
        from tools.single_domain_shallow_water_audit import physical_witness,MODEL,MODEL_V2
        result = run_fixture(backend="shallow_water")
        geometry = copy.deepcopy(result["geometry"]["arrays"])
        geometry["H2_m"][:] = 0
        geometry["boundary_crest_m"][:] = 0
        state = np.column_stack((np.array([1.,.4,.1,1.,.4,.1]),np.zeros((6,2))))
        for model in (MODEL,MODEL_V2):
            rhs,_,_,source = physical_witness(state,geometry,1.,9.81,np.zeros(10),.01,model=model)
            np.testing.assert_array_equal(source,np.zeros((6,3)))
            self.assertGreater(np.linalg.norm(rhs[:,1:]),0)
            self.assertGreater(np.max(abs(rhs[:,0])),0)

    def test_v2_independent_reconstruction_flux_and_pressure_match_saved_witness(self):
        from tests.test_single_domain_fine_hydraulics import run_fixture
        from tools.single_domain_shallow_water_audit import physical_witness,MODEL_V2
        from terrain_pipeline.single_domain_shallow_water_support_v2 import shallow_water_rhs
        result = run_fixture(backend="shallow_water")
        geometry = result["geometry"]["arrays"]
        state = np.column_stack((np.array([.2,.1,0,.1,.05,.2]),np.array([.02,-.01,0,.01,0,-.02]),np.array([.01,0,0,-.01,.01,0])))
        kinds = geometry["boundary_kind"].copy()
        kinds[2:4] = 2
        geometry["boundary_kind"] = kinds
        tail = np.full(10,.25)
        actual = physical_witness(state,geometry,1.,9.81,tail,.01,model=MODEL_V2)
        expected,witness = shallow_water_rhs(state,geometry["H2_m"],spacing=1.,gravity=9.81,boundary_kind=kinds,
            tailwater=tail,roughness=.03,dt=.01,boundary_crest=geometry["boundary_crest_m"])
        for first,second in zip(actual,(expected,witness["internal_flux"],witness["boundary_flux"],witness["bed_source"])):
            np.testing.assert_allclose(first,second,atol=1e-12,rtol=1e-12)

    def test_physical_hll_rejects_coordinated_algebra_consistent_witness(self):
        from tests.test_single_domain_fine_hydraulics import run_fixture
        from tools.single_domain_shallow_water_audit import audit_momentum
        from terrain_pipeline.single_domain_fine_io import validate_fine_momentum,_saved_flux_divergence
        from terrain_pipeline.mountain_source_adapter import identity
        result = run_fixture(backend="shallow_water",initial_depth_m=np.full((2,3),.1))
        witness = copy.deepcopy(result["momenta"][0])
        geometry = result["geometry"]
        forcing = result["forcing"]["arrays"]
        budget = result["states"]["metadata"]["solver_metadata"]["budget"]
        with (patch("terrain_pipeline.single_domain_shallow_water_support.hydrostatic_hll",side_effect=RuntimeError("forbidden")),
              patch("terrain_pipeline.single_domain_shallow_water_support.shallow_water_rhs",side_effect=RuntimeError("forbidden"))):
            audit_momentum(witness["arrays"],witness["metadata"],geometry["arrays"],1.,budget,forcing["local_q_m3_s"][0],forcing["boundary_stage_m"][0])
            a = witness["arrays"]
            a["rk2_internal_flux"][0] += np.array([.001,.002,.003])
            rhs = _saved_flux_divergence(geometry,a["rk2_internal_flux"],a["rk2_boundary_flux"])+a["rk2_bed_source"]
            rhs[:,0] += a["forcing_m3_s"]
            undamped = .5*a["state_before"]+.5*(a["state_predictor"]+witness["metadata"]["dt_s"]*rhs)
            a["state_after"] = undamped.copy()
            wet = undamped[:,0]>0
            drag = budget["gravity_m_s2"]*budget["roughness_s_m_third"]**2*np.linalg.norm(undamped[wet,1:],axis=1)/undamped[wet,0]**(7/3)
            a["state_after"][wet,1:] /= (1+witness["metadata"]["dt_s"]*drag)[:,None]
            a["manning_momentum_change"] = a["state_after"][:,1:]-undamped[:,1:]
            witness["identity_sha256"] = identity(a,witness["metadata"])
            validate_fine_momentum(witness,bed=result["bed"],geometry=geometry,forcing=result["forcing"],
                states=result["states"],interval=0,interval_packet=result["intervals"][0])
            with self.assertRaisesRegex(ValueError,"physical RK2 internal_flux"):
                audit_momentum(a,witness["metadata"],geometry["arrays"],1.,budget,forcing["local_q_m3_s"][0],forcing["boundary_stage_m"][0])

    def test_true_triangle_mean_detects_center_equal_wrong_h2(self):
        source,arrays,metadata = sample()
        self.assertTrue(audit_bed(arrays,metadata,source)["triangle_fv_bed_mean_verified"])
        arrays["bed_vertices_xyz_m"][-1,1] = 2.
        diagnostics = audit_bed(arrays,metadata,source)
        self.assertFalse(diagnostics["triangle_fv_bed_mean_verified"])
        self.assertAlmostEqual(diagnostics["maximum_triangle_fv_bed_mean_difference_m"],1/3)
        with self.assertRaisesRegex(ValueError,"triangle area-mean"):
            validate_canonical_bed(dict(arrays=arrays,metadata=metadata))

    def test_canonical_protection_is_checked_without_builders(self):
        source,arrays,metadata = sample()
        source["protected_mask"][:] = True
        source["receiver"][0] = 1
        arrays["native_protected_mask"][:] = True
        arrays["native_receiver"][0] = 1
        arrays["selected_edge_cell_ids"] = np.array([[0,1]],np.int64)
        with patch("terrain_pipeline.single_domain_fine_geometry._geometry_arrays",side_effect=RuntimeError("builder forbidden")):
            expected,protected,suppressed = canonical_reference(arrays,metadata,source)
            actual,mask = canonical_bed_fields(dict(arrays=arrays,metadata=metadata))
        self.assertTrue(protected.all())
        self.assertTrue(mask.all())
        self.assertGreater(suppressed.max(),0.)
        np.testing.assert_array_equal(expected,np.ones((30,30)))
        np.testing.assert_array_equal(actual,expected)

    def test_coarse_initial_depth_restricts_wetted_inventory(self):
        bed = np.array([[0.,2.],[2.,2.]])
        coarse = np.array([[.25]])
        correct = audit_initial_contract(coarse,bed,lake_stage_m=1.,spacing_m=2.,initial_kind="lake")
        self.assertTrue(correct["passed"])
        wrong = np.maximum(1.-bed.mean(),0).reshape(1,1)
        self.assertFalse(audit_initial_contract(wrong,bed,lake_stage_m=1.,spacing_m=2.,initial_kind="lake")["passed"])

    def test_subgrid_cold_equation_witness_never_calls_production_flux(self):
        from terrain_pipeline.single_domain_fine_io import _segment_momentum_witness
        from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
        arrays = dict(face_left=np.array([0]),face_right=np.array([1]),boundary_cell=np.array([0,1]),
                      boundary_kind=np.array([0,0]),face_segment_crest_relative_m=np.zeros((1,2)),
                      boundary_segment_crest_relative_m=np.zeros((2,2)))
        geometry = dict(arrays=arrays,metadata=dict(spacing_m=2.,hydraulic_datum_m=100.))
        with patch("terrain_pipeline.single_domain_fine_geometry.segmented_flux",side_effect=RuntimeError("solver forbidden")):
            internal,boundary,limiter = _segment_momentum_witness(geometry,np.array([.1,.1]),np.zeros((1,2)),np.zeros((2,2)),
                 np.array([100.,100.]),np.zeros(2),.01,SurfaceBudget(),np.array([.1,.1]))
        np.testing.assert_array_equal(internal,np.zeros((1,2)))
        np.testing.assert_array_equal(boundary,np.zeros((2,2)))
        self.assertEqual(limiter["limited_donors"],0)


if __name__ == "__main__":
    unittest.main()
