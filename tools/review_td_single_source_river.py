"""Cold-read one finite TD river/lake case and write a bounded four-layer review."""

import argparse
import json
from pathlib import Path

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_td_single_source_review import review_water_cycle_case
from terrain_pipeline.surface_rivers.metric_water_cycle import load_water_cycle

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "verification/td-natural-river-stages/water-cycle-20261011-final-bound/rain-closed-30-evidence.npz"
DEFAULT_REFERENCE = ROOT / "verification/td-natural-river-stages/channel-real-calibration-20261011-04/reference.json"


def review(evidence_path=DEFAULT_EVIDENCE, reference_path=DEFAULT_REFERENCE):
    evidence_path = Path(evidence_path)
    evidence_sha = file_sha256(evidence_path)
    evidence = load_water_cycle(evidence_path, expected_sha256=evidence_sha)
    reference_path = Path(reference_path)
    reference_sha = file_sha256(reference_path)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    result = review_water_cycle_case(evidence, real_reference=reference)
    result["external_files"] = {"evidence": {"path": str(evidence_path.resolve()), "sha256": evidence_sha},
                                "real_reference": {"path": str(reference_path.resolve()), "sha256": reference_sha}}
    # The review identity includes external byte pins as well as embedded evidence identities.
    from terrain_pipeline.common_infra import identity
    result["identity_sha256"] = identity({}, {k: v for k, v in result.items() if k != "identity_sha256"})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(args.evidence, args.reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "identity_sha256": result["identity_sha256"]}))
