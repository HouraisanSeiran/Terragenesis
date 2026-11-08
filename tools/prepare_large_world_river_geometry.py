"""Prepare a finite-page, declared-climate river geometry product."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.large_world_river_geometry import build_geometry, load, save
from terrain_pipeline.surface_rivers.metric_network_discharge_product import load_discharge_product
from terrain_pipeline.surface_rivers.native_30m_source import load_native_window


def render(product, path):
    import matplotlib.pyplot as plt
    from terrain_pipeline.terrain_map_style import relief_colormap

    a, m = product["arrays"], product["metadata"]
    rows, cols = a["valid_mask"].shape
    x, z = m["origin_native_xz"]
    extent = [(x - .5) * .03, (x + cols - .5) * .03,
              (z + rows - .5) * .03, (z - .5) * .03]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), constrained_layout=True)
    fields = (np.where(a["valid_mask"], a["source_elevation_m"], np.nan),
              np.where(a["complete_mask"], a["known_q_m3_s"], np.nan),
              np.where(a["channel_mask"], a["channel_width_m"], np.nan))
    titles = ("Source elevation (m)", "Complete representative Q (m3/s)", "Channel width (m)")
    for axis, field, title, cmap in zip(axes, fields, titles, (relief_colormap(), "viridis", "viridis")):
        image = axis.imshow(field, origin="upper", extent=extent, cmap=cmap)
        axis.set_title(title)
        axis.set_xlabel("World X (km)")
        axis.set_ylabel("World Z (km, south)")
        fig.colorbar(image, ax=axis, shrink=.7)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", help="pinned native-page npz")
    parser.add_argument("--page-sha256")
    parser.add_argument("--origin", nargs=2, type=int, metavar=("X", "Z"))
    parser.add_argument("--shape", nargs=2, type=int, metavar=("ROWS", "COLS"))
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--runoff-m-per-year", type=float)
    parser.add_argument("--channel-threshold-m3-s", type=float)
    parser.add_argument("--network", help="saved network product directory; event Q is not reused")
    parser.add_argument("--layout-classes", help="layout-classes.npy from the same new layout page")
    parser.add_argument("--layout-page-json", help="page.json from the same new layout page")
    parser.add_argument("--output")
    parser.add_argument("--figure", help="optional inspection PNG")
    parser.add_argument("--render-existing", help="render an existing saved product without recalculation")
    parser.add_argument("--product-sha256")
    args = parser.parse_args()
    if args.render_existing:
        if not args.figure or not args.product_sha256:
            parser.error("--render-existing requires --product-sha256 and --figure")
        render(load(args.render_existing, args.product_sha256), args.figure)
        return
    if any(value is None for value in (args.page, args.page_sha256, args.origin, args.shape,
                                       args.runoff_m_per_year, args.channel_threshold_m3_s, args.output)):
        parser.error("preparation requires page, page-sha256, origin, shape, runoff, channel threshold and output")
    window = load_native_window([{"path": args.page, "sha256": args.page_sha256}],
        origin_native_xz=args.origin, shape_zx=args.shape, world_seed=args.seed)
    with np.load(args.page, allow_pickle=False) as page:
        page_metadata = json.loads(str(page["metadata_json"].item()))
    source = {"assembly_digest": window["assembly_digest"], "pages": window["source_records"],
              "page_metadata": page_metadata}
    water = None
    classes = None
    if bool(args.layout_classes) != bool(args.layout_page_json):
        raise ValueError("layout classes and page metadata must be supplied together")
    if args.layout_classes:
        layout = json.loads(Path(args.layout_page_json).read_text(encoding="utf-8"))
        if not page_metadata.get("layout_identity") or layout.get("layout_identity") != page_metadata["layout_identity"]:
            raise ValueError("layout metadata does not match the native page")
        if layout.get("conditioning_identity") != page_metadata.get("conditioning_identity"):
            raise ValueError("conditioning identity mismatch")
        if (layout.get("origin_native_xz") != page_metadata["native_origin"]
                or layout.get("page_side_cells") != page_metadata["size"]
                or layout.get("plan", {}).get("seed") != page_metadata["world_seed"]):
            raise ValueError("layout page coordinates, size or seed mismatch")
        classes = np.load(args.layout_classes, allow_pickle=False)
        if classes.dtype != np.uint8 or classes.shape != tuple(args.shape) or not np.isin(classes, [0, 1, 2]).all():
            raise ValueError("layout classes must match the requested window and contain land, sea or lake")
        if args.origin != page_metadata["native_origin"] or args.shape != [page_metadata["size"]] * 2:
            raise ValueError("layout classes require the full matching page window")
        water = (classes != 0) & window["resolved_mask"]
        source["layout_classes_sha256"] = file_sha256(args.layout_classes)
        source["layout_page_json_sha256"] = file_sha256(args.layout_page_json)
        source["layout_parameters"] = layout.get("layout_parameters")
        source["water_classification"] = "layout classes 0 land, 1 sea, 2 lake"
    elif page_metadata.get("layout_identity"):
        raise ValueError("new layout pages require their water classification")
    topology = None
    if args.network:
        network = load_discharge_product(args.network)
        m, a = network["metadata"], network["arrays"]
        if (m["source_sha256"] != window["assembly_digest"] or m["origin_native_cells"] != args.origin
                or m["shape_zx"] != args.shape or m["world_seed"] != args.seed
                or m["spacing_m"] != 30. or not np.array_equal(a["valid_mask"], window["resolved_mask"] & ~(water if water is not None else False))):
            raise ValueError("saved network does not match this source assembly")
        topology = {key: a[key] for key in ("receiver", "terminal_kind", "upstream_unknown_mask")}
        source["network_identity"] = network["identity_sha256"]
    product = build_geometry(window["field"], window["resolved_mask"], args.origin, args.seed, source,
        runoff_m_per_year=args.runoff_m_per_year, channel_threshold_m3_s=args.channel_threshold_m3_s,
        topology=topology, water_mask=water, water_classes=classes)
    save(args.output, product)
    if args.figure:
        render(product, args.figure)
    print(json.dumps({"output": args.output, "sha256": file_sha256(args.output),
        "identity": product["identity_sha256"], "channel_cells": int(product["arrays"]["channel_mask"].sum()),
        "pending_cells": int(product["arrays"]["pending_mask"].sum())}, indent=2))


if __name__ == "__main__":
    main()
