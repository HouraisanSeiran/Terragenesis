"""Consolidated environment_processes implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import dataclass as _i0_dataclass
from dataclasses import field as _i0_dc_field
from importlib import import_module as _i0_import_module
import numpy as _i1_np
from dataclasses import asdict as _i2_asdict
from dataclasses import dataclass as _i2_dataclass
from dataclasses import field as _i2_field
import math as _i2_math
import numpy as _i2_np
import math as _i3_math
import numpy as _i3_np
import numpy as _i4_np
import numpy as _i5_np
from scipy.ndimage import binary_propagation as _i5_binary_propagation
import numpy as _i6_np
import numpy as _i7_np
import heapq as _i8_heapq
import numpy as _i8_np
from copy import deepcopy as _i9_deepcopy
import numpy as _i9_np
import hashlib as _i10_hashlib
import numpy as _i10_np
import numpy as _i11_np
import numpy as _i12_np
import numpy as _i13_np
import numpy as _i14_np
CATEGORY = 'D'
PROTOCOL_ID = 'environment-process-protocol-v1'
PROCESSES = {'radiation': ('environment_processes', 'radiation_initialize', 'radiation_step', True), 'frozen_ground': ('environment_processes', 'frozen_ground_initialize', 'frozen_ground_step', True), 'volcanism': ('environment_processes', 'volcanism_initialize', 'volcanism_step', True), 'aeolian': ('environment_processes', 'aeolian_initialize', 'aeolian_step', True), 'groundwater': ('environment_processes', 'groundwater_initial_state', 'groundwater_step', False), 'mass': ('environment_processes', 'mass_initial_state', 'mass_step', False), 'network_transition': ('environment_processes', 'network_transition_initial_state', 'network_transition_step', False), 'coastal_exchange': ('environment_processes', 'initialize_coastal_exchange', 'advance_coastal_exchange', False), 'habitat': ('environment_processes', 'initialize_habitat', 'advance_habitat', False), 'soil_chemistry': ('environment_processes', 'initialize_soil_chemistry', 'advance_soil_chemistry', False), 'succession': ('environment_processes', 'initialize_succession', 'advance_succession', False)}
_STOCKS_BEFORE = {'initial_solid_m3', 'water_before_m3', 'initial_population', 'initial_carbon_kg'}
_STOCKS_AFTER = {'final_solid_m3', 'water_after_m3', 'final_population', 'final_carbon_kg', 'current_total_solid_m3'}
_OUT_WORDS = ('export', 'pumping', 'drainage', 'evaporation', 'leached', 'respired', 'deaths', 'reflected', 'fire_atmosphere', 'cooling', 'snow_latent', 'uptake', 'soil_water_export', 'soil_salt_export')
_UNITS = (('_m3', 'm3'), ('_kg', 'kg'), ('_j', 'J'), ('_individuals', 'individuals'), ('_population', 'individuals'), ('_s', 's'))

def _unit(key):
    for suffix, unit in _UNITS:
        if key.endswith(suffix):
            return unit
    if key in ('initial_population', 'final_population'):
        return 'individuals'
    return '1'

@_i0_dataclass(frozen=True)
class State:
    process: str
    arrays: dict
    params: dict = _i0_dc_field(default_factory=dict)
    last_fluxes: dict = _i0_dc_field(default_factory=dict)
    last_metadata: dict = _i0_dc_field(default_factory=dict)

@_i0_dataclass(frozen=True)
class Ledger:
    process: str
    stocks_before: dict
    stocks_after: dict
    fluxes_in: dict
    fluxes_out: dict
    residual: dict
    units: dict
    derived: tuple = ()

    def max_abs_residual(self):
        return max((abs(v) for v in self.residual.values()), default=0.0)

def _classify(process, legacy):
    before, after, fin, fout, residual, units, derived = ({}, {}, {}, {}, {}, {}, [])
    data = dict(legacy)
    if process == 'radiation' and (not any((k.endswith('_residual_j') for k in data))):
        data['energy_residual_j'] = data['incident_j'] - data['reflected_j'] - data['absorbed_j']
        derived.append('energy_residual_j')
    for key, value in data.items():
        value = float(value)
        units[key] = _unit(key)
        if 'residual' in key:
            residual[key] = value
        elif key in _STOCKS_BEFORE:
            before[key] = value
        elif key in _STOCKS_AFTER:
            after[key] = value
        elif any((word in key for word in _OUT_WORDS)):
            fout[key] = value
        else:
            fin[key] = value
    return Ledger(process, before, after, fin, fout, residual, units, tuple(derived))

def _entry(process):
    if process not in PROCESSES:
        raise ValueError('unknown environment process ' + repr(process))
    initializer, stepper, takes_parameters = _PROCESS_FUNCTIONS[process]
    return (initializer, stepper, takes_parameters)

def init(process, ctx, params=None, forcing=None):
    """Create a State. ``forcing`` is accepted for protocol symmetry; no legacy initializer uses it."""
    initializer, _, _ = _entry(process)
    params = params or {}
    unknown = set(params) - {'init', 'step'}
    if unknown:
        raise ValueError("params may only contain 'init' and 'step'")
    arrays = initializer(ctx, **params.get('init', {}))
    return State(process, arrays, {'init': dict(params.get('init', {})), 'step': params.get('step')})

def step(state, ctx, forcing, dt_s):
    _, stepper, takes_parameters = _entry(state.process)
    if takes_parameters:
        result = stepper(state.arrays, forcing, ctx, dt_s, state.params.get('step'))
    else:
        if state.params.get('step'):
            raise ValueError(state.process + ' takes no step parameters')
        result = stepper(state.arrays, forcing, ctx, dt_s)
    new = State(state.process, result['state'], state.params, result.get('fluxes', {}), result.get('metadata', {}))
    return (new, _classify(state.process, result['ledger']))

def inventory_totals(product):
    s, packets = (product['states'], product['pending_packets'])
    area = float(product['context']['spacing_m']) ** 2

    def total(module, names):
        return sum((float(_i1_np.asarray(s[module][name]).sum()) for name in names))
    result = {'water_m3': total('groundwater', ('groundwater_water_m3', 'surface_water_m3')) + total('soil_chemistry', ('water_m3',)) + total('coastal_exchange', ('water_m3',)) + area * total('frozen_ground', ('liquid_water_m', 'ground_ice_m', 'snow_swe_m')) + float(packets['soil_water_m3'].sum()), 'solid_m3': total('mass', ('bedrock_solid_m3', 'regolith_solid_m3', 'soil_solid_m3', 'hillslope_deposit_solid_m3', 'river_sediment_solid_m3')) + total('aeolian', ('loose_solid_m3', 'airborne_solid_m3')) + total('volcanism', ('mobile_lava_m3', 'airborne_ash_m3', 'deposited_lava_m3', 'deposited_ash_m3')) + total('coastal_exchange', ('bed_solid_m3',)), 'carbon_kg': total('soil_chemistry', ('organic_carbon_kg',)) + total('succession', ('biomass_carbon_kg', 'dead_carbon_kg', 'char_carbon_kg')) + float(packets['litter_carbon_kg'].sum()), 'salt_kg': total('soil_chemistry', ('salt_dissolved_kg', 'salt_solid_kg')) + total('coastal_exchange', ('salt_kg',)) + float(packets['soil_salt_kg'].sum() + packets['subsurface_salt_kg'].sum()), 'nutrient_kg': total('soil_chemistry', ('nutrient_kg', 'organic_nutrient_kg')) + total('succession', ('plant_nutrient_kg',)) + float(packets['plant_nutrient_return_kg'].sum() + packets['subsurface_nutrient_kg'].sum())}
    if 'seasonal' in product:
        seasonal = product['seasonal']
        result['water_m3'] += area / 1000.0 * sum((float(seasonal[key].sum()) for key in ('snow_swe_mm', 'fast_mm', 'slow_mm')))
        result['water_m3'] += (float(seasonal['climate_state']['arrays']['vapour_kg'].sum()) + float(seasonal['pending_et_kg'].sum())) / 1000.0
    return result
GLACIER_SCHEMA = 'bounded-glacier-v1'
LOGICAL_VERSION = 'bounded-ice-mass-flux-v1'
GLACIER_ALGORITHM = 'sia-creep-flowline-v1'
GRAVITY_M_S2 = 9.80665
WATER_DENSITY_KG_M3 = 1000.0
CELL_AREA_M2 = 900.0
NATIVE_SPACING_M = 30.0
MAX_CELLS = 9
MIN_CELLS = 3
MAX_INTERVALS = 512
MAX_SUBSTEPS = 64
CFL = 0.25
MAX_THICKNESS_M = 500.0
FLOW_MODELS = ('shallow_ice', 'none')
MOTION_FLOWING = 'flowing'
MOTION_STATIONARY = 'stationary_below_threshold'
MOTION_STATIC = 'static_flow_model_none'
EROSION_PROXY_DECLARED = 'erosion_proxy_declared'
EROSION_NOT_AVAILABLE = 'not_available'
CREEP_PARAMETER_UNIT = 'Pa^-n s^-1'
CREEP_PARAMETER_SEMANTICS = 'dimensional Glen creep parameter of the flow law; it is NOT a dimensionless lumped coefficient. A caller that wants a lumped coefficient must carry its own dimensions instead'
EROSION_PROXY_SEMANTICS = 'declared proxy: erosion volume = coefficient * cumulative |face ice flux|. That is an explicit upper bound, not a conversion of rock into ice or ice into rock; the only stock that is actually decremented is the supplied finite bedrock volume'
LIQUID_TO_LAND = 'declared_land_port'
LIQUID_UNRESOLVED = 'liquid_export_unresolved'
GLACIER_EXISTENCE_POLICY = 'not_decided_here: a multi-year net balance (positive or negative) is not a glacier-existence criterion; this bounded store reports mass and flux only'
FORMULA_SOURCE = 'shallow ice approximation, deformation (creep) only, Glen flow law with exponent n; the flux form q = W (2A/(n+2)) (rho g)^n H^(n+2) |ds/dx|^(n-1) (-ds/dx) is the standard 1-D SIA discretisation on cell centres with mean face thickness and central surface slope. No basal sliding law is implemented, so no velocity here is a sliding velocity.'
LIMITATIONS = ('one-dimensional fixed-width flowline of 3..9 native 30 m cells; not a glacier inventory', 'deformation-only SIA: no basal sliding, no hydrology, no thermodynamics, no calving', 'the ice surface is recomputed as bed + thickness every step; there is no separate surface field that could disagree with the ice', 'accumulation and ablation inputs are water-equivalent depths; ice volume is derived through both densities, so ice volume and water volume are never numerically equal', 'the erosion proxy is declared and requires an explicit finite bedrock stock; without one the answer is not_available, never an unbounded bed', 'derived bed_delta_m is returned only; no TD bed is written and no bed feedback is claimed', 'no real-world glacier is predicted and the multi-year net balance is not a glacier-existence criterion', 'the 1 m minimum spacing unit is a bound, not a claimed 1 m accuracy')

def _finite(value, name, *, minimum=None, maximum=None, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, _i2_np.integer, _i2_np.floating)):
        raise ValueError('%s must be numeric' % name)
    number = float(value)
    if not _i2_math.isfinite(number):
        raise ValueError('%s must be finite' % name)
    if positive and number <= 0.0:
        raise ValueError('%s must be positive' % name)
    if nonnegative and number < 0.0:
        raise ValueError('%s must be nonnegative' % name)
    if minimum is not None and number < minimum:
        raise ValueError('%s must be >= %r' % (name, minimum))
    if maximum is not None and number > maximum:
        raise ValueError('%s must be <= %r' % (name, maximum))
    return number

@_i2_dataclass(frozen=True)
class GlacierParameters:
    """Declared engineering parameters; uncalibrated, and every value enters the identity."""
    ice_density_kg_m3: float = 917.0
    creep_parameter_pa_n_s: float = 2.4e-24
    glen_exponent: int = 3
    min_flow_thickness_m: float = 0.0
    max_thickness_m: float = MAX_THICKNESS_M
    erosion_proxy_coefficient: float = 0.001

    def __post_init__(self):
        _finite(self.ice_density_kg_m3, 'ice_density_kg_m3', positive=True)
        _finite(self.creep_parameter_pa_n_s, 'creep_parameter_pa_n_s', positive=True)
        if self.glen_exponent not in (1, 2, 3, 4, 5):
            raise ValueError('glen_exponent must be a small positive integer')
        _finite(self.min_flow_thickness_m, 'min_flow_thickness_m', nonnegative=True)
        _finite(self.max_thickness_m, 'max_thickness_m', positive=True)
        _finite(self.erosion_proxy_coefficient, 'erosion_proxy_coefficient', nonnegative=True)

    @property
    def densification(self):
        """Ice volume per unit water-equivalent depth, per unit area."""
        return WATER_DENSITY_KG_M3 / self.ice_density_kg_m3

    def identity(self):
        payload = _i2_asdict(self)
        payload['formula_source'] = FORMULA_SOURCE
        payload['densification'] = self.densification
        payload['creep_parameter_unit'] = CREEP_PARAMETER_UNIT
        payload['creep_parameter_semantics'] = CREEP_PARAMETER_SEMANTICS
        payload['glacier_existence_criterion'] = GLACIER_EXISTENCE_POLICY
        return payload

def _edges(time_edges_s):
    edges = _i2_np.asarray(time_edges_s, _i2_np.float64)
    if edges.ndim != 1 or edges.size < 2 or edges.size - 1 > MAX_INTERVALS:
        raise ValueError('time_edges_s must be 1D with 1..%d intervals' % MAX_INTERVALS)
    if not _i2_np.isfinite(edges).all() or _i2_np.any(_i2_np.diff(edges) <= 0.0):
        raise ValueError('time_edges_s must be finite and strictly increasing')
    return edges

def _grid(x_m, width_m):
    x = _i2_np.asarray(x_m, _i2_np.float64).reshape(-1)
    if x.size < MIN_CELLS or x.size > MAX_CELLS:
        raise ValueError('this bounded model handles %d..%d cells, got %d' % (MIN_CELLS, MAX_CELLS, x.size))
    if not _i2_np.isfinite(x).all() or _i2_np.any(_i2_np.diff(x) <= 0.0):
        raise ValueError('x_m must be finite and strictly increasing along the flowline')
    dx = _i2_np.diff(x)
    if not _i2_np.allclose(dx, dx[0], rtol=0.0, atol=1e-09):
        raise ValueError('a uniform cell spacing is required; got %s' % list(dx))
    width = _finite(width_m, 'width_m', positive=True)
    return (x, float(dx[0]), width)

def _per_cell(value, name, cells, *, nonnegative=True):
    array = _i2_np.asarray(value, _i2_np.float64)
    if array.shape != (cells,):
        raise ValueError('%s must be one value per cell' % name)
    if not _i2_np.isfinite(array).all():
        raise ValueError('%s must be finite' % name)
    if nonnegative and _i2_np.any(array < 0.0):
        raise ValueError('%s must be nonnegative' % name)
    return array

def _per_interval(value, name, intervals, cells, *, nonnegative=True):
    array = _i2_np.asarray(value, _i2_np.float64)
    if array.shape != (intervals, cells):
        raise ValueError('%s must be [intervals, cells] = [%d, %d], got %s' % (name, intervals, cells, list(array.shape)))
    if not _i2_np.isfinite(array).all():
        raise ValueError('%s must be finite' % name)
    if nonnegative and _i2_np.any(array < 0.0):
        raise ValueError('%s must be nonnegative' % name)
    return array

def _face_flux(*, surface_m, thickness_m, dx_m, width_m, parameters):
    """SIA volume flux per face, in m^3 s^-1, positive towards increasing ``x``.

    Closed ends: the two outermost faces carry no flux, so this small grid is a bounded domain and
    nothing leaves it as ice. Liquid leaves only through the declared liquid port.
    """
    cells = thickness_m.size
    flux = _i2_np.zeros(cells + 1, _i2_np.float64)
    diffusivity = _i2_np.zeros(cells + 1, _i2_np.float64)
    if cells < 2:
        return (flux, diffusivity)
    n = parameters.glen_exponent
    prefactor = 2.0 * parameters.creep_parameter_pa_n_s / (n + 2.0) * (parameters.ice_density_kg_m3 * GRAVITY_M_S2) ** n
    slope = _i2_np.diff(surface_m) / dx_m
    mean_thickness = 0.5 * (thickness_m[:-1] + thickness_m[1:])
    positive = mean_thickness > 0.0
    magnitude = _i2_np.zeros_like(slope)
    if positive.any():
        magnitude[positive] = prefactor * mean_thickness[positive] ** (n + 2) * _i2_np.abs(slope[positive]) ** (n - 1) * -slope[positive]
    flux[1:-1] = width_m * magnitude
    diffusivity[1:-1] = prefactor * mean_thickness ** (n + 2) * _i2_np.abs(slope) ** (n - 1)
    return (flux, diffusivity)

def _dt_limit(diffusivity, dx_m, cfl):
    peak = float(_i2_np.max(diffusivity)) if diffusivity.size else 0.0
    if peak <= 0.0:
        return _i2_math.inf
    return cfl * dx_m * dx_m / peak

def advance_glacier(*, thickness_start_m, bed_m, accumulation_mm, ablation_mm, time_edges_s, x_m, width_m=NATIVE_SPACING_M, bedrock_erodible_m3=None, land_port_mask=None, flow_model='shallow_ice', parameters=None):
    """Advance the bounded ice body over declared intervals, with closed lateral ends.

    ``accumulation_mm`` and ``ablation_mm`` are **water-equivalent depths per interval**. Ice
    volume is derived through ``water_mass = mm/1000 * area * rho_water`` then
    ``ice_volume = water_mass / rho_ice``, so ice volume and water volume are never equal.

    ``ablation_mm`` that melts ice produces liquid water back at water density. Where a cell has a
    declared land port (``land_port_mask``) that water is reported in ``melt_to_land_mm``;
    everywhere else it is reported in ``liquid_export_unresolved_mm``. Ice is never removed
    without the water being accounted for somewhere.

    ``bedrock_erodible_m3`` is an explicit **finite** bedrock stock per cell. Without it the
    erosion answer is ``not_available`` and no rock is removed.
    """
    from terrain_pipeline.artifacts.contracts import array_hash as _i2_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i2_digest
    edges = _edges(time_edges_s)
    intervals = int(edges.size - 1)
    parameters = GlacierParameters() if parameters is None else parameters
    if not isinstance(parameters, GlacierParameters):
        raise ValueError('parameters must be GlacierParameters')
    if flow_model not in FLOW_MODELS:
        raise ValueError('flow_model must be one of %s' % (FLOW_MODELS,))
    x, dx, width = _grid(x_m, width_m)
    cells = x.size
    thickness = _per_cell(thickness_start_m, 'thickness_start_m', cells)
    bed = _per_cell(bed_m, 'bed_m', cells, nonnegative=False)
    if _i2_np.any(thickness > parameters.max_thickness_m):
        raise ValueError('the initial thickness exceeds the declared ceiling %r m' % parameters.max_thickness_m)
    accumulation = _per_interval(accumulation_mm, 'accumulation_mm', intervals, cells)
    ablation = _per_interval(ablation_mm, 'ablation_mm', intervals, cells)
    if bedrock_erodible_m3 is None:
        rock_stock = None
        erosion_status = EROSION_NOT_AVAILABLE
    else:
        rock_stock = _per_cell(bedrock_erodible_m3, 'bedrock_erodible_m3', cells)
        erosion_status = EROSION_PROXY_DECLARED
    if land_port_mask is None:
        land_port = _i2_np.zeros(cells, _i2_np.bool_)
    else:
        land_port = _i2_np.asarray(land_port_mask, _i2_np.bool_)
        if land_port.shape != (cells,):
            raise ValueError('land_port_mask must be one boolean per cell')
    area = CELL_AREA_M2
    densification = parameters.densification
    n = parameters.glen_exponent
    thickness_edge = _i2_np.zeros((intervals + 1, cells), _i2_np.float64)
    surface_edge = _i2_np.zeros((intervals + 1, cells), _i2_np.float64)
    volume_edge = _i2_np.zeros((intervals + 1, cells), _i2_np.float64)
    thickness_edge[0] = thickness
    surface_edge[0] = bed + thickness
    volume_edge[0] = thickness * area
    accumulation_ice = _i2_np.zeros((intervals, cells), _i2_np.float64)
    ablation_ice = _i2_np.zeros((intervals, cells), _i2_np.float64)
    melt_liquid_mm = _i2_np.zeros((intervals, cells), _i2_np.float64)
    melt_to_land_mm = _i2_np.zeros((intervals, cells), _i2_np.float64)
    unresolved_liquid_mm = _i2_np.zeros((intervals, cells), _i2_np.float64)
    face_flux_cube = _i2_np.zeros((intervals, cells + 1), _i2_np.float64)
    face_flux_mean = _i2_np.zeros((intervals, cells + 1), _i2_np.float64)
    erosion_rock = _i2_np.zeros((intervals, cells), _i2_np.float64)
    solid_export = _i2_np.zeros((intervals, cells), _i2_np.float64)
    motion = _i2_np.full((intervals, cells), MOTION_STATIC, dtype='<U32')
    substeps = _i2_np.zeros(intervals, _i2_np.int64)
    dt_limit_edge = _i2_np.zeros(intervals, _i2_np.float64)
    limited_cells = _i2_np.zeros((intervals, cells), _i2_np.bool_)
    rock_used = _i2_np.zeros(cells, _i2_np.float64)
    for index in range(intervals):
        span = float(edges[index + 1] - edges[index])
        acc_ice = accumulation[index] / 1000.0 * area * densification
        abl_ice = _i2_np.minimum(ablation[index] / 1000.0 * area * densification, thickness * area)
        thickness = thickness + (acc_ice - abl_ice) / area
        if _i2_np.any(thickness < -1e-12):
            raise RuntimeError('ablation drove the ice thickness negative in interval %d' % index)
        thickness = _i2_np.maximum(thickness, 0.0)
        if _i2_np.any(thickness > parameters.max_thickness_m):
            raise ValueError('interval %d would exceed the declared thickness ceiling %r m' % (index, parameters.max_thickness_m))
        accumulation_ice[index] = acc_ice
        ablation_ice[index] = abl_ice
        produced_mm = abl_ice / (area * densification) * 1000.0
        melt_liquid_mm[index] = produced_mm
        melt_to_land_mm[index] = _i2_np.where(land_port, produced_mm, 0.0)
        unresolved_liquid_mm[index] = _i2_np.where(land_port, 0.0, produced_mm)
        if flow_model == 'shallow_ice':
            surface = bed + thickness
            flux, diffusivity = _face_flux(surface_m=surface, thickness_m=thickness, dx_m=dx, width_m=width, parameters=parameters)
            limit = _dt_limit(diffusivity, dx, CFL)
            dt_limit_edge[index] = limit
            if _i2_math.isfinite(limit) and span > MAX_SUBSTEPS * limit:
                raise ValueError("interval %d spans %r s but the explicit shallow-ice stability limit is %r s per sub-step, so at most %d sub-steps cover %r s. Refine the interval edges with the caller's own fixed split; this module does not take an unstable step and does not clip the store to fake stability." % (index, span, limit, MAX_SUBSTEPS, MAX_SUBSTEPS * limit))
            count = 1 if not _i2_math.isfinite(limit) else int(_i2_math.ceil(span / limit))
            count = max(1, min(count, MAX_SUBSTEPS))
            sub_dt = span / count
            substeps[index] = count
            flux_sum = _i2_np.zeros_like(flux)
            for _ in range(count):
                surface = bed + thickness
                flux, diffusivity = _face_flux(surface_m=surface, thickness_m=thickness, dx_m=dx, width_m=width, parameters=parameters)
                detail = float(_i2_np.max(diffusivity)) if diffusivity.size else 0.0
                if detail > 0.0 and sub_dt > CFL * dx * dx / detail:
                    raise RuntimeError('the sub-step violated the declared CFL bound')
                volume = thickness * area
                out_left = _i2_np.zeros(cells, _i2_np.float64)
                out_right = _i2_np.zeros(cells, _i2_np.float64)
                positive = _i2_np.maximum(flux, 0.0) * sub_dt
                negative = _i2_np.maximum(-flux, 0.0) * sub_dt
                out_left[:-1] = positive[1:-1]
                out_right[1:] = negative[1:-1]
                requested = out_left + out_right
                over = requested > volume
                if over.any():
                    scale = _i2_np.ones(cells, _i2_np.float64)
                    scale[over] = volume[over] / requested[over]
                    positive[1:-1] *= scale[:-1]
                    negative[1:-1] *= scale[1:]
                    limited_cells[index] = limited_cells[index] | over
                change = _i2_np.zeros(cells, _i2_np.float64)
                change[:-1] -= positive[1:-1]
                change[1:] += positive[1:-1]
                change[1:] -= negative[1:-1]
                change[:-1] += negative[1:-1]
                thickness = thickness + change / area
                if _i2_np.any(thickness < -1e-12):
                    raise RuntimeError('the flow step drove the thickness negative')
                thickness = _i2_np.maximum(thickness, 0.0)
                flux_sum += flux
            face_flux_mean[index] = flux_sum / count
            face_flux_cube[index] = _i2_np.abs(flux_sum / count) * span
            motion[index] = _i2_np.where(thickness >= parameters.min_flow_thickness_m, MOTION_FLOWING, MOTION_STATIONARY)
            if parameters.min_flow_thickness_m > 0.0:
                thin = thickness < parameters.min_flow_thickness_m
                if thin.any():
                    motion[index][thin] = MOTION_STATIONARY
        else:
            face_flux_mean[index] = 0.0
            substeps[index] = 0
            motion[index] = MOTION_STATIC
        if rock_stock is not None:
            if flow_model == 'shallow_ice':
                proxy = parameters.erosion_proxy_coefficient * face_flux_cube[index].sum()
            else:
                proxy = _i2_np.zeros(cells, _i2_np.float64)
            remaining_rock = _i2_np.maximum(rock_stock - rock_used, 0.0)
            removed = _i2_np.minimum(proxy, _i2_np.maximum(remaining_rock, 0.0))
            erosion_rock[index] = removed
            rock_used += removed
            solid_export[index] = removed
        thickness_edge[index + 1] = thickness
        surface_edge[index + 1] = bed + thickness
        volume_edge[index + 1] = thickness * area
    volume = thickness_edge * area
    flux_divergence = _i2_np.zeros((intervals, cells), _i2_np.float64)
    for index in range(intervals):
        flux = face_flux_mean[index] * (edges[index + 1] - edges[index])
        flux_divergence[index, :-1] -= flux[1:-1]
        flux_divergence[index, 1:] += flux[1:-1]
    ice_residual = volume[-1] - volume[0] - accumulation_ice.sum(axis=0) + ablation_ice.sum(axis=0) - flux_divergence.sum(axis=0)
    liquid_total = melt_liquid_mm.sum(axis=0)
    liquid_land = melt_to_land_mm.sum(axis=0)
    liquid_unresolved = unresolved_liquid_mm.sum(axis=0)
    liquid_residual = liquid_total - liquid_land - liquid_unresolved
    if _i2_np.abs(liquid_residual).max() > 1e-09:
        raise RuntimeError('the liquid ledger does not close')
    if _i2_np.abs(ice_residual).max() > 1e-06:
        raise RuntimeError('the ice ledger does not close (max |residual| = %r m3)' % float(_i2_np.abs(ice_residual).max()))
    if rock_stock is not None:
        rock_residual = rock_used - solid_export.sum(axis=0)
        if _i2_np.abs(rock_residual).max() > 1e-09:
            raise RuntimeError('the rock ledger does not close')
    bed_delta = -rock_used / area
    payload = {'schema': GLACIER_SCHEMA, 'logical_version': LOGICAL_VERSION, 'algorithm': GLACIER_ALGORITHM, 'flow_model': flow_model, 'parameters': parameters.identity(), 'formula_source': FORMULA_SOURCE, 'flow_law': {'model': 'shallow_ice_deformation_only', 'glen_exponent': n, 'creep_parameter_unit': CREEP_PARAMETER_UNIT, 'creep_parameter_semantics': CREEP_PARAMETER_SEMANTICS, 'face_flux_form': 'W * (2A/(n+2)) * (rho g)^n * H_f^(n+2) * |ds/dx|^(n-1) * (-ds/dx)', 'surface_rule': 'surface = bed + thickness, recomputed every sub-step', 'basal_sliding': False, 'ends': 'closed: the two outer faces carry no ice flux', 'cfl': float(CFL), 'max_substeps_per_interval': int(MAX_SUBSTEPS)}, 'units': {'thickness': 'm', 'volume': 'm3', 'accumulation_input': 'mm_water_equivalent', 'ablation_input': 'mm_water_equivalent', 'melt_output': 'mm_water_equivalent', 'face_flux': 'm3 s^-1', 'erosion': 'intact_rock_m3', 'bed_delta': 'm', 'densification': 'ice_volume_per_unit_water_depth'}, 'erosion': {'status': erosion_status, 'proxy': EROSION_PROXY_SEMANTICS, 'bounded_by_ice_store': False, 'finite_bedrock_supplied': rock_stock is not None, 'couples_back_to_bed': False}, 'liquid': {'to_land_field': 'melt_to_land_mm', 'unresolved_field': 'liquid_export_unresolved_mm', 'policy': 'ice is only ablated when the water it produces is accounted for; a cell without a declared land port exports to liquid_export_unresolved_mm', 'land_port_cells': int(land_port.sum())}, 'time_edges_s': [float(v) for v in edges], 'x_m': [float(v) for v in x], 'dx_m': dx, 'width_m': width, 'cell_area_m2': area, 'spacing_m': NATIVE_SPACING_M, 'claims_denied': {'basal_sliding': True, 'ice_temperature': True, 'calving': True, 'glacier_existence': True, 'bed_feedback_coupled': True, 'real_world_prediction': True, 'one_metre_accuracy': True, 'three_dimensional': True}}
    arrays = {'thickness_edge_m': thickness_edge, 'surface_edge_m': surface_edge, 'ice_volume_edge_m3': volume_edge, 'accumulation_ice_m3': accumulation_ice, 'ablation_ice_m3': ablation_ice, 'melt_liquid_mm': melt_liquid_mm, 'melt_to_land_mm': melt_to_land_mm, 'liquid_export_unresolved_mm': unresolved_liquid_mm, 'face_flux_m3_s': face_flux_mean, 'face_flux_cumulative_m3': face_flux_cube, 'erosion_rock_m3': erosion_rock, 'solid_export_rock_m3': solid_export, 'bed_delta_m': _i2_np.repeat(bed_delta.reshape(1, cells), intervals, axis=0), 'motion_state': motion, 'flux_limited': limited_cells}
    ledger = {'ice': {'volume_start_m3': [float(v) for v in volume[0]], 'volume_end_m3': [float(v) for v in volume[-1]], 'accumulation_m3': [float(v) for v in accumulation_ice.sum(axis=0)], 'ablation_m3': [float(v) for v in ablation_ice.sum(axis=0)], 'flux_divergence_m3': [float(v) for v in flux_divergence.sum(axis=0)], 'residual_m3': [float(v) for v in ice_residual], 'max_abs_residual_m3': float(_i2_np.abs(ice_residual).max())}, 'liquid': {'produced_mm': [float(v) for v in liquid_total], 'to_land_mm': [float(v) for v in liquid_land], 'unresolved_mm': [float(v) for v in liquid_unresolved], 'residual_mm': [float(v) for v in liquid_residual]}, 'rock': {'status': erosion_status, 'supplied_m3': [float(v) for v in rock_stock] if rock_stock is not None else None, 'removed_m3': [float(v) for v in rock_used], 'exported_solid_m3': [float(v) for v in solid_export.sum(axis=0)], 'remaining_m3': [float(v) for v in rock_stock - rock_used] if rock_stock is not None else None}, 'substeps_per_interval': [int(v) for v in substeps], 'dt_limit_s_per_interval': [float(v) for v in dt_limit_edge], 'limited_cells': int(limited_cells.sum()), 'note': 'ice volume closes against accumulation, ablation and face flux divergence; the melt water is fully split between the declared land port and the unresolved export, so none is lost; the rock account is separate and closes against its own finite supply'}
    return {'arrays': arrays, 'ledger': ledger, 'metadata': payload, 'identity_sha256': _i2_digest({'metadata': payload, 'arrays': {name: _i2_array_hash(_i2_np.ascontiguousarray(value)) for name, value in sorted(arrays.items())}})}

def describe():
    return {'schema': GLACIER_SCHEMA, 'logical_version': LOGICAL_VERSION, 'algorithm': GLACIER_ALGORITHM, 'flow_models': list(FLOW_MODELS), 'motion_states': [MOTION_FLOWING, MOTION_STATIONARY, MOTION_STATIC], 'formula_source': FORMULA_SOURCE, 'limitations': list(LIMITATIONS), 'default_parameters': GlacierParameters().identity(), 'cells_bounds': [MIN_CELLS, MAX_CELLS], 'intervals_bound': MAX_INTERVALS, 'max_substeps_per_interval': MAX_SUBSTEPS, 'cfl': CFL, 'cell_area_m2': CELL_AREA_M2, 'spacing_m': NATIVE_SPACING_M, 'not_modelled': ['basal_sliding', 'ice_temperature', 'calving', 'glacier_lake_outburst', 'three_dimensional_flow', 'bed_feedback_coupled', 'real_world_prediction', 'one_metre_accuracy', 'glacier_existence'], 'glacier_existence_policy': GLACIER_EXISTENCE_POLICY, 'creep_parameter_unit': CREEP_PARAMETER_UNIT, 'erosion_proxy_semantics': EROSION_PROXY_SEMANTICS}
OCEAN_COAST_SCHEMA = 'bounded-ocean-coast-v1'
MODEL = 'bounded_basin_wind_driven_conservative_water_heat_v1'
SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K = 4000000.0
LEDGER_RTOL = 1e-09
OPEN = 'open'
CLOSED = 'closed'
AXIAL_STEPS = {(1, 0): 'east', (-1, 0): 'west', (0, 1): 'south', (0, -1): 'north'}
DECLARED_LIMITS = ('finite declared basin; not a global ocean and not a general circulation model', 'no salinity state and therefore no salt budget is claimed', 'heat moves only by conservative upwind advection with the water; sea-surface temperature is never produced by a diffusion operator and called a current', 'flow is driven by a declared wind bearing and speed, not by a random warm/cold label', 'a land cell is never transported through; basins separated by land stay separate')

def water_volume_m3(depth_m, wet_mask, spacing_m):
    """Per-cell water volume in m³ on the declared wet cells; land is exactly zero."""
    depth = _i3_np.asarray(depth_m, _i3_np.float64)
    wet = _i3_np.asarray(wet_mask, bool)
    if depth.shape != wet.shape or depth.ndim != 2:
        raise ValueError('depth_m and wet_mask must be matching 2-D arrays')
    if not _i3_np.isfinite(depth).all() or _i3_np.any(depth < 0.0):
        raise ValueError('finite nonnegative depth required')
    if _i3_np.any(depth[~wet] != 0.0):
        raise ValueError('land cells must declare exactly zero depth')
    return _i3_np.where(wet, depth, 0.0) * float(spacing_m) ** 2

def _validate_axial(wind_bearing):
    pair = (int(wind_bearing[0]), int(wind_bearing[1]))
    if pair not in AXIAL_STEPS:
        raise ValueError('wind_bearing must be one of the axial pairs %r; a diagonal or continuous wind is not accepted here' % (sorted(AXIAL_STEPS),))
    return pair

def _validate_cfl(wind_speed_m_s, dt_s, spacing_m):
    for name, value in (('wind_speed_m_s', wind_speed_m_s), ('dt_s', dt_s), ('spacing_m', spacing_m)):
        if isinstance(value, bool) or not isinstance(value, (int, float, _i3_np.floating)):
            raise ValueError('%s must be a finite positive number' % name)
        if not _i3_math.isfinite(float(value)):
            raise ValueError('%s must be finite' % name)
    speed, dt, dx = (float(wind_speed_m_s), float(dt_s), float(spacing_m))
    if speed < 0.0 or dt <= 0.0 or dx <= 0.0:
        raise ValueError('nonnegative speed and positive dt/dx required')
    cfl = speed * dt / dx
    if cfl > 1.0 + 1e-12:
        raise ValueError('CFL %.6f exceeds 1 (speed %.3f m/s, dt %.3f s, dx %.2f m); the step is refused rather than silently reduced' % (cfl, speed, dt, dx))
    return (speed, cfl)

def _neighbour_index(wind_bearing, shape):
    """Flat index of each cell's downwind neighbour, and the mask of exit cells."""
    rows, columns = shape
    step_x, step_z = wind_bearing
    row = _i3_np.arange(rows)[:, None]
    column = _i3_np.arange(columns)[None, :]
    to_row = row + step_z
    to_column = column + step_x
    inside = (to_row >= 0) & (to_row < rows) & (to_column >= 0) & (to_column < columns)
    index = _i3_np.where(inside, to_row * columns + to_column, -1).astype(_i3_np.int64)
    return (index.reshape(-1), inside.reshape(-1))

