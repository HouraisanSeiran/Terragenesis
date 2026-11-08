"""Synthetic orthophoto-style rendering of a saved world reach.

What this is
------------
A **visualisation** that imitates an overhead remote-sensing image. It is not
satellite data: no observation, sensor model or spectral calibration is
involved. Surface colour, hillshade and water tint are declared rendering
choices; the elevation field, carved bed and water stages come from saved
physical results.

Declared rendering choices (also written into the report)
--------------------------------------------------------
* Sun azimuth 315 deg, altitude 45 deg, constant. This is a drawing light, not
  an observation and not a solar-geometry computation.
* Elevation colour bands and the slope-to-rock blend are aesthetic.
* Water colour maps depth; it is not a spectral water index.

Physical quantities read from the saved run
------------------------------------------
``source-owner-left/right.npz``  real 10 km coarse terrain pages of the owning
                                 cores (identical in their overlap),
``generated-geometry.npz``       carved bed on the 50 m conforming mesh,
``dynamic-water-sediment-bed.npz`` per-interval node volume and node bed.

Run
---
    python tools/render_remote_sensing.py \\
        --run .scratch/cross-region-tributary/real-world-run-03 \\
        --output .scratch/cross-region-tributary/real-world-run-03/remote-sensing
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib.colors import LightSource
from matplotlib.patches import Rectangle

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

SUN_AZIMUTH_DEG = 315.0
SUN_ALTITUDE_DEG = 45.0
WATER_MIN_DEPTH_M = 0.005
DECLARATION = "SYNTHETIC RENDER - NOT SATELLITE OBSERVATION"

# Elevation -> base surface colour. Aesthetic, not radiometric.
ELEVATION_BANDS = (
    (-3000.0, (0.10, 0.14, 0.15)),
    (-200.0, (0.13, 0.19, 0.17)),
    (0.0, (0.20, 0.27, 0.17)),
    (250.0, (0.23, 0.33, 0.18)),
    (700.0, (0.34, 0.42, 0.23)),
    (1200.0, (0.48, 0.45, 0.33)),
    (1900.0, (0.61, 0.58, 0.54)),
    (2600.0, (0.86, 0.89, 0.92)),
    (4000.0, (0.97, 0.98, 1.00)),
)
ROCK_RGB = np.array((0.54, 0.52, 0.48))
SHALLOW_WATER_RGB = np.array((0.42, 0.70, 0.76))
DEEP_WATER_RGB = np.array((0.05, 0.20, 0.40))
LAKE_RGB = np.array((0.04, 0.14, 0.30))


def grid_axes(origin, spacing, shape):
    """Cell-centre world coordinates of a regular page."""
    spacing = float(spacing)
    return (float(origin[0]) + np.arange(int(shape[1])) * spacing,
            float(origin[1]) + np.arange(int(shape[0])) * spacing)


def bilinear(values, gx, gz, xs, zs):
    """Bilinear sample of a regular page onto world cells (edge-clamped)."""
    values = np.asarray(values, np.float64)
    if values.shape != (len(gz), len(gx)):
        raise ValueError("page shape and axes disagree")
    X, Z = np.meshgrid(np.asarray(xs, np.float64), np.asarray(zs, np.float64))
    sx = (gx[-1] - gx[0]) / (len(gx) - 1)
    sz = (gz[-1] - gz[0]) / (len(gz) - 1)
    if sx <= 0 or sz <= 0:
        raise ValueError("non-increasing page axes")
    fx = np.clip((X - gx[0]) / sx, 0.0, len(gx) - 1.0 - 1e-9)
    fz = np.clip((Z - gz[0]) / sz, 0.0, len(gz) - 1.0 - 1e-9)
    i0 = np.floor(fx).astype(np.int64)
    j0 = np.floor(fz).astype(np.int64)
    tx = fx - i0
    tz = fz - j0
    i1 = np.minimum(i0 + 1, len(gx) - 1)
    j1 = np.minimum(j0 + 1, len(gz) - 1)
    return (values[j0, i0] * (1.0 - tx) * (1.0 - tz)
            + values[j0, i1] * tx * (1.0 - tz)
            + values[j1, i0] * (1.0 - tx) * tz
            + values[j1, i1] * tx * tz)


def _coarse_spacing(run_dir):
    """Declared coarse cell size, from the run's own source selection."""
    path = Path(run_dir) / "source-selection.json"
    if path.exists():
        selection = json.loads(path.read_text(encoding="utf-8"))
        if "coarse_terrain_spacing_m" in selection:
            return float(selection["coarse_terrain_spacing_m"])
    return 10000.0


def terrain_window(run_dir, xs, zs):
    """Real coarse terrain, either one shared page or two owning pages."""
    run_dir = Path(run_dir)
    single = run_dir / "source-terrain-and-forcing.npz"
    if single.exists():
        page = np.load(single)
        if "height_m" in page.files:
            spacing = _coarse_spacing(run_dir)
            gx, gz = grid_axes(page["origin_xz_m"], spacing, page["height_m"].shape)
            return bilinear(page["height_m"], gx, gz, xs, zs), spacing, None
    left = np.load(run_dir / "source-owner-left.npz")
    right = np.load(run_dir / "source-owner-right.npz")
    lx, lz = grid_axes(left["origin_xz_m"], left["spacing_m"], left["height_m"].shape)
    rx, rz = grid_axes(right["origin_xz_m"], right["spacing_m"], right["height_m"].shape)
    hl = bilinear(left["height_m"], lx, lz, xs, zs)
    hr = bilinear(right["height_m"], rx, rz, xs, zs)
    boundary = float(right["core_origin_xz_m"][0])
    height = np.where(np.asarray(xs)[None, :] < boundary, hl, hr)
    return height, float(left["spacing_m"]), boundary


