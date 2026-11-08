"""Consolidated environment_contract implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import replace as _i44_replace
import numpy as _i44_np
import numpy as _i45_np
import numpy as _i46_np
from dataclasses import dataclass as _i47_dataclass
CATEGORY = 'D'

def field(mapping, name, shape, default=0.0, *, nonnegative=True):
    value = _i44_np.asarray(mapping.get(name, default), _i44_np.float64)
    try:
        value = _i44_np.broadcast_to(value, shape).copy()
    except ValueError as error:
        raise ValueError(name + ' must match the context grid') from error
    if not _i44_np.isfinite(value).all() or (nonnegative and _i44_np.any(value < 0.0)):
        raise ValueError(name + ' must be finite' + (' and nonnegative' if nonnegative else ''))
    return value

def prepare_mesh(context, shape, *, edge_order='sorted'):
    """Use saved support directly, retaining the consumer's neighbor ordering."""
    from terrain_pipeline.drainage import IrregularMesh as _i44_IrregularMesh
    from terrain_pipeline.drainage import build_mesh as _i44_build_mesh
    stable = edge_order == 'stable'
    origin = tuple(context['origin_native_xz']) if stable else context['origin_native_xz']
    spacing = float(context['spacing_m']) if stable else context['spacing_m']
    seed = context['world_seed']
    explicit = 'graph_edge_source' in context or (stable and 'graph_edge_target' in context)
    if not explicit:
        return _i44_build_mesh(shape, origin_native_xz=origin, spacing_m=spacing, world_seed=seed)
    if len(shape) != 2 or any((not isinstance(v, (int, _i44_np.integer)) or v < 1 for v in shape)):
        raise ValueError('shape must contain two positive integers')
    if len(origin) != 2 or any((not isinstance(v, (int, _i44_np.integer)) for v in origin)):
        raise ValueError('origin_native_xz must contain two integers')
    if not _i44_np.isfinite(spacing) or spacing <= 0:
        raise ValueError('spacing_m must be finite and positive')
    if not isinstance(seed, (int, _i44_np.integer)):
        raise ValueError('world_seed must be an integer')
    count = int(_i44_np.prod(shape))
    if stable:
        source = _i44_np.asarray(context['graph_edge_source'])
        target = _i44_np.asarray(context['graph_edge_target'])
        if source.ndim != 1 or target.shape != source.shape or source.dtype.kind not in 'iu' or (target.dtype.kind not in 'iu') or _i44_np.any((source < 0) | (source >= count)) or _i44_np.any((target < 0) | (target >= count)):
            raise ValueError('explicit saved graph edge arrays required')
        order = _i44_np.argsort(source, kind='stable')
        x = field(context, 'node_x_m', shape, nonnegative=False).ravel()
        z = field(context, 'node_z_m', shape, nonnegative=False).ravel()
    else:
        source = _i44_np.asarray(context['graph_edge_source'], _i44_np.int64)
        target = _i44_np.asarray(context['graph_edge_target'], _i44_np.int64)
        if source.ndim != 1 or target.shape != source.shape or _i44_np.any(source < 0) or _i44_np.any(target < 0) or _i44_np.any(source >= count) or _i44_np.any(target >= count):
            raise ValueError('invalid explicit graph adjacency')
        order = _i44_np.lexsort((target, source))
        encoded = source * count + target
        reverse_encoded = target * count + source
        if _i44_np.any(source == target) or _i44_np.unique(encoded).size != encoded.size or (not _i44_np.array_equal(_i44_np.sort(encoded), _i44_np.sort(reverse_encoded))):
            raise ValueError('explicit graph requires unique symmetric non-self edges')
        x = array(context['node_x_m'], shape, 'node_x_m', nonnegative=False).ravel()
        z = array(context['node_z_m'], shape, 'node_z_m', nonnegative=False).ravel()
    source, target = (source[order], target[order])
    lengths = _i44_np.hypot(x[source] - x[target], z[source] - z[target])
    if _i44_np.any(lengths <= 0.0):
        raise ValueError('positive saved edge length required' if stable else 'explicit graph requires positive metric edge lengths')
    return _i44_IrregularMesh(tuple(map(int, shape)), tuple(map(int, origin)), float(spacing), int(seed), x, z, _i44_np.r_[0, _i44_np.cumsum(_i44_np.bincount(source, minlength=count))], target, lengths)

