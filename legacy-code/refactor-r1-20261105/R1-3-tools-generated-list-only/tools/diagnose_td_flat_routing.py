"""Compare flat routing policies without changing frozen acceptance rules."""

import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_drainage import route_diagnostic, accumulate_local_discharge
from terrain_pipeline.surface_rivers.metric_naturalness_audit import channel_graph_observations
from terrain_pipeline.surface_rivers.metric_distribution_calibration import evaluate_distribution
from tools.verify_td_natural_river_baseline import boundary_for


def run(source_path, reference_path, windows, output):
    source_path, reference_path, output = Path(source_path), Path(reference_path), Path(output)
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    with np.load(source_path, allow_pickle=False) as archive:
        height = archive["elevation"].astype(np.float64)
        metadata = json.loads(str(archive["metadata"].item()))
    cases = []
    for row, column in windows:
        h = height[row:row + 144:3, column:column + 144:3]
        relief = float(np.ptp(np.rint(h)))
        condition = "low_relief" if relief < 50. else "moderate_relief" if relief < 250. else "high_relief"
        outputs = []
        graphs = {}
        for projection in ("raw_continuous", "one_meter"):
            bed = h if projection == "raw_continuous" else np.rint(h)
            terrain = TerrainGrid(bed, np.isfinite(bed), 0., 0., 90., 90., "generated_terrain", "routing-probe", file_sha256(source_path))
            for strategy in ("hop_count", "metric_distance"):
                graph = route_diagnostic(terrain, boundary_for(terrain, "unknown_boundary"), flat_distance_strategy=strategy)
                area = accumulate_local_discharge(graph, terrain.valid_mask * terrain.cell_area_m2)
                observations = channel_graph_observations(terrain, graph, area["routed_q_m3_s"], minimum_area_m2=100000.)
                frozen = reference["calibrations"].get(condition)
                samples = {name: observations[name]["samples"] for name in frozen["reference_samples"]} if frozen else None
                evaluation = evaluate_distribution(samples, frozen, conditions_match=True) if samples and all(len(v) >= 2 for v in samples.values()) else None
                edge = graph.receiver >= 0
                outputs.append({"projection": projection, "strategy": strategy,
                    "channel_node_count": observations.get("channel_support", {}).get("selected_node_count"),
                    "flat_edge_fraction": float((graph.edge_slope[edge] == 0.).mean()),
                    "curvature_zero_fraction": float((np.asarray(observations["curvature_rad_per_m"]["samples"]) == 0.).mean()),
                    "distribution_against_old_reference_context_only": evaluation,
                    "reference_semantics": "frozen_original_hop_one_meter; alternate_policy_is_not_formal_acceptance",
                    "area_residual_m2": area["residual_m3_s"]})
                graphs[projection + ":" + strategy] = graph.receiver
        cases.append({"window_zx": [row, column], "relief_class": condition, "relief_m": relief,
            "policy_changed_receiver_cells": int(np.count_nonzero(graphs["one_meter:hop_count"] != graphs["one_meter:metric_distance"])),
            "projection_changed_receiver_cells": int(np.count_nonzero(graphs["one_meter:hop_count"] != graphs["raw_continuous:hop_count"])),
            "observations": outputs})
    result = {"schema": "flat-routing-diagnosis-v1", "source_sha256": file_sha256(source_path),
              "source_metadata": metadata, "reference_sha256": file_sha256(reference_path), "cases": cases}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--row", type=int, default=0)
    parser.add_argument("--column", type=int, default=0)
    args = parser.parse_args()
    run(args.source, args.reference, [(args.row, args.column)], args.output)