def carved_bed(run_dir, xs, zs, chunk_rows=256, frame=None):
    """Rasterise the saved conforming mesh bed; also return its triangle mask.

    Interpolation runs in row blocks: a wide window over a 90-thousand-vertex
    mesh otherwise materialises several million-element temporaries at once.

    A **dynamic** bed is used when the run wrote `bed-change-field.npz` (the
    full-grid coupling does, with the final mesh bed and the per-vertex change).
    `frame="final"` rasterises the final bed, `frame="initial"` the carve, and
    `frame="change"` the change field; without that file the static
    `generated-geometry.bed_elevation_m` carve is rasterised exactly as before,
    so every existing run renders byte-identically.
    """
    run_dir = Path(run_dir)
    page = np.load(run_dir / "generated-geometry.npz")
    try:
        bed_values = np.array(page["bed_elevation_m"], np.float64)
        vertices = np.array(page["vertices_xz_m"], np.float64)
        triangle_index = np.array(page["triangles"], np.int64)
    finally:
        # Release the file handle: Windows will not delete a directory whose npz
        # is still open, which broke temp-directory tests.
        page.close()
    field_path = run_dir / "bed-change-field.npz"
    if frame in ("final", "initial", "change"):
        if not field_path.exists():
            raise ValueError("frame=%r needs bed-change-field.npz; this run has a static carve"
                             % (frame,))
        with np.load(field_path) as field:
            bed_values = np.array({"final": field["final_bed_m"],
                                   "initial": field["initial_bed_m"],
                                   "change": field["bed_change_m"]}[frame], np.float64)
    triangles = mtri.Triangulation(vertices[:, 0], vertices[:, 1], triangle_index)
    interpolator = mtri.LinearTriInterpolator(triangles, bed_values)
    xs = np.asarray(xs, np.float64)
    zs = np.asarray(zs, np.float64)
    values = np.empty((len(zs), len(xs)), np.float64)
    mask = np.empty((len(zs), len(xs)), bool)
    for start in range(0, len(zs), chunk_rows):
        stop = min(start + chunk_rows, len(zs))
        X, Z = np.meshgrid(xs, zs[start:stop])
        block = interpolator(X, Z)
        mask[start:stop] = np.ma.getmaskarray(block)
        values[start:stop] = block.filled(np.nan)
    summary = {"vertices_xz_m": vertices, "triangles": triangle_index,
               "bed_elevation_m": bed_values}
    return values, mask, summary


def node_state(run_dir, frame):
    """Per-node water depth and free surface for one saved interval."""
    dynamic = np.load(Path(run_dir) / "dynamic-water-sediment-bed.npz")
    geometry = np.load(Path(run_dir) / "generated-geometry.npz")
    width = np.asarray(geometry["width_m"], np.float64)
    area = np.asarray(dynamic["material_area_m2"], np.float64)
    if np.any(width <= 0.0) or np.any(area <= 0.0):
        raise ValueError("nonpositive width or material area")
    control_length = area / width
    volume = np.asarray(dynamic["water_volume_m3"][frame], np.float64)
    bed = np.asarray(dynamic["node_bed_m"][frame], np.float64)
    depth = volume / (width * control_length)
    return {
        "node_xz_m": np.asarray(geometry["node_xz_m"], np.float64),
        "receiver": np.asarray(geometry["receiver"], np.int64),
        "bed_m": bed,
        "depth_m": depth,
        "stage_m": bed + depth,
        "width_m": width,
        "time_seconds": float(dynamic["time_seconds"][frame]),
        "volume_m3": volume,
        "control_length_m": control_length,
    }


def stage_field(xs, zs, state, chunk_rows=192):
    """Free surface and half-width along the reach, as functions of position.

    The free surface is piecewise linear between nodes, which is the usual
    gradually-varied approximation at this resolution. The stage is only
    meaningful inside the declared channel width: outside it there is no water
    body, however low the surrounding ground happens to be. Depth at a pixel is
    then ``stage - carved bed``, so the water edge follows the carved
    cross-section instead of a painted ribbon.
    """
    xs = np.asarray(xs, np.float64)
    zs = np.asarray(zs, np.float64)
    xz = state["node_xz_m"]
    receiver = state["receiver"]
    stage = state["stage_m"]
    half_width = 0.5 * np.asarray(state["width_m"], np.float64)
    node_depth = np.asarray(state["depth_m"], np.float64)
    shape = (len(zs), len(xs))
    best = np.empty(shape, np.float64)
    surface = np.empty(shape, np.float64)
    half = np.empty(shape, np.float64)
    along = np.empty(shape, np.float64)
    # Row blocks keep a 37-node reach from materialising a dozen multi-million
    # element temporaries per segment at once.
    for start in range(0, shape[0], chunk_rows):
        stop = min(start + chunk_rows, shape[0])
        X, Z = np.meshgrid(xs, zs[start:stop])
        block_best = np.full(X.shape, np.inf)
        block_surface = np.full(X.shape, np.nan)
        block_half = np.full(X.shape, np.nan)
        block_along = np.full(X.shape, np.nan)
        for donor in range(len(xz)):
            target = int(receiver[donor])
            if target < 0:
                continue
            p0 = xz[donor]
            p1 = xz[target]
            segment = p1 - p0
            squared = float(segment @ segment)
            if squared <= 0.0:
                raise ValueError("zero-length reach segment")
            t_raw = ((X - p0[0]) * segment[0] + (Z - p0[1]) * segment[1]) / squared
            t = np.clip(t_raw, 0.0, 1.0)
            px = p0[0] + t * segment[0]
            pz = p0[1] + t * segment[1]
            # The stage is defined between nodes only. Beyond a terminal node the
            # carved bed keeps sloping, but no water body has been computed there,
            # so that extension must stay dry rather than inherit the last stage.
            distance = np.where((t_raw >= 0.0) & (t_raw <= 1.0),
                                np.hypot(X - px, Z - pz), np.inf)
            take = distance < block_best
            block_best = np.where(take, distance, block_best)
            block_surface = np.where(take, stage[donor] * (1.0 - t) + stage[target] * t,
                                     block_surface)
            block_half = np.where(take, half_width[donor] * (1.0 - t) + half_width[target] * t,
                                  block_half)
            block_along = np.where(take, node_depth[donor] * (1.0 - t) + node_depth[target] * t,
                                   block_along)
        best[start:stop] = block_best
        surface[start:stop] = block_surface
        half[start:stop] = block_half
        along[start:stop] = block_along
    return surface, best, half, along


