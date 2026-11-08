"""Single source of truth for offline terrain-map styling.

Every terrain figure in this repository draws the *same* physical hillshade, the same
hypsometric ramps and the same map furniture, so that two figures can be compared by eye
without re-learning the legend.  Before this module the six-stop relief ramp existed as
three verbatim copies under ``tools/`` and the land/ocean ramp as nine further copies; new
renderers import from here instead of adding a tenth.

What this module is *not*: nothing here measures anything.  Band edges, colour stops,
hillshade weight and the sea-level datum are **declared cartographic style**, not derived
quantities, and no function in this module certifies a terrain, a river or an outlet.  Any
figure built on it inherits that status.

Layering note: ``tools/compare_hydrology_projection_naturalness.fixed_hillshade`` and the
inline ramps in the delta review tools are the historical copies of the same recipes.  They
are deliberately left byte-identical because their PNG outputs sit inside ``verification/``
as evidence; migrating them is a separate, explicitly reviewed change.
"""

import numpy as np

# ---------------------------------------------------------------------------------
# Declared style constants.  Changing any of these changes what every figure looks
# like, so they are versioned by the module docstring rather than by a schema constant.
# ---------------------------------------------------------------------------------

#: Six-stop hypsometric-tint ramp, verbatim from the three existing preview tools.
RELIEF_COLORS = ("#123a9b", "#00a8d5", "#27bb72", "#f3e85b", "#ef9a33", "#cb2d32")

#: Land ramp used by the saved river-mouth geography renderer.
LAND_COLORS = ("#b5c982", "#76995c", "#9a9d71", "#d3d5ce", "#f7f7f3")

#: Ocean depth ramp, ordered shallow to deep.
OCEAN_COLORS = ("#b1e0e4", "#60b4d1", "#286aab", "#173f7f")

#: Ocean depth scale, metres below the declared sea-level datum.
OCEAN_DEPTH_LIMITS_M = (0.0, 35.0)

#: Declared hypsometric band edges, metres above the sea-level datum.  Open ended at the
#: top: everything at or above the last edge takes the last colour.
LAND_BANDS_M = (0.0, 50.0, 100.0, 200.0, 300.0, 500.0, 750.0, 1000.0, 1500.0, 2000.0,
                3000.0, 4000.0, 6000.0, 8000.0)

#: One colour per band, so ``len(BAND_COLORS) == len(LAND_BANDS_M) - 1``.
BAND_COLORS = ("#2f7d4f", "#48975a", "#6cae63", "#93c172", "#bcd07f", "#e0dc8a",
               "#e6c877", "#d9ae68", "#c3965f", "#a8825f", "#9c8570", "#cfc9c1",
               "#f4f3f0")

#: The existing ``(.55 + .65 * shade)`` blend, kept bit-for-bit so figures stay comparable.
HILLSHADE_BASE = 0.55
HILLSHADE_WEIGHT = 0.65

#: Sea-level datum for every map in this project.
SEA_LEVEL_M = 0.0

#: NW light in raster convention (z increases southward, so the light has negative x/z).
HILLSHADE_LIGHT = (-0.5, -0.5, float(np.sqrt(0.5)))


