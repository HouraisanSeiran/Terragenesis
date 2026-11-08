"""Saved-event main watershed review using retained lake and spill nodes."""

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_overflow import load_overflow_topology
from terrain_pipeline.td_basin_runoff_exchange import load_runoff_exchange
from terrain_pipeline.td_lake_spill_graph import build_lake_spill_graph, digest, interval_ranges, save_lake_spill_graph

PARENT = ROOT / "verification/natural-river-network/bounded-conditioning-20261005-01"
PARENT_SHA = "9091396732558f7b795888bd83c86713c3e8c9e644768c3b8cb801ab9b152437"
AUDIT_SHA = "636f619b0661bb0bb50ccd8bb9f242dae255f4a6a202f9c64a7162af889adbf6"
BASELINE_SHA = "cd78c2f2ce9c6a1abbd98ae7ee528079dfb2ee1b5ce2905458e64137aa868e5f"
CODE = ("terrain_pipeline/td_lake_spill_graph.py", "terrain_pipeline/td_lake_spill_geometry.py",
        "terrain_pipeline/td_lake_outlet_forest.py", "tools/prepare_td_lake_spill_graph.py")
NORMAL = "normal-spatial-recession-24h"
STRONG = "strong-spatial-recession-6h"


def publish(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))


def pin_path(pin, directory):
    path = (Path(directory) / pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("saved lake-graph input escapes workspace")
    return path


def pinned_json(pin, directory):
    path = pin_path(pin, directory)
    if file_sha256(path) != pin["sha256"]:
        raise ValueError("lake-graph saved input hash mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def absolute_pin(pin, directory):
    return {**pin, "path": str(pin_path(pin, directory))}


def load_inputs(configuration, cases, directory):
    hierarchy_pin = absolute_pin(configuration["hierarchy"], directory)
    topology_pin = absolute_pin(configuration["topology"], directory)
    hierarchy = load_basin_hierarchy(hierarchy_pin["path"], expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    topology = load_overflow_topology(topology_pin["path"], expected_sha256=topology_pin["sha256"],
                                     expected_identity=topology_pin["identity_sha256"])
    lookup = {case["name"]: case for case in cases}
    if set(lookup) != {NORMAL, STRONG} or len(cases) != 2:
        raise ValueError("ordinary/strong input coverage differs")
    events, pins = {}, {}
    for key, name in (("ordinary", NORMAL), ("strong", STRONG)):
        levels = lookup[name]["levels"]
        if [level["level"] for level in levels] != [0, 1]:
            raise ValueError("lake graph requires two actual saved refinement levels")
        for suffix, level in (("", levels[1]), ("_reference", levels[0])):
            pin = absolute_pin(level["event"], directory)
            events[key + suffix] = load_runoff_exchange(pin["path"], expected_sha256=pin["sha256"],
                expected_identity=pin["identity_sha256"], topology=topology)
            pins[key + suffix] = pin
    return hierarchy, topology, events, {"hierarchy": hierarchy_pin, "topology": topology_pin, "events": pins}


def main_route_support(graph, topology, ordinary):
    forest = graph["routing_forest"]
    primary = forest["primary_component"]
    if primary is None:
        return {"path_face_ids": [], "positive_intervals": [], "positive_duration_s": 0.,
                "semantics": "no event-supported route to an accepted engineering outlet"}
    face_lookup = {face["face_id"]: position for position, face in enumerate(topology["faces"])}
    edge_lookup = {edge["face_id"]: edge for edge in graph["edges"]}
    mask = np.ones(ordinary["metadata"]["steps"], bool)
    for face_id in forest["main_path_face_ids"]:
        position, edge = face_lookup[face_id], edge_lookup[face_id]
        signed = ordinary["arrays"]["face_forward_m3"][:, position] - ordinary["arrays"]["face_reverse_m3"][:, position]
        mask &= signed * edge["ordinary"]["direction"] >= 1e-6
    boundary_position = next(position for position, boundary in enumerate(topology["engineering_boundaries"])
                             if boundary["cell_id"] == primary["root_boundary_cell_id"])
    mask &= ordinary["arrays"]["engineering_boundary_outflow_m3"][:, boundary_position] >= 1e-6
    return {"path_face_ids": forest["main_path_face_ids"], "root_boundary_cell_id": primary["root_boundary_cell_id"],
            "positive_intervals": interval_ranges(mask), "positive_duration_s": float(mask.sum() * 300.),
            "saved_index_for_review": int(np.flatnonzero(mask)[-1] + 1) if mask.any() else ordinary["metadata"]["steps"],
            "semantics": "same 300s saved intervals have positive transfer on every selected face and outlet; not travel-time or resolved continuous-channel certification"}


def frontier_requests(graph):
    primary = graph["routing_forest"]["primary_component"]
    if primary is None:
        return []
    members = set(primary["leaf_ids"])
    nodes = {node["leaf_id"]: node for node in graph["nodes"]}
    requests = []
    for edge in graph["edges"]:
        first, second = edge["leaf_ids"]
        if (first in members) == (second in members):
            continue
        source, receiver = (second, first) if first in members else (first, second)
        if nodes[source]["blocked_reasons"] or nodes[receiver]["blocked_reasons"]:
            continue
        direction = 1 if source == first else -1
        net_into_main = direction * edge["ordinary"]["net_m3"]
        requests.append({"face_id": edge["face_id"], "face_cell_ids": edge["cell_ids"],
            "source_leaf_id": source, "receiver_leaf_id": receiver,
            "upstream_exclusive_area_m2": nodes[source]["exclusive_area_m2"],
            "physical_sill_m": edge["sill_m"], "ordinary_net_toward_main_m3": net_into_main,
            "stage_gap_to_sill_m": max(0., edge["sill_m"] - nodes[source]["ordinary_stage_max_m"]),
            "ordinary_rejection_reasons": edge["ordinary"]["rejection_reasons"],
            "geometry_rejection_reason": None if edge["geometry"] is None else edge["geometry"].get("reason"),
            "generation_requested": False, "semantics": "shared-face frontier for targeted evaluation; no imposed flow or terrain modification"})
    return sorted(requests, key=lambda item: (item["ordinary_net_toward_main_m3"] <= 0.,
        item["stage_gap_to_sill_m"], -item["upstream_exclusive_area_m2"], item["face_id"]))


def build_review_case(case_id, graph, hierarchy, topology, ordinary):
    primary = graph["routing_forest"]["primary_component"]
    members = [] if primary is None else primary["leaf_ids"]
    owner = hierarchy["arrays"]["contribution_owner"]
    mask = hierarchy["arrays"]["valid_mask"] & np.isin(owner, members)
    selected_index = graph["main_route_support"].get("saved_index_for_review", 0)
    stage_by_node = np.full(len(hierarchy["arrays"]["node_parent"]), -np.inf)
    stage_by_node[topology["arrays"]["leaf_ids"]] = ordinary["arrays"]["stage_m"][selected_index]
    stage = stage_by_node[np.maximum(owner, 0)]
    wet = mask & (stage > hierarchy["arrays"]["height_m"]) & ~hierarchy["arrays"]["protected_mask"]
    routing_faces = {record["parent_face_id"] for record in graph["routing_forest"]["records"]
                     if record["leaf_id"] in members and record["parent_face_id"] is not None}
    routes = [edge for edge in graph["edges"] if edge["face_id"] in routing_faces]
    outlet = None if primary is None else next(item for item in graph["outlets"]
        if item["cell_id"] == primary["root_boundary_cell_id"])
    return {"case_id": case_id, "source_identity_sha256": graph["source_identity_sha256"],
            "height_m": hierarchy["arrays"]["height_m"].tolist(),
            "primary_support_cell_ids": np.flatnonzero(mask).tolist(),
            "sampled_lake_wet_cell_ids": np.flatnonzero(wet).tolist(),
            "sampled_index": selected_index, "sampled_time_s": selected_index * 300.,
            "sampled_wet_semantics": "wet footprint of the saved equipotential basin storage model, not native-grid fine hydraulics",
            "primary_component": primary, "nodes": graph["nodes"], "routes": routes,
            "outlet": outlet, "main_route_support": graph["main_route_support"],
            "frontier_requests": graph["frontier_requests"],
            "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False, "permanent_trunk_ready": False}


def render_review(path, cases, origin, spacing):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    figure, axes = plt.subplots(1, len(cases), figsize=(15, 7), constrained_layout=True, squeeze=False)
    for axis, case in zip(axes[0], cases):
        bed = np.asarray(case["height_m"])
        half_cell_km = spacing / 2000.
        extent = [-half_cell_km, (bed.shape[1] - .5) * spacing / 1000.,
                  (bed.shape[0] - .5) * spacing / 1000., -half_cell_km]
        terrain = LightSource(azdeg=315, altdeg=45).hillshade(bed, dx=spacing, dy=spacing)
        axis.imshow(terrain, cmap="gray", extent=extent)
        overlay = np.zeros((*bed.shape, 4))
        overlay.reshape(-1, 4)[case["primary_support_cell_ids"]] = [.24, .67, .37, .4]
        overlay.reshape(-1, 4)[case["sampled_lake_wet_cell_ids"]] = [.08, .7, .88, .8]
        axis.imshow(overlay, extent=extent, interpolation="nearest")
        for edge in case["routes"]:
            for name, color, style in (("source_lake_approach", "#086fa1", "-"),
                                       ("cross_face", "#086fa1", "-"),
                                       ("downhill_terrain_approach", "#e26c30", "--")):
                xyz = np.asarray(edge["geometry"][name]["xyz_m"])
                axis.plot((xyz[:, 0] - origin[0]) / 1000., (xyz[:, 2] - origin[1]) / 1000.,
                          color=color, linestyle=style, linewidth=1.)
        if case["outlet"] is not None:
            xyz = np.asarray(case["outlet"]["geometry"]["source_lake_approach"]["xyz_m"])
            axis.plot((xyz[:, 0] - origin[0]) / 1000., (xyz[:, 2] - origin[1]) / 1000., color="#941d46", linewidth=1.5)
            axis.scatter((xyz[-1, 0] - origin[0]) / 1000., (xyz[-1, 2] - origin[1]) / 1000.,
                         marker="v", c="#941d46", s=45, zorder=5)
        primary = case["primary_component"]
        area = 0. if primary is None else primary["area_m2"] / 1e6
        count = 0 if primary is None else primary["leaf_count"]
        axis.set_title(f"{case['case_id']}: {area:.3f} km2 event-supported area\n{count} retained basins; ordinary saved t={case['sampled_time_s']/3600:.2f} h")
        axis.set_xlabel("Local east (km)")
        axis.set_ylabel("Local south (km)")
    figure.suptitle("Lake/spill connections: green=support, cyan=storage wet footprint; blue=lake approach, orange=terrain route")
    figure.savefig(path, dpi=120)
    plt.close(figure)


def run(output):
    parent_pin = {"path": str(PARENT / "index.json"), "sha256": PARENT_SHA}
    audit_pin = {"path": str(PARENT / "independent-audit.json"), "sha256": AUDIT_SHA}
    parent = pinned_json(parent_pin, ROOT)
    audit = pinned_json(audit_pin, ROOT)
    if audit["status"] != "passed" or audit["index_sha256"] != PARENT_SHA:
        raise ValueError("accepted new-bed parent evidence required")
    baseline_pin = parent["configuration"]["baseline_index"]
    if baseline_pin["sha256"] != BASELINE_SHA:
        raise ValueError("baseline source changed")
    baseline = pinned_json(baseline_pin, ROOT)
    baseline_audit_pin = parent["configuration"]["baseline_audit"]
    baseline_audit = pinned_json(baseline_audit_pin, ROOT)
    if baseline_audit["status"] != "passed" or baseline_audit["index_sha256"] != BASELINE_SHA:
        raise ValueError("accepted original-bed evidence required")
    derived = next(record for record in parent["candidates"] if record["candidate_id"] == "limited_fill")
    configurations = [("baseline", {"hierarchy": parent["configuration"]["hierarchy"],
        "topology": parent["configuration"]["baseline_topology"]}, baseline["cases"], Path(baseline_pin["path"]).parent),
        ("limited_fill", {"hierarchy": derived["hierarchy"], "topology": derived["topology"]}, derived["cases"], PARENT)]
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    code_pins = {name: file_sha256(ROOT / name) for name in CODE}
    started = time.perf_counter()
    cases, reviews = [], []
    for case_id, config, inputs, directory in configurations:
        print(json.dumps({"state": "reading_saved_events", "case": case_id}), flush=True)
        hierarchy, topology, events, pins = load_inputs(config, inputs, directory)
        graph = build_lake_spill_graph(hierarchy, topology, **events)
        graph["main_route_support"] = main_route_support(graph, topology, events["ordinary"])
        graph["frontier_requests"] = frontier_requests(graph)
        graph["identity_sha256"] = digest({key: value for key, value in graph.items() if key != "identity_sha256"})
        path = output / f"{case_id}-graph.json"
        save_lake_spill_graph(graph, path)
        primary = graph["routing_forest"]["primary_component"]
        case = {"case_id": case_id, "inputs": pins,
                "graph": {"path": path.name, "sha256": file_sha256(path), "identity_sha256": graph["identity_sha256"]},
                "summary": {"basin_count": len(graph["nodes"]), "physical_faces": len(graph["edges"]),
                    "ordinary_stable_faces": sum(edge["ordinary"]["stable_relationship"] for edge in graph["edges"]),
                    "routing_eligible_faces": sum(edge["routing_eligible"] for edge in graph["edges"]),
                    "routing_eligible_outlets": sum(item["routing_eligible"] for item in graph["outlets"]),
                    "primary_event_supported_area_m2": 0. if primary is None else primary["area_m2"],
                    "primary_basin_count": 0 if primary is None else primary["leaf_count"],
                    "static_largest_catchment_area_m2": float(topology["arrays"]["leaf_area_m2"].max()),
                    "main_route_positive_duration_s": graph["main_route_support"]["positive_duration_s"],
                    "frontier_request_count": len(graph["frontier_requests"])}}
        cases.append(case)
        reviews.append(build_review_case(case_id, graph, hierarchy, topology, events["ordinary"]))
        origin, spacing = hierarchy["metadata"]["origin_m_xz"], hierarchy["metadata"]["spacing_m"]
        print(json.dumps({"state": "graph_saved", "case": case_id, **case["summary"]}), flush=True)
        del hierarchy, topology, events, graph
    for name, expected in code_pins.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("lake graph implementation changed during prepare")
    review = {"schema": "td-lake-spill-review-v1", "origin_m_xz": origin, "spacing_m": spacing,
              "cases": reviews, "solver_advanced": False, "hydraulic_ready": False,
              "natural_outlet_verified": False, "publishable": False, "permanent_trunk_ready": False}
    publish(output / "review.json", review)
    render_review(output / "main-watershed-review.png", reviews, origin, spacing)
    index = {"schema": "td-lake-spill-preparation-v1", "status": "ready_for_independent_audit",
             "parent_index": parent_pin, "parent_audit": audit_pin, "baseline_index": baseline_pin,
             "baseline_audit": baseline_audit_pin, "code_sha256": code_pins, "cases": cases,
             "review": {"path": "review.json", "sha256": file_sha256(output / "review.json")},
             "image": {"path": "main-watershed-review.png", "sha256": file_sha256(output / "main-watershed-review.png")},
             "elapsed_s": time.perf_counter() - started,
             "solver_advanced": False, "bed_changed": False, "water_generated": False,
             "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False, "permanent_trunk_ready": False}
    publish(output / "index.json", index)
    return {"directory": str(output), "index_sha256": file_sha256(output / "index.json"), "cases": [case["summary"] for case in cases]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    print(json.dumps(run(parser.parse_args().output), ensure_ascii=False))
