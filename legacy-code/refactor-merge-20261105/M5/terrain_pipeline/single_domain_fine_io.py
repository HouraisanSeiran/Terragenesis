"""Strict fine-run evidence IO, with no execution adapter or accelerated imports."""

import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, save_bundle, file_sha256, publish_bytes
from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as ARRAY_KEYS
from terrain_pipeline.runoff import validate_rainfall_runoff_result as validate_rainfall_runoff_result
from terrain_pipeline.regional_surface_hydraulics import validate_surface_geometry, SurfaceBudget, validate_budget, limited_inertial_fluxes, _net_flux
from terrain_pipeline.td_native_weather_storage_io import _json, _layout

MAX_BYTES = 268435456
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable")
SUBGRID_MODEL = "canonical-subcell-storage-segmented-face-local-inertia-v1"
SHALLOW_MODEL = "single-domain-hydrostatic-HLL-SSPRK2-v1"
SHALLOW_MODEL_V2 = "single-domain-MUSCL-hydrostatic-HLL-SSPRK2-v2"
SHALLOW_SUBGRID_MODEL = "single-domain-subgrid-storage-segmented-HLL-SSPRK2-v3"
SHALLOW_SUBGRID_MANNING_MODEL = "single-domain-subgrid-storage-segmented-HLL-canonical-Manning-SSPRK2-v7"
SHALLOW_SUBGRID_MODELS = (SHALLOW_SUBGRID_MODEL,SHALLOW_SUBGRID_MANNING_MODEL)
SHALLOW_MODELS = (SHALLOW_MODEL,SHALLOW_MODEL_V2,*SHALLOW_SUBGRID_MODELS)
INTERVAL_ARRAYS = ("depth_before_m", "depth_after_m", "internal_transfer_m3", "boundary_transfer_m3",
                   "forcing_volume_m3", "internal_q_before_m3_s", "internal_q_after_m3_s",
                   "boundary_q_before_m3_s", "boundary_q_after_m3_s")


def _check(result, schema):
    if (result.get("identity_sha256") != identity(result["arrays"], result["metadata"])
            or result["metadata"].get("schema") != schema
            or any(result["metadata"].get(name) is not False for name in FLAGS)
            or any(not np.isfinite(value).all() for value in result["arrays"].values())):
        raise ValueError("fine saved schema/identity/flags/finite mismatch")
    return result["arrays"], result["metadata"]


def _near(actual, expected, label):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all() or np.any(abs(actual-expected) > 1e-8+2e-11*abs(expected)):
        raise ValueError("fine independent account mismatch: " + label)


def canonical_bed_fields(bed):
    """Evaluate declared source/cut/protection math without geometry construction."""
    arrays,meta = bed["arrays"],bed["metadata"]
    height,mask = arrays["native_height_m"],arrays["native_protected_mask"]
    x0,x1,z0,z1 = meta["native_window"]
    x,z = np.meshgrid(x0+(np.arange((x1-x0)*30)+.5)/30.,z0+(np.arange((z1-z0)*30)+.5)/30.)
    ix,iz = np.floor(x).astype(int),np.floor(z).astype(int)
    jx,jz = np.minimum(ix+1,height.shape[1]-1),np.minimum(iz+1,height.shape[0]-1)
    tx,tz = x-ix,z-iz
    native = ((height[iz,ix]*(1-tx)+height[iz,jx]*tx)*(1-tz)+(height[jz,ix]*(1-tx)+height[jz,jx]*tx)*tz)
    cut = np.zeros(native.shape)
    for first,second in arrays["selected_edge_cell_ids"]:
        if arrays["native_receiver"][first] != second:
            raise ValueError("fine canonical cut edge source mismatch")
        ax,az = first%height.shape[1],first//height.shape[1]
        bx,bz = second%height.shape[1],second//height.shape[1]
        length = (bx-ax)**2+(bz-az)**2
        if length != 1:
            raise ValueError("fine canonical cut requires D4 receiver segment")
        fraction = np.clip(((x-ax)*(bx-ax)+(z-az)*(bz-az))/length,0,1)
        distance = 30*np.hypot(x-ax-fraction*(bx-ax),z-az-fraction*(bz-az))
        cut = np.maximum(cut,np.where(distance<4,.5*(1+np.cos(np.pi*np.minimum(distance/4,1))),0))
    protected = mask[iz,ix] | mask[iz,jx] | mask[jz,ix] | mask[jz,jx]
    cut[protected] = 0
    return native-cut,protected


def validate_canonical_bed(bed):
    arrays,meta = bed["arrays"],bed["metadata"]
    if meta.get("scope") == "synthetic_fixture" and "canonical_bed_center_m" not in arrays:
        return True
    if "canonical_bed_center_m" not in arrays:
        raise ValueError("fine saved canonical bed witness required")
    # Source recipe evaluation belongs to the independent audit, not cold IO.
    canonical = arrays["canonical_bed_center_m"]
    if canonical.dtype != np.float64 or not np.isfinite(canonical).all():
        raise ValueError("fine saved canonical bed finite/type mismatch")
    factor = int(meta["spacing_m"])
    rows,columns = arrays["bed_center_m"].shape
    if canonical.shape != (rows*factor,columns*factor):
        raise ValueError("fine canonical complete footprint mismatch")
    _near(arrays["bed_center_m"],canonical.reshape(rows,factor,columns,factor).mean(axis=(1,3)),"canonical area restriction")
    points = arrays["bed_vertices_xyz_m"][arrays["bed_triangles"]]
    normals = np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0])
    if np.any(normals[:,1]<=0) or len(points)!=4*rows*columns:
        raise ValueError("fine triangle bed winding/coverage mismatch")
    areas = normals[:,1]/2
    integrated = (areas*points[:,:,1].mean(axis=1)).reshape(rows,columns,4).sum(axis=2)/meta["spacing_m"]**2
    _near(integrated,arrays["bed_center_m"],"actual triangle area-mean bed")
    return True


