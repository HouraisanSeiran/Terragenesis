"""Render an offline terrain map in remote-sensing or topographic style.

Two declared cartographic styles, both built from ``terrain_pipeline.terrain_map_style``:

``remote``
    Continuous hypsometric tint under physical relief shading, with the routing network
    drawn as permanent (solid) and seasonal (dashed) channels.  The look of a shaded-relief
    satellite composite: no graticule, because a grid is a printed-sheet device, not imagery.
``topo``
    Discrete hypsometric bands, index contours on every band edge, a kilometre graticule,
    scale bar and north arrow.  The look of a printed topographic sheet.

Where the data comes from
-------------------------
``--source``  a routed terrain archive holding ``original_td_m`` plus a ``receiver`` and
              optional ``permanent_channel_mask`` / ``seasonal_channel_mask``.
``--bundle``  a special-terrain surface bundle holding ``surface_xyz_m``; the chart is used
              *as stored*, and the figure is labelled a synthetic geometry study because a
              chart is not a georeferenced landscape.

What this tool refuses to do
----------------------------
* Write anywhere under ``verification/``.
* Draw a degree graticule unless the caller declares the metres-per-degree conversion
  explicitly; this terrain is an unbounded tile-pixel field, not a sphere.  Even then the
  figure stamps ``declared_graticule_not_a_projection`` and marks the labels with ``*``.
* Certify anything.  Every report carries ``status=candidate`` plus the four capability
  flags read from the source, and the figures are illustrations of stored arrays.

Colour limits and the grid step are derived from the chart unless the caller overrides them: a
208 m karst chart keeps the 536 m large-TD scale only if you ask for it, and a 160 m chart gets
a 20 m grid rather than a 10 km one that would draw nothing.  The one exception is the default
large-TD source, which keeps the frozen ``ELEVATION_LIMITS`` used by the existing review tools
so that a new map can be laid beside an old one without re-learning the scale.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import terrain_map_style as style
from terrain_pipeline.common_infra import identity

DEFAULT_SOURCE = (ROOT / "verification/hydrological-planning-domain/large-td-lowland-20261014-01"
                  / "lowland-runoff.npz")
DEFAULT_OUTPUT = ROOT / ".scratch/terrain-map-preview-20261020"
FROZEN_ELEVATION_LIMITS_M = (0.6085212230682373, 536.1844482421875)
PNG_META = {"Software": "render_terrain_map"}
FORBIDDEN_OUTPUT_PARTS = ("verification",)
CAPABILITY_FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable",
                   "self_intersection_verified")
STYLES = ("remote", "topo")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b""):
            digest.update(block)
    return digest.hexdigest()


def guard_output(output):
    resolved = Path(output).resolve()
    parts = [part.lower() for part in resolved.parts]
    for forbidden in FORBIDDEN_OUTPUT_PARTS:
        require(forbidden not in parts,
                f"refusing to write maps under {forbidden}/: {resolved}")
    return resolved


def _as_chart(arrays, key, height):
    """Return a boolean mask / index field on the chart grid, or None when absent."""
    if key not in arrays:
        return None
    field = np.asarray(arrays[key])
    if field.ndim == 1:
        require(field.size == height.size,
                f"{key} holds {field.size} cells but the chart holds {height.size}")
        field = field.reshape(height.shape)
    require(field.shape == height.shape,
            f"{key} has shape {field.shape}, expected {height.shape}")
    return field


def load_routed_scene(path, *, label):
    with np.load(path, allow_pickle=False) as archive:
        files = set(archive.files)
        require("original_td_m" in files, f"{label}: archive has no original_td_m")
        arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
        metadata = json.loads(str(archive["metadata_json"].item()))
    height = np.asarray(arrays["original_td_m"], np.float64)
    require(height.ndim == 2, f"{label}: original_td_m must be 2-D")
    require(np.isfinite(height).all(), f"{label}: original_td_m must be finite")
    spacing = float(metadata.get("spacing_m", 30.0))
    require(spacing > 0.0, f"{label}: spacing_m must be positive")
    origin = [float(value) for value in metadata.get("origin_xz_m", (0.0, 0.0))]
    receiver = _as_chart(arrays, "receiver", height)
    if receiver is not None:
        receiver = np.asarray(receiver, np.int64)
        require(receiver.min() >= -1, f"{label}: receiver below -1 is meaningless")
        require(receiver.max() < height.size, f"{label}: receiver leaves the chart")
    permanent = _as_chart(arrays, "permanent_channel_mask", height)
    seasonal = _as_chart(arrays, "seasonal_channel_mask", height)
    if permanent is not None and seasonal is not None:
        require(not bool(np.any(np.asarray(permanent, bool) & np.asarray(seasonal, bool))),
                f"{label}: permanent and seasonal masks overlap")
    require(receiver is not None or permanent is None,
            f"{label}: channel masks without a receiver cannot be drawn as a network")
    return {"label": label, "kind": "routed_terrain_archive", "height": height,
            "receiver": receiver, "permanent": permanent, "seasonal": seasonal,
            "spacing_m": spacing, "origin_xz_m": origin, "metadata": metadata,
            "source_identity": metadata.get("source_identity"),
            "chart_note": "stored original_td_m on its declared planar metre grid",
            "caveats": ["planar tile-pixel grid, not a geographic projection",
                        "river lines show stored routing, not a certified bed"]}


def resolve_bundle_provenance(path, *, manifest_path=None, sha256=None, identity=None):
    """Find a surface bundle's pinned digest and identity.

    ``load_special_form_surface`` refuses to read a bundle without both, and that refusal
    is the whole point of the bundle contract, so this tool will not paper over it with the
    digest of the file it is about to read.  The values come from an explicit pair of flags
    or from the sibling ``manifest-report.json`` that produced the bundle; guessing is not
    an option.
    """
    if sha256 is not None and identity is not None:
        return str(sha256), str(identity), "explicit_flags"
    candidates = []
    if manifest_path is not None:
        candidates.append(Path(manifest_path))
    candidates.append(Path(path).parent / "manifest-report.json")
    name = Path(path).name
    for candidate in candidates:
        if not candidate.is_file():
            continue
        record = json.loads(candidate.read_text(encoding="utf-8"))
        entry = record.get("forms", {}).get(Path(name).stem)
        if entry is None:
            continue
        return str(entry["sha256"]), str(entry["identity_sha256"]), str(candidate)
    raise SystemExit(
        f"no pinned digest/identity for {name}: pass --bundle-sha256 and --bundle-identity, "
        "or point --bundle-manifest at the manifest that lists it")


def load_bundle_scene(path, *, label, sha256, identity_sha256):
    from terrain_pipeline.special_terrain import load_special_form_surface
    result = load_special_form_surface(path, expected_sha256=sha256,
                                       expected_identity=identity_sha256)
    arrays, metadata = result["arrays"], result["metadata"]
    reference = np.asarray(arrays["reference_xyz_m"], np.float64)
    require(reference.ndim == 3 and reference.shape[2] == 3,
            f"{label}: bundle has no usable reference_xyz_m")
    surface = np.asarray(arrays["surface_xyz_m"], np.float64)
    require(surface.shape == reference.shape,
            f"{label}: surface and reference charts differ in shape")
    x = reference[:, :, 0]
    z = reference[:, :, 2]
    spacing_x = float(x[0, 1] - x[0, 0]) if x.shape[1] > 1 else 0.0
    spacing_z = float(z[1, 0] - z[0, 0]) if x.shape[0] > 1 else 0.0
    require(spacing_x > 0.0 and abs(spacing_x - spacing_z) <= 1e-9 * max(spacing_x, spacing_z),
            f"{label}: chart spacing is not uniform and positive")
    require(np.allclose(x, x[0, 0] + np.arange(x.shape[1])[None, :] * spacing_x),
            f"{label}: chart x coordinates are not a regular grid")
    require(np.allclose(z, z[0, 0] + np.arange(z.shape[0])[:, None] * spacing_z),
            f"{label}: chart z coordinates are not a regular grid")
    for flag in CAPABILITY_FLAGS:
        require(metadata.get(flag) is False,
                f"{label}: bundle flag {flag} is not False, so it is not a candidate")
    height = np.asarray(surface[:, :, 1], np.float64)
    require(np.isfinite(height).all(), f"{label}: surface chart must be finite")
    return {"label": label, "kind": "special_terrain_surface_bundle", "height": height,
            "receiver": None, "permanent": None, "seasonal": None,
            "spacing_m": spacing_x,
            "origin_xz_m": [float(x[0, 0]), float(z[0, 0])], "metadata": metadata,
            "source_identity": result["identity_sha256"],
            "chart_note": "stored surface chart; synthetic analytic geometry, not a landscape",
            "caveats": ["synthetic analytic chart, not real Terrain Diffusion detail",
                        "no routing exists on this chart, so no river layer is drawn"]}


def scene_extent_km(scene):
    height = scene["height"]
    spacing = scene["spacing_m"] / 1000.0
    ox, oz = scene["origin_xz_m"][0] / 1000.0, scene["origin_xz_m"][1] / 1000.0
    return [ox, ox + (height.shape[1] - 1) * spacing,
            oz + (height.shape[0] - 1) * spacing, oz]


def river_segments(scene):
    """Cell-centre segments from the stored receiver, in kilometres."""
    receiver = scene["receiver"]
    if receiver is None:
        return None
    height = scene["height"]
    spacing = scene["spacing_m"] / 1000.0
    ox, oz = scene["origin_xz_m"][0] / 1000.0, scene["origin_xz_m"][1] / 1000.0
    columns = height.shape[1]
    flat = receiver.ravel()
    def coordinates(cells):
        return np.c_[ox + (cells % columns) * spacing, oz + (cells // columns) * spacing]
    layers = {}
    for key, source in (("permanent", scene["permanent"]), ("seasonal", scene["seasonal"])):
        if source is None:
            continue
        selected = np.flatnonzero(np.asarray(source, bool).ravel() & (flat >= 0))
        if selected.size == 0:
            layers[key] = np.empty((0, 2, 2))
            continue
        layers[key] = np.stack((coordinates(selected), coordinates(flat[selected])), axis=1)
    return layers


def draw_rivers(axis, layers, span_km):
    from matplotlib.collections import LineCollection
    handles = []
    if layers is None:
        return handles
    # Line width follows the declared map span, not the axes' own autoscaled limits, so the
    # same network reads the same way at every zoom.
    thin = max(float(span_km), 1.0) / 320.0
    for key, colour, dash, title in (("permanent", "#043c67", "solid", "permanent channel"),
                                     ("seasonal", "#b80a82", "dashed", "seasonal channel")):
        segments = layers.get(key)
        if segments is None or segments.shape[0] == 0:
            continue
        axis.add_collection(LineCollection(segments, colors="#eaf7ff", linewidths=thin * 2.1,
                                           alpha=0.85, zorder=11))
        axis.add_collection(LineCollection(segments, colors=colour, linewidths=thin * 1.1,
                                           linestyles=dash, zorder=12))
        handles.append((colour, dash, f"{title} ({segments.shape[0]} links)"))
    return handles


def band_legend(axis, band_edges, colours):
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.cm import ScalarMappable
    edges = np.asarray(band_edges, np.float64)
    norm = BoundaryNorm(edges, len(colours))
    return ScalarMappable(norm=norm, cmap=ListedColormap([tuple(row) for row in colours]))


def draw_contours(axis, scene, band_edges, *, heavy_every=2, colour="#1b1b1b"):
    height = scene["height"]
    x = scene["origin_xz_m"][0] / 1000.0 + np.arange(height.shape[1]) * scene["spacing_m"] / 1000.0
    z = scene["origin_xz_m"][1] / 1000.0 + np.arange(height.shape[0]) * scene["spacing_m"] / 1000.0
    low, high = float(height.min()), float(height.max())
    levels = [float(value) for value in band_edges if low < value < high]
    if not levels:
        return []
    axis.contour(x, z, height, levels=levels, colors=colour, linewidths=0.35,
                 alpha=0.55, zorder=10)
    heavy = levels[::heavy_every]
    if heavy:
        axis.contour(x, z, height, levels=heavy, colors=colour, linewidths=0.8,
                     alpha=0.75, zorder=10)
    return levels


def resolve_elevation_limits(height, requested, *, label):
    """Colour limits for a figure: the caller's, or this chart's own range.

    ``FROZEN_ELEVATION_LIMITS_M`` belongs to the large-TD sheet, so borrowing it for a 208 m
    karst chart would stretch the ramp over 2.6x the real relief and squeeze the towers into
    one or two bands.  The frozen pair is therefore a default for that source only, and any
    other source gets its own extremes unless the caller overrides them explicitly.
    """
    if requested is not None:
        low, high = float(requested[0]), float(requested[1])
        require(high > low, f"{label}: elevation limits must increase")
        return [low, high]
    require(np.isfinite(height).all(), f"{label}: height must be finite to derive limits")
    low, high = float(height.min()), float(height.max())
    if not high > low:
        low, high = low, low + 1.0
        print(f"{label}: flat chart, colour limits widened to {low:g}..{high:g} m")
    return [low, high]


def resolve_graticule_step(span_km, requested, *, label):
    if requested is None:
        return style.nice_graticule_step_km(span_km)
    require(float(requested) > 0.0, f"{label}: graticule step must be positive")
    return float(requested)


def render_scene(scene, output, *, styles, elevation_limits=None, graticule_step_km=None,
                 declared_graticule, band_edges, band_colours, dpi):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    height = scene["height"]
    extent = scene_extent_km(scene)
    require(abs((extent[1] - extent[0]) - (height.shape[1] - 1) * scene["spacing_m"] / 1000.0)
            <= 1e-9 * max(1.0, extent[1] - extent[0]),
            f"{scene['label']}: map width disagrees with chart shape x spacing")
    require(abs((extent[2] - extent[3]) - (height.shape[0] - 1) * scene["spacing_m"] / 1000.0)
            <= 1e-9 * max(1.0, extent[2] - extent[3]),
            f"{scene['label']}: map height disagrees with chart shape x spacing")
    span_km = max(extent[1] - extent[0], extent[2] - extent[3])
    scale_km = style.nice_scale_length_km(span_km)
    limits = resolve_elevation_limits(height, elevation_limits, label=scene["label"])
    graticule_step_km = resolve_graticule_step(span_km, graticule_step_km,
                                              label=scene["label"])
    ocean = ~(height >= style.SEA_LEVEL_M)
    layers = river_segments(scene)
    figures, records = {}, {}

    colours = style.band_colors(band_edges, band_colours)
    aspect = (extent[2] - extent[3]) / max(extent[1] - extent[0], 1e-9)

    for name in styles:
        if name == "remote":
            rgb = style.continuous_relief_rgb(height, scene["spacing_m"], limits,
                                              ocean_mask=ocean if ocean.any() else None)
            legend = "continuous elevation (m)"
        else:
            rgb = style.banded_relief_rgb(height, scene["spacing_m"], band_edges=band_edges,
                                          colors=band_colours,
                                          ocean_mask=ocean if ocean.any() else None)
            legend = "hypsometric band (m)"
        fig, axis = plt.subplots(figsize=(12.0, 1.0 + 11.0 * aspect), dpi=dpi)
        image = axis.imshow(rgb, extent=extent, interpolation="nearest", zorder=5)
        require(tuple(np.asarray(image.get_array()).shape[:2]) == height.shape,
                f"{scene['label']}: the {name} panel does not show the stored chart")
        handles = draw_rivers(axis, layers, span_km)
        contour_levels = []
        graticule = None
        if name == "topo":
            # The kilometre graticule is part of the printed-sheet style only: a shaded-relief
            # satellite composite carries no cartographic grid, so the remote panel stays a
            # pure image of the stored chart plus the routing network.
            contour_levels = draw_contours(axis, scene, band_edges)
            if graticule_step_km:
                graticule = style.draw_metre_graticule(axis, step_km=graticule_step_km)
        declared = None
        if declared_graticule is not None:
            declared = style.draw_declared_graticule(axis, **declared_graticule)
        style.draw_scale_bar(axis, scale_km)
        style.draw_north_arrow(axis)
        axis.set_xlim(extent[0], extent[1])
        axis.set_ylim(extent[2], extent[3])
        axis.set_aspect("equal")
        axis.set_xlabel("world x east (km)")
        axis.set_ylabel("world z south (km)")
        axis.set_title(f"{scene['label']} - {name} style ({scene['kind']})\n{scene['chart_note']}",
                       fontsize=11)
        if name == "remote":
            # The panel is an RGB array, so `colorbar(image)` would label the bar with the
            # pixel range 0..1 instead of metres -- a reader could not tell 300 m from
            # 3000 m. Attach the same Normalize the ramp used, over a greyscale ramp of
            # the declared elevation limits, and the ticks become metres again.
            from matplotlib.cm import ScalarMappable
            from matplotlib.colors import Normalize
            mappable = ScalarMappable(norm=Normalize(*limits, clip=True), cmap="Greys_r")
            mappable.set_array(np.asarray([]))
            bar = fig.colorbar(mappable, ax=axis, shrink=0.82, pad=0.02)
            bar.set_label(legend)
        else:
            mappable = band_legend(axis, band_edges, colours)
            bar = fig.colorbar(mappable, ax=axis, shrink=0.82, pad=0.02, ticks=band_edges)
            bar.set_label(legend)
            bar.ax.tick_params(labelsize=7)
        if handles:
            for colour, dash, title in handles:
                axis.plot([], [], color=colour, linestyle=dash, linewidth=1.4, label=title)
            axis.legend(loc="lower right", fontsize=8, framealpha=0.85)
        if declared is not None:
            axis.text(0.01, 0.985, "degree labels marked * use a declared conversion, "
                      "not a geographic projection", transform=axis.transAxes, fontsize=7,
                      color="#5a3d7a", va="top")
        path = output / f"{scene['label']}-{name}.png"
        fig.savefig(path, metadata=PNG_META, bbox_inches="tight")
        plt.close(fig)
        figures[name] = path
        records[name] = {
            "file": path.name, "sha256": sha256_file(path),
            "style": name, "chart_shape": list(height.shape),
            "extent_km": [float(value) for value in extent],
            "scale_bar_km": float(scale_km),
            "plotted_min_m": float(height.min()), "plotted_max_m": float(height.max()),
            "colour_range_m": [float(limits[0]), float(limits[1])],
            "contour_levels_m": contour_levels,
            "river_link_counts": ({key: int(value.shape[0]) for key, value in layers.items()}
                                   if layers else None),
            "graticule": graticule,
            "declared_graticule": declared,
            "ocean_drawn": bool(ocean.any()),
            "colour_recipe": ("continuous_relief" if name == "remote" else "hypsometric_bands"),
        }
    return figures, records, {"scale_bar_km": float(scale_km), "span_km": float(span_km),
                             "colour_range_m": list(limits),
                             "graticule_step_km": float(graticule_step_km)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--bundle-manifest", type=Path,
                        help="manifest-report.json that lists the bundle's digest and identity")
    parser.add_argument("--bundle-sha256")
    parser.add_argument("--bundle-identity")
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--label")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--styles", default="remote,topo")
    parser.add_argument("--elevation-limits", type=float, nargs=2,
                        help="colour limits in metres; default is the chart's own range for a "
                             "bundle and the frozen large-TD limits for the default source")
    parser.add_argument("--graticule-step-km", type=float,
                        help="kilometre grid step; default is derived from the map span")
    parser.add_argument("--band-edges", type=float, nargs="+", default=list(style.LAND_BANDS_M))
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--declare-metres-per-degree-east", type=float)
    parser.add_argument("--declare-metres-per-degree-north", type=float)
    parser.add_argument("--declare-origin-degrees", type=float, nargs=2)
    parser.add_argument("--declare-step-degrees", type=float, default=0.5)
    args = parser.parse_args(argv)

    requested = [value for value in args.styles.split(",") if value]
    unknown = sorted(set(requested) - set(STYLES))
    if unknown:
        raise SystemExit(f"unknown styles: {unknown}")
    if not requested:
        raise SystemExit("at least one style is required")
    output = guard_output(args.output)
    output.mkdir(parents=True, exist_ok=True)

    bundle_provenance = None
    requested_limits = args.elevation_limits
    if args.bundle:
        source = Path(args.bundle)
        label = args.label or source.stem
        digest, bundle_identity, origin = resolve_bundle_provenance(
            source, manifest_path=args.bundle_manifest, sha256=args.bundle_sha256,
            identity=args.bundle_identity)
        bundle_provenance = {"expected_sha256": digest, "expected_identity": bundle_identity,
                             "resolved_from": origin}
        scene = load_bundle_scene(source, label=label, sha256=digest,
                                  identity_sha256=bundle_identity)
    else:
        source = Path(args.source)
        label = args.label or source.stem
        scene = load_routed_scene(source, label=label)
        if requested_limits is None and Path(args.source).resolve() == DEFAULT_SOURCE.resolve():
            # The frozen pair belongs to that published sheet; keep it so a new map can be
            # laid beside the existing review figures on the same scale.
            requested_limits = list(FROZEN_ELEVATION_LIMITS_M)
    if args.expected_source_sha256:
        digest = sha256_file(source)
        require(digest == args.expected_source_sha256,
                f"source digest differs: {digest} != {args.expected_source_sha256}")

    declared = None
    declare = (args.declare_metres_per_degree_east, args.declare_metres_per_degree_north,
               args.declare_origin_degrees)
    if any(value is not None for value in declare):
        require(all(value is not None for value in declare),
                "a declared graticule needs metres-per-degree east and north plus origin degrees")
        declared = {"origin_xz_m": scene["origin_xz_m"],
                    "metres_per_degree_east": args.declare_metres_per_degree_east,
                    "metres_per_degree_north": args.declare_metres_per_degree_north,
                    "origin_degrees": args.declare_origin_degrees,
                    "step_degrees": args.declare_step_degrees}

    figures, records, geometry = render_scene(
        scene, output, styles=requested, elevation_limits=requested_limits,
        graticule_step_km=args.graticule_step_km, declared_graticule=declared,
        band_edges=args.band_edges, band_colours=style.BAND_COLORS, dpi=args.dpi)

    flags = {flag: scene["metadata"].get(flag, False) for flag in CAPABILITY_FLAGS}
    report = {
        "status": "candidate",
        "tool": "render_terrain_map",
        "style": "offline terrain map, remote-sensing and topographic styles",
        "scene": {"label": scene["label"], "kind": scene["kind"],
                  "chart_note": scene["chart_note"], "caveats": scene["caveats"]},
        "source": {"path": str(Path(source).resolve()), "sha256": sha256_file(source),
                   "spacing_m": scene["spacing_m"], "origin_xz_m": scene["origin_xz_m"],
                   "chart_shape": list(scene["height"].shape),
                   "source_identity_sha256": scene["source_identity"],
                   "bundle_provenance": bundle_provenance,
                   "declared_capability_flags": flags},
        "band_declaration": {"edges_m": [float(value) for value in style.validate_band_edges(args.band_edges)],
                             "colours": list(style.BAND_COLORS)},
        "relief_declaration": {"ramp": list(style.RELIEF_COLORS),
                               "hillshade_base": style.HILLSHADE_BASE,
                               "hillshade_weight": style.HILLSHADE_WEIGHT,
                               "light": list(style.HILLSHADE_LIGHT),
                               "sea_level_m": style.SEA_LEVEL_M},
        "geometry": geometry, "figures": records,
        "claims": {"geographic_projection": False, "graticule_is_geographic": False,
                   "certified": False, "illustration_only": True},
        "notes": ["colour bands and ramps are declared cartographic style, not derivations",
                  "the terrain lies on a planar tile-pixel grid; no CRS is resolved",
                  "no figure certifies a channel, an outlet or a lake"],
    }
    report["report_identity_sha256"] = identity(
        {"chart": scene["height"]}, {key: value for key, value in report.items()
                                     if key != "report_identity_sha256"})
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    print(f"label={scene['label']} kind={scene['kind']} chart={scene['height'].shape}")
    print(f"span_km={geometry['span_km']:.2f} scale_bar_km={geometry['scale_bar_km']:g}"
          f" relief={scene['height'].min():.3f}..{scene['height'].max():.3f} m")
    for name, record in sorted(records.items()):
        print(f"  {name}: {record['file']} sha256={record['sha256'][:16]} "
              f"contours={len(record['contour_levels_m'])}")
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
