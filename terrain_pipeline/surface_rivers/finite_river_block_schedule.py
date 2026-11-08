"""Block-scheduled finite event: per-block soil, cell-ready strict-D8 dispatch, real cross-block
port exchange, and checkpointed continuation in a fresh process.

Scope: the same finite support, the same frozen soil kernel, the same strict-D8 receiver and the
same ``quasi_steady_d8_no_channel_storage`` model as ``finite_river_event``. What is new here is
only *scheduling* and *persistence*: a spatial block computes its own soil slice, a **cell-level**
readiness count (never a block-level DAG - the block graph is cyclic on this support) drives the
strict-D8 routing, every cross-block edge transfers its flux exactly once as a recorded port
event, and a checkpoint can be reloaded by a new process and continued on the physical time axis.

No soil equation and no routing law is re-derived here: the per-cell increment is the same
``flow[dst] += flow[src]`` step that ``metric_network_accumulation`` performs, and the whole
scheduled result is gated against that whole-domain kernel. Blocks are never merged into a
whole-domain accumulate that is then sliced.
"""
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.climate_forcing import advance_soil
from terrain_pipeline.surface_rivers.finite_river_event import (
    BALANCE_ABSOLUTE_M3,
    BALANCE_RELATIVE,
    FiniteEventDomain,
    soil_volume_m3,
    water_account,
)

SCHEDULE_SCHEMA = 'finite-river-block-schedule-v1'
CHECKPOINT_SCHEMA = 'finite-river-block-checkpoint-v1'
DISPATCH_ORDERS = ('forward', 'reverse', 'shuffled')
MAX_BLOCKS = 8


def _sha_bytes(*chunks):
    digest = hashlib.sha256()
    for chunk in chunks:
        if isinstance(chunk, str):
            chunk = chunk.encode('utf-8')
        digest.update(chunk)
    return digest.hexdigest()


def _array_sha(array):
    array = np.ascontiguousarray(array)
    return _sha_bytes(str(array.shape).encode('ascii'), array.dtype.str.encode('ascii'),
                      array.tobytes())


def _finite(value, label, *, maximum=1e12, positive=False):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.floating, np.integer))
            or not math.isfinite(float(value)) or float(value) < 0 or float(value) > maximum
            or (positive and float(value) == 0.0)):
        raise ValueError('finite %srequired %s' % ('positive ' if positive else 'nonnegative ', label))
    return float(value)


# --------------------------------------------------------------------------- #
# block layout
# --------------------------------------------------------------------------- #
class BlockLayout:
    """Deterministic assignment of every domain cell to exactly one spatial block."""

    def __init__(self, block_of, block_count, *, axis, cuts, label):
        self.block_of = np.ascontiguousarray(block_of, np.int64)
        self.block_count = int(block_count)
        self.axis = axis
        self.cuts = cuts
        self.label = label
        self._positions = {}

    @property
    def cells(self):
        return int(self.block_of.size)

    def sizes(self):
        counts = np.bincount(self.block_of, minlength=self.block_count)
        return [int(value) for value in counts]

    def positions(self, block):
        block = int(block)
        if not 0 <= block < self.block_count:
            raise ValueError('block id out of range')
        if block not in self._positions:
            self._positions[block] = np.flatnonzero(self.block_of == block).astype(np.int64)
        return self._positions[block]

    def masks(self):
        return np.stack([self.block_of == block for block in range(self.block_count)])

    def sha256(self):
        return _array_sha(self.block_of)

    def metadata(self):
        return {'schema': SCHEDULE_SCHEMA + '-layout', 'label': self.label, 'axis': self.axis,
                'block_count': self.block_count, 'cells': self.cells, 'sizes': self.sizes(),
                'cuts': None if self.cuts is None else [int(value) for value in self.cuts],
                'block_of_sha256': self.sha256()}


def _domain_positions(domain):
    if not isinstance(domain, FiniteEventDomain):
        raise ValueError('prepared finite event domain required')
    return np.flatnonzero(domain.active_flat).astype(np.int64)


def layout_from_block_of(domain, block_of, *, block_count=None, label='explicit', cuts=None):
    """Adopt an explicit per-position block assignment; every block must be really non-empty."""
    positions = _domain_positions(domain)
    array = np.asarray(block_of)
    if array.shape != positions.shape or array.dtype.kind not in 'iu' or array.dtype == np.bool_:
        raise ValueError('block_of must be an integer array of one block id per domain cell')
    array = np.ascontiguousarray(array.astype(np.int64), np.int64)
    if (array < 0).any():
        raise ValueError('negative block id')
    count = int(array.max()) + 1 if array.size else 0
    if block_count is not None:
        if int(block_count) != count:
            raise ValueError('block id range disagrees with the declared block count')
        count = int(block_count)
    if not 1 <= count <= MAX_BLOCKS:
        raise ValueError('between 1 and %d blocks required' % MAX_BLOCKS)
    if not np.array_equal(np.unique(array), np.arange(count)):
        missing = sorted(set(range(count)) - set(int(value) for value in np.unique(array)))
        raise ValueError('every declared block must be non-empty; empty %s' % missing)
    return BlockLayout(array, count, axis='explicit' if cuts is None else 'row_bands',
                       cuts=cuts, label=label)


