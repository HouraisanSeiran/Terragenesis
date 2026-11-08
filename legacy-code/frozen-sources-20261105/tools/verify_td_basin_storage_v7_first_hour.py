"""Original TD first-hour refinement only, with compensated forcing and simultaneous transport."""

from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256
from terrain_pipeline.td_basin_storage_v7_io import save_storage as save_basin_storage, load_storage as load_basin_storage
from terrain_pipeline.td_basin_storage_v7 import simulate_basin_storage, PROFILE
from terrain_pipeline.td_basin_transport_v6 import validate_cfl
from tools.verify_td_basin_storage import summary, HIERARCHY, HIERARCHY_SHA256, HIERARCHY_IDENTITY
from tools.audit_td_basin_generation import read_saved, audit_storage


def write(path, record):
    publish_bytes(path, json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def compare(coarse, fine):
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    step, cell = np.unravel_index(np.argmax(difference), difference.shape)
    receiver_error = float(abs(coarse["routed_volume_m3"] - fine["routed_volume_m3"]).sum() /
                           max(1e-12, fine["routed_volume_m3"].sum()))
    head_error = float(difference[step, cell])
    diagnostics = {}
    for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "internal_net_m3", "surface_et_m3"):
        delta = coarse[name][:step].sum(axis=0) - fine[name][:step].sum(axis=0)
        diagnostics[name] = {"at_max_depth_cell_m3": float(delta[cell]), "global_l1_m3": float(abs(delta).sum())}
    for name in ("soil_mm", "fast_mm", "slow_mm"):
        diagnostics[name] = {"at_max_depth_cell_mm": float(coarse[name][step, cell] - fine[name][step, cell]),
                             "max_saved_difference_mm": float(abs(coarse[name] - fine[name]).max())}
    return {"max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": receiver_error,
            "depth_gate_m": .001, "receiver_gate": .01, "gate_passed": head_error <= .001 and receiver_error <= .01,
            "max_difference_step": int(step), "max_difference_cell": int(cell),
            "max_difference_zx": list(map(int, divmod(cell, coarse["height_m"].shape[1]))),
            "coarse_depth_m": float(coarse["depth_m"][step, cell]), "fine_depth_m": float(fine["depth_m"][step, cell]),
            "forcing_partition_and_exchange_diagnostics": diagnostics,
            "failure_reason": None if head_error <= .001 and receiver_error <= .01 else "full-domain saved transient difference exceeds fixed gate"}


