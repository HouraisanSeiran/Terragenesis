"""Saved products, finite forcing, and one-way continuation contracts."""
import json
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline.complete_delta import (
    default_forcing, high_sediment_challenge_forcing, validate_forcing, purpose_seed, save_run, load_run, resume,
)


def write_scene(path, offset=0.):
    bed = np.full((40,40),-2.)
    trunk = np.column_stack([np.arange(2.,16.)*20.,np.full(14,400.)])
    parent = np.column_stack([np.arange(15.,36.)*20.,np.full(21,400.)])
    secondary = np.column_stack([np.linspace(500.,700.,21),np.linspace(400.,600.,21)])
    incoming = np.column_stack([np.arange(3)*20.,np.full(3,400.)])
    trunk+=offset; parent+=offset; secondary+=offset; incoming+=offset
    marine = np.zeros_like(bed,bool); marine[:,35:]=True
    meta = dict(origin_xz_m=[0.,0.],spacing_m=20.,mouth_xz_m=[700.+offset,400.+offset],fan_apex_xz_m=[40.+offset,400.+offset])
    arrays = dict(bed_m=bed,base_bed_m=bed,metadata_json=np.asarray(json.dumps(meta)),
        trunk_path_xz_m=trunk,branch_paths_xz_m=np.asarray([parent,secondary]),
        trunk_width_m=np.asarray(80.),branch_width_m=np.asarray([60.,30.]),
        original_land_mask=bed>0.,retained_upstream_raster_mask=np.zeros_like(bed,bool),
        designed_incoming_path_xz_m=incoming,designed_incoming_bed_m=np.full(3,-2.),
        main_section_mask=np.ones_like(bed,bool),connected_ocean_mask=marine,open_marine_mask=marine,
        terminal_parent_index=np.asarray([-1,0]),terminal_level=np.asarray([0,1]))
    np.savez_compressed(path,**arrays)


def forcing(ids, solid=2.):
    return validate_forcing(dict(record_ids=ids,month_seconds=[100.]*len(ids),
        monthly_water_m3=[1000.]*len(ids),monthly_solid_m3=[solid]*len(ids)))


def test_forcing_finite_and_unique_records():
    f=high_sediment_challenge_forcing()
    assert f['total_seconds']==365*86400
    assert max(np.asarray(f['monthly_water_m3'])/f['month_seconds'])==180.
    assert 0.<f['total_solid_m3']<.8*f['total_seconds']
    assert purpose_seed('a')==purpose_seed('a')!=purpose_seed('b')
    archived=default_forcing()
    assert np.isclose(archived['total_solid_m3'],31101.98584437747)
    with pytest.raises(ValueError): forcing(['a','a'])
    with pytest.raises(ValueError): forcing(['a'],float('nan'))


def test_cold_resume_matches_continuous_and_emits_only_new_packets(tmp_path):
    first=tmp_path/'first'; first.mkdir(); write_scene(first/'scene.npz')
    f=forcing(['m1'])
    (first/'forcing.json').write_text(json.dumps(f))
    save_run(first,first/'scene.npz',f)
    second=tmp_path/'second'
    resume(first/'state.json',second,forcing(['m2']))
    cold=load_run(second)
    full=tmp_path/'full'; full.mkdir(); write_scene(full/'scene.npz')
    ff=forcing(['m1','m2']); (full/'forcing.json').write_text(json.dumps(ff))
    save_run(full,full/'scene.npz',ff)
    continuous=load_run(full)
    for key in ('final_bed_m','water_depth_m','monthly_terminal_q_m3_s','stored_solid_m3'):
        assert np.array_equal(cold['arrays'][key],continuous['arrays'][key])
    packets=json.loads((second/'outlet-packets.json').read_text())
    assert len(packets)==2 and all(p['month_index']==1 for p in packets)
    with pytest.raises(ValueError,match='already consumed'):
        resume(first/'state.json',tmp_path/'duplicate',forcing(['m1']))
    (second/'state.json').write_text('{}')
    with pytest.raises(ValueError,match='identity mismatch'): load_run(second)


def test_zero_solid_preserves_actual_bed(tmp_path):
    write_scene(tmp_path/'scene.npz'); f=forcing(['zero'],0.)
    (tmp_path/'forcing.json').write_text(json.dumps(f))
    summary=save_run(tmp_path,tmp_path/'scene.npz',f)
    data=load_run(tmp_path)['arrays']
    assert np.array_equal(data['initial_bed_m'],data['final_bed_m'])
    assert summary['final_wet_connectivity']['all_centerlines_wet']
    assert abs(summary['water_ledger']['residual_m3'])<1.e-5


def test_each_substep_joins_protected_apex_cell_with_its_own_head(tmp_path):
    write_scene(tmp_path/'scene.npz',offset=5.)
    f=forcing(['zero'],0.); (tmp_path/'forcing.json').write_text(json.dumps(f))
    summary=save_run(tmp_path,tmp_path/'scene.npz',f)
    arrays=load_run(tmp_path)['arrays']
    assert not arrays['raw_delta_only_substep_wet_snapshots'][:,20,2].any()
    assert arrays['substep_wet_hydraulic_snapshots'][:,20,2].all()
    assert summary['substep_hydraulic_checks']['all_centerlines_wet']


def test_tidal_construction_total_ledger_is_against_base(monkeypatch, tmp_path):
    import terrain_pipeline.complete_delta as complete
    source = tmp_path/'source.npz'
    np.savez_compressed(source, metadata_json=np.asarray(json.dumps(dict(seed=1))))
    base = np.zeros((2, 2))
    coast = np.asarray([[-2., 1.], [0., 0.]])
    final = np.asarray([[-3., 1.], [0., 0.]])
    coast_audit = dict(cut_bulk_m3=8., fill_bulk_m3=4., net_bulk_m3=-4.)
    def build(arrays, metadata, **kwargs):
        return dict(arrays=dict(base_bed_m=base, bed_m=coast),
            metadata=dict(metadata, algorithm='coast', spacing_m=2.), audit=coast_audit)
    def enrich(arrays, metadata, **kwargs):
        return dict(arrays=dict(arrays, bed_m=final),
            metadata=dict(metadata, tidal_coast_construction=dict(algorithm='tidal')),
            audit=dict(cut_bulk_m3=4., fill_bulk_m3=0., net_bulk_m3=-4.))
    monkeypatch.setattr(complete, 'construct_coast_bounded_scene', build)
    monkeypatch.setattr(complete, 'enrich_tidal_coast', enrich)
    result = complete.construct_scene(source, forcing(['one']))
    assert result['audit']['cut_bulk_m3'] == 12.
    assert result['audit']['fill_bulk_m3'] == 4.
    assert result['audit']['net_bulk_m3'] == -8.
    assert result['audit']['coast_construction'] == coast_audit
    assert result['audit']['tidal_detail']['cut_bulk_m3'] == 4.
    assert result['metadata']['construction_algorithms'] == dict(coast='coast', tidal_detail='tidal')
