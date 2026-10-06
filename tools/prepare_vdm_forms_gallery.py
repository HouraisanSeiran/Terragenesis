"""Publish six metric cliff forms on the same pinned TD bed for comparison."""

import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.prepare_td_channel_vdm import prepare


FORMS = {
    "layered_ledge": "层状岩棚",
    "undercut_alcove": "凹蚀岩厦",
    "fluted_wall": "纵向槽脊",
    "stepped_wall": "阶梯崖壁",
    "curved_escarpment": "弯曲崖带",
    "massive_overhang": "厚顶悬挑",
}


def _publish_json(path, document):
    publish_bytes(path, json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def _parameter_section(reference, vertices, center, along, outward, along_m, depth_m):
    basis = np.stack((reference[0, 1, [0, 2]] - reference[0, 0, [0, 2]],
                      reference[1, 0, [0, 2]] - reference[0, 0, [0, 2]]), axis=1)
    rows, columns = np.indices(reference.shape[:2])
    expected = reference[0, 0, [0, 2]] + np.stack((columns, rows), axis=-1) @ basis.T
    if not np.allclose(reference[..., [0, 2]], expected, rtol=0, atol=1e-7):
        raise ValueError("gallery sections require a regular affine reference chart")
    step = min(np.linalg.norm(basis[:, 0]), np.linalg.norm(basis[:, 1])) / 2
    across = np.linspace(-depth_m, depth_m, max(3, int(np.ceil(2 * depth_m / step)) + 1))
    positions = center + along_m * along + across[:, None] * outward
    indices = (positions - reference[0, 0, [0, 2]]) @ np.linalg.inv(basis).T
    if (np.any(indices < -1e-7) or
            np.any(indices > np.array([reference.shape[1] - 1, reference.shape[0] - 1]) + 1e-7)):
        raise ValueError("requested section outside reference chart")
    indices = np.clip(indices, 0, [reference.shape[1] - 1, reference.shape[0] - 1])
    lower = np.minimum(np.floor(indices).astype(int), [reference.shape[1] - 2, reference.shape[0] - 2])
    column, row = lower.T
    fraction_column, fraction_row = (indices - lower).T
    sampled = []
    for field in (reference, vertices.reshape(reference.shape)):
        points = ((1 - fraction_column)[:, None] * (1 - fraction_row)[:, None] * field[row, column] +
                  fraction_column[:, None] * (1 - fraction_row)[:, None] * field[row, column + 1] +
                  (1 - fraction_column)[:, None] * fraction_row[:, None] * field[row + 1, column] +
                  fraction_column[:, None] * fraction_row[:, None] * field[row + 1, column + 1])
        sampled.append(points)
    return sampled


def plot_gallery(output, records, recipe):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    figure = plt.figure(figsize=(16, 12), layout="constrained")
    sections, section_axes = plt.subplots(2, 3, figsize=(15, 9), layout="constrained")
    center = np.asarray(recipe["center_xz_m"], float)
    for number, record in enumerate(records):
        effective_recipe = record.get("effective_recipe", recipe)
        outward = np.asarray(effective_recipe["outward_xz"], float)
        outward /= np.linalg.norm(outward)
        along = np.array([outward[1], -outward[0]])
        with np.load(record["vdm"]["path"], allow_pickle=False) as archive:
            reference = archive["reference_xyz_m"]
            vertices = archive["vertices_xyz_m"]
            triangles = archive["triangles"]
        offset = reference[..., [0, 2]] - center
        chart_along, chart_outward = offset @ along, offset @ outward
        nearest = np.unravel_index(np.sum(offset ** 2, axis=-1).argmin(), offset.shape[:2])
        height_origin = float(reference[nearest][1])
        selected = ((np.abs(chart_along) <= recipe["half_length_m"] + 2) &
                    (np.abs(chart_outward) <= recipe["half_depth_m"] + 2)).ravel()
        faces = triangles[np.all(selected[triangles], axis=1)]
        points = vertices[faces].copy()
        points -= [center[0], height_origin, center[1]]
        normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        normals /= np.linalg.norm(normals, axis=1)[:, None]
        light = np.array([.4, .8, -.5])
        light /= np.linalg.norm(light)
        shade = .35 + .65 * np.abs(normals @ light)
        colors = np.clip(shade[:, None] * np.array([.77, .66, .49]), 0, 1)
        axis = figure.add_subplot(2, 3, number + 1, projection="3d")
        axis.add_collection3d(Poly3DCollection(points[:, :, [0, 2, 1]], facecolors=colors,
                                               edgecolors="#685b48", linewidths=.16))
        horizontal = max(recipe["half_depth_m"], recipe["half_length_m"]) + 2
        vertical = max(recipe["height_m"] * .8, float(np.max(np.abs(points[..., 1]))) * 1.05)
        axis.set(xlim=(-horizontal, horizontal), ylim=(-horizontal, horizontal),
                 zlim=(-vertical, vertical), title=record["label"],
                 xlabel="东向偏移 m", ylabel="南向偏移 m", zlabel="高程偏移 m")
        axis.set_box_aspect((horizontal * 2, horizontal * 2, vertical * 2))
        axis.tick_params(labelsize=7, pad=0)
        axis.set_zlabel("")
        axis.view_init(23, -65)
        section_axis = section_axes.ravel()[number]
        section_extent = max(0, recipe["half_length_m"] - recipe["end_fade_m"])
        for along_m, color in ((-section_extent, "#6990a9"), (0, "#ad542e"), (section_extent, "#479474")):
            base, shaped = _parameter_section(reference, vertices, center, along, outward,
                                              along_m, recipe["half_depth_m"] + 1)
            section_axis.plot((shaped[:, [0, 2]] - center) @ outward, shaped[:, 1] - height_origin,
                              ".-", ms=2, lw=1, color=color, label=f"沿崖 {along_m:+g}m")
            if along_m == 0:
                section_axis.plot((base[:, [0, 2]] - center) @ outward, base[:, 1] - height_origin,
                                  "--", color="#444444", lw=1, label="原床")
        section_axis.set(title=record["label"], xlabel="崖外方向 m", ylabel="高程偏移 m")
        section_axis.set_aspect("equal", adjustable="datalim")
        section_axis.grid(alpha=.2)
        section_axis.legend(fontsize=7)
    figure.suptitle("同一 TD 河床上的米制 VDM 对照 · 几何候选，未作稳定性/自交认证", fontsize=14)
    sections.suptitle("随岩壁走向的 XYZ 参数曲线 · 网格双线性取样，保留折返", fontsize=14)
    figure.savefig(output / "forms.png", dpi=150)
    sections.savefig(output / "sections.png", dpi=150)
    plt.close(figure)
    plt.close(sections)


def build_gallery(configuration, configuration_sha256, output, *, amplitude_m=1.5, wavelength_m=6., seed=20261003,
                  surface_curvature_m=0.0, end_elevation_difference_m=0.0,
                  extension_direction_degrees=None, geometry_controls_comparison=False):
    configuration = Path(configuration).resolve(strict=True)
    if file_sha256(configuration) != configuration_sha256:
        raise ValueError("gallery configuration SHA mismatch")
    config = json.loads(configuration.read_text(encoding="utf-8"))
    if set(config) != {"surface", "hierarchy", "recipe"}:
        raise ValueError("gallery requires one base configuration without form")
    common = dict(amplitude_m=amplitude_m, wavelength_m=wavelength_m, seed=seed)
    if geometry_controls_comparison:
        if surface_curvature_m <= 0 or end_elevation_difference_m <= 0 or extension_direction_degrees is None:
            raise ValueError("controls comparison requires positive curvature/drop magnitudes and explicit direction")
        baseline = dict(kind="fluted_wall", **common)
        variants = [
            ("baseline", "原始走向 · 无新增曲率或高差", baseline),
            ("convex", f"外凸 {surface_curvature_m:g} m", dict(baseline, surface_curvature_m=surface_curvature_m)),
            ("concave", f"内凹 {surface_curvature_m:g} m", dict(baseline, surface_curvature_m=-surface_curvature_m)),
            ("rising", f"正向端高差 +{end_elevation_difference_m:g} m", dict(baseline, end_elevation_difference_m=end_elevation_difference_m)),
            ("falling", f"正向端高差 -{end_elevation_difference_m:g} m", dict(baseline, end_elevation_difference_m=-end_elevation_difference_m)),
            ("direction", f"延伸方位 {extension_direction_degrees:g}°", dict(baseline, extension_direction_degrees=extension_direction_degrees)),
        ]
    else:
        variants = [(kind, label, dict(kind=kind, **common, surface_curvature_m=surface_curvature_m,
                                       end_elevation_difference_m=end_elevation_difference_m,
                                       extension_direction_degrees=extension_direction_degrees))
                    for kind, label in FORMS.items()]
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    records = []
    for kind, label, form in variants:
        variant = {**config, "form": form}
        variant_path = output / (kind + ".json")
        _publish_json(variant_path, variant)
        report = prepare(variant_path, file_sha256(variant_path), output / kind)
        with np.load(report["vdm"]["path"], allow_pickle=False) as archive:
            displacement_hash = hashlib.sha256(archive["displacement_xyz_m"].tobytes()).hexdigest()
        records.append(dict(kind=kind, label=label, vdm=report["vdm"],
                            effective_recipe=report["effective_recipe"], form=report["form"],
                            displacement_sha256=displacement_hash,
                            report=dict(path=str(output / kind / "report.json"), expected_sha256=file_sha256(output / kind / "report.json")),
                            changed_vertices=report["changed_vertices"],
                            downward_facing_triangles=report["downward_facing_triangles"],
                            protected_vertices=report["protected_vertices"]))
        print(kind + " exported", flush=True)
    if len({record["displacement_sha256"] for record in records}) != len(variants):
        raise ValueError("different form names produced duplicate displacement geometry")
    plot_gallery(output, records, config["recipe"])
    if file_sha256(configuration) != configuration_sha256:
        raise ValueError("gallery source configuration changed")
    report = dict(schema="metric-vdm-forms-gallery-v1", configuration=dict(path=str(configuration), expected_sha256=configuration_sha256),
                  variants=records, geometry_controls_comparison=geometry_controls_comparison,
                  water_generated=False, source_unchanged=True, hydraulic_ready=False,
                  natural_outlet_verified=False, self_intersection_verified=False, stability_verified=False,
                  artifacts={name: file_sha256(output / name) for name in ("forms.png", "sections.png")})
    labels = "\n".join(f'<li><a href="{record["kind"]}/derived.obj">{record["label"]} OBJ</a> · '
                       f'<a href="{record["kind"]}/review.json">三维审查数据</a></li>' for record in records)
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>VDM岩壁形态对照</title>'
            '<style>body{max-width:1400px;margin:32px auto;padding:0 20px;font:16px system-ui;background:#faf8f3;color:#302d27}'
            'img{width:100%;height:auto}li{margin:10px}</style><h1>VDM 岩壁形态对照</h1>'
            '<p>同一 TD 河床、相同位置和尺度。下图为 XYZ 网格与沿有效走向取样的参数曲线（双线性插值，并非实体平面切割）；每种形态均另存。</p>'
            '<p>当前为地貌启发的几何候选；未完成稳定性、自交及新床面水力认证。</p>'
            '<img src="forms.png" alt="六种岩壁三维对照"><img src="sections.png" alt="六种岩壁真实XYZ截面对照">'
            '<ul>' + labels + '</ul></html>')
    publish_bytes(output / "review.html", page.encode("utf-8"))
    report["artifacts"]["review.html"] = file_sha256(output / "review.html")
    _publish_json(output / "gallery.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/metric-vdm-forms" / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ"))
    parser.add_argument("--amplitude-m", type=float, default=1.5)
    parser.add_argument("--wavelength-m", type=float, default=6.)
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--surface-curvature-m", type=float, default=0.0)
    parser.add_argument("--end-elevation-difference-m", type=float, default=0.0)
    parser.add_argument("--extension-direction-degrees", type=float, default=None)
    parser.add_argument("--geometry-controls-comparison", action="store_true")
    args = parser.parse_args()
    build_gallery(args.configuration, args.configuration_sha256, args.output,
                  amplitude_m=args.amplitude_m, wavelength_m=args.wavelength_m, seed=args.seed,
                  surface_curvature_m=args.surface_curvature_m,
                  end_elevation_difference_m=args.end_elevation_difference_m,
                  extension_direction_degrees=args.extension_direction_degrees,
                  geometry_controls_comparison=args.geometry_controls_comparison)
    print(str(args.output / "gallery.json"))
