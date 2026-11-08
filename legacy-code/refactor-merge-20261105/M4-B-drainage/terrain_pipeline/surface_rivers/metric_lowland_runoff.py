"""Illustrative monthly runoff/storage on an immutable, finite terrain DAG."""

from dataclasses import asdict, dataclass

import numpy as np
from numba import njit
from scipy.ndimage import maximum_filter, minimum_filter

from .metric_noise_forcing import MONTH_DAYS

ALGORITHM = "td_lowland_runoff_channel_separation_v1"
OBJECT_FLAGS = {"river": 1, "wetland": 2, "shallow_lake": 4,
                "seasonal_swale": 8, "floodplain": 16}
MONTH_SECONDS = MONTH_DAYS * 86400.
YEAR_SECONDS = float(MONTH_SECONDS.sum())


@dataclass(frozen=True)
class LowlandRunoffConfig:
    relief_radius_m: float = 300.
    lowland_relief_m: float = 20.
    lowland_slope: float = .025
    upland_initiation_area_m2: float = 1000000.
    lowland_initiation_area_m2: float = 4000000.
    channel_q_threshold_m3_s: float = .015
    persistent_months: int = 8
    seasonal_months: int = 2
    simulation_years: int = 3
    shallow_lake_min_raise_m: float = .5
    shallow_lake_max_depth_m: float = 4.
    wetland_min_raise_m: float = .03
    floodplain_storage_depth_m: float = .04
    swale_storage_depth_m: float = .02
    wetland_storage_depth_m: float = .12
    monthly_release_fraction: float = .35
    monthly_evaporation_depth_m: float = .015
    floodplain_max_dag_distance_m: float = 300.
    floodplain_max_height_above_channel_m: float = 1.


@njit(cache=True)
def _accumulate(local, receiver, order):
    routed = local.astype(np.float64)
    for cell in order:
        target = receiver[cell]
        if target >= 0:
            routed[target] += routed[cell]
    return routed


@njit(cache=True)
def _monthly_storage(local, receiver, order, capacity, storage, evaporation,
                     release_fraction, perimeter):
    inflow = local.astype(np.float64)
    routed = np.zeros(local.size, np.float64)
    et_cells = np.zeros(local.size, np.float64)
    evaporated = 0.
    released = 0.
    overflow_total = 0.
    unknown = 0.
    unresolved = 0.
    for cell in order:
        water = inflow[cell] + storage[cell]
        if capacity[cell] > 0.:
            # Overflow bypasses retention; evaporation and release act on the
            # finite retained reservoir, including this month's incoming water.
            overflow = max(0., water - capacity[cell])
            retained = min(water, capacity[cell])
            loss = min(retained, evaporation)
            retained -= loss
            release = retained * release_fraction
            storage[cell] = retained - release
            out = overflow + release
            evaporated += loss
            et_cells[cell] = loss
            released += release
            overflow_total += overflow
        else:
            out = water
            storage[cell] = 0.
        routed[cell] = out
        target = receiver[cell]
        if target >= 0:
            inflow[target] += out
        elif perimeter[cell]:
            unknown += out
        else:
            unresolved += out
    return routed, et_cells, evaporated, released, overflow_total, unknown, unresolved


