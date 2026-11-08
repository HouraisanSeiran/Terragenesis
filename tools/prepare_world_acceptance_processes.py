"""Run same-source 90 m seasonal acceptance processes without a GPU."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.environment_product import prepare_world_acceptance_processes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terrain", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--spinup-years", type=int, default=1)
    parser.add_argument("--river-display-q", type=float, default=2.)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    report = prepare_world_acceptance_processes(args.terrain, args.output,
        spinup_years=args.spinup_years, river_display_q_m3_s=args.river_display_q, resume=args.resume)
    print(f"Finished {report['shape']}, {report['runtime_seconds']:.1f}s")


if __name__ == "__main__":
    main()
