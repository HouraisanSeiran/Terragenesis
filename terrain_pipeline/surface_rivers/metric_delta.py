"""Bounded deterministic delta-growth candidates on a metric terrain grid."""

from dataclasses import dataclass
import hashlib
import math
import random

import numpy as np

from .metric_contracts import TerrainGrid
from .metric_morphology_events import MorphologyEvent


def _bounded_integer(value, name, lower, upper):
    if isinstance(value, bool) or type(value) is not int or not lower <= value <= upper:
        raise ValueError(name + " outside bounded integer range")
    return value


@dataclass(frozen=True)
class DeltaConfig:
    max_radius_cells: int = 8
    max_deposit_depth_m: float = 1.0
    porosity: float = 0.35
    seed: int = 0
    max_distributary_candidates: int = 8

    def __post_init__(self):
        _bounded_integer(self.max_radius_cells, "max_radius_cells", 1, 4096)
        _bounded_integer(self.max_distributary_candidates, "max_distributary_candidates", 1, 4096)
        if isinstance(self.max_deposit_depth_m, bool) or not isinstance(self.max_deposit_depth_m, (int, float)):
            raise ValueError("max_deposit_depth_m must be numeric")
        if not math.isfinite(self.max_deposit_depth_m) or self.max_deposit_depth_m <= 0.:
            raise ValueError("max_deposit_depth_m must be finite and positive")
        if isinstance(self.porosity, bool) or not isinstance(self.porosity, (int, float)):
            raise ValueError("porosity must be numeric")
        if not math.isfinite(self.porosity) or not 0. <= self.porosity < 1.:
            raise ValueError("porosity must be in [0, 1)")
        _bounded_integer(self.seed, "seed", 0, 0xffffffff)
        object.__setattr__(self, "max_deposit_depth_m", float(self.max_deposit_depth_m))
        object.__setattr__(self, "porosity", float(self.porosity))


def _cell(value, shape, name):
    if (not isinstance(value, tuple) or len(value) != 2 or
            any(isinstance(item, bool) or type(item) is not int for item in value)):
        raise ValueError(name + " must be an integer row/column tuple")
    if not 0 <= value[0] < shape[0] or not 0 <= value[1] < shape[1]:
        raise ValueError(name + " outside grid")
    return value


def _mask(value, shape, name):
    if not isinstance(value, np.ndarray) or value.dtype != bool or value.shape != shape:
        raise ValueError(name + " must be a matching boolean array")


def _neighbors(cell, shape, diagonal):
    row, column = cell
    offsets = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
    if not diagonal:
        offsets = ((-1, 0), (0, -1), (0, 1), (1, 0))
    for row_offset, column_offset in offsets:
        candidate = (row + row_offset, column + column_offset)
        if 0 <= candidate[0] < shape[0] and 0 <= candidate[1] < shape[1]:
            yield candidate


def _water_component(water_mask, mouth):
    component = {mouth}
    pending = [mouth]
    while pending:
        current = pending.pop()
        for candidate in _neighbors(current, water_mask.shape, False):
            if candidate not in component and water_mask[candidate]:
                component.add(candidate)
                pending.append(candidate)
    result = np.zeros(water_mask.shape, dtype=bool)
    for row, column in component:
        result[row, column] = True
    return result, component


def _validate_sha(value, name):
    if (not isinstance(value, str) or len(value) != 64 or
            any(character not in "0123456789abcdef" for character in value)):
        raise ValueError(name + " must be a lowercase SHA256")


def _candidate_paths(mouth, direction, component, config, shape):
    randomizer = random.Random(config.seed)
    forward_row, forward_column = direction
    lateral_row, lateral_column = -forward_column, forward_row
    candidates = []
    seen_paths = set()
    candidate_limit = config.max_distributary_candidates
    for index in range(candidate_limit):
        side = (index - (candidate_limit - 1) / 2.)
        side += (randomizer.random() - .5) * .6
        path = [mouth]
        visited = {mouth}
        current = mouth
        for step in range(1, config.max_radius_cells + 1):
            target = (round(mouth[0] + forward_row * step + lateral_row * side * step / max(1, config.max_radius_cells)),
                      round(mouth[1] + forward_column * step + lateral_column * side * step / max(1, config.max_radius_cells)))
            choices = [cell for cell in _neighbors(current, shape, True)
                       if cell in component and cell not in visited]
            if not choices:
                break
            # Prefer forward, unvisited cells close to the deterministic target.  The
            # forward tie-break prevents a candidate from folding back toward its mouth.
            next_cell = min(
                choices,
                key=lambda cell: (
                    abs(cell[0] - target[0]) + abs(cell[1] - target[1]),
                    -((cell[0] - mouth[0]) * forward_row + (cell[1] - mouth[1]) * forward_column),
                    cell,
                ),
            )
            path.append(next_cell)
            visited.add(next_cell)
            current = next_cell
        frozen = tuple(path)
        if len(frozen) >= 2 and frozen not in seen_paths:
            seen_paths.add(frozen)
            candidates.append({"edge_id": "delta-" + format(len(candidates), "04x"),
                               "polyline": frozen})
    return candidates


def _allocate_weighted_capacity(weights, capacity, total):
    """Allocate total solid volume without losing mass to sequential clamping."""
    allocation = {cell: 0. for cell in weights}
    remaining = float(total)
    active = set(weights)
    tolerance = 1e-12 * max(1., float(total))
    while active and remaining > tolerance:
        weight_sum = math.fsum(weights[cell] for cell in sorted(active))
        if not math.isfinite(weight_sum) or weight_sum <= 0.:
            break
        saturated = []
        for cell in sorted(active):
            share = remaining * weights[cell] / weight_sum
            room = capacity - allocation[cell]
            if share >= room - tolerance:
                allocation[cell] += max(0., room)
                saturated.append(cell)
        if not saturated:
            for cell in sorted(active):
                allocation[cell] += remaining * weights[cell] / weight_sum
            remaining = 0.
            break
        remaining = float(total) - math.fsum(allocation[cell] for cell in sorted(allocation))
        for cell in saturated:
            active.remove(cell)
    return allocation


