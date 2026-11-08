import numpy as np
import pytest
from tools.render_world_river_acceptance import crop_slices, colorize, render


def test_bounds_and_outside():
    m = {"spacing_m": 30, "origin_native_xz": [-2048, -2048], "shape_zx": [4096, 4096]}
    slices, extent = crop_slices(m)
    assert (slices[0].start, slices[0].stop, slices[1].start, slices[1].stop) == (1382, 3049, 1176, 2843)
    assert extent[0] <= -26170 and extent[1] >= 23830
    with pytest.raises(ValueError, match="outside"):
        crop_slices(m, (-100000, 0, 0, 100))


def test_negative_bed_is_not_ocean():
    bed = np.full((3, 3), -10, dtype=np.float32)
    mask = np.zeros((3, 3), dtype=bool)
    ocean = mask.copy(); ocean[0, 0] = True
    rgb = colorize(bed, ocean, mask, ~mask, 30)
    assert np.allclose(rgb[0, 0], (.12, .28, .36))
    assert not np.allclose(rgb[1, 1], rgb[0, 0])


def test_products_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="native product reader unavailable"):
        render(tmp_path, tmp_path / "out", "wrong", True, "water")
    with pytest.raises(ValueError, match="base-only"):
        render(tmp_path, tmp_path / "out", "wrong", False)
