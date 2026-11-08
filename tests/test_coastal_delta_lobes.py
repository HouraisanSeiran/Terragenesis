import numpy as np
import pytest
from terrain_pipeline.coastal_delta_product import DeltaConfig, start, load_checkpoint, save_checkpoint
from terrain_pipeline.coastal_delta_lobes import advance_stage
from terrain_pipeline.coastal_marine_sediment import classify_ocean

SOURCE = '.scratch/coast-marine-reorganization-20261102/growth-v3-stage10'

def total(state):
    return sum(float(getattr(state, name).sum()) for name in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')) + state.exported_solid_m3 + state.unresolved_solid_m3

def test_switch_deposition_and_restart(tmp_path):
    source, prior = load_checkpoint(SOURCE)
    cfg = DeltaConfig(formation_id='lobe-test', inlet_zx=(214, 401), direction_xz=(10200, 1200), clearance_m=1, total_years=60, interval_years=20, solid_rate_m3_s=.08)
    progress = start(source, cfg)
    progress['network'] = prior['network']
    first, p1, _, info = advance_stage(source, progress, cfg, (213, 400))
    assert info['switched']
    assert info['metrics']['separation_cells'] >= 5
    assert np.array_equal(source.base_bed_m, first.base_bed_m)
    assert np.isclose(total(first)-total(source), p1['supply_solid_m3'], atol=1e-5)
    assert all(item['target_bed_m'] >= source.base_bed_m[tuple(item['cell_zx'])] for item in info['excavation'])
    save_checkpoint(tmp_path/'lobe', first, p1)
    restored, restored_progress = load_checkpoint(tmp_path/'lobe')
    second, p2, _, info2 = advance_stage(first, p1, cfg, (213, 400))
    resumed, p3, _, _ = advance_stage(restored, restored_progress, cfg, (213, 400))
    assert np.array_equal(second.bed_solid_m3, resumed.bed_solid_m3)
    assert p2 == p3 and not info2['switched']
    assert len([r for r in resumed.consumed_packets if r['input_id'] == 'formation:lobe-test']) == 1
    wet, _ = classify_ocean(second, 0)
    assert all(wet[tuple(c)] for path in [p2['network']['trunk'], *p2['network']['branches']] for c in path)
    with pytest.raises(ValueError, match='progress'):
        advance_stage(second, p1, cfg, (213, 400))

def test_both_branches_considered(monkeypatch):
    import terrain_pipeline.coastal_delta_lobes as lobes
    source, prior = load_checkpoint(SOURCE)
    cfg = DeltaConfig(formation_id='lobe-both', inlet_zx=(214, 401), direction_xz=(10200, 1200), clearance_m=1, total_years=40, interval_years=20, solid_rate_m3_s=.08)
    progress = start(source, cfg)
    progress['network'] = prior['network']
    starts = set()
    route = lobes._route
    def observed(cost, start_cell, end):
        starts.add(start_cell)
        return route(cost, start_cell, end)
    monkeypatch.setattr(lobes, '_route', observed)
    lobes.propose_switch(source, progress, cfg, (213, 400))
    trunk = progress['network']['trunk']
    assert {tuple(trunk[index]) for index in progress['network']['fork_indices']} <= starts


def test_unchanged_state_and_retired_mouth_remain_eligible():
    from copy import deepcopy
    from terrain_pipeline.coastal_delta_lobes import propose_switch
    source, prior = load_checkpoint(SOURCE)
    cfg = DeltaConfig(formation_id='lobe-repeat', inlet_zx=(214, 401), direction_xz=(10200, 1200), clearance_m=1, total_years=40, interval_years=20, solid_rate_m3_s=.08)
    progress = start(source, cfg)
    progress['network'] = prior['network']
    proposal, excavation, metrics = propose_switch(source, progress, cfg, (213, 400))
    assert proposal is not None
    repeat = propose_switch(source, progress, cfg, (213, 400))
    assert repeat == (proposal, excavation, metrics)
    # A previously retired outlet with no prescribed erosion remains eligible.
    with_history = deepcopy(progress)
    with_history['lobe_history'] = [{'switched': True, 'metrics': {'old_outlet_zx': metrics['new_outlet_zx']}, 'retired_mean_bed_m': -1e6}]
    assert propose_switch(source, with_history, cfg, (213, 400)) == repeat
    assert metrics['new_min_depth_m'] >= 0
    assert metrics['new_p10_depth_m'] >= metrics['new_min_depth_m']


def test_path_score_exposes_control_section():
    from terrain_pipeline.coastal_delta_lobes import _path_score
    path = [(0, i) for i in range(11)]
    depth = np.full((1, 11), 2.)
    space = np.zeros_like(depth)
    deep = _path_score(path, depth, space, 1.)
    depth[0, 5] = 0.
    shallow = _path_score(path, depth, space, 1.)
    assert shallow[0] < deep[0]
    assert shallow[2] == 0.
    assert shallow[4] < deep[4]


def test_reproposal_after_cut_does_not_reverse_without_bed_change():
    from dataclasses import replace
    from terrain_pipeline.coastal_delta_lobes import propose_switch
    source, prior = load_checkpoint(SOURCE)
    cfg = DeltaConfig(formation_id='lobe-static', inlet_zx=(214, 401), direction_xz=(10200, 1200), clearance_m=1, total_years=40, interval_years=20, solid_rate_m3_s=.08)
    progress = start(source, cfg)
    progress['network'] = prior['network']
    proposal, excavation, first = propose_switch(source, progress, cfg, (213, 400))
    stock = source.bed_solid_m3.copy()
    for cell, target in excavation.items():
        stock[cell] = (target - source.base_bed_m[cell]) * source.spacing_m**2 * (1 - source.porosity[cell])
    cut_state = replace(source, bed_solid_m3=stock)
    progress['network'] = dict(trunk=proposal[0], branches=proposal[1], fork_indices=proposal[2], targets=proposal[3])
    _, _, next_metrics = propose_switch(cut_state, progress, cfg, (213, 400))
    assert not (next_metrics.get('branch_index') == first['branch_index'] and next_metrics.get('new_outlet_zx') == first['old_outlet_zx'] and next_metrics.get('benefit_m', 0) > .15)
