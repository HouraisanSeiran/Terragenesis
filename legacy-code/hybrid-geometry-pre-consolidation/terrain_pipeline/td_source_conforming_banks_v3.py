"""Versioned legacy-boundary matching with isolated, read-only v2 geometry reuse."""

from collections import Counter, defaultdict
from copy import deepcopy
import gc
import json
import math
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline import td_source_conforming_banks as v2

SCHEMA = "td-source-conforming-banks-v3"
ALGORITHM = "native-bilinear-minus-legacy-matched-shared-knot-affine-depth-fan-v3"
FLAGS = v2.FLAGS
MAX_BYTES, MAX_CELLS, MAX_RSS = v2.MAX_BYTES, v2.MAX_CELLS, v2.MAX_RSS
POLICY = {
    "algorithm": ALGORITHM,
    "legacy_depth": "native_segment_source_minus_unchanged_legacy_line_whole_coefficients",
    "legacy_quadratic": "refuse_nonzero_source_quadratic_no_joint_neighbor_version",
    "incident_knots": "legacy_constraint_propagates_to_all_incident_edges_before_fan_build",
    "interior_depth": "original_shared_T_vertex_interpolation_unless_legacy_constrained",
    "uncovered_nonzero": "classify_from_original_sections_paths_but_refuse_without_bound_BC",
    "nonnegative": "strict_no_clamp",
    "gates": "unchanged_v2_maxcut_wet_source_coverage_atomic_signed_material",
}
POLICY_IDENTITY_SHA256 = v2._record_identity(POLICY)
evaluate_bank_function = v2.evaluate_bank_function


def _seal(record):
    record.pop("identity_sha256", None)
    record["policy_identity_sha256"] = POLICY_IDENTITY_SHA256
    return v2._seal(record)


def _bucket(point):
    return tuple(int(np.floor(value / v2.GEOMETRY_TOLERANCE_M)) for value in point)


def _constraint(context, point):
    registry = context.setdefault("v3_legacy_knots", {})
    bucket = _bucket(point)
    found = []
    for horizontal in (-1, 0, 1):
        for vertical in (-1, 0, 1):
            for record in registry.get((bucket[0] + horizontal, bucket[1] + vertical), []):
                if max(abs(first - second) for first, second in zip(point, record["xz_m"])) <= v2.GEOMETRY_TOLERANCE_M:
                    found.append(record)
    return found


def _register_legacy_knots(segment, context):
    start, end = np.asarray(segment["start_xz_m"]), np.asarray(segment["end_xz_m"])
    legacy = [side for side in segment["sides"] if side["triangle_id"].startswith("legacy06:")]
    if not legacy:
        return
    for side in legacy:
        for point in (start, end):
            sample = v2._source_sample(context, *map(float, point))
            if sample["height_m"] is None:
                continue
            depth = sample["height_m"] - v2._edge_y(side, point)
            existing = _constraint(context, point)
            if existing:
                if abs(existing[0]["cut_depth_m"] - depth) > v2.FUNCTION_TOLERANCE_M:
                    existing[0]["conflicting_legacy_depth"] = True
                continue
            record = {"xz_m": point.tolist(), "cut_depth_m": float(depth),
                      "legacy_triangle_id": side["triangle_id"],
                      "legacy_edge_index": side["edge_index"],
                      "legacy_segment_id": segment["segment_id"],
                      "conflicting_legacy_depth": False}
            context["v3_legacy_knots"].setdefault(_bucket(point), []).append(record)


def _boundary_evidence(sections, paths):
    incoming = defaultdict(list)
    arcs = {arc["arc_id"]: arc for arc in paths.get("arcs", [])}
    nodes = {node["node_id"]: node for node in sections.get("node_sections", [])}
    for arc in arcs.values():
        for first, second in zip(arc["node_ids"], arc["node_ids"][1:]):
            incoming[second].append({"arc_id": arc["arc_id"], "from_node_id": first})
    evidence = {}
    mesh = sections["mesh"]
    for section_index, section in enumerate(sections["edge_sections"]):
        profiles = section.get("cross_section_xyz_m", [])
        if not profiles or not section.get("node_ids"):
            continue
        node_id = section["node_ids"][0]
        arc = arcs.get(section["arc_id"])
        node = nodes.get(node_id)
        bound = (arc is not None and arc["node_ids"][:2] == section["node_ids"][:2]
                 and node is not None and node.get("cross_section_xyz_m") == profiles[0]
                 and not node.get("rejection_reasons", [])
                 and np.isfinite(node.get("representative_q_m3_s", np.nan))
                 and node.get("representative_q_m3_s", 0.) > 0.)
        for triangle_index in section["triangle_indices"]:
            indices = mesh["triangles"][triangle_index]
            for edge_index in range(3):
                points = [mesh["vertices_xyz_m"][indices[edge_index]],
                          mesh["vertices_xyz_m"][indices[(edge_index + 1) % 3]]]
                if not any(points == [first, second] or points == [second, first]
                           for first, second in zip(profiles[0], profiles[0][1:])):
                    continue
                evidence["06:" + str(triangle_index) + ":" + str(edge_index)] = {
                    "classification": "upstream_profile_without_bound_BC" if bound and not incoming[node_id]
                                      else "truncated_bank",
                    "sections_identity_sha256": sections["identity_sha256"],
                    "paths_identity_sha256": paths["identity_sha256"],
                    "section_index": section_index, "arc_id": section["arc_id"],
                    "node_id": node_id, "profile_index": 0,
                    "original_edge_xyz_m": points, "original_profile_xyz_m": profiles[0],
                    "ordinary_identity_sha256": sections.get("ordinary_identity_sha256"),
                    "representative_q_m3_s": None if node is None else node.get("representative_q_m3_s"),
                    "incoming_path_steps": incoming[node_id], "section_path_profile_bound": bool(bound),
                    "boundary_condition_bound": False, "hydraulic_inflow_claimed": False}
    return evidence


