"""Prepare or explicitly execute a separate 0.625s v10 temporal refinement run."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes


STEP_S = .625
REFERENCE_STEP_S = 1.25
THREAD_NAMES = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")
MIN_REMAINING_S = 3600



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

def _json(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 ** 2:
        raise ValueError("refinement JSON budget exceeded")
    return json.loads(path.read_text(encoding="utf-8"))


def _pin(path, expected_sha256):
    path = Path(path).resolve(strict=True)
    if file_sha256(path) != expected_sha256:
        raise ValueError("refinement external SHA mismatch: " + str(path))
    return dict(path=str(path), expected_sha256=expected_sha256)


def _check_code(code_sha256):
    if len(code_sha256) != 15 and set(code_sha256) != set(['terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_topology.py', 'terrain_pipeline/climate_forcing.py', 'terrain_pipeline/common_infra.py', 'terrain_pipeline/runoff.py', 'terrain_pipeline/td_native_weather_storage_inputs.py', 'tools/verify_basin_storage.py', 'tools/verify_basin_storage_execution.py']):
        raise ValueError("baseline requires exactly 15 frozen code pins")
    if not _m4_recorded_code_matches(code_sha256):
        raise ValueError("baseline frozen code pin mismatch")


def _check_baseline_pages(index, inputs):
    if (index.get("schema") != "td-v10-spatial-weather-hour-pages-index-v1" or
            index.get("steps_s") != [2.5, REFERENCE_STEP_S] or
            set(index.get("scenarios", {})) != {"eastward", "westward"}):
        raise ValueError("baseline complete 96-page index required")
    count = 0
    reference_elapsed = 0.
    for direction in ("eastward", "westward"):
        scenario = index["scenarios"][direction]
        if (scenario.get("weather_record") != inputs["weather_records"][direction] or
                scenario.get("forcing_identity") != inputs["forcing_identities"][direction] or
                set(scenario.get("pages", {})) != {"2.5", "1.25"}):
            raise ValueError("baseline weather/forcing/step evidence mismatch")
        for step in ("2.5", "1.25"):
            records = scenario["pages"][step]
            if len(records) != 24:
                raise ValueError("baseline incomplete hourly pages")
            for hour, record in enumerate(records):
                if record.get("hour") != hour or record.get("forcing_identity") != scenario["forcing_identity"]:
                    raise ValueError("baseline hourly chain/forcing mismatch")
                elapsed = record.get("elapsed_s")
                if type(elapsed) not in (int, float) or not 0 < elapsed < 3600:
                    raise ValueError("baseline hourly elapsed evidence invalid")
                if step == "1.25":
                    reference_elapsed += elapsed
                for name in ("storage", "checkpoint"):
                    item = record[name]
                    _pin(item["path"], item["expected_sha256"])
                    if len(item["expected_identity"]) != 64:
                        raise ValueError("baseline hourly identity missing")
                count += 1
    if count != 96:
        raise ValueError("baseline complete 96-page evidence required")
    return reference_elapsed


def _check_status(path):
    status = _json(path)
    if status.get("schema") != "td-ten-hour-pipeline-status-v1" or status.get("state") != "diagnostic_stop":
        raise ValueError("baseline pipeline active or not diagnostic_stop")
    pid = status.get("pid")
    if type(pid) is int and pid > 0:
        import psutil
        if psutil.pid_exists(pid):
            raise ValueError("baseline pipeline PID still active")
    return status


def _check_runtime_pins(plan):
    _pin(plan["pipeline_status_record"]["path"], plan["pipeline_status_record"]["expected_sha256"])
    _check_status(plan["pipeline_status_record"]["path"])
    _check_code(plan["baseline_code_sha256"])
    if file_sha256(__file__) != plan["runner_sha256"]:
        raise ValueError("refinement runner changed")
    for record in plan["baseline_records"].values():
        _pin(record["path"], record["expected_sha256"])
    sources = plan["source_records"]
    for record in (sources["hierarchy"], *sources["weather_records"].values()):
        _pin(record["path"], record["expected_sha256"])
    _pin(sources["weather_index"]["path"], sources["weather_index"]["sha256"])


def prepare(baseline_run, baseline_index_sha256, baseline_resource_sha256, baseline_inputs_sha256,
            baseline_acceptance_record, pipeline_status, deadline_utc, output):
    baseline_run = Path(baseline_run).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    deadline = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        raise ValueError("UTC deadline requires timezone")
    remaining = (deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
    if remaining < MIN_REMAINING_S:
        raise TimeoutError("insufficient remaining deadline for one bounded hour")
    records = dict(index=_pin(baseline_run / "index.json", baseline_index_sha256),
                   resource=_pin(baseline_run / "resource.json", baseline_resource_sha256),
                   inputs=_pin(baseline_run / "run-inputs.json", baseline_inputs_sha256))
    acceptance_pin = _pin(baseline_acceptance_record["path"], baseline_acceptance_record["expected_sha256"])
    records["acceptance"] = acceptance_pin
    index, resource, inputs = (_json(records[name]["path"]) for name in ("index", "resource", "inputs"))
    acceptance = _json(acceptance_pin["path"])
    if (acceptance.get("schema") != "td-independent-final-spatial-weather-v10-v1" or
            acceptance.get("io_chain_accepted") is not True or
            Path(acceptance.get("index_path", "")).resolve() != baseline_run / "index.json" or
            acceptance.get("index_sha256") != baseline_index_sha256 or
            acceptance.get("resource_sha256") != baseline_resource_sha256 or
            any(acceptance.get("acceptance_arguments", {}).get(name, {}).get("expected_sha256") != records[key]["expected_sha256"] or
                Path(acceptance.get("acceptance_arguments", {}).get(name, {}).get("path", "")).resolve() != Path(records[key]["path"])
                for name, key in (("run_inputs_record", "inputs"), ("execution_resource_record", "resource"))) or
            acceptance.get("cold_acceptance", {}).get("io_chain_accepted") is not True):
        raise ValueError("baseline full-final IO acceptance missing or mismatched")
    status = _check_status(pipeline_status)
    status_deadline = datetime.fromisoformat(status["deadline_utc"].replace("Z", "+00:00"))
    if status_deadline.tzinfo is None or deadline.astimezone(timezone.utc) > status_deadline.astimezone(timezone.utc):
        raise ValueError("refinement deadline exceeds pipeline deadline")
    if (inputs.get("schema") != "td-v10-spatial-weather-run-inputs-v1" or
            inputs.get("steps_s") != [2.5, REFERENCE_STEP_S] or
            inputs.get("depth_gate_m") != .001 or inputs.get("receiver_gate") != .01 or
            index.get("code_sha256") != inputs.get("code_sha256") or
            resource.get("schema") != "td-v10-spatial-weather-resource-v1" or
            resource.get("index_sha256") != baseline_index_sha256 or resource.get("complete") is not True or
            resource.get("scope") != "complete eastward+westward both steps execution" or
            resource.get("monitor_error") is not None or resource.get("sampling_interval_s") != 2 or
            any(type(resource.get(name)) is not int or resource[name] < 1
                for name in ("peak_rss_bytes", "peak_private_bytes", "sample_count")) or
            max(resource["peak_rss_bytes"], resource["peak_private_bytes"]) > 1024 ** 3 or
            resource.get("within_1GiB", True) is not True or
            inputs.get("job_max_bytes") != 1024 ** 3 or
            inputs.get("chunk_max_face_steps") != 6000000000):
        raise ValueError("baseline inputs/resource incomplete or changed")
    _check_code(inputs["code_sha256"])
    reference_elapsed = _check_baseline_pages(index, inputs)
    estimated_new_s = reference_elapsed * (REFERENCE_STEP_S / STEP_S)
    required_remaining_s = max(MIN_REMAINING_S, estimated_new_s * 1.25 + 600)
    source_pins = [inputs["hierarchy"], inputs["weather_index"], *inputs["weather_records"].values()]
    for item in source_pins:
        _pin(item["path"], item.get("expected_sha256", item.get("sha256")))
    from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
    if file_sha256(PRIMARY_PATH) != inputs["primary_sha256"]:
        raise ValueError("original TD source pin mismatch")
    reference_work = inputs["budgets"]["1.25"]["chunk_face_steps"]
    if type(reference_work) is not int or reference_work <= 0 or reference_work % int(3600 / REFERENCE_STEP_S):
        raise ValueError("baseline reference work budget invalid")
    face_count = reference_work // int(3600 / REFERENCE_STEP_S)
    chunk_work = int(3600 / STEP_S) * face_count
    if chunk_work > inputs["chunk_max_face_steps"]:
        raise ValueError("new step exceeds chunk work budget")
    plan = dict(schema="td-v10-temporal-refinement-plan-v1", baseline_records=records,
                pipeline_status_record=dict(path=str(Path(pipeline_status).resolve()),
                                            expected_sha256=file_sha256(pipeline_status)),
                source_records=dict(hierarchy=inputs["hierarchy"], weather_index=inputs["weather_index"],
                                    weather_records=inputs["weather_records"]),
                baseline_code_sha256=inputs["code_sha256"], new_step_s=STEP_S,
                reference_step_s=REFERENCE_STEP_S, expected_new_pages=48,
                expected_reference_pages=48, expected_baseline_pages=96,
                estimated_new_elapsed_s=estimated_new_s, required_remaining_s=required_remaining_s,
                execution_ready=remaining >= required_remaining_s,
                deadline_utc=deadline.astimezone(timezone.utc).isoformat(),
                output=str(output), chunk_work_face_steps=chunk_work,
                physics_version=inputs["physics_version"], depth_gate_m=inputs["depth_gate_m"],
                receiver_gate=inputs["receiver_gate"], job_max_bytes=inputs["job_max_bytes"],
                chunk_max_face_steps=inputs["chunk_max_face_steps"],
                runner_sha256=file_sha256(__file__),
                scope="prepare-only unless --execute; baseline 96 pages are historical reference only",
                hydraulic_ready=False, transient_converged=False, publishable=False)
    return plan


def _write(path, record):
    publish_bytes(path, json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def execute(plan):
    if any(os.environ.get(name) != "1" for name in THREAD_NAMES):
        raise ValueError("explicit single-thread environment required")
    output = Path(plan["output"])
    if output.exists():
        raise FileExistsError(output)
    deadline = datetime.fromisoformat(plan["deadline_utc"])
    remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
    if remaining < plan["required_remaining_s"]:
        raise TimeoutError("insufficient remaining deadline for estimated 48-page execution")
    if file_sha256(__file__) != plan["runner_sha256"]:
        raise ValueError("refinement runner changed after prepare")
    _check_runtime_pins(plan)
    output.mkdir(parents=True)
    _write(output / "run-inputs.json", plan)
    _write(output / "execution-code.json", dict(baseline_code_sha256=plan["baseline_code_sha256"],
                                                 runner_sha256=plan["runner_sha256"],
                                                 runner_source=Path(__file__).read_text(encoding="utf-8")))
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--output", str(output)]
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    for name in THREAD_NAMES:
        environment[name] = "1"
    try:
        with (output / "worker.stdout.log").open("wb") as stdout, (output / "worker.stderr.log").open("wb") as stderr:
            completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
                                       timeout=remaining, check=False)
        if completed.returncode:
            raise RuntimeError(f"refinement worker failed with exit {completed.returncode}")
    except Exception as error:
        if not (output / "failure.json").exists():
            _write(output / "failure.json", dict(schema="td-v10-temporal-refinement-failure-v1",
                                                 error=str(error), complete=False, resource_scope="new 48 pages only",
                                                 partial_resource_authenticated=False))
        raise
    return _json(output / "final-pin.json")


def worker(output):
    import psutil
    from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
    from terrain_pipeline.td_native_weather_storage_inputs import load_weather_inputs
    from terrain_pipeline.basin_storage import simulate_hour as simulate_hour
    from terrain_pipeline.basin_storage import storagev10_save_storage as save_storage
    from terrain_pipeline.basin_storage import save_checkpoint as save_checkpoint
    from terrain_pipeline.basin_storage import storagev10_load_checkpoint as load_checkpoint
    from tools.verify_basin_storage_execution import NativeWeatherResourceMonitor as ResourceMonitor

    output = Path(output)
    monitor = ResourceMonitor(psutil.Process())
    monitor.start()
    scenarios = {}
    try:
        plan = _json(output / "run-inputs.json")
        if (plan.get("schema") != "td-v10-temporal-refinement-plan-v1" or
                plan.get("new_step_s") != STEP_S or plan.get("reference_step_s") != REFERENCE_STEP_S or
                plan.get("expected_new_pages") != 48):
            raise ValueError("refinement worker plan invalid")
        if file_sha256(__file__) != plan["runner_sha256"]:
            raise ValueError("refinement runner changed before worker")
        if (plan.get("depth_gate_m") != .001 or plan.get("receiver_gate") != .01 or
                plan.get("job_max_bytes") != 1024 ** 3 or plan.get("chunk_max_face_steps") != 6000000000):
            raise ValueError("refinement fixed physical gates/budgets invalid")
        _check_runtime_pins(plan)
        run_inputs_sha256 = file_sha256(output / "run-inputs.json")
        execution_code_sha256 = file_sha256(output / "execution-code.json")
        code_snapshot = _json(output / "execution-code.json")
        if (code_snapshot.get("runner_sha256") != plan["runner_sha256"] or
                code_snapshot.get("baseline_code_sha256") != plan["baseline_code_sha256"] or
                code_snapshot.get("runner_source") != Path(__file__).read_text(encoding="utf-8")):
            raise ValueError("refinement execution code snapshot mismatch")
        if (datetime.fromisoformat(plan["deadline_utc"]) - datetime.now(timezone.utc)).total_seconds() < plan["required_remaining_s"]:
            raise TimeoutError("refinement worker start has insufficient deadline")
        sources = plan["source_records"]
        hierarchy = load_basin_hierarchy(**sources["hierarchy"])
        weather_pin = sources["weather_index"]
        weather = load_weather_inputs(weather_pin["path"], expected_sha256=weather_pin["sha256"], hierarchy=hierarchy)
        for direction in ("eastward", "westward"):
            case = weather["cases"][direction]
            records = []
            checkpoint = None
            for hour in range(24):
                _check_runtime_pins(plan)
                _pin(output / "run-inputs.json", run_inputs_sha256)
                _pin(output / "execution-code.json", execution_code_sha256)
                if (datetime.fromisoformat(plan["deadline_utc"]) - datetime.now(timezone.utc)).total_seconds() < MIN_REMAINING_S:
                    raise TimeoutError("refinement deadline leaves insufficient single-hour margin")
                began = time.perf_counter()
                result = simulate_hour(hierarchy, case["rain_mm_h"], substep_s=STEP_S, checkpoint=checkpoint)
                page_dir = output / f"{direction}-{STEP_S:g}s" / f"hour-{hour:02d}"
                page_dir.mkdir(parents=True)
                storage_path, checkpoint_path = page_dir / "storage.npz", page_dir / "checkpoint.npz"
                save_storage(storage_path, result["storage"])
                save_checkpoint(checkpoint_path, result["checkpoint"])
                storage = dict(path=str(storage_path.resolve()), expected_sha256=file_sha256(storage_path),
                               expected_identity=result["storage"]["identity_sha256"])
                cp = dict(path=str(checkpoint_path.resolve()), expected_sha256=file_sha256(checkpoint_path),
                          expected_identity=result["checkpoint"]["identity_sha256"])
                record = dict(hour=hour, storage=storage, checkpoint=cp, elapsed_s=time.perf_counter() - began,
                              forcing_identity=case["forcing_identity"],
                              chunk_work_face_steps=plan["chunk_work_face_steps"],
                              global_water_residual_m3=float(result["storage"]["arrays"]["balance_residual_m3"].sum()))
                _write(page_dir / "report.json", record)
                checkpoint = load_checkpoint(**cp)
                records.append(record)
                monitor.check()
                print(f"{direction} hour {hour + 1}/24", flush=True)
            scenarios[direction] = dict(pages=records, weather_record=case["record"],
                                        forcing_identity=case["forcing_identity"])
        _check_runtime_pins(plan)
        _pin(output / "run-inputs.json", run_inputs_sha256)
        _pin(output / "execution-code.json", execution_code_sha256)
        index = dict(schema="td-v10-temporal-refinement-index-v1", scenarios=scenarios,
                     new_step_s=STEP_S, reference_step_s=REFERENCE_STEP_S,
                     baseline_records=plan["baseline_records"],
                     run_inputs_record=dict(path=str(output / "run-inputs.json"),
                                            expected_sha256=file_sha256(output / "run-inputs.json")),
                     source_records=plan["source_records"],
                     code_sha256=plan["baseline_code_sha256"],
                     physics_version=plan["physics_version"],
                     scope="new 0.625s 48 pages only; baseline 96 pages historical reference",
                     hydraulic_ready=False, transient_converged=False, publishable=False)
        _write(output / "index.json", index)
        monitor.stop()
        monitor.check()
        _write(output / "resource.json", dict(schema="td-v10-temporal-refinement-resource-v1",
                                              index_sha256=file_sha256(output / "index.json"),
                                              scope="complete new eastward+westward 0.625s 48 pages only",
                                              complete=True, code_sha256=plan["baseline_code_sha256"],
                                              within_1GiB=True, job_max_bytes=1024 ** 3,
                                              **monitor.record()))
        _write(output / "final-pin.json", dict(index=dict(path=str(output / "index.json"),
                                                        expected_sha256=file_sha256(output / "index.json")),
                                                  resource=dict(path=str(output / "resource.json"),
                                                                expected_sha256=file_sha256(output / "resource.json"))))
    except Exception as error:
        monitor.stop()
        _write(output / "failure.json", dict(schema="td-v10-temporal-refinement-failure-v1", error=str(error),
                                              complete=False, resource_scope="new 48 pages only",
                                              resource=monitor.record()))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path)
    parser.add_argument("--baseline-index-sha256")
    parser.add_argument("--baseline-resource-sha256")
    parser.add_argument("--baseline-inputs-sha256")
    parser.add_argument("--baseline-acceptance-record", type=Path)
    parser.add_argument("--baseline-acceptance-sha256")
    parser.add_argument("--pipeline-status", type=Path)
    parser.add_argument("--deadline-utc")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.output)
        return
    required = (args.baseline_run, args.baseline_index_sha256, args.baseline_resource_sha256,
                args.baseline_inputs_sha256, args.baseline_acceptance_record,
                args.baseline_acceptance_sha256, args.pipeline_status, args.deadline_utc)
    if any(value is None for value in required):
        parser.error("all baseline pins, pipeline status and deadline are required")
    acceptance_pin = dict(path=args.baseline_acceptance_record, expected_sha256=args.baseline_acceptance_sha256)
    plan = prepare(args.baseline_run, args.baseline_index_sha256, args.baseline_resource_sha256,
                   args.baseline_inputs_sha256, acceptance_pin, args.pipeline_status, args.deadline_utc, args.output)
    if args.execute:
        print(json.dumps(execute(plan), indent=2))
    else:
        print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
