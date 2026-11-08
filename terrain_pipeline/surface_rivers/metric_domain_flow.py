"""Domain water ledger: rainfall -> production -> routing -> outlet, per domain.

Why this module exists
----------------------
`metric_domain_pipeline` turns world coordinates into domain products that carry
**geometry and ownership only** (`metric_domain_pipeline.py:123-141`): a product
says which land cells drain to which outlet, and certifies nothing about water.
`metric_runoff` produces a diagnostic local runoff that declares itself
`not_river_routed`, and `accumulate_local_discharge` can sum an arbitrary local
`q` along a diagnostic graph -- but nothing yet joins the two to the closure
module's own domains.

This module closes that gap **for one world-anchored tile**: it injects rainfall
only on the cells the closure module accepted, runs the repository's one soil
bucket on them, routes the released water along the closure module's own
raw-face D8 receiver, and reports where every cubic metre went -- to the sea, or
into a closed basin. It writes no second flood and no second steepest-D8 pass:
the routing arrays come from `metric_domain_closure.domain_topology`, and the
bucket equations come from `rainfall_runoff.simulate_rainfall_runoff`. Both are
called, not copied, because a second implementation would be a second truth that
can drift from the one the auditor certifies.

What is certified, and what is not
----------------------------------
Certified: the **volume ledger closes**. For every published domain,
`rain_input_m3` is split into `actual_et_m3`, `soil_storage_change_m3` and the
water that leaves the producing cells (`terminal_release_m3`), and the released
water is routed along the closure module's receiver to that domain's own
terminal -- so `terminal_release_m3` is exactly the volume delivered to the
outlet (the sea for a `marine` domain, a closed basin for an `inland` one). The
per-domain residual and the tile-level residual are reported, never hidden.

NOT certified (declared, not discovered later):

* the soil bucket parameters are the repository's **illustrative, uncalibrated**
  values (`rainfall_runoff.RunoffParameters`); this is a water *accounting*
  chain, not a calibrated catchment;
* a coarse conditioning node is treated as one area element of `spacing_m ** 2`
  (10 km x 10 km at the default config, i.e. 1e8 m^2). Routing inside one step is
  instantaneous and volume-conserving, the same approximation
  `accumulate_local_discharge` already uses; it is not a flood wave;
* the base face is the RAW pure field, not a Terrain Diffusion inference window
  (`diffusion/geography_physical.py:1` -- "coordinate-continuous physical
  conditioning, not model-generated terrain"); no local TD detail is added;
* rainfall on cells the closure module refused (`unresolved_border`), on the sea,
  and outside the core is **not routed** and is reported in its own tally, so a
  refusal can never be mistaken for a land cell that simply received no rain.

Refusals are first-class
------------------------
Rainfall over the refused set has an unknown destination: the chain may leave the
tile, so the module refuses to route it rather than guessing. The tally
`unresolved_rain_m3` / `ocean_direct_rain_m3` / `outside_core_rain_m3` makes the
partition auditable, and `requested_rain_m3` equals their sum plus the routed
`rain_input_m3` to within the accumulator tolerance.
"""
from __future__ import annotations

import math

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff
from terrain_pipeline.surface_rivers.metric_domain_closure import domain_topology

__all__ = [
    "ALGORITHM",
    "FLOW_SCHEMA",
    "LIMITATIONS",
    "MAX_INTERVALS",
    "PRODUCT_KEYS",
    "domain_flow_name",
    "domain_flow_topology",
    "load_domain_flow",
    "save_domain_flow",
    "solve_domain_flow",
    "validate_domain_flow",
]

ALGORITHM = "domain-water-ledger-v1"
FLOW_SCHEMA = "river-domain-flow-v1"

# `simulate_rainfall_runoff` budgets `24 * 8 * (steps + 1) * cells <= 256 MB` AND
# `steps * cells <= 1e6` with a 100 000-cell cap. A 129 x 129 core has 16 641
# nodes, so the binding cap is `steps <= 1e6 / 16641 ~= 60`. The limit is stated
# here rather than discovered as a solver error at run time.
MAX_INTERVALS = 60

