"""Diagnostic native-grid water snapshot from an externally pinned saved v10 page."""

import math

import numpy as np

from terrain_pipeline.common_infra import (
    file_sha256,
    identity,
    load_bundle,
    readonly,
    save_bundle,
    publish_bytes,
)
from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage
from terrain_pipeline.basin_storage import validate_storage as validate_storage


MAX_CELLS = 250000
MAX_VERTICES = 250000
MAX_TRIANGLES = 500000
MAX_BYTES = 128 * 1024 ** 2
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")


def _grid(height, depth, valid, threshold):
    if height.size > MAX_CELLS:
        raise ValueError("native water cell budget exceeded")
    if (height.dtype != np.float64 or depth.dtype != np.float64 or valid.dtype != bool or
            height.ndim != 2 or depth.shape != height.shape or valid.shape != height.shape or
            not np.isfinite(height).all() or
            not np.isfinite(depth).all() or np.any(depth < 0) or np.any(depth[~valid] != 0) or
            not math.isfinite(threshold) or threshold <= 0):
        raise ValueError("native water grid/threshold invalid")
    wet = valid & (depth >= threshold)
    cells = wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]
    row, column = np.nonzero(cells)
    columns = height.shape[1]
    corners = np.column_stack((row * columns + column, (row + 1) * columns + column,
                               (row + 1) * columns + column + 1, row * columns + column + 1))
    vertex_ids = np.unique(corners)
    if len(vertex_ids) > MAX_VERTICES or len(corners) * 2 > MAX_TRIANGLES:
        raise ValueError("native water mesh budget exceeded")
    local = np.searchsorted(vertex_ids, corners)
    triangles = np.empty((2 * len(corners), 3), dtype=np.int64)
    triangles[0::2] = local[:, [0, 1, 2]]
    triangles[1::2] = local[:, [0, 2, 3]]
    return vertex_ids.astype(np.int64), triangles, wet, cells


def build_water_surface(page, *, source_sha256, wet_threshold_m):
    validate_storage(page)
    if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(character not in "0123456789abcdef" for character in source_sha256):
        raise ValueError("external page SHA required")
    source = page["arrays"]
    page_meta = page["metadata"]
    height = source["height_m"]
    valid = source["valid_mask"]
    depth = source["depth_m"][-1].reshape(height.shape)
    spacing = page_meta["spacing_m"]
    origin = page_meta["origin_m_xz"]
    vertex_ids, triangles, wet, covered = _grid(height, depth, valid, wet_threshold_m)
    cell_ids = np.flatnonzero(valid).astype(np.int64)
    native_bed = height.ravel()[cell_ids].copy()
    cell_depth = depth.ravel()[cell_ids].copy()
    if (len(cell_ids) * 32 + len(vertex_ids) * 48 + len(triangles) * 24) > MAX_BYTES:
        raise ValueError("native water byte budget exceeded")
    x = origin[0] + vertex_ids % height.shape[1] * spacing
    z = origin[1] + vertex_ids // height.shape[1] * spacing
    vertices = np.column_stack((x, height.ravel()[vertex_ids] + depth.ravel()[vertex_ids], z))
    drawn_vertex_mask = np.zeros(height.size, bool)
    drawn_vertex_mask[vertex_ids] = True
    undrawn_wet = wet.ravel() & ~drawn_vertex_mask.reshape(height.shape).ravel()
    area = spacing ** 2
    arrays = dict(cell_ids=cell_ids, native_bed_m=native_bed, hour_end_depth_m=cell_depth,
                  vertex_cell_ids=vertex_ids, vertices_xyz_m=vertices, triangles=triangles)
    metadata = dict(schema="td-native-water-surface-v1", algorithm="native-v10-hour-end-wet-quad-v1",
                    source_page_sha256=source_sha256, source_page_identity=page["identity_sha256"],
                    hierarchy_identity=page_meta["hierarchy_identity"], forcing_identity=page_meta["forcing_identity"],
                    grid_shape=list(height.shape), origin_m_xz=list(origin), spacing_m=spacing,
                    start_s=page_meta["start_s"], end_s=page_meta["end_s"], wet_threshold_m=wet_threshold_m,
                    valid_cell_count=int(len(cell_ids)), wet_cell_count=int(np.count_nonzero(wet)),
                    drawn_quad_count=int(np.count_nonzero(covered)),
                    undrawn_wet_cell_count=int(np.count_nonzero(undrawn_wet)),
                    grid_water_volume_m3=float(np.sum(cell_depth, dtype=np.float64) * area),
                    undrawn_wet_grid_volume_m3=float(np.sum(depth.ravel()[undrawn_wet], dtype=np.float64) * area),
                    volume_semantics="sum of all valid native cell end-depth times native cell area; not mesh volume",
                    scope="diagnostic native coarse snapshot from saved v10 hour; no full time-series acceptance",
                    coordinates="physical metres [x,y,z]; x east, y up, z south",
                    derived_fine_hydraulics=False, water_generated=False,
                    **{flag: False for flag in FLAGS})
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
    validate_water_surface(result)
    result["arrays"] = {name: readonly(value) for name, value in arrays.items()}
    return result


