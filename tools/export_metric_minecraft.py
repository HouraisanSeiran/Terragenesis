"""Export a validated metric region for the read-only Minecraft adapter."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.minecraft_export import export_metric_minecraft


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("region", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    print(export_metric_minecraft(arguments.region, arguments.destination))


if __name__ == "__main__":
    main()
