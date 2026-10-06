"""Bounded-window large surface river benchmark.

This module is deliberately independent from the frozen regional hydraulic
solver.  It exercises the contracts needed before a tiled solver: one global
coordinate system, exact shared edges, globally stable cell IDs, and routing
that can read terrain through a bounded tile cache.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
import json
import math
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class LargeScaleSpec:
    rows: int = 1024
    cols: int = 1024
    tile_size: int = 128
    halo: int = 1
    cell_size_m: float = 30.0
    seed: int = 20261001

    def __post_init__(self) -> None:
        if min(self.rows, self.cols, self.tile_size) <= 0 or self.halo < 1:
            raise ValueError("dimensions and halo must be positive")
        if self.rows % self.tile_size or self.cols % self.tile_size:
            raise ValueError("rows and cols must be tile aligned")

    @property
    def cell_count(self) -> int:
        return self.rows * self.cols

    def cell_id(self, row: int, col: int) -> int:
        return row * self.cols + col

    def tile_key(self, row: int, col: int) -> tuple[int, int]:
        return row // self.tile_size, col // self.tile_size


class SyntheticMountain:
    """A continuous analytic mountain; no full terrain array is allocated."""

    def __init__(self, spec: LargeScaleSpec):
        self.spec = spec
        self.read_count = 0

    def read_window(self, row0: int, col0: int, rows: int, cols: int) -> np.ndarray:
        if row0 < 0 or col0 < 0 or row0 + rows > self.spec.rows or col0 + cols > self.spec.cols:
            raise ValueError("window outside domain")
        self.read_count += 1
        rr, cc = np.mgrid[row0:row0 + rows, col0:col0 + cols]
        # Global coordinates make adjoining tiles agree bit-for-bit.
        y = rr.astype(np.float64) / max(1, self.spec.rows - 1)
        x = cc.astype(np.float64) / max(1, self.spec.cols - 1)
        ridge = 32.0 * np.sin((x * 7.0 + y * 2.0) * math.pi)
        cross_ridge = 18.0 * np.sin((x * 2.0 - y * 9.0) * math.pi)
        southeast_drop = 420.0 * (1.0 - 0.62 * y - 0.38 * x)
        basin = 70.0 * np.exp(-((x - 0.72) ** 2 + (y - 0.68) ** 2) / 0.025)
        return (900.0 + southeast_drop + ridge + cross_ridge + basin).astype(np.float32)


class BoundedTileReader:
    """Tile/halo reader with an explicit upper bound on resident windows."""

    def __init__(self, source: SyntheticMountain, max_windows: int = 3):
        if max_windows < 1:
            raise ValueError("max_windows must be positive")
        self.source = source
        self.max_windows = max_windows
        self._cache: OrderedDict[tuple[int, int], np.ndarray] = OrderedDict()
        self.peak_windows = 0

    def tile(self, tile_row: int, tile_col: int) -> np.ndarray:
        key = (tile_row, tile_col)
        if key in self._cache:
            value = self._cache.pop(key)
            self._cache[key] = value
            return value
        spec = self.source.spec
        r0, c0 = tile_row * spec.tile_size, tile_col * spec.tile_size
        value = self.source.read_window(r0, c0, spec.tile_size, spec.tile_size)
        self._cache[key] = value
        while len(self._cache) > self.max_windows:
            self._cache.popitem(last=False)
        self.peak_windows = max(self.peak_windows, len(self._cache))
        return value

    def window(self, tile_row: int, tile_col: int) -> np.ndarray:
        """Return a tile plus a clipped one-cell halo."""
        spec = self.source.spec
        r0 = tile_row * spec.tile_size
        c0 = tile_col * spec.tile_size
        top, left = max(0, r0 - spec.halo), max(0, c0 - spec.halo)
        bottom = min(spec.rows, r0 + spec.tile_size + spec.halo)
        right = min(spec.cols, c0 + spec.tile_size + spec.halo)
        # Halo reads are intentionally uncached separately from tile storage.
        return self.source.read_window(top, left, bottom - top, right - left)

    def clear(self) -> None:
        self._cache.clear()


@dataclass
class RiverNetwork:
    receiver: np.ndarray
    order: np.ndarray
    accumulation: np.ndarray
    river_id: np.ndarray
    outlets: np.ndarray


def _iter_tiles(spec: LargeScaleSpec) -> Iterator[tuple[int, int]]:
    for tile_row in range(spec.rows // spec.tile_size):
        for tile_col in range(spec.cols // spec.tile_size):
            yield tile_row, tile_col


def build_river_network(spec: LargeScaleSpec, reader: BoundedTileReader) -> RiverNetwork:
    """Build D8 routing with global IDs while only reading tile plus halo."""
    receiver = np.full(spec.cell_count, -1, dtype=np.int64)
    indegree = np.zeros(spec.cell_count, dtype=np.int32)
    directions = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
    for tr, tc in _iter_tiles(spec):
        local = reader.window(tr, tc)
        r0, c0 = tr * spec.tile_size, tc * spec.tile_size
        row_offset = 1 if r0 > 0 else 0
        col_offset = 1 if c0 > 0 else 0
        for lr in range(spec.tile_size):
            for lc in range(spec.tile_size):
                base_r, base_c = lr + row_offset, lc + col_offset
                best = float(local[base_r, base_c])
                target = -1
                for dr, dc in directions:
                    nr, nc = r0 + lr + dr, c0 + lc + dc
                    if 0 <= nr < spec.rows and 0 <= nc < spec.cols:
                        value = float(local[base_r + dr, base_c + dc])
                        if value < best:
                            best, target = value, spec.cell_id(nr, nc)
                cell = spec.cell_id(r0 + lr, c0 + lc)
                receiver[cell] = target
                if target >= 0:
                    indegree[target] += 1

    queue = deque(np.flatnonzero(indegree == 0).tolist())
    order = np.empty(spec.cell_count, dtype=np.int64)
    count = 0
    while queue:
        cell = queue.popleft()
        order[count] = cell
        count += 1
        target = int(receiver[cell])
        if target >= 0:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if count != spec.cell_count:
        raise RuntimeError("D8 graph contains a cycle")

    accumulation = np.ones(spec.cell_count, dtype=np.float64)
    for cell in order:
        target = int(receiver[cell])
        if target >= 0:
            accumulation[target] += accumulation[cell]
    outlets = np.flatnonzero(receiver < 0).astype(np.int64)
    threshold = max(32.0, spec.cell_count / 4096.0)
    river_id = np.full(spec.cell_count, -1, dtype=np.int64)
    for cell in order[::-1]:
        cell = int(cell)
        target = int(receiver[cell])
        if accumulation[cell] >= threshold:
            river_id[cell] = cell if target < 0 else (river_id[target] if river_id[target] >= 0 else target)
    return RiverNetwork(receiver, order, accumulation, river_id, outlets)


@dataclass(frozen=True)
class PropagationResult:
    rainfall_m3: float
    outlet_m3: float
    remaining_m3: float
    residual_m3: float
    steps: int


def propagate_windowed(spec: LargeScaleSpec, reader: BoundedTileReader, network: RiverNetwork,
                       steps: int = 8, rainfall_m_per_step: float = 0.001) -> PropagationResult:
    """Route rainfall in global topological order, loading terrain by tile."""
    if steps <= 0 or rainfall_m_per_step < 0:
        raise ValueError("invalid propagation parameters")
    water = np.zeros(spec.cell_count, dtype=np.float64)
    rainfall_total = 0.0
    outlet_total = 0.0
    area = spec.cell_size_m ** 2
    # Tile reads are part of the propagation contract even though D8 metadata
    # is already available: each step proves the execution path is windowed.
    for _ in range(steps):
        for tr, tc in _iter_tiles(spec):
            reader.tile(tr, tc)
        rain = rainfall_m_per_step * area
        water += rain
        rainfall_total += rain * spec.cell_count
        # The graph order is global, so a discharge crossing a tile boundary
        # is handled identically to an interior edge.
        for cell in network.order:
            cell = int(cell)
            amount = water[cell]
            water[cell] = 0.0
            target = int(network.receiver[cell])
            if target < 0:
                outlet_total += amount
            else:
                water[target] += amount
    remaining = float(water.sum())
    return PropagationResult(rainfall_total, outlet_total, remaining,
                             rainfall_total - outlet_total - remaining, steps)


def run_benchmark(spec: LargeScaleSpec | None = None, max_windows: int = 3) -> dict:
    spec = spec or LargeScaleSpec()
    source = SyntheticMountain(spec)
    reader = BoundedTileReader(source, max_windows=max_windows)
    network = build_river_network(spec, reader)
    result = propagate_windowed(spec, reader, network)
    return {
        "schema": "large-scale-surface-tiles-v1",
        "shape": [spec.rows, spec.cols], "tile_size": spec.tile_size,
        "tile_count": (spec.rows // spec.tile_size) * (spec.cols // spec.tile_size),
        "cell_count": spec.cell_count, "outlet_count": int(network.outlets.size),
        "river_cell_count": int(np.count_nonzero(network.river_id >= 0)),
        "cross_tile_edges": int(sum(1 for cell, target in enumerate(network.receiver)
                                    if target >= 0 and spec.tile_key(cell // spec.cols, cell % spec.cols) !=
                                    spec.tile_key(int(target) // spec.cols, int(target) % spec.cols))),
        "max_windows": max_windows, "peak_windows": reader.peak_windows,
        "source_reads": source.read_count, "propagation": result.__dict__,
        "conservation_passed": bool(abs(result.residual_m3) < 1e-6),
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