def ocean_coast_transport_step(volume_m3, temperature_c, wet_mask, *, wind_bearing, wind_speed_m_s, dt_s, spacing_m, boundary=OPEN):
    """One bounded conservative step of water and heat.

    Parameters
    ----------
    volume_m3 : array_like
        Per-cell water volume in m³, `(rows, columns)`. Land cells must be exactly 0.
    temperature_c : array_like
        Per-cell water temperature in °C on wet cells.
    wet_mask : array_like
        Boolean `(rows, columns)`. A land cell is never transported through.
    wind_bearing : (int, int)
        Axial direction the water is pushed toward.
    wind_speed_m_s, dt_s, spacing_m :
        Face speed, step, and cell spacing; CFL is `speed·dt/dx ≤ 1`.
    boundary : OPEN or CLOSED
        What happens at a wet cell whose downwind neighbour is land or outside.

    Returns
    -------
    dict
        New volume and temperature, per-step face discharge, the water and heat
        ledgers, and the diagnostics that make the step auditable.
    """
    volume = _i3_np.asarray(volume_m3, _i3_np.float64)
    temperature = _i3_np.asarray(temperature_c, _i3_np.float64)
    wet = _i3_np.asarray(wet_mask, bool)
    if not volume.shape == temperature.shape == wet.shape or volume.ndim != 2:
        raise ValueError('volume_m3, temperature_c and wet_mask must be matching 2-D')
    if not _i3_np.isfinite(volume).all() or _i3_np.any(volume < 0.0):
        raise ValueError('finite nonnegative volume required')
    if not _i3_np.isfinite(temperature).all():
        raise ValueError('finite temperature required')
    if _i3_np.any(volume[~wet] != 0.0):
        raise ValueError('land cells must declare exactly zero volume')
    if boundary not in (OPEN, CLOSED):
        raise ValueError('boundary must be %r or %r' % (OPEN, CLOSED))
    direction = _validate_axial(wind_bearing)
    speed, cfl = _validate_cfl(wind_speed_m_s, dt_s, spacing_m)
    spacing = float(spacing_m)
    shape = volume.shape
    flat_volume = volume.reshape(-1)
    flat_wet = wet.reshape(-1)
    flat_temperature = temperature.reshape(-1)
    partner, inside = _neighbour_index(direction, shape)
    open_face = flat_wet & inside & _i3_np.where(partner >= 0, flat_wet[_i3_np.where(partner >= 0, partner, 0)], False)
    face_discharge = _i3_np.where(open_face, speed * dt_s / spacing * flat_volume, 0.0)
    face_discharge = _i3_np.minimum(face_discharge, flat_volume)
    outflow = _i3_np.zeros(flat_volume.size, _i3_np.float64)
    inflow = _i3_np.zeros(flat_volume.size, _i3_np.float64)
    if face_discharge.any():
        outflow += face_discharge
        receiving = partner[open_face]
        _i3_np.add.at(inflow, receiving, face_discharge[open_face])
    exit_face = flat_wet & ~inside
    exit_discharge = _i3_np.zeros(flat_volume.size, _i3_np.float64)
    if boundary == OPEN and exit_face.any():
        exit_discharge[exit_face] = _i3_np.minimum(speed * dt_s / spacing * flat_volume[exit_face], flat_volume[exit_face])
    outflow += exit_discharge
    new_volume = flat_volume - outflow + inflow
    heat_outflow = _i3_np.where(face_discharge > 0.0, face_discharge * flat_temperature, 0.0) + exit_discharge * flat_temperature
    heat_inflow = _i3_np.zeros(flat_volume.size, _i3_np.float64)
    if face_discharge.any():
        _i3_np.add.at(heat_inflow, partner[open_face], face_discharge[open_face] * flat_temperature[open_face])
    old_heat = flat_volume * flat_temperature
    new_heat = old_heat - heat_outflow + heat_inflow
    new_temperature = _i3_np.divide(new_heat, new_volume, out=_i3_np.zeros_like(new_heat), where=new_volume > 0.0)
    water_change = float(new_volume.sum() - flat_volume.sum())
    water_outflow_total = float(exit_discharge.sum())
    heat_change = float(new_heat.sum() - old_heat.sum())
    heat_outflow_total = float((exit_discharge * flat_temperature).sum())
    scale = max(float(flat_volume.sum()), 1.0)
    heat_scale = max(float(_i3_np.abs(old_heat).sum()), 1.0)
    ledger = {'water_start_m3': float(flat_volume.sum()), 'water_end_m3': float(new_volume.sum()), 'water_change_m3': water_change, 'boundary_outflow_m3': water_outflow_total, 'internal_transported_volume_m3': float(face_discharge.sum()), 'heat_start_m3_degc': float(old_heat.sum()), 'heat_end_m3_degc': float(new_heat.sum()), 'heat_change_m3_degc': heat_change, 'boundary_heat_outflow_m3_degc': heat_outflow_total, 'heat_reference': '0 degC; constant specific heat; NOT joules', 'heat_capacity_j_m3k_if_converted': SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K, 'heat_energy_j_if_converted': float(new_heat.sum()) * SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K, 'water_tolerance_m3': LEDGER_RTOL * scale, 'heat_tolerance_m3_degc': LEDGER_RTOL * heat_scale}
    ledger['water_residual_m3'] = water_change + water_outflow_total
    ledger['water_ok'] = abs(ledger['water_residual_m3']) <= ledger['water_tolerance_m3']
    ledger['heat_residual_m3_degc'] = heat_change + heat_outflow_total
    ledger['heat_ok'] = abs(ledger['heat_residual_m3_degc']) <= ledger['heat_tolerance_m3_degc']
    return {'schema': OCEAN_COAST_SCHEMA, 'model': MODEL, 'volume_m3': new_volume.reshape(shape), 'temperature_c': new_temperature.reshape(shape), 'transported_volume_m3': face_discharge.reshape(shape), 'exit_volume_m3': exit_discharge.reshape(shape), 'ledger': ledger, 'diagnostics': {'wind_bearing': list(direction), 'prescribed_current_speed_from_declared_wind_proxy_m_s': speed, 'wind_stress_solved': False, 'dt_s': float(dt_s), 'spacing_m': spacing, 'cfl': cfl, 'boundary': boundary, 'shared_face_count': int(open_face.sum()), 'open_exit_count': int(exit_face.sum()), 'open_boundary_means': 'geometric domain edge only; a land coast is never an open drain', 'heat_content_units': 'm3*degC relative to 0 degC; not joules', 'salinity': 'not_modelled', 'units': 'volume m3; temperature degC; transported quantity is per step, not a rate (divide by dt for m3/s)'}, 'declared_limits': list(DECLARED_LIMITS)}
