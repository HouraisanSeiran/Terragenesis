"""Bounded, atomic hub selection and evidence-based display-network composition."""

from collections import defaultdict, deque
from copy import deepcopy
import math

import numpy as np
import psutil

from terrain_pipeline import td_ported_junction as junction
from terrain_pipeline import channel_geometry as geometry

SCHEMA = "td-ported-network-composition-v1"
MAX_HUBS = 256
MAX_BYTES = junction.MAX_BYTES
MAX_RSS = junction.MAX_RSS
TOLERANCE_M = 1e-9
POLICY = {"schema": SCHEMA, "census": "all_actual_three_land_channel_arms_q_descending",
    "selection": "whole_hub_atomic_missing_unique_arcs_original_06_unchanged",
    "ports": "actual_three_boundary_segments_reverse_whole_native_function_union_partition",
    "conflicts": "positive_projected_overlap_partial_edge_contact_nonmanifold_or_unbound_seam_refuse_whole_hub",
    "source": "unchanged_frozen_ported_junction_native_source_nonnegative_cut_wet_guards",
    "topology": "full_section_geometry_connections_not_node_id_adjacency_candidate_until_independent_audit",
    "max_hubs": MAX_HUBS, "max_json_bytes": MAX_BYTES, "max_rss_bytes": MAX_RSS}
POLICY_IDENTITY_SHA256 = geometry._record_identity(POLICY)


def check_memory():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, "peak_wset", 0))
    if peak > MAX_RSS:
        raise MemoryError("network composition exceeds 1GiB RSS")
    return peak


def census_hubs(paths, sections):
    incident = defaultdict(list)
    for arc in paths["arcs"]:
        if arc["kind"] == "land_channel":
            for node_id in arc["node_ids"]:
                incident[node_id].append(arc["arc_id"])
    profiles = {section["node_id"]: section for section in sections["node_sections"]}
    result = []
    for node_id, arc_ids in incident.items():
        if len(arc_ids) != 3:
            continue
        section = profiles.get(node_id, {})
        flow = float(section.get("representative_q_m3_s", 0.))
        if not math.isfinite(flow) or flow < 0.:
            raise ValueError("invalid saved ordinary Q")
        result.append({"hub_node_id": node_id, "ordinary_q_m3_s": flow,
            "incident_arc_ids": sorted(arc_ids), "anchor": bool(section.get("anchor", False)),
            "parent_rejection_reasons": list(section.get("rejection_reasons", []))})
    if len(result) > MAX_HUBS:
        raise ValueError("all-hub census exceeds 256; no silent truncation allowed")
    return sorted(result, key=lambda row: (-row["ordinary_q_m3_s"], row["hub_node_id"]))


def _pair_key(pair):
    return tuple(sorted(tuple(point) for point in np.asarray(pair)[:, [0, 2]].tolist()))


def _boundary(mesh, triangle_ids):
    incidence = defaultdict(list)
    for triangle_id in triangle_ids:
        indices = mesh["triangles"][triangle_id]
        for edge_index in range(3):
            pair = [mesh["vertices_xyz_m"][indices[edge_index]],
                    mesh["vertices_xyz_m"][indices[(edge_index + 1) % 3]]]
            incidence[_pair_key(pair)].append({"triangle_index": triangle_id,
                "edge_index": edge_index, "points_xyz_m": pair})
    return {key: sides[0] for key, sides in incidence.items() if len(sides) == 1}


