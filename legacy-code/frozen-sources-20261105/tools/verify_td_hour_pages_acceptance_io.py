"""Small pure-IO fixture acceptance; never launches a hydrological solver."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_hour_pages_acceptance_io import _memory
from tests.test_td_hour_pages_acceptance_io import HourPagesAcceptanceTests


def verify():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HourPagesAcceptanceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    rss, private = _memory()
    destination = ROOT / "verification/td-hour-pages-acceptance-io" / ("B-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    names = ("terrain_pipeline/td_hour_pages_acceptance_io.py", "tests/test_td_hour_pages_acceptance_io.py", "tools/verify_td_hour_pages_acceptance_io.py", ".scratch/terrain-framework/td-hour-pages-acceptance-spec-v1.md")
    report = {"scope": "synthetic pureIO acceptance and negative fixtures only", "tests": result.testsRun,
        "passed": result.wasSuccessful(), "failures": len(result.failures), "errors": len(result.errors),
        "peak_rss_bytes": rss, "peak_private_bytes": private,
        "synthetic_within_1GiB": private is not None and max(rss, private) <= 1073741824,
        "real_final_index_coldread": False, "actual_execution_resource_verified": False,
        "hydraulic_ready": False, "transient_converged": False, "publishable": False,
        "code_sha256": {name: file_sha256(ROOT / name) for name in names}}
    publish_bytes(destination / "report.json", json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"path": str(destination / "report.json"), "sha256": file_sha256(destination / "report.json")}))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    verify()