def surface_rgb(height, spacing, vertical_exaggeration=1.0):
    """Natural-colour style surface with a declared constant light."""
    bands = np.array([band[0] for band in ELEVATION_BANDS], np.float64)
    colours = np.array([band[1] for band in ELEVATION_BANDS], np.float64)
    rgb = np.empty(height.shape + (3,), np.float64)
    for channel in range(3):
        rgb[..., channel] = np.interp(height, bands, colours[:, channel])
    dz_dx, dz_dz = np.gradient(height, spacing, spacing)
    slope = np.hypot(dz_dx, dz_dz)
    rock = np.clip((slope - 0.25) / 0.9, 0.0, 1.0)[..., None]
    rgb = rgb * (1.0 - rock) + ROCK_RGB * rock
    shade = LightSource(azdeg=SUN_AZIMUTH_DEG, altdeg=SUN_ALTITUDE_DEG).hillshade(
        height, vert_exag=vertical_exaggeration, dx=spacing, dy=spacing)
    shade = 0.45 + 0.75 * shade
    return np.clip(rgb * shade[..., None], 0.0, 1.0)


def false_colour_rgb(height, spacing, wet):
    """Near-infrared style false colour: vegetation red, bare ground cyan."""
    dz_dx, dz_dz = np.gradient(height, spacing, spacing)
    slope = np.hypot(dz_dx, dz_dz)
    vegetation = np.clip(1.0 - slope / 0.7, 0.0, 1.0) * np.clip((2100.0 - height) / 1600.0, 0.0, 1.0)
    snow = np.clip((height - 2100.0) / 700.0, 0.0, 1.0)
    bare = np.clip(1.0 - vegetation - snow, 0.0, 1.0)
    rgb = (vegetation[..., None] * np.array((0.72, 0.12, 0.16))
           + bare[..., None] * np.array((0.55, 0.62, 0.64))
           + snow[..., None] * np.array((0.95, 0.96, 0.98)))
    shade = LightSource(azdeg=SUN_AZIMUTH_DEG, altdeg=SUN_ALTITUDE_DEG).hillshade(
        height, vert_exag=1.0, dx=spacing, dy=spacing)
    rgb = rgb * (0.55 + 0.65 * shade)[..., None]
    rgb = np.where(wet[..., None], np.array((0.02, 0.03, 0.10)), rgb)
    return np.clip(rgb, 0.0, 1.0)


def water_rgb(depth):
    """Depth tint for wetted pixels (aesthetic, not a spectral index)."""
    span = np.clip((depth - 0.02) / 0.45, 0.0, 1.0)[..., None]
    return SHALLOW_WATER_RGB * (1.0 - span) + DEEP_WATER_RGB * span


def lake_state(run_dir, time_seconds):
    """Saved terminal lake stage, interpolated onto a reach interval.

    The lake is one native coarse cell with a vertical-wall V(h): the
    stored volume and stage come from ``lake-storage.npz``; nothing here
    invents water. Its covered area is the modelled cell, not a terrain flood
    line, so the picture must be labelled as such.
    """
    run_dir = Path(run_dir)
    definition_path = run_dir / "lake-definition.json"
    storage_path = run_dir / "lake-storage.npz"
    if not definition_path.exists() or not storage_path.exists():
        return None
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    storage = np.load(storage_path)
    if "time_edges_seconds" not in storage.files or "stage_m" not in storage.files:
        return None
    times = np.asarray(storage["time_edges_seconds"], np.float64)
    stage = float(np.interp(float(time_seconds), times,
                            np.asarray(storage["stage_m"], np.float64)))
    volume = float(np.interp(float(time_seconds), times,
                             np.asarray(storage["volume_m3"], np.float64)))
    surface = float(np.interp(float(time_seconds), times,
                              np.asarray(storage["surface_area_m2"], np.float64)))
    terminal = int(definition["terminal_node_index"])
    geometry = np.load(run_dir / "generated-geometry.npz")
    centre = np.asarray(geometry["node_xz_m"], np.float64)[terminal]
    cell_area = float(definition["lake"]["cell_area_m2"][0])
    bed = float(definition["lake"]["bed_elevation_m"][0])
    return {
        "centre_xz_m": centre,
        "half_size_m": 0.5 * float(np.sqrt(cell_area)),
        "cell_area_m2": cell_area,
        "stage_m": stage,
        "volume_m3": volume,
        "surface_area_m2": surface,
        "bed_m": bed,
        "depth_m": max(0.0, stage - bed),
        "sill_stage_m": float(storage["sill_stage_m"]),
        "terminal_node_index": terminal,
        "run_dir": str(run_dir),
    }


