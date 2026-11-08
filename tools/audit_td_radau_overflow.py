"""Independent cold-read audit of pinned full-event Radau refinement."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import OverflowParameters as OverflowParameters
from terrain_pipeline.basin_storage import load_overflow_topology as load_overflow_topology
from terrain_pipeline.basin_storage import load_radau_overflow as load_radau_overflow
from tools.audit_td_original_bed_overflow import audit_saved_arrays


ALGORITHM = "radau-conservative-original-bed-basin-face-exchange-v5"
EVENTS = {"normal-24h": (30., 86400), "strong-6h": (120., 21600)}
STAGE_LIMIT_M = .001
RELATIVE_LIMIT = .01


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _pin_path(pin, directory):
    path = Path(pin["path"])
    if not path.is_absolute():
        path = directory / path
    return path.resolve(strict=True)


def _same_pin(first, second):
    return all(first[key] == second[key] for key in ("sha256", "identity_sha256", "path"))


def _audit_event(topology, event, name, duration, rain_rate):
    arrays, metadata = event["arrays"], event["metadata"]
    steps = duration // 300
    _require(metadata["algorithm"] == ALGORITHM and metadata["steps"] == steps
             and metadata["duration_s"] == duration and metadata["timestep_s"] == 300.,
             f"{name}: incomplete event or invalid saved times")
    _require(arrays["rain_mm_h"].shape == (steps,)
             and np.array_equal(arrays["rain_mm_h"], np.full(steps, rain_rate))
             and arrays["volume_m3"].shape[0] == steps + 1,
             f"{name}: incomplete rainfall or saved states")
    _require(np.count_nonzero(arrays["volume_m3"][0]) == 0,
             f"{name}: expected zero initial basin inventories")
    _require(metadata["parameters"] == asdict(OverflowParameters(timestep_s=300., duration_s=duration)),
             f"{name}: reservoir model parameters changed")
    _require(metadata["topology_identity_sha256"] == topology["identity_sha256"]
             and metadata["hierarchy_identity_sha256"] == topology["metadata"]["hierarchy_identity_sha256"]
             and metadata["source_identity_sha256"] == topology["metadata"]["source_identity_sha256"],
             f"{name}: event provenance mismatch")
    _require(all(metadata.get(key) is False for key in
                 ("hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable")),
             f"{name}: event claims unsupported certification")
    work = metadata["work"]
    _require(np.isfinite(work["maximum_scaled_collocation_defect"])
             and 0 <= work["maximum_scaled_collocation_defect"] <= .05
             and np.isfinite(work["maximum_inventory_correction_m3"])
             and work["maximum_inventory_correction_m3"] >= 0
             and np.isfinite(work["minimum_inventory_m3"])
             and work["minimum_inventory_m3"] >= -1e-8,
             f"{name}: collocation defect, correction or inventory failed")
    for key in ("face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3"):
        _require(np.isfinite(arrays[key]).all() and np.all(arrays[key] >= 0.),
                 f"{name}: negative directional exchange in {key}")
    _require(np.isfinite(arrays["volume_m3"]).all() and np.all(arrays["volume_m3"] >= 0.),
             f"{name}: negative inventory")
    _require(np.allclose(arrays["face_net_m3"], arrays["face_forward_m3"] - arrays["face_reverse_m3"],
                         rtol=0, atol=1e-9), f"{name}: face divergence mismatch")
    return audit_saved_arrays(topology, event)


def _compare(coarse, fine):
    first, second = coarse["arrays"], fine["arrays"]
    _require(coarse["metadata"]["parameters"] == fine["metadata"]["parameters"]
             and np.array_equal(first["rain_mm_h"], second["rain_mm_h"])
             and np.array_equal(first["volume_m3"][0], second["volume_m3"][0]),
             "refinement physics, rain or initial inventory changed")
    stage_error = float(np.max(np.abs(first["stage_m"] - second["stage_m"])))
    coarse_net = np.cumsum(first["face_forward_m3"] - first["face_reverse_m3"], axis=0)
    fine_net = np.cumsum(second["face_forward_m3"] - second["face_reverse_m3"], axis=0)
    numerator = np.abs(coarse_net - fine_net).sum(axis=1)
    denominator = np.abs(fine_net).sum(axis=1)
    relative = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0.)
    relative[(denominator == 0.) & (numerator > 1e-9)] = 1e300
    flux_error = float(np.max(relative))
    directional_first = np.concatenate((first["face_forward_m3"].sum(axis=0), first["face_reverse_m3"].sum(axis=0)))
    directional_second = np.concatenate((second["face_forward_m3"].sum(axis=0), second["face_reverse_m3"].sum(axis=0)))
    directional_error = float(np.abs(directional_first - directional_second).sum()
                              / max(float(directional_second.sum()), 1e-30))
    inventory_error = float(np.abs(first["volume_m3"][-1] - second["volume_m3"][-1]).sum()
                            / max(float(second["volume_m3"][-1].sum()), 1e-30))
    return {"max_saved_stage_error_m": stage_error,
            "max_saved_cumulative_face_net_relative_l1": flux_error,
            "directional_total_relative_l1": directional_error,
            "final_inventory_relative_l1": inventory_error,
            "passed": all(value <= limit for value, limit in
                          ((stage_error, STAGE_LIMIT_M), (flux_error, RELATIVE_LIMIT),
                           (directional_error, RELATIVE_LIMIT), (inventory_error, RELATIVE_LIMIT)))}


def audit(directory, expected_index_sha256):
    directory = Path(directory).resolve(strict=True)
    index_path = directory / "index.json"
    _require(file_sha256(index_path) == expected_index_sha256, "Radau index external SHA mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    _require(index["schema"] == "td-radau-overflow-refinement-v1" and index["algorithm"] == ALGORITHM,
             "Radau index schema or algorithm mismatch")
    _require(index["status"] in ("ready_for_independent_audit", "diagnostic_stop"), "invalid runner status")
    _require(all(index.get(key) is False for key in
                 ("hydraulic_ready", "natural_outlet_verified", "publishable")),
             "index claims unsupported certification")
    parent_pin = index["parent_index"]
    parent_path = _pin_path(parent_pin, directory)
    pinned_files = [(index_path, expected_index_sha256), (parent_path, parent_pin["sha256"])]
    _require(file_sha256(parent_path) == parent_pin["sha256"], "parent index SHA mismatch")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    _require(parent["schema"] in ("td-original-bed-overflow-diagnostic-v1",
                                  "td-original-bed-overflow-diagnostic-v2"), "parent index schema mismatch")
    _require(set(index["input_pins"]) == {"original_td", "hierarchy"}
             and index["input_pins"] == parent["input_pins"], "parent input pins mismatch")
    for pin in index["input_pins"].values():
        path = _pin_path(pin, parent_path.parent)
        _require(file_sha256(path) == pin["sha256"], "input pin SHA mismatch")
        pinned_files.append((path, pin["sha256"]))
    hierarchy_pin = index["input_pins"]["hierarchy"]
    hierarchy = load_basin_hierarchy(_pin_path(hierarchy_pin, parent_path.parent),
                                      expected_sha256=hierarchy_pin["sha256"],
                                      expected_identity=hierarchy_pin["identity_sha256"])
    _require(_same_pin(index["topology"], parent["topology"]), "parent topology pin mismatch")
    topology_pin = index["topology"]
    topology_path = _pin_path(topology_pin, parent_path.parent)
    pinned_files.append((topology_path, topology_pin["sha256"]))
    topology = load_overflow_topology(topology_path, expected_sha256=topology_pin["sha256"],
                                      expected_identity=topology_pin["identity_sha256"])
    _require(topology["metadata"]["hierarchy_identity_sha256"] == hierarchy["identity_sha256"]
             and topology["metadata"]["source_identity_sha256"] == hierarchy["metadata"]["source_identity_sha256"],
             "topology/hierarchy/source provenance mismatch")
    _require(set(index["code_sha256"]) == {
        'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
        'terrain_pipeline/basin_storage.py', "terrain_pipeline/mountain_source_adapter.py",
        "tools/audit_td_original_bed_overflow.py", "tools/verify_td_stable_overflow.py",
        "tools/prepare_td_radau_overflow.py"}, "runner code pin set mismatch")
    for name, digest in index["code_sha256"].items():
        _require(file_sha256(ROOT / name) == digest, f"code SHA mismatch: {name}")
        pinned_files.append((ROOT / name, digest))
    resources = index["resources"]
    _require(resources["monitor_error"] is None and resources["sample_count"] >= 2
             and 0 < resources["sample_interval_s"] <= .1
             and resources["rss_limit_bytes"] == 1024**3
             and resources["disk_limit_bytes"] == 2 * 1024**3
             and resources["peak_rss_bytes"] <= 1024**3
             and resources["peak_output_disk_bytes"] <= 2 * 1024**3
             and resources["counted_rhs_face_leaf_work"] <= 6_000_000_000,
             "resource budget or monitoring failed")
    _require(len(index["cases"]) == len(EVENTS)
             and {case["name"] for case in index["cases"]} == set(EVENTS), "incomplete event set")
    cases = []
    counted_work = 0
    audited_field_work = 0
    for case in index["cases"]:
        name = case["name"]
        rain_rate, duration = EVENTS[name]
        records = case["levels"]
        _require(len(records) >= 2 and len(records) <= 5
                 and [record["level"] for record in records] == list(range(len(records))),
                 f"{name}: missing refinement levels")
        loaded = []
        audits = []
        for record in records:
            level = record["level"]
            controls = {"max_step_s": 300. / 2**level, "rtol": 5e-7 / 2**level,
                        "atol_stage_m": 2e-7 / 2**level, "flux_atol_m3": .001 / 2**level}
            _require(record["controls"] == controls, f"{name}: refinement controls mismatch")
            pin = record["event"]
            path = _pin_path(pin, directory)
            _require(path.parent == directory and path.name == f"{name}-level-{level}.npz"
                     and path.stat().st_size == pin["bytes"], f"{name}: event pin mismatch")
            event = load_radau_overflow(path, expected_sha256=pin["sha256"],
                                         expected_identity=pin["identity_sha256"], topology=topology)
            pinned_files.append((path, pin["sha256"]))
            metadata = event["metadata"]
            _require(all(metadata[key] == value for key, value in controls.items()),
                     f"{name}: saved integration controls mismatch")
            audits.append(dict(level=level, identity_sha256=event["identity_sha256"],
                               ledger=_audit_event(topology, event, name, duration, rain_rate)))
            counted_work += metadata["work"]["rhs_evaluations"] * (topology["metadata"]["leaf_count"] + len(topology["faces"]))
            field_units = (topology["metadata"]["leaf_count"] + len(topology["faces"])
                           + len(topology["engineering_boundaries"]))
            audited_field_work += (metadata["work"]["rhs_evaluations"]
                                   + 4 * metadata["work"]["accepted_steps"]
                                   + metadata["steps"] + 1) * field_units
            _require(record["work"] == metadata["work"], f"{name}: saved work mismatch")
            loaded.append(event)
        comparisons = [_compare(loaded[level - 1], loaded[level]) for level in range(1, len(loaded))]
        _require(all(records[level]["comparison_with_previous"]["passed"] is comparisons[level - 1]["passed"]
                     for level in range(1, len(records))), f"{name}: runner comparison claim mismatch")
        passed = comparisons[-1]["passed"]
        _require(not any(comparison["passed"] for comparison in comparisons[:-1]),
                 f"{name}: refinement continued after accepted level")
        _require(case["temporal_refinement_passed"] is passed
                 and case["selected_level"] == (records[-1]["level"] if passed else None),
                 f"{name}: false convergence or selected level")
        cases.append({"name": name, "levels": audits, "comparisons": comparisons,
                      "selected_level": case["selected_level"], "temporal_refinement_passed": passed})
    _require(counted_work == resources["counted_rhs_face_leaf_work"] and counted_work <= 6_000_000_000,
             "counted work budget mismatch")
    _require(audited_field_work <= 6_000_000_000, "audited field evaluation work budget exceeded")
    passed = all(case["temporal_refinement_passed"] for case in cases)
    _require(index["status"] == ("ready_for_independent_audit" if passed else "diagnostic_stop"),
             "runner falsely claims accepted refinement")
    for path, digest in pinned_files:
        _require(file_sha256(path) == digest, f"pinned file changed during audit: {path}")
    report = {"schema": "td-radau-overflow-independent-audit-v1",
              "status": "passed" if passed else "failed", "index_sha256": expected_index_sha256,
              "scope": "original-bed basin reservoirs with fixed runoff coefficient and baseflow; no four-store hydrology; reservoir temporal refinement only",
              "cases": cases,
              "audited_field_evaluation_work": audited_field_work,
              "work_semantics": "upper-ish field evaluation units: (solver RHS evaluations + 4 per accepted step + saved steps + 1) times leaves plus physical and engineering boundary faces; not floating-point FLOPs or complete algorithm operations",
              "resource_monitor_semantics": "peak RSS and output disk are finite-interval samples, not continuous maxima",
              "cold_read": True, "solver_advanced": False,
              "natural_outlet_verified": False, "hydraulic_ready": False, "publishable": False}
    report_path = directory / "independent-audit.json"
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode("utf-8")
    if report_path.exists():
        _require(report_path.read_bytes() == payload, "existing independent audit report differs")
    else:
        publish_bytes(report_path, payload)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-index-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, args.expected_index_sha256), ensure_ascii=False))
