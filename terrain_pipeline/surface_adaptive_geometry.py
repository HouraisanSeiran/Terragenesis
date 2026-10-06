"""One finite-domain 4/2/1 m leaf partition with unique canonical face segments."""

import hashlib
import json

import numpy as np
from numba import njit

MODEL = "single-domain-adaptive-canonical-HLL-Manning-SSPRK2-v1"


@njit(cache=True, fastmath=False)
def _aligned_partition(requested):
    rows, columns = requested.shape
    leaves = np.empty((requested.size, 3), np.int64)
    count = 0
    for row in range(0, rows, 4):
        for column in range(0, columns, 4):
            if requested[row:row+4, column:column+4].min() >= 4:
                leaves[count] = (row, column, 4)
                count += 1
                continue
            for dz in (0, 2):
                for dx in (0, 2):
                    r, c = row+dz, column+dx
                    if requested[r:r+2, c:c+2].min() >= 2:
                        leaves[count] = (r, c, 2)
                        count += 1
                    else:
                        for fine_z in (0, 1):
                            for fine_x in (0, 1):
                                leaves[count] = (r+fine_z, c+fine_x, 1)
                                count += 1
    return leaves[:count].copy()


@njit(cache=True, fastmath=False)
def _compact_support(bed, leaves, offsets, datum):
    owner = np.full(bed.shape, -1, np.int64)
    sorted_bed = np.zeros(bed.size)
    prefix = np.zeros(bed.size)
    for index in range(len(leaves)):
        row, column, size = leaves[index]
        samples = np.empty(size*size)
        position = 0
        for dz in range(size):
            for dx in range(size):
                owner[row+dz, column+dx] = index
                samples[position] = bed[row+dz, column+dx]-datum
                position += 1
        samples.sort()
        total = 0.
        for position in range(size*size):
            sorted_bed[offsets[index]+position] = samples[position]
            total += samples[position]
            prefix[offsets[index]+position] = total
    return owner, sorted_bed, prefix


@njit(cache=True, fastmath=False)
def _coverage_valid(owner, leaf_row, leaf_column, leaf_spacing):
    coverage = np.zeros_like(owner)
    for cell in range(len(leaf_row)):
        row, column, size = leaf_row[cell], leaf_column[cell], leaf_spacing[cell]
        for dz in range(size):
            for dx in range(size):
                if owner[row+dz, column+dx] != cell:
                    return False
                coverage[row+dz, column+dx] += 1
    return np.all(coverage == 1)


