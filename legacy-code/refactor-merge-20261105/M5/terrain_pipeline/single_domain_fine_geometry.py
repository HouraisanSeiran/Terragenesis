"""Finite-window shared fine beds and locally conservative continuous water fans.

Fine channels are declared artificial capsule cuts of native bilinear terrain.
The water fan is a conservative display reconstruction of a new-bed FV state,
not a change to that state or an increase in hydraulic discretization order.
"""

import math
import re

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.basin_topology import validate_basin_hierarchy as validate_basin_hierarchy


MAX_NATIVE_CELLS = 250000
MAX_FINE_CELLS = 62500
MAX_BYTES = 256 * 1024 ** 2
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")
GEOMETRY_SCHEMA = "single-domain-fine-geometry-v1"
WATER_SCHEMA = "single-domain-fine-water-fan-v1"
COORDINATES = "physical metres [x,y,z]; x east, y up, z south; raster [z,x]"
GEOMETRY_SEMANTICS = "native bilinear corners minus protected 8m-wide 1m-deep max-union cosine capsules; shared corner-centre fans"
WATER_SEMANTICS = "corner depth=min adjacent cell depth; centre depth=3*cell depth-0.5*corner depth sum; exact per-cell fan volume"
SCOPE_SEMANTICS = dict(
    protection_semantics="any native bilinear stencil protection forbids cut; preserves original corner heights",
    boundary_semantics="explicit finite engineering window; external receiver crossings retained; no inferred upstream completion",
    fine_detail_semantics="bilinear source landform plus declared artificial channels; no new Terrain Diffusion detail",
    fv_bed_semantics="canonical 1m area mean; fan centre=3*FV bed-0.5*corner sum, so exact fan area mean equals FV bed",
)


