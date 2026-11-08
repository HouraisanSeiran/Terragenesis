"""Compare saved river geometry at frozen baseline locations, one mesh at a time."""

import argparse
import gc
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib.collections import PolyCollection
import numpy as np
from scipy.interpolate import RegularGridInterpolator

from tools.render_td_generated_rivers import load_sample
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import load_component_geometry
from terrain_pipeline.surface_rivers.metric_td_generated_source import load_generated_td_source


def edge_inventory(mesh):
    cells = mesh["source_node_cell_ids"]
    return {(int(cells[i]), int(cells[j])) for i, j in enumerate(mesh["receiver"]) if j >= 0}


def coverage(before, after):
    return {"baseline_count": len(before), "candidate_count": len(after),
            "common_count": len(before & after), "lost_edge_ids": sorted(before - after),
            "added_edge_ids": sorted(after - before)}


def selection_transitions(before, after):
    def statuses(arrays):
        return {(int(source), int(target)): str(status) for source, target, status in zip(
            arrays["selected_edge_source_ids"], arrays["selected_edge_target_ids"], arrays["selected_edge_status"])}
    old, new = statuses(before), statuses(after)
    old_rejected = {edge for edge, status in old.items() if not status.startswith("accepted")}
    new_rejected = {edge for edge, status in new.items() if not status.startswith("accepted")}
    return {"baseline_rejected_edge_ids": sorted(old_rejected), "candidate_rejected_edge_ids": sorted(new_rejected),
            "previously_accepted_now_rejected_edge_ids": sorted(new_rejected & (old.keys() - old_rejected)),
            "previously_rejected_now_accepted_edge_ids": sorted(old_rejected & (new.keys() - new_rejected)),
            "no_longer_selected_edge_ids": sorted(old.keys() - new.keys()),
            "newly_selected_edge_ids": sorted(new.keys() - old.keys())}


def turn_metrics(mesh, allowed_edges=None):
    """Measure actual saved node positions; include junction turns separately."""
    cells, receiver, points = (mesh[key] for key in ("source_node_cell_ids", "receiver", "node_xz_m"))
    donors = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    values = {"ordinary": [], "confluence": []}
    edge_count = terminal_count = 0
    for first, middle in enumerate(receiver):
        if middle < 0 or (allowed_edges is not None and (int(cells[first]), int(cells[middle])) not in allowed_edges):
            continue
        edge_count += 1
        last = receiver[middle]
        if last < 0:
            terminal_count += 1
            continue
        if allowed_edges is not None and (int(cells[middle]), int(cells[last])) not in allowed_edges:
            continue
        incoming, outgoing = points[middle] - points[first], points[last] - points[middle]
        denominator = np.linalg.norm(incoming) * np.linalg.norm(outgoing)
        if denominator <= 0:
            raise ValueError("Saved path has zero-length edge")
        angle = float(np.degrees(np.arccos(np.clip(np.dot(incoming, outgoing) / denominator, -1, 1))))
        values["confluence" if donors[middle] > 1 else "ordinary"].append(angle)
    result = {"edge_count": edge_count, "terminal_incoming_edge_count": terminal_count,
              "angle_tolerance_degrees": 1.0}
    for kind, angles in values.items():
        angles = np.asarray(angles)
        bins = np.array([0., 5., 15., 30., 45., 60., 75., 90., 105., 120., 150., 180.])
        result[kind] = {"count": len(angles), "maximum_degrees": float(angles.max()) if len(angles) else None,
                        "p95_degrees": float(np.percentile(angles, 95)) if len(angles) else None,
                        "angle_histogram": {"bin_edges_degrees": bins.tolist(),
                                            "counts": np.histogram(angles, bins=bins)[0].tolist(),
                                            "semantics": "left closed, right open; final bin includes 180 degrees"},
                        "at_least_30_degrees_count": int(np.count_nonzero(angles >= 30)),
                        "near_45_or_90_count": int(np.count_nonzero((abs(angles - 45) <= 1) | (abs(angles - 90) <= 1)))}
    return result


