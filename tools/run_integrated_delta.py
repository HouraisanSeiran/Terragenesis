"""Runner for the integrated reduced channel-tree delta morphodynamics.

See ``terrain_pipeline.surface_rivers.metric_integrated_delta`` for the model
description.  This runner:

  * discovers the 16 km scene geometry from NPZ,
  * loads the frozen upstream sediment bundle and cuts it at the new apex,
  * aggregates daily sediment export into 12 monthly solid volumes,
  * runs the integrated reduced delta model,
  * runs a zero-solid control for invariant bed comparison,
  * writes ``result.npz``, ``summary.json``, ``overview.png``, ``process.png``
    and ``deposition.png`` to the output directory.

Command line:  python tools/run_integrated_delta.py --output <dir> [--audit <dir>]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_variable] = "1"

import numpy as np  # noqa: E402


def _terminal_q(record):
    values = getattr(record, "terminal_q_m3_s", None)
    if values is not None and len(values):
        return np.asarray(values, dtype=float)
    return np.asarray([record.q_branch0_m3_s, record.q_branch1_m3_s, record.q_branch2_m3_s], dtype=float)

from tools.verify_fluvial_channel_remobilization import resource_limits  # noqa: E402
from tools.run_feedback_landward_case import cut_source  # noqa: E402
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_upstream_sediment import (  # noqa: E402
    load_daily_sediment,
    save_daily_sediment,
    route_daily_sediment,
)
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import route_feedback_daily  # noqa: E402
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import normal_depth  # noqa: E402
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import bed_slopes  # noqa: E402
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters  # noqa: E402
from terrain_pipeline.surface_rivers.metric_integrated_delta import (  # noqa: E402
    IntegratedDeltaConfig,
    build_channel_tree,
    integrated_solid_ledger,
    run_integrated_delta,
)


SCENE = ROOT / ".scratch/hydrological-planning-domain/stylized-mouth-16km-20261017-09/scene.npz"
SOURCE = ROOT / "verification/fluvial-delta/same-source-feedback-landward-20261016-02"
DEFAULT_OUTPUT = ROOT / "verification/fluvial-delta/integrated-16km-20261017-03"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get(path: Path, *keys: str) -> np.ndarray:
    with np.load(path) as data:
        for key in keys:
            if key in data.files:
                return data[key]
    raise KeyError(f"none of {keys} found in {path}")


def load_scene(scene_path: Path) -> dict:
    """Load the 16 km scene geometry.  Tolerant to key naming."""

    with np.load(scene_path, allow_pickle=False) as data:
        files = list(data.files)
        bed = data["bed_m"].copy() if "bed_m" in files else data["base_bed_m"].copy()
        metadata = json.loads(str(data["metadata_json"].item()))
        origin = np.asarray(metadata["origin_xz_m"])
        spacing = float(metadata["spacing_m"])
        mouth = np.asarray(metadata["mouth_xz_m"])
        apex = np.asarray(metadata["fan_apex_xz_m"])
        trunk = data["trunk_path_xz_m"].copy()
        branches = data["branch_paths_xz_m"].copy()
        widths = np.r_[float(data["trunk_width_m"]) if "trunk_width_m" in files else 100., data["branch_width_m"]]
        extra = {key: data[key].copy() for key in (
            "original_land_mask", "retained_upstream_raster_mask", "designed_incoming_path_xz_m",
            "designed_incoming_bed_m", "main_section_mask", "connected_ocean_mask")}
        extra["base_bed_m"] = data["base_bed_m"].copy()
        for key in ("open_marine_mask", "incoming_width_profile_m", "terminal_parent_index", "terminal_level"):
            if key in files:
                extra[key] = data[key].copy()
        metadata = {}
        for key in ("metadata_json", "scene_metadata_json", "meta_json"):
            if key in files:
                try:
                    metadata = json.loads(str(data[key].item()))
                except Exception:
                    metadata = {}
                break
    if branches.ndim != 3 or branches.shape[0] < 1 or branches.shape[2] != 2:
        raise ValueError(f"branch_paths_xz_m has unexpected shape {branches.shape}")
    return {
        "bed_m": bed,
        "origin_xz_m": origin,
        "spacing_m": spacing,
        "mouth_xz_m": mouth,
        "fan_apex_xz_m": apex,
        "trunk_path_xz_m": trunk,
        "branch_paths_xz_m": branches,
        "widths_m": widths,
        "metadata": metadata,
        **extra,
    }


def monthly_partition(
    daily_time_s: np.ndarray,
    daily_export_solid_m3: np.ndarray,
    daily_water_m3: np.ndarray,
    month_starts_s: np.ndarray,
    month_ends_s: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Sum daily values into exact monthly bins."""

    starts = np.asarray(daily_time_s[:-1], dtype=np.float64)
    ends = np.asarray(daily_time_s[1:], dtype=np.float64)
    if starts.shape != ends.shape:
        raise ValueError("daily_time_s must be strictly increasing")
    covered = np.zeros(starts.shape, dtype=np.int64)
    solid = []
    water = []
    for ms, me in zip(month_starts_s, month_ends_s):
        mask = (starts >= ms - 1e-9) & (ends <= me + 1e-9)
        covered += mask
        solid.append(float(np.sum(daily_export_solid_m3[mask])))
        water.append(float(np.sum(daily_water_m3[mask])))
    if np.any(covered != 1) or not np.isclose(sum(solid), np.sum(daily_export_solid_m3), rtol=1e-9, atol=1e-6):
        raise ValueError("monthly intervals must partition daily boundaries exactly")
    return np.asarray(solid, dtype=np.float64), np.asarray(water, dtype=np.float64)


def positive_discharge_scale(value):
    scale = float(value)
    if not np.isfinite(scale) or scale <= 0.:
        raise ValueError("discharge scale must be positive and finite")
    return scale