def floodplain_depth_state(run_dir, time_seconds):
    """Saved two-dimensional depth field, if this run produced one.

    The floodplain product stores ``depth_m[frame, row(z), column(x)]`` on a regular
    page with an explicit cell-centre origin. Reading it here keeps the renderer the
    single place that draws water; this function only samples the saved field onto
    the rendering grid and never invents water where the field is zero.
    """
    path = Path(run_dir) / "floodplain-depth-field.npz"
    if not path.exists():
        return None
    saved = np.load(path)
    if "depth_m" not in saved.files or "time_s" not in saved.files:
        return None
    sidecar = Path(run_dir) / "floodplain-depth-field.json"
    if sidecar.exists():
        spacing = float(json.loads(sidecar.read_text(encoding="utf-8"))["spacing_m"])
    elif "spacing_m" in saved.files:
        spacing = float(np.asarray(saved["spacing_m"]))
    else:
        raise ValueError("saved floodplain depth field declares no spacing")
    times = np.asarray(saved["time_s"], np.float64)
    frame = int(np.argmin(np.abs(times - float(time_seconds))))
    return {
        "depth_m": np.asarray(saved["depth_m"][frame], np.float64),
        "height_m": np.asarray(saved["height_m"], np.float64),
        "origin_xz_m": np.asarray(saved["origin_xz_m"], np.float64),
        "spacing_m": spacing,
        "time_seconds": float(times[frame]),
        "frame": frame,
        "frames_available": int(times.size),
        "run_dir": str(run_dir),
    }


def floodplain_mask_on(xs, zs, state):
    """Sample the saved depth page onto the rendering grid (zero outside the page)."""
    page = state["depth_m"]
    spacing = state["spacing_m"]
    gx = state["origin_xz_m"][0] + np.arange(page.shape[1]) * spacing
    gz = state["origin_xz_m"][1] + np.arange(page.shape[0]) * spacing
    X, Z = np.meshgrid(np.asarray(xs, np.float64), np.asarray(zs, np.float64))
    inside = ((X >= gx[0] - spacing / 2.) & (X <= gx[-1] + spacing / 2.)
              & (Z >= gz[0] - spacing / 2.) & (Z <= gz[-1] + spacing / 2.))
    values = bilinear(page, gx, gz, np.asarray(xs, np.float64), np.asarray(zs, np.float64))
    return np.where(inside, np.maximum(values, 0.), 0.)


def lake_mask_on(xs, zs, lake):
    """Boolean mask of the modelled lake cell, plus its uniform depth."""
    X, Z = np.meshgrid(np.asarray(xs, np.float64), np.asarray(zs, np.float64))
    inside = ((np.abs(X - lake["centre_xz_m"][0]) <= lake["half_size_m"])
              & (np.abs(Z - lake["centre_xz_m"][1]) <= lake["half_size_m"]))
    wet = inside & (lake["depth_m"] > WATER_MIN_DEPTH_M)
    return wet


def compose(run_dir, xs, zs, frame, *, false_colour=False, vertical_exaggeration=1.0,
            lake=None, floodplain=None, bed_frame=None):
    """Return RGB image, extent and diagnostics for one frame.

    ``bed_frame`` selects the bed surface: ``None`` draws the static carve in
    ``generated-geometry.npz`` (the historical behaviour), while ``"final"``,
    ``"initial"`` or ``"change"`` read ``bed-change-field.npz``. Callers that
    want the coupled bed pass ``"final"`` explicitly; nothing here assumes that
    file exists.
    """
    height, terrain_spacing, boundary = terrain_window(run_dir, xs, zs)
    bed_fine, mesh_mask, _ = carved_bed(run_dir, xs, zs, frame=bed_frame)
    bed = np.where(mesh_mask, height, bed_fine)
    state = node_state(run_dir, frame)
    if lake is not None:
        # Re-read the stored stage at this frame so a time series can show the
        # lake filling, not one frozen water level.
        lake = lake_state(lake["run_dir"], state["time_seconds"]) or lake
    surface, distance, half, along = stage_field(xs, zs, state)
    inside_channel = np.isfinite(half) & (distance <= half)
    valid = (~mesh_mask) & inside_channel
    # Depth is capped by the interval's own mean depth for that reach position.
    # Coasting the free surface over the coarse field can put water far deeper
    # than the census carries (neighbouring ground may sit below the stage); the
    # cap keeps the picture consistent with the solved volume instead of
    # inventing ponds the ledger never held.
    depth = np.where(valid, np.minimum(surface - bed, along), np.nan)
    wet = np.isfinite(depth) & (depth > WATER_MIN_DEPTH_M)
    spacing = float(xs[1] - xs[0])
    lake_wet = None
    floodplain_wet = None
    floodplain_state = None
    if lake is not None:
        lake_wet = lake_mask_on(xs, zs, lake)
        depth = np.where(lake_wet, lake["depth_m"], depth)
        wet = wet | lake_wet
    if floodplain is not None:
        # A saved two-dimensional field replaces the one-dimensional ribbon
        # wherever it has water: it is the solved depth, not a painted surface.
        floodplain_state = floodplain_depth_state(
            floodplain["run_dir"], state["time_seconds"]) or floodplain
        floodplain_depth = floodplain_mask_on(xs, zs, floodplain_state)
        floodplain_wet = floodplain_depth > WATER_MIN_DEPTH_M
        depth = np.where(floodplain_wet, floodplain_depth, depth)
        wet = wet | floodplain_wet
    if false_colour:
        rgb = false_colour_rgb(height, spacing, wet)
    else:
        rgb = surface_rgb(height, spacing, vertical_exaggeration)
        water = water_rgb(np.where(wet, depth, 0.0))
        edge = np.clip(depth / 0.03, 0.0, 1.0)[..., None]
        rgb = np.where(wet[..., None], rgb * (1.0 - edge) + water * edge, rgb)
        if lake_wet is not None and lake_wet.any():
            # The modelled lake is ~110 m deep in a single cell; the reach ramp
            # tops out at half a metre, so it gets its own deeper tint.
            rgb = np.where(lake_wet[..., None], LAKE_RGB, rgb)
    diagnostics = {
        "frame": int(frame),
        "time_seconds": state["time_seconds"],
        "wet_pixels": int(np.count_nonzero(wet)),
        "channel_pixels": int(np.count_nonzero(valid)),
        "max_depth_m": float(np.nanmax(np.where(wet, depth, 0.0))),
        "cap_applied": True,
        "node_depth_m": [float(value) for value in state["depth_m"]],
        "terrain_min_m": float(np.nanmin(height)),
        "terrain_max_m": float(np.nanmax(height)),
        "core_boundary_x_m": boundary,
        "terrain_source_spacing_m": terrain_spacing,
    }
    if lake is not None:
        diagnostics["lake"] = {
            "stage_m": lake["stage_m"],
            "volume_m3": lake["volume_m3"],
            "depth_m": lake["depth_m"],
            "sill_stage_m": lake["sill_stage_m"],
            "modelled_area_m2": lake["cell_area_m2"],
            "above_sill": lake["stage_m"] > lake["sill_stage_m"],
            "wet_pixels": int(np.count_nonzero(lake_wet)),
        }
    if floodplain_state is not None:
        diagnostics["floodplain"] = {
            "frame": floodplain_state["frame"],
            "frames_available": floodplain_state["frames_available"],
            "time_seconds": floodplain_state["time_seconds"],
            "spacing_m": floodplain_state["spacing_m"],
            "wet_pixels": int(np.count_nonzero(floodplain_wet)),
            "max_depth_m": float(np.max(floodplain_depth)),
            "note": "saved two-dimensional local-inertial depth sampled bilinearly; "
                    "not a painted surface and not an observation",
        }
    return rgb, diagnostics, height, bed, depth, wet, state


