import numpy as np

from terrain_pipeline.surface_rivers.metric_design_bed import _barycentric_batch
from terrain_pipeline.surface_rivers.metric_valley_union import _cell_at_point


def _piece_geometry(record):
    if not isinstance(record, dict):
        raise ValueError("record must be a dict")

    identity = record.get("identity")
    parent_detail_identity = record.get("parent_detail_identity")
    frozen_plan_identity = record.get("frozen_plan_identity")
    if not isinstance(identity, str) or not identity:
        raise ValueError("identity must be non-empty str")
    if not isinstance(parent_detail_identity, str) or not parent_detail_identity:
        raise ValueError("parent_detail_identity must be non-empty str")
    if not isinstance(frozen_plan_identity, str) or not frozen_plan_identity:
        raise ValueError("frozen_plan_identity must be non-empty str")

    source_path = record.get("source_path")
    archive_sha256 = record.get("archive_sha256")
    if not isinstance(source_path, str) or not source_path:
        raise ValueError("source_path must be non-empty str")
    if not isinstance(archive_sha256, str) or not archive_sha256:
        raise ValueError("archive_sha256 must be non-empty str")

    spacing_m = record.get("fine_spacing_m")
    if isinstance(spacing_m, (bool, np.bool_)) or not isinstance(spacing_m, (int, float, np.integer, np.floating)):
        raise ValueError("fine_spacing_m must be a positive finite float")
    spacing_m = float(spacing_m)
    if not np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("fine_spacing_m must be a positive finite float")

    origin = record.get("mesh_origin_xz_m")
    origin = np.asarray(origin, dtype=np.float64)
    if origin.shape != (2,) or not np.all(np.isfinite(origin)):
        raise ValueError("mesh_origin_xz_m must be finite float[2]")

    if not isinstance(record.get("shared_sections"), list):
        raise ValueError("shared_sections must be a list")
    shared_sections = record["shared_sections"]

    arrays = record.get("arrays")
    if not isinstance(arrays, dict):
        raise ValueError("arrays must be a dict")

    cells = arrays.get("cells")
    if cells is None:
        raise ValueError("cells missing")
    if not isinstance(cells, np.ndarray) or cells.dtype.kind not in "iu":
        raise ValueError("cells must be integer ndarray")
    if cells.ndim != 2 or cells.shape[1] != 2 or cells.shape[0] <= 0:
        raise ValueError("cells must be integer[n,2], n>0")
    cells = cells.astype(np.int64, copy=False)

    if np.unique(cells, axis=0).shape[0] != cells.shape[0]:
        raise ValueError("cells must be unique")
    n = cells.shape[0]

    vertices = arrays.get("vertices_xz_m")
    if vertices is None:
        raise ValueError("vertices_xz_m missing")
    if not isinstance(vertices, np.ndarray):
        raise ValueError("vertices_xz_m must be ndarray")
    vertices = vertices.astype(np.float64, copy=False)
    if vertices.ndim != 2 or vertices.shape[1] != 2:
        raise ValueError("vertices_xz_m must be float[v,2]")
    v = vertices.shape[0]
    if v <= 0:
        raise ValueError("vertices_xz_m must have v>0")
    if not np.all(np.isfinite(vertices)):
        raise ValueError("vertices_xz_m must be finite")

    triangles = arrays.get("triangles")
    if triangles is None:
        raise ValueError("triangles missing")
    if not isinstance(triangles, np.ndarray) or triangles.dtype.kind not in "iu":
        raise ValueError("triangles must be integer ndarray")
    if triangles.shape != (4 * n, 3):
        raise ValueError("triangles must be integer[4n,3]")
    triangles = triangles.astype(np.int64, copy=False)
    if triangles.min() < 0 or triangles.max() >= v:
        raise ValueError("triangles indices out of bounds")

    bed = arrays.get("bed_elevation_m")
    if bed is None:
        raise ValueError("bed_elevation_m missing")
    if not isinstance(bed, np.ndarray):
        raise ValueError("bed_elevation_m must be ndarray")
    bed = bed.astype(np.float64, copy=False)
    if bed.shape != (v,):
        raise ValueError("bed_elevation_m must be float[v]")
    if not np.all(np.isfinite(bed)):
        raise ValueError("bed_elevation_m must be finite")

    node_xz = arrays.get("node_xz_m")
    if node_xz is None:
        raise ValueError("node_xz_m missing")
    if not isinstance(node_xz, np.ndarray):
        raise ValueError("node_xz_m must be ndarray")
    node_xz = node_xz.astype(np.float64, copy=False)
    if node_xz.shape != (2, 2):
        raise ValueError("node_xz_m must be float[2,2]")
    if not np.all(np.isfinite(node_xz)):
        raise ValueError("node_xz_m must be finite")

    node_source_edges = arrays.get("node_source_edges")
    if node_source_edges is None:
        raise ValueError("node_source_edges missing")
    if not isinstance(node_source_edges, np.ndarray) or node_source_edges.dtype.kind not in "iu":
        raise ValueError("node_source_edges must be integer ndarray")
    if node_source_edges.shape != (2, 2):
        raise ValueError("node_source_edges must be integer[2,2]")
    node_source_edges = node_source_edges.astype(np.int64, copy=False)
    if not (isinstance(node_source_edges, np.ndarray) and node_source_edges.shape == (2, 2) and node_source_edges.dtype == np.int64):
        raise ValueError("node_source_edges must be an int64 np.ndarray of shape (2, 2)")
    if not np.array_equal(node_source_edges[0], node_source_edges[1]):
        raise ValueError("node_source_edges rows must be equal")
    if node_source_edges[0, 0] == node_source_edges[0, 1]:
        raise ValueError("node_source_edges first-row ids must differ")
    if not np.all(node_source_edges >= 0):
        raise ValueError("all node_source_edges ids must be >= 0")

    node_edge_fractions = arrays.get("node_edge_fractions")
    if node_edge_fractions is None:
        raise ValueError("node_edge_fractions missing")
    if not isinstance(node_edge_fractions, np.ndarray):
        raise ValueError("node_edge_fractions must be ndarray")
    node_edge_fractions = node_edge_fractions.astype(np.float64, copy=False)
    if node_edge_fractions.shape != (2,):
        raise ValueError("node_edge_fractions must be float[2]")
    if not np.all(np.isfinite(node_edge_fractions)):
        raise ValueError("node_edge_fractions must be finite")
    lo, hi = float(node_edge_fractions[0]), float(node_edge_fractions[1])
    if not (0.0 <= lo < hi <= 1.0):
        raise ValueError("node_edge_fractions must satisfy 0<=lo<hi<=1")

    receiver = arrays.get("receiver")
    if receiver is None:
        raise ValueError("receiver missing")
    if not isinstance(receiver, np.ndarray) or receiver.dtype.kind not in "iu":
        raise ValueError("receiver must be integer ndarray")
    if receiver.shape != (2,):
        raise ValueError("receiver must be integer[2]")
    receiver = receiver.astype(np.int64, copy=False)
    if not (receiver[0] == 1 and receiver[1] == -1):
        raise ValueError("receiver must be [1,-1]")

    if node_xz[0, 0] == node_xz[1, 0] and node_xz[0, 1] == node_xz[1, 1]:
        raise ValueError("node_xz_m points must be distinct")

    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)

    return {
        "identity": identity,
        "parent_detail_identity": parent_detail_identity,
        "frozen_plan_identity": frozen_plan_identity,
        "source_path": source_path,
        "archive_sha256": archive_sha256,
        "spacing_m": spacing_m,
        "origin_xz_m": origin,
        "cells": cells,
        "vertices_xz_m": vertices,
        "triangles": triangles,
        "bed_elevation_m": bed,
        "node_xz_m": node_xz,
        "node_source_edges": node_source_edges,
        "node_edge_fractions": node_edge_fractions,
        "receiver": receiver,
        "shared_sections": shared_sections,
        "lookup": {(int(cell[0]), int(cell[1])): row_index for row_index, cell in enumerate(cells)},
        "bbox_min_xz_m": bbox_min,
        "bbox_max_xz_m": bbox_max,
    }