def physical_hillshade(field, spacing_m=30.0):
    """Normal/light cosine from real gradients, with no per-image contrast stretching.

    Per-image stretching would make two maps whose colourbars agree look different, which
    is exactly the failure this module exists to prevent.
    """
    field = np.asarray(field, np.float64)
    if field.ndim != 2:
        raise ValueError("hillshade input must be a 2-D height field")
    if not np.isfinite(field).all():
        raise ValueError("hillshade input must be finite")
    if not np.isfinite(spacing_m) or spacing_m <= 0.0:
        raise ValueError("hillshade spacing must be a positive number of metres")
    dz, dx = np.gradient(field, float(spacing_m))
    normal = np.stack((-dx, -dz, np.ones_like(field)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    return np.clip(normal @ np.asarray(HILLSHADE_LIGHT, np.float64), 0.0, 1.0)


def apply_hillshade(rgb, field, spacing_m=30.0):
    """Multiply a colour image by the declared relief-shading blend."""
    rgb = np.asarray(rgb, np.float64)
    if rgb.shape[:2] != np.shape(field):
        raise ValueError("colour image and height field must share a shape")
    shade = physical_hillshade(field, spacing_m)[..., None]
    return np.clip(rgb * (HILLSHADE_BASE + HILLSHADE_WEIGHT * shade), 0.0, 1.0)


def relief_colormap(name="declared-relief"):
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(name, list(RELIEF_COLORS))


def ocean_colormap(name="declared-ocean"):
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(name, list(OCEAN_COLORS))


def band_colors(band_edges=LAND_BANDS_M, colors=BAND_COLORS):
    """Validate the band declaration and return RGB rows, one per band."""
    from matplotlib.colors import to_rgb
    edges = validate_band_edges(band_edges)
    if len(colors) != len(edges) - 1:
        raise ValueError(
            f"band declaration is inconsistent: {len(edges)} edges need {len(edges) - 1} "
            f"colours, got {len(colors)}")
    return np.array([to_rgb(value) for value in colors], np.float64)


def validate_band_edges(band_edges=LAND_BANDS_M):
    values = np.asarray(band_edges, np.float64)
    if values.ndim != 1 or values.size < 2:
        raise ValueError("hypsometric bands need at least two edges")
    if not np.isfinite(values).all():
        raise ValueError("hypsometric band edges must be finite")
    if np.any(np.diff(values) <= 0.0):
        raise ValueError("hypsometric band edges must be strictly increasing")
    if values[0] != SEA_LEVEL_M:
        raise ValueError("the first hypsometric band edge must be the sea-level datum")
    return values


def continuous_relief_rgb(height, spacing_m, limits, *, ocean_mask=None, ocean_depth=None):
    """Remote-sensing style: continuous hypsometric tint under physical relief shading."""
    from matplotlib.colors import Normalize
    height = np.asarray(height, np.float64)
    low, high = (float(limits[0]), float(limits[1]))
    if not high > low:
        raise ValueError("elevation limits must increase")
    rgb = relief_colormap()(Normalize(low, high, clip=True)(height))[..., :3]
    if ocean_mask is not None:
        wet = np.asarray(ocean_mask, bool)
        if wet.any():
            depth = np.maximum(-height, 0.0) if ocean_depth is None else np.asarray(ocean_depth, np.float64)
            limits_m = OCEAN_DEPTH_LIMITS_M
            rgb[wet] = ocean_colormap()(Normalize(*limits_m, clip=True)(depth[wet]))[..., :3]
    return apply_hillshade(rgb, height, spacing_m)


def banded_relief_rgb(height, spacing_m, *, band_edges=LAND_BANDS_M, colors=BAND_COLORS,
                      ocean_mask=None, ocean_depth=None):
    """Topographic style: discrete hypsometric bands under the same relief shading."""
    from matplotlib.colors import Normalize
    height = np.asarray(height, np.float64)
    edges = validate_band_edges(band_edges)
    palette = band_colors(edges, colors)
    index = np.clip(np.searchsorted(edges, height, side="right") - 1, 0, len(palette) - 1)
    rgb = palette[index]
    wet = np.asarray(ocean_mask, bool) if ocean_mask is not None else ~(height >= SEA_LEVEL_M)
    if wet.any():
        depth = np.maximum(-height, 0.0) if ocean_depth is None else np.asarray(ocean_depth, np.float64)
        rgb[wet] = ocean_colormap()(Normalize(*OCEAN_DEPTH_LIMITS_M, clip=True)(depth[wet]))[..., :3]
    return apply_hillshade(rgb, height, spacing_m)


def _nice_125(target):
    """Largest 1/2/5 x 10^n value not exceeding ``target``."""
    if not np.isfinite(target) or target <= 0.0:
        raise ValueError("target must be a positive number of kilometres")
    exponent = int(np.floor(np.log10(target)))
    for factor in (5.0, 2.0, 1.0):
        candidate = factor * 10.0 ** exponent
        if candidate <= target:
            return candidate
    return 10.0 ** exponent


def nice_scale_length_km(span_km):
    """Largest 1/2/5 x 10^n scale-bar length that stays under a quarter of the map."""
    return _nice_125(float(span_km) / 4.0)


def nice_graticule_step_km(span_km, *, divisions=6.0):
    """Largest 1/2/5 x 10^n kilometre step that still yields about ``divisions`` lines.

    A fixed step cannot serve both a 38 km sheet and a 160 m chart: 10 km across a 0.16 km
    chart draws no grid at all while still being reported as one.  Deriving the step from the
    span keeps the frame meaningful, and callers may of course override it.
    """
    if not np.isfinite(divisions) or divisions <= 0.0:
        raise ValueError("divisions must be a positive number")
    return _nice_125(float(span_km) / float(divisions))


def format_scale_label(length_km):
    if length_km >= 1.0:
        return f"{length_km:g} km"
    return f"{length_km * 1000.0:g} m"


def screen_frame(axis):
    """Axes limits as ``(xmin, xmax, screen_bottom_y, screen_top_y, signed_span_y)``.

    Every map here is drawn with an **inverted** y axis (``z`` increases southward), so
    ``get_ylim()`` returns a larger first value than second and naively adding a fraction
    of ``abs(top - bottom)`` to ``bottom`` would place furniture outside the sheet.  The
    signed span makes the same formula correct for either orientation.
    """
    xmin, xmax = axis.get_xlim()
    ymin, ymax = axis.get_ylim()
    return float(xmin), float(xmax), float(ymin), float(ymax), float(ymax - ymin)


def draw_scale_bar(axis, length_km, *, label=None, fraction=0.06, zorder=20):
    """White-haloed bar anchored to the lower-left corner, with end ticks."""
    xmin, xmax, ymin, ymax, span_signed = screen_frame(axis)
    span = abs(span_signed)
    x = xmin + fraction * (xmax - xmin)
    z = ymin + 0.07 * span_signed
    tick = 0.012 * span
    axis.plot([x, x + length_km], [z, z], color="white", linewidth=7,
              solid_capstyle="butt", zorder=zorder)
    for start, stop in ((x, x), (x + length_km, x + length_km)):
        axis.plot([start, stop], [z - tick, z + tick], color="white", linewidth=7,
                  solid_capstyle="butt", zorder=zorder)
    axis.plot([x, x + length_km], [z, z], color="#172b35", linewidth=3,
              solid_capstyle="butt", zorder=zorder + 1)
    for start, stop in ((x, x), (x + length_km, x + length_km)):
        axis.plot([start, stop], [z - tick, z + tick], color="#172b35", linewidth=1.2,
                  solid_capstyle="butt", zorder=zorder + 2)
    axis.text(x + length_km / 2.0, z + 0.018 * span_signed,
              label or format_scale_label(length_km), ha="center", va="bottom", fontsize=9,
              bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 2},
              zorder=zorder + 3)


def draw_north_arrow(axis, *, fraction=0.055, zorder=20):
    """Raster north points towards decreasing z, which is the top of every figure here.

    Every map in this project uses the raster convention ``z`` increases southward, so the
    axes are always inverted and screen-up is *smaller* z.  Both the anchor and the arrow
    are computed from the signed y span, so the same code stays correct if a figure is ever
    drawn with a non-inverted axis.
    """
    xmin, xmax, ymin, _ymax, span_signed = screen_frame(axis)
    span = abs(span_signed)
    x = xmax - fraction * (xmax - xmin)
    tail_z = ymin + 0.10 * span_signed
    head_z = tail_z + 0.075 * span_signed
    axis.annotate("", xy=(x, head_z), xytext=(x, tail_z),
                  arrowprops={"facecolor": "#172b35", "edgecolor": "white", "width": 1.4,
                              "headwidth": 9.0, "headlength": 7.0}, zorder=zorder)
    axis.text(x, tail_z + 0.10 * span_signed, "N", ha="center", va="bottom", fontsize=10,
              bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 1},
              zorder=zorder + 1)