def validate_initial_contract(states,*,bed,lake_stage_m,initial_kind):
    canonical = bed["arrays"]["canonical_bed_center_m"]
    factor = int(bed["metadata"]["spacing_m"])
    rows,columns = bed["arrays"]["bed_center_m"].shape
    expected = np.zeros((rows,columns)) if initial_kind=="rain" else np.maximum(lake_stage_m-canonical,0).reshape(rows,factor,columns,factor).mean(axis=(1,3))
    _near(states["arrays"]["initial_depth_m"],expected,"canonical initial water contract")
    return True


def _segment_momentum_witness(geometry,depth,internal_before,boundary_before,tailwater,forcing,dt,budget,stage):
    """Independent saved-step equation certificate; no solver helper or advancement."""
    arrays,meta = geometry["arrays"],geometry["metadata"]
    left,right,cells = arrays["face_left"],arrays["face_right"],arrays["boundary_cell"]
    exterior = np.broadcast_to((tailwater-meta["hydraulic_datum_m"])[:,None],boundary_before.shape).copy()
    drainage = arrays["boundary_kind"]==1
    exterior[drainage] = arrays["boundary_segment_crest_relative_m"][drainage]
    answers = []
    for first,second,crest,previous,distance in (
            (stage[left,None],stage[right,None],arrays["face_segment_crest_relative_m"],internal_before,meta["spacing_m"]),
            (stage[cells,None],exterior,arrays["boundary_segment_crest_relative_m"],boundary_before,meta["spacing_m"]/2)):
        wet_depth = np.maximum(np.maximum(first,second)-crest,0)
        wet = wet_depth>0
        rhs = previous-budget.gravity_m_s2*wet_depth*dt*(second-first)/distance
        drag = np.zeros_like(wet_depth)
        drag[wet] = budget.gravity_m_s2*dt*budget.roughness_s_m_third**2/wet_depth[wet]**(7/3)
        answer = np.zeros_like(previous)
        answer[wet] = 2*rhs[wet]/(1+np.sqrt(1+4*drag[wet]*abs(rhs[wet])))
        answers.append(answer)
    internal,boundary = answers
    boundary[arrays["boundary_kind"]==0] = 0
    outgoing = np.bincount(left,weights=np.maximum(internal,0).sum(axis=1),minlength=len(depth))
    outgoing += np.bincount(right,weights=np.maximum(-internal,0).sum(axis=1),minlength=len(depth))
    outgoing += np.bincount(cells,weights=np.maximum(boundary,0).sum(axis=1),minlength=len(depth))
    available = depth*meta["spacing_m"]**2+dt*forcing
    limited = outgoing*dt>available
    factors = np.ones(len(depth))
    factors[limited] = available[limited]/(outgoing[limited]*dt)*(1-1e-12)
    raw_internal,raw_boundary = internal.copy(),boundary.copy()
    internal *= np.where(internal>=0,factors[left,None],factors[right,None])
    boundary *= np.where(boundary>=0,factors[cells,None],1.)
    limiter = dict(limited_donors=int(limited.sum()),minimum_scale=float(factors.min(initial=1)),
                   limited_volume_m3=float(dt*(abs(raw_internal-internal).sum()+abs(raw_boundary-boundary).sum())))
    return internal,boundary,limiter


def validate_fine_geometry(geometry, *, bed):
    if bed["identity_sha256"] != identity(bed["arrays"],bed["metadata"]):
        raise ValueError("fine original bed content identity mismatch")
    if geometry["identity_sha256"] != identity(geometry["arrays"], geometry["metadata"]):
        raise ValueError("fine hydraulic geometry identity mismatch")
    validate_canonical_bed(bed)
    height = bed["arrays"]["bed_center_m"]
    subgrid = geometry["metadata"].get("hydraulic_model") in (SUBGRID_MODEL,*SHALLOW_SUBGRID_MODELS)
    shallow = geometry["metadata"].get("hydraulic_model") == SHALLOW_MODEL
    support_names = {"subcell_bed_relative_m","subcell_prefix_relative_m","face_segment_crest_relative_m","boundary_segment_crest_relative_m"}
    base_arrays = {name:value for name,value in geometry["arrays"].items() if name not in support_names}
    validate_surface_geometry(dict(arrays=base_arrays,metadata=geometry["metadata"]), trusted_height=height, source_identity=bed["identity_sha256"])
    spacing = bed["metadata"]["spacing_m"]
    center = [value+spacing/2 for value in bed["metadata"]["origin_m_xz"]]
    if geometry["metadata"]["spacing_m"] != spacing or geometry["metadata"]["origin_m_xz"] != center:
        raise ValueError("fine hydraulic cell-center coordinate binding mismatch")
    if subgrid:
        canonical = bed["arrays"]["canonical_bed_center_m"]
        rows,columns = height.shape
        factor = int(spacing)
        datum = float(canonical.min())
        relative = canonical-datum
        subbed = np.sort(relative.reshape(rows,factor,columns,factor).transpose(0,2,1,3).reshape(rows*columns,factor**2),axis=1)
        face_x = np.maximum(relative[:,:-1],relative[:,1:])[:,factor-1::factor].reshape(rows,factor,columns-1).transpose(0,2,1).reshape(-1,factor)
        face_z = np.maximum(relative[:-1],relative[1:])[factor-1::factor].reshape(rows-1,columns,factor).reshape(-1,factor)
        boundary = np.concatenate((relative[:,0].reshape(rows,factor),relative[:,-1].reshape(rows,factor),
                                   relative[0,:].reshape(columns,factor),relative[-1,:].reshape(columns,factor)))
        expected = dict(subcell_bed_relative_m=subbed,subcell_prefix_relative_m=np.cumsum(subbed,axis=1),
                        face_segment_crest_relative_m=np.concatenate((face_x,face_z)),boundary_segment_crest_relative_m=boundary)
        if (set(geometry["arrays"])-set(base_arrays) != support_names or geometry["metadata"]["hydraulic_datum_m"] != datum
                or geometry["metadata"]["subcell_spacing_m"] != 1. or geometry["metadata"]["coarse_independent_unknowns"] != height.size):
            raise ValueError("subgrid canonical support metadata mismatch")
        for name,values in expected.items():
            _near(geometry["arrays"][name],values,"independent canonical segmented support "+name)
    elif set(geometry["arrays"]) != set(base_arrays):
        raise ValueError("flat hydraulic model cannot carry subgrid support")
    return True


