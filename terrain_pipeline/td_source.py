"""TD 源的生成、拼接、区域存储与产品查询（A 类）。

合并自 `dem_domain`、`geography_preparation_inventory`、`hydrology_detail_td`、
`new_world_source_mosaic`、`new_world_terrain`、`world_acceptance_terrain`、
`world_terrain_composition`、`world_terrain_disk_store`、`world_terrain_mosaic`、
`world_terrain_store`、`surface_rivers/metric_fine_terrain`。同组重名的 `prepare` /
`read_product` / `plan` / `open_registry` / `ALGORITHM` / `SCHEMA` / `MAX_CELLS` 等按
产品线起命名变体；块内代码原样保留。
"""

from __future__ import annotations

from terrain_pipeline.common_infra import published_algorithm_matches, published_algorithm_hashes

# ========================================================================
# 外部依赖（合并前各旧文件的 import，去重后集中在此）
# ========================================================================
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine, rowcol
from rasterio.warp import transform, transform_bounds
from rasterio.windows import Window, from_bounds
from terrain_pipeline.artifacts.contracts import array_hash, canonical_json, digest
from terrain_pipeline.surface_rivers import accumulate, route
import csv
from dataclasses import dataclass
import io
import stat
from terrain_pipeline.common_infra import checked_archive, file_sha256, make_source
from scipy.ndimage import label
import shutil
from terrain_pipeline import tectonic as plate_td_product
from terrain_pipeline.tectonic import load_product
from diffusion.plate_td_conditioning import PLATE_IDENTITY, WORLD_SEED
from diffusion.physical_config import PhysicalGenerationConfig
from terrain_pipeline.coastal_terrain import classify
import sys
import time
from scipy.ndimage import gaussian_filter
from diffusion.geographic_noise import field
from scipy.ndimage import distance_transform_edt, gaussian_filter, label
from terrain_pipeline.world_water_layout import LayoutSpec, layout_field
import uuid
from terrain_pipeline.common_infra import identity
from terrain_pipeline.world_river_network_io import verify_network
from terrain_pipeline.surface_rivers.native_30m_source import (
    BORDER_BAND_CELLS, _page_records, _read_page,
)
from terrain_pipeline.world_water_layout import LayoutSpec
from terrain_pipeline.world_river_network_io import verify_network, write_network
from diffusion.geography_physical import sample_physical
from terrain_pipeline.common_infra import identity, readonly



# ------------------------------------------------------------------------
# 原 terrain_pipeline/dem_domain.py
# ------------------------------------------------------------------------

DEM_FORMAT = "dem-domain-candidate-v2"


DEM_ALGORITHM = "bounded-exact-inverse-center-dem-sampling-v2"


STATUS = "candidate_not_publishable"


ARRAY_NAMES = {"height_m", "valid_mask", "unknown_mask", "footprint_mask", "core_mask"}


DEM_MAX_CELLS = 500000


MAX_SOURCE_CELLS = 599999


TRANSFORM_CHUNK_ROWS = 32


BLOCKERS = ["vertical_datum_not_independently_verified", "sea_datum_not_verified",
            "dem_low_surface_proxy_is_not_actual_ocean", "natural_mouth_not_verified",
            "river_and_two_tributaries_not_independently_verified",
            "complete_catchment_and_boundary_not_verified", "fine_bed_evidence_missing",
            "license_not_cleared_local_research_only"]


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _validate_elevation_units(scale, offset, unit, declaration):
    if scale != 1 or offset != 0:
        raise ValueError("height_m requires band_scale=1 and band_offset=0; encoded elevations unsupported")
    if unit is not None and not isinstance(unit, str):
        raise ValueError("invalid elevation band unit")
    normalized = "" if unit is None else unit.strip().casefold()
    if normalized in ("m", "meter", "meters", "metre", "metres", "米"):
        return
    if normalized not in ("", "unknown", "unspecified"):
        raise ValueError("height_m rejects explicitly non-metre band units")
    assumptions = ("elevation assumed metres", "elevation assumed meters",
                   "height assumed metres", "height assumed meters", "高程假定为米", "高程假设为米")
    if not any(phrase in declaration.casefold() for phrase in assumptions):
        raise ValueError("unknown band unit requires source_declaration: elevation assumed metres")


def _recipe(bbox, target_crs, spacing_m, halo_m, sea_level_m, sea_datum,
            source_declaration, vertical_datum, vertical_datum_status,
            max_cells, max_source_cells):
    if (len(bbox) != 4 or any(isinstance(value, bool) for value in bbox) or
            not np.isfinite(bbox).all()):
        raise ValueError("bbox requires four finite lon/lat bounds")
    west, south, east, north = map(float, bbox)
    target = CRS.from_user_input(target_crs)
    code = target.to_epsg()
    if code not in (32615, 32651):
        raise ValueError("target CRS must be explicit EPSG:32615 or EPSG:32651 (metres)")
    zone_west = (code - 32601) * 6 - 180
    if not (zone_west <= west < east <= zone_west + 6 and 0 <= south < north < 84):
        raise ValueError("bbox must be ordered and inside its explicit northern UTM zone")
    if (isinstance(spacing_m, bool) or spacing_m != 90 or
            isinstance(halo_m, bool) or not math.isfinite(halo_m) or halo_m < 90):
        raise ValueError("spacing must be 90m; finite halo must be at least 90m")
    if isinstance(sea_level_m, bool) or sea_level_m != 0:
        raise ValueError("sea_level_m must be explicitly 0, not a verified sea datum")
    if vertical_datum_status not in ("unknown", "source_declared"):
        raise ValueError("vertical datum cannot be marked independently verified")
    if any(not isinstance(value, str) or not value.strip() for value in
           (sea_datum, source_declaration, vertical_datum)):
        raise ValueError("source, vertical and sea datum declarations are required")
    for name, value, maximum in (("max_cells", max_cells, DEM_MAX_CELLS),
                                 ("max_source_cells", max_source_cells, MAX_SOURCE_CELLS)):
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError(f"{name} must be an integer in 1..{maximum}")
    return {"bbox_epsg4326": [west, south, east, north], "target_crs": target.to_string(),
            "spacing_m": 90., "halo_m": float(halo_m), "sea_level_m": 0.,
            "sea_datum": sea_datum, "source_declaration": source_declaration,
            "vertical_datum": vertical_datum, "vertical_datum_status": vertical_datum_status,
            "max_cells": max_cells, "max_source_cells": max_source_cells,
            "resampling": "nearest", "license_scope": "local_research_only_not_cleared",
            "sampling": "exact_inverse_target_pixel_center_source_affine_floor",
            "transform_chunk_rows": TRANSFORM_CHUNK_ROWS,
            "detail_limit": "Resampling does not turn 90m information into real fine river beds."}


def _layout(recipe):
    west, south, east, north = transform_bounds(
        "EPSG:4326", recipe["target_crs"], *recipe["bbox_epsg4326"], densify_pts=41)
    spacing = recipe["spacing_m"]
    halo = recipe["halo_m"]
    left = math.floor((west - halo) / spacing) * spacing
    top = math.ceil((north + halo) / spacing) * spacing
    right = math.ceil((east + halo) / spacing) * spacing
    bottom = math.floor((south - halo) / spacing) * spacing
    cols = int(round((right - left) / spacing))
    rows = int(round((top - bottom) / spacing))
    if rows * cols > recipe["max_cells"]:
        raise ValueError("target max_cells exceeded before allocation")
    return {"shape_zx": [rows, cols], "origin_x_m": left + spacing / 2,
            "origin_z_m": -(top - spacing / 2), "spacing_x_m": spacing,
            "spacing_z_m": spacing, "axes": "X=easting; Z=-northing; rows increase south",
            "target_transform": [spacing, 0., left, 0., -spacing, top],
            "target_bounds_en_m": [left, bottom, right, top], "node_location": "pixel_center"}


def _window(bounds, source):
    fractional = from_bounds(*bounds, transform=source.transform)
    col = math.floor(fractional.col_off + 1e-7)
    row = math.floor(fractional.row_off + 1e-7)
    end_col = math.ceil(fractional.col_off + fractional.width - 1e-7)
    end_row = math.ceil(fractional.row_off + fractional.height - 1e-7)
    if col < 0 or row < 0 or end_col > source.width or end_row > source.height:
        raise ValueError("bbox/halo not covered by source extent")
    return Window(col, row, end_col - col, end_row - row)


def _target_center_blocks(grid):
    rows, cols = grid["shape_zx"]
    eastings = grid["origin_x_m"] + np.arange(cols) * grid["spacing_x_m"]
    for start_row in range(0, rows, TRANSFORM_CHUNK_ROWS):
        end_row = min(start_row + TRANSFORM_CHUNK_ROWS, rows)
        northings = -(grid["origin_z_m"] + np.arange(start_row, end_row) * grid["spacing_z_m"])
        block_eastings, block_northings = np.meshgrid(eastings, northings)
        yield start_row, end_row, block_eastings.ravel(), block_northings.ravel()


def _core_mask(recipe, grid):
    rows, cols = grid["shape_zx"]
    core = np.zeros((rows, cols), bool)
    west, south, east, north = recipe["bbox_epsg4326"]
    for start_row, end_row, eastings, northings in _target_center_blocks(grid):
        longitude, latitude = transform(recipe["target_crs"], "EPSG:4326", eastings, northings)
        longitude = np.asarray(longitude)
        latitude = np.asarray(latitude)
        core[start_row:end_row] = ((longitude >= west) & (longitude <= east) &
                                   (latitude >= south) & (latitude <= north)).reshape(end_row - start_row, cols)
    return core


def _exact_sample(raw, source_valid, source_crs, source_affine, read_window, recipe, grid):
    rows, cols = grid["shape_zx"]
    height = np.full((rows, cols), np.nan, dtype="<f8")
    valid = np.zeros((rows, cols), bool)
    footprint = np.zeros((rows, cols), bool)
    for start_row, end_row, eastings, northings in _target_center_blocks(grid):
        source_x, source_y = transform(recipe["target_crs"], source_crs, eastings, northings)
        if not np.isfinite(source_x).all() or not np.isfinite(source_y).all():
            raise ValueError("nonfinite inverse-projected source coordinates")
        source_rows, source_cols = rowcol(source_affine, source_x, source_y, op=np.floor)
        local_rows = np.asarray(source_rows, dtype=np.int64) - int(read_window.row_off)
        local_cols = np.asarray(source_cols, dtype=np.int64) - int(read_window.col_off)
        inside = ((local_rows >= 0) & (local_rows < raw.shape[0]) &
                  (local_cols >= 0) & (local_cols < raw.shape[1]))
        block_valid = np.zeros(inside.shape, bool)
        block_valid[inside] = source_valid[local_rows[inside], local_cols[inside]]
        block_height = np.full(inside.shape, np.nan, dtype="<f8")
        block_height[block_valid] = raw[local_rows[block_valid], local_cols[block_valid]]
        block_shape = (end_row - start_row, cols)
        height[start_row:end_row] = block_height.reshape(block_shape)
        valid[start_row:end_row] = block_valid.reshape(block_shape)
        footprint[start_row:end_row] = inside.reshape(block_shape)
    return height, valid, footprint


def _components(mask):
    rows, cols = mask.shape
    seen = np.zeros(mask.size, bool)
    flat = mask.ravel()
    components = []
    for start in np.flatnonzero(flat):
        if seen[start]:
            continue
        seen[start] = True
        queue = deque([int(start)])
        count = 0
        boundary_cells = 0
        while queue:
            current = queue.popleft()
            count += 1
            row, col = divmod(current, cols)
            boundary_cells += int(row in (0, rows - 1) or col in (0, cols - 1))
            neighbors = []
            if row > 0:
                neighbors.append(current - cols)
            if row < rows - 1:
                neighbors.append(current + cols)
            if col > 0:
                neighbors.append(current - 1)
            if col < cols - 1:
                neighbors.append(current + 1)
            for neighbor in neighbors:
                if flat[neighbor] and not seen[neighbor]:
                    seen[neighbor] = True
                    queue.append(neighbor)
        components.append({"representative_zx": list(divmod(int(start), cols)),
                           "cells": count, "boundary_cells": boundary_cells})
    return components


def _summary(arrays):
    height = arrays["height_m"]
    valid = arrays["valid_mask"]
    unknown = arrays["unknown_mask"]
    components = _components(valid & (height <= 0))
    blockers = list(BLOCKERS)
    if unknown.any():
        blockers.append("nodata_or_unknown_coverage_blocks_hydrology_and_outlet_certification")
    if (~arrays["footprint_mask"]).any():
        blockers.append("target_footprint_edge_unknown")
    return {"status": STATUS, "publishable": False, "default_world_eligible": False,
            "natural_outlet_verified": False, "river_independently_verified": False,
            "closed_observed_candidate": False, "blockers": blockers,
            "cells": int(height.size), "valid_cells": int(valid.sum()),
            "unknown_cells": int(unknown.sum()),
            "target_nodata_cells": int((unknown & arrays["footprint_mask"]).sum()),
            "target_footprint_unknown_cells": int((~arrays["footprint_mask"]).sum()),
            "core_cells": int(arrays["core_mask"].sum()),
            "core_unknown_cells": int((unknown & arrays["core_mask"]).sum()),
            "halo_cells": int((~arrays["core_mask"]).sum()),
            "min_m": float(height[valid].min()) if valid.any() else None,
            "max_m": float(height[valid].max()) if valid.any() else None,
            "valid_components_4_connected": _components(valid),
            "unknown_components_4_connected": _components(unknown),
            "low_surface_components_4_connected": components,
            "outlet_candidates": [dict(component, kind="boundary_connected_DEM_low_surface_proxy",
                                       natural_mouth_verified=False, boundary_risk=True)
                                  for component in components if component["boundary_cells"]],
            "boundary_risk": True, "sea_proxy_is_actual_ocean": False,
            "hydrology_status": "blocked_unknown_coverage" if unknown.any() else "complete_coverage_not_routed",
            "observability": {"two_tributaries": "not_established", "mainstem": "not_established",
                              "reason": "DEM candidate alone is not independent river evidence"}}


def _seal(identity, arrays):
    manifest = {"format": DEM_FORMAT, "status": STATUS, "identity": identity,
                "identity_sha256": digest(identity), "summary": _summary(arrays),
                "array_hashes": {name: array_hash(value) for name, value in arrays.items()}}
    manifest["content_sha256"] = digest(manifest)
    for values in arrays.values():
        values.flags.writeable = False
    return {"manifest": manifest, "arrays": arrays}


def prepare_dem_candidate(source_path, bbox_epsg4326, *, target_crs, spacing_m,
                          sea_level_m, sea_datum, source_declaration,
                          vertical_datum="unknown", vertical_datum_status="unknown",
                          halo_m=900., max_cells=DEM_MAX_CELLS, max_source_cells=MAX_SOURCE_CELLS):
    """Project a bounded window; unknown units require 'elevation assumed metres'."""
    recipe = _recipe(bbox_epsg4326, target_crs, spacing_m, halo_m, sea_level_m, sea_datum,
                     source_declaration, vertical_datum, vertical_datum_status,
                     max_cells, max_source_cells)
    grid = _layout(recipe)
    source_path = Path(source_path).resolve(strict=True)
    before = file_sha256(source_path)
    with rasterio.open(source_path, "r") as source:
        if (source.driver != "GTiff" or source.crs is None or source.count != 1 or
                source.transform.b != 0 or source.transform.d != 0 or
                source.transform.a <= 0 or source.transform.e >= 0):
            raise ValueError("single-band north-up georeferenced GeoTIFF required")
        _validate_elevation_units(source.scales[0], source.offsets[0], source.units[0], source_declaration)
        core_bounds = transform_bounds("EPSG:4326", source.crs, *recipe["bbox_epsg4326"], densify_pts=41)
        core_window = _window(core_bounds, source)
        read_bounds = transform_bounds(recipe["target_crs"], source.crs,
                                       *grid["target_bounds_en_m"], densify_pts=41)
        read_window = _window(read_bounds, source)
        if read_window.width * read_window.height > max_source_cells:
            raise ValueError("source max_source_cells exceeded before raster read")
        observed = source.read(1, window=read_window, masked=True)
        source_valid = ~np.ma.getmaskarray(observed)
        if not np.isfinite(observed.data[source_valid]).all():
            raise ValueError("unmasked nonfinite source elevations")
        if not source_valid.any():
            raise ValueError("no coverage: source window contains only nodata")
        raw = np.where(source_valid, observed.data, np.nan).astype("<f8")
        row = int(core_window.row_off - read_window.row_off)
        col = int(core_window.col_off - read_window.col_off)
        core_valid = source_valid[row:row + int(core_window.height), col:col + int(core_window.width)]
        core_raw = raw[row:row + int(core_window.height), col:col + int(core_window.width)]
        height, valid, footprint = _exact_sample(raw, source_valid, source.crs, source.transform,
                                                read_window, recipe, grid)
        nodata = source.nodata
        if nodata is not None and not math.isfinite(nodata):
            nodata = str(nodata)
        source_record = {"path": str(source_path), "sha256": before, "crs": source.crs.to_string(),
                         "driver": source.driver, "band_count": source.count, "dtype": source.dtypes[0],
                         "band_unit": source.units[0], "band_scale": source.scales[0], "band_offset": source.offsets[0],
                         "transform": list(source.transform)[:6], "extent": list(source.bounds),
                         "shape_zx": list(source.shape), "resolution_source_units": list(source.res),
                         "nodata": nodata, "area_or_point": source.tags().get("AREA_OR_POINT", "unknown"),
                         "node_location": "pixel_center", "pixel_center_offset_col_row": [0.5, 0.5],
                         "read_window_col_row_width_height": list(read_window.flatten()),
                         "read_transform": list(source.window_transform(read_window))[:6],
                         "read_shape_zx": list(raw.shape), "read_cells": int(raw.size),
                         "read_nodata_cells": int((~source_valid).sum()),
                         "requested_window_shape_zx": [int(core_window.height), int(core_window.width)],
                         "requested_window_nodata_cells": int((~core_valid).sum()),
                         "requested_window_unknown_components_4_connected": _components(~core_valid),
                         "requested_window_valid_low_cells": int(np.count_nonzero(core_valid & (core_raw <= 0))),
                         "requested_window_min_m": float(np.nanmin(core_raw)) if core_valid.any() else None,
                         "requested_window_max_m": float(np.nanmax(core_raw)) if core_valid.any() else None}
    if file_sha256(source_path) != before:
        raise ValueError("source changed during preparation")
    if not valid.any():
        raise ValueError("no coverage: target contains only unknown elevations")
    arrays = {"height_m": height, "valid_mask": valid, "unknown_mask": ~valid,
              "footprint_mask": footprint, "core_mask": _core_mask(recipe, grid)}
    return _seal({"algorithm": DEM_ALGORITHM, "recipe": recipe, "recipe_sha256": digest(recipe),
                  "source": source_record, "grid": grid, "rasterio_version": rasterio.__version__}, arrays)


