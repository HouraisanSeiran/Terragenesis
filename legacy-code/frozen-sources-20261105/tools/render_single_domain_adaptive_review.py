"""Render fixed saved AMR inventory maps and an actual junction fan patch."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(name, "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest
from terrain_pipeline.surface_adaptive_water import load_consumer_adaptive_frame


def render(manifest_path, manifest_sha256, output):
    started = time.monotonic()
    context = load_consumer_manifest(manifest_path, expected_sha256=manifest_sha256)
    saved = load_consumer_adaptive_frame(context, scenario="tailwater-rise-root4", frame_index=4)
    baseline = load_consumer_adaptive_frame(context, scenario="tailwater-baseline-root4", frame_index=4)
    a, geometry = saved["frame"]["arrays"], saved["geometry"]["arrays"]
    snapshot = saved["snapshot"]["arrays"]
    depth = snapshot["canonical_depth_m"]
    spacing = geometry["leaf_spacing_m"][geometry["canonical_owner"]]
    response = depth-baseline["snapshot"]["arrays"]["canonical_depth_m"]
    origin = saved["bed"]["metadata"]["origin_m_xz"]
    extent = [0, depth.shape[1], depth.shape[0], 0]
    fig = plt.figure(figsize=(13, 10), layout="constrained")
    for number, field, title, cmap, norm in (
            (1, depth, "Saved canonical water depth at 120 s", "Blues", None),
            (2, spacing, "Actual leaf spacing at 120 s", ListedColormap(["#459b6c", "#e6b851", "#8c91a1"]), BoundaryNorm([.5, 1.5, 3, 5], 3)),
            (3, response, "Controlled tailwater depth response", "RdBu_r", None)):
        axis = fig.add_subplot(2, 2, number)
        image = axis.imshow(field, extent=extent, cmap=cmap, norm=norm)
        axis.set(title=title, xlabel="East offset (m)", ylabel="South offset (m)")
        bar = fig.colorbar(image, ax=axis, shrink=.8)
        bar.set_label("m")
        if number==2:
            bar.set_ticks([1, 2, 4])
    axis = fig.add_subplot(2, 2, 4, projection="3d")
    rows, columns = np.indices(depth.shape)
    selected = (rows>=96)&(rows<144)&(columns>=96)&(columns<144)
    ids = np.flatnonzero(selected.ravel())
    bed_triangles = a["bed_triangles"].reshape(-1, 4, 3)[ids].reshape(-1, 3)
    wet_selected = selected.ravel()[a["wet_cell_ids"]]
    water_triangles = a["water_triangles"].reshape(-1, 4, 3)[wet_selected].reshape(-1, 3)

    def points(vertices, triangles):
        result = vertices[triangles][:, :, [0, 2, 1]].copy()
        result[:, :, 0] -= origin[0]
        result[:, :, 1] -= origin[1]
        return result

    bed_points = points(a["bed_vertices_xyz_m"], bed_triangles)
    water_points = points(a["water_vertices_xyz_m"], water_triangles)
    axis.add_collection3d(Poly3DCollection(bed_points, facecolor="#8b9786", linewidth=0, alpha=1.))
    axis.add_collection3d(Poly3DCollection(water_points, facecolor="#28a7bd", linewidth=0, alpha=.78))
    ymin = float(bed_points[:, :, 2].min())
    ymax = max(float(bed_points[:, :, 2].max()), float(water_points[:, :, 2].max(initial=ymin)))
    axis.set(xlim=(96, 144), ylim=(96, 144), zlim=(ymin, ymax),
        xlabel="East offset (m)", ylabel="South offset (m)", zlabel="Elevation (m)",
        title="Saved junction fan mesh, 48 m patch (6x vertical)")
    axis.set_box_aspect((48, 48, 6*max(ymax-ymin, .1)))
    axis.view_init(elev=33, azim=-58)
    fig.suptitle("Finite TD window: independent AMR leaf inventory and conservative display", fontsize=14)
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    png = output/"saved-adaptive-review.png"
    fig.savefig(png, dpi=130)
    plt.close(fig)
    memory = psutil.Process().memory_info()
    resource = dict(elapsed_s=time.monotonic()-started,
        peak_rss_bytes=int(getattr(memory, "peak_wset", memory.rss)),
        peak_private_bytes=int(getattr(memory, "peak_pagefile", memory.vms)))
    if resource["elapsed_s"]>1800 or max(resource["peak_rss_bytes"], resource["peak_private_bytes"])>1073741824:
        raise RuntimeError("saved review resource budget exceeded")
    if any(name=="numba" or name.startswith("numba.") or name=="terrain_pipeline.surface_adaptive_execution" for name in sys.modules):
        raise RuntimeError("saved review imported solver")
    report = dict(schema="single-domain-adaptive-saved-review-v1", source_manifest=dict(
        path=str(Path(manifest_path).resolve()), expected_sha256=manifest_sha256),
        png=dict(path=str(png), expected_sha256=file_sha256(png)), solver_advanced=False,
        frame_identity=saved["frame"]["identity_sha256"], snapshot_identity=saved["snapshot"]["identity_sha256"],
        geometry_identity=saved["geometry"]["identity_sha256"], full_window_maps=True,
        actual_patch_bed_triangles=len(bed_triangles), actual_patch_water_triangles=len(water_triangles),
        patch_canonical_bounds=[96,144,96,144], vertical_display_exaggeration=6.,
        resource=resource, natural_outlet_verified=False, hydraulic_ready=False, publishable=False,
        rendering_code_sha256=file_sha256(Path(__file__)))
    target = output/"report.json"
    publish_bytes(target, (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n").encode("utf-8"))
    print(dict(path=str(target), expected_sha256=file_sha256(target)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    render(args.manifest, args.manifest_sha256, args.output)
