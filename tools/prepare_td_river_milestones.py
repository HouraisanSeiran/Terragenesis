"""Prepare and cold-audit M1/M2 diagnostics on an immutable native TD grid."""

import argparse
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import shutil
import time
import uuid

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle, validate_source
from terrain_pipeline.surface_rivers.metric_drainage import accumulate_local_discharge
from terrain_pipeline.surface_rivers.metric_forcing import (
    SpatialRainRecipe, build_spatial_forcing, load_spatial_forcing_package,
    save_spatial_forcing_package,
)
from terrain_pipeline.surface_rivers.metric_large_source import load_large_td_source
from terrain_pipeline.surface_rivers.metric_output import (
    load_diagnostic_output, sample_diagnostic_output, save_diagnostic_output,
)
from terrain_pipeline.surface_rivers.metric_product import (
    build_diagnostic_product, load_diagnostic_product, save_diagnostic_product,
)
from terrain_pipeline.surface_rivers.metric_routing_comparison import (
    compare_routing_policies, decode_routing_comparison, load_routing_comparison,
    save_routing_comparison,
)
from terrain_pipeline.surface_rivers.metric_source import (
    load_source_registration, register_source, save_source_registration, slice_tile,
)
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from tools.prepare_td_river_diagnostic import ROOT, _contracts


SCHEMA = "td-river-m1-m2-preparation-v1"
FROZEN_PATHS = (
    "terrain_pipeline/surface_rivers/drainage.py",
    "terrain_pipeline/rainfall_runoff.py",
    "terrain_pipeline/td_basin_hierarchy.py",
    "terrain_pipeline/td_basin_source.py",
    "diffusion/geographic_noise.py",
    "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz",
)
HISTORICAL_HIERARCHY_IDENTITY = "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"


