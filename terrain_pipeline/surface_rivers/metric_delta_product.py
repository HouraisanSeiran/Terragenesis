"""Auditable saved artifacts for bounded metric delta candidates.

This module deliberately separates candidate generation from persistence.  A saved
artifact contains the parent terrain, masks, sediment ledger, and distributary
polylines, but it does not claim that any candidate is a hydraulic graph edge.
"""

from dataclasses import fields
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.common_infra import RoutingGraph, TerrainGrid
from .metric_delta import DeltaConfig, build_delta_candidate
from .metric_morphology_events import event_from_record


SCHEMA = "terragenesis-delta-candidate-product-v2"
LEGACY_SCHEMA = "terragenesis-delta-candidate-product-v1"
ALGORITHM = "bounded-metric-delta-growth-candidate-v1"
GRAPH_SCHEMA = "terragenesis-delta-candidate-product-v3"
GRAPH_ALGORITHM = "source-graph-metric-delta-growth-candidate-v2"
_GRAPH_ARRAYS = ("receiver", "order_downstream_first", "valid_mask", "edge_length_m",
                 "edge_slope", "outlet_kind", "lake_id")
MAX_BYTES = 128 * 1024 * 1024
_ARRAYS = (
    "terrain_elevation_m", "terrain_valid_mask", "land_mask", "water_mask",
    "main_path_cells", "height_delta_m", "deposit_mask", "water_component_mask",
    "candidate_polylines", "candidate_lengths",
)
_METADATA = {
    "schema", "algorithm", "status", "terrain_metadata", "terrain_identity_sha256",
    "parent_graph_identity_sha256", "parent_geometry_identity_sha256",
    "sediment_input_solid_m3", "material_ledger", "mouth_cell",
    "candidate_edge_ids", "event_record", "revalidation_required", "capabilities", "units",
}
_REVALIDATION = ("topology", "geometry", "hydraulics", "sediment")
_CAPABILITIES = {"topology_mutation": False, "hydrodynamics": False,
                 "sediment_recompute": False, "natural_outlet": False,
                 "publishable": False}
_UNITS = {"elevation": "m", "solid": "m3", "porous_deposit": "m3"}
_BOUNDARY_EVIDENCE = {
    "land_water_classification": "caller_supplied_unverified",
    "upstream_path": "caller_supplied_unverified",
    "natural_outlet_verified": False,
    "water_forcing_bound": False,
    "sediment_forcing_bound": False,
    "revalidation_required": ["topology", "geometry", "hydraulics", "sediment", "outlet"],
}


def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(name + " must be a lowercase SHA256")


def _terrain_metadata(terrain):
    return {field.name: getattr(terrain, field.name) for field in fields(TerrainGrid)
            if field.name not in ("elevation_m", "valid_mask")}


def _cell_path_array(path, name, *, minimum=2):
    if not isinstance(path, tuple) or len(path) < minimum:
        raise ValueError(name + " requires a tuple of cells")
    result = np.asarray(path, dtype=np.int64)
    if result.shape != (len(path), 2):
        raise ValueError(name + " must have shape [N,2]")
    return result


def _candidate_arrays(candidates):
    if not isinstance(candidates, tuple):
        candidates = tuple(candidates)
    polylines = []
    edge_ids = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {"edge_id", "polyline"}:
            raise ValueError("invalid distributary candidate record")
        edge_id = candidate["edge_id"]
        if not isinstance(edge_id, str) or not edge_id:
            raise ValueError("candidate edge_id required")
        edge_ids.append(edge_id)
        polyline = _cell_path_array(tuple(candidate["polyline"]), "candidate polyline")
        polylines.append(polyline)
    if len(set(edge_ids)) != len(edge_ids):
        raise ValueError("candidate edge IDs must be unique")
    width = max((len(path) for path in polylines), default=2)
    encoded = np.full((len(polylines), width, 2), -1, dtype=np.int64)
    lengths = np.empty(len(polylines), dtype=np.int64)
    for index, path in enumerate(polylines):
        encoded[index, :len(path)] = path
        lengths[index] = len(path)
    return encoded, lengths, edge_ids


