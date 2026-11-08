"""Bounded physical channel geometry and piecewise-constant local forcing."""

from dataclasses import dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import readonly


MAX_CHANNEL_NODES = 4096
MAX_FORCING_BYTES = 128 * 1024 * 1024
TERMINAL_KINDS = ("interior", "open_outflow", "closed_wall", "unknown_boundary")
GEOMETRY_SEMANTICS = {
    "length_m": "storage_control_length_not_receiver_distance",
    "receiver_distance_m": "positive_horizontal_receiver_distance_zero_at_terminals",
    "bed_slope": "interior_bed_drop_over_receiver_distance",
    "open_outflow_slope": "prescribed_positive_boundary_gradient_no_receiver",
}


def receiver_distances(node_xz_m, receiver):
    distance = np.zeros(receiver.size, np.float64)
    interior = receiver >= 0
    distance[interior] = np.linalg.norm(node_xz_m[interior] - node_xz_m[receiver[interior]], axis=1)
    return distance


def validate_receiver_acyclic(receiver):
    """Visit each receiver once, including DAGs whose indices are not sorted."""
    color = np.zeros(receiver.size, np.uint8)
    for start in range(receiver.size):
        node = start
        path = []
        while node >= 0 and color[node] == 0:
            color[node] = 1
            path.append(node)
            node = int(receiver[node])
        if node >= 0 and color[node] == 1:
            raise ValueError("receiver graph must be acyclic")
        color[path] = 2


def validate_channel_geometry_identity(receiver, bed, slope, distance):
    """Check physical edges, not finite-volume storage control lengths."""
    if (not isinstance(distance, np.ndarray) or distance.dtype != np.float64
            or distance.shape != receiver.shape or not np.isfinite(distance).all()):
        raise ValueError("finite float64 receiver_distance_m required")
    interior = receiver >= 0
    if np.any(distance[interior] <= 0.) or np.any(distance[~interior] != 0.):
        raise ValueError("receiver distance must be positive on edges and zero at terminals")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        drop = bed[interior] - bed[receiver[interior]]
        expected = drop / distance[interior]
    if not np.isfinite(expected).all() or np.any(drop <= 0.):
        raise ValueError("channel receiver bed must be strictly downhill")
    if not np.allclose(slope[interior], expected, rtol=1e-9, atol=0.):
        raise ValueError("channel bed slope inconsistent with receiver geometry")


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("lowercase SHA256 required")


def _float_array(value, shape, name, *, positive=False, nonnegative=False):
    if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != shape:
        raise ValueError(name + " must be float64 with shape " + str(shape))
    if not np.isfinite(value).all() or (positive and np.any(value <= 0.)) or (nonnegative and np.any(value < 0.)):
        raise ValueError(name + " must contain finite physical values")
    return readonly(value)


@dataclass(frozen=True)
class ChannelNetwork:
    receiver: np.ndarray
    length_m: np.ndarray
    width_m: np.ndarray
    bed_elevation_m: np.ndarray
    bed_slope: np.ndarray
    roughness: np.ndarray
    max_depth_m: np.ndarray
    terminal_kind: np.ndarray
    source_identity_sha256: str
    section_source: str
    roughness_source: str
    receiver_distance_m: np.ndarray | None = None

    def __post_init__(self):
        receiver = self.receiver
        if not isinstance(receiver, np.ndarray) or receiver.dtype != np.int64 or receiver.ndim != 1 or not 1 <= receiver.size <= MAX_CHANNEL_NODES:
            raise ValueError("bounded int64 receiver array required")
        n = receiver.size
        if np.any((receiver < -1) | (receiver >= n) | (receiver == np.arange(n))):
            raise ValueError("invalid channel receiver")
        for name in ("length_m", "width_m", "bed_elevation_m", "bed_slope", "roughness", "max_depth_m"):
            value = _float_array(getattr(self, name), (n,), name,
                                 positive=name in ("length_m", "width_m", "roughness", "max_depth_m"),
                                 nonnegative=name == "bed_slope")
            object.__setattr__(self, name, value)
        kind = self.terminal_kind
        if not isinstance(kind, np.ndarray) or kind.shape != (n,) or kind.dtype.kind != "U":
            raise ValueError("Unicode terminal_kind array required")
        if not np.isin(kind, TERMINAL_KINDS).all():
            raise ValueError("unrecognized terminal_kind")
        if np.any((receiver == -1) != (kind != "interior")):
            raise ValueError("terminal_kind must match receiver topology")
        if np.any((self.bed_slope <= 0.) & np.isin(kind, ("interior", "open_outflow"))):
            raise ValueError("positive slope required for active transport and open outflow")
        validate_receiver_acyclic(receiver)
        _sha(self.source_identity_sha256)
        for name in ("section_source", "roughness_source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(name + " provenance required")
        object.__setattr__(self, "receiver", readonly(receiver))
        object.__setattr__(self, "terminal_kind", readonly(kind.astype("U24")))
        distance = self.receiver_distance_m
        if distance is None:
            distance = np.where(receiver >= 0, self.length_m, 0.)
        validate_channel_geometry_identity(receiver, self.bed_elevation_m, self.bed_slope, distance)
        object.__setattr__(self, "receiver_distance_m", readonly(distance))


@dataclass(frozen=True)
class ChannelForcing:
    time_seconds: np.ndarray
    local_q_m3_s: np.ndarray
    source_identity_sha256: str

    def __post_init__(self):
        time = self.time_seconds
        if not isinstance(time, np.ndarray) or time.dtype != np.float64 or time.ndim != 1 or not 2 <= time.size <= 100001 or not np.isfinite(time).all() or np.any(time < 0.) or not np.isfinite(np.diff(time)).all() or np.any(np.diff(time) <= 0.):
            raise ValueError("strictly increasing finite float64 physical times required")
        q = self.local_q_m3_s
        if not isinstance(q, np.ndarray) or q.dtype != np.float64 or q.ndim != 2 or q.shape[0] != time.size - 1 or not 1 <= q.shape[1] <= MAX_CHANNEL_NODES:
            raise ValueError("local discharge must be float64 [interval,node]")
        if q.nbytes + time.nbytes > MAX_FORCING_BYTES or not np.isfinite(q).all() or np.any(q < 0.):
            raise ValueError("local discharge exceeds resource or physical bounds")
        _sha(self.source_identity_sha256)
        object.__setattr__(self, "time_seconds", readonly(time))
        object.__setattr__(self, "local_q_m3_s", readonly(q))


@dataclass(frozen=True)
class ChannelConfig:
    max_dt_seconds: float = 1.
    cfl: float = .8
    max_steps: int = 100000
    min_dt_seconds: float = 1e-8

    def __post_init__(self):
        for name in ("max_dt_seconds", "cfl", "min_dt_seconds"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(value) or value <= 0.:
                raise ValueError(name + " must be finite positive")
            object.__setattr__(self, name, float(value))
        if self.cfl > 1. or self.min_dt_seconds > self.max_dt_seconds:
            raise ValueError("CFL or step bounds invalid")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 1_000_000:
            raise ValueError("max_steps must be a bounded positive integer")
