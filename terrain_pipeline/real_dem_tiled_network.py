"""Array-backed tile access with a global graph, not disk-streamed full state.

Routing preserves raw strict-downhill D8 semantics; flats are not resolved.
Reader windows are read-only views of an already resident DEM candidate.
"""

from dataclasses import dataclass

import numpy as np

from terrain_pipeline.dem_domain import MAX_CELLS, validate_dem_candidate
from terrain_pipeline.real_dem_surface_network import RealDemNetwork


ALGORITHM = "real-dem-array-tile-halo-d8-global-graph-v1"
DIRECTIONS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1),
              (1, -1), (1, 0), (1, 1))
MAX_TILE_SIZE = 1024


def _positive_integer(value, name, maximum=None):
    if type(value) is not int or value <= 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be a positive integer" + (f" <= {maximum}" if maximum else ""))
    return value


def _arrays(candidate):
    if not isinstance(candidate, dict) or "arrays" not in candidate:
        raise ValueError("candidate arrays required")
    arrays = candidate["arrays"]
    height = arrays.get("height_m")
    valid = arrays.get("valid_mask")
    if (not isinstance(height, np.ndarray) or height.ndim != 2 or height.dtype != np.dtype("float64")
            or not isinstance(valid, np.ndarray) or valid.dtype != np.dtype(bool) or valid.shape != height.shape):
        raise ValueError("height_m/valid_mask shape or dtype mismatch")
    rows, cols = height.shape
    _positive_integer(rows, "rows")
    _positive_integer(cols, "cols")
    if height.size > MAX_CELLS:
        raise ValueError("candidate exceeds global graph cell budget")
    if not valid.any() or not np.array_equal(valid, np.isfinite(height)) or not np.isnan(height[~valid]).all():
        raise ValueError("invalid finite height/unknown semantics or empty valid mask")
    if "unknown_mask" in arrays and not np.array_equal(arrays["unknown_mask"], ~valid):
        raise ValueError("unknown_mask mismatch")
    if "manifest" in candidate:
        validate_dem_candidate(candidate, verify_source=False)
    return height, valid


@dataclass(frozen=True)
class DemTile:
    core_bounds: tuple
    window_bounds: tuple
    height_m: np.ndarray
    valid_mask: np.ndarray


class CandidateTileReader:
    """Read-only resident-array windows; counters do not bound total solver RAM.

    Bounds are half-open (row_start, row_stop, col_start, col_stop).
    Arrays-only candidates are supported for isolated routing fixtures.
    """

    def __init__(self, candidate, *, tile_size=256):
        self.tile_size = _positive_integer(tile_size, "tile_size", MAX_TILE_SIZE)
        self.height_m, self.valid_mask = _arrays(candidate)
        self.shape = self.height_m.shape
        self.read_windows = 0
        self.peak_window_cells = 0

    def read_window(self, row_start, row_stop, col_start, col_stop):
        bounds = (row_start, row_stop, col_start, col_stop)
        if any(type(value) is not int for value in bounds):
            raise ValueError("window bounds must be integers, not bool")
        if not (0 <= row_start < row_stop <= self.shape[0] and 0 <= col_start < col_stop <= self.shape[1]):
            raise ValueError("window outside candidate or empty")
        height = self.height_m[row_start:row_stop, col_start:col_stop].view()
        valid = self.valid_mask[row_start:row_stop, col_start:col_stop].view()
        height.flags.writeable = False
        valid.flags.writeable = False
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
            row_start, row_stop, col_start, col_stop = core
            window = (max(0, row_start - 1), min(rows, row_stop + 1),
                      max(0, col_start - 1), min(cols, col_stop + 1))
            values = self.read_window(*window)
            yield DemTile(core, window, values["height_m"], values["valid_mask"])

    def statistics(self):
        return {"read_windows": self.read_windows, "peak_window_cells": self.peak_window_cells,
                "storage": "read_only_views_of_resident_candidate_arrays", "halo_cells": 1,
                "disk_streamed_full_state": False}


