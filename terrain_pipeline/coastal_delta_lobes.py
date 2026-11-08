"""Experimental shoreline lobe switching over the single formation ledger.

Scores use local water-column accommodation and finite deposit blockage. They
are game-scale proxies, not a hydrodynamic avulsion prediction.
"""
from dataclasses import replace
import json
import numpy as np
from scipy import ndimage
from .coastal_delta_product import _route, advance_formation
from .coastal_delta_growth import _saved_network
from .coastal_marine_sediment import classify_ocean


def _path_score(path, depth, space, clearance):
    """Score actual effective depths; include a low-depth control section."""
    depths = np.array([depth[cell] for cell in path[1:]], dtype=float)
    fraction = np.clip(depths / (2. * clearance), 0., 1.)
    deficit = float(1. - np.mean(fraction))
    bottleneck = float(np.min(depths))
    low_depth = float(np.percentile(depths, 10))
    conveyance = float(np.mean(fraction) * min(low_depth / (2. * clearance), 1.))
    score = float(space[path[-1]] - .035 * len(path) - 2. * deficit - (1. - min(low_depth / (2. * clearance), 1.)))
    return score, deficit, bottleneck, low_depth, conveyance


def propose_switch(state, progress, cfg, land_anchor_zx, *, max_cut_m=2., min_separation_cells=5):
    trunk, branches, forks, targets = _saved_network(state, progress, cfg)
    land = state.valid_mask & (state.bed_m >= cfg.sea_level_m)
    labels, _ = ndimage.label(land)
    label = labels[tuple(land_anchor_zx)]
    if not label:
        raise ValueError('land anchor is not emerged')
    coast = ndimage.binary_dilation(labels == label) & ~land
    ocean, _ = classify_ocean(state, cfg.sea_level_m)
    depth = np.maximum(cfg.sea_level_m-state.bed_m, 0.)
    space = ndimage.uniform_filter(np.where(ocean, np.minimum(depth, 12.), 0.), size=7)
    rows, cols = np.indices(land.shape)
    target_bed = np.minimum(state.bed_m, cfg.sea_level_m-cfg.clearance_m)
    cut = state.bed_m-target_bed
    base_allowed = state.valid_mask & (state.base_bed_m <= target_bed) & (cut <= max_cut_m) & (ocean | (cut > 0))
    choices = []
    for branch_index, old in enumerate(branches):
        occupied = set(trunk) | set(branches[1-branch_index])
        junction = trunk[forks[branch_index]]
        separation = np.hypot(rows-old[-1][0], cols-old[-1][1])
        distance = np.hypot(rows-junction[0], cols-junction[1])
        candidates = coast & ocean & (separation >= min_separation_cells) & (distance >= 4) & (distance <= 32)
        for cell in occupied:
            candidates[cell] = False
        allowed = base_allowed.copy()
        for cell in occupied:
            allowed[cell] = False
        allowed[junction] = True
        # Shallow water and excavation impose cost; deep pre-existing sediment
        # is not itself an obstruction.
        shallow = np.clip((2*cfg.clearance_m-depth)/(2*cfg.clearance_m), 0., 1.)
        cost = np.where(allowed, 1. + 1.5*shallow + .4*cut + .015*depth, np.inf)
        ranked = np.argsort(np.where(candidates, space-.035*distance, -np.inf).ravel())[::-1]
        old_score, old_deficit, old_min, old_p10, old_conveyance = _path_score(old, depth, space, cfg.clearance_m)
        evaluated = 0
        for flat in ranked[:80]:
            end = tuple(map(int, np.unravel_index(flat, land.shape)))
            if not candidates[end]:
                break
            try:
                path = _route(cost, junction, end)
            except ValueError:
                continue
            if len(path) < 5 or len(set(path)-set(old)) < 4:
                continue
            projected_depth = np.maximum(cfg.sea_level_m-target_bed, 0.)
            new_score, new_deficit, new_min, new_p10, new_conveyance = _path_score(path, projected_depth, space, cfg.clearance_m)
            excavation = {cell: float(target_bed[cell]) for cell in path if cut[cell] > 1e-9}
            cut_penalty = sum(float(cut[cell]) for cell in excavation) / max(len(path), 1)
            benefit = new_score-old_score-cut_penalty
            updated_branches = [list(p) for p in branches]
            updated_branches[branch_index] = path
            updated_targets = list(targets)
            updated_targets[branch_index+1] = end
            info = {'branch_index':branch_index, 'old_outlet_zx':list(old[-1]),
                'new_outlet_zx':list(end), 'old_accommodation_m':float(space[old[-1]]),
                'new_accommodation_m':float(space[end]), 'old_score_m':old_score,
                'new_score_m':new_score, 'old_shallow_deficit':old_deficit,
                'new_shallow_deficit':new_deficit, 'cut_penalty_m':cut_penalty,
                'old_min_depth_m':old_min, 'old_p10_depth_m':old_p10, 'old_conveyance':old_conveyance,
                'new_min_depth_m':new_min, 'new_p10_depth_m':new_p10, 'new_conveyance':new_conveyance,
                'benefit_m':benefit, 'route_cells':len(path),
                'separation_cells':float(separation[end])}
            choices.append((benefit, (trunk, updated_branches, forks, updated_targets), excavation, info))
            evaluated += 1
            if evaluated >= 8:
                break
    if not choices:
        return None, {}, {'reason':'no connected shoreline outlet with finite deposit cut'}
    _, proposal, excavation, info = max(choices, key=lambda item:item[0])
    return proposal, excavation, info

