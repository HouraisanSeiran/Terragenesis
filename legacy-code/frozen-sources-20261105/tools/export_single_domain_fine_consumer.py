"""Export saved fine stage data into a relocatable diagnostic consumer package."""

import argparse
import gc
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(name, "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import psutil

from terrain_pipeline import single_domain_fine_io as fine_io
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.single_domain_surface_consumer import (
    BUDGETS, SCHEMA, copy_payload, publish_manifest, load_consumer_manifest,
)
from tools.audit_single_domain_fine_stage import audit_fan


def no_execution_modules():
    if any(name == "numba" or name.startswith("numba.")
            or name == "terrain_pipeline.single_domain_fine_hydraulics"
            or name == "terrain_pipeline.regional_surface_hydraulics_accelerated"
            or name.startswith("terrain_pipeline.single_domain_shallow_water") for name in sys.modules):
        raise RuntimeError("fine consumer exporter imported execution modules")


def resources(started, artifacts):
    memory = psutil.Process().memory_info()
    result = dict(elapsed_s=time.monotonic()-started,
        peak_rss_bytes=int(getattr(memory, "peak_wset", memory.rss)),
        peak_private_bytes=int(getattr(memory, "peak_pagefile", memory.vms)))
    if (max(result["peak_rss_bytes"], result["peak_private_bytes"]) > BUDGETS["max_memory_bytes"]
            or sum(item["bytes"] for item in artifacts) > BUDGETS["max_output_bytes"]
            or result["elapsed_s"] > BUDGETS["max_wall_s"]):
        raise RuntimeError("fine consumer predeclared resource budget exceeded")
    return result


def export(index_path, index_sha256, output):
    no_execution_modules()
    started = time.monotonic()
    source_pin = dict(path=str(Path(index_path).resolve()), expected_sha256=index_sha256)
    index = fine_io._json(source_pin)
    if (index.get("schema") != "single-domain-fine-stage-index-v1"
            or any(index.get(flag) is not False for flag in fine_io.FLAGS)
            or len(index["cases"]) != 7):
        raise ValueError("fine consumer requires complete diagnostic stage index")
    stage_report = fine_io._json(index["report"])
    if stage_report["cases"] != index["cases"]:
        raise ValueError("fine consumer source report mismatch")
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    artifacts, scenarios, beds = [], {}, {}
    for name, case in index["cases"].items():
        bed_pin = case["bed"]
        identity = bed_pin["expected_identity"]
        bed = fine_io._load(bed_pin, fine_io.validate_canonical_bed)
        if identity not in beds:
            bed_name = "beds/"+identity+".npz"
            artifacts.append(copy_payload(output, bed_name, bed_pin, bed,
                role="continuous-bed-and-network", provenance=dict(source_index=source_pin, source_artifact=bed_pin)))
            beds[identity] = bed_name
        loaded = fine_io.load_fine_run(case["run"]["path"],
            expected_sha256=case["run"]["expected_sha256"], bed=bed)
        evidence = {}
        for role in ("geometry", "forcing", "states"):
            pin = loaded["index"][role]
            payload = name+"/"+role+".npz"
            artifacts.append(copy_payload(output, payload, pin, loaded[role], role="saved-"+role,
                provenance=dict(source_index=source_pin, source_run=case["run"], source_artifact=pin)))
            evidence[role] = payload
        frames = []
        steps = loaded["forcing"]["metadata"]["steps"]
        if len(case["frames"]) != steps+1:
            raise ValueError("fine consumer frame coverage mismatch")
        for number, entry in enumerate(case["frames"]):
            pin = entry["frame"]
            frame = fine_io._load(pin, lambda item: fine_io._check(item, "single-domain-fine-water-fan-v1"))
            metadata = frame["metadata"]
            time_s = float(loaded["states"]["arrays"]["time_s"][number])
            if (entry["state_index"] != number or metadata["state_index"] != number
                    or metadata["bed_identity"] != identity
                    or metadata["hydraulic_state_identity"] != loaded["states"]["identity_sha256"]
                    or metadata["time_s"] != time_s
                    or not np.array_equal(frame["arrays"]["cell_depth_m"], loaded["states"]["arrays"]["depth_m"][number])):
                raise ValueError("fine consumer original frame binding mismatch")
            audit_fan(bed["arrays"], frame["arrays"], bed["metadata"]["spacing_m"])
            payload = name+f"/frame-{number:02d}.npz"
            artifacts.append(copy_payload(output, payload, pin, frame, role="saved-water-frame",
                provenance=dict(source_index=source_pin, source_run=case["run"], source_artifact=pin)))
            frames.append(dict(frame=number, time_s=time_s, artifact=payload))
            resources(started, artifacts)
            del frame
        scenarios[name] = dict(geometry=beds[identity], frames=frames, evidence=evidence,
            spacing_m=case["spacing_m"], initial_kind=case["initial_kind"],
            max_dt_s=case["max_dt_s"], intervals_verified=loaded["intervals_verified"])
        print("exported "+name, flush=True)
        del loaded, bed
        gc.collect()
    if file_sha256(index_path) != index_sha256:
        raise ValueError("fine consumer source changed during export")
    no_execution_modules()
    manifest = dict(schema=SCHEMA, backend="fine-saved-fan", evidence_status="diagnostic-fine-only",
        source_index=source_pin, artifacts=artifacts, scenarios=scenarios, budgets=BUDGETS,
        output_bytes=sum(item["bytes"] for item in artifacts), resource=resources(started, artifacts),
        coordinates="physical metres [x,y,z]; x east, y up, z south; raster [z,x]",
        solver_advanced=False, execution_modules_absent=True,
        hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
        official_frontend_integrated=False, full_native_domain_fine_verified=False,
        all_predeclared_gates_passed=stage_report["all_predeclared_gates_passed"],
        comparisons=stage_report["comparisons"], scenario_gates=stage_report["scenario_gates"],
        limitations=stage_report["limitations"]+[
            "Consumer payloads are copies of saved evidence; loading never advances a solver.",
            "Intervals and sampled RK witnesses remain in the authenticated source stage for independent auditing.",
            "Fine consumer status stays diagnostic regardless of individual scenario results."],
        code_sha256={name: file_sha256(ROOT/name) for name in (
            "terrain_pipeline/single_domain_surface_consumer.py", "tools/export_single_domain_fine_consumer.py")})
    pin = publish_manifest(output, manifest)
    load_consumer_manifest(pin["path"], expected_sha256=pin["expected_sha256"])
    print(pin, flush=True)
    return pin


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    export(args.index, args.index_sha256, args.output)
