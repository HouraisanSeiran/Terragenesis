"""Strict consumer for saved polygon slices, including owned holes."""

import math
from fractions import Fraction

from shapely.geometry import GeometryCollection, LinearRing, Polygon
from shapely.ops import unary_union


AREA_TOLERANCE_M2 = 1e-8


def _number(value, label):
    if type(value) not in (int, float):
        raise ValueError(label + ": nonnumeric or boolean value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(label + ": nonfinite value")
    return result


def _ring(values, label):
    if not isinstance(values, list) or len(values) < 3:
        raise ValueError(label + ": ring has fewer than three points")
    points = []
    for point in values:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(label + ": invalid point")
        point = tuple(_number(value, label + " coordinate") for value in point)
        points.append(point)
    ring = LinearRing(points)
    if not ring.is_valid or ring.is_empty or ring.length == 0:
        raise ValueError(label + ": invalid ring")
    return points


def _exact_signed_area(values):
    points = [(Fraction.from_float(point[0]), Fraction.from_float(point[1])) for point in values]
    return sum((first[0] * second[1] - second[0] * first[1]
                for first, second in zip(points, points[1:] + points[:1])), Fraction(0)) / 2


def consume_saved_slice(record):
    """Return the exact saved polygonal domain without dropping hole rings.

    This adapter does not repair, buffer, snap, or fill a domain. Zero-area
    contact fields remain diagnostics and are never promoted to area.
    """
    if not isinstance(record, dict):
        raise ValueError("saved slice must be an object")
    exteriors = record.get("polygons_uv_m")
    holes_by_polygon = record.get("holes_uv_m")
    if not isinstance(exteriors, list) or not isinstance(holes_by_polygon, list):
        raise ValueError("saved slice missing polygon/hole arrays")
    if len(exteriors) != len(holes_by_polygon):
        raise ValueError("saved slice hole ownership mismatch")
    polygons = []
    for ordinal, (exterior, holes) in enumerate(zip(exteriors, holes_by_polygon)):
        outer = _ring(exterior, "polygon " + str(ordinal) + " exterior")
        if not isinstance(holes, list):
            raise ValueError("polygon " + str(ordinal) + ": holes must be a list")
        inner = [_ring(hole, "polygon " + str(ordinal) + " hole " + str(index))
                 for index, hole in enumerate(holes)]
        exterior_only = Polygon(outer)
        exact_outer_area = _exact_signed_area(outer)
        if exact_outer_area == 0:
            raise ValueError("zero-area saved slice exterior")
        if not math.isfinite(exterior_only.area) or exterior_only.area <= 0:
            raise ValueError("exact nonzero exterior has zero display area")
        if not exterior_only.is_valid or exterior_only.is_empty or exterior_only.area <= 0:
            raise ValueError("invalid saved slice exterior")
        polygon = Polygon(outer, inner)
        exact_polygon_area = exact_outer_area - sum((_exact_signed_area(hole) for hole in inner), Fraction(0))
        if exact_polygon_area == 0:
            raise ValueError("zero-area saved slice polygon or hole topology")
        if not math.isfinite(polygon.area) or polygon.area <= 0:
            raise ValueError("exact nonzero polygon has zero display area")
        if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
            raise ValueError("invalid saved slice polygon or hole topology")
        if any(not exterior_only.contains(Polygon(hole).representative_point()) for hole in inner):
            raise ValueError("saved hole is outside its owning exterior")
        polygons.append(polygon)
    domain = unary_union(polygons) if polygons else GeometryCollection()
    if not domain.is_empty and domain.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("saved slice polygon components are nonpolygonal")
    for ordinal, first in enumerate(polygons):
        for other_ordinal, second in enumerate(polygons[ordinal + 1:], ordinal + 1):
            overlap = first.intersection(second).area
            if not math.isfinite(overlap) or overlap > AREA_TOLERANCE_M2:
                raise ValueError("overlapping saved slice components: "
                                 + str(ordinal) + "," + str(other_ordinal))
    if not math.isfinite(domain.area):
        raise ValueError("saved slice domain area is nonfinite")
    expected = record.get("area_m2")
    if expected is not None and not math.isfinite(_number(expected, "saved slice area")):
        raise ValueError("saved slice area is nonfinite")
    if expected is not None and abs(float(expected) - domain.area) > AREA_TOLERANCE_M2:
        raise ValueError("saved slice area does not match owned-hole domain")
    return domain


def describe_saved_slice(record):
    domain = consume_saved_slice(record)
    areas = []
    for exterior, holes in zip(record["polygons_uv_m"], record["holes_uv_m"]):
        polygon = Polygon(_ring(exterior, "polygon exterior"),
                          [_ring(hole, "polygon hole") for hole in holes])
        areas.append(polygon.area)
    return {"polygon_count": len(record["polygons_uv_m"]),
            "hole_count": sum(len(holes) for holes in record["holes_uv_m"]),
            "area_m2": domain.area, "geometry_type": domain.geom_type,
            "empty_domain": domain.is_empty,
            "positive_area_sliver_polygon_count": sum(0 < area <= AREA_TOLERANCE_M2 for area in areas),
            "hole_ownership": [len(holes) for holes in record["holes_uv_m"]],
            "contacts_kept_diagnostic_only": True}
