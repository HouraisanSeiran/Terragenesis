"""Bounded original-bed lake components with instantaneous common-stage projection.

Finite weirs move water between separate pools. Joined components equilibrate
instantaneously; their projection is an inventory redistribution, not a dt flux.
This reduced model does not solve Saint-Venant backwater.
"""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_natural_lakes import (
    DOMAIN_SCHEMA, _curves, _stage_at_volume, _volume_at_stage, _wet_state,
    validate_natural_lakes,
)

SCHEMA = "terragenesis-equilibrium-lake-support-v1"
ALGORITHM = "original-d4-saddle-instant-equilibrium-projection-v1"
MAX_BYTES = 128 * 1024 * 1024
DOMAIN_FIELDS = ("source_height_m", "source_valid_mask", "seed_cell_ids", "owner_grid",
                 "max_stage_m", "support_cell_ids", "internal_faces", "internal_crest_m",
                 "boundary_faces", "boundary_kinds", "boundary_crest_m", "unresolved_stage_limit_m")


@dataclass(frozen=True)
class EquilibriumLakeState:
    owner_volume_m3: np.ndarray
    component_id: np.ndarray

    def __post_init__(self):
        volume, component = self.owner_volume_m3, self.component_id
        if (not isinstance(volume, np.ndarray) or volume.dtype != np.float64 or volume.ndim != 1
                or not np.isfinite(volume).all() or np.any(volume < 0.)
                or not isinstance(component, np.ndarray) or component.dtype != np.int64
                or component.shape != volume.shape or np.any(component < 0.)):
            raise ValueError("finite owner inventory and int64 component labels required")
        object.__setattr__(self, "owner_volume_m3", readonly(volume))
        object.__setattr__(self, "component_id", readonly(component))


@dataclass(frozen=True)
class EquilibriumLakeForcing:
    time_seconds: np.ndarray
    local_q_m3_s: np.ndarray
    tailwater_stage_m: np.ndarray
    port_q_m3_s: np.ndarray
    source_identity_sha256: str
    provenance: str
    port_source_identity_sha256: str
    port_provenance: str

    def __post_init__(self):
        t = self.time_seconds
        if (not isinstance(t, np.ndarray) or t.dtype != np.float64 or t.ndim != 1
                or not 2 <= len(t) <= 100001 or not np.isfinite(t).all()
                or t[0] < 0. or np.any(np.diff(t) <= 0.)):
            raise ValueError("finite increasing forcing times required")
        for name in ("local_q_m3_s", "tailwater_stage_m", "port_q_m3_s"):
            value = getattr(self, name)
            if (not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.ndim != 2
                    or value.shape[0] != len(t) - 1 or not np.isfinite(value).all()
                    or name == "local_q_m3_s" and np.any(value < 0.)):
                raise ValueError("finite interval forcing invalid: " + name)
            object.__setattr__(self, name, readonly(value))
        if (not isinstance(self.source_identity_sha256, str) or len(self.source_identity_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.source_identity_sha256)
                or not isinstance(self.port_source_identity_sha256, str) or len(self.port_source_identity_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.port_source_identity_sha256)
                or not isinstance(self.provenance, str) or not self.provenance.strip()
                or not isinstance(self.port_provenance, str) or not self.port_provenance.strip()):
            raise ValueError("forcing source identity and provenance required")
        object.__setattr__(self, "time_seconds", readonly(t))


