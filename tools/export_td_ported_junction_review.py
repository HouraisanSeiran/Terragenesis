"""Pure IO review of td-ported-junction-v1; no generator/auditor/solver invocation.

API: load_review(junction_path, junction_sha256, audit_path=None,
audit_sha256=None, audit_schema=AUDIT_SCHEMA, preparation_index=None,
preparation_index_sha256=None), caseartifact(review), render_overview(review).
CLI requires --junction/--junction-sha256 and a NEW --output directory.
Optional audit needs --audit/--audit-sha256 plus --index/--index-sha256.
Actual audit schema is td-ported-junction-independent-audit-v1: index_sha256,
junction_sha256, junction_identity_sha256 and inputs bind the verified preparation
index, saved junction identity and all seven fixed sources. Missing/different bindings mean not_matched,
never inherited passed. No true package export is run as part of implementation.
Rendered triangles are saved display approximations, not exact native depth-fan
functions, fine DEM, full river or solved hydraulic surfaces. Old 07 is excluded.
"""

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_td_watershed_inspection import (
    DEFAULT_INDEX, DEFAULT_SHA256, ROOT, encoded, publish_directory, read_json_pin,
    read_pin, require, unique)
from audit_td_watershed_connectivity import check_memory


SCHEMA = "td-ported-junction-review-v1"
AUDIT_SCHEMA = "td-ported-junction-independent-audit-v1"
EXTRA_SOURCE_SHAS = {
    "source_bank_parent_audit": "c410f1871d8b17cee5b48cb2ba141f3cce41b447daa042ddb8637abdc42041d9",
    "source_bank_parent_index": "aac571e0a6f0b730e0ebd5c67db9ac9182f2f1398409754d33d9d66273fc277e",
    "wet_protection_manifest": "b1e901474ecefc3674ffcdc3fc949d03662910cb4bf7e3b4949c35ea341b3651",
}
FALSE_FLAGS = {"full_river_verified": False, "full_network_verified": False,
               "fine_generated": False, "material_budget_verified": False,
               "hydraulic_ready": False, "hydraulic_solved": False,
               "natural_outlet_certified": False, "bed_changed": False}


def signatures(pins):
    require(isinstance(pins, dict), "source pins must be an object")
    return {(str(Path(pin["path"]).resolve()), pin["sha256"].lower())
            for pin in pins.values() if isinstance(pin, dict) and "path" in pin and "sha256" in pin}


def validate_mesh(mesh):
    vertices = np.asarray(mesh["vertices_xyz_m"], dtype=float)
    triangles = np.asarray(mesh["triangles"])
    require(vertices.ndim == 2 and vertices.shape[1] == 3 and np.isfinite(vertices).all(), "invalid saved vertices")
    require(triangles.ndim == 2 and triangles.shape[1] == 3 and triangles.dtype.kind in "iu"
            and np.all((triangles >= 0) & (triangles < len(vertices)))
            and all(len(set(triangle)) == 3 for triangle in mesh["triangles"]), "invalid saved triangle reference")


