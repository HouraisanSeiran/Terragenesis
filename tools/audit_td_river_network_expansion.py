"""Cold whole-domain coverage and local patch audit with producers disabled."""

import argparse
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import load_channel_geometry
from terrain_pipeline.surface_rivers.metric_network_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from tools.audit_td_river_geometry_sediment import independent_continuous_bed, independent_source_and_cut
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID, mesh_evidence


def audit(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((directory / "acceptance.json").read_text(encoding="utf-8"))
    pin = manifest["plan"]
    if (manifest["source"]["sha256"] != TD_PRODUCT_SHA
            or manifest["source"]["identity_sha256"] != TD_PRODUCT_ID
            or Path(manifest["source"]["path"]).resolve() != TD_DIRECTORY / "product.npz"):
        raise AssertionError("network catalogue source differs from fixed original TD pins")
    disabled = (
        "terrain_pipeline.surface_rivers.metric_network_geometry.build_network_geometry_plan",
        "terrain_pipeline.surface_rivers.metric_channel_geometry.build_channel_geometry",
        "terrain_pipeline.surface_rivers.metric_channel_solver.solve_channel",
        "terrain_pipeline.surface_rivers.metric_sediment.solve_sediment",
        "terrain_pipeline.surface_rivers.metric_drainage.route_diagnostic",
    )
    active = []
    try:
        for name in disabled:
            handle = patch(name, side_effect=AssertionError("cold audit called " + name))
            handle.start()
            active.append(handle)
        plan = load_network_geometry_plan(directory / pin["path"], expected_sha256=pin["sha256"])
        if plan["identity_sha256"] != pin["identity_sha256"]:
            raise AssertionError("network plan external identity mismatch")
        source = load_diagnostic_product(TD_DIRECTORY / "product.npz", expected_sha256=TD_PRODUCT_SHA,
                                         expected_identity=TD_PRODUCT_ID)
        a, original = plan["arrays"], source["arrays"]
        np.testing.assert_array_equal(a["source_elevation_m"], original["elevation_m"])
        np.testing.assert_array_equal(a["graph_receiver"], original["graph_receiver"])
        rec = a["graph_receiver"]
        area = np.zeros(rec.size)
        tm = plan["metadata"]["terrain_metadata"]
        area[a["source_valid_mask"].ravel()] = tm["dx_m"] * tm["dz_m"]
        # Independent accumulation adds each donor once in height/order rank.
        rank = np.empty(rec.size, np.int64)
        rank[a["graph_order_downstream_first"]] = np.arange(len(a["graph_order_downstream_first"]))
        for cell in np.argsort(rank)[::-1]:
            if rec[cell] >= 0:
                area[rec[cell]] += area[cell]
        np.testing.assert_array_equal(area, a["contributing_area_m2"])
        selected = np.flatnonzero((area >= manifest["selected_area_threshold_km2"] * 1e6) & (rec >= 0))
        np.testing.assert_array_equal(selected, a["selected_edge_source_ids"])
        np.testing.assert_array_equal(np.sort(a["patch_edge_source_ids"]), selected)
        np.testing.assert_array_equal(np.sort([row["source_cell_id"] for row in manifest["preflight"]]), selected)
        np.testing.assert_array_equal(np.sort([cell for row in manifest["patch_records"] for cell in row["owned_edge_source_ids"]]), selected)
        patch_status = dict(Counter(row["status"] for row in manifest["patch_records"]))
        if patch_status != manifest["patch_status"]:
            raise AssertionError("patch status summary loses rejected or unresolved coverage")
        cases = {}
        nodes = {}
        conflicting_shared_nodes = []
        for name, pin in manifest["artifacts"].items():
            if pin["path"] != name + ".npz":
                raise AssertionError("unexpected patch artifact path")
            product = load_channel_geometry(directory / pin["path"], expected_sha256=pin["sha256"],
                                            expected_identity=pin["identity_sha256"])
            cases[name] = mesh_evidence(product) | independent_source_and_cut(product) | independent_continuous_bed(product)
            pa = product["arrays"]
            np.testing.assert_array_equal(pa["source_height_m"], original["elevation_m"])
            for cell, xz in zip(pa["source_node_cell_ids"], pa["node_xz_m"]):
                key = (int(cell), name.rsplit("-", 1)[1])
                if key in nodes and not np.array_equal(nodes[key], xz):
                    conflicting_shared_nodes.append(key)
                nodes[key] = xz
            print(json.dumps({"cold_patch": name, "status": "passed"}), flush=True)
        if conflicting_shared_nodes:
            raise AssertionError("patch shared XZ anchors conflict")
        report = dict(schema="td-network-expansion-cold-v1", status="passed_candidate_scope",
                      disabled_entrypoints=disabled, selected_edges=len(selected),
                      geometry_artifacts=len(cases), cases=cases,
                      selected_edges_owned_exactly_once=True,
                      original_native_area_verified=True,
                      shared_node_xz_consistent=True,
                      cross_patch_bed_ports_verified=False,
                      global_material_volume_verified=False,
                      source_unresolved_preserved=True,
                      geometry_verified=False, hydraulic_ready=False,
                      natural_outlet_verified=False, publishable=False)
        publish_bytes(output / "cold-audit.json", json.dumps(report, indent=2, allow_nan=False).encode())
        return report
    finally:
        for handle in reversed(active):
            handle.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.input, args.output)
    print(json.dumps({key: report[key] for key in ("status", "selected_edges", "geometry_artifacts")}))


if __name__ == "__main__":
    main()
