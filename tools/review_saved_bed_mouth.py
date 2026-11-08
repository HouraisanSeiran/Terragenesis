# HEADER
import os

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMBA_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import generate_binary_structure, label

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.channel_geometry import _ordered_pieces, _sample_piece_points
from tools.prepare_hydrology_domains import _artifact_identity, _read_bed_piece
from tools.verify_fluvial_channel_remobilization import resource_limits


def load_inputs(root):
    root = Path(root)
    report_path = root / "verification/hydrological-planning-domain/full-edges-v5-20261014-03/edge-8470-8600-v7-shared-sections-owned-halo2/report.json"
    report = json.loads(report_path.read_text())
    assert isinstance(report, dict)
    assert report.get("accepted") is True
    assert str(report.get("source_edge")) == "8470->8600" or report.get("source_edge") == [8470, 8600]
    piece_paths = report["piece_paths"]
    assert len(piece_paths) == 29

    source_hashes = {report_path.resolve(): hashlib.sha256(report_path.read_bytes()).hexdigest()}
    records = []
    piece_parent = set()
    piece_plan = set()
    seen = set()
    for rel in piece_paths:
        p = Path(str(rel))
        if not p.is_absolute():
            p = root / p
        p = p.resolve()
        assert p not in seen
        seen.add(p)
        raw = p.read_bytes()
        source_hashes[p] = hashlib.sha256(raw).hexdigest()
        rec = _read_bed_piece(str(p))
        rec = dict(rec)
        rec["source_path"] = str(p)
        rec["archive_sha256"] = source_hashes[p]
        piece_parent.add(rec["parent_detail_identity"])
        piece_plan.add(rec["frozen_plan_identity"])
        records.append(rec)

    detail_path = Path(str(report["detail_path"]))
    if not detail_path.is_absolute():
        detail_path = root / detail_path
    detail_path = detail_path.resolve()
    detail_bytes = detail_path.read_bytes()
    source_hashes[detail_path] = hashlib.sha256(detail_bytes).hexdigest()
    with np.load(detail_path, allow_pickle=False) as npz:
        metadata_json = str(npz['metadata_json'].item())
        metadata = json.loads(metadata_json)
        detail_arrays = {k: npz[k].copy() for k in npz.files if k != 'metadata_json'}

    detail_identity = report["detail_identity"]
    plan_identity = report["plan_identity"]
    assert _artifact_identity(metadata, detail_arrays) == metadata["identity"] == detail_identity
    assert metadata["plan_identity"] == plan_identity
    assert piece_parent == {detail_identity}
    assert piece_plan == {plan_identity}

    ordered, edge_start, edge_end, tol = _ordered_pieces(records)
    return {
        "ordered": ordered,
        "edge_start": edge_start,
        "edge_end": edge_end,
        "fraction_tol": tol,
        "detail_metadata": metadata,
        "detail_arrays": detail_arrays,
        "source_hashes": source_hashes,
    }


