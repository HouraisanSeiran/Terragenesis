"""Pinned 07 patch delta and provenance addendum; frozen 06 exports stay unchanged."""

from collections import Counter
import gc
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_td_watershed_inspection import ROOT, encoded, parser, publish_directory, read_json_pin, require, unique
from audit_td_watershed_connectivity import check_memory


BASE = ROOT / "verification/natural-river-network"
FIXED = {
    "inspection_06": ("watershed-inspection-export-20261006-01/review.json", "db7a511457cc14291e9f01f82414cc5a2443c1cb55ae710fbdfe6ddb69a93ee9"),
    "connectivity_06": ("connectivity-inspection-20261006-01/report.json", "2a59530e456961e7154cc94c2df3fe7ddcc1663de7d38bb4486f47db29b4555a"),
    "07_index": ("watershed-interface-patches-20261005-06/index.json", "e655e345342fc2aaa3a8fc9b77715704ef860b9969fd7ab16d8156a74ede6bba"),
    "07_audit": ("watershed-interface-patches-20261005-06/independent-audit.json", "f5faed2deae2943cc7ab0ea8cdcd4cd1cdf9174fb1ec1a193c5472c4b256edf9"),
    "09_index": ("lake-entry-taper-20261005-02/index.json", "dc6f3072dd717fa7300c087b7d4ab9b23db9baab8d0a51ed0d4bdf7de788b17e"),
    "09_fine_index": ("fine-bed-raster-lake-entry-20261005-01/index.json", "113f3990de828f25f4b766afffa58c948a5d5aea12b9e2de05d383486795f759"),
    "09_fine_audit": ("fine-bed-raster-lake-entry-20261005-01/independent-audit.json", "787ed835e848bc7b23158d845db2160495ae0ea01dfccf7813773d046d95b6ed"),
    "10_index": ("fine-bed-shards-entry-20261005-01/index.json", "af3c777166218e8968c0083e0a8e32ad5a416f8d841f5c09ebcd4c8f544261f9"),
    "10_audit": ("fine-bed-shards-entry-20261005-01/independent-audit.json", "5ef4a0ae5a09244a148dd5bee4db96f28aa7c479eda97e33c835826ae3888ea7"),
}


def triangle_census(pin):
    path = Path(pin["path"]).resolve(strict=True)
    require(path.is_relative_to(ROOT.resolve()) and path.stat().st_size <= 64*1024**2, "fine input outside budget/workspace")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            digest.update(block)
    require(digest.hexdigest() == pin["sha256"], "fine provenance SHA mismatch")
    with path.open(encoding="utf-8") as stream:
        record = json.load(stream)
    check_memory()
    counts = dict(Counter(triangle["source_package"] for triangle in record["triangles"]))
    result = {"schema": record["schema"], "source_package_triangle_counts": counts,
              "patch_07_triangle_count": counts.get("07", 0), "input_pins": record.get("input_pins", record.get("inputs", {})),
              "selection": record["selection"], "identity_sha256": record["identity_sha256"]}
    require(result["identity_sha256"] == pin["identity_sha256"], "fine identity mismatch")
    del record
    gc.collect()
    return result, {**pin, "path": str(path), "bytes": path.stat().st_size}


