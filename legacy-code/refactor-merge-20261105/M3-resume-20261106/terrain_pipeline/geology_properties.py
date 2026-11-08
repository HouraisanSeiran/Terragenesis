"""Geology property composition: one layer column plus a physical-property bundle.

Scope of this module (G2 first card, deliberately narrow)
---------------------------------------------------------
This is a **composition adapter**. Every physical field is read from an existing
core; nothing here is a new distribution rule:

* rock identity, class, hardness and resistance come from
  :mod:`terrain_pipeline.td_lithology_field`;
* the erodible cover thickness comes from
  :mod:`terrain_pipeline.td_material_field`.

The module adds exactly three things the repository did not have:

1. a **non-empty layer column** (`cover` then `bedrock`) with an explicit status
   per layer, so "no source" is recorded as ``unknown_no_source`` and never as a
   silent zero or a silent half-infinite slab;
2. **declared** inputs for the parts that have no model yet -- bedrock/strata
   thickness, joint geometry, fault geometry, and a per-rock extended property
   table (uniaxial compressive strength, intrinsic permeability). Unsupplied
   values stay ``pending``; nothing is invented for the 18 rocks;
3. an explicit adapter to the existing channel-width law, so a real public
   consumer can be driven on purpose rather than by a hidden default.

What is explicitly NOT here
---------------------------
* no second rock table, no re-derivation of ``bed_hardness``/``bank_hardness``
  (they are read, never recomputed), no porosity-to-permeability inversion;
* no tectonic, plate, subsidence or fault-offset model: a fault declaration is
  geometry only and always reports ``strata_offset_status='unverified'``;
* no regolith or soil inventory and no weathering flux. ``cover_thickness_m`` is
  the erodible material thickness, which is **not** soil depth, **not** regolith
  stock and **not** soil water storage;
* no temperature input at all (this module has no thermal field);
* no default-world wiring, no file IO, no environment-query import.

Coordinate semantics (this is the part that is easy to get wrong)
---------------------------------------------------------------
``td_material_field`` samples **cell centres** ``origin + (index + 0.5) * spacing``,
not grid nodes. A 30 m integer reference point therefore sits half a cell away
from the material sample it would be compared with. This module never snaps:

* :func:`geology_column` samples the material field and the lithology field at
  the *same* cell-centre coordinates, by passing those exact centres to
  ``sample_lithology_points``;
* :func:`reference_points_to_cells` is the only place that maps external
  reference points onto cells, it returns the measured offset, and it refuses
  unless the caller accepts that offset explicitly.

Determinism: absolute world metres only, ``world_seed`` sub-seeds taken from the
lithology core's own derivation, and the material seed passed in by the caller
(no third derivation scheme is invented here).
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from terrain_pipeline import td_lithology_field as _lithology
from terrain_pipeline import td_material_field as _material


SCHEMA = "geology-properties-v1"
ALGORITHM = "geology-properties-composition-v1"
FORMAT_VERSION = 1

#: The only supported grid spacing. 30 m is the native Terrain Diffusion cell.
GRID_SPACING_M = 30.0
#: Distance from a 30 m integer reference node to the centre of the cell that
#: contains it. Named so a caller that has reference points must accept it.
HALF_CELL_M = 15.0

#: Point-set form budget (same ceiling the A1 environment query uses).
MAX_POINTS = 8192
#: Grid form budget: never inherit the core's 1024**2 and then build per-cell
#: containers; this module stores compact column arrays only.
MAX_GRID_CELLS = 262_144
#: Logical payload ceiling for one result (arrays plus metadata).
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
#: Columns counted by the payload estimate: 9 grid columns + 3 optional + x/z in the
#: point form, rounded up so the estimate cannot under-count a container.
_ESTIMATED_COLUMNS = 14
_METADATA_RESERVE_BYTES = 64 * 1024

# Field groups. One schema, one spelling per field, no aliases.
INT_FIELDS = ("rock_index", "class_index")
FLOAT_FIELDS = (
    "x_m",
    "z_m",
    "bed_hardness",
    "bank_hardness",
    "erodibility_index",
    "mohs_hardness",
    "solubility",
    "porosity",
    "cover_thickness_m",
)
OPTIONAL_FLOAT_FIELDS = ("bedrock_thickness_m", "uniaxial_strength_mpa",
                         "intrinsic_permeability_m2")
#: Fields that may legitimately be negative (world coordinates are east/north signed;
#: every other numeric property is a magnitude and must be >= 0).
SIGNED_FIELDS = ("x_m", "z_m")

# Status vocabulary. Only these strings are allowed to describe availability.
COMPUTED = "computed"
DECLARED = "declared"
PENDING = "pending"
PARTIALLY_DECLARED = "partially_declared"
UNKNOWN_NO_SOURCE = "unknown_no_source"
NOT_SAMPLED_NO_GRID_WINDOW = "not_sampled_no_grid_window"
DECLARED_GEOMETRY_NOT_LITHOLOGY_OFFSET = "declared_geometry_not_lithology_offset"
UNVERIFIED = "unverified"

UNITS = {
    "x_m": "m",
    "z_m": "m",
    "rock_index": "index into td_lithology_field.ROCK_ORDER",
    "class_index": "index into td_lithology_field.CLASS_IDS",
    "bed_hardness": "1 (0 weak .. 1 strong), discharge-geometry input",
    "bank_hardness": "1 (0 weak .. 1 strong), discharge-geometry input",
    "erodibility_index": "1 (0 resistant .. 1 highly erodible)",
    "mohs_hardness": "dimensionless Mohs scale",
    "solubility": "1",
    "porosity": "volume fraction",
    "cover_thickness_m": "m",
    "bedrock_thickness_m": "m",
    "uniaxial_strength_mpa": "MPa",
    "intrinsic_permeability_m2": "m2",
    "joint_strike_deg": "deg (0 <= strike < 360)",
    "joint_dip_deg": "deg (0 <= dip <= 90)",
    "joint_spacing_m": "m",
}

#: Property fields the extended table may declare, with their unit.
EXTENDED_FIELDS = {
    "uniaxial_strength_mpa": "MPa",
    "intrinsic_permeability_m2": "m2",
}

LIMITATIONS = (
    "cover_thickness_m is the erodible material thickness: not soil depth, not "
    "regolith stock, and not soil water storage",
    "bedrock_thickness_m is unknown_no_source unless the caller declares a finite "
    "value; it is never zero-filled and never treated as half-infinite",
    "no strata column, dip, age or fault offset is modelled; the layer column has "
    "a cover and a bedrock entry only",
    "fault declarations are geometry only and always report "
    "strata_offset_status='unverified'",
    "extended strength and permeability values are declared engineering reference "
    "end members unless the caller supplies them; they are not calibrated and not "
    "measured for any field site",
    "bed_hardness / bank_hardness are generation-rule inputs, not rock strength "
    "and not an erosion rate",
    "permeability is not derived from porosity and strength is not a tensile "
    "strength nor an erodibility",
    "no consumer reads permeability or solubility yet (G11 karst/groundwater is not "
    "implemented)",
    "not wired into any default world; consumption is explicit at the call site",
)


# ---------------------------------------------------------------------------
# Small validated helpers
# ---------------------------------------------------------------------------
def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _array_digest(values):
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(_canonical(list(array.shape)).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def _identity(arrays, metadata, layer_definitions):
    record = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "format_version": FORMAT_VERSION,
        "metadata": metadata,
        "layer_definitions": layer_definitions,
        "arrays": {name: _array_digest(arrays[name]) for name in sorted(arrays)},
    }
    return hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()


def _points_digest(x, z):
    """Order-independent digest of a point set (lexsorted absolute coordinates).

    The stored arrays keep the caller's order, so the bundle identity binds that
    order; this digest is the extra, order-independent handle a joint observation
    can compare across shuffled or windowed queries.
    """
    flat_x = np.asarray(x, np.float64).reshape(-1)
    flat_z = np.asarray(z, np.float64).reshape(-1)
    order = np.lexsort((flat_z, flat_x))
    canonical = np.stack((flat_x[order], flat_z[order]), axis=1)
    return hashlib.sha256(np.ascontiguousarray(canonical).tobytes()).hexdigest()


def _finite_nonnegative(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(name + " must be finite and non-negative")
    return result


def _check_world_seed(seed):
    """Mirror of the lithology core's seed policy (no extra random source)."""
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
        raise ValueError("world_seed must be an integer")
    value = int(seed)
    if not 0 <= value < 2 ** 64:
        raise ValueError("world_seed must be a uint64")
    return value


