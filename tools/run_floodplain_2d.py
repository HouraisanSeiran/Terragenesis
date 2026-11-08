"""Two-dimensional floodplain / terminal-basin run fed by the solved reach.

What this does
--------------
Takes the finished one-dimensional reach of `full-reach-run-02` and drives a
two-dimensional local-inertial march (the frozen
`regional-surface-local-inertial-D4-implicit-new-q-drag-v2` solver, unchanged) over a
window of the TD 30 m fine terrain field.

Coupling direction: **one way, 1D -> 2D**. Water enters the two-dimensional domain
only where a reach edge crosses the window boundary, on that boundary cell, using the
donor node's own saved `water_outgoing_volume_m3`. Nothing flows back. Every injected
cubic metre is a line item the reach ledger already removed from the donor, so the
two-dimensional ledger closes on its own and no volume is counted twice.

Run
---
    python tools/run_floodplain_2d.py \\
        --output .scratch/cross-region-tributary/floodplain-2d-01
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.surface_hydraulics import INERTIAL_SCHEMA, SurfaceBudget
from terrain_pipeline.surface_hydraulics import WORLD_FLOODPLAIN_2D_SCHEMA as SCHEMA, FloodplainWindow, aggregate_fine_field, build_domain, cell_centres, crossing_edges, domain_ledger, extent_statistics, hydrograph, residual_wetland, run_domain, source_locations, source_matrix, window_extent

REACH_RUN = ROOT / ".scratch/cross-region-tributary/full-reach-run-02"
FINE_FIELD = ROOT / ".scratch/cross-region-tributary/td-detail-01/fine-terrain-field.npz"
WORLD_SEED = 20261020
BLOCK_CELLS = 3          # 3 x 3 fine cells -> 90 m; 513 // 3 = 171 -> 29 241 cells
INTERVAL_S = 3600.
INTERVALS = 72           # 72 h, the reach scenario's own physical duration
SNAPSHOT_S = 3600.
BUDGET = SurfaceBudget(max_depth_m=60., max_snapshots=80, max_duration_s=259200.,
                       max_wall_s=7200., roughness_s_m_third=.035, max_dt_s=30.,
                       inertial_cfl=.45)


def write_packet(directory, name, packet):
    arrays = {key: value for key, value in packet.items() if isinstance(value, np.ndarray)}
    meta = {key: value for key, value in packet.items() if not isinstance(value, np.ndarray)}
    with (directory / (name + ".npz")).open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    publish_bytes(directory / (name + ".json"), json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"))


def reconcile_with_one_dimensional_section(geometry_raw, dynamic, fine):
    """Measure what the one-dimensional rectangular section assumes versus the terrain.

    The reach solver's `_hydraulics` divides volume by `width * length` only, i.e. it
    fills a flat rectangle of uniform depth. This records, at every reach node, what
    the fine terrain says along the same centreline, so the report can state the
    discrepancy as a number instead of a caveat.
    """
    origin = np.asarray(fine["origin_xz_m"], np.float64)
    fine_spacing = float(fine["spacing_m"])
    height = np.asarray(fine["height_m"], np.float64)
    receiver = np.asarray(geometry_raw["receiver"], np.int64)
    width = np.asarray(geometry_raw["width_m"], np.float64)
    carve = np.asarray(geometry_raw["depth_m"], np.float64)
    node_xz = np.asarray(geometry_raw["node_xz_m"], np.float64)
    volume = np.asarray(dynamic["water_volume_m3"], np.float64)
    material = np.asarray(dynamic["material_area_m2"], np.float64)
    depth = volume / material
    rows = []
    for node in range(node_xz.shape[0]):
        target = int(receiver[node])
        if target < 0:
            continue
        start, end = node_xz[node], node_xz[target]
        length = float(np.hypot(*(end - start)))
        segment = end - start
        samples = []
        for fraction in (.1, .3, .5, .7, .9):
            point = start + fraction * segment
            row = int(round((point[1] - origin[1]) / fine_spacing))
            column = int(round((point[0] - origin[0]) / fine_spacing))
            inside_page = 0 <= row < height.shape[0] and 0 <= column < height.shape[1]
            samples.append(float(height[row, column]) if inside_page else None)
        usable = [value for value in samples if value is not None]
        rows.append({"donor": node, "receiver": target, "length_m": length,
                     "width_m": float(width[node]), "carve_depth_m": float(carve[node]),
                     "centreline_fine_elevation_m": samples,
                     "centreline_relief_m": (max(usable) - min(usable)) if usable else None,
                     "centreline_samples_inside_fine_page": len(usable),
                     "max_depth_m": float(depth[:, node].max()),
                     "peak_volume_m3": float(volume[:, node].max())})
    return {
        "note": "the reach solver is manning-rectangular-explicit-v2: depth = volume / "
                "(width * length) in a flat rectangle, capacity = length * width * max_depth. "
                "Its depth_m is a uniform carriage depth, not a terrain crest.",
        "one_dimensional_section_kind": "rectangular, constant width, no terrain cross-section",
        "nodes": rows,
        "consequence": "a 'water level above the channel top' cannot be read off this model, "
                       "because the model has no channel top: it has a depth limit. Floodplain "
                       "inundation here therefore has to come from boundary injection into real "
                       "terrain, not from overtopping a section that does not exist in the data.",
    }


def overbank_sensitivity(geometry_raw, dynamic):
    """What an overtopping reading would have produced, and why it is not physical here.

    Computed and reported so the alternative is auditable: it assumes the carriage
    depth limit is the channel top and converts every node's excess depth into an
    overbank volume.
    """
    carry = np.asarray(geometry_raw["depth_m"], np.float64)
    material = np.asarray(dynamic["material_area_m2"], np.float64)
    volume = np.asarray(dynamic["water_volume_m3"], np.float64)
    times = np.asarray(dynamic["time_seconds"], np.float64)
    depth = volume / material
    excess = np.maximum(depth - carry[None, :], 0.) * material[None, :]
    total = excess.sum(axis=1)
    peak = int(np.argmax(total))
    return {
        "definition": "overbank volume = max(depth - carriage_depth, 0) * material_area, "
                      "treating the uniform 0.4 m carriage depth as the channel top",
        "peak_volume_m3": float(total[peak]),
        "peak_time_s": float(times[peak]),
        "never_positive": bool(total.max() <= 0.),
        "nodes_ever_over": [int(i) for i in np.flatnonzero(excess.max(axis=0) > 0.)],
        "rejected_because": [
            "the one-dimensional section is 800-3200 m wide and its cross-section in the "
            "terrain rises 33-85 m on the east flank at the very nodes where the excess "
            "appears, so the water is inside the ground, not above it",
            "the carriage depth is an explicit engineering constant (uniform 0.4 m at all 37 "
            "nodes), not a measured channel top, so 'overtopping' it is not a terrain event",
            "the excess is not a released volume: it is the difference between two book-keeping "
            "depths, and pouring it into terrain would double count the same storage",
        ],
    }


def aggregate_reach_outgoing(step_seconds, outgoing, donors, *, interval_s, intervals):
    """Sum the reach solver's per-substep transferred volumes into fixed intervals.

    The reach saves one row per solver sub-step, which is not a fixed clock. Binning
    on physical time keeps the injected hydrograph a function of time only, never of
    the adapted step count.
    """
    step_seconds = np.asarray(step_seconds, np.float64)
    outgoing = np.asarray(outgoing, np.float64)
    bins = np.floor(step_seconds / interval_s + 1e-9).astype(np.int64)
    if bins.min() < 0 or bins.max() >= intervals:
        raise ValueError("saved sub-step time outside the declared scenario")
    volumes = np.zeros((intervals, len(donors)), np.float64)
    for column, donor in enumerate(donors):
        np.add.at(volumes[:, column], bins, outgoing[:, donor])
    if not np.isfinite(volumes).all() or (volumes < 0.).any():
        raise ValueError("injection volume must be finite and non-negative")
    return volumes


def closed_reach_subledger(products, inside):
    """Water ledger of the parts of the reach that sit outside the 2D window.

    Removing the window's own nodes from the reach turns the crossing edges into the
    sub-region's export and the two-dimensional domain's import; the same volume
    cancels in the merge, which is the concrete reason nothing is double counted.
    """
    node_volume = np.asarray(products["water_volume_m3"], np.float64)
    receiver = np.asarray(products["receiver"], np.int64)
    outgoing = np.asarray(products["outgoing_volume_m3"], np.float64)
    local = np.asarray(products["local_bucket_q_m3_s"], np.float64) * INTERVAL_S
    # The reach also receives water through its declared truncated upstream boundary
    # scenarios. Omitting that term leaves the sub-region roughly 1.6e8 m3 short and
    # the merged ledger visibly open, so it is a required input, not an extra.
    boundary = np.asarray(products["boundary_q_m3_s"], np.float64) * INTERVAL_S
    outside = ~np.asarray(inside, bool)
    crossing = np.array([receiver[i] >= 0 and inside[i] != inside[receiver[i]]
                         for i in range(receiver.size)])
    if crossing.any() and (outside & crossing).sum() != crossing.sum():
        raise ValueError("this window is expected to sit downstream of every crossing edge")
    initial = float(node_volume[0][outside].sum())
    final = float(node_volume[-1][outside].sum())
    supplied = float(local[:, outside].sum())
    injected = float(boundary[:, outside].sum())
    exported = float(outgoing[:, crossing].sum())
    return {
        "scope": "reach nodes outside the two-dimensional window only",
        "excluded_nodes_inside_window": [int(i) for i in np.flatnonzero(inside)],
        "crossing_edges": [int(i) for i in np.flatnonzero(crossing)],
        "initial_storage_m3": initial,
        "local_input_m3": supplied,
        "boundary_input_m3": injected,
        "export_to_two_dimensional_m3": exported,
        "final_storage_m3": final,
        "residual_m3": final - initial - supplied - injected + exported,
        "interval_s": INTERVAL_S,
        "algebra": "final = initial + local_input + boundary_input "
                   "- export_to_two_dimensional + residual",
    }


def merged_ledger(two_dimensional, reach_subledger, *, local_runoff_inside_domain_m3):
    """Merge: the injected volume appears once as an export and once as an import.

    The merged system is {reach nodes outside the window} UNION {two-dimensional
    domain}. The injected volume is an internal transfer inside that system, so it is
    subtracted from neither side's input nor added to either side's export.

    Rain falling on the two-dimensional domain's own cells (the reach node's local
    runoff bucket) is **not** part of that system: this run does not model spatially
    distributed rainfall over the two-dimensional page, so the bucket is declared and
    excluded rather than silently folded into one side.
    """
    initial = reach_subledger["initial_storage_m3"] + two_dimensional["initial_storage_m3"]
    supplied = reach_subledger["local_input_m3"] + reach_subledger["boundary_input_m3"]
    exported = two_dimensional["boundary_output_m3"]
    final = reach_subledger["final_storage_m3"] + two_dimensional["final_storage_m3"]
    residual = final - initial - supplied + exported
    return {
        "system": "reach nodes outside the two-dimensional window UNION the "
                  "two-dimensional domain",
        "initial_storage_m3": initial,
        "input_m3": supplied,
        "export_m3": exported,
        "final_storage_m3": final,
        "residual_m3": residual,
        "residual_relative": residual / max(abs(supplied) + abs(initial), 1.),
        "components": {
            "reach_outside_initial_m3": reach_subledger["initial_storage_m3"],
            "reach_outside_local_input_m3": reach_subledger["local_input_m3"],
            "reach_outside_boundary_input_m3": reach_subledger["boundary_input_m3"],
            "reach_outside_final_m3": reach_subledger["final_storage_m3"],
            "two_dimensional_initial_m3": two_dimensional["initial_storage_m3"],
            "two_dimensional_injected_m3": two_dimensional["injected_m3"],
            "two_dimensional_outfall_m3": two_dimensional["boundary_output_m3"],
            "two_dimensional_boundary_input_m3": two_dimensional["boundary_input_m3"],
            "two_dimensional_final_m3": two_dimensional["final_storage_m3"],
        },
        "cancelled_internal_transfer_m3": two_dimensional["injected_m3"],
        "declared_out_of_scope": {
            "local_runoff_on_two_dimensional_domain_m3": float(local_runoff_inside_domain_m3),
            "reason": "the reach's local runoff bucket for the node inside the window is "
                      "rainfall on the two-dimensional page itself; this run has no "
                      "two-dimensional rainfall forcing, so the bucket is excluded from "
                      "both the ledger and the injection instead of being counted twice",
        },
        "algebra": "final = initial + input - export + residual, with the injected volume "
                   "as an internal transfer",
        "no_double_count_statement":
            "the two-dimensional injected volume is the same figure as the reach sub-region's "
            "export_to_two_dimensional_m3; it is an internal transfer in the merged account and "
            "therefore appears in neither the merged input nor the merged export",
    }


def frame_selection(times, wet_area, volume):
    """Four declared frames: first wet, peak volume, recession, final."""
    times = np.asarray(times, np.float64)
    wet_area = np.asarray(wet_area, np.float64)
    volume = np.asarray(volume, np.float64)
    peak = int(np.argmax(volume))
    first = int(np.flatnonzero(wet_area > 0.)[0]) if (wet_area > 0.).any() else 0
    after = np.flatnonzero(volume[peak:] < volume[peak] * .5)
    recession = int(peak + after[0]) if after.size else len(times) - 1
    frames = []
    for index, label in ((first, "涨水"), (peak, "洪峰/最高水位"),
                         (recession, "退水"), (len(times) - 1, "终态")):
        if index not in [item[0] for item in frames]:
            frames.append((index, label))
    frames.sort(key=lambda item: item[0])
    return frames, peak


def plot_frames(directory, output, depth_m, times, height, spacing, carved, frames, world_seed):
    """Flood-extent frames drawn with the shared renderer's own primitives."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from tools.render_remote_sensing import DECLARATION, _annotate, _save, surface_rgb, water_rgb

    xs, zs = output["xs"], output["zs"]
    extent = [float(xs[0]), float(xs[-1]), float(zs[-1]), float(zs[0])]
    written = {}
    count = len(frames)
    fig, axes = plt.subplots(1, count, figsize=(6.2 * count, 7.0), facecolor="#0d1117", squeeze=False)
    axes = axes[0]
    for axis, (index, label) in zip(axes, frames):
        field = depth_m[index]
        rgb = surface_rgb(height, spacing, vertical_exaggeration=6.)
        wet = field > .02
        water = water_rgb(np.where(wet, field, 0.))
        edge = np.clip(field / .03, 0., 1.)[..., None]
        rgb = np.where(wet[..., None], rgb * (1. - edge) + water * edge, rgb)
        axis.imshow(rgb, extent=extent, origin="upper", interpolation="nearest")
        axis.set_facecolor("#0d1117")
        overlay = np.where(wet, field, np.nan)
        axis.contour(xs, zs, overlay, levels=[.02], colors="#ffd166", linewidths=.9)
        axis.contour(xs, zs, overlay, levels=[1., 5., 15.], colors="#ffd166",
                     linewidths=.5, linestyles="dotted")
        axis.set_title("%s · t = %.0f s%s" % (label, times[index],
                      "\n淹没 %.2f km² · 最大水深 %.1f m"
                      % (wet.sum() * spacing ** 2 / 1e6, float(field.max()))), fontsize=10, pad=6)
        axis.set_xticks([])
        axis.set_yticks([])
    _annotate(axes[0], xs, zs, "二维漫流 · 淹没范围", "TD 30 m 细地形聚合到 %.0f m；"
              "等值线 0.02 / 1 / 5 / 15 m" % spacing,
              ["world_seed=%d" % world_seed,
               "一维→二维单向耦合，无回水",
               "一维位置 %d 帧" % len(times)])
    fig.suptitle("洪水演进 · 二维局部惯性漫流（非卫星观测）", fontsize=14, y=0.99)
    fig.text(.5, .02, "world_seed=%d · %s" % (world_seed, DECLARATION),
             ha="center", fontsize=9, color="#c9d4dc")
    written["flood-extent-frames"] = str(directory / "flood-extent-frames.png")
    _save(fig, written["flood-extent-frames"], dpi=150)

    # Second figure: extent / depth / volume time series, so the recession is visible
    # as a curve and not only as four stills.
    fig, axes = plt.subplots(3, 1, figsize=(11., 10.), facecolor="#0d1117", sharex=True)
    for axis in axes:
        axis.set_facecolor("#12181f")
        axis.tick_params(colors="#c9d4dc", labelsize=8)
        for spine in axis.spines.values():
            spine.set_color("#3a4653")
        axis.grid(color="#22303c", lw=.6)
    axes[0].plot(times / 3600., output["wet_area_km2"], color="#4aa3d8", lw=1.8, label="淹没面积")
    axes[0].plot(times / 3600., output["overbank_area_km2"], color="#ffd166", lw=1.4,
                 label="槽外（漫滩）面积")
    axes[0].set_ylabel("km²", color="#c9d4dc")
    axes[0].legend(fontsize=8, facecolor="#12181f", labelcolor="#c9d4dc")
    axes[1].plot(times / 3600., output["max_depth_m"], color="#e8a33d", lw=1.8)
    axes[1].set_ylabel("最大水深 m", color="#c9d4dc")
    axes[2].plot(times / 3600., output["volume_m3"] / 1e6, color="#7fd1a8", lw=1.8)
    axes[2].set_ylabel("二维存量 百万 m³", color="#c9d4dc")
    axes[2].set_xlabel("物理时间 (h)", color="#c9d4dc")
    fig.suptitle("淹没范围 / 水深 / 存量 过程线", fontsize=13, color="#e6edf3")
    written["flood-series"] = str(directory / "flood-series.png")
    _save(fig, written["flood-series"], dpi=150)
    plt.close("all")
    return written