def _mesh_spacing(geometry):
    """Nominal node spacing of the saved conforming mesh."""
    unique = np.unique(np.round(np.asarray(geometry["vertices_xz_m"])[:, 0], 3))
    if unique.size < 2:
        return 0.0
    return float(np.median(np.diff(unique)))


def _extent(xs, zs):
    return [float(xs[0]), float(xs[-1]), float(zs[-1]), float(zs[0])]


def _annotate(ax, xs, zs, title, subtitle, extra_lines):
    span_x = float(xs[-1] - xs[0])
    span_z = float(zs[-1] - zs[0])
    ax.set_title(title, fontsize=13, pad=8)
    ax.set_xlabel("世界坐标 X (m)", fontsize=9)
    ax.set_ylabel("世界坐标 Z (m)", fontsize=9)
    ax.ticklabel_format(style="plain", useOffset=False)
    ax.tick_params(labelsize=7)
    bar = 10.0 ** np.floor(np.log10(span_x * 0.18))
    for factor in (1.0, 2.0, 5.0):
        if bar * factor <= span_x * 0.3:
            bar = bar * factor
    x0 = xs[0] + span_x * 0.05
    y0 = zs[-1] - span_z * 0.08
    ax.plot([x0, x0 + bar], [y0, y0], color="white", lw=4, solid_capstyle="butt")
    ax.plot([x0, x0 + bar], [y0, y0], color="black", lw=1.4, solid_capstyle="butt")
    ax.text(x0 + bar / 2.0, y0 - span_z * 0.035, "%.0f km" % (bar / 1000.0),
            color="white", ha="center", va="top", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.15", fc="black", alpha=0.45, lw=0))
    ax.annotate("N", xy=(xs[-1] - span_x * 0.07, zs[0] + span_z * 0.10),
                xytext=(xs[-1] - span_x * 0.07, zs[0] + span_z * 0.20),
                color="white", fontsize=12, ha="center",
                arrowprops=dict(facecolor="white", width=2.5, headwidth=9,
                                headlength=9, shrink=0.0))
    lines = list(extra_lines) + [DECLARATION]
    ax.text(0.012, 0.018, "\n".join(lines), transform=ax.transAxes,
            color="white", fontsize=7.5, va="bottom", ha="left",
            bbox=dict(boxstyle="round,pad=0.35", fc="black", alpha=0.55, lw=0))
    if subtitle:
        ax.text(0.012, 0.985, subtitle, transform=ax.transAxes, color="white",
                fontsize=8, va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.5, lw=0))


