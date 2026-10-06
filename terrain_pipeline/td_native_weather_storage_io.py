"""Pure IO acceptance for v9 native spatial-weather hour pages."""

import json
import math
import re
from pathlib import Path

import numpy as np
import psutil
from dataclasses import asdict

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_source import load_td_source_bundle
from terrain_pipeline.td_native_storm_forcing import load_native_storm
from terrain_pipeline.rainfall_runoff import RunoffParameters, _strict_json
from terrain_pipeline.td_basin_storage_compiled_io import load_storage, load_checkpoint
from terrain_pipeline.td_hour_pages_acceptance_io import _hour, _checkpoint_headers
from terrain_pipeline.td_basin_source import PRIMARY_SHA256, PRIMARY_PATH

SCHEMA = "td-v9-spatial-weather-hour-pages-index-v1"
PROFILE = "v9-compiled-hour-loop-v8-equivalent-v1"
STEPS = (2.5, 1.25)
MAX_BYTES = 1_073_741_824
FLAGS = ("hydraulic_ready", "transient_converged", "morphology_flux_ready", "natural_outlet_verified", "publishable")
PHYSICS = dict(face_conductance_m_s=.6, surface_evaporation_mm_h=.15, wet_threshold_m=1e-9,
               max_substeps=100000, max_work_face_steps=6000000000)
STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
FACE = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s")
CELL_LEDGER = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
               "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
RECEIVER = ("routed_volume_m3", "wet_duration_s")


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("external SHA256 required")
    return value


def _json(record, limit=16 * 1024 * 1024):
    path = Path(record["path"])
    if not path.is_file() or path.stat().st_size > limit or file_sha256(path) != _sha(record["expected_sha256"]):
        raise ValueError("external JSON pin or size rejected")
    return _strict_json(path.read_text(encoding="utf-8"))


def _layout(record, expected):
    path = Path(record["path"]).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)) or path != Path(expected).absolute():
        raise ValueError("canonical artifact layout rejected")


def _flags(record):
    for name in FLAGS:
        if (name in ("hydraulic_ready", "transient_converged") or name in record) and record.get(name) is not False:
            raise ValueError("certification flag must remain false: " + name)


def _bundle(record, checkpoint=False):
    arrays = (load_checkpoint if checkpoint else load_storage)(**record)
    if checkpoint:
        _checkpoint_headers({**{name:(value.shape,value.dtype) for name,value in arrays["arrays"].items()},
                             "manifest":((1,),np.dtype("uint8"))})
    if arrays["identity_sha256"] != _sha(record["expected_identity"]):
        raise ValueError("saved artifact identity mismatch")
    return arrays


def _identity(result):
    if identity(result["arrays"], result["metadata"]) != result["identity_sha256"]:
        raise ValueError("saved artifact content identity mismatch")


def _near(actual, expected, allowed=None):
    actual, expected = float(actual), float(expected)
    tolerance = 1e-6 + 1e-10 * abs(expected) if allowed is None else allowed
    if not math.isfinite(actual) or not math.isfinite(expected) or abs(actual - expected) > tolerance:
        raise ValueError("hour water budget mismatch")


