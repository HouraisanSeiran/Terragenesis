from dataclasses import replace

import numpy as np

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
    save_checkpoint(tmp_path/'formation', first, progress)
    restored, saved = load_checkpoint(tmp_path/'formation')
    second, finished, _ = advance_formation(restored, saved, cfg)
    assert finished['years_delivered'] == cfg.total_years
    assert np.isclose(total(second)-total(source), finished['supply_solid_m3'], atol=1e-4)
