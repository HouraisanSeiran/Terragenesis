"""Event-supported lake/spill connectivity on immutable saved basin beds."""

import hashlib
import json

import numpy as np

from terrain_pipeline.common_infra import publish_bytes
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_overflow import _face_id, _topology_identity
from terrain_pipeline.td_basin_runoff_exchange import validate_runoff_exchange
from terrain_pipeline.td_lake_outlet_forest import build_outlet_forest
from terrain_pipeline.td_lake_spill_geometry import trace_engineering_outlet, trace_spill_connection

SCHEMA = "td-lake-spill-graph-v1"
MIN_VOLUME_M3 = 1e-6
RELATIVE_TOLERANCE = .01
MAX_BYTES = 32 * 1024**2
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable", "permanent_trunk_ready")


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def face_evidence(first, second, position):
    fine, coarse = first["arrays"], second["arrays"]
    forward, reverse = fine["face_forward_m3"][:, position], fine["face_reverse_m3"][:, position]
    other_forward = coarse["face_forward_m3"][:, position]
    other_reverse = coarse["face_reverse_m3"][:, position]
    net, other = forward - reverse, other_forward - other_reverse
    gross, other_gross = forward + reverse, other_forward + other_reverse
    significant = np.maximum(gross, other_gross) >= MIN_VOLUME_M3
    active = np.flatnonzero(gross >= MIN_VOLUME_M3)
    signs = np.sign(net[active])
    signs = signs[signs != 0]
    switches = int(np.count_nonzero(signs[1:] != signs[:-1]))
    direction = int(np.sign(net.sum()))
    late_start = int(.8 * len(net))
    late_net = float(net[late_start:].sum())
    late_ref = float(other[late_start:].sum())
    late_abs = float(np.abs(net[late_start:]).sum())
    consistency = max(0., direction * late_net / late_abs) if late_abs else 0.
    error = float(np.abs(net[significant] - other[significant]).sum())
    scale = float(np.abs(other[significant]).sum())
    relative = error / max(scale, MIN_VOLUME_M3)
    interval_error = float(np.max(np.abs(net[significant] - other[significant]) /
        np.maximum(np.abs(other[significant]), MIN_VOLUME_M3))) if significant.any() else 0.
    reasons = []
    if not active.size or direction == 0:
        reasons.append("no_significant_directional_transfer")
    if switches:
        reasons.append("saved_interval_direction_switches")
    if direction * float(net.sum()) < (1. - RELATIVE_TOLERANCE) * float(gross.sum()):
        reasons.append("cancellation_exceeds_one_percent")
    if direction * late_net < MIN_VOLUME_M3 or direction * late_ref < MIN_VOLUME_M3:
        reasons.append("no_same_direction_late_reception")
    if consistency < 1. - RELATIVE_TOLERANCE:
        reasons.append("late_direction_not_consistent")
    if relative > RELATIVE_TOLERANCE or interval_error > RELATIVE_TOLERANCE:
        reasons.append("per_face_time_refinement_failed")
    if not np.array_equal(np.sign(net[significant]), np.sign(other[significant])):
        reasons.append("refinement_direction_disagreement")
    return {"stable_relationship": not reasons, "direction": direction,
            "forward_m3": float(forward.sum()), "reverse_m3": float(reverse.sum()),
            "net_m3": float(net.sum()), "gross_m3": float(gross.sum()),
            "canceled_m3": float(2 * min(forward.sum(), reverse.sum())),
            "active_interval_sign_switches": switches,
            "first_active_interval": int(active[0]) if active.size else None,
            "last_active_interval": int(active[-1]) if active.size else None,
            "late_start_interval": late_start, "late_net_m3": late_net,
            "late_direction_consistency": consistency,
            "interval_net_relative_l1_difference": relative,
            "max_interval_net_relative_difference": interval_error,
            "rejection_reasons": reasons}


def sampled_stage(event, leaf_index, interval_values):
    active = np.flatnonzero(interval_values >= MIN_VOLUME_M3)
    if not active.size:
        return None
    samples = np.unique(np.concatenate((active, active + 1)))
    position = int(samples[np.argmax(event["arrays"]["stage_m"][samples, leaf_index])])
    return {"saved_index": position, "time_s": position * event["metadata"]["timestep_s"],
            "stage_m": float(event["arrays"]["stage_m"][position, leaf_index]),
            "semantics": "saved stage adjacent to an active transfer interval; not an internal solver-stage sample"}


def interval_ranges(mask):
    positions = np.flatnonzero(mask)
    if not positions.size:
        return []
    groups = np.split(positions, np.flatnonzero(np.diff(positions) > 1) + 1)
    return [[int(group[0]), int(group[-1] + 1)] for group in groups]


