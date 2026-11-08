"""Explicit non-fastmath JIT execution of the unchanged v7 hydraulic equations."""

from functools import lru_cache,partial
import math

import numpy as np
from numba import njit

from terrain_pipeline.single_domain_shallow_water_support_v7 import MODEL
from terrain_pipeline.single_domain_shallow_water_execution_v7 import advance_shallow_water as reference_advance


@njit(cache=True,fastmath=False)
def storage_kernel(depth,bed,prefix):
    stage = np.empty(len(depth))
    count = bed.shape[1]
    for cell in range(len(depth)):
        volume = depth[cell]*count
        wet = 0
        for index in range(count):
            if volume >= (index+1)*bed[cell,index]-prefix[cell,index]:
                wet += 1
        wet = max(wet,1)
        stage[cell] = (volume+prefix[cell,wet-1])/wet
    return stage


@njit(cache=True,fastmath=False,inline="always")
def _hll(hl,hr,ul,vl,ur,vr,crest,gravity,axis):
    # Match the reference's common-crest hydrostatic reconstruction, including
    # its finite-precision depth/momentum round trip.
    if hl>0:
        ul,vl = (hl*ul)/hl,(hl*vl)/hl
    else:
        ul,vl = 0.,0.
    if hr>0:
        ur,vr = (hr*ur)/hr,(hr*vr)/hr
    else:
        ur,vr = 0.,0.
    hl = max(hl+crest-crest,0.)
    hr = max(hr+crest-crest,0.)
    normal_left = ul if axis==0 else vl
    normal_right = ur if axis==0 else vr
    lower = min(normal_left-math.sqrt(gravity*hl),normal_right-math.sqrt(gravity*hr))
    upper = max(normal_left+math.sqrt(gravity*hl),normal_right+math.sqrt(gravity*hr))
    mass,xmomentum,zmomentum = 0.,0.,0.
    for component in range(3):
        first = hl if component==0 else hl*ul if component==1 else hl*vl
        second = hr if component==0 else hr*ur if component==1 else hr*vr
        fl,fr = first*normal_left,second*normal_right
        if component==axis+1:
            fl += .5*gravity*hl**2
            fr += .5*gravity*hr**2
        flux = 0.
        if upper-lower>0:
            flux = (upper*fl-lower*fr+(lower*upper)*(second-first))/(upper-lower)
        if lower>=0:
            flux = fl
        if upper<=0:
            flux = fr
        if component==0:
            mass = flux
        elif component==1:
            xmomentum = flux
        else:
            zmomentum = flux
    return mass,xmomentum,zmomentum,max(abs(lower),abs(upper))


@lru_cache(maxsize=16)
def _topology(rows,columns):
    grid = np.arange(rows*columns).reshape(rows,columns)
    return (np.r_[grid[:,:-1].ravel(),grid[:-1].ravel()],np.r_[grid[:,1:].ravel(),grid[1:].ravel()],
        np.r_[np.zeros(rows*(columns-1),np.int64),np.ones((rows-1)*columns,np.int64)],
        np.r_[grid[:,0],grid[:,-1],grid[0],grid[-1]],
        np.r_[np.zeros(2*rows,np.int64),np.ones(2*columns,np.int64)],
        np.r_[-np.ones(rows),np.ones(rows),-np.ones(columns),np.ones(columns)])


