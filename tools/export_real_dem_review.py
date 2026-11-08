"""Read-only review adapter for the fixed raw/flat/rainfall evidence chain."""

import argparse
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_source import load_dem_candidate
from tools import verify_real_dem_rainfall_routing as rainfall_exporter
from tools.verify_real_dem_outlet_classification import (
    DEFAULT_CANDIDATE, canonical_bytes, check_unchanged, confined_file, file_sha256,
    read_json, source_record,
)

DEFAULT_OUTPUT = ROOT / "verification/real-dem-review"
THRESHOLD = 100
MAX_JSON_BYTES = 128 * 1024 * 1024


def layers(candidate, raw, flat, flat_report):
    height = candidate["arrays"]["height_m"]
    valid = candidate["arrays"]["valid_mask"]
    return {"schema": "real-dem-static-review-v1", "shape_zx": list(height.shape),
            "grid": candidate["manifest"]["identity"]["grid"],
            "height_m": np.where(valid, height, None).tolist(),
            "valid_mask": valid.tolist(), "unknown_mask": (~valid).tolist(),
            "raw_receiver_global_id": raw["receiver"].tolist(),
            "raw_accumulation_cells": raw["accumulation_cells"].tolist(),
            "flat_receiver_global_id": flat["receiver"].tolist(),
            "flat_accumulation_cells": flat["accumulation_cells"].tolist(),
            "flat_component_id": flat["component_id"].tolist(),
            "flat_distance_to_exit_edges": flat["distance_to_exit"].tolist(),
            "terminals": flat_report["terminals"],
            "unknown_semantics": "null heights are missing evidence, not ocean; no triangles across missing cells",
            "raw_flat_difference": "exact_equal_height_irregular_graph_connectivity_only_no_filling_or_carving",
            "natural_outlet_verified": False, "ocean_outlet_certified": False}


def dynamic_review(result, flat):
    global_ids = result["valid_cell_ids"]
    selected = flat["accumulation_cells"].ravel()[global_ids] >= THRESHOLD
    chosen = global_ids[selected]
    storage = result["channel_storage"]
    local = result["local_volume"]
    dt_s = result["metadata"]["dt_s"]
    return {"schema": "real-dem-saved-dynamic-review-v1", "metadata": result["metadata"],
            "summary": result["summary"], "selected_global_cell_ids": chosen.tolist(),
            "selection": {"min_contributing_cells": THRESHOLD,
                          "selected_cells": len(chosen), "omitted_valid_cells": int((~selected).sum())},
            "time_state_s": (np.arange(storage.shape[0]) * dt_s).tolist(),
            "time_interval_start_s": (np.arange(local.shape[0]) * dt_s).tolist(),
            "rain_mm_h": result["rain_mm_h"].tolist(),
            "selected_storage_m3": storage[:, selected].tolist(),
            "selected_local_runoff_q_m3_s": (local[:, selected] / dt_s).tolist(),
            "omitted_storage_m3": storage[:, ~selected].sum(axis=1).tolist(),
            "omitted_local_runoff_m3": local[:, ~selected].sum(axis=1).tolist(),
            "whole_domain_storage_m3": storage.sum(axis=1).tolist(),
            "ledger": {key: value.tolist() for key, value in result["ledger"].items()},
            "storage_semantics": "conceptual linear reservoir volume; no solved channel water stage or surface",
            "q_semantics": "local rainfall runoff only, NOT accumulated river discharge or edge flux",
            "time_semantics": "storage[k] at state time; local_q[k] average over interval k; T+1 states, T intervals",
            "model": "one_way_delayed_linear_storage_not_backwater",
            "natural_outlet_verified": False, "ocean_outlet_certified": False}


def source_inputs(rainfall_path):
    directory = Path(rainfall_path).resolve(strict=True)
    report = rainfall_exporter.verify_package(directory)
    manifest = read_json(directory / "manifest.json")
    inputs = list(manifest["inputs"].values()) + manifest["source_files"]
    inputs += [source_record(directory / name) for name in
               ("manifest.json", "report.json") + tuple(name + ".npz" for name in rainfall_exporter.SCENARIOS)]
    inputs += [source_record(__file__)]
    unique = {item["path"]: item for item in inputs}
    candidate = load_dem_candidate(DEFAULT_CANDIDATE, verify_source=True)
    flat_report = read_json(rainfall_exporter.DEFAULT_FLAT / "report.json")
    with np.load(rainfall_exporter.DEFAULT_FLAT / "network.npz", allow_pickle=False) as archive:
        flat = {name: archive[name] for name in archive.files}
    with np.load(rainfall_exporter.DEFAULT_STAGE_B / "network.npz", allow_pickle=False) as archive:
        raw = {name: archive[name] for name in archive.files}
    return directory, report, candidate, flat_report, flat, raw, list(unique.values())


