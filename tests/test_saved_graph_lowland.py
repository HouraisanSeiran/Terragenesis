import numpy as np
from terrain_pipeline.runoff import LowlandRunoffConfig as LowlandRunoffConfig
from terrain_pipeline.runoff import _accumulate as _accumulate
from terrain_pipeline.runoff import classify_saved_graph as classify_saved_graph


def test_suppression_continuity_capture_and_mass():
    # Two basins with adjacent cells: 0->1->2 and 3->4->5.
    height = np.array([[10., 9., 8.], [10., 9., 8.]])
    rec = np.array([1, 2, -1, 4, 5, -1])
    order = np.array([0, 3, 1, 4, 2, 5])
    area = _accumulate(np.ones(6), rec, order)
    cfg = LowlandRunoffConfig(relief_radius_m=1, lowland_relief_m=100,
                              lowland_slope=100, lowland_initiation_area_m2=3,
                              upland_initiation_area_m2=1)
    result = classify_saved_graph(height, np.ones(6, bool), rec, order, area, 1, config=cfg)
    assert result['channel'].tolist() == [False, False, True, False, False, True]
    assert result['capture'].tolist() == [2, 2, 2, 5, 5, 5]
    assert _accumulate(np.ones(6), rec, order)[[2, 5]].sum() == 6
    # Upland initiation continues through a lowland whose threshold is unmet.
    cfg = LowlandRunoffConfig(relief_radius_m=1, lowland_relief_m=100,
                              lowland_slope=0.1, lowland_initiation_area_m2=100,
                              upland_initiation_area_m2=1)
    flat = np.array([[4., 2., 2., 2.]])
    result = classify_saved_graph(flat, np.ones(4, bool), np.array([1,2,3,-1]),
                                  np.arange(4), np.arange(1,5), 1, config=cfg)
    assert result['channel'].all()
