"""Declared stratigraphy: parallel dipping horizons and a vertical rock query.

Scope (G2 second card)
--------------------
One thing only: turn a **declared, finite** layer stack into world-anchored
geometry, and answer "which layer and which rock is at this (x, z, elevation)?".

* the stack is given by the caller (rock id, vertical thickness, source);
* horizons are **planes**, all with the same strike and dip, so a horizon is
  `h_k = H_k - tan(dip) * u` with `u` the along-dip horizontal coordinate;
* a fault is a **finite** piecewise-discontinuous offset inside a declared band;
* joints are a world-anchored plane family with a measured distance.

What this is NOT
----------------
* not a tectonic, subsidence or provenance reconstruction;
* no folds, unconformities, lenses or lateral facies change;
* no 2D noise rock copied downward: below the deepest horizon the answer is
  `unknown_no_source`, never the surface rock;
* no weathering, erosion, transport or inventory model;
* no default-world wiring, no file IO, no hashing.

Conventions
-----------
``x`` east, ``z`` south, ``[z, x]``. ``elev`` in metres, positive up.
``strike`` is an azimuth in degrees, north = 0, clockwise toward east, so the
*right-hand* dip direction is ``strike + 90``. All trigonometry converts degrees
to radians explicitly. Layer thickness is **vertical** thickness at the anchor
(field name ``vertical_thickness_m``), not true normal thickness; the two differ
by ``cos(dip)`` and must not be confused when a volume is claimed.

``dip`` must satisfy ``0 <= dip < 90``. At 90 degrees a horizon is a vertical
plane and cannot be written as a single-valued height field, so a vertical layer
is refused instead of approximated.
"""

from __future__ import annotations

import math

import numpy as np

from terrain_pipeline import td_lithology_field as _lithology


SCHEMA = "geology-strata-v1"
ALGORITHM = "declared-parallel-strata-v1"
FORMAT_VERSION = 1

#: Hard caps. A grid crossed with a layer stack is the expensive shape, so the
#: product gets its own ceiling instead of inheriting the flat cell budget.
MAX_STRATA_LAYERS = 64
MAX_POINTS = 8192
MAX_GRID_CELLS = 262_144
MAX_CELL_LAYER_VALUES = 1_000_000
MAX_FAULTS = 8
MAX_JOINT_SETS = 8

#: Above the top horizon / inside the stack / below the deepest horizon.
ABOVE_COLUMN = 0
INSIDE_STACK = 1
BELOW_COLUMN = 2
STATE_NAMES = {ABOVE_COLUMN: "above_column", INSIDE_STACK: "inside_stack",
               BELOW_COLUMN: "below_column"}

#: Fault band outcome per query point.
FAULT_NOT_DECLARED = "not_declared"
FAULT_OUTSIDE = "outside"
FAULT_APPLIED = "applied"

UNKNOWN_NO_SOURCE = "unknown_no_source"
PENDING = "pending"
DECLARED = "declared"

STOCK_PENDING = "pending_missing_footprint"
STOCK_DECLARED = "declared"

LIMITATIONS = (
    "layers are declared planes with one common strike and dip; no fold, "
    "unconformity, lens or lateral facies change is modelled",
    "layer thickness is VERTICAL thickness measured at the anchor (field "
    "vertical_thickness_m); normal thickness is vertical * cos(dip). With a "
    "horizontal projected footprint the volume is area * vertical thickness, and "
    "normal thickness * (area / cos(dip)) gives the same rock volume",
    "dip = 90 is refused: a vertical layer is not a single-valued height field",
    "a fault is a piecewise-discontinuous engineering offset inside a declared "
    "influence width; it is not a mechanical rupture model",
    "below the deepest horizon the rock is unknown_no_source; the surface rock is "
    "never copied downward",
    "no weathering, erosion or stock model here; a finite declared volume can be "
    "reported but it is not a soil or regolith inventory",
)


class StrataBudgetError(ValueError):
    """Raised before any array is allocated."""


