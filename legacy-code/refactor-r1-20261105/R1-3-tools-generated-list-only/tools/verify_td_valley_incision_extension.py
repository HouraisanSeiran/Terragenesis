"""Enumerate every original-bed uphill edge against the new bounded incision recipe."""

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig
from terrain_pipeline.surface_rivers.metric_network_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_valley_incision import (
    build_valley_incision, load_valley_incision, save_valley_incision,
)
from tools.verify_td_river_geometry import (
    TD_DIRECTORY, TD_PRODUCT_ID, TD_PRODUCT_SHA, terrain_from_product,
)


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "verification/td-river-network-expansion/td1024-20261008-01"


def verify(output):
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
        raise ValueError("parent network plan identity changed")
    arrays = plan["arrays"]
    owner = arrays["terminal_owner"].reshape(terrain.elevation_m.shape)
    q = arrays["contributing_area_m2"] / 1000. / 3600.
    options = dict(owner_grid=owner, corridor_mask=np.ones(owner.shape, bool),
                   lake_mask=np.zeros(owner.shape, bool))
    outcomes = []
    representative = None
    expected = [row for row in parent["preflight"]
                if row.get("reason") == "candidate has uphill original-bed derivative"]
    for index, row in enumerate(expected, 1):
        start = row["source_cell_id"]
        target = int(source["arrays"]["graph_receiver"][start])
        ids = np.array([start, target], np.int64)
        width = np.maximum(6., 4. * np.sqrt(q[ids]))
        depth = np.maximum(.25, .2 * np.cbrt(q[ids]))
        record = dict(source_cell_id=start, target_cell_id=target)
        try:
            coarse = build_valley_incision(terrain, ids, np.array([1, -1], np.int64),
                                           width, depth,
                                           config=GeometryConfig(fine_spacing_m=.5,
                                                                 smoothing_iterations=0), **options)
            fine = build_valley_incision(terrain, ids, np.array([1, -1], np.int64),
                                         width, depth,
                                         config=GeometryConfig(fine_spacing_m=.25,
                                                               smoothing_iterations=0), **options)
            cv = coarse["metadata"]["cut_volume_m3"]
            fv = fine["metadata"]["cut_volume_m3"]
            error = abs(cv - fv) / max(fv, 1e-12)
            if error > .02:
                raise ValueError("spatial cut volume refinement exceeds fixed 2% gate")
            record.update(status="accepted_local_edge", coarse_cut_volume_m3=cv,
                          fine_cut_volume_m3=fv, spatial_refinement_relative=error,
                          max_profile_cut_m=float(np.max(fine["arrays"]["profile_source_m"]
                                                     - fine["arrays"]["profile_center_bed_m"])),
                          coarse_identity_sha256=coarse["identity_sha256"],
                          fine_identity_sha256=fine["identity_sha256"])
            if representative is None:
                representative = {}
                for label, product in (("coarse", coarse), ("fine", fine)):
                    path = output / ("representative-" + label + ".npz")
                    save_valley_incision(path, product)
                    sha = file_sha256(path)
                    load_valley_incision(path, expected_sha256=sha,
                                         expected_identity=product["identity_sha256"])
                    representative[label] = dict(path=path.name, sha256=sha,
                                                 identity_sha256=product["identity_sha256"])
        except ValueError as error:
            record.update(status="refused", reason=str(error))
        outcomes.append(record)
        if index % 25 == 0:
            print(json.dumps({"checked": index, "accepted": sum(
                item["status"] == "accepted_local_edge" for item in outcomes)}), flush=True)
    if len(outcomes) != len(expected):
        raise AssertionError("missing original-bed uphill edge")
    accepted = [row for row in outcomes if row["status"] == "accepted_local_edge"]
    report = dict(schema="td-valley-incision-extension-v1", status="local_candidates_only",
                  source=dict(path=str(TD_DIRECTORY / "product.npz"), sha256=TD_PRODUCT_SHA,
                              identity_sha256=TD_PRODUCT_ID),
                  parent_report_sha256=file_sha256(PARENT / "acceptance.json"),
                  parent_network_plan=pin, total_original_uphill_edges=len(expected),
                  local_accepted_edges=len(accepted),
                  outcomes=outcomes,
                  refusal_reasons=dict(Counter(row["reason"] for row in outcomes if "reason" in row)),
                  max_spatial_refinement_relative=max((row["spatial_refinement_relative"]
                                                       for row in accepted), default=None),
                  representative=representative,
                  code_sha256={name: file_sha256(ROOT / name) for name in (
                      "terrain_pipeline/surface_rivers/metric_valley_incision.py",
                      "terrain_pipeline/surface_rivers/metric_channel_geometry.py",
                      "tools/verify_td_valley_incision_extension.py")},
                  global_mesh_assembled=False, shared_ports_verified=False,
                  unique_material_ledger_verified=False, natural_outlet_verified=False,
                  publishable=False)
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2,
                                                        allow_nan=False).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.output)
    print(json.dumps({key: report[key] for key in
                      ("status", "total_original_uphill_edges", "local_accepted_edges",
                       "refusal_reasons", "max_spatial_refinement_relative")}))
