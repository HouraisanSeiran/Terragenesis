"""Bounded metric alluvial-fan and floodplain visual candidates."""

from dataclasses import dataclass
import hashlib
import json
import math

import numpy as np

from .metric_contracts import TerrainGrid
from .metric_morphology_events import MorphologyEvent


def _number(value, name, nonnegative=False, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value) or (nonnegative and value < 0.) or (positive and value <= 0.):
        raise ValueError(name + " outside finite bounds")
    return value


def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(name + " must be a lowercase SHA256")


def _point(value, name):
    if not isinstance(value, (tuple, list, np.ndarray)) or len(value) != 2:
        raise ValueError(name + " must be an XZ point")
    point = tuple(_number(item, name + " coordinate") for item in value)
    if not np.isfinite(point).all():
        raise ValueError(name + " must be finite")
    return point


def _polyline(value, name):
    if not isinstance(value, (tuple, list, np.ndarray)) or len(value) < 2:
        raise ValueError(name + " requires at least two points")
    return tuple(_point(point, name + " point") for point in value)


def _config_record(config):
    return {name: getattr(config, name) for name in config.__dataclass_fields__}


def _nearest_cell(terrain, point, name):
    column = int(round((point[0] - terrain.x0_m) / terrain.dx_m))
    row = int(round((point[1] - terrain.z0_m) / terrain.dz_m))
    if not (0 <= row < terrain.elevation_m.shape[0] and 0 <= column < terrain.elevation_m.shape[1]):
        raise ValueError(name + " outside terrain")
    if not terrain.valid_mask[row, column]:
        raise ValueError(name + " lies on unknown terrain")
    return row, column


def _event_id(event_type, parent_graph, parent_geometry, parameters, ledger):
    payload = json.dumps({"event_type": event_type, "parent_graph": parent_graph,
                          "parent_geometry": parent_geometry, "parameters": parameters,
                          "ledger": ledger}, sort_keys=True, separators=(",", ":")).encode()
    return event_type + "-" + hashlib.sha256(payload).hexdigest()


def _capabilities():
    return {"hydraulic": False, "natural_outlet": False, "publishable": False}


@dataclass(frozen=True)
class FanFloodplainConfig:
    max_fan_radius_m: float = 32.
    fan_half_angle_deg: float = 55.
    max_deposit_depth_m: float = 1.
    porosity: float = .35
    bank_height_m: float = 2.
    max_floodplain_half_width_m: float = 24.

    def __post_init__(self):
        for name in ("max_fan_radius_m", "max_deposit_depth_m", "bank_height_m", "max_floodplain_half_width_m"):
            value = _number(getattr(self, name), name, positive=True)
            if value > 1e6:
                raise ValueError(name + " exceeds resource bound")
            object.__setattr__(self, name, value)
        angle = _number(self.fan_half_angle_deg, "fan_half_angle_deg", positive=True)
        if angle >= 90.:
            raise ValueError("fan_half_angle_deg must be below 90 degrees")
        object.__setattr__(self, "fan_half_angle_deg", angle)
        porosity = _number(self.porosity, "porosity", nonnegative=True)
        if porosity >= 1.:
            raise ValueError("porosity must be below one")
        object.__setattr__(self, "porosity", porosity)


def _fan_cells(terrain, apex, direction, config):
    rows, columns = terrain.elevation_m.shape
    apex_height = terrain.elevation_m[_nearest_cell(terrain, apex, "apex")]
    direction = np.asarray(direction, dtype=np.float64)
    length = float(np.linalg.norm(direction))
    if length <= 0.:
        raise ValueError("flow_direction_xz must be nonzero")
    direction /= length
    half_angle = math.radians(config.fan_half_angle_deg)
    cells = []
    for row in range(rows):
        for column in range(columns):
            if not terrain.valid_mask[row, column]:
                continue
            point = np.array((terrain.x0_m + column * terrain.dx_m,
                              terrain.z0_m + row * terrain.dz_m))
            offset = point - np.asarray(apex)
            distance = float(np.linalg.norm(offset))
            if distance <= 0. or distance > config.max_fan_radius_m:
                continue
            forward = float(np.dot(offset, direction))
            if forward <= 0. or forward / distance < math.cos(half_angle):
                continue
            if terrain.elevation_m[row, column] > apex_height + 1e-10:
                continue
            slope_factor = max(0., (apex_height - terrain.elevation_m[row, column]) / max(apex_height - np.min(terrain.elevation_m[terrain.valid_mask]), 1e-9))
            weight = max(1e-12, forward / config.max_fan_radius_m) * (0.25 + slope_factor)
            cells.append(((row, column), weight))
    return tuple(cells)


