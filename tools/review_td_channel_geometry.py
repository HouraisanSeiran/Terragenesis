"""Cold numeric and visual acceptance for discharge-derived TD channel cuts."""
import argparse
import html
import json
import os
from pathlib import Path
import sys
import time

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256
from tools.review_large_td_confluence import load_archive
from tools.review_td_lowland_runoff import WEATHER_SOURCE, WEATHER_SOURCE_SHA, product_identity
from terrain_pipeline.runoff import OBJECT_FLAGS as OBJECT_FLAGS

PROTECTED_FLAGS = OBJECT_FLAGS["wetland"] | OBJECT_FLAGS["shallow_lake"]


def hardness_fields(shape, spacing, origin, seed):
    from diffusion.geographic_noise import field
    bed = np.empty(shape)
    bank = np.empty(shape)
    x = origin[0] + np.arange(shape[1])[None, :] * spacing
    for start in range(0, shape[0], 128):
        stop = min(start + 128, shape[0])
        z = origin[1] + np.arange(start, stop)[:, None] * spacing
        tile_x, tile_z = np.broadcast_arrays(x, z)
        scales = ((6000., .6), (1800., .3), (600., .1))
        bed[start:stop] = .5 * (1. + field(tile_x, tile_z, seed, 2101, scales))
        bank[start:stop] = .5 * (1. + field(tile_x, tile_z, seed, 2203, scales))
    return np.clip(bed, 0., 1.), np.clip(bank, 0., 1.)


def generate(source, source_metadata, source_path, source_sha):
    from terrain_pipeline.channel_geometry import build_discharge_geometry, channel_section_cut
    height = source["original_td_m"]
    spacing = source_metadata["spacing_m"]
    bed, bank = hardness_fields(height.shape, spacing, source_metadata["origin_xz_m"], source_metadata["seed"])
    channel = source["permanent_channel_mask"].astype(bool) | source["seasonal_channel_mask"].astype(bool)
    protected = (source["object_flags"] & PROTECTED_FLAGS) != 0
    result = build_discharge_geometry(height, source["mean_routed_q_m3_s"], channel, spacing,
        bed_hardness=bed, bank_hardness=bank, protected_mask=protected)
    arrays = result["arrays"]
    arrays.pop("bed_elevation_m")
    arrays["protected_mask"] = protected
    selected = np.flatnonzero(arrays["channel_width_m"].ravel() > 0)
    ranked = selected[np.argsort(arrays["representative_q_m3_s"].ravel()[selected])]
    section_ids = ranked[np.unique(np.linspace(0, max(0, ranked.size-1), min(9, ranked.size)).astype(int))]
    offsets = np.linspace(-120., 120., 481)
    arrays["section_native_cell_ids"] = section_ids
    arrays["section_offset_m"] = offsets
    arrays["section_parametric_cut_m"] = channel_section_cut(offsets[None, :],
        arrays["channel_width_m"].ravel()[section_ids, None], arrays["channel_depth_m"].ravel()[section_ids, None])
    arrays["section_parametric_bed_elevation_m"] = height.ravel()[section_ids, None] - arrays["section_parametric_cut_m"]
    metadata = {"schema": "td-discharge-channel-geometry-review-v1", "geometry": result["metadata"],
        "source_archive": {"path": str(source_path.resolve()), "sha256": source_sha},
        "spacing_m": spacing, "origin_xz_m": source_metadata["origin_xz_m"], "seed": source_metadata["seed"],
        "discharge_input": "saved last synthetic year duration-weighted mean_routed_q_m3_s",
        "hardness": {"synthetic_not_geological_observation": True, "algorithm": "geographic_noise.field",
            "bed_salt": 2101, "bank_salt": 2203, "scales_m_weights": [[6000., .6], [1800., .3], [600., .1]], "range": [0., 1.]},
        "protected_policy": "saved wetland and shallow-lake flags preserve design dimensions but prevent actual raster excavation",
        "coordinate_convention": "row z south, column x east; absolute metres; saved native cell IDs",
        "resources": {"max_cpu_cores": 2, "priority": "BelowNormal", "numeric_threads": 1},
        "display_width_exaggeration": 12., "calibrated": False, "publishable": False}
    metadata["product_identity_sha256"] = product_identity(arrays, metadata)
    return arrays, metadata


