"""Read pinned native single-domain surface evidence without executing hydrology."""

from dataclasses import asdict
import math
from pathlib import Path

import numpy as np
import psutil

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import load_td_source_bundle as load_td_source_bundle
from terrain_pipeline.basin_storage import STORAGEV10_PROFILE as PROFILE
from terrain_pipeline.basin_storage import STATES as STATES
from terrain_pipeline.basin_storage import ERRORS as ERRORS
from terrain_pipeline.basin_storage import FLUX as FLUX
from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage
from terrain_pipeline.basin_storage import storagev10_load_checkpoint as load_checkpoint
from terrain_pipeline.climate_forcing import load_native_storm
from terrain_pipeline.td_native_weather_storage_io import _json, _layout
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS, PHYSICS_SEMANTICS, validate_native_v10_accounts

ACCEPTANCE_SHA256 = "c7da55e59be8d9d91fc81c45f17a0c6421848b06fafe215fc268608b1b00a24f"
MAX_BYTES = 1073741824
BUDGETS = dict(max_memory_bytes=MAX_BYTES, max_output_bytes=2*MAX_BYTES,
               max_wall_s=1800, max_artifact_bytes=268435456)
REQUIRED_CODE_FILES = {
    "terrain_pipeline/single_domain_surface_archive.py",
    "terrain_pipeline/single_domain_surface_geometry.py",
    "tools/prepare_single_domain_surface.py",
}
LIMITATIONS = [
    "Native 30 m saved same-bed surface review; no fine-bed spatial convergence.",
    "Engineering exterior exports are not verified natural outlets.",
    "Saved temporal acceptance is separate from full 3D hydraulic certification.",
    "Fast and slow release components are inferred from endpoint changes; only their combined release has a saved ledger.",
    "Compensation is opaque finite signed checkpoint state; no page-start compensation witness is saved.",
]


def _flags(value):
    for flag in ("hydraulic_ready", "publishable"):
        if value.get(flag) is not False:
            raise ValueError("unsupported surface certification: " + flag)
    for flag in ("natural_outlet_verified", "transient_converged", "full_3d_verified", "fine_bed_converged"):
        if flag in value and value[flag] is not False:
            raise ValueError("unsupported surface certification: " + flag)


def _memory():
    info = psutil.Process().memory_info()
    rss = int(getattr(info, "peak_wset", info.rss))
    private = getattr(info, "peak_pagefile", getattr(info, "private", None))
    if max(rss, private or 0) > MAX_BYTES:
        raise MemoryError("single-domain loader exceeds 1 GiB")
    return dict(peak_rss_bytes=rss, peak_private_bytes=private, max_bytes=MAX_BYTES)


