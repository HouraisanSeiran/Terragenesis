"""Full-grid local-inertial surface water with conservative wet/dry face fluxes."""

from dataclasses import dataclass
import math
import time

import numpy as np


SCHEMA = "regional-surface-flat-cell-geometry-v1"
INERTIAL_SCHEMA = "regional-surface-local-inertial-D4-implicit-new-q-drag-v2"


@dataclass(frozen=True)
class SurfaceBudget:
    roughness_s_m_third: float = .035
    max_dt_s: float = 30.
    max_cells: int = 65536
    max_substeps: int = 1000000
    max_face_evaluations: int = 100000000000
    max_bytes: int = 256 * 1024 * 1024
    max_duration_s: float = 259200.
    max_wall_s: float = 7200.
    max_depth_m: float = 20.
    max_snapshots: int = 50
    gravity_m_s2: float = 9.81
    inertial_cfl: float = .45


def validate_budget(budget):
    if not isinstance(budget, SurfaceBudget):
        raise ValueError("SurfaceBudget required")
    integer_fields = ("max_cells", "max_substeps", "max_face_evaluations", "max_bytes", "max_snapshots")
    for name in integer_fields:
        value = getattr(budget, name)
        if type(value) is not int or value <= 0:
            raise ValueError("positive integer budget: " + name)
    for name in set(vars(budget)) - set(integer_fields):
        value = getattr(budget, name)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("finite positive numeric budget: " + name)
    if budget.max_snapshots < 3:
        raise ValueError("snapshot/CFL budget")
    if budget.inertial_cfl > .45:
        raise ValueError("inertial CFL ceiling")


def prepare_surface_geometry(height_m, *, spacing_m, origin_m_xz, source_identity,
                             boundary_kind=None, boundary_crest_m=None):
    """Every cell and each D4 face retained; boundary sides W/E/N/S are explicit."""
    if (not isinstance(height_m, np.ndarray) or height_m.dtype != np.float64 or height_m.ndim != 2
            or not 1 <= height_m.size <= 65536 or not np.isfinite(height_m).all()
            or type(spacing_m) not in (int, float) or not math.isfinite(spacing_m) or spacing_m <= 0):
        raise ValueError("bounded finite original bed and metric spacing required")
    rows, columns = height_m.shape
    origin = np.asarray(origin_m_xz)
    if origin.shape != (2,) or not np.isfinite(origin).all() or not isinstance(source_identity, str) or not source_identity:
        raise ValueError("finite center origin and explicit source identity")
    grid = np.arange(height_m.size, dtype=np.int64).reshape(height_m.shape)
    donor = np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    receiver = np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    exterior = np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    kinds = np.zeros(exterior.size, np.int64) if boundary_kind is None else np.asarray(boundary_kind)
    crests = height_m.ravel()[exterior].copy() if boundary_crest_m is None else np.asarray(boundary_crest_m)
    if kinds.shape != exterior.shape or kinds.dtype != np.int64 or not np.isin(kinds, [0, 1, 2]).all():
        raise ValueError("boundary 0 closed/1 engineering drainage/2 prescribed stage")
    if crests.shape != exterior.shape or crests.dtype != np.float64 or not np.isfinite(crests).all() or (crests < height_m.ravel()[exterior]).any():
        raise ValueError("boundary crest cannot be below original bed")
    return {"arrays": {"H0_m": height_m.copy(), "H2_m": height_m.copy(), "face_left": donor,
        "face_right": receiver, "face_crest_m": np.maximum(height_m.ravel()[donor], height_m.ravel()[receiver]),
        "boundary_cell": exterior, "boundary_kind": kinds.copy(), "boundary_crest_m": crests.copy()},
        "metadata": {"schema": SCHEMA, "spacing_m": float(spacing_m), "origin_m_xz": list(origin_m_xz),
            "source_identity": source_identity, "shape": list(height_m.shape), "area_m2": height_m.size * spacing_m**2,
            "scope": "full_finite_window_30m_flat_cells_not_natural_basin_or_subgrid_channel",
            "boundary_types": ["closed", "engineering_drainage", "prescribed_external_stage"]}}


