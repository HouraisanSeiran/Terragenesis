"""Consolidated audit_shallow_water implementations; numeric expressions preserved."""
from __future__ import annotations
import numpy as _i0_np
import numpy as _i1_np
CATEGORY = 'B'

def positive_affine_rectangle(depth_coefficients, bounds, velocity_coefficients=None):
    """Integrate h=max(a+b*x+c*z,0), and optional h*u, using clipped triangles."""
    xmin, xmax, zmin, zmax = bounds
    polygon = [_i0_np.array([xmin, zmin]), _i0_np.array([xmax, zmin]), _i0_np.array([xmax, zmax]), _i0_np.array([xmin, zmax])]
    coefficients = _i0_np.asarray(depth_coefficients)

    def value(point):
        return coefficients[0] + _i0_np.dot(coefficients[1:], point)
    clipped = []
    previous = polygon[-1]
    previous_value = value(previous)
    for current in polygon:
        current_value = value(current)
        if (current_value >= 0) != (previous_value >= 0):
            fraction = previous_value / (previous_value - current_value)
            clipped.append(previous + fraction * (current - previous))
        if current_value >= 0:
            clipped.append(current)
        previous, previous_value = (current, current_value)
    volume = 0.0
    momentum = _i0_np.zeros(2)
    if len(clipped) < 3:
        return (volume, momentum)
    for number in range(1, len(clipped) - 1):
        triangle = _i0_np.array([clipped[0], clipped[number], clipped[number + 1]])
        first, second = (triangle[1] - triangle[0], triangle[2] - triangle[0])
        area = abs(first[0] * second[1] - first[1] * second[0]) / 2
        h = _i0_np.maximum(coefficients[0] + triangle @ coefficients[1:], 0)
        volume += area * h.sum() / 3
        if velocity_coefficients is not None:
            u = _i0_np.asarray(velocity_coefficients)[:, 0][None, :] + triangle @ _i0_np.asarray(velocity_coefficients)[:, 1:].T
            momentum += area * (h.sum() * u.sum(axis=0) + (h[:, None] * u).sum(axis=0)) / 12
    return (volume, momentum)

def continuous_profile_moments(center, slope_x, slope_z, position_bed):
    """Canonical tile beds are constant; integrate each tile's linear free surface."""
    factor = position_bed.shape[1]
    count = len(center)
    volumes, momenta = (_i0_np.zeros(count), _i0_np.zeros((count, 2)))
    edges = _i0_np.linspace(-0.5, 0.5, factor + 1)
    for cell in range(count):
        velocity = _i0_np.column_stack((center[cell, 1:], slope_x[cell, 1:], slope_z[cell, 1:]))
        for row in range(factor):
            for column in range(factor):
                depth = [center[cell, 0] - position_bed[cell, row, column], slope_x[cell, 0], slope_z[cell, 0]]
                bounds = (edges[column], edges[column + 1], edges[row], edges[row + 1])
                volume, momentum = positive_affine_rectangle(depth, bounds, velocity)
                volumes[cell] += volume
                momenta[cell] += momentum
    return (volumes, momenta)

def positive_affine_square_line(first, last, length=1.0):
    """Exact integral of max(linear endpoint depths,0)^2 along an interface."""
    if first >= 0 and last >= 0:
        return length * (first * first + first * last + last * last) / 3
    if first <= 0 and last <= 0:
        return 0.0
    wet = max(first, last)
    return length * wet ** 3 / (3 * abs(last - first))

