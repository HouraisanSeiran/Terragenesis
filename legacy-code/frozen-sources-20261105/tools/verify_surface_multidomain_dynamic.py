"""Fixed two-domain forest verification against the unchanged saved evaluation."""

from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import surface_multidomain_dynamic as forest
from terrain_pipeline.surface_domain_prepare import load_surface_domains
from tests.test_surface_dynamic_prepare import SAVED_DOMAIN_PATH, SAVED_DOMAIN_SHA256, generation_disabled
from tests.test_surface_multidomain_dynamic import SurfaceMultidomainDynamicTests, forcing, propagation_forcing


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def retain(name, result, directory):
    path = directory / (name + ".npz")
    forest.save_surface_multidomain_dynamic(result, path)
    with ExitStack() as stack:
        generation_disabled(stack)
        loaded = forest.load_surface_multidomain_dynamic(path)
        forest.query_surface_multidomain_dynamic(loaded)
    dynamic = loaded["dynamic"]
    ledgers = loaded["domain_ledger_m3"]
    if loaded["identity_sha256"] != result["identity_sha256"]:
        raise AssertionError("static identity changed")
    return {"bundle": str(path.resolve()), "file_sha256": file_hash(path),
            "identity_sha256": loaded["identity_sha256"], "status": dynamic["status"],
            "committed_steps": dynamic["committed_steps"], "domain_ids": list(loaded["domain_ids"]),
            "nodes": len(loaded["node_keys"]), "edges": len(loaded["edges"]),
            "outlets": int(dynamic["inputs"]["boundary_mask"].sum()),
            "wet_cells": sum(len(binding["wet_cell_ids"]) for binding in loaded["bindings"]),
            "initial_internal_storage_m3": float(dynamic["storage_m3"][0].sum()),
            "source_proof_sha256": [binding["source_proof_sha256"] for binding in loaded["bindings"]],
            "binding_sha256": [binding["identity_sha256"] for binding in loaded["bindings"]],
            "maximum_domain_residual_m3": float(np.max(np.abs(ledgers[:, :, 5]))) if ledgers.size else 0.,
            "maximum_global_residual_m3": float(np.max(np.abs(dynamic["ledger_m3"][:, 5])))
            if dynamic["ledger_m3"].size else 0.,
            "domain_local_volume_m3": ledgers[:, :, 1].sum(axis=0).tolist(),
            "domain_boundary_inward_m3": ledgers[:, :, 2].sum(axis=0).tolist(),
            "static_no_generation_reload": True}


def main():
    started = datetime.now(timezone.utc)
    directory = ROOT / "verification/surface-multidomain-dynamic" / ("run-" + started.strftime("%Y%m%dT%H%M%S.%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    implementation = [ROOT / item for item in (
        "terrain_pipeline/surface_multidomain_dynamic.py", "tests/test_surface_multidomain_dynamic.py",
        "tools/verify_surface_multidomain_dynamic.py", "docs/surface-multidomain-dynamic-v1.md")]
    report = {"started_utc": started.isoformat(), "status": "running", "algorithm_version": forest.VERSION,
              "source": str(SAVED_DOMAIN_PATH.resolve()), "source_file_sha256": file_hash(SAVED_DOMAIN_PATH),
              "implementation_files": {str(path.resolve()): file_hash(path) for path in implementation},
              "cases": {}, "natural_outlets_certified": False, "full_dynamic_wave_prepared": False,
              "physics_limit": "fixed area A0, caller constant linear K, explicit local Q and tailwater; no V(h), momentum or tides"}
    try:
        if report["source_file_sha256"] != SAVED_DOMAIN_SHA256:
            raise AssertionError("old prepared source SHA256 differs")
        evaluation = load_surface_domains(SAVED_DOMAIN_PATH)
        report["evaluation_sha256"] = evaluation["identity_sha256"]
        cases = {"pulse": propagation_forcing(), "domain2-tailwater-rise": propagation_forcing(raised=True),
                 "cancelled-prefix": {**forcing(), "cancel": iter([False, False, True]).__next__}}
        failed = forcing()
        failed["tailwater_m"][2:, :] = 100.
        cases["failed-prefix"] = failed
        for name, values in cases.items():
            result = forest.prepare_surface_multidomain_dynamic(evaluation, **values)
            report["cases"][name] = retain(name, result, directory)
        pulse = forest.load_surface_multidomain_dynamic(report["cases"]["pulse"]["bundle"])
        raised = forest.load_surface_multidomain_dynamic(report["cases"]["domain2-tailwater-rise"]["bundle"])
        if (report["cases"]["pulse"]["nodes"] != 16 or report["cases"]["pulse"]["edges"] != 14 or
                report["cases"]["pulse"]["outlets"] != 2 or report["cases"]["pulse"]["wet_cells"] != 676 or
                report["cases"]["pulse"]["initial_internal_storage_m3"] != 322.):
            raise AssertionError("fixed forest counts changed")
        if (not np.array_equal(pulse["dynamic"]["stage_m"][:, :8], raised["dynamic"]["stage_m"][:, :8]) or
                not np.any(raised["dynamic"]["qedges_m3_s"][:, 7:] < 0)):
            raise AssertionError("domain independence/reverse flux changed")
        report["domain1_unchanged_by_domain2_tailwater"] = True
        report["domain2_negative_edge_flux_values"] = int((raised["dynamic"]["qedges_m3_s"][:, 7:] < 0).sum())
        with (directory / "focused-tests.txt").open("x", encoding="utf8") as stream:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceMultidomainDynamicTests)
            tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        report["focused_tests"] = {"run": tests.testsRun, "failures": len(tests.failures),
                                   "errors": len(tests.errors), "log": str((directory / "focused-tests.txt").resolve()),
                                   "file_sha256": file_hash(directory / "focused-tests.txt")}
        if not tests.wasSuccessful() or file_hash(SAVED_DOMAIN_PATH) != SAVED_DOMAIN_SHA256:
            raise AssertionError("focused tests or immutable source check failed")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                        allow_nan=False), encoding="utf8")
        print(str(directory.resolve()))


if __name__ == "__main__":
    main()
