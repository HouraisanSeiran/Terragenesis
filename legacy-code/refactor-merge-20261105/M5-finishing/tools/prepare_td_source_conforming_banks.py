"""Prepare a new, bounded source-conforming v2 candidate from frozen task10 pins."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_FLAGS as FLAGS, _i46_MAX_BYTES as MAX_BYTES, MAX_RSS, build_source_conforming_banks, save_source_conforming_banks

PARENT = ROOT / "verification/natural-river-network/fine-bed-shards-entry-20261005-01"
INDEX_SHA = "af3c777166218e8968c0083e0a8e32ad5a416f8d841f5c09ebcd4c8f544261f9"
AUDIT_SHA = "5ef4a0ae5a09244a148dd5bee4db96f28aa7c479eda97e33c835826ae3888ea7"
MANIFEST_SHA = "2ad6022687e0c696aff9bedb60b5a4910ba36ce3dcbd0c911d9ac8e3496d3c84"
PREVIOUS_FAILURE = ROOT / "verification/natural-river-network/source-conforming-banks-entry-20261006-01-failure.json"


def _read(path, expected_sha):
    path = path.resolve(strict=True)
    if (not path.is_relative_to(ROOT) or path.stat().st_size > MAX_BYTES
            or file_sha256(path) != expected_sha):
        raise ValueError("frozen JSON path/SHA/byte budget mismatch: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _read_pin(pin):
    record = _read(Path(pin["path"]), pin["sha256"])
    if "identity_sha256" in pin and record.get("identity_sha256") != pin["identity_sha256"]:
        raise ValueError("frozen parent identity mismatch")
    return record


def _pin(path, record=None):
    result = {"path": str(path.resolve()), "sha256": file_sha256(path), "bytes": path.stat().st_size}
    if record is not None and "identity_sha256" in record:
        result["identity_sha256"] = record["identity_sha256"]
    return result


def _observe(resource, process, phase, counters):
    memory = process.memory_info()
    resource["actual_peak_rss_bytes"] = max(resource["actual_peak_rss_bytes"], memory.rss, getattr(memory, "peak_wset", 0))
    resource["last_rss_bytes"] = memory.rss
    resource["phase"] = phase
    resource["counters"] = counters
    resource["phase_samples"][phase] = {"rss_bytes": memory.rss,
        "peak_rss_bytes": resource["actual_peak_rss_bytes"], "counters": counters}


def _failure_log(output, resource, started, error):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = output.parent / (output.name + "-failure-" + stamp + "-" + str(os.getpid()) + ".json")
    result = {"schema": "td-source-conforming-banks-preparation-failure-v2", "status": "diagnostic_failure",
              "attempt_output": str(output), "exception": type(error).__name__ + ": " + str(error),
              "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__))[-6000:],
              "resource": resource, "actual_peak_rss_bytes": resource["actual_peak_rss_bytes"],
              "max_rss_bytes": MAX_RSS, "elapsed_s": time.perf_counter() - started,
              "candidate_directory_exists": output.exists(), "published_candidate": False,
              "previous_failure": _pin(PREVIOUS_FAILURE) if PREVIOUS_FAILURE.exists() else None,
              "frozen_parent_index_sha256": INDEX_SHA, "water_solves": 0,
              "code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "terrain_pipeline/td_source_conforming_banks.py", "tools/prepare_td_source_conforming_banks.py",
                  "tests/test_td_source_conforming_banks.py")}, **{flag: False for flag in FLAGS}}
    publish_bytes(path, json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode("utf-8"))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cells", type=int, default=2_000_000)
    parser.add_argument("--max-shard-bytes", type=int, default=MAX_BYTES)
    args = parser.parse_args()
    output = args.output.resolve()
    parent = (ROOT / "verification/natural-river-network").resolve()
    if output.exists() or not output.is_relative_to(parent) or output == parent:
        raise ValueError("new verification output directory required")
    started = time.perf_counter()
    process = psutil.Process()
    resource = {"actual_peak_rss_bytes": 0, "last_rss_bytes": 0, "phase": "load_inputs", "counters": {}, "phase_samples": {}}

    def resource_check():
        _observe(resource, process, getattr(resource_check, "phase", "load_inputs"), getattr(resource_check, "counters", {}))
        if resource["actual_peak_rss_bytes"] > MAX_RSS:
            raise MemoryError("hard 1GiB peak RSS exceeded")

    try:
        _prepare(args, output, resource_check, resource, started)
    except Exception as error:
        _observe(resource, process, resource["phase"], resource["counters"])
        try:
            failure = _failure_log(output, resource, started, error)
            print("Failure diagnostics: " + str(failure), file=sys.stderr)
        except Exception as log_error:
            print("Failure diagnostics unavailable: " + str(log_error), file=sys.stderr)
        raise


def _prepare(args, output, resource_check, resource, started):
    resource_check()
    index = _read(PARENT / "index.json", INDEX_SHA)
    audit = _read(PARENT / "independent-audit.json", AUDIT_SHA)
    if (audit["status"] != "passed" or audit["index_sha256"] != INDEX_SHA
            or audit["manifest_sha256"] != MANIFEST_SHA or index["manifest"]["sha256"] != MANIFEST_SHA):
        raise ValueError("frozen shards01 independent audit binding mismatch")
    pins = {**index["inputs"], "shards_index": _pin(PARENT / "index.json"),
            "shards_independent_audit": _pin(PARENT / "independent-audit.json"),
            "shards_manifest": index["manifest"], "shards_raw": index["raw"],
            **{"shard:" + str(number): pin for number, pin in enumerate(index["shards"])}}
    for name, pin in pins.items():
        path = Path(pin["path"]).resolve(strict=True)
        if not path.is_relative_to(ROOT) or file_sha256(path) != pin["sha256"]:
            raise ValueError("immutable input changed: " + name)
    base = _read_pin(pins["base_raster"])
    manifest, raw = _read_pin(index["manifest"]), _read_pin(index["raw"])
    shards = [_read_pin(pin) for pin in index["shards"]]
    if (raw["identity_sha256"] != manifest["raw_identity_sha256"]
            or [item["identity_sha256"] for item in shards] != manifest["shard_identities"]
            or audit["material_ledger"] != manifest["material_ledger_merged"]):
        raise ValueError("saved shard raw/material/transaction identity chain mismatch")
    sections = _read_pin(pins["06_sections"])
    transitions = _read_pin(pins["09_transitions"])
    paths = _read_pin(pins["06_paths"])
    hierarchy_pin = pins["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]),
        expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    resource_check()
    package = build_source_conforming_banks(base, {"manifest": manifest, "raw": raw, "shards": shards},
        hierarchy, sections, transitions, paths, audit["readiness"], input_pins=pins,
        max_cells=args.max_cells, max_shard_bytes=args.max_shard_bytes, resource_check=resource_check)
    resource_check.phase = "save_candidate"
    resource_check.counters = {}
    save_source_conforming_banks(package, output, resource_check=resource_check)
    resource_check()
    chunks = {kind: [_pin(output / kind / (chunk["chunk_id"] + ".json"), chunk)
                     for chunk in package[kind]] for kind in ("raw", "proofs", "effects")}
    result = {"schema": "td-source-conforming-banks-preparation-v2", "status": "candidate_only",
              "inputs": pins, "manifest": _pin(output / "manifest.json", package["manifest"]),
              "chunks": chunks, "connection_queue": _pin(output / "connection-queue.json", package["queue"]),
              "summary": package["manifest"]["summary"],
              "material_ledger_parent": package["manifest"]["material_ledger_parent"],
              "material_ledger_delta": package["manifest"]["material_ledger_delta"],
              "resource": {"actual_peak_rss_bytes": resource["actual_peak_rss_bytes"], "max_rss_bytes": MAX_RSS,
                           "phase_samples": resource["phase_samples"],
                           "elapsed_s": time.perf_counter() - started, "water_solves": 0,
                           "old_fine_center_source_resamples": 0, "new_lattice_cells": 0,
                           "old_package_reaudited": False},
              "previous_failure": _pin(PREVIOUS_FAILURE) if PREVIOUS_FAILURE.exists() else None,
              "code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "terrain_pipeline/td_source_conforming_banks.py", "tools/prepare_td_source_conforming_banks.py",
                  "terrain_pipeline/td_fine_bed_raster.py", "terrain_pipeline/td_fine_bed_shards.py",
                  "terrain_pipeline/mountain_source_adapter.py", 'terrain_pipeline/basin_topology.py')},
              "old_mesh_passed": False, "full_watershed_fine_verified": False,
              "independent_audit_passed": False, **{flag: False for flag in FLAGS}}
    payload = json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode("utf-8")
    if len(payload) > args.max_shard_bytes:
        raise MemoryError("new preparation index exceeds bounded byte budget")
    resource_check()
    publish_bytes(output / "index.json", payload)
    print(json.dumps({"summary": result["summary"], "material_ledger_delta": result["material_ledger_delta"]}, sort_keys=True))


if __name__ == "__main__":
    main()