def verify(destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
        raise ValueError("primary source changed")
    code_names = ("terrain_pipeline/td_basin_storage_v7.py", "terrain_pipeline/td_basin_forcing_compensated.py", "terrain_pipeline/td_basin_storage_v4.py", "terrain_pipeline/td_basin_transport_v6.py", "terrain_pipeline/td_basin_storage.py",
                  "terrain_pipeline/td_basin_storage_implicit.py", "tools/verify_td_basin_storage_v7_first_hour.py",
                  "tools/audit_td_basin_generation.py", "terrain_pipeline/rainfall_runoff.py",
                  "terrain_pipeline/mountain_source_adapter.py", "terrain_pipeline/td_basin_hierarchy.py",
                  "terrain_pipeline/td_basin_source.py", "tools/verify_td_basin_storage.py", "terrain_pipeline/td_basin_storage_v7_io.py")
    code = {name: file_sha256(ROOT / name) for name in code_names}
    hierarchy = load_basin_hierarchy(HIERARCHY, expected_sha256=HIERARCHY_SHA256, expected_identity=HIERARCHY_IDENTITY)
    cells = hierarchy["arrays"]["height_m"].size
    faces = len(hierarchy["arrays"]["face_cells"])
    topology = hierarchy["arrays"]
    spacing = hierarchy["metadata"]["spacing_m"]
    boundary = topology["boundary_cells"]
    rows, columns = np.divmod(boundary, topology["height_m"].shape[1])
    widths = spacing * ((rows == 0).astype(int) + (rows == topology["height_m"].shape[0] - 1)
                        + (columns == 0) + (columns == topology["height_m"].shape[1] - 1))
    cfl = {str(step): validate_cfl(topology["face_cells"], boundary, widths, spacing, step, .6, cells)
           for step in (5., 2.5, 1.25, .625)}
    inputs = {"primary": {"path": str(PRIMARY_PATH), "sha256": PRIMARY_SHA256},
              "hierarchy": {"path": str(HIERARCHY), "sha256": HIERARCHY_SHA256, "identity": HIERARCHY_IDENTITY},
              "source_identity": hierarchy["metadata"]["source_identity_sha256"],
              "forcing": "one hour strong30mm/h; original full TD; identical zero initial depth and default soil/fast/slow",
              "initial_state": "depth0; frozen default RunoffParameters soil/fast/slow; identical across refinements",
              "steps_s": [5., 2.5, 1.25, .625], "face_conductance_m_s": .6, "wet_threshold_m": 1e-9,
              "profile": PROFILE, "max_work_face_steps": 6000000000, "job_memory_budget_bytes": 1073741824,
              "work_by_step": {str(step): int(3600 / step * faces) for step in (5., 2.5, 1.25, .625)},
              "saved_cells_time": cells, "code_sha256": code}
    inputs["positivity_cfl_by_step"] = cfl
    inputs["v5_strong_reference"] = {"path": str(ROOT / "verification/td-basin-generation/A-storage-v5-full-20261002T094535898252Z/strong-comparison.json"),
                                     "max_saved_depth_difference_m": .036112752799497105, "gate_passed": False}
    write(destination / "run-inputs.json", inputs)
    execution = {"schema": "td-v7-execution-code-v1", "profile": PROFILE, "numba": version("numba"),
                 "numpy": version("numpy"), "python": sys.version, "fastmath": False, "code_sha256": code,
                 "solver_source_utf8": (ROOT / code_names[0]).read_text(encoding="utf-8"),
                 "cold_read": "v4 validation uses v2 parameter schema only; no import of symmetric forcing compiled v7, JIT, or advancement",
                 "v3_correctness_evidence_invalidated": True,
                 "forcing_correction": "half runoff/rain/ET, full compiled transport, half runoff/rain/ET; same g/rain/wet threshold",
                 "transport_source_utf8": (ROOT / "terrain_pipeline/td_basin_transport_v6.py").read_text(encoding="utf-8")}
    write(destination / "execution-code.json", execution)
    results = {}
    comparisons = {}
    process = psutil.Process()
    start = time.perf_counter()
    for scenario in ("strong",):
        pins = {}
        for step in (5., 2.5, 1.25, .625):
            print(f"starting {scenario} {step}s symmetric forcing compiled v7", flush=True)
            began = time.perf_counter()
            rain = np.array([30.])
            result = simulate_basin_storage(hierarchy, rain, parameters={"substep_s": step})
            directory = destination / f"{scenario}-{step:g}s"
            path = directory / "storage.npz"
            memory = process.memory_info()
            peak = int(getattr(memory, "peak_wset", memory.rss))
            if peak > 1073741824:
                write(directory / "failure.json", {"reason": "process memory exceeded declared1GiB", "peak_bytes": peak})
                raise MemoryError("v7 first-hour job budget")
            save_basin_storage(path, result)
            pin = {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": result["identity_sha256"]}
            record = summary(result)
            record.update({"pin": pin, "elapsed_s": time.perf_counter() - began, "peak_process_bytes": peak,
                           "code_sha256": code, "profile": PROFILE, "hydraulic_ready": False, "publishable": False})
            write(directory / "report.json", record)
            del result
            arrays, metadata = read_saved(path, pin["expected_sha256"])
            audit = audit_storage(arrays, metadata)
            write(directory / "independent-audit.json", {"pin": pin, "checks": audit, "solver_advanced": False,
                  "auditor_sha256": code["tools/audit_td_basin_generation.py"], "hydraulic_ready": False})
            del arrays
            results[f"{scenario}-{step:g}s"] = record
            pins[str(step)] = pin
            print(f"complete {scenario} {step}s elapsed {record['elapsed_s']:.2f}s peak {peak}", flush=True)
        for coarse_step, fine_step in ((5.,2.5),(2.5,1.25),(1.25,.625)):
            coarse = load_basin_storage(**pins[str(coarse_step)])
            fine = load_basin_storage(**pins[str(fine_step)])
            label = f"strong-{coarse_step:g}-{fine_step:g}"
            comparisons[label] = {**compare(coarse["arrays"],fine["arrays"]),"coarse":pins[str(coarse_step)],"fine":pins[str(fine_step)]}
            write(destination/(label+"-comparison.json"),comparisons[label])
            print(json.dumps({label:comparisons[label]},ensure_ascii=True),flush=True)
            del coarse,fine
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256 or file_sha256(HIERARCHY) != HIERARCHY_SHA256:
        raise ValueError("input changed")
    if any(file_sha256(ROOT / name) != sha for name, sha in code.items()):
        raise ValueError("frozen execution source changed")
    report = {"schema": "td-v7-first-hour-refinement-v1", "scope": "entire original TD domain, first hour only; not 24h certification",
              "comparisons": comparisons, "runs": results, "elapsed_s": time.perf_counter() - start,
              "all_numerical_gates_passed": all(item["gate_passed"] for item in comparisons.values()),
              "hydraulic_ready": False, "publishable": False, "transient_converged": False,
              "next_repair_if_failed": "Diagnose simultaneous transport versus ordered soil/wet-front time integration using saved first-error ledgers; keep conductance, rain and gates fixed.",
              "old_packages_unchanged": True, "execution_sha256": file_sha256(destination / "execution-code.json")}
    write(destination / "report.json", report)
    print(json.dumps({"output": str(destination), "report_sha256": file_sha256(destination / "report.json"),
                      "gates": report["all_numerical_gates_passed"]}), flush=True)


if __name__ == "__main__":
    verify(ROOT / "verification/td-basin-generation" / ("A-storage-v7-first-hour-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))