def advance_stage(state, progress, cfg, land_anchor_zx, *, min_residence_intervals=3,
                  switch_margin_m=0.15, delivery_leak_multiplier=.25):
    """Advance once; apply a switch only after residence and score hysteresis."""
    network = _saved_network(state, progress, cfg)
    history = progress.get('lobe_history', [])
    last_switch = next((h['interval'] for h in reversed(history) if h['switched']), -min_residence_intervals)
    proposal, excavation, metrics = propose_switch(state, progress, cfg, land_anchor_zx)
    benefit = metrics.get('benefit_m', -1e9)
    switch = proposal is not None and len(history)-last_switch >= min_residence_intervals and benefit > switch_margin_m
    chosen = proposal if switch else network
    depth = np.maximum(cfg.sea_level_m-state.bed_m, 0.)
    # Use the same projected post-excavation bed used for route selection.
    if switch:
        depth = depth.copy()
        for cell, bed in excavation.items():
            depth[cell] = max(cfg.sea_level_m - bed, 0.)
    # Shares respond to present channel depth, independent of buried deposits.
    conveyance = []
    for path in chosen[1]:
        channel_depth = np.array([depth[c] for c in path[1:]])
        fractions = np.clip(channel_depth/(2*cfg.clearance_m), 0., 1.)
        conveyance.append(float(np.mean(fractions) * min(np.percentile(channel_depth, 10)/(2*cfg.clearance_m), 1.)))
    splits = (float(.34*conveyance[0]), float(.30*conveyance[1]))
    before = json.loads(json.dumps({'trunk':network[0], 'branches':network[1], 'fork_indices':network[2], 'targets':network[3]}))
    result, updated, actual = advance_formation(state, progress, cfg, network_proposal=chosen,
        channel_excavation=excavation if switch else {}, delivery_leak_multiplier=delivery_leak_multiplier,
        split_fractions=splits)
    old_end = metrics.get('old_outlet_zx', list(network[1][0][-1]))
    rows, cols = np.indices(state.bed_m.shape)
    retired_mean = float(np.mean(state.bed_m[(rows-old_end[0])**2+(cols-old_end[1])**2 <= 9]))
    info = {'retired_mean_bed_m':retired_mean, 'interval':len(history), 'year_start':progress['years_delivered'], 'year_end':updated['years_delivered'],
        'switched':switch, 'benefit_m':benefit, 'margin_m':switch_margin_m, 'residence_intervals':min_residence_intervals,
        'metrics':metrics, 'branch_conveyance':conveyance, 'network_before':before, 'network_after':updated['network'],
        'excavation':updated['channel_treatment'][-1]['excavation'], 'split':updated['split_history'][-1],
        'source_record':'formation:'+cfg.formation_id}
    updated.setdefault('lobe_history', []).append(info)
    records = tuple(dict(r, formation_progress=updated) if r['input_id'] == 'formation:'+cfg.formation_id else r
                    for r in result.consumed_packets)
    return replace(result, consumed_packets=records), updated, actual, info
