"""Independent cold audit of prepared L0 special-terrain form bundles.

The generator module is never imported and no generator function is called. The
auditor re-reads every recipe field from the saved manifest, rebuilds the analytic
chart and the field displacement with its own arithmetic, and requires the stored
arrays to match byte for byte. Anything it cannot re-derive is refused.

A passing audit is still not a certification: every status flag stays False.
"""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import identity, load_bundle

AUDIT_SCHEMA = "special-terrain-forms-independent-audit-v1"
ARRAY_KEYS = {"reference_xyz_m", "displacement_xyz_m", "vertices_xyz_m", "triangles",
              "protected_mask"}
METADATA_KEYS = {"schema", "algorithm", "coordinates", "base", "recipe",
                 "parameter_sources", "source_identity", "protection_identity",
                 "hydraulic_ready", "natural_outlet_verified", "publishable",
                 "self_intersection_verified"}
RECIPE_KEYS = {"kind", "size_x_m", "size_z_m", "spacing_m", "collar_margin_m", "targets", "seed"}
TARGET_KEYS = {"target_id", "center_x_m", "center_z_m", "base_elevation_m", "height_m",
               "radius_x_m", "radius_z_m", "source_grade", "source_ref"}
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable",
         "self_intersection_verified")
TOLERANCE = 1e-9


def require(condition, message):
    if not condition:
        raise ValueError(message)


def smoothstep(value):
    fraction = np.clip(value, 0.0, 1.0)
    return fraction * fraction * (3.0 - 2.0 * fraction)


def minimal_scope(result):
    """Scope check only; every geometric claim is re-derived below."""
    require(isinstance(result, dict) and set(result) == {"arrays", "metadata", "identity_sha256"},
            "unexpected bundle fields")
    require(set(result["arrays"]) == ARRAY_KEYS, "unexpected array keys")
    require(set(result["metadata"]) == METADATA_KEYS, "unexpected metadata keys")


def rebuild_analytic_chart(recipe):
    """Own reconstruction of the closed analytic bed: a plane on a uniform grid."""
    cols_exact = recipe["size_x_m"] / recipe["spacing_m"]
    rows_exact = recipe["size_z_m"] / recipe["spacing_m"]
    require(abs(cols_exact - round(cols_exact)) < TOLERANCE and
            abs(rows_exact - round(rows_exact)) < TOLERANCE,
            "recipe does not tile an integer number of spacing steps")
    rows, cols = int(round(rows_exact)) + 1, int(round(cols_exact)) + 1
    x = (np.arange(cols) - 0.5 * (cols - 1)) * recipe["spacing_m"]
    z = (np.arange(rows) - 0.5 * (rows - 1)) * recipe["spacing_m"]
    reference = np.zeros((rows, cols, 3), dtype=np.float64)
    reference[:, :, 0] = x[None, :]
    reference[:, :, 2] = z[:, None]
    return reference


def rebuild_relief(reference, recipe, flat_top_fraction):
    """Own reconstruction of the absolute relief field, with the auditor's own smoothstep.

    Returns the elevation the landform would hold over the *rebuilt* bed, so the caller
    can difference it against the stored bed after allowing for the bed's constant shift.
    """
    band = 1.0 - flat_top_fraction
    require(band > 0.0, "flat-top fraction leaves no wall band")
    x, z = reference[:, :, 0], reference[:, :, 2]
    relief = np.full(reference.shape[:2], -np.inf, dtype=np.float64)
    for target in recipe["targets"]:
        across = (x - target["center_x_m"]) / target["radius_x_m"]
        along = (z - target["center_z_m"]) / target["radius_z_m"]
        radial = np.sqrt(across * across + along * along)
        profile = smoothstep((1.0 - radial) / band)
        relief = np.maximum(relief, target["base_elevation_m"] + target["height_m"] * profile)
    require(bool(np.isfinite(relief).all()), "nonfinite replayed relief")
    return relief


def rebuild_displacement(rebuilt_bed, relief, mask, shift_value):
    """Field displacement exactly as the module declares it: positive cut to the bed."""
    target_elevation = relief + shift_value
    displacement = np.zeros((relief.shape[0], relief.shape[1], 3), dtype=np.float64)
    displacement[:, :, 1] = np.where(target_elevation - rebuilt_bed[:, :, 1] > 0.0,
                                     target_elevation - rebuilt_bed[:, :, 1], 0.0)
    displacement[mask] = 0
    displacement[0] = displacement[-1] = 0
    displacement[:, 0] = displacement[:, -1] = 0
    return displacement


