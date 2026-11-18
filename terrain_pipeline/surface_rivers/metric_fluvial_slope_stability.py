"""Conservative repose relaxation of an explicitly bounded mobile column.

Composition is a homogeneous-column approximation for this gravity phase.
It does not imply grain-class conservation in native pyDeltaRCM routing.
"""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class SlopeStabilityResult:
    bed_m: np.ndarray
    sand_fraction: np.ndarray
    active_layer: np.ndarray
    ledger: dict
    converged: bool


def _edge_groups(shape, eligible):
    rows, columns = np.indices(shape)
    groups = []
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        r, c = rows.ravel(), columns.ravel()
        rr, cc = r + dr, c + dc
        valid = (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
        r, c, rr, cc = r[valid], c[valid], rr[valid], cc[valid]
        valid = eligible[r, c] & eligible[rr, cc]
        r, c, rr, cc = r[valid], c[valid], rr[valid], cc[valid]
        parity = c % 2 if dr == 0 else r % 2
        for color in (0, 1):
            take = parity == color
            groups.append((r[take] * shape[1] + c[take],
                           rr[take] * shape[1] + cc[take], math.hypot(dr, dc)))
    return groups


def relax_mobile_slopes(bed_m, mobile_base_m, sand_fraction, active_layer,
                        eligible, *, dx_m, repose_angle_deg=30.,
                        tolerance_m=1e-6, max_sweeps=512,
                        substrate_sand_fraction=.5):
    """Return actual relaxed state, including an unconverged finite-stop state.

    ``mobile_base_m`` stays fixed. Callers own its native-phase updates and
    persistence. Row zero is always excluded; callers exclude walls/invalid cells.
    No transfer crosses the eligible domain and no material is exported.
    """
    bed = np.array(bed_m, dtype=np.float64, copy=True)
    base = np.asarray(mobile_base_m, dtype=np.float64)
    fraction = np.array(sand_fraction, dtype=np.float64, copy=True)
    active = np.array(active_layer, dtype=np.float64, copy=True)
    mask = np.array(eligible, dtype=bool, copy=True)
    if (bed.ndim != 2 or min(bed.shape) < 1
            or any(array.shape != bed.shape for array in (base, fraction, active, mask))
            or any(not np.isfinite(array).all() for array in (bed, base, fraction, active))
            or np.any(base > bed) or np.any((fraction < 0.) | (fraction > 1.))
            or np.any((active < 0.) | (active > 1.))):
        raise ValueError("finite matching beds, mobile base and material fractions required")
    if (not all(math.isfinite(value) for value in
                (dx_m, repose_angle_deg, tolerance_m, substrate_sand_fraction))
            or dx_m <= 0. or not 0. < repose_angle_deg < 90.
            or tolerance_m <= 0. or type(max_sweeps) is not int or max_sweeps < 1
            or not 0. <= substrate_sand_fraction <= 1.):
        raise ValueError("positive spacing, finite repose/tolerance and sweep budget required")
    mask[0, :] = False
    groups = _edge_groups(bed.shape, mask)
    area = dx_m ** 2
    slope = math.tan(math.radians(repose_angle_deg))
    initial_bed = bed.copy()
    initial_mobile = (bed - base) * area
    initial_sand = initial_mobile * fraction
    z, b, f, a = bed.ravel(), base.ravel(), fraction.ravel(), active.ravel()
    transferred = sand_transferred = mud_transferred = 0.
    exchanges = 0

    def maximum_excess():
        excess_max = 0.
        inherited_max = 0.
        for left, right, distance in groups:
            high = np.where(z[left] >= z[right], left, right)
            excess = np.abs(z[left] - z[right]) - slope * dx_m * distance
            movable = z[high] > b[high]
            excess_max = max(excess_max, float(np.max(excess[movable], initial=0.)))
            inherited_max = max(inherited_max, float(np.max(excess[~movable], initial=0.)))
        return excess_max, inherited_max

    excess_before, _ = maximum_excess()
    sweeps = 0
    stalled = False
    excess, inherited_excess = maximum_excess()
    while excess > tolerance_m and sweeps < max_sweeps:
        sweep_start = bed.copy()
        ordered = groups if sweeps % 2 == 0 else reversed(groups)
        for left, right, distance in ordered:
            high = np.where(z[left] >= z[right], left, right)
            low = np.where(z[left] >= z[right], right, left)
            excess_pair = z[high] - z[low] - slope * dx_m * distance
            available = (z[high] - b[high]) * area
            volume = np.minimum(available, area * .5 * np.maximum(excess_pair, 0.))
            take = (volume > 0.) & (excess_pair > tolerance_m)
            take &= ((z[high] - volume / area != z[high])
                     | (z[low] + volume / area != z[low]))
            donor, receiver, volume = high[take], low[take], volume[take]
            if not volume.size:
                continue
            donor_fraction = f[donor].copy()
            receiver_mobile = (z[receiver] - b[receiver]) * area
            receiver_sand = receiver_mobile * f[receiver] + volume * donor_fraction
            f[receiver] = receiver_sand / (receiver_mobile + volume)
            # Each color contains disjoint pairs, so no cell can overdraw here.
            exhausted = volume == available[take]
            z[donor] -= volume / area
            z[donor[exhausted]] = b[donor[exhausted]]
            z[receiver] += volume / area
            f[donor[exhausted]] = substrate_sand_fraction
            a[donor] = f[donor]
            a[receiver] = f[receiver]
            transferred += float(volume.sum())
            sand_transferred += float(np.sum(volume * donor_fraction))
            mud_transferred += float(np.sum(volume * (1. - donor_fraction)))
            exchanges += volume.size
        sweeps += 1
        excess, inherited_excess = maximum_excess()
        if np.array_equal(bed, sweep_start) and excess > tolerance_m:
            stalled = True
            break

    final_mobile = (bed - base) * area
    final_sand = final_mobile * fraction
    bulk_residual = float(np.sum((bed - initial_bed) * area))
    sand_residual = float(np.sum(final_sand - initial_sand))
    mud_residual = float(np.sum((final_mobile - final_sand) - (initial_mobile - initial_sand)))
    ledger = {
        "sweeps": sweeps, "exchange_count": int(exchanges),
        "transferred_bulk_m3": transferred,
        "transferred_sand_bulk_m3": sand_transferred,
        "transferred_mud_bulk_m3": mud_transferred,
        "raw_residual_bulk_m3": bulk_residual,
        "raw_residual_sand_bulk_m3": sand_residual,
        "raw_residual_mud_bulk_m3": mud_residual,
        "maximum_mobile_excess_before_m": excess_before,
        "maximum_mobile_excess_after_m": excess,
        "maximum_immobile_excess_after_m": inherited_excess,
        "exported_bulk_m3": 0.,
        "repose_angle_deg": repose_angle_deg, "tolerance_m": tolerance_m,
        "max_sweeps": max_sweeps,
        "stalled_at_float64_resolution": stalled,
        "composition_semantics": "homogeneous mobile column; gravity phase only",
    }
    return SlopeStabilityResult(bed, fraction, active, ledger, excess <= tolerance_m)
