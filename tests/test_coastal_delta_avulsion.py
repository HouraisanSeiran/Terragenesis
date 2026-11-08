from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_avulsion import activate_candidate
from terrain_pipeline.coastal_delta_branching import _record
from terrain_pipeline.coastal_delta_evolution import initialize, save, load
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_marine_sediment import make_state


def fixture(ridge=0.):
    base = np.full((9, 13), -2.)
    base[3, 5] = ridge
    seeds = np.zeros(base.shape, bool); seeds[:, -1] = True
    s = make_state(base_bed_m=base, bed_solid_m3=0., mobile_solid_m3=0., porosity=.4,
                   valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
                   origin_xz_m=(0., 0.), source_identity='test')
    main = np.array([[4, c] for c in range(12)])
    candidate = np.array([[4, 4]] + [[3, c] for c in range(4, 12)])
    data = {'main_cells_zx': main, 'branch_offsets': np.array([0, len(candidate)]),
            'branch_cells_zx': candidate, 'section_bed_m': np.full(12, -2.),
            'section_bank_m': np.ones(12), 'section_width_m': np.full(12, 30.),
            'section_stage_m': np.ones(12)}
    s, p = initialize(s, data, {'source_identity': 'test'}, discharge_m3_s=30.)
    return s, p


def raised(s, p):
    p = deepcopy(p)
    p['hydraulic_sections']['nodes'][7][2] += .2
    p['integrated']['sections']['section_bed_m'][7] += .2
    return _record(s, p), p


def test_baseline_and_no_deposition():
    s, p = fixture(.113); cfg = HydraulicConfig(4.)
    s, p, report = activate_candidate(s, p, hydraulic_config=cfg)
    assert report['trigger'] == 'baseline_recorded'
    a, b, report = activate_candidate(s, p, hydraulic_config=cfg)
    assert not report['activated'] and a is s and b is p


def test_positive_flow_cut_conservation_and_restart(tmp_path):
    s, p = fixture(-.1); cfg = HydraulicConfig(4.)
    stock = s.bed_solid_m3.copy(); stock[3, 5] = 1800.
    s = replace(s, bed_solid_m3=stock)
    from terrain_pipeline.coastal_delta_product import _source_fingerprint
    p['source_state_fingerprint'] = _source_fingerprint(s)
    s, p, _ = activate_candidate(s, p, hydraulic_config=cfg)
    s, p = raised(s, p)
    out, progress, report = activate_candidate(s, p, hydraulic_config=cfg)
    assert report['activated'] and report['actual_Q_m3_s'] > 0
    assert 0 < report['solid_cut_m3'] <= 1800.
    assert np.array_equal(out.base_bed_m, s.base_bed_m)
    assert np.allclose(out.bed_solid_m3 + out.mobile_solid_m3, s.bed_solid_m3 + s.mobile_solid_m3)
    assert np.max(s.bed_m-out.bed_m) <= .5 + 1e-9
    save(tmp_path/'checkpoint', out, progress)
    restored, loaded = load(tmp_path/'checkpoint')
    _, again, result = activate_candidate(restored, loaded, hydraulic_config=cfg)
    assert not result['activated'] and again == loaded


def test_barrier_rejected_without_partial_update():
    s, p = fixture(20.); cfg = HydraulicConfig(4.)
    s, p, _ = activate_candidate(s, p, hydraulic_config=cfg)
    s, p = raised(s, p)
    a, b, report = activate_candidate(s, p, hydraulic_config=cfg)
    assert not report['activated'] and a is s and b is p


def test_natural_overflow_without_cut():
    s, p = fixture(-.2); cfg = HydraulicConfig(4.)
    s, p, _ = activate_candidate(s, p, hydraulic_config=cfg)
    s, p = raised(s, p)
    _, _, report = activate_candidate(s, p, hydraulic_config=cfg)
    assert report['activated'] and report['solid_cut_m3'] == 0
    assert report['actual_Q_m3_s'] > 0


