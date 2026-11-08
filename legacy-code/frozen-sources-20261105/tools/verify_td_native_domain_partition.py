"""Stream synthetic 1024/2048 native tile topology without allocating grid floats."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_native_domain_partition import NativePartition


def verify_size(size):
    partition = NativePartition((size, size))
    face_count = 0
    cross_count = 0
    open_count = 0
    digest = hashlib.sha256()
    for tile in partition.tiles():
        for face in partition.faces(tile, lambda cell_id: True):
            first, second = face.first_cell_id, face.second_cell_id
            if first >= second or second - first not in (1, size):
                raise ValueError("noncanonical synthetic D4 face")
            digest.update(f"{face.face_id}:{first}:{second}:{face.owner_tile_id}:{face.neighbor_tile_id};".encode("ascii"))
            face_count += 1
            cross_count += face.crosses_tile
        for cell_id in partition.open_boundary_cells(tile, lambda cell_id: True,
                                                      lambda cell_id: cell_id // size in (0, size - 1)
                                                      or cell_id % size in (0, size - 1)):
            open_count += 1
    expected_faces = 2 * size * (size - 1)
    if face_count != expected_faces or open_count != 4 * size - 4:
        raise ValueError("synthetic native full-grid coverage mismatch")
    return {"shape_zx": [size, size], "tile_count": partition.tile_count,
            "face_count": face_count, "cross_tile_face_count": cross_count,
            "true_grid_perimeter_open_cells": open_count, "canonical_face_stream_sha256": digest.hexdigest(),
            "synthetic_full_valid_grid": True, "td_terrain_generated": False, "solver_advanced": False}


def main():
    results = {str(size): verify_size(size) for size in (1024, 2048)}
    print(json.dumps({"schema": "td-native-domain-partition-synthetic-verification-v1", "cases": results,
                      "rain_streaming_implemented": False, "synchronous_halo_solver_implemented": False,
                      "global_6e9_work_limit_changed": False}, indent=2))


if __name__ == "__main__":
    main()
