"""Finite, uncalibrated river candidates from an immutable TD hierarchy.

Hydraulic geometry exponents are starting values informed by USGS Leopold and
Maddock (1953), Professional Paper 252, doi:10.3133/pp252. They are not a
regional fit; no channel or outlet is certified by this module.
"""

from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np

from terrain_pipeline.common_infra import identity, readonly, save_bundle, load_bundle, MAX_METADATA
from terrain_pipeline.basin_topology import validate_basin_hierarchy as validate_basin_hierarchy


SCHEMA = "td-natural-river-network-v2"
LEVELS = ("small_gully", "seasonal_tributary", "perennial_tributary", "mainstem")
SCENARIOS = ("dry", "normal", "wet", "strong")
MAX_CELLS = 250_000
MAX_EDGES = 250_000
MAX_REACHES = 250_000
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")
REFINEMENT_BITS = {"width": 1, "area": 2, "level": 4, "junction": 8,
                   "slope": 16, "curvature": 32, "terminal": 64, "protected": 128}
SCORE_WEIGHTS = {"coverage": .25, "tributaries": .10, "strahler": .15, "length": .15,
                 "outlet": .10, "completeness": .15, "resource_budget": .10}
SECONDS_PER_YEAR = 365.25 * 86400


@dataclass(frozen=True)
class NaturalNetworkRecipe:
    dry_rainfall_mm: float = 12.0
    normal_rainfall_mm: float = 30.0
    wet_rainfall_mm: float = 55.0
    strong_rainfall_mm: float = 120.0
    ordinary_duration_s: float = 86400.0
    strong_duration_s: float = 21600.0
    dry_frequency_per_year: float = 8.0
    normal_frequency_per_year: float = 18.0
    wet_frequency_per_year: float = 8.0
    strong_frequency_per_year: float = 0.5
    baseflow_mm_per_day: float = 0.15
    runoff_coefficient: float = 0.35
    minimum_area_m2: float = 3600.0
    seasonal_area_m2: float = 18000.0
    perennial_area_m2: float = 72000.0
    mainstem_area_m2: float = 270000.0
    minimum_q_m3_s: float = 0.0005
    seasonal_q_m3_s: float = 0.003
    perennial_q_m3_s: float = 0.012
    mainstem_q_m3_s: float = 0.04
    perennial_baseflow_q_m3_s: float = 0.0001
    perennial_supply_fraction: float = 0.65
    minimum_seasonal_frequency_per_year: float = 4.0
    minimum_ordinary_frequency_per_year: float = 12.0
    minimum_slope_m_per_m: float = 0.001
    minimum_valley_support: float = 0.25
    material_erodibility: float = 0.65
    reference_q_m3_s: float = 1.0
    reference_width_m: float = 3.0
    reference_depth_m: float = 0.5
    width_exponent: float = 0.5
    depth_exponent: float = 0.3
    minimum_width_m: float = 0.7
    maximum_width_m: float = 80.0
    minimum_depth_m: float = 0.08
    maximum_depth_m: float = 5.0
    refinement_width_cells: float = 2.0
    gully_min_width_m: float = 0.7
    seasonal_min_width_m: float = 1.2
    perennial_min_width_m: float = 2.0
    mainstem_min_width_m: float = 4.0
    gully_min_depth_m: float = 0.08
    seasonal_min_depth_m: float = 0.15
    perennial_min_depth_m: float = 0.25
    mainstem_min_depth_m: float = 0.4
    gully_bank_slope_h_per_v: float = 1.5
    seasonal_bank_slope_h_per_v: float = 1.8
    perennial_bank_slope_h_per_v: float = 2.0
    mainstem_bank_slope_h_per_v: float = 2.5
    gully_protection_distance_m: float = 2.0
    seasonal_protection_distance_m: float = 3.0
    perennial_protection_distance_m: float = 5.0
    mainstem_protection_distance_m: float = 8.0
    gully_required_spacing_m: float = 2.0
    seasonal_required_spacing_m: float = 3.0
    perennial_required_spacing_m: float = 4.0
    mainstem_required_spacing_m: float = 6.0
    activity_q_m3_s: float = 0.0001

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid finite recipe field: {name}")
            if value == 0 and name not in ("baseflow_mm_per_day", "minimum_slope_m_per_m", "minimum_valley_support"):
                raise ValueError(f"positive recipe field required: {name}")
        if not (self.dry_rainfall_mm <= self.normal_rainfall_mm <= self.wet_rainfall_mm < self.strong_rainfall_mm):
            raise ValueError("rainfall scenarios out of order")
        if not (self.minimum_area_m2 <= self.seasonal_area_m2 <= self.perennial_area_m2 <= self.mainstem_area_m2):
            raise ValueError("area thresholds out of order")
        if not (self.minimum_q_m3_s <= self.seasonal_q_m3_s <= self.perennial_q_m3_s <= self.mainstem_q_m3_s):
            raise ValueError("discharge thresholds out of order")
        if not (0 < self.runoff_coefficient <= 1 and 0 < self.material_erodibility <= 1 and
                0 < self.perennial_supply_fraction <= 1 and 0 <= self.minimum_valley_support <= 1 and
                self.minimum_width_m <= self.maximum_width_m and self.minimum_depth_m <= self.maximum_depth_m and
                0 < self.width_exponent < 1 and 0 < self.depth_exponent < 1):
            raise ValueError("invalid material, geometry or support bounds")
        for suffix in ("min_width_m", "min_depth_m", "bank_slope_h_per_v", "protection_distance_m", "required_spacing_m"):
            values = [getattr(self, f"{level}_{suffix}") for level in ("gully", "seasonal", "perennial", "mainstem")]
            if values != sorted(values):
                raise ValueError("level geometry bounds out of order")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _stable_identity(hierarchy_identity, forcing, recipe):
    return _digest({"algorithm": SCHEMA, "hierarchy": hierarchy_identity, "ordinary": forcing[:3],
                    "geometry_recipe": {key: value for key, value in asdict(recipe).items()
                                        if not key.startswith("strong_")}})


