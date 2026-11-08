"""Pure IO review of a saved shared-midpoint branched channel fragment.

API: load_review(index_path, index_sha256, audit_path=None, audit_sha256=None,
audit_schema=AUDIT_SCHEMA), caseartifact(review), render_overview(review).
No generator, connectivity algorithm, independent auditor or solver invocation.
Only saved new fragment geometry is displayed; no old 06/07 mesh overlay.
Scientific figures use local metres plus an explicit model-coordinate origin;
renderer vertices and triangle indices remain exactly as saved.
CLI: D:/anaconda/python.exe -B tools/export_td_shared_port_channel_review.py
--index <index.json> --index-sha256 <SHA> --audit <audit.json>
--audit-sha256 <SHA> --audit-schema td-shared-port-channel-independent-audit-v1
--output <NEW workspace directory>. Audit flags may be omitted: not_supplied.
Outputs: review.json, caseartifact.json and overview.png, each <=64MiB.
Optional --oblique-3d adds oblique-3d.png using original native grid samples;
--vertical-exaggeration defaults to 1.0 and affects plotting only.
"""

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_td_watershed_inspection import (
    DEFAULT_INDEX, DEFAULT_SHA256, MAX_BYTES, ROOT, encoded, publish_directory,
    read_json_pin, read_pin, require, unique)
from export_td_ported_junction_review import EXTRA_SOURCE_SHAS, FALSE_FLAGS, signatures, validate_mesh
from audit_td_watershed_connectivity import check_memory


SCHEMA = "td-shared-port-channel-review-v1"
AUDIT_SCHEMA = "td-shared-port-channel-independent-audit-v1"
PACKAGE_PARTS = ("graph", "selection", "manifest", "mesh", "topology")


def audit_binding(audit, schema, index, manifest, pins):
    failures = []
    if audit.get("schema") != schema:
        failures.append("audit_schema_mismatch")
    for name in ("index",) + PACKAGE_PARTS:
        if audit.get(name + "_sha256") != pins[name]["sha256"]:
            failures.append("audit_pin_mismatch_or_missing:" + name)
    if audit.get("manifest_identity_sha256") != manifest["identity_sha256"]:
        failures.append("audit_manifest_identity_mismatch_or_missing")
    if (set(audit.get("inputs", {})) != set(index["inputs"])
            or signatures(audit.get("inputs", {})) != signatures(index["inputs"])):
        failures.append("audit_inputs_mismatch_or_missing")
    selected = sorted(row["node_id"] for row in manifest["nodes"] if row["composition_status"] == "selected")
    if sorted(audit.get("selected_node_ids", [])) != selected:
        failures.append("audit_selected_node_census_mismatch_or_missing")
    for category in ("nodes", "ports"):
        actual = audit.get(category, {})
        expected = pins[category]
        if not isinstance(actual, dict) or set(actual) != set(expected):
            failures.append("audit_record_census_mismatch_or_missing:" + category)
            continue
        for identifier, pin in expected.items():
            value = actual[identifier]
            if (not isinstance(value, dict) or not value.get("path")
                    or Path(value["path"]).resolve() != Path(pin["path"]).resolve()
                    or value.get("sha256") != pin["sha256"]
                    or value.get("identity_sha256") != pin["identity_sha256"]):
                failures.append("audit_record_binding_mismatch:" + category + ":" + identifier)
    if audit.get("status") not in ("passed", "failed"):
        failures.append("audit_status_missing_or_unknown")
    if not isinstance(audit.get("errors"), list) or audit.get("status") == "passed" and audit["errors"]:
        failures.append("audit_errors_missing_or_inconsistent")
    for flag in ("full_network_verified", "hydraulic_ready", "hydraulic_solved", "fine_generated", "material_budget_verified"):
        if audit.get(flag) is not False:
            failures.append("audit_capability_mismatch:" + flag)
    result = {"binding_status": "not_matched" if failures else "matched", "binding_failures": failures,
              "scope": "saved task14 independent evidence audit reference only; not executed by exporter"}
    if not failures:
        result["referenced_status"] = audit["status"]
        result["errors"] = audit["errors"]
    return result


def load_sources(index):
    original, original_pin = read_json_pin({"path": str(DEFAULT_INDEX), "sha256": DEFAULT_SHA256}, ROOT)
    paths, paths_pin = read_json_pin(original["paths"], DEFAULT_INDEX.parent)
    sections, sections_pin = read_json_pin(original["sections"], DEFAULT_INDEX.parent)
    _, hierarchy_pin = read_pin(original["inputs"]["hierarchy"], DEFAULT_INDEX.parent)
    expected = {"06_index": original_pin, "06_paths": paths_pin, "06_sections": sections_pin, "hierarchy": hierarchy_pin}
    require(signatures(expected).issubset(signatures(index["inputs"])), "fixed 06/native source path/SHA mismatch")
    extra_paths = {"source_bank_parent_index": "index.json", "source_bank_parent_audit": "independent-audit.json",
                   "wet_protection_manifest": "manifest.json"}
    for name, digest in EXTRA_SOURCE_SHAS.items():
        pin = index["inputs"][name]
        fixed_path = ROOT / "verification/natural-river-network/source-conforming-banks-entry-20261006-03" / extra_paths[name]
        require(pin["sha256"] == digest and Path(pin["path"]).resolve() == fixed_path.resolve(), "fixed source-bank/wet pin mismatch: " + name)
    pins = {}
    for name, pin in index["inputs"].items():
        _, pins[name] = read_pin(pin, ROOT)
    with np.load(hierarchy_pin["path"], allow_pickle=False) as bundle:
        native_manifest = json.loads(bytes(bundle["manifest"]))
        height = bundle["height_m"].copy()
        valid = bundle["valid_mask"].copy()
    require(native_manifest["identity_sha256"] == hierarchy_pin["identity_sha256"]
            and height.ndim == 2 and height.size <= 250000 and valid.shape == height.shape
            and np.isfinite(height).all(), "invalid native terrain")
    check_memory()
    return paths, sections, pins, native_manifest, height, valid


