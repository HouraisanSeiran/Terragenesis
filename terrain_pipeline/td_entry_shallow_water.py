"""Pinned source-background entry windows and existing HLL/SSPRK2 execution."""

import math
import time

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget, prepare_surface_geometry
from terrain_pipeline.single_domain_shallow_water import advance_shallow_water

MAX_CELLS = 65536
MAX_BYTES = 1024**3
MAX_WORK = 6_000_000_000
SPACING = .175
FLAGS = dict(hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
             new_bed_hydrology_verified=False, time_refinement_verified=False)


def finish(arrays, metadata):
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise MemoryError('artifact_array_budget')
    return dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))


def check_resource():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, 'peak_wset', 0))
    if peak > MAX_BYTES:
        raise MemoryError('actual_process_1GiB_limit')
    return peak


def source_samples(hierarchy, selected, protection, points):
    arrays, meta = hierarchy['arrays'], hierarchy['metadata']
    bed = arrays['height_m']
    coordinates = (points - meta['origin_m_xz']) / meta['spacing_m']
    if (not np.isfinite(coordinates).all() or np.any(coordinates < 0) or
            np.any(coordinates > np.array(bed.shape[::-1])-1)):
        raise ValueError('outside_native_source')
    lower = np.minimum(np.floor(coordinates).astype(np.int64), np.array(bed.shape[::-1])-2)
    fraction = coordinates-lower
    rows = np.column_stack((lower[:, 1], lower[:, 1], lower[:, 1]+1, lower[:, 1]+1))
    columns = np.column_stack((lower[:, 0], lower[:, 0]+1, lower[:, 0], lower[:, 0]+1))
    weights = np.column_stack(((1-fraction[:, 0])*(1-fraction[:, 1]), fraction[:, 0]*(1-fraction[:, 1]),
                               (1-fraction[:, 0])*fraction[:, 1], fraction[:, 0]*fraction[:, 1]))
    active = weights > 0
    owner = arrays['cell_owner'][rows, columns]
    leaf = arrays['contribution_owner'][rows, columns]
    unknown = arrays['node_unknown_contact']
    if (not arrays['valid_mask'][rows, columns][active].all() or
            arrays['protected_mask'][rows, columns][active].any() or
            arrays['open_boundary_mask'][rows, columns][active].any() or
            not np.isin(leaf[active], selected).all() or
            np.any(owner[active] < 0) or np.any(owner[active] >= len(unknown)) or
            np.any(leaf[active] < 0) or np.any(leaf[active] >= len(unknown))):
        raise ValueError('invalid_protected_unknown_owner_source')
    if unknown[owner[active]].any() or unknown[leaf[active]].any():
        raise ValueError('unknown_source_owner_contact')
    values = bed[rows, columns]
    if not np.isfinite(values[active]).all():
        raise ValueError('nonfinite_source')
    source = np.sum(np.where(active, values, 0)*weights, axis=1)
    nearest = np.floor(coordinates+.5).astype(np.int64)
    native_cell = nearest[:, 1]*bed.shape[1]+nearest[:, 0]
    nearest_leaf = arrays['contribution_owner'][nearest[:, 1], nearest[:, 0]]
    stages = {int(item['leaf_id']): item['stage_m'] for item in protection['stage_by_leaf']}
    wet = np.isin(native_cell, protection['covered_native_cell_ids'])
    wet |= source < np.array([stages.get(int(leaf_id), -np.inf) for leaf_id in nearest_leaf])
    return dict(source_bed_m=source, native_corner_row=rows, native_corner_column=columns,
                native_corner_cell=rows*bed.shape[1]+columns, native_weights=weights,
                native_owner=owner, native_leaf=leaf, nearest_native_cell=native_cell,
                wet_protected_mask=wet)


def _weights(vertices, points):
    first, second, third = vertices
    denominator = ((second[2]-third[2])*(first[0]-third[0])+(third[0]-second[0])*(first[2]-third[2]))
    if abs(denominator) < 1e-14:
        raise ValueError('degenerate_parent_triangle')
    weight_first = ((second[2]-third[2])*(points[:, 0]-third[0])+(third[0]-second[0])*(points[:, 1]-third[2]))/denominator
    weight_second = ((third[2]-first[2])*(points[:, 0]-third[0])+(first[0]-third[0])*(points[:, 1]-third[2]))/denominator
    raw = np.column_stack((weight_first, weight_second, 1-weight_first-weight_second))
    inside = raw.min(axis=1) >= -1e-9
    clipped = np.clip(raw, 0, 1)
    return inside, clipped / clipped.sum(axis=1)[:, None]


