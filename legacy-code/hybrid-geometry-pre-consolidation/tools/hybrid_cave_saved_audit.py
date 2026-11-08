"""Independent saved local solid, Boolean and air-path evidence primitives."""

from collections import defaultdict
from dataclasses import dataclass
import importlib.metadata
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, MAX_RSS, checked_path, check_identity, check_memory, compare,
    digest, file_sha256, read, read_audit, require)

MAX_VERTICES = 100000
MAX_FACES = 200000
MANIFOLD_DIRECTORY = ROOT / ".scratch/hybrid-river-network/python-deps"


def manifold_library():
    sys.path.insert(0, str(MANIFOLD_DIRECTORY))
    import manifold3d
    require(importlib.metadata.version("manifold3d") == "3.5.4", "frozen manifold3d 3.5.4 required")
    return manifold3d


@dataclass
class Solid:
    vertices: np.ndarray
    triangles: np.ndarray
    label: str = "saved solid"

    def __post_init__(self):
        self.vertices = np.asarray(self.vertices, dtype=np.float64)
        raw_faces = np.asarray(self.triangles)
        require(self.vertices.ndim == 2 and self.vertices.shape[1] == 3
                and 4 <= len(self.vertices) <= MAX_VERTICES and np.isfinite(self.vertices).all(), self.label + ": invalid vertices")
        require(raw_faces.ndim == 2 and raw_faces.shape[1] == 3 and np.issubdtype(raw_faces.dtype, np.integer)
                and 4 <= len(raw_faces) <= MAX_FACES and raw_faces.min() >= 0 and raw_faces.max() < len(self.vertices), self.label + ": invalid triangle references")
        self.triangles = raw_faces.astype(np.int64)
        require(len(set(map(tuple, np.sort(self.triangles, axis=1)))) == len(self.triangles), self.label + ": duplicate faces")
        require(len(np.unique(self.triangles)) == len(self.vertices), self.label + ": unreferenced vertices")
        self.points = self.vertices[self.triangles]
        self.normals = np.cross(self.points[:, 1]-self.points[:, 0], self.points[:, 2]-self.points[:, 0])
        require(np.all(np.linalg.norm(self.normals, axis=1) > 1e-14), self.label + ": degenerate faces")
        edges = defaultdict(list)
        for ordinal, face in enumerate(self.triangles):
            for first, second in zip(face, np.roll(face, -1)):
                require(first != second, self.label + ": repeated triangle vertex")
                edges[tuple(sorted((int(first), int(second))))].append((ordinal, int(first), int(second)))
        adjacency = defaultdict(set)
        for uses in edges.values():
            require(len(uses) == 2 and uses[0][1:] == uses[1][1:][::-1], self.label + ": boundary/nonmanifold or inconsistent orientation")
            adjacency[uses[0][0]].add(uses[1][0])
            adjacency[uses[1][0]].add(uses[0][0])
        remaining, components = set(range(len(self.triangles))), []
        while remaining:
            frontier, component = [remaining.pop()], []
            while frontier:
                face = frontier.pop()
                component.append(face)
                for neighbor in adjacency[face]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        frontier.append(neighbor)
            components.append(component)
        self.components = components
        self.edge_count = len(edges)
        anchor = self.vertices.mean(axis=0)
        local = self.points-anchor
        self.signed_volume = math.fsum((np.einsum("ij,ij->i", local[:, 0], np.cross(local[:, 1], local[:, 2]))/6).tolist())
        require(self.signed_volume > 0. and math.isfinite(self.signed_volume), self.label + ": nonpositive oriented volume")
        check_memory()

    def manifold(self, library):
        mesh = library.Mesh64(vert_properties=np.array(self.vertices, dtype=np.float64, order="C", copy=True),
                              tri_verts=np.array(self.triangles, dtype=np.uint64, order="C", copy=True))
        result = library.Manifold(mesh)
        require(result.status() == library.Error.NoError and not result.is_empty(), self.label + ": library rejects solid")
        compare(result.volume(), self.signed_volume, self.label + " signed/library volume", atol=1e-7, rtol=1e-9)
        return result

    def winding(self, point):
        offsets = self.points-np.asarray(point, float)
        lengths = np.linalg.norm(offsets, axis=2)
        require(np.all(lengths > 1e-12), self.label + ": air probe touches saved vertex")
        first, second, third = offsets[:, 0], offsets[:, 1], offsets[:, 2]
        numerator = np.einsum("ij,ij->i", first, np.cross(second, third))
        denominator = lengths.prod(axis=1)
        denominator += np.einsum("ij,ij->i", first, second)*lengths[:, 2]
        denominator += np.einsum("ij,ij->i", second, third)*lengths[:, 0]
        denominator += np.einsum("ij,ij->i", third, first)*lengths[:, 1]
        return math.fsum((2*np.arctan2(numerator, denominator)).tolist())/(4*math.pi)

    def segment_hits(self, first, second, endpoint_tolerance=1e-9):
        first, second = np.asarray(first, float), np.asarray(second, float)
        direction = second-first
        require(np.linalg.norm(direction) > 1e-12, "degenerate air-path segment")
        edge_first = self.points[:, 1]-self.points[:, 0]
        edge_second = self.points[:, 2]-self.points[:, 0]
        cross = np.cross(np.broadcast_to(direction, edge_second.shape), edge_second)
        determinant = np.einsum("ij,ij->i", edge_first, cross)
        active = np.abs(determinant) > 1e-12
        offsets = first-self.points[:, 0]
        inverse = np.zeros_like(determinant)
        inverse[active] = 1/determinant[active]
        weight_first = np.einsum("ij,ij->i", offsets, cross)*inverse
        auxiliary = np.cross(offsets, edge_first)
        weight_second = np.einsum("j,ij->i", direction, auxiliary)*inverse
        fraction = np.einsum("ij,ij->i", edge_second, auxiliary)*inverse
        hits = active & (weight_first >= -1e-10) & (weight_second >= -1e-10) & (weight_first+weight_second <= 1+1e-10)
        hits &= (fraction > endpoint_tolerance) & (fraction < 1-endpoint_tolerance)
        normal_lengths = np.linalg.norm(self.normals, axis=1)
        plane_first = np.einsum("ij,ij->i", offsets, self.normals)/normal_lengths
        plane_second = np.einsum("ij,ij->i", second-self.points[:, 0], self.normals)/normal_lengths
        coplanar = (~active) & (np.abs(plane_first) <= 1e-10) & (np.abs(plane_second) <= 1e-10)
        for ordinal in np.flatnonzero(coplanar):
            dropped = int(np.argmax(np.abs(self.normals[ordinal])))
            axes = [axis for axis in range(3) if axis != dropped]
            polygon = self.points[ordinal][:, axes]
            start, delta = first[axes], direction[axes]
            offset_first, offset_second = polygon[1]-polygon[0], polygon[2]-polygon[0]
            orientation = math.copysign(1., offset_first[0]*offset_second[1]-offset_first[1]*offset_second[0])
            lower, upper = endpoint_tolerance, 1-endpoint_tolerance
            for edge_start, edge_end in zip(polygon, np.roll(polygon, -1, axis=0)):
                edge, offset = edge_end-edge_start, start-edge_start
                constant = orientation*(edge[0]*offset[1]-edge[1]*offset[0])
                slope = orientation*(edge[0]*delta[1]-edge[1]*delta[0])
                if abs(slope) <= 1e-14:
                    if constant < -1e-10:
                        upper = -1.
                        break
                elif slope > 0.:
                    lower = max(lower, (-1e-10-constant)/slope)
                else:
                    upper = min(upper, (-1e-10-constant)/slope)
            hits[ordinal] = lower <= upper
        return np.flatnonzero(hits).tolist()