def build_delta_candidate(terrain: TerrainGrid, land_mask: np.ndarray, water_mask: np.ndarray,
                          main_path: tuple[tuple[int, int], ...], sediment_solid_m3: float,
                          parent_graph_identity_sha256: str, parent_geometry_identity_sha256: str,
                          config: DeltaConfig = DeltaConfig()):
    if not isinstance(terrain, TerrainGrid) or not isinstance(config, DeltaConfig):
        raise ValueError("TerrainGrid and DeltaConfig required")
    shape = terrain.elevation_m.shape
    _mask(land_mask, shape, "land_mask")
    _mask(water_mask, shape, "water_mask")
    if np.any(land_mask & water_mask):
        raise ValueError("land_mask and water_mask overlap")
    if np.any((land_mask | water_mask) & ~terrain.valid_mask):
        raise ValueError("land/water classification includes unknown terrain")
    if not isinstance(main_path, tuple) or len(main_path) < 2:
        raise ValueError("main_path requires at least two cells")
    path = tuple(_cell(cell, shape, "main_path cell") for cell in main_path)
    if any(not terrain.valid_mask[cell] for cell in path):
        raise ValueError("main_path crosses unknown terrain")
    for first, second in zip(path, path[1:]):
        if max(abs(first[0] - second[0]), abs(first[1] - second[1])) != 1:
            raise ValueError("main_path must use 8-neighbor steps")
    if (isinstance(sediment_solid_m3, bool) or not isinstance(sediment_solid_m3, (int, float)) or
            not math.isfinite(sediment_solid_m3) or sediment_solid_m3 < 0.):
        raise ValueError("sediment_solid_m3 must be finite and nonnegative")
    _validate_sha(parent_graph_identity_sha256, "parent graph identity")
    _validate_sha(parent_geometry_identity_sha256, "parent geometry identity")
    transitions = [(first, second) for first, second in zip(path, path[1:])
                   if land_mask[first] and water_mask[second]]
    if not transitions:
        raise ValueError("main_path requires a land-to-water mouth")
    mouth = transitions[-1][1]
    component_mask, component = _water_component(water_mask, mouth)
    direction = (mouth[0] - transitions[-1][0][0], mouth[1] - transitions[-1][0][1])
    candidates = _candidate_paths(mouth, direction, component, config, shape)
    weights = {}
    for row, column in component:
        distance = max(abs(row - mouth[0]), abs(column - mouth[1]))
        if distance > config.max_radius_cells:
            continue
        forward = (row - mouth[0]) * direction[0] + (column - mouth[1]) * direction[1]
        lateral = abs((row - mouth[0]) * (-direction[1]) + (column - mouth[1]) * direction[0])
        weights[(row, column)] = max(0., config.max_radius_cells - distance + .01) * max(.05, 1. + forward) / (1. + lateral)
    deposit_mask = np.zeros(shape, dtype=bool)
    height_delta = np.zeros(shape, dtype=np.float64)
    capacity_solid = terrain.cell_area_m2 * config.max_deposit_depth_m * (1. - config.porosity)
    allocation = _allocate_weighted_capacity(weights, capacity_solid, sediment_solid_m3)
    deposited = 0.
    for cell in sorted(allocation):
        amount = allocation[cell]
        if amount <= 0.:
            continue
        deposit_mask[cell] = True
        deposited += amount
        height_delta[cell] = amount / ((1. - config.porosity) * terrain.cell_area_m2)
    unresolved = max(0., float(sediment_solid_m3) - deposited)
    # The candidate intentionally keeps this inventory unresolved: it has not yet
    # been coupled to an outlet boundary, wave/tidal transport, or a sediment solver.
    porous = deposited / (1. - config.porosity)
    ledger = {"deposited_solid_m3": deposited, "exported_solid_m3": 0., "unresolved_solid_m3": unresolved,
              "cut_rock_m3": 0., "fill_m3": 0., "porous_deposit_m3": porous}
    config_record = {"max_radius_cells": config.max_radius_cells, "max_deposit_depth_m": config.max_deposit_depth_m,
                     "porosity": config.porosity, "seed": config.seed,
                     "max_distributary_candidates": config.max_distributary_candidates}
    event_seed = repr((parent_graph_identity_sha256, parent_geometry_identity_sha256, mouth, config_record,
                       tuple((candidate["edge_id"], candidate["polyline"]) for candidate in candidates))).encode()
    event_id = "delta-" + hashlib.sha256(event_seed).hexdigest()
    event = MorphologyEvent(event_id, "delta_growth", parent_graph_identity_sha256,
                            parent_geometry_identity_sha256, (), (), (), 0., float(sediment_solid_m3),
                            ledger, {"mouth": list(mouth), "config": config_record,
                                     "candidate_count": len(candidates),
                                     "topology_status": "candidate_geometry_only"})
    return {"schema": "terragenesis-delta-candidate-v1", "status": "candidate", "mouth_cell": mouth,
            "height_delta_m": height_delta, "deposit_mask": deposit_mask,
            "water_component_mask": component_mask, "distributary_candidates": candidates,
            "material_ledger": ledger, "event": event, "hydraulic": False,
            "natural_outlet": False, "publishable": False}
