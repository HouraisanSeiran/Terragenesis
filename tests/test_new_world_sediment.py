import numpy as np
import pytest
from types import SimpleNamespace

from terrain_pipeline.new_world_sediment import produce_supply
from terrain_pipeline.new_world_delta import DurableMouthConsumer
from terrain_pipeline.channel_geometry import ChannelNetwork, ChannelForcing, ChannelConfig
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig


def supply(stock=(1., 0.), settle=.1):
    n = 2
    network = ChannelNetwork(np.array([-1, -1], np.int64), np.full(n, 10.), np.full(n, 2.),
        np.zeros(n), np.full(n, .01), np.full(n, .05), np.full(n, 3.),
        np.array(['open_outflow', 'open_outflow']), 'a'*64, 'declared sections', 'declared roughness')
    water = ChannelForcing(np.array([0., 1.]), np.zeros((1, n)), 'b'*64)
    return produce_supply(network, water, terrain_identity='terrain', mouth_nodes={'a': 0, 'b': 1},
        rock_floor_m=np.zeros(n), initial_alluvium_bulk_m3=np.zeros(n),
        initial_mobile_solid_m3=np.array(stock), is_lake=np.zeros(n, bool),
        material=MaterialParameters(settling_velocity_m_s=settle, provenance='declared'),
        bed_material_provenance='declared bed', bank_material_provenance='declared banks',
        initial_water_m3=np.full(n, 10.), hydraulic_config=ChannelConfig(max_dt_seconds=1.),
        sediment_config=SedimentConfig(max_dt_seconds=.1, max_bed_change_m=1.))


def test_actual_supply_inventory_and_porosity():
    empty = supply((0., 0.))
    assert all(p['solid_m3'] == 0 for p in empty['packets'])
    product = supply()
    a = product['sediment']['arrays']
    assert sum(p['solid_m3'] for p in product['packets'] if p['mouth_id'] == 'a') > 0
    assert sum(p['solid_m3'] for p in product['packets'] if p['mouth_id'] == 'b') == 0
    assert np.isclose(a['step_bulk_deposition_m3'].sum(), a['step_deposited_solid_m3'].sum() / .65)
    assert np.isclose(a['trace_mobile_solid_m3'][-1].sum() + a['trace_bed_alluvium_solid_m3'][-1].sum() + a['cumulative_exported_solid_m3'][-1], 1.)


def test_durable_delivery_and_rollback(tmp_path, monkeypatch):
    product = supply()
    p = product['packets'][0]
    ocean = np.array([[False, True]])
    args = dict(supply=product, terrain_identity='terrain', hydraulic_identity=product['hydraulic_identity'],
        mouth_id=p['mouth_id'], interval_ids=[p['interval_id']], start_seconds=[p['start_s']], end_seconds=[p['end_s']],
        delivery_id='one', bed_m=np.array([[1., -1.]]), ocean_mask=ocean,
        geometry=SimpleNamespace(ocean_mask=ocean, eligible_mask=np.zeros_like(ocean)), prohibited_mask=np.zeros_like(ocean))
    import terrain_pipeline.new_world_delta as delta
    consumer = DurableMouthConsumer(tmp_path / 'delivery.sqlite')
    monkeypatch.setattr(delta, 'run_integrated_delta', lambda *a: (_ for _ in ()).throw(ValueError('failure')))
    with pytest.raises(ValueError, match='failure'):
        consumer.run(**args)
    monkeypatch.setattr(delta, 'run_integrated_delta', lambda *a: {'water': a[2], 'solid': a[3]})
    monkeypatch.setattr(delta, '_validate_kernel_result', lambda *a: None)
    consumer.run(**args)
    assert np.isclose(consumer.load_result('one')['result']['solid'][0], p['solid_m3'])
    with pytest.raises(ValueError, match='already consumed'):
        DurableMouthConsumer(tmp_path / 'delivery.sqlite').run(**{**args, 'delivery_id': 'two'})
    with pytest.raises(ValueError, match='source'):
        consumer.run(**{**args, 'terrain_identity': 'wrong', 'delivery_id': 'three'})



