"""Freeze source conditions and spatial roles without reading TD naturalness scores."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.request

import numpy as np
import rasterio
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.td_source import file_sha256, load_dem_candidate, prepare_dem_candidate, save_dem_candidate

DEM = ROOT / "verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz"
TD = ROOT / "verification/height-budget-v5/run-20260929T103819083596Z"
GEOGRAPHIC_WINDOWS = [[west, south, west + .4, south + .4]
                      for south in (26.2, 27.2, 28.2, 29.4) for west in (120.2, 121.0)] + [
                      [120 + index * .4, 29.55, 120 + (index + 1) * .4, 29.95] for index in range(8)]


def pin(path):
    path = Path(path)
    return {"path": str(path.resolve()), "sha256": file_sha256(path), "bytes": path.stat().st_size}


def relief_class(relief):
    return "low_relief" if relief < 50 else "moderate_relief" if relief < 250 else "high_relief"


def spatial_blocks(height, valid, unknown, spacing=90., size=48):
    height, valid, unknown = map(np.asarray, (height, valid, unknown))
    if (height.ndim != 2 or height.shape != valid.shape or height.shape != unknown.shape
            or not np.isfinite(height[valid]).all() or np.any(valid & unknown)):
        raise ValueError("consistent finite valid DEM and disjoint unknown mask required")
    result = []
    for row in range(height.shape[0] // size):
        for col in range(height.shape[1] // size):
            z, x = row * size, col * size
            window = (slice(z, z + size), slice(x, x + size))
            values = height[window][valid[window]]
            complete = bool(valid[window].all() and not unknown[window].any())
            relief = float(np.ptp(values)) if values.size else None
            result.append({"id": f"z{z}-x{x}", "window_zx": [z, z + size, x, x + size],
                "role": ("fit", "calibration", "real_holdout")[(row + col) % 3],
                "shape_zx": [size, size], "spacing_m": spacing,
                "nominal_extent_m": [size * spacing, size * spacing],
                "valid_cells": int(valid[window].sum()), "unknown_cells": int(unknown[window].sum()),
                "eligible_complete_coverage": complete,
                "height_range_m": [float(values.min()), float(values.max())] if values.size else None,
                "relief_m": relief, "terrain_class": relief_class(relief) if relief is not None else "unknown",
                "climate_match_status": "not_assessed",
                "independence": "disjoint_window_same_tile_spatial_dependence_not_independent_basin"})
    return result


def climate_sources(grid, blocks, target_crs="EPSG:32651"):
    result = {}
    east = [grid["origin_x_m"] + (b["window_zx"][2] + 23.5) * 90 for b in blocks]
    north = [-grid["origin_z_m"] - (b["window_zx"][0] + 23.5) * 90 for b in blocks]
    lon, lat = transform(target_crs, "EPSG:4326", east, north)
    for index in (1, 4, 12, 15):
        path = ROOT / f"data/global/wc2.1_10m_bio_{index}.tif"
        if not path.exists():
            result[str(index)] = {"status": "missing"}
            continue
        with rasterio.open(path) as source:
            samples = list(source.sample(zip(lon, lat), masked=True))
            result[str(index)] = {**pin(path), "crs": str(source.crs),
                "resolution_source_units": list(source.res), "shape_zx": [source.height, source.width],
                "nodata": source.nodata, "scale": source.scales[0], "offset": source.offsets[0],
                "band_unit": source.units[0], "tags": source.tags(),
                "product_homepage": "https://www.worldclim.org/data/worldclim21.html",
                "download_identity": "existing_local_file_original_download_url_not_recorded",
                "scope": "coarse_geographic_context_not_local_measured_forcing_or_climate_class",
                "raw_sample_by_block": {b["id"]: None if np.ma.is_masked(v[0]) else float(v[0])
                                        for b, v in zip(blocks, samples)}}
    return result


def td_inventory():
    result = []
    for report_path in sorted(TD.glob("*/report.json")):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for entry in report.get("samples", []):
            path = report_path.parent / entry["raw_npz"]
            if file_sha256(path) != entry["raw_sha256"]:
                raise ValueError("TD generation source hash mismatch")
            with np.load(path, allow_pickle=False) as archive:
                metadata = json.loads(str(archive["metadata"].item()))
                config = json.loads(str(archive["generation_config"].item()))
                climate = archive["climate"]
                result.append({**pin(path), "generation_report": pin(report_path),
                    "metadata": metadata, "generation_config": config,
                    "shape_zx": list(archive["elevation"].shape),
                    "climate_shape": list(climate.shape),
                    "climate_channel_range_raw": [[float(a.min()), float(a.max())] for a in climate],
                    "climate_contract": "synthetic_geographic_v5_BIO1_BIO4_BIO12_BIO15_not_measured_location",
                    "naturalness_previously_used": path.name in {
                        "seed20260930-x0-z0.npz", "seed20260931-x0-z0.npz",
                        "seed20260931-x11520-z15360.npz", "seed20261004-x0-z0.npz"},
                    "holdout_scope": "region_can_be_unused_but_seed20261004_already_evaluated"})
    return result


def audit(output, dem=DEM):
    candidate = load_dem_candidate(dem, verify_source=True)
    arrays, identity = candidate["arrays"], candidate["manifest"]["identity"]
    height, valid, unknown = (arrays[key] for key in ("height_m", "valid_mask", "unknown_mask"))
    blocks = spatial_blocks(height, valid, unknown)
    nw = height[:96, :96][valid[:96, :96]]
    report = {"schema": "river-reference-source-conditions-v1", "status": "frozen_source_inventory",
        "dem": {**pin(dem), "identity_sha256": candidate["manifest"]["identity_sha256"],
            "grid": identity["grid"], "source": identity["source"], "recipe": identity["recipe"],
            "source_replay": "verify_source_true_hash_header_masks_projection_windows",
            "height_quantiles_m": np.quantile(height[valid], [0, .05, .5, .95, 1]).tolist(),
            "valid_cells": int(valid.sum()), "unknown_cells": int(unknown.sum()),
            "numeric_zero_valid_cells": int((height[valid] == 0).sum()),
            "zero_semantics": "numeric_source_elevation_not_verified_ocean",
            "northwest_96": {"valid_cells": int(valid[:96, :96].sum()),
                "unknown_cells": int(unknown[:96, :96].sum()),
                "height_quantiles_m": np.quantile(nw, [0, .05, .5, .95, 1]).tolist(),
                "relief_m": float(np.ptp(nw)), "terrain": "observed_high_relief_not_flat_coast"}},
        "preregistered_design": {"size": 48, "spacing_m": 90, "extent_m": 4320,
            "roles": "(block_row+block_col)%3: fit/calibration/real_holdout",
            "relief_bins_m": [50, 250], "relief_statistic": "valid_max_minus_min",
            "missing_policy": "incomplete_coverage_excluded_before_metric_evaluation",
            "channel_support": "same_100000m2_threshold_real_and_TD_runner_counts_support",
            "selection_policy": "all_complete_disjoint_blocks_no_TD_score_access_or_reselection",
            "climate_policy": "context_raw_values_only_climate_match_requires_explicit_unit_and_condition_contract",
            "independence": "no_exchangeability_or_independent_catchment_claim"},
        "blocks": blocks, "eligible_counts": dict(Counter(
            f'{b["terrain_class"]}:{b["role"]}' for b in blocks if b["eligible_complete_coverage"])),
        "climate_sources": climate_sources(identity["grid"], blocks), "td_sources": td_inventory(),
        "coverage_contract": {"one_dimensional_refinement": "metric_resolution_exchange.py serial reach refinement only",
            "two_dimensional_amr": "required_for_full_dynamic_2D_claim_not_implemented_in_stage_contract",
            "sea_outlets": "one_way_engineered_boundary_not_certified_natural_mouth",
            "stage4_exit": "empirical_validation_and_coverage_required_not_automatically_passed_by_inventory",
            "natural_credible": False, "publishable": False}}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return report


def expand(output, dem=DEM, resume=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=resume)
    original = load_dem_candidate(dem, verify_source=True)
    recipe = original["manifest"]["identity"]["recipe"]
    source = original["manifest"]["identity"]["source"]["path"]
    design = {"schema": "river-reference-geographic-design-v1",
        "windows_epsg4326": GEOGRAPHIC_WINDOWS, "selection": "fixed_geographic_lattice_before_metrics",
        "block_size": 48, "relief_bins_m": [50, 250],
        "roles": "(block_row+block_col)%3: fit/calibration/real_holdout",
        "climate_match": "same_dimension_BIO_statistical_conditioning_allowed_not_measured_forcing",
        "climate_channel_order": ["BIO1", "BIO4", "BIO12", "BIO15"],
        "climate_bin_edges": {"BIO1": [0, 10, 20, 30], "BIO4": [500, 1000, 1500, 2000],
                              "BIO12": [500, 1000, 2000, 3000], "BIO15": [30, 60, 90]},
        "climate_bin_rule": "searchsorted(edges,value,side=right); all_four_dimension_bins_required",
        "design_history": "initial_eight_windows_have_only_four_low_relief_blocks; entire_northern_transect_added_before_TD_metrics",
        "same_source_tile": True, "independent_catchments": False}
    design_path = output / "design.json"
    if design_path.exists():
        saved_design = json.loads(design_path.read_text(encoding="utf-8"))
        if not resume or saved_design["windows_epsg4326"] != GEOGRAPHIC_WINDOWS:
            raise ValueError("existing geographic design differs")
    else:
        design_path.write_text(json.dumps(design, indent=2), encoding="utf-8")
    datasets = []
    for index, bbox in enumerate(GEOGRAPHIC_WINDOWS):
        path = output / f"dem-geographic-{index:02d}.npz"
        try:
            candidate = load_dem_candidate(path, verify_source=True) if resume and path.exists() else prepare_dem_candidate(source, bbox, target_crs="EPSG:32651", spacing_m=90.,
                halo_m=900., sea_level_m=0., sea_datum=recipe["sea_datum"],
                source_declaration=recipe["source_declaration"], vertical_datum=recipe["vertical_datum"],
                vertical_datum_status=recipe["vertical_datum_status"])
        except ValueError as error:
            if not (str(error).startswith("no coverage:") or str(error) == "bbox/halo not covered by source extent"):
                raise
            datasets.append({"id": f"geographic-{index:02d}", "bbox_epsg4326": bbox,
                             "status": "unsupported_no_source_coverage", "reason": str(error), "blocks": []})
            print(json.dumps({"dataset": index, "status": "unsupported_no_source_coverage"}), flush=True)
            continue
        if not path.exists():
            save_dem_candidate(candidate, path)
        cold = load_dem_candidate(path, verify_source=True)
        arrays = cold["arrays"]
        grid = cold["manifest"]["identity"]["grid"]
        blocks = spatial_blocks(arrays["height_m"], arrays["valid_mask"], arrays["unknown_mask"])
        for block in blocks:
            block["dataset_id"] = f"geographic-{index:02d}"
            block["local_id"] = block["id"]
            block["id"] = f'geographic-{index:02d}/{block["id"]}'
        climate = climate_sources(grid, blocks)
        edges = design["climate_bin_edges"]
        for block in blocks:
            values = [climate[str(i)]["raw_sample_by_block"][block["id"]] for i in (1, 4, 12, 15)]
            block["climate_BIO1_4_12_15"] = values
            block["climate_sampling"] = "nearest_WorldClim_10arcmin_pixel_at_DEM_block_center_1970_2000"
            block["climate_bin"] = ([int(np.searchsorted(edges[name], value, side="right"))
                for name, value in zip(design["climate_channel_order"], values)]
                if all(value is not None for value in values) else None)
        datasets.append({"id": f"geographic-{index:02d}", "bbox_epsg4326": bbox,
            "dem": {**pin(path), "grid": grid, "identity_sha256": cold["manifest"]["identity_sha256"]},
            "blocks": blocks, "climate_sources": climate})
        print(json.dumps({"dataset": index, "eligible": dict(Counter(
            b["terrain_class"] for b in blocks if b["eligible_complete_coverage"]))}), flush=True)
    official = []
    for name, url in [("worldclim21", "https://www.worldclim.org/data/worldclim21.html"),
                      ("bioclim", "https://www.worldclim.org/data/bioclim.html")]:
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read()
            path = output / f"official-{name}.html"
            path.write_bytes(raw)
            official.append({**pin(path), "requested_url": url, "response_url": response.url,
                "retrieved_utc": datetime.now(timezone.utc).isoformat(), "http_status": response.status})
    report = {"schema": "river-reference-geographic-inventory-v1", "status": "frozen_sources_not_natural_certification",
        "design": pin(design_path), "datasets": datasets, "official_climate_documents": official,
        "source": original["manifest"]["identity"]["source"],
        "unit_contract": {"BIO1": "degrees_C", "BIO4": "temperature_standard_deviation_degrees_C_times_100",
                          "BIO12": "annual_precipitation_mm", "BIO15": "precipitation_coefficient_of_variation_percent"},
        "td_climate_contract_sources": [pin(ROOT / "diffusion/backend.py"), pin(ROOT / "diffusion/geography_v5.py"),
            pin(ROOT / "vendor/terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230/terrain_diffusion/inference/world_pipeline.py"),
            pin(ROOT / "vendor/terrain-diffusion-e8dcb4b1a834ab2f6b1a6f5256ed7c9f2f3e8230/terrain_diffusion/inference/minecraft_api.py")],
        "independence": "disjoint_geographic_windows_same_SRTM_tile_not_independent_surveyed_catchments",
        "natural_credible": False, "publishable": False}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def condition_existing(report_path, output):
    report_path, output = Path(report_path), Path(output)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    design = {"channel_order": ["BIO1", "BIO4", "BIO12", "BIO15"],
        "units": report["unit_contract"],
        "bin_edges": {"BIO1": [0, 10, 20, 30], "BIO4": [500, 1000, 1500, 2000],
                      "BIO12": [500, 1000, 2000, 3000], "BIO15": [30, 60, 90]},
        "rule": "searchsorted(edges,value,side=right); all_four_dimension_bins_required",
        "TD_reduction": "median_saved_output_climate_each_channel_on_same_native_physical_window",
        "semantics": "numeric_condition_matching_not_measured_climate_or_forcing_validation",
        "selection": "fixed_physical_unit_bins_before_new_TD_naturalness_metrics"}
    for dataset in report["datasets"]:
        if "dem" not in dataset:
            continue
        dem = dataset["dem"]
        if file_sha256(dem["path"]) != dem["sha256"]:
            raise ValueError("geographic source hash changed before conditioning freeze")
        candidate = load_dem_candidate(dem["path"], verify_source=True)
        for block in dataset["blocks"]:
            z0, z1, x0, x1 = block["window_zx"]
            in_core = bool(candidate["arrays"]["core_mask"][z0:z1, x0:x1].all())
            northern_replaced = dataset["id"] in ("geographic-06", "geographic-07")
            block["eligible_for_evaluation"] = bool(block["eligible_complete_coverage"] and in_core and not northern_replaced)
            block["core_complete"] = in_core
            block["exclusion_reason"] = ("northern_windows_replaced_by_disjoint_transect" if northern_replaced else
                "block_intersects_halo" if not in_core else "incomplete_known_coverage" if not block["eligible_complete_coverage"] else None)
            values = [dataset["climate_sources"][str(i)]["raw_sample_by_block"][block["id"]]
                      for i in (1, 4, 12, 15)]
            block["climate_BIO1_4_12_15"] = values
            block["climate_sampling"] = "nearest_WorldClim_10arcmin_pixel_at_DEM_block_center_1970_2000"
            block["climate_bin"] = ([int(np.searchsorted(design["bin_edges"][name], value, side="right"))
                for name, value in zip(design["channel_order"], values)]
                if all(value is not None for value in values) else None)
    output.mkdir(parents=True, exist_ok=False)
    design_path = output / "climate-design.json"
    design_path.write_text(json.dumps(design, indent=2), encoding="utf-8")
    report["upstream_geographic_inventory"] = pin(report_path)
    report["climate_design"] = {**pin(design_path), **design}
    report["spatial_exclusion_policy"] = "only_all_core_48x48_blocks; geographic06/07_replaced_by_northern_transect; no_halo_or_overlapping_target_blocks; original_source_pixel_independence_not_asserted"
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def check_inventory(report_path):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    boxes, counts = [], Counter()
    for dataset in report["datasets"]:
        for block in dataset["blocks"]:
            if not block.get("eligible_for_evaluation", False):
                continue
            grid = dataset["dem"]["grid"]
            z0, z1, x0, x1 = block["window_zx"]
            box = (grid["origin_x_m"] + x0 * 90 - 45, grid["origin_x_m"] + x1 * 90 - 45,
                   grid["origin_z_m"] + z0 * 90 - 45, grid["origin_z_m"] + z1 * 90 - 45)
            for other_id, other in boxes:
                if min(box[1], other[1]) > max(box[0], other[0]) and min(box[3], other[3]) > max(box[2], other[2]):
                    raise ValueError(f'eligible blocks overlap: {block["id"]} and {other_id}')
            boxes.append((block["id"], box))
            counts[f'{block["terrain_class"]}:{block["role"]}'] += 1
    return {"status": "nonoverlapping_eligible_source_windows", "report": pin(report_path),
            "eligible_blocks": len(boxes), "counts": dict(counts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expand-geographic", action="store_true")
    parser.add_argument("--condition-existing", type=Path)
    parser.add_argument("--resume-geographic", action="store_true")
    parser.add_argument("--check-inventory", type=Path)
    args = parser.parse_args()
    if args.check_inventory:
        print(json.dumps(check_inventory(args.check_inventory)))
        raise SystemExit(0)
    if args.output is None:
        parser.error("--output required for source preparation")
    report = (condition_existing(args.condition_existing, args.output) if args.condition_existing else
              expand(args.output, resume=args.resume_geographic) if args.expand_geographic else audit(args.output))
    print(json.dumps({"status": report["status"]}))
