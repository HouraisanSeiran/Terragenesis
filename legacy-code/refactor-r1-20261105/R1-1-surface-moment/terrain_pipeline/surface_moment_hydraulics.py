"""Small independent nine-moment reference RHS on canonical tile beds.

This unaccelerated research solver evolves conserved mean and dipole moments;
it never advances a hidden one-meter hydraulic mesh. Coordinates are normalized
per coarse cell, with basis [1, xi, zeta].
"""

import numpy as np

from terrain_pipeline.surface_moment_storage import (
    affine_product_integral, clip_tile, invert_velocity_moments,
    invert_water_moments, profile_moments,
)
from terrain_pipeline.single_domain_shallow_water_support import hydrostatic_hll

MODEL = "independent-canonical-wet-polygon-nine-moment-HLL-reference-v1"
GAUSS_NODES, GAUSS_WEIGHTS = np.polynomial.legendre.leggauss(4)


def moments_from_profile(eta, velocity, bed):
    water, _, gram = profile_moments(eta, bed)
    result = np.empty((3, 3))
    result[0] = water
    result[1:] = (gram@np.asarray(velocity)).T
    return result


def profile_from_moments(moments, bed, initial_eta):
    if moments[0, 0] == 0:
        if np.any(moments != 0):
            raise ValueError("dry cell cannot carry water dipoles or momentum")
        return np.array([float(bed.min()), 0., 0.]), np.zeros((3, 2))
    eta, _ = invert_water_moments(moments[0], bed, initial_coefficients=initial_eta)
    _, _, gram = profile_moments(eta, bed)
    velocity = invert_velocity_moments(moments[1:].T, gram)
    return eta, velocity


def uniform_profile_moments(means, bed):
    if means[0] == 0:
        if np.any(means[1:] != 0):
            raise ValueError("dry cell mean momentum invalid")
        return np.zeros((3, 3)), np.array([float(bed.min()), 0., 0.])
    low, high = float(bed.min()), float(bed.max()+means[0])
    for _ in range(65):
        midpoint = .5*(low+high)
        volume = np.maximum(midpoint-bed, 0.).mean()
        if volume < means[0]:
            low = midpoint
        else:
            high = midpoint
    eta = np.array([.5*(low+high), 0., 0.])
    velocity = np.zeros((3, 2))
    velocity[0] = means[1:]/means[0]
    base = moments_from_profile(eta, velocity, bed)
    base[:, 0] = means
    return base, eta


def limit_realizable_moments(target, bed, initial_eta):
    """Contract higher moments toward a realizable profile, preserving all means."""
    if not np.isfinite(target).all() or target[0, 0] < 0:
        raise ValueError("nonfinite or negative mean water moment refused")
    if target[0, 0] == 0:
        if np.any(target[:, 0] != 0):
            raise ValueError("dry mean momentum refused")
        return np.zeros_like(target), np.array([float(bed.min()), 0., 0.]), np.zeros((3, 2)), 0.
    try:
        eta, velocity = profile_from_moments(target, bed, initial_eta)
        return target.copy(), eta, velocity, 1.
    except (ValueError, np.linalg.LinAlgError):
        pass
    base, base_eta = uniform_profile_moments(target[:, 0], bed)
    for iteration in range(1, 31):
        factor = .5**iteration
        candidate = base+factor*(target-base)
        candidate[:, 0] = target[:, 0]
        try:
            eta, velocity = profile_from_moments(candidate, bed, base_eta)
            return candidate, eta, velocity, factor
        except (ValueError, np.linalg.LinAlgError):
            continue
    eta, velocity = profile_from_moments(base, bed, base_eta)
    return base, eta, velocity, 0.


