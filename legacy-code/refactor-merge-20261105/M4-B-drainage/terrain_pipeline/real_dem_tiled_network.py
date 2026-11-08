"""Read-only DEM tiles with one global irregular graph, not a streamed solve."""
from dataclasses import dataclass

import numpy as np

from terrain_pipeline.td_source import DEM_MAX_CELLS as MAX_CELLS, validate_dem_candidate
from terrain_pipeline.real_dem_surface_network import RealDemNetwork, build_real_dem_network, validate_real_dem_network
from terrain_pipeline.irregular_grid import grid_mesh


ALGORITHM = "real-dem-array-tiles-global-irregular-graph-v2"
MAX_TILE_SIZE = 1024


def _positive_integer(value, name, maximum=None):
    if type(value) is not int or value <= 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be a positive integer" + (f" <= {maximum}" if maximum else ""))
    return value


def _arrays(candidate):
    if not isinstance(candidate, dict) or "arrays" not in candidate:
        raise ValueError("candidate arrays required")
    arrays = candidate["arrays"]
    height, valid = arrays.get("height_m"), arrays.get("valid_mask")
    if (not isinstance(height, np.ndarray) or height.ndim != 2 or height.dtype != np.dtype("float64")
            or not isinstance(valid, np.ndarray) or valid.dtype != np.dtype(bool) or valid.shape != height.shape):
        raise ValueError("height_m/valid_mask shape or dtype mismatch")
    for value, name in zip(height.shape, ("rows", "cols")):
        _positive_integer(value, name)
    if height.size > MAX_CELLS:
        raise ValueError("candidate exceeds global graph cell budget")
    if not valid.any() or not np.array_equal(valid, np.isfinite(height)) or not np.isnan(height[~valid]).all():
        raise ValueError("invalid finite height/unknown semantics or empty valid mask")
    if "unknown_mask" in arrays and not np.array_equal(arrays["unknown_mask"], ~valid):
        raise ValueError("unknown_mask mismatch")
    if "manifest" in candidate:
        validate_dem_candidate(candidate, verify_source=False)
    return height, valid


def candidate_mesh(candidate):
    height, _ = _arrays(candidate)
    grid = candidate.get("manifest", {}).get("identity", {}).get("grid", candidate.get("grid", {}))
    return grid_mesh(height.shape, x0_m=grid.get("origin_x_m", 0.), z0_m=grid.get("origin_z_m", 0.),
        dx_m=grid.get("spacing_x_m", 90.), dz_m=grid.get("spacing_z_m", 90.))


@dataclass(frozen=True)
class DemTile:
    core_bounds: tuple
    window_bounds: tuple
    height_m: np.ndarray
    valid_mask: np.ndarray


class CandidateTileReader:
    """Resident-array views; tile counters do not bound global graph memory."""
    def __init__(self, candidate, *, tile_size=256):
        self.tile_size = _positive_integer(tile_size, "tile_size", MAX_TILE_SIZE)
        self.height_m, self.valid_mask = _arrays(candidate)
        self.shape = self.height_m.shape
        self.read_windows = self.peak_window_cells = 0

    def read_window(self, row_start, row_stop, col_start, col_stop):
        bounds = (row_start, row_stop, col_start, col_stop)
        if any(type(value) is not int for value in bounds):
            raise ValueError("window bounds must be integers, not bool")
        if not (0 <= row_start < row_stop <= self.shape[0] and 0 <= col_start < col_stop <= self.shape[1]):
            raise ValueError("window outside candidate or empty")
        height = self.height_m[row_start:row_stop, col_start:col_stop].view()
        valid = self.valid_mask[row_start:row_stop, col_start:col_stop].view()
        height.flags.writeable = valid.flags.writeable = False
        self.read_windows += 1
        self.peak_window_cells = max(self.peak_window_cells, height.size)
        return {"height_m": height, "valid_mask": valid}

    def iter_tiles(self, *, tile_order="row_major"):
        if tile_order not in ("row_major", "reversed"):
            raise ValueError("tile_order must be row_major or reversed")
        rows, cols = self.shape
        cores = [(row, min(rows, row + self.tile_size), col, min(cols, col + self.tile_size))
                 for row in range(0, rows, self.tile_size) for col in range(0, cols, self.tile_size)]
        if tile_order == "reversed":
            cores.reverse()
        for core in cores:
            r0, r1, c0, c1 = core
            window = (max(0, r0 - 1), min(rows, r1 + 1), max(0, c0 - 1), min(cols, c1 + 1))
            values = self.read_window(*window)
            yield DemTile(core, window, values["height_m"], values["valid_mask"])

    def statistics(self):
        return dict(read_windows=self.read_windows, peak_window_cells=self.peak_window_cells,
            storage="read_only_views_of_resident_candidate_arrays", halo_cells=1,
            disk_streamed_full_state=False)