def _proof(segment, context):
    original = v2._proof(segment, context)
    reasons = set(original["rejection_reasons"])
    reasons.difference_update({"unchanged_neighbor_quadratic_function_mismatch",
                               "uncovered_boundary_has_nonzero_depth", "boundary_knot_fill_or_unknown",
                               "shared_depth_knot_mismatch"})
    parameters = context["v3_parameters"]
    source = original["source"]
    points = [np.asarray(segment[name]) for name in ("start_xz_m", "end_xz_m")]
    legacy = [side for side in segment["sides"] if side["triangle_id"].startswith("legacy06:")]
    neighbors, differences = [], []
    depths = list(original["side_depth_knots"][0]["depth_knots_m"])
    constraints = []
    for endpoint, point in enumerate(points):
        records = _constraint(context, point)
        constraint = records[0] if records else None
        constraints.append(None if constraint is None else dict(constraint))
        if constraint is not None:
            depths[endpoint] = constraint["cut_depth_m"]
            if constraint["conflicting_legacy_depth"] or any(
                    abs(record["cut_depth_m"] - depths[endpoint]) > v2.FUNCTION_TOLERANCE_M for record in records):
                reasons.add("incident_legacy_knot_depth_conflict")
    coefficients = None
    if source is not None and legacy:
        native = source["source_coefficients_m_t012"]
        if abs(native[2]) > v2.FUNCTION_TOLERANCE_M:
            reasons.add("legacy_source_quadratic_requires_joint_version")
        for side in legacy:
            bed_start, bed_end = [v2._edge_y(side, point) for point in points]
            bed = [bed_start, bed_end - bed_start, 0.]
            neighbors.append({"triangle_id": side["triangle_id"], "edge_index": side["edge_index"],
                              "bed_coefficients_m_t012": bed})
        bed = neighbors[0]["bed_coefficients_m_t012"]
        matching_depths = [sample["height_m"] - v2._edge_y(legacy[0], point)
                           if sample["height_m"] is not None else None
                           for sample, point in zip(original["source_samples"], points)]
        coefficients = None if any(depth is None for depth in matching_depths) else [
            matching_depths[0], matching_depths[1] - matching_depths[0]]
        if any(depth is not None and depth < 0 for depth in matching_depths):
            reasons.add("legacy_matching_negative_depth")
        if any(depth is None or value is None or abs(depth - value) > v2.FUNCTION_TOLERANCE_M
               for depth, value in zip(depths, matching_depths)):
            reasons.add("incident_legacy_knot_depth_conflict")
        for neighbor in neighbors:
            if coefficients is None:
                continue
            difference = [native[0] - coefficients[0] - neighbor["bed_coefficients_m_t012"][0],
                          native[1] - coefficients[1] - neighbor["bed_coefficients_m_t012"][1], native[2]]
            differences.append({"triangle_id": neighbor["triangle_id"], "edge_index": neighbor["edge_index"],
                                "difference_coefficients_m_t012": difference})
            if max(abs(value) for value in difference) > v2.FUNCTION_TOLERANCE_M:
                reasons.add("legacy_whole_coefficient_mismatch")
        depths = matching_depths
    elif all(depth is not None for depth in depths):
        coefficients = [depths[0], depths[1] - depths[0]]
    if any(depth is None or not np.isfinite(depth) or depth < 0 for depth in depths):
        reasons.add("boundary_knot_fill_or_unknown")
    if any(depth is not None and depth > parameters["max_cut_m"] + parameters["conflict_tolerance_m"] for depth in depths):
        reasons.add("boundary_knot_cut_depth_exceeded")
    for sample, depth in zip(original["source_samples"], depths):
        if depth is not None and depth > parameters["conflict_tolerance_m"] and sample["wet_source_support"]:
            reasons.add("lake_wet_boundary_knot_cut_refused")
    zero_boundary = original["boundary_condition"] == "explicit_source_bank_zero_depth_v2"
    if zero_boundary and any(depth is not None and abs(depth) > v2.FUNCTION_TOLERANCE_M for depth in depths):
        reasons.add("source_bank_zero_depth_incident_conflict")
    boundary_evidence = None
    if len([side for side in segment["sides"] if not side["triangle_id"].startswith("legacy06:")]) > 2:
        reasons.add("nonmanifold_shared_segment")
    if len(segment["sides"]) == 1:
        side = segment["sides"][0]
        boundary_evidence = context.get("v3_boundary_evidence", {}).get(
            side["triangle_id"] + ":" + str(side["edge_index"]), {
                "classification": "truncated_bank", "boundary_condition_bound": False,
                "hydraulic_inflow_claimed": False})
        if any(depth is not None and depth > v2.FUNCTION_TOLERANCE_M for depth in depths):
            reasons.add("uncovered_boundary_has_nonzero_depth")
    original["side_depth_knots"] = [{**side, "depth_knots_m": depths}
                                    for side in original["side_depth_knots"]]
    original["depth_coefficients_m_t01"] = None if reasons else coefficients
    original["common_function_identity_sha256"] = None if reasons else v2._digest({
        "start_xz_m": points[0].tolist(), "end_xz_m": points[1].tolist(), "source": source,
        "depth_coefficients_m_t01": coefficients, "policy_identity_sha256": POLICY_IDENTITY_SHA256})
    original["boundary_condition"] = ("explicit_source_bank_zero_depth_v3" if zero_boundary else
                                      "unchanged_legacy_whole_linear_match_v3" if legacy else
                                      "unbound_uncovered_boundary_v3" if len(segment["sides"]) == 1 else
                                      "shared_incident_native_knot_depth_v3")
    original["boundary_evidence"] = boundary_evidence
    original["v3proof"] = {"policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "depth_rule": "native_source_minus_legacy_line_v3" if legacy else "shared_incident_native_knot_depth_v3",
        "unchanged_neighbor_polynomials": neighbors, "whole_coefficient_differences_m_t012": differences,
        "knot_constraints": constraints, "proposed_depth_coefficients_m_t01": coefficients}
    original["proof_method"] = "whole_native_source_coefficients_and_incident_shared_affine_depth_v3"
    original["status"] = "refused" if reasons else "candidate"
    original["rejection_reasons"] = sorted(reasons)
    return _seal(original)