def exact_internal_jump_pressure(center, slope_x, slope_z, position_bed, spacing, gravity):
    factor = position_bed.shape[1]
    result = _i0_np.zeros((len(center), 2))
    edges = _i0_np.linspace(-0.5, 0.5, factor + 1)
    for cell in range(len(center)):
        eta, sx, sz = (center[cell, 0], slope_x[cell, 0], slope_z[cell, 0])
        for direction in (0, 1):
            for normal in range(1, factor):
                for tangent in range(factor):
                    if direction == 0:
                        low_bed, high_bed = (position_bed[cell, tangent, normal - 1], position_bed[cell, tangent, normal])
                        first, last = (eta + sx * edges[normal] + sz * edges[tangent], eta + sx * edges[normal] + sz * edges[tangent + 1])
                    else:
                        low_bed, high_bed = (position_bed[cell, normal - 1, tangent], position_bed[cell, normal, tangent])
                        first, last = (eta + sz * edges[normal] + sx * edges[tangent], eta + sz * edges[normal] + sx * edges[tangent + 1])
                    high = positive_affine_square_line(first - high_bed, last - high_bed, 1 / factor)
                    low = positive_affine_square_line(first - low_bed, last - low_bed, 1 / factor)
                    result[cell, direction] += gravity * (high - low) / (2 * spacing)
    return result
MODEL = 'single-domain-hydrostatic-HLL-SSPRK2-v1'
MODEL_V2 = 'single-domain-MUSCL-hydrostatic-HLL-SSPRK2-v2'
MODEL_V3 = 'single-domain-subgrid-storage-segmented-HLL-SSPRK2-v3'
MODEL_V7 = 'single-domain-subgrid-storage-segmented-HLL-canonical-Manning-SSPRK2-v7'

def assert_close(actual, expected, label):
    if _i1_np.shape(actual) != _i1_np.shape(expected) or not _i1_np.isfinite(actual).all() or (not _i1_np.allclose(actual, expected, atol=1e-09, rtol=1e-11)):
        raise ValueError('independent shallow physical ' + label + ' mismatch')

def face_flux(first, second, zfirst, zsecond, g, axis):
    crest = _i1_np.maximum(zfirst, zsecond)
    depths = [_i1_np.maximum(state[:, 0] + bed - crest, 0.0) for state, bed in ((first, zfirst), (second, zsecond))]
    velocities = [_i1_np.divide(state[:, 1:], state[:, 0, None], out=_i1_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0) for state in (first, second)]
    reconstructed = [_i1_np.column_stack((depth, depth[:, None] * velocity)) for depth, velocity in zip(depths, velocities)]
    speeds = [velocity[:, axis] for velocity in velocities]
    lower = _i1_np.minimum(speeds[0] - _i1_np.sqrt(g * depths[0]), speeds[1] - _i1_np.sqrt(g * depths[1]))
    upper = _i1_np.maximum(speeds[0] + _i1_np.sqrt(g * depths[0]), speeds[1] + _i1_np.sqrt(g * depths[1]))
    physical = [state * speed[:, None] for state, speed in zip(reconstructed, speeds)]
    for flux, depth in zip(physical, depths):
        flux[:, axis + 1] += g * depth ** 2 / 2
    denominator = upper - lower
    flux = _i1_np.divide(upper[:, None] * physical[0] - lower[:, None] * physical[1] + (lower * upper)[:, None] * (reconstructed[1] - reconstructed[0]), denominator[:, None], out=_i1_np.zeros_like(first), where=denominator[:, None] > 0)
    flux[lower >= 0] = physical[0][lower >= 0]
    flux[upper <= 0] = physical[1][upper <= 0]
    corrections = [g * (state[:, 0] ** 2 - depth ** 2) / 2 for state, depth in zip((first, second), depths)]
    return (flux, *corrections)

