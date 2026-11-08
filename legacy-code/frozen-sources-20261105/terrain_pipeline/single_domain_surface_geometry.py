"""Bounded native-bed geometry and exact cell-support surfaces of saved v10 states.

The finite-volume model stores cell-centred depths. Independent, flat dual cells
represent those volumes exactly; shared corners are deliberately not smoothed.
Support side walls are numerical wet perimeters, never inferred natural banks.
"""

import math
import re

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_storage_v10_io import validate_storage


MAX_CELLS = 250000
MAX_BYTES = 256 * 1024 ** 2
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")
STATIC = ("height_m", "valid_mask", "receiver", "face_cells", "boundary_cells")
COORDINATES = "physical metres [x,y,z]; x east, y up, z south; raster [z,x]"
ALGORITHM = "native-dual-cell-support-v1"
GEOMETRY_SEMANTICS = dict(
    bed_semantics="original native cell-centred samples, flat independent dual-cell supports; no incision",
    topology_semantics="all valid static D4 receiver links; shared indexed native-bed XYZ junctions; not actual hydraulic flow",
)
FRAME_SEMANTICS = dict(
    water_semantics="saved native cell bed + depth; all depth > 0 supports, without wet threshold",
    volume_semantics="projected triangle area times owning cell depth; compared with native raster area*depth",
    support_side_semantics="wet/dry and outer support perimeter walls; not certified natural river banks",
    limitation="piecewise constant discontinuous cell surfaces; no smoothed junction water surface or 3D hydraulic certification",
)