def build_tiled_network(candidate, *, tile_size=256, tile_order="row_major") -> RealDemNetwork:
    reader = CandidateTileReader(candidate, tile_size=tile_size)
    rows, cols = reader.shape
    receiver = np.full(reader.shape, -1, np.int64)
    boundary = np.zeros(reader.shape, bool)
    unknown_terminal = np.zeros(reader.shape, bool)
    for tile in reader.iter_tiles(tile_order=tile_order):
        row_start, row_stop, col_start, col_stop = tile.core_bounds
        window_row, _, window_col, _ = tile.window_bounds
        local_row = row_start - window_row
        local_col = col_start - window_col
        core_shape = (row_stop - row_start, col_stop - col_start)
        core_slice = (slice(local_row, local_row + core_shape[0]), slice(local_col, local_col + core_shape[1]))
        core_valid = tile.valid_mask[core_slice]
        best_height = tile.height_m[core_slice].copy()
        tile_receiver = np.full(core_shape, -1, np.int64)
        adjacent_unknown = np.zeros(core_shape, bool)
        for delta_row, delta_col in DIRECTIONS:
            source_row_start = max(row_start, -delta_row)
            source_row_stop = min(row_stop, rows - delta_row)
            source_col_start = max(col_start, -delta_col)
            source_col_stop = min(col_stop, cols - delta_col)
            if source_row_start >= source_row_stop or source_col_start >= source_col_stop:
                continue
            source_slice = (slice(source_row_start - row_start, source_row_stop - row_start),
                            slice(source_col_start - col_start, source_col_stop - col_start))
            target_slice = (slice(source_row_start + delta_row - window_row, source_row_stop + delta_row - window_row),
                            slice(source_col_start + delta_col - window_col, source_col_stop + delta_col - window_col))
            neighbor_valid = tile.valid_mask[target_slice]
            neighbor_height = tile.height_m[target_slice]
            replace = core_valid[source_slice] & neighbor_valid & (neighbor_height < best_height[source_slice])
            target_ids = ((np.arange(source_row_start, source_row_stop)[:, None] + delta_row) * cols
                          + np.arange(source_col_start, source_col_stop)[None, :] + delta_col)
            best_height[source_slice][replace] = neighbor_height[replace]
            tile_receiver[source_slice][replace] = target_ids[replace]
            adjacent_unknown[source_slice] |= ~neighbor_valid
        terminal = core_valid & (tile_receiver == -1)
        core = (slice(row_start, row_stop), slice(col_start, col_stop))
        receiver[core] = tile_receiver
        tile_rows = np.arange(row_start, row_stop)[:, None]
        tile_cols = np.arange(col_start, col_stop)[None, :]
        boundary[core] = terminal & ((tile_rows == 0) | (tile_rows == rows - 1)
                                     | (tile_cols == 0) | (tile_cols == cols - 1))
        unknown_terminal[core] = terminal & adjacent_unknown
    valid_ids = np.flatnonzero(reader.valid_mask.ravel())
    order = valid_ids[np.argsort(-reader.height_m.ravel()[valid_ids], kind="stable")]
    accumulation = np.zeros(reader.height_m.size, np.float64)
    accumulation[valid_ids] = 1.
    flat_receiver = receiver.ravel()
    for source_id in order:
        target_id = flat_receiver[source_id]
        if target_id >= 0:
            accumulation[target_id] += accumulation[source_id]
    return RealDemNetwork(receiver, order, accumulation.reshape(reader.shape), boundary, unknown_terminal)


