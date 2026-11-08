"""Read an exported delta graph without regrowing it on a display grid.

The saved local metre geometry is authoritative. A consumer may rasterize the
same graph at several spacings; no random growth or hydraulic solve happens
while loading. This reader intentionally does not reconstruct the obsolete
analytic lobe boundary: it is not the source-controlled plain boundary.
"""

import json
from pathlib import Path

import networkx as nx
import numpy as np

from . import delta_network_skeleton as skeleton
from .delta_network_skeleton_v3 import DeltaParamsV3


def load_graph(directory):
    """Load v3-family graph arrays from a frozen product and its parameters."""
    directory = Path(directory)
    data = json.loads((directory / "channel_graph.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    nodes, edges = data["nodes"], data["edges"]
    if [row["id"] for row in nodes] != list(range(len(nodes))):
        raise ValueError("frozen graph node IDs must be contiguous and ordered")
    if [row["id"] for row in edges] != list(range(len(edges))):
        raise ValueError("frozen graph edge IDs must be contiguous and ordered")
    graph = skeleton.DeltaGraph()
    graph.params = DeltaParamsV3(**manifest["params"]["delta"])
    graph.seeds = manifest["derived_seeds"]
    graph.lobes = data["lobes"]
    graph.youngest = data["youngest_lobe"]
    graph.node_uv = np.asarray([[row["u_m"], row["v_m"]] for row in nodes], float)
    graph.node_kind = np.asarray([skeleton.NODE_KINDS.index(row["kind"]) for row in nodes], np.int8)
    graph.node_q = np.asarray([row["Q_m3s"] for row in nodes], float)
    graph.edge_from = np.asarray([row["from"] for row in edges], np.int64)
    graph.edge_to = np.asarray([row["to"] for row in edges], np.int64)
    graph.edge_q = np.asarray([row["Q_m3s"] for row in edges], float)
    graph.edge_w = np.asarray([row["width_m"] for row in edges], float)
    graph.edge_h = np.asarray([row["depth_m"] for row in edges], float)
    graph.edge_level = np.asarray([row["level"] for row in edges], np.int16)
    graph.edge_lobe = np.asarray([row["lobe"] for row in edges], np.int16)
    graph.edge_kind = np.asarray([skeleton.EDGE_KINDS.index(row["kind"]) for row in edges], np.int8)
    paths = [np.asarray(row["path_uv_m"], float) for row in edges]
    graph.pt_off = np.cumsum([0] + [len(path) for path in paths]).astype(np.int64)
    graph.pts_uv = np.vstack(paths)
    graph.edge_len = np.asarray([np.linalg.norm(np.diff(path, axis=0), axis=1).sum() for path in paths])
    graph.mouth_nodes = np.flatnonzero(graph.node_kind == skeleton.NODE_KINDS.index("mouth"))
    topology = nx.DiGraph(zip(graph.edge_from, graph.edge_to))
    graph.topo = np.asarray(list(nx.lexicographical_topological_sort(topology)), np.int64)
    outgoing = np.bincount(graph.edge_from, weights=graph.edge_q, minlength=len(nodes))
    graph.edge_frac = graph.edge_q / outgoing[graph.edge_from]
    graph.construction_profiles = data.get("construction_profiles", {})
    graph.geological_mouth_trims = []
    if not skeleton.validate_graph(graph)["ok"]:
        raise ValueError("frozen graph violates its saved flow or geometric constraints")
    return graph


def topology_identity(graph):
    """JSON-ready exact identity of topology, nodes and design discharges."""
    return {
        name: getattr(graph, name).tolist()
        for name in ("node_uv", "node_kind", "node_q", "edge_from", "edge_to", "edge_q", "mouth_nodes")
    }