def _volume_flux_integral(eta, velocity, bed, gravity):
    factor = len(bed)
    edges = np.linspace(-.5, .5, factor+1)
    flux = np.zeros((2, 3))
    for row in range(factor):
        for column in range(factor):
            coefficients = eta.copy()
            coefficients[0] -= bed[row, column]
            polygon = clip_tile(coefficients, (edges[column], edges[column+1], edges[row], edges[row+1]))
            for index in range(1, len(polygon)-1):
                triangle = polygon[[0, index, index+1]]
                first, second = triangle[1]-triangle[0], triangle[2]-triangle[0]
                area = abs(first[0]*second[1]-first[1]*second[0])/2
                phi = np.column_stack((np.ones(3), triangle))
                h = phi@coefficients
                uv = phi@velocity
                pressure = .5*gravity*affine_product_integral([h, h], area)
                for axis in (0, 1):
                    flux[axis, 0] += affine_product_integral([h, uv[:, axis]], area)
                    for component in (0, 1):
                        flux[axis, component+1] += affine_product_integral([h, uv[:, axis], uv[:, component]], area)
                    flux[axis, axis+1] += pressure
    return flux


def _line_quadrature(low, high, affine_depths):
    breaks = [low, high]
    for intercept, slope in affine_depths:
        if slope != 0 and low < -intercept/slope < high:
            breaks.append(-intercept/slope)
    breaks = sorted(set(breaks))
    nodes, weights = [], []
    for first, last in zip(breaks[:-1], breaks[1:]):
        nodes.extend(.5*(last+first)+.5*(last-first)*GAUSS_NODES)
        weights.extend(.5*(last-first)*GAUSS_WEIGHTS)
    return np.asarray(nodes), np.asarray(weights)


def _edge_points(axis, normal, tangent):
    return np.column_stack((np.ones(len(tangent)),
        np.full(len(tangent), normal) if axis == 0 else tangent,
        tangent if axis == 0 else np.full(len(tangent), normal)))


def _pressure_edge(eta, axis, normal, low, high, first_bed, second_bed, gravity):
    tangent_axis, normal_axis = (2, 1) if axis == 0 else (1, 2)
    intercept = eta[0]+eta[normal_axis]*normal
    nodes, weights = _line_quadrature(low, high, [(intercept-first_bed, eta[tangent_axis]), (intercept-second_bed, eta[tangent_axis])])
    phi = _edge_points(axis, normal, nodes)
    water_stage = phi@eta
    difference = .5*gravity*(np.maximum(water_stage-second_bed, 0.)**2-np.maximum(water_stage-first_bed, 0.)**2)
    return np.sum(weights[:, None]*difference[:, None]*phi, axis=0)


def _bed_source(eta, bed, spacing, gravity):
    factor = len(bed)
    edges = np.linspace(-.5, .5, factor+1)
    source = np.zeros((3, 3))
    for axis in (0, 1):
        for normal in range(1, factor):
            for tangent in range(factor):
                first_bed = bed[tangent, normal-1] if axis == 0 else bed[normal-1, tangent]
                second_bed = bed[tangent, normal] if axis == 0 else bed[normal, tangent]
                source[axis+1] += _pressure_edge(eta, axis, edges[normal], edges[tangent], edges[tangent+1],
                    first_bed, second_bed, gravity)/spacing
    return source


