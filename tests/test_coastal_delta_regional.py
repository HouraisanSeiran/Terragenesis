import numpy as np
import pytest

from terrain_pipeline.coastal_delta_branching import _record
from terrain_pipeline.coastal_delta_evolution import initialize
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_delta_regional import advance_interval, estimate_cost, load, save
from terrain_pipeline.coastal_marine_longterm import LongtermConfig
from terrain_pipeline.coastal_marine_sediment import make_state


def test_material_and_memory_estimate():
    result = estimate_cost(shape=(500, 500), area_km2=10000, mean_raise_m=5,
                           porosity=.4, solid_rate_m3_s=10, years=100)
    assert result['ideal_demand_solid_m3'] == 30e9
    assert result['requested_supply_solid_m3'] == 10 * 100 * 365.25 * 86400
    assert result['float64_grid_bytes_lower_bound'] == 40_000_000
    with pytest.raises(ValueError):
        estimate_cost(shape=(500, 500), area_km2=1, mean_raise_m=1,
                      porosity=1, solid_rate_m3_s=1, years=1)


def test_regional_interval_restart_and_unique_input(tmp_path):
    base = np.full((7, 7), -2.)
    seeds = np.zeros_like(base, dtype=bool)
    seeds[:, -1] = True
    state = make_state(base_bed_m=base, bed_solid_m3=0., mobile_solid_m3=0.,
                       porosity=.4, valid_mask=True, ocean_seed_mask=seeds,
                       spacing_m=100., origin_xz_m=(0., 0.), source_identity='source-a')
    route = np.array([[3, i] for i in range(1, 6)])
    routes = {'main_cells_zx': route, 'branch_offsets': np.array([0]),
              'branch_cells_zx': np.empty((0, 2), int), 'section_bed_m': np.full(5, -2.),
              'section_bank_m': np.ones(5), 'section_width_m': np.full(5, 20.),
              'section_stage_m': np.ones(5)}
    state, progress = initialize(state, routes, {'source_identity': 'source-a'},
                                 discharge_m3_s=10., solid_rate_m3_s=.01)
    state = _record(state, progress)
    kwargs = dict(source_identity='source-a', hydraulic_config=HydraulicConfig(4.),
                  marine_config=LongtermConfig())
    out, progress = advance_interval(state, progress, .0001, input_id='one', **kwargs)
    save(tmp_path / 'checkpoint', out, progress)
    restored, restored_progress = load(tmp_path / 'checkpoint')
    with pytest.raises(ValueError, match='duplicate'):
        advance_interval(restored, restored_progress, .0001, input_id='one', **kwargs)
    with pytest.raises(ValueError, match='identity'):
        advance_interval(restored, restored_progress, .0001, input_id='two',
                         **(kwargs | {'source_identity': 'other'}))
    a, ap = advance_interval(out, progress, .0001, input_id='two', **kwargs)
    b, bp = advance_interval(restored, restored_progress, .0001, input_id='two', **kwargs)
    assert np.array_equal(a.bed_solid_m3, b.bed_solid_m3)
    assert ap == bp
    assert b.time_s == state.time_s
    total = lambda s: sum(float(getattr(s, k).sum()) for k in
                          ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')) + s.exported_solid_m3
    assert total(b) - total(state) + bp['integrated']['pending_solid_m3'] == pytest.approx(
        .01 * .0002 * 365.25 * 86400)