def _decode_candidates(arrays, metadata):
    encoded = arrays["candidate_polylines"]
    lengths = arrays["candidate_lengths"]
    edge_ids = metadata["candidate_edge_ids"]
    if (encoded.dtype != np.int64 or encoded.ndim != 3 or encoded.shape[2] != 2
            or lengths.dtype != np.int64 or lengths.shape != (encoded.shape[0],)
            or len(edge_ids) != encoded.shape[0]):
        raise ValueError("invalid encoded distributary candidates")
    if not isinstance(edge_ids, list) or any(type(edge_id) is not str or not edge_id for edge_id in edge_ids):
        raise ValueError("invalid candidate edge IDs")
    if len(set(edge_ids)) != len(edge_ids):
        raise ValueError("duplicate candidate edge IDs")
    result = []
    for index, length in enumerate(lengths):
        if not 2 <= int(length) <= encoded.shape[1]:
            raise ValueError("candidate polyline length outside bounds")
        path = encoded[index, :int(length)]
        if np.any(path < 0) or np.any(path[:, 0] >= arrays["terrain_elevation_m"].shape[0]) or np.any(path[:, 1] >= arrays["terrain_elevation_m"].shape[1]):
            raise ValueError("candidate polyline outside terrain")
        if np.any(np.max(np.abs(np.diff(path, axis=0)), axis=1) > 1):
            raise ValueError("candidate polyline is not 8-connected")
        if np.any(np.max(np.abs(np.diff(path, axis=0)), axis=1) == 0):
            raise ValueError("candidate polyline repeats a cell")
        result.append({"edge_id": edge_ids[index], "polyline": tuple(map(tuple, path.tolist()))})
    used = np.arange(encoded.shape[1])[None, :] < lengths[:, None]
    if np.any(encoded[~used] != -1):
        raise ValueError("candidate padding is not canonical")
    return tuple(result)


def _result_arrays(terrain, land_mask, water_mask, main_path, result):
    candidates = tuple(result["distributary_candidates"])
    encoded, lengths, edge_ids = _candidate_arrays(candidates)
    arrays = {
        "terrain_elevation_m": np.asarray(terrain.elevation_m, dtype=np.float64).copy(),
        "terrain_valid_mask": np.asarray(terrain.valid_mask, dtype=bool).copy(),
        "land_mask": np.asarray(land_mask, dtype=bool).copy(),
        "water_mask": np.asarray(water_mask, dtype=bool).copy(),
        "main_path_cells": _cell_path_array(main_path, "main_path").copy(),
        "height_delta_m": np.asarray(result["height_delta_m"], dtype=np.float64).copy(),
        "deposit_mask": np.asarray(result["deposit_mask"], dtype=bool).copy(),
        "water_component_mask": np.asarray(result["water_component_mask"], dtype=bool).copy(),
        "candidate_polylines": encoded,
        "candidate_lengths": lengths,
    }
    return arrays, edge_ids


def build_delta_candidate_product(terrain, land_mask, water_mask, main_path, sediment_solid_m3,
                                  parent_graph_identity_sha256, parent_geometry_identity_sha256,
                                  config=DeltaConfig(), *, source_graph=None, source_geometry=None):
    result = build_delta_candidate(terrain, land_mask, water_mask, main_path, sediment_solid_m3,
                                   parent_graph_identity_sha256, parent_geometry_identity_sha256, config,
                                   source_graph=source_graph, source_geometry=source_geometry)
    return make_delta_candidate_product(terrain, land_mask, water_mask, main_path,
                                        sediment_solid_m3, parent_graph_identity_sha256,
                                        parent_geometry_identity_sha256, result,
                                        source_graph=source_graph, source_geometry=source_geometry)


