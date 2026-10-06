"""Source-constrained land-side lake entries; no lake carving or water solve."""

from collections import Counter
import hashlib
import json
import math

import numpy as np


SCHEMA = "td-lake-entry-taper-v1"
MAX_ENTRIES = 256
MAX_VERTICES = 100_000
FLAGS = {"hydraulic_ready": False, "natural_outlet_verified": False,
         "publishable": False, "new_bed_hydrology_verified": False,
         "solver_advanced": False, "lake_bed_changed": False}


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def sample_source(hierarchy, selected_leaves, points_xz):
    arrays = hierarchy["arrays"]
    height = np.asarray(arrays["height_m"], dtype=float)
    spacing = float(hierarchy["metadata"]["spacing_m"])
    origin = np.asarray(hierarchy["metadata"]["origin_m_xz"], dtype=float)
    points = np.asarray(points_xz, dtype=float).reshape(-1, 2)
    if not np.isfinite(points).all() or not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid_source_coordinates")
    grid = (points - origin) / spacing
    if np.any(grid < 0) or np.any(grid[:, 0] > height.shape[1] - 1) or np.any(grid[:, 1] > height.shape[0] - 1):
        raise ValueError("outside_source_coverage")
    first = np.floor(grid).astype(int)
    fraction = grid - first
    output = np.zeros(len(points))
    for delta_x, delta_z in ((0, 0), (1, 0), (0, 1), (1, 1)):
        weight = (fraction[:, 0] if delta_x else 1 - fraction[:, 0]) * (fraction[:, 1] if delta_z else 1 - fraction[:, 1])
        active = weight > 0
        columns = first[active, 0] + delta_x
        rows = first[active, 1] + delta_z
        if not np.asarray(arrays["valid_mask"])[rows, columns].all():
            raise ValueError("unknown_source_coverage")
        if np.asarray(arrays["protected_mask"])[rows, columns].any():
            raise ValueError("protected_source_coverage")
        if not np.isin(np.asarray(arrays["contribution_owner"])[rows, columns], selected_leaves).all():
            raise ValueError("outside_selected_component")
        if np.asarray(arrays["open_boundary_mask"])[rows, columns].any():
            raise ValueError("engineering_boundary_contact")
        values = height[rows, columns]
        if not np.isfinite(values).all():
            raise ValueError("nonfinite_source_height")
        output[active] += weight[active] * values
    return output


def wet_protection(paths):
    return {"covered_native_cell_ids": sorted({cell for lake in paths["lakes"] for cell in lake["covered_cell_ids"]}),
            "stage_by_leaf": [{"leaf_id": lake["leaf_id"], "stage_m": lake["ordinary_stage_max_m"]}
                              for lake in sorted(paths["lakes"], key=lambda lake: lake["leaf_id"])],
            "semantics": "conservative maximum-saved-stage lake protection, not simultaneous water geometry"}


def wet_source_support(hierarchy, protection, points_xz, source_height):
    height = np.asarray(hierarchy["arrays"]["height_m"])
    origin = np.asarray(hierarchy["metadata"]["origin_m_xz"])
    spacing = float(hierarchy["metadata"]["spacing_m"])
    coordinates = np.floor((np.asarray(points_xz) - origin) / spacing + .5).astype(int)
    if np.any(coordinates < 0) or np.any(coordinates[:, 0] >= height.shape[1]) or np.any(coordinates[:, 1] >= height.shape[0]):
        raise ValueError("outside_source_coverage")
    cells = coordinates[:, 1] * height.shape[1] + coordinates[:, 0]
    owners = np.asarray(hierarchy["arrays"]["contribution_owner"])[coordinates[:, 1], coordinates[:, 0]]
    stages = {item["leaf_id"]: item["stage_m"] for item in protection["stage_by_leaf"]}
    lake_stage = np.array([stages.get(int(owner), -math.inf) for owner in owners])
    return np.isin(cells, protection["covered_native_cell_ids"]) | (source_height < lake_stage)


