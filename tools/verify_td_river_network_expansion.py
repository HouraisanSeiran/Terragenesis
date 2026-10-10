"""Whole-source selection, continuous-bed preflight and bounded patch verification."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import (
    GeometryConfig, _footprint, _route_slope, build_channel_geometry, save_channel_geometry,
)
from terrain_pipeline.surface_rivers.metric_contracts import RoutingGraph
from terrain_pipeline.surface_rivers.metric_network_geometry import (
    NetworkGeometryConfig, build_network_geometry_plan, save_network_geometry_plan,
)
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from tools.verify_td_river_geometry import (
    TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID, terrain_from_product, mesh_evidence,
)


def verify(output, *, min_area_km2=2., max_geometry_patches=256):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    source = load_diagnostic_product(TD_DIRECTORY / "product.npz", expected_sha256=TD_PRODUCT_SHA,
                                     expected_identity=TD_PRODUCT_ID)
    a, m = source["arrays"], source["metadata"]
    terrain = terrain_from_product(source)
    graph = RoutingGraph(**{name: a["graph_" + name] for name in (
        "receiver", "order_downstream_first", "valid_mask", "edge_length_m",
        "edge_slope", "outlet_kind", "lake_id")},
        terrain_identity_sha256=terrain.identity_sha256,
        boundary_identity_sha256=m["boundary_identity_sha256"], policy=m["routing_policy"])
    plan = build_network_geometry_plan(terrain, graph, NetworkGeometryConfig(
        min_contributing_area_m2=min_area_km2 * 1e6, max_patch_edges=4))
    plan_path = output / "network-plan.npz"
    save_network_geometry_plan(plan_path, plan)
    pa = plan["arrays"]
    ids = pa["selected_edge_source_ids"]
    owner = pa["terminal_owner"].reshape(terrain.elevation_m.shape)
    corridor = np.ones(terrain.elevation_m.shape, bool)
    lake = np.zeros_like(corridor)
    outcomes = {}
    for cell in ids:
        target = int(graph.receiver[cell])
        points = np.asarray([terrain.world_xz(int(cell)), terrain.world_xz(target)])
        rec = np.array([1, -1], np.int64)
        # Downstream sections depend on the same global area/model even if not
        # selected as source edges themselves (e.g. a lake terminal).
        area = pa["contributing_area_m2"][[cell, target]]
        design_q = area / 1000. / 3600.
        width = np.maximum(6., 4. * np.sqrt(design_q))
        depth = np.maximum(.25, .2 * np.cbrt(design_q))
        try:
            _route_slope(points, rec, terrain)
            _footprint(points, rec, width, depth, terrain, owner, corridor, lake,
                       owner.ravel()[[cell, target]], .5)
            outcomes[int(cell)] = {"status": "passed_original_preflight"}
        except ValueError as error:
            outcomes[int(cell)] = {"status": "refused", "reason": str(error)}
    artifacts, patch_records = {}, []
    owned_accepted_edges = []
    for patch_index, (lo, hi) in enumerate(zip(pa["patch_offsets"][:-1], pa["patch_offsets"][1:])):
        edges = pa["patch_edge_source_ids"][lo:hi]
        record = {"patch_index": patch_index, "owned_edge_source_ids": edges.tolist()}
        failures = [int(cell) for cell in edges if outcomes[int(cell)]["status"] == "refused"]
        if failures:
            record.update(status="refused_preflight", failed_source_ids=failures)
            patch_records.append(record)
            continue
        if len(artifacts) >= max_geometry_patches * 2:
            record.update(status="unresolved_resource_budget")
            patch_records.append(record)
            continue
        cells = np.r_[edges, graph.receiver[edges[-1]]].astype(np.int64)
        receiver = np.r_[np.arange(1, len(cells)), -1].astype(np.int64)
        area = pa["contributing_area_m2"][cells]
        q = area / 1000. / 3600.
        width, depth = np.maximum(6., 4. * np.sqrt(q)), np.maximum(.25, .2 * np.cbrt(q))
        # All source coordinates are locked during global patch verification.
        # No patch independently moves a shared node into a different position.
        options = dict(width_m=width, depth_m=depth, owner_grid=owner,
                       corridor_mask=corridor, lake_mask=lake,
                       anchor_mask=np.ones(len(cells), bool))
        try:
            coarse = build_channel_geometry(terrain, cells, receiver,
                config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0), **options)
            fine = build_channel_geometry(terrain, cells, receiver,
                config=GeometryConfig(fine_spacing_m=.25, smoothing_iterations=0), **options)
            cv, fv = mesh_evidence(coarse)["represented_cut_volume_m3"], mesh_evidence(fine)["represented_cut_volume_m3"]
            difference = abs(cv - fv) / max(fv, 1e-12)
            if difference > .02:
                raise ValueError("spatial cut volume refinement exceeds fixed 2% gate")
            for label, product in (("coarse", coarse), ("fine", fine)):
                name = "patch-" + str(patch_index).zfill(4) + "-" + label
                path = output / (name + ".npz")
                save_channel_geometry(path, product)
                artifacts[name] = dict(path=path.name, sha256=file_sha256(path),
                                       identity_sha256=product["identity_sha256"])
            record.update(status="accepted_local_patch", cut_volume_m3=fv,
                          spatial_refinement_relative=difference,
                          cross_patch_ports_verified=False,
                          globally_unique_material_ledger_verified=False)
            owned_accepted_edges.extend(edges.tolist())
        except ValueError as error:
            record.update(status="refused_geometry", reason=str(error))
        patch_records.append(record)
        print(json.dumps({"patch": patch_index, "status": record["status"]}), flush=True)
    closure = []
    for terminal in np.unique(pa["terminal_owner"][ids]):
        closure.append(dict(cell_id=int(terminal), kind=str(graph.outlet_kind[terminal]),
                            contributing_area_m2=float(pa["contributing_area_m2"][terminal]),
                            natural_geometry_connection_verified=False))
    report = dict(schema="td-network-expansion-verification-v1",
        status="candidate_incomplete_network", source={"path": str(TD_DIRECTORY / "product.npz"),
            "sha256": TD_PRODUCT_SHA, "identity_sha256": TD_PRODUCT_ID},
        plan=dict(path=plan_path.name, sha256=file_sha256(plan_path), identity_sha256=plan["identity_sha256"]),
        selected_edges=len(ids), patches=len(patch_records), selected_area_threshold_km2=min_area_km2,
        preflight_status=dict(Counter(row["status"] for row in outcomes.values())),
        preflight_reasons=dict(Counter(row["reason"] for row in outcomes.values() if "reason" in row)),
        patch_status=dict(Counter(row["status"] for row in patch_records)),
        local_geometry_accepted_edges=len(owned_accepted_edges),
        local_geometry_coverage_fraction=len(owned_accepted_edges) / max(len(ids), 1),
        preflight=[dict(source_cell_id=cell, **row) for cell, row in outcomes.items()],
        patch_records=patch_records, downstream_closures=closure, artifacts=artifacts,
        elapsed_seconds=time.monotonic()-started, geometry_verified=False,
        hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
        limitations=["native_D8_inside_cell_uphill_requires_rerouting_or_basin_classification",
                     "selected_area_threshold_is_declared_scenario_not_full_source_channel_coverage",
                     "local_patches_not_assembled_global_bed_or_shared_cross_patch_ports",
                     "no_geometry_on_filled_platforms", "no_implicit_lake_stage_or_terminal_water"])
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2, allow_nan=False).encode())
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for axis in axes:
        axis.imshow(terrain.elevation_m, cmap="terrain", origin="upper")
    for cell in ids:
        target = int(graph.receiver[cell])
        cols = terrain.elevation_m.shape[1]
        xs, zs = [cell % cols, target % cols], [cell // cols, target // cols]
        color = "cyan" if outcomes[int(cell)]["status"] == "passed_original_preflight" else "red"
        axes[0].plot(xs, zs, color=color, linewidth=.6)
        axes[1].plot(xs, zs, color="cyan" if int(cell) in owned_accepted_edges else "red", linewidth=.6)
    axes[0].set_title("Whole TD selection | cyan preflight / red refused")
    axes[1].set_title("Cyan local bed accepted | red incomplete | no global certificate")
    fig.tight_layout()
    fig.savefig(output / "network-coverage-preview.png", dpi=150)
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-area-km2", type=float, default=2.)
    parser.add_argument("--max-geometry-patches", type=int, default=256)
    args = parser.parse_args()
    result = verify(args.output, min_area_km2=args.min_area_km2,
                    max_geometry_patches=args.max_geometry_patches)
    print(json.dumps({key: result[key] for key in ("status", "selected_edges", "patches", "patch_status", "local_geometry_coverage_fraction")}))


if __name__ == "__main__":
    main()
