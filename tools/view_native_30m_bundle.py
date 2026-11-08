import argparse
import json
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib.colors import LightSource

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from tools.native_30m_bundle_reader import load_candidate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--identity", default=None)
    args = ap.parse_args()
    if os.path.exists(args.output):
        raise SystemExit("refusing to overwrite existing output: %s" % args.output)
    env = load_candidate(args.bundle, expected_identity_sha256=args.identity)
    geo = env["geometry"]
    garr = geo["arrays"]
    sarr = env["arrays"]["source.npz"]
    darr = env["dynamics"]["arrays"]
    field = np.asarray(sarr["field"])
    origin = np.asarray(sarr["origin_native_xz"], dtype=float)
    node_xz = np.asarray(garr["node_xz_m"], dtype=float)
    ls = LightSource(azdeg=315, altdeg=45)
    rgb = ls.shade(field, cmap=plt.get_cmap("terrain"), vert_exag=1.0, blend_mode="soft")
    ext = [-0.5, field.shape[1] - 0.5, field.shape[0] - 0.5, -0.5]
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    ax = axes[0, 0]
    ax.imshow(rgb, extent=ext, origin="upper", aspect="auto")
    ax.plot(node_xz[:, 0] / 30.0 - origin[0], node_xz[:, 1] / 30.0 - origin[1], color="dodgerblue", lw=1.2)
    ax.set_title("saved 30m terrain (field) + reach nodes")
    ax.set_xlabel("x [30m px]")
    ax.set_ylabel("z [30m px]")
    tri = mtri.Triangulation(garr["vertices_xz_m"][:, 0], garr["vertices_xz_m"][:, 1], garr["triangles"])
    cut = np.asarray(garr["source_elevation_m"], dtype=float) - np.asarray(garr["bed_elevation_m"], dtype=float)
    ax = axes[0, 1]
    tp = ax.tripcolor(tri, cut, shading="gouraud", cmap="viridis")
    ax.plot(node_xz[:, 0], node_xz[:, 1], color="dodgerblue", lw=0.8)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_title("PL cut depth (saved)")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("z [m]")
    fig.colorbar(tp, ax=ax, label="Generation cut (not dynamic erosion) [m]")
    reach = env["arrays"]["reach_context.npz"]
    N = len(node_xz)
    recv = garr['receiver']
    assert np.array_equal(np.asarray(recv).ravel(), np.r_[np.arange(1, N), -1])
    edge = np.asarray(reach['node_distance_m'])
    assert edge.shape == (N,)
    assert np.all(np.isfinite(edge))
    assert edge[-1] == 0
    assert np.all(edge[:-1] > 0)
    assert np.allclose(edge[:-1], np.linalg.norm(np.diff(node_xz, axis=0), axis=1))
    nd = np.r_[0, np.cumsum(edge[:-1])]
    nb0 = np.asarray(reach["node_bed_m"], dtype=float)
    nbT = np.asarray(darr["node_bed_m"], dtype=float)[-1]
    wvT = np.asarray(darr["water_volume_m3"], dtype=float)[-1]
    area = np.asarray(darr["material_area_m2"], dtype=float)
    surf = nbT + np.divide(wvT, area, out=np.zeros_like(wvT), where=area > 0)
    ax = axes[1, 0]
    ax.plot(nd, nb0, color="black", lw=1.4, label="initial bed")
    ax.plot(nd, nbT, color="tab:red", lw=1.4, label="final bed")
    ax.plot(nd, surf, color="tab:blue", lw=1.2, ls="--", label="final surface")
    ax.set_xlabel("distance [m]")
    ax.set_ylabel("elevation [m]")
    ax.set_title("longitudinal profile")
    ax.legend(fontsize=8)
    ts = np.asarray(darr["time_seconds"], dtype=float)
    t_h = ts[-1] / 3600.0 if ts.size else 12.0
    db = (nbT - nb0) * 1000.0
    ax = axes[1, 1]
    ax.plot(nd, db, color="darkgreen", lw=1.3)
    ax.axhline(0.0, color="gray", lw=0.7)
    ax.set_xlabel("distance [m]")
    ax.set_ylabel("bed change [mm]")
    ax.set_title(f"{t_h:g}h nodal bed change (PL mesh unchanged)")
    fig.suptitle("Finite 30m candidate | seed20261020 | bundle=%s" % os.path.basename(args.bundle))
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())
    rgbpix = rgba[..., :3]
    std = float(np.std(rgbpix))
    frac = float(np.any(rgbpix < 250, axis=-1).mean())
    H = rgbpix.shape[0]
    bbox = axes[0, 0].get_position()
    y0 = int(H - np.ceil(bbox.y1 * H))
    y1 = int(H - np.floor(bbox.y0 * H))
    x0 = int(np.floor(bbox.x0 * rgbpix.shape[1]))
    x1 = int(np.ceil(bbox.x1 * rgbpix.shape[1]))
    y0 = np.clip(y0, 0, H)
    y1 = np.clip(y1, 0, H)
    x0 = np.clip(x0, 0, rgbpix.shape[1])
    x1 = np.clip(x1, 0, rgbpix.shape[1])
    crop = rgbpix[y0:y1, x0:x1]
    stdterrain = float(np.std(crop))
    nonwhiteTerrain = float(np.any(crop < 250, axis=-1).mean())
    if stdterrain <= 10 or nonwhiteTerrain <= 0.8:
        raise RuntimeError('terrain panel render check failed')
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    fig.savefig(args.output, dpi=150)
    plt.close(fig)

    print("identity=%s" % env["manifest"]["identity_sha256"])
    print("output=%s" % args.output)
    print("nonwhite=%.4f" % frac)
    print("std=%.3f" % std)

if __name__ == "__main__":
    main()
