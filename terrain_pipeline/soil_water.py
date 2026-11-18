"""Consolidated soil_water implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import asdict as _i26_asdict
from dataclasses import dataclass as _i26_dataclass
from dataclasses import field as _i26_field
from dataclasses import replace as _i26_replace
import hashlib as _i26_hashlib
import importlib as _i26_importlib
import json as _i26_json
import math as _i26_math
from pathlib import Path as _i26_Path
import numpy as _i26_np
from terrain_pipeline.runoff import RunoffParameters as _i26_RunoffParameters
import math as _i27_math
import numpy as _i27_np
from dataclasses import dataclass as _i28_dataclass
import hashlib as _i28_hashlib
import json as _i28_json
import math as _i28_math
import numpy as _i28_np
from dataclasses import asdict as _i29_asdict
from dataclasses import dataclass as _i29_dataclass
from dataclasses import field as _i29_field
import math as _i29_math
import numpy as _i29_np
from copy import deepcopy as _i30_deepcopy
from dataclasses import asdict as _i30_asdict
from dataclasses import replace as _i30_replace
import math as _i30_math
import numpy as _i30_np
import dataclasses as _i31_dataclasses
import math as _i31_math
from dataclasses import dataclass as _i31_dataclass
from typing import Any as _i31_Any
from typing import Callable as _i31_Callable
from typing import Dict as _i31_Dict
from typing import Optional as _i31_Optional
import numpy as _i31_np
from copy import deepcopy as _i32_deepcopy
import numpy as _i32_np
from dataclasses import asdict as _i33_asdict
import json as _i33_json
import os as _i33_os
from pathlib import Path as _i33_Path
import time as _i33_time
import numpy as _i33_np
from numba import njit as _i33_njit
from scipy.ndimage import map_coordinates as _i33_map_coordinates
CATEGORY = 'D'
PET_ET_ALGORITHM = 'pet-et-adapter-v1'
PET_ET_SCHEMA = 'metric-pet-et-v1'
PHASE_SCHEMA = 'declared-freezing-threshold-v1'
CHECKPOINT_SCHEMA = 'metric-pet-et-checkpoint-v1'
PET_PARAMETER_SCHEMA = 'metric-pet-parameters-v1'
BUCKET_MODULE = 'terrain_pipeline.climate_forcing.advance_soil'
_IDENTITY_MODULES = (('terrain_pipeline.soil_water', 'soil_water.py'), ('terrain_pipeline.climate_forcing', 'climate_forcing.py'), ('terrain_pipeline.runoff', 'runoff.py'))
SEASONAL_SOURCE_PATH = 'terrain_pipeline/hydrology_seasonal.py'
SEASONAL_SOURCE_SHA256 = '43f07b683a40c5e9bb1afe5440bda63e131744fbb68e7af4623d44ea770a1e05'
SEASONAL_PET_LINE = 74
SEASONAL_PET_EXPRESSION = 'potential_et_mm = pet_base_mm_per_day + pet_temperature_mm_per_day_c * np.maximum(temperature, 0)'
PET_ET_PHASE_SOURCE = "reuses the semantics of metric_climate_refinement.SNOW_LINE_CRITERION ('monthly_mean_temperature_below_zero_celsius'); that constant is a string, not a phase function, so the numeric threshold is an explicit parameter"
PHASE_SEMANTICS = 'declared_monthly_mean_threshold_not_daily_phase'
NOT_AVAILABLE = 'not_available'
NOT_MODELED = 'not_modeled'
SUBSTEP_POLICY = "the bucket is advanced once per calendar piece of the interval (month and year edges), each piece with that month's own PET rate and its own phase decision; the requested interval only aggregates the per-piece outputs. An interval that straddles a month edge under a supply limit is therefore equal to running the pieces separately, which is asserted by the tests. No daily or diurnal variation is introduced"
SUBSTEP_STATUS = 'substepped_at_calendar_edges'
PET_ET_TEMPERATURE_SOURCES = ('caller_declared_monthly_mean', 'g3_monthly_mean', 'a1_published_monthly_mean')
RAIN_SOURCES = ('declared_event', 'background_estimate')
PET_ET_MAX_CELLS = 4096
MAX_INTERVALS = 8760
SUBSTEP_WORST_CASE_PER_INTERVAL = 2
MAX_CELL_INTERVALS = 2000000
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
INTERVAL_FLOAT_FIELDS = ('rain_mm', 'liquid_rate_mm_h', 'liquid_rain_mm', 'solid_precipitation_swe_mm', 'liquid_fraction', 'interval_pet_mm', 'pet_rate_mm_h', 'actual_et_mm', 'release_mm', 'subsurface_transfer_mm', 'infiltration_mm', 'storage_change_mm', 'available_supply_mm')
EDGE_FLOAT_FIELDS = ('soil_edge_mm', 'fast_edge_mm', 'slow_edge_mm')
INTERVAL_INT_FIELDS = ('substeps_per_interval',)
MONTHLY_FLOAT_FIELDS = ('monthly_temperature_c', 'monthly_potential_et_mm', 'calendar_month_seconds')
REGIME_FIELD = 'et_regime'
REGIME_WIDTH = 16
PET_ET_LIMITATIONS = ('PET/ET adapter only: it copies no bucket and no PET formula, it drives regional_surface_forcing.advance_soil with an exact per-cell scalar PET rate.', "available_water from metric_soil_condition is never used as storage and never used as actual ET; storage is the bucket's own soil/fast/slow states.", 'monthly precipitation totals are never turned into a single storm event; the caller must declare interval-average rain on explicit physical time edges.', 'solid_precipitation_swe_mm is an equivalent water depth of withheld solid input, not a snow depth (no density) and not a snowpack state.', 'slow is an internal store fed by percolation; it is not an aquifer and its release is not a groundwater baseflow.', 'no channel, no routing, no boundary condition and no natural-outlet claim.', 'the PET parameters are declared engineering assumptions reused from SeasonalConfig; they are not calibrated and this module reports no Hargreaves or FAO comparison.', 'RunoffParameters.initial_soil_mm/initial_fast_mm/initial_slow_mm are ignored: the initial states are the explicit ``states`` argument.')

@_i26_dataclass(frozen=True)
class PetEtParameters:
    """PET parameters (reused from ``SeasonalConfig``) plus the declared phase threshold.

    ``runoff`` carries the bucket parameters. Its ``potential_et_mm_h`` is
    **overridden per group** at call time with the exact per-cell PET rate; keeping
    the field here only means the other six bucket parameters are stated in one
    place and enter the model identity.
    """
    pet_base_mm_per_day: float = 0.5
    pet_temperature_mm_per_day_c: float = 0.12
    freezing_threshold_c: float = 0.0
    runoff: _i26_RunoffParameters = _i26_field(default_factory=_i26_RunoffParameters)

    def __post_init__(self):
        for name in ('pet_base_mm_per_day', 'pet_temperature_mm_per_day_c'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i26_math.isfinite(value)) or (value < 0.0):
                raise ValueError('invalid %s: a finite nonnegative number is required' % (name,))
        threshold = self.freezing_threshold_c
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or (not _i26_math.isfinite(threshold)):
            raise ValueError('invalid freezing_threshold_c: a finite number is required')
        if not isinstance(self.runoff, _i26_RunoffParameters):
            raise ValueError('runoff must be a RunoffParameters instance')
        self.runoff.__post_init__()

    @property
    def pet_parameter_identity_sha256(self):
        return pet_parameter_identity(self)

def parameters_from_seasonal_config(climate, runoff=None, *, freezing_threshold_c=0.0):
    """Read the existing PET **parameters** from a ``SeasonalConfig``.

    Only the two parameter values are read. ``seasonal_climate`` is never called:
    it resamples the v1 climate internally, which would replace the caller's v2/G3
    monthly temperature with a v1 one.
    """
    from terrain_pipeline.runoff import SeasonalConfig as _i26_SeasonalConfig
    if not isinstance(climate, _i26_SeasonalConfig):
        raise ValueError('a SeasonalConfig instance is required')
    return PetEtParameters(pet_base_mm_per_day=float(climate.pet_base_mm_per_day), pet_temperature_mm_per_day_c=float(climate.pet_temperature_mm_per_day_c), freezing_threshold_c=freezing_threshold_c, runoff=_i26_RunoffParameters() if runoff is None else runoff)

def _canonical(payload):
    return _i26_json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)

def _digest(payload):
    return _i26_hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()

def _array_digest(array):
    values = _i26_np.ascontiguousarray(_i26_np.asarray(array))
    hasher = _i26_hashlib.sha256()
    hasher.update(str(values.shape).encode('ascii'))
    hasher.update(values.dtype.str.encode('ascii'))
    hasher.update(values.tobytes(order='C'))
    return hasher.hexdigest()

def _points_digest(x_m, z_m):
    """Order-, shape- and window-independent digest of the world point set."""
    x = _i26_np.asarray(x_m, _i26_np.float64).reshape(-1)
    z = _i26_np.asarray(z_m, _i26_np.float64).reshape(-1)
    return _array_digest(_i26_np.stack((x[_point_order(x, z)], z[_point_order(x, z)])))

def _point_order(x_m, z_m):
    """Canonical cell order: sort by ``(x, z)`` so identity is order independent."""
    x = _i26_np.asarray(x_m, _i26_np.float64).reshape(-1)
    z = _i26_np.asarray(z_m, _i26_np.float64).reshape(-1)
    return _i26_np.lexsort((z, x))

def _ordered_digest(array, order, axis):
    """Digest an array after putting its cells in canonical point order."""
    values = _i26_np.asarray(array, _i26_np.float64)
    return _array_digest(_i26_np.take(values, order, axis=axis))

def _source_identities():
    """Module-byte identities of this adapter and the frozen cores it drives.

    ``model_identity`` must bind the actual code, not only a module **name**: two
    different builds of ``advance_soil`` would otherwise share an identity. Computed
    once per process and memoised, so repeated identity calls do not re-read the same
    five files.
    """
    cached = getattr(_source_identities, '_cache', None)
    if cached is not None:
        return cached
    identities = {}
    for module_name, basename in _IDENTITY_MODULES:
        module = _i26_importlib.import_module(module_name)
        path = getattr(module, '__file__', None)
        if path is None:
            raise ValueError('no source file for %r' % (module_name,))
        with open(path, 'rb') as stream:
            identities[module_name] = {'basename': basename, 'source_sha256': _i26_hashlib.sha256(stream.read()).hexdigest()}
    _source_identities._cache = identities
    return identities

def pet_parameter_identity(parameters=None):
    """Identity of the PET parameters **only** (bucket parameters do not enter).

    Changing any ``RunoffParameters`` field other than the PET override must leave
    this digest unchanged; :func:`model_identity` is the place where everything is
    bound together.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError('PetEtParameters required')
    return _digest({'schema': PET_PARAMETER_SCHEMA, 'pet_base_mm_per_day': params.pet_base_mm_per_day, 'pet_temperature_mm_per_day_c': params.pet_temperature_mm_per_day_c, 'freezing_threshold_c': params.freezing_threshold_c, 'expression': {'path': SEASONAL_SOURCE_PATH, 'sha256': SEASONAL_SOURCE_SHA256, 'line': SEASONAL_PET_LINE, 'form': SEASONAL_PET_EXPRESSION}})

def model_identity(*, parameters, x_m, z_m, time_edges_s, states, monthly_temperature_c, rain_mm_h, spacing_m, temperature_source, rain_source):
    """Identity binding points, forcing, time edges, initial states and all parameters."""
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError('PetEtParameters required')
    x = _i26_np.asarray(x_m, _i26_np.float64).reshape(-1)
    z = _i26_np.asarray(z_m, _i26_np.float64).reshape(-1)
    if x.size != z.size:
        raise ValueError('x_m and z_m must have the same number of points')
    order = _point_order(x, z)
    return _digest({'schema': PET_ET_SCHEMA, 'algorithm': PET_ET_ALGORITHM, 'pet_parameter_identity_sha256': pet_parameter_identity(params), 'bucket': {'module': BUCKET_MODULE, 'parameters': _i26_asdict(params.runoff), 'pet_realisation': 'exact per-cell scalar grouping: RunoffParameters.potential_et_mm_h is replaced inside each group; no averaging, no bucketing', 'ignored_initial_fields': ['initial_soil_mm', 'initial_fast_mm', 'initial_slow_mm']}, 'code_identities': _source_identities(), 'spacing_m': float(spacing_m), 'temperature_source': temperature_source, 'rain_source': rain_source, 'cell_order': 'canonical lexsort by (x_m, z_m): identity is order independent', 'points_sha256': _points_digest(x, z), 'time_edges_sha256': _array_digest(_i26_np.asarray(time_edges_s, _i26_np.float64)), 'initial_states_sha256': _ordered_digest(states, order, axis=1), 'monthly_temperature_sha256': _ordered_digest(monthly_temperature_c, order, axis=1), 'rain_mm_h_sha256': _ordered_digest(rain_mm_h, order, axis=1)})

def pet_et_preflight(cells, intervals):
    """Compute the whole budget before allocating anything.

    The worst case for the number of bucket calls is ``cells * intervals`` (one
    group per cell per interval, i.e. every cell has a distinct PET rate). That is
    the number this gate bounds, because no averaging or coarse re-bucketing of the
    PET rate is permitted.
    """
    if isinstance(cells, bool) or not isinstance(cells, int) or (not 1 <= cells <= PET_ET_MAX_CELLS):
        raise ValueError('cells outside 1..%d' % (PET_ET_MAX_CELLS,))
    if isinstance(intervals, bool) or not isinstance(intervals, int) or (not 1 <= intervals <= MAX_INTERVALS):
        raise ValueError('intervals outside 1..%d' % (MAX_INTERVALS,))
    work = cells * intervals
    if work > MAX_CELL_INTERVALS:
        raise ValueError('cell-interval work %d exceeds %d; a longer run must be chunked and its output sampled, not claimed as a full step-by-step product' % (work, MAX_CELL_INTERVALS))
    interval_bytes = (len(INTERVAL_FLOAT_FIELDS) * 8 + 4 * REGIME_WIDTH) * work
    edge_bytes = len(EDGE_FLOAT_FIELDS) * 8 * (intervals + 1) * cells
    int_bytes = len(INTERVAL_INT_FIELDS) * 8 * intervals
    monthly_bytes = len(MONTHLY_FLOAT_FIELDS) * 8 * 12 * cells
    inventory_bytes = 8 * (intervals + 1)
    estimated = interval_bytes + edge_bytes + int_bytes + monthly_bytes + inventory_bytes
    if estimated > MAX_OUTPUT_BYTES:
        raise ValueError('estimated output %d bytes exceeds %d' % (estimated, MAX_OUTPUT_BYTES))
    return {'cells': cells, 'intervals': intervals, 'cell_intervals': work, 'max_bucket_calls': work * SUBSTEP_WORST_CASE_PER_INTERVAL, 'estimated_output_bytes': estimated, 'max_cells': PET_ET_MAX_CELLS, 'max_intervals': MAX_INTERVALS, 'max_cell_intervals': MAX_CELL_INTERVALS, 'max_output_bytes': MAX_OUTPUT_BYTES, 'bucket_gate': 'regional_surface_forcing.preflight(cells, intervals, block_cells, dt_s) also bounds cells*intervals at MAX_CELL_STEPS=25000000 and dt_s at 3600 s'}

def _pet_daily_mm(temperature_c, parameters):
    """The one expression: existing temperature-index PET, in mm per day.

    Synonymous with ``terrain_pipeline/runoff.py:74`` (see
    :data:`SEASONAL_PET_EXPRESSION` and :data:`SEASONAL_SOURCE_SHA256`). The two
    parameters are read from :class:`SeasonalConfig` through
    :class:`PetEtParameters`; the arithmetic is the original arithmetic, so the two
    derived quantities below keep the original operation order.
    """
    return parameters.pet_base_mm_per_day + parameters.pet_temperature_mm_per_day_c * _i26_np.maximum(temperature_c, 0.0)

def temperature_index_pet_rate_mm_h(temperature_c, parameters=None):
    """Existing temperature-index PET in **mm/hour** (the only unit conversion).

    Equal to the mm/day expression divided by 24. Negative temperature contributes
    nothing beyond the base rate, exactly as ``np.maximum(temperature, 0)`` in the
    original; the four PET parameters are never refitted here.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError('PetEtParameters required')
    temperature = _i26_np.asarray(temperature_c, _i26_np.float64)
    if not _i26_np.isfinite(temperature).all():
        raise ValueError('finite monthly temperature required')
    return _pet_daily_mm(temperature, params) / 24.0

def monthly_potential_et_mm(monthly_temperature_c, parameters=None):
    """``(12, N)`` monthly PET depth, same operation order as the original.

    ``daily_mm_per_day * MONTH_DAYS`` is exactly ``seasonal_climate`` line 76
    (``pet * MONTH_DAYS``), so an equivalence test can compare bit for bit. It is the
    monthly depth, **not** an interval depth: interval depths are integrated on the
    real calendar by :func:`interval_pet_mm`.
    """
    from terrain_pipeline.climate_forcing import MONTH_DAYS as _x44_MONTH_DAYS
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    temperature = _i26_np.asarray(monthly_temperature_c, _i26_np.float64)
    if temperature.ndim < 2 or temperature.shape[0] != 12:
        raise ValueError('monthly_temperature_c must be [12, ...]')
    if not _i26_np.isfinite(temperature).all():
        raise ValueError('finite monthly temperature required')
    days = _x44_MONTH_DAYS.reshape((12,) + (1,) * (temperature.ndim - 1))
    return _pet_daily_mm(temperature, params) * days

def _month_index(seconds_in_year):
    from terrain_pipeline.climate_forcing import MONTH_EDGES_S as _x45_MONTH_EDGES_S
    index = int(_i26_np.searchsorted(_x45_MONTH_EDGES_S, seconds_in_year, side='right') - 1)
    return min(11, max(0, index))

def _split_interval(start_s, end_s):
    """Split ``[start_s, end_s)`` on the real 365-day calendar into month pieces."""
    from terrain_pipeline.climate_forcing import MONTH_EDGES_S as _x45_MONTH_EDGES_S
    from terrain_pipeline.climate_forcing import YEAR_S as _x46_YEAR_S
    pieces = []
    lower = float(start_s)
    upper_bound = float(end_s)
    while lower < upper_bound:
        year = _i26_math.floor(lower / _x46_YEAR_S)
        in_year = lower - year * _x46_YEAR_S
        month = _month_index(in_year)
        month_end = year * _x46_YEAR_S + float(_x45_MONTH_EDGES_S[month + 1])
        upper = min(upper_bound, month_end)
        if not upper > lower:
            raise ValueError('degenerate calendar split at %.17g s: the interval edges do not advance on the declared 365-day calendar' % (lower,))
        pieces.append((month, upper - lower))
        lower = upper
    return pieces

def calendar_month_seconds(time_edges_s):
    """``(T, 12)`` seconds each interval actually spends inside each calendar month."""
    edges = _validate_edges(time_edges_s)
    result = _i26_np.zeros((edges.size - 1, 12), _i26_np.float64)
    for index in range(edges.size - 1):
        for month, seconds in _split_interval(edges[index], edges[index + 1]):
            result[index, month] += seconds
    return result

def interval_pet_mm(monthly_temperature_c, time_edges_s, parameters=None):
    """``(T, N)`` interval-average PET depth, integrated across month/year edges.

    Monthly mean temperature is the declared input; it repeats every year on the
    declared calendar (365 days, no leap day, the same convention as
    ``metric_noise_forcing.MONTH_EDGES_S``). An interval that spans a month boundary
    is integrated month by month, so the depth is never assigned to a single month.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError('PetEtParameters required')
    temperature = _i26_np.asarray(monthly_temperature_c, _i26_np.float64)
    if temperature.ndim != 2 or temperature.shape[0] != 12:
        raise ValueError('monthly_temperature_c must be [12, N]')
    if not _i26_np.isfinite(temperature).all():
        raise ValueError('finite monthly temperature required')
    edges = _validate_edges(time_edges_s)
    rate_by_month = temperature_index_pet_rate_mm_h(temperature, params)
    depth = _i26_np.zeros((edges.size - 1, temperature.shape[1]), _i26_np.float64)
    for index in range(edges.size - 1):
        for month, seconds in _split_interval(edges[index], edges[index + 1]):
            depth[index] += rate_by_month[month] * (seconds / 3600.0)
    return depth

