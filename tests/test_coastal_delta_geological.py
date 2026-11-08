import numpy as np
import pytest

from terrain_pipeline.coastal_delta_geological import GeologicalConfig, advance, load, save, start
from terrain_pipeline.coastal_marine_sediment import make_state


def test_connected_finite_supply_and_restart(tmp_path):
    base = np.full((9, 11), -2.)
    ocean = np.ones_like(base, bool)
    ocean[:, 5] = False
    ocean[4, 5] = True
    seeds = np.zeros_like(ocean)
    seeds[0, 0] = True
    state = make_state(base_bed_m=base, bed_solid_m3=0., mobile_solid_m3=0., porosity=.4,
                       valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
                       origin_xz_m=(0., 0.), source_identity='test-source')
    config = GeologicalConfig((4, 2), solid_rate_m3_s=.01, settling_fraction=.1)
    p = start(state, config, ocean_mask=ocean)
    one, p = advance(state, p, .001, input_id='one', ocean_mask=ocean, sweeps=20)
    assert np.all(one.bed_solid_m3[:, 5][np.arange(9) != 4] == 0)
    assert one.bed_solid_m3[4, 6] > 0
    assert one.bed_solid_m3.sum() + one.mobile_solid_m3.sum() == pytest.approx(p['supply_solid_m3'])
    save(tmp_path / 'state', one, p)
    restored, rp = load(tmp_path / 'state')
    with pytest.raises(ValueError, match='duplicate'):
        advance(restored, rp, .001, input_id='one', ocean_mask=ocean, sweeps=20)
    other = ocean.copy(); other[0, 0] = False
    with pytest.raises(ValueError, match='identity'):
        advance(restored, rp, .001, input_id='two', ocean_mask=other, sweeps=20)
    a, ap = advance(one, p, .001, input_id='two', ocean_mask=ocean, sweeps=20)
    b, bp = advance(restored, rp, .001, input_id='two', ocean_mask=ocean, sweeps=20)
    assert np.array_equal(a.bed_solid_m3, b.bed_solid_m3)
    assert ap == bp
    assert b.time_s == state.time_s

def test_finalize_event_preserves_reserve_and_blocks_formation(tmp_path):
    from terrain_pipeline.coastal_delta_geological import finalize_for_event
    from terrain_pipeline.coastal_marine_sediment import MarineConfig, advance as marine_advance
    ocean = np.ones((7, 7), bool)
    seeds = np.zeros_like(ocean); seeds[0, 0] = True
    state = make_state(base_bed_m=np.full(ocean.shape, -2.), bed_solid_m3=0.,
                       mobile_solid_m3=0., porosity=.4, valid_mask=True,
                       ocean_seed_mask=seeds, spacing_m=100., origin_xz_m=(0., 0.),
                       source_identity='test-source')
    p = start(state, GeologicalConfig((3, 3), solid_rate_m3_s=1., settling_fraction=0.), ocean_mask=ocean)
    work, p = advance(state, p, .01, input_id='formation', ocean_mask=ocean, sweeps=2)
    event, ep = finalize_for_event(work, p, ocean_mask=ocean, concentration_limit=.001, input_id='handoff')
    assert event.unresolved_solid_m3 > 0
    assert event.mobile_solid_m3.sum() + event.unresolved_solid_m3 == pytest.approx(p['supply_solid_m3'])
    assert np.max(event.mobile_solid_m3 / (2 * 100**2)) <= .001
    with pytest.raises(ValueError):
        advance(event, p, .01, input_id='bad', ocean_mask=ocean, sweeps=2)
    with pytest.raises(ValueError):
        finalize_for_event(event, ep, ocean_mask=ocean, concentration_limit=.001, input_id='again')
    save(tmp_path / 'event', event, ep)
    event, ep = load(tmp_path / 'event')
    after = marine_advance(event, [], 1., MarineConfig(step_s=1., settling_rate_s=.1))
    assert after.unresolved_solid_m3 == event.unresolved_solid_m3
    assert after.water_input_m3 == 0.
    assert after.bed_solid_m3.sum() + after.mobile_solid_m3.sum() + after.stranded_solid_m3.sum() + after.unresolved_solid_m3 + after.exported_solid_m3 == pytest.approx(p['supply_solid_m3'])
    assert after.consumed_packets[0]['delivered_solid_m3'] == 0.


def test_irregular_distance_respects_barriers():
    from terrain_pipeline.coastal_delta_geological import _marine_graph_distance
    ocean = np.ones((9, 9), bool); ocean[:, 4] = False
    seeds = np.zeros_like(ocean); seeds[0, 0] = True
    state = make_state(base_bed_m=np.full(ocean.shape, -2.), bed_solid_m3=0., mobile_solid_m3=0.,
                       porosity=.4, valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
                       origin_xz_m=(0., 0.), source_identity='barrier')
    d = _marine_graph_distance(state, ocean, (4, 2))
    assert np.isfinite(d[4, 3]) and np.isinf(d[4, 5])
    ocean[0, 4] = True
    d = _marine_graph_distance(state, ocean, (4, 2))
    assert np.isfinite(d[4, 5]) and d[4, 5] > 300.
