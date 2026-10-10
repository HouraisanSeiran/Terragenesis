"""Plot saved M1/M2 policy, rainfall, and water-ledger evidence."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

from terrain_pipeline.surface_rivers.metric_drainage import accumulate_local_discharge
from terrain_pipeline.surface_rivers.metric_forcing import load_spatial_forcing_package
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_routing_comparison import decode_routing_comparison, load_routing_comparison


def plot_saved(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))

    def read(name, loader):
        pin = manifest["artifacts"][name]
        return loader(directory / pin["path"], expected_sha256=pin["sha256"],
                      expected_identity=pin["identity_sha256"])

    product = read("product", load_diagnostic_product)
    comparison = read("routing-comparison", load_routing_comparison)
    rainfall = read("spatial-forcing", load_spatial_forcing_package)
    report = json.loads((directory / "acceptance.json").read_text(encoding="utf-8"))
    graphs = decode_routing_comparison(comparison)
    arrays = product["arrays"]
    height = arrays["elevation_m"]
    valid = arrays["graph_valid_mask"]
    rows, cols = height.shape
    grid = product["metadata"]["terrain"]
    dx, dz = grid["dx_m"] / 1000., grid["dz_m"] / 1000.
    x0, z0 = grid["x0_m"] / 1000., grid["z0_m"] / 1000.
    extent = (x0 - dx / 2, x0 + (cols - .5) * dx,
              z0 + (rows - .5) * dz, z0 - dz / 2)
    local_mean = np.average(arrays["local_q_m3_s"], axis=0, weights=np.diff(arrays["time_seconds"]))
    output.mkdir(parents=True, exist_ok=False)
    paths = []

    def finish(fig, name, top=1.):
        fig.tight_layout(rect=(0., 0., 1., top))
        path = output / name
        fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=.2)
        plt.close(fig)
        paths.append(str(path))

    fig, axes = plt.subplots(1, 3, figsize=(17, 7), sharex=True, sharey=True)
    for axis, (name, graph) in zip(axes, graphs.items()):
        axis.imshow(np.ma.masked_where(~valid, height), extent=extent, cmap="terrain")
        flow = accumulate_local_discharge(graph, local_mean)["routed_q_m3_s"].ravel()
        donors = np.flatnonzero(graph.receiver >= 0)
        threshold = np.percentile(flow[donors], 97.) if donors.size else np.inf
        selected = donors[flow[donors] >= threshold]
        targets = graph.receiver[selected]
        starts = np.column_stack((x0 + selected % cols * dx, z0 + selected // cols * dz))
        ends = np.column_stack((x0 + targets % cols * dx, z0 + targets // cols * dz))
        axis.add_collection(LineCollection(np.stack((starts, ends), axis=1),
                                           colors="#0874c4", linewidths=.8, alpha=.85))
        lakes = np.flatnonzero(graph.outlet_kind == "lake_preserved")
        axis.scatter(x0 + lakes % cols * dx, z0 + lakes // cols * dz, s=3, c="#ce3150")
        axis.set_title(name.replace("_", " ") + f"\n{len(lakes)} closed terminal candidates", fontsize=11)
        axis.set_xlabel("X east (km)")
        axis.set_aspect("equal")
    axes[0].set_ylabel("Z south (km)")
    fig.suptitle("Real TD native-grid diagnostic: policy comparison\n"
                 "Top 3% of Q edges; original bed background; no travel time or wet lake surface", fontsize=13)
    finish(fig, "routing-policy-comparison.png", top=.88)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    image = axes[0].imshow(np.ma.masked_where(~valid, rainfall["arrays"]["multiplier"]),
                           extent=extent, cmap="BrBG", vmin=.6, vmax=1.4)
    axes[0].set_title("Independent absolute-coordinate rainfall multiplier\n30 mm/h pulse multiplied by this field", fontsize=11)
    fig.colorbar(image, ax=axes[0], shrink=.7, label="Dimensionless rainfall multiplier")
    image = axes[1].imshow(np.ma.masked_where(~valid, comparison["arrays"]["fill_depth_m"]),
                           extent=extent, cmap="magma")
    axes[1].set_title("Priority-flood working-surface elevation increase\nOriginal source heights remain unchanged", fontsize=11)
    fig.colorbar(image, ax=axes[1], shrink=.7, label="Working-surface fill depth (m)")
    for axis in axes:
        axis.set_xlabel("X east (km)")
        axis.set_ylabel("Z south (km)")
        axis.set_aspect("equal")
    finish(fig, "rainfall-and-working-fill.png")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    ends = arrays["time_seconds"][1:]
    for label, key, color in (("Rain", "rain_volume_m3", "#2b8a57"),
                              ("ET", "et_volume_m3", "#737373"),
                              ("Storage change", "storage_change_m3", "#a97730"),
                              ("Local release", "outflow_volume_m3", "#166bbc")):
        axes[0].plot(ends, arrays["runoff_" + key].sum(axis=1), "o-", label=label, color=color)
    for name, policy in report["routing_policies"].items():
        volume = [item["open_outflow_m3"] for item in policy["intervals"]]
        axes[1].plot(ends, volume, "o-", label=name.replace("_", " "))
    axes[0].set_title("Independent-cell hydrology ledger")
    axes[1].set_title("Open-boundary diagnostic volume by policy")
    for axis in axes:
        axis.set_xlabel("Native interval end (s)")
        axis.set_ylabel("Volume in interval (m3)")
        axis.grid(alpha=.2)
        axis.legend(fontsize=8)
    fig.suptitle("M2: identical water totals for dense and sparse saved frames")
    finish(fig, "m2-water-ledgers.png", top=.90)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(plot_saved(args.input, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
