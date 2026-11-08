"""Finite-event water supply over an already-certified strict-D8 support.

Scope, stated once so later milestones cannot read more into it: this module orchestrates a
*finite* event. It does not solve soil water, does not route terrain and does not add channel
storage. The caller supplies the frozen soil kernel (``regional_surface_forcing.advance_soil``),
the already-certified strict-D8 receiver graph, the physical domain (reach plus lake-bed cells)
and one declared safety level. Here we only prepare and validate that finite domain, advance the
per-interval state, deliver each interval's real local water exactly once to the single retained
terminal, and keep the lake's exact piecewise-linear stage/volume curve.

Routing is ``quasi_steady_d8_no_channel_storage``: an interval's real local release is
accumulated along the certified strict-D8 receiver to the lake terminal inside that same
interval. No channel storage, travel time, peak timing or transient hydraulics are claimed.
Soil infiltration and percolation are internal transfers and are never external losses.

Nothing here is a climate, calibration or permanent-water-surface claim.
"""

import math

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.climate_forcing import advance_soil
from terrain_pipeline.drainage import MAX_NETWORK_CELLS as MAX_NETWORK_CELLS
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge

ROUTING_POLICY = 'quasi_steady_d8_no_channel_storage'
ROUTING_SEMANTICS = (
    'quasi_steady_d8_no_channel_storage: each interval real local release is accumulated once '
    'along the certified strict-D8 receiver to the single retained lake terminal inside the same '
    'interval; no channel storage, travel time, peak timing or transient hydraulics are claimed')
BALANCE_ABSOLUTE_M3 = 1e-8
BALANCE_RELATIVE = 1e-10
MAX_CELL_AREA_M2 = 1e9
KIND_DTYPE = 'U24'


def _finite(value, label, *, maximum=1e12, positive=False):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.floating, np.integer))
            or not math.isfinite(float(value)) or float(value) < 0 or float(value) > maximum
            or (positive and float(value) == 0.0)):
        raise ValueError('finite %srequired %s below %g' % ('positive ' if positive else 'nonnegative ', label, maximum))
    return float(value)


def _grid(array, shape, kind, label):
    if not isinstance(array, np.ndarray) or array.shape != shape:
        raise ValueError('%s must be a %s array' % (label, ('%dx%d' % shape)))
    if kind == 'f' and (array.dtype.kind != 'f' or not np.isfinite(array).all()):
        raise ValueError('%s must hold finite floats' % label)
    if kind == 'b' and array.dtype != np.bool_:
        raise ValueError('%s must be boolean' % label)
    if kind == 'i' and array.dtype != np.int64:
        raise ValueError('%s must be int64' % label)
    if kind == 'U' and (array.dtype.kind != 'U' or not np.isin(np.unique(array), ('interior', 'retained', 'inactive', 'open_outflow', 'unknown_boundary')).all()):
        raise ValueError('%s must carry declared terminal kinds' % label)
    return array


def _flat_bool(array, size, label):
    if not isinstance(array, np.ndarray):
        raise ValueError('%s must be an ndarray' % label)
    if array.shape == () or int(np.prod(array.shape)) != size:
        raise ValueError('%s must cover exactly the grid (%d cells)' % (label, size))
    if array.dtype != np.bool_:
        raise ValueError('%s must be boolean' % label)
    return np.ascontiguousarray(array.reshape(-1))


