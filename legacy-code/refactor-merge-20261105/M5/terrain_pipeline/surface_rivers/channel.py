"""Bounded routed-channel geometry with explicit unresolved water cells."""
from dataclasses import dataclass
from collections import deque
import numpy as np
from .water import safe_water
from .bridge import bridge_diagonals, flow_tangent


@dataclass(frozen=True)
class ChannelResult:
    height: np.ndarray
    water_surface: np.ndarray
    channel_mask: np.ndarray
    flowline_mask: np.ndarray
    width_blocks: np.ndarray
    incision: np.ndarray
    unresolved_mask: np.ndarray


def _validated_route(receiver, order, shape):
    count = int(np.prod(shape))
    original_receiver = np.asarray(receiver)
    original_order = np.asarray(order)
    if original_receiver.dtype.kind not in 'iu' or original_order.dtype.kind not in 'iu':
        raise ValueError('Route indices must be integers')
    downstream = original_receiver.reshape(-1).astype(np.int64)
    ordered = original_order.reshape(-1).astype(np.int64)
    if downstream.size != count or ordered.size != count:
        raise ValueError('Invalid route dimensions')
    if np.any((downstream < -1) | (downstream >= count)):
        raise ValueError('Invalid receiver index')
    if not np.array_equal(np.sort(ordered), np.arange(count)):
        raise ValueError('Order must be a permutation')
    position = np.empty(count, dtype=np.int64)
    position[ordered] = np.arange(count)
    for cell, target in enumerate(downstream):
        if target >= 0 and position[target] >= position[cell]:
            raise ValueError('Receiver must precede donor')
    return downstream, ordered


def _channel_geometry(flowline, discharge, receiver, spacing, threshold):
    rows, cols = flowline.shape
    corridor = flowline.copy()
    donors = [[] for _ in range(rows * cols)]
    for cell, target in enumerate(receiver):
        if target >= 0 and flowline.flat[cell]:
            donors[target].append(cell)
    width = np.zeros(flowline.shape, dtype=np.float32)
    # A bounded cross-section grows as sqrt(Q), never by tile normalization.
    width[flowline] = np.minimum(5 * spacing,
                                 spacing * np.maximum(1, np.sqrt(discharge[flowline] / threshold)))
    for z, x in zip(*np.nonzero(flowline)):
        target = receiver[z * cols + x]
        if target < 0:
            incoming = donors[z * cols + x]
            if not incoming:
                continue
            donor = max(incoming, key=lambda cell: discharge.flat[cell])
            uz, ux = divmod(donor, cols)
            dz, dx = z - uz, x - ux
        else:
            tz, tx = divmod(int(target), cols)
            dz, dx = tz - z, tx - x
        edge_dz, edge_dx = dz, dx
        dz, dx = flow_tangent(z * cols + x, receiver, donors, cols, discharge)
        length = np.hypot(dz, dx)
        if length == 0.:
            continue
        grid_length = max(abs(dz), abs(dx))
        normal_z, normal_x = dx / grid_length, -dz / grid_length
        radius = min(2, int(np.floor(width[z, x] / (2 * spacing))))
        # Legacy raster consumers have cell anchors, so interpolate their finite
        # graph edge explicitly rather than assuming one neighboring cell.
        samples = max(1, int(np.ceil(np.hypot(edge_dz, edge_dx) * 2.))) if target >= 0 else 1
        for sample in range(samples + 1):
            along = sample / samples if target >= 0 else 0.
            for step in range(-radius, radius + 1):
                nz = int(round(z + along * edge_dz + step * normal_z))
                nx = int(round(x + along * edge_dx + step * normal_x))
                if 0 <= nz < rows and 0 <= nx < cols:
                    corridor[nz, nx] = True
    return corridor, width


def _carve_beds(source, corridor, flowline, receiver, order, discharge,
                threshold, max_incision, diagnostics=None):
    carved = source.copy()
    lower_limit = source.reshape(-1) - max_incision
    q_depth = np.minimum(max_incision, 0.8 + .55 * np.log1p(discharge / threshold))
    carved[corridor] -= np.minimum(max_incision, np.maximum(.4, q_depth[corridor] * .7))
    carved[flowline] = source[flowline] - q_depth[flowline]
    bed = carved.reshape(-1)
    active = flowline.reshape(-1)
    unresolved = np.zeros(source.size, dtype=bool)
    for cell in order[::-1]:
        target = receiver[cell]
        if not active[cell] or target < 0 or not active[target]:
            continue
        required = bed[cell] - .01
        if bed[target] > required:
            bed[target] = max(lower_limit[target], required)
            if bed[target] > required + 1e-9:
                unresolved[cell] = unresolved.reshape(-1)[target] = True
                if diagnostics is not None:
                    diagnostics.mark_cell("bed_cut_cap", int(target))
                    diagnostics.mark_cell("bed_cut_cap_donor", int(cell), propagated=True)
                    diagnostics.required_extra_cut_m.flat[target] = max(
                        diagnostics.required_extra_cut_m.flat[target], bed[target] - required)
    incision = source - carved
    if (incision < -1e-8).any() or (incision > max_incision + 1e-8).any():
        raise AssertionError('Channel incision must only cut within its cap')
    return carved, incision, unresolved