@dataclass(frozen=True)
class EquilibriumLakeConfig:
    max_dt_seconds: float = .5
    min_dt_seconds: float = 1e-8
    cfl: float = .5
    max_steps: int = 20000

    def __post_init__(self):
        for name in ("max_dt_seconds", "min_dt_seconds", "cfl"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.:
                raise ValueError("finite positive lake step control required")
            object.__setattr__(self, name, float(value))
        if self.min_dt_seconds > self.max_dt_seconds or self.cfl > 1. or type(self.max_steps) is not int or not 1 <= self.max_steps <= 100000:
            raise ValueError("bounded lake step control required")


def _geometry(domain, volumes):
    arrays = domain["arrays"]
    terrain = domain["metadata"]["terrain_metadata"]
    area = terrain["dx_m"] * terrain["dz_m"]
    curves = _curves(arrays, area)
    stage = np.array([_stage_at_volume(curve, volume) for curve, volume in zip(curves, volumes)])
    return curves, stage


def _wet(domain, stage):
    return _wet_state(domain["arrays"], stage)


def _labels(count, edges):
    parent = np.arange(count, dtype=np.int64)
    def root(index):
        while parent[index] != index:
            index = int(parent[index])
        return index
    for first, second in edges:
        a, b = root(first), root(second)
        parent[max(a, b)] = min(a, b)
    roots = [root(index) for index in range(count)]
    unique = {value: index for index, value in enumerate(sorted(set(roots)))}
    return np.array([unique[value] for value in roots], np.int64)


def _combined_stage(curves, members, total):
    low = min(curves[i][0][0] for i in members)
    high = max(_stage_at_volume(curves[i], total) for i in members)
    for _ in range(64):
        middle = (low + high) / 2.
        if sum(_volume_at_stage(curves[i], middle) for i in members) < total:
            low = middle
        else:
            high = middle
    return (low + high) / 2.


def _paired_redistribution(domain, labels, delta, bridge_stage):
    arrays = domain["arrays"]
    owner = arrays["owner_grid"].ravel()
    n = len(labels)
    adjacency = [[] for _ in range(n)]
    for edge, (a, b) in enumerate(arrays["internal_faces"]):
        first, second = int(owner[a]), int(owner[b])
        crest = arrays["internal_crest_m"][edge]
        if (labels[first] == labels[second] and
                bridge_stage[first] >= crest - 1e-12 and bridge_stage[second] >= crest - 1e-12):
            adjacency[first].append((second, edge, 1.))
            adjacency[second].append((first, edge, -1.))
    paired = np.zeros(len(arrays["internal_faces"]), np.float64)
    visited = np.zeros(n, bool)
    for start in range(n):
        if visited[start]:
            continue
        visited[start] = True
        parent = {start: None}
        order = [start]
        for node in order:
            for neighbor, edge, sign in adjacency[node]:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    parent[neighbor] = (node, edge, sign)
                    order.append(neighbor)
        remainder = delta.copy()
        for node in reversed(order[1:]):
            parent_node, edge, sign = parent[node]
            paired[edge] = sign * remainder[node]
            remainder[parent_node] += remainder[node]
        if abs(remainder[start]) > 1e-8:
            raise ValueError("unpaired component projection inventory")
    return paired


def project_equilibrium_lakes(domain, owner_volume_m3, previous_component=None, *, _validated=False):
    """Return projected state and signed per-owner redistribution in m3."""
    if not _validated:
        validate_natural_lakes(domain)
    arrays = domain["arrays"]
    n = len(arrays["seed_cell_ids"])
    volume = np.asarray(owner_volume_m3)
    if volume.dtype != np.float64 or volume.shape != (n,) or not np.isfinite(volume).all() or np.any(volume < 0.):
        raise ValueError("finite nonnegative native owner volumes required")
    previous = np.arange(n, dtype=np.int64) if previous_component is None else np.asarray(previous_component)
    if previous.dtype != np.int64 or previous.shape != (n,) or np.any(previous < 0.):
        raise ValueError("previous component labels invalid")
    curves, individual = _geometry(domain, volume)
    owner = arrays["owner_grid"].ravel()
    faces = [(int(owner[a]), int(owner[b]), float(crest))
             for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"])]
    labels = previous.copy()
    # Prior components use aggregate head while deciding whether their saddle
    # remains wet; separate components use each side's own stage.
    group_stage = {}
    for label in np.unique(labels):
        members = np.flatnonzero(labels == label)
        group_stage[int(label)] = _combined_stage(curves, members, float(volume[members].sum()))
    active = []
    for first, second, crest in faces:
        if group_stage[int(labels[first])] >= crest - 1e-12 and group_stage[int(labels[second])] >= crest - 1e-12:
            active.append((first, second))
    labels = _labels(n, active)
    for _ in range(n):
        stage = np.array([_combined_stage(curves, np.flatnonzero(labels == label),
                          float(volume[labels == label].sum())) for label in range(labels.max() + 1)])
        new_edges = [(first, second) for first, second, crest in faces
                     if stage[labels[first]] >= crest - 1e-12 and stage[labels[second]] >= crest - 1e-12]
        updated = _labels(n, new_edges)
        if np.array_equal(updated, labels):
            break
        labels = updated
    else:
        raise ValueError("lake component projection did not settle")
    result = volume.copy()
    for label in np.unique(labels):
        members = np.flatnonzero(labels == label)
        if len(members) > 1:
            level = _combined_stage(curves, members, float(volume[members].sum()))
            result[members] = [_volume_at_stage(curves[i], level) for i in members]
            result[members[-1]] += float(volume[members].sum() - result[members].sum())
    if np.any(result < -1e-10):
        raise ValueError("negative equilibrium projection inventory")
    result = np.maximum(result, 0.)
    return EquilibriumLakeState(result, labels), result - volume


def _checked(domain, state, forcing=None):
    n = len(domain["arrays"]["seed_cell_ids"])
    if not isinstance(state, EquilibriumLakeState) or state.owner_volume_m3.shape != (n,):
        raise ValueError("bounded equilibrium state required")
    projected, redistribution = project_equilibrium_lakes(domain, state.owner_volume_m3,
                                                          state.component_id, _validated=True)
    if not np.array_equal(projected.component_id, state.component_id) or not np.allclose(redistribution, 0., rtol=0., atol=1e-9):
        raise ValueError("state is not at component equilibrium")
    curves, stage = _geometry(domain, state.owner_volume_m3)
    arrays = domain["arrays"]
    if np.any(state.owner_volume_m3 > np.array([_volume_at_stage(c, h) for c, h in zip(curves, arrays["max_stage_m"])]) + 1e-10):
        raise ValueError("finite natural lake support exceeded")
    if np.any(stage > arrays["unresolved_stage_limit_m"] + 1e-10):
        raise ValueError("unknown exterior face crest reached")
    if forcing is not None:
        if (not isinstance(forcing, EquilibriumLakeForcing)
                or forcing.source_identity_sha256 != domain["metadata"]["source_identity_sha256"]
                or forcing.local_q_m3_s.shape[1] != n or forcing.port_q_m3_s.shape[1] != n
                or forcing.tailwater_stage_m.shape[1] != len(arrays["boundary_faces"])):
            raise ValueError("equilibrium forcing/source dimensions mismatch")
    return stage


def _trace_bytes(domain, forcing, steps):
    arrays = domain["arrays"]
    n = len(arrays["seed_cell_ids"])
    faces = len(arrays["internal_faces"])
    boundary = len(arrays["boundary_faces"])
    support = len(arrays["support_cell_ids"])
    static = sum(value.nbytes for value in arrays.values())
    static += sum(getattr(forcing, key).nbytes for key in
                  ("time_seconds", "local_q_m3_s", "tailwater_stage_m", "port_q_m3_s"))
    static += 8 * (2 * n + faces)
    state = 8 * (3 * n) + support + 8 * n
    step = 8 * (faces + boundary + 2 * n + faces + 1)
    return static + state + 8 + steps * (state + step + 16)


def advance_equilibrium_lakes(domain, state, dt_seconds, local_q_m3_s, tailwater_stage_m,
                              port_q_m3_s, *, cfl=1., _validated=False):
    """Advance one explicit interval; port rates are externally paired channel fluxes."""
    if not _validated:
        validate_natural_lakes(domain)
    stage = _checked(domain, state)
    arrays = domain["arrays"]
    n, nb = len(stage), len(arrays["boundary_faces"])
    local = np.asarray(local_q_m3_s, np.float64)
    tail = np.asarray(tailwater_stage_m, np.float64)
    port = np.asarray(port_q_m3_s, np.float64)
    if (not math.isfinite(dt_seconds) or dt_seconds <= 0. or not 0. < cfl <= 1.
            or local.shape != (n,) or tail.shape != (nb,) or port.shape != (n,)
            or not np.isfinite(local).all() or not np.isfinite(tail).all()
            or not np.isfinite(port).all() or np.any(local < 0.)):
        raise ValueError("finite bounded step forcing required")
    owner = arrays["owner_grid"].ravel()
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    internal = np.zeros(len(arrays["internal_faces"]))
    boundary = np.zeros(nb)
    rate = local + port
    outgoing = np.maximum(-port, 0.)
    for index, (a, b) in enumerate(arrays["internal_faces"]):
        first, second = int(owner[a]), int(owner[b])
        if state.component_id[first] == state.component_id[second]:
            continue
        difference = stage[first] - stage[second]
        if difference:
            high, low = max(stage[first], stage[second]), min(stage[first], stage[second])
            q = math.copysign(coefficient * max(high - max(arrays["internal_crest_m"][index], low), 0.) ** 1.5, difference)
            internal[index] = q
            rate[first] -= q
            rate[second] += q
            outgoing[first] += max(q, 0.)
            outgoing[second] += max(-q, 0.)
    for index, (cell, _) in enumerate(arrays["boundary_faces"]):
        lake = int(owner[cell])
        kind, crest = arrays["boundary_kinds"][index], arrays["boundary_crest_m"][index]
        if kind == "free_outflow":
            q = coefficient * max(stage[lake] - crest, 0.) ** 1.5
        elif kind == "tailwater":
            difference = stage[lake] - tail[index]
            high, low = max(stage[lake], tail[index]), min(stage[lake], tail[index])
            q = math.copysign(coefficient * max(high - max(crest, low), 0.) ** 1.5, difference) if difference else 0.
        else:
            q = 0.
        boundary[index] = q
        rate[lake] -= q
        outgoing[lake] += max(q, 0.)
    volume = state.owner_volume_m3
    curves, _ = _geometry(domain, volume)
    for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
        first, second = int(owner[a]), int(owner[b])
        if state.component_id[first] != state.component_id[second]:
            continue
        members = np.flatnonzero(state.component_id == state.component_id[first])
        threshold = sum(_volume_at_stage(curves[i], crest) for i in members)
        start_total = float(volume[members].sum())
        next_total = start_total + dt_seconds * float(rate[members].sum())
        if start_total > threshold + 1e-9 and next_total < threshold - 1e-9:
            raise ValueError("step crosses equilibrium saddle event")
    ratio = np.divide(outgoing, volume, out=np.zeros_like(volume), where=volume > 0.)
    stability = float(dt_seconds * np.max(ratio))
    if stability > cfl * (1. + 1e-12):
        raise ValueError("water donor stability bound exceeded")
    raw = volume + dt_seconds * rate
    if not np.isfinite(raw).all() or np.any(raw < 0.):
        raise ValueError("negative or nonfinite water inventory")
    # A joined pool stays level until its common stage reaches a saddle. Once
    # its aggregate stock is below that saddle, the prior crest allocation is
    # retained and each newly separated side receives only its own forcing.
    balanced = raw.copy()
    curves, _ = _geometry(domain, raw)
    owner = arrays["owner_grid"].ravel()
    old_group_stage = {}
    for label in np.unique(state.component_id):
        members = np.flatnonzero(state.component_id == label)
        old_group_stage[int(label)] = _combined_stage(curves, members, float(raw[members].sum()))
    wet_old_edges = []
    for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
        first, second = int(owner[a]), int(owner[b])
        if (state.component_id[first] == state.component_id[second]
                and old_group_stage[int(state.component_id[first])] >= crest - 1e-12):
            wet_old_edges.append((first, second))
    retained = _labels(n, wet_old_edges)
    for label in np.unique(retained):
        members = np.flatnonzero(retained == label)
        if len(members) > 1:
            level = _combined_stage(curves, members, float(raw[members].sum()))
            balanced[members] = [_volume_at_stage(curves[i], level) for i in members]
            balanced[members[-1]] += float(raw[members].sum() - balanced[members].sum())
    next_state, _ = project_equilibrium_lakes(domain, balanced, state.component_id,
                                              _validated=True)
    redistribution = next_state.owner_volume_m3 - raw
    _checked(domain, next_state)
    old_edges = [(int(owner[a]), int(owner[b])) for a, b in arrays["internal_faces"]
                 if state.component_id[owner[a]] == state.component_id[owner[b]]]
    new_edges = [(int(owner[a]), int(owner[b])) for a, b in arrays["internal_faces"]
                 if next_state.component_id[owner[a]] == next_state.component_id[owner[b]]]
    paired_labels = _labels(n, old_edges + new_edges)
    bridge_stage = np.maximum(stage, _geometry(domain, next_state.owner_volume_m3)[1])
    paired = _paired_redistribution(domain, paired_labels, redistribution, bridge_stage)
    ledger = {"internal_q_m3_s": internal, "boundary_q_m3_s": boundary,
              "owner_rate_m3_s": rate, "redistribution_m3": redistribution,
              "redistribution_face_m3": paired,
              "stability_number": stability}
    return next_state, ledger


def _choose(domain, state, forcing, config, now):
    interval = min(int(np.searchsorted(forcing.time_seconds, now, side="right") - 1),
                   len(forcing.time_seconds) - 2)
    dt = min(config.max_dt_seconds, forcing.time_seconds[interval + 1] - now)
    reason = "minimum step or time resolution exhausted"
    while dt >= config.min_dt_seconds and now + dt > now:
        try:
            result = advance_equilibrium_lakes(domain, state, dt,
                forcing.local_q_m3_s[interval], forcing.tailwater_stage_m[interval],
                forcing.port_q_m3_s[interval], cfl=config.cfl, _validated=True)
            trial_state, trial_ledger = result
            if not np.array_equal(trial_state.component_id, state.component_id):
                arrays = domain["arrays"]
                owner = arrays["owner_grid"].ravel()
                curves, _ = _geometry(domain, state.owner_volume_m3)
                event = dt
                for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
                    first, second = int(owner[a]), int(owner[b])
                    if (state.component_id[first] != state.component_id[second]
                            or trial_state.component_id[first] == trial_state.component_id[second]):
                        continue
                    members = np.flatnonzero(state.component_id == state.component_id[first])
                    rate = float(trial_ledger["owner_rate_m3_s"][members].sum())
                    threshold = sum(_volume_at_stage(curves[i], crest) for i in members)
                    if rate < 0.:
                        remaining = float(state.owner_volume_m3[members].sum()) - threshold
                        if remaining > 1e-9:
                            event = min(event, remaining / -rate)
                if 0. < event < dt:
                    if event < config.min_dt_seconds:
                        return None, 0., "saddle event below minimum step"
                    dt = event
                    result = advance_equilibrium_lakes(domain, state, dt,
                        forcing.local_q_m3_s[interval], forcing.tailwater_stage_m[interval],
                        forcing.port_q_m3_s[interval], cfl=config.cfl, _validated=True)
            return result, dt, None
        except ValueError as error:
            reason = str(error)
            if reason == "step crosses equilibrium saddle event":
                arrays = domain["arrays"]
                owner = arrays["owner_grid"].ravel()
                curves, _ = _geometry(domain, state.owner_volume_m3)
                # The event time is calculated from the unchanged explicit
                # rate, including local, port, boundary, and cross-pool flow.
                probe_dt = min(dt, config.min_dt_seconds)
                try:
                    _, probe_ledger = advance_equilibrium_lakes(domain, state, probe_dt,
                        forcing.local_q_m3_s[interval], forcing.tailwater_stage_m[interval],
                        forcing.port_q_m3_s[interval], cfl=config.cfl, _validated=True)
                except ValueError:
                    dt *= .5
                    continue
                event = dt
                for (a, b), crest in zip(arrays["internal_faces"], arrays["internal_crest_m"]):
                    first, second = int(owner[a]), int(owner[b])
                    if state.component_id[first] != state.component_id[second]:
                        continue
                    members = np.flatnonzero(state.component_id == state.component_id[first])
                    rate = float(probe_ledger["owner_rate_m3_s"][members].sum())
                    threshold = sum(_volume_at_stage(curves[i], crest) for i in members)
                    remaining = float(state.owner_volume_m3[members].sum()) - threshold
                    if rate < 0. and remaining > 1e-9:
                        event = min(event, remaining / -rate)
                if config.min_dt_seconds <= event < dt:
                    dt = event
                    continue
            dt *= .5
    return None, 0., reason + "; minimum step exhausted"


def solve_equilibrium_lakes(domain, forcing, initial_owner_volume_m3, config=None):
    config = EquilibriumLakeConfig() if config is None else config
    validate_natural_lakes(domain)
    raw_curves, raw_stage = _geometry(domain, np.asarray(initial_owner_volume_m3, np.float64))
    native = domain["arrays"]
    if (np.any(np.asarray(initial_owner_volume_m3) > np.array([
            _volume_at_stage(curve, upper) for curve, upper in zip(raw_curves, native["max_stage_m"])]) + 1e-10)
            or np.any(raw_stage > native["unresolved_stage_limit_m"] + 1e-10)):
        raise ValueError("initial owner inventory exceeds finite or known exterior support")
    initial, initial_redistribution = project_equilibrium_lakes(domain, initial_owner_volume_m3,
                                                                 _validated=True)
    initial_paired = _paired_redistribution(domain, initial.component_id, initial_redistribution,
                                           _geometry(domain, initial.owner_volume_m3)[1])
    _checked(domain, initial, forcing)
    if _trace_bytes(domain, forcing, 0) > MAX_BYTES:
        raise ValueError("equilibrium lake static byte budget exceeded")
    state = initial
    times = [float(forcing.time_seconds[0])]
    volumes = [state.owner_volume_m3.copy()]
    components = [state.component_id.copy()]
    stage = _geometry(domain, state.owner_volume_m3)[1]
    wet, wet_component = _wet(domain, stage)
    stages = [stage]
    wet_support = [wet]
    wet_components = [wet_component]
    step = {name: [] for name in ("internal_q_m3_s", "boundary_q_m3_s", "owner_rate_m3_s",
                                  "redistribution_m3", "redistribution_face_m3", "stability_number")}
    failure = None
    while times[-1] < forcing.time_seconds[-1]:
        if len(step["stability_number"]) >= config.max_steps:
            failure = "maximum step count exceeded"
            break
        if _trace_bytes(domain, forcing, len(step["stability_number"]) + 1) > MAX_BYTES:
            failure = "trace byte budget exhausted"
            break
        result, dt, failure = _choose(domain, state, forcing, config, times[-1])
        if failure:
            break
        state, ledger = result
        now = times[-1]
        interval = min(int(np.searchsorted(forcing.time_seconds, now, side="right") - 1),
                       len(forcing.time_seconds) - 2)
        end = forcing.time_seconds[interval + 1]
        times.append(float(end if now + dt >= end - 1e-12 else now + dt))
        volumes.append(state.owner_volume_m3.copy())
        components.append(state.component_id.copy())
        stage = _geometry(domain, state.owner_volume_m3)[1]
        wet, wet_component = _wet(domain, stage)
        stages.append(stage)
        wet_support.append(wet)
        wet_components.append(wet_component)
        for name, value in ledger.items():
            step[name].append(value.copy() if hasattr(value, "copy") else value)
    a = {"time_seconds": np.array(times, np.float64),
         "forcing_time_seconds": forcing.time_seconds,
         "forcing_local_q_m3_s": forcing.local_q_m3_s,
         "forcing_tailwater_stage_m": forcing.tailwater_stage_m,
         "forcing_port_q_m3_s": forcing.port_q_m3_s,
         "initial_owner_volume_m3": np.asarray(initial_owner_volume_m3, np.float64).copy(),
         "initial_redistribution_m3": initial_redistribution,
         "initial_redistribution_face_m3": initial_paired,
         "trace_owner_volume_m3": np.array(volumes, np.float64),
         "trace_component_id": np.array(components, np.int64),
         "trace_owner_stage_m": np.array(stages, np.float64),
         "trace_wet_support": np.array(wet_support, bool),
         "trace_wet_component": np.array(wet_components, np.int64),
         "step_dt_seconds": np.diff(np.array(times, np.float64))}
    a.update({"domain_" + key: value for key, value in domain["arrays"].items()})
    for name, values in step.items():
        width = {"internal_q_m3_s": len(domain["arrays"]["internal_faces"]),
                 "boundary_q_m3_s": len(domain["arrays"]["boundary_faces"]),
                 "owner_rate_m3_s": len(initial.owner_volume_m3),
                 "redistribution_m3": len(initial.owner_volume_m3),
                 "redistribution_face_m3": len(domain["arrays"]["internal_faces"])}.get(name)
        a["step_" + name] = np.asarray(values, np.float64).reshape((len(values), width)) if width is not None else np.asarray(values, np.float64)
    a = {key: readonly(value) for key, value in a.items()}
    m = {"schema": SCHEMA, "algorithm": ALGORITHM,
         "domain_metadata": domain["metadata"], "domain_identity_sha256": domain["identity_sha256"],
         "forcing_source_identity_sha256": forcing.source_identity_sha256,
         "forcing_provenance": forcing.provenance, "config": asdict(config),
         "port_source_identity_sha256": forcing.port_source_identity_sha256,
         "port_provenance": forcing.port_provenance,
         "status": "failed_prefix" if failure else "complete", "failure_reason": failure,
         "requested_end_time_seconds": float(forcing.time_seconds[-1]),
         "last_time_seconds": times[-1],
         "hydraulic_model": "instant_equilibrium_components_and_finite_weir_not_saint_venant",
         "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    bundle = {"arrays": a, "metadata": m, "identity_sha256": identity(a, m)}
    validate_equilibrium_lakes(bundle)
    return bundle


def validate_equilibrium_lakes(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid equilibrium lake bundle")
    a, m = bundle["arrays"], bundle["metadata"]
    if m.get("schema") != SCHEMA or m.get("algorithm") != ALGORITHM or identity(a, m) != bundle["identity_sha256"]:
        raise ValueError("equilibrium lake identity mismatch")
    expected = ({"time_seconds", "forcing_time_seconds", "forcing_local_q_m3_s",
                 "forcing_tailwater_stage_m", "forcing_port_q_m3_s", "initial_owner_volume_m3",
                 "initial_redistribution_m3", "initial_redistribution_face_m3",
                 "trace_owner_volume_m3", "trace_component_id",
                 "trace_owner_stage_m", "trace_wet_support", "trace_wet_component",
                 "step_dt_seconds", "step_internal_q_m3_s", "step_boundary_q_m3_s",
                 "step_owner_rate_m3_s", "step_redistribution_m3",
                 "step_redistribution_face_m3", "step_stability_number"}
                | {"domain_" + key for key in DOMAIN_FIELDS})
    if (set(a) != expected or len(a) > 128 or
            any(any(axis > 8_000_000 for axis in value.shape) for value in a.values()) or
            sum(value.nbytes for value in a.values()) > MAX_BYTES):
        raise ValueError("equilibrium lake schema or budget mismatch")
    if any(m[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("equilibrium lake certification flags invalid")
    domain_arrays = {key: a["domain_" + key] for key in DOMAIN_FIELDS}
    domain = {"arrays": domain_arrays, "metadata": m["domain_metadata"],
              "identity_sha256": m["domain_identity_sha256"]}
    validate_natural_lakes(domain)
    forcing = EquilibriumLakeForcing(a["forcing_time_seconds"], a["forcing_local_q_m3_s"],
        a["forcing_tailwater_stage_m"], a["forcing_port_q_m3_s"],
        m["forcing_source_identity_sha256"], m["forcing_provenance"],
        m["port_source_identity_sha256"], m["port_provenance"])
    config = EquilibriumLakeConfig(**m["config"])
    initial, redistribution = project_equilibrium_lakes(domain, a["initial_owner_volume_m3"],
                                                        _validated=True)
    if not np.allclose(redistribution, a["initial_redistribution_m3"], rtol=0., atol=1e-9):
        raise ValueError("initial equilibrium projection mismatch")
    paired = _paired_redistribution(domain, initial.component_id, redistribution,
                                   _geometry(domain, initial.owner_volume_m3)[1])
    if not np.allclose(paired, a["initial_redistribution_face_m3"], rtol=0., atol=1e-9):
        raise ValueError("initial paired projection mismatch")
    time = a["time_seconds"]
    k = len(time) - 1
    n = len(domain_arrays["seed_cell_ids"])
    if (time.dtype != np.float64 or time.ndim != 1 or not np.isfinite(time).all()
            or np.any(np.diff(time) <= 0.) or time[0] != forcing.time_seconds[0]
            or not np.array_equal(a["step_dt_seconds"], np.diff(time))
            or a["trace_owner_volume_m3"].dtype != np.float64
            or a["trace_owner_volume_m3"].shape != (k + 1, n)
            or a["trace_component_id"].dtype != np.int64
            or a["trace_component_id"].shape != (k + 1, n)
            or a["trace_owner_stage_m"].dtype != np.float64
            or a["trace_owner_stage_m"].shape != (k + 1, n)
            or a["trace_wet_support"].dtype != np.bool_
            or a["trace_wet_support"].shape != (k + 1, len(domain_arrays["support_cell_ids"]))
            or a["trace_wet_component"].dtype != np.int64
            or a["trace_wet_component"].shape != (k + 1, n)
            or not np.array_equal(a["trace_owner_volume_m3"][0], initial.owner_volume_m3)
            or not np.array_equal(a["trace_component_id"][0], initial.component_id)):
        raise ValueError("equilibrium lake trace shape or initial state mismatch")
    shapes = {"internal_q_m3_s": (k, len(domain_arrays["internal_faces"])),
              "boundary_q_m3_s": (k, len(domain_arrays["boundary_faces"])),
              "owner_rate_m3_s": (k, n), "redistribution_m3": (k, n),
              "redistribution_face_m3": (k, len(domain_arrays["internal_faces"])),
              "stability_number": (k,)}
    for name, shape in shapes.items():
        value = a["step_" + name]
        if value.dtype != np.float64 or value.shape != shape or not np.isfinite(value).all():
            raise ValueError("equilibrium lake step schema mismatch")
    for i in range(k + 1):
        state = EquilibriumLakeState(a["trace_owner_volume_m3"][i], a["trace_component_id"][i])
        _checked(domain, state, forcing)
        stage = _geometry(domain, state.owner_volume_m3)[1]
        wet, component = _wet(domain, stage)
        if (not np.allclose(a["trace_owner_stage_m"][i], stage, rtol=0., atol=1e-9)
                or not np.array_equal(a["trace_wet_support"][i], wet)
                or not np.array_equal(a["trace_wet_component"][i], component)):
            raise ValueError("equilibrium lake stage or wet footprint mismatch")
    for i in range(k):
        state = EquilibriumLakeState(a["trace_owner_volume_m3"][i], a["trace_component_id"][i])
        result, dt, reason = _choose(domain, state, forcing, config, time[i])
        if reason or not math.isclose(dt, a["step_dt_seconds"][i], rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("equilibrium lake step selection mismatch")
        next_state, ledger = result
        if (not np.allclose(next_state.owner_volume_m3, a["trace_owner_volume_m3"][i + 1], rtol=0., atol=1e-9)
                or not np.array_equal(next_state.component_id, a["trace_component_id"][i + 1])):
            raise ValueError("equilibrium lake next inventory or component mismatch")
        for name, value in ledger.items():
            if not np.allclose(value, a["step_" + name][i], rtol=0., atol=1e-9):
                raise ValueError("equilibrium lake flux or redistribution mismatch")
    if m["last_time_seconds"] != time[-1] or m["requested_end_time_seconds"] != forcing.time_seconds[-1]:
        raise ValueError("equilibrium lake time metadata mismatch")
    if m["status"] == "complete":
        if time[-1] != forcing.time_seconds[-1] or m["failure_reason"] is not None:
            raise ValueError("invalid complete equilibrium lake trace")
    elif m["status"] == "failed_prefix":
        if time[-1] >= forcing.time_seconds[-1] or not m["failure_reason"]:
            raise ValueError("invalid equilibrium lake failed prefix")
        if k >= config.max_steps:
            reason = "maximum step count exceeded"
        elif _trace_bytes(domain, forcing, k + 1) > MAX_BYTES:
            reason = "trace byte budget exhausted"
        else:
            state = EquilibriumLakeState(a["trace_owner_volume_m3"][-1], a["trace_component_id"][-1])
            _, _, reason = _choose(domain, state, forcing, config, time[-1])
        if reason != m["failure_reason"]:
            raise ValueError("equilibrium lake failed prefix lacks witness")
    else:
        raise ValueError("invalid equilibrium lake status")
    return True


def save_equilibrium_lakes(path, bundle):
    save_bundle(path, bundle, validator=validate_equilibrium_lakes)


def load_equilibrium_lakes(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256,
                       validator=validate_equilibrium_lakes, max_bytes=MAX_BYTES)
