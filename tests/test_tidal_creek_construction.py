"""Actual tidal excavation, marine ownership and deterministic geometry."""
import copy

import numpy as np
from scipy.ndimage import binary_propagation

from terrain_pipeline.surface_rivers.metric_tidal_creek_construction import enrich_tidal_coast


def coast():
    zz, xx = np.indices((160, 220))
    bed = .6+.0001*xx
    marine = xx >= 180
    bed[marine] = -2.
    river = (np.abs(zz-80) <= 3) & ~marine
    bed[river] = -1.
    retained = river & (xx < 20)
    wet = marine | river
    return dict(bed_m=bed, open_marine_mask=marine, channel_mask=river,
        retained_upstream_raster_mask=retained, platform_weight=np.ones_like(bed),
        construction_footprint_mask=np.zeros_like(marine), wet_mask=wet,
        water_surface_m=np.where(wet, 0., bed), water_depth_m=np.where(wet, -bed, 0.)), dict(
        spacing_m=20., origin_xz_m=[-1700., 530.])


def test_seed_repeats_changes_and_keeps_source_immutable():
    arrays, metadata = coast()
    saved = {k: v.copy() for k, v in arrays.items()}
    saved_metadata = copy.deepcopy(metadata)
    first = enrich_tidal_coast(arrays, metadata)
    repeated = enrich_tidal_coast(arrays, metadata)
    changed = enrich_tidal_coast(arrays, metadata, world_seed=20261021)
    for key in arrays:
        np.testing.assert_array_equal(arrays[key], saved[key])
    assert metadata == saved_metadata
    for key in first['arrays']:
        np.testing.assert_array_equal(first['arrays'][key], repeated['arrays'][key])
    assert not np.array_equal(first['arrays']['bed_m'], changed['arrays']['bed_m'])


def test_carved_hierarchy_is_wet_connected_and_never_claims_river():
    source, metadata = coast()
    result = enrich_tidal_coast(source, metadata)
    arrays, audit = result['arrays'], result['audit']
    protected = arrays['tidal_protected_river_mask']
    np.testing.assert_array_equal(arrays['bed_m'][protected], source['bed_m'][protected])
    np.testing.assert_array_equal(arrays['bed_m'][source['open_marine_mask']], source['bed_m'][source['open_marine_mask']])
    assert not np.any(arrays['tidal_creek_mask'] & protected)
    assert not np.any(arrays['open_marine_mask'] & source['channel_mask'])
    connected = binary_propagation(source['open_marine_mask'], mask=arrays['open_marine_mask'])
    np.testing.assert_array_equal(connected, arrays['open_marine_mask'])
    assert np.all(arrays['water_depth_m'][arrays['tidal_creek_mask']] > 0.)
    assert audit['creek_count'] >= audit['root_count'] > 0
    assert audit['omitted_subresolution_branch_count'] > 0
    assert 0 in arrays['tidal_creek_level']
    parents = arrays['tidal_creek_parent_index']
    assert np.all(parents < np.arange(len(parents)))
    assert np.min(arrays['tidal_creek_width_m']) >= 50.
    points = arrays['tidal_creek_points_xz_m']
    cells = np.floor((points-np.array(metadata['origin_xz_m']))/20.+.5).astype(int)
    assert arrays['open_marine_mask'][cells[:, 1], cells[:, 0]].all()
    direction = np.asarray(result['metadata']['tidal_coast_construction']['inherited_river_direction_xz'])
    offsets = arrays['tidal_creek_offsets']
    for identity in range(len(offsets)-1):
        path = points[offsets[identity]:offsets[identity+1]]
        sign = 1. if arrays['tidal_creek_through_channel'][identity] else -1.
        assert np.min(sign*np.diff(path, axis=0)@direction) >= -1.e-8


def test_construction_bulk_ledger_matches_actual_changed_bed():
    source, metadata = coast()
    result = enrich_tidal_coast(source, metadata)
    arrays, audit = result['arrays'], result['audit']
    cut = source['bed_m']-arrays['bed_m']
    assert np.isfinite(cut).all() and np.all(cut >= 0.)
    assert audit['cut_bulk_m3'] == float(cut.sum()*400.)
    assert audit['fill_bulk_m3'] == 0.
    assert audit['net_bulk_m3'] == -audit['cut_bulk_m3']
    assert np.array_equal(cut > 0., arrays['tidal_creek_footprint_mask'])
    assert np.all(cut[~arrays['tidal_detail_allowed_mask']] == 0.)


def test_disjoint_service_storage_uses_actual_high_water_connection():
    source, metadata = coast()
    result = enrich_tidal_coast(source, metadata)
    arrays = result['arrays']
    service = arrays['tidal_service_id']
    valid = service >= 0
    areas = np.bincount(service[valid], minlength=len(arrays['tidal_service_area_m2']))*400.
    np.testing.assert_array_equal(areas, arrays['tidal_service_area_m2'])
    assert not np.any(valid & (source['open_marine_mask'] | arrays['tidal_protected_river_mask']))
    bed = arrays['bed_m']
    low = result['metadata']['tidal_coast_construction']['design_low_stage_m']
    high = result['metadata']['tidal_coast_construction']['design_high_stage_m']
    connected = binary_propagation(source['open_marine_mask'], mask=(bed < high)
        & (arrays['tidal_detail_allowed_mask'] | source['open_marine_mask']))
    exchange = np.maximum(high-bed, 0.)-np.maximum(low-bed, 0.)
    exchange[~connected] = 0.
    expected = np.bincount(service[valid], weights=exchange[valid]*400.,
        minlength=len(arrays['tidal_service_exchange_volume_m3']))
    np.testing.assert_allclose(expected, arrays['tidal_service_exchange_volume_m3'])
    assert result['audit']['final_exchange_volume_m3'] == float(expected.sum())
    design = arrays['tidal_design_service_id']
    valid_design = design >= 0
    expected_design = np.bincount(design[valid_design],
        weights=arrays['tidal_design_exchange_depth_m'][valid_design]*400.,
        minlength=len(arrays['tidal_design_exchange_volume_m3']))
    np.testing.assert_allclose(expected_design, arrays['tidal_design_exchange_volume_m3'])


def test_design_sections_record_unclipped_and_actual_trapezoid_area():
    source, metadata = coast()
    arrays = enrich_tidal_coast(source, metadata)['arrays']
    raw_width = arrays['tidal_design_unconstrained_width_m']
    raw_depth = arrays['tidal_design_unconstrained_depth_m']
    np.testing.assert_allclose(raw_width, 70.*raw_depth)
    np.testing.assert_allclose(.725*raw_width*raw_depth, arrays['tidal_design_cross_section_m2'])
    np.testing.assert_allclose(arrays['tidal_design_actual_mouth_cross_section_m2'],
        .725*arrays['tidal_design_width_m']*arrays['tidal_design_depth_m'])
    np.testing.assert_array_equal(arrays['tidal_design_resolution_limited'], raw_width < 50.)


def test_all_protected_scene_returns_valid_zero_path_result():
    source, metadata = coast()
    source['retained_upstream_raster_mask'][:] = True
    result = enrich_tidal_coast(source, metadata)
    arrays = result['arrays']
    np.testing.assert_array_equal(arrays['bed_m'], source['bed_m'])
    assert arrays['tidal_creek_offsets'].tolist() == [0]
    assert arrays['tidal_creek_points_xz_m'].shape == (0, 2)
    assert arrays['tidal_design_cross_section_m2'].shape == (0,)
    assert result['audit']['creek_count'] == result['audit']['cut_bulk_m3'] == 0
