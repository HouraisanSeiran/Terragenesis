"""Finite raw-conditioning-bed kinematic-wave candidate, not R7 certification."""
from __future__ import annotations

from copy import deepcopy
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.drainage import diagnostic_mesh as diagnostic_mesh
from .metric_channel_state import (
    ChannelConfig, ChannelForcing, ChannelNetwork, MAX_CHANNEL_NODES,
    validate_receiver_acyclic,
)
from .metric_channel_solver import solve_channel
from .metric_channel_product import make_channel_product, validate_channel_product

SCHEMA = "river-domain-channel-hydraulics-candidate-v1"
ALGORITHM = "raw-domain-local-release-kinematic-bridge-v3-irregular-metric"
MAX_BYTES = 256 * 1024 * 1024
LIMITATIONS = (
    "raw_conditioning face only; R6 carved channel geometry is not consumed",
    "kinematic-wave candidate only; no dynamic backwater",
    "no conservative floodplain inundation or lake evolution",
    "no cross-tile accumulated upstream inflow certification",
    "outside-core cells have no local production in this source; not a complete natural catchment",
    "explicit engineering parameters are not calibrated hydraulic parameters",
    "not complete R7 certification and not stage-one certification",
)
TOPOLOGY_FIELDS = ("receiver", "terminal", "height_m", "ocean", "ocean_terminal",
                   "accepted", "unresolved", "in_core")
PARAMETER_SOURCES = ("width_m", "control_length_m", "max_depth_m", "roughness")


def _volume_sum(volume):
    """Canonical interval-major/node-major binary64 sum, independent of NumPy reductions."""
    return math.fsum(float(value) for value in volume.ravel(order="C"))


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " requires explicit provenance text")
    return value


def _array(value, dtype, shape, name):
    value = np.asarray(value)
    if value.dtype != np.dtype(dtype) or value.shape != shape:
        raise ValueError(name + " has invalid dtype/shape")
    if value.dtype.kind == "f" and not np.isfinite(value).all():
        raise ValueError(name + " must be finite")
    return value


def _source(arrays, metadata):
    """Reconstruct terrain and audit the persisted production/topology relationship."""
    terrain = TerrainGrid(arrays["source_height_m"], arrays["source_valid_mask"],
                          **metadata["terrain_metadata"])
    if terrain.identity_sha256 != metadata["terrain_identity_sha256"]:
        raise ValueError("terrain identity mismatch")
    shape = terrain.elevation_m.shape
    size = terrain.elevation_m.size
    frame = metadata["topology_frame"]
    if (frame["shape"] != list(shape) or frame["spacing_m"] != terrain.dx_m
            or frame["spacing_m"] != terrain.dz_m
            or frame["origin_x_m"] != terrain.x0_m or frame["origin_z_m"] != terrain.z0_m):
        raise ValueError("topology and terrain metric frame differ")
    for key in TOPOLOGY_FIELDS:
        dtype = np.float64 if key == "height_m" else np.int64 if key in ("receiver", "terminal") else bool
        _array(arrays["topology_" + key], dtype, shape, key)
    if not np.array_equal(arrays["topology_height_m"], terrain.elevation_m):
        raise ValueError("topology and terrain height differ")
    receiver = arrays["topology_receiver"].ravel()
    terminal = arrays["topology_terminal"].ravel()
    if np.any((receiver < -1) | (receiver >= size)) or np.any((terminal < 0) | (terminal >= size)):
        raise ValueError("invalid original receiver/terminal")
    validate_receiver_acyclic(receiver)
    interior = receiver >= 0
    if (not np.array_equal(terminal[interior], terminal[receiver[interior]])
            or not np.array_equal(terminal[~interior], np.flatnonzero(~interior))):
        raise ValueError("original terminal does not match receiver closure")
    ocean = arrays["topology_ocean"].ravel()
    if not np.array_equal(arrays["topology_ocean_terminal"].ravel(), ocean[terminal]):
        raise ValueError("original ocean terminal classification mismatch")
    accepted = arrays["topology_accepted"].ravel()
    unresolved = arrays["topology_unresolved"].ravel()
    if np.any(accepted & (unresolved | ocean)):
        raise ValueError("accepted production cannot be ocean or unresolved")
    producing = arrays["producing_cell_ids"]
    expected = np.flatnonzero(accepted & arrays["topology_in_core"].ravel())
    _array(producing, np.int64, expected.shape, "producing_cell_ids")
    if not np.array_equal(producing, expected):
        raise ValueError("producing cells must equal accepted core production")
    count, dt = metadata["interval_count"], metadata["dt_s"]
    if (type(count) is not int or not 1 <= count <= 60 or type(dt) not in (int, float)
            or not np.isfinite(dt) or dt <= 0.):
        raise ValueError("invalid source physical interval count/dt_s")
    release = _array(arrays["released_per_interval_grid_m3"], np.float64,
                     (count,) + shape, "released_per_interval_grid_m3")
    total = _array(arrays["released_grid_m3"], np.float64, shape, "released_grid_m3")
    if (np.any(release < 0.) or np.any(release.reshape(count, -1)[:, ~np.isin(np.arange(size), producing)] != 0.)
            or not np.allclose(release.sum(axis=0), total, rtol=1e-12, atol=1e-10)):
        raise ValueError("interval production must match totals and producing support")
    return terrain