def _old_ports(sections):
    ports = []
    for section_index, section in enumerate(sections["edge_sections"]):
        if not section["triangle_indices"]:
            continue
        boundary = _boundary(sections["mesh"], section["triangle_indices"])
        for profile_index, (node_id, profile) in enumerate(zip(section["node_ids"], section["cross_section_xyz_m"])):
            if len(profile) != 4:
                continue
            segments = []
            for number in range(3):
                pair = profile[number:number + 2]
                witness = boundary.get(_pair_key(pair))
                if witness is None or witness["points_xyz_m"] not in (pair, pair[::-1]):
                    break
                segments.append({"points_xyz_m": pair, "profile_segment_index": number,
                    "pieces": [{"interval_t01": [0., 1.], "start_xz_m": [pair[0][0], pair[0][2]],
                        "end_xz_m": [pair[1][0], pair[1][2]],
                        "bed_coefficients_m_t012": [pair[0][1], pair[1][1] - pair[0][1], 0.],
                        "source_coefficients_m_t012": None, "segment_id": None,
                        "side": {**witness, "kind": "legacy06"}}]})
            if len(segments) == 3:
                ports.append({"kind": "legacy06", "hub_node_id": None, "arc_id": section["arc_id"],
                    "outer_node_id": node_id, "original_profile_xyz_m": profile,
                    "section_index": section_index, "profile_index": profile_index, "segments": segments})
    return ports


def _new_ports(record):
    proofs = {proof["segment_id"]: proof for proof in record["edge_proofs"]}
    arms = {arm["arc_id"]: arm for arm in record["arms"]}
    result = []
    for port in record["port_proofs"]:
        if port["kind"] != "outer_port_proof":
            continue
        if port["status"] != "candidate" or len(port["profile_segments"]) != 3:
            raise ValueError("candidate outer port proof incomplete")
        arm = arms[port["arc_id"]]
        segments = []
        for segment in port["profile_segments"]:
            pieces = []
            for reference in segment["native_pieces"]:
                proof = proofs[reference["segment_id"]]
                sides = [side for side in proof["sides"] if side["triangle_id"].startswith("junction:")]
                if proof["status"] != "candidate" or len(sides) != 1:
                    raise ValueError("outer port must have one actual patch boundary side")
                side = sides[0]
                triangle_id = int(side["triangle_id"].split(":")[1])
                indices = record["geometry"]["triangles"][triangle_id]
                actual_pair = [record["geometry"]["vertices_xyz_m"][indices[side["edge_index"]]],
                    record["geometry"]["vertices_xyz_m"][indices[(side["edge_index"] + 1) % 3]]]
                if actual_pair != side["points_xyz_m"]:
                    raise ValueError("port side does not reference actual triangle edge")
                source = proof["source"]["source_coefficients_m_t012"]
                depth = proof["depth_coefficients_m_t01"]
                pieces.append({"interval_t01": reference["interval_t01"],
                    "start_xz_m": proof["start_xz_m"], "end_xz_m": proof["end_xz_m"],
                    "bed_coefficients_m_t012": [source[0] - depth[0], source[1] - depth[1], source[2]],
                    "source_coefficients_m_t012": source, "segment_id": proof["segment_id"],
                    "common_function_identity_sha256": proof["common_function_identity_sha256"],
                    "side": {"kind": "junction", "hub_node_id": record["hub_node_id"],
                        "triangle_index": triangle_id, "edge_index": side["edge_index"],
                        "points_xyz_m": actual_pair}})
            segments.append({"points_xyz_m": segment["points_xyz_m"],
                "profile_segment_index": segment["profile_segment_index"], "pieces": pieces})
        result.append({"kind": "junction", "hub_node_id": record["hub_node_id"],
            "arc_id": arm["arc_id"], "outer_node_id": arm["outer_node_id"],
            "original_profile_xyz_m": arm["outer_profile_xyz_m"],
            "outer_section_index": arm["outer_section_index"],
            "attachment_status": arm["attachment_status"], "segments": segments})
    if len(result) != 3:
        raise ValueError("candidate must expose three complete outer ports")
    return result


def _piece_coordinates(piece, pair):
    start, end = np.asarray(pair)[:, [0, 2]]
    vector = end - start
    denominator = float(vector @ vector)
    if denominator <= 0.:
        raise ValueError("degenerate profile segment")
    parameters = []
    for point in (piece["start_xz_m"], piece["end_xz_m"]):
        point = np.asarray(point)
        if abs(junction._cross(vector, point - start)) > TOLERANCE_M * math.sqrt(denominator):
            raise ValueError("native piece off original section")
        parameters.append(float((point - start) @ vector / denominator))
    if min(parameters) < -TOLERANCE_M or max(parameters) > 1. + TOLERANCE_M:
        raise ValueError("native piece outside original whole section")
    return parameters