AEOLIAN_ALGORITHM = 'environment-finite-wind-solid-v1'

def aeolian_initialize(context, *, loose_solid_m3=0.0):
    from terrain_pipeline.environment_contract import bounded_field as _x0_field
    from terrain_pipeline.environment_contract import grid as _x1_grid
    height, _, _ = _x1_grid(context, 1.0)
    return {'loose_solid_m3': _x0_field(loose_solid_m3, height.shape, 'loose solid', 0.0), 'airborne_solid_m3': _i4_np.zeros(height.shape)}

def aeolian_step(state, forcing, context, dt_s, parameters=None):
    from terrain_pipeline.drainage import segments_clear as _i4_segments_clear
    from terrain_pipeline.environment_contract import bounded_field as _x0_field
    from terrain_pipeline.environment_contract import grid as _x1_grid
    from terrain_pipeline.environment_contract import positive_parameters as _x2_parameters
    height, spacing, active = _x1_grid(context, dt_s)
    p = _x2_parameters(parameters, {'threshold_wind_m_s': 5.0, 'entrainment_rate_s_m': 1e-05, 'settling_time_s': 600.0, 'solid_fraction': 0.6})
    if p['solid_fraction'] > 1:
        raise ValueError('solid fraction must not exceed one')
    loose = _x0_field(state['loose_solid_m3'], height.shape, 'loose', 0.0)
    airborne = _x0_field(state['airborne_solid_m3'], height.shape, 'airborne', 0.0)
    wx = _x0_field(forcing.get('wind_x_m_s', 0.0), height.shape, 'wind x')
    wz = _x0_field(forcing.get('wind_z_m_s', 0.0), height.shape, 'wind z')
    wet = _x0_field(forcing.get('water_saturation', 0.0), height.shape, 'saturation', 0.0, 1.0)
    cover = _x0_field(forcing.get('vegetation_cover', 0.0), height.shape, 'vegetation', 0.0, 1.0)
    ocean = _x0_field(context.get('ocean_mask', False), height.shape, 'ocean').astype(bool)
    land = active & ~ocean
    speed = _i4_np.hypot(wx, wz)
    entrained = loose * -_i4_np.expm1(-p['entrainment_rate_s_m'] * _i4_np.maximum(speed - p['threshold_wind_m_s'], 0.0) * dt_s)
    entrained *= (1 - wet) * (1 - cover) * land
    mobile = airborne + entrained
    rows, cols = _i4_np.indices(height.shape)
    dr = _i4_np.where(_i4_np.abs(wz) >= _i4_np.abs(wx), _i4_np.sign(wz), 0).astype(int)
    dc = _i4_np.where(_i4_np.abs(wx) >= _i4_np.abs(wz), _i4_np.sign(wx), 0).astype(int)
    step_length = spacing * _i4_np.maximum(1.0, _i4_np.hypot(dr, dc))
    moved_fraction = _i4_np.minimum(1.0, speed * dt_s / step_length)
    transport = _i4_np.where(active, mobile * moved_fraction, 0.0)
    rr, cc = (rows + dr, cols + dc)
    inside = (rr >= 0) & (rr < height.shape[0]) & (cc >= 0) & (cc < height.shape[1])
    tr, tc = (_i4_np.clip(rr, 0, height.shape[0] - 1), _i4_np.clip(cc, 0, height.shape[1] - 1))
    accepted = inside & active[tr, tc]
    origins = _i4_np.arange(height.size, dtype=_i4_np.int64).reshape(height.shape)
    accepted &= _i4_segments_clear(origins.ravel(), (tr * height.shape[1] + tc).ravel(), active).reshape(height.shape)
    exported = _i4_np.where(~inside, transport, 0.0)
    transferred = _i4_np.where(accepted, transport, 0.0)
    updated = mobile - transferred - exported
    _i4_np.add.at(updated, (tr[accepted], tc[accepted]), transferred[accepted])
    deposited = _i4_np.where(active, updated * -_i4_np.expm1(-dt_s / p['settling_time_s']), 0.0)
    new_loose = loose - entrained + deposited
    new_airborne = updated - deposited
    delta_height = (deposited - entrained) / (spacing ** 2 * p['solid_fraction'])
    return {'state': {'loose_solid_m3': new_loose, 'airborne_solid_m3': new_airborne}, 'fluxes': {'entrained_solid_m3': entrained, 'transported_solid_m3': transferred, 'deposited_solid_m3': deposited, 'boundary_export_solid_m3': exported, 'height_change_m': delta_height}, 'ledger': {'initial_solid_m3': float((loose + airborne).sum()), 'final_solid_m3': float((new_loose + new_airborne).sum()), 'boundary_export_solid_m3': float(exported.sum()), 'solid_residual_m3': float((new_loose + new_airborne).sum() + exported.sum() - (loose + airborne).sum())}, 'metadata': {'algorithm': AEOLIAN_ALGORITHM, 'parameters': p, 'source': 'declared uncalibrated single sand-class finite inventory', 'units': 'inventories and transfers m3 solid per cell; height metres bulk; wind m/s; dt seconds', 'transport': 'one downwind native account per step; protected/unknown block; exterior export explicit', 'limitation': 'no resolved dune migration/loess grain sorting; ocean deposition remains finite tracked solid'}}
