"""Bounded deterministic cutoff candidates on a metric river centerline."""

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .metric_contracts import TerrainGrid
from .metric_morphology_events import MorphologyEvent


@dataclass(frozen=True)
class CutoffConfig:
    neck_distance_m: float = 32.0
    min_loop_length_m: float = 64.0
    min_node_gap: int = 2
    max_candidates: int = 256
    max_bed_rise_m: float = 0.0
    seed: int = 0

    def __post_init__(self):
        for name in ("neck_distance_m", "min_loop_length_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.:
                raise ValueError(name + " must be finite positive")
            object.__setattr__(self, name, float(value))
        if type(self.min_node_gap) is not int or self.min_node_gap < 2:
            raise ValueError("min_node_gap must be an integer of at least two")
        if type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 100000:
            raise ValueError("max_candidates must be bounded positive integer")
        if isinstance(self.max_bed_rise_m, bool) or not isinstance(self.max_bed_rise_m, (int, float)) or not math.isfinite(self.max_bed_rise_m) or self.max_bed_rise_m < 0.:
            raise ValueError("max_bed_rise_m must be finite nonnegative")
        object.__setattr__(self, "max_bed_rise_m", float(self.max_bed_rise_m))
        if type(self.seed) is not int or not 0 <= self.seed <= 0xFFFFFFFF:
            raise ValueError("seed must be uint32")


def _finite_transfer(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)) or not math.isfinite(value) or value < 0.:
        raise ValueError(name + " must be finite nonnegative")
    return float(value)


def _sample_grid(terrain, points):
    height = terrain.elevation_m
    rows, columns = height.shape
    points = np.asarray(points, dtype=np.float64)
    rows_position = (points[:, 1] - terrain.z0_m) / terrain.dz_m
    columns_position = (points[:, 0] - terrain.x0_m) / terrain.dx_m
    if (not np.isfinite(points).all() or np.any(rows_position < -1e-9) or
            np.any(columns_position < -1e-9) or np.any(rows_position > rows - 1 + 1e-9) or
            np.any(columns_position > columns - 1 + 1e-9)):
        return None
    row0 = np.floor(np.clip(rows_position, 0., rows - 1.)).astype(np.int64)
    column0 = np.floor(np.clip(columns_position, 0., columns - 1.)).astype(np.int64)
    row1 = np.minimum(row0 + 1, rows - 1)
    column1 = np.minimum(column0 + 1, columns - 1)
    valid = (terrain.valid_mask[row0, column0] & terrain.valid_mask[row1, column0] &
             terrain.valid_mask[row0, column1] & terrain.valid_mask[row1, column1])
    row_fraction = rows_position - row0
    column_fraction = columns_position - column0
    values = ((1. - row_fraction) * (1. - column_fraction) * height[row0, column0] +
              row_fraction * (1. - column_fraction) * height[row1, column0] +
              (1. - row_fraction) * column_fraction * height[row0, column1] +
              row_fraction * column_fraction * height[row1, column1])
    if np.any(~valid) or not np.isfinite(values).all():
        return None
    return values


def _dense_segment(start, end, spacing):
    length = float(np.linalg.norm(end - start))
    count = max(1, int(math.ceil(length / spacing)))
    return np.linspace(start, end, count + 1, dtype=np.float64)


def _orientation(first, second, third):
    first_delta = second - first
    second_delta = third - first
    value = float(first_delta[0] * second_delta[1] - first_delta[1] * second_delta[0])
    if abs(value) <= 1e-10:
        return 0
    return 1 if value > 0. else -1


def _segments_intersect(first, second, third, fourth):
    orientations = (_orientation(first, second, third), _orientation(first, second, fourth),
                    _orientation(third, fourth, first), _orientation(third, fourth, second))
    if orientations[0] * orientations[1] < 0 and orientations[2] * orientations[3] < 0:
        return True
    def on_segment(start, end, point):
        if _orientation(start, end, point) != 0:
            return False
        return (min(start[0], end[0]) - 1e-10 <= point[0] <= max(start[0], end[0]) + 1e-10 and
                min(start[1], end[1]) - 1e-10 <= point[1] <= max(start[1], end[1]) + 1e-10)

    return (on_segment(first, second, third) or on_segment(first, second, fourth) or
            on_segment(third, fourth, first) or on_segment(third, fourth, second))


def _crosses_centerline(shortcut_start, shortcut_end, centerline, start_index, end_index):
    for index in range(len(centerline) - 1):
        if index in (start_index - 1, start_index, end_index - 1, end_index):
            continue
        if _segments_intersect(shortcut_start, shortcut_end, centerline[index], centerline[index + 1]):
            return True
    return False


def _edge_span(edge_ids, start_index, end_index):
    return tuple(edge_ids[start_index:end_index])