def _one_entry(support, paths, sections, hierarchy, incoming, ports, nodes):
    anchor_id, wet_id = support["node_ids"]
    predecessors = incoming.get(anchor_id, [])
    if len(predecessors) != 1:
        raise ValueError("missing_or_ambiguous_land_predecessor")
    predecessor = predecessors[0]
    upstream_id = predecessor["node_ids"][0]
    upstream_ports = ports.get(upstream_id, [])
    if len(upstream_ports) != 1:
        raise ValueError("missing_or_ambiguous_accepted_port")
    port = upstream_ports[0]
    start = np.asarray(nodes[upstream_id]["xyz_m"], dtype=float)
    end = np.asarray(nodes[anchor_id]["xyz_m"], dtype=float)
    displacement = end[[0, 2]] - start[[0, 2]]
    length = float(np.linalg.norm(displacement))
    spacing = float(hierarchy["metadata"]["spacing_m"])
    if not math.isclose(length, spacing, rel_tol=0, abs_tol=1e-8):
        raise ValueError("not_native_D4_land_segment")
    receiver = np.asarray(hierarchy["arrays"]["receiver"]).ravel()
    for first_id, second_id in ((upstream_id, anchor_id), (anchor_id, wet_id)):
        if int(receiver[nodes[first_id]["cell_id"]]) != nodes[second_id]["cell_id"]:
            raise ValueError("native_receiver_mismatch")
    profile = np.asarray(port["cross_section_xyz_m"][-1], dtype=float)
    if profile.shape != (4, 3) or not np.isfinite(profile).all():
        raise ValueError("invalid_accepted_port")
    longitudinal = displacement / length
    offsets = profile[:, [0, 2]] - start[[0, 2]]
    if np.max(np.abs(offsets @ longitudinal)) > 1e-8:
        raise ValueError("turn_requires_junction_transition")
    if np.linalg.norm(profile[1, [0, 2]] - profile[2, [0, 2]]) <= 0:
        raise ValueError("zero_port_width")
    midpoint = (profile[1] + profile[2]) / 2
    if not np.allclose(midpoint[[0, 2]], start[[0, 2]], atol=1e-8, rtol=0):
        raise ValueError("uncentered_accepted_port")
    expanded = np.insert(profile, 2, midpoint, axis=0)
    offsets = expanded[:, [0, 2]] - start[[0, 2]]
    source_start = sample_source(hierarchy, paths["selected_leaf_ids"], expanded[:, [0, 2]])
    cut_start = source_start - expanded[:, 1]
    if cut_start.min() < -1e-8:
        raise ValueError("port_requires_fill")
    if cut_start.max() > 4:
        raise ValueError("port_cut_exceeds_4m")
    width = float(np.linalg.norm(profile[1, [0, 2]] - profile[2, [0, 2]]))
    step = min(1., width / 4.)
    station_count = math.ceil(length / step) + 1
    if station_count * 5 > MAX_VERTICES:
        raise ValueError("entry_vertex_budget_exceeded")
    fractions = np.linspace(0, 1, station_count)
    centers = start[[0, 2]][None, :] + fractions[:, None] * displacement
    xz = centers[:, None, :] + offsets[None, :, :]
    source = sample_source(hierarchy, paths["selected_leaf_ids"], xz.reshape(-1, 2)).reshape(-1, 5)
    taper = 1 - (3 * fractions ** 2 - 2 * fractions ** 3)
    bed = source - taper[:, None] * np.maximum(cut_start, 0)[None, :]
    bed[0] = expanded[:, 1]
    wet = wet_source_support(hierarchy, wet_protection(paths), xz.reshape(-1, 2), source.ravel()).reshape(-1, 5)
    if np.any(wet & (source - bed > 1e-8)):
        raise ValueError("lake_wet_bed_cut_refused")
    if np.max(np.diff(bed[:, 2])) > 1e-8:
        raise ValueError("insufficient_downhill_grade_for_zero_cut_anchor")
    vertices = np.stack((xz[:, :, 0], bed, xz[:, :, 1]), axis=-1).reshape(-1, 3)
    triangles = []
    for station in range(station_count - 1):
        for lateral in range(4):
            first = station * 5 + lateral
            triangles.extend([[first, first + 1, first + 6], [first, first + 6, first + 5]])
    return {"status": "candidate", "upstream_node_id": upstream_id,
            "anchor_node_id": anchor_id, "wet_node_id": wet_id,
            "land_arc_id": predecessor["arc_id"], "accepted_port_arc_id": port["arc_id"],
            "accepted_port_xyz_m": profile.tolist(), "length_m": length,
            "width_m": width, "station_spacing_m": length / (station_count - 1),
            "station_count": station_count, "vertices_xyz_m": vertices.tolist(),
            "triangles": triangles, "source_vertex_height_m": source.ravel().tolist(),
            "cut_profile_start_m": np.maximum(cut_start, 0).tolist(),
            "maximum_vertex_cut_m": float((source - bed).max()),
            "anchor_source_profile_xyz_m": vertices[-5:].tolist(),
            "port_semantics": "exact existing four-point port with collinear midpoint subdivision",
            "support_semantics": "land predecessor only; lake_entry_support and wet lake bed unchanged",
            "rejection_reasons": []}