COASTAL_EXCHANGE_ALGORITHM = 'environment-tidal-prism-salt-active-bed-v1'
COASTAL_EXCHANGE_PARAMETERS = {'porosity': 0.35, 'exchange_timescale_s': 1800.0, 'wave_transfer_timescale_s': 86400.0, 'max_tide_substep_s': 900.0}

def _connected(bed, level, seeds, valid):
    below = (bed < level) & valid
    return _i5_binary_propagation(seeds & below, mask=below)

def initialize_coastal_exchange(context, *, sea_level_m=0.0, ocean_salinity_kg_m3=35.0, mobile_thickness_m=0.3):
    from terrain_pipeline.environment_contract import field as _x3_field
    from terrain_pipeline.environment_contract import frame as _x4_frame
    shape, area, masks = _x4_frame(context, 0.0)
    bed = _x3_field(context, 'height_m', shape, nonnegative=False)
    for number in (sea_level_m, ocean_salinity_kg_m3, mobile_thickness_m):
        if not _i5_np.isfinite(number):
            raise ValueError('finite initial coast parameters required')
    if min(ocean_salinity_kg_m3, mobile_thickness_m) < 0.0:
        raise ValueError('nonnegative salt and mobile thickness required')
    wet = _connected(bed, sea_level_m, masks['ocean_mask'], masks['valid_mask'])
    water = _i5_np.maximum(sea_level_m - bed, 0.0) * wet * area
    mobile = mobile_thickness_m * area * (1.0 - COASTAL_EXCHANGE_PARAMETERS['porosity'])
    mobile *= masks['valid_mask'] & ~masks['protected_mask']
    return {'water_m3': water, 'salt_kg': water * ocean_salinity_kg_m3, 'bed_solid_m3': mobile, 'bed_m': bed, 'time_s': _i5_np.zeros(shape)}

def advance_coastal_exchange(state, forcing, context, dt_s):
    from terrain_pipeline.surface_rivers.metric_coastal_transport import _face_transfer as _i5__face_transfer
    from terrain_pipeline.environment_contract import field as _x3_field
    from terrain_pipeline.environment_contract import frame as _x4_frame
    from terrain_pipeline.environment_contract import metadata as _x5_metadata
    from terrain_pipeline.environment_contract import stocks as _x6_stocks
    shape, area, masks = _x4_frame(context, dt_s)
    old = _x6_stocks(state, ('water_m3', 'salt_kg', 'bed_solid_m3', 'bed_m', 'time_s'), shape, signed=('bed_m',))
    if not _i5_np.all(old['time_s'] == old['time_s'].flat[0]):
        raise ValueError('coastal physical time must be uniform across the grid')
    valid = masks['valid_mask']
    active = valid & ~masks['protected_mask']
    mouth = _i5_np.asarray(forcing.get('mouth_mask', _i5_np.zeros(shape, bool)))
    if mouth.shape != shape or mouth.dtype != bool or _i5_np.any(mouth & ~valid):
        raise ValueError('explicit valid mouth_mask required')
    river_rate = _x3_field(forcing, 'river_boundary_water_m3_s', shape)
    solid_rate = _x3_field(forcing, 'river_boundary_solid_m3_s', shape)
    if _i5_np.any((river_rate > 0.0) & ~(mouth & active)) or _i5_np.any((solid_rate > 0.0) & ~(mouth & active)):
        raise ValueError('river water/solid boundary only at explicit unprotected mouths')
    amplitude = float(forcing.get('tide_amplitude_m', 0.0))
    period = float(forcing.get('tide_period_s', 44712.0))
    mean = float(forcing.get('mean_sea_level_m', 0.0))
    phase = float(forcing.get('tide_phase_rad', 0.0))
    wave_height = float(forcing.get('wave_height_m', 0.0))
    if not _i5_np.isfinite([amplitude, period, mean, phase, wave_height]).all() or min(amplitude, wave_height) < 0.0 or period <= 0.0:
        raise ValueError('finite tide/wave forcing and positive period required')
    direction = _i5_np.asarray(forcing.get('wave_direction_xz', (1.0, 0.0)), _i5_np.float64)
    if direction.shape != (2,) or not _i5_np.isfinite(direction).all() or _i5_np.linalg.norm(direction) == 0.0:
        raise ValueError('nonzero wave direction required')
    direction = direction / _i5_np.linalg.norm(direction)
    ocean_salt = _x3_field(forcing, 'ocean_salinity_kg_m3', shape, 35.0)
    water, salt, inventory, bed = (old[k].copy() for k in ('water_m3', 'salt_kg', 'bed_solid_m3', 'bed_m'))
    flux = {name: _i5_np.zeros(shape) for name in ('tide_water_m3', 'tide_salt_kg', 'flood_water_m3', 'ebb_water_m3', 'wave_bed_transfer_m3', 'river_water_m3', 'river_solid_m3', 'soil_water_m3', 'soil_salt_kg')}
    soil_rate = _x3_field(forcing, 'soil_exchange_m3_s', shape) * active
    gross_wave = 0.0
    start = float(old['time_s'].flat[0])
    steps = max(1, int(_i5_np.ceil(dt_s / min(COASTAL_EXCHANGE_PARAMETERS['max_tide_substep_s'], period / 16.0))))
    if steps > 10000:
        raise ValueError('coastal interval exceeds bounded substep budget')
    step = dt_s / steps
    wet = _i5_np.zeros(shape, bool)
    level = mean + amplitude * _i5_np.sin(2.0 * _i5_np.pi * start / period + phase)
    for index in range(steps):
        time = start + (index + 1) * step
        level = mean + amplitude * _i5_np.sin(2.0 * _i5_np.pi * time / period + phase)
        wet = _connected(bed, level, masks['ocean_mask'], valid)
        river_water = river_rate * step
        river_solid = solid_rate * step
        water += river_water
        inventory += river_solid
        flux['river_water_m3'] += river_water
        flux['river_solid_m3'] += river_solid
        target = _i5_np.maximum(level - bed, 0.0) * wet * area
        exchange_support = wet | _connected(bed, mean + amplitude + 1e-09, masks['ocean_mask'], valid)
        exchange = (target - water) * -_i5_np.expm1(-step / COASTAL_EXCHANGE_PARAMETERS['exchange_timescale_s']) * exchange_support * active
        concentration = _i5_np.divide(salt, water, out=_i5_np.zeros(shape), where=water > 0.0)
        salt_exchange = _i5_np.where(exchange >= 0.0, exchange * ocean_salt, exchange * concentration)
        water += exchange
        salt += salt_exchange
        flux['tide_water_m3'] += exchange
        flux['tide_salt_kg'] += salt_exchange
        flux['flood_water_m3'] += _i5_np.maximum(exchange, 0.0)
        flux['ebb_water_m3'] += _i5_np.maximum(-exchange, 0.0)
        soil_water = _i5_np.minimum(water, soil_rate * step)
        mixed_salt = _i5_np.divide(salt, water, out=_i5_np.zeros(shape), where=water > 0.0)
        soil_salt = soil_water * mixed_salt
        water -= soil_water
        salt -= soil_salt
        flux['soil_water_m3'] += soil_water
        flux['soil_salt_kg'] += soil_salt
        if wave_height > 0.0 and step > 0.0:
            gz, gx = _i5_np.gradient(bed, float(context['spacing_m']))
            norm = _i5_np.maximum(_i5_np.hypot(gx, gz), 1e-12)
            tx, tz = (-gz / norm, gx / norm)
            along = direction[0] * tx + direction[1] * tz
            fraction = _i5_np.full(shape, -_i5_np.expm1(-wave_height * step / COASTAL_EXCHANGE_PARAMETERS['wave_transfer_timescale_s']))
            inventory, change, gross = _i5__face_transfer(inventory, along * tx, along * tz, fraction, active.astype(float), wet, wet)
            flux['wave_bed_transfer_m3'] += change
            gross_wave += gross
        bed = old['bed_m'] + (inventory - old['bed_solid_m3']) / (area * (1.0 - COASTAL_EXCHANGE_PARAMETERS['porosity']))
    concentration = _i5_np.divide(salt, water, out=_i5_np.zeros(shape), where=water > 0.0)
    output = {'water_m3': water, 'salt_kg': salt, 'bed_solid_m3': inventory, 'bed_m': bed, 'time_s': old['time_s'] + dt_s}
    ledger = {'river_water_input_m3': float(flux['river_water_m3'].sum()), 'river_solid_input_m3': float(flux['river_solid_m3'].sum()), 'signed_ocean_water_m3': float(flux['tide_water_m3'].sum()), 'signed_ocean_salt_kg': float(flux['tide_salt_kg'].sum()), 'soil_water_export_m3': float(flux['soil_water_m3'].sum()), 'soil_salt_export_kg': float(flux['soil_salt_kg'].sum()), 'gross_wave_transfer_solid_m3': gross_wave}
    ledger['water_residual_m3'] = float((old['water_m3'] + flux['river_water_m3'] + flux['tide_water_m3'] - flux['soil_water_m3'] - water).sum())
    ledger['salt_residual_kg'] = float((old['salt_kg'] + flux['tide_salt_kg'] - flux['soil_salt_kg'] - salt).sum())
    ledger['solid_residual_m3'] = float((old['bed_solid_m3'] + flux['river_solid_m3'] - inventory).sum())
    flux.update(salinity_kg_m3=concentration, water_stage_m=bed + water / area, wet_fraction=(water > 1e-12).astype(float), tide_level_m=_i5_np.full(shape, level))
    return {'state': output, 'fluxes': flux, 'ledger': ledger, 'metadata': _x5_metadata(COASTAL_EXCHANGE_ALGORITHM, context, dt_s, ['reduced connected prism; no dynamic backwater, 2D wave momentum, refraction or long-term shoreline certification', 'ocean_mask is explicit external reservoir support, not inferred scene-edge outlet', 'river boundary volumes are already routed and must be debited upstream exactly once', 'solid transfers closed at patch perimeter; bedrock below finite mobile inventory immobile'], COASTAL_EXCHANGE_PARAMETERS.copy())}
FROZEN_GROUND_ALGORITHM = 'environment-soil-water-enthalpy-v1'
LATENT_J_M3 = 334000000.0

def frozen_ground_initialize(context, *, liquid_water_m=0.1, ground_ice_m=0.0, soil_temperature_c=0.0, snow_swe_m=0.0):
    from terrain_pipeline.environment_contract import bounded_field as _x7_field
    from terrain_pipeline.environment_contract import grid as _x8_grid
    height, _, _ = _x8_grid(context, 1.0)
    return {'liquid_water_m': _x7_field(liquid_water_m, height.shape, 'liquid', 0.0), 'ground_ice_m': _x7_field(ground_ice_m, height.shape, 'ice', 0.0), 'soil_temperature_c': _x7_field(soil_temperature_c, height.shape, 'temperature'), 'snow_swe_m': _x7_field(snow_swe_m, height.shape, 'snow', 0.0), 'thaw_time_s': _i6_np.zeros(height.shape), 'frozen_time_s': _i6_np.zeros(height.shape)}

def frozen_ground_step(state, forcing, context, dt_s, parameters=None):
    from terrain_pipeline.environment_contract import bounded_field as _x7_field
    from terrain_pipeline.environment_contract import grid as _x8_grid
    from terrain_pipeline.environment_contract import positive_parameters as _x9_parameters
    height, spacing, active = _x8_grid(context, dt_s)
    active &= ~_x7_field(context.get('ocean_mask', False), height.shape, 'ocean').astype(bool)
    p = _x9_parameters(parameters, {'soil_heat_capacity_j_m2_k': 2000000.0, 'air_exchange_w_m2_k': 5.0, 'snow_insulation_per_m_swe': 50.0, 'thermal_diffusivity_m2_s': 5e-07, 'soil_depth_m': 2.0})
    old = {key: _x7_field(value, height.shape, key, None if key == 'soil_temperature_c' else 0.0) for key, value in state.items()}
    liquid, ice, snow, temp = (old[key] for key in ('liquid_water_m', 'ground_ice_m', 'snow_swe_m', 'soil_temperature_c'))
    heat = _x7_field(forcing.get('ground_heat_w_m2', 0.0), height.shape, 'ground heat')
    heat += _x7_field(forcing.get('geothermal_heat_w_m2', 0.0), height.shape, 'geothermal')
    air = _x7_field(forcing.get('air_temperature_c', temp), height.shape, 'air temperature')
    heat += p['air_exchange_w_m2_k'] * (air - temp) / (1 + p['snow_insulation_per_m_swe'] * snow)
    energy = _i6_np.where(active, heat * dt_s, 0.0)
    snowmelt = _i6_np.minimum(snow, _i6_np.maximum(energy, 0.0) / LATENT_J_M3)
    soil_energy = energy - snowmelt * LATENT_J_M3
    mass = liquid + ice
    initial_enthalpy = temp * p['soil_heat_capacity_j_m2_k'] + liquid * LATENT_J_M3
    enthalpy = initial_enthalpy + soil_energy
    new_liquid = _i6_np.clip(enthalpy / LATENT_J_M3, 0.0, mass)
    new_ice = mass - new_liquid
    new_temp = _i6_np.where(enthalpy < 0, enthalpy, _i6_np.maximum(enthalpy - mass * LATENT_J_M3, 0.0)) / p['soil_heat_capacity_j_m2_k']
    new = {key: value.copy() for key, value in old.items()}
    for key, value in (('liquid_water_m', new_liquid), ('ground_ice_m', new_ice), ('soil_temperature_c', new_temp), ('snow_swe_m', snow - snowmelt)):
        new[key] = _i6_np.where(active, value, old[key])
    frozen = new['ground_ice_m'] > 1e-10
    new['thaw_time_s'] = _i6_np.where(active, _i6_np.where(frozen, 0.0, old['thaw_time_s'] + dt_s), old['thaw_time_s'])
    new['frozen_time_s'] = _i6_np.where(active, _i6_np.where(frozen, old['frozen_time_s'] + dt_s, 0.0), old['frozen_time_s'])
    final_enthalpy = new['soil_temperature_c'] * p['soil_heat_capacity_j_m2_k'] + new['liquid_water_m'] * LATENT_J_M3
    area = spacing ** 2
    return {'state': new, 'fluxes': {'snow_meltwater_m': snowmelt, 'frozen_water_m': _i6_np.maximum(new['ground_ice_m'] - ice, 0.0), 'thawed_water_m': _i6_np.maximum(ice - new['ground_ice_m'], 0.0), 'infiltration_factor': _i6_np.divide(new['liquid_water_m'], mass, out=_i6_np.ones_like(mass), where=mass > 0), 'active_layer_depth_m': _i6_np.minimum(p['soil_depth_m'], _i6_np.sqrt(2 * p['thermal_diffusivity_m2_s'] * new['thaw_time_s'])), 'height_change_m': 0.09 * (new['ground_ice_m'] - ice)}, 'ledger': {'heat_input_j': float(energy.sum() * area), 'snow_latent_j': float(snowmelt.sum() * LATENT_J_M3 * area), 'energy_residual_j': float((final_enthalpy - initial_enthalpy - soil_energy).sum() * area), 'water_residual_m3': float((new['liquid_water_m'] + new['ground_ice_m'] + new['snow_swe_m'] + snowmelt - liquid - ice - snow).sum() * area)}, 'metadata': {'algorithm': FROZEN_GROUND_ALGORITHM, 'parameters': p, 'latent_heat_j_m3_water': LATENT_J_M3, 'source': 'declared uncalibrated one-layer enthalpy and snow insulation', 'units': 'water/ice/snow water-equivalent metres; soil Celsius; time seconds; ledger J and m3 water; height metres', 'limitation': 'no multilayer permafrost/talik mechanics; snow melt exported for water consumer; phase must initially be in thermal equilibrium'}}