def validate_water_surface(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata.get("schema") != "td-native-water-surface-v1" or
            metadata.get("derived_fine_hydraulics") is not False or metadata.get("water_generated") is not False or
            any(metadata.get(flag) is not False for flag in FLAGS)):
        raise ValueError("water surface schema/scope invalid")
    if identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("water surface identity mismatch")
    shape = metadata["grid_shape"]
    if (len(shape) != 2 or any(type(size) is not int or size < 2 for size in shape) or
            math.prod(shape) > MAX_CELLS or len(metadata["origin_m_xz"]) != 2 or
            not np.isfinite(metadata["origin_m_xz"]).all() or
            not math.isfinite(metadata["spacing_m"]) or metadata["spacing_m"] <= 0):
        raise ValueError("water surface coordinates/budget invalid")
    if set(arrays) != {"cell_ids", "native_bed_m", "hour_end_depth_m", "vertex_cell_ids", "vertices_xyz_m", "triangles"}:
        raise ValueError("water surface fields invalid")
    cell_ids = arrays["cell_ids"]
    vertex_ids = arrays["vertex_cell_ids"]
    vertices = arrays["vertices_xyz_m"]
    triangles = arrays["triangles"]
    if (cell_ids.dtype != np.int64 or cell_ids.ndim != 1 or np.any(cell_ids < 0) or
            np.any(cell_ids >= math.prod(shape)) or np.any(np.diff(cell_ids) <= 0) or
            vertex_ids.dtype != np.int64 or vertex_ids.ndim != 1 or np.any(np.diff(vertex_ids) <= 0) or
            len(vertex_ids) > MAX_VERTICES or len(triangles) > MAX_TRIANGLES or
            vertices.dtype != np.float64 or vertices.shape != (len(vertex_ids), 3) or
            triangles.dtype != np.int64 or triangles.shape != (len(triangles), 3) or
            any(arrays[name].dtype != np.float64 or arrays[name].shape != (len(cell_ids),)
                for name in ("native_bed_m", "hour_end_depth_m")) or
            sum(values.nbytes for values in arrays.values()) > MAX_BYTES or
            any(not np.isfinite(values).all() for values in arrays.values()) or
            np.any(arrays["hour_end_depth_m"] < 0)):
        raise ValueError("water surface arrays invalid")
    valid = np.zeros(math.prod(shape), bool)
    valid[cell_ids] = True
    bed = np.zeros(math.prod(shape), np.float64)
    depth = np.zeros(math.prod(shape), np.float64)
    bed[cell_ids] = arrays["native_bed_m"]
    depth[cell_ids] = arrays["hour_end_depth_m"]
    expected_ids, expected_triangles, wet, covered = _grid(
        bed.reshape(shape), depth.reshape(shape), valid.reshape(shape), metadata["wet_threshold_m"])
    if not np.array_equal(vertex_ids, expected_ids) or not np.array_equal(triangles, expected_triangles):
        raise ValueError("water surface wet topology invalid")
    expected_xyz = np.column_stack((metadata["origin_m_xz"][0] + vertex_ids % shape[1] * metadata["spacing_m"],
                                    bed[vertex_ids] + depth[vertex_ids],
                                    metadata["origin_m_xz"][1] + vertex_ids // shape[1] * metadata["spacing_m"]))
    if not np.array_equal(vertices, expected_xyz):
        raise ValueError("water surface source height/depth mismatch")
    drawn = np.zeros(math.prod(shape), bool)
    drawn[vertex_ids] = True
    undrawn = wet.ravel() & ~drawn
    if (metadata["valid_cell_count"] != len(cell_ids) or
            metadata["wet_cell_count"] != int(np.count_nonzero(wet)) or
            metadata["drawn_quad_count"] != int(np.count_nonzero(covered)) or
            metadata["undrawn_wet_cell_count"] != int(np.count_nonzero(undrawn)) or
            metadata["grid_water_volume_m3"] != float(np.sum(depth[cell_ids], dtype=np.float64) * metadata["spacing_m"] ** 2) or
            metadata["undrawn_wet_grid_volume_m3"] != float(np.sum(depth[undrawn], dtype=np.float64) * metadata["spacing_m"] ** 2)):
        raise ValueError("water surface grid volume/count audit invalid")
    return True


def save_water_surface(path, result):
    save_bundle(path, result, validator=validate_water_surface)


def load_water_surface(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_water_surface, max_bytes=MAX_BYTES)
    if result["identity_sha256"] != expected_identity or file_sha256(path) != expected_sha256:
        raise ValueError("water surface external pin mismatch")
    return result


def export_water_obj(path, result):
    validate_water_surface(result)
    arrays = result["arrays"]
    lines = ["# saved native coarse hour-end water surface; diagnostic only; no water volume from mesh",
             "# source_page_identity " + result["metadata"]["source_page_identity"]]
    for vertex in arrays["vertices_xyz_m"]:
        lines.append("v " + " ".join(format(float(value), ".17g") for value in vertex))
    for triangle in arrays["triangles"]:
        lines.append("f " + " ".join(str(int(index) + 1) for index in triangle))
    payload = ("\n".join(lines) + "\n").encode("ascii")
    if len(payload) > MAX_BYTES:
        raise ValueError("water surface OBJ byte budget exceeded")
    publish_bytes(path, payload)


def load_pinned_page(path, *, expected_sha256, expected_identity):
    if file_sha256(path) != expected_sha256:
        raise ValueError("v10 page external SHA mismatch")
    page = load_storage(path, expected_sha256=expected_sha256, expected_identity=expected_identity)
    if file_sha256(path) != expected_sha256:
        raise ValueError("v10 page changed while reading")
    return page
