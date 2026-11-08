"""Shoreline-driven, finite-stock extensions of the v7 delta network."""
from dataclasses import replace
import json
import numpy as np
from scipy import ndimage
from .coastal_delta_product import advance_formation, _network
from .coastal_marine_sediment import classify_ocean


def _saved_network(state, progress, cfg):
    saved = progress.get('network')
    if saved is None:
        for record in reversed(state.consumed_packets):
            saved = record.get('formation_progress', {}).get('network')
            if saved:
                break
    if saved is None:
        return _network(state, cfg)
    return ([tuple(c) for c in saved['trunk']],
            [[tuple(c) for c in p] for p in saved['branches']],
            list(saved['fork_indices']), [tuple(c) for c in saved['targets']])


def propose_network(state, progress, cfg, land_anchor_zx, *, max_cut_m=2.):
    """Extend one existing shoreline mouth by one D4 cell when feasible.

    The candidate is adjacent to attached newly emerged land and the active
    path endpoint. A cut may remove only deposited stock above the original
    marine bed. No original land, unknown cell, or other path is traversed.
    """
    trunk, branches, forks, targets = _saved_network(state, progress, cfg)
    paths = [trunk, *branches]
    land = state.valid_mask & (state.bed_m >= cfg.sea_level_m)
    labels, _ = ndimage.label(land)
    label = labels[tuple(land_anchor_zx)]
    if not label:
        raise ValueError('land anchor is not emerged')
    new_land = (labels == label) & (state.base_bed_m < cfg.sea_level_m)
    shoreline = ndimage.binary_dilation(new_land)
    occupied = set(c for path in paths for c in path)
    choices = []
    for index in (1, 2):
        end = paths[index][-1]
        if not shoreline[end]:
            continue
        for cell in ((end[0]-1,end[1]),(end[0]+1,end[1]),
                     (end[0],end[1]-1),(end[0],end[1]+1)):
            r, c = cell
            if not (0 <= r < land.shape[0] and 0 <= c < land.shape[1]):
                continue
            target_bed = min(float(state.bed_m[cell]), cfg.sea_level_m-cfg.clearance_m)
            cut = float(state.bed_m[cell]-target_bed)
            if (cell in occupied or not state.valid_mask[cell] or not shoreline[cell]
                    or state.base_bed_m[cell] > target_bed or cut > max_cut_m):
                continue
            distance = np.hypot(r-cfg.inlet_zx[0],c-cfg.inlet_zx[1])
            old_distance = np.hypot(end[0]-cfg.inlet_zx[0],end[1]-cfg.inlet_zx[1])
            if distance <= old_distance:
                continue
            choices.append((distance, -cut, -index, cell, target_bed))
    if not choices:
        return (trunk, branches, forks, targets), {}, {'trigger':'no feasible shoreline extension'}
    _, _, neg_index, cell, target_bed = max(choices)
    index = -neg_index
    old_end = paths[index][-1]
    paths[index].append(cell)
    targets[index] = cell
    cut = max(0., float(state.bed_m[cell]-target_bed))
    excavations = {cell: target_bed} if cut else {}
    return (trunk, branches, forks, targets), excavations, {
        'trigger':'attached shoreline at active endpoint', 'path_index':index,
        'old_endpoint_zx':old_end, 'new_endpoint_zx':cell,
        'cut_depth_m':cut, 'cut_solid_m3':cut*state.spacing_m**2*(1-float(state.porosity[cell]))}


def advance_stage(state, progress, cfg, land_anchor_zx, *, delivery_leak_multiplier=0.25):
    """Advance one finite interval; the original port owns the only supply."""
    old_trunk, old_branches, _, _ = _saved_network(state, progress, cfg)
    old_endpoints = [list(path[-1]) for path in [old_trunk, *old_branches]]
    network, excavation, info = propose_network(state, progress, cfg, land_anchor_zx)
    before = progress['supply_solid_m3']
    before_bed = float(state.bed_solid_m3.sum())
    before_export = state.exported_solid_m3
    result, updated, actual = advance_formation(state, progress, cfg,
        network_proposal=network, channel_excavation=excavation,
        delivery_leak_multiplier=delivery_leak_multiplier)
    info.update(years_start=progress['years_delivered'], years_end=updated['years_delivered'],
        supply_solid_m3=updated['supply_solid_m3']-before,
        bed_change_solid_m3=float(result.bed_solid_m3.sum())-before_bed,
        exported_solid_m3=result.exported_solid_m3-before_export,
        discharge_m3_s=cfg.discharge_m3_s, split_fractions=[0.504,0.28,0.216],
        delivery_leak_multiplier=delivery_leak_multiplier)
    info['mouths_before_zx'] = old_endpoints
    info['mouths_after_zx'] = [list(path[-1]) for path in [network[0], *network[1]]]
    info['excavation'] = updated['channel_treatment'][-1]['excavation']
    updated.setdefault('growth_history', []).append(json.loads(json.dumps(info)))
    record_id = 'formation:' + cfg.formation_id
    records = []
    for record in result.consumed_packets:
        if record['input_id'] == record_id:
            record = dict(record, formation_progress=updated)
        records.append(record)
    result = replace(result, consumed_packets=tuple(records))
    return result, updated, actual, info
