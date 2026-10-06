"""Public compiled driver, saved restart and original water audit on small cases."""

from datetime import datetime, timezone
import json
import argparse
from pathlib import Path
import sys
import tempfile

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_basin_storage_compiled_driver import simulate_basin_storage as optimized
from terrain_pipeline.td_basin_storage_continuation import simulate_basin_storage as reference
from terrain_pipeline.td_basin_storage_compiled_io import save_checkpoint, load_checkpoint, save_storage, load_storage
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.mountain_source_adapter import identity, file_sha256, publish_bytes
from tools.audit_td_basin_generation import audit_storage
from tools.audit_td_compiled_execution import compare, STATES, ERRORS


def audit(*, full_day=False):
    reports = []
    for missing in (False, True):
        valid = np.ones((3, 4), bool)
        if missing:
            valid[1, 1] = False
        bed = np.array([[3., 2., 0., 1.], [1., 0., 0., 2.], [2., 1., 0., 1.]])
        hierarchy = build_basin_hierarchy(make_td_source(bed, spacing_m=30, valid_mask=valid))
        rain = np.r_[np.full(6, 30.), np.zeros(18)] if full_day else np.array([30., 0., 10., 0.])
        duration_s = 3600. if full_day else 60.
        forcing_id = identity({"rain_mm_h": rain}, {"dt_s": duration_s})
        for step in ((2.5, 1.25) if full_day else (5., 2.5, 1.25)):
            previous_reference = previous_compiled = None
            with tempfile.TemporaryDirectory() as directory:
                for hour in range(len(rain)):
                    arguments = dict(dt_s=duration_s, parameters={"substep_s": step}, forcing_identity=forcing_id, full_rain_mm_h=rain)
                    original = reference(hierarchy, rain[hour:hour + 1], checkpoint=previous_reference, **arguments)
                    compiled = optimized(hierarchy, rain[hour:hour + 1], checkpoint=previous_compiled, **arguments)
                    fields = {}
                    for role in ("storage", "checkpoint"):
                        for name, expected in original[role]["arrays"].items():
                            allowed = 1e-8 if "duration" in name or "active_" in name else 1e-6 + abs(expected) * 1e-10
                            if name in STATES + ERRORS:
                                allowed = 1e-12 if "depth" in name else 1e-9
                            if expected.dtype.kind in "biu":
                                allowed = 0
                            fields[role + "_" + name] = compare(compiled[role]["arrays"][name], expected, allowed)
                    budget = audit_storage(compiled["storage"]["arrays"], compiled["storage"]["metadata"])
                    checkpoint_path = Path(directory) / f"{hour}.npz"
                    save_checkpoint(checkpoint_path, compiled["checkpoint"])
                    previous_compiled = load_checkpoint(checkpoint_path, expected_sha256=file_sha256(checkpoint_path),
                                                        expected_identity=compiled["checkpoint"]["identity_sha256"])
                    previous_reference = original["checkpoint"]
                    storage_path = Path(directory) / f"water{hour}.npz"
                    save_storage(storage_path, compiled["storage"])
                    load_storage(storage_path, expected_sha256=file_sha256(storage_path), expected_identity=compiled["storage"]["identity_sha256"])
                    reports.append({"unknown_mask": missing, "step_s": step, "hour": hour,
                                    "passed": all(value["passed"] for value in fields.values()), "fields": fields,
                                    "actual_step_budget": budget})
    memory = psutil.Process().memory_info()
    files = ["terrain_pipeline/td_basin_storage_compiled.py", "terrain_pipeline/td_basin_storage_compiled_driver.py",
             "terrain_pipeline/td_basin_storage_compiled_io.py"]
    return {"schema": "td-independent-compiled-driver-v1", "scope": "Public v9 versus v8, small valid and unknown-masked hierarchy with reload",
            "duration_s": duration_s, "forcing_plan": rain.tolist(), "full_day": full_day,
            "passed": all(value["passed"] for value in reports), "intervals": reports,
            "code_sha256": {name: file_sha256(ROOT / name) for name in files},
            "resources": {"peak_rss_bytes": int(getattr(memory, "peak_wset", memory.rss)), "peak_private_bytes": getattr(memory, "peak_pagefile", None)},
            "actual_TD_verified": False, "hydraulic_ready": False,
            "limitations": "Controlled small execution equivalence; invalid-input, public cold subprocess and original TD performance remain separate gates."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-day", action="store_true")
    arguments = parser.parse_args()
    result = audit(full_day=arguments.full_day)
    output = ROOT / "verification/td-basin-generation" / ("independent-compiled-driver-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, indent=2, allow_nan=False).encode())
    print(json.dumps({"output": str(output), "passed": result["passed"], "intervals": len(result["intervals"])}))
    if not result["passed"]:
        raise SystemExit(1)
