"""Cold feasibility census of all saved requests under the unchanged breach law."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_breach import DEFAULT_PARAMETERS
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_material_field import load_material_field

DIRECTORY = ROOT / "verification/natural-river-network/stable-spill-paths-20261005-01"
INDEX_SHA = "f1d6e89b3bb642f6ede52d231fa340bb41a8a03aa479ab4e889c648f361565af"


def evaluate(original, target, material, cells, volume, duration, spacing):
    required = original.ravel()[cells] - target
    slope = np.zeros(len(cells))
    slope[:-1] = (target[:-1] - target[1:]) / spacing
    config = DEFAULT_PARAMETERS
    potential = np.zeros(len(cells))
    potential[:-1] = (config["erosion_scale_m"] * material["erodibility"].ravel()[cells[:-1]]
                     * material["weak_path_preference"].ravel()[cells[:-1]]
                     * np.log1p(volume / config["reference_volume_m3"])
                     * (-np.expm1(-duration / config["reference_duration_s"]))
                     * np.sqrt(np.maximum(slope[:-1], 0.)))
    thickness_ok = bool(np.all(required <= material["erodible_thickness_m"].ravel()[cells] + 1e-8))
    potential_ok = bool(np.all(required <= potential + 1e-8))
    return {"thickness_passed": thickness_ok, "water_material_potential_passed": potential_ok,
            "feasible": thickness_ok and potential_ok, "max_required_depth_m": float(required.max()),
            "max_potential_depth_m": float(potential.max()), "worst_depth_shortfall_m": float(np.maximum(required - potential, 0.).max())}


def run(output):
    index_path = DIRECTORY / "index.json"
    if file_sha256(index_path) != INDEX_SHA:
        raise ValueError("saved spill index pin mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    pins = [(index_path, INDEX_SHA)]
    for key in ("requests", "material"):
        path = DIRECTORY / index[key]["path"]
        if file_sha256(path) != index[key]["sha256"]:
            raise ValueError("saved request/material pin mismatch")
        pins.append((path, index[key]["sha256"]))
    report = json.loads(pins[1][0].read_text(encoding="utf-8"))
    material_pin = index["material"]
    material = load_material_field(pins[2][0], expected_sha256=material_pin["sha256"], expected_identity=material_pin["identity_sha256"])
    hierarchy_pin = next(pin for pin in index["source_pins"] if pin.get("identity_sha256") == report["hierarchy_identity_sha256"])
    hierarchy = load_basin_hierarchy(hierarchy_pin["path"], expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    pins.append((Path(hierarchy_pin["path"]), hierarchy_pin["sha256"]))
    results = []
    for path in report["paths"]:
        for request in path["bounded_candidate_requests"]:
            cells = np.asarray(request["path_cell_ids"], np.int64)
            entry = evaluate(hierarchy["arrays"]["height_m"], np.asarray(request["target_bed_m"]), material["arrays"], cells,
                             request["routed_volume_m3"], request["wet_duration_s"], hierarchy["metadata"]["spacing_m"])
            results.append({"case": request["case"], "face_id": request["face_id"], "request_identity_sha256": request["identity_sha256"], **entry})
    cases = []
    for name in ("normal-24h", "strong-6h"):
        selected = [entry for entry in results if entry["case"] == name]
        if len(selected) != 503:
            raise ValueError("feasibility census source coverage changed")
        counts = Counter("feasible" if entry["feasible"] else "rejected" for entry in selected)
        thickness = [entry for entry in selected if entry["thickness_passed"]]
        cases.append({"name": name, "requests": len(selected), "counts": dict(counts),
                      "thickness_passed": len(thickness),
                      "water_material_potential_passed": sum(entry["water_material_potential_passed"] for entry in selected),
                      "nearest_thickness_legal_request": min(thickness, key=lambda entry: entry["worst_depth_shortfall_m"])})
    for path, expected in pins:
        if file_sha256(path) != expected:
            raise ValueError("feasibility input changed during cold census")
    output_report = {"schema": "td-saved-spill-feasibility-v1", "status": "diagnostic_only", "index_sha256": INDEX_SHA,
                     "cases": cases, "requests": results, "checked_requests": len(results),
                     "parameters": DEFAULT_PARAMETERS, "cold_read": True, "solver_advanced": False,
                     "candidate_generated": False, "baseline_unchanged": True,
                     "scope": "existing complete receiver paths, fixed synthetic material field and old audited events; not all possible conditioning paths",
                     "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    publish_bytes(output, json.dumps(output_report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return {"path": str(output), "sha256": file_sha256(output), "cases": cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))
