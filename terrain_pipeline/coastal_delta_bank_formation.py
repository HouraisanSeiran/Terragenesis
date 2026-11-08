"""Explicit, conservative bank preparation using lagged saved water stages."""
from dataclasses import replace
import math

import numpy as np

from .coastal_delta_branching import _record
from .coastal_delta_geological_network import _footprint
from .coastal_delta_multicell import _prepare
from .coastal_delta_node_inventory import ChannelInventory


def prepare_banks(state, progress, *, max_cut_m=.5, min_wet_depth_m=.05, subdivisions=None):
    """Claim inundatable design-corridor area; return (state, progress, report).

    Distances are metres, areas m² and sediment amounts solid m³. Saved node
    stages are lagged: callers must solve hydraulics again after preparation.
    """
    if (not np.isfinite([max_cut_m, min_wet_depth_m]).all()
            or max_cut_m < 0 or min_wet_depth_m < 0):
        raise ValueError('invalid bank preparation limits')
    if subdivisions is None:
        subdivisions = progress.get('geological_network', {}).get('footprint_subdivisions', 8)
    if isinstance(subdivisions, bool) or not isinstance(subdivisions, int) or subdivisions < 2:
        raise ValueError('invalid footprint subdivisions')
    state, p = _prepare(state, progress)
    pool = ChannelInventory(state, p)
    geometry = p.get('route_geometry')
    if not geometry:
        raise ValueError('bank preparation requires irregular route geometry')
    coords = {tuple(row[:2]): row[2:4] for row in geometry['nodes']}
    paths = p['routes']
    try:
        points = [[coords[tuple(cell)] for cell in path] for path in paths]
        widths = {node: float(p['fixed_channel_footprint']['design_width_m'][str(node)])
                  for node in pool.node_keys}
    except KeyError as exc:
        raise ValueError('missing route geometry or design width') from exc
    if any(not math.isfinite(w) or w <= 0 for w in widths.values()):
        raise ValueError('invalid design width')
    targets = {node: pool.section_bed(node) for node in pool.node_keys}
    ordered, _, _, _, _, _, parts = _footprint(
        state, state.valid_mask, paths, points, widths, targets, subdivisions)
    stages = {}
    for row in p.get('river_hydraulics', {}).get('nodes', []):
        if len(row) >= 3 and row[2] is not None:
            try:
                stage = float(row[2])
            except (TypeError, ValueError):
                continue
            if math.isfinite(stage):
                stages[tuple(row[:2])] = stage
    area = state.spacing_m ** 2
    details = {str(node): {'added_area_m2': 0., 'cut_solid_m3': 0.,
                           'requested_area_m2': 0., 'rejected_area_m2': {}}
               for node in pool.node_keys}
    requests = {}
    design_area = 0.
    for node, entries in zip(ordered, parts):
        old = {}
        for part in pool._parts[node]:
            cell = tuple(part[:2])
            old[cell] = old.get(cell, 0.) + part[2]
        for r, c, fraction, _ in entries:
            design_area += fraction * area
            request = max(0., fraction - old.get((r, c), 0.))
            if request:
                details[str(node)]['requested_area_m2'] += request * area
                requests.setdefault((r, c), []).append((node, request))
    before_area = float(pool._fractions.sum() * area)
    def reject(node, reason, fraction):
        reasons = details[str(node)]['rejected_area_m2']
        reasons[reason] = reasons.get(reason, 0.) + fraction * area

    for cell, candidates in sorted(requests.items()):
        free = max(0., 1. - pool._fractions[cell])
        if free <= 1e-12:
            for node, request in candidates:
                reject(node, 'no_free_area', request)
            continue
        solid_factor = area * (1. - state.porosity[cell])
        outer_bed = state.base_bed_m[cell] + pool._outer['bed_solid_m3'][cell] / (free * solid_factor)
        eligible = []
        for node, request in candidates:
            if node not in stages:
                reject(node, 'missing_stage', request)
                continue
            limit = stages[node] - min_wet_depth_m
            floor = max(float(state.base_bed_m[cell]), targets[node], outer_bed - max_cut_m)
            if outer_bed > limit and floor > limit + 1e-10:
                reject(node, 'bank_above_wet_limit', request)
                continue
            eligible.append((node, request, max(0., outer_bed - limit)))
        demand = math.fsum(item[1] for item in eligible)
        scale = min(1., free / demand) if demand else 0.
        for node, request, depth in eligible:
            fraction = request * scale
            if fraction < request:
                reject(node, 'competing_for_free_area', request - fraction)
            if fraction <= 0:
                continue
            stock = [float(pool._outer[field][cell] * fraction / free) for field in
                     ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')]
            cut = min(stock[0], depth * fraction * solid_factor)
            for field, amount in zip(('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'), stock):
                pool._outer[field][cell] -= amount
            part = [*cell, fraction, stock[0] - cut, stock[1] + cut, stock[2]]
            pool._parts[node].append(part)
            pool._cells.setdefault(cell, []).append(part)
            pool._fractions[cell] += fraction
            # All contenders draw their share from the original outer density.
            free -= fraction
            details[str(node)]['added_area_m2'] += fraction * area
            details[str(node)]['cut_solid_m3'] += cut
    owners = {tuple(row[:2]): row for row in p['integrated']['owner_cells']}
    for cell in pool._cells:
        if cell not in owners:
            owners[cell] = [*cell, 0., 0., 0., 0., float(state.base_bed_m[cell]),
                            float(state.base_bed_m[cell]), 0.]
    p['integrated']['owner_cells'] = [owners[cell] for cell in sorted(owners)]
    state, p = pool.commit(state, p)
    state, p = _prepare(_record(state, p), p)
    p['fixed_channel_footprint']['lateral_change'] = 'explicit lagged bank preparation; hydraulics require recomputation'
    report = {'design_area_m2': design_area, 'effective_area_before_m2': before_area,
              'effective_area_after_m2': float(pool._fractions.sum() * area),
              'added_area_m2': math.fsum(d['added_area_m2'] for d in details.values()),
              'cut_solid_m3': math.fsum(d['cut_solid_m3'] for d in details.values()),
              'nodes': details, 'stage_reference': 'saved river_hydraulics nodes (lagged)',
              'hydraulics_recompute_required': True, 'max_cut_m': float(max_cut_m),
              'min_wet_depth_m': float(min_wet_depth_m), 'subdivisions': subdivisions}
    p['fixed_channel_footprint']['last_bank_preparation'] = report
    return _record(state, p), p, report

