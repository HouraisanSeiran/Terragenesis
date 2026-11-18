"""Consolidated geology implementations; numeric expressions preserved."""
from __future__ import annotations
import hashlib as _i35_hashlib
import json as _i35_json
import math as _i35_math
import numpy as _i35_np
import hashlib as _i37_hashlib
import json as _i37_json
import math as _i37_math
import os as _i37_os
from pathlib import Path as _i37_Path
import tempfile as _i37_tempfile
import numpy as _i37_np
import hashlib as _i34_hashlib
import json as _i34_json
import math as _i34_math
import numpy as _i34_np
import math as _i36_math
import numpy as _i36_np
import math as _i38_math
from copy import deepcopy as _i38_deepcopy
import numpy as _i38_np
CATEGORY = 'D'
LITHOLOGY_SCHEMA = 'td-lithology-field-v1'
LITHOLOGY_ALGORITHM = 'td-lithology-noise-v1'
LITHOLOGY_MAX_CELLS = 1024 ** 2
DEFAULT_WORLD_SEED = 20261020
PROVENANCE = 'engineering_reference_values_uncalibrated'
SEED_DERIVATION = "sha256('terragenesis-lithology-v1|<world_seed>|<purpose>')[0:8] big-endian"
CLASS_IDS = ('igneous', 'sedimentary', 'metamorphic')
CLASS_NAMES_ZH = {'igneous': '岩浆岩', 'sedimentary': '沉积岩', 'metamorphic': '变质岩'}
ERODIBILITY_WEIGHTS = {'hardness_complement': 0.45, 'fracture_density': 0.2, 'layering': 0.15, 'solubility': 0.1, 'porosity_normalized': 0.1}
MOHS_FLOOR = 1.0
MOHS_CEILING = 7.0
POROSITY_CEILING = 0.4
BANK_LAYERING_PENALTY = 0.25
BANK_SOLUBILITY_PENALTY = 0.12
HARDNESS_FLOOR = 0.02
HARDNESS_CEILING = 0.98
LITHOLOGY_DEFAULT_PARAMETERS = {'class_primary_scale_m': 220000.0, 'class_secondary_scale_m': 92000.0, 'class_secondary_weight': 0.35, 'rock_scale_m': 30000.0, 'patch_scale_m': 8000.0, 'patch_weight': 0.2, 'class_weights': {'igneous': 0.3, 'sedimentary': 0.45, 'metamorphic': 0.25}, 'rock_weights': {'igneous': {'granite': 0.3, 'basalt': 0.3, 'andesite': 0.15, 'rhyolite': 0.08, 'gabbro': 0.07, 'tuff': 0.1}, 'sedimentary': {'limestone': 0.2, 'sandstone': 0.28, 'shale': 0.22, 'conglomerate': 0.08, 'mudstone': 0.15, 'dolomite': 0.07}, 'metamorphic': {'schist': 0.3, 'gneiss': 0.28, 'marble': 0.1, 'quartzite': 0.1, 'slate': 0.14, 'hornfels': 0.08}}}
_RAW_ROCKS = (('granite', '花岗岩', 'granite', 'igneous', 6.5, 0.05, 0.3, 0.02, 0.01, 0.3), ('basalt', '玄武岩', 'basalt', 'igneous', 6.0, 0.25, 0.45, 0.02, 0.05, 0.3), ('andesite', '安山岩', 'andesite', 'igneous', 5.5, 0.2, 0.4, 0.03, 0.06, 0.15), ('rhyolite', '流纹岩', 'rhyolite', 'igneous', 6.5, 0.35, 0.4, 0.02, 0.04, 0.08), ('gabbro', '辉长岩', 'gabbro', 'igneous', 6.5, 0.1, 0.3, 0.01, 0.02, 0.07), ('tuff', '凝灰岩', 'tuff', 'igneous', 3.5, 0.6, 0.7, 0.1, 0.3, 0.1), ('limestone', '石灰岩', 'limestone', 'sedimentary', 3.0, 0.75, 0.55, 0.85, 0.08, 0.2), ('sandstone', '砂岩', 'sandstone', 'sedimentary', 4.5, 0.7, 0.6, 0.05, 0.15, 0.28), ('shale', '页岩', 'shale', 'sedimentary', 2.5, 0.95, 0.85, 0.05, 0.12, 0.22), ('conglomerate', '砾岩', 'conglomerate', 'sedimentary', 5.0, 0.55, 0.5, 0.1, 0.12, 0.08), ('mudstone', '泥岩', 'mudstone', 'sedimentary', 2.5, 0.85, 0.7, 0.05, 0.2, 0.15), ('dolomite', '白云岩', 'dolomite', 'sedimentary', 3.5, 0.8, 0.6, 0.7, 0.06, 0.07), ('schist', '片岩', 'schist', 'metamorphic', 3.5, 0.95, 0.75, 0.05, 0.03, 0.3), ('gneiss', '片麻岩', 'gneiss', 'metamorphic', 6.0, 0.8, 0.55, 0.03, 0.02, 0.28), ('marble', '大理岩', 'marble', 'metamorphic', 3.5, 0.15, 0.4, 0.6, 0.01, 0.1), ('quartzite', '石英岩', 'quartzite', 'metamorphic', 7.0, 0.1, 0.35, 0.01, 0.01, 0.1), ('slate', '板岩', 'slate', 'metamorphic', 3.0, 0.98, 0.85, 0.02, 0.02, 0.14), ('hornfels', '角岩', 'hornfels', 'metamorphic', 6.5, 0.3, 0.6, 0.02, 0.02, 0.08))

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
    for name, value in zip(('mohs_hardness', 'layering', 'fracture_density', 'solubility', 'porosity'), values):
        if isinstance(value, (bool, _i35_np.bool_)) or not isinstance(value, (int, float)) or (not _i35_math.isfinite(value)):
            raise ValueError(name + ' must be a finite number')
    hardness_norm = min(max((float(mohs_hardness) - MOHS_FLOOR) / (MOHS_CEILING - MOHS_FLOOR), 0.0), 1.0)
    porosity_norm = min(max(float(porosity) / POROSITY_CEILING, 0.0), 1.0)
    erodibility = ERODIBILITY_WEIGHTS['hardness_complement'] * (1.0 - hardness_norm) + ERODIBILITY_WEIGHTS['fracture_density'] * float(fracture_density) + ERODIBILITY_WEIGHTS['layering'] * float(layering) + ERODIBILITY_WEIGHTS['solubility'] * float(solubility) + ERODIBILITY_WEIGHTS['porosity_normalized'] * porosity_norm
    erodibility = min(max(erodibility, 0.0), 1.0)
    bed_hardness = min(max(1.0 - erodibility, HARDNESS_FLOOR), HARDNESS_CEILING)
    bank_hardness = bed_hardness - BANK_LAYERING_PENALTY * float(layering) - BANK_SOLUBILITY_PENALTY * float(solubility)
    bank_hardness = min(max(bank_hardness, HARDNESS_FLOOR), min(bed_hardness, HARDNESS_CEILING))
    return (erodibility, bed_hardness, bank_hardness)

def _rock_record(raw):
    identifier, name_zh, name_en, class_id, mohs, layering, fracture, solubility, porosity, weight = raw
    erodibility, bed_hardness, bank_hardness = derive_resistance_fields(mohs, layering, fracture, solubility, porosity)
    return {'id': identifier, 'name_zh': name_zh, 'name_en': name_en, 'class': class_id, 'class_name_zh': CLASS_NAMES_ZH[class_id], 'mohs_hardness': float(mohs), 'erodibility_index': erodibility, 'bed_hardness': bed_hardness, 'bank_hardness': bank_hardness, 'layering': float(layering), 'fracture_density': float(fracture), 'solubility': float(solubility), 'porosity': float(porosity), 'abundance_weight': float(weight), 'units': {'mohs_hardness': 'dimensionless Mohs scale', 'erodibility_index': '1 (0 resistant .. 1 highly erodible)', 'bed_hardness': '1 (0 weak .. 1 strong), discharge-geometry input', 'bank_hardness': '1 (0 weak .. 1 strong), discharge-geometry input', 'layering': '1', 'fracture_density': '1', 'solubility': '1', 'porosity': 'volume fraction'}, 'value_status': PROVENANCE}
ROCK_TABLE = tuple((_rock_record(raw) for raw in _RAW_ROCKS))
ROCK_ORDER = tuple((record['id'] for record in ROCK_TABLE))
ROCK_POSITION = {identifier: position for position, identifier in enumerate(ROCK_ORDER)}
ROCK_BY_ID = {record['id']: record for record in ROCK_TABLE}
ROCK_ORDER_BY_CLASS = {class_id: tuple((record['id'] for record in ROCK_TABLE if record['class'] == class_id)) for class_id in CLASS_IDS}
_BED_HARDNESS_TABLE = _i35_np.asarray([record['bed_hardness'] for record in ROCK_TABLE], _i35_np.float64)
_BANK_HARDNESS_TABLE = _i35_np.asarray([record['bank_hardness'] for record in ROCK_TABLE], _i35_np.float64)
_ERODIBILITY_TABLE = _i35_np.asarray([record['erodibility_index'] for record in ROCK_TABLE], _i35_np.float64)
_CLASS_POSITION_TABLE = _i35_np.asarray([CLASS_IDS.index(record['class']) for record in ROCK_TABLE], _i35_np.int64)
SEED_PURPOSES = ('class_primary', 'class_secondary', 'rock_medium', 'patch_high')
_MIX_X = _i35_np.uint64(11400714785074694791)
_MIX_Z = _i35_np.uint64(14029467366897019727)
_MIX_1 = _i35_np.uint64(13787848793156543929)
_MIX_2 = _i35_np.uint64(10723151780598845931)
_LATTICE_LIMIT = 2.0 ** 50

def derive_subseed(world_seed, purpose):
    """Derive a stable uint64 sub-seed from the world seed and a purpose name.

    The rule is recorded in :data:`SEED_DERIVATION`; it never uses wall-clock time,
    system entropy or Python's ``hash()``.
    """
    if isinstance(world_seed, (bool, _i35_np.bool_)) or not isinstance(world_seed, (int, _i35_np.integer)):
        raise ValueError('world_seed must be an integer')
    if not 0 <= int(world_seed) < 2 ** 64:
        raise ValueError('world_seed must be a uint64')
    if purpose not in SEED_PURPOSES:
        raise ValueError('unknown seed purpose: ' + repr(purpose))
    payload = 'terragenesis-lithology-v1|' + str(int(world_seed)) + '|' + purpose
    digest = _i35_hashlib.sha256(payload.encode('ascii')).digest()
    return int.from_bytes(digest[:8], 'big')

def lithology_subseeds(world_seed=DEFAULT_WORLD_SEED):
    """Return the four sub-seeds used by the distribution rule."""
    return {purpose: derive_subseed(world_seed, purpose) for purpose in SEED_PURPOSES}

def _lattice_unit(lattice_x, lattice_z, seed):
    with _i35_np.errstate(over='ignore'):
        value = lattice_x.astype(_i35_np.uint64) * _MIX_X
        value = value ^ lattice_z.astype(_i35_np.uint64) * _MIX_Z
        value = value ^ _i35_np.uint64(seed)
        value = (value ^ value >> _i35_np.uint64(30)) * _MIX_1
        value = (value ^ value >> _i35_np.uint64(27)) * _MIX_2
        value = value ^ value >> _i35_np.uint64(31)
    return (value >> _i35_np.uint64(11)).astype(_i35_np.float64) / float(2 ** 53)

def _value_noise(global_x, global_z, scale_m, seed):
    """Quintic value noise on a lattice defined in absolute metres."""
    coordinate_x = _i35_np.asarray(global_x, _i35_np.float64) / scale_m
    coordinate_z = _i35_np.asarray(global_z, _i35_np.float64) / scale_m
    if _i35_np.any(_i35_np.abs(coordinate_x) > _LATTICE_LIMIT) or _i35_np.any(_i35_np.abs(coordinate_z) > _LATTICE_LIMIT):
        raise ValueError('global lattice coordinate exceeds precision budget')
    lattice_x = _i35_np.floor(coordinate_x).astype(_i35_np.int64)
    lattice_z = _i35_np.floor(coordinate_z).astype(_i35_np.int64)
    fraction_x = coordinate_x - lattice_x
    fraction_z = coordinate_z - lattice_z
    smooth_x = fraction_x ** 3 * (fraction_x * (fraction_x * 6.0 - 15.0) + 10.0)
    smooth_z = fraction_z ** 3 * (fraction_z * (fraction_z * 6.0 - 15.0) + 10.0)
    upper = _lattice_unit(lattice_x, lattice_z, seed) * (1.0 - smooth_x) + _lattice_unit(lattice_x + 1, lattice_z, seed) * smooth_x
    lower = _lattice_unit(lattice_x, lattice_z + 1, seed) * (1.0 - smooth_x) + _lattice_unit(lattice_x + 1, lattice_z + 1, seed) * smooth_x
    return upper * (1.0 - smooth_z) + lower * smooth_z
QUANTILE_TABLE_POINTS = 81
QUANTILE_SAMPLE_GRID = 2048
QUANTILE_SAMPLE_COUNT = 4194304
CLASS_NOISE_QUANTILES = (0.001816476, 0.141964583, 0.17851451, 0.203909328, 0.22388455, 0.24078303, 0.255572455, 0.268607043, 0.280496225, 0.291428375, 0.301646722, 0.311232643, 0.320278411, 0.328848633, 0.337069448, 0.3449674, 0.352567154, 0.359910636, 0.367004639, 0.373947669, 0.380729582, 0.387355019, 0.393884103, 0.400289731, 0.406615087, 0.412868263, 0.418983958, 0.42504855, 0.431033979, 0.436998099, 0.442876696, 0.448722549, 0.454518374, 0.460292481, 0.466004909, 0.47169837, 0.477357123, 0.483019179, 0.488669687, 0.494322348, 0.49998692, 0.505598254, 0.511253209, 0.516917792, 0.522578999, 0.528285189, 0.534008082, 0.539754227, 0.545486583, 0.551287388, 0.557117601, 0.563008463, 0.568961825, 0.574955967, 0.581001481, 0.587114549, 0.593329, 0.599586846, 0.605998573, 0.612526422, 0.619134571, 0.62587769, 0.632799117, 0.639874231, 0.647195776, 0.654745353, 0.662578853, 0.670743544, 0.679295563, 0.68834591, 0.697958909, 0.708156673, 0.719183288, 0.731081076, 0.744152151, 0.758811433, 0.775711233, 0.79584974, 0.821317129, 0.858111144, 0.99771644)
ROCK_NOISE_QUANTILES = (0.001215837, 0.123498628, 0.155627057, 0.177942914, 0.195982787, 0.211378746, 0.225068577, 0.237735259, 0.249573142, 0.260599417, 0.271161844, 0.281147392, 0.290807979, 0.300125874, 0.309129617, 0.317893788, 0.326412607, 0.334779287, 0.343020685, 0.351041967, 0.358890364, 0.366646385, 0.374279852, 0.381741463, 0.389219916, 0.396598745, 0.403818636, 0.410981992, 0.418106683, 0.425089222, 0.432083009, 0.438989271, 0.445909097, 0.452715422, 0.45949731, 0.466251544, 0.473003671, 0.479826058, 0.486493191, 0.493192949, 0.499947893, 0.506711554, 0.513476583, 0.520215085, 0.526962217, 0.533748947, 0.540502269, 0.547300521, 0.554201314, 0.561106062, 0.567963814, 0.574945494, 0.58199807, 0.589064886, 0.596226855, 0.603451489, 0.610761811, 0.618145817, 0.625652351, 0.633306058, 0.640959959, 0.648783788, 0.656856797, 0.664980666, 0.673353681, 0.681924054, 0.690743163, 0.699761637, 0.708994143, 0.718675012, 0.728727297, 0.739212132, 0.750250467, 0.762041444, 0.774637968, 0.788269956, 0.803635076, 0.821686689, 0.844225737, 0.876414702, 0.997628687)

