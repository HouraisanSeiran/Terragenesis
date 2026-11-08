"""Render-only bounded paths from saved active D4 receiver edges."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, readonly, save_bundle
from terrain_pipeline.basin_topology import validate_basin_hierarchy as validate_basin_hierarchy
from terrain_pipeline.td_native_channel_geometry import validate_channel_geometry


MAX_POINTS = 262144
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")


@dataclass(frozen=True)
class ValleyPathRecipe:
    resample_spacing_m: float = 2.
    corner_fraction: float = .2
    max_corridor_fraction: float = .25

    def __post_init__(self):
        if (self.resample_spacing_m != 2. or self.corner_fraction != .2 or
                self.max_corridor_fraction != .25):
            raise ValueError("unsupported valley path recipe")


def _window(window, shape):
    if window is None:
        return [0, shape[1] - 1, 0, shape[0] - 1]
    if (len(window) != 4 or any(type(value) is not int for value in window) or
            not (0 <= window[0] <= window[1] < shape[1] and 0 <= window[2] <= window[3] < shape[0])):
        raise ValueError("invalid inclusive coarse-cell window")
    return list(window)


def _sample_native(hierarchy, geometry, points_xz, *, strict=True, return_owner=False):
    arrays = hierarchy["arrays"]
    rows, columns = arrays["height_m"].shape
    spacing = geometry["metadata"]["spacing_m"]
    origin = geometry["metadata"]["origin_m_xz"]
    grid = (points_xz - origin) / spacing
    if not np.isfinite(grid).all() or np.any(grid < 0) or np.any(grid[:, 0] > columns - 1) or np.any(grid[:, 1] > rows - 1):
        return None
    lower = np.floor(grid).astype(np.int64)
    upper = np.minimum(lower + 1, [columns - 1, rows - 1])
    corners = np.column_stack((lower[:, 1] * columns + lower[:, 0],
                               lower[:, 1] * columns + upper[:, 0],
                               upper[:, 1] * columns + lower[:, 0],
                               upper[:, 1] * columns + upper[:, 0]))
    valid = arrays["valid_mask"].ravel()[corners]
    protected = arrays["protected_mask"].ravel()[corners]
    boundary = arrays["open_boundary_mask"].ravel()[corners]
    owners = arrays["contribution_owner"].ravel()[corners]
    child_count = np.bincount(arrays["node_parent"][arrays["node_parent"] >= 0],
                              minlength=len(arrays["node_parent"]))
    if not valid.all():
        return None
    if strict and (protected.any() or boundary.any() or np.any(owners != owners[:, :1]) or
                   np.any(owners < 0) or np.any(child_count[owners] != 0)):
        return None
    bed = arrays["height_m"].ravel()[corners]
    fraction = grid - lower
    north = bed[:, 0] * (1 - fraction[:, 0]) + bed[:, 1] * fraction[:, 0]
    south = bed[:, 2] * (1 - fraction[:, 0]) + bed[:, 3] * fraction[:, 0]
    heights = north * (1 - fraction[:, 1]) + south * fraction[:, 1]
    if return_owner:
        return heights, owners[:, 0]
    return heights


def _continuous_checks(points, origin, spacing):
    checks = [points[0]]
    for start, end in zip(points[:-1], points[1:]):
        parameters = [0., 1.]
        for axis in range(2):
            if start[axis] == end[axis]:
                continue
            lower = math.floor((min(start[axis], end[axis]) - origin[axis]) / spacing)
            upper = math.ceil((max(start[axis], end[axis]) - origin[axis]) / spacing)
            for gridline in range(lower, upper + 1):
                fraction = (origin[axis] + gridline * spacing - start[axis]) / (end[axis] - start[axis])
                if 0 < fraction < 1:
                    parameters.append(fraction)
        parameters = sorted(set(parameters))
        for first, last in zip(parameters[:-1], parameters[1:]):
            checks.append(start + (first + last) / 2 * (end - start))
            checks.append(start + last * (end - start))
    return np.asarray(checks)


def _distance_to_path(points, original):
    shortest = np.full(len(points), np.inf)
    for start, end in zip(original[:-1], original[1:]):
        delta = end - start
        fraction = np.clip(((points - start) @ delta) / (delta @ delta), 0, 1)
        shortest = np.minimum(shortest, np.linalg.norm(points - start - fraction[:, None] * delta, axis=1))
    return shortest


def _within_corridor(points, original, limit):
    distances = _distance_to_path(points, original)
    segment_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return bool(np.all(distances <= limit) and
                np.all(np.nextafter((distances[:-1] + distances[1:] + segment_lengths) / 2,
                                    np.inf) <= limit))


def _resample_segment(start, end, spacing):
    count = max(1, math.ceil(float(np.linalg.norm(end - start)) / spacing))
    return start[None, :] + np.linspace(0, 1, count + 1)[:, None] * (end - start)[None, :]


def _turn(first, second):
    return first[0] * second[1] - first[1] * second[0]


def _candidate(original, spacing, recipe):
    pieces = [original[0:1]]
    corners = 0
    current = original[0]
    for index in range(1, len(original) - 1):
        previous, pivot, following = original[index - 1:index + 2]
        incoming = pivot - previous
        outgoing = following - pivot
        if abs(_turn(incoming, outgoing)) < 1e-8:
            continue
        before = pivot - recipe.corner_fraction * incoming
        after = pivot + recipe.corner_fraction * outgoing
        pieces.append(_resample_segment(current, before, recipe.resample_spacing_m)[1:])
        control_length = float(np.linalg.norm(before - pivot) + np.linalg.norm(after - pivot))
        count = max(2, math.ceil(control_length / recipe.resample_spacing_m))
        parameter = np.linspace(0, 1, count + 1)[1:]
        curve = ((1 - parameter) ** 2)[:, None] * before + \
                (2 * (1 - parameter) * parameter)[:, None] * pivot + parameter[:, None] ** 2 * after
        pieces.append(curve)
        current = after
        corners += 1
    pieces.append(_resample_segment(current, original[-1], recipe.resample_spacing_m)[1:])
    return np.concatenate(pieces), corners


def _original_samples(original, spacing):
    return np.concatenate([original[0:1]] +
                          [_resample_segment(start, end, spacing)[1:] for start, end in zip(original[:-1], original[1:])])


def build_valley_paths(geometry, hierarchy, *, window=None, recipe=ValleyPathRecipe()):
    validate_channel_geometry(geometry)
    validate_basin_hierarchy(hierarchy)
    metadata, graph = geometry["metadata"], geometry["arrays"]
    source = hierarchy["arrays"]
    if (metadata["hierarchy_identity"] != hierarchy["identity_sha256"] or
            metadata["grid_shape"] != list(source["height_m"].shape) or
            metadata["spacing_m"] != hierarchy["metadata"]["spacing_m"] or
            metadata["origin_m_xz"] != hierarchy["metadata"]["origin_m_xz"] or
            not np.array_equal(graph["node_cell_ids"], np.flatnonzero(source["valid_mask"].ravel())) or
            not np.array_equal(graph["node_native_bed_m"], source["height_m"].ravel()[graph["node_cell_ids"]]) or
            not np.array_equal(graph["node_receiver_cell_ids"], source["receiver"][graph["node_cell_ids"]])):
        raise ValueError("geometry/native hierarchy source mismatch")
    bounds = _window(window, source["height_m"].shape)
    edges = graph["edge_cell_ids"]
    active = np.flatnonzero(graph["edge_geometry_active"])
    columns = metadata["grid_shape"][1]
    included = [int(index) for index in active if all(bounds[0] <= cell % columns <= bounds[1] and
                                                        bounds[2] <= cell // columns <= bounds[3]
                                                        for cell in edges[index])]
    included_set = set(included)
    node_ids = graph["node_cell_ids"]
    incoming = np.zeros(len(node_ids), np.int64)
    outgoing = np.full(len(node_ids), -1, np.int64)
    for edge_index in included:
        start, end = np.searchsorted(node_ids, edges[edge_index])
        incoming[end] += 1
        outgoing[start] = edge_index
    edge_start = np.searchsorted(node_ids, edges[:, 0])
    edge_end = np.searchsorted(node_ids, edges[:, 1])
    visited = set()
    chains = []
    for edge_index in included:
        start = edge_start[edge_index]
        if incoming[start] == 1 and outgoing[start] >= 0 and not graph["node_engineering_boundary"][start]:
            continue
        chain = []
        current = edge_index
        while current in included_set and current not in visited:
            visited.add(current)
            chain.append(current)
            target = edge_end[current]
            if incoming[target] != 1 or outgoing[target] < 0 or graph["node_engineering_boundary"][target] or graph["node_internal_sink"][target]:
                break
            current = outgoing[target]
        chains.append(chain)
    if len(visited) != len(included):
        raise ValueError("active graph chain coverage incomplete")
    offsets = [0]
    edge_offsets = [0]
    all_points = []
    chain_edges = []
    accepted = []
    corner_counts = []
    original_corners = 0
    for chain in chains:
        cells = [int(edges[chain[0], 0])] + [int(edges[index, 1]) for index in chain]
        node_indices = np.searchsorted(node_ids, cells)
        original = graph["node_world_xyz_m"][node_indices][:, [0, 2]]
        original_corners += sum(abs(_turn(original[index] - original[index - 1],
                                          original[index + 1] - original[index])) > 1e-8
                                for index in range(1, len(original) - 1))
        candidate, corners = _candidate(original, metadata["spacing_m"], recipe)
        corner_counts.append(corners)
        safe = corners > 0 and _within_corridor(candidate, original, metadata["spacing_m"] * recipe.max_corridor_fraction)
        if safe:
            checks = _continuous_checks(candidate, metadata["origin_m_xz"], metadata["spacing_m"])
            sampled = _sample_native(hierarchy, geometry, checks, return_owner=True)
            safe = sampled is not None and np.all(sampled[1] == sampled[1][0])
            if safe:
                height = _sample_native(hierarchy, geometry, candidate)
        if not safe:
            candidate = _original_samples(original, recipe.resample_spacing_m)
            height = _sample_native(hierarchy, geometry, candidate, strict=False)
            if height is None:
                raise ValueError("original path has unknown native bed stencil")
        candidate[0] = original[0]
        candidate[-1] = original[-1]
        height[0] = graph["node_native_bed_m"][node_indices[0]]
        height[-1] = graph["node_native_bed_m"][node_indices[-1]]
        if offsets[-1] + len(candidate) > MAX_POINTS:
            raise ValueError("valley path point budget exceeded")
        all_points.append(np.column_stack((candidate[:, 0], height, candidate[:, 1])))
        offsets.append(offsets[-1] + len(candidate))
        chain_edges.extend(chain)
        edge_offsets.append(len(chain_edges))
        accepted.append(safe)
    arrays = dict(points_xyz_m=np.concatenate(all_points) if all_points else np.empty((0, 3), np.float64),
                  point_offsets=np.asarray(offsets, np.int64), chain_edge_offsets=np.asarray(edge_offsets, np.int64),
                  chain_edge_indices=np.asarray(chain_edges, np.int64), chain_edge_cell_ids=edges[chain_edges],
                  chain_endpoint_cell_ids=np.asarray([[edges[chain[0], 0], edges[chain[-1], 1]] for chain in chains], np.int64).reshape(-1, 2),
                  chain_accepted=np.asarray(accepted, bool), chain_original_corner_count=np.asarray(corner_counts, np.int64),
                  included_active_edge_indices=np.asarray(included, np.int64))
    result_metadata = dict(schema="td-native-channel-valley-paths-v1", algorithm="bounded-quadratic-corner-v2-conservative-cones",
                           recipe=asdict(recipe), window=bounds, omitted_active_edges=int(len(active) - len(included)),
                           total_active_edges=int(len(active)), original_d4_corners=int(original_corners),
                           accepted_chains=int(sum(accepted)), fallback_chains=int(len(chains) - sum(accepted)),
                           accepted_curved_chains=int(sum(ok and count > 0 for ok, count in zip(accepted, corner_counts))),
                           accepted_smoothed_corners=int(sum(count for ok, count in zip(accepted, corner_counts) if ok)),
                           geometry_identity=geometry["identity_sha256"], hierarchy_identity=hierarchy["identity_sha256"],
                           hour_page_identity=metadata["hour_page_identity"], forcing_identity=metadata["forcing_identity"],
                           grid_shape=metadata["grid_shape"], spacing_m=metadata["spacing_m"],
                           origin_m_xz=metadata["origin_m_xz"],
                           graph_semantics="saved active receiver edges covered once; Q and source graph unchanged",
                           bed_semantics="native coarse bilinear bed only; no candidate carving",
                           source_scope="saved single-hour geometry and original TD hierarchy; selected coarse window only",
                           fallback_semantics="original active graph polyline resampled for display; protected or cross-leaf original links remain source evidence, not a safe new curve",
                           scope="render-only visual path candidate; no water or natural certification",
                           coordinates="physical metres [x,y,z]; x east, y up, z south",
                           **{name: False for name in FLAGS})
    result = dict(arrays=arrays, metadata=result_metadata, identity_sha256=identity(arrays, result_metadata))
    validate_valley_paths(result)
    result["arrays"] = {name: readonly(value) for name, value in arrays.items()}
    return result


def validate_valley_paths(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != "td-native-channel-valley-paths-v1" or any(metadata.get(flag) is not False for flag in FLAGS):
        raise ValueError("valley paths schema/scope invalid")
    ValleyPathRecipe(**metadata["recipe"])
    if (len(metadata["grid_shape"]) != 2 or any(type(value) is not int or value < 1 for value in metadata["grid_shape"]) or
            len(metadata["origin_m_xz"]) != 2 or not np.isfinite(metadata["origin_m_xz"]).all() or
            not math.isfinite(metadata["spacing_m"]) or metadata["spacing_m"] <= 0):
        raise ValueError("valley path coordinates invalid")
    _window(metadata["window"], metadata["grid_shape"])
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("valley paths identity mismatch")
    points = arrays["points_xyz_m"]
    offsets = arrays["point_offsets"]
    edge_offsets = arrays["chain_edge_offsets"]
    chain_edges = arrays["chain_edge_indices"]
    edge_cells = arrays["chain_edge_cell_ids"]
    included = arrays["included_active_edge_indices"]
    chains = len(offsets) - 1
    if (points.dtype != np.float64 or points.ndim != 2 or points.shape[1] != 3 or len(points) > MAX_POINTS or
            not np.isfinite(points).all() or offsets.dtype != np.int64 or edge_offsets.dtype != np.int64 or
            offsets.ndim != 1 or edge_offsets.ndim != 1 or len(offsets) == 0 or len(edge_offsets) != len(offsets) or
            offsets[0] != 0 or edge_offsets[0] != 0 or offsets[-1] != len(points) or edge_offsets[-1] != len(chain_edges) or
            np.any(np.diff(offsets) < 2) or np.any(np.diff(edge_offsets) < 1) or
            edge_cells.shape != (len(chain_edges), 2) or edge_cells.dtype != np.int64 or
            arrays["chain_endpoint_cell_ids"].shape != (chains, 2) or
            arrays["chain_accepted"].shape != (chains,) or arrays["chain_accepted"].dtype != bool or
            arrays["chain_original_corner_count"].shape != (chains,) or
            chain_edges.dtype != np.int64 or included.dtype != np.int64 or
            not np.array_equal(np.sort(chain_edges), included) or
            len(np.unique(included)) != len(included) or
            np.any(included < 0) or np.any(included >= math.prod(metadata["grid_shape"])) or
            metadata["total_active_edges"] != len(included) + metadata["omitted_active_edges"] or
            metadata["accepted_chains"] != int(arrays["chain_accepted"].sum()) or
            metadata["fallback_chains"] != chains - metadata["accepted_chains"] or
            metadata["original_d4_corners"] != int(arrays["chain_original_corner_count"].sum()) or
            metadata["accepted_curved_chains"] != int(np.count_nonzero(arrays["chain_accepted"] & (arrays["chain_original_corner_count"] > 0))) or
            metadata["accepted_smoothed_corners"] != int(arrays["chain_original_corner_count"][arrays["chain_accepted"]].sum())):
        raise ValueError("valley paths structure/coverage invalid")
    for chain in range(chains):
        first, last = edge_offsets[chain:chain + 2]
        selected = edge_cells[first:last]
        if (not np.array_equal(selected[:-1, 1], selected[1:, 0]) or
                not np.array_equal(arrays["chain_endpoint_cell_ids"][chain], [selected[0, 0], selected[-1, 1]])):
            raise ValueError("valley path graph chain invalid")
    endpoint_positions = {}
    columns = metadata["grid_shape"][1]
    rows = metadata["grid_shape"][0]
    spacing = metadata["spacing_m"]
    origin = metadata["origin_m_xz"]
    if (np.any(arrays["chain_endpoint_cell_ids"] < 0) or
            np.any(arrays["chain_endpoint_cell_ids"] >= rows * columns)):
        raise ValueError("valley path coordinates invalid")
    for chain in range(chains):
        start, end = offsets[chain:chain + 2]
        for cell, position in zip(arrays["chain_endpoint_cell_ids"][chain], (points[start], points[end - 1])):
            expected = (origin[0] + cell % columns * spacing, origin[1] + cell // columns * spacing)
            if not np.array_equal(position[[0, 2]], expected):
                raise ValueError("valley path endpoint coordinate invalid")
            old = endpoint_positions.setdefault(int(cell), position)
            if not np.array_equal(old, position):
                raise ValueError("valley path shared node mismatch")
    return True


def save_valley_paths(path, result):
    save_bundle(path, result, validator=validate_valley_paths)


def load_valley_paths(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_valley_paths,
                         max_bytes=128 * 1024 ** 2)
    if result["identity_sha256"] != expected_identity or file_sha256(path) != expected_sha256:
        raise ValueError("valley paths external pin mismatch")
    return result