def load_accepted_single_domain_chain(acceptance_record, direction="eastward"):
    """Resolve only the fixed accepted native chain and its explicit source pins."""
    if acceptance_record.get("expected_sha256") != ACCEPTANCE_SHA256 or direction not in ("eastward", "westward"):
        raise ValueError("fixed native temporal acceptance and direction required")
    accepted = _json(acceptance_record)
    _flags(accepted)
    if (accepted.get("schema") != "td-independent-final-temporal-refinement-v1"
            or accepted.get("io_chain_accepted") is not True
            or accepted.get("all_saved_numerical_gates_passed") is not True
            or accepted.get("solver_advanced") is not False):
        raise ValueError("complete accepted temporal evidence required")
    records = accepted["run_records"]
    execution, inputs, resource = (_json(records[name]) for name in ("index", "inputs", "resource"))
    root = Path(records["index"]["path"]).parent
    _layout(records["inputs"], root / "run-inputs.json")
    _layout(records["resource"], root / "resource.json")
    if (execution.get("schema") != "td-v10-temporal-refinement-index-v1"
            or inputs.get("schema") != "td-v10-temporal-refinement-plan-v1"
            or execution.get("new_step_s") != .625 or inputs.get("new_step_s") != .625
            or execution.get("reference_step_s") != 1.25
            or execution.get("source_records") != accepted.get("source_records")
            or inputs.get("source_records") != accepted.get("source_records")
            or execution.get("baseline_records") != accepted.get("baseline_records")
            or execution.get("run_inputs_record") != records["inputs"]
            or execution.get("code_sha256") != inputs.get("baseline_code_sha256")
            or set(execution.get("scenarios", {})) != {"eastward", "westward"}):
        raise ValueError("accepted execution/source binding mismatch")
    _flags(execution)
    _flags(inputs)
    if (resource.get("schema") != "td-v10-temporal-refinement-resource-v1"
            or resource.get("index_sha256") != records["index"]["expected_sha256"]
            or resource.get("complete") is not True or resource.get("within_1GiB") is not True
            or resource.get("scope") != "complete new eastward+westward 0.625s 48 pages only"
            or resource.get("monitor_error") is not None
            or resource.get("code_sha256") != execution.get("code_sha256")
            or any(type(resource.get(key)) is not int or not 0 < resource[key] <= MAX_BYTES
                   for key in ("peak_rss_bytes", "peak_private_bytes", "sample_count"))):
        raise ValueError("accepted execution resource mismatch")
    code_root = Path(__file__).resolve().parents[1]
    for name, digest in execution["code_sha256"].items():
        target = (code_root / name).resolve(strict=True)
        if not target.is_relative_to(code_root) or file_sha256(target) != digest:
            raise ValueError("frozen accepted dependency changed")
    source_records = accepted["source_records"]
    hierarchy = load_basin_hierarchy(**source_records["hierarchy"])
    weather_record = dict(path=source_records["weather_index"]["path"],
                          expected_sha256=source_records["weather_index"]["sha256"])
    weather_index = _json(weather_record)
    if weather_index.get("schema") != "td-native-storm-forcing-index-v1":
        raise ValueError("native weather index schema mismatch")
    source = load_td_source_bundle(**weather_index["source"])
    if (hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"]
            or hierarchy["metadata"]["source_metadata"] != source["metadata"]):
        raise ValueError("native hierarchy source identity mismatch")
    for name in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask"):
        if not np.array_equal(hierarchy["arrays"][name], source["arrays"][name]):
            raise ValueError("native source same-bed mismatch")
    case = weather_index["cases"][direction]
    if case["record"] != source_records["weather_records"][direction]:
        raise ValueError("accepted weather pin mismatch")
    weather = load_native_storm(**case["record"], source_record=weather_index["source"], expected_plan=case["plan"])
    rain = weather["arrays"]["rain_mm_h"]
    forcing = identity({"rain_mm_h": rain}, {"dt_s": 3600.})
    if (rain.shape != (24, *hierarchy["arrays"]["height_m"].shape)
            or case["forcing_identity"] != forcing
            or case["plan"]["origin_m_xz"] != hierarchy["metadata"]["origin_m_xz"]
            or case["plan"]["spacing_m"] != hierarchy["metadata"]["spacing_m"]):
        raise ValueError("native forcing coordinates/identity mismatch")
    pages = execution["scenarios"][direction]["pages"]
    _page_coverage(pages)
    for hour, page in enumerate(pages):
        for role in ("storage", "checkpoint"):
            _layout(page[role], root / f"{direction}-0.625s" / f"hour-{hour:02d}" / f"{role}.npz")
    _memory()
    return dict(acceptance_record=dict(acceptance_record), acceptance=accepted, execution=execution,
                hierarchy=hierarchy, source=source, source_record=weather_index["source"],
                source_records=source_records, weather=weather, rain=rain, pages=pages,
                direction=direction, forcing_identity=forcing, step_s=.625,
                coordinates=dict(origin_m_xz=hierarchy["metadata"]["origin_m_xz"],
                                 spacing_m=hierarchy["metadata"]["spacing_m"],
                                 axes="x east, y elevation, z south; metres; cell centers"))


def _page_coverage(pages):
    if (not isinstance(pages, list) or len(pages) != 24
            or any(type(page.get("hour")) is not int or page["hour"] != hour for hour, page in enumerate(pages))):
        raise ValueError("ordered complete 24-hour coverage required")