def _sample_piece_points(piece, points):
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("points must have shape (N, 2)")
    if not np.all(np.isfinite(pts)):
        raise ValueError("points must be finite")
    N = pts.shape[0]
    if N == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=bool)

    bmin = np.asarray(piece["bbox_min_xz_m"], dtype=np.float64)
    bmax = np.asarray(piece["bbox_max_xz_m"], dtype=np.float64)
    maxabs = float(np.max(np.abs(np.concatenate([bmin, bmax]))))
    pad = 8.0 * np.spacing(maxabs) if maxabs > 0 else 0.0
    lo = bmin - pad
    hi = bmax + pad

    inside = np.all(pts >= lo, axis=1) & np.all(pts <= hi, axis=1)

    lookup = piece["lookup"]
    origin = np.asarray(piece["origin_xz_m"], dtype=np.float64)
    spacing = piece["spacing_m"]

    cell_rows = []
    supported_idx = []
    for i in np.nonzero(inside)[0]:
        try:
            key = _cell_at_point(pts[i], lookup, origin, spacing)
        except ValueError as exc:
            if str(exc) == "centerline leaves sparse mesh support":
                continue
            raise
        row = lookup.get(key)
        if row is None:
            continue
        supported_idx.append(int(i))
        cell_rows.append(int(row))

    values = np.full(N, np.nan, dtype=np.float64)
    mask = np.zeros(N, dtype=bool)
    if not supported_idx:
        return values, mask

    sup = np.asarray(supported_idx, dtype=np.int64)
    rows = np.asarray(cell_rows, dtype=np.int64)
    ids, weights = _barycentric_batch(
        pts[sup],
        rows,
        piece["vertices_xz_m"],
        piece["triangles"],
    )
    bed = piece["bed_elevation_m"]
    sampled = np.sum(bed[ids] * weights, axis=1)
    values[sup] = sampled
    mask[sup] = True
    return values, mask