def sample_centerline(inputs):
    pieces = inputs['ordered']
    edge_start = np.asarray(inputs['edge_start'], dtype=float)
    edge_end = np.asarray(inputs['edge_end'], dtype=float)
    meta = inputs['detail_metadata']
    arrays = inputs['detail_arrays']

    origin = np.asarray(meta['origin_xz_m'], dtype=float)
    spacing = float(meta['spacing_m'])
    ocean_mask = np.asarray(arrays['ocean_mask'], dtype=bool)
    H, W = ocean_mask.shape

    full_length = float(np.linalg.norm(edge_end - edge_start))

    xz_all, bed_all, sup_all = [], [], []
    pidx_all, frac_all, dist_all = [], [], []
    rows_all, cols_all = [], []
    max_gap = 0.0

    for pi, piece in enumerate(pieces):
        nodes = np.asarray(piece['node_xz_m'], dtype=float)
        start, end = nodes[0], nodes[1]
        delta = end - start
        length = float(np.linalg.norm(delta))
        n = int(np.ceil(length / 1.0))
        if n < 1:
            n = 1
        t = np.linspace(0.0, 1.0, n + 1)
        is_last = (pi == len(pieces) - 1)
        if not is_last:
            t = t[:-1]
        pts = start[None, :] + t[:, None] * delta[None, :]

        if pts.shape[0] > 1:
            g = np.linalg.norm(np.diff(pts, axis=0), axis=1)
            if g.size:
                max_gap = max(max_gap, float(g.max()))

        bed, mask = _sample_piece_points(piece, pts)
        bed = np.asarray(bed, dtype=float).reshape(-1)
        mask = np.asarray(mask, dtype=bool).reshape(-1)

        lo, hi = np.asarray(piece['node_edge_fractions'], dtype=float)
        fr = lo + t * (hi - lo)
        ds = fr * full_length

        ox = np.floor((pts[:, 0] - origin[0]) / spacing + 0.5).astype(int)
        oz = np.floor((pts[:, 1] - origin[1]) / spacing + 0.5).astype(int)
        inb = (ox >= 0) & (ox < W) & (oz >= 0) & (oz < H)
        r = np.where(inb, oz, -1)
        c = np.where(inb, ox, -1)

        xz_all.append(pts)
        bed_all.append(bed)
        sup_all.append(mask)
        pidx_all.append(np.full(pts.shape[0], pi, dtype=int))
        frac_all.append(fr)
        dist_all.append(ds)
        rows_all.append(r)
        cols_all.append(c)

    xz = np.concatenate(xz_all, axis=0)
    bed_m = np.concatenate(bed_all)
    supported_mask = np.concatenate(sup_all)
    piece_index = np.concatenate(pidx_all)
    fraction = np.concatenate(frac_all)
    distance_m = np.concatenate(dist_all)
    ocean_rows = np.concatenate(rows_all)
    ocean_cols = np.concatenate(cols_all)

    known = (ocean_rows >= 0)
    ocean_known = np.zeros(xz.shape[0], dtype=bool)
    ocean_label = np.zeros(xz.shape[0], dtype=bool)
    if known.any():
        rr = ocean_rows[known]
        cc = ocean_cols[known]
        lbl = ocean_mask[rr, cc]
        ocean_label[known] = lbl
        ocean_known[known] = True

    finite = bed_m[np.isfinite(bed_m)]
    if finite.size > 0 and xz.shape[0] > 0:
        assert np.all(np.diff(distance_m) >= -1e-9), "distance_m not sorted"

    max_gap = float(np.max(np.linalg.norm(np.diff(xz, axis=0), axis=1))) if len(xz) > 1 else 0.
    assert max_gap <= 1. + 1e-8

    return {
        'node_xz_m': xz,
        'bed_m': bed_m,
        'supported_mask': supported_mask,
        'piece_index': piece_index,
        'fraction': fraction,
        'distance_m': distance_m,
        'ocean_rows': ocean_rows,
        'ocean_cols': ocean_cols,
        'ocean_known': ocean_known,
        'ocean_label': ocean_label,
        'nominal_detail_spacing_m': float(spacing),
    }


