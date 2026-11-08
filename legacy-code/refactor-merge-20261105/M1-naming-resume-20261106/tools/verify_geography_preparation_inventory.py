"""Fixed, read-only D:/geography inventory verification."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_source import load, prepare_inventory as prepare, save


def main():
    test_path = ROOT / "tests/test_geography_preparation_inventory.py"
    spec = importlib.util.spec_from_file_location("test_geography_preparation_inventory", test_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError(log.getvalue())
    source = Path("D:/geography")
    source_tif = "01-完整流域样本/data/srtm_61_07.tif"
    before = prepare(source)
    manifest = prepare(Path("D:/geography"))
    output = ROOT / "verification/geography-preparation-inventory" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    saved = save(manifest, output / "inventory.json")
    assert load(saved) == manifest
    assert manifest["readiness"]["ready"] is False
    after = prepare(source)
    if before["identity"] != after["identity"]:
        raise AssertionError("source inventory changed during verification")
    (output / "unittest.log").write_text(log.getvalue(), encoding="utf-8")
    implementation = [ROOT / "terrain_pipeline/geography_preparation_inventory.py", ROOT / "tests/test_geography_preparation_inventory.py",
                      ROOT / "tools/verify_geography_preparation_inventory.py", ROOT / "docs/geography-preparation-inventory-v1.md"]
    summary = {"identity": manifest["identity"], "file_count": manifest["file_count"],
               "total_bytes": manifest["total_bytes"], "source_classes": dict(sorted(Counter(file["source_class"] for file in manifest["files"]).items())),
               "readiness": manifest["readiness"], "inventory": str(saved), "verifier_passed": True,
               "tests_run": result.testsRun, "tests_skipped": len(result.skipped),
               "source_identity_before": before["identity"], "source_identity_after": after["identity"],
               "source_tif_sha256": next(file["sha256"] for file in manifest["files"] if file["path"] == source_tif),
               "implementation_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in implementation}}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
