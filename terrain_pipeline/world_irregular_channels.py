"""Continuous irregular reaches and bounded source-relative channel sections.

Node IDs are row-major native control-cell IDs. Coordinates are world metres;
the native height raster samples (origin + column/row) * spacing. Sections are
generation geometry, not a hydraulic solution or a sediment export model.
"""
from dataclasses import asdict
import math

import numpy as np
from numba import njit

from terrain_pipeline.channel_geometry import DischargeGeometryConfig


ALGORITHM = "irregular_shared_node_continuous_sections_v1"


def _field(value, shape, name, *, boolean=False):
    array = np.asarray(value)
    if array.ndim == 0 and not boolean:
        array = np.full(shape, value, dtype=np.float64)
    if array.size != np.prod(shape) or (boolean and array.dtype.kind != "b"):
        raise ValueError(name + " must match native cells")
    return array.reshape(shape)


@njit(cache=True)
def _line_blocked(ax, az, bx, bz, protected, complete, a, b, origin_x, origin_z, spacing):
    """Visit every cell interior crossed by the finite centerline (voxel DDA)."""
    rows, cols = protected.shape
    gx, gz = (ax - origin_x) / spacing + .5, (az - origin_z) / spacing + .5
    hx, hz = (bx - origin_x) / spacing + .5, (bz - origin_z) / spacing + .5
    col, row = int(math.floor(gx)), int(math.floor(gz))
    end_col, end_row = int(math.floor(hx)), int(math.floor(hz))
    dx, dz = hx - gx, hz - gz
    step_x, step_z = (1 if dx > 0. else -1), (1 if dz > 0. else -1)
    delta_x = abs(1. / dx) if dx != 0. else np.inf
    delta_z = abs(1. / dz) if dz != 0. else np.inf
    next_x = ((col + 1 - gx) / dx if dx > 0. else (col - gx) / dx) if dx != 0. else np.inf
    next_z = ((row + 1 - gz) / dz if dz > 0. else (row - gz) / dz) if dz != 0. else np.inf
    for _ in range(abs(end_col - col) + abs(end_row - row) + 1):
        if not (0 <= col < cols and 0 <= row < rows):
            return True
        cell = row * cols + col
        if ((not complete[row, col] and cell != b)
                or (protected[row, col] and cell != a and cell != b)):
            return True
        if col == end_col and row == end_row:
            return False
        if next_x < next_z:
            col += step_x
            next_x += delta_x
        elif next_z < next_x:
            row += step_z
            next_z += delta_z
        else:
            col += step_x
            row += step_z
            next_x += delta_x
            next_z += delta_z
    return True