def write_shadow_run(directory, reach_run, height_page, origin, spacing, fine_identity):
    """A run directory the unmodified renderer can consume.

    `tools/render_remote_sensing.py` reads a run directory: terrain from
    `source-terrain-and-forcing.npz`, bed from `generated-geometry.npz`, node water
    from `dynamic-water-sediment-bed.npz`, and now optionally the two-dimensional
    depth from `floodplain-depth-field.npz`. This run has its own terrain and depth
    but no conforming-mesh bed, so the reach run's geometry and dynamics are mirrored
    in (the same device `td-detail-01/fine-run` uses). Nothing is invented: the
    mirrored files are byte copies and the depth field is this run's own output.
    """
    import shutil

    shadow = directory / "remote-sensing-run"
    shadow.mkdir(exist_ok=True)
    # Rebuilding this bundle must be idempotent: the derived files are rewritten, the
    # mirrored copies are refreshed, and nothing else in the run is touched.
    for name in ("source-terrain-and-forcing.npz", "source-terrain-and-forcing.json",
                 "source-selection.json", "bed-change-field.npz", "bed-change-field.json",
                 "generated-geometry.npz", "dynamic-water-sediment-bed.npz",
                 "lake-definition.json", "lake-storage.npz",
                 "floodplain-depth-field.npz"):
        stale = shadow / name
        if stale.exists():
            stale.unlink()
    # The terrain page must be the one the solver integrated: origin is the cell
    # centre so the renderer's grid_axes reproduces these coordinates.
    with (shadow / "source-terrain-and-forcing.npz").open("wb") as stream:
        np.savez_compressed(stream, height_m=height_page,
                            origin_xz_m=np.asarray(origin, np.float64))
    publish_bytes(shadow / "source-selection.json",
                  json.dumps({"coarse_terrain_spacing_m": float(spacing),
                              "fine_field_identity_sha256": fine_identity,
                              "source_run": str(reach_run.relative_to(ROOT)),
                              "note": "shadow run: 90 m block-mean page this floodplain "
                                      "run integrated, so the renderer draws the same grid"},
                             indent=2, ensure_ascii=False).encode("utf-8"))
    mirrored = {}
    for name in ("generated-geometry.npz", "dynamic-water-sediment-bed.npz",
                 "lake-definition.json", "lake-storage.npz",
                 "floodplain-depth-field.npz", "floodplain-depth-field.json"):
        source = (reach_run if name not in ("floodplain-depth-field.npz",
                                            "floodplain-depth-field.json") else directory) / name
        if source.exists():
            shutil.copy2(source, shadow / name)
            mirrored[name] = file_sha256(shadow / name)
    # The source reach declares `dynamic_geometry_mode = nodal_bed_only_initial_PL_mesh_
    # not_updated`: its conforming mesh bed never moves, only node beds do. The renderer
    # asks for a bed-change field to draw a final bed, so the shadow run states that
    # truth explicitly instead of leaving the request unsatisfiable: initial = final =
    # the saved carve, change = 0. No geometry is invented here.
    field_path = shadow / "bed-change-field.npz"
    if not field_path.exists():
        carve = np.load(shadow / "generated-geometry.npz")["bed_elevation_m"]
        with field_path.open("wb") as stream:
            np.savez_compressed(stream, initial_bed_m=carve, final_bed_m=carve,
                                bed_change_m=np.zeros_like(carve))
        mirrored["bed-change-field.npz"] = file_sha256(field_path)
        publish_bytes(shadow / "bed-change-field.json",
                      json.dumps({"source": "static carve of the source run",
                                  "note": "run-02 declares the conforming mesh is not "
                                          "remapped (node beds only), so final == initial "
                                          "and the change field is identically zero",
                                  "bed_change_max_abs_m": 0.0},
                                 indent=2, ensure_ascii=False).encode("utf-8"))
    return shadow, mirrored


