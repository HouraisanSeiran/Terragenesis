"""New physical hypothesis: permeable surface infiltration and unchanged D4 transport."""

import math
import numpy as np
from numba import njit
from terrain_pipeline.common_infra import identity, readonly
from terrain_pipeline.td_basin_forcing_v10 import advance_forcing
from terrain_pipeline.td_basin_transport_v6 import _compiled_exchange, validate_cfl
from terrain_pipeline.td_basin_storage_v10_io import PROFILE, STATES, ERRORS, LEDGERS, FLUX, validate_storage, validate_checkpoint


@njit(cache=True)
def advance_hour(states, errors, rain, bed, faces, boundary, widths, receiver, spacing, step, count, runoff):
    ledger = np.zeros((13, len(bed)))
    forward = np.zeros(len(faces)); reverse = np.zeros(len(faces))
    forward_s = np.zeros(len(faces)); reverse_s = np.zeros(len(faces))
    routed = np.zeros(len(bed)); duration = np.zeros(len(bed))
    empty = np.empty(0, np.int64)
    area = spacing**2
    for substep in range(count):
        for half in range(2):
            capacity = np.minimum(runoff[0]*step/7200, np.maximum(0., runoff[1]-states[1]))
            result = advance_forcing(states, errors, rain, step/2, 1, runoff, .15)
            states, errors = result[0], result[1]
            ledger[:8] += result[2]*area/1000
            ledger[12] += capacity*area/1000
            if half == 0:
                exchange = _compiled_exchange(states[0], bed, faces, boundary, widths, spacing, step, .6, empty, empty)
                states[0] = exchange[0]
                errors[0] = 0
                forward += exchange[1]; reverse += exchange[2]
                forward_s += exchange[4]; reverse_s += exchange[5]
                for face in range(len(faces)):
                    first, second = faces[face]
                    signed = exchange[1][face]-exchange[2][face]
                    ledger[8, first] -= signed; ledger[8, second] += signed
                    if receiver[first] == second:
                        routed[first] += exchange[1][face]; duration[first] += exchange[4][face]
                    if receiver[second] == first:
                        routed[second] += exchange[2][face]; duration[second] += exchange[5][face]
                for index in range(len(boundary)):
                    ledger[9, boundary[index]] += exchange[3][index]
    return states, errors, ledger, forward, reverse, forward_s, reverse_s, routed, duration