def _allocate(cells, capacity, total):
    allocation = {cell: 0. for cell, _ in cells}
    active = {cell for cell, _ in cells}
    weights = dict(cells)
    remaining = float(total)
    tolerance = 1e-12 * max(1., remaining)
    while active and remaining > tolerance:
        weight_sum = math.fsum(weights[cell] for cell in sorted(active))
        if weight_sum <= 0. or not math.isfinite(weight_sum):
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
            break
        remaining = float(total) - math.fsum(allocation.values())
        for cell in saturated:
            active.remove(cell)
    return allocation


def build_alluvial_fan_candidate(terrain, apex_xz_m, flow_direction_xz, sediment_solid_m3,
                                 parent_graph_identity_sha256, parent_geometry_identity_sha256,
                                 config=FanFloodplainConfig()):
    if not isinstance(terrain, TerrainGrid) or not isinstance(config, FanFloodplainConfig):
        raise ValueError("TerrainGrid and FanFloodplainConfig required")
    apex = _point(apex_xz_m, "apex_xz_m")
    direction = _point(flow_direction_xz, "flow_direction_xz")
    sediment = _number(sediment_solid_m3, "sediment_solid_m3", nonnegative=True)
    _sha(parent_graph_identity_sha256, "parent graph identity")
    _sha(parent_geometry_identity_sha256, "parent geometry identity")
    cells = _fan_cells(terrain, apex, direction, config)
    capacity = terrain.cell_area_m2 * config.max_deposit_depth_m * (1. - config.porosity)
    allocation = _allocate(cells, capacity, sediment)
    shape = terrain.elevation_m.shape
    footprint = np.zeros(shape, dtype=bool)
    deposit_mask = np.zeros(shape, dtype=bool)
    height_delta = np.zeros(shape, dtype=np.float64)
    for cell, _ in cells:
        footprint[cell] = True
        if allocation[cell] > 0.:
            deposit_mask[cell] = True
            height_delta[cell] = allocation[cell] / ((1. - config.porosity) * terrain.cell_area_m2)
    deposited = math.fsum(allocation.values())
    unresolved = max(0., sediment - deposited)
    ledger = {"deposited_solid_m3": deposited, "exported_solid_m3": 0.,
              "unresolved_solid_m3": unresolved, "cut_rock_m3": 0., "fill_m3": 0.,
              "porous_deposit_m3": deposited / (1. - config.porosity)}
    parameters = {"apex_xz_m": list(apex), "flow_direction_xz": list(direction),
                  "config": _config_record(config), "footprint_cell_count": int(footprint.sum()),
                  "geometry_status": "bounded_candidate_only"}
    event = MorphologyEvent(_event_id("alluvial_fan", parent_graph_identity_sha256,
                                       parent_geometry_identity_sha256, parameters, ledger),
                            "alluvial_fan", parent_graph_identity_sha256,
                            parent_geometry_identity_sha256, (), (), (), 0., sediment, ledger, parameters)
    return {"schema": "terragenesis-metric-fan-candidate-v1", "status": "candidate",
            "apex_xz_m": apex, "height_delta_m": height_delta, "deposit_mask": deposit_mask,
            "footprint": footprint, "material_ledger": ledger, "event": event,
            "hydraulic": False, "natural_outlet": False, "publishable": False,
            "capabilities": _capabilities()}