def _check_spacing(spacing_m):
    if isinstance(spacing_m, (bool, np.bool_)) or not isinstance(
            spacing_m, (int, float, np.integer, np.floating)):
        raise ValueError("spacing_m must be numeric")
    value = float(spacing_m)
    if not math.isfinite(value):
        raise ValueError("spacing_m must be finite")
    if value != GRID_SPACING_M:
        raise ValueError(
            "this module is 30 m only: spacing_m must be %.1f, got %r; there is no "
            "arbitrary-resolution mode and no snapping" % (GRID_SPACING_M, value))
    return GRID_SPACING_M


def _shape(shape):
    if len(shape) != 2:
        raise ValueError("shape must be two positive integers")
    result = []
    for size in shape:
        if isinstance(size, (bool, np.bool_)) or not isinstance(size, (int, np.integer)):
            raise ValueError("shape must be two positive integers")
        if int(size) <= 0:
            raise ValueError("shape must be two positive integers")
        result.append(int(size))
    return tuple(result)


def _origin(origin_m_xz):
    origin = np.asarray(origin_m_xz, np.float64)
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("origin_m_xz must contain two finite coordinates")
    return origin


# ---------------------------------------------------------------------------
# Budget: checked before any container is allocated
# ---------------------------------------------------------------------------
class GeologyBudgetError(ValueError):
    """Raised when a request would exceed the point, cell or payload budget."""


def preflight(n_cells, *, point_mode=False):
    """Reject an oversized request before any array or layer container exists."""
    if isinstance(n_cells, (bool, np.bool_)) or not isinstance(n_cells, (int, np.integer)):
        raise GeologyBudgetError("cell/point count must be an integer")
    cells = int(n_cells)
    if cells <= 0:
        raise GeologyBudgetError("cell/point count must be positive")
    limit = MAX_POINTS if point_mode else MAX_GRID_CELLS
    if cells > limit:
        raise GeologyBudgetError(
            "%s count %d exceeds %d" % ("point" if point_mode else "cell", cells, limit))
    estimated = cells * 8 * _ESTIMATED_COLUMNS + _METADATA_RESERVE_BYTES
    if estimated > MAX_OUTPUT_BYTES:
        raise GeologyBudgetError(
            "estimated logical payload %d bytes exceeds %d" % (estimated, MAX_OUTPUT_BYTES))
    return {
        "n_cells": cells,
        "point_mode": bool(point_mode),
        "estimated_columns": _ESTIMATED_COLUMNS,
        "estimated_logical_payload_bytes": estimated,
        "max_points": MAX_POINTS,
        "max_grid_cells": MAX_GRID_CELLS,
        "max_output_bytes": MAX_OUTPUT_BYTES,
    }


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------
def cell_centres(shape, *, origin_m_xz, spacing_m):
    """Absolute cell centres ``origin + (index + 0.5) * spacing``.

    This is the only coordinate the material field ever samples, so it is the
    coordinate every thickness field in this module lives on.
    """
    shape = _shape(shape)
    spacing = _check_spacing(spacing_m)
    origin = _origin(origin_m_xz)
    grid_origin = origin / spacing
    if np.any(np.abs(grid_origin) > 2.0 ** 50) or not np.allclose(
            grid_origin, np.rint(grid_origin), rtol=0.0, atol=1e-8):
        raise ValueError(
            "origin_m_xz must align with the 30 m grid, exactly like "
            "td_material_field requires; this module never snaps the origin")
    x_m = origin[0] + (np.arange(shape[1], dtype=np.int64) + 0.5) * spacing
    z_m = origin[1] + (np.arange(shape[0], dtype=np.int64) + 0.5) * spacing
    return np.broadcast_to(x_m[None, :], shape).copy(), np.broadcast_to(z_m[:, None], shape).copy()


