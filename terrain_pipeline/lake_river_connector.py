"""Explicit, bounded engineering quasi-steady lake/river water geometry."""

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
import zipfile

import numpy as np

from terrain_pipeline.surface_lake_network import validate_surface_lake_network
from terrain_pipeline.surface_lake_network import surface_lake_network_hash
from terrain_pipeline.surface_network_prepare import validate_surface_network
from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.lake_routing import lake_routing_hash
from terrain_pipeline.metric_channel_plan import ChannelRecipe, _validate_route
from terrain_pipeline.surface_network_consumer import _payload, _proof_gate


VERSION = "lake-river-connector-v1"
MAX_BYTES = 64 * 1024 * 1024
MAX_CELLS = 250000
TOL = 1e-9
LIMITATION = (
    "Engineering quasi-steady geometry only; no rating-curve modification, "
    "dynamic or backwater solver, free-fall velocity, river storage or propagation. "
    "No additional injection or lake storage. The source joint remains "
    "diagnostic_not_publishable; this does not publish the whole surface system. "
    "Tailwater >= spill is rejected under the current engineering contract."
)


def _number(value, name, positive=False):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number))
            or not math.isfinite(value) or (positive and value <= 0)):
        raise ValueError(f"invalid finite metre/resource parameter: {name}")


