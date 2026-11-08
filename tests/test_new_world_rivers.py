import numpy as np
import pytest

from terrain_pipeline.new_world_rivers import prepare_rivers


def inputs():
    shape = (3, 3)
    false = np.zeros(shape, dtype=bool)
    channel = false.copy()
    channel[1, :2] = True
    receiver = np.full(shape, -1, dtype=int)
    receiver[1, 0:2] = [4, 5]
    ocean = false.copy()
    ocean[1, 2] = True
    return dict(bed_m=np.array([[4., 3., 2.], [4., 3., -1.], [4., 3., 2.]]),
        receiver=receiver, q_m3_s=np.ones(shape), channel_mask=channel,
        ocean_mask=ocean, lake_mask=false.copy(), unknown_mask=false.copy(),
        protected_mask=false.copy(), origin_native_xz=(0, 0), spacing_m=30.,
        source_identity="synthetic", bed_hardness=.5, bank_hardness=.5)


def test_geometry_keeps_ocean_and_does_not_certify_water():
    args = inputs()
    result = prepare_rivers(**args)
    assert result["arrays"]["final_bed_m"][1, 2] == -1.
    assert result["metadata"]["wet_connectivity_certified"] is False
    assert result["metadata"]["subgrid_sections_resolved"] is False
    assert len(result["evidence"]) == 2


def test_unknown_mask_and_identity_are_required():
    args = inputs()
    args["unknown_mask"] = np.zeros((3, 3), dtype=int)
    with pytest.raises(ValueError):
        prepare_rivers(**args)
    args = inputs()
    args["source_identity"] = ""
    with pytest.raises(ValueError):
        prepare_rivers(**args)


def hydraulic_inputs():
    x = np.arange(9, dtype=float)
    bed = np.tile(20. - x, (5, 1))
    return dict(bed_m=bed, valid_mask=np.ones_like(bed, dtype=bool),
        path_xz_m=np.array([[1., 2.], [3., 2.], [5., 2.], [7., 2.]]),
        width_m=np.full(4, .4), max_depth_m=np.full(4, 3.),
        origin_xz_m=(0., 0.), spacing_m=1., source_identity_sha256='a'*64,
        section_source='measured synthetic sections', roughness=.04, roughness_source='synthetic',
        time_seconds=np.array([0., 10.]), local_volume_m3=np.array([[.1, 0., 0., 0.]]),
        initial_volume_m3=np.zeros(4), downstream={'kind': 'open', 'stage_m': 10.})


def test_real_finite_routing_and_saved_source(tmp_path):
    from terrain_pipeline.new_world_rivers import solve_finite_hydraulics, save_finite_hydraulics
    args = hydraulic_inputs()
    args['time_seconds'][-1] = 100.
    result = solve_finite_hydraulics(**args)
    assert result['metadata']['status'] == 'complete'
    ledger = result['metadata']['water_ledger']
    assert ledger['input_m3'] == pytest.approx(ledger['final_storage_m3'] + ledger['outflow_m3'])
    assert result['arrays']['time_seconds'][-1] == 100.
    assert result['metadata']['sampled_sections_wet_at_end']
    assert np.all(result['arrays']['section_wet'][-1])
    assert ledger['outflow_m3'] > 0
    assert result['arrays']['section_bed_m'].shape[1] >= 2
    assert result['metadata']['raster_resolution'] == 'subgrid_unresolved'
    assert result['metadata']['construction_bulk_m3'] == result['metadata']['sediment_input_m3'] == 0
    destination = tmp_path / 'river50-hydraulic-test.npz'
    save_finite_hydraulics(result, destination)
    with np.load(destination, allow_pickle=False) as saved:
        assert 'section_bed_m' in saved and 'aaaaaaaa' in str(saved['metadata_json'])


def test_real_dry_and_unresolved_boundaries_and_obstruction():
    from terrain_pipeline.new_world_rivers import solve_finite_hydraulics
    args = hydraulic_inputs(); args['local_volume_m3'][:] = 0
    dry = solve_finite_hydraulics(**args)
    assert dry['metadata']['status'] == 'complete'
    assert not dry['metadata']['sampled_sections_wet_at_end']
    args['downstream'] = {}
    assert 'unknown downstream' in solve_finite_hydraulics(**args)['metadata']['reason']
    args['downstream'] = {'kind': 'lake', 'stage_m': 14., 'volume_m3': 100.}
    assert 'backwater' in solve_finite_hydraulics(**args)['metadata']['reason']
    args = hydraulic_inputs(); args['bed_m'][:, 4] = 25.
    assert 'obstruction' in solve_finite_hydraulics(**args)['metadata']['reason']
    args = hydraulic_inputs(); args['local_volume_m3'] = None
    assert 'unknown water' in solve_finite_hydraulics(**args)['metadata']['reason']
