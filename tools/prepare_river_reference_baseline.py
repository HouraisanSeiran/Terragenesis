"""Freeze existing primary measurements and bounded DEM/vector references."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_source import load_dem_candidate
from tools.audit_usgs_channel_reference import reduce_measurements

USGS = ROOT / "verification/usgs-channel-reference/run-20261002T170619349430Z"
DEM = ROOT / "verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz"
VECTORS = ROOT / "verification/hydrovector-evidence/run-20260930T060422593821Z/selected_vectors.json"
TD_DIRECTORY = ROOT / "verification/height-budget-v5/run-20260929T103819083596Z/screen-3"
PROBABILITIES = [.05, .25, .5, .75, .95]
DEM_WINDOW = [0, 96, 0, 96]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pin(path):
    return {"path": str(Path(path).resolve()), "sha256": sha256(path), "bytes": Path(path).stat().st_size}


def measurement_reference(report_path):
    report_path = Path(report_path)
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    sources = []
    for source in saved["sources"]:
        path = report_path.parent / Path(source["path"]).name
        if sha256(path) != source["sha256"]:
            raise ValueError("USGS primary source hash mismatch")
        sources.append({**source, "path": str(path.resolve())})
    raw = json.loads((report_path.parent / "measurements.json").read_text(encoding="utf-8"))
    reduced = reduce_measurements(raw, saved["station"])
    if reduced["retained_measurements"] != saved["retained_measurements"]:
        raise ValueError("USGS report differs from primary measurement replay")
    groups = {}
    for row in reduced["retained_measurements"]:
        name = row["channel_name"]
        group = groups.setdefault(name, {"records": [], "metric_samples": {
            "width_m": [], "mean_depth_m": [], "width_depth_ratio": [], "discharge_m3_s": []}})
        measured = row["measured_si"]
        width = measured["channel_width"]
        depth = measured["channel_area"] / width
        if not all(math.isfinite(value) and value > 0 for value in [width, depth, measured["channel_flow"]]):
            raise ValueError("positive finite physical channel observations required")
        group["records"].append(row)
        for metric, value in [("width_m", width), ("mean_depth_m", depth),
                              ("width_depth_ratio", width / depth), ("discharge_m3_s", measured["channel_flow"])]:
            group["metric_samples"][metric].append(value)
    for group in groups.values():
        group["count"] = len(group["records"])
        group["metrics"] = {}
        for metric, values in group["metric_samples"].items():
            quantiles = np.quantile(values, PROBABILITIES).tolist()
            group["metrics"][metric] = {"quantiles": quantiles,
                "review_interval": [quantiles[0], quantiles[-1]], "absolute_tolerance": 1e-9}
        group["conditions"] = {"station": saved["station"],
            "coordinate_lon_lat": group["records"][0]["coordinate_lon_lat"],
            "observed_discharge_range_m3_s": [min(group["metric_samples"]["discharge_m3_s"]),
                                               max(group["metric_samples"]["discharge_m3_s"])],
            "time_range": [min(row["time"] for row in group["records"]),
                           max(row["time"] for row in group["records"])],
            "climate": "unknown_not_classified", "terrain": "unknown_not_classified",
            "bankfull": "not_identified", "independence": "repeated_station_measurements"}
    return {"sources": sources, "report": pin(report_path), "station": saved["station"],
            "groups": groups, "omitted_measurements": reduced["omitted_measurements"],
            "semantics": reduced["mean_depth_semantics"], "limitations": reduced["limitations"],
            "scope": "single_station_channel_groups_not_global_population"}


def vector_reference(path):
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    audit_path = Path(path).with_name("report.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    reaches = []
    for river in source["rivers"]:
        parts = []
        for points in river["parts_lon_lat"]:
            longitude, latitude = np.asarray(points).T
            east, north = transform("EPSG:4326", "EPSG:32651", longitude, latitude)
            parts.append(np.column_stack([east, -np.asarray(north)]).tolist())
        reaches.append({"id": river["attributes"]["HYRIV_ID"],
                        "attributes": river["attributes"], "parts_lon_lat": river["parts_lon_lat"],
                        "parts_xz_m": parts, "selection": river["selection"]})
    return {"source": pin(path), "upstream_archive_sha256": source["source_archive_sha256"],
            "product_homepage_url": "https://www.hydrosheds.org/products/hydrorivers",
            "archive_download_url": None, "retrieval_status": "existing_local_archive_no_original_download_url_recorded",
            "upstream_provenance_report": pin(audit_path), "upstream_files": audit["sources"],
            "coordinate_order": source["coordinate_order"], "crs": source["crs"],
            "metric_crs": "EPSG:32651", "metric_axes": "X=easting; Z=-northing",
            "policy": source["policy"], "reaches": reaches,
            "curvature_status": "original_reference_polylines_available_not_surveyed_channel_bends"}


def prepare(output, *, usgs=USGS / "report.json", dem=DEM, vectors=VECTORS):
    # Freeze real reference policy before reading any TD metric results.
    measurements = measurement_reference(usgs)
    candidate = load_dem_candidate(dem, verify_source=True)
    grid = candidate["manifest"]["identity"]["grid"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(dem, output / "dem-reference.npz")
    shutil.copyfile(vectors, output / "selected-vectors.json")
    reference = {"schema": "river-reference-observations-v1", "status": "bounded_reference_not_certification",
        "quantile_probs": PROBABILITIES, "numeric_tolerances": {"absolute": 1e-9},
        "reference_metrics_schema": "metric-naturalness-frozen-reference-v1",
        "policy": {"channel_area_threshold_m2": 100000., "dem_window_zx": DEM_WINDOW,
                   "resampling": "saved_target_grid_no_additional_resampling", "quantile_method": "linear",
                   "interval_role": "q05_q95_review_only_not_universal_naturalness_pass",
                   "condition_mismatch": "report_incomparable_without_silent_transfer",
                   "required_comparison_conditions": ["spacing_m", "climate", "terrain", "discharge", "channel_group"]},
        "usgs": measurements,
        "dem": {"source": pin(dem), "saved_copy": {"path": "dem-reference.npz", "sha256": sha256(output / "dem-reference.npz")},
                "identity_sha256": candidate["manifest"]["identity_sha256"], "grid": grid,
                "height_key": "height_m", "valid_key": "valid_mask", "unknown_key": "unknown_mask",
                "conditions": {"spacing_m": grid["spacing_x_m"], "window_zx": DEM_WINDOW,
                               "climate": "unknown_not_classified", "terrain": "observed_SRTM_window_not_classified"},
                "recipe": candidate["manifest"]["identity"]["recipe"],
                "upstream_source": candidate["manifest"]["identity"]["source"],
                "blockers": candidate["manifest"]["summary"]["blockers"],
                "verification": "source_raster_sha256_header_window_projection_replayed",
                "product_homepage_url": "https://srtm.csi.cgiar.org/",
                "archive_download_url": None},
        "hydrorivers": vector_reference(vectors), "publishable": False}
    (output / "reference.json").write_text(json.dumps(reference, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    inventory = []
    td_report_path = TD_DIRECTORY / "report.json"
    td_report = json.loads(td_report_path.read_text(encoding="utf-8"))
    for filename in ["seed20260930-x0-z0.npz", "seed20260931-x0-z0.npz", "seed20260931-x11520-z15360.npz"]:
        path = TD_DIRECTORY / filename
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"]))
            entry = next(item for item in td_report["samples"] if str(item["seed"]) == metadata["seed"]
                         and item["native_origin"] == metadata["native_origin"])
            if entry["raw_sha256"] != sha256(path):
                raise ValueError("TD source report hash mismatch")
            inventory.append({**pin(path), "metadata": metadata,
                              "generation_config": json.loads(str(archive["generation_config"])),
                              "upstream_generation_report": pin(td_report_path),
                              "backend_code": pin(ROOT / "diffusion/backend.py"),
                              "saving_code": pin(ROOT / "tools/benchmark_height_budget_v5.py"),
                              "height_semantics": "WorldPipeline output elev before process_region or +126m game datum shift",
                              "vertical_datum": "model_output_not_independently_geodetic_certified",
                              "shape_zx": list(archive["elevation"].shape), "elevation_key": "elevation",
                              "climate_key": "climate", "kind": "generated_TD_not_measured_DEM"})
    (output / "td-source-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    return reference


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = prepare(arguments.output)
    print(json.dumps({"status": result["status"], "station": result["usgs"]["station"],
                      "groups": {name: group["count"] for name, group in result["usgs"]["groups"].items()}}))
