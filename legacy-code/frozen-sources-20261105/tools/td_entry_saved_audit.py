"""Raw saved DEM and first-order HLL transaction checks, without execution."""

import math

import numpy as np

from tools.single_domain_shallow_water_audit import audit_momentum


def assert_close(actual, expected, name, atol=1e-8):
    actual = np.asarray(actual)
    expected = np.asarray(expected)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all() or not np.allclose(actual, expected, atol=atol, rtol=1e-10):
        raise ValueError("saved entry mismatch: " + name)


def native_bilinear_source(hierarchy, selected_leaves, points_xz, lake_protection):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    height = np.asarray(arrays["height_m"], dtype=float)
    points = np.asarray(points_xz, dtype=float)
    origin = np.asarray(metadata["origin_m_xz"], dtype=float)
    spacing = float(metadata["spacing_m"])
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError("invalid saved sample coordinates")
    position = (points - origin) / spacing
    if np.any(position < 0) or np.any(position[:, 0] > height.shape[1] - 1) or np.any(position[:, 1] > height.shape[0] - 1):
        raise ValueError("entry background outside original DEM")
    first = np.minimum(np.floor(position).astype(int), np.array(height.shape[::-1]) - 2)
    fraction = position - first
    output = np.zeros(len(points))
    for delta_x, delta_z in ((0, 0), (1, 0), (0, 1), (1, 1)):
        weight = (fraction[:, 0] if delta_x else 1 - fraction[:, 0]) * (fraction[:, 1] if delta_z else 1 - fraction[:, 1])
        active = weight > 0
        columns, rows = first[active, 0] + delta_x, first[active, 1] + delta_z
        owner = arrays["cell_owner"][rows, columns]
        leaves = arrays["contribution_owner"][rows, columns]
        unknown = arrays["node_unknown_contact"]
        if not arrays["valid_mask"][rows, columns].all() or arrays["protected_mask"][rows, columns].any() or arrays["open_boundary_mask"][rows, columns].any():
            raise ValueError("entry background unknown/protected/open source")
        if not np.isin(leaves, selected_leaves).all() or np.any(owner < 0) or np.any(owner >= len(unknown)) or np.any(leaves < 0) or np.any(leaves >= len(unknown)):
            raise ValueError("entry background outside selected source component")
        if unknown[owner].any() or unknown[leaves].any():
            raise ValueError("entry background unknown owner")
        values = height[rows, columns]
        if not np.isfinite(values).all():
            raise ValueError("entry background nonfinite terrain")
        output[active] += weight[active] * values
    nearest = np.floor(position + .5).astype(int)
    native_cells = nearest[:, 1] * height.shape[1] + nearest[:, 0]
    leaf = arrays["contribution_owner"][nearest[:, 1], nearest[:, 0]]
    stages = {item["leaf_id"]: item["stage_m"] for item in lake_protection["stage_by_leaf"]}
    nearest_stage = np.array([stages.get(int(value), -math.inf) for value in leaf])
    wet = np.isin(native_cells, lake_protection["covered_native_cell_ids"]) | (output < nearest_stage)
    return output, wet


def flat_geometry(bed, spacing, boundary_kind, boundary_crest):
    rows, columns = bed.shape
    grid = np.arange(bed.size, dtype=np.int64).reshape(bed.shape)
    return {"H2_m": bed, "face_left": np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()],
            "face_right": np.r_[grid[:, 1:].ravel(), grid[1:].ravel()],
            "boundary_cell": np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]],
            "boundary_kind": np.asarray(boundary_kind), "boundary_crest_m": np.asarray(boundary_crest)}