def validate_fine_forcing(forcing, *, bed):
    arrays, metadata = _check(forcing, "single-domain-fine-forcing-v1")
    shape = bed["arrays"]["bed_center_m"].shape
    steps = metadata["steps"]
    if (type(steps) is not int or not 1 <= steps <= 48 or steps*math.prod(shape) > 1000000
            or metadata["bed_identity"] != bed["identity_sha256"] or metadata["grid_shape"] != list(shape)
            or metadata["spacing_m"] != bed["metadata"]["spacing_m"]
            or metadata["origin_m_xz"] != [value+metadata["spacing_m"]/2 for value in bed["metadata"]["origin_m_xz"]]
            or set(arrays) != set(ARRAY_KEYS) | {"boundary_stage_m"}):
        raise ValueError("fine forcing exact source/grid/fields mismatch")
    runoff = {key:arrays[key] for key in ARRAY_KEYS}
    runoff["metadata"] = metadata["runoff_metadata"]
    validate_rainfall_runoff_result(runoff)
    if runoff["metadata"]["source_id"] != bed["identity_sha256"] or runoff["metadata"]["dt_s"] != metadata["dt_s"]:
        raise ValueError("fine forcing runoff source/time mismatch")
    if not np.array_equal(arrays["area_m2"], np.full(math.prod(shape), metadata["spacing_m"]**2)):
        raise ValueError("fine forcing exact support area mismatch")
    boundaries = 2*sum(shape)
    if arrays["boundary_stage_m"].dtype != np.float64 or arrays["boundary_stage_m"].shape != (steps, boundaries):
        raise ValueError("fine forcing complete tailwater coverage mismatch")
    return True


def validate_fine_states(states, *, bed, geometry, forcing):
    arrays, metadata = _check(states, "single-domain-fine-states-v1")
    validate_fine_geometry(geometry, bed=bed)
    validate_fine_forcing(forcing, bed=bed)
    steps, dt = forcing["metadata"]["steps"], forcing["metadata"]["dt_s"]
    shape = bed["arrays"]["bed_center_m"].shape
    solver = metadata["solver_metadata"]
    subgrid = geometry["metadata"].get("hydraulic_model") == SUBGRID_MODEL
    model = geometry["metadata"].get("hydraulic_model")
    shallow = model in SHALLOW_MODELS
    extra_names = ({"stage_relative_m","final_internal_segment_q_m3_s","final_boundary_segment_q_m3_s"} if subgrid else {"momentum_x_m2_s","momentum_z_m2_s"} if shallow else set())
    if model in SHALLOW_SUBGRID_MODELS:
        extra_names.add("stage_relative_m")
    if (metadata["bed_identity"] != bed["identity_sha256"]
            or metadata["geometry_identity"] != geometry["identity_sha256"]
            or metadata["forcing_identity"] != forcing["identity_sha256"]
            or metadata["interval_count"] != steps or solver["status"] != "completed" or solver["failure"] is not None
            or solver["source_identity"] != bed["identity_sha256"] or solver["forcing_identity"] != forcing["identity_sha256"]
            or abs(solver["committed_time_s"]-steps*dt)>1e-9 or solver["requested_time_s"] != steps*dt
            or set(arrays) != {"time_s", "depth_m", "initial_depth_m", "ledger", "final_internal_q_m3_s", "final_boundary_q_m3_s"}|extra_names):
        raise ValueError("fine complete states binding mismatch")
    if (arrays["depth_m"].shape != (steps+1, *shape) or arrays["time_s"].shape != (steps+1,)
            or np.any(arrays["depth_m"] < 0) or not np.allclose(arrays["time_s"], np.arange(steps+1)*dt,rtol=0,atol=1e-9)
            or not np.array_equal(arrays["initial_depth_m"], arrays["depth_m"][0])):
        raise ValueError("fine complete snapshot time/depth mismatch")
    expected_shapes = dict(time_s=(steps+1,),depth_m=(steps+1,*shape),initial_depth_m=shape,ledger=(steps+1,5),
                           final_internal_q_m3_s=(len(geometry["arrays"]["face_left"]),),
                           final_boundary_q_m3_s=(len(geometry["arrays"]["boundary_cell"]),))
    if shallow and (solver.get("schema") != model or solver.get("hydraulic_model") != model):
        raise ValueError("shallow-water saved solver model mismatch")
    if shallow:
        expected_shapes.update(momentum_x_m2_s=(steps+1,*shape),momentum_z_m2_s=(steps+1,*shape))
        if np.any(arrays["momentum_x_m2_s"][0] != 0) or np.any(arrays["momentum_z_m2_s"][0] != 0):
            raise ValueError("shallow-water initial momentum mismatch")
    if model in SHALLOW_SUBGRID_MODELS:
        expected_shapes["stage_relative_m"] = (steps+1,*shape)
        for stage,depth in zip(arrays["stage_relative_m"],arrays["depth_m"]):
            _near(np.maximum(stage.ravel()[:,None]-geometry["arrays"]["subcell_bed_relative_m"],0).mean(axis=1).reshape(shape),depth,"subgrid shallow V(stage)")
    if subgrid:
        factor = int(geometry["metadata"]["spacing_m"])
        expected_shapes.update(stage_relative_m=(steps+1,*shape),
                               final_internal_segment_q_m3_s=(expected_shapes["final_internal_q_m3_s"][0],factor),
                               final_boundary_segment_q_m3_s=(expected_shapes["final_boundary_q_m3_s"][0],factor))
        if solver.get("schema") != SUBGRID_MODEL or solver.get("hydraulic_model") != SUBGRID_MODEL:
            raise ValueError("subgrid saved solver physical model mismatch")
        for stage,depth in zip(arrays["stage_relative_m"],arrays["depth_m"]):
            implied = np.maximum(stage.ravel()[:,None]-geometry["arrays"]["subcell_bed_relative_m"],0).mean(axis=1).reshape(shape)
            _near(implied,depth,"subgrid V(stage) exact mean depth")
        for kind in ("internal","boundary"):
            _near(arrays[f"final_{kind}_segment_q_m3_s"].sum(axis=1),arrays[f"final_{kind}_q_m3_s"],"subgrid final segment discharge sum")
    if any(values.dtype != np.float64 or values.shape != expected_shapes[name] for name,values in arrays.items()):
        raise ValueError("fine states exact dtype/shape mismatch")
    budget = SurfaceBudget(**solver["budget"])
    validate_budget(budget)
    if (np.any(arrays["depth_m"] > budget.max_depth_m) or type(solver["substeps"]) is not int or not 0 < solver["substeps"] <= budget.max_substeps
            or budget.max_wall_s>1800 or budget.max_bytes>MAX_BYTES or budget.max_cells>65536
            or type(solver["face_evaluations"]) is not int or not 0 < solver["face_evaluations"] <= budget.max_face_evaluations
            or type(solver["wall_s"]) not in (int,float) or not 0 <= solver["wall_s"] <= 1800):
        raise ValueError("fine saved solver depth/work budget mismatch")
    volumes = arrays["depth_m"].sum(axis=(1,2))*geometry["metadata"]["spacing_m"]**2
    ledger = arrays["ledger"]
    if ledger.shape != (steps+1,5) or np.any(ledger[:,:3] < 0) or np.any(np.diff(ledger[:,:3],axis=0) < -1e-8):
        raise ValueError("fine cumulative surface ledger mismatch")
    _near(ledger[:,3], volumes, "surface snapshots")
    expected_supply = np.r_[0., np.cumsum(forcing["arrays"]["outflow_volume_m3"].sum(axis=1))]
    _near(ledger[:,0], expected_supply, "surface supplied runoff exactly once")
    residual = volumes-volumes[0]-ledger[:,0]-ledger[:,1]+ledger[:,2]
    _near(ledger[:,4], residual, "surface saved residual")
    _near(residual, np.zeros_like(residual), "surface whole budget")
    soil = sum(forcing["arrays"][name] for name in ("soil_mm","fast_mm","slow_mm"))*geometry["metadata"]["spacing_m"]**2/1000
    total = soil.sum(axis=1)+volumes
    rain = np.r_[0.,np.cumsum(forcing["arrays"]["rain_volume_m3"].sum(axis=1))]
    et = np.r_[0.,np.cumsum(forcing["arrays"]["et_volume_m3"].sum(axis=1))]
    _near(total-total[0], rain-et+ledger[:,1]-ledger[:,2], "four-compartment whole budget")
    return True