def array(value, shape, name, *, nonnegative=True):
    result = _i44_np.asarray(value, _i44_np.float64)
    if result.ndim == 0:
        result = _i44_np.full(shape, float(result))
    if result.shape != shape or not _i44_np.isfinite(result).all():
        raise ValueError(name + ' must be finite and match the terrain shape')
    if nonnegative and _i44_np.any(result < 0.0):
        raise ValueError(name + ' must be nonnegative')
    return result.copy()

def context_arrays(context, dt_s):
    from terrain_pipeline.drainage import receiver_edges_valid as _i44_receiver_edges_valid
    from terrain_pipeline.drainage import segments_clear as _i44_segments_clear
    if not _i44_np.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError('dt_s must be finite positive physical seconds')
    height = _i44_np.asarray(context['height_m'], _i44_np.float64)
    if height.ndim != 2 or not _i44_np.isfinite(height).all():
        raise ValueError('height_m must be a finite 2D array')
    masks = {}
    for name in ('river_mask', 'ocean_mask', 'valid_mask', 'protected_mask'):
        value = _i44_np.asarray(context[name])
        if value.shape != height.shape or value.dtype != bool:
            raise ValueError(name + ' must be a matching boolean array')
        masks[name] = value
    mesh = prepare_mesh(context, height.shape)
    sources = _i44_np.repeat(_i44_np.arange(height.size), _i44_np.diff(mesh.indptr))
    clear = _i44_segments_clear(sources, mesh.indices, masks['valid_mask'])
    if not clear.all():
        sources, targets = (sources[clear], mesh.indices[clear])
        mesh = _i44_replace(mesh, indptr=_i44_np.r_[0, _i44_np.cumsum(_i44_np.bincount(sources, minlength=height.size))], indices=targets, edge_length_m=mesh.edge_length_m[clear])
    receiver = _i44_np.asarray(context['receiver'])
    if receiver.shape != height.shape or receiver.dtype.kind not in 'iu':
        raise ValueError('receiver must be a matching integer array')
    if not _i44_receiver_edges_valid(receiver, mesh):
        raise ValueError('receiver must follow actual irregular graph edges')
    donors = _i44_np.flatnonzero(receiver.ravel() >= 0)
    if donors.size:
        targets = receiver.ravel()[donors]
        if not _i44_segments_clear(donors, targets, masks['valid_mask']).all():
            raise ValueError('receiver crosses invalid support')
    indegree = _i44_np.bincount(receiver.ravel()[donors], minlength=height.size)
    queue = list(_i44_np.flatnonzero(indegree == 0))
    visited = 0
    for node in queue:
        visited += 1
        target = receiver.ravel()[node]
        if target >= 0:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))
    if visited != height.size:
        raise ValueError('receiver graph must be acyclic')
    return (height, masks, mesh, receiver.ravel())

def frame(context, dt_s):
    height = _i45_np.asarray(context['height_m'], _i45_np.float64)
    spacing = float(context['spacing_m'])
    if height.ndim != 2 or height.size > 1000000 or (not _i45_np.isfinite(height).all()) or (not _i45_np.isfinite(spacing)) or (spacing <= 0.0) or (not _i45_np.isfinite(dt_s)) or (dt_s < 0.0):
        raise ValueError('bounded finite grid, positive spacing and nonnegative physical dt_s required')
    masks = {}
    for name in ('valid_mask', 'protected_mask', 'ocean_mask', 'river_mask'):
        value = _i45_np.asarray(context[name])
        if value.dtype != bool or value.shape != height.shape:
            raise ValueError(name + ' must be a same-shape boolean mask')
        masks[name] = value
    if type(context['world_seed']) is not int or context['world_seed'] < 0:
        raise ValueError('explicit nonnegative world_seed required')
    origin = _i45_np.asarray(context['origin_native_xz'])
    if origin.shape != (2,) or not _i45_np.issubdtype(origin.dtype, _i45_np.integer):
        raise ValueError('integer native origin required')
    receiver = _i45_np.asarray(context['receiver'])
    if receiver.shape != height.shape or not _i45_np.issubdtype(receiver.dtype, _i45_np.integer) or _i45_np.any((receiver < -1) | (receiver >= height.size)):
        raise ValueError('same-shape receiver indices required')
    return (height.shape, spacing ** 2, masks)

