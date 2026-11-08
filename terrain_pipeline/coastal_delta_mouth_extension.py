"""Finite shoreline extension using only unowned multi-cell inventory."""
from copy import deepcopy
from dataclasses import replace

import numpy as np
from scipy import ndimage

from . import coastal_delta_branching as branching
from .coastal_delta_hydraulics import solve
from .coastal_delta_graph_hydraulics import HydraulicNumericalError
from .coastal_delta_node_inventory import ChannelInventory
from .coastal_delta_routes import irregular_valley_path, node_control_length, route_metrics


def extend_multicell_mouths(state, progress, *, hydraulic_config, sea_level_m=0.,
                            radius_m=2000., max_cut_m=.5):
    """Extend closed mouths at a discrete morphology boundary, preserving old parts."""
    branching._validate(state, progress)
    if ('route_geometry' not in progress or not np.isfinite([sea_level_m, radius_m, max_cut_m]).all()
            or radius_m <= 0 or max_cut_m < 0):
        raise ValueError('invalid multicell mouth extension settings')
    current, p = state, deepcopy(progress)
    changes, failures, numerical_failures = [], [], []
    graph_backend = p.get('hydraulics_backend') == 'physical_edge_graph'
    visited = set()
    for index in range(len(p['routes'])):
        old_end = tuple(p['routes'][index][-1])
        if graph_backend and old_end in visited:
            continue
        visited.add(old_end)
        if branching.mouth_exterior_faces(current, p, sea_level_m=sea_level_m)[index]:
            continue
        pool = ChannelInventory(current, p)
        occupied = np.zeros(current.bed_m.shape)
        stocks = {field: np.zeros_like(occupied) for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')}
        for r, c, parts in p['node_footprints']:
            for rr, cc, fraction, *amounts in parts:
                occupied[rr, cc] += fraction
                for field, amount in zip(stocks, amounts):
                    stocks[field][rr, cc] += amount
        free = np.maximum(0., 1.-occupied)
        outer = {field: np.maximum(0., getattr(current, field)-value) for field, value in stocks.items()}
        outer_bed = np.full_like(occupied, np.inf)
        mask = free > 1e-8
        outer_bed[mask] = current.base_bed_m[mask] + outer['bed_solid_m3'][mask] / (
            free[mask]*current.spacing_m**2*(1-current.porosity[mask]))
        wet = current.valid_mask & (current.bed_m < sea_level_m) & (occupied < 1e-8)
        labels, _ = ndimage.label(wet)
        ids = np.unique(labels[current.ocean_seed_mask & wet])
        ocean = np.isin(labels, ids[ids != 0]) & wet
        adjacent = ndimage.binary_dilation(ocean)
        start = tuple(p['routes'][index][-1])
        rows, cols = np.ogrid[:wet.shape[0], :wet.shape[1]]
        local = ((rows-start[0])**2+(cols-start[1])**2)*current.spacing_m**2 <= radius_m**2
        forbidden = free <= 1e-8
        for route in p['routes']:
            for cell in route:
                forbidden[tuple(cell)] = True
        forbidden[start] = False
        geometry = p['route_geometry']
        xy = next(row[2:] for row in geometry['nodes'] if tuple(row[:2]) == start)
        head = hydraulic_config.upstream_stage_limit_m
        section = next(row for row in p['hydraulic_sections']['nodes'] if tuple(row[:2]) == start)
        search_bed = outer_bed.copy()
        search_bed[start] = section[2]
        succeeded = False
        numerical_start = len(numerical_failures)
        for cutting in (False, True) if max_cut_m else (False,):
            cut = np.minimum(max_cut_m, np.maximum(outer_bed-current.base_bed_m, 0.)) if cutting else 0.
            target = current.valid_mask & local & adjacent & mask & ~forbidden & (outer_bed-cut < sea_level_m-1e-4)
            for _ in range(12):
                if not target.any():
                    break
                try:
                    path, path_xy = irregular_valley_path(search_bed, current.valid_mask & local, start, None,
                        head, current.spacing_m, origin_xz_m=current.origin_xz_m,
                        world_seed=geometry['seed'], forbidden=forbidden, target_mask=target, start_xz_m=xy)
                except ValueError:
                    break
                end = tuple(map(int, path[-1]))
                target[end] = False
                if len(path) < 2:
                    continue
                trial = deepcopy(p)
                new_state = current
                transferred = {field: 0. for field in stocks}
                excavated = 0.
                bed_grid = current.bed_solid_m3.copy()
                mobile_grid = current.mobile_solid_m3.copy()
                for raw in path[1:]:
                    cell = tuple(map(int, raw))
                    fraction = float(free[cell])
                    amounts = [float(outer[field][cell]) for field in stocks]
                    if cell == end and cutting:
                        depth = max(0., outer_bed[cell]-(sea_level_m-1e-4))
                        amount = min(amounts[0], max_cut_m*fraction*current.spacing_m**2*(1-current.porosity[cell]),
                                     depth*fraction*current.spacing_m**2*(1-current.porosity[cell]))
                        amounts[0] -= amount
                        amounts[1] += amount
                        bed_grid[cell] -= amount
                        mobile_grid[cell] += amount
                        excavated += amount
                    for field, amount in zip(stocks, amounts):
                        transferred[field] += amount
                    trial['node_footprints'].append([*cell, [[*cell, fraction, *amounts]]])
                    owner = next ( (row for row in trial['integrated']['owner_cells'] if tuple(row[:2]) == cell), None)
                    if owner is None:
                        base = float(current.base_bed_m[cell])
                        trial['integrated']['owner_cells'].append([*cell, fraction, *amounts, base, base, 0.])
                    else:
                        owner[2] += fraction
                        for k, amount in enumerate(amounts):
                            owner[3+k] += amount
                    bed = current.base_bed_m[cell]+amounts[0]/(fraction*current.spacing_m**2*(1-current.porosity[cell]))
                    trial['hydraulic_sections']['nodes'].append([*cell, float(bed), section[3], max(float(bed), section[4])])
                new_state = replace(current, bed_solid_m3=bed_grid, mobile_solid_m3=mobile_grid)
                related = ([i for i, r in enumerate(trial['routes']) if tuple(r[-1]) == start]
                           if graph_backend else [index])
                for i in related:
                    trial['routes'][i].extend(path[1:].tolist())
                trial['route_geometry']['nodes'].extend([[int(cell[0]), int(cell[1]), float(pos[0]), float(pos[1])]
                                                         for cell, pos in zip(path[1:], path_xy[1:])])
                trial['route_geometry']['edges'].extend([[*map(int, a), *map(int, b)] for a, b in zip(path, path[1:])])
                metrics = route_metrics(trial, current.spacing_m)
                widths = []
                design = trial.setdefault('fixed_channel_footprint', {}).setdefault('design_width_m', {})
                for node in trial['hydraulic_sections']['nodes']:
                    key = tuple(node[:2])
                    if key in {tuple(map(int, cell)) for cell in path[1:]}:
                        node[3] = min(section[3], free[key]*current.spacing_m**2/node_control_length(trial, key, current.spacing_m, metrics))
                        design[str(key)] = node[3]
                        widths.append(node[3])
                try:
                    trial_pool = ChannelInventory(new_state, trial)
                    for node in trial['hydraulic_sections']['nodes']:
                        key = tuple(node[:2])
                        reference = design.setdefault(str(key), node[3])
                        node[3] = min(reference, trial_pool.area(key) / node_control_length(
                            trial, key, current.spacing_m, metrics))
                    main_widths = trial['integrated']['sections']['section_width_m']
                    for i, node in enumerate(trial['hydraulic_sections']['nodes'][:len(main_widths)]):
                        main_widths[i] = node[3]
                    new_state, trial = trial_pool.commit(new_state, trial)
                    if not branching.mouth_exterior_faces(new_state, trial, sea_level_m=sea_level_m)[index]:
                        continue
                    solution = solve(new_state, trial, sea_level_m, hydraulic_config)
                    stages = {tuple(row[:2]): row[2] for row in solution['nodes']}
                    beds = {tuple(row[:2]): row[2] for row in trial['hydraulic_sections']['nodes']}
                    mouth_q = ({tuple(row[:2]): row[2] for row in solution['mouth_q_m3_s']}.get(end, 0.)
                               if graph_backend else solution['route_q_m3_s'][index])
                    check_cells = path if graph_backend else trial['routes'][index]
                    if mouth_q <= 0 or any(tuple(cell) not in stages or stages[tuple(cell)] <= beds[tuple(cell)] for cell in check_cells):
                        continue
                except HydraulicNumericalError as exc:
                    numerical_failures.append({
                        'route_index': index, 'old_mouth': list(start), 'candidate_mouth': list(end),
                        'path': path.tolist(), 'reason': 'numerical_failure', 'accepted': False,
                        'residual': exc.residual, 'evaluations': exc.evaluations,
                        'message': str(exc), 'sea_level_m': float(sea_level_m)})
                    continue
                except (ValueError, ArithmeticError):
                    continue
                trial['river_hydraulics'] = solution
                trial['actual_shares'] = solution['actual_shares']
                trial['active'] = solution['active']
                trial['segments'] = branching.segment_fluxes(trial)
                if index < len(trial.get('control_references', [])):
                    trial['control_references'][index] = branching._control_reference(new_state, trial['routes'][index])
                change = {'route_index': index, 'old_mouth': list(start), 'new_mouth': list(end),
                          'path': path.tolist(), 'path_xz_m': path_xy.tolist(),
                          'length_m': float(np.linalg.norm(np.diff(path_xy, axis=0), axis=1).sum()),
                          'widths_m': widths, 'outer_to_fine_m3': transferred, 'solid_cut_m3': excavated}
                changes.append(change)
                current, p = branching._record(new_state, trial), trial
                visited.add(end)
                succeeded = True
                break
            if succeeded:
                break
        if not succeeded:
            reason = ('numerical_failure' if len(numerical_failures) > numerical_start
                      else 'no feasible wet, unowned corridor within radius and cut limit')
            failures.append({'route_index': index, 'reason': reason})
    report = {'extended': bool(changes), 'trigger': ('extended' if changes else
              'numerical_failure' if numerical_failures else 'no_feasible_extension' if failures else 'already_open'),
              'extensions': changes, 'failures': failures, 'solid_cut_m3': sum(x['solid_cut_m3'] for x in changes),
              'numerical_failures': numerical_failures,
              'geometry_updates': [], 'sea_level_m': sea_level_m, 'max_cut_m': max_cut_m, 'radius_m': radius_m}
    p['history'].append({'event': 'mouth_extension', **deepcopy(report)})
    return branching._record(current, p), p, report