def _validate_hour(storage, checkpoint, *, context, hour, previous):
    hierarchy = context["hierarchy"]
    valid = hierarchy["arrays"]["valid_mask"].ravel()
    cells, faces = len(valid), len(hierarchy["arrays"]["face_cells"])
    step = context["step_s"]
    runoff = asdict(RunoffParameters())
    expected = dict(profile=PROFILE, hierarchy_identity=hierarchy["identity_sha256"],
                    forcing_identity=context["forcing_identity"], forcing_hour_offset=hour,
                    start_s=hour*3600., end_s=(hour+1)*3600., dt_s=3600.,
                    substep_s=step, substeps=int(3600/step), cells=cells, faces=faces,
                    spacing_m=hierarchy["metadata"]["spacing_m"], origin_m_xz=hierarchy["metadata"]["origin_m_xz"],
                    parameters=dict(PHYSICS, substep_s=step), runoff_parameters=runoff,
                    physics=PHYSICS_SEMANTICS,
                    permanent_lake_impermeability="not modelled; requires independent material mask",
                    activity_semantics="SSP-RK2 stage quadrature of actual signed exchange; not exact event duration")
    for result in (storage, checkpoint):
        _flags(result["metadata"])
        if any(result["metadata"].get(key) != value for key, value in expected.items()):
            raise ValueError("saved native hour metadata binding mismatch")
    if checkpoint["metadata"].get("last_page_identity") != storage["identity_sha256"]:
        raise ValueError("checkpoint last-page identity mismatch")
    arrays, saved = storage["arrays"], checkpoint["arrays"]
    budget = validate_native_v10_accounts(storage, hierarchy=hierarchy, rain_mm_h=context["rain"][hour])
    for name in STATES:
        initial = np.where(valid, 0. if name == "depth_m" else runoff["initial_"+name], 0.) if previous is None else previous[name]
        if not np.array_equal(arrays[name][0], initial) or not np.array_equal(arrays[name][1], saved[name]):
            raise ValueError("four-state checkpoint continuity mismatch")
    for name in ERRORS:
        if saved[name].dtype != np.float64 or np.any(saved[name][~valid] != 0):
            raise ValueError("checkpoint unknown compensation mismatch")
    for name in FLUX:
        cumulative = arrays[name] if previous is None else previous["cumulative_"+name]+arrays[name]
        if not np.array_equal(saved["cumulative_"+name], cumulative):
            raise ValueError("checkpoint cumulative signed-face continuity mismatch")
    if np.any(saved["cumulative_active_forward_s"]+saved["cumulative_active_reverse_s"] > (hour+1)*3600.+1e-8):
        raise ValueError("checkpoint combined activity exceeds elapsed time")
    area = hierarchy["metadata"]["spacing_m"]**2
    fast_release = arrays["rain_excess_m3"][0] - np.diff(arrays["fast_mm"], axis=0)[0]*area/1000
    slow_release = arrays["percolation_m3"][0] - np.diff(arrays["slow_mm"], axis=0)[0]*area/1000
    if np.any(fast_release < -1e-6) or np.any(slow_release < -1e-6):
        raise ValueError("negative inferred fast/slow release")
    return budget


def iter_single_domain_hours(context):
    """Stream one page/checkpoint pair, retaining one previous checkpoint only."""
    _page_coverage(context["pages"])
    previous = None
    faces = len(context["hierarchy"]["arrays"]["face_cells"])
    for hour, page in enumerate(context["pages"]):
        if (page.get("forcing_identity") != context["forcing_identity"]
                or page.get("chunk_work_face_steps") != int(3600/context["step_s"])*faces):
            raise ValueError("page forcing/work binding mismatch")
        storage, checkpoint = load_storage(**page["storage"]), load_checkpoint(**page["checkpoint"])
        budget = _validate_hour(storage, checkpoint, context=context, hour=hour, previous=previous)
        _memory()
        yield dict(storage=storage, checkpoint=checkpoint, budget=budget, hour=hour,
                   storage_record=page["storage"], checkpoint_record=page["checkpoint"])
        previous = checkpoint["arrays"]
        del storage, checkpoint
    if file_sha256(context["acceptance_record"]["path"]) != context["acceptance_record"]["expected_sha256"]:
        raise ValueError("accepted evidence changed during stream")