def _reparameterize(coefficients, piece_coordinates, interval):
    first, second = piece_coordinates
    if abs(second - first) <= 1e-14:
        raise ValueError("empty native interval")
    offset = (interval[0] - first) / (second - first)
    scale = (interval[1] - interval[0]) / (second - first)
    constant, linear, quadratic = coefficients
    return [constant + linear * offset + quadratic * offset * offset,
        scale * (linear + 2. * quadratic * offset), quadratic * scale * scale]


def match_ports(first, second):
    """Return actual reverse-boundary union-partition witnesses, or a refusal reason."""
    profile = first["original_profile_xyz_m"]
    other = second["original_profile_xyz_m"]
    if first["outer_node_id"] != second["outer_node_id"] or other not in (profile, profile[::-1]):
        return None, "original_four_point_section_mismatch"
    pieces_out = []
    try:
        for segment_index in range(3):
            pair = profile[segment_index:segment_index + 2]
            first_segment = first["segments"][segment_index]
            second_index = segment_index if other == profile else 2 - segment_index
            second_segment = second["segments"][second_index]
            groups = []
            for segment in (first_segment, second_segment):
                group = [(piece, _piece_coordinates(piece, pair)) for piece in segment["pieces"]]
                intervals = sorted(sorted(coordinates) for piece, coordinates in group)
                if not intervals or abs(intervals[0][0]) > TOLERANCE_M or abs(intervals[-1][1] - 1.) > TOLERANCE_M:
                    raise ValueError("native interval incomplete")
                for previous, current in zip(intervals, intervals[1:]):
                    if abs(previous[1] - current[0]) > TOLERANCE_M:
                        raise ValueError("native interval gap or overlap")
                groups.append(group)
            knots = sorted(set([0., 1.] + [coordinate for group in groups for piece, coords in group for coordinate in coords]))
            for low, high in zip(knots, knots[1:]):
                if high - low <= 1e-14:
                    continue
                midpoint = (low + high) / 2.
                selected = []
                for group in groups:
                    matches = [(piece, coords) for piece, coords in group if min(coords) <= midpoint <= max(coords)]
                    if len(matches) != 1:
                        raise ValueError("native interval ambiguous")
                    selected.append(matches[0])
                (first_piece, first_coords), (second_piece, second_coords) = selected
                first_side, second_side = first_piece["side"], second_piece["side"]
                if first_side["points_xyz_m"] != second_side["points_xyz_m"][::-1]:
                    raise ValueError("actual boundary edges not reverse")
                whole = [_reparameterize(piece["bed_coefficients_m_t012"], coords, [low, high])
                         for piece, coords in selected]
                differences = [left - right for left, right in zip(*whole)]
                if max(abs(value) for value in differences) > TOLERANCE_M:
                    raise ValueError("whole native bed coefficient mismatch")
                source_difference = None
                if all(piece["source_coefficients_m_t012"] is not None for piece, coords in selected):
                    source_coefficients = [_reparameterize(piece["source_coefficients_m_t012"], coords, [low, high])
                                           for piece, coords in selected]
                    source_difference = [left - right for left, right in zip(*source_coefficients)]
                    if max(abs(value) for value in source_difference) > TOLERANCE_M:
                        raise ValueError("whole native source coefficient mismatch")
                start, end = np.asarray(pair)[:, [0, 2]]
                pieces_out.append({"profile_segment_index": segment_index, "interval_t01": [low, high],
                    "start_xz_m": (start + (end - start) * low).tolist(),
                    "end_xz_m": (start + (end - start) * high).tolist(),
                    "first_segment_id": first_piece["segment_id"], "second_segment_id": second_piece["segment_id"],
                    "first_side": first_side, "second_side": second_side, "reverse_seam": True,
                    "whole_bed_coefficients_m_t012": whole,
                    "difference_coefficients_m_t012": differences,
                    "source_difference_coefficients_m_t012": source_difference})
    except ValueError as error:
        return None, str(error)
    return {"kind": "complete_original_section_reverse_function_seam",
        "first_hub": first["hub_node_id"], "second_hub": second["hub_node_id"],
        "first_arc": first["arc_id"], "second_arc": second["arc_id"],
        "first_kind": first["kind"], "second_kind": second["kind"],
        "outer_node_id": first["outer_node_id"], "original_profile_xyz_m": profile,
        "native_pieces": pieces_out, "verified": False}, None


