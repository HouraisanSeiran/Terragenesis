"""Run one synthetic cross-seam transport step and report bounded diagnostics."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.td_native_domain_partition import NativePartition, StageSnapshot
from terrain_pipeline.td_native_partition_transport import transport


def _snapshot(partition, values, version):
    chunks = {}
    for tile in partition.tiles():
        z0, z1, x0, x1 = tile.interior_zx
        chunks[tile.tile_id] = (version, values[z0:z1, x0:x1])
    return StageSnapshot(partition, version, chunks)


def main():
    shape = (259, 258)
    partition = NativePartition(shape)
    bed = np.zeros(shape, dtype=np.float64)
    depth = np.zeros(shape, dtype=np.float64)
    depth[255, 256] = 1.
    depth[256, 255] = .8
    depth[255, 255] = .2
    depth[0, 0] = .4
    valid = np.ones(shape, dtype=bool)
    valid[3, 4] = False
    opened = np.zeros(shape, dtype=bool)
    opened[0, 0] = True
    result = transport(partition, _snapshot(partition, bed, "bed"), _snapshot(partition, depth, "start"),
                       valid, opened, spacing_m=30., dt_s=1., steps=2)
    chunks = b"".join(result["final_tile_chunks"][tile.tile_id].tobytes() for tile in partition.tiles())
    report = {"schema": "td-native-partition-transport-synthetic-diagnostic-v1",
              "shape_zx": list(shape), "tile_count": partition.tile_count, "face_count": len(result["face_ids"]),
              "face_steps": result["face_steps"], "reverse_m3": float(result["reverse_m3"].sum()),
              "forward_m3": float(result["forward_m3"].sum()),
              "boundary_outflow_m3": float(result["boundary_outflow_m3"].sum()),
              "volume_budget": result["volume_budget"], "final_tile_chunks_sha256": hashlib.sha256(chunks).hexdigest(),
              "synthetic_not_td_terrain": True, "full_day_accepted": False, "numba_used": False}
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
