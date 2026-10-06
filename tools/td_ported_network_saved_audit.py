"""Independent saved composition ports, selection conflicts and evidence graph."""

from collections import defaultdict, deque
import math

import numpy as np

from tools.audit_td_source_conforming_banks_v3 import require
from tools.td_ported_junction_saved_audit_v2 import audit_mesh


def compare(saved, actual, context):
    if isinstance(actual, dict):
        require(isinstance(saved, dict) and set(saved) == set(actual), context + " keys differ")
        for key in actual:
            compare(saved[key], actual[key], context + "/" + str(key))
    elif isinstance(actual, (list, tuple)):
        require(isinstance(saved, (list, tuple)) and len(saved) == len(actual), context + " length differs")
        for left, right in zip(saved, actual):
            compare(left, right, context)
    elif isinstance(actual, float):
        require(isinstance(saved, (float, int)) and not isinstance(saved, bool)
                and math.isfinite(saved) and math.isfinite(actual)
                and abs(saved-actual) <= 1e-9, context + " numerical value differs")
    else:
        require(type(saved) is type(actual) and saved == actual, context + " value differs")


def census_hubs(paths, sections):
    incident = defaultdict(list)
    for arc in paths["arcs"]:
        if arc["kind"] == "land_channel":
            for node in arc["node_ids"]:
                incident[node].append(arc["arc_id"])
    profiles = {item["node_id"]: item for item in sections["node_sections"]}
    rows = []
    for node, arcs in incident.items():
        if len(arcs) != 3:
            continue
        profile = profiles.get(node, {})
        flow = float(profile.get("representative_q_m3_s", 0.))
        require(math.isfinite(flow) and flow >= 0., "invalid original hub Q")
        rows.append(dict(hub_node_id=node, ordinary_q_m3_s=flow, incident_arc_ids=sorted(arcs),
                         anchor=bool(profile.get("anchor", False)),
                         parent_rejection_reasons=list(profile.get("rejection_reasons", []))))
    require(len(rows) <= 256, "complete census exceeds resource budget")
    return sorted(rows, key=lambda row: (-row["ordinary_q_m3_s"], row["hub_node_id"]))


def pair_key(pair):
    return tuple(sorted(tuple(point) for point in np.asarray(pair, float)[:, [0, 2]]))


def port_id(port):
    return tuple(port[key] for key in ("kind", "hub_node_id", "arc_id", "outer_node_id"))


def old_ports(sections):
    mesh, result = sections["mesh"], []
    for section_index, section in enumerate(sections["edge_sections"]):
        incidence = defaultdict(list)
        for triangle_index in section["triangle_indices"]:
            indices = mesh["triangles"][triangle_index]
            require(mesh["triangle_arc_ids"][triangle_index] == section["arc_id"], "original section triangle owner differs")
            for edge_index in range(3):
                pair = [mesh["vertices_xyz_m"][indices[edge_index]],
                        mesh["vertices_xyz_m"][indices[(edge_index+1)%3]]]
                incidence[pair_key(pair)].append(dict(triangle_index=triangle_index,
                                                     edge_index=edge_index, points_xyz_m=pair))
        for profile_index, (node_id, profile) in enumerate(zip(section["node_ids"], section["cross_section_xyz_m"])):
            if len(profile) != 4:
                continue
            segments = []
            for number in range(3):
                pair = profile[number:number+2]
                sides = incidence.get(pair_key(pair), [])
                if len(sides) != 1 or sides[0]["points_xyz_m"] not in (pair, pair[::-1]):
                    break
                segments.append(dict(points_xyz_m=pair, profile_segment_index=number, pieces=[dict(
                    interval_t01=[0., 1.], start_xz_m=[pair[0][0], pair[0][2]],
                    end_xz_m=[pair[1][0], pair[1][2]],
                    bed_coefficients_m_t012=[pair[0][1], pair[1][1]-pair[0][1], 0.],
                    source_coefficients_m_t012=None, segment_id=None,
                    side=dict(kind="legacy06", **sides[0]))]))
            if len(segments) == 3:
                result.append(dict(kind="legacy06", hub_node_id=None, arc_id=section["arc_id"],
                                   outer_node_id=node_id, original_profile_xyz_m=profile,
                                   section_index=section_index, profile_index=profile_index, segments=segments))
    return result


