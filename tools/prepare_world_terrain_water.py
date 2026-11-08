"""Prepare one finite terrain and water product from a pinned TD page."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_rivers.native_30m_source import BORDER_BAND_CELLS, _read_page
from terrain_pipeline.td_source import compose_source, crop_composition, make_ocean_plan, sample_ocean_mask
from terrain_pipeline.world_water_formation import form_water_and_rivers
from terrain_pipeline.world_water_layout import LayoutSpec
from terrain_pipeline.world_river_network_io import write_network


def render(arrays, origin, path):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    from matplotlib.collections import LineCollection

    rows, cols = arrays["composed_elevation_m"].shape
    x, z = origin
    extent = [(x - .5) * .03, (x + cols - .5) * .03,
              (z + rows - .5) * .03, (z - .5) * .03]
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.5), constrained_layout=True)
    fields = ("macro_elevation_m", "td_elevation_m", "composed_elevation_m", "final_bed_m")
    titles = ("Macro base (m)", "TD source (own scale, m)", "Composed terrain (m)", "Final bed and water (m)")
    shared = ("macro_elevation_m", "composed_elevation_m", "final_bed_m")
    vmin = min(float(np.min(arrays[name])) for name in shared)
    vmax = max(float(np.max(arrays[name])) for name in shared)
    land_cmap = ListedColormap(plt.get_cmap("terrain")(np.linspace(.25, 1., 256)))
    for axis, name, title in zip(axes, fields, titles):
        scale = {} if name == "td_elevation_m" else {"vmin": vmin, "vmax": vmax}
        image = axis.imshow(arrays[name], origin="upper", extent=extent, cmap=land_cmap, **scale)
        if name == "macro_elevation_m":
            ocean = np.ma.masked_where(~arrays["ocean_mask"], np.ones((rows, cols)))
            axis.imshow(ocean, origin="upper", extent=extent,
                        cmap=ListedColormap(["#1678b5"]), interpolation="nearest")
        if name == "final_bed_m":
            network = arrays.get("__river_network__")
            masks = [(arrays["ocean_mask"] | arrays["lake_mask"], "#1678b5"),
                     (arrays["pending_basin_mask"], "#e83997")]
            if network is None and "node_x_m" not in arrays:
                masks.insert(1, (arrays["channel_mask"], "#00e5ff"))
            for mask, color in masks:
                overlay = np.ma.masked_where(~mask, np.ones(mask.shape))
                axis.imshow(overlay, origin="upper", extent=extent,
                            cmap=ListedColormap([color]), interpolation="nearest")
            if network is not None:
                nx, nz = network["node_x_m"], network["node_z_m"]
                sources = network.get("reach_source_node", network.get("reach_source"))
                targets = network.get("reach_target_node", network.get("reach_target"))
            elif "node_x_m" in arrays and "node_z_m" in arrays:
                nx, nz = arrays["node_x_m"].ravel(), arrays["node_z_m"].ravel()
                receiver = arrays["receiver"].ravel()
                sources = np.flatnonzero(arrays["channel_mask"].ravel() & (receiver >= 0))
                targets = receiver[sources]
            else:
                sources = None
            if sources is not None:
                segments = np.stack((np.column_stack((nx[sources], nz[sources])),
                                     np.column_stack((nx[targets], nz[targets]))), axis=1) / 1000.
                if network is None:
                    axis.add_collection(LineCollection(segments, colors="#00e5ff", linewidths=.65))
                else:
                    blocked = np.asarray(network.get("reach_projection_blocked", np.zeros(sources.size, bool)))
                    limited = np.asarray(network.get("reach_max_cut_limited", np.zeros(sources.size, bool)))
                    uphill = np.asarray(network.get("reach_raw_uphill", np.zeros(sources.size, bool)))
                    for selected, color, style in (
                            (~blocked & ~limited & ~uphill, "#00e5ff", "solid"),
                            (~blocked & (limited | uphill), "#ffb000", "dashed"),
                            (blocked, "#f13f9a", "dotted")):
                        axis.add_collection(LineCollection(segments[selected], colors=color,
                                                           linewidths=.8, linestyles=style))
            if network is not None and "spill_source_node" in network:
                active = network["spill_volume_m3"] > 0
                sources, targets = network["spill_source_node"][active], network["spill_target_node"][active]
                segments = np.stack((np.column_stack((nx[sources], nz[sources])),
                                     np.column_stack((nx[targets], nz[targets]))), axis=1) / 1000.
                axis.add_collection(LineCollection(segments, colors="#ffd43b", linewidths=.8))
            axis.legend(handles=[Patch(color="#1678b5", label="Ocean / lake"),
                                 Patch(color="#00e5ff", label="Projected reach"),
                                 Patch(color="#ffb000", label="Uphill / cut limited"),
                                 Patch(color="#f13f9a", label="Projection blocked"),
                                 Patch(color="#e83997", label="Pending basin")],
                        loc="upper left", bbox_to_anchor=(1.02, 1), fontsize="small")
        axis.set_title(title)
        axis.set_xlabel("World X (km)")
        axis.set_ylabel("World Z (km, south)")
        fig.colorbar(image, ax=axis, shrink=.7)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", required=True)
    parser.add_argument("--page-sha256", required=True)
    parser.add_argument("--preset", choices=("lakes", "archipelago", "earth"), default="lakes")
    parser.add_argument("--water", type=float)
    parser.add_argument("--frame-side-m", type=float, default=12_288_000.)
    parser.add_argument("--frame-origin-m", nargs=2, type=float, default=(0., 0.))
    parser.add_argument("--region-side-m", type=float)
    parser.add_argument("--sigma-cells", type=float, default=6.)
    parser.add_argument("--max-source-cells", type=int, default=2049 ** 2)
    parser.add_argument("--origin", nargs=2, type=int, metavar=("X", "Z"))
    parser.add_argument("--shape", nargs=2, type=int, metavar=("ROWS", "COLS"))
    parser.add_argument("--runoff-m-per-year", type=float, required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--channel-threshold-m3-s", type=float, required=True)
    parser.add_argument("--min-lake-area-m2", type=float, default=10000.)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if (args.origin is None) != (args.shape is None):
        parser.error("--origin and --shape must be supplied together")
    destination = Path(args.output)
    if destination.exists():
        raise ValueError("output already exists")
    if not 1 <= args.max_source_cells <= 2049 ** 2:
        raise ValueError("max-source-cells must be between 1 and 2049 squared")
    elevation, page_meta, source_origin = _read_page(
        {"path": args.page, "sha256": args.page_sha256}, seed=20261020)
    size = page_meta["size"]
    if size * size > args.max_source_cells:
        raise ValueError("source page exceeds max-source-cells")
    border = BORDER_BAND_CELLS
    if size <= 2 * border:
        raise ValueError("source page has no trusted interior")
    trusted_slice = (slice(border, size - border), slice(border, size - border)) if border else (slice(None), slice(None))
    trusted = elevation[trusted_slice]
    trusted_origin = [source_origin[0] + border, source_origin[1] + border]
    trusted_size = size - 2 * border
    water = args.water if args.water is not None else {"lakes": .12, "earth": .62, "archipelago": .8}[args.preset]
    spec = LayoutSpec(args.preset, water, world_seed=20261020, layout_id="large-world-first-pass",
        mode="finite", frame_origin_m=args.frame_origin_m, frame_side_m=args.frame_side_m,
        region_side_m=args.region_side_m)
    source = {"sha256": args.page_sha256, "world_seed": 20261020,
              "page_metadata": page_meta, "reading_policy": "single pinned native page; checked archive and seed",
              "page_origin_native_xz": source_origin, "trusted_origin_native_xz": trusted_origin,
              "source_border_cells": border, "trusted_shape_zx": [trusted_size, trusted_size],
              "role": "existing TD detail source; not generated from this macro base"}
    ocean = None
    ocean_metadata = None
    if args.preset != "lakes":
        plan = make_ocean_plan(spec)
        x = (trusted_origin[0] + np.arange(trusted_size))[None, :] * 30.
        z = (trusted_origin[1] + np.arange(trusted_size))[:, None] * 30.
        ocean = sample_ocean_mask(plan, spec, x, z)
        ocean_metadata = plan["metadata"]
    composition = compose_source(spec, trusted, trusted_origin, source_record=source,
                                 ocean_mask=ocean, sigma_cells=args.sigma_cells)
    halo = composition["metadata"]["filter_radius_cells"]
    origin = args.origin if args.origin is not None else [trusted_origin[0] + halo, trusted_origin[1] + halo]
    shape = args.shape if args.shape is not None else [trusted_size - 2 * halo, trusted_size - 2 * halo]
    crop = crop_composition(composition, origin, shape)
    cropped_ocean = crop["ocean_mask"] if crop["ocean_mask"] is not None else np.zeros(shape, dtype=bool)
    formation = form_water_and_rivers(crop["composed_elevation_m"], cropped_ocean, origin, 20261020,
        {"composition_identity": composition["metadata"]["identity"]},
        runoff_m_per_year=args.runoff_m_per_year, duration_seconds=args.duration_seconds,
        channel_threshold_m3_s=args.channel_threshold_m3_s, min_lake_area_m2=args.min_lake_area_m2)
    arrays = {name: value for name, value in crop.items() if name != "metadata" and value is not None}
    arrays.update(formation["arrays"])
    metadata = {"schema": "world-terrain-water-v1", "origin_native_xz": list(origin),
        "shape_zx": list(shape), "spacing_m": 30., "layout": spec.parameters(),
        "composition": crop["metadata"], "ocean_plan": ocean_metadata,
        "formation": formation["metadata"], "formation_identity": formation["identity_sha256"]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".terrain-water-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "product"
        staging.mkdir()
        network = formation.get("network")
        if network is not None:
            metadata["network"] = write_network(staging, network, formation["metadata"].get("network", {}))
        product_identity = identity(arrays, metadata)
        np.savez_compressed(staging / "arrays.npz", **arrays)
        (staging / "metadata.json").write_text(json.dumps({**metadata, "identity_sha256": product_identity},
            indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        render_arrays = arrays if network is None else {**arrays, "__river_network__": network}
        render(render_arrays, origin, staging / "stages.png")
        staging.rename(destination)
    print(json.dumps({"output": str(destination), "identity_sha256": product_identity,
        "lake_cells": int(arrays["lake_mask"].sum()), "pending_cells": int(arrays["pending_basin_mask"].sum()),
        "channel_cells": int(arrays["channel_mask"].sum()), "ocean_cells": int(arrays["ocean_mask"].sum()),
        "max_bed_correction_m": float(np.max(np.abs(arrays["final_bed_m"] - arrays["bed_before_m"]))) }))


if __name__ == "__main__":
    main()