def _json_file(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _pins():
    return {name: file_sha256(ROOT / name) for name in FROZEN_PATHS}


def _historical_d4(terrain):
    path = ROOT / FROZEN_PATHS[-1]
    historical = load_basin_hierarchy(path, expected_sha256=file_sha256(path),
                                      expected_identity=HISTORICAL_HIERARCHY_IDENTITY)
    arrays, meta = historical["arrays"], historical["metadata"]
    same = (terrain.elevation_m.shape == arrays["height_m"].shape
            and np.array_equal(terrain.elevation_m, arrays["height_m"])
            and np.array_equal(terrain.valid_mask, arrays["valid_mask"])
            and meta["origin_m_xz"] == [terrain.x0_m, terrain.z0_m]
            and meta["spacing_m"] == terrain.dx_m == terrain.dz_m)
    receiver = arrays["receiver"].ravel()
    valid = arrays["valid_mask"].ravel()
    return {"path": str(path), "sha256": file_sha256(path),
            "identity_sha256": historical["identity_sha256"],
            "algorithm": meta["algorithm"], "grid_shape_zx": list(arrays["height_m"].shape),
            "terminal_count": int(np.count_nonzero(valid & (receiver < 0))),
            "receiver_count": int(np.count_nonzero(receiver >= 0)),
            "same_source_window": same,
            "comparison_role": "same_original_bed_distinct_boundary_and_D4_hierarchy_policy" if same
                               else "historical_256_reference_not_same_expanded_1024_source",
            "preserved": True, "natural_outlet_verified": False}


def _artifact(path, value, saver):
    saver(path, value)
    return {"path": path.name, "sha256": file_sha256(path),
            "identity_sha256": value["identity_sha256"]}


def _tiles(terrain, boundary, forcing, recipe):
    rows, cols = terrain.valid_mask.shape
    row_edges = sorted({0, rows // 2, rows})
    col_edges = sorted({0, cols // 2, cols})
    total_area = 0.
    tile_records = []
    for r0, r1 in zip(row_edges[:-1], row_edges[1:]):
        for c0, c1 in zip(col_edges[:-1], col_edges[1:]):
            tile = slice_tile(terrain, boundary, r0, r1, c0, c1)
            child = tile["terrain"]
            expected = terrain.elevation_m[r0:r1, c0:c1]
            if not np.array_equal(child.elevation_m, expected):
                raise ValueError("tile changed source heights")
            if child.world_xz(0) != terrain.world_xz(r0 * cols + c0):
                raise ValueError("tile changed source coordinates")
            child_forcing, package = build_spatial_forcing(
                child, forcing.time_seconds, np.array([30., 0., 0.]), recipe)
            if not np.array_equal(child_forcing.rain_mm_h, forcing.rain_mm_h[:, r0:r1, c0:c1]):
                raise ValueError("spatial rainfall differs at tile boundaries")
            cut = np.zeros(child.valid_mask.shape, bool)
            if r0:
                cut[0] = True
            if r1 < rows:
                cut[-1] = True
            if c0:
                cut[:, 0] = True
            if c1 < cols:
                cut[:, -1] = True
            if np.any(tile["boundary"].kind[cut] != "unknown_boundary"):
                raise ValueError("internal tile cut opened an outlet")
            area = float(child.valid_mask.sum()) * child.cell_area_m2
            total_area += area
            tile_records.append({"window_zx": [r0, r1, c0, c1], "valid_area_m2": area,
                                 "origin_m_xz": [child.x0_m, child.z0_m],
                                 "registration_identity_sha256": tile["identity_sha256"]})
            del package, child_forcing, tile, child
    area = float(terrain.valid_mask.sum()) * terrain.cell_area_m2
    if total_area != area:
        raise ValueError("tile area duplicates or omits source cells")
    return {"rain_bit_exact": True, "heights_bit_exact": True,
            "coordinates_equal": True, "unique_area_m2": area,
            "internal_cut_open_count": 0, "tiles": tile_records}


def _routing_ledgers(graphs, product):
    local = product["arrays"]["local_q_m3_s"]
    durations = np.diff(product["arrays"]["time_seconds"])
    reports = {}
    categories = ("open_outflow", "lake_retained", "unknown_pending", "prescribed_boundary_candidate")
    for name, graph in graphs.items():
        records = []
        edge_ids = np.flatnonzero(graph.receiver >= 0)
        scale = max(1., float(local.sum()))
        for step, dt in enumerate(durations):
            result = accumulate_local_discharge(graph, local[step])
            flow = result["routed_q_m3_s"].ravel()
            # Independent node balance: no dependence on the routing visit order.
            donor_inflow = np.bincount(graph.receiver[edge_ids], weights=flow[edge_ids],
                                       minlength=graph.receiver.size)
            node_residual = flow - local[step].ravel() - donor_inflow
            error = float(np.max(np.abs(node_residual)))
            if error > 1e-10 * scale or abs(result["residual_m3_s"]) > 1e-10 * scale:
                raise ValueError("diagnostic confluence or terminal balance failed")
            records.append({"interval_start_s": float(product["arrays"]["time_seconds"][step]),
                            "interval_end_s": float(product["arrays"]["time_seconds"][step + 1]),
                            "local_release_m3": result["input_total_m3_s"] * float(dt),
                            **{key + "_m3": result[key + "_m3_s"] * float(dt) for key in categories},
                            "routing_residual_m3": result["residual_m3_s"] * float(dt),
                            "node_residual_max_m3_s": error})
            del result, flow, donor_inflow, node_residual
        reports[name] = {"policy": graph.policy, "identity_sha256": graph.identity_sha256,
                         "valid_cells": int(graph.valid_mask.sum()),
                         "receiver_count": int(edge_ids.size),
                         "closed_candidate_count": int(np.count_nonzero(graph.outlet_kind == "lake_preserved")),
                         "open_outlet_count": int(np.count_nonzero(graph.outlet_kind == "open_outflow")),
                         "unknown_terminal_count": int(np.count_nonzero(graph.outlet_kind == "unknown_boundary")),
                         "intervals": records,
                         "totals_m3": {key: float(sum(record[key] for record in records))
                                       for key in ("local_release_m3",) + tuple(name + "_m3" for name in categories)}}
    return reports


def _sampling_check(dense, sparse):
    da, sa = dense["arrays"], sparse["arrays"]
    state_names = [name for name in da if name.endswith("_mm")]
    if not state_names:
        raise ValueError("output sampler did not save hydrology states")
    same_states = all(np.array_equal(da[name][-1], sa[name][-1]) for name in state_names)
    cumulative_names = [name for name in da if "cumulative" in name]
    if not cumulative_names:
        raise ValueError("output sampler did not save cumulative water")
    same_water = all(np.allclose(da[name][-1], sa[name][-1], rtol=1e-12, atol=1e-9)
                     for name in cumulative_names)
    if not same_states or not same_water:
        raise ValueError("output frequency changed final state or total water")
    return {"dense_time_seconds": da["state_time_seconds"].tolist(),
            "sparse_time_seconds": sa["state_time_seconds"].tolist(),
            "same_final_states": same_states, "same_cumulative_water": same_water,
            "state_fields": state_names, "cumulative_fields": cumulative_names}


def _audit_output_against_product(sampled, product):
    arrays, source = sampled["arrays"], product["arrays"]
    if (sampled["metadata"]["source_water_budget_m3"] != product["metadata"]["water_budget_m3"]
            or not np.array_equal(arrays["source_time_seconds"], source["time_seconds"])
            or not np.array_equal(arrays["valid_cell_ids"], source["valid_cell_ids"])):
        raise ValueError("sampled output time, budget, or cells differ from original product")
    indices = arrays["state_indices"]
    for key in ("soil_mm", "fast_mm", "slow_mm"):
        if not np.array_equal(arrays[key], source["runoff_" + key][indices]):
            raise ValueError("sampled output states differ from original product")
    dt = np.diff(source["time_seconds"])
    for group, (start, stop) in enumerate(zip(indices[:-1], indices[1:])):
        integrated = np.sum(source["local_q_m3_s"][start:stop] * dt[start:stop, None, None], axis=0)
        observed = arrays["local_q_m3_s"][group] * arrays["interval_seconds"][group]
        if not np.allclose(observed, integrated, rtol=1e-12, atol=1e-10):
            raise ValueError("sampled output skipped or altered native local release")
        for target, origin in (("rain_volume_m3", "rain_volume_m3"),
                               ("et_volume_m3", "et_volume_m3"),
                               ("storage_change_m3", "storage_change_m3"),
                               ("local_release_volume_m3", "outflow_volume_m3")):
            native_intervals = np.sum(source["runoff_" + origin], axis=1, dtype=np.float64)
            if not np.isclose(arrays[target][group], native_intervals[start:stop].sum(),
                              rtol=1e-12, atol=1e-9):
                raise ValueError("sampled interval ledger differs from native intervals")
        for name in ("open_outflow", "lake_retained", "unknown_pending", "prescribed_boundary_candidate"):
            if not np.isclose(arrays[name + "_volume_m3"][group],
                              source[name + "_volume_interval_m3"][start:stop].sum(),
                              rtol=1e-12, atol=1e-9):
                raise ValueError("sampled terminal budget differs from native intervals")


def audit_saved(directory):
    """Read and independently audit saved evidence without terrain or runoff generation."""
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "diagnostic_m1_m2":
        raise ValueError("unsupported M1/M2 manifest")
    if any(manifest.get(key) is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("M1/M2 manifest cannot promote capabilities")

    def read(name, loader):
        pin = manifest["artifacts"][name]
        if pin["path"] != name + ".npz":
            raise ValueError("unexpected M1/M2 artifact name")
        return loader(directory / pin["path"], expected_sha256=pin["sha256"],
                      expected_identity=pin["identity_sha256"])

    registration = read("source-registration", load_source_registration)
    forcing = read("spatial-forcing", load_spatial_forcing_package)
    product = read("product", load_diagnostic_product)
    comparison = read("routing-comparison", load_routing_comparison)
    product_pin = manifest["artifacts"]["product"]

    def read_output(path, **kwargs):
        return load_diagnostic_output(path, **kwargs,
                                      expected_product_identity=product_pin["identity_sha256"],
                                      expected_product_sha256=product_pin["sha256"])

    dense = read("output-dense", read_output)
    sparse = read("output-sparse", read_output)
    terrain, boundary = registration["terrain"], registration["boundary"]
    raw_path = Path(manifest["source_path"])
    if manifest["source_format"] == "td_1024":
        raw_source = load_large_td_source(raw_path, expected_sha256=manifest["source_sha256"])
    elif manifest["source_format"] == "pinned":
        raw_source = load_bundle(raw_path, expected_sha256=manifest["source_sha256"], validator=validate_source)
    else:
        raise ValueError("unsupported saved source format")
    raw_meta = raw_source["metadata"]
    if (terrain.source_id != raw_source["identity_sha256"]
            or terrain.source_sha256 != manifest["source_sha256"]
            or not np.array_equal(terrain.elevation_m, raw_source["arrays"]["height_m"])
            or not np.array_equal(terrain.valid_mask, raw_source["arrays"]["hydrology_mask"])
            or [terrain.x0_m, terrain.z0_m] != raw_meta["origin_m_xz"]
            or terrain.dx_m != raw_meta["spacing_m"] or terrain.dz_m != raw_meta["spacing_m"]):
        raise ValueError("registered source differs from pinned original terrain")
    del raw_source
    if product["metadata"]["terrain_identity_sha256"] != terrain.identity_sha256:
        raise ValueError("M1/M2 source/product linkage mismatch")
    if not np.array_equal(forcing["arrays"]["rain_mm_h"], product["arrays"]["rain_mm_h"]):
        raise ValueError("M1/M2 forcing/product linkage mismatch")
    if forcing["metadata"]["terrain_identity_sha256"] != terrain.identity_sha256:
        raise ValueError("M1/M2 spatial rainfall belongs to another source")
    pin = manifest["artifacts"]["product"]
    for sampled in (dense, sparse):
        if sampled["metadata"]["source_product_identity_sha256"] != pin["identity_sha256"]:
            raise ValueError("M1/M2 sampled output belongs to another product")
        _audit_output_against_product(sampled, product)
    graphs = decode_routing_comparison(comparison)
    reports = _routing_ledgers(graphs, product)
    if graphs["original_bed_d8"].identity_sha256 != product["metadata"]["routing_identity_sha256"]:
        raise ValueError("M1 comparison differs from M2 original-bed routing")
    saved = json.loads((directory / "acceptance.json").read_text(encoding="utf-8"))
    if file_sha256(directory / "acceptance.json") != manifest["acceptance_sha256"]:
        raise ValueError("M1/M2 acceptance report hash mismatch")
    if saved["routing_policies"] != reports or saved["sampling"] != _sampling_check(dense, sparse):
        raise ValueError("saved M1/M2 acceptance differs from cold audit")
    if saved["mass_balance_m3"] != product["metadata"]["water_budget_m3"]:
        raise ValueError("saved M2 budget differs from source product")
    if saved["priority_flood"] != comparison["metadata"]["flood"]:
        raise ValueError("saved flood report differs from working-surface evidence")
    if saved["historical_td_d4"] != _historical_d4(terrain):
        raise ValueError("saved historical D4 evidence differs")
    if _pins() != saved["frozen_sha256_before"] or saved["frozen_sha256_after"] != _pins():
        raise ValueError("frozen evidence changed")
    return saved


def prepare(output, *, source_path=PRIMARY_PATH, source_sha256=PRIMARY_SHA256, source_format="pinned"):
    output, source_path = Path(output).resolve(), Path(source_path).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name("." + output.name + ".partial-" + uuid.uuid4().hex)
    staging.mkdir()
    started = time.perf_counter()
    try:
        frozen = _pins()
        source_before = file_sha256(source_path)
        if source_format == "td_1024":
            source = load_large_td_source(source_path, expected_sha256=source_sha256)
        elif source_format == "pinned":
            source = load_bundle(source_path, expected_sha256=source_sha256, validator=validate_source)
        else:
            raise ValueError("source format must be pinned or td_1024")
        terrain, boundary, _, generation = _contracts(source, source_path, source_sha256)
        registration = register_source(terrain, boundary, source_metadata={
            "source_identity_sha256": source["identity_sha256"], "generation_metadata": generation,
            "seam_audit": generation.get("seam_audit", {})})
        pins = {"source-registration": _artifact(staging / "source-registration.npz", registration,
                                                  save_source_registration)}
        del source, registration
        recipe = SpatialRainRecipe(reference_origin_m_xz=(terrain.x0_m, terrain.z0_m),
                                   reference_spacing_m=terrain.dx_m,
                                   reference_shape_zx=terrain.valid_mask.shape)
        forcing, rain_package = build_spatial_forcing(
            terrain, np.array([0., 300., 600., 900.]), np.array([30., 0., 0.]), recipe)
        pins["spatial-forcing"] = _artifact(staging / "spatial-forcing.npz", rain_package,
                                            save_spatial_forcing_package)
        tile_audit = _tiles(terrain, boundary, forcing, recipe)
        rain_stats = {key: rain_package["metadata"][key] for key in
                      ("valid_multiplier_mean", "valid_multiplier_min", "valid_multiplier_max", "calibration")}
        del rain_package
        comparison_started = time.perf_counter()
        comparison = compare_routing_policies(terrain, boundary)
        pins["routing-comparison"] = _artifact(staging / "routing-comparison.npz", comparison,
                                                save_routing_comparison)
        comparison_seconds = time.perf_counter() - comparison_started
        del comparison
        gc.collect()
        product_started = time.perf_counter()
        product = build_diagnostic_product(terrain, boundary, forcing)
        pins["product"] = _artifact(staging / "product.npz", product, save_diagnostic_product)
        product_seconds = time.perf_counter() - product_started
        dense = sample_diagnostic_output(product, [0, 1, 2, 3], product_sha256=pins["product"]["sha256"])
        pins["output-dense"] = _artifact(staging / "output-dense.npz", dense, save_diagnostic_output)
        sparse = sample_diagnostic_output(product, [0, 3], product_sha256=pins["product"]["sha256"])
        pins["output-sparse"] = _artifact(staging / "output-sparse.npz", sparse, save_diagnostic_output)
        sampling = _sampling_check(dense, sparse)
        del dense, sparse
        comparison = load_routing_comparison(staging / "routing-comparison.npz",
                                              expected_sha256=pins["routing-comparison"]["sha256"],
                                              expected_identity=pins["routing-comparison"]["identity_sha256"])
        graphs = decode_routing_comparison(comparison)
        policy_reports = _routing_ledgers(graphs, product)
        if file_sha256(source_path) != source_before or source_before != source_sha256 or _pins() != frozen:
            raise ValueError("source or frozen algorithms changed during M1/M2 preparation")
        report = {"schema": SCHEMA, "status": "diagnostic_m1_m2",
                  "grid_shape_zx": list(terrain.valid_mask.shape),
                  "grid_area_m2": float(terrain.valid_mask.sum()) * terrain.cell_area_m2,
                  "source_sha256_before": source_before, "source_sha256_after": file_sha256(source_path),
                  "provenance_status": terrain.provenance_status, "crs": terrain.crs,
                  "rainfall": rain_stats, "tiles": tile_audit, "sampling": sampling,
                  "routing_policies": policy_reports,
                  "historical_td_d4": _historical_d4(terrain),
                  "priority_flood": comparison["metadata"]["flood"],
                  "mass_balance_m3": product["metadata"]["water_budget_m3"],
                  "frozen_sha256_before": frozen, "frozen_sha256_after": _pins(),
                  "timing_seconds": {"routing_comparison_and_save": comparison_seconds,
                                     "product_build_and_save": product_seconds,
                                     "pre_cold_audit": time.perf_counter() - started},
                  "resources": {"process_peak_working_set_bytes_before_cold_audit": int(
                      getattr(psutil.Process().memory_info(), "peak_wset", psutil.Process().memory_info().rss)),
                      "product_array_bytes": int(sum(value.nbytes for value in product["arrays"].values())),
                      "comparison_array_bytes": int(sum(value.nbytes for value in comparison["arrays"].values())),
                      "resource_semantics": "measured process peak separately from per-product allocation budget"},
                  "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
                  "limitations": ["priority-flood is a separate working surface; original bed unchanged",
                                  "adapted D4 does not replace the pinned historical TD D4 hierarchy",
                                  "closed candidates are contribution catchments, not wet lake surfaces",
                                  "instantaneous accumulation has no channel storage or travel time",
                                  "generated coordinates have unknown CRS; no observed DEM certification"]}
        _json_file(staging / "acceptance.json", report)
        manifest = {"schema": SCHEMA, "status": "diagnostic_m1_m2", "source_path": str(source_path),
                    "source_sha256": source_sha256, "source_format": source_format, "artifacts": pins,
                    "acceptance_sha256": file_sha256(staging / "acceptance.json"),
                    "cold_read_verified": False, "hydraulic_ready": False,
                    "natural_outlet_verified": False, "publishable": False}
        _json_file(staging / "manifest.json", manifest)
        del comparison, graphs, product, terrain, boundary, forcing
        gc.collect()
        audit_saved(staging)
        manifest["cold_read_verified"] = True
        _json_file(staging / "manifest.json", manifest)
        staging.rename(output)
        return {"status": "diagnostic_m1_m2", "output": str(output),
                "mass_balance_m3": report["mass_balance_m3"],
                "elapsed_seconds": time.perf_counter() - started}
    except Exception as error:
        shutil.rmtree(staging)
        staging.mkdir()
        _json_file(staging / "refusal.json", {"schema": SCHEMA, "status": "refused",
                                               "reason": str(error), "publishable": False})
        staging.rename(output)
        return {"status": "refused", "output": str(output), "reason": str(error)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-sha256")
    parser.add_argument("--source-format", choices=("pinned", "td_1024"), default="pinned")
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args(argv)
    if args.audit:
        print(json.dumps(audit_saved(args.audit), ensure_ascii=False, allow_nan=False))
        return 0
    if (args.source is None) != (args.source_sha256 is None):
        parser.error("--source and --source-sha256 must be supplied together")
    stamp = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    result = prepare(args.output or ROOT / "verification/td-river-milestones" / stamp,
                     source_path=args.source or PRIMARY_PATH, source_sha256=args.source_sha256 or PRIMARY_SHA256,
                     source_format=args.source_format)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "diagnostic_m1_m2" else 2


if __name__ == "__main__":
    raise SystemExit(main())
