"""Conservative natural-outlet certification for a pinned raster hydrology graph.

This module consumes evidence; it never infers ocean from nodata or a boundary.
"""

import hashlib
import json
from collections import deque

import numpy as np


SCHEMA = "natural-outlet-certification-v1"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()).hexdigest()


def certify_natural_outlets(height_m, valid_mask, receiver, coastline_mask, sea_level_m,
                            observed_connections, *, protected_mask=None):
    """Return an immutable-by-convention report; failed evidence never certifies.

    ``receiver`` is a flat D4 receiver array with -1 terminals.  A coastline
    cell must be valid and explicitly marked by the caller.  Connections are
    records containing ``terminal_cell_id`` and ``coastline_cell_id``; their
    path is checked against the receiver graph and bed elevations.
    """
    height = np.asarray(height_m, dtype=np.float64)
    valid = np.asarray(valid_mask, dtype=bool)
    coast = np.asarray(coastline_mask, dtype=bool)
    receivers = np.asarray(receiver)
    if height.ndim != 2 or valid.shape != height.shape or coast.shape != height.shape:
        raise ValueError("height, masks must share a 2D shape")
    if receivers.shape not in (height.shape, (height.size,)) or receivers.dtype.kind not in "iu":
        raise ValueError("receiver must be an integer grid or flat array")
    receivers = receivers.reshape(-1).astype(np.int64)
    if not np.isfinite(height[valid]).all() or not np.isfinite(sea_level_m):
        raise ValueError("valid bed and sea level must be finite")
    if np.any(coast & ~valid) or np.any((receivers < -1) | (receivers >= height.size)):
        raise ValueError("coastline and receiver coverage are invalid")
    protected = np.zeros_like(valid) if protected_mask is None else np.asarray(protected_mask, dtype=bool)
    if protected.shape != height.shape:
        raise ValueError("protected mask shape mismatch")
    terminals = set(np.flatnonzero(valid.ravel() & (receivers < 0)).tolist())
    records = []
    for connection in observed_connections:
        if set(connection) != {"terminal_cell_id", "coastline_cell_id", "path_cell_ids", "independent_observation"}:
            raise ValueError("connection schema mismatch")
        terminal = connection["terminal_cell_id"]
        coast_cell = connection["coastline_cell_id"]
        path = np.asarray(connection["path_cell_ids"])
        reasons = []
        if type(terminal) is not int or type(coast_cell) is not int or path.ndim != 1 or path.dtype.kind not in "iu":
            raise ValueError("connection IDs/path must be integer")
        if path.size < 1 or np.any(path < 0) or np.any(path >= height.size) or np.unique(path).size != path.size:
            reasons.append("invalid_path")
        else:
            if int(path[0]) != terminal or int(path[-1]) != coast_cell:
                reasons.append("path_endpoints_mismatch")
            if terminal not in terminals:
                reasons.append("terminal_is_not_receiver_exit")
            if not coast.ravel()[coast_cell]:
                reasons.append("endpoint_not_explicit_coastline")
            if np.any(~valid.ravel()[path]):
                reasons.append("path_crosses_unknown")
            if np.any(protected.ravel()[path]):
                reasons.append("path_crosses_protected_cell")
            rows, cols = np.divmod(path, height.shape[1])
            if path.size > 1 and np.any(np.abs(np.diff(rows)) + np.abs(np.diff(cols)) != 1):
                reasons.append("path_is_not_d4_contiguous")
            if path.size > 1 and not np.all(np.diff(height.ravel()[path]) <= 1e-9):
                reasons.append("path_is_not_downhill")
            if height.ravel()[coast_cell] > sea_level_m + 1e-9:
                reasons.append("coast_endpoint_above_declared_sea_level")
            cursor = terminal
            visited = set()
            while cursor >= 0 and cursor not in visited and cursor != coast_cell:
                visited.add(cursor)
                cursor = int(receivers[cursor])
            if cursor != coast_cell:
                reasons.append("receiver_chain_does_not_reach_coast")
        if connection["independent_observation"] is not True:
            reasons.append("missing_independent_observation")
        records.append({"terminal_cell_id": terminal, "coastline_cell_id": coast_cell,
                        "path_cell_ids": path.tolist(), "reasons": sorted(set(reasons)),
                        "natural_outlet_verified": not reasons,
                        "ocean_outlet_certified": not reasons})
    certified = bool(records) and all(record["natural_outlet_verified"] for record in records)
    report = {"schema": SCHEMA, "sea_level_m": float(sea_level_m),
              "valid_cells": int(valid.sum()), "explicit_coastline_cells": int(coast.sum()),
              "terminals": sorted(terminals), "outlets": records,
              "natural_outlet_verified": certified, "ocean_outlet_certified": certified,
              "policy": "explicit_coastline_and_independent_connection_required",
              "source_unchanged": True}
    report["content_sha256"] = _digest(report)
    return report


def validate_certification(report):
    if report.get("schema") != SCHEMA:
        raise ValueError("unsupported natural outlet report")
    digest = report.get("content_sha256")
    body = dict(report)
    body.pop("content_sha256", None)
    if digest != _digest(body):
        raise ValueError("natural outlet report identity mismatch")
    expected = bool(report["outlets"]) and all(item["natural_outlet_verified"] for item in report["outlets"])
    if report["natural_outlet_verified"] != expected or report["ocean_outlet_certified"] != expected:
        raise ValueError("natural outlet flags are inconsistent")
    return True