def _quantile(table, probability):
    if not 0.0 <= probability <= 1.0:
        raise ValueError('probability must be in [0, 1]')
    position = float(probability) * (len(table) - 1)
    lower = int(_i35_math.floor(position))
    upper = min(lower + 1, len(table) - 1)
    fraction = position - lower
    return float(table[lower]) * (1.0 - fraction) + float(table[upper]) * fraction

def _thresholds(weights, keys, table):
    """Cumulative quantile thresholds of a declared weight vector."""
    total = 0.0
    for key in keys:
        total += float(weights[key])
    if not _i35_math.isfinite(total) or total <= 0.0:
        raise ValueError('weights must have a positive finite sum')
    cumulative = 0.0
    bounds = []
    for key in keys:
        cumulative += float(weights[key]) / total
        bounds.append(_quantile(table, min(cumulative, 1.0)))
    for index in range(1, len(bounds)):
        if bounds[index] < bounds[index - 1]:
            raise ValueError('weight vector produced decreasing thresholds')
    return tuple(bounds)

def rock_table_identity():
    """SHA256 of the attribute table, so a table edit cannot pass silently."""
    return _i35_hashlib.sha256(_properties_canonical(list(ROCK_TABLE)).encode('utf-8')).hexdigest()

def rock_table():
    """Return a deep copy of the attribute table as plain dictionaries."""
    return _i35_json.loads(_properties_canonical(list(ROCK_TABLE)))

def rock_record(identifier):
    """Return a deep copy of one rock record by id (``name_en``)."""
    if identifier not in ROCK_BY_ID:
        raise KeyError('unknown rock: ' + repr(identifier))
    return _i35_json.loads(_properties_canonical(ROCK_BY_ID[identifier]))

def rock_ids(rock_index_array):
    """Map an int64 rock-index array to rock ids."""
    values = _i35_np.asarray(rock_index_array)
    if values.dtype != _i35_np.int64:
        raise ValueError('rock index array must be int64')
    if values.size and (values.min() < 0 or values.max() >= len(ROCK_ORDER)):
        raise ValueError('rock index out of range')
    flat = [ROCK_ORDER[int(value)] for value in values.ravel()]
    return _i35_np.asarray(flat, dtype=object).reshape(values.shape)

def _lithology_positive(value, name):
    if isinstance(value, (bool, _i35_np.bool_)) or not isinstance(value, (int, float, _i35_np.integer, _i35_np.floating)):
        raise ValueError(name + ' must be numeric')
    result = float(value)
    if not _i35_math.isfinite(result) or result <= 0.0:
        raise ValueError(name + ' must be finite and positive')
    return result

def _weights_block(supplied, expected_keys, name):
    if not isinstance(supplied, dict) or set(supplied) != set(expected_keys):
        raise ValueError(name + ' keys must be exactly ' + ','.join(sorted(expected_keys)))
    result = {}
    total = 0.0
    for key in expected_keys:
        value = _lithology_positive(supplied[key], name + '.' + key)
        result[key] = value
        total += value
    if not _i35_math.isfinite(total) or total <= 0.0:
        raise ValueError(name + ' must sum to a positive finite total')
    return result

def normalize_parameters(parameters=None):
    """Validate and fill the distribution rule; unknown keys are rejected."""
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(LITHOLOGY_DEFAULT_PARAMETERS):
        raise ValueError('unknown lithology parameters')
    merged = {**LITHOLOGY_DEFAULT_PARAMETERS, **supplied}
    config = {}
    for name in ('class_primary_scale_m', 'class_secondary_scale_m', 'rock_scale_m', 'patch_scale_m'):
        config[name] = _lithology_positive(merged[name], name)
    for name in ('class_secondary_weight', 'patch_weight'):
        value = merged[name]
        if isinstance(value, (bool, _i35_np.bool_)) or not isinstance(value, (int, float, _i35_np.integer, _i35_np.floating)):
            raise ValueError(name + ' must be numeric')
        if not 0.0 <= float(value) < 1.0:
            raise ValueError(name + ' must be in [0, 1)')
        config[name] = float(value)
    config['class_weights'] = _weights_block(merged['class_weights'], CLASS_IDS, 'class_weights')
    rock_weights = merged['rock_weights']
    if not isinstance(rock_weights, dict) or set(rock_weights) != set(CLASS_IDS):
        raise ValueError('rock_weights must have exactly the three class keys')
    config['rock_weights'] = {class_id: _weights_block(rock_weights[class_id], ROCK_ORDER_BY_CLASS[class_id], 'rock_weights.' + class_id) for class_id in CLASS_IDS}
    return config

def _lithology_shape(shape):
    if len(shape) != 2:
        raise ValueError('shape must be two positive integers')
    for size in shape:
        if isinstance(size, (bool, _i35_np.bool_)) or not isinstance(size, (int, _i35_np.integer)) or size <= 0:
            raise ValueError('shape must be two positive integers')
    result = (int(shape[0]), int(shape[1]))
    if _i35_math.prod(result) > LITHOLOGY_MAX_CELLS:
        raise ValueError('lithology cell budget exceeded')
    return result

def _spacing(spacing_m):
    return _lithology_positive(spacing_m, 'spacing_m')

def _lithology_origin(origin_m_xz, spacing):
    origin = _i35_np.asarray(origin_m_xz, _i35_np.float64)
    if origin.shape != (2,) or not _i35_np.isfinite(origin).all():
        raise ValueError('origin_m_xz must contain two finite coordinates')
    grid_origin = origin / spacing
    if _i35_np.any(_i35_np.abs(grid_origin) > 2.0 ** 50) or not _i35_np.allclose(grid_origin, _i35_np.rint(grid_origin), rtol=0.0, atol=1e-08):
        raise ValueError('origin must align with the global spacing grid')
    return (origin, _i35_np.rint(grid_origin).astype(_i35_np.int64))

def _lithology_check_world_seed(world_seed):
    if isinstance(world_seed, (bool, _i35_np.bool_)) or not isinstance(world_seed, (int, _i35_np.integer)):
        raise ValueError('world_seed must be an integer')
    if not 0 <= int(world_seed) < 2 ** 64:
        raise ValueError('world_seed must be a uint64')
    return int(world_seed)

class _Rule:
    """Precomputed thresholds and lookup tables for one seed/parameter set."""
    __slots__ = ('config', 'subseeds', 'class_bounds', 'rock_bounds', 'class_rock_index')

    def __init__(self, config, subseeds):
        self.config = config
        self.subseeds = subseeds
        self.class_bounds = _thresholds(config['class_weights'], CLASS_IDS, CLASS_NOISE_QUANTILES)
        self.rock_bounds = {class_id: _thresholds(config['rock_weights'][class_id], ROCK_ORDER_BY_CLASS[class_id], ROCK_NOISE_QUANTILES) for class_id in CLASS_IDS}
        self.class_rock_index = {class_id: _i35_np.asarray([ROCK_POSITION[rock] for rock in ROCK_ORDER_BY_CLASS[class_id]], _i35_np.int64) for class_id in CLASS_IDS}

    def sample(self, global_x, global_z):
        config = self.config
        primary = _value_noise(global_x, global_z, config['class_primary_scale_m'], self.subseeds['class_primary'])
        secondary = _value_noise(global_x, global_z, config['class_secondary_scale_m'], self.subseeds['class_secondary'])
        weight = config['class_secondary_weight']
        class_score = (1.0 - weight) * primary + weight * secondary
        class_index = _band(class_score, self.class_bounds)
        medium = _value_noise(global_x, global_z, config['rock_scale_m'], self.subseeds['rock_medium'])
        patch = _value_noise(global_x, global_z, config['patch_scale_m'], self.subseeds['patch_high'])
        patch_weight = config['patch_weight']
        rock_score = (1.0 - patch_weight) * medium + patch_weight * patch
        rock_index = _i35_np.zeros(class_score.shape, _i35_np.int64)
        for position, class_id in enumerate(CLASS_IDS):
            selected = class_index == position
            if not selected.any():
                continue
            local = _band(rock_score[selected], self.rock_bounds[class_id])
            rock_index[selected] = self.class_rock_index[class_id][local]
        return (class_index, rock_index)

def _band(values, bounds):
    bounds = _i35_np.asarray(bounds, _i35_np.float64)
    position = _i35_np.searchsorted(bounds, values, side='left')
    return _i35_np.clip(position, 0, bounds.size - 1).astype(_i35_np.int64)

def _validate_rule_outputs(class_index, rock_index, shape):
    if class_index.shape != shape or rock_index.shape != shape:
        raise ValueError('lithology field shape mismatch')
    if class_index.dtype != _i35_np.int64 or rock_index.dtype != _i35_np.int64:
        raise ValueError('lithology indices must be int64')
    if _i35_np.any((class_index < 0) | (class_index >= len(CLASS_IDS))):
        raise ValueError('class index out of range')
    if _i35_np.any((rock_index < 0) | (rock_index >= len(ROCK_ORDER))):
        raise ValueError('rock index out of range')
    if _i35_np.any(_CLASS_POSITION_TABLE[rock_index] != class_index):
        raise ValueError('rock does not belong to its declared class')

def _fields(class_index, rock_index):
    """Read-only-by-convention float/int fields derived from the rock table.

    ``np.array(..., order="C", copy=True)`` is used instead of
    ``np.ascontiguousarray`` because the latter silently promotes a 0-d array to
    shape ``(1,)``, which would make a single-point query disagree with a grid
    query on shape.
    """
    class_index = _i35_np.array(class_index, dtype=_i35_np.int64, order='C', copy=True)
    rock_index = _i35_np.array(rock_index, dtype=_i35_np.int64, order='C', copy=True)
    return {'class_index': class_index, 'rock_index': rock_index, 'bed_hardness': _i35_np.array(_BED_HARDNESS_TABLE[rock_index], _i35_np.float64, order='C', copy=True), 'bank_hardness': _i35_np.array(_BANK_HARDNESS_TABLE[rock_index], _i35_np.float64, order='C', copy=True), 'erodibility_index': _i35_np.array(_ERODIBILITY_TABLE[rock_index], _i35_np.float64, order='C', copy=True)}

def sample_lithology_points(x_m, z_m, *, world_seed=DEFAULT_WORLD_SEED, parameters=None):
    """Sample the lithology rule at absolute world coordinates (metres).

    ``x_m`` and ``z_m`` are broadcastable; the result is a dict of same-shape
    arrays. Only absolute coordinates enter, so point sets may be shuffled, split
    across windows or queried one at a time and still agree bit for bit. Scalars
    give scalar-shaped (0-d) arrays, so a single point query is allowed.
    """
    seed = _lithology_check_world_seed(world_seed)
    config = normalize_parameters(parameters)
    x = _i35_np.asarray(x_m, _i35_np.float64)
    z = _i35_np.asarray(z_m, _i35_np.float64)
    if not _i35_np.isfinite(x).all() or not _i35_np.isfinite(z).all():
        raise ValueError('coordinates must be finite')
    shape = _i35_np.broadcast_shapes(x.shape, z.shape)
    x, z = _i35_np.broadcast_arrays(x, z)
    rule = _Rule(config, {purpose: derive_subseed(seed, purpose) for purpose in SEED_PURPOSES})
    class_index, rock_index = rule.sample(x, z)
    return _fields(class_index.reshape(shape), rock_index.reshape(shape))

def sample_lithology(shape, *, origin_m_xz, spacing_m, world_seed=DEFAULT_WORLD_SEED, parameters=None, protected_mask=None):
    """Sample the rule on cell centres of a global metric grid.

    Cell centres are ``origin + (index + 0.5) * spacing``; the same absolute
    coordinates are sampled whether the window is large, small or offset, so
    tiles joined later are seamless.
    """
    from terrain_pipeline.common_infra import identity as _i35_identity
    shape = _lithology_shape(shape)
    spacing = _spacing(spacing_m)
    origin, grid_origin = _lithology_origin(origin_m_xz, spacing)
    seed = _lithology_check_world_seed(world_seed)
    config = normalize_parameters(parameters)
    if protected_mask is None:
        protected = _i35_np.zeros(shape, bool)
    else:
        protected = _i35_np.asarray(protected_mask)
        if protected.shape != shape or protected.dtype != _i35_np.dtype(bool):
            raise ValueError('protected_mask must be same-shape boolean array')
        protected = _i35_np.array(protected, dtype=bool, copy=True)
    global_x = (grid_origin[0] + _i35_np.arange(shape[1], dtype=_i35_np.int64) + 0.5) * spacing
    global_z = (grid_origin[1] + _i35_np.arange(shape[0], dtype=_i35_np.int64) + 0.5) * spacing
    if not _i35_np.isfinite(global_x).all() or not _i35_np.isfinite(global_z).all():
        raise ValueError('global coordinate overflow')
    rule = _Rule(config, {purpose: derive_subseed(seed, purpose) for purpose in SEED_PURPOSES})
    class_index, rock_index = rule.sample(global_x[None, :], global_z[:, None])
    class_index = _i35_np.broadcast_to(class_index, shape).copy()
    rock_index = _i35_np.broadcast_to(rock_index, shape).copy()
    _validate_rule_outputs(class_index, rock_index, shape)
    arrays = _fields(class_index, rock_index)
    arrays['protected_mask'] = protected
    metadata = _metadata(shape, origin, spacing, seed, config)
    bundle = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i35_identity(arrays, metadata)}
    return bundle

