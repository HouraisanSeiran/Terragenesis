"""Disk-backed bounded-region priority-flood primitives."""
from __future__ import annotations

import math
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np
from numba import njit

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_lake_storage import LakeStorage, MAX_LAKE_CELLS
from terrain_pipeline.td_lithology_field import sample_lithology_points
from terrain_pipeline.world_basin_transfer import transfer_basins
from terrain_pipeline.world_disk_catchment import certify_raw_catchments
from terrain_pipeline.irregular_drainage import build_mesh, route_graph


@njit
def _accumulate(order, receiver, ocean, flow, unknown, rows, cols, local):
    n = rows * cols
    for i in range(n):
        row, col = i // cols, i % cols
        flow[i] = 0. if ocean[i] else local
        unknown[i] = not ocean[i] and (row < 6 or col < 6 or row >= rows - 6 or col >= cols - 6)
    for i in range(n - 1, -1, -1):
        cell = order[i]
        target = receiver[cell]
        if target >= 0:
            flow[target] += flow[cell]
            unknown[target] |= unknown[cell]


@njit
def _propagate_unknown(order, receiver, unknown):
    for i in range(order.size - 1, -1, -1):
        cell = order[i]
        target = receiver[cell]
        if target >= 0 and unknown[cell]:
            unknown[target] = 1


@njit
def _basin_labels(bed, filled, labels, stack, indptr, indices):
    """Label positive-fill components on the drainage mesh."""
    labels[:] = -1
    count = 0
    for start in range(bed.size):
        if labels[start] >= 0 or filled[start] <= bed[start]:
            continue
        labels[start] = count
        stack[0] = start
        size = 1
        while size:
            size -= 1
            cell = stack[size]
            for edge in range(indptr[cell], indptr[cell + 1]):
                target = indices[edge]
                if labels[target] < 0 and filled[target] > bed[target]:
                    labels[target] = count
                    stack[size] = target
                    size += 1
        count += 1
    return count


class _DiskBasinStore:
    """Original-bed prism inventory, evaluated in bounded chunks."""

    def __init__(self, bed, labels, label, minimum, maximum):
        self.bed = bed.ravel()
        self.labels = labels
        self.label = label
        self.minimum = minimum
        self.maximum = maximum

    def volume_at_stage(self, stage):
        total = 0.
        for start in range(0, self.labels.size, 65536):
            section = slice(start, min(start + 65536, self.labels.size))
            selected = self.labels[section] == self.label
            total += float(np.maximum(stage - self.bed[section][selected], 0.).sum()) * 900.
        return total

    def stage_at_volume(self, volume):
        if volume <= 0.:
            return self.minimum
        low, high = self.minimum, self.maximum
        for _ in range(60):
            middle = (low + high) * .5
            if self.volume_at_stage(middle) < volume:
                low = middle
            else:
                high = middle
        return (low + high) * .5


def _mapped(stack, array):
    stack.callback(array._mmap.close)
    return array


def route_disk(height_path, outlets_path, work_dir, *, local_q_m3_s=0., ocean_path=None,
               mesh=None, origin_native_xz=(0, 0), world_seed=20261020):
    """Return working mappings owned by the caller, who must close each mapping."""
    with ExitStack() as inputs, ExitStack() as outputs:
        result = _route_disk(height_path, outlets_path, work_dir, local_q_m3_s, ocean_path, inputs, outputs,
                             mesh, origin_native_xz, world_seed)
        outputs.pop_all()
        return result


