"""Prescribed island/channel initial geometry, with an explicit tidal storage proxy."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_propagation, gaussian_filter, map_coordinates
from scipy.spatial import cKDTree

DESIGN_LOW_STAGE_M = -1.5
DESIGN_HIGH_STAGE_M = 1.5
DESIGN_PERIOD_S = 12.42*3600.


def construct_island_channels(bed, marine, allowed, coast_distance,
                              origin, dx, rng, river_direction):
    """Return a lowered tidal platform and smooth paths; never route river flow."""
    shape = bed.shape
    zz, xx = np.indices(shape)
    world_x = origin[0]+xx*dx
    world_z = origin[1]+zz*dx
    relief = np.zeros(shape)
    # Fixed Fourier modes sample absolute coordinates; neither amplitude nor
    # phase depends on the raster extent, tile order, or query count.
    for wavelength, amplitude in ((430., .24), (710., .31), (1030., .36),
                                  (1570., .42), (2330., .34), (3470., .25)):
        angle, phase = rng.uniform(0., 2.*np.pi, 2)
        relief += amplitude*np.sin(2.*np.pi*(world_x*np.cos(angle)
                                            +world_z*np.sin(angle))/wavelength+phase)
    inland_target = np.maximum(.16, .43+.25*relief+.24*(coast_distance/1800.)**1.5)
    coast_mode = (np.sin(world_x/397.+world_z/613.+1.3)
                  + .6*np.sin(world_x/941.-world_z/487.+.8))
    inlet_strength = (.5+.5*np.tanh(1.5*coast_mode))**1.4
    bay_reach = 80.+180.*inlet_strength
    target = inland_target-(.30+.85*inlet_strength)*np.exp(-(coast_distance/bay_reach)**2)
    fade = np.clip((2000.-coast_distance)/500., 0., 1.)
    lowered = bed+fade*np.minimum(target-bed, 0.)
    lowered[~allowed | marine] = bed[~allowed | marine]
    relief_z, relief_x = np.gradient(gaussian_filter(relief, max(1., 100./dx)), dx)
    river_direction = np.asarray(river_direction, float)
    river_direction /= np.linalg.norm(river_direction)
    cross_direction = np.array([-river_direction[1], river_direction[0]])

    def cells(path):
        return np.floor((path-origin)/dx+.5).astype(int)

    def sample(field, point):
        col, row = (point-origin)/dx
        return float(map_coordinates(field, [[row], [col]], order=1, mode='nearest')[0])

    def marine_anchor(point, downstream):
        col, row = cells(point)
        lo_row, hi_row = max(0, row-4), min(shape[0], row+5)
        lo_col, hi_col = max(0, col-4), min(shape[1], col+5)
        rr, cc = np.nonzero(marine[lo_row:hi_row, lo_col:hi_col])
        candidates = origin+np.column_stack([cc+lo_col, rr+lo_row])*dx
        delta = candidates-point
        projection = delta@river_direction
        valid = projection >= -1.e-8 if downstream else projection <= 1.e-8
        if not np.any(valid):
            return None
        candidates = candidates[valid]
        return candidates[np.argmin(np.linalg.norm(candidates-point, axis=1))]

    candidates = np.argwhere(allowed & ~marine & (coast_distance <= 1.5*dx))
    rng.shuffle(candidates)
    roots = []
    for row, col in candidates:
        point = origin+np.array([col, row])*dx
        separation = 510.+280.*(.5+.5*np.sin(point[0]/813.+point[1]/937.))
        if all(np.linalg.norm(point-other) > separation for other in roots):
            roots.append(point)
    roots = np.asarray(roots)
    paths, parents, levels, through = [], [], [], []
    occupied = np.zeros(shape, bool)

    def add(path, parent, level, is_through=False):
        if len(path) < 16:
            return -1
        cc = cells(path)
        occupied[cc[:, 1], cc[:, 0]] = True
        identity = len(paths)
        paths.append(path)
        parents.append(parent)
        levels.append(level)
        through.append(is_through)
        return identity

    def grow(start, heading, length, phase):
        points = [start.copy()]
        heading = heading/max(np.linalg.norm(heading), 1.e-12)
        step = .4*dx
        curvature = 0.
        for station in np.arange(0., length, step):
            point = points[-1]
            normal = np.array([-heading[1], heading[0]])
            gradient = np.array([sample(relief_x, point), sample(relief_z, point)])
            desired = (.0024*np.sin(station/225.+phase)
                       + .0010*np.sin(station/91.+.7*phase)
                       - .32*np.dot(gradient, normal))
            curvature += .055*(desired-curvature)
            turn = np.clip(curvature*step, -.055, .055)
            heading = np.cos(turn)*heading+np.sin(turn)*normal
            # Blind tidal branches are stored mouth-to-head. Their heads
            # advance inland against the inherited river direction.
            lateral = np.clip(np.dot(heading, cross_direction), -.72, .72)
            heading = -np.sqrt(1.-lateral*lateral)*river_direction+lateral*cross_direction
            proposal = point+step*heading
            col, row = cells(proposal)
            if not (1 <= col < shape[1]-1 and 1 <= row < shape[0]-1):
                break
            if not allowed[row, col] or (marine[row, col] and station > 3.*dx):
                break
            if station > 130. and occupied[row, col]:
                points.append(proposal)
                break
            points.append(proposal)
        return np.asarray(points)

    # Coast-to-coast cuts follow the inherited downstream direction. A strictly
    # increasing longitudinal coordinate rules out same-shore horseshoe loops.
    used_roots = set()
    root_order = sorted(range(len(roots)), key=lambda i: np.dot(roots[i], river_direction))
    for index in root_order:
        root = roots[index]
        if index in used_roots:
            continue
        choices = sorted((np.linalg.norm(other-root), j) for j, other in enumerate(roots)
                         if j != index and j not in used_roots)
        for distance, other_id in choices:
            if not 500. < distance < 2600.:
                continue
            other = roots[other_id]
            downstream = np.dot(other-root, river_direction)
            if downstream < .65*distance:
                continue
            t = np.linspace(0., 1., max(20, int(distance/(.4*dx))))
            phase = rng.uniform(0., 2.*np.pi)
            lateral = rng.uniform(30., 90.)*np.sin(2.*np.pi*t+phase)*np.sin(np.pi*t)**2
            path = root[None, :]+t[:, None]*(other-root)+lateral[:, None]*cross_direction
            cc = cells(path)
            if (not np.all(allowed[cc[:, 1], cc[:, 0]])
                    or np.mean(bed[cc[:, 1], cc[:, 0]] > .3) < .3):
                continue
            sea_start = marine_anchor(path[0], False)
            sea_end = marine_anchor(path[-1], True)
            if sea_start is None or sea_end is None:
                continue
            add(np.vstack([sea_start, path, sea_end]), -1, 0, True)
            used_roots.update([index, other_id])
            break
    for index, root in enumerate(roots):
        if index in used_roots:
            continue
        lateral = rng.uniform(-.3, .3)
        heading = -np.sqrt(1.-lateral*lateral)*river_direction+lateral*cross_direction
        path = grow(root, heading, rng.uniform(650., 1700.), rng.uniform(0., 6.3))
        if len(path) < 20 or np.linalg.norm(path[-1]-root) < 180.:
            continue
        sea = marine_anchor(root, True)
        if sea is None:
            continue
        add(np.vstack([sea, path]), -1, 0)

    major_count = len(paths)
    # Use the first non-overlapping major-channel service estimate to set a
    # resolvable bend scale. Final sizing is repeated after tributaries exist.
    _, _, _, _, major_sections = assign_tidal_storage(
        lowered, allowed, marine, paths, parents, np.asarray(through), origin, dx,
        prospective=True)
    for identity in range(major_count):
        path = paths[identity]
        station = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        fraction = station/max(station[-1], 1.e-12)
        width = major_sections[identity, 0]
        phase = rng.uniform(0., 2.*np.pi)
        wave = max(420., 6.5*width)
        displacement = (.9*width*np.sin(2.*np.pi*station/wave+phase)
                        + .25*width*np.sin(2.*np.pi*station/(1.7*wave)+.6*phase))
        displacement *= np.sin(np.pi*fraction)**2
        for amplitude in (1., .65, .35, 0.):
            proposal = path+amplitude*displacement[:, None]*cross_direction
            cc = cells(proposal)
            if np.all(allowed[cc[1:-1, 1], cc[1:-1, 0]]):
                paths[identity] = proposal
                break
    occupied[:] = False
    for path in paths:
        cc = cells(path)
        occupied[cc[:, 1], cc[:, 0]] = True
    # Tributaries occupy the larger unserved pieces, with sparse unequal
    # attachments and tangential departures instead of repeated straight teeth.
    for parent in range(major_count):
        path = paths[parent]
        station = np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        fractions = np.sort(rng.uniform(.24, .83, rng.integers(2, 5)))
        for fraction in fractions:
            index = min(len(path)-3, max(2, np.searchsorted(station, fraction*station[-1])))
            tangent = path[index+2]-path[index-2]
            tangent /= np.linalg.norm(tangent)
            if np.dot(tangent, river_direction) > 0.:
                tangent = -tangent
            side = rng.choice([-1., 1.])
            angle = side*rng.uniform(.25, .55)
            normal = np.array([-tangent[1], tangent[0]])
            heading = np.cos(angle)*tangent+np.sin(angle)*normal
            child = grow(path[index], heading, rng.uniform(320., 950.), rng.uniform(0., 6.3))
            child_id = add(child, parent, 1)
            if child_id < 0 or len(child) < 45 or rng.random() < .35:
                continue
            index = int(len(child)*rng.uniform(.4, .72))
            tangent = child[index+1]-child[index-1]
            tangent /= np.linalg.norm(tangent)
            normal = np.array([-tangent[1], tangent[0]])
            twig = grow(child[index], .8*tangent+.6*side*normal,
                        rng.uniform(180., 480.), rng.uniform(0., 6.3))
            add(twig, child_id, 2)
    return lowered, paths, parents, levels, np.asarray(through, bool)


def connected_tidal_exchange(bed, allowed, marine, paths, origin, dx, *, prospective=False):
    """Geometric exchange depth on the high-stage sea-connected platform."""
    high_water_mask = (bed < DESIGN_HIGH_STAGE_M) & (allowed | marine)
    if prospective and paths:
        # Proposed connected paths will be excavated below low water; permit
        # them to convey the high-stage connection during initial sizing.
        path_cells = np.floor((np.concatenate(paths)-origin)/dx+.5).astype(int)
        high_water_mask[path_cells[:, 1], path_cells[:, 0]] = True
    high_water_connected = binary_propagation(marine, mask=high_water_mask)
    exchange = (np.maximum(DESIGN_HIGH_STAGE_M-bed, 0.)
                -np.maximum(DESIGN_LOW_STAGE_M-bed, 0.))
    exchange[~high_water_connected] = 0.
    return exchange, high_water_connected


def assign_tidal_storage(bed, allowed, marine, paths, parents, through, origin, dx,
                         *, prospective=False):
    """Assign disjoint lowland areas, then accumulate their tidal storage upstream."""
    service = np.full(bed.shape, -1, np.int32)
    if not paths:
        return service, np.empty(0), np.empty(0), np.empty(0), np.empty((0, 5))
    point_ids = np.concatenate([np.full(len(path), i, np.int32) for i, path in enumerate(paths)])
    points = np.concatenate(paths)
    rows, cols = np.nonzero(allowed & ~marine)
    query = origin+np.column_stack([cols, rows])*dx
    distance, nearest = cKDTree(points).query(query, workers=1)
    selected = distance < 1100.
    service[rows[selected], cols[selected]] = point_ids[nearest[selected]]
    valid = service >= 0
    area = np.bincount(service[valid], minlength=len(paths))*dx**2
    exchange, _ = connected_tidal_exchange(bed, allowed, marine, paths, origin, dx,
                                           prospective=prospective)
    own_prism = np.bincount(service[valid], weights=exchange[valid]*dx**2, minlength=len(paths))
    prism = own_prism.copy()
    for identity in reversed(range(len(paths))):
        if parents[identity] >= 0:
            prism[parents[identity]] += prism[identity]
    mouth_prism = prism/np.where(through, 2., 1.)
    # Q_peak = pi P/T; a declared design speed and width:depth ratio produce
    # the sections. These chosen geometric parameters are not field calibration.
    cross_section = np.pi*mouth_prism/(DESIGN_PERIOD_S*.25)
    # The excavated section has a 45%-width flat bottom and linear banks:
    # its actual area is 0.725 * full_width * centre_depth.
    raw_depth = np.sqrt(np.maximum(cross_section, 0.)/(.725*70.))
    raw_width = raw_depth*70.
    depth = np.clip(raw_depth, .45, 3.8)
    width = np.maximum(2.5*dx, cross_section/(.725*np.maximum(depth, .01)))
    width = np.minimum(width, 480.)
    return service, area, own_prism, prism, np.column_stack([width, depth, raw_width, raw_depth, cross_section])
