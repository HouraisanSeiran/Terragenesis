"""Pinned full-event adaptive refinement; frozen legacy results remain untouched."""

import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_overflow import OverflowParameters, load_overflow_topology
from terrain_pipeline.td_basin_overflow_radau import ALGORITHM, save_radau_overflow, simulate_radau_overflow
from tools.audit_td_original_bed_overflow import audit_saved_arrays
from tools.verify_td_stable_overflow import compare_events


CODE_FILES = ("terrain_pipeline/td_basin_overflow_radau.py", "terrain_pipeline/td_basin_overflow_implicit.py",
              "terrain_pipeline/td_basin_overflow.py", "terrain_pipeline/mountain_source_adapter.py",
              "tools/audit_td_original_bed_overflow.py", "tools/verify_td_stable_overflow.py",
              "tools/prepare_td_radau_overflow.py")


def write_json(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode("utf-8"))


def run(saved_index, expected_index_sha256, output, *, max_level=4):
    saved_index, output = Path(saved_index).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if not 1 <= max_level <= 4:
        raise ValueError("invalid adaptive refinement level budget")
    if file_sha256(saved_index) != expected_index_sha256:
        raise ValueError("parent index external hash mismatch")
    source = json.loads(saved_index.read_text(encoding="utf-8"))
    for record in source["input_pins"].values():
        if file_sha256(record["path"]) != record["sha256"]:
            raise ValueError("fixed TD input pin mismatch")
    topology_pin = source["topology"]
    topology_path = saved_index.parent / Path(topology_pin["path"]).name
    topology = load_overflow_topology(topology_path, expected_sha256=topology_pin["sha256"], expected_identity=topology_pin["identity_sha256"])
    code_pins = {name: file_sha256(ROOT / name) for name in CODE_FILES}
    output.mkdir(parents=True)
    write_json(output / "configuration.json", {"parent_sha256": expected_index_sha256, "pid": os.getpid(),
               "algorithm": ALGORITHM, "code_sha256": code_pins, "max_level": max_level,
               "thresholds": {"stage_m": .001, "cumulative_net_relative_l1": .01}})
    stopped = threading.Event()
    process = psutil.Process()
    resource = {"peak_rss_bytes": process.memory_info().rss, "peak_output_disk_bytes": 0,
                "rss_limit_bytes": 1024**3, "disk_limit_bytes": 2 * 1024**3,
                "sample_interval_s": .1, "sample_count": 0, "monitor_error": None}

    def sample():
        try:
            while not stopped.is_set():
                resource["peak_rss_bytes"] = max(resource["peak_rss_bytes"], process.memory_info().rss)
                disk = 0
                for path in output.iterdir():
                    try:
                        if path.is_file():
                            disk += path.stat().st_size
                    except FileNotFoundError:
                        continue
                resource["peak_output_disk_bytes"] = max(resource["peak_output_disk_bytes"], disk)
                resource["sample_count"] += 1
                stopped.wait(.1)
        except Exception as error:
            resource["monitor_error"] = str(error)

    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    cases, work = [], 0
    started_run = time.perf_counter()
    try:
        for name, rain_rate, duration in (("normal-24h", 30., 86400.), ("strong-6h", 120., 21600.)):
            previous = None
            levels = []
            accepted = False
            config = OverflowParameters(timestep_s=300., duration_s=duration)
            rain = np.full(int(duration / config.timestep_s), rain_rate)
            for level in range(max_level + 1):
                controls = {"max_step_s": 300. / 2**level, "rtol": 5e-7 / 2**level,
                            "atol_stage_m": 2e-7 / 2**level, "flux_atol_m3": .001 / 2**level}
                print(json.dumps({"state": "solving", "case": name, "level": level, "controls": controls}), flush=True)
                started = time.perf_counter()
                event = simulate_radau_overflow(topology, rain, parameters=config, **controls)
                path = output / f"{name}-level-{level}.npz"
                save_radau_overflow(event, path, topology)
                work += event["metadata"]["work"]["rhs_evaluations"] * (topology["metadata"]["leaf_count"] + len(topology["faces"]))
                if resource["monitor_error"] is not None or work > 6_000_000_000 or resource["peak_rss_bytes"] > resource["rss_limit_bytes"] or resource["peak_output_disk_bytes"] > resource["disk_limit_bytes"]:
                    raise MemoryError("adaptive refinement work/RSS/disk budget exceeded")
                record = {"level": level, "controls": controls, "event": {"path": str(path), "sha256": file_sha256(path),
                          "identity_sha256": event["identity_sha256"], "bytes": path.stat().st_size},
                          "elapsed_s": time.perf_counter() - started, "work": event["metadata"]["work"],
                          "live_ledger": audit_saved_arrays(topology, event)}
                if previous is not None:
                    record["comparison_with_previous"] = compare_events(previous, event)
                    accepted = record["comparison_with_previous"]["passed"]
                levels.append(record)
                write_json(output / f"{name}-level-{level}.json", record)
                print(json.dumps({"state": "saved", "case": name, "level": level,
                                  "elapsed_s": record["elapsed_s"], "comparison": record.get("comparison_with_previous"),
                                  "canceled_fraction": record["live_ledger"]["canceled_fraction_of_gross"]}), flush=True)
                if accepted:
                    break
                previous = event
            cases.append({"name": name, "temporal_refinement_passed": accepted, "levels": levels,
                          "selected_level": levels[-1]["level"] if accepted else None})
    finally:
        stopped.set()
        monitor.join()
    for name, digest in code_pins.items():
        if file_sha256(ROOT / name) != digest:
            raise ValueError("adaptive solver code changed during solve")
    for record in source["input_pins"].values():
        if file_sha256(record["path"]) != record["sha256"]:
            raise ValueError("fixed TD source changed during solve")
    if file_sha256(saved_index) != expected_index_sha256:
        raise ValueError("parent index changed during solve")
    result = {"schema": "td-radau-overflow-refinement-v1", "algorithm": ALGORITHM,
              "status": "ready_for_independent_audit" if all(case["temporal_refinement_passed"] for case in cases) else "diagnostic_stop",
              "parent_index": {"path": str(saved_index), "sha256": expected_index_sha256},
              "input_pins": source["input_pins"],
              "topology": {"path": str(topology_path), "sha256": topology_pin["sha256"], "identity_sha256": topology_pin["identity_sha256"]},
              "cases": cases, "resources": dict(resource, counted_rhs_face_leaf_work=work, elapsed_s=time.perf_counter() - started_run),
              "code_sha256": code_pins, "natural_outlet_verified": False, "hydraulic_ready": False, "publishable": False}
    write_json(output / "index.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--saved-index", type=Path, required=True)
    parser.add_argument("--expected-index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-level", type=int, default=4)
    args = parser.parse_args()
    try:
        result = run(args.saved_index, args.expected_index_sha256, args.output, max_level=args.max_level)
        print(json.dumps({"status": result["status"], "output": str(args.output)}))
    except Exception as error:
        if args.output.is_dir() and not (args.output / "index.json").exists():
            write_json(args.output / "failure.json", {"status": "failed", "reason": str(error)})
        raise