def audit_interval(packet, geometry, spacing, before_depth, after_depth, before_momentum, after_momentum, forcing_volume):
    cell_count = geometry["H2_m"].size
    area = spacing ** 2
    left, right, boundary = (geometry[key] for key in ("face_left", "face_right", "boundary_cell"))
    internal = np.asarray(packet["internal_transfer_m3"])
    exterior = np.asarray(packet["boundary_transfer_m3"])
    if internal.shape != left.shape or exterior.shape != boundary.shape:
        raise ValueError("saved entry face order/shape mismatch")
    net = np.bincount(right, weights=internal, minlength=cell_count) - np.bincount(left, weights=internal, minlength=cell_count)
    net -= np.bincount(boundary, weights=exterior, minlength=cell_count)
    expected_delta = forcing_volume + net
    delta = (after_depth - before_depth) * area
    assert_close(delta, expected_delta, "per-cell water transaction")
    assert_close(packet["forcing_volume_m3"], forcing_volume, "integrated forcing")
    momentum_internal = np.asarray(packet["internal_momentum_transfer"])
    momentum_boundary = np.asarray(packet["boundary_momentum_transfer"])
    if momentum_internal.shape != (len(left), 2) or momentum_boundary.shape != (len(boundary), 2):
        raise ValueError("saved momentum face order/shape mismatch")
    transported = np.zeros((cell_count, 2))
    for component in range(2):
        transported[:, component] = np.bincount(right, weights=momentum_internal[:, component], minlength=cell_count)
        transported[:, component] -= np.bincount(left, weights=momentum_internal[:, component], minlength=cell_count)
        transported[:, component] -= np.bincount(boundary, weights=momentum_boundary[:, component], minlength=cell_count)
    impulse = np.asarray(packet["bed_momentum_change"]) + np.asarray(packet["manning_momentum_change"])
    assert_close((after_momentum - before_momentum) * area, transported + impulse * area, "per-cell momentum transaction")
    assert_close(packet["depth_before_m"], before_depth, "interval initial water")
    assert_close(packet["depth_after_m"], after_depth, "interval final water")
    assert_close(packet["momentum_before"], before_momentum, "interval initial momentum")
    assert_close(packet["momentum_after"], after_momentum, "interval final momentum")
    return {"maximum_cell_mass_residual_m3": float(np.abs(delta - expected_delta).max(initial=0)),
            "maximum_cell_momentum_residual": float(np.abs((after_momentum - before_momentum) * area - transported - impulse * area).max(initial=0)),
            "net_external_in_m3": float(-exterior.sum())}


def audit_first_rk(packet, dt_s, geometry, spacing, budget, forcing_m3_s, tailwater_m):
    return audit_momentum(packet, {"dt_s": float(dt_s), "hydraulic_model": "single-domain-hydrostatic-HLL-SSPRK2-v1"},
                          geometry, spacing, budget, forcing_m3_s, tailwater_m)


def compare_saved_levels(coarse, fine, coarse_internal, fine_internal, spacing, coarse_substeps, fine_substeps):
    assert_close(coarse["time_s"], fine["time_s"], "time comparison endpoints", atol=1e-12)
    difference = np.abs(coarse["depth_m"] - fine["depth_m"])
    coarse_volume = coarse["depth_m"].sum(axis=(1, 2)) * spacing ** 2
    fine_volume = fine["depth_m"].sum(axis=(1, 2)) * spacing ** 2
    volume_relative = np.abs(coarse_volume - fine_volume) / np.maximum(np.abs(fine_volume), 1e-12)
    coarse_flux = np.asarray(coarse_internal).sum(axis=0)
    fine_flux = np.asarray(fine_internal).sum(axis=0)
    flux_l1 = float(np.abs(coarse_flux - fine_flux).sum() / max(float(np.abs(fine_flux).sum()), 1e-12))
    maximum_depth = float(difference.max(initial=0))
    maximum_volume = float(volume_relative.max(initial=0))
    actual_steps = fine_substeps > coarse_substeps
    return {"maximum_saved_depth_difference_m": maximum_depth,
            "maximum_relative_saved_volume_difference": maximum_volume,
            "cumulative_internal_net_transfer_relative_l1": flux_l1,
            "coarse_substeps": coarse_substeps, "fine_substeps": fine_substeps,
            "actual_temporal_resolution_changed": actual_steps,
            "passed": actual_steps and maximum_depth <= .001 and maximum_volume <= .01 and flux_l1 <= .01,
            "gross_directional_time_convergence_verified": False}