def boolean_evidence(rock, cutter, actual, saved_removed=None):
    library = manifold_library()
    source, void, saved = (solid.manifold(library) for solid in (rock, cutter, actual))
    expected = source-void
    removed = source ^ void
    require(expected.status() == library.Error.NoError and removed.status() == library.Error.NoError
            and not expected.is_empty() and not removed.is_empty(), "independent rock-minus-cave Boolean failed/empty")
    residual = (expected-saved).volume()+(saved-expected).volume()
    require(residual <= max(1e-7, source.volume()*1e-10), "saved actual rock differs from independent Boolean")
    compare(source.volume()-saved.volume(), removed.volume(), "actual excavated solid volume", atol=1e-7, rtol=1e-9)
    require(len(void.decompose()) == 1 and len(removed.decompose()) == 1, "cutter/actual excavated space disconnected")
    removed_residual = None
    if saved_removed is not None:
        supplied = saved_removed.manifold(library)
        removed_residual = (removed-supplied).volume()+(supplied-removed).volume()
        require(removed_residual <= max(1e-7, removed.volume()*1e-10), "saved removed solid differs from independent actual intersection")
    check_memory()
    return {"rock_volume_m3": source.volume(), "cutter_volume_m3": void.volume(),
            "actual_rock_volume_m3": saved.volume(), "excavated_volume_m3": removed.volume(),
            "boolean_symmetric_difference_m3": residual, "removed_space_components": len(removed.decompose()),
            "removed_symmetric_difference_m3": removed_residual,
            "actual_rock_boundary_components": len(actual.components), "manifold_version": "3.5.4",
            "closed_oriented_index_edges_verified": True, "independent_boolean_verified": True}


def air_path_evidence(rock, cutter, actual, centers, exterior_points):
    centers = np.asarray(centers, float)
    require(centers.ndim == 2 and centers.shape[1] == 3 and 2 <= len(centers) <= 64
            and np.isfinite(centers).all(), "bounded actual air route required")
    for point in centers:
        require(abs(cutter.winding(point)-1.) < 1e-6 and abs(actual.winding(point)) < 1e-6,
                "saved station air center not inside cutter/outside actual rock")
    for first, second in zip(centers, centers[1:]):
        require(not actual.segment_hits(first, second) and not cutter.segment_hits(first, second), "air route crosses actual rock/cutter boundary")
        midpoint = (first+second)/2
        require(abs(actual.winding(midpoint)) < 1e-6 and abs(cutter.winding(midpoint)-1.) < 1e-6,
                "air route midpoint blocked")
    opening_hits = []
    exterior_points = np.asarray(exterior_points, float)
    require(exterior_points.shape == (2, 3) and np.isfinite(exterior_points).all(), "explicit actual portal exterior probes required")
    for extension, endpoint, neighbor in zip(exterior_points, (centers[0], centers[-1]), (centers[1], centers[-2])):
        require(abs(rock.winding(extension)) < 1e-6 and abs(actual.winding(extension)) < 1e-6,
                "portal exterior air extension not outside rock")
        hits = rock.segment_hits(extension, neighbor)
        require(hits and not actual.segment_hits(extension, endpoint), "no actual rock exterior opening along portal route")
        opening_hits.append(hits)
    return {"air_station_count": len(centers), "air_route_length_m": float(np.linalg.norm(np.diff(centers, axis=0), axis=1).sum()),
            "portal_original_exterior_face_hits": opening_hits,
            "portal_exterior_probe_xyz_local_m": exterior_points.tolist(),
            "actual_air_polyline_verified": True,
            "scope": "saved station interior center polyline and exterior portal probes; not hydraulic capacity"}


def vdm_mapping(reference, displacement, derived, triangles, frozen_vertex_ids):
    reference, displacement, derived = (np.asarray(value, float) for value in (reference, displacement, derived))
    require(reference.ndim == 2 and reference.shape[1] == 3 and 4 <= len(reference) <= MAX_VERTICES
            and reference.shape == displacement.shape == derived.shape
            and all(np.isfinite(value).all() for value in (reference, displacement, derived)), "invalid saved multi-chart VDM points")
    compare(reference+displacement, derived, "VDM reference plus displacement equals saved derived", atol=1e-10)
    frozen = np.asarray(frozen_vertex_ids)
    require(frozen.ndim == 1 and np.issubdtype(frozen.dtype, np.integer) and len(frozen) > 0
            and len(np.unique(frozen)) == len(frozen) and frozen.min() >= 0 and frozen.max() < len(reference), "invalid frozen portal vertex references")
    require(np.array_equal(displacement[frozen], np.zeros((len(frozen), 3)))
            and np.array_equal(reference[frozen], derived[frozen]), "immutable portal moved by VDM")
    Solid(derived, triangles, "VDM derived closed cutter")
    return {"vdm_point_count": len(derived), "frozen_portal_vertex_count": len(frozen),
            "reference_plus_displacement_verified": True, "immutable_portals_verified": True}