def _mainstem_diagnostic(edges, levels, area, routed_q, slope, recipe):
    candidates = [int(cell) for cell in edges[:, 0]
                  if area[cell] >= recipe.mainstem_area_m2 and routed_q[1, cell] >= recipe.mainstem_q_m3_s]
    estimates = [_width_depth(routed_q[1, cell], slope[cell], recipe) for cell in candidates]
    qualified = int(np.count_nonzero(levels == 3))
    if qualified:
        reason = "present"
    elif not candidates:
        reason = "area_or_discharge_threshold_unmet"
    elif not any(width >= recipe.mainstem_min_width_m and depth >= recipe.mainstem_min_depth_m
                 for width, depth in estimates):
        reason = "uncalibrated_width_or_depth_threshold_unmet"
    else:
        reason = "ordinary_supply_or_valley_gate_unmet"
    return {"qualified_edge_count": qualified, "area_q_candidate_count": len(candidates),
            "max_candidate_estimated_width_m": max((width for width, _ in estimates), default=0.0),
            "max_candidate_estimated_depth_m": max((depth for _, depth in estimates), default=0.0),
            "required_width_m": recipe.mainstem_min_width_m, "required_depth_m": recipe.mainstem_min_depth_m,
            "reason": reason}


def _neighbors(cell, rows, columns):
    row, column = divmod(int(cell), columns)
    if row:
        yield cell - columns
    if row + 1 < rows:
        yield cell + columns
    if column:
        yield cell - 1
    if column + 1 < columns:
        yield cell + 1


def _metrics(hierarchy):
    source = hierarchy["arrays"]
    count = source["height_m"].size
    valid = source["valid_mask"].ravel() & ~source["protected_mask"].ravel()
    receiver = source["receiver"].copy()
    receiver[~valid] = -1
    active = np.flatnonzero(valid & (receiver >= 0))
    blocked = active[~valid[receiver[active]]]
    receiver[blocked] = -1
    active = np.flatnonzero(valid & (receiver >= 0))
    donors = np.bincount(receiver[active], minlength=count).astype(np.int64)
    pending = donors.copy()
    queue = deque(int(cell) for cell in np.flatnonzero(valid & (pending == 0)))
    upstream = []
    area = np.where(valid, float(hierarchy["metadata"]["spacing_m"]) ** 2, 0.0)
    max_order = np.zeros(count, np.int16)
    max_order_count = np.zeros(count, np.int16)
    strahler = np.zeros(count, np.int16)
    while queue:
        cell = queue.popleft()
        upstream.append(cell)
        strahler[cell] = max(1, max_order[cell] + (max_order_count[cell] >= 2))
        target = int(receiver[cell])
        if target >= 0:
            area[target] += area[cell]
            if strahler[cell] > max_order[target]:
                max_order[target] = strahler[cell]
                max_order_count[target] = 1
            elif strahler[cell] == max_order[target]:
                max_order_count[target] += 1
            pending[target] -= 1
            if pending[target] == 0:
                queue.append(target)
    if len(upstream) != int(valid.sum()):
        raise ValueError("receiver cycle")
    downstream = np.concatenate((np.asarray(upstream[::-1], dtype=np.int64), np.flatnonzero(~valid)))
    terminal = np.full(count, -1, np.int64)
    length = np.zeros(count, np.int32)
    for cell in downstream:
        if not valid[cell]:
            continue
        target = int(receiver[cell])
        terminal[cell] = terminal[target] if target >= 0 else cell
        length[cell] = length[target] + 1 if target >= 0 else 1
    return valid, receiver, donors, area, terminal, length, downstream, blocked, strahler


def _basins(hierarchy, valid, donors, area, terminal, length, blocked, strahler):
    source = hierarchy["arrays"]
    rows, columns = source["height_m"].shape
    ids, inverse = np.unique(terminal[valid], return_inverse=True)
    cells = np.bincount(inverse, minlength=len(ids))
    junctions = np.bincount(inverse, weights=donors[valid] > 1, minlength=len(ids)).astype(int)
    longest = np.zeros(len(ids), np.int32)
    np.maximum.at(longest, inverse, length[valid])
    unknown = np.zeros(len(ids), np.int64)
    protected = np.zeros(len(ids), np.int64)
    basin_of = np.full(valid.size, -1, np.int64)
    basin_of[np.flatnonzero(valid)] = inverse
    known = source["valid_mask"].ravel()
    barrier = source["protected_mask"].ravel()
    for cell in np.flatnonzero(valid):
        neighbors = tuple(_neighbors(cell, rows, columns))
        unknown[basin_of[cell]] += any(not known[neighbor] for neighbor in neighbors)
        protected[basin_of[cell]] += any(barrier[neighbor] for neighbor in neighbors)
    blocked_set = set(map(int, blocked))
    records = []
    for index, terminal_id in enumerate(ids):
        kind = ("protected_barrier" if int(terminal_id) in blocked_set else
                "unknown_contact" if any(not known[neighbor] for neighbor in _neighbors(terminal_id, rows, columns)) else
                "engineered_open" if source["open_boundary_mask"].ravel()[terminal_id] else "internal_basin")
        records.append({"terminal_cell_id": int(terminal_id), "area_m2": float(area[terminal_id]),
                        "cell_count": int(cells[index]), "junction_count": int(junctions[index]),
                        "longest_path_cells": int(longest[index]), "strahler_order": int(strahler[terminal_id]),
                        "unknown_contact_cells": int(unknown[index]),
                        "protected_contact_cells": int(protected[index]), "terminal_kind": kind})
    maxima = {key: max(record[key] for record in records) or 1 for key in ("area_m2", "junction_count", "longest_path_cells", "strahler_order")}
    for record in records:
        completeness = 1 - (record["unknown_contact_cells"] + record["protected_contact_cells"]) / max(record["cell_count"], 1)
        outlet = {"internal_basin": 1.0, "engineered_open": .85, "protected_barrier": 0.0, "unknown_contact": 0.0}[record["terminal_kind"]]
        record["score_components"] = {
            "coverage": record["area_m2"] / maxima["area_m2"],
            "tributaries": record["junction_count"] / maxima["junction_count"],
            "strahler": record["strahler_order"] / maxima["strahler_order"],
            "length": record["longest_path_cells"] / maxima["longest_path_cells"],
            "outlet": outlet, "completeness": max(0.0, completeness),
            "resource_budget": min(1.0, 25000 / record["cell_count"]),
        }
        record["score"] = sum(SCORE_WEIGHTS[key] * value for key, value in record["score_components"].items())
    records.sort(key=lambda record: (-record["score"], record["terminal_cell_id"]))
    return records


