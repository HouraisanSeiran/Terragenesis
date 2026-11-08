"""Build a read-only basin treatment comparison for review interfaces.

The command consumes an existing candidate record package. It never advances
hydrology, edits terrain, or selects a publishable candidate.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


SCHEMA = "td-basin-treatment-comparison-v1"


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value):
    return float(value) if value is not None else None


def build(records_path, geography_manifest=None, *, expected_sha256=None,
          baseline_inputs=None, expected_baseline_sha256=None):
    records_path = Path(records_path).resolve(strict=True)
    records_sha256 = _sha(records_path)
    if expected_sha256 is not None and records_sha256 != expected_sha256:
        raise ValueError("candidate records external hash mismatch")
    records = json.loads(records_path.read_text(encoding="utf-8"))
    if records.get("schema") != "td-basin-candidate-records-v1":
        raise ValueError("unsupported candidate records schema")
    candidates = records.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidate records are empty")
    by_id = {item.get("candidate_id"): item for item in candidates}
    if len(by_id) != len(candidates) or any(not isinstance(value, str) for value in by_id):
        raise ValueError("duplicate or invalid candidate ID")
    required = {"baseline", "valley_incision", "source_deposition"}
    if not required <= set(by_id):
        raise ValueError("baseline and both treatment candidates are required")
    verified = None
    if baseline_inputs is not None:
        if expected_sha256 is None or expected_baseline_sha256 is None:
            raise ValueError("artifact verification requires external records and baseline pins")
        path = Path(baseline_inputs).resolve(strict=True)
        if _sha(path) != expected_baseline_sha256:
            raise ValueError("baseline inputs external hash mismatch")
        from terrain_pipeline.basin_storage import load_candidate_comparison as load_candidate_comparison
        baseline = json.loads(path.read_text(encoding="utf-8"))["inputs"]
        verified = load_candidate_comparison(records_path, expected_sha256=expected_sha256,
                                             baseline_records=baseline)
    ordered_ids = ["baseline", "valley_incision", "source_deposition"]
    ordered_ids.extend(sorted(candidate_id for candidate_id in by_id if candidate_id.startswith("saddle_breach_")))
    treatments = []
    labels = {"baseline": "保留蓄水基线", "valley_incision": "有限切穿", "source_deposition": "有限填洼/沉积"}
    for candidate_id in ordered_ids:
        item = by_id[candidate_id]
        ledger = item.get("material_ledger", {})
        treatments.append({
            "candidate_id": candidate_id,
            "source_record": item.get("source"),
            "morphology_record": item.get("morphology"),
            "same_bed_saved_water_available": candidate_id == "baseline" or all(key in item for key in ("source", "hierarchy", "ordinary", "strong")),
            "label": labels.get(candidate_id, "鞍部切穿候选 " + candidate_id.removeprefix("saddle_breach_")),
            "changed_cells": int(item.get("changed_cells", 0)),
            "max_abs_delta_m": _number(item.get("max_abs_delta_m", 0.0)),
            "disturbance_m3": _number(item.get("disturbance_m3", 0.0)),
            "source_geometry_m3": _number(ledger.get("source_geometry_m3", 0.0)),
            "deposit_geometry_m3": _number(ledger.get("deposit_geometry_m3", 0.0)),
            "solid_residual_m3": _number(ledger.get("solid_residual_m3", 0.0)),
            "candidate_sensitivity_verified": bool(item.get("candidate_sensitivity_verified", False)),
            "hydraulic_ready": bool(item.get("hydraulic_ready", False)),
            "natural_outlet_verified": bool(item.get("natural_outlet_verified", False)),
            "publishable": bool(item.get("publishable", False)),
            "rejection_reasons": list(item.get("rejection_reasons", [])),
        })
    manifest = None
    if geography_manifest is not None:
        path = Path(geography_manifest).resolve(strict=True)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("format") != "geography-preparation-inventory-v1":
            raise ValueError("unsupported geography manifest")
        geography = {"path": str(path), "sha256": _sha(path),
                     "readiness": manifest.get("readiness", {}),
                     "requirements": manifest.get("requirements", {})}
    else:
        geography = {"path": None, "sha256": None,
                     "readiness": {"ready": False, "outlet_certified": False},
                     "requirements": {}, "limitation": "no geography inventory supplied"}
    report = {
        "schema": SCHEMA,
        "candidate_records": {"path": str(records_path), "sha256": _sha(records_path),
                               "selected_candidate_id": records.get("selected_candidate_id")},
        "treatments": treatments,
        "geography": geography,
        "decision": {"selected": "baseline", "automatic_adoption": False,
                      "reason": "treatments remain diagnostic until candidate sensitivity, natural outlet, and coupled hydraulic gates pass"},
        "flags": {"hydrology_recomputed": False, "terrain_written": False,
                  "cold_read_artifacts_verified": verified is not None,
                  "natural_outlet_verified": False, "hydraulic_ready": False,
                  "publishable": False},
        "limitations": ["candidate records are derived from Terrain Diffusion mountain geometry",
                        "DEM or vector boundary evidence does not certify a natural ocean mouth",
                        "comparison does not establish fine-bed or 3D channel hydraulics"],
    }
    if verified is not None:
        report["artifact_verification"] = verified
    if _sha(records_path) != records_sha256:
        raise ValueError("candidate records changed during comparison")
    report["content_sha256"] = hashlib.sha256(json.dumps(report, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--geography-manifest", type=Path)
    parser.add_argument("--expected-records-sha256")
    parser.add_argument("--baseline-inputs", type=Path)
    parser.add_argument("--expected-baseline-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("output must be a new file")
    report = build(args.records, args.geography_manifest, expected_sha256=args.expected_records_sha256,
                   baseline_inputs=args.baseline_inputs, expected_baseline_sha256=args.expected_baseline_sha256)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "schema": SCHEMA,
                      "selected": report["decision"]["selected"],
                      "treatments": len(report["treatments"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