def saved_air_route(rock, cutter, actual, points, opening_segments):
    points = np.asarray(points, float)
    require(points.ndim == 2 and points.shape[1] == 3 and 2 <= len(points) <= 128
            and np.isfinite(points).all(), "invalid saved air polyline")
    interior = []
    for ordinal, point in enumerate(points):
        require(abs(actual.winding(point)) < 1e-6, "saved air waypoint lies in remaining rock")
        inside = abs(cutter.winding(point)-1.) < 1e-6
        if inside:
            interior.append(ordinal)
        else:
            require(abs(rock.winding(point)) < 1e-6, "air waypoint outside cutter but inside original rock")
    require(interior and interior == list(range(min(interior), max(interior)+1)), "saved air route not one continuous cutter interval")
    for first, second in zip(points, points[1:]):
        require(not actual.segment_hits(first, second), "saved air segment blocked by actual remaining rock")
        require(abs(actual.winding((first+second)/2)) < 1e-6, "saved air segment midpoint lies in remaining rock")
    require(len(opening_segments) == 2, "two actual portal opening witnesses required")
    hits_by_portal = []
    for exterior, interior_point in opening_segments:
        exterior, interior_point = np.asarray(exterior, float), np.asarray(interior_point, float)
        require(exterior.shape == interior_point.shape == (3,)
                and np.isfinite(exterior).all() and np.isfinite(interior_point).all(), "invalid saved opening segment")
        require(abs(rock.winding(exterior)) < 1e-6 and abs(actual.winding(exterior)) < 1e-6
                and abs(rock.winding(interior_point)-1.) < 1e-6
                and abs(cutter.winding(interior_point)-1.) < 1e-6
                and abs(actual.winding(interior_point)) < 1e-6, "portal witness does not connect original exterior to actual removed interior")
        hits = rock.segment_hits(exterior, interior_point)
        require(hits and not actual.segment_hits(exterior, interior_point), "portal witness has no actual Boolean opening")
        hits_by_portal.append(hits)
    return {"actual_air_polyline_verified": True, "actual_exterior_openings_verified": True,
            "air_waypoint_count": len(points), "original_exterior_face_hits": hits_by_portal,
            "air_route_length_m": float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()),
            "scope": "saved air polyline and two original-exterior to removed-interior segments; no hydraulic certification"}


def section_projection(ring, origin, transverse, shape):
    ring, origin, transverse, shape = (np.asarray(value, float) for value in (ring, origin, transverse, shape))
    require(ring.ndim == 2 and ring.shape[1] == 3 and len(ring) >= 2
            and origin.shape == (3,) and transverse.shape == (2,) and shape.shape == (len(ring), 2)
            and all(np.isfinite(value).all() for value in (ring, origin, transverse, shape)), "invalid saved actual section geometry")
    compare(np.linalg.norm(transverse), 1., "section transverse unit vector", atol=1e-10)
    offsets = ring[:, [0, 2]]-origin[[0, 2]]
    projection = np.column_stack((offsets@transverse, ring[:, 1]))
    compare(projection, shape, "actual section projection from final derived mesh", atol=1e-8)
    compare(offsets@np.array([transverse[1], -transverse[0]]), np.zeros(len(ring)), "actual ring planar station", atol=1e-8)
    return projection


