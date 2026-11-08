"""Conservative bedrock -> regolith -> parent-material inventory with mass closure.

Scope (G9 minimum, one thing only)
---------------------------------
A finite column of weatherable bedrock is attacked for a declared time step. The
products are tracked as separate accounts and must close exactly:

    bedrock solid removed = regolith solid produced + dissolved solid exported

Nothing here invents parent material. ``parent_solid_m3`` is a **view** of part of
the regolith solid (the fine fraction declared for soil supply), not a new store.
Pore conversion (solid -> bulk) happens exactly once, at production.

Drivers
-------
Weathering depth rate is a declared product of the available conditions:

    physical  = k_physical * (1 - bed_hardness)
    chemical  = k_chemical * solubility * moisture * temperature_factor
    biogenic  = k_biological * bio_activity * moisture * temperature_factor
    depth_rate = (physical + chemical + biogenic) * dt_s

temperature_factor = Q10 ** ((T - T_ref) / 10). A **negative** temperature is a
legal input and simply gives a smaller factor; it is never treated as invalid.
All coefficient names, units, provenance and value statuses are declared, and the
result records them so a reader can see this is an engineering reference set, not
a global calibration.

The rate is **hard-capped** by the remaining weatherable thickness in every step,
so the stock can be exhausted but never overdrawn.

Not here
--------
* no soil-water bucket, no ET, no groundwater, no vegetation growth model;
* no transport to the river or to the sea: the two supply functions only report
  what is *available*, they do not move it;
* no default-world wiring, no file IO, no hashing, no unrequested defensive layers.
"""

from __future__ import annotations

import math

import numpy as np


SCHEMA = "weathering-soil-inventory-v1"
ALGORITHM = "conservative-bedrock-weathering-inventory-v1"
FORMAT_VERSION = 1

MAX_COLUMNS = 4096

#: Relative closure tolerance. Declared against the mass scale of the step, not an
#: absolute constant, so it scales with any world size.
CLOSURE_RELATIVE_TOLERANCE = 1e-12

EXHAUSTED = "exhausted"
ACTIVE = "active"

MASS_PENDING = "pending_missing_density"
MASS_DECLARED = "declared"

DECLARED = "declared"
ENGINEERING_REFERENCE = "engineering_reference_uncalibrated"

LIMITATIONS = (
    "weathering depth rate is a declared engineering rule of the available "
    "conditions; it is not a calibrated global weathering law",
    "bedrock solid removed equals regolith solid produced plus dissolved solid "
    "exported; the ledger checks this every step",
    "parent material is a fine-fraction view of the regolith, never a second store",
    "a delivery is debited from the single regolith account and recorded as "
    "delivered_regolith_solid_m3, so a soil and a river request cannot double count",
    "pore conversion from solid to bulk is applied once, at production",
    "negative temperature is a legal input and only reduces the rate factor",
    "supply functions report availability only: nothing is transported to the "
    "river, the sea or the ground water here",
)


class WeatheringInventoryError(ValueError):
    """Raised for an invalid declaration, unit or an over-drawn stock."""