def stocks(state, names, shape, *, signed=()):
    if not isinstance(state, dict) or not set(names).issubset(state):
        raise ValueError('complete explicit state inventory required')
    return {name: field(state, name, shape, nonnegative=name not in signed) for name in names}

def metadata(algorithm, context, dt_s, limitations, parameters):
    return {'algorithm': algorithm, 'world_seed': context['world_seed'], 'origin_native_xz': list(map(int, context['origin_native_xz'])), 'spacing_m': float(context['spacing_m']), 'dt_s': float(dt_s), 'parameters': parameters, 'forcing_semantics': 'explicit_declared_scenario', 'limitations': limitations, 'default_world_registered': False}

def grid(context, dt_s):
    height = _i46_np.asarray(context['height_m'], dtype=float)
    spacing = float(context['spacing_m'])
    if height.ndim != 2 or height.size == 0 or height.size > 262144 or (not _i46_np.isfinite(height).all()) or (not _i46_np.isfinite(spacing)) or (spacing <= 0) or (not _i46_np.isfinite(dt_s)) or (dt_s <= 0):
        raise ValueError('finite bounded height grid, positive spacing and physical seconds required')
    valid = bounded_field(context.get('valid_mask', True), height.shape, 'valid_mask').astype(bool)
    protected = bounded_field(context.get('protected_mask', False), height.shape, 'protected_mask').astype(bool)
    return (height, spacing, valid & ~protected)

def bounded_field(value, shape, name, minimum=None, maximum=None):
    array = _i46_np.broadcast_to(_i46_np.asarray(value, dtype=float), shape).copy()
    if not _i46_np.isfinite(array).all() or (minimum is not None and _i46_np.any(array < minimum)) or (maximum is not None and _i46_np.any(array > maximum)):
        raise ValueError(f'invalid {name}')
    return array

def positive_parameters(parameters, defaults):
    values = dict(defaults)
    if parameters:
        if set(parameters) - set(values):
            raise ValueError('unknown process parameter')
        values.update(parameters)
    if any((not _i46_np.isfinite(value) or value <= 0 for value in values.values())):
        raise ValueError('process parameters must be finite and positive')
    return values
REGISTRY_ID = 'environment-defaults-v1'

@_i47_dataclass(frozen=True)
class Default:
    value: float
    unit: str
    source: str
    status: str = 'declared/uncalibrated'
    pinned: bool = False
    note: str = ''

def _d(value, unit, source, pinned=False, note=''):
    return Default(value, unit, source, 'declared/uncalibrated', pinned, note)
