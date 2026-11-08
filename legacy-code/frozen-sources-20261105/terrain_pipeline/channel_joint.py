"""Joint static stage, local geometry and inundation acceptance diagnostics."""

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest


VERSION = "channel-joint-v1"


def assess_joint(plan, sections, stage, inundation):
    """A pass requires the full shared domain and every diagnosed constraint."""
    params = inundation["identity"]["parameters"]
    if (sections["identity"]["parameters"]["plan_identity_sha256"] != plan["identity_sha256"] or
            stage["identity"]["parameters"]["plan_identity_sha256"] != plan["identity_sha256"] or
            params["section_identity_sha256"] != sections["identity_sha256"] or
            params["stage_identity_sha256"] != stage["identity_sha256"]):
        raise ValueError("joint inputs do not share their saved plan and stages")
    if digest({name: array_hash(value) for name, value in sections["arrays"].items()}) != params["section_arrays_sha256"]:
        raise ValueError("joint section arrays differ from inundation source")
    if (ArtifactIdentity(**stage["identity"]).sha256 != stage["identity_sha256"] or
            ArtifactIdentity(**inundation["identity"]).sha256 != inundation["identity_sha256"] or
            digest({name: array_hash(value) for name, value in stage["arrays"].items()}) !=
            stage["identity"]["parameters"]["stage_output_sha256"] or
            array_hash(inundation["arrays"]["water_surface_m"]) != params["water_sha256"] or
            digest({name: array_hash(value) for name, value in inundation["arrays"].items()}) !=
            params["all_arrays_sha256"]):
        raise ValueError("joint stage or water arrays differ from identity")
    if stage["summary"]["stage_feasible"] != (not bool(
            (stage["arrays"]["invalid_depth_mask"] |
             stage["arrays"]["excessive_lift_mask"] |
             stage["arrays"]["inherited_failure_mask"]).any())):
        raise ValueError("stage feasibility summary disagrees with masks")
    flood_arrays = inundation["arrays"]
    flood_summary = inundation["summary"]
    checks = {"wet_nodes": "wet_mask", "overbank_nodes": "overbank_mask",
              "protected_conflict_nodes": "protected_conflict_mask",
              "boundary_contact_nodes": "boundary_contact_mask",
              "reach_limited_nodes": "reach_limited_mask",
              "stage_mismatch_nodes": "stage_mismatch_mask",
              "channel_seed_nodes": "channel_seed_mask",
              "disconnected_seed_nodes": "disconnected_seed_mask"}
    for count_name, mask_name in checks.items():
        if flood_summary[count_name] != int(flood_arrays[mask_name].sum()):
            raise ValueError("inundation summary disagrees with masks")
    complete = (params["whole_graph_covered"] and bool(
        (flood_arrays["wet_mask"] & flood_arrays["legal_outlet_mask"]).any()) and
        not bool((flood_arrays["disconnected_seed_mask"] |
                  flood_arrays["boundary_contact_mask"] |
                  flood_arrays["reach_limited_mask"]).any()))
    if (flood_summary["whole_graph_covered"] != params["whole_graph_covered"] or
            flood_summary["coverage_complete"] != complete or
            flood_summary["legal_outlet_wet"] != bool(
                (flood_arrays["wet_mask"] & flood_arrays["legal_outlet_mask"]).any())):
        raise ValueError("inundation coverage summary mismatch")
    section_summary = sections["summary"]
    stage_summary = stage["summary"]
    flood_summary = inundation["summary"]
    blockers = {
        "plan": section_summary["blocked_by_plan"],
        "centerline": section_summary.get("blocked_by_centerline", False),
        "stage": not stage_summary["stage_feasible"],
        "local_budget": section_summary["local_budget_conflict_nodes"] > 0,
        "protection": section_summary["protected_conflict_nodes"] > 0 or flood_summary["protected_conflict_nodes"] > 0,
        "resolution": section_summary["needs_refinement_nodes"] > 0 or section_summary["potentially_unsampled_segments"] > 0,
        "terrain_coverage": not flood_summary["coverage_complete"] or bool(
            (sections["arrays"]["clipped_boundary_mask"] &
             ~inundation["arrays"]["legal_outlet_mask"]).any()),
        "stage_transition": flood_summary["stage_mismatch_nodes"] > 0,
        "legal_outlet": not flood_summary["legal_outlet_wet"],
        "wet_connectivity": flood_summary["disconnected_seed_nodes"] > 0,
    }
    identity = ArtifactIdentity("Terragenesis", "channel-joint", VERSION, 0,
                                {"plan_identity_sha256": plan["identity_sha256"],
                                 "section_identity_sha256": sections["identity_sha256"],
                                 "stage_identity_sha256": stage["identity_sha256"],
                                 "inundation_identity_sha256": inundation["identity_sha256"]})
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "pass": not any(blockers.values()),
            "blockers": blockers}
