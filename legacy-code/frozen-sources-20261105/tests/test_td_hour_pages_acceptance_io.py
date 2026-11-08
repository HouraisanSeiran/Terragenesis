from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
import io
import copy

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, save_bundle
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy
from terrain_pipeline.td_hour_pages_acceptance_io import load_hour_pages_index, PROFILE, TIME_SEMANTICS, STATES, FLUXES


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    return {"path": str(path), "expected_sha256": file_sha256(path)}


def write_bundle(path, arrays, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    save_bundle(path, result, validator=lambda value: None)
    return {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": result["identity_sha256"]}


def fixture(root, rain_rate=0.):
    root = Path(root).resolve()
    hierarchy = build_basin_hierarchy(make_td_source(np.array([[0., 2., 0.]]), spacing_m=30))
    hierarchy_path = root / "hierarchy.npz"
    save_basin_hierarchy(hierarchy_path, hierarchy)
    hierarchy_record = {"path": str(hierarchy_path), "expected_sha256": file_sha256(hierarchy_path), "expected_identity": hierarchy["identity_sha256"]}
    topology = hierarchy["arrays"]
    faces = len(topology["face_cells"])
    budgets = {str(step): {"chunk_face_steps": int(3600 / step) * faces, "global_face_steps_per_scenario": 24 * int(3600 / step) * faces} for step in (2.5, 1.25)}
    flags = dict(hydraulic_ready=False, transient_converged=False, publishable=False)
    index = dict(schema="td-storage-hour-pages-index-v1", scenarios={}, budgets=budgets, code_sha256={"fixture": "a" * 64}, all_numerical_gates_passed=True, **flags)
    forcing_records = {}
    for scenario in ("ordinary", "strong"):
        forcing_id = identity({"rain_mm_h": np.full(24, rain_rate)}, {"dt_s": 3600.})
        forcing_records[scenario] = write_json(root / (scenario + "-forcing.json"), dict(rain_mm_h=[rain_rate] * 24, dt_s=3600., identity=forcing_id))
        forcing_records[scenario]["expected_identity"] = forcing_id
        groups = {}
        for step in (2.5, 1.25):
            pages = []
            for hour in range(24):
                arrays = {name: topology[name].copy() for name in ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells")}
                arrays.update({name: np.zeros((2, 3)) for name in STATES})
                ledger = ("rain_mm_h", "rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3", "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
                arrays.update({name: np.zeros((1, 3)) for name in ledger})
                arrays.update({name: np.zeros(3 if name in ("routed_volume_m3", "wet_duration_s") else faces) for name in FLUXES})
                arrays.update(boundary_width_m=np.zeros(0), wet_pool_count=np.zeros(2, np.int64))
                arrays["depth_m"][0] = hour * rain_rate / 1000
                arrays["depth_m"][1] = (hour + 1) * rain_rate / 1000
                arrays["rain_mm_h"][:] = rain_rate
                for name in ("rain_volume_m3", "land_rain_m3", "storage_change_m3"):
                    arrays[name][:] = rain_rate * .9
                config = dict(substep_s=step, face_conductance_m_s=.6, surface_evaporation_mm_h=0., wet_threshold_m=1e-9, max_substeps=20000, max_work_face_steps=6000000000)
                runoff = asdict(RunoffParameters(initial_soil_mm=0))
                metadata = dict(schema="td-basin-storage-v1", algorithm="D4-threshold-checkpoint-SSPRK2-v8", work_profile=PROFILE,
                    hierarchy_identity_sha256=hierarchy["identity_sha256"], spacing_m=30., origin_m_xz=[0, 0], dt_s=3600., substep_s=step,
                    substeps=int(3600 / step), parameters=config, runoff_parameters=runoff, chunk_start_s=hour * 3600., chunk_end_s=(hour + 1) * 3600.,
                    forcing_identity=forcing_id, forcing_hour_offset=hour, saved_time_semantics=TIME_SEMANTICS, positivity_cfl=2 * .6 * step / 30,
                    forcing_semantics="runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
                    activity_semantics="RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity",
                    compensation_semantics="soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation", **flags)
                directory = root / f"{scenario}-{step:g}s" / f"hour-{hour:02d}"
                storage_record = write_bundle(directory / "storage.npz", arrays, metadata)
                saved = {name: np.zeros(3) for name in STATES + ("error_depth", "error_soil", "error_fast", "error_slow")}
                saved["depth_m"] = arrays["depth_m"][-1].copy()
                saved.update({"cumulative_" + name: arrays[name].copy() for name in FLUXES})
                cp_metadata = dict(schema="td-storage-continuation-v1", execution_profile=PROFILE, hierarchy_identity_sha256=hierarchy["identity_sha256"],
                    parameters=config, runoff_parameters=runoff, forcing_identity=forcing_id, dt_s=3600., substep_s=step, elapsed_s=(hour + 1) * 3600.,
                    substeps=(hour + 1) * int(3600 / step), work_face_steps=(hour + 1) * int(3600 / step) * faces,
                    cells=3, faces=faces, last_page_storage_identity=storage_record["expected_identity"], **flags)
                checkpoint_record = write_bundle(directory / "checkpoint.npz", saved, cp_metadata)
                pages.append(dict(hour=hour, storage=storage_record, checkpoint=checkpoint_record, forcing_identity=forcing_id,
                    chunk_work_face_steps=budgets[str(step)]["chunk_face_steps"], peak_bytes=1))
            groups[str(step)] = pages
        index["scenarios"][scenario] = dict(pages=groups, max_saved_depth_difference_m=0., cumulative_receiver_relative_l1=0., gate_passed=True, **flags)
    run_inputs = dict(profile=PROFILE, steps_s=[2.5, 1.25], depth_gate_m=.001, receiver_gate=.01,
        hierarchy=dict(path=hierarchy_record["path"], sha256=hierarchy_record["expected_sha256"], identity=hierarchy_record["expected_identity"]),
        budgets=budgets, chunk_max_work_face_steps=6000000000, job_max_bytes=1073741824, code_sha256=index["code_sha256"])
    inputs_record = write_json(root / "run-inputs.json", run_inputs)
    write_json(root / "index.json", index)
    resource_record = write_json(root / "resource.json", dict(index_sha256=file_sha256(root / "index.json"), scope="complete ordinary+strong both steps execution", complete=True, peak_rss_bytes=1, peak_private_bytes=1))
    return index, dict(expected_sha256=file_sha256(root / "index.json"), forcing_records=forcing_records, run_inputs_record=inputs_record, hierarchy_record=hierarchy_record, execution_resource_record=resource_record)


class HourPagesAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.index, self.arguments = fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        return load_hour_pages_index(self.root / "index.json", **self.arguments)

    def reindex(self):
        self.arguments["expected_sha256"] = write_json(self.root / "index.json", self.index)["expected_sha256"]
        value = json.loads((self.root / "resource.json").read_text())
        value["index_sha256"] = self.arguments["expected_sha256"]
        self.arguments["execution_resource_record"] = write_json(self.root / "resource.json", value)

    def mutate_bundle(self, role, mutate, hour=0, step="2.5", scenario="ordinary"):
        from terrain_pipeline.mountain_source_adapter import load_bundle
        page = self.index["scenarios"][scenario]["pages"][step][hour]
        result = load_bundle(page[role]["path"], expected_sha256=page[role]["expected_sha256"], validator=lambda value: None)
        original = {"arrays": {name: values.copy() for name, values in result["arrays"].items()}, "metadata": copy.deepcopy(dict(result["metadata"]))}
        arrays = {name: values.copy() for name, values in result["arrays"].items()}
        metadata = copy.deepcopy(dict(result["metadata"]))
        mutate(arrays, metadata)
        Path(page[role]["path"]).unlink()
        page[role] = write_bundle(Path(page[role]["path"]), arrays, metadata)
        self.reindex()
        return original

    def restore_bundle(self, role, original, hour=0):
        page = self.index["scenarios"]["ordinary"]["pages"]["2.5"][hour]
        Path(page[role]["path"]).unlink()
        page[role] = write_bundle(Path(page[role]["path"]), original["arrays"], original["metadata"])
        self.reindex()

    def test_complete_cold_read_and_no_solver_import(self):
        accepted = self.load()
        self.assertTrue(accepted["io_chain_accepted"])
        self.assertFalse(accepted["hydraulic_ready"])
        code = """import sys,importlib.abc,json
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname=='numba' or fullname.startswith('numba.') or fullname.startswith('terrain_pipeline.td_basin_storage_continuation') or fullname in {'terrain_pipeline.td_basin_storage','terrain_pipeline.td_basin_transport_v6','terrain_pipeline.td_basin_storage_v4'}: raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from terrain_pipeline.td_hour_pages_acceptance_io import load_hour_pages_index
result=load_hour_pages_index(sys.argv[1],**json.loads(sys.argv[2]))
assert result['io_chain_accepted'] and 'numba' not in sys.modules
"""
        completed = subprocess.run([sys.executable, "-c", code, str(self.root / "index.json"), json.dumps(self.arguments)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_missing_final_and_partial_rejected(self):
        (self.root / "index.json").unlink()
        with self.assertRaises(ValueError):
            self.load()
        del self.index["scenarios"]["ordinary"]
        self.reindex()
        with self.assertRaises(ValueError):
            self.load()

    def test_external_index_and_forcing_pin(self):
        self.arguments["expected_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.load()
        self.reindex()
        forcing = self.arguments["forcing_records"]["ordinary"]
        value = json.loads(Path(forcing["path"]).read_text())
        value["rain_mm_h"][2] = 1.
        value["identity"] = identity({"rain_mm_h": np.array(value["rain_mm_h"])}, {"dt_s": 3600.})
        forcing.update(write_json(Path(forcing["path"]), value))
        with self.assertRaises(ValueError):
            self.load()

    def test_rehashed_time_version_and_substeps(self):
        for key, value in (("chunk_start_s", 1.), ("forcing_hour_offset", 1), ("substeps", 1), ("algorithm", "unknown")):
            original = self.mutate_bundle("storage", lambda arrays, metadata: metadata.update({key: value}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load()
            self.restore_bundle("storage", original)

    def test_coverage_order_and_layout(self):
        pages = self.index["scenarios"]["ordinary"]["pages"]["2.5"]
        pages.reverse()
        self.reindex()
        with self.assertRaises(ValueError):
            self.load()
        pages.reverse()
        pages[0]["storage"]["path"] = str(self.root / "ordinary-2.5s" / "hour-00" / ".." / "hour-00" / "storage.npz")
        self.reindex()
        with self.assertRaises(ValueError):
            self.load()

    def test_checkpoint_endpoint_lastpage_and_cumulative_tamper(self):
        for name in ("depth_m", "cumulative_face_forward_m3", "cumulative_active_forward_s"):
            original = self.mutate_bundle("checkpoint", lambda arrays, metadata: arrays[name].__setitem__(0, 1.))
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.load()
            self.restore_bundle("checkpoint", original)
        self.mutate_bundle("checkpoint", lambda arrays, metadata: metadata.update(last_page_storage_identity="0" * 64))
        with self.assertRaises(ValueError):
            self.load()

    def test_prior_inventory_negative_and_budget_tamper(self):
        original = self.mutate_bundle("storage", lambda arrays, metadata: arrays["soil_mm"].__setitem__((0, 0), 1.), hour=1)
        with self.assertRaises(ValueError):
            self.load()
        self.restore_bundle("storage", original, hour=1)
        self.mutate_bundle("checkpoint", lambda arrays, metadata: arrays["slow_mm"].__setitem__(0, -1.))
        with self.assertRaises(ValueError):
            self.load()

    def test_resource_private_over_budget_refused(self):
        value = json.loads((self.root / "resource.json").read_text())
        value["peak_private_bytes"] = 1073741825
        self.arguments["execution_resource_record"] = write_json(self.root / "resource.json", value)
        with self.assertRaisesRegex(ValueError, "private"):
            self.load()

    def test_rehashed_small_member_huge_npy_header(self):
        record = self.index["scenarios"]["ordinary"]["pages"]["2.5"][0]["storage"]
        target = Path(record["path"])
        with zipfile.ZipFile(target) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        stream = io.BytesIO()
        np.lib.format.write_array_header_1_0(stream, dict(descr="<f8", fortran_order=False, shape=(2, 2000000000)))
        members["depth_m.npy"] = stream.getvalue()
        with zipfile.ZipFile(target, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
        record["expected_sha256"] = file_sha256(target)
        self.reindex()
        with self.assertRaises(ValueError):
            self.load()

    def test_hour_global_gate_not_percell_tolerance(self):
        original = self.mutate_bundle("storage", lambda arrays, metadata: arrays["surface_et_m3"].__setitem__(0, [6e-7, 6e-7, 6e-7]))
        with self.assertRaisesRegex(ValueError, "budget"):
            self.load()
        self.restore_bundle("storage", original)
        self.assertTrue(self.load()["io_chain_accepted"])

    def test_missing_and_extra_hour_directory(self):
        extra = self.root / "ordinary-2.5s" / "hour-24"
        extra.mkdir()
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.load()
        extra.rmdir()
        target = self.root / "ordinary-2.5s" / "hour-23" / "checkpoint.npz"
        target.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.load()

    def test_refinement_and_scenario_shared_physical_configuration(self):
        for scenario, step, section, key, value in (
            ("ordinary", "1.25", "parameters", "face_conductance_m_s", .5),
            ("ordinary", "1.25", "runoff_parameters", "potential_et_mm_h", .2),
            ("strong", "2.5", "parameters", "surface_evaporation_mm_h", .1),
            ("strong", "2.5", "runoff_parameters", "infiltration_capacity_mm_h", 20.)):
            original = self.mutate_bundle("storage", lambda arrays, metadata: metadata[section].update({key: value}), scenario=scenario, step=step)
            with self.subTest(scenario=scenario, step=step, key=key), self.assertRaisesRegex(ValueError, "physical parameters or runoff"):
                self.load()
            page = self.index["scenarios"][scenario]["pages"][step][0]
            Path(page["storage"]["path"]).unlink()
            page["storage"] = write_bundle(Path(page["storage"]["path"]), original["arrays"], original["metadata"])
            self.reindex()

    def test_schedule_and_global_declared_work_tamper(self):
        self.arguments["declared_steps_s"] = (5., 2.5)
        with self.assertRaises(ValueError):
            self.load()
        del self.arguments["declared_steps_s"]
        self.index["budgets"]["2.5"]["global_face_steps_per_scenario"] = 1
        self.reindex()
        with self.assertRaises(ValueError):
            self.load()


if __name__ == "__main__":
    unittest.main()