class EventRunoffRouter:
    """Finite saved DAG state, with immutable classification owned by caller.

    Each step admits its local runoff, then routes upstream to downstream in
    the same step. This bucket approximation has no channel travel-time model.
    Monthly rates use an explicit reference month of 30 days by default.
    """

    def __init__(self, receiver, topological_order, capacity_m3, initial_storage_m3,
                 perimeter_mask, spacing_m, *, config=None):
        self.config = LowlandRunoffConfig() if config is None else config
        if not isinstance(self.config, LowlandRunoffConfig):
            raise ValueError("LowlandRunoffConfig required")
        capacity = np.asarray(capacity_m3, np.float64)
        storage = np.asarray(initial_storage_m3, np.float64)
        receiver = np.asarray(receiver)
        order = np.asarray(topological_order)
        perimeter = np.asarray(perimeter_mask)
        if (capacity.ndim not in (1, 2) or not 1 <= capacity.size <= 4_000_000
                or storage.shape != capacity.shape or perimeter.shape != capacity.shape
                or perimeter.dtype.kind != "b"
                or receiver.size != capacity.size or order.size != capacity.size
                or receiver.dtype.kind not in "iu" or order.dtype.kind not in "iu"):
            raise ValueError("bounded storage arrays, boolean perimeter and integer saved DAG required")
        receiver, order = receiver.ravel(), order.ravel()
        if (np.any(receiver < -1) or np.any(receiver >= capacity.size)
                or not np.array_equal(np.sort(order), np.arange(capacity.size))):
            raise ValueError("receiver range or topological permutation invalid")
        rank = np.empty(capacity.size, np.int64)
        rank[order] = np.arange(capacity.size)
        sources = np.flatnonzero(receiver >= 0)
        if np.any(rank[sources] >= rank[receiver[sources]]):
            raise ValueError("saved DAG must be upstream to downstream")
        if (not np.isfinite(capacity).all() or not np.isfinite(storage).all()
                or np.any(capacity < 0.) or np.any(storage < 0.) or np.any(storage > capacity)
                or not np.isfinite(storage.sum()) or not np.isfinite(capacity.sum())
                or not np.isfinite(spacing_m) or not 0. < spacing_m <= 1e6
                or not np.isfinite(self.config.monthly_release_fraction)
                or not 0. <= self.config.monthly_release_fraction <= 1.
                or not np.isfinite(self.config.monthly_evaporation_depth_m)
                or self.config.monthly_evaporation_depth_m < 0.):
            raise ValueError("finite physical capacity, storage and event rates required")
        self.shape = capacity.shape
        self.receiver = receiver.astype(np.int64, copy=True)
        self.order = order.astype(np.int64, copy=True)
        self.capacity = capacity.ravel().copy()
        self.storage = storage.ravel().copy()
        self.perimeter = perimeter.ravel().copy()
        self.cell_area_m2 = float(spacing_m) ** 2

    def step(self, local_runoff_m3, interval_seconds, *, reference_month_seconds=30. * 86400.):
        """Advance one bounded interval; return per-cell volumes and a ledger."""
        local = np.asarray(local_runoff_m3, np.float64)
        if (local.shape != self.shape or not np.isfinite(local).all() or np.any(local < 0.)
                or not np.isfinite(local.sum())
                or not np.isfinite(interval_seconds) or not 0. < interval_seconds <= 32. * 86400.
                or not np.isfinite(reference_month_seconds) or reference_month_seconds <= 0.):
            raise ValueError("finite nonnegative runoff and bounded positive physical interval required")
        ratio = interval_seconds / reference_month_seconds
        release = self.config.monthly_release_fraction
        release_fraction = (1. if release == 1. else
                            -np.expm1(np.log1p(-release) * ratio))
        evaporation = self.config.monthly_evaporation_depth_m * self.cell_area_m2 * ratio
        before = float(self.storage.sum())
        input_volume = float(local.sum())
        if not np.isfinite(evaporation) or not np.isfinite(before + input_volume):
            raise ValueError("finite aggregate event water and evaporation required")
        routed, et_cells, et, released, overflow, unknown, unresolved = _monthly_storage(
            local.ravel(), self.receiver, self.order, self.capacity, self.storage,
            evaporation, release_fraction, self.perimeter)
        after = float(self.storage.sum())
        ledger = dict(interval_seconds=float(interval_seconds),
                      reference_month_seconds=float(reference_month_seconds),
                      input_runoff_m3=input_volume, storage_before_m3=before,
                      storage_after_m3=after, evaporation_m3=float(et),
                      storage_release_m3=float(released), overflow_m3=float(overflow),
                      unknown_boundary_export_m3=float(unknown),
                      unresolved_terminal_export_m3=float(unresolved),
                      balance_residual_m3=input_volume + before - after - et - unknown - unresolved)
        return dict(arrays=dict(outflow_m3=routed.reshape(self.shape),
                                routed_q_m3_s=(routed / interval_seconds).reshape(self.shape),
                                storage_m3=self.storage.reshape(self.shape).copy(),
                                evaporation_m3=et_cells.reshape(self.shape)), ledger=ledger)


def prepare_event_routing(receiver, topological_order, capacity_m3, initial_storage_m3,
                          perimeter_mask, spacing_m, *, config=None):
    """Validate and copy a saved routing state once for a streamed event run."""
    return EventRunoffRouter(receiver, topological_order, capacity_m3, initial_storage_m3,
                             perimeter_mask, spacing_m, config=config)


