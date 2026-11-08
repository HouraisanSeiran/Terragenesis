"""Metric grid adapters for the shared irregular drainage graph."""
from dataclasses import replace

import numpy as np
from numba import njit

from terrain_pipeline.irregular_drainage import build_mesh


def grid_mesh(shape, *, x0_m=0., z0_m=0., dx_m=30., dz_m=None, world_seed=20261020):
    """Preserve absolute native account identity and metric node positions."""
    dz_m = dx_m if dz_m is None else dz_m
    if not np.isfinite([x0_m, z0_m, dx_m, dz_m]).all() or min(dx_m, dz_m) <= 0.:
        raise ValueError("finite metric frame and positive cell dimensions required")
    origin = (int(np.floor(x0_m / dx_m + 1e-9)), int(np.floor(z0_m / dz_m + 1e-9)))
    mesh = build_mesh(shape, origin_native_xz=origin, spacing_m=dx_m, world_seed=world_seed)
    x = mesh.node_x_m + (x0_m - origin[0] * dx_m)
    z = mesh.node_z_m * (dz_m / dx_m) + (z0_m - origin[1] * dz_m)
    lengths = np.empty(mesh.indices.size, np.float64)
    for node in range(x.size):
        section = slice(mesh.indptr[node], mesh.indptr[node + 1])
        targets = mesh.indices[section]
        lengths[section] = np.hypot(x[targets] - x[node], z[targets] - z[node])
    return replace(mesh, node_x_m=x, node_z_m=z, edge_length_m=lengths)


@njit(cache=True)
def _strict(height, valid, outlets, indptr, indices, lengths):
    receiver = np.full(height.size, -1, np.int64)
    edge_length = np.zeros(height.size, np.float64)
    slope = np.zeros(height.size, np.float64)
    for node in range(height.size):
        if not valid[node] or outlets[node]:
            continue
        for edge in range(indptr[node], indptr[node + 1]):
            target = indices[edge]
            if not valid[target]:
                continue
            candidate = (height[node] - height[target]) / lengths[edge]
            if candidate > slope[node] or (candidate > 0. and candidate == slope[node]
                                            and target < receiver[node]):
                receiver[node] = target
                edge_length[node] = lengths[edge]
                slope[node] = candidate
    return receiver, edge_length, slope


def strict_receivers(height, mesh, *, valid_mask=None, outlet_mask=None):
    """Strict downhill metric graph routing; flats remain explicit sinks."""
    raw = np.asarray(height, np.float64)
    valid = np.ones(raw.shape, bool) if valid_mask is None else np.asarray(valid_mask)
    outlets = np.zeros(raw.shape, bool) if outlet_mask is None else np.asarray(outlet_mask)
    if (raw.shape != mesh.shape or valid.shape != raw.shape or outlets.shape != raw.shape
            or valid.dtype != bool or outlets.dtype != bool or not np.isfinite(raw[valid]).all()):
        raise ValueError("finite graph terrain and matching masks required")
    return _strict(raw.ravel(), valid.ravel(), outlets.ravel(), mesh.indptr,
                   mesh.indices, mesh.edge_length_m)


def receiver_edges_valid(receiver, mesh):
    """Check the actual graph edge set without fixed raster-neighbor rules."""
    rec = np.asarray(receiver).ravel()
    if rec.size != mesh.node_x_m.size or np.any(rec < -1) or np.any(rec >= rec.size):
        return False
    return all(rec[node] in mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
               for node in np.flatnonzero(rec >= 0))


def reverse_donors(receiver):
    """Build reverse CSR for receiver traversal in linear time."""
    rec = np.asarray(receiver).ravel()
    donors = np.flatnonzero(rec >= 0)
    order = np.argsort(rec[donors], kind="stable")
    counts = np.bincount(rec[donors], minlength=rec.size)
    return np.r_[0, np.cumsum(counts)], donors[order]


@njit(cache=True)
def segments_clear(sources, targets, valid):
    """Conservative control-cell supercover, including unknown corner touches.

    Cell-center account segments define the mask barrier independently of the
    representative displacement. This preserves the rule that a diagonal may
    not slip between two unknown orthogonal cells, for any graph edge length.
    """
    cols = valid.shape[1]
    result = np.ones(sources.size, np.bool_)
    for edge in range(sources.size):
        row, col = sources[edge] // cols, sources[edge] % cols
        end_row, end_col = targets[edge] // cols, targets[edge] % cols
        dr, dc = end_row - row, end_col - col
        nr, nc = abs(dr), abs(dc)
        sr, sc = (1 if dr > 0 else -1), (1 if dc > 0 else -1)
        ir, ic = 0, 0
        if not valid[row, col] or not valid[end_row, end_col]:
            result[edge] = False
            continue
        while ir < nr or ic < nc:
            cross_x = (2 * ic + 1) * nr
            cross_z = (2 * ir + 1) * nc
            if cross_x == cross_z:
                if not valid[row, col + sc] or not valid[row + sr, col]:
                    result[edge] = False
                    break
                col += sc
                row += sr
                ic += 1
                ir += 1
            elif cross_x < cross_z:
                col += sc
                ic += 1
            else:
                row += sr
                ir += 1
            if not valid[row, col]:
                result[edge] = False
                break
    return result


def valid_edge_mask(mesh, valid_mask):
    valid = np.asarray(valid_mask)
    if valid.dtype != bool or valid.shape != mesh.shape:
        raise ValueError("matching boolean valid mask required")
    sources = np.repeat(np.arange(valid.size, dtype=np.int64), np.diff(mesh.indptr))
    return segments_clear(sources, mesh.indices, valid)


def masked_mesh(mesh, valid_mask):
    """Remove graph edges crossing unknown control cells without bridging holes."""
    keep = valid_edge_mask(mesh, valid_mask)
    source = np.repeat(np.arange(np.prod(mesh.shape), dtype=np.int64), np.diff(mesh.indptr))
    counts = np.bincount(source[keep], minlength=int(np.prod(mesh.shape)))
    indptr = np.r_[0, np.cumsum(counts)].astype(np.int64)
    return replace(mesh, indptr=indptr, indices=mesh.indices[keep],
                   edge_length_m=mesh.edge_length_m[keep])


def graph_support_unknown(valid_mask, *, x0_m=0., z0_m=0., dx_m=30., dz_m=None,
                          world_seed=20261020):
    """Cells whose full bounded-radius graph neighbourhood exceeds known support."""
    valid = np.asarray(valid_mask)
    if valid.ndim != 2 or valid.dtype != bool:
        raise ValueError("2D boolean valid mask required")
    dz_m = dx_m if dz_m is None else dz_m
    pad = 4
    rows, cols = valid.shape
    extended = grid_mesh((rows + 2 * pad, cols + 2 * pad),
        x0_m=x0_m - pad * dx_m, z0_m=z0_m - pad * dz_m,
        dx_m=dx_m, dz_m=dz_m, world_seed=world_seed)
    supported = valid_edge_mask(extended, np.pad(valid, pad, constant_values=False))
    source = np.repeat(np.arange(np.prod(extended.shape), dtype=np.int64), np.diff(extended.indptr))
    unknown = np.bincount(source[~supported], minlength=int(np.prod(extended.shape))) > 0
    return valid & unknown.reshape(extended.shape)[pad:pad + rows, pad:pad + cols]
