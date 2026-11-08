"""Complete, bounded terrain-following paths for unchanged frozen coarse edges.

Paths are planning candidates. Their full identity and arc length are fixed before
clipping; downstream bed preparation must consume this exact represented polyline.
"""

from dataclasses import asdict, dataclass

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import dijkstra
from numba import njit

from terrain_pipeline.common_infra import identity

ALGORITHM = "frozen-edge-td-irregular-corridor-dijkstra-v2"


@dataclass(frozen=True)
class FrozenPathConfig:
    corridor_m: float = 500.
    maximum_nodes: int = 200000
    elevation_cost_per_m: float = .01
    uphill_cost_m_per_m: float = 8.
    displacement_cost_per_m2: float = .000002

    def __post_init__(self):
        if any(not np.isfinite(value) or value <= 0 for value in asdict(self).values()):
            raise ValueError("positive finite frozen path parameters required")


def _sample(height, points, origin, spacing):
    local = (points-origin)/spacing
    maximum = np.array(height.shape)[::-1]-1
    if np.any(local < 0) or np.any(local > maximum):
        raise ValueError("whole frozen path leaves genuine source support")
    cell = np.minimum(np.floor(local).astype(int), maximum.astype(int)-1)
    weight = local-cell
    x, z = cell.T
    wx, wz = weight.T
    return (1-wz)*((1-wx)*height[z,x]+wx*height[z,x+1])+wz*((1-wx)*height[z+1,x]+wx*height[z+1,x+1])


def _segment_samples(points, spacing):
    samples = []
    for first, second in zip(points[:-1], points[1:]):
        count = max(1, int(np.ceil(np.linalg.norm(second-first)/spacing)))
        samples.append(first+np.linspace(0,1,count+1)[:,None]*(second-first))
    return np.concatenate(samples)


def _segment_owner_samples(points, origin, spacing):
    """Visit every constant nearest-node ownership interval, including corners."""
    samples = []
    for first, second in zip(points[:-1], points[1:]):
        parameters = [0., 1.]
        for axis in (0, 1):
            if abs(second[axis]-first[axis]) <= 1e-12:
                continue
            low, high = sorted((first[axis], second[axis]))
            boundaries = origin[axis]+spacing*(np.arange(int(np.floor((low-origin[axis])/spacing-.5))+1,
                                                        int(np.floor((high-origin[axis])/spacing-.5))+1)+.5)
            parameters.extend(((boundaries-first[axis])/(second[axis]-first[axis])).tolist())
        parameters = np.unique(np.clip(parameters, 0., 1.))
        parameters = np.sort(np.r_[parameters, (parameters[:-1]+parameters[1:])/2])
        samples.append(first+parameters[:, None]*(second-first))
    return np.concatenate(samples)