class LakeStageCurve:
    """Exact piecewise-linear stage/volume curve of one lake bed.

    ``V(h) = cell_area * sum_i max(h - bed_i, 0)`` over the bed cells: a convex, continuous,
    strictly increasing piecewise-linear function whose knots are the sorted bed elevations,
    together with its exact inverse and the wet-cell count. No interpolation table, no D4
    stage capacity and no fitted hypsometry are involved.
    """

    def __init__(self, bed_levels_m, cell_area_m2):
        levels = np.asarray(bed_levels_m)
        if levels.ndim != 1 or not 1 <= levels.size <= MAX_NETWORK_CELLS:
            raise ValueError('one-dimensional bounded bed-cell levels required')
        if levels.dtype.kind != 'f' or not np.isfinite(levels).all() or (levels < 0).any():
            raise ValueError('finite nonnegative bed levels required')
        area = _finite(cell_area_m2, 'cell area', maximum=MAX_CELL_AREA_M2, positive=True)
        self._levels = np.sort(np.array(levels, np.float64))
        self._area = area
        self._counts = np.arange(1, self._levels.size + 1, dtype=np.float64)
        self._sums = np.cumsum(self._levels)
        self._knot_volume = self._area * (self._counts * self._levels - self._sums)

    @property
    def cell_area_m2(self):
        return self._area

    @property
    def cell_count(self):
        return int(self._levels.size)

    @property
    def bed_levels_m(self):
        return self._levels.copy()

    @property
    def floor_level_m(self):
        return float(self._levels[0])

    @property
    def rim_level_m(self):
        return float(self._levels[-1])

    @property
    def maximum_volume_m3(self):
        return float(self._knot_volume[-1])

    def knots(self):
        return [{'level_m': float(level), 'volume_m3': float(volume)}
                for level, volume in zip(self._levels, self._knot_volume)]

    def volume(self, level_m):
        height = np.asarray(level_m, np.float64)
        if not np.isfinite(height).all():
            raise ValueError('finite water level required')
        below = np.searchsorted(self._levels, height, side='right')
        volume = np.zeros(height.shape, np.float64)
        wet = below > 0
        if np.any(~wet) and np.any(height[~wet] > self._levels[0]):
            raise ValueError('stage below the bed floor with wet cells')
        if wet.any():
            index = below[wet] - 1
            volume[wet] = self._area * (below[wet] * height[wet] - self._sums[index])
        return volume if volume.shape else float(volume)

    def level_of(self, volume_m3):
        volume = np.asarray(volume_m3, np.float64)
        if not np.isfinite(volume).all():
            raise ValueError('finite lake volume required')
        if np.any(volume < 0):
            raise ValueError('lake volume below the empty bed')
        if np.any(volume > self._knot_volume[-1]):
            raise ValueError('lake volume above the highest lake bed cell')
        index = np.searchsorted(self._knot_volume, volume, side='right') - 1
        index = np.clip(index, 0, self._levels.size - 1)
        level = (volume / self._area + self._sums[index]) / self._counts[index]
        return level if level.shape else float(level)

    def wet_cells(self, level_m):
        height = np.asarray(level_m, np.float64)
        if not np.isfinite(height).all():
            raise ValueError('finite water level required')
        count = np.searchsorted(self._levels, height, side='left')
        return int(count) if count.shape == () else count


class FiniteEventDomain:
    """Validated finite supply support: one retained lake terminal inside a closed reach."""

    def __init__(self, *, grid_shape, cell_area_m2, safe_level_m, safe_capacity_m3,
                 active_mask, land_flat, member_flat, receiver_active, terminal_kinds,
                 terminal_cell, lake):
        self.grid_shape = grid_shape
        self.cell_area_m2 = cell_area_m2
        self.safe_level_m = safe_level_m
        self.safe_capacity_m3 = safe_capacity_m3
        self.active_mask = active_mask
        self.active_flat = active_mask.reshape(-1)
        self.land_flat = land_flat
        self.member_flat = member_flat
        self.receiver_active = receiver_active
        self.terminal_kinds = terminal_kinds
        self.terminal_cell = terminal_cell
        self.lake = lake

    @property
    def active_cells(self):
        return int(np.count_nonzero(self.active_flat))

    @property
    def land_cells(self):
        return int(self.land_flat.size)

    @property
    def member_cells(self):
        return int(self.member_flat.size)

    def lake_state(self, volume_m3):
        volume = _finite(volume_m3, 'lake inventory')
        if volume > self.safe_capacity_m3:
            raise ValueError('lake inventory exceeds the declared safe capacity')
        if volume == 0.0:
            return {'volume_m3': 0.0, 'level_m': self.lake.floor_level_m,
                    'wet_cells': 0, 'dry': True}
        level = float(self.lake.level_of(volume))
        return {'volume_m3': volume, 'level_m': level,
                'wet_cells': int(self.lake.wet_cells(level)), 'dry': False}

    def metadata(self):
        return {
            'grid_shape': [int(value) for value in self.grid_shape],
            'cell_area_m2': self.cell_area_m2,
            'active_cells': self.active_cells,
            'land_cells': self.land_cells,
            'lake_bed_cells': self.member_cells,
            'terminal_cell': self.terminal_cell,
            'terminal_kind': 'retained',
            'routing_policy': ROUTING_POLICY,
            'routing_semantics': ROUTING_SEMANTICS,
            'safe_level_m': self.safe_level_m,
            'safe_capacity_m3': self.safe_capacity_m3,
            'lake_bed_levels_m': [float(value) for value in self.lake.bed_levels_m],
            'lake_floor_level_m': self.lake.floor_level_m,
            'lake_knot_count': self.lake.cell_count,
            'capacity_semantics': ('exact piecewise-linear V(h) = area * sum(max(h - bed, 0)) over '
                                   'the lake bed cells, with its exact inverse; the declared safe '
                                   'capacity is V(safe level) and is never a D4 stage capacity'),
            'channel_storage_m3': 0.0,
        }


