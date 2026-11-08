import numpy as np
from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, bed_elevation, step, tide_stage


def setup():
    geometry = Geometry(np.array([100., 100.]), np.array([-1., -1.]),
                        np.array([0]), np.array([1]), np.array([1.]),
                        np.array([1]), np.array([1.]))
    state = State(0., np.array([100., 100.]), np.array([60., 60.]), np.zeros(2))
    return geometry, state


def test_still_water_and_sea_balance():
    g, s = setup()
    before = s.water_m3.sum()
    step(g, s, 60., 1., 0, 0., 0.)
    assert np.isclose(s.water_m3.sum(), before)
    assert s.sea_water_in_m3 == s.sea_water_out_m3 == 0


def test_reversal_and_conservation():
    g, s = setup()
    initial_water = s.water_m3.sum()
    initial_solid = s.bed_solid_m3.sum()
    for i in range(400):
        step(g, s, 120., tide_stage(i*120), 0, .02, .000001)
    assert s.sea_water_in_m3 > 0 and s.sea_water_out_m3 > 0
    assert np.isclose(initial_water+s.source_water_m3+s.sea_water_in_m3,
                      s.water_m3.sum()+s.sea_water_out_m3)
    assert np.isclose(initial_solid+s.source_solid_m3,
                      s.bed_solid_m3.sum()+s.mobile_solid_m3.sum()+s.sea_solid_out_m3)
    assert np.all(s.bed_solid_m3 >= 0) and np.all(s.water_m3 >= 0)


def test_bed_feedback_and_stock_floor():
    g, s = setup()
    s.water_m3[:] = [300., 10.]
    initial = bed_elevation(g, s).copy()
    for _ in range(50):
        step(g, s, 10., -1., 0, 0., 0.)
    assert np.any(bed_elevation(g, s) != initial)
    assert np.all(bed_elevation(g, s) >= g.floor_m)


def test_checkpoint_preserves_phase_and_stocks(tmp_path):
    from terrain_pipeline.large_delta_tidal_dynamics import save_checkpoint, load_checkpoint
    g, first = setup()
    for _ in range(10):
        step(g, first, 100., tide_stage(first.time_s), 0, .01, .00001)
    path = tmp_path / 'checkpoint.npz'
    save_checkpoint(path, first)
    resumed = load_checkpoint(path)
    for _ in range(10):
        for state in (first, resumed):
            step(g, state, 100., tide_stage(state.time_s), 0, .01, .00001)
    assert first.time_s == resumed.time_s
    for key in vars(first):
        np.testing.assert_array_equal(getattr(first, key), getattr(resumed, key))


def test_timestep_agreement_for_tidal_exchange():
    def simulate(dt):
        g, s = setup()
        for _ in range(int(43200/dt)):
            step(g, s, dt, tide_stage(s.time_s+dt/2), 0, .02, .000001)
        return s
    coarse = simulate(10.)
    fine = simulate(5.)
    np.testing.assert_allclose(coarse.water_m3, fine.water_m3, rtol=.01, atol=.11)
    np.testing.assert_allclose(coarse.bed_solid_m3, fine.bed_solid_m3, rtol=.01, atol=.05)