@njit(cache=True)
def _actual_segments_clear(sources, targets, points, origin, spacing, valid):
    """Check every nearest-cell ownership interval along actual graph edges."""
    result = np.ones(len(sources), np.bool_)
    for i in range(len(sources)):
        first, second = points[sources[i]], points[targets[i]]
        parameters = [0., 1.]
        for axis in range(2):
            delta = second[axis] - first[axis]
            if abs(delta) <= 1e-12:
                continue
            low, high = min(first[axis], second[axis]), max(first[axis], second[axis])
            begin = int(np.floor((low-origin[axis])/spacing-.5))+1
            end = int(np.floor((high-origin[axis])/spacing-.5))+1
            for boundary in range(begin, end):
                t = (origin[axis]+spacing*(boundary+.5)-first[axis])/delta
                parameters.append(min(1., max(0., t)))
        ts = np.sort(np.array(parameters))
        for j in range(len(ts)*2-1):
            t = ts[j//2] if j % 2 == 0 else (ts[j//2]+ts[j//2+1])/2
            x = int(np.floor((first[0]+t*(second[0]-first[0])-origin[0])/spacing+.5))
            z = int(np.floor((first[1]+t*(second[1]-first[1])-origin[1])/spacing+.5))
            if x < 0 or z < 0 or z >= valid.shape[0] or x >= valid.shape[1] or not valid[z, x]:
                result[i] = False
                break
    return result


def _terrain_weighted_path(mesh, height, valid, start, targets, *, config,
                           displacement=None, actual_segment_frame=None, points=None,
                           initial_direction_xz=None, direction_weight=0., direction_decay_m=None,
                           max_turn_deg=None, start_directions_xz=(), end_directions_xz=(), turn_penalty_k=1.):
    """Shared directed terrain-cost search; return flattened account node IDs."""
    from terrain_pipeline.drainage import masked_mesh as masked_mesh
    allowed = masked_mesh(mesh, valid)
    sources = np.repeat(np.arange(height.size), np.diff(allowed.indptr))
    ends = allowed.indices
    keep = valid.ravel()[sources] & valid.ravel()[ends]
    sources, ends = sources[keep], ends[keep]
    lengths = allowed.edge_length_m[keep]
    if points is None:
        points = np.column_stack((mesh.node_x_m, mesh.node_z_m))
    if actual_segment_frame is not None:
        origin, spacing = actual_segment_frame
        keep = _actual_segments_clear(sources, ends, points, origin, spacing, valid)
        sources, ends = sources[keep], ends[keep]
        lengths = np.linalg.norm(points[ends]-points[sources], axis=1)
    ids = np.full(height.size, -1, np.int64)
    ids[valid.ravel()] = np.arange(valid.sum())
    floor = float(height[valid].min())
    multiplier = 1 + config.elevation_cost_per_m * (
        (height.ravel()[sources] + height.ravel()[ends]) / 2 - floor)
    if displacement is not None:
        multiplier += config.displacement_cost_per_m2 * (
            displacement.ravel()[sources] ** 2 + displacement.ravel()[ends] ** 2) / 2
    cost = lengths * multiplier
    cost += config.uphill_cost_m_per_m * np.maximum(0, height.ravel()[ends]-height.ravel()[sources])
    if initial_direction_xz is not None:
        direction = np.array(initial_direction_xz, dtype=float, copy=True)
        if (direction.shape != (2,) or not np.isfinite(direction).all()
                or np.linalg.norm(direction) == 0 or not np.isfinite(direction_weight)
                or direction_weight < 0 or direction_decay_m is None
                or not np.isfinite(direction_decay_m) or direction_decay_m <= 0):
            raise ValueError('invalid initial direction cost')
        direction /= np.linalg.norm(direction)
        edges = points[ends]-points[sources]
        alignment = np.clip(edges @ direction / lengths, -1., 1.)
        distance = np.linalg.norm((points[sources]+points[ends])/2-points[start], axis=1)
        cost += lengths * direction_weight * (1-alignment) * np.exp(-distance/direction_decay_m)
    if max_turn_deg is not None:
        from terrain_pipeline.river_path_geometry import heading_path
        return heading_path(sources, ends, cost, points, start, targets,
            max_turn_deg=max_turn_deg, start_directions=start_directions_xz,
            end_directions=end_directions_xz, turn_penalty_k=turn_penalty_k)
    count = int(valid.sum())
    graph = sparse.coo_matrix((cost, (ids[sources], ids[ends])), shape=(count, count)).tocsr()
    first = int(ids[start])
    distances, previous = dijkstra(graph, directed=True, indices=first, return_predecessors=True)
    candidates = np.asarray(targets, dtype=np.int64)
    candidate_ids = ids[candidates]
    finish = int(candidate_ids[np.argmin(distances[candidate_ids])])
    if not np.isfinite(distances[finish]):
        return None
    selected = [finish]
    while selected[-1] != first:
        selected.append(int(previous[selected[-1]]))
        if selected[-1] < 0 or len(selected) > count:
            raise ValueError("terrain path reconstruction failed")
    return np.flatnonzero(valid.ravel())[np.asarray(selected[::-1])]


def _no_crossing(points, existing_paths):
    # Vectorized orientation tests include collinear overlap and endpoint contact.
    for existing in existing_paths:
        other = np.asarray(existing, float)
        for first, second in zip(points[:-1], points[1:]):
            starts, ends = other[:-1], other[1:]
            def cross(a, b):
                return a[...,0]*b[...,1]-a[...,1]*b[...,0]
            a = cross(second-first, starts-first)
            b = cross(second-first, ends-first)
            c = cross(ends-starts, first-starts)
            d = cross(ends-starts, second-starts)
            overlap = (np.maximum(np.minimum(first,second),np.minimum(starts,ends)) <=
                       np.minimum(np.maximum(first,second),np.maximum(starts,ends))+1e-8).all(axis=1)
            contacts = overlap & (a*b <= 1e-12) & (c*d <= 1e-12)
            for index in np.flatnonzero(contacts):
                shared = [anchor for anchor in (points[0],points[-1])
                          if (np.array_equal(anchor,other[0]) or np.array_equal(anchor,other[-1]))
                          and (np.array_equal(anchor,first) or np.array_equal(anchor,second))
                          and (np.array_equal(anchor,starts[index]) or np.array_equal(anchor,ends[index]))]
                collinear = abs(a[index])+abs(b[index])+abs(c[index])+abs(d[index]) <= 1e-8
                if not shared or collinear:
                    raise ValueError("frozen candidate crosses or overlaps another represented edge")


def prepare_frozen_edge_path(plan, source_edge, height_m, origin_xz_m, spacing_m,
                             source_identity, *, owner_domain_id, protected_mask=None,
                             config=FrozenPathConfig(), existing_paths=()):
    """Route a complete registered edge; reject partial support or owner gaps."""
    height = np.asarray(height_m,float)
    owner = np.asarray(owner_domain_id)
    origin = np.asarray(origin_xz_m,float)
    protected = np.zeros(height.shape,bool) if protected_mask is None else np.asarray(protected_mask,bool)
    edge = np.asarray(source_edge,np.int64)
    if (height.ndim != 2 or min(height.shape)<2 or owner.shape != height.shape or protected.shape != height.shape
            or not np.isfinite(height).all() or origin.shape != (2,) or not np.isfinite(origin).all()
            or not np.isfinite(spacing_m) or spacing_m<=0 or edge.shape != (2,)):
        raise ValueError("aligned finite frozen path source required")
    receiver = np.asarray(plan["receiver"]).ravel()
    if np.any(edge<0) or np.any(edge>=len(receiver)) or receiver[edge[0]]!=edge[1] or not np.asarray(plan["river_mask"]).ravel()[edge[0]]:
        raise ValueError("registered frozen river edge required")
    coarse_owner = np.asarray(plan["owner_domain_id"]).ravel()
    domain = int(coarse_owner[edge[0]])
    if domain<0 or coarse_owner[edge[1]]!=domain:
        raise ValueError("whole dry frozen path requires same declared owner endpoints")
    columns = np.asarray(plan["height_m"]).shape[1]
    anchors = np.asarray(plan["origin_xz_m"])+plan["spacing_m"]*np.column_stack((edge%columns,edge//columns))
    _sample(height,anchors,origin,spacing_m)
    vector = anchors[1]-anchors[0]
    length = np.linalg.norm(vector)
    z,x = np.indices(height.shape)
    points = origin+spacing_m*np.stack((x,z),axis=-1)
    progress = np.sum((points-anchors[0])*vector,axis=-1)/length**2
    distance = np.linalg.norm(points-anchors[0]-np.clip(progress,0,1)[...,None]*vector,axis=-1)
    valid = (distance<=config.corridor_m)&(progress>=0)&(progress<=1)&(owner==domain)&~protected
    endpoint_cells = np.rint((anchors-origin)/spacing_m).astype(int)
    if np.any(endpoint_cells<0) or np.any(endpoint_cells>=np.array(height.shape)[::-1]):
        raise ValueError("frozen endpoint native attachment leaves source")
    for cx,cz in endpoint_cells:
        if owner[cz,cx]!=domain or protected[cz,cx] or distance[cz,cx]>config.corridor_m:
            raise ValueError("frozen endpoint attachment crosses owner or protection")
        valid[cz,cx] = True
    count = int(valid.sum())
    if count>config.maximum_nodes:
        raise ValueError("whole-edge path node budget exceeded")
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    mesh = grid_mesh(height.shape, x0_m=origin[0], z0_m=origin[1],
                     dx_m=spacing_m, world_seed=int(plan.get("seed", 20261020)))
    start, finish = [int(cz * height.shape[1] + cx) for cx, cz in endpoint_cells]
    selected = _terrain_weighted_path(mesh, height, valid, start, [finish],
                                      config=config, displacement=distance)
    if selected is None:
        raise ValueError("no legal complete frozen-edge corridor path")
    graph_points = np.column_stack((mesh.node_x_m, mesh.node_z_m))
    native_points = graph_points[selected].copy()
    native_points[0], native_points[-1] = anchors[0], anchors[1]
    full = np.vstack((anchors[0],native_points,anchors[1]))
    full = full[np.r_[True,np.linalg.norm(np.diff(full,axis=0),axis=1)>1e-8]]
    samples = _segment_owner_samples(full,origin,spacing_m)
    _sample(height,samples,origin,spacing_m)
    cells = np.rint((samples-origin)/spacing_m).astype(int)
    if np.any(owner[cells[:,1],cells[:,0]]!=domain) or np.any(protected[cells[:,1],cells[:,0]]):
        raise ValueError("frozen path segment crosses owner or protection")
    _no_crossing(full,existing_paths)
    arc = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(full,axis=0),axis=1))]
    profile_arc = np.unique(np.r_[arc, np.linspace(0., arc[-1], int(np.ceil(arc[-1]))+1)])
    profile_points = np.column_stack([np.interp(profile_arc, arc, full[:, axis]) for axis in (0, 1)])
    arrays = {"points_xz_m": full, "arclength_m": arc,
              "source_height_m": _sample(height, full, origin, spacing_m),
              "profile_arclength_m": profile_arc,
              "profile_source_m": _sample(height, profile_points, origin, spacing_m)}
    metadata = {"algorithm":ALGORITHM,"plan_identity":plan["identity_sha256"],"source_identity":source_identity,
                "source_edge":edge.tolist(),"owner_domain_id":domain,"config":asdict(config),
                "source_origin_xz_m":origin.tolist(),"source_shape":list(height.shape),"source_spacing_m":float(spacing_m),
                "complete_edge":True,"node_count":count,"represented_length_m":float(arc[-1]),
                "anchor_policy":"exact frozen endpoints attached to source-frame irregular graph corridor",
                "world_seed":int(plan.get("seed", 20261020)),
                "cost_units":"edge cost m; elevation multiplier 1/m; uphill m/m; displacement multiplier 1/m2",
                "protection_identity":identity({"owner_domain_id":owner,"protected_mask":protected},{}),
                "bed_certified":False,"hydraulic_certified":False}
    return {"arrays":arrays,"metadata":metadata,"identity":identity(arrays,metadata)}


