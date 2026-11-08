"""Prepare a bounded v3 candidate from the fixed rejected 03 and original shard pins."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import traceback

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_FLAGS as FLAGS, TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES as MAX_BYTES, MAX_CELLS, TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_RSS as MAX_RSS, POLICY, POLICY_IDENTITY_SHA256, td_source_conforming_banks_mechanism_3_build_source_conforming_banks as build_source_conforming_banks, td_source_conforming_banks_mechanism_3_save_source_conforming_banks as save_source_conforming_banks
from tools.prepare_td_source_conforming_banks import (
    AUDIT_SHA as SHARDS_AUDIT_SHA, INDEX_SHA as SHARDS_INDEX_SHA,
    MANIFEST_SHA as SHARDS_MANIFEST_SHA, _observe, _pin, _read, _read_pin)

PARENT = ROOT / "verification/natural-river-network/source-conforming-banks-entry-20261006-03"
INDEX_SHA = "aac571e0a6f0b730e0ebd5c67db9ac9182f2f1398409754d33d9d66273fc277e"
AUDIT_SHA = "c410f1871d8b17cee5b48cb2ba141f3cce41b447daa042ddb8637abdc42041d9"
DIAGNOSIS_SHA = "b4db6be9440d251f03273e90dfa62c26c71871f5531ba3a33c10caf963c1e871"
CODE_FILES = ("terrain_pipeline/td_source_conforming_banks_v3.py",
              "tools/prepare_td_source_conforming_banks_v3.py",
              "tests/test_td_source_conforming_banks_v3.py")


def _frozen_inputs():
    index = _read(PARENT / "index.json", INDEX_SHA)
    audit = _read(PARENT / "independent-audit.json", AUDIT_SHA)
    diagnosis = _read(PARENT / "boundary-diagnosis.json", DIAGNOSIS_SHA)
    if (audit["status"] != "passed" or audit["index_sha256"] != INDEX_SHA
            or audit["manifest_sha256"] != index["manifest"]["sha256"]
            or diagnosis["index_sha256"] != INDEX_SHA
            or index["summary"]["candidate_components"] != 0
            or index["summary"]["refused_components"] != 14):
        raise ValueError("fixed rejected 03/audit/diagnosis linkage mismatch")
    for code_pins in (index["code_sha256"], audit["audit_code_sha256"]):
        for name, expected in code_pins.items():
            path = (ROOT / name).resolve(strict=True)
            if not path.is_relative_to(ROOT) or file_sha256(path) != expected:
                raise ValueError("frozen v2 implementation/audit changed: " + name)
    pins = dict(index["inputs"])
    pins.update(source_banks_v2_index=_pin(PARENT / "index.json"),
                source_banks_v2_independent_audit=_pin(PARENT / "independent-audit.json"),
                source_banks_v2_boundary_diagnosis=_pin(PARENT / "boundary-diagnosis.json"),
                source_banks_v2_manifest=index["manifest"],
                source_banks_v2_connection_queue=index["connection_queue"])
    for kind in ("raw", "proofs", "effects"):
        for number, pin in enumerate(index["chunks"][kind]):
            pins["source_banks_v2_" + kind + ":" + str(number)] = pin
    for name, pin in pins.items():
        path = Path(pin["path"]).resolve(strict=True)
        if (not path.is_relative_to(ROOT) or path.stat().st_size > MAX_BYTES
                or file_sha256(path) != pin["sha256"]):
            raise ValueError("immutable fixed input changed: " + name)
    if (pins["shards_index"]["sha256"] != SHARDS_INDEX_SHA
            or pins["shards_independent_audit"]["sha256"] != SHARDS_AUDIT_SHA
            or pins["shards_manifest"]["sha256"] != SHARDS_MANIFEST_SHA):
        raise ValueError("original shard01 hard pins mismatch")
    shard_index = _read_pin(pins["shards_index"])
    shard_audit = _read_pin(pins["shards_independent_audit"])
    if (shard_audit["status"] != "passed" or shard_audit["index_sha256"] != SHARDS_INDEX_SHA
            or shard_audit["manifest_sha256"] != SHARDS_MANIFEST_SHA
            or shard_index["manifest"] != pins["shards_manifest"]
            or shard_index["raw"] != pins["shards_raw"]
            or any(pin != pins["shard:" + str(number)] for number, pin in enumerate(shard_index["shards"]))):
        raise ValueError("original shard01 index/audit/raw/shards chain mismatch")
    return pins, shard_index, shard_audit


def _prepare(args, output, resource_check, resource, started):
    resource_check()
    pins, shard_index, shard_audit = _frozen_inputs()
    base = _read_pin(pins["base_raster"])
    manifest, raw = _read_pin(pins["shards_manifest"]), _read_pin(pins["shards_raw"])
    shards = [_read_pin(pin) for pin in shard_index["shards"]]
    if (raw["identity_sha256"] != manifest["raw_identity_sha256"]
            or [shard["identity_sha256"] for shard in shards] != manifest["shard_identities"]
            or shard_audit["material_ledger"] != manifest["material_ledger_merged"]):
        raise ValueError("frozen raw/shard material identity chain mismatch")
    sections, paths = _read_pin(pins["06_sections"]), _read_pin(pins["06_paths"])
    transitions = _read_pin(pins["09_transitions"])
    hierarchy_pin = pins["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]),
        expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    resource_check()
    package = build_source_conforming_banks(
        base, {"manifest": manifest, "raw": raw, "shards": shards}, hierarchy,
        sections, transitions, paths, shard_audit["readiness"], input_pins=pins,
        max_cells=args.max_cells, max_shard_bytes=args.max_shard_bytes, resource_check=resource_check)
    resource_check.phase = "save_v3_candidate"
    resource_check.counters = {}
    save_source_conforming_banks(package, output, resource_check=resource_check)
    resource_check()
    chunks = {kind: [_pin(output / kind / (chunk["chunk_id"] + ".json"), chunk)
                     for chunk in package[kind]] for kind in ("raw", "proofs", "effects")}
    result = {"schema": "td-source-conforming-banks-preparation-v3", "status": "candidate_only",
        "policy": POLICY, "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "inputs": pins, "parent_candidate_index_sha256": INDEX_SHA,
        "parent_candidate_audit_sha256": AUDIT_SHA,
        "manifest": _pin(output / "manifest.json", package["manifest"]), "chunks": chunks,
        "connection_queue": _pin(output / "connection-queue.json", package["queue"]),
        "summary": package["manifest"]["summary"],
        "material_ledger_parent": package["manifest"]["material_ledger_parent"],
        "material_ledger_delta": package["manifest"]["material_ledger_delta"],
        "resource": {"actual_peak_rss_bytes": resource["actual_peak_rss_bytes"], "max_rss_bytes": MAX_RSS,
            "phase_samples": resource["phase_samples"], "elapsed_s": time.perf_counter() - started,
            "water_solves": 0, "old_fine_center_source_resamples": 0, "new_lattice_cells": 0,
            "old_package_reaudited": False},
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES + (
            "terrain_pipeline/td_source_conforming_banks.py", "tools/prepare_td_source_conforming_banks.py",
            "terrain_pipeline/td_fine_bed_raster.py", "terrain_pipeline/td_fine_bed_shards.py",
            "terrain_pipeline/mountain_source_adapter.py", 'terrain_pipeline/basin_topology.py')},
        "old_mesh_passed": False, "independent_audit_passed": False,
        **{flag: False for flag in FLAGS}}
    payload = json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode("utf-8")
    if len(payload) > args.max_shard_bytes:
        raise MemoryError("new v3 preparation index exceeds bounded byte budget")
    resource_check()
    publish_bytes(output / "index.json", payload)
    print(json.dumps({"summary": result["summary"], "policy_identity_sha256": POLICY_IDENTITY_SHA256,
                      "material_ledger_delta": result["material_ledger_delta"]}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cells", type=int, default=MAX_CELLS)
    parser.add_argument("--max-shard-bytes", type=int, default=MAX_BYTES)
    args = parser.parse_args()
    output = args.output.resolve()
    parent = (ROOT / "verification/natural-river-network").resolve()
    if output.exists() or not output.is_relative_to(parent) or output == parent:
        raise ValueError("new verification output directory required")
    if not (1 <= args.max_cells <= MAX_CELLS and 4096 <= args.max_shard_bytes <= MAX_BYTES):
        raise ValueError("invalid v3 preparation resource budget")
    started = time.perf_counter()
    process = psutil.Process()
    resource = {"actual_peak_rss_bytes": 0, "last_rss_bytes": 0,
                "phase": "load_fixed_v2_inputs", "counters": {}, "phase_samples": {}}

    def resource_check():
        _observe(resource, process, getattr(resource_check, "phase", "load_fixed_v2_inputs"),
                 getattr(resource_check, "counters", {}))
        if resource["actual_peak_rss_bytes"] > MAX_RSS:
            raise MemoryError("hard 1GiB peak RSS exceeded")

    try:
        _prepare(args, output, resource_check, resource, started)
    except Exception as error:
        _observe(resource, process, resource["phase"], resource["counters"])
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        failure_path = output.parent / (output.name + "-failure-" + stamp + ".json")
        failure = {"schema": "td-source-conforming-banks-preparation-failure-v3",
            "status": "diagnostic_failure", "policy_identity_sha256": POLICY_IDENTITY_SHA256,
            "attempt_output": str(output), "exception": type(error).__name__ + ": " + str(error),
            "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__))[-6000:],
            "resource": resource, "max_rss_bytes": MAX_RSS,
            "elapsed_s": time.perf_counter() - started, "candidate_directory_exists": output.exists(),
            "published_candidate": False, "frozen_parent_index_sha256": INDEX_SHA,
            "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES},
            "water_solves": 0, **{flag: False for flag in FLAGS}}
        publish_bytes(failure_path, json.dumps(failure, sort_keys=True, allow_nan=False, indent=2).encode("utf-8"))
        raise


if __name__ == "__main__":
    main()
