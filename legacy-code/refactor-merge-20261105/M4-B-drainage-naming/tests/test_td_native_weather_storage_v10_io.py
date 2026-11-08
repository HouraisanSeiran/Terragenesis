import copy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
import json
import subprocess
import sys

import numpy as np

from terrain_pipeline.common_infra import identity, file_sha256, save_bundle
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import STORAGEV10_PROFILE as PROFILE
from terrain_pipeline.basin_storage import STATES as STATES
from terrain_pipeline.basin_storage import ERRORS as ERRORS
from terrain_pipeline.basin_storage import LEDGERS as LEDGERS
from terrain_pipeline.basin_storage import FLUX as FLUX
from terrain_pipeline.td_native_weather_storage_v10_io import load_native_weather_v10_hour, load_native_weather_storage_v10_index, PHYSICS, PHYSICS_SEMANTICS


class NativeWeatherV10IoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.hierarchy = build_basin_hierarchy(make_td_source(np.array([[0., 1.]]), spacing_m=30.))
        self.parameters = copy.deepcopy(PHYSICS)
        self.runoff = asdict(RunoffParameters())
        self.rain = np.full((1, 2), 1., np.float64)
        topology = self.hierarchy["arrays"]
        arrays = {name:topology[name].copy() for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells")}
        arrays["boundary_width_m"] = np.zeros(len(topology["boundary_cells"]), np.float64)
        arrays.update({name:np.zeros((2, 2), np.float64) for name in STATES})
        arrays["soil_mm"][:] = [[30., 30.], [31., 31.]]
        arrays.update({name:np.zeros((1, 2), np.float64) for name in LEDGERS})
        arrays["rain_mm_h"] = self.rain.copy()
        for name in ("rain_volume_m3", "rain_infiltration_m3", "storage_change_m3"):
            arrays[name][:] = .9
        arrays["infiltration_capacity_m3"][:] = 13.5
        arrays.update({name:np.zeros(len(topology["face_cells"]) if name.startswith(("face_", "active_")) else 2, np.float64) for name in FLUX})
        metadata = dict(schema="td-v10-hour-page-v1", profile=PROFILE, hierarchy_identity=self.hierarchy["identity_sha256"],
                        forcing_identity="a"*64, cells=2, faces=len(topology["face_cells"]), substeps=1440,
                        forcing_hour_offset=0, dt_s=3600., substep_s=2.5, spacing_m=30.,
                        origin_m_xz=self.hierarchy["metadata"]["origin_m_xz"], start_s=0., end_s=3600.,
                        positivity_cfl=.05, parameters=dict(self.parameters, substep_s=2.5), runoff_parameters=self.runoff,
                        physics=PHYSICS_SEMANTICS, permanent_lake_impermeability="not modelled; requires independent material mask",
                        activity_semantics="SSP-RK2 stage quadrature of actual signed exchange; not exact event duration",
                        hydraulic_ready=False, transient_converged=False, publishable=False)
        self.storage = dict(arrays=arrays, metadata=metadata)
        self.checkpoint = dict(arrays={name:arrays[name][1].copy() for name in STATES},
                               metadata=dict(metadata, schema="td-v10-hour-checkpoint-v1"))
        self.checkpoint["arrays"].update({name:np.zeros(2) for name in ERRORS})
        self.checkpoint["arrays"].update({"cumulative_"+name:arrays[name].copy() for name in FLUX})

    def tearDown(self):
        self.temp.cleanup()

    def _save(self, name, result):
        result["identity_sha256"] = identity(result["arrays"], result["metadata"])
        path = self.root / (name+".npz")
        if path.exists():
            path.unlink()
        save_bundle(path, result, validator=lambda value:None)
        return dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])

    def _load(self):
        storage_record = self._save("storage", self.storage)
        self.checkpoint["metadata"]["last_page_identity"] = storage_record["expected_identity"]
        checkpoint_record = self._save("checkpoint", self.checkpoint)
        return load_native_weather_v10_hour(storage_record, checkpoint_record, hierarchy=self.hierarchy,
            rain_mm_h=self.rain, forcing_identity="a"*64, hour=0, step_s=2.5,
            parameters=self.parameters, runoff_parameters=self.runoff)

    def test_valid_actual_compartment_fixture(self):
        result = self._load()
        self.assertTrue(result["hour_io_accepted"])
        self.assertFalse(result["complete_index_accepted"])
        self.assertFalse(result["solver_advanced"])

    def test_rehashed_rain_and_compartment_reallocation_rejected(self):
        original = copy.deepcopy(self.storage)
        for kind in ("rain", "soil", "capacity", "receiver", "time", "origin"):
            with self.subTest(kind=kind):
                self.storage = copy.deepcopy(original)
                arrays = self.storage["arrays"]
                if kind == "rain":
                    arrays["rain_mm_h"][:] = [[.5, 1.5]]
                elif kind == "soil":
                    arrays["rain_infiltration_m3"][:] = .4
                    arrays["rain_excess_m3"][:] = .5
                elif kind == "capacity":
                    arrays["infiltration_capacity_m3"][:] = 20.
                elif kind == "time":
                    self.storage["metadata"].update(forcing_hour_offset=1,start_s=3600.,end_s=7200.)
                elif kind == "origin":
                    self.storage["metadata"]["origin_m_xz"] = [1.,0.]
                else:
                    arrays["routed_volume_m3"][0] = .1
                with self.assertRaises(ValueError):
                    self._load()

    def test_checkpoint_endpoint_cumulative_and_config_rejected(self):
        original = copy.deepcopy(self.checkpoint)
        for kind in ("state", "cumulative", "profile", "config", "offset"):
            with self.subTest(kind=kind):
                self.checkpoint = copy.deepcopy(original)
                if kind == "state":
                    self.checkpoint["arrays"]["soil_mm"][0] += 1.
                elif kind == "cumulative":
                    self.checkpoint["arrays"]["cumulative_face_forward_m3"][0] = .1
                elif kind == "profile":
                    self.checkpoint["metadata"]["profile"] = "v9-compiled-hour-loop-v8-equivalent-v1"
                elif kind == "offset":
                    self.checkpoint["metadata"]["forcing_hour_offset"] = 1
                else:
                    self.checkpoint["metadata"]["parameters"]["face_conductance_m_s"] = .7
                with self.assertRaises(ValueError):
                    self._load()

    def test_wrong_slice_unknown_shape_and_step_rejected(self):
        original = self.rain.copy()
        for rain in (np.full((2,1),1.), np.full((1,2),2.), np.full((1,2),np.nan)):
            self.rain = rain
            with self.assertRaises(ValueError):
                self._load()
        self.rain = original
        with self.assertRaises(ValueError):
            load_native_weather_v10_hour({}, {}, hierarchy=self.hierarchy, rain_mm_h=self.rain,
                forcing_identity="a"*64, hour=0, step_s=.625, parameters=self.parameters, runoff_parameters=self.runoff)

    def _whole_fixture(self):
        from terrain_pipeline.basin_storage import save_td_source as save_td_source
        from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
        from terrain_pipeline.climate_forcing import generate_native_storm, fixed_storm, save_native_storm
        source = make_td_source(np.array([[0.,1.]]),spacing_m=30.)
        source_path, hierarchy_path = self.root/"source.npz", self.root/"hierarchy.npz"
        save_td_source(source_path,source)
        save_basin_hierarchy(hierarchy_path,self.hierarchy)
        source_record = dict(path=str(source_path),expected_sha256=file_sha256(source_path),expected_identity=source["identity_sha256"])
        hierarchy_record = dict(path=str(hierarchy_path),expected_sha256=file_sha256(hierarchy_path),expected_identity=self.hierarchy["identity_sha256"])
        def write(name,value):
            target = self.root/name
            target.write_text(json.dumps(value),encoding="utf8")
            return dict(path=str(target),expected_sha256=file_sha256(target))
        fixture_code = self.root/"fixture-code.txt"
        fixture_code.write_text("fixed synthetic account construction, no solver",encoding="utf8")
        codes = {fixture_code.name:file_sha256(fixture_code)}
        weather_cases, scenarios = {}, {}
        budgets = {str(step):dict(chunk_face_steps=int(3600/step),global_face_steps_per_direction=24*int(3600/step)) for step in (2.5,1.25)}
        for direction in ("eastward","westward"):
            weather = generate_native_storm(source_record,parameters=fixed_storm(source,direction))
            weather_path = self.root/(direction+".npz")
            save_native_storm(weather_path,weather)
            record = dict(path=str(weather_path),expected_sha256=file_sha256(weather_path),expected_identity=weather["identity_sha256"])
            forcing = weather["metadata"]["forcing_identity"]
            weather_cases[direction] = dict(record=record,plan=weather["metadata"]["plan"],forcing_identity=forcing)
            groups = {}
            for step in (2.5,1.25):
                pages = []
                soil = np.full(2,30.)
                for hour in range(24):
                    storage = copy.deepcopy(self.storage)
                    arrays = storage["arrays"]
                    rain = weather["arrays"]["rain_mm_h"][hour].reshape(1,2)
                    arrays["soil_mm"][0] = soil
                    arrays["soil_mm"][1] = soil + rain[0]
                    soil = arrays["soil_mm"][1].copy()
                    arrays["rain_mm_h"] = rain.copy()
                    for name in ("rain_volume_m3","rain_infiltration_m3","storage_change_m3"):
                        arrays[name] = rain*.9
                    storage["metadata"].update(forcing_identity=forcing,forcing_hour_offset=hour,start_s=hour*3600.,
                        end_s=(hour+1)*3600.,substeps=int(3600/step),substep_s=step,positivity_cfl=.6*step/30.,parameters=dict(self.parameters,substep_s=step))
                    directory = self.root/f"{direction}-{step:g}s"/f"hour-{hour:02d}"
                    directory.mkdir(parents=True)
                    storage["identity_sha256"] = identity(arrays,storage["metadata"])
                    save_bundle(directory/"storage.npz",storage,validator=lambda value:None)
                    cp = copy.deepcopy(self.checkpoint)
                    cp["arrays"]["soil_mm"] = soil.copy()
                    cp["metadata"] = dict(storage["metadata"],schema="td-v10-hour-checkpoint-v1",last_page_identity=storage["identity_sha256"])
                    cp["identity_sha256"] = identity(cp["arrays"],cp["metadata"])
                    save_bundle(directory/"checkpoint.npz",cp,validator=lambda value:None)
                    pages.append(dict(hour=hour,storage=dict(path=str(directory/"storage.npz"),expected_sha256=file_sha256(directory/"storage.npz"),expected_identity=storage["identity_sha256"]),
                        checkpoint=dict(path=str(directory/"checkpoint.npz"),expected_sha256=file_sha256(directory/"checkpoint.npz"),expected_identity=cp["identity_sha256"]),
                        forcing_identity=forcing,chunk_work_face_steps=int(3600/step)))
                groups[str(step)] = pages
            scenarios[direction] = dict(schema="td-v10-spatial-weather-comparison-v1",pages=groups,
                hour_comparisons=[dict(hour=hour,max_depth_difference_m=0.,frame=0,cell=0) for hour in range(24)],
                max_saved_depth_difference_m=0.,cumulative_receiver_relative_l1=0.,gate_passed=True,
                weather_record=record,forcing_identity=forcing,steps_s=[2.5,1.25],hydraulic_ready=False,publishable=False)
        weather_record = write("weather-index.json",dict(schema="td-native-storm-forcing-index-v1",source=source_record,cases=weather_cases))
        weather_pin = dict(path=weather_record["path"],sha256=weather_record["expected_sha256"])
        index = dict(schema="td-v10-spatial-weather-hour-pages-index-v1",scenarios=scenarios,weather_index=weather_pin,steps_s=[2.5,1.25],
                     code_sha256=codes,budgets=budgets,all_numerical_gates_passed=True,hydraulic_ready=False,transient_converged=False,publishable=False)
        index_record = write("index.json",index)
        inputs_record = write("run-inputs.json",dict(schema="td-v10-spatial-weather-run-inputs-v1",weather_index=weather_pin,
            weather_records={name:value["record"] for name,value in weather_cases.items()},hierarchy=hierarchy_record,primary_sha256="0"*64,
            steps_s=[2.5,1.25],budgets=budgets,chunk_max_face_steps=6000000000,job_max_bytes=1073741824,code_sha256=codes,
            physics_version="v10-unified-infiltration; not execution-equivalence",forcing_identities={name:value["forcing_identity"] for name,value in weather_cases.items()},depth_gate_m=.001,receiver_gate=.01))
        resource_record = write("resource.json",dict(schema="td-v10-spatial-weather-resource-v1",index_sha256=index_record["expected_sha256"],
            scope="complete eastward+westward both steps execution",complete=True,peak_rss_bytes=1000000,peak_private_bytes=1000000,sample_count=1,sampling_interval_s=2,monitor_error=None))
        return dict(expected_sha256=index_record["expected_sha256"],weather_index_record=weather_record,hierarchy_record=hierarchy_record,
                    source_record=source_record,run_inputs_record=inputs_record,execution_resource_record=resource_record,scope="synthetic_fixture",code_root=str(self.root))

    def _repin_index(self,index,args):
        path = self.root/"index.json"
        path.write_text(json.dumps(index),encoding="utf8")
        args["expected_sha256"] = file_sha256(path)
        path = self.root/"resource.json"
        resource = json.loads(path.read_text())
        resource["index_sha256"] = args["expected_sha256"]
        path.write_text(json.dumps(resource),encoding="utf8")
        args["execution_resource_record"]["expected_sha256"] = file_sha256(path)

    def test_complete_index_cold_and_fresh_no_solver(self):
        args = self._whole_fixture()
        result = load_native_weather_storage_v10_index(self.root/"index.json",**args)
        self.assertTrue(result["io_chain_accepted"])
        self.assertTrue(result["cases"]["eastward"]["numerical_gate_passed"])
        path = self.root/"arguments.json"
        path.write_text(json.dumps(args),encoding="utf8")
        script = '''import sys,json,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.startswith('numba') or fullname in ('terrain_pipeline.td_basin_storage_v10','terrain_pipeline.td_basin_forcing_v10','terrain_pipeline.td_basin_storage_compiled','terrain_pipeline.td_basin_storage_compiled_driver'):
   raise RuntimeError('solver import forbidden')
sys.meta_path.insert(0,Block())
from terrain_pipeline import td_basin_hierarchy,td_native_storm_forcing
def forbidden(*args,**kwargs): raise RuntimeError('generation forbidden')
td_basin_hierarchy.build_basin_hierarchy=forbidden
td_native_storm_forcing.generate_native_storm=forbidden
from terrain_pipeline.td_native_weather_storage_v10_io import load_native_weather_storage_v10_index
assert load_native_weather_storage_v10_index(sys.argv[2],**json.load(open(sys.argv[1])))['io_chain_accepted']
'''
        completed = subprocess.run([sys.executable,"-c",script,str(path),str(self.root/"index.json")],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def test_complete_index_coverage_resource_and_gate_tamper(self):
        args = self._whole_fixture()
        original = json.loads((self.root/"index.json").read_text())
        for kind in ("missing","order","step","gate"):
            with self.subTest(kind=kind):
                index = copy.deepcopy(original)
                if kind == "missing":
                    index["scenarios"]["westward"]["pages"]["1.25"].pop()
                elif kind == "order":
                    index["scenarios"]["eastward"]["pages"]["2.5"].reverse()
                elif kind == "step":
                    index["steps_s"] = [5.,2.5]
                else:
                    index["all_numerical_gates_passed"] = False
                self._repin_index(index,args)
                with self.assertRaises(ValueError):
                    load_native_weather_storage_v10_index(self.root/"index.json",**args)
        self._repin_index(original,args)
        path = self.root/"resource.json"
        resource = json.loads(path.read_text())
        resource["peak_private_bytes"] = 1073741825
        path.write_text(json.dumps(resource),encoding="utf8")
        args["execution_resource_record"]["expected_sha256"] = file_sha256(path)
        with self.assertRaisesRegex(ValueError,"resource exceeded"):
            load_native_weather_storage_v10_index(self.root/"index.json",**args)

    def test_gross_swap_preserving_total_water_rejected(self):
        self.storage["arrays"]["soil_et_m3"][:] = .05
        self.storage["arrays"]["percolation_m3"][:] = .05
        self.storage["arrays"]["soil_mm"][1] -= .1/.9
        self.storage["arrays"]["slow_mm"][1] += .05/.9
        self.storage["arrays"]["storage_change_m3"][:] -= .05
        for name in STATES:
            self.checkpoint["arrays"][name] = self.storage["arrays"][name][1].copy()
        self.assertTrue(self._load()["hour_io_accepted"])
        self.storage["arrays"]["percolation_m3"][:] = 0.
        self.storage["arrays"]["surface_infiltration_m3"][:] = .05
        with self.assertRaisesRegex(ValueError,"compartment"):
            self._load()


if __name__ == "__main__":
    unittest.main()