def audit_binding(audit, audit_schema, junction, junction_pin, sources, preparation=None, preparation_pin=None):
    failures = []
    if audit.get("schema") != audit_schema:
        failures.append("audit_schema_mismatch")
    if audit.get("junction_sha256") != junction_pin["sha256"]:
        failures.append("audit_junction_file_sha_mismatch_or_missing")
    if audit.get("junction_identity_sha256") != junction["identity_sha256"]:
        failures.append("audit_junction_identity_mismatch_or_missing")
    if signatures(audit.get("inputs", {})) != signatures(junction["inputs"]) or not signatures(sources).issubset(signatures(audit.get("inputs", {}))):
        failures.append("audit_fixed_source_pins_mismatch_or_missing")
    if audit_schema == AUDIT_SCHEMA:
        if preparation is None or preparation_pin is None:
            failures.append("audit_preparation_index_binding_not_supplied")
        else:
            if audit.get("index_sha256") != preparation_pin["sha256"]:
                failures.append("audit_preparation_index_sha_mismatch_or_missing")
            if not signatures(sources).issubset(signatures(preparation.get("inputs", {}))):
                failures.append("audit_fixed_source_pins_mismatch_or_missing")
            if audit.get("policy_identity_sha256") != junction["policy_identity_sha256"]:
                failures.append("audit_policy_identity_mismatch_or_missing")
            for audit_key, junction_key in (("junction_status", "status"), ("hub_node_id", "hub_node_id"),
                                          ("actual_external_attachment_count", "actual_external_attachment_count"),
                                          ("external_closure_verified", "external_closure_verified")):
                if audit.get(audit_key) != junction[junction_key]:
                    failures.append("audit_junction_metadata_mismatch:" + audit_key)
    if audit.get("status") not in ("passed", "failed"):
        failures.append("audit_status_unknown_or_missing")
    if audit.get("status") == "passed" and audit.get("errors"):
        failures.append("audit_passed_with_errors")
    result = {"binding_status": "not_matched" if failures else "matched", "binding_failures": failures,
              "scope": "reference to saved independent audit only; exporter does not rerun it"}
    if not failures:
        result["referenced_status"] = audit["status"]
    return result


