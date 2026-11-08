"""Conservative explicit channel, finite-pool lake, and boundary coupling."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import readonly
from .metric_channel_state import ChannelConfig, ChannelNetwork
from .metric_lake_storage import LakeOutlet, LakeStorage


ALGORITHM = "manning-lake-boundary-explicit-v1"
MAX_TRACE_BYTES = 128 * 1024 * 1024
MAX_FORCING_BYTES = 128 * 1024 * 1024
MAX_LAKES = 256
MAX_OUTLETS = 4096
MAX_SUPPORT_CELLS = 65536
BOUNDARY_KINDS = ("open_outflow", "closed_wall", "unknown_boundary",
                  "prescribed_stage", "prescribed_discharge")


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("lowercase SHA256 required")


def _times(value):
    if (not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.ndim != 1
            or not 2 <= value.size <= 100001 or not np.isfinite(value).all()
            or np.any(value < 0.) or not np.isfinite(np.diff(value)).all()
            or np.any(np.diff(value) <= 0.)):
        raise ValueError("strictly increasing nonnegative physical interval endpoints required")
    return readonly(value)


@dataclass(frozen=True)
class BoundarySeries:
    node_ids: np.ndarray
    kinds: np.ndarray
    allow_inflow: np.ndarray
    time_seconds: np.ndarray
    stage_m: np.ndarray
    discharge_m3_s: np.ndarray
    conductance_m2_s: np.ndarray
    source_identity_sha256: str

    def __post_init__(self):
        times = _times(self.time_seconds)
        ids = self.node_ids
        if (not isinstance(ids, np.ndarray) or ids.dtype != np.int64 or ids.ndim != 1
                or np.any(ids < 0) or np.unique(ids).size != ids.size):
            raise ValueError("distinct nonnegative int64 boundary node_ids required")
        count = ids.size
        kinds = self.kinds
        inflow = self.allow_inflow
        if (not isinstance(kinds, np.ndarray) or kinds.dtype.kind != "U" or kinds.shape != (count,)
                or not np.isin(kinds, BOUNDARY_KINDS).all()
                or not isinstance(inflow, np.ndarray) or inflow.dtype != bool or inflow.shape != (count,)
                or np.any(inflow & ~np.isin(kinds, ("prescribed_stage", "prescribed_discharge")))):
            raise ValueError("invalid boundary kind or inflow policy")
        for name in ("stage_m", "discharge_m3_s"):
            value = getattr(self, name)
            if (not isinstance(value, np.ndarray) or value.dtype != np.float64
                    or value.shape != (times.size - 1, count) or not np.isfinite(value).all()):
                raise ValueError("finite boundary series required: " + name)
            selected = kinds == ("prescribed_stage" if name == "stage_m" else "prescribed_discharge")
            if np.any(value[:, ~selected] != 0.):
                raise ValueError("boundary payload outside declared kind: " + name)
            object.__setattr__(self, name, readonly(value))
        if np.any((self.discharge_m3_s < 0.) & ~inflow[None, :]):
            raise ValueError("negative prescribed discharge requires explicit inflow")
        conductance = self.conductance_m2_s
        if (not isinstance(conductance, np.ndarray) or conductance.dtype != np.float64
                or conductance.shape != (count,) or not np.isfinite(conductance).all()
                or np.any(conductance[kinds == "prescribed_stage"] <= 0.)
                or np.any(conductance[kinds != "prescribed_stage"] != 0.)):
            raise ValueError("positive conductance only for prescribed stage")
        if (self.stage_m.nbytes + self.discharge_m3_s.nbytes + times.nbytes
                + ids.nbytes + kinds.nbytes + inflow.nbytes + conductance.nbytes > MAX_FORCING_BYTES):
            raise ValueError("boundary series resource budget exceeded")
        _sha(self.source_identity_sha256)
        object.__setattr__(self, "node_ids", readonly(ids))
        object.__setattr__(self, "kinds", readonly(kinds.astype("U24")))
        object.__setattr__(self, "allow_inflow", readonly(inflow))
        object.__setattr__(self, "time_seconds", times)
        object.__setattr__(self, "conductance_m2_s", readonly(conductance))


@dataclass(frozen=True)
class CoupledForcing:
    time_seconds: np.ndarray
    channel_local_q_m3_s: np.ndarray
    lake_local_q_m3_s: np.ndarray
    source_identity_sha256: str

    def __post_init__(self):
        times = _times(self.time_seconds)
        for name in ("channel_local_q_m3_s", "lake_local_q_m3_s"):
            value = getattr(self, name)
            if (not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.ndim != 2
                    or value.shape[0] != times.size - 1 or not np.isfinite(value).all()
                    or np.any(value < 0.)):
                raise ValueError("nonnegative float64 local coupled input required: " + name)
            object.__setattr__(self, name, readonly(value))
        if (times.nbytes + self.channel_local_q_m3_s.nbytes
                + self.lake_local_q_m3_s.nbytes > MAX_FORCING_BYTES):
            raise ValueError("coupled forcing resource budget exceeded")
        _sha(self.source_identity_sha256)
        object.__setattr__(self, "time_seconds", times)


def _channel_hydraulics(network, volume):
    area = volume / network.length_m
    depth = area / network.width_m
    perimeter = network.width_m + 2. * depth
    q = np.zeros_like(volume)
    wave = np.zeros_like(volume)
    active = (volume > 0.) & np.isin(network.terminal_kind, ("interior", "open_outflow"))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        q[active] = (area[active] * np.power(area[active] / perimeter[active], 2. / 3.)
                     * np.sqrt(network.bed_slope[active]) / network.roughness[active])
        wave[active] = q[active] / area[active] * (5. / 3. - 4. * depth[active] / (3. * perimeter[active]))
    return depth, network.bed_elevation_m + depth, q, wave


def _state(network, lakes, channel_volume, lake_volume):
    depth, channel_stage, channel_q, wave = _channel_hydraulics(network, channel_volume)
    lake_stage = np.array([lake.stage_at_volume(float(value)) for lake, value in zip(lakes, lake_volume)],
                          dtype=np.float64)
    if not all(np.isfinite(value).all() for value in (depth, channel_stage, channel_q, wave, lake_stage)):
        raise ValueError("nonfinite coupled state")
    return channel_stage, lake_stage, channel_q, wave


def solve_coupled(channel_network, lakes, outlets, channel_to_lake, forcing, boundaries,
                  initial_channel_volume_m3=None, initial_lake_volume_m3=None, config=None):
    """Advance all transfers on one physical timestep; return committed prefix on failure."""
    if not isinstance(channel_network, ChannelNetwork) or not isinstance(forcing, CoupledForcing) or not isinstance(boundaries, BoundarySeries):
        raise ValueError("ChannelNetwork, CoupledForcing, and BoundarySeries required")
    if config is None:
        config = ChannelConfig()
    if not isinstance(config, ChannelConfig):
        raise ValueError("ChannelConfig required")
    if (not isinstance(lakes, tuple) or any(not isinstance(lake, LakeStorage) for lake in lakes)
            or not isinstance(outlets, tuple) or any(not isinstance(outlet, LakeOutlet) for outlet in outlets)):
        raise ValueError("lake and outlet tuples required")
    nc, nl, no, nb = channel_network.receiver.size, len(lakes), len(outlets), boundaries.node_ids.size
    if nl > MAX_LAKES or no > MAX_OUTLETS or sum(lake.cell_ids.size for lake in lakes) > MAX_SUPPORT_CELLS:
        raise ValueError("coupled lake/outlet support resource budget exceeded")
    if (not isinstance(channel_to_lake, np.ndarray) or channel_to_lake.dtype != np.int64
            or channel_to_lake.shape != (nc,) or np.any(channel_to_lake < -1)
            or np.any(channel_to_lake >= nl) or forcing.channel_local_q_m3_s.shape[1] != nc
            or forcing.lake_local_q_m3_s.shape[1] != nl
            or not np.array_equal(forcing.time_seconds, boundaries.time_seconds)
            or np.any(boundaries.node_ids >= nc)
            or np.any(channel_network.receiver[boundaries.node_ids] >= 0)):
        raise ValueError("coupled shape, time, or mapping mismatch")
    linked = channel_to_lake >= 0
    if (np.any(linked & (channel_network.receiver != -1))
            or np.any(linked & (channel_network.terminal_kind != "open_outflow"))
            or np.intersect1d(np.flatnonzero(linked), boundaries.node_ids).size):
        raise ValueError("channel-to-lake must be an unoverridden open terminal")
    claimed_cells = set()
    for lake in lakes:
        ids = set(map(int, lake.cell_ids))
        if claimed_cells & ids:
            raise ValueError("lake support cells overlap")
        claimed_cells.update(ids)
    for outlet in outlets:
        if (outlet.lake_index >= nl or outlet.receiver >= nc + nl or outlet.receiver < -1
                or outlet.receiver == nc + outlet.lake_index):
            raise ValueError("invalid lake outlet receiver")
        lake = lakes[outlet.lake_index]
        if not lake.bed_elevation_m.min() <= outlet.crest_stage_m <= lake.max_stage_m:
            raise ValueError("lake outlet crest outside supported stage")
    channel_capacity = channel_network.length_m * channel_network.width_m * channel_network.max_depth_m
    lake_capacity = np.array([lake.capacity_m3 for lake in lakes], np.float64)
    if not np.isfinite(channel_capacity).all() or not np.isfinite(lake_capacity).all():
        raise ValueError("nonfinite coupled capacity")
    channel_volume = (np.zeros(nc, np.float64) if initial_channel_volume_m3 is None
                      else np.asarray(initial_channel_volume_m3))
    lake_volume = (np.zeros(nl, np.float64) if initial_lake_volume_m3 is None
                   else np.asarray(initial_lake_volume_m3))
    if (channel_volume.dtype != np.float64 or channel_volume.shape != (nc,)
            or lake_volume.dtype != np.float64 or lake_volume.shape != (nl,)
            or not np.isfinite(channel_volume).all() or not np.isfinite(lake_volume).all()
            or np.any(channel_volume < 0.) or np.any(channel_volume > channel_capacity)
            or np.any(lake_volume < 0.) or np.any(lake_volume > lake_capacity)):
        raise ValueError("invalid initial coupled storage")
    with np.errstate(over="ignore", invalid="ignore"):
        initial_total = np.sum(channel_volume, dtype=np.float64) + np.sum(lake_volume, dtype=np.float64)
    if not np.isfinite(initial_total):
        raise ValueError("initial aggregate storage exceeds finite total")
    channel_volume = channel_volume.copy()
    lake_volume = lake_volume.copy()
    channel_stage, lake_stage, _, _ = _state(channel_network, lakes, channel_volume, lake_volume)
    times = [float(forcing.time_seconds[0])]
    cv, lv = [channel_volume.copy()], [lake_volume.copy()]
    cs, ls = [channel_stage], [lake_stage]
    trace = {name: [] for name in ("channel_q_m3_s", "lake_outlet_q_m3_s", "boundary_q_m3_s",
            "channel_local_q_m3_s", "lake_local_q_m3_s", "channel_donor_q_m3_s", "lake_donor_q_m3_s",
            "channel_boundary_volume_m3", "lake_external_volume_m3", "channel_residual_m3",
            "lake_residual_m3", "stability_number")}
    failure = None
    trace_limit = MAX_TRACE_BYTES // (8 * (28 * nc + 20 * nl + 4 * no + 4 * nb + 4))
    while times[-1] < forcing.time_seconds[-1]:
        if len(times) - 1 >= config.max_steps:
            failure = "maximum step count exceeded"
            break
        if len(times) - 1 >= trace_limit:
            failure = "trace byte budget exceeded"
            break
        now = times[-1]
        interval = min(int(np.searchsorted(forcing.time_seconds, now, side="right") - 1), forcing.time_seconds.size - 2)
        segment_end = float(forcing.time_seconds[interval + 1])
        channel_stage, lake_stage, manning_q, wave = _state(channel_network, lakes, channel_volume, lake_volume)
        channel_q = manning_q.copy()
        boundary_q = np.zeros(nb, np.float64)
        rate = wave / channel_network.length_m
        for index, node in enumerate(boundaries.node_ids):
            kind = boundaries.kinds[index]
            if kind in ("closed_wall", "unknown_boundary"):
                q = 0.
                rate[node] = 0.
            elif kind == "open_outflow":
                q = float(manning_q[node])
            elif kind == "prescribed_discharge":
                q = float(boundaries.discharge_m3_s[interval, index])
                rate[node] = 0.
            else:
                with np.errstate(over="ignore", invalid="ignore"):
                    q = float(boundaries.conductance_m2_s[index] *
                              (channel_stage[node] - boundaries.stage_m[interval, index]))
                if not boundaries.allow_inflow[index]:
                    q = max(q, 0.)
                if q > 0. and channel_volume[node] == 0.:
                    q = 0.
                rate[node] = (boundaries.conductance_m2_s[index] /
                              (channel_network.length_m[node] * channel_network.width_m[node]))
            channel_q[node] = q
            boundary_q[index] = q
        try:
            lake_q = np.array([outlet.discharge_at_stage(float(lake_stage[outlet.lake_index]))
                               for outlet in outlets], np.float64)
        except ValueError:
            failure = "nonfinite hydraulic flux"
            break
        channel_donor = np.zeros(nc, np.float64)
        lake_donor = np.zeros(nl, np.float64)
        for node, receiver in enumerate(channel_network.receiver):
            if receiver >= 0:
                channel_donor[receiver] += channel_q[node]
            elif channel_to_lake[node] >= 0:
                lake_donor[channel_to_lake[node]] += channel_q[node]
        for index, outlet in enumerate(outlets):
            if 0 <= outlet.receiver < nc:
                channel_donor[outlet.receiver] += lake_q[index]
            elif outlet.receiver >= nc:
                lake_donor[outlet.receiver - nc] += lake_q[index]
        lake_outgoing = np.zeros(nl, np.float64)
        for index, outlet in enumerate(outlets):
            lake_outgoing[outlet.lake_index] += lake_q[index]
        lake_area = np.array([lake.surface_area_at_stage(float(stage))
                              for lake, stage in zip(lakes, lake_stage)], np.float64)
        lake_rate = np.zeros(nl, np.float64)
        for outlet, q in zip(outlets, lake_q):
            head = max(float(lake_stage[outlet.lake_index] - outlet.crest_stage_m), 0.)
            if head > 0. and lake_area[outlet.lake_index] > 0.:
                lake_rate[outlet.lake_index] += 1.5 * outlet.coefficient_m3_s_m15 * math.sqrt(head) / lake_area[outlet.lake_index]
        if not all(np.isfinite(value).all() for value in
                   (channel_stage, lake_stage, channel_q, lake_q, boundary_q,
                    channel_donor, lake_donor, lake_outgoing, rate, lake_rate)):
            failure = "nonfinite hydraulic flux"
            break
        dt = min(config.max_dt_seconds, segment_end - now)
        if nc and np.any(rate > 0.):
            dt = min(dt, float(config.cfl / np.max(rate)))
        if nl and np.any(lake_rate > 0.):
            dt = min(dt, float(config.cfl / np.max(lake_rate)))
        positive_channel = channel_q > 0.
        if np.any(positive_channel):
            dt = min(dt, float(np.min(config.cfl * channel_volume[positive_channel] / channel_q[positive_channel])))
        positive_lake = lake_outgoing > 0.
        if np.any(positive_lake):
            dt = min(dt, float(np.min(config.cfl * lake_volume[positive_lake] / lake_outgoing[positive_lake])))
        if not np.isfinite(dt) or dt <= 0. or (dt < config.min_dt_seconds and segment_end - now > config.min_dt_seconds):
            failure = "minimum internal step required or nonfinite time step"
            break
        if now + dt == now:
            failure = "time resolution exhausted"
            break
        next_time = segment_end if now + dt >= segment_end else now + dt
        actual_dt = next_time - now
        if actual_dt > config.max_dt_seconds * (1. + 1e-12):
            failure = "maximum internal step exceeded at time resolution"
            break
        channel_external = np.zeros(nc, np.float64)
        terminal = channel_network.receiver == -1
        channel_external[terminal & ~linked] = channel_q[terminal & ~linked]
        lake_external = np.zeros(nl, np.float64)
        for index, outlet in enumerate(outlets):
            if outlet.receiver == -1:
                lake_external[outlet.lake_index] += lake_q[index]
        local_channel = forcing.channel_local_q_m3_s[interval]
        local_lake = forcing.lake_local_q_m3_s[interval]
        with np.errstate(over="ignore", invalid="ignore"):
            next_channel = channel_volume + actual_dt * (local_channel + channel_donor - channel_q)
            next_lake = lake_volume + actual_dt * (local_lake + lake_donor - lake_outgoing)
        if (not np.isfinite(next_channel).all() or not np.isfinite(next_lake).all()
                or np.any(next_channel < -1e-12 * np.maximum(1., channel_capacity))
                or np.any(next_lake < -1e-12 * np.maximum(1., lake_capacity))):
            failure = "nonfinite or negative volume"
            break
        next_channel = np.maximum(next_channel, 0.)
        next_lake = np.maximum(next_lake, 0.)
        if np.any(next_channel > channel_capacity):
            failure = "channel depth limit exceeded"
            break
        if np.any(next_lake > lake_capacity):
            failure = "lake capacity exceeded"
            break
        try:
            next_cs, next_ls, _, _ = _state(channel_network, lakes, next_channel, next_lake)
        except ValueError:
            failure = "nonfinite hydraulic state"
            break
        channel_residual = next_channel - channel_volume - actual_dt * (local_channel + channel_donor - channel_q)
        lake_residual = next_lake - lake_volume - actual_dt * (local_lake + lake_donor - lake_outgoing)
        stability = actual_dt * max(float(np.max(rate)), float(np.max(lake_rate, initial=0.)))
        channel_boundary_volume = actual_dt * channel_external
        lake_external_volume = actual_dt * lake_external
        with np.errstate(over="ignore", invalid="ignore"):
            totals = (np.sum(next_channel, dtype=np.float64) + np.sum(next_lake, dtype=np.float64),
                      actual_dt * (np.sum(local_channel, dtype=np.float64) +
                                   np.sum(local_lake, dtype=np.float64)),
                      np.sum(channel_boundary_volume, dtype=np.float64) +
                      np.sum(lake_external_volume, dtype=np.float64),
                      np.sum(channel_donor, dtype=np.float64) + np.sum(lake_donor, dtype=np.float64))
        if not all(np.isfinite(value).all() for value in (channel_residual, lake_residual,
                                                        channel_boundary_volume, lake_external_volume,
                                                        channel_q, lake_q, boundary_q)) or not all(
                np.isfinite(total) for total in totals):
            failure = "nonfinite water ledger"
            break
        if not np.isfinite(stability) or stability > config.cfl * (1. + 1e-12):
            failure = "stability bound exceeded at time resolution"
            break
        times.append(next_time)
        cv.append(next_channel.copy())
        lv.append(next_lake.copy())
        cs.append(next_cs.copy())
        ls.append(next_ls.copy())
        for name, value in (("channel_q_m3_s", channel_q), ("lake_outlet_q_m3_s", lake_q),
                            ("boundary_q_m3_s", boundary_q), ("channel_local_q_m3_s", local_channel),
                            ("lake_local_q_m3_s", local_lake), ("channel_donor_q_m3_s", channel_donor),
                            ("lake_donor_q_m3_s", lake_donor),
                            ("channel_boundary_volume_m3", channel_boundary_volume),
                            ("lake_external_volume_m3", lake_external_volume),
                            ("channel_residual_m3", channel_residual), ("lake_residual_m3", lake_residual),
                            ("stability_number", np.float64(stability))):
            trace[name].append(np.asarray(value).copy())
        channel_volume, lake_volume = next_channel, next_lake
    steps = len(times) - 1
    arrays = {"time_seconds": np.asarray(times, np.float64),
              "channel_volume_m3": np.stack(cv), "lake_volume_m3": np.stack(lv),
              "channel_stage_m": np.stack(cs), "lake_stage_m": np.stack(ls)}
    shapes = {"channel_q_m3_s": nc, "lake_outlet_q_m3_s": no, "boundary_q_m3_s": nb,
              "channel_local_q_m3_s": nc, "lake_local_q_m3_s": nl,
              "channel_donor_q_m3_s": nc, "lake_donor_q_m3_s": nl,
              "channel_boundary_volume_m3": nc, "lake_external_volume_m3": nl,
              "channel_residual_m3": nc, "lake_residual_m3": nl}
    for name, width in shapes.items():
        arrays[name] = np.stack(trace[name]) if steps else np.empty((0, width), np.float64)
    arrays["stability_number"] = np.asarray(trace["stability_number"], np.float64)
    metadata = {"algorithm": ALGORITHM, "status": "failed_prefix" if failure else "complete",
                "failure_reason": failure, "last_time_seconds": times[-1],
                "requested_end_time_seconds": float(forcing.time_seconds[-1]),
                "config": asdict(config),
                "limitations": ["rectangular channel and finite fixed-support lake",
                                "prescribed stage uses explicit conductance, not backwater",
                                "no sediment, bed change, or natural outlet certification"],
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    return {"arrays": arrays, "metadata": metadata}