def frozen_anchors(sample, count=13):
    """Include the old published center view plus deterministic ID-stratified edges."""
    mesh = sample["meshes"][0]
    receiver, points, cells = (mesh[key] for key in ("receiver", "node_xz_m", "source_node_cell_ids"))
    edges = np.flatnonzero(receiver >= 0)
    midpoints = (points[edges] + points[receiver[edges]]) / 2
    meta = sample["report"]["terrain_metadata"]
    shape = sample["arrays"]["source_height_m"].shape
    center = np.array([meta["x0_m"] + (shape[1] - 1) * meta["dx_m"] / 2,
                       meta["z0_m"] + (shape[0] - 1) * meta["dz_m"] / 2])
    nearest = int(np.argmin(np.sum((midpoints - center) ** 2, axis=1)))
    ordered = np.argsort(cells[edges], kind="stable")
    choices = [nearest, *ordered[np.linspace(0, len(edges) - 1, count - 1).astype(int)].tolist()]
    choices = list(dict.fromkeys(choices))
    missing = min(count, len(edges)) - len(choices)
    if missing:
        remaining = [int(choice) for choice in ordered if int(choice) not in choices]
        choices.extend(remaining[index] for index in np.linspace(0, len(remaining) - 1, missing).astype(int))
    donors = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    anchors = []
    for choice in choices:
        first, second = int(edges[choice]), int(receiver[edges[choice]])
        delta = points[second] - points[first]
        normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
        anchors.append({"edge_cell_ids": [int(cells[first]), int(cells[second])],
                        "center_xz_m": midpoints[choice].tolist(), "normal_xz": normal.tolist(),
                        "baseline_bottom_width_m": float((mesh["width_m"][first] + mesh["width_m"][second]) / 2),
                        "confluence_adjacent": bool(donors[first] > 1 or donors[second] > 1),
                        "terminal_adjacent": bool(receiver[second] < 0),
                        "published_center_view": choice == nearest})
    return anchors


def section_metrics(distance_m, bed_m, width_m, source_m=None):
    """Describe bottom shape; a distant lower valley is not an invalid channel."""
    distance_m, bed_m = np.asarray(distance_m), np.asarray(bed_m)
    bottom = (abs(distance_m) <= width_m / 2) & np.isfinite(bed_m)
    expected = abs(distance_m) <= width_m / 2
    result = {"bottom_sample_coverage_fraction": float(bottom.sum() / max(1, expected.sum()))}
    if bottom.sum() != expected.sum() or bottom.sum() < 3:
        result["available"] = False
        return result
    result["available"] = True
    center = float(np.interp(0, distance_m, bed_m))
    shoulders = np.interp([-width_m / 2, width_m / 2], distance_m, bed_m)
    extra_depth = max(0.0, float(min(shoulders) - center))
    result.update(bottom_elevation_span_m=float(np.ptp(bed_m[bottom])),
                  center_below_lower_bottom_shoulder_m=extra_depth)
    away = bottom & (abs(distance_m) > 1e-7)
    result["maximum_sampled_bottom_rise_from_center_m_per_m"] = float(np.max(
        (bed_m[away] - center) / abs(distance_m[away])))
    result["bottom_shoulder_rise_from_center_m_per_m"] = ((shoulders - center) / (width_m / 2)).tolist()
    # Connected half-depth width distinguishes a narrow extra trench from a broad bottom.
    if extra_depth > 1e-6:
        mask = bottom & (bed_m <= center + extra_depth / 2)
        middle = int(np.argmin(abs(distance_m)))
        left = right = middle
        while left > 0 and mask[left - 1]:
            left -= 1
        while right + 1 < len(mask) and mask[right + 1]:
            right += 1
        result["center_trench_half_depth_width_ratio"] = float((distance_m[right] - distance_m[left]) / width_m)
    else:
        result["center_trench_half_depth_width_ratio"] = None
    if source_m is not None:
        source_m = np.asarray(source_m)
        nearby = (abs(distance_m) <= max(30.0, 2 * width_m)) & np.isfinite(source_m)
        low = np.flatnonzero(nearby)[np.argmin(source_m[nearby])]
        result["nearby_source_valley_offset_m"] = float(distance_m[low])
        result["source_center_above_nearby_valley_m"] = float(np.interp(0, distance_m, source_m) - source_m[low])
    return result


