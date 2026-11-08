"""Proof-bound rectangular refinement cells; not full-domain hydrology acceptance."""

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from types import MappingProxyType
import zipfile

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.surface_network_consumer import (
    _identity as _proof_identity, _payload, _plan_proof, _proof_gate,
)
from terrain_pipeline.surface_network_recovery import _fingerprint
from terrain_pipeline.surface_network_prepare import validate_surface_network

VERSION = "surface-fine-mosaic-v1.1"
MAX_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class DomainFineSource:
    proof: Mapping
    domain_id: int
    window_zx: tuple | None = None
    unknown_mask: np.ndarray | None = None
    protected_mask: np.ndarray | None = None
    role: str = "domain"


@dataclass(frozen=True)
class MosaicResources:
    max_cells: int = 100000
    max_retained_bytes: int = MAX_BYTES
    max_working_bytes: int = MAX_BYTES

    def __post_init__(self):
        for name, ceiling in (("max_cells", 100000), ("max_retained_bytes", MAX_BYTES),
                              ("max_working_bytes", MAX_BYTES)):
            if type(getattr(self, name)) is not int or not 0 < getattr(self, name) <= ceiling:
                raise ValueError("invalid resource bound: " + name)


class MosaicCoverageError(ValueError):
    def __init__(self, diagnostic):
        super().__init__("coverage gap: bbox cells lack validated source")
        self.diagnostic = diagnostic


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(child) for child in value]
    return value


def _freeze(value):
    if isinstance(value, np.ndarray):
        return np.frombuffer(np.ascontiguousarray(value).tobytes(), dtype=value.dtype).reshape(value.shape)
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(child) for child in value)
    return value


