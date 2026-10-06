"""Reduced original-bed basin storage and spill events.

This module is an event diagnostic for the natural-river candidate.  It keeps
one water inventory per contribution basin, derives the water level from the
original bed hypsometry, and exchanges water only across a pinned physical
face.  Engineering perimeter discharge is recorded separately from natural
outlet evidence.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, publish_bytes, readonly
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy


SCHEMA = "td-original-bed-basin-overflow-v1"
MAX_LEAVES = 250_000
MAX_FACES = 500_000
MAX_STEPS = 100_000


@dataclass(frozen=True)
class OverflowParameters:
    runoff_coefficient: float = 0.35
    baseflow_mm_per_day: float = 0.15
    face_conductance_m_s: float = 0.6
    boundary_conductance_m_s: float = 0.6
    timestep_s: float = 300.0
    duration_s: float = 86400.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"positive finite overflow parameter required: {name}")
        if not 0 < self.runoff_coefficient <= 1:
            raise ValueError("runoff coefficient outside (0,1]")
        if self.duration_s / self.timestep_s != int(self.duration_s / self.timestep_s):
            raise ValueError("duration must contain an integer number of steps")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    return value


def _face_id(hierarchy, face_index):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    columns = arrays["height_m"].shape[1]
    endpoints = []
    for cell in arrays["face_cells"][face_index]:
        row, column = divmod(int(cell), columns)
        point = (float(metadata["origin_m_xz"][0] + column * metadata["spacing_m"]),
                 float(arrays["height_m"].ravel()[cell]),
                 float(metadata["origin_m_xz"][1] + row * metadata["spacing_m"]))
        endpoints.append([value.hex() for value in point])
    return "face:" + _hash([metadata["source_identity_sha256"], sorted(endpoints)])


def _curves(hierarchy):
    arrays = hierarchy["arrays"]
    owners = arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    bed = arrays["height_m"].ravel()
    leaves = np.unique(owners[valid]).astype(np.int64)
    if len(leaves) == 0 or len(leaves) > MAX_LEAVES:
        raise ValueError("invalid contribution basin count")
    leaf_index = {int(leaf): index for index, leaf in enumerate(leaves)}
    offsets = [0]
    levels, areas = [], []
    for leaf in leaves:
        values = np.sort(bed[valid & (owners == leaf)])
        unique, counts = np.unique(values, return_counts=True)
        levels.extend(unique.tolist())
        areas.extend((counts * float(hierarchy["metadata"]["spacing_m"]) ** 2).tolist())
        offsets.append(offsets[-1] + len(unique))
    return leaves, np.asarray(offsets, np.int64), np.asarray(levels, np.float64), np.asarray(areas, np.float64), leaf_index


def _volume_at(stage, levels, areas):
    if stage <= levels[0]:
        return 0.0
    return float(np.maximum(stage - levels, 0.0).dot(areas))


def _stage_at(volume, levels, areas):
    if volume <= 0:
        return float(levels[0])
    cumulative = 0.0
    prefix_area = 0.0
    for index, level in enumerate(levels[:-1]):
        prefix_area += float(areas[index])
        next_level = levels[index + 1]
        capacity = float((next_level - level) * prefix_area)
        if volume <= cumulative + capacity + 1e-12:
            return float(level + (volume - cumulative) / prefix_area)
        cumulative += capacity
    prefix_area += float(areas[-1])
    return float(levels[-1] + (volume - cumulative) / prefix_area)


def _physical_faces(hierarchy, leaves, leaf_index):
    arrays = hierarchy["arrays"]
    owners = arrays["contribution_owner"].ravel()
    bed = arrays["height_m"].ravel()
    candidates = {}
    for face_index, cells in enumerate(arrays["face_cells"]):
        first, second = map(int, cells)
        left, right = int(owners[first]), int(owners[second])
        if left == right or left not in leaf_index or right not in leaf_index:
            continue
        pair = tuple(sorted((left, right)))
        sill = float(max(bed[first], bed[second]))
        existing = candidates.get(pair)
        if existing is None or (sill, _face_id(hierarchy, face_index)) < (existing["sill_m"], existing["face_id"]):
            candidates[pair] = {"face_index": face_index, "face_id": _face_id(hierarchy, face_index),
                                "leaf_ids": list(pair), "cell_ids": [first, second], "sill_m": sill}
    return list(candidates.values())


def _boundary_faces(hierarchy, leaves, leaf_index):
    arrays = hierarchy["arrays"]
    owners = arrays["contribution_owner"].ravel()
    bed = arrays["height_m"].ravel()
    shape = arrays["height_m"].shape
    spacing = float(hierarchy["metadata"]["spacing_m"])
    records = []
    for cell in np.flatnonzero(arrays["open_boundary_mask"].ravel()):
        leaf = int(owners[cell])
        if leaf not in leaf_index:
            continue
        row, column = divmod(int(cell), shape[1])
        sides = int(row == 0) + int(row == shape[0] - 1) + int(column == 0) + int(column == shape[1] - 1)
        records.append({"cell_id": int(cell), "leaf_id": leaf, "sill_m": float(bed[cell]),
                        "width_m": float(sides * spacing), "face_count": sides})
    return records


def build_overflow_topology(hierarchy, *, expected_hierarchy_identity=None):
    validate_basin_hierarchy(hierarchy)
    if expected_hierarchy_identity is not None and hierarchy["identity_sha256"] != expected_hierarchy_identity:
        raise ValueError("hierarchy identity mismatch")
    leaves, offsets, levels, areas, leaf_index = _curves(hierarchy)
    faces = _physical_faces(hierarchy, leaves, leaf_index)
    boundaries = _boundary_faces(hierarchy, leaves, leaf_index)
    if len(faces) > MAX_FACES:
        raise ValueError("physical face budget exceeded")
    leaf_areas = np.zeros(len(leaves), np.float64)
    for index in range(len(leaves)):
        start, end = offsets[index], offsets[index + 1]
        leaf_areas[index] = areas[start:end].sum() / (levels[end - 1] - levels[start] + 1e-300) if end > start else 0
        leaf_areas[index] = float(np.sum(areas[start:end]))
    metadata = {"schema": SCHEMA, "algorithm": "original-bed-hypsometry-face-reservoir-v1",
                "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
                "spacing_m": hierarchy["metadata"]["spacing_m"], "origin_m_xz": hierarchy["metadata"]["origin_m_xz"],
                "leaf_count": len(leaves), "physical_face_count": len(faces),
                "engineering_boundary_face_count": len(boundaries),
                "surface_storage_semantics": "volume is water above immutable original bed inside one contribution basin",
                "face_semantics": "one lowest-sill physical D4 face per contribution-leaf pair; ties resolve by face identity",
                "boundary_semantics": "explicit engineering open perimeter discharge, never natural outlet evidence",
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    arrays = {"leaf_ids": readonly(leaves), "curve_offsets": readonly(offsets), "curve_level_m": readonly(levels),
              "curve_area_m2": readonly(areas), "leaf_area_m2": readonly(leaf_areas)}
    result = {"arrays": arrays, "metadata": metadata,
              "faces": faces, "engineering_boundaries": boundaries}
    result["identity_sha256"] = _topology_identity(result)
    return result


def _validate_rain(rain_mm_h, steps):
    rain = np.asarray(rain_mm_h, dtype=np.float64)
    if rain.ndim != 1 or rain.size != steps or not np.isfinite(rain).all() or np.any(rain < 0):
        raise ValueError("rainfall must be a finite nonnegative hourly-rate vector")
    return rain


def simulate_overflow(topology, rain_mm_h, *, parameters=None, initial_volume_m3=None):
    if topology["metadata"]["schema"] != SCHEMA:
        raise ValueError("overflow topology schema mismatch")
    config = OverflowParameters() if parameters is None else parameters
    if not isinstance(config, OverflowParameters):
        raise ValueError("OverflowParameters required")
    steps = int(config.duration_s / config.timestep_s)
    if steps > MAX_STEPS:
        raise ValueError("overflow step budget exceeded")
    rain = _validate_rain(rain_mm_h, steps)
    arrays, metadata = topology["arrays"], topology["metadata"]
    leaf_lookup = {int(leaf): index for index, leaf in enumerate(arrays["leaf_ids"])}
    leaf_count = metadata["leaf_count"]
    levels, areas, offsets = arrays["curve_level_m"], arrays["curve_area_m2"], arrays["curve_offsets"]
    leaf_areas = arrays["leaf_area_m2"]
    volumes = np.zeros(leaf_count, np.float64) if initial_volume_m3 is None else np.asarray(initial_volume_m3, dtype=np.float64).copy()
    if volumes.shape != (leaf_count,) or not np.isfinite(volumes).all() or np.any(volumes < 0):
        raise ValueError("invalid initial basin water inventory")
    stages = np.zeros((steps + 1, leaf_count), np.float64)
    water = np.zeros((steps + 1, leaf_count), np.float64)
    input_volume = np.zeros((steps, leaf_count), np.float64)
    exchanged = np.zeros((steps, len(topology["faces"])), np.float64)
    exchanged_forward = np.zeros_like(exchanged)
    exchanged_reverse = np.zeros_like(exchanged)
    exchanged_net = np.zeros_like(exchanged)
    basin_net_internal = np.zeros((steps, leaf_count), np.float64)
    basin_gross_internal = np.zeros((steps, leaf_count), np.float64)
    basin_boundary_outflow = np.zeros((steps, leaf_count), np.float64)
    boundary_outflow = np.zeros((steps, len(topology["engineering_boundaries"])), np.float64)
    balance = np.zeros(steps, np.float64)
    onset = np.full(len(topology["faces"]), -1, np.int64)
    for leaf_index in range(leaf_count):
        start, end = offsets[leaf_index], offsets[leaf_index + 1]
        stages[0, leaf_index] = _stage_at(volumes[leaf_index], levels[start:end], areas[start:end])
    water[0] = volumes
    for step in range(steps):
        before = float(volumes.sum())
        rates = rain[step] / 1000.0 * config.runoff_coefficient / 3600.0 + config.baseflow_mm_per_day / 1000.0 / 86400.0
        added = leaf_areas * rates * config.timestep_s
        input_volume[step] = added
        volumes += added
        current_stages = np.zeros(leaf_count, np.float64)
        for leaf_index in range(leaf_count):
            start, end = offsets[leaf_index], offsets[leaf_index + 1]
            current_stages[leaf_index] = _stage_at(volumes[leaf_index], levels[start:end], areas[start:end])
        face_proposed = np.zeros(len(topology["faces"]), np.float64)
        face_donors = np.zeros(len(topology["faces"]), np.int64)
        face_recipients = np.zeros(len(topology["faces"]), np.int64)
        face_directions = np.zeros(len(topology["faces"]), np.int8)
        for face_index, face in enumerate(topology["faces"]):
            first, second = (leaf_lookup[face["leaf_ids"][0]], leaf_lookup[face["leaf_ids"][1]])
            stage_first, stage_second = current_stages[first], current_stages[second]
            sill = face["sill_m"]
            if stage_first >= stage_second:
                donor, recipient, excess = first, second, stage_first - max(sill, stage_second)
                direction = 1
            else:
                donor, recipient, excess = second, first, stage_second - max(sill, stage_first)
                direction = -1
            face_proposed[face_index] = max(0.0, config.face_conductance_m_s * metadata["spacing_m"] * excess * config.timestep_s)
            face_donors[face_index] = donor
            face_recipients[face_index] = recipient
            face_directions[face_index] = direction
        boundary_proposed = np.zeros(len(topology["engineering_boundaries"]), np.float64)
        for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
            leaf = leaf_lookup[boundary["leaf_id"]]
            excess = max(0.0, current_stages[leaf] - boundary["sill_m"])
            boundary_proposed[boundary_index] = max(0.0, config.boundary_conductance_m_s * boundary["width_m"] * excess * config.timestep_s)
        demand = np.bincount(face_donors, weights=face_proposed, minlength=leaf_count)
        boundary_leaves = np.asarray([leaf_lookup[item["leaf_id"]] for item in topology["engineering_boundaries"]], dtype=np.int64)
        if boundary_leaves.size:
            np.add.at(demand, boundary_leaves, boundary_proposed)
        scale = np.minimum(1.0, np.divide(volumes, demand, out=np.ones_like(volumes), where=demand > 0))
        delta = np.zeros(leaf_count, np.float64)
        for face_index in range(len(topology["faces"])):
            volume = face_proposed[face_index] * scale[face_donors[face_index]]
            if volume <= 0:
                continue
            donor, recipient = face_donors[face_index], face_recipients[face_index]
            delta[donor] -= volume
            delta[recipient] += volume
            exchanged[step, face_index] = volume
            if face_directions[face_index] > 0:
                exchanged_forward[step, face_index] = volume
            else:
                exchanged_reverse[step, face_index] = volume
            signed = volume if face_directions[face_index] > 0 else -volume
            exchanged_net[step, face_index] = signed
            basin_net_internal[step, donor] -= volume
            basin_net_internal[step, recipient] += volume
            basin_gross_internal[step, donor] += volume
            basin_gross_internal[step, recipient] += volume
            if onset[face_index] < 0:
                onset[face_index] = step
        volumes += delta
        for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
            leaf = boundary_leaves[boundary_index]
            volume = boundary_proposed[boundary_index] * scale[leaf]
            volumes[leaf] -= volume
            boundary_outflow[step, boundary_index] = volume
            basin_boundary_outflow[step, leaf] += volume
        if np.any(volumes < -1e-8):
            raise ValueError("negative basin water inventory")
        volumes = np.maximum(volumes, 0.0)
        after = float(volumes.sum())
        balance[step] = float(added.sum() - boundary_outflow[step].sum() - (after - before))
        for leaf_index in range(leaf_count):
            start, end = offsets[leaf_index], offsets[leaf_index + 1]
            stages[step + 1, leaf_index] = _stage_at(volumes[leaf_index], levels[start:end], areas[start:end])
        water[step + 1] = volumes
    arrays_out = {"rain_mm_h": rain, "stage_m": stages, "volume_m3": water,
                  "input_volume_m3": input_volume, "face_volume_m3": exchanged,
                  "face_forward_m3": exchanged_forward, "face_reverse_m3": exchanged_reverse,
                  "face_net_m3": exchanged_net, "basin_net_internal_m3": basin_net_internal,
                  "basin_gross_internal_m3": basin_gross_internal,
                  "basin_boundary_outflow_m3": basin_boundary_outflow,
                  "basin_balance_residual_m3": input_volume + basin_net_internal - basin_boundary_outflow - np.diff(water, axis=0),
                  "engineering_boundary_outflow_m3": boundary_outflow, "balance_residual_m3": balance,
                  "spill_onset_step": onset}
    out_meta = {"schema": "td-original-bed-overflow-event-v2", "algorithm": "synchronous-basin-face-exchange-v2",
                "topology_identity_sha256": topology["identity_sha256"], "hierarchy_identity_sha256": metadata["hierarchy_identity_sha256"],
                "source_identity_sha256": metadata["source_identity_sha256"], "parameters": asdict(config),
                "steps": steps, "timestep_s": config.timestep_s, "duration_s": config.duration_s,
                "rain_semantics": "representative runoff input after a fixed runoff coefficient plus uniform baseflow; no atmospheric solver",
                "spill_semantics": "a face event begins when synchronous source head exceeds its physical sill and destination head",
                "flux_semantics": "face_net_m3 is signed first-leaf-to-second-leaf volume; basin_net_internal_m3 is positive into a basin; gross exchange is a round-trip diagnostic",
                "engineering_boundary_semantics": "outflow leaves the finite engineering domain and is not natural outlet evidence",
                "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False, "publishable": False}
    result = {"arrays": {key: readonly(value) for key, value in arrays_out.items()}, "metadata": out_meta}
    result["identity_sha256"] = identity(result["arrays"], out_meta)
    validate_overflow_event(result, topology)
    return result


def validate_overflow_event(result, topology):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") not in ("td-original-bed-overflow-event-v1", "td-original-bed-overflow-event-v2") or result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("overflow event identity/schema mismatch")
    if metadata.get("topology_identity_sha256") != topology["identity_sha256"]:
        raise ValueError("overflow event topology identity mismatch")
    steps = metadata["steps"]
    leaves = topology["metadata"]["leaf_count"]
    faces = len(topology["faces"])
    boundaries = len(topology["engineering_boundaries"])
    expected = {
        "rain_mm_h": (steps,), "stage_m": (steps + 1, leaves), "volume_m3": (steps + 1, leaves),
        "input_volume_m3": (steps, leaves), "face_volume_m3": (steps, faces),
        "face_forward_m3": (steps, faces), "face_reverse_m3": (steps, faces),
        "engineering_boundary_outflow_m3": (steps, boundaries),
        "balance_residual_m3": (steps,), "spill_onset_step": (faces,),
    }
    if metadata.get("schema") == "td-original-bed-overflow-event-v2":
        expected.update({"face_net_m3": (steps, faces),
                         "basin_net_internal_m3": (steps, leaves),
                         "basin_gross_internal_m3": (steps, leaves),
                         "basin_boundary_outflow_m3": (steps, leaves),
                         "basin_balance_residual_m3": (steps, leaves)})
    if any(arrays.get(key) is None or arrays[key].shape != shape for key, shape in expected.items()):
        raise ValueError("overflow event time shape mismatch")
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("overflow event nonfinite field")
    for flag in ("hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable"):
        if metadata.get(flag) is not False:
            raise ValueError("overflow diagnostic cannot certify hydraulics or natural outlets")
    if not np.isfinite(arrays["stage_m"]).all() or np.any(arrays["volume_m3"] < -1e-8):
        raise ValueError("overflow event negative state")
    if any(np.any(arrays[key] < 0) for key in ("rain_mm_h", "input_volume_m3", "face_volume_m3",
                                               "face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3")):
        raise ValueError("overflow event negative volume")
    if not np.allclose(arrays["face_volume_m3"], arrays["face_forward_m3"] + arrays["face_reverse_m3"], rtol=0, atol=1e-9):
        raise ValueError("overflow event directional face ledger mismatch")
    leaf_lookup = {int(leaf): index for index, leaf in enumerate(topology["arrays"]["leaf_ids"])}
    expected_net = np.zeros((steps, leaves), np.float64)
    expected_gross = np.zeros_like(expected_net)
    expected_boundary = np.zeros_like(expected_net)
    for face_index, face in enumerate(topology["faces"]):
        first, second = (leaf_lookup[leaf] for leaf in face["leaf_ids"])
        signed = arrays["face_forward_m3"][:, face_index] - arrays["face_reverse_m3"][:, face_index]
        gross = arrays["face_volume_m3"][:, face_index]
        expected_net[:, first] -= signed
        expected_net[:, second] += signed
        expected_gross[:, first] += gross
        expected_gross[:, second] += gross
    for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
        expected_boundary[:, leaf_lookup[boundary["leaf_id"]]] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    local_residual = arrays["input_volume_m3"] + expected_net - expected_boundary - np.diff(arrays["volume_m3"], axis=0)
    if np.any(np.abs(local_residual) > 1e-7):
        raise ValueError("overflow event basin storage closure failed")
    global_residual = arrays["input_volume_m3"].sum(axis=1) - expected_boundary.sum(axis=1) - np.diff(arrays["volume_m3"].sum(axis=1))
    if not np.allclose(global_residual, arrays["balance_residual_m3"], rtol=0, atol=1e-7):
        raise ValueError("overflow event saved global residual mismatch")
    if metadata.get("schema") == "td-original-bed-overflow-event-v2":
        if not np.allclose(arrays["face_net_m3"], arrays["face_forward_m3"] - arrays["face_reverse_m3"], rtol=0, atol=1e-9):
            raise ValueError("overflow event net face ledger mismatch")
        if not np.allclose(arrays["basin_net_internal_m3"], expected_net, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin net ledger mismatch")
        if not np.allclose(arrays["basin_gross_internal_m3"], expected_gross, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin gross ledger mismatch")
        if not np.allclose(arrays["basin_boundary_outflow_m3"], expected_boundary, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin boundary ledger mismatch")
        if not np.allclose(arrays["basin_balance_residual_m3"], local_residual, rtol=0, atol=1e-9):
            raise ValueError("overflow event basin residual mismatch")
    if not np.issubdtype(arrays["spill_onset_step"].dtype, np.integer):
        raise ValueError("overflow event onset must be integer")
    active = arrays["face_volume_m3"] > 0
    expected_onset = np.where(active.any(axis=0), active.argmax(axis=0), -1) if faces else np.empty(0, np.int64)
    if not np.array_equal(arrays["spill_onset_step"], expected_onset):
        raise ValueError("overflow event onset differs from actual exchange")
    if np.any(arrays["spill_onset_step"] < -1) or np.any(arrays["spill_onset_step"] >= steps):
        raise ValueError("overflow event onset index invalid")
    if np.any(np.abs(arrays["balance_residual_m3"]) > 1e-7):
        raise ValueError("overflow event water ledger failed")
    return True


def _topology_payload(result):
    return {"schema": "td-original-bed-overflow-topology-v1", "metadata": result["metadata"],
               "arrays": {key: value.tolist() for key, value in result["arrays"].items()},
               "faces": result["faces"], "engineering_boundaries": result["engineering_boundaries"]}


def add_saved_overflow_accounting(event, topology):
    validate_overflow_event(event, topology)
    arrays = dict(event["arrays"])
    steps = event["metadata"]["steps"]
    leaf_lookup = {int(leaf): index for index, leaf in enumerate(topology["arrays"]["leaf_ids"])}
    net = np.zeros((steps, len(leaf_lookup)), np.float64)
    gross = np.zeros_like(net)
    boundary = np.zeros_like(net)
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    for face_index, face in enumerate(topology["faces"]):
        first, second = (leaf_lookup[leaf] for leaf in face["leaf_ids"])
        net[:, first] -= signed[:, face_index]
        net[:, second] += signed[:, face_index]
        gross[:, first] += arrays["face_volume_m3"][:, face_index]
        gross[:, second] += arrays["face_volume_m3"][:, face_index]
    for boundary_index, face in enumerate(topology["engineering_boundaries"]):
        boundary[:, leaf_lookup[face["leaf_id"]]] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    arrays.update(face_net_m3=signed, basin_net_internal_m3=net, basin_gross_internal_m3=gross,
                  basin_boundary_outflow_m3=boundary,
                  basin_balance_residual_m3=arrays["input_volume_m3"] + net - boundary - np.diff(arrays["volume_m3"], axis=0))
    metadata = dict(event["metadata"], schema="td-original-bed-overflow-event-v2",
                    algorithm="synchronous-basin-face-exchange-v2",
                    flux_semantics="face_net_m3 is signed first-leaf-to-second-leaf volume; basin_net_internal_m3 is positive into a basin; gross exchange is a round-trip diagnostic")
    result = {"arrays": {key: readonly(value) for key, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = identity(result["arrays"], metadata)
    validate_overflow_event(result, topology)
    return result


def _topology_identity(result):
    return _hash(_topology_payload(result))


def save_overflow_topology(result, path):
    payload = _topology_payload(result)
    if _hash(payload) != result["identity_sha256"]:
        raise ValueError("topology identity mismatch")
    payload["identity_sha256"] = result["identity_sha256"]
    publish_bytes(path, json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def load_overflow_topology(path, *, expected_sha256, expected_identity):
    path = Path(path)
    if file_sha256(path) != expected_sha256:
        raise ValueError("overflow topology SHA mismatch")
    payload = json.loads(path.read_bytes())
    digest = payload.pop("identity_sha256", None)
    if digest != expected_identity or _hash(payload) != digest:
        raise ValueError("overflow topology identity mismatch")
    arrays = {key: readonly(np.asarray(value)) for key, value in payload["arrays"].items()}
    return {"arrays": arrays, "metadata": payload["metadata"], "faces": payload["faces"],
            "engineering_boundaries": payload["engineering_boundaries"], "identity_sha256": digest}


def save_overflow_event(result, path):
    payload = {"schema": "td-original-bed-overflow-event-json-v1", "metadata": result["metadata"],
               "arrays": {key: value.tolist() for key, value in result["arrays"].items()},
               "identity_sha256": result["identity_sha256"]}
    publish_bytes(path, json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def load_overflow_event(path, *, expected_sha256, expected_identity, topology):
    path = Path(path)
    if path.stat().st_size > 128 * 1024 * 1024 or file_sha256(path) != expected_sha256:
        raise ValueError("overflow event hash/budget mismatch")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("nonfinite JSON value")

    payload = json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=reject_constant)
    if payload.get("schema") != "td-original-bed-overflow-event-json-v1":
        raise ValueError("overflow event schema mismatch")
    digest = payload.get("identity_sha256")
    if digest != expected_identity:
        raise ValueError("overflow event identity pin mismatch")
    arrays = {key: readonly(np.asarray(value, dtype=np.float64 if key != "spill_onset_step" else np.int64))
              for key, value in payload["arrays"].items()}
    result = {"arrays": arrays, "metadata": payload["metadata"], "identity_sha256": digest}
    validate_overflow_event(result, topology)
    return result