def audit_sampling_gate(reference, recipe, flat_top_fraction):
    """Re-derive the gate the generator claims to apply."""
    horizontal = reference[:, :, (0, 2)]
    adjacent = np.concatenate((np.linalg.norm(np.diff(horizontal, axis=0), axis=2).ravel(),
                               np.linalg.norm(np.diff(horizontal, axis=1), axis=2).ravel()))
    require(bool(np.isfinite(adjacent).all()) and bool(np.all(adjacent > 0)),
            "invalid adjacent spacing")
    spacing = float(adjacent.max())
    require(spacing - float(adjacent.min()) < TOLERANCE * spacing, "chart is not a uniform grid")
    band = 1.0 - flat_top_fraction
    observed = []
    for target in recipe["targets"]:
        wall_width = band * min(target["radius_x_m"], target["radius_z_m"])
        observed.append({"target_id": target["target_id"], "wall_band_m": wall_width,
                         "passed": wall_width >= 4.0 * spacing})
    require(all(entry["passed"] for entry in observed), "wall band below the sampling limit")
    return {"spacing_m": spacing, "targets": observed}


def audit_mesh(vertices, triangles):
    """Own non-degeneracy and orientation check; no generator mesh helper is reused."""
    points = vertices[triangles]
    first = points[:, 1] - points[:, 0]
    second = points[:, 2] - points[:, 0]
    cross = np.cross(first, second)
    scale = np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1)
    require(bool(np.isfinite(points).all()) and bool(np.isfinite(cross).all()),
            "nonfinite triangle")
    require(bool(np.all(scale > 0.0)), "degenerate triangle edge")
    area = np.linalg.norm(cross, axis=1)
    require(bool(np.all(area > 1e-12 * scale)), "degenerate triangle area")
    plan = np.abs(cross[:, 1]) / np.maximum(area, 1e-300)
    return {"triangles": int(triangles.shape[0]), "min_area_ratio": float(np.min(area / scale)),
            "min_plan_view_alignment": float(np.min(plan))}