def ocean_boundary_components(ocean_mask):
    if not isinstance(ocean_mask, np.ndarray):
        raise TypeError("ocean_mask must be a numpy.ndarray")
    if ocean_mask.dtype != np.bool_:
        raise TypeError("ocean_mask must have dtype bool")
    if ocean_mask.ndim != 2:
        raise ValueError("ocean_mask must be 2D")

    mask = ocean_mask.copy()
    Z, X = mask.shape
    structure = generate_binary_structure(2, 1)
    labels, n = label(mask, structure=structure)

    perimeter_ids = set()
    if Z > 0 and X > 0:
        perimeter_ids.update(np.unique(labels[0, :]).tolist())
        perimeter_ids.update(np.unique(labels[-1, :]).tolist())
        perimeter_ids.update(np.unique(labels[:, 0]).tolist())
        perimeter_ids.update(np.unique(labels[:, -1]).tolist())
    perimeter_ids.discard(0)

    side_checks = (
        ("z_min", 0, lambda l: l[0, :]),
        ("z_max", Z - 1, lambda l: l[-1, :]),
        ("x_min", 0, lambda l: l[:, 0]),
        ("x_max", X - 1, lambda l: l[:, -1]),
    )

    components = []
    for cid in sorted(perimeter_ids):
        cell_count = int(np.count_nonzero(labels == cid))
        contact = []
        for name, _idx, getter in side_checks:
            if Z == 0 or X == 0:
                break
            row = getter(labels)
            if np.any(row == cid):
                contact.append(name)
        components.append({
            "id": int(cid),
            "cell_count": cell_count,
            "contact_sides": contact,
        })

    connected_mask = np.isin(labels, list(perimeter_ids)) if perimeter_ids else np.zeros_like(mask)
    connected_mask &= mask

    unconnected = int(np.count_nonzero(mask)) - int(np.count_nonzero(connected_mask))

    return {
        "labels": labels.astype(np.int64, copy=True),
        "boundary_connected_ocean": connected_mask.astype(np.bool_, copy=True),
        "components": components,
        "all_component_count": int(n),
        "unconnected_ocean_cell_count": unconnected,
        "shape_zx": (int(Z), int(X)),
    }