def reconstructed_faces(state, bed):
    depth = state[:, 0].reshape(bed.shape)
    velocity = _i1_np.divide(state[:, 1:], state[:, 0, None], out=_i1_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0).reshape(*bed.shape, 2)
    fields = _i1_np.dstack((depth + bed, bed, velocity))
    slopes = []
    for direction in (1, 0):
        slope = _i1_np.zeros_like(fields)
        low, middle, high = (fields[:, :-2], fields[:, 1:-1], fields[:, 2:]) if direction == 1 else (fields[:-2], fields[1:-1], fields[2:])
        first, second = (middle - low, high - middle)
        limited = _i1_np.where(first * second > 0, _i1_np.sign(first) * _i1_np.minimum(abs(first), abs(second)), 0.0)
        if direction == 1:
            slope[:, 1:-1] = limited
        else:
            slope[1:-1] = limited
        slope[depth == 0] = 0
        difference = slope[:, :, 0] - slope[:, :, 1]
        scale = _i1_np.minimum(1.0, _i1_np.divide(2 * depth, abs(difference), out=_i1_np.ones_like(depth), where=difference != 0))
        slopes.append(slope * scale[:, :, None])
    answers = []
    for slope in slopes:
        for sign in (-1, 1):
            face = fields + sign * 0.5 * slope
            h = _i1_np.maximum(face[:, :, 0] - face[:, :, 1], 0)
            answers.append((_i1_np.column_stack((h.ravel(), (h[:, :, None] * face[:, :, 2:]).reshape(-1, 2))), face[:, :, 1].ravel()))
    return answers

