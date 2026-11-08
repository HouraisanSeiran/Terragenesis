"""Independent cold audit for a saved fine-bed/material candidate."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.td_fine_bed_material import load_fine_bed_material


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(path):
    path = Path(path)
    record = load_fine_bed_material(path)
    errors = []
    for window in record["windows"]:
        if window["status"] != "candidate":
            continue
        source = window["source_surface_m"]
        derived = window["derived_bed_m"]
        cut = window["cut_fill_m3"]["cut_m3"]
        fill = window["cut_fill_m3"]["fill_m3"]
        if len(source) != len(derived) or any(len(a) != len(b) for a, b in zip(source, derived)):
            errors.append(window["window_id"] + ":shape")
        expected_cut = sum(max(float(a) - float(b), 0.) for row_a, row_b in zip(source, derived)
                           for a, b in zip(row_a, row_b)) * window["grid"]["spacing_m"] ** 2
        expected_fill = sum(max(float(b) - float(a), 0.) for row_a, row_b in zip(source, derived)
                            for a, b in zip(row_a, row_b)) * window["grid"]["spacing_m"] ** 2
        if abs(cut - expected_cut) > 1e-8 or abs(fill - expected_fill) > 1e-8:
            errors.append(window["window_id"] + ":cut_fill")
        ledger = window["material_ledger"]
        if abs(ledger["original_rock_m3"] - ledger["cut_rock_m3"]) > 1e-8:
            errors.append(window["window_id"] + ":rock_ledger")
    result = {"schema": "td-fine-bed-material-independent-audit-v1",
              "status": "passed" if not errors else "failed", "errors": errors,
              "source_sha256": sha256(path), "summary": record["summary"],
              "solver_calls": 0, "natural_outlet_verified": False}
    result["identity_sha256"] = hashlib.sha256(json.dumps(result, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