def summarize_crossings(samples, sea):
    """
    Read-only summary of actual bed crossings and nearest-30m D4 ocean boundary
    bracket crossings for the supplied edge-centerline samples.

    Returns:
        summary (dict), connected_ocean_sample (bool[N])

    Semantics:
        - 'actual bed' crossings use only supported, finite bed_m pairs.
        - 'connected ocean' uses nearest ocean-label parent samples and D4
          boundary_connected_ocean connectivity only.
        - Bracketing is <= nominal_detail_spacing_m (30 m), NOT 1 m coastline.
        - No certification, no Q, no sediment, no nodebed targets.
    """
    node_xz   = np.asarray(samples["node_xz_m"], dtype=float)
    bed       = np.asarray(samples["bed_m"], dtype=float)
    support   = np.asarray(samples["supported_mask"], dtype=bool)
    piece     = np.asarray(samples["piece_index"], dtype=np.int64)
    frac      = np.asarray(samples["fraction"], dtype=float)
    dist      = np.asarray(samples["distance_m"], dtype=float)
    o_rows    = np.asarray(samples["ocean_rows"], dtype=np.int64)
    o_cols    = np.asarray(samples["ocean_cols"], dtype=np.int64)
    o_known   = np.asarray(samples["ocean_known"], dtype=bool)
    o_label   = np.asarray(samples["ocean_label"], dtype=bool)
    nominal   = float(samples.get("nominal_detail_spacing_m", 30.0))

    sea_labels = np.asarray(sea["labels"], dtype=np.int64)
    sea_conn   = np.asarray(sea["boundary_connected_ocean"], dtype=bool)

    n = bed.shape[0]
    connected_ocean_sample = np.zeros(n, dtype=bool)

    # ---- Precompute per-sample ocean parent info (nearest 30 m) ----
    parent_conn = np.zeros(n, dtype=bool)   # False/True from boundary_connected_ocean
    parent_lab  = np.zeros(n, dtype=bool)   # True if sea_labels != 0
    parent_id   = np.full(n, -1, dtype=np.int64)
    finite_bed  = support & np.isfinite(bed)

    Z, X = sea_labels.shape
    for i in range(n):
        if not o_known[i]:
            continue
        r = int(o_rows[i]); c = int(o_cols[i])
        if r < 0 or r >= Z or c < 0 or c >= X:
            continue
        connected_ocean_sample[i] = sea_conn[r, c]
        parent_conn[i] = sea_conn[r, c]
        parent_lab[i]  = sea_labels[r, c] != 0
        parent_id[i]   = int(sea_labels[r, c])

    # ---- Helpers ----
    def endpoint(i):
        return {
            "index": int(i),
            "piece_index": int(piece[i]),
            "distance_m": float(dist[i]),
            "fraction": float(frac[i]),
            "position_xz_m": [float(node_xz[i, 0]), float(node_xz[i, 1])],
            "actual_bed_m": float(bed[i]) if finite_bed[i] else None,
            "actual_mesh_supported": bool(support[i]),
            "parent_ocean_known": bool(o_known[i]),
            "parent_ocean_label": bool(parent_lab[i]),
            "boundary_connected_ocean": bool(parent_conn[i]),
            "ocean_component_id": int(parent_id[i]) if parent_id[i] >= 0 else None,
            "parent_ocean_row_col": [int(o_rows[i]), int(o_cols[i])] if o_known[i] else None,
        }

    def bracket(i, j, kind):
        return {
            "kind": kind,
            "before": endpoint(i),
            "after": endpoint(j),
            "distance_width_m": float(abs(dist[j] - dist[i])),
        }

    actual_bed = []
    ocean_entries = []
    ocean_exits = []

    # ---- Adjacent pair scans ----
    for i in range(n - 1):
        j = i + 1
        if not (0. < dist[j] - dist[i] <= 1. + 1e-8):
            continue

        # Actual bed crossing: both supported & finite, sign change on bed
        if finite_bed[i] and finite_bed[j]:
            b0, b1 = bed[i], bed[j]
            if (b0 >= 0.0) != (b1 >= 0.0):
                kind = "downward_bed_sea_level" if b0 >= 0.0 else "upward_bed_sea_level"
                actual_bed.append(bracket(i, j, kind))

        # Finite D4 connected-ocean entry/exit: both KNOWN ocean samples
        if o_known[i] and o_known[j]:
            c0, c1 = parent_conn[i], parent_conn[j]
            if (not c0) and c1:
                ocean_entries.append(bracket(i, j, "finite_connected_ocean_entry"))
            elif c0 and (not c1):
                ocean_exits.append(bracket(i, j, "finite_connected_ocean_exit"))

    # ---- Candidate actual mouth bracket ----
    # First entry where before has parent_ocean_label False, after has
    # connected True, AND all prior samples have ocean_known & supported,
    # AND the very first sample has parent_ocean_label False.
    candidate = None
    candidate_status = "not_evaluated"
    req_possible = (
        (n > 0)
        and bool(o_known[0])
        and bool(finite_bed[0])
        and (not bool(parent_lab[0]))
    )
    if req_possible:
        prior_ok = True
        found = False
        for i in range(n - 1):
            if prior_ok and o_known[i] and finite_bed[i]:
                j = i + 1
                p_lab_before = parent_lab[i]
                p_conn_after = parent_conn[j]
                if (not p_lab_before) and p_conn_after and o_known[j] and not parent_conn[i] and (0. < dist[j] - dist[i] <= 1. + 1e-8) and finite_bed[j]:
                    candidate = bracket(i, j, "candidate_actual_mouth_d4")
                    candidate_status = "candidate_found"
                    found = True
                    break
            else:
                prior_ok = False
            if not (o_known[i] and finite_bed[i]):
                prior_ok = False
        if not found and prior_ok:
            candidate_status = "no_entry_with_required_prior_conditions"
        elif not found and not prior_ok:
            candidate_status = "prior_samples_unknown_or_unsupported"
    else:
        candidate_status = "first_sample_not_land_ocean_or_unsupported"

    # ---- Unknown accounting ----
    unknown_mesh = [
        {"index": int(i),
         "piece_index": int(piece[i]),
         "position_xz_m": [float(node_xz[i, 0]), float(node_xz[i, 1])],
         "distance_m": float(dist[i])}
        for i in range(n) if not bool(support[i])
    ]
    unknown_ocean = [
        {"index": int(i),
         "piece_index": int(piece[i]),
         "position_xz_m": [float(node_xz[i, 0]), float(node_xz[i, 1])],
         "distance_m": float(dist[i])}
        for i in range(n) if not bool(o_known[i])
    ]

    summary = {
        "actual_bed_crossings": actual_bed,
        "finite_ocean_entries": ocean_entries,
        "finite_ocean_exits": ocean_exits,
        "first_land_to_connected_ocean_bracket": candidate,
        "candidate_status": candidate_status,
        "unknown_mesh_samples": unknown_mesh,
        "unknown_ocean_samples": unknown_ocean,
        "multiple_ocean_entries": len(ocean_entries) > 1,
        "finite_ocean_components": sea.get("components", []),
        "global_hydrology_certified": False,
        "publishable": False,
        "nominal_detail_spacing_m": nominal,
        "semantics": (
            "read-only actual bed and nearest-30m parent-ocean brackets; "
            "finite D4 perimeter connectivity only"
        ),
    }
    return summary, connected_ocean_sample