def mouth_fixture(barrier=0.2, sediment=0.):
    base = np.full((7, 10), 5.)
    base[3, :4] = -1.
    base[3, 4:7] = barrier
    base[:, 7:] = -1.
    seeds = np.zeros(base.shape, bool); seeds[:, 9] = True
    stock = np.zeros_like(base); stock[3, 4:7] = sediment
    s = make_state(base_bed_m=base, bed_solid_m3=stock, mobile_solid_m3=0., porosity=.4,
                   valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
                   origin_xz_m=(0., 0.), source_identity='test')
    main = np.array([[3, c] for c in range(4)])
    data = {'main_cells_zx': main, 'branch_offsets': np.array([0]),
            'branch_cells_zx': np.empty((0, 2), int), 'section_bed_m': np.full(4, -1.),
            'section_bank_m': np.ones(4), 'section_width_m': np.full(4, 30.),
            'section_stage_m': np.ones(4)}
    return initialize(s, data, {'source_identity': 'test'}, discharge_m3_s=30.)


def test_mouth_extension_natural_and_restart(tmp_path):
    from terrain_pipeline.coastal_delta_avulsion import extend_mouths
    s, p = mouth_fixture()
    out, progress, report = extend_mouths(s, p, hydraulic_config=HydraulicConfig(4.), max_cut_m=0.)
    assert report['extended'] and report['solid_cut_m3'] == 0
    assert report['extensions'][0]['actual_Q_m3_s'] > 0
    assert report['geometry_updates'] and len(progress['integrated']['sections']['section_bed_m']) == 4
    assert np.array_equal(out.base_bed_m, s.base_bed_m)
    save(tmp_path/'mouth', out, progress)
    restored, loaded = load(tmp_path/'mouth')
    again, repeat, info = extend_mouths(restored, loaded, hydraulic_config=HydraulicConfig(4.))
    assert info['trigger'] == 'already_open' and again is restored and repeat is loaded


def test_mouth_extension_sediment_cut_and_atomic_barrier():
    from terrain_pipeline.coastal_delta_avulsion import extend_mouths
    s, p = mouth_fixture(barrier=1.8, sediment=2400.)
    out, progress, report = extend_mouths(s, p, hydraulic_config=HydraulicConfig(2.))
    assert report['extended'] and report['solid_cut_m3'] > 0
    assert report['extensions'][0]['actual_Q_m3_s'] > 0
    assert np.array_equal(out.base_bed_m, s.base_bed_m)
    assert np.allclose(out.bed_solid_m3 + out.mobile_solid_m3, s.bed_solid_m3 + s.mobile_solid_m3)
    assert np.max(s.bed_m-out.bed_m) <= .5 + 1e-9
    blocked, bp = mouth_fixture(barrier=5.)
    a, b, fail = extend_mouths(blocked, bp, hydraulic_config=HydraulicConfig(2.))
    assert not fail['extended'] and a is blocked and b is bp


def test_candidate_mouth_follows_advanced_coast_and_reloads(tmp_path):
    from terrain_pipeline.coastal_delta_branching import mouth_exterior_faces
    s, p = fixture(-.2)
    p['integrated']['candidate_routes'][0] = [[4, 4], [3, 4], [3, 5], [3, 6], [3, 7], [3, 8]]
    base = s.base_bed_m.copy()
    base[2, 8] = base[3, 9] = base[2, 9] = .2
    s = replace(s, base_bed_m=base)
    from terrain_pipeline.coastal_delta_product import _source_fingerprint
    p['source_state_fingerprint'] = _source_fingerprint(s)
    s, p, _ = activate_candidate(s, p, hydraulic_config=HydraulicConfig(4.))
    s, p = raised(s, p)
    out, progress, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(4.))
    assert report['activated'] and report['actual_Q_m3_s'] > 0
    assert report['mouth_extension']['extended']
    assert report['mouth_extension']['geometry_updates']
    assert progress['routes'][-1][-1] != [3, 8]
    assert all(mouth_exterior_faces(out, progress))
    assert report['solid_cut_m3'] == pytest.approx(report['candidate_solid_cut_m3'] + report['mouth_solid_cut_m3'])
    save(tmp_path/'coast', out, progress)
    restored, loaded = load(tmp_path/'coast')
    a, b, again = activate_candidate(restored, loaded, hydraulic_config=HydraulicConfig(4.))
    assert not again['activated'] and a is restored and b is loaded


