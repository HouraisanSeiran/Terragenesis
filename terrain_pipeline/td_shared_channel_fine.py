"""Sparse fine sampling and exact polygon material integration of saved cut fans."""

from collections import defaultdict
import math

import numpy as np

from terrain_pipeline import channel_geometry as source
from terrain_pipeline.td_fine_bed_raster import LEDGER_KEYS
from terrain_pipeline.td_ported_network_composition import check_memory

SCHEMA = "td-shared-channel-fine-v1"
MAX_CELLS = 2_000_000
MAX_BYTES = 64 * 1024**2
MAX_RSS = 1024**3
MAX_TILES = 16384
SPACING_M = .175
TILE_CELLS = 64
PARAMETERS = {"spacing_m": SPACING_M, "tile_cells": TILE_CELLS, "max_cells": MAX_CELLS,
    "max_cut_m": 4., "max_tiles": MAX_TILES, "max_json_bytes": MAX_BYTES, "max_rss_bytes": MAX_RSS,
    "function_difference_tolerance_m": 1e-9, "integral_absolute_tolerance": 1e-8,
    "integral_relative_tolerance": 1e-9}
PARAMETERS_IDENTITY_SHA256 = source._record_identity(PARAMETERS)
POLICY = {"schema": SCHEMA,
    "source": "unchanged_original_native_bilinear_height",
    "bed": "only_accepted_task14_saved_source_minus_affine_cut_fans",
    "grid": "native_origin_fixed_spacing_0.175m_rows_z_columns_x_sparse_unique_integer_cells",
    "budget": "exact_positive_area_intersection_unique_cells_preflight_all_or_none",
    "cut_evaluation": "saved_affine_fan_via_congruent_nonnegative_vertex_convex_interpolation_exact_support_endpoints_no_clamp",
    "material": "actual_fan_intersection_cell_polygon_affine_cut_area_integral",
    "outside_center": "unchanged_source_even_if_cell_has_partial_material_coverage",
    "rock": "all_excavated_rock_exported_zero_fill_zero_sediment_conversion",
    "hydraulics": "not_generated_no_solver_no_old_carrier_acceptance"}
POLICY_IDENTITY_SHA256 = source._record_identity(POLICY)
FLAGS = {"fine_generated": True, "hydraulic_ready": False, "hydraulic_solved": False,
    "material_budget_verified": False, "full_network_verified": False,
    "natural_outlet_certified": False, "old_source_changed": False, "old_fine_changed": False}


class BudgetExceeded(ValueError):
    pass


def seal(record):
    record.pop("identity_sha256", None)
    return source._seal(record)


def material_ledger(cut_volume):
    return {key: cut_volume if key in ("cut_rock_m3", "exported_excavated_rock_m3") else 0.
        for key in LEDGER_KEYS}


def compact_node_fans(record):
    if record["status"] != "candidate" or record["rejection_reasons"]:
        raise ValueError("only accepted candidate node functions can be rasterized")
    result = []
    for function in record["source_functions"]:
        source._check_identity(function)
        if function["status"] != "candidate" or function["rejection_reasons"]:
            raise ValueError("refused source function cannot contribute fine")
        for fan in function["fans"]:
            vertices = np.asarray(fan["vertices_xz_m"], float)
            depths = np.asarray(fan["depth_at_vertices_m"], float)
            coefficients = np.asarray(fan["depth_coefficients_m_1xz"], float)
            origin = np.asarray(fan["depth_origin_xz_m"], float)
            if (vertices.shape != (3, 2) or depths.shape != (3,) or coefficients.shape != (3,)
                    or origin.shape != (2,) or not all(np.isfinite(value).all() for value in (vertices, depths, coefficients, origin))):
                raise ValueError("invalid saved affine fan")
            if np.any(depths < 0.) or np.any(depths > 4.):
                raise ValueError("strict saved fan cut depth invalid")
            expected = coefficients[0] + (vertices - origin) @ coefficients[1:]
            if np.max(np.abs(expected - depths)) > 1e-9:
                raise ValueError("saved affine coefficients differ from support depths")
            area = abs(float(np.linalg.det(np.stack((vertices[1] - vertices[0], vertices[2] - vertices[0]))))) / 2.
            if area <= 1e-14:
                raise ValueError("degenerate saved fan")
            result.append({"fan_key": fan["fan_id"], "fan_id": fan["fan_id"], "node_id": record["node_id"],
                "node_identity_sha256": record["identity_sha256"], "triangle_id": function["triangle_id"],
                "source_function_identity_sha256": function["identity_sha256"],
                "vertices_xz_m": vertices.tolist(), "depth_at_vertices_m": depths.tolist(),
                "depth_origin_xz_m": origin.tolist(), "depth_coefficients_m_1xz": coefficients.tolist(),
                "boundary_segment_id": fan["boundary_segment_id"], "projected_area_m2": area,
                "expected_integrated_cut_m3": area * math.fsum(depths) / 3.})
    return result