def _validate_page(storage, checkpoint, *, hierarchy, rain, forcing_id, hour, step, config, runoff):
    arrays, metadata = storage["arrays"], storage["metadata"]
    _identity(storage)
    if metadata.get("algorithm") != "D4-threshold-compiled-hour-SSPRK2-v9" or metadata.get("work_profile") != PROFILE:
        raise ValueError("unknown v9 storage profile")
    expected = {"hierarchy_identity_sha256": hierarchy["identity_sha256"], "dt_s": 3600., "substep_s": step,
        "chunk_start_s": hour * 3600., "chunk_end_s": (hour + 1) * 3600., "forcing_identity": forcing_id,
        "forcing_hour_offset": hour, "parameters": config, "runoff_parameters": runoff,
        "spacing_m": hierarchy["metadata"]["spacing_m"], "origin_m_xz": hierarchy["metadata"]["origin_m_xz"]}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("v9 page time/grid/forcing/config mismatch")
    subdivisions = math.ceil(3600. / config["substep_s"])
    if metadata.get("substeps") != subdivisions or metadata.get("substep_s") != 3600. / subdivisions:
        raise ValueError("v9 actual substep count mismatch")
    _flags(metadata)
    checked = {**metadata, "algorithm":"D4-threshold-checkpoint-SSPRK2-v8", "work_profile":"v8-hour-pages-v7-SSPRK2"}
    shared_budget = _hour({"arrays":arrays,"metadata":checked}, hierarchy, hour, step,
                          rain.reshape(-1), forcing_id, 3600., config, runoff)
    topology = hierarchy["arrays"]
    cells = topology["height_m"].size
    if arrays["rain_mm_h"].shape != (1, cells) or not np.array_equal(arrays["rain_mm_h"][0], rain.reshape(-1)):
        raise ValueError("native spatial hour slice mismatch")
    for name in STATES:
        if (arrays[name].shape != (2, cells) or arrays[name].dtype != np.float64 or
                np.any(arrays[name] < 0) or np.any(arrays[name][:, ~topology["valid_mask"].ravel()] != 0)):
            raise ValueError("four-state native shape/unknown inventory mismatch")
    nonnegative = (*FACE, "rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3",
                   "surface_et_m3", "boundary_outflow_m3", "local_release_m3", *RECEIVER)
    for name in (*CELL_LEDGER, *FACE, *RECEIVER):
        if name not in arrays or not np.isfinite(arrays[name]).all() or (name in nonnegative and np.any(arrays[name] < 0)):
            raise ValueError("missing/negative/nonfinite saved account")
    for name in CELL_LEDGER + RECEIVER:
        if np.any(arrays[name][..., ~topology["valid_mask"].ravel()] != 0):
            raise ValueError("unknown cell account must be zero")
    if np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > 3600. + 1e-8):
        raise ValueError("directional activity exceeds hour")
    area = hierarchy["metadata"]["spacing_m"] ** 2
    stores = arrays["depth_m"] + sum(arrays[name] for name in ("soil_mm", "fast_mm", "slow_mm")) / 1000.
    change = math.fsum(((stores[1] - stores[0]) * area).tolist())
    rain_volume = math.fsum((rain.ravel() * area / 1000.).tolist())
    loss = math.fsum((arrays["soil_et_m3"][0] + arrays["surface_et_m3"][0]).tolist())
    external = math.fsum(arrays["boundary_outflow_m3"][0].tolist())
    _near(float(np.sum(arrays["storage_change_m3"], dtype=np.float64)), change)
    _near(rain_volume, loss + external + change, 1e-6 + abs(loss + external + change) * 1e-10)
    _near(float(np.sum(arrays["balance_residual_m3"], dtype=np.float64)), rain_volume - loss - external - change)
    cp_arrays, cp_metadata = checkpoint["arrays"], checkpoint["metadata"]
    _identity(checkpoint)
    if cp_metadata.get("execution_profile") != PROFILE or cp_metadata.get("last_page_storage_identity") != storage["identity_sha256"]:
        raise ValueError("checkpoint page identity/profile mismatch")
    if cp_metadata.get("elapsed_s") != (hour + 1) * 3600. or cp_metadata.get("substep_s") != step:
        raise ValueError("checkpoint time mismatch")
    expected_cp = dict(schema="td-storage-continuation-v1", hierarchy_identity_sha256=hierarchy["identity_sha256"],
        parameters=config,runoff_parameters=runoff,forcing_identity=forcing_id,dt_s=3600.,
        cells=cells,faces=len(topology["face_cells"]),substeps=(hour+1)*subdivisions,
        work_face_steps=(hour+1)*subdivisions*len(topology["face_cells"]))
    if any(cp_metadata.get(name)!=value for name,value in expected_cp.items()) or any(type(cp_metadata[name]) is not int for name in ("cells","faces","substeps","work_face_steps")):
        raise ValueError("checkpoint forcing/config/count/work mismatch")
    for name in ("error_depth","error_soil","error_fast","error_slow"):
        if np.any(cp_arrays[name][~topology["valid_mask"].ravel()]!=0):
            raise ValueError("unknown compensation inventory")
    _flags(cp_metadata)
    for name in STATES:
        if not np.array_equal(cp_arrays[name], arrays[name][-1]):
            raise ValueError("checkpoint state endpoint mismatch")
    for name in FACE + RECEIVER:
        cumulative = cp_arrays["cumulative_" + name]
        if not np.isfinite(cumulative).all() or np.any(cumulative < 0):
            raise ValueError("checkpoint cumulative inventory invalid")
    return dict(shared_budget, rain_m3=rain_volume, loss_m3=loss, external_m3=external, change_m3=change,
                residual_m3=rain_volume-(loss+external+change),allowed_m3=1e-6+abs(loss+external+change)*1e-10)


