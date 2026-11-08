"""Full declared TD valley coverage audit using tiled shared fields."""
import argparse
from collections import Counter
from contextlib import ExitStack
import gc
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.channel_geometry import GeometryConfig, _footprint
from terrain_pipeline.channel_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.channel_geometry import _profile
from terrain_pipeline.channel_geometry import TileBudget, build_tiled_refinement_pair, load_tiled_monotone_union, save_tiled_monotone_union
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_ID, TD_PRODUCT_SHA, terrain_from_product
from tools.verify_td_valley_network_union import connected_components, shape_statistics
ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'verification/td-river-network-expansion/td1024-20261008-01'

def _write_progress(path, record):
    """Refresh the resumable progress snapshot without changing artifacts."""
    target = Path(path)
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(record, indent=2), encoding='utf-8')
    temporary.replace(target)

def _cold_load(path, sha, identity):
    disabled = (('terrain_pipeline.channel_geometry.build_tiled_refinement_pair',), ('terrain_pipeline.channel_geometry._i34_linprog',), ('terrain_pipeline.channel_geometry.build_channel_geometry',), ('terrain_pipeline.surface_hydraulics.solve_channel',), ('terrain_pipeline.drainage.route_diagnostic',), ('terrain_pipeline.runoff.runoff_from_forcing',))
    with ExitStack() as stack:
        for target, in disabled:
            stack.enter_context(patch(target, side_effect=AssertionError('disabled cold entry: ' + target)))
        return load_tiled_monotone_union(path, expected_sha256=sha, expected_identity=identity)

def _independent_volume(bundle):
    a = bundle['arrays']
    triangles = a['global_triangles']
    vertices = a['global_vertex_xz_m'][triangles]
    signed = ((vertices[:, 1, 0] - vertices[:, 0, 0]) * (vertices[:, 2, 1] - vertices[:, 0, 1]) - (vertices[:, 2, 0] - vertices[:, 0, 0]) * (vertices[:, 1, 1] - vertices[:, 0, 1])) / 2.0
    if np.any(signed == 0.0) or not (np.all(signed > 0.0) or np.all(signed < 0.0)):
        raise ValueError('degenerate or reversed tiled triangles')
    volume = float(np.dot(np.abs(signed), np.mean(a['global_cut_depth_m'][triangles], axis=1)))
    np.testing.assert_allclose(volume, bundle['metadata']['cut_volume_m3'], rtol=0.0, atol=1e-07)
    if np.any(a['global_cut_depth_m'] < -1e-10):
        raise ValueError('negative tiled cut depth')
    if np.any(a['global_cut_depth_m'] > bundle['metadata']['config']['max_cut_m'] + 1e-08):
        raise ValueError('tiled cut exceeds four metre limit')
    return volume

def _unique_ledger(bundles):
    cells = {}
    component_volume = 0.0
    duplicate_zero = 0
    for component, bundle in enumerate(bundles):
        a = bundle['arrays']
        component_volume += _independent_volume(bundle)
        for index, xy in enumerate(a['global_cell_xy']):
            key = tuple(map(int, xy))
            corner_ids = a['global_triangles'][4 * index:4 * index + 4]
            coordinates = a['global_vertex_xz_m'][corner_ids]
            cuts = a['global_cut_depth_m'][corner_ids]
            if key in cells:
                old_coordinates, old_cuts, old_component = cells[key]
                np.testing.assert_allclose(old_coordinates, coordinates, rtol=0.0, atol=1e-09)
                if np.any(old_cuts > 0.0) and np.any(cuts > 0.0):
                    raise ValueError(f'cross-component positive cut overlap at {key}')
                duplicate_zero += 1
                cells[key] = (coordinates, np.maximum(old_cuts, cuts), old_component)
            else:
                cells[key] = (coordinates, cuts.copy(), component)
    unique_volume = 0.0
    for coordinates, cuts, _ in cells.values():
        tri = coordinates
        signed = ((tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1]) - (tri[:, 2, 0] - tri[:, 0, 0]) * (tri[:, 1, 1] - tri[:, 0, 1])) / 2.0
        unique_volume += float(np.dot(np.abs(signed), np.mean(cuts, axis=1)))
    np.testing.assert_allclose(unique_volume, component_volume, rtol=1e-10, atol=1e-07)
    return {'unique_cells': len(cells), 'duplicate_zero_support_cells': duplicate_zero, 'global_unique_cut_volume_m3': unique_volume, 'sum_component_cut_volume_m3': component_volume, 'cross_component_positive_support_disjoint': True}