def validate_patches(record, paths, sections):
    require(record["schema"] == "td-watershed-interface-patches-v1", "unsupported 07 schema")
    require(record["composite_parent_identity"]["paths"] == paths["identity_sha256"]
            and record["composite_parent_identity"]["sections"] == sections["identity_sha256"], "07 parent mismatch")
    require(record["parametric_only"] is True and record["source_bed_unchanged"] is True, "07 is not parametric-only")
    for flag in ("bed_changed", "bed_rasterized", "water_surface_meshed", "hydraulic_solved", "natural_outlet_certified", "flow_regime_certified", "publish_ready"):
        require(record[flag] is False, "unsupported 07 capability " + flag)
    nodes = unique(paths["nodes"], "node_id")
    arcs = unique(paths["arcs"], "arc_id")
    unique(record["patches"], "patch_id")
    attachment = []
    for patch in record["patches"]:
        require(all(node in nodes for node in patch["node_ids"]) and all(key in arcs for key in patch["source_arc_ids"]), "07 missing source reference")
        require(patch["status"] in ("candidate", "rejected"), "unknown patch status")
        if patch["status"] == "rejected":
            require(not patch["triangles"] and patch["rejection_reasons"], "rejected patch has usable geometry")
            continue
        require(patch["triangles"] and not patch["rejection_reasons"], "candidate lacks saved mesh")
        vertices = patch["vertices_xyz_m"]
        require(np.asarray(vertices).ndim == 2 and np.asarray(vertices).shape[1] == 3 and np.isfinite(vertices).all(), "nonfinite patch geometry")
        incidence = Counter()
        for triangle in patch["triangles"]:
            require(len(triangle) == 3 and len(set(triangle)) == 3
                    and all(type(index) is int and 0 <= index < len(vertices) for index in triangle), "bad 07 triangle reference")
            for first, second in zip(triangle, triangle[1:] + triangle[:1]):
                incidence[tuple(sorted((first, second)))] += 1
        require(max(incidence.values()) <= 2, "nonmanifold 07 local edge")
        for first, second in patch["boundary_edges"]:
            require(incidence[tuple(sorted((first, second)))] == 1, "declared 07 boundary not saved triangle boundary")
        boundary = {frozenset((tuple(vertices[first]), tuple(vertices[second])))
                    for (first, second), count in incidence.items() if count == 1}
        profile_census = []
        declared_profiles = Counter()
        for index, profile in enumerate(patch["cross_sections"]):
            signature = tuple(tuple(point) for point in profile)
            declared_profiles[signature] += 1
            valid_four_points = len(signature) == 4 and len(set(signature)) == 4
            covered = [frozenset((first, second)) in boundary
                       for first, second in zip(signature, signature[1:])]
            profile_census.append({"declared_profile_index": index,
                                   "four_distinct_points": valid_four_points,
                                   "actual_boundary_segment_count": sum(covered),
                                   "actual_whole_four_point_boundary": valid_four_points and len(covered) == 3 and all(covered)})
        matching = []
        for node in patch["node_ids"]:
            ids = sections["mesh"]["node_vertex_indices"].get(node, [])
            profile = [sections["mesh"]["vertices_xyz_m"][index] for index in ids]
            if len(profile) == 4 and all(frozenset((tuple(first), tuple(second))) in boundary
                                         for first, second in zip(profile, profile[1:])):
                matching.append(node)
        attachment.append({"patch_id": patch["patch_id"], "kind": patch["kind"], "source_arc_ids": patch["source_arc_ids"],
                           "declared_profile_census": profile_census,
                           "duplicate_declared_profile_occurrences": sum(count-1 for count in declared_profiles.values()),
                           "distinct_actual_whole_four_point_boundary_profiles": len({
                               tuple(tuple(point) for point in patch["cross_sections"][item["declared_profile_index"]])
                               for item in profile_census if item["actual_whole_four_point_boundary"]}),
                           "exact_complete_06_mesh_boundary_profile_nodes": matching,
                           "source_06_refused_arc_ids": [key for key in patch["source_arc_ids"]
                                                       if key not in {edge["arc_id"] for edge in sections["edge_sections"]}],
                           "composition_status": "uncomposed_geometry_prototype",
                           "original_strip_truncation_or_replacement_saved": False,
                           "integrated_mesh_or_fine_verified": False})
    return attachment


