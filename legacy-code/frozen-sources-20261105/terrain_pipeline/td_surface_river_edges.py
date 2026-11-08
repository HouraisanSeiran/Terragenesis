"""Read-only adapter from frozen TD D4 faces to river evidence edges."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_storage_dispatch_io import validate_saved_storage as validate_basin_storage
from terrain_pipeline.mountain_source_adapter import publish_bytes

SCHEMA = "td-surface-river-edges-v1"


def _boundary_sides(cell: int, rows: int, columns: int):
    row, column = divmod(cell, columns)
    if row == 0:
        yield "north"
    if row == rows - 1:
        yield "south"
    if column == 0:
        yield "west"
    if column == columns - 1:
        yield "east"


def _validate_masks(arrays):
    height = np.asarray(arrays["height_m"])
    valid = np.asarray(arrays["valid_mask"])
    protected = np.asarray(arrays["protected_mask"])
    if height.ndim != 2 or valid.shape != height.shape or protected.shape != height.shape:
        raise ValueError("height/valid/protected shape mismatch")
    if not np.isfinite(height[valid]).all():
        raise ValueError("unknown elevation in valid river evidence")
    if np.any(protected & valid):
        raise ValueError("unknown or protected barrier blocks river evidence")
    return height, valid


def _edge_direction(source, target, columns):
    difference = target - source
    if difference == 1:
        return "east"
    if difference == -1:
        return "west"
    if difference == columns:
        return "south"
    if difference == -columns:
        return "north"
    raise ValueError("river edge is not axis-aligned D4")


def build_td_surface_river_edges(hierarchy, *, storage=None, require_receiver=False, include_receiver=True):
    """Return frozen D4 edge records and an explicit readiness diagnostic.

    `storage` is optional and is only read for face flux/duration arrays. No
    route, adjacency, geometry, or water state is inferred when it is absent.
    """
    validate_basin_hierarchy(hierarchy)
    arrays = hierarchy["arrays"]
    height, valid = _validate_masks(arrays)
    rows, columns = height.shape
    flat_valid = valid.ravel()
    bed = height.ravel()
    receiver = np.asarray(arrays["receiver"])
    namespace = hierarchy["metadata"]["source_identity_sha256"]

    def cell_id(cell):
        row, column = divmod(cell, columns)
        return f"source:{namespace}:cell:{row}:{column}"
    owner = np.asarray(arrays["cell_owner"]).ravel()
    contribution = np.asarray(arrays["contribution_owner"]).ravel()
    if receiver.shape != flat_valid.shape:
        if require_receiver:
            raise ValueError("complete receiver array required")
        receiver = None
    if receiver is None and require_receiver:
        raise ValueError("complete receiver array required")
    if not include_receiver:
        if require_receiver:
            raise ValueError("complete receiver evidence requested but excluded")
        receiver = None

    storage_arrays = None if storage is None else storage["arrays"]
    flux_names = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s")
    flux_available = storage_arrays is not None and all(name in storage_arrays for name in flux_names)
    faces = np.asarray(arrays["face_cells"])
    if faces.ndim != 2 or faces.shape[1] != 2:
        raise ValueError("frozen face_cells must be an N by 2 D4 face list")
    if storage is not None:
        validate_basin_storage(storage)
        if storage["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
            raise ValueError("saved flux hierarchy identity mismatch")
        for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
            if not np.array_equal(storage_arrays[name], arrays[name]):
                raise ValueError("saved flux geometry/receiver mismatch")
        if (storage["metadata"]["spacing_m"] != hierarchy["metadata"]["spacing_m"] or
                storage["metadata"]["origin_m_xz"] != hierarchy["metadata"]["origin_m_xz"]):
            raise ValueError("saved flux coordinate mismatch")
        time_step = storage["metadata"]["dt_s"]
        substep = storage["metadata"]["substep_s"]
        if not np.isfinite([time_step, substep]).all() or not 0 < substep <= time_step:
            raise ValueError("invalid saved flux physical time")
        total_time = len(storage_arrays["rain_mm_h"]) * time_step
        if np.any(storage_arrays["active_forward_s"] + storage_arrays["active_reverse_s"] > total_time + 1e-8):
            raise ValueError("combined directional duration exceeds physical time")
    if flux_available:
        for name in flux_names:
            values = np.asarray(storage_arrays[name])
            if values.shape != (len(faces),) or not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError("invalid saved directional flux/activity")

    records = []
    for face_index, pair in enumerate(faces):
        first, second = map(int, pair)
        if not flat_valid[first] or not flat_valid[second]:
            raise ValueError("unknown face endpoint cannot become river evidence")
        if arrays["protected_mask"].ravel()[first] or arrays["protected_mask"].ravel()[second]:
            raise ValueError("protected face endpoint cannot become river evidence")
        source = None
        target = None
        if receiver is not None:
            if receiver[first] == second:
                source, target = first, second
            elif receiver[second] == first:
                source, target = second, first
        record = {
            "edge_id": f"{cell_id(min(first, second))}|{cell_id(max(first, second))}",
            "kind": "d4_internal_face",
            "endpoint_ids": [cell_id(first), cell_id(second)],
            "cell_ids": [first, second],
            "face_index": face_index,
            "axis": _edge_direction(first, second, columns),
            "bed_m": [float(bed[first]), float(bed[second])],
            "endpoint_xz_m": [[float(hierarchy["metadata"]["origin_m_xz"][0] + cell % columns * hierarchy["metadata"]["spacing_m"]),
                               float(hierarchy["metadata"]["origin_m_xz"][1] + cell // columns * hierarchy["metadata"]["spacing_m"])]
                              for cell in (first, second)],
            "upstream_bed_m": None if source is None else float(bed[source]),
            "downstream_bed_m": None if target is None else float(bed[target]),
            "merge_node_id": int(arrays["face_merge_node"][face_index]),
            "sill_m": float(arrays["face_level_m"][face_index]),
            "basin_ids": [int(owner[first]), int(owner[second])],
            "leaf_ids": [int(contribution[first]), int(contribution[second])],
            "boundary_kind": "internal",
            "unknown_contact": bool(arrays["node_unknown_contact"][owner[first]] or arrays["node_unknown_contact"][owner[second]]),
            "receiver_edge": source is not None,
            "evidence_kind": "static_contribution_edge" if source is not None else "computational_exchange_face",
            "upstream_cell": source,
            "downstream_cell": target,
        }
        if flux_available:
            record["forward_volume_m3"] = float(storage_arrays["face_forward_m3"][face_index])
            record["reverse_volume_m3"] = float(storage_arrays["face_reverse_m3"][face_index])
            record["forward_active_s"] = float(storage_arrays["active_forward_s"][face_index])
            record["reverse_active_s"] = float(storage_arrays["active_reverse_s"][face_index])
            record["net_volume_m3"] = record["forward_volume_m3"] - record["reverse_volume_m3"]
            record["gross_volume_m3"] = record["forward_volume_m3"] + record["reverse_volume_m3"]
            record["active_duration_s"] = float(storage_arrays["active_forward_s"][face_index] + storage_arrays["active_reverse_s"][face_index])
        records.append(record)

    open_boundary = np.asarray(arrays["open_boundary_mask"]).ravel()
    boundary_cells = np.flatnonzero(open_boundary)
    for cell in boundary_cells:
        cell = int(cell)
        if not flat_valid[cell] or arrays["protected_mask"].ravel()[cell]:
            raise ValueError("unknown or protected boundary cannot become river evidence")
        for side in _boundary_sides(cell, rows, columns):
            records.append({
                "edge_id": f"{cell_id(cell)}:exterior:{side}",
                "kind": "d4_boundary_face",
                "endpoint_ids": [cell_id(cell), f"{cell_id(cell)}:exterior:{side}"],
                "cell_ids": [cell],
                "face_index": None,
                "axis": side,
                "bed_m": [float(bed[cell])],
                "basin_ids": [int(owner[cell])],
                "leaf_ids": [int(contribution[cell])],
                "boundary_kind": "engineered_boundary",
                "receiver_edge": False,
                "upstream_cell": cell if receiver is not None and receiver[cell] < 0 else None,
                "downstream_cell": None,
                "natural_outlet": False,
                "boundary_face_flux_available": False,
                "boundary_flux_reason": "saved boundary_outflow_m3 is per cell; no observed per-exterior-side allocation",
                "evidence_kind": "engineered_computational_boundary_face",
            })

    receiver_complete = receiver is not None and np.all((receiver[flat_valid] == -1) | flat_valid[receiver[flat_valid].clip(min=0)])
    unknown_terminal_cells = []
    if receiver is not None:
        for cell in np.flatnonzero(flat_valid & (receiver == -1)):
            row, column = divmod(int(cell), columns)
            neighbors = [next_row * columns + next_column for next_row, next_column in
                         ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1))
                         if 0 <= next_row < rows and 0 <= next_column < columns]
            if any(not flat_valid[neighbor] for neighbor in neighbors):
                unknown_terminal_cells.append({"cell_id": int(cell), "endpoint_id": cell_id(int(cell)),
                                               "kind": "unknown_contact_terminal", "natural_outlet": False})
    hydraulic_ready = False
    diagnostic = {
        "schema": SCHEMA,
        "hierarchy_identity_sha256": hierarchy["identity_sha256"],
        "storage_identity_sha256": None if storage is None else storage["identity_sha256"],
        "source_identity_sha256": namespace,
        "id_semantics": "source identity plus grid row/column endpoint IDs; face_index is provenance only",
        "edge_semantics": "D4 cell-centre axis-aligned computational links across saved faces; not observed river channels",
        "flux_semantics": "forward/reverse refer to saved face endpoint order; net=forward-reverse; gross=forward+reverse",
        "boundary_face_flux_available": False,
        "receiver_complete": bool(receiver_complete),
        "receiver_evidence_included": include_receiver,
        "flux_available": bool(flux_available),
        "edge_count": len(records),
        "d4_only": True,
        "unknown_or_protected_rejected": True,
        "unknown_cells": int((~valid).sum()),
        "unknown_semantics": "holes retained; only saved valid D4 faces exported; no bridging or outlet inference",
        "unknown_contact_terminals": unknown_terminal_cells,
        "engineered_boundary_not_natural_outlet": True,
        "hydraulic_ready": hydraulic_ready,
        "publishable": False,
        "diagnostic_only": True,
        "transient_converged": False,
        "natural_outlet_verified": False,
        "reason": "D4 terrain face/receiver evidence is not an observed river channel or a full-domain convergence certificate",
    }
    return {"schema": SCHEMA, "records": records, "diagnostic": diagnostic}


def write_report(result, path):
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    publish_bytes(Path(path), payload)
    return hashlib.sha256(payload).hexdigest()
