"""Shared bounded hydraulic model, section geometry and comparison contracts."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import brentq

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
