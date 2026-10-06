"""Conservative river-mouth deposition geometry with an explicit ocean gate."""
from dataclasses import dataclass
import math
from collections import deque
import numpy as np


@dataclass(frozen=True)
class DeltaResult:
    height_delta: np.ndarray
    deposited_solid: float
    exported_solid: float
    mouth: tuple[int, int] | None


def deposit_delta(height: np.ndarray, land_mask: np.ndarray,
                  connected_ocean_mask: np.ndarray, main_path: list[tuple[int, int]],
                  sediment_volume: float, porosity: float = .35,
                  max_radius: int = 12, spacing_blocks: float = 1) -> DeltaResult:
    """Deposit input solid volume only at a land-to-connected-ocean mouth.

    Heights are block units. The input
    sediment volume is solid-equivalent block cubed; each cell area is
    spacing_blocks squared. max_radius is in cells. Material not deposited exits.
    This is a local morphology prototype, not a tide/wave transport solver.
    """
    terrain = np.asarray(height, dtype=np.float64)
    land = np.asarray(land_mask, dtype=bool)
    ocean = np.asarray(connected_ocean_mask, dtype=bool)
    if terrain.ndim != 2 or land.shape != terrain.shape or ocean.shape != terrain.shape:
        raise ValueError("Masks and height must share a 2D grid")
    if not np.isfinite(terrain).all() or not np.isfinite(sediment_volume) or sediment_volume < 0:
        raise ValueError("Invalid height or sediment volume")
    if not np.isfinite(porosity) or not 0 <= porosity < 1 or type(max_radius) is not int or max_radius < 1 or not np.isfinite(spacing_blocks) or spacing_blocks <= 0:
        raise ValueError("Invalid porosity or radius")
    if np.any(land & ocean):
        raise ValueError("Land and connected ocean masks overlap")
    delta = np.zeros_like(terrain)
    path = tuple((int(z), int(x)) for z, x in main_path)
    for point in path:
        if not (0 <= point[0] < terrain.shape[0] and 0 <= point[1] < terrain.shape[1]):
            raise ValueError("Path leaves grid")
    for upstream, downstream in zip(path, path[1:]):
        if max(abs(upstream[0]-downstream[0]), abs(upstream[1]-downstream[1])) > 1:
            raise ValueError("Path is disconnected")
    mouth = None
    tangent = None
    for upstream, downstream in zip(path, path[1:]):
        if land[upstream] and ocean[downstream]:
            mouth = downstream
            tangent = (downstream[0]-upstream[0], downstream[1]-upstream[1])
            break
    if mouth is not None:
        ocean = _ocean_component(ocean, mouth)
    if mouth is None or sediment_volume == 0:
        return DeltaResult(delta, 0.0, float(sediment_volume), mouth)
    norm = math.hypot(*tangent)
    direction = (tangent[0]/norm, tangent[1]/norm)
    weighted_cells = []
    for z in range(max(0, mouth[0]-max_radius), min(terrain.shape[0], mouth[0]+max_radius+1)):
        for x in range(max(0, mouth[1]-max_radius), min(terrain.shape[1], mouth[1]+max_radius+1)):
            if not ocean[z, x]:
                continue
            dz, dx = z-mouth[0], x-mouth[1]
            forward = dz*direction[0] + dx*direction[1]
            lateral = abs(dz*direction[1]-dx*direction[0])
            if forward < 0 or forward > max_radius or lateral > max(1, .7*max_radius):
                continue
            weight = math.exp(-forward/max(1, max_radius/2)) * math.exp(-lateral/max(1, max_radius/3))
            weighted_cells.append(((z, x), weight))
    if not weighted_cells:
        return DeltaResult(delta, 0.0, float(sediment_volume), mouth)
    cell_solid_capacity = .5 * spacing_blocks**2 * (1-porosity)
    remaining = min(sediment_volume, len(weighted_cells) * cell_solid_capacity)
    active = list(weighted_cells)
    allocated = {point: 0.0 for point, _ in weighted_cells}
    while active and remaining > 1e-12:
        weight_sum = sum(weight for _, weight in active)
        distributed = 0.0
        next_active = []
        for point, weight in active:
            allotment = min(remaining * weight / weight_sum,
                            cell_solid_capacity - allocated[point])
            allocated[point] += allotment
            distributed += allotment
            if cell_solid_capacity - allocated[point] > 1e-12:
                next_active.append((point, weight))
        remaining -= distributed
        active = next_active
    for (z, x), solid in allocated.items():
        delta[z, x] = solid / ((1-porosity) * spacing_blocks**2)
    deposited = float(delta.sum() * (1-porosity) * spacing_blocks**2)
    return DeltaResult(delta, deposited, float(sediment_volume-deposited), mouth)

def _ocean_component(ocean: np.ndarray, mouth: tuple[int, int]) -> np.ndarray:
    component = np.zeros_like(ocean)
    queue = deque([mouth])
    component[mouth] = True
    while queue:
        z, x = queue.popleft()
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbor = (z+dz, x+dx)
            if (0 <= neighbor[0] < ocean.shape[0] and 0 <= neighbor[1] < ocean.shape[1]
                    and ocean[neighbor] and not component[neighbor]):
                component[neighbor] = True
                queue.append(neighbor)
    return component