def _finite(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(name + " must be finite")
    return result


def _positive(value, name):
    result = _finite(value, name)
    if result <= 0.0:
        raise ValueError(name + " must be positive")
    return result


def _dip(value, name):
    result = _finite(value, name)
    if not 0.0 <= result < 90.0:
        raise ValueError(
            "%s must satisfy 0 <= %s < 90; dip = 90 is a vertical plane and is "
            "refused rather than approximated" % (name, name))
    return result


def _strike(value):
    result = _finite(value, "strike_deg")
    if not 0.0 <= result < 360.0:
        raise ValueError("strike_deg must satisfy 0 <= strike < 360")
    return result


def _points(x_m, z_m):
    x = np.asarray(x_m, np.float64)
    z = np.asarray(z_m, np.float64)
    x, z = np.broadcast_arrays(x, z)
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("x_m and z_m must be finite absolute world metres")
    return x, z


def preflight(n_points, n_layers, *, with_horizons=False, point_mode=True):
    """Reject an oversized request before any array or layer container exists."""
    for value, name in ((n_points, "n_points"), (n_layers, "n_layers")):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise StrataBudgetError(name + " must be an integer")
    points = int(n_points)
    layers = int(n_layers)
    if points <= 0 or layers <= 0:
        raise StrataBudgetError("point and layer counts must be positive")
    if layers > MAX_STRATA_LAYERS:
        raise StrataBudgetError(
            "layer count %d exceeds %d" % (layers, MAX_STRATA_LAYERS))
    limit = MAX_POINTS if point_mode else MAX_GRID_CELLS
    if points > limit:
        raise StrataBudgetError(
            "%s count %d exceeds %d" % ("point" if point_mode else "cell", points, limit))
    horizon_values = points * (layers + 1)
    if with_horizons and horizon_values > MAX_CELL_LAYER_VALUES:
        raise StrataBudgetError(
            "horizon output %d values (points x layers+1) exceeds %d; query fewer "
            "points or ask for the layer index only" % (horizon_values, MAX_CELL_LAYER_VALUES))
    return {
        "n_points": points,
        "n_layers": layers,
        "with_horizons": bool(with_horizons),
        "horizon_values": horizon_values if with_horizons else 0,
        "max_strata_layers": MAX_STRATA_LAYERS,
        "max_points": MAX_POINTS,
        "max_grid_cells": MAX_GRID_CELLS,
        "max_cell_layer_values": MAX_CELL_LAYER_VALUES,
        "max_faults": MAX_FAULTS,
        "max_joint_sets": MAX_JOINT_SETS,
    }


# ---------------------------------------------------------------------------
# Declared stack
# ---------------------------------------------------------------------------
def normalize_stack(declaration):
    """Validate a declared layer stack; fill nothing, invent nothing."""
    if declaration is None:
        return {"status": UNKNOWN_NO_SOURCE,
                "reason": "no stratigraphy declared; a vertical query has no rock source"}
    if not isinstance(declaration, dict):
        raise ValueError("strata declaration must be a dict or None")
    source = declaration.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("strata declaration needs a non-empty 'source'")
    anchor = declaration.get("anchor_xz_m")
    anchor = np.asarray(anchor, np.float64)
    if anchor.shape != (2,) or not np.isfinite(anchor).all():
        raise ValueError("anchor_xz_m must be two finite coordinates")
    top = _finite(declaration.get("top_elevation_m"), "top_elevation_m")
    strike = _strike(declaration.get("strike_deg"))
    dip = _dip(declaration.get("dip_deg"), "dip_deg")
    layers = declaration.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("strata declaration needs a non-empty 'layers' list")
    if len(layers) > MAX_STRATA_LAYERS:
        raise ValueError("layer count exceeds %d" % (MAX_STRATA_LAYERS,))
    normalized = []
    cumulative = 0.0
    for position, entry in enumerate(layers):
        if not isinstance(entry, dict):
            raise ValueError("layer %d must be a dict" % (position,))
        rock_id = entry.get("rock_id")
        if rock_id not in _lithology.ROCK_POSITION:
            raise ValueError("layer %d has an unknown rock_id: %r" % (position, rock_id))
        thickness = _positive(entry.get("vertical_thickness_m"),
                              "layers[%d].vertical_thickness_m" % (position,))
        layer_source = entry.get("source")
        if not isinstance(layer_source, str) or not layer_source.strip():
            raise ValueError("layer %d needs a non-empty 'source'" % (position,))
        normalized.append({
            "rock_id": rock_id,
            "rock_index": int(_lithology.ROCK_POSITION[rock_id]),
            "vertical_thickness_m": thickness,
            "source": layer_source,
        })
        cumulative += thickness
    horizon_elevations = [top]
    for entry in normalized:
        horizon_elevations.append(horizon_elevations[-1] - entry["vertical_thickness_m"])
    return {
        "status": DECLARED,
        "source": source,
        "anchor_xz_m": [float(anchor[0]), float(anchor[1])],
        "top_elevation_m": top,
        "strike_deg": strike,
        "dip_deg": dip,
        "layer_count": len(normalized),
        "layers": normalized,
        "horizon_elevation_m": horizon_elevations,
        "total_vertical_thickness_m": cumulative,
        "thickness_kind": "vertical_at_anchor_not_normal",
        "synthetic_declared_stratigraphy": True,
        "measured_stratigraphy": False,
    }


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def _along_dip(stack, x, z):
    """Horizontal coordinate along the (right-hand) dip direction, in metres."""
    strike = math.radians(stack["strike_deg"])
    anchor_x, anchor_z = stack["anchor_xz_m"]
    return (x - anchor_x) * math.cos(strike) + (z - anchor_z) * math.sin(strike)


def horizons_at(x_m, z_m, stack, *, point_mode=True):
    """Elevation of every horizon at the given points, shape ``(L+1, ...)``.

    ``h_k = H_k - tan(dip) * u``; all horizons are parallel planes. The layout is
    ``[horizon, z, x]`` for a grid input, matching the repository convention.
    """
    if stack is None or stack.get("status") != DECLARED:
        raise ValueError("a declared stack is required to evaluate horizons")
    x, z = _points(x_m, z_m)
    n = int(x.size)
    layers = stack["layer_count"]
    budget = preflight(n, layers, with_horizons=True, point_mode=bool(point_mode))
    slope = math.tan(math.radians(stack["dip_deg"]))
    shift = slope * _along_dip(stack, x, z)
    reference = np.asarray(stack["horizon_elevation_m"], np.float64)
    horizons = reference.reshape((layers + 1,) + (1,) * x.ndim) - shift[None, ...]
    return np.ascontiguousarray(horizons, np.float64), budget


def query_layers(x_m, z_m, elevation_m, stack, *, faults=None, return_horizons=False):
    """Which layer and rock sits at ``(x, z, elevation)``.

    Returns ``state`` (``above_column`` / ``inside_stack`` / ``below_column``),
    ``layer_index`` (``-1`` outside the stack) and ``rock_index`` (``-1`` when the
    rock is unknown). Below the deepest horizon the answer is unknown: the surface
    rock is never copied down.
    """
    x, z = _points(x_m, z_m)
    elev = np.asarray(elevation_m, np.float64)
    elev = np.broadcast_to(elev, x.shape)
    if not np.isfinite(elev).all():
        raise ValueError("elevation_m must be finite")
    if stack is None or stack.get("status") != DECLARED:
        shape = x.shape
        return {
            "state": np.full(shape, BELOW_COLUMN, np.int8),
            "layer_index": np.full(shape, -1, np.int64),
            "rock_index": np.full(shape, -1, np.int64),
            "fault_effect": np.full(shape, FAULT_NOT_DECLARED, dtype=object),
            "applied_offset_m": np.zeros(shape, np.float64),
            "status": UNKNOWN_NO_SOURCE,
            "reason": "no stratigraphy declared; no rock source for any elevation",
        }

    layers = stack["layer_count"]
    with_horizons = bool(return_horizons)
    point_mode = x.ndim == 1
    budget = preflight(int(x.size), layers, with_horizons=with_horizons,
                       point_mode=point_mode)
    offset, fault_effect = fault_offset_m(x, z, faults)
    shifted = elev - offset

    horizons, _ = horizons_at(x, z, stack, point_mode=point_mode)
    top = horizons[0]
    bottom = horizons[layers]
    state = np.full(x.shape, INSIDE_STACK, np.int8)
    state = np.where(shifted >= top, ABOVE_COLUMN, state)
    state = np.where(shifted < bottom, BELOW_COLUMN, state)

    layer_index = np.full(x.shape, -1, np.int64)
    inside = state == INSIDE_STACK
    # Layer k occupies ``h_{k+1} <= elev < h_k``: BOTH bounds are required, otherwise
    # the first layer would swallow every inside point. The bounds are exclusive at
    # the top and inclusive at the bottom, so exactly one layer matches a point
    # inside the stack and the deepest layer end is shared with ``below_column``.
    for position in range(layers):
        selected = (inside & (layer_index < 0)
                    & (shifted < horizons[position])
                    & (shifted >= horizons[position + 1]))
        layer_index = np.where(selected, position, layer_index)
    if np.any(inside & (layer_index < 0)):
        raise ValueError(
            "an inside-stack point matched no layer: the layer bounds are not "
            "mutually exclusive")

    rock_index = np.full(x.shape, -1, np.int64)
    table = np.asarray([entry["rock_index"] for entry in stack["layers"]], np.int64)
    valid = layer_index >= 0
    if valid.any():
        rock_index[valid] = table[layer_index[valid]]

    result = {
        "state": state,
        "layer_index": layer_index,
        "rock_index": rock_index,
        "fault_effect": fault_effect,
        "applied_offset_m": offset,
        "status": DECLARED,
        "budget": budget,
        "thickness_kind": stack["thickness_kind"],
    }
    if return_horizons:
        result["horizon_elevation_m"] = horizons
    return result


# ---------------------------------------------------------------------------
# Faults: finite band, piecewise-discontinuous offset
# ---------------------------------------------------------------------------
def normalize_faults(declarations):
    """Validate finite fault bands; a band without a width is refused."""
    if declarations is None:
        return []
    if not isinstance(declarations, list):
        raise ValueError("fault declarations must be a list or None")
    if len(declarations) > MAX_FAULTS:
        raise ValueError("fault count exceeds %d" % (MAX_FAULTS,))
    result = []
    for position, entry in enumerate(declarations):
        if not isinstance(entry, dict):
            raise ValueError("fault %d must be a dict" % (position,))
        segment = np.asarray(entry.get("segment_xz_m"), np.float64)
        if segment.shape != (2, 2) or not np.isfinite(segment).all():
            raise ValueError("fault %d segment_xz_m must be two [x, z] endpoints" % (position,))
        length = math.hypot(*(segment[1] - segment[0]))
        if length <= 0.0:
            raise ValueError("fault %d segment has zero length" % (position,))
        offset = _finite(entry.get("vertical_offset_m"),
                         "fault %d vertical_offset_m" % (position,))
        if offset == 0.0:
            raise ValueError("fault %d offset of zero is not a declaration" % (position,))
        side = entry.get("moving_side")
        if side not in ("positive", "negative"):
            raise ValueError("fault %d moving_side must be 'positive' or 'negative'" % (position,))
        width = _positive(entry.get("influence_width_m"),
                          "fault %d influence_width_m" % (position,))
        source = entry.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("fault %d needs a non-empty 'source'" % (position,))
        result.append({
            "segment_xz_m": segment.tolist(),
            "vertical_offset_m": offset,
            "moving_side": side,
            "influence_width_m": width,
            "source": source,
            "half_width_m": 0.5 * width,
        })
    return result


def _segment_distance(x, z, segment):
    """Distance to the segment and the signed side (cross product sign)."""
    ax, az = segment[0]
    bx, bz = segment[1]
    dx = bx - ax
    dz = bz - az
    length_squared = dx * dx + dz * dz
    t = ((x - ax) * dx + (z - az) * dz) / length_squared
    clamped = np.clip(t, 0.0, 1.0)
    closest_x = ax + clamped * dx
    closest_z = az + clamped * dz
    distance = np.hypot(x - closest_x, z - closest_z)
    side = dx * (z - az) - dz * (x - ax)
    return distance, side, t


def fault_offset_m(x_m, z_m, faults):
    """Signed horizon offset at each point: inside a band only, zero elsewhere."""
    x, z = _points(x_m, z_m)
    declared = normalize_faults(faults)
    offset = np.zeros(x.shape, np.float64)
    effect = np.full(x.shape, FAULT_NOT_DECLARED if not declared else FAULT_OUTSIDE,
                     dtype=object)
    for fault in declared:
        distance, side, _t = _segment_distance(x, z, np.asarray(fault["segment_xz_m"]))
        inside = distance <= fault["half_width_m"]
        positive_side = side >= 0.0
        moving = positive_side if fault["moving_side"] == "positive" else ~positive_side
        applied = inside & moving
        offset = np.where(applied, offset + fault["vertical_offset_m"], offset)
        effect = np.where(inside, FAULT_APPLIED, effect)
    return offset, effect


# ---------------------------------------------------------------------------
# Joints: world-anchored plane family with a measured distance
# ---------------------------------------------------------------------------
def normalize_joints(declaration):
    """World-anchored joint sets: strike, dip, spacing and phase in metres."""
    if declaration is None:
        return {"status": PENDING,
                "reason": "no joint geometry declared; the lithology core samples a "
                          "fracture density score, not joint planes"}
    if not isinstance(declaration, dict):
        raise ValueError("joint declaration must be a dict or None")
    source = declaration.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("joint declaration needs a non-empty 'source'")
    sets = declaration.get("sets")
    if not isinstance(sets, list) or not sets:
        raise ValueError("joint declaration sets must be a non-empty list")
    if len(sets) > MAX_JOINT_SETS:
        raise ValueError("joint set count exceeds %d" % (MAX_JOINT_SETS,))
    anchor = np.asarray(declaration.get("anchor_xz_m"), np.float64)
    if anchor.shape != (2,) or not np.isfinite(anchor).all():
        raise ValueError("joint declaration anchor_xz_m must be two finite coordinates")
    normalized = []
    for position, entry in enumerate(sets):
        if not isinstance(entry, dict):
            raise ValueError("joint set %d must be a dict" % (position,))
        normalized.append({
            "strike_deg": _strike(entry.get("strike_deg")),
            "dip_deg": _finite(entry.get("dip_deg"), "joint %d dip_deg" % (position,)),
            "spacing_m": _positive(entry.get("spacing_m"),
                                   "joint %d spacing_m" % (position,)),
            "phase_m": _finite(entry.get("phase_m", 0.0),
                               "joint %d phase_m" % (position,)),
        })
        if not -90.0 <= normalized[-1]["dip_deg"] <= 90.0:
            raise ValueError("joint %d dip_deg must satisfy -90 <= dip <= 90" % (position,))
    return {"status": DECLARED, "source": source,
            "anchor_xz_m": [float(anchor[0]), float(anchor[1])], "sets": normalized}


def joint_distance(x_m, z_m, elevation_m, joints):
    """Distance from each point to the nearest plane of each joint set.

    The normal is built in the (along-dip, up) plane, so a set dipping ``d`` toward
    ``strike + 90`` has normal ``(sin d, cos d)``. The signed normal coordinate is
    wrapped to the nearest multiple of ``spacing_m``, which gives the measured
    distance to the closest joint plane and its plane index. Nothing here claims
    an erosion effect.
    """
    x, z = _points(x_m, z_m)
    elev = np.broadcast_to(np.asarray(elevation_m, np.float64), x.shape)
    if not np.isfinite(elev).all():
        raise ValueError("elevation_m must be finite")
    declared = normalize_joints(joints)
    if declared["status"] != DECLARED:
        return {"status": PENDING, "reason": declared["reason"], "sets": []}
    anchor_x, anchor_z = declared["anchor_xz_m"]
    out = []
    for entry in declared["sets"]:
        strike = math.radians(entry["strike_deg"])
        dip = math.radians(entry["dip_deg"])
        along = (x - anchor_x) * math.cos(strike) + (z - anchor_z) * math.sin(strike)
        normal = along * math.sin(dip) + (elev) * math.cos(dip) - entry["phase_m"]
        index = np.rint(normal / entry["spacing_m"]).astype(np.int64)
        signed = normal - index * entry["spacing_m"]
        out.append({
            "strike_deg": entry["strike_deg"], "dip_deg": entry["dip_deg"],
            "spacing_m": entry["spacing_m"],
            "signed_distance_m": np.ascontiguousarray(signed, np.float64),
            "absolute_distance_m": np.ascontiguousarray(np.abs(signed), np.float64),
            "joint_index": np.ascontiguousarray(index, np.int64),
        })
    return {"status": DECLARED, "anchor_xz_m": declared["anchor_xz_m"], "sets": out}


# ---------------------------------------------------------------------------
# Finite declared stock (G9 input, geometry only)
# ---------------------------------------------------------------------------
def declared_stock(stack, *, footprint_m2=None, weatherable_thickness_m=None,
                   density_kg_m3=None):
    """Finite rock volume under a declared footprint; no weathering rate needed.

    ``footprint_m2`` is the **horizontal projected** area, so the rock volume is
    ``horizontal area * vertical thickness`` — no cosine factor. The normal
    thickness of a layer is ``vertical * cos(dip)`` and the layer's own surface
    area along the bedding is ``horizontal / cos(dip)``; their product is the same
    volume, so the two routes agree and the conversion is reported, never applied
    on top of the volume.

    A stock exists as soon as the geometry is declared: footprint plus layer
    thicknesses already fix a volume. Mass needs a declared density. The
    weatherable part is reported **only** when a weatherable thickness is
    declared; the full layer thickness is never silently treated as weatherable.
    """
    if stack is None or stack.get("status") != DECLARED:
        return {"status": UNKNOWN_NO_SOURCE,
                "reason": "no declared stratigraphy, so no finite stock exists"}
    if footprint_m2 is None:
        return {"status": STOCK_PENDING,
                "reason": "no footprint declared; a thickness without an area is not "
                          "a volume"}
    area = _positive(footprint_m2, "footprint_m2")
    cos_dip = math.cos(math.radians(stack["dip_deg"]))
    vertical = stack["total_vertical_thickness_m"]
    # Footprint is a horizontal projection, so V = horizontal area * vertical
    # thickness. The equivalent normal-thickness route needs the bedding area;
    # reporting both keeps the conversion auditable instead of double-applying it.
    volume = vertical * area
    result = {
        "status": STOCK_DECLARED,
        "footprint_m2": area,
        "footprint_kind": "horizontal_projection",
        "vertical_volume_m3": volume,
        "volume_kind": "horizontal_area_x_vertical_thickness",
        "total_vertical_thickness_m": vertical,
        "total_normal_thickness_m": vertical * cos_dip,
        "bedding_area_m2": area / cos_dip,
        "thickness_conversion": "normal = vertical * cos(dip); bedding area = "
                                "horizontal / cos(dip); both routes give one volume",
        "thickness_kind": stack["thickness_kind"],
    }
    normal_route = (vertical * cos_dip) * (area / cos_dip)
    if not math.isclose(normal_route, volume, rel_tol=1e-12, abs_tol=0.0):
        raise ValueError("vertical and normal volume routes disagree")
    if density_kg_m3 is not None:
        density = _positive(density_kg_m3, "density_kg_m3")
        result["mass_kg"] = volume * density
        result["density_kg_m3"] = density
    if weatherable_thickness_m is not None:
        weatherable = _positive(weatherable_thickness_m, "weatherable_thickness_m")
        result["weatherable_volume_m3"] = min(
            weatherable, stack["total_vertical_thickness_m"]) * area
        result["weatherable_thickness_m"] = weatherable
        result["weatherable_source"] = DECLARED
    else:
        result["weatherable_thickness_m"] = None
        result["weatherable_source"] = PENDING
    return result


def describe():
    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "format_version": FORMAT_VERSION,
        "max_strata_layers": MAX_STRATA_LAYERS,
        "max_points": MAX_POINTS,
        "max_grid_cells": MAX_GRID_CELLS,
        "max_cell_layer_values": MAX_CELL_LAYER_VALUES,
        "max_faults": MAX_FAULTS,
        "max_joint_sets": MAX_JOINT_SETS,
        "state_names": dict(STATE_NAMES),
        "supported_dip_deg": "0 <= dip < 90",
        "strike_convention": "azimuth degrees, north=0, clockwise toward east; "
                             "right-hand dip direction = strike + 90",
        "thickness_kind": "vertical_thickness_m at the anchor, not normal thickness",
        "thickness_conversion": "normal_thickness = vertical_thickness * cos(dip); "
                                "with a horizontal footprint the rock volume is "
                                "horizontal_area * vertical_thickness",
        "limitations": list(LIMITATIONS),
    }
