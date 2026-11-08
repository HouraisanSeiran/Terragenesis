"""Actual soil-thickness and land-cover consumer for G6 (bounded, one entry point).

What this module is
-------------------
A **consumer**, not a new physics model. It takes four already-produced inputs, each
with its own identity and its own declared status, and derives three separated
outputs:

    inputs                     outputs
    ------                     -------
    parent material (G9/S3)    soil thickness (bulk, m)
    rock physical properties    soil water capacity (mm) and the actual
      (porosity, hardness,       G5 water state it is compared against
       solubility, ...)         suitability (temperature + water + material)
    actual G5 water state       land cover (the actual surface class)
    G3 monthly temperature and
      annual precipitation

Nothing here measures soil. Every number is either an input passed through, a
declared conversion, or a declared engineering ranking.

The three products are deliberately **not** collapsed into one label:

* ``soil`` — thickness and capacity, derived from material and pore space;
* ``suitability`` — how favourable the site is, from temperature, water and
  material, in normalized units;
* ``land_cover`` — the actual surface class the site carries, which consumes the
  suitability **and** the material **and** the water state, not just the annual
  precipitation rescaled onto a colour.

Thickness is **bulk**, and pore volume is not water
--------------------------------------------------
The parent solid volume delivered by G9 is a **solid** volume. Converted to a soil
layer it must go through the pore space exactly once::

    bulk_thickness_m = solid_m3 / ((1 - porosity) * horizontal_area_m2)

This is **not** ``solid / area``: that would give an equivalent *solid* thickness and
would understate the layer by the pore factor. The same module keeps the distinction
that G9 already draws in its own ``soil_delivery.conversion`` note.

What the layer can hold is a **capacity**, and capacity is not a stock::

    soil_water_capacity_mm = bulk_thickness_m * 1000 * available_water_fraction

where ``available_water_fraction`` is a declared constant (not a measurement). The
actual water content comes from G5 as a ``[3, N]`` bucket state; the two are compared
and reported side by side. A full capacity never means "the soil is wet now".

What this module does NOT do
----------------------------
* no soil-water bucket, no ET, no percolation: G5 owns that and is consumed read-only;
* no vegetation growth, biomass, succession or ecology dynamics — land cover is a
  class, not a plant;
* no weathering rate: G9 owns it and its delivered volumes are taken as declared;
* no world generation, no file IO, no default-world wiring;
* no silent coordinate snapping: a reference point that is not a cell centre must pass
  an explicit accepted offset, mirroring ``geology_properties.reference_points_to_cells``.

Status is always explicit
-------------------------
Every output field carries one of: ``computed``, ``declared``, ``pending`` (a required
input is missing) or ``not_available``. A ``pending`` field is never treated as zero
and a ``declared`` engineering constant is never presented as a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np


__all__ = [
    "ALGORITHM",
    "COVER_CLASSES",
    "LIMITATIONS",
    "LandCoverParameters",
    "SCHEMA",
    "assess_land_cover",
    "bulk_thickness_m",
    "describe",
    "soil_water_capacity_mm",
]


ALGORITHM = "environment-land-cover-v1"
SCHEMA = "environment-land-cover-v1"

#: Cover classes, ordered from least to most developed. The **order is part of the
#: contract**: a class is chosen by comparing the normalized suitabilities, and index
#: order is what makes the comparison stable and reproducible.
COVER_CLASSES = (
    "bare_rock",
    "sparse",
    "grass",
    "shrub",
    "forest",
    "wetland",
)
BARE_ROCK, SPARSE, GRASS, SHRUB, FOREST, WETLAND = range(len(COVER_CLASSES))

STATUS_COMPUTED = "computed"
STATUS_DECLARED = "declared"
STATUS_PENDING = "pending"
STATUS_NOT_AVAILABLE = "not_available"

LIMITATIONS = (
    "land cover is a classified surface condition, not vegetation: no biomass, no "
    "growth, no succession and no species competition is modelled.",
    "soil thickness is bulk thickness derived from a parent **solid** volume and a "
    "declared porosity; it is not a measured soil depth and not an equivalent solid "
    "thickness.",
    "soil water capacity and the G5 bucket state are different quantities: capacity is "
    "how much the layer could hold, the bucket state is what it holds now. Neither is "
    "derived from the other.",
    "available_water_fraction, the suitability weights and every threshold below are "
    "declared engineering assumptions, not calibrated values.",
    "the parent material is whatever the caller declares (G9 delivered volumes in the "
    "default use); this module does not weather rock itself.",
    "no channel, no routing, no erosion and no sediment transport is touched.",
)


# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LandCoverParameters:
    """Declared engineering constants. Every one is an assumption, not a measurement."""

    #: Fraction of the bulk layer that can hold plant-available water (field capacity
    #: minus wilting point, as a fraction of bulk). Declared, not measured.
    available_water_fraction: float = 0.15
    #: Below this bulk thickness the surface is exposed rock regardless of climate.
    rock_thickness_m: float = 0.02
    #: Bulk thickness at which the material stops being the limiting factor.
    full_thickness_m: float = 1.0
    #: Temperature (°C) that counts as the favourable optimum for plant growth. Declared
    #: engineering value in the same unit as ``family_temperature_c``.
    temperature_optimum_c: float = 14.0
    #: Half-width (°C) of the favourable temperature window; outside it the temperature
    #: score falls to zero linearly.
    temperature_tolerance_c: float = 16.0
    #: Weight of each driver in the suitability score. They sum to 1.
    weight_temperature: float = 0.35
    weight_water: float = 0.40
    weight_material: float = 0.25
    #: Suitability thresholds that separate the cover classes (inclusive lower bounds).
    sparse_threshold: float = 0.15
    grass_threshold: float = 0.35
    shrub_threshold: float = 0.55
    forest_threshold: float = 0.75
    #: Standing water above this fraction of capacity makes the site a wetland.
    wetland_water_fraction: float = 0.85

    def __post_init__(self):
        for name in ("available_water_fraction", "rock_thickness_m",
                     "full_thickness_m", "temperature_optimum_c",
                     "temperature_tolerance_c", "weight_temperature",
                     "weight_water", "weight_material", "sparse_threshold",
                     "grass_threshold", "shrub_threshold", "forest_threshold",
                     "wetland_water_fraction"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0.0):
                raise ValueError(
                    "invalid %s: a finite nonnegative number is required" % (name,))
        if not self.available_water_fraction < 1.0:
            raise ValueError("available_water_fraction must be below 1")
        if not 0.0 < self.full_thickness_m:
            raise ValueError("full_thickness_m must be positive")
        if not 0.0 < self.temperature_tolerance_c:
            raise ValueError("temperature_tolerance_c must be positive")
        weights = (self.weight_temperature, self.weight_water, self.weight_material)
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("driver weights must sum to 1, got %r" % (sum(weights),))
        if not (0.0 < self.sparse_threshold < self.grass_threshold
                < self.shrub_threshold < self.forest_threshold <= 1.0):
            raise ValueError("class thresholds must be strictly increasing in (0, 1]")
        if not 0.0 <= self.wetland_water_fraction <= 1.0:
            raise ValueError("wetland_water_fraction must lie in 0..1")

    @property
    def identity_sha256(self):
        return _digest({"schema": SCHEMA, "algorithm": ALGORITHM,
                        "parameters": {name: getattr(self, name)
                                       for name in self.__dataclass_fields__}})


# --------------------------------------------------------------------------- #
# digests and small guards
# --------------------------------------------------------------------------- #

def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload):
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _array_digest(array):
    values = np.ascontiguousarray(np.asarray(array))
    hasher = hashlib.sha256()
    hasher.update(str(values.shape).encode("ascii"))
    hasher.update(values.dtype.str.encode("ascii"))
    hasher.update(values.tobytes(order="C"))
    return hasher.hexdigest()


def _positive(value, name, maximum):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0.0 < value <= maximum):
        raise ValueError("invalid %s: finite positive <= %g required" % (name, maximum))
    return float(value)


# --------------------------------------------------------------------------- #
# the two conversions this module owns
# --------------------------------------------------------------------------- #

def bulk_thickness_m(solid_m3, *, porosity, horizontal_area_m2):
    """Bulk soil thickness from a parent **solid** volume.

    ``bulk = solid / ((1 - porosity) * area)``. Dividing by the area alone would give an
    equivalent solid thickness and would understate the layer by ``1/(1-porosity)``.
    """
    solid = np.asarray(solid_m3, np.float64)
    if not np.isfinite(solid).all() or np.any(solid < 0.0):
        raise ValueError("finite nonnegative parent solid volume required")
    pore = np.asarray(porosity, np.float64)
    if not np.isfinite(pore).all() or np.any(pore < 0.0) or np.any(pore >= 1.0):
        raise ValueError("porosity must be finite and lie in [0, 1)")
    area = _positive(horizontal_area_m2, "horizontal_area_m2", 1e12)
    return solid / ((1.0 - pore) * area)


def soil_water_capacity_mm(thickness_m, parameters=None):
    """Water the layer could hold, in mm of depth. Capacity, never a stock."""
    params = parameters or LandCoverParameters()
    thickness = np.asarray(thickness_m, np.float64)
    if not np.isfinite(thickness).all() or np.any(thickness < 0.0):
        raise ValueError("finite nonnegative thickness required")
    return thickness * 1000.0 * params.available_water_fraction


# --------------------------------------------------------------------------- #
# main entry
# --------------------------------------------------------------------------- #

def assess_land_cover(
        *, parent_solid_m3, porosity, horizontal_area_m2,
        family_temperature_c, water_state_mm, water_capacity_reference_mm=None,
        hard_substrate=None, parameters=None, status=None):
    """Derive soil thickness, suitability and land cover from declared inputs.

    Parameters
    ----------
    parent_solid_m3 : [N] float64
        Parent **solid** volume per column (G9's ``soil_delivery.solid_m3``).
    porosity : [N] float64
        Rock pore fraction per column, in ``[0, 1)`` (the material property).
    horizontal_area_m2 : float
        Column footprint area. One value for the whole call: the columns must be an
        equal-area set, which the material grid guarantees.
    family_temperature_c : [N] float64
        The temperature the suitability is judged at. **Annual mean** in the default
        use, because that is what the declared temperature window is expressed in.
    water_state_mm : [3, N] or [N] float64
        The actual G5 water state. A ``[3, N]`` bucket state (soil/fast/slow) is summed;
        a ``[N]`` vector is taken as already-total soil water. Either way this is a
        **stock**, not a capacity.
    water_capacity_reference_mm : [N] float64, optional
        The capacity to compare the stock against. When omitted, the capacity derived
        from this call's own thickness is used and that choice is reported.
    hard_substrate : [N] bool, optional
        True where the surface is rock rather than loose material. Omitted means unknown
        and is reported as such.
    parameters : LandCoverParameters, optional
    status : dict, optional
        Per-input status labels (``family_temperature``, ``water_state``, ``material``).
        Anything not marked computed is carried through as declared/pending.

    Returns
    -------
    dict with the three separated products plus a per-field status map. No field of
    this output is a measurement of a real soil.
    """
    params = parameters or LandCoverParameters()
    if not isinstance(params, LandCoverParameters):
        raise ValueError("LandCoverParameters required")

    solid = np.asarray(parent_solid_m3, np.float64).reshape(-1)
    pore = np.asarray(porosity, np.float64).reshape(-1)
    temperature = np.asarray(family_temperature_c, np.float64).reshape(-1)
    cells = solid.size
    if cells == 0:
        raise ValueError("at least one column is required")
    for name, array in (("porosity", pore), ("family_temperature_c", temperature)):
        if array.size != cells:
            raise ValueError("%s must provide one value per column" % (name,))
        if not np.isfinite(array).all():
            raise ValueError("%s must be finite" % (name,))

    water = np.asarray(water_state_mm, np.float64)
    if water.ndim == 2:
        if water.shape != (3, cells):
            raise ValueError("a bucket water state must be [3, N]")
        water_total = water.sum(axis=0)
        water_shape_reported = [3, cells]
    elif water.ndim == 1:
        if water.size != cells:
            raise ValueError("a water state vector must provide one value per column")
        water_total = water
        water_shape_reported = [cells]
    else:
        raise ValueError("water_state_mm must be [3, N] or [N]")
    if not np.isfinite(water_total).all() or np.any(water_total < 0.0):
        raise ValueError("finite nonnegative water state required")

    thickness = bulk_thickness_m(solid, porosity=pore,
                                 horizontal_area_m2=horizontal_area_m2)
    capacity = soil_water_capacity_mm(thickness, params)
    if water_capacity_reference_mm is None:
        capacity_reference = capacity
        capacity_source = "derived_from_this_call_thickness"
    else:
        capacity_reference = np.asarray(water_capacity_reference_mm, np.float64).reshape(-1)
        if capacity_reference.size != cells or not np.isfinite(capacity_reference).all() \
                or np.any(capacity_reference < 0.0):
            raise ValueError("water_capacity_reference_mm must be finite nonnegative [N]")
        capacity_source = "caller_declared"

    # --- suitability: three separate normalized drivers, then one weighted score -------
    # temperature: a declared window in **degC** around a declared optimum in degC, zero
    # outside the tolerance. Both are parameters of this module, not measured optima.
    normalised_temperature = np.clip(
        1.0 - np.abs(temperature - params.temperature_optimum_c)
        / params.temperature_tolerance_c, 0.0, 1.0)
    # water: the standing stock relative to the capacity it is compared against.
    water_ratio = np.zeros(cells, np.float64)
    positive = capacity_reference > 0.0
    np.divide(water_total, capacity_reference, out=water_ratio, where=positive)
    normalised_water = np.clip(water_ratio, 0.0, 1.0)
    # material: bulk thickness relative to the declared full-support thickness.
    normalised_material = np.clip(thickness / params.full_thickness_m, 0.0, 1.0)

    suitability = (params.weight_temperature * normalised_temperature
                   + params.weight_water * normalised_water
                   + params.weight_material * normalised_material)

    # --- land cover: an actual class, consuming all three drivers ---------------------
    cover = np.full(cells, BARE_ROCK, np.int64)
    cover = np.where(suitability >= params.sparse_threshold, SPARSE, cover)
    cover = np.where(suitability >= params.grass_threshold, GRASS, cover)
    cover = np.where(suitability >= params.shrub_threshold, SHRUB, cover)
    cover = np.where(suitability >= params.forest_threshold, FOREST, cover)
    # Rock is rock whatever the climate says; a layer thinner than rock_thickness_m cannot
    # carry a developed cover either.
    too_thin = thickness < params.rock_thickness_m
    cover = np.where(too_thin, BARE_ROCK, cover)
    if hard_substrate is not None:
        substrate = np.asarray(hard_substrate, bool).reshape(-1)
        if substrate.size != cells:
            raise ValueError("hard_substrate must provide one value per column")
        cover = np.where(substrate, BARE_ROCK, cover)
        substrate_status = STATUS_DECLARED
    else:
        substrate_status = STATUS_PENDING
    # Standing water above the declared fraction is a wetland, not a drier class.
    wetland = water_ratio >= params.wetland_water_fraction
    cover = np.where(wetland & ~too_thin, WETLAND, cover)

    cover_names = np.asarray([COVER_CLASSES[int(v)] for v in cover])

    status = dict(status or {})
    field_status = {
        "parent_solid_m3": status.get("material", STATUS_DECLARED),
        "porosity": status.get("material", STATUS_DECLARED),
        "soil_thickness_bulk_m": STATUS_COMPUTED,
        "soil_water_capacity_mm": STATUS_DECLARED,
        "water_state_total_mm": status.get("water_state", STATUS_DECLARED),
        "family_temperature_c": status.get("family_temperature", STATUS_DECLARED),
        "suitability": STATUS_COMPUTED,
        "land_cover": (STATUS_COMPUTED if substrate_status == STATUS_DECLARED
                        else STATUS_PENDING),
        "land_cover_hard_substrate": substrate_status,
    }
    if status.get("family_temperature") == STATUS_PENDING \
            or status.get("water_state") == STATUS_PENDING:
        # A missing driver leaves the class undefined rather than silently guessed.
        field_status["suitability"] = STATUS_PENDING
        field_status["land_cover"] = STATUS_PENDING
        cover_names = np.full(cells, "pending", dtype=object).astype(str)

    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "columns": int(cells),
        "horizontal_area_m2": float(horizontal_area_m2),
        "soil_thickness_bulk_m": thickness,
        "soil_water_capacity_mm": capacity,
        "soil_water_capacity_source": capacity_source,
        "water_capacity_reference_mm": capacity_reference,
        "water_state_total_mm": water_total,
        "water_state_shape": water_shape_reported,
        "water_ratio_of_capacity": water_ratio,
        "family_temperature_c": temperature,
        "normalised_temperature": normalised_temperature,
        "normalised_water": normalised_water,
        "normalised_material": normalised_material,
        "suitability": suitability,
        "land_cover_index": cover,
        "land_cover": cover_names,
        "cover_classes": list(COVER_CLASSES),
        "porosity": pore,
        "parameters_identity_sha256": params.identity_sha256,
        "parameters": {name: getattr(params, name)
                       for name in params.__dataclass_fields__},
        "identity": {
            "inputs_sha256": _digest({
                "parent_solid_m3": _array_digest(solid),
                "porosity": _array_digest(pore),
                "family_temperature_c": _array_digest(temperature),
                "water_state": _array_digest(water),
                "horizontal_area_m2": float(horizontal_area_m2),
                "parameters": params.identity_sha256,
            }),
        },
        "field_status": field_status,
        "units": {
            "soil_thickness_bulk_m": "m_bulk",
            "soil_water_capacity_mm": "mm",
            "water_state_total_mm": "mm",
            "family_temperature_c": "degC",
            "porosity": "1",
            "suitability": "1_normalised",
            "normalised_temperature": "1_normalised",
            "normalised_water": "1_normalised",
            "normalised_material": "1_normalised",
            "water_ratio_of_capacity": "1_ratio",
            "land_cover": "class_label",
        },
        "limitations": list(LIMITATIONS),
    }


def describe():
    """Static declaration for review (no numeric effect)."""
    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "cover_classes": list(COVER_CLASSES),
        "thickness_conversion": (
            "bulk_thickness_m = solid_m3 / ((1 - porosity) * horizontal_area_m2); "
            "dividing by the area alone gives an equivalent solid thickness"),
        "capacity_conversion": (
            "soil_water_capacity_mm = bulk_thickness_m * 1000 * available_water_fraction; "
            "a capacity, never a stock"),
        "separated_products": ["soil", "suitability", "land_cover"],
        "never": [
            "solid volume divided by area reported as a soil thickness",
            "capacity reported as a water stock, or the stock as a capacity",
            "land cover derived from annual precipitation alone",
            "a pending input silently read as zero",
            "a reference point snapped onto a cell centre",
            "vegetation growth, biomass or succession",
            "a weathering rate (G9 owns it)",
        ],
        "parameters": {name: getattr(LandCoverParameters(), name)
                       for name in LandCoverParameters.__dataclass_fields__},
        "limitations": list(LIMITATIONS),
    }