def audit_typed_graph(graph):
    from tools.audit_td_shared_channel_fine import load_channel

    check_identity(graph)
    require(graph["schema"] == "td-hybrid-river-graph-v1"
            and graph["coordinates"] == "XYZ metres; Y elevation; XZ horizontal"
            and graph["hydraulic_state_included"] is False and graph["surface_supply_active"] is False
            and graph["full_network_verified"] is False and graph["natural_outlet_certified"] is False,
            "typed graph schema/capability differs")
    inputs = graph["inputs"]
    for pin in inputs.values():
        checked_path(pin)
    fine_index, fine_audit = read(inputs["fine_index"]), read_audit(inputs["fine_audit"])
    require(fine_audit["schema"] == "td-shared-channel-fine-independent-audit-v1"
            and fine_audit["status"] == "passed" and fine_audit["errors"] == []
            and fine_audit["index_sha256"] == inputs["fine_index"]["sha256"]
            and fine_audit["channel"] == fine_index["channel"]
            and fine_audit["native_source_and_center_bed_verified"] is True
            and fine_audit["complete_saved_fan_cell_intersections_verified"] is True,
            "typed graph fine parent not independently bound and passed")
    for key in ("manifest", "compact_fans", "material"):
        require(inputs["fine_"+key]["sha256"] == fine_index[key]["sha256"] == fine_audit[key+"_sha256"]
                and Path(inputs["fine_"+key]["path"]).resolve() == Path(fine_index[key]["path"]).resolve(), "typed graph fine artifact differs")
    binding = fine_index["channel"]
    for key in ("index", "audit"):
        require(inputs["surface_"+key]["sha256"] == binding[key]["sha256"]
                and Path(inputs["surface_"+key]["path"]).resolve() == Path(binding[key]["path"]).resolve(), "typed graph surface parent differs")
    for key, pin in binding["artifacts"].items():
        require(inputs["surface_"+key]["sha256"] == pin["sha256"]
                and Path(inputs["surface_"+key]["path"]).resolve() == Path(pin["path"]).resolve(), "typed graph surface artifact differs")
    for key, pin in binding["inputs"].items():
        require(inputs["original_"+key]["sha256"] == pin["sha256"]
                and Path(inputs["original_"+key]["path"]).resolve() == Path(pin["path"]).resolve(), "typed graph original source differs")
    artifacts, native = load_channel(binding)
    manifest, topology = artifacts["manifest"], artifacts["topology"]
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    arcs = {arc["arc_id"]: arc for arc in graph["arcs"]}
    require(len(nodes) == len(graph["nodes"]) and len(arcs) == len(graph["arcs"]), "duplicate typed node/arc identity")
    original_nodes = {node["node_id"]: node for node in artifacts["graph"]["nodes"]}
    original_arcs = {arc["arc_id"]: arc for arc in artifacts["graph"]["arcs"]}
    surface_ids = {key for key, node in nodes.items() if node["kind"] == "surface"}
    require(surface_ids == set(manifest["selected_node_ids"]), "typed surface node census differs")
    import json
    for key in surface_ids:
        node, pin = nodes[key], binding["nodes"][key]
        saved = read(pin)
        require(inputs["accepted_node_"+key]["sha256"] == pin["sha256"]
                and Path(inputs["accepted_node_"+key]["path"]).resolve() == Path(pin["path"]).resolve()
                and json.loads(node["source_record_json"]) == original_nodes[key]
                and node["source_xyz_m"] == node["xyz_m"] == saved["source_xyz_m"], "actual surface node binding differs")
        xyz = np.asarray(saved["source_xyz_m"], float)
        sample = native.sample(xyz[[0, 2]])
        require(not sample["rejection_reasons"] and sample["height_m"] is not None, "actual surface node invalid native support")
        compare(xyz[1], sample["height_m"], "typed surface native height")
        require(0. <= saved["center_depth_m"] <= 4., "typed surface bed no-fill/4m differs")
        compare(node["bed_xyz_m"], xyz-[0., saved["center_depth_m"], 0.], "typed surface actual saved center bed")
        del saved
    surface_arcs = {key for key, arc in arcs.items() if arc["kind"] == "surface"}
    require(surface_arcs == set(topology["joined_arc_ids"]), "typed surface arc census differs")
    for key, arc in arcs.items():
        require(len(arc["node_ids"]) == 2 and all(endpoint in nodes for endpoint in arc["node_ids"]), "dangling typed arc")
        if key in surface_arcs:
            require(arc["hydraulic_role"] == "context_only" and arc["node_ids"] == original_arcs[key]["node_ids"]
                    and json.loads(arc["source_record_json"]) == original_arcs[key], "surface context falsely active/altered")
    required = {"engineered:sink:half_arm_attachment": ("portal_attachment", ("surface", "sink")),
                "engineered:underground": ("underground", ("sink", "spring")),
                "engineered:spring:half_arm_attachment": ("portal_attachment", ("spring", "surface"))}
    require(set(arcs)-surface_arcs == set(required), "unknown/missing active typed edge")
    for key, (kind, types) in required.items():
        arc = arcs[key]
        require(arc["kind"] == kind and arc["hydraulic_role"] == "sample_route"
                and tuple(nodes[endpoint]["kind"] for endpoint in arc["node_ids"]) == types, "active route type/direction differs")
    require(arcs["engineered:sink:half_arm_attachment"]["node_ids"][1] == arcs["engineered:underground"]["node_ids"][0]
            and arcs["engineered:underground"]["node_ids"][1] == arcs["engineered:spring:half_arm_attachment"]["node_ids"][0], "active route is not continuous")
    portals = {}
    for kind, ordinal in (("sink", 0), ("spring", 1)):
        matches = [node for node in nodes.values() if node["kind"] == kind]
        require(len(matches) == 1, "exactly one typed sink/spring required")
        node = matches[0]
        arc_id = node["port_arc_id"]
        require(arc_id in topology["joined_arc_ids"], "portal not at actual joined midpoint")
        pin = binding["ports"][arc_id]
        require(inputs["portal_"+arc_id]["sha256"] == pin["sha256"]
                and Path(inputs["portal_"+arc_id]["path"]).resolve() == Path(pin["path"]).resolve(), "portal pin differs")
        port = read(pin)
        require(json.loads(node["source_record_json"]) == port and port["status"] == "candidate"
                and not port["rejection_reasons"] and not port["upstream_parent_section"].get("anchor"), "invalid canonical portal source")
        pieces, floor = [], None
        segments = port["profile"]["profile_segments"]
        require(len(segments) == 3, "portal missing complete native profile")
        for segment_index, segment in enumerate(segments):
            for piece in segment["native_pieces"]:
                source_coefficients = piece["source"]["source_coefficients_m_t012"]
                cut = piece["depth_coefficients_m_t01"]
                require(0. <= min(cut[0], cut[0]+cut[1]) <= max(cut[0], cut[0]+cut[1]) <= 4., "canonical portal no-fill/4m differs")
                start, end = np.asarray(piece["start_xz_m"]), np.asarray(piece["end_xz_m"])
                for fraction in (0., .5, 1.):
                    sample = native.sample(start+(end-start)*fraction)
                    require(not sample["rejection_reasons"] and sample["height_m"] is not None and not sample["wet_source_support"], "portal native wet/unknown support")
                    compare(sample["height_m"], source_coefficients[0]+source_coefficients[1]*fraction+source_coefficients[2]*fraction**2, "canonical portal native polynomial")
                pieces.append({"width_m": float(np.linalg.norm(end-start)),
                    "bed_coefficients_m_t012": [source_coefficients[0]-cut[0], source_coefficients[1]-cut[1], source_coefficients[2]]})
                lower, upper = piece["interval_t01"]
                if segment_index == 1 and lower <= .5 <= upper:
                    fraction = (.5-lower)/(upper-lower)
                    floor = [port["midpoint_xz_m"][0], source_coefficients[0]+source_coefficients[1]*fraction+source_coefficients[2]*fraction**2-cut[0]-cut[1]*fraction, port["midpoint_xz_m"][1]]
        require(floor is not None, "canonical portal floor missing")
        compare(node["xyz_m"], floor, "typed portal actual floor")
        compare(node["bed_xyz_m"], floor, "typed portal bed")
        attachment = arcs["engineered:"+kind+":half_arm_attachment"]
        evidence = json.loads(attachment["source_record_json"])
        surface_id = attachment["node_ids"][0 if kind == "sink" else 1]
        saved = read(binding["nodes"][surface_id])
        proofs = [proof for proof in saved["port_proofs"] if proof.get("arc_id") == arc_id]
        triangle_ids = [index for index, role in enumerate(saved["geometry"]["triangle_roles"]) if role.get("region") == "half_arm" and role.get("arc_id") == arc_id]
        require(len(proofs) == 1 and triangle_ids and evidence["surface_node_record"] == saved
                and evidence["actual_complete_port_proof"] == proofs[0] and evidence["half_arm_triangle_indices"] == triangle_ids
                and evidence["surface_node_pin"] == binding["nodes"][surface_id]
                and evidence["canonical_port_pin"] == pin, "typed halfarm actual geometry/proof binding differs")
        portals[kind] = {"node": node, "port": port, "pieces": pieces, "surface_node": saved, "triangle_ids": triangle_ids}
    require(portals["sink"]["port"]["arc_id"] != portals["spring"]["port"]["arc_id"], "same portal reused")
    bypass = graph["bypass_arc_ids"]
    require(bypass and len(set(bypass)) == len(bypass) and set(bypass) <= surface_arcs
            and bypass[0] == portals["sink"]["port"]["arc_id"] and bypass[-1] == portals["spring"]["port"]["arc_id"], "surface bypass provenance differs")
    require(all(arcs[first]["node_ids"][1] == arcs[second]["node_ids"][0] for first, second in zip(bypass, bypass[1:])), "surface bypass not directed contiguous")
    return {"graph_identity_sha256": graph["identity_sha256"], "surface_node_count": len(surface_ids),
            "surface_context_arc_count": len(surface_arcs), "active_route_arc_count": 3,
            "typed_half_arm_pins_verified": True}, portals, native