def _draw_overlays(ax, lake, truncated_edges):
    """Mark the modelled lake cell and the declared truncated upstream edges."""
    if lake is not None:
        cx, cz = float(lake["centre_xz_m"][0]), float(lake["centre_xz_m"][1])
        half = float(lake["half_size_m"])
        ax.add_patch(Rectangle((cx - half, cz - half), 2 * half, 2 * half, fill=False,
                               edgecolor="#9fd8ff", linewidth=1.1, linestyle=(0, (4, 3))))
        ax.annotate("内流湖泊\n单格竖壁 %.0f km²" % (lake["cell_area_m2"] / 1e6),
                    xy=(cx + half, cz), xytext=(cx + half * 1.25, cz + half * 1.15),
                    color="#cfe9ff", fontsize=8, ha="left", va="bottom",
                    arrowprops=dict(arrowstyle="-", color="#9fd8ff", lw=0.9),
                    bbox=dict(boxstyle="round,pad=0.25", fc="black", alpha=0.5, lw=0))
    for edge in truncated_edges or ():
        start = edge.get("from_xz_m")
        target = edge.get("to_xz_m")
        if not start or not target:
            continue
        ax.plot([target[0]], [target[1]], marker="x", markersize=7, mew=1.6,
                color="#ffd166")
        ax.annotate("裁剪上游 %.0f m³/s" % float(np.max(edge.get("q_m3_s", [0.0]))),
                    xy=(target[0], target[1]), xytext=(target[0] - 6000.0, target[1] - 9000.0),
                    color="#ffd166", fontsize=7, ha="center",
                    arrowprops=dict(arrowstyle="-", color="#ffd166", lw=0.8),
                    bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.45, lw=0))


def _draw_lake_gauge(ax, lake):
    """Small stage gauge: the lake area is fixed by the vertical-wall model.

    Covered area cannot grow when the stage rises half a metre inside a 110 m
    deep cell, so the filling is shown on an explicit gauge instead of faking
    a wider shoreline.
    """
    if lake is None:
        return
    bed = float(lake["bed_m"])
    sill = float(lake["sill_stage_m"])
    stage = float(lake["stage_m"])
    top = max(sill, stage) + max(sill - bed, 1.0) * 0.12
    span = top - bed
    x0, x1 = 0.90, 0.925

    def y(value):
        return 0.12 + (value - bed) / span * 0.42

    ax.plot([x0, x0], [y(bed), y(top)], transform=ax.transAxes,
            color="white", lw=0.9, alpha=0.75)
    ax.fill_between([x0, x1], [y(bed), y(bed)], [y(stage), y(stage)],
                    transform=ax.transAxes, color="#4aa3d8", alpha=0.85, lw=0)
    ax.plot([x0 - 0.010, x1], [y(sill), y(sill)], transform=ax.transAxes,
            color="#ffd166", lw=1.2)
    ax.text(x0 - 0.014, y(sill), "鞍口 %.1f m" % sill, transform=ax.transAxes,
            color="#ffd166", fontsize=7, ha="right", va="center")
    ax.text(x0 - 0.014, y(stage), "%.2f m" % stage, transform=ax.transAxes,
            color="#d8ecff", fontsize=7.5, ha="right", va="center")


def _save(fig, path, dpi=200):
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    image = plt.imread(path)
    if image.size == 0 or float(np.nanstd(image[..., :3])) < 1e-6:
        raise RuntimeError("blank image produced: " + str(path))
    return Path(path).stat().st_size


def _frame_of_peak(run_dir):
    dynamic = np.load(Path(run_dir) / "dynamic-water-sediment-bed.npz")
    totals = np.asarray(dynamic["water_volume_m3"], np.float64).sum(axis=1)
    return int(np.argmax(totals))


def _flood_frame(run_dir):
    """Frame where the stored lake first sits above its primary sill."""
    definition_path = Path(run_dir) / "lake-definition.json"
    storage_path = Path(run_dir) / "lake-storage.npz"
    if not definition_path.exists() or not storage_path.exists():
        return None
    storage = np.load(storage_path)
    stage = np.asarray(storage["stage_m"], np.float64)
    times = np.asarray(storage["time_edges_seconds"], np.float64)
    sill = float(storage["sill_stage_m"])
    above = np.flatnonzero(stage > sill)
    if above.size == 0:
        return None
    spill_time = float(times[int(above[0])])
    dynamic = np.load(Path(run_dir) / "dynamic-water-sediment-bed.npz")
    reach_times = np.asarray(dynamic["time_seconds"], np.float64)
    return int(np.argmin(np.abs(reach_times - spill_time)))


