"""Cold-read the fixed audited reception and publish bounded, separate requests."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle, publish_bytes, validate_source
from terrain_pipeline.td_basin_breach import load_saddle_breach, save_saddle_breach
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_overflow import load_overflow_topology
from terrain_pipeline.td_basin_overflow_radau import load_radau_overflow
from terrain_pipeline.td_material_field import make_material_field, save_material_field
from terrain_pipeline.td_stable_spill_paths import CASE_NAMES, build_stable_spill_paths, generate_bounded_candidates
from tools.export_td_stable_basin_reception import load_export


RECEPTION_DIRECTORY = ROOT / "verification/natural-river-network/stable-reception-20261005-01"
EVENT_DIRECTORY = ROOT / "verification/natural-river-network/radau-overflow-20261005-03"
RECEPTION_SHA256 = "b026838ef77a772d82edf358c16e12fe828b51419337ac6a91a0ca4adeefaad6"
EVENT_SHA256 = "2bdf20aaee1d3f22d4e22ed94f26c66c761896a613afa1abb6338a658ad36618"
AUDIT_SHA256 = "ffbb9022c432ec4d0db9023dc4dbe2aab124925f7ebb21e7b8a9563a8b31c3c7"
MAX_JSON_BYTES = 128 * 1024**2


def _json(path, expected_sha256):
    path = Path(path)
    if path.stat().st_size >= MAX_JSON_BYTES or file_sha256(path) != expected_sha256:
        raise ValueError("fixed input JSON hash/budget mismatch: " + str(path))
    def unique(pairs):
        record = {}
        for key, value in pairs:
            if key in record:
                raise ValueError("duplicate input JSON key")
            record[key] = value
        return record
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite input JSON")))


def _path(pin, directory):
    path = Path(pin["path"])
    return (path if path.is_absolute() else directory / path).resolve(strict=True)


def load_fixed_inputs(reception_directory=RECEPTION_DIRECTORY, event_directory=EVENT_DIRECTORY):
    reception_directory = Path(reception_directory).resolve(strict=True)
    event_directory = Path(event_directory).resolve(strict=True)
    exported = load_export(reception_directory, expected_index_sha256=RECEPTION_SHA256)
    index = _json(event_directory / "index.json", EVENT_SHA256)
    audit = _json(event_directory / "independent-audit.json", AUDIT_SHA256)
    if (index["schema"] != "td-radau-overflow-refinement-v1" or
            audit["schema"] != "td-radau-overflow-independent-audit-v1" or
            audit["status"] != "passed" or audit["index_sha256"] != EVENT_SHA256 or
            audit["cold_read"] is not True or audit["solver_advanced"] is not False or
            exported["parent_index"]["sha256"] != EVENT_SHA256 or
            exported["independent_audit"]["sha256"] != AUDIT_SHA256):
        raise ValueError("fixed reception requires actual passed audit bound to event index")
    for container in (index, audit):
        for key in ("hydraulic_ready", "publishable", "natural_outlet_verified"):
            if container.get(key) is not False:
                raise ValueError("source evidence cannot certify natural hydraulics")
    parent_pin = index["parent_index"]
    parent_path = _path(parent_pin, event_directory)
    parent = _json(parent_path, parent_pin["sha256"])
    if parent["input_pins"] != index["input_pins"] or parent["topology"] != index["topology"]:
        raise ValueError("event parent source/topology pins differ")
    hierarchy_pin = index["input_pins"]["hierarchy"]
    topology_pin = index["topology"]
    if exported["hierarchy"] != hierarchy_pin or exported["topology"] != topology_pin:
        raise ValueError("reception hierarchy/topology pins differ from events")
    hierarchy = load_basin_hierarchy(_path(hierarchy_pin, parent_path.parent),
        expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    topology = load_overflow_topology(_path(topology_pin, parent_path.parent),
        expected_sha256=topology_pin["sha256"], expected_identity=topology_pin["identity_sha256"])
    original_pin = index["input_pins"]["original_td"]
    original = load_bundle(_path(original_pin, parent_path.parent),
                           expected_sha256=original_pin["sha256"], validator=validate_source)
    if (hierarchy["metadata"]["source_metadata"]["source_sha256"] != original_pin["sha256"] or
            not np.array_equal(original["arrays"]["height_m"], hierarchy["arrays"]["height_m"]) or
            not np.array_equal(original["arrays"]["hydrology_mask"], hierarchy["arrays"]["valid_mask"]) or
            original["metadata"]["origin_m_xz"] != hierarchy["metadata"]["origin_m_xz"] or
            original["metadata"]["spacing_m"] != hierarchy["metadata"]["spacing_m"]):
        raise ValueError("hierarchy bed/coverage/grid differs from fixed real TD")
    if (len(index["cases"]) != 2 or {case["name"] for case in index["cases"]} != set(CASE_NAMES) or
            len(audit["cases"]) != 2 or {case["name"] for case in audit["cases"]} != set(CASE_NAMES)):
        raise ValueError("ordinary/strong audit coverage mismatch")
    cases = []
    pins = [{"path": str(reception_directory / "index.json"), "sha256": RECEPTION_SHA256},
            {"path": str(event_directory / "index.json"), "sha256": EVENT_SHA256},
            {"path": str(event_directory / "independent-audit.json"), "sha256": AUDIT_SHA256},
            {"path": str(parent_path), "sha256": parent_pin["sha256"]}]
    reception_pin = _json(reception_directory / "index.json", RECEPTION_SHA256)["reception"]
    pins.append({"path": str(reception_directory / "reception.json"), "sha256": reception_pin["sha256"]})
    for pin in (hierarchy_pin, topology_pin, original_pin):
        pins.append({**pin, "path": str(_path(pin, parent_path.parent))})
    for case in index["cases"]:
        audited = next(item for item in audit["cases"] if item["name"] == case["name"])
        saved = next(item for item in exported["cases"] if item["name"] == case["name"])
        levels = case["levels"]
        if (len(levels) < 2 or case["temporal_refinement_passed"] is not True or
                audited["temporal_refinement_passed"] is not True or
                case["selected_level"] != levels[-1]["level"] or
                audited["selected_level"] != case["selected_level"] or
                saved["selected_level"] != case["selected_level"]):
            raise ValueError("selected event lacks audited refinement")
        bundles = []
        for position, key in [(-1, "selected_event"), (-2, "reference_event")]:
            pin = levels[position]["event"]
            path = _path(pin, event_directory)
            if (path.parent != event_directory or path.stat().st_size != pin["bytes"] or
                    saved[key] != pin or audited["levels"][position]["identity_sha256"] != pin["identity_sha256"]):
                raise ValueError("audited saved event identity/path/size mismatch")
            bundles.append(load_radau_overflow(path, expected_sha256=pin["sha256"],
                                               expected_identity=pin["identity_sha256"], topology=topology))
            pins.append({**pin, "path": str(path)})
        cases.append({"name": case["name"], "reception": saved["reception"],
                      "selected_event": bundles[0], "reference_event": bundles[1]})
    return {"hierarchy": hierarchy, "topology": topology, "cases": cases, "pins": pins}


def verify_pins(pins):
    for pin in pins:
        path = Path(pin["path"])
        if file_sha256(path) != pin["sha256"]:
            raise ValueError("input changed during preparation: " + str(path))


def prepare(output=None, *, max_candidates=8, requests_only=False):
    if type(max_candidates) is not int or not 0 <= max_candidates <= 8:
        raise ValueError("candidate call budget must be 0..8")
    output = None if output is None else Path(output).resolve()
    if output is not None and output.exists():
        raise FileExistsError(output)
    inputs = load_fixed_inputs()
    if output is not None and any(output.is_relative_to(Path(pin["path"]).parent.resolve()) for pin in inputs["pins"]):
        raise ValueError("new candidate output cannot be inside a frozen input directory")
    report = build_stable_spill_paths(inputs["hierarchy"], inputs["topology"], inputs["cases"])
    material = None
    generation = {"attempts": [], "candidates": [], "generation_calls": 0}
    if not requests_only and max_candidates and any(path["bounded_candidate_requests"] for path in report["paths"]):
        hierarchy = inputs["hierarchy"]
        material = make_material_field(hierarchy["arrays"]["height_m"].shape,
            origin_m_xz=hierarchy["metadata"]["origin_m_xz"], spacing_m=hierarchy["metadata"]["spacing_m"],
            protected_mask=hierarchy["arrays"]["protected_mask"])
        generation = generate_bounded_candidates(report, hierarchy, material, max_candidates=max_candidates)
    verify_pins(inputs["pins"])
    summary = {"schema": "td-stable-spill-paths-preparation-v1", "status": "diagnostic_only",
               "request_report_identity_sha256": report["identity_sha256"],
               "source_pins": inputs["pins"], "face_count": len(report["paths"]),
               "path_status_counts": dict(Counter(path["status"] for path in report["paths"])),
               "path_rejection_counts": dict(Counter(reason for path in report["paths"] for reason in path["rejection_reasons"])),
               "event_stable_reception_faces": {name: sum(path["event_evidence"][name]["stable_relationship"] for path in report["paths"]) for name in CASE_NAMES},
               "bounded_request_count": sum(len(path["bounded_candidate_requests"]) for path in report["paths"]),
               "candidate_attempts": generation["attempts"], "candidate_count": len(generation["candidates"]),
               "generation_calls": generation["generation_calls"],
               "candidate_status_counts": dict(Counter(attempt["status"] for attempt in generation["attempts"])),
               "candidate_rejection_counts": dict(Counter(reason for attempt in generation["attempts"] for reason in attempt["rejection_reasons"])),
               "requests_only": requests_only, "baseline_unchanged": True, "solver_advanced": False,
               "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
               "continuous_fine_corridor_ready": False,
               "material_semantics": "existing fixed-default synthetic material field; not measured geology; breach thresholds unchanged",
               "code_sha256": {name: file_sha256(ROOT / name) for name in (
                   "terrain_pipeline/td_stable_spill_paths.py", "tools/prepare_td_stable_spill_paths.py")}}
    if output is None:
        return summary
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) >= MAX_JSON_BYTES:
        raise MemoryError("request report exceeds 128 MiB budget")
    output.mkdir(parents=True, exist_ok=False)
    publish_bytes(output / "requests.json", payload)
    summary["requests"] = {"path": "requests.json", "sha256": file_sha256(output / "requests.json"), "bytes": len(payload)}
    if material is not None:
        save_material_field(material, output / "materials.npz")
        summary["material"] = {"path": "materials.npz", "sha256": file_sha256(output / "materials.npz"), "identity_sha256": material["identity_sha256"]}
    for attempt in generation["attempts"]:
        if "candidate_index" not in attempt:
            continue
        bundle = generation["candidates"][attempt["candidate_index"]]
        path = output / f"candidate-{attempt['candidate_index']:02d}.npz"
        save_saddle_breach(bundle, path)
        pin = {"path": path.name, "sha256": file_sha256(path), "identity_sha256": bundle["identity_sha256"]}
        loaded = load_saddle_breach(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        if loaded["metadata"]["status"] == "rejected":
            np.testing.assert_array_equal(loaded["arrays"]["height_m"], inputs["hierarchy"]["arrays"]["height_m"])
        attempt["artifact"] = pin
    verify_pins(inputs["pins"])
    publish_bytes(output / "index.json", json.dumps(summary, sort_keys=True, indent=2, allow_nan=False).encode("utf-8"))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="new output directory; omission performs verification without writing artifacts")
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--requests-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, max_candidates=args.max_candidates, requests_only=args.requests_only),
                     sort_keys=True, allow_nan=False))
