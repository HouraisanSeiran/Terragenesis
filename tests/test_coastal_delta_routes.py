import json
from pathlib import Path
import numpy as np
import pytest
from terrain_pipeline.coastal_delta_routes import (world_to_cell, connected_ocean, valley_path,
    backwater_profile, fine_backwater, manning_capacity, load_routes, partition_subgrid_stocks)


def test_world_mapping():
    assert world_to_cell((-5160, 5520), (-19950, -19950), 100, (450, 450)) == (255, 148)
    with pytest.raises(ValueError): world_to_cell((-30000, 0), (-19950, -19950), 100, (450, 450))


def test_closed_depression_is_not_ocean():
    bed = np.ones((5,5)); bed[0:2,0] = -1; bed[3,3] = -2
    seed = np.zeros_like(bed, bool); seed[0,0] = True
    sea = connected_ocean(bed, np.ones_like(seed), seed)
    assert sea.sum() == 2 and not sea[3,3]


def test_centimetre_ridge_and_high_barrier():
    bed = np.array([[0., .0068, -.1], [10., 10., 10.]])
    valid = np.ones_like(bed, bool); target = np.zeros_like(valid); target[0,2] = True
    path = valley_path(bed, valid, (0,0), target, 1., 100.)
    assert path.tolist() == [[0,0],[0,1],[0,2]]
    bed[0,1] = 10.
    with pytest.raises(ValueError): valley_path(bed, valid, (0,0), target, 1., 100.)


def test_backwater_and_fine_section_capacity():
    bed = np.array([0., .0068, -.5]); stage = backwater_profile(bed,100,80,150,.035)
    assert np.all(stage > bed) and stage[-1] > 0
    assert np.allclose(manning_capacity(stage[:-1]-bed[:-1],80,np.diff(-stage)/100,.035),150)
    outlet_capacity = manning_capacity(stage[-1]-bed[-1],80,stage[-1]/50,.035)
    assert outlet_capacity >= 150 * (1-1e-9)
    assert stage[-1]-bed[-1] >= (150/80/np.sqrt(9.81))**(2/3)
    fine = np.array([[1.,0.,1.],[.5,-.5,.5],[.5,-.5,.5]])
    levels = fine_backwater(fine,np.array([-40.,0.,40.]),np.array([0.,100.,200.]),1.,150.,.035)
    assert levels[-1] == 1. and np.all(np.diff(levels) <= 0)


def test_subgrid_ownership_conserves_each_solid_and_bed_geometry():
    from terrain_pipeline.coastal_marine_sediment import make_state
    s = make_state(base_bed_m=np.array([[0.,1.]]), bed_solid_m3=np.array([[60.,30.]]),
                   mobile_solid_m3=[[4.,6.]], stranded_solid_m3=[[3.,7.]], porosity=.4,
                   valid_mask=True, ocean_seed_mask=False, spacing_m=10., origin_xz_m=(0.,0.), source_identity='test')
    owner=partition_subgrid_stocks(s, {'fine_owner_area_fraction':np.array([[.25,0.]]),
                                        'fine_owner_bed_m':np.array([[-1.,1.]])})
    for name in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'):
        assert np.allclose(owner['fine_'+name]+owner['outer_'+name], getattr(s,name))
    assert np.isclose(owner['fine_base_bed_m'][0,0] + owner['fine_bed_solid_m3'][0,0]/(25*.6), -1.)
    assert np.isclose(owner['geometry_difference_bulk_m3'][0,0],(-1.-s.bed_m[0,0])*25)


