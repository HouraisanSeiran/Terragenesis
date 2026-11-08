"""Read-only frozen evidence gates, with opt-in joint unittest and browser audits."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import traceback
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = ROOT / "verification/surface-continuity-resumption/run-20260930T171150.386297Z/joint-regression.json"
FIXED = (
    "verification/surface-variable-storage/run-20260930T192708.659151Z",
    "verification/surface-engineering-prepare/run-20260930T193214454541Z",
    "verification/surface-land-coverage/run-20260930T200657434780Z",
)
EXTRA = ("tests.test_surface_variable_storage", "tests.test_surface_engineering_prepare",
         "tests.test_surface_land_coverage", "tests.test_surface_review_export")
OLD_REPORTS = (
    "verification/surface-domain-prepare/run-20260930T103111870204Z/report.json",
    "verification/surface-domain-mosaic/run-20260930T170535.835312Z/report.json",
    "verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/report.json",
)
REPAIR_DIRECTORY = ROOT / "verification/surface-static-validation-repair/run-20260930T204827573351Z"
REPAIR_PATHS = {"terrain_pipeline/surface_engineering_prepare.py", "tests/test_surface_engineering_prepare.py",
                "terrain_pipeline/surface_domain_mosaic.py", "tests/test_surface_domain_mosaic.py",
                "terrain_pipeline/surface_domain_prepare.py", "tests/test_surface_domain_prepare.py"}
REPLACEMENTS = {}
CASE_SOURCES = {
    "two-domain-mosaic": ("mesh", "verification/surface-domain-mosaic/run-20260930T170535.835312Z/two-domain-dry-extension.npz", "c1a39c6f6fee25c631e26548e49799004bbdec9ba457f2f66b6ce879d6f9df65"),
    "dynamic-pulse": ("dynamic", "verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/pulse.npz", "c85e8ef84b896df2f2f3e48d2c062bc9b9c0ddd66d4cf0b56320ef6cc6ea16cd"),
    "dynamic-tailwater": ("dynamic", "verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/domain2-tailwater-rise.npz", "5256af08a0b8d1c5dc7963a4a873dbfdf0c105c70fca82fbe5562bf4940a967c"),
    "domain1-coast-drop": ("coast", "verification/surface-coast-drop/run-20260930T125523.932019Z/actual-river-engineering-coast.npz", "0e896c7832b36d79d4596d7a4b8894b67f5f92fcf6b252c8735943e5e3115313"),
    "dem-candidate": ("dem", "verification/dem-domain/run-20260930T062026836139Z/dem-candidate.npz", "d081ff6439a4d8bd57add2e6316096009a57b197f27e4ad7a93608f1bcd605b3"),
    "two-domain-engineering": ("engineering", FIXED[1] + "/two-domain-engineering.npz", "30f011385e72d346475ec1f6f0c71f74da216a238f38628c4b0668741628097e"),
    "wet-cross-precision": ("mesh", "verification/surface-fine-mosaic/run-20260930T123659.258177Z/wet-cross-precision.npz", "6195a9bffcf464924e562a74a83650085b570bad8a38b1c0aaf42c37f58b840c"),
    "land-footprint-engineering": ("engineering", FIXED[2] + "/two-domain-land-coverage.npz", "3867c0f04aab78fe8e0abd8fda6ed409fa599dc7f1b217ac021987223632eba1"),
}
for case_name, digest in (
    ("baseline", "f903945978b69756c0a7b429c4a596e4b4d504ff1dd7b66d0f9226ce609f0916"),
    ("pulse", "392ea3fad66827fa8a3acd43301627b86ca6a4a186ea9994a2d34b32322e6c63"),
    ("domain2-tailwater-rise", "e2684b14c01c8554e27ad035243ed0f874de8c0326b5a99825920ac14b5f848c"),
    ("failed-prefix", "ed22c413554ac5ff08704804c4f952ba323920b5ab5fea65fabe3240b2caa96a"),
    ("cancelled-prefix", "7433612d5b71bda363a845c3ed8224e1b37a66aed95b547e8df6a2dfaa0b57fa"),
):
    CASE_SOURCES["variable-" + case_name] = ("dynamic", FIXED[0] + "/" + case_name + ".npz", digest)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding="utf8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def workspace_path(value):
    normalized = str(value).replace("\\", "/")
    for segment in ("verification/", "terrain_pipeline/", "tests/", "tools/", "docs/", "web-preview/"):
        if segment in normalized:
            normalized = normalized[normalized.index(segment):]
            break
    path = (ROOT / normalized).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("evidence path outside workspace")
    return path


def check(path, expected, tracked):
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError("strict SHA256 required: " + str(path))
    path = workspace_path(path)
    replacement = REPLACEMENTS.get(str(path))
    if replacement is not None and expected == replacement["old"]:
        expected = replacement["new"]
    actual = sha256(path)
    if actual != expected:
        raise ValueError("frozen hash mismatch: " + str(path))
    previous = tracked.setdefault(str(path), actual)
    if previous != actual:
        raise ValueError("conflicting evidence hashes: " + str(path))
    return actual


def snapshot(path, tracked):
    path = workspace_path(path)
    actual = sha256(path)
    if str(path) in tracked and tracked[str(path)] != actual:
        raise ValueError("evidence changed while checking")
    tracked[str(path)] = actual


def repair_gate(tracked):
    report_path = REPAIR_DIRECTORY / "report.json"
    review_path = REPAIR_DIRECTORY / "independent-review.json"
    report, review = read(report_path), read(review_path)
    if report["status"] != "passed" or review["status"] != "accepted_bounded_scope":
        raise ValueError("supplemental static repair has not been independently accepted")
    snapshot(report_path, tracked)
    snapshot(review_path, tracked)
    check(report_path, review["report_file_sha256"], tracked)
    old, new = report["old_implementation_sha256"], report["new_implementation_sha256"]
    if set(old) != REPAIR_PATHS or set(new) != REPAIR_PATHS or review["implementation_frozen_sha256"] != new:
        raise ValueError("repair must bind exactly the six authorized files")
    historical = {}
    for name in (*OLD_REPORTS, FIXED[1] + "/report.json"):
        path = ROOT / name
        data = read(path)
        snapshot(path, tracked)
        mapping = data.get("code_sha256", data.get("implementation_files", data.get("implementation_file_sha256")))
        for file_path, digest in mapping.items():
            historical[str(workspace_path(file_path))] = digest
    for file_path in sorted(REPAIR_PATHS):
        resolved = workspace_path(file_path)
        if old[file_path] != historical.get(str(resolved)):
            raise ValueError("repair old SHA differs from original historical report: " + file_path)
        check(resolved, new[file_path], tracked)
    if report["original_archives_unchanged"] is not True or report["implementation_unchanged_during_run"] is not True:
        raise ValueError("repair evidence changed during verification")
    original = report["original_bundle_sha256_before"]
    if not original or original != report["original_bundle_sha256_after"]:
        raise ValueError("repair original bundle hashes differ before and after verification")
    for file_path, digest in original.items():
        check(file_path, digest, tracked)
    replacements = {str(workspace_path(path)): {"old": old[path], "new": new[path]} for path in REPAIR_PATHS}
    REPLACEMENTS.update(replacements)
    return {"directory": str(REPAIR_DIRECTORY), "report_sha256": tracked[str(report_path)],
            "review_sha256": tracked[str(review_path)], "replacements": replacements}


def evidence(directory, tracked):
    report_path = directory / "report.json"
    review_path = directory / "independent-review.json"
    report, review = read(report_path), read(review_path)
    snapshot(report_path, tracked)
    snapshot(review_path, tracked)
    if report["status"] != "passed" or review["status"] not in ("accepted_bounded_scope", "passed"):
        raise ValueError("unaccepted evidence: " + str(directory))
    if "report_file_sha256" in review:
        check(report_path, review["report_file_sha256"], tracked)
    implementation = report.get("implementation_sha256", report.get("implementation_file_sha256"))
    if not isinstance(implementation, dict) or not implementation:
        raise ValueError("missing implementation hashes")
    for path, digest in implementation.items():
        check(path, digest, tracked)
    for path, digest in review.get("implementation_frozen_sha256", {}).items():
        check(path, digest, tracked)
    if "cases" in report:
        if {name + ".npz" for name in report["cases"]} != set(review["bundle_sha256"]):
            raise ValueError("review case coverage mismatch")
        for name, case in report["cases"].items():
            check(case["path"], case["file_sha256"], tracked)
            check(directory / (name + ".npz"), review["bundle_sha256"][name + ".npz"], tracked)
    else:
        bundle = report["bundle"]
        check(bundle["path"], bundle["file_sha256"], tracked)
        if review.get("bundle_file_sha256") != bundle["file_sha256"]:
            raise ValueError("independent review not bound to final bundle")
        if review.get("bundle_identity_sha256") != bundle["identity_sha256"]:
            raise ValueError("independent review identity differs")
        check(report["display"]["path"], report["display"]["file_sha256"], tracked)
        if review.get("display_file_sha256") != report["display"]["file_sha256"]:
            raise ValueError("independent review display differs")
    source_path = report.get("source_path", report.get("source"))
    check(source_path, report["source_file_sha256"], tracked)
    return {"directory": str(directory), "report_sha256": tracked[str(report_path)],
            "review_sha256": tracked[str(review_path)], "status": review["status"]}


def manifest_gate(path, tracked):
    manifest = read(path)
    snapshot(path, tracked)
    if manifest["schemaVersion"] != "surface-review-v1" or manifest["generatedFromFixedAllowlist"] is not True:
        raise ValueError("manifest contract mismatch")
    ids, files = set(), set()
    if {case["caseId"] for case in manifest["cases"]} != set(CASE_SOURCES):
        raise ValueError("manifest requires exactly the 13 fixed review cases")
    for case in manifest["cases"]:
        if case["caseId"] in ids or case["file"] in files:
            raise ValueError("duplicate manifest case/file")
        ids.add(case["caseId"])
        files.add(case["file"])
        target = (path.parent / case["file"]).resolve()
        if not target.is_relative_to(path.parent.resolve()):
            raise ValueError("manifest path escapes data directory")
        check(target, case["sha256"], tracked)
        payload = read(target)
        kind, source_path, source_digest = CASE_SOURCES[case["caseId"]]
        status = "diagnostic_candidate" if case["caseId"] == "dem-candidate" else "accepted_bounded_scope"
        evidence_record = payload["evidence"]
        if (payload["schemaVersion"] != "surface-review-v1" or payload["caseId"] != case["caseId"] or
                payload["kind"] != kind or case["kind"] != kind or case["status"] != status or
                evidence_record["status"] != status or evidence_record["source"]["sha256"] != source_digest or
                workspace_path(evidence_record["source"]["path"]) != ROOT / source_path):
            raise ValueError("manifest payload schema/kind/status/fixed source mismatch")
        check(source_path, source_digest, tracked)
    return {"path": str(path), "sha256": tracked[str(path)], "case_ids": sorted(ids)}


def test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_ids(item)
        else:
            yield item.id()


def run_tests(modules, directory):
    if len(modules) != len(set(modules)):
        raise ValueError("duplicate unittest modules")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(modules)
    ids = list(test_ids(suite))
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate unittest IDs in joint suite")
    started = time.perf_counter()
    with (directory / "unittest.txt").open("x", encoding="utf8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=CountedResult).run(suite)
    passed = result.passed
    return {"modules": modules, "module_count": len(modules), "loaded_unique_test_ids": ids,
            "run": result.testsRun, "passed": passed, "skipped": len(result.skipped),
            "failures": len(result.failures), "errors": len(result.errors),
            "expected_failures": len(result.expectedFailures), "unexpected_successes": len(result.unexpectedSuccesses),
            "skip_details": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
            "loader_errors": loader.errors, "duration_s": time.perf_counter() - started,
            "successful": result.wasSuccessful(), "log_sha256": sha256(directory / "unittest.txt"),
            "historical_or_focused_counts_added": False}


class CountedResult(unittest.TextTestResult):
    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.passed = 0

    def addSuccess(self, test):
        self.passed += 1
        super().addSuccess(test)


def self_check(directory):
    """Exercise runner gates with tiny synthetic fixtures, never the joint suite."""
    checks = {}
    def reject(name, operation, error_type=ValueError):
        try:
            operation()
        except error_type:
            checks[name] = True
        else:
            raise AssertionError("self-check did not reject: " + name)
    target = directory / "self-check-payload.txt"
    target.write_text("fixed", encoding="ascii")
    tracked = {}
    check(target, sha256(target), tracked)
    checks["valid_hash"] = True
    reject("bad_hash", lambda: check(target, "0" * 64, {}))
    reject("malformed_hash", lambda: check(target, True, {}))
    target.write_text("changed", encoding="ascii")
    reject("changed_snapshot", lambda: snapshot(target, tracked))
    reject("outside_workspace", lambda: workspace_path(ROOT.parent / "outside.txt"))
    malformed = directory / "duplicate.json"
    malformed.write_text('{"key":1,"key":2}', encoding="ascii")
    reject("duplicate_json", lambda: read(malformed))
    malformed.write_text('{"key":NaN}', encoding="ascii")
    reject("nonfinite_json", lambda: read(malformed))
    manifest = directory / "manifest.json"
    cases = []
    for case_id, (kind, source_path, digest) in CASE_SOURCES.items():
        status = "diagnostic_candidate" if case_id == "dem-candidate" else "accepted_bounded_scope"
        payload_path = directory / (case_id + ".json")
        payload_path.write_text(json.dumps({"schemaVersion": "surface-review-v1", "caseId": case_id,
            "kind": kind, "evidence": {"status": status, "source": {"path": source_path, "sha256": digest}}}), encoding="ascii")
        cases.append({"caseId": case_id, "kind": kind, "status": status, "file": payload_path.name,
                      "sha256": sha256(payload_path)})
    base = {"schemaVersion": "surface-review-v1", "generatedFromFixedAllowlist": True, "cases": cases}
    manifest.write_text(json.dumps(base), encoding="ascii")
    manifest_gate(manifest, {})
    checks["valid_manifest"] = True
    base["cases"].append(dict(base["cases"][0]))
    manifest.write_text(json.dumps(base), encoding="ascii")
    reject("duplicate_manifest", lambda: manifest_gate(manifest, {}))
    base["cases"] = cases[:12]
    manifest.write_text(json.dumps(base), encoding="ascii")
    reject("missing_required_case", lambda: manifest_gate(manifest, {}))
    base["cases"] = cases[:13]
    base["cases"][0] = {**base["cases"][0], "file": "../outside.json"}
    manifest.write_text(json.dumps(base), encoding="ascii")
    reject("manifest_escape", lambda: manifest_gate(manifest, {}))
    base["cases"] = cases[:13]
    base["cases"][0] = dict(cases[0])
    first_payload = directory / cases[0]["file"]
    original = read(first_payload)
    for field in ("caseId", "schemaVersion", "kind", "status", "source"):
        payload = read(first_payload) if field == "caseId" else json.loads(json.dumps(original))
        if field in ("caseId", "schemaVersion", "kind"):
            payload[field] = "wrong"
        elif field == "status":
            payload["evidence"]["status"] = "unreviewed"
        else:
            payload["evidence"]["source"]["sha256"] = "0" * 64
        first_payload.write_text(json.dumps(payload), encoding="ascii")
        base["cases"][0]["sha256"] = sha256(first_payload)
        manifest.write_text(json.dumps(base), encoding="ascii")
        reject("coherent_manifest_wrong_" + field, lambda: manifest_gate(manifest, {}))
        first_payload.write_text(json.dumps(original), encoding="ascii")
    reject("duplicate_modules", lambda: run_tests(["synthetic", "synthetic"], directory))
    class SyntheticTests(unittest.TestCase):
        def test_pass(self):
            pass

        @unittest.skip("synthetic skip")
        def test_skip(self):
            pass

        def test_failure(self):
            self.fail("synthetic failure")

        def test_error(self):
            raise RuntimeError("synthetic error")
    synthetic = directory / "synthetic-suite"
    synthetic.mkdir()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SyntheticTests)
    with patch.object(unittest.TestLoader, "loadTestsFromNames", return_value=suite):
        counted = run_tests(["synthetic"], synthetic)
    if any(counted[key] != value for key, value in
           (("run", 4), ("passed", 1), ("skipped", 1), ("failures", 1), ("errors", 1))):
        raise AssertionError("synthetic unittest counts differ")
    checks["actual_counting_and_skip_reason"] = counted["skip_details"][0]["reason"] == "synthetic skip"
    test = SyntheticTests("test_pass")
    with patch.object(unittest.TestLoader, "loadTestsFromNames", return_value=unittest.TestSuite([test, test])):
        reject("duplicate_test_ids", lambda: run_tests(["synthetic"], directory))
    for name in FIXED:
        result = evidence(ROOT / name, {})
        checks["frozen_evidence_" + Path(name).parent.name] = result["status"] == "accepted_bounded_scope"
    if not all(checks.values()):
        raise AssertionError("self-check false result")
    return {"status": "passed", "checks": checks, "checks_run": len(checks),
            "synthetic_counts": {key: counted[key] for key in ("run", "passed", "skipped", "failures", "errors")},
            "final_suite_or_browser_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", action="store_true", help="Run the unique joint suite only after all writers freeze")
    parser.add_argument("--self-check", action="store_true", help="Focused runner gates only; no joint suite or browser")
    parser.add_argument("--browser", action="store_true", help="Opt in to installed Playwright/Edge audit")
    parser.add_argument("--manifest", type=Path, default=ROOT / "web-preview/data/surface-review-v1/manifest.json")
    parser.add_argument("--old-constrained-hashes", type=Path, help="Optional historical path->SHA256 JSON map for old modules only")
    arguments = parser.parse_args()
    default_manifest = (ROOT / "web-preview/data/surface-review-v1/manifest.json").resolve()
    if arguments.browser and arguments.manifest.resolve() != default_manifest:
        parser.error("--browser requires the default manifest used by the existing audit")
    if arguments.self_check and (arguments.tests or arguments.browser):
        parser.error("--self-check cannot be combined with --tests or --browser")
    started = datetime.now(timezone.utc)
    elapsed_start = time.perf_counter()
    directory = ROOT / "verification/surface-integrated-acceptance" / ("run-" + started.strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    report = {"started_utc": started.isoformat(), "status": "running", "mode": "read_only_evidence",
              "tests_requested": arguments.tests, "browser_requested": arguments.browser,
              "gpu_java_or_manifest_export": False}
    tracked = {}
    snapshot(Path(__file__), tracked)
    exit_code = 0
    with (directory / "stdout.txt").open("x", encoding="utf8") as stdout, \
         (directory / "stderr.txt").open("x", encoding="utf8") as stderr, \
         redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            report["supplemental_static_repair"] = repair_gate(tracked)
            if arguments.self_check:
                report["mode"] = "focused_runner_self_check"
                report["self_check"] = self_check(directory)
                report["status"] = "passed"
            else:
                execute_acceptance(arguments, directory, report, tracked)
        except Exception as error:
            exit_code = 1
            report["status"] = "failed"
            report["error"] = repr(error)
            traceback.print_exc()
        finally:
            changes = []
            for path, before in tracked.items():
                try:
                    after = sha256(path)
                except OSError as error:
                    after = repr(error)
                if before != after:
                    changes.append({"path": path, "before": before, "after": after})
            report["tracked_source_and_evidence_sha256"] = tracked
            report["changed_during_run"] = changes
            if changes:
                exit_code = 1
                report["status"] = "failed"
            report["exit_code"] = exit_code
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            report["duration_s"] = time.perf_counter() - elapsed_start
    report["stdout_sha256"] = sha256(directory / "stdout.txt")
    report["stderr_sha256"] = sha256(directory / "stderr.txt")
    report["runner_sha256"] = sha256(__file__)
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")
    print(directory.resolve())
    return exit_code


def execute_acceptance(arguments, directory, report, tracked):
    baseline = read(BASELINE)
    snapshot(BASELINE, tracked)
    check(BASELINE.parent / baseline["log"], baseline["log_sha256"], tracked)
    old_modules = re.findall(r"\btests\.[A-Za-z_][A-Za-z_0-9]*", baseline["command"])
    if len(old_modules) != 27 or len(set(old_modules)) != 27:
        raise ValueError("historical 27-module allowlist mismatch")
    modules = list(dict.fromkeys(old_modules + list(EXTRA)))
    report["historical_baseline_reference"] = {"path": str(BASELINE), "sha256": tracked[str(BASELINE)],
        "modules": old_modules, "not_added_to_current_counts": True}
    old_checks = {}
    for name in OLD_REPORTS:
        old = read(ROOT / name)
        snapshot(ROOT / name, tracked)
        for path, digest in old.get("code_sha256", old.get("implementation_files", old.get("implementation_file_sha256"))).items():
            old_checks[str(workspace_path(path))] = check(path, digest, tracked)
    if arguments.old_constrained_hashes is not None:
        mapping = read(arguments.old_constrained_hashes)
        snapshot(arguments.old_constrained_hashes, tracked)
        for path, digest in mapping.items():
            normalized = str(workspace_path(path).relative_to(ROOT)).replace("\\", "/")
            if "variable_storage" in normalized or "engineering_prepare" in normalized or "land_coverage" in normalized:
                raise ValueError("new implementation is not an old constrained baseline")
            old_checks[str(workspace_path(path))] = check(path, digest, tracked)
    report["old_constrained_hash_checks"] = old_checks
    report["old_hash_coverage"] = "Only explicit historical hashes are compared; 27 module names are not 27 frozen implementation hashes"
    report["evidence"] = [evidence(ROOT / name, tracked) for name in FIXED]
    report["manifest"] = manifest_gate(arguments.manifest.resolve(), tracked)
    for name in ("app.js", "renderer.js", "index.html", "style.css", "build_surface_review_data.py"):
        snapshot(ROOT / "web-preview" / name, tracked)
    for module in modules:
        snapshot(ROOT / (module.replace(".", "/") + ".py"), tracked)
    if arguments.tests:
        report["mode"] = "joint_regression"
        report["tests"] = run_tests(modules, directory)
        if not report["tests"]["successful"]:
            raise AssertionError("joint unittest suite failed")
    if arguments.browser:
        from tools.verify_surface_review_browser import audit
        browser_directory = directory / "browser"
        browser_directory.mkdir()
        snapshot(ROOT / "tools/verify_surface_review_browser.py", tracked)
        browser_started = time.perf_counter()
        browser_report = {"status": "failed"}
        try:
            browser_report = audit(browser_directory)
        except Exception as error:
            browser_report["error"] = repr(error)
            raise
        finally:
            browser_report["duration_s"] = time.perf_counter() - browser_started
            report["browser"] = browser_report
            (browser_directory / "report.json").write_text(json.dumps(browser_report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")
        if report["browser"]["status"] != "passed":
            raise AssertionError("browser audit failed")
    report["status"] = "passed"


if __name__ == "__main__":
    raise SystemExit(main())