def _terminal_closure(receiver, active, terminal):
    """Every active cell must reach the declared terminal; cycles and dead ends are refused."""
    size = receiver.size
    state = np.zeros(size, np.int8)
    state[terminal] = 1
    for start in np.flatnonzero(active):
        cell = int(start)
        path = []
        while True:
            current = int(state[cell])
            if current == 0:
                path.append(cell)
                state[cell] = -2
                cell = int(receiver[cell])
                continue
            if current == -2:
                raise ValueError('receiver graph contains a cycle')
            reachable = current == 1
            for node in path:
                state[node] = 1 if reachable else -1
            if not reachable:
                raise ValueError('active cell cannot reach the retained terminal')
            break
    return int((state == 1).sum())


def prepare_finite_event_domain(*, elevation_m, resolved_mask, receiver, terminal_kind,
                                member_mask, reach_mask, cell_area_m2, safe_level_m,
                                safe_capacity_m3, upstream_unknown_mask=None):
    """Validate a finite closing support and build the reusable event domain.

    The physical domain is exactly ``reach_mask`` inside ``resolved_mask``: its receiver graph
    must be closed (no active cell routes out of the reach, one retained terminal inside the lake
    bed), upstream-closed inside the resolved support (no resolved cell outside the reach routes
    into it, so the cut never drops a real donor while claiming completeness), complete (no cell
    with unknown upstream) and acyclic, and the lake bed set must be a closed subset that drains
    to that terminal. Every resolved receiver index is checked before clipping (only ``-1`` ends a
    path). Declared cells outside the reach become inactive with receiver ``-1`` and zero local
    water; an outside catchment that drains inside itself stays legitimately inactive.
    Nothing is filled, widened or guessed.
    """
    field = np.asarray(elevation_m)
    if field.ndim != 2 or not 1 <= field.size <= MAX_NETWORK_CELLS:
        raise ValueError('two-dimensional bounded elevation grid required')
    if field.dtype.kind != 'f' or not np.isfinite(field).all():
        raise ValueError('finite elevation grid required')
    shape = field.shape
    mask = _grid(resolved_mask, shape, 'b', 'resolved_mask')
    rec = _grid(receiver, shape, 'i', 'receiver')
    kinds = _grid(terminal_kind, shape, 'U', 'terminal_kind')
    member = _flat_bool(member_mask, field.size, 'member_mask')
    reach = _flat_bool(reach_mask, field.size, 'reach_mask')
    area = _finite(cell_area_m2, 'cell area', maximum=MAX_CELL_AREA_M2, positive=True)
    rec_flat = rec.reshape(-1)
    kinds_flat = kinds.reshape(-1)
    mask_flat = mask.reshape(-1)
    # A receiver index is validated on every *resolved* cell before any clipping: only -1 can mark
    # the end of a path, so a value like -2 is never reinterpreted as a second terminal, and no
    # onward receiver may leave the resolved support (otherwise the index would be used out of
    # bounds below).
    resolved = mask_flat
    if np.any(rec_flat[resolved] < -1) or np.any(rec_flat[resolved] >= rec_flat.size):
        raise ValueError('receiver index outside [-1, cells) on a resolved cell; only -1 may end a '
                         'path')
    resolved_onward = rec_flat[resolved] >= 0
    if np.any(~resolved[rec_flat[resolved][resolved_onward]]):
        raise ValueError('a resolved cell routes to an unresolved cell')
    if not reach.any():
        raise ValueError('the physical reach cannot be empty')
    if np.any(reach & ~mask_flat):
        raise ValueError('the physical reach must lie inside the resolved support')
    if not member.any():
        raise ValueError('at least one lake bed cell is required')
    if np.any(member & ~reach):
        raise ValueError('lake bed cells must lie inside the physical reach')
    live = reach & (rec_flat >= 0)
    terminals = np.flatnonzero(reach & (rec_flat < 0))
    if terminals.size != 1:
        raise ValueError('exactly one retained terminal cell required, found %d' % terminals.size)
    terminal = int(terminals[0])
    if not member[terminal]:
        raise ValueError('the retained terminal must be one of the lake bed cells')
    if np.any(rec_flat[live] >= rec_flat.size) or np.any(rec_flat[live] < -1):
        raise ValueError('receiver index outside the grid')
    if np.any(~reach[rec_flat[live]]):
        raise ValueError('an active cell routes out of the physical reach')
    # In-edge completeness: the reach must be upstream-closed inside the resolved support. A
    # resolved donor that is cut out of the reach but drips into it is a real water source, so the
    # domain is refused instead of being declared complete with that water dropped. An inactive
    # catchment that drains inside itself (never into the reach) stays legitimately inactive.
    donors = np.flatnonzero(resolved & ~reach & (rec_flat >= 0))
    if donors.size:
        draining_in = donors[reach[rec_flat[donors]]]
        if draining_in.size:
            raise ValueError('resolved cell %d outside the physical reach routes into it; the reach '
                             'would be a falsely complete cut, so its water is not dropped silently'
                             % int(draining_in[0]))
    successors = np.arange(rec_flat.size)
    if np.any(live & (rec_flat == successors)):
        raise ValueError('self receiver inside the physical reach')
    if np.any(live & (kinds_flat != 'interior')):
        raise ValueError('active nonterminal cells must be interior')
    if kinds_flat[terminal] != 'retained':
        raise ValueError('the retained terminal cell must carry the retained kind')
    member_cells = np.flatnonzero(member)
    succ = rec_flat[member_cells]
    outside = (succ >= 0) & ~member[np.where(succ >= 0, succ, 0)]
    if outside.any():
        raise ValueError('a lake bed cell routes out of the lake bed set; the lake is not closed')
    if np.any(member & ~live & (np.arange(rec_flat.size) != terminal)):
        raise ValueError('lake bed cells other than the terminal must have a receiver')
    if upstream_unknown_mask is not None:
        unknown = _flat_bool(upstream_unknown_mask, field.size, 'upstream_unknown_mask')
        if np.any(unknown & reach):
            raise ValueError('active cells with unknown upstream are refused; the finite domain must be complete')
    reachable = _terminal_closure(rec_flat, reach, terminal)
    if reachable != int(reach.sum()):
        raise ValueError('every active cell must reach the terminal')
    lake = LakeStageCurve(field.reshape(-1)[member], area)
    level = _finite(safe_level_m, 'safe level')
    capacity = _finite(safe_capacity_m3, 'safe capacity', positive=True)
    expected = float(lake.volume(level))
    if abs(expected - capacity) > BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * max(capacity, 1.0):
        raise ValueError('the declared safe capacity does not equal the exact lake volume at the '
                         'declared safe level (%.17g vs %.17g)' % (expected, capacity))
    active_mask = np.ascontiguousarray(reach.reshape(shape))
    receiver_active = np.where(active_mask, rec, -1).astype(np.int64)
    terminal_kinds = np.full(shape, 'inactive', KIND_DTYPE)
    flat_kinds = terminal_kinds.reshape(-1)
    flat_kinds[live] = 'interior'
    flat_kinds[terminal] = 'retained'
    return FiniteEventDomain(grid_shape=shape, cell_area_m2=area, safe_level_m=level,
                             safe_capacity_m3=capacity, active_mask=active_mask,
                             land_flat=np.ascontiguousarray(np.flatnonzero(reach & ~member)),
                             member_flat=np.ascontiguousarray(member_cells),
                             receiver_active=receiver_active, terminal_kinds=terminal_kinds,
                             terminal_cell=terminal, lake=lake)


