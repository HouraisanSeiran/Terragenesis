"""Read-only natural delta evolution and measured phase-budget diagnostics."""
import argparse
import json
from pathlib import Path

import numpy as np


def run(directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from scipy.ndimage import binary_propagation
    with np.load(directory/"result.npz") as saved:
        a = {key: saved[key] for key in saved.files}
    summary = json.loads((directory/"summary.json").read_text(encoding="utf-8"))
    output = directory/"evolution-diagnostics"
    output.mkdir(exist_ok=True)
    bed, depth, stage = a["bed_m"], a["depth_m"], a["stage_m"]
    initial = a["initial_bed_m"]
    config = summary["config"]
    dx = config["dx_m"]
    extent = [-initial.shape[1]*dx/2., initial.shape[1]*dx/2., initial.shape[0]*dx, 0.]
    water = LinearSegmentedColormap.from_list("water", ["#79d4e5", "#2276a8", "#173a65"])
    eligible = (a["cell_type"] != 1) & (a["cell_type"] != -1) & (a["cell_type"] != -2)
    original_sea = (initial < 0.) & eligible
    land = initial >= 0.
    frames = np.unique(np.linspace(0, len(bed)-1, 4).astype(int))
    fig, axes = plt.subplots(1, len(frames), figsize=(5*len(frames), 7))
    for ax, index in zip(np.atleast_1d(axes), frames):
        ax.imshow(bed[index], extent=extent, cmap="terrain", vmin=-1.5, vmax=1.)
        ax.imshow(np.where(depth[index] > 2.e-6, depth[index], np.nan), extent=extent, cmap=water, vmin=0., vmax=2.)
        ax.contour(bed[index], [0.], extent=extent, origin="upper", colors="black", linewidths=.7)
        wet_above = (bed[index] >= 0.) & (depth[index] > 2.e-6) & eligible
        if wet_above.any():
            ax.contour(wet_above, [.5], extent=extent, origin="upper", colors="#ff9a34", linewidths=.7)
        ax.set_title(f"Frame {index}; t={a['time_s'][index]/3600.:.2f} h\nBlue=actual wet; orange=wet above datum")
        ax.set_xlabel("Cross-stream (m)"); ax.set_ylabel("Downstream (m)")
    fig.tight_layout(); fig.savefig(output/"four-stages.png", dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(17, 7))
    xx, yy = np.meshgrid(np.linspace(extent[0], extent[1], initial.shape[1]), np.arange(initial.shape[0])*dx)
    im = axes[0].imshow(bed[-1], extent=extent, cmap="terrain", vmin=-1.5, vmax=1.)
    axes[0].contour(bed[-1], levels=np.arange(-1.5, 1.51, .25), extent=extent, origin="upper", linewidths=.45, colors="black")
    pick = (slice(6, None, 7), slice(3, None, 7))
    axes[0].quiver(xx[pick], yy[pick], a["qz_m2_s"][-1][pick], a["qx_m2_s"][-1][pick], color="#a50026", scale=80., width=.002)
    axes[0].set_title("Final bed contours and actual unit-discharge vectors")
    fig.colorbar(im, ax=axes[0], shrink=.6, label="Bed (m)")
    for ax, field, title in ((axes[1], stage[-1], "Actual water stage"), (axes[2], depth[-1], "Actual water depth")):
        im = ax.imshow(field, extent=extent, cmap=water)
        ax.contour((bed[-1] >= 0.) & (depth[-1] <= 2.e-6), [.5], extent=extent, origin="upper", colors="black", linewidths=.8)
        ax.set_title(title+"; black=actual dry land")
        fig.colorbar(im, ax=ax, shrink=.6, label="m")
    fig.tight_layout(); fig.savefig(output/"final-hydraulics.png", dpi=170); plt.close(fig)
    metrics = []
    for index in range(len(bed)):
        geometric = bed[index] >= 0.
        dry = geometric & (depth[index] <= 2.e-6)
        geometry_connected = binary_propagation(land & geometric, mask=geometric)
        dry_connected = binary_propagation(land & dry, mask=dry)
        metrics.append([a["time_s"][index], np.count_nonzero(original_sea & geometry_connected)*dx**2,
            np.count_nonzero(original_sea & dry_connected)*dx**2,
            np.count_nonzero(original_sea & geometric & ~dry)*dx**2,
            float(np.maximum(bed[index]-initial, 0.)[original_sea].sum()*dx**2)])
    metrics = np.asarray(metrics)
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    for column, title in ((1, "Connected bed above datum"), (2, "Connected actually dry"), (3, "Above datum but still wet")):
        axes[0].plot(metrics[:, 0]/3600., metrics[:, column], label=title)
    axes[0].legend(); axes[0].set_ylabel("Area (m2), inlet and open boundaries excluded")
    axes[1].plot(metrics[:, 0]/3600., metrics[:, 4], label="Positive change on original marine bed")
    axes[1].plot(a["time_s"]/3600., a["cumulative_input_solid_m3"]/(1.-config["porosity"]), label="Finite supplied bulk")
    axes[1].legend(); axes[1].set_ylabel("Bulk volume (m3)"); axes[1].set_xlabel("Model time (h), compressed mechanism chronology")
    fig.tight_layout(); fig.savefig(output/"morphology-process.png", dpi=170); plt.close(fig)
    phases = summary["phase_records"]
    names = list(dict.fromkeys(row["phase"] for row in phases))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for name in names:
        selected = [row for row in phases if row["phase"] == name]
        steps = [row["step_index"] for row in selected]
        inferred = [row["injected_bulk_m3"]-row["exported_bulk_m3"]-row["lost_bulk_m3"]+row["inlet_correction_bulk_m3"]+row["raw_residual_bulk_m3"] for row in selected]
        axes[0].plot(steps, np.cumsum(inferred), label=name)
        axes[1].plot(steps, np.cumsum([row["raw_residual_bulk_m3"] for row in selected]), label=name)
    axes[0].set_ylabel("Cumulative phase bed change (bulk m3)"); axes[1].set_ylabel("Measured numerical residual (bulk m3)")
    for ax in axes:
        ax.legend(); ax.set_xlabel("Native update index")
    fig.tight_layout(); fig.savefig(output/"phase-budgets.png", dpi=170); plt.close(fig)
    evidence = {"columns": ["model_seconds", "geometric_connected_m2", "actual_dry_connected_m2", "above_datum_still_wet_m2", "positive_marine_bulk_m3"],
        "frames": metrics.tolist(), "area_mask": "initial bed<0, cell_type not 1/-1/-2; entry stub excluded", "wet_tolerance_m": 2.e-6}
    (output/"measurements.json").write_text(json.dumps(evidence, indent=2)+"\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    run(parser.parse_args().input)