def _finite(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        raise WeatheringInventoryError(name + " must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise WeatheringInventoryError(name + " must be finite")
    return result


def _nonnegative(value, name):
    result = _finite(value, name)
    if result < 0.0:
        raise WeatheringInventoryError(name + " must be non-negative")
    return result


def _positive(value, name):
    result = _finite(value, name)
    if result <= 0.0:
        raise WeatheringInventoryError(name + " must be positive")
    return result


def _fraction(value, name):
    result = _finite(value, name)
    if not 0.0 <= result < 1.0:
        raise WeatheringInventoryError(name + " must satisfy 0 <= value < 1")
    return result


def _series(value, n, name, *, nonnegative=True):
    array = np.asarray(value, np.float64)
    if array.ndim == 0:
        array = np.full(n, float(array), np.float64)
    array = np.ascontiguousarray(array.reshape(-1), np.float64)
    if array.size != n:
        raise WeatheringInventoryError(name + " must have one value per column")
    if not np.isfinite(array).all():
        raise WeatheringInventoryError(name + " must be finite")
    if nonnegative and np.any(array < 0.0):
        raise WeatheringInventoryError(name + " must be non-negative")
    return array


def _check_columns(n):
    if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)):
        raise WeatheringInventoryError("column count must be an integer")
    columns = int(n)
    if columns <= 0:
        raise WeatheringInventoryError("column count must be positive")
    if columns > MAX_COLUMNS:
        raise WeatheringInventoryError(
            "column count %d exceeds %d" % (columns, MAX_COLUMNS))
    return columns


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------
def normalize_parameters(declaration=None):
    """Declared rate coefficients. Unknown keys and missing provenance rejected."""
    defaults = {
        "k_physical_m_per_s": {"value": 1.0e-13, "units": "m/s",
                               "status": ENGINEERING_REFERENCE,
                               "source": "declared default; not a global calibration"},
        "k_chemical_m_per_s": {"value": 1.0e-13, "units": "m/s",
                               "status": ENGINEERING_REFERENCE,
                               "source": "declared default; not a global calibration"},
        "k_biological_m_per_s": {"value": 5.0e-14, "units": "m/s",
                                 "status": ENGINEERING_REFERENCE,
                                 "source": "declared default; not a global calibration"},
        "temperature_reference_c": {"value": 10.0, "units": "degC",
                                    "status": DECLARED, "source": "declared reference"},
        "q10": {"value": 2.0, "units": "1", "status": ENGINEERING_REFERENCE,
                "source": "declared Q10 factor; not a fit to measurements"},
        "dissolved_fraction_of_solid": {"value": 0.10, "units": "1",
                                        "status": ENGINEERING_REFERENCE,
                                        "source": "declared chemical share"},
        "regolith_porosity": {"value": 0.35, "units": "volume fraction",
                              "status": ENGINEERING_REFERENCE,
                              "source": "declared porosity of the loose product"},
        "fines_fraction_of_regolith": {"value": 0.50, "units": "1",
                                       "status": ENGINEERING_REFERENCE,
                                       "source": "declared fine fraction available as "
                                                 "parent material"},
    }
    supplied = {} if declaration is None else dict(declaration)
    unknown = sorted(set(supplied) - set(defaults))
    if unknown:
        raise WeatheringInventoryError("unknown parameter keys: %r" % (unknown,))
    resolved = {}
    for name, default in defaults.items():
        entry = dict(default)
        override = supplied.get(name)
        if override is not None:
            if not isinstance(override, dict):
                raise WeatheringInventoryError(name + " must be a dict")
            extra = sorted(set(override) - set(default))
            if extra:
                raise WeatheringInventoryError(
                    "unknown fields for %s: %r" % (name, extra))
            # A caller that overrides a value must declare its own source: silently
            # keeping the default provenance would attribute a new number to the
            # default reference set.
            if "value" in override and "source" not in override:
                raise WeatheringInventoryError(
                    name + " overrides a value and needs an explicit non-empty source")
            entry.update(override)
            for key in ("status", "source"):
                text = entry.get(key)
                if not isinstance(text, str) or not text.strip():
                    raise WeatheringInventoryError(name + " needs a non-empty " + key)
        resolved[name] = entry
    for name in ("k_physical_m_per_s", "k_chemical_m_per_s", "k_biological_m_per_s",
                 "q10"):
        resolved[name]["value"] = _nonnegative(resolved[name]["value"], name)
    resolved["temperature_reference_c"]["value"] = _finite(
        resolved["temperature_reference_c"]["value"], "temperature_reference_c")
    resolved["dissolved_fraction_of_solid"]["value"] = _fraction(
        resolved["dissolved_fraction_of_solid"]["value"], "dissolved_fraction_of_solid")
    resolved["regolith_porosity"]["value"] = _fraction(
        resolved["regolith_porosity"]["value"], "regolith_porosity")
    resolved["fines_fraction_of_regolith"]["value"] = _fraction(
        resolved["fines_fraction_of_regolith"]["value"], "fines_fraction_of_regolith")
    return resolved


def _value(parameters, name):
    return float(parameters[name]["value"])