def _tree(value, arrays):
    if isinstance(value, np.ndarray):
        name = f"array_{len(arrays):05d}.npy"
        arrays[name] = value
        return {"$array": name, "dtype": value.dtype.str, "shape": list(value.shape), "sha256": array_hash(value)}
    if isinstance(value, Mapping):
        return {key: _tree(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_tree(child, arrays) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _identity(value):
    return hashlib.sha256(_json(_tree(value, {})).encode("utf8")).hexdigest()


def _seal(value):
    value["identity_sha256"] = _identity(value)
    return _freeze(value)


def _size(value):
    arrays = {}
    manifest = _tree(value, arrays)
    return sum(array.nbytes + 256 for array in arrays.values()) + len(_json(manifest).encode("utf8"))


def _cancel(cancel):
    if cancel is not None and cancel():
        raise InterruptedError("fine mosaic cancelled")


def sources_from_surface_domains(result):
    from terrain_pipeline.surface_domain_prepare import validate_surface_domains
    validate_surface_domains(result)
    if result["kind"] != "evaluation" or result["status"] != "prepared":
        raise ValueError("statically validated prepared domain evaluation required")
    return tuple(DomainFineSource(entry["recovery"], entry["domain_id"]) for entry in result["domains"])


def _source(source):
    if not isinstance(source, DomainFineSource):
        raise ValueError("accepted recovery proof required; plain arrays cannot self-certify")
    if type(source.domain_id) is not int or source.domain_id <= 0 or source.role not in ("domain", "extension"):
        raise ValueError("invalid explicit source id/role")
    proof = _plain(source.proof)
    arrays = _payload(proof)
    _proof_gate(proof, arrays)
    shape = arrays["source_surface_m"].shape
    window = source.window_zx or (0, shape[0], 0, shape[1])
    if (len(window) != 4 or any(type(value) is not int for value in window) or
            not 0 <= window[0] < window[1] <= shape[0] or
            not 0 <= window[2] < window[3] <= shape[1] or
            window[1] - window[0] < 2 or window[3] - window[2] < 2):
        raise ValueError("invalid proof fine window")
    unknown = np.zeros(shape, bool) if source.unknown_mask is None else np.asarray(source.unknown_mask)
    protected = arrays["protected_mask"].copy()
    if source.protected_mask is not None:
        restriction = np.asarray(source.protected_mask)
        if restriction.dtype != bool or restriction.shape != shape:
            raise ValueError("invalid protected support mask")
        protected |= restriction
    if unknown.dtype != bool or unknown.shape != shape:
        raise ValueError("invalid unknown support mask")
    return proof, {"domain_id": source.domain_id, "role": source.role,
                   "proof_sha256": proof["identity_sha256"], "window_zx": list(window),
                   "unknown_mask": unknown, "protected_mask": protected}


def _stencil(row, column, shape):
    top, left = int(math.floor(row)), int(math.floor(column))
    bottom, right = min(top + 1, shape[0] - 1), min(left + 1, shape[1] - 1)
    fraction_z, fraction_x = row - top, column - left
    indices = np.array([top * shape[1] + left, top * shape[1] + right,
                        bottom * shape[1] + left, bottom * shape[1] + right], np.int64)
    weights = np.array([(1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x,
                        fraction_z * (1 - fraction_x), fraction_z * fraction_x])
    return indices, weights


def _h0_support(proof):
    fine = proof["inputs"]["fine"]
    original = proof["inputs"]["plan"]
    coarse = original["identity"]["parameters"]
    shape = original["arrays"]["source_height_m"].shape
    fine_shape = fine["shape_zx"]
    indices = np.empty((math.prod(fine_shape), 4), np.int64)
    weights = np.empty(indices.shape)
    for row in range(fine_shape[0]):
        for column in range(fine_shape[1]):
            coarse_row = (fine["origin_z_m"] + row * fine["spacing_z_m"] - coarse["origin_z_m"]) / coarse["spacing_z_m"]
            coarse_column = (fine["origin_x_m"] + column * fine["spacing_x_m"] - coarse["origin_x_m"]) / coarse["spacing_x_m"]
            indices[row * fine_shape[1] + column], weights[row * fine_shape[1] + column] = _stencil(coarse_row, coarse_column, shape)
    return {"indices": indices, "weights": weights}


def _grid(sources, proofs, metric_grid, resources):
    fine_grids = [proofs[source["proof_sha256"]]["inputs"]["fine"] for source in sources]
    spacing_x = min(fine["spacing_x_m"] for fine in fine_grids)
    spacing_z = min(fine["spacing_z_m"] for fine in fine_grids)
    bounds = []
    for source, fine in zip(sources, fine_grids):
        for name, spacing in (("spacing_x_m", spacing_x), ("spacing_z_m", spacing_z)):
            ratio = fine[name] / spacing
            if not math.isclose(ratio, round(ratio), abs_tol=1e-8, rel_tol=0):
                raise ValueError("integer precision ratios required; no coarsening")
        top, bottom, left, right = source["window_zx"]
        bounds.append([fine["origin_x_m"] + left * fine["spacing_x_m"],
                       fine["origin_x_m"] + (right - 1) * fine["spacing_x_m"],
                       fine["origin_z_m"] + top * fine["spacing_z_m"],
                       fine["origin_z_m"] + (bottom - 1) * fine["spacing_z_m"]])
    bbox = metric_grid.get("bbox_xz_m", [min(item[0] for item in bounds), max(item[1] for item in bounds),
                                       min(item[2] for item in bounds), max(item[3] for item in bounds)])
    if (len(bbox) != 4 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or
                            not math.isfinite(value) for value in bbox) or
            bbox[1] <= bbox[0] or bbox[3] <= bbox[2]):
        raise ValueError("invalid mosaic bbox")
    columns_f, rows_f = (bbox[1] - bbox[0]) / spacing_x, (bbox[3] - bbox[2]) / spacing_z
    if any(not math.isclose(value, round(value), abs_tol=1e-8, rel_tol=0) for value in (columns_f, rows_f)):
        raise ValueError("bbox not aligned to refinement grid")
    rows, columns = round(rows_f), round(columns_f)
    if rows * columns > resources.max_cells:
        raise ValueError("mosaic cell resource limit")
    grid = {"coordinate_system": "metric-xz-m", "origin_x_m": float(bbox[0]), "origin_z_m": float(bbox[2]),
            "spacing_x_m": spacing_x, "spacing_z_m": spacing_z,
            "shape_cells_zx": [rows, columns], "bbox_xz_m": list(bbox)}
    rectangles = []
    for bound in bounds:
        rectangle = [(bound[2] - bbox[2]) / spacing_z, (bound[3] - bbox[2]) / spacing_z,
                     (bound[0] - bbox[0]) / spacing_x, (bound[1] - bbox[0]) / spacing_x]
        if any(not math.isclose(value, round(value), abs_tol=1e-8, rel_tol=0) for value in rectangle):
            raise ValueError("source origin not aligned to refinement grid")
        rectangles.append([round(value) for value in rectangle])
    return grid, rectangles


def _ownership(grid, rectangles):
    rows, columns = grid["shape_cells_zx"]
    owner = np.full((rows, columns), -1, np.int64)
    for source_id, (top, bottom, left, right) in enumerate(rectangles):
        if bottom <= 0 or right <= 0 or top >= rows or left >= columns:
            continue
        window = (slice(max(top, 0), min(bottom, rows)), slice(max(left, 0), min(right, columns)))
        if np.any(owner[window] != -1):
            raise ValueError("source interior cells overlap; ownership must be unique")
        owner[window] = source_id
    return owner


def prepare_fine_mosaic(domains, *, metric_grid, vertical_datum, source_identity,
                        sea_level_elevation_m, source_extensions=(), seam_tolerance_m=1e-8,
                        q_tolerance_m3_s=1e-8, resources=MosaicResources(), cancel=None):
    if isinstance(domains, Mapping) and domains.get("kind") == "evaluation":
        entries = list(sources_from_surface_domains(domains))
    else:
        entries = list(domains)
    extensions = list(source_extensions)
    if any(not isinstance(source, DomainFineSource) or source.role != "extension" for source in extensions):
        raise ValueError("explicit proof-bound extension source required")
    entries += extensions
    if not entries or len(entries) > 128 or not isinstance(resources, MosaicResources):
        raise ValueError("invalid mosaic source/resource count")
    if not isinstance(metric_grid, Mapping) or metric_grid.get("coordinate_system") != "metric-xz-m":
        raise ValueError("explicit metric-xz-m grid required")
    if any(not isinstance(value, str) or not value.strip() for value in (vertical_datum, source_identity)):
        raise ValueError("explicit datum/source identity required")
    for value in (sea_level_elevation_m, seam_tolerance_m, q_tolerance_m3_s):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("invalid sea/tolerance")
    if not 0 < seam_tolerance_m <= 1e-8 or not 0 < q_tolerance_m3_s <= 1e-8:
        raise ValueError("tolerances cannot weaken source gates")
    _cancel(cancel)
    if _size([source.proof for source in entries if isinstance(source, DomainFineSource)]) > resources.max_retained_bytes:
        raise ValueError("retained proof resource preflight limit")
    proofs, sources, support = {}, [], {}
    for entry in entries:
        _cancel(cancel)
        proof, source = _source(entry)
        if proof["inputs"]["plan"]["identity"]["parameters"]["sea_level_elevation_m"] != sea_level_elevation_m:
            raise ValueError("source sea datum differs")
        if source["domain_id"] in [item["domain_id"] for item in sources]:
            raise ValueError("source ids must be unique")
        proofs[proof["identity_sha256"]] = proof
        sources.append(source)
    grid, rectangles = _grid(sources, proofs, metric_grid, resources)
    cell_count = math.prod(grid["shape_cells_zx"])
    retained_bytes = _size({"proofs": proofs, "sources": sources})
    support_bytes = sum(math.prod(proof["inputs"]["fine"]["shape_zx"]) * 64 for proof in proofs.values())
    if retained_bytes + support_bytes + cell_count * 640 > min(resources.max_working_bytes, resources.max_retained_bytes):
        raise ValueError("working/retained resource preflight limit")
    owner = _ownership(grid, rectangles)
    for identity, proof in proofs.items():
        _cancel(cancel)
        support[identity] = _h0_support(proof)
    result = {"algorithm_version": VERSION, "status": "prepared", "scope": "accepted_recovery_engineering_bbox_cells",
              "vertical_datum": vertical_datum, "datum_evidence": "caller_declared_not_independently_certified",
              "source_identity": source_identity, "sea_level_elevation_m": sea_level_elevation_m,
              "seam_tolerance_m": float(seam_tolerance_m), "q_tolerance_m3_s": float(q_tolerance_m3_s),
              "resources": vars(resources), "grid": grid, "proofs": proofs, "proof_h0_support": support,
              "sources": sources, "cell_owner": owner, "full_domain_mosaic_prepared": False,
              "natural_outlets_certified": False}
    if np.any(owner < 0):
        result.update(status="diagnostic", failures=["coverage_gap_without_validated_source"],
                      missing_cell_count=int((owner < 0).sum()))
        raise MosaicCoverageError(_seal(result))
    result.update(_assemble(result, cancel))
    result["failures"] = []
    sealed = _seal(result)
    validate_fine_mosaic(sealed)
    return sealed


def _evaluate_support(source, arrays, indices, weights, tolerance):
    positive = weights > 0
    if np.any(source["unknown_mask"].ravel()[indices[positive]]) or not np.all(arrays["domain_mask"].ravel()[indices[positive]]):
        raise ValueError("unknown or outside-domain positive-weight source support")
    h0 = float(np.dot(arrays["source_surface_m"].ravel()[indices], weights))
    h2 = float(np.dot(arrays["final_surface_m"].ravel()[indices], weights))
    protected = bool(np.any(source["protected_mask"].ravel()[indices[positive]]))
    if protected and np.any(np.abs(arrays["total_cut_m"].ravel()[indices[positive]]) > tolerance):
        raise ValueError("protected source support was modified")
    stages = arrays["water_surface_m"].ravel()[indices[positive]]
    wet = bool(np.all(arrays["wet_mask"].ravel()[indices[positive]]))
    if protected and np.any(arrays["wet_mask"].ravel()[indices[positive]]):
        raise ValueError("protected source support is wet")
    water = float(np.dot(stages, weights[positive])) if wet else 0.
    if not math.isfinite(h0) or not math.isfinite(h2) or h2 > h0 + tolerance or (wet and water <= h2):
        raise ValueError("invalid H0/H2 or actual wet support")
    return h0, h2, wet, water, protected


def _mesh(grid):
    rows, columns = grid["shape_cells_zx"]
    top_left = np.arange(rows)[:, None] * (columns + 1) + np.arange(columns)[None, :]
    cells = np.stack((top_left, top_left + 1, top_left + columns + 2, top_left + columns + 1), axis=-1).reshape(-1, 4)
    triangles = np.empty((len(cells) * 2, 3), np.int64)
    triangles[::2], triangles[1::2] = cells[:, [0, 1, 2]], cells[:, [0, 2, 3]]
    return cells, triangles


def _assemble(result, cancel):
    grid, sources = result["grid"], result["sources"]
    rows, columns = grid["shape_cells_zx"]
    count, node_count = rows * columns, (rows + 1) * (columns + 1)
    nodes = {name: np.zeros(node_count, bool if name.endswith("mask") else float)
             for name in ("x_m", "z_m", "h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask")}
    nodes["x_m"] = np.tile(grid["origin_x_m"] + np.arange(columns + 1) * grid["spacing_x_m"], rows + 1)
    nodes["z_m"] = np.repeat(grid["origin_z_m"] + np.arange(rows + 1) * grid["spacing_z_m"], columns + 1)
    seen = np.zeros(node_count, bool)
    cells, triangles = _mesh(grid)
    source_cells = np.empty((count, 2), np.int64)
    indices = np.empty((count, 4, 4), np.int64)
    weights = np.empty(indices.shape, float)
    payloads = {identity: _payload(proof) for identity, proof in result["proofs"].items()}
    for cell_id, cell in enumerate(cells):
        if cell_id % columns == 0:
            _cancel(cancel)
        source = sources[int(result["cell_owner"].ravel()[cell_id])]
        fine = result["proofs"][source["proof_sha256"]]["inputs"]["fine"]
        arrays = payloads[source["proof_sha256"]]
        for corner_id, node_id in enumerate(cell):
            source_row = (nodes["z_m"][node_id] - fine["origin_z_m"]) / fine["spacing_z_m"]
            source_column = (nodes["x_m"][node_id] - fine["origin_x_m"]) / fine["spacing_x_m"]
            contributor, weight = _stencil(source_row, source_column, tuple(fine["shape_zx"]))
            indices[cell_id, corner_id], weights[cell_id, corner_id] = contributor, weight
            if corner_id == 0:
                source_cells[cell_id] = (math.floor(source_row + 1e-10), math.floor(source_column + 1e-10))
            values = _evaluate_support(source, arrays, contributor, weight, result["seam_tolerance_m"])
            for name, value in zip(("h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask"), values):
                if seen[node_id] and ((isinstance(value, bool) and nodes[name][node_id] != value) or
                                     (not isinstance(value, bool) and abs(nodes[name][node_id] - value) > result["seam_tolerance_m"])):
                    raise ValueError("shared seam conflict in H0/H2/actual wet/protection")
                nodes[name][node_id] = value
            seen[node_id] = True
    output = {"nodes": nodes, "cells": cells, "triangles": triangles,
              "contributors": {"source_cell_zx": source_cells, "indices": indices, "weights": weights},
              "wet_cells": nodes["wet_mask"][cells].all(axis=1)}
    output["q_cuts"], q_summary = _q_cut(result, payloads)
    output["summary"] = _integrals(grid, output, q_summary)
    return output


def _q_cut(result, payloads):
    records, positions_seen = {}, set()
    total_local, total_out, total_in = 0., 0., 0.
    bbox = result["grid"]["bbox_xz_m"]
    groups = {}
    for identity, arrays in payloads.items():
        graph_key = _identity({name: arrays[name] for name in
                              ("world_xz_m", "receiver", "order", "discharge_m3_s", "active_mask",
                               "outlet_mask", "local_discharge_m3_s", "node_stage_m")})
        groups.setdefault(graph_key, []).append(identity)
    for graph_key, identities in groups.items():
        arrays = payloads[identities[0]]
        selected = np.zeros(arrays["receiver"].shape, bool)
        positions = arrays["world_xz_m"]
        for source in result["sources"]:
            if source["proof_sha256"] not in identities:
                continue
            fine = result["proofs"][source["proof_sha256"]]["inputs"]["fine"]
            top, bottom, left, right = source["window_zx"]
            source_x = (positions[:, 0] - fine["origin_x_m"]) / fine["spacing_x_m"]
            source_z = (positions[:, 1] - fine["origin_z_m"]) / fine["spacing_z_m"]
            selected |= ((source_z >= top) & (source_z <= bottom - 1) & (source_x >= left) & (source_x <= right - 1))
        selected &= ((positions[:, 0] >= bbox[0]) & (positions[:, 0] <= bbox[1]) &
                     (positions[:, 1] >= bbox[2]) & (positions[:, 1] <= bbox[3]))
        carries_q = (arrays["active_mask"] | (arrays["local_discharge_m3_s"] != 0) |
                     (arrays["discharge_m3_s"] != 0))
        for position in positions[selected & carries_q]:
            key = tuple(position)
            if key in positions_seen:
                raise ValueError("duplicate nonzero Q graph ownership across independent proofs")
            positions_seen.add(key)
        receiver = arrays["receiver"]
        internal = receiver >= 0
        target_selected = np.zeros(selected.shape, bool)
        target_selected[internal] = selected[receiver[internal]]
        outgoing = np.flatnonzero(selected & ~target_selected)
        incoming = np.flatnonzero(~selected & target_selected)
        local = float(arrays["local_discharge_m3_s"][selected].sum())
        outflow = float(arrays["discharge_m3_s"][outgoing].sum())
        inflow = float(arrays["discharge_m3_s"][incoming].sum())
        if abs(outflow - inflow - local) > result["q_tolerance_m3_s"]:
            raise ValueError("nonconservative local-cut Q")
        records[graph_key] = {"proof_sha256": sorted(identities),
                             "selected_nodes": np.flatnonzero(selected), "outgoing_nodes": outgoing,
                             "incoming_nodes": incoming, "local_m3_s": local,
                             "outgoing_m3_s": outflow, "incoming_m3_s": inflow,
                             "terminal_nodes": np.flatnonzero(selected & arrays["outlet_mask"] & arrays["active_mask"])}
        total_local += local
        total_out += outflow
        total_in += inflow
    return records, {"q_semantics": "unique_local_cut_not_sum_accumulated_nodes",
                     "q_local_m3_s": total_local, "q_outgoing_m3_s": total_out, "q_incoming_m3_s": total_in}


def _integrals(grid, output, q_summary):
    nodes, triangles = output["nodes"], output["triangles"]
    area = grid["spacing_x_m"] * grid["spacing_z_m"]
    cut = float(((nodes["h0_m"] - nodes["h2_m"])[triangles].mean(axis=1) * area / 2).sum())
    wet_triangles = triangles[np.repeat(output["wet_cells"], 2)]
    volume = float(((nodes["water_surface_m"] - nodes["h2_m"])[wet_triangles].mean(axis=1) * area / 2).sum())
    return {"unique_cell_area_m2": len(output["cells"]) * area, "unique_cut_volume_m3": cut,
            "actual_wet_water_volume_m3": volume, **q_summary}


def _support_check(indices, weights, source_shape, target_x, target_z, source_grid):
    if (indices.dtype != np.dtype("int64") or weights.dtype != np.dtype("float64") or
            indices.shape != weights.shape or indices.shape != np.shape(target_x) + (4,) or
            np.any(indices < 0) or np.any(indices >= math.prod(source_shape)) or
            not np.isfinite(weights).all() or np.any(weights < 0) or
            not np.allclose(weights.sum(axis=-1), 1., atol=1e-10, rtol=0)):
        raise ValueError("invalid saved contributor indices/weights")
    target_column = (target_x - source_grid["origin_x_m"]) / source_grid["spacing_x_m"]
    target_row = (target_z - source_grid["origin_z_m"]) / source_grid["spacing_z_m"]
    left, top = np.floor(target_column + 1e-10).astype(np.int64), np.floor(target_row + 1e-10).astype(np.int64)
    fraction_x, fraction_z = target_column - left, target_row - top
    expected_indices = np.stack((top * source_shape[1] + left,
                                top * source_shape[1] + np.minimum(left + 1, source_shape[1] - 1),
                                np.minimum(top + 1, source_shape[0] - 1) * source_shape[1] + left,
                                np.minimum(top + 1, source_shape[0] - 1) * source_shape[1] + np.minimum(left + 1, source_shape[1] - 1)), axis=-1)
    expected_weights = np.stack(((1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x,
                                 fraction_z * (1 - fraction_x), fraction_z * fraction_x), axis=-1)
    if not np.array_equal(indices, expected_indices) or not np.allclose(weights, expected_weights, atol=1e-10, rtol=0):
        raise ValueError("saved contributors are not original local bilinear support")


def _static_proof(proof, support):
    if _fingerprint({key: value for key, value in proof.items() if key != "identity_sha256"}) != proof["identity_sha256"]:
        raise ValueError("saved recovery source hash mismatch")
    if (proof["status"] != "accepted" or proof["accepted"] is not True or not proof["attempts"] or
            proof["attempts"][-1]["accepted"] is not True or
            proof["selected_method"] != proof["attempts"][-1]["method"] or any(proof["attempts"][-1]["failures"].values())):
        raise ValueError("saved source is not accepted recovery")
    original_local, original_total = _plan_proof(proof["inputs"]["plan"])
    final_local, final_total = _plan_proof(proof["final_plan"])
    if not np.allclose(original_local, final_local, atol=1e-8, rtol=0) or not math.isclose(original_total, final_total, abs_tol=1e-8, rel_tol=0):
        raise ValueError("saved source changes local/outlet Q")
    surface = proof["surface"]
    validate_surface_network(surface)
    params = _proof_identity(surface)
    if (surface["status"] != "prepared" or surface["summary"]["publishable"] is not True or
            any(surface["summary"]["budget_failures"].values()) or any(surface["summary"]["joint_blockers"].values()) or
            params["plan_sha256"] != proof["final_plan"]["identity_sha256"] or
            params["summary_sha256"] != digest(surface["summary"]) or
            params["output_sha256"] != digest({name: array_hash(array) for name, array in surface["arrays"].items()}) or
            any(params[name] != value for name, value in proof["inputs"]["budget"].items())):
        raise ValueError("saved source surface acceptance/budget identity differs")
    arrays = _payload(proof)
    shape = tuple(proof["inputs"]["fine"]["shape_zx"])
    original = proof["inputs"]["plan"]
    fine = proof["inputs"]["fine"]
    target_x = np.tile(fine["origin_x_m"] + np.arange(shape[1]) * fine["spacing_x_m"], shape[0])
    target_z = np.repeat(fine["origin_z_m"] + np.arange(shape[0]) * fine["spacing_z_m"], shape[1])
    _support_check(support["indices"], support["weights"], original["arrays"]["source_height_m"].shape,
                   target_x, target_z, original["identity"]["parameters"])
    supported_h0 = (original["arrays"]["source_height_m"].ravel()[support["indices"]] * support["weights"]).sum(axis=1)
    if not np.allclose(supported_h0, arrays["source_surface_m"].ravel(), atol=1e-8, rtol=0):
        raise ValueError("saved H0 lacks original source support")
    for name in ("source_surface_m", "valley_surface_m", "final_surface_m", "water_surface_m"):
        if arrays[name].shape != shape or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid saved fine source geometry")
    for name in ("domain_mask", "protected_mask", "legal_outlet_mask"):
        if arrays[name].dtype != bool or not np.array_equal(arrays[name], fine[name]):
            raise ValueError("saved source masks differ from original constraints")
    for name, difference in (("valley_cut_m", arrays["source_surface_m"] - arrays["valley_surface_m"]),
                             ("bed_cut_m", arrays["valley_surface_m"] - arrays["final_surface_m"]),
                             ("total_cut_m", arrays["source_surface_m"] - arrays["final_surface_m"])):
        if np.any(difference < -1e-8) or not np.allclose(arrays[name], difference, atol=1e-8, rtol=0):
            raise ValueError("saved source H0/H2/cuts disagree")
    wet, protected = arrays["wet_mask"], arrays["protected_mask"]
    if (wet.dtype != bool or wet.shape != shape or not wet.any() or
            np.any(wet & (~arrays["domain_mask"] | protected)) or
            np.any(arrays["water_surface_m"][wet] <= arrays["final_surface_m"][wet]) or
            np.any(arrays["water_surface_m"][~wet] != 0) or
            np.any((arrays["total_cut_m"] > 1e-8) & (~arrays["domain_mask"] | protected))):
        raise ValueError("saved source actual wet/protection invalid")
    for name in ("disconnected_seed_mask", "boundary_contact_mask", "reach_limited_mask"):
        if surface["arrays"][name].dtype != bool or np.any(surface["arrays"][name]):
            raise ValueError("saved source retains failed inundation")
    ledger, valley = proof["fine_ledger"], proof["valley"]
    if (ledger is None) != (valley is None):
        raise ValueError("saved valley requires cumulative fine ledger")
    if ledger is not None:
        ledger_params, valley_params = _proof_identity(ledger), _proof_identity(valley)
        if (ledger["status"] != "prepared" or any(ledger["summary"]["failures"].values()) or
                valley["summary"]["geometry_feasible"] is not True or any(valley["summary"]["failures"].values()) or
                ledger_params["surface_identity_sha256"] != surface["identity_sha256"] or
                ledger_params["valley_identity_sha256"] != valley["identity_sha256"] or
                ledger_params["summary_sha256"] != digest(ledger["summary"]) or
                ledger_params["arrays_sha256"] != digest({name: array_hash(array) for name, array in ledger["arrays"].items()}) or
                valley_params["replanned_sha256"] != proof["final_plan"]["identity_sha256"] or
                valley_params["summary_sha256"] != digest(valley["summary"]) or
                valley_params["arrays_sha256"] != digest({name: {"sha256": array_hash(array),
                    "shape": list(array.shape), "dtype": array.dtype.str}
                    for name, array in sorted(valley["arrays"].items())}) or
                any(valley_params[name] != value or ledger_params[name] != value
                    for name, value in proof["inputs"]["valley_recipe"].items())):
            raise ValueError("saved valley/ledger proof inconsistent")
        for name in ("source_surface_m", "valley_surface_m", "final_surface_m", "valley_cut_m", "bed_cut_m", "total_cut_m"):
            if not np.allclose(ledger["arrays"][name], arrays[name], atol=1e-8, rtol=0):
                raise ValueError("saved cumulative ledger source disagrees")
    active = arrays["active_mask"]
    positions = arrays["world_xz_m"]
    columns = np.rint((positions[:, 0] - fine["origin_x_m"]) / fine["spacing_x_m"]).astype(int)
    rows = np.rint((positions[:, 1] - fine["origin_z_m"]) / fine["spacing_z_m"]).astype(int)
    if (not np.all(wet[rows[active], columns[active]]) or
            not np.all(arrays["legal_outlet_mask"][rows[active & arrays["outlet_mask"]], columns[active & arrays["outlet_mask"]]]) or
            not np.allclose(arrays["final_surface_m"][rows[active], columns[active]],
                            proof["final_plan"]["arrays"]["bounded_bed_m"].ravel()[active],
                            atol=proof["inputs"]["budget"]["bed_match_tolerance_m"], rtol=0)):
        raise ValueError("saved graph bed/actual wet/terminal support disagrees")
    _static_geometry(proof, arrays, support, rows, columns)
    return arrays


def _static_geometry(proof, arrays, support, rows, columns):
    fine, inputs = proof["inputs"]["fine"], proof["inputs"]
    shape = tuple(fine["shape_zx"])
    original, final = inputs["plan"], proof["final_plan"]
    weights = support["weights"]
    h1 = (final["arrays"]["source_height_m"].ravel()[support["indices"]] * weights).sum(axis=1)
    if not np.allclose(h1, arrays["valley_surface_m"].ravel(), atol=1e-8, rtol=0):
        raise ValueError("saved H1 does not match final plan source support")
    if proof["valley"] is None:
        if not np.array_equal(original["arrays"]["source_height_m"], final["arrays"]["source_height_m"]):
            raise ValueError("non-valley source changed H0")
    else:
        valley = proof["valley"]["arrays"]
        if (not np.array_equal(valley["source_height_m"], original["arrays"]["source_height_m"]) or
                not np.array_equal(valley["valley_surface_m"], final["arrays"]["source_height_m"])):
            raise ValueError("saved valley H0/H1 source chain differs")
    active, receiver = arrays["active_mask"], arrays["receiver"]
    wet, water = arrays["wet_mask"], arrays["water_surface_m"]
    domain, protected = arrays["domain_mask"], arrays["protected_mask"]
    if (not np.array_equal(domain[rows, columns], inputs["coarse_domain"].ravel()) or
            not np.array_equal(protected[rows, columns], inputs["coarse_protected"].ravel()) or
            np.any(active & (~inputs["coarse_domain"].ravel() | inputs["coarse_protected"].ravel()))):
        raise ValueError("saved graph masks differ from fine constraints")
    if not np.array_equal(original["arrays"]["channel_mask"] & original["arrays"]["outlet_mask"],
                          final["arrays"]["channel_mask"] & final["arrays"]["outlet_mask"]):
        raise ValueError("saved active terminal graph changed")
    for recipe_name in ("budget", "stage_recipe", "valley_recipe", "inundation_recipe", "section_recipe"):
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
               for value in inputs[recipe_name].values()):
            raise ValueError("invalid original numeric recipe")
    min_depth, max_depth = inputs["stage_recipe"]["min_clearance_m"], inputs["stage_recipe"]["max_depth_m"]
    stage = arrays["node_stage_m"]
    plan_arrays, plan_params = final["arrays"], final["identity"]["parameters"]
    if (not np.array_equal(plan_arrays["channel_mask"], plan_arrays["discharge_m3_s"] >= plan_params["start_discharge_m3_s"]) or
            not np.array_equal(plan_arrays["outlet_mask"].ravel(), receiver < 0)):
        raise ValueError("saved graph channel/terminal masks differ from Q/topology")
    for name, reference, exponent, minimum, maximum in (
            ("nominal_width_m", "reference_width_m", "width_exponent", "min_width_m", "max_width_m"),
            ("nominal_depth_m", "reference_depth_m", "depth_exponent", "min_depth_m", "max_depth_m")):
        expected = np.clip(plan_params[reference] * (arrays["discharge_m3_s"][active] /
                           plan_params["reference_discharge_m3_s"]) ** plan_params[exponent],
                           plan_params[minimum], plan_params[maximum])
        if not np.allclose(plan_arrays[name].ravel()[active], expected, atol=1e-8, rtol=0):
            raise ValueError("saved nominal section differs from graph Q recipe")
    bed = plan_arrays["bounded_bed_m"].ravel()
    preferred = bed + np.maximum(plan_arrays["nominal_depth_m"].ravel(), min_depth)
    terminals = np.flatnonzero(active & arrays["outlet_mask"])
    if not np.allclose(stage[terminals], inputs["outlet_stage_m"], atol=1e-8, rtol=0):
        raise ValueError("saved terminal stage differs from original boundary")
    if (np.any(stage[active] - bed[active] < min_depth - 1e-9) or
            np.any(stage[active] - bed[active] > max_depth + 1e-9) or
            np.any(stage[active] > preferred[active] + inputs["stage_recipe"]["max_lift_above_nominal_m"] + 1e-9)):
        raise ValueError("saved stage depth/lift differs from original recipe")
    for donor in np.flatnonzero(active & (receiver >= 0)):
        target = int(receiver[donor])
        if not active[target]:
            raise ValueError("active graph edge leaves delivered channel")
        distance = float(np.linalg.norm(arrays["world_xz_m"][donor] - arrays["world_xz_m"][target]))
        expected_stage = max(preferred[donor], stage[target] + inputs["stage_recipe"]["min_stage_slope_m_per_m"] * distance)
        if abs(stage[donor] - expected_stage) > 1e-8:
            raise ValueError("saved source stage violates original static stage equation")
        steps = max(abs(rows[target] - rows[donor]), abs(columns[target] - columns[donor]))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            row = int(round(rows[donor] + fraction * (rows[target] - rows[donor])))
            column = int(round(columns[donor] + fraction * (columns[target] - columns[donor])))
            stage_here = stage[donor] * (1 - fraction) + stage[target] * fraction
            bed_here = arrays["final_surface_m"][row, column]
            if (not wet[row, column] or stage_here - bed_here < min_depth - 1e-9 or
                    stage_here - bed_here > max_depth + 1e-9 or
                    (previous_bed is not None and bed_here > previous_bed + 1e-9)):
                raise ValueError("saved channel edge dry/blocked/reverse or depth budget exceeded")
            previous_bed = bed_here
    boundary = np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    legal = arrays["legal_outlet_mask"]
    if np.any(wet & boundary & ~legal) or np.any(legal & (~domain | protected)):
        raise ValueError("saved wet boundary lacks legal outlet support")
    reached = np.zeros(shape, bool)
    stack = list(map(tuple, np.argwhere(wet & legal)))
    for row, column in stack:
        reached[row, column] = True
    while stack:
        row, column = stack.pop()
        for next_row, next_column in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
            if (0 <= next_row < shape[0] and 0 <= next_column < shape[1] and wet[next_row, next_column] and
                    not reached[next_row, next_column]):
                reached[next_row, next_column] = True
                stack.append((next_row, next_column))
    if not np.array_equal(reached, wet):
        raise ValueError("saved actual wet water disconnected from legal terminals")
    threshold = max(.5, inputs["inundation_recipe"]["min_water_depth_m"] * 10)
    for before, after in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[:, :-1], np.s_[:, 1:])):
        adjacent = wet[before] & wet[after]
        if np.any(adjacent & (np.abs(water[before] - water[after]) > threshold + 1e-9)):
            raise ValueError("saved actual wet stage transition exceeds source gate")
    quadrature = np.ones(shape)
    quadrature[[0, -1], :] *= .5
    quadrature[:, [0, -1]] *= .5
    cell_area = fine["spacing_x_m"] * fine["spacing_z_m"]
    budget = inputs["budget"]
    bed_cut, valley_cut, total_cut = (arrays[name] for name in ("bed_cut_m", "valley_cut_m", "total_cut_m"))
    def area(cut):
        return float(np.sum((cut > 1e-9) * quadrature) * cell_area)
    def volume(cut):
        return float(np.sum(cut * quadrature) * cell_area)
    if (np.any(bed_cut > budget["max_bed_cut_m"] + 1e-9) or
            area(bed_cut) > budget["max_area_m2"] + 1e-9 or volume(bed_cut) > budget["max_cut_volume_m3"] + 1e-9):
        raise ValueError("saved actual bed exceeds original budget")
    if proof["valley"] is not None:
        recipe = inputs["valley_recipe"]
        if (np.any(valley_cut > recipe["max_valley_depth_m"] + 1e-9) or
                area(valley_cut) > recipe["max_valley_area_m2"] + 1e-9 or
                volume(valley_cut) > recipe["max_valley_volume_m3"] + 1e-9 or
                area(total_cut) > recipe["max_total_cut_area_m2"] + 1e-9 or
                volume(total_cut) > recipe["max_total_cut_volume_m3"] + 1e-9):
            raise ValueError("saved cumulative fine ledger exceeds original budget")
    if np.any(bed_cut > inputs["section_recipe"]["max_local_cut_m"] + 1e-9):
        raise ValueError("saved source exceeds original local section budget")
    _static_water_support(proof, arrays)