def adaptive_geometry_identity(arrays, metadata):
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode("ascii"))
    for name in sorted(arrays):
        value = arrays[name]
        digest.update(name.encode("ascii"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(np.asarray(value.shape, np.int64).tobytes())
        digest.update(value.tobytes())
    return digest.hexdigest()


def build_adaptive_geometry(canonical_bed_m, requested_spacing_m, *, origin_m_xz=(0., 0.),
                            boundary_kind=None, boundary_crest_m=None):
    bed = np.asarray(canonical_bed_m)
    requested = np.asarray(requested_spacing_m)
    if (bed.dtype != np.float64 or bed.ndim != 2 or not np.isfinite(bed).all() or
            bed.shape[0] % 4 or bed.shape[1] % 4 or requested.shape != bed.shape or
            not np.isin(requested, [1, 2, 4]).all()):
        raise ValueError("finite 1m canonical bed, multiples-of-four extent and explicit 1/2/4m spacing map required")
    rows, columns = bed.shape
    leaves = _aligned_partition(requested)
    count = len(leaves)
    datum = float(bed.min())
    offsets = np.r_[0, np.cumsum(leaves[:-1, 2]**2)].astype(np.int64)
    owner, sorted_bed, prefix = _compact_support(bed, leaves, offsets, datum)
    left_x, right_x = owner[:, :-1], owner[:, 1:]
    left_z, right_z = owner[:-1], owner[1:]
    mask_x, mask_z = left_x != right_x, left_z != right_z
    zx, xx = np.nonzero(mask_x)
    zz, xz = np.nonzero(mask_z)
    left = np.r_[left_x[mask_x], left_z[mask_z]]
    right = np.r_[right_x[mask_x], right_z[mask_z]]
    axis = np.r_[np.zeros(mask_x.sum(), np.int64), np.ones(mask_z.sum(), np.int64)]
    crest = np.r_[np.maximum(bed[:, :-1], bed[:, 1:])[mask_x], np.maximum(bed[:-1], bed[1:])[mask_z]]-datum
    boundary_cells = np.r_[owner[:, 0], owner[:, -1], owner[0], owner[-1]]
    boundary_bed = np.r_[bed[:, 0], bed[:, -1], bed[0], bed[-1]]
    kinds = np.zeros(len(boundary_cells), np.int64) if boundary_kind is None else np.asarray(boundary_kind)
    boundary_crest = boundary_bed.copy() if boundary_crest_m is None else np.asarray(boundary_crest_m)
    if (kinds.dtype != np.int64 or kinds.shape != boundary_cells.shape or not np.isin(kinds, [0, 1, 2]).all() or
            boundary_crest.dtype != np.float64 or boundary_crest.shape != boundary_cells.shape or
            not np.isfinite(boundary_crest).all() or np.any(boundary_crest < boundary_bed)):
        raise ValueError("complete canonical boundary kind and finite no-lower crest required")
    arrays = dict(canonical_bed_m=bed.copy(), requested_spacing_m=requested.astype(np.int64), leaf_row=leaves[:, 0],
        leaf_column=leaves[:, 1], leaf_spacing_m=leaves[:, 2], leaf_area_m2=leaves[:, 2].astype(np.float64)**2,
        canonical_owner=owner, subcell_count=leaves[:, 2]**2, subcell_offset=offsets, sorted_subcell_bed_relative_m=sorted_bed,
        prefix_subcell_bed_relative_m=prefix, face_left=left, face_right=right, face_axis=axis,
        face_canonical_row=np.r_[zx, zz+1], face_canonical_column=np.r_[xx+1, xz], face_crest_relative_m=crest,
        boundary_cell=boundary_cells, boundary_axis=np.r_[np.zeros(2*rows, np.int64), np.ones(2*columns, np.int64)],
        boundary_sign=np.r_[-np.ones(rows), np.ones(rows), -np.ones(columns), np.ones(columns)],
        boundary_kind=kinds.copy(), boundary_crest_m=boundary_crest.copy(), boundary_bed_relative_m=boundary_bed-datum)
    metadata = dict(model=MODEL, origin_m_xz=list(origin_m_xz), canonical_shape=list(bed.shape), hydraulic_datum_m=datum,
        finest_spacing_m=int(leaves[:, 2].min()), leaf_counts={str(size): int(np.sum(leaves[:, 2] == size)) for size in (1, 2, 4)},
        leaf_area_m2={str(size): int(np.sum(leaves[:, 2] == size))*size**2 for size in (1, 2, 4)},
        leaf_count=count, total_area_m2=bed.size, internal_segment_count=len(left), boundary_segment_count=len(boundary_cells),
        face_length_m=1., full_selected_window_covered=True, uniform_coarse_convergence_claim=False)
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=adaptive_geometry_identity(arrays, metadata))
    validate_adaptive_geometry(result)
    return result


def validate_adaptive_geometry(geometry):
    a = geometry["arrays"]
    owner = a["canonical_owner"]
    if not _coverage_valid(owner, a["leaf_row"], a["leaf_column"], a["leaf_spacing_m"]) or int(a["leaf_area_m2"].sum()) != owner.size:
        raise ValueError("canonical tiles must be covered exactly once")
    tuples = np.column_stack((a["face_axis"], a["face_canonical_row"], a["face_canonical_column"]))
    if len(np.unique(tuples, axis=0)) != len(tuples):
        raise ValueError("internal canonical segments must be unique")
    expected = int(np.sum(owner[:, :-1] != owner[:, 1:])+np.sum(owner[:-1] != owner[1:]))
    if len(tuples) != expected or np.any(a["face_left"] == a["face_right"]):
        raise ValueError("all neighboring leaves must share exactly one canonical segment per interface position")
    for axis in (0, 1):
        mask = a["face_axis"] == axis
        row, column = a["face_canonical_row"][mask], a["face_canonical_column"][mask]
        first = owner[row, column-1] if axis == 0 else owner[row-1, column]
        second = owner[row, column]
        if not np.array_equal(first, a["face_left"][mask]) or not np.array_equal(second, a["face_right"][mask]):
            raise ValueError("canonical segment incidence invalid")
    return True


def initial_leaf_state(geometry, canonical_depth_m, canonical_momentum=None):
    a = geometry["arrays"]
    depth = np.asarray(canonical_depth_m)
    if depth.dtype != np.float64 or depth.shape != a["canonical_owner"].shape or not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError("finite nonnegative canonical initial depth required")
    momentum = np.zeros((*depth.shape, 2)) if canonical_momentum is None else np.asarray(canonical_momentum)
    if momentum.shape != (*depth.shape, 2) or not np.isfinite(momentum).all():
        raise ValueError("finite canonical initial momentum required")
    owner, area = a["canonical_owner"].ravel(), a["leaf_area_m2"]
    return np.column_stack((np.bincount(owner, weights=depth.ravel(), minlength=len(area))/area,
        np.bincount(owner, weights=momentum[:, :, 0].ravel(), minlength=len(area))/area,
        np.bincount(owner, weights=momentum[:, :, 1].ravel(), minlength=len(area))/area))