def local_mesh(mesh, center, half_span_m=160):
    vertices, triangles = mesh["vertices_xz_m"], mesh["triangles"]
    low = vertices[triangles[:, 0]].copy()
    high = low.copy()
    for column in (1, 2):
        np.minimum(low, vertices[triangles[:, column]], out=low)
        np.maximum(high, vertices[triangles[:, column]], out=high)
    visible = np.all(high >= center - half_span_m, axis=1) & np.all(low <= center + half_span_m, axis=1)
    triangles = triangles[visible]
    ids, inverse = np.unique(triangles, return_inverse=True)
    return {"vertices_xz_m": vertices[ids], "triangles": inverse.reshape(-1, 3),
            "source_elevation_m": mesh["source_elevation_m"][ids],
            "bed_elevation_m": mesh["bed_elevation_m"][ids]}


def sample_bed(mesh, points):
    if not len(mesh["triangles"]):
        return np.full(len(points), np.nan)
    origin = mesh["vertices_xz_m"][0]
    vertices = mesh["vertices_xz_m"] - origin
    tri = mtri.Triangulation(vertices[:, 0], vertices[:, 1], mesh["triangles"])
    query = points - origin
    return np.ma.filled(mtri.LinearTriInterpolator(tri, mesh["bed_elevation_m"])(query[:, 0], query[:, 1]), np.nan)


def empty_mesh():
    return {"source_node_cell_ids": np.empty(0, dtype=np.int64), "receiver": np.empty(0, dtype=np.int64),
            "node_xz_m": np.empty((0, 2)), "vertices_xz_m": np.empty((0, 2)),
            "triangles": np.empty((0, 3), dtype=np.int64), "bed_elevation_m": np.empty(0),
            "source_elevation_m": np.empty(0)}


def observe(sample, anchors, common_edges=None):
    mesh = sample["meshes"][0] if sample["meshes"] else empty_mesh()
    inventory = edge_inventory(mesh)
    positions = dict(zip(mesh["source_node_cell_ids"].tolist(), mesh["node_xz_m"]))
    meta = sample["report"]["terrain_metadata"]
    source = sample["arrays"]["source_height_m"]
    interpolate = RegularGridInterpolator((meta["z0_m"] + np.arange(source.shape[0]) * meta["dz_m"],
                                          meta["x0_m"] + np.arange(source.shape[1]) * meta["dx_m"]),
                                         source, bounds_error=False, fill_value=np.nan)
    sections = []
    pictures = []
    for anchor in anchors:
        center, normal = np.asarray(anchor["center_xz_m"]), np.asarray(anchor["normal_xz"])
        distances = np.unique(np.r_[np.linspace(-150., 150., 3001),
                                    np.linspace(-anchor["baseline_bottom_width_m"] / 2,
                                                anchor["baseline_bottom_width_m"] / 2, 101)])
        points = center + distances[:, None] * normal
        nearby = local_mesh(mesh, center)
        bed = sample_bed(nearby, points)
        native = interpolate(points[:, ::-1])
        record = {"anchor": anchor, "edge_retained": tuple(anchor["edge_cell_ids"]) in inventory,
                  "metrics": section_metrics(distances, bed, anchor["baseline_bottom_width_m"], native)}
        if record["edge_retained"]:
            moved_center = np.mean([positions[cell] for cell in anchor["edge_cell_ids"]], axis=0)
            record["centerline_midpoint_displacement_m"] = float(np.linalg.norm(moved_center - center))
            delta = positions[anchor["edge_cell_ids"][1]] - positions[anchor["edge_cell_ids"][0]]
            moved_normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
            moved_points = moved_center + distances[:, None] * moved_normal
            moved_bed = sample_bed(local_mesh(mesh, moved_center), moved_points)
            record["corresponding_edge_normal_metrics"] = section_metrics(
                distances, moved_bed, anchor["baseline_bottom_width_m"], interpolate(moved_points[:, ::-1]))
            record["corresponding_center_xz_m"] = moved_center.tolist()
            record["corresponding_normal_xz"] = moved_normal.tolist()
        else:
            moved_bed = np.full(len(distances), np.nan)
        sections.append(record)
        pictures.append({"mesh": nearby, "distances": distances, "bed": bed, "moved_bed": moved_bed, "source": native})
    return {"all_accepted_turns": turn_metrics(mesh),
            "common_coverage_turns": turn_metrics(mesh, common_edges) if common_edges is not None else None,
            "sections": sections}, pictures