def validate_inputs(hierarchy, topology, ordinary, ordinary_reference, strong, strong_reference):
    validate_basin_hierarchy(hierarchy)
    if (topology["identity_sha256"] != _topology_identity(topology) or
            topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            topology["metadata"]["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("lake graph requires matching immutable bed and physical topology")
    for selected, reference, duration in ((ordinary, ordinary_reference, 86400.), (strong, strong_reference, 21600.)):
        for event in (selected, reference):
            validate_runoff_exchange(event, topology)
            if event["metadata"]["duration_s"] != duration or event["metadata"]["timestep_s"] != 300.:
                raise ValueError("fixed ordinary/strong saved event interval required")
        for key in ("parameters", "runoff_metadata", "topology_identity_sha256", "source_identity_sha256"):
            if selected["metadata"][key] != reference["metadata"][key]:
                raise ValueError("event/reference physics or forcing differs")
        if (selected["identity_sha256"] == reference["identity_sha256"] or
                selected["metadata"]["max_step_s"] != 150. or reference["metadata"]["max_step_s"] != 300. or
                not np.array_equal(selected["arrays"]["rain_mm_h"], reference["arrays"]["rain_mm_h"])):
            raise ValueError("actual distinct 150s/300s surface integration required")


def build_lake_spill_graph(hierarchy, topology, ordinary, ordinary_reference, strong, strong_reference):
    validate_inputs(hierarchy, topology, ordinary, ordinary_reference, strong, strong_reference)
    arrays = hierarchy["arrays"]
    leaves = topology["arrays"]["leaf_ids"].tolist()
    lookup = {leaf: position for position, leaf in enumerate(leaves)}
    bed, owner = arrays["height_m"].ravel(), arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    columns = arrays["height_m"].shape[1]
    spacing, origin = hierarchy["metadata"]["spacing_m"], hierarchy["metadata"]["origin_m_xz"]
    nodes, blocked = [], []
    for position, leaf in enumerate(leaves):
        cells = np.flatnonzero(valid & (owner == leaf))
        sinks = cells[arrays["receiver"][cells] < 0]
        if len(sinks) != 1:
            raise ValueError("one static contribution terminal per leaf required")
        terminal = int(sinks[0])
        reasons = []
        if arrays["node_unknown_contact"][leaf]:
            reasons.append("unknown_contact")
        if protected[cells].any():
            reasons.append("protected_basin")
        if reasons:
            blocked.append(leaf)
        stages = ordinary["arrays"]["stage_m"][:, position]
        nodes.append({"leaf_id": leaf, "kind": "retained_basin_storage", "terminal_cell_id": terminal,
            "terminal_xyz_m": [origin[0] + terminal % columns * spacing, float(bed[terminal]),
                               origin[1] + terminal // columns * spacing],
            "exclusive_area_m2": float(topology["arrays"]["leaf_area_m2"][position]),
            "ordinary_stage_min_m": float(stages.min()), "ordinary_stage_max_m": float(stages.max()),
            "ordinary_max_surface_volume_m3": float(ordinary["arrays"]["surface_volume_m3"][:, position].max()),
            "ordinary_runoff_supply_m3": float(ordinary["arrays"]["outflow_volume_m3"][:, position].sum()),
            "blocked_reasons": reasons})
    edges, routed_edges = [], []
    for position, face in enumerate(topology["faces"]):
        hierarchy_index = face["face_index"]
        cells = arrays["face_cells"][hierarchy_index].tolist()
        if (cells != face["cell_ids"] or face["face_id"] != _face_id(hierarchy, hierarchy_index) or
                sorted(owner[cells].tolist()) != face["leaf_ids"] or face["sill_m"] != max(bed[cells])):
            raise ValueError("graph face differs from actual bed")
        normal = face_evidence(ordinary, ordinary_reference, position)
        storm = face_evidence(strong, strong_reference, position)
        item = {**face, "ordinary": normal, "strong": storm, "routing_eligible": False,
                "strong_direction_agrees": bool(normal["direction"] != 0 and normal["direction"] == storm["direction"]),
                "source_leaf_id": None, "receiver_leaf_id": None, "geometry": None}
        if normal["stable_relationship"]:
            source, receiver = face["leaf_ids"] if normal["direction"] > 0 else face["leaf_ids"][::-1]
            directional = normal["direction"] * (ordinary["arrays"]["face_forward_m3"][:, position] -
                                                ordinary["arrays"]["face_reverse_m3"][:, position])
            sample = sampled_stage(ordinary, lookup[source], directional)
            geometry = ({"status": "rejected", "reason": "no_significant_saved_directional_interval"}
                        if sample is None else trace_spill_connection(
                            hierarchy, face, source, receiver, source_stage_m=sample["stage_m"]))
            item.update(source_leaf_id=source, receiver_leaf_id=receiver, sampled_source_stage=sample, geometry=geometry)
            item["routing_eligible"] = geometry["status"] == "accepted" and source not in blocked and receiver not in blocked
            if item["routing_eligible"]:
                routed_edges.append({"face_id": face["face_id"], "source_leaf_id": source,
                                     "receiver_leaf_id": receiver, "net_m3": abs(normal["net_m3"])})
        edges.append(item)
    outlets, routed_outlets = [], []
    for position, boundary in enumerate(topology["engineering_boundaries"]):
        actual = ordinary["arrays"]["engineering_boundary_outflow_m3"][:, position]
        other = ordinary_reference["arrays"]["engineering_boundary_outflow_m3"][:, position]
        significant = np.maximum(actual, other) >= MIN_VOLUME_M3
        error = float(np.abs(actual - other).sum() / max(float(other.sum()), MIN_VOLUME_M3))
        interval_error = float(np.max(np.abs(actual[significant] - other[significant]) /
            np.maximum(other[significant], MIN_VOLUME_M3))) if significant.any() else 0.
        sample = sampled_stage(ordinary, lookup[boundary["leaf_id"]], actual)
        reasons = []
        if actual.sum() < MIN_VOLUME_M3 or other.sum() < MIN_VOLUME_M3:
            reasons.append("no_actual_boundary_export")
        if error > RELATIVE_TOLERANCE or interval_error > RELATIVE_TOLERANCE:
            reasons.append("outlet_time_refinement_failed")
        geometry = None if sample is None else trace_engineering_outlet(hierarchy, boundary, source_stage_m=sample["stage_m"])
        if geometry is not None and geometry["status"] != "accepted":
            reasons.append("outlet_geometry_rejected")
        if boundary["leaf_id"] in blocked:
            reasons.append("blocked_basin")
        item = {**boundary, "kind": "engineering_outlet", "outflow_m3": float(actual.sum()),
                "strong_outflow_m3": float(strong["arrays"]["engineering_boundary_outflow_m3"][:, position].sum()),
                "relative_l1_difference": error, "max_interval_relative_difference": interval_error,
                "sampled_source_stage": sample, "geometry": geometry,
                "routing_eligible": not reasons and geometry is not None, "rejection_reasons": reasons}
        outlets.append(item)
        if item["routing_eligible"]:
            routed_outlets.append({"leaf_id": boundary["leaf_id"], "cell_id": boundary["cell_id"], "outflow_m3": item["outflow_m3"]})
    forest = build_outlet_forest(leaves, topology["arrays"]["leaf_area_m2"].tolist(), routed_edges, routed_outlets,
                                blocked_leaf_ids=blocked)
    graph = {"schema": SCHEMA, "algorithm": "saved-ordinary-stable-faces-retained-lakes-v1",
             "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
             "hierarchy_identity_sha256": hierarchy["identity_sha256"], "topology_identity_sha256": topology["identity_sha256"],
             "event_identity_sha256": {"ordinary": ordinary["identity_sha256"], "ordinary_reference": ordinary_reference["identity_sha256"],
                                       "strong": strong["identity_sha256"], "strong_reference": strong_reference["identity_sha256"]},
             "thresholds": {"minimum_volume_m3": MIN_VOLUME_M3, "relative_tolerance": RELATIVE_TOLERANCE,
                            "late_start_fraction": .8}, "nodes": nodes, "edges": edges, "outlets": outlets,
             "routing_forest": forest,
             "semantics": "event-supported basin/lake/spill graph; forests are diagnostic subsets of the original graph; approach polylines are not carved channels",
             "solver_advanced": False, "bed_changed": False, "water_generated": False,
             **{name: False for name in FLAGS}}
    graph["identity_sha256"] = digest(graph)
    return graph


def save_lake_spill_graph(graph, path):
    expected = digest({key: value for key, value in graph.items() if key != "identity_sha256"})
    if graph.get("schema") != SCHEMA or graph.get("identity_sha256") != expected or any(graph.get(name) is not False for name in FLAGS):
        raise ValueError("lake graph identity/flags mismatch")
    payload = json.dumps(graph, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise MemoryError("lake/spill graph exceeds 32MiB")
    publish_bytes(path, payload)