def reference_points_to_cells(x_ref_m, z_ref_m, *, origin_m_xz, spacing_m,
                             accept_offset_m=None):
    """Map external reference points onto material cells, reporting the offset.

    A 30 m integer reference node sits half a cell (15 m per axis) away from the
    cell centre whose values this module reports. Nothing is snapped: with
    ``accept_offset_m=None`` any non-zero offset raises, and a caller that really
    wants the containing cell must pass the offset it accepts. ``offset_m`` is the
    measured Euclidean distance from the requested point to that centre.
    """
    spacing = _check_spacing(spacing_m)
    origin = _origin(origin_m_xz)
    x = np.asarray(x_ref_m, np.float64)
    z = np.asarray(z_ref_m, np.float64)
    x, z = np.broadcast_arrays(x, z)
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("reference coordinates must be finite")
    column = np.floor((x - origin[0]) / spacing).astype(np.int64)
    row = np.floor((z - origin[1]) / spacing).astype(np.int64)
    centre_x = origin[0] + (column + 0.5) * spacing
    centre_z = origin[1] + (row + 0.5) * spacing
    offset = np.hypot(x - centre_x, z - centre_z)
    if accept_offset_m is None:
        if np.any(offset > 1e-9):
            raise ValueError(
                "reference points are not cell centres: measured offset up to %.6f m "
                "(a 30 m integer node sits %.1f m from the cell centre it belongs to). "
                "Pass accept_offset_m to accept it explicitly; this module does not snap"
                % (float(offset.max()), HALF_CELL_M))
    else:
        accepted = _finite_nonnegative(accept_offset_m, "accept_offset_m")
        if float(offset.max()) > accepted + 1e-9:
            raise ValueError(
                "measured offset up to %.6f m exceeds the accepted offset %.6f m; this "
                "module reports the containing cell but never moves the requesting point"
                % (float(offset.max()), accepted))
    return {
        "row_index": row,
        "column_index": column,
        "cell_centre_x_m": centre_x,
        "cell_centre_z_m": centre_z,
        "offset_m": offset,
        "snapped": False,
        "semantics": "row/column index the cell whose centre is reported; the requesting "
                      "point keeps its own coordinate and is never moved",
    }


# ---------------------------------------------------------------------------
# Rock attribute lookup tables (read-only, deep copies)
# ---------------------------------------------------------------------------
def _rock_lookup():
    """Per-rock-index lookup arrays built from a deep copy of the rock table."""
    table = _lithology.rock_table()
    by_id = {record["id"]: record for record in table}
    mohs = np.asarray([by_id[name]["mohs_hardness"] for name in _lithology.ROCK_ORDER], np.float64)
    solubility = np.asarray([by_id[name]["solubility"] for name in _lithology.ROCK_ORDER], np.float64)
    porosity = np.asarray([by_id[name]["porosity"] for name in _lithology.ROCK_ORDER], np.float64)
    return {"mohs_hardness": mohs, "solubility": solubility, "porosity": porosity}


# ---------------------------------------------------------------------------
# Extended property table (declared, never invented)
# ---------------------------------------------------------------------------
def default_extended_properties():
    """Every rock starts `pending`: no strength/permeability constant is invented."""
    pending = {
        field: {
            "status": PENDING,
            "units": unit,
            "reason": "no declared source for this rock; the first card does not "
                      "invent a magnitude for it",
        }
        for field, unit in EXTENDED_FIELDS.items()
    }
    return {name: json.loads(_canonical(pending)) for name in _lithology.ROCK_ORDER}


def normalize_extended_properties(table=None):
    """Validate a per-rock extended property table; unknown rocks/fields rejected."""
    if table is None:
        return default_extended_properties()
    if not isinstance(table, dict):
        raise ValueError("extended property table must be a dict keyed by rock id")
    unknown = sorted(set(table) - set(_lithology.ROCK_ORDER))
    if unknown:
        raise ValueError("unknown rock ids in extended property table: %r" % (unknown,))
    result = {}
    for name in _lithology.ROCK_ORDER:
        entry = table.get(name)
        if entry is None:
            result[name] = json.loads(_canonical(default_extended_properties()[name]))
            continue
        if not isinstance(entry, dict):
            raise ValueError("extended property entry for %r must be a dict" % (name,))
        extra = sorted(set(entry) - set(EXTENDED_FIELDS))
        if extra:
            raise ValueError("unknown extended fields for %r: %r" % (name, extra))
        fields = {}
        for field, unit in EXTENDED_FIELDS.items():
            record = entry.get(field)
            if record is None:
                fields[field] = json.loads(
                    _canonical(default_extended_properties()[name][field]))
                continue
            if not isinstance(record, dict):
                raise ValueError("%s.%s must be a dict" % (name, field))
            if record.get("units") != unit:
                raise ValueError("%s.%s units must be %r" % (name, field, unit))
            if record.get("status") == PENDING:
                reason = record.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError("%s.%s pending entries need a reason" % (name, field))
                fields[field] = {"status": PENDING, "units": unit, "reason": reason}
                continue
            if record.get("status") != DECLARED:
                raise ValueError("%s.%s status must be 'declared' or 'pending'" % (name, field))
            value = _finite_nonnegative(record.get("value"), "%s.%s.value" % (name, field))
            for key in ("source", "rock_mass_scale"):
                text = record.get(key)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(
                        "%s.%s declared entries need a non-empty %r "
                        "(a value without a source is not allowed)" % (name, field, key))
            fields[field] = {
                "status": DECLARED,
                "units": unit,
                "value": value,
                "source": record["source"],
                "rock_mass_scale": record["rock_mass_scale"],
            }
        result[name] = fields
    return result