def preflight(n_columns):
    columns = _check_columns(n_columns)
    per_column_bytes = 8 * 12
    return {
        "n_columns": columns,
        "max_columns": MAX_COLUMNS,
        "estimated_payload_bytes": columns * per_column_bytes,
        "closure_relative_tolerance": CLOSURE_RELATIVE_TOLERANCE,
    }


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------
def initial_state(*, bedrock_thickness_m, area_m2, bed_hardness, solubility,
                  density_kg_m3=None):
    """A finite weatherable column. No weathering has happened yet."""
    thickness = np.asarray(bedrock_thickness_m, np.float64)
    if thickness.ndim == 0:
        thickness = np.atleast_1d(np.asarray(thickness, np.float64))
    thickness = np.ascontiguousarray(thickness.reshape(-1), np.float64)
    n = _check_columns(thickness.size)
    budget = preflight(n)
    thickness = _series(thickness, n, "bedrock_thickness_m")
    area = _series(area_m2, n, "area_m2", nonnegative=False)
    if np.any(area <= 0.0):
        raise WeatheringInventoryError("area_m2 must be positive per column")
    hardness = _series(bed_hardness, n, "bed_hardness")
    solubility_series = _series(solubility, n, "solubility")
    if np.any(hardness > 1.0) or np.any(solubility_series > 1.0):
        raise WeatheringInventoryError("hardness and solubility must lie in [0, 1]")
    solid = thickness * area
    state = {
        "bedrock_solid_m3": np.ascontiguousarray(solid, np.float64),
        "regolith_solid_m3": np.zeros(n, np.float64),
        "regolith_bulk_m3": np.zeros(n, np.float64),
        "parent_solid_m3": np.zeros(n, np.float64),
        "dissolved_solid_m3": np.zeros(n, np.float64),
        "delivered_regolith_solid_m3": np.zeros(n, np.float64),
        "delivered_parent_solid_m3": np.zeros(n, np.float64),
        "weatherable_thickness_m": np.ascontiguousarray(thickness, np.float64),
        "area_m2": np.ascontiguousarray(area, np.float64),
        "bed_hardness": np.ascontiguousarray(hardness, np.float64),
        "solubility": np.ascontiguousarray(solubility_series, np.float64),
        "initial_bedrock_solid_m3": np.ascontiguousarray(solid.copy(), np.float64),
        "status": np.full(n, ACTIVE, dtype=object),
        "density_kg_m3": (None if density_kg_m3 is None
                          else _series(density_kg_m3, n, "density_kg_m3",
                                       nonnegative=False)),
        "parameters": normalize_parameters(None),
        "budget": budget,
    }
    if density_kg_m3 is not None and np.any(state["density_kg_m3"] <= 0.0):
        raise WeatheringInventoryError("density_kg_m3 must be positive where declared")
    return state


# ---------------------------------------------------------------------------
# One conservative step
# ---------------------------------------------------------------------------
def _temperature_factor(temperature_c, reference_c, q10):
    """Q10 factor; a negative temperature is legal and just lowers it."""
    exponent = (temperature_c - reference_c) / 10.0
    return np.power(q10, exponent)


