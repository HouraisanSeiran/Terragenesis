"""Solve a bounded composition once and describe its storage-tile crossings."""
from __future__ import annotations

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.world_water_formation import form_water_and_rivers


def form_connected_region(composition, origin_native_xz, *, world_seed=20261020,
                          runoff_m_per_year, duration_seconds, channel_threshold_m3_s,
                          tile_side_cells=128, min_lake_area_m2=10000.):
    if type(tile_side_cells) is not int or tile_side_cells <= 0:
        raise ValueError("positive integer tile_side_cells required")
    if not isinstance(composition, dict) or not isinstance(composition.get("metadata"), dict):
        raise ValueError("composition and metadata required")
    metadata = composition["metadata"]
    expected_origin = metadata.get("crop_origin_native_xz", metadata.get("origin_native_xz"))
    if list(origin_native_xz) != expected_origin or metadata.get("world_seed") != world_seed:
        raise ValueError("composition origin and world seed must match")
    height = np.asarray(composition["composed_elevation_m"], dtype=np.float64)
    valid = np.asarray(composition["valid_mask"])
    if valid.dtype != np.bool_ or valid.shape != height.shape or not valid.all():
        raise ValueError("composition region must be fully resolved")
    ocean = composition.get("ocean_mask")
    if ocean is None:
        ocean = np.zeros(height.shape, bool)
    result = form_water_and_rivers(height, ocean, origin_native_xz, world_seed, metadata,
        runoff_m_per_year=runoff_m_per_year, duration_seconds=duration_seconds,
        channel_threshold_m3_s=channel_threshold_m3_s,
        sea_level_m=metadata.get("sea_level_m") if metadata.get("sea_level_m") is not None else 0.,
        min_lake_area_m2=min_lake_area_m2)
    arrays = result["arrays"]
    receiver = arrays["receiver"]
    rows, cols = receiver.shape
    z, x = np.indices((rows, cols), dtype=np.int64)
    native_x = x + origin_native_xz[0]
    native_z = z + origin_native_xz[1]
    live = receiver >= 0
    safe = np.maximum(receiver, 0)
    arrays["receiver_native_x"] = np.where(live, native_x.ravel()[safe], -1)
    arrays["receiver_native_z"] = np.where(live, native_z.ravel()[safe], -1)
    spill_receiver = arrays["spill_receiver"]
    spill_live = spill_receiver >= 0
    spill_safe = np.maximum(spill_receiver, 0)
    arrays["spill_receiver_native_x"] = np.where(spill_live, native_x.ravel()[spill_safe], -1)
    arrays["spill_receiver_native_z"] = np.where(spill_live, native_z.ravel()[spill_safe], -1)
    spill_active = spill_live & (arrays["spill_edge_volume_m3"] > 0.)
    spill_crossed = spill_active & ((native_x // tile_side_cells != arrays["spill_receiver_native_x"] // tile_side_cells)
                                    | (native_z // tile_side_cells != arrays["spill_receiver_native_z"] // tile_side_cells))
    crossed = live & ((native_x // tile_side_cells != arrays["receiver_native_x"] // tile_side_cells)
                      | (native_z // tile_side_cells != arrays["receiver_native_z"] // tile_side_cells))
    complete = arrays["complete_mask"]
    channel = arrays["channel_mask"]
    channel_edge = live & channel & channel.ravel()[safe]
    paths = _terminal_categories(arrays)
    selected = channel & complete
    stats = {"routing_cross_tile_edges": int(crossed.sum()),
        "complete_routing_cross_tile_edges": int((crossed & complete).sum()),
        "channel_cross_tile_edges": int((crossed & channel_edge).sum()),
        "complete_channel_cross_tile_edges": int((crossed & channel_edge & complete).sum()),
        "active_spill_edges": int(spill_active.sum()),
        "active_spill_cross_tile_edges": int(spill_crossed.sum()),
        "complete_channel_cells_by_terminal": {name: int((selected & (paths == name)).sum())
            for name in ("ocean", "lake", "unknown", "pending", "other")}}
    result_metadata = {"schema": "world-connected-water-v1", "formation": result["metadata"],
        "formation_identity_sha256": result["identity_sha256"], "tile_side_cells": tile_side_cells,
        "tile_grid": "absolute native coordinates; floor division by tile_side_cells",
        "receiver_coordinates": "world native x/z; each receiver<0 identifies its terminal; spill edges are active only with positive spill_edge_volume_m3",
        "spill_chain_destinations": _spill_destinations(result["metadata"]["basin_transfer_links"]),
        "statistics": stats, "scope": "one finite joint region; tile crossings do not certify world connectivity",
        "path_count_semantics": "complete channel source cells grouped by downstream terminal; paths may overlap"}
    product = {"arrays": arrays, "metadata": result_metadata}
    if result.get("network") is not None:
        product["network"] = result["network"]
        result_metadata["network"] = result["metadata"]["network"]
        result_metadata["network_identity_sha256"] = identity(result["network"], result_metadata["network"])
    product["identity_sha256"] = identity(arrays, result_metadata)
    return product


def _spill_destinations(links):
    by_label = {link["source_label"]: link for link in links}
    result = []
    for link in links:
        labels = []
        current = link
        while current is not None and current["source_label"] not in labels:
            labels.append(current["source_label"])
            if current["volume_m3"] is None or current["volume_m3"] <= 0:
                destination = "pending" if current["volume_m3"] is None else "retained"
                break
            target = current["target_label"]
            if target is None:
                destination = current["destination"]
                break
            current = by_label.get(target)
            if current is None:
                destination = "unknown"
                break
        else:
            destination = "cycle"
        result.append({"source_label": link["source_label"], "labels": labels, "destination": destination})
    return result


def _terminal_categories(arrays):
    receiver = arrays["receiver"].ravel()
    labels = arrays["basin_label"].ravel()
    kinds = arrays["terminal_kind"].ravel()
    pending = arrays["pending_basin_mask"].ravel()
    lake = arrays["lake_support_mask"].ravel()
    categories = np.full(receiver.size, "", dtype="U8")
    for start in range(receiver.size):
        if categories[start]:
            continue
        path = []
        current = start
        while receiver[current] >= 0 and not categories[current]:
            path.append(current)
            current = int(receiver[current])
        if categories[current]:
            category = categories[current]
        elif pending[current]:
            category = "pending"
        elif lake[current] and labels[current] >= 0:
            category = "lake"
        elif kinds[current] == "open_outflow":
            category = "ocean"
        elif kinds[current] == "unknown_boundary":
            category = "unknown"
        else:
            category = "other"
        categories[current] = category
        categories[path] = category
    return categories.reshape(arrays["receiver"].shape)
