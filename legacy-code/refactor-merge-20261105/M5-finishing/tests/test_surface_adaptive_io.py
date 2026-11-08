import copy
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import save_bundle, file_sha256, identity
from terrain_pipeline.surface_hydraulics import SurfaceBudget
from terrain_pipeline.adaptive_mesh import build_adaptive_geometry
from terrain_pipeline.adaptive_mesh import advance_adaptive_surface
from terrain_pipeline.adaptive_mesh import save_adaptive_run, load_adaptive_run, validate_geometry, validate_epoch, apply_transaction, _validate_step_algebra, storage_stage
from tools.audit_surface_adaptive import audit_step


def run_fixture():
    bed = np.tile(np.arange(16)*.015,(12,1))+.003*np.arange(12)[:,None]
    geometry = build_adaptive_geometry(bed,np.full(bed.shape,4,np.int64))
    depth = np.maximum(.08-bed,0)
    forcing = np.zeros((2,*bed.shape))
    forcing[:,10,14] = 1e-14
    tailwater = np.zeros((2,2*sum(bed.shape)))
    budget = SurfaceBudget(max_dt_s=.01,max_snapshots=4,max_duration_s=1.,max_cells=65536,max_bytes=268435456,max_wall_s=1800.)
    result = advance_adaptive_surface(geometry,initial_depth_m=depth,forcing_interval_s=.02,intervals=2,
        forcing_provider=lambda i:forcing[i],boundary_stage_provider=lambda i:tailwater[i],budget=budget,halo_m=2)
    return result,forcing,tailwater,budget


