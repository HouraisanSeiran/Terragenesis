"""Static HRU refinement experiment; no hydrology advancement or GPU work."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import checked_archive, file_sha256
from terrain_pipeline.climate_forcing import StormParameters, storm_generate_forcing as generate_forcing, interval_mean_mm_h, storm_load_forcing as load_forcing, save_forcing
from tools.verify_mountain_source_adapter import snapshot, assert_unchanged, write_json

SOURCE = ROOT / "verification/mountain-storm-forcing/run-20261001T071520828638Z"


def partition_bins(mask, lake_mask, origin, spacing_m, bin_m):
    """Merge lake-only bins via shortest selected-cell D4 bin adjacency path."""
    if (mask.dtype != np.bool_ or lake_mask.dtype != np.bool_ or mask.ndim != 2 or
            mask.shape != lake_mask.shape or not mask.any() or (lake_mask & ~mask).any()):
        raise ValueError("matching selected and lake footprints required")
    if (len(origin) != 2 or not np.isfinite(origin).all() or
            not np.isfinite(spacing_m) or spacing_m <= 0 or
            not np.isfinite(bin_m) or bin_m <= 0):
        raise ValueError("finite positive metre grid required")
    rows, columns = np.nonzero(mask)
    pairs = np.column_stack((np.floor((origin[0]+columns*spacing_m)/bin_m).astype(np.int64),
                             np.floor((origin[1]+rows*spacing_m)/bin_m).astype(np.int64)))
    bins, labels = np.unique(pairs, axis=0, return_inverse=True)
    original = np.full(mask.shape, -1, np.int64)
    original[mask] = labels
    land_counts = np.bincount(labels[~lake_mask[mask]], minlength=len(bins))
    land_bins = set(np.flatnonzero(land_counts).tolist())
    adjacency = [set() for _ in bins]
    for left, right in ((original[:-1], original[1:]), (original[:, :-1], original[:, 1:])):
        valid = (left >= 0) & (right >= 0) & (left != right)
        for first, second in zip(left[valid].tolist(), right[valid].tolist()):
            adjacency[first].add(second)
            adjacency[second].add(first)
    targets = np.arange(len(bins))
    merges = []
    for start in np.flatnonzero(land_counts == 0):
        frontier, visited, distance = {int(start)}, {int(start)}, 0
        while frontier and not (frontier & land_bins):
            frontier = set().union(*(adjacency[node] for node in frontier)) - visited
            visited.update(frontier)
            distance += 1
        candidates = frontier & land_bins
        if not candidates:
            raise ValueError("pure lake bin has no D4-selected-cell path to land bin")
        target = min(candidates, key=lambda node: (
            int(np.sum((bins[node]-bins[start])**2)), int(bins[node, 0]), int(bins[node, 1])))
        targets[start] = target
        merges.append({"from_bin": bins[start].tolist(), "to_bin": bins[target].tolist(),
                       "selected_D4_bin_hops": distance})
    retained, merged_labels = np.unique(targets[labels], return_inverse=True)
    if len(retained) > 256:
        raise ValueError("merged HRUs exceed frozen 256 limit")
    owner = np.full(mask.shape, -1, np.int64)
    owner[mask] = merged_labels
    counts = np.bincount(merged_labels, minlength=len(retained))
    final_land_counts = np.bincount(merged_labels[~lake_mask[mask]], minlength=len(retained))
    if not (final_land_counts > 0).all() or counts.sum() != mask.sum():
        raise ValueError("positive land area and unique selected area required")
    return owner, {"original_bins": len(bins), "HRUs": len(retained), "pure_lake_merges": merges,
        "representative_bins_east_south": bins[retained].tolist(),
        "counts": counts.tolist(), "land_counts": final_land_counts.tolist(),
        "lake_counts": (counts-final_land_counts).tolist(),
        "total_area_m2": float(counts.sum()*spacing_m**2)}


def error_metrics(owner, reference, means, lake_mask):
    labels = owner[owner >= 0]
    error = means[:, labels]-reference
    lake = lake_mask[owner >= 0]
    return {"max_cell_error_mm_h": float(np.abs(error).max()),
        "cell_rmse_mm_h": float(np.sqrt(np.mean(error**2))),
        "max_lake_error_mm_h": float(np.abs(error[:, lake]).max()) if lake.any() else 0.,
        "lake_rmse_mm_h": float(np.sqrt(np.mean(error[:, lake]**2))) if lake.any() else 0.,
        "max_signed_total_rain_rate_error_mm_h_cells": float(np.abs(error.sum(axis=1)).max())}


def verify(destination):
    if destination.exists():
        raise FileExistsError(destination)
    frozen = snapshot()
    before = {path.name: file_sha256(path) for path in SOURCE.iterdir() if path.is_file()}
    write_json(destination / "frozen-before.json", {"old_sources": frozen, "weather_071520": before})
    try:
        report = json.loads((SOURCE / "report.json").read_text(encoding="utf-8"))
        arrays = checked_archive(SOURCE / "pressure_mountain-eastward-coupling.npz",
            expected_sha256=report["cases"]["eastward"]["coupling_sha256"], max_bytes=768*1024*1024)
        manifest = json.loads(arrays.pop("manifest").tobytes().decode("utf-8"))
        saved = load_forcing(SOURCE / "eastward-weather.npz",
            expected_sha256=report["cases"]["eastward"]["weather_sha256"], cell_owner=arrays["cell_owner"],
            source_identity=report["source_identity"], selection_identity=report["selection_identity"])
        mask = arrays["hydrology_mask"]
        if not np.array_equal(saved["arrays"]["cell_owner"], arrays["cell_owner"]):
            raise ValueError("saved weather and coupling selected ownership differ")
        lake_nodes = [node for node, kind in enumerate(manifest["metadata"]["node_kind"]) if kind == "lake"]
        lake_mask = mask & np.isin(arrays["anchor_node"], lake_nodes)
        origin = saved["metadata"]["origin_m_xz"]
        rows, columns = np.nonzero(mask)
        east, south = origin[0]+columns*30., origin[1]+rows*30.
        result = {"status": "static_HRU_scale_error_and_unique_area_only", "group": 1378,
            "source_identity": report["source_identity"], "selection_identity": report["selection_identity"],
            "geometry_identity": report["geometry_identity"], "steps": 288, "dt_s": 900.,
            "cell_spacing_m": 30., "active_cells": int(mask.sum()), "scales": {},
            "merge_rule": "selected-cell D4 bin graph shortest hops; tie squared bin-centre distance then east/south lexicographic; lake-only bins move wholly to original positive-land bin",
            "reference": "same analytic time-average storm at 30m cell centres, not observed/subcell rainfall",
            "hydrology_advanced": False, "gpu_inference_run": False,
            "resource_budget": {"HRUs_max": 256, "steps": 288,
                "cell_evaluations_all_scales_and_references": int(mask.sum()*288*10),
                "estimated_working_array_bytes_max": 16*288*int(mask.sum())+16*288*256}}
        reference = {}
        for direction in ("eastward", "westward"):
            parameters = StormParameters(**report["cases"][direction]["parameters"])
            reference[direction] = np.stack([interval_mean_mm_h(east, south, step*900., (step+1)*900., parameters)
                                            for step in range(288)])
        for scale in (300, 150, 100, 60):
            owner, partition = partition_bins(mask, lake_mask, origin, 30., float(scale))
            partition["cases"] = {}
            partition["cell_flat"] = np.flatnonzero(mask).tolist()
            partition["cell_HRU"] = owner[mask].tolist()
            rains = {}
            for direction in ("eastward", "westward"):
                parameters = StormParameters(**report["cases"][direction]["parameters"])
                forcing = generate_forcing(owner, origin_m_xz=origin, spacing_m=30., steps=288, dt_s=900.,
                    start_s=0., parameters=parameters, source_identity=report["source_identity"],
                    selection_identity=report["selection_identity"])
                path = destination / f"{scale}m-{direction}-weather.npz"
                save_forcing(path, forcing)
                rain = forcing["arrays"]["rain_mm_h"]
                rains[direction] = rain
                metrics = error_metrics(owner, reference[direction], rain, lake_mask)
                metrics["total_rain_m3"] = float((rain*forcing["arrays"]["area_m2"]).sum()*.25/1000)
                metrics["weather_sha256"] = file_sha256(path)
                metrics["weather_identity"] = forcing["identity_sha256"]
                partition["cases"][direction] = metrics
                if scale == 300:
                    original = load_forcing(SOURCE / f"{direction}-weather.npz",
                        expected_sha256=report["cases"][direction]["weather_sha256"], cell_owner=arrays["cell_owner"],
                        source_identity=report["source_identity"], selection_identity=report["selection_identity"])
                    if not np.array_equal(rain, original["arrays"]["rain_mm_h"]):
                        raise ValueError("300m regenerated rain is not bitexact to frozen reference")
            partition["max_opposite_integrated_depth_difference_mm"] = float(np.abs(
                (rains["eastward"]-rains["westward"]).sum(axis=0)*.25).max())
            result["scales"][str(scale)] = partition
        result["proposal"] = {"bin_m": 100, "only_changed_parameter": "HRU partition with declared lake-only merge",
            "unchanged": ["source", "selection", "topology", "storm parameters", "900s dt", "72h duration",
                          "135mm initial soil", "surface rain mode", "rating", "zero lake evaporation"],
            "planned_cases": ["eastward", "westward", "same-partition no_rain baseline"],
            "warning": "HRU change also changes nonlinear soil aggregation; compare combined discretization response, not meteorology alone; no claim hydrological precision improves until rerun"}
        result["frozen_after"] = assert_unchanged(frozen)
        if before != {path.name: file_sha256(path) for path in SOURCE.iterdir() if path.is_file()}:
            raise RuntimeError("071520 changed during static experiment")
        result["frozen_weather_unchanged"] = True
        result["exporter_sha256"] = file_sha256(Path(__file__))
        write_json(destination / "report.json", result)
        return result
    except BaseException as error:
        write_json(destination / "failure.json", {"exception": type(error).__name__, "message": str(error),
                                                "traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    destination = arguments.output or ROOT / "verification/mountain-storm-hru-scale" / (
        "run-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    result = verify(destination)
    print(json.dumps({"directory": str(destination), "scales": {
        scale: {"HRUs": item["HRUs"], "merges": len(item["pure_lake_merges"]),
                "eastward": item["cases"]["eastward"]} for scale, item in result["scales"].items()}}, indent=2))