# Contract key set of a published flow product, in order. The npz carries
# exactly these plus nothing else, so a reader sees the whole schema at a glance.
#
# Deliberately ALL series (1-D) and no 0-d scalars: `seed`, `config_id`,
# `spacing_m`, `dt_s`, `interval_count` and `schema` live in `metadata` instead.
# A 0-d array does not survive `mountain_source_adapter.readonly` -- that helper
# funnels every array through `np.ascontiguousarray`, which promotes a 0-d array
# to shape `(1,)` -- so keeping them out of the array set is what makes a reload
# bit-identical to the in-memory bundle rather than an accident of dtype.
PRODUCT_KEYS = (
    "outlet_x_m",
    "outlet_z_m",
    "kind",
    "cell_count",
    "area_m2",
    "rain_input_m3",
    "actual_et_m3",
    "soil_storage_change_m3",
    "terminal_release_m3",
    "domain_residual_m3",
    "cells_x_m",
    "cells_z_m",
    "cell_offsets",
    "limitations",
)

LIMITATIONS = (
    "soil bucket parameters are the repository's illustrative, uncalibrated "
    "RunoffParameters; this is a water accounting chain, not a calibrated catchment",
    "one coarse conditioning node is treated as one area element of spacing_m**2; "
    "routing inside an interval is instantaneous and volume conserving (the same "
    "approximation accumulate_local_discharge uses), not a flood wave",
    "the base face is the RAW pure conditioning field, not a Terrain Diffusion "
    "inference window; no local TD detail is added and no TD identity is claimed",
    "rainfall on refused cells (unresolved_border), on the sea, and outside the core "
    "is deliberately not routed and is reported in its own tally",
    "cells are the accepted LAND cells of the owning tile's CORE; a domain that "
    "continues past the core publishes only its core part",
    "no channel geometry, width, depth, sediment or terrain feedback is certified; "
    "hydraulic_ready / natural_outlet_verified / publishable remain false",
)


def _finite_array(value, shape, name, *, nonnegative=True):
    array = np.asarray(value, np.float64)
    if array.shape != shape:
        raise ValueError("%s must have shape %s; got %s" % (name, shape, array.shape))
    if not np.isfinite(array).all():
        raise ValueError("%s must be finite" % name)
    if nonnegative and np.any(array < 0.0):
        raise ValueError("%s must be nonnegative" % name)
    return array


def _validate_time(dt_s, intervals):
    """Shared time-step validation, so both entry points reject identically."""
    if not isinstance(dt_s, (int, float)) or isinstance(dt_s, (bool, np.bool_)):
        raise ValueError("dt_s must be a number")
    dt_s = float(dt_s)
    if not math.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    if not isinstance(intervals, int) or isinstance(intervals, bool):
        raise ValueError("intervals must be an integer")
    if not 1 <= intervals <= MAX_INTERVALS:
        raise ValueError("intervals must be 1..%d" % MAX_INTERVALS)
    return dt_s, intervals


def _rain_series(rain_mm_h, intervals, core_cells):
    """Rainfall depth rate [mm/h] on the core node grid, from scalar/step/grid.

    Accepted forms:

    * a scalar: the same rate over every core node and every interval;
    * `(intervals,)`: one rate per interval, uniform over the core;
    * `(intervals, core+1, core+1)`: a rate per interval and core node.

    Anything else is an input error, never silently broadcast.
    """
    if isinstance(rain_mm_h, (bool, np.bool_)):
        raise ValueError("rain_mm_h must be a number or array, not a bool")
    if np.ndim(rain_mm_h) == 0:
        rate = float(rain_mm_h)
        if not math.isfinite(rate) or rate < 0.0:
            raise ValueError("rain_mm_h must be finite and nonnegative")
        return np.full((intervals, core_cells + 1, core_cells + 1), rate, np.float64)
    array = np.asarray(rain_mm_h, np.float64)
    if array.ndim == 1:
        if array.shape[0] != intervals:
            raise ValueError("rain_mm_h per-interval length must equal intervals")
        return np.broadcast_to(_finite_array(array, (intervals,), "rain_mm_h")[:, None, None],
                               (intervals, core_cells + 1, core_cells + 1)).copy()
    if array.ndim == 3:
        return _finite_array(array, (intervals, core_cells + 1, core_cells + 1), "rain_mm_h")
    raise ValueError("rain_mm_h must be a scalar, (intervals,), or (intervals, core+1, core+1)")


