"""Source-constrained swept river sections in local metric (u, v) coordinates.

Physical widths remain metres even when narrower than a DEM cell. A separate
four-connected cell traversal represents those channels on the saved raster;
its area must not be interpreted as a hydraulic width or excavation estimate
at finer resolution. This constructs a declared bed, not a hydraulic solution.
"""

import heapq

import numpy as np
from scipy import ndimage as ndi

from terrain_pipeline.delta_network_skeleton_v3 import edge_points


def _smoothstep(value):
    value = np.clip(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def _sample(spec, field, points, order=1):
    indices = (np.asarray(points) - [spec.u0_m, spec.v0_m]) / spec.spacing_m - 0.5
    return ndi.map_coordinates(field, indices.T, order=order, mode="nearest")


def _stations(points, step_m):
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    if np.any(lengths <= 0.0):
        raise ValueError("river centreline contains duplicate points")
    distance = np.r_[0.0, np.cumsum(lengths)]
    stations = np.linspace(0.0, distance[-1], max(2, int(np.ceil(distance[-1] / step_m)) + 1))
    positions = np.column_stack([np.interp(stations, distance, points[:, axis]) for axis in (0, 1)])
    tangent = np.gradient(positions, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    return stations, positions, normal


def _topological_nodes(node_count, edge_from, edge_to):
    outgoing = [[] for _ in range(node_count)]
    indegree = np.bincount(edge_to, minlength=node_count)
    for edge, node in enumerate(edge_from):
        outgoing[node].append(edge)
    ready = list(np.flatnonzero(indegree == 0))
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for edge in outgoing[node]:
            target = edge_to[edge]
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, int(target))
    if len(order) != node_count:
        raise ValueError("river sections require a directed acyclic graph")
    return order, outgoing


def _junction_profile(distance, nominal, start, end):
    # Limit blending so a small distributary never inherits its parent's width.
    transition = min(max(3.0 * nominal, 120.0), 0.4 * distance[-1])
    start = np.clip(start, 0.8 * nominal, 1.2 * nominal)
    end = np.clip(end, 0.8 * nominal, 1.2 * nominal)
    return (
        nominal
        + (start - nominal) * (1.0 - _smoothstep(distance / transition))
        + (end - nominal) * (1.0 - _smoothstep((distance[-1] - distance) / transition))
    )


def _cell_path(spec, start, end, surface, protected):
    """Traverse intersected cells, resolving exact corners to four-connectivity."""
    origin = np.array([spec.u0_m, spec.v0_m])
    first = (start - origin) / spec.spacing_m
    delta = (end - start) / spec.spacing_m
    cell = np.floor(first).astype(int)
    target = np.floor(first + delta).astype(int)
    step = np.sign(delta).astype(int)
    crossing = np.full(2, np.inf)
    stride = np.full(2, np.inf)
    for axis in (0, 1):
        if step[axis]:
            boundary = cell[axis] + (step[axis] > 0)
            crossing[axis] = (boundary - first[axis]) / delta[axis]
            stride[axis] = 1.0 / abs(delta[axis])
    result = [(tuple(cell), 0.0)]
    while np.any(cell != target):
        axes = [int(np.argmin(crossing))]
        if abs(crossing[0] - crossing[1]) < 1e-10:
            def obstruction(axis):
                candidate = cell.copy()
                candidate[axis] += step[axis]
                row, col = candidate
                if not (0 <= row < spec.nu and 0 <= col < spec.nv) or protected[row, col]:
                    return np.inf
                return surface[row, col]
            axes = sorted((0, 1), key=obstruction)
        for axis in axes:
            if cell[axis] == target[axis]:
                continue
            fraction = float(np.clip(crossing[axis], 0.0, 1.0))
            cell[axis] += step[axis]
            crossing[axis] += stride[axis]
            result.append((tuple(cell), fraction))
    return result


def rasterize_channels(
    spec, surface, source_bed, source_ocean, graph, *, protected_elevation_m=45.0, freeboard_m=0.8,
    lowland_excavation_ceiling_m=12.0,
):
    """Return bed, channel mask, actual stage/depth, physical width and audit.

    Source land at or above ``protected_elevation_m`` is immutable. Sections
    contract against that land and against banks above their local clearance.
    Unrepresentable centreline crossings are reported rather than excavated.
    The water stage is a filtered valley profile, shared at graph junctions
    and non-increasing along every directed reach, with sea-level mouths.
    Reconstructable lowland up to ``lowland_excavation_ceiling_m`` can be cut
    without raising that stage; higher ground needs actual bank clearance.
    """
    surface = np.asarray(surface, dtype=float)
    source_bed = np.asarray(source_bed, dtype=float)
    source_ocean = np.asarray(source_ocean, dtype=bool)
    shape = (spec.nu, spec.nv)
    if (
        surface.shape != shape or source_bed.shape != shape or source_ocean.shape != shape
        or not np.isfinite(surface).all() or not np.isfinite(source_bed).all()
        or not np.isfinite([spec.spacing_m, freeboard_m, protected_elevation_m,
                            lowland_excavation_ceiling_m]).all()
        or spec.spacing_m <= 0.0 or freeboard_m < 0.0
        or not 0 <= lowland_excavation_ceiling_m < protected_elevation_m
    ):
        raise ValueError("matching finite source/surface grids and valid metric parameters required")
    edge_from = np.asarray(graph.edge_from, dtype=int)
    edge_to = np.asarray(graph.edge_to, dtype=int)
    widths = np.asarray(graph.edge_w, dtype=float)
    depths = np.asarray(graph.edge_h, dtype=float)
    node_count = len(graph.node_uv)
    if (
        edge_from.shape != edge_to.shape or widths.shape != edge_from.shape
        or depths.shape != edge_from.shape or not len(widths)
        or not np.isfinite(np.r_[widths, depths]).all() or np.any(widths <= 0) or np.any(depths <= 0)
        or np.any(edge_from < 0) or np.any(edge_to < 0)
        or np.any(edge_from >= node_count) or np.any(edge_to >= node_count)
    ):
        raise ValueError("finite positive channel dimensions and valid graph nodes required")
    order, outgoing = _topological_nodes(node_count, edge_from, edge_to)
    protected = (~source_ocean) & (source_bed >= protected_elevation_m)
    incident = [[] for _ in range(node_count)]
    for edge, (start, end) in enumerate(zip(edge_from, edge_to)):
        incident[start].append(edge)
        incident[end].append(edge)
    node_width = np.array([np.median(widths[edges]) if edges else 0.0 for edges in incident])
    node_depth = np.array([np.median(depths[edges]) if edges else 0.0 for edges in incident])
    profiles = []
    node_stage = np.full(node_count, np.inf)
    for edge in range(len(widths)):
        points = np.asarray(edge_points(graph, edge), dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 2 or not np.isfinite(points).all():
            raise ValueError("finite centreline polylines required")
        # Bound section interpolation in physical metres as well as pixels;
        # coarse rasters must still resolve a 120 m junction transition.
        distance, positions, normal = _stations(points, min(spec.spacing_m * 0.45, 18.0))
        start, end = edge_from[edge], edge_to[edge]
        width = _junction_profile(distance, widths[edge], node_width[start], node_width[end])
        depth = _junction_profile(distance, depths[edge], node_depth[start], node_depth[end])
        # A low cross-valley quantile prevents an adjacent hill from raising
        # the channel stage. This never averages a high bank into the river.
        offsets = np.linspace(-0.5, 0.5, max(9, int(np.ceil(width.max() / (0.4 * spec.spacing_m))) + 1))
        probes = positions[:, None, :] + normal[:, None, :] * width[:, None, None] * offsets[None, :, None]
        # The DEM is cell-centred: do not bilinearly smear a cliff into its
        # low neighbouring cell before determining the river's water level.
        sampled = _sample(spec, surface, probes.reshape(-1, 2), order=0).reshape(probes.shape[:2])
        valley = np.minimum(_sample(spec, surface, positions, order=0), np.quantile(sampled, 0.2, axis=1))
        raw_stage = np.maximum(valley - freeboard_m, 0.0)
        sigma = max(1.0, min(widths[edge], 3.0 * spec.spacing_m) / (distance[1] - distance[0]))
        raw_stage = ndi.gaussian_filter1d(ndi.minimum_filter1d(raw_stage, size=3), sigma, mode="nearest")
        node_stage[start] = min(node_stage[start], raw_stage[0])
        node_stage[end] = min(node_stage[end], raw_stage[-1])
        profiles.append(dict(distance_m=distance, uv_m=positions, normal=normal, width_m=width,
                             design_depth_m=depth, raw_stage_m=raw_stage))
    node_stage[~np.isfinite(node_stage)] = 0.0
    node_stage[np.asarray(graph.mouth_nodes, dtype=int)] = 0.0
    for node in order:
        for edge in outgoing[node]:
            node_stage[edge_to[edge]] = min(node_stage[edge_to[edge]], node_stage[node],
                                           float(profiles[edge]["raw_stage_m"].min()))

    bed = surface.copy()
    stage = np.full(shape, np.inf)
    physical_width = np.zeros(shape)
    channel = np.zeros(shape, dtype=bool)
    coverage_only = np.zeros(shape, dtype=bool)
    physical_coverage = np.zeros(shape, dtype=bool)
    represented_centreline = np.zeros(shape, dtype=bool)
    edge_reports = []
    for edge, profile in enumerate(profiles):
        distance = profile["distance_m"]
        positions = profile["uv_m"]
        width = profile["width_m"]
        depth = profile["design_depth_m"]
        water_stage = np.minimum.accumulate(np.minimum(profile.pop("raw_stage_m"), node_stage[edge_from[edge]]))
        transition = min(max(3.0 * widths[edge], 120.0), distance[-1])
        water_stage -= (water_stage[-1] - node_stage[edge_to[edge]]) * _smoothstep(
            (distance - (distance[-1] - transition)) / transition
        )
        profile["stage_m"] = water_stage
        clearance = np.maximum(water_stage + freeboard_m + np.maximum(1.5, 0.5 * depth),
                               lowland_excavation_ceiling_m)
        half_widths = []
        for side in (-1.0, 1.0):
            fractions = np.linspace(0.0, 1.0, max(9, int(np.ceil(width.max() / (0.8 * spec.spacing_m))) + 1))
            probes = positions[:, None, :] + side * profile["normal"][:, None, :] * width[:, None, None] * 0.5 * fractions[None, :, None]
            values = _sample(spec, surface, probes.reshape(-1, 2), order=0).reshape(probes.shape[:2])
            hard = _sample(spec, protected, probes.reshape(-1, 2), order=0).reshape(values.shape)
            inside = np.all((probes >= [spec.u0_m, spec.v0_m]) &
                            (probes < [spec.u0_m + spec.nu * spec.spacing_m, spec.v0_m + spec.nv * spec.spacing_m]), axis=2)
            allowed = (values <= clearance[:, None]) & ~hard & inside
            contiguous = np.cumprod(allowed, axis=1).astype(bool)
            extent = (contiguous * fractions).max(axis=1) * 0.5 * width
            half_widths.append(extent)
        left, right = half_widths
        actual_width = left + right
        profile["left_half_width_m"] = left
        profile["right_half_width_m"] = right
        profile["actual_width_m"] = actual_width
        blocked_cells = set()
        represented_cells = set()

        def apply_cells(rows, cols, local_stage, local_depth, local_width, fraction, coverage):
            valid = ~protected[rows, cols]
            valid &= surface[rows, cols] <= np.maximum(
                local_stage + freeboard_m + np.maximum(1.5, 0.5 * local_depth), lowland_excavation_ceiling_m
            )
            valid &= local_width > 0.0
            rows, cols = rows[valid], cols[valid]
            if not len(rows):
                return
            local_stage, local_depth = local_stage[valid], local_depth[valid]
            proposed = local_stage - local_depth * np.maximum(1.0 - fraction[valid] ** 4, 0.12)
            wins = (proposed < bed[rows, cols]) | ~channel[rows, cols]
            bed[rows, cols] = np.minimum(bed[rows, cols], proposed)
            stage[rows, cols] = np.minimum(stage[rows, cols], local_stage)
            physical_width[rows[wins], cols[wins]] = local_width[valid][wins]
            channel[rows, cols] = True
            if coverage:
                coverage_only[rows, cols] = True
            else:
                physical_coverage[rows, cols] = True

        for station in range(len(positions) - 1):
            start, end = positions[station:station + 2]
            vector = end - start
            squared_length = float(vector @ vector)
            reach_width = max(left[station:station + 2].max(), right[station:station + 2].max())
            lower = np.floor((np.minimum(start, end) - reach_width - [spec.u0_m, spec.v0_m]) / spec.spacing_m).astype(int)
            upper = np.floor((np.maximum(start, end) + reach_width - [spec.u0_m, spec.v0_m]) / spec.spacing_m).astype(int) + 1
            row0, col0 = np.maximum(lower, 0)
            row1, col1 = np.minimum(upper, shape)
            if row1 > row0 and col1 > col0 and reach_width > 0:
                rows, cols = np.meshgrid(np.arange(row0, row1), np.arange(col0, col1), indexing="ij")
                centres = np.stack([spec.u0_m + (rows + 0.5) * spec.spacing_m,
                                    spec.v0_m + (cols + 0.5) * spec.spacing_m], axis=-1)
                projection = np.clip(((centres - start) @ vector) / squared_length, 0.0, 1.0)
                offset = centres - (start + projection[..., None] * vector)
                lateral = vector[0] * offset[..., 1] - vector[1] * offset[..., 0]
                interpolate = lambda values: values[station] + projection * (values[station + 1] - values[station])
                half = np.where(lateral < 0, interpolate(left), interpolate(right))
                radial = np.linalg.norm(offset, axis=-1)
                inside = (radial < half) & (half > 0.0)
                apply_cells(rows[inside], cols[inside], interpolate(water_stage)[inside], interpolate(depth)[inside],
                            interpolate(actual_width)[inside], (radial / np.maximum(half, 1e-12))[inside], False)
            # Traversal is raster coverage only; it never increases physical width.
            for (row, col), projection in _cell_path(spec, start, end, surface, protected):
                if not (0 <= row < spec.nu and 0 <= col < spec.nv):
                    blocked_cells.add((row, col))
                    continue
                interpolate = lambda values: values[station] + projection * (values[station + 1] - values[station])
                local_stage, local_depth = interpolate(water_stage), interpolate(depth)
                local_width = interpolate(actual_width)
                limit = max(local_stage + freeboard_m + max(1.5, 0.5 * local_depth), lowland_excavation_ceiling_m)
                if protected[row, col] or surface[row, col] > limit or local_width <= 0:
                    blocked_cells.add((row, col))
                    continue
                represented_cells.add((row, col))
                apply_cells(np.array([row]), np.array([col]), np.array([local_stage]), np.array([local_depth]),
                            np.array([local_width]), np.array([0.0]), True)
                represented_centreline[row, col] = True
        blocked_cells.difference_update(represented_cells)
        edge_reports.append(dict(
            edge=int(edge), section_count=int(len(distance)),
            contracted_section_count=int(np.count_nonzero(actual_width < 0.99 * width)),
            blocked_section_count=int(np.count_nonzero(actual_width <= 0.0)),
            blocked_centreline_cell_count=len(blocked_cells), represented_centreline_cell_count=len(represented_cells),
            physical_width_min_m=float(actual_width.min()), physical_width_max_m=float(actual_width.max()),
            nominal_width_m=float(widths[edge]),
            maximum_stage_slope=float(np.max(np.abs(np.diff(water_stage) / np.diff(distance)))),
        ))
    labels, components_before_cleanup = ndi.label(channel)
    represented_components = np.unique(labels[represented_centreline])
    # A cell-centred sweep can leave a detached bank-edge pixel around an
    # excluded high bank. It is not a separate river: retain every component
    # containing a successfully represented centreline cell, including both
    # sides of genuinely blocked reaches, and restore only unanchored sweep.
    retained_components = np.zeros(components_before_cleanup + 1, dtype=bool)
    retained_components[represented_components] = True
    retained_components[0] = False
    detached_sweep = channel & ~retained_components[labels]
    removed_components = np.unique(labels[detached_sweep])
    channel[detached_sweep] = False
    bed[detached_sweep] = surface[detached_sweep]
    physical_width[detached_sweep] = 0.0
    coverage_only[detached_sweep] = False
    physical_coverage[detached_sweep] = False
    stage[~channel] = 0.0
    # Intersections use the lower of the coherent reach stages. Keep the
    # corresponding saved bed wet instead of leaving high, dry edge pixels.
    bed[channel] = np.minimum(bed[channel], stage[channel] - 0.05)
    actual_depth = np.where(channel, stage - bed, 0.0)
    coverage_only &= ~physical_coverage
    _, components = ndi.label(channel)
    report = dict(
        operator="continuous swept cross sections with source bank clearance",
        stage_semantics="non-increasing filtered valley profile; shared node stages; sea-level mouths",
        protected_elevation_m=float(protected_elevation_m), freeboard_m=float(freeboard_m),
        lowland_excavation_ceiling_m=float(lowland_excavation_ceiling_m),
        protected_source_cells_cut=int(np.count_nonzero((bed < surface) & protected)),
        contracted_section_count=sum(item["contracted_section_count"] for item in edge_reports),
        blocked_section_count=sum(item["blocked_section_count"] for item in edge_reports),
        blocked_centreline_cell_count=sum(item["blocked_centreline_cell_count"] for item in edge_reports),
        channel_components_4_connected=int(components), channel_cell_count=int(channel.sum()),
        channel_components_before_sweep_cleanup_4_connected=int(components_before_cleanup),
        detached_sweep_cells_removed=int(detached_sweep.sum()),
        detached_sweep_components_removed=int(len(removed_components)),
        subcell_coverage_cell_count=int(coverage_only.sum()),
        raster_coverage_area_m2=float(channel.sum() * spec.spacing_m ** 2),
        coverage_semantics="four-connected intersected cells; physical width is never floored to cell size",
        raster_excavation_is_resolution_dependent=True, edges=edge_reports,
    )
    return dict(bed=bed, chan=channel, stage=stage, width=physical_width, depth=actual_depth,
                report=report, profiles=profiles, node_stage=node_stage, raster_coverage_only=coverage_only,
                represented_centreline_mask=represented_centreline, levee=np.zeros(shape))
