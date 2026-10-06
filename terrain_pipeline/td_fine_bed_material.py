"""Bounded fine bed candidates and cut/fill material ledgers.

The output is a derived candidate on the saved native bed.  It is deliberately
not a surveyed DEM, a bed mutation, or a hydraulic input.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SCHEMA = "td-fine-bed-material-v1"
ALGORITHM = "bounded-derived-fine-bed-material-candidate-v1"
MAX_WINDOWS = 4096
MAX_CELLS = 2_000_000
MAX_BYTES = 64 * 1024**2
EPS = 1e-9
FALSE_FLAGS = ("hydraulic_solved", "natural_outlet_certified", "publish_ready",
               "bed_changed", "water_surface_meshed", "material_ledger_certified")


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _payload(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode()


def _finite(value, name):
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _points(value, name):
    array = np.asarray(value, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite Nx3")
    return array


def _shape(record):
    return {"windows": [{key: window[key] for key in (
        "window_id", "status", "grid", "ports", "bed_m", "derived_bed_m",
        "source_surface_m", "cut_fill_m3", "material_ledger", "rejection_reasons")}
                         for window in record["windows"]]}


def _identity(record):
    excluded = {"identity_sha256", "shape_identity_sha256"}
    return {key: value for key, value in record.items() if key not in excluded}


def _source_pin(record, key):
    value = record.get(key)
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"invalid source pin: {key}")
    return value


def _window_key(points, spacing, window_size_m=64.0):
    array = _points(points, "port points")
    minimum = np.floor(array[:, [0, 2]].min(axis=0) / window_size_m).astype(int)
    return tuple(minimum.tolist())


def _ports(paths, sections, patches, corridors=None):
    sections_by_arc = {item["arc_id"]: item for item in sections.get("edge_sections", [])}
    ports = []
    def collect(value):
        array = np.asarray(value, dtype=float)
        if array.ndim == 1 and array.shape[0] == 3:
            ports.append(array.tolist())
            return
        if array.ndim >= 2 and array.shape[-1] == 3:
            for item in array.reshape((-1, 3)):
                ports.append(item.tolist())
    for item in sections_by_arc.values():
        collect(item["cross_section_xyz_m"])
    for patch in patches.get("patches", []):
        if patch.get("status") == "candidate":
            collect(patch.get("vertices_xyz_m", []))
    corridor_items = (corridors or {}).get("corridors", []) if isinstance(corridors, dict) else (corridors or [])
    for corridor in corridor_items:
        if corridor.get("status") == "candidate":
            collect(corridor.get("centerline_bed_xyz_m", []))
    unique = {}
    for point in ports:
        array = np.asarray(point, dtype=float)
        unique[tuple(float(value) for value in np.round(array[[0, 2]], 8).tolist())] = array.tolist()
    return list(unique.values())


def _make_window(window_id, points, *, target_spacing_m, max_cut_m, max_cells,
                 protected=False, open_boundary=False):
    array = _points(points, "window points")
    xmin, zmin = array[:, [0, 2]].min(axis=0)
    xmax, zmax = array[:, [0, 2]].max(axis=0)
    spacing = float(target_spacing_m)
    x = np.arange(math.floor(xmin / spacing) * spacing,
                  math.ceil(xmax / spacing) * spacing + spacing * .5, spacing)
    z = np.arange(math.floor(zmin / spacing) * spacing,
                  math.ceil(zmax / spacing) * spacing + spacing * .5, spacing)
    estimated = int(len(x) * len(z))
    source = np.empty((len(z), len(x)), dtype=float)
    sample_x, sample_z = np.meshgrid(x, z)
    samples = np.column_stack((sample_x.ravel(), sample_z.ravel()))
    source_points = array[:, [0, 2]]
    for start in range(0, len(samples), 4096):
        batch = samples[start:start + 4096]
        distance = np.linalg.norm(batch[:, None, :] - source_points[None, :, :], axis=2)
        nearest = np.argmin(distance, axis=1)
        weights = 1. / np.maximum(distance, 1e-6) ** 2
        values = (weights * array[None, :, 1]).sum(axis=1) / weights.sum(axis=1)
        exact = distance.min(axis=1) <= 1e-6
        values[exact] = array[nearest[exact], 1]
        source.ravel()[start:start + len(batch)] = values
    depth = float(np.clip(np.max(array[:, 1]) - np.min(array[:, 1]), .08, max_cut_m))
    bed = source.copy()
    derived = bed - depth
    cut = np.maximum(bed - derived, 0.)
    fill = np.maximum(derived - bed, 0.)
    source_volume = float(np.sum(cut) * spacing * spacing)
    fill_volume = float(np.sum(fill) * spacing * spacing)
    ledger = {"original_rock_m3": source_volume, "solid_fill_m3": fill_volume,
              "channel_sediment_m3": 0.0, "pore_sediment_m3": 0.0,
              "cut_rock_m3": source_volume, "net_import_m3": fill_volume,
              "material_balance_residual_m3": 0.0}
    status = "candidate"
    reasons = []
    if protected:
        status = "refused"
        reasons.append("protected_area_contact")
    if open_boundary:
        status = "refused"
        reasons.append("open_boundary_contact")
    if estimated > max_cells:
        status = "refused"
        reasons.append("fine_cell_budget_exceeded")
        bed = derived = np.empty((0, 0))
    return {"window_id": window_id, "status": status,
            "bbox_m_xz": [float(xmin), float(zmin), float(xmax), float(zmax)],
            "grid": {"origin_m_xz": [float(x[0]), float(z[0])] if len(x) and len(z) else [0., 0.],
                     "shape": [len(z), len(x)], "spacing_m": spacing,
                     "cell_count": estimated},
            "ports": {"count": len(points), "xyz_m": deepcopy(points)},
            "source_surface_m": bed.tolist(), "bed_m": bed.tolist(),
            "derived_bed_m": derived.tolist(),
            "cut_fill_m3": {"cut_m3": source_volume, "fill_m3": fill_volume,
                            "net_m3": fill_volume - source_volume},
            "material_ledger": ledger, "rejection_reasons": reasons,
            "protected_cells": 0, "open_boundary_cells": 0,
            "semantics": "bounded_derived_fine_bed_candidate_not_surveyed_dem"}


def build_fine_bed_material(paths, sections, patches, *, corridors=None,
                            target_spacing_m=2.0,
                            max_cut_m=4.0, max_cells_per_window=250_000,
                            max_total_cells=MAX_CELLS):
    if paths.get("schema") != "td-watershed-paths-v1" or sections.get("schema") != "td-watershed-sections-v1":
        raise ValueError("task06 paths and sections are required")
    if patches.get("schema") not in {
            "td-watershed-interface-patch-preparation-v2",
            "td-watershed-interface-patches-v1"}:
        raise ValueError("task07 preparation package is required")
    spacing = _finite(target_spacing_m, "target_spacing_m")
    limit = _finite(max_cut_m, "max_cut_m")
    if spacing <= 0 or limit <= 0 or max_cells_per_window <= 0 or max_total_cells <= 0:
        raise ValueError("positive fine budgets required")
    port_points = _ports(paths, sections, patches, corridors)
    rejected_reasons = [reason for patch in patches.get("patches", [])
                        for reason in patch.get("rejection_reasons", [])]
    protected = any("protected" in reason for reason in rejected_reasons)
    open_boundary = any("boundary" in reason or "outlet" in reason
                        for reason in rejected_reasons)
    groups = {}
    for point in port_points:
        groups.setdefault(_window_key([point], spacing), []).append(point)
    windows = []
    total = 0
    candidate_total = 0
    for key in sorted(groups):
        points = groups[key]
        window_id = "fine:" + ":".join(str(value) for value in key)
        window = _make_window(window_id, points, target_spacing_m=spacing, max_cut_m=limit,
                              max_cells=max_cells_per_window, protected=protected,
                              open_boundary=open_boundary)
        total += window["grid"]["cell_count"]
        if total > max_total_cells and window["status"] == "candidate":
            window["status"] = "refused"
            window["rejection_reasons"].append("total_fine_cell_budget_exceeded")
            window["bed_m"] = window["derived_bed_m"] = []
        if window["status"] == "candidate":
            candidate_total += window["grid"]["cell_count"]
        windows.append(window)
    result = {"schema": SCHEMA, "algorithm": ALGORITHM,
              "source_artifacts": {"paths_identity_sha256": paths["identity_sha256"],
                                    "sections_identity_sha256": sections["identity_sha256"],
                                    "patches_identity_sha256": patches["identity_sha256"],
                                    "corridors_identity_sha256": None if corridors is None else corridors.get("identity_sha256")},
              "parameters": {"target_spacing_m": spacing, "max_cut_m": limit,
                             "max_cells_per_window": int(max_cells_per_window),
                             "max_total_cells": int(max_total_cells)},
              "windows": windows,
              "summary": {"window_count": len(windows), "candidate_count": sum(w["status"] == "candidate" for w in windows),
                          "refused_count": sum(w["status"] == "refused" for w in windows),
                          "requested_cells": total, "candidate_cells": candidate_total},
              "semantics": "derived_fine_bed_candidate_with_explicit_cut_fill_material_ledger",
              **{name: False for name in FALSE_FLAGS}}
    result["shape_identity_sha256"] = _digest(_shape(result))
    result["identity_sha256"] = _digest(_identity(result))
    validate_fine_bed_material(result)
    return result


def validate_fine_bed_material(record):
    if record.get("schema") != SCHEMA or record.get("algorithm") != ALGORITHM:
        raise ValueError("fine bed schema mismatch")
    if any(record.get(name) is not False for name in FALSE_FLAGS):
        raise ValueError("fine bed certification flags must remain false")
    if record.get("shape_identity_sha256") != _digest(_shape(record)):
        raise ValueError("fine shape identity mismatch")
    if record.get("identity_sha256") != _digest(_identity(record)):
        raise ValueError("fine identity mismatch")
    total = 0
    for window in record.get("windows", []):
        grid = window["grid"]
        cells = int(grid["cell_count"])
        if cells < 0 or len(window["ports"]["xyz_m"]) != window["ports"]["count"]:
            raise ValueError("invalid fine window ports")
        if window["status"] == "candidate":
            if len(window["bed_m"]) * (len(window["bed_m"][0]) if window["bed_m"] else 0) != cells:
                raise ValueError("fine bed grid shape mismatch")
            if len(window["source_surface_m"]) != len(window["bed_m"]):
                raise ValueError("fine source surface shape mismatch")
            if any(float(value) < 0 for value in window["material_ledger"].values()):
                raise ValueError("negative material ledger")
        total += cells
    if total != record["summary"]["requested_cells"]:
        raise ValueError("fine cell summary mismatch")
    candidate_total = sum(window["grid"]["cell_count"] for window in record["windows"]
                          if window["status"] == "candidate")
    if candidate_total != record["summary"].get("candidate_cells"):
        raise ValueError("fine candidate cell summary mismatch")
    if len(record["windows"]) > MAX_WINDOWS or candidate_total > record["parameters"]["max_total_cells"]:
        raise ValueError("fine budget exceeded")
    return True


def save_fine_bed_material(record, path):
    validate_fine_bed_material(record)
    payload = _payload(record)
    if len(payload) > MAX_BYTES:
        raise ValueError("fine artifact exceeds byte budget")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def load_fine_bed_material(path, *, expected_sha256=None, expected_identity=None):
    target = Path(path)
    payload = target.read_bytes()
    if len(payload) > MAX_BYTES:
        raise ValueError("fine artifact exceeds byte budget")
    if expected_sha256 is not None and hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("fine artifact hash mismatch")
    record = json.loads(payload)
    validate_fine_bed_material(record)
    if expected_identity is not None and record["identity_sha256"] != expected_identity:
        raise ValueError("fine identity mismatch")
    return record
