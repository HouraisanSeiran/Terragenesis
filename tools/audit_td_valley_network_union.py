"""Cold audit of declared TD coverage and canonical shared valley beds."""

import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_network_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_valley_union import load_valley_union
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID
from tools.verify_td_valley_network_union import independent_mesh, unique_ledger, shape_statistics


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "verification/td-river-network-expansion/td1024-20261008-01"


def bilinear_source(points, height, terrain_metadata):
    gx = (points[:, 0] - terrain_metadata["x0_m"]) / terrain_metadata["dx_m"]
    gz = (points[:, 1] - terrain_metadata["z0_m"]) / terrain_metadata["dz_m"]
    if np.any(gx < 0.) or np.any(gz < 0.) or np.any(gx > height.shape[1] - 1) or np.any(gz > height.shape[0] - 1):
        raise AssertionError("saved mesh leaves original source")
    col = np.minimum(np.floor(gx).astype(np.int64), height.shape[1] - 2)
    row = np.minimum(np.floor(gz).astype(np.int64), height.shape[0] - 2)
    x, z = gx - col, gz - row
    return ((1. - x) * (1. - z) * height[row, col]
            + x * (1. - z) * height[row, col + 1]
            + (1. - x) * z * height[row + 1, col]
            + x * z * height[row + 1, col + 1])


def independent_incision(product):
    a, m = product["arrays"], product["metadata"]
    points, height = a["vertices_xz_m"], a["source_height_m"]
    source = bilinear_source(points, height, m["terrain_metadata"])
    np.testing.assert_allclose(source, a["source_elevation_m"], rtol=0., atol=1e-9)
    cut = np.zeros(len(points))
    edge = 0
    for node, receiver in enumerate(a["receiver"]):
        if receiver < 0:
            continue
        start, end = a["node_xz_m"][[node, receiver]]
        direction = end - start
        fraction = np.clip((points - start) @ direction / (direction @ direction), 0., 1.)
        center = start + fraction[:, None] * direction
        center_source = bilinear_source(center, height, m["terrain_metadata"])
        lo, hi = a["profile_offsets"][edge:edge + 2]
        center_bed = np.interp(fraction, a["profile_t"][lo:hi], a["profile_center_bed_m"][lo:hi])
        depth = np.maximum(center_source - center_bed, 0.)
        half_width = ((1. - fraction) * a["width_m"][node] + fraction * a["width_m"][receiver]) / 2.
        distance = np.linalg.norm(points - center, axis=1)
        envelope = np.minimum(depth, np.maximum(0., depth + (half_width - distance) / 2.))
        cut = np.maximum(cut, envelope)
        edge += 1
    np.testing.assert_allclose(cut, a["cut_depth_m"], rtol=0., atol=1e-9)
    np.testing.assert_allclose(source - cut, a["bed_elevation_m"], rtol=0., atol=1e-9)
    if np.any(cut < 0.) or np.any(cut > m["config"]["max_cut_m"] + 1e-10):
        raise AssertionError("saved material cut exceeds declared depth")
    return dict(original_bilinear_source_verified=True, independent_max_cut_envelope_verified=True)