def _contact(first, second):
    first_start, first_end = np.asarray(first)[:, [0, 2]]
    second_start, second_end = np.asarray(second)[:, [0, 2]]
    vector = first_end - first_start
    length = float(np.linalg.norm(vector))
    if length <= 1e-12:
        return False
    if any(abs(junction._cross(vector, point - first_start)) > TOLERANCE_M * length
           for point in (second_start, second_end)):
        return False
    parameters = sorted(float((point - first_start) @ vector / (length * length))
                        for point in (second_start, second_end))
    return min(1., parameters[1]) - max(0., parameters[0]) > 1e-10


class NetworkComposer:
    """Retains lightweight accepted geometry/ports, never per-hub raw fan functions."""

    def __init__(self, paths, sections):
        self.paths = paths
        self.sections = sections
        self.mesh = {"vertices_xyz_m": deepcopy(sections["mesh"]["vertices_xyz_m"]),
            "triangles": deepcopy(sections["mesh"]["triangles"]),
            "face_origins": [{"kind": "legacy06", "triangle_index": number,
                "arc_id": arc_id} for number, arc_id in enumerate(sections["mesh"]["triangle_arc_ids"])],
            "parametric_only": True, "fine_generated": False, "original_06_prefix_unchanged": True}
        self.owners = {arc_id: {"kind": "legacy06"} for arc_id in sections["mesh"]["triangle_arc_ids"]}
        self.ports = _old_ports(sections)
        self.connections = []
        self.hubs = []
        self.used_hubs = set()
        self.closed_ports = set()
        for number, first in enumerate(self.ports):
            for second in self.ports[number + 1:]:
                if first["outer_node_id"] != second["outer_node_id"] or first["arc_id"] == second["arc_id"]:
                    continue
                proof, reason = match_ports(first, second)
                if reason is None:
                    self.connections.append(proof)
                    self.closed_ports.update([self._port_id(first), self._port_id(second)])
        self._refresh_projection()

    @staticmethod
    def _port_id(port):
        return (port["kind"], port["hub_node_id"], port["arc_id"], port["outer_node_id"])

    def _refresh_projection(self):
        points = np.asarray(self.mesh["vertices_xyz_m"], float).reshape(-1, 3)
        self.projected = points[np.asarray(self.mesh["triangles"], int).reshape(-1, 3)][:, :, [0, 2]]
        self.low = self.projected.min(axis=1) if len(self.projected) else np.empty((0, 2))
        self.high = self.projected.max(axis=1) if len(self.projected) else np.empty((0, 2))

    def _conflicts(self, record, seams):
        reasons, witnesses = set(), []
        allowed = {_pair_key(proof["original_profile_xyz_m"][number:number + 2])
                   for proof in seams for number in range(3)}
        mesh = record["geometry"]
        projected = np.asarray(mesh["vertices_xyz_m"], float)[np.asarray(mesh["triangles"], int)][:, :, [0, 2]]
        pending_edges = defaultdict(list)
        for triangle_id, triangle in enumerate(projected):
            if junction._cross(triangle[1] - triangle[0], triangle[2] - triangle[0]) <= 1e-10:
                reasons.add("degenerate_or_reversed_triangle")
            indices = mesh["triangles"][triangle_id]
            pairs = [[mesh["vertices_xyz_m"][indices[edge]], mesh["vertices_xyz_m"][indices[(edge + 1) % 3]]]
                     for edge in range(3)]
            for pair in pairs:
                pending_edges[_pair_key(pair)].append(pair)
            candidates = np.flatnonzero(np.all(self.high >= triangle.min(axis=0), axis=1)
                & np.all(self.low <= triangle.max(axis=0), axis=1))
            for old_index in candidates:
                old = self.projected[old_index]
                if junction._cross(old[1] - old[0], old[2] - old[0]) < 0.:
                    old = old[::-1]
                if junction._overlap_area(triangle, old) > 1e-8:
                    reasons.add("positive_projected_overlap")
                    if len(witnesses) < 32:
                        witnesses.append({"new_triangle_index": triangle_id,
                            "existing_face_index": int(old_index), "kind": "positive_projected_overlap"})
                old_indices = self.mesh["triangles"][old_index]
                for edge in range(3):
                    old_pair = [self.mesh["vertices_xyz_m"][old_indices[edge]],
                        self.mesh["vertices_xyz_m"][old_indices[(edge + 1) % 3]]]
                    for pair in pairs:
                        if _contact(pair, old_pair):
                            if (_pair_key(pair) != _pair_key(old_pair) or _pair_key(pair) not in allowed
                                    or pair != old_pair[::-1]):
                                reasons.add("partial_unbound_or_wrong_direction_edge_contact")
        for number, triangle in enumerate(projected):
            for other in projected[number + 1:]:
                if junction._overlap_area(triangle, other) > 1e-8:
                    reasons.add("internal_positive_projected_overlap")
        existing_incidence = defaultdict(list)
        for indices in self.mesh["triangles"]:
            for edge in range(3):
                pair = [self.mesh["vertices_xyz_m"][indices[edge]],
                    self.mesh["vertices_xyz_m"][indices[(edge + 1) % 3]]]
                key = _pair_key(pair)
                if key in pending_edges:
                    existing_incidence[key].append(pair)
        for key, pairs in pending_edges.items():
            sides = pairs + existing_incidence[key]
            if len(sides) > 2 or len(sides) == 2 and sides[0] != sides[1][::-1]:
                reasons.add("nonmanifold_or_same_direction_seam")
        return sorted(reasons), witnesses

    def add_junction(self, record, junction_pin=None, census_entry=None):
        check_memory()
        hub_id = record["hub_node_id"]
        if len(self.hubs) >= MAX_HUBS or hub_id in self.used_hubs:
            raise ValueError("duplicate hub or census budget exceeded")
        self.used_hubs.add(hub_id)
        row = {**(census_entry or {}), "hub_node_id": hub_id, "junction": junction_pin,
            "generation_status": record["status"], "composition_status": "refused",
            "generation_rejection_reasons": record["rejection_reasons"],
            "rejection_reasons": [], "conflict_witnesses": [], "added_arc_ids": []}
        self.hubs.append(row)
        if record["status"] != "candidate":
            row["rejection_reasons"] = ["junction_generation_refused"]
            return row
        reasons = set()
        requested = record["requested_replacement_arc_ids"]
        if len(requested) != 3 or len(set(requested)) != 3 or any(arc_id in self.owners for arc_id in requested):
            reasons.add("duplicate_or_existing_incident_arc")
        if (record["parents"]["paths"] != self.paths["identity_sha256"]
                or record["parents"]["sections"] != self.sections["identity_sha256"]):
            reasons.add("parent_identity_mismatch")
        if (record["policy_identity_sha256"] != junction.POLICY_IDENTITY_SHA256
                or not record["internal_three_arm_geometry_candidate"]
                or record["rejection_reasons"]
                or record["transaction"]["candidate_replacement_arc_ids"] != requested
                or record["transaction"]["replaced_original_triangle_indices"]
                or record["old_kept_mesh_triangle_ids"] != list(range(len(self.sections["mesh"]["triangles"])) )):
            reasons.add("invalid_candidate_transaction")
        seams = []
        try:
            ports = _new_ports(record)
            for port in ports:
                candidates = [existing for existing in self.ports if existing["outer_node_id"] == port["outer_node_id"]]
                for existing in candidates:
                    seam, reason = match_ports(port, existing)
                    if reason is not None:
                        reasons.add("shared_port_" + reason)
                    elif self._port_id(existing) in self.closed_ports:
                        reasons.add("shared_port_already_has_two_sides")
                    else:
                        seams.append(seam)
                if port["attachment_status"] == "actual_old_mesh" and not any(
                        seam["first_arc"] == port["arc_id"] and seam["second_kind"] == "legacy06" for seam in seams):
                    reasons.add("claimed_old_attachment_without_complete_reverse_seam")
            conflicts, witnesses = self._conflicts(record, seams)
            reasons.update(conflicts)
            row["conflict_witnesses"] = witnesses
        except (ValueError, KeyError, IndexError) as error:
            reasons.add("invalid_port_geometry:" + str(error))
        if reasons:
            row["rejection_reasons"] = sorted(reasons)
            return row
        offset = len(self.mesh["vertices_xyz_m"])
        self.mesh["vertices_xyz_m"].extend(deepcopy(record["geometry"]["vertices_xyz_m"]))
        self.mesh["triangles"].extend([[index + offset for index in triangle] for triangle in record["geometry"]["triangles"]])
        self.mesh["face_origins"].extend({"kind": "junction", "hub_node_id": hub_id,
            "triangle_index": number, "role": role} for number, role in enumerate(record["geometry"]["triangle_roles"]))
        for arc_id in requested:
            self.owners[arc_id] = {"kind": "junction", "hub_node_id": hub_id}
        self.connections.extend(seams)
        for seam in seams:
            self.closed_ports.add((seam["first_kind"], seam["first_hub"], seam["first_arc"], seam["outer_node_id"]))
            self.closed_ports.add((seam["second_kind"], seam["second_hub"], seam["second_arc"], seam["outer_node_id"]))
        self.connections.append({"kind": "complete_three_arm_inner_ring", "hub_node_id": hub_id,
            "arc_ids": requested, "port_proof_identities": [proof["identity_sha256"] for proof in record["port_proofs"]
                if proof["kind"] == "inner_port_proof"], "verified": False})
        self.ports.extend(ports)
        row["composition_status"] = "selected"
        row["added_arc_ids"] = requested
        self._refresh_projection()
        check_memory()
        return row

    def finish(self):
        topology = network_topology(self.paths, self.sections, self.owners, self.connections,
            [port for port in self.ports if self._port_id(port) not in self.closed_ports])
        manifest = {"schema": SCHEMA, "policy": POLICY, "policy_identity_sha256": POLICY_IDENTITY_SHA256,
            "parents": {"paths": self.paths["identity_sha256"], "sections": self.sections["identity_sha256"],
                "source": self.paths["source_identity_sha256"], "hierarchy": self.paths["hierarchy_identity_sha256"]},
            "hubs": self.hubs, "arc_owners": self.owners, "connections": self.connections,
            "original_06_kept_unchanged": True, "original_06_triangle_count": len(self.sections["mesh"]["triangles"]),
            "metrics_status": "candidate_unverified", "independent_audit_passed": False,
            "full_network_verified": False, **{flag: False for flag in junction.FLAGS}}
        return {"manifest": geometry._seal(manifest), "composed_mesh": geometry._seal(self.mesh),
            "topology": geometry._seal(topology)}