def _route_to_terminals(receiver, terminal, released_m3):
    """Volume landed on each terminal, from a per-cell release.

    `terminal` is constant along a strictly-downhill chain and equals a
    terminal cell's own index there, so summing each cell's release into its
    terminal cell already gives the volume that arrives -- no per-cell walk and
    no traversal order is involved. The routing arrays come from the closure
    module's own D8, so no second topological truth is created.
    """
    flow = np.asarray(released_m3, np.float64)
    flat_terminal = np.asarray(terminal, np.int64).reshape(-1)
    if flow.shape != np.asarray(receiver).shape:
        raise ValueError("released volume must share the receiver's shape")
    if not np.isfinite(flow).all() or np.any(flow < 0.0):
        raise ValueError("released volume must be finite and nonnegative")
    landed = np.zeros(flat_terminal.size, np.float64)
    np.add.at(landed, flat_terminal, flow.reshape(-1))
    return landed.reshape(flow.shape)


def _production(seed, topology, rain_mm_h, parameters, dt_s, intervals):
    """The per-cell production half of the ledger, on one resolved topology.

    Extracted from `solve_domain_flow` **verbatim** so the read-only accessor
    `domain_flow_topology` can expose the same numbers a published product is built
    from, without a second bucket implementation that could drift from it. The
    extraction is behaviour-preserving: `solve_domain_flow`'s published identity is
    unchanged by it (checked against a recorded baseline).

    Returns a dict; every array is freshly allocated and safe to keep.
    """
    spacing = float(topology["spacing_m"])
    cell_area_m2 = spacing * spacing
    core_cells = int(topology["core_cells"])
    margin = int(topology["margin"])
    rows, columns = topology["shape"]
    accepted = topology["accepted"]
    ocean = topology["ocean"]
    unresolved = topology["unresolved"]

    core_slice = np.s_[margin:margin + core_cells + 1, margin:margin + core_cells + 1]
    core_accepted = accepted[core_slice]
    core_ocean = ocean[core_slice]
    core_unresolved = unresolved[core_slice]

    rain = _rain_series(rain_mm_h, intervals, core_cells)
    # `rain` is a depth RATE in mm/h, exactly what `simulate_rainfall_runoff`
    # takes. Volume in m^3 needs a depth in metres, so the mm depth is divided by
    # 1000 here; this is the same conversion the solver's own
    # `rain_volume_m3 = rain_depth * area / 1000` performs, kept explicit so the
    # unit is visible at the partition instead of hidden inside a factor.
    depth_per_interval_m = rain * (dt_s / 3600.0) / 1000.0

    def _volume(mask):
        return float(np.sum(depth_per_interval_m[:, mask], dtype=np.float64) * cell_area_m2)

    requested_rain_m3 = float(np.sum(depth_per_interval_m, dtype=np.float64) * cell_area_m2)
    unresolved_rain_m3 = _volume(core_unresolved)
    ocean_direct_rain_m3 = _volume(core_ocean & ~core_unresolved)
    routed_mask = core_accepted
    routed_rain_m3 = _volume(routed_mask)
    outside_core_rain_m3 = 0.0

    if np.any(core_accepted & (core_ocean | core_unresolved)):
        raise ValueError("accepted cells cannot be ocean or unresolved (contract 3)")

    # One soil bucket for every producing cell, the repository's own solver.
    core_rows, core_columns = np.nonzero(routed_mask)
    if core_rows.size:
        tile_rows = core_rows + margin
        tile_columns = core_columns + margin
        producing_flat = tile_rows * columns + tile_columns
        rain_series = rain[:, core_rows, core_columns]  # [T, N]
        runoff = simulate_rainfall_runoff(
            rain_series, np.full(core_rows.size, cell_area_m2, np.float64),
            dt_s=dt_s, source_id="%s:%d" % (ALGORITHM, seed), parameters=parameters)
        released_per_interval_m3 = np.asarray(runoff["outflow_volume_m3"], np.float64)
        released_per_cell_m3 = np.sum(released_per_interval_m3, axis=0, dtype=np.float64)
        et_per_cell_m3 = np.sum(runoff["et_volume_m3"], axis=0, dtype=np.float64)
        storage_per_cell_m3 = np.sum(runoff["storage_change_m3"], axis=0, dtype=np.float64)
        bucket_residual_per_cell_m3 = np.sum(runoff["balance_residual_m3"], axis=0, dtype=np.float64)
        if not (np.isfinite(released_per_cell_m3).all()
                and np.isfinite(et_per_cell_m3).all()
                and np.isfinite(storage_per_cell_m3).all()):
            raise ValueError("runoff ledger produced nonfinite volumes")
    else:
        producing_flat = np.zeros(0, np.int64)
        released_per_cell_m3 = np.zeros(0, np.float64)
        et_per_cell_m3 = np.zeros(0, np.float64)
        storage_per_cell_m3 = np.zeros(0, np.float64)
        bucket_residual_per_cell_m3 = np.zeros(0, np.float64)
        released_per_interval_m3 = np.zeros((intervals, 0), np.float64)

    # The aggregate ledger keeps its existing totals; the read-only accessor also
    # exposes each bucket interval without reconstructing a hydrograph from totals.
    released_grid = np.zeros((rows, columns), np.float64)
    released_grid.reshape(-1)[producing_flat] = released_per_cell_m3
    released_per_interval_grid = np.zeros((intervals, rows, columns), np.float64)
    if producing_flat.size:
        released_per_interval_grid.reshape(intervals, -1)[:, producing_flat] = released_per_interval_m3

    return {
        "spacing_m": spacing,
        "cell_area_m2": cell_area_m2,
        "core_cells": core_cells,
        "margin": margin,
        "shape": (int(rows), int(columns)),
        "producing_flat": producing_flat,
        "released_per_cell_m3": released_per_cell_m3,
        "released_grid_m3": released_grid,
        "released_per_interval_grid_m3": released_per_interval_grid,
        "et_per_cell_m3": et_per_cell_m3,
        "soil_storage_change_per_cell_m3": storage_per_cell_m3,
        "bucket_residual_per_cell_m3": bucket_residual_per_cell_m3,
        "rain_depth_per_interval_m": depth_per_interval_m,
        "requested_rain_m3": requested_rain_m3,
        "routed_rain_m3": routed_rain_m3,
        "unresolved_rain_m3": unresolved_rain_m3,
        "ocean_direct_rain_m3": ocean_direct_rain_m3,
        "outside_core_rain_m3": outside_core_rain_m3,
    }


