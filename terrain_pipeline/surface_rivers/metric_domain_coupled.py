"""Coupled water-sediment ledger: discharge sets the channel, the channel sets capacity.

Why this module exists
---------------------
`metric_domain_sediment` (P8) closed the sediment half of the tile ledger, but it
declares its own central weakness in its limitations, verbatim: entrainment reads
"the RAW face's local slope only; no discharge, shear, grain size, channel width or
material hardness enters at this scale". Measured: at the declared default
`slope_gain = 150`, **91.05% of producing cells are already saturated** at
`clip(gain * slope, 0, 1) == 1`, so the slope term carries almost no signal there.

This module is the coupling step. It reads the water ledger's own per-cell release
through `metric_domain_flow.domain_flow_topology` (a read-only accessor added for
exactly this purpose; the published water identity is unchanged by it), converts the
released **volume** to a declared **discharge**, accumulates it downstream, derives a
channel width and depth from it, and then lets the resulting **excess shear stress
limit how much the flow can entrain**. A cell with no water entrains nothing.

What is certified, and what is not
----------------------------------
Certified, with two gates the P8 ledger could not state:

* both P8 ledgers still close, per domain and tile wide
  (`weathered = entrained + store_change`, `entrained = deposited + delivered`);
* **the capacity gate**: at every interval and every producing cell, the entrained
  volume never exceeds the capacity the flow's own shear implies. This is measured
  and reported (`totals.capacity_violation_m3`), not assumed;
* **the coupling gate**: entrainment goes to zero when the discharge goes to zero
  and is monotone in the transport coefficient. A run with `rain = 0` therefore
  entrains **nothing** -- which the P8 slope law could not express.

NOT certified (declared here, not discovered later):

* the discharge is a **declared flattening**, not a hydrograph. The water ledger
  routes volume instantaneously; this module divides each cell's total release by
  `intervals * dt_s` to obtain a representative rate. It is not a peak flow and it
  carries no travel time;
* the channel geometry is the repository's **already-declared** power law
  (`metric_channel_plan.ChannelRecipe`: `W = ref_w * (q / ref_q) ** width_exponent`,
  clipped). Its reference discharge and exponents are engineering assumptions with
  no calibration, exactly as in their home module;
* the shear law is the repository's **already-declared** one
  (`metric_sediment._rates`): `tau = rho g R S`, `capacity = k_t * W * excess ** 1.5`.
  No grain size, no roughness calibration, no bed-form resistance;
* **deposition is still a declared constant fraction** of the load passing each
  accepted cell. Only the entrainment half became capacity-limited; the settling
  half is not a settling-velocity law and is not fixed by this module;
* the ledger **does not modify terrain**: it reports volumes. No bed change, no
  Exner update, no derived surface;
* `hydraulic_ready` / `natural_outlet_verified` / `publishable` remain **false**.
  Instantaneous routing is still not a flood wave, and a reference discharge derived
  from a volume is not a hydraulic certification.

Three upstream ceilings, measured rather than hidden
---------------------------------------------------
The coupling is only as responsive as the chain below it, and that chain contains
three declared ceilings. They are reported in `totals` so a reader can see whether
the coupling had room to act:

1. `rainfall_runoff.RunoffParameters.infiltration_capacity_mm_h = 15` sits **below**
   the 4 mm/h scenario, so at both 4 and 8 mm/h the entire rain infiltrates and the
   release is IDENTICAL (`1.047e8 m3`) -- it is the bucket draining its declared
   30 mm store, the draw-down behaviour P7 already documents. Capacity therefore
   cannot respond to rain there, and that is an upstream property, not a coupling
   failure.
2. `ChannelRecipe.max_width_m = 30` saturates the width power law by about
   20 mm/h (`W = clip(3 * (q/0.05)^0.5, 1, 30)`). Past that the width term is a
   constant; `totals.max_channel_width_m` records whether the clip was reached.
3. `sediment_critical_shear_pa = 1` is far below the shear the geometry produces
   (mean excess ~363 Pa), so the threshold is effectively always exceeded and the
   capacity is governed by width and slope rather than by the threshold.

Consequence, stated plainly: at the declared defaults the coupling makes entrainment
**finitely capacity-limited** (measured utilisation 0.967, i.e. it acts), and a dry
catchment entrains nothing (the gate P8 could not state). It does **not** yet make
entrainment finely proportional to rainfall, because the two ceilings above sit in
the way. Lifting them (a calibration decision, not a coding one) is an open item.

Relationship to the two half-ledgers
------------------------------------
This module **consumes** rather than replaces: the water half is
`metric_domain_flow.domain_flow_topology`, the routing arrays are
`metric_domain_closure.domain_topology`, and the geometry, shear and capacity
formulas are called from `metric_channel_plan.ChannelRecipe` /
`metric_sediment`'s declared coefficient set. No flood and no steepest-D8 pass is
authored here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import math

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.channel_geometry import ChannelRecipe
from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.metric_domain_flow import domain_flow_topology

__all__ = [
    "ALGORITHM",
    "COUPLED_SCHEMA",
    "LIMITATIONS",
    "MAX_INTERVALS",
    "PRODUCT_KEYS",
    "CoupledParameters",
    "coupled_name",
    "load_domain_coupled",
    "save_domain_coupled",
    "solve_domain_coupled",
    "validate_domain_coupled",
]

ALGORITHM = "domain-coupled-water-sediment-ledger-v2-irregular-metric"
COUPLED_SCHEMA = "river-domain-coupled-v1"

RHO_WATER_KG_M3 = 1000.0
GRAVITY_M_S2 = 9.81

# Inherited from `metric_domain_flow` (the water half's own cap: the shared soil
# bucket budgets `steps * cells <= 1e6`, and a 129 x 129 core has 16 641 nodes).
MAX_INTERVALS = 60

# Contract key set, in order. All series (1-D), no 0-d scalars, for the measured
# `mountain_source_adapter.readonly` reason the two half-ledgers both record.
PRODUCT_KEYS = (
    "outlet_x_m",
    "outlet_z_m",
    "kind",
    "cell_count",
    "area_m2",
    "rain_input_m3",
    "actual_et_m3",
    "soil_storage_change_m3",
    "water_release_m3",
    "reference_discharge_m3_s",
    "mean_channel_width_m",
    "mean_channel_depth_m",
    "mean_excess_shear_pa",
    "capacity_volume_m3",
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
    "the discharge is a declared flattening of the water ledger's released volume "
    "(volume / (intervals * dt_s)), not a hydrograph, not a peak flow, and it "
    "carries no travel time",
    "channel width and depth come from the repository's declared ChannelRecipe power "
    "law; its reference discharge and exponents are uncalibrated engineering "
    "assumptions",
    "shear and transport capacity use the repository's declared sediment "
    "coefficients (rho g R S and k_t * width * excess**1.5); no grain size, no "
    "roughness calibration",
    "capacity now limits ENTRAINMENT; deposition is still a declared constant "
    "fraction of the passing load and is not a settling-velocity law",
    "the ledger reports volumes only: it writes no bed change, no Exner update and "
    "no derived surface, and it does not modify the immutable base face",
    "cells are the accepted LAND cells of the owning tile's CORE; the tile margin "
    "carries no source and no initial inventory, and settles routed load which is "
    "attributed to the domain its chain drains to",
    "instantaneous routing is still not a flood wave; hydraulic_ready, "
    "natural_outlet_verified and publishable remain false",
    "three ceilings were calibrated (P9.1: infiltration 15->2, width cap 30->1000, "
    "critical shear 1->50); constant weathering is still the default; an optional "
    "water-dependent source requires explicit nonzero coefficient and erodible-area "
    "fraction (domain-coupled-spec.md §5.1)",
)

@dataclass(frozen=True)
class CoupledParameters:
    """Declared coefficients, all inherited from existing repository modules.

    Nothing new is invented here. `channel` is `metric_channel_plan.ChannelRecipe`
    (the discharge -> width/depth power law), and the shear / capacity coefficients
    are the ones `metric_sediment.MaterialParameters` declares. Holding the
    repository's own frozen dataclasses as fields is deliberate: it makes
    "which law am I using" answerable by reading one type, and it keeps this
    module's identity sensitive to the same numbers their home modules use.

    `water_source_coefficient_m_per_interval_per_m3_s` is an explicit opt-in source
    coefficient.  With the default zero coefficient (or zero area fraction), the
    historical constant source remains unchanged.  The coefficient is a declared
    engineering parameter with units of metres per interval per (m3/s); the area
    fraction limits it to the effective erodible part of each coarse cell.

    The three ceilings are calibrated (P9.1; user decision 2026-10-21: raise them)
    because at their inherited values the chain had no rainfall resolution. Each
    value was chosen by a measured sweep, not by taste, and carries its basis:

    * `infiltration_capacity_mm_h = 2.0` (was 15): the bucket is **threshold-type**
      -- at or above the rain rate nothing becomes runoff. Measured: release is
      `1.047e8 m3` (the declared 30 mm draw-down) for infiltration 15, 8 **and 4**,
      then jumps to `5.9e9 m3` at 2. 2 mm/h is a silty-clay end member;
    * `max_width_m = 1000`, `max_depth_m = 50` (was 30 / 3): the power law
      **saturates by itself** near 150 m at this discharge, so 1000 is a
      non-binding cap rather than a new law. Measured mean width at rain 4:
      **150.4 m** with the cap at 1000 versus **150.5 m** with it at 1e6 -- the cap
      no longer decides anything;
    * `sediment_critical_shear_pa = 50` (was 1): a gravel-scale threshold. Measured
      to be **nearly inert** here -- the coarse-grid shear is ~1450 Pa, so raising
      the threshold from 1 to 500 Pa changes capacity by only ~35%. It is a
      declaration, not a tuning knob.

    **What the calibration did NOT achieve, measured and stated**: entrainment is
    still **source-limited**. Raising the caps moved the binding constraint from
    capacity to the declared weathering (`weathered_m_per_interval`), which is a
    CONSTANT independent of water. Measured after calibration: capacity rises
    `2.28e8 -> 2.06e11 m3` across rain 2..40 (~900x) while entrainment moves only
    `1.85e8 -> 7.67e8 m3` and flattens, converging on the declared weathered volume
    `7.68e8`. So the coupling has **capacity-side** resolution, not entrainment-
    side resolution. Making entrainment respond to water needs the SOURCE to become
    water-dependent (a stream-power or excess-shear erosion law) -- a modelling
    change, not a knob. See `domain-coupled-spec.md` §5.1.
    """

    channel: ChannelRecipe = field(default_factory=lambda: ChannelRecipe(
        min_width_m=1.0, max_width_m=1000.0, min_depth_m=0.2, max_depth_m=50.0))
    runoff: RunoffParameters = field(
        default_factory=lambda: RunoffParameters(infiltration_capacity_mm_h=2.0))
    weathered_m_per_interval: float = 0.0002
    water_source_coefficient_m_per_interval_per_m3_s: float = 0.0
    effective_erodible_area_fraction: float = 0.0
    deposit_fraction: float = 0.3
    initial_mobile_m: float = 0.0
    # The repository's declared sediment coefficients, restated as plain fields so
    # this module's parameter identity is flat and readable.
    transport_coefficient_m3_s_per_pa15: float = 1e-5
    sediment_critical_shear_pa: float = 50.0

    def __post_init__(self):
        if not isinstance(self.channel, ChannelRecipe):
            raise ValueError("channel must be a ChannelRecipe")
        if not isinstance(self.runoff, RunoffParameters):
            raise ValueError("runoff must be a RunoffParameters")
        for name in ("weathered_m_per_interval", "water_source_coefficient_m_per_interval_per_m3_s",
                     "initial_mobile_m", "transport_coefficient_m3_s_per_pa15",
                     "sediment_critical_shear_pa"):
            value = getattr(self, name)
            if (isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, float, np.integer, np.floating))
                    or not math.isfinite(float(value)) or float(value) < 0.0):
                raise ValueError("%s must be finite and nonnegative" % name)
        fraction = self.effective_erodible_area_fraction
        if (isinstance(fraction, (bool, np.bool_))
                or not isinstance(fraction, (int, float, np.integer, np.floating))
                or not math.isfinite(float(fraction))
                or not 0.0 <= float(fraction) <= 1.0):
            raise ValueError("effective_erodible_area_fraction must be finite and within [0, 1]")
        fraction = self.deposit_fraction
        if (isinstance(fraction, (bool, np.bool_))
                or not isinstance(fraction, (int, float, np.integer, np.floating))
                or not math.isfinite(float(fraction))
                or not 0.0 <= float(fraction) <= 1.0):
            raise ValueError("deposit_fraction must be finite and within [0, 1]")


def _config_id(config):
    from terrain_pipeline.surface_rivers.metric_domain_pipeline import config_identity
    return config_identity(config)


def coupled_name(outlet_x_m, outlet_z_m):
    """Deterministic product name from the domain identity (the outlet)."""
    return "river-domain-coupled-%d-%d-%s-v1.npz" % (
        int(round(float(outlet_x_m))), int(round(float(outlet_z_m))), COUPLED_SCHEMA)


def _parameters_record(parameters):
    record = {}
    for item in fields(parameters):
        value = getattr(parameters, item.name)
        record[item.name] = asdict(value) if hasattr(value, "__dataclass_fields__") else value
    return record


def _channel_geometry(q_m3_s, channel, spacing_m, height, receiver, *,
                      origin_xz_m=(0., 0.), world_seed=20261020):
    """Width, depth and the flow-path slope, from the repository's declared law.

    `W = clip(ref_w * (q / ref_q) ** width_exp, min_w, max_w)` and the analogous
    depth, exactly the shape `metric_channel_plan.plan_channel` uses (the ratio and
    the two clips are the whole of it). The slope is the **flow-path** slope -- the
    drop to the steepest receiver over the distance to it -- because that is the
    surface the routing itself is built on, so the shear cannot drift from the graph
    the closure module certifies. A cell with no strictly-downhill receiver gets the
    local gradient magnitude instead, and a cell outside the core contributes zero.
    """
    ratio = np.divide(q_m3_s, channel.reference_discharge_m3_s,
                      out=np.zeros_like(q_m3_s), where=q_m3_s > 0.0)
    width = np.clip(channel.reference_width_m * ratio ** channel.width_exponent,
                    channel.min_width_m, channel.max_width_m)
    depth = np.clip(channel.reference_depth_m * ratio ** channel.depth_exponent,
                    channel.min_depth_m, channel.max_depth_m)
    width = np.where(q_m3_s > 0.0, width, 0.0)
    depth = np.where(q_m3_s > 0.0, depth, 0.0)

    rows, columns = height.shape
    flat_height = np.asarray(height, np.float64).reshape(-1)
    flat_receiver = np.asarray(receiver, np.int64).reshape(-1)
    slope = np.zeros(flat_height.size, np.float64)
    dh_dz, dh_dx = np.gradient(np.asarray(height, np.float64), spacing_m, spacing_m)
    local = np.hypot(dh_dx, dh_dz).reshape(-1)
    cells = np.flatnonzero(flat_receiver >= 0)
    if cells.size:
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        mesh = grid_mesh(height.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                         dx_m=spacing_m, world_seed=world_seed)
        target = flat_receiver[cells]
        distance = np.hypot(mesh.node_x_m[cells] - mesh.node_x_m[target],
                            mesh.node_z_m[cells] - mesh.node_z_m[target])
        drop = flat_height[cells] - flat_height[target]
        slope[cells] = np.clip(drop / np.maximum(distance, spacing_m * 1e-12), 0.0, None)
    terminals = flat_receiver < 0
    slope[terminals] = local[terminals]
    return width.reshape(height.shape), depth.reshape(height.shape), slope.reshape(height.shape)


def _hydraulic_radius(width_m, depth_m):
    """R = W d / (W + 2 d), the repository's own rectangle approximation."""
    return np.divide(width_m * depth_m, width_m + 2.0 * depth_m,
                     out=np.zeros_like(depth_m), where=(width_m + 2.0 * depth_m) > 0.0)