def _static_water_support(proof, arrays):
    """Algebraic source-stage support at saved cells, not an inundation replay."""
    fine, inputs = proof["inputs"]["fine"], proof["inputs"]
    donors = np.flatnonzero(arrays["active_mask"] & (arrays["receiver"] >= 0))
    targets = arrays["receiver"][donors]
    starts, ends = arrays["world_xz_m"][donors], arrays["world_xz_m"][targets]
    vectors = ends - starts
    length_squared = (vectors * vectors).sum(axis=1)
    width = proof["final_plan"]["arrays"]["nominal_width_m"].ravel()
    stages = arrays["node_stage_m"]
    shape = tuple(fine["shape_zx"])
    saved_seeds = proof["surface"]["arrays"]["channel_seed_mask"]
    if not len(donors):
        raise ValueError("accepted wet source lacks supporting graph edges")
    for row in range(shape[0]):
        for column in range(shape[1]):
            position = np.array([fine["origin_x_m"] + column * fine["spacing_x_m"],
                                 fine["origin_z_m"] + row * fine["spacing_z_m"]])
            fractions = np.clip(((position - starts) * vectors).sum(axis=1) / length_squared, 0., 1.)
            distances = np.linalg.norm(position - starts - fractions[:, None] * vectors, axis=1)
            nearest = 0
            for index in range(1, len(donors)):
                if distances[index] < distances[nearest] - 1e-9:
                    nearest = index
            local_stages = stages[donors] * (1 - fractions) + stages[targets] * fractions
            radius = (width[donors] * (1 - fractions) + width[targets] * fractions) / 2
            stage_here = local_stages[nearest]
            seed = (bool(np.any(distances <= np.maximum(radius / 2, min(fine["spacing_x_m"], fine["spacing_z_m"]) / 2))) and
                    stage_here > arrays["final_surface_m"][row, column] + inputs["inundation_recipe"]["min_water_depth_m"] and
                    arrays["domain_mask"][row, column] and not arrays["protected_mask"][row, column])
            if bool(saved_seeds[row, column]) != bool(seed):
                raise ValueError("saved channel seed differs from actual graph/section/stage support")
            if arrays["wet_mask"][row, column] and (
                    abs(arrays["water_surface_m"][row, column] - stage_here) > 1e-8 or
                    stage_here <= arrays["final_surface_m"][row, column] + inputs["inundation_recipe"]["min_water_depth_m"] or
                    (not seed and distances[nearest] > inputs["inundation_recipe"]["max_lateral_reach_m"] + 1e-9)):
                raise ValueError("saved wet water stage lacks original graph support")


