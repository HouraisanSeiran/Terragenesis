"""One explicit CPU-only affected-module acceptance run with immutable evidence."""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODULES = (
    "tests.test_mountain_depression_geometry",
    "tests.test_mountain_pool_network",
    "tests.test_mountain_fine_geometry",
    "tests.test_mountain_fine_storage",
    "tests.test_mountain_fine_mesh",
    "tests.test_mountain_manning_storage",
    "tests.test_mountain_source_adapter",
    "tests.test_mountain_lake_coupling",
    "tests.test_mountain_storm_forcing",
    "tests.test_mountain_storm_hru_scale",
    "tests.test_mountain_storm_100m",
    "tests.test_mountain_rainfall",
    "tests.test_mountain_runoff_routing",
    "tests.test_rainfall_runoff",
    "tests.test_lake_balance",
    "tests.test_lake_routing",
    "tests.test_surface_variable_storage",
    "tests.test_physical_generation",
    "tests.test_minecraft_preset",
)
MAX_DURATION_S = 2400
MAX_LOG_BYTES = 16 * 1024 * 1024
EVIDENCE = (
    "verification/mountain-depression-geometry/frozen-20261001T070426687355Z/static-freeze-manifest.json",
    "verification/mountain-manning-tributary/frozen-20261001T075127883716Z/final-handoff-manifest.json",
    "verification/mountain-manning-100m/run-20261001T075855903483Z/current-final-freeze-index.json",
)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def publish_json(path, value):
    target = Path(path)
    data = json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2).encode("ascii")
    temporary = target.with_name("." + target.name + "." + str(os.getpid()))
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def module_path(name):
    relative = Path(*name.split("."))
    for candidate in (ROOT / relative.with_suffix(".py"), ROOT / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def source_paths():
    pending = [module_path(name) for name in MODULES]
    pending.append(Path(__file__).resolve())
    pending += sorted((ROOT / "terrain_pipeline").glob("mountain_*.py"))
    pending += sorted((ROOT / "tools").glob("verify_mountain_*.py"))
    pending += [ROOT / "CONTRIBUTING.md", ROOT / "docs/mountain-depression-geometry.md"]
    pending += [ROOT / name for name in EVIDENCE]
    seen = set()
    while pending:
        path = pending.pop()
        if path is None or path in seen:
            continue
        if not path.is_file():
            raise ValueError("required snapshot file missing: " + str(path))
        seen.add(path)
        if path.suffix != ".py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative = path.parent.relative_to(ROOT).parts
                    package = ".".join(relative[:len(relative) - node.level + 1])
                    prefix = package + ("." + node.module if node.module else "")
                else:
                    prefix = node.module or ""
                names = [prefix] + [prefix + "." + alias.name for alias in node.names if alias.name != "*"]
            for name in names:
                local = module_path(name)
                if local is not None and local not in seen:
                    pending.append(local)
    return sorted(seen)


def snapshot(paths):
    return {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.started = {}
        self.outcomes = {}

    def startTest(self, test):
        self.started[test.id()] = time.monotonic()
        self.outcomes[test.id()] = "passed"
        super().startTest(test)

    def addFailure(self, test, error):
        self.outcomes[test.id()] = "failed"
        super().addFailure(test, error)

    def addError(self, test, error):
        self.outcomes[test.id()] = "error"
        super().addError(test, error)

    def addSkip(self, test, reason):
        self.outcomes[test.id()] = "skipped"
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, error):
        self.outcomes[test.id()] = "expected_failure"
        super().addExpectedFailure(test, error)

    def addUnexpectedSuccess(self, test):
        self.outcomes[test.id()] = "unexpected_success"
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, error):
        if error is not None:
            self.outcomes[test.id()] = "failed_subtest"
        super().addSubTest(test, subtest, error)

    def stopTest(self, test):
        self.records.append({"id": test.id(), "outcome": self.outcomes[test.id()],
                             "elapsed_s": time.monotonic() - self.started[test.id()]})
        super().stopTest(test)


