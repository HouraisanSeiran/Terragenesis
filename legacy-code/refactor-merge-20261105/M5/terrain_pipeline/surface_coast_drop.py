"""Proof-bound engineered straight coastal strip; static geometry, not drop dynamics."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
import zipfile

import numpy as np

from terrain_pipeline.surface_domain_prepare import validate_surface_domains
from terrain_pipeline.surface_domain_prepare import _hash as _domain_hash
from terrain_pipeline.surface_domain_prepare import (
    _validate_plan as _validate_candidate_plan, _edge_ok, _archived_raster_mesh,
    LEGACY_VERSION,
)
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.surface_network_consumer import _payload, _proof_gate, _plan_proof, _identity as _proof_identity
from terrain_pipeline.surface_network_prepare import validate_surface_network
from terrain_pipeline.surface_network_recovery import _fingerprint as _recovery_hash
from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.surface_fine_mosaic import _static_water_support


VERSION = "surface-coast-drop-v1"
MODE = "engineering-synthetic-straight-strip-not-free-fall"
SOURCE_MODEL = "nodal-piecewise-linear-triangles-topright-to-bottomleft"
MAX_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_MEMBERS = 2048
MAX_HEADER_BYTES = 2048


class CoastDropError(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.diagnostic = MappingProxyType({"status": "rejected", "reason": reason,
                                            "geometry_published": False})


def _reject(reason):
    raise CoastDropError(reason)


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


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _array_hash(array):
    digest = hashlib.sha256()
    digest.update(_json([array.dtype.str, list(array.shape)]).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _tree(value, arrays):
    if isinstance(value, np.ndarray):
        name = "array_%04d.npy" % len(arrays)
        arrays[name] = value
        return {"$array": name, "shape": list(value.shape), "dtype": value.dtype.str,
                "sha256": _array_hash(value)}
    if isinstance(value, Mapping):
        return {key: _tree(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_tree(child, arrays) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def fingerprint(value):
    return hashlib.sha256(_json(_tree(value, {})).encode("ascii")).hexdigest()


def _retained(value, ceiling=MAX_BYTES):
    total = 0
    members = 0

    def visit(child, depth):
        nonlocal total, members
        if depth > 40:
            _reject("source nesting resource cap")
        if isinstance(child, np.ndarray):
            if child.dtype.kind not in "bifu" or child.size > 1000000:
                _reject("source array resource/dtype cap")
            total += child.nbytes + MAX_HEADER_BYTES
            members += 1
        elif isinstance(child, Mapping):
            if len(child) > MAX_MEMBERS:
                _reject("source mapping resource cap")
            for key, item in child.items():
                if not isinstance(key, str):
                    _reject("source keys must be strings")
                total += len(key.encode("utf-8"))
                visit(item, depth + 1)
        elif isinstance(child, (tuple, list)):
            if len(child) > 20000:
                _reject("source sequence resource cap")
            for item in child:
                visit(item, depth + 1)
        elif isinstance(child, str):
            total += len(child.encode("utf-8"))
        elif child is None or isinstance(child, (int, float, bool, np.generic)):
            total += 32
        else:
            _reject("unsupported source value")
        if total > ceiling or members >= MAX_MEMBERS:
            _reject("retained source resource cap")

    visit(value, 0)
    return total


@dataclass(frozen=True)
class DropResources:
    max_source_cells: int = 250000
    max_vertices: int = 20000
    max_triangles: int = 40000
    max_work: int = 500000
    max_retained_bytes: int = MAX_BYTES

    def __post_init__(self):
        for name, hard in (("max_source_cells", 250000), ("max_vertices", 20000),
                           ("max_triangles", 40000), ("max_work", 500000),
                           ("max_retained_bytes", MAX_BYTES)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= hard:
                _reject("invalid resource limit " + name)


@dataclass(frozen=True)
class DropBudget:
    max_cut_depth_m: float
    max_cut_volume_m3: float

    def __post_init__(self):
        for value in (self.max_cut_depth_m, self.max_cut_volume_m3):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                _reject("invalid explicit drop budget")


@dataclass(frozen=True)
class RiverAttachment:
    prepared: Mapping
    domain_id: int
    cross_section_xz_m: np.ndarray
    center_index: int
    datum: str

    def __post_init__(self):
        _retained(self.prepared)
        points = np.asarray(self.cross_section_xz_m)
        if (points.ndim != 2 or points.shape[1] != 2 or not 3 <= len(points) <= 256 or
                points.dtype.kind not in "fiu" or not np.all(np.isfinite(points))):
            _reject("invalid explicit upstream cross-section")
        if (type(self.domain_id) is not int or self.domain_id <= 0 or
                type(self.center_index) is not int or not 0 < self.center_index < len(points) - 1):
            _reject("invalid attachment domain or center index")
        if not isinstance(self.datum, str) or not self.datum.strip() or len(self.datum) > 1024:
            _reject("explicit attachment datum required")
        if not np.all(points[:, 1] == points[0, 1]) or np.any(np.diff(points[:, 0]) <= 0):
            _reject("only increasing-x constant-z straight cross-sections supported")
        object.__setattr__(self, "prepared", _freeze(self.prepared))
        object.__setattr__(self, "cross_section_xz_m", _freeze(points.astype("<f8")))


@dataclass(frozen=True)
class EngineeringSource:
    role: str
    source: str
    datum: str
    origin_x_m: float
    origin_z_m: float
    spacing_x_m: float
    spacing_z_m: float
    h0_m: np.ndarray
    h2_m: np.ndarray
    water_m: np.ndarray
    valid_mask: np.ndarray
    unknown_mask: np.ndarray
    protected_mask: np.ndarray
    wet_mask: np.ndarray
    ocean_mask: np.ndarray
    sea_level_m: float
    source_kind: str = "engineering_synthetic"
    surface_model: str = SOURCE_MODEL

    def __post_init__(self):
        shape = np.asarray(self.h0_m).shape
        if len(shape) != 2 or min(shape) < 2 or math.prod(shape) > 250000:
            _reject("engineering source cell resource cap")
        if (self.role not in ("corridor", "sea") or self.source_kind != "engineering_synthetic" or
                self.surface_model != SOURCE_MODEL):
            _reject("explicit engineering synthetic corridor/sea source required")
        for name in ("source", "datum"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 1024:
                _reject("explicit source declaration/datum required")
        for name in ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m", "sea_level_m"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(value) or (name.startswith("spacing") and value <= 0)):
                _reject("invalid engineering metric coordinates/sea level")
        for name in ("h0_m", "h2_m", "water_m", "valid_mask", "unknown_mask", "protected_mask", "wet_mask", "ocean_mask"):
            array = np.asarray(getattr(self, name))
            if array.shape != shape:
                _reject("engineering source shape mismatch")
            if name.endswith("mask"):
                if array.dtype != bool:
                    _reject("engineering source masks must be boolean")
            elif array.dtype.kind not in "fiu" or not np.all(np.isfinite(array)):
                _reject("engineering source geometry must be finite")
            object.__setattr__(self, name, _freeze(array.astype(bool if name.endswith("mask") else "<f8")))


def _source_record(source):
    if not isinstance(source, EngineeringSource):
        _reject("missing explicit corridor/sea source")
    record = {name: getattr(source, name) for name in source.__dataclass_fields__}
    record["identity_sha256"] = fingerprint(record)
    return record


def _check_source(record, role, datum, resources):
    if not isinstance(record, Mapping) or set(record) != set(EngineeringSource.__dataclass_fields__) | {"identity_sha256"}:
        _reject("source record schema mismatch")
    if record["identity_sha256"] != fingerprint({key: value for key, value in record.items() if key != "identity_sha256"}):
        _reject("source content identity mismatch")
    if record["h0_m"].size > resources.max_source_cells:
        _reject("source cell resource cap")
    source = EngineeringSource(**{key: value for key, value in record.items() if key != "identity_sha256"})
    if source.role != role or source.datum != datum:
        _reject("source role or vertical datum mismatch")
    if np.any(source.h2_m > source.h0_m + 1e-10):
        _reject("source H2 raises bed above H0")


def _stencil(source, points, shape):
    indices = np.empty((len(points), 4), dtype=np.int64)
    weights = np.empty((len(points), 4), dtype=np.float64)
    for point_n, (world_x, world_z) in enumerate(points):
        column = (world_x - source["origin_x_m"]) / source["spacing_x_m"]
        row = (world_z - source["origin_z_m"]) / source["spacing_z_m"]
        if not 0 <= row <= shape[0] - 1 or not 0 <= column <= shape[1] - 1:
            _reject("source coverage gap; no implicit extrapolation")
        top, left = int(math.floor(row)), int(math.floor(column))
        bottom, right = min(top + 1, shape[0] - 1), min(left + 1, shape[1] - 1)
        fraction_z, fraction_x = row - top, column - left
        indices[point_n] = [top * shape[1] + left, top * shape[1] + right,
                            bottom * shape[1] + left, bottom * shape[1] + right]
        weights[point_n] = [(1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x,
                            fraction_z * (1 - fraction_x), fraction_z * fraction_x]
    return indices, weights


def _sample(array, indices, weights):
    return np.sum(array.ravel()[indices] * weights, axis=1)


def _support(indices, weights, valid, unknown, protected, wet, ocean=None):
    positive = weights > 0
    for mask, expected, reason in ((valid, True, "invalid support"), (unknown, False, "unknown support"),
                                    (protected, False, "protected support"), (wet, True, "nonwet support")):
        if np.any((mask.ravel()[indices] != expected) & positive):
            _reject(reason)
    if ocean is not None and np.any(~ocean.ravel()[indices] & positive):
        _reject("sea attachment lacks explicit ocean support")


def _attachment(record):
    prepared = _plain(record["prepared"])
    validate_surface_domains(prepared)
    if prepared["kind"] != "evaluation" or prepared["status"] != "prepared":
        _reject("accepted prepared domain product required")
    if record["datum"] != prepared["candidate"]["inputs"]["vertical_datum"]:
        _reject("attachment datum differs from saved prepared source")
    entry = next((entry for entry in prepared["domains"] if entry["domain_id"] == record["domain_id"]), None)
    if entry is None or entry["status"] != "prepared":
        _reject("unknown or unprepared attachment domain")
    recovery = entry["recovery"]
    payload = _payload(recovery)
    _proof_gate(recovery, payload)
    points = record["cross_section_xz_m"]
    fine = recovery["inputs"]["fine"]
    fine_columns = (points[:, 0] - fine["origin_x_m"]) / fine["spacing_x_m"]
    fine_rows = (points[:, 1] - fine["origin_z_m"]) / fine["spacing_z_m"]
    if (not np.allclose(fine_columns, np.round(fine_columns), rtol=0, atol=1e-10) or
            not np.allclose(fine_rows, np.round(fine_rows), rtol=0, atol=1e-10) or
            not np.allclose(np.diff(points[:, 0]), fine["spacing_x_m"], rtol=0, atol=1e-10)):
        _reject("entire river cross-section must sample contiguous aligned fine nodes")
    indices, weights = _stencil(fine, points, payload["final_surface_m"].shape)
    _support(indices, weights, payload["domain_mask"], np.zeros_like(payload["wet_mask"]),
             payload["protected_mask"], payload["wet_mask"])
    center = record["center_index"]
    nodes = np.flatnonzero(payload["active_mask"] & payload["outlet_mask"] &
                           np.all(np.isclose(payload["world_xz_m"], points[center], rtol=0, atol=1e-10), axis=1))
    if len(nodes) != 1:
        _reject("center must attach to exactly one actual active terminal cut")
    terminal = int(nodes[0])
    discharge = float(payload["discharge_m3_s"][terminal])
    if not math.isfinite(discharge) or discharge <= 0:
        _reject("positive actual terminal cut Q required")
    fine_shape = payload["final_surface_m"].shape
    full_points = np.column_stack((np.tile(fine["origin_x_m"] + np.arange(fine_shape[1]) * fine["spacing_x_m"], fine_shape[0]),
                                  np.repeat(fine["origin_z_m"] + np.arange(fine_shape[0]) * fine["spacing_z_m"], fine_shape[1])))
    original = recovery["inputs"]["plan"]
    source_indices, source_weights = _stencil(original["identity"]["parameters"], full_points,
                                              original["arrays"]["source_height_m"].shape)
    return {"indices": indices, "weights": weights,
            "h0_m": _sample(payload["source_surface_m"], indices, weights),
            "h2_m": _sample(payload["final_surface_m"], indices, weights),
            "water_m": _sample(payload["water_surface_m"], indices, weights),
            "terminal_node": terminal, "terminal_q_m3_s": discharge,
            "fine_spacing_x_m": fine["spacing_x_m"],
            "recovery_sha256": recovery["identity_sha256"],
            "proof_support": {"payload": payload, "h0_indices": source_indices, "h0_weights": source_weights}}


def _saved_support(indices, weights, points, source, shape):
    if (indices.dtype != np.dtype("int64") or weights.dtype != np.dtype("float64") or
            indices.shape != (len(points), 4) or weights.shape != indices.shape or
            np.any(indices < 0) or np.any(indices >= math.prod(shape)) or
            not np.all(np.isfinite(weights)) or np.any(weights < 0) or
            not np.allclose(weights.sum(axis=1), 1., rtol=0, atol=1e-10)):
        _reject("invalid saved support indices/weights")
    for point_n, point in enumerate(points):
        column = (point[0] - source["origin_x_m"]) / source["spacing_x_m"]
        row = (point[1] - source["origin_z_m"]) / source["spacing_z_m"]
        if not 0 <= column <= shape[1] - 1 or not 0 <= row <= shape[0] - 1:
            _reject("saved support outside source bounds")
        top, left = int(math.floor(row)), int(math.floor(column))
        bottom, right = min(top + 1, shape[0] - 1), min(left + 1, shape[1] - 1)
        fraction_z, fraction_x = row - top, column - left
        if (not np.array_equal(indices[point_n], [top * shape[1] + left, top * shape[1] + right,
                                                 bottom * shape[1] + left, bottom * shape[1] + right]) or
                not np.allclose(weights[point_n], [(1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x,
                                                   fraction_z * (1 - fraction_x), fraction_z * fraction_x], rtol=0, atol=1e-10)):
            _reject("saved contributor support algebra mismatch")


def _static_attachment(record, support, indices, weights):
    prepared = _plain(record["prepared"])
    if (prepared["kind"] != "evaluation" or prepared["status"] != "prepared" or
            prepared["identity_sha256"] != _domain_hash({key: value for key, value in prepared.items() if key != "identity_sha256"})):
        _reject("saved prepared source status/hash mismatch")
    candidate = prepared["candidate"]
    if (candidate["identity_sha256"] != _domain_hash({key: value for key, value in candidate.items() if key != "identity_sha256"}) or
            record["datum"] != candidate["inputs"]["vertical_datum"]):
        _reject("saved candidate hash/datum mismatch")
    _validate_candidate_plan(candidate)
    entry = next((item for item in prepared["domains"] if item["domain_id"] == record["domain_id"]), None)
    if entry is None or entry["status"] != "prepared":
        _reject("saved domain not prepared")
    proof = entry["recovery"]
    if (proof["identity_sha256"] != _recovery_hash({key: value for key, value in proof.items() if key != "identity_sha256"}) or
            proof["status"] != "accepted" or proof["accepted"] is not True or not proof["attempts"] or
            proof["attempts"][-1]["accepted"] is not True or any(proof["attempts"][-1]["failures"].values()) or
            proof["selected_method"] != proof["attempts"][-1]["method"]):
        _reject("saved recovery acceptance/hash mismatch")
    original, final = proof["inputs"]["plan"], proof["final_plan"]
    domain_record = next((item for item in candidate["domains"] if item["domain_id"] == record["domain_id"]), None)
    if domain_record is None or domain_record["status"] != "routed":
        _reject("saved candidate domain not routed")
    first_row, last_row, first_column, last_column = domain_record["bounds_zx"]
    candidate_inputs = candidate["inputs"]
    candidate_arrays = candidate["arrays"]
    window = np.s_[first_row:last_row, first_column:last_column]
    labels = candidate_inputs["domain_labels"][window]
    domain = labels == record["domain_id"]
    global_columns = candidate_inputs["height_m"].shape[1]
    local_columns = last_column - first_column
    original_arrays = original["arrays"]
    _same(original_arrays["source_height_m"], candidate_inputs["height_m"][window], "candidate original H0 window")
    _same(original_arrays["discharge_m3_s"], np.where(domain, candidate_arrays["discharge_m3_s"][window], 0.), "candidate original Q window")
    _same(proof["inputs"]["coarse_domain"], domain, "candidate original domain mask")
    _same(proof["inputs"]["coarse_protected"], candidate_inputs["protected_mask"][window], "candidate original protection mask")
    global_to_local = {}
    for local_n in range(domain.size):
        global_n = (first_row + local_n // local_columns) * global_columns + first_column + local_n % local_columns
        global_to_local[global_n] = local_n
        target = int(candidate_arrays["receiver"][global_n])
        expected = -1
        if domain.flat[local_n] and target >= 0:
            expected = (target // global_columns - first_row) * local_columns + target % global_columns - first_column
        if int(original_arrays["receiver"][local_n]) != expected:
            _reject("candidate original receiver binding mismatch")
    expected_order = [local_n for local_n in range(domain.size) if not domain.flat[local_n]]
    expected_order.extend(global_to_local[int(global_n)] for global_n in candidate_arrays["order"]
                          if int(global_n) in global_to_local and domain.flat[global_to_local[int(global_n)]])
    _same(original_arrays["order"], expected_order, "candidate original order binding")
    _same(original_arrays["outlet_mask"], (original_arrays["receiver"] == -1).reshape(domain.shape), "candidate original outlets")
    original_params = original["identity"]["parameters"]
    for name, expected in {
        "spacing_x_m": candidate_inputs["spacing_x_m"], "spacing_z_m": candidate_inputs["spacing_z_m"],
        "origin_x_m": candidate_inputs["origin_x_m"] + first_column * candidate_inputs["spacing_x_m"],
        "origin_z_m": candidate_inputs["origin_z_m"] + first_row * candidate_inputs["spacing_z_m"],
        "sea_level_elevation_m": candidate_inputs["sea_level_elevation_m"],
        "source_identity": candidate["identity_sha256"] + ":domain:" + str(record["domain_id"]),
    }.items():
        if original_params[name] != expected:
            _reject("candidate original world metric/source identity binding mismatch")
    config = prepared["configurations"][str(record["domain_id"])]
    for name, expected in config.items():
        if name not in ("channel_recipe", "recovery_recipe") and _domain_hash(expected) != _domain_hash(proof["inputs"][name]):
            _reject("saved recovery changed configured physical budget or fine support")
    if any(original_params[name] != value for name, value in config["channel_recipe"].items()):
        _reject("saved original channel recipe changed")
    mesh = (_archived_raster_mesh(domain.shape) if candidate["algorithm_version"] == LEGACY_VERSION else
            grid_mesh(domain.shape, x0_m=original_params["origin_x_m"], z0_m=original_params["origin_z_m"],
                      dx_m=original_params["spacing_x_m"], dz_m=original_params["spacing_z_m"],
                      world_seed=original_params.get("world_seed", 20261020)))
    for local_n in np.flatnonzero(domain):
        target = int(final["arrays"]["receiver"][local_n])
        if (target < 0 and original_arrays["receiver"][local_n] != -1) or (
                target >= 0 and not _edge_ok(int(local_n), target, domain.shape,
                                           domain & ~candidate_inputs["protected_mask"][window], mesh)):
            _reject("saved final route changes legal terminal or crosses domain/protection")
    original_local, original_total = _plan_proof(original)
    final_local, final_total = _plan_proof(final)
    _same(original_local, final_local, "saved original/final local Q")
    _same(original_total, final_total, "saved total outlet Q")
    _same(original["arrays"]["channel_mask"] & original["arrays"]["outlet_mask"],
          final["arrays"]["channel_mask"] & final["arrays"]["outlet_mask"], "saved active terminal identity")
    surface = proof["surface"]
    validate_surface_network(surface)
    params = _proof_identity(surface)
    if (surface["status"] != "prepared" or surface["summary"]["publishable"] is not True or
            any(surface["summary"]["budget_failures"].values()) or any(surface["summary"]["joint_blockers"].values()) or
            params["plan_sha256"] != final["identity_sha256"] or params["summary_sha256"] != digest(surface["summary"]) or
            params["output_sha256"] != digest({name: array_hash(array) for name, array in surface["arrays"].items()}) or
            any(params[name] != value for name, value in proof["inputs"]["budget"].items())):
        _reject("saved surface acceptance chain mismatch")
    if set(support) != {"payload", "h0_indices", "h0_weights"}:
        _reject("saved proof support schema mismatch")
    arrays = support["payload"]
    fine = proof["inputs"]["fine"]
    shape = tuple(fine["shape_zx"])
    coarse_rows = first_row + np.floor(np.arange(shape[0]) * fine["spacing_z_m"] / candidate_inputs["spacing_z_m"] + .5).astype(np.int64)
    coarse_columns = first_column + np.floor(np.arange(shape[1]) * fine["spacing_x_m"] / candidate_inputs["spacing_x_m"] + .5).astype(np.int64)
    legal = np.zeros_like(candidate_inputs["land_mask"])
    for domain_id, land_cell, _ in candidate_inputs["coastal_outlets"]:
        if domain_id == record["domain_id"]:
            legal.flat[land_cell] = True
    sample = np.ix_(coarse_rows, coarse_columns)
    expected_domain = candidate_inputs["domain_labels"][sample] == record["domain_id"]
    expected_protected = candidate_inputs["protected_mask"][sample]
    _same(fine["domain_mask"], expected_domain, "candidate fine domain binding")
    _same(fine["protected_mask"], expected_protected, "candidate fine protection binding")
    _same(fine["legal_outlet_mask"], legal[sample] & expected_domain & ~expected_protected, "candidate fine coast binding")
    for name in ("source_surface_m", "valley_surface_m", "final_surface_m", "water_surface_m"):
        if arrays[name].shape != shape or not np.all(np.isfinite(arrays[name])):
            _reject("saved fine source geometry invalid")
    ledger, valley = proof["fine_ledger"], proof["valley"]
    if (ledger is None) != (valley is None):
        _reject("saved valley lacks ledger")
    raw = surface["arrays"] if ledger is None else ledger["arrays"]
    for name in ("source_surface_m", "final_surface_m"):
        _same(arrays[name], raw[name], "saved fine payload " + name)
    _same(arrays["valley_surface_m"], surface["arrays"]["source_surface_m"], "saved H1")
    _same(arrays["water_surface_m"], np.where(surface["arrays"]["wet_mask"], surface["arrays"]["water_surface_m"], 0.), "saved fine water")
    if ledger is not None:
        ledger_params, valley_params = _proof_identity(ledger), _proof_identity(valley)
        if (ledger["status"] != "prepared" or any(ledger["summary"]["failures"].values()) or
                valley["summary"]["geometry_feasible"] is not True or any(valley["summary"]["failures"].values()) or
                ledger_params["surface_identity_sha256"] != surface["identity_sha256"] or
                ledger_params["valley_identity_sha256"] != valley["identity_sha256"] or
                ledger_params["summary_sha256"] != digest(ledger["summary"]) or
                ledger_params["arrays_sha256"] != digest({name: array_hash(array) for name, array in ledger["arrays"].items()}) or
                valley_params["replanned_sha256"] != final["identity_sha256"] or
                valley_params["summary_sha256"] != digest(valley["summary"]) or
                valley_params["arrays_sha256"] != digest({name: {"sha256": array_hash(array), "shape": list(array.shape), "dtype": array.dtype.str}
                                                           for name, array in sorted(valley["arrays"].items())}) or
                any(valley_params[name] != value or ledger_params[name] != value for name, value in proof["inputs"]["valley_recipe"].items())):
            _reject("saved valley/ledger acceptance chain mismatch")
        _same(valley["arrays"]["source_height_m"], original["arrays"]["source_height_m"], "valley original H0")
        _same(valley["arrays"]["valley_surface_m"], final["arrays"]["source_height_m"], "valley coarse H1")
    else:
        _same(original["arrays"]["source_height_m"], final["arrays"]["source_height_m"], "unchanged nonvalley H0")
    if array_hash(original["arrays"]["source_height_m"]) != proof["summary"]["original_height_sha256"]:
        _reject("saved original H0 hash mismatch")
    full_points = np.column_stack((np.tile(fine["origin_x_m"] + np.arange(shape[1]) * fine["spacing_x_m"], shape[0]),
                                  np.repeat(fine["origin_z_m"] + np.arange(shape[0]) * fine["spacing_z_m"], shape[1])))
    _saved_support(support["h0_indices"], support["h0_weights"], full_points,
                   original["identity"]["parameters"], original["arrays"]["source_height_m"].shape)
    _same(arrays["source_surface_m"].ravel(), (original["arrays"]["source_height_m"].ravel()[support["h0_indices"]] * support["h0_weights"]).sum(axis=1), "full saved H0 source algebra")
    _same(arrays["valley_surface_m"].ravel(), (final["arrays"]["source_height_m"].ravel()[support["h0_indices"]] * support["h0_weights"]).sum(axis=1), "full saved H1 source algebra")
    for name in ("domain_mask", "protected_mask", "legal_outlet_mask"):
        if arrays[name].dtype != bool or not np.array_equal(arrays[name], fine[name]):
            _reject("saved proof support masks differ")
    wet = arrays["wet_mask"]
    if (wet.dtype != bool or not np.array_equal(wet, surface["arrays"]["wet_mask"]) or
            np.any(wet & (~arrays["domain_mask"] | arrays["protected_mask"])) or
            np.any(arrays["water_surface_m"][wet] <= arrays["final_surface_m"][wet])):
        _reject("saved actual wet/protected/depth support mismatch")
    for name, cut in (("valley_cut_m", arrays["source_surface_m"] - arrays["valley_surface_m"]),
                      ("bed_cut_m", arrays["valley_surface_m"] - arrays["final_surface_m"]),
                      ("total_cut_m", arrays["source_surface_m"] - arrays["final_surface_m"])):
        _same(arrays[name], cut, "saved source cut " + name)
        if np.any(cut < -1e-9) or np.any((cut > 1e-9) & (~arrays["domain_mask"] | arrays["protected_mask"])):
            _reject("saved source cut violates domain/protection")
    area_weights = np.ones(shape)
    area_weights[[0, -1], :] *= .5
    area_weights[:, [0, -1]] *= .5
    cell_area = fine["spacing_x_m"] * fine["spacing_z_m"]
    def check_cut(cut, depth_cap, area_cap, volume_cap):
        if (np.max(cut) > depth_cap + 1e-9 or np.sum((cut > 1e-9) * area_weights) * cell_area > area_cap + 1e-9 or
                np.sum(cut * area_weights) * cell_area > volume_cap + 1e-9):
            _reject("saved upstream cut exceeds original budget")
    budget = proof["inputs"]["budget"]
    check_cut(arrays["bed_cut_m"], budget["max_bed_cut_m"], budget["max_area_m2"], budget["max_cut_volume_m3"])
    if valley is not None:
        recipe = proof["inputs"]["valley_recipe"]
        check_cut(arrays["valley_cut_m"], recipe["max_valley_depth_m"], recipe["max_valley_area_m2"], recipe["max_valley_volume_m3"])
        check_cut(arrays["total_cut_m"], float("inf"), recipe["max_total_cut_area_m2"], recipe["max_total_cut_volume_m3"])
    coarse = final["identity"]["parameters"]
    graph_arrays = final["arrays"]
    positions = arrays["world_xz_m"]
    graph_count = graph_arrays["source_height_m"].size
    graph_columns = graph_arrays["source_height_m"].shape[1]
    _same(positions[:, 0], coarse["origin_x_m"] + np.arange(graph_count) % graph_columns * coarse["spacing_x_m"], "saved graph x")
    _same(positions[:, 1], coarse["origin_z_m"] + np.arange(graph_count) // graph_columns * coarse["spacing_z_m"], "saved graph z")
    for name, expected in (("receiver", graph_arrays["receiver"]), ("order", graph_arrays["order"]),
                            ("discharge_m3_s", graph_arrays["discharge_m3_s"].ravel()),
                            ("active_mask", graph_arrays["channel_mask"].ravel()),
                            ("outlet_mask", graph_arrays["outlet_mask"].ravel()), ("local_discharge_m3_s", final_local)):
        _same(arrays[name], expected, "saved terminal graph " + name)
    graph_rows = np.rint((positions[:, 1] - fine["origin_z_m"]) / fine["spacing_z_m"]).astype(np.int64)
    graph_columns_fine = np.rint((positions[:, 0] - fine["origin_x_m"]) / fine["spacing_x_m"]).astype(np.int64)
    active = arrays["active_mask"]
    graph_sample = (graph_rows, graph_columns_fine)
    _same(arrays["node_stage_m"], np.where(active, arrays["water_surface_m"][graph_sample], 0.), "saved graph stage from actual wet source")
    if (not np.array_equal(arrays["domain_mask"][graph_sample], domain.ravel()) or
            not np.array_equal(arrays["protected_mask"][graph_sample], proof["inputs"]["coarse_protected"].ravel()) or
            np.any(active & (~domain.ravel() | proof["inputs"]["coarse_protected"].ravel())) or
            not np.all(wet[graph_rows[active], graph_columns_fine[active]]) or
            not np.all(arrays["legal_outlet_mask"][graph_rows[active & arrays["outlet_mask"]], graph_columns_fine[active & arrays["outlet_mask"]]])):
        _reject("saved graph lacks domain/wet/legal terminal support")
    graph_bed = graph_arrays["bounded_bed_m"].ravel()
    if not np.allclose(arrays["final_surface_m"][graph_rows[active], graph_columns_fine[active]], graph_bed[active],
                       atol=budget["bed_match_tolerance_m"], rtol=0):
        _reject("saved actual graph H2 differs from bounded bed")
    stage_recipe = proof["inputs"]["stage_recipe"]
    min_depth, max_depth = stage_recipe["min_clearance_m"], stage_recipe["max_depth_m"]
    node_stage = arrays["node_stage_m"]
    preferred = graph_bed + np.maximum(graph_arrays["nominal_depth_m"].ravel(), min_depth)
    if (np.any(node_stage[active] - graph_bed[active] < min_depth - 1e-9) or
            np.any(node_stage[active] - graph_bed[active] > max_depth + 1e-9) or
            np.any(node_stage[active] > preferred[active] + stage_recipe["max_lift_above_nominal_m"] + 1e-9)):
        _reject("saved graph stage exceeds original depth/lift budget")
    terminals = np.flatnonzero(active & arrays["outlet_mask"])
    _same(node_stage[terminals], proof["inputs"]["outlet_stage_m"], "original terminal boundary stage")
    for donor in np.flatnonzero(active & (arrays["receiver"] >= 0)):
        target = int(arrays["receiver"][donor])
        distance = float(np.linalg.norm(positions[donor] - positions[target]))
        expected_stage = max(preferred[donor], node_stage[target] + stage_recipe["min_stage_slope_m_per_m"] * distance)
        if not active[target] or abs(node_stage[donor] - expected_stage) > 1e-8:
            _reject("saved graph stage equation mismatch")
        step_count = max(abs(graph_rows[target] - graph_rows[donor]), abs(graph_columns_fine[target] - graph_columns_fine[donor]))
        previous_bed = None
        for step in range(step_count + 1):
            fraction = step / step_count
            row = int(round(graph_rows[donor] + fraction * (graph_rows[target] - graph_rows[donor])))
            column = int(round(graph_columns_fine[donor] + fraction * (graph_columns_fine[target] - graph_columns_fine[donor])))
            stage_here = node_stage[donor] * (1 - fraction) + node_stage[target] * fraction
            bed_here = arrays["final_surface_m"][row, column]
            if (not wet[row, column] or stage_here - bed_here < min_depth - 1e-9 or
                    stage_here - bed_here > max_depth + 1e-9 or (previous_bed is not None and bed_here > previous_bed + 1e-9)):
                _reject("saved graph edge wet/depth/bed continuity mismatch")
            previous_bed = bed_here
    _static_water_support(proof, arrays)
    points = record["cross_section_xz_m"]
    _saved_support(indices, weights, points, fine, shape)
    if (not np.allclose(np.diff(points[:, 0]), fine["spacing_x_m"], rtol=0, atol=1e-10) or
            not np.allclose((points[:, 0] - fine["origin_x_m"]) / fine["spacing_x_m"],
                            np.round((points[:, 0] - fine["origin_x_m"]) / fine["spacing_x_m"]), rtol=0, atol=1e-10) or
            not math.isclose((points[0, 1] - fine["origin_z_m"]) / fine["spacing_z_m"],
                             round((points[0, 1] - fine["origin_z_m"]) / fine["spacing_z_m"]), abs_tol=1e-10)):
        _reject("saved cross-section skips or misaligns fine nodes")
    _support(indices, weights, arrays["domain_mask"], np.zeros(shape, bool), arrays["protected_mask"], wet)
    center = record["center_index"]
    terminal_nodes = np.flatnonzero(arrays["active_mask"] & arrays["outlet_mask"] &
                                    np.all(np.isclose(positions, points[center], rtol=0, atol=1e-10), axis=1))
    if len(terminal_nodes) != 1:
        _reject("saved attachment lacks unique actual terminal cut")
    terminal = int(terminal_nodes[0])
    terminal_q = float(arrays["discharge_m3_s"][terminal])
    terminal_stage = float(np.sum(arrays["water_surface_m"].ravel()[indices[center]] * weights[center]))
    if (terminal_q <= 0 or not np.any(np.isclose(proof["inputs"]["outlet_stage_m"], terminal_stage, rtol=0, atol=1e-8)) or
            abs(terminal_stage - arrays["node_stage_m"][terminal]) > 1e-8):
        _reject("saved actual terminal stage/Q mismatch")
    return {"h2_m": np.sum(arrays["final_surface_m"].ravel()[indices] * weights, axis=1),
            "water_m": np.sum(arrays["water_surface_m"].ravel()[indices] * weights, axis=1),
            "fine_spacing_x_m": fine["spacing_x_m"], "terminal_node": terminal,
            "terminal_q_m3_s": terminal_q, "recovery_sha256": proof["identity_sha256"]}


def _preflight(attachment, corridor, sea, stations, resources):
    if not isinstance(resources, DropResources):
        _reject("explicit DropResources required")
    DropResources(**asdict(resources))
    section = attachment["cross_section_xz_m"]
    station_count = len(stations)
    vertex_count = station_count * len(section)
    triangle_count = 2 * (station_count - 1) * (len(section) - 1)
    if (station_count < 2 or vertex_count > resources.max_vertices or
            triangle_count > resources.max_triangles or vertex_count * 12 > resources.max_work):
        _reject("mesh vertex/triangle/work resource cap")
    sources = {"attachment": attachment, "corridor": corridor, "sea": sea}
    source_bytes = _retained(sources, resources.max_retained_bytes)
    cells = corridor["h0_m"].size + sea["h0_m"].size
    if cells > resources.max_source_cells:
        _reject("aggregate engineering source cell resource cap")
    prepared = attachment["prepared"]
    selected = next((entry for entry in prepared["domains"] if entry["domain_id"] == attachment["domain_id"]), None)
    if selected is None or selected["recovery"] is None:
        _reject("selected prepared recovery missing")
    proof_cells = math.prod(selected["recovery"]["inputs"]["fine"]["shape_zx"])
    if proof_cells > resources.max_source_cells:
        _reject("selected proof support cell resource cap")
    output_bound = vertex_count * 256 + triangle_count * 80 + proof_cells * 320 + MAX_METADATA_BYTES
    if source_bytes + output_bound > resources.max_retained_bytes:
        _reject("retained geometry resource cap")
    return {"vertices": vertex_count, "triangles": triangle_count,
            "work": vertex_count * 12, "retained_bytes_upper_bound": source_bytes + output_bound}


def _corridor_cells(source, section, stations):
    shape = source["h0_m"].shape
    left = (section[0, 0] - source["origin_x_m"]) / source["spacing_x_m"]
    right = (section[-1, 0] - source["origin_x_m"]) / source["spacing_x_m"]
    top = (stations[0] - source["origin_z_m"]) / source["spacing_z_m"]
    bottom = (stations[-1] - source["origin_z_m"]) / source["spacing_z_m"]
    if left < 0 or top < 0 or right > shape[1] - 1 or bottom > shape[0] - 1:
        _reject("corridor rectangle coverage gap")
    columns = np.arange(math.floor(left), math.ceil(right) + 1)
    rows = np.arange(math.floor(top), math.ceil(bottom) + 1)
    indices = (rows[:, None] * shape[1] + columns).ravel().astype(np.int64)
    for name, expected, reason in (("valid_mask", True, "invalid interior corridor support"),
                                   ("unknown_mask", False, "unknown interior corridor support"),
                                   ("protected_mask", False, "protected interior corridor support"),
                                   ("wet_mask", True, "nonwet interior corridor support")):
        if np.any(source[name].ravel()[indices] != expected):
            _reject(reason)
    return indices


def _aligned_sources(corridor, sea, section, stations, fine_spacing):
    if (not math.isclose(corridor["spacing_x_m"], fine_spacing, rel_tol=0, abs_tol=1e-10) or
            not math.isclose(sea["spacing_x_m"], fine_spacing, rel_tol=0, abs_tol=1e-10) or
            not np.allclose(np.diff(section[:, 0]), fine_spacing, rtol=0, atol=1e-10) or
            not np.allclose(np.diff(stations), corridor["spacing_z_m"], rtol=0, atol=1e-10)):
        _reject("no skipped source cells: exact fine/corridor/sea spacing required")
    for source, points in ((corridor, section), (sea, np.column_stack((section[:, 0], np.full(len(section), stations[-1]))))):
        columns = (points[:, 0] - source["origin_x_m"]) / source["spacing_x_m"]
        rows = (points[:, 1] - source["origin_z_m"]) / source["spacing_z_m"]
        if (not np.allclose(columns, np.round(columns), rtol=0, atol=1e-10) or
                not np.allclose(rows, np.round(rows), rtol=0, atol=1e-10)):
            _reject("aligned source nodes required; no subcell geometry claims")


def _source_triangles(corridor, xz, triangles):
    columns = np.rint((xz[:, 0] - corridor["origin_x_m"]) / corridor["spacing_x_m"]).astype(np.int64)
    rows = np.rint((xz[:, 1] - corridor["origin_z_m"]) / corridor["spacing_z_m"]).astype(np.int64)
    return (rows * corridor["h0_m"].shape[1] + columns)[triangles]


def _triangles(rows, columns):
    triangles = np.empty((2 * (rows - 1) * (columns - 1), 3), dtype=np.int64)
    offset = 0
    for row in range(rows - 1):
        for column in range(columns - 1):
            first = row * columns + column
            triangles[offset] = [first, first + 1, first + columns]
            triangles[offset + 1] = [first + 1, first + columns + 1, first + columns]
            offset += 2
    return triangles


def _mesh_gate(bed_xyz, water_xyz, triangles):
    if not np.all(np.isfinite(bed_xyz)) or not np.all(np.isfinite(water_xyz)):
        _reject("nonfinite output mesh")
    if np.any(water_xyz[:, 1] <= bed_xyz[:, 1]):
        _reject("strip must have positive full-width water depth")
    if len(np.unique(bed_xyz[:, [0, 2]], axis=0)) != len(bed_xyz):
        _reject("duplicate strip vertices")
    for vertices in (bed_xyz, water_xyz):
        corners = vertices[triangles]
        areas = np.linalg.norm(np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
        if np.any(areas <= 1e-12):
            _reject("degenerate strip triangle")
    if len(np.unique(triangles)) != len(bed_xyz):
        _reject("unused or disconnected strip vertices")


def _budget_ledger(h0, h2, xz, triangles, budget):
    cut = h0 - h2
    if np.any(cut < -1e-10):
        _reject("negative engineering cut")
    corners = xz[triangles]
    difference_first = corners[:, 1] - corners[:, 0]
    difference_second = corners[:, 2] - corners[:, 0]
    plan_area = .5 * np.abs(difference_first[:, 0] * difference_second[:, 1] -
                             difference_first[:, 1] * difference_second[:, 0])
    volume = float(np.sum(plan_area * np.mean(cut[triangles], axis=1)))
    max_cut = float(np.max(cut))
    if max_cut > budget.max_cut_depth_m + 1e-10 or volume > budget.max_cut_volume_m3 + 1e-10:
        _reject("explicit original cut depth/volume budget exceeded")
    return {"cut_m": cut, "triangle_plan_area_m2": plan_area,
            "max_cut_depth_m": max_cut, "cut_volume_m3": volume,
            "semantics": "new_strip_H0_minus_H2_piecewise_linear_prism_no_old_recut"}


def prepare_coast_drop(attachment, corridor, sea, stations_z_m, budget, *, resources=DropResources()):
    """Explicit construction only. Rejection publishes no partial geometry."""
    if not isinstance(attachment, RiverAttachment) or not isinstance(budget, DropBudget):
        _reject("explicit RiverAttachment and original DropBudget required")
    stations = np.asarray(stations_z_m)
    if stations.ndim != 1 or stations.dtype.kind not in "fiu" or not np.all(np.isfinite(stations)):
        _reject("explicit finite station vector required")
    attachment_record = {name: getattr(attachment, name) for name in attachment.__dataclass_fields__}
    corridor_record, sea_record = _source_record(corridor), _source_record(sea)
    usage = _preflight(attachment_record, corridor_record, sea_record, stations, resources)
    _check_source(corridor_record, "corridor", attachment.datum, resources)
    _check_source(sea_record, "sea", attachment.datum, resources)
    if stations[0] != attachment.cross_section_xz_m[0, 1] or np.any(np.diff(stations) <= 0):
        _reject("stations must begin at actual endpoint and increase strictly")
    upstream = _attachment(attachment_record)
    section = attachment.cross_section_xz_m
    if sea.sea_level_m >= upstream["water_m"][attachment.center_index]:
        _reject("sea level must be below actual river center stage")
    if corridor.sea_level_m != sea.sea_level_m:
        _reject("corridor and sea level disagree")
    _aligned_sources(corridor_record, sea_record, section, stations, upstream["fine_spacing_x_m"])
    if (np.min(np.diff(section[:, 0])) + 1e-10 < max(corridor.spacing_x_m, sea.spacing_x_m) or
            np.min(np.diff(stations)) + 1e-10 < corridor.spacing_z_m):
        _reject("mesh resolution unsupported by explicit sources")
    xz = np.column_stack((np.tile(section[:, 0], len(stations)), np.repeat(stations, len(section))))
    corridor_indices, corridor_weights = _stencil(corridor_record, xz, corridor.h0_m.shape)
    _support(corridor_indices, corridor_weights, corridor.valid_mask, corridor.unknown_mask,
             corridor.protected_mask, corridor.wet_mask)
    corridor_cells = _corridor_cells(corridor_record, section, stations)
    sea_points = xz[-len(section):]
    sea_indices, sea_weights = _stencil(sea_record, sea_points, sea.h0_m.shape)
    _support(sea_indices, sea_weights, sea.valid_mask, sea.unknown_mask, sea.protected_mask,
             sea.wet_mask, sea.ocean_mask)
    sea_bed = _sample(sea.h2_m, sea_indices, sea_weights)
    sea_water = _sample(sea.water_m, sea_indices, sea_weights)
    if not np.allclose(sea_water, sea.sea_level_m, rtol=0, atol=1e-10):
        _reject("sea source water differs from sea level")
    fraction = (stations - stations[0]) / (stations[-1] - stations[0])
    bed = ((1 - fraction[:, None]) * upstream["h2_m"] + fraction[:, None] * sea_bed).ravel()
    water = ((1 - fraction[:, None]) * upstream["water_m"] + fraction[:, None] * sea_water).ravel()
    supported_bed = _sample(corridor.h2_m, corridor_indices, corridor_weights)
    supported_water = _sample(corridor.water_m, corridor_indices, corridor_weights)
    if (not np.allclose(bed, supported_bed, rtol=0, atol=1e-9) or
            not np.allclose(water, supported_water, rtol=0, atol=1e-9)):
        _reject("explicit corridor H2/water does not support endpoint interpolation")
    h0 = _sample(corridor.h0_m, corridor_indices, corridor_weights)
    triangles = _triangles(len(stations), len(section))
    source_triangles = _source_triangles(corridor_record, xz, triangles)
    bed_xyz = np.column_stack((xz[:, 0], bed, xz[:, 1]))
    water_xyz = np.column_stack((xz[:, 0], water, xz[:, 1]))
    _mesh_gate(bed_xyz, water_xyz, triangles)
    ledger = _budget_ledger(h0, bed, xz, triangles, budget)
    center_indices = np.arange(len(stations)) * len(section) + attachment.center_index
    result = {"algorithm": VERSION, "mode": MODE, "status": "prepared",
              "natural_outlet_certified": False,
              "inputs": {"attachment": attachment_record, "corridor": corridor_record, "sea": sea_record,
                         "stations_z_m": stations.astype("<f8"), "budget": asdict(budget), "resources": asdict(resources)},
              "arrays": {"bed_xyz_m": bed_xyz, "water_xyz_m": water_xyz, "triangles": triangles,
                         "h0_m": h0, "centerline_xyz_m": water_xyz[center_indices],
                         "corridor_indices": corridor_indices, "corridor_weights": corridor_weights,
                         "sea_indices": sea_indices, "sea_weights": sea_weights,
                         "river_indices": upstream["indices"], "river_weights": upstream["weights"]},
              "attachment": {"recovery_sha256": upstream["recovery_sha256"], "terminal_node": upstream["terminal_node"],
                             "terminal_q_m3_s": upstream["terminal_q_m3_s"],
                             "river_bed_xyz_m": bed_xyz[:len(section)], "river_water_xyz_m": water_xyz[:len(section)],
                             "sea_bed_xyz_m": bed_xyz[-len(section):], "sea_water_xyz_m": water_xyz[-len(section):]},
              "ledger": ledger, "usage": usage, "proof_support": upstream["proof_support"]}
    result["arrays"]["corridor_support_cells"] = corridor_cells
    result["arrays"]["corridor_source_triangles"] = source_triangles
    _retained(result, resources.max_retained_bytes)
    result["identity_sha256"] = fingerprint(result)
    frozen = _freeze(result)
    validate_coast_drop(frozen)
    return frozen


def _same(actual, expected, name):
    if np.asarray(actual).shape != np.asarray(expected).shape or not np.allclose(actual, expected, rtol=0, atol=1e-9):
        _reject("static coast proof mismatch: " + name)


def validate_coast_drop(result):
    """Read saved geometry and source equations; never invoke construction/recovery."""
    if not isinstance(result, Mapping):
        _reject("saved coast product required")
    required = {"algorithm", "mode", "status", "natural_outlet_certified", "inputs", "arrays",
                "attachment", "ledger", "usage", "identity_sha256", "proof_support"}
    if set(result) != required or result["algorithm"] != VERSION or result["mode"] != MODE:
        _reject("coast product schema/version mismatch")
    if result["status"] != "prepared" or result["natural_outlet_certified"] is not False:
        _reject("only engineered prepared coast geometry is supported")
    inputs = result["inputs"]
    if set(inputs) != {"attachment", "corridor", "sea", "stations_z_m", "budget", "resources"}:
        _reject("coast input schema mismatch")
    resources = DropResources(**inputs["resources"])
    budget = DropBudget(**inputs["budget"])
    _retained(result, resources.max_retained_bytes)
    attachment = inputs["attachment"]
    if set(attachment) != set(RiverAttachment.__dataclass_fields__):
        _reject("attachment schema mismatch")
    RiverAttachment(**attachment)
    corridor, sea = inputs["corridor"], inputs["sea"]
    stations = inputs["stations_z_m"]
    if (not isinstance(stations, np.ndarray) or stations.ndim != 1 or
            stations.dtype.kind not in "fiu" or not np.all(np.isfinite(stations))):
        _reject("invalid saved station vector")
    usage = _preflight(attachment, corridor, sea, stations, resources)
    if dict(result["usage"]) != usage:
        _reject("saved resource usage mismatch")
    _check_source(corridor, "corridor", attachment["datum"], resources)
    _check_source(sea, "sea", attachment["datum"], resources)
    if result["identity_sha256"] != fingerprint({key: value for key, value in result.items() if key != "identity_sha256"}):
        _reject("coast product identity mismatch")
    section = attachment["cross_section_xz_m"]
    center = attachment["center_index"]
    rows, columns = len(stations), len(section)
    if stations[0] != section[0, 1] or np.any(np.diff(stations) <= 0):
        _reject("invalid saved station origin/order")
    if (np.min(np.diff(section[:, 0])) + 1e-10 < max(corridor["spacing_x_m"], sea["spacing_x_m"]) or
            np.min(np.diff(stations)) + 1e-10 < corridor["spacing_z_m"]):
        _reject("saved mesh exceeds source precision")
    upstream = _static_attachment(attachment, result["proof_support"], result["arrays"]["river_indices"], result["arrays"]["river_weights"])
    _aligned_sources(corridor, sea, section, stations, upstream["fine_spacing_x_m"])
    if sea["sea_level_m"] >= upstream["water_m"][center] or corridor["sea_level_m"] != sea["sea_level_m"]:
        _reject("unsupported high or inconsistent sea level")
    arrays = result["arrays"]
    array_keys = {"bed_xyz_m", "water_xyz_m", "triangles", "h0_m", "centerline_xyz_m",
                  "corridor_indices", "corridor_weights", "sea_indices", "sea_weights",
                  "river_indices", "river_weights", "corridor_support_cells", "corridor_source_triangles"}
    if set(arrays) != array_keys:
        _reject("mesh array members mismatch")
    for name, array in arrays.items():
        if (not isinstance(array, np.ndarray) or array.flags.writeable or array.dtype.kind not in "fiu" or
                not np.all(np.isfinite(array))):
            _reject("saved output array must be immutable finite numeric: " + name)
    bed_xyz, water_xyz, triangles = arrays["bed_xyz_m"], arrays["water_xyz_m"], arrays["triangles"]
    if (bed_xyz.shape != (rows * columns, 3) or water_xyz.shape != bed_xyz.shape or
            triangles.shape != (2 * (rows - 1) * (columns - 1), 3) or triangles.dtype.kind not in "iu"):
        _reject("saved mesh shapes/dtype mismatch")
    xz = bed_xyz[:, [0, 2]]
    _same(xz[:, 0], np.tile(section[:, 0], rows), "world x")
    _same(xz[:, 1], np.repeat(stations, columns), "world z")
    _same(water_xyz[:, [0, 2]], xz, "bed/water planar registration")
    offset = 0
    for row in range(rows - 1):
        for column in range(columns - 1):
            first = row * columns + column
            if (not np.array_equal(triangles[offset], [first, first + 1, first + columns]) or
                    not np.array_equal(triangles[offset + 1], [first + 1, first + columns + 1, first + columns])):
                _reject("saved triangles not connected strip topology")
            offset += 2
    _same(bed_xyz[:columns, 1], upstream["h2_m"], "actual full-width river H2")
    _same(water_xyz[:columns, 1], upstream["water_m"], "actual transverse river stage")
    for role, points in (("corridor", xz), ("sea", xz[-columns:])):
        source = inputs[role]
        indices, weights = arrays[role + "_indices"], arrays[role + "_weights"]
        _saved_support(indices, weights, points, source, source["h0_m"].shape)
        _support(indices, weights, source["valid_mask"], source["unknown_mask"],
                 source["protected_mask"], source["wet_mask"], source["ocean_mask"] if role == "sea" else None)
        saved_bed = bed_xyz[:, 1] if role == "corridor" else bed_xyz[-columns:, 1]
        saved_water = water_xyz[:, 1] if role == "corridor" else water_xyz[-columns:, 1]
        _same(saved_bed, np.sum(source["h2_m"].ravel()[indices] * weights, axis=1), role + " explicit H2")
        _same(saved_water, np.sum(source["water_m"].ravel()[indices] * weights, axis=1), role + " explicit water")
    support_cells = arrays["corridor_support_cells"]
    saved_indices = arrays["corridor_indices"][:, 0]
    if not np.array_equal(support_cells, saved_indices) or len(np.unique(support_cells)) != rows * columns:
        _reject("saved full-strip source cell/node ownership differs")
    _support(support_cells[:, None], np.ones((len(support_cells), 1)), corridor["valid_mask"], corridor["unknown_mask"],
             corridor["protected_mask"], corridor["wet_mask"])
    source_triangles = arrays["corridor_source_triangles"]
    if source_triangles.dtype.kind not in "iu" or not np.array_equal(source_triangles, saved_indices[triangles]):
        _reject("saved source triangle mapping differs from full strip")
    for name, source_name, mesh_values in (("H0", "h0_m", arrays["h0_m"]),
                                           ("H2", "h2_m", bed_xyz[:, 1]),
                                           ("water", "water_m", water_xyz[:, 1])):
        _same(mesh_values[triangles], corridor[source_name].ravel()[source_triangles],
              "full triangle affine source " + name)
    _same(water_xyz[-columns:, 1], np.full(columns, sea["sea_level_m"]), "sea level attachment")
    fraction = (stations - stations[0]) / (stations[-1] - stations[0])
    _same(bed_xyz[:, 1].reshape(rows, columns),
          (1 - fraction[:, None]) * bed_xyz[:columns, 1] + fraction[:, None] * bed_xyz[-columns:, 1], "longitudinal bed continuity")
    _same(water_xyz[:, 1].reshape(rows, columns),
          (1 - fraction[:, None]) * water_xyz[:columns, 1] + fraction[:, None] * water_xyz[-columns:, 1], "longitudinal stage continuity")
    _same(arrays["centerline_xyz_m"], water_xyz[np.arange(rows) * columns + center], "centerline XYZ")
    _same(arrays["h0_m"], np.sum(corridor["h0_m"].ravel()[arrays["corridor_indices"]] * arrays["corridor_weights"], axis=1), "corridor H0")
    _mesh_gate(bed_xyz, water_xyz, triangles)
    expected_ledger = _budget_ledger(arrays["h0_m"], bed_xyz[:, 1], xz, triangles, budget)
    if set(result["ledger"]) != set(expected_ledger):
        _reject("ledger schema mismatch")
    for name, expected in expected_ledger.items():
        if isinstance(expected, str):
            if result["ledger"][name] != expected:
                _reject("ledger semantics mismatch")
        else:
            _same(result["ledger"][name], expected, "cut ledger " + name)
    attach_output = result["attachment"]
    expected_attachment = {"recovery_sha256": upstream["recovery_sha256"], "terminal_node": upstream["terminal_node"],
                           "terminal_q_m3_s": upstream["terminal_q_m3_s"],
                           "river_bed_xyz_m": bed_xyz[:columns], "river_water_xyz_m": water_xyz[:columns],
                           "sea_bed_xyz_m": bed_xyz[-columns:], "sea_water_xyz_m": water_xyz[-columns:]}
    if set(attach_output) != set(expected_attachment):
        _reject("saved full-width attachment schema mismatch")
    for name, expected in expected_attachment.items():
        if isinstance(expected, str):
            if attach_output[name] != expected:
                _reject("saved recovery identity mismatch")
        else:
            _same(attach_output[name], expected, "attachment " + name)
    return {"valid": True, "identity_sha256": result["identity_sha256"], "static_sources_and_geometry_verified": True,
            "terminal_q_m3_s": upstream["terminal_q_m3_s"], "natural_outlet_certified": False}


def query_coast_drop(result):
    """Generation-free immutable view after static proof."""
    validate_coast_drop(result)
    return _freeze({"arrays": result["arrays"], "attachment": result["attachment"], "ledger": result["ledger"]})


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject("duplicate coast JSON key")
        result[key] = value
    return result


def _constant(value):
    _reject("nonfinite coast JSON constant")


def save_coast_drop(result, path):
    validate_coast_drop(result)
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    arrays = {}
    tree = _tree(result, arrays)
    metadata = _json({"format": VERSION + "-npy-v1", "tree": tree}).encode("ascii")
    if len(arrays) + 1 > MAX_MEMBERS or len(metadata) > MAX_METADATA_BYTES:
        _reject("save member/metadata cap")
    descriptor, temporary = tempfile.mkstemp(prefix=".coast-drop-", dir=path.parent)
    try:
        stream = os.fdopen(descriptor, "w+b")
        descriptor = None
        with stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("metadata.json", metadata)
                for name, array in arrays.items():
                    with archive.open(name, "w") as member:
                        np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            if stream.tell() > MAX_BYTES:
                _reject("bundle file cap")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.unlink(temporary)
    return path


def _read_header(stream, info, spec):
    if np.lib.format.read_magic(stream) != (1, 0):
        _reject("only coast NPY v1 supported")
    length_bytes = stream.read(2)
    if len(length_bytes) != 2 or int.from_bytes(length_bytes, "little") > MAX_HEADER_BYTES - 10:
        _reject("coast NPY header cap")
    header_length = int.from_bytes(length_bytes, "little")
    header = stream.read(header_length)
    if len(header) != header_length:
        _reject("truncated coast header")
    shape, fortran, dtype = np.lib.format.read_array_header_1_0(io.BytesIO(length_bytes + header), max_header_size=MAX_HEADER_BYTES)
    payload_bytes = math.prod(shape) * dtype.itemsize
    if (list(shape) != spec["shape"] or dtype.str != spec["dtype"] or dtype.kind not in "bifu" or
            fortran or payload_bytes + stream.tell() != info.file_size or payload_bytes > MAX_BYTES):
        _reject("coast header/dtype/exact payload mismatch")
    return shape, dtype, payload_bytes


def load_coast_drop(path):
    """Strict bounded static load; no prepare/recover/mesh generator invocation."""
    try:
        with Path(path).open("rb") as file:
            if os.fstat(file.fileno()).st_size > MAX_BYTES:
                _reject("coast file resource cap")
            with zipfile.ZipFile(file) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if (len(infos) > MAX_MEMBERS or len(names) != len(set(names)) or
                        any(info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1 for info in infos) or
                        sum(info.file_size for info in infos) > MAX_BYTES):
                    _reject("archive duplicate/member/payload cap or unsupported compression")
                if "metadata.json" not in names or archive.getinfo("metadata.json").file_size > MAX_METADATA_BYTES:
                    _reject("coast metadata missing or resource cap")
                metadata = json.loads(archive.read("metadata.json"), object_pairs_hook=_pairs, parse_constant=_constant)
                if set(metadata) != {"format", "tree"} or metadata["format"] != VERSION + "-npy-v1":
                    _reject("coast metadata format/schema mismatch")
                specs = {}

                def inspect(value, depth=0):
                    if depth > 40:
                        _reject("coast metadata nesting cap")
                    if isinstance(value, dict) and "$array" in value:
                        if set(value) != {"$array", "shape", "dtype", "sha256"}:
                            _reject("invalid saved array reference")
                        name = value["$array"]
                        shape = value["shape"]
                        if (not isinstance(name, str) or name in specs or "/" in name or "\\" in name or
                                not name.startswith("array_") or not name.endswith(".npy") or
                                not isinstance(shape, list) or len(shape) > 4 or
                                any(type(size) is not int or size < 0 or size > 1000000 for size in shape) or
                                math.prod(shape) > 1000000):
                            _reject("saved array dimensions/name cap")
                        dtype = np.dtype(value["dtype"])
                        if dtype.kind not in "bifu" or dtype.itemsize > 8 or math.prod(shape) * dtype.itemsize > MAX_BYTES:
                            _reject("saved array dtype/payload cap")
                        specs[name] = value
                    elif isinstance(value, dict):
                        for child in value.values():
                            inspect(child, depth + 1)
                    elif isinstance(value, list):
                        for child in value:
                            inspect(child, depth + 1)

                inspect(metadata["tree"])
                if set(names) != {"metadata.json"} | set(specs):
                    _reject("missing/unexpected coast members")
                saved_inputs = metadata["tree"]["inputs"]
                resource_record = saved_inputs["resources"]
                resources = DropResources(**resource_record)
                if sum(math.prod(spec["shape"]) * np.dtype(spec["dtype"]).itemsize for spec in specs.values()) > resources.max_retained_bytes:
                    _reject("saved original retained cap before payload allocation")
                vertex_count = metadata["tree"]["arrays"]["bed_xyz_m"]["shape"][0]
                triangle_count = metadata["tree"]["arrays"]["triangles"]["shape"][0]
                if (vertex_count > resources.max_vertices or triangle_count > resources.max_triangles or
                        vertex_count * 12 > resources.max_work or
                        sum(math.prod(saved_inputs[role]["h0_m"]["shape"]) for role in ("corridor", "sea")) > resources.max_source_cells):
                    _reject("saved original mesh/source resource cap before allocation")
                payload_total = 0
                for name, spec in specs.items():
                    with archive.open(name) as stream:
                        _, _, size = _read_header(stream, archive.getinfo(name), spec)
                        payload_total += size
                if payload_total > MAX_BYTES:
                    _reject("aggregate coast array cap")
                arrays = {}
                for name, spec in specs.items():
                    with archive.open(name) as stream:
                        shape, dtype, size = _read_header(stream, archive.getinfo(name), spec)
                        payload = stream.read(size + 1)
                        if len(payload) != size:
                            _reject("coast truncated or trailing payload")
                        array = np.frombuffer(payload, dtype=dtype).reshape(shape)
                        if _array_hash(array) != spec["sha256"]:
                            _reject("saved coast array hash mismatch")
                        arrays[name] = array

        def decode(value):
            if isinstance(value, dict) and "$array" in value:
                return arrays[value["$array"]]
            if isinstance(value, dict):
                return {key: decode(child) for key, child in value.items()}
            if isinstance(value, list):
                return [decode(child) for child in value]
            return value

        result = _freeze(decode(metadata["tree"]))
        validate_coast_drop(result)
        return result
    except (OSError, KeyError, TypeError, RecursionError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise CoastDropError("invalid coast bundle") from error