def audit_single_domain_chain(context):
    hours = [item["budget"] for item in iter_single_domain_hours(context)]
    rain = math.fsum(item["rain_m3"] for item in hours)
    loss = math.fsum(item["loss_m3"] for item in hours)
    export = math.fsum(item["external_m3"] for item in hours)
    residual = math.fsum([hours[0]["initial_water_m3"], rain, -loss, -export, -hours[-1]["final_water_m3"]])
    allowed = 1e-6 + rain*1e-10
    if abs(residual) > allowed:
        raise ValueError("single-domain whole-period budget mismatch")
    return dict(schema="single-domain-surface-chain-audit-v1", direction=context["direction"], hours=hours,
                whole_period_residual_m3=residual, allowed_m3=allowed, rain_m3=rain, loss_m3=loss,
                engineering_export_m3=export, checkpoint_chain_verified=True, cell_budgets_verified=True,
                temporal_acceptance_record=context["acceptance_record"], resource=_memory(),
                solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                limitations=list(LIMITATIONS))


def load_single_domain_index(path, *, expected_sha256):
    """Bind the complete two-direction review to externally accepted native pages."""
    from terrain_pipeline.fine_subgrid import load_geometry

    index_record = dict(path=str(path), expected_sha256=expected_sha256)
    index = _json(index_record)
    _flags(index)
    if (index.get("schema") != "single-domain-surface-index-v1"
            or index.get("natural_outlet_verified") is not False
            or not isinstance(index.get("limitations"), list) or not index["limitations"]
            or set(index.get("directions", {})) != {"eastward", "westward"}):
        raise ValueError("complete finite single-domain index required")
    root = Path(__file__).resolve().parents[1]
    codes = index.get("code_sha256")
    if not isinstance(codes, dict) or not REQUIRED_CODE_FILES.issubset(codes):
        raise ValueError("surface index code pins required")
    for name, digest in codes.items():
        target = (root / name).resolve(strict=True)
        if not target.is_relative_to(root) or file_sha256(target) != digest:
            raise ValueError("surface code pin mismatch")
    published_root = Path(path).resolve(strict=True).parent
    _derived_record(index["report"], published_root)
    _derived_record(index["resource"], published_root)
    report, resource = _json(index["report"]), _json(index["resource"])
    _flags(report)
    if (report.get("schema") != "single-domain-surface-report-v1"
            or resource.get("schema") != "single-domain-surface-resource-v1"
            or resource.get("budgets") != BUDGETS
            or any(report.get(name) != index.get(name) for name in
                   ("acceptance_record", "source_records", "directions", "code_sha256"))
            or resource.get("complete") is not True
            or any(type(resource.get(name)) is not int or not 0 < resource[name] <= MAX_BYTES
                   for name in ("peak_rss_bytes", "peak_private_bytes"))
            or type(resource.get("output_bytes")) is not int or not 0 < resource["output_bytes"] <= 2*MAX_BYTES
            or type(resource.get("elapsed_s")) not in (int, float)
            or not 0 <= resource["elapsed_s"] <= 1800):
        raise ValueError("surface resource evidence outside predeclared budgets")
    artifact_records = [index["report"]]
    for group in index["directions"].values():
        artifact_records.append(group["geometry"])
        if "geometry_obj" in group:
            artifact_records.append(group["geometry_obj"])
        artifact_records.extend(frame["water_frame"] for frame in group["frames"])
    samples = report.get("sample_records", [])
    if not isinstance(samples, list):
        raise ValueError("surface sample artifact inventory must be a list")
    artifact_records.extend(samples)
    saved_records = resource.get("artifact_records")
    if (not isinstance(saved_records, list)
            or any(not isinstance(record, dict) or not isinstance(record.get("path"), str)
                   for record in artifact_records + (saved_records if isinstance(saved_records, list) else []))
            or sorted(saved_records, key=lambda item: item["path"]) != sorted(artifact_records, key=lambda item: item["path"])):
        raise ValueError("surface explicit artifact inventory mismatch")
    artifact_paths = [_derived_record(record, published_root) for record in artifact_records]
    if len(set(artifact_paths)) != len(artifact_paths):
        raise ValueError("duplicate derived surface artifact path")
    if resource["output_bytes"] != sum(target.stat().st_size for target in artifact_paths):
        raise ValueError("surface actual output byte inventory mismatch")
    chains, geometries = {}, {}
    for direction, group in index["directions"].items():
        chain = load_accepted_single_domain_chain(index["acceptance_record"], direction)
        if index.get("source_records") != chain["source_records"]:
            raise ValueError("surface index source binding mismatch")
        frames = group.get("frames")
        if (not isinstance(frames, list) or len(frames) != 25
                or any(type(frame.get("frame")) is not int or frame["frame"] != number
                       or frame.get("time_s") != number*3600.
                       or type(frame.get("state_index")) is not int
                       or frame["state_index"] != (0 if number == 0 else 1)
                       or frame.get("source_page") != chain["pages"][max(0, number-1)]["storage"]
                       for number, frame in enumerate(frames))):
            raise ValueError("surface index complete 25 saved frame binding mismatch")
        geometry = load_geometry(**group["geometry"])
        metadata = geometry["metadata"]
        if (metadata["hierarchy_identity"] != chain["hierarchy"]["identity_sha256"]
                or metadata["source_identity"] != chain["source"]["identity_sha256"]
                or metadata["source_hierarchy_sha256"] != chain["source_records"]["hierarchy"]["expected_sha256"]
                or metadata["spacing_m"] != chain["coordinates"]["spacing_m"]
                or metadata["origin_m_xz"] != chain["coordinates"]["origin_m_xz"]):
            raise ValueError("surface geometry source/coordinate binding mismatch")
        for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
            if not np.array_equal(geometry["arrays"][name], chain["hierarchy"]["arrays"][name]):
                raise ValueError("surface geometry original bed mismatch")
        chains[direction], geometries[direction] = chain, geometry
    _memory()
    return dict(index=index, index_record=index_record, chains=chains, geometries=geometries,
                report=report, resource=resource)