def carve_channels(height, receiver, order, discharge, spacing_blocks,
                   threshold, max_incision=4.0, diagnostics=None) -> ChannelResult:
    """Carve a Q-scaled cross-section; unresolved flowline cells remain dry."""
    source = np.asarray(height, dtype=np.float64)
    q = np.asarray(discharge, dtype=np.float64)
    if source.ndim != 2 or q.shape != source.shape or not np.isfinite(source).all():
        raise ValueError('Expected finite height and matching discharge grids')
    if not np.isfinite(q).all() or (q < 0).any():
        raise ValueError('Discharge must be finite and nonnegative')
    if not np.isfinite(spacing_blocks) or spacing_blocks <= 0:
        raise ValueError('Positive grid spacing required')
    if not np.isfinite(threshold) or threshold <= 0 or not np.isfinite(max_incision) or max_incision <= 0:
        raise ValueError('Positive threshold and incision cap required')
    downstream, ordered = _validated_route(receiver, order, source.shape)
    flowline = q >= threshold
    corridor, width = _channel_geometry(flowline, q, downstream, spacing_blocks, threshold)
    carved, incision, unresolved = _carve_beds(source, corridor, flowline,
                                                 downstream, ordered, q, threshold,
                                                 max_incision, diagnostics)
    water, unresolved = safe_water(source, carved, corridor, flowline, downstream,
                                   unresolved, max_incision, diagnostics)
    carved, water, corridor, bad_edges = bridge_diagonals(
        source, carved, water, corridor, flowline, downstream, max_incision, diagnostics)
    for donor, target in bad_edges:
        unresolved.reshape(-1)[donor] = True
        unresolved.reshape(-1)[target] = True
        if diagnostics is not None:
            diagnostics.mark_cell("diagonal_bridge_failed", donor, propagated=True)
            diagnostics.mark_cell("diagonal_bridge_failed", target, propagated=True)
    flat_water = water.reshape(-1)
    flat_unresolved = unresolved.reshape(-1)
    # Section overlaps leave some lower corridor cells unclaimed by a node.
    # Complete connected cross-section support within the same incision cap.
    todo = deque(map(tuple, np.argwhere(np.isfinite(water))))
    while todo:
        z, x = todo.popleft()
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = z + dz, x + dx
            if (0 <= nz < source.shape[0] and 0 <= nx < source.shape[1]
                    and corridor[nz, nx] and not unresolved[nz, nx]
                    and not np.isfinite(water[nz, nx])
                    and source[nz, nx] - max_incision < water[z, x] - .15):
                carved[nz, nx] = min(carved[nz, nx], water[z, x] - .15)
                water[nz, nx] = water[z, x]
                todo.append((nz, nx))
    for z, x in zip(*np.nonzero(np.isfinite(water))):
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = z + dz, x + dx
            if (0 <= nz < source.shape[0] and 0 <= nx < source.shape[1]
                    and not np.isfinite(water[nz, nx])):
                water[z, x] = min(water[z, x], carved[nz, nx] - .05)
        carved[z, x] = max(source[z, x] - max_incision, min(carved[z, x], water[z, x] - .15))
        if water[z, x] <= carved[z, x] + 1e-6:
            unresolved[z, x] = True
    for cell in ordered[::-1]:
        target = downstream[cell]
        if target >= 0 and np.isfinite(flat_water[cell]) and np.isfinite(flat_water[target]):
            if flat_water[target] > flat_water[cell] + 1e-6:
                lowered = min(flat_water[target], flat_water[cell])
                carved.reshape(-1)[target] = max(source.reshape(-1)[target] - max_incision,
                    min(carved.reshape(-1)[target], lowered - .15))
                if lowered <= carved.reshape(-1)[target] + 1e-6:
                    flat_unresolved[cell] = flat_unresolved[target] = True
                    if diagnostics is not None:
                        diagnostics.mark_cell("stage_repair_no_clearance", cell)
                        diagnostics.mark_cell("stage_repair_no_clearance", target)
                else:
                    flat_water[target] = lowered
    flat_water[flat_unresolved] = np.nan
    incision = source - carved
    if (incision < -1e-8).any() or (incision > max_incision + 1e-8).any():
        raise AssertionError('Channel incision must remain cut-only and capped')
    return ChannelResult(carved, water, corridor,
                         flowline, width, incision, unresolved)