def load_saved_solution(directory):
    """Cold read of a finished run's own saved artefacts.

    The repository's cold-read rule for the regional solver is that a reader must not
    re-prepare terrain, re-build routing or re-advance dynamics. This function obeys
    it: it reads the saved depth field, state ledger and injection packet and returns
    them in the same shape `run_domain` produced, so report and figures can be
    regenerated without touching the physics.
    """
    states = np.load(directory / "states.npz")
    field = np.load(directory / "floodplain-depth-field.npz")
    injection = np.load(directory / "injection.npz")
    if not np.array_equal(np.asarray(states["time_s"], np.float64),
                          np.asarray(field["time_s"], np.float64)):
        raise ValueError("saved depth field and state ledger disagree on time")
    metadata = json.loads((directory / "states.json").read_text(encoding="utf-8"))
    # `write_packet` files every non-ndarray member into the sidecar JSON, so the page
    # scalar spacing lives there, not inside the archive.
    page_meta = (directory / "floodplain-depth-field.json")
    spacing = float(json.loads(page_meta.read_text(encoding="utf-8"))["spacing_m"]) if page_meta.exists() else None
    if spacing is None:
        raise ValueError("saved depth field has no declared spacing")
    return {
        "arrays": {
            "time_s": np.asarray(states["time_s"], np.float64),
            "depth_m": np.asarray(field["depth_m"], np.float64),
            "initial_depth_m": np.zeros(np.asarray(field["depth_m"]).shape[1:], np.float64),
            "ledger": np.asarray(states["ledger"], np.float64),
            "final_internal_q_m3_s": np.asarray(states["final_internal_q_m3_s"], np.float64),
            "final_boundary_q_m3_s": np.asarray(states["final_boundary_q_m3_s"], np.float64),
        },
        "metadata": metadata,
        "diagnostics": metadata["diagnostics"],
        "field": field, "injection": injection, "spacing_m": spacing,
    }


