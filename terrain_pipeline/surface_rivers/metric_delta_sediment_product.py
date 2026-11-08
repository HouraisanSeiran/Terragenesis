"""Saved delta candidates driven by a witnessed upstream water/sediment export."""

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, save_bundle
from terrain_pipeline.channel_geometry import validate_channel_geometry
from terrain_pipeline.common_infra import TerrainGrid
from .metric_delta import DeltaConfig, geometry_graph_identity
from .metric_delta_product import build_delta_candidate_product, validate_delta_candidate_product
from .metric_morphology_coupling import MAX_BYTES, _pack, _sample_nodes, _unpack, _validate_water
from .metric_sediment import validate_sediment

SCHEMA = "terragenesis-delta-sediment-candidate-v1"


def _graph_identity(geometry):
    return geometry_graph_identity(geometry)


def _terminal_geometry(geometry, water, terminal, mouth, terrain):
    a, wa = geometry["arrays"], water["arrays"]
    if (not np.array_equal(a["receiver"], wa["network_receiver"])
            or not np.array_equal(a["width_m"], wa["network_width_m"])):
        raise ValueError("delta upstream geometry graph or width mismatch")
    if not np.allclose(_sample_nodes(geometry, a["bed_elevation_m"]), wa["network_bed_elevation_m"], rtol=0., atol=1e-8):
        raise ValueError("delta upstream water bed differs from canonical geometry")
    expected = divmod(int(a["source_node_cell_ids"][terminal]), terrain.elevation_m.shape[1])
    if tuple(mouth) != expected:
        raise ValueError("delta mouth is detached from upstream export terminal")


def _export(geometry, water, sediment, terminal_node):
    _validate_water(geometry, water)
    validate_sediment(sediment)
    wa, sa = water["arrays"], sediment["arrays"]
    wm, sm = water["metadata"], sediment["metadata"]
    if wm["status"] != "complete" or sm["status"] != "complete":
        raise ValueError("complete upstream water and sediment required")
    if (sm["hydraulic_identity_sha256"] != water["identity_sha256"]
            or sm["geometry_identity_sha256"] != wm["network_source_identity_sha256"]):
        raise ValueError("delta upstream water/sediment parent identity mismatch")
    if type(terminal_node) is not int or not 0 <= terminal_node < len(sa["domain_receiver"]):
        raise ValueError("explicit upstream terminal node required")
    if (sa["domain_receiver"][terminal_node] >= 0 or not sa["domain_open_boundary"][terminal_node]
            or wa["network_terminal_kind"][terminal_node] != "open_outflow"):
        raise ValueError("delta supply requires an explicit open export terminal")
    for target, source in (("forcing_time_seconds", "trace_time_seconds"),
                           ("forcing_water_volume_m3", "trace_volume_m3"),
                           ("forcing_water_depth_m", "trace_depth_m"),
                           ("forcing_water_outflow_m3_s", "trace_outflow_q_m3_s")):
        expected = wa[source][:-1] if source in ("trace_volume_m3", "trace_depth_m") else wa[source]
        if not np.array_equal(sa[target], expected):
            raise ValueError("delta upstream sediment differs from witnessed water trace")
    for sediment_key, water_key in (("domain_receiver", "network_receiver"),
                                    ("domain_width_m", "network_width_m"),
                                    ("domain_bed_elevation_m", "network_bed_elevation_m")):
        if not np.array_equal(sa[sediment_key], wa[water_key]):
            raise ValueError("delta upstream section differs from witnessed water")
    if not np.array_equal(sa["forcing_friction_slope"],
                          np.broadcast_to(wa["network_bed_slope"], sa["forcing_friction_slope"].shape)):
        raise ValueError("delta upstream friction slope differs from witnessed Manning water")
    return float(sa["step_exported_solid_m3"][:, terminal_node].sum())