def load_review(junction_path, junction_sha256, audit_path=None, audit_sha256=None, audit_schema=AUDIT_SCHEMA,
                preparation_index=None, preparation_index_sha256=None):
    index, index_pin = read_json_pin({"path": str(DEFAULT_INDEX), "sha256": DEFAULT_SHA256}, ROOT)
    paths, paths_pin = read_json_pin(index["paths"], DEFAULT_INDEX.parent)
    sections, sections_pin = read_json_pin(index["sections"], DEFAULT_INDEX.parent)
    _, hierarchy_pin = read_pin(index["inputs"]["hierarchy"], DEFAULT_INDEX.parent)
    sources = {"06_index": index_pin, "06_paths": paths_pin, "06_sections": sections_pin, "hierarchy": hierarchy_pin}
    junction, junction_pin = read_json_pin({"path": str(Path(junction_path).resolve()), "sha256": junction_sha256}, ROOT)
    require(junction["schema"] == "td-ported-junction-v1", "unsupported junction schema")
    require(junction["parents"]["paths"] == paths["identity_sha256"]
            and junction["parents"]["sections"] == sections["identity_sha256"]
            and junction["parents"]["hierarchy"] == hierarchy_pin["identity_sha256"], "junction parent identity mismatch")
    require(signatures(sources).issubset(signatures(junction["inputs"])), "junction lacks all fixed source path/SHA pins")
    for name, expected in EXTRA_SOURCE_SHAS.items():
        require(junction["inputs"][name]["sha256"] == expected, "fixed source-bank/wet pin mismatch: " + name)
        _, sources[name] = read_pin(junction["inputs"][name], ROOT)
    require(junction["status"] in ("candidate", "refused"), "unknown junction status")
    for flag in FALSE_FLAGS:
        require(junction.get(flag) is False, "unsupported junction capability " + flag)
    nodes = unique(paths["nodes"], "node_id")
    arcs = unique(paths["arcs"], "arc_id")
    require(junction["hub_node_id"] in nodes, "missing hub source node")
    mesh = junction["geometry"]
    if mesh["triangles"]:
        validate_mesh(mesh)
    else:
        require(junction["status"] == "refused", "candidate without saved triangles")
    require(len(mesh["triangle_roles"]) == len(mesh["triangles"]), "triangle role census mismatch")
    if junction["status"] == "refused":
        require(junction["rejection_reasons"], "refused junction lacks reasons")
    else:
        require(not junction["rejection_reasons"], "candidate contains rejection reasons")
    kept = junction["old_kept_mesh_triangle_ids"]
    require(len(set(kept)) == len(kept) and all(type(index) is int and 0 <= index < len(sections["mesh"]["triangles"]) for index in kept), "invalid kept 06 face IDs")
    require(junction["transaction"]["old_kept_triangle_indices"] == kept, "retained mesh transaction mismatch")
    arm_ids = []
    for arm in junction["arms"]:
        arm_ids.append(arm["arc_id"])
        require(arm["arc_id"] in arcs and arm["node_ids"] == arcs[arm["arc_id"]]["node_ids"]
                and junction["hub_node_id"] in arm["node_ids"] and arm["outer_node_id"] in nodes, "arm is not actual saved incident arc")
        section = sections["node_sections"][arm["outer_section_index"]]
        require(section["node_id"] == arm["outer_node_id"] and section["cross_section_xyz_m"] == arm["outer_profile_xyz_m"], "arm outer profile differs from saved 06 section")
        require(arm["attachment_status"] in ("actual_old_mesh", "bound_original_section_no_accepted_external_strip"), "unknown attachment status")
        if junction["status"] == "candidate":
            for prefix in ("outer", "inner"):
                ids = arm[prefix+"_profile_vertex_ids"]
                require(len(ids) == 4 and len(set(ids)) == 4 and all(type(index) is int and 0 <= index < len(mesh["vertices_xyz_m"]) for index in ids), "invalid saved arm port IDs")
                require([mesh["vertices_xyz_m"][index] for index in ids] == arm[prefix+"_profile_xyz_m"], "saved arm profile vertex mismatch")
        if arm["attachment_status"] == "actual_old_mesh":
            witnesses = arm["outer_old_mesh_edge_witnesses"]
            require(sorted(w["profile_segment_index"] for w in witnesses) == [0, 1, 2], "missing actual old mesh segment witnesses")
            for witness in witnesses:
                triangle_id, edge_id = witness["triangle_index"], witness["edge_index"]
                require(triangle_id in kept and type(edge_id) is int and 0 <= edge_id < 3, "witness not on retained triangle")
                triangle = sections["mesh"]["triangles"][triangle_id]
                points = [sections["mesh"]["vertices_xyz_m"][triangle[edge_id]], sections["mesh"]["vertices_xyz_m"][triangle[(edge_id+1)%3]]]
                segment = arm["outer_profile_xyz_m"][witness["profile_segment_index"]:witness["profile_segment_index"]+2]
                require(points == witness["points_xyz_m"] and (points == segment or points == segment[::-1]), "actual old mesh witness mismatch")
    require(len(arm_ids) == len(set(arm_ids)) and sorted(arm_ids) == sorted(junction["requested_replacement_arc_ids"]), "arm replacement census mismatch")
    for role in mesh["triangle_roles"]:
        require(role["region"] in ("arm", "hub") and (role["region"] != "arm" or role["arc_id"] in arm_ids), "unknown saved geometry role")
    binding = {"binding_status": "not_supplied", "scope": "no independent audit state inherited"}
    pins = {**sources, "junction": junction_pin}
    require(bool(preparation_index) == bool(preparation_index_sha256), "preparation index path/SHA must be supplied together")
    preparation, preparation_pin = None, None
    if preparation_index:
        preparation, preparation_pin = read_json_pin({"path": str(Path(preparation_index).resolve()), "sha256": preparation_index_sha256}, ROOT)
        require(preparation["schema"] == "td-ported-junction-preparation-v1"
                and preparation["inputs"] == junction["inputs"]
                and preparation["junction"]["sha256"] == junction_pin["sha256"]
                and Path(preparation["junction"]["path"]).resolve() == Path(junction_pin["path"])
                and preparation["policy_identity_sha256"] == junction["policy_identity_sha256"], "preparation/junction pin binding mismatch")
        for key in ("hub_node_id", "status", "actual_external_attachment_count", "external_closure_verified", "rejection_reasons"):
            require(preparation[key] == junction[key], "preparation metadata mismatch: " + key)
        pins["preparation_index"] = preparation_pin
    require(bool(audit_path) == bool(audit_sha256), "audit path/SHA must be supplied together")
    if audit_path:
        audit, pins["independent_audit"] = read_json_pin({"path": str(Path(audit_path).resolve()), "sha256": audit_sha256}, ROOT)
        binding = audit_binding(audit, audit_schema, junction, junction_pin, sources, preparation, preparation_pin)
    with np.load(hierarchy_pin["path"], allow_pickle=False) as bundle:
        manifest = json.loads(bytes(bundle["manifest"]))
        height = bundle["height_m"].copy()
        valid = bundle["valid_mask"].copy()
    require(manifest["identity_sha256"] == hierarchy_pin["identity_sha256"] and np.isfinite(height[valid]).all(), "native terrain mismatch")
    rejected = [record for record in sections["reach_diagnostics"] if "cell:62896" in record["node_ids"] and record["status"] == "rejected"]
    original_rejection = {"hub_node_id": "cell:62896", "xyz_m": nodes["cell:62896"]["xyz_m"],
                          "refused_land_arcs": [{**record, "xyz_m": arcs[record["arc_id"]]["xyz_m"]} for record in rejected],
                          "semantics": "original 06 refusal evidence; NOT an invented new refused package or old 07 overlay"}
    report = {"schema": SCHEMA, "pins": pins, "coordinates": {"axes": "x east, y elevation, z south", "length_unit": "m",
              "array_order": "[z,x]", "origin_m_xz": manifest["metadata"]["origin_m_xz"], "spacing_m": manifest["metadata"]["spacing_m"]},
              "native_terrain": {"height_m": height.tolist(), "valid_mask": valid.tolist(), "sampling": "original native samples, no resampling"},
              "layers": {"retained_06_mesh": {"vertices_xyz_m": sections["mesh"]["vertices_xyz_m"],
                         "triangles": [sections["mesh"]["triangles"][index] for index in kept], "original_triangle_ids": kept},
                         "new_ported_geometry": mesh, "ports": junction["arms"], "original_refused_62896": original_rejection},
              "junction": {key: junction[key] for key in ("hub_node_id", "status", "rejection_reasons", "geometry_through_connection",
                           "internal_three_arm_geometry_candidate", "actual_external_attachment_count", "external_closure_verified",
                           "display_mesh_semantics", "transaction")}, "independent_audit_reference": binding,
              "limitations": ["Saved display mesh approximation only; exact bed is native source minus saved affine depth fans.",
                               "Open stubs are bound original sections, not external river closure.", "No old 07 geometry, full river, fine, material or hydraulic certification.",
                               "Matched audit is a saved single-junction reference; missing bindings never inherit passed."], **FALSE_FLAGS}
    report["junction_identity_sha256"] = junction["identity_sha256"]
    report["summary"] = {"actual_old_mesh_ports": sum(arm["attachment_status"] == "actual_old_mesh" for arm in junction["arms"])
                         if junction["status"] == "candidate" else 0,
                         "open_stubs": sum(arm["attachment_status"] != "actual_old_mesh" for arm in junction["arms"])
                         if junction["status"] == "candidate" else 0,
                         "saved_new_triangles": len(mesh["triangles"]), "displayable_new_triangles": len(mesh["triangles"])
                         if junction["status"] == "candidate" else 0}
    report["resource"] = {"peak_rss_bytes": check_memory(), "max_rss_bytes": 1024**3, "max_artifact_bytes": 64*1024**2}
    return report


