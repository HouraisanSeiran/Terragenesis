from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.coastal_marine_longterm import LongtermConfig, advance
from terrain_pipeline.coastal_marine_sediment import make_state, save_state, load_state


def state(*, opened=False, volume=100.):
    shape = (3, 9)
    seeds = np.zeros(shape, bool)
    seeds[1, -1] = opened
    mobile = np.zeros(shape)
    mobile[1, 1] = volume
    return make_state(base_bed_m=np.full(shape, -5.), bed_solid_m3=0,
                      mobile_solid_m3=mobile, porosity=.4, valid_mask=True,
                      ocean_seed_mask=seeds, spacing_m=10., origin_xz_m=(0., 0.),
                      source_identity='test')


def total(s):
    return (s.bed_solid_m3.sum() + s.mobile_solid_m3.sum()
            + s.stranded_solid_m3.sum() + s.exported_solid_m3)


def test_closed_domain_conserves_and_settles():
    initial = state()
    cfg = LongtermConfig(velocity_x_m_s=.1, diffusivity_m2_s=.1,
                         settling_velocity_m_s=.01, max_step_s=50.)
    closed = np.ones(initial.base_bed_m.shape, bool)
    settled, _ = advance(initial, 200., cfg, wet_mask=closed)
    no_settling, _ = advance(initial, 200., replace(cfg, settling_velocity_m_s=0), wet_mask=closed)
    assert np.isclose(total(settled), 100.)
    assert settled.bed_solid_m3.sum() > 0
    assert no_settling.bed_solid_m3.sum() == 0
    assert settled.exported_solid_m3 == 0


def test_transport_deposits_along_route_and_exports_only_at_open_boundary():
    initial = state(opened=True)
    cfg = LongtermConfig(velocity_x_m_s=.1, velocity_z_m_s=0., diffusivity_m2_s=.1,
                         settling_velocity_m_s=.002, boundary_rate_s=.03, max_step_s=20.)
    out, report = advance(initial, 2000., cfg)
    assert out.bed_solid_m3[1, 3:8].sum() > 1
    assert out.exported_solid_m3 > 1
    assert np.isclose(total(out), 100.)
    assert report['morphological_steps'] >= 100


def test_capacity_keeps_unsettled_material_and_restart(tmp_path):
    initial = state(volume=1000.)
    cfg = LongtermConfig(velocity_x_m_s=.02, diffusivity_m2_s=.05,
                         settling_velocity_m_s=.1, max_step_s=10., max_rise_m=.1)
    ceiling = np.full(initial.base_bed_m.shape, -4.99)
    wet = np.ones(ceiling.shape, bool)
    first, _ = advance(initial, 50., cfg, wet_mask=wet, bed_ceiling_m=ceiling)
    assert np.max(first.bed_m - ceiling) < 1e-8
    assert first.mobile_solid_m3.sum() > 900
    assert np.isclose(total(first), 1000.)
    path = tmp_path / 'marine.npz'
    save_state(path, first)
    resumed, _ = advance(load_state(path), 50., cfg, wet_mask=wet, bed_ceiling_m=ceiling)
    assert np.isclose(total(resumed), 1000.)


def test_substeps_agree_within_engineering_error():
    initial = state(opened=True)
    cfg = LongtermConfig(velocity_x_m_s=.1, velocity_z_m_s=0., diffusivity_m2_s=.1,
                         settling_velocity_m_s=.002, boundary_rate_s=.03, max_step_s=5.)
    fine, _ = advance(initial, 500., cfg)
    coarse, _ = advance(initial, 500., replace(cfg, max_step_s=10.))
    assert np.linalg.norm(fine.bed_solid_m3-coarse.bed_solid_m3, 1) / 100 < .04
    assert abs(fine.exported_solid_m3-coarse.exported_solid_m3) / 100 < .04


def test_uniform_supply_at_dry_cell_is_not_lost():
    initial = state(volume=0.)
    wet = np.zeros(initial.base_bed_m.shape, bool)
    wet[1, 2] = True
    source = np.zeros(wet.shape)
    source[1, 1] = 2.  # adjacent to wet water
    source[1, 7] = 3.  # no adjacent wet receiver
    cfg = LongtermConfig(velocity_x_m_s=0., velocity_z_m_s=0., diffusivity_m2_s=0.,
                         settling_velocity_m_s=0., boundary_rate_s=0., max_step_s=10.)
    result, _ = advance(initial, 10., cfg, source_rate_m3_s=source, wet_mask=wet)
    assert np.isclose(result.mobile_solid_m3[1, 2], 20.)
    assert np.isclose(result.stranded_solid_m3[1, 7], 30.)
    assert np.isclose(total(result), 50.)


def test_relocation_follows_original_ocean_and_respects_radius():
    from terrain_pipeline.coastal_marine_longterm import _nearby_receivers
    wet = np.zeros((3, 7), bool)
    wet[1, 0] = True
    allowed = np.ones_like(wet)
    allowed[:, 2] = False
    rows, cols = _nearby_receivers(wet, allowed, 3)
    assert (rows[1, 1], cols[1, 1]) == (1, 0)
    assert rows[1, 3] == -1