def patch_case(record, kind, pins):
    vertices, triangles, provenance = [], [], []
    for patch in record["patches"]:
        if patch["status"] != "candidate" or patch["kind"] != kind:
            continue
        offset = len(vertices)
        vertices.extend(patch["vertices_xyz_m"])
        for index, triangle in enumerate(patch["triangles"]):
            triangles.append([offset + vertex for vertex in triangle])
            provenance.append({"patch_id": patch["patch_id"], "local_triangle_index": index})
    heights = [vertex[1] for vertex in vertices]
    return {"schema": "td-watershed-07-patch-mesh-case-v1", "kind": "mesh", "caseId": "07-"+kind,
            "label": "07 uncomposed "+kind+" geometry prototype; side-by-side only",
            "mesh": {"vertices": vertices, "triangles": triangles, "bed": heights, "h0": heights,
                     "water": None, "wet": [], "wetCells": [], "cells": [], "hydrologicOwner": []},
            "triangle_provenance": provenance, "pins": pins,
            "evidence": {"status": "diagnostic_saved_geometry", "scope": "07-only uncomposed prototype; side-by-side inspection, NOT an overlay of an integrated mesh; H0 is bed alias",
                         "limitations": ["Independent 07 audit passed only for local candidates.", "Not consumed by pinned 09/10 fine.",
                                         "Junction copied hub profiles are not four-point triangle boundary ports.",
                                         "Corner translated end profiles do not trim or replace original full-length strips.",
                                         "No full-network bank or hydraulic certification."]},
            "composition_status": "uncomposed_geometry_prototype", "display_mode": "side_by_side_only",
            "finepassed": False, "hydraulic_ready": False, "water_surface_meshed": False, "parametric_only": True}


