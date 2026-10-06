"""Run the portable artifact contract gate without GPU or game services."""

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "verification" / "terrain-artifacts"


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_terrain_artifacts")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {"gate": "terrain_artifact_contract_v1", "passed": result.wasSuccessful(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "scope": "portable contract only; no consumer, naturalness or hydrology acceptance"}
    (OUTPUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