def make_delta_candidate_product(terrain, land_mask, water_mask, main_path, sediment_solid_m3,
                                 parent_graph_identity_sha256, parent_geometry_identity_sha256, result, *,
                                 source_graph=None, source_geometry=None):
    if not isinstance(terrain, TerrainGrid) or not isinstance(result, dict):
        raise ValueError("TerrainGrid and candidate result required")
    shape = terrain.elevation_m.shape
    for value, name in ((land_mask, "land_mask"), (water_mask, "water_mask")):
        if not isinstance(value, np.ndarray) or value.dtype != bool or value.shape != shape:
            raise ValueError(name + " must be a matching boolean array")
    if np.any(land_mask & water_mask):
        raise ValueError("land_mask and water_mask overlap")
    _sha(parent_graph_identity_sha256, "parent graph identity")
    _sha(parent_geometry_identity_sha256, "parent geometry identity")
    if isinstance(sediment_solid_m3, bool) or not isinstance(sediment_solid_m3, (int, float)) or not math.isfinite(sediment_solid_m3) or sediment_solid_m3 < 0.:
        raise ValueError("sediment_solid_m3 must be finite and nonnegative")
    if result.get("schema") != "terragenesis-delta-candidate-v1" or result.get("status") != "candidate":
        raise ValueError("candidate result schema/status mismatch")
    arrays, edge_ids = _result_arrays(terrain, land_mask, water_mask, main_path, result)
    ledger = dict(result["material_ledger"])
    event = result["event"]
    event_record = event.to_record()
    metadata = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "status": "candidate",
        "terrain_metadata": _terrain_metadata(terrain),
        "terrain_identity_sha256": terrain.identity_sha256,
        "parent_graph_identity_sha256": parent_graph_identity_sha256,
        "parent_geometry_identity_sha256": parent_geometry_identity_sha256,
        "sediment_input_solid_m3": float(sediment_solid_m3),
        "material_ledger": ledger,
        "mouth_cell": list(result["mouth_cell"]),
        "candidate_edge_ids": edge_ids,
        "event_record": event_record,
        "revalidation_required": list(_REVALIDATION),
        "capabilities": dict(_CAPABILITIES),
        "units": dict(_UNITS),
        "boundary_evidence": {**_BOUNDARY_EVIDENCE,
                              "revalidation_required": list(_BOUNDARY_EVIDENCE["revalidation_required"])},
    }
    if source_graph is not None or source_geometry is not None:
        metadata["schema"] = GRAPH_SCHEMA
        metadata["algorithm"] = GRAPH_ALGORITHM
        if source_graph is not None:
            if source_geometry is not None or not isinstance(source_graph, RoutingGraph):
                raise ValueError("select one upstream source graph or geometry")
            arrays.update({"source_graph_" + name: getattr(source_graph, name) for name in _GRAPH_ARRAYS})
            metadata["source_graph"] = {"terrain_identity_sha256": source_graph.terrain_identity_sha256,
                                        "boundary_identity_sha256": source_graph.boundary_identity_sha256,
                                        "policy": source_graph.policy}
        else:
            from .metric_morphology_coupling import _pack
            _pack(arrays, metadata, "source_geometry", source_geometry)
    arrays = {name: readonly(value) for name, value in arrays.items()}
    product = {"arrays": arrays, "metadata": metadata,
               "identity_sha256": identity(arrays, metadata)}
    validate_delta_candidate_product(product)
    return product