def _selection(arrays, metadata, terrain):
    ids = arrays["node_cell_ids"]
    if ids.dtype != np.int64 or ids.ndim != 1 or not 1 <= ids.size <= MAX_CHANNEL_NODES:
        raise ValueError("bounded int64 selected ids required")
    n = ids.size
    if np.unique(ids).size != n or np.any((ids < 0) | (ids >= terrain.elevation_m.size)):
        raise ValueError("invalid selected ids")
    if not terrain.valid_mask.ravel()[ids].all() or arrays["topology_unresolved"].ravel()[ids].any():
        raise ValueError("unknown selected terrain/topology")
    receiver = _array(arrays["selected_receiver"], np.int64, (n,), "selected_receiver")
    if np.any((receiver < -1) | (receiver >= n)):
        raise ValueError("receiver outside selected graph: rejected unresolved_border")
    original = _array(arrays["original_receiver_cell_ids"], np.int64, (n,), "original_receiver_cell_ids")
    if not np.array_equal(original, arrays["topology_receiver"].ravel()[ids]):
        raise ValueError("original receiver snapshot mismatch")
    links = receiver >= 0
    if (np.any((original >= 0) != links)
            or not np.array_equal(original[links], ids[receiver[links]])):
        raise ValueError("omitted or changed receiver: rejected unresolved_border")
    validate_receiver_acyclic(receiver)
    missing = np.setdiff1d(arrays["producing_cell_ids"], ids)
    if missing.size:
        _text(metadata["coverage_note"], "missing upstream contributions coverage_note")
    elif metadata["coverage_note"] is not None:
        _text(metadata["coverage_note"], "coverage_note")
    policies = metadata["terminal_policy"]
    expected_keys = {str(int(cell)) for cell in ids[~links]}
    if not isinstance(policies, dict) or set(policies) != expected_keys:
        raise ValueError("explicit policy required for every original terminal only")
    kind = np.full(n, "interior", dtype="U24")
    slope = np.zeros(n, np.float64)
    for node in np.flatnonzero(~links):
        policy = policies[str(int(ids[node]))]
        if not isinstance(policy, dict) or set(policy) != {"classification", "kind", "slope", "source"}:
            raise ValueError("terminal policy requires classification/kind/slope/source")
        _text(policy["source"], "terminal policy source")
        ocean = bool(arrays["topology_ocean"].ravel()[ids[node]])
        if arrays["topology_terminal"].ravel()[ids[node]] != ids[node]:
            raise ValueError("negative local receiver is not an original terminal")
        if (policy["classification"], policy["kind"]) != (("ocean", "open_outflow") if ocean
                                                                        else ("closed_basin", "closed_wall")):
            raise ValueError("terminal policy disagrees with known ocean/closed basin")
        value = policy["slope"]
        if (type(value) not in (int, float) or not np.isfinite(value)
                or (value <= 0. if ocean else value != 0.)):
            raise ValueError("explicit positive ocean slope or zero closed-wall slope required")
        kind[node] = policy["kind"]
        slope[node] = value
    mesh = diagnostic_mesh(terrain, unmasked=True)
    points = np.column_stack((mesh.node_x_m[ids], mesh.node_z_m[ids]))
    bed = terrain.elevation_m.ravel()[ids]
    distance = np.zeros(n, np.float64)
    distance[links] = np.linalg.norm(points[links] - points[receiver[links]], axis=1)
    slope[links] = (bed[links] - bed[receiver[links]]) / distance[links]
    sources = metadata["parameter_sources"]
    if not isinstance(sources, dict) or set(sources) != set(PARAMETER_SOURCES):
        raise ValueError("explicit parameter_sources required")
    for name in PARAMETER_SOURCES:
        _text(sources[name], name)
    _text(metadata["geometry_source"], "geometry_source")
    network_identity = identity({key: arrays[key] for key in
                                ("node_cell_ids", "selected_receiver", "original_receiver_cell_ids",
                                 "width_m", "control_length_m", "max_depth_m", "roughness")},
                               {"terrain_identity_sha256": terrain.identity_sha256,
                                "terminal_policy": policies, "parameter_sources": sources,
                                "geometry_source": metadata["geometry_source"],
                                "source_face": "raw_conditioning"})
    network = ChannelNetwork(receiver, arrays["control_length_m"], arrays["width_m"], bed,
                             slope, arrays["roughness"], arrays["max_depth_m"], kind,
                             network_identity, metadata["geometry_source"], sources["roughness"], distance)
    time = np.arange(metadata["interval_count"] + 1, dtype=np.float64) * metadata["dt_s"]
    volume = arrays["released_per_interval_grid_m3"].reshape(metadata["interval_count"], -1)[:, ids]
    source_identity = identity({"time_seconds": time, "selected_local_volume_m3": volume,
                                "producing_cell_ids": arrays["producing_cell_ids"],
                                "node_cell_ids": ids},
                               {"source_flow_identity_sha256": metadata["source_flow_identity_sha256"]})
    forcing = ChannelForcing(time, np.asarray(volume / metadata["dt_s"], np.float64), source_identity)
    missing_upstream = missing[np.isin(arrays["topology_terminal"].ravel()[missing], ids[~links])]
    coverage = {"missing_producing_cell_count": int(missing.size),
                "missing_upstream_contributing_cell_count": int(missing_upstream.size),
                "missing_upstream_contributing_release_m3": _volume_sum(
                    arrays["released_per_interval_grid_m3"].reshape(metadata["interval_count"], -1)[:, missing_upstream]),
                "missing_producing_release_m3": _volume_sum(arrays["released_per_interval_grid_m3"].reshape(
                    metadata["interval_count"], -1)[:, missing]),
                "selected_input_volume_m3": _volume_sum(volume),
                "current_production_downstream_closure_complete": missing.size == 0,
                "upstream_contributions_status": "not_certified",
                "cross_tile_inflow_status": "not_certified"}
    return network, forcing, coverage