def draw_metre_graticule(axis, *, step_km, colour="#3d3d3d"):
    """Planar kilometre grid.  This is a coordinate frame, not a geographic graticule.

    Returns a record of what was actually drawn.  A step wider than the sheet still stamps
    the frame it happens to cross, so the counts -- not the requested step -- are what a
    caller should report; ``nice_graticule_step_km`` exists so the counts are never 0 or 1 by
    accident.
    """
    if not np.isfinite(step_km) or step_km <= 0.0:
        raise ValueError("graticule step must be a positive number of kilometres")
    xmin, xmax, ymin, ymax, _span_signed = screen_frame(axis)
    low, high = sorted((ymin, ymax))
    x_ticks = np.arange(np.ceil(xmin / step_km) * step_km, xmax + 1e-9, step_km)
    y_ticks = np.arange(np.ceil(low / step_km) * step_km, high + 1e-9, step_km)
    for value in x_ticks:
        axis.axvline(value, color=colour, linewidth=0.4, alpha=0.35, zorder=8)
        axis.annotate(f"{value:g}", xy=(value, ymin), xytext=(0, -10),
                      textcoords="offset points", ha="center", va="top", fontsize=7,
                      color="#172b35")
    for value in y_ticks:
        axis.axhline(value, color=colour, linewidth=0.4, alpha=0.35, zorder=8)
        axis.annotate(f"{value:g}", xy=(xmax, value), xytext=(4, 0),
                      textcoords="offset points", ha="left", va="center", fontsize=7,
                      color="#172b35")
    return {"kind": "planar_kilometre_grid", "step_km": float(step_km),
            "x_lines": int(x_ticks.size), "y_lines": int(y_ticks.size)}


