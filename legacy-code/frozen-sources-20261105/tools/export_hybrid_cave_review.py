"""Pure saved-geometry scientific review; no Boolean, generator or solver calls.

CLI: --geometry --geometry-sha256 --output NEW_DIRECTORY
Optional: --audit --audit-sha256 --audit-schema; --vertical-exaggeration (default 1).
Outputs review.json, caseartifact.json, overview.png, profile.png, oblique-3d.png.
All rendered triangles are saved references, not a synthetic water surface.
"""

import argparse
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, checked_path, check_memory, read, read_audit, require)
from tools.export_td_watershed_inspection import encoded, publish_directory

SCHEMA = "td-hybrid-cave-review-v1"
AUDIT_SCHEMA = "td-hybrid-cave-geometry-independent-audit-v1"
MESH_NAMES = ("rock_before", "cutter", "rock_after", "removed")


def load_review(geometry_path, geometry_sha256, audit_path=None, audit_sha256=None,
                audit_schema=AUDIT_SCHEMA):
    pin = {"path": str(Path(geometry_path).resolve()), "sha256": geometry_sha256}
    geometry = read(pin)
    require(geometry["schema"] == "td-hybrid-river-geometry-v1", "unexpected saved geometry schema")
    graph = read(geometry["inputs"]["graph"])
    require(graph["schema"] == "td-hybrid-river-graph-v1"
            and graph["identity_sha256"] == geometry["graph_identity_sha256"], "geometry graph identity differs")
    for source_pin in geometry["inputs"].values():
        checked_path(source_pin)
    require(all(geometry["inputs"].get(key) == value for key, value in graph["inputs"].items()), "geometry omitted/altered typed graph parent")
    meshes = {}
    for name in MESH_NAMES:
        mesh = read(geometry["mesh_pins"][name])
        require(mesh["schema"] == "td-hybrid-local-solid-mesh-v1", "unexpected local solid schema")
        points = np.asarray(mesh["vertices_local_xyz_m"], float)
        faces = np.asarray(mesh["triangles"])
        origin = np.asarray(mesh["local_origin_xyz_m"], float)
        require(points.ndim == 2 and points.shape[1] == 3 and len(points) <= 100000
                and origin.shape == (3,) and np.isfinite(points).all() and np.isfinite(origin).all()
                and faces.ndim == 2 and faces.shape[1] == 3 and 0 < len(faces) <= 200000
                and np.issubdtype(faces.dtype, np.integer) and faces.min() >= 0 and faces.max() < len(points), "invalid saved mesh references")
        meshes[name] = mesh
    vdm = read(geometry["vdm_pin"])
    require(vdm["schema"] == "td-hybrid-multichart-vdm-v1", "unexpected saved VDM schema")
    attachments = read(geometry["surface_attachments_pin"])
    native_pin = graph["inputs"]["original_hierarchy"]
    with np.load(checked_path(native_pin), allow_pickle=False) as archive:
        native_manifest = json.loads(bytes(archive["manifest"]))
        height, valid = archive["height_m"].copy(), archive["valid_mask"].copy()
    require(height.ndim == 2 and height.size <= 250000 and valid.shape == height.shape
            and np.isfinite(height).all(), "invalid bounded native terrain")
    binding = {"binding_status": "not_supplied", "scope": "reference to independent saved evidence only; exporter does not execute audit"}
    audit_pin = None
    if audit_path is not None or audit_sha256 is not None:
        require(audit_path is not None and audit_sha256 is not None, "audit path and SHA required together")
        audit_pin = {"path": str(Path(audit_path).resolve()), "sha256": audit_sha256}
        audit = read_audit(audit_pin)
        failures = []
        if audit.get("schema") != audit_schema:
            failures.append("schema")
        if audit.get("geometry_sha256") != geometry_sha256 or audit.get("graph_identity_sha256") != graph["identity_sha256"]:
            failures.append("geometry_graph_binding")
        if audit.get("inputs") != geometry["inputs"] or audit.get("mesh_pins") != geometry["mesh_pins"] or audit.get("vdm_pin") != geometry["vdm_pin"]:
            failures.append("source_mesh_vdm_binding")
        if audit.get("status") not in ("passed", "failed") or not isinstance(audit.get("errors"), list):
            failures.append("status_errors")
        if audit.get("status") == "passed" and (audit.get("errors") or audit.get("actual_hydraulic_sections_verified") is not True or audit.get("actual_portal_connections_verified") is not True):
            failures.append("passed_evidence")
        binding.update(binding_status="not_matched" if failures else "matched", binding_failures=failures)
        if not failures:
            binding.update(referenced_status=audit["status"], errors=audit["errors"])
    portals = {node["kind"]: node for node in graph["nodes"] if node["kind"] in ("sink", "spring")}
    require(set(portals) == {"sink", "spring"}, "missing actual typed portals")
    origin = meshes["rock_after"]["local_origin_xyz_m"]
    review = {"schema": SCHEMA, "geometry_identity_sha256": geometry["identity_sha256"],
        "graph_identity_sha256": graph["identity_sha256"], "pins": {"geometry": pin, "graph": geometry["inputs"]["graph"],
            "inputs": geometry["inputs"], "meshes": geometry["mesh_pins"], "vdm": geometry["vdm_pin"], "audit": audit_pin,
            "source_sampling": geometry["source_sampling_pin"], "surface_attachments": geometry["surface_attachments_pin"]},
        "coordinates": {"convention": "XYZ metres; Y elevation; XZ horizontal", "plot_origin_xyz_m": origin,
            "native_origin_m_xz": native_manifest["metadata"]["origin_m_xz"], "native_spacing_m": native_manifest["metadata"]["spacing_m"]},
        "meshes": meshes, "stations": vdm["stations"], "portals": portals,
        "surface_attachments": attachments["attachments"],
        "actual_closed_core_station_indices": geometry["actual_closed_core_station_indices"],
        "hydraulic_cells": geometry["hydraulic_cells"], "air_path_xyz_m": geometry["air_path_xyz_m"],
        "independent_audit_reference": binding,
        "native_terrain": {"height_m": height.tolist(), "valid_mask": valid.tolist()},
        "limitations": ["Engineered local rock-minus-cave sample, not surveyed geology or full river.",
            "Native terrain shown at original samples; local solid top is an explicitly sampled triangulation.",
            "Remaining-rock transparency is display only, not evidence of a physical opening.",
            "Removed solid and VDM outlines are geometry, not water.",
            "Hydraulic sections alone do not certify hydraulic flow; no hydraulic state attached.",
            "Frontend navigation pending; mesh artifact supplied without UI changes."],
        "hydraulic_solved": False, "three_dimensional_flow_solved": False, "full_network_verified": False,
        "natural_outlet_certified": False}
    check_memory()
    return review


