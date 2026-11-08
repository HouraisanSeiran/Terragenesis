"""Classify refused TD valley edges without changing geometry or masks."""

import argparse
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.channel_geometry import _segment_box_distance
from terrain_pipeline.channel_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_ID, TD_PRODUCT_SHA, terrain_from_product

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "verification/td-river-network-expansion/td1024-20261008-01"
REFUSAL_REPORT = ROOT / "verification/td-valley-global-tiled/td1024-20261008-01/failure-prefix.json"
BANK_SLOPE = 1.5


def _classify_edge(terrain, owner, corridor, lake, source, target, width, depth):
    a = np.asarray(terrain.world_xz(source), dtype=np.float64)
    b = np.asarray(terrain.world_xz(target), dtype=np.float64)
    rows, cols = terrain.elevation_m.shape
    result = {"source_cell_id": int(source), "target_cell_id": int(target),
              "source_owner": int(owner.ravel()[source]), "factors": {}}
    for factor in (1.0, .75, .5, .25, .1, 0.0):
        radius = factor * max(width / 2. + BANK_SLOPE * depth,
                              width / 2. + BANK_SLOPE * depth)
        reasons = {"unknown": 0, "corridor": 0, "divide": 0, "boundary": 0, "lake_touch": 0}
        if (np.any(np.minimum(a, b) - radius < [terrain.x0_m, terrain.z0_m])
                or np.any(np.maximum(a, b) + radius >
                          [terrain.x0_m + (cols - 1) * terrain.dx_m,
                           terrain.z0_m + (rows - 1) * terrain.dz_m])):
            reasons["boundary"] += 1
        else:
            x0 = max(0, math.floor((min(a[0], b[0]) - radius - terrain.x0_m) / terrain.dx_m))
            x1 = min(cols - 2, math.floor((max(a[0], b[0]) + radius - terrain.x0_m) / terrain.dx_m))
            z0 = max(0, math.floor((min(a[1], b[1]) - radius - terrain.z0_m) / terrain.dz_m))
            z1 = min(rows - 2, math.floor((max(a[1], b[1]) + radius - terrain.z0_m) / terrain.dz_m))
            source_owner = owner.ravel()[source]
            for z in range(z0, z1 + 1):
                for x in range(x0, x1 + 1):
                    low = np.array([terrain.x0_m + x * terrain.dx_m,
                                    terrain.z0_m + z * terrain.dz_m])
                    high = low + [terrain.dx_m, terrain.dz_m]
                    if _segment_box_distance(a, b, low, high) > radius + 1e-10:
                        continue
                    stencil = np.s_[z:z + 2, x:x + 2]
                    if not terrain.valid_mask[stencil].all():
                        reasons["unknown"] += 1
                    if not corridor[stencil].all():
                        reasons["corridor"] += 1
                    if np.any(owner[stencil] != source_owner):
                        reasons["divide"] += 1
                    if lake[stencil].any():
                        reasons["lake_touch"] += 1
        result["factors"][str(factor)] = reasons
    viable = []
    for factor, reasons in result["factors"].items():
        if float(factor) > 0.0 and not any(reasons[key] for key in ("unknown", "corridor", "divide", "boundary")):
            viable.append(float(factor))
    result["smallest_viable_factor"] = min(viable) if viable else None
    result["centerline_owner_crossing"] = result["factors"]["0.0"]["divide"] > 0
    result["recommendation"] = ("bounded_width_reduction_candidate" if viable and min(viable) < 1.
                                 else "must_remain_unresolved")
    return result


def diagnose(output):
    output = Path(output)
    report = json.loads(REFUSAL_REPORT.read_text(encoding="utf-8"))
    refused = [int(row["source_cell_id"]) for row in report["preflight"]
               if row["status"] == "refused_edge_preflight"]
    parent = json.loads((PARENT / "acceptance.json").read_text(encoding="utf-8"))
    pin = parent["plan"]
    plan = load_network_geometry_plan(PARENT / pin["path"], expected_sha256=pin["sha256"])
    source = load_diagnostic_product(TD_DIRECTORY / "product.npz",
                                     expected_sha256=TD_PRODUCT_SHA,
                                     expected_identity=TD_PRODUCT_ID)
    terrain = terrain_from_product(source)
    arrays = plan["arrays"]
    receiver = arrays["graph_receiver"]
    owner = arrays["terminal_owner"].reshape(terrain.elevation_m.shape)
    corridor = np.ones(owner.shape, bool)
    lake = np.zeros(owner.shape, bool)
    q = arrays["contributing_area_m2"] / 1000. / 3600.
    widths = np.maximum(6., 4. * np.sqrt(q))
    depths = np.maximum(.25, .2 * np.cbrt(q))
    rows = [_classify_edge(terrain, owner, corridor, lake, source_id,
                           int(receiver[source_id]), float(widths[source_id]),
                           float(depths[source_id])) for source_id in refused]
    summary = {"status": "diagnostic_only", "source_sha256": TD_PRODUCT_SHA,
               "plan_identity_sha256": plan["identity_sha256"],
               "refused_count": len(rows),
               "recommendation_counts": {key: sum(row["recommendation"] == key for row in rows)
                                          for key in ("bounded_width_reduction_candidate", "must_remain_unresolved")},
               "rows": rows,
               "code_sha256": {"self": file_sha256(Path(__file__))}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    result = diagnose(parser.parse_args().output)
    print(json.dumps({key: result[key] for key in ("refused_count", "recommendation_counts")}))
