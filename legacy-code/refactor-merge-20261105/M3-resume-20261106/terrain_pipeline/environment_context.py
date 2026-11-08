"""Terrain arrays and graph support shared by finite environment processes."""
from dataclasses import replace
import numpy as np
from terrain_pipeline.drainage import IrregularMesh as IrregularMesh
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
from terrain_pipeline.drainage import segments_clear as segments_clear


def field(mapping, name, shape, default=0., *, nonnegative=True):
    value = np.asarray(mapping.get(name, default), np.float64)
    try:
        value = np.broadcast_to(value, shape).copy()
    except ValueError as error:
        raise ValueError(name + " must match the context grid") from error
    if not np.isfinite(value).all() or (nonnegative and np.any(value < 0.)):
        raise ValueError(name + " must be finite" + (" and nonnegative" if nonnegative else ""))
    return value


def prepare_mesh(context, shape, *, edge_order="sorted"):
    """Use saved support directly, retaining the consumer's neighbor ordering."""
    stable = edge_order == "stable"
    origin = tuple(context["origin_native_xz"]) if stable else context["origin_native_xz"]
    spacing = float(context["spacing_m"]) if stable else context["spacing_m"]
    seed = context["world_seed"]
    explicit = "graph_edge_source" in context or (stable and "graph_edge_target" in context)
    if not explicit:
        return build_mesh(shape, origin_native_xz=origin, spacing_m=spacing, world_seed=seed)
    # Validate the same metadata without constructing discarded Delaunay edges.
    if len(shape) != 2 or any(not isinstance(v, (int, np.integer)) or v < 1 for v in shape):
        raise ValueError("shape must contain two positive integers")
    if len(origin) != 2 or any(not isinstance(v, (int, np.integer)) for v in origin):
        raise ValueError("origin_native_xz must contain two integers")
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("spacing_m must be finite and positive")
    if not isinstance(seed, (int, np.integer)):
        raise ValueError("world_seed must be an integer")
    count = int(np.prod(shape))
    if stable:
        source = np.asarray(context["graph_edge_source"])
        target = np.asarray(context["graph_edge_target"])
        if (source.ndim != 1 or target.shape != source.shape or source.dtype.kind not in "iu"
                or target.dtype.kind not in "iu" or np.any((source < 0) | (source >= count))
                or np.any((target < 0) | (target >= count))):
            raise ValueError("explicit saved graph edge arrays required")
        order = np.argsort(source, kind="stable")
        x = field(context, "node_x_m", shape, nonnegative=False).ravel()
        z = field(context, "node_z_m", shape, nonnegative=False).ravel()
    else:
        source = np.asarray(context["graph_edge_source"], np.int64)
        target = np.asarray(context["graph_edge_target"], np.int64)
        if source.ndim != 1 or target.shape != source.shape or np.any(source < 0) or np.any(target < 0) or np.any(source >= count) or np.any(target >= count):
            raise ValueError("invalid explicit graph adjacency")
        order = np.lexsort((target, source))
        encoded = source * count + target
        reverse_encoded = target * count + source
        if (np.any(source == target) or np.unique(encoded).size != encoded.size
                or not np.array_equal(np.sort(encoded), np.sort(reverse_encoded))):
            raise ValueError("explicit graph requires unique symmetric non-self edges")
        x = array(context["node_x_m"], shape, "node_x_m", nonnegative=False).ravel()
        z = array(context["node_z_m"], shape, "node_z_m", nonnegative=False).ravel()
    source, target = source[order], target[order]
    lengths = np.hypot(x[source] - x[target], z[source] - z[target])
    if np.any(lengths <= 0.):
        raise ValueError("positive saved edge length required" if stable else
                         "explicit graph requires positive metric edge lengths")
    return IrregularMesh(tuple(map(int, shape)), tuple(map(int, origin)), float(spacing), int(seed),
                         x, z, np.r_[0, np.cumsum(np.bincount(source, minlength=count))],
                         target, lengths)


def array(value, shape, name, *, nonnegative=True):
    result = np.asarray(value, np.float64)
    if result.ndim == 0:
        result = np.full(shape, float(result))
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(name + " must be finite and match the terrain shape")
    if nonnegative and np.any(result < 0.):
        raise ValueError(name + " must be nonnegative")
    return result.copy()


def context_arrays(context, dt_s):
    if not np.isfinite(dt_s) or dt_s <= 0.:
        raise ValueError("dt_s must be finite positive physical seconds")
    height = np.asarray(context["height_m"], np.float64)
    if height.ndim != 2 or not np.isfinite(height).all():
        raise ValueError("height_m must be a finite 2D array")
    masks = {}
    for name in ("river_mask", "ocean_mask", "valid_mask", "protected_mask"):
        value = np.asarray(context[name])
        if value.shape != height.shape or value.dtype != bool:
            raise ValueError(name + " must be a matching boolean array")
        masks[name] = value
    mesh = prepare_mesh(context, height.shape)
    sources = np.repeat(np.arange(height.size), np.diff(mesh.indptr))
    clear = segments_clear(sources, mesh.indices, masks["valid_mask"])
    if not clear.all():
        sources, targets = sources[clear], mesh.indices[clear]
        mesh = replace(mesh, indptr=np.r_[0, np.cumsum(np.bincount(sources, minlength=height.size))],
                       indices=targets, edge_length_m=mesh.edge_length_m[clear])
    receiver = np.asarray(context["receiver"])
    if receiver.shape != height.shape or receiver.dtype.kind not in "iu":
        raise ValueError("receiver must be a matching integer array")
    if not receiver_edges_valid(receiver, mesh):
        raise ValueError("receiver must follow actual irregular graph edges")
    donors = np.flatnonzero(receiver.ravel() >= 0)
    if donors.size:
        targets = receiver.ravel()[donors]
        if not segments_clear(donors, targets, masks["valid_mask"]).all():
            raise ValueError("receiver crosses invalid support")
    # Delivered flood routes may cross raw uphill edges; retain them but require
    # an acyclic graph. Gravity transport itself uses positive raw slope only.
    indegree = np.bincount(receiver.ravel()[donors], minlength=height.size)
    queue = list(np.flatnonzero(indegree == 0))
    visited = 0
    for node in queue:
        visited += 1
        target = receiver.ravel()[node]
        if target >= 0:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))
    if visited != height.size:
        raise ValueError("receiver graph must be acyclic")
    return height, masks, mesh, receiver.ravel()