def network_topology(paths, sections, owners, connections, open_ports):
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
    for section in sections["edge_sections"]:
        arcs.setdefault(section["arc_id"], {"arc_id": section["arc_id"], "node_ids": section["node_ids"],
            "xyz_m": [[float(np.mean(np.asarray(profile)[:, 0])), float(np.mean(np.asarray(profile)[:, 1])),
                       float(np.mean(np.asarray(profile)[:, 2]))] for profile in section["cross_section_xyz_m"]]})
    adjacency = {arc_id: set() for arc_id in owners}
    directed = {arc_id: set() for arc_id in owners}
    for proof in connections:
        pairs = []
        if proof["kind"] == "complete_three_arm_inner_ring":
            arc_ids = proof["arc_ids"]
            pairs = [(first, second, proof["hub_node_id"]) for number, first in enumerate(arc_ids) for second in arc_ids[number + 1:]]
        else:
            pairs = [(proof["first_arc"], proof["second_arc"], proof["outer_node_id"])]
        for first, second, node_id in pairs:
            adjacency[first].add(second)
            adjacency[second].add(first)
            if arcs[first]["node_ids"][-1] == node_id and arcs[second]["node_ids"][0] == node_id:
                directed[first].add(second)
            if arcs[second]["node_ids"][-1] == node_id and arcs[first]["node_ids"][0] == node_id:
                directed[second].add(first)
    positions, lengths = {}, {}
    for arc_id in owners:
        arc = arcs[arc_id]
        coordinates = arc.get("xyz_m")
        if coordinates is None:
            coordinates = [nodes[node_id]["xyz_m"] for node_id in arc["node_ids"]]
        positions[arc_id] = coordinates
        projected = np.asarray(coordinates)[:, [0, 2]]
        lengths[arc_id] = float(np.linalg.norm(np.diff(projected, axis=0), axis=1).sum())
    components, visited = [], set()
    for root in sorted(owners):
        if root in visited:
            continue
        queue, members = [root], []
        visited.add(root)
        while queue:
            current = queue.pop()
            members.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        coordinates = np.asarray([point for arc_id in members for point in positions[arc_id]])
        components.append({"component_id": len(components), "arc_ids": sorted(members), "arc_count": len(members),
            "total_plan_length_m": math.fsum(lengths[arc_id] for arc_id in members),
            "bounds_xyz_m": [coordinates.min(axis=0).tolist(), coordinates.max(axis=0).tolist()]})
    indegree = dict.fromkeys(owners, 0)
    for successors in directed.values():
        for successor in successors:
            indegree[successor] += 1
    queue = deque(sorted(arc_id for arc_id, degree in indegree.items() if degree == 0))
    distance = dict(lengths)
    predecessor = {}
    processed = []
    while queue:
        current = queue.popleft()
        processed.append(current)
        for successor in sorted(directed[current]):
            proposed = distance[current] + lengths[successor]
            if proposed > distance[successor]:
                distance[successor] = proposed
                predecessor[successor] = current
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    longest = None
    cycle_arcs = sorted(arc_id for arc_id, degree in indegree.items() if degree)
    if not cycle_arcs and owners:
        endpoint = max(sorted(owners), key=lambda arc_id: distance[arc_id])
        chain = [endpoint]
        while chain[-1] in predecessor:
            chain.append(predecessor[chain[-1]])
        chain.reverse()
        longest = {"arc_ids": chain, "arc_count": len(chain), "plan_length_m": distance[endpoint],
            "source_arc_xyz_m": [positions[arc_id] for arc_id in chain]}
    all_points = np.asarray([point for coordinates in positions.values() for point in coordinates]).reshape(-1, 3)
    return {"schema": "td-ported-network-topology-v1", "metrics_status": "candidate_unverified", "verified": False,
        "coordinate_system": "source model metres; x,z plan position, y source elevation",
        "source_identity_sha256": paths["source_identity_sha256"],
        "source_terrain": {key: paths.get(key) for key in ("grid_shape", "origin_m_xz", "spacing_m")},
        "geometry_bounds_xyz_m": [all_points.min(axis=0).tolist(), all_points.max(axis=0).tolist()] if len(all_points) else None,
        "arc_count": len(owners), "component_count": len(components), "components": components,
        "longest_directed_path": longest, "directed_cycle_arc_ids": cycle_arcs,
        "directed_transitions": {arc_id: sorted(successors) for arc_id, successors in directed.items()},
        "open_ports": [{key: port[key] for key in ("kind", "hub_node_id", "arc_id", "outer_node_id", "original_profile_xyz_m")}
            for port in open_ports], "open_port_count": len(open_ports),
        "no_node_only_connections": True, "fine_generated": False, "hydraulic_ready": False}
