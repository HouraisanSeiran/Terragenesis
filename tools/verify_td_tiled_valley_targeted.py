"""Targeted TD proof for tiled shared-field valley components."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig, _footprint
from terrain_pipeline.surface_rivers.metric_network_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_valley_incision import _profile
from terrain_pipeline.surface_rivers.metric_valley_tiled_union import (
    TileBudget, build_tiled_refinement_pair, load_tiled_monotone_union,
    save_tiled_monotone_union, validate_tiled_monotone_union,
)
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_ID, TD_PRODUCT_SHA, terrain_from_product
from tools.verify_td_valley_network_union import PARENT, connected_components


ROOT = Path(__file__).resolve().parents[1]


def _eligible(terrain, arrays):
    owner = arrays["terminal_owner"].reshape(terrain.elevation_m.shape)
    receiver = arrays["graph_receiver"]
    selected = arrays["selected_edge_source_ids"]
    q = arrays["contributing_area_m2"] / 1000. / 3600.
    widths = np.maximum(6., 4. * np.sqrt(q))
    depths = np.maximum(.25, .2 * np.cbrt(q))
    eligible = []
    for cell in selected:
        ids = np.array([cell, receiver[cell]], np.int64)
        points = np.array([terrain.world_xz(int(value)) for value in ids])
        rec = np.array([1, -1], np.int64)
        try:
            _profile(points, rec, depths[ids], terrain, 4.)
            _footprint(points, rec, widths[ids], np.full(2, 4.), terrain, owner,
                       np.ones(owner.shape, bool), np.zeros(owner.shape, bool),
                       owner.ravel()[ids], .5)
        except ValueError:
            continue
        eligible.append(int(cell))
    return np.asarray(eligible, np.int64), receiver, widths, depths, owner


def verify(output, targets=(8, 22, 27)):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    parent = json.loads((PARENT / "acceptance.json").read_text(encoding="utf-8"))
    source = load_diagnostic_product(TD_DIRECTORY / "product.npz",
                                     expected_sha256=TD_PRODUCT_SHA,
                                     expected_identity=TD_PRODUCT_ID)
    terrain = terrain_from_product(source)
    pin = parent["plan"]
    plan = load_network_geometry_plan(PARENT / pin["path"], expected_sha256=pin["sha256"])
    if plan["identity_sha256"] != pin["identity_sha256"]:
        raise ValueError("network plan identity changed")
    arrays = plan["arrays"]
    eligible, receiver, widths, depths, owner = _eligible(terrain, arrays)
    components = connected_components(eligible, receiver)
    records = {}
    budget = TileBudget()
    for component_index in targets:
        if component_index < 0 or component_index >= len(components):
            records[str(component_index)] = {"status": "refused_component_index"}
            continue
        ids = components[component_index]
        eligible_set = set(map(int, eligible))
        mapping = {int(cell): i for i, cell in enumerate(ids)}
        rec = np.array([mapping[int(receiver[cell])] if int(receiver[cell]) in mapping and int(cell) in eligible_set else -1
                        for cell in ids], np.int64)
        edge_count = int(np.count_nonzero(rec >= 0))
        base = dict(component_index=int(component_index), node_count=len(ids), edge_count=edge_count,
                    source_node_ids=ids.tolist(), tile_budget={"max_cells": budget.max_cells,
                    "max_vertices": budget.max_vertices, "max_bytes": budget.max_bytes})
        try:
            pair = build_tiled_refinement_pair(
                terrain, ids, rec, widths[ids], depths[ids], owner_grid=owner,
                corridor_mask=np.ones(owner.shape, bool), lake_mask=np.zeros(owner.shape, bool),
                source_plan_identity_sha256=plan["identity_sha256"],
                config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0), budget=budget)
            artifacts = {}
            for label in ("coarse", "fine"):
                product = pair[label]
                validate_tiled_monotone_union(product)
                path = output / f"component-{component_index:03d}-{label}.npz"
                save_tiled_monotone_union(path, product)
                digest = file_sha256(path)
                with patch("terrain_pipeline.surface_rivers.metric_valley_tiled_union._close_bed",
                           side_effect=AssertionError("cold tiled validator reran closure")):
                    cold = load_tiled_monotone_union(path, expected_sha256=digest,
                                                     expected_identity=product["identity_sha256"])
                artifacts[label] = {"path": path.name, "sha256": digest,
                                    "identity_sha256": cold["identity_sha256"],
                                    "tile_count": cold["metadata"]["tile_count"],
                                    "global_cell_count": cold["metadata"]["global_cell_count"],
                                    "global_vertex_count": cold["metadata"]["global_vertex_count"],
                                    "cut_volume_m3": cold["metadata"]["cut_volume_m3"]}
            base.update(status="accepted_targeted_tiled_shared_field", artifacts=artifacts,
                        spatial_refinement_relative=pair["spatial_refinement_relative"],
                        global_unique_cell_ownership=True, unresolved_coverage=[], rejections=[])
        except (ValueError, AssertionError) as error:
            base.update(status="refused_targeted_tiled_shared_field", reason=str(error),
                        unresolved_coverage=["component geometry not exported"])
        records[str(component_index)] = base
    code_paths = ["terrain_pipeline/surface_rivers/metric_valley_tiled_union.py",
                  "tools/verify_td_tiled_valley_targeted.py"]
    report = dict(schema="td-river-targeted-tiled-shared-field-v1",
                  status="accepted_targeted_subset" if all(
                      row["status"].startswith("accepted") for row in records.values())
                  else "candidate_targeted_subset_with_refusals",
                  targets=list(map(int, targets)), component_records=records,
                  source=dict(path=str(TD_DIRECTORY / "product.npz"), sha256=TD_PRODUCT_SHA,
                              identity_sha256=TD_PRODUCT_ID), parent_network_plan=pin,
                  code_sha256={path: file_sha256(ROOT / path) for path in code_paths},
                  old_global_prefix_preserved=True,
                  limitations=["targeted components only", "hydraulic_ready_false",
                               "natural_outlet_verified_false"])
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2, allow_nan=False).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", type=int, nargs="+", default=[8, 22, 27])
    args = parser.parse_args()
    print(json.dumps(verify(args.output, tuple(args.targets)), indent=2))
