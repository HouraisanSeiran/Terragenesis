"""Read-only original-bed diagnostics of saved event-supported spill routes."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


SCHEMA = "td-lake-spill-original-bed-diagnostic-v2"
MAX_CORRIDORS = 4096
MAX_STATIONS = 1_000_000
EPS = 1e-8


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _xyz(value, name):
    array = np.asarray(value, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3 or len(array) < 1 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite XYZ stations")
    return array


def _join(cross_face, downhill, cross_cells, downhill_cells):
    first = _xyz(cross_face, "cross-face")
    second = _xyz(downhill, "downhill")
    if (len(first) != 2 or len(cross_cells) != 2 or len(second) != len(downhill_cells)):
        raise ValueError("invalid_station_cells")
    if cross_cells[-1] != downhill_cells[0]:
        raise ValueError("join_cell_mismatch")
    if not np.array_equal(first[-1], second[0]):
        raise ValueError("join_xyz_mismatch")
    return np.vstack((first, second[1:]))


def _audit_profile(points, sill_m):
    heights = points[:, 1]
    crest = int(np.argmax(heights))
    after = np.diff(heights[crest:])
    reasons = []
    if not math.isfinite(float(sill_m)) or abs(float(max(heights[:2])) - float(sill_m)) > EPS:
        reasons.append("physical_sill_mismatch")
    if np.any(heights[2:] > max(heights[:2]) + EPS):
        reasons.append("crest_not_at_shared_sill")
    if len(after) and np.any(after > EPS):
        reasons.append("downstream_profile_rises")
    return {"crest_station": crest,
            "crest_m": float(heights[crest]),
            "downstream_min_m": float(heights[-1]),
            "downstream_drop_m": float(heights[crest] - heights[-1]),
            "rejection_reasons": reasons,
            "single_crest_downhill": not reasons}


def _corridor(edge):
    geometry = edge.get("geometry") or {}
    if geometry.get("status") != "accepted":
        return {"corridor_id": edge.get("face_id"), "status": "rejected",
                "rejection_reasons": ["spill_geometry_not_accepted"]}
    wet = geometry.get("source_lake_approach", {}).get("xyz_m")
    cross = geometry.get("cross_face", {}).get("xyz_m")
    dry = geometry.get("downhill_terrain_approach", {}).get("xyz_m")
    try:
        cross_cells = geometry["cross_face"]["cell_ids"]
        dry_cells = geometry["downhill_terrain_approach"]["cell_ids"]
        points = _join(cross, dry, cross_cells, dry_cells)
        profile = _audit_profile(points, edge["sill_m"])
        if geometry.get("sill_m") != edge["sill_m"]:
            profile["rejection_reasons"].append("geometry_sill_mismatch")
            profile["single_crest_downhill"] = False
    except (ValueError, KeyError, TypeError) as error:
        return {"corridor_id": edge.get("face_id"), "status": "rejected",
                "rejection_reasons": [str(error)]}
    if not profile["single_crest_downhill"]:
        return {"corridor_id": edge["face_id"], "status": "rejected",
                "source_leaf_id": edge.get("source_leaf_id"),
                "receiver_leaf_id": edge.get("receiver_leaf_id"),
                "profile": profile, "rejection_reasons": profile["rejection_reasons"]}
    return {
        "corridor_id": edge["face_id"],
        "status": "candidate",
        "source_leaf_id": edge["source_leaf_id"],
        "receiver_leaf_id": edge["receiver_leaf_id"],
        "source_lake_approach_xyz_m": wet,
        "spill_cross_face_xyz_m": cross,
        "downstream_support_xyz_m": dry,
        "source_geometry": geometry,
        "sill_m": edge["sill_m"],
        "centerline_cell_ids": cross_cells + dry_cells[1:],
        "centerline_bed_xyz_m": points.tolist(),
        "profile": profile,
        "open_lake_port": True,
        "open_downstream_port": True,
        "source_bed_unchanged": True,
        "channel_verified": False,
        "hydraulic_solved": False,
        "natural_outlet_verified": False,
        "publishable": False,
        "semantics": "saved_original_bed_path_diagnostic_not_new_bed_or_continuous_channel",
    }


def build_lake_spill_corridors(graph, paths=None, *, provenance=None):
    if graph.get("schema") != "td-lake-spill-graph-v1":
        raise ValueError("saved lake spill graph is required")
    domain_edges = [edge for edge in graph.get("edges", []) if edge.get("routing_eligible")]
    selected = None
    if paths is not None:
        if paths.get("graph_identity_sha256") != graph["identity_sha256"]:
            raise ValueError("paths_graph_identity_mismatch")
        selected = sorted({arc["face_id"] for arc in paths.get("arcs", []) if arc.get("face_id")})
        if not set(selected) <= {edge["face_id"] for edge in domain_edges}:
            raise ValueError("paths_face_not_routing_eligible")
    edges = domain_edges if selected is None else [edge for edge in domain_edges if edge["face_id"] in selected]
    if len(edges) > MAX_CORRIDORS:
        raise ValueError("corridor budget exceeded")
    corridors = [_corridor(edge) for edge in edges]
    for edge, corridor in zip(edges, corridors):
        corridor.update(source_leaf_id=edge.get("source_leaf_id"),
                        receiver_leaf_id=edge.get("receiver_leaf_id"),
                        sill_m=edge.get("sill_m"), source_geometry=edge.get("geometry"))
    accepted = sum(item["status"] == "candidate" for item in corridors)
    rejected = len(corridors) - accepted
    result = {
        "schema": SCHEMA,
        "algorithm": "saved-event-spill-original-bed-diagnostic-v2",
        "source_graph_identity_sha256": graph["identity_sha256"],
        "scope": "all_domain" if paths is None else "paths_main_watershed",
        "domain_routing_eligible_count": len(domain_edges),
        "selected_face_ids": [edge["face_id"] for edge in edges],
        "source_paths_identity_sha256": None if paths is None else paths["identity_sha256"],
        "provenance": provenance or {},
        "corridors": corridors,
        "summary": {"requested": len(corridors), "candidate": accepted, "rejected": rejected,
                    "candidate_station_count": sum(len(item.get("centerline_bed_xyz_m", []))
                                                   for item in corridors if item["status"] == "candidate")},
        "status": "candidate" if accepted else "pending",
        "continuous_bed_ready": False,
        "integrated_with_watershed_mesh": False,
        "bed_changed": False,
        "hydraulic_solved": False,
        "natural_outlet_certified": False,
        "publishable": False,
        "solver_calls": 0,
        "limitation": "original-bed diagnostic only; no derived bed, continuous channel or hydraulic certification",
    }
    if result["summary"]["candidate_station_count"] > MAX_STATIONS:
        raise ValueError("station budget exceeded")
    result["identity_sha256"] = _digest(result)
    validate_lake_spill_corridors(result)
    return result


def validate_lake_spill_corridors(result):
    if result.get("schema") != SCHEMA or result.get("status") not in {"pending", "candidate"}:
        raise ValueError("invalid spill corridor package")
    if result.get("continuous_bed_ready") is not False or result.get("integrated_with_watershed_mesh") is not False:
        raise ValueError("spill corridor cannot claim integration")
    for name in ("bed_changed", "hydraulic_solved", "natural_outlet_certified", "publishable"):
        if result.get(name) is not False:
            raise ValueError("spill corridor certification flag must remain false")
    corridors = result.get("corridors", [])
    if (len(corridors) > MAX_CORRIDORS or result.get("solver_calls") != 0 or
            any(item.get("status") not in {"candidate", "rejected"} for item in corridors) or
            result.get("selected_face_ids") != [item.get("corridor_id") for item in corridors] or
            len(set(result["selected_face_ids"])) != len(corridors)):
        raise ValueError("invalid corridor census or budget")
    accepted = sum(item.get("status") == "candidate" for item in corridors)
    summary = {"requested": len(corridors), "candidate": accepted,
               "rejected": len(corridors) - accepted,
               "candidate_station_count": sum(len(item.get("centerline_bed_xyz_m", []))
                                              for item in corridors if item.get("status") == "candidate")}
    if result.get("summary") != summary:
        raise ValueError("spill corridor summary mismatch")
    if summary["candidate_station_count"] > MAX_STATIONS:
        raise ValueError("station budget exceeded")
    for item in corridors:
        if item.get("status") == "candidate":
            points = _xyz(item["centerline_bed_xyz_m"], "candidate centerline")
            if not item.get("open_lake_port") or not item.get("open_downstream_port"):
                raise ValueError("candidate corridor must retain both open ports")
            if item.get("source_bed_unchanged") is not True or item.get("channel_verified") is not False:
                raise ValueError("candidate corridor provenance mismatch")
            if item["profile"]["crest_station"] != int(np.argmax(points[:, 1])):
                raise ValueError("candidate crest mismatch")
            geometry = item["source_geometry"]
            joined = _join(geometry["cross_face"]["xyz_m"], geometry["downhill_terrain_approach"]["xyz_m"],
                           geometry["cross_face"]["cell_ids"], geometry["downhill_terrain_approach"]["cell_ids"])
            if not np.array_equal(points, joined) or item["profile"] != _audit_profile(joined, item["sill_m"]):
                raise ValueError("candidate original-bed profile mismatch")
    unsigned = dict(result)
    identity = unsigned.pop("identity_sha256", None)
    if identity != _digest(unsigned):
        raise ValueError("spill corridor identity mismatch")
    return True


def save_lake_spill_corridors(result, path):
    validate_lake_spill_corridors(result)
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_lake_spill_corridors(path):
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_lake_spill_corridors(result)
    return result