def render(run_dir, output_dir, *, world_seed, regional_km=120.0, reach_km=28.0,
           lake=None, truncated_edges=(), reach_z_km=None, centre_xz_m=None,
           floodplain=False, bed_frame="auto"):
    """Render the regional context, the reach close-up and a three-frame series."""
    run_dir = Path(run_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with np.load(run_dir / "generated-geometry.npz") as page:
        centres = np.array(page["node_xz_m"], np.float64)
        pl_spacing = _mesh_spacing(page)
    centre_x = float(centres[:, 0].mean()) if centre_xz_m is None else float(centre_xz_m[0])
    centre_z = float(centres[:, 1].mean()) if centre_xz_m is None else float(centre_xz_m[1])
    peak = _frame_of_peak(run_dir)
    dynamic = np.load(run_dir / "dynamic-water-sediment-bed.npz")
    last = len(np.asarray(dynamic["time_seconds"])) - 1
    floodplain_state = ({"run_dir": str(run_dir)} if floodplain else None)
    # "auto" upgrades to the coupled bed only where the run actually wrote one, so
    # runs without bed-change-field.npz keep the historical static carve.
    if bed_frame == "auto":
        bed_frame = "final" if (run_dir / "bed-change-field.npz").exists() else None
    elif bed_frame not in (None, "initial", "final", "change"):
        raise ValueError("unknown bed_frame %r" % (bed_frame,))

    written = {}
    diagnostics = {}

    # --- regional context: broad overview, coarse field interpolated ----------
    half = regional_km * 500.0
    # Pixel size grows with the window so a wide basin does not allocate a
    # multi-million-pixel frame that buys no visible detail.
    pixel_r = max(60.0, regional_km * 1000.0 / 1600.0)
    xs_r = np.arange(centre_x - half, centre_x + half + pixel_r, pixel_r)
    zs_r = np.arange(centre_z - half * 0.72, centre_z + half * 0.72 + pixel_r, pixel_r)
    rgb, diag, _, _, _, wet, _ = compose(run_dir, xs_r, zs_r, peak, lake=lake,
                                         floodplain=floodplain_state, bed_frame=bed_frame)
    fig, ax = plt.subplots(figsize=(13.5, 9.0), facecolor="#0d1117")
    ax.imshow(rgb, extent=[xs_r[0], xs_r[-1], zs_r[-1], zs_r[0]], origin="upper",
              interpolation="bilinear")
    ax.set_facecolor("#0d1117")
    _annotate(ax, xs_r, zs_r,
              "区域正射影像 · 流域背景与主支流汇流",
              "区域窗口 %.0f km；10 km 粗网双线性插值，非 TD 细部" % (2 * half / 1000.0),
              ["world_seed=%d" % world_seed,
               "t = %.0f s（洪峰帧）" % diag["time_seconds"],
               "太阳方位 %.0f° / 高度角 %.0f°（固定绘图光照）"
               % (SUN_AZIMUTH_DEG, SUN_ALTITUDE_DEG)])
    _draw_overlays(ax, lake, truncated_edges)
    written["regional_true_color"] = str(
        output / "regional-true-color.png")
    _save(fig, written["regional_true_color"])
    diagnostics["regional"] = diag

    # --- reach close-up: carved bed and water surface -------------------------
    half_x = reach_km * 500.0
    half_z = (reach_km if reach_z_km is None else reach_z_km) * 500.0 * 0.55
    pixel_c = max(40.0, reach_km * 1000.0 / 1400.0)
    xs_c = np.arange(centre_x - half_x, centre_x + half_x + pixel_c, pixel_c)
    zs_c = np.arange(centre_z - half_z, centre_z + half_z + pixel_c, pixel_c)
    for label, false_colour, exaggeration, suffix in (
            ("真彩色", False, 6.0, "reach-true-color.png"),
            ("假彩色（近红外风格）", True, 6.0, "reach-false-color.png")):
        rgb, diag, _, _, _, wet, state = compose(
            run_dir, xs_c, zs_c, peak, false_colour=false_colour,
            vertical_exaggeration=exaggeration, lake=lake, floodplain=floodplain_state,
            bed_frame=bed_frame)
        fig, ax = plt.subplots(figsize=(13.5, 8.4), facecolor="#0d1117")
        ax.imshow(rgb, extent=[xs_c[0], xs_c[-1], zs_c[-1], zs_c[0]], origin="upper",
                  interpolation="nearest")
        ax.set_facecolor("#0d1117")
        _annotate(ax, xs_c, zs_c,
                  "近景正射影像 · 切槽河道与水面（%s）" % label,
                  "切槽床 %.0f m 网格；水面由节点水位与切槽断面求交" % pl_spacing,
                  ["world_seed=%d" % world_seed,
                   "t = %.0f s（洪峰帧）" % diag["time_seconds"],
                   "节点水深 %.3f–%.3f m（%d 节点）"
                   % (min(diag["node_depth_m"]), max(diag["node_depth_m"]),
                      len(diag["node_depth_m"])),
                   "垂直夸张 x%.0f（仅地形明暗）" % exaggeration])
        _draw_overlays(ax, lake, truncated_edges)
        written[suffix.replace(".png", "")] = str(output / suffix)
        _save(fig, written[suffix.replace(".png", "")])
        diagnostics[suffix.replace(".png", "")] = diag

    # --- three-frame series ---------------------------------------------------
    times = np.asarray(dynamic["time_seconds"], np.float64)
    flood = _flood_frame(run_dir) if lake is not None else None
    frames = [(0, "t = 0 s · 初始")]
    if flood is not None and 0 < flood < peak:
        frames.append((flood, "t = %.0f s · 湖泊越鞍口" % float(times[flood])))
    frames.append((peak, "t = %.0f s · 洪峰" % float(times[peak])))
    frames.append((last, "t = %.0f s · 终态" % float(times[last])))
    fig, axes = plt.subplots(1, len(frames), figsize=(6.4 * len(frames), 6.6),
                            facecolor="#0d1117", squeeze=False)
    axes = axes[0]
    series_diag = []
    for ax, (frame, label) in zip(axes, frames):
        rgb, diag, _, _, _, wet, _ = compose(run_dir, xs_c, zs_c, frame,
                                             vertical_exaggeration=6.0, lake=lake,
                                             floodplain=floodplain_state,
                                             bed_frame=bed_frame)
        ax.imshow(rgb, extent=[xs_c[0], xs_c[-1], zs_c[-1], zs_c[0]], origin="upper",
                  interpolation="nearest")
        ax.set_facecolor("#0d1117")
        lake_note = ""
        if lake is not None and "lake" in diag:
            lake_note = "\n湖水位 %.2f m%s" % (
                diag["lake"]["stage_m"], "（溢流）" if diag["lake"]["above_sill"] else "")
        ax.set_title("%s%s\n湿像素 %d" % (label, lake_note, diag["wet_pixels"]),
                     fontsize=10, pad=6)
        _draw_lake_gauge(ax, lake_state(lake["run_dir"], float(times[frame])) if lake else None)
        ax.set_xticks([])
        ax.set_yticks([])
        series_diag.append(diag)
    fig.suptitle("水流演进 · 合成正射影像（非卫星观测）", fontsize=14, y=0.98)
    fig.text(0.5, 0.02, "world_seed=%d · 切槽床 50 m · 水面按节点水位与断面求交 · %s"
             % (world_seed, DECLARATION), ha="center", fontsize=9, color="#c9d4dc")
    written["time_series"] = str(output / "reach-time-series.png")
    _save(fig, written["time_series"], dpi=150)
    diagnostics["time_series"] = series_diag

    report = {
        "declaration": DECLARATION,
        "world_seed": int(world_seed),
        "source_run": str(run_dir),
        "peak_frame": peak,
        "regional_window_km": 2 * half / 1000.0,
        "reach_window_km": 2 * half_x / 1000.0,
        "pixel_size_m": {"regional": float(xs_r[1] - xs_r[0]),
                         "reach": float(xs_c[1] - xs_c[0])},
        "rendering": {
            "sun_azimuth_deg": SUN_AZIMUTH_DEG,
            "sun_altitude_deg": SUN_ALTITUDE_DEG,
            "sun_note": "constant drawing light; not an observation or solar-geometry calculation",
            "vertical_exaggeration": {"regional_true_color": 1.0,
                                      "reach_true_color": 6.0},
            "elevation_bands": [[float(band[0]), list(band[1])]
                                for band in ELEVATION_BANDS],
            "rock_blend": {"reference_rgb": ROCK_RGB.tolist(),
                           "slope_start": 0.25, "slope_full": 1.15},
            "water": {"min_depth_m": WATER_MIN_DEPTH_M,
                      "shallow_rgb": SHALLOW_WATER_RGB.tolist(),
                      "deep_rgb": DEEP_WATER_RGB.tolist(),
                      "depth_ramp_m": [0.02, 0.47],
                      "note": "depth tint is aesthetic, not a spectral index"},
            "terrain_source": "10 km coarse owning-core pages, bilinear interpolation",
            "bed_source": "saved conforming carved mesh (%.0f m), linear triangle interpolation" % pl_spacing,
            "water_source": "node stage = node bed + volume/(width*control length); "
                            "linearly interpolated along reach segments; depth = stage - carved bed",
        },
        "physical_quantities_rendered": [
            "coarse terrain height of the saved source window",
            "carved bed elevation of the saved conforming mesh",
            "per-interval node water volume, node bed and node width",
        ] + (["terminal lake stage, volume and modelled cell area"] if lake else [])
        + (["saved two-dimensional local-inertial floodplain depth field"]
           if floodplain else []),
        "not_rendered": [
            "no dynamic update of the full conforming mesh (node bed only)",
            "no TD detail terrain",
            "no sediment texture on the surface",
        ] + (["no two-dimensional floodplain inundation map around the lake; "
              "the lake is drawn as its modelled single cell, not a terrain flood line"]
             if lake else ["no lake, backwater or two-dimensional floodplain state"]),
        "lake": ({"centre_xz_m": [float(v) for v in lake["centre_xz_m"]],
                  "modelled_cell_area_m2": lake["cell_area_m2"],
                  "bed_m": lake["bed_m"],
                  "sill_stage_m": lake["sill_stage_m"],
                  "vertical_wall": True,
                  "note": "stage from lake-storage.npz; covered area is the modelled "
                          "cell, not a terrain flood line"} if lake else None),
        "truncated_upstream_edges": [
            {"from_xz_m": edge.get("from_xz_m"), "to_xz_m": edge.get("to_xz_m"),
             "omitted_cell_count": edge.get("omitted_cell_count"),
             "peak_q_m3_s": float(np.max(edge.get("q_m3_s", [0.0]))),
             "note": "declared boundary scenario, not a natural source"}
            for edge in (truncated_edges or ())],
        "diagnostics": diagnostics,
        "files": written,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    return report


def _truncated_edges(run_dir):
    """Declared truncated upstream boundary scenarios of this run, if any."""
    path = Path(run_dir) / "source-selection.json"
    if not path.exists():
        return []
    selection = json.loads(path.read_text(encoding="utf-8"))
    return list(selection.get("truncated_upstream_edges") or [])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--world-seed", type=int, default=20261020)
    parser.add_argument("--regional-km", type=float, default=120.0)
    parser.add_argument("--reach-km", type=float, default=28.0)
    parser.add_argument("--reach-z-km", type=float, default=None)
    parser.add_argument("--centre", nargs=2, type=float, default=None, metavar=("X", "Z"))
    parser.add_argument("--floodplain", action="store_true",
                        help="also draw the saved two-dimensional floodplain depth field "
                             "(floodplain-depth-field.npz) when the run produced one")
    parser.add_argument("--bed-frame", default="auto",
                        choices=("auto", "initial", "final", "change"),
                        help="bed surface: auto uses bed-change-field.npz when present "
                             "and the static carve otherwise")
    args = parser.parse_args(argv)
    run_dir = Path(args.run)
    dynamic = np.load(run_dir / "dynamic-water-sediment-bed.npz")
    times = np.asarray(dynamic["time_seconds"], np.float64)
    peak = int(np.argmax(np.asarray(dynamic["water_volume_m3"], np.float64).sum(axis=1)))
    lake = lake_state(run_dir, float(times[peak]))
    report = render(args.run, args.output, world_seed=args.world_seed,
                    regional_km=args.regional_km, reach_km=args.reach_km,
                    lake=lake, truncated_edges=_truncated_edges(run_dir),
                    reach_z_km=args.reach_z_km, centre_xz_m=args.centre,
                    floodplain=args.floodplain, bed_frame=args.bed_frame)
    summary = {name: Path(path).stat().st_size for name, path in report["files"].items()}
    print(json.dumps(summary, indent=2))
    print(json.dumps(report["diagnostics"]["reach-true-color"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