def validate_dem_candidate(candidate, *, verify_source=True):
    """Reject hashes and self-rehashed false publication/coverage semantics."""
    if set(candidate) != {"manifest", "arrays"}:
        raise ValueError("invalid candidate fields")
    manifest, arrays = candidate["manifest"], candidate["arrays"]
    if set(manifest) != {"format", "status", "identity", "identity_sha256", "summary", "array_hashes", "content_sha256"}:
        raise ValueError("invalid manifest fields")
    if manifest["format"] != DEM_FORMAT or manifest["status"] != STATUS:
        raise ValueError("DEM candidate cannot publish")
    identity = manifest["identity"]
    if set(identity) != {"algorithm", "recipe", "recipe_sha256", "source", "grid", "rasterio_version"}:
        raise ValueError("invalid identity fields")
    if identity["algorithm"] != DEM_ALGORITHM or manifest["identity_sha256"] != digest(identity):
        raise ValueError("algorithm or identity hash mismatch")
    recipe = identity["recipe"]
    rebuilt = _recipe(recipe["bbox_epsg4326"], recipe["target_crs"], recipe["spacing_m"],
                      recipe["halo_m"], recipe["sea_level_m"], recipe["sea_datum"],
                      recipe["source_declaration"], recipe["vertical_datum"], recipe["vertical_datum_status"],
                      recipe["max_cells"], recipe["max_source_cells"])
    if recipe != rebuilt or identity["recipe_sha256"] != digest(recipe) or identity["grid"] != _layout(recipe):
        raise ValueError("recipe or grid semantics mismatch")
    if set(arrays) != ARRAY_NAMES or set(manifest["array_hashes"]) != ARRAY_NAMES:
        raise ValueError("invalid array fields")
    shape = tuple(identity["grid"]["shape_zx"])
    for name, values in arrays.items():
        expected_dtype = np.dtype("<f8") if name == "height_m" else np.dtype(bool)
        if values.shape != shape or values.dtype != expected_dtype:
            raise ValueError("invalid array shape or dtype")
        if array_hash(values) != manifest["array_hashes"][name]:
            raise ValueError("array hash mismatch")
    height = arrays["height_m"]
    if (not np.array_equal(arrays["valid_mask"], np.isfinite(height)) or
            not np.array_equal(arrays["unknown_mask"], ~arrays["valid_mask"]) or
            not np.isnan(height[arrays["unknown_mask"]]).all() or
            np.any(arrays["valid_mask"] & ~arrays["footprint_mask"]) or
            not np.array_equal(arrays["core_mask"], _core_mask(recipe, identity["grid"]))):
        raise ValueError("invalid finite/nodata/coverage semantics")
    if manifest["summary"] != _summary(arrays):
        raise ValueError("candidate evidence or summary semantics mismatch; cannot publish")
    if manifest["content_sha256"] != digest({name: value for name, value in manifest.items() if name != "content_sha256"}):
        raise ValueError("content hash mismatch")
    source = identity["source"]
    if (source["read_cells"] != math.prod(source["read_shape_zx"]) or
            not 0 < source["read_cells"] <= recipe["max_source_cells"] or
            source["node_location"] != "pixel_center" or
            source["pixel_center_offset_col_row"] != [0.5, 0.5]):
        raise ValueError("source resource or center semantics mismatch")
    _validate_source_geometry(source, recipe, identity["grid"])
    if not arrays["valid_mask"].any():
        raise ValueError("no coverage: candidate contains only unknown elevations")
    if verify_source:
        if file_sha256(source["path"]) != source["sha256"]:
            raise ValueError("source hash mismatch")
        replay = prepare_dem_candidate(
            source["path"], recipe["bbox_epsg4326"], target_crs=recipe["target_crs"],
            spacing_m=recipe["spacing_m"], sea_level_m=recipe["sea_level_m"],
            sea_datum=recipe["sea_datum"], source_declaration=recipe["source_declaration"],
            vertical_datum=recipe["vertical_datum"], vertical_datum_status=recipe["vertical_datum_status"],
            halo_m=recipe["halo_m"], max_cells=recipe["max_cells"], max_source_cells=recipe["max_source_cells"])
        if identity != replay["manifest"]["identity"]:
            raise ValueError("source header, window or provenance replay mismatch")
        for name, values in arrays.items():
            if not np.array_equal(values, replay["arrays"][name], equal_nan=True):
                raise ValueError("source projection replay mismatch: forged height or coverage")


def _validate_source_geometry(source, recipe, grid):
    expected = {"path", "sha256", "crs", "driver", "band_count", "dtype", "band_unit", "band_scale",
                "band_offset", "transform", "extent", "shape_zx", "resolution_source_units", "nodata",
                "area_or_point", "node_location", "pixel_center_offset_col_row", "read_window_col_row_width_height",
                "read_transform", "read_shape_zx", "read_cells", "read_nodata_cells", "requested_window_shape_zx",
                "requested_window_nodata_cells", "requested_window_unknown_components_4_connected",
                "requested_window_valid_low_cells", "requested_window_min_m", "requested_window_max_m"}
    if set(source) != expected or source["driver"] != "GTiff" or source["band_count"] != 1:
        raise ValueError("invalid single-band source header fields")
    _validate_elevation_units(source["band_scale"], source["band_offset"], source["band_unit"],
                              recipe["source_declaration"])
    affine = Affine(*source["transform"])
    rows, cols = source["shape_zx"]
    if (type(rows) is not int or type(cols) is not int or rows <= 0 or cols <= 0 or
            not np.isfinite(source["transform"]).all() or affine.b != 0 or affine.d != 0 or
            affine.a <= 0 or affine.e >= 0 or
            source["extent"] != [affine.c, affine.f + rows * affine.e,
                                 affine.c + cols * affine.a, affine.f] or
            source["resolution_source_units"] != [affine.a, -affine.e]):
        raise ValueError("source affine, extent or resolution semantics mismatch")
    crs = CRS.from_user_input(source["crs"])
    header = SimpleNamespace(transform=affine, width=cols, height=rows)
    bounds = transform_bounds(recipe["target_crs"], crs, *grid["target_bounds_en_m"], densify_pts=41)
    window = _window(bounds, header)
    core_bounds = transform_bounds("EPSG:4326", crs, *recipe["bbox_epsg4326"], densify_pts=41)
    core_window = _window(core_bounds, header)
    read_affine = affine * Affine.translation(window.col_off, window.row_off)
    if (source["read_window_col_row_width_height"] != list(window.flatten()) or
            source["read_transform"] != list(read_affine)[:6] or
            source["read_shape_zx"] != [int(window.height), int(window.width)] or
            source["requested_window_shape_zx"] != [int(core_window.height), int(core_window.width)]):
        raise ValueError("source read window/transform/shape semantics mismatch")
    if (not 0 <= source["read_nodata_cells"] < source["read_cells"] or
            not 0 <= source["requested_window_nodata_cells"] <= math.prod(source["requested_window_shape_zx"])):
        raise ValueError("source coverage count semantics mismatch")


def save_dem_candidate(candidate, path):
    """Atomically link a verified NPZ into place without replacing a file."""
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    validate_dem_candidate(candidate)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}-", suffix=".npz", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, manifest=canonical_json(candidate["manifest"]), **candidate["arrays"])
            stream.flush()
            os.fsync(stream.fileno())
        load_dem_candidate(temporary)
        os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _dem_unique_pairs(pairs):
    record = {}
    for name, value in pairs:
        if name in record:
            raise ValueError("duplicate manifest key")
        record[name] = value
    return record


def _dem_reject_constant(value):
    raise ValueError(f"nonfinite manifest constant: {value}")


def load_dem_candidate(path, *, verify_source=True):
    """Default: bounded source replay. False: offline structure only, not evidence."""
    with np.load(path, allow_pickle=False) as archive:
        if len(archive.files) != len(ARRAY_NAMES) + 1 or set(archive.files) != ARRAY_NAMES | {"manifest"}:
            raise ValueError("unexpected NPZ payload")
        manifest = json.loads(str(archive["manifest"].item()), object_pairs_hook=_dem_unique_pairs,
                              parse_constant=_dem_reject_constant)
        arrays = {name: archive[name].copy() for name in ARRAY_NAMES}
    candidate = {"manifest": manifest, "arrays": arrays}
    validate_dem_candidate(candidate, verify_source=verify_source)
    for values in arrays.values():
        values.flags.writeable = False
    return candidate


def route_dem_candidate(candidate, outlet_mask=None):
    """Diagnostic irregular graph with explicit outlets and the stored metric frame."""
    validate_dem_candidate(candidate)
    arrays = candidate["arrays"]
    if arrays["unknown_mask"].any():
        raise ValueError("nodata/unknown coverage blocks hydrology and outlet certification")
    height = arrays["height_m"]
    rows, cols = height.shape
    if outlet_mask is None:
        raise ValueError("explicit bool outlet_mask required; no artificial outlet fallback")
    outlets = np.asarray(outlet_mask)
    if (outlets.dtype != np.dtype(bool) or outlets.shape != height.shape or
            not outlets.any() or np.any(outlets & ~arrays["valid_mask"])):
        raise ValueError("explicit outlets must be nonempty bool, same shape and valid")
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import route_graph as route_graph
    from terrain_pipeline.surface_rivers.contracts import RoutingResult
    frame = candidate["manifest"]["identity"]["grid"]
    spacing = float(frame["spacing_x_m"])
    mesh = grid_mesh(height.shape, x0_m=frame["origin_x_m"], z0_m=frame["origin_z_m"],
                     dx_m=spacing, dz_m=frame["spacing_z_m"])
    graph = route_graph(height, outlets, mesh)
    routing = RoutingResult(graph.receiver, graph.order, graph.filled, outlets, spacing)
    cell_area_m2 = spacing * float(frame["spacing_z_m"])
    area = accumulate(routing, np.full(height.shape, cell_area_m2 / spacing ** 2), spacing)
    terminal = np.full(height.size, -1, np.int64)
    boundary = np.zeros(height.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    for cell in routing.order:
        receiver = routing.receiver[cell]
        terminal[cell] = cell if receiver < 0 else terminal[receiver]
    land = ~outlets.ravel()
    mouths, counts = np.unique(terminal[land], return_counts=True)
    risky = set(terminal[boundary.ravel() & land].tolist())
    candidates = [{"explicit_outlet_zx": list(divmod(int(mouth), cols)), "land_cells": int(count),
                   "closed_observed_candidate": int(mouth) not in risky,
                   "boundary_risk": int(mouth) in risky, "natural_mouth_verified": False,
                   "river_independently_verified": False} for mouth, count in zip(mouths, counts)]
    return {"status": STATUS, "publishable": False, "routing": routing,
            "contributing_area_m2": area.discharge, "outlet_candidates": candidates,
            "note": "Unit-flux contributing area, not calibrated runoff or verified river topology; priority flood is diagnostic only."}



# ------------------------------------------------------------------------
# 原 terrain_pipeline/geography_preparation_inventory.py
# ------------------------------------------------------------------------

INVENTORY_VERSION = "geography-preparation-inventory-v1"


MAX_MANIFEST_BYTES = 1024 * 1024


DATA = "01-完整流域样本/data/"


KNOWN = {
    "srtm_61_07.tif": "source_dem_candidate",
    "srtm_61_07.hdr": "source_dem_sidecar",
    "srtm_61_07.tfw": "source_dem_sidecar",
    "srtm_61_07.zip": "source_dem_archive",
    "readme.txt": "source_claim_unverified",
    "ninghai_water_plan_ch3.pdf": "source_document_candidate",
    "funxi_basin_report.json": "dem_derived_candidate",
    "funxi_coarse_basin.json": "dem_derived_candidate",
    "funxi_control_section.json": "area_selected_candidate",
    "funxi_mouth_trace.json": "dem_derived_candidate",
    "funxi_srtm30m_grid.csv": "dem_derived_candidate",
    "funxi_srtm30m_grid_wide.csv": "dem_derived_candidate",
    "funxi_climate_runoff.csv": "modeled_climate_runoff_candidate",
    "valley_cross_sections.json": "other_place_sections",
}


REQUIREMENTS = {
    "valid_real_basin_coverage": ([DATA + "srtm_61_07.tif", DATA + "funxi_basin_report.json", DATA + "funxi_coarse_basin.json"], "DEM coverage and area-selected basin do not certify a real basin boundary or outlet"),
    "vertical_datum": ([DATA + "srtm_61_07.hdr", DATA + "srtm_61_07.tfw", DATA + "readme.txt"], "Horizontal WGS84 and angular pixel spacing do not establish a vertical datum"),
    "independent_river_tributaries": ([DATA + "hydrosheds/HydroRIVERS_v10_as_shp.zip", DATA + "funxi_basin_report.json"], "Regional vector archive and DEM extraction need independent local alignment and tributary verification"),
    "mouth_and_coast": ([DATA + "funxi_mouth_trace.json", DATA + "funxi_control_section.json"], "DEM trace and proposed control point do not certify mouth or coast"),
    "same_place_sections_synchronous_flow": (["02-河谷断面与形态/data/valley_cross_sections.json", DATA + "funxi_climate_runoff.csv"], "Other-place sections and modeled runoff are not colocated synchronous observations"),
    "lake_dam_boundaries": ([DATA + "depression_vs_reservoirs.json", DATA + "ninghai_reservoirs_geocoded.csv"], "DEM depressions and geocoded reservoirs do not certify lake or dam boundary conditions"),
}


class InventoryError(ValueError):
    def __init__(self, diagnostic):
        self.diagnostics = [diagnostic]
        super().__init__(diagnostic)


@dataclass(frozen=True)
class InventoryLimits:
    max_files: int = 512
    max_directories: int = 512
    max_entries: int = 2048
    max_total_bytes: int = 512 * 1024 * 1024
    max_file_bytes: int = 128 * 1024 * 1024
    max_metadata_bytes: int = 64 * 1024

    def __post_init__(self):
        caps = (4096, 4096, 16384, 2 * 1024**3, 512 * 1024**2, 1024 * 1024)
        if any(type(value) is not int or not 0 < value <= cap for value, cap in zip(self.__dict__.values(), caps)):
            raise InventoryError("invalid resource limits")


def _inventory_digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _inventory_unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _inventory_reject_constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")


def _strict_json(content):
    return json.loads(content, object_pairs_hook=_inventory_unique_pairs, parse_constant=_inventory_reject_constant)


def _safe_relative(path):
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or "\x00" in path:
        return False
    parts = path.split("/")
    return all(part not in ("", ".", "..") for part in parts) and not path.startswith("/")


def _kind(path):
    if path.startswith(DATA) and path[len(DATA):] in KNOWN:
        return KNOWN[path[len(DATA):]]
    if path == "02-河谷断面与形态/data/valley_cross_sections.json":
        return "other_place_sections"
    if path.startswith("03-河床与水力/data/") or path.startswith("04-湖泊与溢流/data/"):
        return "other_place_hydraulics"
    if path.startswith(DATA + "hydrosheds/"):
        return "regional_vector_candidate"
    if path.startswith(DATA + "depression/") or path.startswith(DATA) and path.endswith(("depression_vs_reservoirs.json", "ninghai_reservoirs_geocoded.csv")):
        return "dem_derived_candidate"
    return "unreviewed"


def _extract(path, relative, limit):
    if relative in {DATA + "srtm_61_07.hdr", DATA + "srtm_61_07.tfw"}:
        if path.stat().st_size > limit:
            return {"status": "skipped_metadata_limit"}
        try:
            content = path.read_text(encoding="utf-8-sig")
            if relative.endswith(".tfw"):
                numbers = [float(line.strip()) for line in content.splitlines()]
                if len(numbers) != 6 or not all(math.isfinite(number) for number in numbers):
                    raise ValueError("invalid world file")
                return {"status": "parsed_unverified", "world_file_coefficients": numbers}
            return {"status": "parsed_unverified", "declares_wgs84_horizontal": "GCS_WGS_84" in content,
                    "declares_vertical_datum": "VerticalCSTypeGeoKey" in content}
        except (OSError, UnicodeError, ValueError) as error:
            return {"status": "parse_failed", "reason": type(error).__name__}
    if not relative.startswith(DATA) or relative[len(DATA):] not in {
        "funxi_basin_report.json", "funxi_control_section.json", "funxi_mouth_trace.json",
        "funxi_coarse_basin.json", "funxi_climate_runoff.csv"}:
        return None
    if path.stat().st_size > limit:
        return {"status": "skipped_metadata_limit"}
    try:
        content = path.read_text(encoding="utf-8-sig")
        if relative.endswith(".json"):
            value = _strict_json(content)
            if not isinstance(value, dict):
                raise ValueError("expected object")
            result = {"status": "parsed_unverified", "top_level_keys": sorted(value)[:64]}
            if relative.endswith("funxi_control_section.json"):
                control = value.get("control_section")
                if isinstance(control, dict) and type(control.get("upstream_area_km2")) in (int, float):
                    result["reported_control_upstream_area_km2"] = control["upstream_area_km2"]
            return result
        rows = list(csv.reader(io.StringIO(content)))
        if not rows or len(rows) > 4096 or len(rows[0]) > 128:
            raise ValueError("invalid CSV dimensions")
        return {"status": "parsed_unverified", "columns": rows[0], "data_rows": len(rows) - 1}
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        return {"status": "parse_failed", "reason": type(error).__name__}


def prepare_inventory(root, limits=InventoryLimits()):
    if not isinstance(limits, InventoryLimits):
        raise InventoryError("invalid resource limits")
    root = Path(root).absolute()
    if not root.is_dir():
        raise InventoryError("source root must be a real directory")
    for ancestor in (root, *root.parents):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise InventoryError(f"source root traverses link or reparse point: {ancestor}")
    files = []
    diagnostics = []
    total = 0
    stack = [root]
    directory_count = 0
    entry_count = 0
    while stack:
        directory = stack.pop()
        directory_count += 1
        if directory_count > limits.max_directories:
            raise InventoryError(f"directory limit at {directory}; visited={directory_count}")
        try:
            with os.scandir(directory) as listing:
                entries = []
                for entry in listing:
                    entry_count += 1
                    if entry_count > limits.max_entries:
                        raise InventoryError(f"entry limit at {directory}; seen={entry_count}")
                    entries.append(entry)
            entries.sort(key=lambda item: item.name)
        except OSError as error:
            raise InventoryError(f"cannot scan {directory}: {error}") from error
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            if not _safe_relative(relative):
                raise InventoryError(f"unsafe source path: {relative}")
            try:
                info = os.stat(entry.path, follow_symlinks=False)
                is_reparse = bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
                if entry.is_symlink() or is_reparse:
                    diagnostics.append({"path": relative, "status": "skipped_link_or_reparse"})
                    continue
                if stat.S_ISDIR(info.st_mode):
                    if directory_count + len(stack) + 1 > limits.max_directories:
                        raise InventoryError(f"directory limit at {relative}; pending={len(stack)}")
                    stack.append(Path(entry.path))
                    continue
                if not stat.S_ISREG(info.st_mode):
                    diagnostics.append({"path": relative, "status": "skipped_non_regular"})
                    continue
                if len(files) >= limits.max_files or info.st_size > limits.max_file_bytes or total + info.st_size > limits.max_total_bytes:
                    raise InventoryError(f"resource limit at {relative}; files={len(files)}, bytes={total}, next={info.st_size}")
                hasher = hashlib.sha256()
                with open(entry.path, "rb") as source:
                    while chunk := source.read(1024 * 1024):
                        hasher.update(chunk)
                after = os.stat(entry.path, follow_symlinks=False)
                if (after.st_size, after.st_mtime_ns, after.st_ino) != (info.st_size, info.st_mtime_ns, info.st_ino):
                    raise InventoryError(f"source changed during read: {relative}")
                file = {"path": relative, "type": Path(relative).suffix.lower() or "extensionless", "bytes": info.st_size,
                        "sha256": hasher.hexdigest(), "source_class": _kind(relative)}
                metadata = _extract(Path(entry.path), relative, limits.max_metadata_bytes)
                after_metadata = os.stat(entry.path, follow_symlinks=False)
                if (after_metadata.st_size, after_metadata.st_mtime_ns, after_metadata.st_ino) != (info.st_size, info.st_mtime_ns, info.st_ino):
                    raise InventoryError(f"source changed during metadata read: {relative}")
                if metadata is not None:
                    file["metadata"] = metadata
                files.append(file)
                total += info.st_size
            except OSError as error:
                raise InventoryError(f"cannot read {relative}: {error}") from error
    files.sort(key=lambda file: file["path"])
    present = {file["path"] for file in files}
    requirements = {name: {"available_files": [path for path in paths if path in present], "certified": False, "limitation": reason}
                    for name, (paths, reason) in REQUIREMENTS.items()}
    payload = {"format": INVENTORY_VERSION, "source_root": str(root), "file_count": len(files), "total_bytes": total,
               "files": files, "diagnostics": diagnostics, "requirements": requirements,
               "readiness": {"real_basin_certified": False, "outlet_certified": False, "ready": False,
                             "conclusion": "Candidate materials exist; real basin and outlet are not certified."}}
    payload["identity"] = _inventory_digest(payload)
    validate(payload)
    return payload


def validate(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"format", "source_root", "file_count", "total_bytes", "files", "diagnostics", "requirements", "readiness", "identity"}:
        raise InventoryError("invalid manifest fields")
    if manifest["format"] != INVENTORY_VERSION or not isinstance(manifest["source_root"], str) or not Path(manifest["source_root"]).is_absolute():
        raise InventoryError("invalid manifest format or root")
    files = manifest["files"]
    if not isinstance(files, list) or len(files) > 4096 or type(manifest["file_count"]) is not int or manifest["file_count"] != len(files):
        raise InventoryError("invalid file count")
    seen = set()
    total = 0
    for file in files:
        if not isinstance(file, dict) or not {"path", "type", "bytes", "sha256", "source_class"} <= set(file) or set(file) - {"path", "type", "bytes", "sha256", "source_class", "metadata"}:
            raise InventoryError("invalid file record")
        path = file["path"]
        if not _safe_relative(path) or path in seen or file["type"] != (Path(path).suffix.lower() or "extensionless") or file["source_class"] != _kind(path):
            raise InventoryError("unsafe or inconsistent file record")
        seen.add(path)
        if type(file["bytes"]) is not int or not 0 <= file["bytes"] <= 512 * 1024**2 or not isinstance(file["sha256"], str) or len(file["sha256"]) != 64 or any(char not in "0123456789abcdef" for char in file["sha256"]):
            raise InventoryError("invalid file size or hash")
        if "metadata" in file:
            metadata = file["metadata"]
            if not isinstance(metadata, dict) or metadata.get("status") not in {"skipped_metadata_limit", "parsed_unverified", "parse_failed"} or set(metadata) - {"status", "top_level_keys", "reported_control_upstream_area_km2", "columns", "data_rows", "reason", "world_file_coefficients", "declares_wgs84_horizontal", "declares_vertical_datum"}:
                raise InventoryError("invalid metadata")
            status = metadata["status"]
            if (status == "skipped_metadata_limit" and set(metadata) != {"status"}
                    or status == "parse_failed" and set(metadata) != {"status", "reason"}
                    or status == "parsed_unverified" and ("reason" in metadata or len(metadata) == 1)):
                raise InventoryError("inconsistent metadata status")
            if ("columns" in metadata) != ("data_rows" in metadata):
                raise InventoryError("inconsistent CSV metadata")
            if ("declares_wgs84_horizontal" in metadata) != ("declares_vertical_datum" in metadata):
                raise InventoryError("inconsistent sidecar metadata")
            if "top_level_keys" in metadata and (not isinstance(metadata["top_level_keys"], list) or len(metadata["top_level_keys"]) > 64 or any(not isinstance(key, str) for key in metadata["top_level_keys"])):
                raise InventoryError("invalid metadata keys")
            if "columns" in metadata and (not isinstance(metadata["columns"], list) or len(metadata["columns"]) > 128 or any(not isinstance(column, str) for column in metadata["columns"])):
                raise InventoryError("invalid metadata columns")
            if "data_rows" in metadata and (type(metadata["data_rows"]) is not int or not 0 <= metadata["data_rows"] <= 4095):
                raise InventoryError("invalid metadata rows")
            if "reported_control_upstream_area_km2" in metadata and (type(metadata["reported_control_upstream_area_km2"]) not in (int, float) or not math.isfinite(metadata["reported_control_upstream_area_km2"])):
                raise InventoryError("invalid metadata area")
            if "world_file_coefficients" in metadata and (not isinstance(metadata["world_file_coefficients"], list) or len(metadata["world_file_coefficients"]) != 6 or any(type(number) not in (int, float) or not math.isfinite(number) for number in metadata["world_file_coefficients"])):
                raise InventoryError("invalid metadata world file")
            if any(type(metadata[key]) is not bool for key in ("declares_wgs84_horizontal", "declares_vertical_datum") if key in metadata) or "reason" in metadata and (not isinstance(metadata["reason"], str) or len(metadata["reason"]) > 64):
                raise InventoryError("invalid metadata flags")
            if len(json.dumps(metadata, ensure_ascii=False, allow_nan=False)) > 65536:
                raise InventoryError("invalid metadata")
        total += file["bytes"]
    if [file["path"] for file in files] != sorted(seen) or type(manifest["total_bytes"]) is not int or total != manifest["total_bytes"] or total > 2 * 1024**3:
        raise InventoryError("invalid totals or order")
    if not isinstance(manifest["diagnostics"], list) or len(manifest["diagnostics"]) > 4096:
        raise InventoryError("invalid diagnostics")
    for diagnostic in manifest["diagnostics"]:
        if not isinstance(diagnostic, dict) or set(diagnostic) != {"path", "status"} or not _safe_relative(diagnostic["path"]) or diagnostic["status"] not in {"skipped_link_or_reparse", "skipped_non_regular"}:
            raise InventoryError("invalid diagnostic")
    expected = {name: {"available_files": [path for path in paths if path in seen], "certified": False, "limitation": reason}
                for name, (paths, reason) in REQUIREMENTS.items()}
    if not isinstance(manifest["requirements"], dict) or any(
            not isinstance(item, dict) or type(item.get("certified")) is not bool
            for item in manifest["requirements"].values()):
        raise InventoryError("invalid requirement flags")
    if not isinstance(manifest["readiness"], dict) or any(
            type(manifest["readiness"].get(name)) is not bool
            for name in ("real_basin_certified", "outlet_certified", "ready")):
        raise InventoryError("invalid readiness flags")
    if manifest["requirements"] != expected or manifest["readiness"] != {"real_basin_certified": False, "outlet_certified": False, "ready": False, "conclusion": "Candidate materials exist; real basin and outlet are not certified."}:
        raise InventoryError("invalid readiness or requirements")
    identity = manifest["identity"]
    if not isinstance(identity, str) or identity != _inventory_digest({key: value for key, value in manifest.items() if key != "identity"}):
        raise InventoryError("manifest identity mismatch")


def save(manifest, destination):
    validate(manifest)
    encoded = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise InventoryError("manifest exceeds size limit")
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".inventory-", delete=False) as output:
            temporary = Path(output.name)
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def load(source):
    source = Path(source)
    if source.stat().st_size > MAX_MANIFEST_BYTES:
        raise InventoryError("manifest exceeds size limit")
    try:
        manifest = _strict_json(source.read_text(encoding="utf-8"))
        validate(manifest)
    except (UnicodeError, json.JSONDecodeError, TypeError, OverflowError, ValueError) as error:
        raise InventoryError(f"invalid manifest: {error}") from error
    return manifest



