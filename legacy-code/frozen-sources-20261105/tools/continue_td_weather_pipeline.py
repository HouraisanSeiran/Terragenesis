"""Bounded serial river computation with frozen inputs and independent gates."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".pipeline-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def pin(path, identity_required=False):
    path = Path(path).resolve(strict=True)
    record = dict(path=str(path), expected_sha256=file_sha256(path))
    if identity_required:
        record["expected_identity"] = json.loads(path.read_text(encoding="utf-8"))["identity_sha256"]
    return record


def check_pins(configuration):
    for record in [configuration["weather_index_record"], *configuration["candidate_topology_records"].values()]:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("pipeline external input changed: " + record["path"])
    for name, digest in configuration["code_sha256"].items():
        if file_sha256(ROOT / name) != digest:
            raise ValueError("pipeline frozen code changed: " + name)


class Pipeline:
    def __init__(self, configuration, output, hours):
        if type(hours) not in (int, float) or not 0 < hours <= 10:
            raise ValueError("wall-clock hours must be in (0,10]")
        if configuration.get("schema") != "td-ten-hour-pipeline-config-v1":
            raise ValueError("explicit pipeline schema required")
        if set(configuration["candidate_topology_records"]) != {"valley_incision", "source_deposition"}:
            raise ValueError("two candidates required")
        check_pins(configuration)
        self.configuration = configuration
        self.output = Path(output).resolve()
        if self.output.exists():
            raise FileExistsError(self.output)
        self.output.mkdir(parents=True)
        self.deadline = time.monotonic() + hours * 3600
        now = datetime.now(timezone.utc)
        self.status = dict(schema="td-ten-hour-pipeline-status-v1", pid=os.getpid(), state="running", phase="initializing",
            started_utc=now.isoformat(), deadline_utc=(now + timedelta(hours=hours)).isoformat(),
            wall_clock_limit_hours=hours, completed_stages=[], hydraulic_ready=False,
            natural_outlet_verified=False, publishable=False)
        write_json(self.output / "configuration.json", configuration)
        self.update()

    def update(self, **values):
        self.status.update(values)
        self.status["updated_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(self.output / "status.json", self.status)

    def call(self, name, script, arguments):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("pipeline deadline reached")
        check_pins(self.configuration)
        self.update(phase=name)
        command = [sys.executable, str(ROOT / script), *map(str, arguments)]
        write_json(self.output / (name + "-command.json"), dict(command=command, timeout_s=remaining))
        environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                           NUMBA_NUM_THREADS="1", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        stdout = self.output / (name + ".stdout.log")
        stderr = self.output / (name + ".stderr.log")
        with stdout.open("wb") as output_stream, stderr.open("wb") as error_stream:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=output_stream,
                                    stderr=error_stream, timeout=remaining, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"stage {name} failed ({result.returncode}); inspect {stderr}")
        check_pins(self.configuration)
        self.status["completed_stages"].append(name)
        self.update()
        parsed = None
        with stdout.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    parsed = value
        return parsed

    def baseline(self):
        weather = self.configuration["weather_index_record"]
        result = self.call("baseline-run", "tools/verify_td_native_weather_storage_v10.py",
            ["--weather-index", weather["path"], "--weather-index-sha256", weather["expected_sha256"]])
        run = Path(result["run"]).resolve(strict=True)
        self.update(baseline_run=str(run))
        reports = {}
        for direction in ("eastward", "westward"):
            report = self.call("baseline-audit-" + direction, "tools/audit_td_native_weather_v10.py",
                ["--run", run, "--inputs-sha256", file_sha256(run / "run-inputs.json"), "--direction", direction,
                 "--comparison-sha256", file_sha256(run / (direction + "-comparison.json"))])
            reports[direction] = dict(path=report["path"], expected_sha256=report["sha256"])
        arguments = ["--run", run, "--index-sha256", file_sha256(run / "index.json"),
                     "--resource-sha256", file_sha256(run / "resource.json")]
        for direction, record in reports.items():
            arguments.extend(["--" + direction + "-audit", record["path"],
                              "--" + direction + "-audit-sha256", record["expected_sha256"]])
        accepted = self.call("baseline-final", "tools/audit_td_native_weather_v10_final.py", arguments)
        record = dict(path=accepted["path"], expected_sha256=accepted["sha256"])
        self.update(baseline_acceptance_record=record, baseline_numerical_gate_passed=accepted["all_saved_numerical_gates_passed"])
        for direction, audit_record in reports.items():
            self.call("baseline-figure-" + direction, "tools/plot_td_continuation_review.py",
                      ["--audit", audit_record["path"], "--expected-sha256", audit_record["expected_sha256"]])
        review_inputs = self.output / "baseline-review-inputs.json"
        write_json(review_inputs, record)
        self.call("baseline-review", "tools/export_td_v10_accepted_review.py",
                  ["--acceptance-record", review_inputs, "--output", self.output / "baseline-review"])
        return record, accepted["all_saved_numerical_gates_passed"]

    def candidates(self, baseline_record):
        prepare_inputs = self.output / "candidate-prepare-inputs.json"
        write_json(prepare_inputs, dict(baseline_acceptance_record=baseline_record,
                   candidate_topology_records=self.configuration["candidate_topology_records"]))
        self.call("candidate-prepare", "tools/run_td_candidate_weather_jobs.py",
                  ["--stage", "prepare", "--inputs", prepare_inputs, "--output", self.output / "candidate-plan"])
        final_records, raw_reports = {}, {}
        for candidate in ("valley_incision", "source_deposition"):
            destination = self.output / candidate
            self.call(candidate + "-run", "tools/run_td_candidate_weather_jobs.py",
                      ["--stage", "run", "--inputs", self.output / "candidate-plan-record.json", "--output", destination,
                       "--candidate-id", candidate, "--execute"])
            record = pin(destination / "index.json", identity_required=True)
            record_path = self.output / (candidate + "-execution-record.json")
            write_json(record_path, record)
            final_records[candidate], raw_reports[candidate] = record, {}
            passed = True
            for direction in ("eastward", "westward"):
                report = self.call(candidate + "-audit-" + direction, "tools/audit_td_candidate_weather.py",
                    ["--execution-record", record_path, "--direction", direction])
                raw_reports[candidate][direction] = dict(path=report["path"], expected_sha256=report["expected_sha256"])
                passed = passed and report["gate_passed"]
            self.update(candidate_final_records=final_records, candidate_raw_reports=raw_reports)
            if not passed:
                self.update(state="diagnostic_stop", reason=candidate + " failed temporal numerical gates")
                return False
        inputs = self.output / "candidate-selection-inputs.json"
        write_json(inputs, dict(baseline_acceptance_record=baseline_record,
                   candidate_final_records=final_records, independent_numerical_records=raw_reports))
        self.call("candidate-select", "tools/run_td_candidate_weather_jobs.py",
                  ["--stage", "select", "--inputs", inputs, "--output", self.output / "candidate-selection"])
        self.call("candidate-review", "tools/run_td_candidate_weather_jobs.py",
                  ["--stage", "review", "--inputs", self.output / "candidate-selection-record.json",
                   "--output", self.output / "candidate-review"])
        return True

    def execute(self):
        try:
            baseline, passed = self.baseline()
            if not passed:
                self.update(state="diagnostic_stop", reason="baseline failed temporal numerical gates")
            elif self.candidates(baseline):
                self.update(state="complete", phase="delivered", selection="baseline pending")
        except (subprocess.TimeoutExpired, TimeoutError) as error:
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
    parser.add_argument("--wall-clock-hours", type=float, default=10.)
    args = parser.parse_args()
    if file_sha256(args.configuration) != args.configuration_sha256:
        raise ValueError("pipeline configuration pin mismatch")
    configuration = json.loads(args.configuration.read_text(encoding="utf-8"))
    print(json.dumps(Pipeline(configuration, args.output, args.wall_clock_hours).execute(), ensure_ascii=True))


if __name__ == "__main__":
    main()