def _route_disk(height_path, outlets_path, work_dir, local_q_m3_s, ocean_path, inputs, outputs,
                mesh, origin_native_xz, world_seed):
    bed = _mapped(inputs, np.load(height_path, mmap_mode="r", allow_pickle=False))
    outlets = _mapped(inputs, np.load(outlets_path, mmap_mode="r", allow_pickle=False))
    if bed.ndim != 2 or bed.dtype != np.float64 or outlets.shape != bed.shape or outlets.dtype != np.bool_:
        raise ValueError("float64 height and matching boolean outlets required")
    if not np.isfinite(bed).all() or not outlets.any() or not math.isfinite(local_q_m3_s) or local_q_m3_s < 0.:
        raise ValueError("finite terrain, outlet and nonnegative flow required")
    ocean = _mapped(inputs, np.load(ocean_path, mmap_mode="r", allow_pickle=False)) if ocean_path else np.zeros(bed.shape, bool)
    if ocean.shape != bed.shape or ocean.dtype != np.bool_:
        raise ValueError("matching boolean ocean required")
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=False)
    n = bed.size
    arrays = {}
    for name, dtype in (("filled", "f8"), ("order", "i8"), ("rank", "i8"), ("heap", "i8"),
                        ("receiver", "i8"), ("flow", "f8"), ("unknown", "u1"),
                        ("basin_label", "i8")):
        arrays[name] = _mapped(outputs, np.lib.format.open_memmap(work / (name + ".npy"), mode="w+", dtype=dtype, shape=(n,)))
    if mesh is None:
        mesh = build_mesh(bed.shape, origin_native_xz=origin_native_xz, world_seed=world_seed)
    routing = route_graph(bed, outlets, mesh)
    for name in ("filled", "order", "rank", "receiver"):
        arrays[name][:] = getattr(routing, name).ravel()
    _accumulate(arrays["order"], arrays["receiver"], ocean.ravel(), arrays["flow"], arrays["unknown"],
                *bed.shape, local_q_m3_s)
    _basin_labels(bed.ravel(), arrays["filled"], arrays["basin_label"], arrays["heap"],
                  mesh.indptr, mesh.indices)
    for array in arrays.values():
        array.flush()
    return arrays