def liquid_fraction(monthly_temperature_c, month_seconds, parameters=None):
    """``(T, N)`` liquid fraction of the declared precipitation.

    The only criterion is the declared monthly-mean threshold
    (:data:`PHASE_SOURCE`): a month whose mean is **strictly below** the threshold
    contributes solid, at or above it contributes liquid. When an interval spans a
    month boundary the fraction is the elapsed-time-weighted mixture of the two, and
    that mixture is declared, not fitted. This is an approximation from a monthly
    mean, never a daily or hourly phase, and it does not build a snowpack.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    temperature = _i26_np.asarray(monthly_temperature_c, _i26_np.float64)
    if temperature.ndim != 2 or temperature.shape[0] != 12:
        raise ValueError('monthly_temperature_c must be [12, N]')
    seconds = _i26_np.asarray(month_seconds, _i26_np.float64)
    if seconds.ndim != 2 or seconds.shape[1] != 12:
        raise ValueError('month_seconds must be [T, 12]')
    if seconds.shape[0] != 0 and (not _i26_np.isfinite(seconds).all() or _i26_np.any(seconds < 0)):
        raise ValueError('finite nonnegative month seconds required')
    liquid = (temperature >= params.freezing_threshold_c).astype(_i26_np.float64)
    total = seconds.sum(axis=1)
    weighted = seconds @ liquid
    fraction = _i26_np.zeros(weighted.shape, _i26_np.float64)
    _i26_np.divide(weighted, total[:, None], out=fraction, where=total[:, None] > 0.0)
    if total.shape[0] and _i26_np.any(total <= 0.0):
        raise ValueError('every interval must spend positive time inside the calendar')
    return _i26_np.clip(fraction, 0.0, 1.0)

def _validate_edges(time_edges_s):
    edges = _i26_np.asarray(time_edges_s, _i26_np.float64)
    if edges.ndim != 1 or edges.size < 2:
        raise ValueError('time_edges_s must be a one-dimensional array of at least 2 edges')
    if not _i26_np.isfinite(edges).all():
        raise ValueError('finite physical time edges required')
    if edges[0] < 0.0:
        raise ValueError('time edges must be nonnegative physical seconds')
    if _i26_np.any(_i26_np.diff(edges) <= 0.0):
        raise ValueError('strictly increasing time edges required')
    longest = float(_i26_np.max(_i26_np.diff(edges)))
    if longest > 3600.0:
        raise ValueError('the bucket only accepts dt_s <= 3600 s; the longest declared interval is %.17g s, so refine the interval edges instead of widening the gate' % (longest,))
    return edges

def _validate_coordinates(x_m, z_m, cells):
    x = _i26_np.asarray(x_m, _i26_np.float64).reshape(-1)
    z = _i26_np.asarray(z_m, _i26_np.float64).reshape(-1)
    if x.size != cells or z.size != cells:
        raise ValueError('x_m and z_m must each provide one coordinate per cell')
    if not _i26_np.isfinite(x).all() or not _i26_np.isfinite(z).all():
        raise ValueError('finite absolute world coordinates required')
    if max(float(_i26_np.max(_i26_np.abs(x))), float(_i26_np.max(_i26_np.abs(z)))) > 1000000000000.0:
        raise ValueError('bounded absolute world coordinates required')
    return (x, z)

def _validate_states(states, cells, parameters):
    array = _i26_np.asarray(states, _i26_np.float64)
    if array.ndim != 2 or array.shape != (3, cells):
        raise ValueError('states must be a float64 [3, N] block')
    if not _i26_np.isfinite(array).all():
        raise ValueError('finite initial soil/fast/slow states required')
    if _i26_np.any(array < 0.0):
        raise ValueError('nonnegative initial soil/fast/slow states required')
    capacity = parameters.runoff.soil_capacity_mm
    if _i26_np.any(array[0] > capacity):
        raise ValueError('initial soil above the prescribed soil_capacity_mm (%.17g)' % (capacity,))
    return array

def _validate_source(value, allowed, name):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError('%s must be one of %r' % (name, allowed))
    return value

def _advance_grouped(liquid_rate_mm_h, states, *, dt_s, pet_rate_mm_h, parameters):
    """Exact per-PET-value grouping over the existing bucket.

    ``RunoffParameters.potential_et_mm_h`` is a scalar, so a spatially varying PET
    rate is realised by grouping **identical float values** with ``np.unique`` (an
    exact operation, no binning, no averaging) and issuing one bucket call per
    distinct value. Each cell's arithmetic is then identical to calling the bucket on
    that cell alone, which the test suite asserts bit for bit.
    """
    from terrain_pipeline.climate_forcing import advance_soil as _x43_advance_soil
    values, inverse = _i26_np.unique(pet_rate_mm_h, return_inverse=True)
    inverse = inverse.reshape(-1)
    cells = int(states.shape[1])
    next_states = _i26_np.empty((3, cells), _i26_np.float64)
    release = _i26_np.empty(cells, _i26_np.float64)
    actual_et = _i26_np.empty(cells, _i26_np.float64)
    change = _i26_np.empty(cells, _i26_np.float64)
    sizes = []
    for index, value in enumerate(values):
        mask = inverse == index
        group_parameters = _i26_replace(parameters, potential_et_mm_h=float(value))
        group_states, group_release, group_et, group_change = _x43_advance_soil(liquid_rate_mm_h[mask], states[:, mask], dt_s=dt_s, parameters=group_parameters)
        next_states[:, mask] = group_states
        release[mask] = group_release
        actual_et[mask] = group_et
        change[mask] = group_change
        sizes.append(int(mask.sum()))
    report = {'unique_pet_groups': int(values.size), 'calls': int(values.size), 'group_sizes': sizes, 'realisation': 'np.unique on the float64 PET rate: exact, no averaging, no coarse re-bucketing'}
    return (next_states, release, actual_et, change, report)

def advance_pet_et(monthly_temperature_c, rain_mm_h, time_edges_s, states, *, x_m, z_m, spacing_m=30.0, parameters=None, temperature_source='caller_declared_monthly_mean', rain_source='declared_event'):
    """Advance the existing soil bucket with a per-cell PET rate and report the ledger.

    Parameters
    ----------
    monthly_temperature_c : [12, N] float64
        Declared monthly-mean temperature in degC. It is the **declared input** of
        this adapter; the adapter never resamples a climate model.
    rain_mm_h : [T, N] float64
        Declared interval-average precipitation intensity in mm/hour on
        ``time_edges_s``. Never derived from an annual total.
    time_edges_s : [T+1] float64
        Strictly increasing physical seconds; every interval is at most 3600 s
        because that is the bucket's own gate.
    states : [3, N] float64
        Explicit initial soil/fast/slow storage in mm (the bucket's own state order).

    Returns
    -------
    dict
        ``soil_edge_mm``/``fast_edge_mm``/``slow_edge_mm`` are ``[T+1, N]`` **edges**:
        the state before interval ``t`` is ``edge[t]`` and after it ``edge[t+1]``.
        There is deliberately no second ``[T+1, N]`` before/after pair.

    Notes
    -----
    The main account is ``delta(soil+fast+slow) = liquid_rain - ET - release``.
    ``subsurface_transfer_mm`` (percolation from soil into the internal slow store) is
    reported for the soil sub-account only and is **never** deducted a second time:
    it is an internal transfer, not a deep loss. ``release_mm`` already contains both
    the fast and the slow release, so it is deducted exactly once.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError('PetEtParameters required')
    temperature_source = _validate_source(temperature_source, PET_ET_TEMPERATURE_SOURCES, 'temperature_source')
    rain_source = _validate_source(rain_source, RAIN_SOURCES, 'rain_source')
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or (not _i26_math.isfinite(spacing_m)) or (spacing_m <= 0.0):
        raise ValueError('finite positive spacing_m required')
    temperature = _i26_np.asarray(monthly_temperature_c, _i26_np.float64)
    if temperature.ndim != 2 or temperature.shape[0] != 12:
        raise ValueError('monthly_temperature_c must be [12, N]')
    if not _i26_np.isfinite(temperature).all():
        raise ValueError('finite monthly temperature required')
    cells = int(temperature.shape[1])
    rain_rate = _i26_np.asarray(rain_mm_h, _i26_np.float64)
    if rain_rate.ndim != 2 or rain_rate.shape[1] != cells:
        raise ValueError('rain_mm_h must be [T, N] matching monthly_temperature_c')
    intervals = int(rain_rate.shape[0])
    if not _i26_np.isfinite(rain_rate).all():
        raise ValueError('finite interval-average rain required')
    if _i26_np.any(rain_rate < 0.0) or _i26_np.any(rain_rate > 1000.0):
        raise ValueError('rain intensity must lie in 0..1000 mm/h')
    edges = _validate_edges(time_edges_s)
    if edges.size - 1 != intervals:
        raise ValueError('time_edges_s must carry exactly T+1 edges for T intervals')
    initial = _validate_states(states, cells, params)
    x, z = _validate_coordinates(x_m, z_m, cells)
    budget = pet_et_preflight(cells, intervals)
    bucket_gate = {'bucket': BUCKET_MODULE, 'max_dt_s': 3600.0, 'max_cells_per_call': 65536, 'calls': 'one advance_soil call per calendar sub-step per distinct PET value; an interval that straddles a month/year edge is sub-stepped', 'streaming_writer_not_used': 'regional_surface_forcing.generate_forcing (MAX_STEPS=288, MAX_CELL_STEPS=25000000) is a streaming file writer and is not part of this adapter; a long run is a caller-side chunking decision'}
    interval_seconds = _i26_np.diff(edges)
    hours = interval_seconds / 3600.0
    month_seconds = calendar_month_seconds(edges)
    pet_depth = interval_pet_mm(temperature, edges, params)
    pet_rate = pet_depth / hours[:, None]
    liquid = liquid_fraction(temperature, month_seconds, params)
    rain_mm = rain_rate * hours[:, None]
    rate_by_month = temperature_index_pet_rate_mm_h(temperature, params)
    liquid_by_month = (temperature >= params.freezing_threshold_c).astype(_i26_np.float64)
    soil_edge = _i26_np.empty((intervals + 1, cells), _i26_np.float64)
    fast_edge = _i26_np.empty((intervals + 1, cells), _i26_np.float64)
    slow_edge = _i26_np.empty((intervals + 1, cells), _i26_np.float64)
    soil_edge[0] = initial[0]
    fast_edge[0] = initial[1]
    slow_edge[0] = initial[2]
    actual_et = _i26_np.empty((intervals, cells), _i26_np.float64)
    release = _i26_np.empty((intervals, cells), _i26_np.float64)
    subsurface = _i26_np.empty((intervals, cells), _i26_np.float64)
    infiltration = _i26_np.empty((intervals, cells), _i26_np.float64)
    change = _i26_np.empty((intervals, cells), _i26_np.float64)
    available_supply = _i26_np.empty((intervals, cells), _i26_np.float64)
    liquid_rain = _i26_np.empty((intervals, cells), _i26_np.float64)
    solid_rain = _i26_np.empty((intervals, cells), _i26_np.float64)
    substeps = _i26_np.empty(intervals, _i26_np.int64)
    regime = _i26_np.empty((intervals, cells), dtype='<U%d' % (REGIME_WIDTH,))
    groups = {'unique_pet_groups': [], 'calls': [], 'group_sizes': [], 'substeps_per_interval': [], 'realisation': 'np.unique on the float64 PET rate: exact, no averaging'}
    runoff = params.runoff
    current = initial.copy()
    for step in range(intervals):
        pieces = _split_interval(edges[step], edges[step + 1])
        substeps[step] = len(pieces)
        step_release = _i26_np.zeros(cells, _i26_np.float64)
        step_et = _i26_np.zeros(cells, _i26_np.float64)
        step_change = _i26_np.zeros(cells, _i26_np.float64)
        step_subsurface = _i26_np.zeros(cells, _i26_np.float64)
        step_infiltration = _i26_np.zeros(cells, _i26_np.float64)
        step_liquid = _i26_np.zeros(cells, _i26_np.float64)
        step_supply = _i26_np.zeros(cells, _i26_np.float64)
        limited_by_pet = _i26_np.ones(cells, bool)
        limited_by_supply = _i26_np.ones(cells, bool)
        calls_here = 0
        groups_here = 0
        for piece_index, (month, seconds) in enumerate(pieces):
            piece_hours = seconds / 3600.0
            piece_fraction = liquid_by_month[month]
            piece_liquid_rate = rain_rate[step] * piece_fraction
            piece_pet_rate = rate_by_month[month]
            next_states, piece_release, piece_et, piece_change, report = _advance_grouped(piece_liquid_rate, current, dt_s=float(seconds), pet_rate_mm_h=piece_pet_rate, parameters=runoff)
            calls_here += report['calls']
            groups_here += report['unique_pet_groups']
            groups['group_sizes'].append(report['group_sizes'])
            cap_infiltration = runoff.infiltration_capacity_mm_h * piece_hours
            headroom = _i26_np.maximum(runoff.soil_capacity_mm - current[0], 0.0)
            piece_infiltration = _i26_np.minimum(_i26_np.minimum(piece_liquid_rate * piece_hours, cap_infiltration), headroom)
            piece_supply = current[0] + piece_infiltration
            piece_percolation = _i26_np.minimum(piece_supply - piece_et, runoff.percolation_mm_h * piece_hours)
            piece_pet_limit = piece_pet_rate * piece_hours
            step_release += piece_release
            step_et += piece_et
            step_change += piece_change
            step_subsurface += piece_percolation
            step_infiltration += piece_infiltration
            step_liquid += piece_liquid_rate * piece_hours
            if piece_index == 0:
                step_supply = piece_supply
            limited_by_pet &= piece_supply >= piece_pet_limit
            limited_by_supply &= piece_supply < piece_pet_limit
            current = next_states
        groups['unique_pet_groups'].append(groups_here)
        groups['calls'].append(calls_here)
        groups['substeps_per_interval'].append(len(pieces))
        actual_et[step] = step_et
        release[step] = step_release
        subsurface[step] = step_subsurface
        infiltration[step] = step_infiltration
        change[step] = step_change
        available_supply[step] = step_supply
        liquid_rain[step] = step_liquid
        solid_rain[step] = rain_mm[step] - step_liquid
        regime[step] = _i26_np.where(limited_by_pet, 'pet_limited', _i26_np.where(limited_by_supply, 'supply_limited', 'mixed_boundary'))
        soil_edge[step + 1] = current[0]
        fast_edge[step + 1] = current[1]
        slow_edge[step + 1] = current[2]
    cell_area = float(spacing_m) ** 2
    inventory_edge = (soil_edge + fast_edge + slow_edge).sum(axis=1) * cell_area / 1000.0
    edge_storage_delta = soil_edge[1:] + fast_edge[1:] + slow_edge[1:] - (soil_edge[:-1] + fast_edge[:-1] + slow_edge[:-1])
    edge_residual = edge_storage_delta - (liquid_rain - actual_et - release)
    bucket_residual = change - (liquid_rain - actual_et - release)
    volume_factor = cell_area / 1000.0
    total_balance = float(edge_residual.sum()) * volume_factor
    edge_max = float(_i26_np.max(_i26_np.abs(edge_residual))) if edge_residual.size else 0.0
    bucket_max = float(_i26_np.max(_i26_np.abs(bucket_residual))) if bucket_residual.size else 0.0
    edge_vs_bucket = float(_i26_np.max(_i26_np.abs(edge_storage_delta - change))) if change.size else 0.0
    ledger_tolerance_mm = 1e-10
    main_verified = bool(edge_max <= ledger_tolerance_mm and edge_vs_bucket <= ledger_tolerance_mm)
    soil_audit = soil_edge[:-1] + infiltration - actual_et - subsurface
    soil_mismatch = int(_i26_np.count_nonzero(soil_audit != soil_edge[1:]))
    soil_abs = _i26_np.abs(soil_audit - soil_edge[1:])
    solid_total = float(solid_rain.sum())
    rain_total = float(rain_mm.sum())
    liquid_total = float(liquid_rain.sum())
    solid_accounting = {'rain_mm_total': rain_total, 'liquid_mm_total': liquid_total, 'solid_equivalent_water_mm_total': solid_total, 'liquid_plus_solid_minus_rain_mm': liquid_total + solid_total - rain_total, 'solid_is_withheld_not_lost': True, 'solid_destination': 'withheld from the bucket and reported as an equivalent water depth; the G7 snow store is not modelled, so this water is neither stored as snow nor routed as meltwater'}
    pet_limited = int(_i26_np.count_nonzero(regime == 'pet_limited'))
    supply_limited = int(_i26_np.count_nonzero(regime == 'supply_limited'))
    mixed_boundary = int(_i26_np.count_nonzero(regime == 'mixed_boundary'))
    denominator = intervals * cells
    regimes = {'pet_limited': pet_limited, 'supply_limited': supply_limited, 'mixed_boundary': mixed_boundary, 'denominator': denominator, 'pet_limited_fraction': pet_limited / denominator if denominator else 0.0, 'rule': "per sub-step: pet_limited when soil_before + infiltration >= that step's PET (the equality case is pet_limited, because the bucket then returns the PET cap itself), supply_limited when strictly below it. An interval that straddles a calendar month edge is labelled mixed_boundary when its own sub-steps disagree. The branch counts are a rule-coverage gate; a real window need not realise every branch."}
    ledger = {'main_account': 'delta(soil+fast+slow) = liquid_rain - actual_et - release', 'main_account_source': "recomputed from the saved state edges, not from the bucket's change array", 'main_max_abs_residual_mm': edge_max, 'main_account_verified': main_verified, 'ledger_tolerance_mm': ledger_tolerance_mm, 'bucket_internal_max_abs_residual_mm': bucket_max, 'edge_vs_bucket_change_max_abs_mm': edge_vs_bucket, 'total_balance_residual_m3': total_balance, 'inventory_delta_m3': float(inventory_edge[-1] - inventory_edge[0]), 'total_liquid_rain_mm': float(liquid_rain.sum()), 'total_actual_et_mm': float(actual_et.sum()), 'total_release_mm': float(release.sum()), 'storage_change_m3': float(inventory_edge[-1] - inventory_edge[0]), 'total_liquid_rain_m3': float(liquid_rain.sum()) * volume_factor, 'total_actual_et_m3': float(actual_et.sum()) * volume_factor, 'total_release_m3': float(release.sum()) * volume_factor, 'total_balance_residual_unit': 'm3', 'release_deducted_once': True, 'subsurface_transfer_is_internal': True, 'solid_accounting': solid_accounting, 'soil_sub_account': {'status': 'audited' if soil_mismatch == 0 else 'audit_mismatch', 'mismatched_cells': soil_mismatch, 'max_abs_difference_mm': float(_i26_np.max(soil_abs)) if soil_abs.size else 0.0, 'definition': 'soil_edge[t] + infiltration - actual_et - subsurface must equal soil_edge[t+1] bit for bit', 'note': 'the bucket returns neither infiltration nor percolation; both are re-derived from the same declared parameters for this audit only'}}
    not_available = {'deep_loss': {'status': NOT_AVAILABLE, 'reason': 'no deep outlet is modelled; percolation stays inside the fast/slow stores'}, 'aquifer_storage': {'status': NOT_AVAILABLE, 'reason': 'no aquifer exists in this chain; the slow store is not one'}, 'baseflow': {'status': NOT_AVAILABLE, 'reason': 'slow release is an internal store discharge, not a groundwater baseflow'}, 'snowpack_state': {'status': NOT_MODELED, 'reason': 'the G7 snow store is not modelled; solid input is withheld and reported as an equivalent depth'}, 'glacier': {'status': NOT_MODELED, 'reason': 'no multi-year mass balance, ice motion or ice erosion exists in this stage'}}
    sources = {'monthly_temperature_c': {'source': temperature_source, 'units': 'degC_monthly_mean', 'semantics': 'monthly_mean_not_daily_and_not_diurnal', 'note': 'declared input; this adapter never resamples a climate model'}, 'rain_mm_h': {'source': rain_source, 'units': 'mm_per_hour_interval_average', 'time_edges': 'explicit physical seconds', 'note': 'an annual total is never converted into a single storm event'}, 'monthly_potential_et_mm': {'source': 'temperature_index_from_monthly_temperature_c', 'units': 'mm_per_month', 'expression': {'path': SEASONAL_SOURCE_PATH, 'sha256': SEASONAL_SOURCE_SHA256, 'line': SEASONAL_PET_LINE, 'form': SEASONAL_PET_EXPRESSION}, 'note': 'declared engineering assumptions reused from SeasonalConfig; not calibrated'}, 'interval_pet_mm': {'source': 'calendar_integration_of_monthly_potential_et', 'units': 'mm_per_interval', 'calendar': '365 days, no leap day, month edges from metric_noise_forcing.MONTH_EDGES_S'}, 'pet_rate_mm_h': {'source': 'interval_pet_mm / interval hours', 'units': 'mm_per_hour', 'note': 'this is the scalar handed to the bucket, per exact value group'}, 'actual_et_mm': {'source': BUCKET_MODULE + ' returned et', 'units': 'mm_per_interval'}, 'release_mm': {'source': BUCKET_MODULE + ' returned release (fast + slow)', 'units': 'mm_per_interval'}, 'subsurface_transfer_mm': {'source': 'independent audit of percolation (soil -> internal slow store)', 'units': 'mm_per_interval', 'note': 'internal transfer only; never deducted from the main account'}, 'infiltration_mm': {'source': 'independent audit from the same declared parameters', 'units': 'mm_per_interval'}, 'soil_edge_mm': {'source': BUCKET_MODULE + ' states[0] at the edge', 'units': 'mm', 'shape': '[T+1, N]'}, 'fast_edge_mm': {'source': BUCKET_MODULE + ' states[1] at the edge', 'units': 'mm', 'shape': '[T+1, N]'}, 'slow_edge_mm': {'source': BUCKET_MODULE + ' states[2] at the edge', 'units': 'mm', 'shape': '[T+1, N]'}, 'liquid_rain_mm': {'source': 'liquid_rate_mm_h * interval hours', 'units': 'mm_per_interval'}, 'liquid_rate_mm_h': {'source': 'rain_mm_h * liquid_fraction (the rate handed to the bucket)', 'units': 'mm_per_hour'}, 'solid_precipitation_swe_mm': {'source': 'rain_mm * (1 - liquid_fraction)', 'units': 'mm_equivalent_water_depth', 'semantics': 'withheld_solid_input', 'note': 'NOT a snow depth: no density is assumed. The solid part is withheld from the bucket and reported here so it cannot silently vanish'}, 'liquid_fraction': {'source': PET_ET_PHASE_SOURCE, 'units': '1', 'semantics': PHASE_SEMANTICS}, 'inventory_m3_edge': {'source': '(soil+fast+slow) * cell_area / 1000', 'units': 'm3', 'shape': '[T+1]'}, 'available_supply_mm': {'source': "soil_edge[t] + infiltration (the bucket's ET order)", 'units': 'mm_per_interval'}, 'et_regime': {'source': 'available_supply_mm vs interval_pet_mm', 'units': 'label', 'values': ['pet_limited', 'supply_limited']}}
    provenance_split = {'temperature': temperature_source, 'rain': rain_source, 'background_estimate_columns': [] if rain_source != 'background_estimate' else ['rain_mm'], 'event_columns': [] if rain_source != 'declared_event' else ['rain_mm'], 'rule': 'a background-estimate column and a real-event column are never merged into one number; the source label is recorded and enters the identity'}
    sub_seed_registration = {'world_seed': None, 'purpose': None, 'noise_used': False, 'note': 'this chain consumes no noise: temperature-index PET and the bucket are deterministic arithmetic, so no subseed is invented. If a noise-driven producer is attached later it must record its derived value here.'}
    limitations = list(PET_ET_LIMITATIONS)
    if rain_source == 'background_estimate':
        limitations.append('rain_source is background_estimate: this run is a declared background estimate, not a real event, and must not be reported as realised weather.')
    if temperature_source != 'g3_monthly_mean':
        limitations.append('monthly temperature is %r, not a G3 production field; the G3 consumer is still to be integrated by the main branch.' % (temperature_source,))
    pet_sha = pet_parameter_identity(params)
    identity = {'pet_parameter_identity_sha256': pet_sha, 'model_identity_sha256': model_identity(parameters=params, x_m=x, z_m=z, time_edges_s=edges, states=initial, monthly_temperature_c=temperature, rain_mm_h=rain_rate, spacing_m=spacing_m, temperature_source=temperature_source, rain_source=rain_source), 'points_sha256': _points_digest(x, z), 'bucket_module': BUCKET_MODULE, 'bucket_parameters': _i26_asdict(runoff), 'pet_parameters': {'pet_base_mm_per_day': params.pet_base_mm_per_day, 'pet_temperature_mm_per_day_c': params.pet_temperature_mm_per_day_c, 'freezing_threshold_c': params.freezing_threshold_c}, 'ignored_bucket_initial_fields': ['initial_soil_mm', 'initial_fast_mm', 'initial_slow_mm']}
    return {'schema': PET_ET_SCHEMA, 'algorithm': PET_ET_ALGORITHM, 'phase_schema': PHASE_SCHEMA, 'shape': [intervals, cells], 'spacing_m': float(spacing_m), 'cell_area_m2': cell_area, 'x_m': x, 'z_m': z, 'time_edges_s': edges, 'interval_seconds': interval_seconds, 'monthly_temperature_c': temperature, 'monthly_potential_et_mm': monthly_potential_et_mm(temperature, params), 'calendar_month_seconds': month_seconds, 'interval_pet_mm': pet_depth, 'pet_rate_mm_h': pet_rate, 'rain_mm': rain_mm, 'liquid_rain_mm': liquid_rain, 'liquid_rate_mm_h': liquid_rain / hours[:, None], 'solid_precipitation_swe_mm': solid_rain, 'liquid_fraction': liquid, 'substeps_per_interval': substeps, 'soil_edge_mm': soil_edge, 'fast_edge_mm': fast_edge, 'slow_edge_mm': slow_edge, 'actual_et_mm': actual_et, 'release_mm': release, 'subsurface_transfer_mm': subsurface, 'infiltration_mm': infiltration, 'storage_change_mm': change, 'available_supply_mm': available_supply, 'et_regime': regime, 'inventory_m3_edge': inventory_edge, 'ledger': ledger, 'regimes': regimes, 'substep_policy': SUBSTEP_POLICY, 'groups': groups, 'sources': sources, 'units': {'monthly_temperature_c': 'degC_monthly_mean', 'monthly_potential_et_mm': 'mm_per_month', 'interval_pet_mm': 'mm_per_interval', 'pet_rate_mm_h': 'mm_per_hour', 'rain_mm': 'mm_per_interval', 'liquid_rain_mm': 'mm_per_interval', 'liquid_rate_mm_h': 'mm_per_hour', 'solid_precipitation_swe_mm': 'mm_equivalent_water_depth', 'liquid_fraction': '1', 'soil_edge_mm': 'mm', 'fast_edge_mm': 'mm', 'slow_edge_mm': 'mm', 'actual_et_mm': 'mm_per_interval', 'release_mm': 'mm_per_interval', 'subsurface_transfer_mm': 'mm_per_interval', 'infiltration_mm': 'mm_per_interval', 'storage_change_mm': 'mm_per_interval', 'available_supply_mm': 'mm_per_interval', 'inventory_m3_edge': 'm3', 'calendar_month_seconds': 's', 'time_edges_s': 's', 'interval_seconds': 's'}, 'provenance_split': provenance_split, 'sub_seed_registration': sub_seed_registration, 'not_available': not_available, 'budget': budget, 'bucket_gate': bucket_gate, 'identity': identity, 'limitations': limitations}

def advance_pet_et_segment(rain_mm_h, time_edges_s, states, *, x_m, z_m, monthly_temperature_c, spacing_m=30.0, parameters=None, temperature_source='caller_declared_monthly_mean', rain_source='declared_event'):
    """Resume on the **same** interval partition from a saved edge.

    This is a thin, honest wrapper: it forwards the remaining interval edges, the
    remaining rain rows and the stored states to :func:`advance_pet_et`, with the
    monthly temperature unchanged. Bit-for-bit equality with a continuous run is only
    promised when the interval edges are the original ones; changing the partition
    changes the discrete bucket time-stepping, because the bucket is not a continuous
    ODE and its release law integrates ``storage * (1 - exp(-dt/tau))`` per step.
    """
    edges = _validate_edges(time_edges_s)
    rain = _i26_np.asarray(rain_mm_h, _i26_np.float64)
    if rain.ndim != 2 or rain.shape[0] != edges.size - 1:
        raise ValueError('rain_mm_h must be [T, N] for the given T+1 edges')
    return advance_pet_et(monthly_temperature_c, rain, edges, states, x_m=x_m, z_m=z_m, spacing_m=spacing_m, parameters=parameters, temperature_source=temperature_source, rain_source=rain_source)

def save_pet_et_checkpoint(path, *, states, edge_index, time_edges_s, parameters, rain_mm_h, monthly_temperature_c, x_m, z_m):
    """Write one edge checkpoint bound to its **source** (points, forcing, temperature).

    A saved state is only shape-compatible with other point sets, forcings and monthly
    temperatures, so ``x_m``/``z_m`` and the forcing arrays are stored as digests. Without
    them a same-shaped state from somewhere else could be restored silently.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    array = _i26_np.asarray(states, _i26_np.float64)
    if array.ndim != 2 or array.shape[0] != 3 or (not _i26_np.isfinite(array).all()):
        raise ValueError('finite [3, N] states required')
    edges = _validate_edges(time_edges_s)
    if isinstance(edge_index, bool) or not isinstance(edge_index, int) or (not 0 <= edge_index < edges.size):
        raise ValueError('edge_index outside 0..T')
    rain = _i26_np.asarray(rain_mm_h, _i26_np.float64)
    temperature = _i26_np.asarray(monthly_temperature_c, _i26_np.float64)
    if rain.ndim != 2 or rain.shape[1] != array.shape[1]:
        raise ValueError('rain_mm_h must be [T, N] matching the states')
    if temperature.ndim != 2 or temperature.shape[0] != 12 or temperature.shape[1] != array.shape[1]:
        raise ValueError('monthly_temperature_c must be [12, N] matching the states')
    if rain.shape[0] < edge_index:
        raise ValueError('rain_mm_h has fewer rows than the checkpoint edge index')
    x, z = _validate_coordinates(x_m, z_m, array.shape[1])
    order = _point_order(x, z)
    destination = _i26_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata = {'schema': CHECKPOINT_SCHEMA, 'algorithm': PET_ET_ALGORITHM, 'edge_index': int(edge_index), 'edge_seconds': float(edges[edge_index]), 'states_shape': list(array.shape), 'rain_shape': list(rain.shape), 'monthly_temperature_shape': list(temperature.shape), 'pet_parameter_identity_sha256': pet_parameter_identity(params), 'bucket_parameters': _i26_asdict(params.runoff), 'points_sha256': _points_digest(x, z), 'cell_order': 'canonical lexsort by (x_m, z_m)', 'monthly_temperature_sha256': _ordered_digest(temperature, order, axis=1), 'rain_prefix_sha256': _ordered_digest(rain[:edge_index], order, axis=1), 'cell_count': int(array.shape[1])}
    with open(destination, 'wb') as stream:
        _i26_np.savez_compressed(stream, states=array, time_edges_s=edges, metadata_json=_i26_np.array(_i26_json.dumps(metadata, sort_keys=True, allow_nan=False)), points_x=x, points_z=z, rain_prefix=rain[:edge_index], monthly_temperature=temperature)
    return metadata

def load_pet_et_checkpoint(path, *, time_edges_s, parameters, x_m, z_m, rain_mm_h, monthly_temperature_c, states_shape=None):
    """Read a checkpoint and prove it belongs to **this** points/forcing/partition.

    Refused without a message about tolerance when: the point set, the monthly temperature,
    the already-consumed rain prefix, the interval-edge prefix, the PET/bucket parameters
    or the state legality do not match. The state array alone is deliberately not enough.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    edges = _validate_edges(time_edges_s)
    with _i26_np.load(path, allow_pickle=False) as archive:
        metadata = _i26_json.loads(str(archive['metadata_json']))
        if metadata.get('schema') != CHECKPOINT_SCHEMA:
            raise ValueError('unknown checkpoint schema')
        if metadata.get('pet_parameter_identity_sha256') != pet_parameter_identity(params):
            raise ValueError('checkpoint PET parameters differ from the declared ones')
        if metadata.get('bucket_parameters') != _i26_asdict(params.runoff):
            raise ValueError('checkpoint bucket parameters differ from the declared ones')
        stored_edges = _i26_np.asarray(archive['time_edges_s'], _i26_np.float64)
        edge_index = int(metadata['edge_index'])
        if edge_index < 0 or edge_index >= stored_edges.size:
            raise ValueError('checkpoint edge_index outside its own edge array')
        if stored_edges.size > edges.size:
            raise ValueError('checkpoint partition is longer than the declared one')
        if not _i26_np.array_equal(stored_edges[:edge_index + 1], edges[:edge_index + 1]):
            raise ValueError('checkpoint does not belong to the declared partition prefix; only the original interval edges give a bit-for-bit resume')
        states = _i26_np.asarray(archive['states'], _i26_np.float64)
        if states.ndim != 2 or states.shape[0] != 3 or (not _i26_np.isfinite(states).all()):
            raise ValueError('invalid checkpoint states')
        if _i26_np.any(states < 0.0):
            raise ValueError('negative checkpoint states')
        if _i26_np.any(states[0] > params.runoff.soil_capacity_mm):
            raise ValueError('checkpoint soil above soil_capacity_mm')
        if states_shape is not None and tuple(states.shape) != tuple(states_shape):
            raise ValueError('checkpoint states shape differs from the declared one')
        cells = int(states.shape[1])
        x, z = _validate_coordinates(x_m, z_m, cells)
        order = _point_order(x, z)
        if metadata.get('points_sha256') != _points_digest(x, z):
            raise ValueError('checkpoint points differ from the declared point set; a same-shaped state from another location cannot be restored')
        stored_x = _i26_np.asarray(archive['points_x'], _i26_np.float64)
        stored_z = _i26_np.asarray(archive['points_z'], _i26_np.float64)
        if not (_i26_np.array_equal(stored_x, x) and _i26_np.array_equal(stored_z, z)):
            raise ValueError('checkpoint stores a different point set than declared')
        temperature = _i26_np.asarray(monthly_temperature_c, _i26_np.float64)
        if temperature.ndim != 2 or temperature.shape[0] != 12 or temperature.shape[1] != cells:
            raise ValueError('monthly_temperature_c must be [12, N] matching the states')
        if metadata.get('monthly_temperature_sha256') != _ordered_digest(temperature, order, axis=1):
            raise ValueError('checkpoint monthly temperature differs from the declared one')
        rain = _i26_np.asarray(rain_mm_h, _i26_np.float64)
        if rain.ndim != 2 or rain.shape[1] != cells or rain.shape[0] < edge_index:
            raise ValueError('rain_mm_h must be [T, N] with T >= the checkpoint edge index')
        if metadata.get('rain_prefix_sha256') != _ordered_digest(rain[:edge_index], order, axis=1):
            raise ValueError('checkpoint consumed a different rain prefix than the declared forcing')
    return {'schema': CHECKPOINT_SCHEMA, 'edge_index': edge_index, 'edge_seconds': float(stored_edges[edge_index]), 'states': states, 'time_edges_s': stored_edges, 'points_x': stored_x, 'points_z': stored_z, 'metadata': metadata}

def pet_et_describe():
    """Static declaration for review and downstream references (no numeric effect)."""
    return {'schema': PET_ET_SCHEMA, 'algorithm': PET_ET_ALGORITHM, 'phase_schema': PHASE_SCHEMA, 'bucket_module': BUCKET_MODULE, 'network_coupling': 'none', 'boundary_api': 'none', 'pet_expression': {'path': SEASONAL_SOURCE_PATH, 'sha256': SEASONAL_SOURCE_SHA256, 'line': SEASONAL_PET_LINE, 'form': SEASONAL_PET_EXPRESSION, 'declared_synonymous': True}, 'phase_source': PET_ET_PHASE_SOURCE, 'phase_semantics': PHASE_SEMANTICS, 'temperature_sources': list(PET_ET_TEMPERATURE_SOURCES), 'rain_sources': list(RAIN_SOURCES), 'state_edges': '[T+1, N] edge convention; soil_before = edge[t], soil_after = edge[t+1]', 'limits': {'max_cells': PET_ET_MAX_CELLS, 'max_intervals': MAX_INTERVALS, 'max_cell_intervals': MAX_CELL_INTERVALS, 'max_output_bytes': MAX_OUTPUT_BYTES, 'max_interval_seconds': 3600.0}, 'never': ['a second soil bucket', 'a second PET formula', 'averaging or coarse re-bucketing of the PET rate', 'available_water used as storage or as actual ET', 'an annual precipitation total used as a single storm event', 'an aquifer, a groundwater baseflow or a deep loss', 'snow depth or glacier from a freezing-threshold diagnostic', 'resume equality across a changed interval partition', 'a channel network or a boundary condition in this entry point'], 'limitations': list(PET_ET_LIMITATIONS)}
WEATHERING_SCHEMA = 'weathering-soil-inventory-v1'
WEATHERING_ALGORITHM = 'conservative-bedrock-weathering-inventory-v1'
FORMAT_VERSION = 1
MAX_COLUMNS = 4096
CLOSURE_RELATIVE_TOLERANCE = 1e-12
EXHAUSTED = 'exhausted'
ACTIVE = 'active'
MASS_PENDING = 'pending_missing_density'
MASS_DECLARED = 'declared'
DECLARED = 'declared'
ENGINEERING_REFERENCE = 'engineering_reference_uncalibrated'
WEATHERING_LIMITATIONS = ('weathering depth rate is a declared engineering rule of the available conditions; it is not a calibrated global weathering law', 'bedrock solid removed equals regolith solid produced plus dissolved solid exported; the ledger checks this every step', 'parent material is a fine-fraction view of the regolith, never a second store', 'a delivery is debited from the single regolith account and recorded as delivered_regolith_solid_m3, so a soil and a river request cannot double count', 'pore conversion from solid to bulk is applied once, at production', 'negative temperature is a legal input and only reduces the rate factor', 'supply functions report availability only: nothing is transported to the river, the sea or the ground water here')

def _weathering_finite(value, name):
    if isinstance(value, (bool, _i27_np.bool_)) or not isinstance(value, (int, float, _i27_np.integer, _i27_np.floating)):
        raise ValueError(name + ' must be numeric')
    result = float(value)
    if not _i27_math.isfinite(result):
        raise ValueError(name + ' must be finite')
    return result

def _nonnegative(value, name):
    result = _weathering_finite(value, name)
    if result < 0.0:
        raise ValueError(name + ' must be non-negative')
    return result

def _weathering_positive(value, name):
    result = _weathering_finite(value, name)
    if result <= 0.0:
        raise ValueError(name + ' must be positive')
    return result

def _fraction(value, name):
    result = _weathering_finite(value, name)
    if not 0.0 <= result < 1.0:
        raise ValueError(name + ' must satisfy 0 <= value < 1')
    return result

def _series(value, n, name, *, nonnegative=True):
    array = _i27_np.asarray(value, _i27_np.float64)
    if array.ndim == 0:
        array = _i27_np.full(n, float(array), _i27_np.float64)
    array = _i27_np.ascontiguousarray(array.reshape(-1), _i27_np.float64)
    if array.size != n:
        raise ValueError(name + ' must have one value per column')
    if not _i27_np.isfinite(array).all():
        raise ValueError(name + ' must be finite')
    if nonnegative and _i27_np.any(array < 0.0):
        raise ValueError(name + ' must be non-negative')
    return array

def _check_columns(n):
    if isinstance(n, (bool, _i27_np.bool_)) or not isinstance(n, (int, _i27_np.integer)):
        raise ValueError('column count must be an integer')
    columns = int(n)
    if columns <= 0:
        raise ValueError('column count must be positive')
    if columns > MAX_COLUMNS:
        raise ValueError('column count %d exceeds %d' % (columns, MAX_COLUMNS))
    return columns

def normalize_parameters(declaration=None):
    """Declared rate coefficients. Unknown keys and missing provenance rejected."""
    defaults = {'k_physical_m_per_s': {'value': 1e-13, 'units': 'm/s', 'status': ENGINEERING_REFERENCE, 'source': 'declared default; not a global calibration'}, 'k_chemical_m_per_s': {'value': 1e-13, 'units': 'm/s', 'status': ENGINEERING_REFERENCE, 'source': 'declared default; not a global calibration'}, 'k_biological_m_per_s': {'value': 5e-14, 'units': 'm/s', 'status': ENGINEERING_REFERENCE, 'source': 'declared default; not a global calibration'}, 'temperature_reference_c': {'value': 10.0, 'units': 'degC', 'status': DECLARED, 'source': 'declared reference'}, 'q10': {'value': 2.0, 'units': '1', 'status': ENGINEERING_REFERENCE, 'source': 'declared Q10 factor; not a fit to measurements'}, 'dissolved_fraction_of_solid': {'value': 0.1, 'units': '1', 'status': ENGINEERING_REFERENCE, 'source': 'declared chemical share'}, 'regolith_porosity': {'value': 0.35, 'units': 'volume fraction', 'status': ENGINEERING_REFERENCE, 'source': 'declared porosity of the loose product'}, 'fines_fraction_of_regolith': {'value': 0.5, 'units': '1', 'status': ENGINEERING_REFERENCE, 'source': 'declared fine fraction available as parent material'}}
    supplied = {} if declaration is None else dict(declaration)
    unknown = sorted(set(supplied) - set(defaults))
    if unknown:
        raise ValueError('unknown parameter keys: %r' % (unknown,))
    resolved = {}
    for name, default in defaults.items():
        entry = dict(default)
        override = supplied.get(name)
        if override is not None:
            if not isinstance(override, dict):
                raise ValueError(name + ' must be a dict')
            extra = sorted(set(override) - set(default))
            if extra:
                raise ValueError('unknown fields for %s: %r' % (name, extra))
            if 'value' in override and 'source' not in override:
                raise ValueError(name + ' overrides a value and needs an explicit non-empty source')
            entry.update(override)
            for key in ('status', 'source'):
                text = entry.get(key)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(name + ' needs a non-empty ' + key)
        resolved[name] = entry
    for name in ('k_physical_m_per_s', 'k_chemical_m_per_s', 'k_biological_m_per_s', 'q10'):
        resolved[name]['value'] = _nonnegative(resolved[name]['value'], name)
    resolved['temperature_reference_c']['value'] = _weathering_finite(resolved['temperature_reference_c']['value'], 'temperature_reference_c')
    resolved['dissolved_fraction_of_solid']['value'] = _fraction(resolved['dissolved_fraction_of_solid']['value'], 'dissolved_fraction_of_solid')
    resolved['regolith_porosity']['value'] = _fraction(resolved['regolith_porosity']['value'], 'regolith_porosity')
    resolved['fines_fraction_of_regolith']['value'] = _fraction(resolved['fines_fraction_of_regolith']['value'], 'fines_fraction_of_regolith')
    return resolved

def _value(parameters, name):
    return float(parameters[name]['value'])

def weathering_preflight(n_columns):
    columns = _check_columns(n_columns)
    per_column_bytes = 8 * 12
    return {'n_columns': columns, 'max_columns': MAX_COLUMNS, 'estimated_payload_bytes': columns * per_column_bytes, 'closure_relative_tolerance': CLOSURE_RELATIVE_TOLERANCE}

def initial_state(*, bedrock_thickness_m, area_m2, bed_hardness, solubility, density_kg_m3=None):
    """A finite weatherable column. No weathering has happened yet."""
    thickness = _i27_np.asarray(bedrock_thickness_m, _i27_np.float64)
    if thickness.ndim == 0:
        thickness = _i27_np.atleast_1d(_i27_np.asarray(thickness, _i27_np.float64))
    thickness = _i27_np.ascontiguousarray(thickness.reshape(-1), _i27_np.float64)
    n = _check_columns(thickness.size)
    budget = weathering_preflight(n)
    thickness = _series(thickness, n, 'bedrock_thickness_m')
    area = _series(area_m2, n, 'area_m2', nonnegative=False)
    if _i27_np.any(area <= 0.0):
        raise ValueError('area_m2 must be positive per column')
    hardness = _series(bed_hardness, n, 'bed_hardness')
    solubility_series = _series(solubility, n, 'solubility')
    if _i27_np.any(hardness > 1.0) or _i27_np.any(solubility_series > 1.0):
        raise ValueError('hardness and solubility must lie in [0, 1]')
    solid = thickness * area
    state = {'bedrock_solid_m3': _i27_np.ascontiguousarray(solid, _i27_np.float64), 'regolith_solid_m3': _i27_np.zeros(n, _i27_np.float64), 'regolith_bulk_m3': _i27_np.zeros(n, _i27_np.float64), 'parent_solid_m3': _i27_np.zeros(n, _i27_np.float64), 'dissolved_solid_m3': _i27_np.zeros(n, _i27_np.float64), 'delivered_regolith_solid_m3': _i27_np.zeros(n, _i27_np.float64), 'delivered_parent_solid_m3': _i27_np.zeros(n, _i27_np.float64), 'weatherable_thickness_m': _i27_np.ascontiguousarray(thickness, _i27_np.float64), 'area_m2': _i27_np.ascontiguousarray(area, _i27_np.float64), 'bed_hardness': _i27_np.ascontiguousarray(hardness, _i27_np.float64), 'solubility': _i27_np.ascontiguousarray(solubility_series, _i27_np.float64), 'initial_bedrock_solid_m3': _i27_np.ascontiguousarray(solid.copy(), _i27_np.float64), 'status': _i27_np.full(n, ACTIVE, dtype=object), 'density_kg_m3': None if density_kg_m3 is None else _series(density_kg_m3, n, 'density_kg_m3', nonnegative=False), 'parameters': normalize_parameters(None), 'budget': budget}
    if density_kg_m3 is not None and _i27_np.any(state['density_kg_m3'] <= 0.0):
        raise ValueError('density_kg_m3 must be positive where declared')
    return state

def _temperature_factor(temperature_c, reference_c, q10):
    """Q10 factor; a negative temperature is legal and just lowers it."""
    exponent = (temperature_c - reference_c) / 10.0
    return _i27_np.power(q10, exponent)

def advance(state, *, dt_s, temperature_c, moisture, bio_activity=0.0, parameters=None):
    """Advance one declared time step; returns ``(next_state, flux)``.

    The weathered depth is capped by the remaining weatherable thickness, so the
    stock can be exhausted but never over-drawn. Solid closure is checked against
    the step's own mass scale.
    """
    if not isinstance(state, dict) or 'bedrock_solid_m3' not in state:
        raise ValueError('a state from initial_state is required')
    dt = _weathering_positive(dt_s, 'dt_s')
    config = normalize_parameters(parameters)
    n = int(state['bedrock_solid_m3'].size)
    if n != int(state['regolith_solid_m3'].size):
        raise ValueError('state arrays disagree in length')
    temperature = _series(temperature_c, n, 'temperature_c', nonnegative=False)
    wetness = _series(moisture, n, 'moisture')
    if _i27_np.any(wetness > 1.0):
        raise ValueError('moisture must lie in [0, 1]')
    biology = _series(bio_activity, n, 'bio_activity')
    if _i27_np.any(biology > 1.0):
        raise ValueError('bio_activity must lie in [0, 1]')
    factor = _temperature_factor(temperature, _value(config, 'temperature_reference_c'), _value(config, 'q10'))
    physical = _value(config, 'k_physical_m_per_s') * (1.0 - state['bed_hardness'])
    chemical = _value(config, 'k_chemical_m_per_s') * state['solubility'] * wetness * factor
    biogenic = _value(config, 'k_biological_m_per_s') * biology * wetness * factor
    requested_depth = (physical + chemical + biogenic) * dt
    area = state['area_m2']
    available_depth = state['bedrock_solid_m3'] / area
    weathered_depth = _i27_np.minimum(requested_depth, available_depth)
    weathered_depth = _i27_np.maximum(weathered_depth, 0.0)
    weathered_solid = weathered_depth * area
    dissolved_fraction = _value(config, 'dissolved_fraction_of_solid')
    dissolved = weathered_solid * dissolved_fraction
    regolith_solid = weathered_solid - dissolved
    porosity = _value(config, 'regolith_porosity')
    regolith_bulk = regolith_solid / (1.0 - porosity)
    fines_fraction = _value(config, 'fines_fraction_of_regolith')
    parent = regolith_solid * fines_fraction
    next_state = dict(state)
    next_state['bedrock_solid_m3'] = _i27_np.ascontiguousarray(state['bedrock_solid_m3'] - weathered_solid, _i27_np.float64)
    next_state['regolith_solid_m3'] = _i27_np.ascontiguousarray(state['regolith_solid_m3'] + regolith_solid, _i27_np.float64)
    next_state['regolith_bulk_m3'] = _i27_np.ascontiguousarray(state['regolith_bulk_m3'] + regolith_bulk, _i27_np.float64)
    next_state['parent_solid_m3'] = _i27_np.ascontiguousarray(state['parent_solid_m3'] + parent, _i27_np.float64)
    next_state['dissolved_solid_m3'] = _i27_np.ascontiguousarray(state['dissolved_solid_m3'] + dissolved, _i27_np.float64)
    next_state['parameters'] = config
    next_state['status'] = _i27_np.where(next_state['bedrock_solid_m3'] <= 0.0, EXHAUSTED, ACTIVE).astype(object)
    scale = _i27_np.maximum(state['initial_bedrock_solid_m3'], 1.0)
    residual = weathered_solid - regolith_solid - dissolved
    tolerance = CLOSURE_RELATIVE_TOLERANCE * scale
    if _i27_np.any(_i27_np.abs(residual) > tolerance):
        raise ValueError('solid closure broken: weathered minus regolith minus dissolved exceeds the declared tolerance')
    flux = {'dt_s': dt, 'weathered_depth_m': _i27_np.ascontiguousarray(weathered_depth, _i27_np.float64), 'weathered_solid_m3': _i27_np.ascontiguousarray(weathered_solid, _i27_np.float64), 'regolith_solid_m3': _i27_np.ascontiguousarray(regolith_solid, _i27_np.float64), 'regolith_bulk_m3': _i27_np.ascontiguousarray(regolith_bulk, _i27_np.float64), 'parent_solid_m3': _i27_np.ascontiguousarray(parent, _i27_np.float64), 'dissolved_solid_m3': _i27_np.ascontiguousarray(dissolved, _i27_np.float64), 'capped_by_stock': _i27_np.ascontiguousarray(requested_depth > available_depth + 0.0, bool), 'temperature_factor': _i27_np.ascontiguousarray(factor, _i27_np.float64), 'budget': weathering_preflight(n)}
    return (next_state, flux)

def soil_parent_supply(state, fraction=0.1):
    """Parent material available to a soil consumer; nothing is removed here."""
    share = _fraction(fraction, 'fraction')
    available = state['parent_solid_m3'] * share
    return {'available_parent_solid_m3': _i27_np.ascontiguousarray(available, _i27_np.float64), 'fraction_of_parent_stock': share, 'supply_semantics': 'availability only; the caller must debit the stock', 'consumer': 'G6 soil supply (not wired by this module)', 'transported': False}

def sediment_supply(state, fraction=0.1):
    """Loose regolith solid available as river sediment source; not transported."""
    share = _fraction(fraction, 'fraction')
    available = state['regolith_solid_m3'] * share
    return {'available_sediment_solid_m3': _i27_np.ascontiguousarray(available, _i27_np.float64), 'fraction_of_regolith_stock': share, 'supply_semantics': 'availability only; the caller must debit the stock', 'consumer': 'river sediment source (not wired by this module)', 'transported': False}

def allocate(state, *, soil_parent_solid_m3=0.0, sediment_solid_m3=0.0, shortage_policy='reject'):
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
    if not isinstance(state, dict) or 'regolith_solid_m3' not in state:
        raise ValueError('a state from initial_state is required')
    if shortage_policy not in ('reject', 'proportional'):
        raise ValueError("shortage_policy must be 'reject' or 'proportional'")
    n = int(state['regolith_solid_m3'].size)
    soil_request = _series(soil_parent_solid_m3, n, 'soil_parent_solid_m3')
    sediment_request = _series(sediment_solid_m3, n, 'sediment_solid_m3')
    regolith = state['regolith_solid_m3']
    parent = state['parent_solid_m3']
    if _i27_np.any(parent > regolith + 0.0):
        raise ValueError('parent material must be a subset of the regolith solid')
    non_parent = regolith - parent
    requested = soil_request + sediment_request
    total_short = requested > regolith
    soil_short = soil_request > parent
    if shortage_policy == 'reject' and (_i27_np.any(total_short) or _i27_np.any(soil_short)):
        raise ValueError('requested delivery exceeds the stock: the regolith total or the parent fine-particle subset is too small (parent is a subset, not a second stock)')
    if shortage_policy == 'proportional':
        ratio = _i27_np.ones(n, _i27_np.float64)
        _i27_np.divide(regolith, requested, out=ratio, where=requested > 0.0)
        ratio = _i27_np.minimum(ratio, 1.0)
        soil_ratio = _i27_np.ones(n, _i27_np.float64)
        _i27_np.divide(parent, soil_request, out=soil_ratio, where=soil_request > 0.0)
        ratio = _i27_np.minimum(ratio, _i27_np.minimum(soil_ratio, 1.0))
        ratio = _i27_np.clip(ratio, 0.0, 1.0)
    else:
        ratio = _i27_np.ones(n, _i27_np.float64)
    soil_delivered = _i27_np.minimum(soil_request * ratio, parent)
    sediment_delivered = _i27_np.minimum(sediment_request * ratio, _i27_np.maximum(regolith - soil_delivered, 0.0))
    sediment_from_non_parent = _i27_np.minimum(sediment_delivered, non_parent)
    sediment_from_parent = sediment_delivered - sediment_from_non_parent
    parent_delivered = soil_delivered + sediment_from_parent
    total_delivered = soil_delivered + sediment_delivered
    next_state = dict(state)
    next_state['regolith_solid_m3'] = _i27_np.ascontiguousarray(regolith - total_delivered, _i27_np.float64)
    next_state['parent_solid_m3'] = _i27_np.ascontiguousarray(parent - parent_delivered, _i27_np.float64)
    porosity = _declared_porosity(state)
    next_state['regolith_bulk_m3'] = _i27_np.ascontiguousarray(state['regolith_bulk_m3'] - total_delivered / (1.0 - porosity), _i27_np.float64)
    next_state['delivered_regolith_solid_m3'] = _i27_np.ascontiguousarray(state['delivered_regolith_solid_m3'] + total_delivered, _i27_np.float64)
    next_state['delivered_parent_solid_m3'] = _i27_np.ascontiguousarray(state.get('delivered_parent_solid_m3', _i27_np.zeros(n, _i27_np.float64)) + parent_delivered, _i27_np.float64)
    if _i27_np.any(next_state['parent_solid_m3'] < -0.0):
        raise ValueError('parent subset went negative on delivery')
    if _i27_np.any(next_state['parent_solid_m3'] > next_state['regolith_solid_m3'] + 0.0):
        raise ValueError('parent subset exceeded the regolith on delivery')
    remaining = {'regolith_solid_m3': _i27_np.ascontiguousarray(next_state['regolith_solid_m3'], _i27_np.float64), 'parent_solid_m3': _i27_np.ascontiguousarray(next_state['parent_solid_m3'], _i27_np.float64), 'non_parent_solid_m3': _i27_np.ascontiguousarray(next_state['regolith_solid_m3'] - next_state['parent_solid_m3'], _i27_np.float64)}
    return (next_state, {'soil_parent_solid_m3': _i27_np.ascontiguousarray(soil_delivered, _i27_np.float64), 'taken_from_parent_solid_m3': _i27_np.ascontiguousarray(soil_delivered, _i27_np.float64), 'consumer': 'soil parent material', 'transported': False}, {'sediment_solid_m3': _i27_np.ascontiguousarray(sediment_delivered, _i27_np.float64), 'from_non_parent_solid_m3': _i27_np.ascontiguousarray(sediment_from_non_parent, _i27_np.float64), 'from_parent_solid_m3': _i27_np.ascontiguousarray(sediment_from_parent, _i27_np.float64), 'consumer': 'river sediment', 'transported': False}, remaining, ledger(next_state))

def _declared_porosity(state):
    """Porosity used for the bulk view; re-read from the parameters at debit time."""
    parameters = state.get('parameters')
    if parameters is None:
        parameters = normalize_parameters(None)
    return _value(parameters, 'regolith_porosity')

def ledger(state):
    """Initial versus current accounts plus the closure residual."""
    initial = state['initial_bedrock_solid_m3']
    bedrock = state['bedrock_solid_m3']
    regolith = state['regolith_solid_m3']
    dissolved = state['dissolved_solid_m3']
    delivered = state['delivered_regolith_solid_m3']
    removed = initial - bedrock
    residual = removed - regolith - dissolved - delivered
    result = {'initial_bedrock_solid_m3': _i27_np.ascontiguousarray(initial, _i27_np.float64), 'current_bedrock_solid_m3': _i27_np.ascontiguousarray(bedrock, _i27_np.float64), 'removed_bedrock_solid_m3': _i27_np.ascontiguousarray(removed, _i27_np.float64), 'regolith_solid_m3': _i27_np.ascontiguousarray(regolith, _i27_np.float64), 'regolith_bulk_m3': _i27_np.ascontiguousarray(state['regolith_bulk_m3'], _i27_np.float64), 'parent_solid_m3': _i27_np.ascontiguousarray(state['parent_solid_m3'], _i27_np.float64), 'dissolved_exported_solid_m3': _i27_np.ascontiguousarray(dissolved, _i27_np.float64), 'delivered_regolith_solid_m3': _i27_np.ascontiguousarray(delivered, _i27_np.float64), 'closure_residual_m3': _i27_np.ascontiguousarray(residual, _i27_np.float64), 'closure_relative_tolerance': CLOSURE_RELATIVE_TOLERANCE, 'status': _i27_np.array(state['status'], dtype=object), 'units': {'solid': 'm3', 'bulk': 'm3', 'depth': 'm', 'dt': 's'}}
    if state['density_kg_m3'] is None:
        result['mass_status'] = MASS_PENDING
    else:
        density = state['density_kg_m3']
        result['mass_status'] = MASS_DECLARED
        result['current_bedrock_mass_kg'] = _i27_np.ascontiguousarray(bedrock * density, _i27_np.float64)
        result['regolith_mass_kg'] = _i27_np.ascontiguousarray(regolith * density, _i27_np.float64)
        result['dissolved_exported_mass_kg'] = _i27_np.ascontiguousarray(dissolved * density, _i27_np.float64)
    return result

def weathering_describe():
    return {'schema': WEATHERING_SCHEMA, 'algorithm': WEATHERING_ALGORITHM, 'format_version': FORMAT_VERSION, 'max_columns': MAX_COLUMNS, 'closure_relative_tolerance': CLOSURE_RELATIVE_TOLERANCE, 'state_fields': ['bedrock_solid_m3', 'regolith_solid_m3', 'regolith_bulk_m3', 'parent_solid_m3', 'dissolved_solid_m3', 'delivered_regolith_solid_m3', 'delivered_parent_solid_m3'], 'shortage_policies': ['reject', 'proportional'], 'units': {'solid': 'm3', 'bulk': 'm3', 'mass': 'kg', 'dt': 's', 'temperature': 'degC', 'bed_hardness': '1', 'solubility': '1', 'moisture': '1', 'bio_activity': '1'}, 'negative_temperature_allowed': True, 'limitations': list(WEATHERING_LIMITATIONS)}
LAND_COVER_ALGORITHM = 'environment-land-cover-v1'
LAND_COVER_SCHEMA = 'environment-land-cover-v1'
COVER_CLASSES = ('bare_rock', 'sparse', 'grass', 'shrub', 'forest', 'wetland')
BARE_ROCK, SPARSE, GRASS, SHRUB, FOREST, WETLAND = range(len(COVER_CLASSES))
STATUS_COMPUTED = 'computed'
STATUS_DECLARED = 'declared'
STATUS_PENDING = 'pending'
STATUS_NOT_AVAILABLE = 'not_available'
LAND_COVER_LIMITATIONS = ('land cover is a classified surface condition, not vegetation: no biomass, no growth, no succession and no species competition is modelled.', 'soil thickness is bulk thickness derived from a parent **solid** volume and a declared porosity; it is not a measured soil depth and not an equivalent solid thickness.', 'soil water capacity and the G5 bucket state are different quantities: capacity is how much the layer could hold, the bucket state is what it holds now. Neither is derived from the other.', 'available_water_fraction, the suitability weights and every threshold below are declared engineering assumptions, not calibrated values.', 'the parent material is whatever the caller declares (G9 delivered volumes in the default use); this module does not weather rock itself.', 'no channel, no routing, no erosion and no sediment transport is touched.')

@_i28_dataclass(frozen=True)
class LandCoverParameters:
    """Declared engineering constants. Every one is an assumption, not a measurement."""
    available_water_fraction: float = 0.15
    rock_thickness_m: float = 0.02
    full_thickness_m: float = 1.0
    temperature_optimum_c: float = 14.0
    temperature_tolerance_c: float = 16.0
    weight_temperature: float = 0.35
    weight_water: float = 0.4
    weight_material: float = 0.25
    sparse_threshold: float = 0.15
    grass_threshold: float = 0.35
    shrub_threshold: float = 0.55
    forest_threshold: float = 0.75
    wetland_water_fraction: float = 0.85

    def __post_init__(self):
        for name in ('available_water_fraction', 'rock_thickness_m', 'full_thickness_m', 'temperature_optimum_c', 'temperature_tolerance_c', 'weight_temperature', 'weight_water', 'weight_material', 'sparse_threshold', 'grass_threshold', 'shrub_threshold', 'forest_threshold', 'wetland_water_fraction'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i28_math.isfinite(value)) or (value < 0.0):
                raise ValueError('invalid %s: a finite nonnegative number is required' % (name,))
        if not self.available_water_fraction < 1.0:
            raise ValueError('available_water_fraction must be below 1')
        if not 0.0 < self.full_thickness_m:
            raise ValueError('full_thickness_m must be positive')
        if not 0.0 < self.temperature_tolerance_c:
            raise ValueError('temperature_tolerance_c must be positive')
        weights = (self.weight_temperature, self.weight_water, self.weight_material)
        if abs(sum(weights) - 1.0) > 1e-09:
            raise ValueError('driver weights must sum to 1, got %r' % (sum(weights),))
        if not 0.0 < self.sparse_threshold < self.grass_threshold < self.shrub_threshold < self.forest_threshold <= 1.0:
            raise ValueError('class thresholds must be strictly increasing in (0, 1]')
        if not 0.0 <= self.wetland_water_fraction <= 1.0:
            raise ValueError('wetland_water_fraction must lie in 0..1')

    @property
    def identity_sha256(self):
        return _digest({'schema': LAND_COVER_SCHEMA, 'algorithm': LAND_COVER_ALGORITHM, 'parameters': {name: getattr(self, name) for name in self.__dataclass_fields__}})

def _land_cover_positive(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i28_math.isfinite(value)) or (not 0.0 < value <= maximum):
        raise ValueError('invalid %s: finite positive <= %g required' % (name, maximum))
    return float(value)

def bulk_thickness_m(solid_m3, *, porosity, horizontal_area_m2):
    """Bulk soil thickness from a parent **solid** volume.

    ``bulk = solid / ((1 - porosity) * area)``. Dividing by the area alone would give an
    equivalent solid thickness and would understate the layer by ``1/(1-porosity)``.
    """
    solid = _i28_np.asarray(solid_m3, _i28_np.float64)
    if not _i28_np.isfinite(solid).all() or _i28_np.any(solid < 0.0):
        raise ValueError('finite nonnegative parent solid volume required')
    pore = _i28_np.asarray(porosity, _i28_np.float64)
    if not _i28_np.isfinite(pore).all() or _i28_np.any(pore < 0.0) or _i28_np.any(pore >= 1.0):
        raise ValueError('porosity must be finite and lie in [0, 1)')
    area = _land_cover_positive(horizontal_area_m2, 'horizontal_area_m2', 1000000000000.0)
    return solid / ((1.0 - pore) * area)

def soil_water_capacity_mm(thickness_m, parameters=None):
    """Water the layer could hold, in mm of depth. Capacity, never a stock."""
    params = parameters or LandCoverParameters()
    thickness = _i28_np.asarray(thickness_m, _i28_np.float64)
    if not _i28_np.isfinite(thickness).all() or _i28_np.any(thickness < 0.0):
        raise ValueError('finite nonnegative thickness required')
    return thickness * 1000.0 * params.available_water_fraction

def assess_land_cover(*, parent_solid_m3, porosity, horizontal_area_m2, family_temperature_c, water_state_mm, water_capacity_reference_mm=None, hard_substrate=None, parameters=None, status=None):
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
        raise ValueError('LandCoverParameters required')
    solid = _i28_np.asarray(parent_solid_m3, _i28_np.float64).reshape(-1)
    pore = _i28_np.asarray(porosity, _i28_np.float64).reshape(-1)
    temperature = _i28_np.asarray(family_temperature_c, _i28_np.float64).reshape(-1)
    cells = solid.size
    if cells == 0:
        raise ValueError('at least one column is required')
    for name, array in (('porosity', pore), ('family_temperature_c', temperature)):
        if array.size != cells:
            raise ValueError('%s must provide one value per column' % (name,))
        if not _i28_np.isfinite(array).all():
            raise ValueError('%s must be finite' % (name,))
    water = _i28_np.asarray(water_state_mm, _i28_np.float64)
    if water.ndim == 2:
        if water.shape != (3, cells):
            raise ValueError('a bucket water state must be [3, N]')
        water_total = water.sum(axis=0)
        water_shape_reported = [3, cells]
    elif water.ndim == 1:
        if water.size != cells:
            raise ValueError('a water state vector must provide one value per column')
        water_total = water
        water_shape_reported = [cells]
    else:
        raise ValueError('water_state_mm must be [3, N] or [N]')
    if not _i28_np.isfinite(water_total).all() or _i28_np.any(water_total < 0.0):
        raise ValueError('finite nonnegative water state required')
    thickness = bulk_thickness_m(solid, porosity=pore, horizontal_area_m2=horizontal_area_m2)
    capacity = soil_water_capacity_mm(thickness, params)
    if water_capacity_reference_mm is None:
        capacity_reference = capacity
        capacity_source = 'derived_from_this_call_thickness'
    else:
        capacity_reference = _i28_np.asarray(water_capacity_reference_mm, _i28_np.float64).reshape(-1)
        if capacity_reference.size != cells or not _i28_np.isfinite(capacity_reference).all() or _i28_np.any(capacity_reference < 0.0):
            raise ValueError('water_capacity_reference_mm must be finite nonnegative [N]')
        capacity_source = 'caller_declared'
    normalised_temperature = _i28_np.clip(1.0 - _i28_np.abs(temperature - params.temperature_optimum_c) / params.temperature_tolerance_c, 0.0, 1.0)
    water_ratio = _i28_np.zeros(cells, _i28_np.float64)
    positive = capacity_reference > 0.0
    _i28_np.divide(water_total, capacity_reference, out=water_ratio, where=positive)
    normalised_water = _i28_np.clip(water_ratio, 0.0, 1.0)
    normalised_material = _i28_np.clip(thickness / params.full_thickness_m, 0.0, 1.0)
    suitability = params.weight_temperature * normalised_temperature + params.weight_water * normalised_water + params.weight_material * normalised_material
    cover = _i28_np.full(cells, BARE_ROCK, _i28_np.int64)
    cover = _i28_np.where(suitability >= params.sparse_threshold, SPARSE, cover)
    cover = _i28_np.where(suitability >= params.grass_threshold, GRASS, cover)
    cover = _i28_np.where(suitability >= params.shrub_threshold, SHRUB, cover)
    cover = _i28_np.where(suitability >= params.forest_threshold, FOREST, cover)
    too_thin = thickness < params.rock_thickness_m
    cover = _i28_np.where(too_thin, BARE_ROCK, cover)
    if hard_substrate is not None:
        substrate = _i28_np.asarray(hard_substrate, bool).reshape(-1)
        if substrate.size != cells:
            raise ValueError('hard_substrate must provide one value per column')
        cover = _i28_np.where(substrate, BARE_ROCK, cover)
        substrate_status = STATUS_DECLARED
    else:
        substrate_status = STATUS_PENDING
    wetland = water_ratio >= params.wetland_water_fraction
    cover = _i28_np.where(wetland & ~too_thin, WETLAND, cover)
    cover_names = _i28_np.asarray([COVER_CLASSES[int(v)] for v in cover])
    status = dict(status or {})
    field_status = {'parent_solid_m3': status.get('material', STATUS_DECLARED), 'porosity': status.get('material', STATUS_DECLARED), 'soil_thickness_bulk_m': STATUS_COMPUTED, 'soil_water_capacity_mm': STATUS_DECLARED, 'water_state_total_mm': status.get('water_state', STATUS_DECLARED), 'family_temperature_c': status.get('family_temperature', STATUS_DECLARED), 'suitability': STATUS_COMPUTED, 'land_cover': STATUS_COMPUTED if substrate_status == STATUS_DECLARED else STATUS_PENDING, 'land_cover_hard_substrate': substrate_status}
    if status.get('family_temperature') == STATUS_PENDING or status.get('water_state') == STATUS_PENDING:
        field_status['suitability'] = STATUS_PENDING
        field_status['land_cover'] = STATUS_PENDING
        cover_names = _i28_np.full(cells, 'pending', dtype=object).astype(str)
    return {'schema': LAND_COVER_SCHEMA, 'algorithm': LAND_COVER_ALGORITHM, 'columns': int(cells), 'horizontal_area_m2': float(horizontal_area_m2), 'soil_thickness_bulk_m': thickness, 'soil_water_capacity_mm': capacity, 'soil_water_capacity_source': capacity_source, 'water_capacity_reference_mm': capacity_reference, 'water_state_total_mm': water_total, 'water_state_shape': water_shape_reported, 'water_ratio_of_capacity': water_ratio, 'family_temperature_c': temperature, 'normalised_temperature': normalised_temperature, 'normalised_water': normalised_water, 'normalised_material': normalised_material, 'suitability': suitability, 'land_cover_index': cover, 'land_cover': cover_names, 'cover_classes': list(COVER_CLASSES), 'porosity': pore, 'parameters_identity_sha256': params.identity_sha256, 'parameters': {name: getattr(params, name) for name in params.__dataclass_fields__}, 'identity': {'inputs_sha256': _digest({'parent_solid_m3': _array_digest(solid), 'porosity': _array_digest(pore), 'family_temperature_c': _array_digest(temperature), 'water_state': _array_digest(water), 'horizontal_area_m2': float(horizontal_area_m2), 'parameters': params.identity_sha256})}, 'field_status': field_status, 'units': {'soil_thickness_bulk_m': 'm_bulk', 'soil_water_capacity_mm': 'mm', 'water_state_total_mm': 'mm', 'family_temperature_c': 'degC', 'porosity': '1', 'suitability': '1_normalised', 'normalised_temperature': '1_normalised', 'normalised_water': '1_normalised', 'normalised_material': '1_normalised', 'water_ratio_of_capacity': '1_ratio', 'land_cover': 'class_label'}, 'limitations': list(LAND_COVER_LIMITATIONS)}

def land_cover_describe():
    """Static declaration for review (no numeric effect)."""
    return {'schema': LAND_COVER_SCHEMA, 'algorithm': LAND_COVER_ALGORITHM, 'cover_classes': list(COVER_CLASSES), 'thickness_conversion': 'bulk_thickness_m = solid_m3 / ((1 - porosity) * horizontal_area_m2); dividing by the area alone gives an equivalent solid thickness', 'capacity_conversion': 'soil_water_capacity_mm = bulk_thickness_m * 1000 * available_water_fraction; a capacity, never a stock', 'separated_products': ['soil', 'suitability', 'land_cover'], 'never': ['solid volume divided by area reported as a soil thickness', 'capacity reported as a water stock, or the stock as a capacity', 'land cover derived from annual precipitation alone', 'a pending input silently read as zero', 'a reference point snapped onto a cell centre', 'vegetation growth, biomass or succession', 'a weathering rate (G9 owns it)'], 'parameters': {name: getattr(LandCoverParameters(), name) for name in LandCoverParameters.__dataclass_fields__}, 'limitations': list(LAND_COVER_LIMITATIONS)}
SNOW_ICE_SCHEMA = 'seasonal-snow-ice-v1'
LOGICAL_VERSION = 'seasonal-swe-degree-day-v1'
SNOW_ICE_ALGORITHM = 'seasonal-swe-degree-day'
CELL_AREA_M2 = 900.0
NATIVE_SPACING_M = 30.0
SNOW_ICE_MAX_CELLS = 65536
MAX_BUCKET_STEP_S = 3600.0
SNOW_ICE_TEMPERATURE_SOURCES = ('monthly_mean', 'declared_interval')
MELT_ORDERS = ('melt_then_sublimation', 'sublimation_then_melt')
SNOW_ICE_PHASE_SOURCE = 'metric_pet_et.liquid_fraction (declared freezing threshold, month-seconds weighted); this module adds no second phase formula'
CALENDAR_SOURCE = 'metric_pet_et.calendar_month_seconds (fixed 365-day month table); a monthly total is never turned into a single storm'
SUBLIMATION_POLICY = 'an explicitly declared demand in mm per day, applied in the declared order and hard limited by the SWE that is actually left; it is not derived from temperature alone and is never the same water as PET'
NOT_MODELLED = ('snow_depth', 'glacier', 'ice_flow', 'ice_erosion', 'hydraulic_state', 'channel_routing', 'calibration', 'one_metre_accuracy')
SNOW_ICE_LIMITATIONS = ('seasonal snow store only: no snow depth (no density), no glacier, no ice flow, no ice erosion', 'no verdict on whether this snow is a glacier; multi-year net balance is not modelled', 'degree-day coefficients and the sublimation demand are declared engineering assumptions, uncalibrated, carried in the identity', 'a monthly total is never converted into one storm event; the caller declares interval depths on explicit physical time edges', 'the liquid path enters the existing soil bucket once; this module adds no second bucket, no channel routing and no hydraulic state', 'the bucket accepts at most a 3600 s step, so a longer snow interval is consumed in fixed sub-steps and the module reports that split; the old limit is not relaxed')

def _snow_ice_finite(value, name, *, minimum=None, maximum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, _i29_np.integer, _i29_np.floating)):
        raise ValueError('%s must be numeric' % name)
    number = float(value)
    if not _i29_math.isfinite(number):
        raise ValueError('%s must be finite' % name)
    if positive and number <= 0.0:
        raise ValueError('%s must be positive' % name)
    if minimum is not None and number < minimum:
        raise ValueError('%s must be >= %r' % (name, minimum))
    if maximum is not None and number > maximum:
        raise ValueError('%s must be <= %r' % (name, maximum))
    return number

