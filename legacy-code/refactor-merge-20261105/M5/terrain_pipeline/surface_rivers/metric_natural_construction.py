"""Seeded, flow-aligned construction geometry, not a delta growth simulator."""
from __future__ import annotations

import hashlib
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial import cKDTree


def derived_seed(world_seed, purpose):
    return int.from_bytes(hashlib.sha256(f'{int(world_seed)}:{purpose}'.encode('ascii')).digest()[:4], 'little')


def _station(path):
    return np.r_[0., np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]


def _sample(path, stations):
    s = _station(path)
    return np.column_stack([np.interp(stations, s, path[:, axis]) for axis in range(2)])


def flowing_path(start, direction, length, slope, rng, count=1201, *, bend_amplitude=310., initial_lateral_slope=0.):
    """Monotone downstream progression with a prescribed initial lateral slope."""
    direction = np.asarray(direction, float)
    direction = direction/np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    distance = np.linspace(0., length, count)
    knots = np.r_[0., np.cumsum(rng.uniform(.75, 1.3, 7))]
    knots *= length/knots[-1]
    offsets = rng.uniform(-bend_amplitude, bend_amplitude, len(knots))
    offsets[0] = 0.
    bends = CubicSpline(knots, offsets, bc_type=((1, 0.), (1, 0.)))(distance)
    turn_length = rng.uniform(650., 1000.)
    ramp = np.clip(distance/900., 0., 1.)
    ramp = ramp*ramp*(3.-2.*ramp)
    cross = (slope*(distance-turn_length*(1.-np.exp(-distance/turn_length)))
             + bends*ramp + initial_lateral_slope*distance*np.exp(-distance/600.))
    return start+distance[:, None]*direction+cross[:, None]*normal


def natural_distributary_geometry(trunk, world_seed):
    rng = np.random.default_rng(derived_seed(world_seed, 'delta/branch-geometry/v1'))
    trunk = np.asarray(trunk, float)
    direction = trunk[-1]-trunk[-8]
    extension = flowing_path(trunk[-1], direction, 1050., rng.uniform(-.03, .03), rng, len(trunk), bend_amplitude=8.)
    extended = np.vstack([trunk, extension[1:]])
    extended = _sample(extended, np.linspace(0., _station(extended)[-1], len(trunk)))
    s = _station(extended)
    # Outside channels leave first; the inner pair divide farther downstream.
    fractions = np.array([.32, .76, 1., .22])+rng.uniform(-.025, .025, 4)
    fractions[2] = 1.
    slopes = np.array([-.63, -.19, .22, .71])*rng.uniform(.92, 1.08, 4)
    paths = []
    direction = direction/np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    anchor = extended[0]
    trunk_u, trunk_v = (extended-anchor)@direction, (extended-anchor)@normal
    baseline = CubicSpline(trunk_u, trunk_v, bc_type='natural')
    phase = rng.uniform(0., 2.*np.pi)
    def centerline(u):
        beyond = np.maximum(u-trunk_u[-1], 0.)
        taper = 1.-np.exp(-(beyond/600.)**2)
        bend = 210.*np.sin(beyond/620.+phase)*taper
        return baseline(np.minimum(u, trunk_u[-1]))+baseline(trunk_u[-1], 1)*beyond+bend
    for split, slope in zip(fractions*s[-1], slopes):
        start = _sample(extended, [split])[0]
        distance = np.linspace(0., rng.uniform(6500., 7000.), 1201)
        u = (start-anchor)@direction+distance
        separation = slope*distance**2/(distance+800.)
        # Perturb a bounded fraction of the separating corridor, preserving order.
        knots = np.linspace(0., distance[-1], 9)
        factors = CubicSpline(knots, rng.uniform(-.12, .12, len(knots)), bc_type='natural')(distance)
        v = centerline(u)+separation*(1.+factors)
        branch = anchor+u[:, None]*direction+v[:, None]*normal
        branch[0] = start
        paths.append(branch)
    return extended, np.asarray(paths), fractions*s[-1]


def natural_secondary(parent, marine, origin, spacing, world_seed):
    rng = np.random.default_rng(derived_seed(world_seed, 'delta/secondary-geometry/v1'))
    s = _station(parent)
    cells = np.floor((parent-origin)/spacing+.5).astype(int)
    inside = ((cells[:, 0] >= 0) & (cells[:, 0] < marine.shape[1]) &
              (cells[:, 1] >= 0) & (cells[:, 1] < marine.shape[0]))
    hits = np.flatnonzero(inside & marine[cells[:, 1].clip(0, marine.shape[0]-1), cells[:, 0].clip(0, marine.shape[1]-1)])
    if not len(hits):
        return None, {'reason': 'no_open_marine_entry'}
    split_s = float(s[hits[0]]*rng.uniform(.38, .47))
    start = _sample(parent, [split_s])[0]
    direction = parent[20]-parent[0]
    direction /= np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    pu, pv = (parent-parent[0])@direction, (parent-parent[0])@normal
    baseline = CubicSpline(pu, pv, bc_type='natural')
    distance = np.linspace(0., min(5300., pu[-1]-(start-parent[0])@direction), len(parent))
    u = (start-parent[0])@direction+distance
    clearance = .5*(170.+102.)+2.*spacing
    landward_run = max(float(s[hits[0]])-split_s, spacing)
    separation_slope = 2.*clearance*(landward_run+650.)/landward_run**2
    v = baseline(u)-separation_slope*distance**2/(distance+650.)
    child = parent[0]+u[:, None]*direction+v[:, None]*normal
    child[0] = start
    return child, {'reason': 'selected', 'parent_split_station_m': split_s,
                   'parent_first_marine_station_m': float(s[hits[0]]),
                   'required_distinct_channel_clearance_m': clearance}