class AdaptiveIOTests(unittest.TestCase):
    def test_archive_binding_releases_segments_preserves_random_reads_and_rejects_tampering(self):
        from terrain_pipeline.adaptive_mesh import CompressedRecordList, CompressedGeometryHistory
        result,forcing,tailwater,budget = run_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            histories = []
            for name in ("snapshots","epoch_packets","refinement_transactions","first_rk_packets"):
                original = result[name]
                collection = CompressedRecordList(root/"scratch",memory_limit_bytes=128)
                collection._file._segment_limit = 512
                for record in original:
                    collection.append(record)
                result[name] = collection
                histories.append(collection)
            original_geometries = result["geometries"]
            geometries = CompressedGeometryHistory(root/"scratch",memory_limit_bytes=128)
            geometries._records._file._segment_limit = 512
            for geometry in original_geometries.values():
                geometries.register(geometry)
            result["geometries"] = geometries
            histories.append(geometries)
            expected_snapshots = [copy.deepcopy(item) for item in result["snapshots"]]
            source = root/"source.npz"
            arrays = dict(canonical_bed_m=result["geometry"]["arrays"]["canonical_bed_m"])
            metadata = dict(schema="test-source")
            save_bundle(source,dict(arrays=arrays,metadata=metadata,identity_sha256=identity(arrays,metadata)),validator=lambda item:True)
            observations = []
            repo = Path(__file__).resolve().parents[1]
            name = "terrain_pipeline/adaptive_mesh.py"
            pin = save_adaptive_run(root/"run",result,forcing_m3_s=forcing,tailwater_m=tailwater,forcing_interval_s=.02,budget=budget,
                source_record=dict(path=str(source),expected_sha256=file_sha256(source)),code_sha256={name:file_sha256(repo/name)},
                resource_observer=lambda:observations.append(sum(item.temporary_storage_nbytes for item in histories)))
            self.assertGreater(max(observations),0)
            self.assertEqual(observations[-1],0)
            self.assertEqual(list((root/"scratch").iterdir()),[])
            for number in (2,0,1):
                actual = result["snapshots"][number]
                self.assertEqual(set(actual),set(expected_snapshots[number]))
                for field in ("state","canonical_depth_m","canonical_momentum_m2_s"):
                    np.testing.assert_array_equal(actual[field],expected_snapshots[number][field])
            for key in reversed(list(result["geometries"])):
                self.assertEqual(result["geometries"][key]["identity_sha256"],key)
            for field in ("epoch_packets","refinement_transactions","first_rk_packets"):
                for number in reversed(range(len(result[field]))):
                    self.assertNotIn("schema",result[field][number])
            loaded = load_adaptive_run(pin["path"],expected_sha256=pin["expected_sha256"])
            snapshot_path = Path(loaded["index"]["snapshots"][0]["path"])
            snapshot_path.write_bytes(b"tampered immutable snapshot")
            with self.assertRaises(ValueError):
                result["snapshots"][0]
            first_geometry = next(iter(result["geometries"]))
            geometry_path = Path(loaded["index"]["geometries"][first_geometry]["path"])
            geometry_path.write_bytes(b"tampered immutable geometry")
            with self.assertRaises(ValueError):
                result["geometries"][first_geometry]
            for item in histories:
                if hasattr(item,"close"):
                    item.close()
                else:
                    item._records.close()

    def test_grouped_storage_inverse_is_bitwise_equivalent_at_wetting_thresholds(self):
        bed = np.random.default_rng(42).uniform(-2,3,(12,16))
        requested = np.full(bed.shape,4,np.int64)
        requested[:4,:4] = 1
        requested[4:8,:4] = 2
        geometry = build_adaptive_geometry(bed,requested)
        a = geometry["arrays"]
        self.assertEqual(set(a["subcell_count"]),{1,4,16})
        depths = [np.zeros(len(a["leaf_row"])),np.random.default_rng(43).uniform(0,3,len(a["leaf_row"]))]
        for wet_count in range(1,17):
            wet = np.minimum(wet_count,a["subcell_count"])
            indices = a["subcell_offset"]+wet-1
            depths.append((wet*a["sorted_subcell_bed_relative_m"][indices]-a["prefix_subcell_bed_relative_m"][indices])/a["subcell_count"])
        for depth in depths:
            expected = np.empty(len(depth))
            for cell,count in enumerate(a["subcell_count"]):
                offset = a["subcell_offset"][cell]
                sorted_bed = a["sorted_subcell_bed_relative_m"][offset:offset+count]
                prefix = a["prefix_subcell_bed_relative_m"][offset:offset+count]
                volume = depth[cell]*count
                wet = max(int(np.sum(volume>=np.arange(1,count+1)*sorted_bed-prefix)),1)
                expected[cell] = (volume+prefix[wet-1])/wet
            np.testing.assert_array_equal(storage_stage(depth,geometry).view(np.uint64),expected.view(np.uint64))

    def test_archive_cold_roundtrip_and_independent_physical_samples(self):
        result,forcing,tailwater,budget = run_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/"source.npz"
            arrays = dict(canonical_bed_m=result["geometry"]["arrays"]["canonical_bed_m"])
            metadata = dict(schema="test-source")
            save_bundle(source,dict(arrays=arrays,metadata=metadata,identity_sha256=identity(arrays,metadata)),validator=lambda item:True)
            repo = Path(__file__).resolve().parents[1]
            name = "terrain_pipeline/adaptive_mesh.py"
            pin = save_adaptive_run(root/"run",result,forcing_m3_s=forcing,tailwater_m=tailwater,forcing_interval_s=.02,budget=budget,
                source_record=dict(path=str(source),expected_sha256=file_sha256(source)),code_sha256={name:file_sha256(repo/name)})
            with (patch('terrain_pipeline.adaptive_mesh.build_adaptive_geometry',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.adaptive_mesh.advance_adaptive_surface',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.adaptive_mesh.adaptive_rhs',side_effect=RuntimeError("forbidden")),
                  patch('terrain_pipeline.adaptive_mesh.refine_adaptive_state',side_effect=RuntimeError("forbidden"))):
                loaded = load_adaptive_run(pin["path"],expected_sha256=pin["expected_sha256"])
                for step in loaded["first_steps"]:
                    audit_step(step,loaded["geometries"][step["geometry_identity"]],vars(budget))
            self.assertEqual(len(loaded["snapshots"]),3)
            self.assertFalse(loaded["solver_advanced"])
            self.assertGreater(len(loaded["refinements"]),0)
            script = (
                "from contextlib import ExitStack\n"
                "from unittest.mock import patch\n"
                "import terrain_pipeline.adaptive_mesh as adaptive\n"
                "def forbidden(*args, **kwargs): raise AssertionError('execution during cold read')\n"
                "with ExitStack() as guards:\n"
                "    for name in ('build_adaptive_geometry', 'advance_adaptive_surface', 'adaptive_rhs', 'refine_adaptive_state'):\n"
                "        guards.enter_context(patch.object(adaptive, name, forbidden))\n"
                "    r=adaptive.load_adaptive_run(" + repr(pin["path"]) + ",expected_sha256=" + repr(pin["expected_sha256"]) + ")\n"
                "    assert not r['solver_advanced']\n"
                "    assert len(r['snapshots'])==3\n"
            )
            cold = subprocess.run([sys.executable,"-B","-c",script],cwd=repo,capture_output=True,text=True,check=False)
            self.assertEqual(cold.returncode,0,cold.stderr)

    def test_coordinated_algebra_valid_false_physical_flux_rejected(self):
        result,_,_,budget = run_fixture()
        packet = copy.deepcopy(result["first_rk_packets"][0])
        geometry = result["geometries"][packet["geometry_identity"]]
        a = geometry["arrays"]
        packet["rk2_internal_flux"][0] += np.array([.0001,.0002,.0003])
        rhs = packet["rk2_bed_source"].copy()
        np.add.at(rhs,a["face_left"],-packet["rk2_internal_flux"]/a["leaf_area_m2"][a["face_left"],None])
        np.add.at(rhs,a["face_right"],packet["rk2_internal_flux"]/a["leaf_area_m2"][a["face_right"],None])
        np.add.at(rhs,a["boundary_cell"],-packet["rk2_boundary_flux"]/a["leaf_area_m2"][a["boundary_cell"],None])
        rhs[:,0] += packet["forcing_m3_s"]/a["leaf_area_m2"]
        undamped = .5*packet["state_before"]+.5*(packet["state_predictor"]+packet["dt_s"]*rhs)
        from terrain_pipeline.adaptive_mesh import adaptive_drag
        damping,factor = adaptive_drag(geometry,undamped,dt=packet["dt_s"],gravity=budget.gravity_m_s2,roughness=budget.roughness_s_m_third)
        packet["state_after"] = undamped.copy()
        packet["state_after"][:,1:] *= damping[:,None]
        packet["manning_momentum_change"] = packet["state_after"][:,1:]-undamped[:,1:]
        packet["manning_inverse_depth_third_mean"] = factor
        _validate_step_algebra(packet,geometry,vars(budget))
        with self.assertRaisesRegex(ValueError,"physical RK"):
            audit_step(packet,geometry,vars(budget))

    def test_resigned_geometry_epoch_and_refinement_corruption_rejected(self):
        result,_,_,_ = run_fixture()
        geometry = copy.deepcopy(result["geometry"])
        geometry["arrays"]["face_crest_relative_m"][0] += .1
        from terrain_pipeline.surface_identity import geometry_identity
        geometry["identity_sha256"] = geometry_identity(geometry["arrays"],geometry["metadata"])
        with self.assertRaises(ValueError):
            validate_geometry(geometry)
        epoch = copy.deepcopy(result["epoch_packets"][0])
        epoch["bed_impulse"][0,0] += .1
        with self.assertRaises(ValueError):
            validate_epoch(epoch,result["geometries"][epoch["geometry_identity"]])
        transaction = copy.deepcopy(result["refinement_transactions"][0])
        before = result["geometries"][transaction["before_geometry_identity"]]
        after = result["geometries"][transaction["after_geometry_identity"]]
        transaction["child_inventory_m3_m4_s"][0,0] += .1
        with self.assertRaises(ValueError):
            apply_transaction(transaction,before,after,result["snapshots"][0]["state"])


if __name__=="__main__":
    unittest.main()
