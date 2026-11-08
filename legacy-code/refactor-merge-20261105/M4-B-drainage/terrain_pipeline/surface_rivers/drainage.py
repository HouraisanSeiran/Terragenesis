"""Irregular-graph routing and conservative surface-water accumulation."""

import numpy as np

from ..irregular_drainage import build_mesh, route_graph
from .contracts import AccumulationResult, RoutingResult


def route(height: np.ndarray, outlet_mask: np.ndarray, spacing_blocks: float, *,
          origin_native_xz=(0, 0), world_seed=20261020,
          origin_world_xz=None) -> RoutingResult:
    """Route native cell accounts over deterministic irregular graph positions.

    The returned order lists receivers before donors. Flat cells use flood order
    as a deterministic descending tie-break, so the receiver graph is acyclic.
    """
    raw = np.asarray(height, dtype=np.float64)
    outlets = np.asarray(outlet_mask, dtype=np.bool_)
    if raw.ndim != 2 or min(raw.shape) < 1 or outlets.shape != raw.shape:
        raise ValueError("height and outlet_mask must share a nonempty 2D shape")
    if not np.isfinite(raw).all() or not np.isfinite(spacing_blocks) or spacing_blocks <= 0:
        raise ValueError("height and spacing_blocks must be finite; spacing must be positive")
    if not outlets.any():
        raise ValueError("At least one explicit outlet is required")

    if origin_world_xz is None:
        mesh = build_mesh(raw.shape, origin_native_xz, spacing_blocks, world_seed)
    else:
        if len(origin_world_xz) != 2:
            raise ValueError("origin_world_xz must contain two finite coordinates")
        from ..irregular_grid import grid_mesh
        mesh = grid_mesh(raw.shape, x0_m=origin_world_xz[0], z0_m=origin_world_xz[1],
                         dx_m=spacing_blocks, world_seed=world_seed)
    result = route_graph(raw, outlets, mesh)
    receiver, order, routing_height = result.receiver, result.order, result.filled
    outlet_copy = outlets.copy()
    for array in (receiver, order, routing_height, outlet_copy):
        array.flags.writeable = False
    return RoutingResult(receiver, order, routing_height, outlet_copy, float(spacing_blocks))


def accumulate(routing: RoutingResult, runoff: np.ndarray, spacing_blocks: float,
               external_inflow: np.ndarray | None = None) -> AccumulationResult:
    """Accumulate runoff depth/time and optional per-cell volume/time inflow."""
    shape = routing.routing_height.shape
    if routing.receiver.shape != (routing.routing_height.size,) or routing.order.shape != routing.receiver.shape:
        raise ValueError("Invalid routing array shape")
    if routing.outlet_mask.shape != shape or not np.array_equal(np.sort(routing.order), np.arange(routing.receiver.size)):
        raise ValueError("Invalid routing order or outlet mask")
    rank = np.empty(routing.receiver.size, dtype=np.int64)
    rank[routing.order] = np.arange(routing.receiver.size)
    if (routing.receiver < -1).any() or (routing.receiver >= routing.receiver.size).any():
        raise ValueError("Invalid routing receiver index")
    for cell, downstream in enumerate(routing.receiver):
        if (downstream == -1) != bool(routing.outlet_mask.flat[cell]):
            raise ValueError("Routing outlets do not match outlet mask")
        if downstream >= 0 and rank[downstream] >= rank[cell]:
            raise ValueError("Routing receiver must precede donor")
    rain = np.asarray(runoff, dtype=np.float64)
    extra = np.zeros(shape, dtype=np.float64) if external_inflow is None else np.asarray(external_inflow, dtype=np.float64)
    if rain.shape != shape or extra.shape != shape or not np.isfinite(rain).all() or not np.isfinite(extra).all():
        raise ValueError("runoff and external_inflow must be finite arrays matching routing shape")
    if (rain < 0).any() or (extra < 0).any() or not np.isfinite(spacing_blocks) or spacing_blocks <= 0:
        raise ValueError("runoff, inflow, and spacing must be nonnegative and finite")
    if spacing_blocks != routing.spacing_blocks:
        raise ValueError("Accumulation spacing differs from routing spacing")
    local = rain * spacing_blocks ** 2 + extra
    flow = local.ravel().copy()
    if not np.isfinite(flow).all():
        raise ValueError("Local discharge overflows float64")
    for current in routing.order[::-1]:
        downstream = routing.receiver[current]
        if downstream >= 0:
            flow[downstream] += flow[current]
    if not np.isfinite(flow).all():
        raise ValueError("Accumulated discharge overflows float64")
    discharge = flow.reshape(shape)
    outlets = np.where(routing.outlet_mask, discharge, 0.0)
    input_total = float(np.sum(local, dtype=np.float64))
    outlet_total = float(np.sum(outlets, dtype=np.float64))
    if not np.isfinite(input_total) or not np.isfinite(outlet_total):
        raise ValueError("Discharge budget overflows float64")
    return AccumulationResult(discharge, outlets, input_total, outlet_total,
                              input_total - outlet_total)


def channel_mask(discharge: np.ndarray, threshold_q: float) -> np.ndarray:
    """Select channels using an absolute discharge threshold, never tile normalization."""
    flow = np.asarray(discharge, dtype=np.float64)
    if flow.ndim != 2 or not np.isfinite(flow).all() or (flow < 0).any():
        raise ValueError("discharge must be a finite nonnegative 2D array")
    if not np.isfinite(threshold_q) or threshold_q <= 0:
        raise ValueError("threshold_q must be finite and positive")
    return flow >= threshold_q