def scale_source_discharge(prefix, node_xz_m, discharge_scale):
    """Rebuild initial hydraulics with scaled Q and unchanged finite materials."""
    scale = positive_discharge_scale(discharge_scale)
    if scale == 1.:
        return prefix
    a, metadata = prefix["arrays"], prefix["metadata"]
    q = a["water_q_m3_s"]*scale
    slope = bed_slopes(a["receiver"], a["bed_elevation_m"], node_xz_m)
    slopes = np.broadcast_to(slope, q.shape).copy()
    depth = np.array([[normal_depth(flow, width, grade) for flow, width, grade in
                       zip(row, a["width_m"], slope)] for row in q])
    return route_daily_sediment(
        receiver=a["receiver"], length_m=a["length_m"], width_m=a["width_m"],
        bed_elevation_m=a["bed_elevation_m"], water_depth_m=depth, water_q_m3_s=q,
        friction_slope=slopes, time_seconds=a["time_seconds"], rock_floor_m=a["rock_floor_m"],
        initial_alluvium_bulk_m3=a["initial_alluvium_bulk_m3"], hardness=a["hardness_source"],
        material=MaterialParameters(**metadata["material"]),
        initial_mobile_solid_m3=a["initial_mobile_solid_m3"],
        external_solid_m3_s=a["external_solid_m3_s"], retention_fraction=a["retention_fraction"],
        geometry_identity_sha256=metadata["geometry_identity_sha256"],
        hydraulic_identity_sha256=identity({"q": q, "depth": depth, "slope": slopes},
            {"algorithm": "scaled-Q-initial-Manning-v1", "discharge_scale": scale,
             "baseline_hydraulic_identity_sha256": metadata["hydraulic_identity_sha256"]}),
        material_provenance=metadata["material_provenance"])


def source_inventory(prefix, feedback):
    a, final = prefix["arrays"], feedback["arrays"]
    reserve = (a["bed_elevation_m"]-a["initial_alluvium_bulk_m3"]/a["area_m2"]-a["rock_floor_m"])*a["area_m2"]
    removed = final["trace_rock_removed_m3"][-1]
    remaining = np.maximum(reserve-removed, 0.)
    return {"initial_rock_solid_m3": float(reserve.sum()), "eroded_rock_solid_m3": float(removed.sum()),
            "remaining_rock_solid_m3": float(remaining.sum()),
            "initial_loose_solid_m3": float(a["initial_alluvium_bulk_m3"].sum()*(1.-prefix["metadata"]["material"]["porosity"])),
            "remaining_loose_solid_m3": float(final["trace_loose_solid_m3"][-1].sum()),
            "rock_depleted_nodes": int(np.count_nonzero(remaining <= 1.e-8)), "source_nodes": int(len(reserve)),
            "rock_depleted": bool(np.all(remaining <= 1.e-8))}


def load_or_build_source(apex: np.ndarray, mouth: np.ndarray, discharge_scale=1., scene_path=SCENE) -> dict:
    """Re-cut finite inventory before construction, then transfer without exchange."""
    cut_path = SOURCE / "cut_frozen_source.npz"
    fb_path = SOURCE / "feedback_bundle.npz"
    frozen = load_daily_sediment(cut_path, file_sha256(cut_path))
    old_feedback = load_daily_sediment(fb_path, file_sha256(fb_path))
    xz = old_feedback["arrays"]["node_xz_m"]
    tangent = (mouth - apex) / np.linalg.norm(mouth - apex)
    with np.load(scene_path) as scene:
        metadata = json.loads(scene["metadata_json"].item())
    retained_limit = float(metadata["retained_profile_before_u_m"])
    station = (xz - mouth) @ tangent
    count = int(np.flatnonzero(station <= retained_limit)[-1]) + 1
    if count < 2 or np.any(station[:count] > retained_limit):
        raise ValueError("source prefix must end before constructed transition")
    baseline_prefix = cut_source(frozen, xz, count)
    prefix = scale_source_discharge(baseline_prefix, xz[:count], discharge_scale)
    feedback = route_feedback_daily(prefix, xz[:count])
    return {"prefix": prefix, "feedback": feedback, "cut_path": cut_path, "fb_path": fb_path,
            "baseline_daily_terminal_q_m3_s": baseline_prefix["arrays"]["water_q_m3_s"][:, -1].copy(),
            "cut_count": count, "handoff_gap_m": float(np.linalg.norm(xz[count-1]-apex)),
            "retained_source_limit_u_m": retained_limit,
            "source_cut_xz_m": xz[count-1].tolist(),
            "upstream_boundary_bed_m": float(prefix["arrays"]["bed_elevation_m"][-1])}


def monthly_time_from_mouth(mouth_path: Path) -> tuple[np.ndarray, np.ndarray]:
    times = _get(mouth_path, "monthly_time_seconds", "time_seconds")
    if times.ndim == 1:
        if times.size < 2:
            raise ValueError("monthly_time_seconds must have >= 2 entries")
        starts = times[:-1]
        ends = times[1:]
    else:
        starts = times[:, 0]
        ends = times[:, 1]
    return starts.astype(np.float64), ends.astype(np.float64)


def protect_scene_geometry(geometry, scene):
    protected = scene["retained_upstream_raster_mask"].copy()
    if "open_marine_mask" in scene:
        protected |= scene["open_marine_mask"]
    geometry.eligible_mask &= ~protected
    geometry.protected_mask |= protected


