"""Optional corridor-bound split and rejoin geometry; not a fluid solver."""
from dataclasses import dataclass
import heapq
import numpy as np
from .hydraulics import BranchHydraulics
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import masked_mesh as masked_mesh
from terrain_pipeline.drainage import segments_clear as segments_clear


@dataclass(frozen=True)
class BranchResult:
    paths: tuple[tuple[tuple[int, int], ...], ...]
    fractions: tuple[float, ...]
    discharges: tuple[float, ...]
    split: tuple[int, int] | None = None
    rejoin: tuple[int, int] | None = None
    reason: str = ""

    def edge_discharges(self) -> dict[tuple[tuple[int, int], tuple[int, int]], float]:
        """Directed edge flows, with shared trunk edges counted only once."""
        flows: dict[tuple[tuple[int, int], tuple[int, int]], float] = {}
        for path, discharge in zip(self.paths, self.discharges):
            for edge in zip(path, path[1:]):
                flows[edge] = flows.get(edge, 0.0) + discharge
        return flows


def build_branches(height: np.ndarray, main_path: list[tuple[int, int]],
                   corridor_mask: np.ndarray, discharge: float,
                   max_branches: int = 1,
                   hydraulics: BranchHydraulics | None = None, *,
                   origin_native_xz=(0, 0), spacing_m=1., world_seed=20261020) -> BranchResult:
    """Return a main channel and at most one downstream side channel.

    Grid points use (row=z, column=x). The side path starts and rejoins the
    main path, stays in the supplied corridor, and never rises in raw height.
    Branch discharges apply only between split and rejoin. Shared prefix and
    suffix edges carry the full input discharge. Without a qualifying low
    corridor, the full discharge remains in one slot.
    """
    terrain = np.asarray(height, dtype=np.float64)
    corridor = np.asarray(corridor_mask, dtype=bool)
    if terrain.ndim != 2 or terrain.shape != corridor.shape or not np.isfinite(terrain).all():
        raise ValueError("Invalid height or corridor")
    if not np.isfinite(discharge) or discharge < 0 or type(max_branches) is not int or max_branches not in (0, 1):
        raise ValueError("Invalid discharge or branch count")
    path = tuple((int(z), int(x)) for z, x in main_path)
    if len(path) < 4 or len(set(path)) != len(path):
        raise ValueError("Main path needs four or more unique cells")
    for z, x in path:
        if not (0 <= z < terrain.shape[0] and 0 <= x < terrain.shape[1]) or not corridor[z, x]:
            raise ValueError("Main path leaves corridor")
    ids = np.asarray([z * terrain.shape[1] + x for z, x in path], np.int64)
    if not segments_clear(ids[:-1], ids[1:], corridor).all():
        raise ValueError("Main path segments must remain inside the corridor")
    for a, b in zip(path, path[1:]):
        if terrain[b] > terrain[a] + 1e-9:
            raise ValueError("Main path must be non-rising")
    single = BranchResult((path,), (1.0,), (float(discharge),), reason="No valid split")
    if max_branches == 0 or discharge == 0:
        return single
    if hydraulics is None:
        return BranchResult((path,), (1.0,), (float(discharge),), reason="Hydraulics required")
    if not isinstance(hydraulics, BranchHydraulics):
        raise ValueError("Invalid hydraulics")
    main_capacity = hydraulics.main.conveyance()
    side_capacity = hydraulics.side.conveyance()
    if not np.isfinite(main_capacity + side_capacity):
        raise ValueError("Hydraulic conveyance overflow")
    if main_capacity <= 0 or side_capacity <= 0:
        return BranchResult((path,), (1.0,), (float(discharge),), reason="Dry or flat channel")

    # Search local split/rejoin windows. A side channel must bypass at least
    # one main-path cell and contain at least two unique interior cells.
    main_cells = set(path)
    mesh = masked_mesh(grid_mesh(terrain.shape, x0_m=origin_native_xz[0]*spacing_m,
        z0_m=origin_native_xz[1]*spacing_m, dx_m=spacing_m, world_seed=world_seed), corridor)
    for start_index in range(0, len(path) - 3):
        for end_index in range(start_index + 3, min(len(path), start_index + 14)):
            start, end = path[start_index], path[end_index]
            candidate = _side_path(terrain, corridor, start, end, main_cells, mesh)
            if candidate is None:
                continue
            side = tuple(path[:start_index] + candidate + path[end_index + 1:])
            if len(side) < 2 or side == path:
                continue
            fraction = side_capacity / (main_capacity + side_capacity)
            return BranchResult((path, side), (1 - fraction, fraction),
                                (discharge * (1 - fraction), discharge * fraction), start, end)
    return single


def _side_path(height: np.ndarray, corridor: np.ndarray, start: tuple[int, int],
               end: tuple[int, int], main_cells: set[tuple[int, int]], mesh):
    queue = [(0.0, start)]
    distance = {start: 0.0}
    previous = {}
    while queue:
        cost, current = heapq.heappop(queue)
        if cost != distance[current]:
            continue
        if current == end:
            cells = [end]
            while cells[-1] != start:
                cells.append(previous[cells[-1]])
            cells.reverse()
            return tuple(cells) if len(cells) >= 4 else None
        node = current[0] * height.shape[1] + current[1]
        for edge in range(mesh.indptr[node], mesh.indptr[node + 1]):
            neighbor = tuple(divmod(int(mesh.indices[edge]), height.shape[1]))
            if not corridor[neighbor] or (neighbor in main_cells and neighbor != end):
                continue
            if height[neighbor] > height[current] + 1e-9:
                continue
            new_cost = cost + mesh.edge_length_m[edge] + .02 * abs(height[current] - height[neighbor])
            if new_cost < distance.get(neighbor, float("inf")):
                distance[neighbor] = new_cost
                previous[neighbor] = current
                heapq.heappush(queue, (new_cost, neighbor))
    return None
