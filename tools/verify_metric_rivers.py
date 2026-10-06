"""Offline surface-river diagnostic on saved metre-scale v5 model windows."""

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from diffusion.config import GenerationConfig
from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, process_region
from terrain_pipeline.surface_rivers import GridInput, route
from terrain_pipeline.surface_rivers.pipeline import process, save
from terrain_pipeline.surface_rivers.postvalidate import geometry_issues
from tools.preview_surface_rivers import profile_indices


SOURCE_ROOT = ROOT / "verification/height-budget-v5/run-20260929T103819083596Z"
OUTPUT_ROOT = ROOT / "verification/metric-rivers"
SAMPLES = (
    ("pressure_mountain", "screen-3", 20260931, 0, 0),
    ("normal_mountain", "screen-3", 20260931, 11520, 15360),
    ("coast_candidate", "holdout", 20261004, -16000, -13952),
)
SPACING_M = 30.0
RUNOFF_M_PER_S = 1e-8
THRESHOLD_M3_PER_S = .05
MAX_INCISION_M = 4.0
SEA_M = 126.0
HALO_X, HALO_Z = METRIC_30M_RECIPE_V1.required_halo_samples(SPACING_M, SPACING_M)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _same(a, b):
    return np.array_equal(a, b, equal_nan=True) if np.issubdtype(a.dtype, np.floating) else np.array_equal(a, b)


def _write_report(output, report):
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")


def _wet_reached(water, outlet):
    wet = np.isfinite(water)
    reached = np.zeros(wet.shape, dtype=bool)
    queue = deque(map(tuple, np.argwhere(wet & outlet)))
    while queue:
        z, x = queue.popleft()
        if reached[z, x]:
            continue
        reached[z, x] = True
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = z + dz, x + dx
            if 0 <= nz < wet.shape[0] and 0 <= nx < wet.shape[1] and wet[nz, nx] and not reached[nz, nx]:
                queue.append((nz, nx))
    return reached


def _profile_plot(destination, name, grid, result):
    routing = route(grid.height, grid.outlet_mask, grid.spacing_blocks)
    indices = profile_indices(routing.receiver, result.flowline_mask, grid.outlet_mask)
    z, x = np.unravel_index(indices, grid.height.shape)
    distance = np.zeros(indices.size)
    distance[1:] = np.cumsum(np.hypot(np.diff(z), np.diff(x)) * SPACING_M)
    fig, ax = plt.subplots(figsize=(11, 4), constrained_layout=True)
    ax.plot(distance, grid.height[z, x], label="processed input")
    ax.plot(distance, result.height[z, x], label="river bed")
    ax.plot(distance, result.water_surface[z, x], label="water")
    unresolved = result.unresolved_mask[z, x]
    ax.scatter(distance[unresolved], result.height[z, x][unresolved], s=9, color="red",
               label="unresolved")
    ax.set(xlabel="Upstream to artificial outlet (m)", ylabel="Core elevation (m)",
           title=name)
    ax.legend()
    fig.savefig(destination / f"{name}-profile.png", dpi=150)
    plt.close(fig)
    return {"cells": int(indices.size), "unresolved_cells": int(np.count_nonzero(unresolved)),
            "length_m": float(distance[-1])}