def _flow_identity(arrays, metadata):
    names = {"topology_" + key for key in TOPOLOGY_FIELDS} | {
        "producing_cell_ids", "released_per_interval_grid_m3", "released_grid_m3"}
    return identity({key: arrays[key] for key in names},
                    {key: metadata[key] for key in ("topology_frame", "dt_s", "interval_count")})


def build_domain_channel_hydraulics(terrain, flow_topology, *, node_cell_ids, receiver,
                                    width_m, control_length_m, max_depth_m, roughness,
                                    parameter_sources, terminal_policy, geometry_source,
                                    coverage_note, config, initial_volume_m3=None):
    """Route actual interval local releases once on an explicit original-bed graph.

    Policies are keyed by original flat terminal id (string), each containing
    classification, kind, slope, source. Only ocean/open_outflow with an explicit
    positive engineering slope and closed_basin/closed_wall with zero slope are
    supported. Omitted producing cells require coverage_note; missing receivers
    are always rejected. Even full current production closure is not a certified
    natural catchment. Width/control length/depth/roughness arrays are float64.
    """
    if not isinstance(terrain, TerrainGrid) or not isinstance(flow_topology, dict):
        raise ValueError("TerrainGrid and explicit domain_flow_topology result required")
    if not isinstance(config, ChannelConfig):
        raise ValueError("explicit ChannelConfig required")
    source_keys = {"topology", "producing_flat", "released_per_interval_grid_m3", "released_grid_m3",
                   "dt_s", "interval_count"}
    if not source_keys.issubset(flow_topology):
        raise ValueError("incomplete domain_flow_topology result")
    topology = flow_topology["topology"]
    if not isinstance(topology, dict) or not (set(TOPOLOGY_FIELDS) | {
            "shape", "spacing_m", "origin_x_m", "origin_z_m"}).issubset(topology):
        raise ValueError("incomplete original domain topology")
    arrays = {"topology_" + key: np.asarray(topology[key]).copy() for key in TOPOLOGY_FIELDS}
    arrays.update(source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(),
                  producing_cell_ids=np.asarray(flow_topology["producing_flat"]).copy(),
                  released_per_interval_grid_m3=np.asarray(flow_topology["released_per_interval_grid_m3"]).copy(),
                  released_grid_m3=np.asarray(flow_topology["released_grid_m3"]).copy())
    for key, value in (("node_cell_ids", node_cell_ids), ("selected_receiver", receiver),
                       ("width_m", width_m), ("control_length_m", control_length_m),
                       ("max_depth_m", max_depth_m), ("roughness", roughness)):
        arrays[key] = np.asarray(value).copy()
    ids = arrays["node_cell_ids"]
    if ids.dtype != np.int64 or ids.ndim != 1 or np.any((ids < 0) | (ids >= terrain.elevation_m.size)):
        raise ValueError("valid int64 node_cell_ids required")
    arrays["original_receiver_cell_ids"] = arrays["topology_receiver"].ravel()[ids].copy()
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM,
                "terrain_metadata": {key: getattr(terrain, key) for key in terrain.__dataclass_fields__
                                     if key not in ("elevation_m", "valid_mask")},
                "terrain_identity_sha256": terrain.identity_sha256,
                "topology_frame": {"shape": list(topology["shape"]), "spacing_m": topology["spacing_m"],
                                   "origin_x_m": topology["origin_x_m"], "origin_z_m": topology["origin_z_m"]},
                "dt_s": flow_topology["dt_s"], "interval_count": flow_topology["interval_count"],
                "parameter_sources": dict(parameter_sources), "terminal_policy": deepcopy(terminal_policy),
                "geometry_source": geometry_source, "coverage_note": coverage_note,
                "source_face": "raw_conditioning", "r6_carving_consumed": False,
                "limitations": list(LIMITATIONS), "hydraulic_ready": False,
                "natural_outlet_verified": False, "publishable": False}
    _source(arrays, metadata)
    metadata["source_flow_identity_sha256"] = _flow_identity(arrays, metadata)
    network, forcing, coverage = _selection(arrays, metadata, terrain)
    child = make_channel_product(network, forcing, solve_channel(network, forcing, initial_volume_m3, config))
    metadata.update(coverage=coverage, geometry_identity_sha256=network.source_identity_sha256,
                    channel_identity_sha256=child["identity_sha256"], channel_metadata=child["metadata"])
    arrays.update({"channel_" + key: value for key, value in child["arrays"].items()})
    arrays = {key: readonly(value.copy()) for key, value in arrays.items()}
    record = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_domain_channel_hydraulics(record)
    return record