def _ordered_pieces(pieces):
    if not isinstance(pieces, (list, tuple)) or not pieces:
        raise ValueError("pieces must be a non-empty list or tuple")
    normalized = [_piece_geometry(p) for p in pieces]
    keyed = [
        (tuple(float(v) for v in n["node_edge_fractions"]), i, n)
        for i, n in enumerate(normalized)
    ]
    keyed.sort(key=lambda t: (t[0][0], t[2]['identity']))

    ids = [n["identity"] for _, _, n in keyed]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate piece identity")

    parent = keyed[0][2]["parent_detail_identity"]
    frozen = keyed[0][2]["frozen_plan_identity"]


    all_nodes = np.concatenate([n["node_xz_m"] for _, _, n in keyed], axis=0)
    max_abs = float(np.max(np.abs(all_nodes))) if all_nodes.size else 0.0
    world_scale = max(1e-9, 8.0 * float(np.spacing(max(1.0, max_abs))))

    edge_start = np.asarray(keyed[0][2]["node_xz_m"][0], dtype=float).copy()
    edge_end = np.asarray(keyed[-1][2]["node_xz_m"][1], dtype=float).copy()
    delta = edge_end - edge_start
    edge_length = float(np.hypot(delta[0], delta[1]))
    if not (np.isfinite(edge_length) and edge_length > 0.0):
        raise ValueError("global edge must have positive finite length")

    frac_tol = world_scale / edge_length
    if frac_tol <= 0.0 or not np.isfinite(frac_tol):
        raise ValueError("invalid fraction tolerance")

    if keyed[0][0][0] > frac_tol:
        raise ValueError("fraction gap or overlap")
    if abs(keyed[-1][0][1] - 1.0) > frac_tol:
        raise ValueError("fraction gap or overlap")

    source_edge = keyed[0][2]["node_source_edges"][0]
    if np.any(source_edge[0] == source_edge[1]):
        raise ValueError("source edge node IDs must be distinct")

    ordered = []
    prev_hi = None
    for fracs, _, n in keyed:
        if n["parent_detail_identity"] != parent:
            raise ValueError("parent_detail_identity mismatch")
        if n["frozen_plan_identity"] != frozen:
            raise ValueError("frozen_plan_identity mismatch")


        se = n["node_source_edges"]
        if not (np.array_equal(se[0], source_edge) and np.array_equal(se[1], source_edge)):
            raise ValueError("source edge mismatch")

        lo, hi = fracs
        if lo > hi:
            raise ValueError("invalid fraction order")

        if prev_hi is not None:
            if abs(lo - prev_hi) > frac_tol:
                raise ValueError("fraction gap or overlap")
        prev_hi = hi

        pts = np.asarray(n["node_xz_m"], dtype=float)
        expected = edge_start[None, :] + np.asarray([lo, hi])[:, None] * delta[None, :]
        if not np.all(np.abs(pts - expected) <= world_scale):
            raise ValueError("piece endpoint not on global edge")

        ordered.append(n)

    # Verify continuity of adjacent node endpoints along straight line
    for i in range(len(ordered) - 1):
        a = np.asarray(ordered[i]["node_xz_m"][1], dtype=float)
        b = np.asarray(ordered[i + 1]["node_xz_m"][0], dtype=float)
        if not np.all(np.abs(a - b) <= world_scale):
            raise ValueError("fraction gap or overlap")

    return ordered, edge_start, edge_end, frac_tol