class IndependentBed:
    def __init__(self, native, compact):
        from tools.td_shared_channel_fine_saved_audit import Fan
        self.native = native
        self.fans = {item["fan_key"]: Fan(item) for item in compact["fans"]}
        require(len(self.fans) == compact["fan_count"] == len(compact["fans"]), "duplicate native fans")
        self.bins = defaultdict(list)
        for key, fan in self.fans.items():
            low, high = np.floor(fan.points.min(axis=0)/10).astype(int), np.floor(fan.points.max(axis=0)/10).astype(int)
            for column in range(int(low[0]), int(high[0])+1):
                for row in range(int(low[1]), int(high[1])+1):
                    self.bins[(column, row)].append(key)

    def sample(self, point):
        sample = self.native.sample(point)
        require(not sample["rejection_reasons"] and sample["height_m"] is not None
                and not sample["wet_source_support"], "local rock source is wet/unknown/protected/unselected")
        owners, cuts = [], []
        for key in self.bins.get(tuple(np.floor(np.asarray(point)/10).astype(int)), []):
            cut = self.fans[key].center_cut(point)
            if cut is not None:
                owners.append(key)
                cuts.append(cut)
        require(not cuts or max(cuts)-min(cuts) <= 1e-9, "independent saved cuts disagree on shared support")
        cut = cuts[0] if cuts else 0.
        return {"source_sample": sample, "cut_depth_m": cut, "fan_keys": owners,
                "derived_bed_m": sample["height_m"]-cut}

    def verify(self, point, witness):
        expected = self.sample(point)
        require(set(witness["source_sample"]) == set(expected["source_sample"]), "native sampling witness fields differ")
        for key in ("native_cell_ids", "owner_ids", "contribution_leaf_ids", "rejection_reasons", "wet_source_support"):
            require(witness["source_sample"][key] == expected["source_sample"][key], "native source witness provenance differs")
        compare(witness["source_sample"]["weights"], expected["source_sample"]["weights"], "source support weights", atol=1e-12)
        compare(witness["source_sample"]["height_m"], expected["source_sample"]["height_m"], "native bilinear source")
        require(len(witness["fan_keys"]) == len(set(witness["fan_keys"]))
                and set(witness["fan_keys"]) == set(expected["fan_keys"]), "source cut fan census differs")
        require(0. <= witness["cut_depth_m"] <= 4., "saved source cut no-fill/4m differs")
        compare(witness["cut_depth_m"], expected["cut_depth_m"], "source saved affine cut")
        compare(witness["derived_bed_m"], expected["derived_bed_m"], "source derived bed")
        require(witness["derived_bed_m"] <= witness["source_sample"]["height_m"], "source witness adds fill")
        return expected


def audit_source_sampling(sampling, rock, origin, bed, spacing):
    require(sampling["schema"] == "td-hybrid-rock-source-sampling-v1"
            and sampling["native_exact"] is False and sampling["fine15_replaced"] is False
            and sampling["spacing_m"] == spacing, "local source triangulation misrepresented")
    rows, columns = sampling["rows"], sampling["columns"]
    count = sampling["top_vertex_count"]
    require(type(rows) is int and type(columns) is int and min(rows, columns) >= 2
            and count == rows*columns <= 300000 and len(sampling["samples"]) == count
            and count < len(rock.vertices), "sampled source grid budget/census differs")
    top_origin = np.asarray(sampling["origin_xz_m"], float)
    require(top_origin.shape == (2,) and np.isfinite(top_origin).all(), "invalid local source grid origin")
    for ordinal, witness in enumerate(sampling["samples"]):
        row, column = divmod(ordinal, columns)
        require(witness["row"] == row and witness["column"] == column, "source grid key omitted/duplicated/unsorted")
        point = top_origin+np.array([column, row])*spacing
        compare(witness["xz_m"], point, "source top grid coordinate", atol=1e-10)
        result = bed.verify(point, witness)
        compare(rock.vertices[ordinal]+origin, [point[0], result["derived_bed_m"], point[1]], "actual rock top source sample", atol=1e-9)
        if ordinal % 512 == 0:
            check_memory()
    bottom = sampling["bottom_elevation_m"]
    compare(rock.vertices[count:, 1]+origin[1], np.full(len(rock.vertices)-count, bottom), "actual bottom plane")
    require(np.all(rock.vertices[:count, 1]+origin[1] > bottom), "local rock bottom above top")
    expected = set()
    for row in range(rows-1):
        for column in range(columns-1):
            first = row*columns+column
            expected.add(tuple(sorted((first, first+columns, first+columns+1))))
            expected.add(tuple(sorted((first, first+columns+1, first+1))))
    actual = {tuple(sorted(face.tolist())) for face in rock.triangles if np.all(face < count)}
    require(actual == expected, "saved rock top triangles differ from explicit sampled grid")
    low, high = top_origin, top_origin+np.array([columns-1, rows-1])*spacing
    bottom_xz = rock.vertices[count:, [0, 2]]+origin[[0, 2]]
    require(np.all(bottom_xz >= low-1e-9) and np.all(bottom_xz <= high+1e-9), "bottom outside local rock footprint")
    return {"top_vertex_count": count, "source_native_samples_verified": True,
            "top_grid_triangles_verified": True, "native_exact": False, "fine15_replaced": False}


