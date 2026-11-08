"""Bounded synchronous native-tile SSP-RK2 transport prototype; no solver import."""

import math

import numpy as np

from terrain_pipeline.td_native_domain_partition import NativePartition, StageSnapshot


MAX_CELLS = 250000
MAX_FACE_STEPS = 6000000000
MAX_BYTES = 1073741824
CONDUCTANCE_M_S = .6


def _check_mask(mask, shape, name):
    if not isinstance(mask, np.ndarray) or mask.shape != shape or mask.dtype != bool:
        raise ValueError(name + " must be a full native bool grid")
    return mask


def _chunks(partition, flat, version):
    grid = flat.reshape(partition.shape_zx)
    return StageSnapshot(partition, version, {
        tile.tile_id: (version, grid[tile.interior_zx[0]:tile.interior_zx[1],
                                     tile.interior_zx[2]:tile.interior_zx[3]])
        for tile in partition.tiles()})


def _read(snapshot, tile, halo, cell_id):
    row, column = divmod(cell_id, snapshot.partition.shape_zx[1])
    return float(halo[row - tile.halo_zx[0], column - tile.halo_zx[2]])


def _stage(partition, bed, depth, faces, boundaries, spacing_m, tile_order):
    if bed.partition != partition or depth.partition != partition:
        raise ValueError("snapshot partition mismatch")
    rates = np.empty(len(faces), dtype=np.float64)
    by_owner = [[] for _ in range(partition.tile_count)]
    for index, face in enumerate(faces):
        by_owner[face.owner_tile_id].append(index)
    for tile_id in tile_order:
        tile = partition.tile(tile_id)
        bed_halo = bed.sample_halo(tile, version=bed.version)
        depth_halo = depth.sample_halo(tile, version=depth.version)
        for index in by_owner[tile_id]:
            face = faces[index]
            first_bed = _read(bed, tile, bed_halo, face.first_cell_id)
            second_bed = _read(bed, tile, bed_halo, face.second_cell_id)
            first_head = first_bed + _read(depth, tile, depth_halo, face.first_cell_id)
            second_head = second_bed + _read(depth, tile, depth_halo, face.second_cell_id)
            sill = max(first_bed, second_bed)
            if first_head >= second_head:
                rates[index] = CONDUCTANCE_M_S / spacing_m * max(first_head - max(sill, second_head), 0.)
            else:
                rates[index] = -CONDUCTANCE_M_S / spacing_m * max(second_head - max(sill, first_head), 0.)
    derivative = np.zeros(partition.shape_zx[0] * partition.shape_zx[1], dtype=np.float64)
    for index, face in enumerate(faces):
        derivative[face.first_cell_id] -= rates[index]
        derivative[face.second_cell_id] += rates[index]
    exported = np.empty(len(boundaries), dtype=np.float64)
    for index, (cell_id, width_m) in enumerate(boundaries):
        tile = partition.tile(partition.owner_of_cell(cell_id))
        depth_halo = depth.sample_halo(tile, version=depth.version)
        exported[index] = CONDUCTANCE_M_S * width_m / spacing_m**2 * _read(depth, tile, depth_halo, cell_id)
        derivative[cell_id] -= exported[index]
    return derivative, rates, exported


