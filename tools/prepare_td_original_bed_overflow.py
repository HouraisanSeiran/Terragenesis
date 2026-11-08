"""Prepare pinned original-bed basin overflow diagnostics for the TD mountain."""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import OverflowParameters as OverflowParameters
from terrain_pipeline.basin_storage import build_overflow_topology as build_overflow_topology
from terrain_pipeline.basin_storage import save_overflow_event as save_overflow_event
from terrain_pipeline.basin_storage import save_overflow_topology as save_overflow_topology
from terrain_pipeline.basin_storage import simulate_overflow as simulate_overflow
from terrain_pipeline.basin_storage import validate_overflow_event as validate_overflow_event
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256


HIERARCHY = {
    "path": ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz",
    "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
    "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998",
}


def _json(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   allow_nan=False, indent=2).encode("utf-8"))


def _pin(path):
    return {"path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size}


def prepare(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
        raise ValueError("original TD source pin mismatch")
    hierarchy = load_basin_hierarchy(HIERARCHY["path"], expected_sha256=HIERARCHY["expected_sha256"],
                                     expected_identity=HIERARCHY["expected_identity"])
    topology = build_overflow_topology(hierarchy, expected_hierarchy_identity=HIERARCHY["expected_identity"])
    topology_path = output / "original-bed-overflow-topology.json"
    save_overflow_topology(topology, topology_path)
    topology_pin = _pin(topology_path)
    topology_pin["identity_sha256"] = topology["identity_sha256"]
    cases = (
        ("normal-24h", np.full(24, 30.0), OverflowParameters(timestep_s=300.0, duration_s=86400.0)),
        ("strong-6h", np.full(6, 120.0), OverflowParameters(timestep_s=300.0, duration_s=21600.0)),
    )
    case_records = []
    for name, rain, parameters in cases:
        rain = np.full(int(parameters.duration_s / parameters.timestep_s), float(rain[0]), dtype=np.float64)
        event = simulate_overflow(topology, rain, parameters=parameters)
        validate_overflow_event(event, topology)
        path = output / f"{name}.json"
        save_overflow_event(event, path)
        arrays = event["arrays"]
        onset = arrays["spill_onset_step"]
        case_records.append({"name": name, "event": _pin(path), "event_identity_sha256": event["identity_sha256"],
                             "steps": parameters.duration_s / parameters.timestep_s,
                             "rainfall_mm_h": float(rain[0]),
                             "total_input_m3": float(arrays["input_volume_m3"].sum()),
                             "total_internal_face_exchange_m3": float(arrays["face_volume_m3"].sum()),
                             "orientation_signed_face_net_sum_m3": float(arrays["face_net_m3"].sum()),
                             "total_basin_net_internal_m3": float(arrays["basin_net_internal_m3"].sum()),
                             "total_internal_gross_exchange_m3": float(arrays["face_volume_m3"].sum()),
                             "max_abs_basin_net_internal_m3": float(np.max(np.abs(arrays["basin_net_internal_m3"]))),
                             "total_engineering_boundary_outflow_m3": float(arrays["engineering_boundary_outflow_m3"].sum()),
                             "spill_face_count": int(np.count_nonzero(onset >= 0)),
                             "first_spill_step": None if not np.any(onset >= 0) else int(np.min(onset[onset >= 0])),
                             "max_stage_m": float(arrays["stage_m"].max()),
                             "max_volume_m3": float(arrays["volume_m3"].sum(axis=1).max()),
                             "max_abs_balance_residual_m3": float(np.max(np.abs(arrays["balance_residual_m3"]))),
                             "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False})
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256 or file_sha256(HIERARCHY["path"]) != HIERARCHY["expected_sha256"]:
        raise ValueError("fixed source changed during preparation")
    index = {"schema": "td-original-bed-overflow-diagnostic-v1", "status": "diagnostic_only",
             "scope": "original immutable bed basin reservoirs and engineering-boundary spill diagnostics",
             "input_pins": {"hierarchy": {"path": str(HIERARCHY["path"]), "sha256": HIERARCHY["expected_sha256"],
                                            "identity_sha256": HIERARCHY["expected_identity"]},
                            "original_td": {"path": str(PRIMARY_PATH), "sha256": PRIMARY_SHA256}},
             "topology": topology_pin, "cases": case_records,
             "summary": {"leaf_count": topology["metadata"]["leaf_count"],
                         "physical_face_count": topology["metadata"]["physical_face_count"],
                         "engineering_boundary_face_count": topology["metadata"]["engineering_boundary_face_count"],
                         "natural_outlet_verified": False, "hydraulic_ready": False, "publishable": False},
             "semantics": {"bed": "original TD bed unchanged", "water": "rainfall runoff coefficient plus baseflow added to contribution-basin reservoirs",
                           "face": "one lowest-sill physical face per contribution-leaf pair; forward, reverse, signed net, and round-trip gross volumes are retained",
                           "basin_ledger": "basin_net_internal_m3 is signed net water received by each basin; basin_gross_internal_m3 counts both sides of every exchange and is not added water",
                           "boundary": "engineering open boundary discharge is tracked separately and does not certify a natural mouth",
                           "limitations": "no finite-channel Saint-Venant solve, no new bed, no natural outlet evidence, no cross-domain dynamic coupling"},
             "code_sha256": {'terrain_pipeline/basin_storage.py': file_sha256(ROOT / 'terrain_pipeline/basin_storage.py'),
                             "tools/prepare_td_original_bed_overflow.py": file_sha256(Path(__file__))},
             "solver_advanced": False, "natural_outlet_verified": False, "hydraulic_ready": False, "publishable": False}
    _json(output / "index.json", index)
    index["index_sha256"] = file_sha256(output / "index.json")
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or ROOT / "verification/natural-river-network" / ("original-bed-overflow-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    result = prepare(destination)
    print(json.dumps({"output": str(destination), "index_sha256": result["index_sha256"], "summary": result["summary"],
                      "cases": result["cases"]}, ensure_ascii=False))
