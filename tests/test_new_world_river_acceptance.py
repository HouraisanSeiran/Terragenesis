import numpy as np
import pytest

from terrain_pipeline import new_world_river_acceptance as acceptance
from terrain_pipeline.new_world_rivers import solve_finite_hydraulics
from test_new_world_river_scene import event
from test_new_world_rivers import hydraulic_inputs


def test_native_event_unknown_refused_and_pins_checked(event):
    path, common, result, _ = event
    mouth = next(r['mouth_id'] for r in result['outlets'] if r['kind'] == 'marine')
    args = dict(common, origin_native_xz=[-10, 20], shape_zx=[12, 13], width_m=1.,
                max_depth_m=2., roughness=.04, downstream_stage_m=0., mouth_id=mouth)
    report, solved = acceptance.run(path, **args)
    assert report['status'] == 'unresolved'
    assert 'total water unknown' in report['failures']
    assert report['full_chosen_path_parent_indices']
    assert not report['verified_subset_parent_indices'] and solved is None
    with pytest.raises(ValueError):
        acceptance.run(path, **dict(args, expected_water_identity='f' * 64))


def test_real_solver_replay_and_incremental_input():
    args = hydraulic_inputs()
    args['time_seconds'][-1] = 100.
    args['local_volume_m3'][0] = [.1, .2, .3, .4]
    result = solve_finite_hydraulics(**args)
    assert result['metadata']['status'] == 'complete'
    network, forcing, initial, config = acceptance.replay_inputs(result)
    assert np.isclose((forcing.local_q_m3_s * 100).sum(), 1.)
    assert result['metadata']['water_ledger']['input_m3'] == pytest.approx(1.)
    assert network.receiver.size > 4
    assert not initial.any()
    assert config.max_dt_seconds > 0


def test_serialized_replay_to_real_sediment(tmp_path):
    from terrain_pipeline import new_world_river_scene as scene
    from terrain_pipeline.new_world_sediment import produce_supply
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
    args = hydraulic_inputs()
    args['time_seconds'][-1] = 100.
    args['local_volume_m3'][0] = [.1, .2, .3, .4]
    result = solve_finite_hydraulics(**args)
    water_id = result['metadata']['source_identity_sha256']
    sm = dict(terrain_identity='a'*64, planner_identity='b'*64, water_identity=water_id, mouth_id='mouth', known_mouth_volume_m3=1., mouth_total_water_unknown=False)
    sources = dict(terrain=sm['terrain_identity'], planner=sm['planner_identity'], water=water_id, scene=scene._identity(sm))
    report = dict(status='physical_solve_complete_sampled_sections_only', failures=[], scene=sm,
                  source_identities=sources, selected_mouth_id='mouth', candidates=[dict(mouth_id='mouth',
                  total_water_unknown=False, known_volume_m3=1.)])
    policy = dict(active_layer_bulk_thickness_m=.1, rock_depth_m=.2, initial_mobile_solid_m3_per_node=0.,
                  material=MaterialParameters(sediment_erodibility_m_s_pa=0., rock_erodibility_m_s_pa=0., provenance='test engineering scenario'))
    bundle = acceptance.build_supply_inputs(report, result, **policy)
    path = tmp_path / 'supply-input.npz'
    digest = acceptance.save_supply_inputs(path, bundle)
    pins = dict(expected_sha256=digest, expected_terrain_identity=sources['terrain'], expected_planner_identity=sources['planner'],
                expected_water_identity=water_id, expected_scene_identity=sources['scene'], expected_mouth_id='mouth')
    kwargs = acceptance.read_supply_inputs(path, **pins)
    product = produce_supply(**kwargs)
    for key, value in product['hydraulic']['arrays'].items():
        np.testing.assert_array_equal(value, result['arrays'][key])
    ledger = bundle['metadata']['water_ledger']
    assert ledger['input_m3'] == pytest.approx(1.)
    assert ledger['channel_initial_storage_m3'] + ledger['input_m3'] == pytest.approx(ledger['channel_final_storage_m3'] + ledger['physical_mouth_delivered_m3'])
    sed = product['sediment']['arrays']
    assert sed['trace_mobile_solid_m3'][-1].sum() + sed['trace_bed_alluvium_solid_m3'][-1].sum() + sed['cumulative_exported_solid_m3'][-1] == pytest.approx(sed['trace_mobile_solid_m3'][0].sum() + sed['trace_bed_alluvium_solid_m3'][0].sum())
    for key in pins:
        bad = dict(pins, **{key: 'f'*64})
        with pytest.raises(ValueError):
            acceptance.read_supply_inputs(path, **bad)
    from terrain_pipeline.common_infra import identity
    for key in ('network__width_m', 'time_seconds', 'initial_alluvium_bulk_m3'):
        forged = dict(bundle, arrays={k: v.copy() for k, v in bundle['arrays'].items()})
        forged['arrays'][key].flat[0] += .01
        forged['identity_sha256'] = identity(forged['arrays'], forged['metadata'])
        with pytest.raises(ValueError):
            acceptance.save_supply_inputs(tmp_path / (key + '.npz'), forged)



