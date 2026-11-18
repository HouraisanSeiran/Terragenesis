"""Persist and query independent continuous river topology without generation."""
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256


def verify_network(root, record):
    path = Path(root) / record["file"]
    if not path.is_file() or file_sha256(path) != record["sha256"]:
        raise ValueError("river network identity mismatch")
    return path


def write_network(root, graph, metadata):
    """Write inside the caller's unpublished staging directory."""
    _validate(graph)
    path = Path(root) / "river-network.npz"
    np.savez(path, **graph)
    return {"file": path.name, "sha256": file_sha256(path), "metadata": metadata}


def read_network(root, record):
    path = verify_network(root, record)
    with np.load(path, allow_pickle=False) as archive:
        graph = {name: archive[name] for name in archive.files}
    _validate(graph)
    return graph


def _reach_endpoints(graph):
    source = graph["reach_source_node"] if "reach_source_node" in graph else graph["reach_source"]
    target = graph["reach_target_node"] if "reach_target_node" in graph else graph["reach_target"]
    return np.asarray(source), np.asarray(target)


def display_reach_mask(graph, *, min_q_m3_s=0., min_width_m=0.):
    """Select reaches by their source section, without changing accumulated Q.

    Both inclusive thresholds must pass. This is presentation only: receivers,
    terminals, spill edges and node quantities remain unchanged. Geometry warning
    flags remain separate so a renderer can retain their diagnostic styling.
    """
    for name, value in (("min_q_m3_s", min_q_m3_s), ("min_width_m", min_width_m)):
        if isinstance(value, (bool, np.bool_)) or not np.isfinite(value) or value < 0.:
            raise ValueError(f"{name} must be finite and nonnegative")
    _validate(graph)
    count = np.asarray(graph["node_x_m"]).size
    fields = []
    for name in ("node_q_m3_s", "node_width_m"):
        values = np.asarray(graph[name])
        if values.shape != (count,) or not np.isfinite(values).all() or np.any(values < 0.):
            raise ValueError(f"{name} must contain finite nonnegative node quantities")
        fields.append(values)
    source, _ = _reach_endpoints(graph)
    selected = (fields[0][source] >= min_q_m3_s) & (fields[1][source] >= min_width_m)
    return np.frombuffer(selected.tobytes(), dtype=np.bool_)


def downstream_display_destination(graph, node, visible_mask):
    """Find the first visible downstream reach, or preserve the actual terminal.

    Hidden contributions are already included in node_q_m3_s. This function
    reports their topological destination and never transfers or adds discharge.
    """
    _validate(graph)
    source, target = _reach_endpoints(graph)
    visible = np.asarray(visible_mask)
    receiver = np.asarray(graph["receiver"])
    count = np.asarray(graph["node_x_m"]).size
    if (visible.dtype != np.bool_ or visible.shape != source.shape
            or receiver.shape != (count,) or receiver.dtype.kind not in "iu"
            or np.any(receiver < -1) or np.any(receiver >= count)
            or isinstance(node, (bool, np.bool_)) or not isinstance(node, (int, np.integer))
            or not 0 <= node < count):
        raise ValueError("invalid downstream display query")
    if np.unique(source).size != source.size or np.any(receiver[source] != target):
        raise ValueError("display reaches must follow unique source receivers")
    reach_at_node = dict(zip(source.tolist(), range(source.size)))
    seen = set()
    while node not in seen:
        seen.add(node)
        terminal = _value(graph, "node_terminal_kind", node)
        if receiver[node] < 0 or terminal not in (None, 0):
            return {"kind": "terminal", "node_id": int(node), "terminal_kind": terminal}
        reach = reach_at_node.get(node)
        if reach is not None and visible[reach]:
            return {"kind": "visible_reach", "node_id": int(node), "reach_index": int(reach)}
        node = int(receiver[node])
    raise ValueError("downstream display query encountered a receiver cycle")


