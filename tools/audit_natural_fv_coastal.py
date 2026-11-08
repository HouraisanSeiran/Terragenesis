"""Independent saved-array finite-bed/water audits and coastal comparison plots."""
import argparse
import json
from pathlib import Path

import numpy as np


def audit(directory):
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    with np.load(directory / "result.npz") as saved:
        a = {key: saved[key] for key in saved.files}
    initial_depth = a["depth_m"][0]
    cell_area = summary["metadata"]["initial_volume_m3"] / initial_depth.sum()
    porosity = summary["sediment_config"]["porosity"]
    factor = cell_area * (1. - porosity)
    floor = a["source_floor_m"]
    bed = a["bed_m"]
    inventory = (bed - floor) * factor
    if np.min(bed - floor) < -1.e-10:
        raise AssertionError("source floor violated")
    fixed = a["fixed_boundary_mask"].ravel()
    left, right, cells = a["face_left"], a["face_right"], a["boundary_cell"]
    sea = np.zeros(initial_depth.size, bool)
    sea[cells[a["boundary_kind"] == 2]] = True
    maxima = {key: 0. for key in ("cell_water_m3", "cell_momentum_volume_m4_s", "cell_solid_m3",
        "water_depth_handoff_m", "water_momentum_handoff_m2_s", "saved_snapshot_depth_m", "saved_snapshot_momentum_m2_s",
        "source_water_depth_m", "source_water_momentum_m2_s", "saved_sediment_bed_m")}
    sediment_exports = []
    sediment_residuals = []
    gross_internal = []
    minimum_floor_margin = float(np.min(bed - floor))
    previous_h = initial_depth.ravel()
    previous_momentum = np.column_stack([a["momentum_x_m2_s"][0].ravel(), a["momentum_z_m2_s"][0].ravel()])
    with np.load(summary["water_packet"]) as original:
        maxima["source_water_depth_m"] = float(abs(original["depth_after_m"] - previous_h).max())
        maxima["source_water_momentum_m2_s"] = float(abs(original["momentum_after"] - previous_momentum).max())
    for number in range(len(a["time_s"]) - 1):
        with np.load(directory / "intervals" / f"{number:05d}-water.npz") as saved:
            p = {key: saved[key] for key in saved.files}
        with np.load(directory / "intervals" / f"{number:05d}-sediment.npz") as saved:
            s = {key: saved[key] for key in saved.files}
        maxima["water_depth_handoff_m"] = max(maxima["water_depth_handoff_m"], float(abs(p["depth_before_m"] - previous_h).max()))
        maxima["water_momentum_handoff_m2_s"] = max(maxima["water_momentum_handoff_m2_s"], float(abs(p["momentum_before"] - previous_momentum).max()))
        net_water = p["forcing_volume_m3"].copy()
        np.add.at(net_water, left, -p["internal_transfer_m3"])
        np.add.at(net_water, right, p["internal_transfer_m3"])
        np.add.at(net_water, cells, -p["boundary_transfer_m3"])
        residual_water = (p["depth_after_m"] - p["depth_before_m"]) * cell_area - net_water
        maxima["cell_water_m3"] = max(maxima["cell_water_m3"], float(abs(residual_water).max()))
        net_momentum = np.zeros_like(p["momentum_after"])
        np.add.at(net_momentum, left, -p["internal_momentum_transfer"])
        np.add.at(net_momentum, right, p["internal_momentum_transfer"])
        np.add.at(net_momentum, cells, -p["boundary_momentum_transfer"])
        # Water execution stores cell pressure/drag impulses per area, while
        # conservative face momentum transfers already include face width.
        net_momentum += cell_area * (p["bed_momentum_change"] + p["manning_momentum_change"])
        residual_momentum = (p["momentum_after"] - p["momentum_before"]) * cell_area - net_momentum
        maxima["cell_momentum_volume_m4_s"] = max(maxima["cell_momentum_volume_m4_s"], float(abs(residual_momentum).max()))
        transfer = s["internal_transfer_solid_m3"]
        donor, receiver = np.where(transfer >= 0., left, right), np.where(transfer >= 0., right, left)
        sink = fixed[receiver] & sea[receiver]
        net_solid = np.zeros(initial_depth.size)
        np.add.at(net_solid, donor, -abs(transfer))
        np.add.at(net_solid, receiver, abs(transfer) * ~sink)
        np.add.at(net_solid, cells, -s["boundary_export_solid_m3"])
        sink_reconstructed = np.zeros(initial_depth.size)
        np.add.at(sink_reconstructed, receiver, abs(transfer) * sink)
        np.testing.assert_allclose(sink_reconstructed, s["fixed_marine_edge_export_solid_m3"], atol=1.e-11, rtol=1.e-12)
        actual_solid = (inventory[number + 1] - inventory[number]).ravel()
        maxima["cell_solid_m3"] = max(maxima["cell_solid_m3"], float(abs(actual_solid - net_solid).max()))
        export = float(s["boundary_export_solid_m3"].sum() + sink_reconstructed.sum())
        sediment_exports.append(export)
        sediment_residuals.append(float(actual_solid.sum() + export))
        gross_internal.append(float(abs(transfer).sum()))
        np.testing.assert_array_equal(bed[number + 1].ravel()[fixed], bed[0].ravel()[fixed])
        maxima["saved_sediment_bed_m"] = max(maxima["saved_sediment_bed_m"], float(abs(s["bed_m"] - bed[number + 1]).max()))
        snapshot_m = np.column_stack([a["momentum_x_m2_s"][number + 1].ravel(), a["momentum_z_m2_s"][number + 1].ravel()])
        maxima["saved_snapshot_depth_m"] = max(maxima["saved_snapshot_depth_m"], float(abs(p["depth_after_m"] - a["depth_m"][number + 1].ravel()).max()))
        maxima["saved_snapshot_momentum_m2_s"] = max(maxima["saved_snapshot_momentum_m2_s"], float(abs(p["momentum_after"] - snapshot_m).max()))
        previous_h, previous_momentum = p["depth_after_m"], p["momentum_after"]
    for key, error in maxima.items():
        if error > 1.e-8:
            raise AssertionError(f"{key} closure failed: {error}")
    total_export = sum(sediment_exports)
    total_residual = float(inventory[-1].sum() - inventory[0].sum() + total_export)
    if abs(total_residual) > 1.e-7:
        raise AssertionError("global saved finite inventory/export mismatch")
    np.testing.assert_allclose(total_export, summary["sediment_exported_solid_m3"], atol=1.e-9, rtol=1.e-12)
    result = {"directory": str(directory), "duration_physical_s": float(a["time_s"][-1]),
        "absolute_start_time_s": float(a["absolute_time_s"][0]), "absolute_end_time_s": float(a["absolute_time_s"][-1]),
        "water_and_momentum_continuous_between_bed_updates": True, "original_source_floor_respected": True,
        "fixed_boundary_bed_unchanged": True, "maximum_abs_independent_residuals": maxima,
        "minimum_floor_margin_m": minimum_floor_margin, "initial_inventory_solid_m3": float(inventory[0].sum()),
        "final_inventory_solid_m3": float(inventory[-1].sum()), "exported_solid_m3": total_export,
        "external_new_sediment_solid_m3": 0., "global_solid_residual_m3": total_residual,
        "gross_internal_transfer_solid_m3": sum(gross_internal),
        "gross_internal_semantics": "sum of internal movements; the same grains may move repeatedly; this is neither new supply nor net deposition",
        "maximum_abs_bed_change_from_initial_m": float(abs(bed[-1] - bed[0]).max()),
        "interval_export_solid_m3": sediment_exports, "interval_solid_residual_m3": sediment_residuals,
        "wave_height_boundary_m": summary["sediment_config"]["wave_height_m"],
        "scope": "short physical-time diagnostic only; not annual delta maturity or calibrated shoreline evolution"}
    (directory / "independent-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result, a, summary


def compare(wave, calm, output):
    first, a, sa = audit(wave)
    second, b, sb = audit(calm)
    for key in ("parent_sha256", "water_packet_sha256", "physical_start_time_s", "physical_end_time_s", "forcing"):
        if sa[key] != sb[key]:
            raise AssertionError("different comparison initial conditions/forcing: " + key)
    for key in ("bed_m", "depth_m", "momentum_x_m2_s", "momentum_z_m2_s"):
        np.testing.assert_array_equal(a[key][0], b[key][0])
    np.testing.assert_array_equal(a["source_floor_m"], b["source_floor_m"])
    output.mkdir(parents=True, exist_ok=True)
    difference = {key: float(abs(a[key][-1] - b[key][-1]).max())
        for key in ("bed_m", "depth_m", "momentum_x_m2_s", "momentum_z_m2_s")}
    report = {"wave": first, "no_wave": second, "identical_initial_bed_water_momentum_floor_and_forcing": True,
        "final_wave_minus_calm_max_abs_differences": difference,
        "duration_physical_s": first["duration_physical_s"],
        "interpretation": "explicit boundary wave stirring changes finite-bed transport and subsequent water; this short comparison adds no river sediment"}
    (output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    shape = a["bed_m"].shape[1:]
    area = sa["metadata"]["initial_volume_m3"] / a["depth_m"][0].sum()
    dx = np.sqrt(area)
    extent = [-shape[1] * dx / 2., shape[1] * dx / 2., shape[0] * dx, 0.]
    fields = [a["bed_m"][-1] - a["bed_m"][0], b["bed_m"][-1] - b["bed_m"][0], a["bed_m"][-1] - b["bed_m"][-1],
        a["depth_m"][-1] - b["depth_m"][-1], a["momentum_x_m2_s"][-1] - b["momentum_x_m2_s"][-1],
        a["momentum_z_m2_s"][-1] - b["momentum_z_m2_s"][-1]]
    titles = ["Wave-on bed change (m)", "Wave-off bed change (m)", "Wave-on minus off bed (m)",
        "Water depth difference (m)", "Cross-stream unit discharge difference (m2/s)", "Downstream unit discharge difference (m2/s)"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 12))
    for index, (ax, field, title) in enumerate(zip(axes.ravel(), fields, titles)):
        limit = max(float(abs(field).max()), 1.e-8)
        if index < 2:
            limit = max(float(abs(fields[0]).max()), float(abs(fields[1]).max()), 1.e-8)
        image = ax.imshow(field, extent=extent, cmap="RdBu_r", vmin=-limit, vmax=limit)
        ax.set_title(title)
        ax.set_xlabel("Cross-stream / FV x (m)")
        ax.set_ylabel("Downstream / FV z (m)")
        fig.colorbar(image, ax=ax, shrink=.7)
    fig.suptitle(f"{first['duration_physical_s']:g} physical seconds, same saved initial state; no new sediment")
    fig.tight_layout()
    fig.savefig(output / "coastal-wave-comparison.png", dpi=160)
    plt.close(fig)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave", type=Path, required=True)
    parser.add_argument("--no-wave", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = (compare(args.wave, args.no_wave, args.output) if args.no_wave else audit(args.wave)[0])
    print(json.dumps(result, indent=2))