def caseartifact(review):
    saved = review["meshes"]["rock_after"]
    vertices = (np.asarray(saved["vertices_local_xyz_m"])+np.asarray(saved["local_origin_xyz_m"])).tolist()
    heights = [point[1] for point in vertices]
    return {"schema": "td-hybrid-cave-mesh-case-v1", "kind": "mesh",
        "caseId": "hybrid-cave-"+review["geometry_identity_sha256"][:12],
        "label": "Saved actual remaining rock solid; engineered cave; no water",
        "mesh": {"vertices": vertices, "triangles": saved["triangles"], "bed": heights, "h0": heights,
            "water": None, "wet": [], "wetCells": [], "cells": [], "hydrologicOwner": [], "cellOwner": []},
        "geometry_layers": {name: review["meshes"][name] for name in MESH_NAMES},
        "stations": review["stations"], "portals": review["portals"], "pins": review["pins"],
        "surface_attachments": review["surface_attachments"],
        "actual_closed_core_station_indices": review["actual_closed_core_station_indices"],
        "coordinates": review["coordinates"], "independent_audit_reference": review["independent_audit_reference"],
        "limitations": review["limitations"], "hydraulic_solved": False,
        "three_dimensional_flow_solved": False, "full_network_verified": False, "natural_outlet_certified": False}


