"""Prepare or run a new finite natural-deposition delta mechanism experiment."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_natural_delta import NaturalDeltaConfig, finite_schedule, initial_basin, run_natural_delta
from tools.verify_fluvial_channel_remobilization import resource_limits

SOURCE = ROOT/"verification/fluvial-delta/adaptive-tree-16km-20261018-02/feedback_bundle.npz"
DEFAULT = ROOT/"verification/fluvial-delta/natural-deposition-local-20261018-01"
IMPLEMENTATIONS = ("terrain_pipeline/surface_rivers/metric_natural_delta.py", "tools/run_natural_delta.py",
    "terrain_pipeline/surface_rivers/metric_fluvial_native_routers.py", "terrain_pipeline/surface_rivers/metric_fluvial_water_repair.py",
    "terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py")


def audit_saved(output):
    report = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    with np.load(output/"result.npz") as archive:
        arrays = {key: archive[key] for key in archive.files}
    source = report["forcing"]
    if file_sha256(Path(source["source"])) != source["source_sha256"]:
        raise ValueError("source archive changed")
    for path, digest in report["implementation_hashes"].items():
        if file_sha256(ROOT/path) != digest:
            raise ValueError("saved implementation differs: "+path)
    bed = arrays["bed_m"]
    if not np.isfinite(bed).all() or np.min(bed-arrays["source_floor_m"]) < -2.e-6:
        raise ValueError("invalid bed or finite source floor")
    if not np.array_equal(bed[0], arrays["initial_bed_m"]):
        raise ValueError("initial bed mismatch")
    actual = float((bed[-1].astype(float)-bed[0]).sum()*25.)
    ledger = report["ledger_bulk_m3"]
    residual = (actual-ledger["injected_bulk_m3"]+ledger["exported_bulk_m3"]
        +ledger["lost_bulk_m3"]-ledger["inlet_correction_bulk_m3"])
    if not np.isclose(residual, ledger["raw_residual_bulk_m3"], atol=1.e-7):
        raise ValueError("saved measured phase residual differs")
    if morphology_evidence(arrays) != report["morphology_evidence"]:
        raise ValueError("morphology evidence changed")
    return {"source_and_implementation_hashes_match": True, "bed_source_floor_pass": True,
        "measured_bulk_residual_m3": residual, "injected_solid_m3": ledger["injected_bulk_m3"]*.65,
        "independent_numerical_replay": False, "morphology_evidence_recomputed": True}


def morphology_evidence(arrays):
    """New local mechanism measurements; never substitutes for old v6 gates."""
    from scipy.ndimage import binary_propagation, label
    initial = arrays["initial_bed_m"]
    beds = arrays["bed_m"]
    depths = arrays["depth_m"]
    original_ocean = (initial < 0.) & (arrays["cell_type"] == 0)
    original_land = initial >= 0.
    rows = []
    area = NaturalDeltaConfig().dx_m**2
    for index, (bed, depth, qx, qz) in enumerate(zip(beds, depths, arrays["qx_m2_s"], arrays["qz_m2_s"])):
        geometric = bed >= 0.
        exposed = geometric & (depth <= 2.e-6)
        geometry_connected = binary_propagation(original_land & geometric, mask=geometric)
        exposure_connected = binary_propagation(original_land & exposed, mask=exposed)
        new_geometry = original_ocean & geometry_connected
        new_exposed = original_ocean & exposure_connected
        # Cross-sections alone are diagnostic: separated ocean-flow patches
        # are never called distributaries without dry-bar and persistence proof.
        cross_sections = []
        for row in (18, 24, 32, 48):
            forward = np.maximum(qx[row], 0.)*NaturalDeltaConfig().dx_m
            total = float(forward.sum())
            active = (forward >= .1*max(total, 1.e-12)) & (depth[row] > 2.e-6)
            groups, count = label(active)
            fractions = [float(forward[groups == group].sum()/total) for group in range(1, count+1)] if total > 0. else []
            cross_sections.append({"downstream_m": row*NaturalDeltaConfig().dx_m,
                "positive_cross_section_discharge_m3_s": total, "separated_flux_patch_fractions": fractions})
        change = (bed.astype(float)-initial)*area
        rows.append({"frame": index, "geometric_new_connected_land_m2": float(new_geometry.sum()*area),
            "actual_dry_new_connected_land_m2": float(new_exposed.sum()*area),
            "original_ocean_positive_bed_change_bulk_m3": float(np.maximum(change, 0.)[original_ocean].sum()),
            "negative_bed_change_bulk_m3": float(np.maximum(-change, 0.).sum()),
            "max_bed_rise_m": float((bed-initial).max()), "cross_sections": cross_sections})
    tail = beds[-min(5, len(beds)):]
    tail_depth = depths[-len(tail):]
    persistent_exposure = np.all((tail >= 0.) & (tail_depth <= 2.e-6), axis=0)
    linked = binary_propagation(original_land & persistent_exposure, mask=persistent_exposure)
    return {"schema": "natural-local-morphology-evidence-v1", "frames": rows,
        "persistent_last_frames": len(tail),
        "persistent_actual_new_connected_land_m2": float((linked & original_ocean).sum()*area),
        "sustained_distributaries_accepted": False,
        "branch_semantics": "flux patches are diagnostics only; no automatic branch acceptance from ocean spreading",
        "original_substrate_erosion_lower_bound_solid_m3": float(np.maximum(initial-arrays["minimum_visited_bed_m"], 0.).sum()*area*.65)}


def load_forcing(mode):
    with np.load(SOURCE) as source:
        q = source["water_q_m3_s"][:, -1]
        solid = source["exported_solid_m3"].sum(axis=1)
        duration = np.diff(source["time_seconds"])
    schedule = finite_schedule(q, solid, duration, mode=mode)
    return schedule, {"source": str(SOURCE), "source_sha256": file_sha256(SOURCE),
        "daily_input_solid_m3": solid.tolist(), "daily_water_q_m3_s": q.tolist(),
        "real_annual_solid_m3": float(solid.sum()), "real_annual_water_m3": float(np.sum(q*duration)),
        "scheduled_solid_m3": float(schedule[:, 3].sum()), "scheduled_water_m3": float(np.sum(schedule[:, 2]*schedule[:, 4])),
        "scheduled_duration_s": float(schedule[:, 4].sum()), "schedule_steps": len(schedule),
        "mode": mode, "semantics": "mechanism compresses sediment-bearing days to declared 0.1% bulk boundary; same finite annual sediment, not real annual chronology/water budget" if mode == "mechanism" else "actual daily source water and sediment with per-day volume subdivision"}


def prepare_td_basin():
    """Inspect unchanged macro+TD source in a river-aligned local frame."""
    from scipy.ndimage import map_coordinates
    path = ROOT/".scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-15/scene.npz"
    with np.load(path) as archive:
        metadata = json.loads(str(archive["metadata_json"]))
        source_bed = archive["base_bed_m"]
        raw = archive["raw_td_sample_m"]
    direction = np.asarray(metadata["river_direction_xz"], float)
    normal = np.array([-direction[1], direction[0]])
    rows, columns = np.indices(NaturalDeltaConfig().shape)
    # The one upstream boundary stub ends at the actual zero-datum river mouth.
    along = rows*5.-60.
    cross = (columns-60)*5.
    xz = np.asarray(metadata["mouth_xz_m"])+along[..., None]*direction+cross[..., None]*normal
    source_cells = (xz-np.asarray(metadata["origin_xz_m"]))/float(metadata["spacing_m"])
    bed = map_coordinates(source_bed, [source_cells[..., 1], source_cells[..., 0]], order=1, mode="nearest")
    raw_local = map_coordinates(raw, [source_cells[..., 1], source_cells[..., 0]], order=1, mode="nearest")
    prepared = bed.copy()
    prepared[:12, 52:68] = -1.5
    delta = prepared-bed
    return {"initial_bed_m": prepared, "source_td_macro_bed_m": bed, "raw_td_sample_m": raw_local,
        "local_xz_world_m": xz, "boundary_stub_construction_delta_m": delta}, {
        "source_scene": str(path), "source_scene_sha256": file_sha256(path),
        "source_role": "base_bed_m only: unchanged macro + 0.35*TD residual, excludes constructed fan and branches",
        "local_frame": {"origin_world_xz_m": xz[0, 0].tolist(), "downstream_direction_xz": direction.tolist(),
            "cross_stream_direction_xz": normal.tolist(), "spacing_m": 5.},
        "construction_cut_bulk_m3": float(np.maximum(-delta, 0.).sum()*25.),
        "construction_fill_bulk_m3": float(np.maximum(delta, 0.).sum()*25.),
        "initial_basin_centerline_bed_m": bed[:, 60].tolist(),
        "status": "prepared geometry inspection only; not yet accepted native rotated-boundary initialization"}


def render(output, arrays):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    water = LinearSegmentedColormap.from_list("water", ["#75d1df", "#2b80b0", "#183f6b"])
    initial = arrays["initial_bed_m"]
    beds = arrays.get("bed_m", initial[None, ...])
    depths = arrays.get("depth_m", np.maximum(-beds, 0.))
    stages = arrays.get("stage_m", np.maximum(beds, 0.))
    fig, axes = plt.subplots(1, 3, figsize=(16, 7))
    for ax, index, title in ((axes[0], 0, "Initial: one inlet, no bar or branches"),
        (axes[1], -1, "Final: actual bed and wet depth")):
        ax.imshow(beds[index], origin="upper", extent=[-300, 300, 800, 0], cmap="terrain", vmin=-1.5, vmax=1.)
        ax.imshow(np.where(depths[index] > 2.e-6, depths[index], np.nan), extent=[-300, 300, 800, 0], cmap=water, vmin=0., vmax=2.)
        ax.contour(beds[index], [0.], colors="black", linewidths=.7, extent=[-300, 300, 800, 0], origin="upper")
        ax.set_title(title)
    change = beds[-1]-initial
    vmax = max(float(np.abs(change).max()), .01)
    image = axes[2].imshow(change, extent=[-300, 300, 800, 0], cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    axes[2].set_title("Actual erosion / deposition (m)")
    fig.colorbar(image, ax=axes[2], shrink=.6)
    for ax in axes:
        ax.set_xlabel("Cross-stream (m)"); ax.set_ylabel("Downstream (m)")
    fig.tight_layout(); fig.savefig(output/"overview.png", dpi=170); plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT)
    parser.add_argument("--mode", choices=("mechanism", "annual"), default="mechanism")
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--prepare-td", action="store_true")
    parser.add_argument("--zero-supply", action="store_true")
    parser.add_argument("--routing-dry-depth", type=float, choices=(.1, .01), default=.1)
    parser.add_argument("--reference-bulk-concentration", type=float)
    parser.add_argument("--terrain", choices=("synthetic", "td"), default="synthetic")
    parser.add_argument("--audit", action="store_true")
    arguments = parser.parse_args()
    resource_limits()
    if arguments.audit:
        print(json.dumps(audit_saved(arguments.output), indent=2))
        return
    implementation_before = {path: file_sha256(ROOT/path) for path in IMPLEMENTATIONS}
    if arguments.reference_bulk_concentration is not None:
        implementation_before["terrain_pipeline/surface_rivers/metric_reference_erosion.py"] = file_sha256(ROOT/"terrain_pipeline/surface_rivers/metric_reference_erosion.py")
    schedule, forcing = load_forcing(arguments.mode)
    if arguments.prepare_td:
        arguments.output.mkdir(parents=True, exist_ok=False)
        arrays, td_report = prepare_td_basin()
        report = {"schema": "finite-natural-delta-td-preparation-v1", "forcing": forcing,
            "terrain": td_report}
    elif arguments.prepare:
        arguments.output.mkdir(parents=True, exist_ok=False)
        arrays = {"initial_bed_m": initial_basin(), "schedule": schedule}
        report = {"schema": "finite-natural-delta-preparation-v1", "forcing": forcing,
            "initialization": "synthetic shallow basin: hB=.75m, h0=1.5m; 60m upstream boundary stub only; no prepared mouth bar/island/branch"}
    else:
        start = time.perf_counter()
        initialization = None
        terrain_report = {"type": "synthetic shallow basin"}
        if arguments.terrain == "td":
            from tools.prepare_td_natural_delta import SCENE
            from terrain_pipeline.surface_rivers.metric_td_delta_initialization import prepare_td_initialization
            with np.load(SCENE) as archive:
                meta = json.loads(str(archive["metadata_json"]))
                initialization, terrain_report = prepare_td_initialization(archive["base_bed_m"], archive["macro_bed_m"],
                    archive["raw_td_sample_m"], archive["td_residual_m"], source_origin_xz=meta["origin_xz_m"],
                    source_spacing_m=meta["spacing_m"], mouth_xz=meta["mouth_xz_m"], direction_xz=meta["river_direction_xz"])
            terrain_report["source_sha256"] = file_sha256(SCENE)
            terrain_report["source_scene"] = str(SCENE)
            implementation_before["terrain_pipeline/surface_rivers/metric_td_delta_initialization.py"] = file_sha256(ROOT/"terrain_pipeline/surface_rivers/metric_td_delta_initialization.py")
        arrays, report = run_natural_delta(schedule, arguments.output, steps=arguments.steps,
            config=NaturalDeltaConfig(routing_dry_depth_m=arguments.routing_dry_depth,
                reference_bulk_concentration=arguments.reference_bulk_concentration),
            zero_supply=arguments.zero_supply,
            initialization=initialization,
            progress=lambda step, seconds, solid: print("PROGRESS", step, "model_seconds", seconds, "solid_m3", solid, "wall_s", time.perf_counter()-start, flush=True))
        report["forcing"] = forcing
        report["terrain_initialization"] = terrain_report
        report["runtime_s"] = time.perf_counter()-start
        report["morphology_evidence"] = morphology_evidence(arrays)
    report["implementation_hashes"] = implementation_before
    report["implementation_unchanged_during_run"] = all(file_sha256(ROOT/path) == digest for path, digest in implementation_before.items())
    np.savez_compressed(arguments.output/"result.npz", **arrays)
    (arguments.output/"summary.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    render(arguments.output, arrays)
    print(json.dumps({"output": str(arguments.output), "forcing": forcing, "steps": report.get("steps", 0)}, indent=2))


if __name__ == "__main__":
    main()
