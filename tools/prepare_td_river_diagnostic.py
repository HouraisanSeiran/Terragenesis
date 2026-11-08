"""Prepare a pinned TD native-grid river diagnostic without channel hydraulics."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import numpy as np

from terrain_pipeline.common_infra import file_sha256, load_bundle, validate_source
from terrain_pipeline.common_infra import BoundaryGrid, RainfallForcing, TerrainGrid
from terrain_pipeline.surface_rivers.metric_product import (
    build_diagnostic_product, load_diagnostic_product, save_diagnostic_product,
)
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.surface_rivers.metric_large_source import load_large_td_source


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "verification/td-river-diagnostic"
SCHEMA = "td-river-diagnostic-preparation-v1"


def _json_file(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                               indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _contracts(source, source_path, source_sha256):
    arrays, metadata = source["arrays"], source["metadata"]
    if metadata["boundary"]["policy"] != "all_edges_open":
        raise ValueError("pinned all_edges_open engineering boundary required")
    generation = metadata["provenance"].get("generation_metadata", {})
    model = generation.get("model", {})
    seed = generation.get("seed")
    if not isinstance(seed, (str, int)) or not str(seed).isdecimal():
        raise ValueError("generation seed required")
    revision = model.get("revision")
    condition_hash = generation.get("conditioning_identity")
    if not isinstance(revision, str) or not revision or not isinstance(condition_hash, str) or len(condition_hash) != 64:
        raise ValueError("model revision and conditioning identity required")
    if metadata["spacing_m"] != 30.:
        raise ValueError("native TD source must have 30 m spacing")
    terrain = TerrainGrid(arrays["height_m"], arrays["hydrology_mask"],
                          x0_m=float(metadata["origin_m_xz"][0]),
                          z0_m=float(metadata["origin_m_xz"][1]),
                          dx_m=30., dz_m=30., source_kind="generated_terrain",
                          source_id=source["identity_sha256"], source_sha256=source_sha256,
                          vertical_datum=metadata["vertical_datum"],
                          model_version=revision, generation_seed=int(seed),
                          condition_summary=condition_hash, source_path=str(source_path.resolve()))
    perimeter = np.zeros(terrain.valid_mask.shape, dtype=bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    open_mask = perimeter & terrain.valid_mask
    boundary = BoundaryGrid.from_outlet_mask(terrain, open_mask,
                                             source_id="all_edges_open_engineering_boundary",
                                             source_sha256=source_sha256)
    rain = np.zeros((3,) + terrain.valid_mask.shape, dtype=np.float64)
    rain[0, terrain.valid_mask] = 30.
    forcing_id = "td-river-diagnostic-pulse-30mmh-300s-v1"
    forcing_sha = hashlib.sha256((source_sha256 + ":" + forcing_id).encode("ascii")).hexdigest()
    forcing = RainfallForcing(np.array([0., 300., 600., 900.]), rain,
                              source_id=forcing_id, source_sha256=forcing_sha)
    return terrain, boundary, forcing, generation


def prepare(output, *, source_path=PRIMARY_PATH, source_sha256=PRIMARY_SHA256, source_format="pinned"):
    """Publish a complete diagnostic or a refusal at a new output directory."""
    output = Path(output).resolve()
    source_path = Path(source_path).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name("." + output.name + ".partial-" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        source_hash_before = file_sha256(source_path)
        if source_format == "td_1024":
            source = load_large_td_source(source_path, expected_sha256=source_sha256)
        elif source_format == "pinned":
            source = load_bundle(source_path, expected_sha256=source_sha256,
                                 validator=validate_source)
        else:
            raise ValueError("source_format must be pinned or td_1024")
        terrain, boundary, forcing, generation = _contracts(source, source_path, source_sha256)
        product = build_diagnostic_product(terrain, boundary, forcing)
        product_path = staging / "product.npz"
        save_diagnostic_product(product_path, product)
        product_sha = file_sha256(product_path)
        cold = load_diagnostic_product(product_path, expected_sha256=product_sha,
                                       expected_identity=product["identity_sha256"])
        if cold["identity_sha256"] != product["identity_sha256"]:
            raise ValueError("cold-read diagnostic identity mismatch")
        source_hash_after = file_sha256(source_path)
        if source_hash_before != source_sha256 or source_hash_after != source_sha256:
            raise ValueError("source changed during diagnostic preparation")
        budget = product["metadata"]["water_budget_m3"]
        valid = terrain.valid_mask
        perimeter = np.zeros(valid.shape, bool)
        perimeter[[0, -1], :] = True
        perimeter[:, [0, -1]] = True
        provenance = {
        "source_format": source_format, "source_path": str(source_path), "source_sha256_before": source_hash_before,
            "source_sha256_after": source_hash_after,
            "source_identity_sha256": source["identity_sha256"],
            "artifact_kind": source["metadata"]["provenance"]["artifact_kind"],
            "generation_seed": terrain.generation_seed,
            "model_revision": terrain.model_version,
            "conditioning_identity_sha256": terrain.condition_summary,
            "vertical_datum": terrain.vertical_datum, "crs": terrain.crs,
            "status": terrain.provenance_status,
            "origin_m_xz": [terrain.x0_m, terrain.z0_m],
            "spacing_m_xz": [terrain.dx_m, terrain.dz_m],
            "generation_metadata": generation,
        }
        boundary_audit = {
            "policy": "all_edges_open_engineering_boundary",
            "open_perimeter_cells": int(np.count_nonzero(boundary.kind == "open_outflow")),
            "valid_perimeter_cells": int(np.count_nonzero(perimeter & valid)),
            "closed_perimeter_cells": int(np.count_nonzero(perimeter & valid & (boundary.kind == "closed_wall"))),
            "unknown_cells": int(np.count_nonzero(boundary.kind == "unknown_boundary")),
            "natural_outlet_verified": False,
        }
        diagnostics = {
            "status": "diagnostic_runoff", "valid_cells": int(np.count_nonzero(valid)),
            "grid_shape_zx": list(valid.shape), "interval_seconds": [300., 300., 300.],
            "rain_mm_h": [30., 0., 0.],
            "lake_terminal_count": product["metadata"]["lake_terminal_count"],
            "unknown_terminal_count": product["metadata"]["unknown_terminal_count"],
            "routing_policy": product["metadata"]["routing_policy"],
            "active_receiver_count": int(np.count_nonzero(product["arrays"]["graph_receiver"] >= 0)),
            "terminal_count": int(np.count_nonzero(valid.ravel() & (product["arrays"]["graph_receiver"] < 0))),
            "cycle_count": 0, "unknown_crossing_count": 0, "implicit_open_outlet_count": 0,
            "local_residual_max_abs_m3": float(np.abs(product["arrays"]["runoff_balance_residual_m3"]).max()),
            "routing_residual_max_abs_m3": float(np.abs(product["arrays"]["routing_residual_m3"]).max()),
            "limitations": product["metadata"]["limitations"],
            "hydraulic_ready": False, "natural_outlet_verified": False,
            "publishable": False,
        }
        _json_file(staging / "provenance.json", provenance)
        _json_file(staging / "boundary-audit.json", boundary_audit)
        _json_file(staging / "mass-balance.json", budget)
        _json_file(staging / "diagnostics.json", diagnostics)
        manifest = {
            "schema": SCHEMA, "status": "diagnostic_runoff",
            "product": "product.npz", "product_sha256": product_sha,
            "product_identity_sha256": product["identity_sha256"],
            "source_sha256": source_sha256,
            "terrain_source_kind": terrain.source_kind,
            "terrain_source_sha256": terrain.source_sha256,
            "rainfall_source_sha256": forcing.source_sha256,
            "forcing_identity_sha256": forcing.identity_sha256,
            "parameter_sha256": product["metadata"]["runoff_metadata"]["parameter_sha256"],
            "solver_recipe": product["metadata"]["runoff_metadata"]["algorithm"],
            "routing_policy": product["metadata"]["routing_policy"],
            "time_semantics": product["metadata"]["time_semantics"],
            "boundary_semantics": "all_edges_open_engineering_boundary_outward_positive",
            "unknown_semantics": terrain.nodata_semantics,
            "native_grid_is_volume_basis": True,
            "amr_role": product["metadata"]["amr_role"],
            "uniform_role": product["metadata"]["uniform_role"],
            "provenance_status": terrain.provenance_status,
            "limitations": product["metadata"]["limitations"],
            "reports": {name: file_sha256(staging / name) for name in
                        ("provenance.json", "boundary-audit.json", "mass-balance.json", "diagnostics.json")},
            "hydraulic_ready": False, "natural_outlet_verified": False,
            "publishable": False, "cold_read_verified": True,
        }
        _json_file(staging / "manifest.json", manifest)
        staging.rename(output)
        return {"status": "diagnostic_runoff", "output": str(output),
                "product_sha256": product_sha,
                "rain_input_m3": budget["rain_input"],
                "open_outflow_m3": budget["open_outflow"],
                "combined_residual_m3": budget["combined_residual"],
                "valid_cells": diagnostics["valid_cells"]}
    except Exception as error:
        shutil.rmtree(staging)
        staging.mkdir()
        refusal = {"schema": SCHEMA, "status": "refused", "reason": str(error),
                   "source_format": source_format, "source_path": str(source_path), "source_sha256_expected": source_sha256,
                   "publishable": False}
        _json_file(staging / "refusal.json", refusal)
        staging.rename(output)
        return {"status": "refused", "output": str(output), "reason": str(error)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-sha256")
    parser.add_argument("--source-format", choices=("pinned", "td_1024"), default="pinned")
    args = parser.parse_args(argv)
    if (args.source is None) != (args.source_sha256 is None):
        parser.error("--source and --source-sha256 must be supplied together")
    stamp = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    output = args.output if args.output is not None else OUTPUT_ROOT / (stamp + "-" + uuid.uuid4().hex[:8])
    summary = prepare(output, source_path=args.source or PRIMARY_PATH,
                      source_sha256=args.source_sha256 or PRIMARY_SHA256,
                      source_format=args.source_format)
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0 if summary["status"] == "diagnostic_runoff" else 2


if __name__ == "__main__":
    raise SystemExit(main())