def _forcing(recipe):
    fields = asdict(recipe)
    return [{"name": name, "rainfall_mm": fields[f"{name}_rainfall_mm"],
             "duration_s": recipe.strong_duration_s if name == "strong" else recipe.ordinary_duration_s,
             "frequency_per_year": fields[f"{name}_frequency_per_year"],
             "baseflow_mm_per_day": recipe.baseflow_mm_per_day,
             "role": "event_only" if name == "strong" else "stable_morphology"} for name in SCENARIOS]


def _width_depth(q, slope, recipe):
    ratio = max(q / recipe.reference_q_m3_s, 1e-12)
    slope_factor = min(1.5, max(.7, (max(slope, .0001) / .01) ** -.08))
    width = recipe.reference_width_m * ratio ** recipe.width_exponent * slope_factor * (0.8 + .4 * recipe.material_erodibility)
    depth = recipe.reference_depth_m * ratio ** recipe.depth_exponent / slope_factor
    return (min(recipe.maximum_width_m, max(recipe.minimum_width_m, width)),
            min(recipe.maximum_depth_m, max(recipe.minimum_depth_m, depth)))


def _level_value(recipe, level, suffix):
    prefix = ("gully", "seasonal", "perennial", "mainstem")[level]
    return getattr(recipe, f"{prefix}_{suffix}")