def run(output: Path, discharge_scale=1., scene_path=SCENE) -> dict:
    resource_limits()
    discharge_scale = positive_discharge_scale(discharge_scale)
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("scenario output already contains results: "+str(output))

    scene_path = Path(scene_path).resolve()
    scene = load_scene(scene_path)
    bed = scene["bed_m"]
    rows, cols = bed.shape
    origin = scene["origin_xz_m"]
    spacing = scene["spacing_m"]
    mouth = scene["mouth_xz_m"]
    apex = scene["fan_apex_xz_m"]
    trunk = scene["trunk_path_xz_m"]
    branches = scene["branch_paths_xz_m"]
    widths = scene["widths_m"]

    if bed.shape != (800, 800):
        raise ValueError(f"expected 800x800 raster, got {bed.shape}")

    tracked = {"scene": scene_path, "cut_frozen_source": SOURCE/"cut_frozen_source.npz",
               "feedback_bundle": SOURCE/"feedback_bundle.npz", "monthly_partition": SOURCE/"mouth.npz"}
    hashes = {key: file_sha256(path) for key, path in tracked.items()}
    source = load_or_build_source(apex, mouth, discharge_scale, scene_path)
    feedback = source["feedback"]
    a = feedback["arrays"]

    # Construct the tree, splitting the trunk at the branch junction stations.
    trunk_split = len(trunk) // 2
    branch_split = len(trunk) - 1
    geometry = build_channel_tree(
        initial_bed_m=bed,
        origin_xz=origin,
        spacing_m=spacing,
        mouth_xz=mouth,
        apex_xz=apex,
        trunk_path_xz=trunk,
        branch_paths_xz=[branches[i] for i in range(branches.shape[0])],
        widths_m=widths.tolist(),
        trunk_split_station=trunk_split,
        branch_split_station=branch_split,
        ocean_mask=scene.get("open_marine_mask"),
        branch_parent_index=scene.get("terminal_parent_index"),
    )
    protect_scene_geometry(geometry, scene)

    # Monthly time partition.
    mouth_path = SOURCE / "mouth.npz"
    month_starts, month_ends = monthly_time_from_mouth(mouth_path)
    daily_time = a["time_seconds"]
    daily_export = a["exported_solid_m3"].sum(axis=1) if a["exported_solid_m3"].ndim > 1 else a["exported_solid_m3"]
    daily_q = a["water_q_m3_s"][:, -1] if a["water_q_m3_s"].ndim > 1 else a["water_q_m3_s"]
    dt = np.diff(daily_time)
    daily_water = daily_q * dt
    monthly_solid, monthly_water = monthly_partition(
        daily_time, daily_export, daily_water,
        month_starts, month_ends,
    )
    month_dt = month_ends - month_starts

    config = IntegratedDeltaConfig()
    result = run_integrated_delta(
        bed, geometry, monthly_water, monthly_solid, month_dt, config,
    )
    result["discharge_scale"] = discharge_scale

    # Zero-solid control with same water.
    control = run_integrated_delta(
        bed, geometry, monthly_water, np.zeros_like(monthly_solid), month_dt, config,
    )
    if not np.array_equal(control["final_bed_m"], bed):
        raise ValueError("zero-solid control altered terrain")
    water_surface, water_depth, wet_mask = incoming_water(scene, result)
    connectivity = connected_water_diagnostics(scene, wet_mask)
    if not connectivity["apex_and_terminals_connected"] or not connectivity["incoming_connected_to_apex"]:
        raise ValueError("actual final wet raster has a river connectivity gap")

    # Ledger closure.
    ledger = integrated_solid_ledger(result, monthly_solid)
    terminal_water = sum(float(np.sum(_terminal_q(r)))*seconds
                         for r, seconds in zip(result["records"], month_dt))
    prefix_arrays = source["prefix"]["arrays"]
    upstream_initial = float((prefix_arrays["initial_alluvium_bulk_m3"]*.65).sum()+prefix_arrays["initial_mobile_solid_m3"].sum())
    external = float(a["external_solid_m3"].sum())
    rock = float(a["trace_rock_removed_m3"][-1].sum())
    upstream_final = float(a["trace_loose_solid_m3"][-1].sum()+a["trace_mobile_solid_m3"][-1].sum())
    residual = (ledger["input_solid_m3"]
                - ledger["retained_solid_m3"]
                - ledger["exported_solid_m3"]
                - ledger["escrow_solid_m3"])
    if abs(residual) > 1e-6 * max(1.0, ledger["input_solid_m3"]):
        raise ValueError(f"integrated solid ledger residual {residual} too large")

    output.mkdir(parents=True, exist_ok=True)
    save_daily_sediment(output/"cut_frozen_source.npz", source["prefix"])
    save_daily_sediment(output/"feedback_bundle.npz", feedback)
    np.savez_compressed(
        output / "result.npz",
        initial_bed_m=result["initial_bed_m"],
        final_bed_m=result["final_bed_m"],
        height_delta_m=result["height_delta_m"],
        stored_solid_m3=result["stored_solid_m3"],
        deposited_solid_m3=result["deposited_solid_m3"],
        reentrained_solid_m3=result["reentrained_solid_m3"],
        stage_m=result["stage_m"],
        depth_m=result["depth_m"],
        wet_timeseries=result["wet_timeseries"],
        eligible_mask=result["eligible_mask"],
        protected_mask=result["protected_mask"],
        ocean_mask=result["ocean_mask"],
        monthly_solid_m3=monthly_solid,
        monthly_water_m3=monthly_water,
        month_seconds=month_dt,
        origin_xz_m=origin,
        spacing_m=spacing,
        mouth_xz_m=mouth,
        apex_xz_m=apex,
        trunk_path_xz_m=trunk,
        branch_paths_xz_m=branches,
        widths_m=widths,
        terminal_parent_index=np.asarray(scene.get("terminal_parent_index", np.full(len(branches), -1)), dtype=int),
        terminal_level=np.asarray(scene.get("terminal_level", np.zeros(len(branches))), dtype=int),
        original_land_mask=scene["original_land_mask"],
        retained_upstream_raster_mask=scene["retained_upstream_raster_mask"],
        config_json=np.array(json.dumps(vars(config))),
        discharge_scale=np.array(discharge_scale),
        baseline_daily_terminal_q_m3_s=source["baseline_daily_terminal_q_m3_s"],
        actual_daily_terminal_q_m3_s=a["water_q_m3_s"][:, -1],
        final_heads_m=result["final_heads_m"],
        monthly_node_heads_m=result.get("monthly_node_heads_m", np.array([[r.head_source_m, r.head_junction1_m, r.head_junction2_m] for r in result["records"]])),
        node_names=np.asarray(result.get("node_names", ["source", "junction1", "junction2"])),
        monthly_max_junction_q_residual_m3_s=result.get("monthly_max_junction_q_residual_m3_s", np.zeros(len(result["records"]))),
        monthly_terminal_export_solid_m3=result["monthly_terminal_export_solid_m3"],
        monthly_land_stored_solid_m3=result["monthly_land_stored_solid_m3"],
        control_monthly_heads_m=np.array([[r.head_source_m, r.head_junction1_m, r.head_junction2_m] for r in control["records"]]),
        control_monthly_branch_q_m3_s=np.array([_terminal_q(r) for r in control["records"]]),
        water_surface_m=water_surface,
        water_depth_m=water_depth,
        wet_mask=wet_mask,
        monthly_heads_m=np.array([[r.head_source_m, r.head_junction1_m, r.head_junction2_m] for r in result["records"]]),
        monthly_branch_q_m3_s=np.array([_terminal_q(r) for r in result["records"]]),
    )

    records_payload = [{
        "water_input_m3": r.water_input_m3,
        "solid_input_m3": r.solid_input_m3,
        "terminal_q_m3_s": _terminal_q(r).tolist(),
        "head_junction1_m": r.head_junction1_m,
        "head_junction2_m": r.head_junction2_m,
        "head_source_m": r.head_source_m,
        "deposition_solid_m3": r.deposition_solid_m3,
        "reentrainment_solid_m3": r.reentrainment_solid_m3,
        "export_solid_m3": r.export_solid_m3,
        "escrow_solid_m3": r.escrow_solid_m3,
        "mass_error_m3": r.mass_error_m3,
    } for r in result["records"]]

    summary = {
        "schema": "integrated-reduced-channel-tree-delta-v1",
        "algorithm": "quasi-steady diffusive Manning trunk/branch tree with finite sediment routing",
        "scenario": {"discharge_scale": discharge_scale,
            "changed": "all-node daily upstream water discharge only; finite materials and seasonal shape unchanged",
            "baseline_mean_terminal_q_m3_s": float(np.sum(source["baseline_daily_terminal_q_m3_s"]*np.diff(daily_time))/np.sum(np.diff(daily_time))),
            "actual_mean_terminal_q_m3_s": float(monthly_water.sum()/month_dt.sum())},
        "upstream_material_inventory": source_inventory(source["prefix"], feedback),
        "assumptions": {
            "transient": False,
            "full_2d_backwater": False,
            "zero_q_is_dry": True,
            "porosity": config.porosity,
            "roughness": config.roughness,
            "bin_length_m": config.bin_length_m,
            "settling_velocity_m_s": config.settling_velocity_m_s,
        },
        "solid_ledger": ledger,
        "water_ledger": {"input_m3": float(monthly_water.sum()), "terminal_export_m3": float(terminal_water),
                         "residual_m3": float(monthly_water.sum()-terminal_water)},
        "final_wet_connectivity": connectivity,
        "junction_max_q_residual_m3_s": float(np.max(result["monthly_max_junction_q_residual_m3_s"])) if "monthly_max_junction_q_residual_m3_s" in result else max(max(abs(r.q_trunk0_m3_s-r.q_branch0_m3_s-r.q_trunk1_m3_s), abs(r.q_trunk1_m3_s-r.q_branch1_m3_s-r.q_branch2_m3_s)) for r in result["records"]),
        "combined_solid_budget": {"initial_upstream_loose_and_mobile_m3": upstream_initial,
            "external_m3": external, "rock_eroded_solid_m3": rock, "final_upstream_loose_and_mobile_m3": upstream_final,
            "delta_retained_m3": ledger["retained_solid_m3"], "terminal_export_m3": ledger["exported_solid_m3"],
            "escrow_m3": ledger["escrow_solid_m3"],
            "residual_m3": upstream_initial+external+rock-upstream_final-ledger["retained_solid_m3"]-ledger["exported_solid_m3"]-ledger["escrow_solid_m3"]},
        "implementation_hashes": {str(path.relative_to(ROOT)): file_sha256(path) for path in (
            Path(__file__), ROOT/"terrain_pipeline/surface_rivers/metric_integrated_delta.py")},
        "solid_ledger_residual_m3": residual,
        "monthly_records": records_payload,
        "monthly_solid_m3": monthly_solid.tolist(),
        "monthly_water_m3": monthly_water.tolist(),
        "month_seconds": month_dt.tolist(),
        "source_hashes_before": hashes,
        "source_hashes_after": {key: file_sha256(path) for key, path in tracked.items()},
        "source_paths": {key: str(path) for key, path in tracked.items()},
        "recut": {key: source[key] for key in ("cut_count", "handoff_gap_m", "upstream_boundary_bed_m", "retained_source_limit_u_m", "source_cut_xz_m")},
        "handoff": "Only unmodified upstream source inventory is routed. Its water and solid export pass through the immutable constructed approach without material exchange to the delta apex; original source rock removed by construction is excluded.",
        "upstream_global_residual_solid_m3": feedback["metadata"]["global_residual"],
        "upstream_budget": feedback["metadata"],
        "control_unchanged": True,
        "original_land_stored_solid_m3": float(result["stored_solid_m3"][scene["original_land_mask"]].sum()),
        "constructed_land_stored_solid_m3": float(result["stored_solid_m3"][bed > 0.].sum()),
        "emergent_area_m2": float(np.count_nonzero((bed <= 0.) & (result["final_bed_m"] > 0.))*spacing**2),
        "protected_bed_unchanged": bool(np.array_equal(result["final_bed_m"][geometry.protected_mask], bed[geometry.protected_mask])),
        "geometry": {
            "origin_xz_m": origin.tolist(),
            "spacing_m": float(spacing),
            "raster_shape": list(bed.shape),
            "apex_xz_m": apex.tolist(),
            "mouth_xz_m": mouth.tolist(),
            "trunk_split_station": trunk_split,
            "branch_split_station": branch_split,
            "widths_m": [float(w) for w in widths],
        },
        "construction_separation": {
            "construction_cut_volume_m3": float(np.maximum(scene["base_bed_m"]-bed, 0.).sum()*spacing**2),
            "construction_fill_volume_m3": float(np.maximum(bed-scene["base_bed_m"], 0.).sum()*spacing**2),
            "comment": "Construction mine/fill volumes are reference values; the natural delta bed updates only track finite deposits from the frozen upstream source.",
        },
    }

    result_replay = np.load(output / "result.npz")
    assert np.array_equal(result_replay["final_bed_m"], result["final_bed_m"])

    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    _render(output, scene, result, control, geometry, monthly_solid)

    summary["control_unchanged"] = True
    return summary