def load_native_weather_storage_index(path, *, expected_sha256, weather_index_record, hierarchy_record,
                                      source_record, run_inputs_record, execution_resource_record,
                                      declared_steps_s=STEPS, scope="original_td", expected_parameters=None,
                                      expected_runoff=None, code_root=None):
    path = Path(path).absolute()
    if path.name != "index.json":
        raise ValueError("complete final index.json required")
    index = _json({"path": str(path), "expected_sha256": expected_sha256})
    if index.get("schema") != SCHEMA or index.get("steps_s") != list(STEPS) or tuple(declared_steps_s) != STEPS:
        raise ValueError("v9 spatial acceptance schema/step pair rejected")
    _flags(index)
    if index.get("publishable") is not False:
        raise ValueError("final publishable flag must be false")
    root = path.parent
    inputs = _json(run_inputs_record)
    _layout(run_inputs_record, root / "run-inputs.json")
    if inputs.get("schema") != "td-v9-spatial-weather-run-inputs-v1" or inputs.get("profile") != PROFILE or inputs.get("steps_s") != [2.5, 1.25]:
        raise ValueError("v9 run input profile rejected")
    resource = _json(execution_resource_record)
    if (resource.get("schema")!="td-v9-spatial-weather-execution-resource-v1" or resource.get("scope")!="complete eastward+westward both steps execution" or
            resource.get("index_sha256") != expected_sha256 or resource.get("complete") is not True or
            type(resource.get("sample_count")) is not int or resource["sample_count"]<1 or resource.get("sampling_interval_s")!=2 or resource.get("monitor_error") is not None or
            resource.get("thread_environment")!={name:"1" for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS")}):
        raise ValueError("v9 external complete resource record rejected")
    for name in ("peak_rss_bytes", "peak_private_bytes"):
        if type(resource.get(name)) is not int or not 0 < resource[name] <= MAX_BYTES:
            raise ValueError("v9 resource peak missing/exceeded")
    hierarchy = load_basin_hierarchy(**hierarchy_record)
    source = load_td_source_bundle(**source_record)
    if hierarchy["metadata"]["source_identity_sha256"] != source_record["expected_identity"]:
        raise ValueError("v9 source/hierarchy identity mismatch")
    if source["identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]:
        raise ValueError("v9 source content/hierarchy identity mismatch")
    if hierarchy["metadata"]["source_metadata"] != source["metadata"]:
        raise ValueError("source hierarchy grid metadata mismatch")
    for name in ("height_m","valid_mask","protected_mask","open_boundary_mask"):
        if not np.array_equal(source["arrays"][name],hierarchy["arrays"][name]):
            raise ValueError("source hierarchy actual geometry mismatch")
    if source["arrays"]["protected_mask"].any():
        raise ValueError("fresh v9 protected domain rejected")
    if scope=="original_td":
        code_root = Path(__file__).resolve().parents[1] if code_root is None else code_root
        parameters,runoff=PHYSICS,asdict(RunoffParameters())
        if expected_parameters not in (None,PHYSICS) or expected_runoff not in (None,runoff) or source["metadata"]["source_sha256"]!=PRIMARY_SHA256 or weather_index_record["expected_sha256"]!="333046a82778411b95bcb691988a7b016347de1ad288ad2d841cc6a089bb1271":
            raise ValueError("original physics/source/weather predeclaration mismatch")
        if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
            raise ValueError("original primary source external pin mismatch")
    elif scope=="synthetic_fixture" and source["arrays"]["height_m"].size<=4096 and expected_parameters is not None and expected_runoff is not None:
        parameters,runoff=dict(expected_parameters),dict(expected_runoff)
        RunoffParameters(**runoff)
    else:
        raise ValueError("explicit scope and physics required")
    if set(parameters) != set(PHYSICS) or any(not math.isfinite(float(value)) or value < 0 for value in parameters.values()):
        raise ValueError("complete predeclared physics required excluding substep_s")
    weather = _json(weather_index_record, 8 * 1024 * 1024)
    if weather.get("schema") != "td-native-storm-forcing-index-v1" or set(weather.get("cases", {})) != {"eastward", "westward"}:
        raise ValueError("complete two-direction weather index required")
    weather_pin=dict(path=weather_index_record["path"],sha256=weather_index_record["expected_sha256"])
    if weather.get("source")!=source_record or inputs.get("weather_index")!=weather_pin or index.get("weather_index")!=weather_pin or inputs.get("hierarchy")!=dict(path=hierarchy_record["path"],sha256=hierarchy_record["expected_sha256"],identity=hierarchy_record["expected_identity"]):
        raise ValueError("weather/source/hierarchy external pins mismatch")
    if inputs.get("depth_gate_m")!=.001 or inputs.get("receiver_gate")!=.01:
        raise ValueError("refinement gates changed")
    faces=len(hierarchy["arrays"]["face_cells"])
    budgets={str(step):dict(chunk_face_steps=round(3600/step)*faces,global_face_steps_per_scenario=24*round(3600/step)*faces) for step in STEPS}
    if inputs.get("budgets")!=budgets or index.get("budgets")!=budgets or inputs.get("chunk_max_work_face_steps")!=6000000000 or inputs.get("job_max_bytes")!=MAX_BYTES:
        raise ValueError("work budgets mismatch")
    codes=index.get("code_sha256")
    if not codes or codes!=inputs.get("code_sha256"):
        raise ValueError("frozen code identity mismatch")
    def check_codes():
        if code_root is not None:
            base=Path(code_root).resolve()
            for name,digest in codes.items():
                target=(base/name).resolve()
                if not target.is_relative_to(base) or file_sha256(target)!=_sha(digest):
                    raise ValueError("frozen code changed")
    check_codes()
    cases = {}
    for direction, case in weather["cases"].items():
        saved = load_native_storm(**case["record"], source_record=weather["source"], expected_plan=case["plan"])
        rain = saved["arrays"]["rain_mm_h"]
        if rain.shape != (24, *hierarchy["arrays"]["height_m"].shape):
            raise ValueError("native weather full spatial shape mismatch")
        plan=saved["metadata"]["plan"]
        if plan["spacing_m"]!=source["metadata"]["spacing_m"] or plan["origin_m_xz"]!=source["metadata"]["origin_m_xz"] or plan["dt_s"]!=3600. or plan["start_s"]!=0. or plan["window"]!=[0,rain.shape[1],0,rain.shape[2]]:
            raise ValueError("native weather geometry/time mismatch")
        forcing_id = identity({"rain_mm_h": rain}, {"dt_s": 3600.})
        if forcing_id != case["forcing_identity"] or inputs["weather_records"][direction]!=case["record"] or inputs["forcing_identities"][direction]!=forcing_id:
            raise ValueError("native weather forcing identity mismatch")
        cases[direction] = (rain, forcing_id)
    scenarios = index.get("scenarios")
    if set(scenarios or {}) != set(cases):
        raise ValueError("v9 direction coverage mismatch")
    summaries = {}
    for direction, (rain, forcing_id) in cases.items():
        comparison = scenarios[direction]
        _flags(comparison)
        if comparison.get("publishable") is not False:
            raise ValueError("comparison publishable flag must be false")
        if comparison.get("weather_record")!=weather["cases"][direction]["record"] or comparison.get("forcing_identity")!=forcing_id or comparison.get("steps_s")!=list(STEPS):
            raise ValueError("comparison weather identity mismatch")
        groups = comparison.get("pages", {})
        if set(groups) != {"2.5", "1.25"}:
            raise ValueError("v9 step coverage mismatch")
        summaries[direction] = {}
        final_routed={}
        for step in STEPS:
            pages = groups[str(step)]
            if len(pages) != 24 or [page.get("hour") for page in pages] != list(range(24)):
                raise ValueError("v9 complete ordered hour coverage required")
            previous = None
            totals = []
            group=root/f"{direction}-{step:g}s"
            if {entry.name for entry in group.iterdir() if entry.is_dir()}!={f"hour-{hour:02d}" for hour in range(24)}:
                raise ValueError("hour directory coverage mismatch")
            for hour, page in enumerate(pages):
                directory = root / f"{direction}-{step:g}s" / f"hour-{hour:02d}"
                _layout(page["storage"], directory / "storage.npz")
                _layout(page["checkpoint"], directory / "checkpoint.npz")
                if type(page["hour"]) is not int or page.get("forcing_identity")!=forcing_id or page.get("chunk_work_face_steps")!=budgets[str(step)]["chunk_face_steps"] or type(page.get("peak_bytes")) is not int or not 0<page["peak_bytes"]<=resource["peak_rss_bytes"]:
                    raise ValueError("page work/resource declaration mismatch")
                storage = _bundle(page["storage"]); checkpoint = _bundle(page["checkpoint"], True)
                record = _validate_page(storage, checkpoint, hierarchy=hierarchy, rain=rain[hour], forcing_id=forcing_id,
                    hour=hour, step=step, config=dict(parameters,substep_s=step), runoff=runoff)
                totals.append(record)
                for name in STATES:
                    initial=0. if name=="depth_m" else runoff["initial_"+name]
                    expected_initial=np.where(hierarchy["arrays"]["valid_mask"].ravel(),initial,0.) if previous is None else previous[name]
                    if not np.array_equal(storage["arrays"][name][0],expected_initial):
                        raise ValueError("previous checkpoint complete inventory chain mismatch")
                for name in FACE+RECEIVER:
                    expected_sum=storage["arrays"][name] if previous is None else previous["cumulative_"+name]+storage["arrays"][name]
                    if not np.array_equal(checkpoint["arrays"]["cumulative_"+name],expected_sum):
                        raise ValueError("checkpoint exact cumulative chain mismatch")
                previous = checkpoint["arrays"]
                del storage,checkpoint
            summaries[direction][str(step)] = {"hours": 24, "total_rain_m3": math.fsum(item["rain_m3"] for item in totals)}
            rain_total=math.fsum(item["rain_m3"] for item in totals)
            residual=math.fsum([totals[0]["initial_water_m3"],rain_total,-math.fsum(item["loss_m3"] for item in totals),-math.fsum(item["external_m3"] for item in totals),-totals[-1]["final_water_m3"]])
            _near(residual,0.,1e-6+rain_total*1e-10)
            summaries[direction][str(step)].update(interval_budgets=totals,cumulative_residual_m3=residual)
            final_routed[step]=previous["cumulative_routed_volume_m3"].copy()
        relative=float(abs(final_routed[2.5]-final_routed[1.25]).sum()/max(1e-12,final_routed[1.25].sum()))
        maximum=0.
        for coarse,fine in zip(groups["2.5"],groups["1.25"]):
            first,second=_bundle(coarse["storage"]),_bundle(fine["storage"])
            maximum=max(maximum,float(abs(first["arrays"]["depth_m"]-second["arrays"]["depth_m"]).max(initial=0)))
            del first,second
        gate=maximum<=.001 and relative<=.01
        if comparison.get("gate_passed") is not gate or comparison.get("max_saved_depth_difference_m")!=maximum or comparison.get("cumulative_receiver_relative_l1")!=relative:
            raise ValueError("actual refinement comparison mismatch")
        summaries[direction]["numerical_gate_passed"]=gate
        summaries[direction].update(max_saved_depth_difference_m=maximum, cumulative_receiver_relative_l1=relative)
    if index.get("all_numerical_gates_passed") is not all(value["numerical_gate_passed"] for value in summaries.values()):
        raise ValueError("overall refinement flag mismatch")
    records=[weather_index_record,hierarchy_record,source_record,run_inputs_record,execution_resource_record]
    for case in weather["cases"].values():
        records.append(case["record"])
    for comparison in scenarios.values():
        for pages in comparison["pages"].values():
            for page in pages:
                records.extend((page["storage"],page["checkpoint"]))
    for record in records:
        if file_sha256(record["path"])!=record["expected_sha256"]:
            raise ValueError("external pin changed during cold read")
    check_codes()
    if scope == "original_td" and file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
        raise ValueError("original primary source changed during cold read")
    info=psutil.Process().memory_info()
    peak_rss=int(getattr(info,"peak_wset",info.rss)); peak_private=getattr(info,"peak_pagefile",None)
    if type(peak_private) is not int or max(peak_rss,peak_private)>MAX_BYTES:
        raise MemoryError("loader peak resource over1GiB or missing")
    if file_sha256(path) != expected_sha256:
        raise ValueError("v9 final index changed during cold read")
    return dict(schema="td-v9-spatial-weather-hour-pages-acceptance-v1", index_sha256=expected_sha256,
        cases=summaries, weather_index=weather_index_record, io_chain_accepted=True, IO_accepted=True,
        numerical_gate_passed=all(value["numerical_gate_passed"] for value in summaries.values()),
        resource=dict(peak_rss_bytes=peak_rss,peak_private_bytes=peak_private),
        solver_advanced=False, hydraulic_ready=False, transient_converged=False, publishable=False)