def test_saved_supply_and_real_delta_recovery(tmp_path, monkeypatch):
    import subprocess
    import sys
    from terrain_pipeline.new_world_sediment import save_supply, load_supply
    from terrain_pipeline.surface_rivers.metric_integrated_delta import build_channel_tree

    original = supply()
    path = tmp_path / 'supply.npz'
    digest = save_supply(path, original)
    with pytest.raises(FileExistsError):
        save_supply(path, original)
    with pytest.raises(ValueError):
        load_supply(path, expected_sha256='0' * 64)
    saved = load_supply(path, expected_sha256=digest)
    bed = np.full((40, 40), -2.)
    ocean = np.zeros_like(bed, bool)
    trunk = np.column_stack([np.arange(2., 16.) * 20., np.full(14, 400.)])
    parent = np.column_stack([np.arange(15., 36.) * 20., np.full(21, 400.)])
    secondary = np.column_stack([np.linspace(500., 700., 12), np.linspace(400., 600., 12)])
    geometry = build_channel_tree(bed, [0., 0.], 20., trunk[-1], trunk[0], trunk,
        [parent, secondary], [80., 60., 30.], ocean_mask=ocean,
        branch_parent_index=[-1, 0], protected_band_m=0.)
    ledger = tmp_path / 'ledger.sqlite'
    consumer = DurableMouthConsumer(ledger)
    def args(mouth, delivery):
        packet = next(p for p in saved['packets'] if p['mouth_id'] == mouth)
        return dict(supply=saved, terrain_identity='terrain', hydraulic_identity=saved['hydraulic_identity'],
            mouth_id=mouth, interval_ids=[packet['interval_id']], start_seconds=[packet['start_s']],
            end_seconds=[packet['end_s']], delivery_id=delivery, bed_m=bed, ocean_mask=ocean,
            geometry=geometry, prohibited_mask=np.zeros_like(ocean))
    import terrain_pipeline.new_world_delta as delta
    kernel = delta.run_integrated_delta
    def corrupt_result(*inputs):
        result = kernel(*inputs)
        result['stored_solid_m3'][0, 0] = np.nan
        return result
    monkeypatch.setattr(delta, 'run_integrated_delta', corrupt_result)
    with pytest.raises(ValueError, match='kernel result array'):
        consumer.run(**args('a', 'first'))
    monkeypatch.setattr(delta, 'run_integrated_delta', kernel)
    result = consumer.run(**args('a', 'first'))
    assert 'records' in result['result']
    consumer.run(**args('b', 'second'))
    with pytest.raises(ValueError, match='already consumed'):
        consumer.run(**args('a', 'duplicate'))
    code = "from terrain_pipeline.new_world_delta import DurableMouthConsumer; import sys; x=DurableMouthConsumer(sys.argv[1]).load_result('first'); assert x['binding']['mouth_id']=='a'; print(len(x['result']['records']))"
    check = subprocess.run([sys.executable, '-c', code, str(ledger)], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    import sqlite3
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE deliveries SET result = ? WHERE delivery_id = 'first'", (b'corrupt',))
    with pytest.raises(ValueError, match='integrity'):
        consumer.load_result('first')
    with pytest.raises(ValueError, match='already consumed'):
        consumer.run(**args('a', 'after-corruption'))
    bad = args('a', 'wrong')
    bad['end_seconds'] = [999.]
    with pytest.raises(ValueError, match='time'):
        consumer.run(**bad)
    saved['packets'][0]['solid_m3'] += 10
    with pytest.raises(ValueError, match='exports'):
        consumer.run(**args('a', 'forged'))


def test_finite_kernel_erosion_lake_and_reerosion():
    from test_metric_sediment import domain, forcing, GEOMETRY, HYDRAULICS
    from terrain_pipeline.surface_rivers.metric_sediment import SedimentForcing, solve_sediment
    cfg = SedimentConfig(max_dt_seconds=.05, max_bed_change_m=2.)
    material = MaterialParameters(porosity=0., sediment_critical_shear_pa=0., rock_critical_shear_pa=0.,
        sediment_erodibility_m_s_pa=.01, rock_erodibility_m_s_pa=.001,
        transport_coefficient=1., settling_velocity_m_s=0.)
    eroded = solve_sediment(domain(open_boundary=[True]), forcing(1, q=1., slope=.01), material,
                           config=cfg)['arrays']
    assert eroded['step_eroded_rock_m3'].sum() > 0
    assert eroded['cumulative_exported_solid_m3'][-1] > 0
    assert np.isclose(eroded['step_eroded_rock_m3'].sum(),
        eroded['trace_mobile_solid_m3'][-1].sum() + eroded['trace_bed_alluvium_solid_m3'][-1].sum()
        + eroded['cumulative_exported_solid_m3'][-1])
    lake = domain(receiver=(1, -1), is_lake=[True, False], open_boundary=[False, True])
    flow = forcing(2, q=1.)
    bypass = solve_sediment(lake, flow, MaterialParameters(settling_velocity_m_s=0.), np.array([1., 0.]), cfg)['arrays']
    trapped = solve_sediment(lake, flow, MaterialParameters(settling_velocity_m_s=1.), np.array([1., 0.]), cfg)['arrays']
    assert trapped['step_deposited_solid_m3'][:, 0].sum() > 0
    assert trapped['step_incoming_solid_m3'][:, 1].sum() < bypass['step_incoming_solid_m3'][:, 1].sum()
    two_steps = SedimentForcing(np.array([0., 1., 2.]), np.full((2, 1), 10.), np.ones((2, 1)),
        np.array([[0.], [1.]]), np.array([[0.], [.01]]), np.zeros((2, 1)), HYDRAULICS, GEOMETRY, 'two phases')
    material = MaterialParameters(sediment_critical_shear_pa=0., rock_critical_shear_pa=1000.,
        sediment_erodibility_m_s_pa=.01, transport_coefficient=1., settling_velocity_m_s=1.)
    a = solve_sediment(domain(open_boundary=[True]), two_steps, material, np.array([1.]), cfg)['arrays']
    assert a['step_deposited_solid_m3'].sum() > 0
    assert a['step_eroded_loose_solid_m3'].sum() > 0



def test_cli_actual_supply_and_recovery(tmp_path):
    import subprocess
    import sys
    from test_metric_integrated_delta import synthetic_scene
    from terrain_pipeline.new_world_sediment import save_supply
    scene = synthetic_scene()
    product = supply()
    supply_path = tmp_path / 'supply.npz'
    digest = save_supply(supply_path, product)
    packet = product['packets'][0]
    source = tmp_path / 'geometry.npz'
    np.savez(source, terrain_identity=np.array('terrain'), hydraulic_identity=np.array(product['hydraulic_identity']),
        mouth_id=np.array(packet['mouth_id']), bed_m=scene['bed'], ocean_mask=scene['ocean'], origin_xz_m=scene['origin'],
        spacing_m=scene['spacing'], mouth_xz_m=scene['mouth'], apex_xz_m=scene['apex'],
        trunk_path_xz_m=scene['trunk'], widths_m=scene['widths'],
        branch_path_0=scene['branches'][0], branch_path_1=scene['branches'][1], branch_path_2=scene['branches'][2],
        prohibited_mask=np.zeros_like(scene['ocean']), interval_ids=np.array([packet['interval_id']]),
        start_seconds=np.array([packet['start_s']]), end_seconds=np.array([packet['end_s']]),
        duration_s=np.array([packet['end_s'] - packet['start_s']]))
    from terrain_pipeline.common_infra import file_sha256
    geometry_digest = file_sha256(source)
    def command(output):
        return [sys.executable, '-m', 'tools.prepare_new_world_delta', str(source), str(output),
            '--source-identity', product['hydraulic_identity'], '--mouth-id', packet['mouth_id'],
            '--supply', str(supply_path), '--supply-sha256', digest, '--geometry-sha256', geometry_digest, '--terrain-identity', 'terrain',
            '--hydrology-identity', product['hydrology_identity'], '--ledger', str(tmp_path / 'ledger.db'),
            '--delivery-id', 'delivery']
    first = subprocess.run(command(tmp_path / 'first.npz'), capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    duplicate = subprocess.run(command(tmp_path / 'duplicate.npz'), capture_output=True, text=True)
    assert duplicate.returncode != 0 and 'already committed' in duplicate.stderr
    recovery = subprocess.run(command(tmp_path / 'recovered.npz') + ['--recover'], capture_output=True, text=True)
    assert recovery.returncode == 0, recovery.stderr
    with np.load(tmp_path / 'first.npz') as a, np.load(tmp_path / 'recovered.npz') as b:
        np.testing.assert_array_equal(a['forcing_solid_m3'], b['forcing_solid_m3'])


def test_durable_rejects_wrong_bindings_and_unknown_water(tmp_path):
    import copy
    p = supply()
    packet = p['packets'][0]
    ocean = np.array([[False, True]])
    args = dict(supply=p, terrain_identity='terrain', hydraulic_identity=p['hydraulic_identity'],
        mouth_id='a', interval_ids=[packet['interval_id']], start_seconds=[packet['start_s']],
        end_seconds=[packet['end_s']], delivery_id='x', bed_m=np.array([[1., -1.]]), ocean_mask=ocean,
        geometry=SimpleNamespace(ocean_mask=ocean, eligible_mask=np.zeros_like(ocean)), prohibited_mask=np.zeros_like(ocean))
    consumer = DurableMouthConsumer(tmp_path / 'reject.sqlite')
    for change in ({'terrain_identity': 'wrong'}, {'hydraulic_identity': '0' * 64},
                   {'mouth_id': 'wrong'}, {'start_seconds': [-1.]}, {'end_seconds': [2.]}):
        with pytest.raises(ValueError):
            consumer.run(**{**args, **change})
    forged = copy.deepcopy(p)
    forged['packets'][0]['water_m3'] = float('nan')
    with pytest.raises(ValueError, match='exports'):
        consumer.run(**{**args, 'supply': forged})
