"""Plot a pinned saved native water snapshot, including wet cells absent from its mesh."""

import argparse
import io
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_native_water_surface import load_water_surface


MAX_BYTES = 1024 ** 3


def read_record(report_path, expected_report_sha256):
    if file_sha256(report_path) != expected_report_sha256:
        raise ValueError("water report external SHA mismatch")
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if report.get("schema") != "td-native-water-surface-prototype-v1":
        raise ValueError("water report schema mismatch")
    source_pin, surface_pin, obj_pin = (report[name] for name in ("source_page", "surface", "obj"))
    for pin in (source_pin, surface_pin, obj_pin):
        if file_sha256(pin["path"]) != pin["expected_sha256"]:
            raise ValueError("water source file pin mismatch")
    surface = load_water_surface(**surface_pin)
    metadata = surface["metadata"]
    if (metadata != report["metadata"] or metadata["source_page_sha256"] != source_pin["expected_sha256"] or
            metadata["source_page_identity"] != source_pin["expected_identity"] or
            report["vertex_count"] != len(surface["arrays"]["vertex_cell_ids"]) or
            report["triangle_count"] != len(surface["arrays"]["triangles"])):
        raise ValueError("water report/source identity mismatch")
    if file_sha256(report_path) != expected_report_sha256:
        raise ValueError("water report changed while reading")
    return report, surface