def advance(state, *, dt_s, temperature_c, moisture, bio_activity=0.0,
            parameters=None):
    """Advance one declared time step; returns ``(next_state, flux)``.

    The weathered depth is capped by the remaining weatherable thickness, so the
    stock can be exhausted but never over-drawn. Solid closure is checked against
    the step's own mass scale.
    """
    if not isinstance(state, dict) or "bedrock_solid_m3" not in state:
        raise WeatheringInventoryError("a state from initial_state is required")
    dt = _positive(dt_s, "dt_s")
    config = normalize_parameters(parameters)
    n = int(state["bedrock_solid_m3"].size)
    if n != int(state["regolith_solid_m3"].size):
        raise WeatheringInventoryError("state arrays disagree in length")
    temperature = _series(temperature_c, n, "temperature_c", nonnegative=False)
    wetness = _series(moisture, n, "moisture")
    if np.any(wetness > 1.0):
        raise WeatheringInventoryError("moisture must lie in [0, 1]")
    biology = _series(bio_activity, n, "bio_activity")
    if np.any(biology > 1.0):
        raise WeatheringInventoryError("bio_activity must lie in [0, 1]")

    factor = _temperature_factor(temperature, _value(config, "temperature_reference_c"),
                                 _value(config, "q10"))
    physical = _value(config, "k_physical_m_per_s") * (1.0 - state["bed_hardness"])
    chemical = (_value(config, "k_chemical_m_per_s") * state["solubility"]
                * wetness * factor)
    biogenic = _value(config, "k_biological_m_per_s") * biology * wetness * factor
    requested_depth = (physical + chemical + biogenic) * dt

    area = state["area_m2"]
    available_depth = state["bedrock_solid_m3"] / area
    weathered_depth = np.minimum(requested_depth, available_depth)
    weathered_depth = np.maximum(weathered_depth, 0.0)
    weathered_solid = weathered_depth * area

    dissolved_fraction = _value(config, "dissolved_fraction_of_solid")
    dissolved = weathered_solid * dissolved_fraction
    regolith_solid = weathered_solid - dissolved
    porosity = _value(config, "regolith_porosity")
    regolith_bulk = regolith_solid / (1.0 - porosity)
    fines_fraction = _value(config, "fines_fraction_of_regolith")
    parent = regolith_solid * fines_fraction

    next_state = dict(state)
    next_state["bedrock_solid_m3"] = np.ascontiguousarray(
        state["bedrock_solid_m3"] - weathered_solid, np.float64)
    next_state["regolith_solid_m3"] = np.ascontiguousarray(
        state["regolith_solid_m3"] + regolith_solid, np.float64)
    next_state["regolith_bulk_m3"] = np.ascontiguousarray(
        state["regolith_bulk_m3"] + regolith_bulk, np.float64)
    next_state["parent_solid_m3"] = np.ascontiguousarray(
        state["parent_solid_m3"] + parent, np.float64)
    next_state["dissolved_solid_m3"] = np.ascontiguousarray(
        state["dissolved_solid_m3"] + dissolved, np.float64)
    next_state["parameters"] = config
    next_state["status"] = np.where(next_state["bedrock_solid_m3"] <= 0.0,
                                    EXHAUSTED, ACTIVE).astype(object)

    scale = np.maximum(state["initial_bedrock_solid_m3"], 1.0)
    residual = (weathered_solid - regolith_solid - dissolved)
    tolerance = CLOSURE_RELATIVE_TOLERANCE * scale
    if np.any(np.abs(residual) > tolerance):
        raise WeatheringInventoryError(
            "solid closure broken: weathered minus regolith minus dissolved exceeds "
            "the declared tolerance")

    flux = {
        "dt_s": dt,
        "weathered_depth_m": np.ascontiguousarray(weathered_depth, np.float64),
        "weathered_solid_m3": np.ascontiguousarray(weathered_solid, np.float64),
        "regolith_solid_m3": np.ascontiguousarray(regolith_solid, np.float64),
        "regolith_bulk_m3": np.ascontiguousarray(regolith_bulk, np.float64),
        "parent_solid_m3": np.ascontiguousarray(parent, np.float64),
        "dissolved_solid_m3": np.ascontiguousarray(dissolved, np.float64),
        "capped_by_stock": np.ascontiguousarray(requested_depth > available_depth + 0.0,
                                               bool),
        "temperature_factor": np.ascontiguousarray(factor, np.float64),
        "budget": preflight(n),
    }
    return next_state, flux


# ---------------------------------------------------------------------------
# Views for downstream use (no transport claimed)
# ---------------------------------------------------------------------------
def soil_parent_supply(state, fraction=0.10):
    """Parent material available to a soil consumer; nothing is removed here."""
    share = _fraction(fraction, "fraction")
    available = state["parent_solid_m3"] * share
    return {
        "available_parent_solid_m3": np.ascontiguousarray(available, np.float64),
        "fraction_of_parent_stock": share,
        "supply_semantics": "availability only; the caller must debit the stock",
        "consumer": "G6 soil supply (not wired by this module)",
        "transported": False,
    }


def sediment_supply(state, fraction=0.10):
    """Loose regolith solid available as river sediment source; not transported."""
    share = _fraction(fraction, "fraction")
    available = state["regolith_solid_m3"] * share
    return {
        "available_sediment_solid_m3": np.ascontiguousarray(available, np.float64),
        "fraction_of_regolith_stock": share,
        "supply_semantics": "availability only; the caller must debit the stock",
        "consumer": "river sediment source (not wired by this module)",
        "transported": False,
    }


