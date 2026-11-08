"""Export an independent offline TD review from explicit external package pins."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_basin_review import export_basin_review, load_candidate_comparison


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True, type=Path, help="JSON role -> path/expected_sha256/expected_identity")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-records", type=Path)
    parser.add_argument("--candidate-records-sha256")
    arguments = parser.parse_args()
    records = json.loads(arguments.inputs.read_text(encoding="utf-8"))
    if arguments.candidate_records:
        comparison = load_candidate_comparison(arguments.candidate_records,
            expected_sha256=arguments.candidate_records_sha256, baseline_records=records)
        if arguments.output.exists():
            raise FileExistsError(arguments.output)
        from terrain_pipeline.mountain_source_adapter import publish_bytes
        publish_bytes(arguments.output, json.dumps(comparison, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
        print(json.dumps({"comparison_path": str(arguments.output.resolve()), "selected_candidate_id": comparison["selected_candidate_id"]}, ensure_ascii=False))
    else:
        print(json.dumps(export_basin_review(records, arguments.output), ensure_ascii=False))