def caseartifact(review):
    mesh = review["layers"]["new_ported_geometry"]
    drawable = review["junction"]["status"] == "candidate"
    vertices = mesh["vertices_xyz_m"] if drawable else []
    triangles = mesh["triangles"] if drawable else []
    heights = [point[1] for point in vertices]
    binding = review["independent_audit_reference"]
    return {"schema": "td-ported-junction-mesh-case-v1", "kind": "mesh", "caseId": "ported-"+review["junction"]["hub_node_id"],
            "label": "Local ported junction display geometry; open stubs are NOT river closure",
            "mesh": {"vertices": vertices, "triangles": triangles, "bed": heights, "h0": heights,
                     "water": None, "wet": [], "wetCells": [], "cells": [], "hydrologicOwner": []},
            "triangle_roles": mesh["triangle_roles"] if drawable else [], "ports": review["layers"]["ports"], "pins": review["pins"],
            "retained_mesh_layer": review["layers"]["retained_06_mesh"], "independent_audit_reference": binding,
            "evidence": {"status": "diagnostic_saved_geometry", "scope": "Local saved display mesh; H0 is bed alias, NOT native reference terrain",
                         "limitations": review["limitations"]}, **FALSE_FLAGS}


def render_overview(review):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection
    from matplotlib.colors import LightSource
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    layers = review["layers"]
    mesh = layers["new_ported_geometry"]
    coords = review["coordinates"]
    origin = np.asarray(coords["origin_m_xz"])
    spacing = coords["spacing_m"]
    height = np.asarray(review["native_terrain"]["height_m"])
    valid = np.asarray(review["native_terrain"]["valid_mask"])
    background = np.where(valid, height, np.nan)
    shade = LightSource(315, 45).hillshade(background, dx=spacing, dy=spacing)
    extent = [origin[0]-spacing/2, origin[0]+(height.shape[1]-.5)*spacing,
              origin[1]+(height.shape[0]-.5)*spacing, origin[1]-spacing/2]
    retained = layers["retained_06_mesh"]
    old_polygons = np.asarray(retained["vertices_xyz_m"])[:, [0, 2]][np.asarray(retained["triangles"], dtype=int).reshape(-1, 3)]
    points = np.asarray(mesh["vertices_xyz_m"], float).reshape(-1, 3)
    polygons = points[:, [0, 2]][np.asarray(mesh["triangles"], dtype=int).reshape(-1, 3)]
    focus = [np.asarray(arm["outer_profile_xyz_m"])[:, [0, 2]] for arm in layers["ports"]]
    focal_points = np.vstack(focus) if focus else origin.reshape(1, 2)
    refused = layers["original_refused_62896"]
    all_points = np.vstack((focal_points, np.asarray(refused["xyz_m"])[[0, 2]]))
    figure, axes = plt.subplots(1, 3, figsize=(19, 7))
    figure.subplots_adjust(left=.06, right=.98, top=.8, bottom=.24, wspace=.28)
    for index, axis in enumerate(axes):
        axis.imshow(shade, cmap="gray", vmin=-.15, vmax=1.15, extent=extent, interpolation="nearest")
        axis.add_collection(PolyCollection(old_polygons, facecolors="#68755d", edgecolors="#45543a", linewidths=.25, alpha=.55))
        if review["junction"]["status"] == "candidate" and index < 2:
            colors = ["#bc9635" if role["region"] == "hub" else "#527e77" for role in mesh["triangle_roles"]]
            axis.add_collection(PolyCollection(polygons, facecolors=colors, edgecolors="#303c35", linewidths=.55, zorder=4))
        if index < 2:
            for arm in layers["ports"]:
                profile = np.asarray(arm["outer_profile_xyz_m"])
                attached = arm["attachment_status"] == "actual_old_mesh"
                axis.plot(profile[:, 0], profile[:, 2], color="#283c30" if attached else "#b84d33",
                          linestyle="-" if attached else "--", linewidth=2., zorder=6)
                if index == 1:
                    point = profile[0]
                    axis.annotate(("saved old mesh port" if attached else "OPEN STUB: no external strip")+"\n"+arm["outer_node_id"],
                                  point[[0, 2]], xytext=(6, 10), textcoords="offset points", fontsize=8,
                                  bbox={"facecolor": "white", "alpha": .85, "edgecolor": "none"}, zorder=7)
        if index != 1:
            lines = [np.asarray(arc["xyz_m"])[:, [0, 2]] for arc in refused["refused_land_arcs"]]
            axis.add_collection(LineCollection(lines, colors="#994e64", linewidths=1.4, linestyles="dotted", zorder=5))
            axis.scatter(refused["xyz_m"][0], refused["xyz_m"][2], marker="x", c="#994e64", s=45, zorder=6)
        selected = all_points if index == 0 else focal_points if index == 1 else np.asarray([refused["xyz_m"]])[:, [0, 2]]
        pad = 35. if index != 2 else 65.
        axis.set_xlim(selected[:, 0].min()-pad, selected[:, 0].max()+pad)
        axis.set_ylim(selected[:, 1].max()+pad, selected[:, 1].min()-pad)
        axis.set_aspect("equal")
        axis.ticklabel_format(style="plain", useOffset=False)
        axis.set_xlabel("Model east X (m)")
        axis.set_ylabel("Model south Z (m)")
        axis.set_title(["Native mountain / retained strips / local context", "New saved arms + hub / explicit outer ports", "Original 06 refused hub cell:62896"][index], fontsize=10)
    reasons = sorted({reason for arc in refused["refused_land_arcs"] for reason in arc["rejection_reasons"]})
    axes[2].text(.02,.02,"06 rejection reasons:\n"+"\n".join(reasons), transform=axes[2].transAxes, fontsize=8,
                 bbox={"facecolor": "white", "alpha": .85, "edgecolor": "none"})
    binding = review["independent_audit_reference"]
    audit_label = binding.get("referenced_status", binding["binding_status"])
    figure.suptitle("Local ported junction inspection | "+review["junction"]["hub_node_id"]+" | audit reference: "+audit_label, fontsize=14, y=.96)
    figure.text(.5,.87,"Saved geometry status: "+review["junction"]["status"]+"; display triangles approximate exact source-depth functions. NOT full river / fine / hydraulic.", ha="center", fontsize=10)
    figure.legend(handles=[Patch(facecolor="#68755d", label="Retained saved 06 strips"), Patch(facecolor="#527e77", label="New saved arm triangles"),
                           Patch(facecolor="#bc9635", label="New saved hub triangles"), Line2D([], [], color="#b84d33", linestyle="--", label="Open stub; no external strip"),
                           Line2D([], [], color="#994e64", linestyle=":", label="Original 62896 refusal; no bed generated")],
                  loc="lower center", bbox_to_anchor=(.5,.075), ncol=3, fontsize=9, frameon=False)
    figure.text(.5,.025,"No old 07 overlay. Native source samples remain unchanged. Audit state requires matching preparation index, junction SHA and every source pin.", ha="center", fontsize=9)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=150)
    plt.close(figure)
    return output.getvalue()


def main():
    arguments = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arguments.add_argument("--junction", type=Path, required=True)
    arguments.add_argument("--junction-sha256", required=True)
    arguments.add_argument("--audit", type=Path)
    arguments.add_argument("--audit-sha256")
    arguments.add_argument("--audit-schema", default=AUDIT_SCHEMA)
    arguments.add_argument("--index", type=Path, help="single-junction preparation index, required for actual audit binding")
    arguments.add_argument("--index-sha256")
    arguments.add_argument("--output", type=Path, required=True)
    args = arguments.parse_args()
    review = load_review(args.junction, args.junction_sha256, args.audit, args.audit_sha256, args.audit_schema, args.index, args.index_sha256)
    overview = render_overview(review)
    review["resource"]["peak_rss_bytes"] = check_memory()
    print(publish_directory(args.output, {"review.json": encoded(review), "caseartifact.json": encoded(caseartifact(review)), "overview.png": overview}))


if __name__ == "__main__":
    main()