def test_real_output_cold_read_shared_branches_and_inventory():
    p=Path('.scratch/coast-marine-reorganization-20261102/full-routes-initial')
    if not p.with_suffix('.json').exists(): pytest.skip('real artifact not built')
    routes, meta = load_routes(p)
    main=routes['main_cells_zx']; packed=routes['branch_cells_zx']; offsets=routes['branch_offsets']
    assert len(offsets) >= 3 and len(set(map(tuple, [packed[offsets[i]] for i in range(len(offsets)-1)]))) >= 2
    for i in range(len(offsets)-1):
        b=packed[offsets[i]:offsets[i+1]]
        assert any(np.array_equal(b[0], x) for x in main)
        assert np.all(np.abs(np.diff(b,axis=0)).sum(axis=1) == 1)
    assert np.all(np.abs(np.diff(main,axis=0)).sum(axis=1) == 1)
    assert meta['excavation']['new_solid_m3'] == 0 and meta['excavation']['new_rock_m3'] == 0
    assert meta['excavation']['historical_fine_destination'].startswith('unknown')
    assert np.all((routes['historical_cut_area_fraction'] >= 0) & (routes['historical_cut_area_fraction'] <= 1 + 1e-12))
    ledger = meta['excavation']
    assert np.isclose(routes['historical_cut_bulk_m3'].sum(), ledger['historical_cut_inside_window_bulk_m3'])
    assert np.isclose(ledger['historical_cut_inside_window_bulk_m3'] + ledger['historical_cut_outside_window_bulk_m3'], ledger['historical_fine_bulk_m3'], rtol=1e-6)
    assert meta['source_identity'] == json.loads((p.parent/'window100-v2/manifest.json').read_text())['source_identity']
    from terrain_pipeline.coastal_marine_sediment import load_state
    state = load_state(p.parent/'window100-v2/state.npz')
    with np.load(p.parent/'window100-v2/source.npz') as source:
        ocean = connected_ocean(state.bed_m, state.valid_mask, state.ocean_seed_mask) & source['source_ocean']
    assert ocean[tuple(main[-1])]
    assert np.isclose(meta['accepted_q_m3_s']+meta['pending_q_m3_s'],meta['requested_q_m3_s'])
    assert meta['mouth_capacity_m3_s'] >= meta['accepted_q_m3_s']*(1-1e-8)
    fraction=routes['owner_fine_area_fraction']
    for name in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'):
        assert np.allclose(routes['owner_fine_'+name]+routes['owner_outer_'+name],getattr(state,name))
    assert fraction[tuple(main[0])] > 0
    assert routes['section_bed_m'][0] == meta['fine_port_bed_m']
    assert meta['fine_port_bed_m'] != meta['coarse_port_bed_m']
    assert meta['fine_sha256'] and meta['fine_geometry_arrays_sha256']
    assert np.isclose(meta['owner_geometry_difference_bulk_m3'],routes['owner_geometry_difference_bulk_m3'].sum())
    mask = fraction > 0
    area = fraction[mask] * state.spacing_m**2
    recovered = (routes['owner_fine_base_bed_m'][mask] +
                 routes['owner_fine_bed_solid_m3'][mask] / (area * (1-state.porosity[mask])))
    assert np.allclose(recovered, routes['owner_fine_bed_m'][mask])


def test_backwater_uses_actual_segment_lengths():
    bed = np.array([-2., -2., -2.])
    short = backwater_profile(bed, 100., 20., 30., .035, segment_lengths_m=[50., 70.])
    long = backwater_profile(bed, 100., 20., 30., .035, segment_lengths_m=[150., 170.])
    assert long[0] > short[0]
    assert np.allclose(backwater_profile(bed, 100., 20., 30., .035),
                       backwater_profile(bed, 100., 20., 30., .035, segment_lengths_m=[100., 100.]))
    with pytest.raises(ValueError):
        backwater_profile(bed, 100., 20., 30., .035, segment_lengths_m=[0., 100.])


def test_irregular_prepare_and_single_trunk_start(tmp_path):
    from terrain_pipeline.coastal_marine_sediment import make_state
    from terrain_pipeline.coastal_delta_pipeline import start_irregular
    from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
    from terrain_pipeline.coastal_delta_branching import mouth_exterior_faces
    from terrain_pipeline.coastal_delta_product import save_checkpoint, load_checkpoint
    bed = np.full((10, 10), -1.)
    seeds = np.zeros_like(bed, bool); seeds[:, -1] = True
    state = make_state(base_bed_m=bed, bed_solid_m3=np.zeros_like(bed),
        mobile_solid_m3=np.zeros_like(bed), stranded_solid_m3=np.zeros_like(bed),
        porosity=.4, valid_mask=True, ocean_seed_mask=seeds, spacing_m=100.,
        origin_xz_m=(0., 0.), source_identity='test')
    fine = {'distance_m': np.array([0., 100., 200.]),
        'path_xz_m': np.array([[100., 400.], [200., 400.], [300., 400.]]),
        'stage_m': np.full(3, 3.), 'target_bed_m': np.full(3, -1.),
        'section_distance_m': np.array([0., 100., 200.]),
        'section_offset_m': np.array([-10., 0., 10.]),
        'section_bed_m': np.full((3, 3), -1.), 'spacing_m': 100.,
        'origin_xz_m': np.array([0., 0.]), 'bed_m': bed.copy(), 'cut_m': np.zeros_like(bed)}
    ocean = np.zeros_like(seeds); ocean[:, -1] = True
    state, progress, report = start_irregular(state, ocean, fine,
        {'width_m': 20., 'port_bed_m': -1., 'removed_bulk_m3': 0.},
        hydraulic_config=HydraulicConfig(3.), q_m3_s=10.)
    assert len(progress['routes']) == 1
    assert progress['integrated']['candidate_routes'] == []
    assert all(mouth_exterior_faces(state, progress))
    assert report['hydraulics']['route_q_m3_s'][0] > 0
    save_checkpoint(tmp_path / 'initial', state, progress)
    restored, loaded = load_checkpoint(tmp_path / 'initial')
    assert loaded['river_hydraulics'] == report['hydraulics']
    assert loaded['river_hydraulics']['route_q_m3_s'][0] > 0
    assert restored.consumed_packets[-1]['formation_progress'] == loaded
    assert loaded['active'] == report['hydraulics']['active']
    coords = progress['route_geometry']['nodes']
    assert next(row[2:] for row in coords if row[:2] == [4, 3]) == [300., 400.]