def plot(report_path, expected_report_sha256, output_directory):
    output = Path(output_directory)
    if output.exists():
        raise FileExistsError(output)
    report, surface = read_record(report_path, expected_report_sha256)
    metadata, arrays = surface["metadata"], surface["arrays"]
    rows, columns = metadata["grid_shape"]
    if rows * columns > 250000 or sum(value.nbytes for value in arrays.values()) > MAX_BYTES // 4:
        raise ValueError("water plot memory budget exceeded")
    depth = np.full(rows * columns, np.nan)
    depth[arrays["cell_ids"]] = arrays["hour_end_depth_m"]
    depth = depth.reshape(rows, columns)
    threshold = metadata["wet_threshold_m"]
    wet = np.isfinite(depth) & (depth >= threshold)
    drawn = np.zeros(rows * columns, bool)
    drawn[arrays["vertex_cell_ids"]] = True
    drawn = drawn.reshape(rows, columns)
    omitted = wet & ~drawn
    spacing = metadata["spacing_m"]
    grid_volume = float(np.sum(arrays["hour_end_depth_m"], dtype=np.float64) * spacing ** 2)
    missing_volume = float(np.sum(depth[omitted], dtype=np.float64) * spacing ** 2)
    if (int(wet.sum()) != metadata["wet_cell_count"] or int(omitted.sum()) != metadata["undrawn_wet_cell_count"] or
            grid_volume != metadata["grid_water_volume_m3"] or missing_volume != metadata["undrawn_wet_grid_volume_m3"]):
        raise ValueError("water plot grid volume/count mismatch")
    figure = plt.figure(figsize=(19, 7), constrained_layout=True)
    depth_axis = figure.add_subplot(131)
    positive = depth[np.isfinite(depth) & (depth > 0)]
    if len(positive):
        image = depth_axis.imshow(np.ma.masked_invalid(np.where(depth > 0, depth, np.nan)), origin="upper",
                                  cmap="Blues", norm=LogNorm(vmin=max(float(positive.min()), 1e-7),
                                                            vmax=max(float(positive.max()), 1e-6)))
        figure.colorbar(image, ax=depth_axis, label="hour-end depth (m), log", shrink=.65)
    depth_axis.set(title="All native valid-cell depths", xlabel="native X cell (30 m)", ylabel="native Z cell (30 m)")
    coverage_axis = figure.add_subplot(132)
    omitted_z, omitted_x = np.nonzero(omitted)
    drawn_z, drawn_x = np.nonzero(wet & drawn)
    coverage_axis.scatter(omitted_x, omitted_z, s=5, c="#dc643b", label=f"wet, not in triangles: {len(omitted_x)}")
    coverage_axis.scatter(drawn_x, drawn_z, s=7, c="#2369aa", label=f"triangle vertices: {len(drawn_x)}")
    coverage_axis.set(xlim=(-1, columns), ylim=(rows, -1), aspect="equal", xlabel="native X cell (30 m)",
                      ylabel="native Z cell (30 m)", title="Wet-cell display coverage")
    coverage_axis.legend(loc="lower right", fontsize=8)
    spatial = figure.add_subplot(133, projection="3d")
    wet_ids = np.flatnonzero(wet.ravel())
    cell_ids = arrays["cell_ids"]
    positions = np.searchsorted(cell_ids, wet_ids)
    bed = arrays["native_bed_m"][positions]
    water_y = bed + depth.ravel()[wet_ids]
    origin = metadata["origin_m_xz"]
    scatter_x = origin[0] + wet_ids % columns * spacing
    scatter_z = origin[1] + wet_ids // columns * spacing
    spatial.scatter(scatter_x, scatter_z, water_y, s=2, c="#e19142", alpha=.7,
                    label=f"all {len(wet_ids)} native wet cells")
    vertices = arrays["vertices_xyz_m"]
    triangles = arrays["triangles"]
    if len(triangles):
        spatial.plot_trisurf(vertices[:, 0], vertices[:, 2], vertices[:, 1], triangles=triangles,
                             color="#4789b3", alpha=.65, linewidth=.1)
    spatial.set(xlabel="world X (m)", ylabel="world Z (m)", zlabel="bed + depth (m)",
                title=f"Saved triangles: {len(triangles)}; wet points: {len(wet_ids)}")
    spatial.legend(loc="upper right", fontsize=8)
    figure.suptitle(f"Native 30 m | single saved hour | {threshold * 1000:g} mm display threshold | "
                    f"all-grid {grid_volume:,.1f} m3; not in triangles {missing_volume:,.1f} m3\n"
                    "Grid volume is sum(depth x cell area), not mesh volume. No derived fine-bed water or time-series claim.")
    image_bytes = io.BytesIO()
    figure.savefig(image_bytes, format="png", dpi=150)
    plt.close(figure)
    if image_bytes.tell() > MAX_BYTES:
        raise ValueError("water plot output byte budget exceeded")
    for pin in (report["source_page"], report["surface"], report["obj"]):
        if file_sha256(pin["path"]) != pin["expected_sha256"]:
            raise ValueError("water source changed while plotting")
    if file_sha256(report_path) != expected_report_sha256:
        raise ValueError("water report changed while plotting")
    output.mkdir(parents=True)
    image_path = output / "native-water-coverage.png"
    publish_bytes(image_path, image_bytes.getvalue())
    result = dict(schema="td-native-water-coverage-figure-v1",
                  source_report=dict(path=str(Path(report_path).resolve()), expected_sha256=expected_report_sha256),
                  source_page=report["source_page"], surface=report["surface"], obj=report["obj"],
                  figure=dict(path=str(image_path.resolve()), expected_sha256=file_sha256(image_path)),
                  wet_cell_count=int(wet.sum()), triangle_vertex_count=int(drawn.sum()),
                  undrawn_wet_cell_count=int(omitted.sum()), triangles=int(len(triangles)),
                  grid_water_volume_m3=grid_volume, undrawn_wet_grid_volume_m3=missing_volume,
                  spacing_m=spacing, wet_threshold_m=threshold,
                  scope="saved native 30m single-hour diagnostic; visual threshold only; no derived fine water or full time-series",
                  volume_semantics="all valid cell depth times native cell area; not mesh volume",
                  plotted_from_saved_snapshot=True, solver_run=False)
    publish_bytes(output / "report.json", json.dumps(result, indent=2, ensure_ascii=False,
                                                      allow_nan=False).encode("utf-8"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(plot(args.report, args.report_sha256, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
