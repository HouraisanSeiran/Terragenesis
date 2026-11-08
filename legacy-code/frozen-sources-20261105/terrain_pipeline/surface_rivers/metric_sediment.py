"""Conservative solid-volume replay over pinned, frozen hydraulic intervals."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import MAX_METADATA, identity, load_bundle, readonly, save_bundle
from terrain_pipeline.surface_rivers.metric_bed_update import bed_from_inventory, bed_rejection
from terrain_pipeline.surface_rivers.metric_channel_state import validate_receiver_acyclic


SCHEMA = "terragenesis-sediment-replay-v1"
LEGACY_ALGORITHM = "bounded-frozen-water-exner-v1"
ALGORITHM = "bounded-frozen-water-exner-v2"
MAX_BYTES = 128 * 1024 * 1024
MAX_SEDIMENT_NODES = 2048
MAX_ARCHIVE_MEMBERS = 128
MAX_NPY_HEADER_BYTES = 4096
RHO_WATER_KG_M3 = 1000.
GRAVITY_M_S2 = 9.81


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _finite(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.) or (nonnegative and result < 0.):
        raise ValueError(name + " outside finite physical range")
    return result


def _array(value, shape, name, *, positive=False, nonnegative=False, dtype=np.float64):
    if not isinstance(value, np.ndarray) or value.dtype != dtype or value.shape != shape:
        raise ValueError(name + " shape or dtype mismatch")
    if dtype == np.float64 and (not np.isfinite(value).all() or
                                (positive and np.any(value <= 0.)) or
                                (nonnegative and np.any(value < 0.))):
        raise ValueError(name + " outside finite physical range")
    return readonly(value)


@dataclass(frozen=True)
class MaterialParameters:
    porosity: float = .35
    sediment_critical_shear_pa: float = 1.
    rock_critical_shear_pa: float = 5.
    sediment_erodibility_m_s_pa: float = 1e-6
    rock_erodibility_m_s_pa: float = 1e-8
    transport_coefficient: float = 1e-5
    settling_velocity_m_s: float = .001
    provenance: str = "declared homogeneous scenario"

    def __post_init__(self):
        for name in ("porosity", "sediment_critical_shear_pa", "rock_critical_shear_pa",
                     "sediment_erodibility_m_s_pa", "rock_erodibility_m_s_pa",
                     "transport_coefficient", "settling_velocity_m_s"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, nonnegative=True))
        if self.porosity >= 1. or self.rock_critical_shear_pa < self.sediment_critical_shear_pa:
            raise ValueError("porosity or shear thresholds invalid")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("material provenance required")


@dataclass(frozen=True)
class SedimentConfig:
    max_dt_seconds: float = .5
    min_dt_seconds: float = 1e-7
    cfl: float = .4
    max_steps: int = 20000
    max_bed_change_m: float = .05

    def __post_init__(self):
        for name in ("max_dt_seconds", "min_dt_seconds", "cfl", "max_bed_change_m"):
            object.__setattr__(self, name, _finite(getattr(self, name), name, positive=True))
        if self.min_dt_seconds > self.max_dt_seconds or self.cfl > 1.:
            raise ValueError("invalid sediment step controls")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 1_000_000:
            raise ValueError("invalid sediment step budget")


@dataclass(frozen=True)
class SedimentDomain:
    receiver: np.ndarray
    bed_area_m2: np.ndarray
    width_m: np.ndarray
    bed_elevation_m: np.ndarray
    rock_floor_m: np.ndarray
    initial_alluvium_bulk_m3: np.ndarray
    is_lake: np.ndarray
    open_boundary: np.ndarray
    geometry_identity_sha256: str
    provenance: str

    def __post_init__(self):
        receiver = self.receiver
        if not isinstance(receiver, np.ndarray) or receiver.dtype != np.int64 or receiver.ndim != 1 or not 1 <= receiver.size <= MAX_SEDIMENT_NODES:
            raise ValueError("bounded int64 receiver required")
        n = receiver.size
        if np.any((receiver < -1) | (receiver >= n) | (receiver == np.arange(n))):
            raise ValueError("invalid receiver")
        for name in ("bed_area_m2", "width_m", "bed_elevation_m", "rock_floor_m", "initial_alluvium_bulk_m3"):
            object.__setattr__(self, name, _array(getattr(self, name), (n,), name,
                positive=name in ("bed_area_m2", "width_m"), nonnegative=name == "initial_alluvium_bulk_m3"))
        for name in ("is_lake", "open_boundary"):
            object.__setattr__(self, name, _array(getattr(self, name), (n,), name, dtype=np.bool_))
        if np.any(self.open_boundary & (receiver != -1)):
            raise ValueError("open sediment boundary must be terminal")
        rock_reserve = ((self.bed_elevation_m - self.initial_alluvium_bulk_m3 / self.bed_area_m2)
                        - self.rock_floor_m) * self.bed_area_m2
        if not np.isfinite(rock_reserve).all() or np.any(rock_reserve < -1e-10):
            raise ValueError("initial rock reserve below declared floor")
        edges = receiver >= 0
        if np.any(self.bed_elevation_m[edges] <= self.bed_elevation_m[receiver[edges]]):
            raise ValueError("receiver requires positive initial bed slope")
        validate_receiver_acyclic(receiver)
        if not _sha(self.geometry_identity_sha256) or not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("geometry identity and provenance required")
        object.__setattr__(self, "receiver", readonly(receiver))


@dataclass(frozen=True)
class SedimentForcing:
    time_seconds: np.ndarray
    water_volume_m3: np.ndarray
    water_depth_m: np.ndarray
    water_outflow_m3_s: np.ndarray
    friction_slope: np.ndarray
    external_solid_m3_s: np.ndarray
    hydraulic_identity_sha256: str
    geometry_identity_sha256: str
    provenance: str

    def __post_init__(self):
        time = self.time_seconds
        if not isinstance(time, np.ndarray) or time.dtype != np.float64 or time.ndim != 1 or not 2 <= time.size <= 100001:
            raise ValueError("finite forcing interval endpoints required")
        time = _array(time, time.shape, "time_seconds", nonnegative=True)
        if np.any(np.diff(time) <= 0.) or not np.isfinite(np.diff(time)).all():
            raise ValueError("strictly increasing physical times required")
        object.__setattr__(self, "time_seconds", time)
        shape = None
        for name in ("water_volume_m3", "water_depth_m", "water_outflow_m3_s", "friction_slope", "external_solid_m3_s"):
            value = getattr(self, name)
            if shape is None:
                if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.ndim != 2 or value.shape[0] != time.size - 1 or not 1 <= value.shape[1] <= MAX_SEDIMENT_NODES:
                    raise ValueError("bounded interval-node forcing required")
                shape = value.shape
            object.__setattr__(self, name, _array(value, shape, name, nonnegative=True))
        if sum(getattr(self, name).nbytes for name in ("time_seconds", "water_volume_m3", "water_depth_m", "water_outflow_m3_s", "friction_slope", "external_solid_m3_s")) > MAX_BYTES:
            raise ValueError("forcing byte budget exceeded")
        if np.any((self.water_depth_m == 0.) & (self.water_outflow_m3_s > 0.)) or np.any((self.water_volume_m3 == 0.) & (self.water_outflow_m3_s > 0.)):
            raise ValueError("dry water cannot discharge")
        if not _sha(self.hydraulic_identity_sha256) or not _sha(self.geometry_identity_sha256):
            raise ValueError("hydraulic and geometry identities required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("water replay provenance required")


DOMAIN_FIELDS = ("receiver", "bed_area_m2", "width_m", "bed_elevation_m", "rock_floor_m",
                 "initial_alluvium_bulk_m3", "is_lake", "open_boundary")
FORCING_FIELDS = ("time_seconds", "water_volume_m3", "water_depth_m", "water_outflow_m3_s",
                  "friction_slope", "external_solid_m3_s")
STATE_FIELDS = ("mobile_solid_m3", "bed_alluvium_solid_m3", "rock_removed_m3", "bed_elevation_m")
STEP_FIELDS = ("outgoing_solid_m3", "incoming_solid_m3", "external_solid_m3", "eroded_loose_solid_m3",
               "eroded_rock_m3", "deposited_solid_m3", "bulk_deposition_m3", "bulk_erosion_m3",
               "pore_deposition_m3", "exported_solid_m3", "shear_pa", "capacity_solid_m3_s",
               "balance_residual_m3", "stability_number")


def _rates(domain, forcing, material, interval, mobile, loose, rock_removed):
    volume = forcing.water_volume_m3[interval]
    depth = forcing.water_depth_m[interval]
    q = forcing.water_outflow_m3_s[interval]
    slope = forcing.friction_slope[interval]
    radius = np.divide(domain.width_m * depth, domain.width_m + 2. * depth,
                       out=np.zeros_like(depth), where=depth > 0.)
    tau = np.where((q > 0.) & ~domain.is_lake, RHO_WATER_KG_M3 * GRAVITY_M_S2 * radius * slope, 0.)
    excess = np.maximum(tau - material.sediment_critical_shear_pa, 0.)
    concentration = np.divide(mobile, volume, out=np.zeros_like(mobile), where=volume > 0.)
    capacity = material.transport_coefficient * domain.width_m * excess ** 1.5
    capacity = np.where(domain.is_lake, q * concentration, capacity)
    outgoing = np.minimum(q * concentration, capacity)
    deposit = np.divide(material.settling_velocity_m_s * mobile, depth,
                        out=np.zeros_like(mobile), where=depth > 0.)
    deficit = np.maximum(capacity - outgoing, 0.)
    loose_rate = np.minimum(deficit, domain.bed_area_m2 * material.sediment_erodibility_m_s_pa * excess * (1. - material.porosity))
    loose_rate = np.where(loose > 0., loose_rate, 0.)
    rock_excess = np.maximum(tau - material.rock_critical_shear_pa, 0.)
    rock_rate = np.minimum(np.maximum(deficit - loose_rate, 0.), domain.bed_area_m2 * material.rock_erodibility_m_s_pa * rock_excess)
    rock_rate = np.where(loose == 0., rock_rate, 0.)
    return tau, capacity, outgoing, deposit, loose_rate, rock_rate


def _candidate(domain, forcing, material, config, interval, dt, mobile, loose, rock_removed, rates=None):
    if rates is None:
        rates = _rates(domain, forcing, material, interval, mobile, loose, rock_removed)
    tau, capacity, out_rate, deposit_rate, loose_rate, rock_rate = rates
    outgoing = dt * out_rate
    deposited = dt * deposit_rate
    eroded_loose = np.minimum(dt * loose_rate, loose)
    rock_reserve = (domain.bed_elevation_m - domain.initial_alluvium_bulk_m3 / domain.bed_area_m2
                    - domain.rock_floor_m) * domain.bed_area_m2 - rock_removed
    eroded_rock = np.minimum(dt * rock_rate, np.maximum(rock_reserve, 0.))
    external = dt * forcing.external_solid_m3_s[interval]
    incoming = np.zeros_like(mobile)
    edges = domain.receiver >= 0
    if incoming.ndim == 1:
        np.add.at(incoming, domain.receiver[edges], outgoing[edges])
    else:
        np.add.at(incoming.T, domain.receiver[edges], outgoing[:, edges].T)
    exported = np.where(domain.open_boundary, outgoing, 0.)
    next_mobile = mobile + incoming + external + eroded_loose + eroded_rock - outgoing - deposited
    next_loose = loose - eroded_loose + deposited
    next_rock = rock_removed + eroded_rock
    next_bed = bed_from_inventory(domain.bed_elevation_m,
                                  domain.initial_alluvium_bulk_m3 * (1. - material.porosity),
                                  next_loose, next_rock, domain.bed_area_m2, material.porosity)
    if not all(np.isfinite(item).all() for item in (tau, capacity, outgoing, incoming, external,
                                                   next_mobile, next_loose, next_rock, next_bed)):
        return None, "nonfinite sediment candidate"
    if np.any(next_mobile < -1e-10) or np.any(next_loose < -1e-10) or np.any(rock_reserve < -1e-9):
        return None, "negative sediment inventory"
    reason = bed_rejection(domain.bed_elevation_m, next_bed, domain.rock_floor_m,
                           domain.receiver, forcing.water_depth_m[interval], config.max_bed_change_m)
    if reason:
        return None, reason
    residual = next_mobile + next_loose - mobile - loose - incoming - external - eroded_rock + outgoing
    denominator = np.where(mobile > 0., mobile, 1.)
    stability = np.where(mobile > 0., (outgoing + deposited) / denominator, 0.)
    result = dict(mobile_solid_m3=next_mobile, bed_alluvium_solid_m3=next_loose,
                  rock_removed_m3=next_rock, bed_elevation_m=next_bed,
                  outgoing_solid_m3=outgoing, incoming_solid_m3=incoming,
                  external_solid_m3=external, eroded_loose_solid_m3=eroded_loose,
                  eroded_rock_m3=eroded_rock, deposited_solid_m3=deposited,
                  bulk_deposition_m3=deposited / (1. - material.porosity),
                  bulk_erosion_m3=eroded_loose / (1. - material.porosity) + eroded_rock,
                  pore_deposition_m3=deposited * material.porosity / (1. - material.porosity),
                  exported_solid_m3=exported, shear_pa=tau, capacity_solid_m3_s=capacity,
                  balance_residual_m3=residual, stability_number=stability)
    return result, None


def _paired(domain, forcing):
    if domain.geometry_identity_sha256 != forcing.geometry_identity_sha256:
        raise ValueError("hydraulic replay geometry identity mismatch")
    if forcing.water_volume_m3.shape[1] != domain.receiver.size:
        raise ValueError("sediment forcing node count mismatch")
    closed = (domain.receiver == -1) & ~domain.open_boundary
    if np.any(forcing.water_outflow_m3_s[:, closed] > 0.):
        raise ValueError("closed terminal cannot export water or sediment")
    if np.any(domain.is_lake & domain.open_boundary):
        raise ValueError("lake cannot be undeclared sediment exporter")


def _bounded_next_time(time, dt, segment_end, *, legacy=False):
    next_time = np.minimum(time + dt, segment_end)
    if not legacy:
        # Absolute-time rounding must not increase the physical donor bound.
        next_time = np.where(next_time - time > dt, np.nextafter(next_time, time), next_time)
    return next_time


def _next_step(domain, forcing, material, config, time, mobile, loose, rock, step_count, trace_limit, *, legacy=False):
    if step_count >= config.max_steps:
        return None, None, "maximum step count exceeded"
    if step_count >= trace_limit:
        return None, None, "trace byte budget exceeded"
    interval = min(int(np.searchsorted(forcing.time_seconds, time, side="right") - 1), forcing.time_seconds.size - 2)
    segment_end = float(forcing.time_seconds[interval + 1])
    rates = _rates(domain, forcing, material, interval, mobile, loose, rock)
    if not all(np.isfinite(rate).all() for rate in rates):
        return None, None, "nonfinite sediment rates"
    out_rate, deposit_rate = rates[2:4]
    dt = min(config.max_dt_seconds, segment_end - time)
    draining = mobile > 0.
    if np.any(draining):
        dt = min(dt, float(np.min(config.cfl * mobile[draining] / (out_rate[draining] + deposit_rate[draining] + 1e-300))))
    if not math.isfinite(dt) or dt <= 0. or (dt < config.min_dt_seconds and segment_end - time > config.min_dt_seconds) or time + dt == time:
        return None, None, "minimum internal step or time resolution exhausted"
    next_time = float(_bounded_next_time(time, dt, segment_end, legacy=legacy))
    if next_time <= time:
        return None, None, "minimum internal step or time resolution exhausted"
    candidate, reason = _candidate(domain, forcing, material, config, interval, next_time - time, mobile, loose, rock, rates=rates)
    if reason:
        return None, None, reason
    if np.any(candidate["stability_number"] > config.cfl * (1. + 1e-12)):
        return None, None, "sediment donor stability bound exceeded"
    return next_time, candidate, None


def solve_sediment(domain, forcing, material, initial_mobile_solid_m3=None, config=None):
    if not isinstance(domain, SedimentDomain) or not isinstance(forcing, SedimentForcing) or not isinstance(material, MaterialParameters):
        raise ValueError("sediment domain, forcing and material required")
    config = SedimentConfig() if config is None else config
    if not isinstance(config, SedimentConfig):
        raise ValueError("sediment config required")
    _paired(domain, forcing)
    n = domain.receiver.size
    initial_mobile = np.zeros(n) if initial_mobile_solid_m3 is None else _array(initial_mobile_solid_m3, (n,), "initial_mobile_solid_m3", nonnegative=True)
    initial_loose = domain.initial_alluvium_bulk_m3 * (1. - material.porosity)
    states = {name: [] for name in STATE_FIELDS}
    for name, value in zip(STATE_FIELDS, (initial_mobile, initial_loose, np.zeros(n), domain.bed_elevation_m)):
        states[name].append(np.asarray(value).copy())
    steps = {name: [] for name in STEP_FIELDS}
    times = [float(forcing.time_seconds[0])]
    reason = None
    static_bytes = sum(np.asarray(getattr(domain, name)).nbytes for name in DOMAIN_FIELDS)
    static_bytes += sum(np.asarray(getattr(forcing, name)).nbytes for name in FORCING_FIELDS)
    static_bytes += 8 * (len(STATE_FIELDS) * n + n + 2)
    if static_bytes >= MAX_BYTES:
        raise ValueError("sediment static trace budget exceeded")
    trace_limit = (MAX_BYTES - static_bytes) // (8 * (len(STATE_FIELDS) * n + len(STEP_FIELDS) * n + 3))
    while times[-1] < forcing.time_seconds[-1]:
        now = times[-1]
        mobile = states["mobile_solid_m3"][-1]
        loose = states["bed_alluvium_solid_m3"][-1]
        rock = states["rock_removed_m3"][-1]
        next_time, candidate, reason = _next_step(domain, forcing, material, config, now, mobile, loose, rock,
                                                   len(steps[STEP_FIELDS[0]]), trace_limit)
        if reason:
            break
        for name in STATE_FIELDS:
            states[name].append(candidate[name].copy())
        for name in STEP_FIELDS:
            steps[name].append(candidate[name].copy())
        times.append(next_time)
    arrays = {"trace_time_seconds": np.array(times, np.float64),
              "initial_mobile_solid_m3": np.asarray(initial_mobile).copy()}
    arrays.update({"domain_" + name: np.asarray(getattr(domain, name)).copy() for name in DOMAIN_FIELDS})
    arrays.update({"forcing_" + name: np.asarray(getattr(forcing, name)).copy() for name in FORCING_FIELDS})
    arrays.update({"trace_" + name: np.asarray(values, np.float64) for name, values in states.items()})
    arrays.update({"step_" + name: np.asarray(values, np.float64).reshape(-1, n) for name, values in steps.items()})
    arrays["step_dt_seconds"] = np.diff(arrays["trace_time_seconds"])
    arrays["cumulative_exported_solid_m3"] = np.concatenate(([0.], np.cumsum(np.sum(arrays["step_exported_solid_m3"], axis=1))))
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM, "material": asdict(material),
                "config": asdict(config), "geometry_identity_sha256": domain.geometry_identity_sha256,
                "hydraulic_identity_sha256": forcing.hydraulic_identity_sha256,
                "domain_provenance": domain.provenance, "forcing_provenance": forcing.provenance,
                "status": "failed_prefix" if reason else "complete", "failure_reason": reason,
                "last_time_seconds": times[-1], "requested_end_time_seconds": float(forcing.time_seconds[-1]),
                "uncompleted_from_seconds": times[-1] if reason else None,
                "uncompleted_to_seconds": float(forcing.time_seconds[-1]) if reason else None,
                "needs_geometry_and_hydraulic_revalidation": bool(np.any(arrays["trace_bed_elevation_m"] != domain.bed_elevation_m)),
                "frozen_water_bounded_approximation": True,
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
                "units": {"mobile": "solid_m3", "rock_removed": "intact_rock_m3", "bed": "model_m",
                          "transport_coefficient": "solid_m3/(s*m*Pa^1.5)",
                          "erodibility": "m/(s*Pa)"},
                "lake_transport": "q_times_mobile_concentration_without_shear_capacity_or_entrainment"}
    arrays = {name: readonly(value) for name, value in arrays.items()}
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("sediment bundle byte budget exceeded")
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_sediment(result)
    return result


def validate_sediment(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid sediment bundle")
    a, m = bundle["arrays"], bundle["metadata"]
    if m.get("schema") != SCHEMA or m.get("algorithm") not in (ALGORITHM, LEGACY_ALGORITHM) or identity(a, m) != bundle["identity_sha256"]:
        raise ValueError("sediment schema or identity mismatch")
    if set(a) != ({"trace_time_seconds", "initial_mobile_solid_m3", "step_dt_seconds",
                   "cumulative_exported_solid_m3"} | {"domain_" + k for k in DOMAIN_FIELDS} |
                  {"forcing_" + k for k in FORCING_FIELDS} | {"trace_" + k for k in STATE_FIELDS} |
                  {"step_" + k for k in STEP_FIELDS}):
        raise ValueError("sediment array schema mismatch")
    if sum(value.nbytes for value in a.values()) > MAX_BYTES:
        raise ValueError("sediment bundle byte budget exceeded")
    material = MaterialParameters(**m["material"])
    config = SedimentConfig(**m["config"])
    domain = SedimentDomain(**{key: a["domain_" + key] for key in DOMAIN_FIELDS},
                            geometry_identity_sha256=m["geometry_identity_sha256"], provenance=m["domain_provenance"])
    forcing = SedimentForcing(**{key: a["forcing_" + key] for key in FORCING_FIELDS},
                              hydraulic_identity_sha256=m["hydraulic_identity_sha256"],
                              geometry_identity_sha256=m["geometry_identity_sha256"], provenance=m["forcing_provenance"])
    _paired(domain, forcing)
    n = domain.receiver.size
    time = a["trace_time_seconds"]
    k = time.size - 1
    if time.dtype != np.float64 or time.ndim != 1 or k < 0 or not np.isfinite(time).all() or np.any(np.diff(time) <= 0.) or time[0] != forcing.time_seconds[0]:
        raise ValueError("invalid committed time prefix")
    static_bytes = sum(np.asarray(getattr(domain, name)).nbytes for name in DOMAIN_FIELDS)
    static_bytes += sum(np.asarray(getattr(forcing, name)).nbytes for name in FORCING_FIELDS)
    static_bytes += 8 * (len(STATE_FIELDS) * n + n + 2)
    trace_limit = (MAX_BYTES - static_bytes) // (8 * (len(STATE_FIELDS) * n + len(STEP_FIELDS) * n + 3))
    if k > config.max_steps or k > trace_limit:
        raise ValueError("sediment trace resource limit")
    for name in STATE_FIELDS:
        _array(a["trace_" + name], (k + 1, n), name)
        if name != "bed_elevation_m" and np.any(a["trace_" + name] < 0.):
            raise ValueError("negative sediment inventory")
    for name in STEP_FIELDS:
        _array(a["step_" + name], (k, n), name)
        if name != "balance_residual_m3" and np.any(a["step_" + name] < 0.):
            raise ValueError("negative sediment step quantity")
    _array(a["initial_mobile_solid_m3"], (n,), "initial mobile", nonnegative=True)
    _array(a["step_dt_seconds"], (k,), "step dt", positive=True)
    _array(a["cumulative_exported_solid_m3"], (k + 1,), "cumulative export", nonnegative=True)
    if not np.array_equal(a["step_dt_seconds"], np.diff(time)) or not np.allclose(a["trace_mobile_solid_m3"][0], a["initial_mobile_solid_m3"], rtol=0, atol=0):
        raise ValueError("initial state or step times mismatch")
    initial_loose = domain.initial_alluvium_bulk_m3 * (1. - material.porosity)
    for name, reference in (("bed_alluvium_solid_m3", initial_loose), ("rock_removed_m3", np.zeros(n)),
                            ("bed_elevation_m", domain.bed_elevation_m)):
        if not np.allclose(a["trace_" + name][0], reference, rtol=0, atol=1e-12):
            raise ValueError("initial sediment geometry mismatch")
    # A fixed block bounds temporary memory while eliminating Python work per step.
    for start in range(0, k, 64):
        stop = min(start + 64, k)
        current_time = time[start:stop]
        following_time = time[start + 1:stop + 1]
        interval = np.minimum(np.searchsorted(forcing.time_seconds, current_time, side="right") - 1, forcing.time_seconds.size - 2)
        segment_end = forcing.time_seconds[interval + 1]
        if np.any(following_time > segment_end + 1e-12):
            raise ValueError("step crosses forcing boundary")
        actual_dt = a["step_dt_seconds"][start:stop]
        if np.any(actual_dt > config.max_dt_seconds * (1. + 1e-12)):
            raise ValueError("sediment maximum time step exceeded")
        mobile = a["trace_mobile_solid_m3"][start:stop]
        loose = a["trace_bed_alluvium_solid_m3"][start:stop]
        rock = a["trace_rock_removed_m3"][start:stop]
        rates = _rates(domain, forcing, material, interval, mobile, loose, rock)
        if not all(np.isfinite(rate).all() for rate in rates):
            raise ValueError("nonfinite committed sediment rates")
        donor_dt = np.where(mobile > 0., config.cfl * mobile / (rates[2] + rates[3] + 1e-300), np.inf)
        dt = np.minimum(np.minimum(config.max_dt_seconds, segment_end - current_time), np.min(donor_dt, axis=1))
        expected_time = _bounded_next_time(current_time, dt, segment_end, legacy=m["algorithm"] == LEGACY_ALGORITHM)
        if (not np.isfinite(dt).all() or np.any(dt <= 0.)
                or np.any((dt < config.min_dt_seconds) & (segment_end - current_time > config.min_dt_seconds))
                or np.any(current_time + dt == current_time) or not np.array_equal(expected_time, following_time)):
            raise ValueError("committed sediment time step does not match declared controls")
        candidate, reason = _candidate(domain, forcing, material, config, interval, actual_dt[:,None], mobile, loose, rock, rates=rates)
        if reason:
            raise ValueError("committed invalid sediment step: " + reason)
        for name in STATE_FIELDS:
            if not np.allclose(candidate[name], a["trace_" + name][start + 1:stop + 1], rtol=0, atol=1e-8 if name == "bed_elevation_m" else 1e-10):
                raise ValueError("sediment state ledger mismatch: " + name)
        for name in STEP_FIELDS:
            if not np.allclose(candidate[name], a["step_" + name][start:stop], rtol=1e-10, atol=1e-10):
                raise ValueError("sediment step ledger mismatch: " + name)
        if np.any(candidate["stability_number"] > config.cfl * (1. + 1e-12)):
            raise ValueError("sediment stability violation")
    export = np.concatenate(([0.], np.cumsum(np.sum(a["step_exported_solid_m3"], axis=1))))
    if not np.allclose(export, a["cumulative_exported_solid_m3"], rtol=1e-10, atol=1e-10):
        raise ValueError("cumulative export mismatch")
    left = np.sum(a["initial_mobile_solid_m3"] + initial_loose)
    left += np.sum(a["step_external_solid_m3"]) + np.sum(a["step_eroded_rock_m3"])
    right = np.sum(a["trace_mobile_solid_m3"][-1] + a["trace_bed_alluvium_solid_m3"][-1]) + export[-1]
    if not math.isfinite(left) or not math.isfinite(right) or not np.isfinite(export).all():
        raise ValueError("nonfinite aggregate sediment ledger")
    if abs(left - right) > 1e-8 * max(1., left):
        raise ValueError("global solid-volume balance mismatch")
    if m["last_time_seconds"] != time[-1] or m["requested_end_time_seconds"] != forcing.time_seconds[-1]:
        raise ValueError("sediment prefix times mismatch")
    if m["status"] == "complete":
        if m["failure_reason"] is not None or time[-1] != forcing.time_seconds[-1]:
            raise ValueError("invalid complete sediment trace")
        if m["uncompleted_from_seconds"] is not None or m["uncompleted_to_seconds"] is not None:
            raise ValueError("complete trace has unfinished range")
    elif m["status"] == "failed_prefix":
        if not isinstance(m["failure_reason"], str) or not m["failure_reason"] or time[-1] >= forcing.time_seconds[-1]:
            raise ValueError("invalid sediment failure prefix")
        if m["uncompleted_from_seconds"] != time[-1] or m["uncompleted_to_seconds"] != forcing.time_seconds[-1]:
            raise ValueError("failed trace unfinished range mismatch")
        _, _, witnessed_reason = _next_step(domain, forcing, material, config, time[-1],
            a["trace_mobile_solid_m3"][-1], a["trace_bed_alluvium_solid_m3"][-1],
            a["trace_rock_removed_m3"][-1], k, trace_limit, legacy=m["algorithm"] == LEGACY_ALGORITHM)
        if witnessed_reason != m["failure_reason"]:
            raise ValueError("unverified sediment failure reason")
    else:
        raise ValueError("invalid sediment status")
    if type(m["needs_geometry_and_hydraulic_revalidation"]) is not bool or m["needs_geometry_and_hydraulic_revalidation"] != bool(np.any(a["trace_bed_elevation_m"] != domain.bed_elevation_m)):
        raise ValueError("revalidation flag mismatch")
    if (m["frozen_water_bounded_approximation"] is not True or
            any(m[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"))):
        raise ValueError("sediment replay cannot certify hydraulics or publication")
    if m["lake_transport"] != "q_times_mobile_concentration_without_shear_capacity_or_entrainment":
        raise ValueError("lake transport semantics mismatch")


def save_sediment(path, bundle):
    save_bundle(path, bundle, validator=validate_sediment)


def load_sediment(path, *, expected_sha256):
    # MAX_BYTES bounds array payloads in the solver/validator. Archive members
    # also include up to 128 bounded NPY headers and the bounded JSON manifest.
    archive_bytes = MAX_BYTES + MAX_ARCHIVE_MEMBERS * MAX_NPY_HEADER_BYTES + MAX_METADATA
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_sediment, max_bytes=archive_bytes)