def validate_surface_geometry(geometry, *, trusted_height, source_identity):
    arrays, meta = geometry["arrays"], geometry["metadata"]
    expected_keys = {"H0_m", "H2_m", "face_left", "face_right", "face_crest_m", "boundary_cell", "boundary_kind", "boundary_crest_m"}
    if set(arrays) != expected_keys:
        raise ValueError("exact geometry array schema")
    if trusted_height.dtype != np.float64 or trusted_height.ndim != 2 or not 1 <= trusted_height.size <= 65536 or not np.isfinite(trusted_height).all():
        raise ValueError("trusted finite bounded original bed")
    if meta["schema"] != SCHEMA or meta["source_identity"] != source_identity:
        raise ValueError("regional geometry source mismatch")
    if not np.array_equal(arrays["H0_m"], trusted_height) or not np.array_equal(arrays["H2_m"], trusted_height):
        raise ValueError("regional original bed identity")
    rows, columns = trusted_height.shape
    grid = np.arange(trusted_height.size, dtype=np.int64).reshape(trusted_height.shape)
    left = np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    if not np.array_equal(arrays["face_left"], left) or not np.array_equal(arrays["face_right"], right):
        raise ValueError("all unique D4 shared faces required")
    if not np.array_equal(arrays["face_crest_m"], np.maximum(trusted_height.ravel()[left], trusted_height.ravel()[right])):
        raise ValueError("regional shared crest forged")
    boundary = np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    shapes = {"H0_m": trusted_height.shape, "H2_m": trusted_height.shape,
        "face_left": left.shape, "face_right": left.shape, "face_crest_m": left.shape,
        "boundary_cell": boundary.shape, "boundary_kind": boundary.shape, "boundary_crest_m": boundary.shape}
    for key, value in arrays.items():
        dtype = np.int64 if key in {"face_left", "face_right", "boundary_cell", "boundary_kind"} else np.float64
        if not isinstance(value, np.ndarray) or value.shape != shapes[key] or value.dtype != dtype:
            raise ValueError("geometry exact shape/dtype: " + key)
    if type(meta["spacing_m"]) not in (int, float) or not math.isfinite(meta["spacing_m"]) or meta["spacing_m"] <= 0:
        raise ValueError("geometry finite metric spacing")
    origin = np.asarray(meta["origin_m_xz"])
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("geometry finite center origin")
    if not np.array_equal(arrays["boundary_cell"], boundary):
        raise ValueError("regional all boundary faces required")
    for value in arrays.values():
        if not isinstance(value, np.ndarray) or not np.isfinite(value).all():
            raise ValueError("regional finite arrays")
    if not np.isin(arrays["boundary_kind"], [0, 1, 2]).all() or (arrays["boundary_crest_m"] < trusted_height.ravel()[boundary]).any():
        raise ValueError("regional boundary certificate")
    if meta["shape"] != list(trusted_height.shape) or meta["area_m2"] != trusted_height.size * meta["spacing_m"]**2:
        raise ValueError("regional full area identity")


def _net_flux(geometry, internal, boundary):
    arrays = geometry["arrays"]
    count = arrays["H0_m"].size
    net = np.bincount(arrays["face_right"], weights=internal, minlength=count)
    net -= np.bincount(arrays["face_left"], weights=internal, minlength=count)
    net -= np.bincount(arrays["boundary_cell"], weights=boundary, minlength=count)
    return net



def inertial_face_flux(stage_left, stage_right, crest, previous_q, dt_s, spacing_m, distance_m, budget):
    """Actual stage gradient; analytic implicit new-discharge Manning drag."""
    flow_depth = np.maximum(np.maximum(stage_left, stage_right) - crest, 0.)
    wet = flow_depth > 0
    discharge_per_width = previous_q / spacing_m
    updated = np.zeros_like(previous_q)
    numerator = discharge_per_width[wet] - budget.gravity_m_s2 * flow_depth[wet] * dt_s * (stage_right[wet] - stage_left[wet]) / distance_m
    friction = budget.gravity_m_s2 * dt_s * budget.roughness_s_m_third**2 / flow_depth[wet]**(7 / 3)
    updated[wet] = spacing_m * 2 * numerator / (1 + np.sqrt(1 + 4 * friction * np.abs(numerator)))
    return updated, flow_depth