def incoming_water(scene, result):
    """Join frozen incoming terrain to solved apex water; no upstream bed update."""
    from scipy.spatial import cKDTree
    surface = result["stage_m"].copy()
    bed = result["final_bed_m"]
    path = scene["designed_incoming_path_xz_m"]
    profile = scene["designed_incoming_bed_m"]
    ds = np.linalg.norm(np.diff(path, axis=0), axis=1)
    slope = np.r_[np.maximum(-np.diff(profile)/ds, 1.e-5), 1.e-5]
    record = result["records"][-1]
    q = float(np.sum(_terminal_q(record)))
    widths = scene.get("incoming_width_profile_m", np.full(len(path), 100.))
    depth = np.array([normal_depth(q, width, s) for width, s in zip(widths, slope)])
    apex_head = float(result["final_heads_m"][0])
    stage = np.maximum(profile + depth, apex_head)
    stage = np.maximum.accumulate(stage[::-1])[::-1]
    stage[-1] = apex_head
    rr, cc = np.nonzero(scene["main_section_mask"])
    xz = scene["origin_xz_m"] + np.column_stack([cc, rr])*scene["spacing_m"]
    tangent = scene["mouth_xz_m"] - scene["fan_apex_xz_m"]
    upstream = (xz-scene["fan_apex_xz_m"]) @ tangent < 0.
    idx = cKDTree(path).query(xz[upstream])[1]
    surface[rr[upstream], cc[upstream]] = np.maximum(surface[rr[upstream], cc[upstream]], stage[idx])
    if "open_marine_mask" in scene:
        surface[scene["open_marine_mask"]] = 0.
    wet = (surface > bed) & ((result["depth_m"] > 0.) | scene["main_section_mask"])
    return surface, np.where(wet, surface-bed, 0.), wet


