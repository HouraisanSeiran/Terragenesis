"""Export pinned natural-network candidates without rebuilding or solving."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.runoff import _strict_json as _strict_json
from terrain_pipeline.td_natural_river_network import load_natural_river_network


MAX_REVIEW_BYTES = 32 * 1024 * 1024


def export_review(output, *, network_record, geometry_record, max_bytes=MAX_REVIEW_BYTES):
    from terrain_pipeline.channel_geometry import load_natural_channel_geometry

    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_REVIEW_BYTES:
        raise ValueError("bounded review byte budget required")
    path = Path(output)
    if path.exists():
        raise FileExistsError(path)
    network = load_natural_river_network(**network_record)
    geometry = load_natural_channel_geometry(**geometry_record)
    if geometry["metadata"]["network_identity_sha256"] != network["identity_sha256"]:
        raise ValueError("saved natural geometry belongs to another network")
    source = network["arrays"]
    bed = geometry["arrays"]
    if (not np.array_equal(bed["node_cell_ids"], source["node_cell_ids"]) or
            not np.array_equal(bed["edge_cell_ids"], source["edge_cell_ids"])):
        raise ValueError("saved natural geometry topology mismatch")
    node_ids = source["node_cell_ids"]
    reach_offsets = source["reach_offsets"]
    reach_cells = source["reach_cell_ids"]
    reaches = []
    for index, (start, stop) in enumerate(zip(reach_offsets[:-1], reach_offsets[1:])):
        cells = reach_cells[start:stop]
        indices = np.searchsorted(node_ids, cells)
        reaches.append({"reach_index": index, "cell_ids": cells.tolist(),
                        "node_indices": indices.tolist(),
                        "bed_centerline_xyz_m": bed["node_world_xyz_m"][indices].tolist()})
    record = {
        "schema": "td-natural-river-review-v1", "workspace": "natural-river-candidates",
        "status": "diagnostic_not_publishable", "units": "metres; X east, Y up, Z south",
        "source_pins": {"network": dict(network_record), "geometry": dict(geometry_record)},
        "network_identity_sha256": network["identity_sha256"],
        "geometry_identity_sha256": geometry["identity_sha256"],
        "grid": {"shape_zx": source["source_height_m"].shape,
                 "origin_m_xz": network["metadata"]["origin_m_xz"],
                 "spacing_m": network["metadata"]["spacing_m"],
                 "terrain_height_m": source["source_height_m"].ravel().tolist(),
                 "valid_mask": source["valid_mask"].ravel().tolist(),
                 "protected_mask": source["protected_mask"].ravel().tolist(),
                 "selected_basin_mask": source["selected_basin_mask"].ravel().tolist()},
        "network": {"node_cell_ids": node_ids.tolist(),
                    "node_native_xyz_m": source["node_native_xyz_m"].tolist(),
                    "node_bed_xyz_m": bed["node_world_xyz_m"].tolist(),
                    "node_width_m": source["node_width_m"].tolist(),
                    "node_depth_m": source["node_depth_m"].tolist(),
                    "edge_cell_ids": source["edge_cell_ids"].tolist(),
                    "edge_level_code": source["edge_level_code"].tolist(),
                    "edge_requires_refinement": source["edge_requires_refinement"].tolist(),
                    "edge_sections_xyz_m": bed["edge_sections_xyz_m"].tolist(),
                    "reaches": reaches},
        "network_metadata": network["metadata"], "geometry_metadata": geometry["metadata"],
        "layer_semantics": {"terrain": "unchanged native TD input, not the full derived bed",
                            "centerline": "shared candidate bed centerline, not water or instantaneous flow",
                            "sections": "candidate cross-sections, not a unified confluence surface",
                            "selected_basin": "one contribution basin only; others are diagnostic statistics"},
        "capabilities": {"terrain_2d_3d": True, "candidate_centerline_3d": True,
                         "water_surface_3d": False, "time_playback": False,
                         "solver_advanced": False, "perlin_forcing": False},
        "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
    }
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > max_bytes:
        raise ValueError("natural review byte budget exceeded before publication")
    for pin in (network_record, geometry_record):
        if file_sha256(pin["path"]) != pin["expected_sha256"]:
            raise ValueError("natural review input pin changed while reading")
    publish_bytes(path, payload)
    return {"path": str(path), "sha256": file_sha256(path), "bytes": len(payload),
            "schema": record["schema"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if file_sha256(args.index) != args.index_sha256:
        raise ValueError("natural delivery index SHA mismatch")
    index = _strict_json(args.index.read_text(encoding="utf-8"))
    if (index.get("schema") != "td-natural-river-delivery-v1" or
            any(index.get(name) is not False for name in
                ("hydraulic_ready", "natural_outlet_verified", "publishable", "solver_advanced"))):
        raise ValueError("natural delivery index schema/certification mismatch")
    records = {}
    for name in ("network", "geometry"):
        pin = index["artifacts"][name]
        relative = Path(pin["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("delivery artifact must remain inside its index directory")
        records[name] = {"path": str(args.index.parent / relative),
                         "expected_sha256": pin["sha256"], "expected_identity": pin["identity_sha256"]}
    print(json.dumps(export_review(args.output, network_record=records["network"],
                                    geometry_record=records["geometry"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
