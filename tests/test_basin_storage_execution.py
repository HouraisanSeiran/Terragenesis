"""M4 tests.test_basin_storage_execution; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from pathlib import Path as _m4_test_td_basin_storage_compiled_driver_Path
from pathlib import Path as _m4_test_td_basin_storage_continuation_Path
from terrain_pipeline.basin_storage import advance_hour_compensated as _m4_test_td_basin_storage_compiled_advance_hour
from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as _m4_test_td_basin_storage_continuation_load_checkpoint
from terrain_pipeline.basin_storage import checkpointio_save_checkpoint as _m4_test_td_basin_storage_continuation_save_checkpoint
from terrain_pipeline.basin_storage import compiled_load_checkpoint as _m4_test_td_basin_storage_compiled_driver_load_checkpoint
from terrain_pipeline.basin_storage import compiled_validate_checkpoint as _m4_test_td_basin_storage_compiled_driver_validate_checkpoint
from terrain_pipeline.basin_storage import compiled_validate_saved_storage as _m4_test_td_basin_storage_compiled_driver_validate_saved_storage
from terrain_pipeline.basin_storage import compileddriver_simulate as _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage
from terrain_pipeline.basin_storage import compiledio_save_checkpoint as _m4_test_td_basin_storage_compiled_driver_save_checkpoint
from terrain_pipeline.basin_storage import continuation_simulate as _m4_test_td_basin_storage_continuation_simulate_basin_storage
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_compiled_driver_make_td_source
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_compiled_make_td_source
from terrain_pipeline.basin_storage import make_td_source as _m4_test_td_basin_storage_continuation_make_td_source
from terrain_pipeline.basin_storage import storagev7_simulate as _m4_test_td_basin_storage_compiled_driver_monolithic
from terrain_pipeline.basin_storage import storagev7_simulate as _m4_test_td_basin_storage_compiled_simulate_basin_storage
from terrain_pipeline.basin_storage import storagev7_simulate as _m4_test_td_basin_storage_continuation_monolithic
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_compiled_build_basin_hierarchy
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_compiled_driver_build_basin_hierarchy
from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_test_td_basin_storage_continuation_build_basin_hierarchy
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_basin_storage_compiled_driver_file_sha256
from terrain_pipeline.common_infra import file_sha256 as _m4_test_td_basin_storage_continuation_file_sha256
from terrain_pipeline.common_infra import identity as _m4_test_td_basin_storage_compiled_driver_identity
from terrain_pipeline.common_infra import identity as _m4_test_td_basin_storage_continuation_identity
from terrain_pipeline.runoff import RunoffParameters as _m4_test_td_basin_storage_compiled_RunoffParameters
import numpy as _m4_test_td_basin_storage_compiled_driver_np
import numpy as _m4_test_td_basin_storage_compiled_np
import numpy as _m4_test_td_basin_storage_continuation_np
import subprocess as _m4_test_td_basin_storage_compiled_driver_subprocess
import subprocess as _m4_test_td_basin_storage_continuation_subprocess
import sys as _m4_test_td_basin_storage_compiled_driver_sys
import sys as _m4_test_td_basin_storage_continuation_sys
import tempfile as _m4_test_td_basin_storage_compiled_driver_tempfile
import tempfile as _m4_test_td_basin_storage_continuation_tempfile
import unittest as _m4_test_td_basin_storage_compiled_driver_unittest
import unittest as _m4_test_td_basin_storage_compiled_unittest
import unittest as _m4_test_td_basin_storage_continuation_unittest

# --- tests/test_td_basin_storage_compiled.py:10 ---
class BasinStorageCompiledCompiledExecutionTests(_m4_test_td_basin_storage_compiled_unittest.TestCase):
    def test_tiny_hour_equivalence(self):
        hierarchy=_m4_test_td_basin_storage_compiled_build_basin_hierarchy(_m4_test_td_basin_storage_compiled_make_td_source(_m4_test_td_basin_storage_compiled_np.array([[2.,0.,1.],[0.,2.,0.]]),spacing_m=30))
        topology=hierarchy["arrays"]
        runoff=_m4_test_td_basin_storage_compiled_RunoffParameters()
        for step in (5.,2.5):
            initial=_m4_test_td_basin_storage_compiled_np.array([[1.,0.,.2],[0.,.5,.1]])
            reference=_m4_test_td_basin_storage_compiled_simulate_basin_storage(hierarchy,_m4_test_td_basin_storage_compiled_np.array([30.]),dt_s=60,initial_depth_m=initial,parameters={"substep_s":step})
            states=_m4_test_td_basin_storage_compiled_np.vstack((initial.ravel(),_m4_test_td_basin_storage_compiled_np.full(6,30.),_m4_test_td_basin_storage_compiled_np.zeros(6),_m4_test_td_basin_storage_compiled_np.zeros(6)))
            result=_m4_test_td_basin_storage_compiled_advance_hour(states,_m4_test_td_basin_storage_compiled_np.zeros((4,6)),_m4_test_td_basin_storage_compiled_np.full(6,30.),topology["height_m"].ravel(),topology["face_cells"],topology["boundary_cells"],reference["arrays"]["boundary_width_m"],topology["receiver"],30.,step,round(60/step),
                _m4_test_td_basin_storage_compiled_np.array([runoff.infiltration_capacity_mm_h,runoff.soil_capacity_mm,runoff.potential_et_mm_h,runoff.percolation_mm_h,runoff.fast_tau_s,runoff.slow_tau_s]),_m4_test_td_basin_storage_compiled_np.array([.6,1e-9,.15]))
            for index,key in enumerate(("depth_m","soil_mm","fast_mm","slow_mm")):
                _m4_test_td_basin_storage_compiled_np.testing.assert_allclose(result[0][index],reference["arrays"][key][-1],rtol=0,atol=1e-12)
            for index,key in enumerate(("rain_volume_m3","lake_rain_m3","land_rain_m3","soil_et_m3","local_release_m3","surface_et_m3","internal_net_m3","boundary_outflow_m3")):
                _m4_test_td_basin_storage_compiled_np.testing.assert_allclose(result[2][index],reference["arrays"][key][0],rtol=1e-12,atol=1e-10)
            for index,key in enumerate(("face_forward_m3","face_reverse_m3","active_forward_s","active_reverse_s","routed_volume_m3","wet_duration_s")):
                _m4_test_td_basin_storage_compiled_np.testing.assert_allclose(result[index+3],reference["arrays"][key],rtol=1e-12,atol=1e-10)

# --- tests/test_td_basin_storage_compiled_driver.py:18 ---
class BasinStorageCompiledDriverContinuationTests(_m4_test_td_basin_storage_compiled_driver_unittest.TestCase):
    def test_forged_derived_count_and_prebroadcast_budget(self):
        hierarchy=_m4_test_td_basin_storage_compiled_driver_build_basin_hierarchy(_m4_test_td_basin_storage_compiled_driver_make_td_source(_m4_test_td_basin_storage_compiled_driver_np.zeros((2,2)),spacing_m=30))
        rain=_m4_test_td_basin_storage_compiled_driver_np.zeros(1)
        forcing_id=_m4_test_td_basin_storage_compiled_driver_identity({"rain_mm_h":rain},{"dt_s":60.})
        result=_m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain,dt_s=60,parameters={"substep_s":2.5},forcing_identity=forcing_id,full_rain_mm_h=rain)
        for role,validator in (("storage",_m4_test_td_basin_storage_compiled_driver_validate_saved_storage),("checkpoint",_m4_test_td_basin_storage_compiled_driver_validate_checkpoint)):
            original=result[role]
            metadata={**original["metadata"],"substeps":12,"substep_s":5.}
            if role=="storage":
                metadata["positivity_cfl"]=.4
            forged={"arrays":original["arrays"],"metadata":metadata,"identity_sha256":_m4_test_td_basin_storage_compiled_driver_identity(original["arrays"],metadata)}
            with self.assertRaisesRegex(ValueError,"count|substeps"):
                validator(forged)
        with self.assertRaisesRegex(ValueError,"before broadcast"):
            _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,_m4_test_td_basin_storage_compiled_driver_np.zeros(1001),dt_s=60,full_rain_mm_h=rain,forcing_identity=forcing_id)

    def test_unknown_compensation_rejected_before_execution(self):
        valid=_m4_test_td_basin_storage_compiled_driver_np.array([[True,False],[True,True]])
        hierarchy=_m4_test_td_basin_storage_compiled_driver_build_basin_hierarchy(_m4_test_td_basin_storage_compiled_driver_make_td_source(_m4_test_td_basin_storage_compiled_driver_np.zeros((2,2)),spacing_m=30,valid_mask=valid))
        rain=_m4_test_td_basin_storage_compiled_driver_np.zeros(2)
        forcing_id=_m4_test_td_basin_storage_compiled_driver_identity({"rain_mm_h":rain},{"dt_s":60.})
        result=_m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},forcing_identity=forcing_id,full_rain_mm_h=rain)
        checkpoint=result["checkpoint"]
        for key in ("depth","soil","fast","slow"):
            arrays={**checkpoint["arrays"],"error_"+key:checkpoint["arrays"]["error_"+key].copy()}
            arrays["error_"+key][1]=-1
            forged={"arrays":arrays,"metadata":checkpoint["metadata"],"identity_sha256":_m4_test_td_basin_storage_compiled_driver_identity(arrays,checkpoint["metadata"])}
            with self.assertRaisesRegex(ValueError,"compensation"):
                _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},forcing_identity=forcing_id,full_rain_mm_h=rain,checkpoint=forged)
        for key in ("routed_volume_m3","wet_duration_s"):
            arrays={**checkpoint["arrays"],"cumulative_"+key:checkpoint["arrays"]["cumulative_"+key].copy()}
            arrays["cumulative_"+key][1]=1
            forged={"arrays":arrays,"metadata":checkpoint["metadata"],"identity_sha256":_m4_test_td_basin_storage_compiled_driver_identity(arrays,checkpoint["metadata"])}
            with self.assertRaisesRegex(ValueError,"unknown"):
                _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},forcing_identity=forcing_id,full_rain_mm_h=rain,checkpoint=forged)
        arrays={**checkpoint["arrays"],"cumulative_wet_duration_s":_m4_test_td_basin_storage_compiled_driver_np.full(4,61.)}
        forged={"arrays":arrays,"metadata":checkpoint["metadata"],"identity_sha256":_m4_test_td_basin_storage_compiled_driver_identity(arrays,checkpoint["metadata"])}
        with self.assertRaisesRegex(ValueError,"elapsed"):
            _m4_test_td_basin_storage_compiled_driver_validate_checkpoint(forged)

    def test_checkpoint_rejects_time_geometry_forcing_and_initial_override(self):
        hierarchy = _m4_test_td_basin_storage_compiled_driver_build_basin_hierarchy(_m4_test_td_basin_storage_compiled_driver_make_td_source(_m4_test_td_basin_storage_compiled_driver_np.zeros((2,2)),spacing_m=30))
        rain=_m4_test_td_basin_storage_compiled_driver_np.array([30.,0.])
        forcing_id=_m4_test_td_basin_storage_compiled_driver_identity({"rain_mm_h":rain},{"dt_s":60.})
        result=_m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},forcing_identity=forcing_id,full_rain_mm_h=rain)
        checkpoint=result["checkpoint"]
        with self.assertRaisesRegex(ValueError,"mutually"):
            _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},checkpoint=checkpoint,initial_depth_m=_m4_test_td_basin_storage_compiled_driver_np.zeros((2,2)),forcing_identity=forcing_id,full_rain_mm_h=rain)
        with self.assertRaisesRegex(ValueError,"slice"):
            _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},checkpoint=checkpoint,forcing_identity=forcing_id,full_rain_mm_h=rain)
        for name,value in (("elapsed_s",61.),("elapsed_s",float("nan")),("cells",5),("faces",3),("substeps",True)):
            metadata={**checkpoint["metadata"],name:value}
            with self.assertRaises(ValueError):
                forged={"arrays":checkpoint["arrays"],"metadata":metadata,"identity_sha256":_m4_test_td_basin_storage_compiled_driver_identity(checkpoint["arrays"],metadata)}
                _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},checkpoint=forged,forcing_identity=forcing_id,full_rain_mm_h=rain)
        for invalid in (_m4_test_td_basin_storage_compiled_driver_np.array([_m4_test_td_basin_storage_compiled_driver_np.nan]),_m4_test_td_basin_storage_compiled_driver_np.array([-1.]),_m4_test_td_basin_storage_compiled_driver_np.array([1e7]),_m4_test_td_basin_storage_compiled_driver_np.zeros((1,3,4))):
            with self.assertRaises(ValueError):
                _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,_m4_test_td_basin_storage_compiled_driver_np.zeros(1),dt_s=60,forcing_identity=forcing_id,full_rain_mm_h=invalid)
        with _m4_test_td_basin_storage_compiled_driver_tempfile.TemporaryDirectory() as directory:
            path=_m4_test_td_basin_storage_compiled_driver_Path(directory)/"checkpoint.npz"
            _m4_test_td_basin_storage_compiled_driver_save_checkpoint(path,checkpoint)
            code='from terrain_pipeline.basin_storage import compiled_load_checkpoint as load_checkpoint; import sys; load_checkpoint(sys.argv[1],expected_sha256=sys.argv[2],expected_identity=sys.argv[3]); assert "terrain_pipeline.basin_storage" in sys.modules; assert \'terrain_pipeline.td_basin_storage_compiled_driver\' not in sys.modules'
            completed=_m4_test_td_basin_storage_compiled_driver_subprocess.run([_m4_test_td_basin_storage_compiled_driver_sys.executable,"-c",code,str(path),_m4_test_td_basin_storage_compiled_driver_file_sha256(path),checkpoint["identity_sha256"]],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)

    def test_reload_matches_monolithic_states_ledgers_and_faces(self):
        hierarchy = _m4_test_td_basin_storage_compiled_driver_build_basin_hierarchy(_m4_test_td_basin_storage_compiled_driver_make_td_source(_m4_test_td_basin_storage_compiled_driver_np.array([[2., 0., 1.], [0., 2., 0.]]), spacing_m=30))
        for step in (5., 2.5):
            rain = _m4_test_td_basin_storage_compiled_driver_np.array([30., 0., 10.])
            config = {"substep_s": step}
            forcing_id = _m4_test_td_basin_storage_compiled_driver_identity({"rain_mm_h":rain},{"dt_s":60.})
            full = _m4_test_td_basin_storage_compiled_driver_monolithic(hierarchy, rain, dt_s=60, parameters=config)
            checkpoint = None
            pages = []
            with _m4_test_td_basin_storage_compiled_driver_tempfile.TemporaryDirectory() as directory:
                for index, value in enumerate(rain):
                    result = _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_compiled_driver_np.array([value]), dt_s=60, parameters=config,
                                                    checkpoint=checkpoint, forcing_identity=forcing_id,full_rain_mm_h=rain)
                    pages.append(result["storage"])
                    path = _m4_test_td_basin_storage_compiled_driver_Path(directory) / f"{index}.npz"
                    _m4_test_td_basin_storage_compiled_driver_save_checkpoint(path, result["checkpoint"])
                    checkpoint = _m4_test_td_basin_storage_compiled_driver_load_checkpoint(path, expected_sha256=_m4_test_td_basin_storage_compiled_driver_file_sha256(path), expected_identity=result["checkpoint"]["identity_sha256"])
            for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
                _m4_test_td_basin_storage_compiled_driver_np.testing.assert_allclose(_m4_test_td_basin_storage_compiled_driver_np.concatenate([pages[0]["arrays"][key][:1]]+[page["arrays"][key][1:] for page in pages]),full["arrays"][key],rtol=0,atol=1e-12)
            for key in ("rain_volume_m3", "storage_change_m3", "balance_residual_m3", "internal_net_m3"):
                _m4_test_td_basin_storage_compiled_driver_np.testing.assert_allclose(_m4_test_td_basin_storage_compiled_driver_np.concatenate([page["arrays"][key] for page in pages]),full["arrays"][key],rtol=1e-12,atol=1e-10)
            for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s"):
                _m4_test_td_basin_storage_compiled_driver_np.testing.assert_allclose(checkpoint["arrays"]["cumulative_"+key],full["arrays"][key],rtol=1e-14,atol=1e-14)
            self.assertEqual(checkpoint["metadata"]["elapsed_s"],180)
            self.assertEqual(checkpoint["metadata"]["substeps"],round(180/step))
            with self.assertRaisesRegex(ValueError,"forcing"):
                _m4_test_td_basin_storage_compiled_driver_simulate_basin_storage(hierarchy,_m4_test_td_basin_storage_compiled_driver_np.zeros(1),dt_s=60,parameters=config,checkpoint=checkpoint,forcing_identity="b"*64,full_rain_mm_h=rain)

# --- tests/test_td_basin_storage_continuation.py:16 ---
class BasinStorageContinuationContinuationTests(_m4_test_td_basin_storage_continuation_unittest.TestCase):
    def test_checkpoint_rejects_time_geometry_forcing_and_initial_override(self):
        hierarchy = _m4_test_td_basin_storage_continuation_build_basin_hierarchy(_m4_test_td_basin_storage_continuation_make_td_source(_m4_test_td_basin_storage_continuation_np.zeros((2,2)),spacing_m=30))
        rain=_m4_test_td_basin_storage_continuation_np.array([30.,0.])
        forcing_id=_m4_test_td_basin_storage_continuation_identity({"rain_mm_h":rain},{"dt_s":60.})
        result=_m4_test_td_basin_storage_continuation_simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},forcing_identity=forcing_id,full_rain_mm_h=rain)
        checkpoint=result["checkpoint"]
        with self.assertRaisesRegex(ValueError,"mutually"):
            _m4_test_td_basin_storage_continuation_simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},checkpoint=checkpoint,initial_depth_m=_m4_test_td_basin_storage_continuation_np.zeros((2,2)),forcing_identity=forcing_id,full_rain_mm_h=rain)
        with self.assertRaisesRegex(ValueError,"slice"):
            _m4_test_td_basin_storage_continuation_simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},checkpoint=checkpoint,forcing_identity=forcing_id,full_rain_mm_h=rain)
        for name,value in (("elapsed_s",61.),("elapsed_s",float("nan")),("cells",5),("faces",3),("substeps",True)):
            metadata={**checkpoint["metadata"],name:value}
            with self.assertRaises(ValueError):
                forged={"arrays":checkpoint["arrays"],"metadata":metadata,"identity_sha256":_m4_test_td_basin_storage_continuation_identity(checkpoint["arrays"],metadata)}
                _m4_test_td_basin_storage_continuation_simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},checkpoint=forged,forcing_identity=forcing_id,full_rain_mm_h=rain)
        for invalid in (_m4_test_td_basin_storage_continuation_np.array([_m4_test_td_basin_storage_continuation_np.nan]),_m4_test_td_basin_storage_continuation_np.array([-1.]),_m4_test_td_basin_storage_continuation_np.array([1e7]),_m4_test_td_basin_storage_continuation_np.zeros((1,3,4))):
            with self.assertRaises(ValueError):
                _m4_test_td_basin_storage_continuation_simulate_basin_storage(hierarchy,_m4_test_td_basin_storage_continuation_np.zeros(1),dt_s=60,forcing_identity=forcing_id,full_rain_mm_h=invalid)
        with _m4_test_td_basin_storage_continuation_tempfile.TemporaryDirectory() as directory:
            path=_m4_test_td_basin_storage_continuation_Path(directory)/"checkpoint.npz"
            _m4_test_td_basin_storage_continuation_save_checkpoint(path,checkpoint)
            code='from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as load_checkpoint; import sys; load_checkpoint(sys.argv[1],expected_sha256=sys.argv[2],expected_identity=sys.argv[3]); assert "terrain_pipeline.basin_storage" in sys.modules; assert \'terrain_pipeline.td_basin_storage_continuation\' not in sys.modules'
            completed=_m4_test_td_basin_storage_continuation_subprocess.run([_m4_test_td_basin_storage_continuation_sys.executable,"-c",code,str(path),_m4_test_td_basin_storage_continuation_file_sha256(path),checkpoint["identity_sha256"]],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)

    def test_reload_matches_monolithic_states_ledgers_and_faces(self):
        hierarchy = _m4_test_td_basin_storage_continuation_build_basin_hierarchy(_m4_test_td_basin_storage_continuation_make_td_source(_m4_test_td_basin_storage_continuation_np.array([[2., 0., 1.], [0., 2., 0.]]), spacing_m=30))
        for step in (5., 2.5):
            rain = _m4_test_td_basin_storage_continuation_np.array([30., 0., 10.])
            config = {"substep_s": step}
            forcing_id = _m4_test_td_basin_storage_continuation_identity({"rain_mm_h":rain},{"dt_s":60.})
            full = _m4_test_td_basin_storage_continuation_monolithic(hierarchy, rain, dt_s=60, parameters=config)
            checkpoint = None
            pages = []
            with _m4_test_td_basin_storage_continuation_tempfile.TemporaryDirectory() as directory:
                for index, value in enumerate(rain):
                    result = _m4_test_td_basin_storage_continuation_simulate_basin_storage(hierarchy, _m4_test_td_basin_storage_continuation_np.array([value]), dt_s=60, parameters=config,
                                                    checkpoint=checkpoint, forcing_identity=forcing_id,full_rain_mm_h=rain)
                    pages.append(result["storage"])
                    path = _m4_test_td_basin_storage_continuation_Path(directory) / f"{index}.npz"
                    _m4_test_td_basin_storage_continuation_save_checkpoint(path, result["checkpoint"])
                    checkpoint = _m4_test_td_basin_storage_continuation_load_checkpoint(path, expected_sha256=_m4_test_td_basin_storage_continuation_file_sha256(path), expected_identity=result["checkpoint"]["identity_sha256"])
            for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
                _m4_test_td_basin_storage_continuation_np.testing.assert_array_equal(_m4_test_td_basin_storage_continuation_np.concatenate([pages[0]["arrays"][key][:1]]+[page["arrays"][key][1:] for page in pages]),full["arrays"][key])
            for key in ("rain_volume_m3", "storage_change_m3", "balance_residual_m3", "internal_net_m3"):
                _m4_test_td_basin_storage_continuation_np.testing.assert_array_equal(_m4_test_td_basin_storage_continuation_np.concatenate([page["arrays"][key] for page in pages]),full["arrays"][key])
            for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s"):
                _m4_test_td_basin_storage_continuation_np.testing.assert_allclose(checkpoint["arrays"]["cumulative_"+key],full["arrays"][key],rtol=1e-14,atol=1e-14)
            self.assertEqual(checkpoint["metadata"]["elapsed_s"],180)
            self.assertEqual(checkpoint["metadata"]["substeps"],round(180/step))
            with self.assertRaisesRegex(ValueError,"forcing"):
                _m4_test_td_basin_storage_continuation_simulate_basin_storage(hierarchy,_m4_test_td_basin_storage_continuation_np.zeros(1),dt_s=60,parameters=config,checkpoint=checkpoint,forcing_identity="b"*64,full_rain_mm_h=rain)
