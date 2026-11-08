import tempfile
import unittest
import subprocess
import sys
from pathlib import Path
import numpy as np
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import storagev7_simulate as monolithic
from terrain_pipeline.basin_storage import continuation_simulate as simulate_basin_storage
from terrain_pipeline.basin_storage import checkpointio_save_checkpoint as save_checkpoint
from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as load_checkpoint
from terrain_pipeline.common_infra import file_sha256, identity


class ContinuationTests(unittest.TestCase):
    def test_checkpoint_rejects_time_geometry_forcing_and_initial_override(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.zeros((2,2)),spacing_m=30))
        rain=np.array([30.,0.])
        forcing_id=identity({"rain_mm_h":rain},{"dt_s":60.})
        result=simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},forcing_identity=forcing_id,full_rain_mm_h=rain)
        checkpoint=result["checkpoint"]
        with self.assertRaisesRegex(ValueError,"mutually"):
            simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},checkpoint=checkpoint,initial_depth_m=np.zeros((2,2)),forcing_identity=forcing_id,full_rain_mm_h=rain)
        with self.assertRaisesRegex(ValueError,"slice"):
            simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},checkpoint=checkpoint,forcing_identity=forcing_id,full_rain_mm_h=rain)
        for name,value in (("elapsed_s",61.),("elapsed_s",float("nan")),("cells",5),("faces",3),("substeps",True)):
            metadata={**checkpoint["metadata"],name:value}
            with self.assertRaises(ValueError):
                forged={"arrays":checkpoint["arrays"],"metadata":metadata,"identity_sha256":identity(checkpoint["arrays"],metadata)}
                simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":2.5},checkpoint=forged,forcing_identity=forcing_id,full_rain_mm_h=rain)
        for invalid in (np.array([np.nan]),np.array([-1.]),np.array([1e7]),np.zeros((1,3,4))):
            with self.assertRaises(ValueError):
                simulate_basin_storage(hierarchy,np.zeros(1),dt_s=60,forcing_identity=forcing_id,full_rain_mm_h=invalid)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"checkpoint.npz"
            save_checkpoint(path,checkpoint)
            code='from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as load_checkpoint; import sys; load_checkpoint(sys.argv[1],expected_sha256=sys.argv[2],expected_identity=sys.argv[3]); assert "terrain_pipeline.basin_storage" in sys.modules; assert \'terrain_pipeline.td_basin_storage_continuation\' not in sys.modules'
            completed=subprocess.run([sys.executable,"-c",code,str(path),file_sha256(path),checkpoint["identity_sha256"]],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)

    def test_reload_matches_monolithic_states_ledgers_and_faces(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.array([[2., 0., 1.], [0., 2., 0.]]), spacing_m=30))
        for step in (5., 2.5):
            rain = np.array([30., 0., 10.])
            config = {"substep_s": step}
            forcing_id = identity({"rain_mm_h":rain},{"dt_s":60.})
            full = monolithic(hierarchy, rain, dt_s=60, parameters=config)
            checkpoint = None
            pages = []
            with tempfile.TemporaryDirectory() as directory:
                for index, value in enumerate(rain):
                    result = simulate_basin_storage(hierarchy, np.array([value]), dt_s=60, parameters=config,
                                                    checkpoint=checkpoint, forcing_identity=forcing_id,full_rain_mm_h=rain)
                    pages.append(result["storage"])
                    path = Path(directory) / f"{index}.npz"
                    save_checkpoint(path, result["checkpoint"])
                    checkpoint = load_checkpoint(path, expected_sha256=file_sha256(path), expected_identity=result["checkpoint"]["identity_sha256"])
            for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
                np.testing.assert_array_equal(np.concatenate([pages[0]["arrays"][key][:1]]+[page["arrays"][key][1:] for page in pages]),full["arrays"][key])
            for key in ("rain_volume_m3", "storage_change_m3", "balance_residual_m3", "internal_net_m3"):
                np.testing.assert_array_equal(np.concatenate([page["arrays"][key] for page in pages]),full["arrays"][key])
            for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s"):
                np.testing.assert_allclose(checkpoint["arrays"]["cumulative_"+key],full["arrays"][key],rtol=1e-14,atol=1e-14)
            self.assertEqual(checkpoint["metadata"]["elapsed_s"],180)
            self.assertEqual(checkpoint["metadata"]["substeps"],round(180/step))
            with self.assertRaisesRegex(ValueError,"forcing"):
                simulate_basin_storage(hierarchy,np.zeros(1),dt_s=60,parameters=config,checkpoint=checkpoint,forcing_identity="b"*64,full_rain_mm_h=rain)


if __name__ == "__main__":
    unittest.main()
