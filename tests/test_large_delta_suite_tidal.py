import json
import numpy as np
import pytest
from terrain_pipeline.large_delta_suite_tidal import prepare, run_case, _stages, _project


def make_case(path, spacing=100., origin=(1000., -4000.)):
    shape = (30, 30)
    rows = np.arange(8, 21)
    columns = np.full(len(rows), 15)
    sections = np.column_stack((np.zeros(len(rows)), origin[0]+columns*spacing,
                                origin[1]+rows*spacing, rows, columns,
                                np.linspace(.5, .1, len(rows)), np.full(len(rows), 40.),
                                np.ones(len(rows)), np.full(len(rows), 10.)))
    bed = np.full(shape, -1.)
    valid = np.ones(shape, bool)
    valid[3, 3] = False
    bed[3, 3] = 1234.
    ocean = np.ones(shape, bool)
    case = dict(final_bed_m=bed, valid=valid, ocean=ocean, sections=sections, parent=np.array([-1]))
    manifest = {'source': {'spacing_m': spacing, 'origin_xz_m': list(origin), 'source_identity': 'fixture'},
                'scenario': {'porosity': .4, 'discharge_m3_s': 10.}}
    path.mkdir()
    np.savez_compressed(path/'product.npz', **case)
    (path/'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    return case, manifest


def test_area_and_world_coordinates(tmp_path):
    a, m = make_case(tmp_path/'a')
    b, n = make_case(tmp_path/'b', origin=(45000., 80000.))
    p = prepare(a, m, hydro_spacing_m=500, reach_length_m=400)
    q = prepare(b, n, hydro_spacing_m=500, reach_length_m=400)
    assert np.array_equal(p['owner'], q['owner'])
    assert np.allclose(p['fraction'], q['fraction'])
    assert p['river_area'].sum() == pytest.approx(1200*40)
    assert np.all(p['coast_area'] + p['river_area'] <= 10000. + 1e-8)
    assert np.all(p['fraction'] <= 1)
    assert np.all(p['owner'][~p['local_valid']] == -1)
    assert not np.any(p['river_blocks'].ravel()[p['boundary']])


def test_event_conserves_and_respects_floor(tmp_path):
    case, manifest = make_case(tmp_path/'case')
    output = tmp_path/'out'
    result = run_case(tmp_path/'case', output, hours=.1, hydro_spacing_m=500,
                      reach_length_m=400, dt_s=30, relaxation_iterations=3)
    ledger = result['ledger']
    assert abs(ledger['water_residual_m3']) < 1e-5
    assert abs(ledger['solid_residual_m3']) < 1e-5
    assert abs(ledger['native_water_error_m3']) < 1e-5
    assert ledger['native_bed_delta_solid_m3'] == pytest.approx(ledger['graph_bed_delta_solid_m3'], abs=1e-5)
    with np.load(output/'native.npz') as native, np.load(output/'checkpoint.npz') as state:
        assert np.all(native['bed_m'][case['valid']] >= case['final_bed_m'][case['valid']]-.25-1e-10)
        assert native['bed_m'][3, 3] == 1234.
        assert not native['coverage'][3, 3]
        assert np.all(state['bed_solid_m3'] >= -1e-9)
    from terrain_pipeline.large_delta_tidal_dynamics import load_checkpoint
    geometry = prepare(case, manifest, hydro_spacing_m=500, reach_length_m=400)
    saved = load_checkpoint(output/'checkpoint.npz')
    with np.load(output/'node_state.npz') as nodes:
        assert nodes['stage_m'] == pytest.approx(_stages(geometry, saved)[0])
        assert nodes['coast_node_count'] == geometry['n']
    with pytest.raises(FileExistsError):
        run_case(tmp_path/'case', output, hours=.1)


def test_subpixel_river_bed_and_stage_use_section_geometry(tmp_path):
    case, manifest = make_case(tmp_path/'case')
    # Coarse side pixels may be high land; they must not become a riverbed
    # merely because analytic channel area spills across a pixel boundary.
    case['final_bed_m'][:] = 20.
    case['sections'] = np.column_stack((case['sections'], np.full(len(case['sections']), -1.)))
    p = prepare(case, manifest, hydro_spacing_m=500, reach_length_m=400)
    assert np.max(p['base'][p['n']:]) == pytest.approx(-1.)
    graph_stage = _stages(p, p['state'])[0][p['n']:]
    native = _project(p, p['state'], 0)
    for i, expected in enumerate(graph_stage):
        assert native['river_stage_m'][p['owner'] == i] == pytest.approx(expected)

    # A partially wet reach must use the same subpixel storage curve in the
    # solver and the mapped river, rather than a mean-bed approximation.
    case['sections'][:, 9] = np.linspace(-2., 1., len(case['sections']))
    p = prepare(case, manifest, hydro_spacing_m=500, reach_length_m=400)
    p['state'].water_m3[p['n']:] *= .05
    graph_stage = _stages(p, p['state'])[0][p['n']:]
    native = _project(p, p['state'], 0)
    for i, expected in enumerate(graph_stage):
        assert native['river_stage_m'][p['owner'] == i] == pytest.approx(expected)


def test_coarse_source_and_large_forcing_smoke(tmp_path):
    case_dir = tmp_path/'coarse'
    case, manifest = make_case(case_dir, spacing=600., origin=(60000., -90000.))
    case['sections'][:, 6] = 900.
    case['sections'][:, 8] = 18000.
    case['sections'] = np.column_stack((case['sections'], np.full(len(case['sections']), -1.)))
    manifest['scenario']['discharge_m3_s'] = 18000.
    np.savez_compressed(case_dir/'product.npz', **case)
    (case_dir/'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    p = prepare(case, manifest, hydro_spacing_m=600, reach_length_m=1200)
    assert p['river_area'].sum() == pytest.approx(12 * 600 * 900)
    assert not np.any(p['river_blocks'].ravel()[p['boundary']])
    weighted = prepare(case, manifest, hydro_spacing_m=600, reach_length_m=1200, calibration='weighted')
    assert weighted['coefficient'] == pytest.approx(p['coefficient'])
    result = run_case(case_dir, tmp_path/'out', hours=.05, dt_s=2.5, reach_length_m=1200,
                      relaxation_iterations=2)
    assert result['source_spacing_m'] == 600.
    assert result['forcing']['discharge_m3_s'] == 18000.
    assert result['ledger']['source_water_m3'] == pytest.approx(18000 * 180)
    assert abs(result['ledger']['water_residual_m3']) < .01
    assert abs(result['ledger']['solid_residual_m3']) < .01
    assert result['ledger']['native_bed_delta_solid_m3'] == pytest.approx(
        result['ledger']['graph_bed_delta_solid_m3'], abs=1e-4)


def test_weighted_conveyance_accounts_for_main_channel_discharge(tmp_path):
    case, manifest = make_case(tmp_path/'case')
    main = case['sections'].copy()
    main[:, 6] = 100.
    main[:, 8] = 100.
    branch = main.copy()
    branch[:, 0] = 1
    branch[:, 1] += 300.
    branch[:, 4] += 3
    branch[:, 8] = 1.
    case['sections'] = np.r_[main, branch]
    case['parent'] = np.array([-1, 0])
    median = prepare(case, manifest, hydro_spacing_m=500, reach_length_m=400)
    weighted = prepare(case, manifest, hydro_spacing_m=500, reach_length_m=400, calibration='weighted')
    assert weighted['coefficient'] > median['coefficient'] * 1.5
    assert weighted['coefficient'] <= 100.



def test_implicit_manning_exchange_keeps_crest_and_solids():
    from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step
    # The downstream bed is a 1 m sill. No more than the 1 m above the
    # sill may drain from the first cell, regardless of a long interval.
    geom = Geometry(np.array([100., 100.]), np.array([0., 1.]),
                    np.array([0]), np.array([1]), np.array([1.]),
                    np.array([], int), np.array([]), .4,
                    np.array([0]), np.array([10.]), np.array([100.]))
    state = State(0., np.array([200., 0.]), np.zeros(2), np.array([2., 0.]))
    stage = np.array([2., 1.])
    step(geom, state, 1000., 0., 0, 0., 0., stage_override=stage,
         storage_area=np.array([100., 100.]),
         crest_available=lambda donor, crest: np.maximum(state.water_m3[donor] - 100*crest, 0.))
    assert state.water_m3[0] >= 100. - 1e-10
    assert state.water_m3.sum() == pytest.approx(200.)
    assert np.min(state.water_m3) >= 0.
    assert np.min(state.mobile_solid_m3) >= 0.
    assert state.mobile_solid_m3.sum() + state.bed_solid_m3.sum() == pytest.approx(2.)
    assert state.water_m3[1] > 0.


def test_boundary_outflow_respects_volume_below_crest():
    from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step
    geom = Geometry(np.array([100.]), np.array([1.]), np.array([], int),
                    np.array([], int), np.array([]), np.array([0]), np.array([100.]))
    state = State(0., np.array([60.]), np.zeros(1), np.array([3.]))
    packet = step(geom, state, 1000., 0., 0, 0., 0., stage_override=np.array([1.2]),
                  storage_area=np.array([50.]),
                  crest_available=lambda donor, crest: np.maximum(state.water_m3[donor] - 50., 0.))
    assert state.water_m3[0] == pytest.approx(50.)
    assert packet['boundary_water_m3'].sum() == pytest.approx(10.)
    assert state.mobile_solid_m3[0] >= 0.
    assert state.sea_solid_out_m3 + state.mobile_solid_m3.sum() + state.bed_solid_m3.sum() == pytest.approx(3.)


def test_bank_weir_moves_only_available_water_above_sill():
    from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step
    geom = Geometry(np.array([100., 100.]), np.array([0., 0.]),
                    np.array([0]), np.array([1]), np.array([1.]),
                    np.array([], int), np.array([]), .4,
                    bank_faces=np.array([0]), bank_length_m=np.array([100.]))
    state = State(0., np.array([200., 50.]), np.zeros(2), np.zeros(2))
    step(geom, state, 100., 0., 0, 0., 0., stage_override=np.array([2., .5]),
         storage_area=np.array([100., 100.]), face_crest_offset=np.array([1.]),
         crest_available=lambda donor, crest: np.maximum(state.water_m3[donor] - 100*crest, 0.))
    assert 100. <= state.water_m3[0] < 200.
    assert state.water_m3.sum() == pytest.approx(250.)
    assert state.water_m3[1] > 50.


def test_coastal_face_uses_wet_manning_section_and_real_width():
    from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step
    geom = Geometry(np.array([100., 100.]), np.zeros(2), np.array([0]), np.array([1]),
                    np.array([0.]), np.array([], int), np.array([]),
                    coast_faces=np.array([0]), coast_width_m=np.array([10.]), coast_distance_m=100.)
    state = State(0., np.array([200., 100.]), np.zeros(2), np.zeros(2))
    packet = step(geom, state, .01, 0., 0, 0., 0., storage_area=np.array([100., 100.]))
    area = 20.
    radius = area / 14.
    expected_q = area * radius**(2/3) / .04 * np.sqrt(1./100.)
    assert packet['internal_water_m3'][0] == pytest.approx(expected_q*.01)
    assert state.water_m3.sum() == pytest.approx(300.)


def test_high_crest_does_not_block_competing_lower_outlet():
    from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step
    geom = Geometry(np.full(3, 100.), np.zeros(3), np.array([0, 0]), np.array([1, 2]),
                    np.ones(2), np.array([], int), np.array([]))
    state = State(0., np.array([200., 0., 0.]), np.zeros(3), np.zeros(3))
    packet = step(geom, state, 10., 0., 0, 0., 0., face_crest_offset=np.array([1.9, 0.]),
                  crest_available=lambda donor, crest: np.maximum(state.water_m3[donor]-100*crest, 0.))
    assert packet['internal_water_m3'][0] == pytest.approx(5.)
    assert packet['internal_water_m3'][1] == pytest.approx(20.)
    assert state.water_m3.sum() == pytest.approx(200.)



def test_narrow_diagonal_coastal_path_and_real_barrier():
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from terrain_pipeline.large_delta_suite_tidal import _coastal_subgrid_faces
    # A one-pixel sea channel crosses coarse-cell corners, while all other
    # terrain is high. Raising one genuine native pixel must block the path.
    bed = np.full((4, 6), 8.)
    ocean = np.zeros_like(bed, dtype=bool)
    path = [(1, 1), (2, 2), (1, 3), (2, 4)]
    for row, col in path:
        bed[row, col] = -2.
        ocean[row, col] = True
    area = np.full_like(bed, 100.)
    def reaches_other_end(heights):
        faces, _ = _coastal_subgrid_faces(heights, area, ocean, 2, 10.)
        wet = [(a, b) for a, b, crest, width, _ in faces if crest < 0 and width > 0]
        left = np.array([a for a, _ in wet], dtype=int)
        right = np.array([b for _, b in wet], dtype=int)
        graph = coo_matrix((np.ones(2*len(left)), (np.r_[left, right], np.r_[right, left])), shape=(6, 6))
        _, labels = connected_components(graph, directed=False)
        return labels[0] == labels[5]
    def delivered_water(heights):
        from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, step
        faces, levels = _coastal_subgrid_faces(heights, area, ocean, 2, 10.)
        floor = np.array([np.min(levels[r:r+2, c:c+2])
                          for r in (0, 2) for c in (0, 2, 4)])
        left = np.array([f[0] for f in faces], dtype=int)
        right = np.array([f[1] for f in faces], dtype=int)
        crest = np.array([f[2] for f in faces])
        geom = Geometry(np.full(6, 1000.), floor, left, right, np.zeros(len(faces)),
                        np.array([], int), np.array([]), coast_faces=np.arange(len(faces)),
                        coast_width_m=np.array([f[3] for f in faces]),
                        coast_distance_m=np.array([f[4] for f in faces]))
        state = State(0., np.array([1000., 0., 0., 0., 0., 0.]), np.zeros(6), np.zeros(6))
        for _ in range(2000):
            step(geom, state, .1, 0., 0, 0., 0., storage_area=geom.area_m2,
                 face_crest_offset=crest-np.maximum(floor[left], floor[right]))
        assert state.water_m3.sum() == pytest.approx(1000.)
        return state.water_m3[5]
    assert reaches_other_end(bed)
    assert delivered_water(bed) > 1.
    bed[1, 3] = 6.
    assert not reaches_other_end(bed)
    assert delivered_water(bed) == 0.


def test_disconnected_subpixel_pocket_does_not_make_nonfinite_face():
    from terrain_pipeline.large_delta_suite_tidal import _coastal_subgrid_faces
    bed = np.full((3, 6), -2.)
    area = np.zeros_like(bed)
    area[0, 0] = area[2, 2] = area[2, 3] = 100.
    ocean = area > 0
    faces, levels = _coastal_subgrid_faces(bed, area, ocean, 3, 10.)
    assert np.isinf(levels[2, 2])
    assert faces == []


def test_seeded_continuation_restart_phase_and_inventory(tmp_path):
    from dataclasses import replace
    from terrain_pipeline.large_delta_tidal_dynamics import State, bed_elevation
    from terrain_pipeline.large_delta_suite_tidal import (
        prepare_continuation, bind_continuation, advance_prepared, save_continuation_checkpoint,
        load_continuation_checkpoint,
    )
    case, manifest = make_case(tmp_path/'case')
    case['final_bed_m'][6, 6] = .5
    default = prepare(case, manifest, hydro_spacing_m=500, reach_length_m=400)
    reference = default['stock'] * .6
    p = bind_continuation(default, reference, source_identity='fixture')
    rebuilt = prepare_continuation(case, manifest, reference, source_identity='fixture',
                                   hydro_spacing_m=500, reach_length_m=400)
    assert p['geometry_id'] == rebuilt['geometry_id']
    explicit_floor = bind_continuation(default, reference, source_identity='fixture', floor_m=p['floor'])
    assert explicit_floor['geometry_id'] == p['geometry_id']
    assert p['state'] is None and default['state'] is not None
    mobile = np.zeros_like(reference)
    mobile[p['n']] = 7.5
    original = State(1234.5, default['state'].water_m3.copy(), reference.copy(), mobile,
                     sea_water_in_m3=71., sea_water_out_m3=11., sea_solid_out_m3=2.,
                     source_water_m3=53., source_solid_m3=3.)
    assert bed_elevation(p['geom'], original) == pytest.approx(p['base'])
    assert np.allclose(_project(p, original, 0)['bed_m'][p['local_valid']], p['local_bed'][p['local_valid']])
    kwargs = dict(source_identity='fixture', geometry_id=p['geometry_id'], dt_s=5.,
                  source_water_m3_s=10., source_solid_m3_s=.02)
    whole = advance_prepared(p, original, duration_s=180., **kwargs)
    first = advance_prepared(p, original, duration_s=60., **kwargs)
    checkpoint = tmp_path/'checkpoint.npz'
    save_continuation_checkpoint(checkpoint, p, first['state'])
    with pytest.raises(FileExistsError):
        save_continuation_checkpoint(checkpoint, p, first['state'])
    loaded = load_continuation_checkpoint(checkpoint, p, source_identity='fixture')
    second = advance_prepared(p, loaded, duration_s=120., **kwargs)
    assert original.time_s == 1234.5
    assert np.array_equal(original.bed_solid_m3, reference)
    assert original.mobile_solid_m3[p['n']] == 7.5
    assert whole['start_time_s'] == 1234.5
    assert whole['end_time_s'] == second['end_time_s'] == 1414.5
    for key in vars(original):
        assert np.array_equal(getattr(whole['state'], key), getattr(second['state'], key))
    for key in whole['exchanges']:
        assert whole['exchanges'][key] == pytest.approx(first['exchanges'][key] + second['exchanges'][key], abs=1e-8)
    assert whole['ledger']['initial_mobile_solid_m3'] == pytest.approx(7.5)
    assert whole['ledger']['initial_solid_m3'] == pytest.approx(reference.sum()+7.5)
    assert whole['ledger']['source_water_m3'] == pytest.approx(1800.)
    assert whole['ledger']['source_solid_m3'] == pytest.approx(3.6)
    assert abs(whole['ledger']['water_residual_m3']) < 1e-6
    assert abs(whole['ledger']['solid_residual_m3']) < 1e-6
    assert whole['node_stage_m'] == pytest.approx(_stages(p, whole['state'])[0])
    naive = whole['node_bed_m'][:p['n']] + whole['node_water_depth_m'][:p['n']]
    assert np.max(np.abs(whole['node_stage_m'][:p['n']] - naive)) > 1e-3
    assert len(whole['node_stage_m']) == len(p['geom'].area_m2)
    assert whole['node_water_depth_m'] == pytest.approx(whole['state'].water_m3/p['geom'].area_m2)
    at_zero = advance_prepared(p, replace(original, time_s=0.), duration_s=180., **kwargs)
    assert np.max(np.abs(whole['node_stage_m']-at_zero['node_stage_m'])) > 1e-5
    with pytest.raises(ValueError, match='identity'):
        advance_prepared(p, original, duration_s=5., **{**kwargs, 'geometry_id': 'wrong'})
    with pytest.raises(ValueError, match='identity'):
        load_continuation_checkpoint(checkpoint, p, source_identity='wrong')
    with pytest.raises(ValueError, match='source identity'):
        bind_continuation(default, reference, source_identity='wrong')
    different = bind_continuation(default, reference * .9, source_identity='fixture')
    assert different['geometry_id'] != p['geometry_id']
    with pytest.raises(ValueError, match='identity'):
        load_continuation_checkpoint(checkpoint, different, source_identity='fixture')
    with pytest.raises(ValueError, match='state'):
        advance_prepared(p, replace(original, water_m3=original.water_m3[:-1]), duration_s=5., **kwargs)
    with pytest.raises(ValueError, match='floor'):
        prepare_continuation(case, manifest, reference, source_identity='fixture',
                             floor_m=p['floor']+1., hydro_spacing_m=500, reach_length_m=400)
