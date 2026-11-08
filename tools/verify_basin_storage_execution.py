"""M4 tools.verify_basin_storage_execution; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from datetime import datetime as _m4_verify_td_basin_storage_compiled_datetime
from datetime import datetime as _m4_verify_td_basin_storage_compiled_ordinary_stages_datetime
from datetime import datetime as _m4_verify_td_basin_storage_compiled_stages_datetime
from datetime import datetime as _m4_verify_td_basin_storage_continuation_datetime
from datetime import datetime as _m4_verify_td_native_weather_storage_datetime
from datetime import datetime as _m4_verify_td_native_weather_storage_v10_datetime
from datetime import timezone as _m4_verify_td_basin_storage_compiled_ordinary_stages_timezone
from datetime import timezone as _m4_verify_td_basin_storage_compiled_stages_timezone
from datetime import timezone as _m4_verify_td_basin_storage_compiled_timezone
from datetime import timezone as _m4_verify_td_basin_storage_continuation_timezone
from datetime import timezone as _m4_verify_td_native_weather_storage_timezone
from datetime import timezone as _m4_verify_td_native_weather_storage_v10_timezone
from pathlib import Path as _m4_verify_td_basin_storage_compiled_Path
from pathlib import Path as _m4_verify_td_basin_storage_compiled_ordinary_stages_Path
from pathlib import Path as _m4_verify_td_basin_storage_compiled_stages_Path
from pathlib import Path as _m4_verify_td_basin_storage_continuation_Path
from pathlib import Path as _m4_verify_td_native_weather_storage_Path
from pathlib import Path as _m4_verify_td_native_weather_storage_v10_Path
import argparse as _m4_verify_td_basin_storage_compiled_argparse
import argparse as _m4_verify_td_basin_storage_compiled_ordinary_stages_argparse
import argparse as _m4_verify_td_basin_storage_compiled_stages_argparse
import argparse as _m4_verify_td_basin_storage_continuation_argparse
import argparse as _m4_verify_td_native_weather_storage_argparse
import argparse as _m4_verify_td_native_weather_storage_v10_argparse
import json as _m4_verify_td_basin_storage_compiled_json
import json as _m4_verify_td_basin_storage_compiled_ordinary_stages_json
import json as _m4_verify_td_basin_storage_compiled_stages_json
import json as _m4_verify_td_basin_storage_continuation_json
import json as _m4_verify_td_native_weather_storage_json
import json as _m4_verify_td_native_weather_storage_v10_json
import math as _m4_verify_td_basin_storage_continuation_math
import math as _m4_verify_td_native_weather_storage_math
import numpy as _m4_verify_td_basin_storage_compiled_np
import numpy as _m4_verify_td_basin_storage_compiled_ordinary_stages_np
import numpy as _m4_verify_td_basin_storage_compiled_stages_np
import numpy as _m4_verify_td_basin_storage_continuation_np
import numpy as _m4_verify_td_native_weather_storage_np
import numpy as _m4_verify_td_native_weather_storage_v10_np
import os as _m4_verify_td_native_weather_storage_os
import os as _m4_verify_td_native_weather_storage_v10_os
import psutil as _m4_verify_td_basin_storage_compiled_ordinary_stages_psutil
import psutil as _m4_verify_td_basin_storage_compiled_psutil
import psutil as _m4_verify_td_basin_storage_compiled_stages_psutil
import psutil as _m4_verify_td_basin_storage_continuation_psutil
import psutil as _m4_verify_td_native_weather_storage_psutil
import psutil as _m4_verify_td_native_weather_storage_v10_psutil
import sys as _m4_verify_td_basin_storage_compiled_ordinary_stages_sys
import sys as _m4_verify_td_basin_storage_compiled_stages_sys
import sys as _m4_verify_td_basin_storage_compiled_sys
import sys as _m4_verify_td_basin_storage_continuation_sys
import sys as _m4_verify_td_native_weather_storage_sys
import sys as _m4_verify_td_native_weather_storage_v10_sys
import threading as _m4_verify_td_native_weather_storage_threading
import time as _m4_verify_td_basin_storage_compiled_ordinary_stages_time
import time as _m4_verify_td_basin_storage_compiled_stages_time
import time as _m4_verify_td_basin_storage_compiled_time
import time as _m4_verify_td_basin_storage_continuation_time
import time as _m4_verify_td_native_weather_storage_time
import time as _m4_verify_td_native_weather_storage_v10_time

# --- tools/verify_td_basin_storage_compiled.py:8 ---
compiled_ROOT=_m4_verify_td_basin_storage_compiled_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_compiled.py:9 ---
_m4_verify_td_basin_storage_compiled_sys.path.insert(0,str(compiled_ROOT))

# --- tools/verify_td_basin_storage_compiled.py:23 ---
compiled_BASELINE=compiled_ROOT/"verification/td-basin-generation/A-storage-continuation-20261002T110815168692Z"

# --- tools/verify_td_basin_storage_compiled.py:26 ---

def _m4_recorded_code_matches(recorded, *, root=None):
    """Accept published historical pins, or the unchanged current source bytes."""
    from pathlib import Path
    from terrain_pipeline.common_infra import file_sha256, published_algorithm_matches
    root=Path(__file__).resolve().parents[1] if root is None else Path(root).resolve()
    current={}
    for name in recorded:
        target=(root/name).resolve()
        if not target.is_relative_to(root):
            return False
        if target.is_file():
            current[name]=file_sha256(target)
    return published_algorithm_matches('basin_storage',recorded,current)

def compiled_write(path,value):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_compiled_publish_bytes
    _m4_verify_td_basin_storage_compiled_publish_bytes(path,_m4_verify_td_basin_storage_compiled_json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_compiled.py:30 ---
def compiled_verify(destination,acceptance_path,acceptance_sha256):
    from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as _m4_verify_td_basin_storage_compiled_load_checkpoint
    from terrain_pipeline.basin_storage import compiled_save_storage as _m4_verify_td_basin_storage_compiled_save_storage
    from terrain_pipeline.basin_storage import compileddriver_simulate as _m4_verify_td_basin_storage_compiled_simulate_basin_storage
    from terrain_pipeline.basin_storage import compiledio_save_checkpoint as _m4_verify_td_basin_storage_compiled_save_checkpoint
    from terrain_pipeline.basin_storage import continuation_load_storage as _m4_verify_td_basin_storage_compiled_load_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_compiled_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_compiled_file_sha256
    from terrain_pipeline.common_infra import identity as _m4_verify_td_basin_storage_compiled_identity
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_compiled_audit_storage
    from tools.publish_td_accepted_review import accepted_inputs as _m4_verify_td_basin_storage_compiled_accepted_inputs
    from tools.verify_basin_storage import threshold_storage_HIERARCHY as _m4_verify_td_basin_storage_compiled_HIERARCHY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_IDENTITY as _m4_verify_td_basin_storage_compiled_HIERARCHY_IDENTITY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_SHA256 as _m4_verify_td_basin_storage_compiled_HIERARCHY_SHA256
    if _m4_verify_td_basin_storage_compiled_file_sha256(acceptance_path)!=acceptance_sha256:
        raise ValueError("external acceptance SHA mismatch")
    acceptance=_m4_verify_td_basin_storage_compiled_accepted_inputs(acceptance_path,acceptance_sha256)
    index=compiled_BASELINE/"index.json"
    if not index.exists():
        raise ValueError("complete frozen v8 index required; do not overlap current heavy job")
    resource_path=compiled_BASELINE/"resource.json"
    resource_pin=acceptance["acceptance_arguments"]["execution_resource_record"]
    if _m4_verify_td_basin_storage_compiled_Path(resource_pin["path"]).resolve()!=resource_path.resolve() or _m4_verify_td_basin_storage_compiled_file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted execution resource external pin mismatch")
    resource=_m4_verify_td_basin_storage_compiled_json.loads(resource_path.read_text(encoding="utf-8"))
    baseline_index=_m4_verify_td_basin_storage_compiled_json.loads(index.read_text(encoding="utf-8"))
    index_sha=_m4_verify_td_basin_storage_compiled_file_sha256(index)
    if acceptance.get("input_index_sha256")!=index_sha or _m4_verify_td_basin_storage_compiled_Path(acceptance.get("input_index","")).resolve()!=index.resolve():
        raise ValueError("external acceptance does not bind this baseline index")
    if resource.get("index_sha256")!=index_sha or resource.get("complete") is not True or resource.get("scope")!="complete ordinary+strong both steps execution" or max(resource["peak_rss_bytes"],resource["peak_private_bytes"])>1073741824 or baseline_index.get("all_numerical_gates_passed") is not True:
        raise ValueError("complete accepted v8 resource/numerical reference required")
    frozen=baseline_index["code_sha256"]
    if not _m4_recorded_code_matches(frozen) or _m4_verify_td_basin_storage_compiled_file_sha256(_m4_verify_td_basin_storage_compiled_HIERARCHY)!=_m4_verify_td_basin_storage_compiled_HIERARCHY_SHA256:
        raise ValueError("baseline frozen reference changed")
    code_names=('terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
                'terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
                'terrain_pipeline/basin_storage.py','tools/verify_basin_storage_execution.py',
                "tools/publish_td_accepted_review.py")
    code={name:_m4_verify_td_basin_storage_compiled_file_sha256(compiled_ROOT/name) for name in code_names}
    hierarchy=_m4_verify_td_basin_storage_compiled_load_basin_hierarchy(_m4_verify_td_basin_storage_compiled_HIERARCHY,expected_sha256=_m4_verify_td_basin_storage_compiled_HIERARCHY_SHA256,expected_identity=_m4_verify_td_basin_storage_compiled_HIERARCHY_IDENTITY)
    references={}
    for step in (2.5,1.25):
        path=compiled_BASELINE/f"strong-{step:g}s/hour-00/report.json"
        references[str(step)]={"report_sha256":_m4_verify_td_basin_storage_compiled_file_sha256(path),"report":_m4_verify_td_basin_storage_compiled_json.loads(path.read_text(encoding="utf-8"))}
    compiled_write(destination/"run-inputs.json",{"scope":"originalTD first hour only; execution equivalence, not new hydraulic refinement",
        "profile":"v9-compiled-hour-loop-v8-equivalent-v1","reference_index_sha256":_m4_verify_td_basin_storage_compiled_file_sha256(index),
        "references":references,"code_sha256":code,"external_acceptance":{"path":str(acceptance_path),"sha256":acceptance_sha256},"reference_resource_sha256":_m4_verify_td_basin_storage_compiled_file_sha256(resource_path),"reference_frozen_code":frozen,"max_job_bytes":1073741824,"steps_s":[2.5,1.25]})
    records={}
    rain=_m4_verify_td_basin_storage_compiled_np.zeros(24);rain[:6]=30
    forcing_id=_m4_verify_td_basin_storage_compiled_identity({"rain_mm_h":rain},{"dt_s":3600.})
    for step in (2.5,1.25):
        began=_m4_verify_td_basin_storage_compiled_time.perf_counter()
        result=_m4_verify_td_basin_storage_compiled_simulate_basin_storage(hierarchy,rain[:1],parameters={"substep_s":step},forcing_identity=forcing_id,full_rain_mm_h=rain)
        elapsed=_m4_verify_td_basin_storage_compiled_time.perf_counter()-began
        directory=destination/f"strong-{step:g}s"
        _m4_verify_td_basin_storage_compiled_save_storage(directory/"storage.npz",result["storage"])
        _m4_verify_td_basin_storage_compiled_save_checkpoint(directory/"checkpoint.npz",result["checkpoint"])
        checks=_m4_verify_td_basin_storage_compiled_audit_storage(result["storage"]["arrays"],result["storage"]["metadata"])
        reference=references[str(step)]["report"]
        differences={}
        passed=True
        for role,loader in (("storage",_m4_verify_td_basin_storage_compiled_load_storage),("checkpoint",_m4_verify_td_basin_storage_compiled_load_checkpoint)):
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
                    ok=_m4_verify_td_basin_storage_compiled_np.array_equal(value,expected)
                elif "duration" in key or "active_" in key:
                    ok=maximum<=1e-8
                elif key in ("depth_m","soil_mm","fast_mm","slow_mm") or key.startswith("error_"):
                    ok=maximum<=(1e-9 if key in ("soil_mm","fast_mm","slow_mm","error_soil","error_fast","error_slow") else 1e-12)
                elif value.dtype.kind in "biu":
                    ok=_m4_verify_td_basin_storage_compiled_np.array_equal(value,expected)
                else:
                    ok=bool(_m4_verify_td_basin_storage_compiled_np.all(abs(value-expected)<=1e-6+1e-10*(abs(value)+abs(expected))))
                role_differences[key]={"max_difference":maximum,"bit_equal":bool(_m4_verify_td_basin_storage_compiled_np.array_equal(value,expected)),"passed":bool(ok)}
                passed=passed and bool(ok)
            differences[role]=role_differences
            del saved
        memory=_m4_verify_td_basin_storage_compiled_psutil.Process().memory_info()
        resource={"peak_rss_bytes":int(getattr(memory,"peak_wset",memory.rss)),
                  "peak_private_bytes":int(max(getattr(memory,"private",memory.vms),getattr(memory,"peak_pagefile",0)))}
        passed=passed and max(resource.values())<=1073741824
        record={"elapsed_s":elapsed,"reference_elapsed_s":reference["elapsed_s"],"resource":resource,"all_equivalence_checks_passed":passed,
            "field_differences":differences,"water_audit":checks,"storage_sha256":_m4_verify_td_basin_storage_compiled_file_sha256(directory/"storage.npz"),
            "storage_identity":result["storage"]["identity_sha256"],"checkpoint_sha256":_m4_verify_td_basin_storage_compiled_file_sha256(directory/"checkpoint.npz"),
            "checkpoint_identity":result["checkpoint"]["identity_sha256"],"hydraulic_ready":False,"transient_converged":False}
        compiled_write(directory/"report.json",record)
        records[str(step)]=record
        del result
        print(_m4_verify_td_basin_storage_compiled_json.dumps({"step":step,"elapsed_s":elapsed,"passed":passed,"resource":resource}),flush=True)
    if any(_m4_verify_td_basin_storage_compiled_file_sha256(compiled_ROOT/name)!=sha for name,sha in code.items()):
        raise ValueError("compiled execution frozen code changed")
    if _m4_verify_td_basin_storage_compiled_file_sha256(acceptance_path)!=acceptance_sha256 or _m4_verify_td_basin_storage_compiled_file_sha256(index)!=index_sha or not _m4_recorded_code_matches(frozen) or _m4_verify_td_basin_storage_compiled_file_sha256(resource_path)!=_m4_verify_td_basin_storage_compiled_json.loads((destination/"run-inputs.json").read_text(encoding="utf-8"))["reference_resource_sha256"]:
        raise ValueError("reference changed during compiled execution probe")
    _m4_verify_td_basin_storage_compiled_accepted_inputs(acceptance_path,acceptance_sha256)
    if _m4_verify_td_basin_storage_compiled_file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted resource changed during probe")
    compiled_write(destination/"report.json",{"scope":"first-hour execution equivalence only","runs":records,"code_sha256":code,
        "all_passed":all(record["all_equivalence_checks_passed"] for record in records.values()),"hydraulic_ready":False,"publishable":False})
    print(_m4_verify_td_basin_storage_compiled_json.dumps({"run":str(destination),"report_sha256":_m4_verify_td_basin_storage_compiled_file_sha256(destination/"report.json")}),flush=True)

def run_compiled_cli():
    parser=_m4_verify_td_basin_storage_compiled_argparse.ArgumentParser()
    parser.add_argument("--acceptance",type=_m4_verify_td_basin_storage_compiled_Path,required=True)
    parser.add_argument("--acceptance-sha256",required=True)
    arguments=parser.parse_args()
    compiled_verify(compiled_ROOT/"verification/td-basin-generation"/("A-compiled-execution-"+_m4_verify_td_basin_storage_compiled_datetime.now(_m4_verify_td_basin_storage_compiled_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),arguments.acceptance,arguments.acceptance_sha256)

# --- tools/verify_td_basin_storage_compiled_ordinary_stages.py:8 ---
compiled_ordinary_stages_ROOT=_m4_verify_td_basin_storage_compiled_ordinary_stages_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_compiled_ordinary_stages.py:9 ---
_m4_verify_td_basin_storage_compiled_ordinary_stages_sys.path.insert(0,str(compiled_ordinary_stages_ROOT))

# --- tools/verify_td_basin_storage_compiled_ordinary_stages.py:24 ---
compiled_ordinary_stages_BASELINE=compiled_ordinary_stages_ROOT/"verification/td-basin-generation/A-storage-continuation-20261002T110815168692Z"

# --- tools/verify_td_basin_storage_compiled_ordinary_stages.py:27 ---
def compiled_ordinary_stages_write(path,value):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_compiled_ordinary_stages_publish_bytes
    _m4_verify_td_basin_storage_compiled_ordinary_stages_publish_bytes(path,_m4_verify_td_basin_storage_compiled_ordinary_stages_json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_compiled_ordinary_stages.py:31 ---
def compiled_ordinary_stages_verify(destination,acceptance_path,acceptance_sha256):
    from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as _m4_verify_td_basin_storage_compiled_ordinary_stages_load_checkpoint
    from terrain_pipeline.basin_storage import compiled_save_storage as _m4_verify_td_basin_storage_compiled_ordinary_stages_save_storage
    from terrain_pipeline.basin_storage import compiled_validate_checkpoint as _m4_verify_td_basin_storage_compiled_ordinary_stages_validate_v9_checkpoint
    from terrain_pipeline.basin_storage import compileddriver_simulate as _m4_verify_td_basin_storage_compiled_ordinary_stages_simulate_basin_storage
    from terrain_pipeline.basin_storage import compiledio_save_checkpoint as _m4_verify_td_basin_storage_compiled_ordinary_stages_save_checkpoint
    from terrain_pipeline.basin_storage import continuation_load_storage as _m4_verify_td_basin_storage_compiled_ordinary_stages_load_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_compiled_ordinary_stages_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256
    from terrain_pipeline.common_infra import identity as _m4_verify_td_basin_storage_compiled_ordinary_stages_identity
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_compiled_ordinary_stages_audit_storage
    from tools.publish_td_accepted_review import accepted_inputs as _m4_verify_td_basin_storage_compiled_ordinary_stages_accepted_inputs
    from tools.verify_basin_storage import threshold_storage_HIERARCHY as _m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_IDENTITY as _m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY_IDENTITY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_SHA256 as _m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY_SHA256
    if _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(acceptance_path)!=acceptance_sha256:
        raise ValueError("external acceptance SHA mismatch")
    acceptance=_m4_verify_td_basin_storage_compiled_ordinary_stages_accepted_inputs(acceptance_path,acceptance_sha256)
    index=compiled_ordinary_stages_BASELINE/"index.json"
    if not index.exists():
        raise ValueError("complete frozen v8 index required; do not overlap current heavy job")
    resource_path=compiled_ordinary_stages_BASELINE/"resource.json"
    resource_pin=acceptance["acceptance_arguments"]["execution_resource_record"]
    if _m4_verify_td_basin_storage_compiled_ordinary_stages_Path(resource_pin["path"]).resolve()!=resource_path.resolve() or _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted execution resource external pin mismatch")
    resource=_m4_verify_td_basin_storage_compiled_ordinary_stages_json.loads(resource_path.read_text(encoding="utf-8"))
    baseline_index=_m4_verify_td_basin_storage_compiled_ordinary_stages_json.loads(index.read_text(encoding="utf-8"))
    index_sha=_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(index)
    if acceptance.get("input_index_sha256")!=index_sha or _m4_verify_td_basin_storage_compiled_ordinary_stages_Path(acceptance.get("input_index","")).resolve()!=index.resolve():
        raise ValueError("external acceptance does not bind this baseline index")
    if resource.get("index_sha256")!=index_sha or resource.get("complete") is not True or resource.get("scope")!="complete ordinary+strong both steps execution" or max(resource["peak_rss_bytes"],resource["peak_private_bytes"])>1073741824 or baseline_index.get("all_numerical_gates_passed") is not True:
        raise ValueError("complete accepted v8 resource/numerical reference required")
    frozen=baseline_index["code_sha256"]
    if not _m4_recorded_code_matches(frozen) or _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(_m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY)!=_m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY_SHA256:
        raise ValueError("baseline frozen reference changed")
    code_names=('terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
                'terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
                'terrain_pipeline/basin_storage.py','tools/verify_basin_storage_execution.py',
                "tools/publish_td_accepted_review.py")
    code={name:_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(compiled_ordinary_stages_ROOT/name) for name in code_names}
    hierarchy=_m4_verify_td_basin_storage_compiled_ordinary_stages_load_basin_hierarchy(_m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY,expected_sha256=_m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY_SHA256,expected_identity=_m4_verify_td_basin_storage_compiled_ordinary_stages_HIERARCHY_IDENTITY)
    references={}
    for hour in (5,23):
        for step in (2.5,1.25):
            path=compiled_ordinary_stages_BASELINE/f"ordinary-{step:g}s/hour-{hour:02d}/report.json"
            page=baseline_index["scenarios"]["ordinary"]["pages"][str(step)][hour]
            page_report=_m4_verify_td_basin_storage_compiled_ordinary_stages_json.loads(path.read_text(encoding="utf-8"))
            if page_report["storage"]!=page["storage"] or page_report["checkpoint"]!=page["checkpoint"]:
                raise ValueError("stage report differs from externally accepted page pins")
            previous=baseline_index["scenarios"]["ordinary"]["pages"][str(step)][hour-1]["checkpoint"]
            references[f"{hour}-{step}"]={"report_sha256":_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(path),"report":_m4_verify_td_basin_storage_compiled_ordinary_stages_json.loads(path.read_text(encoding="utf-8")),"previous_checkpoint":previous,"hour":hour,"step":step}
    compiled_ordinary_stages_write(destination/"run-inputs.json",{"scope":"originalTD peak and late-recession hours only; execution equivalence, not new hydraulic refinement",
        "profile":"v9-compiled-hour-loop-v8-equivalent-v1","reference_index_sha256":_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(index),
        "references":references,"code_sha256":code,"external_acceptance":{"path":str(acceptance_path),"sha256":acceptance_sha256},"reference_resource_sha256":_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(resource_path),"reference_frozen_code":frozen,"max_job_bytes":1073741824,"steps_s":[2.5,1.25]})
    records={}
    rain=_m4_verify_td_basin_storage_compiled_ordinary_stages_np.zeros(24);rain[:6]=10
    forcing_id=_m4_verify_td_basin_storage_compiled_ordinary_stages_identity({"rain_mm_h":rain},{"dt_s":3600.})
    for label,entry in references.items():
        step,hour=entry["step"],entry["hour"]
        previous=_m4_verify_td_basin_storage_compiled_ordinary_stages_load_checkpoint(**entry["previous_checkpoint"])
        converted_metadata={**previous["metadata"],"execution_profile":"v9-compiled-hour-loop-v8-equivalent-v1"}
        converted={"arrays":previous["arrays"],"metadata":converted_metadata,"identity_sha256":_m4_verify_td_basin_storage_compiled_ordinary_stages_identity(previous["arrays"],converted_metadata)}
        _m4_verify_td_basin_storage_compiled_ordinary_stages_validate_v9_checkpoint(converted)
        compiled_ordinary_stages_write(destination/f"conversion-{label}.json",{"source_external_pin":entry["previous_checkpoint"],"new_identity":converted["identity_sha256"],"change":"execution_profile only; all states/errors/cumulative unchanged","source_identity":previous["identity_sha256"]})
        began=_m4_verify_td_basin_storage_compiled_ordinary_stages_time.perf_counter()
        result=_m4_verify_td_basin_storage_compiled_ordinary_stages_simulate_basin_storage(hierarchy,rain[hour:hour+1],parameters={"substep_s":step},forcing_identity=forcing_id,full_rain_mm_h=rain,checkpoint=converted)
        elapsed=_m4_verify_td_basin_storage_compiled_ordinary_stages_time.perf_counter()-began
        directory=destination/f"ordinary-hour{hour+1}-{step:g}s"
        _m4_verify_td_basin_storage_compiled_ordinary_stages_save_storage(directory/"storage.npz",result["storage"])
        _m4_verify_td_basin_storage_compiled_ordinary_stages_save_checkpoint(directory/"checkpoint.npz",result["checkpoint"])
        checks=_m4_verify_td_basin_storage_compiled_ordinary_stages_audit_storage(result["storage"]["arrays"],result["storage"]["metadata"])
        reference=entry["report"]
        differences={}
        passed=True
        for role,loader in (("storage",_m4_verify_td_basin_storage_compiled_ordinary_stages_load_storage),("checkpoint",_m4_verify_td_basin_storage_compiled_ordinary_stages_load_checkpoint)):
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
                    ok=_m4_verify_td_basin_storage_compiled_ordinary_stages_np.array_equal(value,expected)
                elif "duration" in key or "active_" in key:
                    ok=maximum<=1e-8
                elif key in ("depth_m","soil_mm","fast_mm","slow_mm") or key.startswith("error_"):
                    ok=maximum<=(1e-9 if key in ("soil_mm","fast_mm","slow_mm","error_soil","error_fast","error_slow") else 1e-12)
                elif value.dtype.kind in "biu":
                    ok=_m4_verify_td_basin_storage_compiled_ordinary_stages_np.array_equal(value,expected)
                else:
                    ok=bool(_m4_verify_td_basin_storage_compiled_ordinary_stages_np.all(abs(value-expected)<=1e-6+1e-10*(abs(value)+abs(expected))))
                role_differences[key]={"max_difference":maximum,"bit_equal":bool(_m4_verify_td_basin_storage_compiled_ordinary_stages_np.array_equal(value,expected)),"passed":bool(ok)}
                passed=passed and bool(ok)
            differences[role]=role_differences
            del saved
        memory=_m4_verify_td_basin_storage_compiled_ordinary_stages_psutil.Process().memory_info()
        resource={"peak_rss_bytes":int(getattr(memory,"peak_wset",memory.rss)),
                  "peak_private_bytes":int(max(getattr(memory,"private",memory.vms),getattr(memory,"peak_pagefile",0)))}
        passed=passed and max(resource.values())<=1073741824
        record={"elapsed_s":elapsed,"reference_elapsed_s":reference["elapsed_s"],"resource":resource,"all_equivalence_checks_passed":passed,
            "field_differences":differences,"water_audit":checks,"storage_sha256":_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(directory/"storage.npz"),
            "storage_identity":result["storage"]["identity_sha256"],"checkpoint_sha256":_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(directory/"checkpoint.npz"),
            "checkpoint_identity":result["checkpoint"]["identity_sha256"],"hydraulic_ready":False,"transient_converged":False}
        compiled_ordinary_stages_write(directory/"report.json",record)
        records[label]=record
        del result,previous,converted
        print(_m4_verify_td_basin_storage_compiled_ordinary_stages_json.dumps({"step":step,"elapsed_s":elapsed,"passed":passed,"resource":resource}),flush=True)
    if any(_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(compiled_ordinary_stages_ROOT/name)!=sha for name,sha in code.items()):
        raise ValueError("compiled execution frozen code changed")
    if _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(acceptance_path)!=acceptance_sha256 or _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(index)!=index_sha or not _m4_recorded_code_matches(frozen) or _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(resource_path)!=_m4_verify_td_basin_storage_compiled_ordinary_stages_json.loads((destination/"run-inputs.json").read_text(encoding="utf-8"))["reference_resource_sha256"]:
        raise ValueError("reference changed during compiled execution probe")
    _m4_verify_td_basin_storage_compiled_ordinary_stages_accepted_inputs(acceptance_path,acceptance_sha256)
    for entry in references.values():
        for pin in (entry["previous_checkpoint"],entry["report"]["storage"],entry["report"]["checkpoint"]):
            if _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(pin["path"])!=pin["expected_sha256"]:
                raise ValueError("stage source pin changed during execution")
    if _m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted resource changed during probe")
    compiled_ordinary_stages_write(destination/"report.json",{"scope":"peak and late-recession execution equivalence only","runs":records,"code_sha256":code,
        "all_passed":all(record["all_equivalence_checks_passed"] for record in records.values()),"hydraulic_ready":False,"publishable":False})
    print(_m4_verify_td_basin_storage_compiled_ordinary_stages_json.dumps({"run":str(destination),"report_sha256":_m4_verify_td_basin_storage_compiled_ordinary_stages_file_sha256(destination/"report.json")}),flush=True)

def run_compiled_ordinary_stages_cli():
    parser=_m4_verify_td_basin_storage_compiled_ordinary_stages_argparse.ArgumentParser()
    parser.add_argument("--acceptance",type=_m4_verify_td_basin_storage_compiled_ordinary_stages_Path,required=True)
    parser.add_argument("--acceptance-sha256",required=True)
    arguments=parser.parse_args()
    compiled_ordinary_stages_verify(compiled_ordinary_stages_ROOT/"verification/td-basin-generation"/("A-compiled-ordinary-stages-"+_m4_verify_td_basin_storage_compiled_ordinary_stages_datetime.now(_m4_verify_td_basin_storage_compiled_ordinary_stages_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),arguments.acceptance,arguments.acceptance_sha256)

# --- tools/verify_td_basin_storage_compiled_stages.py:8 ---
compiled_stages_ROOT=_m4_verify_td_basin_storage_compiled_stages_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_compiled_stages.py:9 ---
_m4_verify_td_basin_storage_compiled_stages_sys.path.insert(0,str(compiled_stages_ROOT))

# --- tools/verify_td_basin_storage_compiled_stages.py:24 ---
compiled_stages_BASELINE=compiled_stages_ROOT/"verification/td-basin-generation/A-storage-continuation-20261002T110815168692Z"

# --- tools/verify_td_basin_storage_compiled_stages.py:27 ---
def compiled_stages_write(path,value):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_compiled_stages_publish_bytes
    _m4_verify_td_basin_storage_compiled_stages_publish_bytes(path,_m4_verify_td_basin_storage_compiled_stages_json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_compiled_stages.py:31 ---
def compiled_stages_verify(destination,acceptance_path,acceptance_sha256):
    from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as _m4_verify_td_basin_storage_compiled_stages_load_checkpoint
    from terrain_pipeline.basin_storage import compiled_save_storage as _m4_verify_td_basin_storage_compiled_stages_save_storage
    from terrain_pipeline.basin_storage import compiled_validate_checkpoint as _m4_verify_td_basin_storage_compiled_stages_validate_v9_checkpoint
    from terrain_pipeline.basin_storage import compileddriver_simulate as _m4_verify_td_basin_storage_compiled_stages_simulate_basin_storage
    from terrain_pipeline.basin_storage import compiledio_save_checkpoint as _m4_verify_td_basin_storage_compiled_stages_save_checkpoint
    from terrain_pipeline.basin_storage import continuation_load_storage as _m4_verify_td_basin_storage_compiled_stages_load_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_compiled_stages_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_compiled_stages_file_sha256
    from terrain_pipeline.common_infra import identity as _m4_verify_td_basin_storage_compiled_stages_identity
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_compiled_stages_audit_storage
    from tools.publish_td_accepted_review import accepted_inputs as _m4_verify_td_basin_storage_compiled_stages_accepted_inputs
    from tools.verify_basin_storage import threshold_storage_HIERARCHY as _m4_verify_td_basin_storage_compiled_stages_HIERARCHY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_IDENTITY as _m4_verify_td_basin_storage_compiled_stages_HIERARCHY_IDENTITY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_SHA256 as _m4_verify_td_basin_storage_compiled_stages_HIERARCHY_SHA256
    if _m4_verify_td_basin_storage_compiled_stages_file_sha256(acceptance_path)!=acceptance_sha256:
        raise ValueError("external acceptance SHA mismatch")
    acceptance=_m4_verify_td_basin_storage_compiled_stages_accepted_inputs(acceptance_path,acceptance_sha256)
    index=compiled_stages_BASELINE/"index.json"
    if not index.exists():
        raise ValueError("complete frozen v8 index required; do not overlap current heavy job")
    resource_path=compiled_stages_BASELINE/"resource.json"
    resource_pin=acceptance["acceptance_arguments"]["execution_resource_record"]
    if _m4_verify_td_basin_storage_compiled_stages_Path(resource_pin["path"]).resolve()!=resource_path.resolve() or _m4_verify_td_basin_storage_compiled_stages_file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted execution resource external pin mismatch")
    resource=_m4_verify_td_basin_storage_compiled_stages_json.loads(resource_path.read_text(encoding="utf-8"))
    baseline_index=_m4_verify_td_basin_storage_compiled_stages_json.loads(index.read_text(encoding="utf-8"))
    index_sha=_m4_verify_td_basin_storage_compiled_stages_file_sha256(index)
    if acceptance.get("input_index_sha256")!=index_sha or _m4_verify_td_basin_storage_compiled_stages_Path(acceptance.get("input_index","")).resolve()!=index.resolve():
        raise ValueError("external acceptance does not bind this baseline index")
    if resource.get("index_sha256")!=index_sha or resource.get("complete") is not True or resource.get("scope")!="complete ordinary+strong both steps execution" or max(resource["peak_rss_bytes"],resource["peak_private_bytes"])>1073741824 or baseline_index.get("all_numerical_gates_passed") is not True:
        raise ValueError("complete accepted v8 resource/numerical reference required")
    frozen=baseline_index["code_sha256"]
    if not _m4_recorded_code_matches(frozen) or _m4_verify_td_basin_storage_compiled_stages_file_sha256(_m4_verify_td_basin_storage_compiled_stages_HIERARCHY)!=_m4_verify_td_basin_storage_compiled_stages_HIERARCHY_SHA256:
        raise ValueError("baseline frozen reference changed")
    code_names=('terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
                'terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
                'terrain_pipeline/basin_storage.py','tools/verify_basin_storage_execution.py',
                "tools/publish_td_accepted_review.py")
    code={name:_m4_verify_td_basin_storage_compiled_stages_file_sha256(compiled_stages_ROOT/name) for name in code_names}
    hierarchy=_m4_verify_td_basin_storage_compiled_stages_load_basin_hierarchy(_m4_verify_td_basin_storage_compiled_stages_HIERARCHY,expected_sha256=_m4_verify_td_basin_storage_compiled_stages_HIERARCHY_SHA256,expected_identity=_m4_verify_td_basin_storage_compiled_stages_HIERARCHY_IDENTITY)
    references={}
    for hour in (5,23):
        for step in (2.5,1.25):
            path=compiled_stages_BASELINE/f"strong-{step:g}s/hour-{hour:02d}/report.json"
            page=baseline_index["scenarios"]["strong"]["pages"][str(step)][hour]
            page_report=_m4_verify_td_basin_storage_compiled_stages_json.loads(path.read_text(encoding="utf-8"))
            if page_report["storage"]!=page["storage"] or page_report["checkpoint"]!=page["checkpoint"]:
                raise ValueError("stage report differs from externally accepted page pins")
            previous=baseline_index["scenarios"]["strong"]["pages"][str(step)][hour-1]["checkpoint"]
            references[f"{hour}-{step}"]={"report_sha256":_m4_verify_td_basin_storage_compiled_stages_file_sha256(path),"report":_m4_verify_td_basin_storage_compiled_stages_json.loads(path.read_text(encoding="utf-8")),"previous_checkpoint":previous,"hour":hour,"step":step}
    compiled_stages_write(destination/"run-inputs.json",{"scope":"originalTD peak and late-recession hours only; execution equivalence, not new hydraulic refinement",
        "profile":"v9-compiled-hour-loop-v8-equivalent-v1","reference_index_sha256":_m4_verify_td_basin_storage_compiled_stages_file_sha256(index),
        "references":references,"code_sha256":code,"external_acceptance":{"path":str(acceptance_path),"sha256":acceptance_sha256},"reference_resource_sha256":_m4_verify_td_basin_storage_compiled_stages_file_sha256(resource_path),"reference_frozen_code":frozen,"max_job_bytes":1073741824,"steps_s":[2.5,1.25]})
    records={}
    rain=_m4_verify_td_basin_storage_compiled_stages_np.zeros(24);rain[:6]=30
    forcing_id=_m4_verify_td_basin_storage_compiled_stages_identity({"rain_mm_h":rain},{"dt_s":3600.})
    for label,entry in references.items():
        step,hour=entry["step"],entry["hour"]
        previous=_m4_verify_td_basin_storage_compiled_stages_load_checkpoint(**entry["previous_checkpoint"])
        converted_metadata={**previous["metadata"],"execution_profile":"v9-compiled-hour-loop-v8-equivalent-v1"}
        converted={"arrays":previous["arrays"],"metadata":converted_metadata,"identity_sha256":_m4_verify_td_basin_storage_compiled_stages_identity(previous["arrays"],converted_metadata)}
        _m4_verify_td_basin_storage_compiled_stages_validate_v9_checkpoint(converted)
        compiled_stages_write(destination/f"conversion-{label}.json",{"source_external_pin":entry["previous_checkpoint"],"new_identity":converted["identity_sha256"],"change":"execution_profile only; all states/errors/cumulative unchanged","source_identity":previous["identity_sha256"]})
        began=_m4_verify_td_basin_storage_compiled_stages_time.perf_counter()
        result=_m4_verify_td_basin_storage_compiled_stages_simulate_basin_storage(hierarchy,rain[hour:hour+1],parameters={"substep_s":step},forcing_identity=forcing_id,full_rain_mm_h=rain,checkpoint=converted)
        elapsed=_m4_verify_td_basin_storage_compiled_stages_time.perf_counter()-began
        directory=destination/f"strong-hour{hour+1}-{step:g}s"
        _m4_verify_td_basin_storage_compiled_stages_save_storage(directory/"storage.npz",result["storage"])
        _m4_verify_td_basin_storage_compiled_stages_save_checkpoint(directory/"checkpoint.npz",result["checkpoint"])
        checks=_m4_verify_td_basin_storage_compiled_stages_audit_storage(result["storage"]["arrays"],result["storage"]["metadata"])
        reference=entry["report"]
        differences={}
        passed=True
        for role,loader in (("storage",_m4_verify_td_basin_storage_compiled_stages_load_storage),("checkpoint",_m4_verify_td_basin_storage_compiled_stages_load_checkpoint)):
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
                    ok=_m4_verify_td_basin_storage_compiled_stages_np.array_equal(value,expected)
                elif "duration" in key or "active_" in key:
                    ok=maximum<=1e-8
                elif key in ("depth_m","soil_mm","fast_mm","slow_mm") or key.startswith("error_"):
                    ok=maximum<=(1e-9 if key in ("soil_mm","fast_mm","slow_mm","error_soil","error_fast","error_slow") else 1e-12)
                elif value.dtype.kind in "biu":
                    ok=_m4_verify_td_basin_storage_compiled_stages_np.array_equal(value,expected)
                else:
                    ok=bool(_m4_verify_td_basin_storage_compiled_stages_np.all(abs(value-expected)<=1e-6+1e-10*(abs(value)+abs(expected))))
                role_differences[key]={"max_difference":maximum,"bit_equal":bool(_m4_verify_td_basin_storage_compiled_stages_np.array_equal(value,expected)),"passed":bool(ok)}
                passed=passed and bool(ok)
            differences[role]=role_differences
            del saved
        memory=_m4_verify_td_basin_storage_compiled_stages_psutil.Process().memory_info()
        resource={"peak_rss_bytes":int(getattr(memory,"peak_wset",memory.rss)),
                  "peak_private_bytes":int(max(getattr(memory,"private",memory.vms),getattr(memory,"peak_pagefile",0)))}
        passed=passed and max(resource.values())<=1073741824
        record={"elapsed_s":elapsed,"reference_elapsed_s":reference["elapsed_s"],"resource":resource,"all_equivalence_checks_passed":passed,
            "field_differences":differences,"water_audit":checks,"storage_sha256":_m4_verify_td_basin_storage_compiled_stages_file_sha256(directory/"storage.npz"),
            "storage_identity":result["storage"]["identity_sha256"],"checkpoint_sha256":_m4_verify_td_basin_storage_compiled_stages_file_sha256(directory/"checkpoint.npz"),
            "checkpoint_identity":result["checkpoint"]["identity_sha256"],"hydraulic_ready":False,"transient_converged":False}
        compiled_stages_write(directory/"report.json",record)
        records[label]=record
        del result,previous,converted
        print(_m4_verify_td_basin_storage_compiled_stages_json.dumps({"step":step,"elapsed_s":elapsed,"passed":passed,"resource":resource}),flush=True)
    if any(_m4_verify_td_basin_storage_compiled_stages_file_sha256(compiled_stages_ROOT/name)!=sha for name,sha in code.items()):
        raise ValueError("compiled execution frozen code changed")
    if _m4_verify_td_basin_storage_compiled_stages_file_sha256(acceptance_path)!=acceptance_sha256 or _m4_verify_td_basin_storage_compiled_stages_file_sha256(index)!=index_sha or not _m4_recorded_code_matches(frozen) or _m4_verify_td_basin_storage_compiled_stages_file_sha256(resource_path)!=_m4_verify_td_basin_storage_compiled_stages_json.loads((destination/"run-inputs.json").read_text(encoding="utf-8"))["reference_resource_sha256"]:
        raise ValueError("reference changed during compiled execution probe")
    _m4_verify_td_basin_storage_compiled_stages_accepted_inputs(acceptance_path,acceptance_sha256)
    for entry in references.values():
        for pin in (entry["previous_checkpoint"],entry["report"]["storage"],entry["report"]["checkpoint"]):
            if _m4_verify_td_basin_storage_compiled_stages_file_sha256(pin["path"])!=pin["expected_sha256"]:
                raise ValueError("stage source pin changed during execution")
    if _m4_verify_td_basin_storage_compiled_stages_file_sha256(resource_path)!=resource_pin["expected_sha256"]:
        raise ValueError("accepted resource changed during probe")
    compiled_stages_write(destination/"report.json",{"scope":"peak and late-recession execution equivalence only","runs":records,"code_sha256":code,
        "all_passed":all(record["all_equivalence_checks_passed"] for record in records.values()),"hydraulic_ready":False,"publishable":False})
    print(_m4_verify_td_basin_storage_compiled_stages_json.dumps({"run":str(destination),"report_sha256":_m4_verify_td_basin_storage_compiled_stages_file_sha256(destination/"report.json")}),flush=True)

def run_compiled_stages_cli():
    parser=_m4_verify_td_basin_storage_compiled_stages_argparse.ArgumentParser()
    parser.add_argument("--acceptance",type=_m4_verify_td_basin_storage_compiled_stages_Path,required=True)
    parser.add_argument("--acceptance-sha256",required=True)
    arguments=parser.parse_args()
    compiled_stages_verify(compiled_stages_ROOT/"verification/td-basin-generation"/("A-compiled-stages-"+_m4_verify_td_basin_storage_compiled_stages_datetime.now(_m4_verify_td_basin_storage_compiled_stages_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),arguments.acceptance,arguments.acceptance_sha256)

# --- tools/verify_td_basin_storage_continuation.py:10 ---
hour_pages_ROOT = _m4_verify_td_basin_storage_continuation_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_continuation.py:11 ---
_m4_verify_td_basin_storage_continuation_sys.path.insert(0, str(hour_pages_ROOT))

# --- tools/verify_td_basin_storage_continuation.py:28 ---
def hour_pages_write(path, value):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_continuation_publish_bytes
    _m4_verify_td_basin_storage_continuation_publish_bytes(path, _m4_verify_td_basin_storage_continuation_json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_continuation.py:32 ---
def hour_pages_pin(path, result):
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_continuation_file_sha256
    return {"path": str(path), "expected_sha256": _m4_verify_td_basin_storage_continuation_file_sha256(path), "expected_identity": result["identity_sha256"]}

# --- tools/verify_td_basin_storage_continuation.py:36 ---
def hour_pages_verify(destination, coarse_step, fine_step):
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_basin_storage_continuation_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_continuation_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import checkpoint_load_checkpoint as _m4_verify_td_basin_storage_continuation_load_checkpoint
    from terrain_pipeline.basin_storage import checkpointio_save_checkpoint as _m4_verify_td_basin_storage_continuation_save_checkpoint
    from terrain_pipeline.basin_storage import continuation_load_storage as _m4_verify_td_basin_storage_continuation_load_storage
    from terrain_pipeline.basin_storage import continuation_save_storage as _m4_verify_td_basin_storage_continuation_save_storage
    from terrain_pipeline.basin_storage import continuation_simulate as _m4_verify_td_basin_storage_continuation_simulate_basin_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_continuation_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_continuation_file_sha256
    from terrain_pipeline.common_infra import identity as _m4_verify_td_basin_storage_continuation_identity
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_continuation_audit_storage
    from tools.verify_basin_storage import compensated_ssprk2_compare as _m4_verify_td_basin_storage_continuation_compare
    from tools.verify_basin_storage import threshold_storage_HIERARCHY as _m4_verify_td_basin_storage_continuation_HIERARCHY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_IDENTITY as _m4_verify_td_basin_storage_continuation_HIERARCHY_IDENTITY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_SHA256 as _m4_verify_td_basin_storage_continuation_HIERARCHY_SHA256
    if destination.exists():
        raise FileExistsError(destination)
    if any(not _m4_verify_td_basin_storage_continuation_math.isfinite(step) or step<=0 or 3600/step != int(3600/step) for step in (coarse_step,fine_step)) or coarse_step != 2*fine_step:
        raise ValueError("finite exact halving and integer hourly substeps required")
    if _m4_verify_td_basin_storage_continuation_file_sha256(_m4_verify_td_basin_storage_continuation_PRIMARY_PATH)!=_m4_verify_td_basin_storage_continuation_PRIMARY_SHA256:
        raise ValueError("primary source SHA mismatch")
    hierarchy = _m4_verify_td_basin_storage_continuation_load_basin_hierarchy(_m4_verify_td_basin_storage_continuation_HIERARCHY, expected_sha256=_m4_verify_td_basin_storage_continuation_HIERARCHY_SHA256, expected_identity=_m4_verify_td_basin_storage_continuation_HIERARCHY_IDENTITY)
    faces = len(hierarchy["arrays"]["face_cells"])
    code_names = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/runoff.py', 'terrain_pipeline/basin_topology.py',
                  'terrain_pipeline/common_infra.py', 'terrain_pipeline/basin_storage.py',
                  'tools/verify_basin_storage_execution.py', "tools/audit_td_basin_generation.py",
                  'tools/verify_basin_storage.py', 'tools/verify_basin_storage.py')
    code = {name: _m4_verify_td_basin_storage_continuation_file_sha256(hour_pages_ROOT/name) for name in code_names}
    budgets = {str(step): {"chunk_face_steps": round(3600/step)*faces,
                          "global_face_steps_per_scenario": 24*round(3600/step)*faces} for step in (coarse_step,fine_step)}
    if any(item["chunk_face_steps"] > 6_000_000_000 for item in budgets.values()):
        raise ValueError("hourly chunk budget exceeded")
    hour_pages_write(destination/"run-inputs.json", {"profile":"v8-hour-pages-v7-SSPRK2", "steps_s":[coarse_step,fine_step],
        "hierarchy":{"path":str(_m4_verify_td_basin_storage_continuation_HIERARCHY),"sha256":_m4_verify_td_basin_storage_continuation_HIERARCHY_SHA256,"identity":_m4_verify_td_basin_storage_continuation_HIERARCHY_IDENTITY},
        "forcing":"ordinary6h10mm/h or strong6h30mm/h then18h0; initial zero depth and default runoff",
        "budgets":budgets,"chunk_max_work_face_steps":6_000_000_000,"job_max_bytes":1073741824,
        "global_budget_semantics":"global sum explicitly exceeds chunk cap; independently finite 24 hourly pages per scenario/step",
        "depth_gate_m":.001,"receiver_gate":.01,"code_sha256":code})
    hour_pages_write(destination/"execution-code.json", {"code_sha256":code,"sources":{name:(hour_pages_ROOT/name).read_text(encoding="utf-8") for name in code_names[:4]},
        "checkpoint":"all four states plus compensation; hourly forcing ledger reset only; cumulative directional/routed evidence retained"})
    records = {}
    process = _m4_verify_td_basin_storage_continuation_psutil.Process()
    for scenario in ("strong","ordinary"):
        rain = _m4_verify_td_basin_storage_continuation_np.zeros(24)
        rain[:6] = 30 if scenario=="strong" else 10
        forcing_id = _m4_verify_td_basin_storage_continuation_identity({"rain_mm_h":rain},{"dt_s":3600.})
        hour_pages_write(destination/(scenario+"-forcing.json"),{"rain_mm_h":rain.tolist(),"dt_s":3600.,"identity":forcing_id})
        scenario_records = {}
        for step in (coarse_step,fine_step):
            checkpoint = None
            pages = []
            for hour in range(24):
                began = _m4_verify_td_basin_storage_continuation_time.perf_counter()
                try:
                    result = _m4_verify_td_basin_storage_continuation_simulate_basin_storage(hierarchy,rain[hour:hour+1],parameters={"substep_s":step},
                                                    checkpoint=checkpoint,forcing_identity=forcing_id,full_rain_mm_h=rain)
                except Exception as error:
                    hour_pages_write(destination/"failure.json",{"scenario":scenario,"step_s":step,"hour":hour,"reason":str(error),"completed_pages":pages,
                        "hydraulic_ready":False,"transient_converged":False,"publishable":False})
                    raise
                storage = result["storage"]
                directory = destination/f"{scenario}-{step:g}s"/f"hour-{hour:02d}"
                if checkpoint is not None:
                    for key in ("depth_m","soil_mm","fast_mm","slow_mm"):
                        if not _m4_verify_td_basin_storage_continuation_np.array_equal(storage["arrays"][key][0],checkpoint["arrays"][key]):
                            raise ValueError("page initial state checkpoint mismatch")
                for key in ("face_forward_m3","face_reverse_m3","active_forward_s","active_reverse_s","routed_volume_m3","wet_duration_s"):
                    previous = 0 if checkpoint is None else checkpoint["arrays"]["cumulative_"+key]
                    if not _m4_verify_td_basin_storage_continuation_np.allclose(result["checkpoint"]["arrays"]["cumulative_"+key]-previous,storage["arrays"][key],rtol=1e-12,atol=1e-9):
                        raise ValueError("checkpoint cumulative delta mismatch")
                memory = process.memory_info()
                peak = int(getattr(memory,"peak_wset",memory.rss))
                if peak > 1073741824:
                    raise MemoryError("continuation job exceeded1GiB")
                _m4_verify_td_basin_storage_continuation_save_storage(directory/"storage.npz",storage)
                _m4_verify_td_basin_storage_continuation_save_checkpoint(directory/"checkpoint.npz",result["checkpoint"])
                try:
                    audit = _m4_verify_td_basin_storage_continuation_audit_storage(storage["arrays"],storage["metadata"])
                except Exception as error:
                    hour_pages_write(directory/"failure.json",{"reason":str(error),"storage":hour_pages_pin(directory/"storage.npz",storage),"checkpoint":hour_pages_pin(directory/"checkpoint.npz",result["checkpoint"]),"hydraulic_ready":False,"publishable":False})
                    hour_pages_write(destination/"failure.json",{"scenario":scenario,"step_s":step,"hour":hour,"reason":str(error),"completed_pages":pages,"hydraulic_ready":False,"publishable":False})
                    raise
                record = {"hour":hour,"elapsed_s":_m4_verify_td_basin_storage_continuation_time.perf_counter()-began,"peak_bytes":peak,
                    "storage":hour_pages_pin(directory/"storage.npz",storage),"checkpoint":hour_pages_pin(directory/"checkpoint.npz",result["checkpoint"]),
                    "audit":audit,"forcing_identity":forcing_id,"chunk_work_face_steps":budgets[str(step)]["chunk_face_steps"]}
                hour_pages_write(directory/"report.json",record)
                checkpoint = _m4_verify_td_basin_storage_continuation_load_checkpoint(**record["checkpoint"])
                pages.append(record)
                del result,storage
                print(f"complete {scenario} {step}s hour{hour+1} elapsed{record['elapsed_s']:.2f}s peak{peak}",flush=True)
            scenario_records[str(step)] = pages
            if checkpoint["metadata"]["work_face_steps"] != budgets[str(step)]["global_face_steps_per_scenario"]:
                raise ValueError("global checkpoint work mismatch")
            del checkpoint
        comparisons = []
        for coarse_page,fine_page in zip(scenario_records[str(coarse_step)],scenario_records[str(fine_step)]):
            coarse = _m4_verify_td_basin_storage_continuation_load_storage(**coarse_page["storage"])
            fine = _m4_verify_td_basin_storage_continuation_load_storage(**fine_page["storage"])
            comparisons.append(_m4_verify_td_basin_storage_continuation_compare(coarse["arrays"],fine["arrays"]))
            del coarse,fine
        coarse_checkpoint = _m4_verify_td_basin_storage_continuation_load_checkpoint(**scenario_records[str(coarse_step)][-1]["checkpoint"])
        fine_checkpoint = _m4_verify_td_basin_storage_continuation_load_checkpoint(**scenario_records[str(fine_step)][-1]["checkpoint"])
        coarse_routed = coarse_checkpoint["arrays"]["cumulative_routed_volume_m3"]
        fine_routed = fine_checkpoint["arrays"]["cumulative_routed_volume_m3"]
        receiver = float(abs(coarse_routed-fine_routed).sum()/max(1e-12,fine_routed.sum()))
        maximum = max(item["max_saved_depth_difference_m"] for item in comparisons)
        record = {"pages":scenario_records,"hour_comparisons":comparisons,"max_saved_depth_difference_m":maximum,
                  "cumulative_receiver_relative_l1":receiver,"gate_passed":maximum<=.001 and receiver<=.01,
                  "scope":"all24 originalTD hourly states and cumulative actual receiver volumes",
                  "hydraulic_ready":False,"transient_converged":False,"publishable":False}
        hour_pages_write(destination/(scenario+"-comparison.json"),record)
        records[scenario]=record
        del coarse_checkpoint,fine_checkpoint
    if any(_m4_verify_td_basin_storage_continuation_file_sha256(hour_pages_ROOT/name)!=sha for name,sha in code.items()):
        raise ValueError("frozen continuation source changed")
    if _m4_verify_td_basin_storage_continuation_file_sha256(_m4_verify_td_basin_storage_continuation_PRIMARY_PATH)!=_m4_verify_td_basin_storage_continuation_PRIMARY_SHA256 or _m4_verify_td_basin_storage_continuation_file_sha256(_m4_verify_td_basin_storage_continuation_HIERARCHY)!=_m4_verify_td_basin_storage_continuation_HIERARCHY_SHA256:
        raise ValueError("final primary/hierarchy SHA mismatch")
    hour_pages_write(destination/"index.json",{"schema":"td-storage-hour-pages-index-v1","scenarios":records,"budgets":budgets,
        "code_sha256":code,"all_numerical_gates_passed":all(record["gate_passed"] for record in records.values()),
        "hydraulic_ready":False,"transient_converged":False,"publishable":False})
    hour_pages_write(destination/"final-pin.json",{"path":str(destination/"index.json"),"sha256":_m4_verify_td_basin_storage_continuation_file_sha256(destination/"index.json")})
    print(_m4_verify_td_basin_storage_continuation_json.dumps({"run":str(destination),"index_sha256":_m4_verify_td_basin_storage_continuation_file_sha256(destination/"index.json")}),flush=True)

def run_hour_pages_cli():
    parser = _m4_verify_td_basin_storage_continuation_argparse.ArgumentParser()
    parser.add_argument("--coarse-step",type=float,required=True)
    parser.add_argument("--fine-step",type=float,required=True)
    arguments = parser.parse_args()
    hour_pages_verify(hour_pages_ROOT/"verification/td-basin-generation"/("A-storage-continuation-"+_m4_verify_td_basin_storage_continuation_datetime.now(_m4_verify_td_basin_storage_continuation_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),arguments.coarse_step,arguments.fine_step)

# --- tools/verify_td_native_weather_storage.py:13 ---
native_weather_ROOT = _m4_verify_td_native_weather_storage_Path(__file__).resolve().parents[1]

# --- tools/verify_td_native_weather_storage.py:14 ---
_m4_verify_td_native_weather_storage_sys.path.insert(0, str(native_weather_ROOT))

# --- tools/verify_td_native_weather_storage.py:32 ---
def native_weather_write(path, value):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_native_weather_storage_publish_bytes
    _m4_verify_td_native_weather_storage_publish_bytes(path, _m4_verify_td_native_weather_storage_json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_native_weather_storage.py:36 ---
def native_weather_pin(path, result):
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_native_weather_storage_file_sha256
    return {"path": str(path), "expected_sha256": _m4_verify_td_native_weather_storage_file_sha256(path), "expected_identity": result["identity_sha256"]}

# --- tools/verify_td_native_weather_storage.py:40 ---
native_weather_THREAD_NAMES=("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS")

# --- tools/verify_td_native_weather_storage.py:43 ---
class NativeWeatherResourceMonitor:
    def __init__(self,process):
        self.process=process
        self.finished=_m4_verify_td_native_weather_storage_threading.Event()
        self.peak_rss=0
        self.peak_private=0
        self.samples=0
        self.error=None

    def sample(self):
        memory=self.process.memory_info()
        self.peak_rss=max(self.peak_rss,memory.rss,getattr(memory,"peak_wset",0))
        self.peak_private=max(self.peak_private,getattr(memory,"private",memory.vms),getattr(memory,"peak_pagefile",0))
        self.samples+=1

    def run(self):
        try:
            while not self.finished.wait(2):
                self.sample()
        except Exception as error:
            self.error=str(error)

    def start(self):
        self.sample()
        self.thread=_m4_verify_td_native_weather_storage_threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def stop(self):
        self.finished.set()
        self.thread.join()
        self.sample()

    def check(self):
        self.sample()
        if self.error or max(self.peak_rss,self.peak_private)>1073741824:
            raise MemoryError("weather history RSS/private budget or monitor failure")

    def record(self):
        return {"peak_rss_bytes":self.peak_rss,"peak_private_bytes":self.peak_private,"sample_count":self.samples,"sampling_interval_s":2,"monitor_error":self.error}

# --- tools/verify_td_native_weather_storage.py:84 ---
def native_weather_verify(destination, coarse_step, fine_step, weather_index, weather_index_sha256):
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_native_weather_storage_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_native_weather_storage_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import compiled_load_checkpoint as _m4_verify_td_native_weather_storage_load_checkpoint
    from terrain_pipeline.basin_storage import compiled_load_storage as _m4_verify_td_native_weather_storage_load_storage
    from terrain_pipeline.basin_storage import compiled_save_storage as _m4_verify_td_native_weather_storage_save_storage
    from terrain_pipeline.basin_storage import compileddriver_simulate as _m4_verify_td_native_weather_storage_simulate_basin_storage
    from terrain_pipeline.basin_storage import compiledio_save_checkpoint as _m4_verify_td_native_weather_storage_save_checkpoint
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_native_weather_storage_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_native_weather_storage_file_sha256
    from terrain_pipeline.td_native_weather_storage_inputs import load_weather_inputs as _m4_verify_td_native_weather_storage_load_weather_inputs
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_native_weather_storage_audit_storage
    from tools.verify_basin_storage import compensated_ssprk2_compare as _m4_verify_td_native_weather_storage_compare
    from tools.verify_basin_storage import threshold_storage_HIERARCHY as _m4_verify_td_native_weather_storage_HIERARCHY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_IDENTITY as _m4_verify_td_native_weather_storage_HIERARCHY_IDENTITY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_SHA256 as _m4_verify_td_native_weather_storage_HIERARCHY_SHA256
    if any(_m4_verify_td_native_weather_storage_os.environ.get(name)!="1" for name in native_weather_THREAD_NAMES):
        raise ValueError("explicit single-thread execution environment required")
    if destination.exists():
        raise FileExistsError(destination)
    if any(not _m4_verify_td_native_weather_storage_math.isfinite(step) or step<=0 or 3600/step != int(3600/step) for step in (coarse_step,fine_step)) or coarse_step != 2*fine_step:
        raise ValueError("finite exact halving and integer hourly substeps required")
    if _m4_verify_td_native_weather_storage_file_sha256(_m4_verify_td_native_weather_storage_PRIMARY_PATH)!=_m4_verify_td_native_weather_storage_PRIMARY_SHA256:
        raise ValueError("primary source SHA mismatch")
    hierarchy = _m4_verify_td_native_weather_storage_load_basin_hierarchy(_m4_verify_td_native_weather_storage_HIERARCHY, expected_sha256=_m4_verify_td_native_weather_storage_HIERARCHY_SHA256, expected_identity=_m4_verify_td_native_weather_storage_HIERARCHY_IDENTITY)
    weather = _m4_verify_td_native_weather_storage_load_weather_inputs(weather_index,expected_sha256=weather_index_sha256,hierarchy=hierarchy)
    faces = len(hierarchy["arrays"]["face_cells"])
    code_names = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/runoff.py', 'terrain_pipeline/basin_topology.py',
                  'terrain_pipeline/common_infra.py', 'terrain_pipeline/basin_storage.py',
                  "terrain_pipeline/td_native_weather_storage_inputs.py", 'terrain_pipeline/climate_forcing.py',
                  'terrain_pipeline/climate_forcing.py', 'tools/verify_basin_storage_execution.py',
                  "tools/audit_td_basin_generation.py", 'tools/verify_basin_storage.py', 'tools/verify_basin_storage.py')
    code = {name: _m4_verify_td_native_weather_storage_file_sha256(native_weather_ROOT/name) for name in code_names}
    budgets = {str(step): {"chunk_face_steps": round(3600/step)*faces,
                          "global_face_steps_per_scenario": 24*round(3600/step)*faces} for step in (coarse_step,fine_step)}
    if any(item["chunk_face_steps"] > 6_000_000_000 for item in budgets.values()):
        raise ValueError("hourly chunk budget exceeded")
    native_weather_write(destination/"run-inputs.json", {"schema":"td-v9-spatial-weather-run-inputs-v1", "profile":"v9-compiled-hour-loop-v8-equivalent-v1", "weather_index":weather["index_pin"], "weather_records":{name:case["record"] for name,case in weather["cases"].items()}, "forcing_identities":{name:case["forcing_identity"] for name,case in weather["cases"].items()}, "steps_s":[coarse_step,fine_step],
        "hierarchy":{"path":str(_m4_verify_td_native_weather_storage_HIERARCHY),"sha256":_m4_verify_td_native_weather_storage_HIERARCHY_SHA256,"identity":_m4_verify_td_native_weather_storage_HIERARCHY_IDENTITY},
        "forcing":"externally pinned native [24,z,x] interval means; initial zero depth and default runoff",
        "budgets":budgets,"chunk_max_work_face_steps":6_000_000_000,"job_max_bytes":1073741824,
        "global_budget_semantics":"global sum explicitly exceeds chunk cap; independently finite 24 hourly pages per scenario/step",
        "depth_gate_m":.001,"receiver_gate":.01,"code_sha256":code})
    native_weather_write(destination/"execution-code.json", {"code_sha256":code,"sources":{name:(native_weather_ROOT/name).read_text(encoding="utf-8") for name in code_names[:4]},
        "checkpoint":"all four states plus compensation; hourly forcing ledger reset only; cumulative directional/routed evidence retained"})
    records = {}
    process = _m4_verify_td_native_weather_storage_psutil.Process()
    monitor = NativeWeatherResourceMonitor(process)
    monitor.start()
    for scenario in ("eastward","westward"):
        case=weather["cases"][scenario]
        rain=case["rain_mm_h"]
        forcing_id=case["forcing_identity"]
        native_weather_write(destination/(scenario+"-forcing.json"),{"schema":"td-v9-spatial-weather-forcing-record-v1","weather_record":case["record"],"dt_s":3600.,"shape":list(rain.shape),"identity":forcing_id,"plan_identity":case["plan_identity"]})
        scenario_records = {}
        for step in (coarse_step,fine_step):
            checkpoint = None
            pages = []
            for hour in range(24):
                began = _m4_verify_td_native_weather_storage_time.perf_counter()
                try:
                    result = _m4_verify_td_native_weather_storage_simulate_basin_storage(hierarchy,rain[hour:hour+1],parameters={"substep_s":step},
                                                    checkpoint=checkpoint,forcing_identity=forcing_id,full_rain_mm_h=rain)
                except Exception as error:
                    native_weather_write(destination/"failure.json",{"scenario":scenario,"step_s":step,"hour":hour,"reason":str(error),"completed_pages":pages,
                        "hydraulic_ready":False,"transient_converged":False,"publishable":False})
                    raise
                storage = result["storage"]
                directory = destination/f"{scenario}-{step:g}s"/f"hour-{hour:02d}"
                if checkpoint is not None:
                    for key in ("depth_m","soil_mm","fast_mm","slow_mm"):
                        if not _m4_verify_td_native_weather_storage_np.array_equal(storage["arrays"][key][0],checkpoint["arrays"][key]):
                            raise ValueError("page initial state checkpoint mismatch")
                for key in ("face_forward_m3","face_reverse_m3","active_forward_s","active_reverse_s","routed_volume_m3","wet_duration_s"):
                    previous = 0 if checkpoint is None else checkpoint["arrays"]["cumulative_"+key]
                    if not _m4_verify_td_native_weather_storage_np.allclose(result["checkpoint"]["arrays"]["cumulative_"+key]-previous,storage["arrays"][key],rtol=1e-12,atol=1e-9):
                        raise ValueError("checkpoint cumulative delta mismatch")
                monitor.check()
                memory = process.memory_info()
                peak = int(getattr(memory,"peak_wset",memory.rss))
                if peak > 1073741824:
                    raise MemoryError("continuation job exceeded1GiB")
                _m4_verify_td_native_weather_storage_save_storage(directory/"storage.npz",storage)
                _m4_verify_td_native_weather_storage_save_checkpoint(directory/"checkpoint.npz",result["checkpoint"])
                try:
                    audit = _m4_verify_td_native_weather_storage_audit_storage(storage["arrays"],storage["metadata"])
                except Exception as error:
                    native_weather_write(directory/"failure.json",{"reason":str(error),"storage":native_weather_pin(directory/"storage.npz",storage),"checkpoint":native_weather_pin(directory/"checkpoint.npz",result["checkpoint"]),"hydraulic_ready":False,"publishable":False})
                    native_weather_write(destination/"failure.json",{"scenario":scenario,"step_s":step,"hour":hour,"reason":str(error),"completed_pages":pages,"hydraulic_ready":False,"publishable":False})
                    raise
                record = {"hour":hour,"elapsed_s":_m4_verify_td_native_weather_storage_time.perf_counter()-began,"peak_bytes":peak,
                    "storage":native_weather_pin(directory/"storage.npz",storage),"checkpoint":native_weather_pin(directory/"checkpoint.npz",result["checkpoint"]),
                    "audit":audit,"forcing_identity":forcing_id,"chunk_work_face_steps":budgets[str(step)]["chunk_face_steps"]}
                native_weather_write(directory/"report.json",record)
                checkpoint = _m4_verify_td_native_weather_storage_load_checkpoint(**record["checkpoint"])
                pages.append(record)
                del result,storage
                print(f"complete {scenario} {step}s hour{hour+1} elapsed{record['elapsed_s']:.2f}s peak{peak}",flush=True)
            scenario_records[str(step)] = pages
            if checkpoint["metadata"]["work_face_steps"] != budgets[str(step)]["global_face_steps_per_scenario"]:
                raise ValueError("global checkpoint work mismatch")
            del checkpoint
        comparisons = []
        for coarse_page,fine_page in zip(scenario_records[str(coarse_step)],scenario_records[str(fine_step)]):
            coarse = _m4_verify_td_native_weather_storage_load_storage(**coarse_page["storage"])
            fine = _m4_verify_td_native_weather_storage_load_storage(**fine_page["storage"])
            comparisons.append(_m4_verify_td_native_weather_storage_compare(coarse["arrays"],fine["arrays"]))
            del coarse,fine
        coarse_checkpoint = _m4_verify_td_native_weather_storage_load_checkpoint(**scenario_records[str(coarse_step)][-1]["checkpoint"])
        fine_checkpoint = _m4_verify_td_native_weather_storage_load_checkpoint(**scenario_records[str(fine_step)][-1]["checkpoint"])
        coarse_routed = coarse_checkpoint["arrays"]["cumulative_routed_volume_m3"]
        fine_routed = fine_checkpoint["arrays"]["cumulative_routed_volume_m3"]
        receiver = float(abs(coarse_routed-fine_routed).sum()/max(1e-12,fine_routed.sum()))
        maximum = max(item["max_saved_depth_difference_m"] for item in comparisons)
        record = {"pages":scenario_records,"hour_comparisons":comparisons,"max_saved_depth_difference_m":maximum,
                  "cumulative_receiver_relative_l1":receiver,"gate_passed":maximum<=.001 and receiver<=.01,
                  "scope":"all24 originalTD spatial-weather hourly states and cumulative actual receiver volumes", "weather_record":case["record"], "forcing_identity":forcing_id, "steps_s":[coarse_step,fine_step],
                  "hydraulic_ready":False,"transient_converged":False,"publishable":False}
        native_weather_write(destination/(scenario+"-comparison.json"),record)
        records[scenario]=record
        del coarse_checkpoint,fine_checkpoint
    if any(_m4_verify_td_native_weather_storage_file_sha256(native_weather_ROOT/name)!=sha for name,sha in code.items()):
        raise ValueError("frozen continuation source changed")
    if _m4_verify_td_native_weather_storage_file_sha256(_m4_verify_td_native_weather_storage_PRIMARY_PATH)!=_m4_verify_td_native_weather_storage_PRIMARY_SHA256 or _m4_verify_td_native_weather_storage_file_sha256(_m4_verify_td_native_weather_storage_HIERARCHY)!=_m4_verify_td_native_weather_storage_HIERARCHY_SHA256:
        raise ValueError("final primary/hierarchy SHA mismatch")
    if _m4_verify_td_native_weather_storage_file_sha256(weather_index)!=weather_index_sha256:
        raise ValueError("external weather index changed")
    for case in weather["cases"].values():
        if _m4_verify_td_native_weather_storage_file_sha256(case["record"]["path"])!=case["record"]["expected_sha256"]:
            raise ValueError("weather artifact changed")
    native_weather_write(destination/"index.json",{"schema":"td-v9-spatial-weather-hour-pages-index-v1", "weather_index":weather["index_pin"], "steps_s":[coarse_step,fine_step],"scenarios":records,"budgets":budgets,
        "code_sha256":code,"all_numerical_gates_passed":all(record["gate_passed"] for record in records.values()),
        "hydraulic_ready":False,"transient_converged":False,"publishable":False})
    monitor.stop()
    monitor.check()
    resource={"schema":"td-v9-spatial-weather-execution-resource-v1", "index_sha256":_m4_verify_td_native_weather_storage_file_sha256(destination/"index.json"), "scope":"complete eastward+westward both steps execution", "complete":True, **monitor.record(), "thread_environment":{name:_m4_verify_td_native_weather_storage_os.environ.get(name) for name in native_weather_THREAD_NAMES}}
    native_weather_write(destination/"resource.json",resource)
    native_weather_write(destination/"final-pin.json",{"path":str(destination/"index.json"),"sha256":_m4_verify_td_native_weather_storage_file_sha256(destination/"index.json"),"resource_path":str(destination/"resource.json"),"resource_sha256":_m4_verify_td_native_weather_storage_file_sha256(destination/"resource.json")})
    print(_m4_verify_td_native_weather_storage_json.dumps({"run":str(destination),"index_sha256":_m4_verify_td_native_weather_storage_file_sha256(destination/"index.json")}),flush=True)

def run_native_weather_cli():
    parser = _m4_verify_td_native_weather_storage_argparse.ArgumentParser()
    parser.add_argument("--coarse-step",type=float,required=True)
    parser.add_argument("--fine-step",type=float,required=True)
    parser.add_argument("--weather-index",type=_m4_verify_td_native_weather_storage_Path,required=True)
    parser.add_argument("--weather-index-sha256",required=True)
    arguments = parser.parse_args()
    native_weather_verify(native_weather_ROOT/"verification/td-basin-generation"/("A-native-weather-storage-"+_m4_verify_td_native_weather_storage_datetime.now(_m4_verify_td_native_weather_storage_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),arguments.coarse_step,arguments.fine_step,arguments.weather_index,arguments.weather_index_sha256)

# --- tools/verify_td_native_weather_storage_v10.py:11 ---
unified_infiltration_ROOT = _m4_verify_td_native_weather_storage_v10_Path(__file__).resolve().parents[1]

# --- tools/verify_td_native_weather_storage_v10.py:12 ---
_m4_verify_td_native_weather_storage_v10_sys.path.insert(0, str(unified_infiltration_ROOT))

# --- tools/verify_td_native_weather_storage_v10.py:29 ---
def unified_infiltration_write(path, value):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_native_weather_storage_v10_publish_bytes
    _m4_verify_td_native_weather_storage_v10_publish_bytes(path, _m4_verify_td_native_weather_storage_v10_json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))

# --- tools/verify_td_native_weather_storage_v10.py:33 ---
def unified_infiltration_pin(path, result):
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_native_weather_storage_v10_file_sha256
    return {'path':str(path.resolve()),'expected_sha256':_m4_verify_td_native_weather_storage_v10_file_sha256(path),'expected_identity':result['identity_sha256']}

# --- tools/verify_td_native_weather_storage_v10.py:37 ---
def unified_infiltration_verify(weather_index, weather_sha, coarse=2.5, fine=1.25):
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_native_weather_storage_v10_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_native_weather_storage_v10_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import save_checkpoint as _m4_verify_td_native_weather_storage_v10_save_checkpoint
    from terrain_pipeline.basin_storage import simulate_hour as _m4_verify_td_native_weather_storage_v10_simulate_hour
    from terrain_pipeline.basin_storage import storagev10_load_checkpoint as _m4_verify_td_native_weather_storage_v10_load_checkpoint
    from terrain_pipeline.basin_storage import storagev10_load_storage as _m4_verify_td_native_weather_storage_v10_load_storage
    from terrain_pipeline.basin_storage import storagev10_save_storage as _m4_verify_td_native_weather_storage_v10_save_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_native_weather_storage_v10_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_native_weather_storage_v10_file_sha256
    from terrain_pipeline.td_native_weather_storage_inputs import load_weather_inputs as _m4_verify_td_native_weather_storage_v10_load_weather_inputs
    from tools.verify_basin_storage import threshold_storage_HIERARCHY as _m4_verify_td_native_weather_storage_v10_HIERARCHY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_IDENTITY as _m4_verify_td_native_weather_storage_v10_HIERARCHY_IDENTITY
    from tools.verify_basin_storage import threshold_storage_HIERARCHY_SHA256 as _m4_verify_td_native_weather_storage_v10_HIERARCHY_SHA256
    if any(_m4_verify_td_native_weather_storage_v10_os.environ.get(name) != '1' for name in native_weather_THREAD_NAMES):
        raise ValueError('explicit single-thread environment required')
    if coarse != 2*fine or any(not _m4_verify_td_native_weather_storage_v10_np.isfinite(step) or step <= 0 or int(3600/step)*step != 3600 for step in (coarse,fine)):
        raise ValueError('exact finite hourly halving required')
    if _m4_verify_td_native_weather_storage_v10_file_sha256(_m4_verify_td_native_weather_storage_v10_PRIMARY_PATH) != _m4_verify_td_native_weather_storage_v10_PRIMARY_SHA256:
        raise ValueError('primary source SHA mismatch')
    hierarchy = _m4_verify_td_native_weather_storage_v10_load_basin_hierarchy(_m4_verify_td_native_weather_storage_v10_HIERARCHY, expected_sha256=_m4_verify_td_native_weather_storage_v10_HIERARCHY_SHA256, expected_identity=_m4_verify_td_native_weather_storage_v10_HIERARCHY_IDENTITY)
    weather = _m4_verify_td_native_weather_storage_v10_load_weather_inputs(weather_index, expected_sha256=weather_sha, hierarchy=hierarchy)
    directory = unified_infiltration_ROOT/'verification/td-basin-generation'/('A-native-weather-v10-'+_m4_verify_td_native_weather_storage_v10_datetime.now(_m4_verify_td_native_weather_storage_v10_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    code_names = ('terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
        'terrain_pipeline/basin_storage.py','terrain_pipeline/basin_storage.py',
        'terrain_pipeline/basin_storage.py','terrain_pipeline/common_infra.py',
        'terrain_pipeline/td_native_weather_storage_inputs.py','terrain_pipeline/climate_forcing.py',
        'terrain_pipeline/climate_forcing.py','terrain_pipeline/basin_topology.py',
        'terrain_pipeline/basin_storage.py','terrain_pipeline/runoff.py',
        'tools/verify_basin_storage_execution.py','tools/verify_basin_storage_execution.py',
        'tools/verify_basin_storage.py')
    code = {name:_m4_verify_td_native_weather_storage_v10_file_sha256(unified_infiltration_ROOT/name) for name in code_names}
    budgets = {str(step):{'chunk_face_steps':int(3600/step)*len(hierarchy['arrays']['face_cells']),
        'global_face_steps_per_direction':24*int(3600/step)*len(hierarchy['arrays']['face_cells'])} for step in (coarse,fine)}
    if any(value['chunk_face_steps'] > 6000000000 for value in budgets.values()):
        raise ValueError('v10 chunk budget exceeded')
    unified_infiltration_write(directory/'run-inputs.json', {'schema':'td-v10-spatial-weather-run-inputs-v1',
        'weather_index':weather['index_pin'],'weather_records':{name:value['record'] for name,value in weather['cases'].items()},
        'hierarchy':{'path':str(_m4_verify_td_native_weather_storage_v10_HIERARCHY),'expected_sha256':_m4_verify_td_native_weather_storage_v10_HIERARCHY_SHA256,'expected_identity':_m4_verify_td_native_weather_storage_v10_HIERARCHY_IDENTITY},
        'primary_sha256':_m4_verify_td_native_weather_storage_v10_PRIMARY_SHA256,'steps_s':[coarse,fine],'budgets':budgets,'chunk_max_face_steps':6000000000,
        'job_max_bytes':1073741824,'code_sha256':code,'physics_version':'v10-unified-infiltration; not execution-equivalence',
        'forcing_identities':{name:value['forcing_identity'] for name,value in weather['cases'].items()},
        'depth_gate_m':.001,'receiver_gate':.01})
    unified_infiltration_write(directory/'execution-code.json', {'code_sha256':code,'sources':{name:(unified_infiltration_ROOT/name).read_text(encoding='utf-8') for name in code_names[:5]}})
    monitor = NativeWeatherResourceMonitor(_m4_verify_td_native_weather_storage_v10_psutil.Process()); monitor.start()
    scenarios = {}
    try:
        for direction in ('eastward','westward'):
            case = weather['cases'][direction]
            pages = {}
            for step in (coarse,fine):
                checkpoint = None
                records = []
                for hour in range(24):
                    began = _m4_verify_td_native_weather_storage_v10_time.perf_counter()
                    result = _m4_verify_td_native_weather_storage_v10_simulate_hour(hierarchy, case['rain_mm_h'], substep_s=step, checkpoint=checkpoint)
                    page_dir = directory/f'{direction}-{step:g}s'/f'hour-{hour:02d}'
                    _m4_verify_td_native_weather_storage_v10_save_storage(page_dir/'storage.npz',result['storage'])
                    _m4_verify_td_native_weather_storage_v10_save_checkpoint(page_dir/'checkpoint.npz',result['checkpoint'])
                    record = {'hour':hour,'storage':unified_infiltration_pin(page_dir/'storage.npz',result['storage']),
                        'checkpoint':unified_infiltration_pin(page_dir/'checkpoint.npz',result['checkpoint']),
                        'elapsed_s':_m4_verify_td_native_weather_storage_v10_time.perf_counter()-began,'forcing_identity':case['forcing_identity'],
                        'chunk_work_face_steps':budgets[str(step)]['chunk_face_steps'],
                        'global_water_residual_m3':float(result['storage']['arrays']['balance_residual_m3'].sum())}
                    unified_infiltration_write(page_dir/'report.json',record)
                    checkpoint = _m4_verify_td_native_weather_storage_v10_load_checkpoint(**record['checkpoint'])
                    records.append(record); monitor.check()
                    print(f'{directory.name} {direction} {step}s hour{hour+1} elapsed{record["elapsed_s"]:.2f}s',flush=True)
                pages[str(step)] = records
            maximum = 0.; differences = []
            for first,second in zip(pages[str(coarse)],pages[str(fine)]):
                first_page=_m4_verify_td_native_weather_storage_v10_load_storage(**first['storage']);second_page=_m4_verify_td_native_weather_storage_v10_load_storage(**second['storage'])
                difference=abs(first_page['arrays']['depth_m']-second_page['arrays']['depth_m'])
                value=float(difference.max());maximum=max(maximum,value)
                frame,cell=_m4_verify_td_native_weather_storage_v10_np.unravel_index(difference.argmax(),difference.shape)
                differences.append({'hour':first['hour'],'max_depth_difference_m':value,'frame':int(frame),'cell':int(cell)})
            first_cp=_m4_verify_td_native_weather_storage_v10_load_checkpoint(**pages[str(coarse)][-1]['checkpoint'])
            second_cp=_m4_verify_td_native_weather_storage_v10_load_checkpoint(**pages[str(fine)][-1]['checkpoint'])
            routed_first=first_cp['arrays']['cumulative_routed_volume_m3'];routed_second=second_cp['arrays']['cumulative_routed_volume_m3']
            relative=float(abs(routed_first-routed_second).sum()/max(1e-12,routed_second.sum()))
            comparison={'schema':'td-v10-spatial-weather-comparison-v1','pages':pages,'hour_comparisons':differences,
                'max_saved_depth_difference_m':maximum,'cumulative_receiver_relative_l1':relative,
                'gate_passed':maximum<=.001 and relative<=.01,'weather_record':case['record'],
                'forcing_identity':case['forcing_identity'],'steps_s':[coarse,fine],
                'hydraulic_ready':False,'publishable':False,'scope':'24h new v10 physical hypothesis; original TD full spatial weather'}
            unified_infiltration_write(directory/(direction+'-comparison.json'),comparison)
            scenarios[direction]=comparison
        if any(_m4_verify_td_native_weather_storage_v10_file_sha256(unified_infiltration_ROOT/name)!=sha for name,sha in code.items()) or _m4_verify_td_native_weather_storage_v10_file_sha256(weather_index)!=weather_sha or _m4_verify_td_native_weather_storage_v10_file_sha256(_m4_verify_td_native_weather_storage_v10_HIERARCHY)!=_m4_verify_td_native_weather_storage_v10_HIERARCHY_SHA256 or _m4_verify_td_native_weather_storage_v10_file_sha256(_m4_verify_td_native_weather_storage_v10_PRIMARY_PATH)!=_m4_verify_td_native_weather_storage_v10_PRIMARY_SHA256:
            raise ValueError('v10 final frozen dependency changed')
        for case in weather['cases'].values():
            if _m4_verify_td_native_weather_storage_v10_file_sha256(case['record']['path'])!=case['record']['expected_sha256']:
                raise ValueError('v10 weather file changed')
        unified_infiltration_write(directory/'index.json', {'schema':'td-v10-spatial-weather-hour-pages-index-v1','scenarios':scenarios,
            'weather_index':weather['index_pin'],'steps_s':[coarse,fine],'code_sha256':code,'budgets':budgets,
            'all_numerical_gates_passed':all(value['gate_passed'] for value in scenarios.values()),
            'hydraulic_ready':False,'transient_converged':False,'publishable':False})
        monitor.stop();monitor.check()
        unified_infiltration_write(directory/'resource.json', {'schema':'td-v10-spatial-weather-resource-v1','index_sha256':_m4_verify_td_native_weather_storage_v10_file_sha256(directory/'index.json'),
            'scope':'complete eastward+westward both steps execution','complete':True,**monitor.record()})
        unified_infiltration_write(directory/'final-pin.json', {'index_path':str(directory/'index.json'),'index_sha256':_m4_verify_td_native_weather_storage_v10_file_sha256(directory/'index.json'),
            'resource_path':str(directory/'resource.json'),'resource_sha256':_m4_verify_td_native_weather_storage_v10_file_sha256(directory/'resource.json')})
        print(_m4_verify_td_native_weather_storage_v10_json.dumps({'run':str(directory),'index_sha256':_m4_verify_td_native_weather_storage_v10_file_sha256(directory/'index.json')}),flush=True)
    except Exception as error:
        monitor.stop()
        unified_infiltration_write(directory/'failure.json', {'error':str(error),'complete':False,'resource':monitor.record(),
            'hydraulic_ready':False,'publishable':False})
        raise

def run_unified_infiltration_cli():
    parser=_m4_verify_td_native_weather_storage_v10_argparse.ArgumentParser()
    parser.add_argument('--weather-index',type=_m4_verify_td_native_weather_storage_v10_Path,required=True)
    parser.add_argument('--weather-index-sha256',required=True)
    parser.add_argument('--coarse-step',type=float,default=2.5)
    parser.add_argument('--fine-step',type=float,default=1.25)
    arguments=parser.parse_args()
    unified_infiltration_verify(arguments.weather_index,arguments.weather_index_sha256,arguments.coarse_step,arguments.fine_step)

PROFILES = {
    'compiled': run_compiled_cli,
    'compiled_ordinary_stages': run_compiled_ordinary_stages_cli,
    'compiled_stages': run_compiled_stages_cli,
    'hour_pages': run_hour_pages_cli,
    'native_weather': run_native_weather_cli,
    'unified_infiltration': run_unified_infiltration_cli,
}

def main(argv=None):
    """Select a preserved M4 validator; remaining options go to that validator."""
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=tuple(PROFILES),default=next(iter(PROFILES)))
    selected,remaining=parser.parse_known_args(argv)
    previous=_m4_tail_sys.argv
    try:
        _m4_tail_sys.argv=[previous[0],*remaining]
        return PROFILES[selected.profile]()
    finally:
        _m4_tail_sys.argv=previous

if __name__ == '__main__':
    main()