def new_ports(record):
    edges = {item["segment_id"]: item for item in record["edge_proofs"]}
    arms = {item["arc_id"]: item for item in record["arms"]}
    result = []
    for proof in record["port_proofs"]:
        if proof["kind"] != "outer_port_proof":
            continue
        arm, segments = arms[proof["arc_id"]], []
        for segment in proof["profile_segments"]:
            pieces = []
            for reference in segment["native_pieces"]:
                edge = edges[reference["segment_id"]]
                sides = [side for side in edge["sides"] if side["triangle_id"].startswith("junction:")]
                require(len(sides) == 1, "external port lacks unique actual patch side")
                side = sides[0]
                triangle_index = int(side["triangle_id"].split(":")[1])
                indices = record["geometry"]["triangles"][triangle_index]
                pair = [record["geometry"]["vertices_xyz_m"][indices[side["edge_index"]]],
                        record["geometry"]["vertices_xyz_m"][indices[(side["edge_index"]+1)%3]]]
                require(pair == side["points_xyz_m"], "saved port is not actual triangle boundary")
                source, depth = edge["source"]["source_coefficients_m_t012"], edge["depth_coefficients_m_t01"]
                pieces.append(dict(interval_t01=reference["interval_t01"], start_xz_m=edge["start_xz_m"],
                    end_xz_m=edge["end_xz_m"], bed_coefficients_m_t012=[source[0]-depth[0], source[1]-depth[1], source[2]],
                    source_coefficients_m_t012=source, segment_id=edge["segment_id"],
                    common_function_identity_sha256=edge["common_function_identity_sha256"],
                    side=dict(kind="junction", hub_node_id=record["hub_node_id"],
                              triangle_index=triangle_index, edge_index=side["edge_index"], points_xyz_m=pair)))
            segments.append(dict(points_xyz_m=segment["points_xyz_m"],
                                 profile_segment_index=segment["profile_segment_index"], pieces=pieces))
        result.append(dict(kind="junction", hub_node_id=record["hub_node_id"], arc_id=arm["arc_id"],
                           outer_node_id=arm["outer_node_id"], original_profile_xyz_m=arm["outer_profile_xyz_m"],
                           outer_section_index=arm["outer_section_index"], attachment_status=arm["attachment_status"], segments=segments))
    require(len(result) == 3, "three full external ports required")
    return result


def coordinates(piece, pair):
    start, end = np.asarray(pair, float)[:, [0, 2]]
    vector = end-start
    denominator = float(vector@vector)
    require(denominator > 0., "degenerate profile segment")
    offsets = np.asarray([piece["start_xz_m"], piece["end_xz_m"]])-start
    distances = np.abs(offsets[:, 0]*vector[1]-offsets[:, 1]*vector[0])/math.sqrt(denominator)
    require(float(distances.max()) <= 1e-9, "native piece off original section")
    parameters = offsets@vector/denominator
    require(parameters.min() >= -1e-9 and parameters.max() <= 1.+1e-9, "native piece outside original whole section")
    return parameters.tolist()


def polynomial_on_interval(coefficients, parameters, interval):
    first, last = parameters
    require(abs(last-first) > 1e-14, "empty native interval")
    offset, scale = (interval[0]-first)/(last-first), (interval[1]-interval[0])/(last-first)
    constant, linear, quadratic = coefficients
    return [constant+linear*offset+quadratic*offset**2,
            scale*(linear+2.*quadratic*offset), quadratic*scale**2]