def draw_declared_graticule(axis, *, origin_xz_m, metres_per_degree_east,
                            metres_per_degree_north, origin_degrees, step_degrees,
                            colour="#5a3d7a"):
    """Opt-in degree grid derived from an *explicitly declared* metres-per-degree value.

    This terrain is not on a sphere: upstream coordinates are unbounded tile pixels.  A
    degree grid is therefore only ever drawn when the caller states the conversion, and
    every figure using it must stamp ``declared_graticule`` in its provenance.  The
    function refuses to guess a conversion.
    """
    for value, name in ((metres_per_degree_east, "metres_per_degree_east"),
                        (metres_per_degree_north, "metres_per_degree_north")):
        if not np.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be an explicitly declared positive quantity")
    if step_degrees <= 0.0 or not np.isfinite(step_degrees):
        raise ValueError("declared graticule step must be a positive number of degrees")
    xmin, xmax, ymin, ymax, _span = screen_frame(axis)
    low, high = sorted((ymin, ymax))
    lon0, lat0 = float(origin_degrees[0]), float(origin_degrees[1])
    ox_km, oz_km = float(origin_xz_m[0]) / 1000.0, float(origin_xz_m[1]) / 1000.0
    east = metres_per_degree_east / 1000.0
    north = metres_per_degree_north / 1000.0
    # Longitude straight from the declared conversion.
    start = np.ceil((lon0 + (xmin - ox_km) / east) / step_degrees) * step_degrees
    for lon in np.arange(start, lon0 + (xmax - ox_km) / east + 1e-9, step_degrees):
        x = ox_km + (lon - lon0) * east
        axis.axvline(x, color=colour, linewidth=0.6, alpha=0.45, zorder=9)
        axis.annotate(f"{lon:.4g}\u00b0E*", xy=(x, ymin), xytext=(0, -10),
                      textcoords="offset points", ha="center", va="top", fontsize=7,
                      color=colour)
    # Latitude runs *against* z, because z increases southward: north is smaller z.
    offset_km = oz_km + lat0 * north
    start_lat = np.ceil((offset_km - high) / north / step_degrees) * step_degrees
    for lat in np.arange(start_lat, (offset_km - low) / north + 1e-9, step_degrees):
        z = offset_km - lat * north
        axis.axhline(z, color=colour, linewidth=0.6, alpha=0.45, zorder=9)
        axis.annotate(f"{lat:.4g}\u00b0N*", xy=(xmax, z), xytext=(4, 0),
                      textcoords="offset points", ha="left", va="center", fontsize=7,
                      color=colour)
    return {"kind": "declared_graticule_not_a_projection",
            "metres_per_degree_east": float(metres_per_degree_east),
            "metres_per_degree_north": float(metres_per_degree_north),
            "origin_degrees": [lon0, lat0], "step_degrees": float(step_degrees)}