GROUNDWATER_ALGORITHM = 'environment-head-bucket-exchange-v1'

def groundwater_initial_state(context, *, groundwater_water_m3=0.0, surface_water_m3=0.0):
    from terrain_pipeline.environment_contract import array as _x10_array
    from terrain_pipeline.environment_contract import context_arrays as _x11_context_arrays
    height, masks, _, _ = _x11_context_arrays(context, 1.0)
    state = {'groundwater_water_m3': _x10_array(groundwater_water_m3, height.shape, 'groundwater_water_m3'), 'surface_water_m3': _x10_array(surface_water_m3, height.shape, 'surface_water_m3')}
    if any((_i7_np.any(value[~masks['valid_mask']] != 0.0) for value in state.values())):
        raise ValueError('water stock outside valid support')
    return state

def groundwater_step(initial_state, forcing, context, dt_s):
    from terrain_pipeline.drainage import segments_clear as _i7_segments_clear
    from terrain_pipeline.environment_contract import array as _x10_array
    from terrain_pipeline.environment_contract import context_arrays as _x11_context_arrays
    height, masks, mesh, _ = _x11_context_arrays(context, dt_s)
    shape = height.shape
    state = {name: _x10_array(initial_state[name], shape, name) for name in ('groundwater_water_m3', 'surface_water_m3')}
    if any((_i7_np.any(value[~masks['valid_mask']] != 0.0) for value in state.values())):
        raise ValueError('water stock outside valid support')
    before = sum((float(value.sum()) for value in state.values()))
    area_m2 = float(context['spacing_m']) ** 2
    specific_yield = _x10_array(forcing.get('specific_yield', 0.2), shape, 'specific_yield')
    if _i7_np.any(specific_yield <= 0.0) or _i7_np.any(specific_yield > 1.0):
        raise ValueError('specific_yield must be in (0,1]')
    base = _x10_array(forcing.get('aquifer_base_m', height - 10.0), shape, 'aquifer_base_m', nonnegative=False)
    if _i7_np.any(base > height):
        raise ValueError('aquifer base cannot exceed terrain')
    recharge = _x10_array(forcing.get('recharge_m3', 0.0), shape, 'recharge_m3')
    surface_input = _x10_array(forcing.get('surface_input_m3', 0.0), shape, 'surface_input_m3')
    if _i7_np.any((recharge + surface_input)[~masks['valid_mask']] != 0.0):
        raise ValueError('water forcing outside valid support')
    groundwater = state['groundwater_water_m3']
    surface = state['surface_water_m3']
    groundwater += recharge
    surface += surface_input
    head = base + groundwater / (area_m2 * specific_yield)
    conductance = _x10_array(forcing.get('lateral_conductance_m2_s', 0.0), shape, 'lateral_conductance_m2_s')
    sources = _i7_np.repeat(_i7_np.arange(height.size), _i7_np.diff(mesh.indptr))
    targets = mesh.indices.astype(_i7_np.int64)
    keep = sources < targets
    sources, targets = (sources[keep], targets[keep])
    keep = _i7_segments_clear(sources, targets, masks['valid_mask'])
    sources, targets = (sources[keep], targets[keep])
    delta_head = head.ravel()[sources] - head.ravel()[targets]
    donors = _i7_np.where(delta_head >= 0.0, sources, targets)
    receivers = _i7_np.where(delta_head >= 0.0, targets, sources)
    requested = _i7_np.minimum(conductance.ravel()[donors], conductance.ravel()[receivers]) * _i7_np.abs(delta_head) * dt_s
    requested_total = _i7_np.bincount(donors, weights=requested, minlength=height.size)
    factor = _i7_np.minimum(1.0, _i7_np.divide(groundwater.ravel(), requested_total, out=_i7_np.ones(height.size), where=requested_total > 0.0))
    exchanged = requested * factor[donors]
    lateral_delta = _i7_np.bincount(receivers, weights=exchanged, minlength=height.size)
    lateral_delta -= _i7_np.bincount(donors, weights=exchanged, minlength=height.size)
    groundwater += lateral_delta.reshape(shape)
    head = base + groundwater / (area_m2 * specific_yield)
    lake = _i7_np.asarray(context.get('lake_mask', _i7_np.zeros(shape, bool)))
    if lake.shape != shape or lake.dtype != bool:
        raise ValueError('lake_mask must be a matching boolean array')
    connected = (masks['river_mask'] | lake) & masks['valid_mask']
    stage = _x10_array(forcing.get('surface_stage_m', height + surface / area_m2), shape, 'surface_stage_m', nonnegative=False)
    exchange_k = _x10_array(forcing.get('surface_conductance_m2_s', 0.0), shape, 'surface_conductance_m2_s')
    exchange = exchange_k * (head - stage) * dt_s * connected
    exchange = _i7_np.where(exchange >= 0.0, _i7_np.minimum(exchange, groundwater), -_i7_np.minimum(-exchange, surface))
    groundwater -= exchange
    surface += exchange
    capacity = (height - base) * area_m2 * specific_yield
    spring = _i7_np.maximum(groundwater - capacity, 0.0)
    groundwater -= spring
    surface += spring
    pumping = _i7_np.minimum(_x10_array(forcing.get('pumping_request_m3', 0.0), shape, 'pumping_request_m3'), groundwater)
    groundwater -= pumping
    after = float(groundwater.sum() + surface.sum())
    return {'state': state, 'fluxes': {'recharge_m3': recharge, 'surface_input_m3': surface_input, 'lateral_net_m3': lateral_delta.reshape(shape), 'groundwater_to_surface_m3': exchange, 'spring_m3': spring, 'pumping_m3': pumping, 'groundwater_head_m': base + groundwater / (area_m2 * specific_yield)}, 'ledger': {'water_before_m3': before, 'water_after_m3': after, 'recharge_m3': float(recharge.sum()), 'surface_input_m3': float(surface_input.sum()), 'pumping_m3': float(pumping.sum()), 'water_residual_m3': before + float(recharge.sum() + surface_input.sum()) - float(pumping.sum()) - after}, 'metadata': {'algorithm': GROUNDWATER_ALGORITHM, 'dt_s': float(dt_s), 'origin_native_xz': list(context['origin_native_xz']), 'spacing_m': float(context['spacing_m']), 'world_seed': int(context['world_seed']), 'parameter_status': 'engineering_scenario_uncalibrated', 'exchange_semantics': 'already applied to both returned stocks; do not debit again', 'limitations': ['explicit finite head buckets, donor limited; not a Darcy/PDE aquifer solver', 'no karst conduits or calibrated natural spring certification']}}
HABITAT_ALGORITHM = 'environment-functional-habitat-cost-dispersal-v1'
HABITAT_PARAMETERS = {'capacity_individuals_m2': 0.001, 'growth_timescale_s': 180.0 * 86400.0, 'migration_timescale_s': 7.0 * 86400.0, 'max_cost_m': 3000.0, 'minimum_suitability': 0.05}

def initialize_habitat(context, *, population_individuals=0.0):
    from terrain_pipeline.environment_contract import field as _x12_field
    from terrain_pipeline.environment_contract import frame as _x13_frame
    shape, _, masks = _x13_frame(context, 0.0)
    population = _x12_field({'v': population_individuals}, 'v', shape)
    population *= masks['valid_mask'] & ~masks['ocean_mask'] & ~masks['protected_mask']
    return {'population_individuals': population, 'occupancy_s': _i8_np.zeros(shape)}

def advance_habitat(state, forcing, context, dt_s):
    from terrain_pipeline.drainage import valid_edge_mask as _i8_valid_edge_mask
    from terrain_pipeline.environment_contract import field as _x12_field
    from terrain_pipeline.environment_contract import frame as _x13_frame
    from terrain_pipeline.environment_contract import metadata as _x14_metadata
    from terrain_pipeline.environment_contract import stocks as _x15_stocks
    from terrain_pipeline.environment_contract import prepare_mesh as _x16_prepare_mesh
    shape, area, masks = _x13_frame(context, dt_s)
    pools = _x15_stocks(state, ('population_individuals', 'occupancy_s'), shape)
    population = pools['population_individuals']
    occupancy = pools['occupancy_s']
    active = masks['valid_mask'] & ~masks['ocean_mask'] & ~masks['protected_mask']
    cover = _x12_field(forcing, 'vegetation_cover_fraction', shape)
    water = _x12_field(forcing, 'water_available_fraction', shape)
    disturbance = _x12_field(forcing, 'disturbance_fraction', shape)
    if any((_i8_np.any(v > 1.0) for v in (cover, water, disturbance))):
        raise ValueError('habitat cover, water and disturbance fractions must be <=1')
    temperature = _x12_field(forcing, 'water_temperature_c', shape, 15.0, nonnegative=False)
    thermal = _i8_np.clip(1.0 - _i8_np.abs(temperature - 15.0) / 25.0, 0.0, 1.0)
    suitability = cover * _i8_np.sqrt(water) * thermal * (1.0 - disturbance) * active
    capacity = suitability * area * HABITAT_PARAMETERS['capacity_individuals_m2']
    passable = (suitability >= HABITAT_PARAMETERS['minimum_suitability']) & active
    mesh = _x16_prepare_mesh(context, shape, edge_order='stable')
    edges_valid = _i8_valid_edge_mask(mesh, active)
    initial = population.copy()
    distances = _i8_np.full(population.size, _i8_np.inf)
    queue = []
    for node in _i8_np.flatnonzero((population > 0.0) & active):
        distances[node] = 0.0
        _i8_heapq.heappush(queue, (0.0, int(node)))
    flat_suitable = suitability.ravel()
    height = _i8_np.asarray(context['height_m']).ravel()
    pass_flat = passable.ravel()
    while queue:
        distance, node = _i8_heapq.heappop(queue)
        if distance != distances[node]:
            continue
        for edge in range(mesh.indptr[node], mesh.indptr[node + 1]):
            target = int(mesh.indices[edge])
            if not edges_valid[edge] or not pass_flat[target]:
                continue
            length = mesh.edge_length_m[edge]
            cost = length * (1.0 + abs(height[node] - height[target]) / length) / max(flat_suitable[target], 0.05)
            candidate = distance + cost
            if candidate <= HABITAT_PARAMETERS['max_cost_m'] and candidate < distances[target]:
                distances[target] = candidate
                _i8_heapq.heappush(queue, (candidate, target))
    reachable = _i8_np.isfinite(distances).reshape(shape)
    migration = _i8_np.zeros(population.size)
    gross = 0.0
    remaining = _i8_np.maximum(capacity.ravel() - population.ravel(), 0.0)
    fraction = -_i8_np.expm1(-dt_s / HABITAT_PARAMETERS['migration_timescale_s'])
    for donor in _i8_np.flatnonzero((population > 0.0) & active):
        section = slice(mesh.indptr[donor], mesh.indptr[donor + 1])
        targets = mesh.indices[section][edges_valid[section]]
        lengths = mesh.edge_length_m[section][edges_valid[section]]
        costs = lengths * (1.0 + _i8_np.abs(height[donor] - height[targets]) / lengths) / _i8_np.maximum(flat_suitable[targets], 0.05)
        allowed = pass_flat[targets] & reachable.ravel()[targets] & (costs <= HABITAT_PARAMETERS['max_cost_m'])
        targets = targets[allowed]
        costs = costs[allowed]
        if targets.size == 0:
            continue
        weights = remaining[targets] * flat_suitable[targets] / _i8_np.maximum(costs, 1e-12)
        if weights.sum() <= 0.0:
            continue
        proposed = population.ravel()[donor] * fraction * weights / weights.sum()
        moved = _i8_np.minimum(proposed, remaining[targets])
        migration[donor] -= moved.sum()
        _i8_np.add.at(migration, targets, moved)
        remaining[targets] -= moved
        gross += float(moved.sum())
    migrated = population + migration.reshape(shape)
    growth_fraction = -_i8_np.expm1(-dt_s / HABITAT_PARAMETERS['growth_timescale_s'])
    birth = migrated * _i8_np.clip(1.0 - _i8_np.divide(migrated, capacity, out=_i8_np.ones(shape), where=capacity > 0.0), 0.0, 1.0) * growth_fraction * active
    birth = _i8_np.minimum(birth, _i8_np.maximum(capacity - migrated, 0.0))
    death = _i8_np.maximum(migrated - capacity, 0.0) * growth_fraction * active
    final = migrated + birth - death
    occupied_time = _i8_np.where(active & (final > 1e-12), occupancy + dt_s, occupancy)
    ledger = {'initial_population': float(initial.sum()), 'births_individuals': float(birth.sum()), 'deaths_individuals': float(death.sum()), 'gross_migration_individuals': gross, 'final_population': float(final.sum())}
    ledger['population_residual'] = float((initial + birth - death - final).sum())
    cost = _i8_np.where(reachable, distances.reshape(shape), -1.0)
    return {'state': {'population_individuals': final, 'occupancy_s': occupied_time}, 'fluxes': {'migration_net_individuals': migration.reshape(shape), 'births_individuals': birth, 'deaths_individuals': death, 'suitability': suitability, 'carrying_capacity_individuals': capacity, 'reachable_mask': reachable, 'corridor_cost_m': cost}, 'ledger': ledger, 'metadata': _x14_metadata(HABITAT_ALGORITHM, context, dt_s, ['declared terrestrial riparian functional group, fractional expected individuals, no species food web', 'irregular graph dispersal within finite patch; no cross-patch migration certification', 'max_cost_m bounds each actual donor movement; global cost field is a multi-source corridor witness', 'protected and unknown accounts block migration'], HABITAT_PARAMETERS.copy())}
