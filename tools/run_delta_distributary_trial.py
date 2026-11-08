"""Fixed finite-bed distributary trial; flux witnesses, not streamline inference."""
import argparse
import hashlib
import heapq
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.ndimage import maximum_filter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_delta_fv import FVDeltaConfig, initialize, advance, save, load

WORLD_SEED = 20261020
ORIGIN = (1374000., 1242000.)
PURPOSE = "delta-distributary-seabed-microrelief-v1"
SUBSEED = int.from_bytes(hashlib.sha256(f"{WORLD_SEED}:{PURPOSE}".encode()).digest()[:8], "little")


def microrelief(x_m, z_m):
    """Coordinate hash: independent of crop, query order and adaptive time steps."""
    x, z = np.broadcast_arrays(np.asarray(x_m, float), np.asarray(z_m, float))
    output = np.empty(x.shape)
    for index in np.ndindex(x.shape):
        token = f"{SUBSEED}:{float(x[index]).hex()}:{float(z[index]).hex()}".encode()
        value = int.from_bytes(hashlib.sha256(token).digest()[:8], "little")
        output[index] = .025 * (2. * value / (2**64 - 1) - 1.)
    return output


def initial_product(perturbed, max_wall_s=180.):
    bed = np.full((32, 48), -.5)
    bed[:, 36:] = .8
    baseline = bed.copy()
    bed[15:18, 36:] = -1.
    ocean = np.indices(bed.shape)[1] < 36
    if perturbed:
        rr, cc = np.indices(bed.shape)
        bed[ocean] += microrelief(ORIGIN[0]+cc[ocean]*30., ORIGIN[1]+rr[ocean]*30.)
    floor = bed.copy()
    floor[ocean] -= .6
    product = initialize(bed, ocean, [16*48+46], origin_m_xz=ORIGIN,
        source_world_identity="seed20261020", source_identity="declared-finite-distributary-trial-v1:"+str(perturbed),
        floor_m=floor, config=FVDeltaConfig(coupling_interval_s=10., max_hydro_dt_s=3., max_wall_s=max_wall_s))
    construction = float((baseline[:, 36:]-bed[:, 36:]).sum()*900.)
    return product, construction


def _graph(product):
    a, m = product["arrays"], product["metadata"]
    dt = m["last_coupling_interval_s"]
    q = a["internal_last_water_transfer_m3"] / dt if dt else np.zeros(len(a["face_left"]))
    wet = a["depth_m"].ravel() > m["config"]["bedload"]["dry_depth_m"]
    graph = [[] for _ in wet]
    for left, right, flow in zip(a["face_left"], a["face_right"], q):
        if abs(flow) > 1.e-4 and wet[left] and wet[right]:
            first, second = (left, right) if flow > 0. else (right, left)
            graph[first].append((int(second), float(abs(flow))))
    boundary_q = a["boundary_last_water_transfer_m3"] / dt if dt else np.zeros(len(a["boundary_cell"]))
    exports = {}
    for cell, kind, flow in zip(a["boundary_cell"], a["boundary_kind"], boundary_q):
        if kind == 2 and flow > 0.:
            exports[int(cell)] = exports.get(int(cell), 0.) + float(flow)
    exports = {cell: flow for cell, flow in exports.items() if flow > 1.e-4}
    return graph, q, exports


def _widest(graph, source, targets, allowed):
    best = {int(source): float("inf")}
    parents = {int(source): None}
    queue = [(-float("inf"), int(source))]
    while queue:
        negative, node = heapq.heappop(queue)
        if -negative < best[node]:
            continue
        for target, flow in graph[node]:
            capacity = min(best[node], flow)
            if allowed[target] and capacity > best.get(target, 0.):
                best[target], parents[target] = capacity, node
                heapq.heappush(queue, (-capacity, target))
    reached = [(min(best[node], capacity), node) for node, capacity in targets.items() if node in best]
    if not reached:
        return [], 0.
    capacity, node = max(reached)
    path = []
    while node is not None:
        path.append(node)
        node = parents[node]
    return path[::-1], capacity


def candidate_anchors(product):
    a = product["arrays"]
    rise = a["bed_m"]-a["initial_bed_m"]
    mask = a["ocean_mask"] & (rise >= .1) & (a["bed_m"] == maximum_filter(a["bed_m"], size=5))
    mask[:6] = False
    mask[-6:] = False
    mask[:, :4] = False
    mask[:, 34:] = False
    candidates = sorted(zip(*np.nonzero(mask)), key=lambda rc: float(rise[rc]), reverse=True)
    selected = []
    for row, col in candidates:
        if all(max(abs(row-r), abs(col-c)) >= 4 for r, c in selected):
            selected.append((int(row), int(col)))
    return selected[:12]


