"""Domain sediment ledger: weathering -> entrainment -> routing -> outlet.

Why this module exists
----------------------
`metric_domain_flow` closes the **water** ledger for one world-anchored tile:
rain in, ET / storage / outlet out. The phase-1 completion condition asks for the
source and fate of BOTH ("水量和泥沙的来源去向可核对"), and the sediment half was
still missing at tile scale.

The repository's sediment machinery is bounded and replay based: `metric_sediment`
solves shear, transport capacity, deposition and bed change **given a supplied
hydraulic state**, and `metric_morphology_coupling` needs a channel geometry plus a
frozen hydraulic identity. Neither is available for a 480 km-scale domain tile
whose products carry geometry and ownership only. What is available is the closure
module's own raw-face D8, which is exactly what a tile-scale delivery accounting
needs.

So this module publishes the **source -> entrain -> route -> deposit -> deliver**
ledger for one tile, with the same discipline as the water ledger: it authors no
second flood and no second steepest-D8 pass (the routing arrays come from
`metric_domain_closure.domain_topology`), and every cubic metre is accounted.

What is certified, and what is not
----------------------------------
Certified: both ledgers close, per domain and tile wide.

* source ledger: `weathered = entrained + store_change` -- what the declared
  weathering produces is either entrained into the flow path or left in the
  mobile store;
* routing ledger: `entrained = deposited + delivered` -- what is entrained settles
  somewhere on its own chain or arrives at its own terminal.

Both ledgers are statements about the **producing cells** (the accepted CORE cells):
that is where the declared weathering is placed and where the mobile store lives.
The tile MARGIN carries no source and no initial inventory, exactly as the water
ledger injects rain on the core only. A margin cell still receives and settles
routed load, and that deposition is attributed to the domain whose terminal the
margin cell drains to -- otherwise the margin's deposition would leak out of the
per-domain ledger and leave a residual.

NOT certified (declared here, not discovered later):

* the yield coefficients are **declared, uncalibrated engineering assumptions**
  (`SedimentYieldParameters`), in the same spirit as `rainfall_runoff`'s
  illustrative soil parameters. This is a **source-and-fate accounting chain, not
  a calibrated erosion model** and not a sediment-transport law;
* entrainment is a declared function of the RAW face's local slope only
  (`clip(slope_gain * slope, 0, 1)` of the available mobile depth). No discharge,
  shear stress, grain size, channel width or material hardness enters, because
  none of them is available at this scale yet;
* deposition is a declared constant fraction of the load passing each accepted
  cell. It is not a settling-velocity law and does not know grain size;
* the ledger **does not modify terrain**: it reports volumes, it does not write a
  bed change, an Exner update or any derived surface. Coupling the delivered load
  back into a bed is a later, separate step with its own identity and regression;
* cells that the closure module refused (`unresolved_border`) and ocean cells
  receive **no source**. Any load that nevertheless strands on a non-accepted,
  non-ocean terminal is reported separately (`stranded_on_refused_m3`) rather than
  silently counted as delivery. By the closure module's own tested property
  (`test_refused_halo_does_not_feed_an_accepted_domain`) that tally is expected to
  be zero; it is measured, not assumed.

Relationship to the water ledger
--------------------------------
The two ledgers are deliberately **independent** in this round: sediment
entrainment does not read the water ledger's release, and the water ledger does
not read sediment. Coupling them (discharge-dependent transport capacity) is a
declared next step, not something this module quietly assumes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.surface_rivers.metric_domain_closure import domain_topology

__all__ = [
    "ALGORITHM",
    "LIMITATIONS",
    "MAX_INTERVALS",
    "PRODUCT_KEYS",
    "SEDIMENT_SCHEMA",
    "SedimentYieldParameters",
    "domain_sediment_name",
    "load_domain_sediment",
    "save_domain_sediment",
    "solve_domain_sediment",
    "validate_domain_sediment",
]

ALGORITHM = "domain-sediment-ledger-v1"
SEDIMENT_SCHEMA = "river-domain-sediment-v1"

# The routing pass is a Python loop over the tile's nodes, repeated once per
# interval (the mobile store's evolution is nonlinear, so the intervals cannot be
# collapsed). At the default tile (225 x 225 = 50 625 nodes) an interval costs a
# few hundred milliseconds, so the cap keeps a run in the tens of seconds.
MAX_INTERVALS = 120

# Contract key set of a published sediment product, in order. All series (1-D) and
# no 0-d scalars, for the same measured reason as `metric_domain_flow`: the shared
# `mountain_source_adapter.readonly` funnels every array through
# `np.ascontiguousarray`, which promotes a 0-d array to shape `(1,)` and would make
# a reload differ from the in-memory bundle. Scalars live in `metadata` instead.
PRODUCT_KEYS = (
    "outlet_x_m",
    "outlet_z_m",
    "kind",
    "cell_count",
    "area_m2",
    "weathered_m3",
    "entrained_m3",
    "deposited_m3",
    "delivered_m3",
    "store_change_m3",
    "source_residual_m3",
    "routing_residual_m3",
    "cells_x_m",
    "cells_z_m",
    "cell_offsets",
    "limitations",
)

LIMITATIONS = (
    "yield coefficients are declared, uncalibrated engineering assumptions; this is "
    "a source-and-fate accounting chain, not a calibrated erosion or transport law",
    "entrainment depends on the RAW face's local slope only; no discharge, shear, "
    "grain size, channel width or material hardness enters at this scale",
    "deposition is a declared constant fraction of the load passing each accepted "
    "cell; it is not a settling-velocity law",
    "the ledger reports volumes only: it writes no bed change, no Exner update and "
    "no derived surface, and it does not modify the immutable base face",
    "sediment and water ledgers are independent here: entrainment does not read "
    "discharge, and discharge does not read sediment; coupling is a later step",
    "cells are the accepted LAND cells of the owning tile's CORE; a domain that "
    "continues past the core publishes only its core part",
    "load stranded on a non-accepted, non-ocean terminal is reported separately "
    "rather than counted as delivery; it is expected to be zero, and is measured",
    "the mobile store exists on the accepted CORE cells only: the tile margin "
    "carries no source and no initial inventory, mirroring the water ledger's "
    "core-only rainfall injection; a margin cell still settles routed load and "
    "that deposition is attributed to the domain its chain drains to",
)


@dataclass(frozen=True)
class SedimentYieldParameters:
    """Declared, uncalibrated yield coefficients (see the module docstring).

    Sources for these numbers: **none**. They are engineering assumptions chosen so
    that a 100 km2 tile node yields a plausible order of magnitude, in the same
    declared-assumption spirit as `rainfall_runoff.RunoffParameters`. A future
    material or climate field must replace them through the documented injection
    point (`source_m_per_interval`) rather than by quietly editing them.
    """

    weathered_m_per_interval: float = 0.0002
    slope_gain: float = 150.0
    deposit_fraction: float = 0.3
    initial_mobile_m: float = 0.0

    def __post_init__(self):
        for name in ("weathered_m_per_interval", "slope_gain", "initial_mobile_m"):
            value = getattr(self, name)
            if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0.0):
                raise ValueError("%s must be finite and nonnegative" % name)
        fraction = self.deposit_fraction
        if (isinstance(fraction, (bool, np.bool_)) or not isinstance(fraction, (int, float))
                or not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0):
            raise ValueError("deposit_fraction must be finite and within [0, 1]")


def _source_grid(source_m_per_interval, default_depth, core_cells):
    """Declared weathering depth per interval [m] on the core node lattice.

    `source_m_per_interval` is an injection point for a future material or climate
    field. Accepted forms: `None` (use the parameter default uniformly), a scalar,
    or a `(core+1, core+1)` grid. Anything else is an input error, never silently
    broadcast -- a mis-shaped source field would quietly move the whole sediment
    budget.
    """
    shape = (core_cells + 1, core_cells + 1)
    if source_m_per_interval is None:
        return np.full(shape, float(default_depth), np.float64)
    if isinstance(source_m_per_interval, (bool, np.bool_)):
        raise ValueError("source_m_per_interval must be a number or grid, not a bool")
    if np.ndim(source_m_per_interval) == 0:
        value = float(source_m_per_interval)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("source_m_per_interval must be finite and nonnegative")
        return np.full(shape, value, np.float64)
    grid = np.asarray(source_m_per_interval, np.float64)
    if grid.shape != shape:
        raise ValueError("source_m_per_interval grid must have shape %s; got %s"
                         % (shape, grid.shape))
    if not np.isfinite(grid).all() or np.any(grid < 0.0):
        raise ValueError("source_m_per_interval grid must be finite and nonnegative")
    return grid


def _config_id(config):
    from terrain_pipeline.surface_rivers.metric_domain_pipeline import config_identity
    return config_identity(config)


def domain_sediment_name(outlet_x_m, outlet_z_m):
    """Deterministic product name from the domain identity (the outlet)."""
    return "river-domain-sediment-%d-%d-%s-v1.npz" % (
        int(round(float(outlet_x_m))), int(round(float(outlet_z_m))), SEDIMENT_SCHEMA)


def solve_domain_sediment(seed, points_xz_m, *, config=None, parameters=None,
                          source_m_per_interval=None, intervals=12):
    """Weathering -> entrainment -> routing -> deposition -> delivery, one tile.

    `points_xz_m` selects the world-anchored tile; every point must share it, and a
    point in another tile is an input error (never a silent second tile).
    `intervals` is the number of physical intervals of the declared weathering and
    entrainment step. Returns a bundle: `arrays`, `metadata`, `identity_sha256` --
    exactly what `save_domain_sediment` writes and `load_domain_sediment` checks.
    """
    config = config or PlanningConfig()
    config.validate()
    parameters = parameters or SedimentYieldParameters()
    if not isinstance(parameters, SedimentYieldParameters):
        raise ValueError("SedimentYieldParameters required")
    if not isinstance(intervals, int) or isinstance(intervals, bool):
        raise ValueError("intervals must be an integer")
    if not 1 <= intervals <= MAX_INTERVALS:
        raise ValueError("intervals must be 1..%d" % MAX_INTERVALS)

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
    height = topology["height_m"]
    receiver = topology["receiver"]
    terminal = topology["terminal"]
    accepted = topology["accepted"]
    ocean = topology["ocean"]
    ocean_terminal = topology["ocean_terminal"].reshape(-1)
    unresolved = topology["unresolved"]
    owner_x = topology["owner_outlet_x_m"]
    owner_z = topology["owner_outlet_z_m"]

    core_slice = np.s_[margin:margin + core_cells + 1, margin:margin + core_cells + 1]
    core_accepted = accepted[core_slice]
    core_ocean = ocean[core_slice]
    core_unresolved = unresolved[core_slice]
    if np.any(core_accepted & (core_ocean | core_unresolved)):
        raise ValueError("accepted cells cannot be ocean or unresolved (contract 3)")

    source_grid = _source_grid(source_m_per_interval,
                               parameters.weathered_m_per_interval, core_cells)

    # Local slope on the RAW face, central differences on the node lattice. This is
    # the only terrain signal entrainment uses, so it is computed here rather than
    # taken from a derived surface that could drift from the routing face.
    dh_dz, dh_dx = np.gradient(height, spacing, spacing)
    slope = np.hypot(dh_dx, dh_dz)

    flat_size = rows * columns
    height_flat = height.reshape(-1)
    flat_receiver = np.asarray(receiver, np.int64).reshape(-1)
    flat_terminal = np.asarray(terminal, np.int64).reshape(-1)
    accepted_flat = accepted.reshape(-1)
    slope_flat = slope.reshape(-1)
    entrain_fraction = np.clip(parameters.slope_gain * slope_flat, 0.0, 1.0)

    # A strictly-downhill receiver makes descending height a valid topological
    # order: every cell that drains into a node is strictly higher, so it is
    # processed before that node. Computed once and reused by every interval.
    upstream_first = np.argsort(-height_flat, kind="stable")

    producing_rows, producing_columns = np.nonzero(core_accepted)
    producing_flat = (producing_rows + margin) * columns + (producing_columns + margin)

    source_tile = np.zeros(flat_size, np.float64)
    source_tile[producing_flat] = source_grid[producing_rows, producing_columns]

    # The mobile store lives ONLY on the producing cells. Initialising it tile-wide
    # leaked volume: a cell outside the core (or a margin cell) entrained its
    # initial inventory and routed it to a terminal, while neither `entrained` nor
    # `store_change` is summed there -- so the tile ledger opened by exactly that
    # amount. Measured with `initial_mobile_m = 0.05` before the fix: the tile
    # routing residual was 1.38e10 m3 and the per-domain entrainment sums fell
    # 9.45e10 m3 short of the tile total. The fix is structural, not a tolerance.
    producing_mask = np.zeros(flat_size, bool)
    producing_mask[producing_flat] = True

    initial_mobile = float(parameters.initial_mobile_m)
    store = np.zeros(flat_size, np.float64)
    store[producing_flat] = initial_mobile
    weathered_flat = np.zeros(flat_size, np.float64)
    entrained_flat = np.zeros(flat_size, np.float64)
    deposited_flat = np.zeros(flat_size, np.float64)
    delivered_flat = np.zeros(flat_size, np.float64)

    for _ in range(intervals):
        # Zero off the producing cells by construction, so nothing outside them can
        # be entrained (and therefore routed) into the ledger.
        available = np.where(producing_mask, store + source_tile, 0.0)
        take = entrain_fraction * available
        store = available - take
        weathered_flat += source_tile * cell_area_m2
        load = take * cell_area_m2
        entrained_flat += load
        for cell in upstream_first:
            value = load[cell]
            if value <= 0.0:
                continue
            if accepted_flat[cell]:
                settle = parameters.deposit_fraction * value
                if settle > 0.0:
                    deposited_flat[cell] += settle
                    value -= settle
                    load[cell] = value
            target = flat_receiver[cell]
            if target >= 0:
                load[target] += value
                load[cell] = 0.0
        # After the walk, volume still in `load` sits only on terminal cells
        # (receiver == -1); it is this interval's delivered load.
        delivered_flat += load

    # `store` is a mobile DEPTH in metres; the ledger is in cubic metres, so the
    # store change must be multiplied by the cell area before it can sit next to
    # `weathered` and `entrained` -- the same mm-vs-m factor the water ledger keeps
    # explicit at its own partition. Getting this wrong would leave a residual of
    # exactly (cell_area - 1) times the store change.
    store_change_flat = np.where(producing_mask, store - initial_mobile, 0.0) * cell_area_m2

    # Group producing cells by their domain identity: the outlet world coordinate,
    # which the closure contract defines as the TERMINAL's world coordinate.
    producing_outlet_x = owner_x.reshape(-1)[producing_flat]
    producing_outlet_z = owner_z.reshape(-1)[producing_flat]
    producing_terminal = flat_terminal[producing_flat]
    if producing_flat.size and not (np.isfinite(producing_outlet_x).all()
                                    and np.isfinite(producing_outlet_z).all()):
        raise ValueError("accepted producing cells must carry a finite owner outlet")

    domains = {}
    for position in range(producing_flat.size):
        flat_term = int(producing_terminal[position])
        key = (float(producing_outlet_x[position]), float(producing_outlet_z[position]))
        record = domains.get(key)
        if record is None:
            record = domains[key] = {
                "terminal": flat_term,
                "positions": [],
                "marine": bool(ocean_terminal[flat_term]),
            }
        elif record["terminal"] != flat_term:
            raise ValueError("one outlet coordinate carries two terminals: %r vs %r"
                             % (record["terminal"], flat_term))
        record["positions"].append(position)

    keys = sorted(domains)
    count = len(keys)
    outlet_x = np.empty(count, np.float64)
    outlet_z = np.empty(count, np.float64)
    kind = np.empty(count, dtype=object)
    cell_count = np.empty(count, np.int64)
    area_m2 = np.empty(count, np.float64)
    weathered_m3 = np.empty(count, np.float64)
    entrained_m3 = np.empty(count, np.float64)
    deposited_m3 = np.empty(count, np.float64)
    delivered_m3 = np.empty(count, np.float64)
    store_change_m3 = np.empty(count, np.float64)
    source_residual_m3 = np.empty(count, np.float64)
    routing_residual_m3 = np.empty(count, np.float64)
    cell_offsets = np.zeros(count + 1, np.int64)
    domain_terminals = np.empty(count, np.int64)
    cells_x = []
    cells_z = []

    producing_row, producing_column = np.divmod(producing_flat, columns)
    producing_world_x = topology["origin_x_m"] + producing_column * spacing
    producing_world_z = topology["origin_z_m"] + producing_row * spacing

    for index, key in enumerate(keys):
        record = domains[key]
        positions = np.asarray(record["positions"], np.int64)
        outlet_x[index] = key[0]
        outlet_z[index] = key[1]
        kind[index] = "marine" if record["marine"] else "inland"
        cell_count[index] = positions.size
        area_m2[index] = positions.size * cell_area_m2
        domain_terminals[index] = record["terminal"]
        weathered_m3[index] = float(np.sum(weathered_flat[producing_flat[positions]],
                                           dtype=np.float64))
        entrained_m3[index] = float(np.sum(entrained_flat[producing_flat[positions]],
                                           dtype=np.float64))
        # Deposition happens on EVERY accepted cell along the chain, including the
        # tile's margin, so it is attributed by the domain's TERMINAL rather than by
        # the domain's own core cells: summing over core cells alone would leak the
        # margin's deposition out of the ledger and leave a residual.
        deposited_m3[index] = float(np.sum(
            deposited_flat[accepted_flat & (flat_terminal == record["terminal"])],
            dtype=np.float64))
        store_change_m3[index] = float(np.sum(store_change_flat[producing_flat[positions]],
                                              dtype=np.float64))
        delivered_m3[index] = float(delivered_flat[record["terminal"]])
        # Both ledgers must close per domain, not only tile wide.
        source_residual_m3[index] = (weathered_m3[index] - entrained_m3[index]
                                     - store_change_m3[index])
        routing_residual_m3[index] = (entrained_m3[index] - deposited_m3[index]
                                      - delivered_m3[index])
        cell_offsets[index + 1] = cell_offsets[index] + positions.size
        cells_x.append(producing_world_x[positions])
        cells_z.append(producing_world_z[positions])

    cells_x_m = (np.concatenate(cells_x) if cells_x else np.zeros(0, np.float64))
    cells_z_m = (np.concatenate(cells_z) if cells_z else np.zeros(0, np.float64))

    # Any delivered volume on a terminal that no domain claims can only be a
    # non-accepted, non-ocean local minimum. It is reported, never absorbed.
    matched = np.zeros(flat_size, bool)
    if count:
        matched[domain_terminals] = True
    # Keep what sits on a terminal that NO domain claims. The first draft kept the
    # complement instead (`unclaimed[~matched] = 0.0`), which reported the whole
    # delivered volume as stranded and drove the tile routing residual to exactly
    # `-delivered_total_m3`.
    unclaimed = delivered_flat.copy()
    unclaimed[matched] = 0.0
    stranded_on_refused_m3 = float(np.sum(unclaimed, dtype=np.float64))

    weathered_total = float(np.sum(weathered_flat, dtype=np.float64))
    entrained_total = float(np.sum(entrained_flat, dtype=np.float64))
    deposited_total = float(np.sum(deposited_flat, dtype=np.float64))
    delivered_total = float(np.sum(delivered_m3, dtype=np.float64))
    store_change_total = float(np.sum(store_change_flat, dtype=np.float64))
    accepted_slope = slope_flat[producing_flat] if producing_flat.size else np.zeros(0)

    config_id = _config_id(config)
    arrays = {
        "outlet_x_m": outlet_x,
        "outlet_z_m": outlet_z,
        "kind": kind.astype("<U8"),
        "cell_count": cell_count,
        "area_m2": area_m2,
        "weathered_m3": weathered_m3,
        "entrained_m3": entrained_m3,
        "deposited_m3": deposited_m3,
        "delivered_m3": delivered_m3,
        "store_change_m3": store_change_m3,
        "source_residual_m3": source_residual_m3,
        "routing_residual_m3": routing_residual_m3,
        "cells_x_m": cells_x_m,
        "cells_z_m": cells_z_m,
        "cell_offsets": cell_offsets,
        "limitations": np.asarray(LIMITATIONS, "<U" + str(max(len(t) for t in LIMITATIONS))),
    }
    metadata = {
        "algorithm": ALGORITHM,
        "schema": SEDIMENT_SCHEMA,
        "seed": int(seed),
        "config_id": config_id,
        "spacing_m": spacing,
        "interval_count": int(intervals),
        "cell_area_m2": cell_area_m2,
        "core_cells": core_cells,
        "tile_shape": [int(rows), int(columns)],
        "tile_origin_m_xz": [float(topology["origin_x_m"]), float(topology["origin_z_m"])],
        "parameters": dict(asdict(parameters)),
        "domain_count": int(count),
        "requested_points": len(points),
        "totals": {
            "weathered_total_m3": weathered_total,
            "entrained_total_m3": entrained_total,
            "deposited_total_m3": deposited_total,
            "delivered_total_m3": delivered_total,
            "store_change_total_m3": store_change_total,
            "delivered_to_sea_m3": float(np.sum(delivered_m3[kind == "marine"], dtype=np.float64)),
            "delivered_to_basins_m3": float(np.sum(delivered_m3[kind == "inland"], dtype=np.float64)),
            "stranded_on_refused_m3": stranded_on_refused_m3,
            "source_residual_m3": float(weathered_total - entrained_total - store_change_total),
            "routing_residual_m3": float(entrained_total - deposited_total
                                         - delivered_total - stranded_on_refused_m3),
            "accepted_cells": int(producing_flat.size),
            "initial_mobile_total_m3": float(initial_mobile * producing_flat.size
                                             * cell_area_m2),
            "entrainment_saturated_fraction": (
                float(np.mean(entrain_fraction[producing_flat] >= 1.0))
                if producing_flat.size else 0.0),
            "excluded_ocean_core_cells": int(np.count_nonzero(core_ocean & ~core_unresolved)),
            "excluded_unresolved_core_cells": int(np.count_nonzero(core_unresolved)),
            "mean_slope_m_per_m": (float(np.mean(accepted_slope)) if accepted_slope.size else 0.0),
            "max_slope_m_per_m": (float(np.max(accepted_slope)) if accepted_slope.size else 0.0),
        },
        "claims": {
            "hydraulic_ready": False,
            "natural_outlet_verified": False,
            "publishable": False,
            "terrain_feedback_applied": False,
        },
    }
    record = {"arrays": arrays, "metadata": metadata}
    record["identity_sha256"] = identity(arrays, metadata)
    validate_domain_sediment(record)
    return record


def validate_domain_sediment(record):
    """Cold validation: shapes, both closures, and the reported totals.

    Recomputes from the arrays in front of it, so a forged `totals` block is caught
    rather than trusted. Raises ValueError on any breach.
    """
    if not isinstance(record, dict) or set(record) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("domain sediment bundle must be {arrays, metadata, identity_sha256}")
    arrays = record["arrays"]
    metadata = record["metadata"]
    expected = set(PRODUCT_KEYS)
    if set(arrays) != expected:
        raise ValueError("sediment arrays must be exactly the contract keys; "
                         "missing %s, unexpected %s"
                         % (sorted(expected - set(arrays)), sorted(set(arrays) - expected)))
    if metadata.get("schema") != SEDIMENT_SCHEMA:
        raise ValueError("sediment schema mismatch")
    for key in ("seed", "config_id", "spacing_m", "interval_count", "domain_count",
                "cell_area_m2"):
        if key not in metadata:
            raise ValueError("metadata.%s is required" % key)
    if not isinstance(metadata["config_id"], str) or len(metadata["config_id"]) != 64:
        raise ValueError("metadata.config_id must be a sha256 hex digest")
    if not isinstance(metadata["interval_count"], int) or isinstance(metadata["interval_count"], bool):
        raise ValueError("metadata.interval_count must be an integer")
    if not 1 <= metadata["interval_count"] <= MAX_INTERVALS:
        raise ValueError("metadata.interval_count must be 1..%d" % MAX_INTERVALS)
    if identity(arrays, metadata) != record["identity_sha256"]:
        raise ValueError("sediment identity mismatch")

    count = int(metadata["domain_count"])
    outlet_x = np.asarray(arrays["outlet_x_m"], np.float64)
    outlet_z = np.asarray(arrays["outlet_z_m"], np.float64)
    if outlet_x.shape != (count,) or outlet_z.shape != (count,):
        raise ValueError("outlet arrays must be 1-D of length domain_count")
    if count:
        if not np.isfinite(outlet_x).all() or not np.isfinite(outlet_z).all():
            raise ValueError("outlet coordinates must be finite")
        if count > 1 and np.unique(np.stack([outlet_x, outlet_z], axis=1), axis=0).shape[0] != count:
            raise ValueError("domain identities must be unique outlet coordinates")

    for name in ("cell_count", "area_m2", "weathered_m3", "entrained_m3",
                 "deposited_m3", "delivered_m3", "store_change_m3",
                 "source_residual_m3", "routing_residual_m3"):
        array = np.asarray(arrays[name])
        if array.shape != (count,) or not np.isfinite(array).all():
            raise ValueError("%s must be finite and 1-D of length domain_count" % name)
    kind = np.asarray(arrays["kind"]).astype(str)
    if kind.shape != (count,) or not set(kind.tolist()).issubset({"marine", "inland"}):
        raise ValueError("kind must be one of marine/inland")

    cell_count = np.asarray(arrays["cell_count"], np.int64)
    if np.any(cell_count < 0):
        raise ValueError("cell_count must be nonnegative")
    offsets = np.asarray(arrays["cell_offsets"], np.int64)
    cells_x = np.asarray(arrays["cells_x_m"], np.float64)
    cells_z = np.asarray(arrays["cells_z_m"], np.float64)
    if offsets.shape != (count + 1,) or offsets[0] != 0 or np.any(np.diff(offsets) < 0):
        raise ValueError("cell_offsets must be a nondecreasing D+1 index")
    if int(offsets[-1]) != cells_x.size or cells_z.size != cells_x.size:
        raise ValueError("cells_x_m/cells_z_m must match the offset total")
    if not (np.isfinite(cells_x).all() and np.isfinite(cells_z).all()):
        raise ValueError("cell coordinates must be finite")
    if int(np.sum(cell_count, dtype=np.int64)) != int(offsets[-1]):
        raise ValueError("cell_count must sum to the offset total")
    if np.any(np.diff(offsets) != cell_count):
        raise ValueError("cell_offsets must follow cell_count exactly")

    spacing = float(metadata["spacing_m"])
    if not math.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("metadata.spacing_m must be finite and positive")
    area = np.asarray(arrays["area_m2"], np.float64)
    if not np.allclose(area, cell_count * spacing * spacing, rtol=1e-9, atol=1e-6):
        raise ValueError("area_m2 must equal cell_count * spacing_m**2")

    weathered = np.asarray(arrays["weathered_m3"], np.float64)
    entrained = np.asarray(arrays["entrained_m3"], np.float64)
    deposited = np.asarray(arrays["deposited_m3"], np.float64)
    delivered = np.asarray(arrays["delivered_m3"], np.float64)
    store_change = np.asarray(arrays["store_change_m3"], np.float64)
    if np.any(weathered < 0) or np.any(entrained < 0) or np.any(deposited < 0) or np.any(delivered < 0):
        raise ValueError("sediment volumes must be nonnegative")

    scale_source = np.maximum(weathered + entrained + np.abs(store_change), 1.0)
    recomputed_source = weathered - entrained - store_change
    if np.any(np.abs(recomputed_source) > 1e-6 * scale_source):
        raise ValueError("per-domain source ledger does not close: worst relative residual %.3e"
                         % float(np.max(np.abs(recomputed_source) / scale_source)))
    if not np.allclose(np.asarray(arrays["source_residual_m3"], np.float64),
                       recomputed_source, rtol=1e-9, atol=1e-6):
        raise ValueError("source_residual_m3 must equal weathered - entrained - store_change")

    scale_routing = np.maximum(entrained + deposited + delivered, 1.0)
    recomputed_routing = entrained - deposited - delivered
    if np.any(np.abs(recomputed_routing) > 1e-6 * scale_routing):
        raise ValueError("per-domain routing ledger does not close: worst relative residual %.3e"
                         % float(np.max(np.abs(recomputed_routing) / scale_routing)))
    if not np.allclose(np.asarray(arrays["routing_residual_m3"], np.float64),
                       recomputed_routing, rtol=1e-9, atol=1e-6):
        raise ValueError("routing_residual_m3 must equal entrained - deposited - delivered")

    totals = metadata.get("totals")
    if not isinstance(totals, dict):
        raise ValueError("metadata.totals required")
    for name in ("weathered_total_m3", "entrained_total_m3", "deposited_total_m3",
                 "delivered_total_m3", "store_change_total_m3", "source_residual_m3",
                 "routing_residual_m3", "delivered_to_sea_m3", "delivered_to_basins_m3",
                 "stranded_on_refused_m3"):
        if name not in totals or not math.isfinite(float(totals[name])):
            raise ValueError("metadata.totals.%s must be a finite number" % name)
    tolerance = 1e-6 * max(float(totals["weathered_total_m3"]), 1.0)
    if abs(float(totals["weathered_total_m3"]) - float(np.sum(weathered))) > tolerance:
        raise ValueError("weathered_total_m3 must equal the domain weathered sum")
    if abs(float(totals["entrained_total_m3"]) - float(np.sum(entrained))) > tolerance:
        raise ValueError("entrained_total_m3 must equal the domain entrained sum")
    if abs(float(totals["deposited_total_m3"]) - float(np.sum(deposited))) > tolerance:
        raise ValueError("deposited_total_m3 must equal the domain deposited sum")
    if abs(float(totals["delivered_total_m3"]) - float(np.sum(delivered))) > tolerance:
        raise ValueError("delivered_total_m3 must equal the domain delivered sum")
    if abs(float(totals["source_residual_m3"])) > tolerance:
        raise ValueError("tile source ledger residual must be zero")
    if abs(float(totals["routing_residual_m3"])) > tolerance:
        raise ValueError("tile routing ledger residual must be zero")
    sea = float(np.sum(delivered[kind == "marine"], dtype=np.float64))
    basins = float(np.sum(delivered[kind == "inland"], dtype=np.float64))
    if abs(float(totals["delivered_to_sea_m3"]) - sea) > tolerance:
        raise ValueError("delivered_to_sea_m3 must equal the marine delivered sum")
    if abs(float(totals["delivered_to_basins_m3"]) - basins) > tolerance:
        raise ValueError("delivered_to_basins_m3 must equal the inland delivered sum")
    if float(totals["stranded_on_refused_m3"]) < -tolerance:
        raise ValueError("stranded_on_refused_m3 must be nonnegative")
    claims = metadata.get("claims")
    if not isinstance(claims, dict) or any(claims.get(key) is not False for key in
                                          ("hydraulic_ready", "natural_outlet_verified",
                                           "publishable", "terrain_feedback_applied")):
        raise ValueError("a domain sediment product claims no publishable hydraulics "
                         "and no applied terrain feedback")
    return True


def save_domain_sediment(path, record):
    """Persist with the repository's atomic-link discipline; never overwrite."""
    save_bundle(path, record, validator=validate_domain_sediment)


def load_domain_sediment(path, *, expected_sha256, expected_identity=None):
    """Reload cold, re-deriving the identity; refuse a wrong expected value."""
    record = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_domain_sediment)
    if expected_identity is not None and record["identity_sha256"] != expected_identity:
        raise ValueError("domain sediment identity mismatch against the expected value")
    return record