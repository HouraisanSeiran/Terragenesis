"""Read completed FV growth evidence for spreading, inundation and edge truncation."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256
from tools.diagnose_natural_delta_spreading import weighted_span
from tools.inspect_natural_fv_growth import read_arrays


def flow_bands(q):
    """Separated high-flow intervals are candidates, not certified distributaries."""
    total = float(q.sum())
    if total <= 1.e-8:
        return []
    mask = q >= .1 * q.max()
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.flatnonzero(mask & ~np.r_[mask[1:], False]) + 1
    return [{"cross_range_m": [float(first * 5. - 602.5), float(last * 5. - 602.5)],
        "width_m": float((last - first) * 5.), "flow_fraction": float(q[first:last].sum() / total)}
        for first, last in zip(starts, ends) if q[first:last].sum() >= .05 * total]


def analyze(run):
    summary_path = run / "summary.json"
    if not summary_path.exists():
        raise ValueError("completed summary required; active run files are not read: " + str(run))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("status") not in ("completed", "completed-prefix-after-rejected-step"):
        raise ValueError("only completed or explicitly recovered prefix evidence is supported")
    a = read_arrays(run / "result.npz")
    bed, h = a["bed_m"][-1], a["depth_m"][-1]
    nr, nc = h.shape
    station = np.arange(nr) * 5. - 360.
    sea_side = np.broadcast_to((station >= 0.)[:, None], h.shape)
    original_sea = sea_side & (a["initial_bed_m"] < 0.)
    inundation_samples = [{"time_s": float(time_s),
        "dry_area_m2": float(np.count_nonzero(original_sea & (depth <= 2.e-6)) * 25.),
        "thin_area_m2": float(np.count_nonzero(original_sea & (depth > 2.e-6) & (depth <= .01)) * 25.)}
        for time_s, depth in zip(a["time_s"], a["depth_m"], strict=True)]
    max_dry_area = max(sample["dry_area_m2"] for sample in inundation_samples)
    max_dry_times = [sample["time_s"] for sample in inundation_samples if sample["dry_area_m2"] == max_dry_area]
    momentum = a["momentum_m2_s"][-1].reshape(nr, nc, 2)
    q = np.where(h > 2.e-6, np.maximum(momentum[..., 1], 0.) * 5., 0.)
    deposited = np.zeros_like(h)
    boundary_exports = {"left": 0., "right": 0., "downstream": 0., "upstream": 0.}
    fixed_edge_sink = np.zeros(h.size)
    for path in sorted(run.glob("chunk-audit-*.npz")):
        with np.load(path) as block:
            deposited += block["suspended_deposited_solid_m3"].reshape(h.shape)
            fixed_edge_sink += block["bedload_fixed_marine_edge_export_solid_m3"]
            cells = block["boundary_cell"]
            export = block["suspended_boundary_export_solid_m3"] + block["bedload_boundary_export_solid_m3"]
            row, col = cells // nc, cells % nc
            # Corner contributions may occur in two named edges; total is reported separately.
            for name, mask in (("left", col == 0), ("right", col == nc - 1), ("downstream", row == nr - 1), ("upstream", row == 0)):
                boundary_exports[name] += float(export[mask].sum())
    ledger = json.loads((run / "interval-ledgers.json").read_text(encoding="utf-8"))
    last_forcing_time = ledger[-1]["physical_time_start_s"]
    parameters = summary["parameters"]
    sea_level = parameters["sea_mean"] + parameters["tide_amplitude"] * np.sin(2. * np.pi * last_forcing_time / parameters["tide_period"] + np.deg2rad(parameters["tide_phase"]))
    analytic_final_sea = parameters["sea_mean"] + parameters["tide_amplitude"] * np.sin(2. * np.pi * float(a["time_s"][-1]) / parameters["tide_period"] + np.deg2rad(parameters["tide_phase"]))
    delta = bed - a["bed_m"][0]
    positive_bulk = np.maximum(delta, 0.) * 25.
    side = np.zeros_like(h, bool)
    side[:, :5] = True
    side[:, -5:] = True
    end = np.zeros_like(h, bool)
    end[-5:] = True
    dry = h <= 2.e-6
    thin = (h > 2.e-6) & (h <= .01)
    above_sea_wet = original_sea & (bed > sea_level) & ~dry
    newly_above = above_sea_wet & (a["bed_m"][0] <= sea_level)
    bands = []
    profiles = []
    split_rows = []
    for row in range(nr):
        candidates = flow_bands(q[row])
        multiple = len(candidates) >= 2 and max(b["flow_fraction"] for b in candidates) <= .85
        split_rows.append(multiple and station[row] >= 0.)
        water_span = weighted_span(q[row], 5.)
        settling_span = weighted_span(deposited[row], 5.)
        profiles.append({"station_m": float(station[row]), "positive_downstream_q_m3_s": float(q[row].sum()),
            "flow_central90_width_m": water_span["central_90_percent_width_m"],
            "flow_effective_width_m": float(5. * q[row].sum() ** 2 / np.square(q[row]).sum()) if np.square(q[row]).sum() else 0.,
            "settling_solid_m3": float(deposited[row].sum()), "settling_central90_width_m": settling_span["central_90_percent_width_m"],
            "lateral25m_positive_flow_fraction": float(q[row, :5].sum() + q[row, -5:].sum()) / max(float(q[row].sum()), 1.e-12),
            "high_flow_bands": candidates, "multiple_high_flow_bands": bool(multiple)})
    split_rows = np.asarray(split_rows)
    starts = np.flatnonzero(split_rows & ~np.r_[False, split_rows[:-1]])
    ends = np.flatnonzero(split_rows & ~np.r_[split_rows[1:], False]) + 1
    for first, last in zip(starts, ends):
        if last - first >= 3:
            bands.append([float(station[first]), float(station[last - 1] + 5.)])
    gross = float(deposited.sum())
    report = {"schema": "completed-fv-natural-morphology-v1", "run": str(run), "source_status": summary["status"],
        "result_sha256": file_sha256(run / "result.npz"), "physical_start_end_s": [float(a["time_s"][0]), float(a["time_s"][-1])],
        "new_input_solid_m3": summary["injected_solid_m3"], "initial_suspended_solid_m3": float(a["suspended_solid_m3"][0].sum()),
        "remaining_source_solid_m3": summary["remaining_finite_source_solid_m3"],
        "gross_suspended_settling_solid_m3": gross, "landward_gross_settling_solid_m3": float(deposited[~sea_side].sum()),
        "seaward_gross_settling_solid_m3": float(deposited[sea_side].sum()),
        "seaward_final_suspended_solid_m3": float(a["suspended_solid_m3"][-1][sea_side].sum()),
        "lateral25m_settling_fraction": float(deposited[side].sum() / gross) if gross else 0.,
        "downstream25m_settling_fraction": float(deposited[end].sum() / gross) if gross else 0.,
        "lateral25m_final_suspended_fraction": float(a["suspended_solid_m3"][-1][side].sum() / max(a["suspended_solid_m3"][-1].sum(), 1.e-12)),
        "lateral25m_positive_bed_bulk_fraction": float(positive_bulk[side].sum() / max(positive_bulk.sum(), 1.e-12)),
        "boundary_solid_exports_by_edge_m3": boundary_exports, "boundary_edge_corner_note": "corner-cell faces may be counted in both named edges; do not sum these labels as total export",
        "fixed_marine_edge_bed_sink_solid_m3": float(fixed_edge_sink.sum()),
        "final_imposed_sea_level_m": float(sea_level), "actual_sea_dry_area_m2": float(np.count_nonzero(original_sea & dry) * 25.),
        "final_imposed_sea_sample_time_s": float(last_forcing_time),
        "analytic_tide_at_final_physical_time_m": float(analytic_final_sea),
        "final_held_minus_analytic_sea_level_m": float(sea_level - analytic_final_sea),
        "original_sea_bed_above_analytic_final_sea_still_wet_area_m2": float(np.count_nonzero(original_sea & (bed > analytic_final_sea) & ~dry) * 25.),
        "sea_thin_water_area_m2": float(np.count_nonzero(original_sea & thin) * 25.),
        "saved_state_sea_inundation": {"samples": inundation_samples,
            "max_dry_area_m2": max_dry_area, "max_dry_area_first_time_s": max_dry_times[0],
            "max_dry_area_times_s": max_dry_times,
            "any_saved_state_has_dry_sea": bool(max_dry_area > 0.),
            "final_state_has_dry_sea": bool(inundation_samples[-1]["dry_area_m2"] > 0.),
            "final_dry_area_m2": inundation_samples[-1]["dry_area_m2"],
            "scope": "Only states saved in result.npz, including the initial state; maximum and exposure presence refer to these samples. Unsaved times may have different areas; these samples do not establish continuous-time exposure or its absence.",
            "original_sea_definition": "station >= 0m and initial_bed_m < 0m; cell area 25m2",
            "thresholds_m": {"dry_depth_max": 2.e-6, "thin_depth_min_exclusive": 2.e-6, "thin_depth_max": .01}},
        "original_sea_bed_above_sea_but_still_wet_area_m2": float(np.count_nonzero(above_sea_wet) * 25.),
        "newly_raised_above_sea_still_wet_area_this_run_m2": float(np.count_nonzero(newly_above) * 25.),
        "above_sea_still_wet_depth_p50_p95_m": np.percentile(h[above_sea_wet], [50., 95.]).tolist() if above_sea_wet.any() else None,
        "above_sea_still_wet_maximum_bed_elevation_over_sea_m": float((bed - sea_level)[above_sea_wet].max()) if above_sea_wet.any() else None,
        "multiple_high_flow_band_station_ranges_ge15m": bands, "profiles": profiles,
        "marine_rows_flow90_width_gt1000m_station_ranges_m": [float(station[row]) for row in range(nr)
            if station[row] >= 0. and profiles[row]["flow_central90_width_m"] > 1000.],
        "semantics": {"settling": "gross scalar settling includes inherited suspended material; not a tracer of only this run's new source",
            "flow": "actual final cell momentum transverse section; positive downstream component, not an independent face-flux audit",
            "bands": "contiguous columns >=10% row peak carrying >=5% row flow; multiple bands require largest <=85%, sustained >=3 rows. Candidate separation, not verified distributary topology or sustained channels",
            "width": "existing weighted_span central 90% cell span; one 5m row per observation",
            "dry": "actual h<=2e-6m; thin water 2e-6<h<=.01m; bed>imposed sea does not establish dry land"}}
    report["semantics"]["sea_level"] = "Final imposed boundary level is sampled at the last coupling interval start and held through its end, matching the frozen runner. Analytic tide at final physical time is reported separately; a different adaptive interval can create a small held-sea difference. Neither level substitutes for actual depth in dry-area measurements."
    report["decision_evidence"] = {
        "drawdown_can_test_above_sea_bed": bool(above_sea_wet.any()),
        "material_has_reached_marine_domain": bool(deposited[sea_side].sum() > 1. or a["suspended_solid_m3"][-1][sea_side].sum() > 1.),
        "side_truncation_screen_gt5pct_settling_or_suspended": bool(report["lateral25m_settling_fraction"] > .05 or report["lateral25m_final_suspended_fraction"] > .05),
        "multiple_concentrated_band_candidates_present": bool(bands),
        "interpretation": "Use actual above-sea wet area to motivate drawdown; material at sea establishes transit, not a delta. Edge screens are descriptive thresholds, not acceptance. More sediment cannot establish emergence while water remains above the bed."}
    return report, {"bed": bed, "depth": h, "q": q, "deposited": deposited, "above_sea_wet": above_sea_wet, "sea_level": sea_level}


def render(run, output):
    report, fields = analyze(run)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output.mkdir(parents=True, exist_ok=False)
    (output / "morphology.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(2, 3, figsize=(18, 11), constrained_layout=True)
    extent = [-602.5, 597.5, 737.5, -362.5]
    for ax, field, title, cmap, label in ((axes[0, 0], fields["q"], "Actual positive downstream discharge", "Blues", "m3/s per cell width"),
            (axes[0, 1], fields["deposited"], "Gross suspended settling during this run", "viridis", "Solid m3/cell"),
            (axes[0, 2], fields["depth"], "Actual final depth", "Blues", "m")):
        im = ax.imshow(field, extent=extent, cmap=cmap)
        fig.colorbar(im, ax=ax, label=label, shrink=.8)
        ax.axhline(0., color="black", linewidth=.5)
        ax.set(title=title, xlabel="Cross stream (m)", ylabel="Station (m)")
    profiles = report["profiles"]
    station = [p["station_m"] for p in profiles]
    for key, label in (("flow_central90_width_m", "90% downstream flow"), ("flow_effective_width_m", "Effective flow width"),
            ("settling_central90_width_m", "90% settling")):
        axes[1, 0].plot(station, [p[key] if p["settling_solid_m3"] > 1.e-6 or "settling" not in key else np.nan for p in profiles], label=label)
    axes[1, 0].set(title="Actual flow and settling widths", xlabel="Station (m)", ylabel="m")
    axes[1, 0].legend()
    axes[1, 1].plot(station, [len(p["high_flow_bands"]) for p in profiles], label="High-flow bands")
    for left, right in report["multiple_high_flow_band_station_ranges_ge15m"]:
        axes[1, 1].axvspan(left, right, color="#e8bd55", alpha=.4)
    axes[1, 1].set(title="Separated-flow candidates (not topology proof)", xlabel="Station (m)", ylabel="Band count")
    classes = np.zeros(fields["depth"].shape)
    classes[fields["depth"] <= 2.e-6] = 1
    classes[(fields["depth"] > 2.e-6) & (fields["depth"] <= .01)] = 2
    classes[fields["above_sea_wet"]] = 3
    from matplotlib.colors import ListedColormap, BoundaryNorm
    im = axes[1, 2].imshow(classes, extent=extent, cmap=ListedColormap(["#4696bb", "#7a9a63", "#ecc975", "#b66b75"]), norm=BoundaryNorm(np.arange(-.5, 4.5), 4))
    bar = fig.colorbar(im, ax=axes[1, 2], ticks=range(4), shrink=.8)
    bar.ax.set_yticklabels(["Wet", "Dry <=2e-6m", "Thin <=1cm", "Bed>sea, still wet"])
    axes[1, 2].set(title="Actual inundation versus bed elevation", xlabel="Cross stream (m)", ylabel="Station (m)")
    fig.savefig(output / "morphology-diagnosis.png", dpi=170)
    plt.close(fig)
    return {key: value for key, value in report.items() if key not in ("profiles", "semantics")}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(render(args.run, args.output), indent=2))