def match_ports(first, second):
    profile, other = first["original_profile_xyz_m"], second["original_profile_xyz_m"]
    if first["outer_node_id"] != second["outer_node_id"] or other not in (profile, profile[::-1]):
        return None, "original_four_point_section_mismatch"
    output = []
    try:
        for number in range(3):
            pair = profile[number:number+2]
            groups = []
            for segment in (first["segments"][number], second["segments"][number if other == profile else 2-number]):
                group = [(piece, coordinates(piece, pair)) for piece in segment["pieces"]]
                intervals = sorted(sorted(parameters) for piece, parameters in group)
                require(intervals and abs(intervals[0][0]) <= 1e-9 and abs(intervals[-1][1]-1.) <= 1e-9,
                        "native interval incomplete")
                require(all(abs(left[1]-right[0]) <= 1e-9 for left, right in zip(intervals, intervals[1:])),
                        "native interval gap or overlap")
                groups.append(group)
            knots = sorted({0., 1.} | {value for group in groups for piece, parameters in group for value in parameters})
            for low, high in zip(knots, knots[1:]):
                if high-low <= 1e-14:
                    continue
                midpoint = (low+high)/2.
                selected = []
                for group in groups:
                    matches = [(piece, parameters) for piece, parameters in group if min(parameters)-1e-12 <= midpoint <= max(parameters)+1e-12]
                    require(len(matches) == 1, "native interval ambiguous")
                    selected.append(matches[0])
                (left, left_coordinates), (right, right_coordinates) = selected
                require(left["side"]["points_xyz_m"] == right["side"]["points_xyz_m"][::-1], "actual boundary edges not reverse")
                whole = [polynomial_on_interval(piece["bed_coefficients_m_t012"], parameters, [low, high])
                         for piece, parameters in selected]
                differences = (np.asarray(whole[0])-whole[1]).tolist()
                require(max(abs(value) for value in differences) <= 1e-9, "whole native bed coefficient mismatch")
                source_difference = None
                if all(piece["source_coefficients_m_t012"] is not None for piece, parameters in selected):
                    source = [polynomial_on_interval(piece["source_coefficients_m_t012"], parameters, [low, high])
                              for piece, parameters in selected]
                    source_difference = (np.asarray(source[0])-source[1]).tolist()
                    require(max(abs(value) for value in source_difference) <= 1e-9, "whole native source coefficient mismatch")
                start, end = np.asarray(pair)[:, [0, 2]]
                output.append(dict(profile_segment_index=number, interval_t01=[low, high],
                    start_xz_m=(start+(end-start)*low).tolist(), end_xz_m=(start+(end-start)*high).tolist(),
                    first_segment_id=left["segment_id"], second_segment_id=right["segment_id"],
                    first_side=left["side"], second_side=right["side"], reverse_seam=True,
                    whole_bed_coefficients_m_t012=whole, difference_coefficients_m_t012=differences,
                    source_difference_coefficients_m_t012=source_difference))
    except ValueError as error:
        return None, str(error)
    return dict(kind="complete_original_section_reverse_function_seam", first_hub=first["hub_node_id"],
                second_hub=second["hub_node_id"], first_arc=first["arc_id"], second_arc=second["arc_id"],
                first_kind=first["kind"], second_kind=second["kind"], outer_node_id=first["outer_node_id"],
                original_profile_xyz_m=profile, native_pieces=output, verified=False), None


def cross_plan(first, second):
    return float(first[0]*second[1]-first[1]*second[0])


def overlap_area(first, second):
    clip = np.asarray(second, float)-np.asarray(first[0], float)
    polygon = np.asarray(first, float)-first[0]
    signed = cross_plan(clip[1]-clip[0], clip[2]-clip[0])
    if signed < 0.:
        clip = clip[::-1]
    for start, end in zip(clip, np.roll(clip, -1, axis=0)):
        if len(polygon) == 0:
            return 0.
        output = []
        direction = end-start
        for previous, current in zip(np.roll(polygon, 1, axis=0), polygon):
            previous_distance = cross_plan(direction, previous-start)
            current_distance = cross_plan(direction, current-start)
            if (previous_distance >= 0.) != (current_distance >= 0.):
                fraction = previous_distance/(previous_distance-current_distance)
                output.append(previous+(current-previous)*fraction)
            if current_distance >= 0.:
                output.append(current)
        polygon = np.asarray(output, float)
    return abs(math.fsum(cross_plan(start, end) for start, end in zip(polygon, np.roll(polygon, -1, axis=0))))/2.


