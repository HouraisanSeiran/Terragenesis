"""Prepare one explicit real hub candidate or refusal from immutable 06/source-bank pins."""

import argparse
import json
from pathlib import Path
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_ported_junction import (
    FLAGS, MAX_BYTES, MAX_RSS, POLICY_IDENTITY_SHA256, build_ported_junction, save_ported_junction)

VERIFICATION = ROOT / "verification/natural-river-network"
INPUTS = {
    "06_index": {"path": str(VERIFICATION / "watershed-geometry-20261005-01/index.json"),
        "sha256": "fec57d5c9df599ba3c419d2283910d27afe172c236743b3536769bf579af662b"},
    "06_paths": {"path": str(VERIFICATION / "watershed-geometry-20261005-01/paths.json"),
        "sha256": "4db1e25e6b0d1f7ed5443e10a6eaabb467ac95e4669ea57f88d8e7f1bac2fd1b"},
    "06_sections": {"path": str(VERIFICATION / "watershed-geometry-20261005-01/sections.json"),
        "sha256": "0d867183f2dc404c56959912bb4edacc559215d50c2075ac6769277e54ba8935"},
    "hierarchy": {"path": str(ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"),
        "sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
        "identity_sha256": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"},
    "source_bank_parent_index": {"path": str(VERIFICATION / "source-conforming-banks-entry-20261006-03/index.json"),
        "sha256": "aac571e0a6f0b730e0ebd5c67db9ac9182f2f1398409754d33d9d66273fc277e"},
    "source_bank_parent_audit": {"path": str(VERIFICATION / "source-conforming-banks-entry-20261006-03/independent-audit.json"),
        "sha256": "c410f1871d8b17cee5b48cb2ba141f3cce41b447daa042ddb8637abdc42041d9"},
    "wet_protection_manifest": {"path": str(VERIFICATION / "source-conforming-banks-entry-20261006-03/manifest.json"),
        "sha256": "b1e901474ecefc3674ffcdc3fc949d03662910cb4bf7e3b4949c35ea341b3651"},
}
FROZEN_HELPERS = {
    "terrain_pipeline/td_source_conforming_banks.py": "b0978a4fc4d16a1d80fddc1a2d6f4274e59edddfaa7f40de52ee0410fb424353",
    "terrain_pipeline/td_source_conforming_banks_v3.py": "075947dac928bc95c16b5bc95b7c5414d6e22cd8fae7a6c0b8ec3f88d24db29c",
    "terrain_pipeline/td_fine_bed_raster.py": "b46950b02aeb8524b58b3985353f480bf25b8d7167ef3492005c852d6f08a293",
    "terrain_pipeline/mountain_source_adapter.py": "796e763097d4b49ca74dcffc052afdd5f1fc5ad03cbdeb26f4cadc57b5cc3c85",
    "terrain_pipeline/td_basin_hierarchy.py": "e618ac7177e34a877efa9ef50abaa5002e6669e152a090cb82917061507dc895",
}
CODE_FILES = ("terrain_pipeline/td_ported_junction.py", "tools/prepare_td_ported_junction.py",
              "tests/test_td_ported_junction.py")


def _read(pin):
    path = Path(pin["path"]).resolve(strict=True)
    if (not path.is_relative_to(ROOT) or path.stat().st_size > MAX_BYTES or file_sha256(path) != pin["sha256"]):
        raise ValueError("immutable input path/size/SHA mismatch: " + str(path))
    return json.loads(path.read_bytes())


def _pin(path, record=None):
    pin = {"path": str(path.resolve()), "sha256": file_sha256(path), "bytes": path.stat().st_size}
    if record is not None:
        pin["identity_sha256"] = record["identity_sha256"]
    return pin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hub-node-id", default="cell:62896")
    parser.add_argument("--arc-id", action="append")
    parser.add_argument("--inset-m", type=float)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or output == VERIFICATION.resolve() or not output.is_relative_to(VERIFICATION.resolve()):
        raise ValueError("new verification output directory required")
    started = time.perf_counter()
    for name, expected in FROZEN_HELPERS.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("frozen readonly helper changed: " + name)
    paths, sections = _read(INPUTS["06_paths"]), _read(INPUTS["06_sections"])
    geometry_index = _read(INPUTS["06_index"])
    if (geometry_index["paths"]["sha256"] != INPUTS["06_paths"]["sha256"]
            or geometry_index["sections"]["sha256"] != INPUTS["06_sections"]["sha256"]):
        raise ValueError("fixed 06 index/path/section pin mismatch")
    source_index = _read(INPUTS["source_bank_parent_index"])
    source_audit = _read(INPUTS["source_bank_parent_audit"])
    wet_manifest = _read(INPUTS["wet_protection_manifest"])
    if (source_audit["status"] != "passed"
            or source_audit["index_sha256"] != INPUTS["source_bank_parent_index"]["sha256"]
            or source_audit["manifest_sha256"] != INPUTS["wet_protection_manifest"]["sha256"]
            or source_index["manifest"]["sha256"] != INPUTS["wet_protection_manifest"]["sha256"]
            or wet_manifest["sections_identity_sha256"] != sections["identity_sha256"]
            or wet_manifest["paths_identity_sha256"] != paths["identity_sha256"]):
        raise ValueError("saved wet-protection/source audit linkage mismatch")
    hierarchy_pin = INPUTS["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]),
        expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    if wet_manifest["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("wet-protection hierarchy identity mismatch")
    record = build_ported_junction(hierarchy, paths, sections, hub_node_id=args.hub_node_id,
        incident_arc_ids=args.arc_id, wet_protection=wet_manifest["wet_protection"],
        input_pins=INPUTS, inset_m=args.inset_m)
    save_ported_junction(record, output)
    memory = psutil.Process().memory_info()
    peak_rss = max(memory.rss, getattr(memory, "peak_wset", 0))
    if peak_rss > MAX_RSS:
        raise MemoryError("ported junction peak 1GiB budget exceeded")
    index = {"schema": "td-ported-junction-preparation-v1", "status": record["status"],
        "policy_identity_sha256": POLICY_IDENTITY_SHA256, "hub_node_id": args.hub_node_id,
        "inputs": INPUTS, "junction": _pin(output / "junction.json", record),
        "requested_replacement_arc_ids": record["requested_replacement_arc_ids"],
        "rejection_reasons": record["rejection_reasons"],
        "internal_three_arm_geometry_candidate": record["internal_three_arm_geometry_candidate"],
        "actual_external_attachment_count": record["actual_external_attachment_count"],
        "external_closure_verified": record["external_closure_verified"], "full_network_verified": False,
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES + tuple(FROZEN_HELPERS)},
        "resource": {"actual_peak_rss_bytes": peak_rss, "max_rss_bytes": MAX_RSS,
            "elapsed_s": time.perf_counter() - started, "solver_calls": 0, "fine_cells_generated": 0,
            "old_packages_modified": False, "max_json_bytes": MAX_BYTES},
        "independent_audit_passed": False, **{flag: False for flag in FLAGS}}
    payload = json.dumps(index, sort_keys=True, allow_nan=False, indent=2).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise MemoryError("ported junction index exceeds 64MiB")
    publish_bytes(output / "index.json", payload)
    print(json.dumps({key: index[key] for key in ("status", "hub_node_id",
        "internal_three_arm_geometry_candidate", "actual_external_attachment_count", "external_closure_verified",
        "rejection_reasons")}, sort_keys=True))


if __name__ == "__main__":
    main()
