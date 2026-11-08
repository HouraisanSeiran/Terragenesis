"""Finite native backwater and honest world environment publication contracts."""
import pytest
import numpy as np
from pathlib import Path
import json

from terrain_pipeline import world_processes
from terrain_pipeline.world_process_backwater import solve_native_backwater
from terrain_pipeline.world_process_detail import solve_native_reach, apply_replacements
from tests.test_world_process_detail import coarse_product, native_fixture


def test_environment_stage_requires_generation_and_final_seasonal_processes():
    generation = dict(status='complete', processes=dict(weathering=dict(status='computed')))
    final = dict(processes=dict(snow=dict(status='computed'), volcanism=dict(status='not-triggered')))
    assert world_processes._environment_stage(generation, final) == 'complete'
    for status in ('pending-input', 'pending-preparation', 'pending-geological-event', 'partial-or-pending'):
        final['processes']['glacier'] = dict(status=status)
        assert world_processes._environment_stage(generation, final) == 'partial-or-pending'
    final['processes'].pop('glacier')
    generation['status'] = 'pending-input'
    assert world_processes._environment_stage(generation, final) == 'partial-or-pending'
    assert world_processes._environment_stage(dict(status='complete'), {}) == 'partial-or-pending'


def test_generation_complete_does_not_hide_pending_final_seasonal_processes(monkeypatch, tmp_path):
    def seasons(source, bed, *args, **kwargs):
        shape = bed.shape
        return dict(arrays=dict(monthly_runoff_m3=np.zeros((12,)+shape), temperature_c=np.full(shape,10.),
            soil_water_mm=np.zeros(shape), cover_fraction=np.zeros(shape),
            monthly_weathered_rock_m=np.zeros((12,)+shape),wind_x_m_s=np.zeros(shape),wind_z_m_s=np.zeros(shape)),
            metadata=dict(processes=dict(glacier=dict(status='pending-preparation'),groundwater=dict(status='pending-input'))))
    monkeypatch.setattr(world_processes, '_seasons', seasons)
    zz,xx = np.indices((8,8))
    bed = 500.-zz*30.-xx*15.
    source = dict(elevation_m=bed, ocean_mask=np.zeros(bed.shape,bool),first_xz_m=[1000.,1000.],
        spacing_m=2000.,world_seed=20260903,source_identity='a'*64,
        materials=dict(porosity=np.full(bed.shape,.35),erodibility=np.full(bed.shape,.8)))
    result = world_processes.compute(source,dict(shaping_rounds=1))
    assert result['metadata']['generation_environment']['status'] == 'complete'
    assert result['metadata']['stages']['environment'] == 'partial-or-pending'
    world_processes.save_product(result,tmp_path/'world')
    loaded = world_processes.query(tmp_path/'world')
    assert loaded['metadata']['stages']['environment'] == 'partial-or-pending'
    assert loaded['metadata']['environment']['processes']['groundwater']['status'] == 'pending-input'


def storage_fixture(*, sea=False):
    p = coarse_product()
    row = col = 67
    zz, xx = np.indices((513, 513))
    bed = (100.+.03*((xx-col)**2+(zz-row)**2)).astype(np.float32)
    if sea:
        bed[row, :col+3] = -12.
    p['arrays']['lake_id'][1, 1] = 7
    p['arrays']['generation_transported_solid_m3'][:] = 1.e6
    region = dict(id='original', node=9, coarse_support_id='original-support',
        kind='lake_port', location_xz_m=[3010.,3010.])
    terrain = dict(elevation_m=bed, identity='c'*64, binding=dict(saved='fixture'),
        grid=dict(first_sample_xz_m=[1000.,1000.], spacing_m=30., shape_zx=[513,513]))
    return p, region, terrain


