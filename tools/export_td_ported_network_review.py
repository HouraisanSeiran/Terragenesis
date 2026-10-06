"""Pure IO review of saved ported-network composition; no generation or audit run.

API: load_review(index_path, index_sha256, audit_path=None, audit_sha256=None,
audit_schema=AUDIT_SCHEMA), caseartifact(review), render_overview(review).
CLI: D:/anaconda/python.exe -B tools/export_td_ported_network_review.py
--index <composition/index.json> --index-sha256 <SHA>
--audit <independent-audit.json> --audit-sha256 <SHA> --audit-schema <schema>
--output <NEW directory>.
Artifacts: review.json, caseartifact.json, overview.png (each <=64MiB).
Saved merged triangles only: retained 06 prefix + composition-selected patches.
No 07 overlay, welding, fabricated faces, solver, fine generation or audit rerun.
Topology is a saved full-profile evidence graph, not hydraulic certification.
Audit v2 binds index/manifest/mesh/census/topology SHA, manifest identity, all
source inputs, accepted_hub_ids and all census junction path/SHA/identities.
"""

import argparse
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_td_watershed_inspection import (
    DEFAULT_INDEX, DEFAULT_SHA256, MAX_BYTES, ROOT, encoded, publish_directory,
    read_json_pin, read_pin, require, unique)
from export_td_ported_junction_review import (
    EXTRA_SOURCE_SHAS, FALSE_FLAGS, signatures, validate_mesh)
from audit_td_watershed_connectivity import check_memory


SCHEMA = "td-ported-network-review-v1"
AUDIT_SCHEMA = "td-ported-network-independent-audit-v2"
EXTRA_SOURCE_PATHS = {
    "source_bank_parent_index": "source-conforming-banks-entry-20261006-03/index.json",
    "source_bank_parent_audit": "source-conforming-banks-entry-20261006-03/independent-audit.json",
    "wet_protection_manifest": "source-conforming-banks-entry-20261006-03/manifest.json",
}


def audit_binding(audit, schema, index, manifest, pins):
    failures = []
    if audit.get("schema") != schema:
        failures.append("audit_schema_mismatch")
    for name in ("index", "manifest", "composed_mesh", "census", "topology"):
        if audit.get(name + "_sha256") != pins[name]["sha256"]:
            failures.append("audit_pin_mismatch_or_missing:" + name)
    if audit.get("manifest_identity_sha256") != manifest["identity_sha256"]:
        failures.append("audit_manifest_identity_mismatch_or_missing")
    if signatures(audit.get("inputs", {})) != signatures(index["inputs"]):
        failures.append("audit_inputs_mismatch_or_missing")
    if audit.get("status") not in ("passed", "failed"):
        failures.append("audit_status_missing_or_unknown")
    if audit.get("status") == "passed" and audit.get("errors"):
        failures.append("audit_passed_with_errors")
    selected = sorted(row["hub_node_id"] for row in manifest["hubs"] if row["composition_status"] == "selected")
    if sorted(audit.get("accepted_hub_ids", [])) != selected:
        failures.append("audit_selected_hub_census_mismatch_or_missing")
    junctions = audit.get("junctions", {})
    if not isinstance(junctions, dict) or set(junctions) != set(pins["junctions"]):
        failures.append("audit_junction_census_mismatch_or_missing")
    else:
        for hub_id, pin in pins["junctions"].items():
            actual = junctions[hub_id]
            if (not isinstance(actual, dict) or not actual.get("path")
                    or Path(actual["path"]).resolve() != Path(pin["path"]).resolve()
                    or actual.get("sha256") != pin["sha256"]
                    or actual.get("identity_sha256") != pin["identity_sha256"]):
                failures.append("audit_junction_binding_mismatch:" + hub_id)
    result = {"binding_status": "not_matched" if failures else "matched",
              "binding_failures": failures,
              "scope": "saved independent composition evidence audit reference only; not rerun"}
    if not failures:
        result["referenced_status"] = audit["status"]
    return result