def _freeze(value):
    if isinstance(value, np.ndarray):
        contiguous = np.ascontiguousarray(value)
        return np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)
    if isinstance(value, Mapping):
        return MappingProxyType({name: _freeze(child) for name, child in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(child) for child in value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def _thaw(value):
    if isinstance(value, Mapping):
        return {name: _thaw(child) for name, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(child) for child in value]
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _array_hash(array):
    digest = hashlib.sha256(array.dtype.str.encode("ascii"))
    digest.update(_json(list(array.shape)).encode("ascii"))
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _tree(value, arrays):
    if isinstance(value, np.ndarray):
        identity = _array_hash(value)
        name = "array_" + identity
        arrays[name] = value
        return {"$array": name, "dtype": value.dtype.str, "shape": list(value.shape), "sha256": identity}
    if isinstance(value, Mapping):
        return {name: _tree(child, arrays) for name, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_tree(child, arrays) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def lake_river_connector_hash(result):
    """Integrity digest, not a semantic certificate or issuer signature."""
    payload = {name: value for name, value in result.items() if name != "identity_sha256"}
    return hashlib.sha256(_json(_tree(payload, {})).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConnectorCorridor:
    surface_m: np.ndarray
    valid_mask: np.ndarray
    domain_mask: np.ndarray
    protected_mask: np.ndarray
    origin_x_m: float
    origin_z_m: float
    spacing_x_m: float
    spacing_z_m: float
    vertical_datum: str
    source_identity: str

    def __post_init__(self):
        for name in ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m"):
            _number(getattr(self, name), name, name.startswith("spacing"))
        for name in ("vertical_datum", "source_identity"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError("explicit corridor datum/source required")
        surface = np.asarray(self.surface_m)
        if (surface.ndim != 2 or min(surface.shape) < 2 or surface.size > MAX_CELLS
                or surface.dtype.kind not in "fiu"):
            raise ValueError("bounded 2D numeric corridor required")
        for name in ("valid_mask", "domain_mask", "protected_mask"):
            mask = np.asarray(getattr(self, name))
            if mask.dtype != bool or mask.shape != surface.shape:
                raise ValueError("matching explicit boolean corridor masks required")
            object.__setattr__(self, name, _freeze(mask))
        if np.isinf(surface).any() or not np.isfinite(surface[self.valid_mask]).all():
            raise ValueError("valid source terrain must be finite; unknown may be NaN")
        object.__setattr__(self, "surface_m", _freeze(surface.astype(np.float64)))


@dataclass(frozen=True)
class ConnectorRecipe:
    path_xz_m: tuple
    width_m: tuple
    spill_vertex: int
    max_station_spacing_m: float = .02
    min_width_cells: float = 2.
    min_depth_m: float = .01
    max_depth_m: float = 4.
    max_cut_m: float = .6
    max_cut_volume_m3: float = .1
    max_changed_area_m2: float = .1
    max_stations: int = 2048
    max_triangles: int = 8192
    max_support_tests: int = 200000
    max_retained_bytes: int = MAX_BYTES

    def __post_init__(self):
        path = np.asarray(self.path_xz_m)
        if (path.ndim != 2 or path.shape[1] != 2 or not 3 <= len(path) <= 64
                or path.dtype.kind not in "fiu" or not np.isfinite(path).all()
                or np.any(np.linalg.norm(np.diff(path, axis=0), axis=1) <= 0)):
            raise ValueError("explicit finite nondegenerate bounded metric path required")
        if type(self.spill_vertex) is not int or not 0 < self.spill_vertex < len(path) - 1:
            raise ValueError("spill must be an interior path vertex")
        widths = tuple(self.width_m)
        if len(widths) != len(path):
            raise ValueError("one explicit width per path vertex required")
        for width in widths:
            _number(width, "width_m", True)
        for name in ("max_station_spacing_m", "min_width_cells", "min_depth_m", "max_depth_m"):
            _number(getattr(self, name), name, True)
        if self.min_width_cells < 2 or self.max_depth_m < self.min_depth_m:
            raise ValueError("at least two source intervals across width and ordered depth bounds required")
        for name in ("max_cut_m", "max_cut_volume_m3", "max_changed_area_m2"):
            _number(getattr(self, name), name)
            if getattr(self, name) < 0:
                raise ValueError("nonnegative construction budgets required")
        for name, ceiling in (("max_stations", 4096), ("max_triangles", 16384),
                              ("max_support_tests", 1000000), ("max_retained_bytes", MAX_BYTES)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid bounded connector resource: " + name)
        object.__setattr__(self, "path_xz_m", tuple(tuple(float(value) for value in point) for point in path))
        object.__setattr__(self, "width_m", tuple(float(value) for value in widths))


class _Gate(Exception):
    def __init__(self, code, **evidence):
        self.code = code
        self.evidence = evidence


def _grid(corridor):
    return dict(origin_x_m=corridor.origin_x_m, origin_z_m=corridor.origin_z_m,
                spacing_x_m=corridor.spacing_x_m, spacing_z_m=corridor.spacing_z_m)


def _support(point, grid, shape):
    column = (point[0] - grid["origin_x_m"]) / grid["spacing_x_m"]
    row = (point[1] - grid["origin_z_m"]) / grid["spacing_z_m"]
    if column < -TOL or row < -TOL or column > shape[1] - 1 + TOL or row > shape[0] - 1 + TOL:
        raise _Gate("outside_source_support", point_xz_m=list(point))
    column = min(max(column, 0.), shape[1] - 1.)
    row = min(max(row, 0.), shape[0] - 1.)
    left = min(int(math.floor(column)), shape[1] - 2)
    top = min(int(math.floor(row)), shape[0] - 2)
    dx, dz = column - left, row - top
    if dz <= dx:
        return ((top, left), (top, left + 1), (top + 1, left + 1)), np.array([1 - dx, dx - dz, dz])
    return ((top, left), (top + 1, left + 1), (top + 1, left)), np.array([1 - dz, dx, dz - dx])


def _sample(point, grid, surface, valid, domain, protected, wet=None):
    indices, weights = _support(point, grid, surface.shape)
    for index in indices:
        if not valid[index] or not np.isfinite(surface[index]):
            raise _Gate("unknown_support", grid_zx=list(index))
        if not domain[index]:
            raise _Gate("domain_support", grid_zx=list(index))
        if protected[index]:
            raise _Gate("protected_support", grid_zx=list(index))
        if wet is not None and not wet[index]:
            raise _Gate("dry_splice_support", grid_zx=list(index))
    return float(sum(weight * surface[index] for index, weight in zip(indices, weights)))


def _cross(first, second):
    return float(first[0] * second[1] - first[1] * second[0])


def _clip(polygon, triangle):
    output = [np.asarray(point, dtype=float) for point in polygon]
    for first, second in zip(triangle, np.roll(triangle, -1, axis=0)):
        previous = output
        output = []
        if not previous:
            break
        for begin, end in zip(previous, previous[1:] + previous[:1]):
            begin_side = _cross(second - first, begin - first)
            end_side = _cross(second - first, end - first)
            if begin_side >= 0:
                output.append(begin)
            if (begin_side < 0) != (end_side < 0):
                output.append(begin + (end - begin) * begin_side / (begin_side - end_side))
    return output


def _area(polygon):
    if len(polygon) < 3:
        return 0.
    return abs(sum(_cross(point - polygon[0], following - polygon[0])
                   for point, following in zip(polygon[1:-1], polygon[2:]))) / 2


def _plane_values(points, triangle, heights):
    coefficients = np.linalg.solve(np.column_stack((triangle, np.ones(3))), heights)
    return np.column_stack((points, np.ones(len(points)))) @ coefficients


def _source_facets(triangle, grid, shape):
    minimum = triangle.min(axis=0)
    maximum = triangle.max(axis=0)
    origin = np.array([grid["origin_x_m"], grid["origin_z_m"]])
    spacing = np.array([grid["spacing_x_m"], grid["spacing_z_m"]])
    lower = np.floor((minimum - origin) / spacing).astype(int)
    upper = np.floor((maximum - origin) / spacing).astype(int)
    if np.any(minimum < origin - TOL) or np.any(maximum > origin + spacing * (np.array(shape[::-1]) - 1) + TOL):
        raise _Gate("outside_source_support")
    for row in range(max(0, lower[1]), min(shape[0] - 2, upper[1]) + 1):
        for column in range(max(0, lower[0]), min(shape[1] - 2, upper[0]) + 1):
            for indices in (((row, column), (row, column + 1), (row + 1, column + 1)),
                            ((row, column), (row + 1, column + 1), (row + 1, column))):
                facet = np.array([origin + spacing * np.array([index[1], index[0]]) for index in indices])
                yield indices, facet


def _stations(recipe):
    path = np.asarray(recipe.path_xz_m)
    points, widths, distance, spill = [], [], [], None
    total = 0.
    for segment, (first, second) in enumerate(zip(path[:-1], path[1:])):
        length = float(np.linalg.norm(second - first))
        count = math.ceil(length / recipe.max_station_spacing_m - TOL)
        if len(points) + count + 1 > recipe.max_stations:
            raise _Gate("station_resource_exhausted")
        for offset in range(count):
            fraction = offset / count
            points.append(first + fraction * (second - first))
            widths.append(recipe.width_m[segment] * (1 - fraction) + recipe.width_m[segment + 1] * fraction)
            distance.append(total + fraction * length)
        if segment + 1 == recipe.spill_vertex:
            spill = len(points)
        total += length
    points.append(path[-1])
    widths.append(recipe.width_m[-1])
    distance.append(total)
    return np.asarray(points), np.asarray(widths), np.asarray(distance), spill


def _path_crossing(path):
    for first in range(len(path) - 1):
        for second in range(first + 2, len(path) - 1):
            start, end = path[first:first + 2]
            other_start, other_end = path[second:second + 2]
            direction, other_direction = end - start, other_end - other_start
            denominator = _cross(direction, other_direction)
            if abs(denominator) < TOL:
                if abs(_cross(other_start - start, direction)) < TOL:
                    fractions = [np.dot(point - start, direction) / np.dot(direction, direction)
                                 for point in (other_start, other_end)]
                    if max(min(fractions), 0) <= min(max(fractions), 1):
                        raise _Gate("path_selfintersection")
            else:
                fraction = _cross(other_start - start, other_direction) / denominator
                other_fraction = _cross(other_start - start, direction) / denominator
                if 0 <= fraction <= 1 and 0 <= other_fraction <= 1:
                    raise _Gate("path_selfintersection")


def _corridor_input(corridor):
    return {name: getattr(corridor, name) for name in ConnectorCorridor.__dataclass_fields__}


def _recipe_input(recipe):
    return {name: getattr(recipe, name) for name in ConnectorRecipe.__dataclass_fields__}


def _input_gate(joint, corridor, recipe):
    lake = joint["inputs"]["lake_inputs"]
    seam = joint["inputs"]["seam"]
    spill_index = tuple(lake["legal_spill_grid_zx"])
    spill = (lake["origin_x_m"] + spill_index[1] * lake["spacing_x_m"],
             lake["origin_z_m"] + spill_index[0] * lake["spacing_z_m"])
    if corridor.vertical_datum != lake["vertical_datum"] or corridor.vertical_datum != seam["downstream_vertical_datum"]:
        raise ValueError("connector datum mismatch")
    if tuple(recipe.path_xz_m[recipe.spill_vertex]) != spill:
        raise ValueError("path must pass through the actual legal spill exactly")
    if tuple(recipe.path_xz_m[-1]) != (seam["world_x_m"], seam["world_z_m"]):
        raise ValueError("path must terminate at the actual fine injection exactly")
    arrays = {}
    tree = _tree(dict(source_joint=joint, corridor=_corridor_input(corridor), recipe=_recipe_input(recipe)), arrays)
    if sum(array.nbytes + 256 for array in arrays.values()) + len(_json(tree).encode("utf-8")) * 4 > recipe.max_retained_bytes:
        raise ValueError("connector input retained byte ceiling")


def _ribbon_gate(vertices, triangles, recipe, counter):
    if len(triangles) > recipe.max_triangles:
        raise _Gate("triangle_resource_exhausted")
    for indices in triangles:
        if _cross(vertices[indices[1], :2] - vertices[indices[0], :2],
                  vertices[indices[2], :2] - vertices[indices[0], :2]) <= 0:
            raise _Gate("degenerate_or_folded_ribbon")
    minimum = vertices[triangles, :2].min(axis=1)
    maximum = vertices[triangles, :2].max(axis=1)
    order = np.argsort(minimum[:, 0], kind="stable")
    for position, index in enumerate(order):
        for other in order[position + 1:]:
            if minimum[other, 0] >= maximum[index, 0]:
                break
            counter[0] += 1
            if counter[0] > recipe.max_support_tests:
                raise _Gate("support_resource_exhausted", support_tests=counter[0])
            if maximum[index, 1] <= minimum[other, 1] or maximum[other, 1] <= minimum[index, 1]:
                continue
            if _area(_clip(vertices[triangles[index], :2], vertices[triangles[other], :2])) > TOL * TOL:
                raise _Gate("ribbon_selfintersection")


def _geometry_gate(joint, corridor, recipe, step, widths):
    lake = joint["inputs"]["lake_inputs"]
    spill_stage = float(lake["height_m"][tuple(lake["legal_spill_grid_zx"])])
    if step["injection_stage_m"] >= spill_stage:
        raise _Gate("tailwater_at_or_above_spill")
    _path_crossing(np.asarray(recipe.path_xz_m))
    if widths.min() + TOL < recipe.min_width_cells * max(corridor.spacing_x_m, corridor.spacing_z_m):
        raise _Gate("width_resolution_failed")
    if recipe.max_station_spacing_m > min(corridor.spacing_x_m, corridor.spacing_z_m) * 2:
        raise _Gate("longitudinal_resolution_failed")


def _splice_gate(points, bed, water, binding):
    for prefix, cross_section, heights in (("lake", points[0], bed[0]), ("river", points[-1], bed[-1])):
        samples = binding[prefix + "_xz_m"]
        direction = cross_section[-1] - cross_section[0]
        fractions = (samples - cross_section[0]) @ direction / np.dot(direction, direction)
        expected_bed = np.interp(fractions, (0., .5, 1.), heights)
        expected_water = np.interp(fractions, (0., .5, 1.), water[0 if prefix == "lake" else -1])
        if (not np.allclose(expected_bed, binding[prefix + "_bed_m"], rtol=0, atol=TOL)
                or not np.allclose(expected_water, binding[prefix + "_water_m"], rtol=0, atol=TOL)):
            raise _Gate("full_cross_section_splice_mismatch")


def _positive_polygon(points, values):
    output = []
    for begin, end, first, second in zip(points, np.roll(points, -1, axis=0), values, np.roll(values, -1)):
        if first > 0:
            output.append(begin)
        if (first > 0) != (second > 0):
            output.append(begin + (end - begin) * first / (first - second))
    return np.asarray(output)


def _integral(points, triangle, values):
    positive = _positive_polygon(np.asarray(points), _plane_values(points, triangle, values))
    volume, area = 0., 0.
    if len(positive) >= 3:
        for index in range(1, len(positive) - 1):
            piece = positive[[0, index, index + 1]]
            piece_area = _area(piece)
            volume += piece_area * float(np.mean(_plane_values(piece, triangle, values)))
            area += piece_area
    return volume, area


def _line_proof(first, second, grid, surface, valid, domain, protected, wet=None):
    _sample(first, grid, surface, valid, domain, protected, wet)
    _sample(second, grid, surface, valid, domain, protected, wet)
    fractions = {0., 1.}
    for axis, origin_name, spacing_name in ((0, "origin_x_m", "spacing_x_m"),
                                            (1, "origin_z_m", "spacing_z_m")):
        delta = second[axis] - first[axis]
        if delta != 0:
            lower, upper = sorted((first[axis], second[axis]))
            for node in range(math.floor((lower - grid[origin_name]) / grid[spacing_name]),
                              math.ceil((upper - grid[origin_name]) / grid[spacing_name]) + 1):
                fraction = (grid[origin_name] + node * grid[spacing_name] - first[axis]) / delta
                if 0 < fraction < 1:
                    fractions.add(float(fraction))
    ordered = sorted(fractions)
    for begin, end in zip(ordered[:-1], ordered[1:]):
        midpoint = first + (second - first) * ((begin + end) / 2)
        indices, weights = _support(midpoint, grid, surface.shape)
        left = min(index[1] for index in indices)
        top = min(index[0] for index in indices)
        start_dx = (first[0] - grid["origin_x_m"]) / grid["spacing_x_m"] - left
        start_dz = (first[1] - grid["origin_z_m"]) / grid["spacing_z_m"] - top
        slope = (second[0] - first[0]) / grid["spacing_x_m"] - (second[1] - first[1]) / grid["spacing_z_m"]
        if slope != 0:
            fraction = (start_dz - start_dx) / slope
            if begin < fraction < end:
                fractions.add(float(fraction))
    ordered = sorted(fractions)
    samples = sorted(set(ordered + [(begin + end) / 2 for begin, end in zip(ordered[:-1], ordered[1:])]))
    points = np.array([first + fraction * (second - first) for fraction in samples])
    values = [_sample(point, grid, surface, valid, domain, protected, wet) for point in points]
    return points, np.asarray(values)


def _end_binding(points, corridor, joint, step, stage):
    inputs = joint["inputs"]
    lake = inputs["lake_inputs"]
    height = lake["height_m"]
    wet = lake["basin_mask"] & (height < stage)
    lake_grid = {name: lake[name] for name in _grid(corridor)}
    first = points[0]
    lake_points, lake_bed = _line_proof(first[0], first[-1], lake_grid, height,
        np.isfinite(height), lake["domain_mask"], lake["protected_mask"], wet)
    for point, expected in zip(lake_points, lake_bed):
        actual = _sample(point, _grid(corridor), corridor.surface_m, corridor.valid_mask,
                         corridor.domain_mask, corridor.protected_mask)
        if abs(actual - expected) > TOL:
            raise _Gate("lake_source_splice_mismatch", actual_bed_m=actual, lake_bed_m=float(expected))
    fine = inputs["fine"]
    river = step["recovery"]["surface"]["arrays"]
    river_grid = {name: fine[name] for name in _grid(corridor)}
    last = points[-1]
    river_points, source_bed = _line_proof(last[0], last[-1], river_grid, river["source_surface_m"],
        np.isfinite(river["source_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
    for point, expected in zip(river_points, source_bed):
        actual = _sample(point, _grid(corridor), corridor.surface_m, corridor.valid_mask,
                         corridor.domain_mask, corridor.protected_mask)
        if abs(actual - expected) > TOL:
            raise _Gate("river_source_splice_mismatch", actual_bed_m=actual, river_H0_m=float(expected))
    actual_bed = np.array([_sample(point, river_grid, river["final_surface_m"],
        np.isfinite(river["final_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in river_points])
    actual_water = np.array([_sample(point, river_grid, river["water_surface_m"],
        np.isfinite(river["water_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in river_points])
    return dict(lake_xz_m=lake_points, lake_bed_m=lake_bed, lake_water_m=np.full(len(lake_points), stage),
                river_xz_m=river_points, river_bed_m=actual_bed, river_water_m=actual_water,
                source_representation="fixed NW-SE diagonal piecewise-linear node facets; full line facet proof",
                contact="shared positive-depth wet cross-section, not proximity of two endpoints")


def _audit_triangles(vertices, bed, triangles, corridor, recipe, counter):
    grid = _grid(corridor)
    min_depth, max_depth, max_cut = math.inf, 0., 0.
    cut_volume, changed_area, covered_area = 0., 0., 0.
    support = set()
    for indices in triangles:
        triangle = vertices[indices, :2]
        water_heights = vertices[indices, 2]
        bed_heights = bed[indices]
        total_area = _area(triangle)
        if total_area <= TOL * TOL:
            raise _Gate("degenerate_or_folded_ribbon")
        facet_area = 0.
        for source_indices, facet in _source_facets(triangle, grid, corridor.surface_m.shape):
            counter[0] += 1
            if counter[0] > recipe.max_support_tests:
                raise _Gate("support_resource_exhausted", support_tests=counter[0])
            clipped = _clip(triangle, facet)
            area = _area(clipped)
            if area <= TOL * TOL:
                continue
            source_heights = []
            for source_index in source_indices:
                if not corridor.valid_mask[source_index]:
                    raise _Gate("unknown_support", grid_zx=list(source_index))
                if not corridor.domain_mask[source_index]:
                    raise _Gate("domain_support", grid_zx=list(source_index))
                if corridor.protected_mask[source_index]:
                    raise _Gate("protected_support", grid_zx=list(source_index))
                source_heights.append(corridor.surface_m[source_index])
                support.add(source_index)
            source = _plane_values(clipped, facet, source_heights)
            actual_bed = _plane_values(clipped, triangle, bed_heights)
            water = _plane_values(clipped, triangle, water_heights)
            depths, cuts = water - actual_bed, source - actual_bed
            min_depth = min(min_depth, float(depths.min()))
            max_depth = max(max_depth, float(depths.max()))
            max_cut = max(max_cut, float(cuts.max()))
            if depths.min() < recipe.min_depth_m - TOL:
                raise _Gate("clearance_failed", actual_min_depth_m=float(depths.min()))
            if depths.max() > recipe.max_depth_m + TOL:
                raise _Gate("depth_failed", actual_max_depth_m=float(depths.max()))
            if cuts.min() < -TOL:
                raise _Gate("bed_raise_failed", raise_m=float(-cuts.min()), triangle_xz_m=triangle.tolist(),
                            clipped_xz_m=np.asarray(clipped).tolist(), source_m=source.tolist(), bed_m=actual_bed.tolist())
            if cuts.max() > recipe.max_cut_m + TOL:
                raise _Gate("cut_depth_budget", actual_cut_m=float(cuts.max()))
            source_at_triangle = _plane_values(triangle, facet, source_heights)
            volume, positive_area = _integral(clipped, triangle, source_at_triangle - bed_heights)
            cut_volume += volume
            changed_area += positive_area
            facet_area += area
        if abs(facet_area - total_area) > TOL:
            raise _Gate("incomplete_triangle_coverage")
        covered_area += facet_area
    if cut_volume > recipe.max_cut_volume_m3 + TOL:
        raise _Gate("cut_volume_budget", actual_cut_volume_m3=cut_volume)
    if changed_area > recipe.max_changed_area_m2 + TOL:
        raise _Gate("changed_area_budget", actual_changed_area_m2=changed_area)
    return dict(min_depth_m=min_depth, max_depth_m=max_depth, max_cut_m=max_cut,
                cut_volume_m3=cut_volume, changed_area_m2=changed_area, wet_area_m2=covered_area,
                source_support_grid_zx=np.array(sorted(support), dtype=np.int64))


def _geometry(joint, corridor, recipe, step, counter):
    lake = joint["inputs"]["lake_inputs"]
    stage = float(joint["committed_lake_arrays"]["stage_m"][step["index"] + 1])
    spill_stage = float(lake["height_m"][tuple(lake["legal_spill_grid_zx"])])
    centers, widths, stations, spill = _stations(recipe)
    _geometry_gate(joint, corridor, recipe, step, widths)
    tangents = np.empty_like(centers)
    tangents[0] = centers[1] - centers[0]
    tangents[-1] = centers[-1] - centers[-2]
    tangents[1:-1] = centers[2:] - centers[:-2]
    lengths = np.linalg.norm(tangents, axis=1)
    if np.any(lengths <= TOL):
        raise _Gate("path_fold")
    normals = np.column_stack((-tangents[:, 1], tangents[:, 0])) / lengths[:, None]
    points = centers[:, None, :] + normals[:, None, :] * widths[:, None, None] * np.array([-.5, 0., .5])[None, :, None]
    binding = _end_binding(points, corridor, joint, step, stage)
    grid = _grid(corridor)
    source = np.array([[_sample(point, grid, corridor.surface_m, corridor.valid_mask,
                                corridor.domain_mask, corridor.protected_mask) for point in cross_section]
                       for cross_section in points])
    fine = joint["inputs"]["fine"]
    river_grid = {name: fine[name] for name in grid}
    river = step["recovery"]["surface"]["arrays"]
    end_bed = np.array([_sample(point, river_grid, river["final_surface_m"],
        np.isfinite(river["final_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in points[-1]])
    end_water = np.array([_sample(point, river_grid, river["water_surface_m"],
        np.isfinite(river["water_surface_m"]), fine["domain_mask"], fine["protected_mask"], river["wet_mask"])
        for point in points[-1]])
    if np.any(end_water >= spill_stage):
        raise _Gate("tailwater_at_or_above_spill")
    fraction = np.maximum(stations - stations[spill], 0.) / (stations[-1] - stations[spill])
    terminal_cut = source[-1] - end_bed
    if np.any(terminal_cut < -TOL):
        raise _Gate("bed_raise_failed")
    bed = source - fraction[:, None] * terminal_cut[None, :]
    water = stage + fraction[:, None] * (end_water[None, :] - stage)
    bed[-1] = end_bed
    water[-1] = end_water
    if np.any(np.diff(bed[spill:], axis=0) > TOL):
        raise _Gate("post_spill_bed_uphill")
    if np.any(np.diff(water[spill:], axis=0) > TOL):
        raise _Gate("post_spill_water_uphill")
    vertices = np.column_stack((points.reshape(-1, 2), water.ravel()))
    triangles = []
    for station in range(len(centers) - 1):
        for lateral in range(2):
            first = station * 3 + lateral
            triangles.extend(((first, first + 3, first + 4), (first, first + 4, first + 1)))
    triangles = np.array(triangles, dtype=np.int64)
    _ribbon_gate(vertices, triangles, recipe, counter)
    _splice_gate(points, bed, water, binding)
    audit = _audit_triangles(vertices, bed.ravel(), triangles, corridor, recipe, counter)
    return dict(geometry_type="terrain_following_excavated_water_ribbon", station_m=stations,
        station_xz_m=centers, station_width_m=widths, station_source_bed_m=source[:, 1],
        station_bed_m=bed[:, 1], station_water_m=water[:, 1], spill_station=spill,
        water_vertices_xzw_m=vertices, bed_vertices_m=bed.ravel(), triangles=triangles,
        attachment=binding, audit=audit,
        construction="actual source bed minus linear post-spill taper of actual per-step river terminal cut")


def _evaluate(joint, corridor, recipe):
    _input_gate(joint, corridor, recipe)
    inputs = dict(corridor=_corridor_input(corridor), recipe=_recipe_input(recipe))
    arrays = {}
    tree = _tree(dict(source_joint=joint, inputs=inputs), arrays)
    initial_bytes = sum(array.nbytes + 256 for array in arrays.values()) + len(_json(tree).encode("utf-8")) * 4
    if initial_bytes > recipe.max_retained_bytes:
        raise ValueError("connector source input exceeds retained byte ceiling")
    counter = [0]
    steps = []
    diagnostic = dict(code="geometry_feasible", failed_step=None, evidence={})
    for step in joint["trace"]:
        if not step["committed"]:
            raise ValueError("only a complete transfer_feasible committed joint may be connected")
        ledger = joint["ledger"][step["index"]]
        outflow = step["lake_outflow_m3_s"]
        if outflow != ledger["lake_outflow_m3_s"]:
            raise ValueError("actual per-step Q/ledger mismatch")
        row = dict(index=step["index"], source_joint_identity=joint["identity_sha256"],
            lake_prefix_identity=step["lake_prefix_identity_sha256"], actual_outflow_m3_s=outflow,
            river_identity=None if step["recovery"] is None else step["recovery"]["identity_sha256"],
            ledger_recheck=ledger, added_injection_m3_s=0., connector_storage_accounted_m3=0.,
            geometry=None, status="closed_dry")
        steps.append(row)
        if outflow == 0:
            continue
        try:
            row["geometry"] = _geometry(joint, corridor, recipe, step, counter)
            row["status"] = "connected"
        except _Gate as error:
            row["status"] = "diagnostic"
            diagnostic = dict(code=error.code, failed_step=step["index"], evidence=error.evidence)
            break
    result = dict(algorithm_version=VERSION, format_version=1, status="engineering_quasi_steady_geometry",
        geometry_feasible=diagnostic["code"] == "geometry_feasible", source_joint=joint, inputs=inputs,
        steps=steps, diagnostic=diagnostic, summary=dict(connected_steps=sum(row["status"] == "connected" for row in steps),
            closed_steps=sum(row["status"] == "closed_dry" for row in steps), support_tests=counter[0],
            source_joint_publishable=False, limitation=LIMITATION))
    arrays = {}
    encoded = _tree(result, arrays)
    retained = sum(array.nbytes + 256 for array in arrays.values()) + len(_json(encoded).encode("utf-8")) * 4
    if retained > recipe.max_retained_bytes:
        raise ValueError("connector result exceeds retained byte ceiling")
    result["identity_sha256"] = lake_river_connector_hash(result)
    return _freeze(result)


def evaluate_lake_river_connector(source_joint, corridor, recipe):
    """Explicit preparation; fully validate the supplied joint before any geometry."""
    if not isinstance(corridor, ConnectorCorridor) or not isinstance(recipe, ConnectorRecipe):
        raise ValueError("explicit ConnectorCorridor and ConnectorRecipe required")
    arrays = {}
    tree = _tree(source_joint, arrays)
    if (sum(array.nbytes + 256 for array in arrays.values()) + len(_json(tree).encode("utf-8")) * 4
            + corridor.surface_m.nbytes * 4 > recipe.max_retained_bytes):
        raise ValueError("connector input byte preflight before source replay")
    try:
        joint = validate_surface_lake_network(_thaw(source_joint))
    except (KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError("invalid source joint") from error
    if not joint["transfer_feasible"]:
        raise ValueError("source joint must be fully transfer_feasible")
    _static_joint(joint)
    return _evaluate(joint, corridor, recipe)


def replay_lake_river_connector(result):
    """Explicit opt-in algorithm replay, including upstream lake/recovery computation."""
    try:
        if result["identity_sha256"] != lake_river_connector_hash(result):
            raise ValueError("connector integrity mismatch")
        replay = evaluate_lake_river_connector(result["source_joint"],
            ConnectorCorridor(**result["inputs"]["corridor"]), ConnectorRecipe(**result["inputs"]["recipe"]))
        if _json(_tree(result, {})) != _json(_tree(replay, {})):
            raise ValueError("connector semantic geometry replay mismatch")
        return replay
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError("malformed connector") from error


def query_lake_river_connector(result, step_index):
    """Read the already prepared immutable step; never validate, generate or recompute."""
    if type(step_index) is not int or not 0 <= step_index < len(result["steps"]):
        raise ValueError("invalid prepared connector step index")
    if not isinstance(result, MappingProxyType):
        raise ValueError("query requires an immutable prepared or loaded connector")
    return result["steps"][step_index]


def _static_plan(plan):
    parameters = plan["identity"]["parameters"]
    arrays = plan["arrays"]
    if digest(_thaw(plan["identity"])) != plan["identity_sha256"]:
        raise ValueError("source plan identity mismatch")
    ChannelRecipe(**{name: parameters[name] for name in ChannelRecipe.__dataclass_fields__})
    for name, field in (("source_height_m", "source_height_sha256"),
                        ("discharge_m3_s", "source_discharge_sha256"),
                        ("receiver", "source_route_sha256"), ("order", "source_order_sha256"),
                        ("outlet_mask", "source_outlet_sha256")):
        if array_hash(arrays[name]) != parameters[field]:
            raise ValueError("source plan H0/Q/route identity mismatch")
    shape = arrays["source_height_m"].shape
    _validate_route(arrays["receiver"], arrays["order"], shape, arrays["outlet_mask"])
    discharge = arrays["discharge_m3_s"].ravel()
    if not np.isfinite(discharge).all() or np.any(discharge < 0):
        raise ValueError("invalid source plan Q")
    local = discharge.copy()
    donors = np.flatnonzero(arrays["receiver"] >= 0)
    np.subtract.at(local, arrays["receiver"][donors], discharge[donors])
    if np.any(local < -TOL):
        raise ValueError("nonconservative source plan Q")
    return local


def _static_joint(joint):
    if (joint["identity_sha256"] != surface_lake_network_hash(_thaw(joint))
            or joint["transfer_feasible"] is not True or joint["status"] != "diagnostic_not_publishable"):
        raise ValueError("invalid complete source joint identity/status")
    inputs = joint["inputs"]
    lake_inputs = inputs["lake_inputs"]
    lake = joint["independent_lake_diagnostic"]
    if lake["identity_sha256"] != lake_routing_hash(_thaw(lake)) or not lake["scenario_feasible"]:
        raise ValueError("invalid source lake identity/status")
    lake_arrays = lake["arrays"]
    for name in ("height_m", "basin_mask", "domain_mask", "protected_mask"):
        if not np.array_equal(lake_arrays[name], lake_inputs[name]):
            raise ValueError("source lake input mismatch")
    recipe = lake_inputs["recipe"]
    if _json(_thaw(lake["input"]["recipe"])) != _json(_thaw(recipe)):
        raise ValueError("source lake recipe mismatch")
    for name in ("spacing_x_m", "spacing_z_m", "origin_x_m", "origin_z_m", "vertical_datum", "source_identity"):
        if lake["input"][name] != lake_inputs[name]:
            raise ValueError("source lake coordinate/source mismatch")
    stages = lake_arrays["stage_m"]
    area = lake_inputs["spacing_x_m"] * lake_inputs["spacing_z_m"]
    volumes = np.array([np.maximum(stage - lake_inputs["height_m"][lake_inputs["basin_mask"]], 0.).sum() * area
                        for stage in stages])
    if not np.allclose(volumes, lake_arrays["storage_m3"], rtol=0, atol=TOL):
        raise ValueError("source lake actual storage mismatch")
    for name in ("stage_m", "storage_m3"):
        if not np.array_equal(joint["committed_lake_arrays"][name], lake_arrays[name]):
            raise ValueError("committed source lake timeline mismatch")
    local = _static_plan(inputs["plan"])
    params = inputs["plan"]["identity"]["parameters"]
    shape = inputs["plan"]["arrays"]["source_height_m"].shape
    outlet_stage = np.asarray(inputs["outlet_stage_m"])
    if (outlet_stage.shape != shape or outlet_stage.dtype.kind not in "fiu"
            or not np.isfinite(outlet_stage).all()
            or not np.all(outlet_stage == outlet_stage.flat[0])):
        raise ValueError("source outlet stages are not the declared uniform grid input")
    seam = inputs["seam"]
    column = round((seam["world_x_m"] - params["origin_x_m"]) / params["spacing_x_m"])
    row = round((seam["world_z_m"] - params["origin_z_m"]) / params["spacing_z_m"])
    injection = row * shape[1] + column
    if not 0 <= injection < len(local):
        raise ValueError("invalid source injection")
    if len(joint["trace"]) != len(recipe["inflow_m3_s"]) or len(joint["ledger"]) != len(joint["trace"]):
        raise ValueError("incomplete source joint")
    attempts, fine_work = 0, 0
    for index, step in enumerate(joint["trace"]):
        if not step["committed"] or step["index"] != index:
            raise ValueError("source step not committed")
        outflow = step["lake_outflow_m3_s"]
        expected_q = float(np.interp(stages[index + 1], recipe["rating_stage_m"], recipe["rating_outflow_m3_s"]))
        if abs(outflow - expected_q) > TOL or outflow != lake_arrays["step_outflow_m3_s"][index]:
            raise ValueError("source step Q differs from actual lake stage/rating")
        injected = local.copy()
        injected[injection] += outflow
        if (not np.allclose(step["original_local_inflow_m3_s"].ravel(), local, rtol=0, atol=TOL)
                or not np.allclose(step["injected_local_inflow_m3_s"].ravel(), injected, rtol=0, atol=TOL)
                or not np.allclose(_static_plan(step["recomputed_plan"]), injected, rtol=0, atol=TOL)):
            raise ValueError("source actual injection differs or is duplicated")
        final = step["recomputed_plan"]
        recovery = step["recovery"]
        if recovery is not None:
            if not recovery["accepted"]:
                raise ValueError("source river not accepted")
            proof = _thaw(recovery)
            validate_surface_network(proof["surface"])
            _proof_gate(proof, _payload(proof))
            recovery_inputs = recovery["inputs"]
            for name in ("coarse_domain", "coarse_protected", "fine", "section_recipe", "stage_recipe",
                         "inundation_recipe", "budget", "network_recipe", "valley_recipe", "reroute_recipe"):
                if _json(_tree(inputs[name], {})) != _json(_tree(recovery_inputs[name], {})):
                    raise ValueError("source recovery call input mismatch: " + name)
            if _json(_tree(recovery_inputs["plan"], {})) != _json(_tree(step["recomputed_plan"], {})):
                raise ValueError("source recovery did not use the actual step plan")
            active_outlets = step["recomputed_plan"]["arrays"]["channel_mask"] & inputs["plan"]["arrays"]["outlet_mask"]
            if not np.array_equal(recovery_inputs["outlet_stage_m"], inputs["outlet_stage_m"][active_outlets]):
                raise ValueError("source recovery actual outlet stages differ")
            expected_recipe = dict(inputs["recovery_recipe"])
            expected_recipe["max_attempts"] = min(expected_recipe["max_attempts"], inputs["recipe"]["max_total_attempts"] - attempts)
            expected_recipe["max_total_fine_cells"] = min(expected_recipe["max_total_fine_cells"], inputs["recipe"]["max_total_fine_work"] - fine_work)
            if _json(expected_recipe) != _json(_thaw(recovery_inputs["recovery_recipe"])):
                raise ValueError("source recovery aggregate resource call mismatch")
            attempts += len(recovery["attempts"])
            fine_work += recovery["summary"]["total_fine_cells_evaluated"]
            final = recovery["final_plan"]
            _static_plan(final)
            if array_hash(final["arrays"]["discharge_m3_s"]) != array_hash(step["recomputed_plan"]["arrays"]["discharge_m3_s"]):
                raise ValueError("source recovery Q changed")
            surface = recovery["surface"]["arrays"]
            fine = inputs["fine"]
            fine_row = round((seam["world_z_m"] - fine["origin_z_m"]) / fine["spacing_z_m"])
            fine_column = round((seam["world_x_m"] - fine["origin_x_m"]) / fine["spacing_x_m"])
            if outflow > 0 and (not surface["wet_mask"][fine_row, fine_column]
                    or surface["water_surface_m"][fine_row, fine_column] != step["injection_stage_m"]):
                raise ValueError("source actual injection wet/stage mismatch")
            original_height = inputs["plan"]["arrays"]["source_height_m"]
            ledger_source = recovery["fine_ledger"]
            original_fine = surface["source_surface_m"] if ledger_source is None else ledger_source["arrays"]["source_surface_m"]
            for coarse_row in range(shape[0]):
                for coarse_column in range(shape[1]):
                    world_x = params["origin_x_m"] + coarse_column * params["spacing_x_m"]
                    world_z = params["origin_z_m"] + coarse_row * params["spacing_z_m"]
                    fine_x = round((world_x - fine["origin_x_m"]) / fine["spacing_x_m"])
                    fine_z = round((world_z - fine["origin_z_m"]) / fine["spacing_z_m"])
                    if abs(original_fine[fine_z, fine_x] - original_height[coarse_row, coarse_column]) > TOL:
                        raise ValueError("source actual river H0 differs from original terrain")
        river_outflow = float(final["arrays"]["discharge_m3_s"][final["arrays"]["outlet_mask"]].sum())
        ledger = joint["ledger"][index]
        dt = recipe["dt_s"]
        storage_change = volumes[index + 1] - volumes[index]
        combined = storage_change + dt * river_outflow - dt * (recipe["inflow_m3_s"][index] - recipe["loss_m3_s"][index] + local.sum())
        lake_residual = storage_change - dt * (recipe["inflow_m3_s"][index] - recipe["loss_m3_s"][index] - outflow)
        river_residual = river_outflow - float(local.sum()) - outflow
        allowed_lake = recipe["volume_abs_tolerance_m3"] + recipe["volume_rel_tolerance"] * max(
            volumes[index], volumes[index + 1], dt * recipe["inflow_m3_s"][index], dt * recipe["loss_m3_s"][index], dt * outflow)
        joint_recipe = inputs["recipe"]
        allowed_flow = joint_recipe["discharge_abs_tolerance_m3_s"] + joint_recipe["discharge_rel_tolerance"] * max(
            abs(river_outflow), abs(float(local.sum())), abs(outflow))
        allowed = allowed_lake + dt * allowed_flow
        if (ledger["lake_outflow_m3_s"] != outflow or abs(ledger["downstream_outlet_m3_s"] - river_outflow) > TOL
                or abs(ledger["lake_storage_change_m3"] - storage_change) > TOL
                or abs(combined - ledger["combined_residual_m3"]) > TOL
                or ledger["dt_s"] != dt or ledger["lake_inflow_m3_s"] != recipe["inflow_m3_s"][index]
                or ledger["lake_loss_m3_s"] != recipe["loss_m3_s"][index]
                or abs(ledger["lake_residual_m3"] - lake_residual) > TOL
                or abs(ledger["downstream_residual_m3_s"] - river_residual) > TOL
                or abs(ledger["combined_tolerance_m3"] - allowed) > 1e-13
                or abs(lake_residual) > allowed_lake + 1e-13 or abs(river_residual) > allowed_flow
                or abs(combined) > allowed + 1e-13):
            raise ValueError("source actual conservation ledger mismatch")
    summary = joint["summary"]
    expected_summary = dict(committed_steps=len(joint["trace"]), requested_steps=len(recipe["inflow_m3_s"]),
        committed_final_lake_stage_m=float(stages[-1]), committed_initial_lake_storage_m3=float(volumes[0]),
        committed_final_lake_storage_m3=float(volumes[-1]), total_attempts=attempts, total_fine_work=fine_work,
        total_lake_work=lake_inputs["height_m"].size * (len(joint["trace"]) + len(joint["trace"]) * (len(joint["trace"]) + 1) // 2),
        connector_geometry_generated=False, river_storage_or_propagation_modeled=False)
    for name, field in (("total_lake_inflow_m3", "lake_inflow_m3_s"), ("total_lake_loss_m3", "lake_loss_m3_s"),
                        ("total_lake_outflow_m3", "lake_outflow_m3_s"), ("total_downstream_local_m3", "downstream_local_total_m3_s"),
                        ("total_downstream_outlet_m3", "downstream_outlet_m3_s")):
        expected_summary[name] = math.fsum(ledger["dt_s"] * ledger[field] for ledger in joint["ledger"])
    for name, field in (("total_combined_residual_m3", "combined_residual_m3"),
                        ("total_combined_tolerance_m3", "combined_tolerance_m3")):
        expected_summary[name] = math.fsum(ledger[field] for ledger in joint["ledger"])
    expected_summary["aggregate_combined_residual_m3"] = math.fsum((volumes[-1], -volumes[0],
        expected_summary["total_downstream_outlet_m3"], -expected_summary["total_lake_inflow_m3"],
        expected_summary["total_lake_loss_m3"], -expected_summary["total_downstream_local_m3"]))
    for name, value in expected_summary.items():
        if isinstance(value, float):
            if not math.isclose(summary[name], value, rel_tol=0, abs_tol=TOL):
                raise ValueError("source joint recomputed summary mismatch: " + name)
        elif summary[name] != value:
            raise ValueError("source joint summary mismatch: " + name)
    final_depth = np.where(lake_inputs["basin_mask"], np.maximum(stages[-1] - lake_inputs["height_m"], 0.), 0.)
    committed = joint["committed_lake_arrays"]
    if (not np.array_equal(committed["water_depth_m"], final_depth)
            or not np.array_equal(committed["wet_mask"], final_depth > 0)
            or not np.array_equal(committed["water_surface_m"], np.where(final_depth > 0, stages[-1], np.nan), equal_nan=True)):
        raise ValueError("source committed actual lake wet geometry mismatch")


def _static_geometry(geometry, joint, corridor, recipe, step, counter):
    centers, widths, stations, spill = _stations(recipe)
    _geometry_gate(joint, corridor, recipe, step, widths)
    if (geometry["spill_station"] != spill or geometry["geometry_type"] != "terrain_following_excavated_water_ribbon"
            or geometry["construction"] != "actual source bed minus linear post-spill taper of actual per-step river terminal cut"):
        raise ValueError("connector geometry representation mismatch")
    for name, expected in (("station_xz_m", centers), ("station_width_m", widths), ("station_m", stations)):
        if not np.array_equal(geometry[name], expected):
            raise ValueError("connector station recipe mismatch")
    vertices = geometry["water_vertices_xzw_m"]
    bed = geometry["bed_vertices_m"]
    triangles = geometry["triangles"]
    if (vertices.shape != (len(centers) * 3, 3) or bed.shape != (len(vertices),)
            or not np.isfinite(vertices).all() or not np.isfinite(bed).all()):
        raise ValueError("invalid connector vertices")
    tangents = np.empty_like(centers)
    tangents[0], tangents[-1] = centers[1] - centers[0], centers[-1] - centers[-2]
    tangents[1:-1] = centers[2:] - centers[:-2]
    normals = np.column_stack((-tangents[:, 1], tangents[:, 0])) / np.linalg.norm(tangents, axis=1)[:, None]
    points = centers[:, None, :] + normals[:, None, :] * widths[:, None, None] * np.array([-.5, 0., .5])[None, :, None]
    if not np.array_equal(vertices[:, :2], points.reshape(-1, 2)):
        raise ValueError("connector actual width/position mismatch")
    expected_triangles = []
    for station in range(len(centers) - 1):
        for lateral in range(2):
            first = station * 3 + lateral
            expected_triangles.extend(((first, first + 3, first + 4), (first, first + 4, first + 1)))
    if not np.array_equal(triangles, expected_triangles):
        raise ValueError("connector triangle topology mismatch")
    _ribbon_gate(vertices, triangles, recipe, counter)
    stage = joint["committed_lake_arrays"]["stage_m"][step["index"] + 1]
    binding = _end_binding(points, corridor, joint, step, stage)
    if _json(_tree(binding, {})) != _json(_tree(geometry["attachment"], {})):
        raise ValueError("connector full-width attachment mismatch")
    source = np.array([[_sample(point, _grid(corridor), corridor.surface_m, corridor.valid_mask,
        corridor.domain_mask, corridor.protected_mask) for point in cross_section] for cross_section in points])
    fine = joint["inputs"]["fine"]
    river = step["recovery"]["surface"]["arrays"]
    river_grid = {name: fine[name] for name in _grid(corridor)}
    terminal_bed = np.array([_sample(point, river_grid, river["final_surface_m"], np.isfinite(river["final_surface_m"]),
        fine["domain_mask"], fine["protected_mask"], river["wet_mask"]) for point in points[-1]])
    terminal_water = np.array([_sample(point, river_grid, river["water_surface_m"], np.isfinite(river["water_surface_m"]),
        fine["domain_mask"], fine["protected_mask"], river["wet_mask"]) for point in points[-1]])
    fraction = np.maximum(stations - stations[spill], 0.) / (stations[-1] - stations[spill])
    expected_bed = source - fraction[:, None] * (source[-1] - terminal_bed)[None, :]
    expected_water = stage + fraction[:, None] * (terminal_water[None, :] - stage)
    expected_bed[-1], expected_water[-1] = terminal_bed, terminal_water
    spill_stage = joint["inputs"]["lake_inputs"]["height_m"][tuple(joint["inputs"]["lake_inputs"]["legal_spill_grid_zx"])]
    if np.any(terminal_water >= spill_stage) or np.any(np.diff(expected_water[spill:], axis=0) > TOL):
        raise ValueError("connector tailwater or water uphill")
    _splice_gate(points, expected_bed, expected_water, binding)
    if (not np.array_equal(bed.reshape(-1, 3), expected_bed)
            or not np.array_equal(vertices[:, 2].reshape(-1, 3), expected_water)
            or not np.array_equal(geometry["station_bed_m"], expected_bed[:, 1])
            or not np.array_equal(geometry["station_water_m"], expected_water[:, 1])
            or not np.array_equal(geometry["station_source_bed_m"], source[:, 1])):
        raise ValueError("connector actual bed/water construction mismatch")
    if np.any(np.diff(expected_bed[spill:], axis=0) > TOL):
        raise ValueError("connector post-spill bed uphill")
    audit = _audit_triangles(vertices, bed, triangles, corridor, recipe, counter)
    if _json(_tree(audit, {})) != _json(_tree(geometry["audit"], {})):
        raise ValueError("connector actual geometry budget summary mismatch")


def validate_lake_river_connector(result):
    """Static source, conservation, full-width facet and geometry audit; no prepare/recovery."""
    try:
        if (result["identity_sha256"] != lake_river_connector_hash(result) or result["algorithm_version"] != VERSION
                or result["format_version"] != 1 or result["status"] != "engineering_quasi_steady_geometry"
                or type(result["geometry_feasible"]) is not bool):
            raise ValueError("connector identity mismatch")
        corridor = ConnectorCorridor(**result["inputs"]["corridor"])
        recipe = ConnectorRecipe(**result["inputs"]["recipe"])
        joint = result["source_joint"]
        _input_gate(joint, corridor, recipe)
        _static_joint(joint)
        diagnostic = result["diagnostic"]
        if (set(diagnostic) != {"code", "failed_step", "evidence"} or not isinstance(diagnostic["evidence"], Mapping)
                or not isinstance(diagnostic["code"], str)):
            raise ValueError("invalid connector diagnostic schema")
        failure_codes = {"tailwater_at_or_above_spill", "path_selfintersection", "station_resource_exhausted",
            "width_resolution_failed", "longitudinal_resolution_failed", "path_fold", "outside_source_support",
            "unknown_support", "domain_support", "protected_support", "dry_splice_support", "lake_source_splice_mismatch",
            "river_source_splice_mismatch", "bed_raise_failed", "post_spill_bed_uphill", "post_spill_water_uphill",
            "triangle_resource_exhausted", "support_resource_exhausted", "ribbon_selfintersection",
            "degenerate_or_folded_ribbon", "full_cross_section_splice_mismatch", "clearance_failed", "depth_failed",
            "cut_depth_budget", "incomplete_triangle_coverage", "cut_volume_budget", "changed_area_budget"}
        if not result["geometry_feasible"]:
            if (not result["steps"] or diagnostic["code"] not in failure_codes
                    or type(diagnostic["failed_step"]) is not int or diagnostic["failed_step"] != len(result["steps"]) - 1
                    or result["steps"][-1]["status"] != "diagnostic"):
                raise ValueError("connector diagnostic requires the real retained prefix and terminal failed step")
        counter = [0]
        connected, closed = 0, 0
        for index, row in enumerate(result["steps"]):
            step = joint["trace"][index]
            if (row["index"] != index or row["actual_outflow_m3_s"] != step["lake_outflow_m3_s"]
                    or row["source_joint_identity"] != joint["identity_sha256"]
                    or row["lake_prefix_identity"] != step["lake_prefix_identity_sha256"]
                    or row["river_identity"] != (None if step["recovery"] is None else step["recovery"]["identity_sha256"])
                    or row["added_injection_m3_s"] != 0. or row["connector_storage_accounted_m3"] != 0.
                    or _json(_tree(row["ledger_recheck"], {})) != _json(_tree(joint["ledger"][index], {}))):
                raise ValueError("connector actual Q/identity/conservation mismatch")
            if row["status"] == "connected":
                if row["actual_outflow_m3_s"] <= 0:
                    raise ValueError("zero Q cannot have wet geometry")
                _static_geometry(row["geometry"], joint, corridor, recipe, step, counter)
                connected += 1
            elif row["status"] == "closed_dry":
                if row["actual_outflow_m3_s"] != 0 or row["geometry"] is not None:
                    raise ValueError("closed connector must be dry and zero Q")
                closed += 1
            elif row["status"] != "diagnostic" or row["geometry"] is not None or result["geometry_feasible"]:
                raise ValueError("invalid connector diagnostic")
            elif index != diagnostic["failed_step"] or row["actual_outflow_m3_s"] <= 0:
                raise ValueError("connector failure must be the positive-Q terminal prefix step")
        if (result["summary"]["connected_steps"] != connected or result["summary"]["closed_steps"] != closed
                or result["summary"]["source_joint_publishable"] is not False
                or result["summary"]["limitation"] != LIMITATION
                or (result["geometry_feasible"] and result["summary"]["support_tests"] != counter[0])
                or (result["geometry_feasible"] and len(result["steps"]) != len(joint["trace"]))):
            raise ValueError("connector summary/completeness mismatch")
        if result["geometry_feasible"] and (result["diagnostic"]["code"] != "geometry_feasible"
                or result["diagnostic"]["failed_step"] is not None):
            raise ValueError("connector feasible diagnostic mismatch")
        arrays = {}
        encoded = _tree(result, arrays)
        if sum(array.nbytes + 256 for array in arrays.values()) + len(_json(encoded).encode("utf-8")) * 4 > recipe.max_retained_bytes:
            raise ValueError("connector actual retained-byte ceiling")
        return _freeze(result)
    except _Gate as error:
        raise ValueError("static connector gate: " + error.code) from error
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError, RecursionError) as error:
        raise ValueError("malformed static connector") from error


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate connector JSON key")
        result[name] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite connector JSON constant")


def _preflight(handle):
    if os.fstat(handle.fileno()).st_size > MAX_BYTES:
        raise ValueError("compressed connector archive exceeds resource ceiling")
    with zipfile.ZipFile(handle) as archive:
        entries = archive.infolist()
        names = {entry.filename for entry in entries}
        if (len(entries) > 4096 or len(entries) != len(names) or "manifest.npy" not in names
                or sum(entry.file_size for entry in entries) > MAX_BYTES):
            raise ValueError("connector ZIP duplicate/member/expanded resource ceiling")
        for entry in entries:
            if (entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or "/" in entry.filename or "\\" in entry.filename
                    or not entry.filename.endswith(".npy")):
                raise ValueError("invalid connector ZIP member")
            if entry.filename != "manifest.npy" and (
                    not entry.filename.startswith("array_") or len(entry.filename) != 74
                    or any(character not in "0123456789abcdef" for character in entry.filename[6:-4])):
                raise ValueError("invalid connector array member name")
            with archive.open(entry) as member:
                version = np.lib.format.read_magic(member)
                if version == (1, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(member)
                elif version == (2, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_2_0(member)
                else:
                    raise ValueError("unsupported connector NPY version")
                byte_count = math.prod(shape) * dtype.itemsize
                if (dtype.hasobject or fortran or len(shape) > 2 or dtype.itemsize <= 0
                        or any(type(size) is not int or size < 0 for size in shape)
                        or byte_count > MAX_BYTES or member.tell() + byte_count != entry.file_size):
                    raise ValueError("connector NPY header/payload/resource mismatch")
                if entry.filename == "manifest.npy":
                    if shape != () or dtype.kind != "U" or byte_count > 4 * 1024 * 1024:
                        raise ValueError("invalid bounded connector manifest")
                elif dtype.kind not in "bifu" or math.prod(shape) > 2000000:
                    raise ValueError("invalid bounded connector numeric array")
    handle.seek(0)


def save_lake_river_connector(result, destination):
    """Replay then atomic no-overwrite publication of a self-contained bundle."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.suffix != ".npz":
        raise ValueError("connector requires .npz destination")
    validated = validate_lake_river_connector(result)
    arrays = {}
    tree = _tree(validated, arrays)
    manifest = _json(dict(format_version=1, tree=tree,
        tree_sha256=hashlib.sha256(_json(tree).encode("utf-8")).hexdigest()))
    if (len(manifest) * 4 > 4 * 1024 * 1024 or len(arrays) + 1 > 4096
            or sum(array.nbytes + 256 for array in arrays.values()) + len(manifest) * 4
            > validated["inputs"]["recipe"]["max_retained_bytes"]):
        raise ValueError("connector save exceeds resource ceiling")
    descriptor, temporary = tempfile.mkstemp(prefix=".connector-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez_compressed(handle, manifest=np.asarray(manifest), **arrays)
            handle.flush()
            os.fsync(handle.fileno())
        with open(temporary, "rb") as handle:
            _preflight(handle)
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    return destination


def load_lake_river_connector(source, replay=False):
    """Default static semantic audit; replay=True explicitly opts into upstream computation."""
    try:
        with open(source, "rb") as handle:
            _preflight(handle)
            with np.load(handle, allow_pickle=False) as archive:
                manifest = json.loads(str(archive["manifest"].item()), object_pairs_hook=_unique_object,
                                      parse_constant=_reject_constant)
                if (set(manifest) != {"format_version", "tree", "tree_sha256"}
                        or manifest["format_version"] != 1
                        or hashlib.sha256(_json(manifest["tree"]).encode("utf-8")).hexdigest() != manifest["tree_sha256"]):
                    raise ValueError("connector manifest integrity mismatch")
                used, cache = {"manifest"}, {}

                def decode(value):
                    if isinstance(value, dict) and "$array" in value:
                        if set(value) != {"$array", "dtype", "shape", "sha256"}:
                            raise ValueError("malformed connector array reference")
                        name = value["$array"]
                        if name not in archive.files or name != "array_" + value["sha256"]:
                            raise ValueError("missing connector array binding")
                        used.add(name)
                        if name not in cache:
                            cache[name] = _freeze(archive[name])
                        array = cache[name]
                        if (array.dtype.str != value["dtype"] or list(array.shape) != value["shape"]
                                or _array_hash(array) != value["sha256"]):
                            raise ValueError("connector array integrity mismatch")
                        return array
                    if isinstance(value, dict):
                        return {name: decode(child) for name, child in value.items()}
                    if isinstance(value, list):
                        return [decode(child) for child in value]
                    return value

                result = decode(manifest["tree"])
                if used != set(archive.files):
                    raise ValueError("undeclared connector archive arrays")
        return replay_lake_river_connector(result) if replay else validate_lake_river_connector(result)
    except (OSError, EOFError, KeyError, TypeError, AttributeError, RecursionError,
            zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid connector archive") from error
