"""Read a saved world terrain and water product at a native cell."""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import identity
from terrain_pipeline.world_river_network_io import read_network, query_node


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product")
    parser.add_argument("--native-xz", nargs=2, type=int, required=True, metavar=("X", "Z"))
    args = parser.parse_args(argv)
    path = Path(args.product)
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    x = args.native_xz[0] - metadata["origin_native_xz"][0]
    z = args.native_xz[1] - metadata["origin_native_xz"][1]
    rows, cols = metadata["shape_zx"]
    if not (0 <= x < cols and 0 <= z < rows):
        raise ValueError("cell is outside the prepared product")
    with np.load(path / "arrays.npz", allow_pickle=False) as arrays:
        data = {name: arrays[name] for name in arrays.files}
    if not data or any(value.shape != (rows, cols) for value in data.values()):
        raise ValueError("product array shape mismatch")
    expected = metadata.pop("identity_sha256")
    if identity(data, metadata) != expected:
        raise ValueError("product identity mismatch")
    values = {}
    for name, array in data.items():
        value = array[z, x].item()
        values[name] = None if isinstance(value, float) and not math.isfinite(value) else value
    network = metadata.get("network")
    node = None if network is None else query_node(read_network(path, network), args.native_xz, network.get("metadata"))
    print(json.dumps({"native_xz": args.native_xz, "identity_sha256": expected,
                      "values": values, "river_network": node}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
