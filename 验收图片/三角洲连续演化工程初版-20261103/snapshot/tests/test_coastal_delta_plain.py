from dataclasses import replace
import numpy as np
import pytest
from terrain_pipeline.coastal_delta_branching import start
from terrain_pipeline.coastal_delta_plain import advance_years
from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint
from terrain_pipeline.coastal_marine_longterm import LongtermConfig
from terrain_pipeline.coastal_marine_sediment import make_state


def fixture():
    base = np.full((8, 12), -2.)
    base[0, 0] = 1.
    seeds = np.zeros(base.shape, bool)
    seeds[:, -1] = True
    state = make_state(base_bed_m=base, bed_solid_m3=0, mobile_solid_m3=0,
                       porosity=.4, valid_mask=True, ocean_seed_mask=seeds,
                       spacing_m=100., origin_xz_m=(0., 0.), source_identity='test')
    trunk = [[3, c] for c in range(12)]
    network = {'trunk': trunk, 'fork_indices': [4, 6], 'branches': [
        [[3,4],[2,4],[2,5],[2,6],[2,7],[2,8],[2,9],[2,10],[2,11]],
        [[3,6],[4,6],[4,7],[4,8],[4,9],[4,10],[4,11]]]}
    return state, start(state, network, input_id='test', discharge_m3_s=3000, solid_rate_m3_s=.01)


def total(s):
    return sum(getattr(s, k).sum() for k in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')) + s.exported_solid_m3


def test_finite_supply_land_and_clocks():
    state, p = fixture()
    cfg = LongtermConfig(max_step_s=40000., source_relocation_cells=0)
    result, q = advance_years(state, p, .001, cfg, step_years=.001)
    assert result.time_s == state.time_s and q['years'] == pytest.approx(.001)
    assert total(result)-total(state) == pytest.approx(.01*.001*365.25*86400)
    assert result.bed_solid_m3[0, 0] == 0
    assert np.array_equal(result.base_bed_m, state.base_bed_m)


def test_resume_identity_and_rewet(tmp_path):
    state, p = fixture()
    cfg = LongtermConfig(max_step_s=40000., source_relocation_cells=0)
    state, p = advance_years(state, p, .001, cfg, step_years=.001)
    save_checkpoint(tmp_path/'state', state, p)
    restored, saved = load_checkpoint(tmp_path/'state')
    a, ap = advance_years(state, p, .001, cfg, step_years=.001)
    b, bp = advance_years(restored, saved, .001, cfg, step_years=.001)
    assert ap == bp and np.array_equal(a.bed_solid_m3, b.bed_solid_m3)
    with pytest.raises(ValueError):
        advance_years(state, p, .001, cfg, step_years=.001, amplitude_m=.5)


def test_disconnected_wet_stock_stays_in_place():
    from terrain_pipeline.coastal_delta_product import _source_fingerprint
    state, p = fixture()
    valid = state.valid_mask.copy()
    valid[0, 4:7] = False
    valid[1, 4] = valid[1, 6] = valid[2, 4:7] = False
    mobile = state.mobile_solid_m3.copy()
    mobile[1, 5] = 100.
    state = replace(state, valid_mask=valid, mobile_solid_m3=mobile)
    p['source_state_fingerprint'] = _source_fingerprint(state)
    cfg = LongtermConfig(max_step_s=40000., source_relocation_cells=0)
    result, _ = advance_years(state, p, .001, cfg, step_years=.001)
    assert result.bed_solid_m3[1, 5] == 0
    assert result.stranded_solid_m3[1, 5] == pytest.approx(100.)


def test_stranded_stock_releases_on_same_cell_rewetting():
    from terrain_pipeline.coastal_delta_product import _source_fingerprint
    state, p = fixture()
    base = state.base_bed_m.copy()
    base[1, 2] = -.5
    stranded = state.stranded_solid_m3.copy()
    stranded[1, 2] = 100.
    state = replace(state, base_bed_m=base, stranded_solid_m3=stranded)
    p['source_state_fingerprint'] = _source_fingerprint(state)
    cfg = LongtermConfig(max_step_s=40000., velocity_x_m_s=0., velocity_z_m_s=0.,
                         diffusivity_m2_s=0., boundary_rate_s=0., source_relocation_cells=0)
    result, _ = advance_years(state, p, .001, cfg, step_years=.001)
    assert result.bed_solid_m3[1, 2] > 0
    assert result.bed_solid_m3[1, 2] + result.mobile_solid_m3[1, 2] + result.stranded_solid_m3[1, 2] == pytest.approx(100.)
