"""Conservative reduced storage-graph primitives for tidal delta experiments.

Volumes are m3, beds/stages metres, times physical seconds. Optional face
sections use Manning and weir closures; legacy faces use linear conductance.
No momentum is stored.
This module is experimental and does not itself prepare a regional product.
"""
from dataclasses import dataclass
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters


@dataclass(frozen=True)
class Geometry:
    area_m2: np.ndarray
    floor_m: np.ndarray
    left: np.ndarray
    right: np.ndarray
    conductance_m2_s: np.ndarray
    boundary_cell: np.ndarray
    boundary_conductance_m2_s: np.ndarray
    porosity: float = .4
    river_faces: np.ndarray = None
    river_width_m: np.ndarray = None
    river_distance_m: np.ndarray = None
    river_roughness: float = .035
    bank_faces: np.ndarray = None
    bank_length_m: np.ndarray = None
    coast_faces: np.ndarray = None
    coast_width_m: np.ndarray = None
    coast_distance_m: float = 1.
    coast_roughness: float = .04


@dataclass
class State:
    time_s: float
    water_m3: np.ndarray
    bed_solid_m3: np.ndarray
    mobile_solid_m3: np.ndarray
    sea_water_in_m3: float = 0.
    sea_water_out_m3: float = 0.
    sea_solid_out_m3: float = 0.
    source_water_m3: float = 0.
    source_solid_m3: float = 0.
    wave_bed_transfer_m3: float = 0.


def tide_stage(time_s, m2_amplitude_m=1., s2_amplitude_m=.35):
    """Uncalibrated M2/S2 sea stage; phase is absolute physical time."""
    return (m2_amplitude_m * np.sin(2*np.pi*time_s/(12.4206*3600))
            + s2_amplitude_m * np.sin(2*np.pi*time_s/(12*3600)))


def bed_elevation(geometry, state):
    return geometry.floor_m + state.bed_solid_m3 / ((1-geometry.porosity)*geometry.area_m2)