def confluence_evidence(source, arrays):
    rec = source["receiver"].ravel()
    channel = arrays["channel_mask"].ravel()
    q = arrays["representative_q_m3_s"].ravel()
    width = arrays["channel_width_m"].ravel()
    depth = arrays["channel_depth_m"].ravel()
    ids = np.flatnonzero(channel & (rec >= 0))
    counts = np.bincount(rec[ids], minlength=rec.size)
    junctions = np.flatnonzero((counts >= 2) & channel)
    donors = {}
    for cell in ids:
        if counts[rec[cell]] >= 2:
            donors.setdefault(int(rec[cell]), []).append(int(cell))
    q_reduced = 0
    width_reduced = 0
    depth_reduced = 0
    width_increased = 0
    depth_increased = 0
    q_increased = 0
    for cell in junctions:
        incoming = donors[int(cell)]
        q_reduced += q[cell] + 1e-12 < max(q[incoming])
        width_reduced += width[cell] + 1e-12 < max(width[incoming])
        depth_reduced += depth[cell] + 1e-12 < max(depth[incoming])
        width_increased += width[cell] > max(width[incoming]) + 1e-12
        depth_increased += depth[cell] > max(depth[incoming]) + 1e-12
        q_increased += q[cell] > max(q[incoming]) + 1e-12
    def row(cell):
        return {"cell": int(cell), "q_m3_s": float(q[cell]), "width_m": float(width[cell]), "incision_depth_m": float(depth[cell])}
    strongest = junctions[np.argsort(q[junctions])[-5:][::-1]]
    return {"all_selected_confluence_count": int(junctions.size), "downstream_q_below_largest_donor_count": int(q_reduced),
        "downstream_width_below_largest_donor_count": int(width_reduced),
        "downstream_depth_below_largest_donor_count": int(depth_reduced),
        "downstream_q_above_largest_donor_count": int(q_increased),
        "downstream_width_above_largest_donor_count": int(width_increased),
        "downstream_depth_above_largest_donor_count": int(depth_increased),
        "interpretation": "Q can decrease at retention cells; width also responds to independently varying hardness/protection",
        "strongest_by_downstream_q": [{"downstream": row(cell), "donors": [row(d) for d in donors[int(cell)]]} for cell in strongest]}


