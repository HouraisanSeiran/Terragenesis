"""Write the v2 facet-noise + hydraulic-dissection surface bundles for each L0 kind.

The parent bundles are the L0 chart forms written by
``tools/prepare_special_terrain_forms.py``; this tool consumes them read-only and
never rewrites them.  Output is a scratch evidence directory -- never a source cache
and never ``verification/``.  The base bed stays the synthetic analytic chart, so no
bundle claims real Terrain Diffusion detail and none of the four status flags is
turned on.
"""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.special_terrain import KINDS, load_special_form_vdm
from terrain_pipeline.special_terrain import METRIC_SURFACE_ALGORITHM as ALGORITHM, METRIC_SURFACE_SCHEMA as SCHEMA, SUPERSEDES_ALGORITHM, build_special_form_surface, save_special_form_surface, surface_preset
from terrain_pipeline.common_infra import file_sha256


DEFAULT_PARENTS = Path(".scratch/special-terrain/bundles-20261019")
DEFAULT_OUTPUT = Path(".scratch/special-terrain/surface-20261020")


def load_parent(parents, kind):
    manifest = json.loads((parents / "manifest-report.json").read_text(encoding="utf-8"))
    entry = manifest["forms"][kind]
    parent = load_special_form_vdm(parents / entry["file"], expected_sha256=entry["sha256"],
                                   expected_identity=entry["identity_sha256"])
    return parent, manifest, entry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parents", type=Path, default=DEFAULT_PARENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--kinds", default=",".join(sorted(KINDS)))
    args = parser.parse_args(argv)
    requested = [value for value in args.kinds.split(",") if value]
    unknown = sorted(set(requested) - KINDS)
    if unknown:
        raise SystemExit(f"unknown kinds: {unknown}")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"schema": SCHEMA, "algorithm": ALGORITHM,
              "supersedes_algorithm": SUPERSEDES_ALGORITHM,
              "parents": str(args.parents), "status": "candidate", "forms": {}}
    for kind in sorted(set(requested)):
        parent, manifest, entry = load_parent(args.parents, kind)
        roughness, dissection = surface_preset(kind)
        result = build_special_form_surface(parent, roughness=roughness, dissection=dissection)
        path = args.output / f"{kind}.npz"
        save_special_form_surface(path, result)
        metadata, arrays = result["metadata"], result["arrays"]
        change = arrays["erosion_change_m"]
        spacing = float(arrays["reference_xyz_m"][0, 1, 0] - arrays["reference_xyz_m"][0, 0, 0])
        report["forms"][kind] = {
            "file": path.name, "sha256": file_sha256(path),
            "identity_sha256": result["identity_sha256"],
            "parent_file": entry["file"], "parent_sha256": entry["sha256"],
            "parent_identity_sha256": metadata["parent_identity_sha256"],
            "chart_rows": int(arrays["reference_xyz_m"].shape[0]),
            "chart_cols": int(arrays["reference_xyz_m"].shape[1]),
            "spacing_m": spacing,
            "relief_reference_m": metadata["relief_reference_m"],
            "roughened_relief_reference_m": metadata["roughened_relief_reference_m"],
            "facet_recipe": metadata["facet_recipe"],
            "facet_wavelengths_m": metadata["facet_wavelengths_m"],
            "dissection_recipe": metadata["dissection_recipe"],
            "kernel_revisions": metadata["kernel_revisions"],
            "ledger": metadata["ledger"],
            "net_change_m3_recomputed": float(np.sum(change) * spacing ** 2),
            "target_count": len(metadata["targets"]),
        }
        print(f"{kind}: {path.name} identity={result['identity_sha256'][:16]} "
              f"relief={metadata['relief_reference_m']:.2f}->"
              f"{metadata['roughened_relief_reference_m']:.2f} m "
              f"incision_max={metadata['ledger']['maximum_incision_m']:.3f} m "
              f"relax_converged={metadata['ledger']['relaxation_converged']}")
    report_path = args.output / "manifest-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
