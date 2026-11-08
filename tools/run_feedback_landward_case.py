"""Saved-source sequential channel feedback and connected coastal-land deposition."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import load_daily_sediment, route_daily_sediment, save_daily_sediment
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import route_feedback_daily
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval, simulate_fluvial_delta
from tools.prepare_upstream_sediment_supply import CENTER, SUPPLY, DETAIL
from tools.verify_fluvial_channel_remobilization import resource_limits

SOURCE = ROOT / "verification/upstream-sediment/same-source-20261016-04"
DEFAULT_OUTPUT = ROOT / "verification/fluvial-delta/same-source-feedback-landward-20261016-02"


def monthly_sum(daily, starts, ends, monthly_starts, monthly_ends):
    result = []
    covered = np.zeros(starts.shape, np.int64)
    for start, end in zip(monthly_starts, monthly_ends):
        mask = (starts >= start) & (ends <= end)
        covered += mask
        result.append(float(np.sum(daily[mask])))
    if np.any(covered != 1) or not np.isclose(sum(result), np.sum(daily), rtol=1e-12, atol=1e-8):
        raise ValueError("monthly intervals must partition exact daily boundaries")
    return np.array(result)


def cut_source(bundle, node_xz_m, count):
    a, m = bundle["arrays"], bundle["metadata"]
    receiver = a["receiver"][:count].copy()
    receiver[-1] = -1
    edge_lengths = np.linalg.norm(np.diff(node_xz_m[:count], axis=0), axis=1)
    lengths = np.r_[edge_lengths[0]*.5, (edge_lengths[:-1]+edge_lengths[1:])*.5, edge_lengths[-1]*.5]
    area = lengths*a["width_m"][:count]
    alluvium = a["initial_alluvium_bulk_m3"][:count] / a["area_m2"][:count] * area
    return route_daily_sediment(
        receiver=receiver, length_m=lengths, width_m=a["width_m"][:count],
        bed_elevation_m=a["bed_elevation_m"][:count], water_depth_m=a["water_depth_m"][:, :count],
        water_q_m3_s=a["water_q_m3_s"][:, :count], friction_slope=a["friction_slope"][:, :count],
        time_seconds=a["time_seconds"], rock_floor_m=a["rock_floor_m"][:count],
        initial_alluvium_bulk_m3=alluvium, hardness=a["hardness_source"][:count],
        initial_mobile_solid_m3=a["initial_mobile_solid_m3"][:count],
        external_solid_m3_s=a["external_solid_m3_s"][:, :count], retention_fraction=a["retention_fraction"][:count],
        material=MaterialParameters(**m["material"]), material_provenance=m["material_provenance"],
        geometry_identity_sha256=identity({"receiver": receiver, "bed": a["bed_elevation_m"][:count], "length_m": lengths, "node_xz_m": node_xz_m[:count]},
                                         {"source": m["geometry_identity_sha256"], "prefix_count": count}),
        hydraulic_identity_sha256=m["hydraulic_identity_sha256"])


def wet_diagnostics(result, boundary, area):
    """Head-bounded wet-connectivity proxy, explicitly not solved inundation."""
    land = result["initial_bed_m"] > boundary.sea_level_m
    wet = []
    depths = []
    bed = result["initial_bed_m"].copy()
    porosity = result["metadata"]["config"]["porosity"]
    for record in result["intervals"]:
        flowing = record["water_throughput_m3"] > 0.
        depth = np.where(flowing, np.maximum(0., boundary.river_head_m - bed), 0.)
        wet.append(flowing & (depth > 0.))
        depths.append(depth)
        bed += (record["deposited_solid_m3"] - record["reentrained_solid_m3"]) / ((1. - porosity) * area)
    wet = np.asarray(wet)
    return {"head_bounded_water_depth_proxy_m": np.asarray(depths), "wet_connected_mask": wet,
            "initial_land_mask": land,
            "new_inundation_proxy_mask": land & np.any(wet[1:] & ~wet[0], axis=0),
            "wetland_candidate_mask": land & wet[-1] & (np.asarray(depths)[-1] <= 2.),
            "emergent_mask": (result["initial_bed_m"] <= 0.) & (result["final_bed_m"] > 0.),
            "subaqueous_deposition_mask": (result["final_bed_m"] <= 0.) & (result["stored_solid_m3"] > 0.)}


def archive_mouth(path, result, terrain, boundary, diagnostics, times):
    arrays = {name: result[name] for name in ("initial_bed_m", "final_bed_m", "height_delta_m", "deposited_solid_m3", "stored_solid_m3")}
    arrays.update(diagnostics)
    arrays.update({"monthly_time_seconds": times, "monthly_deposited_solid_m3": np.asarray([r["deposited_solid_m3"] for r in result["intervals"]]),
                   "monthly_reentrained_solid_m3": np.asarray([r["reentrained_solid_m3"] for r in result["intervals"]]),
                   "monthly_stored_solid_m3": np.asarray([r["stored_solid_m3"] for r in result["intervals"]]),
                   "monthly_ledgers_json": np.array(json.dumps([{k: r[k] for k in ("water_ledger", "solid_ledger")} for r in result["intervals"]])),
                   "global_ledgers_json": np.array(json.dumps({k: result[k] for k in ("water_ledger", "solid_ledger")})),
                   "monthly_water_throughput_m3": np.asarray([r["water_throughput_m3"] for r in result["intervals"]]),
                   "ocean_mask": boundary.initial_ocean_mask, "export_mask": boundary.ocean_export_mask,
                   "origin_xz_m": np.array([terrain.x0_m, terrain.z0_m]), "spacing_m": np.array(terrain.dx_m),
                   "metadata_json": np.array(json.dumps(result["metadata"]))})
    np.savez_compressed(path, **arrays)


def render(output, feedback, terrain, result, diagnostic, monthly, supply):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    a = feedback["arrays"]
    inlet_row, inlet_col = result["metadata"]["forcing"][0]["inlet_cell"]
    extent = [(-inlet_col-.5)*terrain.dx_m/1000., (terrain.elevation_m.shape[1]-inlet_col-.5)*terrain.dx_m/1000.,
              (terrain.elevation_m.shape[0]-inlet_row-.5)*terrain.dz_m/1000., (-inlet_row-.5)*terrain.dz_m/1000.]
    fig, axes = plt.subplots(2, 3, figsize=(17, 10))
    initial, final = result["initial_bed_m"], result["final_bed_m"]
    for ax, bed, title in zip(axes[0, :2], (initial, final), ("Actual initial derived terrain", "After supplied-sediment routing")):
        image = ax.imshow(bed, extent=extent, cmap="terrain", vmin=-20, vmax=20)
        ax.contour(bed, levels=[0], colors="black", linewidths=.8, extent=extent, origin="upper")
        ax.set_title(title)
    fig.colorbar(image, ax=axes[0, :2].tolist(), label="Bed elevation (m)", shrink=.75)
    delta = axes[1, 0].imshow(result["height_delta_m"], extent=extent, cmap="viridis", vmin=0)
    axes[1, 0].contour(initial, levels=[0], colors="white", linewidths=.8, extent=extent, origin="upper")
    axes[1, 0].set_title("Deposition; white = initial coastline")
    fig.colorbar(delta, ax=axes[1, 0], label="Bed rise (m)")
    axes[1, 1].imshow(np.where(diagnostic["initial_land_mask"], result["stored_solid_m3"], np.nan), extent=extent, cmap="magma")
    axes[1, 1].contour(initial, levels=[0], colors="black", linewidths=.8, extent=extent, origin="upper")
    axes[1, 1].set_title("Solid sediment retained on original land (m3/cell)")
    axes[1, 1].set_xlim(-.15, .35)
    axes[1, 1].set_ylim(.35, -.15)
    for ax, values, title, cmap in ((axes[0, 2], final, "Coastal detail: final bed", "terrain"),
                                   (axes[1, 2], result["height_delta_m"], "Coastal detail: bed rise", "viridis")):
        ax.imshow(values, extent=extent, cmap=cmap)
        ax.contour(initial, levels=[0], colors="white", linewidths=1., extent=extent, origin="upper")
        ax.contour(final, levels=[0], colors="black", linewidths=.7, extent=extent, origin="upper")
        ax.set_xlim(-.3, .7)
        ax.set_ylim(.7, -.3)
        ax.set_title(title)
    for ax in axes.flat:
        ax.plot(0., 0., marker="x", color="red", markersize=7)
        ax.set_xlabel("East from land inlet (km)")
        ax.set_ylabel("South from land inlet (km)")
    fig.savefig(output / "coastal-before-after.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    days = a["time_seconds"] / 86400.
    axes[0].plot(days[:-1], a["water_q_m3_s"][:, -1], color="royalblue", label="Water Q")
    twin = axes[0].twinx()
    twin.plot(days[:-1], a["qs_solid_m3_s"][:, -1], color="firebrick", label="Solid Qs")
    axes[0].set_ylabel("Water m3/s")
    twin.set_ylabel("Solid m3/s")
    axes[1].plot(days, a["trace_bed_m"][:, [0, len(a["receiver"])//2, -1]])
    axes[1].set_ylabel("Channel bed m")
    axes[1].legend(["Upstream", "Middle", "Coastal cut"])
    axes[2].imshow(a["trace_bed_m"] - a["trace_bed_m"][0], aspect="auto", origin="lower", extent=[0, len(a["receiver"])-1, 0, days[-1]], cmap="coolwarm")
    axes[2].set_ylabel("Day")
    axes[2].set_xlabel("Channel node; color = bed change (m)")
    fig.tight_layout()
    fig.savefig(output / "daily-water-sediment-bed.png", dpi=150)
    plt.close(fig)


def audit(output):
    """Cold replay uses saved source, complete forcing, geometry and inventory."""
    resource_limits()
    output = Path(output)
    prefix = load_daily_sediment(output/"cut_frozen_source.npz", file_sha256(output/"cut_frozen_source.npz"))
    feedback = load_daily_sediment(output/"feedback_bundle.npz", file_sha256(output/"feedback_bundle.npz"))
    replay = route_feedback_daily(prefix, feedback["arrays"]["node_xz_m"])
    if replay["identity_sha256"] != feedback["identity_sha256"]:
        raise ValueError("cold sequential feedback replay mismatch")
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    with np.load(output/"mouth.npz") as mouth:
        meta = json.loads(mouth["metadata_json"].item())
        initial = mouth["initial_bed_m"].copy()
        origin = mouth["origin_xz_m"]
        spacing = float(mouth["spacing_m"])
        terrain = TerrainGrid(initial, np.ones(initial.shape, bool), float(origin[0]), float(origin[1]), spacing, spacing,
                              "diagnostic_dem_proxy", "same-saved-detail-coastal-cut", summary["source_hashes_before"]["detail"], source_path=str(DETAIL))
        boundary = FluvialDeltaBoundary(mouth["ocean_mask"], mouth["export_mask"], meta["sea_level_m"], meta["river_head_m"], meta["boundary_source_id"])
        forcing = [FluvialDeltaInterval(tuple(f["inlet_cell"]), f["water_volume_m3"], f["sediment_solid_m3"]) for f in meta["forcing"]]
        result = simulate_fluvial_delta(terrain, boundary, forcing, FluvialDeltaConfig(**meta["config"]))
        for name in ("final_bed_m", "stored_solid_m3", "deposited_solid_m3"):
            if not np.array_equal(result[name], mouth[name]):
                raise ValueError("cold mouth replay mismatch: " + name)
        for field in ("deposited_solid_m3", "reentrained_solid_m3", "stored_solid_m3"):
            if not np.array_equal(np.asarray([r[field] for r in result["intervals"]]), mouth["monthly_"+field]):
                raise ValueError("cold monthly mouth inventory mismatch: " + field)
        ledgers = [{k: r[k] for k in ("water_ledger", "solid_ledger")} for r in result["intervals"]]
        if ledgers != json.loads(mouth["monthly_ledgers_json"].item()):
            raise ValueError("cold monthly mouth ledgers mismatch")
    if result["solid_ledger"] != summary["mouth_solid_ledger"]:
        raise ValueError("cold mouth ledger mismatch")
    return {"cold_feedback_identity_match": True, "cold_mouth_arrays_exact_match": True,
            "cold_mouth_ledger_match": True, "feedback_identity_sha256": replay["identity_sha256"]}


def render_saved(output):
    output = Path(output)
    feedback = load_daily_sediment(output/"feedback_bundle.npz", file_sha256(output/"feedback_bundle.npz"))
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    with np.load(output/"mouth.npz") as archive:
        result = {key: archive[key].copy() for key in ("initial_bed_m", "final_bed_m", "height_delta_m", "stored_solid_m3")}
        result["metadata"] = json.loads(archive["metadata_json"].item())
        diagnostic = {"initial_land_mask": archive["initial_land_mask"].copy()}
        origin = archive["origin_xz_m"]
        spacing = float(archive["spacing_m"])
    terrain = TerrainGrid(result["initial_bed_m"], np.ones(result["initial_bed_m"].shape, bool), float(origin[0]), float(origin[1]), spacing, spacing,
                          "diagnostic_dem_proxy", "same-saved-detail-coastal-cut", summary["source_hashes_before"]["detail"], source_path=str(DETAIL))
    render(output, feedback, terrain, result, diagnostic, None, None)
    return {"rendered": str(output)}


def run(output=DEFAULT_OUTPUT):
    resource_limits()
    output = Path(output)
    tracked = {"frozen_bundle": SOURCE/"upstream_bundle.npz", "geometry": SOURCE/"geometry.npz",
               "centerline": CENTER, "seasonal_supply": SUPPLY, "detail": DETAIL}
    hashes = {name: file_sha256(path) for name, path in tracked.items()}
    bundle = load_daily_sediment(tracked["frozen_bundle"], hashes["frozen_bundle"])
    with np.load(tracked["geometry"]) as g, np.load(DETAIL) as d, np.load(SUPPLY) as s:
        xz = g["node_xz_m"].copy()
        dm = json.loads(d["metadata_json"].item())
        spacing = float(dm["spacing_m"])
        origin = np.asarray(dm["origin_xz_m"])
        cells = np.rint((xz - origin) / spacing).astype(int)
        heights = d["derived_height_m"][cells[:, 1], cells[:, 0]]
        land_nodes = np.flatnonzero((heights > 0.) & ~d["ocean_mask"][cells[:, 1], cells[:, 0]])
        cut = int(land_nodes[-1])
        prefix = cut_source(bundle, xz, cut + 1)
        feedback = route_feedback_daily(prefix, xz[:cut+1])
        a = feedback["arrays"]
        starts, ends = a["time_seconds"][:-1], a["time_seconds"][1:]
        dt = ends-starts
        monthly_starts, monthly_ends = s["monthly_start_s"].copy(), s["monthly_end_s"].copy()
        monthly = monthly_sum(a["exported_solid_m3"].sum(axis=1), starts, ends, monthly_starts, monthly_ends)
        water = monthly_sum(a["water_q_m3_s"][:, -1]*dt, starts, ends, monthly_starts, monthly_ends)
        row, col = int(cells[cut, 1]), int(cells[cut, 0])
        r0, c0, size = row-32, col-32, 96
        crop = d["derived_height_m"][r0:r0+size, c0:c0+size].copy()
        ocean = d["ocean_mask"][r0:r0+size, c0:c0+size].copy()
    terrain = TerrainGrid(crop, np.ones(crop.shape, bool), float(origin[0]+c0*spacing), float(origin[1]+r0*spacing), spacing, spacing,
                          "diagnostic_dem_proxy", "same-saved-detail-coastal-cut", hashes["detail"], source_path=str(DETAIL))
    exports = np.zeros(crop.shape, bool)
    exports[0] = ocean[0]
    exports[-1] = ocean[-1]
    exports[:, 0] |= ocean[:, 0]
    exports[:, -1] |= ocean[:, -1]
    inlet = (row-r0, col-c0)
    head = float(crop[inlet] + a["water_depth_m"][:, -1].max())
    boundary = FluvialDeltaBoundary(ocean, exports, 0., head, "same-detail-local-bed-plus-peak-normal-depth")
    config = FluvialDeltaConfig(capacity_solid_per_water=.0001, routing_relief_scale_m=.5,
                               max_deposit_depth_per_interval_m=.25, max_reentrainment_depth_per_interval_m=.03)
    forcing = [FluvialDeltaInterval(inlet, float(w), float(v)) for w, v in zip(water, monthly)]
    result = simulate_fluvial_delta(terrain, boundary, forcing, config)
    control = simulate_fluvial_delta(terrain, boundary, [FluvialDeltaInterval(inlet, float(w), 0.) for w in water], config)
    if not np.array_equal(control["final_bed_m"], crop):
        raise ValueError("zero-solid matched-water control altered terrain")
    diagnostic = wet_diagnostics(result, boundary, terrain.cell_area_m2)
    solid_input = float(monthly.sum())
    if not np.isclose(solid_input, result["solid_ledger"]["input_solid_m3"], rtol=1e-12, atol=1e-8):
        raise ValueError("handoff sediment mismatch")
    combined_residual = (float(a["initial_alluvium_bulk_m3"].sum()*(1.-feedback["metadata"]["material"]["porosity"]) + a["initial_mobile_solid_m3"].sum()
                               + a["external_solid_m3"].sum() + a["eroded_rock_m3"].sum())
                         - float(a["trace_loose_solid_m3"][-1].sum() + a["trace_mobile_solid_m3"][-1].sum())
                         - result["solid_ledger"]["stored_solid_m3"] - result["solid_ledger"]["ocean_export_solid_m3"] - result["solid_ledger"]["unresolved_solid_m3"])
    if abs(combined_residual) > 1e-7:
        raise ValueError("combined sediment ledger mismatch")
    if hashes != {name: file_sha256(path) for name, path in tracked.items()}:
        raise ValueError("source artifact changed during run")
    output.mkdir(parents=True, exist_ok=False)
    save_daily_sediment(output/"feedback_bundle.npz", feedback)
    cold = load_daily_sediment(output/"feedback_bundle.npz", file_sha256(output/"feedback_bundle.npz"))
    replay = route_feedback_daily(prefix, xz[:cut+1])
    if cold["identity_sha256"] != replay["identity_sha256"]:
        raise ValueError("feedback cold-load/replay identity mismatch")
    save_daily_sediment(output/"cut_frozen_source.npz", prefix)
    np.savez_compressed(output/"geometry-material-daily.npz", node_xz_m=xz[:cut+1], rock_floor_m=a["rock_floor_m"], hardness=a["hardness_source"],
                        daily_time_seconds=a["time_seconds"], daily_water_q_m3_s=a["water_q_m3_s"][:, -1], daily_terminal_solid_m3=a["exported_solid_m3"].sum(axis=1),
                        monthly_start_s=monthly_starts, monthly_end_s=monthly_ends, monthly_solid_m3=monthly, monthly_water_m3=water)
    times = np.r_[monthly_starts, monthly_ends[-1]]
    archive_mouth(output/"mouth.npz", result, terrain, boundary, diagnostic, times)
    archive_mouth(output/"zero-solid-control.npz", control, terrain, boundary, wet_diagnostics(control, boundary, terrain.cell_area_m2), times)
    land = diagnostic["initial_land_mask"]
    report = {"schema": "sequential-feedback-coastal-land-v1", "days": len(dt), "mouth_intervals": len(forcing),
              "cut_source_node": cut, "source_node_count": len(bundle["arrays"]["receiver"]), "modeled_upstream_nodes": cut+1,
              "cut_xz_m": xz[cut].tolist(), "cut_grid_row_column": [row, col], "inlet_is_original_land": bool(crop[inlet]>0),
              "channel_length_m": float(np.linalg.norm(np.diff(xz[:cut+1], axis=0), axis=1).sum()),
              "channel_control_length_sum_m": float(a["length_m"].sum()),
              "landward_reach_to_original_mouth_m": float(np.linalg.norm(xz[-1]-xz[cut])),
              "cut_profile_bed_m": float(a["bed_elevation_m"][-1]), "cut_grid_bed_m": float(crop[inlet]),
              "interface_bed_difference_m": float(crop[inlet]-a["bed_elevation_m"][-1]), "river_head_ceiling_m": head,
              "handoff_solid_m3": solid_input, "mouth_water_ledger": result["water_ledger"], "mouth_solid_ledger": result["solid_ledger"],
              "channel_global_residual_m3": feedback["metadata"]["global_residual"], "combined_residual_solid_m3": combined_residual,
              "original_land_deposited_area_m2": float(np.count_nonzero(land & (result["stored_solid_m3"]>1e-9))*terrain.cell_area_m2),
              "original_land_stored_solid_m3": float(result["stored_solid_m3"][land].sum()),
              "emergent_area_m2": float(diagnostic["emergent_mask"].sum()*terrain.cell_area_m2),
              "subaqueous_deposition_area_m2": float(diagnostic["subaqueous_deposition_mask"].sum()*terrain.cell_area_m2),
              "new_inundation_proxy_area_m2": float(diagnostic["new_inundation_proxy_mask"].sum()*terrain.cell_area_m2),
              "wetland_candidate_area_m2": float(diagnostic["wetland_candidate_mask"].sum()*terrain.cell_area_m2),
              "inundation_semantics": "head-ceiling-minus-current-bed proxy only on flowing ocean-connected DAG cells; not solved water surface or certified wetland",
              "material_provenance": "saved declared scenario: 5cm initial loose cover, 1m finite intact rock, spatial procedural hardness; retained original MaterialParameters",
              "no_double_spend": "source nodes downstream of cut omitted; exact exported solid is mouth input; mouth erodes only its own earlier deposits",
              "control_same_water_zero_solid_unchanged": True, "source_hashes_before": hashes,
              "source_hashes_after": {name: file_sha256(path) for name, path in tracked.items()},
              "feedback_identity_sha256": feedback["identity_sha256"], "cold_load_and_replay_identity_match": True,
              "config": result["metadata"], "monthly_solid_m3": monthly.tolist(),
              "dynamic_upstream": True, "transient_hydraulics": False, "backwater_feedback": False,
              "naturalness_verified": False, "hydraulic_ready": False, "publishable": False,
              "resource_policy": "single process, 2 CPU cores, BelowNormal, numerical threads1; no GPU/game"}
    render(output, feedback, terrain, result, diagnostic, monthly, None)
    (output/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--render", type=Path)
    args = parser.parse_args()
    print(json.dumps(render_saved(args.render) if args.render else audit(args.audit) if args.audit else run(args.output), indent=2))