def _grid_vertices(fan, grid):
    return (np.asarray(fan["vertices_xz_m"]) - np.asarray(grid["origin_m_xz"])) / grid["spacing_m"]


def _clip(polygon, axis, bound, above):
    result = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        first_inside = first[axis] >= bound if above else first[axis] <= bound
        second_inside = second[axis] >= bound if above else second[axis] <= bound
        if first_inside:
            result.append(first)
        if first_inside != second_inside:
            fraction = (bound - first[axis]) / (second[axis] - first[axis])
            if not 0. <= fraction <= 1.:
                raise ValueError("invalid polygon clipping fraction")
            if fraction == 0.:
                point = list(first)
            elif fraction == 1.:
                point = list(second)
            else:
                point = [(1. - fraction) * left + fraction * right for left, right in zip(first, second)]
            point[axis] = bound
            result.append(point)
    return result


def integrate_polygon(polygon, spacing_m):
    if len(polygon) < 3:
        return 0., 0.
    areas, volumes = [], []
    anchor = polygon[0]
    for first, second in zip(polygon[1:], polygon[2:]):
        cross = ((first[0] - anchor[0]) * (second[1] - anchor[1])
            - (first[1] - anchor[1]) * (second[0] - anchor[0]))
        area = abs(cross) * spacing_m**2 / 2.
        if any(not 0. <= point[2] <= 4. for point in (anchor, first, second)):
            raise ValueError("strict clipped affine cut depth invalid; no clamp")
        areas.append(area)
        volumes.append(area * math.fsum([anchor[2], first[2], second[2]]) / 3.)
    return math.fsum(areas), math.fsum(volumes)


def intersect_cell(fan, row, column, grid, *, vertices_grid=None):
    vertices = _grid_vertices(fan, grid) if vertices_grid is None else vertices_grid
    polygon = [[float(vertex[0] - column), float(vertex[1] - row), depth]
        for vertex, depth in zip(vertices, fan["depth_at_vertices_m"])]
    for axis, bound, above in ((0, 0., True), (0, 1., False), (1, 0., True), (1, 1., False)):
        polygon = _clip(polygon, axis, bound, above) if polygon else []
    area, volume = integrate_polygon(polygon, grid["spacing_m"])
    return polygon, area, volume


def _bounds(fan, grid):
    vertices = _grid_vertices(fan, grid)
    low = np.floor(vertices.min(axis=0)).astype(int)
    high = np.ceil(vertices.max(axis=0)).astype(int) - 1
    return int(low[1]), int(high[1]), int(low[0]), int(high[0])


