import copy
from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_avulsion import extend_mouths
from terrain_pipeline.coastal_delta_evolution import load, save
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_delta_branching import _record, mouth_exterior_faces
from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
from terrain_pipeline.coastal_delta_routes import node_control_length, route_metrics
from test_coastal_delta_multicell import fixture


def test_closed_mouth_without_reachable_ocean_is_not_forced(tmp_path):
    state, progress = fixture()
    original = copy.deepcopy(progress['node_footprints'])
    out, updated, report = extend_mouths(state, progress, hydraulic_config=HydraulicConfig(12.),
                                         sea_level_m=-100., radius_m=10., max_cut_m=.5)
    assert not report['extended'] and report['failures']
    assert updated['node_footprints'] == original
    assert np.array_equal(out.base_bed_m, state.base_bed_m)
    for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        assert np.array_equal(getattr(out, field), getattr(state, field))
    assert out.time_s == state.time_s
    save(tmp_path/'closed', out, updated)
    restored, rp = load(tmp_path/'closed')
    assert restored.time_s == state.time_s and rp == updated


def test_extension_transfers_only_outer_inventory_and_preserves_old_parts(tmp_path):
    state, progress = fixture()
    faces = mouth_exterior_faces(state, progress)
    bed = state.bed_solid_m3.copy()
    for route_faces in faces:
        for cell in route_faces:
            cell = tuple(cell)
            bed[cell] += 4.*state.spacing_m**2*(1-state.porosity[cell])
    state = _record(replace(state, bed_solid_m3=bed), progress)
    old_parts = copy.deepcopy(progress['node_footprints'])
    out, updated, report = extend_mouths(state, progress, hydraulic_config=HydraulicConfig(12.),
                                         sea_level_m=0., radius_m=400., max_cut_m=.5)
    assert report['extended']
    old = {(r, c): parts for r, c, parts in old_parts}
    new = {(r, c): parts for r, c, parts in updated['node_footprints']}
    assert all(new[node] == parts for node, parts in old.items())
    assert len(new) > len(old)
    assert np.array_equal(out.base_bed_m, state.base_bed_m)
    assert out.time_s == state.time_s
    assert sum(getattr(out, f).sum() for f in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')) == pytest.approx(
        sum(getattr(state, f).sum() for f in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')))
    pool = ChannelInventory(out, updated)
    owners = {tuple(row[:2]): row for row in updated['integrated']['owner_cells']}
    for cell, row in owners.items():
        assert len(row) == 9
        parts = [part for _, _, entries in updated['node_footprints'] for part in entries
                 if tuple(part[:2]) == cell]
        assert row[2:6] == pytest.approx([sum(part[i] for part in parts) for i in range(2, 6)])
    metrics = route_metrics(updated, out.spacing_m)
    for node in updated['hydraulic_sections']['nodes']:
        key = tuple(node[:2])
        assert node[3] <= pool.area(key) / node_control_length(updated, key, out.spacing_m, metrics) + 1e-9
    save(tmp_path/'extended', out, updated)
    _, restored = load(tmp_path/'extended')
    assert restored == updated


def test_numerical_candidate_rejection_preserves_current_inventory(monkeypatch, tmp_path):
    from terrain_pipeline.coastal_delta_graph_hydraulics import HydraulicNumericalError
    from terrain_pipeline.coastal_delta_branching import _validate

    state, progress = fixture()
    progress['hydraulics_backend'] = 'physical_edge_graph'
    bed = state.bed_solid_m3.copy()
    for faces in mouth_exterior_faces(state, progress):
        for cell in faces:
            cell = tuple(cell)
            bed[cell] += 4.*state.spacing_m**2*(1-state.porosity[cell])
    state = _record(replace(state, bed_solid_m3=bed), progress)
    before = copy.deepcopy(progress)
    trials = []

    def fail_candidate(candidate_state, candidate_progress, level, config):
        assert len(candidate_progress['node_footprints']) > len(progress['node_footprints'])
        trials.append(candidate_progress['routes'])
        raise HydraulicNumericalError(.00831452, 30)

    monkeypatch.setattr('terrain_pipeline.coastal_delta_mouth_extension.solve', fail_candidate)
    out, updated, report = extend_mouths(state, progress, hydraulic_config=HydraulicConfig(12.),
        sea_level_m=0., radius_m=400., max_cut_m=.5)
    assert trials and not report['extended']
    assert report['trigger'] == 'numerical_failure'
    assert report['numerical_failures']
    for failure in report['numerical_failures']:
        assert failure['reason'] == 'numerical_failure'
        assert failure['residual'] == .00831452 and failure['evaluations'] == 30
        assert failure['path'] and failure['accepted'] is False
    assert progress == before
    for key in ('routes', 'node_footprints', 'hydraulic_sections', 'river_hydraulics', 'integrated'):
        assert updated[key] == progress[key]
    for field in ('base_bed_m', 'bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        assert np.array_equal(getattr(out, field), getattr(state, field))
    _validate(out, updated)
    save(tmp_path/'numerical-rejection', out, updated)
    _, restored = load(tmp_path/'numerical-rejection')
    assert restored == updated


def test_current_network_numerical_failure_still_propagates(monkeypatch):
    from terrain_pipeline.coastal_delta_graph_hydraulics import HydraulicNumericalError
    from terrain_pipeline.coastal_delta_evolution import advance_years

    state, progress = fixture()
    progress['hydraulics_backend'] = 'physical_edge_graph'
    state = _record(state, progress)
    before = copy.deepcopy(progress)

    def fail_current(*args, **kwargs):
        raise HydraulicNumericalError(.008, 30)

    monkeypatch.setattr('terrain_pipeline.coastal_delta_graph_hydraulics.solve_graph', fail_current)
    with pytest.raises(HydraulicNumericalError):
        advance_years(state, progress, .000001, input_id='current-network-failure',
            hydraulic_config=HydraulicConfig(12.))
    assert progress == before