def validate_fine_momentum(packet, *, bed, geometry, forcing, states, interval, interval_packet):
    arrays, metadata = _check(packet,"single-domain-fine-momentum-v1")
    if geometry["metadata"].get("hydraulic_model") in SHALLOW_MODELS:
        return _validate_shallow_momentum(arrays,metadata,bed,geometry,forcing,states,interval,interval_packet)
    fields = {"depth_before_m","depth_after_m","forcing_m3_s","tailwater_m",
              "internal_q_before_m3_s","internal_q_after_m3_s","boundary_q_before_m3_s","boundary_q_after_m3_s"}
    subgrid = geometry["metadata"].get("hydraulic_model") == SUBGRID_MODEL
    shallow = geometry["metadata"].get("hydraulic_model") == SHALLOW_MODEL
    if subgrid:
        fields |= {f"{kind}_segment_q_{endpoint}_m3_s" for kind in ("internal","boundary") for endpoint in ("before","after")}
    if set(arrays) != fields:
        raise ValueError("fine exact first-substep momentum fields required")
    cells = bed["arrays"]["bed_center_m"].size
    faces, boundaries = len(geometry["arrays"]["face_left"]),len(geometry["arrays"]["boundary_cell"])
    for name,values in arrays.items():
        count = boundaries if name.startswith("boundary_") or name=="tailwater_m" else faces if name.startswith("internal_") else cells
        shape = (count,int(geometry["metadata"]["spacing_m"])) if "_segment_" in name else (count,)
        if values.dtype != np.float64 or values.shape != shape:
            raise ValueError("fine momentum exact array shape/type mismatch")
    dt, cadence = metadata["dt_s"], forcing["metadata"]["dt_s"]
    budget = SurfaceBudget(**states["metadata"]["solver_metadata"]["budget"])
    if (metadata["bed_identity"] != bed["identity_sha256"] or metadata["geometry_identity"] != geometry["identity_sha256"]
            or metadata["forcing_identity"] != forcing["identity_sha256"] or type(metadata["interval"]) is not int
            or metadata["interval"] != interval or abs(metadata["time_start_s"]-interval*cadence)>1e-9
            or type(dt) not in (int,float) or not 0 < dt <= budget.max_dt_s):
        raise ValueError("fine sampled momentum time/source mismatch")
    for name in ("depth_before_m","internal_q_before_m3_s","boundary_q_before_m3_s"):
        if not np.array_equal(arrays[name],interval_packet["arrays"][name]):
            raise ValueError("fine sampled momentum interval endpoint mismatch")
    _near(arrays["forcing_m3_s"],forcing["arrays"]["local_q_m3_s"][interval],"sampled runoff Q")
    _near(arrays["tailwater_m"],forcing["arrays"]["boundary_stage_m"][interval],"sampled tailwater")
    kinds, crest = geometry["arrays"]["boundary_kind"], geometry["arrays"]["boundary_crest_m"]
    exterior = np.where(kinds==1,crest,arrays["tailwater_m"])
    if subgrid:
        from terrain_pipeline.single_domain_fine_geometry import storage_stages
        g = geometry["arrays"]
        stage = storage_stages(arrays["depth_before_m"],g["subcell_bed_relative_m"],g["subcell_prefix_relative_m"])
        flow_depth = np.maximum(np.maximum(stage[g["face_left"]],stage[g["face_right"]])[:,None]-g["face_segment_crest_relative_m"],0)
        boundary_depth = np.maximum(arrays["tailwater_m"][:,None]-geometry["metadata"]["hydraulic_datum_m"]-g["boundary_segment_crest_relative_m"],0)
        deepest = max(float(flow_depth.max(initial=0)),float(boundary_depth[kinds!=0].max(initial=0)))
    else:
        deepest = max(float(arrays["depth_before_m"].max()),float(np.maximum(exterior-crest,0)[kinds!=0].max(initial=0)))
    cfl = budget.inertial_cfl*geometry["metadata"]["spacing_m"]/2/math.sqrt(budget.gravity_m_s2*deepest) if deepest else math.inf
    if dt > cfl+1e-12:
        raise ValueError("fine sampled momentum gravity CFL mismatch")
    if subgrid:
        internal_segments,boundary_segments,limiter = _segment_momentum_witness(geometry,arrays["depth_before_m"],
            arrays["internal_segment_q_before_m3_s"],arrays["boundary_segment_q_before_m3_s"],
            arrays["tailwater_m"],arrays["forcing_m3_s"],dt,budget,stage)
        for kind,expected in (("internal",internal_segments),("boundary",boundary_segments)):
            _near(arrays[f"{kind}_segment_q_after_m3_s"],expected,"subgrid sampled segment momentum")
            for endpoint in ("before","after"):
                _near(arrays[f"{kind}_segment_q_{endpoint}_m3_s"].sum(axis=1),arrays[f"{kind}_q_{endpoint}_m3_s"],"subgrid sampled total Q")
            if not np.array_equal(arrays[f"{kind}_segment_q_before_m3_s"],interval_packet["arrays"][f"{kind}_segment_q_before_m3_s"]):
                raise ValueError("subgrid sampled segment checkpoint continuity mismatch")
        internal,boundary = internal_segments.sum(axis=1),boundary_segments.sum(axis=1)
    else:
        internal,boundary,limiter = limited_inertial_fluxes(geometry,arrays["depth_before_m"],arrays["internal_q_before_m3_s"],
            arrays["boundary_q_before_m3_s"],arrays["tailwater_m"],arrays["forcing_m3_s"],dt,budget)
    _near(arrays["internal_q_after_m3_s"],internal,"sampled momentum internal Q")
    _near(arrays["boundary_q_after_m3_s"],boundary,"sampled momentum boundary Q")
    expected = arrays["depth_before_m"]+dt*(arrays["forcing_m3_s"]+_net_flux(geometry,internal,boundary))/geometry["metadata"]["spacing_m"]**2
    _near(arrays["depth_after_m"],expected,"sampled momentum water depth")
    if metadata["limiter"] != limiter:
        raise ValueError("fine sampled momentum donor limiter mismatch")
    return True