def _segment_distance(point, start, end):
    vector = end - start
    length_squared = float(np.dot(vector, vector))
    if length_squared == 0.:
        return float(np.linalg.norm(point - start)), 0.
    fraction = float(np.clip(np.dot(point - start, vector) / length_squared, 0., 1.))
    return float(np.linalg.norm(point - (start + fraction * vector))), fraction


def build_floodplain_candidate(terrain, centerline_xz_m, water_depth_m,
                               parent_graph_identity_sha256, parent_geometry_identity_sha256,
                               config=FanFloodplainConfig()):
    if not isinstance(terrain, TerrainGrid) or not isinstance(config, FanFloodplainConfig):
        raise ValueError("TerrainGrid and FanFloodplainConfig required")
    centerline = _polyline(centerline_xz_m, "centerline_xz_m")
    depth = _number(water_depth_m, "water_depth_m", nonnegative=True)
    _sha(parent_graph_identity_sha256, "parent graph identity")
    _sha(parent_geometry_identity_sha256, "parent geometry identity")
    for start, end in zip(centerline, centerline[1:]):
        distance = float(np.linalg.norm(np.asarray(end) - np.asarray(start)))
        if distance <= 0.:
            raise ValueError("centerline must not repeat points")
        for fraction in np.linspace(0., 1., max(2, int(math.ceil(distance / min(terrain.dx_m, terrain.dz_m))) + 1)):
            _nearest_cell(terrain, tuple(np.asarray(start) + fraction * (np.asarray(end) - np.asarray(start))), "centerline")
    shape = terrain.elevation_m.shape
    inundation = np.zeros(shape, dtype=bool)
    height_delta = np.zeros(shape, dtype=np.float64)
    storage = 0.
    effective_depth = min(depth, config.bank_height_m)
    points = [np.asarray(point, dtype=np.float64) for point in centerline]
    for row in range(shape[0]):
        for column in range(shape[1]):
            if not terrain.valid_mask[row, column]:
                continue
            point = np.array((terrain.x0_m + column * terrain.dx_m, terrain.z0_m + row * terrain.dz_m))
            nearest_distance = math.inf
            bed = None
            for start, end in zip(points, points[1:]):
                distance, fraction = _segment_distance(point, start, end)
                if distance < nearest_distance:
                    nearest_distance = distance
                    first = _nearest_cell(terrain, tuple(start), "centerline")
                    second = _nearest_cell(terrain, tuple(end), "centerline")
                    bed = (1. - fraction) * terrain.elevation_m[first] + fraction * terrain.elevation_m[second]
            if nearest_distance > config.max_floodplain_half_width_m or bed is None:
                continue
            local_depth = effective_depth + bed - terrain.elevation_m[row, column]
            if local_depth <= 0. or local_depth > config.bank_height_m + 1e-10:
                continue
            inundation[row, column] = True
            storage += local_depth * terrain.cell_area_m2
    parameters = {"centerline_xz_m": [list(point) for point in centerline], "water_depth_m": depth,
                  "effective_depth_m": effective_depth, "config": _config_record(config),
                  "geometry_status": "bounded_wet_footprint_only"}
    ledger = {"deposited_solid_m3": 0., "exported_solid_m3": 0., "unresolved_solid_m3": 0.,
              "cut_rock_m3": 0., "fill_m3": 0., "porous_deposit_m3": 0.}
    event = MorphologyEvent(_event_id("floodplain_inundation", parent_graph_identity_sha256,
                                       parent_geometry_identity_sha256, parameters, ledger),
                            "floodplain_inundation", parent_graph_identity_sha256,
                            parent_geometry_identity_sha256, (), (), (), 0., 0., ledger, parameters)
    return {"schema": "terragenesis-metric-floodplain-candidate-v1", "status": "candidate",
            "inundation_mask": inundation, "height_delta_m": height_delta,
            "storage_proxy_m3": float(storage), "event": event, "material_ledger": ledger,
            "hydraulic": False, "natural_outlet": False, "publishable": False,
            "capabilities": _capabilities()}
