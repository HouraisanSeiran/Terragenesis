"""Bounded material-conserving PL bed, Manning and sediment recoupling."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.surface_rivers.metric_channel_product import (
    make_channel_product, validate_channel_product,
)
from terrain_pipeline.channel_geometry import _modified_bed_slope, validate_channel_geometry
from terrain_pipeline.surface_hydraulics import solve_channel
from terrain_pipeline.channel_geometry import ChannelConfig, ChannelForcing, ChannelNetwork, receiver_distances
from terrain_pipeline.surface_rivers.metric_sediment import (
    MaterialParameters, SedimentConfig, SedimentDomain, SedimentForcing,
    solve_sediment, validate_sediment,
)

SCHEMA = "terragenesis-morphology-coupling-v1"
ALGORITHM = "canonical-pl-exner-manning-recoupling-v1"
MAX_BYTES = 128 * 1024 * 1024
PAYLOAD_COLUMNS = 4096
STATE_KEYS = ("mesh_bed_m", "node_bed_m", "water_volume_m3", "mobile_solid_m3",
              "loose_solid_m3", "rock_removed_m3")


@dataclass(frozen=True)
class MorphologyConfig:
    max_intervals: int = 16
    max_cumulative_bed_change_m: float = .05
    max_depth_change_m: float = .05
    min_bed_slope: float = 1e-10

    def __post_init__(self):
        if type(self.max_intervals) is not int or not 1 <= self.max_intervals <= 256:
            raise ValueError("bounded morphology interval count required")
        for name in ("max_cumulative_bed_change_m", "max_depth_change_m", "min_bed_slope"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.:
                raise ValueError(name + " must be finite positive")
            object.__setattr__(self, name, float(value))


def _sample(vertices, triangles, values, point):
    tri = vertices[triangles]
    candidate = np.flatnonzero(np.all((point >= tri.min(axis=1) - 1e-9) &
                                     (point <= tri.max(axis=1) + 1e-9), axis=1))
    for index in candidate:
        triangle = tri[index]
        uv = np.linalg.solve(np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0])),
                             point - triangle[0])
        weight = np.array([1. - uv.sum(), uv[0], uv[1]])
        if weight.min() >= -1e-9:
            return np.asarray(values)[..., triangles[index]] @ weight
    raise ValueError("node or port outside canonical mesh")


def _sample_nodes(geometry, mesh_bed):
    a = geometry["arrays"]
    return np.array([_sample(a["vertices_xz_m"], a["triangles"], mesh_bed, point)
                     for point in a["node_xz_m"]], np.float64)


def _basis(geometry):
    a = geometry["arrays"]
    vertices, triangles, nodes = (a[key] for key in ("vertices_xz_m", "triangles", "node_xz_m"))
    cut = a["cut_depth_m"]
    n, v = len(nodes), len(vertices)
    if not 2 <= n <= 16 or v > 262144 or np.any(a["lake_mask"]):
        raise ValueError("bounded no-lake canonical geometry required")
    distances = np.sum((vertices[:, None, :] - nodes[None, :, :]) ** 2, axis=2)
    nearest = np.argmin(distances, axis=1)
    basis = np.zeros((n, v), np.float64)
    basis[nearest, np.arange(v)] = cut > 1e-10
    # At a centerline node, its containing triangle must be wholly owned by
    # that node. This makes interpolation cardinal without moving its XZ anchor.
    for i, point in enumerate(nodes):
        tri = vertices[triangles]
        candidate = np.flatnonzero(np.all((point >= tri.min(axis=1) - 1e-9) &
                                         (point <= tri.max(axis=1) + 1e-9), axis=1))
        found = False
        for index in candidate:
            try:
                sampled = _sample(vertices, triangles, basis, point)
            except ValueError:
                continue
            if sampled[i] > 0.999999 and np.max(np.delete(sampled, i)) < 1e-10:
                found = True
                break
        if not found:
            raise ValueError("nearest-control PL basis is not cardinal at node")
    xy = vertices[triangles]
    first, second = xy[:, 1] - xy[:, 0], xy[:, 2] - xy[:, 0]
    area = np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / 2.
    integrals = np.sum(area[None, :] * np.mean(basis[:, triangles], axis=2), axis=1)
    if not np.isfinite(integrals).all() or np.any(integrals <= 0.):
        raise ValueError("invalid exact PL basis material area")
    return basis, integrals, area


def _edge_slope(geometry, mesh_bed, i, j, minimum):
    a = geometry["arrays"]
    vertices, triangles, nodes = a["vertices_xz_m"], a["triangles"], a["node_xz_m"]
    p0, p1 = nodes[[i, j]]
    delta = p1 - p0
    length = float(np.linalg.norm(delta))
    edges = np.unique(np.sort(np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]],
                                               triangles[:, [2, 0]]), axis=0), axis=1), axis=0)
    start, end = vertices[edges[:, 0]], vertices[edges[:, 1]]
    segment = end - start
    cross = delta[0] * segment[:, 1] - delta[1] * segment[:, 0]
    offset = start - p0
    active = np.abs(cross) > 1e-14
    t = np.divide(offset[:, 0] * segment[:, 1] - offset[:, 1] * segment[:, 0], cross,
                  out=np.full(len(edges), np.nan), where=active)
    u = np.divide(offset[:, 0] * delta[1] - offset[:, 1] * delta[0], cross,
                  out=np.full(len(edges), np.nan), where=active)
    hits = active & (t > 1e-10) & (t < 1. - 1e-10) & (u >= -1e-10) & (u <= 1. + 1e-10)
    times = np.r_[0., t[hits], 1.]
    heights = np.r_[_sample(vertices, triangles, mesh_bed, p0),
                    mesh_bed[edges[hits, 0]] + u[hits] *
                    (mesh_bed[edges[hits, 1]] - mesh_bed[edges[hits, 0]]),
                    _sample(vertices, triangles, mesh_bed, p1)]
    order = np.argsort(times)
    times, heights = times[order], heights[order]
    distinct = np.r_[True, np.diff(times) > 1e-9]
    times, heights = times[distinct], heights[distinct]
    if np.any(np.diff(heights) >= -minimum * length * np.diff(times)):
        raise ValueError("updated PL bed has nonpositive continuous receiver slope")
    return float((heights[0] - heights[-1]) / length)


def _sections(geometry, mesh_bed, network, config):
    a = geometry["arrays"]
    node_bed = _sample_nodes(geometry, mesh_bed)
    _modified_bed_slope(a["node_xz_m"], network.receiver, a["vertices_xz_m"],
                        a["triangles"], mesh_bed, geometry["metadata"]["config"]["fine_spacing_m"])
    slope = network.bed_slope.copy()
    for i, j in enumerate(network.receiver):
        if j >= 0:
            length = np.linalg.norm(a["node_xz_m"][i] - a["node_xz_m"][j])
            slope[i] = (node_bed[i] - node_bed[j]) / length
            if slope[i] <= config.min_bed_slope:
                raise ValueError("updated PL bed slope below declared minimum")
    # Terminal Manning slope is an explicit extrapolation of its only incoming
    # edge. A branching terminal has no unique tangent and is refused.
    for i, j in enumerate(network.receiver):
        if j < 0 and network.terminal_kind[i] == "open_outflow":
            donors = np.flatnonzero(network.receiver == i)
            if len(donors) != 1:
                raise ValueError("open terminal needs one donor for slope extrapolation")
            slope[i] = slope[donors[0]]
    port_bed = np.array([[_sample(a["vertices_xz_m"], a["triangles"], mesh_bed, point)
                          for point in profile] for profile in a["canonical_port_profile_xz_m"]])
    if not np.isfinite(port_bed).all() or not np.isfinite(node_bed).all():
        raise ValueError("nonfinite shared section")
    return node_bed, slope, port_bed


def _geometry_id(parent, mesh_bed, version):
    return identity({"mesh_bed_m": np.asarray(mesh_bed, np.float64)},
                    {"parent_geometry_identity_sha256": parent, "version": version,
                     "algorithm": ALGORITHM})


def _network(base, node_bed, slope, geometry_id):
    return ChannelNetwork(base.receiver.copy(), base.length_m.copy(), base.width_m.copy(),
                          node_bed.copy(), slope.copy(), base.roughness.copy(),
                          base.max_depth_m.copy(), base.terminal_kind.copy(), geometry_id,
                          "recoupled canonical PL node bed and shared section", base.roughness_source,
                          receiver_distance_m=base.receiver_distance_m.copy())


def _water_distance(geometry, arrays):
    expected = receiver_distances(geometry["arrays"]["node_xz_m"], arrays["network_receiver"])
    distance = arrays.get("network_receiver_distance_m", expected)
    if not np.allclose(distance, expected, rtol=0., atol=1e-8):
        raise ValueError("water receiver distances differ from canonical centerline")
    return distance


def _validate_water(geometry, water):
    distance = _water_distance(geometry, water["arrays"])
    validate_channel_product(water, legacy_receiver_distance_m=
                             distance if "network_receiver_distance_m" not in water["arrays"] else None)


def _pack(arrays, metadata, name, bundle):
    layout = []
    chunks = []
    offset = 0
    for key, value in sorted(bundle["arrays"].items()):
        value = np.ascontiguousarray(value)
        if value.dtype.hasobject or value.ndim > 3 or value.nbytes > MAX_BYTES:
            raise ValueError("unsafe embedded bundle array")
        chunk = value.tobytes()
        layout.append({"name": key, "dtype": value.dtype.str, "shape": list(value.shape),
                       "start": offset, "stop": offset + len(chunk)})
        chunks.append(chunk)
        offset += len(chunk)
    if offset > MAX_BYTES:
        raise ValueError("embedded bundle exceeds byte budget")
    metadata[name] = {"metadata": bundle["metadata"], "identity_sha256": bundle["identity_sha256"],
                      "layout": layout, "payload_bytes": offset}
    rows = max(1, math.ceil(offset / PAYLOAD_COLUMNS))
    if rows > 8_000_000 or rows * PAYLOAD_COLUMNS > MAX_BYTES:
        raise ValueError("embedded payload exceeds archive bounds")
    payload = np.zeros((rows, PAYLOAD_COLUMNS), np.uint8)
    if offset:
        payload.ravel()[:offset] = np.frombuffer(b"".join(chunks), dtype=np.uint8)
    arrays[name + "__payload"] = readonly(payload)


def _unpack(arrays, metadata, name):
    pin = metadata[name]
    payload = arrays[name + "__payload"]
    if (payload.dtype != np.uint8 or payload.ndim != 2 or payload.shape[1] != PAYLOAD_COLUMNS
            or payload.shape[0] < 1 or payload.shape[0] > 8_000_000 or payload.size > MAX_BYTES):
        raise ValueError("invalid embedded bundle payload")
    valid_bytes = pin["payload_bytes"]
    if type(valid_bytes) is not int or valid_bytes < 0 or valid_bytes > payload.size:
        raise ValueError("embedded payload byte count invalid")
    flat = payload.ravel()
    if np.any(flat[valid_bytes:] != 0.) or payload.shape[0] != max(1, math.ceil(valid_bytes / PAYLOAD_COLUMNS)):
        raise ValueError("embedded payload padding invalid")
    values = {}
    last = 0
    for field in pin["layout"]:
        if set(field) != {"name", "dtype", "shape", "start", "stop"}:
            raise ValueError("invalid embedded array layout")
        key, shape = field["name"], field["shape"]
        if not isinstance(key, str) or not key or key in values or len(shape) > 3 or any(
                type(size) is not int or size < 0 or size > MAX_BYTES for size in shape):
            raise ValueError("invalid embedded array name or shape")
        dtype = np.dtype(field["dtype"])
        if dtype.hasobject or dtype.itemsize <= 0:
            raise ValueError("unsafe embedded array dtype")
        start, stop = field["start"], field["stop"]
        if type(start) is not int or type(stop) is not int or start != last or stop > valid_bytes or stop < start:
            raise ValueError("embedded array offsets invalid")
        if math.prod(shape) * dtype.itemsize != stop - start:
            raise ValueError("embedded array byte size mismatch")
        values[key] = readonly(np.frombuffer(flat[start:stop].tobytes(), dtype=dtype).reshape(shape))
        last = stop
    if last != valid_bytes:
        raise ValueError("embedded payload has unused bytes")
    return {"arrays": values,
            "metadata": pin["metadata"], "identity_sha256": pin["identity_sha256"]}


def couple_morphology(geometry, network, forcing, material, *, initial_water_volume_m3,
                      initial_mobile_solid_m3, initial_alluvium_bulk_m3, rock_floor_m,
                      external_solid_m3_s=None,
                      config=None, channel_config=None, sediment_config=None):
    """Commit complete water+sediment intervals and map Exner volumes onto PL triangles."""
    config = MorphologyConfig() if config is None else config
    channel_config = ChannelConfig() if channel_config is None else channel_config
    sediment_config = SedimentConfig() if sediment_config is None else sediment_config
    if not all(isinstance(x, t) for x, t in ((config, MorphologyConfig),
        (channel_config, ChannelConfig), (sediment_config, SedimentConfig),
        (network, ChannelNetwork), (forcing, ChannelForcing), (material, MaterialParameters))):
        raise ValueError("typed morphology inputs required")
    if geometry.get("metadata", {}).get("geometry_verified") is not True:
        raise ValueError("accepted M5 geometry required")
    validate_channel_geometry(geometry)
    a = geometry["arrays"]
    n = len(network.receiver)
    if n != len(a["receiver"]) or not np.array_equal(network.receiver, a["receiver"]):
        raise ValueError("network receiver differs from canonical geometry")
    if forcing.local_q_m3_s.shape[1] != n or len(forcing.time_seconds) - 1 > config.max_intervals:
        raise ValueError("forcing outside bounded morphology interval count")
    if network.source_identity_sha256 != geometry["identity_sha256"] or not np.array_equal(network.width_m, a["width_m"]):
        raise ValueError("hydraulic section geometry identity mismatch")
    for name, value in (("initial_water_volume_m3", initial_water_volume_m3),
                        ("initial_mobile_solid_m3", initial_mobile_solid_m3),
                        ("initial_alluvium_bulk_m3", initial_alluvium_bulk_m3),
                        ("rock_floor_m", rock_floor_m)):
        if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != (n,) or not np.isfinite(value).all():
            raise ValueError(name + " requires finite float64 node array")
    if external_solid_m3_s is None:
        external_solid_m3_s = np.zeros_like(forcing.local_q_m3_s)
    if (not isinstance(external_solid_m3_s, np.ndarray) or external_solid_m3_s.dtype != np.float64
            or external_solid_m3_s.shape != forcing.local_q_m3_s.shape or not np.isfinite(external_solid_m3_s).all()
            or np.any(external_solid_m3_s < 0.)):
        raise ValueError("external solid forcing must be finite nonnegative interval-node rates")
    if any(np.any(x < 0.) for x in (initial_water_volume_m3, initial_mobile_solid_m3, initial_alluvium_bulk_m3)):
        raise ValueError("negative initial inventory")
    basis, areas, triangle_area = _basis(geometry)
    if not np.allclose(network.receiver_distance_m, receiver_distances(a["node_xz_m"], network.receiver), rtol=0., atol=1e-8):
        raise ValueError("network receiver distances differ from canonical centerline")
    expected_lengths = np.zeros(n, np.float64)
    for i, j in enumerate(network.receiver):
        if j >= 0:
            half = np.linalg.norm(a["node_xz_m"][i] - a["node_xz_m"][j]) / 2.
            expected_lengths[i] += half
            expected_lengths[j] += half
    if np.any(expected_lengths <= 0.) or not np.allclose(network.length_m, expected_lengths, rtol=0., atol=1e-8):
        raise ValueError("hydraulic lengths must partition canonical centerline edges")
    if np.any(areas < network.width_m * network.length_m - 1e-9):
        raise ValueError("material basis area below hydraulic control area")
    mesh = a["bed_elevation_m"].copy()
    node_bed, slope, ports = _sections(geometry, mesh, network, config)
    if not np.allclose(node_bed, network.bed_elevation_m, rtol=0., atol=1e-8):
        raise ValueError("initial network bed differs from M5 canonical mesh")
    if not np.allclose(slope, network.bed_slope, rtol=0., atol=1e-8):
        raise ValueError("initial network slope differs from continuous PL bed")
    if np.any(node_bed - initial_alluvium_bulk_m3 / areas < rock_floor_m - 1e-10):
        raise ValueError("initial alluvium exceeds geological rock reserve")
    water_volume = initial_water_volume_m3.copy()
    mobile = initial_mobile_solid_m3.copy()
    loose = initial_alluvium_bulk_m3 * (1. - material.porosity)
    rock_removed = np.zeros(n)
    original_mesh = mesh.copy()
    initial_node_bed = node_bed.copy()
    states = {"mesh_bed_m": [mesh.copy()], "node_bed_m": [node_bed.copy()],
              "water_volume_m3": [water_volume.copy()], "mobile_solid_m3": [mobile.copy()],
              "loose_solid_m3": [loose.copy()], "rock_removed_m3": [rock_removed.copy()]}
    arrays = {"basis": readonly(basis), "material_area_m2": readonly(areas),
              "triangle_area_m2": readonly(triangle_area),
              "source_mesh_bed_m": readonly(original_mesh),
              "source_node_bed_m": readonly(initial_node_bed),
              "rock_floor_m": readonly(rock_floor_m),
              "forcing_time_seconds": readonly(forcing.time_seconds),
              "forcing_local_q_m3_s": readonly(forcing.local_q_m3_s),
              "forcing_external_solid_m3_s": readonly(external_solid_m3_s)}
    meta = {"schema": SCHEMA, "algorithm": ALGORITHM, "geometry_identity_sha256": geometry["identity_sha256"],
            "source_hydraulic_identity_sha256": forcing.source_identity_sha256,
            "config": asdict(config), "channel_config": asdict(channel_config),
            "sediment_config": asdict(sediment_config), "material": asdict(material),
            "intervals": [], "status": "complete", "failure_reason": None, "failure_phase": None,
            "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    _pack(arrays, meta, "geometry", geometry)
    times = [float(forcing.time_seconds[0])]
    for interval, (start, end) in enumerate(zip(forcing.time_seconds[:-1], forcing.time_seconds[1:])):
        wp = None
        sediment = None
        next_mesh = None
        try:
            gid = _geometry_id(geometry["identity_sha256"], mesh, interval)
            current = _network(network, node_bed, slope, gid)
            wf = ChannelForcing(np.array([start, end], np.float64),
                                forcing.local_q_m3_s[interval:interval + 1].copy(), forcing.source_identity_sha256)
            water = solve_channel(current, wf, water_volume, channel_config)
            if water["metadata"]["status"] != "complete":
                wp = make_channel_product(current, wf, water)
                raise ValueError("M3 water " + str(water["metadata"]["failure_reason"]))
            wp = make_channel_product(current, wf, water)
            wa = water["arrays"]
            sf = SedimentForcing(wa["time_seconds"].copy(), wa["volume_m3"][:-1].copy(),
                wa["depth_m"][:-1].copy(), wa["outflow_q_m3_s"].copy(),
                np.broadcast_to(slope, wa["outflow_q_m3_s"].shape).copy(),
                np.broadcast_to(external_solid_m3_s[interval], wa["outflow_q_m3_s"].shape).copy(),
                wp["identity_sha256"], gid,
                "exact newly solved M3 interval water replay")
            sd = SedimentDomain(network.receiver.copy(), areas.copy(), network.width_m.copy(),
                node_bed.copy(), rock_floor_m.copy(), (loose / (1. - material.porosity)).copy(),
                np.zeros(n, bool), network.terminal_kind == "open_outflow", gid,
                "exact PL basis material area and current bed state")
            sediment = solve_sediment(sd, sf, material, mobile, sediment_config)
            if sediment["metadata"]["status"] != "complete":
                raise ValueError("M6 sediment " + str(sediment["metadata"]["failure_reason"]))
            sa = sediment["arrays"]
            next_mobile = sa["trace_mobile_solid_m3"][-1]
            next_loose = sa["trace_bed_alluvium_solid_m3"][-1]
            rock_increment = sa["trace_rock_removed_m3"][-1]
            next_rock_removed = rock_removed + rock_increment
            delta = (next_loose - loose) / ((1. - material.porosity) * areas) - rock_increment / areas
            next_mesh = mesh + delta @ basis
            if np.max(np.abs(next_mesh - original_mesh)) > config.max_cumulative_bed_change_m + 1e-12:
                raise ValueError("maximum cumulative PL bed change exceeded")
            next_node, next_slope, next_ports = _sections(geometry, next_mesh, network, config)
            if not np.allclose(next_node, node_bed + delta, rtol=0., atol=1e-8):
                raise ValueError("node Exner and canonical mesh disagree")
            if np.any(next_node - (next_loose / (1. - material.porosity)) / areas < rock_floor_m - 1e-10):
                raise ValueError("updated mesh violates rock floor")
            mesh_change = np.sum(triangle_area * np.mean((next_mesh - mesh)[a["triangles"]], axis=1))
            material_change = np.sum((next_loose - loose) / (1. - material.porosity) - rock_increment)
            if not math.isclose(mesh_change, material_change, rel_tol=0., abs_tol=1e-8):
                raise ValueError("exact mesh volume and material ledger disagree")
            next_water = wa["volume_m3"][-1]
            if np.any(np.abs(next_node - node_bed) > config.max_depth_change_m + 1e-12):
                raise ValueError("fixed-water-volume stage shift exceeds morphology bound")
            if np.any(next_water > network.width_m * network.length_m * network.max_depth_m):
                raise ValueError("remapped water exceeds section capacity")
            _network(network, next_node, next_slope, _geometry_id(geometry["identity_sha256"], next_mesh, interval + 1))
        except ValueError as error:
            if next_mesh is not None and wp is not None and sediment is not None:
                meta["failure_phase"] = "candidate_geometry"
                arrays["rejected_mesh_bed_m"] = readonly(next_mesh)
                _pack(arrays, meta, "rejected_water", wp)
                _pack(arrays, meta, "rejected_sediment", sediment)
            elif sediment is not None and wp is not None:
                meta["failure_phase"] = "sediment"
                _pack(arrays, meta, "rejected_water", wp)
                _pack(arrays, meta, "rejected_sediment", sediment)
            elif wp is not None:
                meta["failure_phase"] = "water"
                _pack(arrays, meta, "rejected_water", wp)
            else:
                raise
            meta["status"] = "failed_prefix"; meta["failure_reason"] = str(error)
            break
        _pack(arrays, meta, "water_" + str(interval), wp)
        _pack(arrays, meta, "sediment_" + str(interval), sediment)
        arrays["port_" + str(interval)] = readonly(ports)
        arrays["port_" + str(interval + 1)] = readonly(next_ports)
        meta["intervals"].append({"start_seconds": float(start), "end_seconds": float(end),
            "geometry_identity_sha256": gid, "next_geometry_identity_sha256": _geometry_id(geometry["identity_sha256"], next_mesh, interval + 1),
            "water_identity_sha256": wp["identity_sha256"], "sediment_identity_sha256": sediment["identity_sha256"],
            "mesh_volume_delta_m3": float(mesh_change), "material_bulk_minus_rock_m3": float(material_change),
            "water_inventory_mapping": "fixed_volume_recompute_depth_and_stage"})
        mesh, node_bed, slope, ports = next_mesh, next_node, next_slope, next_ports
        water_volume, mobile, loose, rock_removed = next_water, next_mobile, next_loose, next_rock_removed
        times.append(float(end))
        for name, value in (("mesh_bed_m", mesh), ("node_bed_m", node_bed),
                            ("water_volume_m3", water_volume), ("mobile_solid_m3", mobile),
                            ("loose_solid_m3", loose), ("rock_removed_m3", rock_removed)):
            states[name].append(value.copy())
    arrays["time_seconds"] = readonly(np.array(times, np.float64))
    for name in STATE_KEYS:
        arrays[name] = readonly(np.array(states[name], np.float64))
    final_depth = water_volume / (network.width_m * network.length_m)
    final_q = np.zeros(n, np.float64)
    active = np.isin(network.terminal_kind, ("interior", "open_outflow"))
    wetted_area = network.width_m * final_depth
    radius = np.divide(wetted_area, network.width_m + 2. * final_depth,
                       out=np.zeros(n), where=final_depth > 0.)
    final_q[active] = (wetted_area[active] * radius[active] ** (2. / 3.) *
                       np.sqrt(slope[active]) / network.roughness[active])
    arrays["final_water_depth_m"] = readonly(final_depth)
    arrays["final_water_stage_m"] = readonly(node_bed + final_depth)
    arrays["final_manning_q_m3_s"] = readonly(final_q)
    arrays["final_bed_slope"] = readonly(slope)
    meta["requested_end_time_seconds"] = float(forcing.time_seconds[-1])
    meta["last_time_seconds"] = times[-1]
    meta["uncompleted_time_seconds"] = None if meta["status"] == "complete" else [times[-1], float(forcing.time_seconds[-1])]
    meta["needs_geometry_and_hydraulic_revalidation"] = False if meta["status"] == "complete" else True
    if sum(x.nbytes for x in arrays.values()) > MAX_BYTES:
        raise ValueError("morphology product exceeds 128MiB")
    result = {"arrays": arrays, "metadata": meta, "identity_sha256": identity(arrays, meta)}
    validate_morphology_coupling(result)
    return result


def validate_morphology_coupling(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid morphology bundle")
    a, m = bundle["arrays"], bundle["metadata"]
    if m.get("schema") != SCHEMA or m.get("algorithm") != ALGORITHM or identity(a, m) != bundle["identity_sha256"]:
        raise ValueError("morphology identity or schema mismatch")
    if sum(x.nbytes for x in a.values()) > MAX_BYTES:
        raise ValueError("morphology resource budget exceeded")
    expected = {"basis", "material_area_m2", "triangle_area_m2", "source_mesh_bed_m",
                "source_node_bed_m", "rock_floor_m", "forcing_time_seconds",
                "forcing_local_q_m3_s", "forcing_external_solid_m3_s", "time_seconds",
                "final_water_depth_m", "final_water_stage_m", "final_manning_q_m3_s", "final_bed_slope"}
    expected |= set(STATE_KEYS)
    expected.add("geometry__payload")
    for i in range(len(m["intervals"])):
        expected.add("water_" + str(i) + "__payload")
        expected.add("sediment_" + str(i) + "__payload")
        expected.add("port_" + str(i))
        expected.add("port_" + str(i + 1))
    if m["status"] == "failed_prefix":
        for role in ("rejected_water", "rejected_sediment"):
            if role in m:
                expected.add(role + "__payload")
        if m["failure_phase"] == "candidate_geometry":
            expected.add("rejected_mesh_bed_m")
    if set(a) != expected:
        raise ValueError("morphology array schema mismatch")
    if any(m.get(key) is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("morphology certification flags invalid")
    geometry = _unpack(a, m, "geometry")
    validate_channel_geometry(geometry)
    if geometry["identity_sha256"] != m["geometry_identity_sha256"]:
        raise ValueError("parent geometry identity mismatch")
    config = MorphologyConfig(**m["config"])
    ChannelConfig(**m["channel_config"])
    SedimentConfig(**m["sediment_config"])
    times = a["time_seconds"]
    k = len(times) - 1
    if times.dtype != np.float64 or not np.isfinite(times).all() or np.any(np.diff(times) <= 0.) or k != len(m["intervals"]):
        raise ValueError("invalid morphology committed times")
    for name in STATE_KEYS:
        state = a[name]
        if state.dtype != np.float64 or state.shape[0] != k + 1 or not np.isfinite(state).all():
            raise ValueError("invalid morphology state " + name)
    if m["last_time_seconds"] != times[-1] or m["requested_end_time_seconds"] < times[-1]:
        raise ValueError("morphology time metadata mismatch")
    if m["status"] == "complete":
        if m["failure_reason"] is not None or m["uncompleted_time_seconds"] is not None or times[-1] != m["requested_end_time_seconds"]:
            raise ValueError("invalid complete morphology result")
        if m["failure_phase"] is not None or m["needs_geometry_and_hydraulic_revalidation"] is not False:
            raise ValueError("complete recoupled morphology state flags mismatch")
    elif m["status"] == "failed_prefix":
        if not m["failure_reason"] or m["uncompleted_time_seconds"] != [times[-1], m["requested_end_time_seconds"]]:
            raise ValueError("invalid morphology failure prefix")
        if m["failure_phase"] not in ("water", "sediment", "candidate_geometry"):
            raise ValueError("missing morphology failure witness phase")
        if m["needs_geometry_and_hydraulic_revalidation"] is not True:
            raise ValueError("failed recoupling requires geometry and hydraulic review")
    else:
        raise ValueError("invalid morphology status")
    material = MaterialParameters(**m["material"])
    basis, area, tri_area = a["basis"], a["material_area_m2"], a["triangle_area_m2"]
    expected_basis, expected_area, expected_tri_area = _basis(geometry)
    if (not np.array_equal(basis, expected_basis) or not np.allclose(area, expected_area, rtol=0., atol=1e-10)
            or not np.allclose(tri_area, expected_tri_area, rtol=0., atol=1e-10)):
        raise ValueError("saved PL material basis or integral mismatch")
    if not np.array_equal(a["source_mesh_bed_m"], geometry["arrays"]["bed_elevation_m"]):
        raise ValueError("morphology parent bed mismatch")
    if not np.array_equal(a["mesh_bed_m"][0], a["source_mesh_bed_m"]):
        raise ValueError("morphology initial mesh mismatch")
    if not np.allclose(a["node_bed_m"][0], _sample_nodes(geometry, a["mesh_bed_m"][0]), rtol=0., atol=1e-9):
        raise ValueError("morphology initial node bed mismatch")
    n = len(geometry["arrays"]["receiver"])
    if a["forcing_time_seconds"].dtype != np.float64 or a["forcing_time_seconds"].ndim != 1 or len(a["forcing_time_seconds"]) - 1 < k:
        raise ValueError("invalid parent forcing times")
    if (a["forcing_local_q_m3_s"].shape != (len(a["forcing_time_seconds"]) - 1, n)
            or a["forcing_external_solid_m3_s"].shape != a["forcing_local_q_m3_s"].shape
            or np.any(a["forcing_local_q_m3_s"] < 0.) or np.any(a["forcing_external_solid_m3_s"] < 0.)
            or not np.isfinite(a["forcing_local_q_m3_s"]).all()
            or not np.isfinite(a["forcing_external_solid_m3_s"]).all()):
        raise ValueError("invalid parent forcing rates")
    if not np.array_equal(times, a["forcing_time_seconds"][:k + 1]):
        raise ValueError("committed times differ from parent forcing")
    if np.any(a["mobile_solid_m3"] < 0.) or np.any(a["loose_solid_m3"] < 0.) or np.any(a["rock_removed_m3"] < 0.) or np.any(a["water_volume_m3"] < 0.):
        raise ValueError("negative morphology inventory")
    if (a["basis"].shape != (n, a["mesh_bed_m"].shape[1]) or a["material_area_m2"].shape != (n,)
            or a["node_bed_m"].shape != (k + 1, n) or a["water_volume_m3"].shape != (k + 1, n)
            or a["mobile_solid_m3"].shape != (k + 1, n) or a["loose_solid_m3"].shape != (k + 1, n)
            or a["rock_removed_m3"].shape != (k + 1, n)):
        raise ValueError("morphology state shape mismatch")
    if np.any(np.abs(a["mesh_bed_m"] - a["source_mesh_bed_m"]) > config.max_cumulative_bed_change_m + 1e-12):
        raise ValueError("committed mesh exceeds deformation gate")
    for index in range(k + 1):
        if not np.allclose(_sample_nodes(geometry, a["mesh_bed_m"][index]), a["node_bed_m"][index], rtol=0., atol=1e-9):
            raise ValueError("node bed differs from canonical mesh")
        if np.any(a["node_bed_m"][index] - a["loose_solid_m3"][index] /
                  ((1. - material.porosity) * area) < a["rock_floor_m"] - 1e-10):
            raise ValueError("committed mesh geological floor violation")
    for i, record in enumerate(m["intervals"]):
        water = _unpack(a, m, "water_" + str(i)); sediment = _unpack(a, m, "sediment_" + str(i))
        _validate_water(geometry, water); validate_sediment(sediment)
        wa, sa = water["arrays"], sediment["arrays"]
        if (record["geometry_identity_sha256"] != _geometry_id(geometry["identity_sha256"], a["mesh_bed_m"][i], i)
                or record["next_geometry_identity_sha256"] != _geometry_id(geometry["identity_sha256"], a["mesh_bed_m"][i + 1], i + 1)
                or water["metadata"]["network_source_identity_sha256"] != record["geometry_identity_sha256"]
                or sediment["metadata"]["geometry_identity_sha256"] != record["geometry_identity_sha256"]
                or sediment["metadata"]["hydraulic_identity_sha256"] != water["identity_sha256"]):
            raise ValueError("geometry hydraulic material lineage mismatch")
        if not np.array_equal(wa["network_receiver"], geometry["arrays"]["receiver"]) or not np.array_equal(wa["network_width_m"], geometry["arrays"]["width_m"]):
            raise ValueError("recoupled topology or width mismatch")
        if not np.array_equal(wa["network_bed_elevation_m"], a["node_bed_m"][i]):
            raise ValueError("recoupled M3 bed mismatch")
        expected_lengths = np.zeros(n, np.float64)
        nodes = geometry["arrays"]["node_xz_m"]
        for donor, target in enumerate(wa["network_receiver"]):
            if target >= 0:
                half = np.linalg.norm(nodes[donor] - nodes[target]) / 2.
                expected_lengths[donor] += half
                expected_lengths[target] += half
        if not np.allclose(wa["network_length_m"], expected_lengths, rtol=0., atol=1e-8):
            raise ValueError("hydraulic control lengths do not partition centerline")
        base = ChannelNetwork(wa["network_receiver"], wa["network_length_m"], wa["network_width_m"],
            wa["network_bed_elevation_m"], wa["network_bed_slope"], wa["network_roughness"],
            wa["network_max_depth_m"], wa["network_terminal_kind"], record["geometry_identity_sha256"],
            "cold reconstructed section", "cold reconstructed roughness",
            receiver_distance_m=_water_distance(geometry, wa))
        expected_node, expected_slope, expected_port = _sections(geometry, a["mesh_bed_m"][i], base, config)
        if not np.allclose(expected_node, a["node_bed_m"][i], rtol=0., atol=1e-9) or not np.allclose(expected_slope, wa["network_bed_slope"], rtol=0., atol=1e-10):
            raise ValueError("updated PL section or slope mismatch")
        if not np.allclose(expected_port, a["port_" + str(i)], rtol=0., atol=1e-9):
            raise ValueError("shared port re-sampling mismatch")
        if not np.array_equal(wa["forcing_local_q_m3_s"][0], a["forcing_local_q_m3_s"][i]):
            raise ValueError("local water source counted incorrectly")
        if wa["forcing_time_seconds"].tolist() != [float(a["forcing_time_seconds"][i]), float(a["forcing_time_seconds"][i + 1])]:
            raise ValueError("water interval forcing time mismatch")
        if not np.array_equal(sa["forcing_external_solid_m3_s"], np.broadcast_to(a["forcing_external_solid_m3_s"][i], sa["forcing_external_solid_m3_s"].shape)):
            raise ValueError("external solid source counted incorrectly")
        if water["identity_sha256"] != record["water_identity_sha256"] or sediment["identity_sha256"] != record["sediment_identity_sha256"]:
            raise ValueError("recoupling interval lineage mismatch")
        if water["metadata"]["forcing_source_identity_sha256"] != m["source_hydraulic_identity_sha256"]:
            raise ValueError("parent hydraulic forcing lineage mismatch")
        if not np.array_equal(wa["trace_volume_m3"][0], a["water_volume_m3"][i]) or not np.array_equal(wa["trace_volume_m3"][-1], a["water_volume_m3"][i + 1]):
            raise ValueError("water inventory mapping mismatch")
        if not np.array_equal(sa["trace_mobile_solid_m3"][0], a["mobile_solid_m3"][i]) or not np.array_equal(sa["trace_mobile_solid_m3"][-1], a["mobile_solid_m3"][i + 1]):
            raise ValueError("mobile material mapping mismatch")
        if not np.allclose(sa["trace_bed_alluvium_solid_m3"][0], a["loose_solid_m3"][i], rtol=0., atol=1e-10) or not np.allclose(sa["trace_bed_alluvium_solid_m3"][-1], a["loose_solid_m3"][i + 1], rtol=0., atol=1e-10):
            raise ValueError("bed solid inventory mismatch")
        rock_delta = sa["trace_rock_removed_m3"][-1]
        delta = ((a["loose_solid_m3"][i + 1] - a["loose_solid_m3"][i]) / ((1. - material.porosity) * area)
                 - rock_delta / area)
        expected_mesh = a["mesh_bed_m"][i] + delta @ basis
        if not np.allclose(expected_mesh, a["mesh_bed_m"][i + 1], rtol=0., atol=1e-9):
            raise ValueError("canonical mesh Exner update mismatch")
        if np.any(np.abs(a["node_bed_m"][i + 1] - a["node_bed_m"][i]) > config.max_depth_change_m + 1e-12):
            raise ValueError("fixed-volume stage shift exceeds bound")
        next_node, _, next_port = _sections(geometry, expected_mesh, base, config)
        if not np.allclose(next_node, a["node_bed_m"][i + 1], rtol=0., atol=1e-9) or not np.allclose(next_port, a["port_" + str(i + 1)], rtol=0., atol=1e-9):
            raise ValueError("post-Exner node or port mismatch")
        if not np.array_equal(sa["domain_bed_area_m2"], area) or not np.array_equal(sa["domain_bed_elevation_m"], a["node_bed_m"][i]):
            raise ValueError("sediment material area or bed mismatch")
        if not np.array_equal(sa["domain_rock_floor_m"], a["rock_floor_m"]):
            raise ValueError("geological floor changed across versions")
        if not np.allclose(sa["domain_initial_alluvium_bulk_m3"] * (1. - material.porosity), a["loose_solid_m3"][i], rtol=0., atol=1e-10):
            raise ValueError("loose solid mapped incorrectly")
        for target, parent in (("forcing_time_seconds", "trace_time_seconds"),
                               ("forcing_water_volume_m3", "trace_volume_m3"),
                               ("forcing_water_depth_m", "trace_depth_m"),
                               ("forcing_water_outflow_m3_s", "trace_outflow_q_m3_s")):
            expected = wa[parent][:-1] if parent in ("trace_volume_m3", "trace_depth_m") else wa[parent]
            if not np.array_equal(sa[target], expected):
                raise ValueError("sediment replay differs from newly solved water: " + target)
        if not np.allclose(a["rock_removed_m3"][i] + rock_delta, a["rock_removed_m3"][i + 1], rtol=0., atol=1e-10):
            raise ValueError("cumulative rock depletion mismatch")
        mesh_delta = np.sum(tri_area * np.mean((expected_mesh - a["mesh_bed_m"][i])[geometry["arrays"]["triangles"]], axis=1))
        material_delta = np.sum((a["loose_solid_m3"][i + 1] - a["loose_solid_m3"][i]) / (1. - material.porosity) - rock_delta)
        if not math.isclose(record["material_bulk_minus_rock_m3"], material_delta, rel_tol=0., abs_tol=1e-8) or not math.isclose(mesh_delta, material_delta, rel_tol=0., abs_tol=1e-8):
            raise ValueError("material and mesh volume ledger mismatch")
    if m["status"] == "failed_prefix":
        rejected_water = _unpack(a, m, "rejected_water")
        _validate_water(geometry, rejected_water)
        wa = rejected_water["arrays"]
        gid = _geometry_id(geometry["identity_sha256"], a["mesh_bed_m"][-1], k)
        if (rejected_water["metadata"]["network_source_identity_sha256"] != gid
                or rejected_water["metadata"]["forcing_source_identity_sha256"] != m["source_hydraulic_identity_sha256"]
                or not np.array_equal(wa["forcing_time_seconds"], a["forcing_time_seconds"][k:k + 2])
                or not np.array_equal(wa["forcing_local_q_m3_s"], a["forcing_local_q_m3_s"][k:k + 1])
                or not np.array_equal(wa["trace_volume_m3"][0], a["water_volume_m3"][-1])
                or not np.array_equal(wa["network_receiver"], geometry["arrays"]["receiver"])
                or not np.array_equal(wa["network_width_m"], geometry["arrays"]["width_m"])
                or not np.array_equal(wa["network_bed_elevation_m"], a["node_bed_m"][-1])):
            raise ValueError("rejected water candidate is detached from parent state or forcing")
        base = ChannelNetwork(wa["network_receiver"], wa["network_length_m"], wa["network_width_m"],
            wa["network_bed_elevation_m"], wa["network_bed_slope"], wa["network_roughness"],
            wa["network_max_depth_m"], wa["network_terminal_kind"], gid, "rejected section", "rejected roughness",
            receiver_distance_m=_water_distance(geometry, wa))
        expected_node, expected_slope, _ = _sections(geometry, a["mesh_bed_m"][-1], base, config)
        if (not np.allclose(expected_node, wa["network_bed_elevation_m"], rtol=0., atol=1e-9)
                or not np.allclose(expected_slope, wa["network_bed_slope"], rtol=0., atol=1e-10)):
            raise ValueError("rejected water section differs from current canonical mesh")
        if m["failure_phase"] == "water":
            if rejected_water["metadata"]["status"] != "failed_prefix" or m["failure_reason"] != "M3 water " + str(rejected_water["metadata"]["failure_reason"]):
                raise ValueError("unverified water failure witness")
        else:
            if rejected_water["metadata"]["status"] != "complete":
                raise ValueError("invalid rejected candidate water")
            rejected_sediment = _unpack(a, m, "rejected_sediment")
            validate_sediment(rejected_sediment)
            sa = rejected_sediment["arrays"]
            if (rejected_sediment["metadata"]["geometry_identity_sha256"] != gid
                    or rejected_sediment["metadata"]["hydraulic_identity_sha256"] != rejected_water["identity_sha256"]
                    or rejected_sediment["metadata"]["material"] != m["material"]
                    or not np.array_equal(sa["domain_receiver"], geometry["arrays"]["receiver"])
                    or not np.array_equal(sa["domain_bed_area_m2"], area)
                    or not np.array_equal(sa["domain_width_m"], geometry["arrays"]["width_m"])
                    or not np.array_equal(sa["domain_bed_elevation_m"], a["node_bed_m"][-1])
                    or not np.array_equal(sa["domain_rock_floor_m"], a["rock_floor_m"])
                    or not np.allclose(sa["domain_initial_alluvium_bulk_m3"] * (1. - material.porosity), a["loose_solid_m3"][-1], rtol=0., atol=1e-10)
                    or not np.array_equal(sa["initial_mobile_solid_m3"], a["mobile_solid_m3"][-1])
                    or not np.array_equal(sa["forcing_external_solid_m3_s"], np.broadcast_to(a["forcing_external_solid_m3_s"][k], sa["forcing_external_solid_m3_s"].shape))):
                raise ValueError("rejected sediment candidate is detached from parent state or material")
            for target, parent in (("forcing_time_seconds", "trace_time_seconds"),
                                   ("forcing_water_volume_m3", "trace_volume_m3"),
                                   ("forcing_water_depth_m", "trace_depth_m"),
                                   ("forcing_water_outflow_m3_s", "trace_outflow_q_m3_s")):
                expected_water = wa[parent][:-1] if parent in ("trace_volume_m3", "trace_depth_m") else wa[parent]
                if not np.array_equal(sa[target], expected_water):
                    raise ValueError("rejected sediment replay differs from candidate water")
            if m["failure_phase"] == "sediment":
                if rejected_sediment["metadata"]["status"] != "failed_prefix" or m["failure_reason"] != "M6 sediment " + str(rejected_sediment["metadata"]["failure_reason"]):
                    raise ValueError("unverified sediment failure witness")
            else:
                if rejected_sediment["metadata"]["status"] != "complete":
                    raise ValueError("candidate geometry has incomplete sediment")
                delta = ((rejected_sediment["arrays"]["trace_bed_alluvium_solid_m3"][-1] - a["loose_solid_m3"][-1]) /
                         ((1. - material.porosity) * area) - rejected_sediment["arrays"]["trace_rock_removed_m3"][-1] / area)
                trial_mesh = a["mesh_bed_m"][-1] + delta @ basis
                if not np.allclose(trial_mesh, a["rejected_mesh_bed_m"], rtol=0., atol=1e-9):
                    raise ValueError("failed geometry candidate mesh mismatch")
                if m["failure_reason"] == "maximum cumulative PL bed change exceeded":
                    if np.max(np.abs(trial_mesh - a["source_mesh_bed_m"])) <= config.max_cumulative_bed_change_m:
                        raise ValueError("unverified deformation failure")
                elif m["failure_reason"] in ("canonical cut bed is flat or uphill",
                                            "updated PL bed slope below declared minimum"):
                    last_water = rejected_water["arrays"]
                    witness_network = ChannelNetwork(last_water["network_receiver"], last_water["network_length_m"],
                        last_water["network_width_m"], last_water["network_bed_elevation_m"],
                        last_water["network_bed_slope"], last_water["network_roughness"],
                        last_water["network_max_depth_m"], last_water["network_terminal_kind"],
                        rejected_water["metadata"]["network_source_identity_sha256"], "witness", "witness",
                        receiver_distance_m=_water_distance(geometry, last_water))
                    try:
                        _sections(geometry, trial_mesh, witness_network, config)
                    except ValueError as error:
                        if str(error) != m["failure_reason"]:
                            raise ValueError("geometry failure witness reason mismatch") from error
                    else:
                        raise ValueError("missing continuous PL slope failure witness")
                elif m["failure_reason"] == "updated mesh violates rock floor":
                    next_node = _sample_nodes(geometry, trial_mesh)
                    next_loose = rejected_sediment["arrays"]["trace_bed_alluvium_solid_m3"][-1]
                    if not np.any(next_node - next_loose / ((1. - material.porosity) * area) < a["rock_floor_m"] - 1e-10):
                        raise ValueError("missing rock floor failure witness")
                elif m["failure_reason"] == "fixed-water-volume stage shift exceeds morphology bound":
                    next_node = _sample_nodes(geometry, trial_mesh)
                    if not np.any(np.abs(next_node - a["node_bed_m"][-1]) > config.max_depth_change_m + 1e-12):
                        raise ValueError("missing stage shift failure witness")
                else:
                    raise ValueError("unverified candidate geometry failure reason")
    if k:
        final_water = _unpack(a, m, "water_" + str(k - 1))["arrays"]
        final_network = ChannelNetwork(final_water["network_receiver"], final_water["network_length_m"],
            final_water["network_width_m"], a["node_bed_m"][-1], a["final_bed_slope"],
            final_water["network_roughness"], final_water["network_max_depth_m"],
            final_water["network_terminal_kind"], _geometry_id(geometry["identity_sha256"], a["mesh_bed_m"][-1], k),
            "cold final section", "cold roughness",
            receiver_distance_m=_water_distance(geometry, final_water))
        _, slope, port = _sections(geometry, a["mesh_bed_m"][-1], final_network, config)
        depth = a["water_volume_m3"][-1] / (final_network.width_m * final_network.length_m)
        area_water = final_network.width_m * depth
        radius = np.divide(area_water, final_network.width_m + 2. * depth, out=np.zeros(n), where=depth > 0.)
        active = np.isin(final_network.terminal_kind, ("interior", "open_outflow"))
        q = np.where(active, area_water * radius ** (2. / 3.) * np.sqrt(slope) / final_network.roughness, 0.)
        for key, expected in (("final_bed_slope", slope), ("final_water_depth_m", depth),
                              ("final_water_stage_m", a["node_bed_m"][-1] + depth),
                              ("final_manning_q_m3_s", q)):
            if not np.allclose(a[key], expected, rtol=0., atol=1e-9):
                raise ValueError("final post-bed hydraulic state mismatch: " + key)
        if not np.allclose(port, a["port_" + str(k)], rtol=0., atol=1e-9):
            raise ValueError("final shared port mismatch")


def save_morphology_coupling(path, bundle):
    save_bundle(path, bundle, validator=validate_morphology_coupling)


def load_morphology_coupling(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_morphology_coupling, max_bytes=MAX_BYTES)