def validate_fine_mosaic(result, *, allow_unprepared=False):
    """Check saved source/contributors/topology/Q without generating a mosaic."""
    try:
        record = _plain(result)
        identity = record.pop("identity_sha256")
        if record["algorithm_version"] != VERSION or _identity(record) != identity:
            raise ValueError("fine mosaic identity mismatch")
        if record["full_domain_mosaic_prepared"] is not False or record["natural_outlets_certified"] is not False:
            raise ValueError("engineering cells cannot certify full domains/natural outlets")
        if (record["scope"] != "accepted_recovery_engineering_bbox_cells" or
                record["datum_evidence"] != "caller_declared_not_independently_certified" or
                any(not isinstance(record[name], str) or not record[name].strip()
                    for name in ("vertical_datum", "source_identity"))):
            raise ValueError("invalid saved scope/datum")
        for name in ("seam_tolerance_m", "q_tolerance_m3_s"):
            if type(record[name]) not in (int, float) or not 0 < record[name] <= 1e-8:
                raise ValueError("invalid saved tolerance")
        resources = MosaicResources(**record["resources"])
        if _size(result) > resources.max_retained_bytes:
            raise ValueError("saved mosaic retained resource limit")
        cell_count = math.prod(record["grid"]["shape_cells_zx"])
        if _size(result) + cell_count * 640 > resources.max_working_bytes:
            raise ValueError("saved mosaic working resource limit")
        if not 0 < len(record["sources"]) <= 128 or set(record["proofs"]) != set(record["proof_h0_support"]):
            raise ValueError("saved source/proof set invalid")
        payloads = {}
        for identity, proof in record["proofs"].items():
            if (identity != proof["identity_sha256"] or
                    proof["inputs"]["plan"]["identity"]["parameters"]["sea_level_elevation_m"] != record["sea_level_elevation_m"]):
                raise ValueError("saved proof key/sea mismatch")
            payloads[identity] = _static_proof(proof, record["proof_h0_support"][identity])
        ids = []
        for source in record["sources"]:
            if (type(source["domain_id"]) is not int or source["domain_id"] <= 0 or
                    source["domain_id"] in ids or source["role"] not in ("domain", "extension")):
                raise ValueError("saved source id/role invalid")
            ids.append(source["domain_id"])
            arrays = payloads[source["proof_sha256"]]
            shape = arrays["source_surface_m"].shape
            for name in ("unknown_mask", "protected_mask"):
                if source[name].dtype != bool or source[name].shape != shape:
                    raise ValueError("saved source support mask invalid")
            if np.any(arrays["protected_mask"] & ~source["protected_mask"]):
                raise ValueError("saved source removes protection")
            top, bottom, left, right = source["window_zx"]
            if (any(type(value) is not int for value in source["window_zx"]) or
                    not 0 <= top < bottom <= shape[0] or not 0 <= left < right <= shape[1] or
                    bottom - top < 2 or right - left < 2):
                raise ValueError("saved source window invalid")
        _validate_coverage(record, resources)
        owner = record["cell_owner"]
        if record["status"] == "diagnostic":
            if (not allow_unprepared or not np.any(owner < 0) or
                    record["missing_cell_count"] != int((owner < 0).sum()) or
                    record["failures"] != ["coverage_gap_without_validated_source"] or "nodes" in record):
                raise ValueError("unprepared gap diagnostic cannot be published as mosaic")
            return True
        if record["status"] != "prepared" or record["failures"] or np.any(owner < 0):
            raise ValueError("only completely covered bbox cells are prepared")
        _validate_mesh(record, payloads)
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("invalid fine mosaic semantic record") from error


