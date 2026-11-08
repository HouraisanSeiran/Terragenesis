"""Serial hourly checkpoint pages, with explicit global work and final pinned index."""

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys
import time
import math
import os
import threading
from importlib.metadata import version
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import psutil
from terrain_pipeline.common_infra import file_sha256, publish_bytes, identity
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.basin_storage import compileddriver_simulate as simulate_basin_storage
from terrain_pipeline.td_native_weather_storage_inputs import load_weather_inputs
from terrain_pipeline.basin_storage import compiledio_save_checkpoint as save_checkpoint
from terrain_pipeline.basin_storage import compiled_load_checkpoint as load_checkpoint
from terrain_pipeline.basin_storage import compiled_save_storage as save_storage
from terrain_pipeline.basin_storage import compiled_load_storage as load_storage
from tools.verify_td_basin_storage import HIERARCHY, HIERARCHY_SHA256, HIERARCHY_IDENTITY
from tools.verify_td_basin_storage_v7 import compare
from tools.audit_td_basin_generation import audit_storage


def write(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def pin(path, result):
    return {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": result["identity_sha256"]}


THREAD_NAMES=("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS")


class ResourceMonitor:
    def __init__(self,process):
        self.process=process
        self.finished=threading.Event()
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
        self.thread=threading.Thread(target=self.run,daemon=True)
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


def verify(destination, coarse_step, fine_step, weather_index, weather_index_sha256):
    if any(os.environ.get(name)!="1" for name in THREAD_NAMES):
        raise ValueError("explicit single-thread execution environment required")
    if destination.exists():
        raise FileExistsError(destination)
    if any(not math.isfinite(step) or step<=0 or 3600/step != int(3600/step) for step in (coarse_step,fine_step)) or coarse_step != 2*fine_step:
        raise ValueError("finite exact halving and integer hourly substeps required")
    if file_sha256(PRIMARY_PATH)!=PRIMARY_SHA256:
        raise ValueError("primary source SHA mismatch")
    hierarchy = load_basin_hierarchy(HIERARCHY, expected_sha256=HIERARCHY_SHA256, expected_identity=HIERARCHY_IDENTITY)
    weather = load_weather_inputs(weather_index,expected_sha256=weather_index_sha256,hierarchy=hierarchy)
    faces = len(hierarchy["arrays"]["face_cells"])
    code_names = ("terrain_pipeline/td_basin_storage_compiled.py", "terrain_pipeline/td_basin_storage_compiled_driver.py", "terrain_pipeline/td_basin_storage_compiled_io.py",
                  "terrain_pipeline/td_basin_forcing_compensated.py", "terrain_pipeline/td_basin_transport_v6.py",
                  "terrain_pipeline/td_basin_storage_checkpoint_io.py", "terrain_pipeline/td_basin_storage_continuation_io.py",
                  "terrain_pipeline/td_basin_storage_v7_io.py", "terrain_pipeline/td_basin_storage_v4.py",
                  "terrain_pipeline/td_basin_storage.py", "terrain_pipeline/td_basin_storage_implicit.py",
                  "terrain_pipeline/rainfall_runoff.py", "terrain_pipeline/td_basin_hierarchy.py",
                  "terrain_pipeline/mountain_source_adapter.py", "terrain_pipeline/td_basin_source.py",
                  "terrain_pipeline/td_native_weather_storage_inputs.py", "terrain_pipeline/td_native_storm_forcing.py",
                  "terrain_pipeline/mountain_storm_forcing.py", "tools/verify_td_native_weather_storage.py",
                  "tools/audit_td_basin_generation.py", "tools/verify_td_basin_storage_v7.py", "tools/verify_td_basin_storage.py")
    code = {name: file_sha256(ROOT/name) for name in code_names}
    budgets = {str(step): {"chunk_face_steps": round(3600/step)*faces,
                          "global_face_steps_per_scenario": 24*round(3600/step)*faces} for step in (coarse_step,fine_step)}
    if any(item["chunk_face_steps"] > 6_000_000_000 for item in budgets.values()):
        raise ValueError("hourly chunk budget exceeded")
    write(destination/"run-inputs.json", {"schema":"td-v9-spatial-weather-run-inputs-v1", "profile":"v9-compiled-hour-loop-v8-equivalent-v1", "weather_index":weather["index_pin"], "weather_records":{name:case["record"] for name,case in weather["cases"].items()}, "forcing_identities":{name:case["forcing_identity"] for name,case in weather["cases"].items()}, "steps_s":[coarse_step,fine_step],
        "hierarchy":{"path":str(HIERARCHY),"sha256":HIERARCHY_SHA256,"identity":HIERARCHY_IDENTITY},
        "forcing":"externally pinned native [24,z,x] interval means; initial zero depth and default runoff",
        "budgets":budgets,"chunk_max_work_face_steps":6_000_000_000,"job_max_bytes":1073741824,
        "global_budget_semantics":"global sum explicitly exceeds chunk cap; independently finite 24 hourly pages per scenario/step",
        "depth_gate_m":.001,"receiver_gate":.01,"code_sha256":code})
    write(destination/"execution-code.json", {"code_sha256":code,"sources":{name:(ROOT/name).read_text(encoding="utf-8") for name in code_names[:4]},
        "checkpoint":"all four states plus compensation; hourly forcing ledger reset only; cumulative directional/routed evidence retained"})
    records = {}
    process = psutil.Process()
    monitor = ResourceMonitor(process)
    monitor.start()
    for scenario in ("eastward","westward"):
        case=weather["cases"][scenario]
        rain=case["rain_mm_h"]
        forcing_id=case["forcing_identity"]
        write(destination/(scenario+"-forcing.json"),{"schema":"td-v9-spatial-weather-forcing-record-v1","weather_record":case["record"],"dt_s":3600.,"shape":list(rain.shape),"identity":forcing_id,"plan_identity":case["plan_identity"]})
        scenario_records = {}
        for step in (coarse_step,fine_step):
            checkpoint = None
            pages = []
            for hour in range(24):
                began = time.perf_counter()
                try:
                    result = simulate_basin_storage(hierarchy,rain[hour:hour+1],parameters={"substep_s":step},
                                                    checkpoint=checkpoint,forcing_identity=forcing_id,full_rain_mm_h=rain)
                except Exception as error:
                    write(destination/"failure.json",{"scenario":scenario,"step_s":step,"hour":hour,"reason":str(error),"completed_pages":pages,
                        "hydraulic_ready":False,"transient_converged":False,"publishable":False})
                    raise
                storage = result["storage"]
                directory = destination/f"{scenario}-{step:g}s"/f"hour-{hour:02d}"
                if checkpoint is not None:
                    for key in ("depth_m","soil_mm","fast_mm","slow_mm"):
                        if not np.array_equal(storage["arrays"][key][0],checkpoint["arrays"][key]):
                            raise ValueError("page initial state checkpoint mismatch")
                for key in ("face_forward_m3","face_reverse_m3","active_forward_s","active_reverse_s","routed_volume_m3","wet_duration_s"):
                    previous = 0 if checkpoint is None else checkpoint["arrays"]["cumulative_"+key]
                    if not np.allclose(result["checkpoint"]["arrays"]["cumulative_"+key]-previous,storage["arrays"][key],rtol=1e-12,atol=1e-9):
                        raise ValueError("checkpoint cumulative delta mismatch")
                monitor.check()
                memory = process.memory_info()
                peak = int(getattr(memory,"peak_wset",memory.rss))
                if peak > 1073741824:
                    raise MemoryError("continuation job exceeded1GiB")
                save_storage(directory/"storage.npz",storage)
                save_checkpoint(directory/"checkpoint.npz",result["checkpoint"])
                try:
                    audit = audit_storage(storage["arrays"],storage["metadata"])
                except Exception as error:
                    write(directory/"failure.json",{"reason":str(error),"storage":pin(directory/"storage.npz",storage),"checkpoint":pin(directory/"checkpoint.npz",result["checkpoint"]),"hydraulic_ready":False,"publishable":False})
                    write(destination/"failure.json",{"scenario":scenario,"step_s":step,"hour":hour,"reason":str(error),"completed_pages":pages,"hydraulic_ready":False,"publishable":False})
                    raise
                record = {"hour":hour,"elapsed_s":time.perf_counter()-began,"peak_bytes":peak,
                    "storage":pin(directory/"storage.npz",storage),"checkpoint":pin(directory/"checkpoint.npz",result["checkpoint"]),
                    "audit":audit,"forcing_identity":forcing_id,"chunk_work_face_steps":budgets[str(step)]["chunk_face_steps"]}
                write(directory/"report.json",record)
                checkpoint = load_checkpoint(**record["checkpoint"])
                pages.append(record)
                del result,storage
                print(f"complete {scenario} {step}s hour{hour+1} elapsed{record['elapsed_s']:.2f}s peak{peak}",flush=True)
            scenario_records[str(step)] = pages
            if checkpoint["metadata"]["work_face_steps"] != budgets[str(step)]["global_face_steps_per_scenario"]:
                raise ValueError("global checkpoint work mismatch")
            del checkpoint
        comparisons = []
        for coarse_page,fine_page in zip(scenario_records[str(coarse_step)],scenario_records[str(fine_step)]):
            coarse = load_storage(**coarse_page["storage"])
            fine = load_storage(**fine_page["storage"])
            comparisons.append(compare(coarse["arrays"],fine["arrays"]))
            del coarse,fine
        coarse_checkpoint = load_checkpoint(**scenario_records[str(coarse_step)][-1]["checkpoint"])
        fine_checkpoint = load_checkpoint(**scenario_records[str(fine_step)][-1]["checkpoint"])
        coarse_routed = coarse_checkpoint["arrays"]["cumulative_routed_volume_m3"]
        fine_routed = fine_checkpoint["arrays"]["cumulative_routed_volume_m3"]
        receiver = float(abs(coarse_routed-fine_routed).sum()/max(1e-12,fine_routed.sum()))
        maximum = max(item["max_saved_depth_difference_m"] for item in comparisons)
        record = {"pages":scenario_records,"hour_comparisons":comparisons,"max_saved_depth_difference_m":maximum,
                  "cumulative_receiver_relative_l1":receiver,"gate_passed":maximum<=.001 and receiver<=.01,
                  "scope":"all24 originalTD spatial-weather hourly states and cumulative actual receiver volumes", "weather_record":case["record"], "forcing_identity":forcing_id, "steps_s":[coarse_step,fine_step],
                  "hydraulic_ready":False,"transient_converged":False,"publishable":False}
        write(destination/(scenario+"-comparison.json"),record)
        records[scenario]=record
        del coarse_checkpoint,fine_checkpoint
    if any(file_sha256(ROOT/name)!=sha for name,sha in code.items()):
        raise ValueError("frozen continuation source changed")
    if file_sha256(PRIMARY_PATH)!=PRIMARY_SHA256 or file_sha256(HIERARCHY)!=HIERARCHY_SHA256:
        raise ValueError("final primary/hierarchy SHA mismatch")
    if file_sha256(weather_index)!=weather_index_sha256:
        raise ValueError("external weather index changed")
    for case in weather["cases"].values():
        if file_sha256(case["record"]["path"])!=case["record"]["expected_sha256"]:
            raise ValueError("weather artifact changed")
    write(destination/"index.json",{"schema":"td-v9-spatial-weather-hour-pages-index-v1", "weather_index":weather["index_pin"], "steps_s":[coarse_step,fine_step],"scenarios":records,"budgets":budgets,
        "code_sha256":code,"all_numerical_gates_passed":all(record["gate_passed"] for record in records.values()),
        "hydraulic_ready":False,"transient_converged":False,"publishable":False})
    monitor.stop()
    monitor.check()
    resource={"schema":"td-v9-spatial-weather-execution-resource-v1", "index_sha256":file_sha256(destination/"index.json"), "scope":"complete eastward+westward both steps execution", "complete":True, **monitor.record(), "thread_environment":{name:os.environ.get(name) for name in THREAD_NAMES}}
    write(destination/"resource.json",resource)
    write(destination/"final-pin.json",{"path":str(destination/"index.json"),"sha256":file_sha256(destination/"index.json"),"resource_path":str(destination/"resource.json"),"resource_sha256":file_sha256(destination/"resource.json")})
    print(json.dumps({"run":str(destination),"index_sha256":file_sha256(destination/"index.json")}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--coarse-step",type=float,required=True)
    parser.add_argument("--fine-step",type=float,required=True)
    parser.add_argument("--weather-index",type=Path,required=True)
    parser.add_argument("--weather-index-sha256",required=True)
    arguments = parser.parse_args()
    verify(ROOT/"verification/td-basin-generation"/("A-native-weather-storage-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),arguments.coarse_step,arguments.fine_step,arguments.weather_index,arguments.weather_index_sha256)