def audit(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest_path = directory / "acceptance.json"
    manifest_sha = file_sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_pin = manifest["source"]
    if (source_pin["sha256"] != TD_PRODUCT_SHA or source_pin["identity_sha256"] != TD_PRODUCT_ID
            or Path(source_pin["path"]).resolve() != TD_DIRECTORY / "product.npz"):
        raise AssertionError("union changed fixed TD source")
    code_paths = ("terrain_pipeline/surface_rivers/metric_valley_union.py",
                  "terrain_pipeline/surface_rivers/metric_valley_incision.py",
                  "tools/audit_td_valley_network_union.py")
    code_pins = {path: file_sha256(ROOT / path) for path in code_paths}
    disabled = (
        "terrain_pipeline.surface_rivers.metric_valley_union.build_valley_union",
        "terrain_pipeline.surface_rivers.metric_network_geometry.build_network_geometry_plan",
        "terrain_pipeline.surface_rivers.metric_channel_solver.solve_channel",
        "terrain_pipeline.surface_rivers.metric_sediment.solve_sediment",
        "terrain_pipeline.surface_rivers.metric_drainage.route_diagnostic",
    )
    with ExitStack() as stack:
        for name in disabled:
            stack.enter_context(patch(name, side_effect=AssertionError("cold audit called " + name)))
        source = load_diagnostic_product(TD_DIRECTORY / "product.npz", expected_sha256=TD_PRODUCT_SHA,
                                         expected_identity=TD_PRODUCT_ID)
        plan_pin = manifest["parent_network_plan"]
        plan = load_network_geometry_plan(PARENT / plan_pin["path"], expected_sha256=plan_pin["sha256"])
        if plan["identity_sha256"] != plan_pin["identity_sha256"]:
            raise AssertionError("union parent topology changed")
        selected = plan["arrays"]["selected_edge_source_ids"]
        receiver = plan["arrays"]["graph_receiver"]
        records = manifest["component_records"]
        np.testing.assert_array_equal(sorted(row["source_cell_id"] for row in manifest["preflight"]), selected)
        eligible = sorted(row["source_cell_id"] for row in manifest["preflight"] if row["status"] == "passed_edge_preflight")
        represented = sorted(cell for row in records.values() for cell in row["source_edge_ids"])
        np.testing.assert_array_equal(represented, eligible)
        if len(set(represented)) != len(represented):
            raise AssertionError("edge belongs to multiple components")
        if dict(Counter(row["status"] for row in records.values())) != manifest["component_status"]:
            raise AssertionError("coverage summary lost component refusals")
        accepted = sorted(cell for row in records.values() if row["status"] == "accepted_connected_component"
                          for cell in row["source_edge_ids"])
        if (manifest["accepted_global_edges"] != len(accepted)
                or manifest["declared_selected_edges"] != len(selected)
                or manifest["coverage_fraction"] != len(accepted) / len(selected)):
            raise AssertionError("accepted geometry coverage summary invalid")
        expected_names = {"component-" + key.zfill(3) + "-" + level for key, row in records.items()
                          if row["status"] == "accepted_connected_component" for level in ("coarse", "fine")}
        if set(manifest["artifacts"]) != expected_names:
            raise AssertionError("accepted component artifact coverage incomplete")
        products, cases = [], {}
        for name, pin in manifest["artifacts"].items():
            if pin["path"] != name + ".npz":
                raise AssertionError("unexpected union artifact path")
            product = load_valley_union(directory / pin["path"], expected_sha256=pin["sha256"],
                                        expected_identity=pin["identity_sha256"])
            a, m = product["arrays"], product["metadata"]
            np.testing.assert_array_equal(a["source_height_m"], source["arrays"]["elevation_m"])
            if m["source_plan_identity_sha256"] != plan["identity_sha256"]:
                raise AssertionError("component parent source plan changed")
            record = records[str(int(name.split("-")[1]))]
            np.testing.assert_array_equal(a["source_node_cell_ids"], record["source_node_ids"])
            ids = a["source_node_cell_ids"]
            np.testing.assert_array_equal(ids[a["receiver"] >= 0], record["source_edge_ids"])
            np.testing.assert_array_equal(ids[a["receiver"][a["receiver"] >= 0]], receiver[ids[a["receiver"] >= 0]])
            cases[name] = independent_incision(product) | dict(cut_volume_m3=independent_mesh(product))
            if name.endswith("-fine"):
                products.append(product)
            print(json.dumps(dict(cold_component=name, status="passed")), flush=True)
        for key, record in records.items():
            if record["status"] != "accepted_connected_component":
                if not record.get("reason"):
                    raise AssertionError("refused component lacks reason")
                continue
            name = "component-" + key.zfill(3)
            coarse, fine = [cases[name + "-" + level]["cut_volume_m3"] for level in ("coarse", "fine")]
            error = abs(coarse - fine) / max(fine, 1e-12)
            if error > .02:
                raise AssertionError("saved union exceeds fixed 2% volume refinement gate")
            np.testing.assert_allclose(error, record["spatial_refinement_relative"], rtol=0., atol=1e-12)
        ledger = unique_ledger(products)
        if ledger != manifest["unique_material_ledger"]:
            raise AssertionError("global unique material ledger changed")
        assignment = np.full(receiver.size, -1, np.int64)
        accepted_set = set(accepted)
        for cell in plan["arrays"]["graph_order_downstream_first"]:
            target = receiver[cell]
            assignment[cell] = cell if int(cell) in accepted_set else (assignment[target] if target >= 0 else -1)
        q = source["arrays"]["local_q_m3_s"].reshape(len(source["arrays"]["time_seconds"]) - 1, -1)
        dt = np.diff(source["arrays"]["time_seconds"])
        volume = {"assigned_volume_m3": float(np.sum(q[:, assignment >= 0] * dt[:, None])),
                  "unresolved_or_outside_coverage_volume_m3": float(np.sum(q[:, assignment < 0] * dt[:, None]))}
        if volume != manifest["unique_native_local_source_accounting"]:
            raise AssertionError("native forcing coverage changed")
    if file_sha256(manifest_path) != manifest_sha or any(file_sha256(ROOT / path) != sha for path, sha in code_pins.items()):
        raise AssertionError("cold audit dependencies changed during run")
    report = dict(status="passed_candidate_global_union_cold", source_manifest_sha256=manifest_sha,
                  code_sha256=code_pins, disabled_entrypoints=disabled, cases=cases,
                  selected_edges=len(selected), accepted_edges=len(accepted), coverage_fraction=len(accepted)/len(selected),
                  unique_material_ledger=ledger, unique_native_local_source_accounting=volume,
                  all_preflight_and_component_refusals_preserved=True,
                  geometry_verified=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    publish_bytes(output / "cold-audit.json", json.dumps(report, indent=2, allow_nan=False).encode())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input, args.output)
    print(json.dumps({key: result[key] for key in ("status", "selected_edges", "accepted_edges", "coverage_fraction")}))
