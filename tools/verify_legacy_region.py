"""Fixed GPU-free gate for the validated real legacy region pair."""

import hashlib
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.legacy_region import load_legacy_region, prepare_legacy_region


SOURCE = ROOT / "verification/tuned-model/plains-geographic_v2-seed20260927-x2176-z8832.npz"
PROCESSED = ROOT / "verification/region-processing/plains-geographic_v2-seed20260927-x2176-z8832-derived.npz"
OUTPUT = ROOT / "verification/legacy-region-integration"
BASELINE = ROOT / ".scratch/terrain-framework/legacy-integration-baseline.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_baseline() -> int:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))["sha256"]
    for relative, known in expected.items():
        actual = sha256(ROOT / relative)
        if actual != known:
            raise ValueError(f"protected source changed: {relative}")
    return len(expected)


def main() -> int:
    count = verify_baseline()
    source_hash, processed_hash = sha256(SOURCE), sha256(PROCESSED)
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_legacy_region")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run = OUTPUT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    run.mkdir()
    pair = run / "pair"
    prepared = prepare_legacy_region(SOURCE, PROCESSED, pair)
    loaded = load_legacy_region(pair)
    with np.load(PROCESSED, allow_pickle=False) as archive:
        expected = (archive["processed_height"].astype(np.float64) - 62) * 6
    error = float(np.max(np.abs(loaded.reconstructed_elevation_m() - expected)))
    if error > 1e-12 or sha256(SOURCE) != source_hash or sha256(PROCESSED) != processed_hash:
        raise ValueError("real sample reconstruction or source integrity failed")
    report = {"gate": "legacy_region_integration_v1", "passed": True, "tests_run": result.testsRun,
              "protected_files_checked": count, "source_sha256": source_hash,
              "processed_sha256": processed_hash, "base_content_id": loaded.base.content_id,
              "derived_content_id": loaded.derived.content_id, "origin_m": [loaded.base.origin_x_m, loaded.base.origin_z_m],
              "spacing_m": [loaded.base.spacing_x_m, loaded.base.spacing_z_m], "shape_zx": list(loaded.shape),
              "max_reconstruction_error_m": error, "water_present": loaded.derived.water is not None,
              "pair_path": str(pair.relative_to(ROOT)),
              "scope": "existing surface pair only; no algorithm, hydrology, cave or software consumer acceptance"}
    if prepared.derived.content_id != loaded.derived.content_id:
        raise ValueError("published derived identity changed on reload")
    (run / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