def transport(partition, bed, depth, valid_mask, open_mask, *, spacing_m, dt_s, steps=1, tile_order=None):
    if not isinstance(partition, NativePartition) or not isinstance(bed, StageSnapshot) or not isinstance(depth, StageSnapshot):
        raise ValueError("partition and immutable bed/depth snapshots required")
    cells = math.prod(partition.shape_zx)
    if cells > MAX_CELLS or type(steps) is not int or not 1 <= steps <= 8:
        raise ValueError("reference prototype cell/step budget exceeded")
    if (type(spacing_m) not in (int, float) or type(dt_s) not in (int, float)
            or not math.isfinite(spacing_m) or not math.isfinite(dt_s) or spacing_m <= 0 or dt_s <= 0):
        raise ValueError("positive finite metre/second units required")
    valid = _check_mask(valid_mask, partition.shape_zx, "valid mask").ravel()
    opened = _check_mask(open_mask, partition.shape_zx, "open mask").ravel()
    if bed.partition != partition or depth.partition != partition or bed.version == depth.version:
        raise ValueError("bed/depth partition or stage version mismatch")
    order = tuple(range(partition.tile_count)) if tile_order is None else tuple(tile_order)
    if len(order) != partition.tile_count or set(order) != set(range(partition.tile_count)) or any(type(item) is not int for item in order):
        raise ValueError("tile order must be a permutation")
    faces = sorted((face for tile in partition.tiles() for face in partition.faces(tile, lambda cell_id: bool(valid[cell_id]))),
                   key=lambda face: face.face_id)
    boundaries = []
    height, width = partition.shape_zx
    for tile in partition.tiles():
        for cell_id in partition.open_boundary_cells(tile, lambda cell_id: bool(valid[cell_id]),
                                                       lambda cell_id: bool(opened[cell_id])):
            row, column = divmod(cell_id, width)
            edge_count = (row == 0) + (row == height - 1) + (column == 0) + (column == width - 1)
            boundaries.append((cell_id, spacing_m * edge_count))
    boundaries.sort()
    if len(faces) * steps > MAX_FACE_STEPS:
        raise ValueError("global face-work limit exceeded")
    estimate = (96 * cells + 144 * len(faces) + 32 * len(boundaries)) * 8
    if estimate > MAX_BYTES:
        raise MemoryError("prototype 1GiB array/object reserve exceeded")
    degree = np.zeros(cells, dtype=np.float64)
    for face in faces:
        degree[face.first_cell_id] += 1
        degree[face.second_cell_id] += 1
    for cell_id, width_m in boundaries:
        degree[cell_id] += width_m / spacing_m
    cfl = float(degree.max(initial=0)) * CONDUCTANCE_M_S * dt_s / spacing_m
    if cfl > 1:
        raise ValueError("SSP-RK2 positivity CFL exceeded")
    initial = np.empty(cells, dtype=np.float64)
    for tile in partition.tiles():
        z0, z1, x0, x1 = tile.interior_zx
        initial.reshape(partition.shape_zx)[z0:z1, x0:x1] = depth.chunks[tile.tile_id]
    if not np.isfinite(initial).all() or np.any(initial < 0) or np.any(initial[~valid] != 0):
        raise ValueError("initial depth invalid or unknown cell wet")
    current = initial.copy()
    forward = np.zeros(len(faces), dtype=np.float64)
    reverse = np.zeros(len(faces), dtype=np.float64)
    external = np.zeros(len(boundaries), dtype=np.float64)
    area = spacing_m**2
    for step_index in range(steps):
        current_snapshot = _chunks(partition, current, f"depth-step-{step_index}-stage-0")
        derivative0, rate0, boundary0 = _stage(partition, bed, current_snapshot, faces, boundaries, spacing_m, order)
        stage1 = current + dt_s * derivative0
        if np.any(stage1 < 0):
            raise ValueError("SSP-RK2 negative first Euler stage")
        stage1_snapshot = _chunks(partition, stage1, f"depth-step-{step_index}-stage-1")
        derivative1, rate1, boundary1 = _stage(partition, bed, stage1_snapshot, faces, boundaries, spacing_m, order)
        stage2 = stage1 + dt_s * derivative1
        if np.any(stage2 < 0):
            raise ValueError("SSP-RK2 negative second Euler stage")
        current = .5 * current + .5 * stage2
        half_volume = .5 * dt_s * area
        forward += half_volume * (np.maximum(rate0, 0) + np.maximum(rate1, 0))
        reverse += half_volume * (np.maximum(-rate0, 0) + np.maximum(-rate1, 0))
        external += half_volume * (boundary0 + boundary1)
    final_snapshot = _chunks(partition, current, f"depth-final-{steps}")
    before_m3 = float(initial[valid].sum() * area)
    after_m3 = float(current[valid].sum() * area)
    exported_m3 = float(external.sum())
    residual_m3 = before_m3 - after_m3 - exported_m3
    if abs(residual_m3) > 1e-6 + 1e-10 * before_m3:
        raise ValueError("global volume budget failed")
    return {"final_tile_chunks": final_snapshot.chunks,
            "face_ids": np.array([face.face_id for face in faces], dtype=np.int64),
            "face_cells": np.array([(face.first_cell_id, face.second_cell_id) for face in faces], dtype=np.int64).reshape(-1, 2),
            "forward_m3": forward, "reverse_m3": reverse,
            "boundary_cells": np.array([item[0] for item in boundaries], dtype=np.int64),
            "boundary_outflow_m3": external,
            "volume_budget": {"initial_m3": before_m3, "final_m3": after_m3,
                              "exported_m3": exported_m3, "residual_m3": residual_m3},
            "face_steps": len(faces) * steps, "positivity_cfl": cfl,
            "solver_advanced": True, "full_day_accepted": False}