def plot_comparison(name, anchors, before, after, output):
    for index, (anchor, old, new) in enumerate(zip(anchors, before, after)):
        figure, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
        heights = np.r_[old["mesh"]["bed_elevation_m"], new["mesh"]["bed_elevation_m"]]
        low, high = (float(heights.min()), float(heights.max())) if len(heights) else (0., 1.)
        center, normal = np.asarray(anchor["center_xz_m"]), np.asarray(anchor["normal_xz"])
        for axis, picture, title in zip(axes[:2], (old, new), ("Baseline saved bed", "Candidate saved bed")):
            mesh = picture["mesh"]
            polygons = mesh["vertices_xz_m"][mesh["triangles"]] - center
            collection = PolyCollection(polygons, array=mesh["bed_elevation_m"][mesh["triangles"]].mean(axis=1),
                                        cmap="gist_earth", clim=(low, high), edgecolors="none", rasterized=True)
            axis.add_collection(collection)
            axis.plot([-150 * normal[0], 150 * normal[0]], [-150 * normal[1], 150 * normal[1]], "k--", lw=.7)
            axis.set(xlim=(-150, 150), ylim=(150, -150), aspect="equal", title=title,
                     xlabel="X from frozen center (m)", ylabel="Z from frozen center (m)")
        axis = axes[2]
        axis.plot(old["distances"], old["source"], color="#555555", label="Original TD source")
        axis.plot(old["distances"], old["bed"], color="#ba493d", label="Baseline bed")
        axis.plot(new["distances"], new["bed"], color="#168072", label="Candidate bed")
        axis.plot(new["distances"], new["moved_bed"], color="#264d6d", linestyle=":", label="Candidate corresponding-edge normal")
        axis.axvspan(-anchor["baseline_bottom_width_m"] / 2, anchor["baseline_bottom_width_m"] / 2,
                     color="#666666", alpha=.12)
        axis.set(xlabel="Frozen normal distance (m)", ylabel="Elevation (m)", title="Same-location actual triangle section")
        axis.legend(fontsize=8)
        axis.grid(alpha=.2)
        figure.suptitle(f"{name}, baseline edge {anchor['edge_cell_ids']}, fixed center {anchor['center_xz_m']}")
        figure.savefig(output / f"{name}-anchor-{index:02d}.png", dpi=140)
        plt.close(figure)


def bind_component_to_sample(bundle, sample, registration):
    arrays, metadata = bundle["arrays"], bundle["metadata"]
    terrain = registration["terrain"]
    if (metadata["source_identity_sha256"] != terrain.identity_sha256
            or metadata["terrain_metadata"] != sample["report"]["terrain_metadata"]
            or not np.array_equal(arrays["source_height_m"], terrain.elevation_m)
            or not np.array_equal(arrays["source_valid_mask"], terrain.valid_mask)):
        raise ValueError("Component original TD terrain, coordinates or provenance differs from network sample")
    selected = set(zip(sample["arrays"]["selected_edge_source_ids"].tolist(),
                       sample["arrays"]["selected_edge_target_ids"].tolist()))
    if not edge_inventory(arrays) <= selected:
        raise ValueError("Component topology differs from the boundary-bound frozen network")
    return {"terrain_identity_sha256": terrain.identity_sha256,
            "boundary_identity_sha256": registration["metadata"]["boundary_identity_sha256"],
            "binding": "registered original TD and coordinates; component edges matched to frozen boundary-bound selected network"}


