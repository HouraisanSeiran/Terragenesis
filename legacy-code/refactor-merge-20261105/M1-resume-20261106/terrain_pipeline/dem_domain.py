"""Bounded read-only real DEM preparation; never a publishable water product."""

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


FORMAT = "dem-domain-candidate-v2"
ALGORITHM = "bounded-exact-inverse-center-dem-sampling-v2"
STATUS = "candidate_not_publishable"
ARRAY_NAMES = {"height_m", "valid_mask", "unknown_mask", "footprint_mask", "core_mask"}
MAX_CELLS = 500000
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
    for name, value, maximum in (("max_cells", max_cells, MAX_CELLS),
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
    manifest = {"format": FORMAT, "status": STATUS, "identity": identity,
                "identity_sha256": digest(identity), "summary": _summary(arrays),
                "array_hashes": {name: array_hash(value) for name, value in arrays.items()}}
    manifest["content_sha256"] = digest(manifest)
    for values in arrays.values():
        values.flags.writeable = False
    return {"manifest": manifest, "arrays": arrays}


def prepare_dem_candidate(source_path, bbox_epsg4326, *, target_crs, spacing_m,
                          sea_level_m, sea_datum, source_declaration,
                          vertical_datum="unknown", vertical_datum_status="unknown",
                          halo_m=900., max_cells=MAX_CELLS, max_source_cells=MAX_SOURCE_CELLS):
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
    return _seal({"algorithm": ALGORITHM, "recipe": recipe, "recipe_sha256": digest(recipe),
                  "source": source_record, "grid": grid, "rasterio_version": rasterio.__version__}, arrays)


def validate_dem_candidate(candidate, *, verify_source=True):
    """Reject hashes and self-rehashed false publication/coverage semantics."""
    if set(candidate) != {"manifest", "arrays"}:
        raise ValueError("invalid candidate fields")
    manifest, arrays = candidate["manifest"], candidate["arrays"]
    if set(manifest) != {"format", "status", "identity", "identity_sha256", "summary", "array_hashes", "content_sha256"}:
        raise ValueError("invalid manifest fields")
    if manifest["format"] != FORMAT or manifest["status"] != STATUS:
        raise ValueError("DEM candidate cannot publish")
    identity = manifest["identity"]
    if set(identity) != {"algorithm", "recipe", "recipe_sha256", "source", "grid", "rasterio_version"}:
        raise ValueError("invalid identity fields")
    if identity["algorithm"] != ALGORITHM or manifest["identity_sha256"] != digest(identity):
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


def _unique_pairs(pairs):
    record = {}
    for name, value in pairs:
        if name in record:
            raise ValueError("duplicate manifest key")
        record[name] = value
    return record


def _reject_constant(value):
    raise ValueError(f"nonfinite manifest constant: {value}")


def load_dem_candidate(path, *, verify_source=True):
    """Default: bounded source replay. False: offline structure only, not evidence."""
    with np.load(path, allow_pickle=False) as archive:
        if len(archive.files) != len(ARRAY_NAMES) + 1 or set(archive.files) != ARRAY_NAMES | {"manifest"}:
            raise ValueError("unexpected NPZ payload")
        manifest = json.loads(str(archive["manifest"].item()), object_pairs_hook=_unique_pairs,
                              parse_constant=_reject_constant)
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
    from terrain_pipeline.irregular_grid import grid_mesh
    from terrain_pipeline.irregular_drainage import route_graph
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
