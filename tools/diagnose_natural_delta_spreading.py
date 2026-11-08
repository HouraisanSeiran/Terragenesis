"""Read-only cross-shore widths and boundary evidence from saved native states."""
import argparse
import json
from pathlib import Path

import numpy as np


def weighted_span(weights, dx):
    weights = np.maximum(np.asarray(weights, float), 0.)
    total = float(weights.sum())
    if total <= 0.:
        return {"total": total, "central_90_percent_width_m": 0., "range_x_m": None}
    cumulative = np.cumsum(weights)
    first, last = np.searchsorted(cumulative, [.05 * total, .95 * total])
    return {"total": total, "central_90_percent_width_m": float((last - first + 1) * dx),
        "range_x_m": [(float(first) - len(weights) / 2.) * dx, (float(last + 1) - len(weights) / 2.) * dx]}


def analyze(directory):
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    with np.load(directory / "result.npz") as saved:
        a = {name: saved[name] for name in saved.files}
    config = summary["config"]
    dx = config["dx_m"]
    mouth = config["land_length_m"]
    bed, h = a["bed_m"][-1].astype(float), a["depth_m"][-1]
    change = bed - a["initial_bed_m"]
    cell_type = a["cell_type"]
    marine = (a["initial_bed_m"] < 0.) & (cell_type == 0)
    deposition = np.where(marine, np.maximum(change, 0.), 0.) * dx ** 2
    downstream = (np.arange(bed.shape[0]) + .5) * dx - mouth
    qdown = np.where(h > 2.e-6, np.maximum(a["qx_m2_s"][-1], 0.), 0.)
    qcross = np.where(h > 2.e-6, a["qz_m2_s"][-1], 0.)
    bands = []
    for start in np.arange(0., downstream[-1], 50.):
        rows = (downstream >= start) & (downstream < start + 50.)
        if not rows.any():
            continue
        water = weighted_span(qdown[rows].mean(axis=0) * dx, dx)
        dep = weighted_span(deposition[rows].sum(axis=0), dx)
        dep["width_plot_supported_by_at_least_1m3_bulk"] = dep["total"] >= 1.
        rows_dep = (change[rows] > .01) & marine[rows]
        columns = np.flatnonzero(rows_dep.any(axis=0))
        bands.append({"distance_from_mouth_m": [float(start), float(start + 50.)],
            "mean_positive_downstream_discharge_m3_s": water["total"], "water": water,
            "marine_positive_deposition": dep,
            "marine_deposition_over_1cm_envelope_width_m": float((columns[-1] - columns[0] + 1) * dx) if len(columns) else 0.,
            "sum_abs_crossstream_to_positive_downstream_unit_flux_ratio": float(np.abs(qcross[rows]).sum() / max(qdown[rows].sum(), 1.e-12))})
    boundaries = {}
    edge_sets = {"upstream": (0, slice(None)), "downstream": (-1, slice(None)),
        "left": (slice(None), 0), "right": (slice(None), -1)}
    for name, index in edge_sets.items():
        values, counts = np.unique(cell_type[index], return_counts=True)
        boundaries[name] = {"cell_type_counts": dict(zip([str(int(v)) for v in values], [int(n) for n in counts])),
            "max_abs_bed_change_m": float(np.abs(change[index]).max()),
            "initial_bed_range_m": [float(a["initial_bed_m"][index].min()), float(a["initial_bed_m"][index].max())]}
    rr, cc = np.indices(bed.shape)
    distance = np.minimum.reduce([rr, cc, bed.shape[0] - 1 - rr, bed.shape[1] - 1 - cc]) * dx
    side_distance = np.minimum(cc, bed.shape[1] - 1 - cc) * dx
    changed = marine & (change > .01)
    source_flow = a["schedule"][:, 2]
    initial_u = float(source_flow[0] / (config["inlet_width_m"] * config["inlet_depth_m"]))
    phase_net = {}
    for record in summary["phase_records"]:
        phase = record["phase"]
        net = record["injected_bulk_m3"] - record["exported_bulk_m3"] - record["lost_bulk_m3"] + record["inlet_correction_bulk_m3"] + record["raw_residual_bulk_m3"]
        phase_net[phase] = phase_net.get(phase, 0.) + net
    center = bed.shape[1] // 2
    original_land = (a["initial_bed_m"] >= 0.) & (cell_type == 0)
    land_rows = np.flatnonzero(original_land.any(axis=1))
    result = {"directory": str(directory), "saved_steps": summary["steps"], "bands": bands, "boundaries": boundaries,
        "first_packet_q_m3_s": float(source_flow[0]), "scheduled_q_range_m3_s": [float(source_flow.min()), float(source_flow.max())],
        "initial_inlet_u0_m_s": initial_u,
        "initialized_native_velocity_thresholds_m_s": {"mud_deposition": .3 * initial_u, "mud_erosion": 1.5 * initial_u, "sand_erosion": 1.05 * initial_u},
        "upstream_distance_from_stub_end_m": mouth,
        "original_mutable_land_area_m2": float(original_land.sum() * dx ** 2),
        "original_mutable_land_downstream_extent_from_stub_end_m": [float(downstream[land_rows[0]]), float(downstream[land_rows[-1]])],
        "interior_wall_count": int(np.sum(cell_type[1:-1, 1:-1] == -2)),
        "marine_positive_deposition_bulk_m3": float(deposition.sum()),
        "fraction_marine_positive_deposition_within_25m_of_any_domain_edge": float(deposition[distance < 25.].sum() / max(deposition.sum(), 1.e-12)),
        "fraction_marine_positive_deposition_within_25m_of_lateral_edges": float(deposition[side_distance < 25.].sum() / max(deposition.sum(), 1.e-12)),
        "minimum_distance_over_1cm_marine_deposition_to_any_domain_edge_m": float(distance[changed].min()) if changed.any() else None,
        "net_bed_change_by_phase_bulk_m3": phase_net,
        "original_centerline_bed_at_mouth_and_200m_offshore_m": [float(a["initial_bed_m"][int(mouth / dx), center]),
            float(a["initial_bed_m"][int((mouth + 200.) / dx), center])],
        "width_semantics": "central 90% cell span of nonnegative per-column weights; 50m downstream bins; deposited volume is positive net bed change, not sediment flux or new delivered material",
        "water_semantics": "final native cell unit discharge diagnostic, not independent conservative face flux; lateral discharge is present but does not alone prove fan or distributaries"}
    return result


def run(directories, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    reports = [analyze(directory) for directory in directories]
    output.mkdir(parents=True, exist_ok=True)
    (output / "spreading.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for report in reports:
        bands = report["bands"]
        distance = [np.mean(row["distance_from_mouth_m"]) for row in bands]
        name = f"{Path(report['directory']).name} ({report['saved_steps']} steps)"
        axes[0].plot(distance, [row["water"]["central_90_percent_width_m"] for row in bands], marker=".", label=name)
        axes[1].plot(distance, [row["marine_positive_deposition"]["central_90_percent_width_m"]
            if row["marine_positive_deposition"]["width_plot_supported_by_at_least_1m3_bulk"] else np.nan
            for row in bands], marker=".", label=name)
    axes[0].set_title("Final positive downstream water discharge")
    axes[1].set_title("Positive net marine bed deposition\nWidths shown only for bins with >=1 m3 bulk")
    for ax in axes:
        ax.set_xlabel("Distance downstream of inlet-stub end (m)")
        ax.set_ylabel("Central 90% weighted width (m)")
        ax.grid(alpha=.2)
        ax.legend(fontsize=6)
    fig.savefig(output / "measured-spreading-widths.png", dpi=170)
    plt.close(fig)
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.run, args.output), indent=2))