def step(geometry, state, dt_s, sea_stage_m, source_cell, source_water_m3_s,
         source_solid_m3_s, material=MaterialParameters(porosity=.4),
         stage_override=None, face_crest_offset=None, storage_area=None,
         crest_available=None):
    """Advance conservative graph storage; clear water enters from sea.

    River faces use frozen Manning secants and bank faces use weir secants,
    coupled through implicit tangent storage. Optional coastal Manning faces
    retain the explicit stability bound.
    A caller supplying crest_available bounds withdrawal above each sill.
    Bed material exchanges with a well-mixed mobile stock. Time is seconds.
    """
    g, s = geometry, state
    if dt_s <= 0 or source_water_m3_s < 0 or source_solid_m3_s < 0:
        raise ValueError('invalid interval or source')
    bed = bed_elevation(g, s)
    stage = bed + s.water_m3/g.area_m2 if stage_override is None else stage_override
    left, right, bc = g.left, g.right, g.boundary_cell
    crest = np.maximum(bed[left], bed[right])
    if face_crest_offset is not None:
        crest = crest + face_crest_offset
    head = stage[left] - stage[right]
    q = g.conductance_m2_s * head
    q = np.where(np.maximum(stage[left], stage[right]) > crest, q, 0.)
    # Coarse coastal faces use a Manning section based on the actual common
    # valid coast edge and water above its sill. They remain explicit and use
    # the existing storage stability limit below.
    if g.coast_faces is not None:
        cf = g.coast_faces
        cl, cr = left[cf], right[cf]
        depth = np.maximum(np.maximum(stage[cl], stage[cr])-crest[cf], 0.)
        area = g.coast_width_m*depth
        perimeter = g.coast_width_m+2*depth
        radius = np.divide(area, perimeter, out=np.zeros_like(area), where=perimeter > 0)
        slope_head = np.maximum(stage[cl], crest[cf])-np.maximum(stage[cr], crest[cf])
        q[cf] = area*radius**(2/3)/g.coast_roughness * np.sign(slope_head)*np.sqrt(np.abs(slope_head)/g.coast_distance_m)
    bq = g.boundary_conductance_m2_s * (stage[bc]-sea_stage_m)
    bq = np.where(np.maximum(stage[bc], sea_stage_m) > bed[bc], bq, 0.)
    # River friction and lateral overflow are linearized together. Bank
    # heads are measured above the actual crest, including when one side is
    # dry. Offsets freeze that piecewise relation for this interval.
    river = g.river_faces if g.river_faces is not None else np.empty(0, int)
    bank = g.bank_faces if g.bank_faces is not None else np.empty(0, int)
    implicit_faces = np.r_[river, bank]
    if len(implicit_faces):
        if storage_area is None:
            raise ValueError('implicit exchange requires wetted storage area')
        rl, rr = left[river], right[river]
        depth = np.maximum(np.maximum(stage[rl], stage[rr])-crest[river], 0.)
        width = g.river_width_m if len(river) else np.empty(0)
        section = width * depth
        radius = np.divide(section, width+2*depth, out=np.zeros_like(depth), where=width+2*depth > 0)
        conveyance = section * radius**(2/3) / g.river_roughness
        distance = g.river_distance_m if len(river) else np.empty(0)
        river_secant = conveyance / np.sqrt(distance * np.maximum(np.abs(head[river]), 1e-4))
        bl, br = left[bank], right[bank]
        hl = np.maximum(stage[bl]-crest[bank], 0.)
        hr = np.maximum(stage[br]-crest[bank], 0.)
        bank_head = hl-hr
        # One effective overflow crest per reach. A submerged tailwater
        # reduces exchange through the difference of the two weir powers.
        bank_length = g.bank_length_m if len(bank) else np.empty(0)
        bank_secant = np.divide(1.7*bank_length*(hl**1.5-hr**1.5), bank_head,
                                 out=np.zeros_like(bank_head), where=np.abs(bank_head) > 1e-12)
        secant = np.r_[river_secant, bank_secant]
        left_offset = np.r_[np.zeros(len(river)), np.maximum(crest[bank]-stage[bl], 0.)]
        right_offset = np.r_[np.zeros(len(river)), np.maximum(crest[bank]-stage[br], 0.)]
        fl, fr = left[implicit_faces], right[implicit_faces]
        nodes, inverse = np.unique(np.r_[fl, fr], return_inverse=True)
        il, ir = np.split(inverse, 2)
        area = storage_area[nodes]
        diag = area.copy()
        np.add.at(diag, il, dt_s*secant)
        np.add.at(diag, ir, dt_s*secant)
        k = len(nodes)
        matrix = coo_matrix((np.r_[diag, -dt_s*secant, -dt_s*secant],
                             (np.r_[np.arange(k), il, ir], np.r_[np.arange(k), ir, il])),
                            shape=(k, k)).tocsc()
        rhs = area*stage[nodes]
        correction = dt_s*secant*(left_offset-right_offset)
        np.add.at(rhs, il, -correction)
        np.add.at(rhs, ir, correction)
        implicit_stage = spsolve(matrix, rhs)
        proposed = secant*(implicit_stage[il]+left_offset-implicit_stage[ir]-right_offset)
        old_head = np.r_[head[river], bank_head]
        q[implicit_faces] = np.where(proposed*old_head > 0, proposed, 0.)
    if storage_area is not None:
        capacity = .2*np.abs(head)/(1/storage_area[left]+1/storage_area[right])
        capped = np.sign(q)*np.minimum(np.abs(q),capacity/dt_s)
        capped[implicit_faces] = q[implicit_faces]
        q = capped
        limit = .2*np.abs(stage[bc]-sea_stage_m)*storage_area[bc]/dt_s
        bq = np.sign(bq)*np.minimum(np.abs(bq),limit)
    donor = np.where(q >= 0, left, right)
    receiver = np.where(q >= 0, right, left)
    demand = np.bincount(donor, weights=np.abs(q)*dt_s, minlength=len(bed)).astype(float)
    demand += np.bincount(bc, weights=np.maximum(bq, 0)*dt_s, minlength=len(bed))
    scale = np.minimum(1., np.divide(np.maximum(s.water_m3, 0.), demand, out=np.ones_like(demand), where=demand > 0))
    face_scale = scale[donor].copy()
    boundary_scale = scale[bc].copy()
    if crest_available is not None:
        # Allocate each crest its proportional share of the donor's water
        # above that crest. A high sill must not suppress a separate low outlet.
        flowing = np.abs(q) > 0
        face_available = crest_available(donor[flowing], crest[flowing])
        share = np.divide(face_available, demand[donor[flowing]],
                          out=np.ones_like(face_available), where=demand[donor[flowing]] > 0)
        face_scale[flowing] = np.minimum(face_scale[flowing], np.maximum(share, 0.))
        boundary_out = bq > 0
        boundary_available = crest_available(bc[boundary_out], bed[bc[boundary_out]])
        share = np.divide(boundary_available, demand[bc[boundary_out]],
                          out=np.ones_like(boundary_available), where=demand[bc[boundary_out]] > 0)
        boundary_scale[boundary_out] = np.minimum(boundary_scale[boundary_out], np.maximum(share, 0.))
    flow = np.abs(q)*dt_s*face_scale
    out = np.maximum(bq, 0)*dt_s*boundary_scale
    incoming = np.maximum(-bq, 0)*dt_s
    concentration = np.divide(s.mobile_solid_m3, s.water_m3, out=np.zeros_like(bed), where=s.water_m3 > 0)
    solid = flow*concentration[donor]
    exported = out*concentration[bc]
    dv = (np.bincount(receiver, weights=flow, minlength=len(bed))-np.bincount(donor, weights=flow, minlength=len(bed))).astype(float)
    dv += np.bincount(bc, weights=incoming-out, minlength=len(bed))
    ds = (np.bincount(receiver, weights=solid, minlength=len(bed))-np.bincount(donor, weights=solid, minlength=len(bed))).astype(float)
    ds -= np.bincount(bc, weights=exported, minlength=len(bed))
    dv[source_cell] += source_water_m3_s*dt_s
    ds[source_cell] += source_solid_m3_s*dt_s
    s.water_m3 += dv
    s.mobile_solid_m3 += ds
    # Head gradient gives a deliberately reduced friction-shear proxy.  The
    # sediment exchange parameters are those of the existing sediment module.
    gradient = np.abs(head) / np.maximum(np.sqrt(g.area_m2[left])+np.sqrt(g.area_m2[right]), 1.)
    shear_face = 1000*9.81*np.maximum(np.maximum(stage[left], stage[right])-crest, 0)*gradient
    shear = np.zeros(len(bed))
    np.maximum.at(shear, left, shear_face)
    np.maximum.at(shear, right, shear_face)
    erosion = np.minimum(s.bed_solid_m3, material.sediment_erodibility_m_s_pa * .001 * np.maximum(shear-material.sediment_critical_shear_pa, 0)*g.area_m2*(1-g.porosity)*dt_s)
    # A finite concentration ceiling avoids mobilizing an implausible slurry.
    erosion = np.minimum(erosion, np.maximum(.002*s.water_m3-s.mobile_solid_m3, 0.))
    depth = s.water_m3/g.area_m2
    settling_fraction = 1-np.exp(-material.settling_velocity_m_s*dt_s/np.maximum(depth, .001))
    deposition = s.mobile_solid_m3*settling_fraction
    s.bed_solid_m3 += deposition-erosion
    s.mobile_solid_m3 += erosion-deposition
    s.time_s += dt_s
    s.sea_water_in_m3 += incoming.sum()
    s.sea_water_out_m3 += out.sum()
    s.sea_solid_out_m3 += exported.sum()
    s.source_water_m3 += source_water_m3_s*dt_s
    s.source_solid_m3 += source_solid_m3_s*dt_s
    return {'internal_water_m3': np.sign(q)*flow, 'boundary_water_m3': out-incoming,
            'internal_solid_m3': np.sign(q)*solid, 'boundary_solid_m3': exported}


def save_checkpoint(path, state):
    """Save complete evolving state, including absolute tidal phase and ledgers."""
    np.savez_compressed(path, **vars(state))


def load_checkpoint(path):
    """Load an existing checkpoint; no source preparation or simulation occurs."""
    with np.load(path, allow_pickle=False) as saved:
        return State(**{name: (saved[name].copy() if saved[name].ndim else float(saved[name]))
                        for name in State.__dataclass_fields__ if name in saved})
