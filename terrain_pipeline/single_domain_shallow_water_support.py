"""Pure hydrostatic HLL flux equations for saved shallow-water evidence."""

import numpy as np

MODEL = "single-domain-hydrostatic-HLL-SSPRK2-v1"


def minmod(first, second):
    return np.where(first*second > 0, np.sign(first)*np.minimum(abs(first), abs(second)), 0.)


def hydrostatic_hll(left, right, bed_left, bed_right, *, gravity, axis):
    """Audusse hydrostatic reconstruction; side-specific pressure corrections.

    States are [h,hu,hv] and fluxes remain global [mass,xmomentum,zmomentum].
    This first-order source-balanced reference deliberately avoids unbalanced
    MUSCL bed terms. Higher spatial order requires a separate algorithm version.
    """
    hleft, hright = left[:, 0], right[:, 0]
    crest = np.maximum(bed_left, bed_right)
    hl = np.maximum(hleft+bed_left-crest, 0.)
    hr = np.maximum(hright+bed_right-crest, 0.)
    vl = np.divide(left[:, 1:], hleft[:, None], out=np.zeros_like(left[:, 1:]), where=hleft[:, None] > 0)
    vr = np.divide(right[:, 1:], hright[:, None], out=np.zeros_like(right[:, 1:]), where=hright[:, None] > 0)
    reconstructed_left = np.column_stack((hl, hl[:, None]*vl))
    reconstructed_right = np.column_stack((hr, hr[:, None]*vr))
    ul, ur = vl[:, axis], vr[:, axis]
    cl, cr = np.sqrt(gravity*hl), np.sqrt(gravity*hr)
    sl = np.minimum(ul-cl, ur-cr)
    sr = np.maximum(ul+cl, ur+cr)
    fl = reconstructed_left*ul[:, None]
    fr = reconstructed_right*ur[:, None]
    fl[:, axis+1] += .5*gravity*hl**2
    fr[:, axis+1] += .5*gravity*hr**2
    denominator = sr-sl
    flux = np.divide(sr[:, None]*fl-sl[:, None]*fr+(sl*sr)[:, None]*(reconstructed_right-reconstructed_left),
                     denominator[:, None], out=np.zeros_like(fl), where=denominator[:, None] > 0)
    flux[sl >= 0] = fl[sl >= 0]
    flux[sr <= 0] = fr[sr <= 0]
    correction_left = .5*gravity*(hleft**2-hl**2)
    correction_right = .5*gravity*(hright**2-hr**2)
    return flux, correction_left, correction_right, np.maximum(abs(sl),abs(sr))


def shallow_water_rhs(state, bed, *, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    """Global conservative face flux, well-balanced source, and donor limiter."""
    rows, columns = bed.shape
    count = rows*columns
    grid = np.arange(count).reshape(rows,columns)
    left = np.r_[grid[:,:-1].ravel(),grid[:-1,:].ravel()]
    right = np.r_[grid[:,1:].ravel(),grid[1:,:].ravel()]
    axis = np.r_[np.zeros(rows*(columns-1),np.int64),np.ones((rows-1)*columns,np.int64)]
    exterior = np.r_[grid[:,0],grid[:,-1],grid[0],grid[-1]]
    normal_axis = np.r_[np.zeros(2*rows,np.int64),np.ones(2*columns,np.int64)]
    sign = np.r_[-np.ones(rows),np.ones(rows),-np.ones(columns),np.ones(columns)]
    flatbed = bed.ravel()
    flux = np.zeros((len(left),3))
    correction_l, correction_r = np.zeros(len(left)),np.zeros(len(left))
    waves = np.zeros(len(left))
    for direction in (0,1):
        selection = axis == direction
        f,cl,cr,speed = hydrostatic_hll(state[left[selection]],state[right[selection]],flatbed[left[selection]],flatbed[right[selection]],gravity=gravity,axis=direction)
        flux[selection],correction_l[selection],correction_r[selection],waves[selection] = f,cl,cr,speed
    ghost = state[exterior].copy()
    boundary_bed=flatbed[exterior].copy()
    if boundary_crest is not None:
        boundary_bed=np.maximum(boundary_bed,boundary_crest)
    for direction in (0,1):
        selected = normal_axis == direction
        closed = selected&(boundary_kind == 0)
        ghost[closed,direction+1] *= -1
    opened = boundary_kind != 0
    exterior_stage=np.where(boundary_kind == 1,boundary_bed,tailwater)
    ghost[opened,0] = np.maximum(exterior_stage[opened]-boundary_bed[opened],0.)
    ghost[opened,1:] = 0.
    boundary_flux = np.zeros_like(ghost)
    boundary_pressure=np.zeros((len(exterior),3))
    for direction in (0,1):
        selection = normal_axis == direction
        cells = exterior[selection]
        first = state[cells].copy()
        second = ghost[selection].copy()
        signs = sign[selection]
        first[:,direction+1] *= signs
        second[:,direction+1] *= signs
        f,cl,_,speed = hydrostatic_hll(first,second,flatbed[cells],boundary_bed[selection],gravity=gravity,axis=direction)
        f[:,direction+1] *= signs
        boundary_pressure[selection,direction+1]=-cl*signs/spacing
        boundary_flux[selection] = f
        waves = np.r_[waves,speed]
    outgoing = np.bincount(left,weights=np.maximum(flux[:,0],0)*spacing,minlength=count)
    outgoing += np.bincount(right,weights=np.maximum(-flux[:,0],0)*spacing,minlength=count)
    outgoing += np.bincount(exterior,weights=np.maximum(boundary_flux[:,0],0)*spacing,minlength=count)
    scales = np.ones(count)
    limited = outgoing*dt > state[:,0]*spacing**2
    scales[limited] = state[limited,0]*spacing**2/(dt*outgoing[limited])*(1-1e-12)
    face_scale = np.where(flux[:,0] >= 0,scales[left],scales[right])
    boundary_scale = np.where(boundary_flux[:,0] >= 0,scales[exterior],1.)
    # Scale transported mass and advective momentum together. Hydrostatic
    # pressure corrections remain source terms, retaining a resting lake.
    flux *= face_scale[:,None]
    boundary_flux *= boundary_scale[:,None]
    rhs = np.zeros_like(state)
    for component in range(3):
        np.add.at(rhs[:,component],left,-flux[:,component]/spacing)
        np.add.at(rhs[:,component],right,flux[:,component]/spacing)
        np.add.at(rhs[:,component],exterior,-boundary_flux[:,component]/spacing)
    pressure = np.zeros_like(state)
    np.add.at(pressure,(left,axis+1),-correction_l/spacing)
    np.add.at(pressure,(right,axis+1),correction_r/spacing)
    for component in (1,2):
        np.add.at(pressure[:,component],exterior,boundary_pressure[:,component])
    rhs += pressure
    return rhs, dict(internal_flux=flux,boundary_flux=boundary_flux,bed_source=pressure,
                     maximum_wave_speed=float(waves.max(initial=0)),minimum_limiter_factor=float(scales.min(initial=1)),
                     limited_donors=int(limited.sum()))