# ------------------------------------------------------------------------
# 原 terrain_pipeline/hydrology_detail_td.py
# ------------------------------------------------------------------------

HYDROLOGY_TD_ALGORITHM = "hydrology-global-native-core256-query257-v1"


CORE = 256


QUERY_SIZE = 257


def _hydrology_td_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def source_contract(base_identity):
    return {"algorithm": HYDROLOGY_TD_ALGORITHM, "base_generation_identity": base_identity,
            "core_size": CORE, "inference_query_size": QUERY_SIZE,
            "ownership": "floor(native_coordinate/256); northwest core; halo diagnostic only",
            "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class CanonicalTDSource:
    def __init__(self, backend, cache_root):
        self.backend = backend
        self.contract = source_contract(backend.identity)
        self.identity = _hydrology_td_digest(self.contract)
        self.cache_root = Path(cache_root) / self.identity

    def close(self):
        self.backend.close()

    def _tile(self, seed, tx, tz):
        folder = self.cache_root / str(seed & 0xFFFFFFFFFFFFFFFF)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("tile-x" + str(tx) + "-z" + str(tz) + ".npz")
        pin = path.with_suffix(".sha256")
        native_origin = [tx * CORE, tz * CORE]
        if not path.exists():
            for adapter_hash in sorted(published_algorithm_hashes("hydrology_detail_td")):
                old_contract = dict(self.contract, adapter_sha256=adapter_hash)
                old_identity = _hydrology_td_digest(old_contract)
                old_path = self.cache_root.parent / old_identity / str(seed & 0xFFFFFFFFFFFFFFFF) / path.name
                if old_path.is_file():
                    path = old_path
                    pin = path.with_suffix(".sha256")
                    break
        if not path.exists():
            elevation, climate, metadata = self.backend.generate(seed, *native_origin, QUERY_SIZE)
            with path.open("xb") as stream:
                np.savez_compressed(stream, elevation_m=elevation, climate=climate,
                                    metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
            with pin.open("x", encoding="ascii") as stream:
                stream.write(file_sha256(path))
        if not pin.exists():
            raise ValueError("canonical tile lacks immutable external hash pin")
        sha = pin.read_text(encoding="ascii").strip()
        arrays = checked_archive(path, expected_sha256=sha)
        if set(arrays) != {"elevation_m", "climate", "metadata_json"}:
            raise ValueError("canonical tile archive fields mismatch")
        metadata = json.loads(str(arrays["metadata_json"].item()))
        if (metadata["identity"] != self.backend.identity or int(metadata["seed"]) != seed & 0xFFFFFFFFFFFFFFFF
                or metadata["native_origin"] != native_origin or metadata["shape"] != [QUERY_SIZE, QUERY_SIZE]
                or metadata["artifact_kind"] != "terrain_diffusion_output"
                or arrays["elevation_m"].shape != (QUERY_SIZE, QUERY_SIZE)
                or arrays["climate"].shape != (5, QUERY_SIZE, QUERY_SIZE)
                or not np.isfinite(arrays["elevation_m"]).all() or not np.isfinite(arrays["climate"]).all()):
            raise ValueError("canonical tile seed/model/grid/finite contract mismatch")
        record = {"tile_xz": [tx, tz], "native_origin": native_origin, "sha256": sha,
                  "tile_file": path.name, "cache_identity": path.parent.parent.name, "generation_identity": self.backend.identity,
                  "generation_metadata": metadata}
        return arrays["elevation_m"], arrays["climate"], record

    def generate(self, seed, x, z, size):
        if any(type(value) is not int for value in (seed, x, z, size)) or not 1 <= size <= 499:
            raise ValueError("bounded native canonical query requires size1..499")
        elevation = np.empty((size, size), dtype=np.float32)
        climate = np.empty((5, size, size), dtype=np.float32)
        records = []
        for tz in range(z // CORE, (z + size - 1) // CORE + 1):
            for tx in range(x // CORE, (x + size - 1) // CORE + 1):
                tile_h, tile_c, record = self._tile(seed, tx, tz)
                left, right = max(x, tx * CORE), min(x + size, (tx + 1) * CORE)
                top, bottom = max(z, tz * CORE), min(z + size, (tz + 1) * CORE)
                src = (slice(top - tz * CORE, bottom - tz * CORE), slice(left - tx * CORE, right - tx * CORE))
                dst = (slice(top - z, bottom - z), slice(left - x, right - x))
                elevation[dst] = tile_h[src]
                climate[(slice(None),) + dst] = tile_c[(slice(None),) + src]
                records.append(record)
        metadata = dict(self.backend.metadata, schema="hydrology-canonical-td-window-v1",
            identity=self.identity, base_generation_identity=self.backend.identity,
            canonical_source_contract=self.contract, seed=str(seed & 0xFFFFFFFFFFFFFFFF),
            native_origin=[x, z], shape=[size, size], native_resolution_m=self.backend.config.native_resolution_m,
            artifact_kind="terrain_diffusion_output", tile_assembly=records,
            canonical_cache_root=str(self.cache_root.parent.resolve()),
            query_size_invariant=True, hydrologic_seam_certified=False)
        return elevation, climate, metadata


def load_canonical_window(path, expected_sha256):
    arrays = checked_archive(path, expected_sha256=expected_sha256)
    if set(arrays) != {"elevation_m", "climate", "metadata_json"}:
        raise ValueError("canonical assembled archive fields mismatch")
    metadata = json.loads(str(arrays["metadata_json"].item()))
    shape = arrays["elevation_m"].shape
    contract = metadata["canonical_source_contract"]
    if (metadata.get("schema") != "hydrology-canonical-td-window-v1" or metadata["identity"] != _hydrology_td_digest(contract)
            or not published_algorithm_matches("hydrology_detail_td", contract.get("adapter_sha256"), hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
            or contract["algorithm"] != HYDROLOGY_TD_ALGORITHM or contract["core_size"] != CORE or contract["inference_query_size"] != QUERY_SIZE
            or metadata["base_generation_identity"] != contract["base_generation_identity"]
            or metadata["artifact_kind"] != "terrain_diffusion_output" or metadata["shape"] != list(shape)
            or len(shape) != 2 or shape[0] != shape[1] or shape[0] > 499
            or arrays["climate"].shape != (5,) + shape or not np.isfinite(arrays["elevation_m"]).all()
            or not np.isfinite(arrays["climate"]).all()):
        raise ValueError("canonical assembled source contract mismatch")
    native = metadata["native_origin"]
    spacing = metadata["native_resolution_m"]
    if len(native) != 2 or any(type(value) is not int for value in native) or spacing != 30.0:
        raise ValueError("canonical metre/native coordinate contract mismatch")
    tile_records = metadata["tile_assembly"]
    expected_tiles = {(tx, tz) for tz in range(native[1] // CORE, (native[1] + shape[0] - 1) // CORE + 1)
                      for tx in range(native[0] // CORE, (native[0] + shape[1] - 1) // CORE + 1)}
    if len(tile_records) != len(expected_tiles) or {tuple(record["tile_xz"]) for record in tile_records} != expected_tiles:
        raise ValueError("canonical tile assembly ownership mismatch")
    reconstructed = np.empty_like(arrays["elevation_m"])
    reconstructed_climate = np.empty_like(arrays["climate"])
    for record in tile_records:
        tx, tz = record["tile_xz"]
        filename = "tile-x" + str(tx) + "-z" + str(tz) + ".npz"
        if record["tile_file"] != filename or record["native_origin"] != [tx * CORE, tz * CORE]:
            raise ValueError("canonical component filename/origin mismatch")
        generated = record["generation_metadata"]
        base_record = {key: value for key, value in generated.items() if key not in {
            "identity", "seed", "native_origin", "shape", "native_resolution_m", "artifact_kind", "seconds"}}
        if (generated["identity"] != metadata["base_generation_identity"] or _hydrology_td_digest(base_record) != generated["identity"]
                or generated["native_origin"] != record["native_origin"] or generated["shape"] != [QUERY_SIZE, QUERY_SIZE]
                or generated["seed"] != metadata["seed"]):
            raise ValueError("canonical component real generation identity mismatch")
        cache_identity = record.get("cache_identity", metadata["identity"])
        allowed_cache_ids = {_hydrology_td_digest(dict(contract, adapter_sha256=value))
                             for value in published_algorithm_hashes("hydrology_detail_td")}
        allowed_cache_ids.add(_hydrology_td_digest(contract))
        if cache_identity not in allowed_cache_ids:
            raise ValueError("canonical cache identity is not a published adapter")
        tile_path = Path(metadata["canonical_cache_root"]) / cache_identity / metadata["seed"] / filename
        tile = checked_archive(tile_path, expected_sha256=record["sha256"])
        if json.loads(str(tile["metadata_json"].item())) != generated:
            raise ValueError("canonical component metadata differs from pinned original")
        left, right = max(native[0], tx * CORE), min(native[0] + shape[1], (tx + 1) * CORE)
        top, bottom = max(native[1], tz * CORE), min(native[1] + shape[0], (tz + 1) * CORE)
        src = (slice(top - tz * CORE, bottom - tz * CORE), slice(left - tx * CORE, right - tx * CORE))
        dst = (slice(top - native[1], bottom - native[1]), slice(left - native[0], right - native[0]))
        reconstructed[dst] = tile["elevation_m"][src]
        reconstructed_climate[(slice(None),) + dst] = tile["climate"][(slice(None),) + src]
    if not np.array_equal(reconstructed, arrays["elevation_m"]) or not np.array_equal(reconstructed_climate, arrays["climate"]):
        raise ValueError("canonical assembled pixels differ from real pinned component TD")
    source = make_source(arrays["elevation_m"], climate=arrays["climate"],
        origin_m_xz=[coordinate * spacing for coordinate in native], spacing_m=spacing,
        provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
            "archive_sha256": expected_sha256, "generation_metadata": metadata,
            "historical_game_height_conditioning": False},
        boundary={"policy": "explicit", "halo_cells": 0, "upstream_contribution": "excluded_finite_experiment"})
    return source, source["metadata"]



# ------------------------------------------------------------------------
# 原 terrain_pipeline/new_world_source_mosaic.py
# ------------------------------------------------------------------------

MOSAIC_SCHEMA = "new-world-source-mosaic-v1"


PLATE = ".scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz"


def mosaic_identity(record):
    record = {k: v for k, v in record.items() if k not in ("identity", "source_paths")}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def page_name(x, z):
    return f"page_{x:+d}_{z:+d}"


def _page(path, origin, side, plate_identity):
    manifest, arrays = plate_td_product.read_plate_source(path)
    if (manifest["plate_identity"] != plate_identity or manifest["world_seed"] != WORLD_SEED or
            manifest["origin_native_xz"] != list(origin) or manifest["source_shape_zx"] != [side, side] or
            manifest["coastal"] or manifest["spacing_m"] != 30 or manifest["sea_m"] != 0):
        raise ValueError("page source or coordinates mismatch")
    return manifest, arrays


def prepare_mosaic_pages(root, source=PLATE, *, core=1024, halo=128, indices=range(-2, 2), generate=False):
    """Reuse authenticated immutable pages; generate missing pages serially."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    side = core + 2 * halo
    for z in indices:
        for x in indices:
            path = root / page_name(x, z)
            origin = [x * core - halo, z * core - halo]
            if not path.exists():
                if not generate:
                    continue
                plate_td_product.prepare_plate_source(source, path, origin, side, PhysicalGenerationConfig(),
                                         compose_coast=False, expected_identity=PLATE_IDENTITY)
            _page(path, origin, side, PLATE_IDENTITY)


def _boundary_evidence(plate, origin, shape):
    evidence = np.zeros(shape, bool)
    xs = (origin[0] + np.arange(shape[1])) * 30.
    zs = (origin[1] + np.arange(shape[0])) * 30.
    for row in (0, shape[0] - 1):
        evidence[row, :] = plate.sample(xs, np.full_like(xs, zs[row]), outside="reject")["ocean_connected"]
    for col in (0, shape[1] - 1):
        evidence[:, col] = plate.sample(np.full_like(zs, xs[col]), zs, outside="reject")["ocean_connected"]
    return evidence


def assemble(pages, output, source=PLATE, *, core=1024, halo=128, indices=range(-2, 2)):
    """Publish a derived product only after all fixed owner cores authenticate."""
    pages, output = Path(pages), Path(output)
    indices = list(indices)
    if not indices or indices != list(range(indices[0], indices[-1] + 1)) or core < 1 or halo < 1:
        raise ValueError("contiguous page grid and positive core/halo required")
    if output.exists():
        raise FileExistsError(output)
    side = core + 2 * halo
    size = core * len(indices)
    origin = [indices[0] * core, indices[0] * core]
    tmp = Path(tempfile.mkdtemp(prefix=".mosaic-stage-", dir=output.parent))
    raw = climate = None
    try:
        raw = np.lib.format.open_memmap(tmp / "raw_td.npy", mode="w+", dtype=np.float32, shape=(size, size))
        climate = np.lib.format.open_memmap(tmp / "td_climate.npy", mode="w+", dtype=np.float32, shape=(5, size, size))
        records, paths = [], []
        for iz, z in enumerate(indices):
            for ix, x in enumerate(indices):
                path = (pages / page_name(x, z)).resolve()
                parent, arrays = _page(path, [x * core - halo, z * core - halo], side, PLATE_IDENTITY)
                target = (slice(iz * core, (iz + 1) * core), slice(ix * core, (ix + 1) * core))
                raw[target] = arrays["raw_td"][halo:halo + core, halo:halo + core]
                climate[(slice(None), *target)] = arrays["td_climate"][:, halo:halo + core, halo:halo + core]
                records.append({"page_xz": [x, z], "identity": parent["identity"], "files": parent["files"], "owner_origin_native_xz": [x * core, z * core]})
                paths.append(str(path))
                del arrays
        raw.flush(); climate.flush()
        raw._mmap.close()
        climate._mmap.close()
        raw = climate = None
        files = {name: plate_td_product.digest(tmp / (name + ".npy")) for name in ("raw_td", "td_climate")}
        manifest = {"schema": MOSAIC_SCHEMA, "source_schema": "plate-td-source-v1", "world_seed": WORLD_SEED,
                    "plate_identity": PLATE_IDENTITY, "origin_native_xz": origin, "shape_zx": [size, size],
                    "spacing_m": 30, "sea_m": 0, "core": core, "halo": halo, "indices": indices,
                    "pages": records, "files": files, "source_paths": {"plate": str(Path(source).resolve()), "pages": paths},
                    "ownership": "each absolute page coordinate owns its core; halo never owns"}
        manifest["identity"] = mosaic_identity(manifest)
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        read_mosaic_product(tmp)
        os.rename(tmp, output)
    finally:
        for array in (raw, climate):
            if array is not None:
                array._mmap.close()
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_mosaic_product(output)


def read_mosaic_product(path, expected_identity=None):
    path = Path(path)
    m = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if m.get("identity") != mosaic_identity(m) or (expected_identity is not None and m["identity"] != expected_identity):
        raise ValueError("mosaic identity mismatch")
    indices, core, halo = m["indices"], m["core"], m["halo"]
    if (m.get("schema") != MOSAIC_SCHEMA or m.get("source_schema") != "plate-td-source-v1" or
            m.get("world_seed") != WORLD_SEED or m.get("plate_identity") != PLATE_IDENTITY or
            m.get("spacing_m") != 30 or m.get("sea_m") != 0 or type(core) is not int or core < 1 or
            type(halo) is not int or halo < 1 or not indices or indices != list(range(indices[0], indices[-1] + 1)) or
            m["origin_native_xz"] != [indices[0] * core] * 2 or m["shape_zx"] != [len(indices) * core] * 2 or
            set(m["files"]) != {"raw_td", "td_climate"}):
        raise ValueError("mosaic contract mismatch")
    arrays = {}
    for name in ("raw_td", "td_climate"):
        file = path / (name + ".npy")
        if plate_td_product.digest(file) != m["files"][name]:
            raise ValueError("mosaic array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
        shape = tuple(m["shape_zx"])
        if arrays[name].dtype != np.float32 or arrays[name].shape != ((5, *shape) if name == "td_climate" else shape):
            raise ValueError("mosaic array shape mismatch")
    paths = m["source_paths"]["pages"]
    plate_path = m["source_paths"]["plate"]
    if not Path(plate_path).is_absolute() or any(not Path(p).is_absolute() for p in paths):
        raise ValueError("absolute provenance paths required")
    plate = load_product(plate_path, expected_identity=m["plate_identity"])
    if plate.manifest["config"]["world_seed"] != WORLD_SEED:
        raise ValueError("plate seed mismatch")
    if len(paths) != len(indices) ** 2 or len(m["pages"]) != len(paths):
        raise ValueError("page count mismatch")
    for n, (z, x) in enumerate((z, x) for z in indices for x in indices):
        parent, page = _page(paths[n], [x * core - halo, z * core - halo], core + 2 * halo, m["plate_identity"])
        expected = {"page_xz": [x, z], "identity": parent["identity"], "files": parent["files"], "owner_origin_native_xz": [x * core, z * core]}
        if m["pages"][n] != expected:
            raise ValueError("page identity mismatch")
        iz, ix = divmod(n, len(indices))
        target = (slice(iz * core, (iz + 1) * core), slice(ix * core, (ix + 1) * core))
        for name in arrays:
            if not np.array_equal(arrays[name][(..., *target)], page[name][..., halo:halo + core, halo:halo + core]):
                raise ValueError("owner core mismatch")
        del page
    return m, arrays


def seam_report(path):
    """Measure independent overlap disagreement and adjacent owner-core steps."""
    m, arrays = read_mosaic_product(path)
    core, halo, indices = m["core"], m["halo"], m["indices"]
    results = []
    paths = m["source_paths"]["pages"]
    width = len(indices)
    for iz, z in enumerate(indices):
        for ix, x in enumerate(indices):
            a_path = paths[iz * width + ix]
            _, a = _page(a_path, [x * core - halo, z * core - halo], core + 2 * halo, m["plate_identity"])
            for dx, dz in ((1, 0), (0, 1)):
                if ix + dx >= width or iz + dz >= width:
                    continue
                _, b = _page(paths[(iz + dz) * width + ix + dx], [(x + dx) * core - halo, (z + dz) * core - halo], core + 2 * halo, m["plate_identity"])
                overlap = min(2 * halo, core + 2 * halo)
                if dx:
                    difference = a["raw_td"][:, -overlap:] - b["raw_td"][:, :overlap]
                    boundary = (ix + 1) * core
                    step = arrays["raw_td"][iz * core:(iz + 1) * core, boundary] - arrays["raw_td"][iz * core:(iz + 1) * core, boundary - 1]
                else:
                    difference = a["raw_td"][-overlap:, :] - b["raw_td"][:overlap, :]
                    boundary = (iz + 1) * core
                    step = arrays["raw_td"][boundary, ix * core:(ix + 1) * core] - arrays["raw_td"][boundary - 1, ix * core:(ix + 1) * core]
                results.append({"page_xz": [x, z], "neighbor_xz": [x + dx, z + dz],
                                "overlap_max_abs_m": float(np.max(np.abs(difference))),
                                "overlap_rms_m": float(np.sqrt(np.mean(difference.astype(np.float64) ** 2))),
                                "owner_step_max_abs_m": float(np.max(np.abs(step))),
                                "owner_step_rms_m": float(np.sqrt(np.mean(step.astype(np.float64) ** 2)))})
                del b
            del a
    return results


def classify_boundary_ocean(raw_td_m, boundary_ocean_connected):
    """Return (ocean, closed below datum, unknown) four-connected masks.

    The second argument is a bool grid of inherited macro-ocean evidence; only
    its outermost cells are used. Interior depressions cannot become anchors.
    """
    raw = np.asarray(raw_td_m)
    evidence = np.asarray(boundary_ocean_connected)
    if raw.ndim != 2 or min(raw.shape) < 2 or evidence.shape != raw.shape:
        raise ValueError("matching two-dimensional arrays required")
    if evidence.dtype != np.bool_ or not np.isfinite(raw).all():
        raise ValueError("finite terrain and boolean evidence required")
    components, _ = label(raw < 0)
    boundary = np.zeros(raw.shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    touching = np.unique(components[boundary])
    anchored = np.unique(components[boundary & evidence & (raw < 0)])
    touching = touching[touching != 0]
    anchored = anchored[anchored != 0]
    wet = raw < 0
    ocean = wet & np.isin(components, anchored)
    unknown = wet & np.isin(components, touching) & ~ocean
    closed = wet & ~ocean & ~unknown
    return ocean, closed, unknown



# ------------------------------------------------------------------------
# 原 terrain_pipeline/new_world_terrain.py
# ------------------------------------------------------------------------

POLICY = "raw-td-parent-anchor-four-neighbour-v2"


V2_PUBLISHED_ALGORITHMS = frozenset({"dfa8195c2f7267f200b54ae56bce4afb3c873709e365790de7f59a094d55cd11"})


WORLD_SEED = 20261020


NAMES = {"bed_m", "raw_td_m", "valid_mask", "ocean_mask", "closed_below_sea_mask", "unknown_mask", "climate_base"}


def _identity(record):
    record = {k: v for k, v in record.items() if k != "source_path"}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _derive(manifest, source):
    if not manifest["coastal"]:
        raise ValueError("certified coastal parent required")
    raw = source["raw_td"]
    anchor = manifest["anchor_bed_zx"]
    origin = manifest["origin_native_xz"]
    bed_origin = manifest["bed_origin_native_xz"]
    if (not isinstance(anchor, list) or len(anchor) != 2 or
            any(type(v) is not int for v in anchor)):
        raise ValueError("invalid parent anchor")
    az = anchor[0] + bed_origin[1] - origin[1]
    ax = anchor[1] + bed_origin[0] - origin[0]
    if not (0 <= az < raw.shape[0] and 0 <= ax < raw.shape[1]):
        raise ValueError("parent anchor outside raw TD")
    valid = np.ones(raw.shape, dtype=bool)
    if raw[az, ax] < 0:
        codes, _ = classify(raw, valid, [(az, ax)])
    else:
        components, _ = label(raw < 0)
        edges = np.unique(np.concatenate((components[0], components[-1], components[:, 0], components[:, -1])))
        codes = np.where(raw >= 0, 1, np.where(np.isin(components, edges), 0, 3)).astype(np.uint8)
    return {"bed_m": raw, "raw_td_m": raw, "valid_mask": valid,
            "ocean_mask": codes == 2, "closed_below_sea_mask": codes == 3,
            "unknown_mask": codes == 0, "climate_base": source["td_climate"]}


def prepare_world_terrain(source, output, *, expected_source_identity):
    if not isinstance(expected_source_identity, str) or len(expected_source_identity) != 64:
        raise ValueError("expected source identity required")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    source_file = Path(source) / "manifest.json"
    source_manifest = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}
    if source_manifest.get("schema") == "new-world-source-mosaic-v1":
        return _prepare_mosaic(source, output, expected_source_identity)
    parent, source_arrays = plate_td_product.read_plate_source(source, expected_identity=expected_source_identity)
    arrays = _derive(parent, source_arrays)
    tmp = Path(tempfile.mkdtemp(prefix=".terrain-stage-", dir=output.parent))
    try:
        hashes = {}
        for name, array in arrays.items():
            np.save(tmp / (name + ".npy"), array, allow_pickle=False)
            hashes[name] = plate_td_product.digest(tmp / (name + ".npy"))
        manifest = {"schema": "new-world-terrain-v2", "policy": POLICY,
                    "source_path": str(Path(source).resolve()), "world_seed": WORLD_SEED,
                    "algorithm_sha256": plate_td_product.digest(Path(__file__)),
                    "source_identity": expected_source_identity, "plate_identity": parent["plate_identity"],
                    "origin_native_xz": parent["origin_native_xz"], "shape_zx": parent["source_shape_zx"],
                    "spacing_m": 30, "sea_m": 0, "files": hashes,
                    "classification_support": "whole finite TD window; frozen parent anchor mapped to raw; dry anchor certifies no ocean; four-neighbour; boundary wet without anchor unknown; enclosed means below datum, not a lake",
                    "climate_support": "five stored TD channels; no 22.5 km halo; no new G4 rain-shadow acceptance",
                    "morphology": "not user accepted"}
        manifest["identity"] = _identity(manifest)
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        read_world_terrain(tmp)
        os.rename(tmp, output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_world_terrain(output)


def read_world_terrain(path, expected_identity=None):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") == "new-world-terrain-v3":
        return _read_mosaic_terrain(path, manifest, expected_identity)
    identity = manifest.get("identity")
    record = {k: v for k, v in manifest.items() if k != "identity"}
    if identity != _identity(record) or (expected_identity is not None and identity != expected_identity):
        raise ValueError("identity mismatch")
    if (manifest.get("schema") != "new-world-terrain-v2" or manifest.get("policy") != POLICY or
        manifest.get("spacing_m") != 30 or manifest.get("sea_m") != 0 or
        type(manifest.get("world_seed")) is not int or manifest["world_seed"] != WORLD_SEED or
        not published_algorithm_matches("new_world_terrain", manifest.get("algorithm_sha256"), plate_td_product.digest(Path(__file__))) or
        not isinstance(manifest.get("source_path"), str) or not Path(manifest["source_path"]).is_absolute() or
        set(manifest.get("files", {})) != NAMES):
        raise ValueError("product contract mismatch")
    origin, shape = manifest["origin_native_xz"], manifest["shape_zx"]
    if len(origin) != 2 or any(type(v) is not int for v in origin) or len(shape) != 2 or any(type(v) is not int or v <= 0 for v in shape):
        raise ValueError("invalid coordinates")
    for key in ("source_identity", "plate_identity"):
        value = manifest[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid source identity")
    parent, source = plate_td_product.read_plate_source(manifest["source_path"], expected_identity=manifest["source_identity"])
    if (parent["world_seed"] != WORLD_SEED or parent["plate_identity"] != manifest["plate_identity"] or
            parent["origin_native_xz"] != origin or parent["source_shape_zx"] != shape or
            parent["spacing_m"] != manifest["spacing_m"] or parent["sea_m"] != manifest["sea_m"]):
        raise ValueError("parent metadata mismatch")
    expected = _derive(parent, source)
    arrays = {}
    for name in NAMES:
        file = path / (name + ".npy")
        if plate_td_product.digest(file) != manifest["files"][name]:
            raise ValueError("array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
        expected_shape = (5, *shape) if name == "climate_base" else tuple(shape)
        dtype = np.bool_ if name.endswith("_mask") else np.float32
        if arrays[name].shape != expected_shape or arrays[name].dtype != dtype or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid array")
        if not np.array_equal(arrays[name], expected[name]):
            raise ValueError("parent derivation mismatch: " + name)
    bed = arrays["bed_m"]
    ocean, closed, unknown, valid = (arrays[k] for k in ("ocean_mask", "closed_below_sea_mask", "unknown_mask", "valid_mask"))
    if (not valid.all() or not np.array_equal(bed, arrays["raw_td_m"]) or
        np.any((ocean.astype(np.uint8) + closed + unknown) > 1) or
        not np.array_equal(ocean | closed | unknown, bed < 0)):
        raise ValueError("invalid classification or bed")
    return manifest, arrays


def _mosaic_derive(parent, source):
    plate = load_product(parent["source_paths"]["plate"], expected_identity=parent["plate_identity"])
    evidence = _boundary_evidence(plate, parent["origin_native_xz"], parent["shape_zx"])
    raw = source["raw_td"]
    ocean, closed, unknown = classify_boundary_ocean(raw, evidence)
    return {"bed_m": raw, "raw_td_m": raw, "valid_mask": np.ones(raw.shape, bool),
            "ocean_mask": ocean, "closed_below_sea_mask": closed, "unknown_mask": unknown,
            "climate_base": source["td_climate"]}


def _prepare_mosaic(source, output, expected_identity):
    parent, source_arrays = read_mosaic_product(source, expected_identity=expected_identity)
    arrays = _mosaic_derive(parent, source_arrays)
    tmp = Path(tempfile.mkdtemp(prefix=".terrain-stage-", dir=output.parent))
    try:
        hashes = {}
        for name, array in arrays.items():
            np.save(tmp / (name + ".npy"), array, allow_pickle=False)
            hashes[name] = plate_td_product.digest(tmp / (name + ".npy"))
        m = {"schema": "new-world-terrain-v3", "source_schema": MOSAIC_SCHEMA,
             "policy": "raw-negative-four-neighbour-macro-ocean-boundary-v1", "source_path": str(Path(source).resolve()),
             "source_identity": expected_identity, "plate_identity": parent["plate_identity"],
             "world_seed": WORLD_SEED, "origin_native_xz": parent["origin_native_xz"],
             "shape_zx": parent["shape_zx"], "spacing_m": 30, "sea_m": 0, "files": hashes,
             "classification_support": "finite boundary inherits frozen macro ocean; not global hydrodynamic certification"}
        m["identity"] = _identity(m)
        (tmp / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        _read_mosaic_terrain(tmp, m, None)
        os.rename(tmp, output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_world_terrain(output)


def _read_mosaic_terrain(path, m, expected_identity):
    if (m.get("identity") != _identity({k: v for k, v in m.items() if k != "identity"}) or
            (expected_identity is not None and m["identity"] != expected_identity) or
            m.get("schema") != "new-world-terrain-v3" or m.get("source_schema") != MOSAIC_SCHEMA or
            m.get("policy") != "raw-negative-four-neighbour-macro-ocean-boundary-v1" or
            m.get("world_seed") != WORLD_SEED or m.get("spacing_m") != 30 or m.get("sea_m") != 0 or
            set(m.get("files", {})) != NAMES):
        raise ValueError("terrain contract or identity mismatch")
    parent, source = read_mosaic_product(m["source_path"], expected_identity=m["source_identity"])
    if any(m[k] != parent[k] for k in ("plate_identity", "origin_native_xz", "shape_zx", "world_seed", "spacing_m", "sea_m")):
        raise ValueError("mosaic metadata mismatch")
    expected = _mosaic_derive(parent, source)
    arrays = {}
    for name in NAMES:
        file = path / (name + ".npy")
        if plate_td_product.digest(file) != m["files"][name]:
            raise ValueError("terrain array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
        if arrays[name].dtype != expected[name].dtype or arrays[name].shape != expected[name].shape or not np.array_equal(arrays[name], expected[name]):
            raise ValueError("terrain derivation mismatch: " + name)
    return m, arrays


def query_world_terrain(product, origin_native_xz, shape):
    """Return read-only views: origin [x,z] is in native 30 m indices, shape [z,x] in cells."""
    manifest, arrays = product
    if (len(origin_native_xz) != 2 or len(shape) != 2 or
        any(type(v) is not int for v in origin_native_xz) or
        any(type(v) is not int or v <= 0 for v in shape)):
        raise ValueError("integer origin and positive integer shape required")
    x = origin_native_xz[0] - manifest["origin_native_xz"][0]
    z = origin_native_xz[1] - manifest["origin_native_xz"][1]
    if x < 0 or z < 0 or z + shape[0] > manifest["shape_zx"][0] or x + shape[1] > manifest["shape_zx"][1]:
        raise ValueError("window outside product")
    window = {name: a[..., z:z + shape[0], x:x + shape[1]] for name, a in arrays.items()}
    for view in window.values():
        view.setflags(write=False)
    return {"identity": manifest["identity"], "source_identity": manifest["source_identity"],
            "origin_native_xz": list(origin_native_xz), "shape_zx": list(shape), "spacing_m": 30}, window



# ------------------------------------------------------------------------
# 原 terrain_pipeline/world_acceptance_terrain.py
# ------------------------------------------------------------------------

ACCEPTANCE_ALGORITHM = "single-continent-coastal-td-v1"


VIEW_BOUNDS_M = (126000.0, -32040.0, 190000.0, 31960.0)


NATIVE_SPACING_M = 30.0


CLIMATE_QUERY_SUPPORT_M = 22500.0


HALO_CELLS = 849


FILTER_SIGMA_CELLS = 24.0


FILTER_RADIUS_CELLS = 96


TD_CLIMATE_CHANNELS = ["temperature_mean_c", "temperature_std_c_times_100",
                       "precipitation_mean_mm_year", "precipitation_cv_times_100",
                       "temperature_elevation_beta_c_per_m"]


def array_sha256(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def terrain_identity(plan, paths, backend_identity, composition):
    """Content identity excludes execution timings, host memory and file paths."""
    record = {"algorithm": ACCEPTANCE_ALGORITHM, "world_seed": plan["world_seed"],
              "requested_view_bounds_m": plan["requested_view_bounds_m"],
              "origin_native_xz": plan["origin_native_xz"],
              "shape_native_zx": plan["shape_native_zx"],
              "source_origin_native_xz": plan["source_origin_native_xz"],
              "source_shape_zx": plan["source_shape_zx"],
              "native_spacing_m": plan["native_spacing_m"], "spacing_m": plan["spacing_m"],
              "backend_identity": backend_identity, "composition": composition,
              "macro_conditioning": plan["macro_conditioning"],
              "source_array_sha256": {name: source["array_sha256"] for name, source in paths.items()}}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def overlap_comparison(raw, covered, tile, request, origin_xz):
    """Compare new inference halo to prior owned cores at identical coordinates."""
    ox, oz = origin_xz
    tx, tz, size = request["native_x"], request["native_z"], request["size"]
    x0, z0 = max(ox, tx), max(oz, tz)
    x1, z1 = min(ox + raw.shape[1], tx + size), min(oz + raw.shape[0], tz + size)
    selection = np.s_[z0 - oz:z1 - oz, x0 - ox:x1 - ox]
    known = covered[selection]
    count = int(np.count_nonzero(known))
    result = {"count": count, "maximum_absolute_difference_m": 0.0,
              "rms_difference_m": 0.0, "absolute_difference_quantiles_m": [0.0, 0.0, 0.0],
              "quantiles": [.5, .9, .99]}
    if count:
        incoming = tile[z0 - tz:z1 - tz, x0 - tx:x1 - tx]
        delta = incoming[known].astype(np.float64) - raw[selection][known]
        result.update(maximum_absolute_difference_m=float(np.max(np.abs(delta))),
                      rms_difference_m=float(np.sqrt(np.mean(delta * delta))),
                      absolute_difference_quantiles_m=np.quantile(np.abs(delta), [.5, .9, .99]).tolist())
    return result


def macro_fields(x_m, z_m, seed=WORLD_SEED):
    """Sample the same 500 km continent at any absolute metre coordinates.

    A positive polar radius gives exactly one star-shaped landmass, without
    enclosed macro lakes. The eastern orogen includes saddles and a coastal
    piedmont; the acceptance window crosses this orogen and the east coast.
    """
    x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64),
                               np.asarray(z_m, dtype=np.float64))
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("finite world coordinates required")
    angle = np.arctan2(z / 0.93, x)
    radius = np.hypot(x, z / 0.93)
    phase = (int(seed) % 997) / 997.0 * 2 * np.pi
    coast_radius = (173000.0 + 11000.0 * np.sin(3 * angle + phase)
                    + 6500.0 * np.sin(7 * angle - .7)
                    + 2400.0 * np.sin(13 * angle + .4))
    inland = coast_radius - radius
    broad = field(x / 12000.0, z / 12000.0, seed, 1901, ((5, 1), (2, .35)))
    ridge_axis = 135000.0 + 6500.0 * np.sin(z / 37000.0) + 2500.0 * np.sin(z / 11000.0)
    ridge = np.exp(-((x - ridge_axis) / 15500.0) ** 2)
    saddles = .68 + .24 * np.sin(z / 14500.0 + .4) + .08 * np.cos(z / 4700.0)
    land_taper = np.clip(inland / 14000.0, 0, 1)
    interior = 180.0 + 480.0 * np.clip(inland / 100000.0, 0, 1)
    elevation = np.where(inland > 0,
        land_taper * (interior + 2100.0 * ridge * saddles + 180.0 * broad),
        -1400.0 * np.tanh(-inland / 23000.0))
    temperature = 16.0 - .0065 * np.maximum(elevation, 0) - z / 65000.0
    precipitation = np.clip(1100.0 + 500.0 * ridge + 200.0 * broad, 400, 2400)
    return {"elevation_m": elevation.astype(np.float32),
            "ocean_mask": inland <= 0, "inland_distance_m": inland.astype(np.float32),
            "temperature_c": temperature.astype(np.float32),
            "precipitation_mm_year": precipitation.astype(np.float32)}


def make_acceptance_map_factory(seed, config):
    """Use existing physical climate noise and replace the elevation condition."""
    from diffusion.geography_physical import make_physical_map_factory
    physical = make_physical_map_factory(seed, config)

    def sample_raw(x1, z1, x2, z2):
        values = physical.sample_raw(x1, z1, x2, z2)
        x = np.arange(x1, x2, dtype=np.float64)[None, :] * config.conditioning_spacing_m
        z = np.arange(z1, z2, dtype=np.float64)[:, None] * config.conditioning_spacing_m
        macro = macro_fields(x, z, seed)
        values[0] = macro["elevation_m"]
        values[1] = macro["temperature_c"]
        values[3] = macro["precipitation_mm_year"]
        return values

    def sample_full(x1, z1, x2, z2):
        import torch
        values = physical.finalize(sample_raw(x1, z1, x2, z2))
        values[0] = np.sign(values[0]) * np.sqrt(np.abs(values[0]))
        return torch.from_numpy(values)

    sample_full.sample_raw = sample_raw
    sample_full.finalize = physical.finalize
    return sample_full


def preparation_plan(bounds_m=VIEW_BOUNDS_M):
    x0, z0, x1, z1 = map(float, bounds_m)
    if not all(math.isfinite(v) for v in bounds_m) or x1 <= x0 or z1 <= z0:
        raise ValueError("finite increasing view bounds required")
    # Anchor three-cell blocks globally: coarse centres are 30 mod 90 metres.
    origin = [int(math.floor((x0 + 15) / 90)) * 3,
              int(math.floor((z0 + 15) / 90)) * 3]
    columns = int(math.ceil((x1 - (origin[0] * 30 - 15)) / 90)) * 3
    rows = int(math.ceil((z1 - (origin[1] * 30 - 15)) / 90)) * 3
    return {"algorithm": ACCEPTANCE_ALGORITHM, "world_seed": WORLD_SEED,
            "world_frame_bounds_m": [-250000, -250000, 250000, 250000],
            "requested_view_bounds_m": [x0, z0, x1, z1],
            "origin_native_xz": origin, "shape_native_zx": [rows, columns],
            "source_origin_native_xz": [v - HALO_CELLS for v in origin],
            "source_shape_zx": [rows + 2 * HALO_CELLS, columns + 2 * HALO_CELLS],
            "spacing_m": 90.0, "native_spacing_m": 30.0, "halo_native_cells": HALO_CELLS,
            "source_support": {"climate_orographic_scale_m": 15000.0,
                "climate_max_axis_query_offset_m": CLIMATE_QUERY_SUPPORT_M,
                "interpolation_support_m": 30.0,
                "composition_filter_support_m": FILTER_RADIUS_CELLS * 30.0,
                "total_source_halo_m": HALO_CELLS * 30.0,
                "composition_valid_margin_native_cells": FILTER_RADIUS_CELLS,
                "inference_tile_halo_native_cells": 96},
            "origin_xz_m": [origin[0] * 30 + 30, origin[1] * 30 + 30],
            "output_cell_bounds_m": [origin[0] * 30 - 15, origin[1] * 30 - 15,
                                     origin[0] * 30 - 15 + columns * 30,
                                     origin[1] * 30 - 15 + rows * 30],
            "coordinate_convention": "x east, z south; arrays [z,x]; origins are cell centres",
            "macro_conditioning": {
                "formula": "polar star-shaped continent; inland=coast_radius-hypot(x,z/0.93); coastal taper times uplift plus eastern Gaussian orogen",
                "coast_radius_m": 173000, "polar_radius_harmonics_m": [11000, 6500, 2400],
                "polar_radius_frequencies": [3, 7, 13], "north_south_aspect": .93,
                "coastal_land_taper_m": 14000, "ocean_tanh_depth_m": 1400,
                "ocean_tanh_scale_m": 23000, "orogen_axis_x_m": 135000,
                "orogen_width_m": 15500, "orogen_relief_m": 2100,
                "noise": "existing diffusion.geographic_noise.field, purpose1901, scale12000m",
                "condition_channels": "elevation, mean temperature and precipitation replaced; physical temperature variability and precipitation CV retained",
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "lake_status": "no macro lakes; hydrological lakes are not yet modelled",
            "gpu_policy": {"allocator_cap_gib": 4, "max_request_side": 1337,
                           "processes": 1, "inference": "explicit --generate only"}}


def area_mean_3(array):
    """Conservative native30m to90m cell area average, including extra channels."""
    values = np.asarray(array)
    rows, columns = values.shape[-2:]
    if rows % 3 or columns % 3:
        raise ValueError("native shape must be divisible by three")
    return values.reshape(*values.shape[:-2], rows // 3, 3, columns // 3, 3).mean(
        axis=(-3, -1), dtype=np.float64).astype(np.float32)


def compose_native(raw, plan):
    """Keep TD high frequencies and 65% TD low frequencies, constrain shore sign."""
    raw = np.asarray(raw, dtype=np.float32)
    if list(raw.shape) != plan["source_shape_zx"] or not np.isfinite(raw).all():
        raise ValueError("finite TD source matching the prepared shape required")
    x0, z0 = plan["source_origin_native_xz"]
    x = (x0 + np.arange(raw.shape[1]))[None, :] * 30.0
    z = (z0 + np.arange(raw.shape[0]))[:, None] * 30.0
    fields = macro_fields(x, z)
    macro = fields["elevation_m"]
    low = gaussian_filter(raw, sigma=FILTER_SIGMA_CELLS,
                          radius=FILTER_RADIUS_CELLS, mode="nearest")
    # Subtract the same linear low-pass of the macro, not a window statistic.
    macro_low = gaussian_filter(macro, sigma=FILTER_SIGMA_CELLS,
                                radius=FILTER_RADIUS_CELLS, mode="nearest")
    detail = raw - low
    correction = detail + .65 * (low - macro_low)
    limit = .85 * np.abs(macro)
    composed = macro + np.clip(correction, -limit, limit)
    return composed.astype(np.float32), fields


def tile_requests(shape_zx, origin_xz, overlap=96):
    """Absolute anchored cores: requested extent and order never change TD calls."""
    rows, columns = shape_zx
    step = 1024
    ox, oz = origin_xz
    for core_z in range((oz // step) * step, oz + rows, step):
        for core_x in range((ox // step) * step, ox + columns, step):
            x0, z0 = max(ox, core_x), max(oz, core_z)
            x1, z1 = min(ox + columns, core_x + step), min(oz + rows, core_z + step)
            yield {"row": z0 - oz, "column": x0 - ox,
                   "rows": z1 - z0, "columns": x1 - x0,
                   "tile_row": z0 - core_z + overlap, "tile_column": x0 - core_x + overlap,
                   "native_x": core_x - overlap, "native_z": core_z - overlap,
                   "size": step + 2 * overlap}


def _backend(config):
    from diffusion.physical_backend import PhysicalTerrainDiffusionBackend
    from diffusion.paths import ROOT, inside

    class AcceptanceBackend(PhysicalTerrainDiffusionBackend):
        def __init__(self):
            super().__init__(config)
            self.metadata = dict(self.metadata, algorithm=ACCEPTANCE_ALGORITHM,
                adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                conditioning="absolute-coordinate single continent, independent fresh TD")
            self.identity = hashlib.sha256(json.dumps(self.metadata, sort_keys=True).encode()).hexdigest()

        def load(self):
            if self.pipeline is not None:
                return
            model_config = json.loads((inside(config.model_dir) / "config.json").read_text(encoding="utf-8"))
            native = model_config["native_resolution"]
            if (native != config.native_resolution_m or
                    native * model_config["latent_compression"] * 32 != config.conditioning_spacing_m):
                raise ValueError("physical checkpoint native/coarse metre grid mismatch")
            upstream = json.loads((ROOT / "runtime/upstream.json").read_text(encoding="utf-8"))
            sys.path.insert(0, str(inside(upstream["source"])))
            import torch
            from terrain_diffusion.inference.world_pipeline import WorldPipeline
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA required for genuine TD; no fallback")
            torch.cuda.set_per_process_memory_fraction(4 * 2**30 / torch.cuda.get_device_properties(0).total_memory)
            torch.set_num_threads(2)

            class AcceptancePipeline(WorldPipeline):
                def _init_conditioning(self):
                    self.synthetic_map_factory = make_acceptance_map_factory(int(self.seed), config)

            pipeline = AcceptancePipeline.from_pretrained(str(inside(config.model_dir)), seed=0,
                latents_batch_size=1, torch_compile=False,
                dtype=config.dtype if config.dtype == "fp16" else None,
                caching_strategy="direct", cache_limit=64 * 1024 * 1024,
                cond_snr=list(config.cond_snr))
            try:
                pipeline.to("cuda")
                pipeline.bind()
            except BaseException:
                pipeline.close()
                raise
            self.pipeline = pipeline

    return AcceptanceBackend()


def generate_product(output, plan=None, backend=None):
    """Generate genuine native TD in one process and persist source provenance."""
    from diffusion.physical_config import PhysicalGenerationConfig
    import psutil

    plan = preparation_plan() if plan is None else plan
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    backend = _backend(PhysicalGenerationConfig()) if backend is None else backend
    rows, columns = plan["source_shape_zx"]
    halo = plan["halo_native_cells"]
    nr_core, nc_core = plan["shape_native_zx"]
    raw = np.zeros((rows, columns), dtype=np.float32)
    climate = np.zeros((5, nr_core, nc_core), dtype=np.float32)
    covered = np.zeros((rows, columns), dtype=bool)
    records = []
    started = time.perf_counter()
    rss_peak = psutil.Process().memory_info().rss
    try:
        for request in tile_requests((rows, columns), plan["source_origin_native_xz"]):
            print(json.dumps({"stage": "td_request", **request}), flush=True)
            tile, tile_climate, record = backend.generate(WORLD_SEED, request["native_x"],
                                                        request["native_z"], request["size"])
            overlap = overlap_comparison(raw, covered, tile, request, plan["source_origin_native_xz"])
            nr, nc = request["rows"], request["columns"]
            r, c = request["row"], request["column"]
            tr, tc = request["tile_row"], request["tile_column"]
            selection = np.s_[r:r + nr, c:c + nc]
            raw[selection] = tile[tr:tr + nr, tc:tc + nc]
            covered[selection] = True
            cr0, cc0 = max(r, halo), max(c, halo)
            cr1, cc1 = min(r + nr, halo + nr_core), min(c + nc, halo + nc_core)
            if cr1 > cr0 and cc1 > cc0:
                climate[:, cr0 - halo:cr1 - halo, cc0 - halo:cc1 - halo] = tile_climate[
                    :, tr + cr0 - r:tr + cr1 - r, tc + cc0 - c:tc + cc1 - c]
            rss_peak = max(rss_peak, psutil.Process().memory_info().rss)
            records.append({"request": request, "source_metadata": record,
                            "tile_array_sha256": array_sha256(tile), "raw_overlap_comparison": overlap})
    finally:
        backend.close()
    raw = raw.astype(np.float32)
    climate = climate.astype(np.float32)
    composed, fields = compose_native(raw, plan)
    rss_peak = max(rss_peak, psutil.Process().memory_info().rss)
    paths = {}
    for name, array in (("raw_td_30m", raw), ("composed_30m", composed),
                        ("macro_30m", fields["elevation_m"])):
        path = destination / (name + ".npy")
        np.save(path, array, allow_pickle=False)
        paths[name] = {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "array_sha256": array_sha256(array)}
    halo = plan["halo_native_cells"]
    nr, nc = plan["shape_native_zx"]
    crop = np.s_[halo:halo + nr, halo:halo + nc]
    source_metadata = {**plan, "native_source_origin_xz_m": [v * 30 for v in plan["source_origin_native_xz"]],
        "native_source_paths": paths, "tiles": records,
        "climate_base_channels": list(TD_CLIMATE_CHANNELS),
        "runtime_seconds": time.perf_counter() - started, "sampled_peak_rss_bytes": rss_peak,
        "composition": {"detail_gain": 1.0, "low_frequency_td_gain": .65,
            "sigma_native_cells": FILTER_SIGMA_CELLS, "filter_radius_native_cells": FILTER_RADIUS_CELLS,
            "formula": "macro + clip(raw-lowpass(raw)+0.65*(lowpass(raw)-lowpass(macro)), +/-0.85*abs(macro))",
            "coastline": "declared macro sign constrained derivative; not raw TD coastline",
            "tile_assembly": "absolute 1024-cell cores with 96-cell inference halo; trusted core crop, no blending"}}
    source_metadata["terrain_identity"] = terrain_identity(plan, paths, backend.identity,
                                                           source_metadata["composition"])
    source_metadata["raw_overlap_summary"] = {
        "comparison_count": sum(r["raw_overlap_comparison"]["count"] for r in records),
        "maximum_absolute_difference_m": max(r["raw_overlap_comparison"]["maximum_absolute_difference_m"] for r in records),
        "semantics": "new differently located request halo versus already owned absolute core; diagnostic only, cores never overwritten"}
    elevation90 = area_mean_3(composed[crop])
    np.savez_compressed(destination / "terrain90.npz", elevation_m=elevation90,
        raw_td_m=area_mean_3(raw[crop]), macro_elevation_m=area_mean_3(fields["elevation_m"][crop]),
        ocean_mask=elevation90 < 0,
        ocean_area_fraction=area_mean_3(fields["ocean_mask"][crop].astype(np.float32)),
        climate_base=area_mean_3(climate),
        metadata_json=np.asarray(json.dumps(source_metadata, sort_keys=True)))
    (destination / "terrain_metadata.json").write_text(json.dumps(source_metadata, indent=2), encoding="utf-8")
    return source_metadata


def correct_climate_metadata_export(original_directory, corrected_directory):
    """Export unchanged numerical data with the actual TD climate channel names."""
    source = Path(original_directory).resolve()
    destination = Path(corrected_directory).resolve()
    if source == destination:
        raise ValueError("metadata correction requires a separate derived output directory")
    metadata_path = source / "terrain_metadata.json"
    product_path = source / "terrain90.npz"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    upstream = metadata["tiles"][0]["source_metadata"]["upstream"]
    from diffusion.paths import inside
    upstream_path = inside(upstream["source"]) / "terrain_diffusion/inference/world_pipeline.py"
    metadata["metadata_correction"] = {
        "schema": "td-climate-channel-names-correction-v1",
        "reason": "WorldPipeline._compute_climate returns temperature, temperature variability, precipitation, precipitation CV and lapse beta; conditioning elevation is not an output climate channel",
        "original_metadata_path": str(metadata_path),
        "original_metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        "original_product_path": str(product_path),
        "original_product_sha256": hashlib.sha256(product_path.read_bytes()).hexdigest(),
        "original_climate_base_channels": metadata["climate_base_channels"],
        "upstream_source_path": str(upstream_path),
        "upstream_source_sha256": hashlib.sha256(upstream_path.read_bytes()).hexdigest(),
        "upstream_revision": upstream["revision"],
        "upstream_definition": "WorldPipeline._compute_climate lines1413-1463: torch.stack([temp_realistic, coarse_up[3], coarse_up[4], coarse_up[5], beta_up[0]])",
        "correction_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "numerical_arrays": "unchanged; metadata-only derived export; terrain_identity retained",
        "gpu_generation": "not repeated"}
    metadata["climate_base_channels"] = list(TD_CLIMATE_CHANNELS)
    with np.load(product_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files if name != "metadata_json"}
    destination.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(destination / "terrain90.npz", **arrays,
                        metadata_json=np.asarray(json.dumps(metadata, sort_keys=True)))
    (destination / "terrain_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with np.load(destination / "terrain90.npz", allow_pickle=False) as corrected:
        if any(not np.array_equal(array, corrected[name]) for name, array in arrays.items()):
            raise RuntimeError("derived climate metadata export changed numerical data")
    return metadata


def write_preview(output, plan=None):
    """CPU-only preview, explicitly labelled macro rather than TD acceptance."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    plan = preparation_plan() if plan is None else plan
    x0, z0, x1, z1 = plan["requested_view_bounds_m"]
    x = np.linspace(x0, x1, 512)[None, :]
    z = np.linspace(z0, z1, 512)[:, None]
    fields = macro_fields(x, z)
    np.savez_compressed(destination / "macro_preview.npz", **fields,
                        metadata_json=np.asarray(json.dumps(plan)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    whole = np.linspace(-250000, 250000, 512)
    for axis, image, extent in ((axes[0], macro_fields(whole[None, :], whole[:, None])["elevation_m"],
                                [-250, 250, 250, -250]),
                               (axes[1], fields["elevation_m"], [x0 / 1000, x1 / 1000, z1 / 1000, z0 / 1000])):
        axis.imshow(image, cmap="terrain", vmin=-1400, vmax=2400, extent=extent)
        axis.set_xlabel("East (km)")
        axis.set_ylabel("South (km)")
    from matplotlib.patches import Rectangle
    axes[0].add_patch(Rectangle((x0 / 1000, z0 / 1000), (x1 - x0) / 1000,
                                (z1 - z0) / 1000, fill=False, edgecolor="red"))
    fig.suptitle("CPU macro plan only - fresh TD generation pending")
    fig.tight_layout()
    fig.savefig(destination / "macro_preview.png", dpi=140)
    plt.close(fig)
    (destination / "preparation_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan



# ------------------------------------------------------------------------
# 原 terrain_pipeline/world_terrain_composition.py
# ------------------------------------------------------------------------

COMPOSITION_SCHEMA = "world-terrain-composition-v1"


SPACING_M = 30.0


def make_ocean_plan(spec, pixels=512, min_ocean_area_fraction=0.05):
    """Classify whole-frame macro water components on a fixed diagnostic grid."""
    if not isinstance(spec, LayoutSpec) or spec.mode != "finite" or spec.preset == "lakes":
        raise ValueError("ocean planning requires a finite ocean-preset layout")
    if type(pixels) is not int or not 2 <= pixels <= 2048:
        raise ValueError("pixels must be an integer in [2, 2048]")
    if (isinstance(min_ocean_area_fraction, bool) or
            not isinstance(min_ocean_area_fraction, (int, float)) or
            not 0 <= min_ocean_area_fraction <= 1):
        raise ValueError("min_ocean_area_fraction must be in [0, 1]")
    ox, oz = spec.frame_origin_m
    step = spec.frame_side_m / pixels
    axis = (np.arange(pixels, dtype=np.float64) + 0.5) * step
    x, z = np.meshgrid(ox + axis, oz + axis)
    components, count = label(layout_field(spec, x, z) <= 0.0)
    if count == 0:
        raise ValueError("macro planning grid contains no water component")
    sizes = np.bincount(components.ravel(), minlength=count + 1)
    sizes[0] = 0
    selected = sizes >= min_ocean_area_fraction * pixels * pixels
    selected[0] = False
    selected[int(np.argmax(sizes))] = True
    nearest_water = distance_transform_edt(components == 0, return_distances=False,
                                           return_indices=True)
    mask = selected[components[tuple(nearest_water)]]
    record = {"schema": "world-ocean-plan-v2", "layout_identity": spec.identity(),
              "origin_m": [ox, oz], "side_m": spec.frame_side_m,
              "pixels": pixels, "spacing_m": step,
              "min_ocean_area_fraction": float(min_ocean_area_fraction),
              "selection": "largest plus components at least the declared fraction of the whole frame",
              "ownership": "nearest classified water grid centre; exact field determines shoreline",
              "connectivity": 4, "water_components": int(count),
              "ocean_components": int(np.count_nonzero(selected)),
              "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
              "limitation": "macro sampled topology and nearest ownership; sub-grid water bodies and 30m connectivity are not certified"}
    record["identity"] = hashlib.sha256(json.dumps(record, sort_keys=True,
                                                    separators=(",", ":")).encode()).hexdigest()
    return {"ocean_cells": mask, "metadata": record}


def sample_ocean_mask(plan, spec, x_m, z_m):
    """Use nearest sampled water ownership and the exact field's water side."""
    record = plan["metadata"]
    if spec.identity() != record["layout_identity"]:
        raise ValueError("ocean plan does not match layout identity")
    x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64),
                               np.asarray(z_m, dtype=np.float64))
    ox, oz = record["origin_m"]
    side = record["side_m"]
    if (not np.isfinite(x).all() or not np.isfinite(z).all() or
            np.any(x < ox) or np.any(z < oz) or np.any(x >= ox + side) or np.any(z >= oz + side)):
        raise ValueError("ocean query lies outside the finite world")
    col = np.floor((x - ox) / record["spacing_m"]).astype(np.int64)
    row = np.floor((z - oz) / record["spacing_m"]).astype(np.int64)
    return plan["ocean_cells"][row, col] & (layout_field(spec, x, z) <= 0.0)


def _compose_fields(spec, source, residual, x, z, ocean_mask):
    signal = layout_field(spec, x, z)
    if spec.preset == "lakes":
        if ocean_mask is not None:
            raise ValueError("lakes base does not accept a water mask")
        macro = 400.0 - 700.0 * np.tanh(signal / 0.25)
        correction = residual
        ocean = None
    else:
        if ocean_mask is None:
            raise ValueError("ocean presets require an externally determined ocean mask")
        ocean = np.asarray(ocean_mask)
        if ocean.dtype != np.bool_ or ocean.shape != source.shape:
            raise ValueError("ocean_mask must be a boolean array matching the source")
        if np.any(ocean & (signal > 0)):
            raise ValueError("ocean mask includes macro land")
        macro = np.where(signal >= 0.0, 700.0, 600.0) * np.tanh(signal / 0.08)
        limit = 0.8 * np.abs(macro)
        correction = np.clip(residual, -limit, limit)
    return macro, correction, macro + correction, ocean


def compose_source(spec, td_elevation_zx, origin_native_xz, *, source_record,
                   ocean_mask=None, sigma_cells=6.0):
    """Compose one complete, fixed TD source; arrays use [z, x] native cells.

    ``source_record`` identifies the original page with ``sha256`` and
    ``world_seed``. For ocean presets, ``ocean_mask`` is an externally determined
    ocean classification, not a test of elevation; it must only occupy the
    macro field's water side. Lakes mode has no water classification here.
    """
    if not isinstance(spec, LayoutSpec):
        raise ValueError("spec must be a LayoutSpec")
    source = np.asarray(td_elevation_zx, dtype=np.float64)
    if source.ndim != 2 or not np.isfinite(source).all():
        raise ValueError("TD elevation must be a finite 2D array")
    if (not isinstance(origin_native_xz, (tuple, list)) or len(origin_native_xz) != 2
            or any(type(v) is not int for v in origin_native_xz)):
        raise ValueError("origin_native_xz must contain two native integer indices")
    if not isinstance(source_record, dict) or source_record.get("world_seed") != spec.world_seed:
        raise ValueError("source world_seed must match the layout")
    digest = source_record.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("source_record must contain a lowercase SHA256")
    if isinstance(sigma_cells, bool) or not isinstance(sigma_cells, (int, float)) or not math.isfinite(sigma_cells) or sigma_cells <= 0:
        raise ValueError("sigma_cells must be finite and positive")
    halo = int(math.ceil(3.0 * sigma_cells))
    if min(source.shape) <= 2 * halo:
        raise ValueError("source page does not contain a filter interior")

    rows, columns = source.shape
    x = (origin_native_xz[0] + np.arange(columns, dtype=np.float64))[None, :] * SPACING_M
    z = (origin_native_xz[1] + np.arange(rows, dtype=np.float64))[:, None] * SPACING_M
    x, z = np.broadcast_arrays(x, z)
    if spec.mode == "finite":
        ox, oz = spec.frame_origin_m
        if not (x.min() >= ox and z.min() >= oz and x.max() < ox + spec.frame_side_m
                and z.max() < oz + spec.frame_side_m):
            raise ValueError("source page extends outside the finite world")
    smooth = gaussian_filter(source, sigma=float(sigma_cells), radius=halo, mode="nearest")
    residual = source - smooth
    macro, correction, composed, ocean = _compose_fields(spec, source, residual, x, z, ocean_mask)
    valid = np.zeros(source.shape, dtype=bool)
    valid[halo:-halo, halo:-halo] = True
    parameters = {"schema": COMPOSITION_SCHEMA, "layout_identity": spec.identity(),
                  "world_seed": spec.world_seed, "origin_native_xz": list(origin_native_xz),
                  "shape_zx": list(source.shape), "spacing_m": SPACING_M,
                  "source_record": dict(source_record), "sigma_cells": float(sigma_cells),
                  "source_array_sha256": hashlib.sha256(np.ascontiguousarray(source).tobytes()).hexdigest(),
                  "ocean_mask_sha256": (hashlib.sha256(np.ascontiguousarray(ocean).tobytes()).hexdigest()
                                        if ocean is not None else None),
                  "filter_radius_cells": halo, "filter": "gaussian_fixed_source",
                  "macro": "continuous_layout_field", "sea_level_m": 0.0 if ocean is not None else None,
                  "ocean_classification": "externally_supplied" if ocean is not None else "not_applicable",
                  "lake_status": "not_modelled", "cross_source_overlap": "not_certified"}
    parameters["identity"] = hashlib.sha256(json.dumps(parameters, sort_keys=True,
                                                         separators=(",", ":"),
                                                         allow_nan=False).encode()).hexdigest()
    return {"td_elevation_m": source.copy(), "macro_elevation_m": macro,
            "td_residual_m": residual, "applied_residual_m": correction,
            "composed_elevation_m": composed, "valid_mask": valid,
            "ocean_mask": None if ocean is None else ocean.copy(), "metadata": parameters}


def crop_composition(product, origin_native_xz, shape_zx):
    """Crop the precomputed source interior; never recompute filtering."""
    origin = product["metadata"]["origin_native_xz"]
    if (len(origin_native_xz) != 2 or len(shape_zx) != 2 or
            any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
            any(v <= 0 for v in shape_zx)):
        raise ValueError("crop origin and shape require integer pairs")
    x0 = origin_native_xz[0] - origin[0]
    z0 = origin_native_xz[1] - origin[1]
    rows, columns = shape_zx
    mask = product["valid_mask"]
    if (x0 < 0 or z0 < 0 or x0 + columns > mask.shape[1] or z0 + rows > mask.shape[0]
            or not mask[z0:z0 + rows, x0:x0 + columns].all()):
        raise ValueError("crop is outside the source's valid filter interior")
    return {name: (None if array is None else array[z0:z0 + rows, x0:x0 + columns].copy())
            for name, array in product.items() if name != "metadata"} | {
                "metadata": {**product["metadata"], "crop_origin_native_xz": list(origin_native_xz),
                             "crop_shape_zx": list(shape_zx)}}



# ------------------------------------------------------------------------
# 原 terrain_pipeline/world_terrain_disk_store.py
# ------------------------------------------------------------------------

TILE_SIDE = 512


REVISION = "disk-irregular-network-water-v2"


def tiles(origin, shape):
    for z in range(0, shape[0], TILE_SIDE):
        for x in range(0, shape[1], TILE_SIDE):
            yield [origin[0] + x, origin[1] + z], [min(TILE_SIDE, shape[0] - z), min(TILE_SIDE, shape[1] - x)]


def open_disk_registry(path, spec, source_family, forcing, sigma):
    world = {"layout": spec.parameters(), "layout_identity": spec.identity(), "source_family": source_family,
             "forcing": forcing, "sigma_cells": sigma, "revision": REVISION}
    world_id = identity({}, world)
    registry_path = Path(path) / "registry.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry.get("world_identity") != world_id or registry.get("world") != world:
            raise ValueError("world or algorithm identity mismatch; use a new store directory")
        return registry
    return {"schema": "world-terrain-disk-store-v1", "world": world, "world_identity": world_id,
            "pages": [], "components": [], "prepared_cells": 0, "world_cells": 409600 ** 2}


def plan_disk_region(registry, origin, shape):
    bounds = _bounds(origin, shape)
    selected = []
    while True:
        added = [c for c in registry["components"] if c not in selected and _touch(bounds, c["bounds"])]
        if not added:
            break
        for c in added:
            selected.append(c)
            bounds = _union(bounds, c["bounds"])
    hit = next((c for c in selected if c["bounds"][0] <= origin[0] and c["bounds"][1] <= origin[1]
                and c["bounds"][2] >= origin[0] + shape[1] and c["bounds"][3] >= origin[1] + shape[0]), None)
    return {"bounds": bounds, "origin_native_xz": bounds[:2],
            "shape_zx": [bounds[3] - bounds[1], bounds[2] - bounds[0]], "selected": selected, "hit": hit}


def _sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_disk_region(path, registry, request, pages, spec, *, compose, solve, disk_budget_gib=8.):
    if request["hit"]:
        root, manifest = read_disk_manifest(path, request["hit"], registry["world_identity"])
        for tile in manifest["composition_tiles"] + manifest["water_tiles"]:
            if _sha(root / tile["file"]) != tile["sha256"]:
                raise ValueError("disk region tile identity mismatch")
        return request["hit"]
    root = Path(path)
    versions = root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    origin, shape = request["origin_native_xz"], request["shape_zx"]
    if not np.isfinite(disk_budget_gib) or disk_budget_gib <= 0:
        raise ValueError("disk budget must be positive and finite")
    estimated = shape[0] * shape[1] * 512
    if estimated > disk_budget_gib * 1024 ** 3 or estimated > shutil.disk_usage(versions).free:
        raise ValueError("estimated disk requirement exceeds budget or available space")
    world = registry["world"]
    with tempfile.TemporaryDirectory(prefix=".disk-region-", dir=versions) as temporary:
        staging = Path(temporary) / "product"
        staging.mkdir()
        height = np.lib.format.open_memmap(staging / "height.npy", mode="w+", dtype="float64", shape=tuple(shape))
        ocean = None
        composition_tiles = []
        try:
            ocean = np.lib.format.open_memmap(staging / "ocean.npy", mode="w+", dtype="bool", shape=tuple(shape))
            for tile_origin, tile_shape in tiles(origin, shape):
                product = compose(spec, pages, tile_origin, tile_shape, sigma_cells=world["sigma_cells"],
                                  source_family=world["source_family"])
                z, x = tile_origin[1] - origin[1], tile_origin[0] - origin[0]
                sl = np.s_[z:z + tile_shape[0], x:x + tile_shape[1]]
                height[sl] = product["composed_elevation_m"]
                ocean[sl] = product["ocean_mask"] if product["ocean_mask"] is not None else False
                name = "composition-%d-%d.npz" % (tile_origin[0], tile_origin[1])
                np.savez_compressed(staging / name, **{k: v for k, v in product.items() if k != "metadata" and v is not None})
                composition_tiles.append({"origin_native_xz": tile_origin, "shape_zx": tile_shape,
                                          "file": name, "sha256": _sha(staging / name), "metadata": product["metadata"]})
            height.flush()
            ocean.flush()
        finally:
            height._mmap.close()
            if ocean is not None:
                ocean._mmap.close()
        water = solve(staging / "height.npy", staging / "ocean.npy", staging / "water",
                      origin_native_xz=origin, world_seed=20261020, **world["forcing"])
        fields = {}
        try:
            for name, file in water["fields"].items():
                fields[name] = np.load(staging / "water" / file, mmap_mode="r", allow_pickle=False)
            if not fields:
                raise ValueError("water fields are empty")
            if any(field.shape != tuple(shape) for field in fields.values()):
                raise ValueError("water field shape mismatch")
            water_tiles = []
            for tile_origin, tile_shape in tiles(origin, shape):
                z, x = tile_origin[1] - origin[1], tile_origin[0] - origin[0]
                sl = np.s_[z:z + tile_shape[0], x:x + tile_shape[1]]
                name = "water-%d-%d.npz" % tuple(tile_origin)
                np.savez_compressed(staging / name, **{key: value[sl] for key, value in fields.items()})
                water_tiles.append({"origin_native_xz": tile_origin, "shape_zx": tile_shape,
                                    "file": name, "sha256": _sha(staging / name)})
        finally:
            for field in fields.values():
                field._mmap.close()
        manifest = {"schema": "world-terrain-disk-region-v1", "world_identity": registry["world_identity"],
                    "origin_native_xz": origin, "shape_zx": shape, "composition_tiles": composition_tiles,
                    "water_tiles": water_tiles, "water_metadata": water["metadata"]}
        if water.get("network") is not None:
            network = dict(water["network"])
            network["file"] = "water/" + network["file"]
            verify_network(staging, network)
            manifest["network"] = network
        manifest["identity_sha256"] = identity({}, manifest)
        (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
        version = uuid.uuid4().hex
        staging.rename(versions / version)
    component = {"version": version, "bounds": request["bounds"], "identity_sha256": manifest["identity_sha256"]}
    updated = dict(registry)
    updated["components"] = [c for c in registry["components"] if c not in request["selected"]] + [component]
    updated["pages"] = pages
    updated["prepared_cells"] = sum((c["bounds"][2] - c["bounds"][0]) * (c["bounds"][3] - c["bounds"][1]) for c in updated["components"])
    _atomic_json(root / "registry.json", updated)
    registry.update(updated)
    return component


def read_disk_manifest(path, component, world_identity):
    root = Path(path) / "versions" / component["version"]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest.pop("identity_sha256")
    if manifest["world_identity"] != world_identity or expected != component["identity_sha256"] or identity({}, manifest) != expected:
        raise ValueError("disk region identity mismatch")
    if manifest.get("network") is not None:
        verify_network(root, manifest["network"])
    return root, manifest



# ------------------------------------------------------------------------
# 原 terrain_pipeline/world_terrain_mosaic.py
# ------------------------------------------------------------------------

def _read_support(spec, page_records, hx, hz, hrows, hcols, source_family):
    field = np.empty((hrows, hcols), dtype=np.float64)
    resolved = np.zeros((hrows, hcols), dtype=bool)
    records = ([] if isinstance(page_records, (list, tuple)) and not page_records else
               sorted(_page_records(page_records), key=lambda item: item["path"]))
    sources = []
    known = set()
    generations = set()
    for record in records:
        page, metadata, origin = _read_page(record, seed=spec.world_seed)
        embedded = metadata.get("conditioning_identity") or metadata.get("source_family")
        generation = metadata.get("physical_generation_identity")
        if generation is not None:
            generations.add(generation)
            if len(generations) > 1:
                raise ValueError("physical generation identities differ")
        known.add(embedded is not None)
        if embedded is not None and embedded != source_family:
            raise ValueError("source family does not match page metadata")
        px, pz = origin
        edge = BORDER_BAND_CELLS
        sources.append({**record, "physical_generation_identity": generation,
                        "trusted_bounds_native_xz": [px + edge, pz + edge,
                        px + page.shape[1] - edge, pz + page.shape[0] - edge]})
        left, top = max(hx, px + edge), max(hz, pz + edge)
        right = min(hx + hcols, px + page.shape[1] - edge)
        bottom = min(hz + hrows, pz + page.shape[0] - edge)
        if left >= right or top >= bottom:
            continue
        target = np.s_[top - hz:bottom - hz, left - hx:right - hx]
        values = page[top - pz:bottom - pz, left - px:right - px]
        existing = resolved[target]
        if existing.any() and not np.array_equal(field[target][existing], values[existing]):
            raise ValueError("trusted TD page overlap disagrees")
        field[target][~existing] = values[~existing]
        resolved[target] = True
    return field, resolved, records, sources, known


def _family_verification(known):
    if known == {True}:
        return "embedded"
    if known == {True, False}:
        return "mixed_embedded_and_caller_declared"
    return "caller_declared"


def inspect_window_support(spec, page_records, origin_native_xz, shape_zx, *,
                           sigma_cells=6.0, max_cells=1048576, source_family):
    """Read pinned pages and report exact missing target-plus-halo cells, without filtering."""
    if not isinstance(spec, LayoutSpec) or not isinstance(source_family, str) or not source_family.strip():
        raise ValueError("layout and explicit source family required")
    if (not isinstance(origin_native_xz, (tuple, list)) or len(origin_native_xz) != 2 or
            not isinstance(shape_zx, (tuple, list)) or len(shape_zx) != 2 or
            any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
            any(v <= 0 for v in shape_zx)):
        raise ValueError("origin and shape must be integer pairs with positive shape")
    if (isinstance(sigma_cells, bool) or not isinstance(sigma_cells, (int, float)) or
            not math.isfinite(sigma_cells) or sigma_cells <= 0):
        raise ValueError("sigma_cells must be finite and positive")
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError("max_cells must be a positive integer")
    halo = int(math.ceil(3 * sigma_cells))
    rows, cols = shape_zx
    if spec.mode == "finite":
        fx, fz = spec.frame_origin_m
        x0, z0 = origin_native_xz
        if not (fx <= x0 * SPACING_M and fz <= z0 * SPACING_M and
                (x0 + cols - 1) * SPACING_M < fx + spec.frame_side_m and
                (z0 + rows - 1) * SPACING_M < fz + spec.frame_side_m):
            raise ValueError("target lies outside finite world")
    hrows, hcols = rows + 2 * halo, cols + 2 * halo
    if hrows * hcols > max_cells:
        raise ValueError("target and filter halo exceed max_cells")
    hx, hz = origin_native_xz[0] - halo, origin_native_xz[1] - halo
    _, resolved, records, sources, known = _read_support(
        spec, page_records, hx, hz, hrows, hcols, source_family)
    return {"support_origin_native_xz": [hx, hz], "support_shape_zx": [hrows, hcols],
            "missing_mask": ~resolved, "missing_cells": int(np.count_nonzero(~resolved)),
            "source_records": records, "sources": sources, "source_family": source_family,
            "source_family_verification": _family_verification(known),
            "filter_radius_cells": halo, "source_border_cells": BORDER_BAND_CELLS}


def compose_window(spec, page_records, origin_native_xz, shape_zx, *, sigma_cells=6.0,
                   max_cells=1048576, source_family):
    """Compose a target window with fully supplied, verified TD filter support.

    ``source_family`` is an explicit source-family declaration. When pages carry
    a conditioning identity it must match. Older pages without one rely on the caller's
    declaration, which is recorded as such rather than verified from the file.
    """
    if not isinstance(spec, LayoutSpec):
        raise ValueError("spec must be a LayoutSpec")
    if not isinstance(source_family, str) or not source_family.strip():
        raise ValueError("source_family must be explicitly declared")
    if (not isinstance(origin_native_xz, (tuple, list)) or len(origin_native_xz) != 2 or
            not isinstance(shape_zx, (tuple, list)) or len(shape_zx) != 2 or
            any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
            any(v <= 0 for v in shape_zx)):
        raise ValueError("origin and shape must be integer pairs with positive shape")
    if (isinstance(sigma_cells, bool) or not isinstance(sigma_cells, (int, float)) or
            not math.isfinite(sigma_cells) or sigma_cells <= 0):
        raise ValueError("sigma_cells must be finite and positive")
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError("max_cells must be a positive integer")
    halo = int(math.ceil(3 * sigma_cells))
    rows, cols = shape_zx
    hrows, hcols = rows + 2 * halo, cols + 2 * halo
    if hrows * hcols > max_cells:
        raise ValueError("target and filter halo exceed max_cells")
    x0, z0 = origin_native_xz
    if spec.mode == "finite":
        fx, fz = spec.frame_origin_m
        if not (fx <= x0 * SPACING_M and fz <= z0 * SPACING_M and
                (x0 + cols - 1) * SPACING_M < fx + spec.frame_side_m and
                (z0 + rows - 1) * SPACING_M < fz + spec.frame_side_m):
            raise ValueError("target lies outside finite world")
    hx, hz = x0 - halo, z0 - halo
    field, resolved, records, _, known = _read_support(
        spec, page_records, hx, hz, hrows, hcols, source_family)
    if not resolved.all():
        raise ValueError("TD filter support has %d unresolved cells" % np.count_nonzero(~resolved))

    smooth = gaussian_filter(field, sigma=float(sigma_cells), radius=halo, mode="nearest")
    interior = np.s_[halo:halo + rows, halo:halo + cols]
    td = field[interior].copy()
    residual = (field - smooth)[interior].copy()
    x = (x0 + np.arange(cols, dtype=np.float64))[None, :] * SPACING_M
    z = (z0 + np.arange(rows, dtype=np.float64))[:, None] * SPACING_M
    x, z = np.broadcast_arrays(x, z)
    plan = None if spec.preset == "lakes" else make_ocean_plan(spec)
    ocean = None if plan is None else sample_ocean_mask(plan, spec, x, z)
    macro, correction, composed, ocean = _compose_fields(spec, td, residual, x, z, ocean)
    metadata = {"schema": "world-terrain-mosaic-v1", "layout_identity": spec.identity(),
                "world_seed": spec.world_seed, "origin_native_xz": [x0, z0],
                "shape_zx": [rows, cols], "spacing_m": SPACING_M,
                "source_family": source_family,
                "source_family_verification": _family_verification(known),
                "source_records": records, "source_border_cells": BORDER_BAND_CELLS,
                "filter": "gaussian_fixed_support", "sigma_cells": float(sigma_cells),
                "filter_radius_cells": halo, "ocean_plan": None if plan is None else plan["metadata"],
                "lake_status": "not_modelled"}
    metadata["identity"] = hashlib.sha256(json.dumps(metadata, sort_keys=True,
                                                      separators=(",", ":"),
                                                      allow_nan=False).encode()).hexdigest()
    return {"td_elevation_m": td, "macro_elevation_m": macro, "td_residual_m": residual,
            "applied_residual_m": correction, "composed_elevation_m": composed,
            "valid_mask": np.ones((rows, cols), dtype=bool), "ocean_mask": ocean,
            "metadata": metadata}



# ------------------------------------------------------------------------
# 原 terrain_pipeline/world_terrain_store.py
# ------------------------------------------------------------------------

REGION_MAX_CELLS = 1048576


WORLD_CELLS = 409600 ** 2


PREPARATION_REVISION = "connected-irregular-network-water-v3"


def make_spec(preset, water=None):
    if water is None:
        water = {"lakes": .12, "earth": .62, "archipelago": .8}[preset]
    return LayoutSpec(preset, water, world_seed=20261020, layout_id="large-world-first-pass",
                      mode="finite", frame_origin_m=(0., 0.), frame_side_m=12_288_000.)


def _bounds(origin, shape):
    if (len(origin) != 2 or len(shape) != 2 or any(type(v) is not int for v in (*origin, *shape))
            or any(v <= 0 for v in shape)):
        raise ValueError("origin and shape must be integer pairs with positive shape")
    x, z = origin
    rows, cols = shape
    if x < 0 or z < 0 or x + cols > 409600 or z + rows > 409600:
        raise ValueError("region outside finite world")
    return [x, z, x + cols, z + rows]


def _touch(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _covered_area(rectangles):
    edges = sorted({x for b in rectangles for x in (b[0], b[2])})
    area = 0
    for left, right in zip(edges, edges[1:]):
        spans = sorted((b[1], b[3]) for b in rectangles if b[0] < right and b[2] > left)
        end = None
        for start, stop in spans:
            if end is None or start > end:
                area += (right - left) * (stop - start)
                end = stop
            elif stop > end:
                area += (right - left) * (stop - end)
                end = stop
    return area


def _atomic_json(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".registry-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def open_region_registry(path, spec, source_family, forcing, sigma_cells=6.):
    if not isinstance(source_family, str) or not source_family:
        raise ValueError("source_family is required")
    world = {"layout_identity": spec.identity(), "layout": spec.parameters(),
             "source_family": source_family, "forcing": forcing, "sigma_cells": sigma_cells,
             "preparation_revision": PREPARATION_REVISION}
    world_id = identity({}, world)
    path = Path(path)
    if (path / "registry.json").exists():
        registry = json.loads((path / "registry.json").read_text(encoding="utf-8"))
        if registry.get("world", {}).get("preparation_revision") != PREPARATION_REVISION:
            raise ValueError("preparation algorithm revision differs; use a new store directory")
        if registry["world_identity"] != world_id or registry["world"] != world:
            raise ValueError("world identity mismatch")
        return registry
    return {"schema": "world-terrain-store-v1", "world": world, "world_identity": world_id,
            "pages": [], "source_bounds": [], "source_support_cells": 0,
            "components": [], "prepared_cells": 0, "world_cells": WORLD_CELLS}


def plan_region_store(registry, origin, shape, pages, coverage):
    bounds = _bounds(origin, shape)
    selected = []
    while True:
        added = [component for component in registry["components"]
                 if component not in selected and _touch(bounds, component["bounds"])]
        if not added:
            break
        for component in added:
            selected.append(component)
            bounds = _union(bounds, component["bounds"])
    rows, cols = bounds[3] - bounds[1], bounds[2] - bounds[0]
    if rows * cols > REGION_MAX_CELLS:
        raise ValueError("connected support exceeds 1048576 cells; a larger-domain solution is required")
    hit = next((item for item in selected if item["bounds"][0] <= origin[0]
                and item["bounds"][1] <= origin[1] and item["bounds"][2] >= origin[0] + shape[1]
                and item["bounds"][3] >= origin[1] + shape[0]), None)
    missing = ({"missing_cells": 0} if hit is not None else
               coverage([bounds[0], bounds[1]], [rows, cols], pages))
    return {"bounds": bounds, "origin_native_xz": bounds[:2], "shape_zx": [rows, cols],
            "selected": selected, "hit": hit, "coverage": missing}


def read_region_component(path, component, world_identity):
    root = Path(path) / "versions" / component["version"]
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    with np.load(root / "arrays.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    expected = metadata.pop("identity_sha256")
    if metadata["world_identity"] != world_identity or expected != component["identity_sha256"]:
        raise ValueError("component world or registry identity mismatch")
    if any(a.shape != tuple(metadata["shape_zx"]) for a in arrays.values()):
        raise ValueError("component shape mismatch")
    if identity(arrays, metadata) != expected:
        raise ValueError("component identity mismatch")
    if metadata.get("network") is not None:
        verify_network(root, metadata["network"])
    return arrays, metadata


def prepare_region_store(path, registry, request, pages, spec, *, compose, form, render):
    if request["hit"] is not None:
        read_region_component(path, request["hit"], registry["world_identity"])
        return request["hit"]
    if request["coverage"]["missing_cells"]:
        raise ValueError("source coverage missing; generate or register source pages first")
    world = registry["world"]
    origin, shape = request["origin_native_xz"], request["shape_zx"]
    composition = compose(spec, pages, origin, shape, sigma_cells=world["sigma_cells"],
                          max_cells=REGION_MAX_CELLS, source_family=world["source_family"])
    water = form(composition, origin, world_seed=20261020, **world["forcing"])
    arrays = {k: v for k, v in composition.items() if k != "metadata" and v is not None}
    arrays.update(water["arrays"])
    metadata = {"schema": "world-terrain-region-v1", "world_identity": registry["world_identity"],
                "origin_native_xz": origin, "shape_zx": shape, "composition": composition["metadata"],
                "water": water["metadata"], "water_identity": water["identity_sha256"],
                "stages": ["macro", "td_source", "composition", "water_and_bed"]}
    version = uuid.uuid4().hex
    root = Path(path)
    (root / "versions").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".region-", dir=root / "versions") as temp:
        staging = Path(temp) / "product"
        staging.mkdir()
        network = water.get("network")
        if network is not None:
            metadata["network"] = write_network(staging, network, water["metadata"].get("network", {}))
        digest = identity(arrays, metadata)
        np.savez_compressed(staging / "arrays.npz", **arrays)
        (staging / "metadata.json").write_text(json.dumps({**metadata, "identity_sha256": digest},
            sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
        render_arrays = arrays if network is None else {**arrays, "__river_network__": network}
        render(render_arrays, origin, staging / "stages.png")
        staging.rename(root / "versions" / version)
    component = {"version": version, "bounds": request["bounds"], "identity_sha256": digest}
    updated = dict(registry)
    updated["components"] = [c for c in registry["components"] if c not in request["selected"]] + [component]
    updated["pages"] = pages
    existing = {item["path"]: item for item in registry["source_bounds"]}
    for item in request["coverage"].get("sources", []):
        existing[item["path"]] = {"path": item["path"], "sha256": item["sha256"],
                                  "bounds": item["trusted_bounds_native_xz"]}
    updated["source_bounds"] = list(existing.values())
    clipped = [[max(0, b[0]), max(0, b[1]), min(409600, b[2]), min(409600, b[3])]
               for b in (item["bounds"] for item in updated["source_bounds"])]
    updated["source_support_cells"] = _covered_area([b for b in clipped if b[0] < b[2] and b[1] < b[3]])
    updated["prepared_cells"] = sum((b["bounds"][2] - b["bounds"][0]) *
                                    (b["bounds"][3] - b["bounds"][1]) for b in updated["components"])
    _atomic_json(root / "registry.json", updated)
    registry.update(updated)
    return component



# ------------------------------------------------------------------------
# 原 terrain_pipeline/surface_rivers/metric_fine_terrain.py
# ------------------------------------------------------------------------

FINE_SPACING_M = 30.0


SAMPLE_CALL_CELLS = 1_048_576


DEFAULT_RECONCILE_SIGMA_M = 20_000.0


DEFAULT_DETAIL_SIGMA_M = 3_000.0


DEFAULT_EDGE_MARGIN_M = 1_500.0


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.:
        raise ValueError(name + " must be finite positive")
    return value


def _shape(shape):
    if len(shape) != 2:
        raise ValueError("[row, column] shape required")
    rows, columns = (int(value) for value in shape)
    if rows < 2 or columns < 2:
        raise ValueError("at least 2x2 cells required")
    return rows, columns


def _origin(origin_xz_m):
    values = np.asarray(origin_xz_m, np.float64).reshape(-1)
    if values.size != 2 or not np.isfinite(values).all():
        raise ValueError("finite [x, z] origin required")
    return float(values[0]), float(values[1])


def fine_axes(origin_xz_m, shape, spacing_m=FINE_SPACING_M):
    """World coordinates of the lattice points; cell centres, [row(z), column(x)]."""
    rows, columns = _shape(shape)
    spacing = _positive(spacing_m, "spacing_m")
    x0, z0 = _origin(origin_xz_m)
    return (x0 + np.arange(columns) * spacing, z0 + np.arange(rows) * spacing)


def analytic_fine_field(seed, origin_xz_m, shape, spacing_m=FINE_SPACING_M):
    """Direct 30 m sampling of the conditioning field; [z, x] elevation in metres.

    `sample_physical` refuses more than `SAMPLE_CALL_CELLS` per call, so the
    lattice is sampled in row blocks. Block bounds do not affect any value:
    the field is evaluated from absolute world coordinates only.
    """
    rows, columns = _shape(shape)
    spacing = _positive(spacing_m, "spacing_m")
    xs, zs = fine_axes(origin_xz_m, shape, spacing)
    block = max(1, min(rows, SAMPLE_CALL_CELLS // columns))
    out = np.empty((rows, columns), np.float64)
    blocks = []
    for start in range(0, rows, block):
        stop = min(start + block, rows)
        east = np.broadcast_to(xs[None, :], (stop - start, columns))
        south = np.broadcast_to(zs[start:stop, None], (stop - start, columns))
        out[start:stop] = np.asarray(sample_physical(east, south, int(seed))[0], np.float64)
        blocks.append([int(start), int(stop)])
    if not np.isfinite(out).all():
        raise ValueError("conditioning field produced nonfinite elevation")
    return out, {"spacing_m": spacing, "block_rows": blocks, "world_seed": int(seed),
                 "sampler": "diffusion.geography_physical.sample_physical",
                 "coordinates": "cell centres, X east, Z south, arrays [z, x]"}


def bilinear_sample(page, page_origin_xz_m, page_spacing_m, xs, zs):
    """Bilinear sample of a regular page at arbitrary world coordinates (edge clamped).

    Used to reproduce what the reach runs actually did with a 10 km page, so the
    interpolation error of that base can be measured against the analytic field.
    """
    page = np.asarray(page, np.float64)
    if page.ndim != 2 or not np.isfinite(page).all():
        raise ValueError("finite 2D page required")
    step = _positive(page_spacing_m, "page_spacing_m")
    x0, z0 = _origin(page_origin_xz_m)
    rows, columns = page.shape
    gx = np.asarray(xs, np.float64)
    gz = np.asarray(zs, np.float64)
    fx = np.clip((gx - x0) / step, 0., columns - 1. - 1e-9)
    fz = np.clip((gz - z0) / step, 0., rows - 1. - 1e-9)
    i0 = np.floor(fx).astype(np.int64)
    j0 = np.floor(fz).astype(np.int64)
    tx = fx - i0
    tz = fz - j0
    i1 = np.minimum(i0 + 1, columns - 1)
    j1 = np.minimum(j0 + 1, rows - 1)
    tx2, tz2 = np.meshgrid(tx, tz)
    return (page[j0][:, i0] * (1. - tx2) * (1. - tz2) + page[j0][:, i1] * tx2 * (1. - tz2)
            + page[j1][:, i0] * (1. - tx2) * tz2 + page[j1][:, i1] * tx2 * tz2)


def smoothstep(values):
    clipped = np.clip(np.asarray(values, np.float64), 0., 1.)
    return clipped * clipped * (3. - 2. * clipped)


def edge_taper(shape, spacing_m, margin_m):
    """1 in the interior, exactly 0 on the border; smoothstep over `margin_m`."""
    rows, columns = _shape(shape)
    spacing = _positive(spacing_m, "spacing_m")
    margin = _positive(margin_m, "margin_m")
    zs = np.arange(rows) * spacing
    xs = np.arange(columns) * spacing
    distance = np.minimum.reduce([
        np.broadcast_to(xs[None, :], (rows, columns)),
        np.broadcast_to((xs[-1] - xs)[None, :], (rows, columns)),
        np.broadcast_to(zs[:, None], (rows, columns)),
        np.broadcast_to((zs[-1] - zs)[:, None], (rows, columns))])
    weight = smoothstep(distance / margin)
    weight[[0, -1], :] = 0.
    weight[:, [0, -1]] = 0.
    return weight


def affine_reconcile(td, base, spacing_m, reconcile_sigma_m=DEFAULT_RECONCILE_SIGMA_M,
                     detail_sigma_m=DEFAULT_DETAIL_SIGMA_M):
    """Fit the checkpoint's vertical frame onto world metres, then measure the band.

    The fit is done on the low pass at `reconcile_sigma_m` only. It is an
    **uncalibrated engineering conversion** (there is no observational truth for
    this terrain), and it is recorded as such instead of being presented as a
    measurement.
    """
    from scipy import ndimage

    td = np.asarray(td, np.float64)
    base = np.asarray(base, np.float64)
    if td.shape != base.shape or td.ndim != 2:
        raise ValueError("TD and base must share one 2D shape")
    if not (np.isfinite(td).all() and np.isfinite(base).all()):
        raise ValueError("finite TD and base fields required")
    spacing = _positive(spacing_m, "spacing_m")
    sigma_reconcile = _positive(reconcile_sigma_m, "reconcile_sigma_m") / spacing
    sigma_detail = _positive(detail_sigma_m, "detail_sigma_m") / spacing
    td_low = ndimage.gaussian_filter(td, sigma_reconcile, mode="nearest")
    base_low = ndimage.gaussian_filter(base, sigma_reconcile, mode="nearest")
    slope, intercept = np.polyfit(td_low.ravel(), base_low.ravel(), 1)
    if not (math.isfinite(slope) and math.isfinite(intercept)) or slope == 0.:
        raise ValueError("degenerate affine reconciliation")
    residual = base_low - (slope * td_low + intercept)
    return float(slope), float(intercept), {
        "reconcile_sigma_m": float(reconcile_sigma_m), "detail_sigma_m": float(detail_sigma_m),
        "slope": float(slope), "intercept_m": float(intercept),
        "correlation": float(np.corrcoef(td_low.ravel(), base_low.ravel())[0, 1]),
        "residual_rms_m": float(residual.std()),
        "residual_max_m": float(np.max(np.abs(residual))),
        "status": "uncalibrated engineering conversion, not an observation",
        "interpretation": "world_m = slope * td_native + intercept, applied to the detail band only"}


def td_detail_band(td, base, spacing_m=FINE_SPACING_M, *,
                   reconcile_sigma_m=DEFAULT_RECONCILE_SIGMA_M,
                   detail_sigma_m=DEFAULT_DETAIL_SIGMA_M,
                   edge_margin_m=DEFAULT_EDGE_MARGIN_M):
    """High-frequency TD band, in world metres, tapered to zero on the border.

    Returns `detail_m` (already edge-tapered) and the taper `weight_m`. Adding
    `weight * detail_m` to the analytic base changes nothing at the window border
    and nothing at wavelengths longer than `detail_sigma_m`.
    """
    from scipy import ndimage

    td = np.asarray(td, np.float64)
    base = np.asarray(base, np.float64)
    spacing = _positive(spacing_m, "spacing_m")
    slope, intercept, diagnostics = affine_reconcile(
        td, base, spacing, reconcile_sigma_m, detail_sigma_m)
    sigma_cells = _positive(detail_sigma_m, "detail_sigma_m") / spacing
    low = ndimage.gaussian_filter(td, sigma=sigma_cells, mode="nearest")
    band = slope * (td - low)
    weight = edge_taper(td.shape, spacing, edge_margin_m)
    detail = weight * band
    if float(np.abs(detail[[0, -1], :]).max(initial=0.)) != 0. or float(np.abs(detail[:, [0, -1]]).max(initial=0.)) != 0.:
        raise ValueError("edge taper left a nonzero border term")
    diagnostics = dict(diagnostics, edge_margin_m=float(edge_margin_m),
                       band_std_m=float(band.std()), band_min_m=float(band.min()),
                       band_max_m=float(band.max()),
                       border_term_max_abs_m=0.0,
                       border_note="the injected term is exactly zero on the window border")
    return detail, weight, diagnostics


def mosaic_detail_m(contributions):
    """Coverage-weighted sum of edge-tapered detail bands.

    With `coverage = sum(w)`, the result is `sum(w*d)/max(coverage, eps) * min(coverage, 1)`:

    * one window inside        -> coverage 1        -> `d` (full detail)
    * one window on its border -> coverage 0        -> `0` (continuous into the base)
    * one window in the taper  -> coverage w < 1    -> `w*d` (continuous decay)
    * two windows fully stacked-> coverage 2        -> mean of the two bands

    Dividing alone would cancel the taper and put a step exactly at the border,
    which is why `min(coverage, 1)` is not optional.
    """
    if not contributions:
        raise ValueError("at least one detail contribution required")
    shape = None
    detail_sum = None
    coverage = None
    for detail, weight in contributions:
        detail = np.asarray(detail, np.float64)
        weight = np.asarray(weight, np.float64)
        if detail.shape != weight.shape or detail.ndim != 2:
            raise ValueError("each contribution needs matching [z, x] detail and weight")
        if shape is None:
            shape = detail.shape
            detail_sum = np.zeros(shape, np.float64)
            coverage = np.zeros(shape, np.float64)
        elif detail.shape != shape:
            raise ValueError("contributions must share one shape")
        detail_sum += weight * detail
        coverage += weight
    scaled = detail_sum / np.maximum(coverage, 1e-12) * np.minimum(coverage, 1.)
    return np.where(coverage > 1e-12, scaled, 0.), coverage


def adjacent_step_m(field, spacing_m=FINE_SPACING_M):
    """Largest absolute height step between 4-connected neighbours, in metres."""
    values = np.asarray(field, np.float64)
    if values.ndim != 2 or values.size < 4:
        raise ValueError("at least a 2x2 field required")
    _positive(spacing_m, "spacing_m")
    horizontal = np.abs(np.diff(values, axis=1))
    vertical = np.abs(np.diff(values, axis=0))
    return {"max_m": float(max(horizontal.max(initial=0.), vertical.max(initial=0.))),
            "p99_m": float(np.percentile(np.concatenate([horizontal.ravel(), vertical.ravel()]), 99)),
            "p50_m": float(np.percentile(np.concatenate([horizontal.ravel(), vertical.ravel()]), 50))}


def seam_diagnostics(fine, seam_cells, spacing_m=FINE_SPACING_M):
    """Compare steps across declared seam cells with the field's own step scale.

    `seam_cells` is a boolean [z, x] mask marking cells whose downstream/rightward
    neighbour sits in another window. A seam introduces no step when the steps
    across it stay inside the interior step distribution.
    """
    values = np.asarray(fine, np.float64)
    mask = np.asarray(seam_cells, bool)
    if mask.shape != values.shape:
        raise ValueError("seam mask must match the field")
    inside = adjacent_step_m(values, spacing_m)
    steps = []
    for axis in (0, 1):
        moved = np.roll(values, -1, axis=axis)
        crossed = np.abs(moved - values)
        valid = np.zeros(values.shape, bool)
        if axis == 0:
            valid[:-1, :] = True
        else:
            valid[:, :-1] = True
        steps.append(crossed[valid & mask])
    across = np.concatenate(steps) if steps else np.array([])
    return {"seam_cells": int(mask.sum()), "across_seam_samples": int(across.size),
            "across_seam_max_m": float(across.max()) if across.size else None,
            "across_seam_mean_m": float(across.mean()) if across.size else None,
            "interior": inside}


@dataclass(frozen=True)
class FineTerrainField:
    """One 30 m base page plus the identity of everything that produced it."""

    elevation_m: np.ndarray
    valid_mask: np.ndarray
    origin_xz_m: tuple
    spacing_m: float
    provenance: dict

    def __post_init__(self):
        height = self.elevation_m
        if not isinstance(height, np.ndarray) or height.dtype != np.float64 or height.ndim != 2:
            raise ValueError("float64 [z, x] elevation required")
        valid = self.valid_mask
        if not isinstance(valid, np.ndarray) or valid.dtype != bool or valid.shape != height.shape or not valid.any():
            raise ValueError("nonempty boolean valid mask required")
        if not np.isfinite(height[valid]).all():
            raise ValueError("nonfinite elevation on valid cells")
        spacing = _positive(self.spacing_m, "spacing_m")
        x0, z0 = _origin(self.origin_xz_m)
        if not isinstance(self.provenance, dict) or not self.provenance:
            raise ValueError("provenance record required")
        object.__setattr__(self, "elevation_m", readonly(np.where(valid, height, 0.)))
        object.__setattr__(self, "valid_mask", readonly(valid))
        object.__setattr__(self, "origin_xz_m", (x0, z0))
        object.__setattr__(self, "spacing_m", spacing)

    @property
    def identity_sha256(self):
        return identity({"elevation_m": self.elevation_m, "valid_mask": self.valid_mask},
                        {"origin_xz_m": list(self.origin_xz_m), "spacing_m": self.spacing_m,
                         "provenance": self.provenance})

    def metadata(self):
        return {"origin_xz_m": list(self.origin_xz_m), "spacing_m": self.spacing_m,
                "shape": list(self.elevation_m.shape), "cell_area_m2": self.spacing_m ** 2,
                "coordinates": "cell centres; X east, Z south; arrays [z, x]",
                "identity_sha256": self.identity_sha256, "provenance": self.provenance}

    def save(self, path):
        from pathlib import Path

        target = Path(path)
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        metadata = self.metadata()
        np.savez(target, elevation_m=np.asarray(self.elevation_m, np.float64),
                 valid_mask=np.asarray(self.valid_mask, bool),
                 origin_xz_m=np.array(self.origin_xz_m, np.float64),
                 spacing_m=np.array(self.spacing_m, np.float64),
                 provenance_json=np.array(json.dumps(metadata, sort_keys=True)),
                 identity_sha256=np.array(self.identity_sha256))
        return target

    @classmethod
    def load(cls, path):
        page = np.load(path, allow_pickle=False)
        metadata = json.loads(str(page["provenance_json"]))
        field = cls(np.asarray(page["elevation_m"], np.float64),
                    np.asarray(page["valid_mask"], bool),
                    tuple(np.asarray(page["origin_xz_m"], np.float64).tolist()),
                    float(np.asarray(page["spacing_m"], np.float64)),
                    metadata["provenance"])
        if field.identity_sha256 != str(page["identity_sha256"]):
            raise ValueError("saved fine terrain identity does not recompute")
        return field


def compose_fine_terrain(seed, origin_xz_m, shape, contributions=(), *,
                         spacing_m=FINE_SPACING_M, source_label="analytic_30m"):
    """Analytic 30 m base plus an optional mosaicked TD detail term."""
    base, sampling = analytic_fine_field(seed, origin_xz_m, shape, spacing_m)
    if contributions:
        detail, coverage = mosaic_detail_m(contributions)
        elevation = base + detail
        detail_record = {"windows": len(contributions),
                         "coverage_max": float(coverage.max()),
                         "coverage_min_overlap": float(coverage[coverage > 1e-9].min(initial=0.)),
                         "detail_std_m": float(detail.std()),
                         "detail_min_m": float(detail.min()), "detail_max_m": float(detail.max())}
    else:
        elevation = base.copy()
        detail_record = {"windows": 0, "detail_std_m": 0.0}
    provenance = {"schema": "fine-terrain-base-v1", "source_label": source_label,
                  "world_seed": int(seed), "sampling": sampling,
                  "td_detail": detail_record,
                  "declared_quantities": {
                      "analytic": "sample_physical at 30 m; seed-determined, window-independent",
                      "td_detail": "edge-tapered high-pass band of a TD window, affine-fitted onto the analytic low pass",
                      "composed": "analytic + coverage-weighted sum of td_detail terms"},
                  "not_claimed": ("the TD band is not an observation and its affine conversion is an "
                                  "uncalibrated engineering parameter")}
    return FineTerrainField(elevation, np.ones(elevation.shape, bool), origin_xz_m,
                            spacing_m, provenance)

CATEGORY = "A"