def extended_properties_identity(table):
    """Identity of an extended table, used in the bundle identity."""
    return hashlib.sha256(
        _canonical(normalize_extended_properties(table)).encode("utf-8")).hexdigest()


def _extended_arrays(table, rock_index):
    """Expand declared extended fields per cell, plus a per-cell availability mask.

    A partially declared table must not force an invented number for the rocks it
    left ``pending``. So each declared field is emitted together with a boolean
    ``<field>_available`` mask: ``True`` only where the cell's rock declares the
    field. Cell values where the mask is ``False`` are exactly ``0.0`` **and**
    carry no meaning; callers must read the mask. ``pending_rock_ids`` records, per
    field, which rocks are still missing a declared value.
    """
    order = _lithology.ROCK_ORDER
    out = {}
    pending = {}
    for field in EXTENDED_FIELDS:
        values = np.zeros(len(order), np.float64)
        declared = np.zeros(len(order), bool)
        undeclared = []
        for position, name in enumerate(order):
            record = table[name][field]
            if record["status"] != DECLARED:
                undeclared.append(name)
                continue
            values[position] = record["value"]
            declared[position] = True
        pending[field] = undeclared
        if undeclared and len(undeclared) == len(order):
            continue
        out[field] = np.ascontiguousarray(values[rock_index], np.float64)
        out[field + "_available"] = np.ascontiguousarray(declared[rock_index], bool)
    return out, pending


# ---------------------------------------------------------------------------
# Declared extras: strata, joints, fault
# ---------------------------------------------------------------------------
def normalize_strata_declaration(declaration, shape):
    """A finite, declared bedrock thickness. No declaration stays unknown."""
    if declaration is None:
        return {"status": UNKNOWN_NO_SOURCE,
                "values": None,
                "reason": "no bedrock/strata thickness source is declared; the value is "
                          "unknown, never zero and never half-infinite"}
    if not isinstance(declaration, dict):
        raise ValueError("strata_declaration must be a dict or None")
    source = declaration.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("strata_declaration needs a non-empty 'source'")
    thickness = declaration.get("bedrock_thickness_m")
    values = np.asarray(thickness, np.float64)
    if values.ndim == 0:
        values = np.full(shape, _finite_nonnegative(values.item(), "bedrock_thickness_m"),
                         np.float64)
    else:
        if values.shape != shape:
            raise ValueError("bedrock_thickness_m must be scalar or same-shape")
        if not np.isfinite(values).all() or np.any(values < 0.0):
            raise ValueError("bedrock_thickness_m must be finite and non-negative")
        values = np.ascontiguousarray(values, np.float64)
    return {"status": DECLARED, "values": values, "source": source}


def normalize_joint_declaration(declaration):
    """Declared joint sets; no joint field is generated here."""
    if declaration is None:
        return {"status": PENDING, "sets": [],
                "reason": "no joint geometry declared; the lithology core samples a "
                          "fracture density and a layering score, not joint sets"}
    if not isinstance(declaration, dict):
        raise ValueError("joint_declaration must be a dict or None")
    source = declaration.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("joint_declaration needs a non-empty 'source'")
    sets = declaration.get("sets")
    if not isinstance(sets, list) or not sets:
        raise ValueError("joint_declaration.sets must be a non-empty list")
    normalized = []
    for position, item in enumerate(sets):
        if not isinstance(item, dict):
            raise ValueError("joint set %d must be a dict" % (position,))
        strike = item.get("strike_deg")
        dip = item.get("dip_deg")
        spacing = item.get("spacing_m")
        for value, name in ((strike, "strike_deg"), (dip, "dip_deg"),
                            (spacing, "spacing_m")):
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                    value, (int, float, np.integer, np.floating)):
                raise ValueError("joint set %d %s must be numeric" % (position, name))
            if not math.isfinite(float(value)):
                raise ValueError("joint set %d %s must be finite" % (position, name))
        strike = float(strike)
        dip = float(dip)
        spacing = float(spacing)
        if not 0.0 <= strike < 360.0:
            raise ValueError("joint strike_deg must satisfy 0 <= strike < 360")
        if not 0.0 <= dip <= 90.0:
            raise ValueError("joint dip_deg must satisfy 0 <= dip <= 90")
        if spacing <= 0.0:
            raise ValueError("joint spacing_m must be positive")
        normalized.append({"strike_deg": strike, "dip_deg": dip, "spacing_m": spacing})
    return {"status": DECLARED, "sets": normalized, "source": source}


