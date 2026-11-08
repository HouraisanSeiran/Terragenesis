"""Explicit historical hydraulics CLI; never selected by current generation."""

import argparse
import sys

from tools.hybrid_hydraulics_legacy import HydraulicsLegacyReplay

MODULES = tuple("tools.prepare_hybrid_river_hydraulics" + suffix
                for suffix in ("", "_v2", "_v3", "_v4", "_v5", "_v6", "_v7", "_v8")) + (
    "tools.audit_hybrid_river_hydraulics", "tools.audit_hybrid_river_hydraulics_diagnostic",
    "tools.audit_hybrid_river_hydraulics_v8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", choices=MODULES, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    replay = HydraulicsLegacyReplay()
    original_argv = sys.argv
    try:
        sys.argv = [args.module] + forwarded
        replay.load(args.module).main()
    finally:
        sys.argv = original_argv
        replay.close()


if __name__ == "__main__":
    main()