def build_edge_proofs(segments, context, parameters):
    """Prebind all legacy constraints before proving any incident edge."""
    context["v3_parameters"] = parameters
    context["v3_legacy_knots"] = {}
    for segment in segments:
        _register_legacy_knots(segment, context)
    return [_proof(segment, context) for segment in segments]


def build_triangle_function(triangle, edge_proofs, context, parameters):
    function = v2._function(triangle, edge_proofs, context, parameters)
    vertices = {}
    reasons = set(function["rejection_reasons"])
    for fan in function["fans"]:
        for point, depth in zip(fan["vertices_xz_m"], fan["depth_at_vertices_m"]):
            bucket = _bucket(point)
            for horizontal in (-1, 0, 1):
                for vertical in (-1, 0, 1):
                    for prior_point, prior_depth in vertices.get((bucket[0] + horizontal, bucket[1] + vertical), []):
                        if max(abs(first - second) for first, second in zip(point, prior_point)) <= v2.GEOMETRY_TOLERANCE_M:
                            if abs(depth - prior_depth) > v2.FUNCTION_TOLERANCE_M:
                                reasons.add("incident_fan_vertex_depth_discontinuity")
            vertices.setdefault(bucket, []).append((point, depth))
    function["status"] = "refused" if reasons else "candidate"
    function["rejection_reasons"] = sorted(reasons)
    function["incident_fan_vertex_depth_verified"] = not reasons
    return _seal(function)


def _chunks(kind, records, max_bytes, parent_identity):
    chunks, current, size = [], [], 1024
    for record in records:
        record["policy_identity_sha256"] = POLICY_IDENTITY_SHA256
        record_size = v2._record_bytes(record) + 1
        if record_size + 1024 > max_bytes:
            raise MemoryError("single v3 record exceeds bounded byte budget")
        if current and size + record_size > max_bytes:
            chunks.append(_seal({"schema": SCHEMA + "-" + kind,
                "parent_identity_sha256": parent_identity,
                "chunk_id": kind + "-" + str(len(chunks)).zfill(4), "records": current}))
            current, size = [], 1024
        current.append(record)
        size += record_size
    if current:
        chunks.append(_seal({"schema": SCHEMA + "-" + kind,
            "parent_identity_sha256": parent_identity,
            "chunk_id": kind + "-" + str(len(chunks)).zfill(4), "records": current}))
    if len(chunks) > v2.MAX_FILES:
        raise MemoryError("v3 chunk count budget exceeded")
    return chunks


