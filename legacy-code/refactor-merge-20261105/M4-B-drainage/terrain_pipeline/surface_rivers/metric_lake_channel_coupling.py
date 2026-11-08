"""Bounded original-lake and rectangular-channel signed-port water coupling.

The port is a reduced finite conductance weir, not Saint-Venant backwater.
Positive port discharge moves water from channel to lake.
"""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.surface_rivers.metric_channel_geometry import (
    ARRAYS as GEOMETRY_ARRAYS, _modified_bed_slope, validate_channel_geometry,
)
from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork, GEOMETRY_SEMANTICS, receiver_distances
from terrain_pipeline.surface_rivers.metric_channel_product import NETWORK_FIELDS, LEGACY_NETWORK_FIELDS
from terrain_pipeline.surface_rivers.metric_natural_lakes import (
    DOMAIN_SCHEMA, _curves, _stage_at_volume, _volume_at_stage, _wet_state,
    validate_natural_lakes,
)

SCHEMA = "terragenesis-natural-lake-channel-port-v2"
ALGORITHM = "bounded-signed-level-pool-rectangular-channel-v1"
MAX_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class LakeChannelPort:
    boundary_face_index: int
    channel_node_index: int
    coefficient_m3_s_m15: float
    provenance: str

    def __post_init__(self):
        if type(self.boundary_face_index) is not int or self.boundary_face_index < 0:
            raise ValueError("nonnegative boundary face index required")
        if type(self.channel_node_index) is not int or self.channel_node_index < 0:
            raise ValueError("nonnegative channel node index required")
        if (isinstance(self.coefficient_m3_s_m15, bool) or
                not isinstance(self.coefficient_m3_s_m15, (int, float)) or
                not math.isfinite(self.coefficient_m3_s_m15) or self.coefficient_m3_s_m15 <= 0.):
            raise ValueError("finite positive port coefficient required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("port coefficient provenance required")


@dataclass(frozen=True)
class LakeChannelForcing:
    time_seconds: np.ndarray
    channel_local_q_m3_s: np.ndarray
    lake_local_q_m3_s: np.ndarray
    tailwater_stage_m: np.ndarray
    source_identity_sha256: str
    provenance: str

    def __post_init__(self):
        t = self.time_seconds
        if (not isinstance(t, np.ndarray) or t.dtype != np.float64 or t.ndim != 1 or
                not 2 <= len(t) <= 100001 or not np.isfinite(t).all() or t[0] < 0. or
                np.any(np.diff(t) <= 0.)):
            raise ValueError("finite increasing physical forcing times required")
        for name in ("channel_local_q_m3_s", "lake_local_q_m3_s", "tailwater_stage_m"):
            value = getattr(self, name)
            if (not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.ndim != 2 or
                    value.shape[0] != len(t) - 1 or not np.isfinite(value).all()):
                raise ValueError(name + " must be finite interval-node float64")
            if name != "tailwater_stage_m" and np.any(value < 0.):
                raise ValueError("negative local water source")
            object.__setattr__(self, name, readonly(value))
        if sum(x.nbytes for x in (t, self.channel_local_q_m3_s, self.lake_local_q_m3_s,
                                  self.tailwater_stage_m)) > MAX_BYTES // 2:
            raise ValueError("forcing byte budget exceeded")
        if (not isinstance(self.source_identity_sha256, str) or len(self.source_identity_sha256) != 64 or
                any(c not in "0123456789abcdef" for c in self.source_identity_sha256)):
            raise ValueError("source identity SHA256 required")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("forcing provenance required")
        object.__setattr__(self, "time_seconds", readonly(t))


@dataclass(frozen=True)
class LakeChannelConfig:
    max_dt_seconds: float = .5
    min_dt_seconds: float = 1e-8
    cfl: float = .5
    max_steps: int = 20000

    def __post_init__(self):
        for name in ("max_dt_seconds", "min_dt_seconds", "cfl"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.:
                raise ValueError("finite positive step control required")
            object.__setattr__(self, name, float(value))
        if self.min_dt_seconds > self.max_dt_seconds or self.cfl > 1.:
            raise ValueError("invalid step control bounds")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 1_000_000:
            raise ValueError("bounded step count required")


DOMAIN_FIELDS = ("source_height_m", "source_valid_mask", "seed_cell_ids", "owner_grid",
                 "max_stage_m", "support_cell_ids", "internal_faces", "internal_crest_m",
                 "boundary_faces", "boundary_kinds", "boundary_crest_m", "unresolved_stage_limit_m")
FORCING_FIELDS = ("time_seconds", "channel_local_q_m3_s", "lake_local_q_m3_s", "tailwater_stage_m")
STATE_FIELDS = ("channel_volume_m3", "lake_volume_m3", "channel_stage_m", "lake_stage_m",
                "channel_depth_m", "wet_support", "wet_component")
STEP_FIELDS = ("channel_q_m3_s", "lake_internal_q_m3_s", "port_q_m3_s",
               "boundary_q_m3_s", "channel_donor_q_m3_s", "lake_donor_q_m3_s",
               "channel_residual_m3", "lake_residual_m3", "stability_number")


def _mesh_sample(geometry, point):
    a = geometry["arrays"]
    vertices, triangles = a["vertices_xz_m"], a["triangles"]
    spacing = geometry["metadata"]["config"]["fine_spacing_m"]
    nx = int(triangles[2, 1])
    nz = int(triangles[0, 2]) // nx
    col = min(max(int(math.floor((point[0] - vertices[0, 0]) / spacing)), 0), nx - 2)
    row = min(max(int(math.floor((point[1] - vertices[0, 1]) / spacing)), 0), nz - 2)
    cell = row * (nx - 1) + col
    for tri_id in range(4 * cell, 4 * cell + 4):
        ids = triangles[tri_id]
        triangle = vertices[ids]
        matrix = np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0]))
        uv = np.linalg.solve(matrix, point - triangle[0])
        if min(1. - uv.sum(), uv[0], uv[1]) >= -1e-9:
            bed = a["bed_elevation_m"][ids]
            return float(bed[0] + uv @ (bed[1:] - bed[0]))
    raise ValueError("M5 channel node leaves represented mesh")


