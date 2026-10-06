"""Plot saved visual path candidates without bed carving or water interpolation."""

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
from tools.audit_td_candidate_coupling import read_record


def plot(report_path, expected_sha256):
    report_path = Path(report_path).resolve(strict=True)
    if file_sha256(report_path) != expected_sha256:
        raise ValueError("visual path report pin mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    paths, metadata = read_record(report["paths"])
    geometry, geometry_metadata = read_record(report["geometry"])
    selected = paths["chain_edge_indices"]
    source_positions = np.searchsorted(geometry["node_cell_ids"], geometry["edge_cell_ids"][selected])
    native_lines = geometry["node_world_xyz_m"][source_positions].copy()
    native_lines[:, :, 1] = geometry["node_native_bed_m"][source_positions]
    origin = np.min(paths["points_xyz_m"][:, [0, 2]], axis=0)
    local_points = paths["points_xyz_m"].copy()
    local_points[:, 0] -= origin[0]
    local_points[:, 2] -= origin[1]
    native_lines[:, :, 0] -= origin[0]
    native_lines[:, :, 2] -= origin[1]
    chains = [local_points[first:last] for first, last in zip(paths["point_offsets"][:-1], paths["point_offsets"][1:])]
    colors = ["#df6929" if accepted else "#467ba7" for accepted in paths["chain_accepted"]]
    figure = plt.figure(figsize=(14, 6), constrained_layout=True)
    planar = figure.add_subplot(121)
    planar.add_collection(LineCollection(native_lines[:, :, [0, 2]], colors="#bbbbbb", linewidths=2.5))
    planar.add_collection(LineCollection([chain[:, [0, 2]] for chain in chains], colors=colors, linewidths=1.2))
    planar.autoscale()
    planar.invert_yaxis()
    planar.set_aspect("equal")
    planar.set(title="Grey: original D4 | orange: constrained curves | blue: fallback", xlabel="local X (m)", ylabel="local Z (m)")
    spatial = figure.add_subplot(122, projection="3d")
    segments = np.concatenate([np.stack((chain[:-1], chain[1:]), axis=1) for chain in chains])
    segment_colors = [color for color, chain in zip(colors, chains) for index in range(len(chain) - 1)]
    spatial.add_collection3d(Line3DCollection(segments[:, :, [0, 2, 1]], colors=segment_colors, linewidths=1.1))
    spatial.auto_scale_xyz(local_points[:, 0], local_points[:, 2], local_points[:, 1])
    spatial.set(title="Native bed heights sampled along visual paths; no new bed", xlabel="local X (m)", ylabel="local Z (m)", zlabel="elevation (m)")
    figure.suptitle(f"Diagnostic visual paths | {len(selected)} saved active links | {metadata['accepted_curved_chains']} curved chains | {metadata['fallback_chains']} fallback | no solved water")
    destination = ROOT / "verification/td-native-channel-valley-paths" / ("independent-figure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / "visual-paths.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    if file_sha256(report_path) != expected_sha256:
        raise ValueError("path report changed during plot")
    result = dict(report_record=dict(path=str(report_path), expected_sha256=expected_sha256),
        image_record=dict(path=str(path), expected_sha256=file_sha256(path)), water_generated=False,
        omitted_edges=metadata["omitted_active_edges"], source_scope="single diagnostic saved hour; visual paths only")
    publish_bytes(destination / "report.json", json.dumps(result, indent=2).encode("utf-8"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(plot(args.report, args.report_sha256)))


if __name__ == "__main__":
    main()