def initial_event_state(domain, *, parameters):
    """Explicit initial inventories (dry lake, soil/quick/slow from the parameters)."""
    if not isinstance(domain, FiniteEventDomain):
        raise ValueError('prepared finite event domain required')
    if not isinstance(parameters, RunoffParameters):
        raise ValueError('explicit RunoffParameters required')
    parameters.__post_init__()
    states = np.zeros((3, domain.land_cells), np.float64)
    for row, value in enumerate((parameters.initial_soil_mm, parameters.initial_fast_mm,
                                 parameters.initial_slow_mm)):
        states[row] = float(value)
    return {'soil_states_mm': states, 'lake_volume_m3': 0.0, 'elapsed_s': 0.0}


def advance_finite_event(domain, soil_states_mm, lake_volume_m3, rain_mm_h, *, dt_s,
                         parameters, elapsed_s=0.0):
    """Advance one physical interval; inputs are never modified.

    ``rain_mm_h`` is one spatially uniform interval rate over the declared finite domain: the
    land cells see it only through the frozen soil kernel, and the lake bed cells receive the same
    depth directly as local water (no double accounting through soil). All local water is routed
    once and delivered to the lake inventory; a delivery that would exceed the declared safe
    capacity refuses the whole interval.
    """
    if not isinstance(domain, FiniteEventDomain):
        raise ValueError('prepared finite event domain required')
    if not isinstance(parameters, RunoffParameters):
        raise ValueError('explicit RunoffParameters required')
    parameters.__post_init__()
    states = soil_states_mm
    if (not isinstance(states, np.ndarray) or states.ndim != 2
            or states.shape != (3, domain.land_cells) or states.dtype != np.float64
            or not np.isfinite(states).all() or (states < 0).any()):
        raise ValueError('soil states must be finite nonnegative float64 [3, land_cells]')
    if (states[0] > parameters.soil_capacity_mm).any():
        raise ValueError('soil above prescribed capacity')
    lake = _finite(lake_volume_m3, 'lake inventory')
    if lake > domain.safe_capacity_m3:
        raise ValueError('initial lake inventory exceeds the declared safe capacity')
    rain = _finite(rain_mm_h, 'rain rate', maximum=1000.0)
    elapsed = _finite(elapsed_s, 'elapsed physical time')
    if (isinstance(dt_s, bool) or not isinstance(dt_s, (int, float)) or isinstance(dt_s, np.bool_)
            or not math.isfinite(float(dt_s)) or not 0 < float(dt_s) <= 3600):
        raise ValueError('positive physical timestep of at most 3600 s required')
    dt = float(dt_s)
    hours = dt / 3600.0
    area = domain.cell_area_m2
    land_rain_mm_h = np.full(domain.land_cells, rain, np.float64)
    next_states, release_mm, et_mm, change_mm = advance_soil(land_rain_mm_h, states, dt_s=dt,
                                                             parameters=parameters)
    depth_m3_per_cell = rain * hours * area / 1000.0
    land_release_m3 = release_mm * area / 1000.0
    et_volume_m3 = float(np.sum(et_mm)) * area / 1000.0
    soil_change_m3 = float(np.sum(change_mm)) * area / 1000.0
    land_rain_m3 = float(depth_m3_per_cell) * domain.land_cells
    lake_rain_m3 = float(depth_m3_per_cell) * domain.member_cells
    local_q = np.zeros(domain.grid_shape, np.float64)
    flat_q = local_q.reshape(-1)
    flat_q[domain.land_flat] = land_release_m3 / dt
    flat_q[domain.member_flat] = depth_m3_per_cell / dt
    accumulated = accumulate_network_discharge(domain.receiver_active, local_q,
                                               domain.active_mask,
                                               terminal_kind=domain.terminal_kinds,
                                               max_cells=int(domain.active_mask.size))
    routed_total_m3 = accumulated['input_total_m3_s'] * dt
    delivered_m3 = accumulated['retained_m3_s'] * dt
    open_m3 = accumulated['open_outflow_m3_s'] * dt
    unknown_m3 = accumulated['unknown_pending_m3_s'] * dt
    if open_m3 != 0.0 or unknown_m3 != 0.0:
        raise ValueError('a finite event domain must have one retained terminal and no open or '
                         'unknown outlet')
    gate = BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * max(routed_total_m3, 1.0)
    if abs(routed_total_m3 - delivered_m3) > gate:
        raise ValueError('routed water was not delivered exactly once (%.17g vs %.17g)'
                         % (routed_total_m3, delivered_m3))
    local_total_m3 = land_release_m3.sum() + lake_rain_m3
    if abs(local_total_m3 - routed_total_m3) > gate:
        raise ValueError('routed total disagrees with the local water input')
    next_lake = lake + delivered_m3
    if next_lake > domain.safe_capacity_m3:
        raise ValueError('lake inventory %.17g m3 would exceed the declared safe capacity '
                         '%.17g m3; the whole event is refused' % (next_lake, domain.safe_capacity_m3))
    lake_state = domain.lake_state(next_lake)
    active = domain.active_flat
    ledger = {
        'rain_land_m3': land_rain_m3,
        'rain_lake_m3': lake_rain_m3,
        'rain_total_m3': land_rain_m3 + lake_rain_m3,
        'et_m3': et_volume_m3,
        'soil_change_m3': soil_change_m3,
        'land_release_m3': float(land_release_m3.sum()),
        'lake_local_rain_m3': lake_rain_m3,
        'local_input_m3': local_total_m3,
        'routed_total_m3': routed_total_m3,
        'delivered_to_lake_m3': delivered_m3,
        'lake_change_m3': next_lake - lake,
        'channel_storage_m3': 0.0,
        'land_balance_residual_m3': land_rain_m3 - et_volume_m3 - float(land_release_m3.sum())
        - soil_change_m3,
        'port_residual_m3': routed_total_m3 - delivered_m3 - open_m3 - unknown_m3,
    }
    return {'soil_states_mm': next_states, 'lake_volume_m3': next_lake, 'lake': lake_state,
            'elapsed_s': elapsed + dt, 'ledger': ledger,
            'et_mm_land': np.ascontiguousarray(et_mm),
            'release_mm_land': np.ascontiguousarray(release_mm),
            'local_q_m3_s_active': np.ascontiguousarray(local_q.reshape(-1)[active]),
            'routed_q_m3_s_active': np.ascontiguousarray(accumulated['known_routed_q_m3_s']
                                                         .reshape(-1)[active]),
            'routing_policy': ROUTING_POLICY}


