"""Run one declared native-30 m catchment event through the existing buckets and routers.

Scope of this module
--------------------
This is an *orchestration* module. It adds no runoff law, no delay law and no
routing kernel. It wires three pieces that already exist and are frozen:

* ``terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff`` - the soil bucket
  (infiltration, ET, percolation, fast/slow linear reservoirs).
* ``terrain_pipeline.mountain_runoff_routing.route_local_discharge`` - the
  conservative reach router with linear-reservoir travel delay
  ``tau = max(reach_length, minimum_length) / speed``.
* ``terrain_pipeline.surface_rivers.metric_network_accumulation.accumulate_network_discharge``
  - the instantaneous diagnostic accumulation on the same finite graph.

What it produces, and the two discharges that must never be confused
--------------------------------------------------------------------
``instantaneous_terminal_q_m3_s`` is the topological sum of the per-cell local
``m3/s`` on the *same* receiver graph, with no travel delay. It puts every
sub-catchment at its peak at the same instant, so it is an upper envelope and a
diagnostic only.

``routed_terminal_q_m3_s`` / ``design_q_m3_s`` is the outflow of the reach that
contains the declared terminal, from interval volumes pushed through the linear
reservoir cascade. This is the only one that has travel delay, so it is the one
an event-design discharge may be quoted from - and it is explicitly
``event_design_q_not_bankfull``: it is the peak of a *declared synthetic storm*,
not bankfull, not a return-period flood, not calibrated.

Neither value may be substituted for the other, and this module refuses to
publish a single number that hides which one it is.

How each cell's runoff enters the reach network
-----------------------------------------------
The router's HRU semantics are ``lateral_volume_m3[t, reach] =
sum_hru local_q_m3_s[t, hru] * fractions[reach, hru] * dt_s`` with
``fractions = allocation_counts * spacing_m**2 / area_m2``.

One HRU per catchment *cell* would need ``active_cells <= MAX_HRUS = 256`` and
is therefore not generally usable. Instead, each HRU groups the catchment cells
that share one ``cell_reach`` (the reach that owns the cell's first downstream
flowline cell). ``allocation_counts[reach_of_group, group]`` then equals the
group's cell count and ``area_m2[group] = count * spacing_m**2``, so that
fraction is exactly ``1.0`` and every other entry of the column is exactly
``0.0`` (asserted, not assumed). The consequence is the physically correct one:

* every catchment cell's local ``Q`` enters exactly once, in the reach its own
  water first joins, and is never spread along the flowline path;
* a reach whose catchment belongs entirely to an upstream reach receives
  exactly zero lateral inflow, not a share of the catchment total.

The historical two-HRU script summed the *whole* catchment series into one HRU,
so its per-reach lateral inflow was proportional to cell counts. That is
coincidentally identical for a uniform per-cell ``Q`` - which is all this entry
point can produce, because the rain series and the soil parameters are declared
uniform and every active cell has the same area - but it is not a node-level
lateral attribution and is not reproduced here.

Declared boundaries, not certifications
---------------------------------------
``flowline_mask`` and the single ``receiver == -1`` cell of the catchment are a
*declared finite reach boundary*. No natural outlet is inferred from them, no
external upstream water is injected, and cells outside ``catchment_mask`` get
local ``Q`` exactly ``0.0`` - a declared scope restriction, not a claim that
they produce no runoff in reality.

This module writes no files: bundle publication, cold reading and acceptance
belong to other modules.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import string

import numpy as np

from diffusion.physical_config import PhysicalGenerationConfig
from terrain_pipeline.mountain_runoff_routing import (
    MAX_CELLS as ROUTE_MAX_CELLS, MAX_ENTRIES as ROUTE_MAX_ENTRIES,
    MAX_HRUS as ROUTE_MAX_HRUS, MAX_REACHES as ROUTE_MAX_REACHES,
    MAX_STEPS as ROUTE_MAX_STEPS, build_reaches,
    preflight as route_preflight, route_local_discharge)
from terrain_pipeline.rainfall_runoff import (
    MAX_BYTES as BUCKET_MAX_BYTES, MAX_CELLS as BUCKET_MAX_CELLS,
    MAX_ENTRIES as BUCKET_MAX_ENTRIES, MAX_STEPS as BUCKET_MAX_STEPS,
    RunoffParameters, simulate_rainfall_runoff)
from terrain_pipeline.surface_rivers.metric_network_accumulation import (
    accumulate_network_discharge)


__all__ = [
    "ALGORITHM",
    "DESIGN_Q_SEMANTICS",
    "INSTANTANEOUS_Q_SEMANTICS",
    "NATIVE_SPACING_M",
    "RAIN_SEMANTICS",
    "SCHEMA",
    "TERMINAL_SEMANTICS",
    "run_catchment_event",
]


ALGORITHM = "native-30m-catchment-event-irregular-v2"
SCHEMA = "native-30m-catchment-event-dict-v1"
# TD native resolution; the catchment cells, the cell areas and the reach lengths
# all use this one number. The 10 km planning baseline is obsolete here.
NATIVE_SPACING_M = PhysicalGenerationConfig().native_resolution_m
DIAGNOSTIC_TERMINAL_LABEL = "retained"

RAIN_SEMANTICS = (
    "declared interval rain series: one mm/h value per physical interval of dt_s, "
    "applied uniformly to every active catchment cell and passed through the "
    "existing soil bucket (rainfall_runoff.simulate_rainfall_runoff). It is a "
    "rainfall rate, not a runoff rate: no bare rainfall-to-runoff conversion is "
    "applied and none may be substituted for the bucket")
INSTANTANEOUS_Q_SEMANTICS = (
    "instantaneous topological sum of per-cell local m3/s on the declared finite "
    "graph (metric_network_accumulation.accumulate_network_discharge); no travel "
    "delay, no storage, every sub-catchment simultaneously at peak. Diagnostic "
    "upper envelope only; never a design discharge")
DESIGN_Q_SEMANTICS = (
    "event peak of the routed terminal-reach outflow "
    "(mountain_runoff_routing.route_local_discharge: interval volumes through a "
    "linear-reservoir cascade, tau = max(reach_length, minimum_length)/speed). "
    "event_design_q_not_bankfull: it is the peak of a declared synthetic storm "
    "event, not bankfull, not a return-period flood, not calibrated")
TERMINAL_SEMANTICS = (
    "the single receiver == -1 cell of the catchment is a declared finite reach "
    "boundary and the retained endpoint of this event. It is not a certified "
    "natural outlet, not an ocean or lake connection, and no external upstream "
    "contribution is declared")
CELL_ORDER = ("active_cells holds flat row-major cell ids (row * columns + column) "
              "in ascending order; local_q_m3_s columns follow that order")
OUTSIDE_SCOPE = (
    "cells outside catchment_mask contribute local Q of exactly 0.0 m3/s. That is "
    "a declared event scope, not a measurement of those cells")


# --------------------------------------------------------------------------- #
# small local helpers: identity, typing, graph diagnostics
# --------------------------------------------------------------------------- #

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _array_sha256(array):
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(np.ascontiguousarray(array).tobytes(order="C"))
    return digest.hexdigest()


def _typed_grid(value, name, dtype):
    if (not isinstance(value, np.ndarray) or value.ndim != 2
            or value.dtype != np.dtype(dtype) or value.size < 1):
        raise ValueError(
            "invalid_%s: a nonempty 2-D %s ndarray is required" % (name, dtype))
    return value


def _positive_scalar(value, name, maximum):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not np.isfinite(value) or not 0 < value <= maximum):
        raise ValueError("invalid_%s: finite positive <= %r required" % (name, maximum))


def _topological_order(flat_receiver):
    """Upstream-first order of one acyclic flat receiver graph (Kahn)."""
    size = flat_receiver.size
    pending = np.bincount(flat_receiver[flat_receiver >= 0], minlength=size)
    frontier = list(np.flatnonzero(pending == 0).tolist())
    order = []
    position = 0
    while position < len(frontier):
        cell = frontier[position]
        position += 1
        order.append(cell)
        target = int(flat_receiver[cell])
        if target >= 0:
            pending[target] -= 1
            if pending[target] == 0:
                frontier.append(target)
    if len(order) != size:
        raise ValueError("receiver_cycle: the receiver graph is not acyclic")
    return np.asarray(order, dtype=np.int64)


def _terminal_reached(flat_receiver):
    """Flat id of the terminal each cell ultimately drains to (path doubling)."""
    size = flat_receiver.size
    self_id = np.arange(size, dtype=np.int64)
    reached = np.where(flat_receiver < 0, self_id, np.int64(-1))
    hop = np.where(flat_receiver < 0, self_id, flat_receiver)
    while True:
        updated = np.where(reached >= 0, reached, reached[hop])
        if np.array_equal(updated, reached):
            return reached
        reached = updated


def _receiver_diagnostics(receiver, shape, origin=(0, 0), seed=20261020):
    """Reject bad topology here, with a reason code, before any allocation."""
    size = receiver.size
    flat = receiver.ravel()
    if (flat < -1).any() or (flat >= size).any():
        raise ValueError(
            "receiver_index_out_of_range: receiver entries must be -1 or a valid "
            "flat id in [0, %d)" % size)
    sources = np.flatnonzero(flat >= 0)
    targets = flat[sources]
    if (sources == targets).any():
        raise ValueError("receiver_self_loop: a cell cannot receive itself")
    from terrain_pipeline.irregular_grid import grid_mesh, receiver_edges_valid
    mesh = grid_mesh(shape, x0_m=origin[0] * 30., z0_m=origin[1] * 30.,
                     dx_m=30., world_seed=seed)
    if not receiver_edges_valid(receiver, mesh):
        raise ValueError("receiver_not_graph_edge: every receiver must follow the irregular graph")
    order = _topological_order(flat)
    return {"flat": flat, "order": order, "size": int(size)}


def _catchment_diagnostics(flat, catchment, elevation_flat):
    inside = catchment.ravel()
    if not inside.any():
        raise ValueError("catchment_empty: at least one catchment cell is required")
    donors = flat >= 0
    leak = inside & donors & ~np.where(donors, inside[np.where(donors, flat, 0)], True)
    if leak.any():
        raise ValueError(
            "catchment_leaks_outside: %d catchment cell(s) drain to a receiver "
            "outside catchment_mask, so no external water may be substituted"
            % int(leak.sum()))
    terminals = np.flatnonzero(inside & ~donors)
    if terminals.size != 1:
        raise ValueError(
            "catchment_terminal_count: the catchment must hold exactly one "
            "receiver == -1 cell, found %d" % int(terminals.size))
    terminal = int(terminals[0])
    not_land = inside & (elevation_flat <= 0)
    if not_land.any():
        raise ValueError(
            "catchment_cell_not_land: %d catchment cell(s) have elevation <= 0; the "
            "reach router only allocates HRUs to cells with height > 0"
            % int(not_land.sum()))
    return {"mask": inside, "terminal": terminal}


def _flowline_diagnostics(flowline, inside, flat, terminal):
    line = flowline.ravel()
    if not line.any():
        raise ValueError("flowline_empty: at least one flowline cell is required")
    outside = line & ~inside
    if outside.any():
        raise ValueError(
            "flowline_outside_catchment: %d flowline cell(s) lie outside "
            "catchment_mask" % int(outside.sum()))
    donors = flat >= 0
    target_inside_line = np.where(donors, line[np.where(donors, flat, 0)], True)
    broken = line & donors & ~target_inside_line
    if broken.any():
        raise ValueError(
            "flowline_not_downstream_closed: %d flowline cell(s) drain to a cell "
            "outside the flowline and outside the declared terminals"
            % int(broken.sum()))
    reached = _terminal_reached(flat)
    detached = line & (reached != terminal)
    if detached.any():
        raise ValueError(
            "flowline_not_connected_to_terminal: %d flowline cell(s) do not reach "
            "the declared catchment terminal" % int(detached.sum()))
    return {"mask": line, "cells": int(line.sum())}


def _origin(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(isinstance(item, (bool, np.bool_)) for item in value)
            or any(not isinstance(item, (int, np.integer)) for item in value)):
        raise ValueError(
            "invalid_origin_native_xz: a two-entry integer (x, z) native-cell "
            "origin is required")
    return [int(value[0]), int(value[1])]


def _source_identity(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in string.hexdigits for character in value)):
        raise ValueError(
            "invalid_source_identity_sha256: a 64-character hex digest is required")
    return value.lower()


def _world_seed(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError("invalid_world_seed: a nonnegative integer is required")
    if value < 0:
        raise ValueError("invalid_world_seed: a nonnegative integer is required")
    return int(value)


# --------------------------------------------------------------------------- #
# budget gates, all of them before any array allocation
# --------------------------------------------------------------------------- #

def _rainfall_budget(steps, cells):
    if steps > BUCKET_MAX_STEPS:
        raise ValueError(
            "budget_rainfall_steps: %d intervals exceed the soil-bucket "
            "MAX_STEPS=%d" % (steps, BUCKET_MAX_STEPS))
    if cells > BUCKET_MAX_CELLS:
        raise ValueError(
            "budget_rainfall_cells: %d catchment cells exceed the soil-bucket "
            "MAX_CELLS=%d" % (cells, BUCKET_MAX_CELLS))
    entries = steps * cells
    if entries > BUCKET_MAX_ENTRIES:
        raise ValueError(
            "budget_rainfall_entries: %d catchment cells x %d intervals = %d "
            "entries exceed the soil-bucket MAX_ENTRIES=%d; the data is not "
            "truncated and no limit is raised"
            % (cells, steps, entries, BUCKET_MAX_ENTRIES))
    estimate = 24 * 8 * (steps + 1) * cells
    if estimate > BUCKET_MAX_BYTES:
        raise ValueError(
            "budget_rainfall_bytes: estimated %d bytes exceed the soil-bucket "
            "MAX_BYTES=%d" % (estimate, BUCKET_MAX_BYTES))
    return {"steps": int(steps), "cells": int(cells), "entries": int(entries),
            "estimated_bytes": int(estimate),
            "limits": {"max_steps": BUCKET_MAX_STEPS, "max_cells": BUCKET_MAX_CELLS,
                       "max_entries": BUCKET_MAX_ENTRIES,
                       "max_bytes": BUCKET_MAX_BYTES}}


def _route_budget(steps, cells, hrus, reaches):
    try:
        return route_preflight(steps, cells, hrus, reaches)
    except ValueError as error:
        raise ValueError(
            "budget_route: %d steps x %d grid cells with %d HRU(s) and %d reach(es) "
            "exceed the reach-router budget (%s); the sub-window is not shrunk and "
            "no limit is raised" % (steps, cells, hrus, reaches, error)) from error


def _diagnostic_budget(steps, cells):
    entries = steps * cells
    if entries > ROUTE_MAX_ENTRIES:
        raise ValueError(
            "budget_diagnostic_entries: %d intervals x %d cells = %d entries exceed "
            "the existing %d entry ceiling reused for the per-interval diagnostic "
            "accumulation" % (steps, cells, entries, ROUTE_MAX_ENTRIES))
    return {"steps": int(steps), "cells": int(cells), "entries": int(entries),
            "max_entries": ROUTE_MAX_ENTRIES}


# --------------------------------------------------------------------------- #
# the one public entry point
# --------------------------------------------------------------------------- #

def run_catchment_event(elevation_m, receiver, catchment_mask, flowline_mask, *,
                        origin_native_xz, source_identity_sha256, world_seed,
                        rain_mm_h, dt_s, runoff_parameters,
                        travel_speed_m_s=1.0, minimum_reach_length_m=30.0):
    """Run one declared storm over one closed native-30 m catchment.

    Returns a plain dict of arrays and declarations; nothing is written to disk.
    Every rejection happens before the first allocation and carries a stable
    reason token as the first word of the message.
    """
    elevation = _typed_grid(elevation_m, "elevation_m", "float64")
    if not np.isfinite(elevation).all():
        raise ValueError("invalid_elevation_m: every elevation must be finite")
    receiver_array = _typed_grid(receiver, "receiver", "int64")
    catchment = _typed_grid(catchment_mask, "catchment_mask", "bool")
    flowline = _typed_grid(flowline_mask, "flowline_mask", "bool")
    if not (receiver_array.shape == catchment.shape == flowline.shape):
        raise ValueError(
            "invalid_shape: elevation, receiver and both masks must share one shape")
    shape = elevation.shape
    routing_cells = int(elevation.size)
    if routing_cells > ROUTE_MAX_CELLS:
        raise ValueError(
            "budget_route: the route grid holds %d cells, above the reach-router "
            "MAX_CELLS=%d; declare a smaller routing sub-window instead of "
            "shrinking the data" % (routing_cells, ROUTE_MAX_CELLS))

    origin = _origin(origin_native_xz)
    binding_identity = _source_identity(source_identity_sha256)
    seed = _world_seed(world_seed)

    graph = _receiver_diagnostics(receiver_array, shape, origin, seed)
    flat_receiver = graph["flat"]
    basin = _catchment_diagnostics(flat_receiver, catchment, elevation.ravel())
    line = _flowline_diagnostics(flowline, basin["mask"], flat_receiver,
                                 basin["terminal"])
    terminal = basin["terminal"]

    if not isinstance(rain_mm_h, np.ndarray) or rain_mm_h.ndim != 1:
        raise ValueError(
            "rain_not_interval_series: rain_mm_h must be a 1-D interval series, one "
            "value per physical interval; a cumulative table or a per-cell field "
            "cannot be declared here")
    if rain_mm_h.dtype.kind not in "fiu" or not np.isfinite(rain_mm_h).all():
        raise ValueError(
            "invalid_rain: the interval series must be finite and real-valued")
    if (rain_mm_h < 0).any() or (rain_mm_h > 1e6).any():
        raise ValueError("invalid_rain: interval rain must lie in [0, 1e6] mm/h")
    rain = np.ascontiguousarray(rain_mm_h, dtype=np.float64)
    intervals = int(rain.size)
    if intervals < 1:
        raise ValueError("invalid_rain: at least one interval is required")

    _positive_scalar(dt_s, "dt_s", 1e7)
    if dt_s < 1e-6:
        raise ValueError("invalid_dt_s: dt_s must be >= 1e-6 s")
    _positive_scalar(travel_speed_m_s, "travel_speed_m_s", 100.0)
    _positive_scalar(minimum_reach_length_m, "minimum_reach_length_m", 1e6)
    if not isinstance(runoff_parameters, RunoffParameters):
        raise ValueError(
            "runoff_parameters_required: an explicit RunoffParameters instance is "
            "required; no default soil bucket is assumed")
    runoff_parameters.__post_init__()

    active = np.flatnonzero(basin["mask"])
    active_cells = int(active.size)
    spacing = float(NATIVE_SPACING_M)
    cell_area = spacing * spacing
    land = elevation.ravel() > 0

    bucket_budget = _rainfall_budget(intervals, active_cells)
    _route_budget(intervals, routing_cells, 1, 1)
    diagnostic_budget = _diagnostic_budget(intervals, routing_cells)

    # --- soil bucket, catchment cells only ---------------------------------- #
    rain_block = np.broadcast_to(rain[:, None], (intervals, active_cells)).copy()
    areas = np.full(active_cells, cell_area, dtype=np.float64)
    source_id = "native-30m-catchment-event:%s:terminal-%d" % (
        binding_identity[:16], terminal)
    bucket = simulate_rainfall_runoff(rain_block, areas, dt_s=float(dt_s),
                                     source_id=source_id,
                                     parameters=runoff_parameters)
    local_q = bucket["local_q_m3_s"]

    # --- reach mapping, once, to learn which reach each catchment cell owns -- #
    outlet_mask = (receiver_array < 0)
    provisional_owner = np.full(routing_cells, -1, dtype=np.int64)
    provisional_owner[land] = 0
    provisional_area = np.array([float(np.count_nonzero(land)) * cell_area],
                                dtype=np.float64)
    provisional = {"height_m": elevation, "receiver": receiver_array,
                   "flowline_mask": flowline, "outlet_mask": outlet_mask,
                   "cell_owner": provisional_owner.reshape(shape),
                   "area_m2": provisional_area}
    try:
        mapping = build_reaches(**provisional, spacing_m=spacing,
                               speed_m_s=float(travel_speed_m_s),
                               minimum_length_m=float(minimum_reach_length_m))
    except ValueError as error:
        raise ValueError("route_mapping_rejected: %s" % (error,)) from error
    cell_reach = mapping["cell_reach"].ravel()

    reach_ids, group_of_active = np.unique(cell_reach[active], return_inverse=True)
    groups = int(reach_ids.size)
    outside_cells = int(np.count_nonzero(land & ~basin["mask"]))
    outside_group = 1 if outside_cells else 0
    hrus = groups + outside_group
    if hrus > ROUTE_MAX_HRUS:
        raise ValueError(
            "budget_hru: %d catchment cells occupy %d distinct reaches, plus %d "
            "outside HRU(s), which exceeds the reach-router MAX_HRUS=%d; per-cell "
            "HRUs would need %d and are not available either"
            % (active_cells, groups, outside_group, ROUTE_MAX_HRUS, active_cells))

    owner = np.full(routing_cells, -1, dtype=np.int64)
    owner[active] = group_of_active
    if outside_group:
        owner[land & ~basin["mask"]] = groups
    counts = np.bincount(owner[land], minlength=hrus)
    hru_area = counts.astype(np.float64) * cell_area

    hru_q = np.zeros((intervals, hrus), dtype=np.float64)
    for step in range(intervals):
        hru_q[step, :groups] = np.bincount(group_of_active, weights=local_q[step],
                                           minlength=groups)

    binding = {
        "algorithm": ALGORITHM,
        "origin_native_xz": origin,
        "source_identity_sha256": binding_identity,
        "world_seed": seed,
        "spacing_m": spacing,
        "grid_shape": [int(shape[0]), int(shape[1])],
        "elevation_sha256": _array_sha256(elevation),
        "receiver_sha256": _array_sha256(receiver_array),
        "catchment_mask_sha256": _array_sha256(catchment),
        "flowline_mask_sha256": _array_sha256(flowline),
        "terminal_flat_cell": int(terminal),
        "terminal_native_xz": [origin[0] + int(terminal % shape[1]),
                               origin[1] + int(terminal // shape[1])],
        "rain_mm_h_sha256": _array_sha256(rain),
        "runoff_parameter_sha256": bucket["metadata"]["parameter_sha256"],
        "dt_s": float(dt_s),
        "travel_speed_m_s": float(travel_speed_m_s),
        "minimum_reach_length_m": float(minimum_reach_length_m),
    }

    # --- reach routing: the only quantity with travel delay ------------------ #
    route_inputs = {"height_m": elevation, "receiver": receiver_array,
                    "flowline_mask": flowline, "outlet_mask": outlet_mask,
                    "cell_owner": owner.reshape(shape),
                    "area_m2": hru_area, "local_q_m3_s": hru_q}
    routed = route_local_discharge(route_inputs, dt_s=float(dt_s),
                                  spacing_m=spacing, source_binding=binding,
                                  speed_m_s=float(travel_speed_m_s),
                                  minimum_length_m=float(minimum_reach_length_m))

    # The pre-pass mapping must be the mapping the router actually used. Only the
    # HRU-independent keys are compared: `allocation_counts` is [reach, HRU] and
    # therefore differs in width by construction, and the fraction assertion
    # below is what checks it.
    for key in ("river_reach", "cell_reach", "reach_downstream", "reach_length_m",
                "tau_s"):
        if not np.array_equal(np.asarray(mapping[key]), np.asarray(routed[key])):
            raise ValueError(
                "route_mapping_rejected: the %s mapping changed between the "
                "attribution pre-pass and the routing call" % key)

    fractions = ((routed["allocation_counts"] * spacing ** 2)
                 / routed["area_m2"][None, :])
    own_fraction = fractions[reach_ids, np.arange(groups)]
    if not np.all(own_fraction == 1.0):
        raise ValueError(
            "hru_fraction_not_unit: a catchment HRU is rescale-weighted by the "
            "router (own-reach fraction not exactly 1.0), so its water would be "
            "spread over reaches it does not drain to")
    if not np.all(fractions[:, :groups].sum(axis=0) == 1.0):
        raise ValueError(
            "hru_fraction_not_unit: a catchment HRU does not allocate exactly its "
            "whole unit fraction to its own reach")
    if outside_group and np.any(hru_q[:, groups:] != 0):
        raise ValueError(
            "hru_fraction_not_unit: the outside-catchment HRU would carry nonzero "
            "declared local Q")

    terminal_reach = int(routed["river_reach"].ravel()[terminal])
    if terminal_reach < 0:
        raise ValueError(
            "terminal_not_on_a_flowline: the declared terminal has no routed reach")
    if int(routed["reach_downstream"][terminal_reach]) != -1:
        raise ValueError(
            "terminal_reach_not_terminal: the reach holding the declared terminal "
            "does not end there")
    routed_q = routed["outflow_volume_m3"][:, terminal_reach] / float(dt_s)
    design_interval = int(np.argmax(routed_q))
    design_q = float(routed_q[design_interval])

    # --- instantaneous diagnostic accumulation on the same graph ------------ #
    valid_mask = np.ones(shape, dtype=bool)
    terminal_kind = np.full(shape, "interior", dtype="U24")
    terminal_kind[outlet_mask] = DIAGNOSTIC_TERMINAL_LABEL
    unknown = np.zeros(shape, dtype=bool)
    input_total = np.zeros(intervals, dtype=np.float64)
    retained = np.zeros(intervals, dtype=np.float64)
    open_outflow = np.zeros(intervals, dtype=np.float64)
    unknown_pending = np.zeros(intervals, dtype=np.float64)
    residual = np.zeros(intervals, dtype=np.float64)
    instantaneous = np.zeros(intervals, dtype=np.float64)
    other_terminal_peak = 0.0
    terminal_field = np.zeros(routing_cells, dtype=np.float64)
    peak_payload = None
    for step in range(intervals):
        terminal_field[:] = 0.0
        terminal_field[active] = local_q[step]
        try:
            ledger = accumulate_network_discharge(
                receiver_array, terminal_field.reshape(shape), valid_mask,
                terminal_kind=terminal_kind)
        except ValueError as error:
            raise ValueError("diagnostic_graph_rejected: %s" % (error,)) from error
        input_total[step] = ledger["input_total_m3_s"]
        retained[step] = ledger["retained_m3_s"]
        open_outflow[step] = ledger["open_outflow_m3_s"]
        unknown_pending[step] = ledger["unknown_pending_m3_s"]
        residual[step] = ledger["residual_m3_s"]
        terminal_series = ledger["terminal_q_m3_s"].ravel()
        instantaneous[step] = float(terminal_series[terminal])
        other = float(np.abs(terminal_series).sum() - abs(terminal_series[terminal]))
        other_terminal_peak = max(other_terminal_peak, other)
        if step == design_interval:
            peak_payload = {
                "interval_index": int(step),
                "interval_seconds": [float(step) * float(dt_s),
                                     float(step + 1) * float(dt_s)],
                "receiver": receiver_array.copy(),
                "local_q_m3_s": terminal_field.reshape(shape).copy(),
                "valid_mask": valid_mask.copy(),
                "terminal_kind": terminal_kind.copy(),
                "upstream_unknown_mask": unknown.copy(),
                "known_routed_q_m3_s": ledger["known_routed_q_m3_s"].copy(),
                "complete_mask": ledger["complete_mask"].copy(),
                "terminal_q_m3_s": ledger["terminal_q_m3_s"].copy(),
            }
    instantaneous_interval = int(np.argmax(instantaneous))

    # --- cross-checks: water budget, attribution, terminal isolation -------- #
    injected = float(routed["lateral_volume_m3"].sum())
    expected_injected = float(local_q.sum() * float(dt_s))
    injection_gap = injected - expected_injected
    if abs(injection_gap) > 1e-12 * max(1.0, expected_injected):
        raise ValueError(
            "routing_injection_mismatch: the reach router injected %.6e m3 but the "
            "soil bucket released %.6e m3" % (injected, expected_injected))
    outlet_gap = float(np.abs(routed["outlet_q_m3_s"] - routed_q).max())
    if outlet_gap > 1e-12 * max(1.0, float(np.abs(routed_q).max())):
        raise ValueError(
            "routing_injection_mismatch: a reach other than the terminal one "
            "discharges to the outlet, so outside-catchment water leaked in")
    bucket_outflow = float(bucket["outflow_volume_m3"].sum())
    diagnostic_retained_gap = float(np.abs(retained - input_total).max())
    if diagnostic_retained_gap > 1e-12 * max(1.0, float(input_total.max(initial=0.0))):
        raise ValueError(
            "diagnostic_graph_rejected: the instantaneous accumulation lost water "
            "to other terminals or to an undeclared outflow")
    # Interval volume account, recomputed independently of the router's own
    # ledger: bucket release = terminal outlet volume + total storage change.
    # `outlet_q_m3_s` is a rate, so it is converted back to a volume here.
    global_residual = (local_q.sum(axis=1) * float(dt_s)
                       - routed["outlet_q_m3_s"] * float(dt_s)
                       - routed["storage_change_m3"].sum(axis=1))
    accumulated_storage = float(routed["storage_m3"][-1].sum())
    if float(np.abs(global_residual).max(initial=0.0)) > 1e-12 * max(
        1.0, float(expected_injected)):
        raise ValueError(
            "routing_injection_mismatch: the interval volume account does not close "
            "(max |release - outlet - storage change| = %.6e m3)"
            % float(np.abs(global_residual).max()))

    identity = {
        "algorithm": ALGORITHM,
        "schema": SCHEMA,
        "source": binding,
        "time_edges_s": [float(index) * float(dt_s) for index in range(intervals + 1)],
        "rain_mm_h_sha256": binding["rain_mm_h_sha256"],
        "local_q_m3_s_sha256": _array_sha256(local_q),
        "active_cells_sha256": _array_sha256(active.astype(np.int64)),
        "routed_terminal_q_sha256": _array_sha256(routed_q),
        "instantaneous_terminal_q_sha256": _array_sha256(instantaneous),
        "terminal_reach": int(terminal_reach),
        "reach_parameter_sha256": routed["metadata"]["parameter_sha256"],
    }

    return {
        "algorithm": ALGORITHM,
        "schema": SCHEMA,
        "event_identity_sha256": hashlib.sha256(
            _canonical(identity).encode("utf-8")).hexdigest(),
        "identity": identity,
        "source": dict(binding),
        "time": {
            "dt_s": float(dt_s),
            "intervals": intervals,
            "time_edges_s": np.arange(intervals + 1, dtype=np.float64) * float(dt_s),
            "rain_semantics": RAIN_SEMANTICS,
            "rain_scope": "uniform over every active catchment cell",
            "cell_order": CELL_ORDER,
            "outside_catchment_scope": OUTSIDE_SCOPE,
        },
        "rain_mm_h": rain.copy(),
        "active_cells": active.astype(np.int64),
        "active_cell_area_m2": cell_area,
        "local_q_m3_s": local_q.copy(),
        "instantaneous_terminal_q_m3_s": instantaneous,
        "routed_terminal_q_m3_s": routed_q.copy(),
        "design_q_m3_s": design_q,
        "design_q_interval_index": design_interval,
        "design_q_peak_time_s": float(design_interval + 1) * float(dt_s),
        "design_q_semantics": DESIGN_Q_SEMANTICS,
        "instantaneous_q_semantics": INSTANTANEOUS_Q_SEMANTICS,
        "instantaneous_peak_m3_s": float(instantaneous[instantaneous_interval]),
        "instantaneous_peak_interval_index": instantaneous_interval,
        "instantaneous_over_routed_peak_ratio": (
            float(instantaneous[instantaneous_interval] / design_q)
            if design_q > 0 else None),
        "event_design_q_not_bankfull": True,
        "terminal": {
            "flat_cell": int(terminal),
            "rc": [int(terminal // shape[1]), int(terminal % shape[1])],
            "native_xz": binding["terminal_native_xz"],
            "semantics": TERMINAL_SEMANTICS,
            "on_flowline": bool(line["mask"][terminal]),
            "reach": int(terminal_reach),
            "reach_length_m": float(routed["reach_length_m"][terminal_reach]),
            "reach_tau_s": float(routed["tau_s"][terminal_reach]),
            "catchment_cells": active_cells,
            "flowline_cells": line["cells"],
            "terminal_count_in_grid": int(outlet_mask.sum()),
        },
        "runoff": {
            "kernel": "terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff",
            "source_id": bucket["metadata"]["source_id"],
            "parameters": asdict(runoff_parameters),
            "parameter_sha256": bucket["metadata"]["parameter_sha256"],
            "q_semantics": bucket["metadata"]["q_semantics"],
            "rain_volume_m3": bucket["rain_volume_m3"].sum(axis=1),
            "et_volume_m3": bucket["et_volume_m3"].sum(axis=1),
            "outflow_volume_m3": bucket["outflow_volume_m3"].sum(axis=1),
            "storage_change_m3": bucket["storage_change_m3"].sum(axis=1),
            "balance_residual_m3": bucket["balance_residual_m3"].sum(axis=1),
            "terminal_storage_mm": {
                "soil_mm": float(bucket["soil_mm"][-1, 0]),
                "fast_mm": float(bucket["fast_mm"][-1, 0]),
                "slow_mm": float(bucket["slow_mm"][-1, 0]),
                "note": "every active cell is identical, so cell 0 is the whole state",
            },
            "total_outflow_volume_m3": bucket_outflow,
        },
        "routing": routed,
        "diagnostic": {
            "kernel": ("terrain_pipeline.surface_rivers.metric_network_accumulation"
                       ".accumulate_network_discharge"),
            "semantics": INSTANTANEOUS_Q_SEMANTICS,
            "terminal_label": DIAGNOSTIC_TERMINAL_LABEL,
            "input_total_m3_s": input_total,
            "retained_m3_s": retained,
            "open_outflow_m3_s": open_outflow,
            "unknown_pending_m3_s": unknown_pending,
            "residual_m3_s": residual,
            "peak_interval_index": design_interval,
            "peak_interval_payload": peak_payload,
            "payload_note": ("one declared interval only; no per-interval product "
                             "is retained here and no file is written"),
        },
        "checks": {
            "injected_volume_m3": injected,
            "bucket_local_volume_m3": expected_injected,
            "injection_gap_m3": float(injection_gap),
            "routing_outlet_gap_m3_s": float(outlet_gap),
            "routing_max_abs_reach_residual_m3": float(
                np.abs(routed["balance_residual_m3"]).max()),
            "routing_max_abs_global_residual_m3": float(np.abs(global_residual).max()),
            "diagnostic_max_abs_residual_m3_s": float(np.abs(residual).max()),
            "diagnostic_retained_minus_input_m3_s": diagnostic_retained_gap,
            "non_terminal_terminal_q_sum_max_m3_s": float(other_terminal_peak),
            "hru_own_reach_fraction_deviation": float(np.abs(own_fraction - 1.0).max()),
            "routed_peak_not_above_instantaneous_peak": bool(design_q <=
                                                            instantaneous.max()),
            "outside_catchment_local_q_max_m3_s": 0.0,
            "terminal_instantaneous_equals_bucket_total_max_m3_s": float(
                np.abs(instantaneous - local_q.sum(axis=1)).max()),
        },
        "budget": {
            "rainfall_runoff": bucket_budget,
            "route": _route_budget(intervals, routing_cells, hrus,
                                   int(routed["tau_s"].size)),
            "diagnostic": diagnostic_budget,
            "hru_plan": {
                "catchment_cells": active_cells,
                "groups": groups,
                "outside_groups": outside_group,
                "total_hrus": hrus,
                "max_hrus": ROUTE_MAX_HRUS,
                "per_cell_hrus_possible": bool(active_cells <= ROUTE_MAX_HRUS),
                "attribution": ("one HRU per reach that owns at least one catchment "
                                "cell, so each HRU's area equals its cell count "
                                "times the cell area and its own-reach fraction is "
                                "exactly 1"),
            },
            "reach_count": int(routed["tau_s"].size),
            "max_reaches": ROUTE_MAX_REACHES,
            "max_route_steps": ROUTE_MAX_STEPS,
        },
        "capabilities": {
            "natural_outlet_certified": False,
            "hydraulic_ready": False,
            "bankfull": False,
            "calibrated": False,
            "publishable": False,
            "bundle_written": False,
            "topology_window_invariance_verified": False,
            "finite_graph_only": True,
            "spatially_variable_forcing_supported": False,
        },
    }