def test_candidate_mouth_unreachable_is_atomic():
    s, p = fixture(-.2)
    p['integrated']['candidate_routes'][0] = [[4, 4], [3, 4], [3, 5], [3, 6], [3, 7], [3, 8]]
    base = s.base_bed_m.copy()
    base[2, 8] = base[3, 9] = base[2, 9] = 10.
    stock = s.bed_solid_m3.copy(); stock[3, 5] = 2400.
    s = replace(s, base_bed_m=base, bed_solid_m3=stock)
    from terrain_pipeline.coastal_delta_product import _source_fingerprint
    p['source_state_fingerprint'] = _source_fingerprint(s)
    s, p, _ = activate_candidate(s, p, hydraulic_config=HydraulicConfig(4.))
    s, p = raised(s, p)
    before = deepcopy(p)
    a, b, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(4.), mouth_radius_m=100.)
    assert not report['activated'] and a is s and b is p and p == before



def test_irregular_mouth_extension_cuts_deposition_and_preserves_geometry():
    from terrain_pipeline.coastal_delta_avulsion import extend_mouths
    from terrain_pipeline.coastal_delta_branching import mouth_exterior_faces
    from terrain_pipeline.coastal_delta_routes import build_route_geometry, edge_length

    s, p = mouth_fixture(barrier=1.8, sediment=2400.)
    path = np.array(p['routes'][0])
    xy = path[:, ::-1].astype(float) * 100.
    xy[-1] += [10., 5.]
    p['route_geometry'] = build_route_geometry(s, [path], [xy], 'mesh-v1', 20260903)
    s = _record(s, p)
    original = deepcopy(p['route_geometry']['nodes'])
    assert not mouth_exterior_faces(s, p)[0]
    out, progress, report = extend_mouths(s, p, hydraulic_config=HydraulicConfig(2.))
    assert report['extended'] and report['solid_cut_m3'] > 0
    assert report['extensions'][0]['actual_Q_m3_s'] > 0
    assert mouth_exterior_faces(out, progress)[0]
    assert progress['route_geometry']['nodes'][:len(original)] == original
    assert np.allclose(out.bed_solid_m3 + out.mobile_solid_m3, s.bed_solid_m3 + s.mobile_solid_m3)
    assert np.max(s.bed_m - out.bed_m) <= .5 + 1e-9
    for a, b in zip(progress['routes'][0], progress['routes'][0][1:]):
        assert edge_length(progress, a, b, 100.) > 0


def test_irregular_mouth_unknown_barrier_stays_closed():
    from terrain_pipeline.coastal_delta_avulsion import extend_mouths
    from terrain_pipeline.coastal_delta_branching import mouth_exterior_faces
    from terrain_pipeline.coastal_delta_routes import build_route_geometry

    s, p = mouth_fixture()
    valid = s.valid_mask.copy(); valid[:, 5] = False
    s = replace(s, valid_mask=valid)
    path = np.array(p['routes'][0]); xy = path[:, ::-1].astype(float) * 100.
    p['route_geometry'] = build_route_geometry(s, [path], [xy], 'mesh-v1', 20260903)
    s = _record(s, p)
    before = deepcopy(p)
    out, updated, report = extend_mouths(s, p, hydraulic_config=HydraulicConfig(4.))
    assert not report['extended'] and report['trigger'] == 'no_feasible_extension'
    assert out is s and updated is p and p == before
    assert not mouth_exterior_faces(out, updated)[0]


def test_irregular_candidate_uses_saved_geometry():
    from terrain_pipeline.coastal_delta_routes import build_route_geometry
    s, p = fixture(-.2)
    main = np.asarray(p['routes'][0]); candidate = np.asarray(p['integrated']['candidate_routes'][0])
    main_xy = main[:, ::-1].astype(float) * 100.
    candidate_xy = candidate[:, ::-1].astype(float) * 100.
    candidate_xy[1:, 1] += 10.
    p['route_geometry'] = build_route_geometry(s, [main, candidate], [main_xy, candidate_xy], 'mesh-v1', 20260903)
    original = deepcopy(p['route_geometry'])
    s = _record(s, p)
    s, p, _ = activate_candidate(s, p, hydraulic_config=HydraulicConfig(4.))
    s, p = raised(s, p)
    _, result, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(4.))
    assert report['activated']
    assert result['route_geometry'] == original