def build_delta_sediment_candidate(terrain, land_mask, water_mask, main_path, geometry, water, sediment,
                                   terminal_node, config=None):
    validate_channel_geometry(geometry)
    if (geometry["metadata"]["source_identity_sha256"] != terrain.identity_sha256
            or geometry["identity_sha256"] != sediment["metadata"]["geometry_identity_sha256"]):
        raise ValueError("delta terrain differs from upstream canonical geometry source")
    supply = _export(geometry, water, sediment, terminal_node)
    _terminal_geometry(geometry, water, terminal_node, main_path[-1], terrain)
    config = DeltaConfig(porosity=sediment["metadata"]["material"]["porosity"]) if config is None else config
    if config.porosity != sediment["metadata"]["material"]["porosity"]:
        raise ValueError("delta deposit porosity differs from upstream material")
    candidate = build_delta_candidate_product(
        terrain, land_mask, water_mask, main_path, supply, _graph_identity(geometry),
        sediment["metadata"]["geometry_identity_sha256"], config, source_geometry=geometry)
    arrays = {}
    metadata = {"schema": SCHEMA, "status": "candidate", "terminal_node": terminal_node,
                "sediment_supply_solid_m3": supply,
                "supply_semantics": "upstream_export_to_uncertified_local_candidate",
                "topology_mutation": False, "natural_outlet_verified": False, "publishable": False,
                "revalidation_required": ["topology", "geometry", "hydraulics", "sediment", "outlet"]}
    for name, bundle in (("geometry", geometry), ("water", water), ("sediment", sediment), ("candidate", candidate)):
        _pack(arrays, metadata, name, bundle)
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_delta_sediment_candidate(result)
    return result


def validate_delta_sediment_candidate(bundle):
    a, m = bundle["arrays"], bundle["metadata"]
    if (bundle["identity_sha256"] != identity(a, m)
            or set(a) != {name + "__payload" for name in ("geometry", "water", "sediment", "candidate")}
            or set(m) != {"schema", "status", "terminal_node", "sediment_supply_solid_m3",
                          "supply_semantics", "topology_mutation", "natural_outlet_verified",
                          "publishable", "revalidation_required", "geometry", "water", "sediment", "candidate"}
            or m["schema"] != SCHEMA or m["status"] != "candidate"
            or any(m[key] is not False for key in ("topology_mutation", "natural_outlet_verified", "publishable"))
            or m["supply_semantics"] != "upstream_export_to_uncertified_local_candidate"
            or m["revalidation_required"] != ["topology", "geometry", "hydraulics", "sediment", "outlet"]):
        raise ValueError("invalid delta sediment candidate contract")
    water, sediment, candidate = (_unpack(a, m, name) for name in ("water", "sediment", "candidate"))
    geometry = _unpack(a, m, "geometry")
    supply = _export(geometry, water, sediment, m["terminal_node"])
    validate_delta_candidate_product(candidate)
    cm = candidate["metadata"]
    validate_channel_geometry(geometry)
    ca = candidate["arrays"]
    terrain = TerrainGrid(ca["terrain_elevation_m"], ca["terrain_valid_mask"], **cm["terrain_metadata"])
    if (geometry["metadata"]["source_identity_sha256"] != terrain.identity_sha256
            or geometry["identity_sha256"] != sediment["metadata"]["geometry_identity_sha256"]):
        raise ValueError("delta terrain differs from upstream canonical geometry source")
    _terminal_geometry(geometry, water, m["terminal_node"], ca["main_path_cells"][-1], terrain)
    if "source_geometry" in cm and cm["source_geometry"]["identity_sha256"] != geometry["identity_sha256"]:
        raise ValueError("delta candidate source geometry differs from upstream export")
    if (m["sediment_supply_solid_m3"] != supply or cm["sediment_input_solid_m3"] != supply
            or cm["parent_graph_identity_sha256"] != _graph_identity(geometry)
            or cm["parent_geometry_identity_sha256"] != sediment["metadata"]["geometry_identity_sha256"]
            or cm["event_record"]["parameters"]["config"]["porosity"] != sediment["metadata"]["material"]["porosity"]):
        raise ValueError("delta sediment candidate supply or material parent mismatch")
    return True


def save_delta_sediment_candidate(path, bundle):
    save_bundle(path, bundle, validator=validate_delta_sediment_candidate)


def load_delta_sediment_candidate(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256,
                       validator=validate_delta_sediment_candidate, max_bytes=4 * MAX_BYTES)