def fault_context(declaration=None):
    """Fault geometry as a plain serializable declaration, never a model."""
    if declaration is None:
        return {"status": PENDING, "strata_offset_status": PENDING,
                "reason": "no fault declaration supplied; this module models no fault"}
    if not isinstance(declaration, dict):
        raise ValueError("fault declaration must be a dict or None")
    source = declaration.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("fault declaration needs a non-empty 'source'")
    origin = declaration.get("plane_origin_xz_m")
    origin = np.asarray(origin, np.float64)
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("fault plane_origin_xz_m must be two finite coordinates")
    strike = declaration.get("strike_degrees")
    slip = declaration.get("slip_m")
    transition = declaration.get("transition_width_m")
    side = declaration.get("moving_side")
    for value, name in ((strike, "strike_degrees"), (slip, "slip_m"),
                        (transition, "transition_width_m")):
        if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, float, np.integer, np.floating)):
            raise ValueError("fault %s must be numeric" % (name,))
        if not math.isfinite(float(value)):
            raise ValueError("fault %s must be finite" % (name,))
    if side not in ("positive", "negative"):
        raise ValueError("fault moving_side must be 'positive' or 'negative'")
    if float(transition) <= 0.0:
        raise ValueError("fault transition_width_m must be positive")
    if float(slip) < 0.0:
        raise ValueError("fault slip_m is a magnitude and must be non-negative")
    return {
        "status": DECLARED_GEOMETRY_NOT_LITHOLOGY_OFFSET,
        "strata_offset_status": UNVERIFIED,
        "source": source,
        "plane_origin_xz_m": [float(origin[0]), float(origin[1])],
        "strike_degrees": float(strike),
        "slip_m": float(slip),
        "moving_side": side,
        "transition_width_m": float(transition),
        "note": "geometry only: this module does not prove that the declaration offsets "
                "the 30 m lithology column, so the strata offset stays unverified",
    }


# ---------------------------------------------------------------------------
# Layer definitions (shared, not per cell)
# ---------------------------------------------------------------------------
def layer_definitions():
    """The one layer stack this module reports: cover, then bedrock."""
    return [
        {
            "name": "cover",
            "order": 0,
            "thickness_field": "cover_thickness_m",
            "property_source": "terrain_pipeline.td_material_field.make_material_field",
            "semantics": "erodible material thickness: not soil depth, not regolith stock",
        },
        {
            "name": "bedrock",
            "order": 1,
            "thickness_field": "bedrock_thickness_m",
            "property_source": "terrain_pipeline.td_lithology_field.sample_lithology_points",
            "thickness_default_status": UNKNOWN_NO_SOURCE,
            "semantics": "one rock per map column; no strata column, dip or age",
        },
    ]


# ---------------------------------------------------------------------------
# Shared metadata / bundle assembly
# ---------------------------------------------------------------------------
def _base_metadata(*, world_seed, fields_status, extra):
    metadata = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "format_version": FORMAT_VERSION,
        "fields_status": fields_status,
        "units": dict(UNITS),
        "limitations": list(LIMITATIONS),
        "rock_table_identity_sha256": _lithology.rock_table_identity(),
        "rock_order": list(_lithology.ROCK_ORDER),
        "class_order": list(_lithology.CLASS_IDS),
        "lithology_subseeds": _lithology.lithology_subseeds(world_seed),
        "lithology_seed_derivation": _lithology.SEED_DERIVATION,
        "world_seed": int(world_seed),
        "grid_spacing_m": GRID_SPACING_M,
        "half_cell_m": HALF_CELL_M,
        "coordinate_convention": "X east; Z south; [z, x]; absolute world metres",
        "thickness_coordinates": "cell centres origin_m_xz + (index + 0.5) * spacing_m",
        "synthetic_lithology": True,
        "measured_lithology": False,
        "value_status": _lithology.PROVENANCE,
    }
    metadata.update(extra)
    metadata["declared_uncalibrated"] = (
        "rock attribute values and any declared extended property are engineering "
        "reference values, not calibrated measurements")
    return metadata


def _bundle(arrays, metadata):
    frozen = {}
    for name, values in arrays.items():
        contiguous = np.ascontiguousarray(values)
        frozen[name] = np.frombuffer(contiguous.tobytes(),
                                     dtype=contiguous.dtype).reshape(contiguous.shape)
    metadata = json.loads(_canonical(metadata))
    definitions = layer_definitions()
    return {
        "schema": SCHEMA,
        "arrays": frozen,
        "layer_definitions": definitions,
        "metadata": metadata,
        "identity_sha256": _identity(frozen, metadata, definitions),
    }


def _lithology_arrays(x_m, z_m, world_seed):
    sampled = _lithology.sample_lithology_points(x_m, z_m, world_seed=world_seed)
    rock_index = np.asarray(sampled["rock_index"], np.int64)
    arrays = {
        "rock_index": rock_index,
        "class_index": np.asarray(sampled["class_index"], np.int64),
        "bed_hardness": np.asarray(sampled["bed_hardness"], np.float64),
        "bank_hardness": np.asarray(sampled["bank_hardness"], np.float64),
        "erodibility_index": np.asarray(sampled["erodibility_index"], np.float64),
    }
    lookup = _rock_lookup()
    for name in ("mohs_hardness", "solubility", "porosity"):
        arrays[name] = np.ascontiguousarray(lookup[name][rock_index], np.float64)
    return arrays, rock_index


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
def properties_at(x_m, z_m, *, world_seed=_lithology.DEFAULT_WORLD_SEED,
                  extended_properties=None, joint_declaration=None):
    """Point-set properties: rock identity plus the non-thickness properties.

    Thickness fields are deliberately absent: the erodible cover can only be
    produced on an aligned grid window, so pretending to have it per arbitrary
    point would be a half-cell lie. Use :func:`geology_column` for thicknesses.
    """
    seed = _check_world_seed(world_seed)
    x = np.asarray(x_m, np.float64)
    z = np.asarray(z_m, np.float64)
    x, z = np.broadcast_arrays(x, z)
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("x_m and z_m must be finite absolute world metres")
    n = int(x.size)
    budget = preflight(n, point_mode=True)

    table = normalize_extended_properties(extended_properties)
    joints = normalize_joint_declaration(joint_declaration)

    arrays, rock_index = _lithology_arrays(x, z, seed)
    extended, pending = _extended_arrays(table, rock_index)
    arrays.update(extended)
    arrays["x_m"] = np.ascontiguousarray(x, np.float64)
    arrays["z_m"] = np.ascontiguousarray(z, np.float64)

    fields_status = {name: COMPUTED for name in arrays}
    fields_status["cover_thickness_m"] = NOT_SAMPLED_NO_GRID_WINDOW
    fields_status["bedrock_thickness_m"] = UNKNOWN_NO_SOURCE
    for field in EXTENDED_FIELDS:
        if field + "_available" in arrays:
            fields_status[field] = DECLARED if not pending[field] else PARTIALLY_DECLARED
        else:
            fields_status[field] = PENDING

    metadata = _base_metadata(
        world_seed=seed,
        fields_status=fields_status,
        extra={
            "form": "point_set",
            "point_count": n,
            "points_digest": _points_digest(x, z),
            "extended_properties": table,
            "extended_properties_identity_sha256": extended_properties_identity(table),
            "extended_pending_rock_ids": pending,
            "joint_declaration": joints,
            "budget": budget,
        })
    return _bundle(arrays, metadata)


