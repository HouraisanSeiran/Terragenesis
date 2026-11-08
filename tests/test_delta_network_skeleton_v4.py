"""Tests for the complex delta network v4 (v3 skeleton + sand-apron land building, reference-image metrics)."""
import dataclasses
import os

import numpy as np
import pytest

from terrain_pipeline import delta_network_site as site
from terrain_pipeline import delta_network_skeleton_v4 as sk4
from terrain_pipeline import delta_network_terrain_v3 as t3
from terrain_pipeline import delta_network_terrain_v4 as t4

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def built():
    anchor = site.find_anchor(os.path.join(ROOT, site.TD_DIR), t=0.30)
    spec = site.SiteSpec(anchor_world_m=anchor)
    tdb, tdo, inside = site.sample_td(spec)
    assert inside.all()
    g = sk4.build_delta_network_v4(sk4.DeltaParamsV4())
    tp = t4.TerrainParamsV4()
    base = t3.build_terrain_v3(spec, g, tdb, tdo, tp)
    T = t4.postprocess_v4(spec, g, base, tdb, tdo, tp)
    return dict(spec=spec, g=g, tdb=tdb, tdo=tdo, tp=tp, base=base, T=T)


def test_skeleton_hard_acceptance(built):
    g = built['g']
    rep = sk4.validate_graph(g)
    assert rep['ok']
    assert rep['max_node_conservation_error'] <= 1e-9
    assert rep['turns_ge_90deg'] == 0
    assert rep['edges_without_path_to_sea'] == 0


def test_no_nan_and_masks(built):
    T = built['T']
    assert np.isfinite(T['bed']).all()
    assert T['sand'].dtype == bool
    assert not (T['sand'] & T['chan']).any()
    assert not (T['sand'] & ~T['land_dry']).any()


def test_postprocess_deterministic(built):
    b = built
    T2 = t4.postprocess_v4(b['spec'], b['g'], b['base'], b['tdb'], b['tdo'], b['tp'])
    for k in ('bed', 'chan', 'sand', 'water', 'island_label'):
        assert np.array_equal(b['T'][k], T2[k]), k


def test_no_enclosed_ponds(built):
    T = built['T']
    m = t4.terrain_metrics_v4(built['spec'], built['g'], T)
    assert m['pond_check']['n_enclosed_ponds_left'] == 0


def test_upstream_is_only_trunk(built):
    m = t4.terrain_metrics_v4(built['spec'], built['g'], built['T'])
    assert m['upstream_check']['n_chan_cells_above_apex_not_trunk'] == 0
    assert m['upstream_check']['n_components_u_lt_apex'] == 1


def test_connectivity_and_scale(built):
    m = t4.terrain_metrics_v4(built['spec'], built['g'], built['T'])
    assert m['island_connectivity']['ok']
    assert m['island_connectivity']['n_remaining_violations'] == 0
    assert m['apex_to_farthest_shore_km'] >= 30.0
    assert m['alongshore_width_u_ge_3km_km'] >= 30.0


def test_sand_area_in_reference_range(built):
    """Sand share of the delta extent: reference 3 has 0.22; accept a band around it (declared tolerance)."""
    T = built['T']
    dx = built['spec'].spacing_m
    sand_km2 = T['sand'].sum() * dx * dx / 1e6
    land_km2 = T['land_dry'].sum() * dx * dx / 1e6
    assert 0.15 <= sand_km2 / land_km2 <= 0.45
