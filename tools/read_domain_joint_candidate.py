"""Read saved bundle and R7 as a sidecar candidate; never generate or solve."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_domain_candidate_bundle import Audit, DEFAULT, read_json
from terrain_pipeline.common_infra import checked_archive, file_sha256, identity
from terrain_pipeline.surface_hydraulics import load_domain_channel_hydraulics

RUNOFF_FIELDS = {
    "infiltration_capacity_mm_h", "soil_capacity_mm", "potential_et_mm_h",
    "percolation_mm_h", "fast_tau_s", "slow_tau_s", "initial_soil_mm",
    "initial_fast_mm", "initial_slow_mm",
}
INCOMPLETE_GATES = [
    "R6 carved geometry is not consumed by R7 (r6_carving_consumed=false).",
    "R7 covers one terminal's current-core production only; other independent domains remain omitted.",
    "Outside-core and cross-tile upstream contributions are not certified.",
    "Dynamic backwater, conservative floodplain inundation and lake evolution are not certified.",
    "Engineering hydraulic and sediment parameters remain uncalibrated.",
    "R8 changed geometry needs geometry/hydraulic revalidation and bed rejection.",
    "Naturalness, Minecraft connectivity, R7 completion and stage completion are not certified.",
    "This unregistered sidecar does not insert R7 into the source bundle or choose a production default.",
]


def world_points(ids, frame):
    ids = np.asarray(ids)
    columns = frame["shape"][1]
    return np.column_stack((frame["origin_x_m"] + ids % columns * frame["spacing_m"],
                            frame["origin_z_m"] + ids // columns * frame["spacing_m"]))


def same_points(actual, expected):
    actual, expected = np.asarray(actual), np.asarray(expected)
    return (actual.shape == expected.shape and
            set(map(tuple, actual.tolist())) == set(map(tuple, expected.tolist())) and
            len(np.unique(actual, axis=0)) == len(actual))


def check_trace(audit, arrays, budget):
    """Recompute cell/step and global budgets from the saved committed trace."""
    a = arrays
    dt = np.diff(a["channel_trace_time_seconds"])
    volumes = a["channel_trace_volume_m3"]
    local = a["channel_trace_local_q_m3_s"]
    incoming = a["channel_trace_inflow_q_m3_s"]
    outgoing = a["channel_trace_outflow_q_m3_s"]
    boundary = a["channel_trace_boundary_outflow_volume_m3"]
    audit.check("r7/trace_positive_dt", np.all(dt > 0))
    audit.close("r7/trace_cell_step_conservation", np.diff(volumes, axis=0),
                dt[:, None] * (local + incoming - outgoing))
    receiver = a["channel_network_receiver"]
    donor = np.zeros_like(incoming)
    for node, target in enumerate(receiver):
        if target >= 0:
            donor[:, target] += outgoing[:, node]
    audit.close("r7/trace_receiver_transfers", incoming, donor)
    audit.close("r7/trace_boundary_outflow", boundary,
                dt[:, None] * np.where(a["channel_network_terminal_kind"] == "open_outflow", outgoing, 0.))
    audit.close("r7/trace_global_step_conservation", np.diff(volumes.sum(axis=1)),
                np.sum(local * dt[:, None] - boundary, axis=1))
    residual = np.diff(volumes, axis=0) - dt[:, None] * (local + incoming - outgoing)
    audit.close("r7/trace_stored_residual", a["channel_trace_balance_residual_m3"], residual)
    computed = {"local_input": float(np.sum(local * dt[:, None])),
                "boundary_outflow": float(boundary.sum()),
                "initial_storage": float(volumes[0].sum()),
                "final_storage": float(volumes[-1].sum())}
    for key, value in computed.items():
        audit.close("r7/budget/" + key, value, budget[key])
    audit.close("r7/budget/conservation", computed["local_input"],
                computed["final_storage"] + computed["boundary_outflow"] - computed["initial_storage"])
    audit.close("r7/budget/stored_residual", budget["residual"],
                computed["local_input"] - computed["final_storage"] - computed["boundary_outflow"] + computed["initial_storage"])
    return computed


def compare_joint(audit, bundle, summary, r7, flow, coupled, domain, entry):
    a, m = r7["arrays"], r7["metadata"]
    frame = m["topology_frame"]
    ids = a["node_cell_ids"]
    terminals = ids[a["selected_receiver"] < 0]
    audit.check("r7/single_original_terminal", len(terminals) == 1)
    if len(terminals) != 1:
        raise ValueError("joint candidate requires one original terminal")
    terminal = int(terminals[0])
    outlet = world_points([terminal], frame)[0]
    audit.check("r7/selection_report_binding", summary["selected_terminal_cell_id"] == terminal and
                summary["node_cell_ids"] == ids.tolist() and
                np.all(a["topology_terminal"].ravel()[ids] == terminal))
    audit.check("joint/domain_outlet", np.array_equal(domain["outlet_xz_m"], outlet) and
                [entry["outlet_x_m"], entry["outlet_z_m"]] == outlet.tolist())
    contributors = a["producing_cell_ids"][a["topology_terminal"].ravel()[a["producing_cell_ids"]] == terminal]
    points = world_points(contributors, frame)
    audit.check("r7/contributors_report_binding", summary["current_core_producing_contributors"] == contributors.tolist())
    audit.check("r7/no_missing_same_terminal_contributors", np.isin(contributors, ids).all() and
                m["coverage"]["missing_upstream_contributing_cell_count"] == 0 and
                m["coverage"]["missing_upstream_contributing_release_m3"] == 0.)
    missing = np.setdiff1d(a["producing_cell_ids"], ids)
    audit.check("r7/other_independent_domains_not_certified", len(missing) == m["coverage"]["missing_producing_cell_count"] and
                not np.any(a["topology_terminal"].ravel()[missing] == terminal) and
                m["coverage"]["cross_tile_inflow_status"] == "not_certified" and
                m["coverage"]["upstream_contributions_status"] == "not_certified")
    audit.check("r7/report_coverage_binding", summary["coverage"] == m["coverage"])
    audit.check("r7/not_carved_or_certified", m["r6_carving_consumed"] is False and
                summary["r6_carving_consumed"] is False and m["source_face"] == summary["source_face"] == "raw_conditioning" and
                all(m[k] is False and summary[k] is False for k in ("hydraulic_ready", "natural_outlet_verified", "publishable")))
    audit.check("joint/runoff_nine_fields", set(summary["runoff_parameters"]) == RUNOFF_FIELDS and
                summary["runoff_parameters"] == bundle["runoff_parameters"] == flow["metadata"]["parameters"] == coupled["metadata"]["parameters"]["runoff"])
    audit.check("joint/scenario", summary["rain_mm_h"] == bundle["rain_mm_h"] and
                all(summary[k] == bundle[k] == flow["metadata"][k] == coupled["metadata"][k]
                    for k in ("seed", "dt_s")) and
                m["dt_s"] == summary["dt_s"] and
                m["interval_count"] == summary["interval_count"] == bundle["intervals"] == flow["metadata"]["interval_count"] == coupled["metadata"]["interval_count"])
    audit.check("joint/source_tile_frame", all(record["metadata"]["tile_shape"] == frame["shape"] and
                record["metadata"]["tile_origin_m_xz"] == [frame["origin_x_m"], frame["origin_z_m"]] and
                record["metadata"]["spacing_m"] == frame["spacing_m"] for record in (flow, coupled)))
    domain_points = np.column_stack((domain["cells_x_m"], domain["cells_z_m"]))
    audit.check("joint/domain_all_contributor_coordinates_and_count", same_points(domain_points, points))
    lattice = np.rint((domain_points - domain["bbox_origin_xz_m"]) / domain["spacing_m"].item()).astype(int)
    height = domain["base_height_m"][lattice[:, 1], lattice[:, 0]]
    raw_lattice = (domain_points - [frame["origin_x_m"], frame["origin_z_m"]]) / frame["spacing_m"]
    audit.check("joint/domain_members_on_raw_lattice", np.array_equal(raw_lattice, np.rint(raw_lattice)))
    raw_lattice = np.rint(raw_lattice).astype(int)
    audit.close("joint/raw_source_member_heights", a["source_height_m"][raw_lattice[:, 1], raw_lattice[:, 0]], height)
    forcing_volume = float(np.sum(a["channel_forcing_local_q_m3_s"] * np.diff(a["channel_forcing_time_seconds"])[:, None]))
    matches = {}
    for role, record, release_key in (("flow", flow, "terminal_release_m3"), ("coupled", coupled, "water_release_m3")):
        arrays = record["arrays"]
        selected = np.flatnonzero((arrays["outlet_x_m"] == outlet[0]) & (arrays["outlet_z_m"] == outlet[1]))
        audit.check("joint/" + role + "/unique_same_outlet", len(selected) == 1)
        if len(selected) != 1:
            raise ValueError(role + " missing/ambiguous outlet")
        index = int(selected[0])
        lo, hi = arrays["cell_offsets"][index:index + 2]
        members = np.column_stack((arrays["cells_x_m"][lo:hi], arrays["cells_z_m"][lo:hi]))
        audit.check("joint/" + role + "/all_contributor_coordinates_and_count",
                    int(arrays["cell_count"][index]) == len(contributors) and same_points(members, points))
        release = float(arrays[release_key][index])
        audit.close("joint/forcing_integral_equals_" + role + "_domain_release", forcing_volume, release)
        matches[role] = {"domain_index": index, "release_m3": release, "contributor_count": len(members)}
    budget = check_trace(audit, a, m["channel_metadata"]["water_budget_m3"])
    for key, value in budget.items():
        audit.close("r7/report_budget/" + key, summary["water_budget_m3"][key], value)
    audit.close("r7/forcing_integral_equals_trace_input", forcing_volume, budget["local_input"])
    audit.check("r7/complete_saved_trace", m["channel_metadata"]["status"] == summary["status"] == "complete" and
                a["channel_trace_time_seconds"][-1] == a["channel_forcing_time_seconds"][-1])
    return {"terminal_cell_id": terminal, "outlet_xz_m": outlet.tolist(), "contributors": contributors.tolist(),
            "member_points_xz_m": points.tolist(), "matches": matches, "forcing_integral_m3": forcing_volume,
            "water_budget_m3": budget, "other_independent_domain_cells_omitted": len(missing),
            "release_semantics": "flow/coupled instantaneous domain release supplies R7 local forcing; R7 boundary outflow is not that release, since water remains in channel storage"}


def audit_joint(bundle_path, r7_report_path):
    bundle_path, r7_report_path = Path(bundle_path).resolve(), Path(r7_report_path).resolve()
    audit = Audit()
    paths = set(p for p in bundle_path.parent.rglob("*") if p.is_file()) | {r7_report_path}
    before = {str(p): file_sha256(p) for p in paths}
    sources, joint = [], {}
    try:
        bundle, summary = read_json(bundle_path), read_json(r7_report_path)
        r7_path = (r7_report_path.parent / summary["path"]).resolve()
        before[str(r7_path)] = file_sha256(r7_path)
        sources.extend([{"path": str(bundle_path), "sha256": before[str(bundle_path)], "content_identity_sha256": identity({}, bundle)},
                        {"path": str(r7_report_path), "sha256": before[str(r7_report_path)], "content_identity_sha256": identity({}, summary)},
                        {"path": str(r7_path), "sha256": before[str(r7_path)], "declared_identity_sha256": summary["identity_sha256"],
                         "expected_sha256": summary["sha256"]}])
        try:
            r7 = load_domain_channel_hydraulics(r7_path, expected_sha256=summary["sha256"], expected_identity=summary["identity_sha256"])
        except Exception as exc:
            audit.check("r7/pinned_cold_load", False, {"type": type(exc).__name__, "message": str(exc)})
            raise
        audit.check("r7/pinned_cold_load", True)
        sources[-1]["identity_sha256"] = r7["identity_sha256"]
        flows = [audit.ledger(bundle_path.parent, tile) for tile in bundle["tiles"]]
        index_path = ROOT / bundle["domain_products"]["index"].replace("\\", "/")
        index = read_json(index_path)
        audit.domains(index_path, index, flows)
        audit.check("bundle/domain_index_binding", bundle["domain_products"]["product_set_sha256"] == index["product_set_sha256"])
        frame = r7["metadata"]["topology_frame"]
        tiles = [i for i, tile in enumerate(bundle["tiles"]) if [tile["origin_x_m"], tile["origin_z_m"]] == [frame["origin_x_m"], frame["origin_z_m"]]]
        if len(tiles) != 1:
            raise ValueError("R7 source tile not unique in bundle")
        tile_index = tiles[0]
        tile = bundle["tiles"][tile_index]
        declaration = tile["ledgers"]["coupled"]
        from terrain_pipeline.common_infra import load_bundle
        coupled = load_bundle(bundle_path.parent / tile["directory"] / declaration["file"], expected_sha256=declaration["sha256"], validator=audit.validate_bundle)
        terminals = r7["arrays"]["node_cell_ids"][r7["arrays"]["selected_receiver"] < 0]
        if len(terminals) != 1:
            raise ValueError("R7 requires a single selected terminal")
        outlet = world_points(terminals, frame)[0]
        entries = [e for e in index["domains"] if [e["outlet_x_m"], e["outlet_z_m"]] == outlet.tolist()]
        if len(entries) != 1:
            raise ValueError("R7 outlet domain product not unique")
        entry = entries[0]
        domain_path = index_path.parent / entry["product"]
        domain = checked_archive(domain_path, expected_sha256=file_sha256(domain_path))
        joint = compare_joint(audit, bundle, summary, r7, flows[tile_index], coupled, domain, entry)
        sources.append({"path": str(index_path), "sha256": file_sha256(index_path), "content_identity_sha256": identity({}, index), "product_set_sha256": index["product_set_sha256"]})
    except Exception as exc:
        audit.check("joint/cold_read_exception", False, {"type": type(exc).__name__, "message": str(exc)})
    after = {path: file_sha256(Path(path)) if Path(path).is_file() else None for path in before}
    audit.check("source_files_unchanged", before == after)
    passed = bool(audit.checks) and all(check["passed"] for check in audit.checks)
    return {"schema": "river-domain-joint-candidate-sidecar-v1", "status": "PASS" if passed else "FAIL", "passed": passed,
            "role": "unregistered_read_only_joint_candidate_not_production_default", "source_bundle_includes_r7": False,
            "all_phases_complete": False, "r7_certified": False, "production_default_decided": False,
            "scope": "Saved artifacts only; parameter declarations bind the scenario, not independently measured provenance. No generation or solve is called.",
            "incomplete_stage_gates": INCOMPLETE_GATES, "sources": sources + audit.products,
            "check_count": len(audit.checks), "passed_count": sum(c["passed"] for c in audit.checks),
            "checks": audit.checks, "joint": joint,
            "joint_checks_status": "executed" if joint else "blocked_by_cold_read_failure",
            "blocked_joint_checks": [] if joint else ["scenario_nine_runoff_fields_dt_count", "same_tile_outlet", "raw_member_heights", "all_terminal_contributor_coordinates_and_counts", "forcing_integral_vs_flow_and_coupled", "r7_global_and_step_water_budget", "coverage_and_r6_scope"],
            "input_sha256_before": before, "input_sha256_after": after}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT / "bundle/bundle.json")
    parser.add_argument("--r7-report", type=Path, default=DEFAULT / "r7/complete-core-domain-report.json")
    parser.add_argument("--report", type=Path, default=DEFAULT / "joint-candidate-report.json")
    args = parser.parse_args(argv)
    destination = args.report.resolve()
    if destination.exists():
        raise FileExistsError("Refusing to overwrite an existing file: " + str(destination))
    if destination.is_relative_to(args.bundle.resolve().parent) or destination.is_relative_to(args.r7_report.resolve().parent):
        raise ValueError("Sidecar output must be outside both source artifact directories")
    report = audit_joint(args.bundle, args.r7_report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "checks": report["check_count"], "passed": report["passed_count"],
                      "failures": [c for c in report["checks"] if not c["passed"]], "report": str(destination)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