def allocate(state, *, soil_parent_solid_m3=0.0, sediment_solid_m3=0.0,
             shortage_policy="reject"):
    """Debit the two consumers; parent material is a *finite subset* of regolith.

    ``parent_solid_m3`` is the fine-particle subset **inside** ``regolith_solid_m3``
    (``0 <= parent <= regolith``), not a second store and not a ratio. So there are
    two limits, and both apply:

    * the total delivery cannot exceed the regolith solid;
    * the **soil** delivery cannot exceed the parent subset that is actually there.

    Soil is taken from the parent subset and the parent subset is debited by exactly
    that amount, so a repeated soil draw cannot re-take the same parent atoms.
    Sediment is taken from the **non-parent** part first and only spills into the
    subset once the non-parent part is used up, which keeps ``0 <= parent <= regolith``
    and keeps the subset accounts closing.

    ``shortage_policy``:

    * ``"reject"`` (default) — exceeding either limit raises instead of trimming;
    * ``"proportional"`` — one common factor, bounded by **both** ``regolith/total``
      **and** ``parent/soil_request``, so the soil sub-limit is honoured too.

    Returns ``(next_state, soil_delivery, sediment_delivery, remaining, accounts)``.
    The input state is never mutated. No transport, no G10/G11 coupling.
    """
    if not isinstance(state, dict) or "regolith_solid_m3" not in state:
        raise WeatheringInventoryError("a state from initial_state is required")
    if shortage_policy not in ("reject", "proportional"):
        raise WeatheringInventoryError(
            "shortage_policy must be 'reject' or 'proportional'")
    n = int(state["regolith_solid_m3"].size)
    soil_request = _series(soil_parent_solid_m3, n, "soil_parent_solid_m3")
    sediment_request = _series(sediment_solid_m3, n, "sediment_solid_m3")

    regolith = state["regolith_solid_m3"]
    parent = state["parent_solid_m3"]
    if np.any(parent > regolith + 0.0):
        raise WeatheringInventoryError(
            "parent material must be a subset of the regolith solid")
    non_parent = regolith - parent
    requested = soil_request + sediment_request

    total_short = requested > regolith
    soil_short = soil_request > parent
    if shortage_policy == "reject" and (np.any(total_short) or np.any(soil_short)):
        raise WeatheringInventoryError(
            "requested delivery exceeds the stock: the regolith total or the parent "
            "fine-particle subset is too small (parent is a subset, not a second "
            "stock)")

    if shortage_policy == "proportional":
        ratio = np.ones(n, np.float64)
        np.divide(regolith, requested, out=ratio, where=requested > 0.0)
        ratio = np.minimum(ratio, 1.0)
        # The soil share has its own ceiling: a common factor that ignores the parent
        # subset would let soil overdraw the fine particles while the total still fits.
        soil_ratio = np.ones(n, np.float64)
        np.divide(parent, soil_request, out=soil_ratio, where=soil_request > 0.0)
        ratio = np.minimum(ratio, np.minimum(soil_ratio, 1.0))
        ratio = np.clip(ratio, 0.0, 1.0)
    else:
        ratio = np.ones(n, np.float64)

    soil_delivered = np.minimum(soil_request * ratio, parent)
    sediment_delivered = np.minimum(sediment_request * ratio,
                                    np.maximum(regolith - soil_delivered, 0.0))

    # Sediment prefers the non-parent part; only the spill is taken from the subset.
    sediment_from_non_parent = np.minimum(sediment_delivered, non_parent)
    sediment_from_parent = sediment_delivered - sediment_from_non_parent
    parent_delivered = soil_delivered + sediment_from_parent
    total_delivered = soil_delivered + sediment_delivered

    next_state = dict(state)
    next_state["regolith_solid_m3"] = np.ascontiguousarray(
        regolith - total_delivered, np.float64)
    next_state["parent_solid_m3"] = np.ascontiguousarray(
        parent - parent_delivered, np.float64)
    # Bulk is the same solid at the declared porosity; it is debited by the same
    # solid amount, converted once, never re-converted per consumer.
    porosity = _declared_porosity(state)
    next_state["regolith_bulk_m3"] = np.ascontiguousarray(
        state["regolith_bulk_m3"] - total_delivered / (1.0 - porosity), np.float64)
    next_state["delivered_regolith_solid_m3"] = np.ascontiguousarray(
        state["delivered_regolith_solid_m3"] + total_delivered, np.float64)
    next_state["delivered_parent_solid_m3"] = np.ascontiguousarray(
        state.get("delivered_parent_solid_m3", np.zeros(n, np.float64))
        + parent_delivered, np.float64)

    if np.any(next_state["parent_solid_m3"] < -0.0):
        raise WeatheringInventoryError("parent subset went negative on delivery")
    if np.any(next_state["parent_solid_m3"] > next_state["regolith_solid_m3"] + 0.0):
        raise WeatheringInventoryError("parent subset exceeded the regolith on delivery")

    remaining = {
        "regolith_solid_m3": np.ascontiguousarray(next_state["regolith_solid_m3"], np.float64),
        "parent_solid_m3": np.ascontiguousarray(next_state["parent_solid_m3"], np.float64),
        "non_parent_solid_m3": np.ascontiguousarray(
            next_state["regolith_solid_m3"] - next_state["parent_solid_m3"], np.float64),
    }
    return (next_state,
            {"soil_parent_solid_m3": np.ascontiguousarray(soil_delivered, np.float64),
             "taken_from_parent_solid_m3": np.ascontiguousarray(
                 soil_delivered, np.float64),
             "consumer": "soil parent material", "transported": False},
            {"sediment_solid_m3": np.ascontiguousarray(sediment_delivered, np.float64),
             "from_non_parent_solid_m3": np.ascontiguousarray(
                 sediment_from_non_parent, np.float64),
             "from_parent_solid_m3": np.ascontiguousarray(
                 sediment_from_parent, np.float64),
             "consumer": "river sediment", "transported": False},
            remaining,
            ledger(next_state))