def _candidate_event(parent_graph, parent_geometry, edge_ids, start, end, loop_length,
                     shortcut_length, sinuosity_before, water_transfer, sediment_transfer,
                     config):
    body = {"parent_graph_identity_sha256": parent_graph,
            "parent_geometry_identity_sha256": parent_geometry, "edge_ids": list(edge_ids),
            "start": start, "end": end, "seed": config.seed}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    added_edge = "cutoff-" + digest[:24]
    loop_edges = _edge_span(edge_ids, start, end)
    event = MorphologyEvent(
        "cutoff-" + digest, "cutoff", parent_graph, parent_geometry,
        loop_edges, (added_edge,), loop_edges, water_transfer, sediment_transfer, {},
        {"algorithm": "cutoff-v1", "neck_distance_m": config.neck_distance_m,
         "min_loop_length_m": config.min_loop_length_m, "min_node_gap": config.min_node_gap,
         "max_bed_rise_m": config.max_bed_rise_m, "seed": config.seed,
         "neck_indices": [start, end], "loop_length_m": loop_length,
         "shortcut_length_m": shortcut_length, "sinuosity_before": sinuosity_before,
         "sinuosity_after": 1.0, "lake_candidate": True})
    return event


def find_cutoff_candidate(terrain: TerrainGrid, centerline_xz_m: np.ndarray,
                          edge_ids: tuple[str, ...], parent_graph_identity_sha256: str,
                          parent_geometry_identity_sha256: str, water_transfer_m3,
                          sediment_transfer_solid_m3, config=None) -> dict:
    if not isinstance(terrain, TerrainGrid):
        raise ValueError("TerrainGrid required")
    if config is None:
        config = CutoffConfig()
    if not isinstance(config, CutoffConfig):
        raise ValueError("CutoffConfig required")
    points = np.asarray(centerline_xz_m)
    if points.dtype != np.float64 or points.ndim != 2 or points.shape[1] != 2 or len(points) < 5:
        raise ValueError("centerline must be float64 [N,2] with at least five points")
    if not np.isfinite(points).all():
        raise ValueError("centerline must be finite")
    if np.any(np.linalg.norm(np.diff(points, axis=0), axis=1) <= 0.):
        raise ValueError("centerline adjacent nodes must be distinct")
    if not isinstance(edge_ids, tuple) or len(edge_ids) != len(points) - 1 or any(not isinstance(value, str) or not value for value in edge_ids):
        raise ValueError("edge_ids must contain one unique nonempty ID per centerline edge")
    if len(set(edge_ids)) != len(edge_ids):
        raise ValueError("edge_ids must be unique")
    water_transfer = _finite_transfer(water_transfer_m3, "water_transfer_m3")
    sediment_transfer = _finite_transfer(sediment_transfer_solid_m3, "sediment_transfer_solid_m3")
    if not isinstance(parent_graph_identity_sha256, str) or len(parent_graph_identity_sha256) != 64 or any(c not in "0123456789abcdef" for c in parent_graph_identity_sha256):
        raise ValueError("parent graph identity must be lowercase SHA256")
    if not isinstance(parent_geometry_identity_sha256, str) or len(parent_geometry_identity_sha256) != 64 or any(c not in "0123456789abcdef" for c in parent_geometry_identity_sha256):
        raise ValueError("parent geometry identity must be lowercase SHA256")
    centerline_bed = _sample_grid(terrain, points)
    if centerline_bed is None:
        raise ValueError("centerline leaves terrain valid mask")
    cumulative = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    spacing = min(terrain.dx_m, terrain.dz_m) * .25
    candidates = []
    for start in range(len(points) - config.min_node_gap):
        for end in range(start + config.min_node_gap, len(points)):
            neck_length = float(np.linalg.norm(points[end] - points[start]))
            loop_length = float(cumulative[end] - cumulative[start])
            shortcut_length = neck_length
            if neck_length > config.neck_distance_m or loop_length - shortcut_length < config.min_loop_length_m:
                continue
            shortcut = _dense_segment(points[start], points[end], spacing)
            shortcut_bed = _sample_grid(terrain, shortcut)
            if shortcut_bed is None or float(np.max(shortcut_bed) - max(centerline_bed[start], centerline_bed[end])) > config.max_bed_rise_m + 1e-9:
                continue
            if _crosses_centerline(points[start], points[end], points, start, end):
                continue
            candidates.append((loop_length - shortcut_length, start, end, loop_length, shortcut_length, shortcut))
    candidates.sort(key=lambda value: (-value[0], value[1], value[2]))
    candidates = candidates[:config.max_candidates]
    if not candidates:
        return {"status": "rejected", "reason": "no_valid_cutoff_neck", "event": None,
                "capabilities": {"topology_mutation": False, "hydrodynamics": False,
                                  "sediment_recompute": False}}
    saving, start, end, loop_length, shortcut_length, shortcut = candidates[0]
    loop = points[start:end + 1].copy()
    event = _candidate_event(parent_graph_identity_sha256, parent_geometry_identity_sha256,
                             edge_ids, start, end, loop_length, shortcut_length,
                             loop_length / shortcut_length, water_transfer, sediment_transfer, config)
    return {"status": "candidate", "shortcut_xz_m": shortcut, "loop_xz_m": loop,
            "neck_indices": (start, end), "sinuosity_before": loop_length / shortcut_length,
            "sinuosity_after": 1.0, "lake_candidate": True, "event": event,
            "capabilities": {"topology_mutation": False, "hydrodynamics": False,
                              "sediment_recompute": False}, "saving_m": saving}