def soil_volume_m3(states_mm, cell_area_m2):
    """External soil/quick/slow volume of a land-state block (mm depth x area)."""
    states = np.asarray(states_mm)
    if states.ndim != 2 or states.shape[0] != 3 or not states.size:
        raise ValueError('soil states must be [3, cells]')
    if states.dtype.kind not in 'fiu' or not np.isfinite(states).all() or (states < 0).any():
        raise ValueError('finite nonnegative soil states required')
    area = _finite(cell_area_m2, 'cell area', maximum=MAX_CELL_AREA_M2, positive=True)
    return float(np.sum(states, dtype=np.float64)) * area / 1000.0


def water_account(*, rain_volume_m3, initial_soil_m3, final_soil_m3, initial_lake_m3,
                  final_lake_m3, et_volume_m3, channel_storage_m3=0.0):
    """External volume account with a pre-registered gate (m3, never mm).

    ``rain + initial soil + initial lake = ET + final soil + final lake (+ channel storage)``.
    Infiltration and percolation are internal transfers and never appear as external losses; the
    declared quasi-steady model has no channel storage.
    """
    rain = _finite(rain_volume_m3, 'rain volume')
    initial_soil = _finite(initial_soil_m3, 'initial soil volume')
    final_soil = _finite(final_soil_m3, 'final soil volume')
    initial_lake = _finite(initial_lake_m3, 'initial lake volume')
    final_lake = _finite(final_lake_m3, 'final lake volume')
    et = _finite(et_volume_m3, 'ET volume')
    channel = _finite(channel_storage_m3, 'channel storage')
    inputs = rain + initial_soil + initial_lake
    outputs = et + final_soil + final_lake + channel
    residual = inputs - outputs
    gate = BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * inputs
    return {'rain_m3': rain, 'initial_soil_m3': initial_soil, 'final_soil_m3': final_soil,
            'initial_lake_m3': initial_lake, 'final_lake_m3': final_lake, 'et_m3': et,
            'channel_storage_m3': channel, 'inputs_m3': inputs, 'outputs_m3': outputs,
            'residual_m3': residual, 'gate_m3': gate, 'closed': bool(abs(residual) <= gate),
            'units': 'm3',
            'semantics': ('rain + initial soil + initial lake = ET + final soil + final lake; '
                          'channel storage is zero under %s; infiltration and percolation are '
                          'internal transfers, never external losses' % ROUTING_POLICY)}


