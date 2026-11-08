"""Small synthetic boundary and saved-ledger tests for the existing kernel adapter."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import identity, file_sha256, save_bundle
from terrain_pipeline.surface_hydraulics import SurfaceBudget
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.fine_subgrid import run_fine_hydraulics
from terrain_pipeline.fine_subgrid import prepare_subgrid_support, storage_stages, stage_depths, SUBGRID_MODEL
from terrain_pipeline.fine_subgrid import validate_fine_forcing, validate_fine_states, validate_fine_interval, validate_fine_momentum, save_fine_run, load_fine_run


def fixture():
    bed = dict(arrays=dict(bed_center_m=np.array([[0.,.01,.02],[0.,.01,.02]])),
               metadata=dict(spacing_m=1.,origin_m_xz=[2.,3.],scope="synthetic_fixture"))
    bed["identity_sha256"] = identity(bed["arrays"],bed["metadata"])
    return bed


def run_fixture(**overrides):
    bed = fixture()
    options = dict(rain_mm_h=np.full((4,2,3),40.),boundary_stage_m=np.zeros((4,10)),forcing_interval_s=.25,
                   boundary_kind=np.zeros(10,np.int64),backend="reference",
                   budget=SurfaceBudget(max_dt_s=.05,max_snapshots=6,max_duration_s=2.,max_wall_s=1800.))
    options.update(overrides)
    return run_fine_hydraulics(bed,**options)


class FineHydraulicsTests(unittest.TestCase):
    def test_frozen_snapshot_link_cannot_escape_stage_root(self):
        from terrain_pipeline.fine_subgrid import _validate_code_records
        from tools.audit_single_domain_fine_stage import audit_code_records
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage,outside = root/"stage",root/"outside-stage"
            stage.mkdir()
            outside.mkdir()
            name = "module.py"
            source = outside/name
            source.write_bytes(b"# immutable external test source\n")
            link = stage/"execution-code"
            try:
                os.symlink(outside,link,target_is_directory=True)
            except OSError:
                if os.name != "nt":
                    self.skipTest("directory symlinks unavailable")
                created = subprocess.run(["cmd","/c","mklink","/J",str(link),str(outside)],capture_output=True,check=False)
                if created.returncode:
                    self.skipTest("directory symlink and junction creation unavailable")
            digest = file_sha256(source)
            records = {name:dict(path=str(link/name),expected_sha256=digest)}
            with self.assertRaisesRegex(ValueError,"root escaped stage"):
                _validate_code_records({name:digest},records,stage)
            with self.assertRaisesRegex(ValueError,"root escaped stage"):
                audit_code_records(dict(code_sha256={name:digest},code_records=records),stage,[])

    def setUp(self):
        self.result = run_fixture()

    def validate(self,result=None):
        result = self.result if result is None else result
        validate_fine_forcing(result["forcing"],bed=result["bed"])
        validate_fine_states(result["states"],bed=result["bed"],geometry=result["geometry"],forcing=result["forcing"])
        previous = None
        for number,item in enumerate(result["intervals"]):
            validate_fine_interval(item,bed=result["bed"],geometry=result["geometry"],forcing=result["forcing"],interval=number,previous=previous)
            validate_fine_momentum(result["momenta"][number],bed=result["bed"],geometry=result["geometry"],forcing=result["forcing"],
                                   states=result["states"],interval=number,interval_packet=item)
            previous = item

    def test_dry_rain_independent_four_compartments(self):
        self.validate()
        forcing = self.result["forcing"]["arrays"]
        self.assertGreater(forcing["fast_release_mm"].sum(),0.)
        self.assertGreater(forcing["slow_release_mm"].sum(),0.)
        self.assertGreater(self.result["states"]["arrays"]["depth_m"][-1].sum(),0.)
        self.assertEqual(self.result["geometry"]["metadata"]["origin_m_xz"],[2.5,3.5])


    def bed(self):
        canonical = 1350.+np.tile(np.array([0., .03, .01, .04, .02, .05]), (4, 1))
        mean = canonical.reshape(2, 2, 3, 2).mean(axis=(1, 3))
        arrays = dict(canonical_bed_center_m=canonical, bed_center_m=mean, H2_m=mean.copy())
        metadata = dict(spacing_m=2., origin_m_xz=[0., 0.])
        return dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))

    def run_case(self, initial, kinds=None, tailwater=1350.1):
        bed = self.bed()
        return run_fine_hydraulics(bed, rain_mm_h=np.zeros((2, 2, 3)), boundary_stage_m=np.full((2, 10), tailwater),
            backend="subgrid",
            forcing_interval_s=.1, boundary_kind=np.zeros(10, np.int64) if kinds is None else kinds,
            initial_depth_m=initial, runoff_parameters=RunoffParameters(initial_soil_mm=0.,percolation_mm_h=0.,potential_et_mm_h=0.),
            budget=SurfaceBudget(max_dt_s=.01,max_snapshots=4,max_duration_s=1.,max_wall_s=1800.))

    def test_exact_piecewise_wet_storage_inverse(self):
        bed = np.array([[0., .2, .8, 1.]])
        stage = storage_stages(np.array([.15]), bed, np.cumsum(bed, axis=1))
        np.testing.assert_allclose(stage, [.4], rtol=0., atol=1e-15)
        np.testing.assert_allclose(stage_depths(stage, bed), [.15], rtol=0., atol=1e-15)

    def test_closed_partially_wet_lake_at_1350m_uses_relative_datum(self):
        support, _ = prepare_subgrid_support(self.bed())
        initial = stage_depths(np.full(6, .025), support["subcell_bed_relative_m"]).reshape(2, 3)
        result = self.run_case(initial)
        np.testing.assert_allclose(result["states"]["arrays"]["depth_m"][-1], initial, rtol=0., atol=1e-13)
        self.assertEqual(result["geometry"]["metadata"]["coarse_independent_unknowns"], 6)
        self.assertEqual(result["states"]["metadata"]["hydraulic_model"], SUBGRID_MODEL)

    def test_segmented_coarse_boundary_witness_and_local_budget(self):
        kinds = np.zeros(10, np.int64)
        kinds[2:4] = 2
        result = self.run_case(np.zeros((2, 3)), kinds)
        self.assertGreater(result["states"]["arrays"]["ledger"][-1, 1], 0.)
        for packet in result["intervals"]:
            a = packet["arrays"]
            np.testing.assert_array_equal(a["internal_transfer_m3"],a["internal_segment_transfer_m3"].sum(axis=1))
            np.testing.assert_array_equal(a["boundary_transfer_m3"],a["boundary_segment_transfer_m3"].sum(axis=1))
        self.assertEqual(result["states"]["arrays"]["final_internal_segment_q_m3_s"].shape, (7, 2))

    def test_lake_at_rest_and_tailwater_import(self):
        initial = .1-fixture()["arrays"]["bed_center_m"]
        still = run_fixture(rain_mm_h=np.zeros((4,2,3)),initial_depth_m=initial,
                            runoff_parameters=RunoffParameters(initial_soil_mm=0.,percolation_mm_h=0.,potential_et_mm_h=0.))
        self.validate(still)
        np.testing.assert_allclose(still["states"]["arrays"]["depth_m"][-1],initial,atol=1e-14)
        kinds = np.zeros(10,np.int64)
        kinds[2:4] = 2
        backwater = run_fixture(initial_depth_m=initial,boundary_kind=kinds,boundary_stage_m=np.full((4,10),.6))
        self.validate(backwater)
        self.assertGreater(backwater["states"]["arrays"]["ledger"][-1,1],0.)
        self.assertLess(backwater["intervals"][0]["arrays"]["boundary_transfer_m3"].sum(),0.)

    def test_resigned_state_source_release_momentum_and_closed_boundary_rejected(self):
        for kind in ("state","source","fast_release","momentum","closed"):
            with self.subTest(kind=kind):
                result = copy.deepcopy(self.result)
                if kind == "state":
                    result["states"]["arrays"]["depth_m"][-1,0,0] += .1
                elif kind == "source":
                    result["states"]["metadata"]["bed_identity"] = "a"*64
                elif kind == "fast_release":
                    result["forcing"]["arrays"]["fast_release_mm"][0,0] += .1
                elif kind == "momentum":
                    result["momenta"][0]["arrays"]["internal_q_after_m3_s"][0] += 1.
                else:
                    result["intervals"][0]["arrays"]["boundary_q_after_m3_s"][0] = 1.
                for role in ("states","forcing"):
                    result[role]["identity_sha256"] = identity(result[role]["arrays"],result[role]["metadata"])
                for role in ("intervals","momenta"):
                    for item in result[role]:
                        item["identity_sha256"] = identity(item["arrays"],item["metadata"])
                with self.assertRaises(ValueError):
                    self.validate(result)

    def test_resource_and_forcing_preflight_rejected(self):
        with self.assertRaises(ValueError):
            run_fixture(budget=SurfaceBudget(max_wall_s=1801.,max_snapshots=6))
        with self.assertRaises(ValueError):
            run_fixture(rain_mm_h=np.full((4,2,3),np.nan))
        with self.assertRaises(ValueError):
            run_fixture(boundary_stage_m=np.zeros((3,10)))
        forged = copy.deepcopy(self.result)
        forged["states"]["metadata"]["solver_metadata"]["budget"]["max_wall_s"] = 1801.
        forged["states"]["identity_sha256"] = identity(forged["states"]["arrays"],forged["states"]["metadata"])
        with self.assertRaisesRegex(ValueError,"budget"):
            self.validate(forged)

    def test_shallow_saved_momentum_closures_and_resigned_corruption(self):
        result = run_fixture(backend="shallow_water",initial_depth_m=np.full((2,3),.1))
        self.validate(result)
        for role,name in (("momenta","state_predictor"),("momenta","rk1_bed_source"),
                          ("momenta","rk2_internal_flux"),("momenta","manning_momentum_change"),
                          ("intervals","momentum_after"),("intervals","bed_momentum_change"),
                          ("intervals","internal_momentum_transfer")):
            with self.subTest(role=role,field=name):
                forged = copy.deepcopy(result)
                packet = forged[role][0]
                packet["arrays"][name].flat[1] += .01
                packet["identity_sha256"] = identity(packet["arrays"],packet["metadata"])
                with self.assertRaises(ValueError):
                    self.validate(forged)

    def test_shallow_roundtrip_without_execution_helpers(self):
        result = run_fixture(backend="shallow_water",initial_depth_m=np.full((2,3),.1))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bed_path = root/"bed.npz"
            save_bundle(bed_path,result["bed"],validator=lambda item:True)
            bed_record = dict(path=str(bed_path),expected_sha256=file_sha256(bed_path),expected_identity=result["bed"]["identity_sha256"])
            repo = Path(__file__).resolve().parents[1]
            codes = {"terrain_pipeline/single_domain_fine_io.py":file_sha256(repo/"terrain_pipeline/single_domain_fine_io.py")}
            pin = save_fine_run(root/"run",result,bed_record=bed_record,code_sha256=codes)
            with (patch('terrain_pipeline.shallow_water.advance_shallow_water',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_shallow_water_rhs',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.shallow_water.hydrostatic_hll',side_effect=RuntimeError("forbidden"))):
                loaded = load_fine_run(pin["path"],expected_sha256=pin["expected_sha256"],bed=result["bed"])
            self.assertEqual(loaded["intervals_verified"],4)

    def test_subgrid_shallow_stage_cold_package_and_forged_stage(self):
        from tests.test_single_domain_fine_geometry import fixture as geometry_fixture
        from terrain_pipeline.fine_subgrid import build_fine_geometry
        hierarchy,_ = geometry_fixture()
        bed = build_fine_geometry(hierarchy,native_window=[0,2,0,2],source_hierarchy_sha256="a"*64,spacing_m=2.)
        shape = bed["arrays"]["bed_center_m"].shape
        canonical = bed["arrays"]["canonical_bed_center_m"]
        initial = np.maximum(2.-canonical,0).reshape(shape[0],2,shape[1],2).mean(axis=(1,3))
        result = run_fine_hydraulics(bed,rain_mm_h=np.zeros((2,*shape)),boundary_stage_m=np.zeros((2,2*sum(shape))),
            boundary_kind=np.zeros(2*sum(shape),np.int64),
            forcing_interval_s=.02,initial_depth_m=initial,backend="shallow_water_subgrid",
            budget=SurfaceBudget(max_dt_s=.01,max_snapshots=4,max_wall_s=1800.),
            runoff_parameters=RunoffParameters(initial_soil_mm=0.,percolation_mm_h=0.,potential_et_mm_h=0.))
        self.validate(result)
        np.testing.assert_allclose(result["states"]["arrays"]["depth_m"][-1],initial,atol=1e-12,rtol=0)
        forged = copy.deepcopy(result)
        forged["states"]["arrays"]["stage_relative_m"][-1,0,0] += .1
        forged["states"]["identity_sha256"] = identity(forged["states"]["arrays"],forged["states"]["metadata"])
        with self.assertRaises(ValueError):
            self.validate(forged)
        for role,name in (("momenta","rk1_internal_flux"),("momenta","rk2_bed_source"),("intervals","internal_momentum_transfer")):
            forged = copy.deepcopy(result)
            packet = forged[role][0]
            packet["arrays"][name].flat[1] += .1
            packet["identity_sha256"] = identity(packet["arrays"],packet["metadata"])
            with self.assertRaises(ValueError):
                self.validate(forged)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bed_path = root/"bed.npz"
            save_bundle(bed_path,bed,validator=lambda item:True)
            bed_record = dict(path=str(bed_path),expected_sha256=file_sha256(bed_path),expected_identity=bed["identity_sha256"])
            repo = Path(__file__).resolve().parents[1]
            name = "terrain_pipeline/single_domain_fine_io.py"
            snapshot = root/"execution-code"/name
            snapshot.parent.mkdir(parents=True)
            snapshot.write_bytes((repo/name).read_bytes())
            codes = {name:file_sha256(snapshot)}
            code_records = {name:dict(path=str(snapshot),expected_sha256=codes[name])}
            pin = save_fine_run(root/"run",result,bed_record=bed_record,code_sha256=codes,code_records=code_records)
            with (patch('terrain_pipeline.shallow_water.single_domain_shallow_water_mechanism_3_advance_shallow_water',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_mechanism_3_shallow_water_rhs',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.fine_subgrid.storage_stages',side_effect=RuntimeError("forbidden"))):
                loaded = load_fine_run(pin["path"],expected_sha256=pin["expected_sha256"],bed=bed)
            self.assertEqual(loaded["intervals_verified"],2)
            index_path = Path(pin["path"])
            original = index_path.read_text(encoding="utf-8")
            wrong = json.loads(original)
            wrong["code_records"] = {"wrong-name.py":code_records[name]}
            index_path.write_text(json.dumps(wrong),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"record names"):
                load_fine_run(index_path,expected_sha256=file_sha256(index_path),bed=bed)
            index_path.write_text(original,encoding="utf-8")
            snapshot.write_bytes(snapshot.read_bytes()+b"\n# forged snapshot\n")
            with self.assertRaisesRegex(ValueError,"snapshot pin"):
                load_fine_run(index_path,expected_sha256=file_sha256(index_path),bed=bed)

    def test_v7_canonical_manning_saved_witness_cold_and_forgery(self):
        from tests.test_single_domain_fine_geometry import fixture as geometry_fixture
        from terrain_pipeline.fine_subgrid import build_fine_geometry
        from tools.single_domain_shallow_water_audit import audit_momentum
        hierarchy,_ = geometry_fixture()
        bed = build_fine_geometry(hierarchy,native_window=[0,2,0,2],source_hierarchy_sha256="a"*64,spacing_m=2.)
        shape = bed["arrays"]["bed_center_m"].shape
        result = run_fine_hydraulics(bed,rain_mm_h=np.zeros((2,*shape)),boundary_stage_m=np.full((2,2*sum(shape)),2.),
            boundary_kind=np.zeros(2*sum(shape),np.int64),forcing_interval_s=.02,initial_depth_m=np.full(shape,.1),
            backend="shallow_water_subgrid_manning",budget=SurfaceBudget(max_dt_s=.01,max_snapshots=4,max_wall_s=1800.))
        self.validate(result)
        geometry = dict(result["geometry"]["arrays"],hydraulic_datum_m=result["geometry"]["metadata"]["hydraulic_datum_m"])
        packet = result["momenta"][0]
        with patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_mechanism_7_manning_damping',side_effect=RuntimeError("forbidden")):
            audited = audit_momentum(packet["arrays"],packet["metadata"],geometry,2.,result["states"]["metadata"]["solver_metadata"]["budget"],
                result["forcing"]["arrays"]["local_q_m3_s"][0],result["forcing"]["arrays"]["boundary_stage_m"][0])
        self.assertTrue(audited["canonical_subgrid_manning_consistency_verified"])
        forged = copy.deepcopy(result)
        witness = forged["momenta"][0]
        witness["arrays"]["manning_inverse_depth_third_mean"][0] += .1
        witness["identity_sha256"] = identity(witness["arrays"],witness["metadata"])
        with self.assertRaisesRegex(ValueError,"Manning"):
            self.validate(forged)
        with self.assertRaisesRegex(ValueError,"inverse-depth integral"):
            audit_momentum(witness["arrays"],witness["metadata"],geometry,2.,result["states"]["metadata"]["solver_metadata"]["budget"],
                result["forcing"]["arrays"]["local_q_m3_s"][0],result["forcing"]["arrays"]["boundary_stage_m"][0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bed_path = root/"bed.npz"
            save_bundle(bed_path,bed,validator=lambda item:True)
            bed_record = dict(path=str(bed_path),expected_sha256=file_sha256(bed_path),expected_identity=bed["identity_sha256"])
            repo = Path(__file__).resolve().parents[1]
            name = "terrain_pipeline/single_domain_fine_io.py"
            pin = save_fine_run(root/"run",result,bed_record=bed_record,code_sha256={name:file_sha256(repo/name)})
            with (patch('terrain_pipeline.shallow_water.single_domain_shallow_water_mechanism_7_advance_shallow_water',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.shallow_water.single_domain_shallow_water_support_mechanism_7_manning_damping',side_effect=RuntimeError("forbidden"))):
                loaded = load_fine_run(pin["path"],expected_sha256=pin["expected_sha256"],bed=bed)
            self.assertEqual(loaded["intervals_verified"],2)

    def test_roundtrip_cold_without_advance_and_forged_code_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bed_path = root/"bed.npz"
            save_bundle(bed_path,self.result["bed"],validator=lambda item:True)
            bed_record = dict(path=str(bed_path),expected_sha256=file_sha256(bed_path),expected_identity=self.result["bed"]["identity_sha256"])
            repo = Path(__file__).resolve().parents[1]
            codes = {"terrain_pipeline/single_domain_fine_io.py":file_sha256(repo/"terrain_pipeline/single_domain_fine_io.py")}
            pin = save_fine_run(root/"run",self.result,bed_record=bed_record,code_sha256=codes)
            with patch('terrain_pipeline.surface_hydraulics.advance_inertial_surface',side_effect=RuntimeError("advance forbidden")):
                loaded = load_fine_run(pin["path"],expected_sha256=pin["expected_sha256"],bed=self.result["bed"])
            self.assertEqual(loaded["intervals_verified"],4)
            self.assertFalse(loaded["solver_advanced"])
            index = json.loads(Path(pin["path"]).read_text(encoding="utf-8"))
            index["code_sha256"]["terrain_pipeline/single_domain_fine_io.py"] = "a"*64
            Path(pin["path"]).write_text(json.dumps(index),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"implementation pin"):
                load_fine_run(pin["path"],expected_sha256=file_sha256(pin["path"]),bed=self.result["bed"])


if __name__ == "__main__":
    unittest.main()