def caseartifact(review):
    mesh = review["layers"]["saved_fragment_mesh"]
    heights = [point[1] for point in mesh["vertices_xyz_m"]]
    return {"schema": "td-shared-port-channel-mesh-case-v1", "kind": "mesh",
            "caseId": "shared-port-fragment-" + review["manifest_identity_sha256"][:12],
            "label": "Saved shared-midpoint bed fragment; open ends; NOT full river or fine",
            "mesh": {"vertices": mesh["vertices_xyz_m"], "triangles": mesh["triangles"],
                     "bed": heights, "h0": heights, "water": None, "wet": [],
                     "wetCells": [], "cells": [], "hydrologicOwner": [], "cellOwner": []},
            "face_origins": mesh["face_origins"], "face_route_roles": review["layers"]["face_route_roles"],
            "face_component_ids": review["layers"]["face_component_ids"],
            "open_ports": review["layers"]["open_ports"], "pins": review["pins"],
            "coordinates": review["coordinates"], "topology": review["topology"],
            "independent_audit_reference": review["independent_audit_reference"],
            "evidence": {"status": "diagnostic_saved_geometry", "limitations": review["limitations"]}, **FALSE_FLAGS}


def render_overview(review):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection
    from matplotlib.colors import LightSource
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Rectangle
    from matplotlib.ticker import MaxNLocator

    layers = review["layers"]
    mesh = layers["saved_fragment_mesh"]
    points = np.asarray(mesh["vertices_xyz_m"], float).reshape(-1, 3)
    triangles = np.asarray(mesh["triangles"], int).reshape(-1, 3)
    require(len(triangles) > 0, "no saved fragment triangles to render")
    local_origin = np.asarray(review["plot_origin_m_xz"])
    polygons = points[:, [0, 2]][triangles] - local_origin
    plot_bounds = np.asarray([polygons.reshape(-1, 2).min(axis=0), polygons.reshape(-1, 2).max(axis=0)])
    colors_by_role = {"longest_saved_chain": "#ad7e32", "saved_branch": "#527363", "node_core": "#4a5147",
                      "other_component": "#817b89", "open_half_arm": "#989b8d"}
    colors = [colors_by_role[role] for role in layers["face_route_roles"]]
    coords = review["coordinates"]
    spacing = coords["spacing_m"]
    native_origin = np.asarray(coords["origin_m_xz"]) - local_origin
    height = np.asarray(review["native_terrain"]["height_m"], float)
    valid = np.asarray(review["native_terrain"]["valid_mask"], bool)
    shade = LightSource(315, 45).hillshade(height, dx=spacing, dy=spacing)
    shade[~valid] = np.nan
    extent = [native_origin[0] - spacing/2, native_origin[0] + (height.shape[1]-.5)*spacing,
              native_origin[1] + (height.shape[0]-.5)*spacing, native_origin[1] - spacing/2]
    figure = plt.figure(figsize=(17, 10))
    grid = figure.add_gridspec(2, 2, width_ratios=[1, 2.8], left=.07, right=.97,
                              top=.83, bottom=.19, hspace=.45, wspace=.3)
    context_axis = figure.add_subplot(grid[0, 0])
    detail_axis = figure.add_subplot(grid[1, 0])
    corridor_axis = figure.add_subplot(grid[:, 1])
    ports = layers["open_ports"]
    port_lines = [np.asarray(port["profile_xyz_m"])[:, [0, 2]] - local_origin for port in ports]
    refused_lines = [np.asarray(arc["xyz_m"])[:, [0, 2]] - local_origin for arc in layers["refused_arcs"] if arc["reason"] != "node_budget_boundary"]
    clipped_lines = [np.asarray(arc["xyz_m"])[:, [0, 2]] - local_origin for arc in layers["refused_arcs"] if arc["reason"] == "node_budget_boundary"]
    anchors = layers["unclosed_lake_anchors"]
    anchor_points = np.asarray([record["xyz_m"] for record in anchors], float).reshape(-1, 3)[:, [0, 2]] - local_origin
    focus_port = ports[-1] if ports else None
    if focus_port:
        focus = np.asarray(focus_port["profile_xyz_m"])[:, [0, 2]] - local_origin
    elif len(anchor_points):
        focus = anchor_points[-1:]
    else:
        focus = polygons[0]
    for axis in (context_axis, corridor_axis, detail_axis):
        axis.imshow(shade, cmap="gray", extent=extent, interpolation="nearest", vmin=-.15, vmax=1.1)
        axis.add_collection(PolyCollection(polygons, facecolors=colors, edgecolors="none", zorder=4))
        axis.add_collection(LineCollection(port_lines, colors="#b43f35", linewidths=1.5,
                                           linestyles="--", zorder=6))
        axis.add_collection(LineCollection(refused_lines, colors="#8b536b", linewidths=.7,
                                           linestyles=":", alpha=.8, zorder=3))
        axis.add_collection(LineCollection(clipped_lines, colors="#777b78", linewidths=.7,
                                           linestyles="-.", alpha=.7, zorder=3))
        if len(anchor_points):
            axis.scatter(anchor_points[:, 0], anchor_points[:, 1], c="#8b536b", marker="x", s=35, zorder=7)
        axis.set_aspect("equal")
        axis.xaxis.set_major_locator(MaxNLocator(4))
        axis.yaxis.set_major_locator(MaxNLocator(4))
        axis.ticklabel_format(style="plain", useOffset=False)
        axis.tick_params(labelsize=8)
        axis.set_xlabel("Local east X (m)", fontsize=9)
        axis.set_ylabel("Local south Z (m)", fontsize=9)
    context_axis.set_xlim(extent[:2])
    context_axis.set_ylim(extent[2:])
    context_axis.add_patch(Rectangle(plot_bounds[0]-45, *(plot_bounds[1]-plot_bounds[0]+90),
                                    fill=False, edgecolor="#ad7e32", linewidth=1.6, zorder=8))
    context_axis.set_title("Full native mountain / fragment location", fontsize=10)
    corridor_axis.set_xlim(plot_bounds[0, 0]-60, plot_bounds[1, 0]+60)
    corridor_axis.set_ylim(plot_bounds[1, 1]+60, plot_bounds[0, 1]-60)
    corridor_axis.set_title("Actual saved new bed corridor / longest saved chain + branches", fontsize=12, pad=13)
    detail_axis.set_xlim(focus[:, 0].min()-40, focus[:, 0].max()+40)
    detail_axis.set_ylim(focus[:, 1].max()+40, focus[:, 1].min()-40)
    detail_axis.set_title("Saved open end / no outlet closure", fontsize=10)
    if focus_port:
        detail_axis.text(.02, .03, str(focus_port.get("label", "Saved four-point port")),
                         transform=detail_axis.transAxes, fontsize=8,
                         bbox={"facecolor": "white", "alpha": .85, "edgecolor": "none"})
    binding = review["independent_audit_reference"]
    audit_label = binding.get("referenced_status", binding["binding_status"])
    summary = review["summary"]
    figure.suptitle("Shared-midpoint branched channel fragment | audit reference: " + audit_label, fontsize=16, y=.965)
    figure.text(.5, .91, summary["caption"], ha="center", fontsize=11)
    figure.text(.5, .87, "Plot X/Z = saved model X/Z minus origin (" + format(local_origin[0], ".3f") + ", "
                + format(local_origin[1], ".3f") + ") m; Y remains source/bed elevation.", ha="center", fontsize=10)
    figure.legend(handles=[Patch(facecolor=colors_by_role["longest_saved_chain"], label="Saved longest directed arc-chain bed (not permanent trunk)"),
                           Patch(facecolor=colors_by_role["saved_branch"], label="Actual saved branch bed"),
                           Patch(facecolor=colors_by_role["node_core"], label="Saved node core / oriented half-arm interfaces"),
                           Patch(facecolor=colors_by_role["other_component"], label="Other saved component / not a connected tributary"),
                           Patch(facecolor=colors_by_role["open_half_arm"], label="Saved open half-arm / other half missing"),
                           Line2D([], [], color="#b43f35", linestyle="--", label="Open four-point port; no hydraulic boundary"),
                           Line2D([], [], color="#8b536b", linestyle=":", marker="x", label="Refused / unclosed lake anchor; NOT water"),
                           Line2D([], [], color="#777b78", linestyle="-.", label="Window-budget cut / no bed continuation")],
                  loc="lower center", bbox_to_anchor=(.5, .055), ncol=2, fontsize=8.5, frameon=False)
    figure.text(.5, .025, "Native terrain unchanged. New fragment only: no old 06/07 overlap, full network, fine DEM or hydraulic certification. Q: ordinary mean proxy prior.",
                ha="center", fontsize=9)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=170)
    plt.close(figure)
    payload = output.getvalue()
    require(len(payload) <= MAX_BYTES, "overview exceeds 64MiB")
    check_memory()
    return payload