def build_source_conforming_banks(base, shard_package, hierarchy, sections, transitions, paths, readiness, *,
                                  input_pins=None, max_cells=MAX_CELLS, max_shard_bytes=MAX_BYTES,
                                  resource_check=None):
    """Build a separate v3 candidate; original parent triangles and centers stay immutable."""
    if (type(max_cells) is not int or not 1 <= max_cells <= MAX_CELLS
            or type(max_shard_bytes) is not int or not 4096 <= max_shard_bytes <= MAX_BYTES):
        raise ValueError("invalid source-conforming resource budget")
    v2._rss_guard(resource_check, phase="parent_linkage")
    for name, record in (("hierarchy", hierarchy), ("sections", sections), ("transitions", transitions)):
        if base[name + "_identity_sha256"] != record["identity_sha256"]:
            raise ValueError("immutable " + name + " linkage mismatch")
    if (paths["identity_sha256"] != transitions["paths_identity_sha256"]
            or shard_package["manifest"]["base_identity_sha256"] != base["identity_sha256"]
            or base["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("immutable source/paths/shards linkage mismatch")
    parent_identity = shard_package["manifest"]["identity_sha256"]
    context = v2._context(hierarchy, base["selected_leaf_ids"], base["wet_protection"])
    evidence = _boundary_evidence(sections, paths)
    context["v3_parameters"] = base["parameters"]
    context["v3_boundary_evidence"] = evidence
    cells = {key: (cell, owner) for key, cell, owner in v2.iter_merged_cells(base, shard_package["shards"])}
    if len(cells) > max_cells:
        raise MemoryError("merged parent exceeds unique-cell budget")
    v2._rss_guard(resource_check, phase="readonly_parent_cells", counters={"cells": len(cells)})
    triangles = {item["triangle_id"]: item for item in base["triangles"]}
    triangles.update({item["triangle_id"]: item for item in shard_package["raw"]["triangles"]})
    if len(triangles) != len(base["triangles"]):
        raise ValueError("parent triangle indices are duplicated or shard raw introduced new triangles")
    for triangle in triangles.values():
        mesh = sections["mesh"] if triangle["source_package"] == "06" else transitions["entries"][triangle["source_entry_index"]]
        original_indices = mesh["triangles"][triangle["source_triangle_index"]]
        if (original_indices != triangle["source_vertex_indices"]
                or [mesh["vertices_xyz_m"][index] for index in original_indices] != triangle["vertices_xyz_m"]):
            raise ValueError("original triangle indices/source XYZ chain mismatch")
    seeds = {proposal["triangle_id"] for cell, owner in cells.values()
             if "fill_without_material" in cell["rejection_reasons"] for proposal in cell["triangle_sources"]}
    if not seeds.issubset(triangles):
        raise ValueError("saved fill proposals missing original provenance")
    groups = defaultdict(list)
    bank_points = {tuple(point) for edge in sections["edge_sections"]
                   for profile in edge.get("cross_section_xyz_m", []) for point in (profile[0], profile[-1])}
    for triangle in triangles.values():
        for edge_index in range(3):
            edge = v2._edge_record(triangle, edge_index)
            if triangle["source_package"] == "06":
                edge["zero_depth_boundary_eligible"] = all(tuple(point) in bank_points for point in edge["points_xyz_m"])
            else:
                entry = transitions["entries"][triangle["source_entry_index"]]
                first_index = triangle["source_vertex_indices"][edge_index]
                second_index = triangle["source_vertex_indices"][(edge_index + 1) % 3]
                edge["zero_depth_boundary_eligible"] = (
                    first_index % 5 == second_index % 5 and first_index % 5 in (0, 4)
                    or min(first_index, second_index) >= len(entry["vertices_xyz_m"]) - 5)
            groups[v2._line_key(np.asarray(edge["points_xyz_m"])[:, [0, 2]])].append(edge)
    original_mesh = sections["mesh"]
    for index, indices in enumerate(original_mesh["triangles"]):
        if "06:" + str(index) in triangles:
            continue
        legacy = {"triangle_id": "legacy06:" + str(index),
                  "vertices_xyz_m": [original_mesh["vertices_xyz_m"][vertex] for vertex in indices]}
        for edge_index in range(3):
            edge = v2._edge_record(legacy, edge_index)
            key = v2._line_key(np.asarray(edge["points_xyz_m"])[:, [0, 2]])
            if key in groups:
                groups[key].append(edge)
    v2._rss_guard(resource_check, phase="edge_groups", counters={"groups": len(groups)})
    member_sets = v2._components(triangles, v2._iter_segments(groups, context), seeds)
    component_by_triangle = {identifier: component for component, members in member_sets.items() for identifier in members}
    reasons_by_component = defaultdict(set)
    v2._rss_guard(resource_check, phase="component_selection", counters={"triangles": len(component_by_triangle)})
    for number, segment in enumerate(v2._iter_segments(groups, context)):
        if number % 1024 == 0:
            v2._rss_guard(resource_check, phase="legacy_native_knot_prepass", counters={"visited_segments": number})
        if any(side["triangle_id"] in component_by_triangle for side in segment["sides"]):
            _register_legacy_knots(segment, context)
    proofs = []
    by_triangle = defaultdict(list)
    for segment in v2._iter_segments(groups, context):
        if not any(side["triangle_id"] in component_by_triangle for side in segment["sides"]):
            continue
        if len(proofs) % 256 == 0:
            v2._rss_guard(resource_check, phase="selected_proofs", counters={"proofs": len(proofs)})
        proof = _proof(segment, context)
        proofs.append(proof)
        for side in segment["sides"]:
            identifier = side["triangle_id"]
            by_triangle[identifier].append(proof)
            if identifier in component_by_triangle:
                reasons_by_component[component_by_triangle[identifier]].update(proof["rejection_reasons"])
    del groups, bank_points
    gc.collect()
    v2._rss_guard(resource_check, phase="selected_proofs_complete", counters={"proofs": len(proofs)})
    port_proofs = [_seal(record) for record in v2._port_proofs(
        transitions, sections, proofs, component_by_triangle, reasons_by_component)]
    functions = {}
    for number, identifier in enumerate(sorted(component_by_triangle)):
        if number % 128 == 0:
            v2._rss_guard(resource_check, phase="raw_functions", counters={"functions": number, "proofs": len(proofs)})
        function = build_triangle_function(triangles[identifier], by_triangle[identifier], context, base["parameters"])
        functions[identifier] = function
        component = component_by_triangle[identifier]
        reasons_by_component[component].update(function["rejection_reasons"])
        if triangles[identifier]["status"] not in {"rasterized", "no_center_coverage"}:
            reasons_by_component[component].add("parent_triangle_coverage_incomplete")
    context.get("bank_sample_cache", {}).clear()
    context.get("bank_patch_cache", {}).clear()
    context.get("v3_legacy_knots", {}).clear()
    del by_triangle
    gc.collect()
    v2._rss_guard(resource_check, phase="raw_functions_complete", counters={"functions": len(functions)})
    census = Counter(proposal["triangle_id"] for cell, owner in cells.values() for proposal in cell["triangle_sources"])
    for identifier, component in component_by_triangle.items():
        if census[identifier] != triangles[identifier].get("covered_centers", 0):
            reasons_by_component[component].add("saved_triangle_center_census_mismatch")
    affected_cells = [(key, cell, owner) for key, (cell, owner) in cells.items()
                      if any(proposal["triangle_id"] in component_by_triangle for proposal in cell["triangle_sources"])]
    parent_cell_count = len(cells)
    original_fill_count = sum("fill_without_material" in cell["rejection_reasons"] for cell, owner in cells.values())
    del cells, census
    effects = []
    origin, spacing = np.asarray(base["grid"]["origin_m_xz"]), base["grid"]["spacing_m"]
    for number, (key, cell, owner) in enumerate(sorted(affected_cells)):
        if number % 4096 == 0:
            v2._rss_guard(resource_check, phase="effects", counters={"visited_cells": number, "effects": len(effects)})
        components = {component_by_triangle[proposal["triangle_id"]] for proposal in cell["triangle_sources"]
                      if proposal["triangle_id"] in component_by_triangle}
        if any(reasons_by_component[component] for component in components):
            continue
        point = origin + (np.array([key[1], key[0]]) + base["grid"]["center_offset_cells"]) * spacing
        source_height = cell["source_sample"]["height_m"]
        if source_height is None:
            for component in components:
                reasons_by_component[component].add("saved_source_unknown")
            continue
        proposals = []
        try:
            for original in cell["triangle_sources"]:
                proposal = dict(original)
                if original["triangle_id"] in functions:
                    value = evaluate_bank_function(functions[original["triangle_id"]], float(point[0]), float(point[1]), source_height)
                    proposal["legacy_absolute_bed_m"] = original["bed_m"]
                    proposal.update(value)
                proposals.append(proposal)
            after = v2._evaluate(cell["source_sample"], proposals, cell["local_index"], base["parameters"])
            if after["status"] != "candidate":
                for component in components:
                    reasons_by_component[component].update("v3_cell_gate:" + reason for reason in after["rejection_reasons"])
                continue
        except ValueError as error:
            for component in components:
                reasons_by_component[component].add("v3_cell_function:" + str(error))
            continue
        before_cut, after_cut = v2._cut(cell, spacing), v2._cut(after, spacing)
        effects.append({"global_key_row_column": list(key), "operation": "replace", "logical_owner": owner,
            "component_ids": sorted(components), "before_sha256": v2._digest(cell), "cell": after,
            "before_cut_m3": before_cut, "after_cut_m3": after_cut,
            "cut_delta_m3": after_cut - before_cut, "source_sample_reused": True,
            "policy_identity_sha256": POLICY_IDENTITY_SHA256})
    changed = True
    while changed:
        changed = False
        for key, cell, owner in affected_cells:
            components = {component_by_triangle[item["triangle_id"]] for item in cell["triangle_sources"]
                          if item["triangle_id"] in component_by_triangle}
            if any(reasons_by_component[component] for component in components):
                for component in components:
                    if not reasons_by_component[component]:
                        reasons_by_component[component].add("overlapping_refused_component")
                        changed = True
    effects = [effect for effect in effects if not any(reasons_by_component[item] for item in effect["component_ids"])]
    components = {component: {"component_id": component, "triangle_ids": members,
        "status": "refused" if reasons_by_component[component] else "candidate",
        "rejection_reasons": sorted(reasons_by_component[component]),
        "seed_triangle_ids": sorted(set(members).intersection(seeds)),
        "union_method": "entire_parent_shared_edge_component_including_T_junction_overlaps"}
        for component, members in member_sets.items()}
    queue = v2._connection_queue(transitions, paths, sections, readiness, component_by_triangle, components)
    queue["schema"] = SCHEMA + "-connection-queue"
    _seal(queue)
    before_ledger = deepcopy(shard_package["manifest"]["material_ledger_merged"])
    delta = v2._ledger(math.fsum(effect["cut_delta_m3"] for effect in effects))
    after_ledger = {name: before_ledger[name] + delta[name] for name in v2.LEDGER_KEYS}
    package = {"raw": _chunks("raw", list(functions.values()), max_shard_bytes, parent_identity),
               "proofs": _chunks("proofs", proofs + port_proofs, max_shard_bytes, parent_identity),
               "effects": _chunks("effects", effects, max_shard_bytes, parent_identity), "queue": queue}
    package["manifest"] = _seal({"schema": SCHEMA, "algorithm": ALGORITHM, "inputs": dict(input_pins or {}),
        "policy": dict(POLICY), "boundary_evidence": evidence,
        "parent_identity_sha256": parent_identity, "base_identity_sha256": base["identity_sha256"],
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "source_identity_sha256": base["source_identity_sha256"],
        "sections_identity_sha256": sections["identity_sha256"], "transitions_identity_sha256": transitions["identity_sha256"],
        "paths_identity_sha256": paths["identity_sha256"], "grid": deepcopy(base["grid"]),
        "selected_leaf_ids": list(base["selected_leaf_ids"]), "wet_protection": deepcopy(base["wet_protection"]),
        "parameters": deepcopy(base["parameters"]),
        "budgets": {"max_cells": max_cells, "max_shard_bytes": max_shard_bytes, "max_rss_bytes": MAX_RSS},
        "proof_tolerances": {"geometry_m": v2.GEOMETRY_TOLERANCE_M, "function_m": v2.FUNCTION_TOLERANCE_M},
        "components": list(components.values()), "affected_global_keys_row_column": [list(item[0]) for item in sorted(affected_cells)],
        "summary": {"parent_unique_cells": parent_cell_count, "original_fill_refused_cells": original_fill_count,
            "seed_triangles": len(seeds), "affected_triangles": len(functions), "affected_cells": len(affected_cells),
            "replace_cells": len(effects), "unchanged_parent_cells": parent_cell_count - len(effects),
            "candidate_components": sum(item["status"] == "candidate" for item in components.values()),
            "refused_components": sum(item["status"] == "refused" for item in components.values()),
            "center_source_resamples": 0, "new_lattice_cells": 0, "water_solves": 0},
        "material_ledger_parent": before_ledger, "material_ledger_delta": delta, "material_ledger_candidate": after_ledger,
        "chunk_identities": {kind: [chunk["identity_sha256"] for chunk in package[kind]] for kind in ("raw", "proofs", "effects")},
        "queue_identity_sha256": queue["identity_sha256"], "old_mesh_passed": False,
        "old_port_preservation_claimed": False, "independent_audit_passed": False,
        **{flag: False for flag in FLAGS}})
    v2._rss_guard(resource_check, phase="candidate_chunks_complete")
    validate_source_conforming_banks(package)
    return package


def validate_source_conforming_banks(package, *, base=None, shard_package=None, hierarchy=None,
                                     sections=None, paths=None):
    manifest = package["manifest"]
    if (manifest.get("policy") != POLICY or manifest.get("policy_identity_sha256") != POLICY_IDENTITY_SHA256):
        raise ValueError("v3 policy identity mismatch")
    if (sections is None) != (paths is None):
        raise ValueError("both sections and paths required for cold BC evidence")
    evidence = manifest["boundary_evidence"]
    if sections is not None and evidence != _boundary_evidence(sections, paths):
        raise ValueError("v3 original section/path boundary evidence mismatch")
    proofs = [record for chunk in package["proofs"] for record in chunk["records"]
              if record["kind"] == "edge_function_proof"]
    for kind in ("raw", "proofs", "effects"):
        for chunk in package[kind]:
            if chunk.get("policy_identity_sha256") != POLICY_IDENTITY_SHA256:
                raise ValueError("v3 chunk policy mismatch")
            for record in chunk["records"]:
                if record.get("policy_identity_sha256") != POLICY_IDENTITY_SHA256:
                    raise ValueError("v3 record policy mismatch")
    v2._check_identity(manifest)
    v2._check_identity(package["queue"])
    budgets = manifest["budgets"]
    if (manifest["schema"] != SCHEMA or manifest["algorithm"] != ALGORITHM
            or not 1 <= budgets["max_cells"] <= MAX_CELLS
            or not 4096 <= budgets["max_shard_bytes"] <= MAX_BYTES
            or budgets["max_rss_bytes"] != MAX_RSS
            or any(manifest.get(flag) is not False for flag in FLAGS)
            or manifest["old_mesh_passed"] is not False or manifest["independent_audit_passed"] is not False):
        raise ValueError("source-conforming schema/budget/certification mismatch")
    if (package["queue"]["identity_sha256"] != manifest["queue_identity_sha256"]
            or package["queue"]["schema"] != SCHEMA + "-connection-queue"):
        raise ValueError("connection queue pin/schema mismatch")
    parents = None
    if base is not None and shard_package is not None:
        if (base["identity_sha256"] != manifest["base_identity_sha256"]
                or shard_package["manifest"]["identity_sha256"] != manifest["parent_identity_sha256"]
                or base["grid"] != manifest["grid"]
                or shard_package["manifest"]["material_ledger_merged"] != manifest["material_ledger_parent"]):
            raise ValueError("cold immutable parent linkage mismatch")
        parents = {key: (cell, owner) for key, cell, owner in v2.iter_merged_cells(base, shard_package["shards"])}
    keys, deltas, functions, edge_proofs = set(), [], {}, {}
    component_by_triangle = {identifier: component for component in manifest["components"] for identifier in component["triangle_ids"]}
    if len(component_by_triangle) != sum(len(component["triangle_ids"]) for component in manifest["components"]):
        raise ValueError("duplicate component triangle ownership")
    for kind in ("raw", "proofs", "effects"):
        if (len(package[kind]) > v2.MAX_FILES
                or [item["identity_sha256"] for item in package[kind]] != manifest["chunk_identities"][kind]):
            raise ValueError("chunk identity census mismatch")
        for chunk in package[kind]:
            v2._check_identity(chunk)
            if (chunk["schema"] != SCHEMA + "-" + kind
                    or chunk["parent_identity_sha256"] != manifest["parent_identity_sha256"]
                    or v2._record_bytes(chunk) > budgets["max_shard_bytes"]):
                raise ValueError("chunk parent pin/schema/byte limit mismatch")
            for record in chunk["records"]:
                if kind in ("raw", "proofs"):
                    v2._check_identity(record)
                    if (record["status"] not in {"candidate", "refused"}
                            or bool(record["rejection_reasons"]) != (record["status"] == "refused")):
                        raise ValueError("v3 status/reason mismatch")
                if kind == "raw":
                    identifier = record["triangle_id"]
                    if identifier in functions or identifier not in component_by_triangle:
                        raise ValueError("duplicate/unselected raw triangle")
                    functions[identifier] = record
                    if record["status"] == "candidate" and any(
                            depth < 0 for fan in record["fans"] for depth in fan["depth_at_vertices_m"]):
                        raise ValueError("negative candidate depth")
                elif kind == "proofs":
                    if record["kind"] == "edge_function_proof":
                        if record["segment_id"] in edge_proofs:
                            raise ValueError("duplicate edge proof")
                        edge_proofs[record["segment_id"]] = record
                else:
                    key = tuple(record["global_key_row_column"])
                    if key in keys or record["operation"] != "replace" or not record["source_sample_reused"]:
                        raise ValueError("duplicate/new center transaction")
                    keys.add(key)
                    cell = record["cell"]
                    if any(component_by_triangle[item["triangle_id"]]["status"] != "candidate"
                           for item in cell["triangle_sources"] if item["triangle_id"] in component_by_triangle):
                        raise ValueError("effect applied refused component")
                    if parents is not None:
                        before, owner = parents[key]
                        if (v2._digest(before) != record["before_sha256"] or owner != record["logical_owner"]
                                or before["source_sample"] != cell["source_sample"]
                                or abs(v2._cut(before, manifest["grid"]["spacing_m"]) - record["before_cut_m3"]) > 1e-10):
                            raise ValueError("effect parent/source/owner mismatch")
                    cut = v2._cut(cell, manifest["grid"]["spacing_m"])
                    if (abs(cut - record["after_cut_m3"]) > 1e-10
                            or abs(cut - record["before_cut_m3"] - record["cut_delta_m3"]) > 1e-10):
                        raise ValueError("signed effect material mismatch")
                    deltas.append(record["cut_delta_m3"])
    if set(functions) != set(component_by_triangle) or len(keys) != manifest["summary"]["replace_cells"]:
        raise ValueError("complete affected union/effect census mismatch")
    if len(manifest["affected_global_keys_row_column"]) != manifest["summary"]["affected_cells"]:
        raise ValueError("affected center census mismatch")
    if (manifest["summary"]["parent_unique_cells"] > budgets["max_cells"]
            or not keys.issubset({tuple(key) for key in manifest["affected_global_keys_row_column"]})):
        raise ValueError("effect outside bounded affected union")
    expected_delta = v2._ledger(math.fsum(deltas))
    for name in v2.LEDGER_KEYS:
        if (abs(expected_delta[name] - manifest["material_ledger_delta"][name]) > 1e-9
                or abs(manifest["material_ledger_parent"][name] + expected_delta[name]
                       - manifest["material_ledger_candidate"][name]) > 1e-9):
            raise ValueError("signed material ledger double count")
    for component in manifest["components"]:
        if (component["status"] not in {"candidate", "refused"}
                or bool(component["rejection_reasons"]) != (component["status"] == "refused")):
            raise ValueError("component status/reason mismatch")
        if component["status"] == "candidate" and any(
                functions[identifier]["status"] != "candidate" for identifier in component["triangle_ids"]):
            raise ValueError("candidate component has refused raw function")
    if hierarchy is not None:
        if hierarchy["identity_sha256"] != manifest["hierarchy_identity_sha256"]:
            raise ValueError("cold source identity mismatch")
        context = v2._context(hierarchy, manifest["selected_leaf_ids"], manifest["wet_protection"])
        context["v3_parameters"] = manifest["parameters"]
        context["v3_boundary_evidence"] = evidence
        for proof in edge_proofs.values():
            _register_legacy_knots(proof, context)
        by_triangle = defaultdict(list)
        for proof in edge_proofs.values():
            expected = _proof({name: proof[name] for name in (
                "segment_id", "start_xz_m", "end_xz_m", "sides", "depth_support_knots")}, context)
            if proof != expected:
                raise ValueError("cold full edge function proof mismatch: " + proof["segment_id"])
            for side in proof["sides"]:
                by_triangle[side["triangle_id"]].append(proof)
        for identifier, function in functions.items():
            expected = build_triangle_function(function["original_triangle"], by_triangle[identifier],
                                               context, manifest["parameters"])
            if expected != function:
                raise ValueError("cold source-relative raw function mismatch")
    return package


def save_source_conforming_banks(package, directory, *, resource_check=None):
    validate_source_conforming_banks(package)
    target = Path(directory)
    if target.exists():
        raise FileExistsError(target)
    files = {"manifest.json": package["manifest"], "connection-queue.json": package["queue"]}
    for kind in ("raw", "proofs", "effects"):
        files.update({kind + "/" + chunk["chunk_id"] + ".json": chunk for chunk in package[kind]})
    if len(files) > v2.MAX_FILES:
        raise MemoryError("source-conforming file count budget exceeded")
    for name, record in files.items():
        v2._rss_guard(resource_check)
        if v2._record_bytes(record) > package["manifest"]["budgets"]["max_shard_bytes"]:
            raise MemoryError("new candidate file exceeds bounded byte budget: " + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".source-conforming-v3-", dir=target.parent) as staging:
        staging_path = Path(staging) / "package"
        for name, record in files.items():
            v2._rss_guard(resource_check)
            v2._write_record(staging_path / name, record)
        v2._rss_guard(resource_check)
        staging_path.rename(target)
    return target


def load_source_conforming_banks(directory, *, expected_manifest_sha256, expected_manifest_identity, **parents):
    target = Path(directory)

    def read(path):
        if path.stat().st_size > MAX_BYTES:
            raise MemoryError("saved source-conforming file exceeds 64MiB")
        return json.loads(path.read_bytes())

    if v2.file_sha256(target / "manifest.json") != expected_manifest_sha256:
        raise ValueError("external manifest SHA mismatch")
    manifest = read(target / "manifest.json")
    if manifest["identity_sha256"] != expected_manifest_identity:
        raise ValueError("external manifest identity mismatch")
    package = {"manifest": manifest, "queue": read(target / "connection-queue.json")}
    for kind in ("raw", "proofs", "effects"):
        if len(manifest["chunk_identities"][kind]) > v2.MAX_FILES:
            raise MemoryError("saved chunk count exceeded")
        package[kind] = [read(target / kind / (kind + "-" + str(index).zfill(4) + ".json"))
                         for index in range(len(manifest["chunk_identities"][kind]))]
    return validate_source_conforming_banks(package, **parents)