def validate_saved_composition(mesh, manifest, sections, paths, base, inputs):
    validate_mesh(mesh)
    old = sections["mesh"]
    old_vertices, old_faces = len(old["vertices_xyz_m"]), len(old["triangles"])
    require(mesh["vertices_xyz_m"][:old_vertices] == old["vertices_xyz_m"]
            and mesh["triangles"][:old_faces] == old["triangles"], "06 prefix altered")
    origins = mesh["face_origins"]
    require(len(origins) == len(mesh["triangles"]), "face provenance length mismatch")
    for number in range(old_faces):
        require(origins[number] == {"kind": "legacy06", "triangle_index": number,
                                   "arc_id": old["triangle_arc_ids"][number]}, "06 provenance mismatch")
    hubs = unique(manifest["hubs"], "hub_node_id")
    require(len(hubs) <= 256, "hub census budget exceeded")
    arcs = unique(paths["arcs"], "arc_id")
    owners = {arc_id: {"kind": "legacy06"} for arc_id in old["triangle_arc_ids"]}
    selected_faces = {}
    for number, origin in enumerate(origins[old_faces:], start=old_faces):
        require(origin["kind"] == "junction" and origin["hub_node_id"] in hubs
                and hubs[origin["hub_node_id"]]["composition_status"] == "selected", "non-selected or unknown mesh origin")
        selected_faces.setdefault(origin["hub_node_id"], []).append(number)
    junction_pins = {}
    next_vertex = old_vertices
    next_face = old_faces
    for hub_id, row in hubs.items():
        require(row["composition_status"] in ("selected", "refused")
                and row["generation_status"] in ("candidate", "refused"), "unknown hub state")
        junction_record, junction_pins[hub_id] = read_json_pin(row["junction"], base)
        require("identity_sha256" in junction_pins[hub_id], "junction pin lacks record identity")
        require(junction_record["schema"] == "td-ported-junction-v1"
                and junction_record["hub_node_id"] == hub_id
                and junction_record["status"] == row["generation_status"]
                and signatures(junction_record["inputs"]) == signatures(inputs), "hub/source binding mismatch")
        if row["composition_status"] == "refused":
            require(row["rejection_reasons"] and not row["added_arc_ids"] and hub_id not in selected_faces,
                    "refused hub contributes geometry")
        else:
            require(row["generation_status"] == "candidate" and not row["rejection_reasons"], "selected refused candidate")
            actual = junction_record["geometry"]
            validate_mesh(actual)
            ids = selected_faces.get(hub_id, [])
            require(ids == list(range(next_face, next_face + len(actual["triangles"]))), "non-contiguous or missing saved hub faces")
            require(mesh["vertices_xyz_m"][next_vertex:next_vertex + len(actual["vertices_xyz_m"])] == actual["vertices_xyz_m"],
                    "hub vertices differ from saved geometry")
            for local, face_id in enumerate(ids):
                require(mesh["triangles"][face_id] == [vertex + next_vertex for vertex in actual["triangles"][local]]
                        and origins[face_id] == {"kind": "junction", "hub_node_id": hub_id,
                                               "triangle_index": local, "role": actual["triangle_roles"][local]},
                        "hub face differs from saved geometry")
            require(sorted(row["added_arc_ids"]) == sorted(junction_record["requested_replacement_arc_ids"]), "added arc census mismatch")
            for arc_id in row["added_arc_ids"]:
                require(arc_id in arcs and arcs[arc_id]["kind"] == "land_channel" and arc_id not in owners, "duplicate or support arc in merged layer")
                owners[arc_id] = {"kind": "junction", "hub_node_id": hub_id}
            next_vertex += len(actual["vertices_xyz_m"])
            next_face += len(actual["triangles"])
        del junction_record
        check_memory()
    require(next_vertex == len(mesh["vertices_xyz_m"]) and next_face == len(mesh["triangles"])
            and owners == manifest["arc_owners"], "unused geometry or arc ownership mismatch")
    return junction_pins


