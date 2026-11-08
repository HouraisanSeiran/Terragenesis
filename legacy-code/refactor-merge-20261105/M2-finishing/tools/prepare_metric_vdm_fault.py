"""Prepare the current v2 fault; historical v1 requires an explicit replay flag."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from tools.prepare_metric_vdm_fault_v2 import prepare as prepare_latest


def prepare(configuration, expected_sha256, output):
    """Keep the pinned configuration API, but generate only the current schema."""
    configuration = Path(configuration).resolve(strict=True)
    if file_sha256(configuration) != expected_sha256:
        raise ValueError("fault configuration SHA mismatch")
    return prepare_latest(configuration, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".scratch/metric-vdm-fault" /
                        datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ"))
    parser.add_argument("--legacy-v1-replay", action="store_true",
                        help="explicitly replay the hash-pinned archived v1 algorithm")
    args = parser.parse_args()
    if args.legacy_v1_replay:
        from tools.metric_vdm_fault_legacy_v1 import replay_legacy_preparation
        result = replay_legacy_preparation(args.configuration, args.configuration_sha256, args.output)
    else:
        result = prepare(args.configuration, args.configuration_sha256, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