@njit(cache=True)
def _project_sections(source, protected, complete, x, z, sources, targets, width, depth,
                      origin_x, origin_z, spacing, bottom_fraction, max_cut):
    rows, cols = source.shape
    cut = np.zeros(source.shape, np.float64)
    limited = np.zeros(sources.size, np.bool_)
    blocked = np.zeros(sources.size, np.bool_)
    for edge in range(sources.size):
        a, b = sources[edge], targets[edge]
        dx, dz = x[b] - x[a], z[b] - z[a]
        length2 = dx * dx + dz * dz
        radius = max(width[a], width[b]) * .5
        if length2 <= 0. or radius <= 0.:
            continue
        blocked[edge] = _line_blocked(x[a], z[a], x[b], z[b], protected, complete,
            a, b, origin_x, origin_z, spacing)
        if blocked[edge]:
            continue
        c0 = max(0, int(math.floor((min(x[a], x[b]) - radius - origin_x) / spacing)))
        c1 = min(cols - 1, int(math.ceil((max(x[a], x[b]) + radius - origin_x) / spacing)))
        r0 = max(0, int(math.floor((min(z[a], z[b]) - radius - origin_z) / spacing)))
        r1 = min(rows - 1, int(math.ceil((max(z[a], z[b]) + radius - origin_z) / spacing)))
        raw_a, raw_b = source[a // cols, a % cols], source[b // cols, b % cols]
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                if protected[row, col]:
                    continue
                px, pz = origin_x + col * spacing - x[a], origin_z + row * spacing - z[a]
                along = max(0., min(1., (px * dx + pz * dz) / length2))
                lateral = math.sqrt((px - along * dx) ** 2 + (pz - along * dz) ** 2)
                w = width[a] + along * (width[b] - width[a])
                d = depth[a] + along * (depth[b] - depth[a])
                if w <= 0. or lateral >= w * .5:
                    continue
                weight = min(1., (w * .5 - lateral) / (w * (1. - bottom_fraction) * .5))
                # Shared endpoint design elevations ensure the same confluence anchor.
                design = raw_a + along * (raw_b - raw_a) - d
                required = max(0., source[row, col] - design) * weight
                if required > max_cut:
                    limited[edge] = True
                cut[row, col] = max(cut[row, col], min(max_cut, required))
    return cut, limited, blocked


def build_irregular_channel_geometry(source_elevation_m, discharge_q_m3_s, channel_mask,
                                     mesh, receiver, *, bed_hardness=.5, bank_hardness=.5,
                                     protected_mask=None, complete_mask=None, lake_mask=None,
                                     ocean_mask=None, origin_native_xz=None, spacing_m=None,
                                     config=None, formative_section_inputs=None):
    """Project shared-node reaches to native sample points without widening hits.

    A terminal edge retains its lake/ocean/unknown endpoint for querying. No cut
    is applied in protected, lake, ocean or incomplete cells. Raw uphill steps
    and ridges remain bounded by max_incise_m; the resulting profile is explicitly
    not certified downhill. A subgrid reach can have zero raster incision.
    """
    source = np.asarray(source_elevation_m, np.float64)
    if source.ndim != 2 or not np.isfinite(source).all() or not source.size:
        raise ValueError("finite nonempty 2D native terrain required")
    shape, count = source.shape, source.size
    config = DischargeGeometryConfig() if config is None else config
    if not isinstance(config, DischargeGeometryConfig):
        raise ValueError("DischargeGeometryConfig required")
    spacing = spacing_m if spacing_m is not None else getattr(mesh, "spacing_m", 30.)
    origin = origin_native_xz if origin_native_xz is not None else getattr(mesh, "origin_native_xz", None)
    if (isinstance(spacing, (bool, np.bool_)) or not np.isfinite(spacing) or not 0. < spacing <= 10000.
            or origin is None or len(origin) != 2
            or any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer)) for v in origin)):
        raise ValueError("positive spacing and integer native origin required")
    x, z = np.asarray(mesh.node_x_m, np.float64), np.asarray(mesh.node_z_m, np.float64)
    rec = np.asarray(receiver)
    if (x.shape != (count,) or z.shape != (count,) or not np.isfinite(x).all()
            or not np.isfinite(z).all() or rec.size != count or rec.dtype.kind not in "iu"):
        raise ValueError("one finite position and integer receiver per native cell required")
    rec = rec.reshape(-1).astype(np.int64)
    if np.any(rec < -1) or np.any(rec >= count) or np.any(rec == np.arange(count)):
        raise ValueError("receiver must be another native node or -1")
    q = _field(discharge_q_m3_s, shape, "discharge").astype(np.float64)
    bed = _field(bed_hardness, shape, "bed_hardness").astype(np.float64)
    bank = _field(bank_hardness, shape, "bank_hardness").astype(np.float64)
    if (not np.isfinite(q).all() or np.any(q < 0.) or not np.isfinite(bed).all()
            or not np.isfinite(bank).all() or np.any((bed < 0.) | (bed > 1.))
            or np.any((bank < 0.) | (bank > 1.))):
        raise ValueError("nonnegative finite Q and hardness in [0, 1] required")
    channel = _field(channel_mask, shape, "channel_mask", boolean=True)
    complete = np.ones(shape, bool) if complete_mask is None else _field(complete_mask, shape, "complete_mask", boolean=True)
    lake = np.zeros(shape, bool) if lake_mask is None else _field(lake_mask, shape, "lake_mask", boolean=True)
    ocean = np.zeros(shape, bool) if ocean_mask is None else _field(ocean_mask, shape, "ocean_mask", boolean=True)
    protected = np.zeros(shape, bool) if protected_mask is None else _field(protected_mask, shape, "protected_mask", boolean=True)
    excluded = protected | lake | ocean | ~complete
    active = channel & (q > 0.)
    width, depth = np.zeros(shape), np.zeros(shape)
    exposure = -math.expm1(-config.generation_exposure)
    width[active] = np.minimum(config.max_width_m,
        config.width_at_unit_q_m * q[active] ** config.width_q_exponent
        * (1. + 1.5 * bed[active]) * (.5 + 1.5 * (1. - bank[active]))) * exposure
    if formative_section_inputs is not None:
        from terrain_pipeline.channel_geometry import formative_section
        inputs = dict(formative_section_inputs)
        for key, value in inputs.items():
            if value is not None and np.asarray(value).ndim:
                inputs[key] = _field(value, shape, key)[active]
        section = formative_section(q[active], bed[active], bank[active],
            reference_width_m=config.width_at_unit_q_m,
            width_exponent=config.width_q_exponent, max_width_m=config.max_width_m,
            **inputs)
        width[active] = section.width_m * exposure
    depth[active] = np.minimum(config.max_incise_m,
        config.depth_at_unit_q_m * q[active] ** config.depth_q_exponent
        * (.4 + 1.2 * (1. - bed[active])) * (.8 + .4 * bank[active])) * exposure
    sources = np.flatnonzero(active.ravel() & (rec >= 0)).astype(np.int64)
    targets = rec[sources]
    # Endpoints outside the channel set inherit their incoming design section.
    # Maximum reduction is commutative, so tributary ordering cannot move a junction.
    np.maximum.at(width.ravel(), targets, width.ravel()[sources])
    np.maximum.at(depth.ravel(), targets, depth.ravel()[sources])
    cut, limited, blocked = _project_sections(source, excluded, complete, x, z, sources, targets,
        width.ravel(), depth.ravel(), float(origin[0]) * spacing, float(origin[1]) * spacing,
        float(spacing), config.bottom_width_fraction, config.max_incise_m)
    terminal = np.zeros(count, np.uint8)
    terminal[rec < 0] = 1
    terminal[~complete.ravel()] = 2
    terminal[lake.ravel()] = 3
    terminal[ocean.ravel()] = 4
    radius = np.maximum(width.ravel()[sources], width.ravel()[targets]) * .5
    graph = dict(node_x_m=x.copy(), node_z_m=z.copy(), receiver=rec,
        node_q_m3_s=q.ravel().copy(), node_width_m=width.ravel().copy(),
        node_design_incision_depth_m=depth.ravel().copy(),
        node_raw_bed_m=source.ravel().copy(), node_terminal_kind=terminal,
        reach_source=sources, reach_target=targets,
        reach_max_cut_limited=limited,
        reach_projection_blocked=blocked,
        reach_raw_uphill=source.ravel()[targets] > source.ravel()[sources],
        reach_min_x_m=np.minimum(x[sources], x[targets]) - radius,
        reach_max_x_m=np.maximum(x[sources], x[targets]) + radius,
        reach_min_z_m=np.minimum(z[sources], z[targets]) - radius,
        reach_max_z_m=np.maximum(z[sources], z[targets]) + radius,
        origin_native_xz=np.asarray(origin, np.int64), native_shape=np.asarray(shape, np.int64),
        spacing_m=np.asarray(float(spacing)))
    removed = float(cut.sum(dtype=np.float64) * spacing ** 2)
    arrays = dict(representative_q_m3_s=q, channel_width_m=width,
        bottom_width_m=width * config.bottom_width_fraction,
        channel_depth_m=depth, design_incision_depth_m=depth,
        cut_depth_m=cut, bed_elevation_m=source - cut, final_bed_m=source - cut,
        bed_hardness=bed, bank_hardness=bank, channel_mask=channel.copy())
    metadata = dict(algorithm=ALGORITHM, config=asdict(config), spacing_m=float(spacing),
        raster_projection="continuous_segment_projection_at_native_sample_points",
        depth_definition="bounded_source_relative_design_incision_not_water_depth_m",
        profile_policy="shared_linear_endpoint_design_bed_local_cut_capped_raw_ridges_can_remain",
        blocked_reach_policy="retain_topological_edge_but_no_cut_across_protected_or_unknown_interior",
        protected_water_policy="no_cut_in_protected_lake_ocean_or_incomplete_cells_terminal_anchor_retained",
        subgrid_sections_resolved=False, hydraulic_solution=False,
        material_budget=dict(coarse_raster_edit_bulk_m3=removed, removed_terrain_bulk_m3=removed,
            unplaced_excavated_bulk_m3=removed, redeposited_bulk_m3=0., sediment_export_solved=False))
    graph_metadata = dict(algorithm=ALGORITHM, node_identity="rowmajor_native_cell_id",
        world_seed=int(getattr(mesh, "world_seed", 20261020)),
        coordinate_units="world_metres", terminal_kinds={"0": "interior", "1": "retained",
            "2": "unknown", "3": "lake", "4": "ocean"},
        reach_identity="source_node_id", profile_hydraulically_certified=False)
    return dict(arrays=arrays, metadata=metadata, graph=graph, graph_metadata=graph_metadata)


def query_reach_indices(graph, min_x_m, min_z_m, max_x_m, max_z_m):
    """Return reaches whose section envelope intersects a world-metre box.

    Query is vectorized O(reaches), with no node-by-reach pair allocation.
    Saved graph arrays can be replayed directly from np.load without rebuilding.
    """
    bounds = np.asarray([min_x_m, min_z_m, max_x_m, max_z_m], np.float64)
    if not np.isfinite(bounds).all() or min_x_m > max_x_m or min_z_m > max_z_m:
        raise ValueError("finite ordered world bounds required")
    return np.flatnonzero((graph["reach_min_x_m"] <= max_x_m)
        & (graph["reach_max_x_m"] >= min_x_m) & (graph["reach_min_z_m"] <= max_z_m)
        & (graph["reach_max_z_m"] >= min_z_m))