def diagnose_bar(product, anchor, source_q):
    """Three local gates on each side, joined by actual directed face paths."""
    a = product["arrays"]
    rows, cols = a["bed_m"].shape
    row, col = anchor
    graph, q, exports = _graph(product)
    rr, cc = np.indices((rows, cols))
    source = int(a["inlet_cells"][0])
    rise = a["bed_m"]-a["initial_bed_m"]
    sections = []
    threshold = max(.01, .01*source_q)
    for section_col in (col+2, col, col-2):
        spine_row = row + int(np.argmax(a["bed_m"][row-1:row+2, section_col]))-1
        spine = float(a["bed_m"][spine_row, section_col])
        section = {"col": section_col, "bar_cell_rc": [spine_row, section_col], "bar_bed_m": spine,
                   "bar_rise_m": float(rise[spine_row, section_col]),
                   "bed_m_by_row": a["bed_m"][:, section_col].tolist(),
                   "initial_bed_m_by_row": a["initial_bed_m"][:, section_col].tolist(),
                   "depth_m_by_row": a["depth_m"][:, section_col].tolist(),
                   "westward_q_m3_s_by_row": [-float(q[(a["face_left"] == r*cols+section_col) &
                       (a["face_right"] == r*cols+section_col+1)].sum()) for r in range(rows)]}
        for side, band in (("north", range(row-5, row-1)), ("south", range(row+2, row+6))):
            channel_row = min(band, key=lambda r: a["bed_m"][r, section_col])
            faces = (a["face_left"] == channel_row*cols+section_col) & (a["face_right"] == channel_row*cols+section_col+1)
            section[side] = {"cell_rc": [channel_row, section_col], "bed_m": float(a["bed_m"][channel_row, section_col]),
                "depth_m": float(a["depth_m"][channel_row, section_col]),
                "bed_below_bar_m": spine-float(a["bed_m"][channel_row, section_col]),
                "westward_q_m3_s": float(-q[faces].sum()),
                "erosion_below_initial_m": float(max(0., -rise[channel_row, section_col])),
                "at_search_band_edge": channel_row in (band.start, band.stop-1),
                "strict_transverse_local_minimum": bool(a["bed_m"][channel_row, section_col] <
                    min(a["bed_m"][channel_row-1, section_col], a["bed_m"][channel_row+1, section_col])),
                "north_neighbor_bed_minus_gate_m": float(a["bed_m"][channel_row-1, section_col]-a["bed_m"][channel_row, section_col]),
                "south_neighbor_bed_minus_gate_m": float(a["bed_m"][channel_row+1, section_col]-a["bed_m"][channel_row, section_col])}
        sections.append(section)
    report = {"anchor_rc": list(anchor), "material_threshold_m3_s": threshold, "sections": sections, "sides": {}}
    for side in ("north", "south"):
        allowed = np.ones((rows, cols), bool)
        band = (cc >= col-3) & (cc <= col+3)
        allowed[band & ((rr >= row-1) if side == "north" else (rr <= row+1))] = False
        path, bottleneck, current = [], float("inf"), source
        continuous = True
        for section in sections:
            r, c = section[side]["cell_rc"]
            target = r*cols+c
            east = target+1
            leg, capacity = _widest(graph, current, {east: float("inf")}, allowed.ravel())
            gate_capacity = max((flow for receiver, flow in graph[east] if receiver == target), default=0.)
            if not leg or gate_capacity <= 0.:
                continuous = False
                break
            leg.append(target)
            path.extend(leg if not path else leg[1:])
            current, bottleneck = target, min(bottleneck, capacity, gate_capacity)
        if continuous:
            leg, capacity = _widest(graph, current, exports, allowed.ravel())
            continuous = bool(leg)
            if leg:
                path.extend(leg[1:])
                bottleneck = min(bottleneck, capacity)
        local = all(s[side]["bed_below_bar_m"] >= .05 and s[side]["westward_q_m3_s"] >= threshold
                    and s["bar_rise_m"] >= .1 for s in sections)
        report["sides"][side] = {"local_channel_and_flux_passed": local, "directed_to_sea": continuous,
            "path": path if continuous else [], "minimum_edge_q_m3_s": bottleneck if continuous else 0.,
            "strict_local_minimum_section_count": sum(int(s[side]["strict_transverse_local_minimum"]) for s in sections),
            "search_band_edge_section_count": sum(int(s[side]["at_search_band_edge"]) for s in sections),
            "section_count": len(sections),
            "passed": bool(local and continuous and bottleneck >= threshold)}
    report["passed"] = all(s["passed"] for s in report["sides"].values())
    report["interpretation"] = "local_bar_bypass: material two-sided water transport around raised new bed; channel incision and two-bank confinement require separate profile evidence"
    return report


