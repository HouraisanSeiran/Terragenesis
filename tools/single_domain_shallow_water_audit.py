"""Independent NumPy equations for auditing saved first-order shallow-water steps."""

import numpy as np


MODEL = "single-domain-hydrostatic-HLL-SSPRK2-v1"
MODEL_V2 = "single-domain-MUSCL-hydrostatic-HLL-SSPRK2-v2"
MODEL_V3 = "single-domain-subgrid-storage-segmented-HLL-SSPRK2-v3"
MODEL_V7 = "single-domain-subgrid-storage-segmented-HLL-canonical-Manning-SSPRK2-v7"


def assert_close(actual,expected,label):
    if np.shape(actual)!=np.shape(expected) or not np.isfinite(actual).all() or not np.allclose(actual,expected,atol=1e-9,rtol=1e-11):
        raise ValueError("independent shallow physical "+label+" mismatch")


def face_flux(first,second,zfirst,zsecond,g,axis):
    crest = np.maximum(zfirst,zsecond)
    depths = [np.maximum(state[:,0]+bed-crest,0.) for state,bed in ((first,zfirst),(second,zsecond))]
    velocities = [np.divide(state[:,1:],state[:,0,None],out=np.zeros_like(state[:,1:]),where=state[:,0,None]>0) for state in (first,second)]
    reconstructed = [np.column_stack((depth,depth[:,None]*velocity)) for depth,velocity in zip(depths,velocities)]
    speeds = [velocity[:,axis] for velocity in velocities]
    lower = np.minimum(speeds[0]-np.sqrt(g*depths[0]),speeds[1]-np.sqrt(g*depths[1]))
    upper = np.maximum(speeds[0]+np.sqrt(g*depths[0]),speeds[1]+np.sqrt(g*depths[1]))
    physical = [state*speed[:,None] for state,speed in zip(reconstructed,speeds)]
    for flux,depth in zip(physical,depths):
        flux[:,axis+1] += g*depth**2/2
    denominator = upper-lower
    flux = np.divide(upper[:,None]*physical[0]-lower[:,None]*physical[1]+(lower*upper)[:,None]*(reconstructed[1]-reconstructed[0]),
                     denominator[:,None],out=np.zeros_like(first),where=denominator[:,None]>0)
    flux[lower>=0] = physical[0][lower>=0]
    flux[upper<=0] = physical[1][upper<=0]
    corrections = [g*(state[:,0]**2-depth**2)/2 for state,depth in zip((first,second),depths)]
    return flux,*corrections


def reconstructed_faces(state,bed):
    depth = state[:,0].reshape(bed.shape)
    velocity = np.divide(state[:,1:],state[:,0,None],out=np.zeros_like(state[:,1:]),where=state[:,0,None]>0).reshape(*bed.shape,2)
    fields = np.dstack((depth+bed,bed,velocity))
    slopes = []
    for direction in (1,0):
        slope = np.zeros_like(fields)
        low,middle,high = ((fields[:,:-2],fields[:,1:-1],fields[:,2:]) if direction==1 else (fields[:-2],fields[1:-1],fields[2:]))
        first,second = middle-low,high-middle
        limited = np.where(first*second>0,np.sign(first)*np.minimum(abs(first),abs(second)),0.)
        if direction==1:
            slope[:,1:-1] = limited
        else:
            slope[1:-1] = limited
        slope[depth==0] = 0
        difference = slope[:,:,0]-slope[:,:,1]
        scale = np.minimum(1.,np.divide(2*depth,abs(difference),out=np.ones_like(depth),where=difference!=0))
        slopes.append(slope*scale[:,:,None])
    answers = []
    for slope in slopes:
        for sign in (-1,1):
            face = fields+sign*.5*slope
            h = np.maximum(face[:,:,0]-face[:,:,1],0)
            answers.append((np.column_stack((h.ravel(),(h[:,:,None]*face[:,:,2:]).reshape(-1,2))),face[:,:,1].ravel()))
    return answers


