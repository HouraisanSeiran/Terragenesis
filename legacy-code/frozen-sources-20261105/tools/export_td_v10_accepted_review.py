"""Export native review using independently bound complete baseline acceptance."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_native_weather_v10_review import export_native_weather_v10_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(args.acceptance_record.read_text(encoding="utf-8"))
    path = Path(record["path"])
    if file_sha256(path) != record["expected_sha256"]:
        raise ValueError("independent acceptance external pin mismatch")
    acceptance = json.loads(path.read_text(encoding="utf-8"))
    if acceptance.get("schema") != "td-independent-final-spatial-weather-v10-v1" or acceptance.get("io_chain_accepted") is not True:
        raise ValueError("complete independent acceptance required")
    result = export_native_weather_v10_review(acceptance["index_path"], args.output,
                                             acceptance_arguments=acceptance["acceptance_arguments"])
    print(json.dumps(dict(path=str(args.output / "index.json"), expected_sha256=file_sha256(args.output / "index.json"),
        expected_identity=result["identity_sha256"], numerical_gate_passed=acceptance["all_saved_numerical_gates_passed"])))


if __name__ == "__main__":
    main()
