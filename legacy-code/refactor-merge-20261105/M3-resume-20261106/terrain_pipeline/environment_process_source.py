"""Read and pin immutable saved terrain, masks and network windows."""
from pathlib import Path
import json
import math
import numpy as np
from terrain_pipeline.environment_process_storage import MAX_CELLS
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import segments_clear as segments_clear
from terrain_pipeline.common_infra import checked_archive, file_sha256
from terrain_pipeline.td_lithology_field import sample_lithology_points
from terrain_pipeline.world_river_network_io import read_network
from terrain_pipeline.td_source import read_disk_manifest as read_manifest


def context_from_store(store, row, col, size=33):
    """Read and pin an existing source; never generate a TD page or river Q."""
    store = Path(store)
    registry_path = store / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if len(registry["components"]) != 1:
        raise ValueError("select a store with exactly one prepared component")
    root, manifest = read_manifest(store, registry["components"][0], registry["world_identity"])
    graph = read_network(root, manifest["network"])
    shape = tuple(map(int, graph["native_shape"]))
    if min(row, col) < 0 or size < 2 or size * size > MAX_CELLS or row + size > shape[0] or col + size > shape[1]:
        raise ValueError("bounded source window outside saved graph")
    rows, cols = np.indices((size, size))
    source_ids = (rows + row) * shape[1] + cols + col
    remap = np.full(math.prod(shape), -1, np.int64)
    remap[source_ids.ravel()] = np.arange(size * size)
    original_receiver = graph["receiver"][source_ids]
    receiver = np.full((size, size), -1, np.int64)
    linked = original_receiver >= 0
    receiver[linked] = remap[original_receiver[linked]]
    external = linked & (receiver < 0)
    spacing = float(graph["spacing_m"])
    seed = int(manifest["network"]["metadata"]["world_seed"])
    full_mesh = build_mesh(shape, origin_native_xz=tuple(map(int, graph["origin_native_xz"])),
                           spacing_m=spacing, world_seed=seed)
    edge_source = np.repeat(np.arange(math.prod(shape)), np.diff(full_mesh.indptr))
    keep = (remap[edge_source] >= 0) & (remap[full_mesh.indices] >= 0)
    es, et = remap[edge_source[keep]], remap[full_mesh.indices[keep]]
    origin = (int(graph["origin_native_xz"][0]) + col, int(graph["origin_native_xz"][1]) + row)
    source_flags = {}
    tile_sources = []
    for group, needed in (("water_tiles", ("ocean_mask", "channel_mask", "complete_mask", "protected_shore_mask", "pending_basin_mask", "lake_mask", "upstream_unknown_mask")),
                          ("composition_tiles", ("valid_mask",))):
        fields = {name: np.zeros((size, size), bool) for name in needed}
        covered = np.zeros((size, size), bool)
        for tile in manifest[group]:
            tx, tz = tile["origin_native_xz"]
            tr, tc = tile["shape_zx"]
            left, right = max(origin[0], tx), min(origin[0] + size, tx + tc)
            top, bottom = max(origin[1], tz), min(origin[1] + size, tz + tr)
            if right <= left or bottom <= top:
                continue
            path = root / tile["file"]
            data = checked_archive(path, expected_sha256=tile["sha256"])
            target = (slice(top - origin[1], bottom - origin[1]), slice(left - origin[0], right - origin[0]))
            src = (slice(top - tz, bottom - tz), slice(left - tx, right - tx))
            for name in needed:
                fields[name][target] = data[name][src]
            covered[target] = True
            tile_sources.append({"file": str(path.resolve()), "sha256": tile["sha256"]})
        if not covered.all():
            raise ValueError("source masks do not cover selected saved window")
        source_flags.update(fields)
    ocean = source_flags["ocean_mask"]
    valid = source_flags["valid_mask"] & source_flags["complete_mask"]
    donors = np.flatnonzero(receiver.ravel() >= 0)
    blocked = donors[~segments_clear(donors, receiver.ravel()[donors], valid)]
    unresolved = np.zeros((size, size), bool)
    unresolved.ravel()[blocked] = True
    receiver.ravel()[blocked] = -1
    receiver[~valid] = -1
    clear = segments_clear(es, et, valid)
    es, et = es[clear], et[clear]
    river_nodes = np.zeros(math.prod(shape), bool)
    river_nodes[graph.get("reach_source_node", graph.get("reach_source"))] = True
    river_nodes[graph.get("reach_target_node", graph.get("reach_target"))] = True
    ctx = {"height_m": graph["node_raw_bed_m"][source_ids].copy(), "spacing_m": spacing,
           "source_height_m": graph["node_raw_bed_m"][source_ids].copy(),
           "source_receiver_node": original_receiver.copy(),
           "origin_native_xz": list(origin), "world_seed": seed, "receiver": receiver,
           "river_mask": source_flags["channel_mask"], "ocean_mask": ocean,
           "valid_mask": valid, "protected_mask": source_flags["protected_shore_mask"],
           "pending_basin_mask": source_flags["pending_basin_mask"],
           "lake_mask": source_flags["lake_mask"], "source_complete_mask": source_flags["complete_mask"],
           "source_upstream_unknown_mask": source_flags["upstream_unknown_mask"],
           "unresolved_receiver_mask": unresolved,
           "node_x_m": graph["node_x_m"][source_ids], "node_z_m": graph["node_z_m"][source_ids],
           "graph_edge_source": es, "graph_edge_target": et,
           "external_receiver_mask": external,
           "external_receiver_source_node": np.where(external, original_receiver, -1),
           "source_terminal_kind": graph["node_terminal_kind"][source_ids],
           "source_terminal_mask": external | ocean | unresolved | ~valid, "routing_policy": "source_terminal_flood"}
    if not ctx["source_terminal_mask"].any():
        ctx["source_terminal_mask"] = receiver < 0
    lithology = sample_lithology_points((origin[0] + cols) * spacing, (origin[1] + rows) * spacing, world_seed=seed)
    ctx["bed_hardness"] = np.asarray(lithology["bed_hardness"]).reshape(size, size)
    ctx["solubility"] = np.full((size, size), .2)
    sources = {"kind": "saved_generated_TD_terrain_not_observation", "registry_path": str(registry_path.resolve()),
               "registry_sha256": file_sha256(registry_path), "source_world_identity": registry["world_identity"],
               "manifest_sha256": file_sha256(root / "manifest.json"),
               "network_sha256": manifest["network"]["sha256"], "source_pages": registry["pages"],
               "mask_tiles": tile_sources,
               "window_row_col_size": [int(row), int(col), int(size)],
               "external_receiver_cells": int(external.sum()),
               "ocean_identity": "unchanged hash-verified saved water tile ocean_mask; no edge-to-ocean inference",
               "mesh_policy": "saved full-source irregular adjacency restricted to window; real saved node coordinates",
               "routing_policy": "source terminals include external handoff/ocean; no external regeneration",
               "lithology": "same-world sample_lithology_points at native account anchors, seed20261020; graph position offset retained separately",
               "solubility": "declared engineering fraction0.2; existing lithology API does not supply solubility",
               "porosity": "declared engineering regolith porosity0.35; not a sampled material property"}
    return ctx, sources

