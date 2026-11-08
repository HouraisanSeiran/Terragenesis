"""Cold-read diagnostics for the independent wide-inlet short experiment."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import binary_propagation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256


def measure(arrays, summary):
    initial = arrays["initial_bed_m"].astype(float)
    base = arrays["source_base_bed_m"]
    bed = arrays["bed_m"].astype(float)
    depth = arrays["depth_m"].astype(float)
    stage = arrays["stage_m"].astype(float)
    change = bed[-1] - initial
    positive = np.maximum(change, 0.) * 25.
    marine = base < 0.
    land = ~marine
    side = np.zeros(initial.shape, bool)
    side[:, :5] = True
    side[:, -5:] = True
    inlet = arrays["inlet_columns"]
    landward = arrays["station_m"] < 0.
    core = np.zeros_like(landward)
    core[:, inlet] = True
    floodplain = landward & ~core & (base >= 0.)
    frames = []
    for index in range(len(bed)):
        dry = (bed[index] >= 0.) & (depth[index] <= 2.e-6)
        linked = binary_propagation(land & dry, mask=dry)
        sections = []
        for row in range(initial.shape[0]):
            area = float(depth[index, row].sum() * 5.)
            sections.append({"station_m": float(arrays["station_m"][row, 0]),
                "signed_total_q_m3_s": float(arrays["qx_m2_s"][index, row].sum() * 5.),
                "positive_total_q_m3_s": float(np.maximum(arrays["qx_m2_s"][index, row], 0.).sum() * 5.),
                "signed_core_q_m3_s": float(arrays["qx_m2_s"][index, row, inlet].sum() * 5.),
                "total_wet_area_m2": area,
                "core_wet_area_m2": float(depth[index, row, inlet].sum() * 5.),
                "center_bed_m": float(bed[index, row, 120]), "center_depth_m": float(depth[index, row, 120]),
                "center_stage_m": float(stage[index, row, 120]),
                "core_mean_stage_m": float(stage[index, row, inlet].mean())})
        frames.append({"frame": index, "time_s": float(arrays["time_s"][index]),
            "water_volume_m3": float(depth[index].sum() * 25.),
            "landward_water_volume_m3": float(depth[index][landward].sum() * 25.),
            "landward_outside_core_wet_area_m2": float(np.count_nonzero(floodplain & (depth[index] > .01)) * 25.),
            "above_zero_original_marine_area_m2": float(np.count_nonzero(marine & (bed[index] >= 0.)) * 25.),
            "actual_dry_original_marine_area_m2": float(np.count_nonzero(marine & dry) * 25.),
            "actual_dry_connected_original_marine_area_m2": float(np.count_nonzero(marine & linked) * 25.),
            "inlet_measured_q_m3_s": float(arrays["qx_m2_s"][index, 0, inlet].sum() * 5.),
            "inlet_stage_maximum_boundary_error_m": float(abs(stage[index, 0, inlet] - summary["geometry"]["inlet"]["stage_m"]).max()),
            "inlet_correction_bulk_m3": float(arrays["inlet_correction_bulk_m3"][index]), "sections": sections})
    ledger = summary["ledger_bulk_m3"]
    bed_net = float(change.sum() * 25.)
    raw = bed_net - ledger["injected_bulk_m3"] + ledger["exported_bulk_m3"] + ledger["lost_bulk_m3"] - ledger["inlet_correction_bulk_m3"]
    positive_marine = float(positive[marine].sum())
    solid_input = float(arrays["cumulative_input_solid_m3"][-1])
    expected_solid = 0. if summary["zero_supply"] else float(arrays["schedule"][:summary["steps"], 3].sum())
    material = summary["materials"]
    q = arrays["schedule"][:summary["steps"], 2]
    return {"schema": "wide-natural-cold-read-diagnostics-v1", "steps": summary["steps"],
        "scope": "short parcel-mechanism inspection; no FV water budget or mature delta acceptance",
        "bed_budget": {"measured_net_bulk_m3": bed_net, "archived_net_bulk_m3": ledger["bed_change_bulk_m3"],
            "recomputed_raw_numerical_residual_bulk_m3": float(raw),
            "archived_raw_numerical_residual_bulk_m3": ledger["raw_residual_bulk_m3"],
            "raw_residual_reconstruction_mismatch_bulk_m3": float(raw - ledger["raw_residual_bulk_m3"]),
            "interpretation": "reconstruction includes raw numerical residual; matching records do not imply zero numerical error",
            "injected_boundary_solid_m3": solid_input, "scheduled_solid_for_run_m3": expected_solid,
            "delivered_solid_error_m3": solid_input - expected_solid,
            "minimum_floor_margin_m": float(np.min(bed - arrays["source_floor_m"])),
            "inlet_correction_frame_sum_bulk_m3": float(arrays["inlet_correction_bulk_m3"].sum()),
            "archived_ledger": ledger},
        "deposition": {"positive_bulk_m3": float(positive.sum()), "positive_original_marine_bulk_m3": positive_marine,
            "positive_original_land_bulk_m3": float(positive[land].sum()),
            "marine_side25m_positive_bulk_m3": float(positive[marine & side].sum()),
            "marine_side25m_positive_fraction": float(positive[marine & side].sum() / positive_marine) if positive_marine else None,
            "side_edge_cells_rise_over1cm": int(np.count_nonzero(change[:, [0, -1]] > .01)),
            "maximum_bed_rise_m": float(change.max()), "maximum_bed_cut_m": float(-min(change.min(), 0.)),
            "construction_cut_excluded_from_dynamic_budget": True},
        "material_behavior": {"reference": material,
            "native_velocity_cap_range_m_s": [float(np.min(2. * q / 320.)), float(np.max(2. * q / 320.))],
            "native_sand_capacity_uses_changed_inlet_u0": True,
            "interpretation": "absolute sediment thresholds retained; wider inlet still changes native speed cap and capacity normalization"},
        "frames": frames, "all_state_arrays_finite": all(np.isfinite(arrays[key]).all() for key in
            ("bed_m", "depth_m", "stage_m", "qx_m2_s", "qz_m2_s"))}


def render(output, arrays, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    extent = [-602.5, 597.5, 737.5, -362.5]
    fig, axes = plt.subplots(2, 3, figsize=(18, 11), constrained_layout=True)
    change = arrays["bed_m"][-1].astype(float) - arrays["initial_bed_m"]
    limit = max(float(abs(change).max()), .01)
    for ax, field, title, cmap, norm in (
            (axes[0, 0], arrays["bed_m"][-1], "Actual final bed", "terrain", None),
            (axes[0, 1], arrays["depth_m"][-1], "Actual final water depth", "Blues", None),
            (axes[0, 2], change, "Dynamic bed change (initial construction excluded)", "RdBu_r", TwoSlopeNorm(0., -limit, limit))):
        im = ax.imshow(field, extent=extent, cmap=cmap, norm=norm)
        ax.axhline(0., color="black", linewidth=.6)
        ax.set(xlabel="Cross stream (m)", ylabel="Station from mouth (m)", title=title)
        fig.colorbar(im, ax=ax, shrink=.8, label="m")
    for index in (0, -1):
        frame = report["frames"][index]
        sections = frame["sections"]
        station = [s["station_m"] for s in sections]
        label = "Initial" if index == 0 else "Final"
        axes[1, 0].plot(station, [s["center_stage_m"] for s in sections], label=label + " stage")
        axes[1, 0].plot(station, [s["center_bed_m"] for s in sections], linestyle="--", label=label + " bed")
        axes[1, 1].plot(station, [s["signed_total_q_m3_s"] for s in sections], label=label + " whole width")
        axes[1, 1].plot(station, [s["signed_core_q_m3_s"] for s in sections], linestyle="--", label=label + " 80m core")
    axes[1, 0].set(xlabel="Station (m)", ylabel="Elevation (m)", title="Centerline bed and actual water surface")
    axes[1, 1].set(xlabel="Station (m)", ylabel="Signed discharge (m3/s)", title="Downstream discharge; parcel routing diagnostic")
    for ax in axes[1, :2]:
        ax.legend(fontsize=8)
        ax.axvline(0., color="gray", linewidth=.6)
    times = [f["time_s"] for f in report["frames"]]
    axes[1, 2].plot(times, [f["landward_water_volume_m3"] for f in report["frames"]], label="Landward water")
    axes[1, 2].set(xlabel="Compressed model seconds", ylabel="Water volume (m3)", title="Free interior water response")
    axes[1, 2].legend()
    fig.savefig(output / "actual-process.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads((args.run / "summary.json").read_text(encoding="utf-8"))
    if summary["schema"] != "wide-independent-natural-short-validation-v1":
        raise ValueError("wide independent short result required")
    identities = {path: file_sha256(ROOT / path) == digest for path, digest in summary["implementation_hashes"].items()}
    if not all(identities.values()):
        raise ValueError("run implementation identity changed")
    with np.load(args.run / "result.npz") as saved:
        arrays = {key: saved[key] for key in saved.files}
    report = measure(arrays, summary)
    report.update(run=str(args.run), result_sha256=file_sha256(args.run / "result.npz"),
        summary_sha256=file_sha256(args.run / "summary.json"), implementation_identity_matches=identities,
        diagnostic_implementation_sha256=file_sha256(Path(__file__)))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "diagnostics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render(args.output, arrays, report)
    print(json.dumps({key: value for key, value in report.items() if key not in ("frames", "implementation_identity_matches")}, indent=2))


if __name__ == "__main__":
    main()