def write_json(path, value):
    payload = canonical_bytes(value)
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("review JSON exceeds byte budget")
    path.write_bytes(payload)


def check_output(output, inputs):
    workspace = ROOT.resolve()
    verification = (workspace / "verification").resolve()
    output = Path(output).resolve()
    if (not verification.is_relative_to(workspace) or output != (verification / "real-dem-review").resolve()
            or any(Path(item["path"]).resolve().is_relative_to(output) for item in inputs)):
        raise ValueError("review output must be separate workspace/verification/real-dem-review")
    return output


def identity():
    return {"exporter_sha256": file_sha256(__file__),
            "rainfall_exporter_sha256": file_sha256(rainfall_exporter.__file__),
            "rainfall_core_sha256": file_sha256(importlib.import_module('terrain_pipeline.runoff').__file__)}


def make_manifest(directory, inputs):
    names = ["static-layers.json"] + [name + ".json" for name in rainfall_exporter.SCENARIOS]
    return {"schema": "real-dem-review-package-v1", "inputs": inputs, "algorithm": identity(),
            "selection_min_contributing_cells": THRESHOLD,
            "artifacts": {name: {"path": name, "sha256": file_sha256(directory / name),
                                  "bytes": (directory / name).stat().st_size} for name in names},
            "readonly": True, "source_unchanged": True, "viewer_integration": "new_adapter_not_installed_in_Sonnet_frontend",
            "no_inference_no_routing_no_dynamic_advancement": True,
            "water_surface_available": False, "natural_outlet_verified": False, "ocean_outlet_certified": False}


def export_package(rainfall_path, *, output_root=DEFAULT_OUTPUT):
    check_output(output_root, [])
    directory, report, candidate, flat_report, flat, raw, inputs = source_inputs(rainfall_path)
    output = check_output(output_root, inputs)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=output) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        write_json(staging / "static-layers.json", layers(candidate, raw, flat, flat_report))
        for name in rainfall_exporter.SCENARIOS:
            result = rainfall_exporter.load_saved(directory / (name + ".npz"), report["scenarios"][name],
                                                   int(candidate["arrays"]["valid_mask"].sum()))
            write_json(staging / (name + ".json"), dynamic_review(result, flat))
            del result
        write_json(staging / "manifest.json", make_manifest(staging, inputs))
        check_unchanged(inputs)
        if destination.exists():
            raise FileExistsError(destination)
        staging.rename(destination)
    return destination


def verify_package(package, rainfall_path):
    package = Path(package).resolve(strict=True)
    directory, report, candidate, flat_report, flat, raw, inputs = source_inputs(rainfall_path)
    names = {"manifest.json", "static-layers.json"} | {name + ".json" for name in rainfall_exporter.SCENARIOS}
    if {item.name for item in package.iterdir()} != names:
        raise ValueError("unexpected review members")
    for name in names:
        if confined_file(package, name).stat().st_size > MAX_JSON_BYTES:
            raise ValueError("review JSON budget exceeded")
    manifest = read_json(package / "manifest.json")
    if canonical_bytes(read_json(package / "static-layers.json")) != canonical_bytes(layers(candidate, raw, flat, flat_report)):
        raise ValueError("static review does not replay saved evidence")
    for name in rainfall_exporter.SCENARIOS:
        result = rainfall_exporter.load_saved(directory / (name + ".npz"), report["scenarios"][name],
                                               int(candidate["arrays"]["valid_mask"].sum()))
        if canonical_bytes(read_json(package / (name + ".json"))) != canonical_bytes(dynamic_review(result, flat)):
            raise ValueError("dynamic review saved-value/omission/time semantics mismatch")
        del result
    if canonical_bytes(manifest) != canonical_bytes(make_manifest(package, inputs)):
        raise ValueError("review manifest source/algorithm/hash mismatch")
    check_unchanged(inputs)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rainfall-package", type=Path, required=True)
    parser.add_argument("--verify-package", type=Path)
    args = parser.parse_args()
    if args.verify_package is None:
        output = export_package(args.rainfall_package)
    else:
        verify_package(args.verify_package, args.rainfall_package)
        output = args.verify_package
    print(str(output))


if __name__ == "__main__":
    main()
