"""Bounded receiver-chain requests from audited event-specific saddle reception."""

import hashlib
import json

import numpy as np

from terrain_pipeline.td_basin_breach import generate_saddle_breach, saddle_path_face_identity
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_overflow import _face_id, _topology_identity
from terrain_pipeline.td_basin_reception import build_basin_reception, validate_basin_reception


SCHEMA = "td-stable-spill-paths-v1"
MAX_PATH_CELLS = 64
MAX_CANDIDATES = 8
CASE_NAMES = ("normal-24h", "strong-6h")


def _digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _d4(first, second, columns):
    return abs(first // columns - second // columns) + abs(first % columns - second % columns) == 1


def trace_receiver_side(hierarchy, start_cell, basin_id, *, max_path_cells=MAX_PATH_CELLS):
    if type(max_path_cells) is not int or not 3 <= max_path_cells <= MAX_PATH_CELLS:
        raise ValueError("receiver path budget must be 3..64 cells")
    arrays = hierarchy["arrays"]
    height = arrays["height_m"].ravel()
    receiver = arrays["receiver"].ravel()
    owner = arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    columns = arrays["height_m"].shape[1]
    path, reasons, seen = [], [], set()
    cell = int(start_cell)
    complete = False
    while True:
        if not 0 <= cell < height.size:
            reasons.append("receiver_outside_source_domain")
            break
        if cell in seen:
            reasons.append("receiver_cycle")
            break
        if len(path) >= max_path_cells:
            reasons.append("receiver_path_length_exceeds_budget")
            break
        seen.add(cell)
        path.append(cell)
        if not valid[cell] or not np.isfinite(height[cell]):
            reasons.append("unknown_receiver_path_cell")
            break
        if protected[cell]:
            reasons.append("protected_receiver_path_cell")
        if owner[cell] != basin_id:
            reasons.append("receiver_leaves_face_basin")
            break
        downstream = int(receiver[cell])
        if downstream == -1:
            complete = True
            break
        if not 0 <= downstream < height.size:
            reasons.append("receiver_outside_source_domain")
            break
        if not _d4(cell, downstream, columns):
            reasons.append("receiver_not_d4_adjacent")
            break
        if height[downstream] > height[cell]:
            reasons.append("receiver_climbs_original_bed")
            break
        cell = downstream
    return {"basin_id": int(basin_id), "start_cell_id": int(start_cell),
            "cell_ids": path, "terminal_cell_id": path[-1] if complete else None,
            "complete": complete, "length_m": max(0, len(path) - 1) * hierarchy["metadata"]["spacing_m"],
            "rejection_reasons": sorted(set(reasons))}


def _face_geometry(face, topology_face, hierarchy):
    arrays = hierarchy["arrays"]
    index = face["hierarchy_face_index"]
    cells = face["cell_ids"]
    if (cells != topology_face["cell_ids"] or index != topology_face["face_index"] or
            cells != arrays["face_cells"][index].tolist() or face["face_id"] != _face_id(hierarchy, index)):
        raise ValueError("reception source face identity/cell mismatch")
    owners = arrays["contribution_owner"].ravel()[cells].tolist()
    if owners != face["cell_owner_leaf_ids"] or sorted(owners) != face["leaf_ids"]:
        raise ValueError("reception cell/leaf orientation mismatch")
    height = arrays["height_m"].ravel()
    columns = arrays["height_m"].shape[1]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    endpoints = [[origin[0] + (cell % columns) * spacing, float(height[cell]),
                  origin[1] + (cell // columns) * spacing] for cell in cells]
    if (not _d4(*cells, columns) or endpoints != face["endpoints_xyz_m"] or
            float(max(height[cells])) != face["sill_m"]):
        raise ValueError("reception face XYZ/sill/D4 differs from source bed")


def build_stable_spill_paths(hierarchy, topology, cases, *, max_path_cells=MAX_PATH_CELLS):
    """Reverse only the source-side static chain, then cross the actual saddle face."""
    validate_basin_hierarchy(hierarchy)
    if type(max_path_cells) is not int or not 3 <= max_path_cells <= MAX_PATH_CELLS:
        raise ValueError("path work budget must be 3..64 cells")
    if (topology["identity_sha256"] != _topology_identity(topology) or
            topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]):
        raise ValueError("topology/hierarchy identity mismatch")
    lookup = {case["name"]: case for case in cases}
    if len(lookup) != len(cases) or set(lookup) != set(CASE_NAMES):
        raise ValueError("ordinary and strong audited cases required exactly once")
    face_lookup = {}
    for name in CASE_NAMES:
        case = lookup[name]
        reception = case["reception"]
        validate_basin_reception(reception, expected_identity=reception["identity_sha256"])
        restored = build_basin_reception(topology, case["selected_event"], case["reference_event"], hierarchy)
        if restored["identity_sha256"] != reception["identity_sha256"]:
            raise ValueError("reception differs from actual saved event/refinement")
        face_lookup[name] = {face["face_id"]: face for face in reception["faces"]}
        if len(face_lookup[name]) != len(topology["faces"]):
            raise ValueError("reception face coverage/duplicate mismatch")
    records = []
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    height = arrays["height_m"].ravel()
    for topology_face in topology["faces"]:
        face_id = topology_face["face_id"]
        evidence = {name: face_lookup[name][face_id] for name in CASE_NAMES}
        for face in evidence.values():
            _face_geometry(face, topology_face, hierarchy)
        ordinary, strong = (evidence[name] for name in CASE_NAMES)
        reasons = []
        for name, face in evidence.items():
            if not face["stable_relationship"]:
                reasons.append(name + ":not_stable_reception")
        directions = {(face["source_leaf_id"], face["receiver_leaf_id"])
                      for face in evidence.values() if face["stable_relationship"]}
        if len(directions) > 1:
            reasons.append("ordinary_strong_direction_conflict")
        record = {"face_id": face_id, "hierarchy_face_index": ordinary["hierarchy_face_index"],
                  "face_cell_ids": ordinary["cell_ids"], "face_leaf_ids": ordinary["leaf_ids"],
                  "source_identity_sha256": metadata["source_identity_sha256"],
                  "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                  "topology_identity_sha256": topology["identity_sha256"],
                  "sill_m": ordinary["sill_m"], "event_evidence": evidence,
                  "side_paths": [], "path_cell_ids": [], "bounded_candidate_requests": []}
        if directions:
            source_basin, destination_basin = next(iter(sorted(directions)))
            face_cells = ordinary["cell_ids"]
            owners = ordinary["cell_owner_leaf_ids"]
            source_cell = face_cells[owners.index(source_basin)]
            destination_cell = face_cells[owners.index(destination_basin)]
            source_side = trace_receiver_side(hierarchy, source_cell, source_basin, max_path_cells=max_path_cells)
            destination_side = trace_receiver_side(hierarchy, destination_cell, destination_basin, max_path_cells=max_path_cells)
            record.update(source_basin_id=source_basin, destination_basin_id=destination_basin,
                          directed_face_cell_ids=[source_cell, destination_cell],
                          side_paths=[source_side, destination_side])
            for side_name, side in [("source", source_side), ("destination", destination_side)]:
                reasons.extend(side_name + ":" + reason for reason in side["rejection_reasons"])
            path = list(reversed(source_side["cell_ids"])) + destination_side["cell_ids"]
            record["path_cell_ids"] = path
            record["path_length_m"] = (len(path) - 1) * metadata["spacing_m"]
            if not source_side["complete"] or not destination_side["complete"]:
                reasons.append("incomplete_receiver_chain")
            if not 3 <= len(path) <= max_path_cells:
                reasons.append("saddle_path_length_outside_budget")
            if len(set(path)) != len(path):
                reasons.append("saddle_path_repeats_cell")
            if path and not height[path[-1]] < height[path[0]]:
                reasons.append("downstream_anchor_not_lower_than_source_anchor")
            if source_basin == destination_basin:
                reasons.append("downstream_anchor_returns_to_source_basin")
            if not reasons:
                target = np.linspace(height[path[0]], height[path[-1]], len(path))
                if np.any(target > height[path]):
                    reasons.append("target_requires_unsourced_fill")
                if np.any((target[:-1] - target[1:]) / metadata["spacing_m"] < 1e-6):
                    reasons.append("target_slope_below_minimum")
                if not np.any(height[path[1:-1]] > target[1:-1]):
                    reasons.append("no_saddle_cut_requested")
                record["target_bed_m"] = target.tolist()
            if not reasons:
                path_identity = saddle_path_face_identity(arrays["height_m"], path,
                    source_identity_sha256=metadata["source_identity_sha256"],
                    topology_identity_sha256=topology["identity_sha256"])
                record["path_face_identity"] = path_identity
                for name in CASE_NAMES:
                    event = lookup[name]["selected_event"]
                    face = evidence[name]
                    field = "face_forward_m3" if source_basin == face["leaf_ids"][0] else "face_reverse_m3"
                    outward = event["arrays"][field][:, face["face_index"]]
                    volume = float(outward.sum())
                    steps = int(np.count_nonzero(outward > 0))
                    duration = steps * event["metadata"]["timestep_s"]
                    hydro = {"hydro_identity_sha256": event["identity_sha256"],
                             "face_cell_ids": [source_cell, destination_cell],
                             "outward_volume_m3": volume, "positive_outflow_steps": steps,
                             "dt_s": event["metadata"]["timestep_s"]}
                    anchor = {"topology_identity_sha256": topology["identity_sha256"],
                              "source_basin_id": source_basin, "destination_basin_id": destination_basin,
                              "tail_cell_ids": [path[-1]], "engineering_open_boundary": False}
                    request = {"case": name, "face_id": face_id, "path_cell_ids": path,
                               "target_bed_m": record["target_bed_m"], "path_face_identity": path_identity,
                               "source_identity_sha256": metadata["source_identity_sha256"],
                               "topology_identity_sha256": topology["identity_sha256"],
                               "hydro_identity_sha256": event["identity_sha256"],
                               "routed_volume_m3": volume, "wet_duration_s": duration,
                               "hydro_face_evidence": hydro, "downstream_anchor_evidence": anchor,
                               "exposure_policy": "actual outward saddle-face volume assigned to path; not per-cell hydraulic flux"}
                    request["identity_sha256"] = _digest(request)
                    record["bounded_candidate_requests"].append(request)
        record["rejection_reasons"] = sorted(set(reasons))
        record["status"] = "rejected" if reasons else "bounded_candidate_request"
        record["identity_sha256"] = _digest(record)
        records.append(record)
    result = {"schema": SCHEMA, "algorithm": "actual-d4-face-two-static-receiver-chains-v1",
              "source_identity_sha256": metadata["source_identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "topology_identity_sha256": topology["identity_sha256"],
              "event_identity_sha256": {name: lookup[name]["selected_event"]["identity_sha256"] for name in CASE_NAMES},
              "reception_identity_sha256": {name: lookup[name]["reception"]["identity_sha256"] for name in CASE_NAMES},
              "max_path_cells": max_path_cells, "max_independent_candidates": MAX_CANDIDATES,
              "paths": records, "baseline": {"unchanged": True, "source_identity_sha256": metadata["source_identity_sha256"]},
              "semantics": "static receiver geometry plus two audited event-dependent reception records; no permanent trunk or solved channel",
              "solver_advanced": False, "geometry_generated": False,
              "hydraulic_ready": False, "publishable": False, "natural_outlet_verified": False,
              "continuous_fine_corridor_ready": False}
    result["identity_sha256"] = _digest(result)
    return result


def generate_bounded_candidates(report, hierarchy, materials, *, max_candidates=MAX_CANDIDATES):
    """Generate independent alternatives on the unchanged baseline, never chain cuts."""
    if type(max_candidates) is not int or not 0 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError("independent candidate budget must be 0..8")
    if report["identity_sha256"] != _digest({key: value for key, value in report.items() if key != "identity_sha256"}):
        raise ValueError("spill request report identity mismatch")
    validate_basin_hierarchy(hierarchy)
    if (report["schema"] != SCHEMA or report["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            report["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("candidate baseline hierarchy identity mismatch")
    if (tuple(materials["metadata"]["shape"]) != hierarchy["arrays"]["height_m"].shape or
            materials["metadata"]["origin_m_xz"] != hierarchy["metadata"]["origin_m_xz"] or
            materials["metadata"]["spacing_m"] != hierarchy["metadata"]["spacing_m"]):
        raise ValueError("candidate material grid differs from source")
    if not np.array_equal(materials["arrays"]["protected_mask"], hierarchy["arrays"]["protected_mask"]):
        raise ValueError("candidate material protection differs from source")
    attempts, candidates = [], []
    calls = 0
    for path in report["paths"]:
        for request in path["bounded_candidate_requests"]:
            if (request["identity_sha256"] != _digest({key: value for key, value in request.items() if key != "identity_sha256"}) or
                    request["source_identity_sha256"] != report["source_identity_sha256"] or
                    request["topology_identity_sha256"] != report["topology_identity_sha256"] or
                    request["hydro_identity_sha256"] != report["event_identity_sha256"][request["case"]]):
                raise ValueError("candidate request evidence identity mismatch")
            attempt = {"request_identity_sha256": request["identity_sha256"], "face_id": path["face_id"], "case": request["case"]}
            if calls >= max_candidates:
                attempt.update(status="not_attempted", rejection_reasons=["independent_candidate_budget_exhausted"])
            else:
                fields = {key: request[key] for key in ("path_cell_ids", "target_bed_m", "path_face_identity",
                          "source_identity_sha256", "topology_identity_sha256", "hydro_identity_sha256",
                          "routed_volume_m3", "wet_duration_s", "hydro_face_evidence", "downstream_anchor_evidence")}
                for key in ("routed_volume_m3", "wet_duration_s"):
                    fields[key] = np.full(len(request["path_cell_ids"]), request[key])
                try:
                    calls += 1
                    bundle = generate_saddle_breach(hierarchy["arrays"]["height_m"], hierarchy["arrays"]["valid_mask"],
                        spacing_m=hierarchy["metadata"]["spacing_m"], materials=materials, **fields,
                        parameters={"max_path_cells": report["max_path_cells"]})
                    candidate_index = len(candidates)
                    candidates.append(bundle)
                    attempt.update(status=bundle["metadata"]["status"],
                                   candidate_index=candidate_index, identity_sha256=bundle["identity_sha256"],
                                   rejection_reasons=bundle["metadata"]["rejection_reasons"])
                except ValueError as error:
                    attempt.update(status="failed", rejection_reasons=["breach_contract_rejected"], error=str(error))
            attempts.append(attempt)
    return {"attempts": attempts, "candidates": candidates, "generation_calls": calls, "baseline_unchanged": True,
            "hydraulic_ready": False, "publishable": False}
