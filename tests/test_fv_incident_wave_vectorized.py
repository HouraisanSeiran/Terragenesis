from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig, incident_wave_field as reference
from terrain_pipeline.surface_rivers.metric_fv_incident_wave_vectorized import incident_wave_field


DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def scene():
    rng = np.random.default_rng(732)
    depth = rng.uniform(.02, 8., (17, 29))
    depth[5, :] = 0.
    depth[:, 11] = 0.
    depth[8, 11] = 1.e-5
    depth[4, 3] = 1.e-6
    rows, cols = depth.shape
    cells = np.r_[np.arange(rows) * cols, np.arange(rows) * cols + cols - 1,
        np.arange(cols), (rows - 1) * cols + np.arange(cols)]
    kinds = np.full(cells.size, 2)
    kinds[::3] = 0
    return depth, {"arrays": {"boundary_cell": cells, "boundary_kind": kinds}}


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("wave_height", [0., .3, 3.])
def test_all_fields_match_frozen_rays_on_rectangular_dry_coast(direction, wave_height):
    depth, geometry = scene()
    before = depth.copy()
    config = BedloadConfig(wave_direction_xz=direction, wave_height_m=wave_height)
    expected = reference(depth, geometry, config)
    actual = incident_wave_field(depth, geometry, config)
    for key in expected:
        np.testing.assert_allclose(actual[key], expected[key], rtol=2.e-14, atol=2.e-15)
    np.testing.assert_array_equal(depth, before)


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_marine_entry_blocking_and_break_flux_survive_deeper_water(direction):
    # Transform one deliberate ray into each cardinal orientation.
    ray = np.array([4., .1, 4., 0., 4.])
    depth = np.tile(ray, (3, 1))
    if direction[0] < 0:
        depth = depth[:, ::-1].copy()
    if direction[1]:
        depth = depth.T.copy()
        if direction[1] < 0:
            depth = depth[::-1].copy()
    dx, dz = direction
    starts = (np.arange(3) * 5 + (0 if dx > 0 else 4) if dx
        else (0 if dz > 0 else 4) * 3 + np.arange(3))
    geometry = {"arrays": {"boundary_cell": starts, "boundary_kind": np.array([2, 0, 2])}}
    config = replace(BedloadConfig(), wave_direction_xz=direction)
    result = incident_wave_field(depth, geometry, config)
    height = result["wave_height_m"]
    speed = result["wave_group_speed_m_s"]
    if dz:
        height, speed = height.T, speed.T
    if (dx or dz) < 0:
        height, speed = height[:, ::-1], speed[:, ::-1]
    assert not height[1].any()
    assert not height[:, 3:].any()
    assert height[0, 1] == pytest.approx(.078)
    assert height[0, 2] < height[0, 0]
    assert height[0, 1] ** 2 * speed[0, 1] == pytest.approx(height[0, 2] ** 2 * speed[0, 2])