def geology_column(shape, *, origin_m_xz, spacing_m, world_seed=_lithology.DEFAULT_WORLD_SEED,
                   material_seed, extended_properties=None, joint_declaration=None,
                   strata_declaration=None, fault_declaration=None):
    """Grid-form layer column: cover thickness plus the bedrock rock column.

    Both cores are sampled at the **same** cell-centre coordinates, so a column's
    cover thickness and its rock identity describe one physical point.
    ``material_seed`` is required: this module refuses to invent a third seed
    derivation. A caller that wants to match the A1 environment query passes the
    seed it derives there for purpose ``geography-stage2-material``.
    """
    shape = _shape(shape)
    spacing = _check_spacing(spacing_m)
    origin = _origin(origin_m_xz)
    cells = int(shape[0] * shape[1])
    budget = preflight(cells, point_mode=False)
    seed = _check_world_seed(world_seed)
    material_seed = _check_world_seed(material_seed)

    x_m, z_m = cell_centres(shape, origin_m_xz=origin, spacing_m=spacing)
    arrays, rock_index = _lithology_arrays(x_m, z_m, seed)

    material = _material.make_material_field(
        shape, origin_m_xz=[float(origin[0]), float(origin[1])],
        spacing_m=spacing, seed=material_seed)
    cover = np.asarray(material["arrays"]["erodible_thickness_m"], np.float64)
    if cover.shape != shape:
        raise ValueError("material thickness shape mismatch")
    arrays["cover_thickness_m"] = np.ascontiguousarray(cover, np.float64)

    strata = normalize_strata_declaration(strata_declaration, shape)
    if strata["values"] is not None:
        arrays["bedrock_thickness_m"] = strata["values"]

    table = normalize_extended_properties(extended_properties)
    extended, pending = _extended_arrays(table, rock_index)
    arrays.update(extended)

    joints = normalize_joint_declaration(joint_declaration)
    fault = fault_context(fault_declaration)

    fields_status = {name: COMPUTED for name in arrays}
    fields_status["bedrock_thickness_m"] = strata["status"]
    for field in EXTENDED_FIELDS:
        if field + "_available" in arrays:
            fields_status[field] = DECLARED if not pending[field] else PARTIALLY_DECLARED
        else:
            fields_status[field] = PENDING

    metadata = _base_metadata(
        world_seed=seed,
        fields_status=fields_status,
        extra={
            "form": "grid_column",
            "shape": list(shape),
            "origin_m_xz": [float(origin[0]), float(origin[1])],
            "cell_centres_sampled": True,
            "bedrock_thickness_source": strata.get("source", UNKNOWN_NO_SOURCE),
            "material": {
                "algorithm": material["metadata"]["algorithm"],
                "seed": int(material_seed),
                "parameters": material["metadata"]["parameters"],
                "identity_sha256": material["identity_sha256"],
                "semantics": "erodible thickness, not soil depth and not a stock",
            },
            "extended_properties": table,
            "extended_properties_identity_sha256": extended_properties_identity(table),
            "extended_pending_rock_ids": pending,
            "joint_declaration": joints,
            "fault_context": fault,
            "budget": budget,
        })
    return _bundle(arrays, metadata)


# ---------------------------------------------------------------------------
# Explicit consumption adapter
# ---------------------------------------------------------------------------
def width_law_hardness(bundle):
    """Return ``(bed_hardness, bank_hardness)`` copies for the width law.

    This is the explicit bridge to
    :func:`terrain_pipeline.surface_rivers.world_reach_lake.channel_width_from_lithology_m`
    (and to the older ``metric_discharge_geometry`` hardness inputs). It is an
    opt-in call: nothing in this module wires itself into a default path.
    """
    validate_geology_properties(bundle)
    arrays = bundle["arrays"]
    return arrays["bed_hardness"].copy(), arrays["bank_hardness"].copy()


