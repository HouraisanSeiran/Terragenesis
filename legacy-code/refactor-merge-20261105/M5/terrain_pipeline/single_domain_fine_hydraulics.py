"""Fine same-bed runoff and existing D4 local-inertial execution adapter."""

from dataclasses import asdict
import math
import time

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget, prepare_surface_geometry, advance_inertial_surface, validate_budget
from terrain_pipeline.single_domain_fine_geometry import (
    SUBGRID_MODEL, prepare_subgrid_support, storage_stages, segmented_flux,
)

LIMITATIONS = [
    "D4 local inertia with Manning drag omits advective momentum; not full Saint-Venant certification.",
    "Each FV bed is the area mean of the same continuous triangle fan; subcell wetted storage requires separate geometric reconstruction and validation.",
    "Conceptual terrestrial soil rain infiltration applies to every cell; surface water re-infiltration and material permeability are not modelled.",
    "Fine terrain is interpolation and explicitly derived channels, not new Terrain Diffusion source information.",
    "Prescribed stage and drainage faces are engineering boundaries, not verified natural outlets.",
    "Signed boundary transfers independently verify net exterior exchange; gross import/export snapshot totals have no independent per-substep directional witness.",
]


def _advance_subgrid(geometry, *, initial_depth_m, forcing_interval_s, intervals,
                     forcing_provider, boundary_stage_provider, source_identity, forcing_identity,
                     budget, snapshot_interval_s, interval_observer, momentum_observer):
    """One independently evolved coarse volume per cell; canonical segmented Q."""
    a, meta = geometry["arrays"], geometry["metadata"]
    validate_budget(budget)
    initial = np.asarray(initial_depth_m)
    if (initial.dtype != np.float64 or initial.shape != a["H2_m"].shape or np.any(initial < 0) or
            np.any(initial > budget.max_depth_m) or not np.isfinite(initial).all()):
        raise ValueError("subgrid initial mean depth invalid")
    if initial.size > budget.max_cells or intervals*forcing_interval_s > budget.max_duration_s:
        raise ValueError("subgrid predeclared domain/duration exceeded")
    if snapshot_interval_s != forcing_interval_s or intervals+1 > budget.max_snapshots:
        raise ValueError("subgrid saves exactly one snapshot per forcing interval")
    estimate = sum(value.nbytes for value in a.values())
    estimate += initial.size*8*(2*(intervals+1)+30)
    estimate += (a["face_segment_crest_relative_m"].size+a["boundary_segment_crest_relative_m"].size)*8*(12+8*intervals)
    if estimate > budget.max_bytes:
        raise ValueError("subgrid memory preflight exceeded")
    depth = initial.ravel().copy()
    internal = np.zeros_like(a["face_segment_crest_relative_m"])
    boundary = np.zeros_like(a["boundary_segment_crest_relative_m"])
    left, right, cells = a["face_left"], a["face_right"], a["boundary_cell"]
    area, datum = meta["spacing_m"]**2, meta["hydraulic_datum_m"]
    times, snapshots, stage_snapshots = [0.], [initial.copy()], []
    initial_volume = float(depth.sum()*area)
    supplied = imported = exported = 0.
    ledgers = [[0., 0., 0., initial_volume, 0.]]
    accepted = evaluations = limiter_count = 0
    minimum_dt, maximum_dt, max_froude = math.inf, 0., 0.
    residual_max = residual_sum = removed_total = raw_total = 0.
    minimum_factor = 1.
    started = time.monotonic()
    current_time = 0.
    stage_snapshots.append(storage_stages(depth, a["subcell_bed_relative_m"], a["subcell_prefix_relative_m"]).reshape(initial.shape))
    for interval in range(intervals):
        forcing = np.asarray(forcing_provider(interval)).ravel()
        tailwater = np.asarray(boundary_stage_provider(interval))
        if (forcing.dtype != np.float64 or forcing.shape != depth.shape or not np.isfinite(forcing).all() or np.any(forcing < 0) or
                tailwater.dtype != np.float64 or tailwater.shape != (len(cells),) or not np.isfinite(tailwater).all()):
            raise ValueError("subgrid finite complete forcing/tailwater required")
        before_depth, before_i, before_b = depth.copy(), internal.copy(), boundary.copy()
        transfer_i, transfer_b, delivered = np.zeros_like(internal), np.zeros_like(boundary), np.zeros_like(depth)
        start_time, end_time = interval*forcing_interval_s, (interval+1)*forcing_interval_s
        first = True
        while current_time < end_time:
            if (accepted >= budget.max_substeps or evaluations+internal.size+boundary.size > budget.max_face_evaluations or
                    time.monotonic()-started >= budget.max_wall_s):
                raise RuntimeError("subgrid execution resource budget exceeded")
            stage = storage_stages(depth, a["subcell_bed_relative_m"], a["subcell_prefix_relative_m"])
            flow_depth = np.maximum(np.maximum(stage[left], stage[right])[:, None]-a["face_segment_crest_relative_m"], 0.)
            exterior = np.broadcast_to((tailwater-datum)[:, None], boundary.shape).copy()
            exterior[a["boundary_kind"] == 1] = a["boundary_segment_crest_relative_m"][a["boundary_kind"] == 1]
            boundary_depth = np.maximum(np.maximum(stage[cells,None],exterior)-a["boundary_segment_crest_relative_m"], 0.)
            deepest = max(float(flow_depth.max(initial=0)), float(boundary_depth[a["boundary_kind"] != 0].max(initial=0)))
            cfl = budget.inertial_cfl*meta["spacing_m"]/2/math.sqrt(budget.gravity_m_s2*deepest) if deepest else math.inf
            dt = min(budget.max_dt_s, cfl, end_time-current_time)
            next_i, next_b, limiter = segmented_flux(geometry, depth, internal, boundary, tailwater, forcing, dt, budget)
            qi, qb = next_i.sum(axis=1), next_b.sum(axis=1)
            net = np.bincount(right, weights=qi, minlength=len(depth))-np.bincount(left, weights=qi, minlength=len(depth))
            net -= np.bincount(cells, weights=qb, minlength=len(depth))
            updated = depth+dt*(forcing+net)/area
            if not np.isfinite(updated).all() or np.any(updated < 0) or np.any(updated > budget.max_depth_m):
                raise RuntimeError("subgrid positivity/depth refusal; no clipping")
            residual = area*(updated-depth)-dt*(forcing+net)
            residual_max = max(residual_max, float(abs(residual).max(initial=0)))
            residual_sum += float(abs(residual).sum())
            if first:
                momentum_observer(dict(interval=interval,time_start_s=current_time,dt_s=dt,
                    depth_before_m=depth.copy(),depth_after_m=updated.copy(),forcing_m3_s=forcing.copy(),tailwater_m=tailwater.copy(),
                    internal_q_before_m3_s=internal.sum(axis=1),internal_q_after_m3_s=qi,
                    boundary_q_before_m3_s=boundary.sum(axis=1),boundary_q_after_m3_s=qb,
                    internal_segment_q_before_m3_s=internal.copy(),internal_segment_q_after_m3_s=next_i.copy(),
                    boundary_segment_q_before_m3_s=boundary.copy(),boundary_segment_q_after_m3_s=next_b.copy(),limiter=limiter))
                first = False
            wet = flow_depth >= .001
            if wet.any():
                froude = abs(next_i[wet])/flow_depth[wet]/np.sqrt(budget.gravity_m_s2*flow_depth[wet])
                max_froude = max(max_froude,float(froude.max(initial=0)))
            limiter_count += limiter["limited_donors"]
            minimum_factor = min(minimum_factor, limiter["minimum_scale"])
            removed_total += limiter["limited_volume_m3"]
            raw_total += dt*(abs(next_i).sum()+abs(next_b).sum())
            transfer_i += dt*next_i
            transfer_b += dt*next_b
            delivered += dt*forcing
            supplied += float(dt*forcing.sum())
            imported += float(dt*np.maximum(-next_b,0).sum())
            exported += float(dt*np.maximum(next_b,0).sum())
            depth, internal, boundary = updated, next_i, next_b
            current_time = end_time if dt == end_time-current_time else current_time+dt
            accepted += 1
            evaluations += internal.size+boundary.size
            minimum_dt, maximum_dt = min(minimum_dt,dt),max(maximum_dt,dt)
        interval_observer(dict(interval=interval,time_start_s=start_time,time_end_s=end_time,
            depth_before_m=before_depth,depth_after_m=depth.copy(),internal_transfer_m3=transfer_i.sum(axis=1),
            boundary_transfer_m3=transfer_b.sum(axis=1),forcing_volume_m3=delivered,
            internal_segment_transfer_m3=transfer_i,boundary_segment_transfer_m3=transfer_b,
            internal_q_before_m3_s=before_i.sum(axis=1),internal_q_after_m3_s=internal.sum(axis=1),
            boundary_q_before_m3_s=before_b.sum(axis=1),boundary_q_after_m3_s=boundary.sum(axis=1),
            internal_segment_q_before_m3_s=before_i,internal_segment_q_after_m3_s=internal.copy(),
            boundary_segment_q_before_m3_s=before_b,boundary_segment_q_after_m3_s=boundary.copy()))
        volume = float(depth.sum()*area)
        ledgers.append([supplied,imported,exported,volume,volume-initial_volume-supplied-imported+exported])
        times.append(end_time)
        snapshots.append(depth.reshape(initial.shape).copy())
        stage_snapshots.append(storage_stages(depth,a["subcell_bed_relative_m"],a["subcell_prefix_relative_m"]).reshape(initial.shape))
    return dict(arrays=dict(time_s=np.asarray(times),depth_m=np.asarray(snapshots),initial_depth_m=initial.copy(),ledger=np.asarray(ledgers),
                           stage_relative_m=np.asarray(stage_snapshots),final_internal_q_m3_s=internal.sum(axis=1),final_boundary_q_m3_s=boundary.sum(axis=1),
                           final_internal_segment_q_m3_s=internal,final_boundary_segment_q_m3_s=boundary),
                metadata=dict(schema=SUBGRID_MODEL,source_identity=source_identity,forcing_identity=forcing_identity,status="completed",failure=None,
                    budget=vars(budget),requested_time_s=intervals*forcing_interval_s,committed_time_s=current_time,substeps=accepted,face_evaluations=evaluations,
                    estimated_peak_bytes=estimate,
                    wall_s=time.monotonic()-started,initial_volume_m3=initial_volume,supplied_m3=supplied,boundary_input_m3=imported,boundary_output_m3=exported,
                    final_volume_m3=float(depth.sum()*area),hydraulic_model=SUBGRID_MODEL,scope="coarse independent volume/stage; canonical subcell storage and segmented face Q; no advection"),
                diagnostics=dict(minimum_dt_s=minimum_dt,maximum_dt_s=maximum_dt,max_face_froude=max_froude,limited_donor_count=limiter_count,
                    minimum_limiter_factor=minimum_factor,removed_transfer_m3=removed_total,raw_transfer_m3=raw_total,
                    max_cell_residual_m3=residual_max,sum_absolute_cell_residual_m3=residual_sum,negative_water_clip_count=0,
                    physical_limitation="no advective momentum; supercritical front convergence not guaranteed"))