def verify_one(output, name, phase, seed, x, z):
    source = SOURCE_ROOT / phase / f"seed{seed}-x{x}-z{z}.npz"
    source_hash = _hash(source)
    with np.load(source, allow_pickle=False) as archive:
        elevation = archive["elevation"].copy()
        metadata = json.loads(str(archive["metadata"].item()))
        config = json.loads(str(archive["generation_config"].item()))
    source_report = SOURCE_ROOT / phase / "report.json"
    reported = json.loads(source_report.read_text(encoding="utf-8"))
    source_entry = next((item for item in reported["samples"] if item["seed"] == seed and
                         item["native_origin"] == [x, z]), None)
    if (elevation.shape != (513, 513) or elevation.dtype != np.float32 or
            not np.isfinite(elevation).all() or metadata["native_origin"] != [x, z] or
            int(metadata["seed"]) != seed or metadata["native_resolution_m"] != SPACING_M or
            config["conditioning_mode"] != "geographic_v5" or
            config["v5_base_headroom_m"] != 120.0 or
            metadata["identity"] != GenerationConfig(**config).identity()[0] or
            metadata["identity"] != reported["generation_identity"] or
            reported["generation_config"] != config or source_entry is None or
            source_entry["raw_sha256"] != source_hash):
        raise ValueError("v5 source identity or grid mismatch")
    core = elevation.astype(np.float64) + SEA_M
    processed = process_region(core, SEA_M, SPACING_M, SPACING_M,
                               recipe=METRIC_30M_RECIPE_V1).elevation_m
    interior = np.s_[HALO_Z:513-HALO_Z, HALO_X:513-HALO_X]
    height = processed[interior].copy()
    land_cells = int(np.count_nonzero(height > SEA_M))
    entry = {"sample": name, "seed": seed, "native_origin": [x, z],
             "source_npz": str(source.relative_to(ROOT)), "source_sha256": source_hash,
             "source_report": str(source_report.relative_to(ROOT)),
             "generation_identity": metadata["identity"], "source_config": config,
             "shape": list(height.shape), "core_sea_elevation_m": SEA_M,
             "spacing_m": SPACING_M, "origin_core_m_xz": [(x + HALO_X) * SPACING_M,
                                                           (z + HALO_Z) * SPACING_M],
             "unit_bridge": "1 core metre = 1 legacy block for this diagnostic only",
             "legacy_spacing_blocks": SPACING_M,
             "runoff_m_per_s": RUNOFF_M_PER_S,
             "runoff_note": "constant diagnostic input, not climate-calibrated rainfall",
             "threshold_q_m3_per_s": THRESHOLD_M3_PER_S,
             "max_incision_m": MAX_INCISION_M,
             "land_cells_above_core_sea": land_cells,
             "outlet_note": "lowest boundary sample is an artificial diagnostic outlet, not a natural river mouth"}
    if land_cells == 0:
        entry["status"] = "not_applicable_all_ocean"
        entry["river_pass"] = None
        return entry
    edge = np.zeros(height.shape, dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    outlet_flat = int(np.argmin(np.where(edge, height, np.inf)))
    outlet = np.zeros(height.shape, dtype=bool)
    outlet.flat[outlet_flat] = True
    origin = tuple(entry["origin_core_m_xz"])
    grid = GridInput(height, SPACING_M, origin,
                     np.full(height.shape, RUNOFF_M_PER_S), outlet)
    result = process(grid, THRESHOLD_M3_PER_S, MAX_INCISION_M)
    entry["outlet_grid_zx"] = [int(v) for v in np.unravel_index(outlet_flat, height.shape)]
    entry["input_total_m3_per_s"] = float(result.metadata["input_total"])
    entry["outlet_total_m3_per_s"] = float(result.metadata["outlet_total"])
    entry["budget_residual_m3_per_s"] = float(result.metadata["residual"])
    core_unresolved = result.unresolved_mask & result.flowline_mask
    flank_unresolved = result.unresolved_mask & ~result.flowline_mask
    entry["flowline_cells"] = int(np.count_nonzero(result.flowline_mask))
    entry["max_width_legacy_blocks"] = float(np.max(result.width_blocks))
    entry["width_calibration_note"] = ("legacy channel width is coupled to spacing_blocks; "
                                       "at 30 m spacing its minimum active width is 30 m and cap is 150 m, "
                                       "not a calibrated physical river width")
    entry["unresolved_total_cells"] = int(np.count_nonzero(result.unresolved_mask))
    entry["unresolved_core_cells"] = int(np.count_nonzero(core_unresolved))
    entry["unresolved_flank_cells"] = int(np.count_nonzero(flank_unresolved))
    entry["dry_core_cells"] = int(np.count_nonzero(result.flowline_mask &
                                                  ~np.isfinite(result.water_surface)))
    reached = _wet_reached(result.water_surface, outlet)
    entry["wet_core_disconnected_cells"] = int(np.count_nonzero(
        result.flowline_mask & np.isfinite(result.water_surface) & ~reached))
    leak, disconnected = geometry_issues(result.height, result.water_surface,
                                         result.flowline_mask, result.receiver,
                                         result.outlet_mask)
    entry["postmask_leak_cells"] = int(np.count_nonzero(leak))
    entry["postmask_disconnected_core_cells"] = int(np.count_nonzero(disconnected))
    wet = np.isfinite(result.water_surface)
    entry["wet_bed_relation_violations"] = int(np.count_nonzero(
        wet & (result.water_surface <= result.height + 1e-6)))
    entry["max_incision_observed_m"] = float(np.max(grid.height - result.height))
    entry["profile"] = _profile_plot(output, name, grid, result)
    artifact = output / f"{name}.npz"
    save(artifact, result)
    with np.load(artifact, allow_pickle=False) as loaded:
        arrays = {"input_height": result.input_height, "processed_height": result.height,
                  "vdm_dy": result.vdm_dy, "water_surface": result.water_surface,
                  "discharge": result.discharge, "receiver": result.receiver,
                  "channel_mask": result.channel_mask, "flowline_mask": result.flowline_mask,
                  "width_blocks": result.width_blocks,
                  "unresolved_mask": result.unresolved_mask, "outlet_mask": result.outlet_mask}
        entry["saved_arrays_equal_on_reload"] = all(_same(loaded[key], value)
                                                     for key, value in arrays.items())
    entry["river_npz"] = artifact.name
    entry["river_npz_sha256"] = _hash(artifact)
    entry["source_hash_unchanged"] = _hash(source) == source_hash
    entry["river_pass"] = bool(entry["unresolved_total_cells"] == 0 and
                               entry["flowline_cells"] > 0 and
                               entry["dry_core_cells"] == 0 and
                               entry["wet_core_disconnected_cells"] == 0 and
                               entry["postmask_leak_cells"] == 0 and
                               entry["postmask_disconnected_core_cells"] == 0 and
                               entry["wet_bed_relation_violations"] == 0 and
                               entry["max_incision_observed_m"] <= MAX_INCISION_M + 1e-8 and
                               abs(entry["budget_residual_m3_per_s"]) < 1e-7 and
                               entry["saved_arrays_equal_on_reload"] and
                               entry["source_hash_unchanged"])
    entry["status"] = "pass" if entry["river_pass"] else "unresolved"
    sidecar = output / f"{name}-provenance.json"
    sidecar.write_text(json.dumps({
        "river_npz": artifact.name, "river_npz_sha256": entry["river_npz_sha256"],
        "source_npz": entry["source_npz"], "source_sha256": source_hash,
        "generation_identity": metadata["identity"],
        "unit_bridge": entry["unit_bridge"], "spacing_m": SPACING_M,
        "legacy_spacing_blocks": SPACING_M, "origin_core_m_xz": entry["origin_core_m_xz"],
        "core_sea_elevation_m": SEA_M, "runoff_m_per_s": RUNOFF_M_PER_S,
        "runoff_note": entry["runoff_note"], "threshold_q_m3_per_s": THRESHOLD_M3_PER_S,
        "max_incision_m": MAX_INCISION_M, "outlet_note": entry["outlet_note"],
        "status": entry["status"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    entry["provenance_sidecar"] = sidecar.name
    return entry


def main():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    output.mkdir()
    report = {"purpose": "offline metre-scale v5 surface-river diagnostic",
              "legacy_recipe": "surface-routing-width-channel-v4",
              "acceptance_note": "Unresolved NaN water is a failure; conservation alone is insufficient. Artificial boundary outlets are not natural river mouths.",
              "samples": {}, "all_applicable_pass": None}
    for name, phase, seed, x, z in SAMPLES:
        report["samples"][name] = verify_one(output, name, phase, seed, x, z)
        _write_report(output, report)
        print(name, report["samples"][name]["status"], flush=True)
    applicable = [item for item in report["samples"].values() if item["river_pass"] is not None]
    report["all_applicable_pass"] = bool(applicable and all(item["river_pass"] for item in applicable))
    _write_report(output, report)
    print(output, flush=True)


if __name__ == "__main__":
    main()
