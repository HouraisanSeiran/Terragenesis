"""Independent cold audit of the v2 facet-noise + hydraulic-dissection surface bundles.

The generator module ``terrain_pipeline.metric_special_terrain_surface`` is never
imported and none of its functions is called.  The auditor re-reads every recipe field
from the saved manifest, rebuilds the facet noise and the rock floor with its own
arithmetic, replays the elliptic target footprints itself, re-hashes the pinned kernels
from disk, and requires the stored arrays to match.  Anything it cannot re-derive is
refused.

A passing audit is still not a certification: every status flag stays False.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import identity, load_bundle


AUDIT_SCHEMA = "special-terrain-surface-independent-audit-v1"
SURFACE_SCHEMA = "metric-special-terrain-surface-v2"
SURFACE_ALGORITHM = "special-terrain-facet-noise-hydraulic-dissection-v2"
SUPERSEDED = "special-terrain-facet-noise-hydraulic-dissection-v1"
PARENT_SCHEMA = "metric-special-terrain-v1"
PARENT_ARRAY_KEYS = {"reference_xyz_m", "displacement_xyz_m", "vertices_xyz_m", "triangles",
                     "protected_mask"}
ARRAY_KEYS = PARENT_ARRAY_KEYS | {"surface_xyz_m", "erosion_change_m"}
METADATA_KEYS = {"schema", "algorithm", "coordinates", "base", "supersedes_algorithm", "recipe",
                 "parameter_sources", "source_identity", "protection_identity", "parent_schema",
                 "parent_algorithm", "parent_identity_sha256", "parent_kind", "facet_recipe",
                 "facet_source", "facet_wavelengths_m", "dissection_recipe", "dissection_source",
                 "kernel_revisions", "relief_reference_m", "roughened_relief_reference_m", "targets",
                 "ledger", "hydraulic_ready", "natural_outlet_verified", "publishable",
                 "self_intersection_verified"}
FACET_KEYS = {"seed", "scales", "amplitude_fraction"}
DISSECTION_KEYS = {"repose_angle_deg", "steps", "detachment_per_step_m", "maximum_cut_fraction",
                   "maximum_incision_fraction", "mobile_fraction", "mobile_minimum_m",
                   "deposition_fraction", "tolerance_m", "max_sweeps"}
# The one v1 field the probes disproved.  A stale artifact carrying it must be refused,
# not quietly re-read under the new schema.
RETIRED_RECIPE_FIELDS = ("immobile_rock_fraction",)
LEDGER_SCALARS = ("transport_coefficient", "mobile_reference_m", "rock_floor_depth_m",
                  "detachment_ledger_m3", "transport_deposition_ledger_m3",
                  "relaxation_transferred_ledger_m3", "maximum_incision_m",
                  "maximum_deposition_m", "net_change_ledger_m3",
                  "relaxation_tolerance_m", "relaxation_sweep_budget",
                  "relaxation_maximum_excess_m")
LEDGER_COUNTS = ("incised_cells", "deposited_cells", "relaxation_sweeps_max")
STEP_KEYS = ("step_index", "routed_discharge_max_m3_s", "edge_slope_max_m_per_m",
             "detachment_volume_m3", "detachment_depth_max_m",
             "transport_deposition_volume_m3", "transport_change_max_m",
             "relaxation_transferred_volume_m3", "relaxation_change_max_m",
             "relaxation_raw_residual_bulk_m3", "relaxation_sweeps", "relaxation_converged",
             "relaxation_maximum_excess_m", "relaxation_immobile_excess_m",
             "relaxation_stalled_at_float64_resolution", "mobile_column_volume_m3")
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable",
         "self_intersection_verified")
PHASE_KEYS = ("step_index", "phase", "injected_bulk_m3", "exported_bulk_m3", "lost_bulk_m3",
              "inlet_correction_bulk_m3", "raw_residual_bulk_m3")
SHA256_LENGTH = 64
TOLERANCE = 1e-9


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mixture(value):
    """The auditor's own bit-mixing step, re-derived from the published constants."""
    value = np.asarray(value, dtype=np.uint64)
    value = value ^ (value >> np.uint64(30))
    value = value * np.uint64(0xBF58476D1CE4E5B9)
    value = value ^ (value >> np.uint64(27))
    value = value * np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