def render_oblique(review, vertical_exaggeration=1.):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    require(np.isfinite(vertical_exaggeration) and 0.1 <= vertical_exaggeration <= 10., "vertical exaggeration must be in [0.1,10]")
    mesh = review["layers"]["saved_fragment_mesh"]
    points = np.asarray(mesh["vertices_xyz_m"], float).reshape(-1, 3)
    faces = np.asarray(mesh["triangles"], int).reshape(-1, 3)
    require(len(faces), "no saved bed faces for oblique view")
    coords = review["coordinates"]
    source_origin = np.asarray(coords["origin_m_xz"])
    plot_origin = np.asarray(review["plot_origin_m_xz"])
    spacing = coords["spacing_m"]
    height = np.asarray(review["native_terrain"]["height_m"], float)
    valid = np.asarray(review["native_terrain"]["valid_mask"], bool)
    bounds = np.asarray([points[:, [0, 2]].min(axis=0)-60, points[:, [0, 2]].max(axis=0)+60])
    low = np.maximum(0, np.floor((bounds[0]-source_origin)/spacing).astype(int))
    high = np.minimum(np.asarray(height.shape[::-1])-1, np.ceil((bounds[1]-source_origin)/spacing).astype(int))
    require(np.all(high > low), "empty native terrain crop")
    columns = np.arange(low[0], high[0]+1)
    rows = np.arange(low[1], high[1]+1)
    east, south = np.meshgrid(source_origin[0]+columns*spacing-plot_origin[0], source_origin[1]+rows*spacing-plot_origin[1])
    crop = height[rows[:, None], columns[None, :]].copy()
    crop_valid = valid[rows[:, None], columns[None, :]]
    crop[~crop_valid] = np.nan
    local_points = points.copy()
    local_points[:, 0] -= plot_origin[0]
    local_points[:, 2] -= plot_origin[1]
    polygons = local_points[:, [0, 2, 1]][faces]
    colors_by_role = {"longest_saved_chain": "#ad7e32", "saved_branch": "#527363", "node_core": "#4a5147",
                      "other_component": "#817b89", "open_half_arm": "#989b8d"}
    colors = [colors_by_role[role] for role in review["layers"]["face_route_roles"]]
    figure = plt.figure(figsize=(15, 10))
    axis = figure.add_subplot(111, projection="3d")
    figure.subplots_adjust(left=.02, right=.96, bottom=.15, top=.83)
    axis.plot_surface(east, south, crop, rcount=len(rows), ccount=len(columns),
                      color="#a6a6a1", alpha=.18, edgecolor="#83867d", linewidth=.15,
                      antialiased=True, shade=False)
    axis.add_collection3d(Poly3DCollection(polygons, facecolors=colors,
                                         edgecolors="#38463b", linewidths=.18, alpha=1.))
    for port in review["layers"]["open_ports"]:
        profile = np.asarray(port["profile_xyz_m"])
        axis.plot(profile[:, 0]-plot_origin[0], profile[:, 2]-plot_origin[1], profile[:, 1],
                  color="#b43f35", linestyle="--", linewidth=1.5)
    all_elevations = np.concatenate((crop[np.isfinite(crop)], points[:, 1]))
    elevation_low, elevation_high = all_elevations.min(), all_elevations.max()
    elevation_span = max(float(elevation_high-elevation_low), spacing/10)
    axis.set_xlim(east.min(), east.max())
    axis.set_ylim(south.min(), south.max())
    axis.set_zlim(elevation_low-elevation_span*.08, elevation_high+elevation_span*.08)
    axis.set_box_aspect([max(float(east.max()-east.min()), spacing), max(float(south.max()-south.min()), spacing),
                         (elevation_high-elevation_low+elevation_span*.16)*vertical_exaggeration])
    axis.view_init(elev=32, azim=-125)
    axis.xaxis.set_major_locator(MaxNLocator(5))
    axis.yaxis.set_major_locator(MaxNLocator(5))
    axis.zaxis.set_major_locator(MaxNLocator(5))
    axis.ticklabel_format(style="plain", useOffset=False)
    axis.tick_params(labelsize=9)
    axis.set_xlabel("Local east X (m)", labelpad=10)
    axis.set_ylabel("Local south Z (m)", labelpad=10)
    axis.set_zlabel("Elevation: model Y (m)", labelpad=10)
    figure.suptitle("Native mountain crop + actual saved new bed fragment", fontsize=16, y=.96)
    figure.text(.5, .9, "Horizontal origin (" + format(plot_origin[0], ".3f") + ", " + format(plot_origin[1], ".3f")
                + ") model m; vertical exaggeration " + format(vertical_exaggeration, ".3g") + "x; elevation values unchanged.", ha="center", fontsize=10)
    figure.text(.5, .865, "Original " + format(spacing, ".3g") + " m native samples, coarse surface visualization only; no resampling / fine DEM / water surface.", ha="center", fontsize=10)
    figure.legend(handles=[Patch(facecolor="#a6a6a1", alpha=.3, label="Native source grid (transparent for bed inspection)"),
                           Patch(facecolor="#ad7e32", label="Saved longest-chain bed"),
                           Patch(facecolor="#527363", label="Saved branch bed")], loc="lower center", bbox_to_anchor=(.5, .07), ncol=3, fontsize=9, frameon=False)
    figure.text(.5, .025, "New saved geometry only. Open ends remain unbound. Not full network / fine / material / hydraulic certification.", ha="center", fontsize=10)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=170)
    plt.close(figure)
    payload = output.getvalue()
    require(len(payload) <= MAX_BYTES, "oblique view exceeds 64MiB")
    check_memory()
    return payload


