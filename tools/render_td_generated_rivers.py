"""Render all saved native TD river domains and actual bed meshes, read-only."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import LightSource, Normalize
from matplotlib.lines import Line2D
import matplotlib.tri as mtri
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import load_component_geometry


STATUS_COLORS = {"accepted": "#168072", "rejected": "#ba493d"}


def read_npz(path, expected_sha256):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError(f"Saved artifact hash mismatch: {path}")
    with np.load(path, allow_pickle=False) as archive:
        keys = ("source_height_m", "receiver", "outlet_kind", "terminal_owner", "selected_edge_source_ids",
                "selected_edge_target_ids", "selected_edge_status", "baseline_selected_edge_source_ids",
                "baseline_selected_edge_target_ids")
        return {key: archive[key] for key in keys}


def load_sample(path, include_mesh=True):
    report = json.loads((path / "report.json").read_text(encoding="utf-8"))
    network_record = report["network"]
    arrays = read_npz(path / network_record["path"], network_record["sha256"])
    global_record = report.get("global_bed")
    records = [global_record] if global_record else []
    if report.get("accepted_edges", 0) and not global_record:
        raise ValueError("Accepted edges require a pinned final global bed")
    paths = [path / record["path"] for record in records]
    meshes = [load_component_geometry(item, expected_sha256=record["sha256"],
              expected_identity=record["identity_sha256"])["arrays"] for item, record in zip(paths, records)] if include_mesh else []
    for mesh in meshes:
        actual_cut = mesh["source_elevation_m"] - mesh["bed_elevation_m"]
        if not np.allclose(actual_cut, mesh["cut_depth_m"], atol=1e-8, rtol=0):
            raise ValueError("Saved mesh incision does not equal source minus bed")
    return {"name": path.name, "path": path, "report": report, "arrays": arrays,
            "meshes": meshes, "inputs": [path / "report.json", path / network_record["path"], *paths]}


def coordinates(sample):
    metadata = sample["report"]["terrain_metadata"]
    height = sample["arrays"]["source_height_m"]
    x = np.arange(height.shape[1]) * metadata["dx_m"] / 1000
    z = np.arange(height.shape[0]) * metadata["dz_m"] / 1000
    return x, z, np.array([metadata["x0_m"], metadata["z0_m"]])


def terrain(axis, sample, norm, shaded=False):
    x, z, _ = coordinates(sample)
    height = sample["arrays"]["source_height_m"]
    extent = [x[0] - (x[1] - x[0]) / 2, x[-1] + (x[1] - x[0]) / 2,
              z[-1] + (z[1] - z[0]) / 2, z[0] - (z[1] - z[0]) / 2]
    if shaded:
        metadata = sample["report"]["terrain_metadata"]
        shade = LightSource(315, 45).hillshade(height, dx=metadata["dx_m"], dy=metadata["dz_m"])
        axis.imshow(shade, cmap="gray", extent=extent, vmin=-.2, vmax=1.2)
    else:
        axis.imshow(height, cmap="gist_earth", norm=norm, extent=extent)
    axis.set(xlim=(x[0], x[-1]), ylim=(z[-1], z[0]), xlabel="Local X east (km)", ylabel="Local Z south (km)")
    axis.set_aspect("equal")


def network(axis, sample, baseline=False):
    arrays = sample["arrays"]
    x, z, _ = coordinates(sample)
    cols = len(x)
    prefix = "baseline_" if baseline else ""
    sources = arrays[prefix + "selected_edge_source_ids"]
    targets = arrays[prefix + "selected_edge_target_ids"]
    segments = np.stack((np.column_stack((x[sources % cols], z[sources // cols])),
                         np.column_stack((x[targets % cols], z[targets // cols]))), axis=1)
    if baseline:
        axis.add_collection(LineCollection(segments, colors="#264d6d", linewidths=.5, alpha=.9))
        return {"baseline_edges": len(sources)}
    statuses = arrays["selected_edge_status"].astype(str)
    accepted_mask = np.char.startswith(statuses, "accepted")
    if accepted_mask.any():
        _, _, origin = coordinates(sample)
        positions = sample.get("accepted_positions")
        if positions is None:
            mesh = sample["meshes"][0]
            nodes = (mesh["node_xz_m"] - origin) / 1000
            positions = dict(zip(mesh["source_node_cell_ids"].tolist(), nodes))
        segments[accepted_mask] = np.array([[positions[int(source)], positions[int(target)]]
                                  for source, target in zip(sources[accepted_mask], targets[accepted_mask])])
    for status in np.unique(statuses):
        accepted = status == "accepted" or status.startswith("accepted")
        pending = "pending" in status
        axis.add_collection(LineCollection(segments[statuses == status],
                            colors="#777777" if pending else STATUS_COLORS["accepted" if accepted else "rejected"],
                            linewidths=.55 if accepted else .4, alpha=.85 if accepted else .7))
    kinds = arrays["outlet_kind"].reshape(-1).astype(str)
    receiver = arrays["receiver"].reshape(-1)
    terminals = np.flatnonzero(receiver < 0)
    selected_terminals = np.unique(arrays["terminal_owner"].reshape(-1)[sources])
    for kind in np.unique(kinds[terminals]):
        ids = terminals[kinds[terminals] == kind]
        internal = "internal" in kind or "sink" in kind or "depression" in kind or kind == "lake_preserved"
        axis.scatter(x[ids % cols], z[ids // cols], s=3, marker="x" if internal else "s",
                     color="#9b2c75" if internal else "#262626", linewidths=.35, alpha=.3, zorder=3)
        selected_ids = np.intersect1d(ids, selected_terminals)
        axis.scatter(x[selected_ids % cols], z[selected_ids // cols], s=25, marker="x" if internal else "s",
                     color="#9b2c75" if internal else "#262626", linewidths=.9, zorder=5)
    return {str(key): int(np.count_nonzero(statuses == key)) for key in np.unique(statuses)}


def intersecting_triangles(mesh, origin, window):
    triangles = mesh["triangles"]
    vertices = (mesh["vertices_xz_m"] - origin) / 1000
    low = vertices[triangles[:, 0]].copy()
    high = low.copy()
    for column in (1, 2):
        points = vertices[triangles[:, column]]
        np.minimum(low, points, out=low)
        np.maximum(high, points, out=high)
    visible = (high[:, 0] >= window[0]) & (low[:, 0] <= window[1]) & (high[:, 1] >= window[2]) & (low[:, 1] <= window[3])
    return vertices, triangles[visible]


def transect(mesh, origin, xx, z_value):
    zz = np.full_like(xx, z_value) if np.ndim(z_value) == 0 else np.asarray(z_value)
    vertices, triangles = intersecting_triangles(mesh, origin, [xx.min(), xx.max(), zz.min(), zz.max()])
    if not len(triangles):
        return None
    ids, remapped = np.unique(triangles, return_inverse=True)
    local = vertices[ids]
    tri = mtri.Triangulation(local[:, 0], local[:, 1], remapped.reshape(-1, 3))
    return (mtri.LinearTriInterpolator(tri, mesh["source_elevation_m"][ids])(xx, zz),
            mtri.LinearTriInterpolator(tri, mesh["bed_elevation_m"][ids])(xx, zz))


def mesh_layer(axis, sample, key, norm, palette, window=None):
    _, _, origin = coordinates(sample)
    for mesh in sample["meshes"]:
        vertices = (mesh["vertices_xz_m"] - origin) / 1000
        triangles = mesh["triangles"]
        if window is None:
            x, z, _ = coordinates(sample)
            size = 1024
            raster = sample.get("mesh_raster")
            if raster is None:
                centers = (vertices[triangles[:, 0]] + vertices[triangles[:, 1]] + vertices[triangles[:, 2]]) / 3
                cols = np.clip((centers[:, 0] / x[-1] * size).astype(int), 0, size - 1)
                rows = np.clip((centers[:, 1] / z[-1] * size).astype(int), 0, size - 1)
                pixel_ids = rows * size + cols
                a = vertices[triangles[:, 1]] - vertices[triangles[:, 0]]
                b = vertices[triangles[:, 2]] - vertices[triangles[:, 0]]
                area = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) / 2
                weights = np.bincount(pixel_ids, weights=area, minlength=size * size)
                raster = {"pixel_ids": pixel_ids, "area": area, "weights": weights}
                sample["mesh_raster"] = raster
            values = mesh[key][triangles].mean(axis=1)
            averaged = np.bincount(raster["pixel_ids"], weights=values * raster["area"], minlength=size * size)
            np.divide(averaged, raster["weights"], out=averaged, where=raster["weights"] > 0)
            image = plt.get_cmap(palette)(norm(averaged.reshape(size, size)))
            image[:, :, 3] = np.clip(raster["weights"].reshape(size, size) / (x[-1] * z[-1] / size ** 2), 0, 1)
            axis.imshow(image, extent=[0, x[-1], z[-1], 0], interpolation="nearest")
            continue
        vertices, triangles = intersecting_triangles(mesh, origin, window)
        values = mesh[key][triangles].mean(axis=1)
        collection = PolyCollection(vertices[triangles], array=values, cmap=palette,
                                    norm=norm, edgecolors="none", rasterized=True)
        axis.add_collection(collection)


def cross_sections(axis, sample):
    x, z, origin = coordinates(sample)
    height = sample["arrays"]["source_height_m"]
    section_report = []
    figure = axis.figure
    grid = axis.get_subplotspec().subgridspec(3, 1, hspace=.5)
    axis.remove()
    for index, fraction in enumerate((.25, .5, .75)):
        axis = figure.add_subplot(grid[index])
        row = round((len(z) - 1) * fraction)
        axis.plot(x, height[row], color="#555555", linewidth=.65)
        sampled = 0
        max_cut = 0.
        for mesh in sample["meshes"]:
            vertices = (mesh["vertices_xz_m"] - origin) / 1000
            if not len(vertices) or not (vertices[:, 1].min() <= z[row] <= vertices[:, 1].max()):
                continue
            # Use a dense metric transect so narrow subcell mesh strips remain visible.
            xx = np.linspace(x[0], x[-1], 20001)
            section = transect(mesh, origin, xx, z[row])
            if section is None:
                continue
            source, bed = section
            valid = ~np.ma.getmaskarray(bed)
            if valid.any():
                axis.plot(xx, source, color="#d0871c", linewidth=1.1)
                axis.plot(xx, bed, color="#168072", linewidth=1.1)
                sampled += int(valid.sum())
                max_cut = max(max_cut, float(np.max((source - bed)[valid])))
        axis.set(xlabel="Local X east (km)" if index == 2 else "", ylabel="Elevation (m)",
                 title=f"Fixed section Z={fraction:.0%} ({z[row]:.2f} km)")
        axis.set_title(axis.get_title(), fontsize=9)
        axis.tick_params(labelsize=8)
        axis.grid(alpha=.2)
        section_report.append({"fraction_z": fraction, "row": row, "z_km": float(z[row]),
                               "mesh_samples": sampled, "max_sampled_mesh_cut_m": max_cut})
    return section_report


def colorbar(figure, axis, norm, palette, label):
    figure.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=palette), ax=axis, shrink=.75, label=label)


def render_mesh_detail(sample, output, cut_norm):
    if not sample["meshes"]:
        return {"available": False, "reason": "No accepted saved mesh"}
    x, z, origin = coordinates(sample)
    domain_center = np.array([x[-1], z[-1]]) / 2
    mesh = sample["meshes"][0]
    nodes = (mesh["node_xz_m"] - origin) / 1000
    edges = np.flatnonzero(mesh["receiver"] >= 0)
    receivers = mesh["receiver"][edges]
    midpoints = (nodes[edges] + nodes[receivers]) / 2
    selected = int(np.argmin(np.sum((midpoints - domain_center) ** 2, axis=1)))
    first, second = int(edges[selected]), int(receivers[selected])
    center = midpoints[selected]
    delta = nodes[second] - nodes[first]
    normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
    distances_m = np.linspace(-150., 150., 3001)
    section_points = center + distances_m[:, None] / 1000 * normal
    window = [center[0] - .15, center[0] + .15, center[1] - .15, center[1] + .15]
    heights = []
    for mesh in sample["meshes"]:
        vertices = (mesh["vertices_xz_m"] - origin) / 1000
        mask = (vertices[:, 0] >= window[0]) & (vertices[:, 0] <= window[1]) & (vertices[:, 1] >= window[2]) & (vertices[:, 1] <= window[3])
        heights.extend(mesh["source_elevation_m"][mask].tolist())
        heights.extend(mesh["bed_elevation_m"][mask].tolist())
    local_norm = Normalize(min(heights), max(heights))
    figure, axes = plt.subplots(2, 2, figsize=(13, 11), constrained_layout=True)
    for axis, key, title in ((axes[0, 0], "source_elevation_m", "Actual mesh original terrain"),
                             (axes[0, 1], "bed_elevation_m", "Actual processed bed mesh"),
                             (axes[1, 0], "cut_depth_m", "Actual saved mesh incision")):
        terrain(axis, sample, local_norm, shaded=True)
        norm = cut_norm if key == "cut_depth_m" else local_norm
        palette = "magma" if key == "cut_depth_m" else "gist_earth"
        mesh_layer(axis, sample, key, norm, palette, window=window)
        axis.set(xlim=window[:2], ylim=(window[3], window[2]), title=title)
        axis.plot(section_points[:, 0], section_points[:, 1], color="#202020", linestyle="--", linewidth=.65)
        axis.scatter([center[0]], [center[1]], color="#202020", s=10)
        colorbar(figure, axis, norm, palette, "Incision (m)" if key == "cut_depth_m" else "Elevation (m)")
    axis = axes[1, 1]
    xx, zz = section_points.T
    rows = np.clip(zz / (z[1] - z[0]), 0, len(z) - 1)
    cols = np.clip(xx / (x[1] - x[0]), 0, len(x) - 1)
    row0 = np.minimum(rows.astype(int), len(z) - 2)
    col0 = np.minimum(cols.astype(int), len(x) - 2)
    row_fraction, col_fraction = rows - row0, cols - col0
    native = sample["arrays"]["source_height_m"]
    source_line = ((1 - row_fraction) * ((1 - col_fraction) * native[row0, col0] + col_fraction * native[row0, col0 + 1])
                   + row_fraction * ((1 - col_fraction) * native[row0 + 1, col0] + col_fraction * native[row0 + 1, col0 + 1]))
    axis.plot(distances_m, source_line, color="#555555", label="Original native TD bilinear terrain")
    section_max_cut_m = 0.
    center_cut_m = None
    for mesh in sample["meshes"]:
        section = transect(mesh, origin, xx, zz)
        if section is None:
            continue
        incision = section[0] - section[1]
        if incision.count():
            section_max_cut_m = max(section_max_cut_m, float(incision.max()))
        if not np.ma.is_masked(incision[len(distances_m) // 2]):
            center_cut_m = float(incision[len(distances_m) // 2])
        for values, color, label in ((section[0], "#d0871c", "Saved mesh source"),
                                     (section[1], "#168072", "Saved processed bed")):
            if values.count():
                axis.plot(distances_m, values, color=color, linewidth=1.5, label=label)
    axis.set(xlabel="Normal distance from accepted centerline midpoint (m)", ylabel="Elevation (m)",
             title=f"Actual mesh section at X={center[0]:.3f}, Z={center[1]:.3f} km")
    axis.grid(alpha=.2)
    handles, labels = axis.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    axis.legend(unique.values(), unique.keys(), fontsize=8)
    figure.suptitle(f"{sample['name']} | actual saved bed detail\nAccepted edge midpoint nearest full-domain center; 300 m normal section; same rule for every sample.")
    figure.savefig(output / (sample["name"] + "-mesh-detail.png"), dpi=160)
    plt.close(figure)
    return {"available": True, "center_local_km": center.tolist(), "window_local_km": window,
            "normal_xz": normal.tolist(), "source_edge_cell_ids": mesh["source_node_cell_ids"][[first, second]].tolist(),
            "normal_section_max_cut_m": section_max_cut_m, "centerline_cut_m": center_cut_m,
            "rule": "300 m window about accepted centerline edge midpoint nearest domain center; 300 m transect normal to that edge"}


def render_sample(sample, output, elevation_norm, cut_norm):
    figure, axes = plt.subplots(2, 3, figsize=(19, 12))
    figure.subplots_adjust(left=.05, right=.97, top=.89, bottom=.13, wspace=.4, hspace=.3)
    terrain(axes[0, 0], sample, elevation_norm)
    axes[0, 0].set_title("Complete original native TD elevation")
    colorbar(figure, axes[0, 0], elevation_norm, "gist_earth", "Elevation (m)")
    terrain(axes[0, 1], sample, elevation_norm, shaded=True)
    statuses = network(axes[0, 1], sample)
    axes[0, 1].set_title("All algorithm river edges and terminal types")
    for axis, key, title in ((axes[0, 2], "source_elevation_m", "Saved mesh: original terrain surface"),
                             (axes[1, 0], "bed_elevation_m", "Saved mesh: processed channel bed"),
                             (axes[1, 1], "cut_depth_m", "Actual mesh incision (source - bed)")):
        terrain(axis, sample, elevation_norm, shaded=True)
        norm = cut_norm if key == "cut_depth_m" else elevation_norm
        palette = "magma" if key == "cut_depth_m" else "gist_earth"
        mesh_layer(axis, sample, key, norm, palette)
        axis.set_title(title)
        colorbar(figure, axis, norm, palette, "Actual cut (m)" if key == "cut_depth_m" else "Mesh elevation (m)")
    sections = cross_sections(axes[1, 2], sample)
    handles = [Line2D([], [], color="#168072", label="Accepted mesh-backed edges / processed bed"),
               Line2D([], [], color="#ba493d", label="Rejected edges; no constructed bed"),
               Line2D([], [], color="#9b2c75", marker="x", linestyle="none", label="Internal depression terminal; not lake surface"),
               Line2D([], [], color="#262626", marker="s", linestyle="none", label="Unknown domain-edge terminal; not verified sea mouth"),
               Line2D([], [], color="#d0871c", label="Saved mesh original surface in sections")]
    figure.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .02), ncol=3, fontsize=9)
    figure.suptitle(f"{sample['name']} | full native TD domain, generated river network, actual saved bed\n"
                   "Same view rules for all six samples. Edge line widths are annotations, not physical channel widths.", fontsize=14)
    figure.savefig(output / (sample["name"] + ".png"), dpi=145, facecolor="white")
    plt.close(figure)
    detail = render_mesh_detail(sample, output, cut_norm)
    return {"sample": sample["name"], "edge_status_counts": statuses, "sections": sections, "mesh_detail": detail,
            "mesh_vertex_count": sum(len(mesh["vertices_xz_m"]) for mesh in sample["meshes"]),
            "mesh_triangle_count": sum(len(mesh["triangles"]) for mesh in sample["meshes"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    renderer_source = Path(__file__).read_bytes()
    renderer_sha256 = hashlib.sha256(renderer_source).hexdigest()
    samples = [load_sample(path, include_mesh=False) for path in sorted(args.input.glob("sample-*")) if path.is_dir()]
    if len(samples) != 6:
        raise ValueError("Expected all six saved TD samples")
    elevation_norm = Normalize(min(float(s["arrays"]["source_height_m"].min()) for s in samples),
                               max(float(s["arrays"]["source_height_m"].max()) for s in samples))
    cut_max = 0.
    for sample in samples:
        record = sample["report"].get("global_bed")
        if record:
            with np.load(sample["path"] / record["path"], allow_pickle=False) as archive:
                cut_max = max(cut_max, float(archive["cut_depth_m"].max()))
    cut_norm = Normalize(0., max(.01, cut_max))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "renderer-source.py").write_bytes(renderer_source)
    reports = []
    for sample in samples:
        loaded = load_sample(sample["path"])
        sample["meshes"] = loaded["meshes"]
        del loaded
        if sample["meshes"]:
            mesh = sample["meshes"][0]
            _, _, origin = coordinates(sample)
            sample["accepted_positions"] = dict(zip(mesh["source_node_cell_ids"].tolist(),
                                                    (mesh["node_xz_m"] - origin) / 1000))
            del mesh
        reports.append(render_sample(sample, args.output, elevation_norm, cut_norm))
        sample["meshes"] = []
        sample.pop("mesh_raster", None)
        print(json.dumps({"rendered": sample["name"]}), flush=True)
    figure, axes = plt.subplots(2, 3, figsize=(18, 12), constrained_layout=True)
    for sample, axis in zip(samples, axes.ravel()):
        terrain(axis, sample, elevation_norm)
        counts = network(axis, sample)
        axis.set_title(sample["name"] + " | " + ", ".join(f"{key}: {value}" for key, value in counts.items()), fontsize=10)
    figure.suptitle("Six complete native TD domains | same algorithm and display rules\nGreen: accepted; red: rejected. Cross: internal depression; square: unknown edge. No solved water surface.")
    figure.colorbar(plt.cm.ScalarMappable(norm=elevation_norm, cmap="gist_earth"), ax=axes.ravel().tolist(), shrink=.7, label="Original TD elevation (m)")
    figure.savefig(args.output / "overview.png", dpi=150)
    plt.close(figure)
    figure, axes = plt.subplots(6, 2, figsize=(14, 32), constrained_layout=True)
    for sample, row in zip(samples, axes):
        for axis, baseline in zip(row, (True, False)):
            terrain(axis, sample, elevation_norm, shaded=True)
            counts = network(axis, sample, baseline=baseline)
            axis.set_title(sample["name"] + (f" | original D8: {counts['baseline_edges']} selected edges" if baseline
                            else " | " + ", ".join(f"{key}: {value}" for key, value in counts.items())), fontsize=10)
    threshold_km2 = samples[0]["report"]["config"]["min_contributing_area_m2"] / 1e6
    figure.suptitle(f"All six full domains: original D8 baseline vs generated network\nSame selected-edge area threshold: {threshold_km2:g} km2. Matched full domains; no manually selected component.")
    figure.savefig(args.output / "baseline-comparison.png", dpi=120)
    plt.close(figure)
    inputs = [{"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
              for sample in samples for path in sample["inputs"]]
    report = {"inputs": inputs, "elevation_limits_m": [elevation_norm.vmin, elevation_norm.vmax],
              "actual_mesh_cut_limits_m": [0., cut_max], "samples": reports,
              "section_rule": "Full-domain X transects at native rows nearest 25%, 50%, 75% of Z extent",
              "full_domain_mesh_display": "1024 square raster: saved triangle area weighted pixel mean at triangle centroid; alpha equals true mesh area / pixel area. Local detail uses actual triangle polygons.",
              "renderer_sha256": renderer_sha256}
    (args.output / "render-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    links = "\n".join(f'<li><a href="{html.escape(s["name"])}.png">{html.escape(s["name"])}: original terrain, network, saved bed, incision and fixed sections</a></li>' for s in samples)
    images = "\n".join(f'<h2>{html.escape(s["name"])}</h2><a href="{html.escape(s["name"])}.png"><img src="{html.escape(s["name"])}.png" alt="{html.escape(s["name"])} saved terrain and bed inspection"></a>' + (f'<a href="{html.escape(s["name"])}-mesh-detail.png"><img src="{html.escape(s["name"])}-mesh-detail.png" alt="{html.escape(s["name"])} actual saved bed detail"></a>' if s["report"].get("global_bed") else '<p>No accepted saved bed mesh in this sample.</p>') for s in samples)
    document = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Native TD generated rivers</title><style>body{{font:16px system-ui;margin:24px auto;max-width:1500px;padding:0 20px;color:#202626;background:#fff}}img{{max-width:100%;height:auto}}a{{color:#12675d}}h1{{font-size:28px}}h2{{font-size:22px}}</style><h1>Native TD generated rivers: six full domains</h1><p>Original TD terrain, algorithm river edges, and actual saved triangle beds. Internal depression terminals are not lake surfaces. Domain-edge terminals have unknown external continuation. No sea mouth or solved water surface is asserted.</p><ul>{links}</ul><p><a href="render-report.json">Saved-input hashes and section measurements</a> | <a href="baseline-comparison.png">All six original D8 baselines vs generated networks</a></p><a href="overview.png"><img src="overview.png" alt="Six-domain overview"></a>{images}</html>'
    (args.output / "index.html").write_text(document, encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "samples": len(samples), "actual_cut_max_m": cut_max}))


if __name__ == "__main__":
    main()
