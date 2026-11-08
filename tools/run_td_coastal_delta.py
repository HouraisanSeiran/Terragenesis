"""Fixed independent coastal experiment and bit-exact cold replay entry point."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_coastal_transport import (
    CoastalConfig, channel_water_stage, derived_construction, foreshore_outflow, run_coastal_transport,
)
from tools.verify_fluvial_channel_remobilization import resource_limits

SCENE = ROOT/".scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-15/scene.npz"
ANNUAL = ROOT/"verification/fluvial-delta/adaptive-tree-16km-20261018-02/result.npz"
OUTPUT = ROOT/"verification/fluvial-delta/td-coastal-delta-20261018-02"
MODULE = ROOT/"terrain_pipeline/surface_rivers/metric_coastal_transport.py"


def inputs():
    with np.load(SCENE) as source, np.load(ANNUAL) as annual:
        scene = {key: source[key] for key in source.files}
        year = {key: annual[key] for key in annual.files}
    if not np.array_equal(scene["bed_m"], year["initial_bed_m"]):
        raise ValueError("annual run did not originate on frozen scene15")
    metadata = json.loads(str(scene["metadata_json"]))
    origin = np.asarray(metadata["origin_xz_m"])
    spacing = float(metadata["spacing_m"])
    terminals = year["branch_paths_xz_m"][:, -1]
    cells = np.floor((terminals-origin)/spacing+.5).astype(int)[:, ::-1]
    channels = scene["channel_mask"] | scene["main_section_mask"]
    protected = scene["retained_upstream_raster_mask"] | channels
    initial, construction, weight = derived_construction(year["final_bed_m"], .35*scene["td_residual_m"],
        channels, scene["retained_upstream_raster_mask"], spacing)
    return scene, year, initial, construction, weight, protected, cells, spacing


def calculate():
    scene, year, initial, construction, weight, protected, cells, spacing = inputs()
    scene_metadata = json.loads(str(scene["metadata_json"]))
    td_sources = [(Path(path), digest) for path, digest in scene_metadata["input_hashes"].items()
        if Path(path).name == "native-routing.npz"]
    if len(td_sources) != 1 or file_sha256(td_sources[0][0]) != td_sources[0][1]:
        raise ValueError("native TD source identity missing or changed")
    native_td, native_td_hash = td_sources[0]
    supply = year["monthly_terminal_export_solid_m3"]
    config = CoastalConfig()
    cases = {}
    for name, tide, wave in (("combined", True, True), ("zero_forcing", False, False),
                              ("tide_only", True, False), ("wave_only", False, True)):
        cases[name] = run_coastal_transport(initial, protected, cells, supply, spacing, config,
            tides=tide, waves=wave, month_seconds=year["month_seconds"])
    # No supply/no forcing is a stricter immobility check, in addition to same-supply control.
    null = run_coastal_transport(initial, protected, cells, np.zeros_like(supply), spacing,
        config, tides=False, waves=False, month_seconds=year["month_seconds"])
    if not np.array_equal(initial, null["bed_m"]):
        raise AssertionError("zero forcing plus zero supply altered terrain")
    arrays = {"source_scene_bed_m": scene["bed_m"], "annual_bed_m": year["final_bed_m"],
        "initial_bed_m": initial, "construction_height_delta_m": construction,
        "construction_weight": weight, "protected_mask": protected,
        "terminal_cells_zx": cells, "branch_paths_xz_m": year["branch_paths_xz_m"],
        "trunk_path_xz_m": year["trunk_path_xz_m"],
        "terminal_parent_index": year["terminal_parent_index"], "terminal_level": year["terminal_level"],
        "monthly_terminal_export_solid_m3": supply, "monthly_branch_q_m3_s": year["monthly_branch_q_m3_s"],
        "month_seconds": year["month_seconds"], "origin_xz_m": year["origin_xz_m"],
        "spacing_m": np.asarray(spacing), "td_residual_m": scene["td_residual_m"]}
    arrays["annual_water_depth_m"] = year["water_depth_m"]
    for name, result in cases.items():
        arrays.update({name+"__"+key: value for key, value in result.items() if isinstance(value, np.ndarray)})
    # Actual water combines dynamic connected sea with the saved river stages,
    # recomputing wetness against the saved final bed rather than reusing a mask.
    connectivity = {}
    from scipy.ndimage import distance_transform_edt, label
    terminal_flows = year["monthly_branch_q_m3_s"][-1]
    paths = [scene["designed_incoming_path_xz_m"], year["trunk_path_xz_m"], *year["branch_paths_xz_m"]]
    sections = [scene["main_section_mask"], scene["trunk_section_mask"], *scene["branch_section_masks"]]
    widths = [scene["incoming_width_profile_m"], scene["trunk_width_profile_m"], *scene["branch_width_profile_m"]]
    # Branch 1 is a child of branch 0; its discharge also traverses the parent.
    reach_flows = [np.full(len(path), terminal_flows[i]) for i, path in enumerate(year["branch_paths_xz_m"])]
    parents = year["terminal_parent_index"]
    for child in np.argsort(year["terminal_level"])[::-1]:
        if parents[child] >= 0:
            parent = int(parents[child])
            parent_path = year["branch_paths_xz_m"][parent]
            junction = int(np.argmin(np.linalg.norm(parent_path-year["branch_paths_xz_m"][child, 0], axis=1)))
            reach_flows[parent][:junction+1] += float(reach_flows[child][0])
    flows = [float(terminal_flows.sum()), float(terminal_flows.sum()), *reach_flows]
    for name, result in cases.items():
        bed = result["bed_m"]
        case_connectivity = {}
        for phase, level, sea_key in (("", 0., "wet_mask"),
            ("high_tide_", CoastalConfig().tide_amplitude_m if name in ("combined", "tide_only") else 0., "high_tide_wet_mask"),
            ("low_tide_", -CoastalConfig().tide_amplitude_m if name in ("combined", "tide_only") else 0., "low_tide_wet_mask")):
            sea = result[sea_key]
            surface = np.where(sea, level, np.nan)
            stage, hydraulic_diagnostics = channel_water_stage(bed, paths, sections, widths, flows,
                year["origin_xz_m"], spacing, level)
            stage, outflow_routes, outflow_states = foreshore_outflow(bed, sea, stage, cells,
                terminal_flows, scene["branch_width_profile_m"][:, -1], spacing, max_distance_m=2400.)
            # Communicate the foreshore sill tailwater back into the existing
            # river stage envelope; no discontinuous head step at the fixed gate.
            outlets = [level, level]+[max(level, item.get("gate_stage_m", level)) for item in outflow_states]
            for _ in range(int(np.max(year["terminal_level"]))+3):
                rebuilt, hydraulic_diagnostics = channel_water_stage(bed, paths, sections, widths, flows,
                    year["origin_xz_m"], spacing, level, outlets)
                for child, parent in enumerate(parents):
                    source_head = hydraulic_diagnostics[child+2]["source_stage_m"]
                    if parent >= 0:
                        outlets[parent+2] = max(outlets[parent+2], source_head)
                    else:
                        outlets[1] = max(outlets[1], source_head)
                outlets[0] = max(outlets[0], hydraulic_diagnostics[1]["source_stage_m"])
            rebuilt, hydraulic_diagnostics = channel_water_stage(bed, paths, sections, widths, flows,
                year["origin_xz_m"], spacing, level, outlets)
            stage = np.fmax(stage, rebuilt)
            for terminal, route in enumerate(outflow_routes):
                arrays[name+"__"+phase+"foreshore_path_"+str(terminal)+"_zx"] = route
            river = np.isfinite(stage) & (stage > bed)
            surface[river] = np.maximum(stage[river], np.where(sea[river], level, -np.inf))
            wet = np.isfinite(surface)
            arrays[name+"__"+phase+"actual_water_surface_m"] = surface
            arrays[name+"__"+phase+"actual_water_depth_m"] = np.where(wet, np.maximum(surface-bed, 0.), 0.)
            arrays[name+"__"+phase+"actual_wet_mask"] = wet
            points = np.concatenate([scene["designed_incoming_path_xz_m"][:1], year["apex_xz_m"][None, :],
                year["branch_paths_xz_m"][:, -1]], axis=0)
            point_cells = np.floor((points-year["origin_xz_m"])/spacing+.5).astype(int)
            metrics = {}
            for neighborhood, structure in (("D4", None), ("D8", np.ones((3, 3)))):
                components, _ = label(wet, structure=structure)
                ids = components[point_cells[:, 1], point_cells[:, 0]]
                metrics[neighborhood] = {"incoming_apex_all_terminals_connected": bool(np.all(ids == ids[0]) and ids[0] > 0),
                    "component_ids": ids.tolist(),
                    "incoming_component_reaches_connected_sea": bool(ids[0] > 0 and np.any(components[sea] == ids[0]))}
            metrics["sample_depths_m"] = arrays[name+"__"+phase+"actual_water_depth_m"][point_cells[:, 1], point_cells[:, 0]].tolist()
            metrics["reach_hydraulics"] = hydraulic_diagnostics
            metrics["foreshore_surface_outflow"] = outflow_states
            sea_labels, _ = label(sea)
            ocean_distance = distance_transform_edt(~sea)*spacing
            metrics["terminal_to_connected_sea_distance_m"] = ocean_distance[cells[:, 0], cells[:, 1]].tolist()
            metrics["terminals_in_connected_sea"] = sea[cells[:, 0], cells[:, 1]].tolist()
            case_connectivity[phase or "mean"] = metrics
        connectivity[name] = case_connectivity
    annual_summary = json.loads(ANNUAL.with_name("summary.json").read_text(encoding="utf-8"))
    ledgers = {name: result["ledger"] for name, result in cases.items()}
    upstream = annual_summary["solid_ledger"]
    combined = ledgers["combined"]
    summary = {"schema": "td-coastal-delta-finite-layer-water-v2",
        "algorithm": "phase-connected coastal finite-layer donor-capped face transport v1",
        "water_algorithm": "preserved discharge tree Manning/critical stage envelope plus finite foreshore surface outflow v2",
        "terrain_identity": "TD detail coordinated with frozen macro land/sea; not native TD coastline",
        "base_formula": json.loads(str(scene["metadata_json"])).get("base_formula"),
        "coordinates": "arrays [south-row,east-column]; meters; origin cell center; sea datum 0 m",
        "config": cases["combined"]["config"],
        "source_paths": {"scene15": str(SCENE), "annual": str(ANNUAL),
            "annual_summary": str(ANNUAL.with_name("summary.json")), "native_td": str(native_td)},
        "source_hashes": {"scene15": file_sha256(SCENE), "annual": file_sha256(ANNUAL),
            "annual_summary": file_sha256(ANNUAL.with_name("summary.json")), "native_td": native_td_hash},
        "implementation_hashes": {str(MODULE.relative_to(ROOT)): file_sha256(MODULE),
            str(Path(__file__).relative_to(ROOT)): file_sha256(Path(__file__)),
            "terrain_pipeline/surface_rivers/metric_dynamic_feedback.py": file_sha256(ROOT/"terrain_pipeline/surface_rivers/metric_dynamic_feedback.py")},
        "frozen_scene_metadata": json.loads(str(scene["metadata_json"])),
        "construction": {"role": "explicit geometric cut/fill, never financed by river sediment",
            "method": "550 m Gaussian of annual bed minus existing 0.35*TD residual, including inherited fan support; residual retained without duplication; smooth distance exclusion around river/upstream and outer boundary; cut/fill is explicit construction",
            "cut_bulk_m3": float(np.maximum(-construction, 0.).sum()*spacing**2),
            "fill_bulk_m3": float(np.maximum(construction, 0.).sum()*spacing**2),
            "maximum_cut_m": float(-construction.min()), "maximum_fill_m": float(construction.max()),
            "original_scene_construction_cut_bulk_m3": float(np.maximum(scene["base_bed_m"]-scene["bed_m"], 0.).sum()*spacing**2),
            "original_scene_construction_fill_bulk_m3": float(np.maximum(scene["bed_m"]-scene["base_bed_m"], 0.).sum()*spacing**2)},
        "ledgers": ledgers,
        "geological_inventory_assumption": "all cases share the same hypothetical 0.30 m active cover times activity taper and 0.65 solid fraction; this is a finite pre-existing geological store, not annual river production",
        "actual_water_connectivity": connectivity,
        "combined_source_to_sea_ledger": {
            "annual_upstream_input_solid_m3": upstream["input_solid_m3"],
            "annual_land_retained_solid_m3": upstream["retained_solid_m3"],
            "coastal_initial_geological_solid_m3": combined["initial_geological_mobile_solid_m3"],
            "coastal_final_mobile_solid_m3": combined["final_mobile_solid_m3"],
            "offshore_export_solid_m3": combined["offshore_export_solid_m3"],
            "pending_coastal_solid_m3": combined["pending_terminal_solid_m3"]},
        "phase_history_columns": ["month0", "phase0", "sea_level_m", "connected_area_m2", "marine_water_volume_m3",
            "mobile_solid_m3", "cumulative_offshore_export_m3", "pending_solid_m3", "absolute_mobile_change_m3",
            "net_ocean_water_exchange_m3", "represented_calendar_start_s", "representative_cycle_phase_s",
            "represented_tidal_cycles_per_month", "represented_phase_duration_s"],
        "time_interpretation": "one representative 8-phase tidal cycle per month, monthly sediment apportioned equally across phases; fixed per-phase monthly morphological fractions; calendar duration/cycle weights recorded, not calibrated or fully resolved annual tide simulation",
        "river_water_forcing": "saved final-month positive discharge, existing variable-width rectangular sections, actual centerline bed grade and Manning normal depth with critical free-outfall lower control; upstream monotone stage envelope and prescribed tidal sea boundary; reduced quasi-steady stage reconstruction, not solved backwater",
        "low_tide_outfall_policy": "fixed first-mean-sea gates, unchanged bed; beyond gates a bounded 2400 m D4 minimax-sill path follows existing foreshore to the first connected sea cell. Water-only critical-depth surface drainage uses saved discharge and actual one-cell effective width (20 m), consistent with water prism accounting; path, sill, sea contact, Q and replacement seconds recorded. Foreshore sill tailwater is propagated upstream through the existing river stage envelopes. This is an uncalibrated surface outflow closure, not channel excavation or a 2-D momentum solution.",
        "control_semantics": "all four cases receive only saved annual terminal exports; zero forcing includes river deposition; null no-supply/no-forcing is exactly immobile",
        "protection": "river channel tree, retained upstream, and outer taper fixed; no river channel extension past saved first-marine gates",
        "limits": ["reduced coastal transport, not a 2-D momentum solver", "no tidal propagation lag or calibrated storm chronology",
            "macro smoothing is local derived construction; neighboring tile continuity not certified",
            "geological active layer is an explicitly assumed finite local inventory, not newly produced river sand"],
        "zero_supply_zero_forcing_exact": True,
        "max_protected_bed_change_m": float(np.max(np.abs(cases["combined"]["bed_m"][protected]-year["final_bed_m"][protected]))),
        "tidal_intertidal_area_m2": float(np.count_nonzero(cases["combined"]["high_tide_wet_mask"] &
            ~cases["combined"]["low_tide_wet_mask"])*spacing**2),
        "cold_replay_command": "runtime/venv/Scripts/python.exe tools/run_td_coastal_delta.py --audit"}
    summary["combined_source_to_sea_ledger"]["residual_solid_m3"] = (
        upstream["input_solid_m3"]+combined["initial_geological_mobile_solid_m3"]
        -upstream["retained_solid_m3"]-upstream["escrow_solid_m3"]
        -combined["final_mobile_solid_m3"]-combined["offshore_export_solid_m3"]
        -combined["pending_terminal_solid_m3"])
    return arrays, summary


def render(output, a):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource, LinearSegmentedColormap, TwoSlopeNorm
    spacing = float(a["spacing_m"])
    extent = [0., 16., 16., 0.]
    land = LinearSegmentedColormap.from_list("coastal_land", ["#b8c49a", "#78a47b", "#5e806c", "#aaaa99", "#e3dfd3"])
    water_palette = LinearSegmentedColormap.from_list("coastal_water", ["#65c6df", "#318fbc", "#205480", "#123653"])
    def image(ax, bed, depth, title, detail=False):
        height = np.clip(np.log1p(np.maximum(bed, 0.))/np.log(501.), 0., 1.)
        rgb = land(height)[..., :3]
        rgb = LightSource(315, 40).shade_rgb(rgb, bed, dx=spacing, dy=spacing, vert_exag=2., blend_mode="soft")
        ax.imshow(rgb, extent=extent)
        water = np.where(depth > 1.e-8, depth, np.nan)
        ax.imshow(water, extent=extent, cmap=water_palette, vmin=0., vmax=8., alpha=.85)
        ax.contour(bed, [0.], colors="#dfd9b5", linewidths=.4, extent=extent, origin="upper")
        if detail:
            cells = a["terminal_cells_zx"]
            center = cells.mean(axis=0)*spacing/1000.
            ax.set_xlim(center[1]-2.8, center[1]+2.8)
            ax.set_ylim(center[0]+2.6, center[0]-2.6)
        ax.set_title(title)
        ax.set_xlabel("East from origin (km)")
        ax.set_ylabel("South from origin (km)")
    bed = a["combined__bed_m"]
    depth = a["combined__actual_water_depth_m"]
    fig, ax = plt.subplots(figsize=(11, 11))
    image(ax, bed, depth, "16 km TD detail + macro coast / finite coastal transport")
    fig.tight_layout(); fig.savefig(output/"scene-16km.png", dpi=190); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7))
    image(axes[0], bed, depth, "River mouths and land-side lowlands", True)
    image(axes[1], bed, a["combined__high_tide_actual_water_depth_m"], "High tide: connected inundation", True)
    fig.tight_layout(); fig.savefig(output/"mouth-detail.png", dpi=190); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    for ax, phase, title in zip(axes, ("low_tide_", "", "high_tide_"), ("Low tide", "Mean tide", "High tide")):
        image(ax, bed, a["combined__"+phase+"actual_water_depth_m"], title+": prescribed connected water", True)
    fig.tight_layout(); fig.savefig(output/"tidal-stages.png", dpi=170); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    for ax, name in zip(axes.flat, ("zero_forcing", "tide_only", "wave_only", "combined")):
        image(ax, a[name+"__bed_m"], a[name+"__actual_water_depth_m"], name.replace("_", " "), True)
    fig.tight_layout(); fig.savefig(output/"controls.png", dpi=170); plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(17, 10))
    fields = [a["construction_height_delta_m"], a["combined__tide_height_delta_m"],
        a["combined__wave_height_delta_m"], a["combined__river_supply_height_delta_m"],
        a["combined__bed_m"]-a["zero_forcing__bed_m"], a["combined__wet_fraction"]]
    titles = ["Construction only (m)", "Tidal face transport (m)", "Wave face transport (m)",
        "Finite river deposition (m)", "Combined minus no forcing (m)", "Connected marine wet fraction"]
    for ax, field, title in zip(axes.flat, fields, titles):
        vmax = max(float(np.abs(field).max()), 1.e-7)
        im = ax.imshow(field, extent=extent, cmap="RdBu_r" if title != titles[-1] else "Blues",
            vmin=-vmax if title != titles[-1] else 0., vmax=vmax)
        ax.set_title(title); fig.colorbar(im, ax=ax, shrink=.7)
    fig.tight_layout(); fig.savefig(output/"process-components.png", dpi=160); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    h = a["combined__phase_history"]
    axes[0, 0].plot(h[:, 2]); axes[0, 0].set_ylabel("Sea level (m)")
    axes[0, 1].plot(h[:, 3]/1.e6); axes[0, 1].set_ylabel("Connected marine area (km2)")
    axes[1, 0].plot(h[:, 5], label="Active solid"); axes[1, 0].plot(h[:, 6], label="Offshore export")
    axes[1, 0].legend(); axes[1, 0].set_ylabel("Solid (m3)")
    axes[1, 1].plot(h[:, 9]); axes[1, 1].set_ylabel("Net ocean water exchange (m3)")
    for ax in axes.flat:
        ax.set_xlabel("Representative phase")
    fig.tight_layout(); fig.savefig(output/"diagnostics.png", dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7))
    image(axes[0], a["annual_bed_m"], a["annual_water_depth_m"], "Inherited annual bed", False)
    image(axes[1], bed, depth, "Derived smooth macro + coastal bed", False)
    fig.tight_layout(); fig.savefig(output/"construction-before-after.png", dpi=170); plt.close(fig)


def run(output=OUTPUT):
    resource_limits()
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    arrays, summary = calculate()
    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output/"result.npz", **arrays)
    summary["result_sha256"] = file_sha256(output/"result.npz")
    (output/"summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    render(output, arrays)
    (output/"README.md").write_text("# Independent TD-derived coastal delta\n\n"
        "The terrain retains frozen macro land/sea and the existing TD residual. The inherited broad macro folds are rounded by explicit construction. "
        "Only annual terminal river exports enter the finite coastal inventory.\n\n"
        "View scene-16km.png, mouth-detail.png, controls.png, process-components.png, diagnostics.png, and construction-before-after.png. "
        "Full identities, units, inventories, assumptions and controls are in summary.json; actual bed and water arrays are in result.npz.\n\n"
        "Cold replay: `runtime/venv/Scripts/python.exe tools/run_td_coastal_delta.py --audit`\n", encoding="utf-8")
    return summary


def audit(output=OUTPUT):
    resource_limits()
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    for name, source in summary["source_paths"].items():
        if file_sha256(Path(source)) != summary["source_hashes"][name]:
            raise ValueError("source changed: "+name)
    for source, digest in summary["implementation_hashes"].items():
        if file_sha256(ROOT/source) != digest:
            raise ValueError("implementation changed: "+source)
    if file_sha256(output/"result.npz") != summary["result_sha256"]:
        raise ValueError("saved artifact hash changed")
    arrays, replay_summary = calculate()
    with np.load(output/"result.npz") as saved:
        for key, value in arrays.items():
            if not np.array_equal(saved[key], value, equal_nan=True):
                raise ValueError("cold replay mismatch: "+key)
    if summary["ledgers"] != replay_summary["ledgers"]:
        raise ValueError("cold ledger mismatch")
    return {"cold_replay_arrays_exact": True, "array_count": len(arrays),
        "source_hashes_match": True, "zero_supply_zero_forcing_exact": True,
        "ledgers": replay_summary["ledgers"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--audit", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.output) if arguments.audit else run(arguments.output), indent=2, ensure_ascii=False))