def limited_inertial_fluxes(geometry, depth, previous_internal, previous_boundary, tailwater, forcing, dt_s, budget):
    arrays = geometry["arrays"]
    stage = arrays["H2_m"].ravel() + depth
    spacing = geometry["metadata"]["spacing_m"]
    left, right, cells = arrays["face_left"], arrays["face_right"], arrays["boundary_cell"]
    internal, _ = inertial_face_flux(stage[left], stage[right], arrays["face_crest_m"], previous_internal, dt_s, spacing, spacing, budget)
    exterior = np.where(arrays["boundary_kind"] == 1, arrays["boundary_crest_m"], tailwater)
    boundary, _ = inertial_face_flux(stage[cells], exterior, arrays["boundary_crest_m"], previous_boundary, dt_s, spacing, spacing / 2, budget)
    boundary[arrays["boundary_kind"] == 0] = 0.
    outgoing = np.bincount(left, weights=np.maximum(internal, 0), minlength=depth.size)
    outgoing += np.bincount(right, weights=np.maximum(-internal, 0), minlength=depth.size)
    outgoing += np.bincount(cells, weights=np.maximum(boundary, 0), minlength=depth.size)
    available = depth * spacing**2 + dt_s * forcing
    factor = np.ones(depth.size)
    limiting = outgoing * dt_s > available
    factor[limiting] = available[limiting] / (outgoing[limiting] * dt_s)
    factor[limiting] *= 1 - 1e-12
    raw_internal, raw_boundary = internal.copy(), boundary.copy()
    internal *= np.where(internal >= 0, factor[left], factor[right])
    boundary *= np.where(boundary >= 0, factor[cells], 1.)
    removed = float((np.abs(raw_internal - internal).sum() + np.abs(raw_boundary - boundary).sum()) * dt_s)
    raw_volume = float((np.abs(raw_internal).sum() + np.abs(raw_boundary).sum()) * dt_s)
    return internal, boundary, {"limited_donors": int(limiting.sum()), "removed_transfer_m3": removed,
        "raw_transfer_m3": raw_volume, "minimum_factor": float(factor.min()),
        "trigger": "sum_outgoing_dt_exceeds_donor_volume_plus_local_input"}


