"""Acquire fixed same-product SRTM sources and replay climate-matched real windows."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

import numpy as np
import rasterio
from rasterio.merge import merge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.td_source import load_dem_candidate, prepare_dem_candidate, save_dem_candidate
from tools.audit_river_reference_conditions import climate_sources, pin, spatial_blocks


def source_tile(coordinate):
    longitude, latitude = coordinate
    col = math.floor((longitude + 180) / 5) + 1
    row = math.floor((60 - latitude) / 5) + 1
    return f"srtm_{col:02d}_{row:02d}"


def acquire(tile, directory):
    directory.mkdir(parents=True, exist_ok=True)
    url = f"https://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/TIFF/{tile}.zip"
    archive_path = directory / f"{tile}.zip"
    source_path = directory / f"{tile}.tif"
    retrieved = datetime.now(timezone.utc).isoformat()
    if not archive_path.exists():
        partial = archive_path.with_suffix(".zip.part")
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as response:
            size = int(response.headers["Content-Length"])
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > size:
            raise ValueError("partial source archive exceeds declared remote size")
        ranges = [(start, min(start + 256 * 1024, size) - 1) for start in range(offset, size, 256 * 1024)]
        def fetch_range(bounds):
            start, end = bounds
            request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(request, timeout=60) as response:
                expected = f"bytes {start}-{end}/{size}"
                if response.status != 206 or response.headers.get("Content-Range") != expected:
                    raise ValueError("source range response differs from requested bytes")
                raw = response.read()
                if len(raw) != end - start + 1:
                    raise ValueError("incomplete source range response")
                return raw, response.url, response.status, end
        with partial.open("ab") as target, ThreadPoolExecutor(max_workers=4) as pool:
            for raw, response_url, status, end in pool.map(fetch_range, ranges):
                target.write(raw)
                target.flush()
                offset = end + 1
                if offset % (4 * 1024 * 1024) == 0 or offset == size:
                    print(json.dumps({"tile": tile, "downloaded_bytes": offset, "total_bytes": size}), flush=True)
        partial.replace(archive_path)
    else:
        response_url, status = url, "reused_immutable_local_download"
        retrieved = None
    with zipfile.ZipFile(archive_path) as archive:
        selected = [name for name in archive.namelist() if Path(name).name.casefold() == f"{tile}.tif"]
        if len(selected) != 1:
            raise ValueError("exact SRTM tile TIFF archive member required")
        if not source_path.exists():
            with archive.open(selected[0]) as source, source_path.open("wb") as target:
                shutil.copyfileobj(source, target)
        readme = [name for name in archive.namelist() if Path(name).name.casefold() == "readme.txt"]
        if readme:
            (directory / f"{tile}-readme.txt").write_bytes(archive.read(readme[0]))
    return {"tile": tile, "archive": pin(archive_path), "raster": pin(source_path),
        "requested_url": url, "response_url": response_url, "retrieved_utc": retrieved,
        "http_status": status, "product": "CIAT_CSI_hole_filled_SRTM_v4.1",
        "license": "source_readme_local_research_only_not_cleared_for_redistribution"}


def prepare(plan_path, output, source_directory, resume=False):
    plan_path, output, source_directory = Path(plan_path), Path(output), Path(source_directory)
    source_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    locations = [location for target in source_plan["target_conditions"] for location in target["preselected_locations"]]
    output.mkdir(parents=True, exist_ok=resume)
    plan = {"schema": "river-climate-matched-source-plan-v1", "global_climate_inventory": pin(plan_path),
        "source_product": "CIAT_CSI_hole_filled_SRTM_v4.1", "separate_product_calibration": True,
        "locations": locations, "target_crs": "EPSG:32615", "spacing_m": 90, "block_size": 48,
        "roles": "entire_location_role_preserved_no_cross_role_within_window",
        "source_tile_requests": sorted({source_tile(location["center_lon_lat"]) for location in locations}),
        "new_TD_naturalness_accessed": False, "halo_m": 900,
        "selection": "frozen_global_real_climate_inventory_before_DEM_or_new_TD_naturalness"}
    frozen_plan = output / "plan.json"
    if frozen_plan.exists():
        if not resume or json.loads(frozen_plan.read_text(encoding="utf-8")) != plan:
            raise ValueError("existing source plan differs")
    else:
        frozen_plan.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    sources = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for source in pool.map(lambda tile: acquire(tile, source_directory), plan["source_tile_requests"]):
            sources[source["tile"]] = source
            print(json.dumps({"downloaded_tile": source["tile"], "archive_bytes": source["archive"]["bytes"]}), flush=True)
    old = load_dem_candidate(ROOT / "verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz", verify_source=True)
    declaration = old["manifest"]["identity"]["recipe"]["source_declaration"]
    climate_design_path = ROOT / "verification/td-natural-river-stages/reference-geographic-20261011-04/climate-design.json"
    climate_design = json.loads(climate_design_path.read_text(encoding="utf-8"))
    datasets = []
    for index, location in enumerate(locations):
        source = sources[source_tile(location["center_lon_lat"])]["raster"]["path"]
        path = output / f"real-missouri-{index:02d}.npz"
        crop_provenance = None
        if not path.exists():
            try:
                candidate = prepare_dem_candidate(source, location["bbox_lon_lat"], target_crs="EPSG:32615",
                    spacing_m=90, halo_m=900, sea_level_m=0, sea_datum="Unverified numeric zero not tidal sea level",
                    source_declaration=declaration, vertical_datum="Unknown: not independently certified")
            except ValueError as error:
                if str(error) != "bbox/halo not covered by source extent":
                    raise
                west, south, east, north = location["bbox_lon_lat"]
                bounds = [west - .02, south - .02, east + .02, north + .02]
                rasters = [rasterio.open(item["raster"]["path"]) for item in sources.values()]
                try:
                    crop, affine = merge(rasters, bounds=bounds, nodata=-32768, method="first")
                    crop_path = output / f"source-boundary-crop-{index:02d}.tif"
                    with rasterio.open(crop_path, "w", driver="GTiff", height=crop.shape[1], width=crop.shape[2],
                        count=1, dtype=crop.dtype, crs="EPSG:4326", transform=affine, nodata=-32768) as target:
                        target.write(crop)
                    crop_provenance = {"crop": pin(crop_path), "bounds": bounds,
                        "upstream_rasters": [item["raster"] for item in sources.values()],
                        "policy": "bounded_same_product_native_affine_merge_first_no_interpolation"}
                finally:
                    for raster in rasters:
                        raster.close()
                candidate = prepare_dem_candidate(crop_path, location["bbox_lon_lat"], target_crs="EPSG:32615",
                    spacing_m=90, halo_m=900, sea_level_m=0, sea_datum="Unverified numeric zero not tidal sea level",
                    source_declaration=declaration, vertical_datum="Unknown: not independently certified")
            save_dem_candidate(candidate, path)
        cold = load_dem_candidate(path, verify_source=True)
        arrays, manifest = cold["arrays"], cold["manifest"]
        grid = manifest["identity"]["grid"]
        blocks = spatial_blocks(arrays["height_m"], arrays["valid_mask"], arrays["unknown_mask"])
        for block in blocks:
            block["local_id"] = block["id"]
            block["id"] = f'missouri-{index:02d}/{block["id"]}'
            block["role"] = location["role"]
            z0, z1, x0, x1 = block["window_zx"]
            block["core_complete"] = bool(arrays["core_mask"][z0:z1, x0:x1].all())
            block["eligible_for_evaluation"] = block["core_complete"] and block["eligible_complete_coverage"]
        climate = climate_sources(grid, blocks, "EPSG:32615")
        for block in blocks:
            values = [climate[str(i)]["raw_sample_by_block"][block["id"]] for i in (1, 4, 12, 15)]
            block["climate_BIO1_4_12_15"] = values
            block["climate_bin"] = ([int(np.searchsorted(climate_design["bin_edges"][channel], value, side="right"))
                for channel, value in zip(climate_design["channel_order"], values)]
                if all(value is not None for value in values) else None)
        datasets.append({"id": f"missouri-{index:02d}", "dem": {**pin(path), "grid": grid,
            "identity_sha256": manifest["identity_sha256"], "source_product": plan["source_product"]},
            "location": location, "blocks": blocks, "climate_sources": climate, "crop_provenance": crop_provenance})
        print(json.dumps({"location": index, "role": location["role"], "eligible": sum(
            block["eligible_for_evaluation"] for block in blocks)}), flush=True)
    report = {"schema": "river-reference-geographic-inventory-v1", "status": "frozen_climate_matched_real_sources",
        "design": pin(output / "plan.json"), "climate_design": {**pin(climate_design_path), **climate_design},
        "datasets": datasets, "source_product": plan["source_product"], "sources": sources,
        "independence": "separated_locations_roles_no_target_overlap_same_SRTM_product_spatial_dependence_retained",
        "eligible_counts": dict(Counter(f'{b["terrain_class"]}:{b["role"]}:{b["climate_bin"]}'
            for dataset in datasets for b in dataset["blocks"] if b["eligible_for_evaluation"])),
        "natural_credible": False, "publishable": False}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    report = prepare(args.plan, args.output, args.source_directory, resume=args.resume)
    print(json.dumps({"status": report["status"], "eligible_counts": report["eligible_counts"]}))