def independent_ledger(detail):
    h, s, native = detail['hydraulic']['arrays'], detail['sediment']['arrays'], detail['native_arrays']
    left, right, boundary = h['face_left'], h['face_right'], h['boundary_cell']
    n = len(native['node'])
    area = 30.**2
    assert np.all(h['boundary_kind'] == 0)
    assert np.all(h['interval_boundary_transfer_m3'] == 0.)
    source = np.zeros(n)
    inlet = int(native['original_inlet_cell'][0])
    for index, (before, after, face, outer, delivered) in enumerate(zip(
            h['interval_depth_before_m'], h['interval_depth_after_m'], h['interval_internal_transfer_m3'],
            h['interval_boundary_transfer_m3'], h['interval_forcing_volume_m3'])):
        net = np.bincount(right, weights=face, minlength=n)-np.bincount(left, weights=face, minlength=n)
        net -= np.bincount(boundary, weights=outer, minlength=n)
        np.testing.assert_allclose(area*(after-before), delivered+net, atol=1e-8, rtol=1e-9)
        source[:] = 0.
        source[inlet] = s['interval_external_solid_m3'][index]
        sf = s['interval_internal_transfer_solid_m3'][index]
        se = s['interval_boundary_export_solid_m3'][index]
        total_before = ((s['trace_bed_elevation_m'][index]-s['floor_m'])*area*(1-detail['sediment']['metadata']['porosity'])
                        +s['trace_mobile_solid_m3'][index]).ravel()
        total_after = ((s['trace_bed_elevation_m'][index+1]-s['floor_m'])*area*(1-detail['sediment']['metadata']['porosity'])
                       +s['trace_mobile_solid_m3'][index+1]).ravel()
        net_solid = np.bincount(right, weights=sf, minlength=n)-np.bincount(left, weights=sf, minlength=n)
        net_solid -= np.bincount(boundary, weights=se, minlength=n)
        np.testing.assert_allclose(total_after-total_before, source+net_solid, atol=1e-8, rtol=1e-8)
    assert h['interval_forcing_volume_m3'].sum() == pytest.approx(detail['boundary_package']['water_m3'])
    assert s['interval_external_solid_m3'].sum() == pytest.approx(detail['boundary_package']['solid_m3'])
    assert np.all(s['final_bed_m'] >= s['floor_m']-1e-10)
    assert np.min(s['trace_mobile_solid_m3']) >= 0.
    assert all(np.isfinite(v).all() for v in detail['replacement_arrays'].values())


def test_adverse_native_lake_uses_finite_storage_and_unchanged_exact_inlet():
    p, r, terrain = storage_fixture()
    original = terrain['elevation_m'].copy()
    result = solve_native_reach(p, r, terrain, config=dict(detail_duration_s=2.,backwater_window_cells=16))
    assert result['status'] == 'complete'
    assert result['kind'] == r['kind'] and result['region_id'] == r['id']
    assert result['downstream_boundary']['kind'] == 'finite-closed-control-volume'
    assert result['downstream_boundary']['coarse_lake_water_consumed_m3'] == 0.
    assert result['budgets']['initial_water_m3'] == 0.
    assert result['budgets']['solver_water_storage_change_m3'] == pytest.approx(result['boundary_package']['water_m3'])
    assert result['metadata']['inlet_xz_m'] == r['location_xz_m']
    assert 'not full downstream or seasonal lake equilibrium' in result['limitations'][0]
    np.testing.assert_array_equal(terrain['elevation_m'], original)
    independent_ledger(result)
    _, consumed = apply_replacements(p['arrays'], [result])
    with pytest.raises(ValueError, match='counted twice'):
        apply_replacements(p['arrays'], [result], consumed_package_ids=consumed)


def test_full_native_connected_sea_is_only_finite_initial_inventory():
    p, r, t = storage_fixture(sea=True)
    r['kind'] = 'river_reach'
    p['arrays']['lake_id'][:] = 0
    result = solve_native_reach(p, r, t, config=dict(detail_duration_s=2.,backwater_window_cells=16))
    assert result['kind'] == 'river_reach'
    assert result['downstream_boundary']['sea_connected_at_original_inlet']
    assert result['budgets']['initial_water_m3'] > 0.
    assert result['budgets']['solver_water_export_m3'] == 0.
    independent_ledger(result)
    # The same negative pocket touching only the cropped rim is not ocean.
    t['elevation_m'][67, :50] = 100.
    closed = solve_native_backwater(p, r, t, config=dict(detail_duration_s=2.,backwater_window_cells=16))
    assert not closed['downstream_boundary']['sea_connected_at_original_inlet']
    assert closed['budgets']['initial_water_m3'] == 0.


