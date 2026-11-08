"""Read-only structural, identity, and semantic audit for a metric VDM fault.

The command never rebuilds the source VDM or fault geometry. It validates the
current v2 bundle by default. Archived v1 bundles require --legacy-v1-replay.
A report is printed to stdout and can optionally be written to a new JSON path.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.vdm_cuts import load_fault
from terrain_pipeline.common_infra import file_sha256


def _json_value(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return {"shape": list(value.shape), "dtype": str(value.dtype)}
    return value


def audit_fault(path, *, expected_sha256=None, expected_identity=None):
    path = Path(path)
    report = {
        "schema": "metric-vdm-fault-audit-v2",
        "path": str(path.resolve()),
        "file_sha256": file_sha256(path),
        "load": {"passed": False, "error": None},
        "structure": {"passed": False, "checks": {}},
        "identity": {"passed": False, "stored": None, "expected": expected_identity},
        "semantics": {"passed": False, "checks": {}},
    }
    try:
        result = load_fault(path, expected_sha256=expected_sha256 or report["file_sha256"],
                            expected_identity=expected_identity or "0" * 64)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["load"]["error"] = str(error)
        return report

    arrays = result["arrays"]
    metadata = result["metadata"]
    report["load"]["passed"] = True
    report["identity"]["stored"] = result["identity_sha256"]
    report["identity"]["passed"] = expected_identity in (None, result["identity_sha256"])
    required = {
        "vertices_xyz_m", "triangles", "vertex_side", "transition_weight",
        "applied_displacement_xyz_m", "vertex_source_index", "triangle_source_index",
        "seam_edges",
    }
    report["structure"]["checks"]["required_arrays"] = sorted(required - set(arrays)) == []
    if report["structure"]["checks"]["required_arrays"]:
        vertices = arrays["vertices_xyz_m"]
        triangles = arrays["triangles"]
        sides = arrays["vertex_side"]
        report["structure"]["checks"].update({
            "vertices_3d": vertices.ndim == 2 and vertices.shape[1] == 3,
            "triangles_3_indices": triangles.ndim == 2 and triangles.shape[1] == 3,
            "triangle_indices_in_range": bool(np.all((triangles >= 0) &
                                                       (triangles < len(vertices)))),
            "side_length_matches_vertices": len(sides) == len(vertices),
            "finite_geometry": bool(np.isfinite(vertices).all()),
            "readonly_arrays": all(not value.flags.writeable for value in arrays.values()
                                    if isinstance(value, np.ndarray)),
        })
    report["structure"]["passed"] = all(report["structure"]["checks"].values())
    report["semantics"]["checks"]["open_surface"] = metadata.get("closed_surface") is False
    report["semantics"]["checks"]["horizontal_strike"] = metadata.get("slip_axis") == "horizontal_strike"
    report["semantics"]["checks"]["source_identity_present"] = bool(metadata.get("source_identity"))
    report["semantics"]["checks"]["transition_width_positive"] = metadata.get("transition_width_m", 0) > 0
    if report["structure"]["checks"].get("required_arrays"):
        triangle_sides = arrays["vertex_side"][arrays["triangles"]]
        influenced = np.any(arrays["transition_weight"][arrays["triangles"]] > 0., axis=1)
        report["semantics"]["checks"]["no_cross_seam_triangle"] = not bool(
            np.any(np.ptp(triangle_sides[influenced], axis=1) != 0))
        weights = arrays["transition_weight"]
        report["semantics"]["checks"]["bounded_transition"] = bool(
            np.isfinite(weights).all() and np.all((weights >= 0) & (weights <= 1)))
        report["semantics"]["checks"]["seam_edges_present"] = arrays["seam_edges"].ndim == 2
    report["semantics"]["passed"] = all(report["semantics"]["checks"].values())
    report["passed"] = bool(report["load"]["passed"] and report["identity"]["passed"] and
                             report["structure"]["passed"] and report["semantics"]["passed"])
    report["metadata"] = {key: _json_value(value) for key, value in metadata.items()}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="saved fault NPZ")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--expected-identity")
    parser.add_argument("--output", type=Path, help="write a new JSON report")
    parser.add_argument("--legacy-v1-replay", action="store_true",
                        help="explicitly use the pinned historical v1 validator")
    args = parser.parse_args()
    if args.legacy_v1_replay:
        from tools.metric_vdm_fault_legacy_v1 import audit_legacy_fault
        auditor = audit_legacy_fault
    else:
        auditor = audit_fault
    report = auditor(args.path, expected_sha256=args.expected_sha256,
                     expected_identity=args.expected_identity)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    raise SystemExit(0 if report.get("passed") else 1)


if __name__ == "__main__":
    main()
