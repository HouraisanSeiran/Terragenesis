"""Generate static previews for a saved TD natural-river candidate."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_natural_channel_geometry import load_natural_channel_geometry
from terrain_pipeline.td_natural_river_network import load_natural_river_network


def load(root):
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    a = index["artifacts"]
    network = load_natural_river_network(root / "network.npz", expected_sha256=a["network"]["sha256"],
                                         expected_identity=a["network"]["identity_sha256"])
    geometry = load_natural_channel_geometry(root / "geometry.npz", expected_sha256=a["geometry"]["sha256"],
                                             expected_identity=a["geometry"]["identity_sha256"])
    return network, geometry


def setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def detail(path, network, geometry):
    plt = setup()
    n, g = network["arrays"], geometry["arrays"]
    spacing = network["metadata"]["spacing_m"]
    origin = np.asarray(network["metadata"]["origin_m_xz"], float)
    mask = n["selected_basin_mask"]
    cells = np.argwhere(mask)
    lo = np.maximum(cells.min(axis=0) - 8, 0)
    hi = np.minimum(cells.max(axis=0) + 9, mask.shape)
    image = n["source_height_m"][lo[0]:hi[0], lo[1]:hi[1]]
    fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
    extent = [origin[0] + lo[1] * spacing, origin[0] + (hi[1] - 1) * spacing,
              origin[1] + (hi[0] - 1) * spacing, origin[1] + lo[0] * spacing]
    im = ax.imshow(image, extent=extent, cmap="gist_earth", origin="upper")
    lines = g["edge_centerline_xyz_m"]
    q = np.maximum(g["node_representative_q_m3_s"], 1e-12)
    q_by_edge = q[np.searchsorted(g["node_cell_ids"], n["edge_cell_ids"][:, 0])]
    norm = plt.Normalize(float(q_by_edge.min()), float(q_by_edge.max()))
    cmap = plt.get_cmap("viridis")
    for line, value in zip(lines, q_by_edge):
        xy = line[:, [0, 2]]
        ax.plot(xy[:, 0], xy[:, 1], color=cmap(norm(value)), linewidth=1.2, alpha=.9)
    ax.contour(mask.astype(float), levels=[.5], extent=extent, colors="#ffe66d", linewidths=1.4)
    ax.set_title("Selected TD contribution basin | candidate channel centerlines")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Z (m)")
    ax.set_aspect("equal")
    fig.colorbar(im, ax=ax, shrink=.76, label="Terrain elevation (m)")
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, shrink=.76, pad=.08, label="Representative Q (m³/s)")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def oblique(path, network, geometry):
    plt = setup()
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    n, g = network["arrays"], geometry["arrays"]
    spacing = float(network["metadata"]["spacing_m"])
    origin = np.asarray(network["metadata"]["origin_m_xz"], float)
    mask = n["selected_basin_mask"]
    cells = np.argwhere(mask)
    lo = np.maximum(cells.min(axis=0) - 8, 0)
    hi = np.minimum(cells.max(axis=0) + 9, mask.shape)
    dem = n["source_height_m"][lo[0]:hi[0], lo[1]:hi[1]]
    stride = max(1, int(max(dem.shape) / 70))
    rr, cc = np.mgrid[lo[0]:hi[0]:stride, lo[1]:hi[1]:stride]
    zz = n["source_height_m"][lo[0]:hi[0]:stride, lo[1]:hi[1]:stride]
    x = origin[0] + cc * spacing
    z = origin[1] + rr * spacing
    fig = plt.figure(figsize=(12, 9), constrained_layout=True)
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(x, zz, z, cmap="gist_earth", linewidth=0, antialiased=True, alpha=.88,
                    rcount=min(70, zz.shape[0]), ccount=min(70, zz.shape[1]))
    lines = g["edge_centerline_xyz_m"]
    q = np.maximum(g["node_representative_q_m3_s"], 1e-12)
    q_by_edge = q[np.searchsorted(g["node_cell_ids"], n["edge_cell_ids"][:, 0])]
    norm = plt.Normalize(float(q_by_edge.min()), float(q_by_edge.max()))
    cmap = plt.get_cmap("plasma")
    segments = []
    colors = []
    for line, value in zip(lines, q_by_edge):
        segments.append(line[:, [0, 1, 2]])
        colors.append(cmap(norm(value)))
    ax.add_collection3d(Line3DCollection(segments, colors=colors, linewidths=1.8))
    ax.set_title("TD terrain and candidate river network (diagnostic overlay)")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Elevation (m)")
    ax.set_zlabel("Z (m)")
    ax.view_init(elev=36, azim=-124)
    ax.set_box_aspect((max(1, np.ptp(x)), max(1, np.ptp(zz)), max(1, np.ptp(z))))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def qmap(path, network, geometry):
    plt = setup()
    n, g = network["arrays"], geometry["arrays"]
    spacing = float(network["metadata"]["spacing_m"])
    origin = np.asarray(network["metadata"]["origin_m_xz"], float)
    fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
    im = ax.imshow(n["source_height_m"], extent=[origin[0], origin[0] + 255 * spacing,
                                                 origin[1] + 255 * spacing, origin[1]],
                   cmap="gist_earth", origin="upper")
    node_xy = g["node_world_xz_m"]
    q = np.maximum(g["node_representative_q_m3_s"], 1e-12)
    sc = ax.scatter(node_xy[:, 0], node_xy[:, 1], c=np.log10(q), s=8, cmap="magma", alpha=.9)
    ax.set_title("Candidate nodes colored by log₁₀ representative Q")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Z (m)")
    ax.set_aspect("equal")
    fig.colorbar(im, ax=ax, shrink=.78, label="Terrain elevation (m)")
    fig.colorbar(sc, ax=ax, shrink=.78, pad=.08, label="log₁₀ Q (m³/s)")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(root, output):
    output.mkdir(parents=True, exist_ok=True)
    network, geometry = load(root)
    detail(output / "basin-detail.png", network, geometry)
    oblique(output / "oblique-3d.png", network, geometry)
    qmap(output / "discharge-diagnostic.png", network, geometry)
    print(json.dumps({"output": str(output), "files": [p.name for p in output.glob("*.png")]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.output)
