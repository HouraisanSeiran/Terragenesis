"""Wait for complete diagnostic baseline, then run one separately pinned refinement."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256
from tools.continue_td_weather_pipeline import write_json, check_pins


def frozen(configuration):
    check_pins(configuration["baseline_configuration"])
    for name, digest in configuration["followup_code_sha256"].items():
        target = (ROOT / name).resolve(strict=True)
        if not target.is_relative_to(ROOT) or file_sha256(target) != digest:
            raise ValueError("refinement followup frozen code changed: " + name)


def choose(status, parent_alive):
    state = status.get("state")
    if state == "running" or parent_alive:
        return "wait"
    if state != "diagnostic_stop":
        return "stop"
    if (status.get("baseline_numerical_gate_passed") is not False or
            status.get("reason") != "baseline failed temporal numerical gates" or
            not status.get("baseline_acceptance_record")):
        return "stop"
    return "refine"


class Followup:
    def __init__(self, configuration, output):
        self.configuration = configuration
        self.output = Path(output).resolve()
        if self.output.exists():
            raise FileExistsError(self.output)
        frozen(configuration)
        self.output.mkdir(parents=True)
        self.deadline = datetime.fromisoformat(configuration["deadline_utc"])
        if self.deadline.tzinfo is None:
            raise ValueError("followup requires explicit timezone")
        self.status = dict(schema="td-v10-refinement-followup-status-v1", pid=os.getpid(),
                           state="waiting_baseline", deadline_utc=configuration["deadline_utc"],
                           started_utc=datetime.now(timezone.utc).isoformat(),
                           solver_advanced=False, hydraulic_ready=False,
                           natural_outlet_verified=False, publishable=False)
        write_json(self.output / "configuration.json", configuration)
        self.update()

    def update(self, **values):
        self.status.update(values)
        self.status["updated_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(self.output / "status.json", self.status)

    def remaining(self):
        return (self.deadline - datetime.now(timezone.utc)).total_seconds()

    def wait_baseline(self):
        path = Path(self.configuration["baseline_status_path"])
        while self.remaining() > 0:
            status = json.loads(path.read_text(encoding="utf-8"))
            pid = status.get("pid")
            decision = choose(status, type(pid) is int and pid > 0 and psutil.pid_exists(pid))
            if decision == "refine":
                return status
            if decision == "stop":
                self.update(state="baseline_not_eligible", reason=status.get("reason", status.get("state")))
                return None
            time.sleep(min(60., max(0., self.remaining())))
        self.update(state="time_limit", reason="deadline reached while waiting baseline")
        return None

    def call(self, stage, command):
        frozen(self.configuration)
        remaining = self.remaining()
        if remaining <= 0:
            raise TimeoutError("followup deadline reached")
        self.update(state="running", phase=stage)
        write_json(self.output / (stage + "-command.json"), dict(command=list(map(str, command)), timeout_s=remaining))
        environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                           NUMBA_NUM_THREADS="1", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        with (self.output / (stage + ".stdout.log")).open("wb") as stdout, (self.output / (stage + ".stderr.log")).open("wb") as stderr:
            child = subprocess.Popen(list(map(str, command)), cwd=ROOT, env=environment,
                                     stdout=stdout, stderr=stderr)
            self.update(child_pid=child.pid, solver_advanced=stage == "refinement-run" or self.status["solver_advanced"])
            try:
                while child.poll() is None:
                    if self.remaining() <= 0:
                        raise TimeoutError("followup deadline reached with active child")
                    time.sleep(min(2., max(0., self.remaining())))
            except BaseException:
                try:
                    parent = psutil.Process(child.pid)
                    descendants = parent.children(recursive=True)
                    for process in reversed(descendants):
                        try:
                            process.kill()
                        except psutil.NoSuchProcess:
                            pass
                    parent.kill()
                    psutil.wait_procs([*descendants, parent], timeout=5)
                except psutil.NoSuchProcess:
                    pass
                child.wait()
                raise
        if child.returncode:
            raise RuntimeError(f"followup {stage} failed; inspect stderr")
        frozen(self.configuration)

    def execute(self):
        try:
            status = self.wait_baseline()
            if status is None:
                return self.status
            frozen(self.configuration)
            record = status["baseline_acceptance_record"]
            if file_sha256(record["path"]) != record["expected_sha256"]:
                raise ValueError("baseline acceptance SHA mismatch")
            acceptance = json.loads(Path(record["path"]).read_text(encoding="utf-8"))
            if acceptance.get("io_chain_accepted") is not True:
                raise ValueError("baseline full IO not accepted")
            baseline_run = Path(acceptance["index_path"]).resolve(strict=True).parent
            if str(baseline_run) != str(Path(self.configuration["baseline_run"]).resolve(strict=True)):
                raise ValueError("followup baseline run differs from predeclaration")
            from tools.run_td_v10_temporal_refinement import prepare
            destination = self.output / "execution"
            arguments = dict(baseline_run=baseline_run, baseline_index_sha256=acceptance["index_sha256"],
                             baseline_resource_sha256=acceptance["resource_sha256"],
                             baseline_inputs_sha256=acceptance["acceptance_arguments"]["run_inputs_record"]["expected_sha256"],
                             baseline_acceptance_record=record, pipeline_status=self.configuration["baseline_status_path"],
                             deadline_utc=self.configuration["deadline_utc"], output=destination)
            plan = prepare(**arguments)
            write_json(self.output / "preflight-plan.json", plan)
            self.update(baseline_acceptance_record=record, estimated_new_elapsed_s=plan["estimated_new_elapsed_s"],
                        required_remaining_s=plan["required_remaining_s"])
            if plan.get("execution_ready") is not True:
                self.update(state="insufficient_time", reason="predeclared 48-page estimate plus reserve exceeds deadline")
                return self.status
            command = [sys.executable, ROOT / "tools/run_td_v10_temporal_refinement.py"]
            for name, value in arguments.items():
                if name == "baseline_acceptance_record":
                    command.extend(("--baseline-acceptance-record", value["path"], "--baseline-acceptance-sha256", value["expected_sha256"]))
                else:
                    command.extend(("--" + name.replace("_", "-"), value))
            command.append("--execute")
            self.call("refinement-run", command)
            self.update(solver_advanced=True)
            index = destination / "index.json"
            resource = destination / "resource.json"
            inputs = destination / "run-inputs.json"
            command = [sys.executable, ROOT / "tools/audit_td_v10_temporal_refinement.py", "--run", destination,
                       "--index-sha256", file_sha256(index), "--inputs-sha256", file_sha256(inputs),
                       "--resource-sha256", file_sha256(resource)]
            self.call("refinement-audit", command)
            lines = (self.output / "refinement-audit.stdout.log").read_text(encoding="utf-8").splitlines()
            result = json.loads(lines[-1])
            if file_sha256(result["path"]) != result["expected_sha256"]:
                raise ValueError("followup independent acceptance SHA mismatch")
            self.update(state="complete" if result["all_saved_numerical_gates_passed"] else "diagnostic_stop",
                        phase="independent_acceptance", numerical_gate_passed=result["all_saved_numerical_gates_passed"],
                        acceptance_record=dict(path=result["path"], expected_sha256=result["expected_sha256"]),
                        candidates_executed=False)
        except (TimeoutError, subprocess.TimeoutExpired) as error:
            self.update(state="time_limit", reason=str(error))
        except Exception as error:
            self.update(state="failed", reason=str(error), error_type=type(error).__name__)
            raise
        return self.status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if file_sha256(args.configuration) != args.configuration_sha256:
        raise ValueError("followup configuration pin mismatch")
    configuration = json.loads(args.configuration.read_text(encoding="utf-8"))
    print(json.dumps(Followup(configuration, args.output).execute()))


if __name__ == "__main__":
    main()