def render(base, patches):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import LightSource
    from matplotlib.patches import Patch

    height = np.asarray(base["terrain"]["height_m"])
    origin = np.asarray(base["coordinates"]["origin_m_xz"])
    spacing = base["coordinates"]["spacing_m"]
    shade = LightSource(315, 45).hillshade(height, dx=spacing, dy=spacing)
    extent = [-spacing/2, (height.shape[1]-.5)*spacing, (height.shape[0]-.5)*spacing, -spacing/2]
    mesh = base["layers"]["saved_bed_mesh"]
    old = (np.asarray(mesh["vertices_xyz_m"])[:, [0, 2]]-origin)[np.asarray(mesh["triangles"])]
    accepted = [patch for patch in patches["patches"] if patch["status"] == "candidate"]
    chosen = {}
    for kind in ("junction", "corner_transition"):
        candidates = [patch for patch in accepted if patch["kind"] == kind]
        focal = "cell:62896" if kind == "junction" else "cell:62895"
        chosen[kind] = next((patch for patch in candidates if focal in patch["node_ids"]), candidates[len(candidates)//2])
    cells = np.asarray(base["views"]["primary_support_cell_ids"])
    rows, cols = np.divmod(cells, height.shape[1])
    bounds = [cols.min()*spacing-90, cols.max()*spacing+90, rows.min()*spacing-90, rows.max()*spacing+90]
    figure, axes = plt.subplots(2, 2, figsize=(14, 12))
    figure.subplots_adjust(top=.9, bottom=.16, hspace=.32, wspace=.24)
    for index, axis in enumerate(axes.flat):
        axis.imshow(shade, cmap="gray", extent=extent, vmin=-.15, vmax=1.15, interpolation="nearest")
        if index == 0:
            axis.add_collection(PolyCollection(old, facecolors="#657457", edgecolors="#516346", linewidths=.1, alpha=.65))
        for kind, color in (("corner_transition", "#a35b99"), ("junction", "#ce9a30")):
            items = [patch for patch in accepted if patch["kind"] == kind] if index == 1 else [chosen[kind]] if index > 1 else []
            for patch in items:
                points = np.asarray(patch["vertices_xyz_m"])[:, [0, 2]]-origin
                polygons = points[np.asarray(patch["triangles"])]
                axis.add_collection(PolyCollection(polygons, facecolors=color, edgecolors="#3d3035",
                                                   linewidths=.15 if index < 2 else .7, zorder=4))
        if index < 2:
            axis.set_xlim(bounds[0], bounds[1])
            axis.set_ylim(bounds[3], bounds[2])
            if index == 1:
                for kind, color in (("corner_transition", "#a35b99"), ("junction", "#ce9a30")):
                    centers = [np.mean(np.asarray(patch["vertices_xyz_m"])[:, [0, 2]], axis=0)-origin
                               for patch in accepted if patch["kind"] == kind]
                    axis.scatter(*np.asarray(centers).T, s=3, c=color, alpha=.6, zorder=5)
        else:
            kind = "junction" if index == 2 else "corner_transition"
            patch = chosen[kind]
            points = np.asarray(patch["vertices_xyz_m"])[:, [0, 2]]-origin
            center = points.mean(axis=0)
            radius = max(2., np.max(np.ptp(points, axis=0))*.7)
            axis.set_xlim(center[0]-radius, center[0]+radius)
            axis.set_ylim(center[1]+radius, center[1]-radius)
            axis.text(.02,.02,patch["patch_id"]+"\nUncomposed prototype; NOT attached strip ports", transform=axis.transAxes, fontsize=9)
        axis.set_aspect("equal")
        axis.set_xlabel("Local east from native origin (m)")
        axis.set_ylabel("Local south (m)")
        axis.set_title(["Frozen 06 strips ONLY (not latest geometry)", "07 prototypes ONLY on native terrain (not merged with 06)",
                        "07 hub prototype: copied profiles are NOT boundary ports", "07 corner prototype: original strips NOT truncated"][index], fontsize=10)
    figure.suptitle("Side-by-side inspection | 07 uncomposed geometry prototypes, NOT connected river beds", fontsize=14, y=.96)
    figure.legend(handles=[Patch(facecolor="#657457", label="06 saved strips"), Patch(facecolor="#a35b99", label="07 corner candidates"),
                           Patch(facecolor="#ce9a30", label="07 junction candidates")], loc="lower center", bbox_to_anchor=(.5,.07), ncol=3)
    figure.text(.5,.025,"07 audit passed for local candidate geometry. Pinned 09/10 fine consumes 06 + 09, NOT 07.\n"
                "1188 corner + 195 junction prototypes; 178 refusals. No mesh composition, water, finepassed or whole-network claim.", ha="center", fontsize=10)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=140)
    plt.close(figure)
    return output.getvalue()


def main():
    args = parser(__doc__).parse_args()
    records, pins = {}, {}
    for name, (relative, sha) in FIXED.items():
        records[name], pins[name] = read_json_pin({"path": str(BASE/relative), "sha256": sha}, BASE)
    base = records["inspection_06"]
    require(base["pins"]["index"]["sha256"] == args.index_sha256
            and Path(base["pins"]["index"]["path"]).resolve() == args.index.resolve(), "06 index differs from fixed inspection")
    paths, pins["06_paths"] = read_json_pin(base["pins"]["paths"], BASE)
    sections, pins["06_sections"] = read_json_pin(base["pins"]["sections"], BASE)
    index = records["07_index"]
    patches, pins["07_patches"] = read_json_pin(index["patches"], Path(pins["07_index"]["path"]).parent)
    audit = records["07_audit"]
    require(audit["status"] == "passed" and not audit["errors"] and all(check["passed"] for check in audit["checks"]), "07 independent audit not passed")
    require(patches["identity_sha256"] == index["core"]["identity_sha256"] == audit["core_identity_sha256"]
            and patches["shape_identity_sha256"] == index["core"]["shape_identity_sha256"] == audit["core_shape_identity_sha256"]
            and patches["summary"] == index["summary"] == audit["summary"], "07 audit identity mismatch")
    require(index["source_06_index_sha256"] == base["pins"]["index"]["sha256"]
            and all(index["source_artifacts"][key] == base["pins"][key]["sha256"] for key in ("paths", "sections", "review")), "07 source pins mismatch")
    attachments = validate_patches(patches, paths, sections)
    port_census = {}
    for kind in sorted({item["kind"] for item in attachments}):
        items = [item for item in attachments if item["kind"] == kind]
        profiles = [profile for item in items for profile in item["declared_profile_census"]]
        port_census[kind] = {"candidate_prototypes": len(items), "declared_profile_occurrences": len(profiles),
                             "actual_whole_four_point_boundary_occurrences": sum(profile["actual_whole_four_point_boundary"] for profile in profiles),
                             "distinct_whole_boundary_profiles_sum_per_patch": sum(item["distinct_actual_whole_four_point_boundary_profiles"] for item in items),
                             "missing_whole_boundary_profile_occurrences": sum(not profile["actual_whole_four_point_boundary"] for profile in profiles),
                             "duplicate_declared_profile_occurrences": sum(item["duplicate_declared_profile_occurrences"] for item in items),
                             "original_strip_replacements_saved": 0, "composed_connections_certified": 0}
    all_arcs = unique(paths["arcs"], "arc_id")
    focal = {"highest_q_chain_last_node": "cell:62895", "refused_next_arc_id": "receiver:62895:62896",
             "actual_junction_hub_node": "cell:62896",
             "hub_incident_land_arcs": [{"arc_id": arc["arc_id"], "node_ids": arc["node_ids"]}
                                        for arc in all_arcs.values() if arc["kind"] == "land_channel" and "cell:62896" in arc["node_ids"]],
             "junction_patch_id": "junction:cell:62896", "composition_status": "uncomposed_geometry_prototype"}
    fine09, pins["09_fine_raster"] = triangle_census(records["09_fine_index"]["raster"])
    raw10, pins["10_raw"] = triangle_census(records["10_index"]["raw"])
    require(records["09_fine_audit"]["status"] == "passed"
            and records["09_fine_audit"]["raster_sha256"] == pins["09_fine_raster"]["sha256"], "09 audit linkage mismatch")
    require(records["10_audit"]["index_sha256"] == pins["10_index"]["sha256"]
            and records["10_audit"]["raw_sha256"] == pins["10_raw"]["sha256"], "10 audit linkage mismatch")
    fine09_refs = records["09_fine_index"]["inputs"]
    fine10_refs = records["10_index"]["inputs"]
    require(fine09_refs["06_sections"]["sha256"] == pins["06_sections"]["sha256"]
            and fine10_refs["06_sections"]["sha256"] == pins["06_sections"]["sha256"]
            and fine10_refs["base_index"]["sha256"] == pins["09_fine_index"]["sha256"]
            and fine09_refs["09_transitions"]["sha256"] == fine10_refs["09_transitions"]["sha256"]
            == records["09_index"]["entries"]["sha256"], "fine provenance linkage mismatch")
    candidate_counts = dict(Counter(patch["kind"] for patch in patches["patches"] if patch["status"] == "candidate"))
    consumed = fine09["patch_07_triangle_count"] + raw10["patch_07_triangle_count"]
    require(consumed == 0 and set(fine09["source_package_triangle_counts"]) <= {"06", "09"}
            and set(raw10["source_package_triangle_counts"]) <= {"06", "09"}, "fixed fine lineage changed; review conclusions required")
    report = {"schema": "td-watershed-connectivity-07-lineage-addendum-v1", "pins": pins,
              "scope_correction": "Previous 238-component connectivity and PNG are 06-only, NOT latest whole-network geometry. 07 has separate saved local candidates; no updated merged-network certification is inferred.",
              "07_summary": patches["summary"], "07_candidate_by_kind": candidate_counts,
              "07_vertices": sum(len(patch["vertices_xyz_m"]) for patch in patches["patches"] if patch["status"] == "candidate"),
              "07_triangles": sum(len(patch["triangles"]) for patch in patches["patches"] if patch["status"] == "candidate"),
              "07_independent_audit": audit, "07_to_06_boundary_evidence": attachments,
              "actual_whole_four_point_boundary_port_census": port_census,
              "focal_highest_q_gap": focal,
              "prototype_limitations": ["_make_junction copies the hub node profile for each arm, but center-plus-ring triangles do not use those complete four-point profiles as boundary ports.",
                                        "_make_corner translates a shared-node profile into new end faces; no original full-length strip truncation/replacement is saved.",
                                        "A matching boundary occurrence is not an integrated connection; no composed connection is certified by this inspection."],
              "candidates_with_exact_complete_06_boundary_profile": sum(bool(item["exact_complete_06_mesh_boundary_profile_nodes"]) for item in attachments),
              "fine09_provenance": fine09, "fine10_provenance": raw10, "patch07_consumed_by_pinned_09_10_fine": False,
              "next_steps": ["Bind 07 patch IDs and exact complete boundary profiles to separately saved integrated strips; resolve any offset or incomplete port rather than welding by node name.",
                             "Feed that new geometry explicitly into a new fine selection/raster/shard package with 07 triangle provenance and whole-corridor coverage/material checks.",
                             "Only after composition and fine gates, inspect saved evidence; candidate07 audit alone is not finepassed. Do not run a new solver in this inspection."],
              "other_current_evidence": {"source": "main coordinator statement, not independently pinned here",
                                         "banks_accepted_passed": 12, "fine240_passed": True,
                                         "scope": "Separate current banks/fine evidence is not an acceptance upgrade for uncomposed 07 prototypes; no new solver requested."},
              "resource": {"peak_rss_bytes": check_memory(), "max_rss_bytes": 1024**3}, "finepassed": False,
              "whole_network_bank_continuity_certified": False, "hydraulic_ready": False}
    delta = {"schema": "td-watershed-inspection-v2", "base_review": pins["inspection_06"],
             "coordinates": base["coordinates"], "pins": pins,
             "layers": {"patches_07": {"schema": patches["schema"], "patches": patches["patches"],
                                       "summary": patches["summary"], "independent_audit": pins["07_audit"],
                                       "semantics": "uncomposed geometry prototypes, side-by-side only; not merged into 06 or finepassed",
                                       "composition_status": "uncomposed_geometry_prototype", "display_mode": "side_by_side_only",
                                       "actual_whole_four_point_boundary_port_census": port_census}},
             "scope_correction": report["scope_correction"], "finepassed": False, "hydraulic_ready": False}
    text = ("# 07 Saved Patch Layer and Fine Consumption Addendum\n\n"+report["scope_correction"]+"\n\n"
            f"07 local audit passed: {candidate_counts}; 178 refusals retained; {report['07_vertices']} saved vertices / {report['07_triangles']} triangles.\n\n"
            f"09 fine triangle sources: {fine09['source_package_triangle_counts']}. 10 raw additions: {raw10['source_package_triangle_counts']}. No 07 consumption.\n\n"
            f"Candidates with a complete exact 06 mesh-node profile covered by actual 07 boundary triangle edges: {report['candidates_with_exact_complete_06_boundary_profile']}. This narrow attachment check is not a global merge audit.\n\n"
            f"Actual whole-four-point boundary census: {port_census}. These are boundary occurrences, NOT composed connections.\n\n"
            "Junction cross_sections repeat the same hub profile per arm; center+ring triangles do not provide those four-point boundary ports. Corner translated end faces have no saved truncation/replacement of original full-length strips. Neither proves reconnection.\n\n"
            f"Highest-Q chain ends at cell:62895, next refused arc receiver:62895:62896; actual hub is cell:62896. Incident saved land arcs: {focal['hub_incident_land_arcs']}.\n\n"
            "review-v2.json is a delta: load base_review by absolute path and SHA, then patches_07 for SIDE-BY-SIDE UNCOMPOSED inspection only. Do not overlay as a single connected mesh. Caseartifacts remap local triangle indices only; no welding, joining, water or finepassed. H0 is a renderer-required bed alias.\n\n"
            "overview-v2.png shows 06-only and 07-only panels on native terrain, NOT a composed overlay. Markers locate tiny prototypes; details show exact triangles. Earlier v2 images remain historical and cannot certify composition.\n\n"
            "Coordinator reports current banks audit 12 accepted/passed and fine240 passed; these separate results are not independently pinned in this 07/09/10 lineage inspection and do not upgrade 07. No new solver.\n\n"
            "## Concrete Next Steps\n\n"+"\n".join("- "+step for step in report["next_steps"])+"\n")
    overview = render(base, patches)
    report["resource"]["peak_rss_bytes"] = check_memory()
    artifacts = {"review-v2.json": encoded(delta), "connectivity-addendum.json": encoded(report), "contract.md": text.encode(),
                 "turn-caseartifact.json": encoded(patch_case(patches, "corner_transition", pins)),
                 "junction-caseartifact.json": encoded(patch_case(patches, "junction", pins)), "overview-v2.png": overview}
    check_memory()
    print(publish_directory(args.output, artifacts))
    print(candidate_counts, report["07_vertices"], report["07_triangles"], "exact 06 boundary attachment candidates", report["candidates_with_exact_complete_06_boundary_profile"])
    print("09", fine09["source_package_triangle_counts"], "10", raw10["source_package_triangle_counts"])
    print("actual whole-four-point boundary census", port_census)


if __name__ == "__main__":
    main()