def validate_delta_candidate_product(product):
    if not isinstance(product, dict) or set(product) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid delta candidate product")
    arrays, metadata = product["arrays"], product["metadata"]
    graph_version = metadata.get("schema") == GRAPH_SCHEMA
    source_graph = source_geometry = None
    extra_arrays, extra_metadata = set(), set()
    if graph_version:
        if ("source_graph" in metadata) == ("source_geometry" in metadata):
            raise ValueError("saved delta requires one source graph or geometry")
        if "source_graph" in metadata:
            extra_arrays = {"source_graph_" + name for name in _GRAPH_ARRAYS}
            extra_metadata = {"source_graph"}
            source_graph = RoutingGraph(**{name: arrays["source_graph_" + name] for name in _GRAPH_ARRAYS},
                                        **metadata["source_graph"])
        else:
            from .metric_morphology_coupling import _unpack
            extra_arrays, extra_metadata = {"source_geometry__payload"}, {"source_geometry"}
            source_geometry = _unpack(arrays, metadata, "source_geometry")
    if (set(arrays) != set(_ARRAYS) | extra_arrays or not isinstance(metadata, dict)
            or metadata.get("schema") not in (SCHEMA, LEGACY_SCHEMA, GRAPH_SCHEMA)
            or set(metadata) != (_METADATA | {"boundary_evidence"} | extra_metadata
                                 if metadata.get("schema") != LEGACY_SCHEMA else _METADATA)
            or metadata["algorithm"] != (GRAPH_ALGORITHM if graph_version else ALGORITHM)
            or metadata["status"] != "candidate"
            or product["identity_sha256"] != identity(arrays, metadata)):
        raise ValueError("delta candidate schema or identity mismatch")
    if (metadata["units"] != _UNITS or metadata["capabilities"] != _CAPABILITIES
            or metadata["revalidation_required"] != list(_REVALIDATION)):
        raise ValueError("delta candidate units/capability/revalidation mismatch")
    # Historical v1 candidates retain their identity and remain uncertified.
    if "boundary_evidence" in metadata and metadata["boundary_evidence"] != _BOUNDARY_EVIDENCE:
        raise ValueError("delta caller supplied boundary evidence cannot certify a natural outlet")
    if (not isinstance(metadata["sediment_input_solid_m3"], (int, float))
            or isinstance(metadata["sediment_input_solid_m3"], bool)
            or not math.isfinite(metadata["sediment_input_solid_m3"])
            or metadata["sediment_input_solid_m3"] < 0.):
        raise ValueError("invalid delta sediment input")
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("delta candidate byte budget exceeded")
    terrain = TerrainGrid(arrays["terrain_elevation_m"], arrays["terrain_valid_mask"],
                          **metadata["terrain_metadata"])
    if terrain.identity_sha256 != metadata["terrain_identity_sha256"]:
        raise ValueError("delta terrain identity mismatch")
    shape = terrain.elevation_m.shape
    for name in ("land_mask", "water_mask", "deposit_mask", "water_component_mask"):
        value = arrays[name]
        if value.dtype != bool or value.shape != shape:
            raise ValueError("invalid delta mask: " + name)
    if np.any(arrays["land_mask"] & arrays["water_mask"]):
        raise ValueError("delta land/water overlap")
    if np.any((arrays["land_mask"] | arrays["water_mask"]) & ~terrain.valid_mask):
        raise ValueError("delta land/water classification includes unknown terrain")
    if np.any(~arrays["water_component_mask"] & arrays["deposit_mask"]):
        raise ValueError("deposit outside connected water component")
    delta = arrays["height_delta_m"]
    if delta.dtype != np.float64 or delta.shape != shape or not np.isfinite(delta).all() or np.any(delta < 0.):
        raise ValueError("invalid delta height change")
    if np.any((delta != 0.) & ~arrays["water_mask"]) or np.any((delta > 0.) != arrays["deposit_mask"]):
        raise ValueError("height change outside declared water deposit")
    main_path = arrays["main_path_cells"]
    if main_path.dtype != np.int64 or main_path.ndim != 2 or main_path.shape[1] != 2 or len(main_path) < 2:
        raise ValueError("invalid saved main path")
    if np.any(main_path < 0) or np.any(main_path[:, 0] >= shape[0]) or np.any(main_path[:, 1] >= shape[1]):
        raise ValueError("main path outside terrain")
    if not graph_version:
        for first, second in zip(main_path, main_path[1:]):
            if np.max(np.abs(second - first)) != 1:
                raise ValueError("main path is not 8-connected")
        transitions = [(tuple(first), tuple(second)) for first, second in zip(main_path, main_path[1:])
                       if arrays["land_mask"][tuple(first)] and arrays["water_mask"][tuple(second)]]
        if not transitions or tuple(metadata["mouth_cell"]) != transitions[-1][1]:
            raise ValueError("saved mouth does not match land-to-water path")
    candidates = _decode_candidates(arrays, metadata)
    mouth = tuple(metadata["mouth_cell"])
    component = arrays["water_component_mask"]
    for candidate in candidates:
        path = candidate["polyline"]
        if path[0] != mouth or any(not component[cell] for cell in path):
            raise ValueError("candidate leaves connected water component")
    _sha(metadata["parent_graph_identity_sha256"], "parent graph identity")
    _sha(metadata["parent_geometry_identity_sha256"], "parent geometry identity")
    event = event_from_record(metadata["event_record"])
    if (event.event_type != "delta_growth" or event.status != "candidate"
            or event.water_transfer_m3 != 0. or event.affected_edges
            or event.parent_graph_identity_sha256 != metadata["parent_graph_identity_sha256"]
            or event.parent_geometry_identity_sha256 != metadata["parent_geometry_identity_sha256"]
            or event.added_edges or event.retired_edges
            or event.parameters["topology_status"] != "candidate_geometry_only"
            or tuple(event.revalidation_required) != _REVALIDATION
            or tuple(event.parameters["mouth"]) != mouth
            or event.parameters["candidate_count"] != len(candidates)):
        raise ValueError("delta event does not describe geometry-only candidates")
    ledger = metadata["material_ledger"]
    required = {"deposited_solid_m3", "exported_solid_m3", "unresolved_solid_m3",
                "cut_rock_m3", "fill_m3", "porous_deposit_m3"}
    if set(ledger) != required or any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0. for value in ledger.values()):
        raise ValueError("invalid delta material ledger")
    if not math.isclose(ledger["deposited_solid_m3"] + ledger["unresolved_solid_m3"] + ledger["exported_solid_m3"],
                        metadata["sediment_input_solid_m3"], rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError("delta solid-volume conservation mismatch")
    config = DeltaConfig(**dict(event.parameters["config"]))
    if not math.isclose(ledger["porous_deposit_m3"], ledger["deposited_solid_m3"] / (1. - config.porosity), rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError("delta pore-volume mismatch")
    gridded_solid = float(np.sum(delta)) * terrain.cell_area_m2 * (1. - config.porosity)
    if (not math.isclose(gridded_solid, ledger["deposited_solid_m3"], rel_tol=1e-10, abs_tol=1e-10)
            or np.any(delta > config.max_deposit_depth_m * (1. + 1e-12))
            or ledger["exported_solid_m3"] != 0. or ledger["cut_rock_m3"] != 0. or ledger["fill_m3"] != 0.
            or not math.isclose(event.sediment_transfer_solid_m3, metadata["sediment_input_solid_m3"], rel_tol=0., abs_tol=1e-12)
            or dict(event.material_ledger) != ledger):
        raise ValueError("delta gridded deposit or event ledger mismatch")
    # Cold re-run: the saved arrays alone must reproduce the candidate exactly.
    rebuilt = build_delta_candidate(terrain, arrays["land_mask"], arrays["water_mask"],
                                    tuple(map(tuple, main_path.tolist())), metadata["sediment_input_solid_m3"],
                                    metadata["parent_graph_identity_sha256"],
                                    metadata["parent_geometry_identity_sha256"], config,
                                    source_graph=source_graph, source_geometry=source_geometry)
    if (rebuilt["event"].identity_sha256 != event.identity_sha256
            or rebuilt["mouth_cell"] != mouth
            or not np.array_equal(rebuilt["height_delta_m"], delta)
            or not np.array_equal(rebuilt["deposit_mask"], arrays["deposit_mask"])
            or not np.array_equal(rebuilt["water_component_mask"], component)
            or tuple(rebuilt["distributary_candidates"]) != candidates):
        raise ValueError("delta candidate is not reproducible from saved inputs")
    return True


def save_delta_candidate_product(path, product):
    save_bundle(path, product, validator=validate_delta_candidate_product)


def load_delta_candidate_product(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256,
                       validator=validate_delta_candidate_product, max_bytes=MAX_BYTES)