def load_review(index_path, index_sha256, audit_path=None, audit_sha256=None, audit_schema=AUDIT_SCHEMA):
    check_memory()
    source_index, source_index_pin = read_json_pin({"path": str(DEFAULT_INDEX), "sha256": DEFAULT_SHA256}, ROOT)
    paths, paths_pin = read_json_pin(source_index["paths"], DEFAULT_INDEX.parent)
    sections, sections_pin = read_json_pin(source_index["sections"], DEFAULT_INDEX.parent)
    _, hierarchy_pin = read_pin(source_index["inputs"]["hierarchy"], DEFAULT_INDEX.parent)
    source_pins = {"06_index": source_index_pin, "06_paths": paths_pin, "06_sections": sections_pin, "hierarchy": hierarchy_pin}
    index, index_pin = read_json_pin({"path": str(Path(index_path).resolve()), "sha256": index_sha256}, ROOT)
    require(index["schema"] == "td-ported-network-composition-preparation-v1", "unsupported preparation schema")
    base = Path(index_pin["path"]).parent
    require(signatures(source_pins).issubset(signatures(index["inputs"])), "fixed source path/SHA mismatch")
    for name, expected in EXTRA_SOURCE_SHAS.items():
        expected_path = ROOT / "verification/natural-river-network" / EXTRA_SOURCE_PATHS[name]
        require(index["inputs"][name]["sha256"] == expected
                and Path(index["inputs"][name]["path"]).resolve() == expected_path.resolve(), "fixed source-bank/wet pin mismatch: " + name)
    for name, pin in index["inputs"].items():
        _, source_pins[name] = read_pin(pin, ROOT)
    code_pins = {}
    for name, digest in index["code_sha256"].items():
        _, code_pins[name] = read_pin({"path": str(ROOT / name), "sha256": digest}, ROOT)
    records, pins = {}, {"index": index_pin, "inputs": source_pins}
    pins["preparation_code"] = code_pins
    for name in ("manifest", "composed_mesh", "topology", "census"):
        records[name], pins[name] = read_json_pin(index[name], base)
    manifest, mesh, topology, census = (records[name] for name in ("manifest", "composed_mesh", "topology", "census"))
    require(manifest["schema"] == "td-ported-network-composition-v1"
            and topology["schema"] == "td-ported-network-topology-v1", "unsupported composition schema")
    require(signatures(manifest["inputs"]) == signatures(index["inputs"])
            and signatures(census["inputs"]) == signatures(index["inputs"])
            and census["schema"] == "td-ported-network-census-v1"
            and census["all_actual_three_arm_hubs"] is True
            and census["hub_count"] == len(census["hubs"]) == len(manifest["hubs"])
            and census["hub_count"] == index["hub_count"], "census/source binding mismatch")
    census_hubs = unique(census["hubs"], "hub_node_id")
    for row in manifest["hubs"]:
        require(row["hub_node_id"] in census_hubs
                and all(row[key] == value for key, value in census_hubs[row["hub_node_id"]].items()), "manifest/census hub mismatch")
    require(manifest["parents"]["paths"] == paths["identity_sha256"]
            and manifest["parents"]["sections"] == sections["identity_sha256"]
            and manifest["parents"]["hierarchy"] == hierarchy_pin["identity_sha256"]
            and index["policy_identity_sha256"] == manifest["policy_identity_sha256"], "composition parent/policy mismatch")
    require(manifest["original_06_kept_unchanged"] is True and mesh["original_06_prefix_unchanged"] is True
            and manifest["metrics_status"] == topology["metrics_status"] == "candidate_unverified"
            and topology["verified"] is False, "unsupported composition capabilities")
    for flag in FALSE_FLAGS:
        require(manifest.get(flag, False) is False, "unsupported capability: " + flag)
    pins["junctions"] = validate_saved_composition(mesh, manifest, sections, paths, base, index["inputs"])
    arcs = unique(paths["arcs"], "arc_id")
    nodes = unique(paths["nodes"], "node_id")
    owners = manifest["arc_owners"]
    component_by_arc = {}
    component_ids = set()
    for component in topology["components"]:
        require(component["arc_count"] == len(component["arc_ids"]) > 0
                and component["component_id"] not in component_ids, "component arc/ID census mismatch")
        component_ids.add(component["component_id"])
        for arc_id in component["arc_ids"]:
            require(arc_id in owners and arc_id not in component_by_arc, "component duplicates/unknown arc")
            component_by_arc[arc_id] = component["component_id"]
    require(set(component_by_arc) == set(owners) and topology["component_count"] == len(topology["components"]), "incomplete saved component census")
    for port in topology["open_ports"]:
        require(port["arc_id"] in owners and port["outer_node_id"] in nodes
                and len(port["original_profile_xyz_m"]) == 4, "invalid saved open port")
    require(topology["open_port_count"] == len(topology["open_ports"]), "open port census mismatch")
    longest = topology["longest_directed_path"]
    if longest:
        chain = longest["arc_ids"]
        require(len(chain) == longest["arc_count"] and len(set(chain)) == len(chain)
                and all(arc_id in owners for arc_id in chain)
                and longest["source_arc_xyz_m"] == [arcs[arc_id]["xyz_m"] for arc_id in chain]
                and all(second in topology["directed_transitions"][first] for first, second in zip(chain, chain[1:])), "invalid saved directed chain references")
    binding = {"binding_status": "not_supplied", "scope": "no independent audit status inherited"}
    require(bool(audit_path) == bool(audit_sha256), "audit path/SHA required together")
    if audit_path:
        audit, pins["independent_audit"] = read_json_pin({"path": str(Path(audit_path).resolve()), "sha256": audit_sha256}, ROOT)
        binding = audit_binding(audit, audit_schema, index, manifest, pins)
    with np.load(hierarchy_pin["path"], allow_pickle=False) as bundle:
        terrain_manifest = json.loads(bytes(bundle["manifest"]))
        height = bundle["height_m"].copy()
        valid = bundle["valid_mask"].copy()
    require(terrain_manifest["identity_sha256"] == hierarchy_pin["identity_sha256"]
            and height.ndim == 2 and height.size <= 250000 and np.isfinite(height).all(), "native terrain mismatch")
    hubs = [{**row, "xyz_m": nodes[row["hub_node_id"]]["xyz_m"]} for row in manifest["hubs"]]
    rejected = [{**row, "xyz_m": arcs[row["arc_id"]]["xyz_m"]} for row in sections["reach_diagnostics"]
                if row["status"] == "rejected" and row["arc_id"] not in owners]
    hub_component_ids = {}
    for row in hubs:
        if row["composition_status"] == "selected":
            memberships = {component_by_arc[arc_id] for arc_id in row["added_arc_ids"]}
            require(len(memberships) == 1, "selected hub split across saved components")
            hub_component_ids[row["hub_node_id"]] = memberships.pop()
    face_components = [component_by_arc[origin["arc_id"]] if origin["kind"] == "legacy06"
                       else hub_component_ids[origin["hub_node_id"]]
                       for origin in mesh["face_origins"]]
    return {"schema": SCHEMA, "pins": pins, "manifest_identity_sha256": manifest["identity_sha256"],
            "coordinates": {"axes": "x east, y elevation, z south", "length_unit": "model m, not survey or Minecraft blocks",
                            "array_order": "[z,x]", **{key: terrain_manifest["metadata"][key] for key in ("origin_m_xz", "spacing_m")}},
            "native_terrain": {"height_m": height.tolist(), "valid_mask": valid.tolist(), "sampling": "unchanged native samples"},
            "layers": {"merged_only_mesh": mesh, "face_component_ids": face_components, "open_ports": topology["open_ports"],
                       "hubs": hubs, "refused_uncomposed_06_arcs": rejected},
            "topology": topology, "census": census, "connections": manifest["connections"],
            "independent_audit_reference": binding,
            "summary": {"hub_states": dict(Counter(row["composition_status"] for row in hubs)),
                        "saved_triangles": len(mesh["triangles"]), "components": topology["component_count"],
                        "open_ports": topology["open_port_count"]},
            "limitations": ["Merged saved display triangles only; no 07 overlay or exporter-generated connections.",
                            "Complete-profile evidence components and longest source-arc chain are saved candidate metrics, not hydraulic proof.",
                            "Open ports are not river closure. Refused arcs/hubs are not water or constructed beds.",
                            "Q is an ordinary mean proxy prior, not measured discharge; no permanent trunk selected.",
                            "Mesh approximates saved source-depth functions, not fine DEM. Renderer H0 is bed alias; water=null.",
                            "Formal frontend navigation/layer integration pending; no UI changes."],
            "resource": {"peak_rss_bytes": check_memory(), "max_rss_bytes": 1024**3, "max_artifact_bytes": MAX_BYTES}, **FALSE_FLAGS}


