"""Deterministic native D4 tiling and immutable stage halo reads; no solver."""

from dataclasses import dataclass
import math
from types import MappingProxyType

import numpy as np


INTERIOR = 256
HALO = 1
MAX_WINDOW_CELLS = 260 * 260
MAX_WINDOW_FACES = 2 * 260 * 259
MAX_GRID_SIDE = 2048


@dataclass(frozen=True)
class Tile:
    tile_id: int
    interior_zx: tuple
    halo_zx: tuple
    shape_zx: tuple

    @property
    def interior_cells(self):
        z0, z1, x0, x1 = self.interior_zx
        return (z1 - z0) * (x1 - x0)

    @property
    def halo_cells(self):
        z0, z1, x0, x1 = self.halo_zx
        return (z1 - z0) * (x1 - x0)

    def interior_ids(self):
        _, width = self.shape_zx
        z0, z1, x0, x1 = self.interior_zx
        for row in range(z0, z1):
            for column in range(x0, x1):
                yield row * width + column


@dataclass(frozen=True)
class Face:
    face_id: int
    first_cell_id: int
    second_cell_id: int
    owner_tile_id: int
    neighbor_tile_id: int | None

    @property
    def crosses_tile(self):
        return self.neighbor_tile_id is not None


@dataclass(frozen=True, slots=True, init=False)
class NativePartition:
    shape_zx: tuple
    tile_columns: int
    tile_rows: int
    tile_count: int

    def __init__(self, shape_zx, *, interior=INTERIOR, halo=HALO):
        if (not isinstance(shape_zx, tuple) or len(shape_zx) != 2
                or any(type(value) is not int or not 1 <= value <= MAX_GRID_SIDE for value in shape_zx)):
            raise ValueError("bounded positive [z,x] native grid required")
        if interior != INTERIOR or halo != HALO:
            raise ValueError("v1 fixes 256 interior and one-cell halo")
        tile_columns = math.ceil(shape_zx[1] / INTERIOR)
        tile_rows = math.ceil(shape_zx[0] / INTERIOR)
        object.__setattr__(self, "shape_zx", shape_zx)
        object.__setattr__(self, "tile_columns", tile_columns)
        object.__setattr__(self, "tile_rows", tile_rows)
        object.__setattr__(self, "tile_count", tile_rows * tile_columns)

    def tile(self, tile_id):
        if type(tile_id) is not int or not 0 <= tile_id < self.tile_count:
            raise ValueError("tile ID out of range")
        tile_row, tile_column = divmod(tile_id, self.tile_columns)
        z0, x0 = tile_row * INTERIOR, tile_column * INTERIOR
        z1, x1 = min(self.shape_zx[0], z0 + INTERIOR), min(self.shape_zx[1], x0 + INTERIOR)
        halo_zx = (max(0, z0 - HALO), min(self.shape_zx[0], z1 + HALO),
                   max(0, x0 - HALO), min(self.shape_zx[1], x1 + HALO))
        result = Tile(tile_id, (z0, z1, x0, x1), halo_zx, self.shape_zx)
        if result.halo_cells > MAX_WINDOW_CELLS:
            raise ValueError("window cell budget exceeded")
        return result

    def tiles(self):
        for tile_id in range(self.tile_count):
            yield self.tile(tile_id)

    def owner_of_cell(self, cell_id):
        height, width = self.shape_zx
        if type(cell_id) is not int or not 0 <= cell_id < height * width:
            raise ValueError("global cell ID out of range")
        row, column = divmod(cell_id, width)
        return (row // INTERIOR) * self.tile_columns + column // INTERIOR

    def _valid(self, valid_at, cell_id):
        value = valid_at(cell_id)
        if type(value) not in (bool, np.bool_):
            raise ValueError("valid mask accessor must return bool")
        return bool(value)

    def faces(self, tile, valid_at):
        if not isinstance(tile, Tile) or tile != self.tile(tile.tile_id):
            raise ValueError("foreign or malformed tile")
        if not callable(valid_at):
            raise ValueError("valid mask accessor required")
        height, width = self.shape_zx
        produced = 0
        for first in tile.interior_ids():
            if not self._valid(valid_at, first):
                continue
            row, column = divmod(first, width)
            for direction, allowed, second in ((0, column + 1 < width, first + 1),
                                                (1, row + 1 < height, first + width)):
                if not allowed or not self._valid(valid_at, second):
                    continue
                neighbor = self.owner_of_cell(second)
                produced += 1
                if produced > MAX_WINDOW_FACES:
                    raise ValueError("window face budget exceeded")
                yield Face(2 * first + direction, first, second, tile.tile_id,
                           neighbor if neighbor != tile.tile_id else None)

    def open_boundary_cells(self, tile, valid_at, open_at):
        if not isinstance(tile, Tile) or tile != self.tile(tile.tile_id):
            raise ValueError("foreign or malformed tile")
        if not callable(open_at):
            raise ValueError("open boundary accessor required")
        height, width = self.shape_zx
        for cell_id in tile.interior_ids():
            opened = open_at(cell_id)
            if type(opened) not in (bool, np.bool_):
                raise ValueError("open mask accessor must return bool")
            if not opened:
                continue
            row, column = divmod(cell_id, width)
            if not self._valid(valid_at, cell_id) or not (row == 0 or row == height - 1 or column == 0 or column == width - 1):
                raise ValueError("open boundary outside valid global grid perimeter")
            yield cell_id


@dataclass(frozen=True, slots=True, init=False)
class StageSnapshot:
    """Owns copied, read-only tile interiors at one stage version."""

    partition: NativePartition
    version: str
    chunks: object

    def __init__(self, partition, version, chunks):
        if not isinstance(partition, NativePartition) or not isinstance(version, str) or not version:
            raise ValueError("partition and nonempty stage version required")
        if set(chunks) != set(range(partition.tile_count)):
            raise ValueError("stage snapshot must cover every interior tile once")
        frozen_chunks = {}
        for tile in partition.tiles():
            declared_version, values = chunks[tile.tile_id]
            if declared_version != version:
                raise ValueError("mixed stage versions forbidden")
            array = np.asarray(values)
            z0, z1, x0, x1 = tile.interior_zx
            if array.shape != (z1 - z0, x1 - x0) or array.dtype != np.float64 or not np.isfinite(array).all():
                raise ValueError("invalid stage tile array")
            frozen = np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)
            frozen_chunks[tile.tile_id] = frozen
        object.__setattr__(self, "partition", partition)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "chunks", MappingProxyType(frozen_chunks))

    def sample_halo(self, tile, *, version):
        if version != self.version or not isinstance(tile, Tile) or tile != self.partition.tile(tile.tile_id):
            raise ValueError("stage version or tile mismatch")
        z0, z1, x0, x1 = tile.halo_zx
        result = np.empty((z1 - z0, x1 - x0), dtype=np.float64)
        for owner in self.partition.tiles():
            a0, a1, b0, b1 = owner.interior_zx
            overlap = max(z0, a0), min(z1, a1), max(x0, b0), min(x1, b1)
            oz0, oz1, ox0, ox1 = overlap
            if oz0 >= oz1 or ox0 >= ox1:
                continue
            result[oz0-z0:oz1-z0, ox0-x0:ox1-x0] = self.chunks[owner.tile_id][oz0-a0:oz1-a0, ox0-b0:ox1-b0]
        return np.frombuffer(result.tobytes(), dtype=np.float64).reshape(result.shape)
