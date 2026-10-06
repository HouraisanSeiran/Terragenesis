"""Dry-drain, source-isolated pulse experiment on the unchanged task10 bed."""

import math

import numpy as np

from terrain_pipeline.td_entry_shallow_water import finish, run_case

ORDINARY_Q_M3_S = .006926036196388915
INJECTION_NODE = 'cell:61625'
FLAGS = dict(hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
             new_bed_hydrology_verified=False, time_refinement_verified=False,
             upstream_pulse_to_lake_verified=False)


def build_dry_drain_geometry(carrier, parent_geometry):
    bed = carrier['arrays']['derived_bed_m']
    old = parent_geometry['arrays']
    if (parent_geometry['metadata']['bed_identity_sha256'] != carrier['identity_sha256'] or
            not np.array_equal(old['H2_m'], bed) or
            not np.array_equal(old['boundary_crest_m'], bed.ravel()[old['boundary_cell']]) or
            not np.isin(old['boundary_kind'], (0, 2)).all() or not np.any(old['boundary_kind'] == 2)):
        raise ValueError('parent_geometry_bed_crest_or_kind_mismatch')
    arrays = {key: value.copy() for key, value in old.items()}
    arrays['boundary_kind'][old['boundary_kind'] == 2] = 1
    metadata = dict(parent_geometry['metadata'], schema='td-entry-pulse-dry-drain-geometry-v1',
                    parent_geometry_identity_sha256=parent_geometry['identity_sha256'],
                    scope='unchanged task10 D4 faces and bed; only previous downstream stage faces become dry engineering drains; all other faces closed',
                    source_isolation='kind1 ghost stage is actual boundary bed, no prescribed lake stage', **FLAGS)
    return finish(arrays, metadata)


def build_pulse_forcing(carrier, geometry, *, duration_s=240., pulse_s=120., interval_s=10.):
    meta, arrays = carrier['metadata'], carrier['arrays']
    if meta['injection_node_id'] != INJECTION_NODE or meta['ordinary_q_m3_s'] != ORDINARY_Q_M3_S:
        raise ValueError('exact_upstream_node_Q_binding_required')
    if (not all(math.isfinite(value) for value in (duration_s, pulse_s, interval_s)) or
            not 0 < pulse_s < duration_s <= 240 or interval_s <= 0 or
            not math.isclose(duration_s/interval_s, round(duration_s/interval_s), abs_tol=1e-10) or
            not math.isclose(pulse_s/interval_s, round(pulse_s/interval_s), abs_tol=1e-10)):
        raise ValueError('invalid_pulse_schedule')
    mask = arrays['forcing_mask']
    if (mask.dtype != bool or not mask.any() or mask.shape != arrays['derived_bed_m'].shape or
            not arrays['overlay_mask'][mask].all() or arrays['wet_protected_mask'][mask].any()):
        raise ValueError('injection_not_actual_dry_accepted_upstream_support')
    kinds = geometry['arrays']['boundary_kind']
    if not np.isin(kinds, (0, 1)).all() or not np.any(kinds == 1):
        raise ValueError('source_isolation_requires_closed_or_dry_drain_only')
    count = round(duration_s/interval_s)
    times = np.arange(count+1, dtype=np.float64)*interval_s
    injection = mask.ravel().astype(np.float64)*ORDINARY_Q_M3_S/mask.sum()
    source = (times[:-1] < pulse_s)[None, :, None]*injection[None, None, :]
    boundary = np.broadcast_to(geometry['arrays']['boundary_crest_m'], (1, count, len(kinds))).copy()
    initial = np.zeros((1, *mask.shape), np.float64)
    return finish(dict(time_s=times, forcing_m3_s=source, boundary_stage_m=boundary, initial_depth_m=initial),
                  dict(schema='td-entry-pulse-isolated-forcing-v1', case_names=['isolated-normal-pulse-retreat'],
                       grid_shape=list(mask.shape), forcing_array_axes='case, interval, flattened_row_major_cell',
                       duration_s=duration_s, pulse_s=pulse_s, pulse_duration_s=pulse_s, interval_s=interval_s,
                       geometry_identity_sha256=geometry['identity_sha256'], bed_identity_sha256=carrier['identity_sha256'],
                       injection_node_id=INJECTION_NODE, ordinary_q_m3_s=ORDINARY_Q_M3_S,
                       planned_supply_volume_m3=ORDINARY_Q_M3_S*pulse_s,
                       initial_semantics='all dry, zero momentum; new event from time zero, no continuation',
                       forcing_semantics='exact task10 injection mask and cell61625 ordinary Q; no rainfall or momentum source',
                       boundary_semantics='dry engineering drainage only; boundary stage array equals actual bed crest, ignored by closed sides',
                       attribution_requirement='completed raw ledger boundary_input_m3 must equal zero exactly', **FLAGS))