def clip_frozen_edge_path(path, start_arclength_m, end_arclength_m):
    """Clip by global arc length, never reroute or recompute a window identity."""
    arrays,metadata = path["arrays"],path["metadata"]
    if path["identity"]!=identity(arrays,metadata):
        raise ValueError("whole frozen path identity differs")
    arc,points = arrays["arclength_m"],arrays["points_xz_m"]
    if not 0<=start_arclength_m<end_arclength_m<=arc[-1]:
        raise ValueError("bounded increasing whole-path arc interval required")
    selected = np.r_[start_arclength_m,arc[(arc>start_arclength_m)&(arc<end_arclength_m)],end_arclength_m]
    clipped = np.column_stack([np.interp(selected,arc,points[:,axis]) for axis in (0,1)])
    return {"whole_path_identity":path["identity"],"source_edge":metadata["source_edge"],
            "points_xz_m":clipped,"arclength_m":selected,"edge_fractions":selected/arc[-1]}


def validate_frozen_path_nodes(path, plan, points, source_edges, fractions, receiver=None):
    """Prove bed nodes and every represented chord belong to the frozen polyline."""
    arrays, metadata = path["arrays"], path["metadata"]
    if path["identity"] != identity(arrays, metadata) or metadata["plan_identity"] != plan["identity_sha256"]:
        raise ValueError("whole frozen path or plan identity differs")
    edge = np.asarray(metadata["source_edge"], int)
    if not np.all(np.asarray(source_edges) == edge):
        raise ValueError("bed nodes refer to another whole frozen edge")
    arc = arrays["arclength_m"]
    whole_points = arrays["points_xz_m"]
    positions = np.asarray(fractions)*arc[-1]
    expected = np.column_stack([np.interp(positions, arc, whole_points[:, axis]) for axis in (0, 1)])
    if not np.allclose(points, expected, rtol=0, atol=1e-7):
        raise ValueError("bed nodes differ from whole frozen path arc clipping")
    if receiver is not None:
        for node in np.flatnonzero(np.asarray(receiver) >= 0):
            other = receiver[node]
            chord = np.linalg.norm(np.asarray(points)[other]-np.asarray(points)[node])
            if positions[other] <= positions[node] or abs(chord-(positions[other]-positions[node])) > 1e-7:
                raise ValueError("bed piece shortcuts a represented frozen path bend")


