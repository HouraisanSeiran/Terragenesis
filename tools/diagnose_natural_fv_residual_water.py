"""Cold-read residual water, D4 spill barriers and last-chunk exchange."""
import argparse
import heapq
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.inspect_natural_fv_growth import read_arrays


def spill_surface(bed, cell_type, sea):
    """Minimum maximum bed elevation on any D4 path to open marine cells."""
    nr, nc = bed.shape
    spill = np.full(bed.shape, np.inf)
    queue = []
    for row, col in zip(*np.nonzero(cell_type == -1)):
        spill[row, col] = max(float(bed[row, col]), sea)
        heapq.heappush(queue, (spill[row, col], row, col))
    while queue:
        height, row, col = heapq.heappop(queue)
        if height != spill[row, col]:
            continue
        for r, c in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if 0 <= r < nr and 0 <= c < nc:
                candidate = max(height, float(bed[r, c]))
                if candidate < spill[r, c]:
                    spill[r, c] = candidate
                    heapq.heappush(queue, (candidate, r, c))
    return spill


def analyze(run):
    report = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    if report["status"] != "completed":
        raise ValueError("complete controls only")
    a = read_arrays(run / "result.npz")
    block = read_arrays(sorted(run.glob("chunk-audit-*.npz"))[-1])
    ledgers = json.loads((run / "interval-ledgers.json").read_text(encoding="utf-8"))
    p = report["parameters"]
    t = ledgers[-1]["physical_time_start_s"]
    sea = p["sea_mean"] + p["tide_amplitude"] * np.sin(2 * np.pi * t / p["tide_period"] + np.deg2rad(p["tide_phase"]))
    bed, h = a["bed_m"][-1], a["depth_m"][-1]
    stage = bed + h
    station = np.arange(h.shape[0]) * 5. - 360.
    marine = (a["initial_bed_m"] < 0.) & (station[:, None] >= 0.)
    above = marine & (bed > sea)
    thin = marine & (h > 2.e-6) & (h <= .01)
    spill = spill_surface(bed, a["cell_type"], float(sea))
    trapped = stage < spill - 1.e-10
    padded = np.pad(bed, 1, constant_values=np.inf)
    neighbors = np.minimum.reduce((padded[:-2, 1:-1], padded[2:, 1:-1], padded[1:-1, :-2], padded[1:-1, 2:]))
    blocked = stage <= np.maximum(bed, neighbors) + 1.e-12
    concentration = np.divide(a["suspended_solid_m3"][-1], h * 25., out=np.zeros_like(h), where=h > 0.)
    fields = {"above_sea_original_marine": above, "marine_thin_water": thin}
    results = {}
    for name, mask in fields.items():
        ids = mask.ravel()
        left, right, cells = block["face_left"], block["face_right"], block["boundary_cell"]
        transfer = block["water_internal_transfer_m3"]
        entering = np.where(~ids[left] & ids[right], transfer, np.where(ids[left] & ~ids[right], -transfer, 0.))
        entering_boundary = np.where(ids[cells], -block["water_boundary_transfer_m3"], 0.)
        incoming = np.maximum(entering, 0.).sum() + np.maximum(entering_boundary, 0.).sum()
        outgoing = -np.minimum(entering, 0.).sum() - np.minimum(entering_boundary, 0.).sum()
        percentiles = [0., 5., 25., 50., 75., 95., 100.]
        results[name] = {"cell_count": int(mask.sum()), "area_m2": float(mask.sum() * 25.),
            "depth_percentiles_0_5_25_50_75_95_100_m": np.percentile(h[mask], percentiles).tolist() if mask.any() else None,
            "initial_depth_percentiles_m": np.percentile(a["depth_m"][0][mask], percentiles).tolist() if mask.any() else None,
            "final_water_volume_m3": float(h[mask].sum() * 25.),
            "last_chunk_water_volume_change_m3": float((block["after_depth_m"] - block["before_depth_m"])[mask].sum() * 25.),
            "last_chunk_net_face_incoming_partition_m3": float(incoming), "last_chunk_net_face_outgoing_partition_m3": float(outgoing),
            "last_chunk_source_m3": float(block["water_forcing_volume_m3"][ids].sum()),
            "stage_below_D4_spill_area_m2": float((mask & trapped).sum() * 25.),
            "no_lower_immediate_wet_face_area_m2": float((mask & blocked).sum() * 25.),
            "depth_exactly_initial_within_1e12_area_m2": float((mask & (abs(h - a["depth_m"][0]) <= 1.e-12)).sum() * 25.),
            "last_chunk_depth_change_max_abs_m": float(abs(block["after_depth_m"] - block["before_depth_m"])[mask].max()) if mask.any() else None,
            "last_chunk_bed_change_max_abs_m": float(abs(block["after_bed_m"] - block["before_bed_m"])[mask].max()) if mask.any() else None,
            "maximum_suspended_volume_concentration": float(concentration[mask].max()) if mask.any() else None}
    bins = np.array([0., 2.e-6, 1.e-4, .001, .01, .1, 1., np.inf])
    hist = [int(np.count_nonzero(marine & (h > lo) & (h <= hi))) for lo, hi in zip(bins[:-1], bins[1:])]
    return {"run": str(run), "river_q_m3_s": p["river_q"], "wave_height_m": p["wave_height"],
        "absolute_final_time_s": float(a["time_s"][-1]), "actual_last_held_sea_level_m": float(sea),
        "last_chunk_duration_s": float(block["absolute_time_end_s"] - block["absolute_time_start_s"]),
        "marine_actual_dry_area_m2": float(np.count_nonzero(marine & (h <= 2.e-6)) * 25.),
        "marine_depth_bin_edges_m": [0., 2.e-6, 1.e-4, .001, .01, .1, 1., "inf"],
        "marine_depth_bin_cell_counts": hist, "regions": results,
        "method": "Actual saved water volume; D4 minimax spill to open marine cells at last held sea. Last chunk signed-net face partitions are not substep gross exchange. Spill below-stage classification does not prove absence of kinetic overtopping or changing forcing."}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    results = [analyze(run) for run in args.run]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