def build_tiled_network(candidate, *, tile_size=256, tile_order="row_major") -> RealDemNetwork:
    reader = CandidateTileReader(candidate, tile_size=tile_size)
    # The complete supplied window owns topology; a tile halo is only a read window.
    for _ in reader.iter_tiles(tile_order=tile_order):
        pass
    return build_real_dem_network(reader.height_m, reader.valid_mask, mesh=candidate_mesh(candidate))


def validate_tiled_network(candidate, network, *, tile_size=256) -> dict:
    """Audit actual graph receivers, order, accumulation and terminal risks."""
    reader = CandidateTileReader(candidate, tile_size=tile_size)
    height, valid = reader.height_m, reader.valid_mask
    if not isinstance(network, RealDemNetwork):
        raise ValueError("RealDemNetwork required")
    for name, dtype in (("receiver", np.int64), ("accumulation_cells", np.float64),
                        ("boundary_outlet", bool), ("unknown_adjacent_terminal", bool)):
        value = getattr(network, name)
        if not isinstance(value, np.ndarray) or value.shape != height.shape or value.dtype != np.dtype(dtype):
            raise ValueError(f"invalid {name} shape/dtype")
    ids = np.flatnonzero(valid.ravel())
    expected_order = ids[np.argsort(-height.ravel()[ids], kind="stable")]
    if (not isinstance(network.order, np.ndarray) or network.order.dtype != np.dtype(np.int64)
            or not np.array_equal(network.order, expected_order)):
        raise ValueError("order must be stable descending valid height")
    audit = validate_real_dem_network(network, height, valid)
    mesh = network.mesh if network.mesh is not None else candidate_mesh(candidate)
    rec = network.receiver.ravel()
    if np.any(rec[~valid.ravel()] != -1):
        raise ValueError("unknown cells must remain terminal")
    expected = np.zeros(height.size)
    expected[ids] = 1.
    for node in network.order:
        if rec[node] >= 0:
            expected[rec[node]] += expected[node]
    if not np.array_equal(network.accumulation_cells.ravel(), expected):
        raise ValueError("contributing accumulation mismatch")
    boundary = np.zeros(height.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    unknown = np.zeros(height.size, bool)
    for node in ids:
        adjacent = mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
        unknown[node] = np.any(~valid.ravel()[adjacent])
    terminal = valid & (network.receiver < 0)
    if (not np.array_equal(network.boundary_outlet, terminal & boundary)
            or not np.array_equal(network.unknown_adjacent_terminal, terminal & unknown.reshape(height.shape))):
        raise ValueError("terminal boundary/unknown risk mismatch")
    contribution = expected[ids[rec[ids] < 0]].sum()
    if contribution != ids.size:
        raise ValueError("terminal contributions do not cover valid cells")
    for _ in reader.iter_tiles():
        pass
    graph_bytes = {name: int(getattr(network, name).nbytes) for name in
        ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal")}
    return dict(audit, algorithm=ALGORITHM, tile_size=tile_size, contributing_cells_sum=int(contribution),
        reader=reader.statistics(), global_graph_state=True, graph_array_nbytes=graph_bytes,
        graph_arrays_nbytes=sum(graph_bytes.values()), memory_scope="graph payload excludes mesh and sort temporaries",
        disk_streamed_full_state=False)
