"""Plot saved candidate centerlines and sections beside actual native water samples."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_native_channel_geometry import load_channel_geometry


def plot(geometry_record, max_edges=800):
    if type(max_edges) is not int or not 1 <= max_edges <= 5000:
        raise ValueError("bounded plot selection requires 1..5000 edges")
    saved = load_channel_geometry(**geometry_record)
    arrays, metadata = saved["arrays"], saved["metadata"]
    indices = np.searchsorted(arrays["node_cell_ids"], arrays["edge_cell_ids"])
    q_mean = arrays["node_receiver_interval_mean_q_m3_s"][indices[:, 0]]
    wet_edges = np.flatnonzero(q_mean > 0.)
    ordered = wet_edges[np.argsort(-q_mean[wet_edges], kind="stable")]
    chosen = ordered[:max_edges]
    if chosen.size == 0:
        raise ValueError("saved hour has no positive receiver integral to plot")
    nodes = np.unique(indices[chosen])
    origin = np.asarray(metadata["origin_m_xz"])
    centerline = arrays["edge_centerline_xyz_m"][chosen].copy()
    centerline[:, :, 0] = (centerline[:, :, 0] - origin[0]) / 1000.
    centerline[:, :, 2] = (centerline[:, :, 2] - origin[1]) / 1000.
    sections = arrays["edge_sections_xyz_m"][chosen].copy().reshape(-1, 2, 3, 3)
    sections[:, :, :, 0] = (sections[:, :, :, 0] - origin[0]) / 1000.
    sections[:, :, :, 2] = (sections[:, :, :, 2] - origin[1]) / 1000.
    world = arrays["node_world_xyz_m"][nodes]
    local_x = (world[:, 0] - origin[0]) / 1000.
    local_z = (world[:, 2] - origin[1]) / 1000.
    colors = np.log10(1. + q_mean[chosen])
    figure = plt.figure(figsize=(16, 7), constrained_layout=True)
    planar = figure.add_subplot(121)
    lines = LineCollection(centerline[:, :, [0, 2]], cmap="viridis", linewidths=.9)
    lines.set_array(colors)
    planar.add_collection(lines)
    planar.autoscale()
    planar.set_aspect("equal")
    planar.invert_yaxis()
    planar.set(title="Actual receiver interval volume selects candidate links", xlabel="local X (km)", ylabel="local Z (km)")
    figure.colorbar(lines, ax=planar, label="log10(1 + interval mean Q in m3/s)", shrink=.7)
    spatial = figure.add_subplot(122, projection="3d")
    curves = Line3DCollection(centerline[:, :, [0, 2, 1]], cmap="viridis", linewidths=.8)
    curves.set_array(colors)
    spatial.add_collection3d(curves)
    section_lines = sections[::max(1, len(sections) // 100)].reshape(-1, 3, 3)
    spatial.add_collection3d(Line3DCollection(section_lines[:, :, [0, 2, 1]], colors="#a76536", linewidths=.35, alpha=.5))
    spatial.scatter(local_x, local_z, arrays["node_native_bed_m"][nodes], s=2, color="#999999", alpha=.3, label="native bed samples")
    wet = arrays["node_hour_end_water_depth_m"][nodes] > 1e-9
    spatial.scatter(local_x[wet], local_z[wet], arrays["node_hour_end_surface_sample_m"][nodes][wet], s=3, color="#2494d4", alpha=.5, label="actual water surface samples")
    spatial.auto_scale_xyz(local_x, local_z, world[:, 1])
    spatial.set(title="Candidate bed/sections; actual water shown only as points", xlabel="local X (km)", ylabel="local Z (km)", zlabel="elevation (m)")
    spatial.legend(loc="upper left", fontsize=8)
    figure.suptitle(f"TD saved hour {metadata['start_s']/3600:g} to {metadata['end_s']/3600:g} | Diagnostic 3D morphology candidate | {len(chosen)} selected links")
    directory = ROOT / "verification/td-native-channel-geometry" / ("independent-figure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "native-channel-candidate.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    if file_sha256(geometry_record["path"]) != geometry_record["expected_sha256"]:
        raise ValueError("geometry changed during plotting")
    report = dict(schema="td-native-channel-geometry-figure-v1", geometry_record=geometry_record,
                  image_sha256=file_sha256(path), selected_edges=int(len(chosen)), total_receiver_edges=int(len(indices)),
                  positive_volume_edges=int(len(wet_edges)), omitted_edges=int(len(indices)-len(chosen)),
                  selection="largest actual hourly receiver integrals; stable ties; no network completion",
                  sections="edge-oriented schematic cross sections; shared centerlines are not a joined surface mesh",
                  water_surface="actual native hour-end points only, no interpolated surface",
                  solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                  plotter_sha256=file_sha256(__file__))
    publish_bytes(directory / "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-identity", required=True)
    parser.add_argument("--max-edges", type=int, default=800)
    args = parser.parse_args()
    print(plot(dict(path=str(args.geometry.resolve()), expected_sha256=args.expected_sha256,
                    expected_identity=args.expected_identity), max_edges=args.max_edges))