def test_delta_optional_forcing_is_saved_and_resumable(tmp_path):
    from terrain_pipeline.coastal_delta_product import (
        DeltaConfig, advance_formation, load_checkpoint, save_checkpoint, start,
    )
    source, prior = load_checkpoint('.scratch/coast-marine-reorganization-20261102/growth-v3-stage10')
    cfg = DeltaConfig(formation_id='longterm-restart-test', inlet_zx=(214, 401),
        direction_xz=(10200, 1200), clearance_m=1, total_years=.002,
        interval_years=.001, solid_rate_m3_s=.08,
        longterm_transport={'sea_level_m': 1.})
    progress = start(source, cfg)
    progress['network'] = prior['network']
    first, progress, _ = advance_formation(source, progress, cfg)
    assert progress['longterm_forcing']['settling_velocity_m_s'] > 0
    # Cold-read an identity saved before boundary_transport was introduced.
    progress['longterm_forcing'].pop('boundary_transport')
    save_checkpoint(tmp_path/'formation', first, progress)
    restored, saved = load_checkpoint(tmp_path/'formation')
    second, finished, _ = advance_formation(restored, saved, cfg)
    assert finished['years_delivered'] == cfg.total_years
    assert np.isclose(total(second)-total(source), finished['supply_solid_m3'], atol=1e-4)


def test_external_supply_remains_nonnegative_and_within_capacity():
    initial = state(volume=1000.)
    source = np.zeros(initial.base_bed_m.shape)
    source[1, 1] = 2.
    ceiling = np.full(initial.base_bed_m.shape, -4.99)
    cfg = LongtermConfig(velocity_x_m_s=.02, diffusivity_m2_s=.05,
                         settling_velocity_m_s=.1, max_step_s=10., max_rise_m=.1)
    result, report = advance(initial, 50., cfg, source_rate_m3_s=source,
                             wet_mask=np.ones(ceiling.shape, bool), bed_ceiling_m=ceiling)
    assert np.min(result.bed_solid_m3) >= 0
    assert np.min(result.mobile_solid_m3) >= 0
    assert np.min(result.stranded_solid_m3) >= 0
    assert np.max(result.bed_m - ceiling) < 1e-8
    assert np.isclose(total(result), total(initial) + 100.)
    assert np.isclose(report['deposited_solid_m3'], result.bed_solid_m3.sum())


def test_mouth_direction_moves_finite_inventory_without_adding_mass():
    from terrain_pipeline.coastal_marine_sediment import MouthForcing
    initial = state(opened=True)
    cfg = LongtermConfig(velocity_x_m_s=0., velocity_z_m_s=0., diffusivity_m2_s=.01,
                         settling_velocity_m_s=.003, boundary_rate_s=.001, max_step_s=20.)
    east = MouthForcing(1, 1, (10., 10.), (1., 0.), 20., 10., 1.)
    west = replace(east, direction_xz=(-1., 0.))
    a, _ = advance(initial, 400., cfg, mouth_forcing=[east])
    b, _ = advance(initial, 400., cfg, mouth_forcing=[west])
    baseline, _ = advance(initial, 400., cfg)
    assert a.bed_solid_m3[1, 2:].sum() > b.bed_solid_m3[1, 2:].sum()
    for result in (a, b, baseline):
        assert np.isclose(total(result), total(initial))
        assert result.water_input_m3 == initial.water_input_m3
        assert np.min(result.mobile_solid_m3) >= 0
        assert np.max(result.bed_m) <= cfg.sea_level_m + 1e-8


def test_zero_and_disconnected_mouth_match_background():
    from terrain_pipeline.coastal_marine_sediment import MouthForcing
    initial = state(opened=True)
    cfg = LongtermConfig(max_step_s=20.)
    zero = MouthForcing(1, 1, (10., 10.), (1., 0.), 0., 10., 1.)
    disconnected = replace(zero, row=0, col=0, discharge_m3_s=20.)
    wet = np.zeros(initial.base_bed_m.shape, bool)
    wet[1, 4:] = True
    baseline, _ = advance(initial, 100., cfg, wet_mask=wet)
    for mouth in (zero, disconnected):
        result, _ = advance(initial, 100., cfg, wet_mask=wet, mouth_forcing=[mouth])
        assert np.array_equal(result.bed_solid_m3, baseline.bed_solid_m3)
        assert np.array_equal(result.mobile_solid_m3, baseline.mobile_solid_m3)
        assert np.isclose(total(result), total(initial))


