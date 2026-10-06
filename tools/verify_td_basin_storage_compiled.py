"""Serial original-TD first-hour execution equivalence against pinned saved v8 pages."""
from pathlib import Path
from datetime import datetime,timezone
import json
import sys
import time
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import psutil
from terrain_pipeline.mountain_source_adapter import file_sha256,publish_bytes,identity
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_storage_compiled_driver import simulate_basin_storage
from terrain_pipeline.td_basin_storage_compiled_io import save_storage,save_checkpoint
from terrain_pipeline.td_basin_storage_continuation_io import load_storage
from terrain_pipeline.td_basin_storage_checkpoint_io import load_checkpoint
from tools.verify_td_basin_storage import HIERARCHY,HIERARCHY_SHA256,HIERARCHY_IDENTITY
from tools.audit_td_basin_generation import audit_storage
from tools.publish_td_accepted_review import accepted_inputs

BASELINE=ROOT/"verification/td-basin-generation/A-storage-continuation-20261002T110815168692Z"


def write(path,value):
    publish_bytes(path,json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode("utf-8"))


def verify(destination,acceptance_path,acceptance_sha256):
    if file_sha256(acceptance_path)!=acceptance_sha256:
        raise ValueError("external acceptance SHA mismatch")
    acceptance=accepted_inputs(acceptance_path,acceptance_sha256)
    index=BASELINE/"index.json"
    if not index.exists():
        raise ValueError("complete frozen v8 index required; do not overlap current heavy job")
    resource_path=BASELINE/"resource.json"
    resource_pin=acceptance["acceptance_arguments"]["execution_resource_record"]
    if Path(resource_pin["path"]).resolve()!=resource_path.resolve() or file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted execution resource external pin mismatch")
    resource=json.loads(resource_path.read_text(encoding="utf-8"))
    baseline_index=json.loads(index.read_text(encoding="utf-8"))
    index_sha=file_sha256(index)
    if acceptance.get("input_index_sha256")!=index_sha or Path(acceptance.get("input_index","")).resolve()!=index.resolve():
        raise ValueError("external acceptance does not bind this baseline index")
    if resource.get("index_sha256")!=index_sha or resource.get("complete") is not True or resource.get("scope")!="complete ordinary+strong both steps execution" or max(resource["peak_rss_bytes"],resource["peak_private_bytes"])>1073741824 or baseline_index.get("all_numerical_gates_passed") is not True:
        raise ValueError("complete accepted v8 resource/numerical reference required")
    frozen=baseline_index["code_sha256"]
    if any(file_sha256(ROOT/name)!=sha for name,sha in frozen.items()) or file_sha256(HIERARCHY)!=HIERARCHY_SHA256:
        raise ValueError("baseline frozen reference changed")
    code_names=("terrain_pipeline/td_basin_storage_compiled.py","terrain_pipeline/td_basin_storage_compiled_driver.py",
                "terrain_pipeline/td_basin_storage_compiled_io.py","terrain_pipeline/td_basin_transport_v6.py",
                "terrain_pipeline/td_basin_forcing_compensated.py","tools/verify_td_basin_storage_compiled.py",
                "tools/publish_td_accepted_review.py")
    code={name:file_sha256(ROOT/name) for name in code_names}
    hierarchy=load_basin_hierarchy(HIERARCHY,expected_sha256=HIERARCHY_SHA256,expected_identity=HIERARCHY_IDENTITY)
    references={}
    for step in (2.5,1.25):
        path=BASELINE/f"strong-{step:g}s/hour-00/report.json"
        references[str(step)]={"report_sha256":file_sha256(path),"report":json.loads(path.read_text(encoding="utf-8"))}
    write(destination/"run-inputs.json",{"scope":"originalTD first hour only; execution equivalence, not new hydraulic refinement",
        "profile":"v9-compiled-hour-loop-v8-equivalent-v1","reference_index_sha256":file_sha256(index),
        "references":references,"code_sha256":code,"external_acceptance":{"path":str(acceptance_path),"sha256":acceptance_sha256},"reference_resource_sha256":file_sha256(resource_path),"reference_frozen_code":frozen,"max_job_bytes":1073741824,"steps_s":[2.5,1.25]})
    records={}
    rain=np.zeros(24);rain[:6]=30
    forcing_id=identity({"rain_mm_h":rain},{"dt_s":3600.})
    for step in (2.5,1.25):
        began=time.perf_counter()
        result=simulate_basin_storage(hierarchy,rain[:1],parameters={"substep_s":step},forcing_identity=forcing_id,full_rain_mm_h=rain)
        elapsed=time.perf_counter()-began
        directory=destination/f"strong-{step:g}s"
        save_storage(directory/"storage.npz",result["storage"])
        save_checkpoint(directory/"checkpoint.npz",result["checkpoint"])
        checks=audit_storage(result["storage"]["arrays"],result["storage"]["metadata"])
        reference=references[str(step)]["report"]
        differences={}
        passed=True
        for role,loader in (("storage",load_storage),("checkpoint",load_checkpoint)):
            saved=loader(**reference[role])
            role_differences={}
            for key,value in result[role]["arrays"].items():
                expected=saved["arrays"][key]
                if value.shape!=expected.shape:
                    raise ValueError("execution field shape changed")
                if value.dtype!=expected.dtype:
                    raise ValueError("execution field dtype changed")
                maximum=float(abs(value.astype(float)-expected.astype(float)).max(initial=0))
                if key in ("height_m","valid_mask","face_cells","receiver","boundary_cells","boundary_width_m","rain_mm_h"):
                    ok=np.array_equal(value,expected)
                elif "duration" in key or "active_" in key:
                    ok=maximum<=1e-8
                elif key in ("depth_m","soil_mm","fast_mm","slow_mm") or key.startswith("error_"):
                    ok=maximum<=(1e-9 if key in ("soil_mm","fast_mm","slow_mm","error_soil","error_fast","error_slow") else 1e-12)
                elif value.dtype.kind in "biu":
                    ok=np.array_equal(value,expected)
                else:
                    ok=bool(np.all(abs(value-expected)<=1e-6+1e-10*(abs(value)+abs(expected))))
                role_differences[key]={"max_difference":maximum,"bit_equal":bool(np.array_equal(value,expected)),"passed":bool(ok)}
                passed=passed and bool(ok)
            differences[role]=role_differences
            del saved
        memory=psutil.Process().memory_info()
        resource={"peak_rss_bytes":int(getattr(memory,"peak_wset",memory.rss)),
                  "peak_private_bytes":int(max(getattr(memory,"private",memory.vms),getattr(memory,"peak_pagefile",0)))}
        passed=passed and max(resource.values())<=1073741824
        record={"elapsed_s":elapsed,"reference_elapsed_s":reference["elapsed_s"],"resource":resource,"all_equivalence_checks_passed":passed,
            "field_differences":differences,"water_audit":checks,"storage_sha256":file_sha256(directory/"storage.npz"),
            "storage_identity":result["storage"]["identity_sha256"],"checkpoint_sha256":file_sha256(directory/"checkpoint.npz"),
            "checkpoint_identity":result["checkpoint"]["identity_sha256"],"hydraulic_ready":False,"transient_converged":False}
        write(directory/"report.json",record)
        records[str(step)]=record
        del result
        print(json.dumps({"step":step,"elapsed_s":elapsed,"passed":passed,"resource":resource}),flush=True)
    if any(file_sha256(ROOT/name)!=sha for name,sha in code.items()):
        raise ValueError("compiled execution frozen code changed")
    if file_sha256(acceptance_path)!=acceptance_sha256 or file_sha256(index)!=index_sha or any(file_sha256(ROOT/name)!=sha for name,sha in frozen.items()) or file_sha256(resource_path)!=json.loads((destination/"run-inputs.json").read_text(encoding="utf-8"))["reference_resource_sha256"]:
        raise ValueError("reference changed during compiled execution probe")
    accepted_inputs(acceptance_path,acceptance_sha256)
    if file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted resource changed during probe")
    write(destination/"report.json",{"scope":"first-hour execution equivalence only","runs":records,"code_sha256":code,
        "all_passed":all(record["all_equivalence_checks_passed"] for record in records.values()),"hydraulic_ready":False,"publishable":False})
    print(json.dumps({"run":str(destination),"report_sha256":file_sha256(destination/"report.json")}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--acceptance",type=Path,required=True)
    parser.add_argument("--acceptance-sha256",required=True)
    arguments=parser.parse_args()
    verify(ROOT/"verification/td-basin-generation"/("A-compiled-execution-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),arguments.acceptance,arguments.acceptance_sha256)