def _trace_bytes(domain, geometry, network, ports, forcing, steps):
    da = domain["arrays"]
    nc, nl = len(network.receiver), len(da["seed_cell_ids"])
    static = sum(value.nbytes for value in da.values())
    static += sum(value.nbytes for value in geometry["arrays"].values())
    static += sum(np.asarray(getattr(network, key)).astype("U24").nbytes
                  if key == "terminal_kind" else np.asarray(getattr(network, key)).nbytes
                  for key in NETWORK_FIELDS)
    static += sum(getattr(forcing, key).nbytes for key in FORCING_FIELDS)
    static += 8 * (nc + nl + 3 * len(ports))
    state = 8 * (3 * nc + 3 * nl) + len(da["support_cell_ids"])
    step = 8 * (3 * nc + 2 * nl + len(da["internal_faces"]) +
                len(ports) + len(da["boundary_faces"]) + 1)
    return static + state + 8 + steps * (state + step + 16)


def _checked_inputs(domain, geometry, network, ports, forcing, initial_channel, initial_lake, config):
    validate_natural_lakes(domain)
    validate_channel_geometry(geometry)
    if domain["metadata"]["schema"] != DOMAIN_SCHEMA or not isinstance(network, ChannelNetwork):
        raise ValueError("natural lake domain and channel network required")
    da, ga = domain["arrays"], geometry["arrays"]
    terrain = domain["metadata"]["terrain_metadata"]
    if not isinstance(forcing, LakeChannelForcing) or not isinstance(config, LakeChannelConfig):
        raise ValueError("typed forcing and config required")
    if (network.source_identity_sha256 != geometry["identity_sha256"] or
            forcing.source_identity_sha256 != domain["metadata"]["source_identity_sha256"] or
            geometry["metadata"]["source_identity_sha256"] != domain["metadata"]["source_identity_sha256"] or
            not np.array_equal(ga["source_height_m"], da["source_height_m"]) or
            not np.array_equal(ga["source_valid_mask"], da["source_valid_mask"]) or
            geometry["metadata"]["terrain_metadata"].get("vertical_datum") != domain["metadata"]["terrain_metadata"].get("vertical_datum")):
        raise ValueError("channel and natural lake source or vertical datum mismatch")
    nc, nl, nb = len(network.receiver), len(da["seed_cell_ids"]), len(da["boundary_faces"])
    if nc > 32 or nl > 16 or len(ports) > 32:
        raise ValueError("bounded lake-channel node count exceeded")
    if any(not isinstance(p, LakeChannelPort) for p in ports):
        raise ValueError("LakeChannelPort objects required")
    if (forcing.channel_local_q_m3_s.shape[1] != nc or forcing.lake_local_q_m3_s.shape[1] != nl or
            forcing.tailwater_stage_m.shape[1] != nb):
        raise ValueError("forcing node or face count mismatch")
    if (not np.array_equal(network.receiver, ga["receiver"]) or
            not np.array_equal(network.width_m, ga["width_m"])):
        raise ValueError("channel network topology or width differs from M5 geometry")
    expected_length = np.zeros(nc)
    if not np.allclose(network.receiver_distance_m, receiver_distances(ga["node_xz_m"], network.receiver), rtol=0., atol=1e-8):
        raise ValueError("channel receiver distances differ from M5 centerline")
    for node, target in enumerate(network.receiver):
        if target >= 0:
            half = np.linalg.norm(ga["node_xz_m"][node] - ga["node_xz_m"][target]) / 2.
            expected_length[node] += half
            expected_length[target] += half
    if np.any(expected_length <= 0.) or not np.allclose(network.length_m, expected_length, rtol=0., atol=1e-8):
        raise ValueError("channel lengths do not partition M5 centerline")
    vertex = ga["vertices_xz_m"]
    mesh_bed = ga["bed_elevation_m"]
    sampled = np.array([_mesh_sample(geometry, point) for point in ga["node_xz_m"]])
    if not np.allclose(network.bed_elevation_m, sampled, rtol=0., atol=1e-8):
        raise ValueError("channel bed differs from M5 represented bed")
    _modified_bed_slope(ga["node_xz_m"], network.receiver, vertex, ga["triangles"],
                        mesh_bed, geometry["metadata"]["config"]["fine_spacing_m"])
    for node, target in enumerate(network.receiver):
        if target >= 0:
            length = np.linalg.norm(ga["node_xz_m"][node] - ga["node_xz_m"][target])
            slope = (sampled[node] - sampled[target]) / length
            if not math.isclose(network.bed_slope[node], slope, rel_tol=0., abs_tol=1e-8):
                raise ValueError("channel slope differs from M5 represented bed")
    for node, kind in enumerate(network.terminal_kind):
        if kind == "open_outflow":
            donors = np.flatnonzero(network.receiver == node)
            if len(donors) != 1 or not math.isclose(network.bed_slope[node],
                                                    network.bed_slope[donors[0]], rel_tol=0., abs_tol=1e-8):
                raise ValueError("open terminal Manning slope lacks unique M5 edge extrapolation")
    for value, shape, name in ((initial_channel, (nc,), "initial channel"),
                               (initial_lake, (nl,), "initial lake")):
        if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != shape or not np.isfinite(value).all() or np.any(value < 0.):
            raise ValueError(name + " inventory invalid")
    if np.any(initial_channel > network.width_m * network.length_m * network.max_depth_m + 1e-10):
        raise ValueError("initial channel depth exceeds finite capacity")
    if np.any(initial_channel[network.terminal_kind == "unknown_boundary"] > 0.):
        raise ValueError("initial channel inventory reaches unknown terminal")
    area_m2 = terrain["dx_m"] * terrain["dz_m"]
    curves = _curves(da, area_m2)
    capacities = np.array([_volume_at_stage(curve, upper) for curve, upper in zip(curves, da["max_stage_m"])])
    if np.any(initial_lake > capacities + 1e-10):
        raise ValueError("initial natural lake inventory exceeds finite support")
    _, _, initial_stage, _, _ = _geometry(domain, network, initial_channel, initial_lake)
    if np.any(initial_stage > da["unresolved_stage_limit_m"] + 1e-10):
        raise ValueError("initial lake reaches unknown exterior face crest")
    if _trace_bytes(domain, geometry, network, ports, forcing, 0) > MAX_BYTES:
        raise ValueError("lake-channel static input byte budget exceeded")
    owner = da["owner_grid"].ravel()
    ids = ga["source_node_cell_ids"]
    if np.any(owner[ids] >= 0):
        raise ValueError("channel control overlaps natural lake storage support")
    # M5 stores the represented cut on canonical vertices. A positive cut on
    # an original lake support vertex would assign that prism to both stores.
    vertices = ga["vertices_xz_m"]
    terrain = domain["metadata"]["terrain_metadata"]
    gx = (vertices[:, 0] - terrain["x0_m"]) / terrain["dx_m"]
    gz = (vertices[:, 1] - terrain["z0_m"]) / terrain["dz_m"]
    rows, cols = da["owner_grid"].shape
    node_col = np.clip(np.rint(gx).astype(np.int64), 0, cols - 1)
    node_row = np.clip(np.rint(gz).astype(np.int64), 0, rows - 1)
    if np.any((da["owner_grid"][node_row, node_col] >= 0) &
              (ga["cut_depth_m"] > 1e-10)):
        raise ValueError("channel cut overlaps natural lake support")
    face_ids = [p.boundary_face_index for p in ports]
    nodes = [p.channel_node_index for p in ports]
    if len(set(face_ids)) != len(face_ids) or len(set(nodes)) != len(nodes):
        raise ValueError("duplicate lake-channel port face or node")
    for port in ports:
        face, node = port.boundary_face_index, port.channel_node_index
        if face >= nb or node >= nc or da["boundary_kinds"][face] != "tailwater" or network.receiver[node] != -1:
            raise ValueError("port must bind a tailwater face and terminal channel")
        lake_cell, neighbor_cell = da["boundary_faces"][face]
        if neighbor_cell < 0 or ids[node] != neighbor_cell or owner[lake_cell] < 0 or owner[neighbor_cell] >= 0:
            raise ValueError("port lacks matching original D4 lake/channel face")
        expected_xz = np.array([terrain["x0_m"] + neighbor_cell % cols * terrain["dx_m"],
                                terrain["z0_m"] + neighbor_cell // cols * terrain["dz_m"]])
        if not np.allclose(ga["node_xz_m"][node], expected_xz, rtol=0., atol=1e-9):
            raise ValueError("port terminal shifted away from original D4 outer neighbor")
        if forcing.tailwater_stage_m[:, face].any():
            raise ValueError("ported tailwater face cannot also receive external stage")
    unported_tail = np.flatnonzero(da["boundary_kinds"] == "tailwater")
    if any(face not in face_ids for face in unported_tail) and not np.isfinite(forcing.tailwater_stage_m[:, unported_tail]).all():
        raise ValueError("unported tailwater stage required")
    return nc, nl, nb


def _geometry(domain, network, channel_volume, lake_volume):
    da = domain["arrays"]
    area = network.width_m * network.length_m
    depth = channel_volume / area
    channel_stage = network.bed_elevation_m + depth
    cell_area = domain["metadata"]["terrain_metadata"]["dx_m"] * domain["metadata"]["terrain_metadata"]["dz_m"]
    curves = _curves(da, cell_area)
    lake_stage = np.array([_stage_at_volume(curve, volume) for curve, volume in zip(curves, lake_volume)])
    wet, component = _wet_state(da, lake_stage)
    return depth, channel_stage, lake_stage, wet, component


def _rates(domain, network, ports, forcing, interval, channel_volume, lake_volume):
    da = domain["arrays"]
    nc, nl = len(channel_volume), len(lake_volume)
    depth, channel_stage, lake_stage, _, _ = _geometry(domain, network, channel_volume, lake_volume)
    area = network.width_m * depth
    perimeter = network.width_m + 2. * depth
    radius = np.divide(area, perimeter, out=np.zeros(nc), where=perimeter > 0.)
    channel_q = np.zeros(nc)
    port_nodes = np.array([p.channel_node_index for p in ports], np.int64)
    active = np.isin(network.terminal_kind, ("interior", "open_outflow"))
    active[port_nodes] = False
    channel_q[active] = area[active] * radius[active] ** (2. / 3.) * np.sqrt(network.bed_slope[active]) / network.roughness[active]
    owner = da["owner_grid"].ravel()
    internal = np.zeros(len(da["internal_faces"]))
    coefficient = domain["metadata"]["weir_coefficient_m3_s_m15"]
    for e, (first_cell, second_cell) in enumerate(da["internal_faces"]):
        first, second = int(owner[first_cell]), int(owner[second_cell])
        difference = lake_stage[first] - lake_stage[second]
        if difference:
            high, low = max(lake_stage[first], lake_stage[second]), min(lake_stage[first], lake_stage[second])
            internal[e] = math.copysign(coefficient * max(high - max(da["internal_crest_m"][e], low), 0.) ** 1.5, difference)
    boundary = np.zeros(len(da["boundary_faces"]))
    port_faces = {p.boundary_face_index for p in ports}
    for e, (lake_cell, _) in enumerate(da["boundary_faces"]):
        if e in port_faces:
            continue
        lake = int(owner[lake_cell])
        kind, crest = da["boundary_kinds"][e], da["boundary_crest_m"][e]
        if kind == "free_outflow":
            boundary[e] = coefficient * max(lake_stage[lake] - crest, 0.) ** 1.5
        elif kind == "tailwater":
            tail = forcing.tailwater_stage_m[interval, e]
            difference = lake_stage[lake] - tail
            if difference:
                high, low = max(lake_stage[lake], tail), min(lake_stage[lake], tail)
                boundary[e] = math.copysign(coefficient * max(high - max(crest, low), 0.) ** 1.5, difference)
    port_q = np.zeros(len(ports))
    for index, port in enumerate(ports):
        face, node = port.boundary_face_index, port.channel_node_index
        lake = int(owner[da["boundary_faces"][face, 0]])
        difference = channel_stage[node] - lake_stage[lake]
        if difference:
            high, low = max(channel_stage[node], lake_stage[lake]), min(channel_stage[node], lake_stage[lake])
            crest = da["boundary_crest_m"][face]
            port_q[index] = math.copysign(port.coefficient_m3_s_m15 * max(high - max(crest, low), 0.) ** 1.5, difference)
            if (port_q[index] > 0. and channel_volume[node] <= 0.) or (port_q[index] < 0. and lake_volume[lake] <= 0.):
                port_q[index] = 0.
    if not all(np.isfinite(x).all() for x in (channel_q, internal, boundary, port_q)):
        raise ValueError("nonfinite reduced hydraulic discharge")
    return channel_q, internal, boundary, port_q


def _candidate(domain, network, ports, forcing, interval, dt, channel_volume, lake_volume):
    da = domain["arrays"]
    channel_q, internal_q, boundary_q, port_q = _rates(domain, network, ports, forcing, interval, channel_volume, lake_volume)
    owner = da["owner_grid"].ravel()
    channel_donor = np.zeros_like(channel_volume)
    lake_donor = np.zeros_like(lake_volume)
    outward_channel = channel_q.copy()
    outward_lake = np.zeros_like(lake_volume)
    receiver = network.receiver
    edges = receiver >= 0
    np.add.at(channel_donor, receiver[edges], channel_q[edges])
    for edge, (first_cell, second_cell) in enumerate(da["internal_faces"]):
        first, second = int(owner[first_cell]), int(owner[second_cell])
        lake_donor[first] -= internal_q[edge]
        lake_donor[second] += internal_q[edge]
        outward_lake[first] += max(internal_q[edge], 0.)
        outward_lake[second] += max(-internal_q[edge], 0.)
    for edge, (lake_cell, _) in enumerate(da["boundary_faces"]):
        lake_donor[int(owner[lake_cell])] -= boundary_q[edge]
        outward_lake[int(owner[lake_cell])] += max(boundary_q[edge], 0.)
    for index, port in enumerate(ports):
        lake = int(owner[da["boundary_faces"][port.boundary_face_index, 0]])
        channel_donor[port.channel_node_index] -= port_q[index]
        lake_donor[lake] += port_q[index]
        outward_channel[port.channel_node_index] += max(port_q[index], 0.)
        outward_lake[lake] += max(-port_q[index], 0.)
    channel_next = channel_volume + dt * (forcing.channel_local_q_m3_s[interval] + channel_donor - channel_q)
    lake_next = lake_volume + dt * (forcing.lake_local_q_m3_s[interval] + lake_donor)
    if not np.isfinite(channel_next).all() or not np.isfinite(lake_next).all():
        return None, "nonfinite water inventory"
    if np.any(channel_next < 0.) or np.any(lake_next < 0.):
        return None, "negative water inventory"
    if np.any(channel_next[network.terminal_kind == "unknown_boundary"] > 0.):
        return None, "unknown channel terminal reached"
    if np.any(channel_next > network.width_m * network.length_m * network.max_depth_m + 1e-10):
        return None, "channel depth capacity exceeded"
    area = domain["metadata"]["terrain_metadata"]["dx_m"] * domain["metadata"]["terrain_metadata"]["dz_m"]
    curves = _curves(da, area)
    capacities = np.array([_volume_at_stage(curve, upper) for curve, upper in zip(curves, da["max_stage_m"])])
    if np.any(lake_next > capacities + 1e-10):
        return None, "finite natural lake support exceeded"
    _, _, next_stage, _, _ = _geometry(domain, network, channel_next, lake_next)
    if np.any(next_stage > da["unresolved_stage_limit_m"] + 1e-10):
        return None, "unknown exterior face crest reached"
    channel_residual = channel_next - channel_volume - dt * (forcing.channel_local_q_m3_s[interval] + channel_donor - channel_q)
    lake_residual = lake_next - lake_volume - dt * (forcing.lake_local_q_m3_s[interval] + lake_donor)
    channel_ratio = np.divide(outward_channel, channel_volume, out=np.zeros_like(channel_volume), where=channel_volume > 0.)
    lake_ratio = np.divide(outward_lake, lake_volume, out=np.zeros_like(lake_volume), where=lake_volume > 0.)
    stability = dt * max(float(np.max(channel_ratio)), float(np.max(lake_ratio)))
    return dict(channel_volume_m3=channel_next, lake_volume_m3=lake_next,
                channel_q_m3_s=channel_q, lake_internal_q_m3_s=internal_q,
                boundary_q_m3_s=boundary_q, port_q_m3_s=port_q,
                channel_donor_q_m3_s=channel_donor, lake_donor_q_m3_s=lake_donor,
                channel_residual_m3=channel_residual, lake_residual_m3=lake_residual,
                stability_number=stability), None


def _choose_step(domain, network, ports, forcing, config, now, channel, lake):
    interval = min(int(np.searchsorted(forcing.time_seconds, now, side="right") - 1),
                   len(forcing.time_seconds) - 2)
    end = forcing.time_seconds[interval + 1]
    dt = min(config.max_dt_seconds, end - now)
    last_reason = "minimum step or time resolution exhausted"
    while dt >= config.min_dt_seconds and now + dt > now:
        try:
            trial, reason = _candidate(domain, network, ports, forcing, interval, dt, channel, lake)
        except ValueError as error:
            return None, 0., str(error)
        if reason is None and trial["stability_number"] <= config.cfl * (1. + 1e-12):
            return trial, dt, None
        last_reason = reason or "water donor stability bound exceeded"
        dt *= .5
    return None, 0., last_reason + "; minimum step exhausted"


def solve_lake_channel(domain, geometry, network, ports, forcing, initial_channel_volume_m3,
                       initial_lake_volume_m3, config=None):
    config = LakeChannelConfig() if config is None else config
    ports = tuple(ports)
    _checked_inputs(domain, geometry, network, ports, forcing, initial_channel_volume_m3,
                    initial_lake_volume_m3, config)
    channel, lake = initial_channel_volume_m3.copy(), initial_lake_volume_m3.copy()
    times = [float(forcing.time_seconds[0])]
    states = {name: [] for name in STATE_FIELDS}
    steps = {name: [] for name in STEP_FIELDS}
    def append_state():
        depth, cstage, lstage, wet, component = _geometry(domain, network, channel, lake)
        for name, value in (("channel_volume_m3", channel), ("lake_volume_m3", lake),
                            ("channel_stage_m", cstage), ("lake_stage_m", lstage),
                            ("channel_depth_m", depth), ("wet_support", wet),
                            ("wet_component", component)):
            states[name].append(value.copy())
    append_state()
    failure = None
    while times[-1] < forcing.time_seconds[-1]:
        if len(steps[STEP_FIELDS[0]]) >= config.max_steps:
            failure = "maximum step count exceeded"; break
        if _trace_bytes(domain, geometry, network, ports, forcing, len(steps[STEP_FIELDS[0]]) + 1) > MAX_BYTES:
            failure = "trace byte budget exhausted"; break
        now = times[-1]
        trial, dt, failure = _choose_step(domain, network, ports, forcing, config, now, channel, lake)
        if failure:
            break
        interval = min(int(np.searchsorted(forcing.time_seconds, now, side="right") - 1), len(forcing.time_seconds) - 2)
        end = forcing.time_seconds[interval + 1]
        channel, lake = trial["channel_volume_m3"], trial["lake_volume_m3"]
        for name in STEP_FIELDS:
            steps[name].append(trial[name].copy() if hasattr(trial[name], "copy") else trial[name])
        times.append(float(end if now + dt >= end else now + dt))
        append_state()
    arrays = {"trace_time_seconds": readonly(np.array(times, np.float64)),
              "forcing_time_seconds": forcing.time_seconds,
              "forcing_channel_local_q_m3_s": forcing.channel_local_q_m3_s,
              "forcing_lake_local_q_m3_s": forcing.lake_local_q_m3_s,
              "forcing_tailwater_stage_m": forcing.tailwater_stage_m,
              "initial_channel_volume_m3": readonly(initial_channel_volume_m3),
              "initial_lake_volume_m3": readonly(initial_lake_volume_m3),
              "port_face_index": readonly(np.array([p.boundary_face_index for p in ports], np.int64)),
              "port_channel_index": readonly(np.array([p.channel_node_index for p in ports], np.int64)),
              "port_coefficient": readonly(np.array([p.coefficient_m3_s_m15 for p in ports], np.float64))}
    arrays.update({"domain_" + key: value for key, value in domain["arrays"].items()})
    arrays.update({"geometry_" + key: value for key, value in geometry["arrays"].items()})
    arrays.update({"network_" + key: np.asarray(getattr(network, key)).copy() for key in NETWORK_FIELDS})
    arrays.update({"trace_" + key: readonly(np.asarray(values)) for key, values in states.items()})
    for key, values in steps.items():
        count = len(values)
        if key == "stability_number":
            arrays["step_" + key] = readonly(np.asarray(values, np.float64))
        else:
            width = {"channel_q_m3_s": len(channel), "lake_internal_q_m3_s": len(domain["arrays"]["internal_faces"]),
                     "port_q_m3_s": len(ports), "boundary_q_m3_s": len(domain["arrays"]["boundary_faces"]),
                     "channel_donor_q_m3_s": len(channel), "lake_donor_q_m3_s": len(lake),
                     "channel_residual_m3": len(channel), "lake_residual_m3": len(lake)}[key]
            arrays["step_" + key] = readonly(np.asarray(values, np.float64).reshape(count, width))
    arrays["step_dt_seconds"] = readonly(np.diff(arrays["trace_time_seconds"]))
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM, "domain_metadata": domain["metadata"],
                "geometry_semantics": dict(GEOMETRY_SEMANTICS),
                "geometry_metadata": geometry["metadata"], "domain_identity_sha256": domain["identity_sha256"],
                "geometry_identity_sha256": geometry["identity_sha256"],
                "network_source_identity_sha256": network.source_identity_sha256,
                "network_section_source": network.section_source, "network_roughness_source": network.roughness_source,
                "forcing_source_identity_sha256": forcing.source_identity_sha256,
                "forcing_provenance": forcing.provenance,
                "ports": [asdict(port) for port in ports], "config": asdict(config),
                "status": "failed_prefix" if failure else "complete", "failure_reason": failure,
                "last_time_seconds": times[-1], "requested_end_time_seconds": float(forcing.time_seconds[-1]),
                "hydraulic_model": "finite_level_pool_signed_port_not_saint_venant",
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    if len(arrays) > 128 or any(any(axis > 8_000_000 for axis in value.shape) for value in arrays.values()) or sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("lake-channel trace byte budget exceeded")
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_lake_channel(result)
    return result


def validate_lake_channel(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid lake-channel bundle")
    a, m = bundle["arrays"], bundle["metadata"]
    legacy = m.get("schema") == "terragenesis-natural-lake-channel-port-v1"
    fields = LEGACY_NETWORK_FIELDS if legacy else NETWORK_FIELDS
    if (m.get("schema") != ("terragenesis-natural-lake-channel-port-v1" if legacy else SCHEMA)
            or (not legacy and m.get("geometry_semantics") != GEOMETRY_SEMANTICS)
            or m.get("algorithm") != ALGORITHM or identity(a, m) != bundle["identity_sha256"]):
        raise ValueError("lake-channel identity mismatch")
    if len(a) > 128 or any(any(axis > 8_000_000 for axis in value.shape) for value in a.values()) or sum(value.nbytes for value in a.values()) > MAX_BYTES:
        raise ValueError("lake-channel byte budget exceeded")
    expected = ({"trace_time_seconds", "step_dt_seconds", "initial_channel_volume_m3",
                 "initial_lake_volume_m3", "port_face_index", "port_channel_index", "port_coefficient"}
                | {"forcing_" + key for key in FORCING_FIELDS}
                | {"trace_" + key for key in STATE_FIELDS}
                | {"step_" + key for key in STEP_FIELDS}
                | {"domain_" + key for key in DOMAIN_FIELDS}
                | {"geometry_" + key for key in GEOMETRY_ARRAYS}
                | {"network_" + key for key in fields})
    if set(a) != expected:
        raise ValueError("lake-channel array schema mismatch")
    if any(m[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("lake-channel certification flags invalid")
    domain_arrays = {key[7:]: value for key, value in a.items() if key.startswith("domain_")}
    geometry_arrays = {key[9:]: value for key, value in a.items() if key.startswith("geometry_")}
    domain = {"arrays": domain_arrays, "metadata": m["domain_metadata"], "identity_sha256": m["domain_identity_sha256"]}
    geometry = {"arrays": geometry_arrays, "metadata": m["geometry_metadata"], "identity_sha256": m["geometry_identity_sha256"]}
    values = {key: a["network_" + key] for key in fields}
    if legacy:
        values["receiver_distance_m"] = receiver_distances(geometry_arrays["node_xz_m"], values["receiver"])
    network = ChannelNetwork(**values,
                             source_identity_sha256=m["network_source_identity_sha256"],
                             section_source=m["network_section_source"], roughness_source=m["network_roughness_source"])
    forcing = LakeChannelForcing(a["forcing_time_seconds"], a["forcing_channel_local_q_m3_s"],
                                 a["forcing_lake_local_q_m3_s"], a["forcing_tailwater_stage_m"],
                                 m["forcing_source_identity_sha256"], m["forcing_provenance"])
    ports = tuple(LakeChannelPort(**entry) for entry in m["ports"])
    if (not np.array_equal(a["port_face_index"], [p.boundary_face_index for p in ports]) or
            not np.array_equal(a["port_channel_index"], [p.channel_node_index for p in ports]) or
            not np.array_equal(a["port_coefficient"], [p.coefficient_m3_s_m15 for p in ports])):
        raise ValueError("saved port mapping mismatch")
    config = LakeChannelConfig(**m["config"])
    nc, nl, nb = _checked_inputs(domain, geometry, network, ports, forcing,
                                 a["initial_channel_volume_m3"], a["initial_lake_volume_m3"], config)
    t = a["trace_time_seconds"]
    k = len(t) - 1
    if t.dtype != np.float64 or t.ndim != 1 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0.) or t[0] != forcing.time_seconds[0] or k > config.max_steps:
        raise ValueError("invalid committed lake-channel times")
    if not np.array_equal(a["step_dt_seconds"], np.diff(t)):
        raise ValueError("saved step duration mismatch")
    if (not np.array_equal(a["trace_channel_volume_m3"][0], a["initial_channel_volume_m3"]) or
            not np.array_equal(a["trace_lake_volume_m3"][0], a["initial_lake_volume_m3"])):
        raise ValueError("initial water inventory mismatch")
    shapes = {"channel_volume_m3": (k + 1, nc), "lake_volume_m3": (k + 1, nl),
              "channel_stage_m": (k + 1, nc), "lake_stage_m": (k + 1, nl),
              "channel_depth_m": (k + 1, nc), "wet_support": (k + 1, len(domain_arrays["support_cell_ids"])),
              "wet_component": (k + 1, nl)}
    for name, shape in shapes.items():
        value = a["trace_" + name]
        expected_dtype = np.dtype(bool if name == "wet_support" else np.int64 if name == "wet_component" else np.float64)
        if value.shape != shape or value.dtype != expected_dtype or (value.dtype.kind == "f" and not np.isfinite(value).all()):
            raise ValueError("lake-channel state shape or finite mismatch")
    if np.any(a["trace_channel_volume_m3"] < -1e-10) or np.any(a["trace_lake_volume_m3"] < -1e-10):
        raise ValueError("negative saved water inventory")
    step_shapes = {"channel_q_m3_s": (k, nc), "lake_internal_q_m3_s": (k, len(domain_arrays["internal_faces"])),
                   "port_q_m3_s": (k, len(ports)), "boundary_q_m3_s": (k, nb),
                   "channel_donor_q_m3_s": (k, nc), "lake_donor_q_m3_s": (k, nl),
                   "channel_residual_m3": (k, nc), "lake_residual_m3": (k, nl),
                   "stability_number": (k,)}
    for name, shape in step_shapes.items():
        value = a["step_" + name]
        if value.shape != shape or value.dtype != np.float64 or not np.isfinite(value).all():
            raise ValueError("lake-channel step shape or finite mismatch")
    for i in range(k + 1):
        depth, cstage, lstage, wet, component = _geometry(domain, network,
            a["trace_channel_volume_m3"][i], a["trace_lake_volume_m3"][i])
        for name, expected in (("channel_depth_m", depth), ("channel_stage_m", cstage),
                               ("lake_stage_m", lstage), ("wet_support", wet), ("wet_component", component)):
            equal = np.array_equal(a["trace_" + name][i], expected) if name in ("wet_support", "wet_component") else np.allclose(a["trace_" + name][i], expected, rtol=0., atol=1e-9)
            if not equal:
                raise ValueError("wet footprint or stage mismatch")
    for i in range(k):
        interval = min(int(np.searchsorted(forcing.time_seconds, t[i], side="right") - 1), len(forcing.time_seconds) - 2)
        if t[i + 1] > forcing.time_seconds[interval + 1] + 1e-10 or a["step_dt_seconds"][i] > config.max_dt_seconds * (1. + 1e-12):
            raise ValueError("step crosses forcing or max dt")
        chosen, chosen_dt, chosen_reason = _choose_step(domain, network, ports, forcing, config, t[i],
            a["trace_channel_volume_m3"][i], a["trace_lake_volume_m3"][i])
        if chosen_reason or not math.isclose(chosen_dt, a["step_dt_seconds"][i], rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("committed step differs from solver step selection")
        candidate, reason = _candidate(domain, network, ports, forcing, interval,
            a["step_dt_seconds"][i], a["trace_channel_volume_m3"][i], a["trace_lake_volume_m3"][i])
        if reason:
            raise ValueError("committed invalid water step: " + reason)
        if candidate["stability_number"] > config.cfl * (1. + 1e-12):
            raise ValueError("committed water donor stability bound exceeded")
        for name in STEP_FIELDS:
            if not np.allclose(a["step_" + name][i], candidate[name], rtol=0., atol=1e-9):
                raise ValueError("paired port or water ledger mismatch: " + name)
        for name in ("channel_volume_m3", "lake_volume_m3"):
            if not np.allclose(a["trace_" + name][i + 1], candidate[name], rtol=0., atol=1e-9):
                raise ValueError("next water inventory mismatch")
    if m["last_time_seconds"] != t[-1] or m["requested_end_time_seconds"] != forcing.time_seconds[-1]:
        raise ValueError("lake-channel time metadata mismatch")
    if m["status"] == "complete":
        if t[-1] != forcing.time_seconds[-1] or m["failure_reason"] is not None:
            raise ValueError("invalid complete lake-channel trace")
    elif m["status"] == "failed_prefix":
        if not m["failure_reason"] or t[-1] >= forcing.time_seconds[-1]:
            raise ValueError("invalid lake-channel failed prefix")
        if k >= config.max_steps:
            expected_failure = "maximum step count exceeded"
        elif _trace_bytes(domain, geometry, network, ports, forcing, k + 1) > MAX_BYTES:
            expected_failure = "trace byte budget exhausted"
        else:
            _, _, expected_failure = _choose_step(domain, network, ports, forcing, config,
                t[-1], a["trace_channel_volume_m3"][-1], a["trace_lake_volume_m3"][-1])
        if expected_failure != m["failure_reason"]:
            raise ValueError("failed prefix lacks physical failure witness")
    else:
        raise ValueError("invalid lake-channel status")
    return True


def save_lake_channel(path, bundle):
    save_bundle(path, bundle, validator=validate_lake_channel)


def load_lake_channel(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_lake_channel, max_bytes=MAX_BYTES)