def nine_moment_rhs(state, eta, velocity, bed, *, spacing, gravity=9.81):
    """Closed-boundary weak RHS; output mean/dipole ledgers remain independent."""
    rows, columns, factor, _ = bed.shape
    count = rows*columns
    if state.shape != (count, 3, 3) or eta.shape != (count, 3) or velocity.shape != (count, 3, 2):
        raise ValueError("nine moment state/profile shape invalid")
    rhs = np.zeros_like(state)
    geometric_source = np.zeros_like(state)
    edges = np.linspace(-.5, .5, factor+1)
    internal_packets, boundary_packets = [], []
    for cell in range(count):
        local_bed = bed.reshape(count, factor, factor)[cell]
        volume_flux = _volume_flux_integral(eta[cell], velocity[cell], local_bed, gravity)
        rhs[cell, :, 1] += volume_flux[0]/spacing
        rhs[cell, :, 2] += volume_flux[1]/spacing
        geometric_source[cell] += _bed_source(eta[cell], local_bed, spacing, gravity)
    flat_bed = bed.reshape(count, factor, factor)
    for axis in (0, 1):
        for row in range(rows):
            for column in range(columns):
                first = row*columns+column
                neighbor_row, neighbor_column = (row, column+1) if axis == 0 else (row+1, column)
                if neighbor_row < rows and neighbor_column < columns:
                    second = neighbor_row*columns+neighbor_column
                    for segment in range(factor):
                        first_bed = flat_bed[first, segment, -1] if axis == 0 else flat_bed[first, -1, segment]
                        second_bed = flat_bed[second, segment, 0] if axis == 0 else flat_bed[second, 0, segment]
                        crest = max(first_bed, second_bed)
                        tangent_axis, normal_axis = (2, 1) if axis == 0 else (1, 2)
                        nodes, weights = _line_quadrature(edges[segment], edges[segment+1],
                            [(eta[first, 0]+.5*eta[first, normal_axis]-crest, eta[first, tangent_axis]),
                             (eta[second, 0]-.5*eta[second, normal_axis]-crest, eta[second, tangent_axis])])
                        phi_first, phi_second = _edge_points(axis, .5, nodes), _edge_points(axis, -.5, nodes)
                        h_first, h_second = np.maximum(phi_first@eta[first]-crest, 0.), np.maximum(phi_second@eta[second]-crest, 0.)
                        state_first = np.column_stack((h_first, h_first[:, None]*(phi_first@velocity[first])))
                        state_second = np.column_stack((h_second, h_second[:, None]*(phi_second@velocity[second])))
                        flux, _, _, _ = hydrostatic_hll(state_first, state_second, np.full(len(nodes), crest), np.full(len(nodes), crest), gravity=gravity, axis=axis)
                        first_flux = np.einsum("n,nc,np->cp", weights, flux, phi_first)/spacing
                        second_flux = np.einsum("n,nc,np->cp", weights, flux, phi_second)/spacing
                        rhs[first] -= first_flux
                        rhs[second] += second_flux
                        geometric_source[first, axis+1] += _pressure_edge(eta[first], axis, .5, edges[segment], edges[segment+1], first_bed, crest, gravity)/spacing
                        geometric_source[second, axis+1] -= _pressure_edge(eta[second], axis, -.5, edges[segment], edges[segment+1], second_bed, crest, gravity)/spacing
                        internal_packets.append((first, second, first_flux, second_flux))
                for sign in (-1., 1.):
                    on_edge = (column == 0 if sign < 0 else column == columns-1) if axis == 0 else (row == 0 if sign < 0 else row == rows-1)
                    if not on_edge:
                        continue
                    for segment in range(factor):
                        crest = flat_bed[first, segment, 0 if sign < 0 else -1] if axis == 0 else flat_bed[first, 0 if sign < 0 else -1, segment]
                        tangent_axis, normal_axis = (2, 1) if axis == 0 else (1, 2)
                        nodes, weights = _line_quadrature(edges[segment], edges[segment+1],
                            [(eta[first, 0]+.5*sign*eta[first, normal_axis]-crest, eta[first, tangent_axis])])
                        phi = _edge_points(axis, .5*sign, nodes)
                        h = np.maximum(phi@eta[first]-crest, 0.)
                        uv = phi@velocity[first]
                        local = np.column_stack((h, h[:, None]*uv))
                        ghost = local.copy()
                        local[:, axis+1] *= sign
                        ghost[:, axis+1] *= -sign
                        flux, _, _, _ = hydrostatic_hll(local, ghost, np.full(len(nodes), crest), np.full(len(nodes), crest), gravity=gravity, axis=axis)
                        flux[:, axis+1] *= sign
                        integrated = np.einsum("n,nc,np->cp", weights, flux, phi)/spacing
                        rhs[first] -= integrated
                        boundary_packets.append((first, integrated))
    rhs += geometric_source
    return rhs, dict(geometric_source=geometric_source, internal_packets=internal_packets, boundary_packets=boundary_packets)