DEFAULTS = {'runoff.infiltration_capacity_mm_h': _d(15.0, 'mm/h', 'runoff.py:RunoffParameters', True), 'runoff.soil_capacity_mm': _d(150.0, 'mm', 'runoff.py:RunoffParameters', True, 'differs from seasonal.soil_capacity_mm (120); both kept'), 'runoff.potential_et_mm_h': _d(0.15, 'mm/h', 'runoff.py:RunoffParameters', True), 'runoff.percolation_mm_h': _d(1.0, 'mm/h', 'runoff.py:RunoffParameters', True), 'runoff.fast_tau_s': _d(3600.0, 's', 'runoff.py:RunoffParameters', True), 'runoff.slow_tau_s': _d(259200.0, 's', 'runoff.py:RunoffParameters', True), 'runoff.initial_soil_mm': _d(30.0, 'mm', 'runoff.py:RunoffParameters', True), 'seasonal.soil_capacity_mm': _d(120.0, 'mm', 'runoff.py:SeasonalConfig', True), 'seasonal.soil_drainage_days': _d(45.0, 'day', 'runoff.py:SeasonalConfig', True), 'seasonal.climate_noise_scale_m': _d(60000.0, 'm', 'runoff.py:SeasonalConfig', True), 'pet.base_mm_per_day': _d(0.5, 'mm/day', 'runoff.py:SeasonalConfig; soil_water.py:PetEtParameters', True, 'same value in both files; metric_pet_et is not pinned'), 'pet.temperature_mm_per_day_c': _d(0.12, 'mm/day/degC', 'runoff.py:SeasonalConfig; soil_water.py:PetEtParameters', True), 'pet.freezing_threshold_c': _d(0.0, 'degC', 'soil_water.py:PetEtParameters'), 'climate.lapse_rate_c_per_m': _d(-0.0065, 'degC/m', 'climate_forcing.py:NoiseClimateParameters'), 'radiation.solar_constant_w_m2': _d(1000.0, 'W/m2', 'environment_processes.py:step', note='effective clear-sky value, not the 1361 W/m2 TOA constant'), 'radiation.atmospheric_transmission': _d(0.7, '1', 'environment_processes.py:step'), 'radiation.evaporation_energy_fraction': _d(0.3, '1', 'environment_processes.py:step'), 'radiation.albedo': _d(0.2, '1', 'environment_processes.py:step (forcing default)'), 'radiation.day_seconds': _d(86400.0, 's', 'environment_processes.py:step'), 'radiation.year_days': _d(365.0, 'day', 'environment_processes.py:step'), 'frozen.latent_heat_j_m3': _d(334000000.0, 'J/m3', 'environment_processes.py:LATENT_J_M3'), 'frozen.soil_heat_capacity_j_m2_k': _d(2000000.0, 'J/m2/K', 'environment_processes.py:step'), 'frozen.air_exchange_w_m2_k': _d(5.0, 'W/m2/K', 'environment_processes.py:step'), 'frozen.snow_insulation_per_m_swe': _d(50.0, '1/m', 'environment_processes.py:step'), 'frozen.thermal_diffusivity_m2_s': _d(5e-07, 'm2/s', 'environment_processes.py:step'), 'frozen.soil_depth_m': _d(2.0, 'm', 'environment_processes.py:step'), 'regolith.porosity': _d(0.35, '1', 'environment_processes.py:initial_state'), 'coastal.bed_porosity': _d(0.35, '1', 'environment_processes.py:PARAMETERS'), 'land_cover.available_water_fraction': _d(0.15, '1', 'soil_water.py:138'), 'aeolian.threshold_wind_m_s': _d(5.0, 'm/s', 'environment_processes.py:step'), 'aeolian.entrainment_rate_s_m': _d(1e-05, 's/m', 'environment_processes.py:step'), 'aeolian.settling_time_s': _d(600.0, 's', 'environment_processes.py:step'), 'aeolian.solid_fraction': _d(0.6, '1', 'environment_processes.py:step'), 'volcanism.lava_heat_j_m3': _d(2000000000.0, 'J/m3', 'environment_processes.py:step'), 'volcanism.cooling_time_s': _d(3600.0, 's', 'environment_processes.py:step'), 'volcanism.lava_speed_m_s': _d(0.05, 'm/s', 'environment_processes.py:step'), 'volcanism.ash_settling_time_s': _d(1800.0, 's', 'environment_processes.py:step'), 'volcanism.ash_solid_fraction': _d(0.5, '1', 'environment_processes.py:step'), 'succession.bare_manning_n': _d(0.025, 's/m^(1/3)', 'environment_processes.py:PARAMETERS'), 'succession.vegetated_manning_increment': _d(0.09, 's/m^(1/3)', 'environment_processes.py:PARAMETERS'), 'mass.bulk_density_kg_m3': _d(1800.0, 'kg/m3', 'environment_processes.py:step'), 'mass.repose_angle_deg': _d(34.0, 'deg', 'environment_processes.py:step (forcing default)'), 'mass.gravity_m_s2': _d(9.80665, 'm/s2', 'environment_processes.py:step'), 'groundwater.specific_yield': _d(0.2, '1', 'environment_processes.py:step (forcing default)'), 'groundwater.aquifer_base_depth_m': _d(10.0, 'm', 'environment_processes.py:step (height - 10)')}
PROCESS_PARAMETER_SOURCES = {'coastal_exchange': 'environment_processes.COASTAL_EXCHANGE_PARAMETERS', 'habitat': 'environment_processes.HABITAT_PARAMETERS', 'soil_chemistry': 'environment_processes.SOIL_CHEMISTRY_PARAMETERS', 'succession': 'environment_processes.SUCCESSION_PARAMETERS'}

def get(name):
    """Return the registered value (a plain float)."""
    return DEFAULTS[name].value

def group(prefix):
    """Return ``{short_name: value}`` for all entries under ``prefix.``."""
    start = prefix + '.'
    return {k[len(start):]: v.value for k, v in DEFAULTS.items() if k.startswith(start)}

def describe():
    return {name: {'value': e.value, 'unit': e.unit, 'source': e.source, 'status': e.status, 'pinned': e.pinned, 'note': e.note} for name, e in sorted(DEFAULTS.items())}
