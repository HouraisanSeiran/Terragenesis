import numpy as np
import pytest

from tools.prepare_voronoi_mountains import generate, routing
from terrain_pipeline.mountain_forms import VoronoiConfig, rasterize_voronoi as rasterize


def test_routing_reports_real_three_field_comparison():
    fields = rasterize((0., 0.), (17, 17), 375., VoronoiConfig())
    report, arrays = routing(fields, (0., 0.), 375., 20260903)
    assert report['protection']['core_fraction'] > 0
    assert report['protection']['core_max_abs_error_m'] == 0
    assert report['protection']['outside_mean_abs_change_m'] > 0
    assert all(abs(report[key]['residual_m3_s']) < 1e-10 for key in ('advanced_base_m', 'unprotected_height_m', 'height_m'))
    assert arrays['height_m_terminal'].shape == (17 * 17,)
    assert np.isfinite(arrays['height_m_routed_q_m3_s']).all()


def test_existing_output_is_never_overwritten(tmp_path):
    target = tmp_path / 'existing'
    target.mkdir()
    marker = target / 'keep'
    marker.write_text('keep')
    with pytest.raises(FileExistsError):
        generate(target)
    assert marker.read_text() == 'keep'