@njit(cache=True)
def _close(mask, receiver, order):
    result = mask.copy()
    for cell in order:
        if result[cell] and receiver[cell] >= 0:
            result[receiver[cell]] = True
    return result


@njit(cache=True)
def _first_object(flags, receiver, order):
    owner = np.full(flags.size, -1, np.int64)
    received_flags = np.zeros(flags.size, np.uint8)
    for k in range(order.size - 1, -1, -1):
        cell = order[k]
        if flags[cell] != 0:
            owner[cell] = cell
            received_flags[cell] = flags[cell]
        elif receiver[cell] >= 0:
            owner[cell] = owner[receiver[cell]]
            received_flags[cell] = received_flags[receiver[cell]]
    return owner, received_flags


@njit(cache=True)
def _channel_corridor(channel, receiver, order, work, cols, spacing,
                      max_distance, max_hand):
    distance = np.full(channel.size, np.inf)
    channel_height = np.zeros(channel.size, np.float64)
    corridor = np.zeros(channel.size, np.bool_)
    for k in range(order.size - 1, -1, -1):
        cell = order[k]
        if channel[cell]:
            distance[cell] = 0.
            channel_height[cell] = work[cell]
        elif receiver[cell] >= 0:
            target = receiver[cell]
            dr = cell // cols - target // cols
            dc = cell % cols - target % cols
            distance[cell] = distance[target] + spacing * np.sqrt(dr * dr + dc * dc)
            channel_height[cell] = channel_height[target]
        corridor[cell] = (distance[cell] <= max_distance
                          and work[cell] - channel_height[cell] <= max_hand)
    return corridor