def connected_water_diagnostics(scene, wet):
    from scipy.ndimage import label
    labels, _ = label(wet)
    origin, spacing = scene["origin_xz_m"], scene["spacing_m"]
    def cell(point):
        cc, rr = np.rint((point-origin)/spacing).astype(int)
        return int(np.clip(rr, 0, wet.shape[0]-1)), int(np.clip(cc, 0, wet.shape[1]-1))
    apex = int(labels[cell(scene["fan_apex_xz_m"])])
    terminal = [int(labels[cell(point)]) for point in scene["branch_paths_xz_m"][:, -1]]
    path = scene["designed_incoming_path_xz_m"]
    # Check the first actual incoming path sample inside this saved raster.
    ij = np.rint((path-origin)/spacing).astype(int)
    inside = (ij[:,0] >= 0) & (ij[:,0] < wet.shape[1]) & (ij[:,1] >= 0) & (ij[:,1] < wet.shape[0])
    incoming = int(labels[cell(path[np.flatnonzero(inside)[0]])])
    return {"apex_and_terminals_connected": bool(apex and all(v == apex for v in terminal)),
            "apex_and_three_terminals_connected": bool(apex and all(v == apex for v in terminal)),
            "incoming_connected_to_apex": bool(apex and incoming == apex),
            "apex_component": apex, "terminal_components": terminal, "incoming_component": incoming}