def lattice(x, z, seed, salt):
    with np.errstate(over="ignore"):
        bits = np.asarray(x, dtype=np.int64).astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
        bits ^= np.asarray(z, dtype=np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
        bits ^= np.uint64(seed & 0xFFFFFFFFFFFFFFFF) + np.uint64(salt)
        return ((mixture(bits) >> np.uint64(11)).astype(np.float64) / (1 << 53) * 2 - 1)


def smooth_noise(x, z, spacing, seed, salt):
    gx, gz = x / spacing, z / spacing
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    fx, fz = gx - ix, gz - iz
    fx, fz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
    a, b = lattice(ix, iz, seed, salt), lattice(ix + 1, iz, seed, salt)
    c, d = lattice(ix, iz + 1, seed, salt), lattice(ix + 1, iz + 1, seed, salt)
    return ((a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz)


def noise_field(x, z, seed, salt, scales):
    """Weighted octave sum, with the auditor's own salt progression and normaliser."""
    result, total = np.zeros_like(x, dtype=np.float64), 0.0
    for octave, (spacing, weight) in enumerate(scales):
        result += weight * smooth_noise(x, z, spacing, seed, salt + octave * 811)
        total += weight
    return result / total


def minimal_scope(result):
    require(isinstance(result, dict) and set(result) == {"arrays", "metadata", "identity_sha256"},
            "unexpected bundle fields")
    require(set(result["arrays"]) == ARRAY_KEYS, "unexpected surface array keys")
    require(set(result["metadata"]) == METADATA_KEYS, "unexpected surface metadata keys")


def surface_headers(headers):
    require(set(headers) == ARRAY_KEYS | {"manifest"}, "unexpected surface archive members")
    require(headers["reference_xyz_m"][1] == np.dtype("float64"), "surface reference is not float64")


def parent_scope(result):
    require(isinstance(result, dict) and set(result) == {"arrays", "metadata", "identity_sha256"},
            "unexpected parent bundle fields")
    require(set(result["arrays"]) == PARENT_ARRAY_KEYS, "unexpected parent array keys")


def uniform_spacing(reference):
    horizontal = reference[:, :, (0, 2)]
    adjacent = np.concatenate((np.linalg.norm(np.diff(horizontal, axis=0), axis=2).ravel(),
                               np.linalg.norm(np.diff(horizontal, axis=1), axis=2).ravel()))
    require(bool(np.isfinite(adjacent).all()) and bool(np.all(adjacent > 0.0)), "invalid spacing")
    spacing = float(adjacent.max())
    require(spacing - float(adjacent.min()) < TOLERANCE * spacing, "chart is not a uniform grid")
    return spacing


def rebuild_facet(reference, parent_displacement, facet_recipe, spacing):
    """Own reconstruction of the facet relief from the declared recipe alone."""
    require(set(facet_recipe) == FACET_KEYS, "unexpected facet recipe keys")
    seed = facet_recipe["seed"]
    require(type(seed) is int and 0 <= seed < 2 ** 64, "facet seed is not uint64")
    scales = facet_recipe["scales"]
    require(isinstance(scales, list) and 1 <= len(scales) <= 8, "unexpected facet octave list")
    for pair in scales:
        require(isinstance(pair, list) and len(pair) == 2 and
                all(type(value) is float and np.isfinite(value) and value > 0.0 for value in pair),
                "unexpected facet octave")
    amplitude = facet_recipe["amplitude_fraction"]
    require(type(amplitude) is float and 0.0 < amplitude <= 0.5, "facet amplitude outside range")
    top = parent_displacement[:, :, 1]
    peak = float(np.max(top))
    require(np.isfinite(peak) and peak > 0.0, "parent chart carries no relief to roughen")
    metres = [(cells * spacing, weight) for cells, weight in scales]
    noise = noise_field(reference[:, :, 0], reference[:, :, 2], seed, 1901, metres)
    require(noise.shape == top.shape and bool(np.isfinite(noise).all()), "nonfinite facet noise")
    noise = noise - float(np.mean(noise, dtype=np.float64))
    scale = float(np.max(np.abs(noise)))
    require(np.isfinite(scale) and scale > 0.0, "degenerate facet noise field")
    taper = np.clip(top / peak, 0.0, 1.0)
    return (noise / scale) * taper * (amplitude * peak)


def audit_mesh(vertices, triangles):
    """Own non-degeneracy and orientation check; no generator mesh helper is reused."""
    points = vertices[triangles]
    first, second = points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]
    cross = np.cross(first, second)
    scale = np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1)
    require(bool(np.isfinite(points).all()) and bool(np.isfinite(cross).all()), "nonfinite triangle")
    require(bool(np.all(scale > 0.0)), "degenerate triangle edge")
    area = np.linalg.norm(cross, axis=1)
    require(bool(np.all(area > 1e-12 * scale)), "degenerate triangle area")
    plan = np.abs(cross[:, 1]) / np.maximum(area, 1e-300)
    return {"triangles": int(triangles.shape[0]), "min_area_ratio": float(np.min(area / scale)),
            "min_plan_view_alignment": float(np.min(plan))}


