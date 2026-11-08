"""Audit a pinned interrupted v10 run without resuming or accepting it."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_weather_checkpoint_recovery import inspect_prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--run-inputs-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = inspect_prefix(arguments.run, run_inputs_sha256=arguments.run_inputs_sha256)
    output = arguments.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"path": str(output), "verified_hours": {name: group["verified_hours"]
                      for name, group in result["groups"].items()}, "resource_authenticated": False}))


if __name__ == "__main__":
    main()