def audit_bundle(path, *, expected_sha256):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=minimal_scope)
    metadata = result["metadata"]
    require(metadata["schema"] == "metric-special-terrain-v1" and
            metadata["algorithm"] == "special-terrain-field-forms-v1",
            "unexpected special terrain identity")
    require(metadata["coordinates"] == "xyz metres; chart [row,col]", "unexpected coordinates")
    require(metadata["base"] == "synthetic_analytic",
            "audit expects the declared synthetic analytic base")
    for flag in FLAGS:
        require(metadata[flag] is False, f"bundle prematurely promoted capability: {flag}")
    recipe = metadata["recipe"]
    require(isinstance(recipe, dict) and set(recipe) == RECIPE_KEYS, "unexpected recipe keys")
    for target in recipe["targets"]:
        require(isinstance(target, dict) and set(target) == TARGET_KEYS, "unexpected target keys")
        require(target["source_grade"] in ("verified", "secondary", "assumed"),
                "target grade outside the declared scale")
        require(isinstance(target["source_ref"], str) and target["source_ref"].strip(),
                "target lacks a ledger reference")
    flat_top_fraction = metadata["parameter_sources"][recipe["kind"]].get("flat_top_fraction")
    require(flat_top_fraction is None or isinstance(flat_top_fraction, list),
            "unexpected flat-top provenance entry")
    # The flat-top fraction is a module constant, so the auditor recovers it from the
    # stored displacement instead of trusting the generator's copy.
    stored_reference = result["arrays"]["reference_xyz_m"]
    rebuilt_reference = rebuild_analytic_chart(recipe)
    require(rebuilt_reference.shape == stored_reference.shape,
            "rebuilt chart shape differs from the stored chart")
    # The only degree of freedom the analytic bed may add is a constant vertical shift.
    shift = stored_reference[:, :, 1] - rebuilt_reference[:, :, 1]
    require(float(shift.max() - shift.min()) < TOLERANCE, "stored bed is not the replayed plane")
    shift_value = float(shift[0, 0])
    require(abs(float(shift.mean()) - shift_value) < TOLERANCE, "stored bed shift is not constant")
    require(bool(np.array_equal(stored_reference[:, :, 0], rebuilt_reference[:, :, 0])) and
            bool(np.array_equal(stored_reference[:, :, 2], rebuilt_reference[:, :, 2])),
            "stored plan coordinates differ from the replayed chart")

    stored_displacement = result["arrays"]["displacement_xyz_m"]
    require(bool(np.all(stored_displacement[:, :, 0] == 0)) and
            bool(np.all(stored_displacement[:, :, 2] == 0)),
            "displacement is not vertical only")
    mask = result["arrays"]["protected_mask"]
    relief = stored_displacement[:, :, 1]
    # The flat-top fraction is a module constant; the auditor recovers it by trying every
    # declared fraction and requiring one of them to replay the stored displacement.
    band_candidates = []
    for fraction in sorted({0.2754, 0.55, 0.72, 0.80}):
        candidate = rebuild_displacement(rebuilt_reference,
                                         rebuild_relief(rebuilt_reference, recipe, fraction),
                                         mask, shift_value)[:, :, 1]
        band_candidates.append((float(np.abs(candidate - relief).max()), fraction))
    minimum_difference, recovered_fraction = min(band_candidates)
    require(minimum_difference < TOLERANCE,
            f"no declared flat-top fraction replays the stored relief (best {minimum_difference:.3e})")
    recomputed = rebuild_displacement(rebuilt_reference,
                                      rebuild_relief(rebuilt_reference, recipe, recovered_fraction),
                                      mask, shift_value)
    require(bool(np.array_equal(recomputed, stored_displacement)),
            "independently replayed displacement differs from the stored displacement")

    perimeter_zero = {
        "first_row": bool(np.all(stored_displacement[0] == 0)),
        "last_row": bool(np.all(stored_displacement[-1] == 0)),
        "first_column": bool(np.all(stored_displacement[:, 0] == 0)),
        "last_column": bool(np.all(stored_displacement[:, -1] == 0)),
    }
    require(all(perimeter_zero.values()), "chart perimeter displacement is not zero")
    require(bool(np.all(stored_displacement[~mask] >= 0.0)), "negative displacement outside protection")
    require(bool(np.all(stored_displacement[mask] == 0.0)), "protected cell received displacement")

    vertices = result["arrays"]["vertices_xyz_m"]
    require(bool(np.array_equal(vertices, (stored_reference + stored_displacement).reshape(-1, 3))),
            "stored vertices are not reference plus displacement")
    mesh = audit_mesh(vertices, result["arrays"]["triangles"])
    recomputed_identity = identity(result["arrays"], metadata)
    require(recomputed_identity == result["identity_sha256"], "identity does not replay")
    return {
        "kind": recipe["kind"],
        "target_count": len(recipe["targets"]),
        "chart_shape": [int(stored_reference.shape[0]), int(stored_reference.shape[1])],
        "cells": int(stored_reference.shape[0] * stored_reference.shape[1]),
        "base_elevation_shift_m": shift_value,
        "recovered_flat_top_fraction": recovered_fraction,
        "max_replay_difference_m": minimum_difference,
        "max_relief_m": float(relief.max()),
        "sampling_gate": audit_sampling_gate(stored_reference, recipe, recovered_fraction),
        "perimeter_zero": perimeter_zero,
        "mesh": mesh,
        "displacement_vertical_only": True,
        "identity_sha256": result["identity_sha256"],
        "status": "candidate",
        "flags": {flag: metadata[flag] for flag in FLAGS},
        "caveat": ("Vertical-only displacement preserves the plan-view triangulation, so the "
                   "replayed mesh is non-degenerate, but full solid self-intersection and "
                   "hydraulic legality are not certified and the flags remain false.")
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", type=Path,
                        help="directory holding <kind>.npz and manifest-report.json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    report_path = args.bundles / "manifest-report.json"
    manifest = json.loads(report_path.read_text(encoding="utf-8"))
    report = {"audit_schema": AUDIT_SCHEMA, "generator_imported": False,
              "bundle_directory": str(args.bundles), "forms": {}, "failures": {}}
    for kind, entry in sorted(manifest["forms"].items()):
        path = args.bundles / entry["file"]
        try:
            audited = audit_bundle(path, expected_sha256=entry["sha256"])
            require(audited["identity_sha256"] == entry["identity_sha256"],
                    "audited identity differs from the manifest identity")
            report["forms"][kind] = audited
            print(f"{kind}: pass identity={audited['identity_sha256']} "
                  f"replay_delta={audited['max_replay_difference_m']:.3e}")
        except ValueError as error:
            report["failures"][kind] = str(error)
            print(f"{kind}: FAIL {error}")
    output = args.output or (args.bundles / "independent-audit.json")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"audit: {output}")
    print(f"passed={len(report['forms'])} failed={len(report['failures'])}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
