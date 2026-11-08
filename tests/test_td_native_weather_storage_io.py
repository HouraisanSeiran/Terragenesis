import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
import io
import zipfile

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, save_bundle, load_bundle
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_storage import save_td_source as save_td_source
from terrain_pipeline.climate_forcing import generate_native_storm, fixed_storm
from terrain_pipeline.td_native_weather_storage_io import load_native_weather_storage_index


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return {"path": str(path), "expected_sha256": file_sha256(path)}


def write_bundle(path, arrays, metadata):
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    path.parent.mkdir(parents=True, exist_ok=True)
    save_bundle(path, result, validator=lambda value: None)
    return {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": result["identity_sha256"]}


class NativeWeatherStorageIoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        source = make_td_source(np.array([[0., 2., 0.]]), spacing_m=30., valid_mask=np.array([[True, True, not getattr(self, "unknown_fixture", False)]]))
        self.source_path = self.root / "source.npz"
        save_td_source(self.source_path, source)
        self.source_record = dict(path=str(self.source_path), expected_sha256=file_sha256(self.source_path), expected_identity=source["identity_sha256"])
        hierarchy = build_basin_hierarchy(source)
        self.hierarchy_path = self.root / "hierarchy.npz"
        save_basin_hierarchy(self.hierarchy_path, hierarchy)
        self.hierarchy_record = dict(path=str(self.hierarchy_path), expected_sha256=file_sha256(self.hierarchy_path), expected_identity=hierarchy["identity_sha256"])
        self.hierarchy = hierarchy
        self.rains = {}
        weather_cases = {}
        for direction in ("eastward", "westward"):
            params = fixed_storm(source, direction)
            result = generate_native_storm(self.source_record, parameters=params)
            rain_path = self.root / (direction + ".npz")
            from terrain_pipeline.climate_forcing import save_native_storm
            save_native_storm(rain_path, result)
            weather_cases[direction] = dict(record=dict(path=str(rain_path), expected_sha256=file_sha256(rain_path), expected_identity=result["identity_sha256"]), plan=result["metadata"]["plan"], forcing_identity=result["metadata"]["forcing_identity"])
            self.rains[direction] = result["arrays"]["rain_mm_h"]
        self.weather_cases = weather_cases
        self.weather_path = self.root / "weather-index.json"
        self.weather_record = write_json(self.weather_path, dict(schema="td-native-storm-forcing-index-v1", source=self.source_record, cases=weather_cases))
        self.args = self._make_pages()
        self.args["expected_parameters"].pop("substep_s")

    def tearDown(self):
        self.temp.cleanup()

    def _make_pages(self, fine_soil=False):
        cells = 3
        faces = len(self.hierarchy["arrays"]["face_cells"])
        flags = dict(hydraulic_ready=False, transient_converged=False, morphology_flux_ready=False, natural_outlet_verified=False, publishable=False)
        scenarios = {}
        for direction, rain in self.rains.items():
            groups = {}
            for step in (2.5, 1.25):
                pages = []
                cumulative = {"face_forward_m3": np.zeros(faces), "face_reverse_m3": np.zeros(faces), "active_forward_s": np.zeros(faces), "active_reverse_s": np.zeros(faces), "routed_volume_m3": np.zeros(cells), "wet_duration_s": np.zeros(cells)}
                previous_states = {"depth_m": np.zeros(cells), "soil_mm": np.where(self.hierarchy["arrays"]["valid_mask"].ravel(), 30., 0.), "fast_mm": np.zeros(cells), "slow_mm": np.zeros(cells)}
                for hour in range(24):
                    arrays = {name: self.hierarchy["arrays"][name].copy() for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells")}
                    arrays.update({name: np.zeros((2, cells), np.float64) for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm")})
                    rain_slice = rain[hour].reshape(1, cells)
                    for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
                        arrays[name][0] = previous_states[name]
                    arrays["depth_m"][1] = previous_states["depth_m"] + rain_slice[0] / 1000.
                    arrays["soil_mm"][1] = previous_states["soil_mm"]
                    if fine_soil and step == 1.25:
                        arrays["depth_m"][1] = previous_states["depth_m"]
                        arrays["soil_mm"][1] += rain_slice[0]
                    for name in ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3", "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3"):
                        arrays[name] = np.zeros((1, cells), np.float64)
                    arrays["rain_mm_h"] = rain_slice
                    rain_m3 = rain_slice * 900 / 1000
                    arrays["rain_volume_m3"] = rain_m3.copy(); arrays["land_rain_m3"] = rain_m3.copy(); arrays["storage_change_m3"] = rain_m3.copy()
                    arrays.update({name: np.zeros(faces, np.float64) for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s")})
                    arrays.update({name: np.zeros(cells, np.float64) for name in ("routed_volume_m3", "wet_duration_s")})
                    boundary = self.hierarchy["arrays"]["boundary_cells"]
                    rows, columns = np.divmod(boundary, self.hierarchy["arrays"]["height_m"].shape[1])
                    arrays["boundary_width_m"] = 30. * ((rows == 0).astype(int) + (rows == 0) + (columns == 0) + (columns == 2)).astype(np.float64)
                    arrays["wet_pool_count"] = np.zeros(2, np.int64)
                    config = dict(substep_s=step, face_conductance_m_s=.6, surface_evaporation_mm_h=.15, wet_threshold_m=1e-9, max_substeps=100000, max_work_face_steps=6000000000)
                    runoff = dict(initial_soil_mm=30., initial_fast_mm=0., initial_slow_mm=0., infiltration_capacity_mm_h=15., percolation_mm_h=1., potential_et_mm_h=.15, fast_tau_s=3600., slow_tau_s=259200., soil_capacity_mm=150.)
                    metadata = dict(schema="td-basin-storage-v1", algorithm="D4-threshold-compiled-hour-SSPRK2-v9", work_profile="v9-compiled-hour-loop-v8-equivalent-v1", hierarchy_identity_sha256=self.hierarchy["identity_sha256"], spacing_m=30., origin_m_xz=list(self.hierarchy["metadata"]["origin_m_xz"]), dt_s=3600., substep_s=step, chunk_start_s=hour*3600., chunk_end_s=(hour+1)*3600., forcing_identity=identity({"rain_mm_h":rain},{"dt_s":3600.}), forcing_hour_offset=hour, parameters=config, runoff_parameters=runoff, substeps=int(3600/step), saved_time_semantics="state0 is checkpoint time; state[k] at chunk_start_s+k*dt_s; ledger[k] covers local hour k", forcing_semantics="runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half", activity_semantics="RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity", compensation_semantics="soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation", positivity_cfl=2*.6*step/30, hydraulic_ready=False, transient_converged=False, morphology_flux_ready=False, natural_outlet_verified=False, publishable=False)
                    metadata["positivity_cfl"] = float(np.bincount(arrays["face_cells"].ravel(), minlength=cells).max(initial=0))*.6*step/30
                    storage = write_bundle(self.root / f"{direction}-{step:g}s" / f"hour-{hour:02d}" / "storage.npz", arrays, metadata)
                    saved = {name: arrays[name][-1].copy() for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
                    saved.update({"error_"+name: np.zeros(cells) for name in ("depth", "soil", "fast", "slow")})
                    saved.update({"cumulative_"+name: cumulative[name].copy() for name in cumulative})
                    cpmeta = dict(schema="td-storage-continuation-v1", execution_profile="v9-compiled-hour-loop-v8-equivalent-v1", last_page_storage_identity=storage["expected_identity"], elapsed_s=(hour+1)*3600., dt_s=3600., substep_s=step, substeps=(hour+1)*int(3600/step), work_face_steps=(hour+1)*int(3600/step)*faces, cells=cells, faces=faces, hierarchy_identity_sha256=self.hierarchy["identity_sha256"], parameters=config, runoff_parameters=runoff, forcing_identity=metadata["forcing_identity"], hydraulic_ready=False, transient_converged=False)
                    checkpoint = write_bundle(self.root / f"{direction}-{step:g}s" / f"hour-{hour:02d}" / "checkpoint.npz", saved, cpmeta)
                    pages.append(dict(hour=hour, storage=storage, checkpoint=checkpoint, forcing_identity=metadata["forcing_identity"], chunk_work_face_steps=int(3600/step)*faces, peak_bytes=1))
                    previous_states = {name: arrays[name][-1].copy() for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
                groups[str(step)] = pages
            scenarios[direction] = dict(pages=groups, weather_record=self.weather_cases[direction]["record"], forcing_identity=self.weather_cases[direction]["forcing_identity"], steps_s=[2.5, 1.25], gate_passed=True, max_saved_depth_difference_m=0., cumulative_receiver_relative_l1=0., **flags)
            if fine_soil:
                maximum = float((rain.sum(axis=0)/1000.).max())
                scenarios[direction].update(gate_passed=maximum<=.001, max_saved_depth_difference_m=maximum)
        index = dict(schema="td-v9-spatial-weather-hour-pages-index-v1", steps_s=[2.5, 1.25], weather_index=dict(path=str(self.weather_path), sha256=self.weather_record["expected_sha256"]), scenarios=scenarios, budgets={str(step): dict(chunk_face_steps=int(3600/step)*faces, global_face_steps_per_scenario=24*int(3600/step)*faces) for step in (2.5,1.25)}, code_sha256={"fixture":"a"*64}, all_numerical_gates_passed=True, **flags)
        index["all_numerical_gates_passed"] = all(case["gate_passed"] for case in scenarios.values())
        index_record = write_json(self.root / "index.json", index)
        resource = write_json(self.root / "resource.json", dict(schema="td-v9-spatial-weather-execution-resource-v1", index_sha256=index_record["expected_sha256"], scope="complete eastward+westward both steps execution", complete=True, peak_rss_bytes=1, peak_private_bytes=1, sample_count=1, sampling_interval_s=2, monitor_error=None, thread_environment={name:"1" for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS")}))
        inputs = write_json(self.root / "run-inputs.json", dict(schema="td-v9-spatial-weather-run-inputs-v1", profile="v9-compiled-hour-loop-v8-equivalent-v1", steps_s=[2.5,1.25], weather_index=dict(path=str(self.weather_path), sha256=self.weather_record["expected_sha256"]), weather_records={name: case["record"] for name, case in self.weather_cases.items()}, forcing_identities={name: case["forcing_identity"] for name, case in self.weather_cases.items()}, hierarchy=dict(path=self.hierarchy_record["path"], sha256=self.hierarchy_record["expected_sha256"], identity=self.hierarchy_record["expected_identity"]), depth_gate_m=.001, receiver_gate=.01, budgets=index["budgets"], chunk_max_work_face_steps=6000000000, job_max_bytes=1073741824, code_sha256=index["code_sha256"]))
        return dict(expected_sha256=index_record["expected_sha256"], weather_index_record=self.weather_record, hierarchy_record=self.hierarchy_record, source_record=self.source_record, run_inputs_record=inputs, execution_resource_record=resource, expected_parameters=dict(substep_s=2.5, face_conductance_m_s=.6, surface_evaporation_mm_h=.15, wet_threshold_m=1e-9, max_substeps=100000, max_work_face_steps=6000000000), expected_runoff=dict(initial_soil_mm=30., initial_fast_mm=0., initial_slow_mm=0., infiltration_capacity_mm_h=15., percolation_mm_h=1., potential_et_mm_h=.15, fast_tau_s=3600., slow_tau_s=259200., soil_capacity_mm=150.))

    def test_complete_tiny_cold_load(self):
        accepted = load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")
        self.assertTrue(accepted["io_chain_accepted"])

    def test_missing_index_and_weather_pin_rejected(self):
        args = dict(self.args, expected_sha256="0"*64)
        with self.assertRaises(ValueError):
            load_native_weather_storage_index(self.root / "index.json", **args, scope="synthetic_fixture")
        args = dict(self.args); args["weather_index_record"] = dict(self.weather_record, expected_sha256="0"*64)
        with self.assertRaises(ValueError):
            load_native_weather_storage_index(self.root / "index.json", **args, scope="synthetic_fixture")

    def test_partial_page_and_shape_rejected(self):
        page = json.loads((self.root / "index.json").read_text())["scenarios"]["eastward"]["pages"]["2.5"][0]
        from terrain_pipeline.common_infra import load_bundle
        bundle = load_bundle(page["storage"]["path"], expected_sha256=page["storage"]["expected_sha256"], validator=lambda value: None)
        arrays = {name: value.copy() for name, value in bundle["arrays"].items()}; arrays["rain_mm_h"] = np.zeros((2, 3))
        Path(page["storage"]["path"]).unlink(); page["storage"] = write_bundle(Path(page["storage"]["path"]), arrays, bundle["metadata"])
        index = json.loads((self.root / "index.json").read_text()); index["scenarios"]["eastward"]["pages"]["2.5"][0] = page
        write_json(self.root / "index.json", index); self.args["expected_sha256"] = file_sha256(self.root / "index.json")
        self._repin(index)
        with self.assertRaises(ValueError):
            load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")

    def _repin(self, index):
        self.args["expected_sha256"] = write_json(self.root / "index.json", index)["expected_sha256"]
        resource = json.loads((self.root / "resource.json").read_text())
        resource["index_sha256"] = self.args["expected_sha256"]
        self.args["execution_resource_record"] = write_json(self.root / "resource.json", resource)

    def test_rehashed_checkpoint_chain_and_metadata_rejected(self):
        original = json.loads((self.root / "index.json").read_text())
        page = original["scenarios"]["eastward"]["pages"]["2.5"][1]
        record = page["checkpoint"]
        target = Path(record["path"])
        raw = target.read_bytes()
        bundle = load_bundle(target, expected_sha256=record["expected_sha256"], validator=lambda value: None)
        mutations = [("cumulative_face_forward_m3", 1.), ("cumulative_routed_volume_m3", 1.),
                     ("cumulative_active_forward_s", 1.), ("elapsed_s", 3600.),
                     ("forcing_identity", "0"*64), ("last_page_storage_identity", "0"*64),
                     ("work_face_steps", 1), ("substeps", 1), ("cells", 4)]
        for name, value in mutations:
            with self.subTest(name=name):
                arrays = {key: item.copy() for key, item in bundle["arrays"].items()}
                metadata = copy.deepcopy(bundle["metadata"])
                if name in arrays:
                    arrays[name][0] = value
                else:
                    metadata[name] = value
                target.unlink()
                index = copy.deepcopy(original)
                index["scenarios"]["eastward"]["pages"]["2.5"][1]["checkpoint"] = write_bundle(target, arrays, metadata)
                self._repin(index)
                with self.assertRaises(ValueError):
                    load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")
                target.write_bytes(raw)

    def test_rehashed_native_accounts_and_config_rejected(self):
        original = json.loads((self.root / "index.json").read_text())
        record = original["scenarios"]["eastward"]["pages"]["2.5"][1]["storage"]
        target = Path(record["path"])
        raw = target.read_bytes()
        bundle = load_bundle(target, expected_sha256=record["expected_sha256"], validator=lambda value: None)
        for name in ("rain_mm_h", "rain_volume_m3", "internal_net_m3", "storage_change_m3", "height_m", "receiver", "depth_m", "parameters", "runoff_parameters", "forcing_hour_offset"):
            with self.subTest(name=name):
                arrays = {key: item.copy() for key, item in bundle["arrays"].items()}
                metadata = copy.deepcopy(bundle["metadata"])
                if name in arrays:
                    if name == "receiver":
                        arrays[name].flat[0] = 2
                    else:
                        arrays[name].flat[0] += .1
                elif name == "forcing_hour_offset":
                    metadata[name] = 0
                else:
                    key = "face_conductance_m_s" if name == "parameters" else "potential_et_mm_h"
                    metadata[name][key] += .1
                target.unlink()
                index = copy.deepcopy(original)
                index["scenarios"]["eastward"]["pages"]["2.5"][1]["storage"] = write_bundle(target, arrays, metadata)
                self._repin(index)
                with self.assertRaises(ValueError):
                    load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")
                target.write_bytes(raw)

    def test_partial_coverage_and_false_gate_claim_rejected(self):
        original = json.loads((self.root / "index.json").read_text())
        for kind in ("direction", "hour", "order", "gate", "profile"):
            with self.subTest(kind=kind):
                index = copy.deepcopy(original)
                if kind == "direction":
                    del index["scenarios"]["westward"]
                elif kind == "hour":
                    index["scenarios"]["eastward"]["pages"]["2.5"].pop()
                elif kind == "order":
                    index["scenarios"]["eastward"]["pages"]["2.5"].reverse()
                elif kind == "gate":
                    index["all_numerical_gates_passed"] = False
                else:
                    index["schema"] = "unknown"
                self._repin(index)
                with self.assertRaises(ValueError):
                    load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")

    def test_resource_peaks_and_monitor_rejected(self):
        original = json.loads((self.root / "resource.json").read_text())
        for name, value in (("peak_private_bytes", 1073741825), ("peak_rss_bytes", 0), ("complete", False), ("monitor_error", "failed"), ("sample_count", 0)):
            with self.subTest(name=name):
                resource = dict(original, **{name: value})
                self.args["execution_resource_record"] = write_json(self.root / "resource.json", resource)
                with self.assertRaises(ValueError):
                    load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")

    def test_fresh_cold_process_no_numba_or_generation(self):
        argument_path = self.root / "arguments.json"
        argument_path.write_text(json.dumps(dict(self.args, scope="synthetic_fixture")))
        script = '''import sys,json,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.startswith('numba') or fullname in ('terrain_pipeline.td_basin_storage_compiled','terrain_pipeline.td_basin_storage_compiled_driver'):
   raise RuntimeError('compiled import forbidden')
sys.meta_path.insert(0,Block())
from terrain_pipeline import td_basin_hierarchy,td_native_storm_forcing
def forbidden(*args,**kwargs): raise RuntimeError('generation forbidden')
td_basin_hierarchy.build_basin_hierarchy=forbidden
td_native_storm_forcing.generate_native_storm=forbidden
from terrain_pipeline.td_native_weather_storage_io import load_native_weather_storage_index
args=json.load(open(sys.argv[1]))
assert load_native_weather_storage_index(sys.argv[2],**args)['IO_accepted']
assert 'numba' not in sys.modules
'''
        completed = subprocess.run([sys.executable, "-c", script, str(argument_path), str(self.root / "index.json")], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_unknown_zero_and_invented_compensation_rejected(self):
        self.tearDown()
        self.unknown_fixture = True
        self.setUp()
        self.assertTrue(load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")["IO_accepted"])
        index = json.loads((self.root / "index.json").read_text())
        page = index["scenarios"]["eastward"]["pages"]["2.5"][0]
        record = page["checkpoint"]
        bundle = load_bundle(record["path"], expected_sha256=record["expected_sha256"], validator=lambda value: None)
        bundle["arrays"] = {name: values.copy() for name, values in bundle["arrays"].items()}
        bundle["arrays"]["error_soil"][-1] = -.001
        Path(record["path"]).unlink()
        page["checkpoint"] = write_bundle(Path(record["path"]), bundle["arrays"], bundle["metadata"])
        self._repin(index)
        with self.assertRaisesRegex(ValueError, "unknown compensation"):
            load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")

    def test_signed_transport_accounts_are_legal(self):
        from terrain_pipeline.td_native_weather_storage_io import _validate_page
        index = json.loads((self.root / "index.json").read_text())
        page = index["scenarios"]["eastward"]["pages"]["2.5"][1]
        storage = load_bundle(page["storage"]["path"], expected_sha256=page["storage"]["expected_sha256"], validator=lambda value: None)
        checkpoint = load_bundle(page["checkpoint"]["path"], expected_sha256=page["checkpoint"]["expected_sha256"], validator=lambda value: None)
        storage["arrays"] = {name: values.copy() for name, values in storage["arrays"].items()}
        checkpoint["arrays"] = {name: values.copy() for name, values in checkpoint["arrays"].items()}
        arrays = storage["arrays"]
        first, second = arrays["face_cells"][0]
        volume = .0001
        arrays["face_forward_m3"][0] = volume
        arrays["active_forward_s"][0] = 1.
        arrays["internal_net_m3"][0,first] -= volume
        arrays["internal_net_m3"][0,second] += volume
        arrays["storage_change_m3"] += arrays["internal_net_m3"]
        arrays["depth_m"][1] += arrays["internal_net_m3"][0]/900.
        if arrays["receiver"][first] == second:
            arrays["routed_volume_m3"][first] = volume
            arrays["wet_duration_s"][first] = 1.
        storage["identity_sha256"] = identity(arrays,storage["metadata"])
        checkpoint["arrays"]["depth_m"] = arrays["depth_m"][1].copy()
        checkpoint["metadata"]["last_page_storage_identity"] = storage["identity_sha256"]
        checkpoint["identity_sha256"] = identity(checkpoint["arrays"],checkpoint["metadata"])
        _validate_page(storage,checkpoint,hierarchy=self.hierarchy,rain=self.rains["eastward"][1],forcing_id=page["forcing_identity"],hour=1,step=2.5,config=storage["metadata"]["parameters"],runoff=self.args["expected_runoff"])
        self.assertLess(arrays["internal_net_m3"].min(),0.)

    def test_locally_balanced_but_broken_previous_state_rejected(self):
        index = json.loads((self.root / "index.json").read_text())
        page = index["scenarios"]["eastward"]["pages"]["2.5"][1]
        storage = load_bundle(page["storage"]["path"], expected_sha256=page["storage"]["expected_sha256"], validator=lambda value: None)
        checkpoint = load_bundle(page["checkpoint"]["path"], expected_sha256=page["checkpoint"]["expected_sha256"], validator=lambda value: None)
        storage["arrays"] = {name: values.copy() for name, values in storage["arrays"].items()}
        checkpoint["arrays"] = {name: values.copy() for name, values in checkpoint["arrays"].items()}
        storage["arrays"]["depth_m"][:,0] += .01
        target = Path(page["storage"]["path"])
        target.unlink()
        page["storage"] = write_bundle(target,storage["arrays"],storage["metadata"])
        checkpoint["arrays"]["depth_m"][0] += .01
        checkpoint["metadata"]["last_page_storage_identity"] = page["storage"]["expected_identity"]
        target = Path(page["checkpoint"]["path"])
        target.unlink()
        page["checkpoint"] = write_bundle(target,checkpoint["arrays"],checkpoint["metadata"])
        self._repin(index)
        with self.assertRaisesRegex(ValueError,"previous checkpoint complete inventory"):
            load_native_weather_storage_index(self.root / "index.json", **self.args, scope="synthetic_fixture")

    def test_malicious_header_rejected_before_allocation(self):
        from terrain_pipeline.td_native_weather_storage_io import _bundle
        index = json.loads((self.root / "index.json").read_text())
        record = index["scenarios"]["eastward"]["pages"]["2.5"][0]["storage"]
        target = Path(record["path"])
        with zipfile.ZipFile(target) as archive:
            members = {name:archive.read(name) for name in archive.namelist()}
        header = io.BytesIO()
        np.lib.format.write_array_header_1_0(header,dict(descr="<f8",fortran_order=False,shape=(1000000000,)))
        members["depth_m.npy"] = header.getvalue()+b"12345678"
        with zipfile.ZipFile(target,"w") as archive:
            for name,payload in members.items():
                archive.writestr(name,payload)
        record["expected_sha256"] = file_sha256(target)
        with self.assertRaises(ValueError):
            _bundle(record)


if __name__ == "__main__":
    unittest.main()