def physical_witness(state, geometry, spacing, g, tailwater, dt, *, model=MODEL):
    if model in (MODEL_V3, MODEL_V7):
        return subgrid_witness(state, geometry, spacing, g, tailwater, dt)
    bed = geometry['H2_m']
    rows, columns = bed.shape
    grid = _i1_np.arange(bed.size).reshape(bed.shape)
    left = _i1_np.concatenate((grid[:, :-1].ravel(), grid[:-1, :].ravel()))
    right = _i1_np.concatenate((grid[:, 1:].ravel(), grid[1:, :].ravel()))
    boundary = _i1_np.concatenate((grid[:, 0], grid[:, -1], grid[0], grid[-1]))
    for name, expected in (('face_left', left), ('face_right', right), ('boundary_cell', boundary)):
        if not _i1_np.array_equal(geometry[name], expected):
            raise ValueError('independent shallow D4 ordering mismatch')
    axis = _i1_np.concatenate((_i1_np.zeros(rows * (columns - 1), int), _i1_np.ones((rows - 1) * columns, int)))
    boundary_axis = _i1_np.concatenate((_i1_np.zeros(2 * rows, int), _i1_np.ones(2 * columns, int)))
    signs = _i1_np.concatenate((-_i1_np.ones(rows), _i1_np.ones(rows), -_i1_np.ones(columns), _i1_np.ones(columns)))
    datum = float(bed.min())
    z = bed.ravel() - datum
    reconstructed = reconstructed_faces(state, bed - datum) if model == MODEL_V2 else [(state, z)] * 4
    source = _i1_np.zeros_like(state)
    internal = _i1_np.zeros((len(left), 3))
    for direction in (0, 1):
        selected = axis == direction
        high, low = (reconstructed[2 * direction + 1], reconstructed[2 * direction])
        flux, first_pressure, second_pressure = face_flux(high[0][left[selected]], low[0][right[selected]], high[1][left[selected]], low[1][right[selected]], g, direction)
        internal[selected] = flux
        _i1_np.add.at(source[:, direction + 1], left[selected], -first_pressure / spacing)
        _i1_np.add.at(source[:, direction + 1], right[selected], second_pressure / spacing)
    kind = geometry['boundary_kind']
    exterior = _i1_np.zeros((len(boundary), 3))
    for side, (begin, end) in enumerate(((0, rows), (rows, 2 * rows), (2 * rows, 2 * rows + columns), (2 * rows + columns, len(boundary)))):
        direction = side // 2
        selected = slice(begin, end)
        normal = signs[selected]
        ids = boundary[selected]
        inside = reconstructed[side][0][ids].copy()
        outside = inside.copy()
        inside_bed = reconstructed[side][1][ids]
        outside_bed = inside_bed.copy()
        opened = kind[selected] != 0
        crest_selection = opened if model == MODEL_V2 else _i1_np.ones(len(ids), bool)
        outside_bed[crest_selection] = _i1_np.maximum(outside_bed[crest_selection], (geometry['boundary_crest_m'][selected] - datum)[crest_selection])
        outside[:, direction + 1] *= -1
        stage = _i1_np.where(kind[selected] == 1, outside_bed, tailwater[selected] - datum)
        outside[opened, 0] = _i1_np.maximum(stage[opened] - outside_bed[opened], 0)
        outside[opened, 1:] = 0
        inside[:, direction + 1] *= normal
        outside[:, direction + 1] *= normal
        flux, pressure, _ = face_flux(inside, outside, inside_bed, outside_bed, g, direction)
        flux[:, direction + 1] *= normal
        exterior[selected] = flux
        _i1_np.add.at(source[:, direction + 1], boundary[selected], -pressure * normal / spacing)
    if model == MODEL_V2:
        for direction in (0, 1):
            low, high = (reconstructed[2 * direction], reconstructed[2 * direction + 1])
            source[:, direction + 1] -= g * 0.5 * (low[0][:, 0] + high[0][:, 0]) * (high[1] - low[1]) / spacing
    outgoing = _i1_np.bincount(left, weights=_i1_np.maximum(internal[:, 0], 0) * spacing, minlength=bed.size)
    outgoing += _i1_np.bincount(right, weights=_i1_np.maximum(-internal[:, 0], 0) * spacing, minlength=bed.size)
    outgoing += _i1_np.bincount(boundary, weights=_i1_np.maximum(exterior[:, 0], 0) * spacing, minlength=bed.size)
    scale = _i1_np.ones(bed.size)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scale[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    internal *= _i1_np.where(internal[:, 0] >= 0, scale[left], scale[right])[:, None]
    exterior *= _i1_np.where(exterior[:, 0] >= 0, scale[boundary], 1.0)[:, None]
    rhs = source.copy()
    _i1_np.add.at(rhs, left, -internal / spacing)
    _i1_np.add.at(rhs, right, internal / spacing)
    _i1_np.add.at(rhs, boundary, -exterior / spacing)
    return (rhs, internal, exterior, source)

def storage_stage(depth, subbed):
    counts = _i1_np.arange(1, subbed.shape[1] + 1)
    candidate = (depth[:, None] * subbed.shape[1] + _i1_np.cumsum(subbed, axis=1)) / counts
    index = (candidate >= subbed).sum(axis=1) - 1
    return candidate[_i1_np.arange(len(depth)), index]

def canonical_manning(state, subbed, dt, gravity, roughness):
    stage = storage_stage(state[:, 0], subbed)
    h = _i1_np.maximum(stage[:, None] - subbed, 0)
    integral = _i1_np.zeros_like(h)
    _i1_np.power(h, -1 / 3, out=integral, where=h > 0)
    factor = integral.mean(axis=1)
    squared = state[:, 0] ** 2
    denominator = squared + dt * gravity * roughness ** 2 * _i1_np.hypot(state[:, 1], state[:, 2]) * factor
    damping = _i1_np.divide(squared, denominator, out=_i1_np.zeros_like(squared), where=denominator > 0)
    return (damping, factor)

def subgrid_witness(state, geometry, spacing, g, tailwater, dt):
    left, right, cells = (geometry[name] for name in ('face_left', 'face_right', 'boundary_cell'))
    rows, columns = geometry['H2_m'].shape
    axes = _i1_np.r_[_i1_np.zeros(rows * (columns - 1), int), _i1_np.ones((rows - 1) * columns, int)]
    boundary_axes = _i1_np.r_[_i1_np.zeros(2 * rows, int), _i1_np.ones(2 * columns, int)]
    signs = _i1_np.r_[-_i1_np.ones(rows), _i1_np.ones(rows), -_i1_np.ones(columns), _i1_np.ones(columns)]
    datum = float(geometry['hydraulic_datum_m'])
    stage = storage_stage(state[:, 0], geometry['subcell_bed_relative_m'])
    velocity = _i1_np.divide(state[:, 1:], state[:, 0, None], out=_i1_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    internal = _i1_np.zeros((len(left), 3))
    exterior = _i1_np.zeros((len(cells), 3))
    source = _i1_np.zeros_like(state)
    for direction in (0, 1):
        selected = axes == direction
        crest = geometry['face_segment_crest_relative_m'][selected]
        hl = _i1_np.maximum(stage[left[selected], None] - crest, 0)
        hr = _i1_np.maximum(stage[right[selected], None] - crest, 0)
        first = _i1_np.column_stack((hl.ravel(), (hl[:, :, None] * velocity[left[selected], None, :]).reshape(-1, 2)))
        second = _i1_np.column_stack((hr.ravel(), (hr[:, :, None] * velocity[right[selected], None, :]).reshape(-1, 2)))
        flux, _, _ = face_flux(first, second, crest.ravel(), crest.ravel(), g, direction)
        internal[selected] = flux.reshape(*crest.shape, 3).mean(axis=1)
        _i1_np.add.at(source[:, direction + 1], left[selected], 0.5 * g * (hl ** 2).mean(axis=1) / spacing)
        _i1_np.add.at(source[:, direction + 1], right[selected], -0.5 * g * (hr ** 2).mean(axis=1) / spacing)
        selected = boundary_axes == direction
        ids = cells[selected]
        kind = geometry['boundary_kind'][selected]
        crest = geometry['boundary_segment_crest_relative_m'][selected].copy()
        opened = kind != 0
        crest[opened] = _i1_np.maximum(crest[opened], geometry['boundary_crest_m'][selected][opened, None] - datum)
        h = _i1_np.maximum(stage[ids, None] - crest, 0)
        first = _i1_np.column_stack((h.ravel(), (h[:, :, None] * velocity[ids, None, :]).reshape(-1, 2)))
        ghost = first.copy()
        ghost[:, direction + 1] *= -1
        opened_segments = _i1_np.repeat(opened, crest.shape[1])
        outside = _i1_np.where(kind[:, None] == 1, crest, tailwater[selected, None] - datum)
        ghost[opened_segments, 0] = _i1_np.maximum(outside - crest, 0).ravel()[opened_segments]
        ghost[opened_segments, 1:] = 0
        normal = _i1_np.repeat(signs[selected], crest.shape[1])
        first[:, direction + 1] *= normal
        ghost[:, direction + 1] *= normal
        flux, _, _ = face_flux(first, ghost, crest.ravel(), crest.ravel(), g, direction)
        flux[:, direction + 1] *= normal
        exterior[selected] = flux.reshape(*crest.shape, 3).mean(axis=1)
        _i1_np.add.at(source[:, direction + 1], ids, signs[selected] * 0.5 * g * (h ** 2).mean(axis=1) / spacing)
    outgoing = _i1_np.bincount(left, weights=_i1_np.maximum(internal[:, 0], 0) * spacing, minlength=len(state))
    outgoing += _i1_np.bincount(right, weights=_i1_np.maximum(-internal[:, 0], 0) * spacing, minlength=len(state))
    outgoing += _i1_np.bincount(cells, weights=_i1_np.maximum(exterior[:, 0], 0) * spacing, minlength=len(state))
    scale = _i1_np.ones(len(state))
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scale[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    internal *= _i1_np.where(internal[:, 0] >= 0, scale[left], scale[right])[:, None]
    exterior *= _i1_np.where(exterior[:, 0] >= 0, scale[cells], 1.0)[:, None]
    rhs = source.copy()
    _i1_np.add.at(rhs, left, -internal / spacing)
    _i1_np.add.at(rhs, right, internal / spacing)
    _i1_np.add.at(rhs, cells, -exterior / spacing)
    return (rhs, internal, exterior, source)

def audit_momentum(packet, metadata, geometry, spacing, budget, forcing, tailwater):
    before, predictor, after = (packet[name] for name in ('state_before', 'state_predictor', 'state_after'))
    dt = metadata['dt_s']
    model = metadata.get('hydraulic_model')
    if model not in (MODEL, MODEL_V2, MODEL_V3, MODEL_V7):
        raise ValueError('independent shallow model unsupported')
    g = budget['gravity_m_s2']
    assert_close(packet['forcing_m3_s'], forcing, 'forcing')
    assert_close(packet['tailwater_m'], tailwater, 'tailwater')
    if not 0 < dt <= budget['max_dt_s'] or any((_i1_np.any(state[:, 0] < 0) for state in (before, predictor, after))):
        raise ValueError('independent shallow sampled time/depth mismatch')
    velocity = _i1_np.divide(before[:, 1:], before[:, 0, None], out=_i1_np.zeros_like(before[:, 1:]), where=before[:, 0, None] > 0)
    speed = float((abs(velocity).sum(axis=1) + 2 * _i1_np.sqrt(g * before[:, 0])).max(initial=0))
    if model in (MODEL_V3, MODEL_V7):
        stages = storage_stage(before[:, 0], geometry['subcell_bed_relative_m'])
        deepest = _i1_np.maximum(stages - geometry['subcell_bed_relative_m'][:, 0], 0)
        speed = max(speed, float((abs(velocity).sum(axis=1) + 2 * _i1_np.sqrt(g * deepest)).max(initial=0)))
    external_bed = _i1_np.maximum(geometry['H2_m'].ravel()[geometry['boundary_cell']], geometry['boundary_crest_m'])
    if model in (MODEL_V3, MODEL_V7):
        external_bed = _i1_np.maximum(geometry['boundary_segment_crest_relative_m'].min(axis=1) + geometry['hydraulic_datum_m'], geometry['boundary_crest_m'])
    exterior_stage = _i1_np.where(geometry['boundary_kind'] == 1, external_bed, tailwater)
    external_depth = _i1_np.maximum(exterior_stage - external_bed, 0)
    speed = max(speed, float((2 * _i1_np.sqrt(g * external_depth[geometry['boundary_kind'] != 0])).max(initial=0)))
    if dt > budget['inertial_cfl'] * spacing / max(speed, 1e-12) + 1e-12:
        raise ValueError('independent shallow advective CFL mismatch')
    equations = []
    for number, state in ((1, before), (2, predictor)):
        rhs, internal, external, source = physical_witness(state, geometry, spacing, g, tailwater, dt, model=model)
        for name, expected in (('internal_flux', internal), ('boundary_flux', external), ('bed_source', source)):
            assert_close(packet[f'rk{number}_' + name], expected, f'RK{number} ' + name)
        rhs[:, 0] += forcing / spacing ** 2
        equations.append(rhs)
    assert_close(predictor, before + dt * equations[0], 'RK predictor')
    undamped = 0.5 * before + 0.5 * (predictor + dt * equations[1])
    expected = undamped.copy()
    wet = expected[:, 0] > 0
    if model == MODEL_V7:
        damping, factor = canonical_manning(undamped, geometry['subcell_bed_relative_m'], dt, g, budget['roughness_s_m_third'])
        assert_close(packet['manning_inverse_depth_third_mean'], factor, 'canonical wet-subcell inverse-depth integral')
        expected[:, 1:] *= damping[:, None]
    else:
        hpower = expected[wet, 0] ** (7 / 3)
        denominator = hpower + dt * g * budget['roughness_s_m_third'] ** 2 * _i1_np.linalg.norm(expected[wet, 1:], axis=1)
        expected[wet, 1:] = _i1_np.divide(expected[wet, 1:] * hpower[:, None], denominator[:, None], out=_i1_np.zeros_like(expected[wet, 1:]), where=denominator[:, None] > 0)
    assert_close(after, expected, 'RK endpoint and drag')
    assert_close(packet['manning_momentum_change'], expected[:, 1:] - undamped[:, 1:], 'drag witness')
    return dict(physical_hll_flux_verified=True, side_pressure_source_verified=True, reflect_open_crest_verified=True, donor_limiter_verified=True, ssprk2_and_manning_verified=True, advective_cfl_verified=True, manning_equation_verified='canonical wet-subcell integrated implicit Manning' if model == MODEL_V7 else 'legacy coarse mean depth implicit Manning', canonical_subgrid_manning_consistency_verified=True if model == MODEL_V7 else False if model == MODEL_V3 else None)
