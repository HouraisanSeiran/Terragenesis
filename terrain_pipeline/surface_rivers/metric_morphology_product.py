"""Saved native inputs and reproducible uncommitted morphology proposals."""

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import CutoffConfig, find_cutoff_candidate
from .metric_delta import DeltaConfig, build_delta_candidate
from terrain_pipeline.channel_geometry import BankPointbarConfig, BraidedConfig, build_bank_pointbar_candidate, build_braided_candidate
from terrain_pipeline.channel_geometry import FanFloodplainConfig, build_alluvial_fan_candidate, build_floodplain_candidate
from .metric_morphology_events import MorphologyEvent

SCHEMA = "terragenesis-morphology-proposal-product-v1"
KINDS = ("delta", "cutoff", "bank_pointbar", "braided", "alluvial_fan", "floodplain")
REVALIDATION = ("topology", "geometry", "hydraulics", "sediment", "outlet")


def _plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _build(kind, terrain, inputs, parameters):
    if kind not in KINDS:
        raise ValueError("unsupported morphology proposal kind")
    graph = identity({"centerline_xz_m": inputs["centerline_xz_m"], "path_cells": inputs["path_cells"]},
                     {"edge_ids": parameters["edge_ids"], "terrain_identity_sha256": terrain.identity_sha256,
                      "graph_status": "saved caller candidate design, not certified routing"})
    geometry = identity(inputs, {"terrain_identity_sha256": terrain.identity_sha256,
                                 "input_semantics": "saved native masks and design coordinates"})
    path = tuple(map(tuple, inputs["path_cells"].tolist()))
    config = parameters["config"]
    reason = None
    try:
        if kind == "delta":
            result = build_delta_candidate(terrain, inputs["land_mask"], inputs["water_mask"], path,
                parameters["solid_m3"], graph, geometry, DeltaConfig(**config))
        elif kind == "cutoff":
            result = find_cutoff_candidate(terrain, inputs["centerline_xz_m"], tuple(parameters["edge_ids"]),
                graph, geometry, 0., 0., CutoffConfig(**config))
        elif kind == "bank_pointbar":
            result = build_bank_pointbar_candidate(terrain, inputs["centerline_xz_m"], graph, geometry,
                parameters["solid_m3"], BankPointbarConfig(**config))
        elif kind == "braided":
            result = build_braided_candidate(terrain, path, inputs["water_mask"], graph, geometry,
                parameters["water_m3_s"], parameters["solid_m3"], BraidedConfig(**config))
        elif kind == "alluvial_fan":
            result = build_alluvial_fan_candidate(terrain, parameters["apex_xz_m"], parameters["direction_xz"],
                parameters["solid_m3"], graph, geometry, FanFloodplainConfig(**config))
        else:
            result = build_floodplain_candidate(terrain, inputs["centerline_xz_m"], parameters["water_depth_m"],
                graph, geometry, FanFloodplainConfig(**config))
    except ValueError as error:
        result = {"status": "rejected", "reason": str(error)}
    status = result["status"]
    if status == "candidate" and (len(parameters["edge_ids"]) != len(inputs["centerline_xz_m"]) - 1
            or len(set(parameters["edge_ids"])) != len(parameters["edge_ids"])):
        raise ValueError("morphology parent edge IDs do not correspond to saved centerline segments")
    reason = result.get("reason")
    output = {}
    record = {}
    for key, value in result.items():
        if isinstance(value, np.ndarray):
            output["result_" + key] = value
        elif key == "event" and value is not None:
            event = value
            affected = event.affected_edges if kind == "cutoff" else tuple(parameters["edge_ids"])
            event = MorphologyEvent(event.event_id, event.event_type, graph, geometry, affected,
                event.added_edges, event.retired_edges, event.water_transfer_m3, event.sediment_transfer_solid_m3,
                event.material_ledger, {**event.to_record()["parameters"], "parent_input_identity_sha256": geometry,
                    "status_semantics": "uncommitted native proposal; dynamic water/sediment revalidation pending"}, REVALIDATION)
            record["event_record"] = event.to_record()
        else:
            record[key] = _plain(value)
    arrays = {"terrain_elevation_m": terrain.elevation_m, "terrain_valid_mask": terrain.valid_mask,
              **{"input_" + key: value for key, value in inputs.items()}, **output}
    meta = {"schema": SCHEMA, "kind": kind, "status": status, "failure_reason": reason,
            "terrain_metadata": {name: getattr(terrain, name) for name in terrain.__dataclass_fields__ if name not in ("elevation_m", "valid_mask")},
            "terrain_identity_sha256": terrain.identity_sha256, "parent_graph_identity_sha256": graph,
            "parent_geometry_identity_sha256": geometry, "parameters": parameters, "result": record,
            "revalidation_required": list(REVALIDATION), "capabilities": {"topology_mutation": False,
                "dynamic_hydraulics": False, "dynamic_sediment": False, "natural_outlet": False, "publishable": False},
            "time_semantics": "static native proposal, no physical timestep or elapsed duration",
            "supply_provenance": "explicit local scenario input, not measured geological or solved sediment forcing"}
    arrays = {key: readonly(np.ascontiguousarray(value)) for key, value in arrays.items()}
    return {"arrays": arrays, "metadata": meta, "identity_sha256": identity(arrays, meta)}


def build_morphology_proposal(kind, terrain, inputs, parameters):
    return _build(kind, terrain, inputs, _plain(parameters))


def validate_morphology_proposal(bundle):
    a, m = bundle["arrays"], bundle["metadata"]
    if bundle["identity_sha256"] != identity(a, m) or m.get("schema") != SCHEMA:
        raise ValueError("morphology proposal identity/schema mismatch")
    terrain = TerrainGrid(a["terrain_elevation_m"], a["terrain_valid_mask"], **m["terrain_metadata"])
    inputs = {key.removeprefix("input_"): value for key, value in a.items() if key.startswith("input_")}
    rebuilt = _build(m["kind"], terrain, inputs, m["parameters"])
    if rebuilt["identity_sha256"] != bundle["identity_sha256"]:
        raise ValueError("morphology proposal cold native reconstruction mismatch")
    return True


def save_morphology_proposal(path, bundle):
    save_bundle(path, bundle, validator=validate_morphology_proposal)


def load_morphology_proposal(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_morphology_proposal)
