"""Read-only audit of composition03 saved slice polygon/hole consumers."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.hybrid_saved_slice_geometry_adapter import consume_saved_slice, describe_saved_slice


def audit(path):
    composition = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    report = {"schema": "td-hybrid-saved-slice-consumer-audit-v1",
              "composition_path": str(Path(path).resolve()),
              "source_status": composition.get("status"),
              "source_rejection_reasons": composition.get("rejection_reasons", []),
              "ports": {}, "hydraulic_solved": False, "source_artifacts_modified": False}
    for kind, connection in composition.get("portal_connections", {}).items():
        port = report["ports"][kind] = {"slices": {}, "status": "refused"}
        try:
            for name, record in connection["exact_solid_slices"].items():
                port["slices"][name] = describe_saved_slice(record)
            port["status"] = "consumed"
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            port["error"] = type(error).__name__ + ": " + str(error)
    report["status"] = ("candidate_consumer_only" if report["ports"]
                         and all(item["status"] == "consumed" for item in report["ports"].values())
                         else "refused")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("composition", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.composition)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "candidate_consumer_only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