def simulate_hour(hierarchy, full_rain_mm_h, *, substep_s, checkpoint=None):
    topology = hierarchy['arrays']
    bed = topology['height_m'].ravel()
    valid = topology['valid_mask'].ravel()
    if topology['protected_mask'].any():
        raise ValueError('v10 protected cells unsupported')
    full = np.asarray(full_rain_mm_h, dtype=np.float64)
    shape = topology['height_m'].shape
    if full.shape != (24, *shape) or full.size > 4000000 or not np.isfinite(full).all() or np.any((full < 0) | (full > 1e6)):
        raise ValueError('v10 fixed spatial 24h forcing invalid')
    if np.any(full[:, ~topology['valid_mask']] != 0):
        raise ValueError('v10 rainfall on unknown cells forbidden')
    full = full.copy()
    forcing_id = identity({'rain_mm_h': full}, {'dt_s': 3600.})
    if type(substep_s) not in (float, int) or not math.isfinite(substep_s) or substep_s <= 0 or int(3600/substep_s)*substep_s != 3600:
        raise ValueError('v10 exact integer hourly substeps required')
    count = int(3600/substep_s)
    faces = topology['face_cells']
    if count > 100000 or count*len(faces) > 6000000000:
        raise ValueError('v10 chunk work budget exceeded')
    spacing = hierarchy['metadata']['spacing_m']
    boundary = topology['boundary_cells']
    rows, columns = np.divmod(boundary, shape[1])
    widths = spacing*((rows == 0).astype(int)+(rows == shape[0]-1)+(columns == 0)+(columns == shape[1]-1))
    cfl = validate_cfl(faces, boundary, widths, spacing, substep_s, .6, len(bed))
    runoff = np.array([15.,150.,.15,1.,3600.,259200.])
    physical = {'substep_s':substep_s,'runoff':[15.,150.,.15,1.,3600.,259200.],
        'face_conductance_m_s':.6,'surface_evaporation_mm_h':.15,
        'forcing_profile':'v10-unified-rain-surface-infiltration-experimental-v1'}
    runoff_parameters = {'infiltration_capacity_mm_h':15.,'soil_capacity_mm':150.,
        'potential_et_mm_h':.15,'percolation_mm_h':1.,'fast_tau_s':3600.,'slow_tau_s':259200.,
        'initial_soil_mm':30.,'initial_fast_mm':0.,'initial_slow_mm':0.}
    states = np.zeros((4,len(bed))); states[1, valid] = 30.
    errors = np.zeros_like(states)
    offset = 0
    previous = {key: np.zeros(len(faces) if key.startswith(('face_', 'active_')) else len(bed)) for key in FLUX}
    if checkpoint is not None:
        validate_checkpoint(checkpoint)
        metadata = checkpoint['metadata']
        if metadata['hierarchy_identity'] != hierarchy['identity_sha256'] or metadata['forcing_identity'] != forcing_id or metadata['parameters'] != physical or metadata.get('runoff_parameters') != runoff_parameters or metadata['cells'] != len(bed) or metadata['faces'] != len(faces) or metadata['spacing_m'] != spacing or metadata['origin_m_xz'] != hierarchy['metadata']['origin_m_xz']:
            raise ValueError('v10 checkpoint topology/forcing/config mismatch')
        offset = int(metadata['end_s']/3600)
        states = np.vstack([checkpoint['arrays'][key] for key in STATES]).copy()
        errors = np.vstack([checkpoint['arrays'][key] for key in ERRORS]).copy()
        if np.any(states[1] > runoff[1]):
            raise ValueError('v10 checkpoint soil exceeds capacity')
        previous = {key: checkpoint['arrays']['cumulative_'+key] for key in FLUX}
        if np.any(states[:, ~valid] != 0) or np.any(errors[:, ~valid] != 0) or any(np.any(previous[key][~valid] != 0) for key in ('routed_volume_m3','wet_duration_s')):
            raise ValueError('v10 unknown checkpoint inventories/evidence forbidden')
    if offset >= 24:
        raise ValueError('v10 forcing plan exhausted')
    initial = states.copy()
    rain = full[offset].ravel()
    result = advance_hour(states, errors, rain, bed, faces, boundary, widths, topology['receiver'], spacing, substep_s, count, runoff)
    states, errors, ledger = result[:3]
    ledger[12, ~valid] = 0
    area = spacing**2
    before = area*(initial[0]+initial[1:].sum(axis=0)/1000)
    after = area*(states[0]+states[1:].sum(axis=0)/1000)
    ledger[10] = after-before
    ledger[11] = ledger[0]+ledger[8]-ledger[4]-ledger[5]-ledger[9]-ledger[10]
    arrays = {key: np.vstack((initial[index],states[index])) for index,key in enumerate(STATES)}
    arrays.update({key: ledger[index:index+1] for index,key in enumerate(LEDGERS)})
    arrays.update({key: value for key,value in zip(FLUX,result[3:])})
    arrays.update({key: topology[key] for key in ('height_m','valid_mask','face_cells','receiver','boundary_cells')})
    arrays.update(boundary_width_m=widths, rain_mm_h=rain[None,:])
    metadata = {'schema':'td-v10-hour-page-v1','profile':PROFILE,'cells':len(bed),'faces':len(faces),
        'substeps':count,'substep_s':substep_s,'dt_s':3600.,'forcing_hour_offset':offset,
        'start_s':offset*3600.,'end_s':(offset+1)*3600.,'spacing_m':spacing,'positivity_cfl':cfl,
        'parameters':physical,'origin_m_xz':hierarchy['metadata']['origin_m_xz'],
        'runoff_parameters':runoff_parameters,
        'forcing_identity':forcing_id,'hierarchy_identity':hierarchy['identity_sha256'],
        'physics':'all valid cells experimentally permeable; rain first accesses finite capacity, remaining capacity draws surface water; rain excess enters unchanged fast store; ordered ET/percolation; no wet bypass',
        'permanent_lake_impermeability':'not modelled; requires independent material mask',
        'activity_semantics':'SSP-RK2 stage quadrature of actual signed exchange; not exact event duration',
        'hydraulic_ready':False,'transient_converged':False,'publishable':False}
    page = {'arrays':{key:readonly(value) for key,value in arrays.items()},'metadata':metadata,'identity_sha256':identity(arrays,metadata)}
    validate_storage(page)
    cp_arrays = {key:states[index] for index,key in enumerate(STATES)}
    cp_arrays.update({key:errors[index] for index,key in enumerate(ERRORS)})
    cp_arrays.update({'cumulative_'+key:previous[key]+arrays[key] for key in FLUX})
    cp_meta = {**metadata,'schema':'td-v10-hour-checkpoint-v1','last_page_identity':page['identity_sha256']}
    cp = {'arrays':{key:readonly(value) for key,value in cp_arrays.items()},'metadata':cp_meta,'identity_sha256':identity(cp_arrays,cp_meta)}
    validate_checkpoint(cp)
    return {'storage':page,'checkpoint':cp}