def physical_witness(state,geometry,spacing,g,tailwater,dt,*,model=MODEL):
    if model in (MODEL_V3,MODEL_V7):
        return subgrid_witness(state,geometry,spacing,g,tailwater,dt)
    bed = geometry["H2_m"]
    rows,columns = bed.shape
    grid = np.arange(bed.size).reshape(bed.shape)
    left = np.concatenate((grid[:,:-1].ravel(),grid[:-1,:].ravel()))
    right = np.concatenate((grid[:,1:].ravel(),grid[1:,:].ravel()))
    boundary = np.concatenate((grid[:,0],grid[:,-1],grid[0],grid[-1]))
    for name,expected in (("face_left",left),("face_right",right),("boundary_cell",boundary)):
        if not np.array_equal(geometry[name],expected):
            raise ValueError("independent shallow D4 ordering mismatch")
    axis = np.concatenate((np.zeros(rows*(columns-1),int),np.ones((rows-1)*columns,int)))
    boundary_axis = np.concatenate((np.zeros(2*rows,int),np.ones(2*columns,int)))
    signs = np.concatenate((-np.ones(rows),np.ones(rows),-np.ones(columns),np.ones(columns)))
    datum = float(bed.min())
    z = bed.ravel()-datum
    reconstructed = reconstructed_faces(state,bed-datum) if model==MODEL_V2 else [(state,z)]*4
    source = np.zeros_like(state)
    internal = np.zeros((len(left),3))
    for direction in (0,1):
        selected = axis==direction
        high,low = reconstructed[2*direction+1],reconstructed[2*direction]
        flux,first_pressure,second_pressure = face_flux(high[0][left[selected]],low[0][right[selected]],high[1][left[selected]],low[1][right[selected]],g,direction)
        internal[selected] = flux
        np.add.at(source[:,direction+1],left[selected],-first_pressure/spacing)
        np.add.at(source[:,direction+1],right[selected],second_pressure/spacing)
    kind = geometry["boundary_kind"]
    exterior = np.zeros((len(boundary),3))
    for side,(begin,end) in enumerate(((0,rows),(rows,2*rows),(2*rows,2*rows+columns),(2*rows+columns,len(boundary)))):
        direction = side//2
        selected = slice(begin,end)
        normal = signs[selected]
        ids = boundary[selected]
        inside = reconstructed[side][0][ids].copy()
        outside = inside.copy()
        inside_bed = reconstructed[side][1][ids]
        outside_bed = inside_bed.copy()
        opened = kind[selected]!=0
        crest_selection = opened if model==MODEL_V2 else np.ones(len(ids),bool)
        outside_bed[crest_selection] = np.maximum(outside_bed[crest_selection],(geometry["boundary_crest_m"][selected]-datum)[crest_selection])
        outside[:,direction+1] *= -1
        stage = np.where(kind[selected]==1,outside_bed,tailwater[selected]-datum)
        outside[opened,0] = np.maximum(stage[opened]-outside_bed[opened],0)
        outside[opened,1:] = 0
        inside[:,direction+1] *= normal
        outside[:,direction+1] *= normal
        flux,pressure,_ = face_flux(inside,outside,inside_bed,outside_bed,g,direction)
        flux[:,direction+1] *= normal
        exterior[selected] = flux
        np.add.at(source[:,direction+1],boundary[selected],-pressure*normal/spacing)
    if model==MODEL_V2:
        for direction in (0,1):
            low,high = reconstructed[2*direction],reconstructed[2*direction+1]
            source[:,direction+1] -= g*.5*(low[0][:,0]+high[0][:,0])*(high[1]-low[1])/spacing
    outgoing = np.bincount(left,weights=np.maximum(internal[:,0],0)*spacing,minlength=bed.size)
    outgoing += np.bincount(right,weights=np.maximum(-internal[:,0],0)*spacing,minlength=bed.size)
    outgoing += np.bincount(boundary,weights=np.maximum(exterior[:,0],0)*spacing,minlength=bed.size)
    scale = np.ones(bed.size)
    limited = outgoing*dt>state[:,0]*spacing**2
    scale[limited] = state[limited,0]*spacing**2/(outgoing[limited]*dt)*(1-1e-12)
    internal *= np.where(internal[:,0]>=0,scale[left],scale[right])[:,None]
    exterior *= np.where(exterior[:,0]>=0,scale[boundary],1.)[:,None]
    rhs = source.copy()
    np.add.at(rhs,left,-internal/spacing)
    np.add.at(rhs,right,internal/spacing)
    np.add.at(rhs,boundary,-exterior/spacing)
    return rhs,internal,exterior,source


def storage_stage(depth,subbed):
    counts = np.arange(1,subbed.shape[1]+1)
    candidate = (depth[:,None]*subbed.shape[1]+np.cumsum(subbed,axis=1))/counts
    index = (candidate>=subbed).sum(axis=1)-1
    return candidate[np.arange(len(depth)),index]