def audit_vdm(vdm, cutter, origin, portals):
    require(vdm["schema"] == "td-hybrid-multichart-vdm-v1" and vdm["old_fixed_chart_vdm_accepted"] is False,
            "unexpected multi-chart VDM")
    stations = vdm["stations"]
    require(9 <= len(stations) <= 33 and len({station["station_id"] for station in stations}) == len(stations), "VDM station budget/identity differs")
    require(vdm["immutable_portal_station_ids"] == [stations[0]["station_id"], stations[-1]["station_id"]], "VDM immutable portal census differs")
    counts = [len(station["derived_ring_xyz_m"]) for station in stations]
    require(len(set(counts)) == 1, "VDM ring vertex counts inconsistent")
    count = counts[0]
    reference = np.asarray([station["reference_ring_xyz_m"] for station in stations]).reshape(-1, 3)
    displacement = np.asarray([station["displacement_ring_xyz_m"] for station in stations]).reshape(-1, 3)
    derived = np.asarray([station["derived_ring_xyz_m"] for station in stations]).reshape(-1, 3)
    frozen = list(range(count))+list(range((len(stations)-1)*count, len(stations)*count))
    result = vdm_mapping(reference-origin, displacement, derived-origin, vdm["triangles"], frozen)
    compare(cutter.vertices, derived-origin, "actual closed cutter uses saved final VDM vertices", atol=1e-10)
    require({tuple(sorted(face.tolist())) for face in cutter.triangles} == {tuple(sorted(face)) for face in vdm["triangles"]}, "actual cutter faces not saved VDM triangles")
    parameters = vdm["profile_parameters"]
    require(parameters == sorted(set(parameters)) and parameters[0] == 0. and parameters[-1] == 3.
            and {0., 1., 2., 3.} <= set(parameters), "VDM portal profile knots incomplete")
    for station in stations:
        floor_count = station["floor_vertex_count"]
        require(floor_count == len(parameters) == count-2, "VDM canonical floor census differs")
        require(np.array_equal(np.asarray(station["displacement_ring_xyz_m"])[:floor_count], np.zeros((floor_count, 3))), "VDM moved immutable floor")
        ring = np.asarray(station["derived_ring_xyz_m"])
        transverse = np.asarray(station["transverse_unit_xz"])
        station_origin = np.asarray(station["origin_xyz_m"])
        shape = np.column_stack(((ring[:, [0, 2]]-station_origin[[0, 2]])@transverse, ring[:, 1]))
        section_projection(ring, station_origin, transverse, shape)
    for kind, station in (("sink", stations[0]), ("spring", stations[-1])):
        port = portals[kind]["port"]
        knots = {0., 1., 2., 3.}
        for index, segment in enumerate(port["profile"]["profile_segments"]):
            for piece in segment["native_pieces"]:
                require(piece["source"]["source_coefficients_m_t012"][2] == 0., "curved native portal not exactly represented by linear saved boundary")
                knots.update(index+bound for bound in piece["interval_t01"])
        require(knots <= set(parameters), "VDM omitted native portal segment break")
        floor = np.asarray(station["derived_ring_xyz_m"])[:len(parameters)]
        for parameter, point in zip(parameters, floor):
            if parameter in (0., 1., 2., 3.):
                expected = port["profile"]["profile_xyz_m"][int(parameter)]
            else:
                index = min(int(parameter), 2)
                fraction = parameter-index
                candidates = [piece for piece in port["profile"]["profile_segments"][index]["native_pieces"] if piece["interval_t01"][0] <= fraction <= piece["interval_t01"][1]]
                require(candidates, "VDM portal point has no native piece")
                piece = candidates[0]
                lower, upper = piece["interval_t01"]
                local = (fraction-lower)/(upper-lower)
                xz = np.asarray(piece["start_xz_m"])*(1-local)+np.asarray(piece["end_xz_m"])*local
                coefficients, cut = piece["source"]["source_coefficients_m_t012"], piece["depth_coefficients_m_t01"]
                expected = [xz[0], coefficients[0]+coefficients[1]*local-cut[0]-cut[1]*local, xz[1]]
            compare(point, expected, "immutable VDM portal complete canonical floor", atol=1e-8)
        compare(station["origin_xyz_m"], portals[kind]["node"]["xyz_m"], "VDM original canonical portal origin")
    result["actual_cutter_vdm_binding_verified"] = True
    return result


