"""Independent saved-reference connectivity inspection, not a hydraulic audit."""

from collections import Counter, defaultdict, deque
import math
from pathlib import Path
import sys
import time

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_td_watershed_inspection import (
    ROOT, encoded, parser, publish_directory, read_json_pin, require, unique)


INSPECTION = ROOT / "verification/natural-river-network/watershed-inspection-export-20261006-01/review.json"
INSPECTION_SHA = "db7a511457cc14291e9f01f82414cc5a2443c1cb55ae710fbdfe6ddb69a93ee9"
MAX_RSS_BYTES = 1024**3


def check_memory():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, "peak_wset", memory.rss))
    require(peak <= MAX_RSS_BYTES, "connectivity inspection exceeds 1GiB RSS budget")
    return peak


def components(adjacency):
    remaining = set(adjacency)
    result = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        members = []
        pending = [seed]
        while pending:
            member = pending.pop()
            members.append(member)
            for neighbor in sorted(adjacency[member]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    pending.append(neighbor)
        result.append(sorted(members))
    return sorted(result, key=lambda members: (-len(members), members[0]))


def arc_length(arc):
    return sum(math.hypot(second[0]-first[0], second[2]-first[2])
               for first, second in zip(arc["xyz_m"], arc["xyz_m"][1:]))


def profile_port(edge, endpoint, mesh, sections):
    node = edge["node_ids"][endpoint]
    profile = edge["cross_section_xyz_m"][endpoint]
    indices = mesh["node_vertex_indices"].get(node, [])
    reasons = []
    if len(profile) != 4 or len(indices) != 4:
        return {"node_id": node, "valid": False, "reasons": ["missing_complete_four_point_profile"]}
    if profile != sections[node]["cross_section_xyz_m"] or profile != [mesh["vertices_xyz_m"][index] for index in indices]:
        reasons.append("saved_profile_not_exactly_equal")
    incidence = defaultdict(list)
    for index in edge["triangle_indices"]:
        require(0 <= index < len(mesh["triangles"]) and mesh["triangle_arc_ids"][index] == edge["arc_id"],
                "invalid saved triangle ownership")
        triangle = mesh["triangles"][index]
        require(all(type(vertex) is int and 0 <= vertex < len(mesh["vertices_xyz_m"]) for vertex in triangle),
                "invalid saved vertex reference")
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            incidence[tuple(sorted((first, second)))].append([first, second])
    boundary = []
    for first, second in zip(indices, indices[1:]):
        directions = incidence[tuple(sorted((first, second)))]
        if len(directions) != 1:
            reasons.append("whole_profile_boundary_segment_not_covered_once")
        else:
            boundary.append(directions[0])
    return {"node_id": node, "valid": not reasons, "reasons": sorted(set(reasons)),
            "profile_xyz_m": profile, "vertex_indices": indices, "boundary_directed_segments": boundary}


def joins(first, second, ports, sections):
    left, right = ports[first][1], ports[second][0]
    if left["node_id"] != right["node_id"]:
        return False
    node = left["node_id"]
    if sections[node]["junction"] or sections[node]["rejection_reasons"]:
        return False
    return (left["valid"] and right["valid"] and left["profile_xyz_m"] == right["profile_xyz_m"]
            and left["vertex_indices"] == right["vertex_indices"]
            and left["boundary_directed_segments"] == [segment[::-1] for segment in right["boundary_directed_segments"]])


def maximal_chains(keys, successors, predecessors):
    chains = []
    for start in sorted(keys):
        if predecessors[start]:
            continue
        chain = []
        current = start
        seen = set()
        while current is not None:
            require(current not in seen, "cycle in saved chain")
            seen.add(current)
            chain.append(current)
            next_arcs = successors[current]
            require(len(next_arcs) <= 1, "ambiguous native downstream continuation")
            current = next_arcs[0] if next_arcs else None
        chains.append(chain)
    require(set(key for chain in chains for key in chain) == set(keys), "cycle or missing chain coverage")
    return chains


def chain_record(chain, arcs, diagnostics, edges, ports, proof):
    nodes = list(arcs[chain[0]]["node_ids"])
    for key in chain[1:]:
        require(nodes[-1] == arcs[key]["node_ids"][0], "chain missing node attachment")
        nodes.extend(arcs[key]["node_ids"][1:])
    xyz = list(arcs[chain[0]]["xyz_m"])
    for key in chain[1:]:
        xyz.extend(arcs[key]["xyz_m"][1:])
    quantities = [diagnostics[key]["representative_q_m3_s"] for key in chain]
    return {"semantics": proof, "actual_arc_ids": chain, "node_ids": nodes,
            "source_xyz_m": xyz, "xz_m": [[point[0], point[2]] for point in xyz],
            "edge_count": len(chain), "xz_length_m": sum(arc_length(arcs[key]) for key in chain),
            "peak_ordinary_mean_q_proxy_m3_s": max(quantities),
            "downstream_ordinary_mean_q_proxy_m3_s": quantities[-1],
            "q_semantics": "uncalibrated prior; not measured or instantaneous discharge",
            "triangle_indices": [index for key in chain for index in edges[key]["triangle_indices"]],
            "whole_profile_ports_verified": proof == "saved_whole_profile_strip_chain",
            "downstream_port": ports[chain[-1]][1], "hydraulic_ready": False,
            "whole_network_bank_continuity_certified": False}


def investigate(paths, saved, inspection):
    nodes = unique(paths["nodes"], "node_id")
    arcs = unique(paths["arcs"], "arc_id")
    sections = unique(saved["node_sections"], "node_id")
    edges = unique(saved["edge_sections"], "arc_id")
    diagnostics = unique(saved["reach_diagnostics"], "arc_id")
    mesh = saved["mesh"]
    require(inspection["schema"] == "td-watershed-inspection-v1", "unsupported inspection schema")
    require(inspection["layers"]["nodes"] == paths["nodes"]
            and inspection["layers"]["saved_bed_mesh"] == mesh
            and inspection["layers"]["constructible_edges"] == saved["edge_sections"]
            and inspection["reach_diagnostics"] == saved["reach_diagnostics"]
            and inspection["layers"]["support_arcs"] == saved["support_arcs"]
            and inspection["layers"]["receiver_candidates"] == [arc for arc in paths["arcs"] if arc["channel_candidate"]]
            and inspection["layers"]["lakes"] == paths["lakes"], "export/source layer mismatch")
    require(saved["composite_parent_identity"]["paths"] == paths["identity_sha256"], "section path parent mismatch")
    require(set(edges) == {key for key, record in diagnostics.items() if record["status"] == "geometry_candidate"},
            "accepted edge/diagnostics mismatch")
    require(set(diagnostics) == {key for key, arc in arcs.items() if arc["channel_candidate"]}, "candidate coverage mismatch")
    incoming, outgoing = defaultdict(list), defaultdict(list)
    candidate_in, candidate_out = defaultdict(list), defaultdict(list)
    node_graph = defaultdict(set)
    ports = {}
    triangle_refs = []
    for key, edge in sorted(edges.items()):
        check_memory()
        require(arcs[key]["kind"] == "land_channel" and edge["node_ids"] == arcs[key]["node_ids"], "nonland constructible edge")
        require(len(edge["node_ids"]) == 2, "unsupported multi-port saved strip")
        require(all(node in nodes for node in edge["node_ids"]), "missing strip node")
        require(arcs[key]["xyz_m"] == [nodes[node]["xyz_m"] for node in edge["node_ids"]], "arc/source XYZ mismatch")
        ports[key] = [profile_port(edge, endpoint, mesh, sections) for endpoint in (0, 1)]
        triangle_refs.extend(edge["triangle_indices"])
        for first, second in zip(edge["node_ids"], edge["node_ids"][1:]):
            outgoing[first].append(key)
            incoming[second].append(key)
            node_graph[first].add(second)
            node_graph[second].add(first)
    require(sorted(triangle_refs) == list(range(len(mesh["triangles"]))), "saved triangles missing or duplicated")
    for key in diagnostics:
        for first, second in zip(arcs[key]["node_ids"], arcs[key]["node_ids"][1:]):
            candidate_out[first].append(key)
            candidate_in[second].append(key)
    require(all(len(keys) == 1 for keys in candidate_out.values()), "ambiguous native receiver graph")
    indegree = {node: len(incoming[node]) for node in node_graph}
    queue = deque(sorted(node for node, count in indegree.items() if count == 0))
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for key in outgoing[node]:
            target = arcs[key]["node_ids"][-1]
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    require(visited == len(node_graph), "cycle in saved constructible graph")
    weak_components = []
    for members in components(node_graph):
        keys = sorted({key for node in members for key in outgoing[node]})
        weak_components.append({"node_count": len(members), "edge_count": len(keys), "actual_arc_ids": keys,
                                "xz_length_m": sum(arc_length(arcs[key]) for key in keys)})
    strict_graph = {key: set() for key in edges}
    strict_next, strict_previous = defaultdict(list), defaultdict(list)
    topological_next, topological_previous = defaultdict(list), defaultdict(list)
    transition_gaps = []
    turns = []
    for node in sorted(set(candidate_in) & set(candidate_out)):
        gaps = []
        turn_pairs = []
        for first in candidate_in[node]:
            for second in candidate_out[node]:
                points = arcs[first]["xyz_m"]
                next_points = arcs[second]["xyz_m"]
                direction = [points[-1][axis]-points[-2][axis] for axis in (0, 2)]
                next_direction = [next_points[1][axis]-next_points[0][axis] for axis in (0, 2)]
                turn = direction != next_direction
                available = first in edges and second in edges
                complete = available and joins(first, second, ports, sections)
                if available:
                    topological_next[first].append(second)
                    topological_previous[second].append(first)
                if complete:
                    strict_graph[first].add(second)
                    strict_graph[second].add(first)
                    strict_next[first].append(second)
                    strict_previous[second].append(first)
                else:
                    reasons = sorted(set(diagnostics[first]["rejection_reasons"] + diagnostics[second]["rejection_reasons"]))
                    gaps.append({"incoming_arc_id": first, "outgoing_arc_id": second,
                                 "missing_saved_strip_arc_ids": [key for key in (first, second) if key not in edges],
                                 "rejection_reasons": reasons,
                                 "whole_profile_port_gap": available, "turn": turn})
                if turn:
                    turn_pairs.append({"incoming_arc_id": first, "outgoing_arc_id": second,
                                       "whole_profile_connected": complete})
        if gaps:
            transition_gaps.append({"node_id": node, "xyz_m": nodes[node]["xyz_m"], "gaps": gaps})
        if turn_pairs:
            turns.append({"node_id": node, "pairs": turn_pairs})
    strict_components = [{"edge_count": len(keys), "actual_arc_ids": keys,
                          "xz_length_m": sum(arc_length(arcs[key]) for key in keys)} for keys in components(strict_graph)]
    missing_ports = [{"node_id": node, "candidate_incident_arc_ids": sorted(candidate_in[node]+candidate_out[node]),
                      "section_rejection_reasons": sections[node]["rejection_reasons"]}
                     for node in sorted(set(candidate_in) | set(candidate_out))
                     if node not in mesh["node_vertex_indices"] or len(mesh["node_vertex_indices"][node]) != 4]
    junctions = [{"node_id": node, "xyz_m": nodes[node]["xyz_m"],
                  "incident_candidate_arc_ids": sorted(candidate_in[node]+candidate_out[node])}
                 for node, section in sorted(sections.items()) if "needs_junction_patch" in section["rejection_reasons"]]
    interfaces = []
    for lake in paths["lakes"]:
        for interface in lake["entry_interfaces"]:
            key = interface["support_arc_id"]
            land = interface["land_node_id"]
            wet = interface["wet_node_id"]
            require(arcs[key]["node_ids"] == [land, wet], "saved lake interface mismatch")
            approaches = incoming[land]
            interfaces.append({"kind": "lake_entry", "leaf_id": lake["leaf_id"], "support_arc_id": key,
                               "last_interface_node_ids": [land, wet], "exact_interface_saved_geometry": key in edges,
                               "constructible_approach_arc_ids": approaches,
                               "complete_approach_ports": [key for key in approaches if ports[key][1]["valid"]],
                               "missing": "land_to_wet_transition_strip_and_lake_boundary_port",
                               "upstream_refused_arcs": [{"arc_id": key, "reasons": diagnostics[key]["rejection_reasons"]}
                                                         for key in candidate_in[land] if key not in edges]})
    for arc in saved["support_arcs"]:
        if arc["kind"] not in ("engineering_outlet_support", "cross_face", "downhill_terrain_approach"):
            continue
        last = arc["node_ids"][-2:]
        exact = [key for key, edge in edges.items() if len(last) == 2 and edge["node_ids"] == last]
        terminal = arc["node_ids"][-1]
        interfaces.append({"kind": arc["kind"], "support_arc_id": arc["arc_id"], "last_interface_node_ids": last,
                           "exact_interface_saved_geometry": bool(exact), "matching_geometry_arc_ids": exact,
                           "terminal_has_complete_profile": terminal in mesh["node_vertex_indices"]
                           and len(mesh["node_vertex_indices"][terminal]) == 4,
                           "missing": "explicit_engineering_boundary_port_no_saved_segment" if len(last) == 1
                           else "typed_support_last_segment_has_no_matching_bed_strip" if not exact else None})
    strict_chains = maximal_chains(edges, strict_next, strict_previous)
    topological_chains = maximal_chains(edges, topological_next, topological_previous)

    def ranking(chain):
        return (max(diagnostics[key]["representative_q_m3_s"] for key in chain),
                sum(arc_length(arcs[key]) for key in chain), tuple(chain))

    highest_q = max(strict_chains, key=ranking)
    longest = max(strict_chains, key=lambda chain: (sum(arc_length(arcs[key]) for key in chain), ranking(chain)))
    representatives = {"highest_q_maximal_saved_profile_chain": chain_record(highest_q, arcs, diagnostics, edges, ports,
                                                                           "saved_whole_profile_strip_chain"),
                       "longest_saved_profile_chain": chain_record(longest, arcs, diagnostics, edges, ports,
                                                                    "saved_whole_profile_strip_chain"),
                       "longest_topological_strip_chain": chain_record(max(topological_chains, key=lambda chain: (len(chain), ranking(chain))),
                                                                       arcs, diagnostics, edges, ports, "topological_strip_chain")}
    stops = []
    for name, chain in representatives.items():
        node = chain["node_ids"][-1]
        stops.append({"chain": name, "terminal_node_id": node,
                      "next_candidate_arcs": [{"arc_id": key, "saved_geometry_exists": key in edges,
                                               "rejection_reasons": diagnostics[key]["rejection_reasons"]}
                                              for key in candidate_out[node]],
                      "support_departures": [{"arc_id": arc["arc_id"], "kind": arc["kind"]}
                                             for arc in saved["support_arcs"] if arc["node_ids"][0] == node]})
    counts = {"constructible_land_edges": len(edges), "separate_support_arcs": len(saved["support_arcs"]),
              "node_shared_weak_components": len(weak_components), "whole_profile_strip_components": len(strict_components),
              "whole_profile_maximal_chains": len(strict_chains), "unpatched_junction_nodes": len(junctions),
              "junction_refused_edges": sum("needs_junction_patch" in record["rejection_reasons"] for record in diagnostics.values()),
              "turn_nodes": len(turns), "unconnected_turn_nodes": sum(any(not pair["whole_profile_connected"] for pair in turn["pairs"]) for turn in turns),
              "candidate_nodes_missing_complete_saved_port": len(missing_ports),
              "candidate_transition_gap_nodes": len(transition_gaps),
              "accepted_endpoint_invalid_ports": sum(not port["valid"] for pair in ports.values() for port in pair),
              "accepted_to_accepted_whole_profile_gap_pairs": sum(gap["whole_profile_port_gap"] for node in transition_gaps for gap in node["gaps"])}
    return {"schema": "td-watershed-connectivity-inspection-v1", "counts": counts,
            "rejection_reason_edge_counts_overlapping": dict(Counter(reason for record in diagnostics.values() for reason in record["rejection_reasons"])),
            "interface_counts": {kind: {"total": len(items), "missing_exact_geometry": sum(not item["exact_interface_saved_geometry"] for item in items)}
                                 for kind in sorted({item["kind"] for item in interfaces})
                                 for items in [[item for item in interfaces if item["kind"] == kind]]},
            "node_shared_weak_components": weak_components, "whole_profile_strip_components": strict_components,
            "unpatched_junctions": junctions, "turns": turns, "missing_ports": missing_ports,
            "candidate_transition_gaps": transition_gaps, "interfaces": interfaces,
            "representative_chains": representatives, "chain_stops": stops,
            "support_arc_ids_excluded_from_land_graph": [arc["arc_id"] for arc in saved["support_arcs"]],
            "semantics": {"weak_components": "shared-node topology only, not whole-bank continuity",
                          "whole_profile_join": "exact four XYZ points, same saved vertex IDs, all three profile boundary segments covered once by each strip with opposite winding; no rejected junction",
                          "chain": "source path annotations referencing only saved strip arcs/triangles; not a new river",
                          "scope": "independent read-only reference analysis; does not replace prior audit or certify hydraulics"},
            "next_steps": [
                {"missing": "needs_junction_patch", "action": "Use listed junction nodes/incident arc IDs to specify inlet/outlet four-point ports and a local bank patch; do not enable refused strips until a separately saved patch covers every port and passes overlap/manifold checks."},
                {"missing": "folded_or_degenerate_bank_geometry_and_turn_ports", "action": "Use listed turn nodes and rejection reasons to define nonfolding corner transition geometry; resolve sampled bank-below-bed and component/coverage refusals before producing a new saved candidate. No smoothing or fine DEM invented here."},
                {"missing": "anchor_cut_conflict_and_lake_entry", "action": "Specify a depth-to-zero land/lake transition at each listed land/wet interface and a compatible lake boundary profile; current support lines and maximum-stage masks supply no bed connection."},
                {"missing": "spill_and_engineering_ports", "action": "Save explicit spill inlet/outlet and engineering boundary sections/triangles. The single-node engineering support has no last segment or complete boundary profile and cannot close a trunk."},
                {"missing": "candidate_bed_slope_failed_and_native_coverage", "action": "Inspect the exact rejected arc reasons, native bank samples and coverage masks; source data or boundary constraints must change in a separate geometry task, not in a visualization adapter."}],
            "hydraulic_ready": False, "whole_network_bank_continuity_certified": False,
            "water_surface_generated": False, "solver_advanced": False, "bed_changed": False}


def markdown_report(report):
    lines = ["# Saved Watershed Connectivity Inspection", "", "Independent read-only saved-reference analysis; NOT a replacement for the previous audit.", "",
             "## Counts", ""]
    lines.extend(f"- {key}: {value}" for key, value in report["counts"].items())
    lines.extend(["", "## Last Interfaces", ""])
    lines.extend(f"- {key}: {value['missing_exact_geometry']} / {value['total']} lack exact saved geometry."
                 for key, value in report["interface_counts"].items())
    lines.extend(["", "## Representative Saved Chains", ""])
    for name, chain in report["representative_chains"].items():
        lines.append(f"- {name}: {chain['edge_count']} arcs, {chain['xz_length_m']:.1f} m XZ, peak ordinary mean Q prior {chain['peak_ordinary_mean_q_proxy_m3_s']:.6f} m3/s; {chain['semantics']}.")
    lines.extend(["", "## Why the Trunk Does Not Connect", "",
                  "Shared source nodes do not establish whole-bank continuity. Only exact complete four-point saved profiles and triangle boundary ports establish the local joins counted here.",
                  "Rejected junctions and missing land/lake/spill/engineering geometry break the route; support arcs never bridge these missing beds.", ""])
    for stop in report["chain_stops"]:
        lines.append(f"- {stop['chain']} ends at {stop['terminal_node_id']}; next candidates: {stop['next_candidate_arcs']}; support departures: {stop['support_departures']}.")
    lines.extend(["", "## Concrete Follow-Up Geometry Tasks", ""])
    lines.extend(f"- {item['missing']}: {item['action']}" for item in report["next_steps"])
    lines.extend(["", "## Renderer Overlay Contract", "",
                  "chains.json contains selected source-path annotations, actual_arc_ids and triangle_indices. Draw the saved XYZ polyline as an annotation on the original saved bed mesh; do not create tubes, widths, water or additional triangles.",
                  "All coordinates are absolute model meters (x east, y elevation, z south); Q is an uncalibrated prior. topological_strip_chain proves only shared-node topology; saved_whole_profile_strip_chain proves only local strip-port attachment, not whole-network banks or hydraulics.",
                  "Full per-node gaps, component memberships, arc IDs, interface evidence and output source pins are in report.json.", "", "## Resources", "",
                  f"Peak observed process RSS: {report['resource']['peak_rss_bytes']} bytes; budget 1073741824 bytes. Each output is limited to 64MiB. No solver, geometry generation or additional tests run.", ""])
    return "\n".join(lines).encode("utf-8")


def main():
    started = time.monotonic()
    arguments = parser(__doc__)
    arguments.add_argument("--inspection", type=Path, default=INSPECTION)
    arguments.add_argument("--inspection-sha256", default=INSPECTION_SHA)
    args = arguments.parse_args()
    index, index_pin = read_json_pin({"path": str(args.index.resolve()), "sha256": args.index_sha256}, ROOT)
    paths, paths_pin = read_json_pin(index["paths"], args.index.parent)
    sections, sections_pin = read_json_pin(index["sections"], args.index.parent)
    inspection, inspection_pin = read_json_pin({"path": str(args.inspection.resolve()), "sha256": args.inspection_sha256}, ROOT)
    require(inspection["pins"]["index"]["sha256"] == index_pin["sha256"]
            and inspection["pins"]["paths"]["sha256"] == paths_pin["sha256"]
            and inspection["pins"]["sections"]["sha256"] == sections_pin["sha256"], "inspection source pins differ")
    check_memory()
    report = investigate(paths, sections, inspection)
    report["pins"] = {"index": index_pin, "paths": paths_pin, "sections": sections_pin, "inspection": inspection_pin}
    report["resource"] = {"peak_rss_bytes": check_memory(), "max_rss_bytes": MAX_RSS_BYTES,
                          "max_artifact_bytes": 64*1024**2, "elapsed_s": time.monotonic()-started}
    overlay = {"schema": "td-watershed-saved-chain-overlay-v1", "pins": report["pins"],
               "coordinates": inspection["coordinates"], "chains": report["representative_chains"],
               "rendering": "annotation on existing saved mesh only; no fabricated river or hydraulic arrows",
               "hydraulic_ready": False, "water_surface_generated": False, "bed_changed": False}
    artifacts = {"report.json": encoded(report), "report.md": markdown_report(report), "chains.json": encoded(overlay)}
    check_memory()
    print(publish_directory(args.output, artifacts))
    print(report["counts"])
    print(report["interface_counts"])
    for name, chain in report["representative_chains"].items():
        print(name, chain["edge_count"], chain["xz_length_m"], chain["peak_ordinary_mean_q_proxy_m3_s"])


if __name__ == "__main__":
    main()
