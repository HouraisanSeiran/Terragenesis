import numpy as np
import pytest
from scipy import ndimage
from terrain_pipeline.large_delta_suite import Scenario, initialize
from terrain_pipeline.large_delta_suite_network import construct_network
from terrain_pipeline.large_delta_suite_event import run_event


def test_network_scales_and_short_event_conserves():
    size = 180
    spacing = 600.
    z, x = np.indices((size, size))
    bed = np.where(z < 30, 4., -4. - .002 * (z - 30) * spacing)
    ocean = z >= 30
    valid = np.ones_like(ocean)
    scenario = Scenario('fixture', (54000., 18000.), 48000., 400000., 20., .5, 4000., toe_depth_m=100.)
    formed = initialize(bed, valid, ocean, (0., 0.), spacing, scenario)
    network = construct_network(formed['bed_m'], bed, formed['landform'], valid,
                                ocean & (formed['bed_m'] < 0), (0., 0.), spacing, 4000., outlet_count=7)
    parent = network['parent']; sections = network['sections']
    assert len(network['outlet_zx']) >= 3
    assert len(parent) >= 5
    assert ndimage.label(network['river'], np.ones((3, 3)))[1] == 1
    sec = network['sections']
    assert np.array_equal(np.rint(sec[:, 1]/spacing).astype(int), sec[:, 4].astype(int))
    assert np.array_equal(np.rint(sec[:, 2]/spacing).astype(int), sec[:, 3].astype(int))
    rows, cols = sec[:, 3].astype(int), sec[:, 4].astype(int)
    terrestrial = formed['bed_m'][rows, cols] >= 0
    assert np.max(sec[terrestrial, 5] - formed['bed_m'][rows[terrestrial], cols[terrestrial]]) <= .500001
    assert np.all(sections[:, 5] > sections[:, 9])
    for i, p in enumerate(parent):
        if p >= 0:
            assert sections[sections[:, 0] == i][0, 5] == pytest.approx(sections[sections[:, 0] == p][-1, 5])
    event = run_event(network, 4000., .1, duration_s=1200., dt_s=10.)
    assert abs(event['water_residual_m3']) < 1.e-4
    assert abs(event['solid_residual_m3']) < 1.e-4
    assert (event['final_water_m3'] >= 0).all()
    assert np.isfinite(event['time_stage_m']).all()


def test_broad_plain_supports_many_distinct_outlets():
    size = 450
    spacing = 600.
    z, x = np.indices((size, size))
    bed = np.where(z < 60, 4., -4. - .001*(z-60)*spacing)
    ocean = z >= 60
    valid = np.ones_like(ocean)
    scenario = Scenario('broad', (135000., 36000.), 115000., 1800000., 20., .5, 18000., toe_depth_m=150.)
    formed = initialize(bed, valid, ocean, (0., 0.), spacing, scenario)
    network = construct_network(formed['bed_m'], bed, formed['landform'], valid,
                                ocean & (formed['bed_m'] < 0), (0., 0.), spacing, 18000., outlet_count=12)
    assert len(network['outlet_zx']) >= 9
    assert len(set(network['outlet_zx'])) == len(network['outlet_zx'])
    assert ndimage.label(network['river'], np.ones((3, 3)))[1] == 1


