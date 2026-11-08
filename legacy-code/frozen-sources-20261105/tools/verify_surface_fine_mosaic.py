"""Fixed engineering cases; retain original domain gap, never claim full mosaic."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import surface_fine_mosaic as mosaic
from terrain_pipeline.surface_domain_prepare import evaluate_surface_domains, plan_surface_domains
from terrain_pipeline.surface_network_recovery import _tree as recovery_tree
from terrain_pipeline.artifacts.contracts import digest
from tests.test_surface_domain_prepare import complete_two_domain_inputs, fine_configurations
from tests.test_surface_fine_mosaic import (
    SurfaceFineMosaicTests, build, engineering_proofs, positive_sources, wet_sources,
)


def retain(result, path, diagnostic=False):
    mosaic.save_fine_mosaic(result, path, allow_unprepared=diagnostic)
    with ExitStack() as stack:
        for name in ("prepare_fine_mosaic", "_assemble", "_mesh", "_h0_support", "_stencil", "_grid", "_ownership", "_proof_gate"):
            stack.enter_context(patch.object(mosaic, name, side_effect=AssertionError("load generated " + name)))
        for target in ("terrain_pipeline.surface_network_consumer._fine_source",
                       "terrain_pipeline.surface_network_recovery.recover_surface_network",
                       "terrain_pipeline.surface_domain_prepare.evaluate_surface_domains",
                       "terrain_pipeline.surface_network_prepare.prepare_surface_network"):
            stack.enter_context(patch(target, side_effect=AssertionError("load recovered/resampled")))
        loaded = mosaic.load_fine_mosaic(path, allow_unprepared=diagnostic)
        if not diagnostic:
            mosaic.query_fine_mosaic(loaded)
    if loaded["identity_sha256"] != result["identity_sha256"]:
        raise AssertionError("static reload changed identity")
    return {"bundle": str(path.resolve()), "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "identity_sha256": result["identity_sha256"], "status": result["status"],
            "scope": result["scope"], "full_domain_mosaic_prepared": False,
            "static_no_generation_reload": True,
            "summary": mosaic._plain(result.get("summary", {})),
            "missing_cell_count": result.get("missing_cell_count", 0),
            "cell_count": 0 if diagnostic else len(result["cells"]),
            "wet_cell_count": 0 if diagnostic else int(result["wet_cells"].sum())}


def run_cases(directory, report, args):
    proofs = engineering_proofs()
    report["source_evidence"] = []
    for index, proof in enumerate(proofs):
        arrays = {}
        tree = recovery_tree(mosaic._plain(proof), arrays)
        manifest = {"format_version": 1, "tree": tree, "tree_sha256": digest(tree)}
        path = directory / ("source-accepted-recovery-" + str(index + 1) + ".npz")
        with path.open("xb") as stream:
            np.savez_compressed(stream, manifest=json.dumps(manifest, sort_keys=True), **arrays)
        report["source_evidence"].append({"path": str(path.resolve()),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "proof_sha256": proof["identity_sha256"], "accepted": proof["accepted"],
            "validation": "existing_payload_and_proof_gate_static_no_replay",
            "original_h0_sha256": proof["summary"]["original_height_sha256"],
            "fine_spacing_m": proof["inputs"]["fine"]["spacing_x_m"]})
    dry = build(positive_sources(proofs))
    wet = build(wet_sources(proofs))
    full = build((mosaic.DomainFineSource(proofs[0], 1),))
    for name, result in (("dry-cross-precision", dry), ("wet-cross-precision", wet), ("single-proof-terminal", full)):
        report["cases"][name] = retain(result, directory / (name + ".npz"))
    shared = wet["nodes"]["wet_mask"] & (wet["nodes"]["x_m"] == 30.)
    report["cases"]["wet-cross-precision"]["shared_wet_nodes"] = int(shared.sum())
    if int(wet["wet_cells"].sum()) != 645 or int(shared.sum()) != 41:
        raise AssertionError("actual wet cross-precision fixture changed")
    candidate = plan_surface_domains(**complete_two_domain_inputs())
    prepared = evaluate_surface_domains(candidate, fine_configurations(candidate))
    try:
        build(prepared)
    except mosaic.MosaicCoverageError as error:
        diagnostic = error.diagnostic
    else:
        raise AssertionError("old ten-metre source gap was invented")
    report["cases"]["old-two-domain-gap"] = retain(diagnostic, directory / "old-two-domain-gap.npz", True)
    if diagnostic["missing_cell_count"] != 600:
        raise AssertionError("old 10m by 60m gap changed")
    try:
        build((mosaic.DomainFineSource(proofs[0], 1, (0, 61, 20, 31)),
               mosaic.DomainFineSource(proofs[1], 2, (0, 31, 15, 21))))
    except ValueError as error:
        report["cases"]["incompatible-real-wet-seam"] = {"rejected": True, "reason": str(error)}
    else:
        raise AssertionError("incompatible upstream wet seam accepted")
    if not args.skip_tests:
        with (directory / "focused-tests.txt").open("x", encoding="utf8") as stream:
            tests = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceFineMosaicTests)
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
        report["focused_tests"] = {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)}
        if not result.wasSuccessful():
            raise AssertionError("focused tests failed; retained test log")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    directory = ROOT / "verification" / "surface-fine-mosaic" / ("run-" + started.strftime("%Y%m%dT%H%M%S.%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    report = {"executed_utc": started.isoformat(), "algorithm_version": mosaic.VERSION,
              "natural_outlets_certified": False, "full_domain_mosaic_prepared": False,
              "status": "running", "cases": {}, "output_directory": str(directory.resolve()),
              "implementation_files": {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (ROOT / "terrain_pipeline/surface_fine_mosaic.py",
                               ROOT / "tests/test_surface_fine_mosaic.py",
                               ROOT / "tools/verify_surface_fine_mosaic.py",
                               ROOT / "docs/surface-fine-mosaic-v1.md")}}
    try:
        run_cases(directory, report, args)
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error), traceback=traceback.format_exc())
        with (directory / "traceback.txt").open("x", encoding="utf8") as stream:
            stream.write(report["traceback"])
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        with (directory / "report.json").open("x", encoding="utf8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