def cold_audit(arrays, metadata, source):
    from scipy.ndimage import distance_transform_edt
    c = metadata["geometry"]["config"]
    q = source["mean_routed_q_m3_s"]
    bed, bank = arrays["bed_hardness"], arrays["bank_hardness"]
    protected = (source["object_flags"] & PROTECTED_FLAGS) != 0
    mask = source["permanent_channel_mask"].astype(bool) | source["seasonal_channel_mask"].astype(bool)
    active = mask & (q > 0)
    saturation = 1. - np.exp(-c["generation_exposure"])
    width = np.where(active, np.minimum(c["max_width_m"], c["width_at_unit_q_m"] * q ** c["width_q_exponent"]
        * (1. + 1.5 * bed) * (.5 + 1.5 * (1. - bank))) * saturation, 0.)
    depth = np.where(active, np.minimum(c["max_incise_m"], c["depth_at_unit_q_m"] * q ** c["depth_q_exponent"]
        * (.4 + 1.2 * (1. - bed)) * (.8 + .4 * bank)) * saturation, 0.)
    expected_cut = np.zeros(q.shape)
    raster_active = active & ~protected
    if raster_active.any():
        distance, nearest = distance_transform_edt(~raster_active, sampling=metadata["spacing_m"], return_indices=True)
        w, d = width[tuple(nearest)], depth[tuple(nearest)]
        taper = np.zeros(q.shape)
        np.divide(w / 2. - distance, w * (1. - c["bottom_width_fraction"]) / 2., out=taper, where=w > 0)
        expected_cut = d * np.clip(taper, 0., 1.)
        expected_cut[protected] = 0.
    budget = metadata["geometry"]["material_budget"]
    volume = float(arrays["cut_depth_m"].sum() * metadata["spacing_m"] ** 2)
    gates = {"product_identity": product_identity(arrays, metadata) == metadata["product_identity_sha256"],
        "representative_q_matches_saved_source": np.allclose(arrays["representative_q_m3_s"], q, rtol=1e-12, atol=1e-12),
        "channel_mask_matches_source": np.array_equal(arrays["channel_mask"], mask),
        "protected_mask_matches_source": np.array_equal(arrays["protected_mask"], protected),
        "independent_width_formula": np.allclose(arrays["channel_width_m"], width, rtol=1e-12, atol=1e-12),
        "independent_depth_formula": np.allclose(arrays["channel_depth_m"], depth, rtol=1e-12, atol=1e-12),
        "bottom_width": np.allclose(arrays["bottom_width_m"], width * c["bottom_width_fraction"]),
        "independent_actual_raster_cut": np.allclose(arrays["cut_depth_m"], expected_cut, rtol=1e-12, atol=1e-12),
        "finite_fields": all(np.isfinite(v).all() for v in arrays.values()),
        "nonnegative_geometry_fields": all(np.all(arrays[key] >= 0) for key in ("channel_width_m", "channel_depth_m", "cut_depth_m", "representative_q_m3_s")),
        "bulk_volume_ledger": bool(np.isclose(volume, budget["removed_terrain_bulk_m3"], rtol=1e-12)
            and np.isclose(volume, budget["coarse_raster_edit_bulk_m3"], rtol=1e-12)
            and np.isclose(volume, budget["unplaced_excavated_bulk_m3"], rtol=1e-12) and budget["redeposited_bulk_m3"] == 0),
        "no_immutable_td_or_graph_duplication": not any(key in arrays for key in ("original_td_m", "receiver", "topological_order"))}
    if "section_native_cell_ids" in arrays:
        cells = arrays["section_native_cell_ids"]
        sw, sd = width.ravel()[cells, None], depth.ravel()[cells, None]
        taper = np.zeros((cells.size, arrays["section_offset_m"].size))
        np.divide(sw/2.-np.abs(arrays["section_offset_m"][None, :]), sw*(1.-c["bottom_width_fraction"])/2., out=taper, where=sw > 0)
        section_cut = sd*np.clip(taper, 0., 1.)
        gates["independent_saved_parametric_sections"] = bool(np.allclose(arrays["section_parametric_cut_m"], section_cut)
            and np.allclose(arrays["section_parametric_bed_elevation_m"], source["original_td_m"].ravel()[cells, None]-section_cut))
    widths = width[width > 0]
    return {"passed": bool(all(gates.values())), "gates": {k: bool(v) for k, v in gates.items()},
        "material_budget": budget, "width_quantiles_m": np.quantile(widths, [0., .5, .9, 1.]).tolist() if widths.size else [],
        "subgrid_channel_fraction": float(np.mean(widths < metadata["spacing_m"])) if widths.size else 0.,
        "actual_cut_cell_count": int(np.count_nonzero(arrays["cut_depth_m"])),
        "confluences": confluence_evidence(source, arrays),
        "interpretation": "Separate source-relative excavation candidate; incision is not water depth. Coarse cut volume retained unplaced; water levels, sediment transport and connected subgrid bed unsolved."}


def mainstem_ids(source, arrays):
    rec = source["receiver"].ravel()
    q = arrays["representative_q_m3_s"].ravel()
    mask = arrays["channel_mask"].ravel()
    if not mask.any():
        return np.empty(0, np.int64)
    best = np.full(rec.size, -1, np.int64)
    for cell in np.flatnonzero(mask & (rec >= 0)):
        target = rec[cell]
        if best[target] < 0 or q[cell] > q[best[target]]:
            best[target] = cell
    cell = int(np.argmax(np.where(mask, q, -1.)))
    path = [cell]
    while best[cell] >= 0:
        cell = int(best[cell])
        path.append(cell)
    return np.asarray(path[::-1], np.int64)


