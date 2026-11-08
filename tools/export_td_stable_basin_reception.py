"""Export audited Radau saved-face reception without advancing a solver."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import load_overflow_topology as load_overflow_topology
from terrain_pipeline.basin_storage import load_radau_overflow as load_radau_overflow
from terrain_pipeline.basin_topology import build_basin_reception as build_basin_reception
from terrain_pipeline.basin_topology import validate_basin_reception as validate_basin_reception


MAX_OUTPUT_BYTES = 128 * 1024**2


def load_export(directory, *, expected_index_sha256):
    directory = Path(directory).resolve(strict=True)
    manifest_path = directory / "index.json"
    if file_sha256(manifest_path) != expected_index_sha256:
        raise ValueError("export index SHA mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pin = manifest["reception"]
    path = directory / pin["path"]
    if (manifest.get("schema") != "td-stable-basin-reception-index-v1" or
            pin["path"] != "reception.json" or path.stat().st_size != pin["bytes"] or
            pin["bytes"] >= MAX_OUTPUT_BYTES or file_sha256(path) != pin["sha256"]):
        raise ValueError("export reception pin/budget mismatch")
    report = json.loads(path.read_text(encoding="utf-8"),
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite export JSON")))
    if (report.get("schema") != "td-stable-basin-reception-export-v1" or
            report["parent_index"]["sha256"] != manifest["parent_index_sha256"] or
            report["independent_audit"]["sha256"] != manifest["independent_audit_sha256"] or
            report["independent_audit"]["status"] != "passed"):
        raise ValueError("export parent/audit binding mismatch")
    for container in (manifest, report):
        if any(container.get(flag) is not False for flag in
               ("publishable", "natural_outlet_verified", "hydraulic_ready", "continuous_fine_corridor_ready")):
            raise ValueError("export claims unsupported certification")
    if {case["name"] for case in report["cases"]} != set(manifest["event_identity_sha256"]):
        raise ValueError("export case coverage mismatch")
    for case in report["cases"]:
        reception = case["reception"]
        validate_basin_reception(reception, expected_identity=reception["identity_sha256"])
        if (reception["event_identity_sha256"] != manifest["event_identity_sha256"][case["name"]] or
                reception["event_identity_sha256"] != case["selected_event"]["identity_sha256"] or
                reception["reference_event_identity_sha256"] != case["reference_event"]["identity_sha256"]):
            raise ValueError("export event identity binding mismatch")
    return report


def _pinned_path(pin, base):
    path = Path(pin["path"])
    return (path if path.is_absolute() else base / path).resolve(strict=True)


def _load_json(path, expected_sha256):
    if file_sha256(path) != expected_sha256:
        raise ValueError(f"external SHA mismatch: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run(directory, expected_index_sha256, expected_audit_sha256, output):
    directory = Path(directory).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    index_path = directory / "index.json"
    index = _load_json(index_path, expected_index_sha256)
    audit = _load_json(directory / "independent-audit.json", expected_audit_sha256)
    if (index.get("schema") != "td-radau-overflow-refinement-v1" or
            index.get("status") != "ready_for_independent_audit" or
            audit.get("schema") != "td-radau-overflow-independent-audit-v1" or
            audit.get("status") != "passed" or audit.get("index_sha256") != expected_index_sha256 or
            audit.get("cold_read") is not True or audit.get("solver_advanced") is not False):
        raise ValueError("passed independent audit bound to parent index required")
    if {case["name"] for case in audit["cases"]} != {case["name"] for case in index["cases"]}:
        raise ValueError("audit case coverage mismatch")
    parent_pin = index["parent_index"]
    parent_path = _pinned_path(parent_pin, directory)
    parent = _load_json(parent_path, parent_pin["sha256"])
    if parent.get("input_pins") != index["input_pins"] or parent.get("topology") != index["topology"]:
        raise ValueError("refinement source pins differ from parent")
    for pin in index["input_pins"].values():
        if file_sha256(_pinned_path(pin, parent_path.parent)) != pin["sha256"]:
            raise ValueError("source input pin mismatch")
    hierarchy_pin = index["input_pins"]["hierarchy"]
    hierarchy = load_basin_hierarchy(_pinned_path(hierarchy_pin, parent_path.parent),
                                      expected_sha256=hierarchy_pin["sha256"],
                                      expected_identity=hierarchy_pin["identity_sha256"])
    topology_pin = index["topology"]
    topology = load_overflow_topology(_pinned_path(topology_pin, parent_path.parent),
                                      expected_sha256=topology_pin["sha256"],
                                      expected_identity=topology_pin["identity_sha256"])
    cases = []
    for case in index["cases"]:
        audited = next(item for item in audit["cases"] if item["name"] == case["name"])
        if (case["temporal_refinement_passed"] is not True or
                audited["temporal_refinement_passed"] is not True or
                audited["selected_level"] != case["selected_level"] or
                case["selected_level"] != case["levels"][-1]["level"] or
                len(case["levels"]) < 2):
            raise ValueError("selected event lacks accepted audited refinement")
        selected_pin = case["levels"][-1]["event"]
        previous_pin = case["levels"][-2]["event"]
        for pin in (selected_pin, previous_pin):
            path = _pinned_path(pin, directory)
            if path.parent != directory or path.stat().st_size != pin["bytes"]:
                raise ValueError("event pin directory/size mismatch")
        if (audited["levels"][-1]["identity_sha256"] != selected_pin["identity_sha256"] or
                audited["levels"][-2]["identity_sha256"] != previous_pin["identity_sha256"] or
                audited["levels"][-1]["level"] != case["levels"][-1]["level"] or
                audited["levels"][-2]["level"] != case["levels"][-2]["level"]):
            raise ValueError("audited event identity/level mismatch")
        event = load_radau_overflow(_pinned_path(selected_pin, directory),
                                     expected_sha256=selected_pin["sha256"],
                                     expected_identity=selected_pin["identity_sha256"], topology=topology)
        reference = load_radau_overflow(_pinned_path(previous_pin, directory),
                                         expected_sha256=previous_pin["sha256"],
                                         expected_identity=previous_pin["identity_sha256"], topology=topology)
        reception = build_basin_reception(topology, event, reference, hierarchy)
        cases.append({"name": case["name"], "selected_level": case["selected_level"],
                      "selected_event": selected_pin, "reference_event": previous_pin,
                      "reception": reception})
    if file_sha256(index_path) != expected_index_sha256 or file_sha256(directory / "independent-audit.json") != expected_audit_sha256:
        raise ValueError("parent index/audit changed during export")
    report = {"schema": "td-stable-basin-reception-export-v1", "status": "diagnostic_only",
              "parent_index": {"path": str(index_path), "sha256": expected_index_sha256},
              "independent_audit": {"path": str(directory / "independent-audit.json"),
                                    "sha256": expected_audit_sha256, "status": "passed"},
              "topology": topology_pin, "hierarchy": hierarchy_pin, "cases": cases,
              "summary": {"saved_interval_switch_semantics": "sign switches count only active saved intervals; subinterval reversals are unresolved",
                          "late_interval_semantics": "last 20% of each event, not a permanent trunk",
                          "geometry_semantics": "lowest original-bed D4 saddle face and XYZ endpoints, not a river cross-section or center-to-center corridor",
                          "certification": "neither controlled tailwater nor complete hydraulics independently certified"},
              "publishable": False, "natural_outlet_verified": False, "hydraulic_ready": False,
              "continuous_fine_corridor_ready": False}
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) >= MAX_OUTPUT_BYTES:
        raise MemoryError("reception JSON exceeds 128 MiB output budget")
    output.mkdir(parents=True)
    publish_bytes(output / "reception.json", payload)
    manifest = {"schema": "td-stable-basin-reception-index-v1", "reception": {
        "path": "reception.json", "sha256": file_sha256(output / "reception.json"),
        "bytes": len(payload)}, "parent_index_sha256": expected_index_sha256,
        "independent_audit_sha256": expected_audit_sha256,
        "event_identity_sha256": {case["name"]: case["selected_event"]["identity_sha256"] for case in cases},
        "publishable": False, "natural_outlet_verified": False, "hydraulic_ready": False,
        "continuous_fine_corridor_ready": False}
    publish_bytes(output / "index.json", json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-index-sha256", required=True)
    parser.add_argument("--expected-audit-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.directory, args.expected_index_sha256,
                         args.expected_audit_sha256, args.output), ensure_ascii=False))