def _derived_record(record, root):
    target = Path(record["path"])
    if (any(parent.is_symlink() for parent in (target, *target.parents))
            or not target.resolve(strict=True).is_relative_to(root)
            or target.stat().st_size > BUDGETS["max_artifact_bytes"]
            or file_sha256(target) != record["expected_sha256"]):
        raise ValueError("derived surface artifact containment/SHA/size mismatch")
    return target.resolve(strict=True)


def iter_single_domain_frames(context, direction="eastward"):
    """Yield exact saved geometry/frame/page bindings after hourly account checks."""
    from terrain_pipeline.fine_subgrid import load_water_frame

    if direction not in context["chains"]:
        raise ValueError("unknown surface direction")
    geometry = context["geometries"][direction]
    frames = context["index"]["directions"][direction]["frames"]
    budgets = []
    for item in iter_single_domain_hours(context["chains"][direction]):
        hour = item["hour"]
        budgets.append(item["budget"])
        for number in ((0, 1) if hour == 0 else (hour+1,)):
            declaration = frames[number]
            frame = load_water_frame(**declaration["water_frame"])
            metadata = frame["metadata"]
            if (metadata["geometry_identity"] != geometry["identity_sha256"]
                    or metadata["geometry_metadata"] != geometry["metadata"]
                    or metadata["source_page_identity"] != item["storage"]["identity_sha256"]
                    or metadata["source_page_sha256"] != item["storage_record"]["expected_sha256"]
                    or metadata["forcing_identity"] != context["chains"][direction]["forcing_identity"]
                    or metadata["time_s"] != declaration["time_s"]
                    or metadata["state_index"] != declaration["state_index"]):
                raise ValueError("saved water frame metadata binding mismatch")
            for name, values in geometry["arrays"].items():
                if not np.array_equal(frame["arrays"][name], values):
                    raise ValueError("saved frame same-bed geometry mismatch")
            expected = item["storage"]["arrays"]["depth_m"][declaration["state_index"], geometry["arrays"]["node_cell_ids"]]
            if not np.array_equal(frame["arrays"]["native_depth_m"], expected):
                raise ValueError("saved frame original water depth mismatch")
            _memory()
            yield dict(frame=frame, declaration=declaration, direction=direction, hour=hour)
            del frame
    rain = math.fsum(item["rain_m3"] for item in budgets)
    residual = math.fsum([budgets[0]["initial_water_m3"], rain,
                          -math.fsum(item["loss_m3"] for item in budgets),
                          -math.fsum(item["external_m3"] for item in budgets), -budgets[-1]["final_water_m3"]])
    if abs(residual) > 1e-6+rain*1e-10:
        raise ValueError("saved frame complete-period budget mismatch")
    if file_sha256(context["index_record"]["path"]) != context["index_record"]["expected_sha256"]:
        raise ValueError("surface index changed during frame stream")
