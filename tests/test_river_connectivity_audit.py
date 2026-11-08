import numpy as np
import pytest
from terrain_pipeline.river_connectivity_audit import audit


def fixture():
    return dict(native_shape=np.array([1, 4]), origin_native_xz=np.array([-2, -1]), spacing_m=np.array(1.),
        node_x_m=np.array([-2., 1., -1., 0.]), node_z_m=np.full(4, -1.),
        node_width_m=np.ones(4), reach_source=np.array([0]), reach_target=np.array([1]),
        reach_projection_blocked=np.array([False]), reach_max_cut_limited=np.array([True]))


def test_midpoint_barrier_and_unknown_surface():
    g = fixture()
    bed = np.array([[0., 5., 1., 0.]])
    unknown = np.array([[False, True, False, False]])
    r = audit(g, bed, bed, unknown=unknown)[0]
    assert r["maximum_downstream_rise_m"] == 5
    assert r["crossings"]["unknown"] is True
    assert r["crossings"]["protected"] is None
    assert r["wet_connectivity"] == "unknown"
    assert {s["col"] for s in r["samples"]} == {0, 1, 2, 3}


def test_short_segment_and_partial_surface():
    g = fixture()
    g["node_x_m"][1] = -1.9
    bed = np.zeros((1, 4))
    r = audit(g, bed, bed, water_surface=np.array([[1., np.nan, np.nan, np.nan]]), water_source="measured")[0]
    assert r["length_m"] == pytest.approx(.1)
    assert r["wet_connectivity"] == "wet_at_samples"
    assert audit(g, bed, bed, water_surface=np.full((1, 4), np.nan), water_source="partial")[0]["wet_connectivity"] == "unknown"


def test_invalid_inputs():
    g = fixture()
    bed = np.zeros((1, 4))
    with pytest.raises(ValueError): audit(g, bed, np.zeros((4, 1)))
    with pytest.raises(ValueError): audit(g, bed, bed, lake=np.zeros((4, 1), bool))
    with pytest.raises(ValueError): audit(g, bed, bed, water_surface=bed)
    with pytest.raises(ValueError): audit(g, bed, bed, indices=np.array([-1]))
    g["spacing_m"] = np.array(0.)
    with pytest.raises(ValueError): audit(g, bed, bed)
