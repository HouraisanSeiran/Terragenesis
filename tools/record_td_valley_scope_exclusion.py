"""Record an auditable scope exclusion for unresolved TD valley edges."""

import argparse
import json
from pathlib import Path

from terrain_pipeline.common_infra import file_sha256, publish_bytes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIAGNOSTIC = (
    ROOT / "verification/td-valley-global-tiled/td1024-20261008-01/refusal-diagnostic.json"
)


def record_scope_exclusion(diagnostic_path, output_path, failure_path=None):
    diagnostic_path = Path(diagnostic_path)
    output_path = Path(output_path)
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    failure_path = Path(failure_path or diagnostic_path.with_name("failure-prefix.json"))
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    if (diagnostic["source_sha256"] != failure["source"]["sha256"]
            or diagnostic["plan_identity_sha256"] != failure["parent_network_plan"]["identity_sha256"]):
        raise ValueError("diagnostic source or plan does not match failure report")
    rows = diagnostic["rows"]
    refused_ids = {row["source_cell_id"] for row in failure["preflight"]
                   if row["status"] == "refused_edge_preflight"}
    row_ids = [row["source_cell_id"] for row in rows]
    if len(set(row_ids)) != len(row_ids) or set(row_ids) != refused_ids:
        raise ValueError("diagnostic edges do not match refused edge set")
    unresolved = [row for row in rows if row["recommendation"] == "must_remain_unresolved"]
    width_candidates = [
        row for row in rows if row["recommendation"] == "bounded_width_reduction_candidate"
    ]
    centerline_crossing = sum(bool(row["centerline_owner_crossing"]) for row in rows)
    min_radius_crossing = sum(
        row["factors"]["0.1"]["divide"] > 0 for row in rows
    )
    try:
        diagnostic_label = str(diagnostic_path.relative_to(ROOT))
    except ValueError:
        diagnostic_label = str(diagnostic_path)
    result = {
        "status": "scope_exclusion_owner_divide",
        "basis": "td_valley_global_tiled_refusal_diagnostic",
        "diagnostic_path": diagnostic_label,
        "diagnostic_sha256": file_sha256(diagnostic_path),
        "failure_report_sha256": file_sha256(failure_path),
        "source_sha256": diagnostic["source_sha256"],
        "plan_identity_sha256": diagnostic["plan_identity_sha256"],
        "refused_count": len(rows),
        "unresolved_count": len(unresolved),
        "width_reduction_candidate_count": len(width_candidates),
        "centerline_owner_crossing_count": centerline_crossing,
        "factor_0_1_owner_crossing_count": min_radius_crossing,
        "factor_definition": "radius = factor * (width_m / 2 + 1.5 * depth_m); factor 0.1 is dimensionless",
        "declared_selected_edges": failure["declared_selected_edges"],
        "accepted_global_edges": failure["accepted_global_edges"],
        "global_geometry_complete": False,
        "decision": (
            "exclude_existing_refused_edges_from_this_delivery; retain_original_declared_set_as_incomplete"
        ),
        "rerouting_status": "not_evaluated; existing_path_and_width_factor_evidence_only",
        "edge_ids": [
            {"source_cell_id": row["source_cell_id"], "target_cell_id": row["target_cell_id"]}
            for row in unresolved
        ],
        "publishable": False,
    }
    if len(unresolved) != len(rows) or width_candidates:
        raise ValueError("scope exclusion requires every refused edge to remain unresolved")
    publish_bytes(output_path, json.dumps(result, indent=2, allow_nan=False).encode("utf-8"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", type=Path, default=DEFAULT_DIAGNOSTIC)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = record_scope_exclusion(args.diagnostic, args.output)
    print(json.dumps({key: result[key] for key in (
        "status", "refused_count", "unresolved_count", "publishable"
    )}))