def _load_ledger_bundles(refs):
    """Load one cold-validated fine bundle at a time for bounded memory use."""
    for path, sha, identity_sha in refs:
        bundle = _cold_load(path, sha, identity_sha)
        try:
            yield bundle
        finally:
            del bundle

def _preflight(terrain, plan):
    a = plan['arrays']
    receiver = a['graph_receiver']
    owner = a['terminal_owner'].reshape(terrain.elevation_m.shape)
    q = a['contributing_area_m2'] / 1000.0 / 3600.0
    widths = np.maximum(6.0, 4.0 * np.sqrt(q))
    depths = np.maximum(0.25, 0.2 * np.cbrt(q))
    eligible, rows = ([], [])
    for cell in a['selected_edge_source_ids']:
        ids = np.array([cell, receiver[cell]], np.int64)
        points = np.array([terrain.world_xz(int(value)) for value in ids])
        local_receiver = np.array([1, -1], np.int64)
        try:
            _profile(points, local_receiver, depths[ids], terrain, 4.0)
            _footprint(points, local_receiver, widths[ids], np.full(2, 4.0), terrain, owner, np.ones(owner.shape, bool), np.zeros(owner.shape, bool), owner.ravel()[ids], 0.5)
            eligible.append(int(cell))
            rows.append({'source_cell_id': int(cell), 'status': 'passed_edge_preflight'})
        except ValueError as error:
            rows.append({'source_cell_id': int(cell), 'status': 'refused_edge_preflight', 'reason': str(error)})
    return (receiver, owner, widths, depths, eligible, rows)