@_i29_dataclass(frozen=True)
class SnowParameters:
    """Declared engineering parameters. Uncalibrated; every value enters the identity."""
    freezing_threshold_c: float = 0.0
    degree_day_melt_mm_per_day_c: float = 4.0
    sublimation_demand_mm_per_day: float = 0.5
    max_swe_mm: float = 5000.0
    min_melt_temperature_c: float = 0.0
    phase_parameters: PetEtParameters = _i29_field(default_factory=PetEtParameters)

    def __post_init__(self):
        _snow_ice_finite(self.freezing_threshold_c, 'freezing_threshold_c')
        _snow_ice_finite(self.degree_day_melt_mm_per_day_c, 'degree_day_melt_mm_per_day_c', minimum=0.0)
        _snow_ice_finite(self.sublimation_demand_mm_per_day, 'sublimation_demand_mm_per_day', minimum=0.0)
        _snow_ice_finite(self.max_swe_mm, 'max_swe_mm', positive=True)
        _snow_ice_finite(self.min_melt_temperature_c, 'min_melt_temperature_c')
        if not isinstance(self.phase_parameters, PetEtParameters):
            raise ValueError('phase_parameters must be PetEtParameters')
        if self.phase_parameters.freezing_threshold_c != self.freezing_threshold_c:
            raise ValueError('the phase threshold must be the one the adapter is given; two thresholds would be two phases')

    def identity(self):
        payload = _i29_asdict(self)
        payload['phase_parameters'] = _i29_asdict(self.phase_parameters)
        payload['phase_parameters'].pop('runoff', None)
        return payload

