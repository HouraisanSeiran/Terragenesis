"""Independently bind all exported AMR water fans to original saved records."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ.setdefault(name,"1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import psutil
import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256,publish_bytes
from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest
from terrain_pipeline.surface_adaptive_io import validate_geometry
from tools.audit_surface_adaptive import audit_frame
from tools.audit_single_domain_fine_stage import read_json,read_bundle


def audit(manifest_record,output):
    started = time.monotonic()
    context = load_consumer_manifest(manifest_record["path"],expected_sha256=manifest_record["expected_sha256"])
    manifest = context["manifest"]
    if manifest["backend"]!="adaptive-saved-canonical-fan":
        raise ValueError("independent adaptive fan requires AMR consumer")
    stage = read_json(manifest["source_index"])
    source = read_json(stage["source_v7_index"])
    required_cases = {"dry-rain-root4","zero-source-lake-root4","tailwater-baseline-root4",
        "tailwater-rise-root1","tailwater-rise-root1-half-dt","tailwater-rise-root2","tailwater-rise-root4"}
    if (stage.get("schema")!="single-domain-adaptive-stage-index-v1"
            or set(manifest["scenarios"])!=required_cases or set(stage["cases"])!=required_cases):
        raise ValueError("independent adaptive fan complete seven-case coverage required")
    artifacts = {item["path"]:item for item in manifest["artifacts"]}
    root = Path(manifest_record["path"]).resolve().parent
    def copied_pin(name,original=None):
        item = artifacts[name]
        if original is not None and (item["sha256"]!=original["expected_sha256"] or item["identity_sha256"]!=original["expected_identity"]):
            raise ValueError("independent adaptive copied original record mismatch")
        return dict(path=str(root/name),expected_sha256=item["sha256"],expected_identity=item["identity_sha256"])
    cases = {}
    count = 0
    for name,scenario in manifest["scenarios"].items():
        case = stage["cases"][name]
        run = read_json(case["run"])
        source_case = source["cases"][case["source_v7_case"]]
        source_run = read_json(source_case["run"])
        if run["source_record"]!=source_case["run"]:
            raise ValueError("independent adaptive original four-store run binding mismatch")
        original_pin = copied_pin(scenario["evidence"]["original_rainfall_runoff"],source_run["forcing"])
        original_forcing,_,_ = read_bundle(original_pin)
        actual_pin = copied_pin(scenario["evidence"]["forcing"],run["forcing"])
        actual_forcing,_,_ = read_bundle(actual_pin)
        override = name=="zero-source-lake-root4"
        original_item = artifacts[scenario["evidence"]["original_rainfall_runoff"]]
        provenance = original_item["provenance"]
        if (original_item["role"]!="original-rainfall-runoff" or provenance["source_index"]!=stage["source_v7_index"]
                or provenance["source_run"]!=source_case["run"] or provenance["source_artifact"]!=source_run["forcing"]
                or provenance["used_hydraulic_forcing_zero"] is not override or scenario["used_hydraulic_forcing_zero"] is not override):
            raise ValueError("independent adaptive original four-store provenance/override mismatch")
        original_q = original_forcing["local_q_m3_s"].reshape(actual_forcing["forcing_m3_s"].shape)
        if not (np.all(actual_forcing["forcing_m3_s"]==0) if override else np.array_equal(actual_forcing["forcing_m3_s"],original_q)):
            raise ValueError("independent adaptive actual/original hydraulic forcing mismatch")
        bed_pin = copied_pin(scenario["geometry"],case["bed"])
        if len(scenario["frames"])!=5 or len(run["snapshots"])!=5:
            raise ValueError("independent adaptive five original snapshots required")
        frames = []
        for number,frame in enumerate(scenario["frames"]):
            snapshot_pin = copied_pin(frame["snapshot"],run["snapshots"][number])
            _,snapshot_metadata,_ = read_bundle(snapshot_pin)
            key = snapshot_metadata["geometry_identity"]
            geometry_pin = copied_pin(frame["adaptive_geometry"],run["geometries"][key])
            arrays,metadata,_ = read_bundle(geometry_pin)
            geometry = dict(arrays=arrays,metadata=metadata["raw_geometry_metadata"],identity_sha256=metadata["raw_geometry_identity"])
            validate_geometry(geometry)
            frame_pin = copied_pin(frame["artifact"])
            provenance = artifacts[frame["artifact"]]["provenance"]
            if (provenance["source_run"]!=case["run"] or provenance["source_snapshot"]!=run["snapshots"][number]
                    or provenance["source_bed"]!=case["bed"] or provenance["source_adaptive_geometry_identity"]!=key):
                raise ValueError("independent adaptive frame original provenance mismatch")
            frames.append(audit_frame(frame_pin,bed_pin,snapshot_pin,geometry,number))
            count += 1
        cases[name] = dict(bound_frames_verified=len(frames),frames=frames,
            original_four_store_forcing_copy_verified=True,used_hydraulic_forcing_zero=override)
        print("independent adaptive fans "+name,flush=True)
    if file_sha256(manifest_record["path"])!=manifest_record["expected_sha256"] or count!=35:
        raise ValueError("independent adaptive consumer changed or frame coverage incomplete")
    memory = psutil.Process().memory_info()
    resource = dict(elapsed_s=time.monotonic()-started,peak_rss_bytes=int(getattr(memory,"peak_wset",memory.rss)),
        peak_private_bytes=int(getattr(memory,"peak_pagefile",memory.vms)))
    if resource["elapsed_s"]>1800 or max(resource["peak_rss_bytes"],resource["peak_private_bytes"])>1073741824:
        raise RuntimeError("independent adaptive consumer resource budget exceeded")
    result = dict(schema="surface-adaptive-consumer-independent-audit-v1",source_manifest=manifest_record,
        source_index=manifest["source_index"],cases=cases,bound_frames_verified=count,
        all_fan_geometry_gates_passed=True,original_snapshot_bindings_verified=True,resource=resource,
        original_four_store_forcing_copies_verified=True,
        original_rainfall_runoff_bindings_verified=True,
        solver_advanced=False,stage_accepted=False,hydraulic_ready=False,natural_outlet_verified=False,publishable=False,
        code_sha256=file_sha256(Path(__file__)))
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True,exist_ok=False)
    target = output/"report.json"
    publish_bytes(target,(json.dumps(result,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    print(json.dumps(dict(path=str(target),expected_sha256=file_sha256(target))),flush=True)
    return result


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--manifest-sha256",required=True)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    audit(dict(path=str(args.manifest.resolve()),expected_sha256=args.manifest_sha256),args.output)