def render_figures(review, vertical_exaggeration=1.):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import LightSource
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    require(np.isfinite(vertical_exaggeration) and 0 < vertical_exaggeration <= 10, "explicit display vertical multiplier must be in (0,10]")
    origin = np.asarray(review["coordinates"]["plot_origin_xyz_m"])
    points = {name: np.asarray(mesh["vertices_local_xyz_m"])+np.asarray(mesh["local_origin_xyz_m"])-origin for name, mesh in review["meshes"].items()}
    faces = {name: np.asarray(mesh["triangles"], int) for name, mesh in review["meshes"].items()}
    native = np.asarray(review["native_terrain"]["height_m"])
    valid = np.asarray(review["native_terrain"]["valid_mask"], bool)
    spacing = review["coordinates"]["native_spacing_m"]
    native_origin = np.asarray(review["coordinates"]["native_origin_m_xz"])-origin[[0, 2]]
    shade = LightSource(315, 45).hillshade(native, dx=spacing, dy=spacing)
    shade[~valid] = np.nan
    extent = [native_origin[0]-spacing/2, native_origin[0]+(native.shape[1]-.5)*spacing,
              native_origin[1]+(native.shape[0]-.5)*spacing, native_origin[1]-spacing/2]
    portals = {kind: np.asarray(node["xyz_m"])-origin for kind, node in review["portals"].items()}
    output = {}

    def finish(figure, name):
        stream = BytesIO()
        figure.savefig(stream, format="png", dpi=150, facecolor="white")
        plt.close(figure)
        require(stream.tell() <= MAX_BYTES, "scientific PNG exceeds 64MiB")
        output[name] = stream.getvalue()
        check_memory()

    figure, axes = plt.subplots(1, 2, figsize=(14, 7), gridspec_kw={"width_ratios": [1, 1.5]})
    low, high = points["rock_before"][:, [0, 2]].min(axis=0), points["rock_before"][:, [0, 2]].max(axis=0)
    for axis in axes:
        axis.imshow(shade, cmap="gray", extent=extent, interpolation="nearest")
        for kind, point in portals.items():
            axis.scatter(point[0], point[2], marker="v" if kind == "sink" else "^", s=55, c="#a84635", zorder=5)
            axis.annotate(kind, point[[0, 2]], xytext=(6, 7), textcoords="offset points", fontsize=9)
        axis.set_aspect("equal")
        axis.xaxis.set_major_locator(MaxNLocator(4))
        axis.yaxis.set_major_locator(MaxNLocator(4))
        axis.ticklabel_format(style="plain", useOffset=False)
        axis.set_xlabel("Local X (m)")
        axis.set_ylabel("Local Z (m)")
    axes[0].add_patch(Rectangle(low, *(high-low), facecolor="none", edgecolor="#a84635", linewidth=1.5))
    axes[0].set_title("Native mountain location")
    axes[1].add_collection(PolyCollection(points["removed"][:, [0, 2]][faces["removed"]], facecolors="#a78342", edgecolors="none", alpha=.65))
    margin = max(5., float(np.max(high-low))*.08)
    axes[1].set_xlim(low[0]-margin, high[0]+margin)
    axes[1].set_ylim(low[1]-margin, high[1]+margin)
    axes[1].set_title("Saved excavated-solid projection; not water")
    figure.suptitle("Engineered local cave | native terrain and actual saved geometry", fontsize=14)
    figure.text(.05, .03, "Model origin XYZ (m): "+str(origin.tolist())+" | Original native samples, no solver", fontsize=9)
    figure.subplots_adjust(bottom=.15, top=.86, wspace=.3)
    finish(figure, "overview.png")

    stations = review["stations"]
    rings = [np.asarray(station["derived_ring_xyz_m"])-origin for station in stations]
    centers = np.asarray([np.asarray(station["origin_xyz_m"])-origin for station in stations])
    distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(centers, axis=0), axis=1))]
    figure, axis = plt.subplots(figsize=(13, 5))
    floor = [ring[:, 1].min()+origin[1] for ring in rings]
    roof = [ring[:, 1].max()+origin[1] for ring in rings]
    axis.plot(distance, floor, color="#825f2c", linewidth=2., label="Saved VDM ring minimum elevation")
    axis.plot(distance, roof, color="#696561", linewidth=1., linestyle=":", label="Cutter roof outline; not rock roof at open ramps")
    core = review["actual_closed_core_station_indices"]
    if core:
        axis.plot(distance[core], np.asarray(roof)[core], color="#696561", linewidth=2.5, label="Saved roof outline within actual covered core")
    axis.fill_between(distance, floor, roof, color="#a78342", alpha=.16, label="Section envelope only; not water")
    axis.set_xlabel("Saved station-origin path distance (m)")
    axis.set_ylabel("Model Y elevation (m)")
    axis.set_title("Final saved VDM sections | longitudinal elevation envelope")
    axis.grid(alpha=.2)
    axis.legend(fontsize=9)
    axis.ticklabel_format(style="plain", useOffset=False)
    figure.tight_layout()
    finish(figure, "profile.png")

    figure = plt.figure(figsize=(13, 9))
    axis = figure.add_subplot(111, projection="3d")
    for name, color, alpha in (("rock_after", "#787d77", .16), ("removed", "#b29155", .45)):
        plotted = points[name][:, [0, 2, 1]].copy()
        plotted[:, 2] *= vertical_exaggeration
        axis.add_collection3d(Poly3DCollection(plotted[faces[name]], facecolors=color, edgecolors="none", alpha=alpha, rasterized=True))
    for ring in rings:
        closed = np.vstack((ring, ring[0]))
        axis.plot(closed[:, 0], closed[:, 2], closed[:, 1]*vertical_exaggeration, color="#73552b", linewidth=.65, alpha=.8)
    for attachment in review["surface_attachments"].values():
        mesh = attachment["geometry"]
        halfarm = np.asarray(mesh["vertices_xyz_m"])-origin
        halfarm = halfarm[:, [0, 2, 1]]
        halfarm[:, 2] *= vertical_exaggeration
        triangles = np.asarray(mesh["triangles"], int)[attachment["half_arm_triangle_indices"]]
        axis.add_collection3d(Poly3DCollection(halfarm[triangles], facecolors="#527363", edgecolors="none", alpha=.8))
    rows, columns = np.indices(native.shape)
    native_x = native_origin[0]+columns*spacing
    native_z = native_origin[1]+rows*spacing
    crop = valid & (native_x >= low[0]) & (native_x <= high[0]) & (native_z >= low[1]) & (native_z <= high[1])
    axis.scatter(native_x[crop], native_z[crop], (native[crop]-origin[1])*vertical_exaggeration,
                 s=2, c="#444844", alpha=.35, depthshade=False)
    for kind, point in portals.items():
        axis.scatter(point[0], point[2], point[1]*vertical_exaggeration, c="#a84635", marker="v" if kind == "sink" else "^", s=50)
        axis.text(point[0], point[2], point[1]*vertical_exaggeration, " "+kind, fontsize=9)
    bounds = points["rock_before"][:, [0, 2, 1]].copy()
    bounds[:, 2] *= vertical_exaggeration
    minimum, maximum = bounds.min(axis=0), bounds.max(axis=0)
    span = np.maximum(maximum-minimum, 1.)
    axis.set_xlim(minimum[0], maximum[0])
    axis.set_ylim(minimum[1], maximum[1])
    axis.set_zlim(minimum[2], maximum[2])
    axis.set_box_aspect(span)
    axis.view_init(elev=22, azim=-58)
    axis.set_xlabel("Local X (m)")
    axis.set_ylabel("Local Z (m)")
    axis.set_zlabel("Local Y (m)" if vertical_exaggeration == 1 else "Local Y x "+str(vertical_exaggeration))
    for coordinate_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
        coordinate_axis.set_major_locator(MaxNLocator(4))
    axis.set_title("Actual remaining-rock shell (transparent) + saved excavated solid + final VDM rings\n"
                   "Native samples (dots), saved half-arms (green); no water; Y multiplier "+str(vertical_exaggeration), fontsize=11)
    figure.text(.08, .03, "Local origin XYZ (m): "+str(origin.tolist())+" | Transparency is inspection only; independent opening audit required", fontsize=9)
    finish(figure, "oblique-3d.png")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--geometry-sha256", required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--audit-sha256")
    parser.add_argument("--audit-schema", default=AUDIT_SCHEMA, choices=[AUDIT_SCHEMA])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vertical-exaggeration", type=float, default=1.)
    args = parser.parse_args()
    require(not args.output.exists(), "new review output directory required")
    review = load_review(args.geometry, args.geometry_sha256, args.audit, args.audit_sha256, args.audit_schema)
    artifacts = {"review.json": encoded(review), "caseartifact.json": encoded(caseartifact(review))}
    artifacts.update(render_figures(review, args.vertical_exaggeration))
    print(publish_directory(args.output, artifacts))


if __name__ == "__main__":
    main()