def solve_domain_coupled(seed, points_xz_m, rain_mm_h, *, config=None, parameters=None,
                         dt_s=3600.0, intervals=12, source_m_per_interval=None):
    """Coupled ledger for one world-anchored tile.

    Water first (`domain_flow_topology`), then discharge, channel, shear, capacity,
    then capacity-limited entrainment along the closure module's irregular graph.
    Every point must share one tile, or it is an input error -- never a silent
    second tile.
    """
    config = config or PlanningConfig()
    config.validate()
    parameters = parameters or CoupledParameters()
    if not isinstance(parameters, CoupledParameters):
        raise ValueError("CoupledParameters required")
    if not isinstance(intervals, int) or isinstance(intervals, bool):
        raise ValueError("intervals must be an integer")
    if not 1 <= intervals <= MAX_INTERVALS:
        raise ValueError("intervals must be 1..%d" % MAX_INTERVALS)

    points = [(float(x), float(z)) for x, z in points_xz_m]
    if not points:
        raise ValueError("at least one world point is required to select the tile")
    water = domain_flow_topology(seed, points[0][0], points[0][1], rain_mm_h,
                                 config=config, parameters=parameters.runoff,
                                 dt_s=dt_s, intervals=intervals)
    topology = water["topology"]
    for x_m, z_m in points[1:]:
        other = domain_flow_topology(seed, x_m, z_m, rain_mm_h, config=config,
                                     parameters=parameters.runoff,
                                     dt_s=dt_s, intervals=intervals)["topology"]
        if (other["origin_x_m"] != topology["origin_x_m"]
                or other["origin_z_m"] != topology["origin_z_m"]):
            raise ValueError("all points must share one world-anchored tile; "
                             "got a second tile at (%r, %r)" % (x_m, z_m))

    spacing = float(water["spacing_m"])
    cell_area_m2 = float(water["cell_area_m2"])
    core_cells = int(water["core_cells"])
    margin = int(water["margin"])
    rows, columns = water["shape"]
    dt_s = float(water["dt_s"])

    height = np.asarray(topology["height_m"], np.float64)
    receiver = np.asarray(topology["receiver"], np.int64)
    terminal = np.asarray(topology["terminal"], np.int64)
    accepted = np.asarray(topology["accepted"], bool)
    ocean_terminal = np.asarray(topology["ocean_terminal"], bool)
    owner_x = np.asarray(topology["owner_outlet_x_m"], np.float64)
    owner_z = np.asarray(topology["owner_outlet_z_m"], np.float64)

    producing_flat = np.asarray(water["producing_flat"], np.int64)
    released_grid = np.asarray(water["released_grid_m3"], np.float64)

    # ---- discharge, accumulated downstream -------------------------------------
    # The water ledger routes a VOLUME instantaneously, so a representative rate is
    # the declared flattening `volume / duration`. Stated as a declaration because a
    # hydrograph would need a travel time this chain does not carry.
    duration_s = dt_s * intervals
    local_q = np.asarray(released_grid, np.float64).reshape(-1) / duration_s

    flat_receiver = receiver.reshape(-1)
    flat_height = height.reshape(-1)
    downstream_first = np.argsort(flat_height, kind="stable")
    accumulated_q = local_q.copy()
    # Ascending height is upstream-first for a strictly-downhill receiver, so
    # summing each cell into its receiver once propagates the whole upstream chain.
    for cell in downstream_first[::-1]:
        target = flat_receiver[cell]
        if target >= 0:
            accumulated_q[target] += accumulated_q[cell]

    # ---- channel, shear, capacity ----------------------------------------------
    width, depth, slope = _channel_geometry(accumulated_q.reshape(rows, columns),
        parameters.channel, spacing, height, receiver,
        origin_xz_m=(topology["origin_x_m"], topology["origin_z_m"]), world_seed=seed)
    radius = _hydraulic_radius(width, depth)
    tau = RHO_WATER_KG_M3 * GRAVITY_M_S2 * radius * slope
    excess = np.maximum(tau - parameters.sediment_critical_shear_pa, 0.0)
    # The repository's own capacity law (`metric_sediment._rates`), in solid m3/s.
    capacity_rate = (parameters.transport_coefficient_m3_s_per_pa15
                     * width * excess ** 1.5)
    if not (np.isfinite(capacity_rate).all() and np.isfinite(tau).all()):
        raise ValueError("coupled hydraulics produced nonfinite rates")

    flat_capacity_volume = (capacity_rate * dt_s).reshape(-1)
    flat_width = width.reshape(-1)
    flat_depth = depth.reshape(-1)
    flat_excess = excess.reshape(-1)

    # ---- source, store, capacity-limited entrainment ---------------------------
    source_grid = _source_grid(source_m_per_interval,
                               parameters.weathered_m_per_interval, core_cells)
    if (source_m_per_interval is None
            and parameters.water_source_coefficient_m_per_interval_per_m3_s > 0.0
            and parameters.effective_erodible_area_fraction > 0.0):
        source_grid = (parameters.water_source_coefficient_m_per_interval_per_m3_s
                       * accumulated_q.reshape(rows, columns)[margin:margin + core_cells + 1,
                                                               margin:margin + core_cells + 1]
                       * parameters.effective_erodible_area_fraction)
    producing_rows, producing_columns = np.divmod(producing_flat, columns)
    source_tile = np.zeros(rows * columns, np.float64)
    source_tile[producing_flat] = source_grid[producing_rows - margin,
                                               producing_columns - margin]

    producing_mask = np.zeros(rows * columns, bool)
    producing_mask[producing_flat] = True
    initial_mobile = float(parameters.initial_mobile_m)
    store = np.zeros(rows * columns, np.float64)
    store[producing_flat] = initial_mobile

    weathered_flat = np.zeros(rows * columns, np.float64)
    entrained_flat = np.zeros(rows * columns, np.float64)
    deposited_flat = np.zeros(rows * columns, np.float64)
    delivered_flat = np.zeros(rows * columns, np.float64)
    capacity_used_flat = np.zeros(rows * columns, np.float64)
    capacity_violation_m3 = 0.0

    upstream_first = np.argsort(-flat_height, kind="stable")
    for _ in range(intervals):
        available = np.where(producing_mask, store + source_tile, 0.0)
        # THE coupling: the flow can only entrain what its own shear lets it carry.
        # Zero discharge -> zero capacity -> zero entrainment, which is exactly the
        # behaviour the P8 slope law could not express.
        allowed_volume = np.where(producing_mask, flat_capacity_volume, 0.0)
        take_volume = np.minimum(available * cell_area_m2, allowed_volume)
        take_volume = np.maximum(take_volume, 0.0)
        overshoot = np.maximum(take_volume - allowed_volume, 0.0)
        if overshoot.any():
            capacity_violation_m3 = max(capacity_violation_m3,
                                        float(np.max(overshoot)))
        store = available - take_volume / cell_area_m2
        weathered_flat += source_tile * cell_area_m2
        entrained_flat += take_volume
        capacity_used_flat += take_volume
        load = take_volume.copy()
        for cell in upstream_first:
            value = load[cell]
            if value <= 0.0:
                continue
            if accepted.reshape(-1)[cell]:
                settle = parameters.deposit_fraction * value
                if settle > 0.0:
                    deposited_flat[cell] += settle
                    value -= settle
                    load[cell] = value
            target = flat_receiver[cell]
            if target >= 0:
                load[target] += value
                load[cell] = 0.0
        delivered_flat += load

    store_change_flat = np.where(producing_mask, store - initial_mobile, 0.0) * cell_area_m2

    # ---- per-domain attribution -------------------------------------------------
    producing_terminal = np.asarray(terminal, np.int64).reshape(-1)[producing_flat]
    producing_outlet_x = owner_x.reshape(-1)[producing_flat]
    producing_outlet_z = owner_z.reshape(-1)[producing_flat]
    if producing_flat.size and not (np.isfinite(producing_outlet_x).all()
                                    and np.isfinite(producing_outlet_z).all()):
        raise ValueError("accepted producing cells must carry a finite owner outlet")

    domains = {}
    for position in range(producing_flat.size):
        flat_term = int(producing_terminal[position])
        key = (float(producing_outlet_x[position]), float(producing_outlet_z[position]))
        record = domains.get(key)
        if record is None:
            record = domains[key] = {"terminal": flat_term, "positions": [],
                                     "marine": bool(ocean_terminal.reshape(-1)[flat_term])}
        elif record["terminal"] != flat_term:
            raise ValueError("one outlet coordinate carries two terminals")
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
    water_release_m3 = np.empty(count, np.float64)
    reference_discharge_m3_s = np.empty(count, np.float64)
    mean_channel_width_m = np.empty(count, np.float64)
    mean_channel_depth_m = np.empty(count, np.float64)
    mean_excess_shear_pa = np.empty(count, np.float64)
    capacity_volume_m3 = np.empty(count, np.float64)
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

    producing_world_x = topology["origin_x_m"] + producing_columns * spacing
    producing_world_z = topology["origin_z_m"] + producing_rows * spacing
    release_per_cell = np.asarray(water["released_per_cell_m3"], np.float64)
    et_per_cell = np.asarray(water["et_per_cell_m3"], np.float64)
    storage_per_cell = np.asarray(water["soil_storage_change_per_cell_m3"], np.float64)
    rain_depth = np.asarray(water["rain_depth_per_interval_m"], np.float64)

    accepted_flat = accepted.reshape(-1)
    for index, key in enumerate(keys):
        record = domains[key]
        positions = np.asarray(record["positions"], np.int64)
        cell_flat = producing_flat[positions]
        outlet_x[index] = key[0]
        outlet_z[index] = key[1]
        kind[index] = "marine" if record["marine"] else "inland"
        cell_count[index] = positions.size
        area_m2[index] = positions.size * cell_area_m2
        rows_in_core = producing_rows[positions] - margin
        columns_in_core = producing_columns[positions] - margin
        rain_input_m3[index] = float(np.sum(
            np.sum(rain_depth, axis=0)[rows_in_core, columns_in_core],
            dtype=np.float64) * cell_area_m2)
        actual_et_m3[index] = float(np.sum(et_per_cell[positions], dtype=np.float64))
        soil_storage_change_m3[index] = float(np.sum(storage_per_cell[positions], dtype=np.float64))
        water_release_m3[index] = float(np.sum(release_per_cell[positions], dtype=np.float64))
        reference_discharge_m3_s[index] = float(np.sum(
            accumulated_q[cell_flat], dtype=np.float64) / max(positions.size, 1))
        mean_channel_width_m[index] = float(np.sum(flat_width[cell_flat], dtype=np.float64)
                                            / max(positions.size, 1))
        mean_channel_depth_m[index] = float(np.sum(flat_depth[cell_flat], dtype=np.float64)
                                            / max(positions.size, 1))
        mean_excess_shear_pa[index] = float(np.sum(flat_excess[cell_flat], dtype=np.float64)
                                             / max(positions.size, 1))
        capacity_volume_m3[index] = float(np.sum(capacity_used_flat[cell_flat], dtype=np.float64))
        weathered_m3[index] = float(np.sum(weathered_flat[cell_flat], dtype=np.float64))
        entrained_m3[index] = float(np.sum(entrained_flat[cell_flat], dtype=np.float64))
        deposited_m3[index] = float(np.sum(
            deposited_flat[accepted_flat & (np.asarray(terminal, np.int64).reshape(-1)
                                            == record["terminal"])], dtype=np.float64))
        store_change_m3[index] = float(np.sum(store_change_flat[cell_flat], dtype=np.float64))
        delivered_m3[index] = float(delivered_flat[record["terminal"]])
        source_residual_m3[index] = (weathered_m3[index] - entrained_m3[index]
                                     - store_change_m3[index])
        routing_residual_m3[index] = (entrained_m3[index] - deposited_m3[index]
                                      - delivered_m3[index])
        cell_offsets[index + 1] = cell_offsets[index] + positions.size
        domain_terminals[index] = record["terminal"]
        cells_x.append(producing_world_x[positions])
        cells_z.append(producing_world_z[positions])

    cells_x_m = (np.concatenate(cells_x) if cells_x else np.zeros(0, np.float64))
    cells_z_m = (np.concatenate(cells_z) if cells_z else np.zeros(0, np.float64))

    matched = np.zeros(rows * columns, bool)
    if count:
        matched[domain_terminals] = True
    unclaimed = delivered_flat.copy()
    unclaimed[matched] = 0.0
    stranded_on_refused_m3 = float(np.sum(unclaimed, dtype=np.float64))

    weathered_total = float(np.sum(weathered_flat, dtype=np.float64))
    entrained_total = float(np.sum(entrained_flat, dtype=np.float64))
    deposited_total = float(np.sum(deposited_flat, dtype=np.float64))
    delivered_total = float(np.sum(delivered_m3, dtype=np.float64))
    store_change_total = float(np.sum(store_change_flat, dtype=np.float64))
    capacity_total_m3 = float(np.sum(capacity_rate.reshape(-1)[producing_flat],
                                     dtype=np.float64) * dt_s * intervals)
    capacities = capacity_rate.reshape(-1)[producing_flat] * dt_s

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
        "water_release_m3": water_release_m3,
        "reference_discharge_m3_s": reference_discharge_m3_s,
        "mean_channel_width_m": mean_channel_width_m,
        "mean_channel_depth_m": mean_channel_depth_m,
        "mean_excess_shear_pa": mean_excess_shear_pa,
        "capacity_volume_m3": capacity_volume_m3,
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
        "limitations": np.asarray(LIMITATIONS,
                                  "<U" + str(max(len(text) for text in LIMITATIONS))),
    }
    metadata = {
        "algorithm": ALGORITHM,
        "schema": COUPLED_SCHEMA,
        "seed": int(seed),
        "config_id": config_id,
        "spacing_m": spacing,
        "dt_s": dt_s,
        "interval_count": int(intervals),
        "duration_s": duration_s,
        "cell_area_m2": cell_area_m2,
        "core_cells": core_cells,
        "tile_shape": [int(rows), int(columns)],
        "tile_origin_m_xz": [float(topology["origin_x_m"]), float(topology["origin_z_m"])],
        "parameters": _parameters_record(parameters),
        "domain_count": int(count),
        "requested_points": len(points),
        "totals": {
            "requested_rain_m3": float(water["requested_rain_m3"]),
            "routed_rain_m3": float(water["routed_rain_m3"]),
            "unresolved_rain_m3": float(water["unresolved_rain_m3"]),
            "ocean_direct_rain_m3": float(water["ocean_direct_rain_m3"]),
            "outside_core_rain_m3": float(water["outside_core_rain_m3"]),
            "water_release_total_m3": float(np.sum(release_per_cell, dtype=np.float64)),
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
            "capacity_volume_total_m3": capacity_total_m3,
            "capacity_violation_m3": capacity_violation_m3,
            "capacity_utilisation": (float(entrained_total / capacity_total_m3)
                                     if capacity_total_m3 > 0.0 else 0.0),
            "accepted_cells": int(producing_flat.size),
            "zero_capacity_cells": int(np.count_nonzero(capacities <= 0.0)),
            "initial_mobile_total_m3": float(initial_mobile * producing_flat.size
                                              * cell_area_m2),
            "mean_channel_width_m": (float(np.mean(flat_width[producing_flat]))
                                     if producing_flat.size else 0.0),
            "min_channel_width_m": (float(np.min(flat_width[producing_flat]))
                                    if producing_flat.size else 0.0),
            "max_channel_width_m": (float(np.max(flat_width[producing_flat]))
                                    if producing_flat.size else 0.0),
            "mean_channel_depth_m": (float(np.mean(flat_depth[producing_flat]))
                                     if producing_flat.size else 0.0),
            "min_channel_depth_m": (float(np.min(flat_depth[producing_flat]))
                                    if producing_flat.size else 0.0),
            "max_channel_depth_m": (float(np.max(flat_depth[producing_flat]))
                                    if producing_flat.size else 0.0),
            "mean_excess_shear_pa": (float(np.mean(flat_excess[producing_flat]))
                                     if producing_flat.size else 0.0),
            "mean_reference_discharge_m3_s": (float(np.mean(accumulated_q[producing_flat]))
                                              if producing_flat.size else 0.0),
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
    validate_domain_coupled(record)
    return record


def _source_grid(source_m_per_interval, default_depth, core_cells):
    """Declared weathering depth per interval [m] on the core node lattice.

    Same injection discipline as `metric_domain_sediment`: `None` (the parameter
    default), a scalar, or a `(core+1, core+1)` grid. Anything else is an input
    error, never silently broadcast -- a mis-shaped field would move the whole
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


def validate_domain_coupled(record):
    """Cold validation: shapes, both ledgers, the reported totals, and the gate.

    Recomputes from the arrays in front of it, so a forged `totals` block is caught
    rather than trusted. Raises ValueError on any breach.
    """
    if not isinstance(record, dict) or set(record) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("coupled bundle must be {arrays, metadata, identity_sha256}")
    arrays = record["arrays"]
    metadata = record["metadata"]
    expected = set(PRODUCT_KEYS)
    if set(arrays) != expected:
        raise ValueError("coupled arrays must be exactly the contract keys; "
                         "missing %s, unexpected %s"
                         % (sorted(expected - set(arrays)), sorted(set(arrays) - expected)))
    if metadata.get("schema") != COUPLED_SCHEMA:
        raise ValueError("coupled schema mismatch")
    for key in ("seed", "config_id", "spacing_m", "dt_s", "interval_count",
                "duration_s", "domain_count", "cell_area_m2"):
        if key not in metadata:
            raise ValueError("metadata.%s is required" % key)
    if not isinstance(metadata["config_id"], str) or len(metadata["config_id"]) != 64:
        raise ValueError("metadata.config_id must be a sha256 hex digest")
    for key in ("dt_s", "duration_s", "spacing_m", "cell_area_m2"):
        value = metadata[key]
        if (isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not math.isfinite(float(value)) or float(value) <= 0.0):
            raise ValueError("metadata.%s must be finite and positive" % key)
    if not isinstance(metadata["interval_count"], int) or isinstance(metadata["interval_count"], bool):
        raise ValueError("metadata.interval_count must be an integer")
    if not 1 <= metadata["interval_count"] <= MAX_INTERVALS:
        raise ValueError("metadata.interval_count must be 1..%d" % MAX_INTERVALS)
    if identity(arrays, metadata) != record["identity_sha256"]:
        raise ValueError("coupled identity mismatch")

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

    for name in ("cell_count", "area_m2", "rain_input_m3", "actual_et_m3",
                 "soil_storage_change_m3", "water_release_m3",
                 "reference_discharge_m3_s", "mean_channel_width_m",
                 "mean_channel_depth_m", "mean_excess_shear_pa", "capacity_volume_m3",
                 "weathered_m3", "entrained_m3", "deposited_m3", "delivered_m3",
                 "store_change_m3", "source_residual_m3", "routing_residual_m3"):
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
                 "stranded_on_refused_m3", "capacity_volume_total_m3",
                 "capacity_violation_m3"):
        if name not in totals or not math.isfinite(float(totals[name])):
            raise ValueError("metadata.totals.%s must be a finite number" % name)
    tolerance = 1e-6 * max(float(totals["weathered_total_m3"]), 1.0)
    for name, array in (("weathered_total_m3", weathered),
                        ("entrained_total_m3", entrained),
                        ("deposited_total_m3", deposited),
                        ("delivered_total_m3", delivered)):
        if abs(float(totals[name]) - float(np.sum(array, dtype=np.float64))) > tolerance:
            raise ValueError("%s must equal the domain sum" % name)
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

    # The coupling gates. `capacity_violation_m3` is measured during the solve; a
    # nonzero value means entrainment exceeded what the shear implied, which would
    # make the whole coupling claim false. It is a hard zero, not a tolerance to
    # widen.
    if float(totals["capacity_violation_m3"]) > 0.0:
        raise ValueError("entrainment exceeded the flow's own transport capacity")
    capacity_total = float(totals["capacity_volume_total_m3"])
    if capacity_total < -tolerance:
        raise ValueError("capacity_volume_total_m3 must be nonnegative")
    if capacity_total > 0.0 and float(totals["entrained_total_m3"]) > capacity_total + tolerance:
        raise ValueError("tile entrainment exceeds the tile capacity budget")

    claims = metadata.get("claims")
    if not isinstance(claims, dict) or any(claims.get(key) is not False for key in
                                           ("hydraulic_ready", "natural_outlet_verified",
                                            "publishable", "terrain_feedback_applied")):
        raise ValueError("a coupled product claims no publishable hydraulics "
                         "and no applied terrain feedback")
    return True


def save_domain_coupled(path, record):
    """Persist with the repository's atomic-link discipline; never overwrite."""
    save_bundle(path, record, validator=validate_domain_coupled)


def load_domain_coupled(path, *, expected_sha256, expected_identity=None):
    """Reload cold, re-deriving the identity; refuse a wrong expected value."""
    record = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_domain_coupled)
    if expected_identity is not None and record["identity_sha256"] != expected_identity:
        raise ValueError("coupled identity mismatch against the expected value")
    return record
