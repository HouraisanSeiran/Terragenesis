"""Explicit parametric channel geometry on an accepted saved lake/spill graph."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_overflow import load_overflow_topology
from terrain_pipeline.td_basin_runoff_exchange import load_runoff_exchange
from terrain_pipeline.td_watershed_paths import build_watershed_paths
from terrain_pipeline.td_watershed_sections import build_watershed_sections

PARENT = ROOT / "verification/natural-river-network/lake-spill-main-watershed-20261005-02"
PARENT_SHA = "79d6b056cb4a3d612009daea42e1f45fbf5ed19950b625d1c7ee5e8d90e401f6"
AUDIT_SHA = "bff158c828efedfecb975d6201986128b1b73059a40f96ca3216062bc58fbded"
CODE = ("terrain_pipeline/td_watershed_paths.py", "terrain_pipeline/td_watershed_sections.py",
        "terrain_pipeline/td_natural_river_network.py", "terrain_pipeline/mountain_source_adapter.py",
        "terrain_pipeline/td_basin_hierarchy.py", "terrain_pipeline/td_basin_overflow.py",
        "terrain_pipeline/td_basin_runoff_exchange.py", "tools/prepare_td_watershed_geometry.py")
MAX_JSON_BYTES = 32 * 1024**2
MAX_RSS_BYTES = 1024**3
FLAGS = {"hydraulic_ready": False, "natural_outlet_verified": False,
         "permanent_trunk_ready": False, "publishable": False,
         "solver_advanced": False, "bed_changed": False}


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def publish_json(path, record):
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_JSON_BYTES:
        raise MemoryError("watershed JSON exceeds declared 32MiB artifact limit")
    publish_bytes(path, payload)


def pinned_path(pin, base):
    path = (Path(base) / pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()) or file_sha256(path) != pin["sha256"]:
        raise ValueError("watershed input path/hash mismatch")
    return path


def pinned_json(pin, base):
    path = pinned_path(pin, base)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise MemoryError("watershed parent JSON exceeds input budget")
    return json.loads(path.read_text(encoding="utf-8"))


def pin(path, record=None):
    result = {"path": Path(path).name, "sha256": file_sha256(path), "bytes": Path(path).stat().st_size}
    if record is not None:
        result["identity_sha256"] = record["identity_sha256"]
    return result


def make_review(paths, sections, hierarchy, topology, ordinary, graph):
    arrays = hierarchy["arrays"]
    selected = arrays["valid_mask"] & np.isin(arrays["contribution_owner"], paths["selected_leaf_ids"])
    sample_index = graph["main_route_support"]["saved_index_for_review"]
    stage = np.full(len(arrays["node_parent"]), -np.inf)
    stage[topology["arrays"]["leaf_ids"]] = ordinary["arrays"]["stage_m"][sample_index]
    wet = selected & (stage[np.maximum(arrays["contribution_owner"], 0)] > arrays["height_m"])
    review = {"schema": "td-watershed-geometry-review-v1", "case_id": "baseline",
              "origin_m_xz": hierarchy["metadata"]["origin_m_xz"],
              "spacing_m": hierarchy["metadata"]["spacing_m"],
              "height_m": arrays["height_m"].tolist(),
              "primary_support_cell_ids": np.flatnonzero(selected).tolist(),
              "sampled_lake_wet_cell_ids": np.flatnonzero(wet).tolist(),
              "sampled_index": sample_index, "sampled_time_s": sample_index * ordinary["metadata"]["timestep_s"],
              "sampled_stage_by_leaf": [{"leaf_id": int(leaf), "stage_m": float(stage[leaf])}
                                        for leaf in paths["selected_leaf_ids"]],
              "paths": paths, "sections": sections, "parametric_only": True,
              "bed_rasterized": False, "water_surface_meshed": False,
              "semantics": "native bed and sampled storage footprint with parametric land cross-sections; support arcs are not carved channels",
              **FLAGS}
    review["identity_sha256"] = digest(review)
    return review


def draw_plan(axis, review, *, zoom):
    from matplotlib.colors import LightSource
    from matplotlib.lines import Line2D

    bed = np.asarray(review["height_m"])
    spacing = review["spacing_m"]
    origin = review["origin_m_xz"]
    half = spacing / 2000.
    extent = [-half, (bed.shape[1] - .5) * spacing / 1000.,
              (bed.shape[0] - .5) * spacing / 1000., -half]
    axis.imshow(LightSource(315, 45).hillshade(bed, dx=spacing, dy=spacing), cmap="gray", extent=extent)
    overlay = np.zeros((*bed.shape, 4))
    overlay.reshape(-1, 4)[review["primary_support_cell_ids"]] = [.24, .67, .37, .28]
    overlay.reshape(-1, 4)[review["sampled_lake_wet_cell_ids"]] = [.08, .7, .88, .85]
    axis.imshow(overlay, extent=extent, interpolation="nearest")
    for arc in review["paths"]["arcs"]:
        points = np.asarray(arc["xyz_m"])
        if not len(points):
            continue
        color = "#11776f" if arc["channel_candidate"] else "#a23474" if arc["is_main_path"] else "#3685ac"
        axis.plot((points[:, 0] - origin[0]) / 1000., (points[:, 2] - origin[1]) / 1000.,
                  color=color, linewidth=1.25 if arc["is_main_path"] else .7,
                  linestyle="-" if arc["channel_candidate"] else "--")
    if zoom:
        cells = np.asarray(review["primary_support_cell_ids"])
        rows, columns = cells // bed.shape[1], cells % bed.shape[1]
        axis.set_xlim((columns.min() * spacing - 90.) / 1000., (columns.max() * spacing + 90.) / 1000.)
        axis.set_ylim((rows.max() * spacing + 90.) / 1000., (rows.min() * spacing - 90.) / 1000.)
    axis.set_xlabel("Local east (km)")
    axis.set_ylabel("Local south (km)")
    axis.set_title("Main component / typed support" if zoom else "Full TD domain / 2.9169 km2 diagnostic support")
    axis.legend(handles=[Line2D([0], [0], color="#11776f", label="Land receiver candidates"),
                         Line2D([0], [0], color="#a23474", linestyle="--", label="Main lake/spill support"),
                         Line2D([0], [0], color="#3685ac", linestyle="--", label="Other lake/spill support")],
                loc="upper left", fontsize=8)


def render_review(output, review):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    figure, axes = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True)
    draw_plan(axes[0], review, zoom=False)
    draw_plan(axes[1], review, zoom=True)
    figure.suptitle("Typed watershed geometry candidates; dashed lake paths are not river beds")
    figure.savefig(output / "watershed-overview.png", dpi=120)
    plt.close(figure)
    figure = plt.figure(figsize=(14, 6), layout="constrained")
    axis = figure.add_subplot(121, projection="3d")
    section_axis = figure.add_subplot(122)
    mesh = review["sections"]["mesh"]
    vertices = np.asarray(mesh["vertices_xyz_m"], dtype=float).reshape(-1, 3)
    triangles = np.asarray(mesh["triangles"], dtype=int).reshape(-1, 3)
    used_xyz = {tuple(point) for point in vertices[np.unique(triangles)]} if len(triangles) else set()
    candidates = [record for record in review["sections"]["node_sections"]
                  if record.get("cross_section_xyz_m") and
                  any(tuple(point) in used_xyz for point in record["cross_section_xyz_m"])]
    if candidates and len(triangles):
        section = max(candidates, key=lambda record: (record["width_m"], -record["cell_id"]))
        center = next(node["xyz_m"] for node in review["paths"]["nodes"] if node["node_id"] == section["node_id"])
        radius = max(35., section["width_m"] * 8.)
        triangle_xyz = vertices[triangles]
        nearby = np.max(np.abs(triangle_xyz[:, :, (0, 2)] - np.asarray(center)[[0, 2]]), axis=(1, 2)) <= radius * 1.5
        selected = triangle_xyz[nearby]
        if not len(selected):
            raise ValueError("section close-up did not include a real mesh triangle")
        shifted = selected - np.asarray(center)
        axis.add_collection3d(Poly3DCollection(shifted[:, :, (0, 2, 1)], facecolor="#3d998d", edgecolor="#1c5550",
                                             linewidth=.4, alpha=.95))
        axis.set_xlim(-radius, radius)
        axis.set_ylim(-radius, radius)
        heights = shifted[:, :, 1]
        axis.set_zlim(float(heights.min()) - .3, float(heights.max()) + .3)
        axis.set_box_aspect((1., 1., .6))
        axis.view_init(elev=30., azim=-55.)
        axis.set_xlabel("East offset (m)")
        axis.set_ylabel("South offset (m)")
        axis.set_zlabel("Elevation offset (m)")
        axis.set_title("Actual parametric triangles / not rasterized terrain")
        profile = np.asarray(section["cross_section_xyz_m"])
        distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(profile[:, (0, 2)], axis=0), axis=1))]
        distance -= distance[len(distance) // 2]
        section_axis.plot(distance, profile[:, 1] - section["bed_m"], "o-", color="#11776f", markersize=4)
        section_axis.set_xlabel("Transverse offset (m)")
        section_axis.set_ylabel("Height above candidate bed (m)")
        section_axis.set_title(f"Shared node {section['node_id']} / width {section['width_m']:.3f} m / depth {section['depth_m']:.3f} m")
        section_axis.grid(alpha=.2)
    else:
        axis.set_title("No accepted land triangles; refusals retained")
        section_axis.set_title("No accepted cross-section")
    figure.suptitle("Diagnostic cross-sections only; no fine DEM, channel hydraulics or natural outlet certification")
    figure.savefig(output / "channel-closeup.png", dpi=120)
    plt.close(figure)


def run(output):
    started = time.perf_counter()
    parent_pin = {"path": str(PARENT / "index.json"), "sha256": PARENT_SHA}
    audit_pin = {"path": str(PARENT / "independent-audit.json"), "sha256": AUDIT_SHA}
    parent = pinned_json(parent_pin, ROOT)
    audit = pinned_json(audit_pin, ROOT)
    if audit["status"] != "passed" or audit["index_sha256"] != PARENT_SHA:
        raise ValueError("accepted lake/spill parent required")
    for name, expected in parent["code_sha256"].items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("frozen lake/spill parent code changed")
    source = next(case for case in parent["cases"] if case["case_id"] == "baseline")
    graph = pinned_json(source["graph"], PARENT)
    inputs = source["inputs"]
    hierarchy_pin, topology_pin, ordinary_pin = inputs["hierarchy"], inputs["topology"], inputs["events"]["ordinary"]
    hierarchy = load_basin_hierarchy(pinned_path(hierarchy_pin, PARENT), expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    topology = load_overflow_topology(pinned_path(topology_pin, PARENT), expected_sha256=topology_pin["sha256"],
                                     expected_identity=topology_pin["identity_sha256"])
    ordinary = load_runoff_exchange(pinned_path(ordinary_pin, PARENT), expected_sha256=ordinary_pin["sha256"],
                                    expected_identity=ordinary_pin["identity_sha256"], topology=topology)
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError("watershed output must stay inside workspace")
    output.mkdir(parents=True, exist_ok=False)
    code_pins = {name: file_sha256(ROOT / name) for name in CODE}
    print(json.dumps({"state": "building_paths", "solver_advanced": False}), flush=True)
    paths = build_watershed_paths(graph, hierarchy, ordinary)
    print(json.dumps({"state": "building_sections", "nodes": len(paths["nodes"]), "arcs": len(paths["arcs"])}), flush=True)
    sections = build_watershed_sections(paths, hierarchy, topology, ordinary)
    review = make_review(paths, sections, hierarchy, topology, ordinary, graph)
    publish_json(output / "paths.json", paths)
    publish_json(output / "sections.json", sections)
    publish_json(output / "review.json", review)
    render_review(output, review)
    memory = psutil.Process().memory_info()
    peak = getattr(memory, "peak_wset", None)
    if peak is None or peak > MAX_RSS_BYTES:
        raise MemoryError("Windows peak RSS required within original 1GiB budget")
    for name, expected in code_pins.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("geometry code changed during preparation")
    summary = {"primary_support_area_m2": graph["routing_forest"]["primary_component"]["area_m2"],
               "basin_count": len(paths["selected_leaf_ids"]), "node_count": len(paths["nodes"]),
               "arc_count": len(paths["arcs"]), "land_arc_count": sum(arc["channel_candidate"] for arc in paths["arcs"]),
               "section_count": len(sections["node_sections"]),
               "vertex_count": len(sections["mesh"]["vertices_xyz_m"]),
               "triangle_count": len(sections["mesh"]["triangles"]),
               "fine_request_count": len(sections["fine_requests"]), "details": sections.get("summary", {})}
    index = {"schema": "td-watershed-geometry-preparation-v1", "status": "ready_for_independent_audit",
             "parent_index": parent_pin, "parent_audit": audit_pin, "parent_graph": {**source["graph"],
                 "path": str(pinned_path(source["graph"], PARENT))},
             "inputs": {"hierarchy": hierarchy_pin, "topology": topology_pin, "ordinary": ordinary_pin},
             "code_sha256": code_pins, "paths": pin(output / "paths.json", paths),
             "sections": pin(output / "sections.json", sections), "review": pin(output / "review.json", review),
             "images": [pin(output / name) for name in ("watershed-overview.png", "channel-closeup.png")],
             "summary": summary, "resource": {"peak_rss_bytes": peak, "max_rss_bytes": MAX_RSS_BYTES,
                 "elapsed_s": time.perf_counter() - started, "max_json_bytes": MAX_JSON_BYTES},
             "parametric_only": True, "bed_rasterized": False, "water_surface_meshed": False, **FLAGS}
    publish_json(output / "index.json", index)
    return {"directory": str(output), "index_sha256": file_sha256(output / "index.json"), "summary": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), ensure_ascii=False))