def build_lake_entry_tapers(paths, sections, hierarchy):
    if paths["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or sections["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("hierarchy_identity_mismatch")
    if paths["ordinary_identity_sha256"] != sections["ordinary_identity_sha256"]:
        raise ValueError("ordinary_identity_mismatch")
    if sections["composite_parent_identity"]["paths"] != paths["identity_sha256"] or sections["selected_leaf_ids"] != paths["selected_leaf_ids"]:
        raise ValueError("sections_paths_identity_mismatch")
    supports = [arc for arc in paths["arcs"] if arc["kind"] == "lake_entry_support"]
    if len(supports) > MAX_ENTRIES:
        raise ValueError("entry_count_budget_exceeded")
    incoming, ports = {}, {}
    for arc in paths["arcs"]:
        if arc["kind"] == "land_channel":
            incoming.setdefault(arc["node_ids"][-1], []).append(arc)
    for port in sections["edge_sections"]:
        ports.setdefault(port["node_ids"][-1], []).append(port)
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    entries, vertices_used = [], 0
    for support in sorted(supports, key=lambda arc: arc["arc_id"]):
        entry = {"entry_id": support["arc_id"], "leaf_id": support["leaf_id"]}
        try:
            candidate = _one_entry(support, paths, sections, hierarchy, incoming, ports, nodes)
            if vertices_used + len(candidate["vertices_xyz_m"]) > MAX_VERTICES:
                raise ValueError("total_vertex_budget_exceeded")
            entry.update(candidate)
            vertices_used += len(candidate["vertices_xyz_m"])
        except ValueError as error:
            entry.update(status="refused", rejection_reasons=[str(error)],
                         vertices_xyz_m=[], triangles=[])
        entries.append(entry)
    result = {"schema": SCHEMA, "algorithm": "native-source-wet-protected-smoothstep-land-entry-v2",
              "coordinate_system": "model XYZ metres; hierarchy arrays [z,x]",
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "paths_identity_sha256": paths["identity_sha256"],
              "sections_identity_sha256": sections["identity_sha256"],
              "selected_leaf_ids": paths["selected_leaf_ids"], "entries": entries,
              "wet_protection": wet_protection(paths),
              "parameters": {"maximum_cut_m": 4., "maximum_station_spacing_m": 1.,
                             "minimum_width_samples": 4, "maximum_vertices": MAX_VERTICES},
              "summary": {"requested": len(entries),
                          "candidates": sum(entry["status"] == "candidate" for entry in entries),
                          "vertices": vertices_used,
                          "refusals": dict(Counter(reason for entry in entries for reason in entry["rejection_reasons"]))},
              "semantics": "source-sampled geometry candidate; interior triangle cut/fill and overlap must pass raster audit",
              **FLAGS}
    result["identity_sha256"] = digest(result)
    return result