def audit_surface_attachments(record, geometry, portals, bed, compact):
    require(record["schema"] == "td-hybrid-surface-attachments-v1" and set(record["attachments"]) == {"sink", "spring"}, "surface attachment census differs")
    compact_by_node = defaultdict(list)
    for fan in compact["fans"]:
        compact_by_node[fan["node_id"]].append(fan)
    result = {}
    for kind, region in (("sink", "surface_in"), ("spring", "surface_out")):
        saved, port = portals[kind]["surface_node"], portals[kind]["port"]
        attachment = record["attachments"][kind]
        require(attachment["geometry"] == saved["geometry"]
                and attachment["surface_node_pin"]["identity_sha256"] == saved["identity_sha256"]
                and attachment["canonical_port_pin"]["identity_sha256"] == port["identity_sha256"]
                and attachment["half_arm_triangle_indices"] == portals[kind]["triangle_ids"], "surface saved geometry pin/triangle reference differs")
        proofs = [proof for proof in saved["port_proofs"] if proof.get("arc_id") == port["arc_id"]]
        arms = [arm for arm in saved["arms"] if arm["arc_id"] == port["arc_id"]]
        require(len(proofs) == len(arms) == 1 and attachment["actual_complete_port_proof"] == proofs[0]
                and attachment["inner_vertex_ids"] == arms[0]["inner_vertex_ids"], "surface actual port proof/inner profile differs")
        own = compact_by_node[saved["node_id"]]
        require(attachment["compact_native_fans"] == own, "surface fans differ from passed fine source functions")
        cells = [cell for cell in geometry["hydraulic_cells"] if cell["route_region"] == region]
        require(len(cells) == 1, "surface actual halfarm section census differs")
        cell = cells[0]
        ring = np.asarray(cell["section_geometry_reference"]["derived_ring_xyz_m"])
        require(cell["cell_id"] == attachment["hydraulic_station_id"]
                and cell["section_geometry_reference"]["station_id"] == cell["cell_id"]
                and cell["section_geometry_reference"]["actual_half_arm_triangle_indices"] == portals[kind]["triangle_ids"], "surface section triangle provenance differs")
        compare(ring, attachment["hydraulic_inner_ring_xyz_m"], "saved hydraulic halfarm ring")
        source_vertices = np.asarray(saved["geometry"]["vertices_xyz_m"])[arms[0]["inner_vertex_ids"]]
        require(len(source_vertices) == 4 and len(ring) == len(attachment["inner_source_witnesses"]) >= 4, "surface four-point profile incomplete")
        transverse = np.asarray(cell["section_geometry_reference"]["transverse_unit_xz"])
        offsets = ring[:, [0, 2]]@transverse
        require(np.all(np.diff(offsets) > 0.), "surface section knots not strictly ordered")
        for source_point in source_vertices:
            require(np.linalg.norm(ring[:, [0, 2]]-source_point[[0, 2]], axis=1).min() <= 1e-8, "actual surface inner port point omitted")
        expected_knots = source_vertices[:, [0, 2]].tolist()
        start, end = ring[0, [0, 2]], ring[-1, [0, 2]]
        vector = end-start
        denominator = float(vector@vector)
        require(denominator > 0., "degenerate halfarm inner line")
        for fan in own:
            for point in fan["vertices_xz_m"]:
                offset = np.asarray(point)-start
                fraction = float(offset@vector/denominator)
                distance = abs(offset[0]*vector[1]-offset[1]*vector[0])/math.sqrt(denominator)
                if distance <= 1e-8 and 0 < fraction < 1:
                    expected_knots.append(point)
        for point in expected_knots:
            require(np.linalg.norm(ring[:, [0, 2]]-point, axis=1).min() <= 1e-8, "surface section omitted actual fan/native knot")
        for point, witness in zip(ring, attachment["inner_source_witnesses"]):
            require(np.linalg.norm(np.asarray(expected_knots)-point[[0, 2]], axis=1).min() <= 1e-8, "fabricated surface section knot")
            expected = bed.verify(point[[0, 2]], witness)
            compare(point[1], expected["derived_bed_m"], "actual halfarm source-minus-cut bed")
        result[kind] = {"actual_half_arm_faces": len(portals[kind]["triangle_ids"]), "actual_inner_profile_knots": len(ring), "complete_native_port_proof_verified": True}
    return result


def sampled_top_height(rock, sampling, origin, xz):
    position = (np.asarray(xz)-sampling["origin_xz_m"])/sampling["spacing_m"]
    rows, columns = sampling["rows"], sampling["columns"]
    require(np.all(position >= 0.) and position[0] <= columns-1 and position[1] <= rows-1, "ring point outside actual sampled rock footprint")
    column, row = min(math.floor(position[0]), columns-2), min(math.floor(position[1]), rows-2)
    horizontal, vertical = position-[column, row]
    first = row*columns+column
    heights = rock.vertices[[first, first+1, first+columns, first+columns+1], 1]+origin[1]
    if horizontal <= vertical:
        return float(heights[0]+vertical*(heights[2]-heights[0])+horizontal*(heights[3]-heights[2]))
    return float(heights[0]+horizontal*(heights[1]-heights[0])+vertical*(heights[3]-heights[1]))