def prepare_block_layout(domain, block_count, *, axis='row_bands', label=None):
    """Split the finite support into ``block_count`` row bands of the reach's own row range."""
    if type(block_count) is not int or not 1 <= block_count <= MAX_BLOCKS:
        raise ValueError('between 1 and %d blocks required' % MAX_BLOCKS)
    if axis != 'row_bands':
        raise ValueError('only row_bands layouts are supported')
    positions = _domain_positions(domain)
    rows = positions // int(domain.grid_shape[1])
    low, high = int(rows.min()), int(rows.max())
    if high - low + 1 < block_count:
        raise ValueError('the support has fewer rows than declared blocks')
    cuts = np.linspace(low, high + 1, block_count + 1).astype(np.int64)
    block_of = np.digitize(rows, cuts[1:-1]).astype(np.int64)
    return layout_from_block_of(domain, block_of, block_count=block_count,
                                label=label or ('row_bands-%d' % block_count),
                                cuts=cuts)


def check_layout_cover(layout, masks):
    """Reject a membership matrix that overlaps, misses cells or disagrees with the layout."""
    matrix = np.asarray(masks)
    if matrix.dtype != np.bool_ or matrix.shape != (layout.block_count, layout.cells):
        raise ValueError('block membership must be boolean [blocks, cells]')
    per_cell = matrix.sum(axis=0)
    if np.any(per_cell == 0):
        raise ValueError('block union misses %d cells' % int((per_cell == 0).sum()))
    if np.any(per_cell > 1):
        raise ValueError('blocks overlap on %d cells' % int((per_cell > 1).sum()))
    if np.any(np.bincount(layout.block_of, minlength=layout.block_count) != matrix.sum(axis=1)):
        raise ValueError('block sizes disagree with the membership matrix')
    return True


# --------------------------------------------------------------------------- #
# port exchange ledger
# --------------------------------------------------------------------------- #
class PortExchange:
    """Every cross-block transfer is recorded once; a repeated delivery is refused."""

    def __init__(self):
        self._records = []
        self._seen = set()

    def record(self, interval, wave, source, target, q_m3_s, dt_s):
        source = int(source)
        key = (int(interval), source)
        if key in self._seen:
            raise ValueError('port event from cell %d in interval %d delivered twice'
                             % (source, int(interval)))
        self._seen.add(key)
        self._records.append((int(interval), int(wave), source, int(target), float(q_m3_s),
                              float(q_m3_s) * float(dt_s)))
        return key

    def arrays(self):
        if not self._records:
            empty = np.zeros(0, np.int64)
            return {'interval': empty, 'wave': empty.copy(), 'source': empty.copy(),
                    'target': empty.copy(), 'volume_m3': np.zeros(0, np.float64)}
        table = list(zip(*self._records))
        return {'interval': np.asarray(table[0], np.int64), 'wave': np.asarray(table[1], np.int64),
                'source': np.asarray(table[2], np.int64),
                'target': np.asarray(table[3], np.int64),
                'q_m3_s': np.asarray(table[4], np.float64),
                'volume_m3': np.asarray(table[5], np.float64)}

    def total_volume_m3(self, interval=None):
        arrays = self.arrays()
        if arrays['volume_m3'].size == 0:
            return 0.0
        if interval is None:
            return float(arrays['volume_m3'].sum())
        return float(arrays['volume_m3'][arrays['interval'] == int(interval)].sum())