def test_known_native_scene_to_sediment(tmp_path, monkeypatch):
    from terrain_pipeline import new_world_stage1 as stage
    from terrain_pipeline import td_source as terrain
    from terrain_pipeline import new_world_native_water as water, new_world_river_scene as scene
    from terrain_pipeline.new_world_sediment import produce_supply
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters

    # The outer slopes drain away from the ridge-enclosed central catchment.
    z, x = np.indices((55, 55))
    raw = (35. - np.abs(z - 27) - .2 * np.abs(x - 27)).astype(np.float32)
    inner = (x >= 8) & (x <= 51) & (z >= 8) & (z <= 46)
    raw[inner] = (52 - x[inner]) * .2 + np.abs(z[inner] - 27) * .3 + 1
    raw[8:47, 8] = 100
    raw[8, 8:52] = 100
    raw[46, 8:52] = 100
    raw[:, 52:] = -1
    shape = raw.shape
    parent = {'coastal': True, 'origin_native_xz': [-10, 20], 'bed_origin_native_xz': [-10, 20],
              'anchor_bed_zx': [0, 54], 'source_shape_zx': list(shape), 'world_seed': 20261020,
              'spacing_m': 30, 'sea_m': 0, 'plate_identity': 'b'*64}
    source = {'raw_td': raw, 'td_climate': np.zeros((5, *shape), np.float32)}
    upstream = tmp_path / 'parent'; upstream.mkdir()
    monkeypatch.setattr(terrain.plate_td_product, "read_plate_source", lambda path, expected_identity: (parent, source))
    tm, _ = terrain.prepare_world_terrain(upstream, tmp_path / 'terrain', expected_source_identity='a'*64)
    pm, planner = stage.prepare(tmp_path / 'terrain', tmp_path / 'planner', expected_terrain_identity=tm['identity'], block_size=5)
    common = dict(expected_terrain_identity=tm['identity'], expected_planner_identity=pm['identity'])
    wm, event = water.prepare(tmp_path / 'planner', tmp_path / 'event', **common, source='rain', duration_s=60, runoff_depth_m=.001)
    common['expected_water_identity'] = wm['identity']
    mouths = [r for r in event['outlets'] if r['kind'] == 'marine' and not r['total_water_unknown']]
    assert mouths, event['outlets']
    mouth = max(mouths, key=lambda r: r['known_local_volume_m3'])
    sm, a = scene.extract(tmp_path / 'event', **common, mouth_id=mouth['mouth_id'], interval=wm['interval'], origin_native_xz=[-10, 20], shape_zx=list(shape))
    report, result = acceptance.run(tmp_path / 'event', **common, mouth_id=mouth['mouth_id'], origin_native_xz=[-10, 20], shape_zx=list(shape), width_m=10., max_depth_m=10., roughness=.04, downstream_stage_m=0.)
    assert report['status'] == 'physical_solve_complete_sampled_sections_only', report['failures']
    assert sm['interval'] == wm['interval'] and sm['mouth_source_index'] == mouth['index']
    assert report['scene'] == sm and report['source_identities'] == dict(terrain=tm['identity'], planner=pm['identity'], water=wm['identity'], scene=scene._identity(sm))
    trace = water.read_product(tmp_path / 'event', **common).context[2].ravel()
    rec = planner['routing/receiver']
    assert sm['boundary_contributions']
    for edge in sm['boundary_contributions']:
        assert rec[edge['source_index']] == edge['receiver_index']
        assert edge['known_volume_m3'] == trace[edge['source_index']]
    assert np.sum(a['incremental_volume_m3']) == pytest.approx(mouth['known_local_volume_m3'])
    np.testing.assert_allclose(np.cumsum(a['incremental_volume_m3']), a['routed_volume_m3'])
    bundle = acceptance.build_supply_inputs(report, result, active_layer_bulk_thickness_m=.1, rock_depth_m=.2,
        initial_mobile_solid_m3_per_node=0., material=MaterialParameters(sediment_erodibility_m_s_pa=0., rock_erodibility_m_s_pa=0., provenance='test engineering scenario'))
    path = tmp_path / 'supply.npz'
    digest = acceptance.save_supply_inputs(path, bundle)
    s = report['source_identities']
    kwargs = acceptance.read_supply_inputs(path, expected_sha256=digest, expected_terrain_identity=s['terrain'], expected_planner_identity=s['planner'], expected_water_identity=s['water'], expected_scene_identity=s['scene'], expected_mouth_id=mouth['mouth_id'])
    product = produce_supply(**kwargs)
    for key, value in result['arrays'].items():
        np.testing.assert_array_equal(product['hydraulic']['arrays'][key], value)
    ledger = bundle['metadata']['water_ledger']
    assert ledger['input_m3'] == pytest.approx(mouth['known_local_volume_m3'])
    assert ledger['channel_initial_storage_m3'] + ledger['input_m3'] == pytest.approx(ledger['channel_final_storage_m3'] + ledger['physical_mouth_delivered_m3'])
    sed = product['sediment']['arrays']
    assert sed['trace_mobile_solid_m3'][-1].sum() + sed['trace_bed_alluvium_solid_m3'][-1].sum() + sed['cumulative_exported_solid_m3'][-1] == pytest.approx(sed['trace_mobile_solid_m3'][0].sum() + sed['trace_bed_alluvium_solid_m3'][0].sum())