def validate_domain_channel_hydraulics(record):
    """Cold-check parent/child topology, local forcing and summaries, not only hashes."""
    if not isinstance(record, dict) or set(record) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid domain hydraulic bundle")
    arrays, meta = record["arrays"], record["metadata"]
    if (meta.get("schema") != SCHEMA or meta.get("algorithm") != ALGORITHM
            or meta.get("source_face") != "raw_conditioning" or meta.get("r6_carving_consumed") is not False
            or meta.get("limitations") != list(LIMITATIONS)
            or any(meta.get(key) is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or sum(value.nbytes for value in arrays.values()) > MAX_BYTES
            or record["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("domain hydraulic identity/schema/scope mismatch")
    terrain = _source(arrays, meta)
    if meta["source_flow_identity_sha256"] != _flow_identity(arrays, meta):
        raise ValueError("source flow identity mismatch")
    network, forcing, coverage = _selection(arrays, meta, terrain)
    if meta["coverage"] != coverage or meta["geometry_identity_sha256"] != network.source_identity_sha256:
        raise ValueError("coverage or geometry summary mismatch")
    child = {"arrays": {key[len("channel_"):]: value for key, value in arrays.items() if key.startswith("channel_")},
             "metadata": meta["channel_metadata"], "identity_sha256": meta["channel_identity_sha256"]}
    validate_channel_product(child)
    ca, cm = child["arrays"], child["metadata"]
    for name in ("receiver", "length_m", "width_m", "bed_elevation_m", "bed_slope", "roughness",
                 "max_depth_m", "terminal_kind", "receiver_distance_m"):
        if not np.array_equal(ca["network_" + name], getattr(network, name)):
            raise ValueError("nested channel geometry disagrees with original selected graph: " + name)
    if (not np.array_equal(ca["forcing_time_seconds"], forcing.time_seconds)
            or not np.array_equal(ca["forcing_local_q_m3_s"], forcing.local_q_m3_s)
            or cm["network_source_identity_sha256"] != network.source_identity_sha256
            or cm["forcing_source_identity_sha256"] != forcing.source_identity_sha256
            or cm["section_source"] != network.section_source or cm["roughness_source"] != network.roughness_source):
        raise ValueError("nested channel source/local forcing relationship mismatch")
    expected = {"topology_" + key for key in TOPOLOGY_FIELDS} | {
        "source_height_m", "source_valid_mask", "producing_cell_ids", "released_per_interval_grid_m3",
        "released_grid_m3", "node_cell_ids", "selected_receiver", "original_receiver_cell_ids",
        "width_m", "control_length_m", "max_depth_m", "roughness"}
    if set(arrays) != expected | {"channel_" + key for key in ca}:
        raise ValueError("unexpected domain hydraulic arrays")
    return True


def save_domain_channel_hydraulics(path, record):
    save_bundle(path, record, validator=validate_domain_channel_hydraulics)


def load_domain_channel_hydraulics(path, *, expected_sha256, expected_identity):
    record = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_domain_channel_hydraulics, max_bytes=MAX_BYTES)
    if record["identity_sha256"] != expected_identity:
        raise ValueError("external domain hydraulic identity mismatch")
    return record
