"""Bounded finite 1D diffusive storage diagnostics, not momentum/3D CFD."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

SCHEMA = "td-hybrid-river-hydraulics-v1"
OLD_FACE_BUDGET_REMAINING = 2_949_448_968
MAX_CELLS = 64
QUAD_POINTS, QUAD_WEIGHTS = np.polynomial.legendre.leggauss(12)


def positive(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(name + " must be finite and positive")
    return value


def submerged_intervals(coefficients, stage):
    constant, linear, quadratic = coefficients
    polynomial = [quadratic, linear, constant - stage]
    roots = np.roots(np.trim_zeros(polynomial, "f")) if any(polynomial) else []
    knots = [0.0, 1.0] + [float(root.real) for root in roots if abs(root.imag) < 1e-12 and 0 < root.real < 1]
    knots.sort()
    return [(lower, upper) for lower, upper in zip(knots[:-1], knots[1:])
            if constant + linear * ((lower + upper) / 2) + quadratic * ((lower + upper) / 2)**2 < stage]


@dataclass(frozen=True)
class Section:
    kind: str
    pieces: tuple = ()
    polygon: tuple = ()
    pressure_slot_width_m: float = 0.0

    @classmethod
    def from_record(cls, record):
        if record["kind"] == "native_bed":
            if record.get("sidewall_extension") != "explicit_engineering_vertical":
                raise ValueError("surface overflow walls must be explicitly engineered")
            section = cls("native_bed", tuple((float(piece["width_m"]), tuple(float(value) for value in piece["bed_coefficients_m_t012"])) for piece in record["pieces"]))
        elif record["kind"] == "open_polyline":
            if record.get("sidewall_extension") != "explicit_engineering_vertical":
                raise ValueError("surface overflow walls must be explicitly engineered")
            points = record["polyline_transverse_elevation_m"]
            if len(points) < 2 or len(points) > 256:
                raise ValueError("bounded actual open cross section required")
            pieces = []
            for start, end in zip(points[:-1], points[1:]):
                pieces.append((positive(end[0] - start[0], "ordered section width"), (float(start[1]), float(end[1] - start[1]), 0.0)))
            section = cls("open_polyline", tuple(pieces))
        elif record["kind"] == "closed_polygon":
            section = cls("closed_polygon", polygon=tuple(tuple(float(value) for value in point) for point in record["polygon_transverse_elevation_m"]), pressure_slot_width_m=float(record["pressure_slot_width_m"]))
        else:
            raise ValueError("unsupported actual section representation")
        section.validate()
        return section

    def validate(self):
        if self.kind in ("native_bed", "open_polyline"):
            if not self.pieces:
                raise ValueError("empty native section")
            previous = None
            for width, coefficients in self.pieces:
                positive(width, "native width")
                if len(coefficients) != 3 or not all(math.isfinite(value) for value in coefficients):
                    raise ValueError("invalid native polynomial")
                if previous is not None and abs(coefficients[0] - previous) > 1e-8:
                    raise ValueError("native section discontinuity")
                previous = sum(coefficients)
        elif self.kind == "closed_polygon":
            polygon = np.asarray(self.polygon)
            if polygon.ndim != 2 or polygon.shape[1] != 2 or len(polygon) < 3 or len(polygon) > 256 or not np.isfinite(polygon).all():
                raise ValueError("invalid bounded polygon section")
            positive(self.pressure_slot_width_m, "engineered pressure compliance width")
            from shapely.geometry import Polygon
            shape = Polygon(polygon - polygon[0])
            if not shape.is_valid or shape.area <= 0 or len(set(self.polygon)) != len(self.polygon):
                raise ValueError("self-intersecting or degenerate actual section")
        else:
            raise ValueError("unsupported section kind")

    @property
    def floor_m(self):
        if self.kind == "closed_polygon":
            return min(point[1] for point in self.polygon)
        values = []
        for width, (constant, linear, quadratic) in self.pieces:
            values.extend((constant, constant + linear + quadratic))
            if quadratic and 0 < -linear / (2 * quadratic) < 1:
                fraction = -linear / (2 * quadratic)
                values.append(constant + linear * fraction + quadratic * fraction**2)
        return min(values)

    @property
    def crown_m(self):
        return max(point[1] for point in self.polygon) if self.kind == "closed_polygon" else None

    def area_perimeter(self, head_m):
        if not math.isfinite(head_m):
            raise ValueError("nonfinite section head")
        if head_m <= self.floor_m:
            return 0.0, 0.0
        if self.kind in ("native_bed", "open_polyline"):
            area, perimeter = 0.0, 0.0
            for width, coefficients in self.pieces:
                constant, linear, quadratic = coefficients
                for lower, upper in submerged_intervals(coefficients, head_m):
                    area += width * ((head_m - constant) * (upper - lower) - linear * (upper**2 - lower**2) / 2 - quadratic * (upper**3 - lower**3) / 3)
                    fractions = lower + (QUAD_POINTS + 1) * (upper - lower) / 2
                    perimeter += float(np.dot(QUAD_WEIGHTS, np.sqrt(width**2 + (linear + 2 * quadratic * fractions)**2))) * (upper - lower) / 2
            perimeter += max(0.0, head_m - self.pieces[0][1][0]) + max(0.0, head_m - sum(self.pieces[-1][1]))
            return area, perimeter
        crown = self.crown_m
        level = min(head_m, crown)
        clipped, perimeter = [], 0.0
        for start, end in zip(self.polygon, self.polygon[1:] + self.polygon[:1]):
            start_inside, end_inside = start[1] <= level, end[1] <= level
            fraction = None
            if start_inside != end_inside:
                fraction = (level - start[1]) / (end[1] - start[1])
                intersection = (start[0] + fraction * (end[0] - start[0]), level)
                clipped.append(intersection)
            if end_inside:
                clipped.append(end)
            length = math.dist(start, end)
            if start_inside and end_inside:
                perimeter += length
            elif fraction is not None:
                perimeter += length * (fraction if start_inside else 1 - fraction)
        area = 0.0
        if len(clipped) >= 3:
            local = [(point[0] - clipped[0][0], point[1] - clipped[0][1]) for point in clipped]
            area = abs(sum(start[0] * end[1] - end[0] * start[1] for start, end in zip(local, local[1:] + local[:1]))) / 2
        return area + self.pressure_slot_width_m * max(0.0, head_m - crown), perimeter

    def head_for_area(self, area_m2):
        positive(area_m2, "stored section area")
        lower = self.floor_m
        upper = max(lower + 1, self.crown_m or lower + 1)
        while self.area_perimeter(upper)[0] < area_m2:
            upper = lower + 2 * (upper - lower)
            if upper - lower > 1e6:
                raise ValueError("head exceeds bounded model range")
        return brentq(lambda head: self.area_perimeter(head)[0] - area_m2, lower, upper, xtol=1e-10)


@dataclass(frozen=True)
class Cell:
    cell_id: str
    kind: str
    length_m: float
    roughness_manning: float
    section: Section


@dataclass(frozen=True)
class Link:
    link_id: str
    from_cell_id: str
    to_cell_id: str
    length_m: float
    kind: str


@dataclass(frozen=True)
class Model:
    cells: tuple[Cell, ...]
    links: tuple[Link, ...]
    head_regularization_m: float = 1e-4
    donor_regularization_m3: float = 1e-6

    @classmethod
    def from_geometry(cls, geometry):
        cells = tuple(Cell(cell["cell_id"], cell["kind"], positive(cell["length_m"], "cell length"), positive(cell["roughness_manning"], "Manning roughness"), Section.from_record(cell["section"])) for cell in geometry["hydraulic_cells"])
        links = tuple(Link(link["link_id"], link["from_cell_id"], link["to_cell_id"], positive(link["length_m"], "link length"), link["kind"]) for link in geometry["hydraulic_links"])
        model = cls(cells, links)
        model.validate()
        return model

    def validate(self):
        count = len(self.cells)
        if not 3 <= count <= MAX_CELLS or len(self.links) != count - 1:
            raise ValueError("bounded sink/conduit/spring chain required")
        if len(set(cell.cell_id for cell in self.cells)) != count or len(set(link.link_id for link in self.links)) != len(self.links):
            raise ValueError("duplicate hydraulic ownership")
        kinds = [cell.kind for cell in self.cells]
        if kinds[0] != "surface" or kinds[-1] != "surface" or "underground" not in kinds:
            raise ValueError("invalid hydraulic cell types")
        first_underground, last_underground = kinds.index("underground"), count - 1 - kinds[::-1].index("underground")
        if any(kind != "underground" for kind in kinds[first_underground:last_underground + 1]) or any(kind != "surface" for kind in kinds[:first_underground] + kinds[last_underground + 1:]):
            raise ValueError("hydraulic route must have consecutive surface-in/conduit/surface-out cells")
        for cell in self.cells:
            positive(cell.length_m, "cell length")
            positive(cell.roughness_manning, "roughness")
            cell.section.validate()
            if cell.section.kind != ("open_polyline" if cell.kind == "surface" else "closed_polygon"):
                raise ValueError("cell/section physical type mismatch")
        for ordinal, link in enumerate(self.links):
            if (link.from_cell_id, link.to_cell_id) != (self.cells[ordinal].cell_id, self.cells[ordinal + 1].cell_id):
                raise ValueError("links must be actual ordered cell connections")
            pair = kinds[ordinal:ordinal + 2]
            expected = {("surface", "surface"): "surface_half_arm", ("surface", "underground"): "sink_exchange", ("underground", "surface"): "spring_exchange", ("underground", "underground"): "conduit"}[tuple(pair)]
            if link.kind != expected:
                raise ValueError("missing explicit paired surface/conduit exchange")
            positive(link.length_m, "link length")
        positive(self.head_regularization_m, "head regularization")
        positive(self.donor_regularization_m3, "donor regularization")


@dataclass(frozen=True)
class Experiment:
    scenario: str
    duration_s: float
    pulse_duration_s: float
    pulse_q_m3_s: float
    tailwater_head_m: float
    initial_heads_m: tuple[float, ...]
    saved_times_s: tuple[float, ...]
    max_step_s: float = 1.0
    relative_tolerance: float = 1e-7
    absolute_tolerance: float = 1e-9
    max_rhs_evaluations: int = 200000
    max_link_evaluations: int = 12000000
    max_wall_seconds: float = 600.0
    source_arrival_threshold_m3: float = 1e-6

    def validate(self, model):
        if self.scenario not in ("pulse", "reverse_tailwater"):
            raise ValueError("unknown engineering experiment")
        for name in ("duration_s", "max_step_s", "relative_tolerance", "absolute_tolerance", "max_wall_seconds", "source_arrival_threshold_m3"):
            positive(getattr(self, name), name)
        if not 1e-12 <= self.relative_tolerance <= 1e-4 or not 1e-14 <= self.absolute_tolerance <= 1e-6 or self.max_step_s > self.duration_s or self.max_wall_seconds > 600:
            raise ValueError("solver tolerances/step/wall guard exceed authorized range")
        if not math.isfinite(self.tailwater_head_m) or not math.isfinite(self.pulse_q_m3_s) or self.pulse_q_m3_s < 0:
            raise ValueError("invalid prescribed engineering forcing")
        if self.tailwater_head_m <= model.cells[-1].section.floor_m:
            raise ValueError("wet-boundary storage model requires tailwater strictly above outlet floor; dry free outfall is unsupported")
        if self.scenario == "pulse" and not (0 < self.pulse_duration_s < self.duration_s and self.pulse_q_m3_s > 0):
            raise ValueError("pulse requires a finite positive single source")
        if self.scenario == "reverse_tailwater" and (self.pulse_q_m3_s != 0 or self.pulse_duration_s != 0):
            raise ValueError("reverse experiment cannot inject duplicate ordinary source Q")
        if len(self.initial_heads_m) != len(model.cells) or any(not math.isfinite(head) or head <= cell.section.floor_m for head, cell in zip(self.initial_heads_m, model.cells)):
            raise ValueError("explicit positive initial water required; no depth clamp")
        times = np.asarray(self.saved_times_s)
        if len(times) < 2 or len(times) > 4096 or not np.isfinite(times).all() or times[0] != 0 or times[-1] != self.duration_s or np.any(np.diff(times) <= 0):
            raise ValueError("invalid bounded physical observation times")
        if not 1 <= self.max_rhs_evaluations <= 200000 or not 1 <= self.max_link_evaluations <= 12000000:
            raise ValueError("invalid independent 1D work bounds")


def conveyance(cell, head):
    area, perimeter = cell.section.area_perimeter(head)
    return area * (area / perimeter)**(2 / 3) / cell.roughness_manning if area > 0 and perimeter > 0 else 0.0


def signed_flow(conductance, difference, length, regularization):
    return conductance * difference / ((difference**2 + regularization**2)**0.25 * math.sqrt(length))


def run_experiment(model: Model, experiment: Experiment):
    model.validate()
    experiment.validate(model)
    count = len(model.cells)
    initial_volumes = np.array([cell.section.area_perimeter(head)[0] * cell.length_m for cell, head in zip(model.cells, experiment.initial_heads_m)])
    if np.any(initial_volumes <= 0):
        raise ValueError("initial storage must be strictly positive")
    link_count = len(model.links)
    ledger_start = 3 * count
    state = np.zeros(ledger_start + 6 + 3 * link_count)
    state[:count] = np.log(initial_volumes)
    work = {"rhs_evaluations": 0, "link_evaluations": 0, "old_hll_face_work": 0}
    started = time.monotonic()
    import psutil
    process = psutil.Process()
    peak_rss = process.memory_info().rss

    def physical(log_volumes):
        if not np.isfinite(log_volumes).all() or np.any(abs(log_volumes) > 600):
            raise ValueError("storage transform exceeds physical range")
        volumes = np.exp(log_volumes)
        heads = np.array([cell.section.head_for_area(volume / cell.length_m) for cell, volume in zip(model.cells, volumes)])
        if any(head <= cell.section.floor_m for cell, head in zip(model.cells, heads)):
            raise ValueError("positive storage is below representable section depth; no floor clamp")
        capacities = np.array([conveyance(cell, head) for cell, head in zip(model.cells, heads)])
        return volumes, heads, capacities

    def rhs_for(source_q):
        def rhs(seconds, current):
            nonlocal peak_rss
            work["rhs_evaluations"] += 1
            work["link_evaluations"] += link_count + 1
            if work["rhs_evaluations"] > experiment.max_rhs_evaluations or work["link_evaluations"] > experiment.max_link_evaluations or time.monotonic() - started > experiment.max_wall_seconds:
                raise ValueError("independent 1D work/time bound exceeded")
            if work["rhs_evaluations"] % 32 == 1:
                peak_rss = max(peak_rss, process.memory_info().rss)
                if peak_rss > 1024**3:
                    raise ValueError("1GiB hydraulic RSS limit exceeded")
            volumes, heads, capacities = physical(current[:count])
            concentrations = current[count:3 * count].reshape(2, count) / volumes
            volume_rates = np.zeros(count)
            tracer_rates = np.zeros((2, count))
            derivative = np.zeros_like(current)
            for ordinal, link in enumerate(model.links):
                flow = signed_flow(min(capacities[ordinal:ordinal + 2]), heads[ordinal] - heads[ordinal + 1], link.length_m, model.head_regularization_m)
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
            boundary_capacity = min(capacities[-1], conveyance(model.cells[-1], experiment.tailwater_head_m))
            outlet_flow = signed_flow(boundary_capacity, heads[-1] - experiment.tailwater_head_m, model.cells[-1].length_m / 2, model.head_regularization_m)
            if outlet_flow >= 0:
                outlet_flow *= volumes[-1] / (volumes[-1] + model.donor_regularization_m3)
                boundary_tracer = outlet_flow * concentrations[:, -1]
                derivative[ledger_start + 1] = outlet_flow
                derivative[ledger_start + 3] = boundary_tracer[0]
                derivative[ledger_start + 5] = boundary_tracer[1]
            else:
                boundary_tracer = np.array([0.0, outlet_flow])
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
    if experiment.scenario == "pulse":
        breaks.insert(1, experiment.pulse_duration_s)
    observations = []
    integration_segments = []
    saved_times = np.asarray(experiment.saved_times_s)
    for lower, upper in zip(breaks[:-1], breaks[1:]):
        source_q = experiment.pulse_q_m3_s if experiment.scenario == "pulse" and lower < experiment.pulse_duration_s else 0.0
        solution = solve_ivp(rhs_for(source_q), (lower, upper), state, method="Radau", dense_output=True,
                             max_step=experiment.max_step_s, rtol=experiment.relative_tolerance, atol=experiment.absolute_tolerance)
        if not solution.success:
            raise ValueError("Radau failed: " + solution.message)
        steps = np.diff(solution.t)
        integration_segments.append({"start_s": lower, "end_s": upper, "accepted_steps": len(steps),
                                     "min_adaptive_step_s": float(steps.min()), "max_adaptive_step_s": float(steps.max()),
                                     "nfev": solution.nfev, "njev": solution.njev, "nlu": solution.nlu})
        selected = saved_times[(saved_times >= lower) & (saved_times <= upper)]
        for seconds in selected:
            if observations and observations[-1][0] == seconds:
                continue
            observations.append((float(seconds), solution.sol(seconds)))
        state = solution.y[:, -1]
    rows = np.array([current for seconds, current in observations])
    volumes = np.exp(rows[:, :count])
    masses = rows[:, count:3 * count].reshape(-1, 2, count)
    if not np.isfinite(rows).all() or np.any(masses < 0) or np.any(masses.sum(axis=1) > volumes + experiment.absolute_tolerance * 100):
        raise ValueError("strict saved tracer positivity/composition failed; no output clamp")
    ledgers = rows[:, ledger_start:ledger_start + 6]
    residual_water = volumes.sum(axis=1) - initial_volumes.sum() - ledgers[:, 0] - ledgers[:, 2] + ledgers[:, 1]
    residual_source = masses[:, 0].sum(axis=1) - ledgers[:, 0] + ledgers[:, 3]
    residual_tailwater = masses[:, 1].sum(axis=1) - ledgers[:, 4] + ledgers[:, 5]
    threshold = max(1e-7, experiment.relative_tolerance * max(1.0, initial_volumes.sum() + ledgers[-1, 0] + ledgers[-1, 2]) * 100)
    if max(np.max(abs(values)) for values in (residual_water, residual_source, residual_tailwater)) > threshold:
        raise ValueError("water/tracer conservation gate failed")
    heads = np.array([physical(row[:count])[1] for row in rows])
    stages, pressure = [], []
    for head_row in heads:
        stages.append([float(head) if cell.kind == "surface" or head <= cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
        pressure.append([float(head) if cell.kind == "underground" and head > cell.section.crown_m else None for cell, head in zip(model.cells, head_row)])
    arrival = [seconds for (seconds, current), mass in zip(observations, masses[:, 0, -1]) if mass >= experiment.source_arrival_threshold_m3]
    sink_link_index = next(ordinal for ordinal, link in enumerate(model.links) if link.kind == "sink_exchange")
    reverse_transfer = -float(state[ledger_start + 6 + sink_link_index])
    return {"schema": SCHEMA, "status": "diagnostic_completed", "model": "finite_1d_diffusive_storage_signed_manning_Radau",
            "pressure_model": "explicit_engineered_Preissmann_slot_compliance_not_waterhammer",
            "scenario": experiment.scenario, "cell_ids": [cell.cell_id for cell in model.cells],
            "link_ids": [link.link_id for link in model.links], "times_s": [seconds for seconds, current in observations],
            "water_volume_m3": volumes.tolist(), "source_tracer_mass_m3": masses[:, 0].tolist(),
            "tailwater_tracer_mass_m3": masses[:, 1].tolist(), "open_channel_stage_m": stages,
            "pressurized_head_m": pressure, "hydraulic_head_m": heads.tolist(),
            "initial_untraced_water_m3": initial_volumes.tolist(),
            "ledger_columns": ["source_in_m3", "outlet_water_out_m3", "tailwater_water_in_m3", "source_tracer_out_m3", "tailwater_tracer_in_m3", "tailwater_tracer_out_m3"],
            "boundary_ledger_m3": ledgers.tolist(), "paired_link_water_integral_m3": rows[:, ledger_start + 6:ledger_start + 6 + link_count].tolist(),
            "paired_link_source_integral_m3": rows[:, ledger_start + 6 + link_count:ledger_start + 6 + 2 * link_count].tolist(),
            "paired_link_tailwater_integral_m3": rows[:, ledger_start + 6 + 2 * link_count:].tolist(),
            "max_water_residual_m3": float(np.max(abs(residual_water))), "max_source_residual_m3": float(np.max(abs(residual_source))),
            "max_tailwater_residual_m3": float(np.max(abs(residual_tailwater))), "conservation_gate_m3": threshold,
            "source_arrival_threshold_m3": experiment.source_arrival_threshold_m3, "source_arrival_time_s": arrival[0] if arrival else None,
            "arrival_semantics": "threshold_source_tracer_arrival_in_diffusive_storage_not_wave_speed",
            "source_reached_spring": bool(arrival), "source_reached_engineered_outlet": bool(ledgers[-1, 3] >= experiment.source_arrival_threshold_m3),
            "reverse_reached_sink": bool(reverse_transfer > experiment.source_arrival_threshold_m3 and masses[-1, 1, 0] >= experiment.source_arrival_threshold_m3),
            "boundary_condition_kind": "engineering_prescribed_tailwater_and_single_pulse_not_naturaloutlet",
            "boundary_scope": "positively_wet_prescribed_tailwater_only_no_dry_free_outfall",
            "integration_segments": integration_segments,
            "model_parameters": {"head_regularization_m": model.head_regularization_m, "donor_regularization_m3": model.donor_regularization_m3},
            "no_duplicate_cumulative_Q": True, "natural_outlet_certified": False, "full_network_verified": False,
            "finite_speed_front_verified": False, "three_dimensional_flow_solved": False,
            "work": {**work, "old_hll_face_budget_remaining_unchanged": OLD_FACE_BUDGET_REMAINING,
                     "actual_peak_rss_bytes": max(peak_rss, process.memory_info().rss), "max_rss_bytes": 1024**3,
                     "wall_seconds": time.monotonic() - started}}


def compare_refinement(coarse, fine, volume_absolute_tolerance_m3=1e-4, head_absolute_tolerance_m=1e-3, volume_relative_tolerance=0.01):
    if coarse["times_s"] != fine["times_s"] or coarse["cell_ids"] != fine["cell_ids"] or coarse["scenario"] != fine["scenario"]:
        raise ValueError("refinement requires the same physical experiment and observation times")
    positive(volume_absolute_tolerance_m3, "refinement volume tolerance")
    positive(head_absolute_tolerance_m, "refinement head tolerance")
    if head_absolute_tolerance_m > 1e-3 or not 0 < volume_relative_tolerance <= 0.01:
        raise ValueError("refinement cannot relax the 1mm/1percent accuracy contract")
    volume_error = float(np.max(abs(np.asarray(coarse["water_volume_m3"]) - np.asarray(fine["water_volume_m3"]))))
    volume_relative_error = float(np.max(abs(np.asarray(coarse["water_volume_m3"]) - np.asarray(fine["water_volume_m3"])) / np.asarray(fine["water_volume_m3"])))
    head_error = float(np.max(abs(np.asarray(coarse["hydraulic_head_m"]) - np.asarray(fine["hydraulic_head_m"]))))
    tracer_error = max(float(np.max(abs(np.asarray(coarse[key]) - np.asarray(fine[key])))) for key in ("source_tracer_mass_m3", "tailwater_tracer_mass_m3", "boundary_ledger_m3"))
    return {"status": "passed" if volume_error <= volume_absolute_tolerance_m3 and volume_relative_error <= volume_relative_tolerance and tracer_error <= volume_absolute_tolerance_m3 and head_error <= head_absolute_tolerance_m else "refused",
            "scope": "Radau_adaptive_tolerance_and_max_step_refinement_not_explicit_0.005s_certification",
            "max_volume_difference_m3": volume_error, "max_head_difference_m": head_error, "max_tracer_ledger_difference_m3": tracer_error,
            "max_relative_volume_difference": volume_relative_error, "volume_relative_tolerance": volume_relative_tolerance,
            "volume_absolute_tolerance_m3": volume_absolute_tolerance_m3, "head_absolute_tolerance_m": head_absolute_tolerance_m}
