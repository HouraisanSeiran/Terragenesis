"""Synthetic accepted-water to sediment-candidate verification; no solver."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_hour_pages_acceptance_io import _memory
from tests.test_td_accepted_water_morphology import AcceptedWaterMorphologyTests

if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AcceptedWaterMorphologyTests))
    rss, private = _memory()
    directory = ROOT / "verification/td-accepted-water-morphology" / ("B-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    report = dict(scope="synthetic complete-v8 acceptance to one-round candidate; no solver or real TD", tests=result.testsRun,
        passed=result.wasSuccessful(), peak_rss_bytes=rss, peak_private_bytes=private,
        within_1GiB=private is not None and max(rss, private) <= 1073741824,
        recoupling_required=True, selection="baseline pending", hydraulic_ready=False, transient_converged=False, publishable=False)
    names = ("terrain_pipeline/td_accepted_water_morphology.py", "tests/test_td_accepted_water_morphology.py",
        "tools/verify_td_accepted_water_morphology.py", ".scratch/terrain-framework/td-accepted-water-morphology-spec-v1.md",
        "terrain_pipeline/td_basin_morphology.py", "terrain_pipeline/geology.py",
        "terrain_pipeline/td_hour_pages_acceptance_io.py", 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_topology.py')
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in names}
    publish_bytes(directory / "report.json", json.dumps(report, indent=2).encode())
    print(json.dumps(dict(path=str(directory / "report.json"), sha256=file_sha256(directory / "report.json"))))
    if not result.wasSuccessful():
        raise SystemExit(1)