@pytest.mark.parametrize('cell,velocity', [
    ((1,0),(-2.,0.)), ((1,2),(2.,0.)), ((0,1),(0.,-2.)), ((2,1),(0.,2.)),
])
def test_advective_outflow_uses_actual_open_face_and_conserves(cell, velocity):
    mobile=np.zeros((3,3));mobile[cell]=100.
    seeds=np.zeros((3,3),bool);seeds[cell]=True
    initial=make_state(base_bed_m=np.full((3,3),-5.),bed_solid_m3=0.,mobile_solid_m3=mobile,
        porosity=.4,valid_mask=True,ocean_seed_mask=seeds,spacing_m=10.,origin_xz_m=(0.,0.),source_identity='open-face')
    cfg=LongtermConfig(velocity_x_m_s=velocity[0],velocity_z_m_s=velocity[1],diffusivity_m2_s=0.,
        settling_velocity_m_s=0.,boundary_rate_s=.03,max_step_s=1.,boundary_transport='advective_outflow')
    out,report=advance(initial,1.,cfg)
    # One backward-Euler step exports exactly the solved donor times the
    # physical normal rate plus the independent seed exchange rate.
    expected=100.*(.2+.03)/(1.+.2+.03)
    assert out.exported_solid_m3==pytest.approx(expected)
    assert out.mobile_solid_m3.sum()==pytest.approx(100.-expected)
    assert total(out)==pytest.approx(total(initial))
    assert report['exported_solid_m3']==pytest.approx(expected)


def test_corner_counts_two_outgoing_faces_and_single_seed_exchange():
    mobile=np.zeros((3,3));mobile[-1,-1]=100.
    seeds=np.zeros((3,3),bool);seeds[-1,-1]=True
    initial=make_state(base_bed_m=np.full((3,3),-5.),bed_solid_m3=0.,mobile_solid_m3=mobile,
        porosity=.4,valid_mask=True,ocean_seed_mask=seeds,spacing_m=10.,origin_xz_m=(0.,0.),source_identity='corner')
    cfg=LongtermConfig(velocity_x_m_s=1.,velocity_z_m_s=2.,diffusivity_m2_s=0.,
        settling_velocity_m_s=0.,boundary_rate_s=.03,max_step_s=1.,boundary_transport='advective_outflow')
    out,_=advance(initial,1.,cfg)
    assert out.exported_solid_m3==pytest.approx(100.*.33/1.33)
    assert total(out)==pytest.approx(100.)


@pytest.mark.parametrize('seed_cell,velocity', [((1,2),(-2.,0.)), (None,(2.,0.))])
def test_inward_or_interior_or_closed_face_adds_no_source_or_outflow(seed_cell,velocity):
    mobile=np.zeros((3,3));mobile[1,1]=100.
    seeds=np.zeros((3,3),bool)
    if seed_cell is not None: seeds[seed_cell]=True
    initial=make_state(base_bed_m=np.full((3,3),-5.),bed_solid_m3=0.,mobile_solid_m3=mobile,
        porosity=.4,valid_mask=True,ocean_seed_mask=seeds,spacing_m=10.,origin_xz_m=(0.,0.),source_identity='closed-faces')
    cfg=LongtermConfig(velocity_x_m_s=velocity[0],velocity_z_m_s=velocity[1],diffusivity_m2_s=0.,
        settling_velocity_m_s=0.,boundary_rate_s=0.,max_step_s=1.,boundary_transport='advective_outflow')
    out,_=advance(initial,1.,cfg,wet_mask=np.ones((3,3),bool))
    assert out.exported_solid_m3==0
    assert out.mobile_solid_m3.sum()==pytest.approx(100.)
    assert total(out)==pytest.approx(100.)


def test_nonperimeter_seed_does_not_gain_advective_exit():
    from terrain_pipeline.coastal_marine_longterm import _solve
    # Public MarineState construction already rejects interior ocean seeds.
    # Exercise the lower flux seam too: its advection adds only real outer faces.
    mobile=np.zeros((3,3));mobile[1,1]=100.
    seeds=np.zeros((3,3),bool);seeds[1,1]=True
    cfg=LongtermConfig(velocity_x_m_s=2.,velocity_z_m_s=0.,diffusivity_m2_s=0.,
        settling_velocity_m_s=0.,boundary_rate_s=0.,boundary_transport='advective_outflow')
    moved,settled,exported=_solve(mobile,np.zeros_like(mobile),np.ones_like(seeds),
        np.full_like(mobile,5.),seeds,10.,1.,np.full_like(mobile,1000.),cfg)
    assert exported.sum()==0 and settled.sum()==0
    assert moved.sum()==pytest.approx(100.)


def test_boundary_mode_default_is_legacy_and_invalid_mode_rejected():
    initial=state(opened=True)
    config=LongtermConfig(max_step_s=20.)
    default,_=advance(initial,100.,config)
    legacy,_=advance(initial,100.,replace(config,boundary_transport='exchange_only'))
    assert np.array_equal(default.bed_solid_m3,legacy.bed_solid_m3)
    assert np.array_equal(default.mobile_solid_m3,legacy.mobile_solid_m3)
    assert default.exported_solid_m3==legacy.exported_solid_m3
    with pytest.raises(ValueError,match='boundary transport'):
        advance(initial,1.,replace(config,boundary_transport='unknown'))
