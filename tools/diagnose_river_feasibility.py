"""Offline first-cause diagnostics and read-only coast candidate scan."""

import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.surface_rivers import GridInput, route
from terrain_pipeline.surface_rivers.diagnostics import RiverDiagnostics, route_cut_lower_bound
from terrain_pipeline.surface_rivers.pipeline import process
from tools.verify_metric_rivers import SOURCE_ROOT, SAMPLES, SPACING_M, RUNOFF_M_PER_S
from tools.verify_metric_rivers import THRESHOLD_M3_PER_S, MAX_INCISION_M, SEA_M


OUTPUT_ROOT = ROOT / "verification/river-feasibility"
SCAN_ROOTS = (ROOT / "verification/tuned-model", ROOT / "verification/height-budget-v3",
              ROOT / "verification/height-budget-v4",
              ROOT / "verification/height-budget-confirmation",
              ROOT / "verification/height-budget-v5")
HALO = 13


def _read_source(path):
    with np.load(path, allow_pickle=False) as archive:
        if "elevation" not in archive or "metadata" not in archive or "generation_config" not in archive:
            return None
        elevation = archive["elevation"].copy()
        metadata = json.loads(str(archive["metadata"].item()))
        config = json.loads(str(archive["generation_config"].item()))
    if (elevation.shape != (513, 513) or not np.isfinite(elevation).all() or
            config.get("conditioning_mode") not in ("geographic_v3", "geographic_v4", "geographic_v5") or
            metadata.get("identity") is None or metadata.get("native_resolution_m") != 30):
        return None
    return elevation, metadata, config