def frozen_path_profiles(plan, paths, height_m, origin_xz_m, spacing_m, *, sample_spacing_m=1.,
                         clip_origin_xz_m=None, clip_shape=None):
    """Use one whole-source bed profile, then clip it to the computational window."""
    height = np.asarray(height_m, float)
    source_origin = np.asarray(origin_xz_m, float)
    origin = source_origin if clip_origin_xz_m is None else np.asarray(clip_origin_xz_m, float)
    shape = height.shape if clip_shape is None else tuple(clip_shape)
    maximum = origin+(np.array(shape)[::-1]-1)*spacing_m
    profiles = []
    for path in paths:
        arrays, metadata = path["arrays"], path["metadata"]
        validate_frozen_path_nodes(path, plan, arrays["points_xz_m"],
            np.tile(metadata["source_edge"], (len(arrays["points_xz_m"]), 1)),
            arrays["arclength_m"]/arrays["arclength_m"][-1])
        intervals = []
        for index, (start, finish) in enumerate(zip(arrays["points_xz_m"][:-1], arrays["points_xz_m"][1:])):
            vector = finish-start
            low, high = 0., 1.
            for axis in (0, 1):
                if abs(vector[axis]) < 1e-12:
                    if not origin[axis] <= start[axis] <= maximum[axis]:
                        high = -1.
                else:
                    limits = sorted(((origin[axis]-start[axis])/vector[axis], (maximum[axis]-start[axis])/vector[axis]))
                    low, high = max(low, limits[0]), min(high, limits[1])
            if high > low:
                base = arrays["arclength_m"][index]
                length = arrays["arclength_m"][index+1]-base
                intervals.append((base+low*length, base+high*length))
        if not intervals:
            continue
        if any(abs(first[1]-second[0]) > 1e-7 for first, second in zip(intervals[:-1], intervals[1:])):
            raise ValueError("whole frozen path reenters this window; explicit disconnected clips required")
        low, high = intervals[0][0], intervals[-1][1]
        full_arc = arrays["profile_arclength_m"]
        full_source = arrays["profile_source_m"]
        full_bed = np.minimum.accumulate(full_source+.001*full_arc)-.001*full_arc-.5
        arc = np.unique(np.r_[low, high, arrays["arclength_m"][(arrays["arclength_m"]>low)&(arrays["arclength_m"]<high)],
                              np.linspace(low, high, int(np.ceil((high-low)/sample_spacing_m))+1)])
        points = np.column_stack([np.interp(arc, arrays["arclength_m"], arrays["points_xz_m"][:, axis]) for axis in (0, 1)])
        source = _sample(height, points, source_origin, spacing_m)
        profiles.append({"source_edge": metadata["source_edge"], "fractions": arc/arrays["arclength_m"][-1],
                         "points_xz_m": points, "source_m": source, "bed_m": np.interp(arc, full_arc, full_bed),
                         "length_m": float(high-low), "full_coarse_edge_length_m": float(arrays["arclength_m"][-1]),
                         "whole_path_identity": path["identity"], "whole_path_arclength_m": arc})
    return profiles