def advance_inertial_surface(geometry, *, initial_depth_m, forcing_interval_s, intervals,
                            forcing_provider, boundary_stage_provider, source_identity, forcing_identity,
                            budget=SurfaceBudget(), snapshot_interval_s=900., interval_observer=None,
                            momentum_observer=None):
    """Full-grid local inertia, no advective momentum, conservative limited shared Q."""
    validate_budget(budget)
    arrays, meta = geometry["arrays"], geometry["metadata"]
    validate_surface_geometry(geometry, trusted_height=arrays["H0_m"], source_identity=source_identity)
    if type(intervals) is not int or intervals < 1 or type(forcing_interval_s) not in (int, float) or not math.isfinite(forcing_interval_s) or forcing_interval_s <= 0:
        raise ValueError("inertial forcing time dimensions")
    duration = intervals * forcing_interval_s
    if duration > budget.max_duration_s or arrays["H0_m"].size > budget.max_cells:
        raise ValueError("inertial duration/cell budget")
    if type(snapshot_interval_s) not in (int, float) or not math.isfinite(snapshot_interval_s) or snapshot_interval_s <= 0:
        raise ValueError("inertial snapshot interval")
    initial = np.asarray(initial_depth_m)
    if initial.shape != arrays["H0_m"].shape or initial.dtype != np.float64 or not np.isfinite(initial).all() or (initial < 0).any() or (initial > budget.max_depth_m).any():
        raise ValueError("inertial initial water shape/finite/depth")
    snapshot_interval_s = max(snapshot_interval_s, duration / (budget.max_snapshots - 2))
    estimate = (budget.max_snapshots * 2 + 40) * initial.size * 8
    if estimate > budget.max_bytes:
        raise ValueError("inertial memory preflight")
    depth = initial.ravel().copy()
    internal = np.zeros(arrays["face_left"].size)
    boundary = np.zeros(arrays["boundary_cell"].size)
    spacing = meta["spacing_m"]
    area = spacing**2
    time_s = 0.
    next_snapshot = snapshot_interval_s
    snapshots, times = [depth.copy()], [0.]
    initial_volume = float(depth.sum() * area)
    supplied = imported = exported = 0.
    ledgers = [[0., 0., 0., initial_volume, 0.]]
    accepted = evaluations = rejected = 0
    limiter_count = 0
    removed_total = raw_total = 0.
    minimum_factor = 1.
    minimum_dt = math.inf
    maximum_dt = maximum_depth = max_cell_error = absolute_cell_error = 0.
    max_velocity = max_froude = 0.
    high_froude_faces = shallow_faces = 0
    wall = time.monotonic()
    failure = None
    for interval in range(intervals):
        forcing = np.asarray(forcing_provider(interval))
        tailwater = np.asarray(boundary_stage_provider(interval))
        if forcing.shape != initial.shape or forcing.dtype != np.float64 or not np.isfinite(forcing).all() or (forcing < 0).any():
            raise ValueError("full-grid m3/s forcing required")
        if tailwater.shape != boundary.shape or tailwater.dtype != np.float64 or not np.isfinite(tailwater).all():
            raise ValueError("inertial tailwater finite shape")
        forcing = forcing.ravel()
        start_depth = depth.copy()
        start_time = time_s
        transfers = np.zeros_like(internal)
        external_transfers = np.zeros_like(boundary)
        delivered = np.zeros_like(depth)
        before_q, before_boundary = internal.copy(), boundary.copy()
        interval_end = (interval + 1) * forcing_interval_s
        while time_s < interval_end - 1e-9:
            face_count = internal.size + boundary.size
            if accepted >= budget.max_substeps or evaluations + face_count > budget.max_face_evaluations or time.monotonic() - wall >= budget.max_wall_s:
                failure = {"reason": "inertial_resource_budget_refused", "time_s": time_s, "interval": interval}
                break
            stage = arrays["H2_m"].ravel() + depth
            exterior = np.where(arrays["boundary_kind"] == 1, arrays["boundary_crest_m"], tailwater)
            boundary_depth = np.maximum(exterior - arrays["boundary_crest_m"], 0.)
            max_wet_depth = max(float(depth.max()), float(boundary_depth[arrays["boundary_kind"] != 0].max(initial=0)))
            gravity_dt = budget.inertial_cfl * (spacing / 2) / math.sqrt(budget.gravity_m_s2 * max_wet_depth) if max_wet_depth else math.inf
            dt = min(budget.max_dt_s, gravity_dt, interval_end - time_s, next_snapshot - time_s)
            if dt <= 0 or not math.isfinite(dt):
                failure = {"reason": "inertial_timestep_failure", "time_s": time_s}
                break
            next_internal, next_boundary, limiting = limited_inertial_fluxes(geometry, depth, internal, boundary, tailwater, forcing, dt, budget)
            evaluations += face_count
            flow_depth = np.maximum(np.maximum(stage[arrays["face_left"]], stage[arrays["face_right"]]) - arrays["face_crest_m"], 0.)
            evaluable = flow_depth >= .001
            if evaluable.any():
                velocity = np.abs(next_internal[evaluable]) / (spacing * flow_depth[evaluable])
                froude = velocity / np.sqrt(budget.gravity_m_s2 * flow_depth[evaluable])
                max_velocity = max(max_velocity, float(velocity.max()))
                max_froude = max(max_froude, float(froude.max()))
                high_froude_faces += int((froude > 1).sum())
            shallow_faces += int(((flow_depth > 0) & ~evaluable).sum())
            net = _net_flux(geometry, next_internal, next_boundary)
            updated = depth + dt * (forcing + net) / area
            if not np.isfinite(updated).all() or (updated < 0).any() or (updated > budget.max_depth_m).any():
                failure = {"reason": "inertial_depth_or_positivity_refused_no_clip", "time_s": time_s, "attempted_max_depth_m": float(updated.max())}
                rejected += 1
                break
            residual = area * (updated - depth) - dt * (forcing + net)
            if momentum_observer is not None and time_s == start_time:
                momentum_observer({"interval": interval, "time_start_s": time_s, "dt_s": dt,
                    "depth_before_m": depth.copy(), "depth_after_m": updated.copy(), "forcing_m3_s": forcing.copy(),
                    "tailwater_m": tailwater.copy(), "internal_q_before_m3_s": internal.copy(),
                    "boundary_q_before_m3_s": boundary.copy(), "internal_q_after_m3_s": next_internal.copy(),
                    "boundary_q_after_m3_s": next_boundary.copy(), "limiter": limiting.copy()})
            max_cell_error = max(max_cell_error, float(np.abs(residual).max()))
            absolute_cell_error += float(np.abs(residual).sum())
            limiter_count += limiting["limited_donors"]
            removed_total += limiting["removed_transfer_m3"]
            raw_total += limiting["raw_transfer_m3"]
            minimum_factor = min(minimum_factor, limiting["minimum_factor"])
            depth, internal, boundary = updated, next_internal, next_boundary
            transfers += dt * internal
            external_transfers += dt * boundary
            delivered += dt * forcing
            supplied += float(forcing.sum() * dt)
            imported += float(np.maximum(-boundary, 0).sum() * dt)
            exported += float(np.maximum(boundary, 0).sum() * dt)
            time_s += dt
            accepted += 1
            minimum_dt = min(minimum_dt, dt)
            maximum_dt = max(maximum_dt, dt)
            maximum_depth = max(maximum_depth, float(depth.max()))
            if time_s >= next_snapshot - 1e-9:
                snapshots.append(depth.copy()); times.append(time_s)
                volume = float(depth.sum() * area)
                ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
                next_snapshot += snapshot_interval_s
        if interval_observer is not None and time_s > start_time:
            interval_observer({"interval": interval, "time_start_s": start_time, "time_end_s": time_s,
                "depth_before_m": start_depth, "depth_after_m": depth.copy(), "internal_transfer_m3": transfers,
                "boundary_transfer_m3": external_transfers, "forcing_volume_m3": delivered,
                "internal_q_before_m3_s": before_q, "internal_q_after_m3_s": internal.copy(),
                "boundary_q_before_m3_s": before_boundary, "boundary_q_after_m3_s": boundary.copy()})
        if failure is not None:
            break
    if times[-1] != time_s:
        snapshots.append(depth.copy()); times.append(time_s)
        volume = float(depth.sum() * area)
        ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
    return {"metadata": {"schema": INERTIAL_SCHEMA, "source_identity": source_identity, "forcing_identity": forcing_identity,
        "status": "completed" if failure is None else "refused", "failure": failure, "budget": vars(budget),
        "requested_time_s": duration, "committed_time_s": time_s, "substeps": accepted, "face_evaluations": evaluations,
        "wall_s": time.monotonic() - wall, "estimated_peak_bytes": estimate, "initial_volume_m3": initial_volume,
        "supplied_m3": supplied, "boundary_input_m3": imported, "boundary_output_m3": exported,
        "final_volume_m3": float(depth.sum() * area),
        "scope": "full_finite_computational_region_local_inertia_no_advection_not_full_Saint_Venant"},
        "arrays": {"time_s": np.asarray(times), "depth_m": np.asarray(snapshots).reshape(-1, *initial.shape),
            "initial_depth_m": initial.copy(), "ledger": np.asarray(ledgers), "final_internal_q_m3_s": internal,
            "final_boundary_q_m3_s": boundary},
        "diagnostics": {"minimum_dt_s": minimum_dt if accepted else None, "maximum_dt_s": maximum_dt,
            "maximum_depth_m": maximum_depth, "max_cell_residual_m3": max_cell_error,
            "sum_absolute_cell_residual_m3": absolute_cell_error, "limited_donor_count": limiter_count,
            "removed_transfer_m3": removed_total, "raw_transfer_m3": raw_total,
            "removed_fraction": removed_total / raw_total if raw_total else 0., "minimum_limiter_factor": minimum_factor,
            "negative_water_clip_count": 0, "rejected_trials": rejected,
            "max_face_velocity_m_s": max_velocity, "max_face_froude": max_froude,
            "supercritical_face_evaluations": high_froude_faces, "shallow_face_evaluations": shallow_faces,
            "froude_minimum_evaluation_depth_m": .001,
            "physical_limitation": "no_advective_momentum_steep_supercritical_flow_not_full_shallow_water_certification"}}
