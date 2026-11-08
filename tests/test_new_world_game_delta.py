import numpy as np
import pytest

from terrain_pipeline.new_world_game_delta import route_trace_sediment, section_stages
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters


def test_irregular_section_stage_and_overtopping():
    bed = np.array([[4., 1., 0., 2., 4.]])
    stage, width = section_stages(bed, 10., np.array([[1.], [3.]]),
                                  np.array([.01]), .035)
    assert 0 < stage[0, 0] < stage[1, 0] < 4
    assert 0 < width[0, 0] < width[1, 0]
    with pytest.raises(ValueError, match='overtopped'):
        section_stages(bed, 10., np.array([[1e9]]), np.array([.01]), .035)


def test_finite_stock_budget_uses_routed_interval_water():
    bundle = route_trace_sediment(receiver=np.array([1, -1]), length_m=np.array([100., 100.]),
        width_m=np.array([10., 10.]), bed_m=np.array([3., 2.]),
        depth_m=np.array([[1., 1.], [1., 1.]]), routed_water_m3=np.array([[100., 200.], [50., 100.]]),
        slope=np.array([.01, .01]), time_seconds=np.array([0., 10., 20.]),
        rock_floor_m=np.array([1., 0.]), alluvium_bulk_m3=np.array([100., 100.]),
        hardness=np.array([.5, .5]), material=MaterialParameters(), geometry_identity='a'*64,
        hydraulic_identity='b'*64, provenance='declared test stock')
    a = bundle['arrays']
    assert np.array_equal(a['water_q_m3_s'], [[10., 20.], [5., 10.]])
    assert a['exported_solid_m3'][:, 1].sum() > 0
    assert abs(bundle['metadata']['global_residual']) < 1e-8
    assert np.all(a['trace_loose_solid_m3'] >= 0)


def test_bounded_subgrid_preserves_source_and_enforces_cap():
    from terrain_pipeline.new_world_game_delta import bounded_subgrid_channel
    source = np.array([3., 2.8, .3])
    result = bounded_subgrid_channel(source, [3., 2., 0.], [2., 2., 2.],
                                     [.2, .2, .2], [0., 10., 20.])
    assert np.array_equal(source, [3., 2.8, .3])
    assert np.all(result['bed_m'] < result['stage_m'])
    assert result['construction_bulk_m3'] > 0
    with pytest.raises(ValueError, match='cut cap'):
        bounded_subgrid_channel([10., 10.], [1., 0.], [1., 1.], [.2, .2], [0., 1.])


def test_delta_junction_rejects_inconsistent_original_raster_bed():
    from types import SimpleNamespace
    from terrain_pipeline.surface_rivers.metric_integrated_delta import _solve_hydraulics, IntegratedDeltaConfig
    bed = {
        'trunk0': [3.6471941471, 3.6471941471, 3.7260825634],
        'trunk1': [3.7260825634, 3.7260825634, 3.8808488846, 1.2209267616, -.109867394],
        'branch0': [3.7260825634, 3.3461515903, 3.3461515903, 3.5785660744, 3.6493494511, 3.0014784336, 2.3653962612, -.0899273157],
        'branch1': [-.109867394, -.109867394, -.109867394, -.0922227353, -.0922227353, -.2381948531, -.4649179876, -.4649179876],
        'branch2': [-.109867394, -.0922227353, -.0922227353, -.4649179876, -.6794971228, -.8467268944, -.9623581171, -1.1253712171],
    }
    bed = {k: np.asarray(v) for k, v in bed.items()}
    lengths = {'trunk0': 35.05421534, 'trunk1': 70.10843069,
               'branch0': 207.06186963, 'branch1': 75.94811168, 'branch2': 169.95529828}
    station = {k: np.linspace(0., lengths[k], len(v)) for k, v in bed.items()}
    geometry = SimpleNamespace(paths={k: SimpleNamespace(width_m=2.65 if k.startswith('trunk') else 1.6) for k in bed})
    target = .06228454789213938
    with pytest.raises(ArithmeticError, match="hydraulic junction continuity"):
        _solve_hydraulics(geometry, bed, station, target, IntegratedDeltaConfig())


def test_subgrid_distributaries_account_once_and_zero_water():
    from terrain_pipeline.new_world_game_delta import route_subgrid_distributaries
    masks = np.array([[[True, False]], [[False, True]]])
    out = route_subgrid_distributaries([10., 0.], [2., 1.], [100., 100.],
        [30., 50.], [2., 1.], [.2, .2], masks, 900.)
    assert np.allclose(out['branch_water_m3'].sum(axis=1), [10., 0.])
    assert np.isclose(out['stored_solid_m3'].sum() + out['exported_solid_m3'].sum() + out['escrow_solid_m3'].sum(), 3.)
    assert out['deposited_solid_m3'][1].sum() == 0.


def test_retained_supply_rejects_changed_inlet_geometry_and_water():
    from terrain_pipeline.new_world_game_delta import retained_sediment_supply, validate_retained_supply
    supply = retained_sediment_supply(station_m=[0., 10., 20.], points_xz_m=[[0.,0.],[10.,0.],[20.,0.]],
        bed_m=[1.8,1.,.1],stage_m=[2.,1.2,.3],width_m=[2.,2.,2.],
        control_edges_m=[0.,10.,20.],control_water_m3=[[50.,70.],[80.,100.]],
        time_seconds=[0.,100.,200.],source_identity='source',mouth_id='mouth',inlet_xz_m=[20.,0.],
        material=MaterialParameters())
    kwargs=dict(geometry_identity=supply['geometry_identity'],inlet_xz_m=[20.,0.],mouth_id='mouth',
                time_seconds=[0.,100.,200.],mouth_water_m3=[70.,100.])
    assert validate_retained_supply(supply,**kwargs).shape == (2,)
    for key, value in [('geometry_identity','other'),('inlet_xz_m',[21.,0.]),
                       ('mouth_water_m3',[70.,101.])]:
        with pytest.raises(ValueError,match='binding mismatch'):
            validate_retained_supply(supply,**(kwargs|{key:value}))
    assert abs(supply['result']['metadata']['global_residual']) < 1e-8
    assert np.isclose(supply['result']['arrays']['length_m'].sum(),20.)