import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot_profile(samples, summary, connected, outdir):
    x = samples['distance_m']
    y = np.where(samples['supported_mask'], samples['bed_m'], np.nan)

    fig, axes = plt.subplots(2, 1, figsize=(12, 8))

    groups = [
        ('actual_bed_crossings', 'blue'),
        ('finite_ocean_entries', 'green'),
        ('finite_ocean_exits', 'red'),
    ]

    for ax in axes:
        ax.plot(x, y, color='black', lw=1.2, label='Actual bed')
        ax.axhline(0, color='cyan', label='Sea 0')
        for group, color in groups:
            for bracket in summary[group]:
                ax.axvspan(
                    bracket['before']['distance_m'],
                    bracket['after']['distance_m'],
                    color=color,
                    alpha=0.5,
                )

    axes[0].set_xlim(x.min(), x.max())

    zoom = summary['first_land_to_connected_ocean_bracket']
    if zoom is None and summary['actual_bed_crossings']:
        zoom = summary['actual_bed_crossings'][0]

    if zoom is not None:
        center = zoom['after']['distance_m']
        axes[1].set_xlim(center - 300, center + 300)
    else:
        axes[1].set_xlim(x.min(), x.max())

    left, right = axes[1].get_xlim()
    local_mask = (x >= left) & (x <= right) & samples['supported_mask'] & np.isfinite(y)
    local_values = y[local_mask]
    candidates = list(local_values)
    candidates.append(0)
    candidates = [v for v in candidates if np.isfinite(v)]
    if candidates:
        low = min(0, min(candidates))
        high = max(0, max(candidates))
        pad = max(0.25, 0.08 * (high - low))
        axes[1].set_ylim(low - pad, high + pad)

    oc = np.where(samples['ocean_known'], np.asarray(connected, dtype=float), np.nan)
    ax2 = axes[1].twinx()
    ax2.step(x, oc, where='mid', label='30 m parent D4 ocean')
    ax2.legend(loc='upper right')

    from matplotlib.patches import Patch
    handles, labels = axes[1].get_legend_handles_labels()
    extra = [
        Patch(color='blue', alpha=0.5, label='actual SL bracket'),
        Patch(color='green', alpha=0.5, label='ocean entry'),
        Patch(color='red', alpha=0.5, label='ocean exit'),
    ]
    seen = set()
    combined = []
    for h, l in list(zip(handles, labels)) + [(p, p.get_label()) for p in extra]:
        if l not in seen:
            seen.add(l)
            combined.append((h, l))
    axes[1].legend([h for h, _ in combined], [l for _, l in combined], loc='upper left', fontsize=8)

    for ax in axes:
        ax.set_xlabel('Along-edge (m)')
        ax.set_ylabel('Actual bed (m)')

    fig.suptitle('Saved mesh bed and 30 m ocean labels')
    fig.savefig(outdir / 'actual-centerline-coast-brackets.png', dpi=150)
    plt.close(fig)