def _audit_shared_sections(ordered, edge_start, edge_end, fraction_tol):
    import numpy as np

    if not ordered or len(ordered) < 2:
        return [], 0.0

    def _metric_tol_for(coord):
        scale = max(1.0, float(np.max(np.abs(coord))) if np.size(coord) else 1.0)
        return max(1e-9, 8.0 * np.spacing(scale))

    sections = []
    max_abs_bed_diff = 0.0

    for i in range(len(ordered) - 1):
        left = ordered[i]
        right = ordered[i + 1]

        # Shared position along the seam is the node xz of the shared node.
        shared_pos = np.asarray(left['node_xz_m'][-1], dtype=float)
        tol_pos = _metric_tol_for(shared_pos)

        def _select_section(piece):
            parent = piece['parent_detail_identity']
            candidates = []
            for sec in piece.get('shared_sections', []) or []:
                if sec.get('parent_detail_identity') != parent:
                    continue
                p = np.asarray(sec.get('position_xz_m'), dtype=float)
                if p.shape != (2,) or not np.all(np.isfinite(p)):
                    continue
                if np.all(np.abs(p - shared_pos) <= tol_pos):
                    candidates.append(sec)
            if len(candidates) != 1:
                raise ValueError(
                    'expected exactly one matching shared section per piece'
                )
            return candidates[0]

        left_sec = _select_section(left)
        right_sec = _select_section(right)

        for piece, sec in ((left, left_sec), (right, right_sec)):
            parent = piece['parent_detail_identity']
            if sec.get('parent_detail_identity') != parent:
                raise ValueError('shared section parent identity mismatch')

            p = np.asarray(sec['position_xz_m'], dtype=float)
            n = np.asarray(sec['normal_xz'], dtype=float)
            if p.shape != (2,) or not np.all(np.isfinite(p)):
                raise ValueError('invalid section position')
            if n.shape != (2,) or not np.all(np.isfinite(n)):
                raise ValueError('invalid section normal')

            n_norm = float(np.linalg.norm(n))
            if abs(n_norm - 1.0) > 1e-6:
                raise ValueError('section normal not unit length')

            r = float(sec['radius_m'])
            if not np.isfinite(r) or r <= 0.0:
                raise ValueError('invalid section radius')

            # Perpendicularity to the global edge direction.
            edge_vec = np.asarray(edge_end, dtype=float) - np.asarray(edge_start, dtype=float)
            e_norm = float(np.linalg.norm(edge_vec))
            if e_norm == 0.0:
                raise ValueError('degenerate edge for perpendicularity check')
            e_hat = edge_vec / e_norm
            if abs(float(np.dot(n, e_hat))) > 1e-6:
                raise ValueError('section normal not perpendicular to edge')

            offs = np.asarray(sec['offsets_m'], dtype=float)
            if offs.ndim != 1 or offs.size < 2:
                raise ValueError('invalid section offsets')
            if not np.all(np.isfinite(offs)):
                raise ValueError('non-finite section offsets')
            if np.any(np.diff(offs) <= 0.0):
                raise ValueError('section offsets must be strictly ascending')

            if offs[0] < -r - tol_pos or offs[-1] > r + tol_pos:
                raise ValueError('section offsets out of radius bounds')

            near_center = np.any(np.abs(offs) <= tol_pos)
            near_neg = np.any(np.abs(offs + r) <= tol_pos)
            near_pos = np.any(np.abs(offs - r) <= tol_pos)
            if not (near_center and near_neg and near_pos):
                raise ValueError('section offsets missing required endpoints/center')

        # Ensure the persisted sections are truly the same shared section.
        lp = np.asarray(left_sec['position_xz_m'], dtype=float)
        rp = np.asarray(right_sec['position_xz_m'], dtype=float)
        if not np.all(np.abs(lp - rp) <= tol_pos):
            raise ValueError('shared section positions differ')

        ln = np.asarray(left_sec['normal_xz'], dtype=float)
        rn = np.asarray(right_sec['normal_xz'], dtype=float)
        if np.any(np.abs(ln - rn) > 1e-6):
            raise ValueError('shared section normals differ')

        lr = float(left_sec['radius_m'])
        rr = float(right_sec['radius_m'])
        if abs(lr - rr) > tol_pos:
            raise ValueError('shared section radii differ')

        loff = np.asarray(left_sec['offsets_m'], dtype=float)
        roff = np.asarray(right_sec['offsets_m'], dtype=float)
        union = np.union1d(loff, roff)

        must = [-lr, 0.0, lr]
        for req in must:
            if not np.any(np.abs(union - req) <= tol_pos):
                union = np.concatenate([union, [req]])
        union = np.unique(union)
        if not (union[0] >= -lr - tol_pos and union[-1] <= lr + tol_pos):
            raise ValueError('union offsets out of radius bounds')

        normal = ln
        position = lp
        points = position[None, :] + union[:, None] * normal[None, :]

        left_vals, left_mask = _sample_piece_points(left, points)
        right_vals, right_mask = _sample_piece_points(right, points)

        if not np.all(left_mask) or not np.all(right_mask):
            raise ValueError('shared section offsets fall outside both pieces')

        left_bed = np.asarray(left_vals)
        right_bed = np.asarray(right_vals)
        if left_bed.shape != right_bed.shape:
            raise ValueError('shared section bed shapes differ')

        diff = np.abs(left_bed - right_bed)
        finite = np.isfinite(diff)
        if not np.all(finite):
            # Non-finite bed values are treated as an outright mismatch.
            raise ValueError('shared section beds differ beyond tolerance')
        local_max = float(np.max(diff))
        if local_max > 1e-6:
            raise ValueError('shared section beds differ beyond tolerance')
        max_abs_bed_diff = max(max_abs_bed_diff, local_max)

        frac = float(left['node_edge_fractions'][-1])
        rfrac = float(right['node_edge_fractions'][0])
        if abs(frac - rfrac) > fraction_tol:
            raise ValueError('shared section endpoint fractions differ')

        sections.append({
            'left_index': i,
            'right_index': i + 1,
            'fraction': frac,
            'position_xz_m': np.array(position, dtype=float, copy=True),
            'normal_xz': np.array(normal, dtype=float, copy=True),
            'radius_m': float(lr),
        })

    return sections, max_abs_bed_diff


