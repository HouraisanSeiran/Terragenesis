"""Native review fixture verification, without hydrological advancement."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import publish_bytes, file_sha256
from terrain_pipeline.td_hour_pages_acceptance_io import _memory
from tests.test_td_hour_pages_review import HourPagesReviewTests


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HourPagesReviewTests))
    rss, private = _memory()
    destination = ROOT / "verification/td-hour-pages-review" / ("B-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    names = ("terrain_pipeline/td_hour_pages_review.py", "tests/test_td_hour_pages_review.py", "tools/verify_td_hour_pages_review.py", ".scratch/terrain-framework/td-hour-pages-review-integration-v1.md")
    report = dict(scope="synthetic saved-v8 24hour native review only; no solver", tests=result.testsRun, passed=result.wasSuccessful(),
        peak_rss_bytes=rss, peak_private_bytes=private, within_1GiB=private is not None and max(rss, private) <= 1073741824,
        real_final_export=False, hydraulic_ready=False, transient_converged=False, publishable=False,
        default_selected_steps_s=[1.25], default_hour_flux=False, default_output_budget_bytes=536870912,
        synthetic_default_output_bytes=HourPagesReviewTests.default_output_bytes,
        synthetic_default_artifact_count=HourPagesReviewTests.default_artifact_count,
        code_sha256={name: file_sha256(ROOT / name) for name in names})
    publish_bytes(destination / "report.json", json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination / "report.json"), sha256=file_sha256(destination / "report.json"))))
    if not result.wasSuccessful():
        raise SystemExit(1)
