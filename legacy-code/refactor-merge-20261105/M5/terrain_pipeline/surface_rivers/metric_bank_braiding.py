"""Bounded deterministic bank migration and braided-channel candidates."""

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from .metric_morphology_events import MorphologyEvent


def _positive(value, name, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.:
        raise ValueError(name + " must be finite positive")
    if maximum is not None and value > maximum:
        raise ValueError(name + " exceeds bound")
    return float(value)


def _nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0.:
        raise ValueError(name + " must be finite nonnegative")
    return float(value)


def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(name + " must be a lowercase SHA256")


def _mask(value, shape, name):
    if not isinstance(value, np.ndarray) or value.dtype != bool or value.shape != shape:
        raise ValueError(name + " must be a matching boolean array")


def _event_id(kind, graph, geometry, parameters):
    body = {"kind": kind, "graph": graph, "geometry": geometry, "parameters": parameters}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return kind + "-" + digest


@dataclass(frozen=True)
class BankPointbarConfig:
    max_erosion_depth_m: float = 0.25
    max_deposit_depth_m: float = 0.25
    porosity: float = 0.35
    influence_radius_m: float = 0.0

    def __post_init__(self):
        _positive(self.max_erosion_depth_m, "max_erosion_depth_m", 1000.)
        _positive(self.max_deposit_depth_m, "max_deposit_depth_m", 1000.)
        if isinstance(self.porosity, bool) or not isinstance(self.porosity, (int, float)) or not math.isfinite(self.porosity) or not 0. <= self.porosity < 1.:
            raise ValueError("porosity must be in [0, 1)")
        radius = self.influence_radius_m
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius < 0.:
            raise ValueError("influence_radius_m must be finite nonnegative")
        object.__setattr__(self, "max_erosion_depth_m", float(self.max_erosion_depth_m))
        object.__setattr__(self, "max_deposit_depth_m", float(self.max_deposit_depth_m))
        object.__setattr__(self, "porosity", float(self.porosity))
        object.__setattr__(self, "influence_radius_m", float(radius))


@dataclass(frozen=True)
class BraidedConfig:
    max_candidates: int = 3
    branch_offset_cells: int = 1
    max_deposit_depth_m: float = 0.2
    porosity: float = 0.35
    branch_fraction: float = 0.25

    def __post_init__(self):
        if type(self.max_candidates) is not int or self.max_candidates not in (2, 3):
            raise ValueError("max_candidates must be two or three")
        if type(self.branch_offset_cells) is not int or self.branch_offset_cells < 1 or self.branch_offset_cells > 8:
            raise ValueError("branch_offset_cells must be between one and eight")
        _positive(self.max_deposit_depth_m, "max_deposit_depth_m", 1000.)
        if isinstance(self.porosity, bool) or not isinstance(self.porosity, (int, float)) or not math.isfinite(self.porosity) or not 0. <= self.porosity < 1.:
            raise ValueError("porosity must be in [0, 1)")
        if isinstance(self.branch_fraction, bool) or not isinstance(self.branch_fraction, (int, float)) or not math.isfinite(self.branch_fraction) or not 0. < self.branch_fraction < .5:
            raise ValueError("branch_fraction must be in (0, 0.5)")
        object.__setattr__(self, "max_deposit_depth_m", float(self.max_deposit_depth_m))
        object.__setattr__(self, "porosity", float(self.porosity))
        object.__setattr__(self, "branch_fraction", float(self.branch_fraction))


def _terrain_cell(terrain, point):
    x, z = float(point[0]), float(point[1])
    column = int(round((x - terrain.x0_m) / terrain.dx_m))
    row = int(round((z - terrain.z0_m) / terrain.dz_m))
    if not (0 <= row < terrain.elevation_m.shape[0] and 0 <= column < terrain.elevation_m.shape[1]):
        raise ValueError("path point leaves terrain")
    if not terrain.valid_mask[row, column]:
        raise ValueError("path crosses unknown terrain")
    return row, column


def _validate_centerline(terrain, points):
    if not isinstance(points, np.ndarray) or points.dtype != np.float64 or points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        raise ValueError("centerline must be float64 [N,2] with at least three points")
    if not np.isfinite(points).all() or np.any(np.linalg.norm(np.diff(points, axis=0), axis=1) <= 0.):
        raise ValueError("centerline must contain finite distinct points")
    for point in points:
        _terrain_cell(terrain, point)


def _side_cell(terrain, point, tangent, side):
    normal = np.array((tangent[1], -tangent[0]), dtype=np.float64)
    normal /= max(float(np.linalg.norm(normal)), 1e-12)
    distance = max(terrain.dx_m, terrain.dz_m)
    return _terrain_cell(terrain, point + side * distance * normal)


def build_bank_pointbar_candidate(terrain, centerline_xz_m, parent_graph_identity_sha256,
                                  parent_geometry_identity_sha256, sediment_solid_m3, config=None):
    if not isinstance(terrain, TerrainGrid):
        raise ValueError("TerrainGrid required")
    config = BankPointbarConfig() if config is None else config
    if not isinstance(config, BankPointbarConfig):
        raise ValueError("BankPointbarConfig required")
    points = centerline_xz_m
    _validate_centerline(terrain, points)
    _sha(parent_graph_identity_sha256, "parent graph identity")
    _sha(parent_geometry_identity_sha256, "parent geometry identity")
    sediment = _nonnegative(sediment_solid_m3, "sediment_solid_m3")
    shape = terrain.elevation_m.shape
    erosion_mask = np.zeros(shape, dtype=bool)
    deposit_mask = np.zeros(shape, dtype=bool)
    erosion = np.zeros(shape, dtype=np.float64)
    deposit = np.zeros(shape, dtype=np.float64)
    curvature_records = []
    for index in range(1, len(points) - 1):
        incoming = points[index] - points[index - 1]
        outgoing = points[index + 1] - points[index]
        cross = float(incoming[0] * outgoing[1] - incoming[1] * outgoing[0])
        scale = max(float(np.linalg.norm(incoming) * np.linalg.norm(outgoing)), 1e-12)
        curvature = cross / scale
        if abs(curvature) <= 1e-12:
            continue
        tangent = incoming / max(float(np.linalg.norm(incoming)), 1e-12) + outgoing / max(float(np.linalg.norm(outgoing)), 1e-12)
        tangent /= max(float(np.linalg.norm(tangent)), 1e-12)
        outer = 1 if curvature > 0. else -1
        try:
            outer_cell = _side_cell(terrain, points[index], tangent, outer)
            inner_cell = _side_cell(terrain, points[index], tangent, -outer)
        except ValueError:
            continue
        outer_row, outer_column = outer_cell
        inner_row, inner_column = inner_cell
        if terrain.valid_mask[outer_cell]:
            erosion_mask[outer_cell] = True
            erosion[outer_cell] = max(erosion[outer_cell], config.max_erosion_depth_m)
        if terrain.valid_mask[inner_cell] and not erosion_mask[inner_cell]:
            deposit_mask[inner_cell] = True
            deposit[inner_cell] = max(deposit[inner_cell], config.max_deposit_depth_m)
        curvature_records.append((index, round(curvature, 12), outer_cell, inner_cell))
    erosion_volume = float(erosion.sum() * terrain.cell_area_m2)
    available = sediment + erosion_volume
    requested_fill = float((deposit * terrain.cell_area_m2).sum())
    deposited = min(available, requested_fill * (1. - config.porosity))
    if requested_fill > 0. and deposited < requested_fill * (1. - config.porosity):
        deposit *= deposited / (requested_fill * (1. - config.porosity))
    height_delta = deposit - erosion
    actual_deposit_volume = float((deposit * terrain.cell_area_m2 * (1. - config.porosity)).sum())
    unresolved = max(0., available - actual_deposit_volume)
    ledger = {"input_solid_m3": sediment, "eroded_solid_m3": erosion_volume,
              "deposited_solid_m3": actual_deposit_volume, "exported_solid_m3": 0.,
              "unresolved_solid_m3": unresolved}
    config_record = {"max_erosion_depth_m": config.max_erosion_depth_m,
                     "max_deposit_depth_m": config.max_deposit_depth_m,
                     "porosity": config.porosity, "influence_radius_m": config.influence_radius_m}
    parameters = {"algorithm": "bank-pointbar-v1", "config": config_record,
                  "curvature_records": [list(record) for record in curvature_records]}
    event = MorphologyEvent(_event_id("bank-migration", parent_graph_identity_sha256,
                                      parent_geometry_identity_sha256, parameters), "bank_migration",
                            parent_graph_identity_sha256, parent_geometry_identity_sha256, (), (), (), 0., sediment,
                            {"deposited_solid_m3": actual_deposit_volume, "exported_solid_m3": 0.,
                             "unresolved_solid_m3": unresolved, "cut_rock_m3": erosion_volume,
                             "fill_m3": float((deposit * terrain.cell_area_m2).sum()),
                             "porous_deposit_m3": float((deposit * terrain.cell_area_m2).sum())}, parameters)
    return {"schema": "terragenesis-bank-pointbar-candidate-v1", "status": "candidate",
            "height_delta_m": height_delta, "erosion_mask": erosion_mask, "deposit_mask": deposit_mask,
            "solid_ledger": ledger, "material_ledger": ledger, "event": event,
            "candidate": True, "hydraulic": False, "publishable": False}


def _validate_cells(terrain, path):
    if isinstance(path, np.ndarray):
        if path.dtype != np.float64 or path.ndim != 2 or path.shape[1] != 2:
            raise ValueError("main_path points must be float64 [N,2]")
        values = tuple(path[index] for index in range(len(path)))
    elif isinstance(path, (tuple, list)):
        values = tuple(path)
    else:
        values = ()
    if len(values) < 2:
        raise ValueError("main_path requires at least two cells or points")
    cells = []
    for value in values:
        if isinstance(value, tuple) and len(value) == 2 and all(type(item) is int for item in value):
            row, column = value
            if not (0 <= row < terrain.elevation_m.shape[0] and 0 <= column < terrain.elevation_m.shape[1]):
                raise ValueError("main_path cell outside terrain")
            cell = (row, column)
        else:
            array = np.asarray(value)
            if array.dtype != np.float64 or array.shape != (2,) or not np.isfinite(array).all():
                raise ValueError("main_path points must be float64 [2]")
            cell = _terrain_cell(terrain, array)
        if not terrain.valid_mask[cell]:
            raise ValueError("main_path crosses unknown terrain")
        cells.append(cell)
    if any(max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1 for a, b in zip(cells, cells[1:])):
        raise ValueError("main_path must use 8-neighbor steps")
    return tuple(cells)


def build_braided_candidate(terrain, main_path, water_mask, parent_graph_identity_sha256,
                            parent_geometry_identity_sha256, discharge_m3_s, sediment_solid_m3, config=None):
    if not isinstance(terrain, TerrainGrid):
        raise ValueError("TerrainGrid required")
    config = BraidedConfig() if config is None else config
    if not isinstance(config, BraidedConfig):
        raise ValueError("BraidedConfig required")
    _mask(water_mask, terrain.elevation_m.shape, "water_mask")
    if np.any(water_mask & ~terrain.valid_mask):
        raise ValueError("water_mask includes unknown terrain")
    path = _validate_cells(terrain, main_path)
    if any(not water_mask[cell] for cell in path):
        raise ValueError("main_path must remain in legal wet water")
    _sha(parent_graph_identity_sha256, "parent graph identity")
    _sha(parent_geometry_identity_sha256, "parent geometry identity")
    discharge = _nonnegative(discharge_m3_s, "discharge_m3_s")
    sediment = _nonnegative(sediment_solid_m3, "sediment_solid_m3")
    direction = np.array((path[-1][0] - path[0][0], path[-1][1] - path[0][1]), dtype=np.float64)
    if np.linalg.norm(direction) == 0.:
        raise ValueError("main_path direction is undefined")
    direction /= np.linalg.norm(direction)
    lateral = np.array((-direction[1], direction[0]))
    candidates = []
    for branch_index in range(config.max_candidates):
        offset = 0 if branch_index == 0 else (-1 if branch_index == 1 else 1)
        candidate = []
        for path_index, (row, column) in enumerate(path):
            if path_index in (0, len(path) - 1) or offset == 0:
                candidate.append((row, column))
                continue
            point = np.array((terrain.x0_m + column * terrain.dx_m, terrain.z0_m + row * terrain.dz_m))
            shifted = point + offset * config.branch_offset_cells * np.array((lateral[1] * terrain.dx_m, lateral[0] * terrain.dz_m))
            try:
                shifted_cell = _terrain_cell(terrain, shifted)
            except ValueError:
                shifted_cell = (row, column)
            candidate.append(shifted_cell if water_mask[shifted_cell] else (row, column))
        candidate = tuple(candidate)
        if any(not water_mask[cell] for cell in candidate) or any(max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1 for a, b in zip(candidate, candidate[1:])):
            continue
        if candidate not in [item["path_cells"] for item in candidates]:
            candidates.append({"path_cells": candidate, "offset": offset})
    if len(candidates) < 2:
        raise ValueError("fewer than two legal braided candidates")
    fractions = [1. - (len(candidates) - 1) * config.branch_fraction] + [config.branch_fraction] * (len(candidates) - 1)
    bar_mask = np.zeros(terrain.elevation_m.shape, dtype=bool)
    for first, second in zip(candidates, candidates[1:]):
        bar_mask[first["path_cells"][-1]] = True
        bar_mask[second["path_cells"][-1]] = True
    capacity = terrain.cell_area_m2 * config.max_deposit_depth_m * (1. - config.porosity)
    deposited = min(sediment, capacity * float(np.count_nonzero(bar_mask)))
    unresolved = sediment - deposited
    height_delta = np.zeros(terrain.elevation_m.shape, dtype=np.float64)
    if np.count_nonzero(bar_mask):
        height_delta[bar_mask] = deposited / np.count_nonzero(bar_mask) / terrain.cell_area_m2 / (1. - config.porosity)
    fractions_record = [round(value, 12) for value in fractions]
    parameters = {"algorithm": "braided-v1", "candidate_count": len(candidates),
                  "flow_fractions": fractions_record, "discharge_m3_s": discharge}
    event = MorphologyEvent(_event_id("bifurcation", parent_graph_identity_sha256,
                                      parent_geometry_identity_sha256, parameters), "bifurcation",
                            parent_graph_identity_sha256, parent_geometry_identity_sha256, (),
                            tuple("braid-" + str(index) for index in range(1, len(candidates))), (), discharge,
                            sediment, {"deposited_solid_m3": deposited, "exported_solid_m3": 0.,
                                       "unresolved_solid_m3": unresolved, "cut_rock_m3": 0.,
                                       "fill_m3": deposited / (1. - config.porosity),
                                       "porous_deposit_m3": deposited / (1. - config.porosity)},
                            parameters)
    return {"schema": "terragenesis-braided-candidate-v1", "status": "candidate",
            "candidate_paths": tuple(item["path_cells"] for item in candidates),
            "braid_candidates": tuple(candidates), "flow_split": tuple(fractions),
            "bar_mask": bar_mask, "deposit_mask": bar_mask.copy(), "height_delta_m": height_delta,
            "solid_ledger": {"input_solid_m3": sediment, "deposited_solid_m3": deposited,
                             "exported_solid_m3": 0., "unresolved_solid_m3": unresolved},
            "event": event, "candidate": True, "hydraulic": False,
            "routing_graph_written": False, "publishable": False}