def _validate(height, raises, receiver, order, area, spacing, runoff, config):
    if height.ndim != 2 or height.size == 0 or height.size > 4_000_000:
        raise ValueError("bounded nonempty 2D terrain required")
    if raises.shape != height.shape or area.size != height.size:
        raise ValueError("terrain, raise and contributing area shapes must match")
    if (receiver.shape != (height.size,) or order.shape != receiver.shape
            or receiver.dtype.kind not in "iu" or order.dtype.kind not in "iu"):
        raise ValueError("integer receiver and topological_order [N] required")
    if runoff.shape not in ((12, *height.shape), (12, height.size)):
        raise ValueError("12 months of local runoff volumes required")
    if not np.isfinite(spacing) or spacing <= 0.:
        raise ValueError("positive finite spacing_m required")
    for values in (height, raises, area, runoff):
        if not np.isfinite(values).all():
            raise ValueError("finite terrain and runoff required")
    if np.any(raises < 0.) or np.any(area < spacing ** 2) or np.any(runoff < 0.):
        raise ValueError("nonnegative raise/runoff and physical cell areas required")
    if not np.isfinite(runoff.sum(dtype=np.float64)):
        raise ValueError("finite aggregate runoff volume required")
    if (np.any(receiver < -1) or np.any(receiver >= height.size)
            or not np.array_equal(np.sort(order), np.arange(height.size))):
        raise ValueError("receiver range or topological permutation invalid")
    rank = np.empty(height.size, np.int64)
    rank[order] = np.arange(height.size)
    sources = np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    if np.any(rank[sources] >= rank[targets]):
        raise ValueError("topological_order must be upstream to downstream")
    rows, cols = height.shape
    if (np.any(np.abs(sources // cols - targets // cols) > 1)
            or np.any(np.abs(sources % cols - targets % cols) > 1)):
        raise ValueError("saved routing edges must connect neighboring terrain cells")
    work = (height + raises).ravel()
    if np.any(work[targets] > work[sources] + 1e-7):
        raise ValueError("saved routing must not climb its working surface")
    values = asdict(config)
    if any(not np.isfinite(v) or v < 0. for v in values.values()):
        raise ValueError("finite nonnegative configuration required")
    if (not 1 <= config.simulation_years <= 5 or type(config.simulation_years) is not int
            or not 1 <= config.seasonal_months <= config.persistent_months <= 12
            or type(config.persistent_months) is not int or type(config.seasonal_months) is not int
            or config.channel_q_threshold_m3_s <= 0.
            or not 0. <= config.monthly_release_fraction <= 1.
            or config.shallow_lake_min_raise_m > config.shallow_lake_max_depth_m):
        raise ValueError("invalid bounded monthly/storage configuration")


def lowland_geometry(height, spacing_m, config):
    """Original-surface local relief, slope and lowland mask on a regular sample."""
    window = 2 * max(1, int(np.ceil(config.relief_radius_m / spacing_m))) + 1
    relief = maximum_filter(height, size=window, mode="nearest") - minimum_filter(
        height, size=window, mode="nearest")
    gradients = []
    for axis in range(2):
        gradients.append(np.gradient(height, spacing_m, axis=axis)
                         if height.shape[axis] > 1 else np.zeros_like(height))
    slope = np.hypot(*gradients)
    lowland = (relief <= config.lowland_relief_m) & (slope <= config.lowland_slope)
    return relief, slope, lowland


def classify_and_route(original_td_m, working_raise_m, receiver, topological_order,
                       contributing_area_m2, spacing_m, monthly_local_runoff_m3,
                       *, config=None):
    """Separate channel evidence from conserved runoff; never modify routing.

    Volumes are already runoff, not gross rain. Repeated synthetic years start
    with empty candidate storage; the last year is diagnostic, not equilibrium
    or evidence of calibrated perennial flow. Object IDs are flat cell IDs.
    """
    config = LowlandRunoffConfig() if config is None else config
    if not isinstance(config, LowlandRunoffConfig):
        raise ValueError("LowlandRunoffConfig required")
    height = np.asarray(original_td_m, np.float64)
    raises = np.asarray(working_raise_m, np.float64)
    receiver = np.asarray(receiver)
    order = np.asarray(topological_order)
    area = np.asarray(contributing_area_m2, np.float64)
    runoff = np.asarray(monthly_local_runoff_m3)
    _validate(height, raises, receiver, order, area, spacing_m, runoff, config)
    receiver = receiver.astype(np.int64, copy=False)
    order = order.astype(np.int64, copy=False)
    runoff = runoff.reshape(12, -1)
    relief, slope, lowland = lowland_geometry(height, spacing_m, config)
    perimeter = np.zeros(height.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    concentration = area.ravel() >= np.where(lowland.ravel(),
        config.lowland_initiation_area_m2, config.upland_initiation_area_m2)
    full_mean = np.zeros(height.size, np.float64)
    raw_wet_count = np.zeros(height.size, np.uint8)
    for month in range(12):
        routed = _accumulate(runoff[month], receiver, order)
        full_mean += routed / YEAR_SECONDS
        raw_wet_count += routed >= config.channel_q_threshold_m3_s * MONTH_SECONDS[month]
    provisional_permanent = _close(concentration & (
        raw_wet_count >= config.persistent_months), receiver, order)
    provisional_seasonal = _close(concentration & (
        raw_wet_count >= config.seasonal_months), receiver, order) & ~provisional_permanent
    corridor = _channel_corridor(provisional_permanent, receiver, order,
        (height + raises).ravel(), height.shape[1], spacing_m,
        config.floodplain_max_dag_distance_m,
        config.floodplain_max_height_above_channel_m).reshape(height.shape)
    # Storage class describes terrain geometry independently of channel
    # visibility. River and storage flags can coexist at a single location.
    storage_flags = np.zeros(height.shape, np.uint8)
    floodplain = lowland & corridor
    swale = lowland & provisional_seasonal.reshape(height.shape)
    storage_flags[floodplain] = OBJECT_FLAGS["floodplain"]
    storage_flags[swale] = OBJECT_FLAGS["seasonal_swale"]
    wetland = lowland & (raises >= config.wetland_min_raise_m)
    lake = lowland & (raises >= config.shallow_lake_min_raise_m) & (
        raises <= config.shallow_lake_max_depth_m)
    storage_flags[wetland] = OBJECT_FLAGS["wetland"]
    storage_flags[lake] = OBJECT_FLAGS["shallow_lake"]
    depth = np.zeros(height.shape, np.float64)
    depth[floodplain] = config.floodplain_storage_depth_m
    depth[swale] = config.swale_storage_depth_m
    depth[wetland] = config.wetland_storage_depth_m
    depth[lake] = raises[lake]
    depth[perimeter] = 0.
    capacity = (depth * spacing_m ** 2).ravel()
    storage = np.zeros(height.size, np.float64)
    routed_mean = np.zeros(height.size, np.float64)
    wet_count = np.zeros(height.size, np.uint8)
    annual_et = np.zeros(height.size, np.float64)
    annual_local = np.zeros(height.size, np.float64)
    annual_out = np.zeros(height.size, np.float64)
    initial_last_year_storage = np.zeros(height.size, np.float64)
    ledger = []
    for step in range(config.simulation_years * 12):
        before = float(storage.sum())
        if step == (config.simulation_years - 1) * 12:
            initial_last_year_storage[:] = storage
        local = runoff[step % 12]
        routed, et_cells, et, release, overflow, unknown, unresolved = _monthly_storage(
            local, receiver, order, capacity, storage,
            config.monthly_evaporation_depth_m * spacing_m ** 2,
            config.monthly_release_fraction, perimeter.ravel())
        after = float(storage.sum())
        input_volume = float(local.sum(dtype=np.float64))
        residual = input_volume + before - after - et - unknown - unresolved
        ledger.append(dict(year=step // 12 + 1, month=step % 12 + 1,
                           interval_seconds=float(MONTH_SECONDS[step % 12]),
                           input_runoff_m3=input_volume, storage_before_m3=before,
                           storage_after_m3=after, evaporation_m3=float(et),
                           storage_release_m3=float(release), overflow_m3=float(overflow),
                           unknown_boundary_export_m3=float(unknown),
                           unresolved_terminal_export_m3=float(unresolved),
                           balance_residual_m3=float(residual)))
        if step >= (config.simulation_years - 1) * 12:
            routed_mean += routed / YEAR_SECONDS
            wet_count += routed >= config.channel_q_threshold_m3_s * MONTH_SECONDS[step % 12]
            annual_et += et_cells
            annual_local += local
            annual_out += routed
    permanent_seeds = concentration & (wet_count >= config.persistent_months)
    seasonal_seeds = concentration & (wet_count >= config.seasonal_months)
    permanent = _close(permanent_seeds, receiver, order)
    seasonal = _close(seasonal_seeds, receiver, order) & ~permanent
    flags = storage_flags.ravel().copy()
    flags[permanent | seasonal] |= OBJECT_FLAGS["river"]
    owner, received_flags = _first_object(flags, receiver, order)
    arrays = dict(receiver=receiver.copy(), topological_order=order.copy())
    grids = dict(lowland_mask=lowland, local_relief_m=relief, slope=slope,
                 permanent_channel_mask=permanent, seasonal_channel_mask=seasonal,
                 permanent_initiation_mask=permanent_seeds,
                 seasonal_initiation_mask=seasonal_seeds & ~permanent_seeds,
                 object_flags=flags, first_receiving_object_id=owner,
                 first_receiving_object_flags=received_flags,
                 storage_capacity_m3=capacity, final_storage_m3=storage,
                 mean_routed_q_m3_s=routed_mean,
                 mean_full_network_q_m3_s=full_mean,
                 wet_month_count=wet_count, full_network_wet_month_count=raw_wet_count)
    grids.update(last_year_initial_storage_m3=initial_last_year_storage,
                 last_year_local_runoff_m3=annual_local,
                 last_year_outflow_m3=annual_out, last_year_evaporation_m3=annual_et,
                 provisional_permanent_channel_mask=provisional_permanent,
                 provisional_seasonal_channel_mask=provisional_seasonal)
    arrays.update({key: value.reshape(height.shape) for key, value in grids.items()})
    metadata = dict(algorithm=ALGORITHM, config=asdict(config),
        object_flag_codes=OBJECT_FLAGS.copy(), month_ledger=ledger,
        monthly_seconds=MONTH_SECONDS.tolist(), runoff_network_intact=True,
        receiver_policy="saved adjacent working-surface DAG; no routing edits",
        receiving_object_policy="first flagged cell on saved DAG, including self; co-located flags have equal priority",
        storage_policy="per-cell candidate buckets, shallow raise footprint or explicit retention depths; no excavation or verified water surface",
        channel_policy="persistent-flow/seasonal candidates from last synthetic year; downstream closure preserves upland-origin trunks",
        climate_policy="12 supplied synthetic runoff months repeated from empty storage; no annual equilibrium claim",
        rain_balance_scope="input is runoff only; rainfall partition losses must be accounted by the forcing producer",
        unresolved_terminal_policy="interior residual outflow remains unresolved, never accepted lake/ocean discharge",
        illustrative=True, calibrated=False, hydraulic_ready=False, publishable=False)
    return dict(arrays=arrays, metadata=metadata)