def _render(output, scene, result, control, geometry, monthly_solid):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from matplotlib.colors import LinearSegmentedColormap
    bed, final = scene["bed_m"], result["final_bed_m"]
    spacing = scene["spacing_m"]
    scale_label = format(float(result.get("discharge_scale", 1.)), "g")+"x upstream discharge"
    extent = [0, bed.shape[1]*spacing/1000., bed.shape[0]*spacing/1000., 0]
    rows, cols = np.nonzero(geometry.eligible_mask)
    limits = ((max(0., cols.min()*spacing/1000.-.5), min(16., cols.max()*spacing/1000.+.5)),
              (min(16., rows.max()*spacing/1000.+.5), max(0., rows.min()*spacing/1000.-.5)))
    surface, depth, wet = incoming_water(scene, result)
    _, control_depth, control_wet = incoming_water(scene, control)
    land_palette = LinearSegmentedColormap.from_list("delta_land", ["#82b87e", "#5b8f63", "#8c9b82", "#a2a6a0", "#d8dad6"])
    sea_palette = LinearSegmentedColormap.from_list("delta_seabed", ["#184e6d", "#5e9b9a"])
    positive_max = max(float(np.maximum(bed, 0.).max()), 1.)
    negative_min = min(float(bed.min()), -1.)
    def terrain_rgb(terrain):
        land_scale = np.log1p(np.maximum(terrain, 0.))/np.log1p(positive_max)
        sea_scale = np.clip((terrain-negative_min)/(-negative_min), 0., 1.)
        rgb = np.where((terrain > 0.)[...,None], land_palette(land_scale)[...,:3], sea_palette(sea_scale)[...,:3])
        return LightSource(315,45).shade_rgb(rgb, terrain, vert_exag=3., dx=spacing, dy=spacing, blend_mode="soft")
    fig, axes = plt.subplots(1, 2, figsize=(15,7))
    for ax, terrain, water_depth, water_wet, title in zip(axes, (bed, final), (control_depth, depth),
            (control_wet, wet), ("Accepted constructed reference", "After one finite supplied year")):
        rgb = terrain_rgb(terrain)
        ax.imshow(rgb, extent=extent)
        water = np.where(water_wet, np.minimum(water_depth, 5.), np.nan)
        image = ax.imshow(water, extent=extent, cmap="Blues", vmin=0., vmax=5., alpha=.8)
        ax.contour(terrain, levels=[0.], colors="black", linewidths=.4, extent=extent, origin="upper")
        ax.set_title(title)
        ax.set_xlim(*limits[0]); ax.set_ylim(*limits[1])
        ax.set_xlabel("East from scene origin (km)"); ax.set_ylabel("South (km)")
    fig.colorbar(image, ax=axes.tolist(), label="Final connected water depth (m)", shrink=.7)
    fig.suptitle(scale_label)
    fig.savefig(output/"overview.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10,10))
    rgb = terrain_rgb(final)
    ax.imshow(rgb, extent=extent)
    image = ax.imshow(np.where(wet, np.minimum(depth, 5.), np.nan), extent=extent,
                      cmap="Blues", vmin=0., vmax=5., alpha=.8)
    ax.contour(final, levels=[0.], colors="black", linewidths=.4, extent=extent, origin="upper")
    ax.set_xlim(0., 16.); ax.set_ylim(16., 0.)
    ax.set_xlabel("East from scene origin (km)"); ax.set_ylabel("South (km)")
    ax.set_title("Full 16 km scene after one finite supplied year; "+scale_label)
    fig.colorbar(image, ax=ax, label="Final connected water depth (m)", shrink=.75)
    fig.tight_layout(); fig.savefig(output/"scene-16km.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(4, 1, figsize=(12,12), sharex=True)
    months = np.arange(1, len(monthly_solid)+1)
    def hydraulic(runs):
        q = np.array([_terminal_q(r) for r in runs["records"]])
        return q/q.sum(axis=1)[:,None]
    actual, zero = hydraulic(result), hydraulic(control)
    for i in range(actual.shape[1]):
        axes[0].plot(months, actual[:,i], label="branch "+str(i))
        axes[0].plot(months, zero[:,i], linestyle="--", alpha=.6)
    axes[0].set_ylabel("Flow fraction"); axes[0].legend(ncol=3)
    axes[0].set_title("Solid = evolving bed; dashed = same-water zero-solid control")
    if "monthly_node_heads_m" in result:
        for index, name in enumerate(result["node_names"]):
            axes[1].plot(months, result["monthly_node_heads_m"][:, index], label=name)
    else:
        for attr, label in (("head_source_m","apex"),("head_junction1_m","junction 1"),("head_junction2_m","junction 2")):
            axes[1].plot(months, [getattr(r,attr) for r in result["records"]], label=label)
    axes[1].set_ylabel("Stage above sea (m)"); axes[1].legend(ncol=3)
    axes[2].bar(months, monthly_solid, label="Finite input solid", color="firebrick")
    axes[2].plot(months, [r.export_solid_m3 for r in result["records"]], label="Terminal export", color="black")
    axes[2].set_ylabel("Solid volume (m3)"); axes[2].legend()
    axes[3].plot(months, result["monthly_land_stored_solid_m3"], marker="o", color="seagreen")
    axes[3].set_ylabel("Net on constructed land (m3)"); axes[3].set_xlabel("Calendar month")
    fig.suptitle(scale_label)
    fig.tight_layout(); fig.savefig(output/"process.png", dpi=150); plt.close(fig)

    fig, axes = plt.subplots(1,3,figsize=(17,6))
    fields = (result["height_delta_m"]*1000., result["stored_solid_m3"],
              np.where(scene["original_land_mask"], result["stored_solid_m3"], np.nan))
    titles = ("Natural bed rise (mm)", "Net stored solid (m3/cell)", "On original pre-construction land (m3/cell)")
    for ax, field, title in zip(axes, fields, titles):
        image=ax.imshow(field, extent=extent, cmap="magma", vmin=0.)
        ax.contour(bed, levels=[0.], colors="cyan", linewidths=.4, extent=extent, origin="upper")
        ax.set_xlim(*limits[0]); ax.set_ylim(*limits[1]); ax.set_title(title)
        ax.set_xlabel("East from scene origin (km)"); ax.set_ylabel("South (km)")
        fig.colorbar(image, ax=ax, shrink=.7)
    fig.suptitle(scale_label+"; one year: "+format(float(monthly_solid.sum()),",.1f")+" m3 finite input; construction excluded")
    fig.tight_layout(); fig.savefig(output/"deposition.png", dpi=160); plt.close(fig)

    apex = (scene["fan_apex_xz_m"]-scene["origin_xz_m"])/1000.
    fig, axes = plt.subplots(2,2,figsize=(12,11))
    fields = (bed, final, depth, result["height_delta_m"])
    titles = ("Initial constructed bed (m)", "Final bed (m)", "Final connected depth (m)", "Natural bed rise (m)")
    for ax, field, title, cmap in zip(axes.flat, fields, titles, ("terrain","terrain","Blues","magma")):
        options = {"vmin": -3., "vmax": 4.} if "bed (m)" in title else {"vmin":0.}
        if title == "Final connected depth (m)":
            options["vmax"] = 5.
        image = ax.imshow(field, extent=extent, cmap=cmap, **options)
        ax.contour(bed, levels=[0.], colors="cyan", linewidths=.7, extent=extent, origin="upper")
        ax.plot(apex[0],apex[1],marker="+",color="red",markersize=10)
        ax.set_xlim(apex[0]-.35,apex[0]+.65); ax.set_ylim(apex[1]+.65,apex[1]-.35)
        ax.set_title(title); ax.set_xlabel("East from scene origin (km)"); ax.set_ylabel("South (km)")
        fig.colorbar(image, ax=ax, shrink=.8, extend="max" if title == "Final connected depth (m)" else "neither")
    fig.suptitle(scale_label)
    fig.tight_layout(); fig.savefig(output/"apex-deposition-detail.png",dpi=160); plt.close(fig)


def audit(output: Path) -> dict:
    resource_limits()
    output = Path(output)
    result = np.load(output / "result.npz")
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    for key, path in summary["source_paths"].items():
        if file_sha256(Path(path)) != summary["source_hashes_before"][key]:
            raise ValueError("source hash mismatch: " + key)
    frozen = load_daily_sediment(output/"cut_frozen_source.npz", file_sha256(output/"cut_frozen_source.npz"))
    saved_feedback = load_daily_sediment(output/"feedback_bundle.npz", file_sha256(output/"feedback_bundle.npz"))
    replay_feedback = route_feedback_daily(frozen, saved_feedback["arrays"]["node_xz_m"])
    if replay_feedback["identity_sha256"] != saved_feedback["identity_sha256"]:
        raise ValueError("upstream finite feedback replay mismatch")
    discharge_scale = positive_discharge_scale(summary.get("scenario", {}).get("discharge_scale", 1.))
    scene_path = Path(summary["source_paths"]["scene"])
    scene = load_scene(scene_path)
    rebuilt = load_or_build_source(result["apex_xz_m"], result["mouth_xz_m"], discharge_scale, scene_path)
    if rebuilt["prefix"]["identity_sha256"] != frozen["identity_sha256"]:
        raise ValueError("source recut replay mismatch")
    if "discharge_scale" in result.files:
        if float(result["discharge_scale"]) != discharge_scale:
            raise ValueError("saved discharge parameter mismatch")
        if not np.array_equal(result["baseline_daily_terminal_q_m3_s"], rebuilt["baseline_daily_terminal_q_m3_s"]):
            raise ValueError("baseline daily discharge replay mismatch")
        if not np.array_equal(result["actual_daily_terminal_q_m3_s"], replay_feedback["arrays"]["water_q_m3_s"][:, -1]):
            raise ValueError("actual daily discharge replay mismatch")
    if "upstream_material_inventory" in summary and source_inventory(frozen, replay_feedback) != summary["upstream_material_inventory"]:
        raise ValueError("source material inventory replay mismatch")
    starts, ends = monthly_time_from_mouth(SOURCE/"mouth.npz")
    fa = replay_feedback["arrays"]
    ms, mw = monthly_partition(fa["time_seconds"], fa["exported_solid_m3"].sum(axis=1),
                               fa["water_q_m3_s"][:, -1]*np.diff(fa["time_seconds"]), starts, ends)
    for key, expected in (("monthly_solid_m3", ms), ("monthly_water_m3", mw), ("month_seconds", ends-starts)):
        if not np.array_equal(result[key], expected):
            raise ValueError("saved forcing mismatch: " + key)
    geometry = build_channel_tree(result["initial_bed_m"], result["origin_xz_m"], float(result["spacing_m"]),
        result["mouth_xz_m"], result["apex_xz_m"], result["trunk_path_xz_m"], result["branch_paths_xz_m"],
        result["widths_m"], trunk_split_station=summary["geometry"]["trunk_split_station"],
        branch_split_station=summary["geometry"]["branch_split_station"], ocean_mask=scene.get("open_marine_mask"),
        branch_parent_index=scene.get("terminal_parent_index"))
    protect_scene_geometry(geometry, scene)
    config = IntegratedDeltaConfig(**json.loads(result["config_json"].item()))
    replay = run_integrated_delta(result["initial_bed_m"], geometry, mw, ms, ends-starts, config)
    for key in ("final_bed_m", "height_delta_m", "stored_solid_m3", "deposited_solid_m3", "reentrained_solid_m3", "stage_m", "depth_m", "wet_timeseries", "eligible_mask", "protected_mask", "ocean_mask", "final_heads_m", "monthly_land_stored_solid_m3", "monthly_terminal_export_solid_m3"):
        if not np.array_equal(replay[key], result[key]):
            raise ValueError("cold numerical replay mismatch: " + key)
    heads = np.array([[r.head_source_m, r.head_junction1_m, r.head_junction2_m] for r in replay["records"]])
    q = np.array([_terminal_q(r) for r in replay["records"]])
    if not np.array_equal(heads, result["monthly_heads_m"]) or not np.array_equal(q, result["monthly_branch_q_m3_s"]):
        raise ValueError("monthly hydraulics replay mismatch")
    if "monthly_node_heads_m" in replay and not np.array_equal(replay["monthly_node_heads_m"], result["monthly_node_heads_m"]):
        raise ValueError("monthly node head replay mismatch")
    control = run_integrated_delta(result["initial_bed_m"], geometry, mw, np.zeros_like(ms), ends-starts, config)
    control_unchanged = np.array_equal(control["final_bed_m"], result["initial_bed_m"])
    surface, depth, wet = incoming_water(scene, replay)
    for key, value in (("water_surface_m", surface), ("water_depth_m", depth), ("wet_mask", wet)):
        if not np.array_equal(result[key], value):
            raise ValueError("incoming water replay mismatch: "+key)
    if connected_water_diagnostics(scene, wet) != summary["final_wet_connectivity"]:
        raise ValueError("wet continuity replay mismatch")
    ledger = integrated_solid_ledger(replay, ms)
    if ledger != summary["solid_ledger"]:
        raise ValueError("summary ledger replay mismatch")
    residual = ledger["input_solid_m3"] - ledger["retained_solid_m3"] - ledger["exported_solid_m3"] - ledger["escrow_solid_m3"]
    return {
        "cold_numerical_replay_match": True,
        "source_recut_and_feedback_replay_match": True,
        "initial_bed_finite": bool(np.isfinite(result["initial_bed_m"]).all()),
        "final_bed_finite": bool(np.isfinite(result["final_bed_m"]).all()),
        "zero_solid_control_unchanged": control_unchanged,
        "solid_ledger_residual_m3": float(residual),
        "schema": summary["schema"],
    }


def compare_discharge_cases(output):
    """Compare completed scenarios; the accepted 1x archive is read-only."""
    resource_limits()
    output = Path(output)
    scenarios = [(1., DEFAULT_OUTPUT), (2., output/"q2"), (5., output/"q5"), (10., output/"q10")]
    records = []
    for scale, directory in scenarios:
        summary = json.loads((directory/"summary.json").read_text(encoding="utf-8"))
        with np.load(directory/"result.npz") as result:
            initial, final = result["initial_bed_m"], result["final_bed_m"]
            delta, store = result["height_delta_m"], result["stored_solid_m3"]
            area = float(result["spacing_m"])**2
            water = float(result["monthly_water_m3"].sum())
            supply = float(result["monthly_solid_m3"].sum())
            record = {"discharge_scale": scale, "path": str(directory),
                "input_solid_m3": supply, "retained_solid_m3": float(store.sum()),
                "exported_solid_m3": summary["solid_ledger"]["exported_solid_m3"],
                "mean_water_q_m3_s": water/float(result["month_seconds"].sum()),
                "annual_mean_solid_water_volume_ratio": supply/water,
                "maximum_bed_rise_m": float(delta.max()),
                "actual_new_dry_area_m2": float(np.count_nonzero((initial <= 0.) & (final > 0.) & (result["water_depth_m"] <= 1.e-9))*area),
                "zero_datum_crossing_area_m2": float(np.count_nonzero((initial <= 0.) & (final > 0.))*area),
                "wet_connectivity": summary["final_wet_connectivity"],
                "solid_residual_m3": summary["solid_ledger_residual_m3"]}
            for name, mask in (("constructed_dry_land", initial > 0.), ("original_preconstruction_land", result["original_land_mask"])):
                record[name] = {"retained_solid_m3": float(store[mask].sum()),
                    "bed_rise_at_least_1mm_area_m2": float(np.count_nonzero(mask & (delta >= .001))*area),
                    "bed_rise_at_least_1cm_area_m2": float(np.count_nonzero(mask & (delta >= .01))*area)}
        prefix = load_daily_sediment(directory/"cut_frozen_source.npz", file_sha256(directory/"cut_frozen_source.npz"))
        feedback = load_daily_sediment(directory/"feedback_bundle.npz", file_sha256(directory/"feedback_bundle.npz"))
        record["upstream_material_inventory"] = source_inventory(prefix, feedback)
        records.append(record)
    inventory_keys = ("initial_rock_solid_m3", "initial_loose_solid_m3", "source_nodes")
    for record in records[1:]:
        if any(record["upstream_material_inventory"][key] != records[0]["upstream_material_inventory"][key] for key in inventory_keys):
            raise ValueError("sweep changed finite source materials")
    comparison = {"parameter": "upstream all-node daily discharge scale",
        "terrain_and_materials_fixed": True, "baseline_reused_read_only": str(DEFAULT_OUTPUT),
        "interpretation": "Larger water discharge does not create sediment; annual supply remains bounded by the same finite loose and rock inventories.",
        "cases": records}
    output.mkdir(parents=True, exist_ok=True)
    (output/"comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,2,figsize=(13,5))
    x = np.arange(len(records))
    for offset, key, label in ((-.25,"input_solid_m3","Input"),(0.,"retained_solid_m3","Retained"),(.25,"exported_solid_m3","Exported")):
        axes[0].bar(x+offset, [r[key] for r in records], width=.25, label=label)
    axes[0].set_ylabel("Annual solid volume (m3)"); axes[0].legend()
    axes[0].set_title("Same finite upstream materials")
    for offset, key, label in ((-.18,"bed_rise_at_least_1mm_area_m2",">=1 mm"),(.18,"bed_rise_at_least_1cm_area_m2",">=1 cm")):
        axes[1].bar(x+offset, [r["constructed_dry_land"][key] for r in records], width=.36,label=label)
    axes[1].set_ylabel("Area on initially constructed dry land (m2)"); axes[1].legend()
    axes[1].set_title("Actual land-side deposition")
    for ax in axes:
        ax.set_xticks(x, [format(r["discharge_scale"],"g")+"x" for r in records]); ax.set_xlabel("Upstream discharge scale")
    fig.tight_layout(); fig.savefig(output/"comparison.png",dpi=160); plt.close(fig)
    return comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scene", type=Path, default=SCENE)
    parser.add_argument("--discharge-scale", type=positive_discharge_scale, default=1.)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--compare-sweep", type=Path)
    args = parser.parse_args(argv)
    if args.audit:
        print(json.dumps(audit(args.audit), indent=2))
        return 0
    if args.compare_sweep:
        print(json.dumps(compare_discharge_cases(args.compare_sweep), indent=2))
        return 0
    if args.scene.resolve() != SCENE.resolve() and args.output is None:
        parser.error("--output is required for an independent --scene")
    output = args.output or (DEFAULT_OUTPUT if args.discharge_scale == 1. else
        ROOT/"verification/fluvial-delta/discharge-sweep-20261017"/("q"+format(args.discharge_scale,"g")))
    print(json.dumps(run(output, args.discharge_scale, args.scene), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

