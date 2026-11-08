"""Real-rock lithology catalogue plus a simplified two-level noise distribution.

Scope of this module (phase 1, user-approved simplification)
-----------------------------------------------------------
* The attribute table lists rocks that actually exist and are common, grouped in
  the three standard classes (igneous / sedimentary / metamorphic).
* The spatial distribution is a **simplified noise rule**: a low-frequency field
  decides the class, then a mid-frequency field plus a few high-frequency patches
  decide which rock of that class is present.
* It is **not** a tectonic, plate, subsidence, volcanic-arc or sediment-provenance
  reconstruction. Phase 2 replaces the distribution rule; the attribute table is
  kept.

Provenance of the numbers
-------------------------
Every numeric attribute in :data:`ROCK_TABLE` is an **engineering reference value
chosen from published ranges and qualitative rock descriptions, not a measured or
calibrated property of any field site** (``PROVENANCE``). Mohs hardness and
porosity are order-of-magnitude reference values. ``erodibility_index``,
``bed_hardness`` and ``bank_hardness`` are derived by the documented formulas below
from those reference values, so they carry exactly the same uncalibrated status.
The rock table also declares ``synthetic_lithology: True`` / ``measured_lithology:
False`` in every saved bundle, matching the convention of
``td_material_field.py``.

The distribution samples **absolute world coordinates** only, so a query does not
depend on window origin, tile order or load order; the same coordinate always
returns the same rock, bit for bit.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, save_bundle


SCHEMA = "td-lithology-field-v1"
ALGORITHM = "td-lithology-noise-v1"
#: Per-window cell budget, the same figure the continuous material field uses.
MAX_CELLS = 1024 ** 2
DEFAULT_WORLD_SEED = 20261020
PROVENANCE = "engineering_reference_values_uncalibrated"
SEED_DERIVATION = "sha256('terragenesis-lithology-v1|<world_seed>|<purpose>')[0:8] big-endian"

CLASS_IDS = ("igneous", "sedimentary", "metamorphic")
CLASS_NAMES_ZH = {"igneous": "岩浆岩", "sedimentary": "沉积岩", "metamorphic": "变质岩"}

#: Engineering weights of the formulas that derive the 0-1 resistance fields.
#: They are a declared rule, not a fit to measurements.
ERODIBILITY_WEIGHTS = {
    "hardness_complement": 0.45,
    "fracture_density": 0.20,
    "layering": 0.15,
    "solubility": 0.10,
    "porosity_normalized": 0.10,
}
MOHS_FLOOR = 1.0
MOHS_CEILING = 7.0
POROSITY_CEILING = 0.40
BANK_LAYERING_PENALTY = 0.25
BANK_SOLUBILITY_PENALTY = 0.12
HARDNESS_FLOOR = 0.02
HARDNESS_CEILING = 0.98

DEFAULT_PARAMETERS = {
    "class_primary_scale_m": 220000.0,
    "class_secondary_scale_m": 92000.0,
    "class_secondary_weight": 0.35,
    "rock_scale_m": 30000.0,
    "patch_scale_m": 8000.0,
    "patch_weight": 0.20,
    "class_weights": {"igneous": 0.30, "sedimentary": 0.45, "metamorphic": 0.25},
    "rock_weights": {
        "igneous": {"granite": 0.30, "basalt": 0.30, "andesite": 0.15,
                    "rhyolite": 0.08, "gabbro": 0.07, "tuff": 0.10},
        "sedimentary": {"limestone": 0.20, "sandstone": 0.28, "shale": 0.22,
                        "conglomerate": 0.08, "mudstone": 0.15, "dolomite": 0.07},
        "metamorphic": {"schist": 0.30, "gneiss": 0.28, "marble": 0.10,
                        "quartzite": 0.10, "slate": 0.14, "hornfels": 0.08},
    },
}


# ---------------------------------------------------------------------------
# Rock attribute table
# ---------------------------------------------------------------------------
#: id, name_zh, name_en, class, mohs_hardness, layering, fracture_density,
#: solubility, porosity, within-class abundance weight.
_RAW_ROCKS = (
    ("granite", "花岗岩", "granite", "igneous", 6.5, 0.05, 0.30, 0.02, 0.010, 0.30),
    ("basalt", "玄武岩", "basalt", "igneous", 6.0, 0.25, 0.45, 0.02, 0.050, 0.30),
    ("andesite", "安山岩", "andesite", "igneous", 5.5, 0.20, 0.40, 0.03, 0.060, 0.15),
    ("rhyolite", "流纹岩", "rhyolite", "igneous", 6.5, 0.35, 0.40, 0.02, 0.040, 0.08),
    ("gabbro", "辉长岩", "gabbro", "igneous", 6.5, 0.10, 0.30, 0.01, 0.020, 0.07),
    ("tuff", "凝灰岩", "tuff", "igneous", 3.5, 0.60, 0.70, 0.10, 0.300, 0.10),
    ("limestone", "石灰岩", "limestone", "sedimentary", 3.0, 0.75, 0.55, 0.85, 0.080, 0.20),
    ("sandstone", "砂岩", "sandstone", "sedimentary", 4.5, 0.70, 0.60, 0.05, 0.150, 0.28),
    ("shale", "页岩", "shale", "sedimentary", 2.5, 0.95, 0.85, 0.05, 0.120, 0.22),
    ("conglomerate", "砾岩", "conglomerate", "sedimentary", 5.0, 0.55, 0.50, 0.10, 0.120, 0.08),
    ("mudstone", "泥岩", "mudstone", "sedimentary", 2.5, 0.85, 0.70, 0.05, 0.200, 0.15),
    ("dolomite", "白云岩", "dolomite", "sedimentary", 3.5, 0.80, 0.60, 0.70, 0.060, 0.07),
    ("schist", "片岩", "schist", "metamorphic", 3.5, 0.95, 0.75, 0.05, 0.030, 0.30),
    ("gneiss", "片麻岩", "gneiss", "metamorphic", 6.0, 0.80, 0.55, 0.03, 0.020, 0.28),
    ("marble", "大理岩", "marble", "metamorphic", 3.5, 0.15, 0.40, 0.60, 0.010, 0.10),
    ("quartzite", "石英岩", "quartzite", "metamorphic", 7.0, 0.10, 0.35, 0.01, 0.010, 0.10),
    ("slate", "板岩", "slate", "metamorphic", 3.0, 0.98, 0.85, 0.02, 0.020, 0.14),
    ("hornfels", "角岩", "hornfels", "metamorphic", 6.5, 0.30, 0.60, 0.02, 0.020, 0.08),
)


def derive_resistance_fields(mohs_hardness, layering, fracture_density, solubility, porosity):
    """Convert reference rock descriptions into the three 0-1 resistance fields.

    Documented rule (same weights as :data:`ERODIBILITY_WEIGHTS`, no fitting):

    ``h = clip((mohs - 1) / (7 - 1), 0, 1)``
        normalised Mohs hardness between talc (1) and quartz (7);
    ``p = clip(porosity / 0.40, 0, 1)``
        porosity normalised by a declared 0.40 upper reference;
    ``erodibility_index = 0.45 (1 - h) + 0.20 fracture + 0.15 layering
                         + 0.10 solubility + 0.10 p``
        i.e. weak in the mineral sense, broken, bedded, soluble and porous rock
        erodes more readily;
    ``bed_hardness = clip(1 - erodibility_index, 0.02, 0.98)``
        the complement, in the units the existing discharge-geometry rule uses;
    ``bank_hardness = clip(bed_hardness - 0.25 layering - 0.12 solubility,
                          0.02, 0.98)``
        banks are weakened further by bedding planes (undercut and collapse) and
        by karst solution, which is why layered carbonate banks fail before the
        bed does. Bank hardness never exceeds bed hardness.

    These are generation-rule inputs, not measured rock strength or an erosion
    rate.
    """
    values = (mohs_hardness, layering, fracture_density, solubility, porosity)
    for name, value in zip(("mohs_hardness", "layering", "fracture_density",
                            "solubility", "porosity"), values):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(name + " must be a finite number")
    hardness_norm = min(max((float(mohs_hardness) - MOHS_FLOOR) / (MOHS_CEILING - MOHS_FLOOR), 0.0), 1.0)
    porosity_norm = min(max(float(porosity) / POROSITY_CEILING, 0.0), 1.0)
    erodibility = (ERODIBILITY_WEIGHTS["hardness_complement"] * (1.0 - hardness_norm)
                   + ERODIBILITY_WEIGHTS["fracture_density"] * float(fracture_density)
                   + ERODIBILITY_WEIGHTS["layering"] * float(layering)
                   + ERODIBILITY_WEIGHTS["solubility"] * float(solubility)
                   + ERODIBILITY_WEIGHTS["porosity_normalized"] * porosity_norm)
    erodibility = min(max(erodibility, 0.0), 1.0)
    bed_hardness = min(max(1.0 - erodibility, HARDNESS_FLOOR), HARDNESS_CEILING)
    bank_hardness = bed_hardness - BANK_LAYERING_PENALTY * float(layering) - BANK_SOLUBILITY_PENALTY * float(solubility)
    bank_hardness = min(max(bank_hardness, HARDNESS_FLOOR), min(bed_hardness, HARDNESS_CEILING))
    return erodibility, bed_hardness, bank_hardness


def _rock_record(raw):
    identifier, name_zh, name_en, class_id, mohs, layering, fracture, solubility, porosity, weight = raw
    erodibility, bed_hardness, bank_hardness = derive_resistance_fields(
        mohs, layering, fracture, solubility, porosity)
    return {
        "id": identifier,
        "name_zh": name_zh,
        "name_en": name_en,
        "class": class_id,
        "class_name_zh": CLASS_NAMES_ZH[class_id],
        "mohs_hardness": float(mohs),
        "erodibility_index": erodibility,
        "bed_hardness": bed_hardness,
        "bank_hardness": bank_hardness,
        "layering": float(layering),
        "fracture_density": float(fracture),
        "solubility": float(solubility),
        "porosity": float(porosity),
        "abundance_weight": float(weight),
        "units": {"mohs_hardness": "dimensionless Mohs scale",
                  "erodibility_index": "1 (0 resistant .. 1 highly erodible)",
                  "bed_hardness": "1 (0 weak .. 1 strong), discharge-geometry input",
                  "bank_hardness": "1 (0 weak .. 1 strong), discharge-geometry input",
                  "layering": "1", "fracture_density": "1", "solubility": "1",
                  "porosity": "volume fraction"},
        "value_status": PROVENANCE,
    }


ROCK_TABLE = tuple(_rock_record(raw) for raw in _RAW_ROCKS)
ROCK_ORDER = tuple(record["id"] for record in ROCK_TABLE)
ROCK_POSITION = {identifier: position for position, identifier in enumerate(ROCK_ORDER)}
ROCK_BY_ID = {record["id"]: record for record in ROCK_TABLE}
ROCK_ORDER_BY_CLASS = {
    class_id: tuple(record["id"] for record in ROCK_TABLE if record["class"] == class_id)
    for class_id in CLASS_IDS
}

_BED_HARDNESS_TABLE = np.asarray([record["bed_hardness"] for record in ROCK_TABLE], np.float64)
_BANK_HARDNESS_TABLE = np.asarray([record["bank_hardness"] for record in ROCK_TABLE], np.float64)
_ERODIBILITY_TABLE = np.asarray([record["erodibility_index"] for record in ROCK_TABLE], np.float64)
_CLASS_POSITION_TABLE = np.asarray(
    [CLASS_IDS.index(record["class"]) for record in ROCK_TABLE], np.int64)


# ---------------------------------------------------------------------------
# Deterministic seeds and coordinate-only value noise
# ---------------------------------------------------------------------------
SEED_PURPOSES = ("class_primary", "class_secondary", "rock_medium", "patch_high")

_MIX_X = np.uint64(0x9E3779B185EBCA87)
_MIX_Z = np.uint64(0xC2B2AE3D27D4EB4F)
_MIX_1 = np.uint64(0xBF58476D1CE4E5B9)
_MIX_2 = np.uint64(0x94D049BB133111EB)
_LATTICE_LIMIT = 2.0 ** 50


def derive_subseed(world_seed, purpose):
    """Derive a stable uint64 sub-seed from the world seed and a purpose name.

    The rule is recorded in :data:`SEED_DERIVATION`; it never uses wall-clock time,
    system entropy or Python's ``hash()``.
    """
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, (int, np.integer)):
        raise ValueError("world_seed must be an integer")
    if not 0 <= int(world_seed) < 2 ** 64:
        raise ValueError("world_seed must be a uint64")
    if purpose not in SEED_PURPOSES:
        raise ValueError("unknown seed purpose: " + repr(purpose))
    payload = "terragenesis-lithology-v1|" + str(int(world_seed)) + "|" + purpose
    digest = hashlib.sha256(payload.encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def lithology_subseeds(world_seed=DEFAULT_WORLD_SEED):
    """Return the four sub-seeds used by the distribution rule."""
    return {purpose: derive_subseed(world_seed, purpose) for purpose in SEED_PURPOSES}


def _lattice_unit(lattice_x, lattice_z, seed):
    with np.errstate(over="ignore"):
        value = lattice_x.astype(np.uint64) * _MIX_X
        value = value ^ (lattice_z.astype(np.uint64) * _MIX_Z)
        value = value ^ np.uint64(seed)
        value = (value ^ (value >> np.uint64(30))) * _MIX_1
        value = (value ^ (value >> np.uint64(27))) * _MIX_2
        value = value ^ (value >> np.uint64(31))
    return (value >> np.uint64(11)).astype(np.float64) / float(2 ** 53)


def _value_noise(global_x, global_z, scale_m, seed):
    """Quintic value noise on a lattice defined in absolute metres."""
    coordinate_x = np.asarray(global_x, np.float64) / scale_m
    coordinate_z = np.asarray(global_z, np.float64) / scale_m
    if np.any(np.abs(coordinate_x) > _LATTICE_LIMIT) or np.any(np.abs(coordinate_z) > _LATTICE_LIMIT):
        raise ValueError("global lattice coordinate exceeds precision budget")
    lattice_x = np.floor(coordinate_x).astype(np.int64)
    lattice_z = np.floor(coordinate_z).astype(np.int64)
    fraction_x = coordinate_x - lattice_x
    fraction_z = coordinate_z - lattice_z
    smooth_x = fraction_x ** 3 * (fraction_x * (fraction_x * 6.0 - 15.0) + 10.0)
    smooth_z = fraction_z ** 3 * (fraction_z * (fraction_z * 6.0 - 15.0) + 10.0)
    upper = (_lattice_unit(lattice_x, lattice_z, seed) * (1.0 - smooth_x)
             + _lattice_unit(lattice_x + 1, lattice_z, seed) * smooth_x)
    lower = (_lattice_unit(lattice_x, lattice_z + 1, seed) * (1.0 - smooth_x)
             + _lattice_unit(lattice_x + 1, lattice_z + 1, seed) * smooth_x)
    return upper * (1.0 - smooth_z) + lower * smooth_z


# The two mixed noise fields below are stationary, so their marginal quantiles are
# independent of position and of the noise *scale*. They were sampled once in
# lattice space (scale = 1.0, 2048 x 2048 quasi-uniform offsets, 4,194,304 values)
# and are frozen here as constants (see .scratch/lithology-01/derive_quantiles.py).
# Thresholds are then read off these tables instead of being hand-tuned magic
# numbers. Entry ``i`` is the quantile at probability ``i / 80``; the far tails are
# the raw sampled extremes, so the tables are NOT clipped to [0, 1] and scores
# outside them fall into the first / last class, which is the intended tail
# behaviour.
#
#   CLASS = 0.65 * noise(class_primary_scale_m) + 0.35 * noise(class_secondary_scale_m)
#   ROCK  = 0.80 * noise(rock_scale_m)        + 0.20 * noise(patch_scale_m)
QUANTILE_TABLE_POINTS = 81
QUANTILE_SAMPLE_GRID = 2048
QUANTILE_SAMPLE_COUNT = 4_194_304
CLASS_NOISE_QUANTILES = (
    0.001816476, 0.141964583, 0.178514510, 0.203909328, 0.223884550, 0.240783030,
    0.255572455, 0.268607043, 0.280496225, 0.291428375, 0.301646722, 0.311232643,
    0.320278411, 0.328848633, 0.337069448, 0.344967400, 0.352567154, 0.359910636,
    0.367004639, 0.373947669, 0.380729582, 0.387355019, 0.393884103, 0.400289731,
    0.406615087, 0.412868263, 0.418983958, 0.425048550, 0.431033979, 0.436998099,
    0.442876696, 0.448722549, 0.454518374, 0.460292481, 0.466004909, 0.471698370,
    0.477357123, 0.483019179, 0.488669687, 0.494322348, 0.499986920, 0.505598254,
    0.511253209, 0.516917792, 0.522578999, 0.528285189, 0.534008082, 0.539754227,
    0.545486583, 0.551287388, 0.557117601, 0.563008463, 0.568961825, 0.574955967,
    0.581001481, 0.587114549, 0.593329000, 0.599586846, 0.605998573, 0.612526422,
    0.619134571, 0.625877690, 0.632799117, 0.639874231, 0.647195776, 0.654745353,
    0.662578853, 0.670743544, 0.679295563, 0.688345910, 0.697958909, 0.708156673,
    0.719183288, 0.731081076, 0.744152151, 0.758811433, 0.775711233, 0.795849740,
    0.821317129, 0.858111144, 0.997716440,
)
ROCK_NOISE_QUANTILES = (
    0.001215837, 0.123498628, 0.155627057, 0.177942914, 0.195982787, 0.211378746,
    0.225068577, 0.237735259, 0.249573142, 0.260599417, 0.271161844, 0.281147392,
    0.290807979, 0.300125874, 0.309129617, 0.317893788, 0.326412607, 0.334779287,
    0.343020685, 0.351041967, 0.358890364, 0.366646385, 0.374279852, 0.381741463,
    0.389219916, 0.396598745, 0.403818636, 0.410981992, 0.418106683, 0.425089222,
    0.432083009, 0.438989271, 0.445909097, 0.452715422, 0.459497310, 0.466251544,
    0.473003671, 0.479826058, 0.486493191, 0.493192949, 0.499947893, 0.506711554,
    0.513476583, 0.520215085, 0.526962217, 0.533748947, 0.540502269, 0.547300521,
    0.554201314, 0.561106062, 0.567963814, 0.574945494, 0.581998070, 0.589064886,
    0.596226855, 0.603451489, 0.610761811, 0.618145817, 0.625652351, 0.633306058,
    0.640959959, 0.648783788, 0.656856797, 0.664980666, 0.673353681, 0.681924054,
    0.690743163, 0.699761637, 0.708994143, 0.718675012, 0.728727297, 0.739212132,
    0.750250467, 0.762041444, 0.774637968, 0.788269956, 0.803635076, 0.821686689,
    0.844225737, 0.876414702, 0.997628687,
)


def _quantile(table, probability):
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    position = float(probability) * (len(table) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(table) - 1)
    fraction = position - lower
    return float(table[lower]) * (1.0 - fraction) + float(table[upper]) * fraction


def _thresholds(weights, keys, table):
    """Cumulative quantile thresholds of a declared weight vector."""
    total = 0.0
    for key in keys:
        total += float(weights[key])
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("weights must have a positive finite sum")
    cumulative = 0.0
    bounds = []
    for key in keys:
        cumulative += float(weights[key]) / total
        bounds.append(_quantile(table, min(cumulative, 1.0)))
    for index in range(1, len(bounds)):
        if bounds[index] < bounds[index - 1]:
            raise ValueError("weight vector produced decreasing thresholds")
    return tuple(bounds)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def rock_table_identity():
    """SHA256 of the attribute table, so a table edit cannot pass silently."""
    return hashlib.sha256(_canonical(list(ROCK_TABLE)).encode("utf-8")).hexdigest()


def rock_table():
    """Return a deep copy of the attribute table as plain dictionaries."""
    return json.loads(_canonical(list(ROCK_TABLE)))


def rock_record(identifier):
    """Return a deep copy of one rock record by id (``name_en``)."""
    if identifier not in ROCK_BY_ID:
        raise KeyError("unknown rock: " + repr(identifier))
    return json.loads(_canonical(ROCK_BY_ID[identifier]))


def rock_ids(rock_index_array):
    """Map an int64 rock-index array to rock ids."""
    values = np.asarray(rock_index_array)
    if values.dtype != np.int64:
        raise ValueError("rock index array must be int64")
    if values.size and (values.min() < 0 or values.max() >= len(ROCK_ORDER)):
        raise ValueError("rock index out of range")
    flat = [ROCK_ORDER[int(value)] for value in values.ravel()]
    return np.asarray(flat, dtype=object).reshape(values.shape)


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------
def _positive(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(name + " must be finite and positive")
    return result


def _weights_block(supplied, expected_keys, name):
    if not isinstance(supplied, dict) or set(supplied) != set(expected_keys):
        raise ValueError(name + " keys must be exactly " + ",".join(sorted(expected_keys)))
    result = {}
    total = 0.0
    for key in expected_keys:
        value = _positive(supplied[key], name + "." + key)
        result[key] = value
        total += value
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError(name + " must sum to a positive finite total")
    return result


def normalize_parameters(parameters=None):
    """Validate and fill the distribution rule; unknown keys are rejected."""
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown lithology parameters")
    merged = {**DEFAULT_PARAMETERS, **supplied}
    config = {}
    for name in ("class_primary_scale_m", "class_secondary_scale_m", "rock_scale_m", "patch_scale_m"):
        config[name] = _positive(merged[name], name)
    for name in ("class_secondary_weight", "patch_weight"):
        value = merged[name]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError(name + " must be numeric")
        if not 0.0 <= float(value) < 1.0:
            raise ValueError(name + " must be in [0, 1)")
        config[name] = float(value)
    config["class_weights"] = _weights_block(merged["class_weights"], CLASS_IDS, "class_weights")
    rock_weights = merged["rock_weights"]
    if not isinstance(rock_weights, dict) or set(rock_weights) != set(CLASS_IDS):
        raise ValueError("rock_weights must have exactly the three class keys")
    config["rock_weights"] = {
        class_id: _weights_block(rock_weights[class_id], ROCK_ORDER_BY_CLASS[class_id],
                                 "rock_weights." + class_id)
        for class_id in CLASS_IDS
    }
    return config


def _shape(shape):
    if len(shape) != 2:
        raise ValueError("shape must be two positive integers")
    for size in shape:
        if isinstance(size, (bool, np.bool_)) or not isinstance(size, (int, np.integer)) or size <= 0:
            raise ValueError("shape must be two positive integers")
    result = (int(shape[0]), int(shape[1]))
    if math.prod(result) > MAX_CELLS:
        raise ValueError("lithology cell budget exceeded")
    return result


def _spacing(spacing_m):
    return _positive(spacing_m, "spacing_m")


def _origin(origin_m_xz, spacing):
    origin = np.asarray(origin_m_xz, np.float64)
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("origin_m_xz must contain two finite coordinates")
    grid_origin = origin / spacing
    if np.any(np.abs(grid_origin) > 2.0 ** 50) or not np.allclose(
            grid_origin, np.rint(grid_origin), rtol=0.0, atol=1e-8):
        raise ValueError("origin must align with the global spacing grid")
    return origin, np.rint(grid_origin).astype(np.int64)


def _check_world_seed(world_seed):
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, (int, np.integer)):
        raise ValueError("world_seed must be an integer")
    if not 0 <= int(world_seed) < 2 ** 64:
        raise ValueError("world_seed must be a uint64")
    return int(world_seed)


# ---------------------------------------------------------------------------
# The distribution rule
# ---------------------------------------------------------------------------
class _Rule:
    """Precomputed thresholds and lookup tables for one seed/parameter set."""

    __slots__ = ("config", "subseeds", "class_bounds", "rock_bounds", "class_rock_index")

    def __init__(self, config, subseeds):
        self.config = config
        self.subseeds = subseeds
        self.class_bounds = _thresholds(config["class_weights"], CLASS_IDS, CLASS_NOISE_QUANTILES)
        self.rock_bounds = {
            class_id: _thresholds(config["rock_weights"][class_id],
                                  ROCK_ORDER_BY_CLASS[class_id], ROCK_NOISE_QUANTILES)
            for class_id in CLASS_IDS
        }
        self.class_rock_index = {
            class_id: np.asarray([ROCK_POSITION[rock] for rock in ROCK_ORDER_BY_CLASS[class_id]], np.int64)
            for class_id in CLASS_IDS
        }

    def sample(self, global_x, global_z):
        config = self.config
        primary = _value_noise(global_x, global_z, config["class_primary_scale_m"], self.subseeds["class_primary"])
        secondary = _value_noise(global_x, global_z, config["class_secondary_scale_m"], self.subseeds["class_secondary"])
        weight = config["class_secondary_weight"]
        class_score = (1.0 - weight) * primary + weight * secondary
        class_index = _band(class_score, self.class_bounds)

        medium = _value_noise(global_x, global_z, config["rock_scale_m"], self.subseeds["rock_medium"])
        patch = _value_noise(global_x, global_z, config["patch_scale_m"], self.subseeds["patch_high"])
        patch_weight = config["patch_weight"]
        rock_score = (1.0 - patch_weight) * medium + patch_weight * patch

        rock_index = np.zeros(class_score.shape, np.int64)
        for position, class_id in enumerate(CLASS_IDS):
            selected = class_index == position
            if not selected.any():
                continue
            local = _band(rock_score[selected], self.rock_bounds[class_id])
            rock_index[selected] = self.class_rock_index[class_id][local]
        return class_index, rock_index


def _band(values, bounds):
    bounds = np.asarray(bounds, np.float64)
    position = np.searchsorted(bounds, values, side="left")
    return np.clip(position, 0, bounds.size - 1).astype(np.int64)


def _validate_rule_outputs(class_index, rock_index, shape):
    if class_index.shape != shape or rock_index.shape != shape:
        raise ValueError("lithology field shape mismatch")
    if class_index.dtype != np.int64 or rock_index.dtype != np.int64:
        raise ValueError("lithology indices must be int64")
    if np.any((class_index < 0) | (class_index >= len(CLASS_IDS))):
        raise ValueError("class index out of range")
    if np.any((rock_index < 0) | (rock_index >= len(ROCK_ORDER))):
        raise ValueError("rock index out of range")
    if np.any(_CLASS_POSITION_TABLE[rock_index] != class_index):
        raise ValueError("rock does not belong to its declared class")


def _fields(class_index, rock_index):
    """Read-only-by-convention float/int fields derived from the rock table.

    ``np.array(..., order="C", copy=True)`` is used instead of
    ``np.ascontiguousarray`` because the latter silently promotes a 0-d array to
    shape ``(1,)``, which would make a single-point query disagree with a grid
    query on shape.
    """
    class_index = np.array(class_index, dtype=np.int64, order="C", copy=True)
    rock_index = np.array(rock_index, dtype=np.int64, order="C", copy=True)
    return {
        "class_index": class_index,
        "rock_index": rock_index,
        "bed_hardness": np.array(_BED_HARDNESS_TABLE[rock_index], np.float64, order="C", copy=True),
        "bank_hardness": np.array(_BANK_HARDNESS_TABLE[rock_index], np.float64, order="C", copy=True),
        "erodibility_index": np.array(_ERODIBILITY_TABLE[rock_index], np.float64, order="C", copy=True),
    }


# ---------------------------------------------------------------------------
# Public sampling entry points
# ---------------------------------------------------------------------------
def sample_lithology_points(x_m, z_m, *, world_seed=DEFAULT_WORLD_SEED, parameters=None):
    """Sample the lithology rule at absolute world coordinates (metres).

    ``x_m`` and ``z_m`` are broadcastable; the result is a dict of same-shape
    arrays. Only absolute coordinates enter, so point sets may be shuffled, split
    across windows or queried one at a time and still agree bit for bit. Scalars
    give scalar-shaped (0-d) arrays, so a single point query is allowed.
    """
    seed = _check_world_seed(world_seed)
    config = normalize_parameters(parameters)
    x = np.asarray(x_m, np.float64)
    z = np.asarray(z_m, np.float64)
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("coordinates must be finite")
    shape = np.broadcast_shapes(x.shape, z.shape)
    x, z = np.broadcast_arrays(x, z)
    rule = _Rule(config, {purpose: derive_subseed(seed, purpose) for purpose in SEED_PURPOSES})
    class_index, rock_index = rule.sample(x, z)
    return _fields(class_index.reshape(shape), rock_index.reshape(shape))


def sample_lithology(shape, *, origin_m_xz, spacing_m, world_seed=DEFAULT_WORLD_SEED,
                     parameters=None, protected_mask=None):
    """Sample the rule on cell centres of a global metric grid.

    Cell centres are ``origin + (index + 0.5) * spacing``; the same absolute
    coordinates are sampled whether the window is large, small or offset, so
    tiles joined later are seamless.
    """
    shape = _shape(shape)
    spacing = _spacing(spacing_m)
    origin, grid_origin = _origin(origin_m_xz, spacing)
    seed = _check_world_seed(world_seed)
    config = normalize_parameters(parameters)
    if protected_mask is None:
        protected = np.zeros(shape, bool)
    else:
        protected = np.asarray(protected_mask)
        if protected.shape != shape or protected.dtype != np.dtype(bool):
            raise ValueError("protected_mask must be same-shape boolean array")
        protected = np.array(protected, dtype=bool, copy=True)

    global_x = (grid_origin[0] + np.arange(shape[1], dtype=np.int64) + 0.5) * spacing
    global_z = (grid_origin[1] + np.arange(shape[0], dtype=np.int64) + 0.5) * spacing
    if not np.isfinite(global_x).all() or not np.isfinite(global_z).all():
        raise ValueError("global coordinate overflow")
    rule = _Rule(config, {purpose: derive_subseed(seed, purpose) for purpose in SEED_PURPOSES})
    class_index, rock_index = rule.sample(global_x[None, :], global_z[:, None])
    class_index = np.broadcast_to(class_index, shape).copy()
    rock_index = np.broadcast_to(rock_index, shape).copy()
    _validate_rule_outputs(class_index, rock_index, shape)

    arrays = _fields(class_index, rock_index)
    arrays["protected_mask"] = protected
    metadata = _metadata(shape, origin, spacing, seed, config)
    bundle = {"arrays": arrays, "metadata": metadata,
              "identity_sha256": identity(arrays, metadata)}
    return bundle


def _metadata(shape, origin, spacing, seed, config):
    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "format_version": 1,
        "shape": list(shape),
        "origin_m_xz": [float(origin[0]), float(origin[1])],
        "spacing_m": spacing,
        "world_seed": int(seed),
        "subseeds": {purpose: derive_subseed(seed, purpose) for purpose in SEED_PURPOSES},
        "seed_derivation": SEED_DERIVATION,
        "parameters": {
            "class_primary_scale_m": config["class_primary_scale_m"],
            "class_secondary_scale_m": config["class_secondary_scale_m"],
            "class_secondary_weight": config["class_secondary_weight"],
            "rock_scale_m": config["rock_scale_m"],
            "patch_scale_m": config["patch_scale_m"],
            "patch_weight": config["patch_weight"],
            "class_weights": config["class_weights"],
            "rock_weights": config["rock_weights"],
        },
        "coordinate_convention": "X east; Z south; [z,x]; cell centres; absolute world metres",
        "coordinate_absolute": True,
        "class_order": list(CLASS_IDS),
        "rock_order": list(ROCK_ORDER),
        "rock_table_sha256": rock_table_identity(),
        "synthetic_lithology": True,
        "measured_lithology": False,
        "value_status": PROVENANCE,
        "distribution_model": "simplified_two_level_value_noise",
        "tectonic_context": False,
        "erodibility_rule": {
            "weights": dict(ERODIBILITY_WEIGHTS),
            "mohs_range": [MOHS_FLOOR, MOHS_CEILING],
            "porosity_reference_max": POROSITY_CEILING,
            "bank_layering_penalty": BANK_LAYERING_PENALTY,
            "bank_solubility_penalty": BANK_SOLUBILITY_PENALTY,
            "hardness_bounds": [HARDNESS_FLOOR, HARDNESS_CEILING],
        },
        "units": {"bed_hardness": "1", "bank_hardness": "1", "erodibility_index": "1",
                  "class_index": "index into class_order", "rock_index": "index into rock_order"},
        "limitations": [
            "distribution is a simplified noise rule, not a plate/tectonic/sedimentary-basin reconstruction",
            "attribute values are engineering reference values and are not calibrated",
            "no strata column, dip, age or fault offset is modelled here",
            "depth below the surface is not sampled; one rock is assigned per map column",
            "phase 2 replaces the distribution rule and keeps the attribute table",
        ],
    }


def discharge_geometry_inputs(bundle):
    """Return ``(bed_hardness, bank_hardness)`` copies ready for the existing rule."""
    validate_lithology_field(bundle)
    arrays = bundle["arrays"]
    return arrays["bed_hardness"].copy(), arrays["bank_hardness"].copy()


def hardness_lookup(rock_id):
    """Return ``(bed_hardness, bank_hardness)`` for one rock id."""
    record = ROCK_BY_ID.get(rock_id)
    if record is None:
        raise ValueError("unknown rock: " + repr(rock_id))
    return record["bed_hardness"], record["bank_hardness"]


# ---------------------------------------------------------------------------
# Validation, reporting and storage
# ---------------------------------------------------------------------------
def validate_lithology_field(bundle):
    """Reject a bundle that does not recompute from its own declared inputs."""
    if not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid lithology bundle structure")
    arrays, metadata = bundle["arrays"], bundle["metadata"]
    if identity(arrays, metadata) != bundle["identity_sha256"]:
        raise ValueError("lithology bundle identity mismatch")
    if metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM or metadata.get("format_version") != 1:
        raise ValueError("unsupported lithology identity")
    if metadata.get("synthetic_lithology") is not True or metadata.get("measured_lithology") is not False:
        raise ValueError("lithology bundle must declare synthetic, unmeasured status")
    if metadata.get("value_status") != PROVENANCE:
        raise ValueError("lithology bundle must declare uncalibrated reference values")
    if metadata.get("tectonic_context") is not False:
        raise ValueError("phase-1 distribution has no tectonic context and must say so")
    if metadata.get("rock_table_sha256") != rock_table_identity():
        raise ValueError("rock attribute table differs from the one recorded by the bundle")
    if metadata.get("rock_order") != list(ROCK_ORDER) or metadata.get("class_order") != list(CLASS_IDS):
        raise ValueError("lithology ordering mismatch")
    shape = _shape(metadata["shape"])
    if set(arrays) != {"class_index", "rock_index", "bed_hardness", "bank_hardness",
                       "erodibility_index", "protected_mask"}:
        raise ValueError("lithology array names mismatch")
    class_index = arrays["class_index"]
    rock_index = arrays["rock_index"]
    if class_index.dtype != np.int64 or rock_index.dtype != np.int64:
        raise ValueError("lithology indices must be int64")
    _validate_rule_outputs(np.ascontiguousarray(class_index), np.ascontiguousarray(rock_index), shape)
    for name, table in (("bed_hardness", _BED_HARDNESS_TABLE),
                        ("bank_hardness", _BANK_HARDNESS_TABLE),
                        ("erodibility_index", _ERODIBILITY_TABLE)):
        expected = table[rock_index]
        values = arrays[name]
        if values.shape != shape or values.dtype != np.float64 or not np.array_equal(values, expected):
            raise ValueError("lithology field " + name + " is inconsistent with the rock table")
    if np.any(_BANK_HARDNESS_TABLE[rock_index] > _BED_HARDNESS_TABLE[rock_index]):
        raise ValueError("bank hardness must not exceed bed hardness")
    reference = sample_lithology(shape, origin_m_xz=metadata["origin_m_xz"], spacing_m=metadata["spacing_m"],
                                 world_seed=metadata["world_seed"], parameters=metadata["parameters"],
                                 protected_mask=arrays["protected_mask"])
    if reference["identity_sha256"] != bundle["identity_sha256"]:
        raise ValueError("lithology provenance mismatch: field does not recompute")
    return True


def compose_report(bundle):
    """Return class and rock proportions actually present in a sampled field."""
    validate_lithology_field(bundle)
    arrays = bundle["arrays"]
    class_index = arrays["class_index"]
    rock_index = arrays["rock_index"]
    total = int(class_index.size)
    classes = {}
    for position, class_id in enumerate(CLASS_IDS):
        count = int((class_index == position).sum())
        classes[class_id] = {"name_zh": CLASS_NAMES_ZH[class_id], "count": count,
                            "fraction": count / total}
    rocks = {}
    for identifier in ROCK_ORDER:
        count = int((rock_index == ROCK_POSITION[identifier]).sum())
        rocks[identifier] = {"name_zh": ROCK_BY_ID[identifier]["name_zh"],
                            "class": ROCK_BY_ID[identifier]["class"],
                            "count": count, "fraction": count / total}
    return {"total_cells": total, "classes": classes, "rocks": rocks,
            "distinct_rocks": sum(1 for value in rocks.values() if value["count"] > 0),
            "distinct_classes": sum(1 for value in classes.values() if value["count"] > 0)}


def save_lithology_field(bundle, path):
    return save_bundle(path, bundle, validator=validate_lithology_field)


def load_lithology_field(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256,
                       validator=validate_lithology_field, max_bytes=256 * 1024 * 1024)