def _edges(time_edges_s):
    edges = _i29_np.asarray(time_edges_s, _i29_np.float64)
    if edges.ndim != 1 or edges.size < 2 or edges.size - 1 > MAX_INTERVALS:
        raise ValueError('time_edges_s must be 1D with 1..%d intervals' % MAX_INTERVALS)
    if not _i29_np.isfinite(edges).all() or _i29_np.any(_i29_np.diff(edges) <= 0.0):
        raise ValueError('time_edges_s must be finite and strictly increasing')
    return edges

def _cells(values, name, shape):
    array = _i29_np.asarray(values, _i29_np.float64)
    if array.shape != shape:
        raise ValueError('%s must have shape %s, got %s' % (name, list(shape), list(array.shape)))
    if not _i29_np.isfinite(array).all():
        raise ValueError('%s must be finite' % name)
    return array

def _points(x_m, z_m):
    x = _i29_np.asarray(x_m, _i29_np.float64).reshape(-1)
    z = _i29_np.asarray(z_m, _i29_np.float64).reshape(-1)
    if x.shape != z.shape or x.size == 0 or x.size > SNOW_ICE_MAX_CELLS:
        raise ValueError('x_m/z_m must be 1..%d matching points' % SNOW_ICE_MAX_CELLS)
    if not _i29_np.isfinite(x).all() or not _i29_np.isfinite(z).all():
        raise ValueError('world coordinates must be finite')
    return (x, z)

