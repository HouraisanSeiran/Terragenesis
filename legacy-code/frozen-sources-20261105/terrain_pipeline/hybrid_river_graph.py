"""Immutable metre-based topology; hydraulic state is deliberately absent."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "td-hybrid-river-graph-v1"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_SURFACE_NODES = 128


def canonical_json(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(record):
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FilePin:
    path: str
    sha256: str

    def __post_init__(self):
        if not Path(self.path).is_absolute() or len(self.sha256) != 64:
            raise ValueError("pins require absolute paths and SHA256")
        int(self.sha256, 16)


def read_pinned(pin: FilePin):
    path = Path(pin.path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("pinned JSON exceeds bounded file size")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pin.sha256:
        raise ValueError("pinned file SHA256 mismatch")
    return json.loads(data)


@dataclass(frozen=True)
class RiverNode:
    node_id: str
    kind: str
    xyz_m: tuple[float, float, float]
    source_record_json: str
    port_arc_id: str | None = None
    source_xyz_m: tuple[float, float, float] | None = None
    bed_xyz_m: tuple[float, float, float] | None = None

    def __post_init__(self):
        if self.kind not in ("surface", "sink", "spring"):
            raise ValueError("unknown river node type")
        if not isinstance(self.xyz_m, tuple) or len(self.xyz_m) != 3:
            raise ValueError("XYZ must be an immutable three-tuple")
        if not all(math.isfinite(value) for value in self.xyz_m):
            raise ValueError("nonfinite XYZ")
        for coordinates in (self.source_xyz_m, self.bed_xyz_m):
            if coordinates is not None and (not isinstance(coordinates, tuple) or len(coordinates) != 3 or not all(math.isfinite(value) for value in coordinates)):
                raise ValueError("source/bed coordinates must be finite immutable XYZ")
        if self.kind == "surface" and (self.source_xyz_m != self.xyz_m or self.bed_xyz_m is None):
            raise ValueError("surface reference XYZ and actual derived bed XYZ must be distinct fields")
        if self.kind != "surface" and self.bed_xyz_m != self.xyz_m:
            raise ValueError("route station XYZ must represent derived portal bed")


@dataclass(frozen=True)
class RiverArc:
    arc_id: str
    kind: str
    node_ids: tuple[str, str]
    hydraulic_role: str
    source_record_json: str

    def __post_init__(self):
        if self.kind not in ("surface", "underground", "portal_attachment"):
            raise ValueError("unknown river arc type")
        if not isinstance(self.node_ids, tuple) or len(self.node_ids) != 2:
            raise ValueError("arc endpoints must be immutable")
        if self.hydraulic_role != ("context_only" if self.kind == "surface" else "sample_route"):
            raise ValueError("surface context cannot supply duplicate cumulative Q")


@dataclass(frozen=True)
class HybridRiverGraph:
    nodes: tuple[RiverNode, ...]
    arcs: tuple[RiverArc, ...]
    inputs: tuple[tuple[str, FilePin], ...]
    bypass_arc_ids: tuple[str, ...]

    def __post_init__(self):
        if not all(isinstance(value, tuple) for value in (self.nodes, self.arcs, self.inputs, self.bypass_arc_ids)):
            raise ValueError("graph collections must be immutable tuples")
        node_ids = [node.node_id for node in self.nodes]
        arc_ids = [arc.arc_id for arc in self.arcs]
        if len(set(node_ids)) != len(node_ids) or len(set(arc_ids)) != len(arc_ids):
            raise ValueError("duplicate graph identities")
        if sum(node.kind == "surface" for node in self.nodes) > MAX_SURFACE_NODES:
            raise ValueError("surface node resource limit exceeded")
        if any(endpoint not in node_ids for arc in self.arcs for endpoint in arc.node_ids):
            raise ValueError("dangling graph arc")
        if len([node for node in self.nodes if node.kind == "sink"]) != 1 or len([node for node in self.nodes if node.kind == "spring"]) != 1:
            raise ValueError("sample requires exactly one explicit sink/spring pair")
        underground = [arc for arc in self.arcs if arc.kind == "underground"]
        if len(underground) != 1:
            raise ValueError("sample requires one underground route")
        types = {node.node_id: node.kind for node in self.nodes}
        if tuple(types[key] for key in underground[0].node_ids) != ("sink", "spring"):
            raise ValueError("underground route must bind sink to spring")
        attachments = [arc for arc in self.arcs if arc.kind == "portal_attachment"]
        attachment_types = [tuple(types[key] for key in arc.node_ids) for arc in attachments]
        if sorted(attachment_types) != sorted([("surface", "sink"), ("spring", "surface")]):
            raise ValueError("route requires explicit actual surface-to-portal half-arm attachments")
        if any(key not in arc_ids for key in self.bypass_arc_ids):
            raise ValueError("bypass provenance is missing")

    def to_record(self):
        record = {"schema": SCHEMA, "coordinates": "XYZ metres; Y elevation; XZ horizontal",
                  "nodes": [asdict(node) for node in self.nodes],
                  "arcs": [asdict(arc) for arc in self.arcs],
                  "inputs": {key: asdict(pin) for key, pin in self.inputs},
                  "bypass_arc_ids": list(self.bypass_arc_ids),
                  "hydraulic_state_included": False, "natural_outlet_certified": False,
                  "full_network_verified": False, "surface_supply_active": False}
        record["identity_sha256"] = identity(record)
        return json.loads(canonical_json(record))


def native_bed_pieces(port):
    pieces = []
    for segment in port["profile"]["profile_segments"]:
        for native in segment["native_pieces"]:
            source = native["source"]["source_coefficients_m_t012"]
            cut = native["depth_coefficients_m_t01"]
            if min(cut[0], cut[0] + cut[1]) < 0 or max(cut[0], cut[0] + cut[1]) > 4:
                raise ValueError("native profile violates strict cut limits")
            start, end = native["start_xz_m"], native["end_xz_m"]
            pieces.append({"width_m": math.dist(start, end),
                           "bed_coefficients_m_t012": [source[0] - cut[0], source[1] - cut[1], source[2]]})
    if len(port["profile"]["profile_segments"]) != 3 or not pieces:
        raise ValueError("incomplete canonical native profile")
    return pieces


def port_floor_xyz(port):
    segment = port["profile"]["profile_segments"][1]
    for piece in segment["native_pieces"]:
        lower, upper = piece["interval_t01"]
        if lower <= 0.5 <= upper:
            fraction = (0.5 - lower) / (upper - lower)
            source = piece["source"]["source_coefficients_m_t012"]
            cut = piece["depth_coefficients_m_t01"]
            bed = source[0] + source[1] * fraction + source[2] * fraction**2 - cut[0] - cut[1] * fraction
            return (port["midpoint_xz_m"][0], bed, port["midpoint_xz_m"][1])
    raise ValueError("port midpoint is unsupported")


def attachment_evidence(saved_node, port, node_witness, port_witness):
    if saved_node["identity_sha256"] != node_witness["identity_sha256"] or saved_node["status"] != "candidate":
        raise ValueError("attachment is not an audited accepted surface node")
    key = port["arc_id"]
    arms = [arm for arm in saved_node["arms"] if arm["arc_id"] == key]
    proofs = [proof for proof in saved_node["port_proofs"] if proof.get("arc_id") == key]
    if len(arms) != 1 or len(proofs) != 1 or arms[0]["midpoint_port_identity_sha256"] != port["identity_sha256"]:
        raise ValueError("attachment lacks a unique actual canonical half arm")
    proof = proofs[0]
    if proof["midpoint_port_identity_sha256"] != port["identity_sha256"] or sorted(segment["profile_segment_index"] for segment in proof["segments"]) != [0, 1, 2]:
        raise ValueError("attachment omitted full three-segment canonical boundary")
    geometry = saved_node["geometry"]
    triangle_indices = [ordinal for ordinal, role in enumerate(geometry["triangle_roles"]) if role.get("region") == "half_arm" and role.get("arc_id") == key]
    ring_indices = [ordinal for ordinal, role in enumerate(geometry["triangle_roles"]) if role.get("region") == "node_ring"]
    if not triangle_indices or not ring_indices or any(not segment["pieces"] for segment in proof["segments"]):
        raise ValueError("attachment has no actual half-arm triangle/native edge evidence")
    for segment in proof["segments"]:
        for piece in segment["pieces"]:
            if piece["side"]["triangle_index"] not in triangle_indices:
                raise ValueError("canonical port side is not on the actual half arm")
    return canonical_json({"surface_node_pin": node_witness, "canonical_port_pin": port_witness,
                           "half_arm_triangle_indices": triangle_indices, "node_ring_triangle_indices": ring_indices,
                           "actual_complete_port_proof": proof,
                           "surface_node_record": saved_node, "hydraulic_boundary_certified": False})


def build_graph(surface_graph, manifest, topology, audit, ports, inputs, sink_arc_id, spring_arc_id, saved_nodes):
    if audit["status"] != "passed" or not audit["complete_actual_reverse_midpoint_functions_verified"]:
        raise ValueError("surface audit has not verified actual complete port functions")
    if sink_arc_id == spring_arc_id:
        raise ValueError("sink and spring cannot share one midpoint")
    selected = set(manifest["selected_node_ids"])
    joined = set(topology["joined_arc_ids"])
    if selected != set(audit["selected_node_ids"]):
        raise ValueError("surface selection differs from passed audit")
    if any(key not in joined or key not in audit["ports"] for key in (sink_arc_id, spring_arc_id)):
        raise ValueError("sink/spring require audited actual joined midpoint ports")
    source_nodes = {node["node_id"]: node for node in surface_graph["nodes"]}
    source_arcs = {arc["arc_id"]: arc for arc in surface_graph["arcs"]}
    if not joined <= set(source_arcs) or not selected <= set(source_nodes):
        raise ValueError("accepted surface provenance missing")
    sink_arc, spring_arc = source_arcs[sink_arc_id], source_arcs[spring_arc_id]
    outgoing = {}
    for key in joined:
        arc = source_arcs[key]
        if not set(arc["node_ids"]) <= selected:
            raise ValueError("accepted arc references unselected node")
        outgoing.setdefault(arc["node_ids"][0], []).append(key)
    start, target = sink_arc["node_ids"][1], spring_arc["node_ids"][0]
    queue = [(start, ())]
    visited = set()
    route = None
    while queue:
        current, path = queue.pop(0)
        if current == target:
            route = path
            break
        if current in visited:
            continue
        visited.add(current)
        for key in sorted(outgoing.get(current, ())):
            queue.append((source_arcs[key]["node_ids"][1], path + (key,)))
    if route is None:
        raise ValueError("ports do not lie on a directed accepted surface bypass")
    nodes = []
    for key in sorted(selected):
        original = source_nodes[key]
        saved = saved_nodes[key]
        if saved["identity_sha256"] != audit["nodes"][key]["identity_sha256"]:
            raise ValueError("saved surface bed differs from actual audited node")
        source_xyz = tuple(saved["source_xyz_m"])
        if source_xyz != tuple(original["xyz_m"]) or not 0 <= saved["center_depth_m"] <= 4:
            raise ValueError("surface source/derived bed coordinates differ from original evidence")
        bed_xyz = (source_xyz[0], source_xyz[1] - saved["center_depth_m"], source_xyz[2])
        nodes.append(RiverNode(key, "surface", tuple(original["xyz_m"]), canonical_json(original), source_xyz_m=source_xyz, bed_xyz_m=bed_xyz))
    for kind, key in (("sink", sink_arc_id), ("spring", spring_arc_id)):
        port = ports[key]
        witness = audit["ports"][key]
        if witness["identity_sha256"] != port["identity_sha256"]:
            raise ValueError("canonical port identity differs from audit")
        if port.get("rejection_reasons") or port["upstream_parent_section"].get("anchor"):
            raise ValueError("rejected or anchor midpoint cannot be an engineered portal")
        native_bed_pieces(port)
        nodes.append(RiverNode("engineered:" + kind, kind, port_floor_xyz(port), canonical_json(port), key, bed_xyz_m=port_floor_xyz(port)))
    arcs = [RiverArc(key, "surface", tuple(source_arcs[key]["node_ids"]), "context_only", canonical_json(source_arcs[key])) for key in sorted(joined)]
    arcs.append(RiverArc("engineered:underground", "underground", ("engineered:sink", "engineered:spring"), "sample_route", canonical_json({"engineering_selection": True})))
    for kind, key, surface_node_id in (("sink", sink_arc_id, sink_arc["node_ids"][0]), ("spring", spring_arc_id, spring_arc["node_ids"][1])):
        evidence = attachment_evidence(saved_nodes[surface_node_id], ports[key], audit["nodes"][surface_node_id], audit["ports"][key])
        endpoints = (surface_node_id, "engineered:sink") if kind == "sink" else ("engineered:spring", surface_node_id)
        arcs.append(RiverArc("engineered:" + kind + ":half_arm_attachment", "portal_attachment", endpoints, "sample_route", evidence))
    return HybridRiverGraph(tuple(nodes), tuple(arcs), tuple(sorted(inputs.items())), (sink_arc_id,) + route + (spring_arc_id,))


def load_graph(record):
    unsigned = dict(record)
    expected = unsigned.pop("identity_sha256")
    if record["schema"] != SCHEMA or identity(unsigned) != expected:
        raise ValueError("hybrid graph schema/identity mismatch")
    nodes = tuple(RiverNode(**{**node, "xyz_m": tuple(node["xyz_m"]),
                              "source_xyz_m": tuple(node["source_xyz_m"]) if node["source_xyz_m"] is not None else None,
                              "bed_xyz_m": tuple(node["bed_xyz_m"]) if node["bed_xyz_m"] is not None else None}) for node in record["nodes"])
    arcs = tuple(RiverArc(**{**arc, "node_ids": tuple(arc["node_ids"])}) for arc in record["arcs"])
    graph = HybridRiverGraph(nodes, arcs, tuple(sorted((key, FilePin(**pin)) for key, pin in record["inputs"].items())), tuple(record["bypass_arc_ids"]))
    if graph.to_record() != record:
        raise ValueError("graph fields do not match immutable contract")
    return graph