def _validate_coverage(record, resources):
    grid, owner = record["grid"], record["cell_owner"]
    rows, columns = grid["shape_cells_zx"]
    if (type(rows) is not int or type(columns) is not int or rows <= 0 or columns <= 0 or
            rows * columns > resources.max_cells or owner.dtype != np.dtype("int64") or
            owner.shape != (rows, columns) or np.any(owner < -1) or np.any(owner >= len(record["sources"]))):
        raise ValueError("saved cell ownership shape/range invalid")
    bbox = grid["bbox_xz_m"]
    fine_grids = [record["proofs"][source["proof_sha256"]]["inputs"]["fine"] for source in record["sources"]]
    for axis, count, first, last in (("x", columns, bbox[0], bbox[1]), ("z", rows, bbox[2], bbox[3])):
        spacing = grid["spacing_" + axis + "_m"]
        if (spacing != min(fine["spacing_" + axis + "_m"] for fine in fine_grids) or
                grid["origin_" + axis + "_m"] != first or
                not math.isclose(first + spacing * count, last, abs_tol=1e-8, rel_tol=0)):
            raise ValueError("saved grid is not common finest refinement")
    if grid["coordinate_system"] != "metric-xz-m":
        raise ValueError("invalid saved coordinate system")
    for row in range(rows):
        for column in range(columns):
            matches = []
            for source_id, (source, fine) in enumerate(zip(record["sources"], fine_grids)):
                top, bottom, left, right = source["window_zx"]
                grid_left = (fine["origin_x_m"] + left * fine["spacing_x_m"] - bbox[0]) / grid["spacing_x_m"]
                grid_right = (fine["origin_x_m"] + (right - 1) * fine["spacing_x_m"] - bbox[0]) / grid["spacing_x_m"]
                grid_top = (fine["origin_z_m"] + top * fine["spacing_z_m"] - bbox[2]) / grid["spacing_z_m"]
                grid_bottom = (fine["origin_z_m"] + (bottom - 1) * fine["spacing_z_m"] - bbox[2]) / grid["spacing_z_m"]
                for value in (grid_left, grid_right, grid_top, grid_bottom,
                              fine["spacing_x_m"] / grid["spacing_x_m"], fine["spacing_z_m"] / grid["spacing_z_m"]):
                    if not math.isclose(value, round(value), abs_tol=1e-8, rel_tol=0):
                        raise ValueError("saved source precision/origin not integer aligned")
                if round(grid_top) <= row < round(grid_bottom) and round(grid_left) <= column < round(grid_right):
                    matches.append(source_id)
            if len(matches) > 1 or owner[row, column] != (matches[0] if matches else -1):
                raise ValueError("saved coverage/ownership overlaps or disagrees")


