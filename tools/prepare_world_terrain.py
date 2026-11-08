"""Prepare a bounded unified raw-TD terrain product."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.td_source import prepare_world_terrain as prepare

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--expected-source-identity", required=True)
    args = parser.parse_args()
    manifest, _ = prepare(args.source, args.output, expected_source_identity=args.expected_source_identity)
    print(manifest["identity"])