def domain_flow_topology(seed, x_m, z_m, rain_mm_h, *, config=None, parameters=None,
                         dt_s=3600.0, intervals=12):
    """Read-only per-cell water quantities for the tile holding a world point.

    This is a **pure addition** in the same spirit as
    `metric_domain_closure.domain_topology`: it runs the ledger's own production
    half once and hands back its arrays (plus the topology the routing is built on),
    so a consumer never authors a second bucket. Nothing published changes and no
    existing function's signature or behaviour is touched.

    Every returned array is freshly allocated: mutating one cannot alter any answer,
    and no cached state is exposed. Keys are those of `_production` plus the
    routing topology under `"topology"` (`metric_domain_closure.domain_topology`,
    itself already documented as read-only and copied).

    Units, stated because they matter here: `released_grid_m3` is a **volume in
    cubic metres** released over the whole run (all `intervals`), on ONE coarse node
    of `spacing_m`. It is not a discharge. A consumer that needs a rate must divide
    by the physical duration it claims, and say which duration it used.
    `released_per_interval_grid_m3` is `[interval, z, x]` volume in m³, emitted
    directly by the same soil-bucket solve. It is local runoff, not routed discharge; a
    consumer must route it exactly once along the returned topology.
    """
    config = config or PlanningConfig()
    config.validate()
    parameters = parameters or RunoffParameters()
    if not isinstance(parameters, RunoffParameters):
        raise ValueError("RunoffParameters required")
    dt_s, intervals = _validate_time(dt_s, intervals)
    topology = domain_topology(seed, float(x_m), float(z_m), config)
    result = _production(seed, topology, rain_mm_h, parameters, dt_s, intervals)
    result["topology"] = topology
    result["dt_s"] = dt_s
    result["interval_count"] = intervals
    return result