def _validate_mesh(record, payloads):
    grid = record["grid"]
    rows, columns = grid["shape_cells_zx"]
    count, node_count = rows * columns, (rows + 1) * (columns + 1)
    nodes, cells, triangles = record["nodes"], record["cells"], record["triangles"]
    if set(nodes) != {"x_m", "z_m", "h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask"}:
        raise ValueError("saved node fields invalid")
    for name, array in nodes.items():
        dtype = bool if name.endswith("mask") else np.dtype("float64")
        if array.dtype != dtype or array.shape != (node_count,) or not np.isfinite(array).all():
            raise ValueError("saved node geometry shape/dtype invalid")
    node_ids = np.arange(node_count)
    if (not np.allclose(nodes["x_m"], grid["origin_x_m"] + node_ids % (columns + 1) * grid["spacing_x_m"], atol=1e-8, rtol=0) or
            not np.allclose(nodes["z_m"], grid["origin_z_m"] + node_ids // (columns + 1) * grid["spacing_z_m"], atol=1e-8, rtol=0)):
        raise ValueError("saved shared coordinates not unique/aligned")
    if (cells.dtype != np.dtype("int64") or cells.shape != (count, 4) or
            triangles.dtype != np.dtype("int64") or triangles.shape != (count * 2, 3)):
        raise ValueError("saved topology shape/dtype invalid")
    for cell_id, cell in enumerate(cells):
        top_left = cell_id // columns * (columns + 1) + cell_id % columns
        if (tuple(cell) != (top_left, top_left + 1, top_left + columns + 2, top_left + columns + 1) or
                not np.array_equal(triangles[2 * cell_id], cell[[0, 1, 2]]) or
                not np.array_equal(triangles[2 * cell_id + 1], cell[[0, 2, 3]])):
            raise ValueError("saved cell/triangle connectivity not continuous unique tessellation")
    contributors = record["contributors"]
    indices, weights = contributors["indices"], contributors["weights"]
    if (indices.shape != (count, 4, 4) or weights.shape != indices.shape or
            contributors["source_cell_zx"].shape != (count, 2) or contributors["source_cell_zx"].dtype != np.dtype("int64")):
        raise ValueError("saved cell contributor shape invalid")
    for source_id, source in enumerate(record["sources"]):
        selection = np.flatnonzero(record["cell_owner"].ravel() == source_id)
        fine = record["proofs"][source["proof_sha256"]]["inputs"]["fine"]
        arrays = payloads[source["proof_sha256"]]
        selected_cells = cells[selection]
        _support_check(indices[selection], weights[selection], tuple(fine["shape_zx"]),
                       nodes["x_m"][selected_cells], nodes["z_m"][selected_cells], fine)
        for cell_id in selection:
            first = cells[cell_id, 0]
            source_cell = (math.floor((nodes["z_m"][first] - fine["origin_z_m"]) / fine["spacing_z_m"] + 1e-10),
                           math.floor((nodes["x_m"][first] - fine["origin_x_m"]) / fine["spacing_x_m"] + 1e-10))
            if tuple(contributors["source_cell_zx"][cell_id]) != source_cell:
                raise ValueError("saved source cell reference disagrees")
            for corner_id, node_id in enumerate(cells[cell_id]):
                values = _evaluate_support(source, arrays, indices[cell_id, corner_id], weights[cell_id, corner_id], record["seam_tolerance_m"])
                for name, value in zip(("h0_m", "h2_m", "wet_mask", "water_surface_m", "protected_mask"), values):
                    actual = nodes[name][node_id]
                    if (isinstance(value, bool) and actual != value) or (not isinstance(value, bool) and abs(actual - value) > record["seam_tolerance_m"]):
                        raise ValueError("saved node disagrees with source H0/H2/actual wet support")
    wet_cells = nodes["wet_mask"][cells].all(axis=1)
    if record["wet_cells"].dtype != bool or not np.array_equal(wet_cells, record["wet_cells"]):
        raise ValueError("saved actual wet cells disagree")
    q_records, q_summary = _q_cut(record, payloads)
    if _identity(q_records) != _identity(record["q_cuts"]) or _identity(_integrals(grid, record, q_summary)) != _identity(record["summary"]):
        raise ValueError("saved unique integration/Q ledger disagrees")


def query_fine_mosaic(result, node_ids=None):
    validate_fine_mosaic(result)
    if node_ids is None:
        return _freeze(result["nodes"])
    selection = np.asarray(node_ids)
    if (selection.dtype.kind not in "iu" or selection.ndim != 1 or np.any(selection < 0) or
            np.any(selection >= len(result["nodes"]["x_m"]))):
        raise ValueError("invalid query node ids")
    return _freeze({name: array[selection] for name, array in result["nodes"].items()})


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate mosaic JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite mosaic JSON constant: " + value)


def _preflight_archive(archive):
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if (not entries or len(entries) > 20000 or len(names) != len(set(names)) or
            sum(entry.file_size for entry in entries) > MAX_BYTES or "manifest.json" not in names):
        raise ValueError("duplicate/oversized/incomplete mosaic ZIP")
    for entry in entries:
        if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError("invalid encrypted/compressed ZIP member")
        if entry.filename == "manifest.json":
            if entry.file_size > 4 * 1024 * 1024:
                raise ValueError("mosaic manifest too large")
            continue
        if (not entry.filename.startswith("array_") or not entry.filename.endswith(".npy") or
                "/" in entry.filename or "\\" in entry.filename):
            raise ValueError("invalid mosaic ZIP member")
        with archive.open(entry) as stream:
            version = np.lib.format.read_magic(stream)
            if version not in ((1, 0), (2, 0)):
                raise ValueError("unsupported NPY version")
            length_size = 2 if version == (1, 0) else 4
            length_bytes = stream.read(length_size)
            if len(length_bytes) != length_size:
                raise ValueError("truncated NPY header length")
            header_length = struct.unpack("<H" if length_size == 2 else "<I", length_bytes)[0]
            if header_length > 8192 or stream.tell() + header_length > entry.file_size:
                raise ValueError("NPY raw header length exceeds bound")
            stream.seek(8)
            if version == (1, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
            elif version == (2, 0):
                shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
            else:
                raise ValueError("unsupported NPY version")
            if (dtype.hasobject or dtype.kind not in "biuf" or fortran or len(shape) > 5 or
                    any(type(size) is not int or size < 0 for size in shape) or
                    math.prod(shape) * dtype.itemsize > MAX_BYTES or
                    stream.tell() + math.prod(shape) * dtype.itemsize != entry.file_size):
                raise ValueError("invalid NPY shape/dtype/payload size")


def save_fine_mosaic(result, path, *, allow_unprepared=False):
    validate_fine_mosaic(result, allow_unprepared=allow_unprepared)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = _tree(result, arrays)
    manifest = {"format_version": 2, "tree": tree, "tree_sha256": _identity(tree)}
    descriptor, temporary_name = tempfile.mkstemp(prefix="." + destination.name + "-", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", _json(manifest))
                for name, array in arrays.items():
                    with io.BytesIO() as payload:
                        np.save(payload, np.ascontiguousarray(array), allow_pickle=False)
                        archive.writestr(name, payload.getvalue())
            stream.flush()
            os.fsync(stream.fileno())
        with zipfile.ZipFile(temporary) as archive:
            _preflight_archive(archive)
        os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def load_fine_mosaic(path, *, allow_unprepared=False):
    try:
        with Path(path).open("rb") as retained, zipfile.ZipFile(retained) as archive:
            if os.fstat(retained.fileno()).st_size > MAX_BYTES:
                raise ValueError("mosaic file exceeds byte cap")
            _preflight_archive(archive)
            manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=_pairs, parse_constant=_constant)
            if (set(manifest) != {"format_version", "tree", "tree_sha256"} or manifest["format_version"] != 2 or
                    manifest["tree_sha256"] != _identity(manifest["tree"])):
                raise ValueError("mosaic manifest identity mismatch")
            tree = manifest["tree"]
            resources = MosaicResources(**tree["resources"])
            rows, columns = tree["grid"]["shape_cells_zx"]
            if (type(rows) is not int or type(columns) is not int or rows <= 0 or columns <= 0 or
                    rows * columns > resources.max_cells or
                    sum(entry.file_size for entry in archive.infolist()) > resources.max_retained_bytes or
                    sum(entry.file_size for entry in archive.infolist()) + rows * columns * 640 > resources.max_working_bytes):
                raise ValueError("archive JSON resource preflight limit")
            arrays, used = {}, set()
            for name in archive.namelist():
                if name.endswith(".npy"):
                    with archive.open(name) as stream:
                        arrays[name] = np.load(stream, allow_pickle=False)

            def decode(value):
                if isinstance(value, dict) and "$array" in value:
                    name = value["$array"]
                    if set(value) != {"$array", "dtype", "shape", "sha256"} or name in used or name not in arrays:
                        raise ValueError("invalid/duplicate mosaic array reference")
                    array = arrays[name]
                    if value["dtype"] != array.dtype.str or value["shape"] != list(array.shape) or value["sha256"] != array_hash(array):
                        raise ValueError("mosaic array hash/shape mismatch")
                    used.add(name)
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value

            result = decode(manifest["tree"])
            if used != set(arrays):
                raise ValueError("unreferenced mosaic arrays")
        validate_fine_mosaic(result, allow_unprepared=allow_unprepared)
        return _freeze(result)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile, EOFError) as error:
        raise ValueError("invalid fine mosaic bundle") from error


build_fine_mosaic = prepare_fine_mosaic
validate_surface_fine_mosaic = validate_fine_mosaic
save_surface_fine_mosaic = save_fine_mosaic
load_surface_fine_mosaic = load_fine_mosaic
query_surface_fine_mosaic = query_fine_mosaic