def compare_components(baseline_path, candidate_path, sample_path, output, edge_cell_ids, anchor_count=13):
    """Small counterexample entry; source/report comes from the pinned old sample."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sample = load_sample(Path(sample_path), include_mesh=False)
    source_record = sample["report"]["source_registration"]["source_metadata"]
    registration = load_generated_td_source(source_record["generation_report_path"], source_record["sample_index"],
                                             expected_report_sha256=source_record["generation_report_sha256"])
    if registration["metadata"] != sample["report"]["source_registration"]:
        raise ValueError("Network sample original TD or boundary registration differs from pinned generation source")
    if (sample["report"]["terrain_metadata"] != registration["terrain"].metadata()
            or not np.array_equal(sample["arrays"]["source_height_m"], registration["terrain"].elevation_m)):
        raise ValueError("Network sample terrain or coordinates differ from pinned original TD")
    paths = [Path(baseline_path), Path(candidate_path)]
    edge_sets = []
    for path in paths:
        with np.load(path, allow_pickle=False) as archive:
            edge_sets.append(edge_inventory({key: archive[key] for key in ("source_node_cell_ids", "receiver")}))
    common_edges = edge_sets[0] & edge_sets[1]
    pins = []
    observations, pictures = [], []
    anchors = None
    for path in paths:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        expected_identity = None
        records = [component["geometry"] for component in sample["report"].get("component_records", []) if component.get("geometry")]
        for record in records:
            if (Path(sample_path) / record["path"]).resolve() == path.resolve():
                if checksum != record["sha256"]:
                    raise ValueError("Baseline component differs from pinned network sample geometry")
                expected_identity = record["identity_sha256"]
        bundle = load_component_geometry(path, expected_sha256=checksum, expected_identity=expected_identity)
        binding = bind_component_to_sample(bundle, sample, registration)
        pins.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "metadata": bundle["metadata"], "sample_binding": binding})
        if anchors is None:
            mesh = bundle["arrays"]
            lookup = {int(cell): index for index, cell in enumerate(mesh["source_node_cell_ids"])}
            first, second = (lookup[int(cell)] for cell in edge_cell_ids)
            if mesh["receiver"][first] != second:
                raise ValueError("Requested baseline edge is not represented")
            center = (mesh["node_xz_m"][first] + mesh["node_xz_m"][second]) / 2
            delta = mesh["node_xz_m"][second] - mesh["node_xz_m"][first]
            normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
            anchors = [{"edge_cell_ids": list(edge_cell_ids), "center_xz_m": center.tolist(), "normal_xz": normal.tolist(),
                        "baseline_bottom_width_m": float((mesh["width_m"][first] + mesh["width_m"][second]) / 2)}]
            selected = frozen_anchors({**sample, "meshes": [mesh]}, anchor_count)
            anchors.extend(anchor for anchor in selected if anchor["edge_cell_ids"] != list(edge_cell_ids))
            anchors = anchors[:anchor_count]
            del mesh
        sample["meshes"] = [bundle["arrays"]]
        observation, picture = observe(sample, anchors, common_edges)
        observations.append(observation)
        pictures.append(picture)
        sample["meshes"] = []
        del bundle
        gc.collect()
    plot_comparison("component", anchors, pictures[0], pictures[1], output)
    report = {"inputs": pins, "coverage": coverage(*edge_sets), "baseline": observations[0], "candidate": observations[1],
              "evaluation_scope": "fixed same-source development counterexample component; not holdout or whole-domain validation"}
    (output / "component-shape-comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample", type=int, action="append", help="Source index; default all six")
    parser.add_argument("--anchor-count", type=int, default=13)
    parser.add_argument("--network-sample", type=Path, help="Component comparison: pinned baseline sample directory")
    parser.add_argument("--edge", type=int, nargs=2, help="Component comparison: fixed source and target cell IDs")
    args = parser.parse_args()
    if args.network_sample:
        if not args.edge:
            parser.error("component comparison requires --edge SOURCE TARGET")
        compare_components(args.baseline, args.candidate, args.network_sample, args.output, args.edge, args.anchor_count)
        return
    if args.anchor_count < 2:
        parser.error("anchor-count must be at least 2")
    if args.output.resolve() in (args.baseline.resolve(), args.candidate.resolve()):
        parser.error("Comparison output must be a separate directory")
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for index in args.sample if args.sample is not None else range(6):
        name = f"sample-{index}"
        old = load_sample(args.baseline / name)
        anchors = frozen_anchors(old, args.anchor_count)
        old_edges = edge_inventory(old["meshes"][0])
        # Read candidate node arrays only, avoiding two resident large meshes.
        candidate_report = json.loads((args.candidate / name / "report.json").read_text(encoding="utf-8"))
        pin = candidate_report.get("global_bed")
        new_edges = set()
        if pin:
            candidate_path = args.candidate / name / pin["path"]
            with np.load(candidate_path, allow_pickle=False) as archive:
                new_edges = edge_inventory({key: archive[key] for key in ("source_node_cell_ids", "receiver")})
        common = old_edges & new_edges
        old_observation, old_pictures = observe(old, anchors, common)
        old_meta = old["report"]["terrain_metadata"]
        old_config = old["report"]["config"]
        old_registration = old["report"]["source_registration"]
        old_input_pins = {"report_sha256": hashlib.sha256((old["path"] / "report.json").read_bytes()).hexdigest(),
                          "network": old["report"]["network"], "global_bed": old["report"].get("global_bed")}
        old_selection = {key: old["arrays"][key] for key in (
            "selected_edge_source_ids", "selected_edge_target_ids", "selected_edge_status")}
        old_source_digest = hashlib.sha256(old["arrays"]["source_height_m"].tobytes()).hexdigest()
        del old
        gc.collect()
        new = load_sample(args.candidate / name)
        source_equal = old_source_digest == hashlib.sha256(new["arrays"]["source_height_m"].tobytes()).hexdigest()
        coordinates_equal = all(old_meta[key] == new["report"]["terrain_metadata"][key]
                                for key in ("x0_m", "z0_m", "dx_m", "dz_m"))
        if not source_equal or not coordinates_equal:
            raise ValueError(f"{name}: comparison requires identical original terrain and coordinates")
        registration_equal = all(old_registration[key] == new["report"]["source_registration"][key]
                                 for key in ("terrain_identity_sha256", "boundary_identity_sha256", "source_sha256", "boundary"))
        if not registration_equal or old_config["min_contributing_area_m2"] != new["report"]["config"]["min_contributing_area_m2"]:
            raise ValueError(f"{name}: comparison requires identical registered source, boundary and selection area threshold")
        new_observation, new_pictures = observe(new, anchors, common)
        plot_comparison(name, anchors, old_pictures, new_pictures, args.output)
        results.append({"sample": name, "coverage": coverage(old_edges, new_edges),
                        "input_pins": {"baseline": old_input_pins,
                                       "candidate": {"report_sha256": hashlib.sha256((new["path"] / "report.json").read_bytes()).hexdigest(),
                                                     "network": new["report"]["network"], "global_bed": new["report"].get("global_bed")}},
                        "selection_and_rejection_transitions": selection_transitions(old_selection, new["arrays"]),
                        "source_gate": {"same_original_terrain": source_equal, "same_coordinates": coordinates_equal,
                                        "same_registered_source_and_boundary": registration_equal},
                        "scale_gate": {"baseline_config": old_config, "candidate_config": new["report"]["config"],
                                       "real_reference_validation": "not assessed"},
                        "boundary_gate": {"planning_domain_independence": "not assessed; finite terrain windows"},
                        "baseline": old_observation, "candidate": new_observation})
        del new, old_pictures, new_pictures
        gc.collect()
        print(f"{name}: saved shape comparison completed", flush=True)
    report = {"schema": "td-river-saved-shape-comparison-v1", "baseline": str(args.baseline.resolve()),
              "candidate": str(args.candidate.resolve()), "evaluation_set": "same six development sources; not independent holdout",
              "section_rule": "Baseline center-view edge plus source-ID stratified accepted edges; baseline positions, normals and widths frozen",
              "section_scope": "fixed sampled sections; not exhaustive whole-bed transverse certification",
              "shape_metrics_are": "descriptive comparisons, not real-river certification",
              "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "samples": results}
    (args.output / "shape-comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