def edge_contact(first, second):
    first, second = np.asarray(first)[:, [0, 2]], np.asarray(second)[:, [0, 2]]
    vector = first[1]-first[0]
    length = float(np.linalg.norm(vector))
    if length <= 1e-12:
        return False
    offsets = second-first[0]
    if np.max(np.abs(offsets[:, 0]*vector[1]-offsets[:, 1]*vector[0])) > 1e-9*length:
        return False
    parameters = sorted((offsets@vector/(length*length)).tolist())
    return min(1., parameters[1])-max(0., parameters[0]) > 1e-10


class SelectionAudit:
    def __init__(self, sections):
        self.vertices = list(sections["mesh"]["vertices_xyz_m"])
        self.triangles = list(sections["mesh"]["triangles"])
        self.origins = [dict(kind="legacy06", triangle_index=number, arc_id=arc)
                        for number, arc in enumerate(sections["mesh"]["triangle_arc_ids"])]
        self.owners = {arc: dict(kind="legacy06") for arc in sections["mesh"]["triangle_arc_ids"]}
        self.ports = old_ports(sections)
        self.connections, self.closed = [], set()
        self.accepted = []
        for number, first in enumerate(self.ports):
            for second in self.ports[number+1:]:
                if first["outer_node_id"] != second["outer_node_id"] or first["arc_id"] == second["arc_id"]:
                    continue
                seam, reason = match_ports(first, second)
                if reason is None:
                    require(port_id(first) not in self.closed and port_id(second) not in self.closed, "original port has more than two incident strips")
                    self.connections.append(seam)
                    self.closed.update((port_id(first), port_id(second)))
        self.refresh()

    def refresh(self):
        points = np.asarray(self.vertices, float).reshape(-1, 3)
        self.shapes = points[np.asarray(self.triangles, int).reshape(-1, 3)][:, :, [0, 2]]
        self.low = self.shapes.min(axis=1) if len(self.shapes) else np.empty((0, 2))
        self.high = self.shapes.max(axis=1) if len(self.shapes) else np.empty((0, 2))

    def conflicts(self, record, seams):
        allowed = {pair_key(seam["original_profile_xyz_m"][number:number+2]) for seam in seams for number in range(3)}
        mesh = record["geometry"]
        shapes = np.asarray(mesh["vertices_xyz_m"], float)[np.asarray(mesh["triangles"], int)][:, :, [0, 2]]
        reasons, witnesses, pending = set(), [], defaultdict(list)
        for number, shape in enumerate(shapes):
            if cross_plan(shape[1]-shape[0], shape[2]-shape[0]) <= 1e-10:
                reasons.add("degenerate_or_reversed_triangle")
            indices = mesh["triangles"][number]
            pairs = [[mesh["vertices_xyz_m"][indices[edge]], mesh["vertices_xyz_m"][indices[(edge+1)%3]]] for edge in range(3)]
            for pair in pairs:
                pending[pair_key(pair)].append(pair)
            nearby = np.flatnonzero(np.all(self.high >= shape.min(axis=0)-1e-9, axis=1)
                                    & np.all(self.low <= shape.max(axis=0)+1e-9, axis=1))
            for old_number in nearby:
                if overlap_area(shape, self.shapes[old_number]) > 1e-8:
                    reasons.add("positive_projected_overlap")
                    if len(witnesses) < 32:
                        witnesses.append(dict(new_triangle_index=number, existing_face_index=int(old_number), kind="positive_projected_overlap"))
                old_indices = self.triangles[old_number]
                for edge in range(3):
                    old_pair = [self.vertices[old_indices[edge]], self.vertices[old_indices[(edge+1)%3]]]
                    for pair in pairs:
                        if edge_contact(pair, old_pair) and (pair_key(pair) != pair_key(old_pair)
                                or pair_key(pair) not in allowed or pair != old_pair[::-1]):
                            reasons.add("partial_unbound_or_wrong_direction_edge_contact")
            for other in shapes[number+1:]:
                if overlap_area(shape, other) > 1e-8:
                    reasons.add("internal_positive_projected_overlap")
        for indices in self.triangles:
            for edge in range(3):
                pair = [self.vertices[indices[edge]], self.vertices[indices[(edge+1)%3]]]
                key = pair_key(pair)
                if key in pending:
                    pending[key].append(pair)
        for pairs in pending.values():
            if len(pairs) > 2 or len(pairs) == 2 and pairs[0] != pairs[1][::-1]:
                reasons.add("nonmanifold_or_same_direction_seam")
        return reasons, witnesses

    def consider(self, record):
        requested = record["requested_replacement_arc_ids"]
        reasons = set()
        if len(requested) != 3 or len(set(requested)) != 3 or any(arc in self.owners for arc in requested):
            reasons.add("duplicate_or_existing_incident_arc")
        ports, seams = new_ports(record), []
        for port in ports:
            for existing in self.ports:
                if existing["outer_node_id"] != port["outer_node_id"]:
                    continue
                seam, reason = match_ports(port, existing)
                if reason is not None:
                    reasons.add("shared_port_"+reason)
                elif port_id(existing) in self.closed:
                    reasons.add("shared_port_already_has_two_sides")
                else:
                    seams.append(seam)
            if port["attachment_status"] == "actual_old_mesh" and not any(
                    seam["first_arc"] == port["arc_id"] and seam["second_kind"] == "legacy06" for seam in seams):
                reasons.add("claimed_old_attachment_without_complete_reverse_seam")
        conflicts, witnesses = self.conflicts(record, seams)
        reasons.update(conflicts)
        if reasons:
            return sorted(reasons), witnesses
        audit_mesh(record["geometry"]["vertices_xyz_m"], record["geometry"]["triangles"])
        offset = len(self.vertices)
        self.vertices.extend(record["geometry"]["vertices_xyz_m"])
        self.triangles.extend([[offset+index for index in indices] for indices in record["geometry"]["triangles"]])
        self.origins.extend(dict(kind="junction", hub_node_id=record["hub_node_id"], triangle_index=number, role=role)
                            for number, role in enumerate(record["geometry"]["triangle_roles"]))
        for arc in requested:
            self.owners[arc] = dict(kind="junction", hub_node_id=record["hub_node_id"])
        self.connections.extend(seams)
        for seam in seams:
            self.closed.update((tuple(seam[key] for key in ("first_kind", "first_hub", "first_arc", "outer_node_id")),
                                tuple(seam[key] for key in ("second_kind", "second_hub", "second_arc", "outer_node_id"))))
        self.connections.append(dict(kind="complete_three_arm_inner_ring", hub_node_id=record["hub_node_id"],
            arc_ids=requested, port_proof_identities=[proof["identity_sha256"] for proof in record["port_proofs"]
                                                    if proof["kind"] == "inner_port_proof"], verified=False))
        self.ports.extend(ports)
        self.accepted.append(record["hub_node_id"])
        self.refresh()
        return [], witnesses