# --------------------------------------------------------------------------- #
# schedule
# --------------------------------------------------------------------------- #
class BlockSchedule:
    """Per-block execution of one finite event with cell-level readiness routing."""

    def __init__(self, domain, layout, *, dispatch_order='forward'):
        if not isinstance(domain, FiniteEventDomain):
            raise ValueError('prepared finite event domain required')
        if not isinstance(layout, BlockLayout):
            raise ValueError('prepared block layout required')
        if dispatch_order not in DISPATCH_ORDERS:
            raise ValueError('dispatch order must be one of %s' % (DISPATCH_ORDERS,))
        positions = _domain_positions(domain)
        if layout.cells != positions.size:
            raise ValueError('layout does not cover this domain')
        self.domain = domain
        self.layout = layout
        self.dispatch_order = dispatch_order
        self.cells = int(positions.size)
        receiver = domain.receiver_active.reshape(-1)
        onward = receiver[positions]
        if np.any(onward >= receiver.size) or np.any(onward < -1):
            raise ValueError('receiver index outside the grid')
        position_of_cell = -np.ones(receiver.size, np.int64)
        position_of_cell[positions] = np.arange(self.cells)
        successor = np.where(onward >= 0, position_of_cell[np.clip(onward, 0, None)], -1)
        if np.any(onward >= 0) and np.any(successor[onward >= 0] < 0):
            raise ValueError('an active cell routes outside the prepared domain')
        self.successor = successor.astype(np.int64)
        self.donor_count = np.bincount(self.successor[self.successor >= 0],
                                       minlength=self.cells).astype(np.int64)
        terminal_positions = np.flatnonzero(self.successor < 0)
        if terminal_positions.size != 1:
            raise ValueError('exactly one retained terminal required')
        self.terminal_position = int(terminal_positions[0])
        land_cells = np.asarray(domain.land_flat, np.int64)
        self.land_state_index = -np.ones(self.cells, np.int64)
        land_positions = np.searchsorted(positions, land_cells)
        if land_positions.size and not np.array_equal(positions[land_positions], land_cells):
            raise ValueError('land cells are not part of this domain')
        self.land_state_index[land_positions] = np.arange(land_positions.size)
        member_positions = np.searchsorted(positions, np.asarray(domain.member_flat, np.int64))
        self.member_positions = np.ascontiguousarray(member_positions)
        self.member_mask = np.zeros(self.cells, bool)
        self.member_mask[self.member_positions] = True
        block_of = layout.block_of
        cross = (self.successor >= 0) & (block_of[np.clip(self.successor, 0, None)] != block_of)
        self.cross_positions = np.flatnonzero(cross)
        self.cross_sources = self.cross_positions.astype(np.int64)
        self.cross_targets = self.successor[self.cross_positions].astype(np.int64)
        self.cross_src_block = block_of[self.cross_positions]
        self.cross_dst_block = block_of[self.cross_targets]
        self.block_permutation = self._permutation()
        self.land_by_block = [self._land_positions(block) for block in range(layout.block_count)]

    # -- layout helpers ---------------------------------------------------
    def _land_positions(self, block):
        positions = self.layout.positions(block)
        index = self.land_state_index[positions]
        return np.ascontiguousarray(positions[index >= 0])

    def _permutation(self):
        count = self.layout.block_count
        if self.dispatch_order == 'forward':
            return list(range(count))
        if self.dispatch_order == 'reverse':
            return list(range(count - 1, -1, -1))
        seed = _sha_bytes('finite-river-block-dispatch', str(count), self.layout.sha256())
        order = list(range(count))
        state = int(seed[:16], 16)
        for index in range(count - 1, 0, -1):
            state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            swap = state % (index + 1)
            order[index], order[swap] = order[swap], order[index]
        if order == sorted(order) and count > 1:
            # a fixed pseudo-random order must be a real change, not the identity by accident
            order = order[1:] + order[:1]
        return order

    def metadata(self):
        return {'schema': SCHEDULE_SCHEMA, 'dispatch_order': self.dispatch_order,
                'block_permutation': [int(value) for value in self.block_permutation],
                'block_count': self.layout.block_count, 'layout': self.layout.metadata(),
                'cells': self.cells, 'terminal_position': self.terminal_position,
                'land_cells': int((self.land_state_index >= 0).sum()),
                'lake_bed_cells': int(self.member_mask.sum()),
                'cross_block_edges': int(self.cross_positions.size),
                'cross_block_edge_pairs': self.cross_pair_counts(),
                'max_donors_per_cell': int(self.donor_count.max()) if self.cells else 0}

    def cross_pair_counts(self):
        pairs = {}
        for src, dst in zip(self.cross_src_block.tolist(), self.cross_dst_block.tolist()):
            pairs['%d->%d' % (src, dst)] = pairs.get('%d->%d' % (src, dst), 0) + 1
        return {key: pairs[key] for key in sorted(pairs)}

    def identity(self):
        domain = self.domain
        return {'schedule_schema': SCHEDULE_SCHEMA,
                'schedule_module_sha256': _array_sha_spec(__file__),
                'domain': {'grid_shape': [int(value) for value in domain.grid_shape],
                           'cell_area_m2': domain.cell_area_m2,
                           'active_mask_sha256': _array_sha(domain.active_mask),
                           'receiver_sha256': _array_sha(domain.receiver_active),
                           'terminal_kinds_sha256': _array_sha(domain.terminal_kinds),
                           'land_flat_sha256': _array_sha(domain.land_flat),
                           'member_flat_sha256': _array_sha(domain.member_flat),
                           'lake_bed_levels_sha256': _array_sha(domain.lake.bed_levels_m),
                           'safe_level_m': domain.safe_level_m,
                           'safe_capacity_m3': domain.safe_capacity_m3},
                'layout_sha256': self.layout.sha256(), 'block_count': self.layout.block_count,
                'dispatch_order': self.dispatch_order,
                'block_permutation': [int(value) for value in self.block_permutation]}