def canonical_manning(state,subbed,dt,gravity,roughness):
    stage = storage_stage(state[:,0],subbed)
    h = np.maximum(stage[:,None]-subbed,0)
    integral = np.zeros_like(h)
    np.power(h,-1/3,out=integral,where=h>0)
    factor = integral.mean(axis=1)
    squared = state[:,0]**2
    denominator = squared+dt*gravity*roughness**2*np.hypot(state[:,1],state[:,2])*factor
    damping = np.divide(squared,denominator,out=np.zeros_like(squared),where=denominator>0)
    return damping,factor


def subgrid_witness(state,geometry,spacing,g,tailwater,dt):
    left,right,cells = (geometry[name] for name in ("face_left","face_right","boundary_cell"))
    rows,columns = geometry["H2_m"].shape
    axes = np.r_[np.zeros(rows*(columns-1),int),np.ones((rows-1)*columns,int)]
    boundary_axes = np.r_[np.zeros(2*rows,int),np.ones(2*columns,int)]
    signs = np.r_[-np.ones(rows),np.ones(rows),-np.ones(columns),np.ones(columns)]
    datum = float(geometry["hydraulic_datum_m"])
    stage = storage_stage(state[:,0],geometry["subcell_bed_relative_m"])
    velocity = np.divide(state[:,1:],state[:,0,None],out=np.zeros_like(state[:,1:]),where=state[:,0,None]>0)
    internal = np.zeros((len(left),3))
    exterior = np.zeros((len(cells),3))
    source = np.zeros_like(state)
    for direction in (0,1):
        selected = axes==direction
        crest = geometry["face_segment_crest_relative_m"][selected]
        hl = np.maximum(stage[left[selected],None]-crest,0)
        hr = np.maximum(stage[right[selected],None]-crest,0)
        first = np.column_stack((hl.ravel(),(hl[:,:,None]*velocity[left[selected],None,:]).reshape(-1,2)))
        second = np.column_stack((hr.ravel(),(hr[:,:,None]*velocity[right[selected],None,:]).reshape(-1,2)))
        flux,_,_ = face_flux(first,second,crest.ravel(),crest.ravel(),g,direction)
        internal[selected] = flux.reshape(*crest.shape,3).mean(axis=1)
        np.add.at(source[:,direction+1],left[selected],.5*g*(hl**2).mean(axis=1)/spacing)
        np.add.at(source[:,direction+1],right[selected],-.5*g*(hr**2).mean(axis=1)/spacing)
        selected = boundary_axes==direction
        ids = cells[selected]
        kind = geometry["boundary_kind"][selected]
        crest = geometry["boundary_segment_crest_relative_m"][selected].copy()
        opened = kind!=0
        crest[opened] = np.maximum(crest[opened],geometry["boundary_crest_m"][selected][opened,None]-datum)
        h = np.maximum(stage[ids,None]-crest,0)
        first = np.column_stack((h.ravel(),(h[:,:,None]*velocity[ids,None,:]).reshape(-1,2)))
        ghost = first.copy()
        ghost[:,direction+1] *= -1
        opened_segments = np.repeat(opened,crest.shape[1])
        outside = np.where(kind[:,None]==1,crest,tailwater[selected,None]-datum)
        ghost[opened_segments,0] = np.maximum(outside-crest,0).ravel()[opened_segments]
        ghost[opened_segments,1:] = 0
        normal = np.repeat(signs[selected],crest.shape[1])
        first[:,direction+1] *= normal
        ghost[:,direction+1] *= normal
        flux,_,_ = face_flux(first,ghost,crest.ravel(),crest.ravel(),g,direction)
        flux[:,direction+1] *= normal
        exterior[selected] = flux.reshape(*crest.shape,3).mean(axis=1)
        np.add.at(source[:,direction+1],ids,signs[selected]*.5*g*(h**2).mean(axis=1)/spacing)
    outgoing = np.bincount(left,weights=np.maximum(internal[:,0],0)*spacing,minlength=len(state))
    outgoing += np.bincount(right,weights=np.maximum(-internal[:,0],0)*spacing,minlength=len(state))
    outgoing += np.bincount(cells,weights=np.maximum(exterior[:,0],0)*spacing,minlength=len(state))
    scale = np.ones(len(state))
    limited = outgoing*dt>state[:,0]*spacing**2
    scale[limited] = state[limited,0]*spacing**2/(outgoing[limited]*dt)*(1-1e-12)
    internal *= np.where(internal[:,0]>=0,scale[left],scale[right])[:,None]
    exterior *= np.where(exterior[:,0]>=0,scale[cells],1.)[:,None]
    rhs = source.copy()
    np.add.at(rhs,left,-internal/spacing)
    np.add.at(rhs,right,internal/spacing)
    np.add.at(rhs,cells,-exterior/spacing)
    return rhs,internal,exterior,source