def _saved_flux_divergence(geometry, internal, boundary):
    arrays = geometry["arrays"]
    result = np.zeros((geometry["arrays"]["H2_m"].size,internal.shape[1]))
    np.add.at(result,arrays["face_left"],-internal)
    np.add.at(result,arrays["face_right"],internal)
    np.add.at(result,arrays["boundary_cell"],-boundary)
    return result


def _validate_shallow_momentum(arrays,metadata,bed,geometry,forcing,states,interval,interval_packet):
    cells = bed["arrays"]["bed_center_m"].size
    faces,boundaries = len(geometry["arrays"]["face_left"]),len(geometry["arrays"]["boundary_cell"])
    shapes = dict(state_before=(cells,3),state_predictor=(cells,3),state_after=(cells,3),
                  forcing_m3_s=(cells,),tailwater_m=(boundaries,),manning_momentum_change=(cells,2))
    canonical_manning = geometry["metadata"].get("hydraulic_model") == SHALLOW_SUBGRID_MANNING_MODEL
    if canonical_manning:
        shapes["manning_inverse_depth_third_mean"] = (cells,)
    for rk in (1,2):
        shapes.update({f"rk{rk}_internal_flux":(faces,3),f"rk{rk}_boundary_flux":(boundaries,3),f"rk{rk}_bed_source":(cells,3)})
    if set(arrays) != set(shapes) or any(value.dtype != np.float64 or value.shape != shapes[name] for name,value in arrays.items()):
        raise ValueError("shallow exact sampled momentum layout mismatch")
    dt,cadence = metadata["dt_s"],forcing["metadata"]["dt_s"]
    budget = SurfaceBudget(**states["metadata"]["solver_metadata"]["budget"])
    if (metadata.get("hydraulic_model") != geometry["metadata"].get("hydraulic_model") or metadata["bed_identity"] != bed["identity_sha256"]
            or metadata["geometry_identity"] != geometry["identity_sha256"] or metadata["forcing_identity"] != forcing["identity_sha256"]
            or type(metadata["interval"]) is not int or metadata["interval"] != interval
            or abs(metadata["time_start_s"]-interval*cadence)>1e-9 or type(dt) not in (int,float) or not 0 < dt <= min(cadence,budget.max_dt_s)):
        raise ValueError("shallow sampled momentum model/time/source mismatch")
    before,predictor,after = (arrays[name] for name in ("state_before","state_predictor","state_after"))
    if any(np.any(value[:,0] < 0) or np.any(value[:,0] > budget.max_depth_m) for value in (before,predictor,after)):
        raise ValueError("shallow sampled depth range mismatch")
    _near(before[:,0],interval_packet["arrays"]["depth_before_m"],"shallow first substep depth")
    _near(before[:,1:],interval_packet["arrays"]["momentum_before"],"shallow first substep momentum")
    _near(arrays["forcing_m3_s"],forcing["arrays"]["local_q_m3_s"][interval],"shallow sampled runoff")
    _near(arrays["tailwater_m"],forcing["arrays"]["boundary_stage_m"][interval],"shallow sampled tailwater")
    spacing = geometry["metadata"]["spacing_m"]
    rhs = []
    for rk in (1,2):
        source = arrays[f"rk{rk}_bed_source"]
        if np.any(source[:,0] != 0):
            raise ValueError("shallow bed source must not create water")
        flux = _saved_flux_divergence(geometry,arrays[f"rk{rk}_internal_flux"],arrays[f"rk{rk}_boundary_flux"])/spacing+source
        flux[:,0] += arrays["forcing_m3_s"]/spacing**2
        rhs.append(flux)
        if np.any(arrays[f"rk{rk}_boundary_flux"][geometry["arrays"]["boundary_kind"]==0,0] != 0):
            raise ValueError("shallow closed wall sampled mass flux")
    _near(predictor,before+dt*rhs[0],"shallow SSPRK2 predictor")
    undamped = .5*before+.5*(predictor+dt*rhs[1])
    _near(after[:,0],undamped[:,0],"shallow SSPRK2 mass endpoint")
    expected_momentum = undamped[:,1:].copy()
    wet = undamped[:,0] > 0
    if canonical_manning:
        stage = _saved_storage_stage(undamped[:,0],geometry["arrays"]["subcell_bed_relative_m"])
        subdepth = np.maximum(stage[:,None]-geometry["arrays"]["subcell_bed_relative_m"],0)
        inverse = np.zeros_like(subdepth)
        np.power(subdepth,-1/3,out=inverse,where=subdepth>0)
        factor = inverse.mean(axis=1)
        _near(arrays["manning_inverse_depth_third_mean"],factor,"canonical Manning wet-subcell integral")
        hsquared = undamped[:,0]**2
        denominator = hsquared+dt*budget.gravity_m_s2*budget.roughness_s_m_third**2*np.linalg.norm(expected_momentum,axis=1)*factor
        expected_momentum = np.divide(expected_momentum*hsquared[:,None],denominator[:,None],out=np.zeros_like(expected_momentum),where=denominator[:,None]>0)
    else:
        hpower = undamped[wet,0]**(7/3)
        denominator = hpower+dt*budget.gravity_m_s2*budget.roughness_s_m_third**2*np.linalg.norm(expected_momentum[wet],axis=1)
        expected_momentum[wet] = np.divide(expected_momentum[wet]*hpower[:,None],denominator[:,None],out=np.zeros_like(expected_momentum[wet]),where=denominator[:,None]>0)
    _near(after[:,1:],expected_momentum,"shallow implicit Manning momentum")
    _near(arrays["manning_momentum_change"],after[:,1:]-undamped[:,1:],"shallow Manning impulse witness")
    velocity = np.divide(before[:,1:],before[:,0,None],out=np.zeros_like(before[:,1:]),where=before[:,0,None]>0)
    speed = float((abs(velocity).sum(axis=1)+2*np.sqrt(budget.gravity_m_s2*before[:,0])).max(initial=0))
    if geometry["metadata"].get("hydraulic_model") in SHALLOW_SUBGRID_MODELS:
        stage = _saved_storage_stage(before[:,0],geometry["arrays"]["subcell_bed_relative_m"])
        deepest = np.maximum(stage-geometry["arrays"]["subcell_bed_relative_m"][:,0],0)
        speed = max(speed,float((abs(velocity).sum(axis=1)+2*np.sqrt(budget.gravity_m_s2*deepest)).max(initial=0)))
    boundary_bed = np.maximum(geometry["arrays"]["H2_m"].ravel()[geometry["arrays"]["boundary_cell"]],geometry["arrays"]["boundary_crest_m"])
    if geometry["metadata"].get("hydraulic_model") in SHALLOW_SUBGRID_MODELS:
        boundary_bed = np.maximum(geometry["arrays"]["boundary_segment_crest_relative_m"].min(axis=1)+geometry["metadata"]["hydraulic_datum_m"],geometry["arrays"]["boundary_crest_m"])
    exterior_stage = np.where(geometry["arrays"]["boundary_kind"]==1,boundary_bed,arrays["tailwater_m"])
    external_depth = np.maximum(exterior_stage-boundary_bed,0)
    speed = max(speed,float((2*np.sqrt(budget.gravity_m_s2*external_depth[geometry["arrays"]["boundary_kind"]!=0])).max(initial=0)))
    if dt > budget.inertial_cfl*spacing/max(speed,1e-12)+1e-12:
        raise ValueError("shallow sampled advective gravity CFL mismatch")
    return True


