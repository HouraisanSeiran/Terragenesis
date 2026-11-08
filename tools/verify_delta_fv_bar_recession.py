"""Bed-only hydraulic reinitialization at fixed low flow and low sea stage."""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.ndimage import label

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.environment_delta_fv import FVDeltaConfig, initialize, advance, load, save


def _tree(graph, source, allowed):
    parents = {int(source): None}
    queue = deque([int(source)])
    while queue:
        node = queue.popleft()
        for target in graph[node]:
            if allowed[target] and target not in parents:
                parents[target] = node
                queue.append(target)
    return parents


def _path(parents, target):
    result = []
    while target is not None:
        result.append(int(target))
        target = parents[target]
    return result[::-1]


def island_rejoining_paths(product, *, source_q_m3_s, minimum_depth_m=None):
    """Witness two directed FV routes through opposite gates around a dry island.

    Both routes begin at the same source and end at the same downstream cell.
    During their passage through the island's column band they occupy disjoint
    north/south sides. Fluxes are actual final coupling-interval net transfers.
    """
    a, m = product["arrays"], product["metadata"]
    if minimum_depth_m is None:
        minimum_depth_m = m["config"]["bedload"]["dry_depth_m"]
    rows, cols = a["bed_m"].shape
    wet = a["depth_m"].ravel() > minimum_depth_m
    dry = ~wet.reshape(rows, cols)
    components, count = label(dry, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    dt = m["last_coupling_interval_s"]
    q = a["internal_last_water_transfer_m3"]/dt
    left, right = a["face_left"], a["face_right"]
    graph = [[] for _ in range(rows*cols)]
    edge_flow = {}
    active = (abs(q) > 1.e-4) & wet[left] & wet[right]
    for first, second, flow in zip(left[active], right[active], q[active]):
        donor, receiver = (first, second) if flow > 0. else (second, first)
        graph[int(donor)].append(int(receiver))
        edge_flow[int(donor), int(receiver)] = float(abs(flow))
    rr, cc = np.indices((rows, cols))
    candidates = []
    for number in range(1, count+1):
        island = components == number
        ir, ic = np.nonzero(island)
        if (not np.all(a["ocean_mask"][island]) or min(ir) == 0 or max(ir) == rows-1
                or min(ic) == 0 or max(ic) == cols-1):
            continue
        r0, r1, c0, c1 = int(min(ir)), int(max(ir)), int(min(ic)), int(max(ic))
        middle_col = (c0+c1)//2
        gate_faces = (left % cols == middle_col) & (right == left+1)
        north_q = float(np.maximum(-q[gate_faces & (left//cols < r0)], 0.).sum())
        south_q = float(np.maximum(-q[gate_faces & (left//cols > r1)], 0.).sum())
        candidate = {"dry_cells": int(island.sum()), "bounds_rc": [r0, r1, c0, c1],
                     "north_gate_q_m3_s": north_q, "south_gate_q_m3_s": south_q,
                     "north_gate_fraction_of_source_q": north_q/source_q_m3_s,
                     "south_gate_fraction_of_source_q": south_q/source_q_m3_s,
                     "material_flow_threshold_m3_s": max(.01, .01*source_q_m3_s), "rejoins": False}
        candidates.append(candidate)
        if min(north_q, south_q) <= 1.e-4:
            continue
        band = (cc >= c0-1) & (cc <= c1+1)
        north_allowed = wet & (~(band & (rr >= r0))).ravel()
        south_allowed = wet & (~(band & (rr <= r1))).ravel()
        for source in a["inlet_cells"]:
            north = _tree(graph, source, north_allowed)
            south = _tree(graph, source, south_allowed)
            common = [node for node in north.keys() & south.keys()
                      if node % cols < c0-1 and r0 <= node//cols <= r1]
            if common:
                target = min(common, key=lambda n: (c0-n % cols, abs(n//cols-(r0+r1)/2.)))
                material = min(north_q, south_q) >= max(.01, .01*source_q_m3_s)
                candidate.update(rejoins=True, material_flow_passed=material, common_source=int(source), common_downstream_cell=int(target),
                                 north_path=_path(north, target), south_path=_path(south, target))
                for side in ("north", "south"):
                    path = candidate[side+"_path"]
                    candidate[side+"_minimum_edge_q_m3_s"] = min(edge_flow[pair] for pair in zip(path[:-1], path[1:]))
                return {"passed": material, "geometric_passed": True, "islands": candidates,
                        "dry_depth_threshold_m": minimum_depth_m, "flux_threshold_m3_s": 1.e-4,
                        "interpretation": "actual two-side directed FV paths join the same downstream cell; transient low-flow diagnostic only"}
    return {"passed": False, "geometric_passed": False, "islands": candidates,
            "dry_depth_threshold_m": minimum_depth_m, "flux_threshold_m3_s": 1.e-4,
            "interpretation": "no qualifying dry island with two materially flowing directed routes and a common downstream cell"}


def draw(product, witness, path, title="Bed-only recession diagnostic: Q=10 m3/s, sea=-0.3 m, no new sediment; red=dry/wet edge"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    a, m = product["arrays"], product["metadata"]
    rows, cols = a["bed_m"].shape
    h = a["depth_m"]
    velocity = np.divide(a["momentum_m2_s"], h.ravel()[:, None], out=np.zeros_like(a["momentum_m2_s"]),
                         where=h.ravel()[:, None] > m["config"]["bedload"]["dry_depth_m"]).reshape(rows, cols, 2)
    x, z = np.arange(cols)*m["spacing_m"], np.arange(rows)*m["spacing_m"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
    for axis, data, title in zip(axes, [a["bed_m"], h, np.linalg.norm(velocity, axis=2)],
                               ["Bed elevation (m)", "Water depth (m)", "Velocity (m/s)"]):
        im = axis.pcolormesh(x, z, data, shading="nearest", cmap="viridis")
        fig.colorbar(im, ax=axis)
        axis.contour(x, z, h, levels=[m["config"]["bedload"]["dry_depth_m"]], colors="red", linewidths=.7)
        axis.set_aspect("equal")
        axis.set(xlabel="x (m)", ylabel="z (m)", title=title)
    for axis in axes[1:]:
        axis.streamplot(x, z, velocity[:, :, 0], velocity[:, :, 1], color="white", density=1.3, linewidth=.6)
    for island in witness["islands"]:
        if island["rejoins"]:
            for name, color in (("north_path", "cyan"), ("south_path", "magenta")):
                cells = np.asarray(island[name])
                axes[2].plot(x[cells % cols], z[cells//cols], color=color, linewidth=2.)
    fig.suptitle(title)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def sections(product):
    a, m = product["arrays"], product["metadata"]
    cols = a["bed_m"].shape[1]
    output = {}
    for col in (35, 32, 28, 24, 20):
        faces = (a["face_left"] % cols == col) & (a["face_right"] == a["face_left"]+1)
        flow = a["internal_last_water_transfer_m3"][faces]/m["last_coupling_interval_s"]
        output[str(col)] = {"net_westward_q_m3_s": float(-flow.sum()), "q_east_m3_s_by_row": flow.tolist(),
                            "bed_m_by_row": a["bed_m"][:, col].tolist(), "depth_m_by_row": a["depth_m"][:, col].tolist()}
    return output


def run(args):
    parent_hash = file_sha256(args.parent)
    parent = load(args.parent, expected_sha256=parent_hash)
    args.output.mkdir(parents=True, exist_ok=False)
    reports = {}
    for name, bed in (("grown", parent["arrays"]["bed_m"]), ("original", parent["arrays"]["initial_bed_m"])):
        started = time.monotonic()
        case = args.output/name
        case.mkdir()
        pa, pm = parent["arrays"], parent["metadata"]
        initial = initialize(bed, pa["ocean_mask"], pa["inlet_cells"], origin_m_xz=pm["origin_m_xz"],
            source_world_identity=pm["source_world_identity"], source_identity="bed-only-recession:"+parent_hash+":"+name,
            spacing_m=pm["spacing_m"], floor_m=pa["floor_m"],
            config=FVDeltaConfig(sea_mean_m=-.3, coupling_interval_s=10., max_hydro_dt_s=3., max_wall_s=120.))
        initial["metadata"]["diagnostic"] = {"kind": "bed-only-hydraulic-relaxation-reinitialization",
            "parent_sha256": parent_hash, "parent_product_identity": parent["identity_sha256"], "case": name,
            "parent_physical_time_s": pm["physical_time_s"], "diagnostic_clock_origin_s": 0.,
            "water_and_momentum": "reset to declared -0.3m still-water stage and zero momentum; not physical continuation",
            "suspended_inventory": "reset to zero; parent suspended load is outside this bed-only experiment, not reissued or exported",
            "bed_inventory": "existing bed minus original floor counted once as initial finite stock; no external sediment"}
        initial["identity_sha256"] = identity(initial["arrays"], initial["metadata"])
        save(case/"initial.npz", initial)
        result = advance(initial, [{"id": "recession-1800", "source": "declared fixed low-flow low-sea hydraulic diagnostic",
            "time_start_s": 0., "time_end_s": 1800., "water_m3": 18000., "solid_m3": 0.}])
        save(case/"final.npz", result)
        witness = island_rejoining_paths(result, source_q_m3_s=10.)
        draw(result, witness, case/"flow.png")
        a, m = result["arrays"], result["metadata"]
        ocean = a["ocean_mask"]
        report = {"diagnostic": initial["metadata"]["diagnostic"], "runtime_s": time.monotonic()-started,
            "initial_bed_solid_m3": m["initial_bed_solid_m3"], "ledger": m["ledger"],
            "ocean_dry_cells": int(np.count_nonzero(a["depth_m"][ocean] <= m["config"]["bedload"]["dry_depth_m"])),
            "ocean_exact_zero_depth_cells": int(np.count_nonzero(a["depth_m"][ocean] == 0.)),
            "ocean_depth_at_most_1mm_cells": int(np.count_nonzero(a["depth_m"][ocean] <= .001)),
            "max_bed_change_during_recession_m": float(abs(a["bed_m"]-a["initial_bed_m"]).max()),
            "sections": sections(result), "two_side_rejoining_witness": witness,
            "final_sha256": file_sha256(case/"final.npz")}
        (case/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        reports[name] = report
    reports["source_unchanged"] = file_sha256(args.parent) == parent_hash
    (args.output/"summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    return reports


def extend(args):
    """One fixed extension retaining the existing diagnostic's complete live state."""
    reports = {}
    for name in ("grown", "original"):
        parent_path = args.output/name/"final.npz"
        previous_hash = file_sha256(parent_path)
        previous = load(parent_path, expected_sha256=previous_hash)
        if previous["metadata"]["physical_time_s"] != 1800.:
            raise ValueError("extension requires the completed original 1800s diagnostic")
        case = args.output/(name+"-7200")
        case.mkdir()
        save(case/"initial.npz", previous)
        started = time.monotonic()
        result = advance(previous, [{"id": "recession-extension-5400", "source": "same diagnostic live-state hydraulic relaxation; no resetting and no sediment",
            "time_start_s": 1800., "time_end_s": 7200., "water_m3": 54000., "solid_m3": 0.}])
        save(case/"final.npz", result)
        witness = island_rejoining_paths(result, source_q_m3_s=10.)
        draw(result, witness, case/"flow.png")
        a, m = result["arrays"], result["metadata"]
        report = {"diagnostic": m["diagnostic"], "live_continuation_parent_sha256": previous_hash,
            "physical_time_s": m["physical_time_s"], "runtime_s": time.monotonic()-started,
            "initial_bed_solid_m3": m["initial_bed_solid_m3"], "ledger": m["ledger"],
            "water_storage_change_since_diagnostic_start_m3": float(a["depth_m"].sum()*m["spacing_m"]**2-m["initial_water_m3"]),
            "final_interval_boundary_net_export_q_m3_s": float(a["boundary_last_water_transfer_m3"].sum()/m["last_coupling_interval_s"]),
            "ocean_dry_cells": int(np.count_nonzero(a["depth_m"][a["ocean_mask"]] <= m["config"]["bedload"]["dry_depth_m"])),
            "ocean_exact_zero_depth_cells": int(np.count_nonzero(a["depth_m"][a["ocean_mask"]] == 0.)),
            "ocean_depth_at_most_1mm_cells": int(np.count_nonzero(a["depth_m"][a["ocean_mask"]] <= .001)),
            "max_bed_change_since_reinitialization_m": float(abs(a["bed_m"]-a["initial_bed_m"]).max()),
            "sections": sections(result), "two_side_rejoining_witness": witness,
            "source_unchanged": file_sha256(parent_path) == previous_hash,
            "final_sha256": file_sha256(case/"final.npz")}
        (case/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        reports[name] = report
    (args.output/"extension-summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=Path(".scratch/delta-development-20261030/morphology-feeder-12h-continued/final.npz"))
    parser.add_argument("--output", type=Path, default=Path(".scratch/delta-development-20261030/bar-recession"))
    parser.add_argument("--extend-existing", action="store_true", help="retain 1800s diagnostic water/momentum/bed/suspended state and advance once to 7200s")
    args = parser.parse_args()
    reports = extend(args) if args.extend_existing else run(args)
    print(json.dumps({name: {"dry_cells": reports[name]["ocean_dry_cells"],
        "rejoins": reports[name]["two_side_rejoining_witness"]["passed"]} for name in ("grown", "original")}))


if __name__ == "__main__":
    main()