def _solve_disk_region(height_path, ocean_path, work_dir, *, stack, origin_native_xz, world_seed=20261020,
                      runoff_m_per_year, duration_seconds, channel_threshold_m3_s,
                      min_lake_area_m2=10000., sea_level_m=0.):
    """Solve a finite rectangle using disk-backed global routing and basin stores."""
    from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry

    if (len(origin_native_xz) != 2 or any(type(v) is not int for v in origin_native_xz)
            or not math.isfinite(runoff_m_per_year) or runoff_m_per_year < 0.
            or not math.isfinite(duration_seconds) or duration_seconds <= 0.
            or not math.isfinite(channel_threshold_m3_s) or channel_threshold_m3_s <= 0.
            or not math.isfinite(min_lake_area_m2) or min_lake_area_m2 <= 0.
            or not math.isfinite(sea_level_m)):
        raise ValueError("invalid finite region or forcing")
    bed = _mapped(stack, np.load(height_path, mmap_mode="r", allow_pickle=False))
    ocean = _mapped(stack, np.load(ocean_path, mmap_mode="r", allow_pickle=False))
    if bed.ndim != 2 or min(bed.shape) < 4 or ocean.shape != bed.shape or ocean.dtype != np.bool_:
        raise ValueError("matching finite 2D terrain and ocean required")
    if np.any(bed[ocean] > sea_level_m):
        raise ValueError("ocean bed exceeds sea level")
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=False)
    rows, cols = bed.shape
    outlets = _mapped(stack, np.lib.format.open_memmap(root / "outlets.npy", mode="w+", dtype=np.bool_, shape=bed.shape))
    outlets[:] = ocean
    outlets[[0, -1], :] = True
    outlets[:, [0, -1]] = True
    outlets.flush()
    mesh = build_mesh(bed.shape, origin_native_xz=origin_native_xz, world_seed=world_seed)
    local = float(runoff_m_per_year) * 900. / (365.25 * 86400.)
    arrays = route_disk(height_path, root / "outlets.npy", root / "routing", local_q_m3_s=local, ocean_path=ocean_path, mesh=mesh)
    for value in arrays.values():
        _mapped(stack, value)
    labels = arrays["basin_label"]
    filled = arrays["filled"]
    original_receiver = _mapped(stack, np.lib.format.open_memmap(root / "spill_receiver_work.npy", mode="w+", dtype=np.int64,
                                                   shape=(bed.size,)))
    original_receiver[:] = arrays["receiver"]
    original_receiver.flush()
    basin_count = int(labels.max()) + 1
    counts = np.zeros(basin_count, np.int64)
    for start in range(0, bed.size, 65536):
        values = labels[start:min(start + 65536, bed.size)]
        counts += np.bincount(values[values >= 0], minlength=basin_count)
    basin_ids = [int(i) for i in range(basin_count) if counts[i] * 900. >= min_lake_area_m2]
    raw_catchments = certify_raw_catchments(bed, labels.reshape(bed.shape), root / "raw-catchment", mesh=mesh)
    for start in range(0, bed.size, 65536):
        section = slice(start, min(start + 65536, bed.size))
        outlets.ravel()[section] |= np.isin(labels[section], basin_ids)
    outlets.flush()
    spill_arrays = arrays
    arrays = route_disk(height_path, root / "outlets.npy", root / "local-routing", local_q_m3_s=local, ocean_path=ocean_path, mesh=mesh)
    for value in arrays.values():
        _mapped(stack, value)
    receiver = arrays["receiver"]
    geometry_receiver = np.array(receiver, copy=True)
    for start in range(0, bed.size, 65536):
        section = slice(start, min(start + 65536, bed.size))
        targets = receiver[section]
        into_ocean = (targets >= 0) & ocean.ravel()[np.maximum(targets, 0)]
        targets[into_ocean] = -1
    _accumulate(arrays["order"], receiver, ocean.ravel(), arrays["flow"], arrays["unknown"], rows, cols, local)
    basins, stores, paths = [], {}, {}
    source_sha = file_sha256(height_path)
    for label in basin_ids:
        cells = _mapped(stack, np.lib.format.open_memmap(root / ("members-%d.npy" % label), mode="w+", dtype=np.int64,
                                         shape=(int(counts[label]),)))
        position = 0
        for start in range(0, bed.size, 65536):
            indices = np.flatnonzero(labels[start:min(start + 65536, bed.size)] == label) + start
            cells[position:position + indices.size] = indices
            position += indices.size
        beds = _mapped(stack, np.lib.format.open_memmap(root / ("beds-%d.npy" % label), mode="w+", dtype=np.float64,
                                        shape=(cells.size,)))
        for start in range(0, cells.size, 65536):
            section = slice(start, min(start + 65536, cells.size))
            beds[section] = bed.ravel()[cells[section]]
        spill = float(filled[cells].max())
        rim_clear = min(int((cells // cols).min()), int((cells % cols).min()),
                        int(rows - 1 - (cells // cols).max()), int(cols - 1 - (cells % cols).max()))
        raw = raw_catchments[label]
        rim_clear -= 1
        complete = (rim_clear >= 6 and not arrays["unknown"][cells].any()
                    and raw["unknown_cells"] == 0 and raw["leaked_cells"] == 0)
        exits = [int(original_receiver[c]) for c in cells if original_receiver[c] >= 0
                 and labels[original_receiver[c]] != label and abs(filled[original_receiver[c]] - spill) <= 1e-9]
        complete = complete and float(filled[cells].max() - filled[cells].min()) <= 1e-9
        if exits:
            complete = complete and all(min(exit_cell // cols, exit_cell % cols,
                rows - 1 - exit_cell // cols, cols - 1 - exit_cell % cols) >= 6 for exit_cell in exits)
        path = []
        target = None
        if exits:
            current = min(exits, key=lambda c: (int(spill_arrays["rank"][c]), c))
            while current >= 0:
                path.append(current)
                next_label = int(labels[current])
                if next_label in basin_ids or ocean.ravel()[current]:
                    if next_label in basin_ids:
                        target = next_label
                    break
                current = int(original_receiver[current])
        else:
            complete = False
        if cells.size <= MAX_LAKE_CELLS:
            store = LakeStorage(cell_ids=np.array(cells, dtype=np.int64), bed_elevation_m=np.array(beds),
                cell_area_m2=np.full(cells.size, 900., np.float64), seed_cell_id=int(cells[np.argmin(beds)]),
                max_stage_m=spill + 1., source_identity_sha256=source_sha,
                footprint_policy="joint region positive-fill component")
        else:
            store = _DiskBasinStore(bed, labels, label, float(beds.min()), spill)
        stores[label] = store
        paths[label] = path
        destination = "lake" if target is not None else "ocean" if path and ocean.ravel()[path[-1]] else "unknown"
        basins.append({"label": label, "local_m3": float(arrays["flow"][cells].sum()) * duration_seconds,
                       "capacity_m3": store.volume_at_stage(spill), "downstream": target,
                       "destination": destination, "complete": bool(complete),
                       "raw_unknown_cells": raw["unknown_cells"], "raw_leaked_cells": raw["leaked_cells"],
                       "rim_clearance_cells": rim_clear,
                       "filled_level_range_m": float(filled[cells].max() - filled[cells].min())})
        cells._mmap.close()
        beds._mmap.close()
    spill_seen = _mapped(stack, np.lib.format.open_memmap(root / "spill_unknown_work.npy", mode="w+", dtype=np.uint8, shape=(bed.size,)))
    while True:
        settled = transfer_basins(basins)
        for basin in basins:
            if settled[basin["label"]]["complete"]:
                continue
            members = _mapped(stack, np.load(root / ("members-%d.npy" % basin["label"]), mmap_mode="r"))
            for cell in members:
                current = int(original_receiver[cell])
                while current >= 0 and not ocean.ravel()[current] and not spill_seen[current]:
                    spill_seen[current] = 1
                    arrays["unknown"][current] = 1
                    current = int(original_receiver[current])
            members._mmap.close()
        _propagate_unknown(arrays["order"], receiver, arrays["unknown"])
        changed = False
        for basin in basins:
            members = _mapped(stack, np.load(root / ("members-%d.npy" % basin["label"]), mmap_mode="r"))
            has_unknown = False
            for start in range(0, members.size, 65536):
                if arrays["unknown"][members[start:start + 65536]].any():
                    has_unknown = True
                    break
            members._mmap.close()
            if basin["complete"] and has_unknown:
                basin["complete"] = False
                changed = True
        if not changed:
            break
    output_names = ("bed_before_m", "ocean_mask", "channel_mask", "protected_shore_mask", "water_surface_m", "lake_mask", "pending_basin_mask", "spill_routed_volume_m3",
                    "spill_edge_volume_m3", "lake_support_mask", "complete_mask", "known_q_m3_s",
                    "channel_width_m", "design_incision_depth_m", "cut_depth_m", "final_bed_m",
                    "bed_hardness", "bank_hardness", "representative_q_m3_s")
    output = {}
    for name in output_names:
        dtype = np.bool_ if name in ("ocean_mask", "channel_mask", "protected_shore_mask", "lake_mask", "pending_basin_mask", "lake_support_mask", "complete_mask") else np.float64
        output[name] = _mapped(stack, np.lib.format.open_memmap(root / (name + ".npy"), mode="w+", dtype=dtype, shape=bed.shape))
    output["water_surface_m"][:] = np.nan
    output["complete_mask"][:] = ~arrays["unknown"].reshape(bed.shape).astype(bool)
    output["water_surface_m"][ocean] = sea_level_m
    links = []
    for basin in basins:
        label = basin["label"]
        result = settled[label]
        cells = _mapped(stack, np.load(root / ("members-%d.npy" % label), mmap_mode="r"))
        if not result["complete"]:
            output["pending_basin_mask"].ravel()[cells] = True
            output["complete_mask"].ravel()[paths[label]] = False
        else:
            output["lake_support_mask"].ravel()[cells] = True
            stage = stores[label].stage_at_volume(result["stored_m3"])
            wet = cells[bed.ravel()[cells] < stage]
            output["lake_mask"].ravel()[wet] = True
            output["water_surface_m"].ravel()[wet] = stage
            output["spill_routed_volume_m3"].ravel()[paths[label]] += result["outflow_m3"]
            output["spill_edge_volume_m3"].ravel()[paths[label][:-1]] += result["outflow_m3"]
        reason = None if result["complete"] else ("raw_catchment_unknown_or_leaked" if basin["raw_unknown_cells"] or basin["raw_leaked_cells"] else "incomplete_support_or_upstream")
        seed = int(cells[np.argmin(bed.ravel()[cells])])
        links.append({**basin, **result, "pending_reason": reason, "reason": reason,
                      "lake_exit_source_node": min((int(cell) for cell in cells if paths[label] and original_receiver[cell] == paths[label][0]), default=None),
                      "status": ("lake" if result["stored_m3"] > 0. else "dry") if result["complete"] else "pending",
                      "water_surface_m": float(stage) if result["complete"] and result["stored_m3"] > 0. else None,
                      "seed_rc": [seed // cols, seed % cols], "area_m2": int(cells.size) * 900.,
                      "path_flat": paths[label]})
        cells._mmap.close()
    from scipy.ndimage import binary_dilation
    q = arrays["flow"].reshape(bed.shape) + output["spill_routed_volume_m3"] / duration_seconds
    pending = ~output["complete_mask"] | output["pending_basin_mask"]
    shore = binary_dilation(output["lake_support_mask"] | output["pending_basin_mask"],
                            structure=np.ones((3, 3), bool), iterations=2)
    channel = (~ocean & ~output["lake_support_mask"] & ~output["pending_basin_mask"]
               & ~pending & (q >= channel_threshold_m3_s))
    x = (origin_native_xz[0] + np.arange(cols))[None, :] * 30.
    z = (origin_native_xz[1] + np.arange(rows))[:, None] * 30.
    rock = sample_lithology_points(x, z, world_seed=world_seed)
    geometry = build_irregular_channel_geometry(bed, q, channel, mesh, geometry_receiver,
        bed_hardness=rock["bed_hardness"], bank_hardness=rock["bank_hardness"],
        protected_mask=ocean | shore | pending, complete_mask=output["complete_mask"],
        lake_mask=output["lake_support_mask"], ocean_mask=ocean)
    geom = geometry["arrays"]
    for name in ("channel_width_m", "cut_depth_m", "bed_hardness", "bank_hardness"):
        output[name][:] = geom[name]
    output["design_incision_depth_m"][:] = geom["channel_depth_m"]
    output["bed_before_m"][:] = bed
    output["ocean_mask"][:] = ocean
    output["channel_mask"][:] = channel
    output["protected_shore_mask"][:] = shore
    output["representative_q_m3_s"][:] = np.where(pending | ocean, np.nan, q)
    output["known_q_m3_s"][:] = q
    original_cut = output["cut_depth_m"].copy()
    if ocean.any():
        eligible = ~ocean & (bed >= sea_level_m)
        output["cut_depth_m"][eligible] = np.minimum(output["cut_depth_m"][eligible], bed[eligible] - sea_level_m)
    output["final_bed_m"][:] = bed - output["cut_depth_m"]
    geometry["metadata"]["sea_level_cut_limit"] = {
        "enabled": bool(ocean.any()),
        "limited_cells": int(np.count_nonzero(output["cut_depth_m"] < original_cut)),
        "avoided_cut_bulk_m3": float((original_cut - output["cut_depth_m"]).sum()) * 900.}
    removed = float(output["cut_depth_m"].sum()) * 900.
    geometry["metadata"]["material_budget"].update({
        "coarse_raster_edit_bulk_m3": removed, "removed_terrain_bulk_m3": removed,
        "unplaced_excavated_bulk_m3": removed})
    network_path = root / "river-network.npz"
    spill_volume = output["spill_edge_volume_m3"].ravel()
    spill_sources = np.flatnonzero((spill_volume > 0.) & (original_receiver >= 0))
    lake_exits = [link for link in links if link["lake_exit_source_node"] is not None
                  and link["outflow_m3"] is not None and link["outflow_m3"] > 0.]
    edge_sources = np.concatenate((spill_sources,
        np.asarray([link["lake_exit_source_node"] for link in lake_exits], dtype=np.int64)))
    edge_targets = np.concatenate((np.asarray(original_receiver[spill_sources]),
        np.asarray([link["path_flat"][0] for link in lake_exits], dtype=np.int64)))
    edge_volumes = np.concatenate((np.asarray(spill_volume[spill_sources]),
        np.asarray([link["outflow_m3"] for link in lake_exits], dtype=np.float64)))
    geometry["graph"].update(spill_source_node=edge_sources,
        spill_target_node=edge_targets, spill_volume_m3=edge_volumes)
    geometry["graph_metadata"].update(
        schema="irregular-river-network-v1", node_count=bed.size,
        reach_count=int(geometry["graph"]["reach_source"].size),
        active_spill_edge_count=int(edge_sources.size),
        spill_semantics="positive finite actual outflow edges; basin boundary edge identified by transfer link lake_exit_source_node",
        lake_exit_semantics="lake control-cell node to first exterior node; source bed is protected, no invented shoreline sample")
    np.savez(network_path, **geometry["graph"])
    for value in output.values():
        value.flush()
    production = terminal_volume = ocean_terminal_volume = 0.
    for start in range(0, bed.size, 65536):
        section = slice(start, min(start + 65536, bed.size))
        is_ocean = ocean.ravel()[section]
        terminal = (receiver[section] < 0) & ~np.isin(labels[section], basin_ids)
        flow = arrays["flow"][section]
        production += float((~is_ocean).sum()) * local * duration_seconds
        terminal_volume += float(flow[terminal].sum()) * duration_seconds
        spill_targets = original_receiver[section]
        coastal = (spill_targets >= 0) & ocean.ravel()[np.maximum(spill_targets, 0)]
        ocean_terminal_volume += float(flow[terminal & (is_ocean | coastal)].sum()) * duration_seconds
    stored = sum(b["stored_m3"] or 0. for b in links)
    pending_volume = sum(b["inflow_m3"] for b in links if not b["complete"])
    spill_terminal = sum(b["outflow_m3"] or 0. for b in links if b["downstream"] is None)
    ledger = {"local_production_m3": production, "lake_stored_m3": stored,
              "pending_known_inflow_m3": pending_volume, "local_terminal_m3": terminal_volume,
              "spill_terminal_m3": spill_terminal,
              "residual_m3": production - stored - pending_volume - terminal_volume - spill_terminal}
    ledger["local_terminal_ocean_m3"] = ocean_terminal_volume
    ledger["local_terminal_unknown_m3"] = terminal_volume - ledger["local_terminal_ocean_m3"]
    ledger["spill_terminal_ocean_m3"] = sum(b["outflow_m3"] or 0. for b in links if b["downstream"] is None and b["destination"] == "ocean")
    ledger["spill_terminal_unknown_m3"] = spill_terminal - ledger["spill_terminal_ocean_m3"]
    fields = {name: name + ".npy" for name in output_names}
    for name, data in (("receiver", receiver), ("basin_label", labels),
                       ("node_x_m", mesh.node_x_m), ("node_z_m", mesh.node_z_m),
                       ("routing_elevation_m", arrays["filled"]), ("upstream_unknown_mask", arrays["unknown"].astype(bool)),
                       ("local_routed_q_m3_s", arrays["flow"]), ("spill_receiver", original_receiver)):
        field = _mapped(stack, np.lib.format.open_memmap(root / (name + ".npy"), mode="w+", dtype=data.dtype, shape=bed.shape))
        field[:] = data.reshape(bed.shape)
        field.flush()
        field._mmap.close()
        fields[name] = name + ".npy"
    for name, data in (("receiver", receiver), ("spill_receiver", original_receiver)):
        for coordinate in ("x", "z"):
            field_name = name + "_native_" + coordinate
            field = _mapped(stack, np.lib.format.open_memmap(root / (field_name + ".npy"), mode="w+", dtype=np.int64, shape=bed.shape))
            for start in range(0, bed.size, 65536):
                section = slice(start, min(start + 65536, bed.size))
                target = data[section]
                value = target % cols + origin_native_xz[0] if coordinate == "x" else target // cols + origin_native_xz[1]
                field.ravel()[section] = np.where(target >= 0, value, -1)
            field.flush()
            field._mmap.close()
            fields[field_name] = field_name + ".npy"
    manifest = {"schema": "world-disk-water-v2", "algorithm": "irregular-delaunay-static-fill-spill-v1",
                "origin_native_xz": list(origin_native_xz),
                "shape_zx": list(bed.shape), "world_seed": world_seed, "sea_level_m": sea_level_m, "basins": links,
                "basin_transfer_links": [{"source_label": link["label"], "target_label": link["downstream"],
                    "path_flat": link["path_flat"], "volume_m3": link["outflow_m3"],
                    "lake_exit_source_node": link["lake_exit_source_node"],
                    "destination": link["destination"]} for link in links],
                "water_ledger": ledger, "source_sha256": source_sha,
                "ocean_sha256": file_sha256(ocean_path), "runoff_m_per_year": runoff_m_per_year,
                "duration_seconds": duration_seconds, "channel_threshold_m3_s": channel_threshold_m3_s,
                "scope": "finite joint rectangle; unresolved upstream remains pending",
                "cell_account_area_m2": 900.,
                "terrain_sampling": "one native control-cell representative elevation per displaced graph node",
                "unknown_boundary_band_cells": 6,
                "basin_certification": "global fill constancy, exit and rim clearance, raw catchment and local routed unknown",
                "min_lake_area_m2": min_lake_area_m2,
                "geometry_policy": "continuous irregular graph segments with cross-section incision; lake shore protected; ocean floor",
                "geometry": geometry["metadata"],
                "material_budget": {"coarse_raster_edit_bulk_m3": float(output["cut_depth_m"].sum()) * 900.},
                "spill_exit_policy": "eligible actual basin exit, lowest flood rank then row-major index",
                "field_sha256": {name: file_sha256(root / path) for name, path in fields.items()}}
    result = {"fields": fields, "metadata": manifest,
              "network": {"file": network_path.name, "sha256": file_sha256(network_path),
                          "metadata": geometry["graph_metadata"]}}
    (root / "manifest.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result


def solve_disk_region(height_path, ocean_path, work_dir, *, origin_native_xz, world_seed=20261020,
                      runoff_m_per_year, duration_seconds, channel_threshold_m3_s,
                      min_lake_area_m2=10000., sea_level_m=0.):
    with ExitStack() as stack:
        return _solve_disk_region(height_path, ocean_path, work_dir, stack=stack, origin_native_xz=origin_native_xz,
            world_seed=world_seed, runoff_m_per_year=runoff_m_per_year, duration_seconds=duration_seconds,
            channel_threshold_m3_s=channel_threshold_m3_s, min_lake_area_m2=min_lake_area_m2,
            sea_level_m=sea_level_m)