def _saved_storage_stage(depth,subbed):
    count = subbed.shape[1]
    prefix = np.cumsum(subbed,axis=1)
    candidate = (depth[:,None]*count+prefix)/np.arange(1,count+1)
    valid = candidate >= subbed
    index = valid.sum(axis=1)-1
    return candidate[np.arange(len(depth)),index]


def validate_fine_interval(packet, *, bed, geometry, forcing, interval, previous=None):
    arrays, metadata = _check(packet, "single-domain-fine-interval-v1")
    shape = bed["arrays"]["bed_center_m"].shape
    cells, faces = math.prod(shape), len(geometry["arrays"]["face_left"])
    boundaries = len(geometry["arrays"]["boundary_cell"])
    expected_shapes = {name:(faces if name.startswith("internal_") else boundaries if name.startswith("boundary_") else cells,)
                       for name in INTERVAL_ARRAYS}
    subgrid = geometry["metadata"].get("hydraulic_model") == SUBGRID_MODEL
    shallow = geometry["metadata"].get("hydraulic_model") in SHALLOW_MODELS
    if subgrid:
        factor = int(geometry["metadata"]["spacing_m"])
        for kind,count in (("internal",faces),("boundary",boundaries)):
            expected_shapes[f"{kind}_segment_transfer_m3"] = (count,factor)
            for endpoint in ("before","after"):
                expected_shapes[f"{kind}_segment_q_{endpoint}_m3_s"] = (count,factor)
    if shallow:
        expected_shapes.update(momentum_before=(cells,2),momentum_after=(cells,2),internal_momentum_transfer=(faces,2),
                               boundary_momentum_transfer=(boundaries,2),bed_momentum_change=(cells,2),manning_momentum_change=(cells,2))
    if set(arrays) != set(expected_shapes) or any(arrays[name].shape != expected_shapes[name] or arrays[name].dtype != np.float64 for name in arrays):
        raise ValueError("fine interval exact array layout mismatch")
    dt = forcing["metadata"]["dt_s"]
    if (metadata["bed_identity"] != bed["identity_sha256"] or metadata["geometry_identity"] != geometry["identity_sha256"]
            or metadata["forcing_identity"] != forcing["identity_sha256"] or type(metadata["interval"]) is not int
            or metadata["interval"] != interval or abs(metadata["time_start_s"]-interval*dt)>1e-9 or abs(metadata["time_end_s"]-(interval+1)*dt)>1e-9):
        raise ValueError("fine interval time/source binding mismatch")
    if np.any(arrays["depth_before_m"] < 0) or np.any(arrays["depth_after_m"] < 0):
        raise ValueError("fine interval negative water")
    if previous is not None:
        for name in ("depth", "internal_q", "boundary_q"):
            unit = "m" if name == "depth" else "m3_s"
            if not np.array_equal(arrays[f"{name}_before_{unit}"], previous["arrays"][f"{name}_after_{unit}"]):
                raise ValueError("fine interval exact depth/momentum continuity mismatch")
    elif interval == 0 and any(np.any(arrays[name] != 0) for name in ("internal_q_before_m3_s","boundary_q_before_m3_s")):
        raise ValueError("fine declared initial zero momentum mismatch")
    _near(arrays["forcing_volume_m3"], forcing["arrays"]["outflow_volume_m3"][interval], "complete runoff forcing")
    change = geometry["metadata"]["spacing_m"]**2*(arrays["depth_after_m"]-arrays["depth_before_m"])
    _near(change, arrays["forcing_volume_m3"]+_net_flux(geometry, arrays["internal_transfer_m3"], arrays["boundary_transfer_m3"]), "signed face cell continuity")
    if np.any(arrays["boundary_transfer_m3"][geometry["arrays"]["boundary_kind"] == 0] != 0):
        raise ValueError("fine closed exterior transfer")
    closed = geometry["arrays"]["boundary_kind"] == 0
    if np.any(arrays["boundary_q_before_m3_s"][closed] != 0) or np.any(arrays["boundary_q_after_m3_s"][closed] != 0):
        raise ValueError("fine closed exterior endpoint discharge")
    if subgrid:
        for kind in ("internal","boundary"):
            _near(arrays[f"{kind}_segment_transfer_m3"].sum(axis=1),arrays[f"{kind}_transfer_m3"],"subgrid signed segment transfer sum")
            for endpoint in ("before","after"):
                _near(arrays[f"{kind}_segment_q_{endpoint}_m3_s"].sum(axis=1),arrays[f"{kind}_q_{endpoint}_m3_s"],"subgrid segment endpoint discharge sum")
            before = arrays[f"{kind}_segment_q_before_m3_s"]
            if previous is None and np.any(before!=0) or previous is not None and not np.array_equal(before,previous["arrays"][f"{kind}_segment_q_after_m3_s"]):
                raise ValueError("subgrid exact segment momentum chain mismatch")
        if np.any(arrays["boundary_segment_transfer_m3"][closed]!=0):
            raise ValueError("subgrid closed boundary segment transfer")
    if shallow:
        if metadata.get("hydraulic_model") != geometry["metadata"].get("hydraulic_model"):
            raise ValueError("shallow interval model binding mismatch")
        expected_before = previous["arrays"]["momentum_after"] if previous is not None else np.zeros((cells,2))
        _near(arrays["momentum_before"],expected_before,"shallow momentum continuity")
        momentum_change = _saved_flux_divergence(geometry,arrays["internal_momentum_transfer"],arrays["boundary_momentum_transfer"])/geometry["metadata"]["spacing_m"]**2
        momentum_change += arrays["bed_momentum_change"]+arrays["manning_momentum_change"]
        _near(arrays["momentum_after"]-arrays["momentum_before"],momentum_change,"shallow interval momentum closure")
        if np.any(arrays["boundary_transfer_m3"][closed] != 0):
            raise ValueError("shallow closed boundary transfer")
    return True