def _temperature_intervals(temperature_c, temperature_source, edges, parameters):
    """``(T, N)`` interval mean temperature and ``(T, N)`` liquid fraction.

    Two declared contracts, and never a silent conversion between them:

    ``monthly_mean``       ``(12, N)`` monthly means; the interval mean is the elapsed-second
                          weighted average from the repository's own calendar, and the phase
                          mixture comes from ``metric_pet_et.liquid_fraction``. That public
                          entry reads the same 365-day clock through the PET adapter's own
                          ``dt_s <= 3600`` gate, so **every interval must be at most one hour**
                          on this contract. A longer interval is refused rather than silently
                          split: the bucket gate is not widened, and this module does not carry
                          a second phase formula to work around it.
    ``declared_interval``  ``(T, N)`` one declared mean per interval; the phase is the same
                          declared threshold applied to that interval mean. A ``(T, N)``
                          array is **never** handed to ``liquid_fraction``, which requires the
                          twelve-month axis. This contract has **no** per-interval length
                          ceiling; the bucket consumption is split separately.
    """
    intervals = int(edges.size - 1)
    if temperature_source not in SNOW_ICE_TEMPERATURE_SOURCES:
        raise ValueError('temperature_source must be one of %s' % (SNOW_ICE_TEMPERATURE_SOURCES,))
    array = _i29_np.asarray(temperature_c, _i29_np.float64)
    if temperature_source == 'monthly_mean':
        if array.ndim != 2 or array.shape[0] != 12:
            raise ValueError('monthly_mean temperature must be [12, N]')
        cells = array.shape[1]
        _cells(array, 'monthly_temperature_c', (12, cells))
        longest = float(_i29_np.max(_i29_np.diff(edges)))
        if longest > MAX_BUCKET_STEP_S:
            raise ValueError("the monthly_mean contract reads the calendar through metric_pet_et, whose own gate refuses dt_s > %r s; the longest interval here is %r s. Use edges of at most one hour, or declare per-interval temperatures with temperature_source='declared_interval', which has no such ceiling. The PET gate is not widened here." % (MAX_BUCKET_STEP_S, longest))
        month_seconds = calendar_month_seconds(edges)
        total = month_seconds.sum(axis=1)
        if _i29_np.any(total <= 0.0):
            raise ValueError('every interval must spend positive time inside the calendar')
        interval_temperature = month_seconds @ array / total[:, None]
        fraction = liquid_fraction(array, month_seconds, parameters.phase_parameters)
        return (interval_temperature, fraction)
    if array.ndim != 2 or array.shape[0] != intervals:
        raise ValueError('declared_interval temperature must be [intervals, N] = [%d, N]' % intervals)
    cells = array.shape[1]
    _cells(array, 'interval_temperature_c', (intervals, cells))
    fraction = (array >= parameters.freezing_threshold_c).astype(_i29_np.float64)
    return (array, fraction)