MASS_ALGORITHM = 'environment-finite-weathering-transport-v1'
STOCKS = ('soil_solid_m3', 'hillslope_deposit_solid_m3', 'river_sediment_solid_m3', 'ocean_export_solid_m3', 'downstream_delivered_solid_m3')
WEATHER_FIELDS = ('bedrock_solid_m3', 'regolith_solid_m3', 'regolith_bulk_m3', 'parent_solid_m3', 'dissolved_solid_m3', 'delivered_regolith_solid_m3', 'delivered_parent_solid_m3', 'weatherable_thickness_m', 'area_m2', 'bed_hardness', 'solubility', 'initial_bedrock_solid_m3')

def mass_initial_state(context, *, bedrock_thickness_m=1.0, bed_hardness=0.5, solubility=0.2):
    from terrain_pipeline.soil_water import MAX_COLUMNS as _x110_MAX_COLUMNS
    from terrain_pipeline.soil_water import initial_state as _x111_initial_state
    from terrain_pipeline.environment_contract import array as _x17_array
    from terrain_pipeline.environment_contract import context_arrays as _x18_context_arrays
    height, masks, _, _ = _x18_context_arrays(context, 1.0)
    shape = height.shape
    values = [_x17_array(v, shape, n) for v, n in ((bedrock_thickness_m, 'bedrock_thickness_m'), (bed_hardness, 'bed_hardness'), (solubility, 'solubility'))]
    if _i9_np.any(values[1] > 1.0) or _i9_np.any(values[2] > 1.0):
        raise ValueError('bed_hardness and solubility must be fractions')
    values[0][~masks['valid_mask'] | masks['ocean_mask']] = 0.0
    parts = {name: [] for name in WEATHER_FIELDS}
    for start in range(0, height.size, _x110_MAX_COLUMNS):
        stop = start + _x110_MAX_COLUMNS
        block = _x111_initial_state(bedrock_thickness_m=values[0].ravel()[start:stop], area_m2=float(context['spacing_m']) ** 2, bed_hardness=values[1].ravel()[start:stop], solubility=values[2].ravel()[start:stop])
        for name in WEATHER_FIELDS:
            parts[name].append(block[name])
    state = {name: _i9_np.concatenate(parts[name]).reshape(shape) for name in WEATHER_FIELDS}
    state.update({name: _i9_np.zeros(shape) for name in STOCKS})
    state['regolith_porosity'] = _i9_np.full(shape, 0.35)
    return state

def mass_step(initial_state, forcing, context, dt_s):
    from terrain_pipeline.soil_water import MAX_COLUMNS as _x110_MAX_COLUMNS
    from terrain_pipeline.soil_water import normalize_parameters as _x112_normalize_parameters
    from terrain_pipeline.soil_water import advance as _x113_advance
    from terrain_pipeline.soil_water import allocate as _x114_allocate
    from terrain_pipeline.environment_contract import array as _x17_array
    from terrain_pipeline.environment_contract import context_arrays as _x18_context_arrays
    height, masks, mesh, receiver = _x18_context_arrays(context, dt_s)
    shape = height.shape
    state = {name: _x17_array(initial_state[name], shape, name) for name in (*WEATHER_FIELDS, *STOCKS)}
    active = masks['valid_mask'] & ~masks['protected_mask'] & ~masks['ocean_mask']
    parameters = _x112_normalize_parameters(forcing.get('weathering_parameters'))
    previous_porosity = _x17_array(initial_state['regolith_porosity'], shape, 'regolith_porosity')
    porosity = float(parameters['regolith_porosity']['value'])
    if _i9_np.any((previous_porosity != porosity) & (state['regolith_solid_m3'] > 0.0)):
        raise ValueError('cannot change porosity of an existing regolith stock')
    state['regolith_porosity'] = _i9_np.full(shape, porosity)
    temperature = _x17_array(forcing.get('temperature_c', 10.0), shape, 'temperature_c', nonnegative=False)
    moisture = _x17_array(forcing.get('moisture', 0.0), shape, 'moisture')
    biology = _x17_array(forcing.get('bio_activity', 0.0), shape, 'bio_activity')
    if _i9_np.any(moisture > 1.0) or _i9_np.any(biology > 1.0):
        raise ValueError('moisture and bio_activity must be fractions')
    soil_request = _x17_array(forcing.get('soil_request_solid_m3', 0.0), shape, 'soil_request_solid_m3')
    rate = _x17_array(forcing.get('transport_fraction_per_s', 0.0), shape, 'transport_fraction_per_s')
    repose = _x17_array(forcing.get('repose_angle_deg', 34.0), shape, 'repose_angle_deg')
    if _i9_np.any(repose >= 90.0):
        raise ValueError('repose_angle_deg must be below 90')
    slope = _i9_np.zeros(height.size)
    donors = _i9_np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    distance = _i9_np.hypot(mesh.node_x_m[targets] - mesh.node_x_m[donors], mesh.node_z_m[targets] - mesh.node_z_m[donors])
    slope[donors] = (height.ravel()[donors] - height.ravel()[targets]) / distance
    root = _x17_array(forcing.get('root_cohesion_pa', 0.0), shape, 'root_cohesion_pa')
    loose_depth = (state['regolith_bulk_m3'] + state['hillslope_deposit_solid_m3'] / (1.0 - state['regolith_porosity'])) / state['area_m2']
    threshold = _i9_np.tan(_i9_np.deg2rad(repose)) * (1.0 - 0.5 * moisture)
    threshold += root / (1800.0 * 9.80665 * _i9_np.maximum(loose_depth, 0.01))
    unstable = (slope.reshape(shape) > threshold) & active
    fraction = _i9_np.minimum(rate * dt_s, 1.0) * unstable
    delivery = _i9_np.zeros(shape)
    weathered = _i9_np.zeros(shape)
    for start in range(0, height.size, _x110_MAX_COLUMNS):
        stop = min(start + _x110_MAX_COLUMNS, height.size)
        section = slice(start, stop)
        block = {name: state[name].ravel()[section].copy() for name in WEATHER_FIELDS}
        block.update(status=_i9_np.where(block['bedrock_solid_m3'] > 0.0, 'active', 'exhausted'), density_kg_m3=None, parameters=_i9_deepcopy(parameters))
        hardness = block['bed_hardness'].copy()
        block['bed_hardness'][~active.ravel()[section]] = 1.0
        block, flux = _x113_advance(block, dt_s=dt_s, temperature_c=temperature.ravel()[section], moisture=moisture.ravel()[section] * active.ravel()[section], bio_activity=biology.ravel()[section] * active.ravel()[section], parameters=forcing.get('weathering_parameters'))
        block['bed_hardness'] = hardness
        weathered.ravel()[section] = flux['weathered_solid_m3']
        request = block['regolith_solid_m3'] * fraction.ravel()[section]
        block, soil, sediment, _, _ = _x114_allocate(block, soil_parent_solid_m3=soil_request.ravel()[section] * active.ravel()[section], sediment_solid_m3=request, shortage_policy='proportional')
        for name in WEATHER_FIELDS:
            state[name].ravel()[section] = block[name]
        state['soil_solid_m3'].ravel()[section] += soil['soil_parent_solid_m3']
        delivery.ravel()[section] = sediment['sediment_solid_m3']
    deposit_out = state['hillslope_deposit_solid_m3'] * fraction
    state['hillslope_deposit_solid_m3'] -= deposit_out
    moved = delivery + deposit_out
    flux_river = _i9_np.zeros(shape)
    flux_ocean = _i9_np.zeros(shape)
    for donor in _i9_np.flatnonzero(moved.ravel() > 0.0):
        target = receiver[donor]
        if target < 0 or masks['protected_mask'].ravel()[target]:
            state['hillslope_deposit_solid_m3'].ravel()[donor] += moved.ravel()[donor]
        elif masks['ocean_mask'].ravel()[target]:
            flux_ocean.ravel()[target] += moved.ravel()[donor]
        elif masks['river_mask'].ravel()[target]:
            flux_river.ravel()[target] += moved.ravel()[donor]
        else:
            state['hillslope_deposit_solid_m3'].ravel()[target] += moved.ravel()[donor]
    state['river_sediment_solid_m3'] += flux_river
    state['ocean_export_solid_m3'] += flux_ocean
    total = sum((float(state[name].sum()) for name in ('bedrock_solid_m3', 'regolith_solid_m3', 'dissolved_solid_m3', *STOCKS)))
    residual = float(state['initial_bedrock_solid_m3'].sum()) - total
    return {'state': state, 'fluxes': {'weathered_solid_m3': weathered, 'mobilized_solid_m3': moved, 'river_delivery_solid_m3': flux_river, 'ocean_delivery_solid_m3': flux_ocean, 'unstable_mask': unstable}, 'ledger': {'solid_residual_m3': residual, 'current_total_solid_m3': total}, 'metadata': {'algorithm': MASS_ALGORITHM, 'dt_s': float(dt_s), 'origin_native_xz': list(context['origin_native_xz']), 'spacing_m': float(context['spacing_m']), 'world_seed': int(context['world_seed']), 'parameter_status': 'engineering_scenario_uncalibrated', 'weathering_parameters': parameters, 'limitations': ['one-hop loose regolith transport per physical step', 'no rigid blocks, impact, rheology or calibrated landslide hazard']}}
NETWORK_TRANSITION_ALGORITHM = 'environment-finite-network-transition-v1'
INVENTORIES = ('water_m3', 'sediment_solid_m3', 'floodplain_solid_m3')

def _identity(arrays):
    digest = _i10_hashlib.sha256()
    for name, value in sorted(arrays.items()):
        data = _i10_np.ascontiguousarray(value)
        digest.update(name.encode('ascii'))
        digest.update(str((data.dtype.str, data.shape)).encode('ascii'))
        digest.update(data.tobytes())
    return digest.hexdigest()

def _owners(height, receiver, valid):
    owners = _i10_np.full(height.size, -1, _i10_np.int64)
    rec = receiver.ravel()
    linked = rec >= 0
    indegree = _i10_np.bincount(rec[linked], minlength=height.size)
    order = list(_i10_np.flatnonzero(indegree == 0))
    for node in order:
        if rec[node] >= 0:
            indegree[rec[node]] -= 1
            if indegree[rec[node]] == 0:
                order.append(int(rec[node]))
    if len(order) != height.size:
        raise ValueError('receiver graph must be acyclic')
    for node in reversed(order):
        if valid.ravel()[node]:
            target = receiver.ravel()[node]
            owners[node] = node if target < 0 else owners[target]
    return owners.reshape(height.shape)

def network_transition_initial_state(context, *, water_m3=0.0, sediment_solid_m3=0.0, floodplain_solid_m3=0.0):
    from terrain_pipeline.environment_contract import array as _x19_array
    from terrain_pipeline.environment_contract import context_arrays as _x20_context_arrays
    height, masks, _, receiver = _x20_context_arrays(context, 1.0)
    state = {'height_m': height.copy(), 'receiver': receiver.reshape(height.shape).copy(), 'owner_terminal_cell': _owners(height, receiver, masks['valid_mask'])}
    for name, value in zip(INVENTORIES, (water_m3, sediment_solid_m3, floodplain_solid_m3)):
        state[name] = _x19_array(value, height.shape, name)
        if _i10_np.any(state[name][~masks['valid_mask']] != 0.0):
            raise ValueError('inventory outside valid support')
    return state

def _bound_state(state, context, dt_s):
    from terrain_pipeline.environment_contract import context_arrays as _x20_context_arrays
    height, masks, mesh, receiver = _x20_context_arrays(context, dt_s)
    if not _i10_np.array_equal(state['height_m'], height) or not _i10_np.array_equal(state['receiver'].ravel(), receiver):
        raise ValueError('state graph does not match current context; update context after commit')
    result = network_transition_initial_state(context, **{name: state[name] for name in INVENTORIES})
    if not _i10_np.array_equal(state['owner_terminal_cell'], result['owner_terminal_cell']):
        raise ValueError('old ownership does not match graph')
    return (result, masks, mesh)

def network_transition_step(initial_state, forcing, context, dt_s):
    from terrain_pipeline.drainage import route_graph as _i10_route_graph
    from terrain_pipeline.drainage import segments_clear as _i10_segments_clear
    from terrain_pipeline.drainage import strict_receivers as _i10_strict_receivers
    from terrain_pipeline.environment_contract import array as _x19_array
    state, masks, mesh = _bound_state(initial_state, context, dt_s)
    height = state['height_m']
    change = _x19_array(forcing.get('bed_change_m', 0.0), height.shape, 'bed_change_m', nonnegative=False)
    if _i10_np.any(change[~masks['valid_mask'] | masks['protected_mask']] != 0.0):
        raise ValueError('bed change on invalid/protected terrain')
    proposed_height = height + change
    baseline_receiver = state['receiver'].copy()
    if not _i10_np.any(change):
        receiver = state['receiver'].ravel().copy()
    elif context.get('routing_policy', 'strict_candidate') == 'source_terminal_flood':
        outlets = _i10_np.asarray(context['source_terminal_mask'], bool) | masks['ocean_mask'] | ~masks['valid_mask']
        receiver = _i10_route_graph(proposed_height, outlets, mesh).receiver.copy()
        baseline_receiver = _i10_route_graph(height, outlets, mesh).receiver.copy().reshape(height.shape)
    else:
        receiver, _, _ = _i10_strict_receivers(proposed_height, mesh, valid_mask=masks['valid_mask'], outlet_mask=masks['ocean_mask'])
        baseline_receiver = _i10_strict_receivers(height, mesh, valid_mask=masks['valid_mask'], outlet_mask=masks['ocean_mask'])[0].reshape(height.shape)
    donors = _i10_np.flatnonzero(receiver >= 0)
    blocked = donors[~_i10_segments_clear(donors, receiver[donors], masks['valid_mask'])]
    receiver[blocked] = -1
    receiver = receiver.reshape(height.shape)
    owners = _owners(proposed_height, receiver, masks['valid_mask'])
    baseline_owner = _owners(height, baseline_receiver, masks['valid_mask'])
    old_owner = state['owner_terminal_cell']
    changed = masks['valid_mask'] & (owners != old_owner)
    proposed = {'height_m': proposed_height, 'receiver': receiver, 'owner_terminal_cell': owners}
    events = {'previous_owner_terminal_cell': old_owner.copy(), 'proposed_owner_terminal_cell': owners, 'owner_changed_mask': changed, 'receiver_changed_mask': receiver != state['receiver'], 'baseline_policy_receiver': baseline_receiver, 'baseline_policy_changed_mask': baseline_receiver != state['receiver'], 'bed_induced_receiver_changed_mask': receiver != baseline_receiver, 'baseline_policy_owner_terminal_cell': baseline_owner, 'bed_induced_owner_changed_mask': masks['valid_mask'] & (owners != baseline_owner), 'proposed_height_m': proposed_height, 'proposed_receiver': receiver, 'unresolved_blocked_receiver_mask': _i10_np.isin(_i10_np.arange(height.size), blocked).reshape(height.shape)}
    events.update({'reassigned_' + name: _i10_np.where(changed, state[name], 0.0) for name in INVENTORIES})
    return {'state': state, 'fluxes': events, 'ledger': {name + '_residual': 0.0 for name in INVENTORIES}, 'metadata': {'algorithm': NETWORK_TRANSITION_ALGORITHM, 'status': 'proposal_requires_explicit_commit', 'dt_s': float(dt_s), 'source_state_sha256': _identity(state), 'previous_graph_sha256': _identity({name: state[name] for name in proposed}), 'proposed_graph_sha256': _identity(proposed), 'world_seed': int(context['world_seed']), 'origin_native_xz': list(context['origin_native_xz']), 'spacing_m': float(context['spacing_m']), 'changed_owner_cells': int(changed.sum()), 'baseline_policy_changed_edges': int(_i10_np.count_nonzero(baseline_receiver != state['receiver'])), 'bed_induced_changed_edges': int(_i10_np.count_nonzero(receiver != baseline_receiver)), 'bed_induced_changed_owner_cells': int(_i10_np.count_nonzero(masks['valid_mask'] & (owners != baseline_owner))), 'routing_policy': context.get('routing_policy', 'strict_candidate'), 'previous_routing_policy': context.get('active_routing_policy', 'delivered_source'), 'routing_policy_transition': bool(_i10_np.any(change) and context.get('active_routing_policy', 'delivered_source') != context.get('routing_policy', 'strict_candidate')), 'limitations': ['finite declared routing-policy comparison after bed change', 'unresolved mask-crossing links stay explicit sinks, not natural outlets', 'first finite-policy commit can include a declared routing-policy change; not attributed solely to bed erosion', 'no long-term natural capture certification']}}