def _headers(headers):
    if "manifest" not in headers or len(headers)>64:
        raise ValueError("fine exact bounded archive headers required")
    for name,(shape,dtype) in headers.items():
        if name == "manifest":
            if dtype != np.uint8 or len(shape)!=1 or math.prod(shape)>1048576:
                raise ValueError("fine bounded manifest allocation")
        elif dtype not in (np.dtype("float64"),np.dtype("int64"),np.dtype("bool")) or math.prod(shape)>2000000:
            raise ValueError("fine bounded numeric allocation")


def _load(record, validator):
    result = load_bundle(record["path"], expected_sha256=record["expected_sha256"], max_bytes=MAX_BYTES,
                         header_validator=_headers, validator=validator)
    if result["identity_sha256"] != record["expected_identity"]:
        raise ValueError("fine external content identity mismatch")
    return result


def save_fine_run(path, result, *, bed_record, code_sha256, code_records=None):
    root = Path(path).resolve()
    root.mkdir(parents=True, exist_ok=False)
    bed, geometry, forcing, states = (result[name] for name in ("bed","geometry","forcing","states"))
    records = {}
    validators = dict(geometry=lambda item:validate_fine_geometry(item,bed=bed),
                      forcing=lambda item:validate_fine_forcing(item,bed=bed),
                      states=lambda item:validate_fine_states(item,bed=bed,geometry=geometry,forcing=forcing))
    for role in ("geometry","forcing","states"):
        target = root/(role+".npz")
        save_bundle(target,result[role],validator=validators[role])
        records[role] = dict(path=str(target),expected_sha256=file_sha256(target),expected_identity=result[role]["identity_sha256"])
    interval_records = []
    previous = None
    for interval, packet in enumerate(result["intervals"]):
        target = root/f"interval-{interval:03d}.npz"
        save_bundle(target,packet,validator=lambda item:validate_fine_interval(item,bed=bed,geometry=geometry,
                    forcing=forcing,interval=interval,previous=previous))
        interval_records.append(dict(path=str(target),expected_sha256=file_sha256(target),expected_identity=packet["identity_sha256"]))
        previous = packet
    # Momentum witnesses are separate from integrated transfer accounts.
    momentum_records = []
    for interval, packet in enumerate(result["momenta"]):
        target = root/f"momentum-{interval:03d}.npz"
        save_bundle(target,packet,validator=lambda item:validate_fine_momentum(item,bed=bed,geometry=geometry,
                    forcing=forcing,states=states,interval=interval,interval_packet=result["intervals"][interval]))
        momentum_records.append(dict(path=str(target),expected_sha256=file_sha256(target),expected_identity=packet["identity_sha256"]))
    if sum(target.stat().st_size for target in root.iterdir() if target.is_file()) > 2147483648:
        raise ValueError("fine run output exceeds 2 GiB")
    index = dict(schema="single-domain-fine-run-index-v1",bed_record=bed_record,**records,
                 intervals=interval_records,momenta=momentum_records,code_sha256=code_sha256,
                 hydraulic_ready=False,natural_outlet_verified=False,publishable=False,limitations=result["limitations"])
    if code_records is not None:
        _validate_code_records(code_sha256,code_records,root.parent)
        index["code_records"] = code_records
    target = root/"index.json"
    publish_bytes(target,(json.dumps(index,sort_keys=True,indent=2,allow_nan=False)+"\n").encode("utf-8"))
    return dict(path=str(target),expected_sha256=file_sha256(target))