def render(source, arrays, metadata, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from terrain_pipeline.channel_geometry import build_discharge_geometry, channel_section_cut
    height = source["original_td_m"]
    spacing = metadata["spacing_m"]
    ox, oz = metadata["origin_xz_m"]
    cols = height.shape[1]
    rec = source["receiver"].ravel()
    widths = arrays["channel_width_m"].ravel()
    ids = np.flatnonzero((widths > 0) & (rec >= 0))
    def xy(cells):
        return np.c_[ox + cells % cols * spacing, oz + cells // cols * spacing] / 1000.
    extent = np.array([ox-spacing/2., ox+(cols-.5)*spacing, oz+(height.shape[0]-.5)*spacing, oz-spacing/2.]) / 1000.
    fig, ax = plt.subplots(figsize=(12, 11), constrained_layout=True)
    terrain = ax.imshow(height, cmap="terrain", extent=extent, vmin=float(height.min()), vmax=float(height.max()))
    fig.colorbar(terrain, ax=ax, label="Immutable TD elevation (m)", shrink=.7, location="left")
    ax.set(xlabel="World x east (km)", ylabel="World z south (km)", title="Q-derived physical incision width: display exaggerated 12x")
    fig.canvas.draw()
    points_per_km = ax.get_window_extent().width * 72. / fig.dpi / (extent[1]-extent[0])
    lines = LineCollection(np.stack([xy(ids), xy(rec[ids])], axis=1), cmap="cool",
        linewidths=widths[ids]/1000. * points_per_km * metadata["display_width_exaggeration"],
        linestyles=["dashed" if source["seasonal_channel_mask"].ravel()[cell] else "solid" for cell in ids])
    lines.set_array(widths[ids])
    ax.add_collection(lines)
    fig.colorbar(lines, ax=ax, label="Physical top incision width (m)", shrink=.7)
    fig.savefig(output / "channel-width-map.png", dpi=150)
    plt.close(fig)
    path = mainstem_ids(source, arrays)
    positions = xy(path) * 1000.
    distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(positions, axis=0), axis=1))] / 1000.
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    for ax, key, label in zip(axes, ("representative_q_m3_s", "channel_width_m", "channel_depth_m"),
                             ("Annual representative Q (m3/s)", "Top incision width (m)", "Source-relative incision (m)")):
        ax.plot(distance, arrays[key].ravel()[path], color="#008c95")
        ax.set_ylabel(label)
        ax.grid(alpha=.2)
    axes[-1].set_xlabel("Strongest-Q donor mainstem distance downstream (km)")
    fig.savefig(output / "mainstem-q-width-depth.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    offsets = np.linspace(-100., 100., 801)
    for hardness, color in ((0., "#087f8c"), (1., "#bf3d5e")):
        sample = build_discharge_geometry(np.zeros((1, 1)), np.full((12, 1, 1), 10.), np.ones((1, 1), bool), 1.,
            bed_hardness=hardness, bank_hardness=.5)["arrays"]
        width, depth = sample["channel_width_m"].item(), sample["channel_depth_m"].item()
        axes[0].plot(offsets, -channel_section_cut(offsets, width, depth), color=color,
            label=f"Bed hardness {hardness:g}; width {width:.2f}m, cut {depth:.2f}m")
    axes[0].set(xlabel="Transverse offset (m)", ylabel="Source-relative bed (m)", title="Parametric equal Q=10 m3/s, equal bank hardness=.5")
    axes[0].legend(fontsize=8)
    cut_channel = (widths > 0) & (arrays["cut_depth_m"].ravel() > 0)
    cell = int(np.argmax(np.where(cut_channel, widths, -1.))) if cut_channel.any() else int(np.argmax(widths))
    row, col = divmod(cell, cols)
    columns = np.arange(max(0, col-5), min(cols, col+6))
    axes[1].plot((columns-col)*spacing, height[row, columns], "o-", label="Immutable TD")
    axes[1].plot((columns-col)*spacing, height[row, columns]-arrays["cut_depth_m"][row, columns], "o-", label="Actual separate 30m raster cut")
    axes[1].set(xlabel="East-west offset (m); not necessarily normal to river", ylabel="Elevation (m)",
        title=f"Actual cut through widest excavated channel; native cell {cell}")
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=.2)
    fig.savefig(output / "hardness-and-actual-cut-sections.png", dpi=150)
    plt.close(fig)
    images = ["channel-width-map.png", "mainstem-q-width-depth.png", "hardness-and-actual-cut-sections.png"]
    strongest = confluence_evidence(source, arrays)["strongest_by_downstream_q"]
    if strongest:
        junction = strongest[0]
        center = junction["downstream"]["cell"]
        cx, cz = xy(np.array([center]))[0]
        radius_km = .9
        fig, (ax, detail) = plt.subplots(1, 2, figsize=(14, 8), gridspec_kw={"width_ratios": [3, 1.6]}, constrained_layout=True)
        ax.imshow(height, cmap="terrain", extent=extent, vmin=float(height.min()), vmax=float(height.max()))
        ax.set(xlim=(cx-radius_km, cx+radius_km), ylim=(cz+radius_km, cz-radius_km), aspect="equal",
            xlabel="World x east (km)", ylabel="World z south (km)", title="Strongest-Q confluence: true physical widths (1x)")
        coords = xy(ids)
        local = ids[(np.abs(coords[:, 0]-cx) < radius_km) & (np.abs(coords[:, 1]-cz) < radius_km)]
        fig.canvas.draw()
        points_per_km = ax.get_window_extent().width * 72. / fig.dpi / (2.*radius_km)
        segments = LineCollection(np.stack([xy(local), xy(rec[local])], axis=1), cmap="cool",
            linewidths=widths[local]/1000.*points_per_km,
            linestyles=["dashed" if source["seasonal_channel_mask"].ravel()[cell] else "solid" for cell in local])
        segments.set_array(widths[local])
        segments.set_clim(lines.get_clim())
        segments.set_capstyle("round")
        segments.set_joinstyle("round")
        ax.add_collection(segments)
        detail.axis("off")
        detail.set_title("Saved numeric sections", fontsize=13)
        section_rows = [("C", junction["downstream"])] + [(f"D{index+1}", row) for index, row in enumerate(junction["donors"])]
        for index, (label, row) in enumerate(section_rows):
            px, pz = xy(np.array([row["cell"]]))[0]
            ax.plot(px, pz, "o", color="#111111", markersize=4)
            label_offset = (45, -35) if index == 0 else (-65, 45 if index % 2 else -55)
            ax.annotate(label, (px, pz), xytext=label_offset, textcoords="offset points",
                arrowprops={"arrowstyle": "->", "color": "#111111", "linewidth": .8},
                color="#111111", fontsize=10, fontweight="bold", bbox={"facecolor": "white", "edgecolor": "none", "alpha": .95, "pad": 2.})
            detail.text(0., .92-index*.18, f"{label}: {'Downstream' if index == 0 else 'Incoming donor'} cell {row['cell']}\n"
                f"Q {row['q_m3_s']:.4f} m3/s\nTop width {row['width_m']:.2f} m; incision {row['incision_depth_m']:.2f} m",
                transform=detail.transAxes, va="top", fontsize=10)
        detail.text(0., .05, "Solid: persistent candidate\nDashed: seasonal candidate\nWidths: true metres, 1x display\nIncision is not water depth", transform=detail.transAxes, fontsize=9)
        fig.savefig(output / "strongest-confluence-zoom.png", dpi=150)
        plt.close(fig)
        images.append("strongest-confluence-zoom.png")
    return images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=WEATHER_SOURCE)
    parser.add_argument("--expected-source-sha256", default=WEATHER_SOURCE_SHA)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/hydrological-planning-domain/large-td-channel-geometry-20261015-01")
    args = parser.parse_args()
    from tools.prepare_hydrology_v5_lake import limit_resources
    limit_resources()
    start = time.perf_counter()
    if args.output.exists():
        raise FileExistsError(args.output)
    source, source_metadata = load_archive(args.source, args.expected_source_sha256)
    if source["original_td_m"].shape != (1280, 1280) or source_metadata["spacing_m"] != 30. or source_metadata["seed"] != 3:
        raise ValueError("pinned seed3 38.4km 1280-square source required")
    arrays, metadata = generate(source, source_metadata, args.source, args.expected_source_sha256)
    args.output.mkdir(parents=True, exist_ok=False)
    archive = args.output / "channel-geometry.npz"
    with archive.open("xb") as stream:
        np.savez_compressed(stream, **arrays, metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
    del arrays
    cold, cold_metadata = load_archive(archive)
    report = cold_audit(cold, cold_metadata, source)
    report.update(archive_sha256=file_sha256(archive), source_archive=metadata["source_archive"], resources=metadata["resources"])
    images = render(source, cold, cold_metadata, args.output)
    report["source_sha256_unchanged_after_run"] = file_sha256(args.source) == args.expected_source_sha256
    report["passed"] = report["passed"] and report["source_sha256_unchanged_after_run"]
    report["total_wall_seconds"] = time.perf_counter()-start
    (args.output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    document = '<!doctype html><meta charset="utf-8"><title>Discharge channel geometry</title><style>body{font-family:sans-serif;margin:24px}img{width:100%}pre{white-space:pre-wrap}</style><h1>Discharge channel geometry acceptance</h1>'
    document += '<p>' + html.escape(report["interpretation"]) + '</p><p>Full-map widths use 12x display exaggeration; the confluence zoom uses true physical widths at 1x. The numeric archive retains metres. Hardness is synthetic. Mainstem follows the largest-Q incoming donor. Confluence tables include all selected junction counts; examples use the five strongest downstream Q.</p>'
    document += ''.join('<img src="'+name+'" alt="'+name+'">' for name in images)
    document += '<pre>' + html.escape(json.dumps(report, indent=2, allow_nan=False)) + '</pre>'
    (args.output / "preview.html").write_text(document, encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(args.output.resolve()), "seconds": report["total_wall_seconds"]}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
