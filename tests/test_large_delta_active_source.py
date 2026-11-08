import numpy as np

from terrain_pipeline.large_delta_active_source import calculate, DAYS, SECONDS_PER_DAY


def test_active_event_spends_retained_stock_once_without_hillslope_input():
    network = {
        'receiver': np.array([1, -1], dtype=np.int64),
        'length_m': np.array([100., 100.]), 'width_m': np.array([10., 10.]),
        'bed_m': np.array([2., 1.]), 'accumulated_q_m3_s': np.array([5., 10.]),
        'depth_m': np.array([1., 1.]), 'slope': np.array([.01, .01]),
    }
    stock = {'channel_final_solid_m3': np.array([120., 180.]),
             'hillslope_remaining_solid_m3': np.array([400., 500.]),
             'channel_bed_delta_m': np.array([0., 0.])}
    a = calculate(network, stock)
    assert a['time_seconds'][-1] == 30 * 86400
    assert len(a['time_seconds']) == DAYS + 1
    assert np.all(np.diff(a['time_seconds']) == SECONDS_PER_DAY)
    delivered = a['exported_solid_m3'].sum()
    assert delivered > 0
    assert np.isclose(300., a['trace_loose_solid_m3'][-1].sum() + a['trace_mobile_solid_m3'][-1].sum() + delivered)
    assert a['external_solid_m3'].sum() == 0
    assert a['eroded_rock_m3'].sum() == 0
    assert stock['hillslope_remaining_solid_m3'].sum() == 900.
