import unittest
import json
import hashlib
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

from tools.verify_fluvial_morphodynamics import DRY_DEPTH_VERSION, GRAVITY_VERSION, QUANTIZED_EXCHANGE_VERSION, audit_archive, audit_chain, audit_failed_proposal, distributary_evidence, file_sha256, formal_acceptance, morphology_evidence, native_counter_sign_diagnostics, native_material_acceptance, save_archive, spatial_repetition, stored_mobile_slope_diagnostics, surface_exposure_diagnostics, sustained_distributary_evidence, validate_gravity_handoff, validate_gravity_transition
from tools.verify_fluvial_morphodynamics import WATER_ROUTING_REPAIR_VERSION, WATER_REPAIR_MECHANISMS, audit_water_repair_statistics, validate_water_repair_declaration, publish_water_repair_evolution


class MorphodynamicsEvidenceTests(unittest.TestCase):
    def test_water_repair_evolution_uses_actual_handoff_depths_and_saved_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/"v6.npz"
            bed=np.full((2,6,6),.2)
            depth=np.full_like(bed,.4)
            depth[-1,3,3]=0.
            valid=np.ones((6,6),bool)
            ocean=valid.copy()
            ocean[0]=False
            initial=np.full((6,6),-.1)
            initial[0]=.2
            core={"algorithm_version":WATER_ROUTING_REPAIR_VERSION,"native_start_step_index":4096,
                  "native_end_step_index":4097,"dx_m":5.,"sea_level_m":0.}
            np.savez_compressed(path,metadata_json=np.array(json.dumps({"core":core})),
                                initial_bed_m=initial,times_s=np.array([10.,11.]),beds_m=bed,depths_m=depth,
                                stages_m=bed+depth,qx_m2_s=np.zeros_like(bed),qz_m2_s=np.zeros_like(bed),
                                backend_valid_mask=valid,backend_ocean_mask=ocean,backend_inlet_mask=~ocean,
                                backend_export_mask=np.zeros_like(valid),cell_type=np.zeros((6,6),int))
            report=publish_water_repair_evolution([path],root)
            self.assertEqual([s["native_step"] for s in report["snapshots"]],[4096,4097])
            self.assertEqual([s["valid_actual_dry_area_m2"] for s in report["snapshots"]],[0.,25.])
            self.assertEqual(report["snapshots"][-1]["surface_exposure"]["actual_dry_connected_to_original_land"]["area_m2"],0.)
            self.assertFalse(report["snapshots"][-1]["single_snapshot_distributary_evidence"]["two_sustained_branches"])
            self.assertTrue((root/"water-repair-actual-evolution.png").is_file())
            self.assertTrue((root/"water-repair-actual-evolution.json").is_file())

    def test_dry_depth_transition_pins_parameter_evidence_and_inherited_material(self):
        self.check_depth_transition(False)

    def test_quantized_exchange_transition_preserves_threshold_and_pins_precision_evidence(self):
        self.check_depth_transition(True)

    def test_water_repair_transition_requires_exact_v5_4096_parent_and_pinned_evidence(self):
        self.check_depth_transition(True,water_repair=True)

    def check_depth_transition(self,quantized,water_repair=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            inherited=[{"path":"v3.npz","sha256":"v3-hash"}]
            parent=root/"parent.json"
            parent.write_text(json.dumps({"batches":inherited}),encoding="utf-8")
            checkpoint=root/"checkpoint.npz"
            material=root/"material.npz"
            base=np.full((2,2),-2.)
            np.savez_compressed(checkpoint,eta=np.ones((2,2)))
            np.savez_compressed(material,mobile_base_m=base)
            params={"repose_angle_deg":30.,"tolerance_m":1e-6,"max_sweeps":512,"substrate_sand_fraction":.5}
            core={"algorithm_version":DRY_DEPTH_VERSION,"gravity_parameters":params,"mechanism_identity":"v4-id",
                  "material_state_start_sha256":file_sha256(material)}
            previous={"checkpoint_end_sha256":file_sha256(checkpoint),"material_state_end_sha256":file_sha256(material),
                      "mobile_base_m":base,"velocities":{key:np.zeros(base.shape) for key in ("ux_m_s","uz_m_s","speed_m_s")}}
            transition={"parent_manifest_path":str(parent),"parent_manifest_sha256":file_sha256(parent),
                        "checkpoint_path":str(checkpoint),"checkpoint_sha256":file_sha256(checkpoint),
                        "from_algorithm_version":GRAVITY_VERSION,"to_algorithm_version":DRY_DEPTH_VERSION,
                        "from_routing_dry_depth_m":.1,"routing_dry_depth_m":.01,"gravity_parameters":params,"mechanism_identity":"v4-id",
                        "material_state_start_path":str(material),"material_state_start_sha256":file_sha256(material),
                        "numerical_sensitivity_evidence":[{"path":str(checkpoint),"sha256":file_sha256(checkpoint)}]}
            validate_gravity_transition(transition,core,previous,inherited)
            if quantized:
                core.update(algorithm_version=QUANTIZED_EXCHANGE_VERSION,quantized_native_exchange=True)
                transition.update(from_algorithm_version=DRY_DEPTH_VERSION,to_algorithm_version=QUANTIZED_EXCHANGE_VERSION,
                    from_routing_dry_depth_m=.01,quantized_native_exchange=True,
                    numerical_precision_evidence=transition.pop("numerical_sensitivity_evidence"))
                validate_gravity_transition(transition,core,previous,inherited)
                for key,value in (("quantized_native_exchange",False),("from_algorithm_version",GRAVITY_VERSION),
                                  ("numerical_precision_evidence",[])):
                    with self.subTest(key=key),self.assertRaises(ValueError):
                        validate_gravity_transition({**transition,key:value},core,previous,inherited)
            if water_repair:
                core.update(algorithm_version=WATER_ROUTING_REPAIR_VERSION,native_start_step_index=4096,
                            water_routing_repair=True,water_repair_mechanisms=WATER_REPAIR_MECHANISMS)
                previous["end_step"]=4096
                transition.update(from_algorithm_version=QUANTIZED_EXCHANGE_VERSION,to_algorithm_version=WATER_ROUTING_REPAIR_VERSION,
                                  after_step=4096,water_routing_repair=True,water_repair_mechanisms=WATER_REPAIR_MECHANISMS,
                                  water_routing_repair_evidence=transition.pop("numerical_precision_evidence"))
                validate_gravity_transition(transition,core,previous,inherited)
                for key,value in (("after_step",4097),("from_algorithm_version",DRY_DEPTH_VERSION),
                                  ("water_routing_repair",False),("water_repair_mechanisms",{}),("water_routing_repair_evidence",[])):
                    with self.subTest(key=key),self.assertRaises(ValueError):
                        validate_gravity_transition({**transition,key:value},core,previous,inherited)
                with self.assertRaises(ValueError):
                    validate_gravity_transition(transition,core,{**previous,"end_step":4100},inherited)
            for key,value in (("routing_dry_depth_m",.02),("from_routing_dry_depth_m",.01),
                              ("material_state_start_sha256","reset-base"),("numerical_sensitivity_evidence",[])):
                if quantized and key in ("from_routing_dry_depth_m","numerical_sensitivity_evidence"):
                    continue
                with self.subTest(key=key),self.assertRaises(ValueError):
                    validate_gravity_transition({**transition,key:value},core,previous,inherited)
            arrays={"initial_mobile_base_m":base.copy(),**{key:np.zeros((2,*base.shape)) for key in previous["velocities"]}}
            validate_gravity_handoff(previous,core,arrays)
            for key in ("initial_mobile_base_m",*previous["velocities"]):
                altered={name:value.copy() for name,value in arrays.items()}
                altered[key].flat[0]+=1.
                with self.subTest(key=key),self.assertRaises(AssertionError):
                    validate_gravity_handoff(previous,core,altered)

    def test_dry_depth_archive_reconstructs_five_phases_and_requires_actual_router_thresholds(self):
        self.check_depth_archive(False)

    def test_quantized_exchange_archive_requires_actual_precision_and_unchanged_float32_storage(self):
        self.check_depth_archive(True)

    def test_water_repair_archive_checks_identity_and_preserves_precision_and_gravity(self):
        self.check_depth_archive(True,water_repair=True)

    def check_depth_archive(self,quantized,water_repair=False):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"v4.npz"
            self.archive_fixture(path)
            with np.load(path,allow_pickle=False) as archive:
                arrays={key:archive[key].copy() for key in archive.files}
            meta=json.loads(str(arrays["metadata_json"]))
            params={"repose_angle_deg":30.,"tolerance_m":1e-6,"max_sweeps":512,"substrate_sand_fraction":.5}
            core=meta["core"]
            core.update(algorithm_version=DRY_DEPTH_VERSION,gravity_parameters=params,routing_dry_depth_m=.01,
                        native_water_dry_depth_m=.01,native_sand_router_dry_depth_m=float(np.float32(.01)),
                        native_mud_router_dry_depth_m=float(np.float32(.01)))
            identity={"algorithm_version":DRY_DEPTH_VERSION,"gravity_parameters":params,"routing_dry_depth_m":.01}
            if quantized:
                for field in ("beds_m","depths_m","stages_m"):
                    arrays[field]=arrays[field].astype(np.float32)
                core.update(algorithm_version=QUANTIZED_EXCHANGE_VERSION,quantized_native_exchange=True,
                    native_exchange_precision={"bed_dtype":"float32","sand_deposition_dtype":"float64","mud_deposition_dtype":"float64",
                        "routers":{grain:{**{key:"float64" for key in ("Vp_sed","Vp_res","Vp_exported","Vp_lost")},
                            **{key:"array(float64, 2d, A)" for key in ("Vp_dep_sand","Vp_dep_mud")}} for grain in ("sand","mud")}})
                identity.update(algorithm_version=QUANTIZED_EXCHANGE_VERSION,quantized_native_exchange=True)
            if water_repair:
                core["config"]["water_parcels"]=1000
                core.update(algorithm_version=WATER_ROUTING_REPAIR_VERSION,water_routing_repair=True,
                            water_repair_mechanisms=dict(WATER_REPAIR_MECHANISMS),
                            native_start_step_index=0,native_end_step_index=1,
                            water_routing_repair_statistics=self.water_repair_records())
                identity.update(algorithm_version=WATER_ROUTING_REPAIR_VERSION,water_routing_repair=True,
                                water_repair_mechanisms=dict(WATER_REPAIR_MECHANISMS))
            core["mechanism_identity"]=hashlib.sha256(json.dumps(identity,sort_keys=True).encode("ascii")).hexdigest()
            base=np.minimum(arrays["backend_source_bed_m"],arrays["initial_bed_m"])-.25
            state=Path(directory)/"material.npz"
            np.savez_compressed(state,mobile_base_m=base)
            for position in ("start","end"):
                core["material_state_"+position+"_path"]=str(state)
                core["material_state_"+position+"_sha256"]=file_sha256(state)
            arrays["initial_mobile_base_m"],arrays["final_mobile_base_m"]=base.copy(),base.copy()
            for phase in meta["phases"]:
                if phase["phase"] in ("sand","mud"):
                    phase.update(source_floor_limited_bulk_m3=0.,source_floor_limited_exchange_count=0)
            final=arrays["final_bed_m"]
            for field in ("start_bed_m","end_bed_m","delta_bulk_m3"):
                value=np.zeros(final.shape) if field=="delta_bulk_m3" else final
                arrays["phase_"+field]=np.concatenate([arrays["phase_"+field],value[None]])
            for field in ("start_sand_fraction","end_sand_fraction","start_active_layer","end_active_layer"):
                arrays["gravity_"+field]=np.full((1,*final.shape),.5,dtype=np.float32)
            phase={key:0. for key in ("injected_bulk_m3","exported_bulk_m3","lost_bulk_m3","inlet_correction_bulk_m3","raw_residual_bulk_m3")}
            phase.update(step_index=0,phase="gravity",gravity_ledger={"actual_raw_residual_bulk_m3":0.,"actual_raw_residual_sand_bulk_m3":0.,"actual_raw_residual_mud_bulk_m3":0.,"maximum_mobile_excess_after_m":0.,"sweeps":0})
            meta["phases"].append(phase)
            def write():
                arrays["metadata_json"]=np.array(json.dumps(meta))
                np.savez_compressed(path,**arrays)
            write()
            self.assertTrue(audit_archive(path)["gravity_evidence"]["gravity_evidence_reconstructed"])
            manifest=Path(directory)/"chain.json"
            manifest.write_text(json.dumps({"schema":"saved-pydeltarcm-chain-v1","batches":[{"path":str(path),"sha256":file_sha256(path)}]}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"inherited gravity prefix"):
                audit_chain(manifest)
            for key,value in (("routing_dry_depth_m",.02),("native_mud_router_dry_depth_m",.1),
                              ("native_sand_router_dry_depth_m",.1),("native_water_dry_depth_m",.1),
                              ("material_state_start_path",None),("mechanism_identity","v3-id"),
                              *(((("quantized_native_exchange",False),("native_exchange_precision",{}))) if quantized else ())):
                original=core[key]
                core[key]=value
                write()
                with self.subTest(key=key),self.assertRaises(ValueError):
                    audit_archive(path)
                core[key]=original
            if quantized:
                for field in ("beds_m","depths_m","stages_m"):
                    original=arrays[field]
                    arrays[field]=original.astype(np.float64)
                    write()
                    with self.subTest(field=field),self.assertRaises(ValueError):
                        audit_archive(path)
                    arrays[field]=original

    @staticmethod
    def water_repair_records():
        return [{"step_index":0,"iteration":iteration,"native_relocations":1,"accepted_connections":1,
                 "accepted_graph_steps":2,"rejected_connections":{},"out_of_domain_transitions":0,"steps":50,
                 "boundary_parcels":1000,"active_at_end":0,
                 "inlet_weight_mask":{"inlet_cells":7,"changed_cells":7,"removed_upstream_weight_sum":.2}}
                for iteration in range(3)]

    def test_terminal_diagnostics_and_unversioned_water_repairs_are_rejected(self):
        v6={"algorithm_version":WATER_ROUTING_REPAIR_VERSION,"water_routing_repair":True,
            "water_repair_mechanisms":dict(WATER_REPAIR_MECHANISMS)}
        validate_water_repair_declaration({"core":v6})
        for meta in ({"core":{**v6,"diagnostic_only":True}}, {"core":v6,"diagnostic_only":True},
                     {"core":{**v6,"water_repair_mechanisms":{}}},
                     {"core":{**v6,"algorithm_version":QUANTIZED_EXCHANGE_VERSION}}):
            with self.subTest(meta=meta),self.assertRaises(ValueError):
                validate_water_repair_declaration(meta)

    def test_compact_water_repair_statistics_require_all_rounds_and_safe_boundaries(self):
        core={"algorithm_version":WATER_ROUTING_REPAIR_VERSION,"native_start_step_index":0,"native_end_step_index":1,
              "config":{"water_parcels":1000},"water_routing_repair_statistics":self.water_repair_records()}
        self.assertEqual(audit_water_repair_statistics(core)["totals"]["accepted_graph_steps"],6)
        for field,value in (("iteration",2),("out_of_domain_transitions",1),("native_relocations",2),("steps",571)):
            bad=json.loads(json.dumps(core))
            bad["water_routing_repair_statistics"][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                audit_water_repair_statistics(bad)

    def test_native_micro_negative_counters_retain_signed_values_and_residual(self):
        core={"native_parcel_bulk_m3":.245,"config":{"sediment_parcels":1000,"sand_fraction":.5}}
        phase={"phase":"mud","injected_bulk_m3":122.5,"exported_bulk_m3":-1.3732724950383207e-43,
               "lost_bulk_m3":-8.730924434546354e-23,"inlet_correction_bulk_m3":0.,"raw_residual_bulk_m3":-.0007}
        original=phase.copy()
        result=native_counter_sign_diagnostics(phase,core)
        self.assertEqual(phase,original)
        self.assertEqual(result["float32_phase_throughput_resolution_bulk_m3"],7.62939453125e-6)
        self.assertEqual(result["negative_raw_counters"],{key:phase[key] for key in ("exported_bulk_m3","lost_bulk_m3")})
        bound=result["float32_phase_throughput_resolution_bulk_m3"]
        native_counter_sign_diagnostics({**phase,"lost_bulk_m3":-bound},core)

    def test_v5_signed_counter_classification_uses_tighter_actual_float64_resolution(self):
        core={"algorithm_version":QUANTIZED_EXCHANGE_VERSION,"native_parcel_bulk_m3":.245,
              "config":{"sediment_parcels":1000,"sand_fraction":.5}}
        bound=float(np.spacing(np.float64(122.5)))
        phase={"phase":"sand","injected_bulk_m3":122.5,"exported_bulk_m3":0.,
               "lost_bulk_m3":-bound,"inlet_correction_bulk_m3":0.}
        self.assertEqual(native_counter_sign_diagnostics(phase,core)["float64_phase_throughput_resolution_bulk_m3"],bound)
        with self.assertRaises(ValueError):
            native_counter_sign_diagnostics({**phase,"lost_bulk_m3":-np.nextafter(bound,np.inf)},core)
        self.assertEqual(phase["lost_bulk_m3"],-bound)

    def test_native_counter_sign_classification_rejects_substantive_negatives(self):
        core={"native_parcel_bulk_m3":.245,"config":{"sediment_parcels":1000,"sand_fraction":.5}}
        phase={"phase":"mud","injected_bulk_m3":122.5,"exported_bulk_m3":0.,"lost_bulk_m3":0.,"inlet_correction_bulk_m3":0.}
        bound=float(np.spacing(np.float32(122.5)))
        for key in ("exported_bulk_m3","lost_bulk_m3"):
            for value in (-float(np.nextafter(bound,np.inf)),-.01):
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    native_counter_sign_diagnostics({**phase,key:value},core)
            with self.assertRaises(ValueError):
                native_counter_sign_diagnostics({**phase,"phase":"diffusion",key:-1e-44},core)
        with self.assertRaises(ValueError):
            native_counter_sign_diagnostics({**phase,"injected_bulk_m3":-1e-44},core)

    def test_gravity_transition_pins_inherited_chain_checkpoint_and_mechanism(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            parent=root/"parent.json"
            inherited=[{"path":"old-v2.npz","sha256":"old-hash"}]
            parent.write_text(json.dumps({"batches":inherited}),encoding="utf-8")
            checkpoint=root/"checkpoint.npz"
            np.savez_compressed(checkpoint,eta=np.zeros((2,2)))
            params={"repose_angle_deg":30.,"tolerance_m":1e-6,"max_sweeps":512,"substrate_sand_fraction":.5}
            core={"gravity_parameters":params,"mechanism_identity":"frozen-mechanism"}
            previous={"checkpoint_end_sha256":file_sha256(checkpoint)}
            transition={"parent_manifest_path":str(parent),"parent_manifest_sha256":file_sha256(parent),
                        "checkpoint_path":str(checkpoint),"checkpoint_sha256":file_sha256(checkpoint),**core}
            validate_gravity_transition(transition,core,previous,inherited)
            for key,value in (("mechanism_identity","other"),("gravity_parameters",{**params,"repose_angle_deg":40.}),
                              ("parent_manifest_sha256","wrong"),("checkpoint_sha256","wrong")):
                with self.assertRaises(ValueError):
                    validate_gravity_transition({**transition,key:value},core,previous,inherited)
            with self.assertRaises(ValueError):
                validate_gravity_transition(transition,core,previous,[])

    def test_gravity_five_phases_reconstruct_base_and_reject_forged_composition(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"gravity.npz"
            self.archive_fixture(path)
            with np.load(path,allow_pickle=False) as archive:
                arrays={key:archive[key].copy() for key in archive.files}
            meta=json.loads(str(arrays["metadata_json"]))
            params={"repose_angle_deg":30.,"tolerance_m":1e-6,"max_sweeps":512,"substrate_sand_fraction":.5}
            core=meta["core"]
            core.update(algorithm_version=GRAVITY_VERSION,gravity_parameters=params)
            for native in meta["phases"]:
                if native["phase"] in ("sand","mud"):
                    native.update(source_floor_limited_bulk_m3=0.,source_floor_limited_exchange_count=0)
            core["mechanism_identity"]=hashlib.sha256(json.dumps({"algorithm_version":GRAVITY_VERSION,"gravity_parameters":params},sort_keys=True).encode("ascii")).hexdigest()
            base=np.minimum(arrays["backend_source_bed_m"],arrays["initial_bed_m"])
            state=Path(directory)/"material.npz"
            np.savez_compressed(state,mobile_base_m=base)
            core.update(material_state_end_path=str(state),material_state_end_sha256=file_sha256(state))
            arrays["initial_mobile_base_m"]=base.copy()
            arrays["final_mobile_base_m"]=base.copy()
            final=arrays["final_bed_m"]
            for field in ("start_bed_m","end_bed_m","delta_bulk_m3"):
                value=np.zeros(final.shape) if field=="delta_bulk_m3" else final
                arrays["phase_"+field]=np.concatenate([arrays["phase_"+field],value[None]])
            for field in ("start_sand_fraction","end_sand_fraction","start_active_layer","end_active_layer"):
                arrays["gravity_"+field]=np.full((1,*final.shape),.5,dtype=np.float32)
            phase={key:0. for key in ("injected_bulk_m3","exported_bulk_m3","lost_bulk_m3","inlet_correction_bulk_m3","raw_residual_bulk_m3")}
            phase.update(step_index=0,phase="gravity",gravity_ledger={"actual_raw_residual_bulk_m3":0.,"actual_raw_residual_sand_bulk_m3":0.,"actual_raw_residual_mud_bulk_m3":0.,"maximum_mobile_excess_after_m":0.,"sweeps":0})
            meta["phases"].append(phase)
            arrays["metadata_json"]=np.array(json.dumps(meta))
            np.savez_compressed(path,**arrays)
            self.assertTrue(audit_archive(path)["gravity_evidence"]["gravity_evidence_reconstructed"])
            arrays["gravity_end_sand_fraction"][0,2,1]=.75
            np.savez_compressed(path,**arrays)
            with self.assertRaises((ValueError,AssertionError)):
                audit_archive(path)

    def test_actual_float32_slope_bound_retains_sub_ulp_inventory(self):
        bed=np.array([[0.,0.],[4.,0.]],dtype=np.float32)
        valid=np.ones(bed.shape,bool)
        base=np.zeros(bed.shape)
        self.assertFalse(stored_mobile_slope_diagnostics(bed,base,valid,5.)["actual_stored_slope_gate"])
        base[1,0]=4.-float(np.spacing(np.float32(4.)))/2
        result=stored_mobile_slope_diagnostics(bed,base,valid,5.)
        self.assertTrue(result["actual_stored_slope_gate"])
        self.assertGreater(result["unresolvable_positive_mobile_bulk_m3"],0.)
        self.assertGreater(result["maximum_unresolvable_or_immobile_excess_m"],0.)

    def test_above_sea_geometry_does_not_imply_actual_dry_exposure(self):
        initial=np.array([[.2,-.2,-.2,-.2]])
        final=np.array([[.2,.05,.04,.03]])
        depth=np.array([[0.,.1,1e-6,.02]])
        valid=np.array([[True,True,True,False]])
        result=surface_exposure_diagnostics(initial,final,depth,initial<0.,valid,5.)
        for name in ("bed_above_fixed_sea_level","geometrically_connected_above_sea_bed"):
            self.assertEqual(result[name]["area_m2"],50.)
            self.assertEqual(result[name]["actual_depth_range_m"],[1e-6,.1])
            self.assertEqual(result[name]["actual_dry_area_m2"],25.)
        depth[:]=.1
        wet=surface_exposure_diagnostics(initial,final,depth,initial<0.,valid,5.)
        self.assertEqual(wet["bed_above_fixed_sea_level"]["area_m2"],50.)
        self.assertEqual(wet["bed_above_fixed_sea_level"]["actual_dry_area_m2"],0.)

    def test_dry_land_connection_cannot_cross_a_wet_geometric_bridge(self):
        initial=np.array([[.2,-.2,-.2]])
        final=np.array([[.2,.05,.04]])
        depth=np.array([[0.,.1,0.]])
        valid=np.ones(initial.shape,bool)
        result=surface_exposure_diagnostics(initial,final,depth,initial<0,valid,5.)
        self.assertEqual(result["geometrically_connected_above_sea_bed"]["actual_dry_area_m2"],25.)
        self.assertEqual(result["actual_dry_connected_to_original_land"]["area_m2"],0.)
        depth[0,1]=0.
        result=surface_exposure_diagnostics(initial,final,depth,initial<0,valid,5.)
        self.assertEqual(result["actual_dry_connected_to_original_land"]["area_m2"],50.)

    def archive_fixture(self,path):
        source = np.full((3,4),-.1)
        source[:,0] = .2
        initial = source.T.copy()
        final = initial.copy()
        final[2,1] += 1./25.
        phases = []
        previous = initial.copy()
        for name in ("sand","diffusion","mud","finalize"):
            end = final.copy()
            phases.append({"step_index":0,"phase":name,"start_bed_m":previous.copy(),"end_bed_m":end,
                           "delta_bulk_m3":(end-previous)*25.,"injected_bulk_m3":1. if name=="sand" else 0.,
                           "exported_bulk_m3":0.,"lost_bulk_m3":0.,"inlet_correction_bulk_m3":0.,"raw_residual_bulk_m3":0.})
            previous = end.copy()
        result = {"initial_bed_m":initial,"final_bed_m":final,"times_s":np.array([0.,10.]),"beds_m":np.stack([initial,final]),
                  "depths_m":np.maximum(0.,-np.stack([initial,final])),"stages_m":np.maximum(0.,np.stack([initial,final])),
                  "qx_m2_s":np.zeros((2,*initial.shape)),"qz_m2_s":np.zeros((2,*initial.shape)),"phases":phases,
                  "metadata":{"dx_m":5.,"sea_level_m":0.,"maximum_original_source_cut_m":4.,"preparation_ledger":{"placed_bulk_m3":0.},
                              "backend":"synthetic-fixture","backend_version":"0","config":{"steps":1}}}
        inputs = {"source_original_bed_m":source,"source_prepared_bed_m":source,"source_raw_td_m":source,
                  "source_ocean_mask":source<0.,"backend_source_bed_m":initial,"backend_prepared_bed_m":initial,
                  "backend_initialization_delta_m":np.zeros(initial.shape),"backend_valid_mask":np.ones(initial.shape,bool),
                  "backend_ocean_mask":(source<0.).T,"backend_inlet_mask":np.zeros(initial.shape,bool),
                  "backend_export_mask":np.zeros(initial.shape,bool),"cell_type":np.zeros(initial.shape,int)}
        save_archive(path,result,{"kind":"SYNTHETIC"},inputs,{"source_rows_columns":[0,3,0,4],"transpose":True})

    def test_isolated_positive_cells_are_not_connected_delta_advance(self):
        initial = np.full((7,11),-1.)
        initial[:,0] = .1
        ocean = initial < 0.
        final = initial.copy()
        final[2,4],final[4,8] = .2,.2
        result = morphology_evidence(initial,final,ocean,np.ones(initial.shape,bool),5.)
        self.assertGreater(result["whole_ocean_net_bed_volume_m3"],0.)
        self.assertEqual(result["new_emergent_land"]["component_count"],2)
        self.assertEqual(result["land_connected_new_emergence"]["cell_count"],0)
        self.assertFalse(result["bulk_growth_and_land_connected_emergence"])

    def test_connected_emergence_and_whole_domain_net_are_separate(self):
        initial = np.full((7,11),-1.)
        initial[:,0] = .1
        ocean = initial < 0.
        final = initial.copy()
        final[2:5,1:4] = .2
        positive = morphology_evidence(initial,final,ocean,np.ones(initial.shape,bool),5.)
        self.assertTrue(positive["bulk_growth_and_land_connected_emergence"])
        self.assertEqual(positive["land_connected_new_emergence"]["cell_count"],9)
        self.assertEqual(positive["maximum_connected_shoreline_advance_m"],15.)
        final[:,8:] -= 10.
        negative = morphology_evidence(initial,final,ocean,np.ones(initial.shape,bool),5.)
        self.assertEqual(negative["land_connected_new_emergence"]["cell_count"],9)
        self.assertFalse(negative["bulk_growth_and_land_connected_emergence"])

    def test_periodic_pattern_is_measured_without_naturalness_claim(self):
        mask = np.zeros((7,40),bool)
        mask[3,::4] = True
        result = spatial_repetition(mask)
        self.assertEqual(result["columns"]["jaccard_overlap"][3],1.)
        self.assertEqual(result["columns"]["jaccard_overlap"][0],0.)

    def test_eroded_original_shore_bridge_cannot_connect_new_island(self):
        initial = np.full((5,8),-1.)
        initial[2,0:4] = .2
        ocean = initial < 0.
        final = initial.copy()
        final[2,2:4] = -2.
        final[2,4:6] = .5
        result = morphology_evidence(initial,final,ocean,np.ones(initial.shape,bool),5.)
        self.assertEqual(result["new_emergent_land"]["cell_count"],2)
        self.assertEqual(result["land_connected_new_emergence"]["cell_count"],0)

    def test_saved_native_phases_and_transposed_input_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"native.npz"
            self.archive_fixture(path)
            report = audit_archive(path)
            self.assertTrue(report["native_evidence_reconstructed"])
            self.assertEqual(report["physical_duration_s"],10.)
            self.assertAlmostEqual(report["native_phase_totals"]["sand"]["injected_bulk_m3"],1.)
            self.assertAlmostEqual(report["native_phase_totals"]["sand"]["exported_bulk_m3"],0.)
            self.assertTrue(report["material_acceptance"]["native_material_gate"])

    def test_reconstructed_diffusion_residual_still_fails_material_gate(self):
        phase={"injected_bulk_m3":0.,"exported_bulk_m3":0.,"lost_bulk_m3":0.,"inlet_correction_bulk_m3":0.}
        residual={"step":0,"phase":"diffusion","residual_bulk_m3":2.298825979}
        result=native_material_acceptance([phase],[residual])
        self.assertFalse(result["native_material_gate"])
        self.assertEqual(result["cumulative_signed_raw_residual_bulk_m3"],2.298825979)

    def test_small_biased_phases_cannot_hide_cumulative_material_error(self):
        phase={"injected_bulk_m3":0.,"exported_bulk_m3":0.,"lost_bulk_m3":0.,"inlet_correction_bulk_m3":0.}
        residual={"step":0,"phase":"diffusion","residual_bulk_m3":.009}
        result=native_material_acceptance([phase]*3,[residual]*3)
        self.assertTrue(all(p["within_tolerance"] for p in result["phases"]))
        self.assertFalse(result["native_material_gate"])

    def test_native_bed_mapping_and_parcel_counter_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"native.npz"
            self.archive_fixture(path)
            with np.load(path,allow_pickle=False) as archive:
                original = {key:archive[key].copy() for key in archive.files}
            for key in ("phase_delta_bulk_m3","backend_source_bed_m","backend_initialization_delta_m","beds_m"):
                a = {name:value.copy() for name,value in original.items()}
                a[key].flat[0] += 1.
                bad = Path(directory)/(key+".npz")
                np.savez_compressed(bad,**a)
                with self.subTest(key=key),self.assertRaises((AssertionError,ValueError)):
                    audit_archive(bad)
            a = {key:value.copy() for key,value in original.items()}
            meta = json.loads(str(a["metadata_json"].item()))
            meta["phases"][0]["exported_bulk_m3"] = 1.
            a["metadata_json"] = np.array(json.dumps(meta))
            bad = Path(directory)/"export.npz"
            np.savez_compressed(bad,**a)
            with self.assertRaises(AssertionError):
                audit_archive(bad)

    def test_scattered_wet_flux_without_banks_is_not_distributary_geometry(self):
        bed=np.zeros((20,21))
        depth=np.ones(bed.shape)
        flux=np.zeros(bed.shape)
        flux[:,6:8]=1.
        flux[:,13:15]=1.
        ocean=np.zeros(bed.shape,bool)
        ocean[15:]=True
        export=np.zeros(bed.shape,bool)
        export[-1]=True
        inlet=np.zeros(bed.shape,bool)
        inlet[0,9:12]=True
        evidence=distributary_evidence(bed,depth,bed+depth,flux,ocean,export,inlet,5.,[8,12],.1,.05,.05,20.,6)
        self.assertFalse(evidence["two_low_bed_flow_branches_observed"])

    def test_real_wet_bed_branches_are_detected_from_fields(self):
        bed=np.ones((20,21))
        bed[:6,9:12]=0.
        bed[4:6,6:15]=0.
        bed[6:,6:9]=0.
        bed[6:,12:15]=0.
        stage=np.ones(bed.shape)
        depth=stage-bed
        flux=depth.copy()
        ocean=np.zeros(bed.shape,bool)
        ocean[15:]=True
        export=np.zeros(bed.shape,bool)
        export[-1]=True
        inlet=np.zeros(bed.shape,bool)
        inlet[0,9:12]=True
        evidence=distributary_evidence(bed,depth,stage,flux,ocean,export,inlet,5.,[8,12],.1,.05,.05,20.,6)
        self.assertTrue(evidence["two_low_bed_flow_branches_observed"])

    def test_dead_branch_cannot_borrow_other_mouth_through_shared_upstream(self):
        bed=np.ones((20,21))
        bed[:6,9:12]=0.
        bed[4:6,6:15]=0.
        bed[6:12,6:9]=0.
        bed[6:,12:15]=0.
        stage=np.ones(bed.shape)
        depth=stage-bed
        ocean=np.zeros(bed.shape,bool)
        ocean[15:]=True
        export=np.zeros(bed.shape,bool)
        export[-1]=True
        inlet=np.zeros(bed.shape,bool)
        inlet[0,9:12]=True
        evidence=distributary_evidence(bed,depth,stage,depth,ocean,export,inlet,5.,[8],.1,.05,.05,20.,6)
        branches=evidence["section_observations"][0]["branches"]
        self.assertEqual(len(branches),2)
        self.assertFalse(branches[0]["wet_ocean_contact"])
        self.assertTrue(branches[1]["wet_ocean_contact"])

    def test_dead_branch_in_original_ocean_cannot_borrow_upstream_mouth(self):
        bed=np.ones((20,21))
        bed[:6,9:12]=0.
        bed[4:6,6:15]=0.
        bed[6:12,6:9]=0.
        bed[6:,12:15]=0.
        stage=np.ones(bed.shape)
        depth=stage-bed
        ocean=np.ones(bed.shape,bool)
        export=np.zeros(bed.shape,bool)
        export[-1]=True
        inlet=np.zeros(bed.shape,bool)
        inlet[0,9:12]=True
        evidence=distributary_evidence(bed,depth,stage,depth,ocean,export,inlet,5.,[8],.1,.05,.05,20.,6)
        branches=evidence["section_observations"][0]["branches"]
        self.assertEqual(len(branches),2)
        self.assertFalse(branches[0]["wet_ocean_contact"])
        self.assertTrue(branches[1]["wet_ocean_contact"])

    def test_qualifying_prefix_survives_longer_tail_without_ocean_contact(self):
        bed=np.ones((35,21))
        bed[:6,9:12]=0.
        bed[4:6,6:15]=0.
        bed[6:,6:9]=0.
        bed[6:29,12:15]=0.
        stage=np.full(bed.shape,2.)
        depth=stage-bed
        flux=(bed==0.).astype(float)
        flux[26,9:12]=.1
        ocean=np.ones(bed.shape,bool)
        export=np.zeros(bed.shape,bool)
        export[-1]=True
        inlet=np.zeros(bed.shape,bool)
        inlet[0,9:12]=True
        arrays={"times_s":np.arange(3,dtype=float),"beds_m":np.repeat(bed[None],3,axis=0),
                "depths_m":np.repeat(depth[None],3,axis=0),"stages_m":np.repeat(stage[None],3,axis=0),
                "qx_m2_s":np.repeat(flux[None],3,axis=0),"backend_ocean_mask":ocean,
                "backend_export_mask":export,"backend_inlet_mask":inlet}
        evidence=distributary_evidence(bed,depth,stage,flux,ocean,export,inlet,5.,[26,28],.15,.15,.1,20.,12)
        self.assertTrue(all(b["wet_ocean_contact"] for b in evidence["section_observations"][0]["branches"]))
        self.assertFalse(evidence["section_observations"][1]["branches"][1]["wet_ocean_contact"])
        result=sustained_distributary_evidence(arrays)
        self.assertTrue(result["sustained_distributary_gate"])
        self.assertTrue(any(t["first_row"]==6 and t["last_row"]==26 and t["length_m"]==100.
                            for t in result["snapshots"][-1]["qualifying_tracks"]))

    def test_two_banked_branches_must_persist_for_length_and_final_times(self):
        bed=np.ones((35,21))
        bed[:6,9:12]=0.
        bed[4:6,6:15]=0.
        bed[6:,6:9]=0.
        bed[6:,12:15]=0.
        ocean=np.zeros(bed.shape,bool)
        ocean[30:]=True
        export=np.zeros(bed.shape,bool)
        export[-1]=True
        inlet=np.zeros(bed.shape,bool)
        inlet[0,9:12]=True
        a={"beds_m":np.stack([bed]*3),"stages_m":np.ones((3,*bed.shape)),
           "depths_m":np.stack([1-bed]*3),"qx_m2_s":np.stack([1-bed]*3),
           "times_s":np.array([100.,200.,300.]),"backend_ocean_mask":ocean,
           "backend_export_mask":export,"backend_inlet_mask":inlet}
        self.assertTrue(sustained_distributary_evidence(a)["sustained_distributary_gate"])
        a["depths_m"][1,:,6:9]=0.
        self.assertFalse(sustained_distributary_evidence(a)["sustained_distributary_gate"])

    def test_closed_wet_wall_cannot_connect_interior_pool_to_ocean_export(self):
        bed=np.ones((20,11))
        bed[:10,4]=0.
        ocean=np.zeros(bed.shape,bool)
        ocean[:,0]=True
        ocean[10,:5]=True
        ocean[18:]=True
        depth=ocean.astype(float)
        depth[:10,4]=1.
        stage=bed+depth
        flux=np.zeros(bed.shape)
        flux[:10,4]=1.
        inlet=np.zeros(bed.shape,bool)
        inlet[0,4]=True
        export=np.zeros(bed.shape,bool)
        export[-1,1:]=True
        valid=np.ones(bed.shape,bool)
        valid[:,0]=False
        result=distributary_evidence(bed,depth,stage,flux,ocean,export,inlet,5.,[5],.1,.05,.05,20.,3,valid_mask=valid)
        self.assertFalse(result["section_observations"][0]["branches"][0]["wet_ocean_contact"])

    def test_negative_flux_reach_cannot_certify_downstream_branch_contact(self):
        bed=np.ones((20,11))
        bed[:,4:7]=0.
        depth=1-bed
        flux=depth.copy()
        flux[12,4:7]=-1.
        ocean=np.zeros(bed.shape,bool)
        ocean[15:]=True
        export=np.zeros(bed.shape,bool)
        export[-1]=True
        inlet=np.zeros(bed.shape,bool)
        inlet[0,4:7]=True
        result=distributary_evidence(bed,depth,bed+depth,flux,ocean,export,inlet,5.,[8],.1,.05,.05,20.,3)
        self.assertFalse(result["section_observations"][0]["branches"][0]["wet_ocean_contact"])

    def test_batch_chain_checks_absolute_phase_time_and_exact_water_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=root/"first.npz"
            self.archive_fixture(first)
            with np.load(first,allow_pickle=False) as archive:
                a={key:archive[key].copy() for key in archive.files}
            meta=json.loads(str(a["metadata_json"].item()))
            meta["core"]["checkpoint_end_sha256"]="preserved-native-rng-and-state"
            a["metadata_json"]=np.array(json.dumps(meta))
            np.savez_compressed(first,**a)
            initial=a["final_bed_m"].copy()
            final=initial.copy()
            final[2,1]+=1/25.
            a["initial_bed_m"],a["final_bed_m"]=initial,final
            a["beds_m"]=np.stack([initial,final])
            a["depths_m"]=np.maximum(0.,-a["beds_m"])
            a["stages_m"]=np.maximum(0.,a["beds_m"])
            a["times_s"]=np.array([10.,20.])
            previous=initial
            for index in range(4):
                a["phase_start_bed_m"][index]=previous
                a["phase_end_bed_m"][index]=final
                a["phase_delta_bulk_m3"][index]=(final-previous)*25.
                meta["phases"][index]["step_index"]=1
                previous=final
            meta["core"]["native_start_step_index"]=1
            meta["core"]["checkpoint_start_sha256"]="preserved-native-rng-and-state"
            a["metadata_json"]=np.array(json.dumps(meta))
            second=root/"second.npz"
            np.savez_compressed(second,**a)
            manifest=root/"chain.json"
            def write_manifest():
                manifest.write_text(json.dumps({"schema":"saved-pydeltarcm-chain-v1","batches":[
                    {"path":"first.npz","sha256":file_sha256(first)},
                    {"path":"second.npz","sha256":file_sha256(second)}]}),encoding="utf-8")
            write_manifest()
            report=audit_chain(manifest)
            self.assertTrue(report["chain_evidence_reconstructed"])
            self.assertEqual(report["physical_duration_s"],20.)
            self.assertAlmostEqual(report["morphology"]["whole_ocean_net_bed_volume_m3"],2.)
            meta["core"]["algorithm_version"]="undeclared-new-mechanism"
            a["metadata_json"]=np.array(json.dumps(meta))
            np.savez_compressed(second,**a)
            write_manifest()
            with self.assertRaises(ValueError):
                audit_chain(manifest)
            del meta["core"]["algorithm_version"]
            a["metadata_json"]=np.array(json.dumps(meta))
            a["qx_m2_s"][0,1,1]=1.
            np.savez_compressed(second,**a)
            write_manifest()
            with self.assertRaises(AssertionError):
                audit_chain(manifest)

    def test_formal_acceptance_rejects_same_source_with_different_preparation_or_support(self):
        report={"physical_config":{"dx_m":5.,"inlet_width_m":35.,"inlet_depth_m":2.,"inlet_length_m":45.,"inlet_velocity_m_s":1.,
                "sediment_concentration_percent":.1,"sand_fraction":.5,"porosity":.35,"water_parcels":1000,"sediment_parcels":1000,
                "water_iterations":3,"seed":42,"diffusion_enabled":True,"diffusion_mode":"conservative","maximum_original_source_cut_m":4.},
                "source_kind":"saved_TD","source_sha256":"6ae9d436a073ecd64c5f554f27c62ba0248ead1c6ccdbf08c225762ae2387784",
                "source_provenance":{"crop_rows_columns":[116,140,230,262],"refinement_factor":6,"native_spacing_m":30.,"fine_spacing_m":5.},
                "mapping":{"source_rows_columns":[0,144,51,192],"transpose":True},
                "preparation_metadata":{"inlet_cell":[75,51],"config":{"maximum_fill_bulk_m3":2000000.,"maximum_raise_m":16.,
                    "minimum_submergence_m":.2,"porosity":.35,"radius_m":300.,"slope_m_per_m":.03,"supplied_solid_m3":1300000.}},
                "contribution_excluded_morphology":{"substantive_growth_at_least_005m":{"largest_component_area_m2":10000.,"largest_component_fraction":.5},
                    "land_connected_new_emergence":{"cell_count":100},"maximum_connected_shoreline_advance_m":50.,"whole_ocean_net_bed_volume_m3":10000.},
                "batch_reports":[{"end_step":512}],"minimum_bed_minus_original_source_m":-3.,"spacing_m":5.,"sustained_distributary_evidence":{"sustained_distributary_gate":True},
                "material_acceptance":{"native_material_gate":True}}
        with patch("tools.verify_fluvial_morphodynamics.audit_chain",return_value=report):
            self.assertTrue(formal_acceptance("unused")["formal_acceptance"]["all_formal_gates"])
            for key,value in (("crop_rows_columns",[115,139,230,262]),("refinement_factor",3)):
                original=report["source_provenance"][key]
                report["source_provenance"][key]=value
                self.assertFalse(formal_acceptance("unused")["formal_acceptance"]["gates"]["fixed_formal_scenario"]["passed"])
                report["source_provenance"][key]=original
            report["preparation_metadata"]["config"]["radius_m"]=301.
            self.assertFalse(formal_acceptance("unused")["formal_acceptance"]["all_formal_gates"])

    def test_rejected_floor_proposal_is_distinct_from_completed_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            baseline=root/"baseline.npz"
            self.archive_fixture(baseline)
            with np.load(baseline,allow_pickle=False) as archive:
                previous={key:archive[key].copy() for key in archive.files}
            metadata=json.loads(str(previous["metadata_json"].item()))
            metadata["core"].update({"native_dt_s":10.,"native_parcel_bulk_m3":.002})
            metadata["core"]["config"].update({"sand_fraction":.5,"sediment_parcels":1000})
            previous["metadata_json"]=np.array(json.dumps(metadata))
            np.savez_compressed(baseline,**previous)
            before=previous["final_bed_m"]
            proposed=before.copy()
            proposed[2,1]=previous["backend_source_bed_m"][2,1]-4.3
            arrays={"source_bed_m":previous["backend_source_bed_m"],"successful_beds_m":before[None],
                    "proposed_start_bed_m":before,"proposed_bed_m":proposed,
                    "completed_phase_names":np.array([],dtype="U9")}
            arrays.update({"completed_phase_"+key:np.empty((0,*before.shape)) for key in ("start_bed_m","end_bed_m","delta_bulk_m3")})
            arrays["metadata_json"]=np.array(json.dumps({"mapping":metadata["mapping"],"config":metadata["core"]["config"],
                                                         "successful_times_s":[10.],"proposed_phase":"sand"}))
            failed=root/"failed.npz"
            np.savez_compressed(failed,**arrays)
            chain={"batch_reports":[{"path":str(baseline),"sha256":file_sha256(baseline),"end_step":1,"end_time_s":10.}]}
            with patch("tools.verify_fluvial_morphodynamics.audit_chain",return_value=chain):
                result=audit_failed_proposal(failed,"unused")
                self.assertEqual(result["rejected_human_step_number"],2)
                self.assertAlmostEqual(result["maximum_original_source_cut_m"],4.3)
                self.assertAlmostEqual(result["proposed_floor_overshoot_bulk_m3"],7.5)
                self.assertFalse(result["rejected_phase_material_ledger_available"])
                arrays["proposed_bed_m"]=before
                np.savez_compressed(failed,**arrays)
                with self.assertRaises(ValueError):
                    audit_failed_proposal(failed,"unused")


if __name__ == "__main__":
    unittest.main()