def load_review(index_path, index_sha256, audit_path=None, audit_sha256=None, audit_schema=AUDIT_SCHEMA):
    index, index_pin = read_json_pin({"path": str(Path(index_path).resolve()), "sha256": index_sha256}, ROOT)
    require(index["schema"] == "td-shared-port-channel-preparation-v1", "unsupported task14 preparation schema")
    base = Path(index_pin["path"]).parent
    paths, sections, source_pins, terrain_manifest, height, valid = load_sources(index)
    records, pins = {}, {"index": index_pin, "inputs": source_pins}
    pins["preparation_code"] = {}
    for name, digest in index["code_sha256"].items():
        _, pins["preparation_code"][name] = read_pin({"path": str(ROOT / name), "sha256": digest}, ROOT)
    for name in PACKAGE_PARTS:
        records[name], pins[name] = read_json_pin(index[name], base)
    graph, selection, manifest, mesh, topology = (records[name] for name in PACKAGE_PARTS)
    require(graph["schema"] == "td-shared-port-land-graph-v1"
            and selection["schema"] == "td-shared-port-selection-v1"
            and manifest["schema"] == "td-shared-port-channel-v1"
            and mesh["schema"] == "td-shared-port-fragment-mesh-v1"
            and topology["schema"] == "td-shared-port-channel-topology-v1", "unsupported task14 artifact schema")
    require(manifest["inputs"] == index["inputs"] and selection["graph_identity_sha256"] == graph["identity_sha256"]
            and index["policy_identity_sha256"] == manifest["policy_identity_sha256"] == selection["policy_identity_sha256"], "manifest/source identity mismatch")
    original_nodes = unique(paths["nodes"], "node_id")
    original_arcs = unique(paths["arcs"], "arc_id")
    land_arcs = {key: value for key, value in original_arcs.items() if value["kind"] == "land_channel"}
    require(unique(graph["arcs"], "arc_id") == land_arcs and graph["parents"]["paths"] == paths["identity_sha256"]
            and graph["original_land_arc_count"] == len(land_arcs), "graph is not the fixed actual land source")
    for node in graph["nodes"]:
        require(node == original_nodes[node["node_id"]], "graph node differs from native source")
    require(len(selection["selected_node_ids"]) <= selection["max_nodes"] <= 2048
            and set(selection["selected_node_ids"]) <= set(original_nodes)
            and set(selection["selected_arc_ids"]) <= set(land_arcs), "invalid saved selection/budget")
    for record in (index, manifest, mesh, topology):
        for flag in FALSE_FLAGS:
            require(record.get(flag, False) is False, "unsupported task14 capability: " + flag)
    require(mesh["old06_mesh_included"] is False and manifest["replacement"]["original_06_in_fragment_mesh"] is False,
            "legacy mesh must not be part of the new fragment")
    require(mesh["vertices_xyz_m"] and mesh["triangles"] and len(mesh["face_origins"]) == len(mesh["triangles"]), "empty/invalid saved fragment")
    validate_mesh(mesh)
    require(len(mesh["triangles"]) <= 20000, "saved fragment face budget exceeded")
    nodes = unique(manifest["nodes"], "node_id")
    ports = unique(manifest["ports"], "arc_id")
    require(set(nodes) == set(selection["selected_node_ids"]) and set(ports) == set(selection["selected_arc_ids"]), "manifest/selection census mismatch")
    selected = {row["node_id"] for row in manifest["nodes"] if row["composition_status"] == "selected"}
    require(selected == set(manifest["selected_node_ids"]), "selected node census mismatch")
    pins["nodes"], pins["ports"] = {}, {}
    port_profiles, saved_supply = {}, {}
    parent_identities = {"paths": paths["identity_sha256"], "sections": sections["identity_sha256"],
                         "hierarchy": paths["hierarchy_identity_sha256"], "source": paths["source_identity_sha256"]}
    for row in manifest["ports"]:
        record, pin = read_json_pin(row["pin"], base)
        require("identity_sha256" in pin and record["arc_id"] == row["arc_id"] and record["schema"] == "td-shared-midpoint-port-v1"
                and record["status"] == row["status"] and record["inputs"] == index["inputs"]
                and record["policy_identity_sha256"] == manifest["policy_identity_sha256"]
                and all(record["parents"][key] == value for key, value in parent_identities.items()), "port pin/status/source mismatch")
        arc = land_arcs[record["arc_id"]]
        require(record["node_ids"] == arc["node_ids"] and record["source_arc_xyz_m"] == arc["xyz_m"]
                and record["upstream_parent_section"] == sections["node_sections"][record["upstream_section_index"]]
                and record["upstream_parent_section"]["node_id"] == arc["node_ids"][0], "port lacks actual source metrics/reference")
        pins["ports"][str(row["arc_id"])] = pin
        port_profiles[row["arc_id"]] = record["profile"]
        saved_supply[row["arc_id"]] = {"ordinary_mean_proxy_q_m3_s": record["representative_q_m3_s"],
                                        "upstream_section_index": record["upstream_section_index"]}
        del record
        check_memory()
    seams = unique(manifest["shared_midpoint_seams"], "arc_id")
    require(set(seams) == set(topology["joined_arc_ids"]) == set(manifest["selected_arc_ids"])
            and topology["joined_arc_count"] == len(seams), "saved actual seam/arc census mismatch")
    sides_by_node = {}
    for arc_id, seam in seams.items():
        require(arc_id in ports and ports[arc_id]["status"] == "candidate"
                and {seam["first_node_id"], seam["second_node_id"]} == set(land_arcs[arc_id]["node_ids"])
                and seam["first_node_id"] in selected and seam["second_node_id"] in selected
                and seam["midpoint_port_identity_sha256"] == pins["ports"][arc_id]["identity_sha256"]
                and seam["original_profile_xyz_m"] == port_profiles[arc_id]["profile_xyz_m"]
                and {piece["profile_segment_index"] for piece in seam["native_pieces"]} == {0, 1, 2}, "incomplete saved shared midpoint references")
        for piece in seam["native_pieces"]:
            require(piece["reverse_seam"] is True and piece["first_side"]["points_xyz_m"] == piece["second_side"]["points_xyz_m"][::-1], "saved seam does not reference reverse edges")
            for key, node_key in (("first_side", "first_node_id"), ("second_side", "second_node_id")):
                side = piece[key]
                require(side["node_id"] == seam[node_key], "seam side node mismatch")
                sides_by_node.setdefault(side["node_id"], []).append(side)
    open_profiles, degree_census, next_vertex, next_face = {}, {}, 0, 0
    for origin_record in mesh["face_origins"]:
        require(origin_record["node_id"] in selected, "face is not from a selected new node")
    for row in manifest["nodes"]:
        record, pin = read_json_pin(row["pin"], base)
        node_id = row["node_id"]
        require("identity_sha256" in pin and record["node_id"] == node_id and record["schema"] == "td-shared-port-node-piece-v1"
                and record["status"] == row["generation_status"] and record["inputs"] == index["inputs"]
                and record["policy_identity_sha256"] == manifest["policy_identity_sha256"]
                and all(record["parents"][key] == value for key, value in parent_identities.items()), "node pin/status/source mismatch")
        require(record["source_xyz_m"] == row["source_xyz_m"] == original_nodes[node_id]["xyz_m"]
                and record["parent_section"] == sections["node_sections"][record["node_section_index"]]
                and record["parent_section"]["node_id"] == node_id, "node is not derived from the saved source section")
        pins["nodes"][str(node_id)] = pin
        require(row["composition_status"] in ("selected", "refused"), "unknown node composition state")
        if row["composition_status"] == "refused":
            require(row["rejection_reasons"], "refused node lacks reasons")
        else:
            require(row["generation_status"] == "candidate" and not row["rejection_reasons"], "selected refused node")
            geometry = record["geometry"]
            validate_mesh(geometry)
            require(mesh["vertices_xyz_m"][next_vertex:next_vertex+len(geometry["vertices_xyz_m"])] == geometry["vertices_xyz_m"], "new node vertices altered or legacy mesh inserted")
            require(1 <= record["degree"] <= 4 and len(record["arms"]) == record["degree"], "invalid saved node degree")
            degree_census[str(record["degree"])] = degree_census.get(str(record["degree"]), 0)+1
            for number, triangle in enumerate(geometry["triangles"]):
                face_id = next_face+number
                role = geometry["triangle_roles"][number]
                require(mesh["triangles"][face_id] == [vertex+next_vertex for vertex in triangle]
                        and mesh["face_origins"][face_id] == {"node_id": node_id, "triangle_index": number, "role": role}, "new face differs from saved node geometry")
                require(role["region"] in ("half_arm", "node_ring")
                        and (role["region"] != "half_arm" or role["arc_id"] in row["arc_ids"]), "unknown saved face role")
            for arm in record["arms"]:
                arc_id = arm["arc_id"]
                require(arc_id in ports and arm["midpoint_port_identity_sha256"] == pins["ports"][arc_id]["identity_sha256"]
                        and arm["profile_xyz_m"] == port_profiles[arc_id]["profile_xyz_m"], "half-arm lacks the unique saved midpoint")
                ids = arm["midpoint_vertex_ids"]
                require(len(ids) == 4 and [geometry["vertices_xyz_m"][identifier] for identifier in ids] == arm["profile_xyz_m"], "saved four-point port does not reference geometry")
                open_profiles[(node_id, arc_id)] = arm["profile_xyz_m"]
            for side in sides_by_node.get(node_id, []):
                triangle_id, edge_id = side["triangle_index"], side["edge_index"]
                require(type(triangle_id) is int and 0 <= triangle_id < len(geometry["triangles"])
                        and type(edge_id) is int and 0 <= edge_id < 3, "invalid actual seam geometry reference")
                triangle = geometry["triangles"][triangle_id]
                require([geometry["vertices_xyz_m"][triangle[edge_id]], geometry["vertices_xyz_m"][triangle[(edge_id+1)%3]]] == side["points_xyz_m"], "seam edge differs from saved triangle")
            terminal = record["terminal_evidence"]
            if terminal:
                ids = geometry["terminal_vertex_ids"]
                profile = terminal["derived_terminal_profile"]["profile_xyz_m"]
                require(len(ids) == 4 and [geometry["vertices_xyz_m"][identifier] for identifier in ids] == profile, "terminal does not reference actual saved geometry")
                open_profiles[(node_id, None)] = {"node_id": node_id, "arc_id": None, "profile_xyz_m": profile,
                                                  "reason": terminal["classification"], "label": node_id+"\n"+terminal["classification"],
                                                  "terminal_evidence": terminal}
            next_vertex += len(geometry["vertices_xyz_m"])
            next_face += len(geometry["triangles"])
        del record
        check_memory()
    require(next_vertex == len(mesh["vertices_xyz_m"]) and next_face == len(mesh["triangles"]), "unreferenced/duplicate/legacy fragment geometry")
    require(topology["verified"] is False and topology["metrics_status"] == "candidate_unverified"
            and topology["no_node_id_only_connections"] is True, "unsupported topology capability")
    require(topology["source_identity_sha256"] == paths["source_identity_sha256"]
            and all(topology["source_terrain"][key] == paths[key] for key in ("origin_m_xz", "spacing_m", "grid_shape")), "topology/native frame mismatch")
    components = unique(topology["components"], "component_id")
    node_components = {}
    covered_arcs = set()
    for component in components.values():
        for node_id in component["node_ids"]:
            require(node_id in selected and node_id not in node_components, "invalid saved component node census")
            node_components[node_id] = component["component_id"]
        for arc_id in component["arc_ids"]:
            require(arc_id in seams and arc_id not in covered_arcs and set(land_arcs[arc_id]["node_ids"]) <= set(component["node_ids"]), "invalid saved component arc census")
            covered_arcs.add(arc_id)
    require(set(node_components) == selected and covered_arcs == set(seams) and len(components) == topology["component_count"], "incomplete saved components")
    longest = topology["longest_directed_path"]
    chain_ids = longest["arc_ids"]
    if chain_ids:
        chain_nodes = longest["node_ids"]
        require(len(chain_nodes) == len(chain_ids)+1 and len(set(chain_ids)) == len(chain_ids)
                and longest["source_xyz_m"] == [original_nodes[node_id]["xyz_m"] for node_id in chain_nodes]
                and all(arc_id in seams and land_arcs[arc_id]["node_ids"] == chain_nodes[number:number+2] for number, arc_id in enumerate(chain_ids)), "saved chain lacks actual source/seam references")
    else:
        require(not longest["node_ids"] or set(longest["node_ids"]) <= selected, "invalid isolated/cycle chain")
    binding = {"binding_status": "not_supplied", "scope": "no independent task14 audit inherited"}
    require(bool(audit_path) == bool(audit_sha256), "audit path/SHA required together")
    if audit_path:
        audit, pins["independent_audit"] = read_json_pin({"path": str(Path(audit_path).resolve()), "sha256": audit_sha256}, ROOT)
        binding = audit_binding(audit, audit_schema, index, manifest, pins)
    metadata = terrain_manifest["metadata"]
    selected_points = np.asarray(mesh["vertices_xyz_m"], float)
    plot_origin = selected_points[0, [0, 2]]
    open_ports = []
    for port in topology["open_ports"]:
        require(port["arc_id"] not in seams and port["profile_xyz_m"] == open_profiles[(port["node_id"], port["arc_id"])]
                and port["hydraulic_boundary_claimed"] is False, "open midpoint differs from saved half-arm")
        open_ports.append({**port, "label": port["node_id"]+"\nopen midpoint: other half-arm absent"})
    for port in topology["terminal_open_ports"]:
        require((port["node_id"], None) in open_profiles, "terminal evidence missing")
        require(port["profile_xyz_m"] == open_profiles[(port["node_id"], None)]["profile_xyz_m"]
                and port["classification"] == open_profiles[(port["node_id"], None)]["reason"]
                and port["hydraulic_boundary_claimed"] is False, "saved terminal topology/geometry mismatch")
        open_ports.append(open_profiles[(port["node_id"], None)])
    if longest["node_ids"]:
        end_node = longest["node_ids"][-1]
        open_ports.sort(key=lambda port: port["node_id"] == end_node)
    refused_arcs = [{**row, "xyz_m": land_arcs[row["arc_id"]]["xyz_m"]} for row in selection["boundary_arc_clipping"]]
    for arc_id in manifest["replacement"]["partial_or_refused_selected_arc_ids"]:
        require(arc_id in selection["selected_arc_ids"] and arc_id not in seams, "replacement refusal census mismatch")
        refused_arcs.append({"arc_id": arc_id, "xyz_m": land_arcs[arc_id]["xyz_m"], "reason": "partial_or_refused_selected_arc"})
    anchors = [{"node_id": row["node_id"], "xyz_m": row["source_xyz_m"], "rejection_reasons": row["rejection_reasons"],
                "semantics": "saved original lake/anchor safety exclusion; no constructed lake closure"}
               for row in selection["safety_clipping"] if "original_anchor_or_lake" in row["rejection_reasons"]]
    main_component = node_components[longest["node_ids"][0]] if longest["node_ids"] else None
    connected_branch_ids = set(components[main_component]["arc_ids"])-set(chain_ids) if main_component is not None else set()
    require(connected_branch_ids == set(topology["branch_arc_ids"]), "saved main-component branch census mismatch")
    route_roles = []
    for origin_record in mesh["face_origins"]:
        role = origin_record["role"]
        if role["region"] == "node_ring":
            route_roles.append("node_core")
        elif role["arc_id"] in chain_ids:
            route_roles.append("longest_saved_chain")
        elif role["arc_id"] in connected_branch_ids:
            route_roles.append("saved_branch")
        elif role["arc_id"] in seams:
            route_roles.append("other_component")
        else:
            route_roles.append("open_half_arm")
    chain_label = "cycle/empty: no saved chain" if longest["plan_length_m"] is None else f"{len(chain_ids)} arcs / {longest['plan_length_m']:.1f} m"
    summary = {"caption": f"{len(selected)} selected new nodes; {len(seams)} joined midpoint arcs; {len(components)} saved evidence components\n"
               f"Longest saved chain {chain_label}; {len(connected_branch_ids)} side-branch arcs in its component; {len(open_ports)} open profiles",
               "selected_node_degree_census": degree_census, "selected_nodes": len(selected), "joined_arcs": len(seams),
               "components": len(components), "longest_chain_arc_ids": chain_ids, "connected_branch_arc_ids": sorted(connected_branch_ids),
               "open_midpoint_count": len(topology["open_ports"]), "open_terminal_count": len(topology["terminal_open_ports"])}
    return {"schema": SCHEMA, "pins": pins, "manifest_identity_sha256": manifest["identity_sha256"],
            "coordinates": {"axes": "x east, y elevation, z south", "length_unit": "model m, not survey or Minecraft blocks",
                            "array_order": "[z,x]", "origin_m_xz": metadata["origin_m_xz"], "spacing_m": metadata["spacing_m"]},
            "plot_origin_m_xz": plot_origin.tolist(),
            "native_terrain": {"height_m": height.tolist(), "valid_mask": valid.tolist(), "sampling": "unchanged native samples"},
            "layers": {"saved_fragment_mesh": mesh, "face_route_roles": route_roles, "open_ports": open_ports,
                       "face_component_ids": [node_components[origin_record["node_id"]] for origin_record in mesh["face_origins"]],
                       "refused_arcs": refused_arcs, "unclosed_lake_anchors": anchors, "manifest": manifest},
            "topology": topology, "graph": graph, "selection": selection,
            "supply": {"semantics": "saved ordinary mean proxy prior; not measured or instantaneous discharge", "arc_metrics": saved_supply},
            "independent_audit_reference": binding, "summary": summary,
            "limitations": ["Only newly saved shared-midpoint fragment is rendered; old 06 is context outside this mesh and old 07 is excluded.",
                            "Longest chain and branches are saved topology evidence, not a permanent trunk or hydraulic proof; the exporter does not recompute connectivity or certify source-depth functions.",
                            "Branch color covers joined arcs only in the saved longest-chain component; other components and incomplete half-arms are separate.",
                            "Open ports and lake anchors have no closure. Refused geometry is not water or bed.",
                            "No full-network, fine, material, solver or hydraulic certification; Q remains an ordinary prior.",
                            "Renderer H0 is a bed alias, not native terrain; water is null. Navigation/layer integration remains pending Claude."],
            "resource": {"peak_rss_bytes": check_memory(), "max_rss_bytes": 1024**3, "max_artifact_bytes": MAX_BYTES}, **FALSE_FLAGS}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--audit-sha256")
    parser.add_argument("--audit-schema", default=AUDIT_SCHEMA)
    parser.add_argument("--oblique-3d", action="store_true", help="render native crop + saved bed geometry in a scientific oblique view")
    parser.add_argument("--vertical-exaggeration", type=float, default=1., help="oblique plot only; default 1:1, explicit [0.1,10] multiplier")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(args.output.resolve().is_relative_to(ROOT.resolve()) and not args.output.exists(), "output must be a NEW workspace directory")
    require(np.isfinite(args.vertical_exaggeration) and 0.1 <= args.vertical_exaggeration <= 10., "vertical exaggeration must be in [0.1,10]")
    require(args.oblique_3d or args.vertical_exaggeration == 1., "vertical exaggeration requires --oblique-3d")
    review = load_review(args.index, args.index_sha256, args.audit, args.audit_sha256, args.audit_schema)
    overview = render_overview(review)
    artifacts = {"overview.png": overview}
    if args.oblique_3d:
        artifacts["oblique-3d.png"] = render_oblique(review, args.vertical_exaggeration)
        review["oblique_display"] = {"vertical_exaggeration": args.vertical_exaggeration,
                                     "source_sampling": "cropped original native grid samples; no finer source generated"}
    review["resource"]["peak_rss_bytes"] = check_memory()
    artifacts["review.json"] = encoded(review)
    artifacts["caseartifact.json"] = encoded(caseartifact(review))
    print(publish_directory(args.output, artifacts))


if __name__ == "__main__":
    main()
