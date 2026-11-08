"""Replay saved candidate products only; never generate terrain or solve transport.

Run with runtime/venv/Scripts/python.exe. Reports and rejected copies are sidecars.
"""

import argparse
from contextlib import contextmanager
import hashlib
import importlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / ".scratch/river-r7-r9-candidate-20261022"
OUTPUT = ROOT / ".scratch/river-stage1-acceptance-20261022/replay"
ROLES = ("flow", "sediment", "coupled", "bed_feedback")
LOADERS = {
    "flow": ("metric_domain_flow", "load_domain_flow"),
    "sediment": ("metric_domain_sediment", "load_domain_sediment"),
    "coupled": ("metric_domain_coupled", "load_domain_coupled"),
    "bed_feedback": ("metric_domain_bed_feedback", "load_domain_bed_feedback"),
    "r7": ("metric_domain_channel_hydraulics", "load_domain_channel_hydraulics"),
    "domain": ("metric_domain_pipeline", "load_domain_product"),
}
FORBIDDEN_EXACT = {"build_domain_channel_hydraulics", "build_domain_channel_geometry"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-finite JSON: " + value)

    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def contained(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError("artifact escapes candidate source tree: " + str(path))
    return path


def source_snapshot(root):
    return {str(p.resolve()): sha256(p) for p in sorted(Path(root).rglob("*")) if p.is_file()}


def product_specs(source):
    source = Path(source).resolve()
    bundle_path = source / "bundle/bundle.json"
    bundle = read_json(bundle_path)
    specs = []
    for tile in bundle["tiles"]:
        for role in ROLES:
            item = tile["ledgers"][role]
            path = contained(bundle_path.parent / tile["directory"] / item["file"], source)
            specs.append(dict(key=tile["directory"] + "/" + role, role=role,
                              path=str(path), sha256=item["sha256"], identity=item["identity_sha256"]))
    index_path = contained(ROOT / bundle["domain_products"]["index"].replace("\\", "/"), source)
    index = read_json(index_path)
    if index["product_set_sha256"] != bundle["domain_products"]["product_set_sha256"]:
        raise ValueError("bundle domain index binding mismatch")
    for item in index["domains"]:
        path = contained(index_path.parent / item["product"], source)
        specs.append(dict(key="domain/" + item["product"], role="domain", path=str(path),
                          sha256=sha256(path), identity=item["identity_sha256"],
                          byte_pin_origin="acceptance-run snapshot; index pins content identity only"))
    summary_path = source / "r7/v2/runtime/complete-core-domain-report.json"
    summary = read_json(summary_path)
    path = contained(summary_path.parent / summary["path"], source)
    specs.append(dict(key="r7/v2/runtime", role="r7", path=str(path),
                      sha256=summary["sha256"], identity=summary["identity_sha256"]))
    return specs


def schedules(specs):
    shuffled = list(specs)
    random.Random(20261022).shuffle(shuffled)
    return [("forward", list(specs)), ("reverse", list(reversed(specs))),
            ("shuffled", shuffled), ("forward-new-process", list(specs))]


@contextmanager
def no_generation():
    """Fail on entry, before any generation/solver/publisher body can execute."""
    blocked = []

    def profile(frame, event, arg):
        if event != "call":
            return
        filename = frame.f_code.co_filename.replace("\\", "/")
        name = frame.f_code.co_name
        if "/terrain_pipeline/" in filename and (
                name.startswith(("solve", "generate", "publish", "prepare"))
                or name in FORBIDDEN_EXACT):
            blocked.append(filename + ":" + name)
            raise RuntimeError("forbidden generation/solve entry: " + name)

    previous = sys.getprofile()
    sys.setprofile(profile)
    try:
        yield blocked
    finally:
        sys.setprofile(previous)


def load_product(spec):
    module_name, loader_name = LOADERS[spec["role"]]
    module = importlib.import_module("terrain_pipeline.surface_rivers." + module_name)
    loader = getattr(module, loader_name)
    if spec["role"] == "domain":
        # This dedicated loader has no external archive-byte pin argument.
        if sha256(spec["path"]) != spec["sha256"]:
            raise ValueError("external domain archive SHA256 mismatch")
        record = loader(spec["path"], expected_identity_sha256=spec["identity"])
        return record.identity_sha256
    record = loader(spec["path"], expected_sha256=spec["sha256"], expected_identity=spec["identity"])
    return record["identity_sha256"]


def rejection_matches(error, expected):
    if error is None:
        return False
    if expected == "missing":
        return isinstance(error, FileNotFoundError)
    if expected == "sha":
        return isinstance(error, ValueError) and any(s in str(error).lower() for s in (
            "sha256", "sha-256", "sha mismatch", "external archive hash mismatch"))
    if expected == "identity":
        return isinstance(error, ValueError) and "identity" in str(error).lower()
    if expected == "version":
        return isinstance(error, ValueError) and "domain hydraulic identity/schema/scope mismatch" in str(error)
    raise ValueError("unknown rejection expectation: " + expected)


def worker(manifest_path, result_path):
    manifest = read_json(manifest_path)
    checks = []
    with no_generation() as blocked:
        for repeat in range(manifest.get("repeats", 1)):
            for spec in manifest["products"]:
                error, actual = None, None
                try:
                    actual = load_product(spec)
                except Exception as exc:
                    error = exc
                expected = spec.get("reject")
                passed = rejection_matches(error, expected) if expected else (
                    error is None and actual == spec["identity"])
                checks.append(dict(check=spec["key"], repeat=repeat, status="PASS" if passed else "FAIL",
                                   identity_sha256=actual, expected_identity_sha256=spec["identity"],
                                   expected_rejection=expected,
                                   error=None if error is None else dict(type=type(error).__name__, message=str(error))))
    checks.append(dict(check="no_generation_or_solve_entry", status="PASS" if not blocked else "FAIL", blocked=blocked))
    report = dict(pid=__import__("os").getpid(), executable=sys.executable, checks=checks,
                  status="PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL")
    write_json(result_path, report)
    return 0 if report["status"] == "PASS" else 1


def run_process(output, name, specs, repeats=1):
    manifest_path, result_path = output / (name + "-manifest.json"), output / (name + "-result.json")
    write_json(manifest_path, dict(products=specs, repeats=repeats))
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(manifest_path), "--result", str(result_path)]
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
        result = read_json(result_path) if result_path.exists() else {"status": "FAIL", "checks": []}
        result.update(command=command, returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
    except subprocess.TimeoutExpired as exc:
        result = dict(status="FAIL", checks=[], command=command, error="worker timed out", timeout_seconds=exc.timeout)
    result["name"] = name
    result["status"] = "PASS" if result["status"] == "PASS" and result.get("returncode") == 0 else "FAIL"
    write_json(output / (name + "-process.json"), result)
    return result


def negative_specs(specs, source, output):
    fixtures = output / "fixtures"
    fixtures.mkdir()
    cases = []
    for number, spec in enumerate(specs):
        for kind in ("sha-bytes", "sha-pin", "missing", "identity"):
            directory = fixtures / (str(number) + "-" + kind)
            directory.mkdir()
            path = directory / Path(spec["path"]).name
            copied = dict(spec, path=str(path), reject="sha" if kind.startswith("sha") else kind)
            if kind != "missing":
                shutil.copy2(spec["path"], path)
                if kind == "sha-bytes":
                    with path.open("ab") as stream:
                        stream.write(b"\nacceptance external byte tamper\n")
                elif kind == "sha-pin":
                    copied["sha256"] = "0" * 64
                else:
                    copied["identity"] = "0" * 64
            cases.append(("reject-" + str(number) + "-" + kind, [copied]))
    old_summary = read_json(source / "r7/complete-core-domain-report.json")
    old_path = contained(source / "r7" / old_summary["path"], source)
    old_copy = fixtures / "old-r7-v1.npz"
    shutil.copy2(old_path, old_copy)
    cases.append(("reject-old-r7-version", [dict(key="old-r7-v1-correct-own-pins", role="r7", path=str(old_copy),
                 sha256=old_summary["sha256"], identity=old_summary["identity_sha256"], reject="version")]))
    return cases


def acceptance(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("sidecar output must be disjoint from source tree")
    output.mkdir(parents=True, exist_ok=False)
    before = source_snapshot(source)
    write_json(output / "source-sha256-before.json", before)
    results, fatal = [], None
    specs = []
    try:
        specs = product_specs(source)
        write_json(output / "source-product-pins.json", specs)
        for name, order in schedules(specs):
            results.append(run_process(output, name, order, repeats=2))
        for name, products in negative_specs(specs, source, output):
            results.append(run_process(output, name, products))
    except Exception as exc:
        fatal = dict(type=type(exc).__name__, message=str(exc))
    after = source_snapshot(source)
    write_json(output / "source-sha256-after.json", after)
    checks = [dict(check=r["name"], status=r["status"]) for r in results]
    expected_runs = 4 + 4 * len(specs) + 1
    checks.extend([dict(check="all_expected_processes_executed", status="PASS" if len(results) == expected_runs and not fatal else "FAIL"),
                   dict(check="source_bytes_unchanged", status="PASS" if before == after else "FAIL")])
    positive = results[:4]
    fingerprints = [{c["check"]: c["identity_sha256"] for c in r["checks"] if "identity_sha256" in c} for r in positive]
    pids = [r.get("pid") for r in positive]
    stable = (len(positive) == 4 and all(r["status"] == "PASS" for r in positive)
              and len(set(pids)) == 4 and all(f == fingerprints[0] for f in fingerprints)
              and len(fingerprints[0]) == len(specs))
    checks.append(dict(check="new_process_order_and_repeat_identity_stable", status="PASS" if stable else "FAIL", pids=pids))
    report = dict(schema="stage1-saved-candidate-replay-v1", status="PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
                  executable=sys.executable, python_version=sys.version, source=str(source), output=str(output),
                  process_count=len(results), product_count=len(specs), checks=checks, fatal=fatal,
                  process_reports=[r["name"] + "-process.json" for r in results],
                  input_sha256_before=before, input_sha256_after=after,
                  candidate_chain_only=True, all_phases_complete=False, production_default_decided=False,
                  cross_tile_physical_transport_consistency_certified=False,
                  limitations=["Saved consumption order invariance is not cross-tile physical transport consistency.",
                               "This bundle has only one saved tile; no new tile transport evidence is created.",
                               "No source generation, hydraulic solve or sediment evolution is rerun.",
                               "Pins bind saved declarations, not independent historical provenance.",
                               "Domain byte pins are acceptance snapshots; domain index pins content identity.",
                               "R7 covers one terminal's current-core production, not outside-core upstream inflow.",
                               "R6 carved geometry is not consumed; geometry, backwater, floodplain/lake evolution, calibration and naturalness remain uncertified.",
                               "R8 changed bed still needs geometry/hydraulic revalidation and bed rejection.",
                               "Unregistered candidate only; stage completion and a production default are not asserted."])
    write_json(output / "report.json", report)
    lines = ["# Saved candidate replay", "", "Status: " + report["status"], "",
             "Interpreter: `" + sys.executable + "`", "", "Products: " + str(len(specs)),
             "Processes: " + str(len(results)), "", "| Check | Status |", "| --- | --- |"]
    lines.extend("| " + c["check"] + " | " + c["status"] + " |" for c in checks)
    lines.extend(["", "## Scope", ""] + ["- " + text for text in report["limitations"]])
    lines.extend(["", "## Evidence", "", "- Each *-process.json records command, exit code, PID, stdout/stderr and per-item PASS/FAIL.",
                  "- Each *-result.json records every repeat's identity or exact rejection exception.",
                  "- source-sha256-before.json and source-sha256-after.json cover the complete original candidate tree.",
                  "- fixtures/ retains tampered, wrong-pin, old-version copies; missing cases retain their directory and manifest."])
    with (output / "report.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    print(json.dumps(dict(status=report["status"], processes=len(results), checks=len(checks), output=str(output))))
    return 0 if report["status"] == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    if args.worker:
        if not args.result:
            parser.error("--worker requires --result")
        return worker(args.worker, args.result)
    return acceptance(args.source, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