def plan_tiles(fans, grid, *, max_cells=MAX_CELLS):
    if type(max_cells) is not int or not 1 <= max_cells <= MAX_CELLS:
        raise ValueError("unique cell bound must be from 1 to 2000000")
    if grid["spacing_m"] != SPACING_M or grid["tile_cells"] != TILE_CELLS:
        raise ValueError("fixed .175m grid and 64-cell tiles required")
    masks, tile_fans = {}, defaultdict(set)
    count = visits = 0
    seen_fans = set()
    for fan_index, fan in enumerate(fans):
        if fan["fan_id"] in seen_fans:
            raise ValueError("duplicate saved fan identity")
        seen_fans.add(fan["fan_id"])
        row_low, row_high, column_low, column_high = _bounds(fan, grid)
        vertices_grid = _grid_vertices(fan, grid)
        visits += max(0, row_high - row_low + 1) * max(0, column_high - column_low + 1)
        if visits > MAX_CELLS * 64:
            raise BudgetExceeded("whole_package_fan_cell_visit_budget_exceeded")
        for row in range(row_low, row_high + 1):
            for column in range(column_low, column_high + 1):
                polygon, area, volume = intersect_cell(fan, row, column, grid, vertices_grid=vertices_grid)
                if area <= 0.:
                    continue
                key = (row // TILE_CELLS, column // TILE_CELLS)
                local = row % TILE_CELLS * TILE_CELLS + column % TILE_CELLS
                bit = 1 << local
                mask = masks.get(key, 0)
                if not mask & bit:
                    masks[key] = mask | bit
                    count += 1
                    if count > max_cells:
                        raise BudgetExceeded("whole_package_unique_cell_budget_exceeded")
                tile_fans[key].add(fan_index)
                if len(masks) > MAX_TILES:
                    raise BudgetExceeded("whole_package_tile_budget_exceeded")
        if fan_index % 32 == 0:
            check_memory()
    return {"tile_masks": masks, "tile_fans": {key: sorted(indices) for key, indices in tile_fans.items()},
        "unique_cell_count": count, "bbox_cell_visits": visits}


def _center_cut(fan, center_xz):
    vertices = np.asarray(fan["vertices_xz_m"])
    point = np.asarray(center_xz)
    for vertex, cut in zip(vertices, fan["depth_at_vertices_m"]):
        if np.array_equal(point, vertex):
            return cut
    first, second = vertices[1] - vertices[0], vertices[2] - vertices[0]
    relative = point - vertices[0]
    determinant = first[0] * second[1] - first[1] * second[0]
    weight_first = float((relative[0] * second[1] - relative[1] * second[0]) / determinant)
    weight_second = float((first[0] * relative[1] - first[1] * relative[0]) / determinant)
    weights = [1. - weight_first - weight_second, weight_first, weight_second]
    if min(weights) < 0.:
        return None
    depths = fan["depth_at_vertices_m"]
    cut = depths[0] if depths[0] == depths[1] == depths[2] else math.fsum(weight * depth for weight, depth in zip(weights, depths))
    if not 0. <= cut <= 4.:
        raise ValueError("strict center cut depth invalid; no clamp")
    return cut


def build_tile(fans, plan, tile_key, grid, context, *, fan_parent_identity):
    tile_row, tile_column = tile_key
    row_base, column_base = tile_row * TILE_CELLS, tile_column * TILE_CELLS
    contributions, by_cell = [], defaultdict(list)
    totals = defaultdict(lambda: [[], []])
    for fan_index in plan["tile_fans"][tile_key]:
        fan = fans[fan_index]
        row_low, row_high, column_low, column_high = _bounds(fan, grid)
        vertices_grid = _grid_vertices(fan, grid)
        for row in range(max(row_base, row_low), min(row_base + TILE_CELLS - 1, row_high) + 1):
            for column in range(max(column_base, column_low), min(column_base + TILE_CELLS - 1, column_high) + 1):
                polygon, area, volume = intersect_cell(fan, row, column, grid, vertices_grid=vertices_grid)
                if area <= 0.:
                    continue
                local = (row - row_base) * TILE_CELLS + column - column_base
                origin = grid["origin_m_xz"]
                polygon_world = [[origin[0] + (column + point[0]) * grid["spacing_m"],
                    origin[1] + (row + point[1]) * grid["spacing_m"]] for point in polygon]
                contribution = {"fan_key": fan["fan_key"], "fan_id": fan["fan_id"], "global_row": row, "global_col": column,
                    "local_index": local, "polygon_cell_local_uv_cut_m": polygon,
                    "polygon_xz_m": polygon_world,
                    "coverage_area_m2": area, "integrated_cut_m3": volume}
                contribution_index = len(contributions)
                contributions.append(contribution)
                by_cell[local].append((contribution_index, fan_index))
                totals[fan["fan_id"]][0].append(area)
                totals[fan["fan_id"]][1].append(volume)
    if len(by_cell) != plan["tile_masks"][tile_key].bit_count():
        raise ValueError("preflight and actual affected-cell count differ")
    cells, center_volumes = [], []
    for local, entries in sorted(by_cell.items()):
        row, column = row_base + local // TILE_CELLS, column_base + local % TILE_CELLS
        point = np.asarray(grid["origin_m_xz"]) + (np.array([column, row]) + .5) * grid["spacing_m"]
        sample = source._source_sample(context, *map(float, point))
        cuts, owners = [], []
        for contribution_index, fan_index in entries:
            cut = _center_cut(fans[fan_index], point)
            if cut is not None:
                cuts.append(cut)
                owners.append(fans[fan_index]["fan_id"])
        if cuts and max(cuts) - min(cuts) > 1e-9:
            raise ValueError("shared center cut function mismatch")
        cut = cuts[0] if cuts else 0.
        if cuts and (sample["rejection_reasons"] or sample["height_m"] is None):
            raise ValueError("covered center has invalid original source")
        if cut > 0. and sample["wet_source_support"]:
            raise ValueError("covered wet source cut refused")
        bed = sample["height_m"] if not cuts or sample["height_m"] is None else sample["height_m"] - cut
        if bed is not None and bed > sample["height_m"]:
            raise ValueError("no-fill center bed invalid")
        area = math.fsum(contributions[index]["coverage_area_m2"] for index, _ in entries)
        volume = math.fsum(contributions[index]["integrated_cut_m3"] for index, _ in entries)
        if area > grid["spacing_m"]**2 + 1e-10:
            raise ValueError("positive fan projection overlap in fine cell")
        cells.append({"global_row": row, "global_col": column, "local_index": local, "center_xz_m": point.tolist(),
            "source_sample": sample, "source_height_m": sample["height_m"], "derived_bed_m": bed,
            "cut_depth_m": cut, "center_inside": bool(cuts), "center_fan_keys": owners,
            "valid": not sample["rejection_reasons"] and sample["height_m"] is not None,
            "coverage_area_m2": area, "integrated_cut_m3": volume,
            "contribution_indices": [index for index, _ in entries]})
        center_volumes.append(cut * grid["spacing_m"]**2)
    cut_volume = math.fsum(item["integrated_cut_m3"] for item in contributions)
    result = seal({"schema": "td-shared-channel-fine-tile-v1", "status": "candidate_unverified",
        "policy_identity_sha256": POLICY_IDENTITY_SHA256, "parameters_identity_sha256": PARAMETERS_IDENTITY_SHA256,
        "grid_identity_sha256": source._record_identity(grid),
        "grid": grid, "tile_row_column": list(tile_key), "global_origin_row_column": [row_base, column_base],
        "fans_identity_sha256": fan_parent_identity, "cells": cells, "contributions": contributions,
        "fan_integrals": [{"fan_key": fan_id, "fan_id": fan_id, "coverage_area_m2": math.fsum(values[0]),
            "integrated_cut_m3": math.fsum(values[1])} for fan_id, values in sorted(totals.items())],
        "material_ledger": material_ledger(cut_volume), "center_sample_cut_volume_m3": math.fsum(center_volumes),
        "material_semantics": "exact_affine_polygon_integral_not_center_depth_times_full_cell_area", **FLAGS})
    if source._record_bytes(result) > MAX_BYTES:
        raise BudgetExceeded("whole_package_tile_json_byte_budget_exceeded")
    check_memory()
    return result


def verify_integral_conservation(fans, accumulated):
    records = []
    for fan in fans:
        areas, volumes = accumulated[fan["fan_id"]]
        area, volume = math.fsum(areas), math.fsum(volumes)
        area_delta = area - fan["projected_area_m2"]
        volume_delta = volume - fan["expected_integrated_cut_m3"]
        if abs(area_delta) > max(1e-8, fan["projected_area_m2"] * 1e-9):
            raise ValueError("fine intersection fan area conservation failed")
        if abs(volume_delta) > max(1e-8, abs(fan["expected_integrated_cut_m3"]) * 1e-9):
            raise ValueError("fine affine integral material conservation failed")
        records.append({"fan_key": fan["fan_key"], "fan_id": fan["fan_id"], "coverage_area_m2": area,
            "integrated_cut_m3": volume, "area_residual_m2": area_delta, "cut_residual_m3": volume_delta})
    return records
