import numpy as np
import pytest
import copy

from terrain_pipeline.world_geology import build_history, replay_history, sample_materials


def history():
    initial = dict(elevation_m=np.array([[200.,-100.],[100.,-500.]]),
                   continental_fraction=np.array([[1.,.6],[1.,.1]]),plate_id=np.array([[0,1],[0,1]]))
    final = dict(initial, elevation_m=np.array([[1400.,-400.],[50.,-1500.]]))
    return build_history(initial,final,world_seed=20260903,origin_xz_m=(0.,0.),spacing_m=10000.,
                         initial_source_identity='initial-real',final_source_identity='final-real')


def test_forward_operations_replay_and_conserve_columns():
    h = history()
    replay = replay_history(h)
    for name,value in replay['arrays'].items():
        np.testing.assert_array_equal(value,h['arrays'][name])
    assert abs(replay['budgets']['rock_bulk_residual_m3']) < 2.
    assert len(h['metadata']['events']) > 50
    assert h['metadata']['events'][0]['older_ma'] == 500
    assert h['metadata']['events'][-1]['younger_ma'] == 0
    for event in h['metadata']['events']:
        values = h['arrays'][event['array_reference']][event['array_stage']]
        assert np.count_nonzero(values) == event['affected_cells']


def test_actual_exposure_changes_material_properties():
    h = history()
    surface = h['arrays']['geological_surface_m'][0,1]
    top = sample_materials(h,15000.,5000.,surface)
    buried = sample_materials(h,15000.,5000.,surface-1400.)
    assert top['rock_index'] != buried['rock_index']
    assert top['bed_hardness'] != buried['bed_hardness']
    assert top['permeability_m2'] != buried['permeability_m2']
    assert 'not derived from porosity' in top['provenance']['permeability']['source']


def test_final_only_history_and_outside_are_rejected():
    with pytest.raises(ValueError,match='actual initial'):
        build_history(None,{},world_seed=20260903,origin_xz_m=(0,0),spacing_m=10000,
                      initial_source_identity='a',final_source_identity='b')
    with pytest.raises(ValueError,match='outside'):
        sample_materials(history(),-1.,0.,10.)


def test_order_independent_material_queries():
    h = history()
    x = np.array([5000.,15000.])
    z = np.array([5000.,5000.])
    e = np.array([1400.,-400.])
    whole = sample_materials(h,x,z,e)
    for i in range(2):
        single = sample_materials(h,x[i],z[i],e[i])
        for name in ('rock_index','bed_hardness','porosity','permeability_m2'):
            assert whole[name][i] == single[name]


def test_actual_stage_trace_preserves_nonmonotonic_uplift_history():
    initial = dict(elevation_m=np.full((2,2),100.),continental_fraction=np.ones((2,2)),
                   plate_id=np.array([[0,1],[0,1]]))
    final = dict(initial,elevation_m=np.full((2,2),1100.))
    initial['stage_elevation_m'] = np.stack([initial['elevation_m'],np.full((2,2),2100.),final['elevation_m']])
    initial['stage_continental_fraction'] = np.ones((3,2,2))
    initial['stage_plate_id'] = np.broadcast_to(initial['plate_id'],(3,2,2))
    h = build_history(initial,final,world_seed=20260903,origin_xz_m=(0,0),spacing_m=10000.,
                      stages=50,initial_source_identity='a',final_source_identity='b')
    changes = h['arrays']['tectonic_displacement_m']
    assert np.all(changes[:25] > 0)
    assert np.all(changes[25:] < 0)
    np.testing.assert_allclose(changes.sum(axis=0),1000.)
    assert 'saved forward' in h['metadata']['time_mapping']


def test_saved_deposition_erosion_fault_and_intrusion_change_columns():
    h = history()
    clean = copy.deepcopy(h)
    for key in ('tectonic_displacement_m','deposition_thickness_m','erosion_depth_m',
                'fault_displacement_m','fold_displacement_m','volcanic_thickness_m',
                'metamorphism_mask','intrusion_mask'):
        clean['arrays'][key][:] = 0
    clean['arrays']['deposition_thickness_m'][0,0,0] = 30.
    clean['arrays']['deposition_rock_index'][0,0,0] = 7  # sandstone above granite
    deposited = replay_history(clean)
    assert deposited['arrays']['layer_top_m'][1,0,0] > deposited['arrays']['layer_bottom_m'][1,0,0]
    assert deposited['budgets']['sediment_external_bulk_m3'] == 30.*1e8
    clean['arrays']['erosion_depth_m'][1,0,0] = 40.
    eroded = replay_history(clean)
    assert eroded['arrays']['layer_top_m'][1,0,0] == eroded['arrays']['layer_bottom_m'][1,0,0]
    assert eroded['budgets']['erosion_export_bulk_m3'] == 40.*1e8
    # Fault displacements change buried horizon positions relative to the final
    # surface correction when material was deposited after the displacement.
    clean['arrays']['fault_displacement_m'][0,0,0] = 20.
    faulted = replay_history(clean)
    assert faulted['budgets']['tectonic_displacement_volume_m3'] == 20.*1e8
    assert faulted['arrays']['layer_bottom_m'][0,0,0] == eroded['arrays']['layer_bottom_m'][0,0,0] + 20.
    clean['arrays']['metamorphism_mask'][2,0,0] = True
    metamorphic = replay_history(clean)
    assert metamorphic['arrays']['layer_rock_index'][0,0,0] != faulted['arrays']['layer_rock_index'][0,0,0]
    clean['arrays']['intrusion_mask'][3,0,0] = True
    intrusive = replay_history(clean)
    assert intrusive['arrays']['layer_rock_index'][0,0,0] == 0
    assert intrusive['budgets']['intrusion_replacement_bulk_m3'] > 0.
