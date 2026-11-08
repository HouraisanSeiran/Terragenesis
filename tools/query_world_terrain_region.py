"""Query a prepared region without generating or modifying it."""
import argparse
import json
import math
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from terrain_pipeline.td_source import read_region_component as read_component
from terrain_pipeline.common_infra import identity
from terrain_pipeline.world_river_network_io import read_network, query_node


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store")
    parser.add_argument("--native-xz", nargs=2, type=int, required=True)
    args = parser.parse_args(argv)
    registry = json.loads((Path(args.store) / "registry.json").read_text(encoding="utf-8"))
    if identity({}, registry["world"]) != registry["world_identity"]:
        raise ValueError("world identity mismatch")
    x, z = args.native_xz
    component = next((c for c in registry["components"] if c["bounds"][0] <= x < c["bounds"][2]
                      and c["bounds"][1] <= z < c["bounds"][3]), None)
    if component is None:
        raise ValueError("coordinate has not been prepared")
    if registry.get("schema") == "world-terrain-disk-store-v1":
        from terrain_pipeline.td_source import read_disk_manifest as read_manifest, _sha
        root, manifest = read_manifest(args.store, component, registry["world_identity"])
        values = {}
        for group in ("composition_tiles", "water_tiles"):
            tile = next(t for t in manifest[group] if t["origin_native_xz"][0] <= x < t["origin_native_xz"][0] + t["shape_zx"][1]
                        and t["origin_native_xz"][1] <= z < t["origin_native_xz"][1] + t["shape_zx"][0])
            tile_path = root / tile["file"]
            if _sha(tile_path) != tile["sha256"]:
                raise ValueError("disk region tile identity mismatch")
            row, col = z - tile["origin_native_xz"][1], x - tile["origin_native_xz"][0]
            with np.load(tile_path, allow_pickle=False) as archive:
                for name in archive.files:
                    value = archive[name][row, col].item()
                    values[name] = None if isinstance(value, float) and not math.isfinite(value) else value
        water_metadata = manifest["water_metadata"]
        label = values.get("basin_label")
        basin = next ( (b for b in water_metadata.get("basins", []) if b.get("label") == label), None)
        links = [link for link in water_metadata.get("basin_transfer_links", [])
                 if label is not None and label >= 0 and
                 (link.get("source_label") == label or link.get("target_label") == label)]
        network = manifest.get("network")
        node = None if network is None else query_node(read_network(root, network), [x, z], network.get("metadata"))
        print(json.dumps({"native_xz": [x, z], "component": component, "values": values,
                          "basin": basin, "basin_transfer_links": links, "river_network": node}, indent=2, allow_nan=False))
        return
    arrays, metadata = read_component(args.store, component, registry["world_identity"])
    col, row = x - metadata["origin_native_xz"][0], z - metadata["origin_native_xz"][1]
    values = {}
    for name, array in arrays.items():
        value = array[row, col].item()
        values[name] = None if isinstance(value, float) and not math.isfinite(value) else value
    formation = metadata.get("water", {}).get("formation", {})
    label = values.get("basin_label")
    basin = next((b for b in formation.get("basins", []) if b.get("label") == label), None)
    links = [link for link in formation.get("basin_transfer_links", [])
             if label is not None and label >= 0 and
             (link.get("source_label") == label or link.get("target_label") == label)]
    network = metadata.get("network")
    root = Path(args.store) / "versions" / component["version"]
    node = None if network is None else query_node(read_network(root, network), [x, z], network.get("metadata"))
    print(json.dumps({"native_xz": [x, z], "component": component, "values": values,
                      "basin": basin, "basin_transfer_links": links, "river_network": node}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