def _array_sha_spec(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# one interval
# --------------------------------------------------------------------------- #
def advance_block_event(schedule, soil_states_mm, lake_volume_m3, rain_mm_h, *, dt_s,
                        parameters, elapsed_s, interval_index):
    """Advance one interval with per-block soil and blocked, port-exchanging D8 routing.

    Inputs are never modified. The wave set is the cell-level readiness frontier; within a wave the
    sources are dispatched block by block in this schedule's order (so the dispatch order is real),
    and the increments are then merged per receiving block in ascending global cell order, which is
    the exact order the whole-domain accumulator uses for every target. A cell forwards at most
    once per interval, so no event can add the same water twice; cross-block transfers are recorded
    in a ``PortExchange`` ledger.
    """
    if not isinstance(schedule, BlockSchedule):
        raise ValueError('prepared block schedule required')
    if not isinstance(parameters, RunoffParameters):
        raise ValueError('explicit RunoffParameters required')
    parameters.__post_init__()
    domain = schedule.domain
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
    index = int(interval_index)
    if index < 0:
        raise ValueError('interval index must be nonnegative')
    dt = float(dt_s)
    hours = dt / 3600.0
    area = domain.cell_area_m2
    cells = schedule.cells
    states_next = np.array(states, np.float64, copy=True)
    release_mm = np.zeros(cells, np.float64)
    et_mm = np.zeros(cells, np.float64)
    change_mm = np.zeros(cells, np.float64)
    block_soil_seconds = {}
    for block in schedule.block_permutation:
        positions = schedule.land_by_block[block]
        if not positions.size:
            block_soil_seconds[block] = 0.0
            continue
        state_index = schedule.land_state_index[positions]
        rain_block = np.full(positions.size, rain, np.float64)
        updated, release, et, change = advance_soil(rain_block, states[:, state_index], dt_s=dt,
                                                    parameters=parameters)
        states_next[:, state_index] = updated
        release_mm[positions] = release
        et_mm[positions] = et
        change_mm[positions] = change
        block_soil_seconds[block] = 0.0
    depth_m3_per_cell = rain * hours * area / 1000.0
    local_q = np.zeros(cells, np.float64)
    land_mask = schedule.land_state_index >= 0
    local_q[land_mask] = release_mm[land_mask] * area / 1000.0 / dt
    local_q[schedule.member_mask] = depth_m3_per_cell / dt
    flow = local_q.copy()
    dirty = np.zeros(cells, bool)
    forwarded = np.zeros(cells, bool)
    pending = schedule.donor_count.copy()
    frontier = np.flatnonzero(pending == 0)
    exchange = PortExchange()
    block_of = schedule.layout.block_of
    successor = schedule.successor
    waves = 0
    events = 0
    cross_events = 0
    local_by_block = np.zeros(schedule.layout.block_count, np.float64)
    port_in_by_block = np.zeros(schedule.layout.block_count, np.float64)
    port_out_by_block = np.zeros(schedule.layout.block_count, np.float64)
    for block in range(schedule.layout.block_count):
        local_by_block[block] = float(local_q[block_of == block].sum()) * dt
    while frontier.size:
        waves += 1
        order = []
        for block in schedule.block_permutation:
            subset = frontier[block_of[frontier] == block]
            if subset.size:
                order.append(subset)
        dispatched = np.concatenate(order) if order else np.zeros(0, np.int64)
        if forwarded[dispatched].any():
            raise ValueError('a cell was scheduled twice inside one interval')
        forwarded[dispatched] = True
        sources = dispatched[successor[dispatched] >= 0]
        targets = successor[sources]
        if sources.size:
            events += int(sources.size)
            flux = flow[sources]
            source_block = block_of[sources]
            target_block = block_of[targets]
            cross = source_block != target_block
            cross_events += int(cross.sum())
            if cross.any():
                for source, target, value in zip(sources[cross].tolist(),
                                                 targets[cross].tolist(), flux[cross].tolist()):
                    exchange.record(index, waves, source, target, value, dt)
                port_out_by_block += np.bincount(source_block[cross], weights=flux[cross],
                                                 minlength=schedule.layout.block_count) * dt
                port_in_by_block += np.bincount(target_block[cross], weights=flux[cross],
                                                minlength=schedule.layout.block_count) * dt
            for block in range(schedule.layout.block_count):
                selected = target_block == block
                if not selected.any():
                    continue
                order_within = np.argsort(sources[selected], kind='stable')
                destination = targets[selected][order_within]
                value = flux[selected][order_within]
                np.add.at(flow, destination, value)
                np.logical_or.at(dirty, destination, dirty[sources[selected][order_within]])
            if not np.isfinite(flow[targets]).all():
                raise ValueError('routed known discharge overflows float64')
        np.subtract.at(pending, targets, 1)
        frontier = np.unique(targets[pending[targets] == 0])
    if int(forwarded.sum()) != cells:
        raise ValueError('receiver graph contains a cycle: %d of %d cells never became ready'
                         % (cells - int(forwarded.sum()), cells))
    terminal_flow = float(flow[schedule.terminal_position])
    delivered_m3 = terminal_flow * dt
    next_lake = lake + delivered_m3
    if next_lake > domain.safe_capacity_m3:
        raise ValueError('lake inventory %.17g m3 would exceed the declared safe capacity %.17g m3; '
                         'the whole interval is refused' % (next_lake, domain.safe_capacity_m3))
    lake_state = domain.lake_state(next_lake)
    terminal_block = int(block_of[schedule.terminal_position])
    terminal_by_block = np.zeros(schedule.layout.block_count, np.float64)
    terminal_by_block[terminal_block] = delivered_m3
    net = local_by_block + port_in_by_block - port_out_by_block - terminal_by_block
    gate = BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * max(float(local_by_block.sum()), 1.0)
    worst = float(np.abs(net).max()) if net.size else 0.0
    if worst > gate:
        raise ValueError('per-block balance fails by %.17g m3 (gate %.17g)' % (worst, gate))
    land_volume = float(release_mm[land_mask].sum()) * area / 1000.0
    lake_rain_m3 = float(depth_m3_per_cell) * int(schedule.member_mask.sum())
    land_rain_m3 = float(depth_m3_per_cell) * int(land_mask.sum())
    ledger = {
        'interval_index': index,
        'rain_land_m3': land_rain_m3,
        'rain_lake_m3': lake_rain_m3,
        'rain_total_m3': land_rain_m3 + lake_rain_m3,
        'et_m3': float(et_mm[land_mask].sum()) * area / 1000.0,
        'soil_change_m3': float(change_mm[land_mask].sum()) * area / 1000.0,
        'land_release_m3': land_volume,
        'local_input_m3': float(local_q.sum()) * dt,
        'delivered_to_lake_m3': delivered_m3,
        'lake_change_m3': next_lake - lake,
        'channel_storage_m3': 0.0,
        'port_exchange_m3': exchange.total_volume_m3(),
        'local_by_block_m3': [float(value) for value in local_by_block],
        'port_in_by_block_m3': [float(value) for value in port_in_by_block],
        'port_out_by_block_m3': [float(value) for value in port_out_by_block],
        'terminal_by_block_m3': [float(value) for value in terminal_by_block],
        'block_balance_m3': [float(value) for value in net],
        'land_balance_residual_m3': land_rain_m3 - float(et_mm[land_mask].sum()) * area / 1000.0
        - land_volume - float(change_mm[land_mask].sum()) * area / 1000.0,
    }
    return {'interval_index': index, 'soil_states_mm': states_next, 'lake_volume_m3': next_lake,
            'lake': lake_state, 'elapsed_s': elapsed + dt, 'ledger': ledger,
            'local_q_m3_s': local_q, 'routed_q_m3_s': flow,
            'et_mm_land': _land_ordered(et_mm, schedule, land_mask),
            'release_mm_land': _land_ordered(release_mm, schedule, land_mask),
            'complete_mask': ~dirty, 'exchange': exchange.arrays(),
            'dispatch': {'order': schedule.dispatch_order,
                         'block_permutation': [int(value) for value in schedule.block_permutation],
                         'waves': waves, 'events': events, 'cross_events': cross_events,
                         'event_stream_sha256': _event_stream_sha(exchange.arrays(), flow)}}


def _land_ordered(values, schedule, land_mask):
    """Re-index a per-cell array into the domain's land-state column order."""
    output = np.zeros(int(land_mask.sum()), np.float64)
    output[schedule.land_state_index[land_mask]] = values[land_mask]
    return np.ascontiguousarray(output)


def _event_stream_sha(exchange_arrays, flow):
    digest = hashlib.sha256()
    for key in ('interval', 'wave', 'source', 'target', 'q_m3_s'):
        digest.update(np.ascontiguousarray(exchange_arrays[key]).tobytes())
    digest.update(np.ascontiguousarray(flow).tobytes())
    return digest.hexdigest()


def run_block_event(schedule, initial_state, rain_mm_h_by_interval, *, dt_s, parameters,
                    start_index=0, on_step=None):
    """Run whole intervals from a declared state; returns per-step records and the closed account."""
    if not isinstance(schedule, BlockSchedule):
        raise ValueError('prepared block schedule required')
    if (not isinstance(initial_state, dict)
            or set(initial_state) != {'soil_states_mm', 'lake_volume_m3', 'elapsed_s'}):
        raise ValueError('initial state must carry soil_states_mm/lake_volume_m3/elapsed_s')
    rain = np.asarray(rain_mm_h_by_interval)
    if rain.ndim != 1 or rain.size > 100000:
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
    for offset, value in enumerate(rain):
        index = int(start_index) + int(offset)
        outcome = advance_block_event(schedule, state['soil_states_mm'],
                                     state['lake_volume_m3'], float(value), dt_s=dt_s,
                                     parameters=parameters, elapsed_s=state['elapsed_s'],
                                     interval_index=index)
        state = {'soil_states_mm': outcome['soil_states_mm'],
                 'lake_volume_m3': outcome['lake_volume_m3'],
                 'elapsed_s': outcome['elapsed_s']}
        steps.append(outcome)
        if on_step is not None:
            on_step(outcome)
    delivered = sum(step['ledger']['delivered_to_lake_m3'] for step in steps)
    rain_volume = sum(step['ledger']['rain_total_m3'] for step in steps)
    et_volume = sum(step['ledger']['et_m3'] for step in steps)
    account = water_account(rain_volume_m3=rain_volume,
                            initial_soil_m3=soil_volume_m3(initial['soil_states_mm'],
                                                           schedule.domain.cell_area_m2),
                            final_soil_m3=soil_volume_m3(state['soil_states_mm'],
                                                        schedule.domain.cell_area_m2),
                            initial_lake_m3=initial['lake_volume_m3'],
                            final_lake_m3=state['lake_volume_m3'], et_volume_m3=et_volume)
    return {'steps': steps, 'initial_state': initial, 'final_state': state,
            'rain_volume_m3': rain_volume, 'delivered_total_m3': delivered,
            'et_total_m3': et_volume, 'account': account,
            'start_index': int(start_index), 'intervals': int(rain.size)}


# --------------------------------------------------------------------------- #
# checkpoint
# --------------------------------------------------------------------------- #
CHECKPOINT_FILES = ('state.npz', 'manifest.json')
CUMULATIVE_KEYS = ('rain_m3', 'et_m3', 'delivered_m3', 'soil_volume_m3')
INITIAL_KEYS = ('soil_m3', 'lake_m3')


def _checkpoint_identity(schedule, dt_s, parameters, rain_sequence, protocol_sha256):
    return {'schema': CHECKPOINT_SCHEMA,
            'schedule': schedule.identity(),
            'dt_s': float(dt_s),
            'parameters': {key: float(value) for key, value in
                           vars(parameters).items()},
            'parameters_sha256': _sha_bytes(json.dumps({key: float(value) for key, value in
                                                        vars(parameters).items()},
                                                       sort_keys=True)),
            'rain_sequence_sha256': _array_sha(np.asarray(rain_sequence, np.float64)),
            'rain_sequence': [float(value) for value in np.asarray(rain_sequence, np.float64)],
            'protocol_sha256': protocol_sha256,
            'model': 'quasi_steady_d8_no_channel_storage',
            'model_note': ('no channel storage and no in-transit water exist under this model, so a '
                           'checkpoint needs no in-transit state; a model with channel storage '
                           'would need a new checkpoint schema')}


def _checkpoint_totals(*, schedule, states, lake, index, dt_s, rain_sequence, cumulative,
                       initial):
    """Bind the declared totals to the *actual* state and the declared forcing prefix.

    A checkpoint that merely stores four self-declared numbers is worthless: here every total is
    re-derived from the stored soil block, the stored lake inventory and ``rain[:index]``, and the
    prefix external account must close. Non-zero starting inventories must be declared explicitly
    (``initial``) instead of being assumed zero.
    """
    domain = schedule.domain
    if not isinstance(cumulative, dict) or set(cumulative) != set(CUMULATIVE_KEYS):
        raise ValueError('cumulative must carry exactly %s' % (CUMULATIVE_KEYS,))
    if not isinstance(initial, dict) or set(initial) != set(INITIAL_KEYS):
        raise ValueError('initial totals must carry exactly %s' % (INITIAL_KEYS,))
    values = {key: _finite(cumulative[key], 'cumulative ' + key) for key in CUMULATIVE_KEYS}
    started = {key: _finite(initial[key], 'initial ' + key) for key in INITIAL_KEYS}
    rain = np.asarray(rain_sequence, np.float64)
    if rain.ndim != 1 or rain.size < index:
        raise ValueError('the declared rain sequence is shorter than the interval index')
    expected_rain = (float(rain[:index].sum()) * float(dt_s) / 3600.0
                     * domain.cell_area_m2 / 1000.0 * domain.active_cells)
    if abs(values['rain_m3'] - expected_rain) > (BALANCE_ABSOLUTE_M3
                                                + BALANCE_RELATIVE * max(expected_rain, 1.0)):
        raise ValueError('cumulative rain %.17g disagrees with the forcing prefix %.17g'
                         % (values['rain_m3'], expected_rain))
    actual_soil = soil_volume_m3(states, domain.cell_area_m2)
    if abs(values['soil_volume_m3'] - actual_soil) > (BALANCE_ABSOLUTE_M3
                                                     + BALANCE_RELATIVE * max(actual_soil, 1.0)):
        raise ValueError('cumulative soil volume %.17g disagrees with the stored soil state %.17g'
                         % (values['soil_volume_m3'], actual_soil))
    if abs(values['delivered_m3'] - (lake - started['lake_m3'])) > (BALANCE_ABSOLUTE_M3
                                                                   + BALANCE_RELATIVE
                                                                   * max(lake, 1.0)):
        raise ValueError('cumulative delivered %.17g disagrees with lake %.17g minus the declared '
                         'initial lake %.17g'
                         % (values['delivered_m3'], lake, started['lake_m3']))
    inputs = values['rain_m3'] + started['soil_m3'] + started['lake_m3']
    outputs = values['et_m3'] + actual_soil + lake
    residual = inputs - outputs
    if abs(residual) > BALANCE_ABSOLUTE_M3 + BALANCE_RELATIVE * inputs:
        raise ValueError('the checkpoint prefix external account fails by %.17g m3 (inputs %.17g)'
                         % (residual, inputs))
    return values, started, actual_soil


def _checkpoint_state(schedule, states, lake, elapsed, index, dt_s, parameters):
    """Validate a checkpoint state against the prepared domain, never only against itself."""
    domain = schedule.domain
    if (isinstance(dt_s, bool) or not isinstance(dt_s, (int, float))
            or not math.isfinite(float(dt_s)) or not 0 < float(dt_s) <= 3600):
        raise ValueError('positive physical timestep of at most 3600 s required')
    if type(index) is not int or index < 0:
        raise ValueError('the checkpoint interval index must be a nonnegative integer')
    states = np.asarray(states)
    if states.dtype != np.float64 or states.shape != (3, domain.land_cells):
        raise ValueError('checkpoint soil states must be float64 [3, %d]' % domain.land_cells)
    if not np.isfinite(states).all() or (states < 0).any():
        raise ValueError('checkpoint soil states must be finite and nonnegative')
    if (states[0] > parameters.soil_capacity_mm).any():
        raise ValueError('checkpoint soil exceeds the prescribed capacity')
    lake = _finite(lake, 'lake inventory')
    if lake > domain.safe_capacity_m3:
        raise ValueError('checkpoint lake inventory exceeds the declared safe capacity')
    elapsed = _finite(elapsed, 'elapsed physical time')
    if abs(elapsed - index * float(dt_s)) > 1e-9:
        raise ValueError('checkpoint elapsed time disagrees with its interval index')
    return lake, elapsed


def save_checkpoint(directory, *, schedule, state, interval_index, cumulative, initial,
                    dt_s, parameters, rain_sequence, protocol_sha256=None):
    """Publish a complete checkpoint atomically; an existing directory is refused, never replaced.

    ``cumulative`` must carry exactly ``rain_m3``/``et_m3``/``delivered_m3``/``soil_volume_m3`` and
    ``initial`` exactly ``soil_m3``/``lake_m3``; all of them are re-derived from the stored state
    and the declared forcing prefix before anything is written, so a checkpoint cannot declare
    totals that its own state contradicts.
    """
    if not isinstance(schedule, BlockSchedule):
        raise ValueError('prepared block schedule required')
    if (not isinstance(parameters, RunoffParameters)
            or parameters != parameters):
        raise ValueError('explicit RunoffParameters required')
    parameters.__post_init__()
    if (not isinstance(state, dict)
            or set(state) != {'soil_states_mm', 'lake_volume_m3', 'elapsed_s'}):
        raise ValueError('checkpoint state must carry soil_states_mm/lake_volume_m3/elapsed_s')
    if type(interval_index) is not int:
        raise ValueError('the checkpoint interval index must be an integer')
    rain = np.asarray(rain_sequence, np.float64)
    if interval_index < 0 or interval_index > int(rain.size):
        raise ValueError('interval index outside the declared forcing sequence')
    lake, elapsed = _checkpoint_state(schedule, state['soil_states_mm'],
                                      state['lake_volume_m3'], state['elapsed_s'],
                                      interval_index, dt_s, parameters)
    values, started, _ = _checkpoint_totals(schedule=schedule,
                                            states=np.asarray(state['soil_states_mm']),
                                            lake=lake, index=interval_index, dt_s=dt_s,
                                            rain_sequence=rain, cumulative=cumulative,
                                            initial=initial)
    states = np.ascontiguousarray(np.asarray(state['soil_states_mm'], np.float64))
    target = Path(directory)
    if target.exists():
        raise FileExistsError('checkpoint directory already exists: %s' % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.checkpoint-', dir=target.parent))
    try:
        payload = {'soil_states_mm': states,
                   'lake_volume_m3': np.array([lake], np.float64),
                   'elapsed_s': np.array([elapsed], np.float64)}
        state_path = temporary / CHECKPOINT_FILES[0]
        np.savez_compressed(state_path, **payload)
        manifest = {'identity': _checkpoint_identity(schedule, dt_s, parameters, rain,
                                                     protocol_sha256),
                    'interval_index': interval_index, 'elapsed_s': elapsed,
                    'lake_volume_m3': lake,
                    'soil_states_shape': [int(value) for value in states.shape],
                    'state_sha256': hashlib.sha256(state_path.read_bytes()).hexdigest(),
                    'cumulative': values, 'initial': started}
        (temporary / CHECKPOINT_FILES[1]).write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + '\n',
            encoding='utf-8')
        for name in CHECKPOINT_FILES:
            if not (temporary / name).is_file():
                raise ValueError('checkpoint member was not written: %s' % name)
        if target.exists():
            raise FileExistsError('checkpoint directory appeared while writing: %s' % target)
        # The target does not exist, so this is a publish, never an overwrite.
        os.rename(str(temporary), str(target))
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {'directory': str(target), 'interval_index': interval_index,
            'state_sha256': hashlib.sha256((target / CHECKPOINT_FILES[0]).read_bytes()).hexdigest(),
            'lake_volume_m3': lake, 'elapsed_s': elapsed,
            'cumulative': values, 'initial': started}


def load_checkpoint(directory, *, schedule, expected_interval_index, dt_s, parameters,
                    rain_sequence, protocol_sha256=None):
    """Load a checkpoint for this exact schedule; identity, index and totals are all re-checked."""
    if not isinstance(schedule, BlockSchedule):
        raise ValueError('prepared block schedule required')
    parameters.__post_init__()
    directory = Path(directory)
    for name in CHECKPOINT_FILES:
        if not (directory / name).is_file():
            raise FileNotFoundError('checkpoint member missing: %s' % name)
    manifest = json.loads((directory / CHECKPOINT_FILES[1]).read_text(encoding='utf-8'))
    required = {'identity', 'interval_index', 'elapsed_s', 'lake_volume_m3', 'soil_states_shape',
                'state_sha256', 'cumulative', 'initial'}
    if set(manifest) != required:
        raise ValueError('checkpoint manifest keys are not the declared set')
    expected_identity = _checkpoint_identity(schedule, dt_s, parameters,
                                             np.asarray(rain_sequence, np.float64),
                                             protocol_sha256)
    if manifest['identity'] != expected_identity:
        differing = [key for key in expected_identity
                     if manifest['identity'].get(key) != expected_identity[key]]
        raise ValueError('checkpoint identity mismatch: %s' % differing)
    raw = (directory / CHECKPOINT_FILES[0]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['state_sha256']:
        raise ValueError('checkpoint state digest mismatch')
    index = manifest['interval_index']
    if type(index) is not int:
        raise ValueError('the checkpoint interval index must be a JSON integer')
    if index != int(expected_interval_index):
        raise ValueError('checkpoint resumes at interval %d but %d was requested'
                         % (index, int(expected_interval_index)))
    with np.load(directory / CHECKPOINT_FILES[0], allow_pickle=False) as archive:
        if set(archive.files) != {'soil_states_mm', 'lake_volume_m3', 'elapsed_s'}:
            raise ValueError('checkpoint state members are not the declared set')
        states = np.array(archive['soil_states_mm'], np.float64)
        lake = float(np.asarray(archive['lake_volume_m3'], np.float64).reshape(-1)[0])
        elapsed = float(np.asarray(archive['elapsed_s'], np.float64).reshape(-1)[0])
    if list(states.shape) != list(manifest['soil_states_shape']):
        raise ValueError('checkpoint soil shape disagrees with its own manifest')
    lake, elapsed = _checkpoint_state(schedule, states, lake, elapsed, index, dt_s, parameters)
    for archived, declared, label in ((lake, manifest['lake_volume_m3'], 'lake'),
                                      (elapsed, manifest['elapsed_s'], 'elapsed')):
        declared_value = _finite(declared, 'manifest ' + label)
        if archived != declared_value:
            raise ValueError('checkpoint %s value disagrees with the manifest' % label)
    values, started, _ = _checkpoint_totals(schedule=schedule, states=states, lake=lake,
                                            index=index, dt_s=dt_s,
                                            rain_sequence=np.asarray(rain_sequence, np.float64),
                                            cumulative=manifest['cumulative'],
                                            initial=manifest['initial'])
    state = {'soil_states_mm': states, 'lake_volume_m3': lake, 'elapsed_s': elapsed}
    return {'state': state, 'interval_index': index, 'cumulative': values, 'initial': started,
            'manifest': manifest}