def _derive_channels(height, valid, receiver, donors, area, selected, order, routed_q, recipe, spacing):
    rows, columns = height.shape
    flat_height = height.ravel()
    slope = np.zeros(height.size, np.float64)
    support = np.zeros(height.size, np.float64)
    active_selected = np.flatnonzero(selected & (receiver >= 0))
    for cell in active_selected:
        target = int(receiver[cell])
        slope[cell] = max(0.0, (flat_height[cell] - flat_height[target]) / spacing)
        row, column = divmod(int(cell), columns)
        transverse = (cell - columns, cell + columns) if abs(target - cell) == 1 else (cell - 1, cell + 1)
        banks = [neighbor for neighbor in transverse if 0 <= neighbor < height.size and
                 abs(neighbor // columns - row) + abs(neighbor % columns - column) == 1 and valid[neighbor]]
        support[cell] = sum(flat_height[neighbor] > flat_height[cell] for neighbor in banks) / len(banks) if banks else 0.0
    ordinary = _forcing(recipe)[:3]
    frequencies = np.asarray([item["frequency_per_year"] for item in ordinary])
    durations = np.asarray([item["duration_s"] for item in ordinary])
    active = routed_q[:3] >= recipe.activity_q_m3_s
    active_frequency = (active.T @ frequencies) / frequencies.sum()
    active_duration = np.minimum(1., (active.T @ (frequencies * durations)) / SECONDS_PER_YEAR)
    baseflow_q = area * recipe.baseflow_mm_per_day / 1000 / 86400
    baseflow_year_round = baseflow_q >= recipe.activity_q_m3_s
    supply_frequency = np.where(baseflow_year_round, 1., active_frequency)
    supply_duration = np.where(baseflow_year_round, 1., active_duration)
    candidates = np.zeros(height.size, np.int8)
    for cell in active_selected:
        if slope[cell] < recipe.minimum_slope_m_per_m and support[cell] < recipe.minimum_valley_support:
            continue
        q = routed_q[1, cell]
        width, depth = _width_depth(q, slope[cell], recipe)
        if (area[cell] < recipe.minimum_area_m2 or q < recipe.minimum_q_m3_s * (1.2 - .4 * recipe.material_erodibility) or
                width < _level_value(recipe, 0, "min_width_m") or depth < _level_value(recipe, 0, "min_depth_m")):
            continue
        level = 1
        if (area[cell] >= recipe.seasonal_area_m2 and routed_q[2, cell] >= recipe.seasonal_q_m3_s and
                recipe.wet_frequency_per_year >= recipe.minimum_seasonal_frequency_per_year and
                width >= recipe.seasonal_min_width_m and depth >= recipe.seasonal_min_depth_m):
            level = 2
        if (level >= 2 and area[cell] >= recipe.perennial_area_m2 and routed_q[0, cell] >= recipe.perennial_q_m3_s and
                sum(frequencies) >= recipe.minimum_ordinary_frequency_per_year and
                baseflow_q[cell] >= recipe.perennial_baseflow_q_m3_s and
                supply_duration[cell] >= recipe.perennial_supply_fraction and
                width >= recipe.perennial_min_width_m and depth >= recipe.perennial_min_depth_m):
            level = 3
        if (level >= 3 and area[cell] >= recipe.mainstem_area_m2 and q >= recipe.mainstem_q_m3_s and
                width >= recipe.mainstem_min_width_m and depth >= recipe.mainstem_min_depth_m):
            level = 4
        candidates[cell] = level
    propagated = np.zeros(height.size, np.int8)
    for cell in order[::-1]:
        propagated[cell] = max(propagated[cell], candidates[cell])
        target = int(receiver[cell])
        if target >= 0:
            propagated[target] = max(propagated[target], propagated[cell])
    selected_donors = np.flatnonzero(selected & (receiver >= 0) & (propagated > 0))
    if not len(selected_donors):
        raise ValueError("no qualifying river segment in complete basin")
    edges = np.column_stack((selected_donors, receiver[selected_donors])).astype(np.int64)
    nodes = np.unique(edges)
    node_index = np.full(height.size, -1, np.int64)
    node_index[nodes] = np.arange(len(nodes))
    incoming = np.bincount(edges[:, 1], minlength=height.size)
    levels = (propagated[selected_donors] - 1).astype(np.int8)
    closure = candidates[selected_donors] == 0
    widths = np.zeros(len(nodes))
    depths = np.zeros(len(nodes))
    for index, cell in enumerate(nodes):
        widths[index], depths[index] = _width_depth(routed_q[1, cell], slope[cell], recipe)
        level = int(propagated[cell]) - 1
        widths[index] = max(widths[index], _level_value(recipe, level, "min_width_m"))
        depths[index] = max(depths[index], _level_value(recipe, level, "min_depth_m"))
    for cell in order[::-1]:
        target = int(receiver[cell])
        if target >= 0 and node_index[cell] >= 0 and node_index[target] >= 0:
            widths[node_index[target]] = max(widths[node_index[target]], widths[node_index[cell]])
            depths[node_index[target]] = max(depths[node_index[target]], depths[node_index[cell]])
    reason_bits = np.zeros(len(edges), np.uint16)
    target_spacing = np.zeros(len(edges), np.float64)
    for index, (donor, target) in enumerate(edges):
        level = int(levels[index])
        width = widths[node_index[donor]]
        threshold = (recipe.minimum_area_m2, recipe.seasonal_area_m2,
                     recipe.perennial_area_m2, recipe.mainstem_area_m2)[level]
        bits = 0
        if width < recipe.refinement_width_cells * spacing:
            bits |= REFINEMENT_BITS["width"]
        if area[donor] < 2 * threshold:
            bits |= REFINEMENT_BITS["area"]
        if level >= 2:
            bits |= REFINEMENT_BITS["level"]
        if incoming[target] > 1:
            bits |= REFINEMENT_BITS["junction"]
        if slope[donor] < recipe.minimum_slope_m_per_m or slope[donor] > .1:
            bits |= REFINEMENT_BITS["slope"]
        following = int(receiver[target])
        if following >= 0 and (target - donor) != (following - target):
            bits |= REFINEMENT_BITS["curvature"]
        if following < 0:
            bits |= REFINEMENT_BITS["terminal"]
        if any(not valid[neighbor] for neighbor in _neighbors(donor, rows, columns)):
            bits |= REFINEMENT_BITS["protected"]
        reason_bits[index] = bits
        bank_run_m = depths[node_index[donor]] * _level_value(recipe, level, "bank_slope_h_per_v")
        target_spacing[index] = min(spacing, _level_value(recipe, level, "required_spacing_m"),
                                    width / 4, bank_run_m / 2,
                                    _level_value(recipe, level, "protection_distance_m") / 2)
    return {"slope": slope, "support": support, "active_frequency": active_frequency,
            "active_duration": active_duration, "supply_frequency": supply_frequency,
            "supply_duration": supply_duration, "baseflow_year_round": baseflow_year_round,
            "candidates": candidates, "edges": edges, "nodes": nodes, "incoming": incoming,
            "levels": levels, "closure": closure, "widths": widths, "depths": depths,
            "reason_bits": reason_bits, "target_spacing": target_spacing}


def build_natural_river_network(hierarchy, *, expected_hierarchy_identity, recipe=NaturalNetworkRecipe()):
    validate_basin_hierarchy(hierarchy)
    if hierarchy["identity_sha256"] != expected_hierarchy_identity:
        raise ValueError("external hierarchy identity mismatch")
    if not isinstance(recipe, NaturalNetworkRecipe):
        raise ValueError("natural network recipe required")
    source = hierarchy["arrays"]
    height = source["height_m"]
    rows, columns = height.shape
    if height.size > MAX_CELLS:
        raise ValueError("natural network cell budget exceeded")
    valid, receiver, donors, area, terminal, length, order, blocked, strahler = _metrics(hierarchy)
    basins = _basins(hierarchy, valid, donors, area, terminal, length, blocked, strahler)
    eligible = [record for record in basins if record["terminal_kind"] not in ("unknown_contact", "protected_barrier") and
                record["unknown_contact_cells"] == 0 and record["protected_contact_cells"] == 0]
    if not eligible:
        raise ValueError("no complete basin; unknown/protected contact diagnostics: " + str(basins[:3]))
    selected_basin = eligible[0]
    terminal_id = selected_basin["terminal_cell_id"]
    selected = valid & (terminal == terminal_id)
    spacing = float(hierarchy["metadata"]["spacing_m"])
    forcing = _forcing(recipe)
    local_q = np.zeros((4, height.size), np.float64)
    for index, scenario in enumerate(forcing):
        rate = scenario["rainfall_mm"] / 1000 * recipe.runoff_coefficient / scenario["duration_s"]
        rate += recipe.baseflow_mm_per_day / 1000 / 86400
        local_q[index, valid] = spacing ** 2 * rate
    routed_q = local_q.copy()
    for cell in order[::-1]:
        target = int(receiver[cell])
        if target >= 0:
            routed_q[:, target] += routed_q[:, cell]
    derived = _derive_channels(height, valid, receiver, donors, area, selected, order, routed_q, recipe, spacing)
    edges = derived["edges"]
    donors_selected = edges[:, 0]
    if len(donors_selected) > MAX_EDGES:
        raise ValueError("natural network edge budget exceeded")
    nodes = derived["nodes"]
    incoming = derived["incoming"]
    levels = derived["levels"]
    widths = derived["widths"]
    depths = derived["depths"]
    flat_height = height.ravel()
    origin_x, origin_z = hierarchy["metadata"]["origin_m_xz"]
    xyz = np.column_stack((origin_x + nodes % columns * spacing, flat_height[nodes],
                           origin_z + nodes // columns * spacing)).astype(np.float64)
    refine = derived["reason_bits"] != 0
    starts = [int(cell) for cell in nodes if incoming[cell] != 1 and receiver[cell] >= 0]
    edge_of = np.full(height.size, -1, np.int64)
    edge_of[donors_selected] = np.arange(len(edges))
    offsets = [0]
    reach_cells = []
    for start in starts:
        cells = [start]
        current = start
        while edge_of[current] >= 0:
            current = int(receiver[current])
            cells.append(current)
            if incoming[current] != 1 or edge_of[current] < 0:
                break
        reach_cells.extend(cells)
        offsets.append(len(reach_cells))
    if len(offsets) - 1 > MAX_REACHES or sum(np.diff(offsets) - 1) != len(edges):
        raise ValueError("reach compression lost edges")
    basin_kind = {"internal_basin": 0, "engineered_open": 1, "protected_barrier": 2, "unknown_contact": 3}
    output = {
        "source_height_m": height.copy(), "valid_mask": source["valid_mask"].copy(),
        "protected_mask": source["protected_mask"].copy(), "open_boundary_mask": source["open_boundary_mask"].copy(),
        "receiver": receiver, "original_receiver": source["receiver"].copy(),
        "routing_order": order, "selected_basin_mask": selected.reshape(height.shape),
        "contributing_area_m2": area, "local_q_m3_s": local_q, "routed_q_m3_s": routed_q,
        "ordinary_active_frequency_fraction": derived["active_frequency"],
        "ordinary_active_duration_fraction": derived["active_duration"],
        "supply_frequency_fraction": derived["supply_frequency"],
        "supply_duration_fraction": derived["supply_duration"],
        "baseflow_year_round_mask": derived["baseflow_year_round"],
        "edge_cell_ids": edges, "edge_contributing_area_m2": area[donors_selected],
        "edge_q_normal_m3_s": routed_q[1, donors_selected], "edge_q_strong_m3_s": routed_q[3, donors_selected],
        "edge_slope_m_per_m": derived["slope"][donors_selected],
        "edge_valley_support": derived["support"][donors_selected],
        "edge_level_code": levels, "edge_closure_mask": derived["closure"],
        "edge_requires_refinement": refine, "edge_refinement_reason_bits": derived["reason_bits"],
        "edge_target_spacing_m": derived["target_spacing"],
        "node_cell_ids": nodes, "node_native_xyz_m": xyz, "node_width_m": widths, "node_depth_m": depths,
        "node_representative_q_m3_s": routed_q[1, nodes],
        "reach_offsets": np.asarray(offsets, np.int64), "reach_cell_ids": np.asarray(reach_cells, np.int64),
        "basin_terminal_cell_ids": np.asarray([record["terminal_cell_id"] for record in basins], np.int64),
        "basin_area_m2": np.asarray([record["area_m2"] for record in basins], np.float64),
        "basin_cell_count": np.asarray([record["cell_count"] for record in basins], np.int64),
        "basin_junction_count": np.asarray([record["junction_count"] for record in basins], np.int64),
        "basin_longest_path_cells": np.asarray([record["longest_path_cells"] for record in basins], np.int64),
        "basin_strahler_order": np.asarray([record["strahler_order"] for record in basins], np.int16),
        "basin_unknown_contact_cells": np.asarray([record["unknown_contact_cells"] for record in basins], np.int64),
        "basin_protected_contact_cells": np.asarray([record["protected_contact_cells"] for record in basins], np.int64),
        "basin_terminal_kind_code": np.asarray([basin_kind[record["terminal_kind"]] for record in basins], np.int8),
        "basin_score": np.asarray([record["score"] for record in basins], np.float64),
    }
    recipe_record = asdict(recipe)
    metadata = {"schema": SCHEMA, "algorithm": SCHEMA, "hierarchy_identity_sha256": expected_hierarchy_identity,
                "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
                "grid_shape": [rows, columns], "spacing_m": spacing,
                "origin_m_xz": list(hierarchy["metadata"]["origin_m_xz"]), "recipe": recipe_record,
                "forcing": forcing, "forcing_identity_sha256": _digest(forcing),
                "stable_identity_sha256": _stable_identity(expected_hierarchy_identity, forcing, recipe),
                "selected_basin": selected_basin, "basins_preview": basins[:16],
                "independent_internal_example": next((record for record in basins if record["terminal_kind"] == "internal_basin" and
                                                      record["terminal_cell_id"] != terminal_id), None),
                "levels": list(LEVELS), "refinement_reason_bits": REFINEMENT_BITS,
                "basin_score_weights": SCORE_WEIGHTS, "resource_budget_reference_cells": 25000,
                "level_geometry": [{"level": name, "minimum_width_m": _level_value(recipe, index, "min_width_m"),
                                    "minimum_depth_m": _level_value(recipe, index, "min_depth_m"),
                                    "bank_slope_h_per_v": _level_value(recipe, index, "bank_slope_h_per_v"),
                                    "protection_distance_m": _level_value(recipe, index, "protection_distance_m"),
                                    "required_spacing_m": _level_value(recipe, index, "required_spacing_m")}
                                   for index, name in enumerate(LEVELS)],
                "supply_semantics": "ordinary Q>=activity threshold contributes frequency and duration; baseflow Q>=threshold assumed year-round; strong event excluded",
                "physics_semantics": "runoff coefficient converts each fixed rain scenario to a constant local rate over its declared duration; no temporal runoff release or new-bed hydraulic solve",
                "summary": {"basin_count": len(basins), "selected_terminal_cell_id": terminal_id,
                            "selected_cell_count": int(selected.sum()), "edge_count": len(edges),
                            "node_count": len(nodes), "reach_count": len(offsets) - 1,
                            "level_counts": {name: int(np.count_nonzero(levels == index)) for index, name in enumerate(LEVELS)},
                            "refinement_edge_count": int(refine.sum()), "terminal_kind": selected_basin["terminal_kind"],
                            "mainstem_diagnostic": _mainstem_diagnostic(edges, levels, area, routed_q,
                                                                       derived["slope"], recipe)},
                "calibration": "uncalibrated finite prototype; width/depth exponents informed by USGS PP252 (1953), doi:10.3133/pp252; valley width unmeasured",
                **{flag: False for flag in FLAGS}}
    manifest_bytes = len(json.dumps({"metadata": metadata, "identity_sha256": "0" * 64},
                                    sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    if manifest_bytes > MAX_METADATA:
        raise ValueError("natural network metadata budget exceeded")
    result = {"arrays": {key: readonly(value) for key, value in output.items()}, "metadata": metadata,
              "identity_sha256": identity(output, metadata)}
    validate_natural_river_network(result)
    return result


def validate_natural_river_network(result, *, hierarchy=None):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata.get("schema") != SCHEMA or metadata.get("algorithm") != SCHEMA or any(metadata.get(flag) is not False for flag in FLAGS):
        raise ValueError("natural network schema or certification invalid")
    recipe = NaturalNetworkRecipe(**metadata["recipe"])
    if metadata["forcing"] != _forcing(recipe) or metadata["forcing_identity_sha256"] != _digest(metadata["forcing"]):
        raise ValueError("forcing identity mismatch")
    stable = _stable_identity(metadata["hierarchy_identity_sha256"], metadata["forcing"], recipe)
    if metadata["stable_identity_sha256"] != stable or result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("stable or bundle identity mismatch")
    if metadata.get("physics_semantics") != "runoff coefficient converts each fixed rain scenario to a constant local rate over its declared duration; no temporal runoff release or new-bed hydraulic solve":
        raise ValueError("natural network physics semantics mismatch")
    rows, columns = metadata["grid_shape"]
    if type(rows) is not int or type(columns) is not int or rows < 1 or columns < 1 or rows * columns > MAX_CELLS:
        raise ValueError("invalid network grid budget")
    count = rows * columns
    required = {"source_height_m", "valid_mask", "protected_mask", "open_boundary_mask", "receiver", "original_receiver", "routing_order",
                "selected_basin_mask", "contributing_area_m2", "local_q_m3_s", "routed_q_m3_s", "edge_cell_ids",
                "ordinary_active_frequency_fraction", "ordinary_active_duration_fraction", "supply_frequency_fraction",
                "supply_duration_fraction", "baseflow_year_round_mask",
                "edge_contributing_area_m2", "edge_q_normal_m3_s", "edge_q_strong_m3_s", "edge_slope_m_per_m",
                "edge_valley_support", "edge_level_code", "edge_closure_mask", "edge_requires_refinement",
                "edge_refinement_reason_bits", "edge_target_spacing_m", "node_cell_ids",
                "node_native_xyz_m", "node_width_m", "node_depth_m", "node_representative_q_m3_s",
                "reach_offsets", "reach_cell_ids", "basin_terminal_cell_ids", "basin_area_m2", "basin_cell_count",
                "basin_junction_count", "basin_longest_path_cells", "basin_strahler_order",
                "basin_unknown_contact_cells", "basin_protected_contact_cells", "basin_terminal_kind_code", "basin_score"}
    if set(arrays) != required:
        raise ValueError("natural network array schema mismatch")
    edges = arrays["edge_cell_ids"]
    nodes = arrays["node_cell_ids"]
    edge_count = len(edges)
    if edge_count == 0 or edge_count > MAX_EDGES or edges.dtype != np.int64 or edges.shape != (edge_count, 2) or len(nodes) == 0:
        raise ValueError("invalid edge budget/topology")
    shapes = {"source_height_m": (rows, columns), "valid_mask": (rows, columns), "protected_mask": (rows, columns),
              "open_boundary_mask": (rows, columns), "selected_basin_mask": (rows, columns),
              "receiver": (count,), "original_receiver": (count,), "routing_order": (count,),
              "contributing_area_m2": (count,), "ordinary_active_frequency_fraction": (count,),
              "ordinary_active_duration_fraction": (count,), "supply_frequency_fraction": (count,),
              "supply_duration_fraction": (count,), "baseflow_year_round_mask": (count,),
              "local_q_m3_s": (4, count), "routed_q_m3_s": (4, count), "edge_contributing_area_m2": (edge_count,),
              "edge_q_normal_m3_s": (edge_count,), "edge_q_strong_m3_s": (edge_count,),
              "edge_slope_m_per_m": (edge_count,), "edge_valley_support": (edge_count,),
              "edge_level_code": (edge_count,), "edge_closure_mask": (edge_count,),
              "edge_requires_refinement": (edge_count,), "edge_refinement_reason_bits": (edge_count,),
              "edge_target_spacing_m": (edge_count,),
              "node_cell_ids": (len(nodes),), "node_native_xyz_m": (len(nodes), 3),
              "node_width_m": (len(nodes),), "node_depth_m": (len(nodes),),
              "node_representative_q_m3_s": (len(nodes),), "reach_offsets": (metadata["summary"]["reach_count"] + 1,)}
    basin_count = metadata["summary"]["basin_count"]
    for key in ("basin_terminal_cell_ids", "basin_area_m2", "basin_cell_count", "basin_junction_count",
                "basin_longest_path_cells", "basin_strahler_order", "basin_unknown_contact_cells",
                "basin_protected_contact_cells", "basin_terminal_kind_code", "basin_score"):
        shapes[key] = (basin_count,)
    if any(arrays[key].shape != shape for key, shape in shapes.items()):
        raise ValueError("natural network array shape mismatch")
    for key in ("valid_mask", "protected_mask", "open_boundary_mask", "selected_basin_mask",
                "edge_requires_refinement", "edge_closure_mask", "baseflow_year_round_mask"):
        if arrays[key].dtype != bool:
            raise ValueError("nonboolean mask")
    for key in ("receiver", "original_receiver", "routing_order", "node_cell_ids", "reach_offsets", "reach_cell_ids",
                "basin_terminal_cell_ids", "basin_cell_count", "basin_junction_count", "basin_longest_path_cells",
                "basin_unknown_contact_cells", "basin_protected_contact_cells"):
        if arrays[key].dtype != np.int64:
            raise ValueError("invalid integer array")
    if arrays["edge_level_code"].dtype != np.int8 or np.any((arrays["edge_level_code"] < 0) | (arrays["edge_level_code"] >= len(LEVELS))):
        raise ValueError("invalid river level")
    if (arrays["edge_refinement_reason_bits"].dtype != np.uint16 or
            arrays["basin_strahler_order"].dtype != np.int16 or arrays["basin_terminal_kind_code"].dtype != np.int8):
        raise ValueError("invalid classification/refinement dtype")
    for value in arrays.values():
        if value.dtype.kind == "f" and (value.dtype != np.float64 or not np.isfinite(value).all()):
            raise ValueError("nonfinite or non-float64 input")
    valid = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    receiver = arrays["receiver"]
    order = arrays["routing_order"]
    if (np.any((receiver < -1) | (receiver >= count)) or np.any(receiver[~valid] != -1) or
            not np.array_equal(np.sort(order), np.arange(count))):
        raise ValueError("invalid receiver/routing permutation")
    active = np.flatnonzero(receiver >= 0)
    if not valid[active].all() or not valid[receiver[active]].all():
        raise ValueError("receiver crosses unknown/protected cell")
    if np.any(abs(active // columns - receiver[active] // columns) + abs(active % columns - receiver[active] % columns) != 1):
        raise ValueError("receiver is not D4")
    original = arrays["original_receiver"]
    if np.any((original < -1) | (original >= count)):
        raise ValueError("original receiver bounds invalid")
    original_active = np.flatnonzero(original >= 0)
    if (np.any(abs(original_active // columns - original[original_active] // columns) +
               abs(original_active % columns - original[original_active] % columns) != 1) or
            np.any(arrays["source_height_m"].ravel()[original[original_active]] >
                   arrays["source_height_m"].ravel()[original_active])):
        raise ValueError("original receiver geometry invalid")
    rank = np.empty(count, np.int64)
    rank[order] = np.arange(count)
    if np.any(rank[receiver[active]] >= rank[active]):
        raise ValueError("routing order is not downstream first")
    selected = arrays["selected_basin_mask"].ravel()
    if not selected.any() or np.any(selected & ~valid) or metadata["summary"]["selected_cell_count"] != int(selected.sum()):
        raise ValueError("invalid selected basin")
    if np.any((edges < 0) | (edges >= count)) or len(np.unique(edges[:, 0])) != edge_count or not selected[edges].all():
        raise ValueError("invalid selected edges")
    if not np.array_equal(receiver[edges[:, 0]], edges[:, 1]) or not np.array_equal(nodes, np.unique(edges)):
        raise ValueError("edge/node topology mismatch")
    terminal_id = metadata["summary"]["selected_terminal_cell_id"]
    if receiver[terminal_id] != -1 or not selected[terminal_id] or terminal_id not in nodes:
        raise ValueError("selected network does not close at terminal")
    if np.any(selected[active] != selected[receiver[active]]):
        raise ValueError("selected basin is not closed")
    if (np.any(arrays["node_width_m"] <= 0) or np.any(arrays["node_depth_m"] <= 0) or
            np.any(arrays["edge_valley_support"] < 0) or np.any(arrays["edge_valley_support"] > 1)):
        raise ValueError("invalid channel geometry/support")
    node_index = np.searchsorted(nodes, edges)
    if (np.any(arrays["node_width_m"][node_index[:, 1]] < arrays["node_width_m"][node_index[:, 0]] - 1e-12) or
            np.any(arrays["node_depth_m"][node_index[:, 1]] < arrays["node_depth_m"][node_index[:, 0]] - 1e-12)):
        raise ValueError("downstream geometry regression")
    origin_x, origin_z = metadata["origin_m_xz"]
    spacing = metadata["spacing_m"]
    if type(spacing) not in (float, int) or not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid spacing")
    expected_xyz = np.column_stack((origin_x + nodes % columns * spacing,
                                    arrays["source_height_m"].ravel()[nodes], origin_z + nodes // columns * spacing))
    if not np.array_equal(arrays["node_native_xyz_m"], expected_xyz):
        raise ValueError("node coordinates mismatch")
    expected_level_geometry = [{"level": name, "minimum_width_m": _level_value(recipe, index, "min_width_m"),
                                "minimum_depth_m": _level_value(recipe, index, "min_depth_m"),
                                "bank_slope_h_per_v": _level_value(recipe, index, "bank_slope_h_per_v"),
                                "protection_distance_m": _level_value(recipe, index, "protection_distance_m"),
                                "required_spacing_m": _level_value(recipe, index, "required_spacing_m")}
                               for index, name in enumerate(LEVELS)]
    if (metadata["refinement_reason_bits"] != REFINEMENT_BITS or metadata["level_geometry"] != expected_level_geometry or
            metadata["basin_score_weights"] != SCORE_WEIGHTS or metadata["resource_budget_reference_cells"] != 25000):
        raise ValueError("level geometry/refinement contract mismatch")
    for index, scenario in enumerate(metadata["forcing"]):
        rate = scenario["rainfall_mm"] / 1000 * recipe.runoff_coefficient / scenario["duration_s"] + recipe.baseflow_mm_per_day / 1000 / 86400
        expected_local = np.where(valid, spacing ** 2 * rate, 0.0)
        if not np.allclose(arrays["local_q_m3_s"][index], expected_local, rtol=1e-12, atol=1e-14):
            raise ValueError("local runoff mismatch")
        routed = arrays["routed_q_m3_s"][index]
        incoming = np.bincount(receiver[active], weights=routed[active], minlength=count)
        if not np.allclose(routed, expected_local + incoming, rtol=1e-11, atol=1e-12):
            raise ValueError("junction discharge including local runoff is not conserved")
    if (not np.allclose(arrays["edge_contributing_area_m2"], arrays["contributing_area_m2"][edges[:, 0]]) or
            not np.allclose(arrays["edge_q_normal_m3_s"], arrays["routed_q_m3_s"][1, edges[:, 0]]) or
            not np.allclose(arrays["edge_q_strong_m3_s"], arrays["routed_q_m3_s"][3, edges[:, 0]]) or
            not np.allclose(arrays["node_representative_q_m3_s"], arrays["routed_q_m3_s"][1, nodes])):
        raise ValueError("edge/node hydrology mismatch")
    audit_hierarchy = {"arrays": {"height_m": arrays["source_height_m"], "valid_mask": arrays["valid_mask"],
                                  "protected_mask": arrays["protected_mask"],
                                  "open_boundary_mask": arrays["open_boundary_mask"], "receiver": original},
                       "metadata": {"spacing_m": spacing}}
    audit = _metrics(audit_hierarchy)
    audit_valid, audit_receiver, audit_donors, audit_area, audit_terminal, audit_length, audit_order, audit_blocked, audit_strahler = audit
    audit_basins = _basins(audit_hierarchy, audit_valid, audit_donors, audit_area, audit_terminal,
                           audit_length, audit_blocked, audit_strahler)
    eligible = [record for record in audit_basins if record["terminal_kind"] not in ("unknown_contact", "protected_barrier") and
                record["unknown_contact_cells"] == 0 and record["protected_contact_cells"] == 0]
    if (not eligible or metadata["selected_basin"] != eligible[0] or metadata["basins_preview"] != audit_basins[:16] or
            metadata["summary"]["basin_count"] != len(audit_basins) or
            not np.array_equal(receiver, audit_receiver) or not np.array_equal(order, audit_order) or
            not np.array_equal(selected, audit_valid & (audit_terminal == eligible[0]["terminal_cell_id"])) or
            not np.allclose(arrays["contributing_area_m2"], audit_area, rtol=0, atol=1e-9)):
        raise ValueError("basin/routing semantic audit mismatch")
    basin_fields = {"basin_terminal_cell_ids": "terminal_cell_id", "basin_area_m2": "area_m2",
                    "basin_cell_count": "cell_count", "basin_junction_count": "junction_count",
                    "basin_longest_path_cells": "longest_path_cells", "basin_strahler_order": "strahler_order",
                    "basin_unknown_contact_cells": "unknown_contact_cells",
                    "basin_protected_contact_cells": "protected_contact_cells", "basin_score": "score"}
    for array_name, field in basin_fields.items():
        expected = np.asarray([record[field] for record in audit_basins], dtype=arrays[array_name].dtype)
        if not np.array_equal(arrays[array_name], expected):
            raise ValueError("basin score/statistics audit mismatch")
    kind_codes = {"internal_basin": 0, "engineered_open": 1, "protected_barrier": 2, "unknown_contact": 3}
    if not np.array_equal(arrays["basin_terminal_kind_code"],
                          np.asarray([kind_codes[record["terminal_kind"]] for record in audit_basins], np.int8)):
        raise ValueError("basin kind audit mismatch")
    internal_example = next((record for record in audit_basins if record["terminal_kind"] == "internal_basin" and
                             record["terminal_cell_id"] != terminal_id), None)
    if metadata["independent_internal_example"] != internal_example:
        raise ValueError("independent basin example mismatch")
    derived = _derive_channels(arrays["source_height_m"], audit_valid, receiver, audit_donors, audit_area,
                               selected, order, arrays["routed_q_m3_s"], recipe, spacing)
    derived_fields = {"edge_cell_ids": "edges", "node_cell_ids": "nodes", "edge_level_code": "levels",
                      "edge_closure_mask": "closure", "node_width_m": "widths", "node_depth_m": "depths",
                      "edge_refinement_reason_bits": "reason_bits", "edge_target_spacing_m": "target_spacing",
                      "ordinary_active_frequency_fraction": "active_frequency",
                      "ordinary_active_duration_fraction": "active_duration",
                      "supply_frequency_fraction": "supply_frequency",
                      "supply_duration_fraction": "supply_duration",
                      "baseflow_year_round_mask": "baseflow_year_round"}
    for array_name, field in derived_fields.items():
        if not np.array_equal(arrays[array_name], derived[field]):
            raise ValueError("channel classification/geometry/refinement audit mismatch")
    if (not np.array_equal(arrays["edge_slope_m_per_m"], derived["slope"][edges[:, 0]]) or
            not np.array_equal(arrays["edge_valley_support"], derived["support"][edges[:, 0]]) or
            not np.array_equal(arrays["edge_requires_refinement"], derived["reason_bits"] != 0)):
        raise ValueError("channel slope/support/refinement audit mismatch")
    if metadata["summary"]["mainstem_diagnostic"] != _mainstem_diagnostic(
            edges, derived["levels"], audit_area, arrays["routed_q_m3_s"], derived["slope"], recipe):
        raise ValueError("mainstem diagnostic audit mismatch")
    offsets = arrays["reach_offsets"]
    cells = arrays["reach_cell_ids"]
    if (offsets[0] != 0 or offsets[-1] != len(cells) or np.any(np.diff(offsets) < 2) or
            len(offsets) - 1 > MAX_REACHES or sum(np.diff(offsets) - 1) != edge_count):
        raise ValueError("invalid reach CSR")
    reach_edges = np.concatenate([np.column_stack((cells[offsets[index]:offsets[index + 1] - 1],
                                                  cells[offsets[index] + 1:offsets[index + 1]])) for index in range(len(offsets) - 1)])
    if not np.array_equal(reach_edges[np.lexsort((reach_edges[:, 1], reach_edges[:, 0]))], edges):
        raise ValueError("reach compression mismatch")
    if (metadata["summary"]["edge_count"] != edge_count or metadata["summary"]["node_count"] != len(nodes) or
            metadata["summary"]["refinement_edge_count"] != int(arrays["edge_requires_refinement"].sum())):
        raise ValueError("summary mismatch")
    if hierarchy is not None:
        validate_basin_hierarchy(hierarchy)
        if (hierarchy["identity_sha256"] != metadata["hierarchy_identity_sha256"] or
                hierarchy["metadata"]["source_identity_sha256"] != metadata["source_identity_sha256"]):
            raise ValueError("external hierarchy audit mismatch")
        for key, source_key in (("source_height_m", "height_m"), ("valid_mask", "valid_mask"),
                                ("protected_mask", "protected_mask"), ("open_boundary_mask", "open_boundary_mask")):
            if not np.array_equal(arrays[key], hierarchy["arrays"][source_key]):
                raise ValueError("source audit mismatch")
        if not np.array_equal(original, hierarchy["arrays"]["receiver"]):
            raise ValueError("source receiver audit mismatch")
        expected_receiver = hierarchy["arrays"]["receiver"].copy()
        expected_receiver[~valid] = -1
        active_source = np.flatnonzero(valid & (expected_receiver >= 0))
        expected_receiver[active_source[~valid[expected_receiver[active_source]]]] = -1
        if not np.array_equal(receiver, expected_receiver):
            raise ValueError("hierarchy receiver audit mismatch")
    return True


def save_natural_river_network(path, result):
    save_bundle(path, result, validator=validate_natural_river_network)


def load_natural_river_network(path, *, expected_sha256, expected_identity, hierarchy=None):
    result = load_bundle(path, expected_sha256=expected_sha256,
                         validator=lambda bundle: validate_natural_river_network(bundle, hierarchy=hierarchy))
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external natural network identity mismatch")
    return result
