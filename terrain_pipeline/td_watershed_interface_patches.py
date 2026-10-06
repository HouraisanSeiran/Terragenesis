"""Local parametric patches for watershed junctions, lake anchors, and bends.

This module consumes the saved task06 path/section records.  It never changes
the source bed, rebuilds a forest, or invokes a water solver.  Every accepted
piece remains a candidate mesh with explicit open boundary semantics.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np


SCHEMA = "td-watershed-interface-patches-v1"
MAX_PATCHES = 100_000
MAX_VERTICES = 1_000_000
MAX_TRIANGLES = 2_000_000
MAX_BYTES = 32 * 1024 * 1024
MAX_CUT_M = 4.0
EPS = 1e-9
FALSE_FLAGS = (
    "bed_changed", "bed_rasterized", "water_surface_meshed", "hydraulic_solved",
    "natural_outlet_certified", "flow_regime_certified", "publish_ready",
)


def _plain(value):
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    return value


def _encoded(value):
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _identity_payload(record):
    return {key: value for key, value in record.items() if key != "identity_sha256"}


def _shape_payload(record):
    return [{key: patch[key] for key in (
        "patch_id", "kind", "node_ids", "source_arc_ids", "endpoint_xyz_m",
        "shared_bed_m", "cross_sections", "vertices_xyz_m", "triangles",
        "boundary_edges", "required_cut_m", "status", "rejection_reasons",
    )} for patch in record["patches"]]


def _finite_points(points, name):
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite Nx3")
    return array


def _point_equal(first, second):
    return np.allclose(np.asarray(first, dtype=float), np.asarray(second, dtype=float), atol=1e-8, rtol=0)


def _projected_area(vertices, triangle):
    points = np.asarray(vertices, dtype=float)[list(triangle)]
    first = points[1, [0, 2]] - points[0, [0, 2]]
    second = points[2, [0, 2]] - points[0, [0, 2]]
    return float(first[0] * second[1] - first[1] * second[0])


def _mesh_check(vertices, triangles):
    points = _finite_points(vertices, "patch vertices") if vertices else np.empty((0, 3))
    edge_counts = {}
    signs = []
    for triangle in triangles:
        if len(triangle) != 3 or len(set(triangle)) != 3 or any(type(index) is not int for index in triangle):
            return "degenerate_or_invalid_triangle", 0
        if any(index < 0 or index >= len(points) for index in triangle):
            return "triangle_vertex_out_of_range", 0
        area = _projected_area(points, triangle)
        if abs(area) <= EPS:
            return "degenerate_projected_triangle", 0
        signs.append(area)
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            edge = tuple(sorted((first, second)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            if edge_counts[edge] > 2:
                return "nonmanifold_mesh_edge", max(edge_counts.values())
    if signs and (min(signs) < 0 < max(signs)):
        return "inconsistent_mesh_orientation", max(edge_counts.values(), default=0)
    return None, max(edge_counts.values(), default=0)


def _node_maps(paths, sections):
    nodes = {item["node_id"]: item for item in paths.get("nodes", [])}
    section_map = {item["node_id"]: item for item in sections.get("node_sections", [])}
    if len(nodes) != len(paths.get("nodes", [])) or len(section_map) != len(sections.get("node_sections", [])):
        raise ValueError("duplicate path or section node")
    if set(nodes) - set(section_map):
        raise ValueError("paths contain nodes absent from sections")
    for node_id, node in nodes.items():
        section = section_map[node_id]
        if node["xyz_m"] != section["source_xyz_m"]:
            raise ValueError("section source XYZ differs from shared path node")
        if not math.isfinite(float(section["bed_m"])):
            raise ValueError("nonfinite section bed")
    return nodes, section_map


def _land_incidence(paths):
    incidence = {}
    for arc in paths.get("arcs", []):
        if arc.get("kind") != "land_channel" or len(arc.get("node_ids", [])) != 2:
            continue
        first, second = arc["node_ids"]
        incidence.setdefault(first, []).append(arc)
        incidence.setdefault(second, []).append(arc)
    return incidence


def _patch_base(patch_id, kind, node_ids, arcs, endpoint_xyz, shared_bed, reasons=None):
    return {
        "patch_id": patch_id, "kind": kind, "node_ids": list(node_ids),
        "source_arc_ids": sorted({arc["arc_id"] for arc in arcs}),
        "endpoint_xyz_m": deepcopy(endpoint_xyz), "shared_bed_m": float(shared_bed),
        "cross_sections": [], "vertices_xyz_m": [], "triangles": [], "boundary_edges": [],
        "required_cut_m": 0., "finite_length_m": 0., "status": "rejected",
        "rejection_reasons": sorted(set(reasons or [])), "parametric_only": True,
        "source_bed_unchanged": True, "generation_requested": False,
    }


def _section_at_arc(node_id, arc, section_map):
    positions = [index for index, item in enumerate(arc["node_ids"]) if item == node_id]
    if not positions:
        return None
    index = positions[0]
    section = section_map[node_id]
    cross = section.get("cross_section_xyz_m", [])
    if len(cross) != 4 or any(len(point) != 3 for point in cross):
        return None
    return np.asarray(cross, dtype=float), index


def _make_junction(node_id, arcs, nodes, section_map):
    node = nodes[node_id]
    section = section_map[node_id]
    reasons = []
    if any(set(nodes[item]["kinds"]) & {"lake_covered", "protected", "lake_terminal"} for item in [node_id]):
        reasons.append("protected_or_lake_covered_node")
    if section.get("anchor") or "anchor_cut_conflict" in section.get("rejection_reasons", []):
        reasons.append("lake_anchor_overlap")
    profiles = []
    for arc in arcs:
        result = _section_at_arc(node_id, arc, section_map)
        if result is None:
            reasons.append("missing_shared_cross_section")
        else:
            profiles.append(result[0])
    patch = _patch_base("junction:" + node_id, "junction", [node_id], arcs,
                        [node["xyz_m"]], section["bed_m"], reasons)
    hard_reasons = [reason for reason in reasons if reason != "missing_shared_cross_section"]
    if hard_reasons:
        patch["rejection_reasons"] = sorted(set(hard_reasons))
        return patch
    if len(profiles) < 3:
        patch["rejection_reasons"] = ["junction_requires_three_land_arms"]
        return patch
    center = np.asarray(node["xyz_m"], dtype=float).copy()
    center[1] = float(section["bed_m"])
    width = max(float(section.get("width_m", 0.)), 0.7)
    bank_height = max(float(section.get("depth_m", 0.)), 0.)
    ring = []
    for arc in arcs:
        first, second = arc["node_ids"]
        other_id = second if first == node_id else first
        other = np.asarray(nodes[other_id]["xyz_m"], dtype=float)
        direction = other[[0, 2]] - center[[0, 2]]
        length = float(np.linalg.norm(direction))
        if length <= EPS:
            patch["rejection_reasons"].append("zero_length_junction_arm")
            return patch
        direction /= length
        normal = np.asarray([-direction[1], direction[0]])
        arm_length = min(0.45 * length, max(width, 1.0))
        midpoint = center[[0, 2]] + direction * arm_length
        bank_y = max(float(section["bed_m"]), float(center[1] + bank_height))
        ring.extend([
            [float(midpoint[0] - normal[0] * width / 2.), bank_y,
             float(midpoint[1] - normal[1] * width / 2.)],
            [float(midpoint[0] + normal[0] * width / 2.), bank_y,
             float(midpoint[1] + normal[1] * width / 2.)],
        ])
    order = np.argsort(np.arctan2(
        np.asarray(ring)[:, 2] - center[2], np.asarray(ring)[:, 0] - center[0]))
    ring = [ring[int(index)] for index in order]
    vertices = [center.tolist()] + ring
    triangles = [[0, 1 + index, 1 + ((index + 1) % len(ring))]
                 for index in range(len(ring))]
    if any(_projected_area(vertices, triangle) < 0. for triangle in triangles):
        triangles = [triangle[::-1] for triangle in triangles]
    problem, incidence = _mesh_check(vertices, triangles)
    if problem:
        patch["rejection_reasons"].append(problem)
        return patch
    if any(float(point[1]) < float(section["bed_m"]) - EPS for point in vertices):
        patch["rejection_reasons"].append("junction_below_shared_bed")
        return patch
    patch.update({"cross_sections": [profile.tolist() for profile in profiles],
                  "vertices_xyz_m": vertices, "triangles": triangles,
                  "boundary_edges": [[1 + index, 1 + ((index + 1) % len(ring))]
                                      for index in range(len(ring))],
                  "status": "candidate", "mesh_edge_incidence_max": incidence})
    return patch


def _make_anchor(node_id, arcs, nodes, section_map, max_cut_m):
    node = nodes[node_id]
    section = section_map[node_id]
    patch = _patch_base("anchor:" + node_id, "lake_anchor_transition", [node_id], arcs,
                        [node["xyz_m"]], section["bed_m"])
    if "lake_covered" in node["kinds"] or "protected" in node["kinds"]:
        patch["rejection_reasons"].append("protected_or_lake_covered_node")
    if not arcs:
        patch["rejection_reasons"].append("no_land_channel_anchor_arm")
        return patch
    result = _section_at_arc(node_id, arcs[0], section_map)
    if result is None:
        patch["rejection_reasons"].append("missing_anchor_cross_section")
        return patch
    profile = result[0]
    source_bed = float(node["xyz_m"][1])
    if abs(float(section["bed_m"]) - source_bed) > 1e-8 or float(section.get("depth_m", 0.)) != 0.:
        patch["rejection_reasons"].append("anchor_does_not_return_to_original_bed")
        return patch
    max_cut = max(source_bed - float(point[1]) for point in profile)
    if max_cut > max_cut_m + EPS:
        patch["rejection_reasons"].append("anchor_cut_budget_exceeded")
        return patch
    if any(float(point[1]) < source_bed - max_cut_m - EPS for point in profile):
        patch["rejection_reasons"].append("anchor_source_bed_conflict")
        return patch
    anchor = np.asarray([point[:] for point in profile], dtype=float)
    anchor[:, 1] = source_bed
    first, second = arcs[0]["node_ids"]
    other_id = second if first == node_id else first
    direction = np.asarray(nodes[other_id]["xyz_m"], dtype=float)[[0, 2]] - np.asarray(node["xyz_m"], dtype=float)[[0, 2]]
    length = float(np.linalg.norm(direction))
    if length <= EPS:
        patch["rejection_reasons"].append("zero_length_anchor_arm")
        return patch
    direction /= length
    transition_length = min(length * 0.45, max(float(section.get("width_m", 0.)), 1.0))
    candidate = profile.copy()
    candidate[:, 0] += direction[0] * transition_length
    candidate[:, 2] += direction[1] * transition_length
    vertices = anchor.tolist() + candidate.tolist()
    triangles = []
    for index in range(3):
        triangles.extend(([index, 4 + index, index + 1], [index + 1, 4 + index, 4 + index + 1]))
    problem, incidence = _mesh_check(vertices, triangles)
    if problem:
        patch["rejection_reasons"].append(problem)
        return patch
    patch.update({"cross_sections": [anchor.tolist(), candidate.tolist()], "vertices_xyz_m": vertices,
                  "triangles": triangles, "boundary_edges": [[index, index + 1] for index in range(3)] +
                  [[4 + index, 4 + index + 1] for index in range(3)],
                  "required_cut_m": float(max_cut), "finite_length_m": transition_length,
                  "status": "candidate", "mesh_edge_incidence_max": incidence})
    return patch


def _make_corner(node_id, arcs, nodes, section_map):
    patch = _patch_base("corner:" + node_id, "corner_transition", [node_id], arcs,
                        [nodes[node_id]["xyz_m"]], section_map[node_id]["bed_m"])
    if len(arcs) != 2:
        patch["rejection_reasons"].append("corner_requires_two_land_arms")
        return patch
    profiles = [_section_at_arc(node_id, arc, section_map) for arc in arcs]
    if any(item is None for item in profiles):
        patch["rejection_reasons"].append("missing_corner_cross_section")
        return patch
    first, second = (item[0] for item in profiles)
    center = (first + second) / 2.
    shifted = []
    for arc in arcs:
        start, end = arc["node_ids"]
        other_id = end if start == node_id else start
        direction = np.asarray(nodes[other_id]["xyz_m"], dtype=float)[[0, 2]] - np.asarray(nodes[node_id]["xyz_m"], dtype=float)[[0, 2]]
        length = float(np.linalg.norm(direction))
        if length <= EPS:
            patch["rejection_reasons"].append("zero_length_corner_arm")
            return patch
        direction /= length
        distance = min(length * 0.35, max(float(section_map[node_id].get("width_m", 0.)), 1.0))
        candidate = center.copy()
        candidate[:, 0] += direction[0] * distance
        candidate[:, 2] += direction[1] * distance
        shifted.append(candidate)
    vertices = center.tolist() + shifted[0].tolist() + shifted[1].tolist()
    triangles = []
    for first_offset, second_offset in ((0, 4), (4, 8)):
        for index in range(3):
            triangles.extend(([first_offset + index, second_offset + index, first_offset + index + 1],
                              [first_offset + index + 1, second_offset + index, second_offset + index + 1]))
    for start in (0, 6):
        if _projected_area(vertices, triangles[start]) < 0.:
            for index in range(start, start + 6):
                triangles[index] = triangles[index][::-1]
    problem, incidence = _mesh_check(vertices, triangles)
    if problem:
        patch["rejection_reasons"].append(problem)
        return patch
    patch.update({"cross_sections": [center.tolist(), shifted[0].tolist(), shifted[1].tolist()], "vertices_xyz_m": vertices,
                  "triangles": triangles, "boundary_edges": [[index, index + 1] for index in range(3)] +
                  [[8 + index, 8 + index + 1] for index in range(3)], "status": "candidate",
                  "mesh_edge_incidence_max": incidence})
    return patch


def build_watershed_interface_patches(paths, sections, *, max_cut_m=MAX_CUT_M):
    """Build bounded local candidates from saved task06 records only."""
    if paths.get("schema") != "td-watershed-paths-v1" or sections.get("schema") != "td-watershed-sections-v1":
        raise ValueError("task06 paths/sections records required")
    if type(max_cut_m) not in (int, float) or not math.isfinite(max_cut_m) or max_cut_m <= 0:
        raise ValueError("positive finite max_cut_m required")
    nodes, section_map = _node_maps(paths, sections)
    incidence = _land_incidence(paths)
    patches = []
    for node_id in sorted(incidence):
        node = nodes[node_id]
        section = section_map[node_id]
        kinds = set(node["kinds"])
        if len(incidence[node_id]) >= 3 or section.get("junction") or "needs_junction_patch" in section.get("rejection_reasons", []):
            patches.append(_make_junction(node_id, incidence[node_id], nodes, section_map))
        elif section.get("anchor") or kinds.intersection({"lake_entry", "lake_interface"}):
            patches.append(_make_anchor(node_id, incidence[node_id], nodes, section_map, float(max_cut_m)))
        elif len(incidence[node_id]) == 2:
            patches.append(_make_corner(node_id, incidence[node_id], nodes, section_map))
    if len(patches) > MAX_PATCHES:
        raise MemoryError("interface patch budget exceeded")
    result = {
        "schema": SCHEMA, "algorithm": "saved-watershed-local-interface-patches-v1",
        "coordinate_system": "model_xyz_m_original_bed", "source_identity_sha256": paths["source_identity_sha256"],
        "hierarchy_identity_sha256": paths["hierarchy_identity_sha256"],
        "topology_identity_sha256": paths["topology_identity_sha256"],
        "ordinary_identity_sha256": paths["ordinary_identity_sha256"],
        "composite_parent_identity": {"paths": paths.get("identity_sha256"), "sections": sections.get("identity_sha256")},
        "parameters": {"max_cut_m": float(max_cut_m)}, "patches": patches,
        "shape_identity_sha256": _digest(_shape_payload({"patches": patches})),
        "summary": {"total": len(patches), "candidate": sum(item["status"] == "candidate" for item in patches),
                    "rejected": sum(item["status"] == "rejected" for item in patches),
                    "by_kind": {kind: sum(item["kind"] == kind for item in patches)
                                for kind in ("junction", "lake_anchor_transition", "corner_transition")}},
        "budgets": {"max_patches": MAX_PATCHES, "max_vertices": MAX_VERTICES,
                     "max_triangles": MAX_TRIANGLES, "max_json_bytes": MAX_BYTES},
        "parametric_only": True, "source_bed_unchanged": True, "candidate_semantics":
            "local_geometry_candidate_with_open_boundaries; no bed mutation or hydraulic solve",
        **{name: False for name in FALSE_FLAGS},
    }
    result["identity_sha256"] = _digest(_identity_payload(result))
    validate_watershed_interface_patches(result)
    return result


def validate_watershed_interface_patches(record):
    """Validate finite local geometry, pins, flags, and resource limits."""
    if record.get("schema") != SCHEMA or record.get("algorithm") != "saved-watershed-local-interface-patches-v1":
        raise ValueError("patch schema mismatch")
    if record.get("identity_sha256") != _digest(_identity_payload(record)):
        raise ValueError("patch identity mismatch")
    if record.get("shape_identity_sha256") != _digest(_shape_payload(record)):
        raise ValueError("patch shape identity mismatch")
    if any(record.get(name) is not False for name in FALSE_FLAGS) or record.get("parametric_only") is not True:
        raise ValueError("patch candidate flags must remain false")
    if len(record.get("patches", [])) > MAX_PATCHES:
        raise ValueError("patch count budget exceeded")
    vertices = triangles = 0
    for patch in record["patches"]:
        if patch["status"] not in {"candidate", "rejected"} or patch["parametric_only"] is not True:
            raise ValueError("invalid patch status or semantics")
        points = _finite_points(patch["vertices_xyz_m"], "patch vertices") if patch["vertices_xyz_m"] else np.empty((0, 3))
        vertices += len(points)
        triangles += len(patch["triangles"])
        if patch["status"] == "rejected" and patch["triangles"]:
            raise ValueError("rejected patch contains mesh")
        if patch["status"] == "candidate":
            if not patch["triangles"] or patch["rejection_reasons"]:
                raise ValueError("candidate patch must have a clean mesh")
            problem, incidence = _mesh_check(patch["vertices_xyz_m"], patch["triangles"])
            if problem or incidence > 2:
                raise ValueError("candidate patch mesh invalid")
            if patch.get("mesh_edge_incidence_max") != incidence:
                raise ValueError("patch incidence summary mismatch")
        if float(patch["required_cut_m"]) > float(record["parameters"]["max_cut_m"]) + EPS:
            raise ValueError("patch cut budget exceeded")
        if any(not math.isfinite(float(value)) for value in patch["endpoint_xyz_m"][0]):
            raise ValueError("nonfinite patch endpoint")
    if vertices > MAX_VERTICES or triangles > MAX_TRIANGLES:
        raise ValueError("patch geometry budget exceeded")
    expected = record["summary"]
    if expected["total"] != len(record["patches"]):
        raise ValueError("patch summary total mismatch")
    if expected["candidate"] != sum(item["status"] == "candidate" for item in record["patches"]):
        raise ValueError("patch summary candidate mismatch")
    if expected["rejected"] != sum(item["status"] == "rejected" for item in record["patches"]):
        raise ValueError("patch summary rejected mismatch")
    return record


def save_watershed_interface_patches(record, path):
    validate_watershed_interface_patches(record)
    payload = _encoded(record)
    if len(payload) > MAX_BYTES:
        raise ValueError("patch JSON byte budget exceeded")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def load_watershed_interface_patches(path, *, expected_sha256=None, expected_identity=None):
    target = Path(path)
    if target.stat().st_size > MAX_BYTES:
        raise ValueError("patch JSON byte budget exceeded")
    payload = target.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("patch file hash mismatch")
    record = json.loads(payload)
    validate_watershed_interface_patches(record)
    if expected_identity is not None and record["identity_sha256"] != expected_identity:
        raise ValueError("patch identity mismatch")
    return record


build_interface_patches = build_watershed_interface_patches
validate_interface_patches = validate_watershed_interface_patches
save_interface_patches = save_watershed_interface_patches
load_interface_patches = load_watershed_interface_patches