def advance_snow_ice(*, swe_start_mm, temperature_c, precip_mm, time_edges_s, x_m, z_m, temperature_source='monthly_mean', order='melt_then_sublimation', parameters=None):
    """Advance one seasonal snow store per cell over the declared intervals.

    ``precip_mm`` is the **depth per interval** (``[intervals, N]``), not a rate and not a
    monthly total: the caller declares it on the same physical edges it declares the
    temperature on.

    The reported liquid path is ``liquid_to_land_mm = liquid_precip_mm + melt_mm``; both parts
    are also returned separately so a consumer can attribute them. That single liquid field
    is what the soil bucket takes (:func:`advance_soil_with_liquid`), and the melt is **not**
    handed to the PET adapter as well: the phase decision has already been made here, and
    sending melt back through the adapter would freeze it a second time on a cold month mean.
    """
    from terrain_pipeline.artifacts.contracts import array_hash as _i29_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i29_digest
    edges = _edges(time_edges_s)
    intervals = int(edges.size - 1)
    parameters = SnowParameters() if parameters is None else parameters
    if not isinstance(parameters, SnowParameters):
        raise ValueError('parameters must be SnowParameters')
    if order not in MELT_ORDERS:
        raise ValueError('order must be one of %s' % (MELT_ORDERS,))
    temperature, fraction = _temperature_intervals(temperature_c, temperature_source, edges, parameters)
    cells = temperature.shape[1]
    x, z = _points(x_m, z_m)
    if x.size != cells:
        raise ValueError('one world point per cell is required: %d points for %d cells' % (x.size, cells))
    start = _i29_np.asarray(swe_start_mm, _i29_np.float64)
    if start.shape != (cells,):
        raise ValueError('swe_start_mm must be one value per cell')
    if not _i29_np.isfinite(start).all() or _i29_np.any(start < 0.0):
        raise ValueError('swe_start_mm must be finite and nonnegative')
    if _i29_np.any(start > parameters.max_swe_mm):
        raise ValueError('swe_start_mm exceeds the declared ceiling %r mm' % parameters.max_swe_mm)
    precip = _cells(precip_mm, 'precip_mm', (intervals, cells))
    if _i29_np.any(precip < 0.0):
        raise ValueError('precip_mm must be nonnegative')
    dt_days = _i29_np.diff(edges) / 86400.0
    swe = _i29_np.zeros((intervals + 1, cells), _i29_np.float64)
    swe[0] = start
    solid = _i29_np.zeros((intervals, cells), _i29_np.float64)
    liquid = _i29_np.zeros((intervals, cells), _i29_np.float64)
    melt = _i29_np.zeros((intervals, cells), _i29_np.float64)
    sublimation = _i29_np.zeros((intervals, cells), _i29_np.float64)
    for index in range(intervals):
        solid[index] = (1.0 - fraction[index]) * precip[index]
        liquid[index] = fraction[index] * precip[index]
        available = swe[index] + solid[index]
        if _i29_np.any(available > parameters.max_swe_mm):
            raise ValueError('interval %d would exceed the declared SWE ceiling %r mm' % (index, parameters.max_swe_mm))
        potential_melt = parameters.degree_day_melt_mm_per_day_c * _i29_np.maximum(temperature[index] - parameters.min_melt_temperature_c, 0.0) * dt_days[index]
        demand = parameters.sublimation_demand_mm_per_day * dt_days[index]
        if order == 'melt_then_sublimation':
            removed_melt = _i29_np.minimum(potential_melt, available)
            removed_sublimation = _i29_np.minimum(demand, available - removed_melt)
        else:
            removed_sublimation = _i29_np.minimum(demand, available)
            removed_melt = _i29_np.minimum(potential_melt, available - removed_sublimation)
        melt[index] = removed_melt
        sublimation[index] = removed_sublimation
        swe[index + 1] = available - removed_melt - removed_sublimation
    if _i29_np.any(swe < 0.0):
        raise RuntimeError('the snow store went negative')
    liquid_to_land = liquid + melt
    residual = swe[-1] - swe[0] - solid.sum(axis=0) + melt.sum(axis=0) + sublimation.sum(axis=0)
    if _i29_np.abs(residual).max() > 1e-09:
        raise RuntimeError('the SWE ledger does not close (max |residual| = %r mm)' % float(_i29_np.abs(residual).max()))
    payload = {'schema': SNOW_ICE_SCHEMA, 'logical_version': LOGICAL_VERSION, 'algorithm': SNOW_ICE_ALGORITHM, 'temperature_source': temperature_source, 'order': order, 'parameters': parameters.identity(), 'phase_source': SNOW_ICE_PHASE_SOURCE, 'calendar_source': CALENDAR_SOURCE, 'sublimation_policy': SUBLIMATION_POLICY, 'time_edges_s': [float(v) for v in edges], 'x_m': [float(v) for v in x], 'z_m': [float(v) for v in z], 'cell_area_m2': CELL_AREA_M2, 'spacing_m': NATIVE_SPACING_M, 'claims_denied': {'snow_depth': True, 'glacier': True, 'ice_flow': True, 'ice_erosion': True, 'hydraulics': True, 'channel': True, 'calibrated': True, 'one_metre_accuracy': True}}
    arrays = {'swe_edge_mm': swe, 'solid_precip_mm': solid, 'liquid_precip_mm': liquid, 'melt_mm': melt, 'sublimation_mm': sublimation, 'liquid_to_land_mm': liquid_to_land}
    return {'arrays': arrays, 'ledger_mm': {'swe_start_mm': [float(v) for v in swe[0]], 'swe_end_mm': [float(v) for v in swe[-1]], 'solid_precip_mm_total': [float(v) for v in solid.sum(axis=0)], 'liquid_precip_mm_total': [float(v) for v in liquid.sum(axis=0)], 'melt_mm_total': [float(v) for v in melt.sum(axis=0)], 'sublimation_mm_total': [float(v) for v in sublimation.sum(axis=0)], 'liquid_to_land_mm_total': [float(v) for v in liquid_to_land.sum(axis=0)], 'residual_mm': [float(v) for v in residual], 'max_abs_residual_mm': float(_i29_np.abs(residual).max()), 'sublimation_leaves_the_cell': True, 'note': 'SWE closes as swe_end - swe_start = solid - melt - sublimation; the melt and the direct liquid precipitation both go to the land surface once, and the sublimation does not'}, 'metadata': payload, 'identity_sha256': _i29_digest({'metadata': payload, 'arrays': {name: _i29_array_hash(value) for name, value in sorted(arrays.items())}})}

def bucket_substeps(dt_s):
    """Fixed sub-step split so the existing bucket's own ``dt_s <= 3600`` bound is honoured."""
    dt = _snow_ice_finite(dt_s, 'dt_s', positive=True)
    count = int(_i29_math.ceil(dt / MAX_BUCKET_STEP_S))
    if count < 1:
        raise ValueError('at least one sub-step is required')
    return [dt / count for _ in range(count)]

def advance_soil_with_liquid(liquid_to_land_mm, time_edges_s, states, *, x_m, z_m, runoff_parameters=None, max_step_s=MAX_BUCKET_STEP_S):
    """Consume the liquid path **once** through the repository's existing soil bucket.

    ``liquid_to_land_mm`` is ``[intervals, N]`` and already includes melt; it is converted to
    the bucket's ``mm/h`` rate per interval and stepped in fixed sub-steps no longer than the
    bucket's declared ceiling. The bucket's own limit is never relaxed, and a longer snow
    interval is reported as a split rather than silently shortened.

    Only :func:`advance_soil` is called: the melt is not re-phased and not passed to the PET
    adapter, so no water is frozen twice and none is deducted twice.
    """
    from terrain_pipeline.runoff import RunoffParameters as _i29_RunoffParameters
    from terrain_pipeline.climate_forcing import advance_soil as _x47_advance_soil
    edges = _edges(time_edges_s)
    intervals = int(edges.size - 1)
    liquid = _i29_np.asarray(liquid_to_land_mm, _i29_np.float64)
    if liquid.ndim != 2 or liquid.shape[0] != intervals:
        raise ValueError('liquid_to_land_mm must be [intervals, N]')
    if not _i29_np.isfinite(liquid).all() or _i29_np.any(liquid < 0.0):
        raise ValueError('liquid_to_land_mm must be finite and nonnegative')
    cells = liquid.shape[1]
    x, z = _points(x_m, z_m)
    if x.size != cells:
        raise ValueError('one world point per cell is required')
    parameters = runoff_parameters or _i29_RunoffParameters()
    if not isinstance(parameters, _i29_RunoffParameters):
        raise ValueError('runoff_parameters must be RunoffParameters')
    if max_step_s > MAX_BUCKET_STEP_S:
        raise ValueError('the bucket ceiling is %r s; it is never raised here' % MAX_BUCKET_STEP_S)
    state = _i29_np.array(states, _i29_np.float64, copy=True)
    if state.shape != (3, cells):
        raise ValueError('states must be [3, N] (soil, fast, slow)')
    if not _i29_np.isfinite(state).all() or _i29_np.any(state < 0.0):
        raise ValueError('states must be finite and nonnegative')
    released = _i29_np.zeros((intervals, cells), _i29_np.float64)
    evaporated = _i29_np.zeros((intervals, cells), _i29_np.float64)
    change = _i29_np.zeros((intervals, cells), _i29_np.float64)
    substeps_used = []
    for index in range(intervals):
        span = float(_i29_np.diff(edges)[index])
        if span > max_step_s:
            count = int(_i29_math.ceil(span / max_step_s))
            parts = [span / count] * count
        else:
            parts = [span]
        rate = liquid[index] / (span / 3600.0)
        for dt in parts:
            state, release, et, delta = _x47_advance_soil(rate, state, dt_s=float(dt), parameters=parameters)
            released[index] += release
            evaporated[index] += et
            change[index] += delta
        substeps_used.append(len(parts))
    return {'states': state, 'released_mm': released, 'evaporated_mm': evaporated, 'state_change_mm': change, 'substeps_per_interval': substeps_used, 'max_step_s': float(max_step_s), 'bucket_module': BUCKET_MODULE, 'note': 'the liquid path is consumed once by the existing bucket; the melt is not sent back through the PET adapter, so nothing is re-frozen or deducted twice'}