def channel_width_m(bundle, contributing_area_m2, *, reference_discharge_m3_s,
                    reference_width_m, min_width_m, max_width_m,
                    design_runoff_mm_h=1.0, width_exponent=0.5,
                    bed_lateral_factor=1.5, bank_lateral_factor=1.5,
                    bed_hardness=None, bank_hardness=None):
    """Drive the existing channel-width law from a geology bundle.

    This is the real public consumption path: the width comes from
    :func:`terrain_pipeline.surface_rivers.world_reach_lake.channel_width_from_lithology_m`,
    which is imported lazily so importing this module stays lightweight. No
    default world, driver or test is wired to it -- a caller opts in.

    The law uses **both** ``bed_hardness`` and ``bank_hardness``
    (``W = W_ref (Q/Q_ref)**b (1 + a_bed h_bed) (0.5 + a_bank (1 - h_bank))``), so a
    wider granite channel is a measured outcome of that formula and its inputs,
    never an assumption from the rock name.

    ``bed_hardness`` / ``bank_hardness`` are an **explicit experiment override**
    (shape must equal the bundle's). When given they are used instead of the
    bundle's arrays and the returned record says ``overrides_used`` -- so a
    causal control can never be mistaken for the bundle's own values.
    """
    from terrain_pipeline.lake import channel_width_from_lithology_m as channel_width_from_lithology_m

    bed_bundle, bank_bundle = width_law_hardness(bundle)
    shape = bed_bundle.shape
    overrides = []
    bed = bed_bundle
    bank = bank_bundle
    if bed_hardness is not None:
        bed = np.ascontiguousarray(np.asarray(bed_hardness, np.float64))
        _check_hardness_override(bed, shape, "bed_hardness")
        overrides.append("bed_hardness")
    if bank_hardness is not None:
        bank = np.ascontiguousarray(np.asarray(bank_hardness, np.float64))
        _check_hardness_override(bank, shape, "bank_hardness")
        overrides.append("bank_hardness")
    flat_bed = np.ascontiguousarray(np.asarray(bed, np.float64).reshape(-1))
    flat_bank = np.ascontiguousarray(np.asarray(bank, np.float64).reshape(-1))
    area = np.asarray(contributing_area_m2, np.float64).reshape(-1)
    if area.shape != flat_bed.shape:
        raise ValueError("one contributing area per geology column required")
    widths, design_q = channel_width_from_lithology_m(
        area, flat_bed, flat_bank,
        reference_discharge_m3_s=reference_discharge_m3_s,
        reference_width_m=reference_width_m,
        min_width_m=min_width_m, max_width_m=max_width_m,
        design_runoff_mm_h=design_runoff_mm_h, width_exponent=width_exponent,
        bed_lateral_factor=bed_lateral_factor,
        bank_lateral_factor=bank_lateral_factor)
    return {
        "width_m": np.ascontiguousarray(np.asarray(widths, np.float64).reshape(shape)),
        "design_q_m3_s": np.ascontiguousarray(
            np.asarray(design_q, np.float64).reshape(shape)),
        "consumed_fields": ["bed_hardness", "bank_hardness"],
        "overrides_used": overrides,
        "consumer": "surface_rivers.world_reach_lake.channel_width_from_lithology_m",
        "units": {"width_m": "m", "design_q_m3_s": "m3/s"},
    }


def _check_hardness_override(values, shape, name):
    if values.shape != shape:
        raise ValueError(name + " override must match the bundle shape")
    if not np.isfinite(values).all() or np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError(name + " override must be finite and lie in [0, 1]")