def sample_saved_bed_grid(
    pieces,
    *,
    origin_xz_m,
    shape_zx,
    spacing_m,
):
    import numpy as np

    # ---- validate shape ----
    if isinstance(shape_zx, (list, tuple)):
        shape = list(shape_zx)
    elif isinstance(shape_zx, np.ndarray):
        shape = shape_zx.tolist()
    else:
        raise TypeError("shape_zx must be list, tuple, or ndarray")
    if len(shape) != 2:
        raise ValueError("shape_zx must have length 2")
    for v in shape:
        if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
            raise TypeError("shape_zx entries must be integers")
        if v <= 0:
            raise ValueError("shape_zx entries must be positive")
    nz, nx = int(shape[0]), int(shape[1])
    if nz * nx > 65536:
        raise ValueError("shape_zx product must be <= 65536")

    # ---- validate origin ----
    if isinstance(origin_xz_m, (list, tuple)):
        origin = list(origin_xz_m)
    elif isinstance(origin_xz_m, np.ndarray):
        origin = origin_xz_m.tolist()
    else:
        raise TypeError("origin_xz_m must be list, tuple, or ndarray")
    if len(origin) != 2:
        raise ValueError("origin_xz_m must have length 2")
    for v in origin:
        if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
            raise TypeError("origin entries must be numeric")
        if not np.isfinite(float(v)):
            raise ValueError("origin entries must be finite")
    ox, oz = float(origin[0]), float(origin[1])

    # ---- validate spacing ----
    if isinstance(spacing_m, bool):
        raise TypeError("spacing_m must not be bool")
    if isinstance(spacing_m, str):
        raise TypeError("spacing_m must not be string")
    if not isinstance(spacing_m, (int, float, np.integer, np.floating)):
        raise TypeError("spacing_m must be numeric")
    spacing = float(spacing_m)
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("spacing_m must be positive finite")

    # ---- build target grid ----
    zs = oz + np.arange(nz, dtype=np.float64) * spacing
    xs = ox + np.arange(nx, dtype=np.float64) * spacing
    zz, xx = np.meshgrid(zs, xs, indexing="ij")
    points = np.stack([xx.ravel(), zz.ravel()], axis=1)  # [N,2] x,z
    if not np.all(np.isfinite(points)):
        raise ValueError("computed target coordinates must be finite")
    N = points.shape[0]

    # ---- ordered pieces + audit ----
    ordered, edge_start, edge_end, fraction_tol = _ordered_pieces(pieces)
    sections, max_shared_diff = _audit_shared_sections(
        ordered, edge_start, edge_end, fraction_tol
    )

    # ---- allocate bed ----
    bed = np.full(N, np.nan, dtype=np.float64)
    mask = np.zeros(N, dtype=bool)
    owner = np.full(N, -1, dtype=np.int64)

    edge_delta = edge_end - edge_start
    denom = float(np.dot(edge_delta, edge_delta))
    if denom == 0.0:
        raise ValueError("degenerate global edge")

    # ---- projection fractions ----
    frac = ((points - edge_start) @ edge_delta) / denom
    at_lo = np.abs(frac - 0.0) <= fraction_tol
    at_hi = np.abs(frac - 1.0) <= fraction_tol
    valid_frac_range = (frac > 0.0) & (frac < 1.0)
    endpoint_ok = (at_lo | at_hi) & np.isfinite(frac)
    usable = valid_frac_range | endpoint_ok

    # ---- per-piece selection (half-open [lo,hi), final closed) ----
    n_pieces = len(ordered)
    for i, piece in enumerate(ordered):
        lo, hi = piece["node_edge_fractions"]
        lo = float(lo)
        hi = float(hi)
        is_first = (i == 0)
        is_last = (i == n_pieces - 1)
        lo_lo = lo - (fraction_tol if is_first else 0.0)
        hi_hi = hi + (fraction_tol if is_last else 0.0)
        if is_last:
            sel = (frac >= lo_lo) & (frac <= hi_hi) & usable
        else:
            sel = (frac >= lo_lo) & (frac < hi) & usable
        idx = np.nonzero(sel)[0]
        if idx.size == 0:
            continue
        vals, supported = _sample_piece_points(piece, points[idx])
        vals = np.asarray(vals, dtype=np.float64)
        supported = np.asarray(supported, dtype=bool)
        write = idx[supported]
        bed[write] = vals[supported]
        mask[write] = True
        owner[write] = i

    # ---- shared sections: overlap resolution via both sides ----
    metric_tol = max(1e-9, 8.0 * np.spacing(max(1.0, float(np.max(np.abs(edge_start))))))
    max_shared_bed_diff = float(max_shared_diff)

    for sec in sections:
        sec_frac = float(sec["fraction"])
        sec_pos = np.asarray(sec["position_xz_m"], dtype=np.float64)
        sec_nrm = np.asarray(sec["normal_xz"], dtype=np.float64)
        radius = float(sec["radius_m"])
        li = int(sec["left_index"])
        ri = int(sec["right_index"])

        on_line = np.abs(frac - sec_frac) <= fraction_tol
        if not np.any(on_line):
            continue
        cand = np.nonzero(on_line)[0]

        bed[cand] = np.nan
        mask[cand] = False
        owner[cand] = -1

        p = points[cand]
        perp = np.abs((p - sec_pos) @ sec_nrm)
        along = np.abs(((p - sec_pos) @ edge_delta) / np.sqrt(denom))
        rows = cand[(perp <= radius + metric_tol) & (along <= metric_tol)]

        if rows.size == 0:
            continue

        left_vals, left_ok = _sample_piece_points(ordered[li], points[rows])
        right_vals, right_ok = _sample_piece_points(ordered[ri], points[rows])

        left_ok = np.asarray(left_ok, dtype=bool)
        right_ok = np.asarray(right_ok, dtype=bool)
        both = left_ok & right_ok
        if not np.any(both):
            continue

        lv = np.asarray(left_vals, dtype=np.float64)[both]
        rv = np.asarray(right_vals, dtype=np.float64)[both]
        if not np.all(np.isfinite(lv)) or not np.all(np.isfinite(rv)):
            raise ValueError("shared-section sampled bed must be finite")
        diff = np.abs(lv - rv)
        if np.any(diff > 1e-6):
            raise ValueError("shared section bed mismatch exceeds 1e-6")
        d = float(np.max(diff))
        if d > max_shared_bed_diff:
            max_shared_bed_diff = d

        write_rows = rows[both]
        # right/downstream index wins, use right bed
        bed[write_rows] = rv
        mask[write_rows] = True
        owner[write_rows] = ri

    # ---- provenance ----
    canonical_pieces = []
    for i, piece in enumerate(ordered):
        canonical_pieces.append({
            "identity": piece["identity"],
            "parent_detail_identity": piece["parent_detail_identity"],
            "frozen_plan_identity": piece["frozen_plan_identity"],
            "source_path": piece["source_path"],
            "archive_sha256": piece["archive_sha256"],
            "spacing_m": float(piece["spacing_m"]),
            "origin_xz_m": [float(piece["origin_xz_m"][0]), float(piece["origin_xz_m"][1])],
            "node_edge_fractions": [
                float(piece["node_edge_fractions"][0]),
                float(piece["node_edge_fractions"][1]),
            ],
            "node_xz_m": [
                [float(piece["node_xz_m"][0][0]), float(piece["node_xz_m"][0][1])],
                [float(piece["node_xz_m"][1][0]), float(piece["node_xz_m"][1][1])],
            ],
            "source_spacing_m": float(piece["spacing_m"]),
            "fraction_interval": [
                float(piece["node_edge_fractions"][0]),
                float(piece["node_edge_fractions"][1]),
            ],
        })

    provenance = {
        "schema": "saved-bed-grid-v1",
        "canonical_pieces": canonical_pieces,
        "source_path": [p["source_path"] for p in ordered],
        "archive_hash": [p["archive_sha256"] for p in ordered],
        "parent_ids": [p["parent_detail_identity"] for p in ordered],
        "source_spacing_m": [float(p["spacing_m"]) for p in ordered],
        "fraction_interval": [
            [float(p["node_edge_fractions"][0]), float(p["node_edge_fractions"][1])]
            for p in ordered
        ],
        "target_params": {
            "origin_xz_m": [ox, oz],
            "shape_zx": [nz, nx],
            "spacing_m": spacing,
        },
        "support_count": int(np.count_nonzero(mask)),
        "maximum_shared_section_difference_m": float(max_shared_bed_diff),
        "point_samples_not_cell_average": True,
        "hydraulics_coupled": False,
        "cross_edge_endpoint_continuity_verified": False,
        "global_hydrology_certified": False,
        "publishable": False,
    }

    return {
        "bed_m": bed.reshape(nz, nx),
        "supported_mask": mask.reshape(nz, nx),
        "owner_piece_index": owner.reshape(nz, nx),
        "provenance": provenance,
    }
