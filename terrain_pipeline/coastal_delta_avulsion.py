"""Activate terrain-derived candidate distributaries under measured river head."""
from copy import deepcopy
from dataclasses import replace

import numpy as np

from . import coastal_delta_branching as branching
from . import coastal_delta_hydraulics as hydraulics


def activate_candidate(state, progress, *, hydraulic_config, sea_level_m=0.,
                       min_rise_m=.1, max_cut_m=.5, mouth_radius_m=4000.):
    """Trial one candidate atomically; the first call records initial sections."""
    if 'node_footprints' in progress:
        from .coastal_delta_multicell_avulsion import activate_multicell_candidate
        return activate_multicell_candidate(state, progress, hydraulic_config=hydraulic_config,
            sea_level_m=sea_level_m, min_rise_m=min_rise_m, max_cut_m=max_cut_m, mouth_radius_m=mouth_radius_m)
    branching._validate(state, progress)
    if not np.isfinite([sea_level_m, min_rise_m, max_cut_m, mouth_radius_m]).all() or min_rise_m <= 0 or max_cut_m < 0 or mouth_radius_m <= 0:
        raise ValueError('invalid avulsion settings')
    if 'avulsion_baseline_sections' not in progress:
        p = deepcopy(progress)
        p['avulsion_baseline_sections'] = deepcopy(p['hydraulic_sections']['nodes'])
        return branching._record(state, p), p, {'activated': False, 'trigger': 'baseline_recorded'}

    original_state, original_progress = state, progress
    parent_extension = {'extended': False, 'trigger': 'already_open', 'geometry_updates': [],
                        'solid_cut_m3': 0., 'extensions': []}
    if any(not face for face in branching.mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)):
        state, progress, parent_extension = extend_mouths(
            state, progress, hydraulic_config=hydraulic_config, sea_level_m=sea_level_m,
            radius_m=mouth_radius_m, max_cut_m=max_cut_m)
        if not parent_extension['extended']:
            return original_state, original_progress, {'activated': False, 'trigger': 'no_eligible_candidate',
                                                        'reason': 'parent_mouth_unreachable'}

    baseline = {tuple(row[:2]): row for row in progress['avulsion_baseline_sections']}
    sections = {tuple(row[:2]): row for row in progress['hydraulic_sections']['nodes']}
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    occupied = set().union(*map(set, routes))
    try:
        original = hydraulics.solve(state, progress, sea_level_m, hydraulic_config)
    except (ValueError, ArithmeticError):
        return original_state, original_progress, {'activated': False, 'trigger': 'hydraulic_failure'}
    stages = {tuple(n[:2]): n[2] for n in original['nodes']}
    candidates = progress['integrated']['candidate_routes']
    for candidate_index, candidate in enumerate(candidates):
        path = [tuple(c) for c in candidate]
        if len(path) < 2 or len(set(path)) != len(path) or any(
                ('route_geometry' not in progress and abs(a[0]-b[0]) + abs(a[1]-b[1]) != 1) for a, b in zip(path, path[1:])):
            continue
        if any(c in occupied for c in path[1:]):
            continue
        if any(len(c) != 2 or not (0 <= c[0] < state.bed_m.shape[0] and
               0 <= c[1] < state.bed_m.shape[1]) or not state.valid_mask[c] for c in path):
            continue
        parents = [(i, route.index(path[0])) for i, route in enumerate(routes) if path[0] in route]
        for parent, fork_index in parents:
            route = routes[parent]
            if fork_index >= len(route)-1 or path[0] not in stages:
                continue
            rises = [sections[c][2]-baseline[c][2] for c in route[fork_index+1:]
                     if c in sections and c in baseline]
            rise = max(rises, default=0.)
            if rise + 1e-10 < min_rise_m:
                continue
            fork_stage = float(stages[path[0]])
            fork_section = sections[path[0]]
            fork_depth = max(fork_stage-fork_section[2], 0.)
            target_depth = min(fork_depth * .25, max_cut_m)
            stock = state.bed_solid_m3.copy()
            mobile = state.mobile_solid_m3.copy()
            p = deepcopy(progress)
            width = min(float(fork_section[3]) * .5, state.spacing_m)
            excavation = []
            for cell in path[1:]:
                area = state.spacing_m**2 * (1-state.porosity[cell])
                desired = max(float(state.bed_m[cell]) - (fork_stage-target_depth), 0.)
                amount = min(float(stock[cell]), min(max_cut_m, desired)*area)
                stock[cell] -= amount
                mobile[cell] += amount
                if amount > 0:
                    excavation.append([*cell, float(amount)])
            trial = replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile)
            if any(trial.bed_m[c] >= fork_stage for c in path[1:]):
                continue
            for z, x in path[1:]:
                bed = float(trial.bed_m[z, x])
                neighbors = [float(trial.bed_m[r, c]) for r, c in
                             ((z-1,x),(z+1,x),(z,x-1),(z,x+1))
                             if 0 <= r < stock.shape[0] and 0 <= c < stock.shape[1]
                             and state.valid_mask[r, c]]
                bank = max(bed, max(neighbors, default=bed))
                p['hydraulic_sections']['nodes'].append([z, x, bed, width, bank])
            p['routes'].append([list(c) for c in route[:fork_index+1]+path[1:]])
            if 'control_references' in p:
                p['control_references'].append(branching._control_reference(trial, p['routes'][-1]))
            share = p['shares'][parent] * .5
            p['shares'][parent] -= share
            p['shares'].append(share)
            # Bind the tentative progress before invoking the independent mouth
            # helper. Its record and every geometry change remain local until
            # the final candidate solution is accepted.
            for row in p['integrated'].get('owner_cells', []):
                r, c, fraction = row[:3]
                for index, field in enumerate(('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')):
                    before = float(getattr(state, field)[r, c])
                    after = float(getattr(trial, field)[r, c])
                    row[3+index] = min(after, max(0., row[3+index] + (after-before)*fraction))
            trial = branching._record(trial, p)
            trial, p, mouth_extension = extend_mouths(
                trial, p, hydraulic_config=hydraulic_config, sea_level_m=sea_level_m,
                radius_m=mouth_radius_m, max_cut_m=max_cut_m)
            if mouth_extension['trigger'] not in ('extended', 'already_open'):
                continue
            faces = branching.mouth_exterior_faces(trial, p, sea_level_m=sea_level_m)
            if (not all(faces) or any(set(map(tuple, a)) & set(map(tuple, b))
                                      for i, a in enumerate(faces) for b in faces[i+1:])):
                continue
            try:
                solution = hydraulics.solve(trial, p, sea_level_m, hydraulic_config)
            except (ValueError, ArithmeticError):
                continue
            q = float(solution['route_q_m3_s'][-1])
            trial_stages = {tuple(n[:2]): n[2] for n in solution['nodes']}
            trial_sections = {tuple(n[:2]): n[2] for n in p['hydraulic_sections']['nodes']}
            if q <= 0 or any(cell not in trial_stages or
                             trial_sections[cell] >= trial_stages[cell]
                             for cell in map(tuple, p['routes'][-1])):
                continue
            p['river_hydraulics'] = solution
            p['actual_shares'] = solution['actual_shares']
            p['active'] = solution['active']
            p['segments'] = branching.segment_fluxes(p)
            p['widths_m'] = [branching._width(p['discharge_m3_s'] * s, 0., 0.) if s else 0.
                             for s in p['actual_shares']]
            candidate_cut = float(sum(row[2] for row in excavation))
            mouth_cut = parent_extension.get('solid_cut_m3', 0.) + mouth_extension.get('solid_cut_m3', 0.)
            report = {'activated': True, 'trigger': 'activated', 'candidate_index': candidate_index,
                      'parent': parent, 'fork_index': fork_index, 'fork': list(path[0]),
                      'rise_m': float(rise), 'fork_stage_m': fork_stage, 'actual_Q_m3_s': q,
                      'solid_cut_m3': candidate_cut + mouth_cut, 'candidate_solid_cut_m3': candidate_cut,
                      'mouth_solid_cut_m3': mouth_cut, 'parent_mouth_extension': parent_extension,
                      'mouth_extension': mouth_extension, 'excavation': excavation}
            p['history'].append({'event': 'candidate_avulsion', **report})
            return branching._record(trial, p), p, report
    return original_state, original_progress, {'activated': False, 'trigger': 'no_eligible_candidate'}




