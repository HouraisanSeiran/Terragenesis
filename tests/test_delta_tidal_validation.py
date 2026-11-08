"""The validation uses an ocean boundary, finite tides and no repeated river packets."""
import json

import numpy as np
import pytest

from terrain_pipeline.delta_tidal_validation import (
    PERIOD_S, tidal_context, simulate_tides, creek_coverage_checks,
    scene_tide_forcing, verify_saved_run,
)
from terrain_pipeline.environment_processes import _connected


def coast_fixture():
    bed = np.full((12, 16), 2.)
    bed[:, :4] = -2.
    bed[5:7, 4:12] = -.2
    bed[1:3, 11:14] = -.4  # Inland pool has no sea connection.
    protected = np.zeros_like(bed, bool)
    protected[5:7, 10:12] = True
    marine = np.zeros_like(bed, bool)
    marine[:, :4] = True
    scene = dict(tidal_protected_river_mask=protected,
        tidal_original_marine_seed_mask=marine)
    meta = dict(spacing_m=20., origin_xz_m=[0., 0.], world_seed=20261020)
    creek = np.zeros_like(bed, bool)
    creek[5:7, 4:10] = True
    return bed, tidal_context(bed, scene, meta), creek


def test_two_real_periods_flood_ebb_salt_and_frozen_bed():
    bed, context, creek = coast_fixture()
    result = simulate_tides(context, creek)
    ledger = result['ledger']
    assert result['records'][-1]['time_s'] == 2*PERIOD_S
    assert ledger['creek_flood_water_m3'] > 0.
    assert ledger['creek_ebb_water_m3'] > 0.
    assert abs(ledger['total_water_balance_residual_m3']) < 1.e-6
    assert abs(ledger['total_salt_balance_residual_kg']) < 1.e-5
    assert ledger['river_water_input_m3'] == ledger['river_solid_input_m3'] == 0.
    assert ledger['mobile_solid_m3'] == 0.
    assert ledger['bed_frozen_exact'] and ledger['protected_water_unchanged']
    high = _connected(bed, .65, context['ocean_mask'], context['valid_mask'])
    assert not high[1:3, 11:14].any()
    assert not high[context['protected_mask']].any()
    assert result['snapshots']['high']['water_m3'][creek].sum() > result['snapshots']['low']['water_m3'][creek].sum()


def test_zero_tide_control_has_no_exchange_or_river_input():
    _, context, creek = coast_fixture()
    ledger = simulate_tides(context, creek, amplitude_m=0.)['ledger']
    assert ledger['flood_water_m3'] == ledger['ebb_water_m3'] == 0.
    assert ledger['creek_flood_water_m3'] == ledger['creek_ebb_water_m3'] == 0.
    assert ledger['river_water_input_m3'] == ledger['river_solid_input_m3'] == 0.


def test_partial_negative_core_connection_is_rejected():
    bed = np.full((2, 2), -.2)
    core = np.ones_like(bed, bool)
    reachable = np.ones((3, 2, 2), bool)
    reachable[1:, 1, 1] = False
    water = np.full((3, 2, 2), 40.)
    checks, coverage, _ = creek_coverage_checks(bed,core,reachable,water,20.)
    assert coverage[1]['connected_fraction'] == .75
    assert not checks['mean_tide_entire_negative_core_connected']
    assert not checks['high_tide_entire_negative_core_connected']


def test_visible_wet_mask_excludes_ebb_films_without_clipping_water():
    bed = np.full((2, 2), -.2)
    core = np.ones_like(bed, bool)
    reachable = np.ones((3, 2, 2), bool)
    water = np.full((3, 2, 2), 40.)
    water[0] = .04  # 0.1 mm of residual water at 20 m spacing.
    unchanged = water.copy()
    checks, _, visible = creek_coverage_checks(bed,core,reachable,water,20.)
    assert not visible[0].any()
    assert visible[2].all()
    assert checks['creek_visible_low_high_area_changes']
    assert np.array_equal(water, unchanged)


def test_saved_scene_boundary_drives_levels_periods_and_control(tmp_path, monkeypatch):
    bed, context, creek = coast_fixture()
    source = tmp_path/'run'
    source.mkdir()
    period = 43200.
    metadata = dict(spacing_m=20., origin_xz_m=[0., 0.], world_seed=20261020,
        tidal_coast_construction=dict(design_low_stage_m=-1.5,
            design_high_stage_m=1.5, design_period_s=period))
    np.savez_compressed(source/'scene.npz', metadata_json=json.dumps(metadata),
        tidal_protected_river_mask=context['protected_mask'],
        tidal_original_marine_seed_mask=context['ocean_mask'],
        tidal_creek_footprint_mask=creek, tidal_creek_mask=creek,
        tidal_intertidal_mask=creek, tidal_creek_offsets=np.array([0, 2]),
        tidal_creek_points_xz_m=np.array([[80., 100.], [180., 100.]]))
    np.savez_compressed(source/'result.npz', final_bed_m=bed)
    monkeypatch.setattr('terrain_pipeline.delta_tidal_validation.load_run',
        lambda path: dict(arrays=dict(final_bed_m=bed)))
    output = tmp_path/'tides'
    result = verify_saved_run(source, output)
    assert all(result['checks'].values())
    assert result['forcing']['amplitude_m'] == 1.5
    assert result['forcing']['period_s'] == period
    assert result['forcing']['elapsed_seconds'] == 2*period
    assert result['forcing']['source'] == 'scene.metadata.tidal_coast_construction'
    assert result['records'][-1]['time_s'] == pytest.approx(2*period)
    assert result['zero_tide_control']['flood_water_m3'] == 0.
    assert result['zero_tide_control']['ebb_water_m3'] == 0.
    with np.load(output/'tides.npz') as tides:
        assert np.array_equal(tides['tide_levels_m'], [-1.5, 0., 1.5])
        assert np.allclose(tides['snapshot_time_s'], [period*1.75, period, period*1.25])
    saved = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    assert saved['forcing'] == result['forcing']


def test_legacy_scene_keeps_previous_tidal_boundary():
    forcing = scene_tide_forcing({})
    assert forcing['amplitude_m'] == .65
    assert forcing['period_s'] == PERIOD_S


@pytest.mark.parametrize('design', [
    dict(design_low_stage_m=-1.5),
    dict(design_low_stage_m=-1., design_high_stage_m=1.5, design_period_s=PERIOD_S),
    dict(design_low_stage_m=-1.5, design_high_stage_m=1.5, design_period_s=0.),
    dict(design_low_stage_m=-1.5, design_high_stage_m=float('nan'), design_period_s=PERIOD_S),
])
def test_invalid_or_incomplete_scene_boundary_is_rejected(design):
    with pytest.raises(ValueError):
        scene_tide_forcing(dict(tidal_coast_construction=design))
