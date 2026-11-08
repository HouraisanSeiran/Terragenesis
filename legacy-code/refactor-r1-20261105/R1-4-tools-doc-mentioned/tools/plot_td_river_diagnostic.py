"""Plot saved river diagnostics; never generate terrain or solve hydrology."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product


def plot_saved(input_directory, output_directory):
    source = Path(input_directory).resolve()
    output = Path(output_directory).resolve()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    product = load_diagnostic_product(source / manifest["product"],
                                      expected_sha256=manifest["product_sha256"],
                                      expected_identity=manifest["product_identity_sha256"])
    output.mkdir(parents=True, exist_ok=False)
    arrays, meta = product["arrays"], product["metadata"]
    grid = meta["terrain"]
    ny, nx = arrays["elevation_m"].shape
    dx, dz = grid["dx_m"] / 1000., grid["dz_m"] / 1000.
    x0, z0 = grid["x0_m"] / 1000., grid["z0_m"] / 1000.
    extent = (x0 - dx / 2, x0 + (nx - .5) * dx,
              z0 + (ny - .5) * dz, z0 - dz / 2)
    valid = arrays["graph_valid_mask"]
    height = np.ma.masked_where(~valid, arrays["elevation_m"])
    receiver = arrays["graph_receiver"]
    dt = np.diff(arrays["time_seconds"])
    mean_q = np.average(arrays["routed_q_m3_s"], axis=0, weights=dt).ravel()
    donors = np.flatnonzero(receiver >= 0)
    threshold = np.percentile(mean_q[donors], 97.) if donors.size else 0.
    chosen = donors[mean_q[donors] >= threshold]
    targets = receiver[chosen]
    starts = np.column_stack((x0 + chosen % nx * dx, z0 + chosen // nx * dz))
    ends = np.column_stack((x0 + targets % nx * dx, z0 + targets // nx * dz))
    segments = np.stack((starts, ends), axis=1)
    paths = []

    def finish(fig, axis, name):
        axis.set_xlabel("X east (km, generated model coordinates)")
        axis.set_ylabel("Z south (km)")
        axis.set_aspect("equal")
        fig.tight_layout()
        path = output / name
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(str(path))

    fig, axis = plt.subplots(figsize=(10, 8))
    image = axis.imshow(height, extent=extent, cmap="terrain")
    axis.add_collection(LineCollection(segments, colors="#075ea8", linewidths=1.1, alpha=.85))
    lakes = np.flatnonzero(arrays["graph_outlet_kind"] == "lake_preserved")
    axis.scatter(x0 + lakes % nx * dx, z0 + lakes // nx * dz, s=7,
                 c="#be2850", label="Closed terminal candidates", zorder=3)
    axis.legend(loc="lower left", fontsize=8)
    fig.colorbar(image, ax=axis, label="Original bed elevation (m)", shrink=.7)
    axis.set_title("TD original-bed D8 diagnostic\nTop 3% of mean accumulated Q edges; no channel travel time")
    finish(fig, axis, "terrain-and-routing.png")

    lake_ids = arrays["graph_lake_id"].reshape(ny, nx)
    unique = np.unique(lake_ids[lake_ids >= 0])
    classes = np.full((ny, nx), np.nan)
    has_lake = lake_ids >= 0
    classes[has_lake] = np.searchsorted(unique, lake_ids[has_lake]) % 20
    fig, axis = plt.subplots(figsize=(10, 8))
    axis.imshow(height, extent=extent, cmap="Greys", alpha=.35)
    axis.imshow(np.ma.masked_invalid(classes), extent=extent, cmap="tab20", vmin=0, vmax=19, alpha=.8)
    axis.scatter(x0 + lakes % nx * dx, z0 + lakes // nx * dz, c="#151515", s=5)
    axis.set_title(f"{len(lakes)} closed-terminal contribution catchments\nColors repeat; these areas are NOT lake wet footprints")
    finish(fig, axis, "closed-terminal-catchments.png")

    fig, axis = plt.subplots(figsize=(10, 5))
    times = arrays["time_seconds"][1:]
    for label, key, color in (("Rain input", "runoff_rain_volume_m3", "#218649"),
                              ("Hydrology storage change", "runoff_storage_change_m3", "#a97725"),
                              ("ET", "runoff_et_volume_m3", "#666666")):
        axis.plot(times, arrays[key].sum(axis=1), "o-", color=color, label=label)
    for label, key, color in (("Open boundary diagnostic", "open_outflow", "#1765b4"),
                              ("Closed terminal candidate inflow", "lake_retained", "#bf3158")):
        axis.plot(times, arrays[key + "_volume_interval_m3"], "o-", color=color, label=label)
    axis.set_xlabel("Physical interval end (s); each interval is 300 s")
    axis.set_ylabel("Interval volume (m3)")
    axis.set_title("Native-grid diagnostic water ledger\nIndependent-cell storage; no channel or lake stage solution")
    axis.legend(fontsize=8)
    axis.grid(alpha=.2)
    fig.tight_layout()
    path = output / "interval-water-ledger.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(str(path))
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(plot_saved(args.input, args.output)))


if __name__ == "__main__":
    main()
