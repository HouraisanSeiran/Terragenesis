import unittest
import tempfile
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_storage_compiled_driver import simulate_basin_storage
from terrain_pipeline.mountain_source_adapter import identity


class SpatialContinuationTests(unittest.TestCase):
    def test_weather_index_external_pin_and_schema_rejection(self):
        hierarchy=build_basin_hierarchy(make_td_source(np.zeros((2,2)),spacing_m=30))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"index.json"
            path.write_text(json.dumps({"schema":"wrong","cases":{}}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"SHA"):
                from terrain_pipeline.td_native_weather_storage_inputs import load_weather_inputs
                load_weather_inputs(path,expected_sha256="0"*64,hierarchy=hierarchy)

    def test_weather_driver_requires_complete_plan_identity(self):
        hierarchy=build_basin_hierarchy(make_td_source(np.zeros((2,2)),spacing_m=30))
        rain=np.zeros((2,2,2))
        forcing_id=identity({"rain_mm_h":rain},{"dt_s":60.})
        with self.assertRaises(ValueError):
            simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":2.5},full_rain_mm_h=rain,forcing_identity="0"*64)
    def test_full3d_rain_checkpoint_slice_and_identity(self):
        hierarchy=build_basin_hierarchy(make_td_source(np.array([[0.,1.],[2.,0.]]),spacing_m=30))
        rain=np.array([[[30.,10.],[5.,20.]],[[0.,0.],[0.,0.]]])
        forcing_id=identity({"rain_mm_h":rain},{"dt_s":60.})
        for step in (2.5,1.25):
            first=simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":step},full_rain_mm_h=rain,forcing_identity=forcing_id)
            second=simulate_basin_storage(hierarchy,rain[1:],dt_s=60,parameters={"substep_s":step},full_rain_mm_h=rain,forcing_identity=forcing_id,checkpoint=first["checkpoint"])
            whole=simulate_basin_storage(hierarchy,rain,dt_s=60,parameters={"substep_s":step},full_rain_mm_h=rain,forcing_identity=forcing_id)
            for key in ("depth_m","soil_mm","fast_mm","slow_mm"):
                np.testing.assert_array_equal(second["storage"]["arrays"][key][-1],whole["storage"]["arrays"][key][-1])
            with self.assertRaisesRegex(ValueError,"slice"):
                simulate_basin_storage(hierarchy,rain[:1],dt_s=60,parameters={"substep_s":step},full_rain_mm_h=rain,forcing_identity=forcing_id,checkpoint=first["checkpoint"])