def snow_ice_describe():
    return {'schema': SNOW_ICE_SCHEMA, 'logical_version': LOGICAL_VERSION, 'algorithm': SNOW_ICE_ALGORITHM, 'temperature_sources': list(SNOW_ICE_TEMPERATURE_SOURCES), 'melt_orders': list(MELT_ORDERS), 'phase_source': SNOW_ICE_PHASE_SOURCE, 'calendar_source': CALENDAR_SOURCE, 'sublimation_policy': SUBLIMATION_POLICY, 'not_modelled': list(NOT_MODELLED), 'monthly_mean_max_interval_s': MAX_BUCKET_STEP_S, 'limitations': list(SNOW_ICE_LIMITATIONS), 'default_parameters': SnowParameters().identity(), 'bucket_module': BUCKET_MODULE, 'max_bucket_step_s': MAX_BUCKET_STEP_S, 'cells_bound': SNOW_ICE_MAX_CELLS, 'intervals_bound': MAX_INTERVALS, 'cell_area_m2': CELL_AREA_M2, 'spacing_m': NATIVE_SPACING_M}
SEASONAL_COUPLING_ALGORITHM = 'finite-environment-seasonal-coupling-v1'
ALGORITHM_V2 = 'finite-environment-seasonal-coupling-v2'
ALGORITHMS = (SEASONAL_COUPLING_ALGORITHM, ALGORITHM_V2)
NETWORK_ALGORITHM = 'environment-saved-network-frozen-v1'

def is_seasonal(product):
    return product.get('algorithm') in ALGORITHMS

def _climate():
    import terrain_pipeline.environment_regional_hydraulics as environment_climate_driver
    return environment_climate_driver

def driver_slices(context, driver):
    shape = _i30_np.asarray(context['height_m']).shape
    origin = context['origin_native_xz']
    base = driver['metadata']['origin_native_xz']
    extent = driver['metadata']['shape_zx']
    col, row = (int(origin[0] - base[0]), int(origin[1] - base[1]))
    if row < 0 or col < 0 or row + shape[0] > extent[0] or (col + shape[1] > extent[1]):
        raise ValueError('product window must stay inside the pinned climate support')
    return (slice(row, row + shape[0]), slice(col, col + shape[1]))

def initialize(product, driver, climate_state=None, parameters=None, *, material_source, version=1):
    from terrain_pipeline.runoff import RunoffParameters as _i30_RunoffParameters
    from terrain_pipeline.environment_contract import array as _x48_array
    climate = _climate()
    climate.validate_climate_driver(driver)
    config = _i30_deepcopy(parameters or {})
    if set(config) - {'runoff', 'pet', 'snow', 'initial_swe_mm', 'initial_swe_source', 'initial_time_s'}:
        raise ValueError('unsupported seasonal configuration')
    initial_time = float(config.get('initial_time_s', 0.0 if climate_state is None else climate_state['metadata']['time_s']))
    if not _i30_math.isfinite(initial_time) or initial_time < 0.0:
        raise ValueError('finite nonnegative seasonal initial physical time required')
    product['time_s'] = initial_time
    climate_state = climate.initial_climate_state(driver, time_s=initial_time) if climate_state is None else climate_state
    climate.validate_climate_state(climate_state, driver)
    if climate_state['metadata']['time_s'] != product['time_s']:
        raise ValueError('climate and environment physical clocks must match')
    window = driver_slices(product['context'], driver)
    ctx = product['context']
    shape = ctx['height_m'].shape
    if float(ctx['spacing_m']) != 30.0:
        raise ValueError('seasonal mode requires native 30m water accounts')
    if driver['metadata'].get('world_seed', 20261020) != ctx['world_seed']:
        raise ValueError('climate and environment world seeds must match')
    validate_source_binding(product, driver)
    runoff = _i30_RunoffParameters(**config.get('runoff', {}))
    pet = PetEtParameters(runoff=runoff, **config.get('pet', {}))
    snow_values = dict(config.get('snow', {}))
    snow_values['phase_parameters'] = pet
    snow_values.setdefault('freezing_threshold_c', pet.freezing_threshold_c)
    snow = SnowParameters(**snow_values)
    active = ctx['valid_mask'] & ~ctx['ocean_mask'] & ~ctx['protected_mask']
    swe = _x48_array(config.get('initial_swe_mm', 0.0), shape, 'initial_swe_mm') * active
    if _i30_np.any(swe > snow.max_swe_mm):
        raise ValueError('initial SWE exceeds declared ceiling')
    source = config.get('initial_swe_source', 'declared_zero_no_observed_snow_initialization')
    if swe.any() and (not isinstance(source, str) or not source.strip() or 'initial_swe_source' not in config):
        raise ValueError('nonzero initial snow requires an explicit initial_swe_source')
    if _i30_np.any(product['states']['frozen_ground']['snow_swe_m']):
        raise ValueError('G7 owns seasonal snow; G12 initial snow_swe_m must be zero')
    if _i30_np.any(product['states']['soil_chemistry']['water_m3'] / 0.9 > runoff.soil_capacity_mm):
        raise ValueError('initial chemistry soil water exceeds G5 capacity')
    product['algorithm'] = SEASONAL_COUPLING_ALGORITHM if version == 1 else ALGORITHM_V2
    product['seasonal'] = {'climate_driver': _i30_deepcopy(driver), 'climate_state': _i30_deepcopy(climate_state), 'material_source': _i30_deepcopy(material_source), 'snow_swe_mm': swe, 'fast_mm': _i30_np.full(shape, runoff.initial_fast_mm) * active, 'slow_mm': _i30_np.full(shape, runoff.initial_slow_mm) * active, 'pending_et_kg': _i30_np.zeros(tuple(driver['metadata']['shape_zx'])), 'initial_swe_source': source, 'initial_time_s': initial_time, 'runoff_parameters': _i30_asdict(runoff), 'pet_parameters': _i30_asdict(pet), 'snow_parameters': snow.identity(), 'kernel_sources': _source_identities(), 'network_policy': 'frozen_saved_receiver_and_height; derived bed changes are diagnostics', 'soil_water_owner': 'states.soil_chemistry.water_m3; G5 fast/slow are separate inventories', 'ground_water_owner': 'G12 liquid/ground ice are separately declared thermal-layer stocks; no rainfall partition', 'temperature_contract': 'G3 monthly-mean integral on real interval, not measured short-time temperature', 'pet_policy': 'existing monthly temperature-index PET capped by radiation evaporation energy', 'G2_status': 'native-anchor G2 hardness/solubility drive G9; bedrock porosity read-only; permeability/layer geometry pending'}
    product['parameters']['rain_partition'] = 'G7 phase once; liquid enters existing G5; release enters saved network once'
    product['limitations'].extend(['seasonal mode uses declared initial SWE, never fabricated cold/warm temperatures', 'G5 slow store owns percolation; it is not also injected into groundwater', 'seasonal mode freezes saved water geometry and receiver; bed changes are diagnostic only', 'G7 degree-day melt has its own empirical energy closure, not a complete radiation melt model', 'seasonal mode excludes soil/coast exchange packets; coastal river-mouth exchange remains active', 'G2 extended permeability and layer geometry remain pending; sampled bedrock porosity does not replace regolith porosity'])
    if version == 2:
        pass  # Reference the existing consolidated global directly.
        product['seasonal']['land_cover'] = assess(product)
        product['seasonal']['land_cover_policy'] = 'allocated G9 soil -> G6 -> G15 actual growth support; parent potential separate'
    return product

def advance_driver(product, forcing, dt_s):
    if not 0.0 < dt_s <= 3600.0:
        raise ValueError('seasonal physical interval must be positive and at most 3600s')
    if {'rainfall_m_s', 'air_temperature_c'} & set(forcing):
        raise ValueError('seasonal rain and temperature come only from the pinned climate driver')
    seasonal = product['seasonal']
    request = _i30_deepcopy(forcing.get('climate', {}))
    if not isinstance(request, dict) or set(request) - {'external_inflow_kg_per_s', 'wind_speed_m_s', 'uplift_gain'}:
        raise ValueError('unsupported seasonal climate boundary fields')
    if 'external_inflow_kg_per_s' not in request:
        raise ValueError('seasonal climate requires an explicitly declared external_inflow_kg_per_s boundary')
    request = {'wind_speed_m_s': 5.0, 'uplift_gain': 1.0, **request}
    if _i30_np.any(_i30_np.asarray(forcing.get('soil_chemistry', {}).get('drainage_m3_s', 0.0))):
        raise ValueError('seasonal soil drainage is owned by G5 percolation')
    if _i30_np.any(_i30_np.asarray(forcing.get('coastal_exchange', {}).get('soil_exchange_m3_s', 0.0))):
        raise ValueError('seasonal soil/coast exchange packets are outside this mode')
    if _i30_np.any(product['pending_packets']['soil_water_m3']) or _i30_np.any(product['pending_packets']['soil_salt_kg']):
        raise ValueError('seasonal mode cannot consume external coastal soil packets')
    recycled = seasonal['pending_et_kg'].copy()
    state, driving = _climate().advance_climate_driver(seasonal['climate_driver'], seasonal['climate_state'], product['time_s'] + dt_s, et_recycle_kg=recycled, **request)
    seasonal['climate_state'] = state
    seasonal['pending_et_kg'] = _i30_np.zeros_like(recycled)
    window = driver_slices(product['context'], seasonal['climate_driver'])
    result = _i30_deepcopy(forcing)
    for key in ('rainfall_m_s', 'air_temperature_c'):
        result[key] = _i30_np.asarray(driving[key])[window].copy()
    result['wind_x_m_s'] = _i30_np.asarray(seasonal['climate_driver']['arrays']['wind_bearing_x'])[window] * float(request.get('wind_speed_m_s', 5.0))
    result['wind_z_m_s'] = _i30_np.asarray(seasonal['climate_driver']['arrays']['wind_bearing_z'])[window] * float(request.get('wind_speed_m_s', 5.0))
    return (result, driving, recycled)

def snow_and_bucket(product, forcing, dt_s, radiation, infiltration_factor):
    from terrain_pipeline.runoff import RunoffParameters as _i30_RunoffParameters
    from terrain_pipeline.climate_forcing import advance_soil as _x49_advance_soil
    seasonal, ctx = (product['seasonal'], product['context'])
    shape = ctx['height_m'].shape
    active = ctx['valid_mask'] & ~ctx['ocean_mask'] & ~ctx['protected_mask']
    area = float(ctx['spacing_m']) ** 2
    edges = _i30_np.array([product['time_s'], product['time_s'] + dt_s])
    runoff = _i30_RunoffParameters(**seasonal['runoff_parameters'])
    pet_values = dict(seasonal['pet_parameters'])
    pet_values.pop('runoff')
    pet = PetEtParameters(runoff=runoff, **pet_values)
    snow_values = dict(seasonal['snow_parameters'])
    snow_values['phase_parameters'] = pet
    snow = advance_snow_ice(swe_start_mm=seasonal['snow_swe_mm'].ravel(), temperature_c=_i30_np.asarray(forcing['air_temperature_c']).reshape(1, -1), precip_mm=(_i30_np.asarray(forcing['rainfall_m_s']) * dt_s * 1000.0 * active).reshape(1, -1), time_edges_s=edges, x_m=ctx['node_x_m'].ravel(), z_m=ctx['node_z_m'].ravel(), temperature_source='declared_interval', parameters=SnowParameters(**snow_values))
    seasonal['snow_swe_mm'] = snow['arrays']['swe_edge_mm'][-1].reshape(shape)
    window = driver_slices(ctx, seasonal['climate_driver'])
    monthly = seasonal['climate_driver']['arrays']['monthly_temperature_c'][:, window[0], window[1]].reshape(12, -1)
    pet_mm = interval_pet_mm(monthly, edges, pet)[0].reshape(shape)
    limited_pet_mm = _i30_np.minimum(pet_mm, radiation['fluxes']['potential_evaporation_m'] * 1000.0) * active
    liquid = snow['arrays']['liquid_to_land_mm'][0].reshape(shape)
    states = _i30_np.stack((product['states']['soil_chemistry']['water_m3'] * 1000.0 / area, seasonal['fast_mm'], seasonal['slow_mm'])).reshape(3, -1)
    rates = limited_pet_mm.ravel() * 3600.0 / dt_s
    capacity = runoff.infiltration_capacity_mm_h * _i30_np.asarray(infiltration_factor).ravel() * active.ravel()
    groups, inverse = _i30_np.unique(_i30_np.stack((rates, capacity), axis=1), axis=0, return_inverse=True)
    updated = _i30_np.empty_like(states)
    arrays = {key: _i30_np.zeros(states.shape[1]) for key in ('infiltration_mm', 'percolation_mm', 'actual_et_mm', 'release_mm', 'fast_release_mm', 'slow_release_mm')}
    for index, (et_rate, infiltration_capacity) in enumerate(groups):
        mask = inverse == index
        params = _i30_replace(runoff, potential_et_mm_h=float(et_rate), infiltration_capacity_mm_h=float(infiltration_capacity))
        next_state, release, et, _, fluxes = _x49_advance_soil(liquid.ravel()[mask] * 3600.0 / dt_s, states[:, mask], dt_s=dt_s, parameters=params, return_fluxes=True)
        updated[:, mask] = next_state
        arrays['infiltration_mm'][mask] = fluxes['infiltration_mm']
        arrays['percolation_mm'][mask] = fluxes['percolation_mm']
        arrays['actual_et_mm'][mask] = et
        arrays['release_mm'][mask] = release
        arrays['fast_release_mm'][mask] = fluxes['fast_release_mm']
        arrays['slow_release_mm'][mask] = fluxes['slow_release_mm']
    seasonal['fast_mm'] = updated[1].reshape(shape)
    seasonal['slow_mm'] = updated[2].reshape(shape)
    volumes = {key.removesuffix('_mm') + '_m3': value.reshape(shape) * area / 1000.0 for key, value in arrays.items()}
    volumes['soil_end_m3'] = updated[0].reshape(shape) * area / 1000.0
    volumes['pet_m3'] = pet_mm * area / 1000.0
    volumes['energy_limited_pet_m3'] = limited_pet_mm * area / 1000.0
    snow_result = {'fluxes': {key.removesuffix('_mm') + '_m3': value[0].reshape(shape) * area / 1000.0 for key, value in snow['arrays'].items() if key != 'swe_edge_mm'}, 'ledger': snow['ledger_mm'], 'metadata': snow['metadata']}
    snow_result['metadata']['temperature_source_detail'] = seasonal['temperature_contract']
    return (snow_result, volumes)

def net_water(entries):
    get = lambda key: float(entries.get(key, 0.0))
    return get('atmosphere_inflow_m3') - get('atmosphere_outflow_m3') - get('precipitation_unmodelled_export_m3') - get('sublimation_m3') + get('ocean_water_input_m3') - get('window_water_export_m3') - get('pumping_m3') - get('external_hydraulic_water_m3')

def validate_source_binding(product, driver):
    source, climate_source = (product['sources'], driver['metadata']['source'])
    for environment_key, climate_key in (('source_world_identity', 'world_identity'), ('registry_sha256', 'registry_sha256'), ('manifest_sha256', 'manifest_sha256')):
        if environment_key not in source or source[environment_key] != climate_source.get(climate_key):
            raise ValueError('climate and environment saved-source binding mismatch: ' + environment_key)
    window = driver_slices(product['context'], driver)
    bed = product['context'].get('source_height_m', product['context']['height_m'])
    if not _i30_np.array_equal(driver['arrays']['elevation_m'][window], bed):
        raise ValueError('climate must use the same saved TD-derived bed as the environment network')

def seasonal_coupling_validate(product):
    from terrain_pipeline.environment_contract import array as _x48_array
    seasonal = product['seasonal']
    climate = _climate()
    climate.validate_climate_driver(seasonal['climate_driver'])
    climate.validate_climate_state(seasonal['climate_state'], seasonal['climate_driver'])
    if seasonal['climate_state']['metadata']['time_s'] != product['time_s']:
        raise ValueError('persistent climate/environment clocks disagree')
    driver_slices(product['context'], seasonal['climate_driver'])
    validate_source_binding(product, seasonal['climate_driver'])
    from terrain_pipeline.geology import validate_material_source as validate_material_source
    validate_material_source(seasonal['material_source'], product['context'])
    shape = product['context']['height_m'].shape
    for key in ('snow_swe_mm', 'fast_mm', 'slow_mm'):
        _x48_array(seasonal[key], shape, key)
    _x48_array(seasonal['pending_et_kg'], tuple(seasonal['climate_driver']['metadata']['shape_zx']), 'pending_et_kg')
    if _i30_np.any(product['states']['frozen_ground']['snow_swe_m']):
        raise ValueError('persistent G7/G12 snow ownership overlaps')
    if product['algorithm'] == ALGORITHM_V2:
        validate_land_cover = land_cover_coupling_validate
        validate_land_cover(product)
SOIL_ALGORITHM = 'synthetic-surface-soil-condition-v1'
Sampler = _i31_Callable[[_i31_np.ndarray, _i31_np.ndarray], _i31_np.ndarray]