def worker(output):
    loader = unittest.TestLoader()
    tests = []
    seen = set()
    module_counts = {}
    for module in MODULES:
        suite = loader.loadTestsFromName(module)
        module_counts[module] = 0
        for test in flatten(suite):
            if type(test).__module__ != module:
                continue
            if test.id() in seen:
                raise ValueError("duplicate declared test identity: " + test.id())
            seen.add(test.id())
            tests.append(test)
            module_counts[module] += 1
    identities = [test.id() for test in tests]
    zero_modules = [module for module, count in module_counts.items() if count == 0]
    if len(set(identities)) != len(identities) or loader.errors or zero_modules:
        publish_json(output / "worker-result.json", {"status": "test_discovery_refused",
            "loader_errors": loader.errors, "duplicate_ids": len(identities) - len(set(identities)),
            "modules": MODULES, "module_discovered_counts": module_counts, "zero_test_modules": zero_modules})
        return 2
    publish_json(output / "discovered-tests.json", {"modules": MODULES, "unique_test_count": len(identities),
        "module_discovered_counts": module_counts, "test_ids": identities})
    started = time.monotonic()
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2, resultclass=RecordedResult)
    result = runner.run(unittest.TestSuite(tests))
    recorded_ids = [item["id"] for item in result.records]
    coverage_complete = (result.testsRun == len(identities) and len(recorded_ids) == len(identities)
                         and len(set(recorded_ids)) == len(recorded_ids) and set(recorded_ids) == set(identities))
    passed = result.wasSuccessful() and coverage_complete
    record = {"status": "passed" if passed else "failed", "modules": MODULES,
        "module_discovered_counts": module_counts, "coverage_complete": coverage_complete,
        "missing_record_ids": sorted(set(identities) - set(recorded_ids)),
        "unexpected_record_ids": sorted(set(recorded_ids) - set(identities)),
        "unique_discovered_tests": len(identities), "tests_run": result.testsRun,
        "records": result.records, "elapsed_s": time.monotonic() - started,
        "failures": [{"id": test.id(), "traceback": trace} for test, trace in result.failures],
        "errors": [{"id": test.id(), "traceback": trace} for test, trace in result.errors],
        "skipped": [{"id": test.id(), "reason": reason} for test, reason in result.skipped],
        "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
        "scope": "affected_unique_modules_only_not_full_legacy_464_suite",
        "cpu_only": True, "gpu_inference_run": False}
    publish_json(output / "worker-result.json", record)
    return 0 if passed else 1


def run(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "verification/mountain-round-acceptance"):
        raise ValueError("acceptance output must stay under verification/mountain-round-acceptance")
    output.mkdir(parents=True, exist_ok=False)
    paths = source_paths()
    before = snapshot(paths)
    publish_json(output / "source-before.json", before)
    environment = os.environ.copy()
    environment.update(CUDA_VISIBLE_DEVICES="-1", MPLBACKEND="Agg", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--worker", str(output)]
    publish_json(output / "invocation.json", {"modules": MODULES, "command": command, "cwd": str(ROOT),
        "started_utc": datetime.now(timezone.utc).isoformat(), "duration_ceiling_s": MAX_DURATION_S,
        "log_byte_ceiling": MAX_LOG_BYTES, "cuda_visible_devices": "-1", "no_gpu_or_game": True,
        "source_snapshot_policy": "AST_local_import_closure_plus_all_mountain_modules_verifiers_and_delivery_manifests"})
    started = time.monotonic()
    failure = None
    with (output / "unittest.log").open("xb") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            if time.monotonic() - started > MAX_DURATION_S or (output / "unittest.log").stat().st_size > MAX_LOG_BYTES:
                failure = "acceptance_time_or_log_budget_exceeded"
                process.kill()
                process.wait()
                break
            time.sleep(.2)
    after_paths = source_paths()
    after = snapshot(after_paths)
    publish_json(output / "source-after.json", after)
    source_changed = {name: {"before": before.get(name), "after": after.get(name)} for name in set(before) | set(after)
                      if before.get(name) != after.get(name)}
    result_path = output / "worker-result.json"
    results = json.loads(result_path.read_text(encoding="ascii")) if result_path.exists() else None
    passed = process.returncode == 0 and results is not None and results["status"] == "passed" and not source_changed and failure is None
    record = {"schema": "mountain-round-affected-acceptance-v1", "status": "passed" if passed else "failed",
        "exit_code": process.returncode, "failure": failure, "elapsed_s": time.monotonic() - started,
        "modules": MODULES, "source_changed": source_changed, "source_unchanged": not source_changed,
        "unique_discovered_tests": results.get("unique_discovered_tests") if results else None,
        "tests_run": results.get("tests_run") if results else None,
        "worker_result_sha256": digest(result_path) if result_path.exists() else None,
        "log_sha256": digest(output / "unittest.log"), "gpu_inference_run": False,
        "scope": "unit_regression_only_not_repeated_dynamic_artifacts_or_natural_hydrology_certification"}
    publish_json(output / "report.json", record)
    publish_json(output / "artifact-manifest.json", {path.name: digest(path) for path in sorted(output.iterdir()) if path.is_file()})
    print(json.dumps({"output": str(output), **record}, ensure_ascii=True, indent=2))
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="AST-only inventory; no test imports or execution")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    if arguments.worker is not None:
        return worker(arguments.worker)
    if arguments.list:
        print(json.dumps({"modules": MODULES, "module_count": len(MODULES),
            "source_snapshot": snapshot(source_paths()), "tests_executed": False}, indent=2))
        return 0
    destination = arguments.output or ROOT / "verification/mountain-round-acceptance" / (
        "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    return run(destination)


if __name__ == "__main__":
    raise SystemExit(main())