def test_closed_event_publishes_through_existing_detail_contract_and_cold_read(tmp_path):
    product = coarse_product()
    product['details'] = [dict(id='lake',node=9,coarse_support_id='lake-support',kind='lake_port',
        location_xz_m=[3010.,3010.],status='pending-terrain')]
    entry = native_fixture(tmp_path)
    world_processes.save_product(product,tmp_path/'preview')
    result = world_processes.continue_details(tmp_path/'preview',tmp_path/'fine',terrain_entries=[entry],
        config=dict(detail_duration_s=2.,backwater_window_cells=16))
    assert result['details'][0]['status'] == 'complete'
    assert 'short event' in result['details'][0]['completed_scope']
    assert 'unresolved' in result['details'][0]['reason']
    assert len(result['consumed_package_ids']) == 1
    assert abs(result['metadata']['solid_budget']['residual_m3']) < 1e-6
    loaded = world_processes.query(tmp_path/'fine')
    assert loaded['details'][0]['completed_scope'] == result['details'][0]['completed_scope']
    with np.load(tmp_path/'fine/detail-lake/hydraulic.npz',allow_pickle=False) as archive:
        assert 'interval_internal_transfer_m3' in archive.files
        assert np.all(archive['boundary_kind'] == 0)
    (tmp_path/'fine/detail-lake/hydraulic.npz').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='detail file SHA'):
        world_processes.query(tmp_path/'fine')


@pytest.mark.parametrize('options', [dict(max_backwater_cells=65537),dict(backwater_window_cells=257),
    dict(max_backwater_cells=64,backwater_window_cells=16),dict(backwater_interval_s=0.),
    dict(backwater_window_cells=256,backwater_interval_s=.01),dict(detail_duration_s=301.)])
def test_storage_resources_and_interval_refuse_before_solving(options):
    p, r, t = storage_fixture()
    with pytest.raises(ValueError):
        solve_native_backwater(p,r,t,config=options)


SAVED_ROOT = Path(__file__).resolve().parents[2]/'\u7ec7\u68a6/artifacts/fast-world/world-process-20261107-detail'


@pytest.mark.skipif(not (SAVED_ROOT/'continuation.json').exists(), reason='original same-source TD delivery unavailable')
def test_original_three_immutable_native_tasks_with_independent_cell_ledgers():
    from terrain_pipeline.common_infra import file_sha256
    from terrain_pipeline.world_process_detail import load_native_terrain
    product = world_processes.query(SAVED_ROOT/'world-processes')
    continuation = json.loads((SAVED_ROOT/'continuation.json').read_text(encoding='utf-8'))
    terrains = []
    for entry in continuation['terrain']:
        path = Path(entry['manifest_path'])
        manifest = json.loads(path.read_text(encoding='utf-8'))
        terrains.append(load_native_terrain(dict(manifest_path=str(path), manifest_sha256=file_sha256(path)),
            source_identity=product['metadata'].get('plate_identity',manifest['plate_identity']), world_seed=product['metadata']['world_seed'],
            island_provenance=product['metadata'].get('island_provenance')))
    original_ids = {'d23414367e6e956d7120a58e570b36ea19db1f52210f89d19ba4c3676d182755',
        '89b22c7897a5c77d61c916ebf66769269064fccef985b3b0cccba1a5195fd721',
        'ce4dad6333227a843db08defb259e0a397b1da7d13cd25ebd037b8de04383b90'}
    selected = [r for r in product['details'] if r['id'] in original_ids]
    assert {r['id'] for r in selected} == original_ids
    for region in selected:
        x,z = region['location_xz_m']
        matches = [t for t in terrains if t['grid']['first_sample_xz_m'][0] <= x <= t['grid']['first_sample_xz_m'][0]+15360
            and t['grid']['first_sample_xz_m'][1] <= z <= t['grid']['first_sample_xz_m'][1]+15360]
        terrain = sorted(matches,key=lambda t:t['identity'])[0]
        before = np.asarray(terrain['elevation_m']).copy()
        result = solve_native_reach(product,region,terrain)
        assert result['status'] == 'complete'
        assert result['region_id'] == region['id'] and result['terrain_identity'] == terrain['identity']
        assert result['metadata']['cells'] <= 65536
        assert result['metadata']['inlet_xz_m'] == region['location_xz_m']
        assert max(abs(v) for v in result['metadata']['inlet_point_to_cell_center_offset_xz_m']) <= 15.
        assert result['budgets']['water_residual_m3'] == pytest.approx(0.,abs=1e-6)
        assert result['budgets']['solid_residual_m3'] == pytest.approx(0.,abs=1e-6)
        assert result['budgets']['eroded_rock_m3'] == 0.
        assert result['sediment']['metadata']['initial_rock_reserve_m3'] == result['sediment']['metadata']['final_rock_reserve_m3']
        np.testing.assert_array_equal(terrain['elevation_m'],before)
        independent_ledger(result)