def _metadata(shape, origin, spacing, seed, config):
    return {'schema': LITHOLOGY_SCHEMA, 'algorithm': LITHOLOGY_ALGORITHM, 'format_version': 1, 'shape': list(shape), 'origin_m_xz': [float(origin[0]), float(origin[1])], 'spacing_m': spacing, 'world_seed': int(seed), 'subseeds': {purpose: derive_subseed(seed, purpose) for purpose in SEED_PURPOSES}, 'seed_derivation': SEED_DERIVATION, 'parameters': {'class_primary_scale_m': config['class_primary_scale_m'], 'class_secondary_scale_m': config['class_secondary_scale_m'], 'class_secondary_weight': config['class_secondary_weight'], 'rock_scale_m': config['rock_scale_m'], 'patch_scale_m': config['patch_scale_m'], 'patch_weight': config['patch_weight'], 'class_weights': config['class_weights'], 'rock_weights': config['rock_weights']}, 'coordinate_convention': 'X east; Z south; [z,x]; cell centres; absolute world metres', 'coordinate_absolute': True, 'class_order': list(CLASS_IDS), 'rock_order': list(ROCK_ORDER), 'rock_table_sha256': rock_table_identity(), 'synthetic_lithology': True, 'measured_lithology': False, 'value_status': PROVENANCE, 'distribution_model': 'simplified_two_level_value_noise', 'tectonic_context': False, 'erodibility_rule': {'weights': dict(ERODIBILITY_WEIGHTS), 'mohs_range': [MOHS_FLOOR, MOHS_CEILING], 'porosity_reference_max': POROSITY_CEILING, 'bank_layering_penalty': BANK_LAYERING_PENALTY, 'bank_solubility_penalty': BANK_SOLUBILITY_PENALTY, 'hardness_bounds': [HARDNESS_FLOOR, HARDNESS_CEILING]}, 'units': {'bed_hardness': '1', 'bank_hardness': '1', 'erodibility_index': '1', 'class_index': 'index into class_order', 'rock_index': 'index into rock_order'}, 'limitations': ['distribution is a simplified noise rule, not a plate/tectonic/sedimentary-basin reconstruction', 'attribute values are engineering reference values and are not calibrated', 'no strata column, dip, age or fault offset is modelled here', 'depth below the surface is not sampled; one rock is assigned per map column', 'phase 2 replaces the distribution rule and keeps the attribute table']}

def discharge_geometry_inputs(bundle):
    """Return ``(bed_hardness, bank_hardness)`` copies ready for the existing rule."""
    validate_lithology_field(bundle)
    arrays = bundle['arrays']
    return (arrays['bed_hardness'].copy(), arrays['bank_hardness'].copy())

def hardness_lookup(rock_id):
    """Return ``(bed_hardness, bank_hardness)`` for one rock id."""
    record = ROCK_BY_ID.get(rock_id)
    if record is None:
        raise ValueError('unknown rock: ' + repr(rock_id))
    return (record['bed_hardness'], record['bank_hardness'])

def validate_lithology_field(bundle):
    """Reject a bundle that does not recompute from its own declared inputs."""
    from terrain_pipeline.common_infra import identity as _i35_identity
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid lithology bundle structure')
    arrays, metadata = (bundle['arrays'], bundle['metadata'])
    if _i35_identity(arrays, metadata) != bundle['identity_sha256']:
        raise ValueError('lithology bundle identity mismatch')
    if metadata.get('schema') != LITHOLOGY_SCHEMA or metadata.get('algorithm') != LITHOLOGY_ALGORITHM or metadata.get('format_version') != 1:
        raise ValueError('unsupported lithology identity')
    if metadata.get('synthetic_lithology') is not True or metadata.get('measured_lithology') is not False:
        raise ValueError('lithology bundle must declare synthetic, unmeasured status')
    if metadata.get('value_status') != PROVENANCE:
        raise ValueError('lithology bundle must declare uncalibrated reference values')
    if metadata.get('tectonic_context') is not False:
        raise ValueError('phase-1 distribution has no tectonic context and must say so')
    if metadata.get('rock_table_sha256') != rock_table_identity():
        raise ValueError('rock attribute table differs from the one recorded by the bundle')
    if metadata.get('rock_order') != list(ROCK_ORDER) or metadata.get('class_order') != list(CLASS_IDS):
        raise ValueError('lithology ordering mismatch')
    shape = _lithology_shape(metadata['shape'])
    if set(arrays) != {'class_index', 'rock_index', 'bed_hardness', 'bank_hardness', 'erodibility_index', 'protected_mask'}:
        raise ValueError('lithology array names mismatch')
    class_index = arrays['class_index']
    rock_index = arrays['rock_index']
    if class_index.dtype != _i35_np.int64 or rock_index.dtype != _i35_np.int64:
        raise ValueError('lithology indices must be int64')
    _validate_rule_outputs(_i35_np.ascontiguousarray(class_index), _i35_np.ascontiguousarray(rock_index), shape)
    for name, table in (('bed_hardness', _BED_HARDNESS_TABLE), ('bank_hardness', _BANK_HARDNESS_TABLE), ('erodibility_index', _ERODIBILITY_TABLE)):
        expected = table[rock_index]
        values = arrays[name]
        if values.shape != shape or values.dtype != _i35_np.float64 or (not _i35_np.array_equal(values, expected)):
            raise ValueError('lithology field ' + name + ' is inconsistent with the rock table')
    if _i35_np.any(_BANK_HARDNESS_TABLE[rock_index] > _BED_HARDNESS_TABLE[rock_index]):
        raise ValueError('bank hardness must not exceed bed hardness')
    reference = sample_lithology(shape, origin_m_xz=metadata['origin_m_xz'], spacing_m=metadata['spacing_m'], world_seed=metadata['world_seed'], parameters=metadata['parameters'], protected_mask=arrays['protected_mask'])
    if reference['identity_sha256'] != bundle['identity_sha256']:
        raise ValueError('lithology provenance mismatch: field does not recompute')
    return True

def compose_report(bundle):
    """Return class and rock proportions actually present in a sampled field."""
    validate_lithology_field(bundle)
    arrays = bundle['arrays']
    class_index = arrays['class_index']
    rock_index = arrays['rock_index']
    total = int(class_index.size)
    classes = {}
    for position, class_id in enumerate(CLASS_IDS):
        count = int((class_index == position).sum())
        classes[class_id] = {'name_zh': CLASS_NAMES_ZH[class_id], 'count': count, 'fraction': count / total}
    rocks = {}
    for identifier in ROCK_ORDER:
        count = int((rock_index == ROCK_POSITION[identifier]).sum())
        rocks[identifier] = {'name_zh': ROCK_BY_ID[identifier]['name_zh'], 'class': ROCK_BY_ID[identifier]['class'], 'count': count, 'fraction': count / total}
    return {'total_cells': total, 'classes': classes, 'rocks': rocks, 'distinct_rocks': sum((1 for value in rocks.values() if value['count'] > 0)), 'distinct_classes': sum((1 for value in classes.values() if value['count'] > 0))}

def save_lithology_field(bundle, path):
    from terrain_pipeline.common_infra import save_bundle as _i35_save_bundle
    return _i35_save_bundle(path, bundle, validator=validate_lithology_field)

