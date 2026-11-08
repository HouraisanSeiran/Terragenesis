"""Freeze same-product real inventories without changing their block assignments."""

import argparse
import hashlib
import json
from pathlib import Path

from terrain_pipeline.mountain_source_adapter import publish_bytes


def combine(inputs, output):
    reports = []
    pins = []
    for path in inputs:
        raw = path.read_bytes()
        report = json.loads(raw)
        if report.get("schema") != "river-reference-geographic-inventory-v1":
            raise ValueError("geographic reference inventory required")
        reports.append(report)
        pins.append({"path": path.as_posix(), "sha256": hashlib.sha256(raw).hexdigest()})
    if any(report["climate_design"] != reports[0]["climate_design"] for report in reports):
        raise ValueError("frozen climate designs differ")
    datasets = [dataset for report in reports for dataset in report["datasets"]]
    if len({dataset["id"] for dataset in datasets}) != len(datasets):
        raise ValueError("dataset IDs overlap")
    result = {"schema": "river-reference-geographic-inventory-v1", "status": "completed_same_product_combined_inventory",
              "source_product": "CIAT_CSI_hole_filled_SRTM_v4.1", "input_inventories": pins,
              "climate_design": reports[0]["climate_design"], "datasets": datasets,
              "design": "concatenate_frozen_real_inventories_preserving_roles_and_eligibility",
              "independence": "same_product_spatial_dependence_retained;overlap_and_pairs_only_within_same_target_CRS",
              "comparison_scope": "relief_and_grid_geometry;BIO_context_not_mandatory_geographic_matching",
              "natural_credible": False, "natural_certification": False, "publishable": False}
    publish_bytes(output, (json.dumps(result, indent=2) + "\n").encode("utf-8"))
    return hashlib.sha256(output.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(combine(arguments.input, arguments.output))