def validate_tiled_network(candidate, network, *, tile_size=256) -> dict:
    """Independently audit D8 minima/ties, stable rank, contributions and risks."""
    reader = CandidateTileReader(candidate, tile_size=tile_size)
    height, valid = reader.height_m, reader.valid_mask
    rows, cols = reader.shape
    if not isinstance(network, RealDemNetwork):
        raise ValueError("RealDemNetwork required")
    for name, dtype in (("receiver", np.int64), ("accumulation_cells", np.float64),
                        ("boundary_outlet", bool), ("unknown_adjacent_terminal", bool)):
        values = getattr(network, name)
        if not isinstance(values, np.ndarray) or values.shape != reader.shape or values.dtype != np.dtype(dtype):
            raise ValueError(f"invalid {name} shape/dtype")
    receiver = network.receiver.ravel()
    valid_ids = np.flatnonzero(valid.ravel())
    order = network.order
    if (not isinstance(order, np.ndarray) or order.ndim != 1 or order.dtype != np.dtype(np.int64)
            or not np.array_equal(np.sort(order), valid_ids)):
        raise ValueError("order must cover valid cells exactly once")
    order_height = height.ravel()[order]
    if (np.any(order_height[:-1] < order_height[1:])
            or np.any((order_height[:-1] == order_height[1:]) & (order[:-1] >= order[1:]))):
        raise ValueError("order must be stable descending height, row-major ties")
    if np.any(receiver[~valid.ravel()] != -1) or np.any((receiver < -1) | (receiver >= height.size)):
        raise ValueError("invalid unknown/out-of-range receiver")
    routed_sources = valid_ids[receiver[valid_ids] >= 0]
    targets = receiver[routed_sources]
    if np.any(~valid.ravel()[targets]) or np.any(height.ravel()[targets] >= height.ravel()[routed_sources]):
        raise ValueError("receiver must be valid and strictly downhill")
    source_rows, source_cols = np.divmod(routed_sources, cols)
    target_rows, target_cols = np.divmod(targets, cols)
    if np.any(np.maximum(abs(source_rows - target_rows), abs(source_cols - target_cols)) != 1):
        raise ValueError("receiver must be D8 adjacent")
    rank = np.full(height.size, -1, np.int64)
    rank[order] = np.arange(len(order))
    if np.any(rank[routed_sources] >= rank[targets]):
        raise ValueError("receiver rank is not downstream")
    for tile in reader.iter_tiles():
        row_start, row_stop, col_start, col_stop = tile.core_bounds
        window_row, _, window_col, _ = tile.window_bounds
        cell_rows, cell_cols = np.indices((row_stop - row_start, col_stop - col_start))
        cell_rows = cell_rows.ravel() + row_start
        cell_cols = cell_cols.ravel() + col_start
        cell_ids = cell_rows * cols + cell_cols
        cell_valid = valid.ravel()[cell_ids]
        neighbor_ids = np.full((8, len(cell_ids)), -1, np.int64)
        neighbor_heights = np.full((8, len(cell_ids)), np.inf)
        unknown = np.zeros(len(cell_ids), bool)
        for direction, (delta_row, delta_col) in enumerate(DIRECTIONS):
            neighbor_rows = cell_rows + delta_row
            neighbor_cols = cell_cols + delta_col
            inside = ((neighbor_rows >= 0) & (neighbor_rows < rows) & (neighbor_cols >= 0) & (neighbor_cols < cols))
            local_rows = neighbor_rows[inside] - window_row
            local_cols = neighbor_cols[inside] - window_col
            neighbor_valid = tile.valid_mask[local_rows, local_cols]
            neighbor_ids[direction, inside] = neighbor_rows[inside] * cols + neighbor_cols[inside]
            neighbor_heights[direction, inside] = np.where(neighbor_valid, tile.height_m[local_rows, local_cols], np.inf)
            unknown[inside] |= ~neighbor_valid
        minimum_direction = neighbor_heights.argmin(axis=0)
        minimum_height = neighbor_heights[minimum_direction, np.arange(len(cell_ids))]
        downhill = cell_valid & (minimum_height < height.ravel()[cell_ids])
        expected_receiver = np.where(downhill, neighbor_ids[minimum_direction, np.arange(len(cell_ids))], -1)
        if not np.array_equal(receiver[cell_ids], expected_receiver):
            raise ValueError("receiver lowest-neighbor/direction tie semantics mismatch")
        terminal = cell_valid & ~downhill
        boundary = terminal & ((cell_rows == 0) | (cell_rows == rows - 1) | (cell_cols == 0) | (cell_cols == cols - 1))
        if (not np.array_equal(network.boundary_outlet.ravel()[cell_ids], boundary)
                or not np.array_equal(network.unknown_adjacent_terminal.ravel()[cell_ids], terminal & unknown)):
            raise ValueError("terminal boundary/unknown risk mismatch")
    expected_accumulation = np.zeros(height.size, np.float64)
    expected_accumulation[valid_ids] = 1.
    for source_id in order:
        target_id = receiver[source_id]
        if target_id >= 0:
            expected_accumulation[target_id] += expected_accumulation[source_id]
    if not np.array_equal(network.accumulation_cells.ravel(), expected_accumulation):
        raise ValueError("contributing accumulation mismatch")
    terminal_ids = valid_ids[receiver[valid_ids] == -1]
    contribution = float(expected_accumulation[terminal_ids].sum())
    if contribution != len(valid_ids):
        raise ValueError("terminal contributions do not cover valid cells")
    graph_bytes = {name: int(getattr(network, name).nbytes) for name in
                   ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal")}
    return {"verified": True, "algorithm": ALGORITHM, "tile_size": tile_size,
            "valid_cells": len(valid_ids), "unknown_cells": int((~valid).sum()),
            "terminal_cells": len(terminal_ids), "downhill_edges": len(routed_sources),
            "contributing_cells_sum": int(contribution),
            "boundary_outlet_candidates": int(network.boundary_outlet.sum()),
            "unknown_adjacent_terminals": int(network.unknown_adjacent_terminal.sum()),
            "reader": reader.statistics(), "global_graph_state": True,
            "graph_array_nbytes": graph_bytes, "graph_arrays_nbytes": sum(graph_bytes.values()),
            "memory_scope": "graph payload bytes only; resident candidate and validation/sort temporaries excluded",
            "disk_streamed_full_state": False, "natural_outlet_verified": False,
            "status": "real_dem_candidate_not_publishable"}