def audit_momentum(packet,metadata,geometry,spacing,budget,forcing,tailwater):
    before,predictor,after = (packet[name] for name in ("state_before","state_predictor","state_after"))
    dt = metadata["dt_s"]
    model = metadata.get("hydraulic_model")
    if model not in (MODEL,MODEL_V2,MODEL_V3,MODEL_V7):
        raise ValueError("independent shallow model unsupported")
    g = budget["gravity_m_s2"]
    assert_close(packet["forcing_m3_s"],forcing,"forcing")
    assert_close(packet["tailwater_m"],tailwater,"tailwater")
    if not 0<dt<=budget["max_dt_s"] or any(np.any(state[:,0]<0) for state in (before,predictor,after)):
        raise ValueError("independent shallow sampled time/depth mismatch")
    velocity = np.divide(before[:,1:],before[:,0,None],out=np.zeros_like(before[:,1:]),where=before[:,0,None]>0)
    speed = float((abs(velocity).sum(axis=1)+2*np.sqrt(g*before[:,0])).max(initial=0))
    if model in (MODEL_V3,MODEL_V7):
        stages = storage_stage(before[:,0],geometry["subcell_bed_relative_m"])
        deepest = np.maximum(stages-geometry["subcell_bed_relative_m"][:,0],0)
        speed = max(speed,float((abs(velocity).sum(axis=1)+2*np.sqrt(g*deepest)).max(initial=0)))
    external_bed = np.maximum(geometry["H2_m"].ravel()[geometry["boundary_cell"]],geometry["boundary_crest_m"])
    if model in (MODEL_V3,MODEL_V7):
        external_bed = np.maximum(geometry["boundary_segment_crest_relative_m"].min(axis=1)+geometry["hydraulic_datum_m"],geometry["boundary_crest_m"])
    exterior_stage = np.where(geometry["boundary_kind"]==1,external_bed,tailwater)
    external_depth = np.maximum(exterior_stage-external_bed,0)
    speed = max(speed,float((2*np.sqrt(g*external_depth[geometry["boundary_kind"]!=0])).max(initial=0)))
    if dt>budget["inertial_cfl"]*spacing/max(speed,1e-12)+1e-12:
        raise ValueError("independent shallow advective CFL mismatch")
    equations = []
    for number,state in ((1,before),(2,predictor)):
        rhs,internal,external,source = physical_witness(state,geometry,spacing,g,tailwater,dt,model=model)
        for name,expected in (("internal_flux",internal),("boundary_flux",external),("bed_source",source)):
            assert_close(packet[f"rk{number}_"+name],expected,f"RK{number} "+name)
        rhs[:,0] += forcing/spacing**2
        equations.append(rhs)
    assert_close(predictor,before+dt*equations[0],"RK predictor")
    undamped = .5*before+.5*(predictor+dt*equations[1])
    expected = undamped.copy()
    wet = expected[:,0]>0
    if model==MODEL_V7:
        damping,factor = canonical_manning(undamped,geometry["subcell_bed_relative_m"],dt,g,budget["roughness_s_m_third"])
        assert_close(packet["manning_inverse_depth_third_mean"],factor,"canonical wet-subcell inverse-depth integral")
        expected[:,1:] *= damping[:,None]
    else:
        hpower = expected[wet,0]**(7/3)
        denominator = hpower+dt*g*budget["roughness_s_m_third"]**2*np.linalg.norm(expected[wet,1:],axis=1)
        expected[wet,1:] = np.divide(expected[wet,1:]*hpower[:,None],denominator[:,None],out=np.zeros_like(expected[wet,1:]),where=denominator[:,None]>0)
    assert_close(after,expected,"RK endpoint and drag")
    assert_close(packet["manning_momentum_change"],expected[:,1:]-undamped[:,1:],"drag witness")
    return dict(physical_hll_flux_verified=True,side_pressure_source_verified=True,reflect_open_crest_verified=True,
                donor_limiter_verified=True,ssprk2_and_manning_verified=True,advective_cfl_verified=True,
                manning_equation_verified="canonical wet-subcell integrated implicit Manning" if model==MODEL_V7 else "legacy coarse mean depth implicit Manning",
                canonical_subgrid_manning_consistency_verified=True if model==MODEL_V7 else False if model==MODEL_V3 else None)
