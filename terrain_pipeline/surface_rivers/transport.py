"""Finite, conservative sediment routing on an explicitly wet ocean grid.

This is an isolated project approximation, not a DeltaRCM implementation.
"""
from dataclasses import dataclass
from collections import deque
import math
import numpy as np


@dataclass(frozen=True)
class TransportInput:
    height: np.ndarray
    land_mask: np.ndarray
    ocean_mask: np.ndarray
    depth: np.ndarray
    flow_direction: np.ndarray  # (row, column) components per cell
    flow_speed: np.ndarray
    boundary_mask: np.ndarray  # open ocean cells on the domain perimeter
    main_path: tuple[tuple[int, int], ...]
    sediment_solid: float
    settling_velocity: float
    depth_exponent: float = 1.0  # 1: suspended-like; 2: bedload-like
    porosity: float = .35
    spacing_blocks: float = 1.0
    max_steps: int = 24


@dataclass(frozen=True)
class TransportResult:
    height_delta: np.ndarray
    mobile_solid: np.ndarray
    deposited_solid: float
    exported_solid: float
    mouth: tuple[int, int] | None


def route_sediment(inputs: TransportInput) -> TransportResult:
    """Move solid volume along wet 8-neighbor paths, retaining unresolved inventory."""
    height = np.asarray(inputs.height, dtype=float)
    if height.ndim != 2 or not np.isfinite(height).all():
        raise ValueError("Height must be a finite 2D grid")
    shape = height.shape
    land = _grid(inputs.land_mask, shape, bool)
    ocean = _grid(inputs.ocean_mask, shape, bool)
    depth = _grid(inputs.depth, shape, float)
    speed = _grid(inputs.flow_speed, shape, float)
    boundary = _grid(inputs.boundary_mask, shape, bool)
    direction = np.asarray(inputs.flow_direction, dtype=float)
    if direction.shape != shape + (2,) or not np.isfinite(direction).all():
        raise ValueError("Flow direction has invalid shape or values")
    if np.any(land & ocean) or np.any(depth < 0) or np.any(speed < 0):
        raise ValueError("Invalid land, ocean, depth, or speed")
    if np.any(boundary & (~ocean | (depth <= 0))):
        raise ValueError("Open boundary must be wet ocean")
    perimeter = np.zeros(shape, dtype=bool)
    perimeter[0, :] = perimeter[-1, :] = True
    perimeter[:, 0] = perimeter[:, -1] = True
    if np.any(boundary & ~perimeter):
        raise ValueError("Open boundary must touch domain perimeter")
    scalars = (inputs.sediment_solid, inputs.settling_velocity, inputs.depth_exponent,
               inputs.porosity, inputs.spacing_blocks)
    if not all(math.isfinite(value) for value in scalars):
        raise ValueError("Transport parameters must be finite")
    if (inputs.sediment_solid < 0 or inputs.settling_velocity < 0 or
            inputs.depth_exponent < 0 or not 0 <= inputs.porosity < 1 or
            inputs.spacing_blocks <= 0 or type(inputs.max_steps) is not int or inputs.max_steps < 0):
        raise ValueError("Invalid transport parameters")
    path = tuple(inputs.main_path)
    for point in path:
        if len(point) != 2 or not all(isinstance(v, (int, np.integer)) for v in point):
            raise ValueError("Path cell is invalid")
        if not (0 <= point[0] < shape[0] and 0 <= point[1] < shape[1]):
            raise ValueError("Path leaves grid")
    for a, b in zip(path, path[1:]):
        if max(abs(a[0]-b[0]), abs(a[1]-b[1])) != 1:
            raise ValueError("Path must have adjacent, distinct cells")
    wet = ocean & (depth > 0)
    mouth = next((b for a, b in zip(path, path[1:]) if land[a] and wet[b]), None)
    height_delta = np.zeros(shape, dtype=float)
    mobile = np.zeros(shape, dtype=float)
    if mouth is None:
        raise ValueError("No wet land-to-ocean mouth for sediment input")
    wet = _component(wet, mouth)
    mobile[mouth] = inputs.sediment_solid
    exported = 0.0
    area_solid = inputs.spacing_blocks ** 2 * (1 - inputs.porosity)
    offsets = [(dz, dx) for dz in (-1, 0, 1) for dx in (-1, 0, 1) if dz or dx]
    for _ in range(inputs.max_steps):
        outgoing = np.zeros(shape, dtype=float)
        effective_depth = np.maximum(0.0, depth - height_delta)
        wet_step = wet & (effective_depth > 0)
        for z, x in np.argwhere(mobile > 0):
            amount = mobile[z, x]
            if boundary[z, x]:
                exported += amount
                continue
            local_depth = effective_depth[z, x]
            if local_depth == 0:
                outgoing[z, x] += amount
                continue
            # Residence time divided by water depth gives a bounded settling share.
            residence = inputs.spacing_blocks / max(speed[z, x], 1e-12)
            settled = amount * -math.expm1(-inputs.settling_velocity * residence / local_depth)
            cap = min(.5, .25 * local_depth) * area_solid
            settled = min(settled, cap)
            height_delta[z, x] += settled / area_solid
            remainder = amount - settled
            if speed[z, x] == 0:
                outgoing[z, x] += remainder
                continue
            weights = []
            for dz, dx in offsets:
                nz, nx = z + dz, x + dx
                if not (0 <= nz < shape[0] and 0 <= nx < shape[1]) or not wet_step[nz, nx]:
                    continue
                distance = math.hypot(dz, dx)
                forward = max(0.0, (direction[z, x, 0]*dz + direction[z, x, 1]*dx) / distance)
                weight = effective_depth[nz, nx] ** inputs.depth_exponent * forward / distance
                if weight > 0:
                    weights.append((nz, nx, weight))
            total = sum(weight for _, _, weight in weights)
            if total == 0:
                outgoing[z, x] += remainder
            else:
                for nz, nx, weight in weights:
                    outgoing[nz, nx] += remainder * weight / total
        mobile = outgoing
    deposited = float(np.sum(height_delta) * area_solid)
    return TransportResult(height_delta, mobile, deposited, exported, mouth)


def _grid(value: np.ndarray, shape: tuple[int, int], dtype: type) -> np.ndarray:
    grid = np.asarray(value, dtype=dtype)
    if grid.shape != shape or (dtype is float and not np.isfinite(grid).all()):
        raise ValueError("Grid has invalid shape or values")
    return grid


def _component(wet: np.ndarray, mouth: tuple[int, int]) -> np.ndarray:
    connected = np.zeros_like(wet)
    connected[mouth] = True
    queue = deque([mouth])
    while queue:
        z, x = queue.popleft()
        for dz in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nz, nx = z + dz, x + dx
                if ((dz or dx) and 0 <= nz < wet.shape[0] and 0 <= nx < wet.shape[1]
                        and wet[nz, nx] and not connected[nz, nx]):
                    connected[nz, nx] = True
                    queue.append((nz, nx))
    return connected
