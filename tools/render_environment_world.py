"""同坐标联合产品的叠图 driver：真实接入 terrain_map_style，原生 30 m，不插值。

图上坐标轴是**真实的 30 m 世界米**（不是像素索引）；高程的色带与晕渲、比例尺均调
``terrain_map_style`` 的公开接口。只读产品，不生成、不推进、不重算任何字段。

用法
----
    python -B tools/render_environment_world.py --product <dir> --output <png>
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from terrain_pipeline import terrain_map_style as style  # noqa: E402
from terrain_pipeline.soil_water import COVER_CLASSES  # noqa: E402
from terrain_pipeline.environment_product import world_load as load  # noqa: E402


ARRAYS = "environment-world-arrays.npz"
RECORD = "environment-world.json"
#: The water field name in ``FIELD_SPECS``. It is soil+fast+slow, NOT soil alone.
WATER_TOTAL_FIELD = "water_state_total_mm"


def _side(product):
    cells = product.cells
    side = int(round(np.sqrt(cells)))
    if side * side != cells:
        raise ValueError("%d 个点不是方形网格，本 renderer 只画方形窗口" % (cells,))
    return side


def _grid(product, name):
    side = _side(product)
    if name not in product.arrays:
        raise ValueError("产品中没有字段 %r；可用字段：%s"
                         % (name, ", ".join(sorted(product.arrays))))
    return np.asarray(product.arrays[name], np.float64).reshape(side, side)


def _world_km(product):
    """世界坐标转 km，并且是成形的 ``[side, side]`` 数组。

    图轴一律用 **km**：``terrain_map_style.draw_scale_bar`` 把 ``length_km`` 直接加到
    轴坐标上（实读 L210），所以轴必须是 km，否则比例尺会差 1000 倍。
    """
    side = _side(product)
    x = np.asarray(product.record["x_m"], np.float64).reshape(side, side) / 1000.0
    z = np.asarray(product.record["z_m"], np.float64).reshape(side, side) / 1000.0
    return x, z


def _extent_km(product):
    """``imshow`` 的 extent，单位 km（格心 = 原点 + i*spacing，边框扩半格）。"""
    spacing_km = float(product.record["spacing_m"]) / 1000.0
    x, z = _world_km(product)
    return [float(x.min()) - spacing_km / 2.0, float(x.max()) + spacing_km / 2.0,
            float(z.max()) + spacing_km / 2.0, float(z.min()) - spacing_km / 2.0]


def _decorate(axis, product, *, with_scale_bar=True):
    """真实世界坐标轴（km）+ ``terrain_map_style`` 比例尺（同一单位）。"""
    x, z = _world_km(product)
    axis.set_xlabel("x (km, 30 m reference nodes)", fontsize=7)
    axis.set_ylabel("z (km)", fontsize=7)
    axis.set_xticks([float(x.min()), float(x.max())])
    axis.set_yticks([float(z.min()), float(z.max())])
    axis.tick_params(labelsize=6)
    if with_scale_bar:
        span_km = max(float(x.max() - x.min()), float(z.max() - z.min()))
        if span_km > 0.0:
            # 轴是 km，``draw_scale_bar`` 的 ``length_km`` 就是同一单位：不再换算。
            style.draw_scale_bar(axis, style.nice_scale_length_km(span_km))


def _panel(axis, data, title, unit, *, cmap="viridis", product=None,
           scale=1.0, fixed_format=None):
    """One continuous panel. ``scale`` converts the data into the plotted unit.

    The colorbar never uses Matplotlib's automatic offset text: an offset like
    ``1e-11+9.89e-3`` sits on top of the panel title and hides the real magnitude. With
    ``scale`` and ``fixed_format`` the absolute value is printed directly instead.
    """
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        axis.text(0.5, 0.5, "no finite values (pending)", ha="center", va="center",
                  transform=axis.transAxes, fontsize=9)
        axis.set_title(title, fontsize=10)
        return
    scaled = data * scale
    image = axis.imshow(scaled, cmap=cmap, origin="upper", extent=_extent_km(product))
    low, high = float(np.min(scaled)), float(np.max(scaled))
    axis.set_title("%s [%s]\nrange %.6g .. %.6g" % (title, unit, low, high),
                   fontsize=9)
    bar = plt.colorbar(image, ax=axis, fraction=0.046, pad=0.02,
                       format=fixed_format or "%.4g")
    bar.ax.tick_params(labelsize=6)
    # No offset handling here: passing ``format=`` makes Matplotlib use a
    # FormatStrFormatter, which prints the whole number and never adds offset text.
    _decorate(axis, product)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--product", required=True)
    parser.add_argument("--output", required=True, help="输出 PNG 路径（必须不存在）")
    arguments = parser.parse_args(argv)

    if os.path.exists(arguments.output):
        print(json.dumps({"ok": False, "reason": "输出已存在"}, ensure_ascii=False))
        return 2

    product = load(os.path.join(arguments.product, ARRAYS),
                   os.path.join(arguments.product, RECORD))
    side = _side(product)
    spacing = float(product.record["spacing_m"])

    figure, axes = plt.subplots(2, 3, figsize=(16, 9))

    # --- 高程：真实 terrain_map_style 色带 + 晕渲 ---------------------------------
    # ``continuous_relief_rgb`` 内部**已经**调用了 ``apply_hillshade``（实读 L136），
    # 所以这里不再重复叠一次，否则会双重变暗。
    elevation = _grid(product, "elevation_m")
    if np.isfinite(elevation).all() and float(np.ptp(elevation)) > 0.0:
        limits = (float(elevation.min()), float(elevation.max()))
        shaded = style.continuous_relief_rgb(elevation, spacing, limits)
        axes[0, 0].imshow(shaded, origin="upper", extent=_extent_km(product))
        axes[0, 0].set_title("elevation (styled relief + shading) [m]", fontsize=10)
        _decorate(axes[0, 0], product)
    else:
        _panel(axes[0, 0], elevation, "elevation", "m", product=product)

    _panel(axes[0, 1], _grid(product, WATER_TOTAL_FIELD),
           "water total (soil+fast+slow)", "\u00b5m", cmap="Blues", product=product,
           scale=1000.0, fixed_format="%.4g")
    _panel(axes[0, 2], _grid(product, "soil_thickness_bulk_m"),
           "soil thickness (bulk)", "mm", cmap="YlOrBr", product=product,
           scale=1000.0, fixed_format="%.4g")

    # --- 地表覆盖：类别色表与归一都显式声明，不用连续 tab10 --------------------
    # ``tab10`` is a continuous colormap: sampling it at six positions produces ten
    # interpolated bands, so the bar shows colours that no cell actually has. A
    # ListedColormap + BoundaryNorm maps exactly one colour to each declared class, and
    # the same mapping is used for the overlay.
    from matplotlib.colors import BoundaryNorm, ListedColormap
    class_count = len(COVER_CLASSES)
    base = plt.get_cmap("tab10")
    cover_cmap = ListedColormap([base(i) for i in range(class_count)],
                                name="land-cover-class")
    cover_norm = BoundaryNorm(np.arange(-0.5, class_count + 0.5, 1.0), class_count)

    cover = _grid(product, "land_cover_index")
    cover_axis = axes[1, 0]
    if np.isfinite(cover).all():
        image = cover_axis.imshow(cover, cmap=cover_cmap, norm=cover_norm,
                                  origin="upper", extent=_extent_km(product))
        cover_axis.set_title("land cover (class)", fontsize=10)
        bar = plt.colorbar(image, ax=cover_axis, fraction=0.046, pad=0.02,
                           ticks=range(class_count), spacing="uniform")
        bar.ax.set_yticklabels(COVER_CLASSES, fontsize=6)
        bar.ax.tick_params(length=0)
        _decorate(cover_axis, product)
    else:
        cover_axis.text(0.5, 0.5, "cover pending", ha="center", va="center",
                        transform=cover_axis.transAxes, fontsize=9)
        cover_axis.set_title("land cover (class)", fontsize=10)

    _panel(axes[1, 1], _grid(product, "suitability"), "suitability", "1",
           cmap="magma", product=product, fixed_format="%.3f")

    # --- 叠合：覆盖为底，土层厚等高线（世界米坐标） ---------------------------
    overlay = axes[1, 2]
    if np.isfinite(cover).all():
        overlay.imshow(cover, cmap=cover_cmap, norm=cover_norm, origin="upper",
                       alpha=0.75, extent=_extent_km(product))
    thickness = _grid(product, "soil_thickness_bulk_m")
    if np.isfinite(thickness).all() and float(np.ptp(thickness)) > 0.0:
        x_km, z_km = _world_km(product)
        overlay.contour(x_km, z_km, thickness, colors="k", linewidths=0.6)
    overlay.set_title("overlay: cover + thickness contours", fontsize=10)
    _decorate(overlay, product)

    figure.suptitle(
        "environment world product, %dx%d native 30 m, world coordinates (km) | "
        "world=%s\npending: %s | not_available: %s"
        % (side, side, product.world_identity[:16],
           ", ".join(product.count_status("pending")) or "none",
           ", ".join(product.count_status("not_available")) or "none"),
        fontsize=9)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    os.makedirs(os.path.dirname(os.path.abspath(arguments.output)), exist_ok=True)
    figure.savefig(arguments.output, dpi=120)
    plt.close(figure)

    print(json.dumps({
        "ok": True,
        "png": os.path.relpath(arguments.output, ROOT).replace(os.sep, "/"),
        "side": side,
        "world_identity": product.world_identity,
        "computed": product.count_status("computed"),
        "pending": product.count_status("pending"),
        "not_available": product.count_status("not_available"),
        "water_field_used": WATER_TOTAL_FIELD,
        "water_plotted_unit": "um (data_mm * 1000); the stored field stays mm",
        "cover_classes": list(COVER_CLASSES),
        "cover_mapping": "ListedColormap + BoundaryNorm, one colour per declared class",
        "style_functions_used": ["continuous_relief_rgb (includes apply_hillshade)",
                                  "nice_scale_length_km", "draw_scale_bar"],
        "note": ("原生 30 m 格直接成像；坐标轴为世界坐标 km；量值不上 offset 伪造；"
                 "pending 字段明确标出"),
    }, ensure_ascii=False, indent=1, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