def _boundary_connected_ocean(height, sea):
    ocean = height <= sea
    boundary = np.zeros(height.shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    starts = np.flatnonzero(ocean & boundary)
    if starts.size == 0:
        return np.zeros(height.shape, dtype=bool)
    connected = np.zeros(height.shape, dtype=bool)
    stack = [int(value) for value in starts]
    rows, cols = height.shape
    while stack:
        cell = stack.pop()
        if connected.flat[cell]:
            continue
        connected.flat[cell] = True
        z, x = divmod(cell, cols)
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = z + dz, x + dx
            if 0 <= nz < rows and 0 <= nx < cols and ocean[nz, nx] and not connected[nz, nx]:
                stack.append(nz * cols + nx)
    return connected


def _coast_catchments(height, connected_ocean):
    rows, cols = height.shape
    boundary = np.zeros(height.shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    if not connected_ocean.any():
        return []
    # Each connected-ocean cell terminates land routing at the first shoreline crossing.
    routing = route(height, connected_ocean, 30.0)
    mouth = np.full(height.size, -1, dtype=np.int64)
    land = height > 0
    land_flat = land.ravel()
    donors = np.zeros(height.size, dtype=np.int32)
    for cell in routing.order:
        target = routing.receiver[cell]
        mouth[cell] = cell if connected_ocean.flat[cell] else (mouth[target] if target >= 0 else -1)
        if target >= 0 and land_flat[cell] and land_flat[target]:
            donors[target] += 1
    groups = []
    for outlet in np.unique(mouth[land_flat]):
        if outlet < 0:
            continue
        members = (mouth.reshape(height.shape) == outlet) & land
        if not members.any():
            continue
        fill = routing.routing_height - height
        z, x = divmod(int(outlet), cols)
        groups.append({"first_ocean_cell_grid_zx": [z, x],
                       "land_cells": int(np.count_nonzero(members)),
                       "land_boundary_cells": int(np.count_nonzero(members & boundary)),
                       "observed_window_closed": not bool(np.any(members & boundary)),
                       "land_d8_donor_junction_cells": int(np.count_nonzero(members.ravel() & (donors >= 2))),
                       "junction_note": "at least two land D8 donors; does not establish two thresholded river tributaries",
                       "land_relief_m": float(np.ptp(height[members])),
                       "working_fill_max_m": float(np.max(fill[members])),
                       "working_fill_cells": int(np.count_nonzero((fill > 1e-9) & members)),
                       "spill_note": "working fill estimates a basin spill level under connected-ocean outlets; lake balance and legal spill remain unverified"})
    groups.sort(key=lambda group: group["land_cells"], reverse=True)
    return groups


def _flowline_cut_estimate(height, receiver, order, flowline, cap_m):
    working = height.ravel().copy()
    source = working.copy()
    active = flowline.ravel()
    for cell in order[::-1]:
        target = receiver[cell]
        if target >= 0 and active[cell] and active[target]:
            working[target] = min(working[target], working[cell] - .01)
    cut = source[active] - working[active]
    return {"flowline_cells": int(cut.size),
            "max_m": float(cut.max()) if cut.size else 0.,
            "p50_m": float(np.quantile(cut, .5)) if cut.size else 0.,
            "p90_m": float(np.quantile(cut, .9)) if cut.size else 0.,
            "p99_m": float(np.quantile(cut, .99)) if cut.size else 0.,
            "above_cap_cells": int(np.count_nonzero(cut > cap_m + 1e-9)),
            "scope": "fixed-route flowline bed-only cut, before width, banks, stage, spill or outlet replanning; not a total cut budget"}


def scan_saved_sources():
    seen = set()
    candidates = []
    count = 0
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.npz"):
            loaded = _read_source(path)
            if loaded is None:
                continue
            elevation, metadata, config = loaded
            key = (metadata.get("identity"), metadata.get("seed"),
                   tuple(metadata.get("native_origin", [])), elevation.shape)
            if key in seen:
                continue
            seen.add(key)
            count += 1
            if not (float(elevation.min()) < 0 < float(elevation.max())):
                continue
            ocean = _boundary_connected_ocean(elevation, 0)
            boundary = np.zeros(elevation.shape, dtype=bool)
            boundary[0, :] = boundary[-1, :] = True
            boundary[:, 0] = boundary[:, -1] = True
            land_boundary = int(np.count_nonzero((elevation > 0) & boundary))
            edges = {"north": int(np.count_nonzero(elevation[0, :] > 0)),
                     "south": int(np.count_nonzero(elevation[-1, :] > 0)),
                     "west": int(np.count_nonzero(elevation[:, 0] > 0)),
                     "east": int(np.count_nonzero(elevation[:, -1] > 0))}
            candidates.append({"source_npz": str(path.relative_to(ROOT)),
                               "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                               "generation_identity": metadata.get("identity"),
                               "profile": config.get("conditioning_mode"),
                               "seed": metadata.get("seed"),
                               "native_origin": metadata.get("native_origin"),
                               "shape": list(elevation.shape),
                               "min_relative_elevation_m": float(elevation.min()),
                               "max_relative_elevation_m": float(elevation.max()),
                               "boundary_connected_ocean_cells": int(np.count_nonzero(ocean)),
                               "land_boundary_cells": land_boundary,
                               "land_boundary_edge_counts": edges,
                               "window_closed_land": land_boundary == 0,
                               "coast_catchments": _coast_catchments(elevation, ocean),
                               "note": "A closed observed window is not proof of a complete global watershed."})
    return {"unique_sources_scanned": count, "mixed_land_ocean_candidates": candidates}


def diagnose_saved_mountains(output):
    findings = {}
    for name, phase, seed, x, z in SAMPLES[:2]:
        path = SOURCE_ROOT / phase / f"seed{seed}-x{x}-z{z}.npz"
        loaded = _read_source(path)
        if loaded is None:
            raise ValueError(f"missing source {path}")
        elevation, metadata, config = loaded
        from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, process_region
        processed = process_region(elevation.astype(np.float64) + SEA_M, SEA_M,
                                   SPACING_M, SPACING_M,
                                   recipe=METRIC_30M_RECIPE_V1).elevation_m
        height = processed[HALO:-HALO, HALO:-HALO]
        edge = np.zeros(height.shape, dtype=bool)
        edge[0, :] = edge[-1, :] = True
        edge[:, 0] = edge[:, -1] = True
        outlet = np.zeros(height.shape, dtype=bool)
        outlet.flat[int(np.argmin(np.where(edge, height, np.inf)))] = True
        grid = GridInput(height, SPACING_M, ((x + HALO) * SPACING_M, (z + HALO) * SPACING_M),
                         np.full(height.shape, RUNOFF_M_PER_S), outlet)
        routing = route(grid.height, grid.outlet_mask, grid.spacing_blocks)
        cut = route_cut_lower_bound(grid.height, routing.receiver, routing.order, MAX_INCISION_M)
        diagnostics = RiverDiagnostics(height.shape)
        result = process(grid, THRESHOLD_M3_PER_S, MAX_INCISION_M, diagnostics)
        flowline_cut = _flowline_cut_estimate(grid.height, routing.receiver, routing.order,
                                              result.flowline_mask, MAX_INCISION_M)
        first = diagnostics.first_cause
        summary = diagnostics.summary()
        np.savez_compressed(output / f"{name}-diagnostics.npz",
                            first_cause=first, required_extra_cut_m=diagnostics.required_extra_cut_m,
                            fixed_route_cut_lower_bound_m=cut["cut_m"],
                            unresolved_mask=result.unresolved_mask,
                            flowline_mask=result.flowline_mask,
                            routing_fill_m=routing.routing_height - grid.height,
                            **{f"cause_{key}": value for key, value in diagnostics.causes.items()},
                            **{f"propagation_{key}": value for key, value in diagnostics.propagation.items()})
        findings[name] = {"source_npz": str(path.relative_to(ROOT)),
                          "generation_identity": metadata["identity"],
                          "first_cause": summary,
                          "fixed_route_cut_lower_bound_max_m": cut["max_cut_m"],
                          "fixed_route_cut_above_4m_cells": cut["above_cap_cells"],
                          "fixed_route_flowline_cut": flowline_cut,
                          "fixed_route_cut_scope": "all cells of the fixed D8 route, including non-channel cells; not the actual channel-only correction",
                          "diagnostic_masks_npz": f"{name}-diagnostics.npz",
                          "routing_fill_max_m": float((routing.routing_height - grid.height).max()),
                          "unresolved_cells": int(np.count_nonzero(result.unresolved_mask)),
                          "unresolved_core_cells": int(np.count_nonzero(result.unresolved_mask & result.flowline_mask)),
                          "outlet_grid_zx": [int(v) for v in np.argwhere(outlet)[0]],
                          "artificial_outlet": True,
                          "cut_note": "Cut-only lower bound along the fixed D8 route with 0.01 m per edge drop; not globally optimized, not a publication plan."}
        print(name, findings[name]["unresolved_core_cells"], flush=True)
    return findings


def main():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    output.mkdir()
    result = {"purpose": "first-cause river diagnostics and saved-source coast scan",
              "old_algorithm_outputs_unchanged": True,
              "mountains": diagnose_saved_mountains(output),
              "saved_source_scan": scan_saved_sources()}
    (output / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
