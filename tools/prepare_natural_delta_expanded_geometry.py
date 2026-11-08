"""Geometry only: enlarge a completed natural bed without hydraulic restart."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates


def run(parent, annual, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    summary = json.loads((parent / "summary.json").read_text(encoding="utf-8"))
    original = json.loads((annual / "summary.json").read_text(encoding="utf-8"))
    source_info = original["terrain_initialization"]
    scene = Path(source_info["source_scene"])
    assert digest(scene) == source_info["source_sha256"]
    with np.load(parent / "result.npz") as saved:
        old = {key: saved[key] for key in saved.files}
    with np.load(scene) as saved:
        metadata = json.loads(str(saved["metadata_json"]))
        source_base = saved["base_bed_m"]
    dx = summary["config"]["dx_m"]
    assert dx == 5. and old["bed_m"].shape[1:] == (160, 120)
    extension = 60
    shape = (220, 240)
    offset = (60, 60)
    across = old["local_world_xz_m"][0, 1] - old["local_world_xz_m"][0, 0]
    along = old["local_world_xz_m"][1, 0] - old["local_world_xz_m"][0, 0]
    rows, cols = np.indices(shape)
    world = old["local_world_xz_m"][0, 0] + (rows - extension)[..., None] * along + (cols - extension)[..., None] * across
    inside = (slice(offset[0], offset[0] + 160), slice(offset[1], offset[1] + 120))
    # Preserve saved coordinates in the overlap as well as bed and inventory.
    world[inside] = old["local_world_xz_m"]
    cells = (world - np.asarray(metadata["origin_xz_m"])) / float(metadata["spacing_m"])
    if (cells.min() < 0. or cells[..., 0].max() > source_base.shape[1] - 1 or cells[..., 1].max() > source_base.shape[0] - 1):
        raise ValueError("expanded domain leaves original source support")
    base = map_coordinates(source_base, [cells[..., 1], cells[..., 0]], order=1)
    embedded = np.zeros(shape, bool)
    embedded[inside] = True
    bed = base.copy()
    bed[inside] = old["bed_m"][-1]
    floor = base - .3
    floor[inside] = old["source_floor_m"]
    packing = 1. - summary["config"]["porosity"]
    inventory = (bed - floor) * dx ** 2 * packing
    np.testing.assert_array_equal(bed[inside], old["bed_m"][-1])
    np.testing.assert_array_equal(floor[inside], old["source_floor_m"])
    np.testing.assert_array_equal(world[inside], old["local_world_xz_m"])
    old_edge = np.zeros(shape, bool)
    old_edge[60, 60:180] = True
    old_edge[219, 60:180] = True
    old_edge[60:220, 60] = True
    old_edge[60:220, 179] = True
    affected = np.zeros(shape, bool)
    old_change = old["bed_m"][-1].astype(float) - old["initial_bed_m"]
    rr, cc = np.indices((160, 120))
    old_distance = np.minimum.reduce([rr, cc, 159 - rr, 119 - cc]) * dx
    affected[inside] = (old_distance < 25.) & (abs(old_change) > .01)
    seams = {"upstream": bed[60, 60:180] - bed[59, 60:180],
        "left": bed[60:220, 60] - bed[60:220, 59], "right": bed[60:220, 179] - bed[60:220, 180]}
    seam_stats = {name: {"maximum_abs_jump_m": float(abs(values).max()), "mean_abs_jump_m": float(abs(values).mean()),
        "p95_abs_jump_m": float(np.percentile(abs(values), 95)), "count_over_0_1m": int(np.sum(abs(values) > .1)),
        "signed_old_minus_new_jump_m": values.tolist()} for name, values in seams.items()}
    new_land = (base >= 0.) & ~embedded
    land_rows = np.flatnonzero((bed >= 0.).any(axis=1))
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output / "geometry.npz", bed_m=bed, source_base_bed_m=base, source_floor_m=floor,
        initial_erodible_solid_m3=inventory, local_world_xz_m=world, embedded_old_domain_mask=embedded,
        newly_sampled_mask=~embedded, old_outer_edge_mask=old_edge, old_boundary_affected_25m_mask=affected,
        old_domain_cell_type=old["cell_type"], old_domain_initial_bed_m=old["initial_bed_m"],
        seam_upstream_old_minus_new_m=seams["upstream"], seam_left_old_minus_new_m=seams["left"], seam_right_old_minus_new_m=seams["right"])
    report = {"status": "prepared-only-not-runnable", "schema": "expanded-natural-geometry-preparation-v1",
        "parent_result": str(parent / "result.npz"), "parent_sha256": digest(parent / "result.npz"),
        "source_scene": str(scene), "source_scene_sha256": digest(scene), "source_field": "base_bed_m",
        "source_role": "continuous frozen macro + 0.35 TD residual; no constructed scene bed imported",
        "shape": list(shape), "spacing_m": dx, "cross_stream_by_downstream_extent_m": [1200., 1100.],
        "station_center_range_relative_to_mouth_m": [-360., 735.], "cross_stream_center_range_m": [-600., 595.],
        "old_domain_offset_row_column": list(offset), "old_domain_shape": [160, 120],
        "old_final_bed_floor_coordinates_exactly_embedded": True, "no_smoothing_or_seam_repair": True,
        "new_cell_count": int((~embedded).sum()), "new_cell_cover_m": .3, "porosity": 1. - packing,
        "new_cell_erodible_inventory_solid_m3": float(inventory[~embedded].sum()),
        "new_inventory_role": "declared local 0.3m substrate cover in added spatial domain; not extra upstream sediment supply and not yet consumed",
        "old_embedded_inventory_solid_m3": float(inventory[embedded].sum()),
        "new_base_above_zero_area_m2": float(new_land.sum() * dx ** 2),
        "total_geometry_above_zero_area_m2": float(np.sum(bed >= 0.) * dx ** 2),
        "land_row_center_station_range_m": [float(land_rows[0] * dx - 360.), float(land_rows[-1] * dx - 360.)],
        "old_boundary_affected_cells_within25m_over1cm": int(affected.sum()), "seam_jumps": seam_stats,
        "old_downstream_boundary": "unchanged domain downstream end, not a new interior seam",
        "pending": ["incoming channel geometry and vertical datum handoff unresolved; no old saved river elevations automatically imported",
            "new-region hydraulic state and overlap water/momentum handoff unresolved; no water/stage/momentum generated",
            "new computational cell types and inlet boundary unresolved; L0 not extended and old cell types retained only as local provenance",
            "source floor/inventory at future outer boundaries requires explicit solver boundary policy",
            "old domain-boundary-shaped bed may persist inside overlap; no reconstruction of missing beyond-edge deposition",
            "larger shape is not a native checkpoint restart; old consumed sediment cannot be redelivered"],
        "new_supply_delivered_solid_m3": 0., "simulations_started": 0}
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    extent = [-602.5, 597.5, 737.5, -362.5]
    xx, zz = np.meshgrid(np.arange(240) * dx - 600., np.arange(220) * dx - 360.)
    fig, axes = plt.subplots(1, 3, figsize=(16, 7), constrained_layout=True)
    for ax, field, title, cmap in zip(axes, [base, bed, bed - base],
            ["Expanded same-source macro + TD residual", "Exact old final bed embedded; untreated seams", "Embedded final bed minus sampled base"],
            ["terrain", "terrain", "RdBu_r"]):
        limit = max(float(abs(bed - base).max()), .01)
        options = {"vmin": -1.5, "vmax": 5.} if cmap == "terrain" else {"vmin": -limit, "vmax": limit}
        image = ax.imshow(field, extent=extent, cmap=cmap, **options)
        ax.plot([-302.5, 297.5, 297.5, -302.5, -302.5], [-62.5, -62.5, 737.5, 737.5, -62.5], color="#bd2052", linewidth=1.)
        contour_bed = bed if cmap == "RdBu_r" else field
        if contour_bed.min() < 0. < contour_bed.max():
            ax.contour(xx, zz, contour_bed, levels=[0.], colors="black", linewidths=.5)
        if ax is axes[1] and affected.any():
            ax.contour(xx, zz, affected.astype(float), levels=[.5], colors="#f7ba24", linewidths=.7)
        ax.set_title(title)
        ax.set_xlabel("Cross-stream (m)")
        ax.set_ylabel("Station from mouth (m)")
        fig.colorbar(image, ax=ax, shrink=.7, label="m")
    fig.suptitle("Geometry preparation only: 1200 x 1100 m at 5 m; no channel connection or hydraulic restart\n"
        "Pink = old domain; yellow = >1 cm changed cells in its former 25 m boundary strip", fontsize=11)
    fig.savefig(output / "expanded-geometry.png", dpi=170)
    plt.close(fig)
    return {key: value for key, value in report.items() if key != "seam_jumps"} | {"seam_maximum_abs_jumps_m": {name: item["maximum_abs_jump_m"] for name, item in seam_stats.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--annual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.parent, args.annual, args.output), indent=2))
