"""Explicit read-only candidate review export under a predeclared output budget."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_candidate_weather_jobs import export_candidate_weather_review


def export(record_path, output, output_budget_bytes):
    if type(output_budget_bytes) is not int or not 0 < output_budget_bytes <= 1024 ** 3:
        raise ValueError("explicit review output budget must be in (0,1GiB]")
    record_path = Path(record_path).resolve(strict=True)
    if record_path.stat().st_size > 65536:
        raise ValueError("review external record budget exceeded")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if file_sha256(record["path"]) != record["expected_sha256"]:
        raise ValueError("candidate selection external pin mismatch")
    result = export_candidate_weather_review(record, output, output_budget_bytes=output_budget_bytes)
    output = Path(output).resolve(strict=True)
    delivery = dict(schema="td-candidate-bounded-review-delivery-v1", selection_record=record,
                    output_record=dict(path=str(output / "index.json"), expected_sha256=file_sha256(output / "index.json"),
                                       expected_identity=result["identity_sha256"]),
                    predeclared_output_budget_bytes=output_budget_bytes,
                    original_default_budget_bytes=512 * 1024 ** 2,
                    estimated_output_upper_bytes=result["estimated_output_upper_bytes"],
                    actual_artifact_bytes=result["artifact_bytes"], solver_advanced=False,
                    compute_resource_budget_bytes=1024 ** 3, selection="baseline pending",
                    hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                    scope="explicit output capacity choice only; original compute and numerical gates unchanged")
    publish_bytes(output.parent / (output.name + "-delivery.json"),
                  json.dumps(delivery, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return delivery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-budget-bytes", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.selection_record, args.output, args.output_budget_bytes)))


if __name__ == "__main__":
    main()