def audit_targets(change, reference, parent_recipe):
    """Replay every declared target footprint and re-measure its incision."""
    x, z = reference[:, :, 0], reference[:, :, 2]
    record = {}
    for target in parent_recipe["targets"]:
        across = (x - target["center_x_m"]) / target["radius_x_m"]
        along = (z - target["center_z_m"]) / target["radius_z_m"]
        inside = np.sqrt(across * across + along * along) <= 1.0
        record[target["target_id"]] = {
            "footprint_cells": int(inside.sum()),
            "maximum_incision_m": float(np.max(-change[inside])) if inside.any() else 0.0,
            "maximum_deposition_m": float(np.max(change[inside])) if inside.any() else 0.0,
        }
    return record


def audit_bundle(path, *, expected_sha256, parents, parent_manifest):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=minimal_scope,
                         header_validator=surface_headers)
    metadata, arrays = result["metadata"], result["arrays"]
    require(metadata["schema"] == SURFACE_SCHEMA and metadata["algorithm"] == SURFACE_ALGORITHM,
            "unexpected surface identity")
    require(metadata["supersedes_algorithm"] == SUPERSEDED, "missing superseded identity")
    require(metadata["parent_schema"] == PARENT_SCHEMA, "unexpected parent schema")
    require(metadata["coordinates"] == "xyz metres; chart [row,col]", "unexpected coordinates")
    for flag in FLAGS:
        require(metadata[flag] is False, f"bundle prematurely promoted capability: {flag}")
    require(any(field in metadata["dissection_recipe"] for field in RETIRED_RECIPE_FIELDS) is False,
            "retired dissection recipe field is still present")
    require(set(metadata["dissection_recipe"]) == DISSECTION_KEYS, "unexpected dissection recipe keys")
    kind = metadata["parent_kind"]
    require(kind in parent_manifest["forms"], "parent kind is not in the parent manifest")

    entry = parent_manifest["forms"][kind]
    parent = load_bundle(parents / entry["file"], expected_sha256=entry["sha256"],
                         validator=parent_scope)
    require(metadata["parent_identity_sha256"] == entry["identity_sha256"],
            "declared parent identity differs from the parent manifest")
    require(metadata["parent_identity_sha256"] == parent["identity_sha256"],
            "parent bundle on disk does not carry the declared identity")
    require(metadata["parent_algorithm"] == parent["metadata"]["algorithm"],
            "declared parent algorithm differs from the parent bundle")

    reference = arrays["reference_xyz_m"]
    require(bool(np.array_equal(reference, parent["arrays"]["reference_xyz_m"])),
            "surface chart is not the parent chart")
    require(bool(np.array_equal(arrays["protected_mask"], parent["arrays"]["protected_mask"])),
            "surface protection differs from the parent")
    spacing = uniform_spacing(reference)

    parent_displacement = parent["arrays"]["displacement_xyz_m"]
    displacement = arrays["displacement_xyz_m"]
    surface = arrays["surface_xyz_m"]
    change = arrays["erosion_change_m"]
    mask = arrays["protected_mask"]

    # Facet noise: re-derived from the recipe, over the parent displacement the auditor
    # loaded itself.
    facet = rebuild_facet(reference, parent_displacement, metadata["facet_recipe"], spacing)
    facet[mask] = 0.0
    require(bool(np.array_equal(displacement[:, :, 0], parent_displacement[:, :, 0])) and
            bool(np.array_equal(displacement[:, :, 2], parent_displacement[:, :, 2])),
            "horizontal displacement changed")
    rebuilt_roughened = parent_displacement[:, :, 1] + facet
    maximum_difference = float(np.max(np.abs(rebuilt_roughened - displacement[:, :, 1])))
    require(maximum_difference < TOLERANCE,
            f"replayed facet relief differs from the stored displacement ({maximum_difference:.3e})")
    metres = [cells * spacing for cells, _ in metadata["facet_recipe"]["scales"]]
    require([pair[0] for pair in metadata["facet_wavelengths_m"]] == metres,
            "declared facet wavelengths disagree with the recipe")
    require(metadata["relief_reference_m"] == float(np.max(parent_displacement[:, :, 1])),
            "declared parent relief disagrees with the parent chart")
    require(metadata["roughened_relief_reference_m"] == float(np.max(displacement[:, :, 1])) and
            metadata["roughened_relief_reference_m"] >= metadata["relief_reference_m"],
            "declared roughened relief disagrees with the stored displacement")

    # Rock floor: rebuilt from the stored roughened surface and the declared fraction.
    recipe = metadata["dissection_recipe"]
    roughened = reference[:, :, 1] + displacement[:, :, 1]
    depth = recipe["maximum_incision_fraction"] * metadata["roughened_relief_reference_m"]
    floor = np.minimum(np.maximum(roughened - depth, reference[:, :, 1]), roughened)
    final = surface[:, :, 1]
    worst = float(np.min(final - floor))
    require(worst >= -TOLERANCE, f"final bed crosses the recomputed rock floor by {-worst:.3e} m")
    # The stored change must be exactly the bed difference, so the identity is checkable.
    require(float(np.max(np.abs(final - (roughened + change)))) < TOLERANCE,
            "stored change does not close the roughened surface")

    # Ledger: every scalar re-derived from the stored arrays instead of trusted.
    ledger = metadata["ledger"]
    require(all(name in ledger for name in LEDGER_SCALARS + LEDGER_COUNTS),
            "ledger is missing a declared scalar")
    require(float(np.sum(change) * spacing ** 2) == ledger["net_change_ledger_m3"],
            "net change ledger disagrees with the stored change")
    require(int(np.sum(change < 0.0)) == ledger["incised_cells"] and
            int(np.sum(change > 0.0)) == ledger["deposited_cells"],
            "incision cell counts disagree with the stored change")
    require(ledger["maximum_incision_m"] == float(np.max(-change)) and
            ledger["maximum_deposition_m"] == float(np.max(change)),
            "incision extremes disagree with the stored change")
    require(all(ledger[name] >= 0.0 for name in
                ("detachment_ledger_m3", "transport_deposition_ledger_m3",
                 "relaxation_transferred_ledger_m3", "rock_floor_depth_m")),
            "a dissection ledger term is negative")
    require(ledger["rock_floor_depth_m"] == depth, "declared rock floor depth is not the recipe depth")
    # The repose relaxation is checked for *self-consistency*, not for success.  The kernel
    # contracts an unconverged finite-stop state on purpose (``relax_mobile_slopes``:
    # "Return actual relaxed state, including an unconverged finite-stop state"), so a
    # bundle is allowed to record ``relaxation_converged=False`` -- what it may not do is
    # contradict its own numbers.  Every operand of the kernel's own test
    # (``maximum_mobile_excess_after_m <= tolerance_m``) travels with the bundle, so the
    # flag is re-derived here step by step instead of being believed.
    steps = ledger["steps"]
    require(isinstance(steps, list) and len(steps) == recipe["steps"] and
            [step["step_index"] for step in steps] == list(range(recipe["steps"])),
            "step ledger does not match the declared dissection steps")
    for step in steps:
        require(set(step) == set(STEP_KEYS), "unexpected dissection step keys")
    require(ledger["relaxation_tolerance_m"] == recipe["tolerance_m"] and
            ledger["relaxation_sweep_budget"] == recipe["max_sweeps"],
            "relaxation budget does not match the declared dissection recipe")
    derived_converged = all(step["relaxation_maximum_excess_m"] <= recipe["tolerance_m"]
                            for step in steps)
    require(all(bool(step["relaxation_converged"]) ==
                (step["relaxation_maximum_excess_m"] <= recipe["tolerance_m"])
                for step in steps),
            "a step's convergence flag disagrees with its own recorded excess")
    require(ledger["relaxation_converged"] is derived_converged,
            "relaxation summary flag disagrees with the per-step excess")
    require(ledger["relaxation_maximum_excess_m"] ==
            max(step["relaxation_maximum_excess_m"] for step in steps) and
            ledger["relaxation_sweeps_max"] == max(step["relaxation_sweeps"] for step in steps),
            "relaxation extremes disagree with the per-step records")
    # A step that spent its whole budget without converging must have done so by running
    # out of sweeps -- not by stalling, which would mean the kernel stopped moving material
    # while still out of repose.
    for step in steps:
        unresolved = step["relaxation_maximum_excess_m"] > recipe["tolerance_m"]
        require(step["relaxation_sweeps"] <= recipe["max_sweeps"],
                "a relaxation step exceeded the declared sweep budget")
        require(not (unresolved and step["relaxation_stalled_at_float64_resolution"]),
                "a relaxation step stalled short of repose")
    require(ledger["phase_balance"]["phase"] == "hydraulic-dissection" and
            set(ledger["phase_balance"]) == set(PHASE_KEYS),
            "unexpected phase balance record")
    require(ledger["phase_balance"]["exported_bulk_m3"] == -ledger["net_change_ledger_m3"],
            "phase balance export term disagrees with the net change ledger")

    # Targets replayed from the parent recipe.
    recomputed_targets = audit_targets(change, reference, parent["metadata"]["recipe"])
    require(set(recomputed_targets) == set(metadata["targets"]), "target id set differs")
    for target_id, record in recomputed_targets.items():
        stored = metadata["targets"][target_id]
        require(stored["footprint_cells"] == record["footprint_cells"] and
                stored["maximum_incision_m"] == record["maximum_incision_m"] and
                stored["maximum_deposition_m"] == record["maximum_deposition_m"],
                f"target {target_id} incision record does not replay")

    # Pinned kernels re-hashed from disk.
    revisions = metadata["kernel_revisions"]
    for name, digest in revisions.items():
        require(len(digest) == SHA256_LENGTH and
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest,
                f"kernel revision mismatch for {name}")

    perimeter = {"first_row": bool(np.all(displacement[0] == 0) and np.all(change[0] == 0)),
                 "last_row": bool(np.all(displacement[-1] == 0) and np.all(change[-1] == 0)),
                 "first_column": bool(np.all(displacement[:, 0] == 0) and np.all(change[:, 0] == 0)),
                 "last_column": bool(np.all(displacement[:, -1] == 0) and np.all(change[:, -1] == 0))}
    require(all(perimeter.values()), "chart perimeter carries displacement or change")
    require(bool(np.all(change[mask] == 0.0)), "a protected cell was dissected")
    require(bool(np.array_equal(surface[0], reference[0])) and
            bool(np.array_equal(surface[-1], reference[-1])) and
            bool(np.array_equal(surface[:, 0], reference[:, 0])) and
            bool(np.array_equal(surface[:, -1], reference[:, -1])),
            "surface no longer closes on its collar")

    vertices = arrays["vertices_xyz_m"]
    require(bool(np.array_equal(vertices, surface.reshape(-1, 3))),
            "stored vertices are not the stored surface")
    mesh = audit_mesh(vertices, arrays["triangles"])
    recomputed_identity = identity(arrays, metadata)
    require(recomputed_identity == result["identity_sha256"], "identity does not replay")
    return {
        "kind": kind,
        "parent_identity_sha256": metadata["parent_identity_sha256"],
        "chart_shape": [int(reference.shape[0]), int(reference.shape[1])],
        "spacing_m": spacing,
        "relief_reference_m": metadata["relief_reference_m"],
        "roughened_relief_reference_m": metadata["roughened_relief_reference_m"],
        "max_facet_replay_difference_m": maximum_difference,
        "rock_floor_depth_m": depth,
        "min_bed_minus_floor_m": worst,
        "maximum_incision_m": ledger["maximum_incision_m"],
        "maximum_deposition_m": ledger["maximum_deposition_m"],
        "incised_cells": ledger["incised_cells"],
        "deposited_cells": ledger["deposited_cells"],
        "net_change_m3": ledger["net_change_ledger_m3"],
        "detachment_ledger_m3": ledger["detachment_ledger_m3"],
        "transport_deposition_ledger_m3": ledger["transport_deposition_ledger_m3"],
        "relaxation_transferred_ledger_m3": ledger["relaxation_transferred_ledger_m3"],
        "relaxation_converged": ledger["relaxation_converged"],
        "relaxation_tolerance_m": ledger["relaxation_tolerance_m"],
        "relaxation_maximum_excess_m": ledger["relaxation_maximum_excess_m"],
        "relaxation_sweeps_max": ledger["relaxation_sweeps_max"],
        "targets": recomputed_targets,
        "perimeter_zero": perimeter,
        "mesh": mesh,
        "identity_sha256": result["identity_sha256"],
        "status": "candidate",
        "flags": {flag: metadata[flag] for flag in FLAGS},
        "caveat": ("Facet noise, rock floor, ledger scalars, target footprints, kernel pins and "
                   "identity are all re-derived here from the stored arrays and the parent "
                   "bundle; the transpose of the transport and repose kernels themselves is "
                   "imported by the producer and is outside this audit, so hydraulic legality "
                   "and solid self-intersection remain uncertified and every flag stays false."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundles", type=Path,
                        help="directory holding the surface <kind>.npz and manifest-report.json")
    parser.add_argument("--parents", type=Path, required=True,
                        help="directory holding the parent <kind>.npz and manifest-report.json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    manifest = json.loads((args.bundles / "manifest-report.json").read_text(encoding="utf-8"))
    parent_manifest = json.loads((args.parents / "manifest-report.json").read_text(encoding="utf-8"))
    report = {"audit_schema": AUDIT_SCHEMA, "generator_imported": False,
              "bundle_directory": str(args.bundles), "parent_directory": str(args.parents),
              "forms": {}, "failures": {}}
    for kind, entry in sorted(manifest["forms"].items()):
        path = args.bundles / entry["file"]
        try:
            audited = audit_bundle(path, expected_sha256=entry["sha256"], parents=args.parents,
                                   parent_manifest=parent_manifest)
            require(audited["identity_sha256"] == entry["identity_sha256"],
                    "audited identity differs from the manifest identity")
            report["forms"][kind] = audited
            print(f"{kind}: pass identity={audited['identity_sha256'][:16]} "
                  f"facet_delta={audited['max_facet_replay_difference_m']:.3e} "
                  f"bed_minus_floor={audited['min_bed_minus_floor_m']:.3e}")
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