def commit_transition(initial_state, proposal, context):
    """Validate a proposal against the current source and return a copied commit."""
    metadata = proposal['metadata']
    state, _, _ = _bound_state(initial_state, context, metadata['dt_s'])
    if _identity(state) != metadata['source_state_sha256']:
        raise ValueError('stale proposal source state')
    bed_change = proposal['fluxes']['proposed_height_m'] - state['height_m']
    replay = network_transition_step(state, {'bed_change_m': bed_change}, context, metadata['dt_s'])
    if replay['metadata'] != metadata:
        raise ValueError('proposal identity/frame mismatch')
    if set(replay['fluxes']) != set(proposal['fluxes']) or any((not _i10_np.array_equal(value, proposal['fluxes'][name]) for name, value in replay['fluxes'].items())):
        raise ValueError('proposal graph/events mismatch')
    committed = {name: value.copy() for name, value in state.items()}
    committed['height_m'] = replay['fluxes']['proposed_height_m'].copy()
    committed['receiver'] = replay['fluxes']['proposed_receiver'].copy()
    committed['owner_terminal_cell'] = replay['fluxes']['proposed_owner_terminal_cell'].copy()
    return {'state': committed, 'fluxes': replay['fluxes'], 'ledger': replay['ledger'], 'metadata': {**metadata, 'status': 'committed_separate_revision'}}
RADIATION_ALGORITHM = 'environment-fictional-sun-shortwave-v1'

def radiation_initialize(context):
    from terrain_pipeline.environment_contract import grid as _x22_grid
    height, _, _ = _x22_grid(context, 1.0)
    return {'absorbed_energy_j_m2': _i11_np.zeros(height.shape)}

def radiation_step(state, forcing, context, dt_s, parameters=None):
    """Integrate midpoint shortwave; X east and Z north are fictional axes.

    Latitude/longitude are caller-declared fictional degrees, never inferred from
    TD coordinates. Large time intervals need caller substeps for diurnal accuracy.
    """
    from terrain_pipeline.environment_contract import bounded_field as _x21_field
    from terrain_pipeline.environment_contract import grid as _x22_grid
    from terrain_pipeline.environment_contract import positive_parameters as _x23_parameters
    height, spacing, active = _x22_grid(context, dt_s)
    p = _x23_parameters(parameters, {'day_seconds': 86400.0, 'year_days': 365.0, 'solar_constant_w_m2': 1000.0, 'atmospheric_transmission': 0.7, 'evaporation_energy_fraction': 0.3})
    latitude = float(forcing.get('latitude_deg', 35.0))
    longitude = float(forcing.get('longitude_deg', 0.0))
    time = float(forcing.get('time_s', 0.0)) + dt_s / 2
    if not _i11_np.isfinite([latitude, longitude, time]).all() or abs(latitude) > 90 or abs(longitude) > 180:
        raise ValueError('finite declared fictional latitude/longitude/time required')
    if p['atmospheric_transmission'] > 1 or p['evaporation_energy_fraction'] > 1:
        raise ValueError('energy fractions must not exceed one')
    declination = _i11_np.deg2rad(23.44) * _i11_np.sin(2 * _i11_np.pi * time / (p['day_seconds'] * p['year_days']))
    hour = 2 * _i11_np.pi * (time / p['day_seconds'] % 1 - 0.5) + _i11_np.deg2rad(longitude)
    lat = _i11_np.deg2rad(latitude)
    sun = _i11_np.array([-_i11_np.cos(declination) * _i11_np.sin(hour), _i11_np.sin(lat) * _i11_np.sin(declination) + _i11_np.cos(lat) * _i11_np.cos(declination) * _i11_np.cos(hour), _i11_np.cos(lat) * _i11_np.sin(declination) - _i11_np.sin(lat) * _i11_np.cos(declination) * _i11_np.cos(hour)])
    dz = _i11_np.gradient(height, spacing, axis=0) if height.shape[0] > 1 else _i11_np.zeros_like(height)
    dx = _i11_np.gradient(height, spacing, axis=1) if height.shape[1] > 1 else _i11_np.zeros_like(height)
    cosine = _i11_np.maximum(0.0, (-dx * sun[0] + sun[1] - dz * sun[2]) / _i11_np.sqrt(1 + dx * dx + dz * dz))
    shadow = _i11_np.zeros(height.shape, bool)
    if sun[1] > 0:
        horizontal = _i11_np.hypot(sun[0], sun[2])
        if horizontal > 1e-10:
            rows, cols = _i11_np.indices(height.shape)
            for distance in range(1, int(_i11_np.ceil(_i11_np.hypot(*height.shape))) + 1):
                rr = _i11_np.rint(rows + distance * sun[2] / horizontal).astype(int)
                cc = _i11_np.rint(cols + distance * sun[0] / horizontal).astype(int)
                inside = (rr >= 0) & (cc >= 0) & (rr < height.shape[0]) & (cc < height.shape[1])
                r, c = (_i11_np.clip(rr, 0, height.shape[0] - 1), _i11_np.clip(cc, 0, height.shape[1] - 1))
                shadow |= inside & (height[r, c] > height + distance * spacing * sun[1] / horizontal + 1e-09)
    else:
        shadow[:] = True
    albedo = _x21_field(forcing.get('albedo', 0.2), height.shape, 'albedo', 0.0, 1.0)
    incident = _i11_np.where(active & ~shadow, p['solar_constant_w_m2'] * p['atmospheric_transmission'] * cosine, 0.0)
    absorbed = incident * (1 - albedo)
    previous = _x21_field(state['absorbed_energy_j_m2'], height.shape, 'absorbed energy', 0.0)
    evaporation_energy = absorbed * p['evaporation_energy_fraction']
    return {'state': {'absorbed_energy_j_m2': previous + absorbed * dt_s}, 'fluxes': {'absorbed_shortwave_w_m2': absorbed, 'net_ground_heat_w_m2': absorbed - evaporation_energy, 'potential_evaporation_m': evaporation_energy * dt_s / 2450000000.0, 'terrain_shadow_mask': shadow, 'sun_direction_xyz': sun}, 'ledger': {'incident_j': float(incident.sum() * spacing ** 2 * dt_s), 'reflected_j': float((incident * albedo).sum() * spacing ** 2 * dt_s), 'absorbed_j': float(absorbed.sum() * spacing ** 2 * dt_s)}, 'metadata': {'algorithm': RADIATION_ALGORITHM, 'parameters': p, 'latitude_deg': latitude, 'longitude_deg': longitude, 'sun_axes': 'fictional X east Y up Z north', 'source': 'declared fictional solar calendar; uncalibrated', 'units': 'state J/m2; flux W/m2; potential evaporation water metres per step; ledger J; dt seconds', 'limitation': 'shortwave only; no longwave/cloud diffusion; shadow beyond window unknown', 'energy_partition': 'ground plus potential ET; actual ET must cap by water inventory'}}
SOIL_CHEMISTRY_ALGORITHM = 'environment-soil-finite-solutes-v1'
SOIL_CHEMISTRY_PARAMETERS = {'salt_solubility_kg_m3': 350.0, 'stress_half_salinity_kg_m3': 4.0, 'carbon_decay_s': 20.0 * 365.0 * 86400.0}

def initialize_soil_chemistry(context, *, water_depth_m=0.1, salinity_kg_m3=0.0, organic_carbon_kg_m2=1.0, nutrient_kg_m2=0.01, organic_nutrient_kg_m2=0.02):
    from terrain_pipeline.environment_contract import field as _x24_field
    from terrain_pipeline.environment_contract import frame as _x25_frame
    shape, area, masks = _x25_frame(context, 0.0)
    valid = masks['valid_mask']
    water = _x24_field({'v': water_depth_m}, 'v', shape) * area * valid
    salinity = _x24_field({'v': salinity_kg_m3}, 'v', shape)
    if _i12_np.any(salinity > SOIL_CHEMISTRY_PARAMETERS['salt_solubility_kg_m3']):
        raise ValueError('initial dissolved salinity exceeds solubility')
    return {'water_m3': water, 'salt_dissolved_kg': water * salinity, 'salt_solid_kg': _i12_np.zeros(shape), 'organic_carbon_kg': _x24_field({'v': organic_carbon_kg_m2}, 'v', shape) * area * valid, 'organic_nutrient_kg': _x24_field({'v': organic_nutrient_kg_m2}, 'v', shape) * area * valid, 'nutrient_kg': _x24_field({'v': nutrient_kg_m2}, 'v', shape) * area * valid}

def advance_soil_chemistry(state, forcing, context, dt_s):
    from terrain_pipeline.environment_contract import field as _x24_field
    from terrain_pipeline.environment_contract import frame as _x25_frame
    from terrain_pipeline.environment_contract import metadata as _x26_metadata
    from terrain_pipeline.environment_contract import stocks as _x27_stocks
    shape, _, masks = _x25_frame(context, dt_s)
    pools = _x27_stocks(state, ('water_m3', 'salt_dissolved_kg', 'salt_solid_kg', 'organic_carbon_kg', 'organic_nutrient_kg', 'nutrient_kg'), shape)
    active = masks['valid_mask'] & ~masks['protected_mask']
    water_in = _x24_field(forcing, 'water_input_m3_s', shape) * dt_s * active
    concentration = _x24_field(forcing, 'inflow_salinity_kg_m3', shape)
    salt_in = water_in * concentration
    water = pools['water_m3'] + water_in
    dissolved = pools['salt_dissolved_kg'] + salt_in
    solid = pools['salt_solid_kg'].copy()
    equilibrium = _i12_np.where(active & (dt_s > 0.0), _i12_np.minimum(dissolved + solid, water * SOIL_CHEMISTRY_PARAMETERS['salt_solubility_kg_m3']), dissolved)
    solid = dissolved + solid - equilibrium
    dissolved = equilibrium
    drainage = _i12_np.minimum(water, _x24_field(forcing, 'drainage_m3_s', shape) * dt_s * active)
    fraction = _i12_np.divide(drainage, water, out=_i12_np.zeros(shape), where=water > 0.0)
    salt_leached = dissolved * fraction
    dissolved -= salt_leached
    water -= drainage
    evaporation = _i12_np.minimum(water, _x24_field(forcing, 'evaporation_m3_s', shape) * dt_s * active)
    water -= evaporation
    equilibrium = _i12_np.where(active & (dt_s > 0.0), _i12_np.minimum(dissolved + solid, water * SOIL_CHEMISTRY_PARAMETERS['salt_solubility_kg_m3']), dissolved)
    solid = dissolved + solid - equilibrium
    dissolved = equilibrium
    litter = _x24_field(forcing, 'litter_carbon_kg', shape) * active * (dt_s > 0.0)
    carbon = pools['organic_carbon_kg'] + litter
    respiration = carbon * -_i12_np.expm1(-dt_s / SOIL_CHEMISTRY_PARAMETERS['carbon_decay_s']) * active
    carbon -= respiration
    nutrient_in = _x24_field(forcing, 'nutrient_input_kg_s', shape) * dt_s * active
    litter_nutrient = _x24_field(forcing, 'litter_nutrient_kg', shape) * active * (dt_s > 0.0)
    organic_nutrient = pools['organic_nutrient_kg'] + litter_nutrient
    mineralized = organic_nutrient * -_i12_np.expm1(-dt_s / SOIL_CHEMISTRY_PARAMETERS['carbon_decay_s']) * active
    organic_nutrient -= mineralized
    nutrient_return = _x24_field(forcing, 'plant_nutrient_return_kg', shape) * active * (dt_s > 0.0)
    nutrients = pools['nutrient_kg'] + nutrient_in + mineralized + nutrient_return
    nutrient_leached = nutrients * fraction
    nutrients -= nutrient_leached
    demand = _x24_field(forcing, 'plant_uptake_demand_kg', shape) * active * (dt_s > 0.0)
    uptake = _i12_np.minimum(nutrients, demand)
    nutrients -= uptake
    salinity = _i12_np.divide(dissolved, water, out=_i12_np.zeros(shape), where=water > 0.0)
    stress = 1.0 / (1.0 + salinity / SOIL_CHEMISTRY_PARAMETERS['stress_half_salinity_kg_m3'])
    stress = _i12_np.where(water > 0.0, stress, 0.0)
    output = {'water_m3': water, 'salt_dissolved_kg': dissolved, 'salt_solid_kg': solid, 'organic_carbon_kg': carbon, 'organic_nutrient_kg': organic_nutrient, 'nutrient_kg': nutrients}
    ledger = {'water_input_m3': float(water_in.sum()), 'drainage_m3': float(drainage.sum()), 'evaporation_m3': float(evaporation.sum()), 'salt_input_kg': float(salt_in.sum()), 'salt_leached_kg': float(salt_leached.sum()), 'litter_carbon_kg': float(litter.sum()), 'respired_carbon_kg': float(respiration.sum()), 'plant_uptake_kg': float(uptake.sum()), 'nutrient_leached_kg': float(nutrient_leached.sum()), 'nutrient_input_kg': float(nutrient_in.sum()), 'mineralized_nutrient_kg': float(mineralized.sum())}
    ledger['litter_nutrient_kg'] = float(litter_nutrient.sum())
    ledger['plant_nutrient_return_kg'] = float(nutrient_return.sum())
    ledger['water_residual_m3'] = float((pools['water_m3'] + water_in - water - drainage - evaporation).sum())
    ledger['salt_residual_kg'] = float((pools['salt_dissolved_kg'] + pools['salt_solid_kg'] + salt_in - dissolved - solid - salt_leached).sum())
    ledger['carbon_residual_kg'] = float((pools['organic_carbon_kg'] + litter - carbon - respiration).sum())
    ledger['nutrient_residual_kg'] = float((pools['nutrient_kg'] + pools['organic_nutrient_kg'] + nutrient_in + nutrient_return + litter_nutrient - nutrients - organic_nutrient - nutrient_leached - uptake).sum())
    return {'state': output, 'fluxes': {'plant_stress_factor': stress, 'salinity_kg_m3': salinity, 'plant_uptake_kg': uptake, 'salt_leached_kg': salt_leached, 'nutrient_leached_kg': nutrient_leached, 'respired_carbon_kg': respiration, 'drainage_m3': drainage, 'evaporation_m3': evaporation}, 'ledger': ledger, 'metadata': _x26_metadata(SOIL_CHEMISTRY_ALGORITHM, context, dt_s, ['well-mixed account; no pH, alkalinity, ion species or reactive mineral equilibrium', 'finite organic nutrient pool mineralizes with carbon decay; no nutrient species'], SOIL_CHEMISTRY_PARAMETERS.copy())}
