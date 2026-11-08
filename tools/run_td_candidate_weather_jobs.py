"""Explicit serial candidate weather preparation/execution, dry by default."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_candidate_weather_jobs import (prepare_candidate_weather_jobs, run_candidate_weather_job,
    publish_candidate_weather_selection, export_candidate_weather_review)
from terrain_pipeline.common_infra import file_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("prepare", "run", "select", "review"), required=True)
    parser.add_argument("--inputs", type=Path, required=True, help="prepare: external pinned records JSON; run: plan record JSON")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-id", choices=("valley_incision", "source_deposition"))
    parser.add_argument("--execute", action="store_true")
    arguments = parser.parse_args()
    inputs = json.loads(arguments.inputs.read_text(encoding="utf8"))
    if arguments.stage == "prepare":
        if arguments.execute:
            parser.error("prepare does not execute")
        result = prepare_candidate_weather_jobs(inputs["baseline_acceptance_record"], inputs["candidate_topology_records"], arguments.output)
    elif arguments.stage == "run":
        if arguments.candidate_id is None:
            parser.error("run requires --candidate-id")
        result = run_candidate_weather_job(inputs, arguments.output, candidate_id=arguments.candidate_id, execute=arguments.execute)
    elif arguments.stage == "select":
        if arguments.execute:
            parser.error("selection is pure IO")
        result = publish_candidate_weather_selection(arguments.output, **inputs)
    else:
        if arguments.execute:
            parser.error("review is pure IO")
        result = export_candidate_weather_review(inputs, arguments.output)
    if (arguments.output/"index.json").exists():
        record = dict(path=str((arguments.output/"index.json").absolute()), expected_sha256=file_sha256(arguments.output/"index.json"), expected_identity=result["identity_sha256"])
        (arguments.output.parent/(arguments.output.name+"-record.json")).write_text(json.dumps(record, indent=2), encoding="utf8")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