def extend_mouths(state, progress, *, hydraulic_config, sea_level_m=0.,
                  radius_m=2000., max_cut_m=.5):
    """Extend closed mouths across local terrain, committing only a wet solution.

    Distances are in metres and cut depths are bulk sediment thicknesses. The
    upstream stage limit bounds the search; the section solver determines the
    actual water surface and discharge before any changes are returned.
    """
    if 'node_footprints' in progress:
        from .coastal_delta_mouth_extension import extend_multicell_mouths
        return extend_multicell_mouths(state, progress, hydraulic_config=hydraulic_config,
                                       sea_level_m=sea_level_m, radius_m=radius_m, max_cut_m=max_cut_m)
    from scipy import ndimage
    from .coastal_delta_routes import valley_path, irregular_valley_path

    branching._validate(state, progress)
    if (not np.isfinite([sea_level_m, radius_m, max_cut_m]).all() or
            radius_m <= 0 or max_cut_m < 0):
        raise ValueError('invalid mouth extension settings')
    faces = branching.mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)
    closed = [i for i, face in enumerate(faces) if not face]
    if not closed:
        return state, progress, {'extended': False, 'trigger': 'already_open', 'geometry_updates': []}
    head = float(hydraulic_config.upstream_stage_limit_m)
    if not np.isfinite(head):
        raise ValueError('invalid hydraulic boundary')

    def search(current, p, remaining, changes, geometry):
        if not remaining:
            try:
                solution = hydraulics.solve(current, p, sea_level_m, hydraulic_config)
            except (ValueError, ArithmeticError):
                return None
            stages = {tuple(n[:2]): float(n[2]) for n in solution['nodes']}
            sections = {tuple(n[:2]): float(n[2]) for n in p['hydraulic_sections']['nodes']}
            for index, route in enumerate(p['routes']):
                if solution['route_q_m3_s'][index] > 0 and any(
                        cell not in stages or sections[cell] >= stages[cell]
                        for cell in map(tuple, route)):
                    return None
            for change in changes:
                index = change['route_index']
                if solution['route_q_m3_s'][index] <= 0 or any(
                        cell not in stages or sections[cell] >= stages[cell]
                        for cell in map(tuple, p['routes'][index])):
                    return None
                change['actual_Q_m3_s'] = float(solution['route_q_m3_s'][index])
            return current, p, changes, geometry, solution

        index = remaining[0]
        routes = [[tuple(cell) for cell in route] for route in p['routes']]
        start = routes[index][-1]
        sections = {tuple(row[:2]): row for row in p['hydraulic_sections']['nodes']}
        if start not in sections:
            return None
        exterior = branching._exterior_ocean(current, routes, sea_level_m)
        neighbor = ndimage.binary_dilation(exterior, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
        rows, cols = np.ogrid[:exterior.shape[0], :exterior.shape[1]]
        local = ((rows-start[0])**2 + (cols-start[1])**2) * current.spacing_m**2 <= radius_m**2
        forbidden = np.zeros(exterior.shape, dtype=bool)
        for route in routes:
            for cell in route:
                forbidden[cell] = True
        if 'route_geometry' in p:
            for row in p['route_geometry']['nodes']:
                if tuple(row[:2]) != start:
                    forbidden[tuple(row[:2])] = True
        targets = current.valid_mask & local & neighbor & ~forbidden
        area = current.spacing_m**2 * (1-current.porosity)
        available = np.minimum(max_cut_m, current.bed_solid_m3 / area)
        # Try an unmodified corridor first. A second search permits only the
        # sediment actually available in each cell to lower a blocking ridge.
        for cutting in (False, True) if max_cut_m > 0 else (False,):
            lower = available if cutting else np.zeros_like(available)
            search_bed = current.bed_m - lower
            if 'route_geometry' in p:
                search_bed[start] = sections[start][2]
            remaining_targets = targets.copy()
            while remaining_targets.any():
                try:
                    if 'route_geometry' in p:
                        geometry_info = p['route_geometry']
                        start_xy = next(row[2:] for row in geometry_info['nodes'] if tuple(row[:2]) == start)
                        irregular_forbidden = forbidden.copy()
                        irregular_forbidden[start] = False
                        path, path_xy = irregular_valley_path(
                            search_bed, current.valid_mask & local, start, None, head, current.spacing_m,
                            origin_xz_m=current.origin_xz_m, world_seed=geometry_info['seed'],
                            forbidden=irregular_forbidden, target_mask=remaining_targets, start_xz_m=start_xy)
                    else:
                        path = valley_path(search_bed, current.valid_mask & local, start,
                                           remaining_targets, head, current.spacing_m, forbidden)
                except ValueError:
                    break
                endpoint = tuple(map(int, path[-1]))
                remaining_targets[endpoint] = False
                stock = current.bed_solid_m3.copy()
                mobile = current.mobile_solid_m3.copy()
                excavation = []
                # Reserve a small head margin based on the actual mouth width
                # and imposed boundary; never manufacture sediment or rock cuts.
                margin = min(.25, max((head-float(sections[start][2]))*.1, 1e-6))
                target_bed = head - margin
                cut_cells = [tuple(map(int, raw)) for raw in path[1:]]
                if 'route_geometry' in p:
                    from terrain_pipeline.channel_geometry import _segment_owner_samples
                    samples = _segment_owner_samples(path_xy, np.asarray(current.origin_xz_m), current.spacing_m)
                    owners = np.floor((samples-np.asarray(current.origin_xz_m))/current.spacing_m+.5).astype(int)
                    cut_cells = list(dict.fromkeys([*cut_cells, *(tuple(owner[::-1]) for owner in owners
                                                                    if tuple(owner[::-1]) != start)]))
                for cell in cut_cells:
                    amount = min(float(stock[cell]), float(lower[cell]*area[cell]),
                                 max(float(current.bed_m[cell])-target_bed, 0.)*area[cell])
                    stock[cell] -= amount
                    mobile[cell] += amount
                    if amount > 0:
                        excavation.append([*cell, float(amount)])
                trial = replace(current, bed_solid_m3=stock, mobile_solid_m3=mobile)
                trial_p = deepcopy(p)
                new_rows = []
                width = float(sections[start][3])
                for raw in path[1:]:
                    z, x = map(int, raw)
                    bed = float(trial.bed_m[z, x])
                    neighbors = [float(trial.bed_m[r, c]) for r, c in
                                 ((z-1,x), (z+1,x), (z,x-1), (z,x+1))
                                 if 0 <= r < stock.shape[0] and 0 <= c < stock.shape[1]
                                 and trial.valid_mask[r, c]]
                    row = [z, x, bed, width, max(bed, max(neighbors, default=bed))]
                    trial_p['hydraulic_sections']['nodes'].append(row)
                    new_rows.append(row)
                trial_p['routes'][index].extend(path[1:].tolist())
                if 'route_geometry' in trial_p:
                    saved = trial_p['route_geometry']
                    saved['nodes'].extend([[int(cell[0]), int(cell[1]), float(xy[0]), float(xy[1])]
                                           for cell, xy in zip(path[1:], path_xy[1:])])
                    saved['edges'].extend([[*map(int, a), *map(int, b)]
                                           for a, b in zip(path, path[1:])])
                new_faces = branching.mouth_exterior_faces(trial, trial_p, sea_level_m=sea_level_m)
                if not new_faces[index] or any(
                        set(map(tuple, new_faces[index])) & set(map(tuple, face))
                        for j, face in enumerate(new_faces) if j != index):
                    continue
                change = {'route_index': index, 'old_mouth': list(start),
                          'new_mouth': list(endpoint), 'path': path.tolist(),
                          'solid_cut_m3': float(sum(item[2] for item in excavation)),
                          'excavation': excavation}
                result = search(trial, trial_p, remaining[1:], changes + [change], geometry + new_rows)
                if result is not None:
                    return result
        return None

    result = search(state, deepcopy(progress), closed, [], [])
    if result is None:
        return state, progress, {'extended': False, 'trigger': 'no_feasible_extension', 'geometry_updates': []}
    updated, p, changes, geometry, solution = result
    for row in p.get('integrated', {}).get('owner_cells', []):
        r, c, fraction = row[:3]
        for index, field in enumerate(('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')):
            before = float(getattr(state, field)[r, c])
            after = float(getattr(updated, field)[r, c])
            row[3+index] = min(after, max(0., row[3+index] + (after-before)*fraction))
    if 'control_references' in p:
        for change in changes:
            index = change['route_index']
            p['control_references'][index] = branching._control_reference(updated, p['routes'][index])
    p['river_hydraulics'] = solution
    p['actual_shares'] = solution['actual_shares']
    p['active'] = solution['active']
    p['segments'] = branching.segment_fluxes(p)
    p['widths_m'] = [branching._width(p['discharge_m3_s'] * s, 0., 0.) if s else 0.
                     for s in p['actual_shares']]
    report = {'extended': True, 'trigger': 'extended', 'extensions': changes,
              'solid_cut_m3': float(sum(c['solid_cut_m3'] for c in changes)),
              'geometry_updates': geometry}
    p['history'].append({'event': 'mouth_extension', **deepcopy(report)})
    return branching._record(updated, p), p, report




def propose_candidates(state, progress, *, hydraulic_config, sea_level_m=0., max_candidates=2,
                       max_fork_attempts=12):
    """Refresh candidate paths under current solved fork stages without changing stocks.

    Existing unactivated candidates retain their coordinates. Activated or now
    occupied candidates are removed. At most max_fork_attempts paths are tried;
    the report includes the actual attempt_count. Returns state and progress.
    """
    from scipy import ndimage
    from .coastal_delta_routes import irregular_valley_path, build_route_geometry
    from terrain_pipeline.drainage import grid_mesh as grid_mesh

    branching._validate(state, progress)
    if 'route_geometry' not in progress:
        raise ValueError('candidate refresh requires irregular geometry')
    if (not isinstance(max_candidates, int) or max_candidates < 0
            or not isinstance(max_fork_attempts, int) or max_fork_attempts < 0
            or not np.isfinite(sea_level_m)):
        raise ValueError('invalid candidate settings')
    solution = hydraulics.solve(state, progress, sea_level_m, hydraulic_config)
    if not any(q > 0 for q in solution['route_q_m3_s']):
        raise ValueError('parent route has no positive discharge')
    stages = {tuple(row[:2]): float(row[2]) for row in solution['nodes']}
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    occupied = set().union(*map(set, routes))
    geometry = progress['route_geometry']
    coordinates = {tuple(row[:2]): np.asarray(row[2:], float) for row in geometry['nodes']}
    selected = []
    used = set(occupied)
    for raw in progress['integrated']['candidate_routes']:
        path = [tuple(c) for c in raw]
        if (len(path) >= 2 and path[0] in stages and path[0] in occupied
                and not any(c in used for c in path[1:])
                and all(c in coordinates for c in path)
                and all(state.valid_mask[c] and state.bed_m[c] < stages[path[0]] for c in path[1:])):
            selected.append(path)
            used.update(path[1:])
    exterior = branching._exterior_ocean(state, routes, sea_level_m)
    adjacent = ndimage.binary_dilation(exterior, structure=np.array([[0,1,0],[1,1,1],[0,1,0]]))
    # Existing geometry, including retired candidates, is reserved so that no
    # account can silently acquire a different mesh coordinate on a refresh.
    reserved = set(coordinates)
    forks = list(dict.fromkeys(c for route in routes for c in route[1:-1] if c in stages))
    successors = {}
    for route in routes:
        for a, b in zip(route, route[1:]):
            successors.setdefault(a, set()).add(b)
    existing_forks = [cell for cell, following in successors.items() if len(following) > 1]
    existing_forks.extend(path[0] for path in selected)
    forks = [fork for fork in forks if all(max(abs(fork[0]-other[0]),
                                                abs(fork[1]-other[1])) > 2 for other in existing_forks)]
    if len(forks) > max_fork_attempts and max_fork_attempts:
        indices = np.linspace(0, len(forks)-1, max_fork_attempts, dtype=int)
        forks = [forks[i] for i in indices]
    section_beds = {tuple(row[:2]): float(row[2]) for row in progress['hydraulic_sections']['nodes']}
    mesh = None
    attempt_count = 0
    for fork in forks:
        if len(selected) >= max_candidates or attempt_count >= max_fork_attempts:
            break
        if any(max(abs(fork[0]-path[0][0]), abs(fork[1]-path[0][1])) <= 2 for path in selected):
            continue
        forbidden = np.zeros(state.bed_m.shape, bool)
        for cell in used | reserved:
            forbidden[cell] = True
        forbidden[fork] = False
        targets = adjacent & state.valid_mask & ~forbidden
        for path in selected:
            for r, c in path[-1:]:
                targets[max(0,r-1):r+2, max(0,c-1):c+2] = False
        search_bed = state.bed_m.copy()
        search_bed[fork] = section_beds[fork]
        if mesh is None:
            mesh = grid_mesh(state.bed_m.shape, x0_m=state.origin_xz_m[0],
                             z0_m=state.origin_xz_m[1], dx_m=state.spacing_m,
                             world_seed=geometry['seed'])
        attempt_count += 1
        try:
            cells, xy = irregular_valley_path(search_bed, state.valid_mask, fork, None,
                stages[fork], state.spacing_m, origin_xz_m=state.origin_xz_m,
                world_seed=geometry['seed'], forbidden=forbidden, target_mask=targets,
                start_xz_m=coordinates[fork], mesh=mesh)
        except ValueError:
            continue
        path = [tuple(map(int, c)) for c in cells]
        if len(path) < 2:
            continue
        # Mouth faces must remain distinct when all proposed paths are present.
        hypothetical = deepcopy(progress)
        hypothetical['routes'] = [[list(c) for c in route] for route in routes]
        for candidate in [*selected, path]:
            parent = next(route for route in routes if candidate[0] in route)
            prefix = parent[:parent.index(candidate[0])+1]
            hypothetical['routes'].append([list(c) for c in prefix + candidate[1:]])
        faces = branching.mouth_exterior_faces(state, hypothetical, sea_level_m=sea_level_m)
        if not all(faces) or any(set(map(tuple, a)) & set(map(tuple, b))
                                 for i, a in enumerate(faces) for b in faces[i+1:]):
            continue
        # Validate cross-account edges before registering any geometry.
        addition = build_route_geometry(state, [cells], [xy], geometry['algorithm'], geometry['seed'])
        for row in addition['nodes']:
            coordinates.setdefault(tuple(row[:2]), np.asarray(row[2:], float))
        selected.append(path)
        used.update(path[1:])
    p = deepcopy(progress)
    p['integrated']['candidate_routes'] = [[list(c) for c in path] for path in selected]
    existing_nodes = {tuple(row[:2]) for row in p['route_geometry']['nodes']}
    p['route_geometry']['nodes'].extend([[*c, *map(float, xy)] for c, xy in sorted(coordinates.items()) if c not in existing_nodes])
    edges = {tuple(row) for row in p['route_geometry']['edges']}
    edges.update((*a, *b) for path in selected for a, b in zip(path, path[1:]))
    p['route_geometry']['edges'] = [list(edge) for edge in sorted(edges)]
    return branching._record(state, p), p, {'candidate_count': len(selected), 'attempt_count': attempt_count,
                                           'candidates': p['integrated']['candidate_routes']}
