"""Necessary transverse cut bounds on local fan4 vertices, without mesh or LP."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.channel_geometry import _metric_channel_geometry_sample as _sample
from terrain_pipeline.surface_rivers.metric_td_generated_source import load_generated_td_source
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import _continuous_profile, _local_route_crossings
from terrain_pipeline.channel_geometry import enforce_turn_ceiling, initialize_centerline, shape_centerline, turn_ceiling, turn_summary
from terrain_pipeline.channel_geometry import _anchors
from terrain_pipeline.channel_geometry import repair_budget_centerline
from tools.generate_td_terrain_rivers import ROOT, DEFAULT_REPORT
from tools.repair_td_river_shapes import peak_process_memory_bytes


from terrain_pipeline.channel_geometry import local_vertices, necessary_bounds, controlling_upstream_nodes, evaluate_necessary_budget, budget_hotspot_targets


def budget_evaluation(points, receiver, widths, profile, terrain, ids, focus=None):
    return evaluate_necessary_budget(points, receiver, widths, profile, terrain, ids,
                                     1., 4., .02, focus)


def upstream_profile_witness(points, receiver, depths, profile, ids, node):
    donors = [[] for _ in points]
    for source, target in enumerate(receiver):
        if target >= 0:
            donors[target].append(source)
    distance = {node: 0.}
    pending = [node]
    for downstream in pending:
        for upstream in donors[downstream]:
            distance[upstream] = distance[downstream] + float(np.linalg.norm(points[upstream] - points[downstream]))
            pending.append(upstream)
    edge_order = {int(source): edge for edge, source in enumerate(np.flatnonzero(receiver >= 0))}
    best = None
    for source in pending:
        if source == node or source not in edge_order:
            continue
        target = receiver[source]
        edge = edge_order[source]
        start, end = profile[0][edge:edge + 2]
        t, heights = profile[1][start:end], profile[2][start:end]
        depth = (1. - t) * depths[source] + t * depths[target]
        downstream_distance = distance[target] + (1. - t) * np.linalg.norm(points[target] - points[source])
        upper = heights - depth - 1e-5 * downstream_distance
        knot = int(np.argmin(upper))
        if best is None or upper[knot] < best["propagated_highest_center_bed_m"]:
            best = dict(source_node_cell_id=int(ids[source]), target_node_cell_id=int(ids[target]),
                        controlling_knot_t=float(t[knot]),
                        controlling_xz_m=(points[source] + t[knot] * (points[target] - points[source])).tolist(),
                        source_height_m=float(heights[knot]), design_depth_m=float(depth[knot]),
                        downstream_distance_m=float(downstream_distance[knot]),
                        minimum_slope_drop_m=float(1e-5 * downstream_distance[knot]),
                        propagated_highest_center_bed_m=float(upper[knot]))
    return dict(node_cell_id=int(ids[node]), node_xz_m=points[node].tolist(),
                fixed_anchor=bool(_anchors(receiver)[node]), upstream_node_count=len(pending) - 1,
                controlling_upstream=best)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "verification/td-terrain-generated-rivers/generated-20261011-04")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--sample", type=int, required=True, choices=range(6))
    parser.add_argument("--component", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--paths-from", type=Path)
    parser.add_argument("--repair-hotspots", action="store_true")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((args.baseline / "manifest.json").read_text(encoding="utf-8"))
    if file_sha256(args.report) != manifest["generation_report_sha256"]:
        raise ValueError("frozen generation report differs")
    pin = next(s for s in manifest["samples"] if s["sample_index"] == args.sample)
    report_path = args.baseline / pin["report_path"]
    if file_sha256(report_path) != pin["report_sha256"]:
        raise ValueError("baseline report differs")
    old = json.loads(report_path.read_text(encoding="utf-8"))
    registration = load_generated_td_source(args.report, args.sample)
    terrain = registration["terrain"]
    if old["source_registration"]["terrain_identity_sha256"] != terrain.identity_sha256:
        raise ValueError("baseline terrain differs")
    if old["source_registration"]["boundary_identity_sha256"] != registration["boundary"].identity_sha256:
        raise ValueError("baseline boundary differs")
    network_path = args.baseline / f"sample-{args.sample}" / old["network"]["path"]
    if file_sha256(network_path) != old["network"]["sha256"]:
        raise ValueError("baseline network differs")
    with np.load(network_path, allow_pickle=False) as archive:
        selected = archive["selected_component_id"] == args.component
        sources = archive["selected_edge_source_ids"][selected]
        targets = archive["selected_edge_target_ids"][selected]
        ids = np.unique(np.r_[sources, targets])
        widths, depths = archive["width_m"][ids], archive["base_depth_m"][ids]
    mapping = {int(cell): index for index, cell in enumerate(ids)}
    receiver = np.full(len(ids), -1, np.int64)
    for source, target in zip(sources, targets):
        receiver[mapping[int(source)]] = mapping[int(target)]
    cols = terrain.elevation_m.shape[1]
    raw = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m,
                           terrain.z0_m + ids // cols * terrain.dz_m))
    validate = lambda candidate: _local_route_crossings(candidate, receiver)
    certify = lambda candidate: _continuous_profile(candidate, receiver, depths, terrain, 4., 1.)
    if args.paths_from is not None:
        prior = json.loads((args.paths_from / "report.json").read_text(encoding="utf-8"))
        cached_path = args.paths_from / prior["paths"]["path"]
        if (file_sha256(cached_path) != prior["paths"]["sha256"]
                or prior["network_sha256"] != old["network"]["sha256"]):
            raise ValueError("cached paths differ from pinned baseline topology")
        with np.load(cached_path, allow_pickle=False) as archive:
            if (not np.array_equal(ids, archive["source_node_cell_ids"])
                    or not np.array_equal(receiver, archive["receiver"])):
                raise ValueError("cached path topology differs")
            legacy, final = archive["legacy_node_xz_m"], archive["final_node_xz_m"]
        policy = prior["centerline_policy"]
    else:
        legacy = initialize_centerline(raw, receiver, terrain, validate=validate, certify=certify)
        final, policy = shape_centerline(raw, receiver, terrain, iterations=24, corridor_m=30.,
                                        validate=validate, certify=certify)
    repaired = None
    repair_policy = None
    if args.repair_hotspots:
        # Same entry-independent ceiling as the producer: derived from the declared analytic
        # bound and this component's own deterministic initializer, never from a saved path.
        repair_turn_ceiling = turn_ceiling(legacy, receiver)
        source_height = _sample(terrain.elevation_m, raw, terrain)[0]
        def validate_repair(candidate):
            if np.any(np.linalg.norm(candidate - raw, axis=1) > 30. + 1e-8):
                raise ValueError("original 30m corridor")
            if not np.array_equal(candidate[_anchors(receiver)], raw[_anchors(receiver)]):
                raise ValueError("fixed anchor moved")
            sampled, _ = _sample(terrain.elevation_m, candidate, terrain)
            if np.any(sampled > source_height + .5 + 1e-9):
                raise ValueError("original source rise")
            # Same entry-independent turn ceiling as the producer; no saved-reference veto here.
            enforce_turn_ceiling(candidate, receiver, repair_turn_ceiling)
            validate(candidate)
        repaired, repaired_profile, repair_policy = repair_budget_centerline(
            final, receiver, certify(final)[0], max_cut_m=4.,
            evaluate=lambda candidate, profile, focus: budget_evaluation(candidate, receiver, widths, profile, terrain, ids, focus),
            validate=validate_repair, certify=lambda candidate: certify(candidate)[0],
            causal_nodes=lambda candidate, profile, evaluation: controlling_upstream_nodes(
                candidate, receiver, depths, profile,
                budget_hotspot_targets(evaluation), 1e-5),
            source_height=lambda point: _sample(terrain.elevation_m, np.array([point]), terrain)[0][0])
    cases = {}
    selections = [("raw", raw), ("legacy", legacy), ("final", final)]
    if repaired is not None:
        selections.append(("repaired", repaired))
    for name, points in selections:
        profile, _ = certify(points)
        cases[name] = dict(turns=turn_summary(points, receiver),
                           transverse_necessary_bounds=necessary_bounds(points, receiver, widths, profile, terrain, ids),
                           worst_node_upstream_witness=upstream_profile_witness(points, receiver, depths, profile, ids,
                                                                               int(np.flatnonzero(ids == 189397)[0])) if 189397 in ids else None)
        print(json.dumps(dict(case=name, completed=True, elapsed_seconds=time.perf_counter() - started)), flush=True)
    path = args.output / "paths.npz"
    np.savez_compressed(path, source_node_cell_ids=ids, receiver=receiver,
                        raw_node_xz_m=raw, legacy_node_xz_m=legacy, final_node_xz_m=final,
                        repaired_node_xz_m=repaired if repaired is not None else final)
    report = dict(schema="td-transverse-necessary-budget-diagnosis-v1", sample=args.sample,
                  component=args.component, edge_count=len(sources), cases=cases, centerline_policy=policy,
                  hotspot_repair_policy=repair_policy,
                  source_identity_sha256=terrain.identity_sha256, baseline_report_sha256=pin["report_sha256"],
                  network_sha256=old["network"]["sha256"], paths=dict(path=path.name, sha256=file_sha256(path)),
                  elapsed_seconds=time.perf_counter() - started, peak_process_working_set_bytes=peak_process_memory_bytes(),
                  entrypoint_sha256=file_sha256(Path(__file__)),
                  interpretation="necessary individual source-minus-highest-profile-bed bound at local fan4 vertex locations; violations prove >4m under the current path/profile contract before multi-edge closure, not impossibility of alternative physical paths; absence does not certify feasibility",
                  count_semantics="constraint tests; repeated vertices across edges retained; no excavation volume or global mesh",
                  assumptions=dict(fine_spacing_m=1., maximum_cut_m=4., transverse_bottom_slope_m_per_m=.02,
                                   guard_m=float(np.sqrt(2.)), bank_horizontal_per_vertical=2.))
    publish_bytes(args.output / "report.json", json.dumps(report, indent=2, allow_nan=False).encode())


if __name__ == "__main__":
    main()
