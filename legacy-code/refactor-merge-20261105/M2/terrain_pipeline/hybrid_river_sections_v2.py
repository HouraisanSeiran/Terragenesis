"""Cached exact linear-boundary sections for the frozen storage solver."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
import math

from scipy.optimize import brentq

from terrain_pipeline.hybrid_river_hydraulics_common import Section, positive

SCHEMA = "td-hybrid-river-fast-sections-v2"


@dataclass(frozen=True)
class HeightBand:
    lower_m: float
    area_at_lower_m2: float
    width_at_lower_m: float
    width_slope: float
    perimeter_at_lower_m: float
    perimeter_slope: float

    def area_perimeter(self, head_m):
        delta = head_m - self.lower_m
        return (self.area_at_lower_m2 + delta * (self.width_at_lower_m + 0.5 * self.width_slope * delta),
                self.perimeter_at_lower_m + self.perimeter_slope * delta)


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
    return math.fsum(contributions)


def _edge_perimeter(edges, lower, midpoint):
    values, slopes = [], []
    for start, end in edges:
        length = math.dist(start, end)
        bottom, top = sorted((start[1], end[1]))
        if lower >= top:
            values.append(length)
        elif lower > bottom:
            values.append(length * (lower - bottom) / (top - bottom))
        if bottom < midpoint < top:
            slopes.append(length / (top - bottom))
    return math.fsum(values), math.fsum(slopes)


def _open_width(pieces, height, midpoint):
    spans = []
    for width, coefficients in pieces:
        bottom, top = sorted((coefficients[0], sum(coefficients)))
        if midpoint > top:
            spans.append(width)
        elif bottom < midpoint < top:
            spans.append(width * (height - bottom) / (top - bottom))
    return math.fsum(spans)


def _compile(section):
    if section.kind == "native_bed":
        return (), (), (), ()
    floor = section.floor_m
    if section.kind == "closed_polygon":
        origin_x = section.polygon[0][0]
        polygon = tuple((point[0] - origin_x, point[1] - floor) for point in section.polygon)
        edges = tuple(zip(polygon, polygon[1:] + polygon[:1]))
        local = polygon
        signed_area = math.fsum(start[0] * end[1] - end[0] * start[1] for start, end in zip(local, local[1:] + local[:1])) / 2
        orientation = 1 if signed_area > 0 else -1
        levels = tuple(sorted(set(point[1] for point in polygon)))
    else:
        pieces = tuple((width, (coefficients[0] - floor, sum(coefficients) - coefficients[0], 0.0)) for width, coefficients in section.pieces)
        levels = tuple(sorted(set(value for width, coefficients in pieces for value in (coefficients[0], sum(coefficients)))))
        edges = tuple(((0.0, coefficients[0]), (width, sum(coefficients))) for width, coefficients in pieces)
    bands, area_knots = [], [0.0]
    for lower, upper in zip(levels[:-1], levels[1:]):
        midpoint = lower + (upper - lower) / 2
        if section.kind == "closed_polygon":
            lower_width = _polygon_width(edges, lower, midpoint, orientation)
            upper_width = _polygon_width(edges, upper, midpoint, orientation)
        else:
            lower_width = _open_width(pieces, lower, midpoint)
            upper_width = _open_width(pieces, upper, midpoint)
        if lower_width < 0 or upper_width < 0:
            raise ValueError("cached section has negative submerged width")
        perimeter, perimeter_slope = _edge_perimeter(edges, lower, midpoint)
        if section.kind == "open_polyline":
            ends = (pieces[0][1][0], sum(pieces[-1][1]))
            perimeter += math.fsum(max(0.0, lower - end) for end in ends)
            perimeter_slope += sum(midpoint > end for end in ends)
        band = HeightBand(floor + lower, area_knots[-1], lower_width, (upper_width - lower_width) / (upper - lower), perimeter, perimeter_slope)
        bands.append(band)
        area_knots.append(area_knots[-1] + (upper - lower) * (lower_width + upper_width) / 2)
    lower = levels[-1]
    perimeter, perimeter_slope = _edge_perimeter(edges, lower, lower + 1)
    if section.kind == "closed_polygon":
        width = section.pressure_slot_width_m
    else:
        width = math.fsum(piece[0] for piece in section.pieces)
        perimeter += max(0.0, lower - pieces[0][1][0]) + max(0.0, lower - sum(pieces[-1][1]))
        perimeter_slope += 2
    bands.append(HeightBand(floor + lower, area_knots[-1], width, 0.0, perimeter, perimeter_slope))
    absolute_levels = tuple(floor + level for level in levels)
    point_perimeters = tuple(section.area_perimeter(level)[1] for level in absolute_levels)
    return absolute_levels, tuple(area_knots), tuple(bands), point_perimeters


@dataclass(frozen=True)
class FastSection:
    original: Section
    levels_m: tuple = ()
    area_knots_m2: tuple = ()
    bands: tuple = ()
    point_perimeters_m: tuple = ()

    def __init__(self, original):
        original.validate()
        if original.kind == "open_polyline" and any(piece[1][2] != 0 for piece in original.pieces):
            raise ValueError("open polyline cannot contain quadratic geometry")
        levels, areas, bands, point_perimeters = _compile(original)
        object.__setattr__(self, "original", original)
        object.__setattr__(self, "levels_m", levels)
        object.__setattr__(self, "area_knots_m2", areas)
        object.__setattr__(self, "bands", bands)
        object.__setattr__(self, "point_perimeters_m", point_perimeters)

    @classmethod
    def from_record(cls, record):
        return cls(Section.from_record(record))

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
        return self.levels_m[-1] if self.kind == "closed_polygon" else None

    def validate(self):
        return None

    def area_perimeter(self, head_m):
        if not math.isfinite(head_m):
            raise ValueError("nonfinite section head")
        if not self.bands:
            return self.original.area_perimeter(head_m)
        if head_m <= self.floor_m:
            return 0.0, 0.0
        ordinal = bisect_right(self.levels_m, head_m) - 1
        if head_m == self.levels_m[ordinal]:
            return self.area_knots_m2[ordinal], self.point_perimeters_m[ordinal]
        return self.bands[ordinal].area_perimeter(head_m)

    def head_for_area(self, area_m2):
        area = positive(area_m2, "stored section area")
        if not self.bands:
            return self.original.head_for_area(area)
        ordinal = bisect_right(self.area_knots_m2, area) - 1
        band = self.bands[ordinal]
        difference = area - band.area_at_lower_m2
        if difference == 0:
            return band.lower_m
        if band.width_slope == 0:
            delta = difference / band.width_at_lower_m
        else:
            discriminant = band.width_at_lower_m**2 + 2 * band.width_slope * difference
            if discriminant >= 0:
                delta = 2 * difference / (band.width_at_lower_m + math.sqrt(discriminant))
            else:
                delta = -1.0
            span = self.levels_m[ordinal + 1] - band.lower_m
            if not 0 <= delta <= span:
                delta = brentq(lambda offset: offset * (band.width_at_lower_m + 0.5 * band.width_slope * offset) - difference, 0, span, xtol=1e-10)
        head = band.lower_m + delta
        if not math.isfinite(head) or head - self.floor_m > 1e6:
            raise ValueError("head exceeds bounded model range")
        return head


def accelerate_model(model):
    accelerated = replace(model, cells=tuple(replace(cell, section=FastSection(cell.section)) for cell in model.cells))
    accelerated.validate()
    return accelerated