def _sha(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("external SHA/identity invalid")


def _check(result, schema):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != schema or any(metadata.get(name) is not False for name in FLAGS):
        raise ValueError("surface schema/certification invalid")
    semantics = GEOMETRY_SEMANTICS if schema == "single-domain-native-surface-geometry-v1" else FRAME_SEMANTICS
    if (metadata.get("algorithm") != ALGORITHM or metadata.get("coordinates") != COORDINATES or
            any(metadata.get(name) != value for name, value in semantics.items())):
        raise ValueError("surface algorithm/coordinate/representation semantics invalid")
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("surface byte budget exceeded")
    if identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("surface identity mismatch")
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("nonfinite surface array")
    return arrays, metadata


def _finish(arrays, metadata):
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("surface byte budget exceeded")
    return dict(arrays={name: readonly(value) for name, value in arrays.items()},
                metadata=metadata, identity_sha256=identity(arrays, metadata))


def _native(arrays, metadata):
    height, valid, receiver = (arrays[name] for name in ("height_m", "valid_mask", "receiver"))
    shape = height.shape
    if (height.dtype != np.float64 or height.ndim != 2 or min(shape) < 2 or height.size > MAX_CELLS or
            valid.dtype != bool or valid.shape != shape or receiver.dtype != np.int64 or
            receiver.shape != (height.size,) or not valid.any() or
            not np.isfinite(height).all() or np.any(receiver[~valid.ravel()] != -1)):
        raise ValueError("native bed/mask/receiver invalid")
    spacing, origin = metadata["spacing_m"], metadata["origin_m_xz"]
    if (type(spacing) not in (int, float) or not math.isfinite(spacing) or spacing <= 0 or
            not isinstance(origin, list) or len(origin) != 2 or
            any(type(value) not in (int, float) or not math.isfinite(value) for value in origin) or
            metadata["grid_shape"] != list(shape)):
        raise ValueError("native metric coordinates invalid")
    ids = np.flatnonzero(valid).astype(np.int64)
    active = receiver[ids] >= 0
    targets = receiver[ids][active]
    if np.any(receiver < -1) or np.any(targets >= height.size) or not valid.ravel()[targets].all():
        raise ValueError("receiver leaves valid native support")
    sources = ids[active]
    if np.any(abs(sources // shape[1] - targets // shape[1]) + abs(sources % shape[1] - targets % shape[1]) != 1):
        raise ValueError("receiver must be D4")
    completed = np.zeros(height.size, bool)
    for start in ids:
        path = set()
        cell = int(start)
        while cell >= 0 and not completed[cell]:
            if cell in path:
                raise ValueError("receiver cycle")
            path.add(cell)
            cell = int(receiver[cell])
        completed[list(path)] = True
    row, column = np.nonzero(valid[:, :-1] & valid[:, 1:])
    horizontal = np.column_stack((row * shape[1] + column, row * shape[1] + column + 1))
    row, column = np.nonzero(valid[:-1, :] & valid[1:, :])
    vertical = np.column_stack((row * shape[1] + column, (row + 1) * shape[1] + column))
    expected_faces = np.concatenate((horizontal, vertical)).astype(np.int64)
    faces = arrays["face_cells"]
    if (faces.dtype != np.int64 or faces.shape != expected_faces.shape or
            not np.array_equal(faces[np.lexsort((faces[:, 1], faces[:, 0]))],
                               expected_faces[np.lexsort((expected_faces[:, 1], expected_faces[:, 0]))])):
        raise ValueError("native D4 faces missing, duplicated or invalid")
    boundary = arrays["boundary_cells"]
    if (boundary.dtype != np.int64 or boundary.ndim != 1 or np.any(boundary < 0) or
            np.any(boundary >= height.size) or np.any(np.diff(boundary) <= 0) or
            not valid.ravel()[boundary].all()):
        raise ValueError("engineering boundary cells invalid")
    xyz = np.column_stack((origin[0] + ids % shape[1] * spacing, height.ravel()[ids],
                           origin[1] + ids // shape[1] * spacing))
    edges = np.searchsorted(ids, np.column_stack((sources, targets))).astype(np.int64)
    return ids, xyz, edges


def _quads(ids, heights, shape, spacing, origin):
    offsets = np.array([[-.5, -.5], [-.5, .5], [.5, .5], [.5, -.5]]) * spacing
    centres = np.column_stack((origin[0] + ids % shape[1] * spacing,
                               origin[1] + ids // shape[1] * spacing))
    vertices = np.empty((len(ids), 4, 3), np.float64)
    vertices[:, :, 0] = centres[:, None, 0] + offsets[:, 0]
    vertices[:, :, 2] = centres[:, None, 1] + offsets[:, 1]
    vertices[:, :, 1] = heights[:, None]
    corners = np.arange(len(ids) * 4, dtype=np.int64).reshape(-1, 4)
    triangles = np.empty((len(ids) * 2, 3), np.int64)
    triangles[::2] = corners[:, [0, 1, 2]]
    triangles[1::2] = corners[:, [0, 2, 3]]
    return vertices.reshape(-1, 3), triangles


def _geometry_arrays(static, metadata):
    ids, xyz, edges = _native(static, metadata)
    bed, triangles = _quads(ids, xyz[:, 1], static["height_m"].shape,
                            metadata["spacing_m"], metadata["origin_m_xz"])
    boundary = np.isin(ids, static["boundary_cells"])
    receiver = static["receiver"][ids]
    uphill = np.zeros(len(ids), bool)
    active = receiver >= 0
    uphill[active] = static["height_m"].ravel()[receiver[active]] > xyz[active, 1]
    return dict(static, node_cell_ids=ids, node_xyz_m=xyz, edge_node_indices=edges,
                node_engineering_boundary=boundary, node_internal_sink=(receiver < 0) & ~boundary,
                node_receiver_uphill=uphill,
                bed_vertices_xyz_m=bed, bed_triangles=triangles)


def build_geometry(hierarchy, *, source_hierarchy_sha256):
    validate_basin_hierarchy(hierarchy)
    _sha(source_hierarchy_sha256)
    source = hierarchy["metadata"]
    metadata = dict(schema="single-domain-native-surface-geometry-v1", algorithm=ALGORITHM,
                    hierarchy_identity=hierarchy["identity_sha256"], source_hierarchy_sha256=source_hierarchy_sha256,
                    source_identity=source["source_identity_sha256"], grid_shape=list(hierarchy["arrays"]["height_m"].shape),
                    spacing_m=source["spacing_m"], origin_m_xz=list(source["origin_m_xz"]), coordinates=COORDINATES,
                    **GEOMETRY_SEMANTICS,
                    candidate_bed_used=False, continuous_surface=False, **{name: False for name in FLAGS})
    arrays = _geometry_arrays({name: hierarchy["arrays"][name].copy() for name in STATIC}, metadata)
    result = _finish(arrays, metadata)
    validate_geometry(result)
    return result


def _equal_arrays(actual, expected):
    if set(actual) != set(expected):
        raise ValueError("surface array fields invalid")
    for name, value in expected.items():
        if actual[name].dtype != value.dtype or not np.array_equal(actual[name], value):
            raise ValueError("surface geometry/source mismatch: " + name)


def validate_geometry(result):
    arrays, metadata = _check(result, "single-domain-native-surface-geometry-v1")
    for name in ("hierarchy_identity", "source_hierarchy_sha256", "source_identity"):
        _sha(metadata[name])
    if metadata.get("candidate_bed_used") is not False or metadata.get("continuous_surface") is not False:
        raise ValueError("native bed representation invalid")
    _equal_arrays(arrays, _geometry_arrays({name: arrays[name] for name in STATIC}, metadata))
    return True


def _frame_arrays(geometry, depth):
    arrays, metadata = geometry["arrays"], geometry["metadata"]
    shape = arrays["height_m"].shape
    ids = arrays["node_cell_ids"]
    if depth.dtype != np.float64 or depth.shape != (len(ids),) or np.any(depth < 0) or not np.isfinite(depth).all():
        raise ValueError("native state depth invalid")
    wet = ids[depth > 0]
    levels = arrays["height_m"].ravel()[wet] + depth[depth > 0]
    vertices, triangles = _quads(wet, levels, shape, metadata["spacing_m"], metadata["origin_m_xz"])
    wet_mask = np.zeros(math.prod(shape), bool)
    wet_mask[wet] = True
    # Each perimeter wall belongs to its wet dual cell. No artificial walls on wet/wet faces.
    perimeter = []
    columns = shape[1]
    for index, cell in enumerate(wet):
        row, column = divmod(int(cell), columns)
        neighbors = (cell - 1 if column else -1, cell + columns if row + 1 < shape[0] else -1,
                     cell + 1 if column + 1 < columns else -1, cell - columns if row else -1)
        for side, neighbor in enumerate(neighbors):
            if neighbor < 0 or not wet_mask[neighbor]:
                perimeter.append((index, side))
    side_vertices = np.empty((len(perimeter), 4, 3), np.float64)
    top = vertices.reshape(-1, 4, 3)
    for index, (wet_index, side) in enumerate(perimeter):
        first, second = top[wet_index, side], top[wet_index, (side + 1) % 4]
        side_vertices[index] = [first, second, second, first]
        side_vertices[index, 2:, 1] = arrays["height_m"].ravel()[wet[wet_index]]
    corners = np.arange(len(perimeter) * 4, dtype=np.int64).reshape(-1, 4)
    side_triangles = np.empty((len(perimeter) * 2, 3), np.int64)
    side_triangles[::2] = corners[:, [0, 1, 2]]
    side_triangles[1::2] = corners[:, [0, 2, 3]]
    output = {name: value.copy() for name, value in arrays.items()}
    output.update(native_depth_m=depth.copy(), wet_cell_ids=wet, water_vertices_xyz_m=vertices,
                  water_triangles=triangles, support_side_vertices_xyz_m=side_vertices.reshape(-1, 3),
                  support_side_triangles=side_triangles)
    points = vertices[triangles][:, :, [0, 2]]
    delta1, delta2 = points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]
    areas = abs(delta1[:, 0] * delta2[:, 1] - delta1[:, 1] * delta2[:, 0]) / 2
    triangle_volume = float(np.sum(areas * np.repeat(depth[depth > 0], 2), dtype=np.float64))
    full_depth = np.zeros(math.prod(shape), np.float64)
    full_depth[ids] = depth
    faces = arrays["face_cells"]
    both_wet = wet_mask[faces].all(axis=1)
    level = arrays["height_m"].ravel() + full_depth
    steps = abs(level[faces[both_wet, 0]] - level[faces[both_wet, 1]])
    raster_volume = float(np.sum(depth, dtype=np.float64) * metadata["spacing_m"] ** 2)
    diagnostics = dict(wet_cell_count=int(len(wet)), represented_wet_cell_count=int(len(wet)),
                       omitted_wet_cell_count=0, omitted_wet_volume_m3=0., wet_count_coverage_fraction=1.,
                       raster_volume_m3=raster_volume, triangulated_support_volume_m3=triangle_volume,
                       volume_difference_m3=triangle_volume - raster_volume,
                       represented_area_m2=float(np.sum(areas)),
                       raster_wet_area_m2=float(len(wet) * metadata["spacing_m"] ** 2),
                       max_wet_neighbor_surface_jump_m=float(steps.max(initial=0)),
                       support_perimeter_segment_count=len(perimeter))
    if not math.isclose(triangle_volume, raster_volume, rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("triangulated native volume differs from raster storage")
    return output, diagnostics


def build_water_frame(geometry, page, *, source_page_sha256, state_index=1):
    validate_geometry(geometry)
    validate_storage(page)
    _sha(source_page_sha256)
    if type(state_index) is not int or state_index not in (0, 1):
        raise ValueError("saved state_index must be 0 or 1")
    gmeta, pmeta = geometry["metadata"], page["metadata"]
    if pmeta["hierarchy_identity"] != gmeta["hierarchy_identity"]:
        raise ValueError("saved page hierarchy identity mismatch")
    for name in STATIC:
        if not np.array_equal(page["arrays"][name], geometry["arrays"][name]):
            raise ValueError("saved page native static mismatch: " + name)
    if any(pmeta[name] != gmeta[name] for name in ("spacing_m", "origin_m_xz")):
        raise ValueError("saved page coordinate mismatch")
    depth = page["arrays"]["depth_m"][state_index, geometry["arrays"]["node_cell_ids"]]
    arrays, diagnostics = _frame_arrays(geometry, depth)
    metadata = dict(schema="single-domain-saved-water-frame-v1", algorithm=ALGORITHM,
                    geometry_identity=geometry["identity_sha256"], geometry_metadata=gmeta,
                    source_page_sha256=source_page_sha256, source_page_identity=page["identity_sha256"],
                    forcing_identity=pmeta["forcing_identity"], state_index=state_index,
                    start_s=pmeta["start_s"], end_s=pmeta["end_s"],
                    time_s=pmeta["start_s"] if state_index == 0 else pmeta["end_s"],
                    water_generated=False, candidate_bed_used=False, continuous_surface=False,
                    **FRAME_SEMANTICS,
                    coordinates=COORDINATES, **diagnostics, **{name: False for name in FLAGS})
    result = _finish(arrays, metadata)
    validate_water_frame(result)
    return result


def validate_water_frame(result):
    arrays, metadata = _check(result, "single-domain-saved-water-frame-v1")
    for name in ("geometry_identity", "source_page_sha256", "source_page_identity", "forcing_identity"):
        _sha(metadata[name])
    if any(metadata.get(name) is not False for name in ("water_generated", "candidate_bed_used", "continuous_surface")):
        raise ValueError("saved native frame semantics invalid")
    geometry_names = set(STATIC) | {"node_cell_ids", "node_xyz_m", "edge_node_indices", "bed_vertices_xyz_m", "bed_triangles",
                                  "node_engineering_boundary", "node_internal_sink", "node_receiver_uphill"}
    geometry = dict(arrays={name: arrays[name] for name in geometry_names}, metadata=metadata["geometry_metadata"],
                    identity_sha256=metadata["geometry_identity"])
    validate_geometry(geometry)
    state = metadata["state_index"]
    if (type(state) is not int or state not in (0, 1) or not math.isfinite(metadata["start_s"]) or
            metadata["end_s"] - metadata["start_s"] != 3600 or
            metadata["time_s"] != (metadata["start_s"] if state == 0 else metadata["end_s"])):
        raise ValueError("saved frame time invalid")
    expected, diagnostics = _frame_arrays(geometry, arrays["native_depth_m"])
    _equal_arrays(arrays, expected)
    if any(metadata.get(name) != value for name, value in diagnostics.items()):
        raise ValueError("saved frame coverage/volume audit invalid")
    return True


def save_geometry(path, result):
    save_bundle(path, result, validator=validate_geometry)


def save_water_frame(path, result):
    save_bundle(path, result, validator=validate_water_frame)


def _load(path, expected_sha256, expected_identity, validator):
    _sha(expected_sha256)
    _sha(expected_identity)
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validator, max_bytes=MAX_BYTES)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external surface identity mismatch")
    return result


def load_geometry(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_geometry)


def load_water_frame(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_water_frame)