def topology(paths, sections, selection):
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
    for section in sections["edge_sections"]:
        if section["arc_id"] not in arcs:
            arcs[section["arc_id"]] = dict(node_ids=section["node_ids"],
                xyz_m=[np.mean(np.asarray(profile, float), axis=0).tolist() for profile in section["cross_section_xyz_m"]])
    owners = selection.owners
    adjacency, directed = {arc: set() for arc in owners}, {arc: set() for arc in owners}
    for seam in selection.connections:
        if seam["kind"] == "complete_three_arm_inner_ring":
            identifiers = seam["arc_ids"]
            pairs = [(first, second, seam["hub_node_id"]) for number, first in enumerate(identifiers) for second in identifiers[number+1:]]
        else:
            pairs = [(seam["first_arc"], seam["second_arc"], seam["outer_node_id"])]
        for first, second, node in pairs:
            adjacency[first].add(second)
            adjacency[second].add(first)
            for incoming, outgoing in ((first, second), (second, first)):
                if arcs[incoming]["node_ids"][-1] == node and arcs[outgoing]["node_ids"][0] == node:
                    directed[incoming].add(outgoing)
    positions, lengths = {}, {}
    for arc in owners:
        coordinates_xyz = arcs[arc].get("xyz_m")
        if coordinates_xyz is None:
            coordinates_xyz = [nodes[node]["xyz_m"] for node in arcs[arc]["node_ids"]]
        positions[arc] = coordinates_xyz
        lengths[arc] = float(np.linalg.norm(np.diff(np.asarray(coordinates_xyz)[:, [0, 2]], axis=0), axis=1).sum())
    components, visited = [], set()
    for root in sorted(owners):
        if root in visited:
            continue
        stack, members = [root], []
        visited.add(root)
        while stack:
            current = stack.pop()
            members.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        points = np.asarray([point for arc in members for point in positions[arc]])
        components.append(dict(component_id=len(components), arc_ids=sorted(members), arc_count=len(members),
                               total_plan_length_m=math.fsum(lengths[arc] for arc in members),
                               bounds_xyz_m=[points.min(axis=0).tolist(), points.max(axis=0).tolist()]))
    indegree = dict.fromkeys(owners, 0)
    for successors in directed.values():
        for successor in successors:
            indegree[successor] += 1
    queue = deque(sorted(arc for arc in owners if indegree[arc] == 0))
    distance, predecessor = dict(lengths), {}
    while queue:
        current = queue.popleft()
        for successor in sorted(directed[current]):
            proposed = distance[current]+lengths[successor]
            if proposed > distance[successor]:
                distance[successor], predecessor[successor] = proposed, current
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    cycle = sorted(arc for arc in owners if indegree[arc])
    longest = None
    if owners and not cycle:
        endpoint = max(sorted(owners), key=lambda arc: distance[arc])
        chain = [endpoint]
        while chain[-1] in predecessor:
            chain.append(predecessor[chain[-1]])
        chain.reverse()
        longest = dict(arc_ids=chain, arc_count=len(chain), plan_length_m=distance[endpoint],
                       source_arc_xyz_m=[positions[arc] for arc in chain])
    points = np.asarray([point for coordinates_xyz in positions.values() for point in coordinates_xyz]).reshape(-1, 3)
    open_ports = [{key: port[key] for key in ("kind", "hub_node_id", "arc_id", "outer_node_id", "original_profile_xyz_m")}
                  for port in selection.ports if port_id(port) not in selection.closed]
    return dict(schema="td-ported-network-topology-v1", metrics_status="candidate_unverified", verified=False,
                coordinate_system="source model metres; x,z plan position, y source elevation",
                source_identity_sha256=paths["source_identity_sha256"],
                source_terrain={key: paths.get(key) for key in ("grid_shape", "origin_m_xz", "spacing_m")},
                geometry_bounds_xyz_m=[points.min(axis=0).tolist(), points.max(axis=0).tolist()] if len(points) else None,
                arc_count=len(owners), component_count=len(components), components=components,
                longest_directed_path=longest, directed_cycle_arc_ids=cycle,
                directed_transitions={arc: sorted(successors) for arc, successors in directed.items()},
                open_ports=open_ports, open_port_count=len(open_ports), no_node_only_connections=True,
                fine_generated=False, hydraulic_ready=False)