def channel_organized_relief(prebed, fan, paths, origin, spacing, world_seed):
    """Curved interdistributary lobes constrained by adjacent channel corridors."""
    rng = np.random.default_rng(derived_seed(world_seed, 'delta/island-relief/v1'))
    zz, xx = np.indices(prebed.shape)
    points = np.stack([origin[0]+xx*spacing, origin[1]+zz*spacing], axis=-1)
    relief = np.zeros_like(prebed)
    bodies = []
    direction, normal = fan['direction_xz'], fan['normal_xz']
    anchor = fan['apex_xz_m']
    local = points-anchor
    along, across = local@direction, local@normal
    coordinates = [((path-anchor)@direction, (path-anchor)@normal) for path in paths]
    coordinates.sort(key=lambda item: item[1][-1])
    for index, (left, right) in enumerate(zip(coordinates[:-1], coordinates[1:])):
        start = max(left[0][0], right[0][0])+rng.uniform(180., 330.)
        end = min(left[0][-1], right[0][-1], rng.uniform(4200., 5400.))
        t = np.clip((along-start)/(end-start), 0., 1.)
        low = np.interp(along, left[0], left[1])
        high = np.interp(along, right[0], right[1])
        # Bodies widen only where the bounding channels actually separate.
        center_fraction = rng.uniform(.42, .58)
        center = low+(high-low)*center_fraction
        longitudinal = np.maximum(4.*t*(1.-t), 0.)
        half_width = np.maximum((high-low)*rng.uniform(.30, .40)-70., 1.)
        half_width *= np.sqrt(longitudinal)
        offset = across-center
        asymmetry = 1.+.16*np.tanh(offset/200.)*(2.*t-1.)
        transverse = np.maximum(1.-(offset/(np.maximum(half_width, 1.)*asymmetry))**2, 0.)
        height = rng.uniform(2.2, 3.5)
        body = longitudinal*transverse**2
        # A broader, low apron grades the island edge into surrounding shallows.
        apron = longitudinal*np.maximum(1.-(offset/np.maximum(half_width*1.65, 1.))**2, 0.)**2
        relief += height*body+.55*apron
        bodies.append(dict(sorted_corridor_positions=[index, index+1],
            start_downstream_m=start, end_downstream_m=end, center_fraction=center_fraction,
            height_m=height, boundary='interpolated adjacent channel centerlines with channel clearance and asymmetric shallow apron'))
    forward = fan['u_m']-fan['parameters']['apex_u_m']
    def smooth(v):
        v = np.clip(v, 0., 1.)
        return v*v*(3.-2.*v)
    envelope = fan['weight']*smooth((forward-650.)/1000.)*(1.-smooth((np.abs(prebed)-3.)/5.))
    return relief*envelope, bodies


def construct_mouth_transitions(prebed, marine, candidates, paths, junctions, widths,
                                incoming_bed, origin, spacing, transition_length_m=650.):
    """Explicit initial nearshore excavation grading channel beds into the sea."""
    bed = prebed.copy()
    zz, xx = np.indices(bed.shape)
    points = np.stack([origin[0]+xx*spacing, origin[1]+zz*spacing], axis=-1)
    support = np.zeros_like(marine)
    for candidate, path, junction, width in zip(candidates, paths, junctions, widths):
        station = _station(candidate)
        segments = np.diff(candidate, axis=0)
        fraction = np.clip(np.sum((path[-1]-candidate[:-1])*segments, axis=1)/np.sum(segments*segments, axis=1), 0., 1.)
        projected = candidate[:-1]+fraction[:, None]*segments
        index = np.argmin(np.linalg.norm(projected-path[-1], axis=1))
        coast_s = float(station[index]+fraction[index]*np.linalg.norm(segments[index]))
        samples = np.linspace(max(0., coast_s-2.*spacing), min(station[-1], coast_s+transition_length_m), 301)
        line = _sample(candidate, samples)
        distance, nearest = cKDTree(line).query(points.reshape(-1, 2), workers=1)
        distance, nearest = distance.reshape(bed.shape), nearest.reshape(bed.shape)
        tangent_start, tangent_end = line[1]-line[0], line[-1]-line[-2]
        active = (marine & ((points-line[0])@tangent_start >= 0.) &
                  ((points-line[-1])@tangent_end <= 0.))
        lateral = np.clip((1.-distance/(.5*width))/.4, 0., 1.)
        offshore = np.clip((samples[nearest]-coast_s)/transition_length_m, 0., 1.)
        blend = offshore*offshore*(3.-2.*offshore)
        coast_bed = float(incoming_bed)-.00038*(junction+_station(path)[-1])
        target = coast_bed*(1.-blend)+prebed*blend
        proposal = bed+lateral*active*(np.minimum(target, bed)-bed)
        support |= proposal < bed
        bed = proposal
    return bed, support