def _validate(graph):
    shape = np.asarray(graph["native_shape"])
    origin = np.asarray(graph["origin_native_xz"])
    if shape.shape != (2,) or origin.shape != (2,) or shape.dtype.kind not in "iu" or np.any(shape < 1):
        raise ValueError("river network native shape and origin are invalid")
    count = int(shape[0]) * int(shape[1])
    for name in ("node_x_m", "node_z_m"):
        values = np.asarray(graph[name])
        if values.shape != (count,) or not np.isfinite(values).all():
            raise ValueError("river network node coordinates are invalid")
    for name in ("receiver", "node_q_m3_s", "node_width_m", "node_design_incision_depth_m", "node_terminal_kind"):
        if name in graph and np.asarray(graph[name]).shape != (count,):
            raise ValueError("river network node field shape mismatch")
    source, target = _reach_endpoints(graph)
    if (source.ndim != 1 or source.shape != target.shape or source.dtype.kind not in "iu"
            or target.dtype.kind not in "iu" or np.any(source < 0) or np.any(target < 0)
            or np.any(source >= count) or np.any(target >= count)):
        raise ValueError("river network reach indices are invalid")
    for name in ("reach_projection_blocked", "reach_max_cut_limited", "reach_raw_uphill"):
        if name in graph and np.asarray(graph[name]).shape != source.shape:
            raise ValueError("river network reach field shape mismatch")
    if "spill_source_node" in graph:
        source, target = np.asarray(graph["spill_source_node"]), np.asarray(graph["spill_target_node"])
        volume = np.asarray(graph["spill_volume_m3"])
        if (source.ndim != 1 or source.shape != target.shape or source.shape != volume.shape
                or source.dtype.kind not in "iu" or target.dtype.kind not in "iu"
                or np.any(source < 0) or np.any(target < 0) or np.any(source >= count)
                or np.any(target >= count) or not np.isfinite(volume).all() or np.any(volume <= 0)):
            raise ValueError("river network spill edges must have positive finite volume")


def _value(graph, name, index):
    if name not in graph:
        return None
    value = np.asarray(graph[name])[index].item()
    return None if isinstance(value, float) and not np.isfinite(value) else value


def query_node(graph, native_xz, metadata=None):
    """Report actual graph reaches at a cell account, with spill kept separate."""
    origin = np.asarray(graph["origin_native_xz"])
    rows, cols = (int(v) for v in graph["native_shape"])
    col, row = int(native_xz[0]) - int(origin[0]), int(native_xz[1]) - int(origin[1])
    if not (0 <= row < rows and 0 <= col < cols):
        raise ValueError("cell is outside the river network")
    node = row * cols + col

    def position(index):
        return [float(graph["node_x_m"][index]), float(graph["node_z_m"][index])]

    def section(index):
        return {"q_m3_s": _value(graph, "node_q_m3_s", index),
                "width_m": _value(graph, "node_width_m", index),
                "design_incision_depth_m": _value(graph, "node_design_incision_depth_m", index)}

    source, target = _reach_endpoints(graph)

    def reaches(indices):
        return [{"reach_index": int(i), "source_node": int(source[i]), "target_node": int(target[i]),
                 "source_world_xz_m": position(source[i]), "target_world_xz_m": position(target[i]),
                 **section(source[i]), "target_section": section(target[i]),
                 "projection_blocked": _value(graph, "reach_projection_blocked", i),
                 "max_cut_limited": _value(graph, "reach_max_cut_limited", i),
                 "raw_uphill": _value(graph, "reach_raw_uphill", i)} for i in indices]

    spill_source = np.asarray(graph.get("spill_source_node", np.empty(0, dtype=np.int64)))
    spill_target = np.asarray(graph.get("spill_target_node", np.empty(0, dtype=np.int64)))
    spill_volume = np.asarray(graph.get("spill_volume_m3", np.empty(0)))

    def spills(indices):
        return [{"source_node": int(spill_source[i]), "target_node": int(spill_target[i]),
                 "source_world_xz_m": position(spill_source[i]), "target_world_xz_m": position(spill_target[i]),
                 "volume_m3": float(spill_volume[i])} for i in indices]

    terminal = _value(graph, "node_terminal_kind", node)
    kinds = (metadata or {}).get("terminal_kinds", {})
    return {"node_id": node, "native_xz": [int(v) for v in native_xz],
            "world_xz_m": position(node), **section(node),
            "terminal_kind": kinds.get(str(terminal), terminal),
            "receiver_node": _value(graph, "receiver", node),
            "incoming_reaches": reaches(np.flatnonzero(target == node)),
            "outgoing_reaches": reaches(np.flatnonzero(source == node)),
            "incoming_spill_edges": spills(np.flatnonzero((spill_target == node) & (spill_volume > 0))),
            "outgoing_spill_edges": spills(np.flatnonzero((spill_source == node) & (spill_volume > 0)))}