def verify(output):
    output = Path(output).resolve()
    output.mkdir(parents=False, exist_ok=False)
    code_paths = ('terrain_pipeline/channel_geometry.py', 'tools/verify_td_valley_global_tiled.py')
    code_pins = {path: file_sha256(ROOT / path) for path in code_paths}
    publish_bytes(output / 'run-declaration.json', json.dumps({'status': 'running_not_accepted', 'source_sha256': TD_PRODUCT_SHA, 'code_sha256': code_pins, 'declared_set': 'selected_edges_2km2_threshold'}, indent=2).encode())
    source = load_diagnostic_product(TD_DIRECTORY / 'product.npz', expected_sha256=TD_PRODUCT_SHA, expected_identity=TD_PRODUCT_ID)
    terrain = terrain_from_product(source)
    parent = json.loads((PARENT / 'acceptance.json').read_text(encoding='utf-8'))
    pin = parent['plan']
    plan = load_network_geometry_plan(PARENT / pin['path'], expected_sha256=pin['sha256'])
    if plan['identity_sha256'] != pin['identity_sha256']:
        raise ValueError('network plan pin changed')
    receiver, owner, widths, depths, eligible, preflight = _preflight(terrain, plan)
    eligible_set = set(eligible)
    records, artifacts, fine_refs, accepted_edges = ({}, {}, [], [])
    options = {'owner_grid': owner, 'corridor_mask': np.ones(owner.shape, bool), 'lake_mask': np.zeros(owner.shape, bool)}
    for component_index, nodes in enumerate(connected_components(eligible, receiver)):
        mapping = {int(cell): index for index, cell in enumerate(nodes)}
        local_receiver = np.array([mapping.get(int(receiver[cell]), -1) for cell in nodes], np.int64)
        edges = nodes[local_receiver >= 0]
        record = {'source_node_ids': nodes.tolist(), 'source_edge_ids': edges.tolist(), 'status': 'unresolved'}
        pair = coarse = fine = None
        try:
            pair = build_tiled_refinement_pair(terrain, nodes, local_receiver, widths[nodes], depths[nodes], **options, source_plan_identity_sha256=plan['identity_sha256'], config=GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0), budget=TileBudget())
            coarse, fine = (pair['coarse'], pair['fine'])
            cv, fv = (_independent_volume(coarse), _independent_volume(fine))
            relative = abs(cv - fv) / max(fv, 1e-12)
            if relative > 0.02:
                raise ValueError('tiled spatial refinement exceeds fixed two percent gate')
            for label, bundle in (('coarse', coarse), ('fine', fine)):
                name = f'component-{component_index:03d}-{label}'
                save_tiled_monotone_union(output / f'{name}.npz', bundle)
                sha = file_sha256(output / f'{name}.npz')
                cold = _cold_load(output / f'{name}.npz', sha, bundle['identity_sha256'])
                _independent_volume(cold)
                artifacts[name] = {'path': f'{name}.npz', 'sha256': sha, 'identity_sha256': bundle['identity_sha256']}
            fine_refs.append((output / f'component-{component_index:03d}-fine.npz', artifacts[f'component-{component_index:03d}-fine']['sha256'], fine['identity_sha256']))
            accepted_edges.extend(map(int, edges))
            record.update(status='accepted_connected_component', spatial_refinement_relative=relative, cut_volume_m3=fv, tile_count=fine['metadata']['tile_count'])
        except (ValueError, AssertionError) as error:
            record.update(status='refused_connected_component', reason=str(error))
        del pair, coarse, fine
        gc.collect()
        records[str(component_index)] = record
        _write_progress(output / 'progress.json', {'status': 'incomplete_progress', 'component_records': records, 'artifacts': artifacts, 'eligible_edges': len(eligible), 'preflight': preflight})
        print(json.dumps({'component': component_index, 'edges': len(edges), 'status': record['status']}), flush=True)
    ledger_error = None
    ledger = None
    try:
        ledger = _unique_ledger(_load_ledger_bundles(fine_refs))
    except (ValueError, AssertionError) as error:
        ledger_error = str(error)
    accepted_set = set(accepted_edges)
    if len(accepted_set) != len(accepted_edges):
        ledger_error = ledger_error or 'duplicate global edge ownership'
    assignment = np.full(receiver.size, -1, np.int64)
    for cell in plan['arrays']['graph_order_downstream_first']:
        target = receiver[cell]
        assignment[cell] = int(cell) if int(cell) in accepted_set else assignment[target] if target >= 0 else -1
    local = source['arrays']['local_q_m3_s'].reshape(len(source['arrays']['time_seconds']) - 1, -1)
    dt = np.diff(source['arrays']['time_seconds'])
    assigned = float(np.sum(local[:, assignment >= 0] * dt[:, None]))
    unresolved = float(np.sum(local[:, assignment < 0] * dt[:, None]))
    all_components_accepted = all((row['status'] == 'accepted_connected_component' for row in records.values()))
    complete = len(accepted_set) == len(plan['arrays']['selected_edge_source_ids']) and (not ledger_error) and all_components_accepted
    report = {'status': 'accepted_global_tiled_geometry' if complete else 'candidate_incomplete_global_geometry', 'declared_selected_edges': int(len(plan['arrays']['selected_edge_source_ids'])), 'eligible_edges': len(eligible), 'accepted_global_edges': len(accepted_set), 'coverage_fraction': len(accepted_set) / max(1, len(plan['arrays']['selected_edge_source_ids'])), 'component_records': records, 'component_status': dict(Counter((row['status'] for row in records.values()))), 'preflight': preflight, 'preflight_reasons': dict(Counter((row.get('reason') for row in preflight if 'reason' in row))), 'source': {'path': str(TD_DIRECTORY / 'product.npz'), 'sha256': TD_PRODUCT_SHA, 'identity_sha256': TD_PRODUCT_ID}, 'parent_network_plan': pin, 'artifacts': artifacts, 'unique_material_ledger': ledger, 'ledger_error': ledger_error, 'code_sha256': code_pins, 'native_local_source_accounting': {'assigned_volume_m3': assigned, 'unresolved_or_outside_coverage_volume_m3': unresolved, 'assignment_exactly_once': True}, 'shape_statistics': shape_statistics(plan['arrays']['selected_edge_source_ids'], receiver, terrain.elevation_m.shape[1], terrain), 'geometry_verified': complete, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False, 'limitations': ['natural_lake_connections_pending_common_stage_support', 'unresolved_and_refused_edges_are_retained_in_component_records']}
    if any((file_sha256(ROOT / path) != sha for path, sha in code_pins.items())):
        raise AssertionError('verification code changed during run')
    report_name = 'acceptance.json' if complete else 'failure-prefix.json'
    publish_bytes(output / report_name, json.dumps(report, indent=2, allow_nan=False).encode())
    return report
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    result = verify(parser.parse_args().output)
    print(json.dumps({key: result[key] for key in ('status', 'declared_selected_edges', 'accepted_global_edges', 'coverage_fraction')}))
