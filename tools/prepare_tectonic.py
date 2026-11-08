"""Explicit CPU plan/generate entry point for an isolated tectonic background."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.tectonic import plan, prepare_frozen_product as prepare


def render_diagnostics(product, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap, TwoSlopeNorm
    import numpy as np

    output = Path(output)
    config = product.manifest["config"]
    fields = product.arrays
    states = ("initial", "final")
    spacing = config["cell_size_m"]
    nz, nx = config["shape"]
    extent = [config["origin_x_m"] / 1000, (config["origin_x_m"] + nx * spacing) / 1000,
              (config["origin_z_m"] + nz * spacing) / 1000, config["origin_z_m"] / 1000]
    x_centres_km = (config["origin_x_m"] + (np.arange(nx) + .5) * spacing) / 1000
    z_centres_km = (config["origin_z_m"] + (np.arange(nz) + .5) * spacing) / 1000
    # Separate halves keep every negative elevation blue, with an explicit datum boundary.
    bathymetry = LinearSegmentedColormap.from_list("bathymetry", ["#082450", "#1764a0", "#99d9ed"])
    land = LinearSegmentedColormap.from_list("earth_land", ["#d6c38f", "#9d9462", "#897052", "#eee9df"])
    elevation_cmap = ListedColormap(np.vstack((bathymetry(np.linspace(0, 1, 256)),
                                               land(np.linspace(0, 1, 256)))))
    elevation_min_m = min(float(fields[state + "/elevation_m"].min()) for state in states)
    elevation_max_m = max(float(fields[state + "/elevation_m"].max()) for state in states)
    # Include both sides even for constant, entirely dry, or entirely wet products.
    elevation_norm = TwoSlopeNorm(vmin=min(-1., elevation_min_m), vcenter=0.,
                                  vmax=max(1., elevation_max_m))
    crust_limits = {"vmin": min(float(fields[state + "/crust_thickness_m"].min()) for state in states),
                    "vmax": max(float(fields[state + "/crust_thickness_m"].max()) for state in states)}
    max_speed_km_per_step = max(float(np.linalg.norm(fields[state + "/velocities_m_per_step"], axis=1).max())
                                / 1000 for state in states)
    frame_size_km = min(nx, nz) * spacing / 1000
    velocity_enlargement = max(1., .09 * frame_size_km / max_speed_km_per_step) if max_speed_km_per_step else 1.
    reference_km_per_step = (10 ** np.floor(np.log10(max_speed_km_per_step))
                             if max_speed_km_per_step else 1.)

    def plot_elevation(axis, state):
        elevation = fields[state + "/elevation_m"]
        image = axis.imshow(elevation, extent=extent, origin="upper", interpolation="nearest",
                            cmap=elevation_cmap, norm=elevation_norm)
        if min(nz, nx) > 1 and elevation.min() < 0 < elevation.max():
            axis.contour(x_centres_km, z_centres_km, elevation, levels=[0],
                         colors="#202b30", linewidths=.8)
        axis.set(xlim=extent[:2], ylim=extent[2:], xlabel="X east (km)", ylabel="Z south (km)")
        return image

    diagnostic_label = (f"periodic plane; seed {config['world_seed']}; {product.identity[:16]}"
                        "\nMechanism diagnostics only; NOT TD bound")
    for state in states:
        fig, axes = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
        for axis, name, cmap, unit in zip(axes.flat,
                ("elevation_m", "continental_fraction", "plate_id", "crust_thickness_m"),
                (None, "YlOrBr", "tab20", "viridis"), ("elevation (m, datum 0)", "fraction", "plate ID", "m")):
            if name == "elevation_m":
                image = plot_elevation(axis, state)
                axis.set_title("Elevation; coastline at datum 0 m")
            else:
                limits = crust_limits if name == "crust_thickness_m" else {"vmin": 0, "vmax": 1}
                if name == "plate_id":
                    limits = {"vmin": -.5, "vmax": config["plate_count"] - .5}
                image = axis.imshow(fields[state + "/" + name], extent=extent, origin="upper",
                                    interpolation="nearest", cmap=cmap, **limits)
                axis.set(title=name, xlabel="X east (km)", ylabel="Z south (km)")
            fig.colorbar(image, ax=axis, label=unit, shrink=.8)
            if name == "plate_id":
                seeds = fields[state + "/plate_seeds_m"]
                velocities = fields[state + "/velocities_m_per_step"]
                arrows = axis.quiver(seeds[:, 0] / 1000, seeds[:, 1] / 1000,
                                     velocities[:, 0] / 1000 * velocity_enlargement,
                                     velocities[:, 1] / 1000 * velocity_enlargement,
                                     angles="xy", scale_units="xy", scale=1, color="black",
                                     width=.006, edgecolor="white", linewidth=.4)
                axis.quiverkey(arrows, .5, 1.03, reference_km_per_step * velocity_enlargement,
                               f"{reference_km_per_step:g} km/offline-step", labelpos="E", coordinates="axes")
                axis.set_title(f"Plate ID; arrows display x{velocity_enlargement:.4g}\n"
                               "Enlarged displacement; not physical map length", pad=38, fontsize=10)
                axis.set(xlim=extent[:2], ylim=extent[2:])
        step = product.manifest["steps"][state]
        fig.suptitle(f"{state}, offline step {step}; {diagnostic_label}")
        fig.savefig(output / f"{state}-macro.png", dpi=130)
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    for axis, state in zip(axes, states):
        image = plot_elevation(axis, state)
        axis.set_title(f"{state}; offline step {product.manifest['steps'][state]}")
    fig.colorbar(image, ax=axes, label="elevation (m, datum 0); dark contour = 0 m", shrink=.85)
    fig.suptitle(f"Initial / final elevation from frozen product arrays\n{diagnostic_label}")
    fig.savefig(output / "elevation-comparison.png", dpi=150)
    plt.close(fig)

    budgets = product.manifest["budgets"]
    groups = [
        ("Material inventories", "m3", lambda key: key.endswith("_m3") and key.startswith(("initial_", "final_"))),
        ("Material sources / sinks / transfers", "m3 (sink shown negative)",
         lambda key: key.endswith("_m3") and not key.startswith(("initial_", "final_")) and "residual" not in key),
        ("Material balance / transport residuals", "m3", lambda key: key.endswith("_m3") and "residual" in key),
        ("Mixing diagnostic", "m4", lambda key: key.endswith("_m4")),
        ("Uncovered area", "m2", lambda key: key.endswith("_m2")),
        ("Boundary faces", "face count", lambda key: key.endswith("_faces")),
        ("Coverage overlap", "fraction", lambda key: key == "max_coverage_overlap"),
    ]
    fig, axes = plt.subplots(4, 2, figsize=(15, 17), constrained_layout=True)
    for axis, (title, unit, predicate) in zip(axes.flat, groups):
        keys = sorted({key for row in budgets for key in row if predicate(key)})
        for key in keys:
            sign = -1 if key == "subducted_oceanic_m3" else 1
            label = key + (" (sink, negative)" if sign < 0 else "")
            if key == "sutured_continental_m3":
                label += " (internal transfer)"
            if key.startswith("advected_"):
                label += " (internal transport)"
            axis.plot([row["step"] for row in budgets], [sign * row.get(key, np.nan) for row in budgets], label=label)
        axis.set(title=title, xlabel="uncalibrated offline step", ylabel=unit)
        axis.set_yscale("symlog", linthresh=1)
        if keys:
            axis.legend(fontsize=6, loc="best")
    axes.flat[-1].axis("off")
    fig.suptitle(f"Process diagnostics; separate units and volume residuals\n{diagnostic_label}")
    fig.savefig(output / "process-budgets.png", dpi=130)
    plt.close(fig)
    (output / "diagnostics.json").write_text(json.dumps({
        "identity": product.identity, "td_binding": None, "scope": "macro mechanism diagnostics only",
        "coordinates": product.manifest["coordinates"], "config": config, "budgets": budgets,
        "core_metadata": product.manifest["core_metadata"],
        "rendering": {"elevation_limits_m": [elevation_norm.vmin, elevation_norm.vmax],
                      "elevation_datum_m": 0, "coastline_sampling": "absolute cell centres",
                      "velocity_display_enlargement_factor": velocity_enlargement,
                      "velocity_reference_km_per_offline_step": reference_km_per_step,
                      "velocity_display_note": "enlarged displacement, not physical map length",
                      "budget_display_note": "subducted oceanic sink negative; stored budgets unchanged"}},
        indent=2, allow_nan=False), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__ + " Default formation: dispersed core microcells with connected mixed circle/ellipse/triangle shape-prioritized Voronoi growth (generation priors only).")
    parser.add_argument("mode", choices=("plan", "generate"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--shape", type=int, nargs=2, default=(128, 128), metavar=("NZ", "NX"))
    parser.add_argument("--cell-size-m", type=float, default=10000.)
    parser.add_argument("--origin-m", type=float, nargs=2, default=(0., 0.), metavar=("X", "Z"))
    parser.add_argument("--plates", type=int, default=8)
    parser.add_argument("--microcells-per-plate", type=int, default=64, help="target density; capped at one site per four cells")
    parser.add_argument("--min-plate-cells", type=int, default=4, help="minimum resolved initial plate area in full grid cells")
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--max-memory-bytes", type=int, default=2_000_000_000)
    parser.add_argument("--max-cell-plate-steps", type=int, default=200_000_000)
    args = parser.parse_args(argv)
    from terrain_pipeline.tectonic import TectonicConfig
    config = TectonicConfig(shape=tuple(args.shape), cell_size_m=args.cell_size_m,
                            origin_x_m=args.origin_m[0], origin_z_m=args.origin_m[1],
                            plate_count=args.plates, steps=args.steps, world_seed=20261020,
                            microcells_per_plate=args.microcells_per_plate, min_plate_cells=args.min_plate_cells)
    limits = {"max_memory_bytes": args.max_memory_bytes, "max_cell_plate_steps": args.max_cell_plate_steps}
    report = plan(config, **limits)
    if args.mode == "plan":
        print(json.dumps(report, indent=2))
        return report
    if not report["allowed"]:
        raise ValueError("CPU resource budget exceeded before generation")
    if args.output is None:
        parser.error("generate requires --output (new workspace directory)")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("output must be inside the workspace")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".tectonic-stage-", dir=output.parent))
    try:
        product = prepare(config, staging / "product.npz", **limits)
        render_diagnostics(product, staging)
        (staging / "plan.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        os.rename(staging, output)
    finally:
        # The staging path is created directly beneath the verified workspace parent.
        if staging.exists():
            if staging.parent != output.parent or not staging.name.startswith(".tectonic-stage-"):
                raise ValueError("invalid staging cleanup path")
            shutil.rmtree(staging)
    result = {"identity": product.identity, "output": str(output), "plan": report}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
