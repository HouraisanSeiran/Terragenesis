"""Bounded full-event refinement of the pinned original TD reservoir topology."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_overflow import OverflowParameters, load_overflow_topology
from terrain_pipeline.td_basin_overflow_implicit import (ALGORITHM, load_stable_overflow,
                                                        save_stable_overflow, simulate_stable_overflow)
from tools.audit_td_original_bed_overflow import audit_saved_arrays


HEIGHT_TOLERANCE_M = .001
FLUX_RELATIVE_TOLERANCE = .01
MAX_REFINEMENT_LEVEL = 8
MAX_WORK = 6_000_000_000
MAX_DISK_BYTES = 2 * 1024**3


def write_json(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode("utf-8"))


def compare_events(coarse, fine):
    first, second = coarse["arrays"], fine["arrays"]
    if (coarse["metadata"]["topology_identity_sha256"] != fine["metadata"]["topology_identity_sha256"]
            or coarse["metadata"]["parameters"] != fine["metadata"]["parameters"]
            or not np.array_equal(first["rain_mm_h"], second["rain_mm_h"])
            or not np.array_equal(first["volume_m3"][0], second["volume_m3"][0])):
        raise ValueError("refinement requires the same bed, physics, output times, rain and initial inventory")
    max_height_error = float(np.max(np.abs(first["stage_m"] - second["stage_m"])))
    coarse_net = np.cumsum(first["face_net_m3"], axis=0)
    fine_net = np.cumsum(second["face_net_m3"], axis=0)
    numerator = np.abs(coarse_net - fine_net).sum(axis=1)
    denominator = np.abs(fine_net).sum(axis=1)
    relative_flux_error = float(np.max(np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0.)))
    if np.any((denominator == 0.) & (numerator > 1e-9)):
        relative_flux_error = 1e300
    boundary_error = float(np.max(np.abs(np.cumsum(first["engineering_boundary_outflow_m3"], axis=0)
                                         - np.cumsum(second["engineering_boundary_outflow_m3"], axis=0)))) if second["engineering_boundary_outflow_m3"].shape[1] else 0.
    coarse_directional = np.concatenate((first["face_forward_m3"].sum(axis=0), first["face_reverse_m3"].sum(axis=0)))
    fine_directional = np.concatenate((second["face_forward_m3"].sum(axis=0), second["face_reverse_m3"].sum(axis=0)))
    directional_error = float(np.abs(coarse_directional - fine_directional).sum() / max(float(fine_directional.sum()), 1e-30))
    storage_error = float(np.abs(first["volume_m3"][-1] - second["volume_m3"][-1]).sum() / max(float(second["volume_m3"][-1].sum()), 1e-30))
    return {"max_saved_stage_error_m": max_height_error,
            "max_saved_cumulative_face_net_relative_l1": relative_flux_error,
            "directional_total_relative_l1": directional_error,
            "final_inventory_relative_l1": storage_error,
            "max_boundary_cumulative_difference_m3": boundary_error,
            "thresholds": {"stage_m": HEIGHT_TOLERANCE_M, "flux_relative_l1": FLUX_RELATIVE_TOLERANCE},
            "passed": max_height_error <= HEIGHT_TOLERANCE_M and relative_flux_error <= FLUX_RELATIVE_TOLERANCE
                      and directional_error <= FLUX_RELATIVE_TOLERANCE and storage_error <= FLUX_RELATIVE_TOLERANCE}


def run(saved_index, expected_index_sha256, output, *, max_level=MAX_REFINEMENT_LEVEL):
    saved_index, output = Path(saved_index).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if not 1 <= max_level <= MAX_REFINEMENT_LEVEL:
        raise ValueError("invalid refinement level budget")
    if file_sha256(saved_index) != expected_index_sha256:
        raise ValueError("original-bed parent index external hash mismatch")
    source = json.loads(saved_index.read_text(encoding="utf-8"))
    for record in source["input_pins"].values():
        if file_sha256(record["path"]) != record["sha256"]:
            raise ValueError("fixed TD input pin mismatch")
    pin = source["topology"]
    topology_path = saved_index.parent / Path(pin["path"]).name
    topology = load_overflow_topology(topology_path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    output.mkdir(parents=True)
    work, disk_bytes = 0, 0
    cases = []
    for name, rain_rate, duration in (("normal-24h", 30., 86400.), ("strong-6h", 120., 21600.)):
        config = OverflowParameters(timestep_s=300., duration_s=duration)
        rain = np.full(int(duration / config.timestep_s), rain_rate)
        previous = None
        levels = []
        accepted = False
        for level in range(max_level + 1):
            substep = 300. / 2**level
            next_work = int(duration / substep) * (len(topology["faces"]) + topology["metadata"]["leaf_count"])
            if work + next_work > MAX_WORK:
                raise MemoryError("implicit refinement arithmetic work budget exceeded")
            started = time.perf_counter()
            event = simulate_stable_overflow(topology, rain, parameters=config, substep_s=substep)
            path = output / f"{name}-level-{level}.npz"
            save_stable_overflow(event, path, topology)
            work += next_work
            disk_bytes += path.stat().st_size
            if disk_bytes > MAX_DISK_BYTES:
                raise MemoryError("implicit refinement disk budget exceeded")
            record = {"level": level, "substep_s": substep, "event": {"path": str(path), "sha256": file_sha256(path),
                      "identity_sha256": event["identity_sha256"], "bytes": path.stat().st_size},
                      "elapsed_s": time.perf_counter() - started, "live_ledger": audit_saved_arrays(topology, event)}
            if previous is not None:
                record["comparison_with_previous"] = compare_events(previous, event)
                accepted = record["comparison_with_previous"]["passed"]
            levels.append(record)
            write_json(output / f"{name}-level-{level}.json", record)
            print(json.dumps({"case": name, "substep_s": substep, "elapsed_s": record["elapsed_s"],
                              "comparison": record.get("comparison_with_previous"),
                              "canceled_fraction": record["live_ledger"]["canceled_fraction_of_gross"]}), flush=True)
            if accepted:
                break
            previous = event
        cases.append({"name": name, "temporal_refinement_passed": accepted, "levels": levels,
                      "selected_level": levels[-1]["level"] if accepted else None})
    for record in source["input_pins"].values():
        if file_sha256(record["path"]) != record["sha256"]:
            raise ValueError("fixed TD input changed during solve")
    if file_sha256(saved_index) != expected_index_sha256:
        raise ValueError("parent index changed during solve")
    result = {"schema": "td-stable-overflow-refinement-v1", "algorithm": ALGORITHM,
              "status": "ready_for_independent_audit" if all(case["temporal_refinement_passed"] for case in cases) else "diagnostic_stop",
              "parent_index": {"path": str(saved_index), "sha256": expected_index_sha256},
              "topology": {"path": str(topology_path), "sha256": pin["sha256"], "identity_sha256": pin["identity_sha256"]},
              "input_pins": source["input_pins"], "cases": cases,
              "resources": {"counted_face_leaf_steps": work, "saved_event_bytes": disk_bytes,
                            "work_limit": MAX_WORK, "disk_limit_bytes": MAX_DISK_BYTES, "event_array_limit_bytes": 128 * 1024**2},
              "thresholds": {"stage_m": HEIGHT_TOLERANCE_M, "flux_relative_l1": FLUX_RELATIVE_TOLERANCE},
              "code_sha256": {"solver": file_sha256(ROOT / "terrain_pipeline/td_basin_overflow_implicit.py"),
                              "runner": file_sha256(Path(__file__))},
              "natural_outlet_verified": False, "hydraulic_ready": False, "publishable": False}
    write_json(output / "index.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--saved-index", type=Path, required=True)
    parser.add_argument("--expected-index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-level", type=int, default=MAX_REFINEMENT_LEVEL)
    args = parser.parse_args()
    try:
        result = run(args.saved_index, args.expected_index_sha256, args.output, max_level=args.max_level)
        print(json.dumps({"status": result["status"], "output": str(args.output)}))
    except Exception as error:
        if args.output.is_dir() and not (args.output / "index.json").exists():
            write_json(args.output / "failure.json", {"status": "failed", "reason": str(error)})
        raise
