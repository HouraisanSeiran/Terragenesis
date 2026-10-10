"""Prepare a pinned real-TD local candidate package for morphology review."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, save_bundle
from terrain_pipeline.surface_rivers.metric_bank_braiding import (
    BankPointbarConfig, BraidedConfig, build_bank_pointbar_candidate,
    build_braided_candidate)
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_cutoff import CutoffConfig, find_cutoff_candidate
from terrain_pipeline.surface_rivers.metric_delta import DeltaConfig
from terrain_pipeline.surface_rivers.metric_delta_product import save_delta_candidate_product
from terrain_pipeline.surface_rivers.metric_fan_floodplain import (
    FanFloodplainConfig, build_alluvial_fan_candidate, build_floodplain_candidate)
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256, load_td_source


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "verification/td-morphology-candidates/td256-20261010-01"
REFERENCE_REPORT = ROOT / "verification/reference-routing/td256-20261009-01/report.json"
SCHEMA = "td-real-morphology-candidate-set-v1"


def _save_generic(path, arrays, metadata, *, terrain_identity_sha256=None):
    if terrain_identity_sha256 is not None:
        metadata = dict(metadata)
        metadata["terrain_identity_sha256"] = terrain_identity_sha256
    record = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    save_bundle(path, record, validator=lambda value: None)
    return {"path": path.name, "sha256": file_sha256(path), "identity_sha256": record["identity_sha256"]}


def _terrain_window(source):
    arrays, metadata = source["arrays"], source["metadata"]
    rows, columns = arrays["height_m"].shape
    center_row, center_column = rows // 2, columns // 2
    window = (slice(center_row - 16, center_row + 17), slice(center_column - 16, center_column + 17))
    spacing = metadata["spacing_m"]
    origin_x, origin_z = metadata["origin_m_xz"]
    terrain = TerrainGrid(
        arrays["height_m"][window].copy(), arrays["valid_mask"][window].copy(),
        origin_x + (center_column - 16) * spacing,
        origin_z + (center_row - 16) * spacing, spacing, spacing,
        "generated_terrain", source["identity_sha256"], PRIMARY_SHA256,
        vertical_datum="sea_zero_m", model_version="Terrain Diffusion",
        generation_seed=20261001, condition_summary="pinned TD source window",
        source_path=str(PRIMARY_PATH))
    return terrain


def _point(terrain, row, column):
    return [terrain.x0_m + column * terrain.dx_m, terrain.z0_m + row * terrain.dz_m]


def _build(output):
    source = load_td_source()
    reference_report = json.loads(REFERENCE_REPORT.read_text(encoding="utf-8"))
    parent_graph = reference_report["graph_identity_sha256"]
    terrain = _terrain_window(source)
    shape = terrain.elevation_m.shape
    land = np.zeros(shape, dtype=bool)
    water = np.zeros(shape, dtype=bool)
    land[:, :16] = terrain.valid_mask[:, :16]
    water[:, 16:] = terrain.valid_mask[:, 16:]
    delta_path = tuple((16, column) for column in range(12, 18))
    centerline = np.asarray([_point(terrain, 5, 5), _point(terrain, 5, 14),
                             _point(terrain, 10, 20), _point(terrain, 20, 20),
                             _point(terrain, 27, 14), _point(terrain, 27, 5)], dtype=np.float64)
    edge_ids = tuple("td-edge-%02d" % index for index in range(len(centerline) - 1))
    parent_geometry = hashlib.sha256(b"td256-local-morphology-candidate-v1").hexdigest()
    inputs = {
        "terrain_elevation_m": terrain.elevation_m.copy(), "terrain_valid_mask": terrain.valid_mask.copy(),
        "land_mask": land, "water_mask": water, "delta_path_cells": np.asarray(delta_path, np.int64),
        "centerline_xz_m": centerline,
    }
    input_meta = {"schema": "td-real-morphology-input-v1", "source_path": str(PRIMARY_PATH),
                  "source_file_sha256": PRIMARY_SHA256, "source_identity_sha256": source["identity_sha256"],
                  "terrain_identity_sha256": terrain.identity_sha256,
                  "parent_graph_identity_sha256": parent_graph,
                  "parent_geometry_identity_sha256": parent_geometry,
                  "interpretation": "explicit local land-water and centerline test over authentic TD elevation; not natural estuary certification",
                  "window_shape_zx": list(shape), "origin_x_m": terrain.x0_m,
                  "origin_z_m": terrain.z0_m, "spacing_m": terrain.dx_m,
                  "coordinates": "X east, Z south, Y up; arrays [z,x]"}
    artifacts = {"inputs": _save_generic(output / "inputs.npz", inputs, input_meta)}
    delta_product = __import__("terrain_pipeline.surface_rivers.metric_delta_product", fromlist=["build_delta_candidate_product"]).build_delta_candidate_product(
        terrain, land, water, delta_path, 1200., parent_graph, parent_geometry,
        DeltaConfig(max_radius_cells=4, max_deposit_depth_m=.8, seed=17))
    save_delta_candidate_product(output / "delta-candidate.npz", delta_product)
    artifacts["delta"] = {"path": "delta-candidate.npz", "sha256": file_sha256(output / "delta-candidate.npz"),
                           "identity_sha256": delta_product["identity_sha256"]}
    cutoff = find_cutoff_candidate(
        terrain, centerline, edge_ids, parent_graph, parent_geometry, 12., 4.,
        CutoffConfig(neck_distance_m=900., min_loop_length_m=60., max_bed_rise_m=10000.))
    artifacts["cutoff"] = _save_generic(output / "cutoff.npz", {
        "shortcut_xz_m": cutoff.get("shortcut_xz_m", np.empty((0, 2), np.float64)),
        "loop_xz_m": cutoff.get("loop_xz_m", np.empty((0, 2), np.float64)),
    }, {"schema": "td-cutoff-candidate-artifact-v1", "source_identity_sha256": source["identity_sha256"],
        "parent_graph_identity_sha256": parent_graph, "parent_geometry_identity_sha256": parent_geometry,
        "status": cutoff["status"], "event_record": cutoff["event"].to_record() if cutoff["event"] else None,
        "capabilities": cutoff["capabilities"]}, terrain_identity_sha256=terrain.identity_sha256)
    bank = build_bank_pointbar_candidate(
        terrain, centerline, parent_graph, parent_geometry, 20.,
        BankPointbarConfig(max_erosion_depth_m=.05, max_deposit_depth_m=.05))
    artifacts["bank_pointbar"] = _save_generic(output / "bank-pointbar.npz", {
        "height_delta_m": bank["height_delta_m"], "erosion_mask": bank["erosion_mask"],
        "deposit_mask": bank["deposit_mask"],
    }, {"schema": "td-bank-pointbar-candidate-artifact-v1", "source_identity_sha256": source["identity_sha256"],
        "parent_graph_identity_sha256": parent_graph, "parent_geometry_identity_sha256": parent_geometry,
        "status": bank["status"], "solid_ledger": bank["solid_ledger"],
        "event_record": bank["event"].to_record(), "capabilities": {"hydraulic": False, "publishable": False}}, terrain_identity_sha256=terrain.identity_sha256)
    braid_water = np.zeros(shape, dtype=bool)
    for row, column in delta_path:
        braid_water[max(0, row - 1):min(shape[0], row + 2), column] = terrain.valid_mask[max(0, row - 1):min(shape[0], row + 2), column]
    braided = build_braided_candidate(
        terrain, delta_path, braid_water, parent_graph, parent_geometry, 8., 12.,
        BraidedConfig(max_candidates=3, branch_fraction=.2))
    artifacts["braided"] = _save_generic(output / "braided.npz", {
        "bar_mask": braided["bar_mask"], "height_delta_m": braided["height_delta_m"],
        "flow_split": np.asarray(braided["flow_split"], np.float64),
    }, {"schema": "td-braided-candidate-artifact-v1", "source_identity_sha256": source["identity_sha256"],
        "parent_graph_identity_sha256": parent_graph, "parent_geometry_identity_sha256": parent_geometry,
        "status": braided["status"], "candidate_paths": [list(map(list, path)) for path in braided["candidate_paths"]],
        "solid_ledger": braided["solid_ledger"], "event_record": braided["event"].to_record(),
        "capabilities": {"routing_graph_written": False, "hydraulic": False, "publishable": False}}, terrain_identity_sha256=terrain.identity_sha256)
    fan = build_alluvial_fan_candidate(
        terrain, _point(terrain, 16, 16), [1., 0.], 1200., parent_graph, parent_geometry,
        FanFloodplainConfig(max_fan_radius_m=180., max_deposit_depth_m=.5))
    artifacts["alluvial_fan"] = _save_generic(output / "alluvial-fan.npz", {
        "height_delta_m": fan["height_delta_m"], "deposit_mask": fan["deposit_mask"],
        "footprint": fan["footprint"],
    }, {"schema": "td-alluvial-fan-candidate-artifact-v1", "source_identity_sha256": source["identity_sha256"],
        "parent_graph_identity_sha256": parent_graph, "parent_geometry_identity_sha256": parent_geometry,
        "status": fan["status"], "material_ledger": fan["material_ledger"],
        "event_record": fan["event"].to_record(), "capabilities": fan["capabilities"]}, terrain_identity_sha256=terrain.identity_sha256)
    floodplain = build_floodplain_candidate(
        terrain, centerline, 20., parent_graph, parent_geometry,
        FanFloodplainConfig(bank_height_m=30., max_floodplain_half_width_m=180.))
    artifacts["floodplain"] = _save_generic(output / "floodplain.npz", {
        "inundation_mask": floodplain["inundation_mask"], "height_delta_m": floodplain["height_delta_m"],
    }, {"schema": "td-floodplain-candidate-artifact-v1", "source_identity_sha256": source["identity_sha256"],
        "parent_graph_identity_sha256": parent_graph, "parent_geometry_identity_sha256": parent_geometry,
        "status": floodplain["status"], "storage_proxy_m3": floodplain["storage_proxy_m3"],
        "event_record": floodplain["event"].to_record(), "capabilities": floodplain["capabilities"]}, terrain_identity_sha256=terrain.identity_sha256)
    summary = {"schema": SCHEMA, "status": "candidate_set", "source": {"path": str(PRIMARY_PATH),
               "sha256": PRIMARY_SHA256, "identity_sha256": source["identity_sha256"]},
               "terrain_identity_sha256": terrain.identity_sha256,
               "parent_graph_identity_sha256": parent_graph,
               "parent_geometry_identity_sha256": parent_geometry,
               "interpretation": input_meta["interpretation"], "artifacts": artifacts,
               "capabilities": {"hydraulic": False, "natural_outlet": False, "publishable": False}}
    summary_bytes = json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    summary["summary_body_sha256"] = hashlib.sha256(summary_bytes).hexdigest()
    return summary


def prepare(output=DEFAULT_OUTPUT):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".partial-", dir=output.parent))
    published = False
    try:
        result = _build(staging)
        (staging / "summary.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staging.rename(output)
        published = True
        return result
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve()),
                      "artifacts": list(result["artifacts"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
