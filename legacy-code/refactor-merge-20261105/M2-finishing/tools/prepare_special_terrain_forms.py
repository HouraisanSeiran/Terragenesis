"""Write the four L0 special-terrain form bundles for offline inspection.

Output is a scratch evidence directory, never a source cache and never verification/.
The base bed is a synthetic analytic chart; the bundles say so in their metadata and
no bundle claims real Terrain Diffusion detail.
"""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.special_terrain import KINDS, METRIC_FORMS_SCHEMA as SCHEMA, METRIC_FORMS_ALGORITHM as ALGORITHM, analytic_base_chart, build_special_form_vdm, form_preset, save_special_form_vdm
from terrain_pipeline.common_infra import file_sha256

DEFAULT_OUTPUT = Path(".scratch/special-terrain/bundles-20261019")
SOURCE_IDENTITY = "synthetic-analytic-base-plane"
PROTECTION_IDENTITY = "no-protected-cells"


def build_one(kind):
    recipe = form_preset(kind)
    chart = analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m,
                                spacing_m=recipe.spacing_m)
    mask = np.zeros(chart.shape[:2], dtype=bool)
    return build_special_form_vdm(chart, recipe=recipe, protected_mask=mask,
                                  source_identity=SOURCE_IDENTITY,
                                  protection_identity=PROTECTION_IDENTITY)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kinds", default=",".join(sorted(KINDS)))
    args = parser.parse_args(argv)
    requested = [value for value in args.kinds.split(",") if value]
    unknown = sorted(set(requested) - KINDS)
    if unknown:
        raise SystemExit(f"unknown kinds: {unknown}")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"schema": SCHEMA, "algorithm": ALGORITHM,
              "base": "synthetic_analytic", "status": "candidate",
              "forms": {}}
    for kind in sorted(set(requested)):
        result = build_one(kind)
        path = args.output / f"{kind}.npz"
        save_special_form_vdm(path, result)
        recipe = form_preset(kind)
        report["forms"][kind] = {
            "file": path.name, "sha256": file_sha256(path),
            "identity_sha256": result["identity_sha256"],
            "chart_rows": int(result["arrays"]["reference_xyz_m"].shape[0]),
            "chart_cols": int(result["arrays"]["reference_xyz_m"].shape[1]),
            "spacing_m": recipe.spacing_m, "target_count": len(recipe.targets),
            "max_relief_m": float(np.max(result["arrays"]["displacement_xyz_m"][:, :, 1])),
            "parameter_sources": result["metadata"]["parameter_sources"][kind]}
        print(f"{kind}: {path.name} identity={result['identity_sha256']}")
    report_path = args.output / "manifest-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
