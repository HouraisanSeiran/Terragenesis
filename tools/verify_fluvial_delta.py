"""Finite saved-TD macrocoast experiment and independent archive audit."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import (
    FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval, simulate_fluvial_delta,
)

SOURCE = ROOT / "verification/hydrological-planning-domain/full-edges-v5-20261014-03/edge-8470-8600-v7-shared-sections-owned-halo2/detail.npz"
CROP = (64, 192, 208, 336)


def source_input(sediment_per_interval_m3=5000.):
    with np.load(SOURCE, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        crop = np.s_[CROP[0]:CROP[1], CROP[2]:CROP[3]]
        height = archive["derived_height_m"][crop].astype(np.float64)
        ocean = archive["ocean_mask"][crop].copy()
        raw = archive["original_td_m"][crop].copy()
    origin = metadata["origin_xz_m"]
    terrain = TerrainGrid(height, np.ones(height.shape, bool), origin[0] + CROP[2] * 30,
                          origin[1] + CROP[0] * 30, 30., 30., "conditioned_terrain",
                          "saved-v5-registered-macrocoast-TD-projection", file_sha256(SOURCE),
                          generation_seed=3, source_path=str(SOURCE))
    export = ocean.copy()
    export[1:-1, 1:-1] = False
    boundary = FluvialDeltaBoundary(ocean, export, 0., 2., "saved-v5-detail-ocean-mask")
    forcing = tuple(FluvialDeltaInterval((64, 30), 200000., sediment_per_interval_m3) for _ in range(32))
    config = FluvialDeltaConfig(split_cost_scale_m=90.)
    provenance = {"path": str(SOURCE), "sha256": terrain.source_sha256,
                  "crop_rows_columns": list(CROP), "raw_td_sha256": metadata["raw_provenance"]["archive_sha256"],
                  "saved_detail_identity": metadata["identity"], "plan_identity": metadata["plan_identity"],
                  "interpretation": "TD plus saved macro projection; registered model coast, naturalness unverified",
                  "sediment_origin": "explicit synthetic delivery; prior excavation is not sediment",
                  "natural_outlet_verified": False}
    return terrain, boundary, forcing, config, provenance, raw


def save_result(path, terrain, boundary, forcing, result, provenance, raw):
    records = result["intervals"]
    offsets, cells, volumes = [0], [], []
    for record in records:
        for edge in record["flow_edges"]:
            cells.append((*edge["from_cell"], *edge["to_cell"]))
            volumes.append((edge["water_volume_m3"], edge["sediment_solid_m3"]))
        offsets.append(len(cells))
    metadata = {"core": result["metadata"], "source": provenance,
                "terrain": {key: value for key, value in asdict(terrain).items()
                            if key not in ("elevation_m", "valid_mask")},
                "forcing": [asdict(item) for item in forcing],
                "water_ledger": result["water_ledger"], "solid_ledger": result["solid_ledger"],
                "interval_ledgers": [{"water": item["water_ledger"], "solid": item["solid_ledger"]} for item in records]}
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream, metadata_json=np.array(json.dumps(metadata, sort_keys=True)),
                            initial_bed_m=result["initial_bed_m"], final_bed_m=result["final_bed_m"],
                            raw_td_m=raw, deposited_solid_m3=result["deposited_solid_m3"],
                            valid_mask=terrain.valid_mask, ocean_mask=boundary.initial_ocean_mask,
                            export_mask=boundary.ocean_export_mask,
                            water=np.stack([item["water_throughput_m3"] for item in records]),
                            sediment=np.stack([item["sediment_throughput_solid_m3"] for item in records]),
                            deposits=np.stack([item["deposited_solid_m3"] for item in records]),
                            edge_offsets=np.asarray(offsets, np.int64),
                            edge_cells=np.asarray(cells, np.int32).reshape(-1, 4),
                            edge_volumes=np.asarray(volumes, float).reshape(-1, 2))


def audit_archive(path, expected_sha256=None, verify_source=True):
    if expected_sha256 and file_sha256(path) != expected_sha256:
        raise ValueError("saved result hash mismatch")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
        metadata = json.loads(str(archive["metadata_json"].item()))
    source = metadata["source"]
    if verify_source:
        if file_sha256(source["path"]) != source["sha256"]:
            raise ValueError("source hash mismatch")
        r0, r1, c0, c1 = source["crop_rows_columns"]
        with np.load(source["path"], allow_pickle=False) as original:
            for saved, original_key in (("initial_bed_m", "derived_height_m"), ("raw_td_m", "original_td_m"), ("ocean_mask", "ocean_mask")):
                np.testing.assert_array_equal(arrays[saved], original[original_key][r0:r1, c0:c1])
    initial = arrays["initial_bed_m"]
    rows, columns = initial.shape
    config = metadata["core"]["config"]
    area = metadata["terrain"]["dx_m"] * metadata["terrain"]["dz_m"]
    bulk_per_solid = 1. / ((1. - config["porosity"]) * area)
    bed = initial.copy()
    maximum_residual = 0.
    exported_water, exported_solid, retained_water, unresolved_solid = [], [], [], []
    export = arrays["export_mask"]
    perimeter = np.ones(initial.shape, bool)
    perimeter[1:-1, 1:-1] = False
    if np.any(export & ~(perimeter & arrays["ocean_mask"])):
        raise ValueError("exports lack registered perimeter ocean support")
    for index, forcing in enumerate(metadata["forcing"]):
        start, stop = arrays["edge_offsets"][index:index + 2]
        cells, volumes = arrays["edge_cells"][start:stop], arrays["edge_volumes"][start:stop]
        if np.any(volumes < 0.) or not np.isfinite(volumes).all():
            raise ValueError("invalid edge volumes")
        difference = np.abs(cells[:, :2] - cells[:, 2:])
        if cells.size and (np.any(cells < 0) or np.any(cells[:, (0, 2)] >= rows) or np.any(cells[:, (1, 3)] >= columns)
                           or np.any(difference > 1) or np.any(difference.sum(axis=1) == 0)):
            raise ValueError("nonlocal or unbounded path")
        if cells.size and (np.any(bed[cells[:, 0], cells[:, 1]] > metadata["core"]["river_head_m"])
                           or np.any(bed[cells[:, 2], cells[:, 3]] > metadata["core"]["river_head_m"])):
            raise ValueError("path crosses bed above declared head")
        diagonal = cells[(difference[:, 0] == 1) & (difference[:, 1] == 1)]
        if diagonal.size:
            corner_a, corner_b = (diagonal[:, 0], diagonal[:, 3]), (diagonal[:, 2], diagonal[:, 1])
            head = metadata["core"]["river_head_m"]
            if (np.any(~arrays["valid_mask"][corner_a]) or np.any(~arrays["valid_mask"][corner_b])
                    or np.any(bed[corner_a] > head) or np.any(bed[corner_b] > head)):
                raise ValueError("diagonal path crosses blocked cardinal corner")
        incoming, outgoing = [], []
        for channel in range(2):
            incoming.append(np.bincount(cells[:, 2] * columns + cells[:, 3], weights=volumes[:, channel], minlength=initial.size).astype(float).reshape(initial.shape))
            outgoing.append(np.bincount(cells[:, 0] * columns + cells[:, 1], weights=volumes[:, channel], minlength=initial.size).astype(float).reshape(initial.shape))
        inlet = tuple(forcing["inlet_cell"])
        incoming[0][inlet] += forcing["water_volume_m3"]
        incoming[1][inlet] += forcing["sediment_solid_m3"]
        deposit = arrays["deposits"][index]
        np.testing.assert_allclose(incoming[0], arrays["water"][index], atol=1e-7, rtol=1e-12)
        np.testing.assert_allclose(incoming[1], arrays["sediment"][index], atol=1e-7, rtol=1e-12)
        remaining_water = incoming[0] - outgoing[0]
        remaining_solid = incoming[1] - outgoing[1] - deposit
        permitted = export.copy()
        permitted[inlet] = True
        for remaining in (remaining_water, remaining_solid):
            maximum_residual = max(maximum_residual, float(np.max(np.abs(remaining[~permitted]))))
            if np.any(remaining < -1e-7) or np.max(np.abs(remaining[~permitted]), initial=0.) > 1e-7:
                raise ValueError("cell volume conservation failed")
        if np.any(deposit < 0.) or np.max(deposit * bulk_per_solid) > config["max_deposit_depth_per_interval_m"] + 1e-10:
            raise ValueError("deposition exceeds interval bound")
        exported_water.append(float(remaining_water[export].sum()))
        exported_solid.append(float(remaining_solid[export].sum()))
        retained_water.append(float(remaining_water[~export].sum()))
        unresolved_solid.append(float(remaining_solid[~export].sum()))
        ledger = metadata["interval_ledgers"][index]
        np.testing.assert_allclose(ledger["water"]["input_m3"], forcing["water_volume_m3"], atol=1e-7, rtol=1e-12)
        np.testing.assert_allclose(ledger["solid"]["input_solid_m3"], forcing["sediment_solid_m3"], atol=1e-7, rtol=1e-12)
        for values, key in ((exported_water, "ocean_export_m3"), (retained_water, "retained_m3")):
            np.testing.assert_allclose(values[-1], ledger["water"][key], atol=1e-7, rtol=1e-12)
        for value, key in ((exported_solid[-1], "ocean_export_solid_m3"), (unresolved_solid[-1], "unresolved_solid_m3"), (deposit.sum(), "deposited_solid_m3")):
            np.testing.assert_allclose(value, ledger["solid"][key], atol=1e-7, rtol=1e-12)
        bed += deposit * bulk_per_solid
    np.testing.assert_allclose(bed, arrays["final_bed_m"], atol=1e-9, rtol=1e-12)
    np.testing.assert_allclose(arrays["deposits"].sum(axis=0), arrays["deposited_solid_m3"], atol=1e-9, rtol=1e-12)
    totals = {"water_input": sum(item["water_volume_m3"] for item in metadata["forcing"]),
              "solid_input": sum(item["sediment_solid_m3"] for item in metadata["forcing"])}
    np.testing.assert_allclose(totals["water_input"], sum(exported_water) + sum(retained_water), atol=1e-6, rtol=1e-12)
    np.testing.assert_allclose(totals["solid_input"], sum(exported_solid) + sum(unresolved_solid) + arrays["deposits"].sum(), atol=1e-6, rtol=1e-12)
    for value, key in ((totals["water_input"], "input_m3"), (sum(exported_water), "ocean_export_m3"), (sum(retained_water), "retained_m3")):
        np.testing.assert_allclose(value, metadata["water_ledger"][key], atol=1e-6, rtol=1e-12)
    for value, key in ((totals["solid_input"], "input_solid_m3"), (sum(exported_solid), "ocean_export_solid_m3"),
                       (sum(unresolved_solid), "unresolved_solid_m3"), (arrays["deposits"].sum(), "deposited_solid_m3"),
                       (arrays["deposits"].sum() / (1. - config["porosity"]), "deposit_bulk_m3")):
        np.testing.assert_allclose(value, metadata["solid_ledger"][key], atol=1e-6, rtol=1e-12)
    return {"passed": True, "maximum_cell_residual_m3": maximum_residual,
            "max_height_change_m": float((bed - initial).max()), "interval_count": len(metadata["forcing"])}


def render(path, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        initial, final = archive["initial_bed_m"], archive["final_bed_m"]
        initial_ocean = archive["ocean_mask"]
        water, deposits = archive["water"], archive["deposits"]
        fig, axes = plt.subplots(2, 3, figsize=(13, 8), constrained_layout=True)
        width = initial.shape[1] * metadata["terrain"]["dx_m"]
        height = initial.shape[0] * metadata["terrain"]["dz_m"]
        scale, units = (1000., "km") if max(width, height) >= 1000. else (1., "m")
        synthetic = metadata["terrain"]["source_id"].startswith("SYNTHETIC")
        bed_low = float(min(initial.min(), final.min()) - .1) if synthetic else -5
        bed_high = float(max(initial.max(), final.max()) + .1) if synthetic else 15
        panels = ((initial, "SYNTHETIC shallow shelf: initial bed" if synthetic else "Initial saved TD + macro bed", "terrain", bed_low, bed_high),
                  (final, "SYNTHETIC shelf after deposition" if synthetic else "Bed after deposition", "terrain", bed_low, bed_high),
                  (final - initial, "Deposited bed height (m)", "magma", 0, None),
                  (np.log10(1 + water[0]), "First interval water passage log10(m3 + 1)", "viridis", 0, 5.4),
                  (np.log10(1 + water[-1]), "Last interval water passage log10(m3 + 1)", "viridis", 0, 5.4),
                  (deposits.sum(axis=0), "Deposited solid volume per cell (m3)", "magma", 0, None))
        for axis, (data, title, cmap, low, high) in zip(axes.ravel(), panels):
            im = axis.imshow(data, cmap=cmap, vmin=low, vmax=high, extent=(0, width / scale, height / scale, 0))
            axis.set_title(title, fontsize=10)
            axis.set_xlabel("x (" + units + ")")
            axis.set_ylabel("z (" + units + ")")
            fig.colorbar(im, ax=axis, shrink=.8)
        fig.savefig(output, dpi=120)
        plt.close(fig)


def render_locator(output):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    with np.load(SOURCE, allow_pickle=False) as archive:
        height, ocean = archive["derived_height_m"], archive["ocean_mask"]
    fig, axis = plt.subplots(figsize=(7, 6), constrained_layout=True)
    image = axis.imshow(height, cmap="terrain", vmin=-80, vmax=320)
    axis.contour(ocean.astype(float), levels=[.5], colors="cyan", linewidths=.8)
    axis.add_patch(Rectangle((CROP[2] - .5, CROP[0] - .5), CROP[3] - CROP[2], CROP[1] - CROP[0],
                             fill=False, edgecolor="red", linewidth=1.5))
    axis.plot(238, 128, marker="o", color="red", markersize=4)
    axis.set_title("Saved v5 full mouth support: registered ocean + experiment window", fontsize=10)
    axis.set_xlabel("Native 30 m columns")
    axis.set_ylabel("Native 30 m rows")
    fig.colorbar(image, ax=axis, label="Saved TD + macro bed (m)")
    fig.savefig(output, dpi=120)
    plt.close(fig)


def render_mouth_zoom(path, output):
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        initial, final = archive["initial_bed_m"], archive["final_bed_m"]
        initial_ocean = archive["ocean_mask"]
        offsets, cells, volumes = archive["edge_offsets"], archive["edge_cells"], archive["edge_volumes"]
        water, deposits = archive["water"], archive["deposits"]
    row, column = metadata["forcing"][0]["inlet_cell"]
    spacing = metadata["terrain"]["dx_m"]
    radius = max(1, int(300 / spacing))
    r0, r1 = max(0, row - radius), min(initial.shape[0], row + radius + 1)
    c0, c1 = max(0, column - radius), min(initial.shape[1], column + radius + 1)
    extent = ((c0 - column - .5) * spacing, (c1 - column - .5) * spacing,
              (r1 - row - .5) * spacing, (r0 - row - .5) * spacing)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    for axis, index, title in zip(axes[:2], (0, len(water) - 1), ("Initial mouth and first water passage", "Final mouth and last water passage")):
        bed = initial if index == 0 else final
        image = axis.imshow(bed[r0:r1, c0:c1], cmap="terrain", vmin=-10, vmax=3, extent=extent)
        x = (np.arange(c0, c1) - column) * spacing
        z = (np.arange(r0, r1) - row) * spacing
        final_ocean = initial_ocean & (final <= metadata["core"]["sea_level_m"])
        for values, color, style in ((initial_ocean, "black", "--"), (final_ocean, "red", "-")):
            local = values[r0:r1, c0:c1]
            if local.any() and not local.all():
                axis.contour(x, z, local.astype(float), levels=[.5], colors=color, linestyles=style, linewidths=1.2)
        edge_start, edge_end = offsets[index:index + 2]
        lines, widths = [], []
        supplied = metadata["forcing"][index]["water_volume_m3"]
        for edge, flux in zip(cells[edge_start:edge_end], volumes[edge_start:edge_end, 0]):
            fr, fc, tr, tc = edge
            node_water = water[index, fr, fc]
            if (flux >= .005 * supplied and flux >= .1 * node_water
                    and r0 <= fr < r1 and c0 <= fc < c1 and r0 <= tr < r1 and c0 <= tc < c1):
                lines.append(((float(fc - column) * spacing, float(fr - row) * spacing),
                              (float(tc - column) * spacing, float(tr - row) * spacing)))
                widths.append(.5 + 3 * float(flux / supplied))
        axis.add_collection(LineCollection(lines, colors="deepskyblue", linewidths=widths, alpha=.85))
        axis.plot(0, 0, "o", color="white", markeredgecolor="black", markersize=5)
        axis.set_title(title, fontsize=10)
        fig.colorbar(image, ax=axis, label="Bed elevation (m)", shrink=.8)
    image = axes[2].imshow((final - initial)[r0:r1, c0:c1], cmap="magma", extent=extent)
    axes[2].set_title("Mouth deposition; black initial / red final shore", fontsize=10)
    fig.colorbar(image, ax=axes[2], label="Bed rise (m)", shrink=.8)
    for axis in axes:
        axis.set_xlabel("x from inlet (m)")
        axis.set_ylabel("z from inlet (m)")
    fig.savefig(output, dpi=140)
    plt.close(fig)


def growth_metrics(result, boundary, forcing, cell_area_m2):
    records = result["intervals"]
    first_volume, last_volume = forcing[0].water_volume_m3, forcing[-1].water_volume_m3
    first = records[0]["water_throughput_m3"] / max(first_volume, 1e-300)
    last = records[-1]["water_throughput_m3"] / max(last_volume, 1e-300)
    flow_change = float(np.abs(last - first).sum())
    split_counts = []
    bed = result["initial_bed_m"].copy()
    blocked_steps = 0
    for record, supplied in zip(records, forcing):
        blocked_steps += int(bed[supplied.inlet_cell] > boundary.river_head_m)
        grouped = {}
        for edge in record["flow_edges"]:
            cell = tuple(edge["from_cell"])
            grouped.setdefault(cell, []).append(edge["water_volume_m3"])
        count = 0
        for cell, shares in grouped.items():
            throughput = float(record["water_throughput_m3"][cell])
            if (throughput >= .01 * supplied.water_volume_m3
                    and sum(share >= .1 * throughput for share in shares) >= 2):
                count += 1
        split_counts.append(count)
        bed += record["deposited_solid_m3"] / (
            (1. - result["metadata"]["config"]["porosity"])
            * cell_area_m2
        )
    retained_steps = sum(item["water_ledger"]["retained_m3"] > max(1e-7, supplied.water_volume_m3 * 1e-12)
                         for item, supplied in zip(records, forcing))
    persistent_export = all(abs(item["water_ledger"]["ocean_export_m3"] - supplied.water_volume_m3)
                            <= max(1e-7, supplied.water_volume_m3 * 1e-12)
                            for item, supplied in zip(records, forcing))
    deposited = float(result["deposited_solid_m3"].sum())
    same_forcing = all(item.water_volume_m3 == first_volume and item.sediment_solid_m3 == forcing[0].sediment_solid_m3
                       and item.inlet_cell == forcing[0].inlet_cell for item in forcing)
    metrics = {"all_intervals_export_supplied_water": persistent_export,
               "same_forcing_all_intervals": same_forcing,
               "normalized_water_spatial_l1_change": flow_change,
               "significant_split_cells_per_interval": split_counts,
               "significant_split_cell_count_last_interval": split_counts[-1],
               "maximum_significant_split_cell_count": max(split_counts),
               "split_threshold": "at least two receivers each >=10% node flow; node >=1% inlet flow",
               "inlet_above_head_interval_count": blocked_steps,
               "water_retained_interval_count": retained_steps,
               "inlet_initial_bed_m": float(result["initial_bed_m"][forcing[0].inlet_cell]),
               "inlet_final_bed_m": float(result["final_bed_m"][forcing[-1].inlet_cell]),
               "river_head_m": boundary.river_head_m,
               "initial_marine_deposited_solid_m3": float(result["deposited_solid_m3"][boundary.initial_ocean_mask].sum()),
               "initial_land_deposited_solid_m3": float(result["deposited_solid_m3"][~boundary.initial_ocean_mask].sum()),
               "deposited_solid_m3": deposited}
    from scipy.ndimage import label
    sea = boundary.sea_level_m
    initial_land = ~boundary.initial_ocean_mask & (result["initial_bed_m"] >= sea)
    emerged = boundary.initial_ocean_mask & (result["initial_bed_m"] < sea) & (result["final_bed_m"] > sea)
    final_land = initial_land | emerged
    components, _ = label(final_land, structure=np.ones((3, 3), int))
    mainland_ids = np.unique(components[initial_land])
    connected = emerged & np.isin(components, mainland_ids[mainland_ids > 0])
    metrics.update(new_land_cell_count=int(emerged.sum()), new_land_area_m2=float(emerged.sum() * cell_area_m2),
                   new_land_connected_to_initial_land_cell_count=int(connected.sum()),
                   new_land_connected_to_initial_land_area_m2=float(connected.sum() * cell_area_m2),
                   emerged_shape_passed=bool(connected.any()),
                   emerged_land_definition="initial registered ocean below sea datum raised strictly above sea datum",
                   raised_zero_datum_original_land_cell_count=int((~boundary.initial_ocean_mask
                       & (result["initial_bed_m"] == sea) & (result["final_bed_m"] > sea)).sum()),
                   significant_split_interpretation="flow allocation cells; these counts are not numbers of rivers")
    marine_depth = sea - result["initial_bed_m"][boundary.initial_ocean_mask]
    metrics["minimum_initial_ocean_depth_m"] = float(marine_depth.min()) if marine_depth.size else None
    metrics["maximum_cumulative_deposition_depth_m"] = len(forcing) * result["metadata"]["config"]["max_deposit_depth_per_interval_m"]
    metrics["passed"] = bool(persistent_export and same_forcing and deposited > 0.
                             and flow_change > 1e-6 and split_counts[-1] > 0)
    return metrics


def refresh_saved_report(directory):
    directory = Path(directory)
    path = directory / "delta.npz"
    report_path = directory / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    original_sha = file_sha256(path)
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        saved = {key: archive[key] for key in ("edge_offsets", "edge_cells", "edge_volumes", "water", "deposits")}
        records = []
        for index, ledger in enumerate(metadata["interval_ledgers"]):
            start, stop = saved["edge_offsets"][index:index + 2]
            cells, volumes = saved["edge_cells"][start:stop], saved["edge_volumes"][start:stop]
            edges = tuple({"from_cell": tuple(map(int, cell[:2])), "to_cell": tuple(map(int, cell[2:])),
                           "water_volume_m3": float(volume[0]), "sediment_solid_m3": float(volume[1])}
                          for cell, volume in zip(cells, volumes))
            records.append({"water_throughput_m3": saved["water"][index],
                            "deposited_solid_m3": saved["deposits"][index], "flow_edges": edges,
                            "water_ledger": ledger["water"], "solid_ledger": ledger["solid"]})
        result = {"metadata": metadata["core"], "initial_bed_m": archive["initial_bed_m"],
                  "final_bed_m": archive["final_bed_m"], "deposited_solid_m3": archive["deposited_solid_m3"],
                  "intervals": tuple(records)}
        boundary = FluvialDeltaBoundary(archive["ocean_mask"], archive["export_mask"], metadata["core"]["sea_level_m"],
                                       metadata["core"]["river_head_m"], metadata["core"]["boundary_source_id"])
    forcing = tuple(FluvialDeltaInterval(tuple(item["inlet_cell"]), item["water_volume_m3"], item["sediment_solid_m3"])
                    for item in metadata["forcing"])
    area = metadata["terrain"]["dx_m"] * metadata["terrain"]["dz_m"]
    report["useful_fluvial_growth"] = growth_metrics(result, boundary, forcing, area)
    report["metrics_version"] = "registered-ocean-emergence-v2"
    synthetic = directory / "SYNTHETIC-shallow-shelf"
    if synthetic.exists():
        child = refresh_saved_report(synthetic)
        report["controlled_synthetic_emergence"]["new_land_cell_count"] = child["useful_fluvial_growth"]["new_land_cell_count"]
        report["controlled_synthetic_emergence"]["emerged_shape_passed"] = child["useful_fluvial_growth"]["emerged_shape_passed"]
    render_mouth_zoom(path, directory / "mouth-zoom.png")
    if file_sha256(path) != original_sha:
        raise ValueError("refresh changed numerical archive")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def save_synthetic_emergence(output):
    output = Path(output)
    output.mkdir()
    bed = np.full((9, 13), .1, np.float64)
    bed[:, 4:] = -.5
    ocean = bed < 0.
    export = np.zeros(bed.shape, bool)
    export[:, -1] = True
    terrain = TerrainGrid(bed, np.ones(bed.shape, bool), 0., 0., 1., 1.,
                          "diagnostic_dem_proxy", "SYNTHETIC-controlled-shallow-shelf", "a" * 64)
    boundary = FluvialDeltaBoundary(ocean, export, 0., 2., "SYNTHETIC-declared-shallow-shelf")
    forcing = tuple(FluvialDeltaInterval((4, 0), 100., 1.5) for _ in range(32))
    result = simulate_fluvial_delta(terrain, boundary, forcing, FluvialDeltaConfig())
    provenance = {"path": "SYNTHETIC fixture; no TD source", "sha256": "a" * 64,
                  "interpretation": "controlled shallow shelf; mechanism demonstration, not actual TD evidence",
                  "natural_outlet_verified": False}
    path = output / "delta.npz"
    save_result(path, terrain, boundary, forcing, result, provenance, bed)
    report = {"source_kind": "SYNTHETIC", "source": provenance,
              "artifact_sha256": file_sha256(path), "cold_audit": audit_archive(path, verify_source=False),
              "useful_fluvial_growth": growth_metrics(result, boundary, forcing, terrain.cell_area_m2),
              "water_ledger": result["water_ledger"], "solid_ledger": result["solid_ledger"],
              "publishable": False}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render(path, output / "before-after.png")
    render_mouth_zoom(path, output / "mouth-zoom.png")
    return report


def run(output, sediment_per_interval_m3=5000., require_fluvial_growth=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    terrain, boundary, forcing, config, provenance, raw = source_input(sediment_per_interval_m3)
    declaration = {"source": provenance, "config": asdict(config), "forcing": [asdict(item) for item in forcing],
                   "sea_level_m": boundary.sea_level_m, "river_head_m": boundary.river_head_m,
                   "resource_policy": "2 CPU cores, BelowNormal, one numerical thread; no GPU or frontend"}
    (output / "declaration.json").write_text(json.dumps(declaration, indent=2), encoding="utf-8")
    result = simulate_fluvial_delta(terrain, boundary, forcing, config)
    result["metadata"]["cell_area_m2"] = terrain.cell_area_m2
    artifact = output / "delta.npz"
    save_result(artifact, terrain, boundary, forcing, result, provenance, raw)
    audit = audit_archive(artifact, file_sha256(artifact))
    report = {"schema": "finite-fluvial-delta-acceptance-v1", "cold_audit": audit,
              "budget_passed": audit["passed"], "useful_fluvial_growth": growth_metrics(result, boundary, forcing, terrain.cell_area_m2),
              "fluvial_growth_required": require_fluvial_growth,
              "artifact_sha256": file_sha256(artifact), "source": provenance,
              "water_ledger": result["water_ledger"], "solid_ledger": result["solid_ledger"],
              "routing_water_l1_change_m3": float(np.abs(result["intervals"][-1]["water_throughput_m3"] - result["intervals"][0]["water_throughput_m3"]).sum()),
              "hydraulics_verified": False, "naturalness_verified": False, "publishable": False}
    render(artifact, output / "before-after.png")
    render_locator(output / "source-window.png")
    render_mouth_zoom(artifact, output / "mouth-zoom.png")
    synthetic = save_synthetic_emergence(output / "SYNTHETIC-shallow-shelf")
    report["controlled_synthetic_emergence"] = {"path": "SYNTHETIC-shallow-shelf/report.json",
                                               "artifact_sha256": synthetic["artifact_sha256"],
                                               "new_land_cell_count": synthetic["useful_fluvial_growth"]["new_land_cell_count"],
                                               "emerged_shape_passed": synthetic["useful_fluvial_growth"]["emerged_shape_passed"]}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    if os.name == "nt":
        import ctypes
        handle = ctypes.c_void_p(-1)
        ctypes.windll.kernel32.SetProcessAffinityMask(handle, 3)
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x4000)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--sediment-per-interval-m3", type=float, default=5000.)
    parser.add_argument("--require-fluvial-growth", action="store_true")
    args = parser.parse_args()
    if args.audit:
        print(json.dumps(audit_archive(args.audit), indent=2))
    elif args.output:
        report = run(args.output, args.sediment_per_interval_m3, args.require_fluvial_growth)
        print(json.dumps(report, indent=2))
        if args.require_fluvial_growth and not report["useful_fluvial_growth"]["passed"]:
            sys.exit(2)
    else:
        parser.error("--output or --audit required")
