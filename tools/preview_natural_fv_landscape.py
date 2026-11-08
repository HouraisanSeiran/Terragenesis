"""Render actual FV growth in the unconstructed scene15 base; no simulation."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256
from tools.inspect_natural_fv_growth import read_arrays
from tools.render_delta_mouth_16km import terrain_rgb

SCENE = ROOT / ".scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-15/scene.npz"


def frame(arrays):
    world = arrays["local_world_xz_m"]
    origin = world[0, 0]
    cross = (world[0, 1] - origin) / 5.
    downstream = (world[1, 0] - origin) / 5.
    np.testing.assert_allclose(np.column_stack((cross, downstream)).T @ np.column_stack((cross, downstream)), np.eye(2), atol=1.e-10)
    return origin, cross, downstream


def render(run, scene_path, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.transforms import Affine2D
    from matplotlib.lines import Line2D
    a = read_arrays(run / "result.npz")
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    with np.load(scene_path) as saved:
        base = saved["base_bed_m"].copy()
        meta = json.loads(str(saved["metadata_json"]))
    origin, cross, downstream = frame(a)
    bed, h = a["bed_m"][-1], a["depth_m"][-1]
    wet = h > 2.e-6
    concentration = np.divide(a["suspended_solid_m3"][-1], h * 25., out=np.zeros_like(h), where=wet)
    rgb = terrain_rgb(bed, wet, 5., water_depth=h)
    sediment_fraction = np.clip(concentration / max(float(concentration.max()), 1.e-12), 0., 1.) * .65
    rgb = rgb * (1. - sediment_fraction[..., None]) + np.array([.71, .68, .43]) * sediment_fraction[..., None]
    nr, nc = h.shape
    local_extent = [-2.5, (nc - .5) * 5., (nr - .5) * 5., -2.5]
    world = a["local_world_xz_m"]
    boundary = np.vstack((world[0], world[1:, -1], world[-1, -2::-1], world[-2::-1, 0], world[:1, 0]))
    scene_origin = np.asarray(meta["origin_xz_m"])
    spacing = float(meta["spacing_m"])
    r, c = np.indices(base.shape)
    bg_world = scene_origin + np.stack((c, r), axis=-1) * spacing
    displacement = bg_world - origin
    local_c = displacement @ cross / 5.
    local_r = displacement @ downstream / 5.
    inside = (local_c >= -.5) & (local_c <= nc - .5) & (local_r >= -.5) & (local_r <= nr - .5)
    composite = base.copy()
    composite[inside] = map_coordinates(bed, [local_r[inside], local_c[inside]], order=1, mode="nearest")
    local_source_coords = (world - scene_origin) / spacing
    source_crop = map_coordinates(base, [local_source_coords[..., 1], local_source_coords[..., 0]], order=1)
    edge = np.zeros(h.shape, bool)
    edge[[0, -1]] = True
    edge[:, [0, -1]] = True
    seam = bed[edge] - source_crop[edge]
    output.mkdir(parents=True, exist_ok=False)
    scene_extent = [scene_origin[0] - spacing / 2., scene_origin[0] + (base.shape[1] - .5) * spacing,
        scene_origin[1] + (base.shape[0] - .5) * spacing, scene_origin[1] - spacing / 2.]
    affine = Affine2D.from_values(cross[0], cross[1], downstream[0], downstream[1], origin[0], origin[1])
    fig, ax = plt.subplots(figsize=(13, 12), constrained_layout=True)
    ax.imshow(terrain_rgb(composite, composite < 0., spacing), extent=np.asarray(scene_extent) / 1000., interpolation="nearest")
    rgba = np.dstack((rgb, np.ones(h.shape)))
    ax.imshow(rgba, extent=local_extent, transform=affine + Affine2D().scale(.001) + ax.transData, interpolation="nearest", zorder=3)
    ax.plot(boundary[:, 0] / 1000., boundary[:, 1] / 1000., color="#e35b50", linewidth=1.3, linestyle="--", zorder=4)
    center = world.mean(axis=(0, 1)) / 1000.
    ax.annotate("Actual 1.2 x 1.1 km FV footprint\nDashed edge: unblended preview seam", xy=center,
        xytext=center + [1.8, -2.5], arrowprops={"arrowstyle": "->", "color": "#7e2424"},
        bbox={"facecolor": "white", "alpha": .9, "edgecolor": "none"}, zorder=5)
    ax.set(xlim=np.asarray(scene_extent[:2]) / 1000., ylim=np.asarray(scene_extent[2:]) / 1000.,
        xlabel="World X (km)", ylabel="World Z (km)", title="16 km source terrain | actual FV growth location", aspect="equal")
    fig.text(.5, .012, "Background: scene15 base_bed_m (macro + 0.35 TD residual), no designed fan. Background water is sea-level context; only footprint has simulated water.", ha="center", fontsize=9)
    fig.get_layout_engine().set(rect=(0., .045, 1., .955))
    fig.savefig(output / "terrain-context-16km.png", dpi=190)
    plt.close(fig)

    x = np.arange(nc) * 5. - 600.
    station = np.arange(nr) * 5. - 360.
    extent = [x[0] - 2.5, x[-1] + 2.5, station[-1] + 2.5, station[0] - 2.5]
    fig, ax = plt.subplots(figsize=(13, 12), constrained_layout=True)
    ax.imshow(rgb, extent=extent, interpolation="nearest")
    if wet.any() and not wet.all():
        ax.contour(x, station, h, levels=[2.e-6], colors="white", linewidths=.9)
    if np.any(h > .01) and np.any(h < .01):
        ax.contour(x, station, h, levels=[.01], colors="#c4edf7", linewidths=.7, linestyles="dotted")
    momentum = a["momentum_m2_s"][-1].reshape(nr, nc, 2)
    speed = np.divide(np.linalg.norm(momentum, axis=2), h, out=np.zeros_like(h), where=h > .01)
    rr, cc = np.indices((nr, nc))
    selected = (rr % 10 == 5) & (cc % 10 == 5) & (speed > .08) & (h > .01)
    direction = np.divide(momentum, np.linalg.norm(momentum, axis=2)[..., None], out=np.zeros_like(momentum),
        where=np.linalg.norm(momentum, axis=2)[..., None] > 0.)
    ax.quiver(x[cc[selected]], station[rr[selected]], direction[..., 0][selected], direction[..., 1][selected],
        angles="xy", scale_units="xy", scale=.035, color="#f7fbfd", width=.0022, alpha=.85)
    ax.axhline(0., color="#343a36", linewidth=.7, linestyle="--")
    ax.set(xlabel="Cross stream (m)", ylabel="Station from mouth (m)", aspect="equal",
        title=f"Actual FV bed and water | elapsed {a['time_s'][-1] - a['time_s'][0]:.0f} s")
    ax.legend(handles=[Line2D([], [], color="white", label="Actual dry/wet shore: depth 2e-6 m"),
        Line2D([], [], color="#c4edf7", linestyle=":", label="1 cm thin-water edge"),
        Line2D([], [], marker=">", color="#f7fbfd", label="Actual FV direction (normalized arrows)"),
        Line2D([], [], color="#b5ad6e", linewidth=5, label="Water tint: actual suspended concentration")],
        loc="lower left", facecolor="#405e60", labelcolor="white", framealpha=.92, fontsize=9)
    fig.text(.5, .012, "Natural colors are an elevation/shade visualization, not imagery. Water follows actual depth; sediment tint is concentration, not new land. No fan or branch is drawn.", ha="center", fontsize=9)
    fig.get_layout_engine().set(rect=(0., .045, 1., .955))
    fig.savefig(output / "actual-local-landscape.png", dpi=190)
    plt.close(fig)
    report = {"schema": "actual-fv-landscape-preview-v1", "run": str(run), "result_sha256": file_sha256(run / "result.npz"),
        "scene": str(scene_path), "scene_sha256": file_sha256(scene_path), "background_field": "base_bed_m",
        "preview_only": True, "unblended_boundary_bed_minus_source_min_max_m": [float(seam.min()), float(seam.max())],
        "local_bed_min_max_m": [float(bed.min()), float(bed.max())], "final_peak_concentration": float(concentration.max()),
        "physical_time_s": float(a["time_s"][-1]), "remaining_source_solid_m3": summary["remaining_finite_source_solid_m3"],
        "mapping": {"origin_xz_m": origin.tolist(), "cross_unit_xz": cross.tolist(), "downstream_unit_xz": downstream.tolist()},
        "scope": "actual saved final local bed replaces original base crop in preview only; no smoothing, no simulation outside local footprint"}
    (output / "preview.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    np.savez_compressed(output / "preview-composite.npz", preview_bed_m=composite, local_footprint_mask=inside,
        origin_xz_m=scene_origin, spacing_m=spacing)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--scene", type=Path, default=SCENE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.run, args.scene, args.output), indent=2))