def stage_report(product, source_q, anchors=()):
    a, m = product["arrays"], product["metadata"]
    area, porosity = m["spacing_m"]**2, m["config"]["bedload"]["porosity"]
    ledger = m["ledger"]
    bed_stock = float(((a["bed_m"]-a["floor_m"])*area*(1.-porosity)).sum())
    water_stock = float(a["depth_m"].sum()*area)
    dt = m["last_coupling_interval_s"]
    reports = [diagnose_bar(product, anchor, source_q) for anchor in anchors]
    ocean_delta = (a["bed_m"]-a["initial_bed_m"])[a["ocean_mask"]]
    wet = a["depth_m"] > m["config"]["bedload"]["dry_depth_m"]
    concentration = np.divide(a["suspended_solid_m3"], a["depth_m"]*area,
                              out=np.zeros_like(a["depth_m"]), where=wet)
    mouth = np.zeros(wet.shape, bool)
    mouth[11:22, 30:38] = True
    concentration_stats = {}
    for name, mask in (("offshore_wet", wet & a["ocean_mask"]), ("mouth_wet", wet & mouth)):
        values = concentration[mask]
        concentration_stats[name] = {"wet_cells": int(mask.sum()), "maximum_solid_volume_fraction": float(values.max()) if len(values) else 0.,
                                     "median_solid_volume_fraction": float(np.median(values)) if len(values) else 0.}
    return {"physical_time_s": m["physical_time_s"], "ledger": ledger,
        "bed_solid_inventory_m3": bed_stock, "suspended_solid_inventory_m3": float(a["suspended_solid_m3"].sum()),
        "water_inventory_m3": water_stock,
        "water_budget_residual_m3": water_stock+ledger["water_export_m3"]-m["initial_water_m3"]-ledger["water_input_m3"]-ledger["sea_import_m3"],
        "solid_budget_residual_m3": bed_stock+float(a["suspended_solid_m3"].sum())+ledger["solid_export_m3"]-m["initial_bed_solid_m3"]-ledger["solid_input_m3"],
        "maximum_offshore_rise_m": float(ocean_delta.max()), "maximum_offshore_erosion_m": float(-ocean_delta.min()),
        "ocean_dry_cells": int(np.count_nonzero(a["depth_m"][a["ocean_mask"]] <= m["config"]["bedload"]["dry_depth_m"])),
        "last_interval_boundary_export_q_m3_s": float(a["boundary_last_water_transfer_m3"].sum()/dt) if dt else 0.,
        "suspended_concentration": concentration_stats,
        "bars": reports, "local_material_distributary_passed": any(r["passed"] for r in reports),
        "local_bar_bypass_passed": any(r["passed"] for r in reports),
        "interpretation": "local bypass witness does not alone establish incised distributary channels"}


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    summary = {"world_seed": WORLD_SEED, "origin_m_xz": ORIGIN, "spacing_m": 30., "shape_zx": [32, 48],
        "microrelief": {"purpose": PURPOSE, "sha256_little_endian_64_subseed": SUBSEED, "amplitude_m": .025,
                        "sampling": "SHA256 of subseed and float.hex absolute metric x,z; ocean only"},
        "scenario": "finite engineering trial; zero-sediment stages are clear-water reshaping stress tests; not mature long-term delta certification",
        "scale_estimate": {"growth_solid_input_m3": 86400., "radius_200m_half_m_fill_solid_m3": float(np.pi*200.**2*.5*.65),
                           "cover_depth_m": .6, "forcing_concentration": .01}, "cases": {}}
    for case, perturb in (("flat", False), ("microrelief", True)):
        directory = args.output/case
        directory.mkdir()
        product, excavation = initial_product(perturb, args.max_wall_s)
        initial_stock = product["metadata"]["initial_bed_solid_m3"]
        save(directory/"initial.npz", product)
        reports = {"initial": stage_report(product, 100.)}
        reports["initial"]["sha256"] = file_sha256(directory/"initial.npz")
        fixed_anchors = []
        stages = [("warmup", 300., 100., 0.)] if args.smoke else [
            ("warmup", 300., 100., 0.), ("growth_6h", 21600., 100., 1.),
            ("growth_12h", 21600., 100., 1.), ("growth_24h", 43200., 100., 1.),
            ("clearwater_36h", 43200., 100., 0.), ("flood_39h", 10800., 200., 0.),
            ("recession_42h", 10800., 50., 0.), ("recovered_48h", 21600., 100., 0.)]
        for name, duration, q, solid_rate in stages:
            started = time.monotonic()
            start = product["metadata"]["physical_time_s"]
            before = product["arrays"]["internal_water_transfer_m3"].copy()
            product = advance(product, [{"id": name, "source": "declared finite engineering forcing; upstream supply only",
                "time_start_s": start, "time_end_s": start+duration, "water_m3": q*duration, "solid_m3": solid_rate*duration}])
            checkpoint = directory/(name+".npz")
            save(checkpoint, product)
            product = load(checkpoint, expected_sha256=file_sha256(checkpoint))
            found = candidate_anchors(product)
            if name == "growth_24h":
                fixed_anchors = found
            tracking = name in ("growth_24h", "clearwater_36h", "flood_39h", "recession_42h", "recovered_48h")
            report = stage_report(product, q, fixed_anchors if tracking else found)
            report.update(runtime_s=time.monotonic()-started, sha256=file_sha256(checkpoint),
                          anchor_tracking="fixed growth_24h neighborhoods" if tracking else "stage discovery")
            report["stage_net_internal_q_m3_s"] = ((product["arrays"]["internal_water_transfer_m3"]-before)/duration).tolist()
            reports[name] = report
            (directory/(name+".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"case": case, "stage": name, "runtime_s": report["runtime_s"],
                "bed_rise_m": report["maximum_offshore_rise_m"], "passed": report["local_material_distributary_passed"]}), flush=True)
        persistent = []
        for index, anchor in enumerate(fixed_anchors):
            checked = [reports[name]["bars"][index]["passed"] for name in
                       ("growth_24h", "clearwater_36h", "flood_39h", "recession_42h", "recovered_48h")]
            persistent.append({"anchor_rc": list(anchor), "all_recorded_stages_passed": all(checked), "stage_passes": checked})
        summary["cases"][case] = {"initial_substrate_solid_m3": initial_stock, "excavated_bulk_m3": excavation,
            "excavated_solid_equivalent_m3": excavation*.65, "excavation_semantics": "removed before simulation, never supplied",
            "stages": reports, "fixed_growth_24h_anchors_rc": fixed_anchors,
            "same_neighborhood_persistence": persistent,
            "persistence_interpretation": "sampled fixed neighborhoods through clear-water stress test; not proof between snapshots"}
        (args.output/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def recheck(parent, output):
    """Recompute diagnostics from hash-pinned states without advancing physics."""
    summary = json.loads((parent/"summary.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    summary["diagnostic_revision"] = "explicit-directed-gate-faces-and-capacity-aware-sea-exit-v2"
    summary["state_directory"] = str(parent.resolve())
    summary["diagnostic_thresholds"] = {
        "new_deposition_relative_to_each_case_initial_bed_m": .1,
        "bar_above_adjacent_channel_m": .05, "gate_radius_rows": 5,
        "cross_section_offsets_cells": [2, 0, -2], "section_separation_m": 60.,
        "single_gate_and_each_path_edge_q_m3_s": "max(0.01, 0.01 * stage source Q)",
        "graph_edge_activation_q_m3_s": .0001,
        "wet_threshold": "saved config bedload.dry_depth_m",
        "flux_time_support": "gates and paths use final coupling-interval signed water transfers; stage_net_internal_q averages entire stage",
        "persistence": "same growth_24h anchor, local spine row +/-1; every recorded later stage must pass, no claim between snapshots"}
    later = ("growth_24h", "clearwater_36h", "flood_39h", "recession_42h", "recovered_48h")
    qs = {"flood_39h": 200., "recession_42h": 50.}
    for case, case_report in summary["cases"].items():
        directory = output/case
        directory.mkdir()
        anchors = case_report["fixed_growth_24h_anchors_rc"]
        for name, old in case_report["stages"].items():
            state = parent/case/(name+".npz")
            sha = old.get("sha256", file_sha256(state))
            product = load(state, expected_sha256=sha)
            selected = anchors if name in later else candidate_anchors(product)
            new = stage_report(product, qs.get(name, 100.), selected)
            new.update({key: value for key, value in old.items() if key not in new})
            new["sha256"] = sha
            new["state_path"] = str(state.resolve())
            case_report["stages"][name] = new
            (directory/(name+".json")).write_text(json.dumps(new, indent=2), encoding="utf-8")
        case_report["same_neighborhood_persistence"] = [
            {"anchor_rc": anchor, "stage_passes": [case_report["stages"][name]["bars"][index]["passed"] for name in later],
             "all_recorded_stages_passed": all(case_report["stages"][name]["bars"][index]["passed"] for name in later)}
            for index, anchor in enumerate(anchors)]
    (output/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-wall-s", type=float, default=240.)
    parser.add_argument("--smoke", action="store_true", help="only 300 physical seconds per control for budget verification")
    parser.add_argument("--recheck", type=Path, help="cold-read an existing trial and save corrected diagnostics to a new output directory")
    args = parser.parse_args()
    if args.recheck:
        recheck(args.recheck, args.output)
    else:
        run(args)


if __name__ == "__main__":
    main()
