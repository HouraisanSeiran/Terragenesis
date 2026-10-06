"""Pinned cold fault evidence and explicit, bounded in-memory diagnostics."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import threading

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.metric_vdm_fault_v2 import FaultRecipe, apply_fault, load_fault
from terrain_pipeline.metric_vdm_forms import load_formed_vdm

INDEX = ROOT / "verification/metric-vdm-fault/run-v2-20261005-02/index.json"
INDEX_SHA256 = "c4d076e959a6067c6f97af263c041c15a0a4aa4f7bec422665c5f6aac54064da"
CONFIG = ROOT / ".scratch/metric-vdm/fault-formed-example-v2.json"
SOURCE = ROOT / "verification/metric-vdm-forms/run-20261003T101709799064Z/fluted_wall/vdm.npz"
INDEX_SCHEMA = "metric-vdm-fault-delivery-v2"
AUDIT_SCHEMA = "metric-vdm-fault-audit-v2"
REPORT_SCHEMA = "metric-vdm-fault-preparation-v2"
PLANE_ORIGIN_BOUNDS_XZ_M = [[-183596.0, 64589.0], [-183566.0, 64619.0]]
SELECTION = {"row_start": 15, "row_stop": 30, "column_start": 140, "column_stop": 155}
FIELDS = {"plane_origin_xz_m", "strike_degrees", "slip_m", "moving_side", "transition_width_m"}
MAX_DISPLAY_VERTICES = 25_000
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_WORKING_BYTES = 1024 * 1024 * 1024
_PREVIEW_LOCK = threading.Lock()


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(path, expected):
    if _sha256(path) != expected:
        raise ValueError("fixed fault source hash mismatch: " + path.name)
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": expected}


def _json(path, expected, schema=None):
    _verify(path, expected)
    value = json.loads(path.read_text(encoding="utf-8"))
    if schema is not None and value.get("schema") != schema:
        raise ValueError("fixed fault schema mismatch")
    return value


def _fixed_path(raw, expected):
    normalized = raw.replace("\\", "/")
    if normalized != str(expected).replace("\\", "/") and normalized != expected.relative_to(ROOT).as_posix():
        raise ValueError("fixed fault evidence path mismatch")
    return expected


def _evidence():
    index = _json(INDEX, INDEX_SHA256, INDEX_SCHEMA)
    _fixed_path(index["configuration"]["path"], CONFIG)
    _fixed_path(index["source"]["path"], SOURCE)
    config = _json(CONFIG, index["configuration"]["sha256"])
    if set(config) != {"source", "fault", "selection"} or config["selection"] != SELECTION:
        raise ValueError("fixed fault configuration mismatch")
    _fixed_path(config["source"]["path"], SOURCE)
    if (config["source"]["expected_sha256"] != index["source"]["sha256"] or
            config["source"]["expected_identity"] != index["source"]["identity_sha256"]):
        raise ValueError("fixed source identity mismatch")
    records = {"index": _verify(INDEX, INDEX_SHA256),
               "configuration": _verify(CONFIG, index["configuration"]["sha256"]),
               "vdm": _verify(SOURCE, index["source"]["sha256"])}
    for name, filename in (("fault", "fault.npz"), ("audit", "audit.json"), ("report", "report.json")):
        if index[name]["path"] != filename:
            raise ValueError("fixed fault artifact path mismatch")
        records[name] = _verify(INDEX.parent / filename, index[name]["sha256"])
    audit = _json(INDEX.parent / "audit.json", index["audit"]["sha256"], AUDIT_SCHEMA)
    report = _json(INDEX.parent / "report.json", index["report"]["sha256"], REPORT_SCHEMA)
    if (audit.get("passed") is not True or audit["identity"]["passed"] is not True or
            audit["identity"]["stored"] != index["fault"]["identity_sha256"] or
            audit["identity"]["expected"] != index["fault"]["identity_sha256"] or
            audit["file_sha256"] != index["fault"]["sha256"] or
            report["fault_bundle"]["expected_identity"] != index["fault"]["identity_sha256"] or
            report["fault_bundle"]["expected_sha256"] != index["fault"]["sha256"] or
            report["selection"] != SELECTION or
            report["source"]["expected_sha256"] != index["source"]["sha256"] or
            report["source"]["expected_identity"] != index["source"]["identity_sha256"] or
            audit.get("source_vdm_preserved") is not True or report.get("source_vdm_preserved") is not True or
            audit.get("source_vdm_identity") != index["source"]["identity_sha256"] or
            report["geometry"] != index["geometry"] or
            report["fault"]["source_identity"] != index["source"]["identity_sha256"]):
        raise ValueError("fixed fault audit/identity mismatch")
    for record in (index, report):
        for flag in ("hydraulic_ready", "publishable", "solver_advanced", "natural_outlet_verified"):
            if record.get(flag) is not False:
                raise ValueError("fault certification flags must be false")
    if any(report["fault"].get(key) != value for key, value in config["fault"].items()):
        raise ValueError("saved fault recipe differs from pinned configuration")
    records["vdm"]["identity"] = index["source"]["identity_sha256"]
    records["fault"]["identity"] = index["fault"]["identity_sha256"]
    return index, config, records, report


def catalog():
    index, config, records, _ = _evidence()
    geometry = index["geometry"]
    return {"status": "diagnostic-real-cut", "defaults": config["fault"],
            "plane_origin_bounds_xz_m": PLANE_ORIGIN_BOUNDS_XZ_M,
            "selection": dict(SELECTION), "source": records,
            "geometry": {"fullVertices": geometry["vertices"], "fullTriangles": geometry["triangles"],
                         "fullSeamEdges": geometry["seam_edges"], "movedVertices": geometry["moved_vertices"],
                         "maxDisplacement_m": geometry["max_displacement_m"], "crossSeamTriangles": 0},
            "editable": True, "hydraulic_ready": False, "publishable": False, "solver_advanced": False}


def _source(index):
    source = load_formed_vdm(SOURCE, expected_sha256=index["source"]["sha256"],
                             expected_identity=index["source"]["identity_sha256"])
    arrays = source["arrays"]
    estimated = sum(value.nbytes for value in arrays.values()) + len(arrays["triangles"]) * 4096
    if estimated > MAX_WORKING_BYTES:
        raise ValueError("fault working memory budget exceeded")
    return source


def _window(shape):
    return (max(0, SELECTION["row_start"] - 8), min(shape[0], SELECTION["row_stop"] + 8),
            max(0, SELECTION["column_start"] - 8), min(shape[1], SELECTION["column_stop"] + 8))


def _selection(source):
    mask = np.zeros(source["arrays"]["reference_xyz_m"].shape[:2], bool)
    if mask.shape[0] < SELECTION["row_stop"] or mask.shape[1] < SELECTION["column_stop"]:
        raise ValueError("fixed selection outside source chart")
    mask[SELECTION["row_start"]:SELECTION["row_stop"], SELECTION["column_start"]:SELECTION["column_stop"]] = True
    if np.any(mask & source["arrays"]["protected_mask"]):
        raise ValueError("selection intersects protected source area")
    return mask


def _bounded(body, source):
    if not isinstance(body, dict) or set(body) != FIELDS:
        raise ValueError("fault preview requires exactly the five fault recipe fields; paths/source/selection are forbidden")
    values = dict(body)
    origin = values["plane_origin_xz_m"]
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise ValueError("plane_origin_xz_m requires two metre coordinates")
    for name, value in [("plane origin", entry) for entry in origin] + [(key, values[key]) for key in ("strike_degrees", "slip_m", "transition_width_m")]:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(name + " must be finite and numeric, not bool")
    if not -8 <= values["slip_m"] <= 8:
        raise ValueError("slip_m outside [-8, 8] metres")
    if not 1 <= values["transition_width_m"] <= 30:
        raise ValueError("transition_width_m outside [1, 30] metres")
    if not 0 <= values["strike_degrees"] <= 360:
        raise ValueError("strike_degrees outside [0, 360]")
    if values["moving_side"] not in ("positive", "negative"):
        raise ValueError("moving_side must be positive or negative")
    reference = source["arrays"]["vertices_xyz_m"].reshape(source["arrays"]["reference_xyz_m"].shape)
    row_start, row_stop, col_start, col_stop = _window(reference.shape[:2])
    neighborhood = reference[row_start:row_stop, col_start:col_stop][:, :, (0, 2)].reshape(-1, 2)
    if [neighborhood.min(axis=0).tolist(), neighborhood.max(axis=0).tolist()] != PLANE_ORIGIN_BOUNDS_XZ_M:
        raise ValueError("fixed plane origin bounds mismatch")
    if np.any(np.asarray(origin) < neighborhood.min(axis=0)) or np.any(np.asarray(origin) > neighborhood.max(axis=0)):
        raise ValueError("plane origin outside fixed display bounds; no clamping")
    values["plane_origin_xz_m"] = tuple(origin)
    return FaultRecipe(**values)


def _payload(result, source, config, records, report, schema):
    arrays = result["arrays"]
    original = source["arrays"]
    reference = arrays["reference_xyz_m"]
    if reference.shape != original["reference_xyz_m"].shape:
        raise ValueError("fault reference chart shape mismatch")
    if (not np.array_equal(arrays["source_vertices_xyz_m"], original["vertices_xyz_m"]) or
            not np.array_equal(arrays["source_triangles"], original["triangles"])):
        raise ValueError("fault source geometry differs from pinned formed VDM")
    rows, columns = reference.shape[:2]
    row_start, row_stop, col_start, col_stop = _window((rows, columns))
    chart_mask = np.zeros((rows, columns), bool)
    chart_mask[row_start:row_stop, col_start:col_stop] = True
    source_triangles = original["triangles"]
    eligible = np.all(chart_mask.ravel()[source_triangles], axis=1)
    triangles = arrays["triangles"]
    displacement = arrays["applied_displacement_xyz_m"]
    moving = np.linalg.norm(displacement, axis=1) > 1e-12
    keep = eligible[arrays["triangle_source_index"]] | np.any(moving[triangles], axis=1)
    triangle_indices = np.flatnonzero(keep)
    vertex_indices = np.union1d(np.unique(triangles[keep]), np.flatnonzero(moving))
    if len(vertex_indices) > MAX_DISPLAY_VERTICES:
        raise ValueError("fault display vertex budget exceeded")
    if not np.all(np.isin(np.flatnonzero(moving), vertex_indices)):
        raise ValueError("fault crop would omit moved vertices")
    remap = np.full(len(arrays["vertices_xyz_m"]), -1, np.int64)
    remap[vertex_indices] = np.arange(len(vertex_indices))
    seam = arrays["seam_edges"]
    seam = seam[np.all(remap[seam] >= 0, axis=1)]
    sides = arrays["vertex_side"]
    influenced = np.any(moving[triangles], axis=1)
    if np.any(np.ptp(sides[triangles[influenced]], axis=1) != 0):
        raise ValueError("fault triangle crosses open seam")
    before = arrays["vertices_xyz_m"] - displacement
    source_indices = arrays["vertex_source_index"][vertex_indices]
    exact = source_indices >= 0
    before_display = before[vertex_indices].copy()
    protected = np.zeros(len(vertex_indices), bool)
    protected[exact] = arrays["protected_mask"].ravel()[source_indices[exact]]
    if "vertex_source_edge" in arrays:
        source_edges = arrays["vertex_source_edge"][vertex_indices]
        protected = np.any(arrays["protected_mask"].ravel()[source_edges], axis=1)
    mesh = {"vertices": arrays["vertices_xyz_m"][vertex_indices].tolist(),
            "reference": before_display.tolist(), "triangles": remap[triangles[keep]].tolist(),
            "displacement": displacement[vertex_indices].tolist(), "protected": protected.tolist(),
            "vertexSide": sides[vertex_indices].tolist(),
            "transitionWeight": arrays["transition_weight"][vertex_indices].tolist(),
            "seamEdges": remap[seam].tolist(), "sourceVertexIndex": source_indices.tolist(),
            "sourceTriangleIndex": arrays["triangle_source_index"][triangle_indices].tolist()}
    metadata = {**result["metadata"], "solver_advanced": False, "water_generated": False,
                "reference_semantics": "already deformed VDM cut vertices minus applied_displacement_xyz_m; all vertices before slip, no chart substitution",
                "cross_seam_scope": "influenced cut triangles; untouched zero-displacement source triangles retain original topology",
                "units": "meters", "display_window": [row_start, row_stop, col_start, col_stop],
                "display_pad_cells": 8}
    geometry = {"fullVertices": len(arrays["vertices_xyz_m"]), "fullTriangles": len(triangles),
                "fullSeamEdges": len(arrays["seam_edges"]), "movedVertices": int(moving.sum()),
                "maxDisplacement_m": float(np.linalg.norm(displacement, axis=1).max()),
                "crossSeamTriangles": 0, "displayVertices": len(vertex_indices),
                "displayTriangles": len(triangle_indices), "displaySeamEdges": len(seam),
                "displayMovedVertices": int(moving[vertex_indices].sum())}
    payload = {"schema": schema, "identity": result["identity_sha256"], "metadata": metadata,
               "source": records, "report": report, "geometry": geometry, "editable": True,
               "defaults": config["fault"], "selection": dict(SELECTION), "mesh": mesh}
    payload["plane_origin_bounds_xz_m"] = PLANE_ORIGIN_BOUNDS_XZ_M
    if len(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("fault JSON budget exceeded")
    return payload


def fault_case():
    index, config, records, report = _evidence()
    source = _source(index)
    result = load_fault(INDEX.parent / "fault.npz", expected_sha256=index["fault"]["sha256"],
                        expected_identity=index["fault"]["identity_sha256"])
    if result["metadata"]["source_identity"] != source["identity_sha256"]:
        raise ValueError("saved fault source identity mismatch")
    if result["metadata"] != report["fault"]:
        raise ValueError("saved fault metadata differs from pinned report")
    _selection(source)
    return _payload(result, source, config, records, report, "fault-case-v1")


def preview_fault(body):
    if not _PREVIEW_LOCK.acquire(blocking=False):
        raise ValueError("fault preview busy; working memory budget permits one operation")
    try:
        index, config, records, _ = _evidence()
        source = _source(index)
        recipe = _bounded(body, source)
        selection = _selection(source)
        reference = source["arrays"]["vertices_xyz_m"]
        angle = math.radians(recipe.strike_degrees)
        signed = (reference[:, (0, 2)] - recipe.plane_origin_xz_m) @ np.array([-math.sin(angle), math.cos(angle)])
        selected_triangles = source["arrays"]["triangles"]
        selected_triangles = selected_triangles[np.any(selection.ravel()[selected_triangles], axis=1)]
        distances = signed[selected_triangles]
        if not np.any((distances.min(axis=1) < -1e-8) & (distances.max(axis=1) > 1e-8)):
            raise ValueError("cutmiss: plane does not cut the fixed selection interior")
        result = apply_fault(source, recipe=recipe, selection_mask=selection)
        if recipe.slip_m != 0 and not np.any(np.linalg.norm(result["arrays"]["applied_displacement_xyz_m"], axis=1) > 1e-12):
            raise ValueError("nomotion: moving side has no influenced vertices")
        report = {"status": "diagnostic_not_publishable", "operation": "explicit-in-memory-real-cut",
                  "source_unchanged": True, "solver_advanced": False, "water_generated": False,
                  "zero_slip": recipe.slip_m == 0}
        payload = _payload(result, source, config, records, report, "fault-preview-v1")
        _evidence()
        return payload
    finally:
        _PREVIEW_LOCK.release()