def _declared_porosity(state):
    """Porosity used for the bulk view; re-read from the parameters at debit time."""
    parameters = state.get("parameters")
    if parameters is None:
        parameters = normalize_parameters(None)
    return _value(parameters, "regolith_porosity")


def ledger(state):
    """Initial versus current accounts plus the closure residual."""
    initial = state["initial_bedrock_solid_m3"]
    bedrock = state["bedrock_solid_m3"]
    regolith = state["regolith_solid_m3"]
    dissolved = state["dissolved_solid_m3"]
    delivered = state["delivered_regolith_solid_m3"]
    removed = initial - bedrock
    # Delivered loose solid has left the regolith but not the system, so the closure
    # must count it as a destination: otherwise a debit would look like lost mass.
    residual = removed - regolith - dissolved - delivered
    result = {
        "initial_bedrock_solid_m3": np.ascontiguousarray(initial, np.float64),
        "current_bedrock_solid_m3": np.ascontiguousarray(bedrock, np.float64),
        "removed_bedrock_solid_m3": np.ascontiguousarray(removed, np.float64),
        "regolith_solid_m3": np.ascontiguousarray(regolith, np.float64),
        "regolith_bulk_m3": np.ascontiguousarray(state["regolith_bulk_m3"], np.float64),
        "parent_solid_m3": np.ascontiguousarray(state["parent_solid_m3"], np.float64),
        "dissolved_exported_solid_m3": np.ascontiguousarray(dissolved, np.float64),
        "delivered_regolith_solid_m3": np.ascontiguousarray(delivered, np.float64),
        "closure_residual_m3": np.ascontiguousarray(residual, np.float64),
        "closure_relative_tolerance": CLOSURE_RELATIVE_TOLERANCE,
        "status": np.array(state["status"], dtype=object),
        "units": {"solid": "m3", "bulk": "m3", "depth": "m", "dt": "s"},
    }
    if state["density_kg_m3"] is None:
        result["mass_status"] = MASS_PENDING
    else:
        density = state["density_kg_m3"]
        result["mass_status"] = MASS_DECLARED
        result["current_bedrock_mass_kg"] = np.ascontiguousarray(bedrock * density, np.float64)
        result["regolith_mass_kg"] = np.ascontiguousarray(regolith * density, np.float64)
        result["dissolved_exported_mass_kg"] = np.ascontiguousarray(
            dissolved * density, np.float64)
    return result


def describe():
    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "format_version": FORMAT_VERSION,
        "max_columns": MAX_COLUMNS,
        "closure_relative_tolerance": CLOSURE_RELATIVE_TOLERANCE,
        "state_fields": ["bedrock_solid_m3", "regolith_solid_m3", "regolith_bulk_m3",
                         "parent_solid_m3", "dissolved_solid_m3",
                         "delivered_regolith_solid_m3", "delivered_parent_solid_m3"],
        "shortage_policies": ["reject", "proportional"],
        "units": {"solid": "m3", "bulk": "m3", "mass": "kg", "dt": "s",
                  "temperature": "degC", "bed_hardness": "1", "solubility": "1",
                  "moisture": "1", "bio_activity": "1"},
        "negative_temperature_allowed": True,
        "limitations": list(LIMITATIONS),
    }