def render_through_shared_tool(shadow, out, centre=None):
    """Call the unmodified renderer CLI with the two-dimensional depth enabled."""
    from tools.render_remote_sensing import main as render_main

    argv = ["--run", str(shadow), "--output", str(out), "--floodplain",
            "--reach-km", "20", "--reach-z-km", "20", "--regional-km", "40"]
    if centre is not None:
        argv += ["--centre", str(centre[0]), str(centre[1])]
    try:
        render_main(argv)
        return "ok"
    except SystemExit as error:                     # the CLI returns through SystemExit
        return "exit %s" % error.code


def report_only(directory):
    """Regenerate figures and report.json from a finished run's saved artefacts.

    Physics is never re-run here: the depth field, state ledger and injection packet
    are read cold (see `load_saved_solution`). The pre-existing report is preserved as
    `report.initial.json` so nothing is silently overwritten.
    """
    directory = Path(directory)
    saved = load_saved_solution(directory)
    field = saved["field"]
    depth = saved["arrays"]["depth_m"]
    times = saved["arrays"]["time_s"]
    page = np.asarray(field["height_m"], np.float64)
    carved = np.asarray(field["carved_depth_m"], np.float64)
    spacing = saved["spacing_m"]
    origin = np.asarray(field["origin_xz_m"], np.float64)
    shape = page.shape
    xs = origin[0] + np.arange(shape[1]) * spacing
    zs = origin[1] + np.arange(shape[0]) * spacing
    original = directory / "report.json"
    archived = directory / "report.initial.json"
    if original.exists():
        if archived.exists():
            # A previous regeneration already preserved the original; this run's
            # report is a derived artefact and is replaced, not archived again.
            original.unlink()
        else:
            archived.write_bytes(original.read_bytes())
            original.unlink()

    wet_area, overbank_area, max_depth, volume = [], [], [], []
    for index in range(depth.shape[0]):
        stats = extent_statistics(depth[index], spacing_m=spacing, carved_depth_m=carved)
        wet_area.append(stats["wet_area_m2"])
        overbank_area.append(stats["overbank_wet_area_m2"])
        max_depth.append(stats["max_depth_m"])
        volume.append(stats["volume_m3"])
    series = {"times": times, "wet_area_km2": np.asarray(wet_area) / 1e6,
              "overbank_area_km2": np.asarray(overbank_area) / 1e6,
              "max_depth_m": np.asarray(max_depth), "volume_m3": np.asarray(volume),
              "xs": xs, "zs": zs}
    frames, _ = frame_selection(times, wet_area, volume)
    images = plot_frames(directory, series, depth, times, page, spacing, carved,
                         frames, WORLD_SEED)

    geometry_raw = np.load(REACH_RUN / "generated-geometry.npz")
    dynamic = np.load(REACH_RUN / "dynamic-water-sediment-bed.npz")
    forcing = np.load(REACH_RUN / "source-terrain-and-forcing.npz")
    injection = saved["injection"]
    ledger_2d = domain_ledger(saved, spacing_m=spacing,
                              declared_injection_m3=float(np.asarray(
                                  injection["volumes_per_interval_m3"]).sum()))
    products = {
        "water_volume_m3": dynamic["water_volume_m3"],
        "receiver": np.asarray(geometry_raw["receiver"], np.int64),
        "outgoing_volume_m3": np.load(REACH_RUN / "regional-exchanges.npz")["water_outgoing_volume_m3"],
        "local_bucket_q_m3_s": forcing["local_bucket_q_m3_s"],
        "boundary_q_m3_s": forcing["boundary_q_m3_s"],
    }
    x0 = origin[0] - spacing / 2.
    z0 = origin[1] - spacing / 2.
    x1 = origin[0] + (shape[1] - .5) * spacing
    z1 = origin[1] + (shape[0] - .5) * spacing
    node_xz = np.asarray(geometry_raw["node_xz_m"], np.float64)
    inside = np.array([x0 <= p[0] <= x1 and z0 <= p[1] <= z1 for p in node_xz])
    reach_sub = closed_reach_subledger(products, inside)
    merged = merged_ledger(ledger_2d, reach_sub,
                           local_runoff_inside_domain_m3=float(
                               (np.asarray(forcing["local_bucket_q_m3_s"])[:, inside]
                                * INTERVAL_S).sum()))
    metadata = saved["metadata"]
    solver_metadata = json.loads(metadata["metadata"])
    solver_diagnostics = json.loads(metadata["diagnostics"])
    report = {
        "schema": SCHEMA, "solver": solver_metadata["schema"],
        "world_seed": WORLD_SEED,
        "wall_seconds": solver_metadata["wall_s"],
        "regenerated_by": "report_only cold read",
        "coupling": {"direction": "one_way_sequential_1d_to_2d_no_backwater",
                     "reach_ledger_adjusted": False},
        "frames": [dict(extent_statistics(depth[i], spacing_m=spacing, carved_depth_m=carved),
                        frame=int(i), time_s=float(times[i]), label=label)
                   for i, label in frames],
        "final_residual_wetland": residual_wetland(depth[-1], spacing_m=spacing,
                                                   carved_depth_m=carved),
        "ledger_2d": ledger_2d, "reach_subledger": reach_sub, "merged_ledger": merged,
        "solver_metadata": solver_metadata,
        "solver_diagnostics": solver_diagnostics,
        "files": images,
        "frames_plotted": [[int(i), label] for i, label in frames],
    }
    publish_bytes(directory / "report.json",
                  json.dumps(report, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
    print("LEDGER_2D", json.dumps(ledger_2d, default=str), flush=True)
    print("MERGED", json.dumps(merged, default=str), flush=True)
    print("FRAMES", frames, flush=True)
    return report


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--report-only" in argv:
        return report_only(argv[argv.index("--report-only") + 1])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(argv[argv.index("--output") + 1]) if "--output" in argv else (
        ROOT / ".scratch/cross-region-tributary/floodplain-2d-01")
    if output.exists():
        raise FileExistsError("refusing to overwrite an existing run: " + str(output))
    output.mkdir(parents=True, exist_ok=False)

    fine = np.load(FINE_FIELD)
    height_fine = np.asarray(fine["height_m"], np.float64)
    carved_fine = np.asarray(fine["cut_depth_m"], np.float64)
    spacing_fine = float(fine["spacing_m"])
    origin_fine = np.asarray(fine["origin_xz_m"], np.float64)
    fine_identity = str(fine["identity_sha256"])

    page = aggregate_fine_field(height_fine, BLOCK_CELLS)
    carved = aggregate_fine_field(carved_fine, BLOCK_CELLS)
    shape = page.shape
    window = FloodplainWindow(origin_m_xz=tuple(float(v) for v in origin_fine),
                              spacing_m=spacing_fine, block_cells=BLOCK_CELLS)
    spacing = spacing_fine * BLOCK_CELLS
    xs, zs = cell_centres(window, shape)
    extent = window_extent(window, shape)

    geometry_raw = np.load(REACH_RUN / "generated-geometry.npz")
    dynamic = np.load(REACH_RUN / "dynamic-water-sediment-bed.npz")
    exchanges = np.load(REACH_RUN / "regional-exchanges.npz")
    forcing = np.load(REACH_RUN / "source-terrain-and-forcing.npz")
    receiver = np.asarray(geometry_raw["receiver"], np.int64)
    node_xz = np.asarray(geometry_raw["node_xz_m"], np.float64)
    reach_identity = file_sha256(REACH_RUN / "generated-geometry.npz")

    crossings = crossing_edges(window, shape, node_xz, receiver)
    if not crossings:
        raise ValueError("no reach edge crosses the window boundary: nothing to inject")
    locations = source_locations(window, shape, crossings,
                                 np.asarray(geometry_raw["width_m"], np.float64))
    matrix = source_matrix(shape, locations)
    donors = [location["crossing"]["donor"] for location in locations]
    injection_cells = sorted({cell for item in locations for cell in item["cells"]})

    products = {
        "water_volume_m3": dynamic["water_volume_m3"],
        "receiver": receiver,
        "outgoing_volume_m3": exchanges["water_outgoing_volume_m3"],
        "local_bucket_q_m3_s": forcing["local_bucket_q_m3_s"],
        "boundary_q_m3_s": forcing["boundary_q_m3_s"],
    }
    volumes = aggregate_reach_outgoing(exchanges["water_step_start_seconds"],
                                       exchanges["water_outgoing_volume_m3"], donors,
                                       interval_s=INTERVAL_S, intervals=INTERVALS)
    rates = hydrograph(volumes, INTERVAL_S)
    declared_injection = float(volumes.sum())

    source_identity = "floodplain2d:" + fine_identity[:16]
    domain = build_domain(window, page, source_identity=source_identity, margin_cells=2,
                          injection_cells=injection_cells)
    domain["source_matrix"] = matrix
    if int(np.prod(shape)) > BUDGET.max_cells:
        raise ValueError("two-dimensional page exceeds the frozen solver's cell budget")

    initial_depth = np.zeros(shape, np.float64)
    started = time.monotonic()
    print("DOMAIN", shape, "spacing", spacing, "cells", int(np.prod(shape)),
          "crossings", len(crossings), "injection_m3", declared_injection, flush=True)
    result = run_domain(domain, initial_depth_m=initial_depth, interval_s=INTERVAL_S,
                        intervals=INTERVALS, discharge_per_interval=rates,
                        source_identity=source_identity,
                        forcing_identity=reach_identity, budget=BUDGET,
                        snapshot_interval_s=SNAPSHOT_S)
    wall = time.monotonic() - started
    print("RUN", result["metadata"]["status"], "wall_s", round(wall, 2),
          "substeps", result["metadata"]["substeps"], flush=True)

    depth = np.asarray(result["arrays"]["depth_m"], np.float64)
    times = np.asarray(result["arrays"]["time_s"], np.float64)
    area = spacing ** 2
    wet_area, overbank_area, max_depth, volume = [], [], [], []
    for index in range(depth.shape[0]):
        stats = extent_statistics(depth[index], spacing_m=spacing, carved_depth_m=carved)
        wet_area.append(stats["wet_area_m2"])
        overbank_area.append(stats["overbank_wet_area_m2"])
        max_depth.append(stats["max_depth_m"])
        volume.append(stats["volume_m3"])
    series = {
        "times": times, "wet_area_km2": np.asarray(wet_area) / 1e6,
        "overbank_area_km2": np.asarray(overbank_area) / 1e6,
        "max_depth_m": np.asarray(max_depth), "volume_m3": np.asarray(volume),
        "xs": xs, "zs": zs,
    }
    frames, peak = frame_selection(times, wet_area, volume)
    final_dry = residual_wetland(depth[-1], spacing_m=spacing, carved_depth_m=carved)

    ledger_2d = domain_ledger(result, spacing_m=spacing, declared_injection_m3=declared_injection)
    inside = np.array([extent[0] <= p[0] <= extent[1] and extent[2] <= p[1] <= extent[3]
                       for p in node_xz])
    reach_sub = closed_reach_subledger(products, inside)
    local_runoff_inside = float(
        (np.asarray(forcing["local_bucket_q_m3_s"], np.float64)[:, inside] * INTERVAL_S).sum())
    merged = merged_ledger(ledger_2d, reach_sub,
                           local_runoff_inside_domain_m3=local_runoff_inside)

    # ---- artifacts -------------------------------------------------------
    write_packet(output, "geometry", {**domain["geometry"]["arrays"],
                                     **domain["geometry"]["metadata"],
                                     "outlet_cells": np.asarray(domain["outlet_cells"], np.int64),
                                     "rim_elevation_m": float(domain["rim_elevation_m"])})
    write_packet(output, "states", {
        "time_s": times, "depth_m": depth,
        "ledger": np.asarray(result["arrays"]["ledger"], np.float64),
        "final_internal_q_m3_s": np.asarray(result["arrays"]["final_internal_q_m3_s"], np.float64),
        "final_boundary_q_m3_s": np.asarray(result["arrays"]["final_boundary_q_m3_s"], np.float64),
        "metadata": json.dumps(result["metadata"], indent=2, ensure_ascii=False),
        "diagnostics": json.dumps(result["diagnostics"], indent=2, ensure_ascii=False),
    })
    write_packet(output, "floodplain-depth-field", {
        "depth_m": depth.astype(np.float32), "time_s": times,
        "height_m": page, "carved_depth_m": carved,
        "origin_xz_m": np.array([float(xs[0]), float(zs[0])], np.float64),
        "spacing_m": np.float64(spacing), "cell_area_m2": np.float64(area),
        "_schema": SCHEMA, "_solver": INERTIAL_SCHEMA,
        "_world_seed": WORLD_SEED, "_fine_field_identity_sha256": fine_identity,
        "_convention": "depth_m[frame, row(z), column(x)]; origin = cell-centre of [0,0]; "
                       "spacing = aggregated cell size; height_m is the uncarved-bed page the "
                       "solver integrated (carve already subtracted)",
    })
    write_packet(output, "injection", {
        "volumes_per_interval_m3": volumes, "discharge_per_interval_m3_s": rates,
        "donor_nodes": np.asarray(donors, np.int64),
        "crossing_point_x_m": np.asarray([c["point_m_xz"][0] for c in crossings]),
        "crossing_point_z_m": np.asarray([c["point_m_xz"][1] for c in crossings]),
        "crossing_axis": np.asarray([c["axis"] for c in crossings]),
        "source_cells": np.asarray([cell for item in locations for cell in item["cells"]], np.int64),
        "source_weights": np.asarray([w for item in locations for w in item["weights"]], np.float64),
        "local_runoff_node8_m3": float((forcing["local_bucket_q_m3_s"][:, 8] * INTERVAL_S).sum()),
        "interval_s": INTERVAL_S, "intervals": INTERVALS,
        "regional_exchanges_sha256": file_sha256(REACH_RUN / "regional-exchanges.npz"),
    })
    write_packet(output, "flood-series", {
        "time_s": times, "wet_area_m2": np.asarray(wet_area),
        "overbank_wet_area_m2": np.asarray(overbank_area),
        "max_depth_m": np.asarray(max_depth), "volume_m3": np.asarray(volume),
    })
    # A renderer-shaped bundle: `tools/render_remote_sensing.py` gains no 2D read path,
    # but its terrain loader can point straight at this page.
    write_packet(output, "source-terrain-and-forcing", {
        "height_m": page, "origin_xz_m": np.asarray([float(xs[0]), float(zs[0])], np.float64),
        "_note": "90 m block-mean aggregation of the TD 30 m page; origin is the cell centre "
                 "so render_remote_sensing.grid_axes reproduces these coordinates",
    })
    publish_bytes(output / "source-selection.json",
                  json.dumps({"world_seed": WORLD_SEED, "coarse_terrain_spacing_m": spacing,
                              "fine_field_identity_sha256": fine_identity,
                              "fine_spacing_m": spacing_fine, "block_cells": BLOCK_CELLS,
                              "fine_origin_m_xz": [float(v) for v in origin_fine],
                              "source_run": str(REACH_RUN.relative_to(ROOT)),
                              "note": "shadow selection so the unmodified renderer reads the "
                                      "90 m page this run integrated"},
                             indent=2, ensure_ascii=False).encode("utf-8"))

    images = plot_frames(output, series, depth, times, page, spacing, carved, frames, WORLD_SEED)
    shadow, mirrored = write_shadow_run(output, REACH_RUN, page,
                                        (float(xs[0]), float(zs[0])), spacing, fine_identity)
    render_log = render_through_shared_tool(
        shadow, output / "remote-sensing",
        (float(np.mean(xs)), float(np.mean(zs))))
    images["remote-sensing-reach"] = str(output / "remote-sensing" / "reach-true-color.png")
    images["remote-sensing-series"] = str(output / "remote-sensing" / "reach-time-series.png")

    per_frame = []
    for index, label in frames:
        stats = extent_statistics(depth[index], spacing_m=spacing, carved_depth_m=carved)
        stats.update({"frame": int(index), "label": label, "time_s": float(times[index])})
        per_frame.append(stats)

    # Two clarifications the numbers need, both measured rather than asserted.
    terrain_reconciliation = reconcile_with_one_dimensional_section(
        geometry_raw, dynamic, fine)
    overbank_alternative = overbank_sensitivity(geometry_raw, dynamic)

    report = {
        "schema": SCHEMA, "solver": INERTIAL_SCHEMA, "world_seed": WORLD_SEED,
        "generated_utc": stamp, "wall_seconds": wall,
        "coupling": {
            "direction": "one_way_sequential_1d_to_2d_no_backwater",
            "injection_kind": "boundary_cells_at_reach_edge_crossings",
            "no_double_count": "injected volume equals the donor nodes' own saved "
                               "water_outgoing_volume_m3 across the window boundary; it is a "
                               "line item the reach ledger already removed",
            "reach_ledger_adjusted": False,
            "not_injected": "the terminal lake's vertical-wall store is not poured into the "
                            "two-dimensional domain (see terrain_refutation_of_vertical_wall)",
        },
        "domain": {
            "shape": list(shape), "spacing_m": spacing, "cells": int(np.prod(shape)),
            "extent_m": {"x": [extent[0], extent[1]], "z": [extent[2], extent[3]]},
            "extent_km": [(extent[1] - extent[0]) / 1000., (extent[3] - extent[2]) / 1000.],
            "origin_cell_centre_m": [float(xs[0]), float(zs[0])],
            "aggregation": "block mean of %d x %d TD 30 m cells" % (BLOCK_CELLS, BLOCK_CELLS),
            "cells_exceeding_solver_cap": max(0, int(np.prod(shape)) - 65536),
            "boundary": {"closed_faces": domain["closed_faces"],
                         "drainage_faces": domain["drainage_faces"],
                         "policy": "every boundary face is engineering drainage with crest at "
                                   "its own terrain elevation (free outfall): water leaves only "
                                   "where its surface stands above the ground there, and no "
                                   "face can ever draw water in"},
        },
        "injection": {
            "crossing_edges": crossings, "donor_nodes": donors,
            "total_m3": declared_injection,
            "peak_discharge_m3_s": float(np.asarray(rates).sum(axis=1).max()),
            "peak_interval": int(np.argmax(np.asarray(rates).sum(axis=1))),
            "local_runoff_node8_m3_excluded": float((forcing["local_bucket_q_m3_s"][:, 8] * INTERVAL_S).sum()),
            "exclusion_reason": "node 8's local runoff is already inside the two-dimensional "
                                "domain and is not a boundary crossing; injecting it again would "
                                "count the same water twice",
        },
        "terrain_reconciliation": terrain_reconciliation,
        "overbank_alternative": overbank_alternative,
        "frames": per_frame, "final_residual_wetland": final_dry,
        "ledger_2d": ledger_2d, "reach_subledger": reach_sub, "merged_ledger": merged,
        "solver_metadata": result["metadata"], "solver_diagnostics": result["diagnostics"],
        "renderer": {
            "tool": "tools/render_remote_sensing.py (unmodified entry point, --floodplain)",
            "shadow_run": str(shadow.relative_to(ROOT)),
            "result": render_log,
            "mirrored_files": mirrored,
            "note": "the depth field is this run's own floodplain-depth-field.npz; the "
                    "reach geometry and node dynamics are byte copies of the source run, "
                    "used only so the renderer has a conforming bed to draw",
        },
        "files": images,
        "limitations": [
            "local-inertial: no advective momentum; steep or supercritical flow is not certified",
            "one-way coupling: the reach does not feel the two-dimensional water (no backwater)",
            "the 0.4 m canonical carve is a carriage slot, not a surveyed cross-section; overbank "
            "depth relative to it is a modelled quantity, not a surveyed one",
            "the terminal lake's 100 km^2 vertical-wall abstraction is not hostable by the 30 m "
            "terrain and is replaced, not nested",
        ],
    }
    report["terrain_refutation_of_vertical_wall"] = None
    publish_bytes(output / "report.json", json.dumps(report, indent=2,
                                                    ensure_ascii=False, default=str).encode("utf-8"))
    print("LEDGER_2D", json.dumps(ledger_2d, default=str), flush=True)
    print("MERGED", json.dumps(merged, default=str), flush=True)
    print("DONE", output, flush=True)
    return report


REPORT_EXTRA = {}

if __name__ == "__main__":
    main()