@njit(cache=True,fastmath=False)
def rhs_kernel(state,subbed,prefix,crests,boundary_crests,left,right,axes,cells,boundary_axes,signs,
               spacing,gravity,kinds,tailwater,boundary_crest,dt):
    count,segments = len(state),crests.shape[1]
    stage = storage_kernel(state[:,0],subbed,prefix)
    velocity = np.zeros((count,2))
    for cell in range(count):
        if state[cell,0]>0:
            velocity[cell,0] = state[cell,1]/state[cell,0]
            velocity[cell,1] = state[cell,2]/state[cell,0]
    internal,boundary = np.zeros((len(left),3)),np.zeros((len(cells),3))
    first_pressure,second_pressure,exterior_pressure = np.zeros(len(left)),np.zeros(len(left)),np.zeros(len(cells))
    maximum_speed = 0.
    for face in range(len(left)):
        a,b,axis = left[face],right[face],axes[face]
        for segment in range(segments):
            crest = crests[face,segment]
            hl,hr = max(stage[a]-crest,0.),max(stage[b]-crest,0.)
            mass,mx,mz,speed = _hll(hl,hr,velocity[a,0],velocity[a,1],velocity[b,0],velocity[b,1],crest,gravity,axis)
            internal[face,0] += mass
            internal[face,1] += mx
            internal[face,2] += mz
            first_pressure[face] += hl**2
            second_pressure[face] += hr**2
            maximum_speed = max(maximum_speed,speed)
        for component in range(3):
            internal[face,component] /= segments
        first_pressure[face] = .5*gravity*first_pressure[face]/segments
        second_pressure[face] = .5*gravity*second_pressure[face]/segments
    for face in range(len(cells)):
        cell,axis,sign = cells[face],boundary_axes[face],signs[face]
        for segment in range(segments):
            crest = boundary_crests[face,segment]
            if kinds[face]!=0:
                crest = max(crest,boundary_crest[face])
            h = max(stage[cell]-crest,0.)
            ux,uz = velocity[cell,0],velocity[cell,1]
            gx,gz = ux,uz
            if axis==0:
                gx = -gx
            else:
                gz = -gz
            ghost_h = h
            if kinds[face]!=0:
                exterior_stage = crest if kinds[face]==1 else tailwater[face]
                ghost_h,gx,gz = max(exterior_stage-crest,0.),0.,0.
            if axis==0:
                ux,gx = ux*sign,gx*sign
            else:
                uz,gz = uz*sign,gz*sign
            mass,mx,mz,speed = _hll(h,ghost_h,ux,uz,gx,gz,crest,gravity,axis)
            boundary[face,0] += mass
            boundary[face,1] += mx*sign if axis==0 else mx
            boundary[face,2] += mz*sign if axis==1 else mz
            exterior_pressure[face] += h**2
            maximum_speed = max(maximum_speed,speed)
        for component in range(3):
            boundary[face,component] /= segments
        exterior_pressure[face] = .5*gravity*exterior_pressure[face]/segments
    outgoing_left,outgoing_right,outgoing_boundary = np.zeros(count),np.zeros(count),np.zeros(count)
    for face in range(len(left)):
        outgoing_left[left[face]] += max(internal[face,0],0.)*spacing
        outgoing_right[right[face]] += max(-internal[face,0],0.)*spacing
    for face in range(len(cells)):
        outgoing_boundary[cells[face]] += max(boundary[face,0],0.)*spacing
    scales = np.ones(count)
    limited = 0
    minimum = 1.
    for cell in range(count):
        outgoing = outgoing_left[cell]+outgoing_right[cell]+outgoing_boundary[cell]
        if outgoing*dt>state[cell,0]*spacing**2:
            scales[cell] = state[cell,0]*spacing**2/(outgoing*dt)*(1-1e-12)
            minimum = min(minimum,scales[cell])
            limited += 1
    for face in range(len(left)):
        donor = left[face] if internal[face,0]>=0 else right[face]
        for component in range(3):
            internal[face,component] *= scales[donor]
    for face in range(len(cells)):
        if boundary[face,0]>=0:
            for component in range(3):
                boundary[face,component] *= scales[cells[face]]
    rhs,pressure = np.zeros_like(state),np.zeros_like(state)
    for face in range(len(left)):
        for component in range(3):
            rhs[left[face],component] -= internal[face,component]/spacing
        pressure[left[face],axes[face]+1] += first_pressure[face]/spacing
    for face in range(len(left)):
        for component in range(3):
            rhs[right[face],component] += internal[face,component]/spacing
        pressure[right[face],axes[face]+1] -= second_pressure[face]/spacing
    for face in range(len(cells)):
        for component in range(3):
            rhs[cells[face],component] -= boundary[face,component]/spacing
        pressure[cells[face],boundary_axes[face]+1] += signs[face]*exterior_pressure[face]/spacing
    rhs += pressure
    return rhs,internal,boundary,pressure,maximum_speed,minimum,limited


