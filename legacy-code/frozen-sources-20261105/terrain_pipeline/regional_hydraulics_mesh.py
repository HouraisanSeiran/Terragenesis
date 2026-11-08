"""Exact-volume flat-cell water columns, not interpolated continuous water surface."""

import numpy as np


SCHEMA = "regional-flat-cell-water-columns-v1"
TRIANGLES = np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
    [0, 5, 1], [0, 4, 5], [1, 6, 2], [1, 5, 6], [2, 7, 3], [2, 6, 7], [3, 4, 0], [3, 7, 4]], np.int64)


def water_columns(height, depth, *, spacing_m, origin_m_xz, source_identity, time_s):
    if height.shape != depth.shape or height.ndim != 2 or height.size > 65536 or height.dtype != np.float64 or depth.dtype != np.float64:
        raise ValueError("bounded original flat-cell geometry")
    if not np.isfinite(height).all() or not np.isfinite(depth).all() or (depth < 0).any():
        raise ValueError("finite positive saved water depth")
    if not np.isfinite(spacing_m) or spacing_m <= 0 or np.asarray(origin_m_xz).shape != (2,) or not np.isfinite(origin_m_xz).all() or not np.isfinite(time_s) or time_s < 0:
        raise ValueError("finite metric water-column coordinates/time")
    wet = np.flatnonzero(depth.ravel() > 0)
    rows, columns = np.divmod(wet, height.shape[1])
    center_x = origin_m_xz[0] + columns * spacing_m
    center_z = origin_m_xz[1] + rows * spacing_m
    offsets_x = np.array([-.5, .5, .5, -.5, -.5, .5, .5, -.5]) * spacing_m
    offsets_z = np.array([-.5, -.5, .5, .5, -.5, -.5, .5, .5]) * spacing_m
    vertices = np.empty((wet.size, 8, 3), np.float64)
    vertices[:, :, 0] = center_x[:, None] + offsets_x
    vertices[:, :, 2] = center_z[:, None] + offsets_z
    vertices[:, :4, 1] = height.ravel()[wet, None]
    vertices[:, 4:, 1] = (height + depth).ravel()[wet, None]
    triangles = (TRIANGLES[None] + np.arange(wet.size)[:, None, None] * 8).reshape(-1, 3)
    return {"arrays": {"vertices_xyz_m": vertices.reshape(-1, 3), "triangles": triangles,
        "cell_id": wet, "cell_volume_m3": depth.ravel()[wet] * spacing_m**2},
        "metadata": {"schema": SCHEMA, "source_identity": source_identity, "time_s": float(time_s),
            "spacing_m": float(spacing_m), "origin_m_xz": list(origin_m_xz), "shape": list(height.shape),
            "volume_m3": float(depth.sum() * spacing_m**2), "wet_threshold_m": 0.,
            "representation": "independent_closed_step_columns_same_horizontal_edge_positions_no_stage_averaging",
            "continuous_interpolation_volume_certified": False}}


def validate_water_columns(packet, *, trusted_height, saved_depth, source_identity,
                           trusted_spacing_m=None, trusted_origin_m_xz=None):
    arrays, meta = packet["arrays"], packet["metadata"]
    if set(arrays) != {"vertices_xyz_m", "triangles", "cell_id", "cell_volume_m3"} or meta["schema"] != SCHEMA or meta["source_identity"] != source_identity:
        raise ValueError("mesh schema/source")
    wet = np.flatnonzero(saved_depth.ravel() > 0)
    count = wet.size
    specifications = {"vertices_xyz_m": ((count * 8, 3), np.float64), "triangles": ((count * 12, 3), np.int64),
        "cell_id": ((count,), np.int64), "cell_volume_m3": ((count,), np.float64)}
    for key, (shape, dtype) in specifications.items():
        value = arrays[key]
        if value.shape != shape or value.dtype != dtype or not np.isfinite(value).all():
            raise ValueError("exact mesh array schema")
    if not np.array_equal(arrays["cell_id"], wet) or not np.array_equal(arrays["triangles"], (TRIANGLES[None] + np.arange(count)[:, None, None] * 8).reshape(-1, 3)):
        raise ValueError("water-column support/topology")
    vertices = arrays["vertices_xyz_m"].reshape(count, 8, 3)
    spacing = meta["spacing_m"]
    origin = np.asarray(meta["origin_m_xz"])
    if not np.isfinite(spacing) or spacing <= 0 or origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("mesh metric coordinates")
    if meta["shape"] != list(trusted_height.shape) or meta["wet_threshold_m"] != 0. or meta["continuous_interpolation_volume_certified"] is not False or not np.isfinite(meta["time_s"]) or meta["time_s"] < 0:
        raise ValueError("mesh source shape/time/representation")
    if trusted_spacing_m is not None and spacing != trusted_spacing_m:
        raise ValueError("mesh trusted spacing")
    if trusted_origin_m_xz is not None and not np.array_equal(origin, trusted_origin_m_xz):
        raise ValueError("mesh trusted center origin")
    rows, columns = np.divmod(wet, trusted_height.shape[1])
    expected_x = origin[0] + columns[:, None] * spacing + np.array([-.5, .5, .5, -.5, -.5, .5, .5, -.5]) * spacing
    expected_z = origin[1] + rows[:, None] * spacing + np.array([-.5, -.5, .5, .5, -.5, -.5, .5, .5]) * spacing
    if not np.array_equal(vertices[:, :, 0], expected_x) or not np.array_equal(vertices[:, :, 2], expected_z):
        raise ValueError("water footprint/source coordinates")
    if not np.array_equal(vertices[:, :4, 1], np.repeat(trusted_height.ravel()[wet, None], 4, axis=1)) or not np.array_equal(vertices[:, 4:, 1], np.repeat((trusted_height + saved_depth).ravel()[wet, None], 4, axis=1)):
        raise ValueError("saved H0/water stage source")
    volumes = saved_depth.ravel()[wet] * spacing**2
    if not np.array_equal(arrays["cell_volume_m3"], volumes) or not np.isclose(meta["volume_m3"], volumes.sum(), atol=1e-8, rtol=1e-12):
        raise ValueError("exact flat-cell water volume")
    if count:
        top = vertices[:, [4, 6, 5]]
        if not (np.cross(top[:, 1] - top[:, 0], top[:, 2] - top[:, 0])[:, 1] > 0).all():
            raise ValueError("mesh top orientation")
    coordinate_volume = float(((vertices[:, 4, 1] - vertices[:, 0, 1]) * spacing**2).sum())
    difference = coordinate_volume - float(volumes.sum())
    if abs(difference) > 1e-7 + count * spacing**2 * np.spacing(np.max(np.abs(trusted_height))) * 2:
        raise ValueError("water coordinate precision volume discrepancy")
    return {"wet_cells": count, "volume_m3": float(volumes.sum()), "volume_error_m3": difference,
        "coordinate_column_volume_m3": coordinate_volume,
        "zero_coordinate_height_positive_depth_cells": int(((vertices[:, 4, 1] == vertices[:, 0, 1]) & (volumes > 0)).sum()),
        "volume_precision_scope": "support_weights_exact_coordinates_subject_to_float64_stage_rounding",
        "scope": "discrete_column_volume_not_continuous_interpolated_surface"}