def solve_domain_flow(seed, points_xz_m, rain_mm_h, *, config=None, parameters=None,
                      dt_s=3600.0, intervals=12):
    """Rainfall -> production -> routing -> per-domain outlet ledger, one tile.

    `points_xz_m` selects the world-anchored tile (every point must share it; the
    first point picks it and any point in another tile is an input error, never a
    silent second tile). `rain_mm_h` is a scalar, a per-interval rate, or a grid on
    the core node lattice (see `_rain_series`). `intervals` is the number of
    physical timesteps of length `dt_s` seconds.

    Returns a bundle: `arrays` (the published schema), `metadata` and
    `identity_sha256`. It is exactly what `save_domain_flow` writes and
    `load_domain_flow` re-verifies.
    """
    config = config or PlanningConfig()
    config.validate()
    parameters = parameters or RunoffParameters()
    if not isinstance(parameters, RunoffParameters):
        raise ValueError("RunoffParameters required")
    dt_s, intervals = _validate_time(dt_s, intervals)

    points = [(float(x), float(z)) for x, z in points_xz_m]
    if not points:
        raise ValueError("at least one world point is required to select the tile")
    topology = domain_topology(seed, points[0][0], points[0][1], config)
    for x_m, z_m in points[1:]:
        other = domain_topology(seed, x_m, z_m, config)
        if (other["origin_x_m"] != topology["origin_x_m"]
                or other["origin_z_m"] != topology["origin_z_m"]):
            raise ValueError("all points must share one world-anchored tile; "
                             "got a second tile at (%r, %r)" % (x_m, z_m))

    spacing = float(topology["spacing_m"])
    cell_area_m2 = spacing * spacing
    core_cells = int(topology["core_cells"])
    margin = int(topology["margin"])
    rows, columns = topology["shape"]
    receiver = topology["receiver"]
    terminal = topology["terminal"]
    ocean_terminal = topology["ocean_terminal"]
    owner_x = topology["owner_outlet_x_m"]
    owner_z = topology["owner_outlet_z_m"]

    production = _production(seed, topology, rain_mm_h, parameters, dt_s, intervals)
    depth_per_interval_m = production["rain_depth_per_interval_m"]
    requested_rain_m3 = production["requested_rain_m3"]
    unresolved_rain_m3 = production["unresolved_rain_m3"]
    ocean_direct_rain_m3 = production["ocean_direct_rain_m3"]
    routed_rain_m3 = production["routed_rain_m3"]
    outside_core_rain_m3 = production["outside_core_rain_m3"]
    producing_flat = production["producing_flat"]
    released_per_cell_m3 = production["released_per_cell_m3"]
    et_per_cell_m3 = production["et_per_cell_m3"]
    storage_per_cell_m3 = production["soil_storage_change_per_cell_m3"]
    bucket_residual_per_cell_m3 = production["bucket_residual_per_cell_m3"]

    # Route the released volume along the closure module's own receiver.
    landed = _route_to_terminals(receiver, terminal, production["released_grid_m3"])

    terminal_flat = np.asarray(terminal, np.int64).reshape(-1)
    producing_terminals = terminal_flat[producing_flat]
    producing_outlet_x = owner_x.reshape(-1)[producing_flat]
    producing_outlet_z = owner_z.reshape(-1)[producing_flat]
    if producing_flat.size and not (np.isfinite(producing_outlet_x).all()
                                    and np.isfinite(producing_outlet_z).all()):
        raise ValueError("accepted producing cells must carry a finite owner outlet")

    # Group producing cells by their domain identity: the outlet world coordinate.
    domains = {}
    for position in range(producing_flat.size):
        flat_terminal = int(producing_terminals[position])
        key = (float(producing_outlet_x[position]), float(producing_outlet_z[position]))
        record = domains.get(key)
        if record is None:
            record = domains[key] = {
                "terminal": flat_terminal,
                "positions": [],
                "marine": bool(ocean_terminal.reshape(-1)[flat_terminal]),
            }
        elif record["terminal"] != flat_terminal:
            raise ValueError("one outlet coordinate carries two terminals: "
                             "%r vs %r" % (record["terminal"], flat_terminal))
        record["positions"].append(position)

    keys = sorted(domains)
    count = len(keys)
    outlet_x = np.empty(count, np.float64)
    outlet_z = np.empty(count, np.float64)
    kind = np.empty(count, dtype=object)
    cell_count = np.empty(count, np.int64)
    area_m2 = np.empty(count, np.float64)
    rain_input_m3 = np.empty(count, np.float64)
    actual_et_m3 = np.empty(count, np.float64)
    soil_storage_change_m3 = np.empty(count, np.float64)
    terminal_release_m3 = np.empty(count, np.float64)
    domain_residual_m3 = np.empty(count, np.float64)
    cell_offsets = np.zeros(count + 1, np.int64)
    cells_x = []
    cells_z = []

    producing_flat_row, producing_flat_column = np.divmod(producing_flat, columns)
    producing_world_x = topology["origin_x_m"] + producing_flat_column * spacing
    producing_world_z = topology["origin_z_m"] + producing_flat_row * spacing

    for index, key in enumerate(keys):
        record = domains[key]
        positions = np.asarray(record["positions"], np.int64)
        outlet_x[index] = key[0]
        outlet_z[index] = key[1]
        kind[index] = "marine" if record["marine"] else "inland"
        cell_count[index] = positions.size
        area_m2[index] = positions.size * cell_area_m2
        rain_input_m3[index] = float(np.sum(
            np.sum(depth_per_interval_m, axis=0)[producing_flat_row[positions] - margin,
                                                 producing_flat_column[positions] - margin],
            dtype=np.float64) * cell_area_m2)
        actual_et_m3[index] = float(np.sum(et_per_cell_m3[positions], dtype=np.float64))
        soil_storage_change_m3[index] = float(np.sum(storage_per_cell_m3[positions], dtype=np.float64))
        terminal_release_m3[index] = float(np.sum(released_per_cell_m3[positions], dtype=np.float64))
        domain_residual_m3[index] = float(
            rain_input_m3[index] - actual_et_m3[index]
            - soil_storage_change_m3[index] - terminal_release_m3[index])
        cell_offsets[index + 1] = cell_offsets[index] + positions.size
        cells_x.append(producing_world_x[positions])
        cells_z.append(producing_world_z[positions])

    cells_x_m = (np.concatenate(cells_x) if cells_x else np.zeros(0, np.float64))
    cells_z_m = (np.concatenate(cells_z) if cells_z else np.zeros(0, np.float64))

    # Tile-level accounting: every requested cubic metre lands in exactly one bin.
    exported_m3 = float(np.sum(terminal_release_m3[kind == "marine"], dtype=np.float64))
    retained_m3 = float(np.sum(terminal_release_m3[kind == "inland"], dtype=np.float64))
    released_total_m3 = float(np.sum(released_per_cell_m3, dtype=np.float64))
    routing_residual_m3 = float(
        np.sum(landed, dtype=np.float64)
        - np.sum(released_per_cell_m3, dtype=np.float64))
    accounting_residual_m3 = float(
        requested_rain_m3 - routed_rain_m3 - unresolved_rain_m3
        - ocean_direct_rain_m3 - outside_core_rain_m3)

    config_id = _config_id(config)
    arrays = {
        "outlet_x_m": outlet_x,
        "outlet_z_m": outlet_z,
        "kind": kind.astype("<U8"),
        "cell_count": cell_count,
        "area_m2": area_m2,
        "rain_input_m3": rain_input_m3,
        "actual_et_m3": actual_et_m3,
        "soil_storage_change_m3": soil_storage_change_m3,
        "terminal_release_m3": terminal_release_m3,
        "domain_residual_m3": domain_residual_m3,
        "cells_x_m": cells_x_m,
        "cells_z_m": cells_z_m,
        "cell_offsets": cell_offsets,
        "limitations": np.asarray(LIMITATIONS, "<U" + str(max(len(text) for text in LIMITATIONS))),
    }
    metadata = {
        "algorithm": ALGORITHM,
        "schema": FLOW_SCHEMA,
        "seed": int(seed),
        "config_id": config_id,
        "spacing_m": spacing,
        "dt_s": dt_s,
        "interval_count": int(intervals),
        "cell_area_m2": cell_area_m2,
        "core_cells": core_cells,
        "tile_shape": [int(rows), int(columns)],
        "tile_origin_m_xz": [float(topology["origin_x_m"]), float(topology["origin_z_m"])],
        "parameters": dict(_parameters_record(parameters)),
        "domain_count": int(count),
        "requested_points": len(points),
        "totals": {
            "requested_rain_m3": requested_rain_m3,
            "routed_rain_m3": routed_rain_m3,
            "unresolved_rain_m3": unresolved_rain_m3,
            "ocean_direct_rain_m3": ocean_direct_rain_m3,
            "outside_core_rain_m3": outside_core_rain_m3,
            "actual_et_m3": float(np.sum(actual_et_m3, dtype=np.float64)),
            "soil_storage_change_m3": float(np.sum(soil_storage_change_m3, dtype=np.float64)),
            "released_total_m3": released_total_m3,
            "exported_to_sea_m3": exported_m3,
            "retained_in_basins_m3": retained_m3,
            "bucket_residual_m3": float(np.sum(bucket_residual_per_cell_m3, dtype=np.float64)),
            "routing_residual_m3": routing_residual_m3,
            "accounting_residual_m3": accounting_residual_m3,
        },
        "claims": {
            "hydraulic_ready": False,
            "natural_outlet_verified": False,
            "publishable": False,
        },
    }
    record = {"arrays": arrays, "metadata": metadata}
    record["identity_sha256"] = identity(arrays, metadata)
    validate_domain_flow(record)
    return record