def caseartifact(review):
    mesh = review["layers"]["merged_only_mesh"]
    heights = [point[1] for point in mesh["vertices_xyz_m"]]
    return {"schema": "td-ported-network-mesh-case-v1", "kind": "mesh", "caseId": "ported-network-" + review["manifest_identity_sha256"][:12],
            "label": "Saved merged bed mesh; open ports remain; NOT fine or hydraulic",
            "mesh": {"vertices": mesh["vertices_xyz_m"], "triangles": mesh["triangles"], "bed": heights, "h0": heights,
                     "water": None, "wet": [], "wetCells": [], "cells": [], "hydrologicOwner": []},
            "face_origins": mesh["face_origins"], "face_component_ids": review["layers"]["face_component_ids"],
            "open_ports": review["layers"]["open_ports"], "pins": review["pins"],
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

    layers = review["layers"]
    mesh = layers["merged_only_mesh"]
    points = np.asarray(mesh["vertices_xyz_m"])
    polygons = points[:, [0, 2]][np.asarray(mesh["triangles"], dtype=int)]
    height = np.asarray(review["native_terrain"]["height_m"])
    valid = np.asarray(review["native_terrain"]["valid_mask"])
    coords = review["coordinates"]
    origin, spacing = coords["origin_m_xz"], coords["spacing_m"]
    extent = [origin[0]-spacing/2, origin[0]+(height.shape[1]-.5)*spacing,
              origin[1]+(height.shape[0]-.5)*spacing, origin[1]-spacing/2]
    shade = LightSource(315, 45).hillshade(height, dx=spacing, dy=spacing)
    shade[~valid] = np.nan
    topology = review["topology"]
    largest = max(topology["components"], key=lambda record: record["total_plan_length_m"])
    bounds = np.asarray(largest["bounds_xyz_m"])[:, [0, 2]]
    selected = [row for row in layers["hubs"] if row["composition_status"] == "selected"]
    focal = max(selected, key=lambda row: row.get("ordinary_q_m3_s", 0.)) if selected else None
    if focal:
        ids = [number for number, origin_record in enumerate(mesh["face_origins"])
               if origin_record.get("hub_node_id") == focal["hub_node_id"]]
        local = polygons[ids].reshape(-1, 2)
        detail = np.asarray([local.min(axis=0), local.max(axis=0)])
    else:
        detail = bounds
    colors = ["#64765b" if origin_record["kind"] == "legacy06" else "#b69942" for origin_record in mesh["face_origins"]]
    component_colors = [plt.get_cmap("tab20")(number % 20) for number in layers["face_component_ids"]]
    figure, axes = plt.subplots(1, 3, figsize=(20, 8))
    figure.subplots_adjust(left=.055, right=.985, top=.82, bottom=.2, wspace=.26)
    for number, axis in enumerate(axes):
        axis.imshow(shade, cmap="gray", extent=extent, interpolation="nearest", vmin=-.15, vmax=1.15)
        axis.add_collection(PolyCollection(polygons, facecolors=component_colors if number == 1 else colors,
                                          edgecolors="none", zorder=3))
        open_profiles = [np.asarray(port["original_profile_xyz_m"])[:, [0, 2]] for port in layers["open_ports"]]
        axis.add_collection(LineCollection(open_profiles, colors="#b65031", linewidths=.8 if number == 0 else 1.5,
                                           linestyles="--", zorder=5))
        refused_lines = [np.asarray(row["xyz_m"])[:, [0, 2]] for row in layers["refused_uncomposed_06_arcs"]]
        axis.add_collection(LineCollection(refused_lines, colors="#8b536b", linewidths=.35 if number == 0 else .65,
                                           linestyles=":", alpha=.55, zorder=2))
        refused_hubs = [row for row in layers["hubs"] if row["composition_status"] == "refused"]
        if refused_hubs:
            locations = np.asarray([row["xyz_m"] for row in refused_hubs])
            axis.scatter(locations[:, 0], locations[:, 2], c="#8b536b", marker="x", s=9 if number == 0 else 20, zorder=4)
        if number == 0:
            axis.set_xlim(extent[:2])
            axis.set_ylim(extent[2:])
            axis.add_patch(Rectangle(bounds[0]-45, *(bounds[1]-bounds[0]+90), fill=False, edgecolor="#303b2b", linewidth=1.2, zorder=6))
        else:
            limits = bounds if number == 1 else detail
            pad = 60. if number == 1 else 35.
            axis.set_xlim(limits[0, 0]-pad, limits[1, 0]+pad)
            axis.set_ylim(limits[1, 1]+pad, limits[0, 1]-pad)
        axis.set_aspect("equal")
        axis.ticklabel_format(style="plain", useOffset=False)
        axis.set_xlabel("Model east X (m)")
        axis.set_ylabel("Model south Z (m)")
        axis.set_title(["Native full-domain terrain / merged-only beds", "Largest saved profile-connected component", "Highest-Q selected hub / open boundaries" if focal else "No selected patches / saved strips only"][number], fontsize=10)
    if focal:
        axes[2].text(.02, .02, focal["hub_node_id"] + "\nQ ordinary mean proxy: " + format(focal.get("ordinary_q_m3_s", 0.), ".4g") + " m3/s",
                     transform=axes[2].transAxes, fontsize=9, bbox={"facecolor": "white", "alpha": .85, "edgecolor": "none"})
    binding = review["independent_audit_reference"]
    audit_label = binding.get("referenced_status", binding["binding_status"])
    longest = topology["longest_directed_path"]
    longest_label = (str(longest["arc_count"]) + " arcs / " + format(longest["plan_length_m"], ".1f") + " m") if longest else "unavailable (saved graph cycle/empty)"
    figure.suptitle("Saved ported-network composition | audit reference: " + audit_label, fontsize=15, y=.96)
    figure.text(.5, .875, str(topology["component_count"]) + " evidence components; " + str(topology["open_port_count"]) + " open ports; longest directed source-arc chain: " + longest_label,
                ha="center", fontsize=10)
    figure.legend(handles=[Patch(facecolor="#64765b", label="Retained saved 06 bed triangles"), Patch(facecolor="#b69942", label="Selected saved arm/hub triangles"),
                           Line2D([], [], color="#b65031", linestyle="--", label="Open four-point port; no closure"),
                           Line2D([], [], color="#8b536b", linestyle=":", marker="x", label="Refused / uncomposed; NOT water")],
                  loc="lower center", bbox_to_anchor=(.5, .065), ncol=2, fontsize=10, frameon=False)
    figure.text(.5, .025, "Component colors repeat; IDs in review. No 07 overlay, permanent trunk, fine DEM or hydraulic certification. Q is a prior, not measurement.", ha="center", fontsize=9)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=160)
    plt.close(figure)
    payload = output.getvalue()
    require(len(payload) <= MAX_BYTES, "overview exceeds 64MiB")
    check_memory()
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--audit-sha256")
    parser.add_argument("--audit-schema", default=AUDIT_SCHEMA)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = load_review(args.index, args.index_sha256, args.audit, args.audit_sha256, args.audit_schema)
    overview = render_overview(review)
    review["resource"]["peak_rss_bytes"] = check_memory()
    print(publish_directory(args.output, {"review.json": encoded(review), "caseartifact.json": encoded(caseartifact(review)), "overview.png": overview}))


if __name__ == "__main__":
    main()