SUCCESSION_ALGORITHM = 'environment-succession-carbon-pools-v1'
SUCCESSION_PARAMETERS = {'growth_carbon_kg_m2_s': 2e-08, 'carrying_carbon_kg_m2': 8.0, 'nutrient_kg_per_carbon_kg': 0.02, 'turnover_s': 5.0 * 365.0 * 86400.0, 'char_fraction': 0.15, 'root_cohesion_full_pa': 6000.0, 'bare_manning_n': 0.025, 'vegetated_manning_increment': 0.09}

def initialize_succession(context, *, biomass_carbon_kg_m2=0.0, dead_carbon_kg_m2=0.0):
    from terrain_pipeline.environment_contract import field as _x28_field
    from terrain_pipeline.environment_contract import frame as _x29_frame
    shape, area, masks = _x29_frame(context, 0.0)
    land = masks['valid_mask'] & ~masks['ocean_mask']
    return {'biomass_carbon_kg': _x28_field({'v': biomass_carbon_kg_m2}, 'v', shape) * area * land, 'dead_carbon_kg': _x28_field({'v': dead_carbon_kg_m2}, 'v', shape) * area * land, 'char_carbon_kg': _i13_np.zeros(shape), 'age_s': _i13_np.zeros(shape), 'plant_nutrient_kg': _x28_field({'v': biomass_carbon_kg_m2}, 'v', shape) * area * land * SUCCESSION_PARAMETERS['nutrient_kg_per_carbon_kg'], 'disturbance_fraction': _i13_np.zeros(shape)}

def advance_succession(state, forcing, context, dt_s):
    from terrain_pipeline.environment_contract import field as _x28_field
    from terrain_pipeline.environment_contract import frame as _x29_frame
    from terrain_pipeline.environment_contract import metadata as _x30_metadata
    from terrain_pipeline.environment_contract import stocks as _x31_stocks
    shape, area, masks = _x29_frame(context, dt_s)
    pools = _x31_stocks(state, ('biomass_carbon_kg', 'dead_carbon_kg', 'char_carbon_kg', 'plant_nutrient_kg', 'age_s', 'disturbance_fraction'), shape)
    active = masks['valid_mask'] & ~masks['ocean_mask'] & ~masks['protected_mask']
    if _i13_np.any(pools['disturbance_fraction'] > 1.0):
        raise ValueError('disturbance fraction must be <=1')
    fire_rate = _x28_field(forcing, 'fire_hazard_s', shape)
    mortality_rate = _x28_field(forcing, 'disturbance_hazard_s', shape)
    stress = _x28_field(forcing, 'plant_stress_factor', shape, 1.0)
    moisture = _x28_field(forcing, 'water_available_fraction', shape, 1.0)
    if _i13_np.any(stress > 1.0) or _i13_np.any(moisture > 1.0):
        raise ValueError('stress and water fractions must be <=1')
    temperature = _x28_field(forcing, 'temperature_c', shape, 20.0, nonnegative=False)
    fire_fraction = -_i13_np.expm1(-fire_rate * dt_s) * active
    burned_live = pools['biomass_carbon_kg'] * fire_fraction
    burned_dead = pools['dead_carbon_kg'] * fire_fraction
    burned = burned_live + burned_dead
    char = burned * SUCCESSION_PARAMETERS['char_fraction']
    atmosphere = burned - char
    live = pools['biomass_carbon_kg'] - burned_live
    dead = pools['dead_carbon_kg'] - burned_dead
    mortality = live * -_i13_np.expm1(-mortality_rate * dt_s) * active
    live -= mortality
    dead += mortality
    turnover = live * -_i13_np.expm1(-dt_s / SUCCESSION_PARAMETERS['turnover_s']) * active
    live -= turnover
    litter = dead * -_i13_np.expm1(-dt_s / (365.0 * 86400.0)) * active + turnover
    dead -= litter - turnover
    capacity = area * SUCCESSION_PARAMETERS['carrying_carbon_kg_m2']
    thermal = _i13_np.clip(1.0 - _i13_np.abs(temperature - 20.0) / 25.0, 0.0, 1.0)
    potential = area * SUCCESSION_PARAMETERS['growth_carbon_kg_m2_s'] * dt_s * thermal * moisture * stress * _i13_np.clip(1.0 - live / capacity, 0.0, 1.0) * active
    potential = _i13_np.minimum(potential, _i13_np.maximum(capacity - live, 0.0))
    uptake = _x28_field(forcing, 'plant_nutrient_uptake_kg', shape) * (dt_s > 0.0)
    growth = _i13_np.minimum(potential, uptake / SUCCESSION_PARAMETERS['nutrient_kg_per_carbon_kg'])
    assimilated = growth * SUCCESSION_PARAMETERS['nutrient_kg_per_carbon_kg']
    released_fraction = _i13_np.divide(burned + litter, pools['biomass_carbon_kg'] + pools['dead_carbon_kg'], out=_i13_np.zeros(shape), where=pools['biomass_carbon_kg'] + pools['dead_carbon_kg'] > 0.0)
    released_nutrient = pools['plant_nutrient_kg'] * _i13_np.minimum(released_fraction, 1.0)
    nutrient_return = uptake - assimilated + released_nutrient
    live += growth
    disturbance = _i13_np.maximum(fire_fraction, -_i13_np.expm1(-mortality_rate * dt_s) * active)
    remembered = _i13_np.maximum(pools['disturbance_fraction'] * _i13_np.exp(-dt_s / (365.0 * 86400.0)), disturbance)
    remembered = _i13_np.where(active, remembered, pools['disturbance_fraction'])
    age = _i13_np.where(active, (pools['age_s'] + dt_s) * (1.0 - disturbance), pools['age_s'])
    cover = _i13_np.clip(live / capacity, 0.0, 1.0)
    output = {'biomass_carbon_kg': live, 'dead_carbon_kg': dead, 'char_carbon_kg': pools['char_carbon_kg'] + char, 'plant_nutrient_kg': pools['plant_nutrient_kg'] + assimilated - released_nutrient, 'age_s': age, 'disturbance_fraction': remembered}
    initial = sum((float(pools[k].sum()) for k in ('biomass_carbon_kg', 'dead_carbon_kg', 'char_carbon_kg')))
    final = sum((float(output[k].sum()) for k in ('biomass_carbon_kg', 'dead_carbon_kg', 'char_carbon_kg')))
    ledger = {'initial_carbon_kg': initial, 'photosynthesis_carbon_kg': float(growth.sum()), 'fire_atmosphere_carbon_kg': float(atmosphere.sum()), 'soil_litter_carbon_kg': float(litter.sum()), 'final_carbon_kg': final}
    ledger['carbon_residual_kg'] = initial + ledger['photosynthesis_carbon_kg'] - final - float((atmosphere + litter).sum())
    ledger['nutrient_input_kg'] = float(uptake.sum())
    ledger['soil_nutrient_return_kg'] = float(nutrient_return.sum())
    ledger['nutrient_residual_kg'] = float((pools['plant_nutrient_kg'] + uptake - output['plant_nutrient_kg'] - nutrient_return).sum())
    return {'state': output, 'fluxes': {'photosynthesis_carbon_kg': growth, 'fire_atmosphere_carbon_kg': atmosphere, 'litter_carbon_kg': litter, 'nutrient_assimilated_kg': assimilated, 'plant_nutrient_return_kg': nutrient_return, 'cover_fraction': cover, 'root_cohesion_pa': cover * SUCCESSION_PARAMETERS['root_cohesion_full_pa'], 'manning_n': SUCCESSION_PARAMETERS['bare_manning_n'] + cover * SUCCESSION_PARAMETERS['vegetated_manning_increment']}, 'ledger': ledger, 'metadata': _x30_metadata(SUCCESSION_ALGORITHM, context, dt_s, ['declared functional vegetation, no species competition or fire spread; explicit hazards', 'nutrient uptake must be debited once from the soil process; carbon litter returned once'], SUCCESSION_PARAMETERS.copy())}
VOLCANISM_ALGORITHM = 'environment-event-lava-ash-cooling-v1'

def volcanism_initialize(context):
    from terrain_pipeline.environment_contract import grid as _x33_grid
    height, _, _ = _x33_grid(context, 1.0)
    return {key: _i14_np.zeros(height.shape) for key in ('mobile_lava_m3', 'lava_heat_j', 'airborne_ash_m3', 'deposited_lava_m3', 'deposited_ash_m3')}

def volcanism_step(state, forcing, context, dt_s, parameters=None):
    from terrain_pipeline.drainage import segments_clear as _i14_segments_clear
    from terrain_pipeline.environment_contract import bounded_field as _x32_field
    from terrain_pipeline.environment_contract import grid as _x33_grid
    from terrain_pipeline.environment_contract import positive_parameters as _x34_parameters
    height, spacing, active = _x33_grid(context, dt_s)
    p = _x34_parameters(parameters, {'lava_heat_j_m3': 2000000000.0, 'cooling_time_s': 3600.0, 'lava_speed_m_s': 0.05, 'ash_settling_time_s': 1800.0, 'ash_solid_fraction': 0.5})
    if p['ash_solid_fraction'] > 1:
        raise ValueError('ash solid fraction must not exceed one')
    old = {key: _x32_field(state[key], height.shape, key, 0.0) for key in volcanism_initialize(context)}
    lava_input = _x32_field(forcing.get('lava_input_m3', 0.0), height.shape, 'lava input', 0.0)
    ash_input = _x32_field(forcing.get('ash_input_m3', 0.0), height.shape, 'ash input', 0.0)
    if _i14_np.any((lava_input + ash_input)[~active] != 0):
        raise ValueError('eruption input requires unprotected valid source')
    lava = old['mobile_lava_m3'] + lava_input
    heat = old['lava_heat_j'] + lava_input * p['lava_heat_j_m3']
    receiver = _i14_np.asarray(context['receiver'])
    if receiver.size != height.size or receiver.dtype.kind not in 'iu' or _i14_np.any(receiver < -1) or _i14_np.any(receiver >= height.size):
        raise ValueError('explicit finite graph receivers required')
    receiver = receiver.reshape(-1)
    source = _i14_np.flatnonzero((receiver >= 0) & active.ravel())
    target = receiver[source]
    legal = active.ravel()[target] & (height.ravel()[source] > height.ravel()[target])
    legal &= _i14_segments_clear(source, target, active)
    source, target = (source[legal], target[legal])
    if 'node_x_m' in context and 'node_z_m' in context:
        x = _x32_field(_i14_np.asarray(context['node_x_m']).reshape(height.shape), height.shape, 'node x').ravel()
        z = _x32_field(_i14_np.asarray(context['node_z_m']).reshape(height.shape), height.shape, 'node z').ravel()
        length = _i14_np.hypot(x[source] - x[target], z[source] - z[target])
    else:
        length = spacing * _i14_np.hypot(source % height.shape[1] - target % height.shape[1], source // height.shape[1] - target // height.shape[1])
    if _i14_np.any(length <= 0):
        raise ValueError('lava edge requires positive metric length')
    fraction = _i14_np.minimum(1.0, p['lava_speed_m_s'] * dt_s / length)
    moved = lava.ravel()[source] * fraction
    moved_heat = heat.ravel()[source] * fraction
    lava.ravel()[source] -= moved
    heat.ravel()[source] -= moved_heat
    _i14_np.add.at(lava.ravel(), target, moved)
    _i14_np.add.at(heat.ravel(), target, moved_heat)
    cooling = _i14_np.where(active, -_i14_np.expm1(-dt_s / p['cooling_time_s']), 0.0)
    solidified = lava * cooling
    released_heat = heat * cooling
    ash = old['airborne_ash_m3'] + ash_input
    ash_transport = aeolian_step({'loose_solid_m3': _i14_np.zeros_like(ash), 'airborne_solid_m3': ash}, {'wind_x_m_s': forcing.get('wind_x_m_s', 0.0), 'wind_z_m_s': forcing.get('wind_z_m_s', 0.0)}, context, dt_s, {'settling_time_s': p['ash_settling_time_s']})
    ash_deposit = ash_transport['fluxes']['deposited_solid_m3']
    ash_export = ash_transport['fluxes']['boundary_export_solid_m3']
    new = {'mobile_lava_m3': lava - solidified, 'lava_heat_j': heat - released_heat, 'airborne_ash_m3': ash_transport['state']['airborne_solid_m3'], 'deposited_lava_m3': old['deposited_lava_m3'] + solidified, 'deposited_ash_m3': old['deposited_ash_m3'] + ash_deposit}
    geothermal = _x32_field(forcing.get('geothermal_w_m2', 0.0), height.shape, 'geothermal', 0.0)
    geothermal = _i14_np.where(active, geothermal, 0.0)
    mass_keys = ('mobile_lava_m3', 'airborne_ash_m3', 'deposited_lava_m3', 'deposited_ash_m3')
    initial_mass = sum((float(old[key].sum()) for key in mass_keys))
    final_mass = sum((float(new[key].sum()) for key in mass_keys))
    return {'state': new, 'fluxes': {'solidified_lava_m3': solidified, 'deposited_ash_solid_m3': ash_deposit, 'height_change_m': (solidified + ash_deposit / p['ash_solid_fraction']) / spacing ** 2, 'lava_transport_solid_m3': _i14_np.bincount(source, weights=moved, minlength=height.size).reshape(height.shape), 'ash_boundary_export_solid_m3': ash_export, 'geothermal_heat_w_m2': geothermal + released_heat / (spacing ** 2 * dt_s)}, 'ledger': {'event_input_solid_m3': float((lava_input + ash_input).sum()), 'initial_solid_m3': initial_mass, 'final_solid_m3': final_mass, 'boundary_export_solid_m3': float(ash_export.sum()), 'solid_residual_m3': final_mass + float(ash_export.sum()) - initial_mass - float((lava_input + ash_input).sum()), 'cooling_heat_j': float(released_heat.sum()), 'heat_residual_j': float(new['lava_heat_j'].sum() + released_heat.sum() - old['lava_heat_j'].sum() - lava_input.sum() * p['lava_heat_j_m3']), 'geothermal_external_j': float(geothermal.sum() * spacing ** 2 * dt_s)}, 'metadata': {'algorithm': VOLCANISM_ALGORITHM, 'parameters': p, 'source': 'explicit declared eruption and external geothermal scenario; uncalibrated', 'units': 'lava/ash m3 solid per cell; stored heat J per cell; geothermal W/m2; terrain delta metres bulk; dt seconds', 'coordinates': 'context graph nodes when supplied, otherwise native anchors', 'ash_transport': 'shared finite wind transport and settling; no ash re-entrainment in this module', 'lava_boundary': 'terminal lava retained and cooled; no fictitious open lava outlet', 'limitation': 'surface cooling/deposition only; no plume aerodynamics, magma intrusion mechanics or 3D lava tubes'}}
_PROCESS_FUNCTIONS = {'radiation': (radiation_initialize, radiation_step, True), 'frozen_ground': (frozen_ground_initialize, frozen_ground_step, True), 'volcanism': (volcanism_initialize, volcanism_step, True), 'aeolian': (aeolian_initialize, aeolian_step, True), 'groundwater': (groundwater_initial_state, groundwater_step, False), 'mass': (mass_initial_state, mass_step, False), 'network_transition': (network_transition_initial_state, network_transition_step, False), 'coastal_exchange': (initialize_coastal_exchange, advance_coastal_exchange, False), 'habitat': (initialize_habitat, advance_habitat, False), 'soil_chemistry': (initialize_soil_chemistry, advance_soil_chemistry, False), 'succession': (initialize_succession, advance_succession, False)}