def _parameters_record(parameters):
    from dataclasses import asdict
    return asdict(parameters)


def _config_id(config):
    from terrain_pipeline.surface_rivers.metric_domain_pipeline import config_identity
    return config_identity(config)


def domain_flow_name(outlet_x_m, outlet_z_m):
    """Deterministic product name from the domain identity (the outlet)."""
    return "river-domain-flow-%d-%d-%s-v1.npz" % (
        int(round(float(outlet_x_m))), int(round(float(outlet_z_m))), FLOW_SCHEMA)


def validate_domain_flow(record):
    """Cold validation: shapes, closure, and the reported totals must agree.

    Raises ValueError on any breach. Deliberately recomputes from the arrays in
    front of it, so a forged `totals` block is caught instead of trusted.
    """
    if not isinstance(record, dict) or set(record) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("domain flow bundle must be {arrays, metadata, identity_sha256}")
    arrays = record["arrays"]
    metadata = record["metadata"]
    expected_arrays = set(PRODUCT_KEYS)
    if set(arrays) != expected_arrays:
        raise ValueError("flow arrays must be exactly the contract keys; "
                         "missing %s, unexpected %s"
                         % (sorted(expected_arrays - set(arrays)),
                            sorted(set(arrays) - expected_arrays)))
    if metadata.get("schema") != FLOW_SCHEMA:
        raise ValueError("flow schema mismatch")
    for key in ("seed", "config_id", "spacing_m", "dt_s", "interval_count", "domain_count"):
        if key not in metadata:
            raise ValueError("metadata.%s is required" % key)
    if not isinstance(metadata["config_id"], str) or len(metadata["config_id"]) != 64:
        raise ValueError("metadata.config_id must be a sha256 hex digest")
    if not isinstance(metadata["interval_count"], int) or isinstance(metadata["interval_count"], bool):
        raise ValueError("metadata.interval_count must be an integer")
    if not 1 <= metadata["interval_count"] <= MAX_INTERVALS:
        raise ValueError("metadata.interval_count must be 1..%d" % MAX_INTERVALS)
    if not isinstance(metadata["dt_s"], (int, float)) or isinstance(metadata["dt_s"], (bool, np.bool_)) \
            or not math.isfinite(float(metadata["dt_s"])) or float(metadata["dt_s"]) <= 0:
        raise ValueError("metadata.dt_s must be finite and positive")
    if identity(arrays, metadata) != record["identity_sha256"]:
        raise ValueError("flow identity mismatch")

    count = int(metadata["domain_count"])
    outlet_x = arrays["outlet_x_m"]
    outlet_z = arrays["outlet_z_m"]
    if outlet_x.ndim != 1 or outlet_x.shape != (count,) or outlet_z.shape != (count,):
        raise ValueError("outlet arrays must be 1-D of length domain_count")
    if count and not np.all(np.isfinite(outlet_x)) or (count and not np.all(np.isfinite(outlet_z))):
        raise ValueError("outlet coordinates must be finite")
    if count > 1:
        keys = np.stack([outlet_x, outlet_z], axis=1)
        if np.unique(keys, axis=0).shape[0] != count:
            raise ValueError("domain identities must be unique outlet coordinates")

    for name in ("cell_count", "area_m2", "rain_input_m3", "actual_et_m3",
                 "soil_storage_change_m3", "terminal_release_m3", "domain_residual_m3"):
        array = np.asarray(arrays[name])
        if array.shape != (count,):
            raise ValueError("%s must be 1-D of length domain_count" % name)
        if not np.isfinite(array).all():
            raise ValueError("%s must be finite" % name)
    kind = np.asarray(arrays["kind"]).astype(str)
    if kind.shape != (count,) or not set(kind.tolist()).issubset({"marine", "inland"}):
        raise ValueError("kind must be one of marine/inland")
    if np.any(np.asarray(arrays["cell_count"]) < 0):
        raise ValueError("cell_count must be nonnegative")

    offsets = np.asarray(arrays["cell_offsets"], np.int64)
    cells_x = np.asarray(arrays["cells_x_m"], np.float64)
    cells_z = np.asarray(arrays["cells_z_m"], np.float64)
    if offsets.shape != (count + 1,) or offsets[0] != 0 or np.any(np.diff(offsets) < 0):
        raise ValueError("cell_offsets must be a nondecreasing D+1 index")
    if cells_x.shape != cells_z.shape or cells_x.shape != (int(offsets[-1]),):
        raise ValueError("cells_x_m/cells_z_m must match the offset total")
    if not (np.isfinite(cells_x).all() and np.isfinite(cells_z).all()):
        raise ValueError("cell coordinates must be finite")
    if int(np.sum(np.asarray(arrays["cell_count"]), dtype=np.int64)) != int(offsets[-1]):
        raise ValueError("cell_count must sum to the offset total")
    if np.any(np.diff(offsets) != np.asarray(arrays["cell_count"])):
        raise ValueError("cell_offsets must follow cell_count exactly")

    spacing = float(metadata["spacing_m"])
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("metadata.spacing_m must be finite and positive")
    area = np.asarray(arrays["area_m2"], np.float64)
    if not np.allclose(area, np.asarray(arrays["cell_count"]) * spacing * spacing,
                       rtol=1e-9, atol=1e-6):
        raise ValueError("area_m2 must equal cell_count * spacing_m**2")

    rain = np.asarray(arrays["rain_input_m3"], np.float64)
    et = np.asarray(arrays["actual_et_m3"], np.float64)
    storage = np.asarray(arrays["soil_storage_change_m3"], np.float64)
    release = np.asarray(arrays["terminal_release_m3"], np.float64)
    residual = np.asarray(arrays["domain_residual_m3"], np.float64)
    if np.any(rain < 0) or np.any(et < 0) or np.any(release < 0):
        raise ValueError("rain/et/release volumes must be nonnegative")
    recomputed = rain - et - storage - release
    scale = np.maximum(np.abs(rain) + np.abs(et) + np.abs(storage) + np.abs(release), 1.0)
    if not np.allclose(residual, recomputed, rtol=1e-9, atol=1e-6):
        raise ValueError("domain_residual_m3 must equal rain - et - storage - release")
    if np.any(np.abs(recomputed) > 1e-6 * scale):
        raise ValueError("domain ledger does not close: max relative residual %.3e"
                         % float(np.max(np.abs(recomputed) / scale)))

    totals = metadata.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("metadata.totals required")
    requested = float(totals["requested_rain_m3"])
    partition = (float(totals["routed_rain_m3"]) + float(totals["unresolved_rain_m3"])
                 + float(totals["ocean_direct_rain_m3"]) + float(totals["outside_core_rain_m3"]))
    if abs(requested - partition) > 1e-6 * max(abs(requested), 1.0):
        raise ValueError("rainfall partition does not sum to the requested total")
    if abs(float(totals["routed_rain_m3"]) - float(np.sum(rain, dtype=np.float64))) \
            > 1e-6 * max(abs(requested), 1.0):
        raise ValueError("routed_rain_m3 must equal the domain rain_input sum")
    exported = float(np.sum(release[kind == "marine"], dtype=np.float64))
    retained = float(np.sum(release[kind == "inland"], dtype=np.float64))
    if abs(exported - float(totals["exported_to_sea_m3"])) > 1e-6 * max(abs(exported), 1.0):
        raise ValueError("exported_to_sea_m3 must equal the marine release sum")
    if abs(retained - float(totals["retained_in_basins_m3"])) > 1e-6 * max(abs(retained), 1.0):
        raise ValueError("retained_in_basins_m3 must equal the inland release sum")
    if abs(float(totals["accounting_residual_m3"])) > 1e-6 * max(abs(requested), 1.0):
        raise ValueError("rainfall accounting residual must be zero")
    if abs(float(totals["routing_residual_m3"])) > 1e-6 * max(abs(float(totals["released_total_m3"])), 1.0):
        raise ValueError("routing must conserve the released volume in a shared terminal")
    claims = metadata.get("claims")
    if not isinstance(claims, dict) or any(claims.get(key) is not False for key in
                                           ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("a domain flow product claims no publishable hydraulics")
    return True


def save_domain_flow(path, record):
    """Persist with the repository's atomic-link discipline; never overwrite."""
    save_bundle(path, record, validator=validate_domain_flow)


def load_domain_flow(path, *, expected_sha256, expected_identity=None):
    """Reload cold, re-deriving the identity; refuse a wrong expected value."""
    record = load_bundle(path, expected_sha256=expected_sha256, validator=validate_domain_flow)
    if expected_identity is not None and record["identity_sha256"] != expected_identity:
        raise ValueError("domain flow identity mismatch against the expected value")
    return record