def validate_experiment(carrier, geometry, forcing):
    bed, meta = carrier['arrays']['derived_bed_m'], forcing['metadata']
    if (meta['bed_identity_sha256'] != carrier['identity_sha256'] or
            meta['geometry_identity_sha256'] != geometry['identity_sha256'] or
            not np.array_equal(geometry['arrays']['H2_m'], bed) or
            not np.array_equal(geometry['arrays']['boundary_crest_m'], bed.ravel()[geometry['arrays']['boundary_cell']])):
        raise ValueError('experiment_bed_or_geometry_linkage')
    expected = build_pulse_forcing(carrier, geometry, duration_s=meta['duration_s'], pulse_s=meta['pulse_s'], interval_s=meta['interval_s'])
    if expected['identity_sha256'] != forcing['identity_sha256']:
        raise ValueError('experiment_exact_schedule_mask_or_dry_initial_mismatch')


def run_pulse_level(carrier, geometry, forcing, *, max_dt_s, work_limit, wall_limit_s=7200.):
    validate_experiment(carrier, geometry, forcing)
    return run_case(carrier, geometry, forcing, case_index=0, max_dt_s=max_dt_s,
                    work_limit=work_limit, wall_limit_s=wall_limit_s)


def propagation_diagnostics(carrier, geometry, state, packets):
    completed = state['metadata']['status'] == 'completed'
    initial_dry = bool(np.all(state['arrays']['initial_depth_m'] == 0))
    gross_input = state['metadata'].get('boundary_input_m3') if completed else None
    isolated = completed and initial_dry and gross_input == 0. and bool(np.all(state['arrays']['ledger'][:, 1] == 0.))
    distance = carrier['arrays']['longitudinal_from_upstream_m'].ravel()
    wet_source = carrier['arrays']['wet_protected_mask'].ravel()
    left, right = geometry['arrays']['face_left'], geometry['arrays']['face_right']
    transfers = packets['arrays'].get('internal_transfer_m3', np.empty((0, len(left))))
    cuts = []
    for station in (5., 30., 60.):
        forward = (distance[left] < station) & (distance[right] >= station)
        backward = (distance[right] < station) & (distance[left] >= station)
        selected = np.flatnonzero(forward | backward)
        signs = np.where(forward[selected], 1., -1.)
        signed = transfers[:, selected] @ signs
        cuts.append(dict(station_m=station, face_indices=selected.tolist(), downstream_sign=signs.tolist(),
                         signed_interval_downstream_m3=signed.tolist(), cumulative_downstream_m3=float(signed.sum()),
                         gross_substep_direction_certified=False))
    receiving = wet_source & (distance >= 60.)
    depths = state['arrays']['depth_m'].reshape(len(state['arrays']['time_s']), -1)
    area = geometry['metadata']['spacing_m']**2
    volumes = depths[:, receiving].sum(axis=1)*area
    wet_front = []
    center = carrier['arrays']['centerline_offset_m'].ravel() <= .175
    for frame in depths:
        wet = (frame > 1e-6) & center & (distance >= 0)
        wet_front.append(float(distance[wet].max(initial=0)))
    reached = bool(receiving.any() and (depths[:, receiving] > 1e-6).any() and cuts[-1]['cumulative_downstream_m3'] > 1e-12)
    return dict(status='saved_diagnostic_not_independent_acceptance', source_isolation_diagnostic_passed=bool(isolated),
                completed=bool(completed), initial_dry=initial_dry, boundary_input_m3_all_substeps=gross_input,
                boundary_output_m3_all_substeps=state['metadata'].get('boundary_output_m3') if completed else None,
                cuts=cuts, time_s=state['arrays']['time_s'].tolist(), centerline_wet_front_m=wet_front,
                receiving_cell_indices=np.flatnonzero(receiving).tolist(), receiving_volume_m3=volumes.tolist(),
                reached_60m_source_wet_support_diagnostic=bool(isolated and reached),
                no_particle_tracer=True, gross_directional_face_certified=False,
                attribution_scope='new water in originally wet source support can only come from upstream injection when dry initial and global substep boundary input is exactly zero',
                **FLAGS)