def _validate_code_records(code_sha256,code_records,stage_root):
    stage_root = stage_root.resolve(strict=True)
    snapshot_root = (stage_root/"execution-code").resolve(strict=True)
    if not snapshot_root.is_relative_to(stage_root):
        raise ValueError("fine immutable implementation snapshot root escaped stage")
    if not isinstance(code_records,dict) or set(code_records) != set(code_sha256):
        raise ValueError("fine frozen code record names mismatch")
    for name,digest in code_sha256.items():
        record = code_records[name]
        expected_path = (snapshot_root/name).resolve(strict=True)
        path = Path(record["path"]).resolve(strict=True)
        if (not expected_path.is_relative_to(snapshot_root) or path != expected_path
                or record["expected_sha256"] != digest or file_sha256(path) != digest):
            raise ValueError("fine immutable implementation snapshot pin mismatch")


def load_fine_run(path, *, expected_sha256, bed):
    index = _json(dict(path=str(path),expected_sha256=expected_sha256))
    root = Path(path).resolve().parent
    if index.get("schema") != "single-domain-fine-run-index-v1" or any(index.get(name) is not False for name in FLAGS):
        raise ValueError("fine run index schema/flags mismatch")
    if index["bed_record"]["expected_identity"] != bed["identity_sha256"] or file_sha256(index["bed_record"]["path"]) != index["bed_record"]["expected_sha256"]:
        raise ValueError("fine external bed binding mismatch")
    code_root = Path(__file__).resolve().parents[1]
    if not isinstance(index.get("code_sha256"),dict) or not index["code_sha256"]:
        raise ValueError("fine frozen implementation pins required")
    if "code_records" in index:
        _validate_code_records(index["code_sha256"],index["code_records"],root.parent)
    else:
        for name,digest in index["code_sha256"].items():
            target = (code_root/name).resolve(strict=True)
            if not target.is_relative_to(code_root) or file_sha256(target) != digest:
                raise ValueError("fine frozen implementation pin mismatch")
    for role in ("geometry","forcing","states"):
        _layout(index[role],root/(role+".npz"))
    geometry = _load(index["geometry"],lambda item:validate_fine_geometry(item,bed=bed))
    forcing = _load(index["forcing"],lambda item:validate_fine_forcing(item,bed=bed))
    states = _load(index["states"],lambda item:validate_fine_states(item,bed=bed,geometry=geometry,forcing=forcing))
    steps = forcing["metadata"]["steps"]
    if len(index["intervals"]) != steps or len(index["momenta"]) != steps:
        raise ValueError("fine complete interval/momentum coverage required")
    previous = None
    for interval, record in enumerate(index["intervals"]):
        _layout(record,root/f"interval-{interval:03d}.npz")
        packet = _load(record,lambda item:validate_fine_interval(item,bed=bed,geometry=geometry,forcing=forcing,
                                                              interval=interval,previous=previous))
        momentum_record = index["momenta"][interval]
        _layout(momentum_record,root/f"momentum-{interval:03d}.npz")
        _load(momentum_record,lambda item:validate_fine_momentum(item,bed=bed,geometry=geometry,forcing=forcing,
              states=states,interval=interval,interval_packet=packet))
        if not np.array_equal(packet["arrays"]["depth_before_m"],states["arrays"]["depth_m"][interval].ravel()) or not np.array_equal(packet["arrays"]["depth_after_m"],states["arrays"]["depth_m"][interval+1].ravel()):
            raise ValueError("fine interval/snapshot original depth mismatch")
        if geometry["metadata"].get("hydraulic_model") in SHALLOW_MODELS:
            for endpoint,number in (("before",interval),("after",interval+1)):
                momentum = np.column_stack((states["arrays"]["momentum_x_m2_s"][number].ravel(),states["arrays"]["momentum_z_m2_s"][number].ravel()))
                if not np.array_equal(packet["arrays"]["momentum_"+endpoint],momentum):
                    raise ValueError("shallow interval/snapshot momentum endpoint mismatch")
        ledger = states["arrays"]["ledger"]
        actual_boundary_net = float(packet["arrays"]["boundary_transfer_m3"].sum())
        _near(np.asarray(ledger[interval+1,2]-ledger[interval,2]-ledger[interval+1,1]+ledger[interval,1]),
              np.asarray(actual_boundary_net),"exterior net vs gross ledger difference")
        previous = packet
    if not np.array_equal(previous["arrays"]["internal_q_after_m3_s"],states["arrays"]["final_internal_q_m3_s"]) or not np.array_equal(previous["arrays"]["boundary_q_after_m3_s"],states["arrays"]["final_boundary_q_m3_s"]):
        raise ValueError("fine final momentum endpoint mismatch")
    if geometry["metadata"].get("hydraulic_model") == SUBGRID_MODEL:
        for kind in ("internal","boundary"):
            if not np.array_equal(previous["arrays"][f"{kind}_segment_q_after_m3_s"],states["arrays"][f"final_{kind}_segment_q_m3_s"]):
                raise ValueError("subgrid final segment checkpoint mismatch")
    if file_sha256(path) != expected_sha256:
        raise ValueError("fine run index changed during cold load")
    return dict(index=index,bed=bed,geometry=geometry,forcing=forcing,states=states,
                intervals_verified=steps,solver_advanced=False)
