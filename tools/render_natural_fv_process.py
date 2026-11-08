"""Read-only natural native/FV process figures, including in-progress packets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

import numpy as np


def audit_complete(parent, water_run, output):
    summary = json.loads((water_run / "summary.json").read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest(parent / "result.npz") != summary["parent_sha256"]:
        raise AssertionError("native parent source hash differs")
    hashes = {name: digest(root / name) == expected for name, expected in summary["implementation_hashes"].items()}
    if not all(hashes.values()):
        raise AssertionError("saved FV implementation hashes differ: " + str(hashes))
    with np.load(water_run / "result.npz") as saved:
        a = {key: saved[key] for key in saved.files}
    with np.load(parent / "result.npz") as saved:
        np.testing.assert_array_equal(a["bed_m"], saved["bed_m"][-1])
        np.testing.assert_array_equal(a["initial_depth_m"], saved["depth_m"][-1])
    np.testing.assert_array_equal(a["H2_m"].reshape(a["bed_m"].shape), a["bed_m"])
    np.testing.assert_array_equal(a["depth_m"][0], a["initial_depth_m"])
    np.testing.assert_array_equal(a["stage_m"], a["depth_m"] + a["bed_m"])
    np.testing.assert_array_equal(a["momentum_x_m2_s"][0], 0.)
    np.testing.assert_array_equal(a["momentum_z_m2_s"][0], 0.)
    area = summary["metadata"]["initial_volume_m3"] / a["initial_depth_m"].sum()
    left, right, cells = a["face_left"], a["face_right"], a["boundary_cell"]
    previous_h = a["initial_depth_m"].ravel()
    previous_m = np.zeros((len(previous_h), 2))
    maxima = {key: 0. for key in ("cell_water_m3", "cell_momentum_m4_s", "depth_handoff_m", "momentum_handoff_m2_s",
        "snapshot_depth_m", "snapshot_momentum_m2_s", "gross_minus_net_exchange_m3", "forcing_volume_m3")}
    intervals = len(a["time_s"]) - 1
    np.testing.assert_array_equal(a["interval_sea_imported_m3"], np.diff(a["ledger"][:, 1]))
    np.testing.assert_array_equal(a["interval_sea_exported_m3"], np.diff(a["ledger"][:, 2]))
    net_total = 0.
    source_total = 0.
    records = []
    for number in range(intervals):
        with np.load(water_run / "intervals" / f"{number:05d}.npz") as saved:
            p = {key: saved[key] for key in saved.files}
        errors = {"depth_handoff_m": float(abs(p["depth_before_m"] - previous_h).max()),
            "momentum_handoff_m2_s": float(abs(p["momentum_before"] - previous_m).max())}
        net_water = p["forcing_volume_m3"].copy()
        np.add.at(net_water, left, -p["internal_transfer_m3"])
        np.add.at(net_water, right, p["internal_transfer_m3"])
        np.add.at(net_water, cells, -p["boundary_transfer_m3"])
        errors["cell_water_m3"] = float(abs((p["depth_after_m"] - p["depth_before_m"]) * area - net_water).max())
        net_m = np.zeros_like(previous_m)
        np.add.at(net_m, left, -p["internal_momentum_transfer"])
        np.add.at(net_m, right, p["internal_momentum_transfer"])
        np.add.at(net_m, cells, -p["boundary_momentum_transfer"])
        net_m += area * (p["bed_momentum_change"] + p["manning_momentum_change"])
        errors["cell_momentum_m4_s"] = float(abs((p["momentum_after"] - p["momentum_before"]) * area - net_m).max())
        snapshot_m = np.column_stack([a["momentum_x_m2_s"][number + 1].ravel(), a["momentum_z_m2_s"][number + 1].ravel()])
        errors["snapshot_depth_m"] = float(abs(p["depth_after_m"] - a["depth_m"][number + 1].ravel()).max())
        errors["snapshot_momentum_m2_s"] = float(abs(p["momentum_after"] - snapshot_m).max())
        net = float(p["boundary_transfer_m3"].sum())
        errors["gross_minus_net_exchange_m3"] = abs(net - a["interval_sea_exported_m3"][number] + a["interval_sea_imported_m3"][number])
        supplied = float(p["forcing_volume_m3"].sum())
        expected_source = np.zeros_like(p["forcing_volume_m3"])
        inlet = summary["forcing"]["river_cells_row_column"]
        duration = float(p["time_end_s"] - p["time_start_s"])
        for row, column in inlet:
            expected_source[row * a["bed_m"].shape[1] + column] = summary["forcing"]["river_q_m3_s"] * duration / len(inlet)
        np.testing.assert_allclose(p["forcing_volume_m3"], expected_source, atol=1.e-7, rtol=0.)
        errors["forcing_volume_m3"] = abs(supplied - summary["forcing"]["river_q_m3_s"] * float(p["time_end_s"] - p["time_start_s"]))
        for key, value in errors.items():
            maxima[key] = max(maxima[key], float(value))
        np.testing.assert_allclose(net, a["interval_boundary_net_outward_m3"][number], atol=1.e-9, rtol=0.)
        np.testing.assert_allclose(p["time_start_s"], a["time_s"][number], atol=1.e-7, rtol=0.)
        np.testing.assert_allclose(p["time_end_s"], a["time_s"][number + 1], atol=1.e-7, rtol=0.)
        np.testing.assert_allclose(p["applied_sea_stage_m"], a["applied_sea_stage_m"][number], atol=0., rtol=0.)
        previous_h, previous_m = p["depth_after_m"], p["momentum_after"]
        net_total += net
        source_total += supplied
        records.append({"interval": number, **errors})
    if max(maxima.values()) > 1.e-7:
        raise AssertionError("independent complete FV closure failed: " + str(maxima))
    stored_change = float((a["depth_m"][-1] - a["initial_depth_m"]).sum() * area)
    global_residual = stored_change - source_total + net_total
    np.testing.assert_allclose(global_residual, 0., atol=1.e-6, rtol=0.)
    imports = float(a["interval_sea_imported_m3"].sum())
    exports = float(a["interval_sea_exported_m3"].sum())
    np.testing.assert_allclose([source_total, imports, exports], a["ledger"][-1, :3], atol=1.e-6, rtol=0.)
    result = {"status": "passed", "completed_intervals_independently_rebuilt": intervals,
        "duration_physical_s": float(a["time_s"][-1]), "parent_source_hash_matches": True,
        "implementation_hash_matches": hashes, "fixed_bed_matches_native_parent_exactly": True,
        "source_depth_matches_native_final_exactly": True, "initial_FV_momentum_zero": True,
        "maximum_abs_independent_residuals": maxima, "global_water_residual_m3": global_residual,
        "river_supplied_m3": source_total, "gross_sea_imported_m3": imports, "gross_sea_exported_m3": exports,
        "net_sea_outward_m3": net_total, "stored_water_change_m3": stored_change,
        "gross_exchange_scope": "saved substep-integrated gross ledger checked against independent summed interval signed face transfers; full substep trajectories are not archived",
        "interpretation": "fixed-bed exposure is not permanent land growth; interpret river and sea exchange from the measured gross volumes for this run",
        "interval_residuals": records}
    output.mkdir(parents=True, exist_ok=True)
    (output / "complete-independent-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {key: value for key, value in result.items() if key != "interval_residuals"}


def run(parent, water_run, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from scipy.ndimage import binary_propagation

    output.mkdir(parents=True, exist_ok=True)
    native_report = json.loads((parent / "summary.json").read_text(encoding="utf-8"))
    dx = native_report["config"]["dx_m"]
    with np.load(parent / "result.npz") as source:
        native = {name: source[name] for name in source.files}
    bed = native["bed_m"][-1]
    shape = bed.shape
    eligible = native["cell_type"] == 0
    original_sea = (native["initial_bed_m"] < 0.) & eligible
    old_land = native["initial_bed_m"] >= 0.
    extent = [-shape[1] * dx / 2., shape[1] * dx / 2., shape[0] * dx, 0.]
    xx, yy = np.meshgrid((np.arange(shape[1]) + .5) * dx - shape[1] * dx / 2., (np.arange(shape[0]) + .5) * dx)
    pick = (slice(4, None, 8), slice(4, None, 8))

    def contour(ax, field, level, color, width=.7):
        if field.min() < level < field.max():
            ax.contour(xx, yy, field, [level], colors=color, linewidths=width)

    def finish(ax):
        ax.set_xlabel("Cross-stream / FV x (m)")
        ax.set_ylabel("Downstream / FV z (m)")

    fig, axes = plt.subplots(1, 3, figsize=(15, 7))
    delta = bed - native["initial_bed_m"]
    for ax, field, title, cmap in zip(axes, [native["initial_bed_m"], bed, delta],
            ["Initial macro + TD residual bed", "Finite-source deposited bed", "Measured bed change"], ["terrain", "terrain", "RdBu_r"]):
        options = {"vmin": -1.5, "vmax": 1.} if cmap == "terrain" else {"norm": TwoSlopeNorm(0., -max(abs(delta).max(), .01), max(abs(delta).max(), .01))}
        image = ax.imshow(field, extent=extent, cmap=cmap, **options)
        contour(ax, bed, 0., "black")
        ax.set_title(title)
        finish(ax)
        fig.colorbar(image, ax=ax, shrink=.65, label="m")
    # Native pyDeltaRCM qx follows rows; qy was archived under qz_m2_s.
    axes[1].quiver(xx[pick], yy[pick], native["qz_m2_s"][-1][pick], native["qx_m2_s"][-1][pick],
        color="#862b42", angles="xy", scale_units="xy", scale=.035, width=.003)
    fig.tight_layout()
    fig.savefig(output / "natural-bed-process.png", dpi=160)
    plt.close(fig)

    packets = []
    for path in sorted((water_run / "intervals").glob("*.npz")):
        if not re.fullmatch(r"\d{5}\.npz", path.name):
            continue
        try:
            with np.load(path) as saved:
                packet = {key: saved[key] for key in saved.files}
            with np.load(path.with_name(path.stem + "-first-substep.npz")) as saved:
                packet["sea_stage_m"] = float(saved["tailwater_m"][0])
        except (OSError, ValueError, EOFError, zipfile.BadZipFile):
            continue
        packets.append(packet)
    if not packets:
        raise ValueError("no completed FV interval packets")
    selected = np.unique(np.linspace(0, len(packets) - 1, 4).astype(int))
    fig, axes = plt.subplots(1, len(selected), figsize=(5 * len(selected), 7), squeeze=False)
    metrics = []
    for packet in packets:
        depth = packet["depth_after_m"].reshape(shape)
        dry = depth <= 2.e-6
        connected = binary_propagation(old_land & dry, mask=dry)
        metrics.append([float(packet["time_end_s"]), packet["sea_stage_m"],
            float(depth.sum() * dx ** 2), float((dry & original_sea).sum() * dx ** 2),
            float((connected & original_sea).sum() * dx ** 2),
            float(packet["boundary_transfer_m3"].sum()), float(packet["forcing_volume_m3"].sum()),
            float(packet["time_end_s"] - packet["time_start_s"])])
    metrics = np.asarray(metrics)
    vmax = max(1., float(np.percentile(packets[-1]["depth_after_m"], 98)))
    for ax, index in zip(axes[0], selected):
        p = packets[index]
        depth = p["depth_after_m"].reshape(shape)
        ax.imshow(bed, extent=extent, cmap="Greys", vmin=-1.5, vmax=1.)
        image = ax.imshow(np.where(depth > 2.e-6, depth, np.nan), extent=extent, cmap="YlGnBu", vmin=0., vmax=vmax)
        contour(ax, bed, 0., "#6e3030")
        contour(ax, depth, 2.e-6, "#f28c28", 1.)
        dry = ((depth <= 2.e-6) & eligible).astype(float)
        contour(ax, dry, .5, "#2f8b46", .9)
        momentum = p["momentum_after"].reshape(*shape, 2)
        ax.quiver(xx[pick], yy[pick], momentum[:, :, 0][pick], momentum[:, :, 1][pick],
            color="#b52146", angles="xy", scale_units="xy", scale=.035, width=.003)
        ax.set_title(f"FV t={float(p['time_end_s']) / 3600.:.2f} h\nApplied sea={p['sea_stage_m']:+.3f} m")
        finish(ax)
    fig.suptitle("Fixed natural bed; red: zero-datum bed contour; orange/green: actual wet-dry edge; arrows: FV unit discharge")
    fig.subplots_adjust(top=.88, bottom=.1, left=.06, right=.87, wspace=.3)
    fig.colorbar(image, cax=fig.add_axes([.9, .22, .012, .52]), label="Actual depth (m)")
    fig.savefig(output / "FV-water-depth-shoreline.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    t = metrics[:, 0] / 3600.
    axes[0, 0].step(np.r_[0., t], np.r_[metrics[:, 1], metrics[-1, 1]], where="post", color="#315f9b")
    axes[0, 0].set_ylabel("Applied sea stage (m)")
    axes[0, 1].plot(t, metrics[:, 2], color="#315f9b")
    axes[0, 1].set_ylabel("Stored water (m3)")
    axes[1, 0].plot(t, metrics[:, 3], label="Actual dry original marine cells", color="#409651")
    axes[1, 0].plot(t, metrics[:, 4], label="Actual dry connected to original land", color="#9a3d6a")
    axes[1, 0].set_ylabel("Area (m2)")
    axes[1, 0].legend(fontsize=8)
    axes[1, 1].plot(t, metrics[:, 5] / metrics[:, 7], label="Net sea outflow", color="#aa4454")
    axes[1, 1].plot(t, metrics[:, 6] / metrics[:, 7], label="River input", color="#315f9b")
    axes[1, 1].set_ylabel("Interval mean discharge (m3/s)")
    axes[1, 1].legend(fontsize=8)
    for ax in axes.ravel():
        ax.set_xlabel("Physical water time (h)")
        ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(output / "FV-time-process.png", dpi=170)
    plt.close(fig)
    report = {"parent": str(parent), "water_run": str(water_run), "completed_packets_read": len(packets),
        "metric_columns": ["time_end_s", "applied_interval_sea_stage_m", "stored_water_m3", "dry_original_marine_area_m2",
            "dry_original_marine_connected_area_m2", "net_outward_boundary_transfer_m3", "river_volume_m3", "interval_duration_s"],
        "measurements": metrics.tolist(), "dry_threshold_m": 2.e-6,
        "native_vector_axes": "saved qx_m2_s is downstream row; saved qz_m2_s is cross-stream column (native qy)",
        "FV_vector_axes": "momentum_after[:,0] is cross-stream/column x; [:,1] is downstream/row z",
        "exchange_semantics": "packet face transfers give signed net exchange, not gross substep sea import/export; final runner result ledger supplies gross exchange",
        "figures": ["natural-bed-process.png", "FV-water-depth-shoreline.png", "FV-time-process.png"]}
    (output / "measurements.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {key: value for key, value in report.items() if key != "measurements"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--water-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-only", action="store_true", help="audit completed saved intervals without regenerating figures")
    args = parser.parse_args()
    action = audit_complete if args.audit_only else run
    print(json.dumps(action(args.parent, args.water_run, args.output), indent=2))