def plot_cross_section(inputs, summary, outdir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import json
    import numpy as np
    
    br = summary.get('first_land_to_connected_ocean_bracket')
    if br is None:
        crossings = summary.get('actual_bed_crossings')
        if crossings:
            br = crossings[0]
        else:
            return {'status': 'not_located'}
    
    endpoint = br['after']
    idx = int(endpoint['piece_index'])
    piece = inputs['ordered'][idx]
    center = np.array(endpoint['position_xz_m'], float)
    
    delta = np.asarray(inputs['edge_end'], float) - np.asarray(inputs['edge_start'], float)
    unit = delta / np.linalg.norm(delta)
    normal = np.array([unit[1], -unit[0]], float)
    
    offsets = np.linspace(-30, 30, 241)
    points = center[None, :] + offsets[:, None] * normal[None, :]
    bed, mask = _sample_piece_points(piece, points)
    
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(offsets, np.where(mask, bed, np.nan), 'k-', lw=1)
    ax.scatter(offsets[~mask], np.zeros(np.count_nonzero(~mask)), c='gray', marker='x', label='unknown')
    ax.axhline(0, color='b', ls='--', lw=0.5)
    ax.axvline(0, color='r', ls='--', lw=0.5)
    ax.set_title(f"Actual bed | piece {idx} | center {center[0]:.1f}, {center[1]:.1f}")
    ax.set_xlabel('offset [m]')
    ax.set_ylabel('bed [m]')
    fig.tight_layout()
    fig.savefig(outdir / 'actual-mouth-cross-section.png', dpi=150)
    plt.close(fig)
    
    meta = {
        'status': 'ok',
        'center_xz_m': center.tolist(),
        'piece_index': idx,
        'piece_identity': piece['identity'],
        'offset_spacing_m': 0.25,
        'support_count': int(np.sum(mask)),
        'unknown_count': int(np.sum(~mask)),
        'center_bed_m': float(bed[120]) if mask[120] and np.isfinite(bed[120]) else None,
        'hydraulics_coupled': False
    }
    return meta


# MAIN
def main():
    resource_limits()
    inputs = load_inputs(ROOT)
    samples = sample_centerline(inputs)
    sea = ocean_boundary_components(inputs["detail_arrays"]["ocean_mask"])
    summary, connected = summarize_crossings(samples, sea)

    out = ROOT / ".scratch" / "hydrological-planning-domain" / "saved-bed-mouth-20261016-01"
    out.mkdir(parents=True, exist_ok=False)

    summary["cross_section"] = {"status": "pending_saved_data_plot"}

    summary["detail_identity"] = inputs["detail_metadata"]["identity"]
    summary["plan_identity"] = inputs["detail_metadata"]["plan_identity"]
    summary["detail_spacing"] = 30
    summary["source_sha256"] = {
        str(p): d for p, d in inputs["source_hashes"].items()
    }
    summary["pieces"] = [
        {
            "index": i,
            "identity": p["identity"],
            "source_path": p["source_path"],
            "archive_sha256": p["archive_sha256"],
            "node_fraction": p["node_edge_fractions"].tolist()
            if hasattr(p["node_edge_fractions"], "tolist")
            else list(p["node_edge_fractions"]),
        }
        for i, p in enumerate(inputs["ordered"])
    ]

    for path_str, digest in inputs["source_hashes"].items():
        h = hashlib.sha256(Path(path_str).read_bytes()).hexdigest()
        if h != digest:
            raise RuntimeError(f"source mutated: {path_str}")

    np.savez_compressed(
        out / "centerline.npz",
        **samples,
        connected_ocean_sample=connected,
        metadata_json=np.array(json.dumps(summary, allow_nan=False)),
    )

    with open(out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, allow_nan=False, indent=2)

    print(json.dumps(summary, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