def describe():
    """Static declaration for review; it takes part in no numeric result."""
    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "format_version": FORMAT_VERSION,
        "grid_spacing_m": GRID_SPACING_M,
        "half_cell_m": HALF_CELL_M,
        "supported_spacings_m": [GRID_SPACING_M],
        "max_points": MAX_POINTS,
        "max_grid_cells": MAX_GRID_CELLS,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "layer_names": [layer["name"] for layer in layer_definitions()],
        "int_fields": list(INT_FIELDS),
        "float_fields": list(FLOAT_FIELDS),
        "point_form_only_float_fields": list(SIGNED_FIELDS),
        "optional_float_fields": list(OPTIONAL_FLOAT_FIELDS),
        "extended_fields": dict(EXTENDED_FIELDS),
        "status_vocabulary": [COMPUTED, DECLARED, PARTIALLY_DECLARED, PENDING,
                             UNKNOWN_NO_SOURCE, NOT_SAMPLED_NO_GRID_WINDOW,
                             DECLARED_GEOMETRY_NOT_LITHOLOGY_OFFSET, UNVERIFIED],
        "fields_without_consumer": ["intrinsic_permeability_m2", "solubility"],
        "explicit_consumers": {
            "channel_width_m": "surface_rivers.world_reach_lake."
                               "channel_width_from_lithology_m (bed_hardness + bank_hardness)",
        },
        "never": [
            "a second rock table",
            "recomputing bed_hardness or bank_hardness",
            "inverting porosity into permeability",
            "treating compressive strength as tensile strength or as erodibility",
            "a tectonic, plate or fault-offset model",
            "a regolith or soil inventory",
            "any temperature input",
            "snapping reference points onto cell centres silently",
            "an arbitrary spacing mode (10 km compatibility)",
            "importing the A1 environment query to reuse its composition",
        ],
        "coordinate_semantics": "cell centres origin + (index + 0.5) * spacing; a 30 m "
                                "integer reference node is half a cell away",
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _check_identity(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {
            "schema", "arrays", "layer_definitions", "metadata", "identity_sha256"}:
        raise ValueError("invalid geology bundle structure")
    if bundle["schema"] != SCHEMA:
        raise ValueError("unsupported geology schema")
    if bundle["layer_definitions"] != layer_definitions():
        raise ValueError("layer definitions differ from the declared stack")
    if _identity(bundle["arrays"], bundle["metadata"],
                 bundle["layer_definitions"]) != bundle["identity_sha256"]:
        raise ValueError("geology bundle identity mismatch")


def _validate_extended(bundle, table):
    """Extended fields must match the declared table and their availability mask."""
    arrays = bundle["arrays"]
    rock_index = arrays["rock_index"]
    pending_recorded = bundle["metadata"].get("extended_pending_rock_ids")
    if not isinstance(pending_recorded, dict):
        raise ValueError("extended_pending_rock_ids must be recorded")
    expected, pending = _extended_arrays(table, rock_index)
    if sorted(pending_recorded) != sorted(pending):
        raise ValueError("extended pending rock ids differ from the declared table")
    for field in EXTENDED_FIELDS:
        if pending_recorded.get(field) != pending[field]:
            raise ValueError("extended pending rock ids mismatch for " + field)
        mask_name = field + "_available"
        if field in expected:
            if field not in arrays or mask_name not in arrays:
                raise ValueError(field + " is declared but not stored")
            if arrays[mask_name].dtype != np.dtype(bool):
                raise ValueError(mask_name + " must be boolean")
            if not np.array_equal(arrays[mask_name], expected[mask_name]):
                raise ValueError(mask_name + " is inconsistent with the declared table")
            declared_mask = expected[mask_name]
            if not np.array_equal(arrays[field][declared_mask], expected[field][declared_mask]):
                raise ValueError(field + " is inconsistent with the declared table")
            if np.any(arrays[field][~declared_mask] != 0.0):
                raise ValueError(
                    field + " carries a number where the rock has no declared value")
        else:
            if field in arrays or mask_name in arrays:
                raise ValueError(field + " must not be stored when no rock declares it")


def _validate_shared(bundle):
    metadata = bundle["metadata"]
    if metadata.get("schema") != SCHEMA:
        raise ValueError("unsupported geology schema")
    if metadata.get("algorithm") != ALGORITHM or metadata.get("format_version") != FORMAT_VERSION:
        raise ValueError("unsupported geology identity")
    if metadata.get("rock_table_identity_sha256") != _lithology.rock_table_identity():
        raise ValueError("rock attribute table differs from the one recorded by the bundle")
    if metadata.get("rock_order") != list(_lithology.ROCK_ORDER):
        raise ValueError("rock ordering mismatch")
    if metadata.get("grid_spacing_m") != GRID_SPACING_M:
        raise ValueError("bundle spacing is not the 30 m grid")
    if metadata.get("synthetic_lithology") is not True or metadata.get("measured_lithology") is not False:
        raise ValueError("a geology bundle must declare synthetic, unmeasured status")
    if metadata.get("lithology_subseeds") != _lithology.lithology_subseeds(metadata["world_seed"]):
        raise ValueError("lithology sub-seeds do not match the recorded world seed")
    arrays = bundle["arrays"]
    for name in INT_FIELDS:
        if name in arrays and arrays[name].dtype != np.int64:
            raise ValueError(name + " must be int64")
    for name in FLOAT_FIELDS + OPTIONAL_FLOAT_FIELDS:
        if name not in arrays:
            continue
        values = arrays[name]
        if values.dtype != np.float64 or not np.isfinite(values).all():
            raise ValueError(name + " must be finite float64")
        if name not in SIGNED_FIELDS and np.any(values < 0.0):
            raise ValueError(name + " must be non-negative")
    for name in ("bed_hardness", "bank_hardness"):
        if name in arrays and (np.any(arrays[name] < 0.0) or np.any(arrays[name] > 1.0)):
            raise ValueError(name + " must lie in [0, 1]")
    if "bank_hardness" in arrays and "bed_hardness" in arrays:
        if np.any(arrays["bank_hardness"] > arrays["bed_hardness"]):
            raise ValueError("bank hardness must not exceed bed hardness")
    rock_index = arrays["rock_index"]
    if rock_index.size and (rock_index.min() < 0 or rock_index.max() >= len(_lithology.ROCK_ORDER)):
        raise ValueError("rock index out of range")
    lookup = _rock_lookup()
    for name in ("mohs_hardness", "solubility", "porosity"):
        if name in arrays and not np.array_equal(arrays[name], lookup[name][rock_index]):
            raise ValueError(name + " is inconsistent with the rock table")
    return metadata


def validate_geology_properties(bundle):
    """Reject a bundle that does not recompute from its own declared inputs."""
    _check_identity(bundle)
    metadata = _validate_shared(bundle)
    form = metadata.get("form")
    table = normalize_extended_properties(metadata.get("extended_properties"))
    if extended_properties_identity(table) != metadata.get("extended_properties_identity_sha256"):
        raise ValueError("extended property identity mismatch")
    _validate_extended(bundle, table)
    if form == "point_set":
        if "cover_thickness_m" in bundle["arrays"]:
            raise ValueError("point form must not carry a cover thickness")
        status = metadata["fields_status"].get("cover_thickness_m")
        if status != NOT_SAMPLED_NO_GRID_WINDOW:
            raise ValueError("point form must declare the cover thickness as not sampled")
        n = int(metadata["point_count"])
        budget = preflight(n, point_mode=True)
        if budget != metadata["budget"]:
            raise ValueError("recorded budget differs from the recomputed one")
    elif form == "grid_column":
        shape = tuple(metadata["shape"])
        if "cover_thickness_m" not in bundle["arrays"]:
            raise ValueError("grid form must carry a cover thickness")
        if tuple(bundle["arrays"]["cover_thickness_m"].shape) != shape:
            raise ValueError("cover thickness shape mismatch")
        status = metadata["fields_status"].get("bedrock_thickness_m")
        if status not in (DECLARED, UNKNOWN_NO_SOURCE):
            raise ValueError("bedrock thickness status must be declared or unknown_no_source")
        if status == UNKNOWN_NO_SOURCE and "bedrock_thickness_m" in bundle["arrays"]:
            raise ValueError("an unknown bedrock thickness must not be stored as a number")
        if status == DECLARED and "bedrock_thickness_m" not in bundle["arrays"]:
            raise ValueError("a declared bedrock thickness must be stored")
        budget = preflight(int(shape[0] * shape[1]), point_mode=False)
        if budget != metadata["budget"]:
            raise ValueError("recorded budget differs from the recomputed one")
        if metadata.get("cell_centres_sampled") is not True:
            raise ValueError("grid form must declare cell-centre sampling")
        cell_centres(shape, origin_m_xz=metadata["origin_m_xz"],
                     spacing_m=metadata["grid_spacing_m"])
    else:
        raise ValueError("unknown bundle form")
    return True
