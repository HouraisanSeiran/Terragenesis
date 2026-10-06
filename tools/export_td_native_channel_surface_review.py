"""Create a standalone HTML review from an externally pinned surface report."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_native_channel_surface_review import export_surface_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pins = export_surface_review(args.report, expected_report_sha256=args.report_sha256, output_path=args.output)
    print(f"Saved read-only bed review: {args.output}")
    print(f"Surface SHA256: {pins['surface']['expected_sha256']}")


if __name__ == "__main__":
    main()
