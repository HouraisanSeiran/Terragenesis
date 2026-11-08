"""Read-only coarse-plan topology metrics; no generation or TD certification."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hydrology_planning import load_plan


def audit_plan(plan):
    height = plan["height_m"].ravel()
    receiver = plan["receiver"].ravel()
    owner = plan["owner_domain_id"].ravel()
    river = plan["river_mask"].ravel()
    columns = plan["height_m"].shape[1]
    nodes = np.flatnonzero(river)
    donors = [[] for _ in range(height.size)]
    for node in nodes:
        downstream = int(receiver[node])
        if downstream >= 0 and river[downstream]:
            donors[downstream].append(int(node))
    orders = np.zeros(height.size, np.int32)
    for node in np.argsort(height)[::-1]:
        if river[node]:
            upstream = [orders[d] for d in donors[node]]
            maximum = max(upstream, default=1)
            orders[node] = maximum + int(bool(upstream) and upstream.count(maximum) >= 2)
    branch_counts = {}
    side_counts = {}
    direction_counts = {}
    longest = 0.
    runs = {}
    terminal_counts = {}
    cross_owner = 0
    upstream_unknown = 0
    for node in np.flatnonzero(owner >= 0):
        downstream = int(receiver[node])
        if downstream >= 0 and owner[downstream] >= 0 and owner[downstream] != owner[node]:
            cross_owner += 1
    for node in np.flatnonzero((owner == -2) & (receiver >= 0)):
        if owner[receiver[node]] >= 0:
            upstream_unknown += 1
    for domain in plan["domains"]:
        terminal_counts[str(domain["domain_id"])] = {"kind": domain["kind"], "terminal_count": len(domain["terminal_indices"]),
            "true_terminal_indices": domain["terminal_indices"], "registered_inland_terminal": domain["lake_terminal_index"]}
    for node in nodes:
        order = int(orders[node])
        if not any(orders[d] == order for d in donors[node]):
            branch_counts[str(order)] = branch_counts.get(str(order), 0) + 1
        if len(donors[node]) >= 2:
            for donor in donors[node]:
                lower = int(orders[donor])
                if lower < order:
                    # Equal-order merger creates a new branch, not side branching.
                    if any(orders[d] == order for d in donors[node]):
                        key = str(lower) + "," + str(order)
                        side_counts[key] = side_counts.get(key, 0) + 1
    for node in np.argsort(height)[::-1]:
        if not river[node] or receiver[node] < 0:
            continue
        downstream = int(receiver[node])
        r, c = divmod(int(node), columns)
        rr, cc = divmod(downstream, columns)
        direction = (rr-r, cc-c)
        key = str(direction[0]) + "," + str(direction[1])
        direction_counts[key] = direction_counts.get(key, 0) + 1
        length = float(np.hypot(*direction) * plan["spacing_m"])
        run = runs.get((int(node), direction), 0.) + length
        runs[(downstream, direction)] = max(runs.get((downstream, direction), 0.), run)
        longest = max(longest, run)
    tokunaga = [{"lower_order": int(k.split(",")[0]), "receiving_order": int(k.split(",")[1]),
                 "side_branch_count": v, "receiving_branch_count": branch_counts[k.split(",")[1]],
                 "ratio": v / branch_counts[k.split(",")[1]]} for k, v in sorted(side_counts.items())]
    return {"schema": "hydrology-planning-coarse-naturalness-audit-v2", "seed": plan["seed"],
        "plan_identity_sha256": plan["identity_sha256"], "algorithm": plan["algorithm_version"],
        "source": plan["source"], "spacing_m": plan["spacing_m"], "macro_cell": plan["macro_cell"],
        "terminal_domains": terminal_counts, "complete_catchment_count": len(plan["catchments"]),
        "cross_owner_edge_count": cross_owner, "unknown_upstream_inflow_count": upstream_unknown,
        "river_pixel_count": int(nodes.size), "confluence_pixel_count": sum(len(donors[n]) >= 2 for n in nodes),
        "maximum_strahler_order": int(orders.max()), "strahler_branch_counts": branch_counts,
        "tokunaga_order_pair_samples": tokunaga, "tokunaga_nonempty_order_pair_count": len(tokunaga),
        "d8_direction_counts": direction_counts, "river_receiver_edge_count": sum(direction_counts.values()),
        "longest_same_direction_run_m": longest,
        "definition": "river_mask at frozen 25-cell area threshold; Strahler D8 pixel tree; maximal same-order branches; lower-order side tributaries only where receiver continues an existing higher-order branch; directions and lengths include all selected river receiver>=0 edges, including final nonriver/ocean terminal edge",
        "limitations": ["three fixed supports are an initial sample, no naturalness pass threshold or self-similarity fit", "D8 directions are raster representation diagnostics", "no real-TD fine-bed naturalness certification"],
        "naturalness_certified": False, "fine_td_geometry_certified": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan")
    parser.add_argument("output")
    args = parser.parse_args()
    record = audit_plan(load_plan(args.plan))
    with Path(args.output).open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
