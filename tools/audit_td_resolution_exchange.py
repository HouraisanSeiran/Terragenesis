"""Audit pinned M7 water/solid traces without invoking either solver."""
import argparse
import json
from pathlib import Path
from terrain_pipeline.surface_rivers.metric_resolution_exchange import audit_comparison


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("comparison", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_comparison(args.comparison), indent=2))


if __name__ == "__main__":
    main()
