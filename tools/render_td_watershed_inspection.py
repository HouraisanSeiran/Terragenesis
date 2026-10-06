"""Static scientific inspection: native terrain and saved bed triangles only."""

from io import BytesIO
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_td_watershed_inspection import (
    encoded, load_inspection, mesh_caseartifact, parser, publish_directory)


def render_overview(review):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection
    from matplotlib.colors import LightSource
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Rectangle

    terrain = np.asarray(review["terrain"]["height_m"])
    coords = review["coordinates"]
    spacing = coords["spacing_m"]
    origin = np.asarray(coords["origin_m_xz"])
    layers = review["layers"]
    mesh = layers["saved_bed_mesh"]
    vertices = np.asarray(mesh["vertices_xyz_m"])
    triangles = np.asarray(mesh["triangles"])
    plan = (vertices[:, [0, 2]] - origin) / 1000.
    polygons = plan[triangles]
    arcs = {arc["arc_id"]: arc for arc in layers["receiver_candidates"] + layers["support_arcs"]}
    matched = {edge["arc_id"] for edge in layers["constructible_edges"]}
    rejected = {edge["arc_id"] for edge in layers["rejected_edges"]}
    diagnostics = {record["arc_id"]: record for record in review["reach_diagnostics"]}
    selected = np.asarray(review["views"]["primary_support_cell_ids"])
    rows, columns = np.divmod(selected, terrain.shape[1])
    primary = [max(0, columns.min()*spacing/1000.-.12),
               min((terrain.shape[1]-1)*spacing/1000., columns.max()*spacing/1000.+.12),
               max(0, rows.min()*spacing/1000.-.12),
               min((terrain.shape[0]-1)*spacing/1000., rows.max()*spacing/1000.+.12)]
    centers = polygons.mean(axis=1)
    first = polygons[:, 1] - polygons[:, 0]
    second = polygons[:, 2] - polygons[:, 0]
    area = np.abs(first[:, 0]*second[:, 1] - first[:, 1]*second[:, 0])
    center = centers[np.argmax(area)]
    closeup = [center[0]-.04, center[0]+.04, center[1]-.04, center[1]+.04]
    extent = [-spacing/2000., (terrain.shape[1]-.5)*spacing/1000.,
              (terrain.shape[0]-.5)*spacing/1000., -spacing/2000.]
    shade = LightSource(315, 45).hillshade(terrain, dx=spacing, dy=spacing)
    figure, axes = plt.subplots(1, 3, figsize=(19, 8), gridspec_kw={"width_ratios": [1, 1.45, 1.2]})
    figure.subplots_adjust(left=.045, right=.985, top=.84, bottom=.23, wspace=.22)
    footprint = np.zeros(terrain.shape, dtype=float)
    footprint.flat[selected] = 1
    wet = np.zeros((*terrain.shape, 4))
    wet.reshape(-1, 4)[layers["sampled_lake_wet_cell_ids"]] = [.37, .34, .43, .72]

    def lines(axis, identifiers, color, style, widths, alpha=1):
        items = [arcs[key] for key in sorted(identifiers)]
        points = [(np.asarray(arc["xyz_m"])[:, [0, 2]]-origin)/1000. for arc in items]
        axis.add_collection(LineCollection(points, colors=color, linestyles=style,
                                           linewidths=widths, alpha=alpha, zorder=4))

    for index, axis in enumerate(axes):
        axis.imshow(shade, cmap="gray", vmin=-.2, vmax=1.2, extent=extent, interpolation="nearest")
        axis.contour(np.arange(terrain.shape[1])*spacing/1000., np.arange(terrain.shape[0])*spacing/1000.,
                     terrain, levels=12, colors="#555555", linewidths=.25, alpha=.35)
        axis.contour(np.arange(terrain.shape[1])*spacing/1000., np.arange(terrain.shape[0])*spacing/1000.,
                     footprint, levels=[.5], colors="#252525", linewidths=.8)
        axis.imshow(wet, extent=extent, interpolation="nearest", zorder=3)
        lines(axis, rejected, "#9f6258", "dotted", .45, .48)
        lines(axis, set(arcs)-matched-rejected, "#777080", "dashed", .45, .48)
        axis.add_collection(PolyCollection(polygons, facecolors="#58754d", edgecolors="#294025",
                                           linewidths=.16 if index < 2 else .55, zorder=5))
        if index < 2:
            keys = sorted(matched)
            widths = [.6 + min(1.4, np.sqrt(max(0, diagnostics[key]["representative_q_m3_s"]))) for key in keys]
            lines(axis, keys, "#365130", "solid", widths, .9)
        bounds = [extent[0], extent[1], extent[3], extent[2]] if index == 0 else primary if index == 1 else closeup
        axis.set_xlim(bounds[0], bounds[1])
        axis.set_ylim(bounds[3], bounds[2])
        axis.set_aspect("equal")
        axis.set_xlabel("Local east from pinned origin (km)")
        axis.set_ylabel("Local south (km)")
        axis.set_title(["Full native TD domain / component location",
                        f"{review['views']['primary_support_area_m2']/1e6:.4f} km2 component / matched-bed emphasis",
                        "Saved triangle detail / true plan widths"][index], fontsize=11)
    axes[0].add_patch(Rectangle((primary[0], primary[2]), primary[1]-primary[0], primary[3]-primary[2],
                                fill=False, edgecolor="#222222", linewidth=1.3))
    axes[1].add_patch(Rectangle((closeup[0], closeup[2]), closeup[1]-closeup[0], closeup[3]-closeup[2],
                                fill=False, edgecolor="#222222", linewidth=1.3))
    legend = [Patch(facecolor="#425e39", label="Actual saved bed triangles: 6576 (local strips; NOT water)"),
              Line2D([], [], color="#365130", linewidth=1.8, label="1096 mesh-matched receiver annotations; width = ordinary mean Q proxy"),
              Line2D([], [], color="#9f6258", linestyle=":", label="680 refused receiver candidates (no bed / no water)"),
              Line2D([], [], color="#777080", linestyle="--", label="219 lake/spill support arcs (not hydraulic direction)"),
              Patch(facecolor="#665c70", label="Saved simultaneous lake footprint at 24 h (77 native cells; no water mesh)"),
              Line2D([], [], color="#252525", label="Primary contribution footprint on original 30 m terrain")]
    figure.legend(handles=legend, loc="lower center", bbox_to_anchor=(.5,.055), ncol=2, fontsize=10, frameon=False)
    figure.suptitle("TD mountain watershed | native terrain vs saved local bed strips vs candidate", fontsize=16, y=.96)
    figure.text(.5,.89,f"{len(layers['nodes'])} saved nodes / {len(arcs)} typed arcs retained; no invented trunk, no gap filling, no solved water", ha="center", fontsize=11)
    figure.text(.5,.025,"Metric model, not surveyed terrain. Q is an uncalibrated ordinary-event mean prior, NOT measured or instantaneous flow.\n"
                "Triangles retain saved XYZ and connectivity. Green thick lines in overview are matched-source annotations, not physical bed widths.",
                ha="center", fontsize=10)
    output = BytesIO()
    figure.savefig(output, format="png", dpi=160, facecolor="white")
    plt.close(figure)
    return output.getvalue()


def main():
    args = parser(__doc__).parse_args()
    review = load_inspection(args.index, args.index_sha256)
    artifacts = {"overview.png": render_overview(review),
                 "caseartifact.json": encoded(mesh_caseartifact(review))}
    print(publish_directory(args.output, artifacts))


if __name__ == "__main__":
    main()