def load_lithology_field(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _i35_load_bundle
    return _i35_load_bundle(path, expected_sha256=expected_sha256, validator=validate_lithology_field, max_bytes=256 * 1024 * 1024)
MATERIAL_ALGORITHM = 'td-continuous-global-value-noise-v1'
MAX_BYTES = 1024 ** 3
MATERIAL_DEFAULT_PARAMETERS = {'erodibility_range': [0.25, 1.0], 'erodible_thickness_range_m': [0.25, 4.0], 'weak_path_preference_range': [0.8, 1.2], 'correlation_length_m': 900.0, 'solid_density_kg_m3': 2650.0, 'source_porosity': 0.1, 'deposit_porosity': 0.35}

def _json(value):
    return _i37_json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def _material_identity(arrays, metadata):
    digest = _i37_hashlib.sha256(_json(metadata).encode('utf-8'))
    for name, values in sorted(arrays.items()):
        digest.update(name.encode('utf-8'))
        digest.update(values.dtype.str.encode('ascii'))
        digest.update(_json(list(values.shape)).encode('ascii'))
        digest.update(_i37_np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()

def _material_bundle(arrays, metadata):
    frozen = {}
    for name, values in arrays.items():
        contiguous = _i37_np.ascontiguousarray(values)
        frozen[name] = _i37_np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)
    metadata = _i37_json.loads(_json(metadata))
    return {'arrays': frozen, 'metadata': metadata, 'identity_sha256': _material_identity(frozen, metadata)}

def _material_check_identity(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid bundle structure')
    if _material_identity(bundle['arrays'], bundle['metadata']) != bundle['identity_sha256']:
        raise ValueError('bundle identity mismatch')

def _material_positive(value, name, allow_zero=False):
    if isinstance(value, (bool, _i37_np.bool_)):
        raise ValueError(name + ' must be numeric')
    result = float(value)
    if not _i37_math.isfinite(result) or result < 0 or (result == 0 and (not allow_zero)):
        raise ValueError(name + ' outside finite valid range')
    return result

def _parameters(parameters):
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(MATERIAL_DEFAULT_PARAMETERS):
        raise ValueError('unknown material parameters')
    result = {**MATERIAL_DEFAULT_PARAMETERS, **supplied}
    for name in ('erodibility_range', 'erodible_thickness_range_m', 'weak_path_preference_range'):
        values = result[name]
        if len(values) != 2:
            raise ValueError(name + ' needs two bounds')
        low = _material_positive(values[0], name, allow_zero=True)
        high = _material_positive(values[1], name, allow_zero=True)
        if low > high or (name == 'erodibility_range' and high > 1):
            raise ValueError(name + ' invalid bounds')
        result[name] = [low, high]
    for name in ('correlation_length_m', 'solid_density_kg_m3'):
        result[name] = _material_positive(result[name], name)
    for name in ('source_porosity', 'deposit_porosity'):
        result[name] = _material_positive(result[name], name, allow_zero=True)
        if result[name] >= 1:
            raise ValueError(name + ' must be < 1')
    return result

def _material_shape(shape):
    if len(shape) != 2 or any((isinstance(size, (bool, _i37_np.bool_)) or not isinstance(size, (int, _i37_np.integer)) or size <= 0 for size in shape)):
        raise ValueError('shape must be two positive integers')
    result = tuple(map(int, shape))
    if _i37_math.prod(result) > LITHOLOGY_MAX_CELLS:
        raise ValueError('material cell budget exceeded')
    return result

def _mask(values, shape, name):
    if values is None:
        return _i37_np.zeros(shape, bool)
    result = _i37_np.asarray(values)
    if result.shape != shape or result.dtype != _i37_np.dtype(bool):
        raise ValueError(name + ' must be same-shape boolean array')
    return result

def _lattice_value(lattice_x, lattice_z, seed, channel):
    with _i37_np.errstate(over='ignore'):
        value = lattice_x.astype(_i37_np.uint64) * _i37_np.uint64(11400714785074694791)
        value = value ^ lattice_z.astype(_i37_np.uint64) * _i37_np.uint64(14029467366897019727)
        value = value ^ _i37_np.uint64(seed) ^ _i37_np.uint64(channel * 1609587929392839161)
        value = (value ^ value >> _i37_np.uint64(30)) * _i37_np.uint64(13787848793156543929)
        value = (value ^ value >> _i37_np.uint64(27)) * _i37_np.uint64(10723151780598845931)
        value = value ^ value >> _i37_np.uint64(31)
    return (value >> _i37_np.uint64(11)).astype(_i37_np.float64) / float(2 ** 53)

def _noise(global_x, global_z, scale, seed, channel):
    coordinate_x = global_x / scale
    coordinate_z = global_z / scale
    if _i37_np.any(_i37_np.abs(coordinate_x) > 2 ** 50) or _i37_np.any(_i37_np.abs(coordinate_z) > 2 ** 50):
        raise ValueError('global lattice coordinate exceeds precision budget')
    lattice_x = _i37_np.floor(coordinate_x).astype(_i37_np.int64)
    lattice_z = _i37_np.floor(coordinate_z).astype(_i37_np.int64)
    fraction_x = coordinate_x - lattice_x
    fraction_z = coordinate_z - lattice_z
    smooth_x = fraction_x ** 3 * (fraction_x * (fraction_x * 6 - 15) + 10)
    smooth_z = fraction_z ** 3 * (fraction_z * (fraction_z * 6 - 15) + 10)
    upper = _lattice_value(lattice_x, lattice_z, seed, channel) * (1 - smooth_x)
    upper += _lattice_value(lattice_x + 1, lattice_z, seed, channel) * smooth_x
    lower = _lattice_value(lattice_x, lattice_z + 1, seed, channel) * (1 - smooth_x)
    lower += _lattice_value(lattice_x + 1, lattice_z + 1, seed, channel) * smooth_x
    return upper * (1 - smooth_z) + lower * smooth_z

def make_material_field(shape, *, origin_m_xz, spacing_m, seed=20261002, parameters=None, protected_mask=None):
    """Sample centres on the global grid; integer window offsets are exact."""
    shape = _material_shape(shape)
    spacing = _material_positive(spacing_m, 'spacing_m')
    if not isinstance(seed, (int, _i37_np.integer)) or isinstance(seed, (bool, _i37_np.bool_)) or (not 0 <= seed < 2 ** 64):
        raise ValueError('seed must be uint64')
    origin = _i37_np.asarray(origin_m_xz, dtype=_i37_np.float64)
    if origin.shape != (2,) or not _i37_np.isfinite(origin).all():
        raise ValueError('origin_m_xz must contain two finite coordinates')
    grid_origin = origin / spacing
    if _i37_np.any(_i37_np.abs(grid_origin) > 2 ** 50) or not _i37_np.allclose(grid_origin, _i37_np.rint(grid_origin), rtol=0, atol=1e-08):
        raise ValueError('origin must align with global spacing grid')
    grid_origin = _i37_np.rint(grid_origin).astype(_i37_np.int64)
    config = _parameters(parameters)
    global_x = (grid_origin[0] + _i37_np.arange(shape[1], dtype=_i37_np.int64) + 0.5) * spacing
    global_z = (grid_origin[1] + _i37_np.arange(shape[0], dtype=_i37_np.int64) + 0.5) * spacing
    if not _i37_np.isfinite(global_x).all() or not _i37_np.isfinite(global_z).all():
        raise ValueError('global coordinate overflow')
    arrays = {'protected_mask': _mask(protected_mask, shape, 'protected_mask')}
    for channel, (name, range_name) in enumerate((('erodibility', 'erodibility_range'), ('erodible_thickness_m', 'erodible_thickness_range_m'), ('weak_path_preference', 'weak_path_preference_range')), start=1):
        low, high = config[range_name]
        noise = _noise(global_x[None, :], global_z[:, None], config['correlation_length_m'], int(seed), channel)
        arrays[name] = _i37_np.clip(low + (high - low) * noise, low, high)
    metadata = {'algorithm': MATERIAL_ALGORITHM, 'format_version': 1, 'shape': list(shape), 'origin_m_xz': origin.tolist(), 'spacing_m': spacing, 'seed': int(seed), 'parameters': config, 'coordinate_convention': 'X east; Z south; [z,x]; cell centres', 'synthetic_material': True, 'measured_lithology': False, 'units': {'erodibility': '1', 'erodible_thickness_m': 'm', 'weak_path_preference': '1'}}
    return _material_bundle(arrays, metadata)

def validate_material_field(bundle):
    _material_check_identity(bundle)
    metadata = bundle['metadata']
    if metadata.get('algorithm') != MATERIAL_ALGORITHM or metadata.get('format_version') != 1:
        raise ValueError('unsupported material identity')
    shape = _material_shape(metadata['shape'])
    config = _parameters(metadata['parameters'])
    arrays = bundle['arrays']
    if set(arrays) != {'erodibility', 'erodible_thickness_m', 'weak_path_preference', 'protected_mask'}:
        raise ValueError('material array names mismatch')
    _mask(arrays['protected_mask'], shape, 'protected_mask')
    for name, range_name in (('erodibility', 'erodibility_range'), ('erodible_thickness_m', 'erodible_thickness_range_m'), ('weak_path_preference', 'weak_path_preference_range')):
        values = arrays[name]
        low, high = config[range_name]
        if values.shape != shape or values.dtype != _i37_np.dtype('float64') or (not _i37_np.isfinite(values).all()) or _i37_np.any(values < low) or _i37_np.any(values > high):
            raise ValueError('invalid material array ' + name)
    reference = make_material_field(shape, origin_m_xz=metadata['origin_m_xz'], spacing_m=metadata['spacing_m'], seed=metadata['seed'], parameters=config, protected_mask=arrays['protected_mask'])
    if reference['identity_sha256'] != bundle['identity_sha256']:
        raise ValueError('material provenance mismatch')
    return True

def _save_bundle(bundle, path):
    _material_check_identity(bundle)
    path = _i37_Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = _i37_tempfile.mkstemp(prefix='.td-stage-', suffix='.npz', dir=path.parent)
    try:
        with _i37_os.fdopen(descriptor, 'wb') as stream:
            _i37_np.savez_compressed(stream, **bundle['arrays'], metadata_json=_i37_np.asarray(_json(bundle['metadata'])), identity_sha256=_i37_np.asarray(bundle['identity_sha256']))
            stream.flush()
            _i37_os.fsync(stream.fileno())
        _i37_os.link(temporary, path)
    finally:
        _i37_os.unlink(temporary)
    return path

def _archive_headers(headers):
    if not {'metadata_json', 'identity_sha256'} <= set(headers) or len(headers) > 32:
        raise ValueError('invalid bundle headers')
    for name, (shape, dtype) in headers.items():
        if name in ('metadata_json', 'identity_sha256'):
            if shape != () or dtype.kind != 'U' or dtype.itemsize > 4 * 1024 * 1024:
                raise ValueError('invalid metadata header')
        elif len(shape) not in (1, 2) or _i37_math.prod(shape) > LITHOLOGY_MAX_CELLS or dtype not in (_i37_np.dtype('float64'), _i37_np.dtype('int64'), _i37_np.dtype(bool)):
            raise ValueError('invalid array header')

def _load_bundle(path, *, expected_sha256=None, expected_identity=None):
    from terrain_pipeline.common_infra import checked_archive as _i37_checked_archive
    from terrain_pipeline.common_infra import file_sha256 as _i37_file_sha256
    if expected_sha256 is None and expected_identity is None:
        raise ValueError('external expected_sha256 or expected_identity required')
    for expected in (expected_sha256, expected_identity):
        if expected is not None and (not isinstance(expected, str) or len(expected) != 64 or any((char not in '0123456789abcdef' for char in expected))):
            raise ValueError('external identity must be lowercase SHA256')
    archive = _i37_checked_archive(path, expected_sha256=expected_sha256 or _i37_file_sha256(path), max_bytes=MAX_BYTES // 4, header_validator=_archive_headers)
    metadata = _i37_json.loads(str(archive.pop('metadata_json').item()))
    identity = str(archive.pop('identity_sha256').item())
    arrays = archive
    bundle = _material_bundle(arrays, metadata)
    if bundle['identity_sha256'] != identity:
        raise ValueError('stored identity mismatch')
    if expected_identity is not None and identity != expected_identity:
        raise ValueError('external bundle identity mismatch')
    return bundle

def save_material_field(bundle, path):
    validate_material_field(bundle)
    return _save_bundle(bundle, path)

def load_material_field(path, *, expected_sha256=None, expected_identity=None):
    """Read a saved field without sampling or advancing the generator."""
    bundle = _load_bundle(path, expected_sha256=expected_sha256, expected_identity=expected_identity)
    _validate_cold_material(bundle)
    return bundle

def _validate_cold_material(bundle):
    _material_check_identity(bundle)
    metadata = bundle['metadata']
    if metadata.get('algorithm') != MATERIAL_ALGORITHM or metadata.get('format_version') != 1:
        raise ValueError('unsupported material format')
    shape = _material_shape(metadata['shape'])
    config = _parameters(metadata['parameters'])
    spacing = _material_positive(metadata['spacing_m'], 'spacing_m')
    origin = _i37_np.asarray(metadata['origin_m_xz'], _i37_np.float64)
    seed = metadata['seed']
    if origin.shape != (2,) or not _i37_np.isfinite(origin).all() or (not _i37_np.allclose(origin / spacing, _i37_np.rint(origin / spacing), atol=1e-08, rtol=0)):
        raise ValueError('invalid cold material coordinates')
    if not isinstance(seed, int) or isinstance(seed, bool) or (not 0 <= seed < 2 ** 64):
        raise ValueError('invalid cold material seed')
    if set(bundle['arrays']) != {'erodibility', 'erodible_thickness_m', 'weak_path_preference', 'protected_mask'}:
        raise ValueError('material fields mismatch')
    _mask(bundle['arrays']['protected_mask'], shape, 'protected_mask')
    for name, range_name in (('erodibility', 'erodibility_range'), ('erodible_thickness_m', 'erodible_thickness_range_m'), ('weak_path_preference', 'weak_path_preference_range')):
        values = bundle['arrays'][name]
        low, high = config[range_name]
        if values.shape != shape or values.dtype != _i37_np.dtype('float64') or (not _i37_np.isfinite(values).all()) or _i37_np.any(values < low) or _i37_np.any(values > high):
            raise ValueError('invalid cold material field')
PROPERTIES_SCHEMA = 'geology-properties-v1'
PROPERTIES_ALGORITHM = 'geology-properties-composition-v1'
FORMAT_VERSION = 1
GRID_SPACING_M = 30.0
HALF_CELL_M = 15.0
MAX_POINTS = 8192
MAX_GRID_CELLS = 262144
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
_ESTIMATED_COLUMNS = 14
_METADATA_RESERVE_BYTES = 64 * 1024
INT_FIELDS = ('rock_index', 'class_index')
FLOAT_FIELDS = ('x_m', 'z_m', 'bed_hardness', 'bank_hardness', 'erodibility_index', 'mohs_hardness', 'solubility', 'porosity', 'cover_thickness_m')
OPTIONAL_FLOAT_FIELDS = ('bedrock_thickness_m', 'uniaxial_strength_mpa', 'intrinsic_permeability_m2')
SIGNED_FIELDS = ('x_m', 'z_m')
COMPUTED = 'computed'
DECLARED = 'declared'
PENDING = 'pending'
PARTIALLY_DECLARED = 'partially_declared'
UNKNOWN_NO_SOURCE = 'unknown_no_source'
NOT_SAMPLED_NO_GRID_WINDOW = 'not_sampled_no_grid_window'
DECLARED_GEOMETRY_NOT_LITHOLOGY_OFFSET = 'declared_geometry_not_lithology_offset'
UNVERIFIED = 'unverified'
UNITS = {'x_m': 'm', 'z_m': 'm', 'rock_index': 'index into td_lithology_field.ROCK_ORDER', 'class_index': 'index into td_lithology_field.CLASS_IDS', 'bed_hardness': '1 (0 weak .. 1 strong), discharge-geometry input', 'bank_hardness': '1 (0 weak .. 1 strong), discharge-geometry input', 'erodibility_index': '1 (0 resistant .. 1 highly erodible)', 'mohs_hardness': 'dimensionless Mohs scale', 'solubility': '1', 'porosity': 'volume fraction', 'cover_thickness_m': 'm', 'bedrock_thickness_m': 'm', 'uniaxial_strength_mpa': 'MPa', 'intrinsic_permeability_m2': 'm2', 'joint_strike_deg': 'deg (0 <= strike < 360)', 'joint_dip_deg': 'deg (0 <= dip <= 90)', 'joint_spacing_m': 'm'}
EXTENDED_FIELDS = {'uniaxial_strength_mpa': 'MPa', 'intrinsic_permeability_m2': 'm2'}
PROPERTIES_LIMITATIONS = ('cover_thickness_m is the erodible material thickness: not soil depth, not regolith stock, and not soil water storage', 'bedrock_thickness_m is unknown_no_source unless the caller declares a finite value; it is never zero-filled and never treated as half-infinite', 'no strata column, dip, age or fault offset is modelled; the layer column has a cover and a bedrock entry only', "fault declarations are geometry only and always report strata_offset_status='unverified'", 'extended strength and permeability values are declared engineering reference end members unless the caller supplies them; they are not calibrated and not measured for any field site', 'bed_hardness / bank_hardness are generation-rule inputs, not rock strength and not an erosion rate', 'permeability is not derived from porosity and strength is not a tensile strength nor an erodibility', 'no consumer reads permeability or solubility yet (G11 karst/groundwater is not implemented)', 'not wired into any default world; consumption is explicit at the call site')

def _properties_canonical(value):
    return _i34_json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def _array_digest(values):
    array = _i34_np.ascontiguousarray(values)
    digest = _i34_hashlib.sha256()
    digest.update(array.dtype.str.encode('ascii'))
    digest.update(_properties_canonical(list(array.shape)).encode('ascii'))
    digest.update(array.tobytes())
    return digest.hexdigest()

def _properties_identity(arrays, metadata, layer_definitions):
    record = {'schema': PROPERTIES_SCHEMA, 'algorithm': PROPERTIES_ALGORITHM, 'format_version': FORMAT_VERSION, 'metadata': metadata, 'layer_definitions': layer_definitions, 'arrays': {name: _array_digest(arrays[name]) for name in sorted(arrays)}}
    return _i34_hashlib.sha256(_properties_canonical(record).encode('utf-8')).hexdigest()

def _points_digest(x, z):
    """Order-independent digest of a point set (lexsorted absolute coordinates).

    The stored arrays keep the caller's order, so the bundle identity binds that
    order; this digest is the extra, order-independent handle a joint observation
    can compare across shuffled or windowed queries.
    """
    flat_x = _i34_np.asarray(x, _i34_np.float64).reshape(-1)
    flat_z = _i34_np.asarray(z, _i34_np.float64).reshape(-1)
    order = _i34_np.lexsort((flat_z, flat_x))
    canonical = _i34_np.stack((flat_x[order], flat_z[order]), axis=1)
    return _i34_hashlib.sha256(_i34_np.ascontiguousarray(canonical).tobytes()).hexdigest()

def _finite_nonnegative(value, name):
    if isinstance(value, (bool, _i34_np.bool_)) or not isinstance(value, (int, float, _i34_np.integer, _i34_np.floating)):
        raise ValueError(name + ' must be numeric')
    result = float(value)
    if not _i34_math.isfinite(result) or result < 0.0:
        raise ValueError(name + ' must be finite and non-negative')
    return result

def _properties_check_world_seed(seed):
    """Mirror of the lithology core's seed policy (no extra random source)."""
    if isinstance(seed, (bool, _i34_np.bool_)) or not isinstance(seed, (int, _i34_np.integer)):
        raise ValueError('world_seed must be an integer')
    value = int(seed)
    if not 0 <= value < 2 ** 64:
        raise ValueError('world_seed must be a uint64')
    return value

def _check_spacing(spacing_m):
    if isinstance(spacing_m, (bool, _i34_np.bool_)) or not isinstance(spacing_m, (int, float, _i34_np.integer, _i34_np.floating)):
        raise ValueError('spacing_m must be numeric')
    value = float(spacing_m)
    if not _i34_math.isfinite(value):
        raise ValueError('spacing_m must be finite')
    if value != GRID_SPACING_M:
        raise ValueError('this module is 30 m only: spacing_m must be %.1f, got %r; there is no arbitrary-resolution mode and no snapping' % (GRID_SPACING_M, value))
    return GRID_SPACING_M

def _properties_shape(shape):
    if len(shape) != 2:
        raise ValueError('shape must be two positive integers')
    result = []
    for size in shape:
        if isinstance(size, (bool, _i34_np.bool_)) or not isinstance(size, (int, _i34_np.integer)):
            raise ValueError('shape must be two positive integers')
        if int(size) <= 0:
            raise ValueError('shape must be two positive integers')
        result.append(int(size))
    return tuple(result)

def _properties_origin(origin_m_xz):
    origin = _i34_np.asarray(origin_m_xz, _i34_np.float64)
    if origin.shape != (2,) or not _i34_np.isfinite(origin).all():
        raise ValueError('origin_m_xz must contain two finite coordinates')
    return origin

def properties_preflight(n_cells, *, point_mode=False):
    """Reject an oversized request before any array or layer container exists."""
    if isinstance(n_cells, (bool, _i34_np.bool_)) or not isinstance(n_cells, (int, _i34_np.integer)):
        raise ValueError('cell/point count must be an integer')
    cells = int(n_cells)
    if cells <= 0:
        raise ValueError('cell/point count must be positive')
    limit = MAX_POINTS if point_mode else MAX_GRID_CELLS
    if cells > limit:
        raise ValueError('%s count %d exceeds %d' % ('point' if point_mode else 'cell', cells, limit))
    estimated = cells * 8 * _ESTIMATED_COLUMNS + _METADATA_RESERVE_BYTES
    if estimated > MAX_OUTPUT_BYTES:
        raise ValueError('estimated logical payload %d bytes exceeds %d' % (estimated, MAX_OUTPUT_BYTES))
    return {'n_cells': cells, 'point_mode': bool(point_mode), 'estimated_columns': _ESTIMATED_COLUMNS, 'estimated_logical_payload_bytes': estimated, 'max_points': MAX_POINTS, 'max_grid_cells': MAX_GRID_CELLS, 'max_output_bytes': MAX_OUTPUT_BYTES}

def cell_centres(shape, *, origin_m_xz, spacing_m):
    """Absolute cell centres ``origin + (index + 0.5) * spacing``.

    This is the only coordinate the material field ever samples, so it is the
    coordinate every thickness field in this module lives on.
    """
    shape = _properties_shape(shape)
    spacing = _check_spacing(spacing_m)
    origin = _properties_origin(origin_m_xz)
    grid_origin = origin / spacing
    if _i34_np.any(_i34_np.abs(grid_origin) > 2.0 ** 50) or not _i34_np.allclose(grid_origin, _i34_np.rint(grid_origin), rtol=0.0, atol=1e-08):
        raise ValueError('origin_m_xz must align with the 30 m grid, exactly like td_material_field requires; this module never snaps the origin')
    x_m = origin[0] + (_i34_np.arange(shape[1], dtype=_i34_np.int64) + 0.5) * spacing
    z_m = origin[1] + (_i34_np.arange(shape[0], dtype=_i34_np.int64) + 0.5) * spacing
    return (_i34_np.broadcast_to(x_m[None, :], shape).copy(), _i34_np.broadcast_to(z_m[:, None], shape).copy())

def reference_points_to_cells(x_ref_m, z_ref_m, *, origin_m_xz, spacing_m, accept_offset_m=None):
    """Map external reference points onto material cells, reporting the offset.

    A 30 m integer reference node sits half a cell (15 m per axis) away from the
    cell centre whose values this module reports. Nothing is snapped: with
    ``accept_offset_m=None`` any non-zero offset raises, and a caller that really
    wants the containing cell must pass the offset it accepts. ``offset_m`` is the
    measured Euclidean distance from the requested point to that centre.
    """
    spacing = _check_spacing(spacing_m)
    origin = _properties_origin(origin_m_xz)
    x = _i34_np.asarray(x_ref_m, _i34_np.float64)
    z = _i34_np.asarray(z_ref_m, _i34_np.float64)
    x, z = _i34_np.broadcast_arrays(x, z)
    if not _i34_np.isfinite(x).all() or not _i34_np.isfinite(z).all():
        raise ValueError('reference coordinates must be finite')
    column = _i34_np.floor((x - origin[0]) / spacing).astype(_i34_np.int64)
    row = _i34_np.floor((z - origin[1]) / spacing).astype(_i34_np.int64)
    centre_x = origin[0] + (column + 0.5) * spacing
    centre_z = origin[1] + (row + 0.5) * spacing
    offset = _i34_np.hypot(x - centre_x, z - centre_z)
    if accept_offset_m is None:
        if _i34_np.any(offset > 1e-09):
            raise ValueError('reference points are not cell centres: measured offset up to %.6f m (a 30 m integer node sits %.1f m from the cell centre it belongs to). Pass accept_offset_m to accept it explicitly; this module does not snap' % (float(offset.max()), HALF_CELL_M))
    else:
        accepted = _finite_nonnegative(accept_offset_m, 'accept_offset_m')
        if float(offset.max()) > accepted + 1e-09:
            raise ValueError('measured offset up to %.6f m exceeds the accepted offset %.6f m; this module reports the containing cell but never moves the requesting point' % (float(offset.max()), accepted))
    return {'row_index': row, 'column_index': column, 'cell_centre_x_m': centre_x, 'cell_centre_z_m': centre_z, 'offset_m': offset, 'snapped': False, 'semantics': 'row/column index the cell whose centre is reported; the requesting point keeps its own coordinate and is never moved'}

def _rock_lookup():
    """Per-rock-index lookup arrays built from a deep copy of the rock table."""
    table = rock_table()
    by_id = {record['id']: record for record in table}
    mohs = _i34_np.asarray([by_id[name]['mohs_hardness'] for name in ROCK_ORDER], _i34_np.float64)
    solubility = _i34_np.asarray([by_id[name]['solubility'] for name in ROCK_ORDER], _i34_np.float64)
    porosity = _i34_np.asarray([by_id[name]['porosity'] for name in ROCK_ORDER], _i34_np.float64)
    return {'mohs_hardness': mohs, 'solubility': solubility, 'porosity': porosity}

def default_extended_properties():
    """Every rock starts `pending`: no strength/permeability constant is invented."""
    pending = {field: {'status': PENDING, 'units': unit, 'reason': 'no declared source for this rock; the first card does not invent a magnitude for it'} for field, unit in EXTENDED_FIELDS.items()}
    return {name: _i34_json.loads(_properties_canonical(pending)) for name in ROCK_ORDER}

def normalize_extended_properties(table=None):
    """Validate a per-rock extended property table; unknown rocks/fields rejected."""
    if table is None:
        return default_extended_properties()
    if not isinstance(table, dict):
        raise ValueError('extended property table must be a dict keyed by rock id')
    unknown = sorted(set(table) - set(ROCK_ORDER))
    if unknown:
        raise ValueError('unknown rock ids in extended property table: %r' % (unknown,))
    result = {}
    for name in ROCK_ORDER:
        entry = table.get(name)
        if entry is None:
            result[name] = _i34_json.loads(_properties_canonical(default_extended_properties()[name]))
            continue
        if not isinstance(entry, dict):
            raise ValueError('extended property entry for %r must be a dict' % (name,))
        extra = sorted(set(entry) - set(EXTENDED_FIELDS))
        if extra:
            raise ValueError('unknown extended fields for %r: %r' % (name, extra))
        fields = {}
        for field, unit in EXTENDED_FIELDS.items():
            record = entry.get(field)
            if record is None:
                fields[field] = _i34_json.loads(_properties_canonical(default_extended_properties()[name][field]))
                continue
            if not isinstance(record, dict):
                raise ValueError('%s.%s must be a dict' % (name, field))
            if record.get('units') != unit:
                raise ValueError('%s.%s units must be %r' % (name, field, unit))
            if record.get('status') == PENDING:
                reason = record.get('reason')
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError('%s.%s pending entries need a reason' % (name, field))
                fields[field] = {'status': PENDING, 'units': unit, 'reason': reason}
                continue
            if record.get('status') != DECLARED:
                raise ValueError("%s.%s status must be 'declared' or 'pending'" % (name, field))
            value = _finite_nonnegative(record.get('value'), '%s.%s.value' % (name, field))
            for key in ('source', 'rock_mass_scale'):
                text = record.get(key)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError('%s.%s declared entries need a non-empty %r (a value without a source is not allowed)' % (name, field, key))
            fields[field] = {'status': DECLARED, 'units': unit, 'value': value, 'source': record['source'], 'rock_mass_scale': record['rock_mass_scale']}
        result[name] = fields
    return result

def extended_properties_identity(table):
    """Identity of an extended table, used in the bundle identity."""
    return _i34_hashlib.sha256(_properties_canonical(normalize_extended_properties(table)).encode('utf-8')).hexdigest()

def _extended_arrays(table, rock_index):
    """Expand declared extended fields per cell, plus a per-cell availability mask.

    A partially declared table must not force an invented number for the rocks it
    left ``pending``. So each declared field is emitted together with a boolean
    ``<field>_available`` mask: ``True`` only where the cell's rock declares the
    field. Cell values where the mask is ``False`` are exactly ``0.0`` **and**
    carry no meaning; callers must read the mask. ``pending_rock_ids`` records, per
    field, which rocks are still missing a declared value.
    """
    order = ROCK_ORDER
    out = {}
    pending = {}
    for field in EXTENDED_FIELDS:
        values = _i34_np.zeros(len(order), _i34_np.float64)
        declared = _i34_np.zeros(len(order), bool)
        undeclared = []
        for position, name in enumerate(order):
            record = table[name][field]
            if record['status'] != DECLARED:
                undeclared.append(name)
                continue
            values[position] = record['value']
            declared[position] = True
        pending[field] = undeclared
        if undeclared and len(undeclared) == len(order):
            continue
        out[field] = _i34_np.ascontiguousarray(values[rock_index], _i34_np.float64)
        out[field + '_available'] = _i34_np.ascontiguousarray(declared[rock_index], bool)
    return (out, pending)

def normalize_strata_declaration(declaration, shape):
    """A finite, declared bedrock thickness. No declaration stays unknown."""
    if declaration is None:
        return {'status': UNKNOWN_NO_SOURCE, 'values': None, 'reason': 'no bedrock/strata thickness source is declared; the value is unknown, never zero and never half-infinite'}
    if not isinstance(declaration, dict):
        raise ValueError('strata_declaration must be a dict or None')
    source = declaration.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError("strata_declaration needs a non-empty 'source'")
    thickness = declaration.get('bedrock_thickness_m')
    values = _i34_np.asarray(thickness, _i34_np.float64)
    if values.ndim == 0:
        values = _i34_np.full(shape, _finite_nonnegative(values.item(), 'bedrock_thickness_m'), _i34_np.float64)
    else:
        if values.shape != shape:
            raise ValueError('bedrock_thickness_m must be scalar or same-shape')
        if not _i34_np.isfinite(values).all() or _i34_np.any(values < 0.0):
            raise ValueError('bedrock_thickness_m must be finite and non-negative')
        values = _i34_np.ascontiguousarray(values, _i34_np.float64)
    return {'status': DECLARED, 'values': values, 'source': source}

def normalize_joint_declaration(declaration):
    """Declared joint sets; no joint field is generated here."""
    if declaration is None:
        return {'status': PENDING, 'sets': [], 'reason': 'no joint geometry declared; the lithology core samples a fracture density and a layering score, not joint sets'}
    if not isinstance(declaration, dict):
        raise ValueError('joint_declaration must be a dict or None')
    source = declaration.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError("joint_declaration needs a non-empty 'source'")
    sets = declaration.get('sets')
    if not isinstance(sets, list) or not sets:
        raise ValueError('joint_declaration.sets must be a non-empty list')
    normalized = []
    for position, item in enumerate(sets):
        if not isinstance(item, dict):
            raise ValueError('joint set %d must be a dict' % (position,))
        strike = item.get('strike_deg')
        dip = item.get('dip_deg')
        spacing = item.get('spacing_m')
        for value, name in ((strike, 'strike_deg'), (dip, 'dip_deg'), (spacing, 'spacing_m')):
            if isinstance(value, (bool, _i34_np.bool_)) or not isinstance(value, (int, float, _i34_np.integer, _i34_np.floating)):
                raise ValueError('joint set %d %s must be numeric' % (position, name))
            if not _i34_math.isfinite(float(value)):
                raise ValueError('joint set %d %s must be finite' % (position, name))
        strike = float(strike)
        dip = float(dip)
        spacing = float(spacing)
        if not 0.0 <= strike < 360.0:
            raise ValueError('joint strike_deg must satisfy 0 <= strike < 360')
        if not 0.0 <= dip <= 90.0:
            raise ValueError('joint dip_deg must satisfy 0 <= dip <= 90')
        if spacing <= 0.0:
            raise ValueError('joint spacing_m must be positive')
        normalized.append({'strike_deg': strike, 'dip_deg': dip, 'spacing_m': spacing})
    return {'status': DECLARED, 'sets': normalized, 'source': source}

def fault_context(declaration=None):
    """Fault geometry as a plain serializable declaration, never a model."""
    if declaration is None:
        return {'status': PENDING, 'strata_offset_status': PENDING, 'reason': 'no fault declaration supplied; this module models no fault'}
    if not isinstance(declaration, dict):
        raise ValueError('fault declaration must be a dict or None')
    source = declaration.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError("fault declaration needs a non-empty 'source'")
    origin = declaration.get('plane_origin_xz_m')
    origin = _i34_np.asarray(origin, _i34_np.float64)
    if origin.shape != (2,) or not _i34_np.isfinite(origin).all():
        raise ValueError('fault plane_origin_xz_m must be two finite coordinates')
    strike = declaration.get('strike_degrees')
    slip = declaration.get('slip_m')
    transition = declaration.get('transition_width_m')
    side = declaration.get('moving_side')
    for value, name in ((strike, 'strike_degrees'), (slip, 'slip_m'), (transition, 'transition_width_m')):
        if isinstance(value, (bool, _i34_np.bool_)) or not isinstance(value, (int, float, _i34_np.integer, _i34_np.floating)):
            raise ValueError('fault %s must be numeric' % (name,))
        if not _i34_math.isfinite(float(value)):
            raise ValueError('fault %s must be finite' % (name,))
    if side not in ('positive', 'negative'):
        raise ValueError("fault moving_side must be 'positive' or 'negative'")
    if float(transition) <= 0.0:
        raise ValueError('fault transition_width_m must be positive')
    if float(slip) < 0.0:
        raise ValueError('fault slip_m is a magnitude and must be non-negative')
    return {'status': DECLARED_GEOMETRY_NOT_LITHOLOGY_OFFSET, 'strata_offset_status': UNVERIFIED, 'source': source, 'plane_origin_xz_m': [float(origin[0]), float(origin[1])], 'strike_degrees': float(strike), 'slip_m': float(slip), 'moving_side': side, 'transition_width_m': float(transition), 'note': 'geometry only: this module does not prove that the declaration offsets the 30 m lithology column, so the strata offset stays unverified'}

def layer_definitions():
    """The one layer stack this module reports: cover, then bedrock."""
    return [{'name': 'cover', 'order': 0, 'thickness_field': 'cover_thickness_m', 'property_source': 'terrain_pipeline.geology.make_material_field', 'semantics': 'erodible material thickness: not soil depth, not regolith stock'}, {'name': 'bedrock', 'order': 1, 'thickness_field': 'bedrock_thickness_m', 'property_source': 'terrain_pipeline.geology.sample_lithology_points', 'thickness_default_status': UNKNOWN_NO_SOURCE, 'semantics': 'one rock per map column; no strata column, dip or age'}]

def _base_metadata(*, world_seed, fields_status, extra):
    metadata = {'schema': PROPERTIES_SCHEMA, 'algorithm': PROPERTIES_ALGORITHM, 'format_version': FORMAT_VERSION, 'fields_status': fields_status, 'units': dict(UNITS), 'limitations': list(PROPERTIES_LIMITATIONS), 'rock_table_identity_sha256': rock_table_identity(), 'rock_order': list(ROCK_ORDER), 'class_order': list(CLASS_IDS), 'lithology_subseeds': lithology_subseeds(world_seed), 'lithology_seed_derivation': SEED_DERIVATION, 'world_seed': int(world_seed), 'grid_spacing_m': GRID_SPACING_M, 'half_cell_m': HALF_CELL_M, 'coordinate_convention': 'X east; Z south; [z, x]; absolute world metres', 'thickness_coordinates': 'cell centres origin_m_xz + (index + 0.5) * spacing_m', 'synthetic_lithology': True, 'measured_lithology': False, 'value_status': PROVENANCE}
    metadata.update(extra)
    metadata['declared_uncalibrated'] = 'rock attribute values and any declared extended property are engineering reference values, not calibrated measurements'
    return metadata

def _properties_bundle(arrays, metadata):
    frozen = {}
    for name, values in arrays.items():
        contiguous = _i34_np.ascontiguousarray(values)
        frozen[name] = _i34_np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)
    metadata = _i34_json.loads(_properties_canonical(metadata))
    definitions = layer_definitions()
    return {'schema': PROPERTIES_SCHEMA, 'arrays': frozen, 'layer_definitions': definitions, 'metadata': metadata, 'identity_sha256': _properties_identity(frozen, metadata, definitions)}

def _lithology_arrays(x_m, z_m, world_seed):
    sampled = sample_lithology_points(x_m, z_m, world_seed=world_seed)
    rock_index = _i34_np.asarray(sampled['rock_index'], _i34_np.int64)
    arrays = {'rock_index': rock_index, 'class_index': _i34_np.asarray(sampled['class_index'], _i34_np.int64), 'bed_hardness': _i34_np.asarray(sampled['bed_hardness'], _i34_np.float64), 'bank_hardness': _i34_np.asarray(sampled['bank_hardness'], _i34_np.float64), 'erodibility_index': _i34_np.asarray(sampled['erodibility_index'], _i34_np.float64)}
    lookup = _rock_lookup()
    for name in ('mohs_hardness', 'solubility', 'porosity'):
        arrays[name] = _i34_np.ascontiguousarray(lookup[name][rock_index], _i34_np.float64)
    return (arrays, rock_index)

def properties_at(x_m, z_m, *, world_seed=DEFAULT_WORLD_SEED, extended_properties=None, joint_declaration=None):
    """Point-set properties: rock identity plus the non-thickness properties.

    Thickness fields are deliberately absent: the erodible cover can only be
    produced on an aligned grid window, so pretending to have it per arbitrary
    point would be a half-cell lie. Use :func:`geology_column` for thicknesses.
    """
    seed = _properties_check_world_seed(world_seed)
    x = _i34_np.asarray(x_m, _i34_np.float64)
    z = _i34_np.asarray(z_m, _i34_np.float64)
    x, z = _i34_np.broadcast_arrays(x, z)
    if not _i34_np.isfinite(x).all() or not _i34_np.isfinite(z).all():
        raise ValueError('x_m and z_m must be finite absolute world metres')
    n = int(x.size)
    budget = properties_preflight(n, point_mode=True)
    table = normalize_extended_properties(extended_properties)
    joints = normalize_joint_declaration(joint_declaration)
    arrays, rock_index = _lithology_arrays(x, z, seed)
    extended, pending = _extended_arrays(table, rock_index)
    arrays.update(extended)
    arrays['x_m'] = _i34_np.ascontiguousarray(x, _i34_np.float64)
    arrays['z_m'] = _i34_np.ascontiguousarray(z, _i34_np.float64)
    fields_status = {name: COMPUTED for name in arrays}
    fields_status['cover_thickness_m'] = NOT_SAMPLED_NO_GRID_WINDOW
    fields_status['bedrock_thickness_m'] = UNKNOWN_NO_SOURCE
    for field in EXTENDED_FIELDS:
        if field + '_available' in arrays:
            fields_status[field] = DECLARED if not pending[field] else PARTIALLY_DECLARED
        else:
            fields_status[field] = PENDING
    metadata = _base_metadata(world_seed=seed, fields_status=fields_status, extra={'form': 'point_set', 'point_count': n, 'points_digest': _points_digest(x, z), 'extended_properties': table, 'extended_properties_identity_sha256': extended_properties_identity(table), 'extended_pending_rock_ids': pending, 'joint_declaration': joints, 'budget': budget})
    return _properties_bundle(arrays, metadata)

def geology_column(shape, *, origin_m_xz, spacing_m, world_seed=DEFAULT_WORLD_SEED, material_seed, extended_properties=None, joint_declaration=None, strata_declaration=None, fault_declaration=None):
    """Grid-form layer column: cover thickness plus the bedrock rock column.

    Both cores are sampled at the **same** cell-centre coordinates, so a column's
    cover thickness and its rock identity describe one physical point.
    ``material_seed`` is required: this module refuses to invent a third seed
    derivation. A caller that wants to match the A1 environment query passes the
    seed it derives there for purpose ``geography-stage2-material``.
    """
    shape = _properties_shape(shape)
    spacing = _check_spacing(spacing_m)
    origin = _properties_origin(origin_m_xz)
    cells = int(shape[0] * shape[1])
    budget = properties_preflight(cells, point_mode=False)
    seed = _properties_check_world_seed(world_seed)
    material_seed = _properties_check_world_seed(material_seed)
    x_m, z_m = cell_centres(shape, origin_m_xz=origin, spacing_m=spacing)
    arrays, rock_index = _lithology_arrays(x_m, z_m, seed)
    material = make_material_field(shape, origin_m_xz=[float(origin[0]), float(origin[1])], spacing_m=spacing, seed=material_seed)
    cover = _i34_np.asarray(material['arrays']['erodible_thickness_m'], _i34_np.float64)
    if cover.shape != shape:
        raise ValueError('material thickness shape mismatch')
    arrays['cover_thickness_m'] = _i34_np.ascontiguousarray(cover, _i34_np.float64)
    strata = normalize_strata_declaration(strata_declaration, shape)
    if strata['values'] is not None:
        arrays['bedrock_thickness_m'] = strata['values']
    table = normalize_extended_properties(extended_properties)
    extended, pending = _extended_arrays(table, rock_index)
    arrays.update(extended)
    joints = normalize_joint_declaration(joint_declaration)
    fault = fault_context(fault_declaration)
    fields_status = {name: COMPUTED for name in arrays}
    fields_status['bedrock_thickness_m'] = strata['status']
    for field in EXTENDED_FIELDS:
        if field + '_available' in arrays:
            fields_status[field] = DECLARED if not pending[field] else PARTIALLY_DECLARED
        else:
            fields_status[field] = PENDING
    metadata = _base_metadata(world_seed=seed, fields_status=fields_status, extra={'form': 'grid_column', 'shape': list(shape), 'origin_m_xz': [float(origin[0]), float(origin[1])], 'cell_centres_sampled': True, 'bedrock_thickness_source': strata.get('source', UNKNOWN_NO_SOURCE), 'material': {'algorithm': material['metadata']['algorithm'], 'seed': int(material_seed), 'parameters': material['metadata']['parameters'], 'identity_sha256': material['identity_sha256'], 'semantics': 'erodible thickness, not soil depth and not a stock'}, 'extended_properties': table, 'extended_properties_identity_sha256': extended_properties_identity(table), 'extended_pending_rock_ids': pending, 'joint_declaration': joints, 'fault_context': fault, 'budget': budget})
    return _properties_bundle(arrays, metadata)

def width_law_hardness(bundle):
    """Return ``(bed_hardness, bank_hardness)`` copies for the width law.

    This is the explicit bridge to
    :func:`terrain_pipeline.surface_rivers.world_reach_lake.channel_width_from_lithology_m`
    (and to the older ``metric_discharge_geometry`` hardness inputs). It is an
    opt-in call: nothing in this module wires itself into a default path.
    """
    validate_geology_properties(bundle)
    arrays = bundle['arrays']
    return (arrays['bed_hardness'].copy(), arrays['bank_hardness'].copy())

def channel_width_m(bundle, contributing_area_m2, *, reference_discharge_m3_s, reference_width_m, min_width_m, max_width_m, design_runoff_mm_h=1.0, width_exponent=0.5, bed_lateral_factor=1.5, bank_lateral_factor=1.5, bed_hardness=None, bank_hardness=None):
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
        bed = _i34_np.ascontiguousarray(_i34_np.asarray(bed_hardness, _i34_np.float64))
        _check_hardness_override(bed, shape, 'bed_hardness')
        overrides.append('bed_hardness')
    if bank_hardness is not None:
        bank = _i34_np.ascontiguousarray(_i34_np.asarray(bank_hardness, _i34_np.float64))
        _check_hardness_override(bank, shape, 'bank_hardness')
        overrides.append('bank_hardness')
    flat_bed = _i34_np.ascontiguousarray(_i34_np.asarray(bed, _i34_np.float64).reshape(-1))
    flat_bank = _i34_np.ascontiguousarray(_i34_np.asarray(bank, _i34_np.float64).reshape(-1))
    area = _i34_np.asarray(contributing_area_m2, _i34_np.float64).reshape(-1)
    if area.shape != flat_bed.shape:
        raise ValueError('one contributing area per geology column required')
    widths, design_q = channel_width_from_lithology_m(area, flat_bed, flat_bank, reference_discharge_m3_s=reference_discharge_m3_s, reference_width_m=reference_width_m, min_width_m=min_width_m, max_width_m=max_width_m, design_runoff_mm_h=design_runoff_mm_h, width_exponent=width_exponent, bed_lateral_factor=bed_lateral_factor, bank_lateral_factor=bank_lateral_factor)
    return {'width_m': _i34_np.ascontiguousarray(_i34_np.asarray(widths, _i34_np.float64).reshape(shape)), 'design_q_m3_s': _i34_np.ascontiguousarray(_i34_np.asarray(design_q, _i34_np.float64).reshape(shape)), 'consumed_fields': ['bed_hardness', 'bank_hardness'], 'overrides_used': overrides, 'consumer': 'surface_rivers.world_reach_lake.channel_width_from_lithology_m', 'units': {'width_m': 'm', 'design_q_m3_s': 'm3/s'}}

def _check_hardness_override(values, shape, name):
    if values.shape != shape:
        raise ValueError(name + ' override must match the bundle shape')
    if not _i34_np.isfinite(values).all() or _i34_np.any(values < 0.0) or _i34_np.any(values > 1.0):
        raise ValueError(name + ' override must be finite and lie in [0, 1]')

def properties_describe():
    """Static declaration for review; it takes part in no numeric result."""
    return {'schema': PROPERTIES_SCHEMA, 'algorithm': PROPERTIES_ALGORITHM, 'format_version': FORMAT_VERSION, 'grid_spacing_m': GRID_SPACING_M, 'half_cell_m': HALF_CELL_M, 'supported_spacings_m': [GRID_SPACING_M], 'max_points': MAX_POINTS, 'max_grid_cells': MAX_GRID_CELLS, 'max_output_bytes': MAX_OUTPUT_BYTES, 'layer_names': [layer['name'] for layer in layer_definitions()], 'int_fields': list(INT_FIELDS), 'float_fields': list(FLOAT_FIELDS), 'point_form_only_float_fields': list(SIGNED_FIELDS), 'optional_float_fields': list(OPTIONAL_FLOAT_FIELDS), 'extended_fields': dict(EXTENDED_FIELDS), 'status_vocabulary': [COMPUTED, DECLARED, PARTIALLY_DECLARED, PENDING, UNKNOWN_NO_SOURCE, NOT_SAMPLED_NO_GRID_WINDOW, DECLARED_GEOMETRY_NOT_LITHOLOGY_OFFSET, UNVERIFIED], 'fields_without_consumer': ['intrinsic_permeability_m2', 'solubility'], 'explicit_consumers': {'channel_width_m': 'surface_rivers.world_reach_lake.channel_width_from_lithology_m (bed_hardness + bank_hardness)'}, 'never': ['a second rock table', 'recomputing bed_hardness or bank_hardness', 'inverting porosity into permeability', 'treating compressive strength as tensile strength or as erodibility', 'a tectonic, plate or fault-offset model', 'a regolith or soil inventory', 'any temperature input', 'snapping reference points onto cell centres silently', 'an arbitrary spacing mode (10 km compatibility)', 'importing the A1 environment query to reuse its composition'], 'coordinate_semantics': 'cell centres origin + (index + 0.5) * spacing; a 30 m integer reference node is half a cell away'}

def _properties_check_identity(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {'schema', 'arrays', 'layer_definitions', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid geology bundle structure')
    if bundle['schema'] != PROPERTIES_SCHEMA:
        raise ValueError('unsupported geology schema')
    definitions = layer_definitions()
    # Saved pre-consolidation products retain these source names and their
    # original identity. Accept only that complete historical stack; hash the
    # stored definitions below without normalizing or rewriting the bundle.
    historical_definitions = [dict(layer) for layer in definitions]
    historical_definitions[0]['property_source'] = 'terrain_pipeline.td_material_field.make_material_field'
    historical_definitions[1]['property_source'] = 'terrain_pipeline.td_lithology_field.sample_lithology_points'
    if bundle['layer_definitions'] != definitions and bundle['layer_definitions'] != historical_definitions:
        raise ValueError('layer definitions differ from the declared stack')
    if _properties_identity(bundle['arrays'], bundle['metadata'], bundle['layer_definitions']) != bundle['identity_sha256']:
        raise ValueError('geology bundle identity mismatch')

def _validate_extended(bundle, table):
    """Extended fields must match the declared table and their availability mask."""
    arrays = bundle['arrays']
    rock_index = arrays['rock_index']
    pending_recorded = bundle['metadata'].get('extended_pending_rock_ids')
    if not isinstance(pending_recorded, dict):
        raise ValueError('extended_pending_rock_ids must be recorded')
    expected, pending = _extended_arrays(table, rock_index)
    if sorted(pending_recorded) != sorted(pending):
        raise ValueError('extended pending rock ids differ from the declared table')
    for field in EXTENDED_FIELDS:
        if pending_recorded.get(field) != pending[field]:
            raise ValueError('extended pending rock ids mismatch for ' + field)
        mask_name = field + '_available'
        if field in expected:
            if field not in arrays or mask_name not in arrays:
                raise ValueError(field + ' is declared but not stored')
            if arrays[mask_name].dtype != _i34_np.dtype(bool):
                raise ValueError(mask_name + ' must be boolean')
            if not _i34_np.array_equal(arrays[mask_name], expected[mask_name]):
                raise ValueError(mask_name + ' is inconsistent with the declared table')
            declared_mask = expected[mask_name]
            if not _i34_np.array_equal(arrays[field][declared_mask], expected[field][declared_mask]):
                raise ValueError(field + ' is inconsistent with the declared table')
            if _i34_np.any(arrays[field][~declared_mask] != 0.0):
                raise ValueError(field + ' carries a number where the rock has no declared value')
        elif field in arrays or mask_name in arrays:
            raise ValueError(field + ' must not be stored when no rock declares it')

def _validate_shared(bundle):
    metadata = bundle['metadata']
    if metadata.get('schema') != PROPERTIES_SCHEMA:
        raise ValueError('unsupported geology schema')
    if metadata.get('algorithm') != PROPERTIES_ALGORITHM or metadata.get('format_version') != FORMAT_VERSION:
        raise ValueError('unsupported geology identity')
    if metadata.get('rock_table_identity_sha256') != rock_table_identity():
        raise ValueError('rock attribute table differs from the one recorded by the bundle')
    if metadata.get('rock_order') != list(ROCK_ORDER):
        raise ValueError('rock ordering mismatch')
    if metadata.get('grid_spacing_m') != GRID_SPACING_M:
        raise ValueError('bundle spacing is not the 30 m grid')
    if metadata.get('synthetic_lithology') is not True or metadata.get('measured_lithology') is not False:
        raise ValueError('a geology bundle must declare synthetic, unmeasured status')
    if metadata.get('lithology_subseeds') != lithology_subseeds(metadata['world_seed']):
        raise ValueError('lithology sub-seeds do not match the recorded world seed')
    arrays = bundle['arrays']
    for name in INT_FIELDS:
        if name in arrays and arrays[name].dtype != _i34_np.int64:
            raise ValueError(name + ' must be int64')
    for name in FLOAT_FIELDS + OPTIONAL_FLOAT_FIELDS:
        if name not in arrays:
            continue
        values = arrays[name]
        if values.dtype != _i34_np.float64 or not _i34_np.isfinite(values).all():
            raise ValueError(name + ' must be finite float64')
        if name not in SIGNED_FIELDS and _i34_np.any(values < 0.0):
            raise ValueError(name + ' must be non-negative')
    for name in ('bed_hardness', 'bank_hardness'):
        if name in arrays and (_i34_np.any(arrays[name] < 0.0) or _i34_np.any(arrays[name] > 1.0)):
            raise ValueError(name + ' must lie in [0, 1]')
    if 'bank_hardness' in arrays and 'bed_hardness' in arrays:
        if _i34_np.any(arrays['bank_hardness'] > arrays['bed_hardness']):
            raise ValueError('bank hardness must not exceed bed hardness')
    rock_index = arrays['rock_index']
    if rock_index.size and (rock_index.min() < 0 or rock_index.max() >= len(ROCK_ORDER)):
        raise ValueError('rock index out of range')
    lookup = _rock_lookup()
    for name in ('mohs_hardness', 'solubility', 'porosity'):
        if name in arrays and (not _i34_np.array_equal(arrays[name], lookup[name][rock_index])):
            raise ValueError(name + ' is inconsistent with the rock table')
    return metadata

def validate_geology_properties(bundle):
    """Reject a bundle that does not recompute from its own declared inputs."""
    _properties_check_identity(bundle)
    metadata = _validate_shared(bundle)
    form = metadata.get('form')
    table = normalize_extended_properties(metadata.get('extended_properties'))
    if extended_properties_identity(table) != metadata.get('extended_properties_identity_sha256'):
        raise ValueError('extended property identity mismatch')
    _validate_extended(bundle, table)
    if form == 'point_set':
        if 'cover_thickness_m' in bundle['arrays']:
            raise ValueError('point form must not carry a cover thickness')
        status = metadata['fields_status'].get('cover_thickness_m')
        if status != NOT_SAMPLED_NO_GRID_WINDOW:
            raise ValueError('point form must declare the cover thickness as not sampled')
        n = int(metadata['point_count'])
        budget = properties_preflight(n, point_mode=True)
        if budget != metadata['budget']:
            raise ValueError('recorded budget differs from the recomputed one')
    elif form == 'grid_column':
        shape = tuple(metadata['shape'])
        if 'cover_thickness_m' not in bundle['arrays']:
            raise ValueError('grid form must carry a cover thickness')
        if tuple(bundle['arrays']['cover_thickness_m'].shape) != shape:
            raise ValueError('cover thickness shape mismatch')
        status = metadata['fields_status'].get('bedrock_thickness_m')
        if status not in (DECLARED, UNKNOWN_NO_SOURCE):
            raise ValueError('bedrock thickness status must be declared or unknown_no_source')
        if status == UNKNOWN_NO_SOURCE and 'bedrock_thickness_m' in bundle['arrays']:
            raise ValueError('an unknown bedrock thickness must not be stored as a number')
        if status == DECLARED and 'bedrock_thickness_m' not in bundle['arrays']:
            raise ValueError('a declared bedrock thickness must be stored')
        budget = properties_preflight(int(shape[0] * shape[1]), point_mode=False)
        if budget != metadata['budget']:
            raise ValueError('recorded budget differs from the recomputed one')
        if metadata.get('cell_centres_sampled') is not True:
            raise ValueError('grid form must declare cell-centre sampling')
        cell_centres(shape, origin_m_xz=metadata['origin_m_xz'], spacing_m=metadata['grid_spacing_m'])
    else:
        raise ValueError('unknown bundle form')
    return True
STRATA_SCHEMA = 'geology-strata-v1'
STRATA_ALGORITHM = 'declared-parallel-strata-v1'
MAX_STRATA_LAYERS = 64
MAX_CELL_LAYER_VALUES = 1000000
MAX_FAULTS = 8
MAX_JOINT_SETS = 8
ABOVE_COLUMN = 0
INSIDE_STACK = 1
BELOW_COLUMN = 2
STATE_NAMES = {ABOVE_COLUMN: 'above_column', INSIDE_STACK: 'inside_stack', BELOW_COLUMN: 'below_column'}
FAULT_NOT_DECLARED = 'not_declared'
FAULT_OUTSIDE = 'outside'
FAULT_APPLIED = 'applied'
STOCK_PENDING = 'pending_missing_footprint'
STOCK_DECLARED = 'declared'
STRATA_LIMITATIONS = ('layers are declared planes with one common strike and dip; no fold, unconformity, lens or lateral facies change is modelled', 'layer thickness is VERTICAL thickness measured at the anchor (field vertical_thickness_m); normal thickness is vertical * cos(dip). With a horizontal projected footprint the volume is area * vertical thickness, and normal thickness * (area / cos(dip)) gives the same rock volume', 'dip = 90 is refused: a vertical layer is not a single-valued height field', 'a fault is a piecewise-discontinuous engineering offset inside a declared influence width; it is not a mechanical rupture model', 'below the deepest horizon the rock is unknown_no_source; the surface rock is never copied downward', 'no weathering, erosion or stock model here; a finite declared volume can be reported but it is not a soil or regolith inventory')

def _finite(value, name):
    if isinstance(value, (bool, _i36_np.bool_)) or not isinstance(value, (int, float, _i36_np.integer, _i36_np.floating)):
        raise ValueError(name + ' must be numeric')
    result = float(value)
    if not _i36_math.isfinite(result):
        raise ValueError(name + ' must be finite')
    return result

def _strata_positive(value, name):
    result = _finite(value, name)
    if result <= 0.0:
        raise ValueError(name + ' must be positive')
    return result

def _dip(value, name):
    result = _finite(value, name)
    if not 0.0 <= result < 90.0:
        raise ValueError('%s must satisfy 0 <= %s < 90; dip = 90 is a vertical plane and is refused rather than approximated' % (name, name))
    return result

def _strike(value):
    result = _finite(value, 'strike_deg')
    if not 0.0 <= result < 360.0:
        raise ValueError('strike_deg must satisfy 0 <= strike < 360')
    return result

def _points(x_m, z_m):
    x = _i36_np.asarray(x_m, _i36_np.float64)
    z = _i36_np.asarray(z_m, _i36_np.float64)
    x, z = _i36_np.broadcast_arrays(x, z)
    if not _i36_np.isfinite(x).all() or not _i36_np.isfinite(z).all():
        raise ValueError('x_m and z_m must be finite absolute world metres')
    return (x, z)

def strata_preflight(n_points, n_layers, *, with_horizons=False, point_mode=True):
    """Reject an oversized request before any array or layer container exists."""
    for value, name in ((n_points, 'n_points'), (n_layers, 'n_layers')):
        if isinstance(value, (bool, _i36_np.bool_)) or not isinstance(value, (int, _i36_np.integer)):
            raise ValueError(name + ' must be an integer')
    points = int(n_points)
    layers = int(n_layers)
    if points <= 0 or layers <= 0:
        raise ValueError('point and layer counts must be positive')
    if layers > MAX_STRATA_LAYERS:
        raise ValueError('layer count %d exceeds %d' % (layers, MAX_STRATA_LAYERS))
    limit = MAX_POINTS if point_mode else MAX_GRID_CELLS
    if points > limit:
        raise ValueError('%s count %d exceeds %d' % ('point' if point_mode else 'cell', points, limit))
    horizon_values = points * (layers + 1)
    if with_horizons and horizon_values > MAX_CELL_LAYER_VALUES:
        raise ValueError('horizon output %d values (points x layers+1) exceeds %d; query fewer points or ask for the layer index only' % (horizon_values, MAX_CELL_LAYER_VALUES))
    return {'n_points': points, 'n_layers': layers, 'with_horizons': bool(with_horizons), 'horizon_values': horizon_values if with_horizons else 0, 'max_strata_layers': MAX_STRATA_LAYERS, 'max_points': MAX_POINTS, 'max_grid_cells': MAX_GRID_CELLS, 'max_cell_layer_values': MAX_CELL_LAYER_VALUES, 'max_faults': MAX_FAULTS, 'max_joint_sets': MAX_JOINT_SETS}

def normalize_stack(declaration):
    """Validate a declared layer stack; fill nothing, invent nothing."""
    if declaration is None:
        return {'status': UNKNOWN_NO_SOURCE, 'reason': 'no stratigraphy declared; a vertical query has no rock source'}
    if not isinstance(declaration, dict):
        raise ValueError('strata declaration must be a dict or None')
    source = declaration.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError("strata declaration needs a non-empty 'source'")
    anchor = declaration.get('anchor_xz_m')
    anchor = _i36_np.asarray(anchor, _i36_np.float64)
    if anchor.shape != (2,) or not _i36_np.isfinite(anchor).all():
        raise ValueError('anchor_xz_m must be two finite coordinates')
    top = _finite(declaration.get('top_elevation_m'), 'top_elevation_m')
    strike = _strike(declaration.get('strike_deg'))
    dip = _dip(declaration.get('dip_deg'), 'dip_deg')
    layers = declaration.get('layers')
    if not isinstance(layers, list) or not layers:
        raise ValueError("strata declaration needs a non-empty 'layers' list")
    if len(layers) > MAX_STRATA_LAYERS:
        raise ValueError('layer count exceeds %d' % (MAX_STRATA_LAYERS,))
    normalized = []
    cumulative = 0.0
    for position, entry in enumerate(layers):
        if not isinstance(entry, dict):
            raise ValueError('layer %d must be a dict' % (position,))
        rock_id = entry.get('rock_id')
        if rock_id not in ROCK_POSITION:
            raise ValueError('layer %d has an unknown rock_id: %r' % (position, rock_id))
        thickness = _strata_positive(entry.get('vertical_thickness_m'), 'layers[%d].vertical_thickness_m' % (position,))
        layer_source = entry.get('source')
        if not isinstance(layer_source, str) or not layer_source.strip():
            raise ValueError("layer %d needs a non-empty 'source'" % (position,))
        normalized.append({'rock_id': rock_id, 'rock_index': int(ROCK_POSITION[rock_id]), 'vertical_thickness_m': thickness, 'source': layer_source})
        cumulative += thickness
    horizon_elevations = [top]
    for entry in normalized:
        horizon_elevations.append(horizon_elevations[-1] - entry['vertical_thickness_m'])
    return {'status': DECLARED, 'source': source, 'anchor_xz_m': [float(anchor[0]), float(anchor[1])], 'top_elevation_m': top, 'strike_deg': strike, 'dip_deg': dip, 'layer_count': len(normalized), 'layers': normalized, 'horizon_elevation_m': horizon_elevations, 'total_vertical_thickness_m': cumulative, 'thickness_kind': 'vertical_at_anchor_not_normal', 'synthetic_declared_stratigraphy': True, 'measured_stratigraphy': False}

def _along_dip(stack, x, z):
    """Horizontal coordinate along the (right-hand) dip direction, in metres."""
    strike = _i36_math.radians(stack['strike_deg'])
    anchor_x, anchor_z = stack['anchor_xz_m']
    return (x - anchor_x) * _i36_math.cos(strike) + (z - anchor_z) * _i36_math.sin(strike)

def horizons_at(x_m, z_m, stack, *, point_mode=True):
    """Elevation of every horizon at the given points, shape ``(L+1, ...)``.

    ``h_k = H_k - tan(dip) * u``; all horizons are parallel planes. The layout is
    ``[horizon, z, x]`` for a grid input, matching the repository convention.
    """
    if stack is None or stack.get('status') != DECLARED:
        raise ValueError('a declared stack is required to evaluate horizons')
    x, z = _points(x_m, z_m)
    n = int(x.size)
    layers = stack['layer_count']
    budget = strata_preflight(n, layers, with_horizons=True, point_mode=bool(point_mode))
    slope = _i36_math.tan(_i36_math.radians(stack['dip_deg']))
    shift = slope * _along_dip(stack, x, z)
    reference = _i36_np.asarray(stack['horizon_elevation_m'], _i36_np.float64)
    horizons = reference.reshape((layers + 1,) + (1,) * x.ndim) - shift[None, ...]
    return (_i36_np.ascontiguousarray(horizons, _i36_np.float64), budget)

def query_layers(x_m, z_m, elevation_m, stack, *, faults=None, return_horizons=False):
    """Which layer and rock sits at ``(x, z, elevation)``.

    Returns ``state`` (``above_column`` / ``inside_stack`` / ``below_column``),
    ``layer_index`` (``-1`` outside the stack) and ``rock_index`` (``-1`` when the
    rock is unknown). Below the deepest horizon the answer is unknown: the surface
    rock is never copied down.
    """
    x, z = _points(x_m, z_m)
    elev = _i36_np.asarray(elevation_m, _i36_np.float64)
    elev = _i36_np.broadcast_to(elev, x.shape)
    if not _i36_np.isfinite(elev).all():
        raise ValueError('elevation_m must be finite')
    if stack is None or stack.get('status') != DECLARED:
        shape = x.shape
        return {'state': _i36_np.full(shape, BELOW_COLUMN, _i36_np.int8), 'layer_index': _i36_np.full(shape, -1, _i36_np.int64), 'rock_index': _i36_np.full(shape, -1, _i36_np.int64), 'fault_effect': _i36_np.full(shape, FAULT_NOT_DECLARED, dtype=object), 'applied_offset_m': _i36_np.zeros(shape, _i36_np.float64), 'status': UNKNOWN_NO_SOURCE, 'reason': 'no stratigraphy declared; no rock source for any elevation'}
    layers = stack['layer_count']
    with_horizons = bool(return_horizons)
    point_mode = x.ndim == 1
    budget = strata_preflight(int(x.size), layers, with_horizons=with_horizons, point_mode=point_mode)
    offset, fault_effect = fault_offset_m(x, z, faults)
    shifted = elev - offset
    horizons, _ = horizons_at(x, z, stack, point_mode=point_mode)
    top = horizons[0]
    bottom = horizons[layers]
    state = _i36_np.full(x.shape, INSIDE_STACK, _i36_np.int8)
    state = _i36_np.where(shifted >= top, ABOVE_COLUMN, state)
    state = _i36_np.where(shifted < bottom, BELOW_COLUMN, state)
    layer_index = _i36_np.full(x.shape, -1, _i36_np.int64)
    inside = state == INSIDE_STACK
    for position in range(layers):
        selected = inside & (layer_index < 0) & (shifted < horizons[position]) & (shifted >= horizons[position + 1])
        layer_index = _i36_np.where(selected, position, layer_index)
    if _i36_np.any(inside & (layer_index < 0)):
        raise ValueError('an inside-stack point matched no layer: the layer bounds are not mutually exclusive')
    rock_index = _i36_np.full(x.shape, -1, _i36_np.int64)
    table = _i36_np.asarray([entry['rock_index'] for entry in stack['layers']], _i36_np.int64)
    valid = layer_index >= 0
    if valid.any():
        rock_index[valid] = table[layer_index[valid]]
    result = {'state': state, 'layer_index': layer_index, 'rock_index': rock_index, 'fault_effect': fault_effect, 'applied_offset_m': offset, 'status': DECLARED, 'budget': budget, 'thickness_kind': stack['thickness_kind']}
    if return_horizons:
        result['horizon_elevation_m'] = horizons
    return result

def normalize_faults(declarations):
    """Validate finite fault bands; a band without a width is refused."""
    if declarations is None:
        return []
    if not isinstance(declarations, list):
        raise ValueError('fault declarations must be a list or None')
    if len(declarations) > MAX_FAULTS:
        raise ValueError('fault count exceeds %d' % (MAX_FAULTS,))
    result = []
    for position, entry in enumerate(declarations):
        if not isinstance(entry, dict):
            raise ValueError('fault %d must be a dict' % (position,))
        segment = _i36_np.asarray(entry.get('segment_xz_m'), _i36_np.float64)
        if segment.shape != (2, 2) or not _i36_np.isfinite(segment).all():
            raise ValueError('fault %d segment_xz_m must be two [x, z] endpoints' % (position,))
        length = _i36_math.hypot(*segment[1] - segment[0])
        if length <= 0.0:
            raise ValueError('fault %d segment has zero length' % (position,))
        offset = _finite(entry.get('vertical_offset_m'), 'fault %d vertical_offset_m' % (position,))
        if offset == 0.0:
            raise ValueError('fault %d offset of zero is not a declaration' % (position,))
        side = entry.get('moving_side')
        if side not in ('positive', 'negative'):
            raise ValueError("fault %d moving_side must be 'positive' or 'negative'" % (position,))
        width = _strata_positive(entry.get('influence_width_m'), 'fault %d influence_width_m' % (position,))
        source = entry.get('source')
        if not isinstance(source, str) or not source.strip():
            raise ValueError("fault %d needs a non-empty 'source'" % (position,))
        result.append({'segment_xz_m': segment.tolist(), 'vertical_offset_m': offset, 'moving_side': side, 'influence_width_m': width, 'source': source, 'half_width_m': 0.5 * width})
    return result

def _segment_distance(x, z, segment):
    """Distance to the segment and the signed side (cross product sign)."""
    ax, az = segment[0]
    bx, bz = segment[1]
    dx = bx - ax
    dz = bz - az
    length_squared = dx * dx + dz * dz
    t = ((x - ax) * dx + (z - az) * dz) / length_squared
    clamped = _i36_np.clip(t, 0.0, 1.0)
    closest_x = ax + clamped * dx
    closest_z = az + clamped * dz
    distance = _i36_np.hypot(x - closest_x, z - closest_z)
    side = dx * (z - az) - dz * (x - ax)
    return (distance, side, t)

def fault_offset_m(x_m, z_m, faults):
    """Signed horizon offset at each point: inside a band only, zero elsewhere."""
    x, z = _points(x_m, z_m)
    declared = normalize_faults(faults)
    offset = _i36_np.zeros(x.shape, _i36_np.float64)
    effect = _i36_np.full(x.shape, FAULT_NOT_DECLARED if not declared else FAULT_OUTSIDE, dtype=object)
    for fault in declared:
        distance, side, _t = _segment_distance(x, z, _i36_np.asarray(fault['segment_xz_m']))
        inside = distance <= fault['half_width_m']
        positive_side = side >= 0.0
        moving = positive_side if fault['moving_side'] == 'positive' else ~positive_side
        applied = inside & moving
        offset = _i36_np.where(applied, offset + fault['vertical_offset_m'], offset)
        effect = _i36_np.where(inside, FAULT_APPLIED, effect)
    return (offset, effect)

def normalize_joints(declaration):
    """World-anchored joint sets: strike, dip, spacing and phase in metres."""
    if declaration is None:
        return {'status': PENDING, 'reason': 'no joint geometry declared; the lithology core samples a fracture density score, not joint planes'}
    if not isinstance(declaration, dict):
        raise ValueError('joint declaration must be a dict or None')
    source = declaration.get('source')
    if not isinstance(source, str) or not source.strip():
        raise ValueError("joint declaration needs a non-empty 'source'")
    sets = declaration.get('sets')
    if not isinstance(sets, list) or not sets:
        raise ValueError('joint declaration sets must be a non-empty list')
    if len(sets) > MAX_JOINT_SETS:
        raise ValueError('joint set count exceeds %d' % (MAX_JOINT_SETS,))
    anchor = _i36_np.asarray(declaration.get('anchor_xz_m'), _i36_np.float64)
    if anchor.shape != (2,) or not _i36_np.isfinite(anchor).all():
        raise ValueError('joint declaration anchor_xz_m must be two finite coordinates')
    normalized = []
    for position, entry in enumerate(sets):
        if not isinstance(entry, dict):
            raise ValueError('joint set %d must be a dict' % (position,))
        normalized.append({'strike_deg': _strike(entry.get('strike_deg')), 'dip_deg': _finite(entry.get('dip_deg'), 'joint %d dip_deg' % (position,)), 'spacing_m': _strata_positive(entry.get('spacing_m'), 'joint %d spacing_m' % (position,)), 'phase_m': _finite(entry.get('phase_m', 0.0), 'joint %d phase_m' % (position,))})
        if not -90.0 <= normalized[-1]['dip_deg'] <= 90.0:
            raise ValueError('joint %d dip_deg must satisfy -90 <= dip <= 90' % (position,))
    return {'status': DECLARED, 'source': source, 'anchor_xz_m': [float(anchor[0]), float(anchor[1])], 'sets': normalized}

def joint_distance(x_m, z_m, elevation_m, joints):
    """Distance from each point to the nearest plane of each joint set.

    The normal is built in the (along-dip, up) plane, so a set dipping ``d`` toward
    ``strike + 90`` has normal ``(sin d, cos d)``. The signed normal coordinate is
    wrapped to the nearest multiple of ``spacing_m``, which gives the measured
    distance to the closest joint plane and its plane index. Nothing here claims
    an erosion effect.
    """
    x, z = _points(x_m, z_m)
    elev = _i36_np.broadcast_to(_i36_np.asarray(elevation_m, _i36_np.float64), x.shape)
    if not _i36_np.isfinite(elev).all():
        raise ValueError('elevation_m must be finite')
    declared = normalize_joints(joints)
    if declared['status'] != DECLARED:
        return {'status': PENDING, 'reason': declared['reason'], 'sets': []}
    anchor_x, anchor_z = declared['anchor_xz_m']
    out = []
    for entry in declared['sets']:
        strike = _i36_math.radians(entry['strike_deg'])
        dip = _i36_math.radians(entry['dip_deg'])
        along = (x - anchor_x) * _i36_math.cos(strike) + (z - anchor_z) * _i36_math.sin(strike)
        normal = along * _i36_math.sin(dip) + elev * _i36_math.cos(dip) - entry['phase_m']
        index = _i36_np.rint(normal / entry['spacing_m']).astype(_i36_np.int64)
        signed = normal - index * entry['spacing_m']
        out.append({'strike_deg': entry['strike_deg'], 'dip_deg': entry['dip_deg'], 'spacing_m': entry['spacing_m'], 'signed_distance_m': _i36_np.ascontiguousarray(signed, _i36_np.float64), 'absolute_distance_m': _i36_np.ascontiguousarray(_i36_np.abs(signed), _i36_np.float64), 'joint_index': _i36_np.ascontiguousarray(index, _i36_np.int64)})
    return {'status': DECLARED, 'anchor_xz_m': declared['anchor_xz_m'], 'sets': out}

def declared_stock(stack, *, footprint_m2=None, weatherable_thickness_m=None, density_kg_m3=None):
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
    if stack is None or stack.get('status') != DECLARED:
        return {'status': UNKNOWN_NO_SOURCE, 'reason': 'no declared stratigraphy, so no finite stock exists'}
    if footprint_m2 is None:
        return {'status': STOCK_PENDING, 'reason': 'no footprint declared; a thickness without an area is not a volume'}
    area = _strata_positive(footprint_m2, 'footprint_m2')
    cos_dip = _i36_math.cos(_i36_math.radians(stack['dip_deg']))
    vertical = stack['total_vertical_thickness_m']
    volume = vertical * area
    result = {'status': STOCK_DECLARED, 'footprint_m2': area, 'footprint_kind': 'horizontal_projection', 'vertical_volume_m3': volume, 'volume_kind': 'horizontal_area_x_vertical_thickness', 'total_vertical_thickness_m': vertical, 'total_normal_thickness_m': vertical * cos_dip, 'bedding_area_m2': area / cos_dip, 'thickness_conversion': 'normal = vertical * cos(dip); bedding area = horizontal / cos(dip); both routes give one volume', 'thickness_kind': stack['thickness_kind']}
    normal_route = vertical * cos_dip * (area / cos_dip)
    if not _i36_math.isclose(normal_route, volume, rel_tol=1e-12, abs_tol=0.0):
        raise ValueError('vertical and normal volume routes disagree')
    if density_kg_m3 is not None:
        density = _strata_positive(density_kg_m3, 'density_kg_m3')
        result['mass_kg'] = volume * density
        result['density_kg_m3'] = density
    if weatherable_thickness_m is not None:
        weatherable = _strata_positive(weatherable_thickness_m, 'weatherable_thickness_m')
        result['weatherable_volume_m3'] = min(weatherable, stack['total_vertical_thickness_m']) * area
        result['weatherable_thickness_m'] = weatherable
        result['weatherable_source'] = DECLARED
    else:
        result['weatherable_thickness_m'] = None
        result['weatherable_source'] = PENDING
    return result

def strata_describe():
    return {'schema': STRATA_SCHEMA, 'algorithm': STRATA_ALGORITHM, 'format_version': FORMAT_VERSION, 'max_strata_layers': MAX_STRATA_LAYERS, 'max_points': MAX_POINTS, 'max_grid_cells': MAX_GRID_CELLS, 'max_cell_layer_values': MAX_CELL_LAYER_VALUES, 'max_faults': MAX_FAULTS, 'max_joint_sets': MAX_JOINT_SETS, 'state_names': dict(STATE_NAMES), 'supported_dip_deg': '0 <= dip < 90', 'strike_convention': 'azimuth degrees, north=0, clockwise toward east; right-hand dip direction = strike + 90', 'thickness_kind': 'vertical_thickness_m at the anchor, not normal thickness', 'thickness_conversion': 'normal_thickness = vertical_thickness * cos(dip); with a horizontal footprint the rock volume is horizontal_area * vertical_thickness', 'limitations': list(STRATA_LIMITATIONS)}
MATERIAL_SOURCE_MAX_CELLS = 4096
SPACING_M = 30.0
REQUIRED_FIELDS = {'x_m', 'z_m', 'rock_index', 'class_index', 'bed_hardness', 'bank_hardness', 'erodibility_index', 'mohs_hardness', 'solubility', 'porosity'}

def _anchors(context):
    height = _i38_np.asarray(context['height_m'])
    origin = context['origin_native_xz']
    if height.ndim != 2 or min(height.shape) < 1 or height.size > MATERIAL_SOURCE_MAX_CELLS or (not _i38_np.isfinite(height).all()) or (len(origin) != 2) or any((isinstance(value, (bool, _i38_np.bool_)) or not isinstance(value, (int, _i38_np.integer)) for value in origin)) or isinstance(context['spacing_m'], bool) or (context['spacing_m'] != SPACING_M) or isinstance(context['world_seed'], (bool, _i38_np.bool_)) or (context['world_seed'] != 20261020):
        raise ValueError('material source requires bounded native30m seed20261020 context')
    rows, cols = _i38_np.indices(height.shape)
    return ((origin[0] + cols) * SPACING_M, (origin[1] + rows) * SPACING_M)

def prepare_material_source(context):
    """Sample G2 once at the same native anchors as the existing hardness source.

    Irregular node offsets are network geometry and do not move these anchors.
    The returned shape matches context; original G2 metadata records engineering
    table provenance, rock table identity, purpose-derived seeds and field status.
    """
    x, z = _anchors(context)
    result = properties_at(x, z, world_seed=20261020)
    validate_material_source(result, context)
    return result

def validate_material_source(bundle, context=None):
    """Validate the saved G2 bundle without resampling a field or reading terrain."""
    validate_geology_properties(bundle)
    arrays, metadata = (bundle['arrays'], bundle['metadata'])
    shape = arrays['x_m'].shape
    if len(shape) != 2 or min(shape) < 1 or _i38_math.prod(shape) > MATERIAL_SOURCE_MAX_CELLS or (metadata['world_seed'] != 20261020) or (metadata['form'] != 'point_set') or (metadata['point_count'] != _i38_math.prod(shape)) or (set(arrays) != REQUIRED_FIELDS) or any((value.shape != shape for value in arrays.values())):
        raise ValueError('saved material source must match a bounded native G2 point grid')
    for name in ('solubility', 'porosity', 'bed_hardness'):
        if metadata['fields_status'].get(name) != 'computed':
            raise ValueError('material property spatial lookup status mismatch')
    for name in ('intrinsic_permeability_m2', 'uniaxial_strength_mpa'):
        if metadata['fields_status'].get(name) != 'pending':
            raise ValueError('material helper has no declared extended property source')
    if metadata['fields_status'].get('bedrock_thickness_m') != 'unknown_no_source':
        raise ValueError('material helper has no bedrock thickness or strata source')
    if context is not None:
        x, z = _anchors(context)
        if not _i38_np.array_equal(arrays['x_m'], x) or not _i38_np.array_equal(arrays['z_m'], z):
            raise ValueError('material source does not match environment native anchors')
    return True

def material_mass_inputs(bundle, context=None):
    """Existing G9 initializer inputs only; solubility/hardness are fractions."""
    from terrain_pipeline.common_infra import readonly as _i38_readonly
    validate_material_source(bundle, context)
    return {name: _i38_readonly(bundle['arrays'][name]) for name in ('bed_hardness', 'solubility')}

def bedrock_porosity(bundle, context=None):
    """Read the original G2 rock volume fraction; never assign regolith_porosity."""
    from terrain_pipeline.common_infra import readonly as _i38_readonly
    validate_material_source(bundle, context)
    return _i38_readonly(bundle['arrays']['porosity'])

def query_material_source(bundle, row, col):
    """Read one prepared material point, retaining unknown-property status."""
    validate_material_source(bundle)
    shape = bundle['arrays']['x_m'].shape
    if type(row) is not int or type(col) is not int or min(row, col) < 0 or (row >= shape[0]) or (col >= shape[1]):
        raise ValueError('material query outside prepared native grid')
    arrays, metadata = (bundle['arrays'], bundle['metadata'])
    fields = {name: arrays[name][row, col].item() for name in ('x_m', 'z_m', 'rock_index', 'class_index', 'bed_hardness', 'solubility')}
    fields['bedrock_porosity'] = float(arrays['porosity'][row, col])
    fields['status'] = {name: metadata['fields_status'][name] for name in ('bed_hardness', 'solubility', 'intrinsic_permeability_m2', 'bedrock_thickness_m')}
    fields['status']['bedrock_porosity'] = metadata['fields_status']['porosity']
    fields['units'] = {'x_m': 'm', 'z_m': 'm', 'bed_hardness': '1', 'solubility': '1', 'bedrock_porosity': 'volume fraction', 'intrinsic_permeability_m2': 'm2', 'bedrock_thickness_m': 'm'}
    fields['source'] = _i38_deepcopy({name: metadata[name] for name in ('world_seed', 'rock_table_identity_sha256', 'lithology_subseeds', 'value_status', 'synthetic_lithology', 'measured_lithology')})
    fields['source']['identity_sha256'] = bundle['identity_sha256']
    fields['source']['coordinate_semantics'] = 'native30m anchors; irregular network node offsets not applied'
    return fields