def audit_hydraulic_sections(geometry, vdm, rock_before, sampling, origin, bed):
    cells, stations = geometry["hydraulic_cells"], vdm["stations"]
    require(3 <= len(cells) <= 64 and len({cell["cell_id"] for cell in cells}) == len(cells), "hydraulic section budget/identity differs")
    expected_arcs = {"surface_in": "engineered:sink:half_arm_attachment", "underground": "engineered:underground", "surface_out": "engineered:spring:half_arm_attachment"}
    regions = [cell["route_region"] for cell in cells]
    require(set(regions) == set(expected_arcs) and regions == sorted(regions, key=list(expected_arcs).index), "physical section route order/census differs")
    underground = [cell for cell in cells if cell["route_region"] == "underground"]
    require(len(underground) == len(stations), "gallery station sections omitted")
    closed_ids, open_ids = [], []
    cover_rows = geometry["station_source_cover_witnesses"]
    require([row["station_id"] for row in cover_rows] == [station["station_id"] for station in stations], "actual source cover census differs")
    for ordinal, (station, cell, cover) in enumerate(zip(stations, underground, cover_rows)):
        full_ring = np.asarray(station["derived_ring_xyz_m"])
        require(len(cover["ring_source_witnesses"]) == len(full_ring), "source cover ring witnesses omitted")
        source_beds = []
        for point, witness in zip(full_ring, cover["ring_source_witnesses"]):
            source_beds.append(bed.verify(point[[0, 2]], witness)["derived_bed_m"])
        clearance = min(np.asarray(source_beds)[-2:]-full_ring[-2:, 1])
        compare(cover["minimum_roof_cover_m"], clearance, "native source cover at saved roof points")
        source_reference = np.asarray([[point[0], witness["source_sample"]["height_m"], point[2]] for point, witness in zip(full_ring, cover["ring_source_witnesses"])])
        compare(cover["original_source_reference_ring_xyz_m"], source_reference, "original native reference ring")
        compare(cover["source_to_derived_displacement_ring_xyz_m"], full_ring-source_reference, "native source to derived displacement")
        require(cover["separate_from_conduit_chart_VDM_displacement"] is True, "native source displacement conflated with chart displacement")
        actual_cover = [sampled_top_height(rock_before, sampling, origin, point[[0, 2]])-point[1] for point in full_ring]
        require(len(cover["actual_ring_containment"]) == len(full_ring), "actual rock cover witnesses omitted")
        for point, depth, witness in zip(full_ring, actual_cover, cover["actual_ring_containment"]):
            compare(witness["point_xyz_m"], point, "rock cover witness ring point")
            if depth > 1e-8:
                require(witness["rock_before_vertical_hits"] and witness["actual_sampled_top_cover_m"] is not None, "actual sampled rock cover witness missing")
                compare(witness["actual_sampled_top_cover_m"], depth, "actual sampled planar rock cover", atol=1e-8)
            elif depth < -1e-8:
                require(witness["actual_sampled_top_cover_m"] is None and witness["rock_before_vertical_hits"] == [], "uncovered ramp claims actual rock cover")
        contained = bool(min(actual_cover) > 0. and min(actual_cover[-2:]) >= .5)
        if contained:
            for point in full_ring-origin:
                if abs(rock_before.winding(point)-1.) >= 1e-6:
                    contained = False
                    break
        if contained:
            local_ring = full_ring-origin
            contained = not any(rock_before.segment_hits(first, second) for first, second in zip(local_ring, np.roll(local_ring, -1, axis=0)))
        reference = cell["section_geometry_reference"]
        require(reference["station_id"] == station["station_id"] and reference["vdm_station_index"] == ordinal, "section final VDM station binding differs")
        require(reference["vdm_floor_vertex_indices"] == list(range(station["floor_vertex_count"])), "section immutable floor references differ")
        require(cover["physical_closed_rock_section"] is contained, "saved physical closure classification differs from independent actual rock")
        if cell["section"]["kind"] == "closed_polygon":
            require(contained and cell["kind"] == "underground", "closed hydraulic section has no actual rock roof/complete rock enclosure")
            expected_ring = full_ring
            closed_ids.append(ordinal)
        else:
            require(cell["section"]["kind"] == "open_polyline" and cell["kind"] == "surface"
                    and not contained and cell["section"]["sidewall_extension"] == "explicit_engineering_vertical", "open ramp classification/engineering wall differs")
            expected_ring = full_ring[:station["floor_vertex_count"]]
            open_ids.append(ordinal)
        compare(reference["derived_ring_xyz_m"], expected_ring, "actual gallery section final VDM ring/floor prefix", atol=1e-10)
        indices = list(range(ordinal*len(full_ring), ordinal*len(full_ring)+len(expected_ring)))
        require(reference["cutter_ring_vertex_indices"] == indices, "section final cutter vertex references differ")
    require(closed_ids and closed_ids == list(range(min(closed_ids), max(closed_ids)+1)), "closed underground block absent/discontinuous")
    require(geometry["actual_closed_core_station_indices"] == closed_ids
            and geometry["hydraulic_contract_identity_sha256"] == digest({"contract": "actual-open-ramp-v2", "physical_kind_independent_of_graph_route_region": True}), "actual core/physical-kind contract differs")
    kinds = [cell["kind"] for cell in cells]
    first, last = kinds.index("underground"), len(kinds)-1-kinds[::-1].index("underground")
    require(all(kind == "underground" for kind in kinds[first:last+1]) and all(kind == "surface" for kind in kinds[:first]+kinds[last+1:]), "physical cell types not continuous open/closed/open")
    for cell in cells:
        require(cell["graph_arc_id"] == expected_arcs[cell["route_region"]]
                and math.isfinite(cell["length_m"]) and cell["length_m"] > 0
                and math.isfinite(cell["roughness_manning"]) and cell["roughness_manning"] > 0, "section route/length/roughness differs")
        reference, section = cell["section_geometry_reference"], cell["section"]
        shape_key = "polygon_transverse_elevation_m" if section["kind"] == "closed_polygon" else "polyline_transverse_elevation_m"
        section_projection(reference["derived_ring_xyz_m"], reference["origin_xyz_m"], reference["transverse_unit_xz"], section[shape_key])
        if section["kind"] == "closed_polygon":
            require(math.isfinite(section["pressure_slot_width_m"]) and section["pressure_slot_width_m"] > 0., "explicit engineering pressure slot missing")
        else:
            require(section["sidewall_extension"] == "explicit_engineering_vertical", "explicit open-profile engineering walls missing")
    links = geometry["hydraulic_links"]
    require(len(links) == len(cells)-1 and len({link["link_id"] for link in links}) == len(links), "physical links duplicated/omitted")
    link_types = {("surface", "surface"): "surface_half_arm", ("surface", "underground"): "sink_exchange", ("underground", "underground"): "conduit", ("underground", "surface"): "spring_exchange"}
    for first_cell, second_cell, link in zip(cells, cells[1:], links):
        require(link["from_cell_id"] == first_cell["cell_id"] and link["to_cell_id"] == second_cell["cell_id"]
                and link["kind"] == link_types[(first_cell["kind"], second_cell["kind"])], "hydraulic physical connection/type differs")
        compare(link["length_m"], (first_cell["length_m"]+second_cell["length_m"])/2, "physical link length")
    return {"actual_hydraulic_sections_verified": True, "closed_rock_enclosed_station_ids": [stations[index]["station_id"] for index in closed_ids],
            "open_ramp_station_ids": [stations[index]["station_id"] for index in open_ids],
            "engineering_vertical_walls_and_pressure_slots_explicit": True, "hydraulic_solver_executed": False}