def shallow_water_rhs(state,bed,*,support,spacing,gravity,boundary_kind,tailwater,roughness,dt,boundary_crest=None):
    topology = _topology(*bed.shape)
    crest = np.full(len(boundary_kind),-np.inf) if boundary_crest is None else boundary_crest
    rhs,internal,boundary,pressure,speed,minimum,limited = rhs_kernel(state,support["subcell_bed_relative_m"],
        support["subcell_prefix_relative_m"],support["face_segment_crest_relative_m"],support["boundary_segment_crest_relative_m"],
        *topology,spacing,gravity,boundary_kind,tailwater,crest,dt)
    return rhs,dict(internal_flux=internal,boundary_flux=boundary,bed_source=pressure,
        maximum_wave_speed=float(speed),minimum_limiter_factor=float(minimum),limited_donors=int(limited))


@njit(cache=True,fastmath=False)
def damping_kernel(state,subbed,prefix,dt,gravity,roughness):
    stage = storage_kernel(state[:,0],subbed,prefix)
    damping,factor = np.zeros(len(state)),np.zeros(len(state))
    for cell in range(len(state)):
        for index in range(subbed.shape[1]):
            depth = max(stage[cell]-subbed[cell,index],0.)
            if depth>0:
                factor[cell] += depth**(-1/3)
        factor[cell] /= subbed.shape[1]
        squared = state[cell,0]**2
        denominator = squared+dt*gravity*roughness**2*math.hypot(state[cell,1],state[cell,2])*factor[cell]
        if denominator>0:
            damping[cell] = squared/denominator
    return damping,factor


def manning_damping(state,dt,gravity,roughness,*,support):
    return damping_kernel(state,support["subcell_bed_relative_m"],support["subcell_prefix_relative_m"],dt,gravity,roughness)


def advance_shallow_water(geometry,**kwargs):
    arrays,metadata = geometry["arrays"],geometry["metadata"]
    support = {name:arrays[name] for name in ("subcell_bed_relative_m","subcell_prefix_relative_m", "face_segment_crest_relative_m","boundary_segment_crest_relative_m")}
    def stage_provider(depth):
        return storage_kernel(depth,support["subcell_bed_relative_m"],support["subcell_prefix_relative_m"])
    def wave_speed(state,gravity):
        stage = stage_provider(state[:,0])
        maximum_depth = np.maximum(stage-support["subcell_bed_relative_m"][:,0],0.)
        velocity = np.divide(state[:,1:],state[:,0,None],out=np.zeros_like(state[:,1:]),where=state[:,0,None]>0)
        return float((abs(velocity).sum(axis=1)+2*np.sqrt(gravity*maximum_depth)).max(initial=0))
    result = reference_advance(geometry,rhs=partial(shallow_water_rhs,support=support),model=MODEL,
        hydraulic_datum_m=metadata["hydraulic_datum_m"],wave_speed=wave_speed,stage_provider=stage_provider,
        drag_provider=partial(manning_damping,support=support),face_evaluation_multiplier=support["face_segment_crest_relative_m"].shape[1],
        scope="independent FV canonical subgrid storage and segmented advective HLL with canonical Manning; SSPRK2; uncalibrated",
        physical_limitation="one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification",**kwargs)
    result["metadata"]["execution_backend"] = "numba_fastmath_false_v7_reference_control_flow"
    return result