def _bundle(arrays, metadata):
    return dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))


def run_fine_hydraulics(bed, *, rain_mm_h, boundary_stage_m, forcing_interval_s,
                        boundary_kind, boundary_crest_m=None, initial_depth_m=None,
                        runoff_parameters=RunoffParameters(), budget=None, backend="accelerated"):
    """Execute existing kernels on a newly bound bed; retain complete interval evidence."""
    arrays, metadata = bed["arrays"], bed["metadata"]
    if bed.get("identity_sha256") != identity(arrays, metadata):
        raise ValueError("fine bed content identity mismatch")
    height = arrays["bed_center_m"]
    spacing = metadata["spacing_m"]
    origin = [value + spacing/2 for value in metadata["origin_m_xz"]]
    if (not isinstance(rain_mm_h, np.ndarray) or rain_mm_h.dtype != np.float64
            or rain_mm_h.ndim != 3 or rain_mm_h.shape[1:] != height.shape
            or not np.isfinite(rain_mm_h).all() or np.any(rain_mm_h < 0)):
        raise ValueError("fine complete finite rainfall grid required")
    steps = len(rain_mm_h)
    if not 1 <= steps <= 48 or steps*height.size > 1000000:
        raise ValueError("fine runoff saved-state resource budget exceeded")
    if type(forcing_interval_s) not in (int, float) or not math.isfinite(forcing_interval_s) or not 0 < forcing_interval_s <= 3600:
        raise ValueError("fine physical forcing interval required")
    if budget is None:
        budget = SurfaceBudget(max_dt_s=.1, max_cells=65536, max_snapshots=steps+2,
                               max_wall_s=1800., max_duration_s=600., max_depth_m=10.)
    if budget.max_snapshots < steps+2 or budget.max_wall_s > 1800 or budget.max_bytes > 268435456:
        raise ValueError("fine snapshot/wall/artifact predeclaration rejected")
    geometry = prepare_surface_geometry(height, spacing_m=spacing, origin_m_xz=origin,
                                        source_identity=bed["identity_sha256"], boundary_kind=boundary_kind,
                                        boundary_crest_m=boundary_crest_m)
    geometry["metadata"]["scope"] = "explicit_fine_same_area_mean_bed_D4_FV_not_subcell_triangle_hydraulics"
    subgrid = backend in ("subgrid", "shallow_water_subgrid", "shallow_water_subgrid_manning", "shallow_water_subgrid_manning_accelerated")
    if subgrid and "canonical_bed_center_m" not in arrays:
        raise ValueError("explicit subgrid backend requires canonical hydraulic support")
    if subgrid:
        support, datum = prepare_subgrid_support(bed)
        if boundary_crest_m is not None:
            support["boundary_segment_crest_relative_m"] = np.maximum(
                support["boundary_segment_crest_relative_m"], np.asarray(boundary_crest_m)[:, None]-datum)
        geometry["arrays"].update(support)
        geometry["metadata"].update(hydraulic_model=SUBGRID_MODEL, hydraulic_datum_m=datum,
                                    subcell_spacing_m=1., coarse_independent_unknowns=height.size,
                                    explicit_boundary_crest=boundary_crest_m is not None)
    geometry = _bundle(geometry["arrays"], geometry["metadata"])
    boundary_stage_m = np.asarray(boundary_stage_m)
    boundaries = len(geometry["arrays"]["boundary_cell"])
    if boundary_stage_m.shape != (steps, boundaries) or boundary_stage_m.dtype != np.float64 or not np.isfinite(boundary_stage_m).all():
        raise ValueError("fine explicit complete engineering tailwater required")
    initial = np.zeros(height.shape) if initial_depth_m is None else initial_depth_m
    runoff = simulate_rainfall_runoff(rain_mm_h.reshape(steps, height.size),
                                      np.full(height.size, spacing**2), dt_s=forcing_interval_s,
                                      source_id=bed["identity_sha256"], parameters=runoff_parameters)
    runoff_arrays = {key:value for key, value in runoff.items() if key != "metadata"}
    forcing_metadata = dict(schema="single-domain-fine-forcing-v1", bed_identity=bed["identity_sha256"],
                            grid_shape=list(height.shape), spacing_m=spacing, origin_m_xz=origin,
                            runoff_metadata=runoff["metadata"], steps=steps, dt_s=forcing_interval_s,
                            rain_semantics="all-cell conceptual terrestrial soil infiltration; release enters surface exactly once",
                            q_semantics="local_q timestep average; face_q saved endpoint instantaneous discharge",
                            hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    runoff_arrays["boundary_stage_m"] = boundary_stage_m.copy()
    forcing = _bundle(runoff_arrays, forcing_metadata)
    intervals, momenta = [], []

    def observe(packet, target, schema):
        info = {key:value for key, value in packet.items() if not isinstance(value, np.ndarray)}
        fields = {key:value for key, value in packet.items() if isinstance(value, np.ndarray)}
        info.update(schema=schema, bed_identity=bed["identity_sha256"], geometry_identity=geometry["identity_sha256"],
                    forcing_identity=forcing["identity_sha256"], hydraulic_ready=False,
                    natural_outlet_verified=False, publishable=False,
                    hydraulic_model=geometry["metadata"].get("hydraulic_model", "flat-cell-local-inertia"))
        target.append(_bundle(fields, info))

    if backend in ("shallow_water_subgrid_manning","shallow_water_subgrid_manning_accelerated"):
        if backend == "shallow_water_subgrid_manning_accelerated":
            from terrain_pipeline.single_domain_shallow_water_accelerated_v7 import advance_shallow_water
        else:
            from terrain_pipeline.single_domain_shallow_water_v7 import advance_shallow_water
        from terrain_pipeline.single_domain_shallow_water_support_v7 import MODEL
        geometry["metadata"]["hydraulic_model"] = MODEL
        geometry["metadata"]["scope"] = "independent_subgrid_storage_segmented_HLL_canonical_Manning"
        geometry = _bundle(geometry["arrays"],geometry["metadata"])
        advance = advance_shallow_water
    elif backend == "shallow_water_subgrid":
        from terrain_pipeline.single_domain_shallow_water_v3 import advance_shallow_water
        from terrain_pipeline.single_domain_shallow_water_support_v3 import MODEL
        geometry["metadata"]["hydraulic_model"] = MODEL
        geometry["metadata"]["scope"] = "independent_subgrid_storage_segmented_advective_HLL"
        geometry = _bundle(geometry["arrays"],geometry["metadata"])
        advance = advance_shallow_water
    elif backend == "shallow_water":
        from terrain_pipeline.single_domain_shallow_water import advance_shallow_water
        from terrain_pipeline.single_domain_shallow_water_support import MODEL
        geometry["metadata"]["hydraulic_model"] = MODEL
        geometry = _bundle(geometry["arrays"],geometry["metadata"])
        advance = advance_shallow_water
    elif subgrid:
        advance = _advance_subgrid
    elif backend == "accelerated":
        from terrain_pipeline.regional_surface_hydraulics_accelerated import advance_accelerated_surface
        advance = advance_accelerated_surface
    elif backend == "reference":
        advance = advance_inertial_surface
    else:
        raise ValueError("unknown fine execution backend")
    evolved = advance(geometry, initial_depth_m=initial, forcing_interval_s=forcing_interval_s,
                      intervals=steps, forcing_provider=lambda index: runoff["local_q_m3_s"][index].reshape(height.shape),
                      boundary_stage_provider=lambda index: boundary_stage_m[index],
                      source_identity=bed["identity_sha256"], forcing_identity=forcing["identity_sha256"],
                      budget=budget, snapshot_interval_s=forcing_interval_s,
                      interval_observer=lambda packet: observe(packet, intervals, "single-domain-fine-interval-v1"),
                      momentum_observer=lambda packet: observe(packet, momenta, "single-domain-fine-momentum-v1"))
    if evolved["metadata"]["status"] != "completed" or len(intervals) != steps or len(momenta) != steps:
        raise RuntimeError("fine hydraulic resource/positivity refusal: " + str(evolved["metadata"]["failure"]))
    state_metadata = dict(schema="single-domain-fine-states-v1", bed_identity=bed["identity_sha256"],
                          geometry_identity=geometry["identity_sha256"], forcing_identity=forcing["identity_sha256"],
                          solver_metadata=evolved["metadata"], diagnostics=evolved["diagnostics"],
                          interval_count=steps, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                          limitations=list(LIMITATIONS), hydraulic_model=evolved["metadata"].get("hydraulic_model","flat-cell-local-inertia"))
    states = _bundle(evolved["arrays"], state_metadata)
    return dict(bed=bed, geometry=geometry, forcing=forcing, states=states, intervals=intervals,
                momenta=momenta, runoff_parameters=asdict(runoff_parameters), limitations=list(LIMITATIONS))
