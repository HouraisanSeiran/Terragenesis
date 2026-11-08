import numpy as np
import pytest
from terrain_pipeline.large_delta_suite import Scenario, initialize


def test_finite_inventory_and_source_boundaries():
    bed = np.full((80, 80), -2.)
    ocean = np.ones_like(bed, dtype=bool)
    ocean[:, :10] = False
    bed[:, :10] = 5.
    valid = np.ones_like(ocean)
    valid[-10:, :] = False
    ocean[~valid] = False
    scenario = Scenario('test', (1000., 4000.), 4500., 1., 1., .5, 30.)
    result = initialize(bed, valid, ocean, (0., 0.), 100., scenario)
    assert result['retained_solid_m3'] <= scenario.solid_inventory_m3 + 1e-6
    assert result['retained_solid_m3'] + result['unplaced_solid_m3'] == pytest.approx(scenario.solid_inventory_m3)
    assert np.all(result['deposit_m'][~ocean] == 0)
    assert np.all(result['bed_m'] >= bed)
    assert np.array_equal(result['bed_m'], initialize(bed, valid, ocean, (0., 0.), 100., scenario)['bed_m'])


def test_invalid_ocean_and_scenario_rejected():
    bed = np.full((4, 4), -1.)
    valid = np.ones((4, 4), bool)
    valid[0, 0] = False
    ocean = np.ones_like(valid)
    with pytest.raises(ValueError):
        initialize(bed, valid, ocean, (0., 0.), 100., Scenario('bad', (0., 0.), 1000, 1, 1, .5, 1))


def test_explicit_lobes_bound_deposition():
    bed = np.full((100, 100), -2.)
    valid = np.ones_like(bed, dtype=bool)
    ocean = valid.copy()
    scenario = Scenario('lobes', (5000., 5000.), 9000., 100., 20., .5, 600.,
                        lobes_xzr_m=((3000., 5000., 1500.), (7000., 5000., 1500.)))
    result = initialize(bed, valid, ocean, (0., 0.), 100., scenario)
    assert result['deposit_m'][50, 30] > 0
    assert result['deposit_m'][50, 70] > 0
    assert result['deposit_m'][50, 50] == 0
    assert result['retained_solid_m3'] <= scenario.solid_inventory_m3


def test_plain_rises_toward_apex_without_changing_uplands():
    bed = np.full((150, 150), -3.)
    bed[:, :5] = 20.
    valid = np.ones_like(bed, bool)
    ocean = bed < 0
    scenario = Scenario('slope', (7500., 7500.), 6000., 100., 30., .5, 600.,
                        plain_slope_m_per_m=.0004)
    r = initialize(bed, valid, ocean, (0., 0.), 100., scenario)
    assert r['bed_m'][75, 75] > r['bed_m'][75, 115] + 1.
    assert np.array_equal(r['bed_m'][:, :5], bed[:, :5])
    assert r['retained_solid_m3'] <= scenario.solid_inventory_m3
