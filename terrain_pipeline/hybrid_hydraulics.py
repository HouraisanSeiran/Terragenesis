"""Consolidated hybrid_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import dataclass as _i18_dataclass
import math as _i18_math
import numpy as _i18_np
from scipy.optimize import brentq as _i18_brentq
from dataclasses import dataclass as _i16_dataclass
from collections import deque as _i16_deque
from bisect import bisect_right as _i16_bisect_right
import math as _i16_math
import time as _i16_time
from typing import Callable as _i16_Callable
import numpy as _i16_np
from scipy.integrate import Radau as _i16_Radau
from dataclasses import dataclass as _i17_dataclass
import math as _i17_math
import time as _i17_time
import numpy as _i17_np
from scipy.integrate import solve_ivp as _i17_solve_ivp
from scipy.optimize import brentq as _i17_brentq
from dataclasses import dataclass as _i19_dataclass
from collections import deque as _i19_deque
from bisect import bisect_right as _i19_bisect_right
import math as _i19_math
import time as _i19_time
from typing import Callable as _i19_Callable
import numpy as _i19_np
from scipy.integrate import Radau as _i19_Radau
from dataclasses import dataclass as _i20_dataclass
import math as _i20_math
import time as _i20_time
from typing import Callable as _i20_Callable
import numpy as _i20_np
from scipy.integrate import solve_ivp as _i20_solve_ivp
from dataclasses import dataclass as _i21_dataclass
from collections import deque as _i21_deque
import math as _i21_math
import time as _i21_time
from typing import Callable as _i21_Callable
import numpy as _i21_np
from scipy.integrate import Radau as _i21_Radau
from dataclasses import dataclass as _i22_dataclass
from collections import deque as _i22_deque
import math as _i22_math
import time as _i22_time
from typing import Callable as _i22_Callable
import numpy as _i22_np
from scipy.integrate import Radau as _i22_Radau
from dataclasses import dataclass as _i23_dataclass
from collections import deque as _i23_deque
from bisect import bisect_right as _i23_bisect_right
import math as _i23_math
import time as _i23_time
from typing import Callable as _i23_Callable
import numpy as _i23_np
from scipy.integrate import Radau as _i23_Radau
from dataclasses import dataclass as _i24_dataclass
from collections import deque as _i24_deque
from bisect import bisect_right as _i24_bisect_right
import math as _i24_math
import time as _i24_time
from typing import Callable as _i24_Callable
import numpy as _i24_np
from scipy.integrate import BDF as _i24_BDF
from bisect import bisect_right as _i26_bisect_right
from dataclasses import dataclass as _i26_dataclass
from dataclasses import replace as _i26_replace
import math as _i26_math
from scipy.optimize import brentq as _i26_brentq
from dataclasses import asdict as _i25_asdict
from dataclasses import replace as _i25_replace
import math as _i25_math
CATEGORY = 'C'
COMMON_OLD_FACE_BUDGET_REMAINING = 2949448968
COMMON_MAX_CELLS = 64
COMMON_QUAD_POINTS, COMMON_QUAD_WEIGHTS = _i18_np.polynomial.legendre.leggauss(12)

def _nonpositive_water_trial(message):
    error = ValueError(message)
    error.nonpositive_water_trial = True
    return error

def _execution_failure(message, progress):
    error = ValueError(message)
    error.progress = progress
    error.diagnostic_stop = False
    return error

def _diagnostic_stop(message, progress):
    error = ValueError(message)
    error.progress = progress
    error.diagnostic_stop = True
    return error

def common_positive(value, name):
    value = float(value)
    if not _i18_math.isfinite(value) or value <= 0:
        raise ValueError(name + ' must be finite and positive')
    return value

def common_submerged_intervals(coefficients, stage):
    constant, linear, quadratic = coefficients
    polynomial = [quadratic, linear, constant - stage]
    roots = _i18_np.roots(_i18_np.trim_zeros(polynomial, 'f')) if any(polynomial) else []
    knots = [0.0, 1.0] + [float(root.real) for root in roots if abs(root.imag) < 1e-12 and 0 < root.real < 1]
    knots.sort()
    return [(lower, upper) for lower, upper in zip(knots[:-1], knots[1:]) if constant + linear * ((lower + upper) / 2) + quadratic * ((lower + upper) / 2) ** 2 < stage]

@_i18_dataclass(frozen=True)
class common_Section:
    kind: str
    pieces: tuple = ()
    polygon: tuple = ()
    pressure_slot_width_m: float = 0.0

    @classmethod
    def from_record(cls, record):
        if record['kind'] == 'native_bed':
            if record.get('sidewall_extension') != 'explicit_engineering_vertical':
                raise ValueError('surface overflow walls must be explicitly engineered')
            section = cls('native_bed', tuple(((float(piece['width_m']), tuple((float(value) for value in piece['bed_coefficients_m_t012']))) for piece in record['pieces'])))
        elif record['kind'] == 'open_polyline':
            if record.get('sidewall_extension') != 'explicit_engineering_vertical':
                raise ValueError('surface overflow walls must be explicitly engineered')
            points = record['polyline_transverse_elevation_m']
            if len(points) < 2 or len(points) > 256:
                raise ValueError('bounded actual open cross section required')
            pieces = []
            for start, end in zip(points[:-1], points[1:]):
                pieces.append((common_positive(end[0] - start[0], 'ordered section width'), (float(start[1]), float(end[1] - start[1]), 0.0)))
            section = cls('open_polyline', tuple(pieces))
        elif record['kind'] == 'closed_polygon':
            section = cls('closed_polygon', polygon=tuple((tuple((float(value) for value in point)) for point in record['polygon_transverse_elevation_m'])), pressure_slot_width_m=float(record['pressure_slot_width_m']))
        else:
            raise ValueError('unsupported actual section representation')
        section.validate()
        return section

    def validate(self):
        if self.kind in ('native_bed', 'open_polyline'):
            if not self.pieces:
                raise ValueError('empty native section')
            previous = None
            for width, coefficients in self.pieces:
                common_positive(width, 'native width')
                if len(coefficients) != 3 or not all((_i18_math.isfinite(value) for value in coefficients)):
                    raise ValueError('invalid native polynomial')
                if previous is not None and abs(coefficients[0] - previous) > 1e-08:
                    raise ValueError('native section discontinuity')
                previous = sum(coefficients)
        elif self.kind == 'closed_polygon':
            polygon = _i18_np.asarray(self.polygon)
            if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3 or (len(polygon) > 256) or (not _i18_np.isfinite(polygon).all()):
                raise ValueError('invalid bounded polygon section')
            common_positive(self.pressure_slot_width_m, 'engineered pressure compliance width')
            from shapely.geometry import Polygon
            shape = Polygon(polygon - polygon[0])
            if not shape.is_valid or shape.area <= 0 or len(set(self.polygon)) != len(self.polygon):
                raise ValueError('self-intersecting or degenerate actual section')
        else:
            raise ValueError('unsupported section kind')

    @property
    def floor_m(self):
        if self.kind == 'closed_polygon':
            return min((point[1] for point in self.polygon))
        values = []
        for width, (constant, linear, quadratic) in self.pieces:
            values.extend((constant, constant + linear + quadratic))
            if quadratic and 0 < -linear / (2 * quadratic) < 1:
                fraction = -linear / (2 * quadratic)
                values.append(constant + linear * fraction + quadratic * fraction ** 2)
        return min(values)

    @property
    def crown_m(self):
        return max((point[1] for point in self.polygon)) if self.kind == 'closed_polygon' else None

    def area_perimeter(self, head_m):
        if not _i18_math.isfinite(head_m):
            raise ValueError('nonfinite section head')
        if head_m <= self.floor_m:
            return (0.0, 0.0)
        if self.kind in ('native_bed', 'open_polyline'):
            area, perimeter = (0.0, 0.0)
            for width, coefficients in self.pieces:
                constant, linear, quadratic = coefficients
                for lower, upper in common_submerged_intervals(coefficients, head_m):
                    area += width * ((head_m - constant) * (upper - lower) - linear * (upper ** 2 - lower ** 2) / 2 - quadratic * (upper ** 3 - lower ** 3) / 3)
                    fractions = lower + (COMMON_QUAD_POINTS + 1) * (upper - lower) / 2
                    perimeter += float(_i18_np.dot(COMMON_QUAD_WEIGHTS, _i18_np.sqrt(width ** 2 + (linear + 2 * quadratic * fractions) ** 2))) * (upper - lower) / 2
            perimeter += max(0.0, head_m - self.pieces[0][1][0]) + max(0.0, head_m - sum(self.pieces[-1][1]))
            return (area, perimeter)
        crown = self.crown_m
        level = min(head_m, crown)
        clipped, perimeter = ([], 0.0)
        for start, end in zip(self.polygon, self.polygon[1:] + self.polygon[:1]):
            start_inside, end_inside = (start[1] <= level, end[1] <= level)
            fraction = None
            if start_inside != end_inside:
                fraction = (level - start[1]) / (end[1] - start[1])
                intersection = (start[0] + fraction * (end[0] - start[0]), level)
                clipped.append(intersection)
            if end_inside:
                clipped.append(end)
            length = _i18_math.dist(start, end)
            if start_inside and end_inside:
                perimeter += length
            elif fraction is not None:
                perimeter += length * (fraction if start_inside else 1 - fraction)
        area = 0.0
        if len(clipped) >= 3:
            local = [(point[0] - clipped[0][0], point[1] - clipped[0][1]) for point in clipped]
            area = abs(sum((start[0] * end[1] - end[0] * start[1] for start, end in zip(local, local[1:] + local[:1])))) / 2
        return (area + self.pressure_slot_width_m * max(0.0, head_m - crown), perimeter)

    def head_for_area(self, area_m2):
        common_positive(area_m2, 'stored section area')
        lower = self.floor_m
        upper = max(lower + 1, self.crown_m or lower + 1)
        while self.area_perimeter(upper)[0] < area_m2:
            upper = lower + 2 * (upper - lower)
            if upper - lower > 1000000.0:
                raise ValueError('head exceeds bounded model range')
        return _i18_brentq(lambda head: self.area_perimeter(head)[0] - area_m2, lower, upper, xtol=1e-10)

@_i18_dataclass(frozen=True)
class common_Cell:
    cell_id: str
    kind: str
    length_m: float
    roughness_manning: float
    section: common_Section

@_i18_dataclass(frozen=True)
class common_Link:
    link_id: str
    from_cell_id: str
    to_cell_id: str
    length_m: float
    kind: str

@_i18_dataclass(frozen=True)
class common_Model:
    cells: tuple[common_Cell, ...]
    links: tuple[common_Link, ...]
    head_regularization_m: float = 0.0001
    donor_regularization_m3: float = 1e-06

    @classmethod
    def from_geometry(cls, geometry):
        cells = tuple((common_Cell(cell['cell_id'], cell['kind'], common_positive(cell['length_m'], 'cell length'), common_positive(cell['roughness_manning'], 'Manning roughness'), common_Section.from_record(cell['section'])) for cell in geometry['hydraulic_cells']))
        links = tuple((common_Link(link['link_id'], link['from_cell_id'], link['to_cell_id'], common_positive(link['length_m'], 'link length'), link['kind']) for link in geometry['hydraulic_links']))
        model = cls(cells, links)
        model.validate()
        return model

    def validate(self):
        count = len(self.cells)
        if not 3 <= count <= COMMON_MAX_CELLS or len(self.links) != count - 1:
            raise ValueError('bounded sink/conduit/spring chain required')
        if len(set((cell.cell_id for cell in self.cells))) != count or len(set((link.link_id for link in self.links))) != len(self.links):
            raise ValueError('duplicate hydraulic ownership')
        kinds = [cell.kind for cell in self.cells]
        if kinds[0] != 'surface' or kinds[-1] != 'surface' or 'underground' not in kinds:
            raise ValueError('invalid hydraulic cell types')
        first_underground, last_underground = (kinds.index('underground'), count - 1 - kinds[::-1].index('underground'))
        if any((kind != 'underground' for kind in kinds[first_underground:last_underground + 1])) or any((kind != 'surface' for kind in kinds[:first_underground] + kinds[last_underground + 1:])):
            raise ValueError('hydraulic route must have consecutive surface-in/conduit/surface-out cells')
        for cell in self.cells:
            common_positive(cell.length_m, 'cell length')
            common_positive(cell.roughness_manning, 'roughness')
            cell.section.validate()
            if cell.section.kind != ('open_polyline' if cell.kind == 'surface' else 'closed_polygon'):
                raise ValueError('cell/section physical type mismatch')
        for ordinal, link in enumerate(self.links):
            if (link.from_cell_id, link.to_cell_id) != (self.cells[ordinal].cell_id, self.cells[ordinal + 1].cell_id):
                raise ValueError('links must be actual ordered cell connections')
            pair = kinds[ordinal:ordinal + 2]
            expected = {('surface', 'surface'): 'surface_half_arm', ('surface', 'underground'): 'sink_exchange', ('underground', 'surface'): 'spring_exchange', ('underground', 'underground'): 'conduit'}[tuple(pair)]
            if link.kind != expected:
                raise ValueError('missing explicit paired surface/conduit exchange')
            common_positive(link.length_m, 'link length')
        common_positive(self.head_regularization_m, 'head regularization')
        common_positive(self.donor_regularization_m3, 'donor regularization')

@_i18_dataclass(frozen=True)
class common_Experiment:
    scenario: str
    duration_s: float
    pulse_duration_s: float
    pulse_q_m3_s: float
    tailwater_head_m: float
    initial_heads_m: tuple[float, ...]
    saved_times_s: tuple[float, ...]
    max_step_s: float = 1.0
    relative_tolerance: float = 1e-07
    absolute_tolerance: float = 1e-09
    max_rhs_evaluations: int = 200000
    max_link_evaluations: int = 12000000
    max_wall_seconds: float = 600.0
    source_arrival_threshold_m3: float = 1e-06

    def validate(self, model):
        if self.scenario not in ('pulse', 'reverse_tailwater'):
            raise ValueError('unknown engineering experiment')
        for name in ('duration_s', 'max_step_s', 'relative_tolerance', 'absolute_tolerance', 'max_wall_seconds', 'source_arrival_threshold_m3'):
            common_positive(getattr(self, name), name)
        if not 1e-12 <= self.relative_tolerance <= 0.0001 or not 1e-14 <= self.absolute_tolerance <= 1e-06 or self.max_step_s > self.duration_s or (self.max_wall_seconds > 600):
            raise ValueError('solver tolerances/step/wall guard exceed authorized range')
        if not _i18_math.isfinite(self.tailwater_head_m) or not _i18_math.isfinite(self.pulse_q_m3_s) or self.pulse_q_m3_s < 0:
            raise ValueError('invalid prescribed engineering forcing')
        if self.tailwater_head_m <= model.cells[-1].section.floor_m:
            raise ValueError('wet-boundary storage model requires tailwater strictly above outlet floor; dry free outfall is unsupported')
        if self.scenario == 'pulse' and (not (0 < self.pulse_duration_s < self.duration_s and self.pulse_q_m3_s > 0)):
            raise ValueError('pulse requires a finite positive single source')
        if self.scenario == 'reverse_tailwater' and (self.pulse_q_m3_s != 0 or self.pulse_duration_s != 0):
            raise ValueError('reverse experiment cannot inject duplicate ordinary source Q')
        if len(self.initial_heads_m) != len(model.cells) or any((not _i18_math.isfinite(head) or head <= cell.section.floor_m for head, cell in zip(self.initial_heads_m, model.cells))):
            raise ValueError('explicit positive initial water required; no depth clamp')
        times = _i18_np.asarray(self.saved_times_s)
        if len(times) < 2 or len(times) > 4096 or (not _i18_np.isfinite(times).all()) or (times[0] != 0) or (times[-1] != self.duration_s) or _i18_np.any(_i18_np.diff(times) <= 0):
            raise ValueError('invalid bounded physical observation times')
        if not 1 <= self.max_rhs_evaluations <= 200000 or not 1 <= self.max_link_evaluations <= 12000000:
            raise ValueError('invalid independent 1D work bounds')

def common_conveyance(cell, head):
    area, perimeter = cell.section.area_perimeter(head)
    return area * (area / perimeter) ** (2 / 3) / cell.roughness_manning if area > 0 and perimeter > 0 else 0.0

def common_signed_flow(conductance, difference, length, regularization):
    return conductance * difference / ((difference ** 2 + regularization ** 2) ** 0.25 * _i18_math.sqrt(length))

def common_compare_refinement(coarse, fine, volume_absolute_tolerance_m3=0.0001, head_absolute_tolerance_m=0.001, volume_relative_tolerance=0.01):
    if coarse['times_s'] != fine['times_s'] or coarse['cell_ids'] != fine['cell_ids'] or coarse['scenario'] != fine['scenario']:
        raise ValueError('refinement requires the same physical experiment and observation times')
    common_positive(volume_absolute_tolerance_m3, 'refinement volume tolerance')
    common_positive(head_absolute_tolerance_m, 'refinement head tolerance')
    if head_absolute_tolerance_m > 0.001 or not 0 < volume_relative_tolerance <= 0.01:
        raise ValueError('refinement cannot relax the 1mm/1percent accuracy contract')
    volume_error = float(_i18_np.max(abs(_i18_np.asarray(coarse['water_volume_m3']) - _i18_np.asarray(fine['water_volume_m3']))))
    volume_relative_error = float(_i18_np.max(abs(_i18_np.asarray(coarse['water_volume_m3']) - _i18_np.asarray(fine['water_volume_m3'])) / _i18_np.asarray(fine['water_volume_m3'])))
    head_error = float(_i18_np.max(abs(_i18_np.asarray(coarse['hydraulic_head_m']) - _i18_np.asarray(fine['hydraulic_head_m']))))
    tracer_error = max((float(_i18_np.max(abs(_i18_np.asarray(coarse[key]) - _i18_np.asarray(fine[key])))) for key in ('source_tracer_mass_m3', 'tailwater_tracer_mass_m3', 'boundary_ledger_m3')))
    return {'status': 'passed' if volume_error <= volume_absolute_tolerance_m3 and volume_relative_error <= volume_relative_tolerance and (tracer_error <= volume_absolute_tolerance_m3) and (head_error <= head_absolute_tolerance_m) else 'refused', 'scope': 'Radau_adaptive_tolerance_and_max_step_refinement_not_explicit_0.005s_certification', 'max_volume_difference_m3': volume_error, 'max_head_difference_m': head_error, 'max_tracer_ledger_difference_m3': tracer_error, 'max_relative_volume_difference': volume_relative_error, 'volume_relative_tolerance': volume_relative_tolerance, 'volume_absolute_tolerance_m3': volume_absolute_tolerance_m3, 'head_absolute_tolerance_m': head_absolute_tolerance_m}

@_i16_dataclass(frozen=True)
class StorageSystem:
    count: int
    initial_state: _i16_np.ndarray
    initial_volumes: _i16_np.ndarray
    work: dict
    started: float
    physical: _i16_Callable
    rhs_for: _i16_Callable
    jacobian_for: _i16_Callable
    peak_rss: _i16_Callable

def jacobian_policy(model, width_m):
    return {'method': 'native_piecewise_section_and_signed_Manning_full_chain_analytic', 'inventory_columns': 'all_three_origins_share_dV_dM_equal_one_plus_exact_donor_composition', 'ledger_feedback_columns': 'exact_zero', 'jacobian_rhs_evaluations_per_call': 0, 'jacobian_link_evaluations_per_call': 2 * (len(model.links) + 1), 'jacobian_flow_evaluations_per_call': len(model.links) + 1, 'jacobian_link_derivative_evaluations_per_call': len(model.links) + 1, 'section_breakpoint_branch': 'right_height_band', 'min_capacity_tie_branch': 'left_or_cell_at_boundary', 'zero_signed_flow_donor_branch': 'left_or_cell_outlet', 'fallback_scope': 'native_quadratic_section_without_cached_bands_local_geometry_difference_only', 'fallback_max_head_step_m': 1e-06, 'fallback_head_step_rule': 'min(1e-6,width_m*0.01_if_positive)', 'fallback_head_step_float_margin': '16_ulp_of_base_head', 'nonsmooth_scope': 'active_branch_derivative_at_storage_slot_donor_min_and_horizontal_perimeter_jumps_not_whole_RHS_C1', 'scipy_adaptive_difference_factor_used': False}

def section_slopes(cell, head_m, width_m, roof_length, work=None):
    section = cell.section
    details = friction_state(cell, head_m, width_m, roof_length)
    if section.bands:
        ordinal = _i16_bisect_right(section.levels_m, head_m) - 1
        band = section.bands[ordinal]
        area_slope = band.width_at_lower_m + band.width_slope * (head_m - band.lower_m)
        perimeter_slope = band.perimeter_slope
        if width_m > 0 and section.kind == 'closed_polygon' and (section.crown_m <= head_m < section.crown_m + width_m):
            fraction = (head_m - section.crown_m) / width_m
            perimeter_slope += roof_length * 6 * fraction * (1 - fraction) / width_m
        if work is not None:
            work['jacobian_native_section_derivatives'] += 1
    else:
        step = min(1e-06, width_m * 0.01) if width_m > 0 else 1e-06
        raised = friction_state(cell, head_m + step, width_m, roof_length)
        actual_step = head_m + step - head_m
        if actual_step <= 0:
            raise ValueError('fallback section derivative head step unrepresentable')
        if actual_step > step + 16 * _i16_math.ulp(float(head_m)):
            raise ValueError('fallback section derivative exceeds declared head cap')
        area_slope = (raised['area_m2'] - details['area_m2']) / actual_step
        perimeter_slope = (raised['effective_friction_perimeter_m'] - details['effective_friction_perimeter_m']) / actual_step
        if work is not None:
            work['jacobian_section_fallback_evaluations'] += 2
            work['jacobian_max_observed_head_step_m'] = max(work.get('jacobian_max_observed_head_step_m', 0.0), actual_step)
    if not _i16_math.isfinite(area_slope) or area_slope <= 0 or (not _i16_math.isfinite(perimeter_slope)):
        raise ValueError('native section derivative invalid; no derivative clamp')
    head_per_volume = 1 / (cell.length_m * area_slope)
    capacity = details['effective_manning_conveyance']
    capacity_per_head = capacity * (5 / 3 * area_slope / details['area_m2'] - 2 / 3 * perimeter_slope / details['effective_friction_perimeter_m'])
    return (capacity, head_per_volume, capacity_per_head * head_per_volume)

def signed_flow_slopes(capacity, difference_m, length_m, regularization_m):
    squared = difference_m * difference_m + regularization_m * regularization_m
    root_length = _i16_math.sqrt(length_m)
    signed_factor = difference_m / (squared ** 0.25 * root_length)
    head_factor_derivative = (0.5 * difference_m * difference_m + regularization_m * regularization_m) / (squared ** 1.25 * root_length)
    return (signed_factor, capacity * head_factor_derivative)

def build_system(model: common_Model, experiment: common_Experiment, crown_transition_width_m=0.0, rhs_observer=None):
    validate_transition(crown_transition_width_m)
    model.validate()
    experiment.validate(model)
    count, link_count = (len(model.cells), len(model.links))
    initial_volumes = _i16_np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if _i16_np.any(initial_volumes <= 0):
        raise ValueError('initial storage must be strictly positive')
    ledger_start = 3 * count
    state = _i16_np.zeros(ledger_start + 7 + 4 * link_count)
    state[:count] = initial_volumes
    work = {'rhs_evaluations': 0, 'link_evaluations': 0, 'old_hll_face_work': 0, 'jacobian_evaluations': 0, 'jacobian_rhs_evaluations': 0, 'jacobian_link_evaluations': 0, 'jacobian_native_section_derivatives': 0, 'jacobian_flow_evaluations': 0, 'jacobian_link_derivative_evaluations': 0, 'jacobian_section_fallback_evaluations': 0, 'positivity_rejected_steps': 0, 'nonpositive_total_trial_retries': 0, 'solver_reinitializations': 0, 'constructor_nonpositive_retries': 0, 'accepted_endpoint_inventory_checks': 0, 'observation_segment_initializations': 0, 'radau_constructor_attempts': 0}
    started = _i16_time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    roof_lengths = [roof_contact_length(cell.section) for cell in model.cells]

    def capacity_for(ordinal, head):
        return friction_state(model.cells[ordinal], head, crown_transition_width_m, roof_lengths[ordinal])['effective_manning_conveyance']

    def physical(inventories):
        if _i16_np.shape(inventories) != (3 * count,) or not _i16_np.isfinite(inventories).all():
            raise _nonpositive_water_trial('physical inventory requires finite three-origin state')
        volumes = inventories.reshape(3, count).sum(axis=0)
        if _i16_np.any(volumes <= 0):
            raise _nonpositive_water_trial('trial total water is nonpositive; no floor clamp')
        heads = _i16_np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any((head <= cell.section.floor_m for cell, head in zip(model.cells, heads))):
            raise _nonpositive_water_trial('trial positive inventory below representable depth; no floor clamp')
        capacities = _i16_np.array([capacity_for(ordinal, head) for ordinal, head in enumerate(heads)])
        return (volumes, heads, capacities)

    def guard():
        nonlocal peak_rss
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations or work['link_evaluations'] > experiment.max_link_evaluations or _i16_time.monotonic() - started > experiment.max_wall_seconds:
            raise ValueError('independent 1D work/time bound exceeded')
        peak_rss = max(peak_rss, process.memory_info().rss)
        if peak_rss > 1024 ** 3:
            raise ValueError('1GiB hydraulic RSS limit exceeded')

    def flows(current):
        volumes, heads, capacities = physical(current[:3 * count])
        amounts = []
        for ordinal, link in enumerate(model.links):
            flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
            donor = ordinal if flow >= 0 else ordinal + 1
            flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
            amounts.append((float(flow), donor))
        boundary_capacity = min(capacities[-1], capacity_for(count - 1, experiment.tailwater_head_m))
        outlet = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
        if outlet >= 0:
            outlet *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        return (volumes, heads, amounts, float(outlet))

    def concentration_matrix(amounts, outlet):
        matrix = _i16_np.zeros((len(state), 3 * count))
        for ordinal, (flow, donor) in enumerate(amounts):
            for origin in range(3):
                column = origin * count + donor
                matrix[origin * count + ordinal, column] -= flow
                matrix[origin * count + ordinal + 1, column] += flow
                row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                matrix[row, column] += flow
        if outlet >= 0:
            for origin in range(3):
                column = origin * count + count - 1
                matrix[column, column] -= outlet
                row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                matrix[row, column] += outlet
        return matrix

    def rhs_for(source_q):

        def rhs(seconds, current, evaluation_context='Radau_rhs_trial'):
            if rhs_observer is not None:
                rhs_observer(seconds, current, evaluation_context)
            work['rhs_evaluations'] += 1
            work['link_evaluations'] += link_count + 1
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivative = _i16_np.zeros_like(current)
            rates = derivative[:3 * count].reshape(3, count)
            for ordinal, (flow, donor) in enumerate(amounts):
                transport = flow * concentrations[:, donor]
                rates[:, ordinal] -= transport
                rates[:, ordinal + 1] += transport
                derivative[ledger_start + 6 + link_count + ordinal] = transport[1]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = transport[2]
                derivative[ledger_start + 6 + 3 * link_count + ordinal] = transport[0]
            derivative[count] += source_q
            derivative[ledger_start] = source_q
            for ordinal, (flow, donor) in enumerate(amounts):
                derivative[ledger_start + 6 + ordinal] = flow
            if outlet >= 0:
                transport = outlet * concentrations[:, -1]
                rates[:, -1] -= transport
                derivative[ledger_start + 1] = outlet
                derivative[ledger_start + 3] = transport[1]
                derivative[ledger_start + 5] = transport[2]
                derivative[ledger_start + 6 + 4 * link_count] = transport[0]
            else:
                derivative[3 * count - 1] -= outlet
                derivative[ledger_start + 2] = -outlet
                derivative[ledger_start + 4] = -outlet
            return derivative
        return rhs

    def jacobian_for(source_q):

        def jacobian(seconds, current):
            if _i16_np.shape(current) != (len(state),) or not _i16_np.isfinite(current).all():
                raise ValueError('Jacobian requires finite complete three-origin state')
            if rhs_observer is not None:
                rhs_observer(seconds, current, 'Jacobian_analytic_state')
            work['jacobian_evaluations'] += 1
            work['jacobian_link_evaluations'] += 2 * (link_count + 1)
            work['jacobian_flow_evaluations'] += link_count + 1
            work['jacobian_link_derivative_evaluations'] += link_count + 1
            work['link_evaluations'] += 2 * (link_count + 1)
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivatives = [section_slopes(cell, heads[ordinal], crown_transition_width_m, roof_lengths[ordinal], work) for ordinal, cell in enumerate(model.cells)]
            matrix = _i16_np.zeros((len(state), len(state)))
            for ordinal, (flow, donor) in enumerate(amounts):
                link = model.links[ordinal]
                left_capacity, left_head_slope, left_capacity_slope = derivatives[ordinal]
                right_capacity, right_head_slope, right_capacity_slope = derivatives[ordinal + 1]
                limiting_left = left_capacity <= right_capacity
                minimum_capacity = min(left_capacity, right_capacity)
                factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor_factor = volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[donor] + model.donor_regularization_m3) ** 2
                left_flow_slope = donor_factor * (difference_derivative * left_head_slope + factor * left_capacity_slope * limiting_left)
                right_flow_slope = donor_factor * (-difference_derivative * right_head_slope + factor * right_capacity_slope * (not limiting_left))
                if donor == ordinal:
                    left_flow_slope += minimum_capacity * factor * donor_derivative
                else:
                    right_flow_slope += minimum_capacity * factor * donor_derivative
                for cell_ordinal, flow_slope in ((ordinal, left_flow_slope), (ordinal + 1, right_flow_slope)):
                    for origin_column in range(3):
                        column = origin_column * count + cell_ordinal
                        matrix[ledger_start + 6 + ordinal, column] += flow_slope
                        for origin in range(3):
                            transport_slope = concentrations[origin, donor] * flow_slope
                            if cell_ordinal == donor:
                                transport_slope += flow * ((origin == origin_column) - concentrations[origin, donor]) / volumes[donor]
                            matrix[origin * count + ordinal, column] -= transport_slope
                            matrix[origin * count + ordinal + 1, column] += transport_slope
                            row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                            matrix[row, column] += transport_slope
            capacity, head_slope, capacity_slope = derivatives[-1]
            tailwater_capacity = capacity_for(count - 1, experiment.tailwater_head_m)
            limiting_cell = capacity <= tailwater_capacity
            minimum_capacity = min(capacity, tailwater_capacity)
            factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            flow_slope = difference_derivative * head_slope + factor * capacity_slope * limiting_cell
            if outlet >= 0:
                donor_factor = volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[-1] + model.donor_regularization_m3) ** 2
                flow_slope = flow_slope * donor_factor + minimum_capacity * factor * donor_derivative
            for origin_column in range(3):
                column = origin_column * count + count - 1
                if outlet >= 0:
                    matrix[ledger_start + 1, column] += flow_slope
                    for origin in range(3):
                        transport_slope = concentrations[origin, -1] * flow_slope + outlet * ((origin == origin_column) - concentrations[origin, -1]) / volumes[-1]
                        matrix[origin * count + count - 1, column] -= transport_slope
                        row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                        matrix[row, column] += transport_slope
                else:
                    matrix[3 * count - 1, column] -= flow_slope
                    matrix[ledger_start + 2, column] -= flow_slope
                    matrix[ledger_start + 4, column] -= flow_slope
            if not _i16_np.isfinite(matrix).all():
                raise ValueError('analytic three-origin Jacobian nonfinite')
            return matrix
        return jacobian
    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for, lambda: max(peak_rss, process.memory_info().rss))

def inventory_policy():
    return {'origins': ['untraced', 'source', 'tailwater'], 'water_definition': 'sum_three_origin_inventories', 'state_units': 'm3', 'negative_inventory_action': 'reject_entire_Radau_step_and_halve_retry', 'dense_inventory_check': 'no_interpolated_inventory_output_saved_times_are_Radau_endpoints', 'output_clamp': False, 'posthoc_normalization': False, 'positivity_tolerance_m3': 0.0, 'initial_origin': 'untraced', 'pulse_origin': 'source', 'reverse_boundary_origin': 'tailwater', 'trial_scope': 'finite_signed_origin_Newton_trials_allowed_only_with_positive_total_water', 'retry_budget': 'one_original_event_work_wall_RSS_budget_never_reset'}

def positivity_violation(state, count, seconds):
    inventories = state[:3 * count].reshape(3, count)
    if not _i16_np.isfinite(state).all() or _i16_np.any(inventories < 0) or _i16_np.any(inventories.sum(axis=0) <= 0):
        ordinal = _i16_np.unravel_index(_i16_np.argmin(inventories), inventories.shape)
        value = float(inventories[ordinal])
        total = float(inventories[:, ordinal[1]].sum())
        return {'time_s': float(seconds), 'minimum_origin_inventory_m3': value if _i16_math.isfinite(value) else None, 'origin': ('untraced', 'source', 'tailwater')[ordinal[0]], 'cell_ordinal': int(ordinal[1]), 'total_water_m3': total if _i16_math.isfinite(total) else None, 'all_finite': bool(_i16_np.isfinite(state).all())}
    return None

def dense_positivity_violation(dense, count):
    for seconds in (dense.t_old, dense.t):
        violation = positivity_violation(dense(seconds), count, seconds)
        if violation:
            return violation
    coefficients = dense.Q[:3 * count]
    for first, second, third in coefficients:
        candidates = []
        if third == 0:
            if second != 0:
                candidates.append(-first / (2 * second))
        else:
            discriminant = 4 * second * second - 12 * third * first
            if discriminant >= 0:
                root = _i16_math.sqrt(discriminant)
                candidates.extend(((-2 * second + root) / (6 * third), (-2 * second - root) / (6 * third)))
        for fraction in candidates:
            if 0 < fraction < 1:
                seconds = dense.t_old + fraction * (dense.t - dense.t_old)
                violation = positivity_violation(dense(seconds), count, seconds)
                if violation:
                    return violation
    return None

def validate_transition(width_m):
    if not _i16_math.isfinite(width_m) or not 0 <= width_m <= 0.05:
        raise ValueError('declared roof friction transition must be between 0 and 0.05m')

def roof_contact_length(section):
    if section.kind != 'closed_polygon':
        return 0.0
    crown = section.crown_m
    return _i16_math.fsum((_i16_math.dist(start, end) for start, end in zip(section.polygon, section.polygon[1:] + section.polygon[:1]) if start[1] == crown and end[1] == crown))

def friction_state(cell, head_m, width_m, roof_length=None):
    area, actual_perimeter = cell.section.area_perimeter(head_m)
    effective_perimeter = actual_perimeter
    if roof_length is None:
        roof_length = roof_contact_length(cell.section)
    if width_m > 0 and cell.section.kind == 'closed_polygon' and (head_m >= cell.section.crown_m):
        fraction = (head_m - cell.section.crown_m) / width_m
        contact = 1.0 if fraction >= 1 else fraction * fraction * (3 - 2 * fraction)
        effective_perimeter = actual_perimeter - roof_length + roof_length * contact
    if area > 0 and (actual_perimeter <= 0 or effective_perimeter <= 0):
        raise ValueError('wet section has nonpositive actual/effective friction perimeter')
    actual_capacity = area * (area / actual_perimeter) ** (2 / 3) / cell.roughness_manning if area > 0 and actual_perimeter > 0 else 0.0
    capacity = area * (area / effective_perimeter) ** (2 / 3) / cell.roughness_manning if area > 0 and effective_perimeter > 0 else 0.0
    return {'area_m2': area, 'actual_wetted_perimeter_m': actual_perimeter, 'effective_friction_perimeter_m': effective_perimeter, 'actual_geometry_manning_conveyance': actual_capacity, 'effective_manning_conveyance': capacity, 'actual_horizontal_roof_length_m': roof_length}

def effective_conveyance(cell, head_m, width_m):
    return friction_state(cell, head_m, width_m)['effective_manning_conveyance']

def inventory_snapshot(model, system, state, width_m):
    volumes, heads, capacities = system.physical(state[:3 * system.count])
    cells = []
    for ordinal, (cell, volume, head) in enumerate(zip(model.cells, volumes, heads)):
        section = cell.section
        details = friction_state(cell, float(head), width_m)
        details.update(untraced_water_volume_m3=float(state[ordinal]), cell_id=cell.cell_id, kind=cell.kind, head_m=float(head), volume_m3=float(volume), source_tracer_mass_m3=float(state[system.count + ordinal]), tailwater_tracer_mass_m3=float(state[2 * system.count + ordinal]))
        if cell.kind == 'underground':
            details.update(crown_m=section.crown_m, head_minus_crown_m=float(head - section.crown_m), actual_closed_capacity_m3=cell.length_m * section.area_perimeter(section.crown_m)[0], engineered_pressure_slot_volume_m3=cell.length_m * section.pressure_slot_width_m * max(0.0, head - section.crown_m))
        else:
            bank = min(section.pieces[0][1][0], sum(section.pieces[-1][1]))
            details.update(low_bank_m=bank, head_minus_low_bank_m=float(head - bank), engineering_overbank_wall_storage_m3=cell.length_m * (section.area_perimeter(head)[0] - section.area_perimeter(bank)[0]) if head > bank else 0.0)
        cells.append(details)
    return {'cells': cells, 'total_water_m3': float(volumes.sum()), 'boundary_and_paired_ledgers_m3': state[3 * system.count:].tolist()}

def flux_snapshot(model, system, seconds, state, source_q, width_m, tailwater_head_m):
    volumes, heads, capacities = system.physical(state[:3 * system.count])
    concentrations = state[system.count:3 * system.count].reshape(2, system.count) / volumes
    links = []
    for ordinal, link in enumerate(model.links):
        flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
        donor = ordinal if flow >= 0 else ordinal + 1
        flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
        links.append({'link_id': link.link_id, 'water_q_m3_s': float(flow), 'source_tracer_q_m3_s': float(flow * concentrations[0, donor]), 'tailwater_tracer_q_m3_s': float(flow * concentrations[1, donor]), 'donor_cell_id': model.cells[donor].cell_id})
    tailwater_capacity = effective_conveyance(model.cells[-1], tailwater_head_m, width_m)
    flow = common_signed_flow(min(capacities[-1], tailwater_capacity), heads[-1] - tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
    if flow >= 0:
        flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        source_flow, tailwater_flow = flow * concentrations[:, -1]
    else:
        source_flow, tailwater_flow = (0.0, flow)
    system.work['link_evaluations'] += len(model.links) + 1
    system.work['diagnostic_flux_link_evaluations'] = system.work.get('diagnostic_flux_link_evaluations', 0) + len(model.links) + 1
    return {'time_s': float(seconds), 'source_q_m3_s': source_q, 'links': links, 'outlet_signed_water_q_m3_s': float(flow), 'outlet_signed_source_tracer_q_m3_s': float(source_flow), 'outlet_signed_tailwater_tracer_q_m3_s': float(tailwater_flow)}

def make_run_experiment(*, schema, numerical_version, model_version, build_system=build_system, jacobian_policy=jacobian_policy, inventory_policy=inventory_policy, positivity_violation=positivity_violation, inventory_snapshot=inventory_snapshot, flux_snapshot=flux_snapshot, NonpositiveWaterTrial=ValueError, HydraulicExecutionFailure=_execution_failure, HydraulicDiagnosticStop=_diagnostic_stop):
    """Return the shared run_experiment bound to one version identity and its policies."""
    SCHEMA, NUMERICAL_VERSION, MODEL_VERSION = (schema, numerical_version, model_version)

    def run_experiment(model: common_Model, experiment: common_Experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
        if diagnostic_stop_s is not None and (not _i16_math.isfinite(diagnostic_stop_s) or not 0 < diagnostic_stop_s <= experiment.duration_s):
            raise ValueError('diagnostic stop must be positive and within the unchanged physical event')
        last_evaluation = {'context': 'not_started', 'time_s': None}
        last_trial_state = None

        def observe_rhs(seconds, current, context):
            nonlocal last_trial_state
            last_evaluation.update(context=context, time_s=float(seconds))
            last_trial_state = current.copy()
        system = build_system(model, experiment, crown_transition_width_m, rhs_observer=observe_rhs)
        count, link_count = (system.count, len(model.links))
        ledger_start = 3 * count
        state = system.initial_state.copy()
        initial_volumes, work, started = (system.initial_volumes, system.work, system.started)
        physical = system.physical
        accepted_state, accepted_time = (state.copy(), 0.0)
        accepted_steps, min_step, max_step = (0, None, None)
        last_positivity_rejection = None
        saved_mass_extrema = None
        recent_steps = _i16_deque(maxlen=16)
        observations = [(0.0, state.copy())]
        integration_segments = []
        rejected_solver_statistics = {'nfev': 0, 'njev': 0, 'nlu': 0}
        saved_times = _i16_np.asarray(experiment.saved_times_s)
        saved_ordinal = 1

        def progress():
            observed_origins = _i16_np.array([current[:3 * count].reshape(3, count) for seconds, current in observations])
            observed_index = _i16_np.unravel_index(_i16_np.argmin(observed_origins), observed_origins.shape)
            observed_extrema = {'minimum_origin_inventory_m3': float(observed_origins[observed_index]), 'time_s': float(observations[observed_index[0]][0]), 'origin': ('untraced', 'source', 'tailwater')[observed_index[1]], 'cell_id': model.cells[observed_index[2]].cell_id, 'per_origin_minimum_m3': observed_origins.min(axis=(0, 2)).tolist()}
            elapsed = _i16_time.monotonic() - started
            guard = None
            if work['rhs_evaluations'] > experiment.max_rhs_evaluations:
                guard = 'max_rhs_evaluations'
            elif work['link_evaluations'] > experiment.max_link_evaluations:
                guard = 'max_link_evaluations'
            elif elapsed > experiment.max_wall_seconds:
                guard = 'max_wall_seconds'
            elif system.peak_rss() > 1024 ** 3:
                guard = 'max_rss_bytes'
            trial = None
            if last_trial_state is not None:
                trial = {'state_all_finite': bool(_i16_np.isfinite(last_trial_state).all()), 'state': [float(value) if _i16_math.isfinite(value) else None for value in last_trial_state], 'is_accepted_state': False, 'state_layout': 'untracedMass/sourceMass/tailwaterMass/oldSixBoundary/threePaired/untracedPaired/untracedOutlet'}
            try:
                accepted_inventory = inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
            except Exception as snapshot_error:
                accepted_inventory = {'snapshot_error': str(snapshot_error), 'state': [float(value) if _i16_math.isfinite(value) else None for value in accepted_state]}
            return {'last_accepted_physical_time_s': accepted_time, 'configured_physical_duration_s': experiment.duration_s, 'diagnostic_stop_s': diagnostic_stop_s, 'physical_event_complete': accepted_time == experiment.duration_s, 'work': dict(work), 'last_positivity_rejection': last_positivity_rejection, 'saved_mass_extrema': saved_mass_extrema if saved_mass_extrema is not None else observed_extrema, 'elapsed_wall_seconds': elapsed, 'triggered_guard': guard, 'discarded_solver_statistics': dict(rejected_solver_statistics), 'max_rhs_evaluations': experiment.max_rhs_evaluations, 'max_link_evaluations': experiment.max_link_evaluations, 'max_wall_seconds': experiment.max_wall_seconds, 'accepted_steps': accepted_steps, 'min_accepted_step_s': min_step, 'max_accepted_step_s': max_step, 'recent_accepted_steps': list(recent_steps), 'last_evaluation': dict(last_evaluation), 'last_trial': trial, 'last_accepted_inventory': accepted_inventory, 'actual_peak_rss_bytes': system.peak_rss(), 'model_version': MODEL_VERSION, 'crown_friction_transition_width_m': crown_transition_width_m, 'inventory_scope': 'actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume'}
        breaks = [0.0, experiment.duration_s, *experiment.saved_times_s]
        if experiment.scenario == 'pulse':
            breaks.append(experiment.pulse_duration_s)
        breaks = sorted(set(breaks))
        try:
            for lower, full_upper in zip(breaks[:-1], breaks[1:]):
                upper = min(full_upper, diagnostic_stop_s) if diagnostic_stop_s is not None else full_upper
                if upper <= lower:
                    break
                source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
                raw_rhs, raw_jacobian = (system.rhs_for(source_q), system.jacobian_for(source_q))

                def tracked_rhs(seconds, current):
                    return raw_rhs(seconds, current)

                def tracked_jacobian(seconds, current):
                    return raw_jacobian(seconds, current)

                def construct_solver(seconds, current, maximum_step, first_step=None):
                    nonlocal last_positivity_rejection
                    while True:
                        try:
                            work['radau_constructor_attempts'] += 1
                            return _i16_Radau(tracked_rhs, seconds, current, upper, max_step=maximum_step, first_step=first_step, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=tracked_jacobian)
                        except NonpositiveWaterTrial as error:
                            if NonpositiveWaterTrial is ValueError and not getattr(error, 'nonpositive_water_trial', False):
                                raise
                            work['constructor_nonpositive_retries'] += 1
                            work['nonpositive_total_trial_retries'] += 1
                            last_positivity_rejection = {'time_s': seconds, 'trial_error': str(error), 'context': 'Radau_constructor', 'accepted_state_unchanged': True}
                            bound = min(maximum_step, upper - seconds)
                            if first_step is not None:
                                bound = min(bound, first_step)
                            first_step = bound / 2
                            maximum_step = min(maximum_step, first_step)
                            if first_step <= 16 * _i16_math.ulp(seconds) or first_step <= 0:
                                raise ValueError('constructor positivity retry step unrepresentable; no clamp')
                            work['solver_reinitializations'] += 1
                work['observation_segment_initializations'] += 1
                solver = construct_solver(lower, state, experiment.max_step_s)
                segment_steps = []
                while solver.status == 'running':
                    previous_state = accepted_state.copy()
                    attempted_step = min(solver.h_abs, upper - accepted_time)
                    trial_error = None
                    try:
                        message = solver.step()
                    except NonpositiveWaterTrial as error:
                        if NonpositiveWaterTrial is ValueError and not getattr(error, 'nonpositive_water_trial', False):
                            raise
                        trial_error = str(error)
                    if trial_error is None and solver.status != 'failed':
                        work['accepted_endpoint_inventory_checks'] += 1
                        violation = positivity_violation(solver.y, count, solver.t)
                        actual_candidate_step = solver.t - accepted_time
                    else:
                        violation = {'time_s': accepted_time, 'trial_error': trial_error} if trial_error else None
                        actual_candidate_step = attempted_step
                    if violation is not None:
                        last_positivity_rejection = violation
                        if 'cell_ordinal' in violation:
                            last_positivity_rejection['cell_id'] = model.cells[violation['cell_ordinal']].cell_id
                        work['positivity_rejected_steps'] += 1
                        if trial_error:
                            work['nonpositive_total_trial_retries'] += 1
                        retry_step = min(attempted_step, actual_candidate_step) / 2
                        if retry_step <= 16 * _i16_math.ulp(accepted_time) or retry_step <= 0:
                            raise ValueError('strict positivity retry step unrepresentable; no clamp')
                        work['solver_reinitializations'] += 1
                        for name in rejected_solver_statistics:
                            rejected_solver_statistics[name] += getattr(solver, name)
                        solver = construct_solver(accepted_time, previous_state, min(experiment.max_step_s, retry_step), first_step=retry_step)
                        continue
                    if solver.status == 'failed':
                        raise ValueError('Radau failed: ' + str(message))
                    previous_time = accepted_time
                    accepted_time = float(solver.t)
                    accepted_state = solver.y.copy()
                    solver.max_step = experiment.max_step_s
                    step = accepted_time - previous_time
                    accepted_steps += 1
                    min_step = step if min_step is None else min(min_step, step)
                    max_step = step if max_step is None else max(max_step, step)
                    recent_steps.append({'start_s': previous_time, 'end_s': accepted_time, 'step_s': step})
                    segment_steps.append(step)
                    while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                        seconds = float(saved_times[saved_ordinal])
                        if seconds != accepted_time:
                            raise ValueError('saved physical observation must coincide with accepted Radau endpoint')
                        saved_state = accepted_state.copy()
                        violation = positivity_violation(saved_state, count, seconds)
                        if violation:
                            raise ValueError('saved inventory positivity violation: ' + str(violation))
                        observations.append((seconds, saved_state))
                        saved_ordinal += 1
                state = accepted_state.copy()
                integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(segment_steps), 'min_adaptive_step_s': min(segment_steps), 'max_adaptive_step_s': max(segment_steps), 'final_solver_nfev': solver.nfev, 'final_solver_njev': solver.njev, 'final_solver_nlu': solver.nlu, 'discarded_solver_statistics_cumulative': dict(rejected_solver_statistics)})
                if diagnostic_stop_s is not None and accepted_time >= diagnostic_stop_s:
                    raise HydraulicDiagnosticStop('declared short diagnostic stop; not a completed hydraulic case', progress())
        except Exception as error:
            if getattr(error, 'diagnostic_stop', False):
                raise
            raise HydraulicExecutionFailure(str(error), progress()) from error
        if accepted_time != experiment.duration_s or saved_ordinal != len(saved_times):
            raise HydraulicExecutionFailure('physical event/observations incomplete', progress())
        try:
            saved_section_diagnostics = [{'time_s': seconds, **inventory_snapshot(model, system, current, crown_transition_width_m)} for seconds, current in observations]
            flux_probes = []
            for seconds, current in observations:
                source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and seconds < experiment.pulse_duration_s else 0.0
                flux_probes.append(flux_snapshot(model, system, seconds, current, source_q, crown_transition_width_m, experiment.tailwater_head_m))
            if work['link_evaluations'] > experiment.max_link_evaluations:
                raise ValueError('independent 1D diagnostic flux work bound exceeded')
            rows = _i16_np.array([current for seconds, current in observations])
            all_origins = rows[:, :3 * count].reshape(-1, 3, count)
            volumes = all_origins.sum(axis=1)
            masses = rows[:, count:3 * count].reshape(-1, 2, count)
            minimum_index = _i16_np.unravel_index(_i16_np.argmin(all_origins), all_origins.shape)
            saved_mass_extrema = {'minimum_origin_inventory_m3': float(all_origins[minimum_index]), 'time_s': float(saved_times[minimum_index[0]]), 'origin': ('untraced', 'source', 'tailwater')[minimum_index[1]], 'cell_id': model.cells[minimum_index[2]].cell_id, 'per_origin_minimum_m3': all_origins.min(axis=(0, 2)).tolist(), 'max_water_minus_origin_sum_m3': float(_i16_np.max(abs(volumes - all_origins.sum(axis=1))))}
            if not _i16_np.isfinite(rows).all() or _i16_np.any(all_origins < 0) or _i16_np.any(volumes <= 0):
                raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
            ledgers = rows[:, ledger_start:ledger_start + 6]
            residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
            residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
            residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
            untraced_out = rows[:, ledger_start + 6 + 4 * link_count]
            residual_untraced = all_origins[:, 0].sum(axis=1) - initial_volumes.sum() + untraced_out
            threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
            if max((_i16_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater, residual_untraced))) > threshold:
                raise ValueError('water/tracer conservation gate failed')
            heads = _i16_np.array([physical(row[:3 * count])[1] for row in rows])
            stages, pressure = ([], [])
            for head_row in heads:
                stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
                pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
            sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
            reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
            if _i16_time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024 ** 3:
                raise ValueError('final independent 1D wall/RSS bound exceeded')
            return {'schema': SCHEMA, 'numerical_version': NUMERICAL_VERSION, 'model_version': MODEL_VERSION, 'friction_policy': {'width_m': crown_transition_width_m, 'transition_start': 'crown', 'transition_end': 'crown+width_m', 'actual_perimeter_unchanged': True, 'storage_area_unchanged': True, 'pressure_slot_width_unchanged': True, 'roof_length_source': 'sum_actual_polygon_edges_with_both_endpoints_at_crown', 'constitutive_kind': 'C1_effective_roof_contact_friction' if crown_transition_width_m > 0 else 'legacy_actual_perimeter', 'contact_polynomial': 'u*u*(3-2*u)_for_0<=u<=1'}, 'saved_section_diagnostics': saved_section_diagnostics, 'instantaneous_flux_probes': flux_probes, 'execution_progress': progress(), 'jacobian_policy': {**jacobian_policy(model, crown_transition_width_m), 'observed_max_head_step_m': work.get('jacobian_max_observed_head_step_m', 0.0)}, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_Radau', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'untraced_water_volume_m3': all_origins[:, 0].tolist(), 'inventory_policy': inventory_policy(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:ledger_start + 6 + 3 * link_count].tolist(), 'paired_link_untraced_integral_m3': rows[:, ledger_start + 6 + 3 * link_count:ledger_start + 6 + 4 * link_count].tolist(), 'outlet_untraced_out_m3': untraced_out.tolist(), 'max_untraced_residual_m3': float(_i16_np.max(abs(residual_untraced))), 'saved_mass_extrema': saved_mass_extrema, 'dense_positivity_witness': {'policy': 'no_dense_inventory_output_saved_times_are_Radau_endpoints', 'interpolated_inventory_samples': 0, 'continuous_between_steps_positivity_certified': False, 'candidate_endpoint_checks': work['accepted_endpoint_inventory_checks'], 'accepted_steps': accepted_steps, 'last_rejected': last_positivity_rejection, 'negative_inventory_tolerance_m3': 0.0}, 'max_water_residual_m3': float(_i16_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i16_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i16_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': system.peak_rss(), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i16_time.monotonic() - started}}
        except Exception as error:
            raise HydraulicExecutionFailure(str(error), progress()) from error
    return run_experiment
SCHEMA = 'td-hybrid-river-hydraulics-v1'
QUAD_POINTS, QUAD_WEIGHTS = _i17_np.polynomial.legendre.leggauss(12)

@_i17_dataclass(frozen=True)
class Section:
    kind: str
    pieces: tuple = ()
    polygon: tuple = ()
    pressure_slot_width_m: float = 0.0

    @classmethod
    def from_record(cls, record):
        if record['kind'] == 'native_bed':
            if record.get('sidewall_extension') != 'explicit_engineering_vertical':
                raise ValueError('surface overflow walls must be explicitly engineered')
            section = cls('native_bed', tuple(((float(piece['width_m']), tuple((float(value) for value in piece['bed_coefficients_m_t012']))) for piece in record['pieces'])))
        elif record['kind'] == 'open_polyline':
            if record.get('sidewall_extension') != 'explicit_engineering_vertical':
                raise ValueError('surface overflow walls must be explicitly engineered')
            points = record['polyline_transverse_elevation_m']
            if len(points) < 2 or len(points) > 256:
                raise ValueError('bounded actual open cross section required')
            pieces = []
            for start, end in zip(points[:-1], points[1:]):
                pieces.append((common_positive(end[0] - start[0], 'ordered section width'), (float(start[1]), float(end[1] - start[1]), 0.0)))
            section = cls('open_polyline', tuple(pieces))
        elif record['kind'] == 'closed_polygon':
            section = cls('closed_polygon', polygon=tuple((tuple((float(value) for value in point)) for point in record['polygon_transverse_elevation_m'])), pressure_slot_width_m=float(record['pressure_slot_width_m']))
        else:
            raise ValueError('unsupported actual section representation')
        section.validate()
        return section

    def validate(self):
        if self.kind in ('native_bed', 'open_polyline'):
            if not self.pieces:
                raise ValueError('empty native section')
            previous = None
            for width, coefficients in self.pieces:
                common_positive(width, 'native width')
                if len(coefficients) != 3 or not all((_i17_math.isfinite(value) for value in coefficients)):
                    raise ValueError('invalid native polynomial')
                if previous is not None and abs(coefficients[0] - previous) > 1e-08:
                    raise ValueError('native section discontinuity')
                previous = sum(coefficients)
        elif self.kind == 'closed_polygon':
            polygon = _i17_np.asarray(self.polygon)
            if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3 or (len(polygon) > 256) or (not _i17_np.isfinite(polygon).all()):
                raise ValueError('invalid bounded polygon section')
            common_positive(self.pressure_slot_width_m, 'engineered pressure compliance width')
            from shapely.geometry import Polygon
            shape = Polygon(polygon - polygon[0])
            if not shape.is_valid or shape.area <= 0 or len(set(self.polygon)) != len(self.polygon):
                raise ValueError('self-intersecting or degenerate actual section')
        else:
            raise ValueError('unsupported section kind')

    @property
    def floor_m(self):
        if self.kind == 'closed_polygon':
            return min((point[1] for point in self.polygon))
        values = []
        for width, (constant, linear, quadratic) in self.pieces:
            values.extend((constant, constant + linear + quadratic))
            if quadratic and 0 < -linear / (2 * quadratic) < 1:
                fraction = -linear / (2 * quadratic)
                values.append(constant + linear * fraction + quadratic * fraction ** 2)
        return min(values)

    @property
    def crown_m(self):
        return max((point[1] for point in self.polygon)) if self.kind == 'closed_polygon' else None

    def area_perimeter(self, head_m):
        if not _i17_math.isfinite(head_m):
            raise ValueError('nonfinite section head')
        if head_m <= self.floor_m:
            return (0.0, 0.0)
        if self.kind in ('native_bed', 'open_polyline'):
            area, perimeter = (0.0, 0.0)
            for width, coefficients in self.pieces:
                constant, linear, quadratic = coefficients
                for lower, upper in common_submerged_intervals(coefficients, head_m):
                    area += width * ((head_m - constant) * (upper - lower) - linear * (upper ** 2 - lower ** 2) / 2 - quadratic * (upper ** 3 - lower ** 3) / 3)
                    fractions = lower + (QUAD_POINTS + 1) * (upper - lower) / 2
                    perimeter += float(_i17_np.dot(QUAD_WEIGHTS, _i17_np.sqrt(width ** 2 + (linear + 2 * quadratic * fractions) ** 2))) * (upper - lower) / 2
            perimeter += max(0.0, head_m - self.pieces[0][1][0]) + max(0.0, head_m - sum(self.pieces[-1][1]))
            return (area, perimeter)
        crown = self.crown_m
        level = min(head_m, crown)
        clipped, perimeter = ([], 0.0)
        for start, end in zip(self.polygon, self.polygon[1:] + self.polygon[:1]):
            start_inside, end_inside = (start[1] <= level, end[1] <= level)
            fraction = None
            if start_inside != end_inside:
                fraction = (level - start[1]) / (end[1] - start[1])
                intersection = (start[0] + fraction * (end[0] - start[0]), level)
                clipped.append(intersection)
            if end_inside:
                clipped.append(end)
            length = _i17_math.dist(start, end)
            if start_inside and end_inside:
                perimeter += length
            elif fraction is not None:
                perimeter += length * (fraction if start_inside else 1 - fraction)
        area = 0.0
        if len(clipped) >= 3:
            local = [(point[0] - clipped[0][0], point[1] - clipped[0][1]) for point in clipped]
            area = abs(sum((start[0] * end[1] - end[0] * start[1] for start, end in zip(local, local[1:] + local[:1])))) / 2
        return (area + self.pressure_slot_width_m * max(0.0, head_m - crown), perimeter)

    def head_for_area(self, area_m2):
        common_positive(area_m2, 'stored section area')
        lower = self.floor_m
        upper = max(lower + 1, self.crown_m or lower + 1)
        while self.area_perimeter(upper)[0] < area_m2:
            upper = lower + 2 * (upper - lower)
            if upper - lower > 1000000.0:
                raise ValueError('head exceeds bounded model range')
        return _i17_brentq(lambda head: self.area_perimeter(head)[0] - area_m2, lower, upper, xtol=1e-10)

@_i17_dataclass(frozen=True)
class Cell:
    cell_id: str
    kind: str
    length_m: float
    roughness_manning: float
    section: Section

@_i17_dataclass(frozen=True)
class Model:
    cells: tuple[Cell, ...]
    links: tuple[common_Link, ...]
    head_regularization_m: float = 0.0001
    donor_regularization_m3: float = 1e-06

    @classmethod
    def from_geometry(cls, geometry):
        cells = tuple((Cell(cell['cell_id'], cell['kind'], common_positive(cell['length_m'], 'cell length'), common_positive(cell['roughness_manning'], 'Manning roughness'), Section.from_record(cell['section'])) for cell in geometry['hydraulic_cells']))
        links = tuple((common_Link(link['link_id'], link['from_cell_id'], link['to_cell_id'], common_positive(link['length_m'], 'link length'), link['kind']) for link in geometry['hydraulic_links']))
        model = cls(cells, links)
        model.validate()
        return model

    def validate(self):
        count = len(self.cells)
        if not 3 <= count <= COMMON_MAX_CELLS or len(self.links) != count - 1:
            raise ValueError('bounded sink/conduit/spring chain required')
        if len(set((cell.cell_id for cell in self.cells))) != count or len(set((link.link_id for link in self.links))) != len(self.links):
            raise ValueError('duplicate hydraulic ownership')
        kinds = [cell.kind for cell in self.cells]
        if kinds[0] != 'surface' or kinds[-1] != 'surface' or 'underground' not in kinds:
            raise ValueError('invalid hydraulic cell types')
        first_underground, last_underground = (kinds.index('underground'), count - 1 - kinds[::-1].index('underground'))
        if any((kind != 'underground' for kind in kinds[first_underground:last_underground + 1])) or any((kind != 'surface' for kind in kinds[:first_underground] + kinds[last_underground + 1:])):
            raise ValueError('hydraulic route must have consecutive surface-in/conduit/surface-out cells')
        for cell in self.cells:
            common_positive(cell.length_m, 'cell length')
            common_positive(cell.roughness_manning, 'roughness')
            cell.section.validate()
            if cell.section.kind != ('open_polyline' if cell.kind == 'surface' else 'closed_polygon'):
                raise ValueError('cell/section physical type mismatch')
        for ordinal, link in enumerate(self.links):
            if (link.from_cell_id, link.to_cell_id) != (self.cells[ordinal].cell_id, self.cells[ordinal + 1].cell_id):
                raise ValueError('links must be actual ordered cell connections')
            pair = kinds[ordinal:ordinal + 2]
            expected = {('surface', 'surface'): 'surface_half_arm', ('surface', 'underground'): 'sink_exchange', ('underground', 'surface'): 'spring_exchange', ('underground', 'underground'): 'conduit'}[tuple(pair)]
            if link.kind != expected:
                raise ValueError('missing explicit paired surface/conduit exchange')
            common_positive(link.length_m, 'link length')
        common_positive(self.head_regularization_m, 'head regularization')
        common_positive(self.donor_regularization_m3, 'donor regularization')

def run_experiment(model: Model, experiment: common_Experiment):
    model.validate()
    experiment.validate(model)
    count = len(model.cells)
    initial_volumes = _i17_np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if _i17_np.any(initial_volumes <= 0):
        raise ValueError('initial storage must be strictly positive')
    link_count = len(model.links)
    ledger_start = 3 * count
    state = _i17_np.zeros(ledger_start + 6 + 3 * link_count)
    state[:count] = _i17_np.log(initial_volumes)
    work = {'rhs_evaluations': 0, 'link_evaluations': 0, 'old_hll_face_work': 0}
    started = _i17_time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss

    def physical(log_volumes):
        if not _i17_np.isfinite(log_volumes).all() or _i17_np.any(abs(log_volumes) > 600):
            raise ValueError('storage transform exceeds physical range')
        volumes = _i17_np.exp(log_volumes)
        heads = _i17_np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any((head <= cell.section.floor_m for cell, head in zip(model.cells, heads))):
            raise ValueError('positive storage is below representable section depth; no floor clamp')
        capacities = _i17_np.array([common_conveyance(cell, head) for cell, head in zip(model.cells, heads)])
        return (volumes, heads, capacities)

    def rhs_for(source_q):

        def rhs(seconds, current):
            nonlocal peak_rss
            work['rhs_evaluations'] += 1
            work['link_evaluations'] += link_count + 1
            if work['rhs_evaluations'] > experiment.max_rhs_evaluations or work['link_evaluations'] > experiment.max_link_evaluations or _i17_time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError('independent 1D work/time bound exceeded')
            if work['rhs_evaluations'] % 32 == 1:
                peak_rss = max(peak_rss, process.memory_info().rss)
                if peak_rss > 1024 ** 3:
                    raise ValueError('1GiB hydraulic RSS limit exceeded')
            volumes, heads, capacities = physical(current[:count])
            concentrations = current[count:3 * count].reshape(2, count) / volumes
            volume_rates = _i17_np.zeros(count)
            tracer_rates = _i17_np.zeros((2, count))
            derivative = _i17_np.zeros_like(current)
            for ordinal, link in enumerate(model.links):
                flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor = ordinal if flow >= 0 else ordinal + 1
                flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                tracer_flow = flow * concentrations[:, donor]
                volume_rates[ordinal] -= flow
                volume_rates[ordinal + 1] += flow
                tracer_rates[:, ordinal] -= tracer_flow
                tracer_rates[:, ordinal + 1] += tracer_flow
                derivative[ledger_start + 6 + ordinal] = flow
                derivative[ledger_start + 6 + link_count + ordinal] = tracer_flow[0]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = tracer_flow[1]
            boundary_capacity = min(capacities[-1], common_conveyance(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                boundary_tracer = outlet_flow * concentrations[:, -1]
                derivative[ledger_start + 1] = outlet_flow
                derivative[ledger_start + 3] = boundary_tracer[0]
                derivative[ledger_start + 5] = boundary_tracer[1]
            else:
                boundary_tracer = _i17_np.array([0.0, outlet_flow])
                derivative[ledger_start + 2] = -outlet_flow
                derivative[ledger_start + 4] = -outlet_flow
            volume_rates[-1] -= outlet_flow
            tracer_rates[:, -1] -= boundary_tracer
            volume_rates[0] += source_q
            tracer_rates[0, 0] += source_q
            derivative[ledger_start] = source_q
            derivative[:count] = volume_rates / volumes
            derivative[count:3 * count] = tracer_rates.ravel()
            return derivative
        return rhs
    breaks = [0.0, experiment.duration_s]
    if experiment.scenario == 'pulse':
        breaks.insert(1, experiment.pulse_duration_s)
    observations = []
    integration_segments = []
    saved_times = _i17_np.asarray(experiment.saved_times_s)
    for lower, upper in zip(breaks[:-1], breaks[1:]):
        source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
        solution = _i17_solve_ivp(rhs_for(source_q), (lower, upper), state, method='Radau', dense_output=True, max_step=experiment.max_step_s, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance)
        if not solution.success:
            raise ValueError('Radau failed: ' + solution.message)
        steps = _i17_np.diff(solution.t)
        integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(steps), 'min_adaptive_step_s': float(steps.min()), 'max_adaptive_step_s': float(steps.max()), 'nfev': solution.nfev, 'njev': solution.njev, 'nlu': solution.nlu})
        selected = saved_times[(saved_times >= lower) & (saved_times <= upper)]
        for seconds in selected:
            if observations and observations[-1][0] == seconds:
                continue
            observations.append((float(seconds), solution.sol(seconds)))
        state = solution.y[:, -1]
    rows = _i17_np.array([current for seconds, current in observations])
    volumes = _i17_np.exp(rows[:, :count])
    masses = rows[:, count:3 * count].reshape(-1, 2, count)
    if not _i17_np.isfinite(rows).all() or _i17_np.any(masses < 0) or _i17_np.any(masses.sum(axis=1) > volumes + experiment.absolute_tolerance * 100):
        raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
    ledgers = rows[:, ledger_start:ledger_start + 6]
    residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
    residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
    residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
    threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
    if max((_i17_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater))) > threshold:
        raise ValueError('water/tracer conservation gate failed')
    heads = _i17_np.array([physical(row[:count])[1] for row in rows])
    stages, pressure = ([], [])
    for head_row in heads:
        stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
    arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
    sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
    reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
    return {'schema': SCHEMA, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_Radau', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:].tolist(), 'max_water_residual_m3': float(_i17_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i17_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i17_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': max(peak_rss, process.memory_info().rss), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i17_time.monotonic() - started}}
RADAU_SCHEMA = 'td-hybrid-river-hydraulics-v6'
NUMERICAL_VERSION = 'three_origin_analytic_native_chain_Radau-v6'
MODEL_VERSION = 'explicit_roof_friction_contact_transition-v5'
JACOBIAN_HEAD_FRACTION = 0.01
JACOBIAN_MAX_HEAD_STEP_M = 1e-06
DIRECT_VOLUME_RELATIVE_STEP = 1e-06

def radau_run_experiment(model: common_Model, experiment: common_Experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    if diagnostic_stop_s is not None and (not _i19_math.isfinite(diagnostic_stop_s) or not 0 < diagnostic_stop_s <= experiment.duration_s):
        raise ValueError('diagnostic stop must be positive and within the unchanged physical event')
    last_evaluation = {'context': 'not_started', 'time_s': None}
    last_trial_state = None

    def observe_rhs(seconds, current, context):
        nonlocal last_trial_state
        last_evaluation.update(context=context, time_s=float(seconds))
        last_trial_state = current.copy()
    system = build_system(model, experiment, crown_transition_width_m, rhs_observer=observe_rhs)
    count, link_count = (system.count, len(model.links))
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes, work, started = (system.initial_volumes, system.work, system.started)
    physical = system.physical
    accepted_state, accepted_time = (state.copy(), 0.0)
    accepted_steps, min_step, max_step = (0, None, None)
    last_positivity_rejection = None
    saved_mass_extrema = None
    recent_steps = _i19_deque(maxlen=16)
    observations = [(0.0, state.copy())]
    integration_segments = []
    rejected_solver_statistics = {'nfev': 0, 'njev': 0, 'nlu': 0}
    saved_times = _i19_np.asarray(experiment.saved_times_s)
    saved_ordinal = 1

    def progress():
        observed_origins = _i19_np.array([current[:3 * count].reshape(3, count) for seconds, current in observations])
        observed_index = _i19_np.unravel_index(_i19_np.argmin(observed_origins), observed_origins.shape)
        observed_extrema = {'minimum_origin_inventory_m3': float(observed_origins[observed_index]), 'time_s': float(observations[observed_index[0]][0]), 'origin': ('untraced', 'source', 'tailwater')[observed_index[1]], 'cell_id': model.cells[observed_index[2]].cell_id, 'per_origin_minimum_m3': observed_origins.min(axis=(0, 2)).tolist()}
        elapsed = _i19_time.monotonic() - started
        guard = None
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations:
            guard = 'max_rhs_evaluations'
        elif work['link_evaluations'] > experiment.max_link_evaluations:
            guard = 'max_link_evaluations'
        elif elapsed > experiment.max_wall_seconds:
            guard = 'max_wall_seconds'
        elif system.peak_rss() > 1024 ** 3:
            guard = 'max_rss_bytes'
        trial = None
        if last_trial_state is not None:
            trial = {'state_all_finite': bool(_i19_np.isfinite(last_trial_state).all()), 'state': [float(value) if _i19_math.isfinite(value) else None for value in last_trial_state], 'is_accepted_state': False, 'state_layout': 'untracedMass/sourceMass/tailwaterMass/oldSixBoundary/threePaired/untracedPaired/untracedOutlet'}
        try:
            accepted_inventory = inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
        except Exception as snapshot_error:
            accepted_inventory = {'snapshot_error': str(snapshot_error), 'state': [float(value) if _i19_math.isfinite(value) else None for value in accepted_state]}
        return {'last_accepted_physical_time_s': accepted_time, 'configured_physical_duration_s': experiment.duration_s, 'diagnostic_stop_s': diagnostic_stop_s, 'physical_event_complete': accepted_time == experiment.duration_s, 'work': dict(work), 'last_positivity_rejection': last_positivity_rejection, 'saved_mass_extrema': saved_mass_extrema if saved_mass_extrema is not None else observed_extrema, 'elapsed_wall_seconds': elapsed, 'triggered_guard': guard, 'discarded_solver_statistics': dict(rejected_solver_statistics), 'max_rhs_evaluations': experiment.max_rhs_evaluations, 'max_link_evaluations': experiment.max_link_evaluations, 'max_wall_seconds': experiment.max_wall_seconds, 'accepted_steps': accepted_steps, 'min_accepted_step_s': min_step, 'max_accepted_step_s': max_step, 'recent_accepted_steps': list(recent_steps), 'last_evaluation': dict(last_evaluation), 'last_trial': trial, 'last_accepted_inventory': accepted_inventory, 'actual_peak_rss_bytes': system.peak_rss(), 'model_version': MODEL_VERSION, 'crown_friction_transition_width_m': crown_transition_width_m, 'inventory_scope': 'actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume'}
    breaks = [0.0, experiment.duration_s, *experiment.saved_times_s]
    if experiment.scenario == 'pulse':
        breaks.append(experiment.pulse_duration_s)
    breaks = sorted(set(breaks))
    try:
        for lower, full_upper in zip(breaks[:-1], breaks[1:]):
            upper = min(full_upper, diagnostic_stop_s) if diagnostic_stop_s is not None else full_upper
            if upper <= lower:
                break
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
            raw_rhs, raw_jacobian = (system.rhs_for(source_q), system.jacobian_for(source_q))

            def tracked_rhs(seconds, current):
                return raw_rhs(seconds, current)

            def tracked_jacobian(seconds, current):
                return raw_jacobian(seconds, current)

            def construct_solver(seconds, current, maximum_step, first_step=None):
                nonlocal last_positivity_rejection
                while True:
                    try:
                        work['radau_constructor_attempts'] += 1
                        return _i19_Radau(tracked_rhs, seconds, current, upper, max_step=maximum_step, first_step=first_step, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=tracked_jacobian)
                    except ValueError as error:
                        if not getattr(error, 'nonpositive_water_trial', False):
                            raise
                        work['constructor_nonpositive_retries'] += 1
                        work['nonpositive_total_trial_retries'] += 1
                        last_positivity_rejection = {'time_s': seconds, 'trial_error': str(error), 'context': 'Radau_constructor', 'accepted_state_unchanged': True}
                        bound = min(maximum_step, upper - seconds)
                        if first_step is not None:
                            bound = min(bound, first_step)
                        first_step = bound / 2
                        maximum_step = min(maximum_step, first_step)
                        if first_step <= 16 * _i19_math.ulp(seconds) or first_step <= 0:
                            raise ValueError('constructor positivity retry step unrepresentable; no clamp')
                        work['solver_reinitializations'] += 1
            work['observation_segment_initializations'] += 1
            solver = construct_solver(lower, state, experiment.max_step_s)
            segment_steps = []
            while solver.status == 'running':
                previous_state = accepted_state.copy()
                attempted_step = min(solver.h_abs, upper - accepted_time)
                trial_error = None
                try:
                    message = solver.step()
                except ValueError as error:
                    if not getattr(error, 'nonpositive_water_trial', False):
                        raise
                    trial_error = str(error)
                if trial_error is None and solver.status != 'failed':
                    work['accepted_endpoint_inventory_checks'] += 1
                    violation = positivity_violation(solver.y, count, solver.t)
                    actual_candidate_step = solver.t - accepted_time
                else:
                    violation = {'time_s': accepted_time, 'trial_error': trial_error} if trial_error else None
                    actual_candidate_step = attempted_step
                if violation is not None:
                    last_positivity_rejection = violation
                    if 'cell_ordinal' in violation:
                        last_positivity_rejection['cell_id'] = model.cells[violation['cell_ordinal']].cell_id
                    work['positivity_rejected_steps'] += 1
                    if trial_error:
                        work['nonpositive_total_trial_retries'] += 1
                    retry_step = min(attempted_step, actual_candidate_step) / 2
                    if retry_step <= 16 * _i19_math.ulp(accepted_time) or retry_step <= 0:
                        raise ValueError('strict positivity retry step unrepresentable; no clamp')
                    work['solver_reinitializations'] += 1
                    for name in rejected_solver_statistics:
                        rejected_solver_statistics[name] += getattr(solver, name)
                    solver = construct_solver(accepted_time, previous_state, min(experiment.max_step_s, retry_step), first_step=retry_step)
                    continue
                if solver.status == 'failed':
                    raise ValueError('Radau failed: ' + str(message))
                previous_time = accepted_time
                accepted_time = float(solver.t)
                accepted_state = solver.y.copy()
                solver.max_step = experiment.max_step_s
                step = accepted_time - previous_time
                accepted_steps += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                recent_steps.append({'start_s': previous_time, 'end_s': accepted_time, 'step_s': step})
                segment_steps.append(step)
                while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                    seconds = float(saved_times[saved_ordinal])
                    if seconds != accepted_time:
                        raise ValueError('saved physical observation must coincide with accepted Radau endpoint')
                    saved_state = accepted_state.copy()
                    violation = positivity_violation(saved_state, count, seconds)
                    if violation:
                        raise ValueError('saved inventory positivity violation: ' + str(violation))
                    observations.append((seconds, saved_state))
                    saved_ordinal += 1
            state = accepted_state.copy()
            integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(segment_steps), 'min_adaptive_step_s': min(segment_steps), 'max_adaptive_step_s': max(segment_steps), 'final_solver_nfev': solver.nfev, 'final_solver_njev': solver.njev, 'final_solver_nlu': solver.nlu, 'discarded_solver_statistics_cumulative': dict(rejected_solver_statistics)})
            if diagnostic_stop_s is not None and accepted_time >= diagnostic_stop_s:
                raise _diagnostic_stop('declared short diagnostic stop; not a completed hydraulic case', progress())
    except Exception as error:
        if getattr(error, 'diagnostic_stop', False):
            raise
        raise _execution_failure(str(error), progress()) from error
    if accepted_time != experiment.duration_s or saved_ordinal != len(saved_times):
        raise _execution_failure('physical event/observations incomplete', progress())
    try:
        saved_section_diagnostics = [{'time_s': seconds, **inventory_snapshot(model, system, current, crown_transition_width_m)} for seconds, current in observations]
        flux_probes = []
        for seconds, current in observations:
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and seconds < experiment.pulse_duration_s else 0.0
            flux_probes.append(flux_snapshot(model, system, seconds, current, source_q, crown_transition_width_m, experiment.tailwater_head_m))
        if work['link_evaluations'] > experiment.max_link_evaluations:
            raise ValueError('independent 1D diagnostic flux work bound exceeded')
        rows = _i19_np.array([current for seconds, current in observations])
        all_origins = rows[:, :3 * count].reshape(-1, 3, count)
        volumes = all_origins.sum(axis=1)
        masses = rows[:, count:3 * count].reshape(-1, 2, count)
        minimum_index = _i19_np.unravel_index(_i19_np.argmin(all_origins), all_origins.shape)
        saved_mass_extrema = {'minimum_origin_inventory_m3': float(all_origins[minimum_index]), 'time_s': float(saved_times[minimum_index[0]]), 'origin': ('untraced', 'source', 'tailwater')[minimum_index[1]], 'cell_id': model.cells[minimum_index[2]].cell_id, 'per_origin_minimum_m3': all_origins.min(axis=(0, 2)).tolist(), 'max_water_minus_origin_sum_m3': float(_i19_np.max(abs(volumes - all_origins.sum(axis=1))))}
        if not _i19_np.isfinite(rows).all() or _i19_np.any(all_origins < 0) or _i19_np.any(volumes <= 0):
            raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
        ledgers = rows[:, ledger_start:ledger_start + 6]
        residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
        residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
        residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
        untraced_out = rows[:, ledger_start + 6 + 4 * link_count]
        residual_untraced = all_origins[:, 0].sum(axis=1) - initial_volumes.sum() + untraced_out
        threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
        if max((_i19_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater, residual_untraced))) > threshold:
            raise ValueError('water/tracer conservation gate failed')
        heads = _i19_np.array([physical(row[:3 * count])[1] for row in rows])
        stages, pressure = ([], [])
        for head_row in heads:
            stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
        sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
        reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
        if _i19_time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024 ** 3:
            raise ValueError('final independent 1D wall/RSS bound exceeded')
        return {'schema': RADAU_SCHEMA, 'numerical_version': NUMERICAL_VERSION, 'model_version': MODEL_VERSION, 'friction_policy': {'width_m': crown_transition_width_m, 'transition_start': 'crown', 'transition_end': 'crown+width_m', 'actual_perimeter_unchanged': True, 'storage_area_unchanged': True, 'pressure_slot_width_unchanged': True, 'roof_length_source': 'sum_actual_polygon_edges_with_both_endpoints_at_crown', 'constitutive_kind': 'C1_effective_roof_contact_friction' if crown_transition_width_m > 0 else 'legacy_actual_perimeter', 'contact_polynomial': 'u*u*(3-2*u)_for_0<=u<=1'}, 'saved_section_diagnostics': saved_section_diagnostics, 'instantaneous_flux_probes': flux_probes, 'execution_progress': progress(), 'jacobian_policy': {**jacobian_policy(model, crown_transition_width_m), 'observed_max_head_step_m': work.get('jacobian_max_observed_head_step_m', 0.0)}, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_Radau', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'untraced_water_volume_m3': all_origins[:, 0].tolist(), 'inventory_policy': inventory_policy(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:ledger_start + 6 + 3 * link_count].tolist(), 'paired_link_untraced_integral_m3': rows[:, ledger_start + 6 + 3 * link_count:ledger_start + 6 + 4 * link_count].tolist(), 'outlet_untraced_out_m3': untraced_out.tolist(), 'max_untraced_residual_m3': float(_i19_np.max(abs(residual_untraced))), 'saved_mass_extrema': saved_mass_extrema, 'dense_positivity_witness': {'policy': 'no_dense_inventory_output_saved_times_are_Radau_endpoints', 'interpolated_inventory_samples': 0, 'continuous_between_steps_positivity_certified': False, 'candidate_endpoint_checks': work['accepted_endpoint_inventory_checks'], 'accepted_steps': accepted_steps, 'last_rejected': last_positivity_rejection, 'negative_inventory_tolerance_m3': 0.0}, 'max_water_residual_m3': float(_i19_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i19_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i19_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': system.peak_rss(), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i19_time.monotonic() - started}}
    except Exception as error:
        raise _execution_failure(str(error), progress()) from error
FIXED_LOG_SCHEMA = 'td-hybrid-river-hydraulics-v3'
FIXED_LOG_NUMERICAL_VERSION = 'fixed_log_volume_difference_analytic_tracer_jacobian-v3'
LOG_VOLUME_DIFFERENCE_STEP = 1e-06

def fixed_log_build_system(model: Model, experiment: common_Experiment):
    model.validate()
    experiment.validate(model)
    count = len(model.cells)
    initial_volumes = _i20_np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if _i20_np.any(initial_volumes <= 0):
        raise ValueError('initial storage must be strictly positive')
    link_count = len(model.links)
    ledger_start = 3 * count
    state = _i20_np.zeros(ledger_start + 6 + 3 * link_count)
    state[:count] = _i20_np.log(initial_volumes)
    work = {'rhs_evaluations': 0, 'link_evaluations': 0, 'old_hll_face_work': 0, 'jacobian_evaluations': 0, 'jacobian_rhs_evaluations': 0}
    started = _i20_time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss

    def physical(log_volumes):
        if not _i20_np.isfinite(log_volumes).all() or _i20_np.any(abs(log_volumes) > 600):
            raise ValueError('storage transform exceeds physical range')
        volumes = _i20_np.exp(log_volumes)
        heads = _i20_np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any((head <= cell.section.floor_m for cell, head in zip(model.cells, heads))):
            raise ValueError('positive storage is below representable section depth; no floor clamp')
        capacities = _i20_np.array([common_conveyance(cell, head) for cell, head in zip(model.cells, heads)])
        return (volumes, heads, capacities)

    def rhs_for(source_q):

        def rhs(seconds, current):
            nonlocal peak_rss
            work['rhs_evaluations'] += 1
            work['link_evaluations'] += link_count + 1
            if work['rhs_evaluations'] > experiment.max_rhs_evaluations or work['link_evaluations'] > experiment.max_link_evaluations or _i20_time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError('independent 1D work/time bound exceeded')
            if work['rhs_evaluations'] % 32 == 1:
                peak_rss = max(peak_rss, process.memory_info().rss)
                if peak_rss > 1024 ** 3:
                    raise ValueError('1GiB hydraulic RSS limit exceeded')
            volumes, heads, capacities = physical(current[:count])
            concentrations = current[count:3 * count].reshape(2, count) / volumes
            volume_rates = _i20_np.zeros(count)
            tracer_rates = _i20_np.zeros((2, count))
            derivative = _i20_np.zeros_like(current)
            for ordinal, link in enumerate(model.links):
                flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor = ordinal if flow >= 0 else ordinal + 1
                flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                tracer_flow = flow * concentrations[:, donor]
                volume_rates[ordinal] -= flow
                volume_rates[ordinal + 1] += flow
                tracer_rates[:, ordinal] -= tracer_flow
                tracer_rates[:, ordinal + 1] += tracer_flow
                derivative[ledger_start + 6 + ordinal] = flow
                derivative[ledger_start + 6 + link_count + ordinal] = tracer_flow[0]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = tracer_flow[1]
            boundary_capacity = min(capacities[-1], common_conveyance(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                boundary_tracer = outlet_flow * concentrations[:, -1]
                derivative[ledger_start + 1] = outlet_flow
                derivative[ledger_start + 3] = boundary_tracer[0]
                derivative[ledger_start + 5] = boundary_tracer[1]
            else:
                boundary_tracer = _i20_np.array([0.0, outlet_flow])
                derivative[ledger_start + 2] = -outlet_flow
                derivative[ledger_start + 4] = -outlet_flow
            volume_rates[-1] -= outlet_flow
            tracer_rates[:, -1] -= boundary_tracer
            volume_rates[0] += source_q
            tracer_rates[0, 0] += source_q
            derivative[ledger_start] = source_q
            derivative[:count] = volume_rates / volumes
            derivative[count:3 * count] = tracer_rates.ravel()
            return derivative
        return rhs

    def jacobian_for(source_q):
        rhs = rhs_for(source_q)

        def jacobian(seconds, current):
            if _i20_np.shape(current) != (len(state),) or not _i20_np.isfinite(current).all():
                raise ValueError('Jacobian requires a finite complete state vector')
            work['jacobian_evaluations'] += 1
            base = rhs(seconds, current)
            work['jacobian_rhs_evaluations'] += 1
            matrix = _i20_np.zeros((len(state), len(state)))
            for column in range(count):
                displaced = current.copy()
                displaced[column] += LOG_VOLUME_DIFFERENCE_STEP
                actual_step = displaced[column] - current[column]
                if actual_step <= 0 or not _i20_math.isfinite(actual_step):
                    raise ValueError('fixed log-volume Jacobian step is not representable')
                shifted = rhs(seconds, displaced)
                work['jacobian_rhs_evaluations'] += 1
                matrix[:, column] = (shifted - base) / actual_step
            volumes, heads, capacities = physical(current[:count])
            work['link_evaluations'] += link_count + 1
            if work['link_evaluations'] > experiment.max_link_evaluations or _i20_time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError('independent 1D Jacobian work/time bound exceeded')
            for ordinal, link in enumerate(model.links):
                flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor = ordinal if flow >= 0 else ordinal + 1
                flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                coefficient = flow / volumes[donor]
                for tracer in range(2):
                    mass_start = count * (tracer + 1)
                    column = mass_start + donor
                    matrix[mass_start + ordinal, column] -= coefficient
                    matrix[mass_start + ordinal + 1, column] += coefficient
                    ledger_row = ledger_start + 6 + (tracer + 1) * link_count + ordinal
                    matrix[ledger_row, column] += coefficient
            boundary_capacity = min(capacities[-1], common_conveyance(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                coefficient = outlet_flow / volumes[-1]
                for tracer, ledger_offset in ((0, 3), (1, 5)):
                    column = count * (tracer + 1) + count - 1
                    matrix[column, column] -= coefficient
                    matrix[ledger_start + ledger_offset, column] += coefficient
            if not _i20_np.isfinite(matrix).all():
                raise ValueError('explicit Jacobian contains nonfinite entries')
            return matrix
        return jacobian
    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for, lambda: max(peak_rss, process.memory_info().rss))

def fixed_log_run_experiment(model: Model, experiment: common_Experiment):
    system = fixed_log_build_system(model, experiment)
    count = system.count
    link_count = len(model.links)
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes = system.initial_volumes
    work = system.work
    started = system.started
    physical = system.physical
    rhs_for = system.rhs_for
    breaks = [0.0, experiment.duration_s]
    if experiment.scenario == 'pulse':
        breaks.insert(1, experiment.pulse_duration_s)
    observations = []
    integration_segments = []
    saved_times = _i20_np.asarray(experiment.saved_times_s)
    for lower, upper in zip(breaks[:-1], breaks[1:]):
        source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
        solution = _i20_solve_ivp(rhs_for(source_q), (lower, upper), state, method='Radau', dense_output=True, max_step=experiment.max_step_s, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=system.jacobian_for(source_q))
        if not solution.success:
            raise ValueError('Radau failed: ' + solution.message)
        steps = _i20_np.diff(solution.t)
        integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(steps), 'min_adaptive_step_s': float(steps.min()), 'max_adaptive_step_s': float(steps.max()), 'nfev': solution.nfev, 'njev': solution.njev, 'nlu': solution.nlu})
        selected = saved_times[(saved_times >= lower) & (saved_times <= upper)]
        for seconds in selected:
            if observations and observations[-1][0] == seconds:
                continue
            observations.append((float(seconds), solution.sol(seconds)))
        state = solution.y[:, -1]
    rows = _i20_np.array([current for seconds, current in observations])
    volumes = _i20_np.exp(rows[:, :count])
    masses = rows[:, count:3 * count].reshape(-1, 2, count)
    if not _i20_np.isfinite(rows).all() or _i20_np.any(masses < 0) or _i20_np.any(masses.sum(axis=1) > volumes + experiment.absolute_tolerance * 100):
        raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
    ledgers = rows[:, ledger_start:ledger_start + 6]
    residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
    residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
    residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
    threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
    if max((_i20_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater))) > threshold:
        raise ValueError('water/tracer conservation gate failed')
    heads = _i20_np.array([physical(row[:count])[1] for row in rows])
    stages, pressure = ([], [])
    for head_row in heads:
        stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
    arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
    sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
    reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
    return {'schema': FIXED_LOG_SCHEMA, 'numerical_version': FIXED_LOG_NUMERICAL_VERSION, 'jacobian_policy': {'log_volume_absolute_step': LOG_VOLUME_DIFFERENCE_STEP, 'step_units': 'dimensionless_log_volume_fixed_forward_difference', 'tracer_columns': 'analytic_donor_transport', 'ledger_feedback_columns': 'exact_zero', 'nonsmooth_scope': 'fixed_forward_secant_at_donor_kinks_crowns_and_horizontal_ledges_no_smoothing', 'scipy_adaptive_difference_factor_used': False}, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_Radau', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:].tolist(), 'max_water_residual_m3': float(_i20_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i20_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i20_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': system.peak_rss(), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i20_time.monotonic() - started}}
HEAD_BOUNDED_LOG_SCHEMA = 'td-hybrid-river-hydraulics-v4'
HEAD_BOUNDED_LOG_NUMERICAL_VERSION = 'head_bounded_log_difference_Radau_step_diagnostics-v4'
HEAD_BOUNDED_LOG_MODEL_VERSION = 'explicit_roof_friction_contact_transition-v4'

def head_bounded_log_jacobian_policy(model, width_m):
    cap = min(JACOBIAN_MAX_HEAD_STEP_M, model.head_regularization_m * JACOBIAN_HEAD_FRACTION)
    if width_m > 0:
        cap = min(cap, width_m * JACOBIAN_HEAD_FRACTION)
    return {'log_volume_nominal_absolute_step': LOG_VOLUME_DIFFERENCE_STEP, 'max_head_step_m': cap, 'nominal_head_ceiling_m': JACOBIAN_MAX_HEAD_STEP_M, 'head_cap_rule': 'min(nominal_head_ceiling_m,head_regularization_m*0.01,width_m*0.01_if_positive)', 'head_step_target_fraction_of_cap': 0.5, 'head_step_fraction_of_friction_transition': JACOBIAN_HEAD_FRACTION, 'head_step_float_margin': '16_ulp_of_base_head', 'step_units': 'dimensionless_log_volume_forward_difference_bounded_by_physical_head', 'tracer_columns': 'analytic_donor_transport', 'ledger_feedback_columns': 'exact_zero', 'nonsmooth_scope': 'fixed_forward_secant_at_exact_storage_slot_derivative_and_donor_min_ledges;C1_roof_contact_only_not_whole_RHS', 'scipy_adaptive_difference_factor_used': False}

def head_bounded_log_build_system(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, rhs_observer=None):
    validate_transition(crown_transition_width_m)
    model.validate()
    experiment.validate(model)
    count = len(model.cells)
    initial_volumes = _i21_np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if _i21_np.any(initial_volumes <= 0):
        raise ValueError('initial storage must be strictly positive')
    link_count = len(model.links)
    ledger_start = 3 * count
    state = _i21_np.zeros(ledger_start + 6 + 3 * link_count)
    state[:count] = _i21_np.log(initial_volumes)
    work = {'rhs_evaluations': 0, 'link_evaluations': 0, 'old_hll_face_work': 0, 'jacobian_evaluations': 0, 'jacobian_rhs_evaluations': 0}
    started = _i21_time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    roof_lengths = {cell.cell_id: roof_contact_length(cell.section) for cell in model.cells}

    def capacity_for(cell, head):
        return friction_state(cell, head, crown_transition_width_m, roof_lengths[cell.cell_id])['effective_manning_conveyance']

    def physical(log_volumes):
        if not _i21_np.isfinite(log_volumes).all() or _i21_np.any(abs(log_volumes) > 600):
            raise ValueError('storage transform exceeds physical range')
        volumes = _i21_np.exp(log_volumes)
        heads = _i21_np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any((head <= cell.section.floor_m for cell, head in zip(model.cells, heads))):
            raise ValueError('positive storage is below representable section depth; no floor clamp')
        capacities = _i21_np.array([capacity_for(cell, head) for cell, head in zip(model.cells, heads)])
        return (volumes, heads, capacities)

    def rhs_for(source_q):

        def rhs(seconds, current, evaluation_context='Radau_rhs_trial'):
            nonlocal peak_rss
            if rhs_observer is not None:
                rhs_observer(seconds, current, evaluation_context)
            work['rhs_evaluations'] += 1
            work['link_evaluations'] += link_count + 1
            if work['rhs_evaluations'] > experiment.max_rhs_evaluations or work['link_evaluations'] > experiment.max_link_evaluations or _i21_time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError('independent 1D work/time bound exceeded')
            if work['rhs_evaluations'] % 32 == 1:
                peak_rss = max(peak_rss, process.memory_info().rss)
                if peak_rss > 1024 ** 3:
                    raise ValueError('1GiB hydraulic RSS limit exceeded')
            volumes, heads, capacities = physical(current[:count])
            concentrations = current[count:3 * count].reshape(2, count) / volumes
            volume_rates = _i21_np.zeros(count)
            tracer_rates = _i21_np.zeros((2, count))
            derivative = _i21_np.zeros_like(current)
            for ordinal, link in enumerate(model.links):
                flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor = ordinal if flow >= 0 else ordinal + 1
                flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                tracer_flow = flow * concentrations[:, donor]
                volume_rates[ordinal] -= flow
                volume_rates[ordinal + 1] += flow
                tracer_rates[:, ordinal] -= tracer_flow
                tracer_rates[:, ordinal + 1] += tracer_flow
                derivative[ledger_start + 6 + ordinal] = flow
                derivative[ledger_start + 6 + link_count + ordinal] = tracer_flow[0]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = tracer_flow[1]
            boundary_capacity = min(capacities[-1], capacity_for(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                boundary_tracer = outlet_flow * concentrations[:, -1]
                derivative[ledger_start + 1] = outlet_flow
                derivative[ledger_start + 3] = boundary_tracer[0]
                derivative[ledger_start + 5] = boundary_tracer[1]
            else:
                boundary_tracer = _i21_np.array([0.0, outlet_flow])
                derivative[ledger_start + 2] = -outlet_flow
                derivative[ledger_start + 4] = -outlet_flow
            volume_rates[-1] -= outlet_flow
            tracer_rates[:, -1] -= boundary_tracer
            volume_rates[0] += source_q
            tracer_rates[0, 0] += source_q
            derivative[ledger_start] = source_q
            derivative[:count] = volume_rates / volumes
            derivative[count:3 * count] = tracer_rates.ravel()
            return derivative
        return rhs

    def jacobian_for(source_q):
        rhs = rhs_for(source_q)

        def jacobian(seconds, current):
            if _i21_np.shape(current) != (len(state),) or not _i21_np.isfinite(current).all():
                raise ValueError('Jacobian requires a finite complete state vector')
            work['jacobian_evaluations'] += 1
            work['jacobian_rhs_evaluations'] += 1
            base = rhs(seconds, current, 'Jacobian_baseline_rhs')
            matrix = _i21_np.zeros((len(state), len(state)))
            volumes, heads, capacities = physical(current[:count])
            for column in range(count):
                displaced = current.copy()
                head_cap = head_bounded_log_jacobian_policy(model, crown_transition_width_m)['max_head_step_m']
                cell = model.cells[column]
                area = volumes[column] / cell.length_m
                raised_area = cell.section.area_perimeter(heads[column] + 0.5 * head_cap)[0]
                permitted_step = _i21_math.log1p((raised_area - area) / area)
                log_step = min(LOG_VOLUME_DIFFERENCE_STEP, permitted_step)
                if not _i21_math.isfinite(log_step) or log_step <= 0:
                    raise ValueError('head-bounded Jacobian step is not representable')
                displaced[column] += log_step
                actual_step = displaced[column] - current[column]
                if actual_step <= 0 or not _i21_math.isfinite(actual_step):
                    raise ValueError('fixed log-volume Jacobian step is not representable')
                work['jacobian_rhs_evaluations'] += 1
                shifted = rhs(seconds, displaced, 'Jacobian_log_column_' + str(column))
                matrix[:, column] = (shifted - base) / actual_step
                work['jacobian_min_log_step'] = min(work.get('jacobian_min_log_step', actual_step), actual_step)
                work['jacobian_max_log_step'] = max(work.get('jacobian_max_log_step', actual_step), actual_step)
                trial_head = cell.section.head_for_area(_i21_math.exp(displaced[column]) / cell.length_m)
                observed_head_step = abs(trial_head - heads[column])
                work['jacobian_max_observed_head_step_m'] = max(work.get('jacobian_max_observed_head_step_m', 0.0), observed_head_step)
                if observed_head_step > head_cap + 16 * _i21_math.ulp(float(heads[column])):
                    raise ValueError('Jacobian perturbation exceeds declared physical head cap')
            volumes, heads, capacities = physical(current[:count])
            work['link_evaluations'] += link_count + 1
            if work['link_evaluations'] > experiment.max_link_evaluations or _i21_time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError('independent 1D Jacobian work/time bound exceeded')
            for ordinal, link in enumerate(model.links):
                flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor = ordinal if flow >= 0 else ordinal + 1
                flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                coefficient = flow / volumes[donor]
                for tracer in range(2):
                    mass_start = count * (tracer + 1)
                    column = mass_start + donor
                    matrix[mass_start + ordinal, column] -= coefficient
                    matrix[mass_start + ordinal + 1, column] += coefficient
                    ledger_row = ledger_start + 6 + (tracer + 1) * link_count + ordinal
                    matrix[ledger_row, column] += coefficient
            boundary_capacity = min(capacities[-1], capacity_for(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                coefficient = outlet_flow / volumes[-1]
                for tracer, ledger_offset in ((0, 3), (1, 5)):
                    column = count * (tracer + 1) + count - 1
                    matrix[column, column] -= coefficient
                    matrix[ledger_start + ledger_offset, column] += coefficient
            if not _i21_np.isfinite(matrix).all():
                raise ValueError('explicit Jacobian contains nonfinite entries')
            return matrix
        return jacobian
    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for, lambda: max(peak_rss, process.memory_info().rss))

def head_bounded_log_inventory_snapshot(model, system, state, width_m):
    volumes, heads, capacities = system.physical(state[:system.count])
    cells = []
    for ordinal, (cell, volume, head) in enumerate(zip(model.cells, volumes, heads)):
        section = cell.section
        details = friction_state(cell, float(head), width_m)
        details.update(cell_id=cell.cell_id, kind=cell.kind, head_m=float(head), volume_m3=float(volume), source_tracer_mass_m3=float(state[system.count + ordinal]), tailwater_tracer_mass_m3=float(state[2 * system.count + ordinal]))
        if cell.kind == 'underground':
            details.update(crown_m=section.crown_m, head_minus_crown_m=float(head - section.crown_m), actual_closed_capacity_m3=cell.length_m * section.area_perimeter(section.crown_m)[0], engineered_pressure_slot_volume_m3=cell.length_m * section.pressure_slot_width_m * max(0.0, head - section.crown_m))
        else:
            bank = min(section.pieces[0][1][0], sum(section.pieces[-1][1]))
            details.update(low_bank_m=bank, head_minus_low_bank_m=float(head - bank), engineering_overbank_wall_storage_m3=cell.length_m * (section.area_perimeter(head)[0] - section.area_perimeter(bank)[0]) if head > bank else 0.0)
        cells.append(details)
    return {'cells': cells, 'total_water_m3': float(volumes.sum()), 'boundary_and_paired_ledgers_m3': state[3 * system.count:].tolist()}

def head_bounded_log_flux_snapshot(model, system, seconds, state, source_q, width_m, tailwater_head_m):
    volumes, heads, capacities = system.physical(state[:system.count])
    concentrations = state[system.count:3 * system.count].reshape(2, system.count) / volumes
    links = []
    for ordinal, link in enumerate(model.links):
        flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
        donor = ordinal if flow >= 0 else ordinal + 1
        flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
        links.append({'link_id': link.link_id, 'water_q_m3_s': float(flow), 'source_tracer_q_m3_s': float(flow * concentrations[0, donor]), 'tailwater_tracer_q_m3_s': float(flow * concentrations[1, donor]), 'donor_cell_id': model.cells[donor].cell_id})
    tailwater_capacity = effective_conveyance(model.cells[-1], tailwater_head_m, width_m)
    flow = common_signed_flow(min(capacities[-1], tailwater_capacity), heads[-1] - tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
    if flow >= 0:
        flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        source_flow, tailwater_flow = flow * concentrations[:, -1]
    else:
        source_flow, tailwater_flow = (0.0, flow)
    system.work['link_evaluations'] += len(model.links) + 1
    system.work['diagnostic_flux_link_evaluations'] = system.work.get('diagnostic_flux_link_evaluations', 0) + len(model.links) + 1
    return {'time_s': float(seconds), 'source_q_m3_s': source_q, 'links': links, 'outlet_signed_water_q_m3_s': float(flow), 'outlet_signed_source_tracer_q_m3_s': float(source_flow), 'outlet_signed_tailwater_tracer_q_m3_s': float(tailwater_flow)}

def head_bounded_log_run_experiment(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    if diagnostic_stop_s is not None and (not _i21_math.isfinite(diagnostic_stop_s) or not 0 < diagnostic_stop_s <= experiment.duration_s):
        raise ValueError('diagnostic stop must be positive and within the unchanged physical event')
    last_evaluation = {'context': 'not_started', 'time_s': None}
    last_trial_state = None

    def observe_rhs(seconds, current, context):
        nonlocal last_trial_state
        last_evaluation.update(context=context, time_s=float(seconds))
        last_trial_state = current.copy()
    system = head_bounded_log_build_system(model, experiment, crown_transition_width_m, rhs_observer=observe_rhs)
    count, link_count = (system.count, len(model.links))
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes, work, started = (system.initial_volumes, system.work, system.started)
    physical = system.physical
    accepted_state, accepted_time = (state.copy(), 0.0)
    accepted_steps, min_step, max_step = (0, None, None)
    recent_steps = _i21_deque(maxlen=16)
    observations = [(0.0, state.copy())]
    integration_segments = []
    saved_times = _i21_np.asarray(experiment.saved_times_s)
    saved_ordinal = 1

    def progress():
        elapsed = _i21_time.monotonic() - started
        guard = None
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations:
            guard = 'max_rhs_evaluations'
        elif work['link_evaluations'] > experiment.max_link_evaluations:
            guard = 'max_link_evaluations'
        elif elapsed > experiment.max_wall_seconds:
            guard = 'max_wall_seconds'
        elif system.peak_rss() > 1024 ** 3:
            guard = 'max_rss_bytes'
        trial = None
        if last_trial_state is not None:
            trial = {'state_all_finite': bool(_i21_np.isfinite(last_trial_state).all()), 'state': [float(value) if _i21_math.isfinite(value) else None for value in last_trial_state], 'is_accepted_state': False, 'state_layout': 'logV/sourceMass/tailwaterMass/boundaryAndPairedLedgers'}
        try:
            accepted_inventory = head_bounded_log_inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
        except Exception as snapshot_error:
            accepted_inventory = {'snapshot_error': str(snapshot_error), 'state': [float(value) if _i21_math.isfinite(value) else None for value in accepted_state]}
        return {'last_accepted_physical_time_s': accepted_time, 'configured_physical_duration_s': experiment.duration_s, 'diagnostic_stop_s': diagnostic_stop_s, 'physical_event_complete': accepted_time == experiment.duration_s, 'work': dict(work), 'elapsed_wall_seconds': elapsed, 'triggered_guard': guard, 'max_rhs_evaluations': experiment.max_rhs_evaluations, 'max_link_evaluations': experiment.max_link_evaluations, 'max_wall_seconds': experiment.max_wall_seconds, 'accepted_steps': accepted_steps, 'min_accepted_step_s': min_step, 'max_accepted_step_s': max_step, 'recent_accepted_steps': list(recent_steps), 'last_evaluation': dict(last_evaluation), 'last_trial': trial, 'last_accepted_inventory': accepted_inventory, 'actual_peak_rss_bytes': system.peak_rss(), 'model_version': HEAD_BOUNDED_LOG_MODEL_VERSION, 'crown_friction_transition_width_m': crown_transition_width_m, 'inventory_scope': 'actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume'}
    breaks = [0.0, experiment.duration_s]
    if experiment.scenario == 'pulse':
        breaks.insert(1, experiment.pulse_duration_s)
    try:
        for lower, full_upper in zip(breaks[:-1], breaks[1:]):
            upper = min(full_upper, diagnostic_stop_s) if diagnostic_stop_s is not None else full_upper
            if upper <= lower:
                break
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
            raw_rhs, raw_jacobian = (system.rhs_for(source_q), system.jacobian_for(source_q))

            def tracked_rhs(seconds, current):
                return raw_rhs(seconds, current)

            def tracked_jacobian(seconds, current):
                return raw_jacobian(seconds, current)
            solver = _i21_Radau(tracked_rhs, lower, state, upper, max_step=experiment.max_step_s, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=tracked_jacobian)
            segment_steps = []
            while solver.status == 'running':
                message = solver.step()
                if solver.status == 'failed':
                    raise ValueError('Radau failed: ' + str(message))
                previous_time = accepted_time
                accepted_time = float(solver.t)
                accepted_state = solver.y.copy()
                step = accepted_time - previous_time
                accepted_steps += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                recent_steps.append({'start_s': previous_time, 'end_s': accepted_time, 'step_s': step})
                segment_steps.append(step)
                dense = solver.dense_output()
                while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                    seconds = float(saved_times[saved_ordinal])
                    observations.append((seconds, dense(seconds)))
                    saved_ordinal += 1
            state = accepted_state.copy()
            integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(segment_steps), 'min_adaptive_step_s': min(segment_steps), 'max_adaptive_step_s': max(segment_steps), 'nfev': solver.nfev, 'njev': solver.njev, 'nlu': solver.nlu})
            if diagnostic_stop_s is not None and accepted_time >= diagnostic_stop_s:
                raise _diagnostic_stop('declared short diagnostic stop; not a completed hydraulic case', progress())
    except Exception as error:
        if getattr(error, 'diagnostic_stop', False):
            raise
        raise _execution_failure(str(error), progress()) from error
    if accepted_time != experiment.duration_s or saved_ordinal != len(saved_times):
        raise _execution_failure('physical event/observations incomplete', progress())
    try:
        saved_section_diagnostics = [{'time_s': seconds, **head_bounded_log_inventory_snapshot(model, system, current, crown_transition_width_m)} for seconds, current in observations]
        flux_probes = []
        for seconds, current in observations:
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and seconds < experiment.pulse_duration_s else 0.0
            flux_probes.append(head_bounded_log_flux_snapshot(model, system, seconds, current, source_q, crown_transition_width_m, experiment.tailwater_head_m))
        if work['link_evaluations'] > experiment.max_link_evaluations:
            raise ValueError('independent 1D diagnostic flux work bound exceeded')
        rows = _i21_np.array([current for seconds, current in observations])
        volumes = _i21_np.exp(rows[:, :count])
        masses = rows[:, count:3 * count].reshape(-1, 2, count)
        if not _i21_np.isfinite(rows).all() or _i21_np.any(masses < 0) or _i21_np.any(masses.sum(axis=1) > volumes + experiment.absolute_tolerance * 100):
            raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
        ledgers = rows[:, ledger_start:ledger_start + 6]
        residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
        residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
        residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
        threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
        if max((_i21_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater))) > threshold:
            raise ValueError('water/tracer conservation gate failed')
        heads = _i21_np.array([physical(row[:count])[1] for row in rows])
        stages, pressure = ([], [])
        for head_row in heads:
            stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
        sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
        reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
        if _i21_time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024 ** 3:
            raise ValueError('final independent 1D wall/RSS bound exceeded')
        return {'schema': HEAD_BOUNDED_LOG_SCHEMA, 'numerical_version': HEAD_BOUNDED_LOG_NUMERICAL_VERSION, 'model_version': HEAD_BOUNDED_LOG_MODEL_VERSION, 'friction_policy': {'width_m': crown_transition_width_m, 'transition_start': 'crown', 'transition_end': 'crown+width_m', 'actual_perimeter_unchanged': True, 'storage_area_unchanged': True, 'pressure_slot_width_unchanged': True, 'roof_length_source': 'sum_actual_polygon_edges_with_both_endpoints_at_crown', 'constitutive_kind': 'C1_effective_roof_contact_friction' if crown_transition_width_m > 0 else 'legacy_actual_perimeter', 'contact_polynomial': 'u*u*(3-2*u)_for_0<=u<=1'}, 'saved_section_diagnostics': saved_section_diagnostics, 'instantaneous_flux_probes': flux_probes, 'execution_progress': progress(), 'jacobian_policy': {**head_bounded_log_jacobian_policy(model, crown_transition_width_m), 'observed_max_head_step_m': work.get('jacobian_max_observed_head_step_m', 0.0)}, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_Radau', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:].tolist(), 'max_water_residual_m3': float(_i21_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i21_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i21_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': system.peak_rss(), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i21_time.monotonic() - started}}
    except Exception as error:
        raise _execution_failure(str(error), progress()) from error
DIRECT_INVENTORY_SCHEMA = 'td-hybrid-river-hydraulics-v5'
DIRECT_INVENTORY_NUMERICAL_VERSION = 'three_origin_direct_inventory_Radau_positivity_rejection-v5'

def direct_inventory_jacobian_policy(model, width_m):
    cap = min(JACOBIAN_MAX_HEAD_STEP_M, model.head_regularization_m * JACOBIAN_HEAD_FRACTION)
    if width_m > 0:
        cap = min(cap, width_m * JACOBIAN_HEAD_FRACTION)
    return {'total_inventory_nominal_relative_step': DIRECT_VOLUME_RELATIVE_STEP, 'max_head_step_m': cap, 'nominal_head_ceiling_m': JACOBIAN_MAX_HEAD_STEP_M, 'head_cap_rule': 'min(nominal_head_ceiling_m,head_regularization_m*0.01,width_m*0.01_if_positive)', 'head_step_target_fraction_of_cap': 0.5, 'head_step_fraction_of_friction_transition': JACOBIAN_HEAD_FRACTION, 'head_step_float_margin': '16_ulp_of_base_head', 'step_units': 'm3_total_inventory_constant_composition_forward_difference_bounded_by_head', 'tracer_columns': 'all_three_origin_columns_share_total_inventory_feedback_plus_analytic_composition', 'ledger_feedback_columns': 'exact_zero', 'nonsmooth_scope': 'fixed_forward_secant_at_exact_storage_slot_derivative_and_donor_min_ledges;C1_roof_contact_only_not_whole_RHS', 'scipy_adaptive_difference_factor_used': False}

def direct_inventory_build_system(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, rhs_observer=None):
    validate_transition(crown_transition_width_m)
    model.validate()
    experiment.validate(model)
    count, link_count = (len(model.cells), len(model.links))
    initial_volumes = _i22_np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if _i22_np.any(initial_volumes <= 0):
        raise ValueError('initial storage must be strictly positive')
    ledger_start = 3 * count
    state = _i22_np.zeros(ledger_start + 7 + 4 * link_count)
    state[:count] = initial_volumes
    work = {'rhs_evaluations': 0, 'link_evaluations': 0, 'old_hll_face_work': 0, 'jacobian_evaluations': 0, 'jacobian_rhs_evaluations': 0, 'positivity_rejected_steps': 0, 'nonpositive_total_trial_retries': 0, 'solver_reinitializations': 0, 'constructor_nonpositive_retries': 0, 'accepted_endpoint_inventory_checks': 0, 'observation_segment_initializations': 0, 'radau_constructor_attempts': 0}
    started = _i22_time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    roof_lengths = [roof_contact_length(cell.section) for cell in model.cells]

    def capacity_for(ordinal, head):
        return friction_state(model.cells[ordinal], head, crown_transition_width_m, roof_lengths[ordinal])['effective_manning_conveyance']

    def physical(inventories):
        if _i22_np.shape(inventories) != (3 * count,) or not _i22_np.isfinite(inventories).all():
            raise _nonpositive_water_trial('physical inventory requires finite three-origin state')
        volumes = inventories.reshape(3, count).sum(axis=0)
        if _i22_np.any(volumes <= 0):
            raise _nonpositive_water_trial('trial total water is nonpositive; no floor clamp')
        heads = _i22_np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any((head <= cell.section.floor_m for cell, head in zip(model.cells, heads))):
            raise _nonpositive_water_trial('trial positive inventory below representable depth; no floor clamp')
        capacities = _i22_np.array([capacity_for(ordinal, head) for ordinal, head in enumerate(heads)])
        return (volumes, heads, capacities)

    def guard():
        nonlocal peak_rss
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations or work['link_evaluations'] > experiment.max_link_evaluations or _i22_time.monotonic() - started > experiment.max_wall_seconds:
            raise ValueError('independent 1D work/time bound exceeded')
        peak_rss = max(peak_rss, process.memory_info().rss)
        if peak_rss > 1024 ** 3:
            raise ValueError('1GiB hydraulic RSS limit exceeded')

    def flows(current):
        volumes, heads, capacities = physical(current[:3 * count])
        amounts = []
        for ordinal, link in enumerate(model.links):
            flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
            donor = ordinal if flow >= 0 else ordinal + 1
            flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
            amounts.append((float(flow), donor))
        boundary_capacity = min(capacities[-1], capacity_for(count - 1, experiment.tailwater_head_m))
        outlet = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
        if outlet >= 0:
            outlet *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        return (volumes, heads, amounts, float(outlet))

    def concentration_matrix(amounts, outlet):
        matrix = _i22_np.zeros((len(state), 3 * count))
        for ordinal, (flow, donor) in enumerate(amounts):
            for origin in range(3):
                column = origin * count + donor
                matrix[origin * count + ordinal, column] -= flow
                matrix[origin * count + ordinal + 1, column] += flow
                row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                matrix[row, column] += flow
        if outlet >= 0:
            for origin in range(3):
                column = origin * count + count - 1
                matrix[column, column] -= outlet
                row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                matrix[row, column] += outlet
        return matrix

    def rhs_for(source_q):

        def rhs(seconds, current, evaluation_context='Radau_rhs_trial'):
            if rhs_observer is not None:
                rhs_observer(seconds, current, evaluation_context)
            work['rhs_evaluations'] += 1
            work['link_evaluations'] += link_count + 1
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivative = _i22_np.zeros_like(current)
            rates = derivative[:3 * count].reshape(3, count)
            for ordinal, (flow, donor) in enumerate(amounts):
                transport = flow * concentrations[:, donor]
                rates[:, ordinal] -= transport
                rates[:, ordinal + 1] += transport
                derivative[ledger_start + 6 + link_count + ordinal] = transport[1]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = transport[2]
                derivative[ledger_start + 6 + 3 * link_count + ordinal] = transport[0]
            derivative[count] += source_q
            derivative[ledger_start] = source_q
            for ordinal, (flow, donor) in enumerate(amounts):
                derivative[ledger_start + 6 + ordinal] = flow
            if outlet >= 0:
                transport = outlet * concentrations[:, -1]
                rates[:, -1] -= transport
                derivative[ledger_start + 1] = outlet
                derivative[ledger_start + 3] = transport[1]
                derivative[ledger_start + 5] = transport[2]
                derivative[ledger_start + 6 + 4 * link_count] = transport[0]
            else:
                derivative[3 * count - 1] -= outlet
                derivative[ledger_start + 2] = -outlet
                derivative[ledger_start + 4] = -outlet
            return derivative
        return rhs

    def jacobian_for(source_q):
        rhs = rhs_for(source_q)

        def jacobian(seconds, current):
            if _i22_np.shape(current) != (len(state),) or not _i22_np.isfinite(current).all():
                raise ValueError('Jacobian requires finite complete three-origin state')
            work['jacobian_evaluations'] += 1
            work['jacobian_rhs_evaluations'] += 1
            base = rhs(seconds, current, 'Jacobian_baseline_rhs')
            work['link_evaluations'] += link_count + 1
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            concentration_derivative = concentration_matrix(amounts, outlet)
            matrix = _i22_np.zeros((len(state), len(state)))
            cap = direct_inventory_jacobian_policy(model, crown_transition_width_m)['max_head_step_m']
            for ordinal, cell in enumerate(model.cells):
                target_volume = cell.length_m * cell.section.area_perimeter(heads[ordinal] + 0.5 * cap)[0]
                step = min(volumes[ordinal] * DIRECT_VOLUME_RELATIVE_STEP, target_volume - volumes[ordinal])
                if not _i22_math.isfinite(step) or step <= 0:
                    raise ValueError('head-bounded total-inventory Jacobian step unrepresentable')
                displaced = current.copy()
                for origin in range(3):
                    displaced[origin * count + ordinal] += step * concentrations[origin, ordinal]
                actual_step = displaced[:3 * count].reshape(3, count)[:, ordinal].sum() - volumes[ordinal]
                if not _i22_math.isfinite(actual_step) or actual_step <= 0:
                    raise ValueError('total-inventory Jacobian perturbation unrepresentable')
                work['jacobian_rhs_evaluations'] += 1
                shifted = rhs(seconds, displaced, 'Jacobian_total_inventory_column_' + str(ordinal))
                volume_derivative = (shifted - base) / actual_step
                common = volume_derivative.copy()
                for origin in range(3):
                    column = origin * count + ordinal
                    common -= concentration_derivative[:, column] * concentrations[origin, ordinal] / volumes[ordinal]
                for origin in range(3):
                    column = origin * count + ordinal
                    matrix[:, column] = common + concentration_derivative[:, column] / volumes[ordinal]
                trial_head = cell.section.head_for_area((volumes[ordinal] + actual_step) / cell.length_m)
                observed = abs(trial_head - heads[ordinal])
                work['jacobian_max_observed_head_step_m'] = max(work.get('jacobian_max_observed_head_step_m', 0.0), observed)
                work['jacobian_min_volume_step_m3'] = min(work.get('jacobian_min_volume_step_m3', actual_step), actual_step)
                work['jacobian_max_volume_step_m3'] = max(work.get('jacobian_max_volume_step_m3', actual_step), actual_step)
                if observed > cap + 16 * _i22_math.ulp(float(heads[ordinal])):
                    raise ValueError('Jacobian perturbation exceeds physical head cap')
            if not _i22_np.isfinite(matrix).all():
                raise ValueError('explicit three-origin Jacobian nonfinite')
            return matrix
        return jacobian
    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for, lambda: max(peak_rss, process.memory_info().rss))

def direct_inventory_run_experiment(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    if diagnostic_stop_s is not None and (not _i22_math.isfinite(diagnostic_stop_s) or not 0 < diagnostic_stop_s <= experiment.duration_s):
        raise ValueError('diagnostic stop must be positive and within the unchanged physical event')
    last_evaluation = {'context': 'not_started', 'time_s': None}
    last_trial_state = None

    def observe_rhs(seconds, current, context):
        nonlocal last_trial_state
        last_evaluation.update(context=context, time_s=float(seconds))
        last_trial_state = current.copy()
    system = direct_inventory_build_system(model, experiment, crown_transition_width_m, rhs_observer=observe_rhs)
    count, link_count = (system.count, len(model.links))
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes, work, started = (system.initial_volumes, system.work, system.started)
    physical = system.physical
    accepted_state, accepted_time = (state.copy(), 0.0)
    accepted_steps, min_step, max_step = (0, None, None)
    last_positivity_rejection = None
    saved_mass_extrema = None
    recent_steps = _i22_deque(maxlen=16)
    observations = [(0.0, state.copy())]
    integration_segments = []
    rejected_solver_statistics = {'nfev': 0, 'njev': 0, 'nlu': 0}
    saved_times = _i22_np.asarray(experiment.saved_times_s)
    saved_ordinal = 1

    def progress():
        observed_origins = _i22_np.array([current[:3 * count].reshape(3, count) for seconds, current in observations])
        observed_index = _i22_np.unravel_index(_i22_np.argmin(observed_origins), observed_origins.shape)
        observed_extrema = {'minimum_origin_inventory_m3': float(observed_origins[observed_index]), 'time_s': float(observations[observed_index[0]][0]), 'origin': ('untraced', 'source', 'tailwater')[observed_index[1]], 'cell_id': model.cells[observed_index[2]].cell_id, 'per_origin_minimum_m3': observed_origins.min(axis=(0, 2)).tolist()}
        elapsed = _i22_time.monotonic() - started
        guard = None
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations:
            guard = 'max_rhs_evaluations'
        elif work['link_evaluations'] > experiment.max_link_evaluations:
            guard = 'max_link_evaluations'
        elif elapsed > experiment.max_wall_seconds:
            guard = 'max_wall_seconds'
        elif system.peak_rss() > 1024 ** 3:
            guard = 'max_rss_bytes'
        trial = None
        if last_trial_state is not None:
            trial = {'state_all_finite': bool(_i22_np.isfinite(last_trial_state).all()), 'state': [float(value) if _i22_math.isfinite(value) else None for value in last_trial_state], 'is_accepted_state': False, 'state_layout': 'untracedMass/sourceMass/tailwaterMass/oldSixBoundary/threePaired/untracedPaired/untracedOutlet'}
        try:
            accepted_inventory = inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
        except Exception as snapshot_error:
            accepted_inventory = {'snapshot_error': str(snapshot_error), 'state': [float(value) if _i22_math.isfinite(value) else None for value in accepted_state]}
        return {'last_accepted_physical_time_s': accepted_time, 'configured_physical_duration_s': experiment.duration_s, 'diagnostic_stop_s': diagnostic_stop_s, 'physical_event_complete': accepted_time == experiment.duration_s, 'work': dict(work), 'last_positivity_rejection': last_positivity_rejection, 'saved_mass_extrema': saved_mass_extrema if saved_mass_extrema is not None else observed_extrema, 'elapsed_wall_seconds': elapsed, 'triggered_guard': guard, 'discarded_solver_statistics': dict(rejected_solver_statistics), 'max_rhs_evaluations': experiment.max_rhs_evaluations, 'max_link_evaluations': experiment.max_link_evaluations, 'max_wall_seconds': experiment.max_wall_seconds, 'accepted_steps': accepted_steps, 'min_accepted_step_s': min_step, 'max_accepted_step_s': max_step, 'recent_accepted_steps': list(recent_steps), 'last_evaluation': dict(last_evaluation), 'last_trial': trial, 'last_accepted_inventory': accepted_inventory, 'actual_peak_rss_bytes': system.peak_rss(), 'model_version': MODEL_VERSION, 'crown_friction_transition_width_m': crown_transition_width_m, 'inventory_scope': 'actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume'}
    breaks = [0.0, experiment.duration_s, *experiment.saved_times_s]
    if experiment.scenario == 'pulse':
        breaks.append(experiment.pulse_duration_s)
    breaks = sorted(set(breaks))
    try:
        for lower, full_upper in zip(breaks[:-1], breaks[1:]):
            upper = min(full_upper, diagnostic_stop_s) if diagnostic_stop_s is not None else full_upper
            if upper <= lower:
                break
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
            raw_rhs, raw_jacobian = (system.rhs_for(source_q), system.jacobian_for(source_q))

            def tracked_rhs(seconds, current):
                return raw_rhs(seconds, current)

            def tracked_jacobian(seconds, current):
                return raw_jacobian(seconds, current)

            def construct_solver(seconds, current, maximum_step, first_step=None):
                nonlocal last_positivity_rejection
                while True:
                    try:
                        work['radau_constructor_attempts'] += 1
                        return _i22_Radau(tracked_rhs, seconds, current, upper, max_step=maximum_step, first_step=first_step, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=tracked_jacobian)
                    except ValueError as error:
                        if not getattr(error, 'nonpositive_water_trial', False):
                            raise
                        work['constructor_nonpositive_retries'] += 1
                        work['nonpositive_total_trial_retries'] += 1
                        last_positivity_rejection = {'time_s': seconds, 'trial_error': str(error), 'context': 'Radau_constructor', 'accepted_state_unchanged': True}
                        bound = min(maximum_step, upper - seconds)
                        if first_step is not None:
                            bound = min(bound, first_step)
                        first_step = bound / 2
                        maximum_step = min(maximum_step, first_step)
                        if first_step <= 16 * _i22_math.ulp(seconds) or first_step <= 0:
                            raise ValueError('constructor positivity retry step unrepresentable; no clamp')
                        work['solver_reinitializations'] += 1
            work['observation_segment_initializations'] += 1
            solver = construct_solver(lower, state, experiment.max_step_s)
            segment_steps = []
            while solver.status == 'running':
                previous_state = accepted_state.copy()
                attempted_step = min(solver.h_abs, upper - accepted_time)
                trial_error = None
                try:
                    message = solver.step()
                except ValueError as error:
                    if not getattr(error, 'nonpositive_water_trial', False):
                        raise
                    trial_error = str(error)
                if trial_error is None and solver.status != 'failed':
                    work['accepted_endpoint_inventory_checks'] += 1
                    violation = positivity_violation(solver.y, count, solver.t)
                    actual_candidate_step = solver.t - accepted_time
                else:
                    violation = {'time_s': accepted_time, 'trial_error': trial_error} if trial_error else None
                    actual_candidate_step = attempted_step
                if violation is not None:
                    last_positivity_rejection = violation
                    if 'cell_ordinal' in violation:
                        last_positivity_rejection['cell_id'] = model.cells[violation['cell_ordinal']].cell_id
                    work['positivity_rejected_steps'] += 1
                    if trial_error:
                        work['nonpositive_total_trial_retries'] += 1
                    retry_step = min(attempted_step, actual_candidate_step) / 2
                    if retry_step <= 16 * _i22_math.ulp(accepted_time) or retry_step <= 0:
                        raise ValueError('strict positivity retry step unrepresentable; no clamp')
                    work['solver_reinitializations'] += 1
                    for name in rejected_solver_statistics:
                        rejected_solver_statistics[name] += getattr(solver, name)
                    solver = construct_solver(accepted_time, previous_state, min(experiment.max_step_s, retry_step), first_step=retry_step)
                    continue
                if solver.status == 'failed':
                    raise ValueError('Radau failed: ' + str(message))
                previous_time = accepted_time
                accepted_time = float(solver.t)
                accepted_state = solver.y.copy()
                solver.max_step = experiment.max_step_s
                step = accepted_time - previous_time
                accepted_steps += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                recent_steps.append({'start_s': previous_time, 'end_s': accepted_time, 'step_s': step})
                segment_steps.append(step)
                while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                    seconds = float(saved_times[saved_ordinal])
                    if seconds != accepted_time:
                        raise ValueError('saved physical observation must coincide with accepted Radau endpoint')
                    saved_state = accepted_state.copy()
                    violation = positivity_violation(saved_state, count, seconds)
                    if violation:
                        raise ValueError('saved inventory positivity violation: ' + str(violation))
                    observations.append((seconds, saved_state))
                    saved_ordinal += 1
            state = accepted_state.copy()
            integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(segment_steps), 'min_adaptive_step_s': min(segment_steps), 'max_adaptive_step_s': max(segment_steps), 'final_solver_nfev': solver.nfev, 'final_solver_njev': solver.njev, 'final_solver_nlu': solver.nlu, 'discarded_solver_statistics_cumulative': dict(rejected_solver_statistics)})
            if diagnostic_stop_s is not None and accepted_time >= diagnostic_stop_s:
                raise _diagnostic_stop('declared short diagnostic stop; not a completed hydraulic case', progress())
    except Exception as error:
        if getattr(error, 'diagnostic_stop', False):
            raise
        raise _execution_failure(str(error), progress()) from error
    if accepted_time != experiment.duration_s or saved_ordinal != len(saved_times):
        raise _execution_failure('physical event/observations incomplete', progress())
    try:
        saved_section_diagnostics = [{'time_s': seconds, **inventory_snapshot(model, system, current, crown_transition_width_m)} for seconds, current in observations]
        flux_probes = []
        for seconds, current in observations:
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and seconds < experiment.pulse_duration_s else 0.0
            flux_probes.append(flux_snapshot(model, system, seconds, current, source_q, crown_transition_width_m, experiment.tailwater_head_m))
        if work['link_evaluations'] > experiment.max_link_evaluations:
            raise ValueError('independent 1D diagnostic flux work bound exceeded')
        rows = _i22_np.array([current for seconds, current in observations])
        all_origins = rows[:, :3 * count].reshape(-1, 3, count)
        volumes = all_origins.sum(axis=1)
        masses = rows[:, count:3 * count].reshape(-1, 2, count)
        minimum_index = _i22_np.unravel_index(_i22_np.argmin(all_origins), all_origins.shape)
        saved_mass_extrema = {'minimum_origin_inventory_m3': float(all_origins[minimum_index]), 'time_s': float(saved_times[minimum_index[0]]), 'origin': ('untraced', 'source', 'tailwater')[minimum_index[1]], 'cell_id': model.cells[minimum_index[2]].cell_id, 'per_origin_minimum_m3': all_origins.min(axis=(0, 2)).tolist(), 'max_water_minus_origin_sum_m3': float(_i22_np.max(abs(volumes - all_origins.sum(axis=1))))}
        if not _i22_np.isfinite(rows).all() or _i22_np.any(all_origins < 0) or _i22_np.any(volumes <= 0):
            raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
        ledgers = rows[:, ledger_start:ledger_start + 6]
        residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
        residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
        residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
        untraced_out = rows[:, ledger_start + 6 + 4 * link_count]
        residual_untraced = all_origins[:, 0].sum(axis=1) - initial_volumes.sum() + untraced_out
        threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
        if max((_i22_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater, residual_untraced))) > threshold:
            raise ValueError('water/tracer conservation gate failed')
        heads = _i22_np.array([physical(row[:3 * count])[1] for row in rows])
        stages, pressure = ([], [])
        for head_row in heads:
            stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
        sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
        reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
        if _i22_time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024 ** 3:
            raise ValueError('final independent 1D wall/RSS bound exceeded')
        return {'schema': DIRECT_INVENTORY_SCHEMA, 'numerical_version': DIRECT_INVENTORY_NUMERICAL_VERSION, 'model_version': MODEL_VERSION, 'friction_policy': {'width_m': crown_transition_width_m, 'transition_start': 'crown', 'transition_end': 'crown+width_m', 'actual_perimeter_unchanged': True, 'storage_area_unchanged': True, 'pressure_slot_width_unchanged': True, 'roof_length_source': 'sum_actual_polygon_edges_with_both_endpoints_at_crown', 'constitutive_kind': 'C1_effective_roof_contact_friction' if crown_transition_width_m > 0 else 'legacy_actual_perimeter', 'contact_polynomial': 'u*u*(3-2*u)_for_0<=u<=1'}, 'saved_section_diagnostics': saved_section_diagnostics, 'instantaneous_flux_probes': flux_probes, 'execution_progress': progress(), 'jacobian_policy': {**direct_inventory_jacobian_policy(model, crown_transition_width_m), 'observed_max_head_step_m': work.get('jacobian_max_observed_head_step_m', 0.0)}, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_Radau', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'untraced_water_volume_m3': all_origins[:, 0].tolist(), 'inventory_policy': inventory_policy(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:ledger_start + 6 + 3 * link_count].tolist(), 'paired_link_untraced_integral_m3': rows[:, ledger_start + 6 + 3 * link_count:ledger_start + 6 + 4 * link_count].tolist(), 'outlet_untraced_out_m3': untraced_out.tolist(), 'max_untraced_residual_m3': float(_i22_np.max(abs(residual_untraced))), 'saved_mass_extrema': saved_mass_extrema, 'dense_positivity_witness': {'policy': 'no_dense_inventory_output_saved_times_are_Radau_endpoints', 'interpolated_inventory_samples': 0, 'continuous_between_steps_positivity_certified': False, 'candidate_endpoint_checks': work['accepted_endpoint_inventory_checks'], 'accepted_steps': accepted_steps, 'last_rejected': last_positivity_rejection, 'negative_inventory_tolerance_m3': 0.0}, 'max_water_residual_m3': float(_i22_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i22_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i22_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': system.peak_rss(), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i22_time.monotonic() - started}}
    except Exception as error:
        raise _execution_failure(str(error), progress()) from error

def analytic_radau_build_system(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, rhs_observer=None):
    validate_transition(crown_transition_width_m)
    model.validate()
    experiment.validate(model)
    count, link_count = (len(model.cells), len(model.links))
    initial_volumes = _i23_np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if _i23_np.any(initial_volumes <= 0):
        raise ValueError('initial storage must be strictly positive')
    ledger_start = 3 * count
    state = _i23_np.zeros(ledger_start + 7 + 4 * link_count)
    state[:count] = initial_volumes
    work = {'rhs_evaluations': 0, 'link_evaluations': 0, 'old_hll_face_work': 0, 'jacobian_evaluations': 0, 'jacobian_rhs_evaluations': 0, 'jacobian_link_evaluations': 0, 'jacobian_native_section_derivatives': 0, 'jacobian_flow_evaluations': 0, 'jacobian_link_derivative_evaluations': 0, 'jacobian_section_fallback_evaluations': 0, 'positivity_rejected_steps': 0, 'nonpositive_total_trial_retries': 0, 'solver_reinitializations': 0, 'constructor_nonpositive_retries': 0, 'accepted_endpoint_inventory_checks': 0, 'observation_segment_initializations': 0, 'radau_constructor_attempts': 0}
    started = _i23_time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    roof_lengths = [roof_contact_length(cell.section) for cell in model.cells]

    def capacity_for(ordinal, head):
        return friction_state(model.cells[ordinal], head, crown_transition_width_m, roof_lengths[ordinal])['effective_manning_conveyance']

    def physical(inventories):
        if _i23_np.shape(inventories) != (3 * count,) or not _i23_np.isfinite(inventories).all():
            raise _nonpositive_water_trial('physical inventory requires finite three-origin state')
        volumes = inventories.reshape(3, count).sum(axis=0)
        if _i23_np.any(volumes <= 0):
            raise _nonpositive_water_trial('trial total water is nonpositive; no floor clamp')
        heads = _i23_np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any((head <= cell.section.floor_m for cell, head in zip(model.cells, heads))):
            raise _nonpositive_water_trial('trial positive inventory below representable depth; no floor clamp')
        capacities = _i23_np.array([capacity_for(ordinal, head) for ordinal, head in enumerate(heads)])
        return (volumes, heads, capacities)

    def guard():
        nonlocal peak_rss
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations or work['link_evaluations'] > experiment.max_link_evaluations or _i23_time.monotonic() - started > experiment.max_wall_seconds:
            raise ValueError('independent 1D work/time bound exceeded')
        peak_rss = max(peak_rss, process.memory_info().rss)
        if peak_rss > 1024 ** 3:
            raise ValueError('1GiB hydraulic RSS limit exceeded')

    def flows(current):
        volumes, heads, capacities = physical(current[:3 * count])
        amounts = []
        for ordinal, link in enumerate(model.links):
            flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
            donor = ordinal if flow >= 0 else ordinal + 1
            flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
            amounts.append((float(flow), donor))
        boundary_capacity = min(capacities[-1], capacity_for(count - 1, experiment.tailwater_head_m))
        outlet = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
        if outlet >= 0:
            outlet *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        return (volumes, heads, amounts, float(outlet))

    def concentration_matrix(amounts, outlet):
        matrix = _i23_np.zeros((len(state), 3 * count))
        for ordinal, (flow, donor) in enumerate(amounts):
            for origin in range(3):
                column = origin * count + donor
                matrix[origin * count + ordinal, column] -= flow
                matrix[origin * count + ordinal + 1, column] += flow
                row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                matrix[row, column] += flow
        if outlet >= 0:
            for origin in range(3):
                column = origin * count + count - 1
                matrix[column, column] -= outlet
                row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                matrix[row, column] += outlet
        return matrix

    def rhs_for(source_q):

        def rhs(seconds, current, evaluation_context='Radau_rhs_trial'):
            if rhs_observer is not None:
                rhs_observer(seconds, current, evaluation_context)
            work['rhs_evaluations'] += 1
            work['link_evaluations'] += link_count + 1
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivative = _i23_np.zeros_like(current)
            rates = derivative[:3 * count].reshape(3, count)
            for ordinal, (flow, donor) in enumerate(amounts):
                transport = flow * concentrations[:, donor]
                rates[:, ordinal] -= transport
                rates[:, ordinal + 1] += transport
                derivative[ledger_start + 6 + link_count + ordinal] = transport[1]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = transport[2]
                derivative[ledger_start + 6 + 3 * link_count + ordinal] = transport[0]
            derivative[count] += source_q
            derivative[ledger_start] = source_q
            for ordinal, (flow, donor) in enumerate(amounts):
                derivative[ledger_start + 6 + ordinal] = flow
            if outlet >= 0:
                transport = outlet * concentrations[:, -1]
                rates[:, -1] -= transport
                derivative[ledger_start + 1] = outlet
                derivative[ledger_start + 3] = transport[1]
                derivative[ledger_start + 5] = transport[2]
                derivative[ledger_start + 6 + 4 * link_count] = transport[0]
            else:
                derivative[3 * count - 1] -= outlet
                derivative[ledger_start + 2] = -outlet
                derivative[ledger_start + 4] = -outlet
            return derivative
        return rhs

    def jacobian_for(source_q):

        def jacobian(seconds, current):
            if _i23_np.shape(current) != (len(state),) or not _i23_np.isfinite(current).all():
                raise ValueError('Jacobian requires finite complete three-origin state')
            if rhs_observer is not None:
                rhs_observer(seconds, current, 'Jacobian_analytic_state')
            work['jacobian_evaluations'] += 1
            work['jacobian_link_evaluations'] += 2 * (link_count + 1)
            work['jacobian_flow_evaluations'] += link_count + 1
            work['jacobian_link_derivative_evaluations'] += link_count + 1
            work['link_evaluations'] += 2 * (link_count + 1)
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivatives = [section_slopes(cell, heads[ordinal], crown_transition_width_m, roof_lengths[ordinal], work) for ordinal, cell in enumerate(model.cells)]
            matrix = _i23_np.zeros((len(state), len(state)))
            for ordinal, (flow, donor) in enumerate(amounts):
                link = model.links[ordinal]
                left_capacity, left_head_slope, left_capacity_slope = derivatives[ordinal]
                right_capacity, right_head_slope, right_capacity_slope = derivatives[ordinal + 1]
                limiting_left = left_capacity <= right_capacity
                minimum_capacity = min(left_capacity, right_capacity)
                factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor_factor = volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[donor] + model.donor_regularization_m3) ** 2
                left_flow_slope = donor_factor * (difference_derivative * left_head_slope + factor * left_capacity_slope * limiting_left)
                right_flow_slope = donor_factor * (-difference_derivative * right_head_slope + factor * right_capacity_slope * (not limiting_left))
                if donor == ordinal:
                    left_flow_slope += minimum_capacity * factor * donor_derivative
                else:
                    right_flow_slope += minimum_capacity * factor * donor_derivative
                for cell_ordinal, flow_slope in ((ordinal, left_flow_slope), (ordinal + 1, right_flow_slope)):
                    for origin_column in range(3):
                        column = origin_column * count + cell_ordinal
                        matrix[ledger_start + 6 + ordinal, column] += flow_slope
                        for origin in range(3):
                            transport_slope = concentrations[origin, donor] * flow_slope
                            if cell_ordinal == donor:
                                transport_slope += flow * ((origin == origin_column) - concentrations[origin, donor]) / volumes[donor]
                            matrix[origin * count + ordinal, column] -= transport_slope
                            matrix[origin * count + ordinal + 1, column] += transport_slope
                            row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                            matrix[row, column] += transport_slope
            capacity, head_slope, capacity_slope = derivatives[-1]
            tailwater_capacity = capacity_for(count - 1, experiment.tailwater_head_m)
            limiting_cell = capacity <= tailwater_capacity
            minimum_capacity = min(capacity, tailwater_capacity)
            factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            flow_slope = difference_derivative * head_slope + factor * capacity_slope * limiting_cell
            if outlet >= 0:
                donor_factor = volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[-1] + model.donor_regularization_m3) ** 2
                flow_slope = flow_slope * donor_factor + minimum_capacity * factor * donor_derivative
            for origin_column in range(3):
                column = origin_column * count + count - 1
                if outlet >= 0:
                    matrix[ledger_start + 1, column] += flow_slope
                    for origin in range(3):
                        transport_slope = concentrations[origin, -1] * flow_slope + outlet * ((origin == origin_column) - concentrations[origin, -1]) / volumes[-1]
                        matrix[origin * count + count - 1, column] -= transport_slope
                        row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                        matrix[row, column] += transport_slope
                else:
                    matrix[3 * count - 1, column] -= flow_slope
                    matrix[ledger_start + 2, column] -= flow_slope
                    matrix[ledger_start + 4, column] -= flow_slope
            if not _i23_np.isfinite(matrix).all():
                raise ValueError('analytic three-origin Jacobian nonfinite')
            return matrix
        return jacobian
    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for, lambda: max(peak_rss, process.memory_info().rss))

def analytic_radau_run_experiment(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    if diagnostic_stop_s is not None and (not _i23_math.isfinite(diagnostic_stop_s) or not 0 < diagnostic_stop_s <= experiment.duration_s):
        raise ValueError('diagnostic stop must be positive and within the unchanged physical event')
    last_evaluation = {'context': 'not_started', 'time_s': None}
    last_trial_state = None

    def observe_rhs(seconds, current, context):
        nonlocal last_trial_state
        last_evaluation.update(context=context, time_s=float(seconds))
        last_trial_state = current.copy()
    system = analytic_radau_build_system(model, experiment, crown_transition_width_m, rhs_observer=observe_rhs)
    count, link_count = (system.count, len(model.links))
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes, work, started = (system.initial_volumes, system.work, system.started)
    physical = system.physical
    accepted_state, accepted_time = (state.copy(), 0.0)
    accepted_steps, min_step, max_step = (0, None, None)
    last_positivity_rejection = None
    saved_mass_extrema = None
    recent_steps = _i23_deque(maxlen=16)
    observations = [(0.0, state.copy())]
    integration_segments = []
    rejected_solver_statistics = {'nfev': 0, 'njev': 0, 'nlu': 0}
    saved_times = _i23_np.asarray(experiment.saved_times_s)
    saved_ordinal = 1

    def progress():
        observed_origins = _i23_np.array([current[:3 * count].reshape(3, count) for seconds, current in observations])
        observed_index = _i23_np.unravel_index(_i23_np.argmin(observed_origins), observed_origins.shape)
        observed_extrema = {'minimum_origin_inventory_m3': float(observed_origins[observed_index]), 'time_s': float(observations[observed_index[0]][0]), 'origin': ('untraced', 'source', 'tailwater')[observed_index[1]], 'cell_id': model.cells[observed_index[2]].cell_id, 'per_origin_minimum_m3': observed_origins.min(axis=(0, 2)).tolist()}
        elapsed = _i23_time.monotonic() - started
        guard = None
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations:
            guard = 'max_rhs_evaluations'
        elif work['link_evaluations'] > experiment.max_link_evaluations:
            guard = 'max_link_evaluations'
        elif elapsed > experiment.max_wall_seconds:
            guard = 'max_wall_seconds'
        elif system.peak_rss() > 1024 ** 3:
            guard = 'max_rss_bytes'
        trial = None
        if last_trial_state is not None:
            trial = {'state_all_finite': bool(_i23_np.isfinite(last_trial_state).all()), 'state': [float(value) if _i23_math.isfinite(value) else None for value in last_trial_state], 'is_accepted_state': False, 'state_layout': 'untracedMass/sourceMass/tailwaterMass/oldSixBoundary/threePaired/untracedPaired/untracedOutlet'}
        try:
            accepted_inventory = inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
        except Exception as snapshot_error:
            accepted_inventory = {'snapshot_error': str(snapshot_error), 'state': [float(value) if _i23_math.isfinite(value) else None for value in accepted_state]}
        return {'last_accepted_physical_time_s': accepted_time, 'configured_physical_duration_s': experiment.duration_s, 'diagnostic_stop_s': diagnostic_stop_s, 'physical_event_complete': accepted_time == experiment.duration_s, 'work': dict(work), 'last_positivity_rejection': last_positivity_rejection, 'saved_mass_extrema': saved_mass_extrema if saved_mass_extrema is not None else observed_extrema, 'elapsed_wall_seconds': elapsed, 'triggered_guard': guard, 'discarded_solver_statistics': dict(rejected_solver_statistics), 'max_rhs_evaluations': experiment.max_rhs_evaluations, 'max_link_evaluations': experiment.max_link_evaluations, 'max_wall_seconds': experiment.max_wall_seconds, 'accepted_steps': accepted_steps, 'min_accepted_step_s': min_step, 'max_accepted_step_s': max_step, 'recent_accepted_steps': list(recent_steps), 'last_evaluation': dict(last_evaluation), 'last_trial': trial, 'last_accepted_inventory': accepted_inventory, 'actual_peak_rss_bytes': system.peak_rss(), 'model_version': MODEL_VERSION, 'crown_friction_transition_width_m': crown_transition_width_m, 'inventory_scope': 'actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume'}
    breaks = [0.0, experiment.duration_s, *experiment.saved_times_s]
    if experiment.scenario == 'pulse':
        breaks.append(experiment.pulse_duration_s)
    breaks = sorted(set(breaks))
    try:
        for lower, full_upper in zip(breaks[:-1], breaks[1:]):
            upper = min(full_upper, diagnostic_stop_s) if diagnostic_stop_s is not None else full_upper
            if upper <= lower:
                break
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
            raw_rhs, raw_jacobian = (system.rhs_for(source_q), system.jacobian_for(source_q))

            def tracked_rhs(seconds, current):
                return raw_rhs(seconds, current)

            def tracked_jacobian(seconds, current):
                return raw_jacobian(seconds, current)

            def construct_solver(seconds, current, maximum_step, first_step=None):
                nonlocal last_positivity_rejection
                while True:
                    try:
                        work['radau_constructor_attempts'] += 1
                        return _i23_Radau(tracked_rhs, seconds, current, upper, max_step=maximum_step, first_step=first_step, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=tracked_jacobian)
                    except ValueError as error:
                        if not getattr(error, 'nonpositive_water_trial', False):
                            raise
                        work['constructor_nonpositive_retries'] += 1
                        work['nonpositive_total_trial_retries'] += 1
                        last_positivity_rejection = {'time_s': seconds, 'trial_error': str(error), 'context': 'Radau_constructor', 'accepted_state_unchanged': True}
                        bound = min(maximum_step, upper - seconds)
                        if first_step is not None:
                            bound = min(bound, first_step)
                        first_step = bound / 2
                        maximum_step = min(maximum_step, first_step)
                        if first_step <= 16 * _i23_math.ulp(seconds) or first_step <= 0:
                            raise ValueError('constructor positivity retry step unrepresentable; no clamp')
                        work['solver_reinitializations'] += 1
            work['observation_segment_initializations'] += 1
            solver = construct_solver(lower, state, experiment.max_step_s)
            segment_steps = []
            while solver.status == 'running':
                previous_state = accepted_state.copy()
                attempted_step = min(solver.h_abs, upper - accepted_time)
                trial_error = None
                try:
                    message = solver.step()
                except ValueError as error:
                    if not getattr(error, 'nonpositive_water_trial', False):
                        raise
                    trial_error = str(error)
                if trial_error is None and solver.status != 'failed':
                    work['accepted_endpoint_inventory_checks'] += 1
                    violation = positivity_violation(solver.y, count, solver.t)
                    actual_candidate_step = solver.t - accepted_time
                else:
                    violation = {'time_s': accepted_time, 'trial_error': trial_error} if trial_error else None
                    actual_candidate_step = attempted_step
                if violation is not None:
                    last_positivity_rejection = violation
                    if 'cell_ordinal' in violation:
                        last_positivity_rejection['cell_id'] = model.cells[violation['cell_ordinal']].cell_id
                    work['positivity_rejected_steps'] += 1
                    if trial_error:
                        work['nonpositive_total_trial_retries'] += 1
                    retry_step = min(attempted_step, actual_candidate_step) / 2
                    if retry_step <= 16 * _i23_math.ulp(accepted_time) or retry_step <= 0:
                        raise ValueError('strict positivity retry step unrepresentable; no clamp')
                    work['solver_reinitializations'] += 1
                    for name in rejected_solver_statistics:
                        rejected_solver_statistics[name] += getattr(solver, name)
                    solver = construct_solver(accepted_time, previous_state, min(experiment.max_step_s, retry_step), first_step=retry_step)
                    continue
                if solver.status == 'failed':
                    raise ValueError('Radau failed: ' + str(message))
                previous_time = accepted_time
                accepted_time = float(solver.t)
                accepted_state = solver.y.copy()
                solver.max_step = experiment.max_step_s
                step = accepted_time - previous_time
                accepted_steps += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                recent_steps.append({'start_s': previous_time, 'end_s': accepted_time, 'step_s': step})
                segment_steps.append(step)
                while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                    seconds = float(saved_times[saved_ordinal])
                    if seconds != accepted_time:
                        raise ValueError('saved physical observation must coincide with accepted Radau endpoint')
                    saved_state = accepted_state.copy()
                    violation = positivity_violation(saved_state, count, seconds)
                    if violation:
                        raise ValueError('saved inventory positivity violation: ' + str(violation))
                    observations.append((seconds, saved_state))
                    saved_ordinal += 1
            state = accepted_state.copy()
            integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(segment_steps), 'min_adaptive_step_s': min(segment_steps), 'max_adaptive_step_s': max(segment_steps), 'final_solver_nfev': solver.nfev, 'final_solver_njev': solver.njev, 'final_solver_nlu': solver.nlu, 'discarded_solver_statistics_cumulative': dict(rejected_solver_statistics)})
            if diagnostic_stop_s is not None and accepted_time >= diagnostic_stop_s:
                raise _diagnostic_stop('declared short diagnostic stop; not a completed hydraulic case', progress())
    except Exception as error:
        if getattr(error, 'diagnostic_stop', False):
            raise
        raise _execution_failure(str(error), progress()) from error
    if accepted_time != experiment.duration_s or saved_ordinal != len(saved_times):
        raise _execution_failure('physical event/observations incomplete', progress())
    try:
        saved_section_diagnostics = [{'time_s': seconds, **inventory_snapshot(model, system, current, crown_transition_width_m)} for seconds, current in observations]
        flux_probes = []
        for seconds, current in observations:
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and seconds < experiment.pulse_duration_s else 0.0
            flux_probes.append(flux_snapshot(model, system, seconds, current, source_q, crown_transition_width_m, experiment.tailwater_head_m))
        if work['link_evaluations'] > experiment.max_link_evaluations:
            raise ValueError('independent 1D diagnostic flux work bound exceeded')
        rows = _i23_np.array([current for seconds, current in observations])
        all_origins = rows[:, :3 * count].reshape(-1, 3, count)
        volumes = all_origins.sum(axis=1)
        masses = rows[:, count:3 * count].reshape(-1, 2, count)
        minimum_index = _i23_np.unravel_index(_i23_np.argmin(all_origins), all_origins.shape)
        saved_mass_extrema = {'minimum_origin_inventory_m3': float(all_origins[minimum_index]), 'time_s': float(saved_times[minimum_index[0]]), 'origin': ('untraced', 'source', 'tailwater')[minimum_index[1]], 'cell_id': model.cells[minimum_index[2]].cell_id, 'per_origin_minimum_m3': all_origins.min(axis=(0, 2)).tolist(), 'max_water_minus_origin_sum_m3': float(_i23_np.max(abs(volumes - all_origins.sum(axis=1))))}
        if not _i23_np.isfinite(rows).all() or _i23_np.any(all_origins < 0) or _i23_np.any(volumes <= 0):
            raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
        ledgers = rows[:, ledger_start:ledger_start + 6]
        residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
        residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
        residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
        untraced_out = rows[:, ledger_start + 6 + 4 * link_count]
        residual_untraced = all_origins[:, 0].sum(axis=1) - initial_volumes.sum() + untraced_out
        threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
        if max((_i23_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater, residual_untraced))) > threshold:
            raise ValueError('water/tracer conservation gate failed')
        heads = _i23_np.array([physical(row[:3 * count])[1] for row in rows])
        stages, pressure = ([], [])
        for head_row in heads:
            stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
        sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
        reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
        if _i23_time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024 ** 3:
            raise ValueError('final independent 1D wall/RSS bound exceeded')
        return {'schema': RADAU_SCHEMA, 'numerical_version': NUMERICAL_VERSION, 'model_version': MODEL_VERSION, 'friction_policy': {'width_m': crown_transition_width_m, 'transition_start': 'crown', 'transition_end': 'crown+width_m', 'actual_perimeter_unchanged': True, 'storage_area_unchanged': True, 'pressure_slot_width_unchanged': True, 'roof_length_source': 'sum_actual_polygon_edges_with_both_endpoints_at_crown', 'constitutive_kind': 'C1_effective_roof_contact_friction' if crown_transition_width_m > 0 else 'legacy_actual_perimeter', 'contact_polynomial': 'u*u*(3-2*u)_for_0<=u<=1'}, 'saved_section_diagnostics': saved_section_diagnostics, 'instantaneous_flux_probes': flux_probes, 'execution_progress': progress(), 'jacobian_policy': {**jacobian_policy(model, crown_transition_width_m), 'observed_max_head_step_m': work.get('jacobian_max_observed_head_step_m', 0.0)}, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_Radau', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'untraced_water_volume_m3': all_origins[:, 0].tolist(), 'inventory_policy': inventory_policy(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:ledger_start + 6 + 3 * link_count].tolist(), 'paired_link_untraced_integral_m3': rows[:, ledger_start + 6 + 3 * link_count:ledger_start + 6 + 4 * link_count].tolist(), 'outlet_untraced_out_m3': untraced_out.tolist(), 'max_untraced_residual_m3': float(_i23_np.max(abs(residual_untraced))), 'saved_mass_extrema': saved_mass_extrema, 'dense_positivity_witness': {'policy': 'no_dense_inventory_output_saved_times_are_Radau_endpoints', 'interpolated_inventory_samples': 0, 'continuous_between_steps_positivity_certified': False, 'candidate_endpoint_checks': work['accepted_endpoint_inventory_checks'], 'accepted_steps': accepted_steps, 'last_rejected': last_positivity_rejection, 'negative_inventory_tolerance_m3': 0.0}, 'max_water_residual_m3': float(_i23_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i23_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i23_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': system.peak_rss(), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i23_time.monotonic() - started}}
    except Exception as error:
        raise _execution_failure(str(error), progress()) from error
BDF_SCHEMA = 'td-hybrid-river-hydraulics-v7'
BDF_NUMERICAL_VERSION = 'three_origin_analytic_native_chain_BDF_precision-v7'
INTEGRATION = 'BDF'

def bdf_build_system(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, rhs_observer=None):
    validate_transition(crown_transition_width_m)
    model.validate()
    experiment.validate(model)
    count, link_count = (len(model.cells), len(model.links))
    initial_volumes = _i24_np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if _i24_np.any(initial_volumes <= 0):
        raise ValueError('initial storage must be strictly positive')
    ledger_start = 3 * count
    state = _i24_np.zeros(ledger_start + 7 + 4 * link_count)
    state[:count] = initial_volumes
    work = {'rhs_evaluations': 0, 'link_evaluations': 0, 'old_hll_face_work': 0, 'jacobian_evaluations': 0, 'jacobian_rhs_evaluations': 0, 'jacobian_link_evaluations': 0, 'jacobian_native_section_derivatives': 0, 'jacobian_flow_evaluations': 0, 'jacobian_link_derivative_evaluations': 0, 'jacobian_section_fallback_evaluations': 0, 'positivity_rejected_steps': 0, 'nonpositive_total_trial_retries': 0, 'solver_reinitializations': 0, 'constructor_nonpositive_retries': 0, 'accepted_endpoint_inventory_checks': 0, 'observation_segment_initializations': 0, 'bdf_constructor_attempts': 0}
    started = _i24_time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    roof_lengths = [roof_contact_length(cell.section) for cell in model.cells]

    def capacity_for(ordinal, head):
        return friction_state(model.cells[ordinal], head, crown_transition_width_m, roof_lengths[ordinal])['effective_manning_conveyance']

    def physical(inventories):
        if _i24_np.shape(inventories) != (3 * count,) or not _i24_np.isfinite(inventories).all():
            raise _nonpositive_water_trial('physical inventory requires finite three-origin state')
        volumes = inventories.reshape(3, count).sum(axis=0)
        if _i24_np.any(volumes <= 0):
            raise _nonpositive_water_trial('trial total water is nonpositive; no floor clamp')
        heads = _i24_np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any((head <= cell.section.floor_m for cell, head in zip(model.cells, heads))):
            raise _nonpositive_water_trial('trial positive inventory below representable depth; no floor clamp')
        capacities = _i24_np.array([capacity_for(ordinal, head) for ordinal, head in enumerate(heads)])
        return (volumes, heads, capacities)

    def guard():
        nonlocal peak_rss
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations or work['link_evaluations'] > experiment.max_link_evaluations or _i24_time.monotonic() - started > experiment.max_wall_seconds:
            raise ValueError('independent 1D work/time bound exceeded')
        peak_rss = max(peak_rss, process.memory_info().rss)
        if peak_rss > 1024 ** 3:
            raise ValueError('1GiB hydraulic RSS limit exceeded')

    def flows(current):
        volumes, heads, capacities = physical(current[:3 * count])
        amounts = []
        for ordinal, link in enumerate(model.links):
            flow = common_signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
            donor = ordinal if flow >= 0 else ordinal + 1
            flow *= volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
            amounts.append((float(flow), donor))
        boundary_capacity = min(capacities[-1], capacity_for(count - 1, experiment.tailwater_head_m))
        outlet = common_signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
        if outlet >= 0:
            outlet *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
        return (volumes, heads, amounts, float(outlet))

    def concentration_matrix(amounts, outlet):
        matrix = _i24_np.zeros((len(state), 3 * count))
        for ordinal, (flow, donor) in enumerate(amounts):
            for origin in range(3):
                column = origin * count + donor
                matrix[origin * count + ordinal, column] -= flow
                matrix[origin * count + ordinal + 1, column] += flow
                row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                matrix[row, column] += flow
        if outlet >= 0:
            for origin in range(3):
                column = origin * count + count - 1
                matrix[column, column] -= outlet
                row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                matrix[row, column] += outlet
        return matrix

    def rhs_for(source_q):

        def rhs(seconds, current, evaluation_context='BDF_rhs_trial'):
            if rhs_observer is not None:
                rhs_observer(seconds, current, evaluation_context)
            work['rhs_evaluations'] += 1
            work['link_evaluations'] += link_count + 1
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivative = _i24_np.zeros_like(current)
            rates = derivative[:3 * count].reshape(3, count)
            for ordinal, (flow, donor) in enumerate(amounts):
                transport = flow * concentrations[:, donor]
                rates[:, ordinal] -= transport
                rates[:, ordinal + 1] += transport
                derivative[ledger_start + 6 + link_count + ordinal] = transport[1]
                derivative[ledger_start + 6 + 2 * link_count + ordinal] = transport[2]
                derivative[ledger_start + 6 + 3 * link_count + ordinal] = transport[0]
            derivative[count] += source_q
            derivative[ledger_start] = source_q
            for ordinal, (flow, donor) in enumerate(amounts):
                derivative[ledger_start + 6 + ordinal] = flow
            if outlet >= 0:
                transport = outlet * concentrations[:, -1]
                rates[:, -1] -= transport
                derivative[ledger_start + 1] = outlet
                derivative[ledger_start + 3] = transport[1]
                derivative[ledger_start + 5] = transport[2]
                derivative[ledger_start + 6 + 4 * link_count] = transport[0]
            else:
                derivative[3 * count - 1] -= outlet
                derivative[ledger_start + 2] = -outlet
                derivative[ledger_start + 4] = -outlet
            return derivative
        return rhs

    def jacobian_for(source_q):

        def jacobian(seconds, current):
            if _i24_np.shape(current) != (len(state),) or not _i24_np.isfinite(current).all():
                raise ValueError('Jacobian requires finite complete three-origin state')
            if rhs_observer is not None:
                rhs_observer(seconds, current, 'Jacobian_analytic_state')
            work['jacobian_evaluations'] += 1
            work['jacobian_link_evaluations'] += 2 * (link_count + 1)
            work['jacobian_flow_evaluations'] += link_count + 1
            work['jacobian_link_derivative_evaluations'] += link_count + 1
            work['link_evaluations'] += 2 * (link_count + 1)
            guard()
            volumes, heads, amounts, outlet = flows(current)
            concentrations = current[:3 * count].reshape(3, count) / volumes
            derivatives = [section_slopes(cell, heads[ordinal], crown_transition_width_m, roof_lengths[ordinal], work) for ordinal, cell in enumerate(model.cells)]
            matrix = _i24_np.zeros((len(state), len(state)))
            for ordinal, (flow, donor) in enumerate(amounts):
                link = model.links[ordinal]
                left_capacity, left_head_slope, left_capacity_slope = derivatives[ordinal]
                right_capacity, right_head_slope, right_capacity_slope = derivatives[ordinal + 1]
                limiting_left = left_capacity <= right_capacity
                minimum_capacity = min(left_capacity, right_capacity)
                factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
                donor_factor = volumes[donor] / (volumes[donor] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[donor] + model.donor_regularization_m3) ** 2
                left_flow_slope = donor_factor * (difference_derivative * left_head_slope + factor * left_capacity_slope * limiting_left)
                right_flow_slope = donor_factor * (-difference_derivative * right_head_slope + factor * right_capacity_slope * (not limiting_left))
                if donor == ordinal:
                    left_flow_slope += minimum_capacity * factor * donor_derivative
                else:
                    right_flow_slope += minimum_capacity * factor * donor_derivative
                for cell_ordinal, flow_slope in ((ordinal, left_flow_slope), (ordinal + 1, right_flow_slope)):
                    for origin_column in range(3):
                        column = origin_column * count + cell_ordinal
                        matrix[ledger_start + 6 + ordinal, column] += flow_slope
                        for origin in range(3):
                            transport_slope = concentrations[origin, donor] * flow_slope
                            if cell_ordinal == donor:
                                transport_slope += flow * ((origin == origin_column) - concentrations[origin, donor]) / volumes[donor]
                            matrix[origin * count + ordinal, column] -= transport_slope
                            matrix[origin * count + ordinal + 1, column] += transport_slope
                            row = ledger_start + 6 + origin * link_count + ordinal if origin else ledger_start + 6 + 3 * link_count + ordinal
                            matrix[row, column] += transport_slope
            capacity, head_slope, capacity_slope = derivatives[-1]
            tailwater_capacity = capacity_for(count - 1, experiment.tailwater_head_m)
            limiting_cell = capacity <= tailwater_capacity
            minimum_capacity = min(capacity, tailwater_capacity)
            factor, difference_derivative = signed_flow_slopes(minimum_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            flow_slope = difference_derivative * head_slope + factor * capacity_slope * limiting_cell
            if outlet >= 0:
                donor_factor = volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                donor_derivative = model.donor_regularization_m3 / (volumes[-1] + model.donor_regularization_m3) ** 2
                flow_slope = flow_slope * donor_factor + minimum_capacity * factor * donor_derivative
            for origin_column in range(3):
                column = origin_column * count + count - 1
                if outlet >= 0:
                    matrix[ledger_start + 1, column] += flow_slope
                    for origin in range(3):
                        transport_slope = concentrations[origin, -1] * flow_slope + outlet * ((origin == origin_column) - concentrations[origin, -1]) / volumes[-1]
                        matrix[origin * count + count - 1, column] -= transport_slope
                        row = ledger_start + (3 if origin == 1 else 5) if origin else ledger_start + 6 + 4 * link_count
                        matrix[row, column] += transport_slope
                else:
                    matrix[3 * count - 1, column] -= flow_slope
                    matrix[ledger_start + 2, column] -= flow_slope
                    matrix[ledger_start + 4, column] -= flow_slope
            if not _i24_np.isfinite(matrix).all():
                raise ValueError('analytic three-origin Jacobian nonfinite')
            return matrix
        return jacobian
    return StorageSystem(count, state, initial_volumes, work, started, physical, rhs_for, jacobian_for, lambda: max(peak_rss, process.memory_info().rss))

def bdf_inventory_policy():
    return {'origins': ['untraced', 'source', 'tailwater'], 'water_definition': 'sum_three_origin_inventories', 'state_units': 'm3', 'negative_inventory_action': 'reject_entire_BDF_step_and_halve_retry', 'dense_inventory_check': 'no_interpolated_inventory_output_saved_times_are_BDF_endpoints', 'output_clamp': False, 'posthoc_normalization': False, 'positivity_tolerance_m3': 0.0, 'initial_origin': 'untraced', 'pulse_origin': 'source', 'reverse_boundary_origin': 'tailwater', 'trial_scope': 'finite_signed_origin_Newton_trials_allowed_only_with_positive_total_water', 'retry_budget': 'one_original_event_work_wall_RSS_budget_never_reset'}

def bdf_run_experiment(model: Model, experiment: common_Experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    if diagnostic_stop_s is not None and (not _i24_math.isfinite(diagnostic_stop_s) or not 0 < diagnostic_stop_s <= experiment.duration_s):
        raise ValueError('diagnostic stop must be positive and within the unchanged physical event')
    last_evaluation = {'context': 'not_started', 'time_s': None}
    last_trial_state = None

    def observe_rhs(seconds, current, context):
        nonlocal last_trial_state
        last_evaluation.update(context=context, time_s=float(seconds))
        last_trial_state = current.copy()
    system = bdf_build_system(model, experiment, crown_transition_width_m, rhs_observer=observe_rhs)
    count, link_count = (system.count, len(model.links))
    ledger_start = 3 * count
    state = system.initial_state.copy()
    initial_volumes, work, started = (system.initial_volumes, system.work, system.started)
    physical = system.physical
    accepted_state, accepted_time = (state.copy(), 0.0)
    accepted_steps, min_step, max_step = (0, None, None)
    last_positivity_rejection = None
    saved_mass_extrema = None
    recent_steps = _i24_deque(maxlen=16)
    accepted_order_counts = {str(order): 0 for order in range(1, 6)}
    observations = [(0.0, state.copy())]
    integration_segments = []
    rejected_solver_statistics = {'nfev': 0, 'njev': 0, 'nlu': 0}
    saved_times = _i24_np.asarray(experiment.saved_times_s)
    saved_ordinal = 1

    def progress():
        observed_origins = _i24_np.array([current[:3 * count].reshape(3, count) for seconds, current in observations])
        observed_index = _i24_np.unravel_index(_i24_np.argmin(observed_origins), observed_origins.shape)
        observed_extrema = {'minimum_origin_inventory_m3': float(observed_origins[observed_index]), 'time_s': float(observations[observed_index[0]][0]), 'origin': ('untraced', 'source', 'tailwater')[observed_index[1]], 'cell_id': model.cells[observed_index[2]].cell_id, 'per_origin_minimum_m3': observed_origins.min(axis=(0, 2)).tolist()}
        elapsed = _i24_time.monotonic() - started
        guard = None
        if work['rhs_evaluations'] > experiment.max_rhs_evaluations:
            guard = 'max_rhs_evaluations'
        elif work['link_evaluations'] > experiment.max_link_evaluations:
            guard = 'max_link_evaluations'
        elif elapsed > experiment.max_wall_seconds:
            guard = 'max_wall_seconds'
        elif system.peak_rss() > 1024 ** 3:
            guard = 'max_rss_bytes'
        trial = None
        if last_trial_state is not None:
            trial = {'state_all_finite': bool(_i24_np.isfinite(last_trial_state).all()), 'state': [float(value) if _i24_math.isfinite(value) else None for value in last_trial_state], 'is_accepted_state': False, 'state_layout': 'untracedMass/sourceMass/tailwaterMass/oldSixBoundary/threePaired/untracedPaired/untracedOutlet'}
        try:
            accepted_inventory = inventory_snapshot(model, system, accepted_state, crown_transition_width_m)
        except Exception as snapshot_error:
            accepted_inventory = {'snapshot_error': str(snapshot_error), 'state': [float(value) if _i24_math.isfinite(value) else None for value in accepted_state]}
        return {'last_accepted_physical_time_s': accepted_time, 'configured_physical_duration_s': experiment.duration_s, 'diagnostic_stop_s': diagnostic_stop_s, 'physical_event_complete': accepted_time == experiment.duration_s, 'work': dict(work), 'last_positivity_rejection': last_positivity_rejection, 'saved_mass_extrema': saved_mass_extrema if saved_mass_extrema is not None else observed_extrema, 'elapsed_wall_seconds': elapsed, 'triggered_guard': guard, 'discarded_solver_statistics': dict(rejected_solver_statistics), 'max_rhs_evaluations': experiment.max_rhs_evaluations, 'max_link_evaluations': experiment.max_link_evaluations, 'max_wall_seconds': experiment.max_wall_seconds, 'accepted_steps': accepted_steps, 'min_accepted_step_s': min_step, 'max_accepted_step_s': max_step, 'recent_accepted_steps': list(recent_steps), 'accepted_BDF_order_after_step_counts': dict(accepted_order_counts), 'last_evaluation': dict(last_evaluation), 'last_trial': trial, 'last_accepted_inventory': accepted_inventory, 'actual_peak_rss_bytes': system.peak_rss(), 'model_version': MODEL_VERSION, 'integration': INTEGRATION, 'crown_friction_transition_width_m': crown_transition_width_m, 'inventory_scope': 'actual section storage plus explicit engineering slot/overbank walls; not Boolean excavation volume'}
    breaks = [0.0, experiment.duration_s, *experiment.saved_times_s]
    if experiment.scenario == 'pulse':
        breaks.append(experiment.pulse_duration_s)
    breaks = sorted(set(breaks))
    try:
        for lower, full_upper in zip(breaks[:-1], breaks[1:]):
            upper = min(full_upper, diagnostic_stop_s) if diagnostic_stop_s is not None else full_upper
            if upper <= lower:
                break
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and lower < experiment.pulse_duration_s else 0.0
            raw_rhs, raw_jacobian = (system.rhs_for(source_q), system.jacobian_for(source_q))

            def tracked_rhs(seconds, current):
                return raw_rhs(seconds, current)

            def tracked_jacobian(seconds, current):
                return raw_jacobian(seconds, current)

            def construct_solver(seconds, current, maximum_step, first_step=None):
                nonlocal last_positivity_rejection
                while True:
                    try:
                        work['bdf_constructor_attempts'] += 1
                        return _i24_BDF(tracked_rhs, seconds, current, upper, max_step=maximum_step, first_step=first_step, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance, jac=tracked_jacobian)
                    except ValueError as error:
                        if not getattr(error, 'nonpositive_water_trial', False):
                            raise
                        work['constructor_nonpositive_retries'] += 1
                        work['nonpositive_total_trial_retries'] += 1
                        last_positivity_rejection = {'time_s': seconds, 'trial_error': str(error), 'context': 'BDF_constructor', 'accepted_state_unchanged': True}
                        bound = min(maximum_step, upper - seconds)
                        if first_step is not None:
                            bound = min(bound, first_step)
                        first_step = bound / 2
                        maximum_step = min(maximum_step, first_step)
                        if first_step <= 16 * _i24_math.ulp(seconds) or first_step <= 0:
                            raise ValueError('constructor positivity retry step unrepresentable; no clamp')
                        work['solver_reinitializations'] += 1
            work['observation_segment_initializations'] += 1
            solver = construct_solver(lower, state, experiment.max_step_s)
            segment_steps = []
            while solver.status == 'running':
                previous_state = accepted_state.copy()
                attempted_step = min(solver.h_abs, upper - accepted_time)
                trial_error = None
                try:
                    message = solver.step()
                except ValueError as error:
                    if not getattr(error, 'nonpositive_water_trial', False):
                        raise
                    trial_error = str(error)
                if trial_error is None and solver.status != 'failed':
                    work['accepted_endpoint_inventory_checks'] += 1
                    violation = positivity_violation(solver.y, count, solver.t)
                    actual_candidate_step = solver.t - accepted_time
                else:
                    violation = {'time_s': accepted_time, 'trial_error': trial_error} if trial_error else None
                    actual_candidate_step = attempted_step
                if violation is not None:
                    last_positivity_rejection = violation
                    if 'cell_ordinal' in violation:
                        last_positivity_rejection['cell_id'] = model.cells[violation['cell_ordinal']].cell_id
                    work['positivity_rejected_steps'] += 1
                    if trial_error:
                        work['nonpositive_total_trial_retries'] += 1
                    retry_step = min(attempted_step, actual_candidate_step) / 2
                    if retry_step <= 16 * _i24_math.ulp(accepted_time) or retry_step <= 0:
                        raise ValueError('strict positivity retry step unrepresentable; no clamp')
                    work['solver_reinitializations'] += 1
                    for name in rejected_solver_statistics:
                        rejected_solver_statistics[name] += getattr(solver, name)
                    solver = construct_solver(accepted_time, previous_state, min(experiment.max_step_s, retry_step), first_step=retry_step)
                    continue
                if solver.status == 'failed':
                    raise ValueError('BDF failed: ' + str(message))
                previous_time = accepted_time
                accepted_time = float(solver.t)
                accepted_state = solver.y.copy()
                solver.max_step = experiment.max_step_s
                step = accepted_time - previous_time
                accepted_steps += 1
                accepted_order_counts[str(solver.order)] += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                recent_steps.append({'start_s': previous_time, 'end_s': accepted_time, 'step_s': step, 'solver_order_after_step': int(solver.order)})
                segment_steps.append(step)
                while saved_ordinal < len(saved_times) and saved_times[saved_ordinal] <= accepted_time:
                    seconds = float(saved_times[saved_ordinal])
                    if seconds != accepted_time:
                        raise ValueError('saved physical observation must coincide with accepted BDF endpoint')
                    saved_state = accepted_state.copy()
                    violation = positivity_violation(saved_state, count, seconds)
                    if violation:
                        raise ValueError('saved inventory positivity violation: ' + str(violation))
                    observations.append((seconds, saved_state))
                    saved_ordinal += 1
            state = accepted_state.copy()
            integration_segments.append({'start_s': lower, 'end_s': upper, 'accepted_steps': len(segment_steps), 'min_adaptive_step_s': min(segment_steps), 'max_adaptive_step_s': max(segment_steps), 'final_solver_nfev': solver.nfev, 'final_solver_njev': solver.njev, 'final_solver_nlu': solver.nlu, 'discarded_solver_statistics_cumulative': dict(rejected_solver_statistics)})
            if diagnostic_stop_s is not None and accepted_time >= diagnostic_stop_s:
                raise _diagnostic_stop('declared short diagnostic stop; not a completed hydraulic case', progress())
    except Exception as error:
        if getattr(error, 'diagnostic_stop', False):
            raise
        raise _execution_failure(str(error), progress()) from error
    if accepted_time != experiment.duration_s or saved_ordinal != len(saved_times):
        raise _execution_failure('physical event/observations incomplete', progress())
    try:
        saved_section_diagnostics = [{'time_s': seconds, **inventory_snapshot(model, system, current, crown_transition_width_m)} for seconds, current in observations]
        flux_probes = []
        for seconds, current in observations:
            source_q = experiment.pulse_q_m3_s if experiment.scenario == 'pulse' and seconds < experiment.pulse_duration_s else 0.0
            flux_probes.append(flux_snapshot(model, system, seconds, current, source_q, crown_transition_width_m, experiment.tailwater_head_m))
        if work['link_evaluations'] > experiment.max_link_evaluations:
            raise ValueError('independent 1D diagnostic flux work bound exceeded')
        rows = _i24_np.array([current for seconds, current in observations])
        all_origins = rows[:, :3 * count].reshape(-1, 3, count)
        volumes = all_origins.sum(axis=1)
        masses = rows[:, count:3 * count].reshape(-1, 2, count)
        minimum_index = _i24_np.unravel_index(_i24_np.argmin(all_origins), all_origins.shape)
        saved_mass_extrema = {'minimum_origin_inventory_m3': float(all_origins[minimum_index]), 'time_s': float(saved_times[minimum_index[0]]), 'origin': ('untraced', 'source', 'tailwater')[minimum_index[1]], 'cell_id': model.cells[minimum_index[2]].cell_id, 'per_origin_minimum_m3': all_origins.min(axis=(0, 2)).tolist(), 'max_water_minus_origin_sum_m3': float(_i24_np.max(abs(volumes - all_origins.sum(axis=1))))}
        if not _i24_np.isfinite(rows).all() or _i24_np.any(all_origins < 0) or _i24_np.any(volumes <= 0):
            raise ValueError('strict saved tracer positivity/composition failed; no output clamp')
        ledgers = rows[:, ledger_start:ledger_start + 6]
        residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
        residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
        residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
        untraced_out = rows[:, ledger_start + 6 + 4 * link_count]
        residual_untraced = all_origins[:, 0].sum(axis=1) - initial_volumes.sum() + untraced_out
        threshold = max(1e-07, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
        if max((_i24_np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater, residual_untraced))) > threshold:
            raise ValueError('water/tracer conservation gate failed')
        heads = _i24_np.array([physical(row[:3 * count])[1] for row in rows])
        stages, pressure = ([], [])
        for head_row in heads:
            stages.append([float(head) if cell.kind == 'surface' or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
            pressure.append([float(head) if cell.kind == 'underground' and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
        sink_link_index = next((ordinal for ordinal, link in enumerate(model.links) if link.kind == 'sink_exchange'))
        reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
        if _i24_time.monotonic() - started > experiment.max_wall_seconds or system.peak_rss() > 1024 ** 3:
            raise ValueError('final independent 1D wall/RSS bound exceeded')
        return {'schema': BDF_SCHEMA, 'numerical_version': BDF_NUMERICAL_VERSION, 'integration': INTEGRATION, 'model_version': MODEL_VERSION, 'friction_policy': {'width_m': crown_transition_width_m, 'transition_start': 'crown', 'transition_end': 'crown+width_m', 'actual_perimeter_unchanged': True, 'storage_area_unchanged': True, 'pressure_slot_width_unchanged': True, 'roof_length_source': 'sum_actual_polygon_edges_with_both_endpoints_at_crown', 'constitutive_kind': 'C1_effective_roof_contact_friction' if crown_transition_width_m > 0 else 'legacy_actual_perimeter', 'contact_polynomial': 'u*u*(3-2*u)_for_0<=u<=1'}, 'saved_section_diagnostics': saved_section_diagnostics, 'instantaneous_flux_probes': flux_probes, 'execution_progress': progress(), 'jacobian_policy': {**jacobian_policy(model, crown_transition_width_m), 'observed_max_head_step_m': work.get('jacobian_max_observed_head_step_m', 0.0)}, 'status': 'diagnostic_completed', 'model': 'finite_1d_diffusive_storage_signed_manning_BDF', 'pressure_model': 'explicit_engineered_Preissmann_slot_compliance_not_waterhammer', 'scenario': experiment.scenario, 'cell_ids': [cell.cell_id for cell in model.cells], 'link_ids': [link.link_id for link in model.links], 'times_s': [seconds for seconds, current in observations], 'water_volume_m3': volumes.tolist(), 'untraced_water_volume_m3': all_origins[:, 0].tolist(), 'inventory_policy': bdf_inventory_policy(), 'source_tracer_mass_m3': masses[:, 0].tolist(), 'tailwater_tracer_mass_m3': masses[:, 1].tolist(), 'open_channel_stage_m': stages, 'pressurized_head_m': pressure, 'hydraulic_head_m': heads.tolist(), 'initial_untraced_water_m3': initial_volumes.tolist(), 'ledger_columns': ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3'], 'boundary_ledger_m3': ledgers.tolist(), 'paired_link_water_integral_m3': rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(), 'paired_link_source_integral_m3': rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(), 'paired_link_tailwater_integral_m3': rows[:, ledger_start + 6 + 2 * link_count:ledger_start + 6 + 3 * link_count].tolist(), 'paired_link_untraced_integral_m3': rows[:, ledger_start + 6 + 3 * link_count:ledger_start + 6 + 4 * link_count].tolist(), 'outlet_untraced_out_m3': untraced_out.tolist(), 'max_untraced_residual_m3': float(_i24_np.max(abs(residual_untraced))), 'saved_mass_extrema': saved_mass_extrema, 'dense_positivity_witness': {'policy': 'no_dense_inventory_output_saved_times_are_BDF_endpoints', 'interpolated_inventory_samples': 0, 'continuous_between_steps_positivity_certified': False, 'candidate_endpoint_checks': work['accepted_endpoint_inventory_checks'], 'accepted_steps': accepted_steps, 'last_rejected': last_positivity_rejection, 'negative_inventory_tolerance_m3': 0.0}, 'max_water_residual_m3': float(_i24_np.max(abs(residual_water))), 'max_source_residual_m3': float(_i24_np.max(abs(residual_source))), 'max_tailwater_residual_m3': float(_i24_np.max(abs(residual_tailwater))), 'conservation_gate_m3': threshold, 'source_arrival_threshold_m3': experiment.source_arrival_threshold_m3, 'source_arrival_time_s': arrival[0] if arrival else None, 'arrival_semantics': 'threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed', 'source_reached_spring': bool(arrival), 'source_reached_engineered_outlet': bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3), 'reverse_reached_sink': bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3), 'boundary_condition_kind': 'engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet', 'boundary_scope': 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'integration_segments': integration_segments, 'model_parameters': {'head_regularization_m': model.head_regularization_m, 'donor_regularization_m3': model.donor_regularization_m3}, 'no_duplicate_cumulative_Q': True, 'natural_outlet_certified': False, 'full_network_verified': False, 'finite_speed_front_verified': False, 'three_dimensional_flow_solved': False, 'work': {**work, 'old_hll_face_budget_remaining_unchanged': COMMON_OLD_FACE_BUDGET_REMAINING, 'actual_peak_rss_bytes': system.peak_rss(), 'max_rss_bytes': 1024 ** 3, 'wall_seconds': _i24_time.monotonic() - started}}
    except Exception as error:
        raise _execution_failure(str(error), progress()) from error
HYBRID_RIVER_SECTIONS_MECHANISM_2_SCHEMA = 'td-hybrid-river-fast-sections-v2'

@_i26_dataclass(frozen=True)
class HeightBand:
    lower_m: float
    area_at_lower_m2: float
    width_at_lower_m: float
    width_slope: float
    perimeter_at_lower_m: float
    perimeter_slope: float

    def area_perimeter(self, head_m):
        delta = head_m - self.lower_m
        return (self.area_at_lower_m2 + delta * (self.width_at_lower_m + 0.5 * self.width_slope * delta), self.perimeter_at_lower_m + self.perimeter_slope * delta)

def _polygon_width(edges, height, midpoint, orientation):
    contributions = []
    for start, end in edges:
        if min(start[1], end[1]) < midpoint < max(start[1], end[1]):
            if height == start[1]:
                crossing = start[0]
            elif height == end[1]:
                crossing = end[0]
            else:
                crossing = start[0] + (end[0] - start[0]) * ((height - start[1]) / (end[1] - start[1]))
            contributions.append(orientation * (1 if end[1] > start[1] else -1) * crossing)
    return _i26_math.fsum(contributions)

def _edge_perimeter(edges, lower, midpoint):
    values, slopes = ([], [])
    for start, end in edges:
        length = _i26_math.dist(start, end)
        bottom, top = sorted((start[1], end[1]))
        if lower >= top:
            values.append(length)
        elif lower > bottom:
            values.append(length * (lower - bottom) / (top - bottom))
        if bottom < midpoint < top:
            slopes.append(length / (top - bottom))
    return (_i26_math.fsum(values), _i26_math.fsum(slopes))

def _open_width(pieces, height, midpoint):
    spans = []
    for width, coefficients in pieces:
        bottom, top = sorted((coefficients[0], sum(coefficients)))
        if midpoint > top:
            spans.append(width)
        elif bottom < midpoint < top:
            spans.append(width * (height - bottom) / (top - bottom))
    return _i26_math.fsum(spans)

def _compile(section):
    if section.kind == 'native_bed':
        return ((), (), (), ())
    floor = section.floor_m
    if section.kind == 'closed_polygon':
        origin_x = section.polygon[0][0]
        polygon = tuple(((point[0] - origin_x, point[1] - floor) for point in section.polygon))
        edges = tuple(zip(polygon, polygon[1:] + polygon[:1]))
        local = polygon
        signed_area = _i26_math.fsum((start[0] * end[1] - end[0] * start[1] for start, end in zip(local, local[1:] + local[:1]))) / 2
        orientation = 1 if signed_area > 0 else -1
        levels = tuple(sorted(set((point[1] for point in polygon))))
    else:
        pieces = tuple(((width, (coefficients[0] - floor, sum(coefficients) - coefficients[0], 0.0)) for width, coefficients in section.pieces))
        levels = tuple(sorted(set((value for width, coefficients in pieces for value in (coefficients[0], sum(coefficients))))))
        edges = tuple((((0.0, coefficients[0]), (width, sum(coefficients))) for width, coefficients in pieces))
    bands, area_knots = ([], [0.0])
    for lower, upper in zip(levels[:-1], levels[1:]):
        midpoint = lower + (upper - lower) / 2
        if section.kind == 'closed_polygon':
            lower_width = _polygon_width(edges, lower, midpoint, orientation)
            upper_width = _polygon_width(edges, upper, midpoint, orientation)
        else:
            lower_width = _open_width(pieces, lower, midpoint)
            upper_width = _open_width(pieces, upper, midpoint)
        if lower_width < 0 or upper_width < 0:
            raise ValueError('cached section has negative submerged width')
        perimeter, perimeter_slope = _edge_perimeter(edges, lower, midpoint)
        if section.kind == 'open_polyline':
            ends = (pieces[0][1][0], sum(pieces[-1][1]))
            perimeter += _i26_math.fsum((max(0.0, lower - end) for end in ends))
            perimeter_slope += sum((midpoint > end for end in ends))
        band = HeightBand(floor + lower, area_knots[-1], lower_width, (upper_width - lower_width) / (upper - lower), perimeter, perimeter_slope)
        bands.append(band)
        area_knots.append(area_knots[-1] + (upper - lower) * (lower_width + upper_width) / 2)
    lower = levels[-1]
    perimeter, perimeter_slope = _edge_perimeter(edges, lower, lower + 1)
    if section.kind == 'closed_polygon':
        width = section.pressure_slot_width_m
    else:
        width = _i26_math.fsum((piece[0] for piece in section.pieces))
        perimeter += max(0.0, lower - pieces[0][1][0]) + max(0.0, lower - sum(pieces[-1][1]))
        perimeter_slope += 2
    bands.append(HeightBand(floor + lower, area_knots[-1], width, 0.0, perimeter, perimeter_slope))
    absolute_levels = tuple((floor + level for level in levels))
    point_perimeters = tuple((section.area_perimeter(level)[1] for level in absolute_levels))
    return (absolute_levels, tuple(area_knots), tuple(bands), point_perimeters)

@_i26_dataclass(frozen=True)
class FastSection:
    original: common_Section
    levels_m: tuple = ()
    area_knots_m2: tuple = ()
    bands: tuple = ()
    point_perimeters_m: tuple = ()

    def __init__(self, original):
        original.validate()
        if original.kind == 'open_polyline' and any((piece[1][2] != 0 for piece in original.pieces)):
            raise ValueError('open polyline cannot contain quadratic geometry')
        levels, areas, bands, point_perimeters = _compile(original)
        object.__setattr__(self, 'original', original)
        object.__setattr__(self, 'levels_m', levels)
        object.__setattr__(self, 'area_knots_m2', areas)
        object.__setattr__(self, 'bands', bands)
        object.__setattr__(self, 'point_perimeters_m', point_perimeters)

    @classmethod
    def from_record(cls, record):
        return cls(common_Section.from_record(record))

    @property
    def kind(self):
        return self.original.kind

    @property
    def pieces(self):
        return self.original.pieces

    @property
    def polygon(self):
        return self.original.polygon

    @property
    def pressure_slot_width_m(self):
        return self.original.pressure_slot_width_m

    @property
    def floor_m(self):
        return self.levels_m[0] if self.bands else self.original.floor_m

    @property
    def crown_m(self):
        return self.levels_m[-1] if self.kind == 'closed_polygon' else None

    def validate(self):
        return None

    def area_perimeter(self, head_m):
        if not _i26_math.isfinite(head_m):
            raise ValueError('nonfinite section head')
        if not self.bands:
            return self.original.area_perimeter(head_m)
        if head_m <= self.floor_m:
            return (0.0, 0.0)
        ordinal = _i26_bisect_right(self.levels_m, head_m) - 1
        if head_m == self.levels_m[ordinal]:
            return (self.area_knots_m2[ordinal], self.point_perimeters_m[ordinal])
        return self.bands[ordinal].area_perimeter(head_m)

    def head_for_area(self, area_m2):
        area = common_positive(area_m2, 'stored section area')
        if not self.bands:
            return self.original.head_for_area(area)
        ordinal = _i26_bisect_right(self.area_knots_m2, area) - 1
        band = self.bands[ordinal]
        difference = area - band.area_at_lower_m2
        if difference == 0:
            return band.lower_m
        if band.width_slope == 0:
            delta = difference / band.width_at_lower_m
        else:
            discriminant = band.width_at_lower_m ** 2 + 2 * band.width_slope * difference
            if discriminant >= 0:
                delta = 2 * difference / (band.width_at_lower_m + _i26_math.sqrt(discriminant))
            else:
                delta = -1.0
            span = self.levels_m[ordinal + 1] - band.lower_m
            if not 0 <= delta <= span:
                delta = _i26_brentq(lambda offset: offset * (band.width_at_lower_m + 0.5 * band.width_slope * offset) - difference, 0, span, xtol=1e-10)
        head = band.lower_m + delta
        if not _i26_math.isfinite(head) or head - self.floor_m > 1000000.0:
            raise ValueError('head exceeds bounded model range')
        return head

def accelerate_model(model):
    accelerated = _i26_replace(model, cells=tuple((_i26_replace(cell, section=FastSection(cell.section)) for cell in model.cells)))
    accelerated.validate()
    return accelerated
LOCAL_FRAME_SCHEMA = 'td-hybrid-river-hydraulics-v8'
LOCAL_FRAME_INTEGRATION = 'Radau'
LOCAL_FRAME_NUMERICAL_VERSION = 'three_origin_local_vertical_frame_analytic_Radau_precision-v8'
ABSOLUTE_HEIGHT_FIELDS = frozenset(('head_m', 'crown_m', 'low_bank_m', 'floor_m'))

def numerical_frame(model):
    datum = float(_i25_math.floor(min((cell.section.floor_m for cell in model.cells))))
    return {'schema': 'td-hybrid-river-local-vertical-frame-v8', 'datum_m': datum, 'datum_policy': 'floor_minimum_actual_section_floor_m', 'computation': 'one_common_local_frame_before_inverse_friction_flux_and_Jacobian', 'output': 'global_head_equals_datum_plus_local_head', 'source_geometry_unchanged': True, 'tiny_flux_deadband': False}

def translate_section(section, datum):
    original = section.original if isinstance(section, FastSection) else section
    translated = _i25_replace(original, pieces=tuple(((width, (coefficients[0] - datum, coefficients[1], coefficients[2])) for width, coefficients in original.pieces)), polygon=tuple(((point[0], point[1] - datum) for point in original.polygon)))
    return FastSection(translated)

def local_model(model, frame=None):
    frame = numerical_frame(model) if frame is None else frame
    if frame != numerical_frame(model):
        raise ValueError('common datum must be derived from actual source section floors')
    translated = _i25_replace(model, cells=tuple((_i25_replace(cell, section=translate_section(cell.section, frame['datum_m'])) for cell in model.cells)))
    translated.validate()
    return translated

def local_experiment(experiment, frame):
    return _i25_replace(experiment, initial_heads_m=tuple((head - frame['datum_m'] for head in experiment.initial_heads_m)), tailwater_head_m=experiment.tailwater_head_m - frame['datum_m'])

def global_diagnostics(record, datum):
    if isinstance(record, list):
        return [global_diagnostics(value, datum) for value in record]
    if not isinstance(record, dict):
        return record
    restored = {}
    for key, value in record.items():
        if key in ABSOLUTE_HEIGHT_FIELDS and value is not None:
            restored['local_' + key] = value
            restored[key] = datum + value
        else:
            restored[key] = global_diagnostics(value, datum)
    return restored

def global_progress(progress, frame):
    result = global_diagnostics(progress, frame['datum_m'])
    result.update(numerical_frame=frame, absolute_height_coordinate_frame='global', local_height_coordinate_frame='common_local_vertical_frame', raw_state_coordinate_frame='origin_inventory_and_integrated_ledgers_not_height')
    return result

def local_frame_run_experiment(model, experiment, crown_transition_width_m=0.0, diagnostic_stop_s=None):
    model.validate()
    experiment.validate(model)
    frame = numerical_frame(model)
    translated = local_model(model, frame)
    parameters = local_experiment(experiment, frame)
    try:
        result = radau_run_experiment(translated, parameters, crown_transition_width_m, diagnostic_stop_s)
    except ValueError as error:
        if not hasattr(error, 'progress'):
            raise
        progress = global_progress(error.progress, frame)
        progress['local_solver_parameters'] = _i25_asdict(parameters)
        progress['global_parameters'] = _i25_asdict(experiment)
        failure_type = _diagnostic_stop if getattr(error, 'diagnostic_stop', False) else _execution_failure
        raise failure_type(str(error), progress) from error
    result.update(schema=LOCAL_FRAME_SCHEMA, numerical_version=LOCAL_FRAME_NUMERICAL_VERSION, integration=LOCAL_FRAME_INTEGRATION, numerical_frame=frame, local_solver_parameters=_i25_asdict(parameters), local_tailwater_head_m=parameters.tailwater_head_m, local_hydraulic_head_m=result['hydraulic_head_m'], execution_progress=global_progress(result['execution_progress'], frame))
    for field in ('hydraulic_head_m', 'open_channel_stage_m', 'pressurized_head_m'):
        result[field] = [[frame['datum_m'] + value if value is not None else None for value in row] for row in result[field]]
    result['saved_section_diagnostics'] = global_diagnostics(result['saved_section_diagnostics'], frame['datum_m'])
    result['absolute_height_coordinate_frame'] = 'global'
    return result
