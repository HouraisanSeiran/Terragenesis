"""Finite, closed-boundary D4 floodplain water and suspended-solid transport.

This is a storage/flux approximation without momentum, not a shallow-water
solver. Cell-centre water heads drive Manning-type exchange over actual bed
crests. ``spacing_m`` supplies the full face width and centre spacing; partial
cell areas change storage, but do not describe subcell face apertures.
"""

import math

import numpy as np


def _field(value, shape, name, *, mask=False):
    array = np.asarray(value)
    if mask and array.dtype.kind != 'b':
        raise ValueError(f'{name} must contain booleans')
    try:
        array = np.broadcast_to(array, shape)
    except ValueError as exc:
        raise ValueError(f'{name} must be scalar or match bed_m') from exc
    if mask:
        return array
    try:
        array = np.asarray(array, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must contain finite numbers') from exc
    if not np.isfinite(array).all() or np.any(array < 0):
        raise ValueError(f'{name} must contain finite nonnegative numbers')
    return array


def _inventory(value, shape, name):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape:
        raise ValueError(f'{name} must match bed_m')
    if not np.isfinite(array).all() or np.any(array < 0):
        raise ValueError(f'{name} must contain finite nonnegative numbers')
    return array.copy()


def _phase_change(water, mobile, stranded, active):
    wet = active & (water > 0)
    dry = active & ~wet
    released = float(stranded[wet].sum())
    parked = float(mobile[dry].sum())
    mobile[wet] += stranded[wet]
    stranded[wet] = 0.
    stranded[dry] += mobile[dry]
    mobile[dry] = 0.
    return released, parked


def _settle(base, bed, water, mobile, deposited, area, solid_area,
            active, settling_velocity_m_s, duration_s):
    wet = active & (water > 0) & (mobile > 0)
    if not np.any(wet) or settling_velocity_m_s == 0:
        return
    depth = water[wet] / area[wet]
    with np.errstate(over='ignore', divide='ignore'):
        fraction = -np.expm1(-settling_velocity_m_s * duration_s / depth)
    amount = np.minimum(mobile[wet], mobile[wet] * fraction)
    mobile[wet] -= amount
    deposited[wet] += amount
    with np.errstate(over='ignore', divide='ignore'):
        raised = base[wet] + deposited[wet] / solid_area[wet]
    if not np.isfinite(raised).all():
        raise ValueError('deposition produces an unrepresentable bed elevation')
    bed[wet] = raised


def _face_transfers(bed, area, water, active, spacing_m, roughness, duration_s):
    """Return one finite directed transfer per open D4 face.

    A quarter of each pair's head-equalizing amount is a conservative D4
    simultaneous-face limiter. It bounds the sum of the head interpolation
    weights at every cell, including cells with four incoming donors. The
    separate shared-donor limiter below bounds all outgoing water together.
    """
    rows, cols = bed.shape
    depth = np.divide(water, area, out=np.zeros_like(water), where=active)
    head = bed + depth
    if not np.isfinite(head[active]).all():
        raise ValueError('water produces an unrepresentable head')
    donors = []
    receivers = []
    amounts = []
    for axis in (0, 1):
        if bed.shape[axis] < 2:
            continue
        first = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        second = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        difference = head[first] - head[second]
        crest = np.maximum(bed[first], bed[second])
        flowing_depth = np.maximum(head[first], head[second]) - crest
        open_face = (active[first] & active[second] & (flowing_depth > 0)
                     & (difference != 0))
        face = np.flatnonzero(open_face)
        if not face.size:
            continue
        if axis == 0:
            a = face
            b = face + cols
        else:
            a = (face // (cols - 1)) * cols + face % (cols - 1)
            b = a + 1
        flat_area = area.ravel()
        gap = np.abs(difference.ravel()[face])
        flow_depth = flowing_depth.ravel()[face]
        positive = difference.ravel()[face] > 0
        donor = np.where(positive, a, b)
        receiver = np.where(positive, b, a)
        # Algebraic minimum-area form avoids overflowing 1 / very small area.
        low_area = np.minimum(flat_area[a], flat_area[b])
        high_area = np.maximum(flat_area[a], flat_area[b])
        equalizing = gap * low_area / (1. + low_area / high_area)
        above_crest = flow_depth * flat_area[donor]
        with np.errstate(over='ignore', divide='ignore'):
            discharge = (spacing_m / roughness * flow_depth ** (5. / 3.)
                         * np.sqrt(gap / spacing_m))
            amount = np.minimum(discharge * duration_s,
                                .25 * np.minimum(equalizing, above_crest))
        if not np.isfinite(amount).all():
            raise ValueError('face exchange is not representable')
        moving = amount > 0
        donors.append(donor[moving])
        receivers.append(receiver[moving])
        amounts.append(amount[moving])
    if not amounts:
        return np.empty(0, dtype=np.intp), np.empty(0, dtype=np.intp), np.empty(0)
    donor = np.concatenate(donors)
    receiver = np.concatenate(receivers)
    amount = np.concatenate(amounts)
    outgoing = np.bincount(donor, weights=amount, minlength=water.size)
    scale = np.divide(water.ravel(), outgoing, out=np.ones_like(outgoing), where=outgoing > 0)
    amount *= np.minimum(scale[donor], 1.)
    return donor, receiver, amount


def advance_floodplain(bed_m, water_m3, mobile_solid_m3, stranded_solid_m3, *,
                       area_m2, solid_area_m2, allowed_mask, spacing_m,
                       duration_s, roughness=.06, settling_velocity_m_s=.0001,
                       max_step_s=60.):
    """Advance finite water/solid inventories, returning new full-size arrays.

    All inventories are m³; solids exclude pore volume. ``area_m2`` is water
    storage area and ``solid_area_m2`` converts deposited solid volume to bed
    rise (usually water area times one minus porosity). Areas and the boolean
    mask may be scalar or broadcastable to the matching 2D stock arrays.
    Positive-area allowed cells require positive solid area. Zero-area and
    disallowed cells are sealed and retain every inventory unchanged.

    No water or solid enters/leaves the domain. There is no bed erosion,
    momentum, infiltration, evaporation, tide or river-node boundary here.
    Callers own injection/return and may add only uniquely accounted water.
    Dry mobile stock is stranded; all local stranded stock becomes mobile
    when that cell holds water. Deposited stock is never remobilized.
    Strang-split exponential settling uses actual depth; bed rise retains
    water volume and changes the head for subsequent fluxes. ``max_step_s``
    is a maximum physical timestep, not an iteration/relaxation count.
    """
    base = np.asarray(bed_m, dtype=np.float64)
    if base.ndim != 2 or not base.size or not np.isfinite(base).all():
        raise ValueError('bed_m must be a finite nonempty 2D array')
    parameters = (spacing_m, duration_s, roughness, settling_velocity_m_s, max_step_s)
    if any(np.ndim(value) != 0 for value in parameters):
        raise ValueError('floodplain parameters must be scalars')
    try:
        spacing_m, duration_s, roughness, settling_velocity_m_s, max_step_s = (
            float(value) for value in parameters)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('floodplain parameters must be real scalars') from exc
    if (not np.isfinite((spacing_m, duration_s, roughness,
                         settling_velocity_m_s, max_step_s)).all()
            or spacing_m <= 0 or duration_s < 0 or roughness <= 0
            or settling_velocity_m_s < 0 or max_step_s <= 0):
        raise ValueError('invalid floodplain parameters')
    ratio = duration_s / max_step_s
    if not np.isfinite(ratio):
        raise ValueError('duration requires an unrepresentable step count')
    shape = base.shape
    area = _field(area_m2, shape, 'area_m2')
    solid_area = _field(solid_area_m2, shape, 'solid_area_m2')
    allowed = _field(allowed_mask, shape, 'allowed_mask', mask=True)
    active = allowed & (area > 0)
    if np.any(active & (solid_area <= 0)):
        raise ValueError('positive-area allowed cells require positive solid_area_m2')
    water = _inventory(water_m3, shape, 'water_m3')
    mobile = _inventory(mobile_solid_m3, shape, 'mobile_solid_m3')
    stranded = _inventory(stranded_solid_m3, shape, 'stranded_solid_m3')
    initial_water = float(water.sum())
    initial_solid = float(mobile.sum() + stranded.sum())
    if not np.isfinite((initial_water, initial_solid)).all():
        raise ValueError('inventory totals must be representable')
    bed = base.copy()
    deposited = np.zeros(shape, dtype=np.float64)
    released = parked = transferred_water = advected_solid = 0.
    steps = 0
    max_box_cells = 0
    if duration_s > 0:
        released, parked = _phase_change(water, mobile, stranded, active)
        wet_rows, wet_cols = np.nonzero(active & (water > 0))
        requested_steps = max(1, math.ceil(ratio))
        step_s = duration_s / requested_steps
        if wet_rows.size:
            bounds = (int(wet_rows.min()), int(wet_rows.max()) + 1,
                      int(wet_cols.min()), int(wet_cols.max()) + 1)
            for _ in range(requested_steps):
                r0, r1, c0, c1 = bounds
                r0, r1 = max(0, r0 - 1), min(shape[0], r1 + 1)
                c0, c1 = max(0, c0 - 1), min(shape[1], c1 + 1)
                box = (slice(r0, r1), slice(c0, c1))
                local_water = water[box]
                local_mobile = mobile[box]
                local_stranded = stranded[box]
                local_active = active[box]
                max_box_cells = max(max_box_cells, local_water.size)
                _settle(base[box], bed[box], local_water, local_mobile, deposited[box],
                        area[box], solid_area[box], local_active, settling_velocity_m_s, step_s / 2.)
                donor, receiver, amount = _face_transfers(
                    bed[box], area[box], local_water, local_active, spacing_m, roughness, step_s)
                if amount.size:
                    # Flattened copies are required: a cropped 2D box need not
                    # be C-contiguous, so ravel() may otherwise silently copy.
                    old_water = local_water.ravel().copy()
                    old_mobile = local_mobile.ravel().copy()
                    sediment = old_mobile[donor] * (amount / old_water[donor])
                    water_out = np.bincount(donor, weights=amount, minlength=old_water.size)
                    water_in = np.bincount(receiver, weights=amount, minlength=old_water.size)
                    solid_out = np.bincount(donor, weights=sediment, minlength=old_water.size)
                    solid_in = np.bincount(receiver, weights=sediment, minlength=old_water.size)
                    local_water[:] = np.maximum(old_water - water_out + water_in, 0.).reshape(local_water.shape)
                    local_mobile[:] = np.maximum(old_mobile - solid_out + solid_in, 0.).reshape(local_mobile.shape)
                    transferred_water += float(amount.sum())
                    advected_solid += float(sediment.sum())
                new_released, new_parked = _phase_change(
                    local_water, local_mobile, local_stranded, local_active)
                released += new_released
                parked += new_parked
                _settle(base[box], bed[box], local_water, local_mobile, deposited[box],
                        area[box], solid_area[box], local_active, settling_velocity_m_s, step_s / 2.)
                steps += 1
                wet_rows, wet_cols = np.nonzero(local_active & (local_water > 0))
                if not wet_rows.size:
                    break
                bounds = (r0 + int(wet_rows.min()), r0 + int(wet_rows.max()) + 1,
                          c0 + int(wet_cols.min()), c0 + int(wet_cols.max()) + 1)
    final_water = float(water.sum())
    final_solid = float(mobile.sum() + stranded.sum() + deposited.sum())
    report = {
        'algorithm': 'finite-d4-manning-floodplain-v1',
        'approximation': 'no momentum; full-width D4 faces; well-mixed cell sediment',
        'boundary': 'closed; injection and river return belong to the caller',
        'duration_s': float(duration_s),
        'max_step_s': float(max_step_s),
        'steps': steps,
        'max_active_box_cells': max_box_cells,
        'initial_water_m3': initial_water,
        'final_water_m3': final_water,
        'water_residual_m3': final_water - initial_water,
        'initial_solid_m3': initial_solid,
        'final_solid_m3': final_solid,
        'solid_residual_m3': final_solid - initial_solid,
        'transferred_water_m3': transferred_water,
        'advected_solid_m3': advected_solid,
        'deposited_solid_m3': float(deposited.sum()),
        'rewetted_solid_m3': released,
        'newly_stranded_solid_m3': parked,
    }
    return {'bed_m': bed, 'water_m3': water, 'mobile_solid_m3': mobile,
            'stranded_solid_m3': stranded, 'deposited_solid_m3': deposited,
            'report': report}