@_i31_dataclass(frozen=True)
class SoilParameters:
    """合成土壤条件参数，全部为工程假设量。"""
    slope_spacing_m: float = 10000.0
    soil_slope_scale: float = 0.02
    available_water_span_mm: float = 2200.0
    retention_penalty_per_class: float = 0.25
    drainage_threshold_high: float = 0.75
    drainage_threshold_mid: float = 0.5
    drainage_threshold_low: float = 0.25

    def __post_init__(self) -> None:
        for name in ('slope_spacing_m', 'soil_slope_scale', 'available_water_span_mm', 'retention_penalty_per_class'):
            value = getattr(self, name)
            if not _i31_math.isfinite(value) or value <= 0.0:
                raise ValueError(f'{name} 必须为有限正数，得到 {value!r}')
        low = self.drainage_threshold_low
        mid = self.drainage_threshold_mid
        high = self.drainage_threshold_high
        if not 0.0 < low < mid < high <= 1.0:
            raise ValueError(f'排水阈值必须满足 0 < low < mid < high <= 1，得到 low={low!r}, mid={mid!r}, high={high!r}')

def _resolve_parameters(parameters: _i31_Optional[SoilParameters]) -> SoilParameters:
    if parameters is None:
        return SoilParameters()
    if not isinstance(parameters, SoilParameters):
        raise ValueError('parameters 必须是 SoilParameters 实例或 None')
    return parameters

def _validate_seed(seed: _i31_Any) -> int:
    if isinstance(seed, bool) or not isinstance(seed, (int, _i31_np.integer)):
        raise ValueError(f'seed 必须为非布尔整数，得到 {type(seed).__name__}')
    seed_int = int(seed)
    if not 0 <= seed_int < 2 ** 64:
        raise ValueError(f'seed 必须满足 0 <= seed < 2**64，得到 {seed_int}')
    return seed_int

def _as_broadcast_arrays(x_m: _i31_Any, z_m: _i31_Any) -> tuple[_i31_np.ndarray, _i31_np.ndarray]:
    x = _i31_np.asarray(x_m)
    z = _i31_np.asarray(z_m)
    if not _i31_np.issubdtype(x.dtype, _i31_np.floating):
        x = x.astype(_i31_np.float64, copy=False)
    if not _i31_np.issubdtype(z.dtype, _i31_np.floating):
        z = z.astype(_i31_np.float64, copy=False)
    x, z = _i31_np.broadcast_arrays(x, z)
    if not _i31_np.all(_i31_np.isfinite(x)) or not _i31_np.all(_i31_np.isfinite(z)):
        raise ValueError('x_m/z_m 必须为有限值')
    return (x, z)

def _sample(sampler: Sampler, x: _i31_np.ndarray, z: _i31_np.ndarray, shape: tuple[int, ...]) -> _i31_np.ndarray:
    values = _i31_np.asarray(sampler(x, z), dtype=_i31_np.float64)
    if values.shape != shape:
        raise ValueError(f'采样器返回形状 {values.shape} 与期望形状 {shape} 不符')
    if not _i31_np.all(_i31_np.isfinite(values)):
        raise ValueError('采样器返回值必须为有限值')
    return values

def required_halo_m(parameters: _i31_Optional[SoilParameters]=None) -> float:
    """返回逐点查询所需的外部边缘（halo）宽度，单位 m。

    坡度用中心差分，取 `x ± slope_spacing_m` 与 `z ± slope_spacing_m` 四点，
    故半径等于 `slope_spacing_m`。调用方采样范围不足时必须显式拒绝。
    """
    return float(_resolve_parameters(parameters).slope_spacing_m)

def metadata(seed: _i31_Any, parameters: _i31_Optional[SoilParameters]=None) -> _i31_Dict[str, _i31_Any]:
    """返回合成土壤条件算法的元数据。"""
    params = _resolve_parameters(parameters)
    seed_int = _validate_seed(seed)
    return {'algorithm': SOIL_ALGORITHM, 'seed': seed_int, 'parameters': _i31_dataclasses.asdict(params), 'halo_m': required_halo_m(params), 'synthetic_soil': True, 'measured_soil': False, 'provenance': 'declared engineering assumption; no soil survey, no USDA texture class, no Soil Taxonomy'}

def soil_condition(seed: _i31_Any, x_m: _i31_Any, z_m: _i31_Any, *, elevation: Sampler, bio12_mm: Sampler, thickness_m: Sampler, parameters: _i31_Optional[SoilParameters]=None) -> _i31_Dict[str, _i31_np.ndarray]:
    """逐点计算合成土壤条件：`soil_depth_m`、`drainage`、`available_water`。

    `drainage` 方向为 **0=排水快、3=易滞水**（与"坡度越大越不滞水"一致）。
    """
    _validate_seed(seed)
    params = _resolve_parameters(parameters)
    x, z = _as_broadcast_arrays(x_m, z_m)
    shape = x.shape
    s = params.slope_spacing_m
    h_xp = _sample(elevation, x + s, z, shape)
    h_xm = _sample(elevation, x - s, z, shape)
    h_zp = _sample(elevation, x, z + s, shape)
    h_zm = _sample(elevation, x, z - s, shape)
    dhdx = (h_xp - h_xm) / (2.0 * s)
    dhdz = (h_zp - h_zm) / (2.0 * s)
    slope = _i31_np.hypot(dhdx, dhdz)
    thickness = _sample(thickness_m, x, z, shape)
    precipitation = _sample(bio12_mm, x, z, shape)
    if _i31_np.any(thickness < 0.0):
        raise ValueError('thickness_m 必须非负')
    if _i31_np.any(precipitation < 0.0):
        raise ValueError('bio12_mm 必须非负')
    soil_depth_m = thickness * (1.0 / (1.0 + (slope / params.soil_slope_scale) ** 2))
    wetness = _i31_np.clip(precipitation / params.available_water_span_mm, 0.0, 1.0)
    flatness = 1.0 - _i31_np.clip(slope / params.soil_slope_scale, 0.0, 1.0)
    waterlog_index = flatness * wetness
    drainage = _i31_np.full(shape, 0, dtype=_i31_np.int64)
    drainage = _i31_np.where(waterlog_index >= params.drainage_threshold_high, 3, drainage)
    drainage = _i31_np.where((waterlog_index >= params.drainage_threshold_mid) & (waterlog_index < params.drainage_threshold_high), 2, drainage)
    drainage = _i31_np.where((waterlog_index >= params.drainage_threshold_low) & (waterlog_index < params.drainage_threshold_mid), 1, drainage)
    available_water = _i31_np.clip(wetness * (1.0 - params.retention_penalty_per_class * drainage.astype(_i31_np.float64)), 0.0, 1.0)
    if _i31_np.any(soil_depth_m > thickness + 1e-12):
        raise ValueError('soil_depth_m 不得超过 thickness_m')
    return {'soil_depth_m': soil_depth_m, 'drainage': drainage, 'available_water': available_water}
LAND_COVER_COUPLING_ALGORITHM = 'environment-delivered-soil-land-cover-v1'

def assess(product):
    pass  # Reference the existing consolidated global directly.
    ctx, states, seasonal = (product['context'], product['states'], product['seasonal'])
    shape = ctx['height_m'].shape
    area = float(ctx['spacing_m']) ** 2
    window = driver_slices(ctx, seasonal['climate_driver'])
    monthly = seasonal['climate_driver']['arrays']['monthly_temperature_c'][:, window[0], window[1]]
    annual = monthly.mean(axis=0)
    active = ctx['valid_mask'] & ~ctx['ocean_mask'] & ~ctx['protected_mask']
    soil = states['mass']['soil_solid_m3']
    result = assess_land_cover(parent_solid_m3=soil.ravel(), porosity=states['mass']['regolith_porosity'].ravel(), horizontal_area_m2=area, family_temperature_c=annual.ravel(), water_state_mm=(states['soil_chemistry']['water_m3'] * 1000.0 / area).ravel(), hard_substrate=(soil <= 0.0).ravel(), parameters=LandCoverParameters(), status={'material': 'computed', 'family_temperature': 'computed', 'water_state': 'computed'})
    result['land_cover'] = result['land_cover'].tolist()
    for key, value in result.items():
        if isinstance(value, _i32_np.ndarray) and value.size == soil.size:
            result[key] = value.reshape(shape)
    result['material_solid_m3'] = soil.copy()
    result['unallocated_parent_potential_solid_m3'] = states['mass']['parent_solid_m3'].copy()
    result['growth_support_factor'] = result['suitability'] * result['normalised_material'] * active
    result['active_mask'] = active
    result['adapter'] = {'algorithm': LAND_COVER_COUPLING_ALGORITHM, 'material_source': 'G9 allocated soil_solid_m3 only; parent remains unallocated regolith potential', 'porosity_source': 'mass.regolith_porosity, not sampled bedrock porosity', 'water_source': 'G5 sole root-zone soil water; fast/slow excluded from suitability', 'temperature_source': 'arithmetic mean of original G3 twelve monthly means', 'consumer': 'growth_support_factor scales G15 plant stress; resulting roots/roughness feed existing consumers'}
    return result

def land_cover_coupling_validate(product):
    record = product['seasonal']['land_cover']
    shape = product['context']['height_m'].shape
    for key in ('soil_thickness_bulk_m', 'soil_water_capacity_mm', 'suitability', 'land_cover_index', 'growth_support_factor'):
        values = _i32_np.asarray(record[key])
        if values.shape != shape or not _i32_np.isfinite(values).all():
            raise ValueError('invalid persistent G6 field: ' + key)
    if not _i32_np.array_equal(record['material_solid_m3'], product['states']['mass']['soil_solid_m3']):
        raise ValueError('G6 delivered-soil source differs from current G9 inventory')
    if not _i32_np.array_equal(record['porosity'], product['states']['mass']['regolith_porosity']):
        raise ValueError('G6 must use the current regolith porosity')

def query(product, row, col):
    record = product['seasonal']['land_cover']
    index = int(record['land_cover_index'][row, col])
    result = {key: float(record[key][row, col]) for key in ('soil_thickness_bulk_m', 'soil_water_capacity_mm', 'suitability', 'growth_support_factor', 'material_solid_m3', 'unallocated_parent_potential_solid_m3', 'porosity')}
    result.update(land_cover_index=index, land_cover=record['cover_classes'][index], active=bool(record['active_mask'][row, col]), adapter=_i32_deepcopy(record['adapter']))
    return result

def snapshot(product, *, city_name='saved seasonal environment'):
    """Assemble the completed same-anchor fields without sampling or advancing."""
    import terrain_pipeline.environment_product as api
    import terrain_pipeline.environment_product as world
    if 'land_cover' not in product.get('seasonal', {}):
        raise ValueError('a completed seasonal-v2 G6 product is required for a snapshot')
    api._validate_product(product)
    record, ctx, states = (product['seasonal']['land_cover'], product['context'], product['states'])
    area = float(ctx['spacing_m']) ** 2
    rows, cols = _i32_np.indices(ctx['height_m'].shape)
    x = (cols + ctx['origin_native_xz'][0]) * ctx['spacing_m']
    z = (rows + ctx['origin_native_xz'][1]) * ctx['spacing_m']
    fields = {'elevation_m': ctx['height_m'].ravel(), 'annual_temperature_c': record['family_temperature_c'].ravel(), 'water_state_mm': _i32_np.stack((states['soil_chemistry']['water_m3'] * 1000.0 / area, product['seasonal']['fast_mm'], product['seasonal']['slow_mm'])).reshape(3, -1), 'parent_solid_m3': record['material_solid_m3'].ravel(), 'parent_bulk_m3': (record['soil_thickness_bulk_m'] * area).ravel(), 'porosity': record['porosity'].ravel(), 'bed_hardness': states['mass']['bed_hardness'].ravel(), 'solubility': states['mass']['solubility'].ravel(), 'snow_state': product['seasonal']['snow_swe_mm'].ravel()}
    for key in ('soil_thickness_bulk_m', 'soil_water_capacity_mm', 'suitability', 'land_cover_index'):
        fields[key] = record[key].ravel()
    selected = _i32_np.flatnonzero(record['active_mask'].ravel())
    if not selected.size:
        raise ValueError('no active land accounts available for a G6 snapshot')
    fields = {key: value[:, selected] if value.ndim == 2 else value[selected] for key, value in fields.items()}
    return world.assemble(city_name=city_name, world_seed=int(ctx['world_seed']), spacing_m=float(ctx['spacing_m']), x_m=x.ravel()[selected], z_m=z.ravel()[selected], fields={key: _i32_np.array(value, copy=True) for key, value in fields.items()}, statuses={key: 'declared' if key in ('porosity', 'bed_hardness', 'solubility', 'soil_water_capacity_mm') else 'computed' for key in fields}, source_identities={'process_identity_sha256': api.product_identity(product), 'saved_world_identity': product['sources']['source_world_identity'], 'climate_driver_identity': product['seasonal']['climate_driver']['identity_sha256'], 'material_source_identity': product['seasonal']['material_source']['identity_sha256'], 'material_semantics': 'G2 same-world engineering rock-table lookup; regolith porosity is separately declared', 'support_masks': 'active land only: valid & ~ocean & ~protected; other accounts excluded', 'parent_solid_semantics': 'allocated G9 soil only; no unallocated parent potential added'}, model_parameters={'adapter': record['adapter'], 'G6': record['parameters'], 'G6_parameters_identity': record['parameters_identity_sha256']}, time_record={'physical_time_s': float(product['time_s']), 'step_index': int(product['step_index']), 'temperature_statistic': record['adapter']['temperature_source']})

def prepare_snapshot(process_path, *, expected_sha256, arrays_path, record_path):
    import terrain_pipeline.environment_product as api
    import terrain_pipeline.environment_product as world
    product = api.load_product(process_path, expected_sha256=expected_sha256)
    result = snapshot(product)
    world.save(result, arrays_path, record_path)
    return result

def advance_cover_carbon(elevation, ocean, lake, river, receiver, origin_native, monthly_temperature, monthly_water_mm, seed):
    """One final year of existing succession, with finite soil nutrient exchange."""
    from terrain_pipeline.climate_forcing import MONTH_DAYS as _x53_MONTH_DAYS
    from terrain_pipeline.environment_processes import initialize_succession as _x57_initialize_succession
    from terrain_pipeline.environment_processes import advance_succession as _x58_advance_succession
    shape = elevation.shape
    area = 8100.0
    context = dict(height_m=elevation, spacing_m=90.0, world_seed=seed, origin_native_xz=origin_native, receiver=receiver.reshape(shape), valid_mask=~ocean & ~lake, protected_mask=lake, ocean_mask=ocean, river_mask=river)
    state = _x57_initialize_succession(context, biomass_carbon_kg_m2=2.0)
    nutrient = _i33_np.full(shape, 0.05 * area) * (~ocean & ~lake)
    initial_nutrient = float(nutrient.sum() + state['plant_nutrient_kg'].sum())
    records = []
    litter = 0.0
    for month, days in enumerate(_x53_MONTH_DAYS):
        result = _x58_advance_succession(state, dict(temperature_c=monthly_temperature[month].reshape(shape), water_available_fraction=_i33_np.clip(monthly_water_mm[month].reshape(shape) / 150.0, 0.0, 1.0), plant_nutrient_uptake_kg=nutrient), context, float(days * 86400.0))
        nutrient = result['fluxes']['plant_nutrient_return_kg']
        state = result['state']
        litter += result['ledger']['soil_litter_carbon_kg']
        records.append(result['ledger'])
    final_nutrient = float(nutrient.sum() + state['plant_nutrient_kg'].sum())
    return (result['fluxes']['cover_fraction'], state['biomass_carbon_kg'] / area, dict(initial_biomass_carbon_kg_m2=2.0, initial_soil_nutrient_kg_m2=0.05, initial_nutrient_kg=initial_nutrient, final_nutrient_kg=final_nutrient, nutrient_residual_kg=initial_nutrient - final_nutrient, returned_soil_litter_carbon_kg=litter, monthly_ledgers=records, forcing='monthly end-of-month total soil+fast+slow water / 150mm; monthly temperature; zero fire/disturbance hazards', time='final year monthly transient, declared initial canopy; no equilibrium or species claim'))

def constant_month_soil(liquid_mm, states, temperature_c, days, *, failure_path=None, frame_metadata=None):
    """Stream real hourly bucket calls, grouping declared PET into 0.25 C bins.

    Once the entire state changes less than 1e-12 mm/h, the constant-forcing
    fixed point is repeated. The final release is repaired by the water ledger.
    """
    from terrain_pipeline.runoff import RunoffParameters as _i33_RunoffParameters
    from terrain_pipeline.environment_product import atomic_npz as _x172_atomic_npz
    from terrain_pipeline.climate_forcing import advance_soil as _x50_advance_soil
    hours = int(days * 24)
    rain = liquid_mm / hours
    runoff = _i33_np.zeros(rain.size)
    actual_et = _i33_np.zeros(rain.size)
    initial = states.copy()
    bands = _i33_np.floor(temperature_c * 4.0) / 4.0
    for band in _i33_np.unique(bands):
        ids = _i33_np.flatnonzero(bands == band)
        current = states[:, ids].copy()
        group_rain = rain[ids]
        parameters = _i33_RunoffParameters(potential_et_mm_h=float(temperature_index_pet_rate_mm_h(_i33_np.array([band]))[0]))
        for hour in range(hours):
            try:
                updated, release, et, _ = _x50_advance_soil(group_rain, current, dt_s=3600.0, parameters=parameters)
            except ValueError:
                if failure_path is not None:
                    _x172_atomic_npz(failure_path, rain_mm_h=group_rain, states=current, global_cell_ids=ids, parameters_json=_i33_np.array(_i33_json.dumps(_i33_asdict(parameters))), metadata_json=_i33_np.array(_i33_json.dumps(dict(frame_metadata or {}, hour=hour, temperature_band_c=float(band), rain_dtype=str(group_rain.dtype), state_dtype=str(current.dtype)))))
                raise
            runoff[ids] += release
            actual_et[ids] += et
            difference = _i33_np.max(_i33_np.abs(updated - current))
            current = updated
            if difference < 1e-12:
                remaining = hours - hour - 1
                runoff[ids] += release * remaining
                actual_et[ids] += et * remaining
                break
        states[:, ids] = current
    residual = liquid_mm - actual_et - runoff - (states - initial).sum(axis=0)
    runoff += residual
    if _i33_np.min(runoff) < -1e-08:
        raise RuntimeError('negative runoff after soil ledger closure')
    return (_i33_np.maximum(runoff, 0.0), actual_et)