def _sha(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("fine source SHA/identity invalid")


def _limits(window, spacing, native_shape):
    if (not isinstance(window, (list, tuple)) or len(window) != 4 or
            any(type(value) is not int for value in window) or type(spacing) not in (int, float) or spacing not in (1., 2., 4.)):
        raise ValueError("explicit integer native window and declared 1/2/4m spacing required")
    x0, x1, z0, z1 = window
    if not (0 <= x0 < x1 < native_shape[1] and 0 <= z0 < z1 < native_shape[0]):
        raise ValueError("fine window leaves native sample extent")
    lengths = ((z1 - z0) * 30., (x1 - x0) * 30.)
    if any(length / spacing % 1 for length in lengths):
        raise ValueError("fine window must contain complete cells")
    shape = tuple(int(length / spacing) for length in lengths)
    if math.prod(shape) > MAX_FINE_CELLS:
        raise ValueError("fine cell budget exceeded before allocation")
    return shape


def coarsen_cell_field(fine_field, *, factor):
    """Transfer a cell-centred extensive/intensive field by exact area mean."""
    if not isinstance(fine_field, np.ndarray) or fine_field.dtype != np.float64 or fine_field.ndim != 2:
        raise ValueError("fine cell field must be finite float64 2D")
    if type(factor) is not int or factor not in (2, 4) or any(size % factor for size in fine_field.shape):
        raise ValueError("coarsening factor must evenly divide both fine axes")
    if not np.isfinite(fine_field).all():
        raise ValueError("fine cell field nonfinite")
    rows, columns = fine_field.shape
    return fine_field.reshape(rows//factor, factor, columns//factor, factor).mean(axis=(1, 3))


def _bilinear(height, columns, rows):
    left, top = np.floor(columns).astype(np.int64), np.floor(rows).astype(np.int64)
    right, bottom = np.minimum(left + 1, height.shape[1] - 1), np.minimum(top + 1, height.shape[0] - 1)
    u, v = columns - left, rows - top
    return ((1-v) * ((1-u)*height[top, left] + u*height[top, right]) +
            v * ((1-u)*height[bottom, left] + u*height[bottom, right]))


def _stencil_mask(mask, columns, rows):
    left, top = np.floor(columns).astype(np.int64), np.floor(rows).astype(np.int64)
    right, bottom = np.minimum(left + 1, mask.shape[1] - 1), np.minimum(top + 1, mask.shape[0] - 1)
    return mask[top, left] | mask[top, right] | mask[bottom, left] | mask[bottom, right]


def _fan(corner, spacing, origin):
    rows, columns = corner.shape[0]-1, corner.shape[1]-1
    x, z = np.meshgrid(origin[0] + np.arange(columns+1)*spacing,
                       origin[1] + np.arange(rows+1)*spacing)
    centre = (corner[:-1, :-1] + corner[1:, :-1] + corner[1:, 1:] + corner[:-1, 1:]) / 4.
    corner_xyz = np.column_stack((x.ravel(), corner.ravel(), z.ravel()))
    centre_xyz = np.column_stack(((x[:-1, :-1] + spacing/2).ravel(), centre.ravel(),
                                  (z[:-1, :-1] + spacing/2).ravel()))
    grid = np.arange(corner.size, dtype=np.int64).reshape(corner.shape)
    nw = grid[:-1, :-1].ravel()
    corners = np.column_stack((nw, nw+columns+1, nw+columns+2, nw+1))
    centres = np.arange(rows*columns, dtype=np.int64) + corner.size
    triangles = np.empty((rows*columns, 4, 3), np.int64)
    triangles[:, :, 0] = corners
    triangles[:, :, 1] = corners[:, [1, 2, 3, 0]]
    triangles[:, :, 2] = centres[:, None]
    return centre, np.concatenate((corner_xyz, centre_xyz)), triangles.reshape(-1, 3), corners, centres


def _capsule_cut(world_x, world_z, selected, origin, native_shape):
    cut = np.zeros_like(world_x, dtype=np.float64)
    for first, second in selected:
        start = np.array([origin[0] + first % native_shape[1] * 30.,
                          origin[1] + first // native_shape[1] * 30.])
        end = np.array([origin[0] + second % native_shape[1] * 30.,
                        origin[1] + second // native_shape[1] * 30.])
        delta = end - start
        fraction = np.clip(((world_x-start[0])*delta[0] + (world_z-start[1])*delta[1]) / 900., 0., 1.)
        distance = np.hypot(world_x-start[0]-fraction*delta[0], world_z-start[1]-fraction*delta[1])
        capsule = np.where(distance < 4., .5*(1 + np.cos(np.pi*np.minimum(distance/4., 1.))), 0.)
        np.maximum(cut, capsule, out=cut)
    return cut


def _native_topology(height, valid, receiver):
    if (height.dtype != np.float64 or height.ndim != 2 or height.size > MAX_NATIVE_CELLS or
            not np.isfinite(height).all() or valid.dtype != bool or valid.shape != height.shape or
            receiver.dtype != np.int64 or receiver.shape != (height.size,) or
            np.any(receiver < -1) or np.any(receiver >= height.size) or np.any(receiver[~valid.ravel()] != -1)):
        raise ValueError("native fine source arrays invalid")
    source = np.flatnonzero(receiver >= 0)
    target = receiver[source]
    columns = height.shape[1]
    if (not valid.ravel()[source].all() or not valid.ravel()[target].all() or
            np.any(abs(source//columns-target//columns)+abs(source%columns-target%columns) != 1)):
        raise ValueError("native source requires valid D4 receivers")
    done = np.zeros(height.size, bool)
    for start in np.flatnonzero(valid):
        cell, path = int(start), set()
        while cell >= 0 and not done[cell]:
            if cell in path:
                raise ValueError("native receiver cycle")
            path.add(cell)
            cell = int(receiver[cell])
        done[list(path)] = True
    return source, target


def _geometry_arrays(native, metadata, selected):
    height, valid, protected, receiver = (native[name] for name in
                                        ("native_height_m", "native_valid_mask", "native_protected_mask", "native_receiver"))
    source, target = _native_topology(height, valid, receiver)
    if protected.dtype != bool or protected.shape != height.shape:
        raise ValueError("native protection shape/type invalid")
    window, spacing = metadata["native_window"], metadata["spacing_m"]
    rows, columns = _limits(window, spacing, height.shape)
    x0, x1, z0, z1 = window
    origin = metadata["native_origin_m_xz"]
    if (metadata["native_spacing_m"] != 30. or len(origin) != 2 or
            any(type(value) not in (int, float) or not math.isfinite(value) for value in origin)):
        raise ValueError("fixed native metre coordinates required")
    corner_origin = [origin[0]+x0*30., origin[1]+z0*30.]
    if (metadata["origin_m_xz"] != corner_origin or metadata["corner_origin_m_xz"] != corner_origin or
            metadata["cell_center_origin_m_xz"] != [value+spacing/2 for value in corner_origin] or
            metadata["grid_shape"] != [rows, columns]):
        raise ValueError("fine coordinate/shape binding invalid")
    local_mask = np.zeros(height.size, bool)
    coarse_x, coarse_z = np.meshgrid(np.arange(x0, x1+1), np.arange(z0, z1+1))
    node_ids = (coarse_z*height.shape[1]+coarse_x).ravel().astype(np.int64)
    if not valid.ravel()[node_ids].all():
        raise ValueError("entire finite window must have known native support")
    local_mask[node_ids] = True
    internal = local_mask[source] & local_mask[target]
    all_edges = np.column_stack((source[internal], target[internal])).astype(np.int64)
    edge_set = {tuple(pair) for pair in all_edges}
    if (selected.dtype != np.int64 or selected.ndim != 2 or selected.shape[1] != 2 or
            len(selected) > len(all_edges) or len({tuple(pair) for pair in selected}) != len(selected) or
            any(tuple(pair) not in edge_set for pair in selected)):
        raise ValueError("selected edge cells must be unique internal native receiver links")
    if len(selected) and not np.array_equal(selected, selected[np.lexsort((selected[:, 1], selected[:, 0]))]):
        raise ValueError("selected edge cells must be sorted")
    lattice_x, lattice_z = np.meshgrid(np.arange(columns+1), np.arange(rows+1))
    native_x, native_z = x0+lattice_x*spacing/30., z0+lattice_z*spacing/30.
    if _stencil_mask(~valid, native_x, native_z).any():
        raise ValueError("unknown native bilinear stencil in finite window")
    original = _bilinear(height, native_x, native_z)
    protection = _stencil_mask(protected, native_x, native_z)
    world_x, world_z = corner_origin[0]+lattice_x*spacing, corner_origin[1]+lattice_z*spacing
    cut = _capsule_cut(world_x, world_z, selected, origin, height.shape)
    cut[protection] = 0.
    channel = cut > 0
    bank = np.zeros_like(channel)
    bank[:, :-1] |= channel[:, 1:]
    bank[:, 1:] |= channel[:, :-1]
    bank[:-1, :] |= channel[1:, :]
    bank[1:, :] |= channel[:-1, :]
    bank &= ~channel
    bed_corner = original-cut
    bed_centre, vertices, triangles, corners, centres = _fan(bed_corner, spacing, corner_origin)
    fine_x, fine_z = np.meshgrid(corner_origin[0] + np.arange(columns * int(spacing)) + .5,
                                 corner_origin[1] + np.arange(rows * int(spacing)) + .5)
    reference_cut = _capsule_cut(fine_x, fine_z, selected, origin, height.shape)
    reference_source_x, reference_source_z = np.meshgrid(
        x0 + (np.arange(columns * int(spacing)) + .5) / 30.,
        z0 + (np.arange(rows * int(spacing)) + .5) / 30.)
    reference_source = _bilinear(height, reference_source_x, reference_source_z)
    reference_source = np.asarray(reference_source)
    reference_protection = _stencil_mask(protected, reference_source_x, reference_source_z)
    reference_cut[reference_protection] = 0.
    canonical_bed_center = reference_source - reference_cut
    if spacing == 1.:
        integrated_bed = canonical_bed_center
    else:
        factor = int(spacing)
        integrated_bed = canonical_bed_center.reshape(rows, factor, columns, factor).mean(axis=(1, 3))
    bed_centre = integrated_bed
    corner_sum = bed_corner[:-1, :-1]+bed_corner[1:, :-1]+bed_corner[1:, 1:]+bed_corner[:-1, 1:]
    fan_centre = 3*bed_centre-.5*corner_sum
    vertices[centres, 1] = fan_centre.ravel()
    # Coarse nodes land on corners or half-cell positions for the declared 1/2/4m grids.
    node_x, node_z = (node_ids%height.shape[1]-x0)*30./spacing, (node_ids//height.shape[1]-z0)*30./spacing
    node_bed = _bilinear(bed_corner, node_x, node_z)
    node_left, node_top = np.floor(node_x).astype(np.int64), np.floor(node_z).astype(np.int64)
    at_fan_centre = ((node_x-node_left == .5) & (node_z-node_top == .5))
    node_bed[at_fan_centre] = fan_centre[node_top[at_fan_centre], node_left[at_fan_centre]]
    node_xyz = np.column_stack((origin[0]+node_ids%height.shape[1]*30., node_bed,
                                origin[1]+node_ids//height.shape[1]*30.))
    outbound = np.column_stack((source[local_mask[source] & ~local_mask[target]], target[local_mask[source] & ~local_mask[target]])).astype(np.int64)
    inbound = np.column_stack((source[~local_mask[source] & local_mask[target]], target[~local_mask[source] & local_mask[target]])).astype(np.int64)
    native_target = receiver[node_ids]
    return dict(native, selected_edge_cell_ids=selected.copy(), node_cell_ids=node_ids,
                node_receiver_cell_ids=native_target.copy(), node_xyz_m=node_xyz,
                edge_node_indices=np.searchsorted(node_ids, selected).astype(np.int64),
                internal_sink_mask=native_target < 0, outgoing_boundary_edge_cell_ids=outbound,
                incoming_boundary_edge_cell_ids=inbound, all_internal_edge_cell_ids=all_edges,
                native_bilinear_corner_m=original, canonical_bed_center_m=canonical_bed_center,
                canonical_cut_center_m=reference_cut, canonical_protected_center_mask=reference_protection,
                protected_corner_mask=protection,
                artificial_channel_corner_mask=channel, artificial_bank_corner_mask=bank,
                cut_corner_m=cut, bed_corner_m=bed_corner, bed_center_m=bed_centre, H2_m=bed_centre.copy(),
                bed_fan_center_m=fan_centre,
                bed_vertices_xyz_m=vertices, bed_triangles=triangles,
                cell_corner_vertex_ids=corners, cell_center_vertex_ids=centres,
                cell_fan_vertex_ids=np.column_stack((corners, centres)))


def _freeze(arrays, metadata):
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("fine artifact byte budget exceeded")
    return dict(arrays={name: readonly(value) for name, value in arrays.items()}, metadata=metadata,
                identity_sha256=identity(arrays, metadata))


def build_fine_geometry(hierarchy, *, native_window, source_hierarchy_sha256, spacing_m=1.,
                        selected_edge_cell_ids=None, width_m=8., incision_m=1.):
    validate_basin_hierarchy(hierarchy)
    _sha(source_hierarchy_sha256)
    if width_m != 8. or incision_m != 1. or hierarchy["metadata"]["spacing_m"] != 30.:
        raise ValueError("declared native 30m / width8m / incision1m recipe required")
    source = hierarchy["arrays"]
    rows, columns = _limits(native_window, spacing_m, source["height_m"].shape)
    x0, _, z0, _ = native_window
    native_origin = list(hierarchy["metadata"]["origin_m_xz"])
    corner_origin = [native_origin[0]+x0*30., native_origin[1]+z0*30.]
    metadata = dict(schema=GEOMETRY_SCHEMA, algorithm="protected-native-canonical-integral-fan-v2", coordinates=COORDINATES,
                    representation=GEOMETRY_SEMANTICS, hierarchy_identity=hierarchy["identity_sha256"],
                    source_hierarchy_sha256=source_hierarchy_sha256,
                    source_identity=hierarchy["metadata"]["source_identity_sha256"],
                    native_window=list(native_window), native_spacing_m=30., native_origin_m_xz=native_origin,
                    grid_shape=[rows, columns], spacing_m=float(spacing_m), origin_m_xz=corner_origin,
                    corner_origin_m_xz=corner_origin, cell_center_origin_m_xz=[value+spacing_m/2 for value in corner_origin],
                    width_m=8., incision_m=1., water_generated=False, artificial_channels=True,
                    natural_banks_verified=False, full_native_domain_covered=False,
                    **SCOPE_SEMANTICS,
                    **{name: False for name in FLAGS})
    native = dict(native_height_m=source["height_m"].copy(), native_valid_mask=source["valid_mask"].copy(),
                  native_protected_mask=source["protected_mask"].copy(), native_receiver=source["receiver"].copy())
    if selected_edge_cell_ids is None:
        ids = np.arange(source["height_m"].size)
        target = source["receiver"]
        mask = (ids%source["height_m"].shape[1] >= native_window[0]) & (ids%source["height_m"].shape[1] <= native_window[1])
        mask &= (ids//source["height_m"].shape[1] >= native_window[2]) & (ids//source["height_m"].shape[1] <= native_window[3])
        internal = (target >= 0) & mask
        internal[internal] &= mask[target[internal]]
        selected = np.column_stack((ids[internal], target[internal])).astype(np.int64)
    else:
        selected = np.asarray(selected_edge_cell_ids)
        if selected.dtype != np.int64:
            raise ValueError("selected native edges require int64")
        selected = selected.reshape(-1, 2)
    arrays = _geometry_arrays(native, metadata, selected)
    metadata["cut_volume_m3"] = float(np.sum(arrays["canonical_cut_center_m"], dtype=np.float64))
    metadata["maximum_cut_m"] = float(arrays["cut_corner_m"].max(initial=0))
    corners = arrays["bed_corner_m"]
    corner_stack = np.stack((corners[:-1, :-1], corners[1:, :-1], corners[1:, 1:], corners[:-1, 1:]))
    fan = arrays["bed_fan_center_m"]
    cut = arrays["cut_corner_m"]
    corner_cut_mean = (cut[:-1, :-1]+cut[1:, :-1]+cut[1:, 1:]+cut[:-1, 1:])/4
    metadata.update(hydraulic_integral_cut_volume_m3=metadata["cut_volume_m3"],
        corner_trapezoid_cut_volume_m3=float(corner_cut_mean.sum()*spacing_m**2),
        fan_center_minimum_elevation_m=float(fan.min()),
        fan_center_maximum_elevation_m=float(fan.max()),
        fan_center_maximum_corner_undershoot_m=float(np.maximum(corner_stack.min(axis=0)-fan, 0.).max(initial=0)),
        fan_center_maximum_corner_overshoot_m=float(np.maximum(fan-corner_stack.max(axis=0), 0.).max(initial=0)),
        fan_center_maximum_corner_mean_correction_m=float(abs(fan-corner_stack.mean(axis=0)).max(initial=0)),
        hydraulic_cut_semantics="integral of canonical protected 1m center incision; cell mean and fan triangle integral agree",
        fan_shape_limitation="integral correction may create center excursions beyond adjacent corner range")
    result = _freeze(arrays, metadata)
    validate_fine_geometry(result)
    return result


def _check(result, schema):
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata.get("schema") != schema or metadata.get("coordinates") != COORDINATES or
            any(metadata.get(name) is not False for name in FLAGS) or
            result["identity_sha256"] != identity(arrays, metadata)):
        raise ValueError("fine schema/coordinates/certification/identity mismatch")
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES or any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("fine nonfinite/byte budget invalid")
    return arrays, metadata


def _equal(actual, expected):
    if set(actual) != set(expected):
        raise ValueError("fine array fields mismatch")
    for name, value in expected.items():
        if actual[name].dtype != value.dtype or not np.array_equal(actual[name], value):
            raise ValueError("fine source/derivation mismatch: " + name)


def validate_fine_geometry(result):
    arrays, metadata = _check(result, GEOMETRY_SCHEMA)
    if (metadata.get("algorithm") != "protected-native-canonical-integral-fan-v2" or
            metadata.get("representation") != GEOMETRY_SEMANTICS or metadata.get("width_m") != 8. or
            metadata.get("incision_m") != 1. or metadata.get("natural_banks_verified") is not False or
            metadata.get("water_generated") is not False or metadata.get("artificial_channels") is not True or
            metadata.get("full_native_domain_covered") is not False or
            any(metadata.get(name) != value for name, value in SCOPE_SEMANTICS.items())):
        raise ValueError("fine artificial recipe/scope invalid")
    for name in ("hierarchy_identity", "source_hierarchy_sha256", "source_identity"):
        _sha(metadata[name])
    height, valid, protected, receiver = (arrays[name] for name in
        ("native_height_m", "native_valid_mask", "native_protected_mask", "native_receiver"))
    sources, targets = _native_topology(height, valid, receiver)
    rows, columns = _limits(metadata["native_window"], metadata["spacing_m"], height.shape)
    spacing = metadata["spacing_m"]
    corner = arrays["bed_corner_m"]
    canonical = arrays["canonical_bed_center_m"]
    expected_shapes = dict(native_bilinear_corner_m=(rows+1,columns+1),protected_corner_mask=(rows+1,columns+1),
        cut_corner_m=(rows+1,columns+1),bed_corner_m=(rows+1,columns+1),bed_center_m=(rows,columns),H2_m=(rows,columns),
        bed_fan_center_m=(rows,columns),canonical_bed_center_m=(rows*int(spacing),columns*int(spacing)),
        canonical_cut_center_m=(rows*int(spacing),columns*int(spacing)),canonical_protected_center_mask=(rows*int(spacing),columns*int(spacing)))
    if any(arrays[name].shape != shape for name,shape in expected_shapes.items()):
        raise ValueError("fine saved lattice field shape mismatch")
    if (np.any(arrays["cut_corner_m"] < 0) or np.any(arrays["cut_corner_m"] > 1) or
            np.any(arrays["canonical_cut_center_m"] < 0) or np.any(arrays["canonical_cut_center_m"] > 1) or
            np.any(arrays["cut_corner_m"][arrays["protected_corner_mask"]] != 0) or
            np.any(arrays["canonical_cut_center_m"][arrays["canonical_protected_center_mask"]] != 0) or
            not np.array_equal(corner,arrays["native_bilinear_corner_m"]-arrays["cut_corner_m"])):
        raise ValueError("fine saved protection/no-fill relation invalid")
    expected_bed = canonical if spacing == 1. else coarsen_cell_field(canonical, factor=int(spacing))
    if not np.array_equal(arrays["H2_m"],expected_bed) or not np.array_equal(arrays["bed_center_m"],expected_bed):
        raise ValueError("fine saved canonical area restriction invalid")
    corner_sum = corner[:-1,:-1]+corner[1:,:-1]+corner[1:,1:]+corner[:-1,1:]
    if not np.array_equal(arrays["bed_fan_center_m"],3*expected_bed-.5*corner_sum):
        raise ValueError("fine saved triangle fan area mean invalid")
    _,vertices,triangles,corners,centres = _fan(corner,spacing,metadata["origin_m_xz"])
    vertices[centres,1] = arrays["bed_fan_center_m"].ravel()
    for name,expected in (("bed_vertices_xyz_m",vertices),("bed_triangles",triangles),
                          ("cell_corner_vertex_ids",corners),("cell_center_vertex_ids",centres),
                          ("cell_fan_vertex_ids",np.column_stack((corners,centres)))):
        if not np.array_equal(arrays[name],expected):
            raise ValueError("fine saved shared lattice/fan topology mismatch: "+name)
    x0,x1,z0,z1 = metadata["native_window"]
    local = np.zeros(height.size,bool)
    node_x,node_z = np.meshgrid(np.arange(x0,x1+1),np.arange(z0,z1+1))
    node_ids = (node_z*height.shape[1]+node_x).ravel().astype(np.int64)
    local[node_ids] = True
    expected_all = np.column_stack((sources[local[sources]&local[targets]],targets[local[sources]&local[targets]]))
    selected = arrays["selected_edge_cell_ids"]
    if (selected.dtype != np.int64 or selected.shape != (len(selected),2) or
            len({tuple(pair) for pair in selected}) != len(selected) or
            any(tuple(pair) not in {tuple(pair) for pair in expected_all} for pair in selected)):
        raise ValueError("fine saved selected native topology invalid")
    expected_out = np.column_stack((sources[local[sources]&~local[targets]],targets[local[sources]&~local[targets]]))
    expected_in = np.column_stack((sources[~local[sources]&local[targets]],targets[~local[sources]&local[targets]]))
    for name,expected in (("node_cell_ids",node_ids),("node_receiver_cell_ids",receiver[node_ids]),
        ("edge_node_indices",np.searchsorted(node_ids,selected)),("internal_sink_mask",receiver[node_ids]<0),
        ("all_internal_edge_cell_ids",expected_all),("outgoing_boundary_edge_cell_ids",expected_out),
        ("incoming_boundary_edge_cell_ids",expected_in)):
        if not np.array_equal(arrays[name],expected):
            raise ValueError("fine saved receiver/boundary relation invalid")
    fx,fz = (node_ids%height.shape[1]-x0)*30./spacing,(node_ids//height.shape[1]-z0)*30./spacing
    node_bed = _bilinear(corner,fx,fz)
    left,top = np.floor(fx).astype(np.int64),np.floor(fz).astype(np.int64)
    at_centre = (fx-left == .5)&(fz-top == .5)
    node_bed[at_centre] = arrays["bed_fan_center_m"][top[at_centre],left[at_centre]]
    expected_xyz = np.column_stack((metadata["origin_m_xz"][0]+fx*spacing,node_bed,metadata["origin_m_xz"][1]+fz*spacing))
    if not np.array_equal(arrays["node_xyz_m"],expected_xyz):
        raise ValueError("fine saved shared junction XYZ mismatch")
    cut = arrays["cut_corner_m"]
    if (metadata["cut_volume_m3"] != float(np.sum(arrays["canonical_cut_center_m"], dtype=np.float64)) or
            metadata["maximum_cut_m"] != float(cut.max(initial=0))):
        raise ValueError("fine cut volume audit invalid")
    return True


def _water_arrays(geometry, depth):
    source, meta = geometry["arrays"], geometry["metadata"]
    shape = source["H2_m"].shape
    if depth.dtype != np.float64 or depth.shape != shape or not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError("new-bed fine cell depth invalid")
    corner_depth = np.full((shape[0]+1, shape[1]+1), np.inf)
    for selection in (np.s_[:-1, :-1], np.s_[1:, :-1], np.s_[1:, 1:], np.s_[:-1, 1:]):
        np.minimum(corner_depth[selection], depth, out=corner_depth[selection])
    sums = corner_depth[:-1, :-1]+corner_depth[1:, :-1]+corner_depth[1:, 1:]+corner_depth[:-1, 1:]
    centre_depth = 3*depth-.5*sums
    if np.any(centre_depth < 0):
        raise ValueError("conservative water centre depth negative")
    vertex_depth = np.concatenate((corner_depth.ravel(), centre_depth.ravel()))
    vertices = source["bed_vertices_xyz_m"].copy()
    vertices[:, 1] += vertex_depth
    wet_ids = np.flatnonzero(depth.ravel() > 0).astype(np.int64)
    triangles = source["bed_triangles"].reshape(-1, 4, 3)[wet_ids].reshape(-1, 3).copy()
    # Integrate from geometric triangle support, preserving each cell independently.
    points = vertices[source["bed_triangles"]][:, :, [0, 2]]
    delta1, delta2 = points[:, 1]-points[:, 0], points[:, 2]-points[:, 0]
    area = abs(delta1[:, 0]*delta2[:, 1]-delta1[:, 1]*delta2[:, 0])/2
    volumes = (area*vertex_depth[source["bed_triangles"]].mean(axis=1)).reshape(-1, 4).sum(axis=1).reshape(shape)
    fv_volume = depth*meta["spacing_m"]**2
    discrepancy = volumes-fv_volume
    if not np.allclose(discrepancy, 0., rtol=0., atol=1e-10):
        raise ValueError("continuous fan per-cell volume differs from new-bed FV state")
    corner_stage = source["bed_corner_m"]+corner_depth
    centre_stage = source["bed_fan_center_m"]+centre_depth
    fv_stage = source["H2_m"]+depth
    corner_offsets = np.stack((corner_stage[:-1, :-1], corner_stage[1:, :-1],
                               corner_stage[1:, 1:], corner_stage[:-1, 1:]), axis=-1)-fv_stage[:, :, None]
    diagnostics = dict(raster_volume_m3=float(np.sum(fv_volume, dtype=np.float64)),
                       triangulated_volume_m3=float(np.sum(volumes, dtype=np.float64)),
                       max_cell_volume_difference_m3=float(abs(discrepancy).max(initial=0)),
                       wet_cell_count=int(len(wet_ids)), represented_wet_cell_count=int(len(wet_ids)),
                       omitted_wet_cell_count=0, minimum_vertex_depth_m=float(vertex_depth.min(initial=0)),
                       max_center_stage_offset_m=float(abs(centre_stage-fv_stage).max(initial=0)),
                       max_corner_stage_offset_m=float(abs(corner_offsets).max(initial=0)))
    arrays = {name: value.copy() for name, value in source.items()}
    arrays.update(cell_depth_m=depth.copy(), corner_depth_m=corner_depth, center_depth_m=centre_depth,
                  water_vertices_xyz_m=vertices, water_triangles=triangles, wet_cell_ids=wet_ids,
                  cell_volume_m3=volumes)
    return arrays, diagnostics


def build_fine_water_frame(geometry, states, *, state_index):
    """Consume an identity-bound saved new-bed hydraulic state, never native water."""
    validate_fine_geometry(geometry)
    if (states["identity_sha256"] != identity(states["arrays"], states["metadata"]) or
            states["metadata"].get("bed_identity") != geometry["identity_sha256"] or
            states["metadata"].get("schema") != "single-domain-fine-states-v1"):
        raise ValueError("saved new-bed hydraulic state binding invalid")
    times = states["arrays"]["time_s"]
    if type(state_index) is not int or not 0 <= state_index < len(times):
        raise ValueError("saved fine state index invalid")
    depth = states["arrays"]["depth_m"][state_index].reshape(geometry["arrays"]["H2_m"].shape)
    arrays, diagnostics = _water_arrays(geometry, depth)
    metadata = dict(schema=WATER_SCHEMA, algorithm="per-cell-conservative-shared-water-fan-v1", coordinates=COORDINATES,
                    representation=WATER_SEMANTICS, bed_identity=geometry["identity_sha256"],
                    geometry_metadata=geometry["metadata"], hydraulic_state_identity=states["identity_sha256"],
                    state_index=state_index, time_s=float(times[state_index]), water_generated=False,
                    continuous_shared_surface=True, reconstruction_order_claim="conservative visualization only; no hydraulic order claim",
                    limitation="centre depth may reach 3x FV cell depth; shared corner/centre stage differs from FV cell stage",
                    **diagnostics, **{name: False for name in FLAGS})
    result = _freeze(arrays, metadata)
    validate_fine_water_frame(result)
    return result


def validate_fine_water_frame(result):
    arrays, metadata = _check(result, WATER_SCHEMA)
    if (metadata.get("algorithm") != "per-cell-conservative-shared-water-fan-v1" or
            metadata.get("representation") != WATER_SEMANTICS or metadata.get("water_generated") is not False or
            metadata.get("continuous_shared_surface") is not True or
            metadata.get("reconstruction_order_claim") != "conservative visualization only; no hydraulic order claim" or
            metadata.get("limitation") != "centre depth may reach 3x FV cell depth; shared corner/centre stage differs from FV cell stage"):
        raise ValueError("fine water conservative reconstruction semantics invalid")
    for name in ("bed_identity", "hydraulic_state_identity"):
        _sha(metadata[name])
    if type(metadata["state_index"]) is not int or metadata["state_index"] < 0 or not math.isfinite(metadata["time_s"]):
        raise ValueError("fine water saved time invalid")
    extra = {"cell_depth_m", "corner_depth_m", "center_depth_m", "water_vertices_xyz_m", "water_triangles", "wet_cell_ids", "cell_volume_m3"}
    geometry = dict(arrays={name: value for name, value in arrays.items() if name not in extra},
                    metadata=metadata["geometry_metadata"], identity_sha256=metadata["bed_identity"])
    validate_fine_geometry(geometry)
    expected, diagnostics = _water_arrays(geometry, arrays["cell_depth_m"])
    _equal(arrays, expected)
    if any(metadata.get(name) != value for name, value in diagnostics.items()):
        raise ValueError("fine water per-cell volume/stage diagnostics invalid")
    return True


def save_fine_geometry(path, result):
    save_bundle(path, result, validator=validate_fine_geometry)


def save_fine_water_frame(path, result):
    save_bundle(path, result, validator=validate_fine_water_frame)


def _load(path, expected_sha256, expected_identity, validator):
    _sha(expected_sha256)
    _sha(expected_identity)
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validator, max_bytes=MAX_BYTES)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external fine identity mismatch")
    return result


def load_fine_geometry(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_fine_geometry)


def load_fine_water_frame(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_fine_water_frame)


SUBGRID_MODEL = "canonical-subcell-storage-segmented-face-local-inertia-v1"


def prepare_subgrid_support(bed):
    """Canonical bed samples define coarse hypsometry and segmented face support."""
    canonical = bed["arrays"]["canonical_bed_center_m"]
    rows, columns = bed["arrays"]["H2_m"].shape
    factor = int(bed["metadata"]["spacing_m"])
    if canonical.shape != (rows*factor, columns*factor):
        raise ValueError("canonical subcell support shape mismatch")
    datum = float(canonical.min())
    relative = canonical-datum
    subbed = relative.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows*columns, factor**2)
    subbed = np.sort(subbed, axis=1)
    prefix = np.cumsum(subbed, axis=1)
    x_support = np.maximum(relative[:, :-1], relative[:, 1:])[:, factor-1::factor]
    x_support = x_support.reshape(rows, factor, columns-1).transpose(0, 2, 1).reshape(-1, factor)
    z_support = np.maximum(relative[:-1], relative[1:])[factor-1::factor]
    z_support = z_support.reshape(rows-1, columns, factor).reshape(-1, factor)
    boundary = np.concatenate((relative[:, 0].reshape(rows, factor), relative[:, -1].reshape(rows, factor),
                               relative[0].reshape(columns, factor), relative[-1].reshape(columns, factor)))
    return dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=prefix,
                face_segment_crest_relative_m=np.concatenate((x_support, z_support)),
                boundary_segment_crest_relative_m=boundary), datum


def storage_stages(mean_depth_m, subcell_bed_relative_m, subcell_prefix_relative_m):
    """Invert V=sum(max(stage-z,0)) for each independently solved coarse cell."""
    depth = np.asarray(mean_depth_m).ravel()
    bed, prefix = subcell_bed_relative_m, subcell_prefix_relative_m
    if depth.dtype != np.float64 or depth.shape != (len(bed),) or np.any(depth < 0):
        raise ValueError("subgrid mean volume depth invalid")
    count = bed.shape[1]
    volume = depth*count
    levels_volume = np.arange(1, count+1)[None, :]*bed-prefix
    wet_count = np.maximum(np.sum(volume[:, None] >= levels_volume, axis=1), 1)
    positions = np.arange(len(depth))
    return (volume+prefix[positions, wet_count-1])/wet_count


def stage_depths(relative_stage_m, subcell_bed_relative_m):
    return np.maximum(relative_stage_m[:, None]-subcell_bed_relative_m, 0.).mean(axis=1)


def segmented_flux(geometry, depth, internal_before, boundary_before, tailwater, forcing, dt_s, budget):
    """Pure coarse local-inertia momentum and donor limiter; no execution imports."""
    arrays, meta = geometry["arrays"], geometry["metadata"]
    stage = storage_stages(depth, arrays["subcell_bed_relative_m"], arrays["subcell_prefix_relative_m"])
    left, right, cells = arrays["face_left"], arrays["face_right"], arrays["boundary_cell"]
    spacing, datum = meta["spacing_m"], meta["hydraulic_datum_m"]
    exterior = np.broadcast_to((tailwater-datum)[:, None], boundary_before.shape).copy()
    exterior[arrays["boundary_kind"] == 1] = arrays["boundary_segment_crest_relative_m"][arrays["boundary_kind"] == 1]

    def momentum(first, second, crests, previous, distance):
        if second.ndim == 1:
            second = second[:, None]
        flow_depth = np.maximum(np.maximum(first[:, None], second)-crests, 0.)
        wet = flow_depth > 0
        rhs = previous-budget.gravity_m_s2*flow_depth*dt_s*(second-first[:, None])/distance
        drag = np.zeros_like(flow_depth)
        drag[wet] = budget.gravity_m_s2*dt_s*budget.roughness_s_m_third**2/flow_depth[wet]**(7/3)
        result = np.zeros_like(previous)
        result[wet] = 2*rhs[wet]/(1+np.sqrt(1+4*drag[wet]*abs(rhs[wet])))
        return result

    internal = momentum(stage[left], stage[right], arrays["face_segment_crest_relative_m"], internal_before, spacing)
    boundary = momentum(stage[cells], exterior, arrays["boundary_segment_crest_relative_m"], boundary_before, spacing/2)
    boundary[arrays["boundary_kind"] == 0] = 0.
    outgoing = np.bincount(left, weights=np.maximum(internal, 0).sum(axis=1), minlength=len(depth))
    outgoing += np.bincount(right, weights=np.maximum(-internal, 0).sum(axis=1), minlength=len(depth))
    outgoing += np.bincount(cells, weights=np.maximum(boundary, 0).sum(axis=1), minlength=len(depth))
    available = depth*spacing**2+dt_s*forcing
    limited = outgoing*dt_s > available
    factors = np.ones(len(depth))
    factors[limited] = available[limited]/(outgoing[limited]*dt_s)*(1-1e-12)
    raw_internal, raw_boundary = internal.copy(), boundary.copy()
    internal *= np.where(internal >= 0, factors[left, None], factors[right, None])
    boundary *= np.where(boundary >= 0, factors[cells, None], 1.)
    limiter = dict(limited_donors=int(np.count_nonzero(limited)),
                   minimum_scale=float(factors.min(initial=1)),
                   limited_volume_m3=float(dt_s*(abs(raw_internal-internal).sum()+abs(raw_boundary-boundary).sum())))
    return internal, boundary, limiter
