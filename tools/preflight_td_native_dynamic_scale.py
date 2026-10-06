"""Write a read-only v10 native dynamic scale preparation report."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_native_dynamic_scale_preflight import preflight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = preflight()
    target = args.output.resolve()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"path": str(target), "actual_v10_profile_prepare_ready": {
        name: item["actual_v10_profile_prepare_ready"] for name, item in report["sizes"].items()},
        "solver_advanced": False}))


if __name__ == "__main__":
    main()
