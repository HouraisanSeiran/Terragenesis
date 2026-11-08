"""Versioned shared-width update of an already reconciled native v4 network."""
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
from terrain_pipeline.new_world_native_network import section
from terrain_pipeline.new_world_native_network_v4 import reconcile
from terrain_pipeline.new_world_width_reach import file_sha256
from terrain_pipeline.surface_rivers.formative_section import formative_section, section_from_routed_budget
from terrain_pipeline.geology import sample_lithology_points, rock_table_identity


def build_native_width_network(root, output, *, sediment_reach=None):
    """Build a new product from v4; source products and default world stay immutable.

    Known committed reach budgets, if supplied, are applied once. Other river
    nodes use the material/flow baseline with an explicit false known mask.
    """
    root, output = Path(root), Path(output)
    if output.exists():
        raise FileExistsError(output)
    source = root / 'native-network-v4'
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf8'))
    if manifest['schema'] != 'native-network-v4':
        raise ValueError('native-network-v4 required')
    load = lambda name: np.load(source / (name + '.npy'), mmap_mode='r', allow_pickle=False)
    ids, xz, q, kind = (load(n) for n in ('node_id', 'node_xz_m', 'node_q_m3_s', 'node_kind'))
    raw, pools, edges = (load(n) for n in ('node_raw_bed_m', 'node_pool_index', 'edge_nodes'))
    lith = sample_lithology_points(xz[:, 0], xz[:, 1], world_seed=20261020)
    bed, bank = lith['bed_hardness'], lith['bank_hardness']
    eligible = (kind == 0) & (q > 0.)
    previous_width, design_depth = section(q)
    width = previous_width.copy()
    width[eligible] = formative_section(q[eligible], bed[eligible], bank[eligible], 0., .25).width_m
    known = np.zeros(len(ids), dtype=bool)
    budget_names = ('incoming_solid_m3', 'external_solid_m3', 'capacity_solid_m3',
                    'eroded_loose_solid_m3', 'eroded_rock_m3', 'deposited_solid_m3')
    budgets = {name: np.full(len(ids), np.nan) for name in budget_names}
    initial_mobile = np.full(len(ids), np.nan)
    final_loose = np.full(len(ids), np.nan)
    final_mobile = np.full(len(ids), np.nan)
    rock_floor = np.full(len(ids), np.nan)
    committed_bed = np.full(len(ids), np.nan)
    sediment_identity = None
    if sediment_reach is not None:
        sediment_reach = Path(sediment_reach)
        info = json.loads(sediment_reach.with_suffix('.json').read_text(encoding='utf8'))
        if info['terrain_identity'] != manifest['source_identity'] or info['npz_sha256'] != file_sha256(sediment_reach):
            raise ValueError('sediment reach source or archive identity mismatch')
        with np.load(sediment_reach, allow_pickle=False) as reach:
            indices = np.searchsorted(ids, reach['node_id'])
            if np.any(indices >= len(ids)) or not np.array_equal(ids[indices], reach['node_id']):
                raise ValueError('sediment reach is not a subset of network')
            if not np.all(eligible[indices]) or not np.allclose(q[indices], reach['formative_q_m3_s'], rtol=1e-12, atol=0.):
                raise ValueError('sediment reach Q or node eligibility mismatch')
            if not np.allclose(bed[indices], reach['bed_resistance']) or not np.allclose(bank[indices], reach['bank_resistance']):
                raise ValueError('sediment reach material mismatch')
            for name in budget_names:
                budgets[name][indices] = reach['sediment_' + name][0]
            initial_mobile[indices] = reach['sediment_initial_mobile_solid_m3']
            final_loose[indices] = reach['sediment_trace_loose_solid_m3'][-1]
            final_mobile[indices] = reach['sediment_trace_mobile_solid_m3'][-1]
            rock_floor[indices] = reach['sediment_rock_floor_m']
            committed_bed[indices] = reach['bed_m']
            updated = section_from_routed_budget(q[indices], bed[indices], bank[indices], 0., .25,
                **{name: budgets[name][indices] for name in budget_names},
                initial_mobile_solid_m3=initial_mobile[indices])
            if not np.allclose(updated.width_m, reach['width_m'], rtol=1e-12, atol=1e-12):
                raise ValueError('routed section disagrees with saved reach')
            width[indices] = updated.width_m
            known[indices] = True
            sediment_identity = info['sediment_sha256']
    # Reconcile using the cached pool/inlet state. Width is the only modified
    # section dimension; existing stage, bed, midpoint and lake semantics close.
    levels = np.load(root/'native-event-v3/pool_level_m.npy', mmap_mode='r')[2]
    rank = np.load(root/'native-final-routing-v1/routing/rank.npy', mmap_mode='r')[ids]
    target = np.full(len(ids), -1, dtype=np.int64); target[edges[:, 0]] = edges[:, 1]
    inlet_edges, offsets, inlet_stages = (load(n) for n in ('inlet_edge_index', 'inlet_offsets', 'inlet_stage_m'))
    starts = edges[inlet_edges, 1]
    first_stages = inlet_stages[offsets[:-1]]
    stage, node_bed, _, bad = reconcile(raw, q, kind, pools, levels, target, rank,
        starts, first_stages, section_override=(width, design_depth))
    for name, actual in (('node_stage_m', stage), ('node_bed_m', node_bed), ('node_status', bad)):
        if not np.allclose(load(name), actual, equal_nan=True, rtol=0., atol=1e-10):
            raise ValueError('cached reconciliation changed: ' + name)
    node_bed[known] = committed_bed[known]
    node_depth = stage - node_bed
    if np.any(node_depth[known] < 0.) or np.any(raw[known] - node_bed[known] > 4.):
        raise ValueError('committed sediment bed violates stage or cut bound')
    midpoint_raw = load('edge_midpoint_raw_m')
    midpoint_stage = (stage[edges[:, 0]] + stage[edges[:, 1]]) * .5
    midpoint_depth = (node_depth[edges[:, 0]] + node_depth[edges[:, 1]]) * .5
    midpoint_bed = np.minimum(midpoint_raw, midpoint_stage - midpoint_depth)
    status = np.array(load('edge_status'))
    affected = known[edges[:, 0]] | known[edges[:, 1]]
    failed = affected & (status == 0) & ((midpoint_raw-midpoint_bed > 4.) |
        (stage[edges[:, 0]] + 1e-8 < stage[edges[:, 1]]) | bad[edges[:, 0]] | bad[edges[:, 1]])
    status[failed] = 1
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + '-pending-', dir=output.parent))
    try:
        frozen_bounds = {'corridor_capacity_bound_m3.npy', 'sill_extra_storage_bound_m3.npy', 'sill_depth_m.npy'}
        for path in source.iterdir():
            if not path.is_file() or path.name in ('manifest.json', 'node_velocity_m_s.npy'):
                continue
            # These bounds were used to build the saved event. They belong to
            # that historical section, not the newly estimated river widths.
            name = 'source_event_' + path.name if path.name in frozen_bounds else path.name
            shutil.copyfile(path, temporary/name)
        np.save(temporary/'node_width_m.npy', width)
        np.save(temporary/'node_bed_m.npy', node_bed)
        np.save(temporary/'node_depth_m.npy', node_depth)
        np.save(temporary/'edge_midpoint_bed_m.npy', midpoint_bed)
        np.save(temporary/'edge_status.npy', status)
        for name, value in dict(node_bed_resistance=bed, node_bank_resistance=bank,
                node_fracture_additional=np.zeros(len(ids)), node_bank_cohesion=np.full(len(ids), .25),
                node_width_eligible=eligible, node_sediment_known=known,
                node_sediment_initial_mobile_solid_m3=initial_mobile,
                node_sediment_final_loose_solid_m3=final_loose,
                node_sediment_final_mobile_solid_m3=final_mobile, node_sediment_rock_floor_m=rock_floor,
                **{'node_sediment_'+k: v for k,v in budgets.items()}).items():
            np.save(temporary/(name+'.npy'), value)
        width_code = Path(__file__).parent/'surface_rivers/formative_section.py'
        metadata = dict(manifest)
        if 'sill_extra_storage_bound_sum_m3' in metadata:
            metadata['source_event_sill_extra_storage_bound_sum_m3'] = metadata.pop('sill_extra_storage_bound_sum_m3')
        metadata.update(schema='native-network-width-v1', parent_product=str(source),
            parent_manifest_sha256=file_sha256(source/'manifest.json'),
            width_algorithm='formative-section-routed-budget-v2', width_algorithm_sha256=file_sha256(width_code),
            lithology_table_sha256=rock_table_identity(), world_seed=20261020,
            width_parameters=dict(reference_discharge_m3_s=1., reference_width_m=4., min_width_m=0.,
                max_width_m=120., width_exponent=.45, bank_cohesion=.25, additional_fracture=0.),
            formative_flow='native-event-v3 interval 2 mean, fixed formative scenario; historical recurrence unknown',
            sediment_policy='committed reach budget once where known; unknown elsewhere, baseline width',
            sediment_identity_sha256=sediment_identity,
            sediment_reach_sha256=file_sha256(sediment_reach) if sediment_reach is not None else None,
            sediment_known_nodes=int(known.sum()),
            eligible_river_nodes=int(eligible.sum()), other_node_policy='retain v4 lake/ocean and zero-flow widths',
            stage_bed_policy='v4 stage/lake reconciliation; committed sediment bed on known nodes, with updated depth and midpoint; widths may be subgrid',
            velocity_policy='unavailable: no velocity array is copied or inferred; current widths and cached stages are not a solved hydraulic state',
            source_event_storage_bounds='source_event_* bounds and sill depth use the old section and reproduce the frozen source event; they are not recomputed for the new section',
            hydraulics_scope='cached v4 event and stage; current-width network has not been dynamically solved',
            edge_status_counts={str(i):int(np.count_nonzero(status==i)) for i in range(12)},
            committed_bed_new_edge_failures=int(failed.sum()),
            source_q_sha256=file_sha256(source/'node_q_m3_s.npy'),
            result_width_sha256=file_sha256(temporary/'node_width_m.npy'))
        (temporary/'manifest.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf8')
        os.rename(temporary, output)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return metadata