def run_finite_event(domain, initial_state, rain_mm_h_by_interval, *, dt_s, parameters,
                     on_step=None):
    """Run whole intervals of a fixed event; return per-step records and the closed account."""
    if not isinstance(domain, FiniteEventDomain):
        raise ValueError('prepared finite event domain required')
    if not isinstance(initial_state, dict) or set(initial_state) != {'soil_states_mm',
                                                                    'lake_volume_m3',
                                                                    'elapsed_s'}:
        raise ValueError('initial state must carry soil_states_mm/lake_volume_m3/elapsed_s')
    rain = np.asarray(rain_mm_h_by_interval)
    if rain.ndim != 1 or rain.size < 1 or rain.size > 100000:
        raise ValueError('one rain rate per interval required')
    if rain.dtype.kind != 'f' or not np.isfinite(rain).all() or (rain < 0).any() or (rain > 1000).any():
        raise ValueError('bounded finite interval rain required')
    states = initial_state['soil_states_mm']
    if not isinstance(states, np.ndarray) or states.dtype != np.float64 or not states.flags.writeable:
        raise ValueError('writable float64 soil states required')
    state = {'soil_states_mm': np.array(states, np.float64, copy=True),
             'lake_volume_m3': float(initial_state['lake_volume_m3']),
             'elapsed_s': float(initial_state['elapsed_s'])}
    initial = {'soil_states_mm': state['soil_states_mm'].copy(),
               'lake_volume_m3': state['lake_volume_m3'], 'elapsed_s': state['elapsed_s']}
    steps = []
    for index, value in enumerate(rain):
        outcome = advance_finite_event(domain, state['soil_states_mm'],
                                       state['lake_volume_m3'], float(value), dt_s=dt_s,
                                       parameters=parameters, elapsed_s=state['elapsed_s'])
        state = {'soil_states_mm': outcome['soil_states_mm'],
                 'lake_volume_m3': outcome['lake_volume_m3'],
                 'elapsed_s': outcome['elapsed_s']}
        record = {'interval': int(index), 'rain_mm_h': float(value),
                  'seconds_edges': [outcome['elapsed_s'] - float(dt_s), outcome['elapsed_s']],
                  'et_m3': outcome['ledger']['et_m3'],
                  'delivered_to_lake_m3': outcome['ledger']['delivered_to_lake_m3'],
                  'lake_volume_m3': outcome['lake_volume_m3'],
                  'lake_level_m': outcome['lake']['level_m'],
                  'lake_wet_cells': outcome['lake']['wet_cells'],
                  'lake_dry': outcome['lake']['dry'],
                  'ledger': outcome['ledger'],
                  'et_mm_land': outcome['et_mm_land'],
                  'release_mm_land': outcome['release_mm_land'],
                  'local_q_m3_s_active': outcome['local_q_m3_s_active'],
                  'routed_q_m3_s_active': outcome['routed_q_m3_s_active']}
        steps.append(record)
        if on_step is not None:
            on_step(record)
    delivered = sum(record['ledger']['delivered_to_lake_m3'] for record in steps)
    rain_volume = sum(record['ledger']['rain_total_m3'] for record in steps)
    et_volume = sum(record['ledger']['et_m3'] for record in steps)
    if abs(delivered - (state['lake_volume_m3'] - initial['lake_volume_m3'])) > (
            BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * max(rain_volume, 1.0)):
        raise ValueError('cumulative lake increment disagrees with the delivered total')
    account = water_account(rain_volume_m3=rain_volume,
                            initial_soil_m3=soil_volume_m3(initial['soil_states_mm'],
                                                           domain.cell_area_m2),
                            final_soil_m3=soil_volume_m3(state['soil_states_mm'],
                                                         domain.cell_area_m2),
                            initial_lake_m3=initial['lake_volume_m3'],
                            final_lake_m3=state['lake_volume_m3'], et_volume_m3=et_volume)
    return {'steps': steps, 'initial_state': initial, 'final_state': state,
            'rain_volume_m3': rain_volume, 'delivered_total_m3': delivered,
            'et_total_m3': et_volume, 'account': account,
            'routing_policy': ROUTING_POLICY, 'routing_semantics': ROUTING_SEMANTICS}