def build_entry_bed(hierarchy, paths, sections, transitions, fine, readiness, *, entry_id=None, margin_m=1.):
    if (fine['grid']['spacing_m'] != SPACING or fine['grid']['center_offset_cells'] != .5 or
            paths['hierarchy_identity_sha256'] != hierarchy['identity_sha256'] or
            sections['composite_parent_identity']['paths'] != paths['identity_sha256'] or
            transitions['paths_identity_sha256'] != paths['identity_sha256'] or
            transitions['sections_identity_sha256'] != sections['identity_sha256'] or
            fine['transitions_identity_sha256'] != transitions['identity_sha256'] or
            fine['sections_identity_sha256'] != sections['identity_sha256'] or
            fine['hierarchy_identity_sha256'] != hierarchy['identity_sha256'] or
            fine['selected_leaf_ids'] != paths['selected_leaf_ids'] or
            fine['wet_protection']['covered_native_cell_ids'] != transitions['wet_protection']['covered_native_cell_ids'] or
            fine['wet_protection']['stage_by_leaf'] != transitions['wet_protection']['stage_by_leaf']):
        raise ValueError('parent_grid_identity_or_wet_mismatch')
    if not math.isfinite(margin_m) or margin_m < 1:
        raise ValueError('minimum_source_background_margin_1m')
    nodes = {node['node_id']: node for node in paths['nodes']}
    ports = {port['arc_id']: port for port in sections['edge_sections']}
    node_sections = {node['node_id']: node for node in sections['node_sections']}
    ready = {request['entry_id'] for request in readiness['requests'] if request['status'] == 'geometry_diagnostic_complete'}
    choices = []
    for number, entry in enumerate(transitions['entries']):
        if entry['entry_id'] not in ready or entry['status'] != 'candidate':
            continue
        port = ports[entry['accepted_port_arc_id']]
        chain = [port['node_ids'][0], entry['upstream_node_id'], entry['anchor_node_id'], entry['wet_node_id']]
        xyz = np.asarray([nodes[node]['xyz_m'] for node in chain])
        differences = np.diff(xyz[:, [0, 2]], axis=0)
        q = node_sections[port['node_ids'][0]]['representative_q_m3_s']
        if (not math.isfinite(q) or q <= 0 or not np.allclose(differences, differences[0], rtol=0, atol=1e-8) or
                not math.isclose(np.linalg.norm(differences[0]), 30., abs_tol=1e-8) or xyz[0, 1] < xyz[-1, 1]):
            continue
        choices.append((float((xyz[0, 1]-xyz[-1, 1])/90), entry['entry_id'], number, entry, port, xyz, q, chain))
    if entry_id is not None:
        choices = [choice for choice in choices if choice[1] == entry_id]
    if not choices:
        raise ValueError('no_complete_positive_q_collinear_90m_entry')
    slope, selected_id, entry_index, entry, port, xyz, q, chain = min(choices, key=lambda item: item[:2])
    triangles = [triangle for triangle in fine['triangles'] if
                 (triangle['source_package'] == '09' and triangle['source_entry_index'] == entry_index) or
                 (triangle['source_package'] == '06' and triangle['source_arc_id'] == port['arc_id'])]
    if (sum(triangle['source_package'] == '09' for triangle in triangles) != len(entry['triangles']) or
            sum(triangle['source_package'] == '06' for triangle in triangles) != len(port['triangle_indices']) or
            any(triangle['rejection_reasons'] or triangle['status'] not in ('rasterized', 'no_center_coverage') for triangle in triangles)):
        raise ValueError('entry_or_port_triangle_coverage_refused')
    mesh = np.asarray(sections['mesh']['vertices_xyz_m'])
    for triangle in triangles:
        expected = (np.asarray(entry['vertices_xyz_m'])[entry['triangles'][triangle['source_triangle_index']]]
                    if triangle['source_package'] == '09' else mesh[sections['mesh']['triangles'][triangle['source_triangle_index']]])
        if not np.array_equal(expected, triangle['vertices_xyz_m']):
            raise ValueError('fine_parent_triangle_changed')
    origin = np.asarray(fine['grid']['origin_m_xz'])
    triangle_xyz = np.asarray([triangle['vertices_xyz_m'] for triangle in triangles])
    all_points = np.vstack((triangle_xyz.reshape(-1, 3), xyz))[:, [0, 2]]
    direction = (xyz[-1, [0, 2]]-xyz[0, [0, 2]])/90
    axis = int(np.argmax(abs(direction)))
    lateral_axis = 1-axis
    minimum, maximum = all_points.min(axis=0), all_points.max(axis=0)
    minimum[lateral_axis] -= margin_m
    maximum[lateral_axis] += margin_m
    first = np.floor((minimum-origin)/SPACING-.5).astype(np.int64)
    last = np.ceil((maximum-origin)/SPACING-.5).astype(np.int64)
    shape = (int(last[1]-first[1]+1), int(last[0]-first[0]+1))
    if math.prod(shape) > MAX_CELLS:
        raise ValueError('window_65536_cell_limit')
    rows, columns = np.indices(shape, dtype=np.int64)
    global_rows, global_columns = rows+first[1], columns+first[0]
    points = origin+(np.column_stack((global_columns.ravel(), global_rows.ravel()))+.5)*SPACING
    samples = source_samples(hierarchy, paths['selected_leaf_ids'], fine['wet_protection'], points)
    source = samples['source_bed_m']
    derived = source.copy()
    lookup = {}
    triangle_lookup = {triangle['triangle_id']: number for number, triangle in enumerate(triangles)}
    for window_index, window in enumerate(fine['windows']):
        row_base, column_base = window['global_origin_row_column']
        for cell_index, cell in enumerate(window['cells']):
            if any(proposal['triangle_id'] in triangle_lookup for proposal in cell['triangle_sources']):
                key = (row_base+cell['local_index']//fine['grid']['tile_cells'], column_base+cell['local_index']%fine['grid']['tile_cells'])
                if key in lookup:
                    raise ValueError('duplicate_fine_global_cell')
                if cell['status'] != 'candidate' or cell['rejection_reasons']:
                    raise ValueError('whole_entry_or_port_contains_refused_cell')
                lookup[key] = (window_index, cell_index, cell)
    overlay = np.zeros(len(points), bool)
    fine_window = np.full(len(points), -1, np.int64)
    fine_cell = fine_window.copy()
    used_keys, references = set(), [[] for _ in points]
    tolerance = fine['parameters']['conflict_tolerance_m']
    for triangle_index, triangle in enumerate(triangles):
        vertices = np.asarray(triangle['vertices_xyz_m'])
        bbox = ((points >= vertices[:, [0, 2]].min(axis=0)-1e-8) &
                (points <= vertices[:, [0, 2]].max(axis=0)+1e-8)).all(axis=1)
        candidates = np.flatnonzero(bbox)
        inside, weights = _weights(vertices, points[candidates])
        for index, barycentric in zip(candidates[inside], weights[inside]):
            key = (int(global_rows.ravel()[index]), int(global_columns.ravel()[index]))
            if key not in lookup:
                raise ValueError('missing_fine_center_for_actual_parent_triangle')
            window_index, cell_index, cell = lookup[key]
            proposal = next((proposal for proposal in cell['triangle_sources'] if proposal['triangle_id'] == triangle['triangle_id']), None)
            proposed_bed = float(barycentric @ vertices[:, 1])
            if (proposal is None or not np.allclose(proposal['weights'], barycentric, rtol=0, atol=1e-8) or
                    abs(proposal['bed_m']-proposed_bed) > 1e-8 or
                    abs(cell['derived_bed_m']-proposed_bed) > tolerance or
                    abs(cell['source_sample']['height_m']-source[index]) > 1e-8):
                raise ValueError('fine_source_or_triangle_interpolation_mismatch')
            derived[index] = cell['derived_bed_m']
            overlay[index] = True
            fine_window[index], fine_cell[index] = window_index, cell_index
            references[index].append((triangle_index, barycentric, proposed_bed))
            used_keys.add(key)
    if used_keys != set(lookup):
        raise ValueError('entry_port_fine_cells_outside_rect_or_geometry')
    cut = source-derived
    if np.any(cut < -1e-8) or np.any(cut > 4+1e-8) or np.any(samples['wet_protected_mask'] & (cut > tolerance)):
        raise ValueError('fill_cut_or_wet_bed_modification')
    if not np.array_equal(derived[~overlay], source[~overlay]):
        raise ValueError('uncovered_source_changed')
    if not np.array_equal(derived[samples['wet_protected_mask']], source[samples['wet_protected_mask']]):
        raise ValueError('wet_source_bed_must_be_exactly_unchanged')
    offsets = np.r_[0, np.cumsum([len(items) for items in references])].astype(np.int64)
    refs = [reference for items in references for reference in items]
    port_first = np.asarray(port['cross_section_xyz_m'][0])
    bed_low, bed_high = port_first[1:3, [0, 2]].min(axis=0), port_first[1:3, [0, 2]].max(axis=0)
    longitudinal = (points-xyz[0, [0, 2]]) @ direction
    upstream_layer = (longitudinal >= -1e-8) & (longitudinal < SPACING+1e-8)
    forcing_mask = upstream_layer & (points[:, lateral_axis] >= bed_low[lateral_axis]-1e-8) & (points[:, lateral_axis] <= bed_high[lateral_axis]+1e-8) & overlay
    if not forcing_mask.any():
        raise ValueError('no_actual_upstream_bed_cross_section_cells')
    lake = next(lake for lake in paths['lakes'] if lake['leaf_id'] == nodes[chain[-1]]['leaf_id'])
    arrays = {key: value.reshape(*shape, *value.shape[1:]) for key, value in samples.items()}
    arrays.update(derived_bed_m=derived.reshape(shape), global_row=global_rows, global_column=global_columns,
                  overlay_mask=overlay.reshape(shape), valid_mask=np.ones(shape, bool), protected_mask=np.zeros(shape, bool),
                  forcing_mask=forcing_mask.reshape(shape), fine_window_index=fine_window.reshape(shape),
                  longitudinal_from_upstream_m=longitudinal.reshape(shape),
                  centerline_offset_m=abs(points[:, lateral_axis]-xyz[0, lateral_axis*2]).reshape(shape),
                  fine_cell_index=fine_cell.reshape(shape), triangle_offsets=offsets,
                  triangle_indices=np.array([item[0] for item in refs], np.int64),
                  triangle_weights=np.asarray([item[1] for item in refs], np.float64).reshape(-1, 3),
                  triangle_proposed_bed_m=np.array([item[2] for item in refs], np.float64),
                  selected_triangle_vertices_xyz_m=triangle_xyz, chain_xyz_m=xyz,
                  chain_native_cell_ids=np.array([nodes[node]['cell_id'] for node in chain], np.int64))
    metadata = dict(schema='td-entry-shallow-water-bed-v1', entry_id=selected_id, entry_index=entry_index,
                    accepted_port_arc_id=port['arc_id'], ordinary_q_m3_s=float(q), ordinary_lake_stage_m=lake['ordinary_stage_max_m'],
                    injection_node_id=port['node_ids'][0], injection_native_cell_id=nodes[port['node_ids'][0]]['cell_id'],
                    injection_q_semantics='06 node_sections representative_q_m3_s at exact accepted edge[0]; uncalibrated ordinary mean proxy; no additional rainfall',
                    selected_leaf_ids=paths['selected_leaf_ids'], spacing_m=SPACING, shape=list(shape),
                    global_origin_row_column=[int(first[1]), int(first[0])], global_lattice_origin_m_xz=origin.tolist(),
                    local_center_origin_m_xz=(origin+(first+.5)*SPACING).tolist(), direction_xz=direction.tolist(),
                    selected_triangle_ids=[triangle['triangle_id'] for triangle in triangles],
                    selected_triangle_source_refs=[{key: value for key, value in triangle.items() if key.startswith('source_')} for triangle in triangles],
                    selection='explicit entry' if entry_id else 'minimum native 90m source slope among complete positive-q collinear entries',
                    native_path_slope=slope, margin_m=margin_m, source_resolution_m=30.,
                    parent_identities={name: record['identity_sha256'] for name, record in
                                       (('hierarchy', hierarchy), ('paths', paths), ('sections', sections), ('transitions', transitions), ('fine', fine))},
                    wet_protection=fine['wet_protection'], wet_cut_tolerance_m=tolerance,
                    semantics='accepted source fine cells only; all uncovered source background including wet support unchanged; 0.175m is sampling not new DEM detail', **FLAGS)
    return finish(arrays, metadata)


def build_geometry(bed):
    meta = bed['metadata']
    geometry = prepare_surface_geometry(bed['arrays']['derived_bed_m'], spacing_m=SPACING,
                                        origin_m_xz=meta['local_center_origin_m_xz'], source_identity=bed['identity_sha256'])
    rows, columns = bed['arrays']['derived_bed_m'].shape
    direction = np.asarray(meta['direction_xz'])
    axis = int(np.argmax(abs(direction)))
    side = (1 if direction[0] > 0 else 0) if axis == 0 else (3 if direction[1] > 0 else 2)
    lengths = [rows, rows, columns, columns]
    start = sum(lengths[:side])
    geometry['arrays']['boundary_kind'][start:start+lengths[side]] = 2
    geometry['metadata'].update(schema='td-entry-shallow-water-D4-geometry-v1',
        downstream_side=side, scope='entire short downstream cross-section prescribed engineering lake stage; upstream and both sides closed',
        bed_identity_sha256=bed['identity_sha256'], **FLAGS)
    return finish(geometry['arrays'], geometry['metadata'])


def build_forcing(bed, geometry, *, duration_s=60., interval_s=5., tailwater_rise_m=.4):
    if (not math.isfinite(duration_s) or duration_s <= 0 or not math.isfinite(interval_s) or interval_s <= 0 or
            not math.isclose(duration_s/interval_s, round(duration_s/interval_s), abs_tol=1e-10) or
            not .3 <= tailwater_rise_m <= .5):
        raise ValueError('invalid_declared_schedule')
    intervals = round(duration_s/interval_s)
    times = np.arange(intervals+1, dtype=np.float64)*interval_s
    source = np.zeros((2, intervals, *bed['arrays']['derived_bed_m'].shape), np.float64)
    initial = np.zeros((2, *bed['arrays']['derived_bed_m'].shape), np.float64)
    pulse = (times[:-1] < duration_s/3).astype(float)
    source[0] = pulse[:, None, None]*bed['arrays']['forcing_mask'][None]*bed['metadata']['ordinary_q_m3_s']/bed['arrays']['forcing_mask'].sum()
    baseline = bed['metadata']['ordinary_lake_stage_m']
    initial[1] = np.maximum(baseline-bed['arrays']['derived_bed_m'], 0.)
    rise = ((times[:-1] >= duration_s/3) & (times[:-1] < 2*duration_s/3))*tailwater_rise_m
    boundary = np.full((2, intervals, len(geometry['arrays']['boundary_cell'])), baseline, np.float64)
    boundary[1] += rise[:, None]
    return finish(dict(time_s=times, forcing_m3_s=source.reshape(2, intervals, -1), boundary_stage_m=boundary, initial_depth_m=initial),
                  dict(schema='td-entry-shallow-water-forcing-v1', case_names=['normal-pulse-retreat', 'tailwater-rise-fall'],
                       forcing_array_axes='case, interval, flattened_row_major_cell', grid_shape=list(bed['arrays']['derived_bed_m'].shape),
                       duration_s=duration_s, interval_s=interval_s, tailwater_rise_m=tailwater_rise_m,
                       geometry_identity_sha256=geometry['identity_sha256'], bed_identity_sha256=bed['identity_sha256'],
                       baseline_stage_semantics='paths lake ordinary_stage_max_m; conservative maximum, not simultaneous observed water',
                       forcing_semantics='ordinary upstream representative Q proxy; cellwise volume-rate injection on upstream bed support only; no momentum injection',
                       schedules='normal Q during first third then zero; tail stage baseline/rise/baseline thirds, no lateral Q', **FLAGS))


def run_case(bed, geometry, forcing, *, case_index, max_dt_s, work_limit=MAX_WORK, wall_limit_s=7200.):
    if not 0 < work_limit <= MAX_WORK or case_index not in (0, 1):
        raise ValueError('case_or_work_budget')
    started = time.monotonic()
    interval_records, witnesses = [], []
    peak = check_resource()
    intervals = len(forcing['arrays']['time_s'])-1
    estimate = geometry['arrays']['H2_m'].size*8*(90+80*intervals)
    if estimate > MAX_BYTES or estimate+psutil.Process().memory_info().rss > MAX_BYTES:
        raise MemoryError('saved_witness_estimate_exceeds_1GiB')
    def observer(destination):
        def receive(value):
            nonlocal peak
            peak = max(peak, check_resource())
            destination.append({key: np.asarray(item).copy() for key, item in value.items()})
        return receive
    budget = SurfaceBudget(max_dt_s=max_dt_s, max_cells=MAX_CELLS, max_face_evaluations=int(work_limit),
                           max_bytes=MAX_BYTES, max_duration_s=forcing['metadata']['duration_s'],
                           max_wall_s=wall_limit_s, max_snapshots=max(3, intervals+1), max_depth_m=20.)
    try:
        result = advance_shallow_water(geometry, initial_depth_m=forcing['arrays']['initial_depth_m'][case_index],
            forcing_interval_s=forcing['metadata']['interval_s'], intervals=intervals,
            forcing_provider=lambda interval: forcing['arrays']['forcing_m3_s'][case_index, interval].reshape(geometry['arrays']['H2_m'].shape),
            boundary_stage_provider=lambda interval: forcing['arrays']['boundary_stage_m'][case_index, interval],
            source_identity=bed['identity_sha256'], forcing_identity=forcing['identity_sha256'], budget=budget,
            snapshot_interval_s=forcing['metadata']['interval_s'], interval_observer=observer(interval_records), momentum_observer=observer(witnesses))
    except (RuntimeError, ValueError, MemoryError) as error:
        initial = forcing['arrays']['initial_depth_m'][case_index]
        saved = [np.column_stack((initial.ravel(), np.zeros((initial.size, 2))))]
        saved += [np.column_stack((packet['depth_after_m'], packet['momentum_after'])) for packet in interval_records]
        states = np.asarray(saved)
        area = geometry['metadata']['spacing_m']**2
        supplied = [0.]
        external = [0.]
        for packet in interval_records:
            supplied.append(supplied[-1]+float(packet['forcing_volume_m3'].sum()))
            external.append(external[-1]-float(packet['boundary_transfer_m3'].sum()))
        volumes = states[:, :, 0].sum(axis=1)*area
        ledger = np.column_stack((supplied, np.maximum(external, 0), np.maximum(-np.asarray(external), 0),
                                  volumes, volumes-volumes[0]-supplied-external))
        result = dict(arrays=dict(time_s=np.arange(len(saved))*forcing['metadata']['interval_s'],
                                 depth_m=states[:, :, 0].reshape(-1, *initial.shape),
                                 momentum_x_m2_s=states[:, :, 1].reshape(-1, *initial.shape),
                                 momentum_z_m2_s=states[:, :, 2].reshape(-1, *initial.shape),
                                 initial_depth_m=initial, ledger=ledger),
                      metadata=dict(status='diagnostic_failure', failure=str(error), budget=vars(budget),
                                    source_identity=bed['identity_sha256'], forcing_identity=forcing['identity_sha256'],
                                    requested_time_s=forcing['metadata']['duration_s'],
                                    committed_time_s=len(interval_records)*forcing['metadata']['interval_s'],
                                    substeps=-1, face_evaluations=-1, resource_work_upper_bound=int(work_limit*1.5),
                                    ledger_semantics='failure only: signed interval net boundary split, not substep gross totals'),
                      diagnostics=dict(minimum_dt_s=0., maximum_dt_s=0., maximum_wave_speed_m_s=0.))
    metadata = dict(result['metadata'], schema='td-entry-shallow-water-state-v1', geometry_identity_sha256=geometry['identity_sha256'],
                    case_index=case_index, case_name=forcing['metadata']['case_names'][case_index], max_dt_requested_s=max_dt_s,
                    diagnostics=result['diagnostics'], gross_boundary_per_face_certified=False,
                    gross_boundary_semantics='solver totals integrate positive/negative averaged RK flux each actual substep; observer exposes first substep only, no per-face gross certification',
                    actual_peak_rss_bytes=max(peak, check_resource()), total_wall_s=time.monotonic()-started, **FLAGS)
    state = finish(result['arrays'], metadata)
    transfers = finish({key: np.stack([record[key] for record in interval_records]) for key in interval_records[0]} if interval_records else {},
                       dict(schema='td-entry-shallow-water-intervals-v1', state_identity_sha256=state['identity_sha256'],
                            internal_sign='left to right', boundary_sign='outward positive',
                            mass_units='m3', momentum_transfer_units='m4/s', bed_drag_impulse_units='m2/s', **FLAGS))
    first_rk = finish({key: np.stack([record[key] for record in witnesses]) for key in witnesses[0]} if witnesses else {},
                      dict(schema='td-entry-shallow-water-first-rk-v1', state_identity_sha256=state['identity_sha256'],
                           semantics='actual first SSPRK2 substep per forcing interval only, not all-substep gross witness', **FLAGS))
    return state, transfers, first_rk


def event_diagnostics(bed, state, transfers):
    depths = state['arrays']['depth_m']
    center = bed['arrays']['centerline_offset_m'] <= .175
    longitudinal = bed['arrays']['longitudinal_from_upstream_m']
    probes = {}
    for distance in (1., 5., 15., 30.):
        mask = center & (abs((90-longitudinal)-distance) <= .35)
        probes[str(distance)+'m_from_downstream'] = dict(cell_indices=np.flatnonzero(mask).tolist(),
            maximum_depth_change_m=float(abs(depths[:, mask]-depths[0, mask]).max(initial=0)),
            depth_by_snapshot_m=depths[:, mask].mean(axis=1).tolist() if mask.any() else [])
    upstream_wet = (depths > 1e-6) & center & (longitudinal >= 0) & (longitudinal < 60)
    wet_front = [float(longitudinal[mask].max(initial=0)) for mask in upstream_wet]
    boundary = transfers['arrays'].get('boundary_transfer_m3', np.empty((0, 0)))
    return dict(status='diagnostic_only', probes=probes, normal_land_wet_front_m=wet_front,
                signed_interval_boundary_backflow_m3=float(np.maximum(-boundary, 0).sum()),
                signed_interval_boundary_outflow_m3=float(np.maximum(boundary, 0).sum()),
                gross_boundary_per_face_certified=False,
                limitation='normal dry event may receive engineering lake inflow as well as upstream Q; wet front has no source attribution')


def compare_levels(coarse, fine, coarse_transfers, fine_transfers):
    for key in ('source_identity', 'forcing_identity', 'geometry_identity_sha256', 'case_index'):
        if coarse['metadata'][key] != fine['metadata'][key]:
            raise ValueError('different_bed_forcing_or_case_comparison')
    if not np.array_equal(coarse['arrays']['time_s'], fine['arrays']['time_s']):
        raise ValueError('comparison_time_mismatch')
    depth_difference = float(np.max(abs(coarse['arrays']['depth_m']-fine['arrays']['depth_m'])))
    difference = {}
    for name in ('internal_transfer_m3', 'boundary_transfer_m3'):
        first = coarse_transfers['arrays'][name].sum(axis=0)
        second = fine_transfers['arrays'][name].sum(axis=0)
        numerator, denominator = float(abs(first-second).sum()), float(abs(second).sum())
        difference[name] = numerator/denominator if denominator else (0. if numerator == 0 else None)
    effective = (fine['metadata']['max_dt_requested_s'] < coarse['metadata']['max_dt_requested_s'] and
                 fine['metadata']['diagnostics']['maximum_dt_s'] < coarse['metadata']['diagnostics']['maximum_dt_s'] and
                 fine['metadata']['substeps'] > coarse['metadata']['substeps'])
    coarse_volume, fine_volume = coarse['arrays']['ledger'][:, 3], fine['arrays']['ledger'][:, 3]
    relative_volume = float(np.max(abs(coarse_volume-fine_volume)/np.maximum(abs(fine_volume), 1e-12)))
    passed = effective and depth_difference <= .001 and relative_volume <= .01 and all(value is not None and value <= .01 for value in difference.values())
    boundary = fine_transfers['arrays']['boundary_transfer_m3']
    return dict(max_depth_difference_m=depth_difference, cumulative_net_relative_l1=difference,
                maximum_volume_difference_m3=float(np.max(abs(coarse['arrays']['ledger'][:, 3]-fine['arrays']['ledger'][:, 3]))),
                maximum_relative_volume_difference=relative_volume,
                maxdt_constraint_effective=bool(effective), time_refinement_diagnostic_passed=bool(passed),
                time_refinement_verified=False,
                boundary_signed_interval_inflow_observed=bool(np.any(boundary < -1e-12)),
                boundary_signed_interval_outflow_m3=float(np.maximum(boundary, 0).sum()),
                wet_cells_per_snapshot=(fine['arrays']['depth_m'] > 1e-6).sum(axis=(1, 2)).tolist(),
                gross_boundary_per_face_certified=False, depth_threshold_m=.001, relative_l1_threshold=.01)
