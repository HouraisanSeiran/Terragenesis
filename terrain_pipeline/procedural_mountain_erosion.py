"""Pointwise directional gully appearance, algorithm ``directional-gullies-v1``.

A method-level adaptation of Rune Skovbo Johansen's Advanced Terrain Erosion
Filter and its Clay John / Fewes lineage, as reviewed in
research/runevision-erosion-primary-sources-2026-11-03.md. The current
Shadertoy source was unavailable: this is not a verified source port. It
simulates neither water nor sediment.

At each of three fixed scales, 5x5 jittered cells contribute compact radial
weights times a sine/cosine phase perpendicular to the supplied slope. The
weighted phase is partially normalized by (amplitude squared + k2)**0.5;
this avoids division by zero at phase cancellation. Constant phase width and
slope fade towards the structural ridge/valley target retain extrema. A mask
based on each layer suppresses detail at existing extrema; an artistic phase
direction feedback steers the next layer. This feedback is not a physical
derivative; derive real slopes from the final height field instead. Output is
bounded by 48 m times strength and depends on no window-wide statistics.
The radius is 1.5 cells: offsets -2 through +2 cover every jittered cell
that can contribute on either side of a cell boundary. Each octave evaluates
exactly 25 kernels per point.
"""

import hashlib
import numbers

import numpy as np

ALGORITHM_ID = "directional-gullies-v1"
MAX_COORDINATE_M = 1_000_000_000.0
MAX_DELTA_M = 48.0
MAX_SAMPLES = 1_048_576


def _seed(world_seed, purpose):
    data = f"{ALGORITHM_ID}:{world_seed}:{purpose}".encode("ascii")
    return np.uint64(int.from_bytes(hashlib.sha256(data).digest()[:8], "little"))


def _random(ix, iz, seed):
    # Unsigned wraparound is intentional and independent of query order.
    with np.errstate(over="ignore"):
        v = ix.astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
        v ^= iz.astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
        v ^= seed
        v ^= v >> np.uint64(30)
        v *= np.uint64(0xBF58476D1CE4E5B9)
        v ^= v >> np.uint64(27)
        v *= np.uint64(0x94D049BB133111EB)
        v ^= v >> np.uint64(31)
    return (v >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)


def directional_detail(x_m, z_m, height_m, slope_x, slope_z, ridge_target, *, world_seed, strength):
    """Return a float64 elevation delta in metres at broadcast world points.

    Coordinates are metres in [-1e9, 1e9]; height is in metres, slopes are
    actual dimensionless metre/metre gradients, and ridge_target is structural
    position in [-1, 1] (valley to ridge), not elevation above sea level.
    Strength is a finite scalar in [0, 1]. All numeric inputs must be finite.
    The broadcast result must contain 1 to 1,048,576 samples; world_seed is
    an integer in [0, 2**64 - 1].
    """
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, numbers.Integral) or not 0 <= world_seed < 2**64:
        raise ValueError("world_seed must be an unsigned 64-bit integer")
    if isinstance(strength, (bool, np.bool_)) or not isinstance(strength, numbers.Real):
        raise ValueError("strength must be a finite scalar in [0, 1]")
    strength = float(strength)
    if not np.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError("strength must be a finite scalar in [0, 1]")
    try:
        values = np.broadcast_arrays(*[np.asarray(v, dtype=np.float64) for v in
            (x_m, z_m, height_m, slope_x, slope_z, ridge_target)])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("inputs must be broadcastable real numbers") from exc
    if values[0].size == 0 or values[0].size > MAX_SAMPLES:
        raise ValueError("broadcast sample count must be in [1, 1048576]")
    x, z, height, sx, sz, target = values
    if any(not np.all(np.isfinite(v)) for v in values):
        raise ValueError("inputs must be finite")
    if np.any(np.abs(x) > MAX_COORDINATE_M) or np.any(np.abs(z) > MAX_COORDINATE_M):
        raise ValueError("coordinates exceed the fixed domain")
    if np.any(np.abs(target) > 1.0):
        raise ValueError("ridge_target must be in [-1, 1]")
    if strength == 0.0:
        return np.zeros(x.shape, dtype=np.float64)

    # Clipping avoids overflow on extreme but finite gradients without changing
    # the direction or fade of ordinary terrain slopes.
    scale = np.maximum(np.maximum(np.abs(sx), np.abs(sz)), 1.0)
    dx, dz = sx / scale, sz / scale
    norm = np.hypot(dx, dz)
    dx = np.divide(dx, norm, out=np.ones_like(dx), where=norm > 1e-15)
    dz = np.divide(dz, norm, out=np.zeros_like(dz), where=norm > 1e-15)
    slope = np.minimum(np.hypot(sx / scale, sz / scale) * np.minimum(scale, 1e6), 1.0)
    fade = 1.0 - (1.0 - slope) ** 2
    mask = np.ones_like(x)
    result = np.zeros_like(x)
    for octave, (wavelength, amplitude) in enumerate(((1200.0, 24.0), (600.0, 12.0), (300.0, 6.0))):
        px, pz = x / wavelength, z / wavelength
        bx, bz = np.floor(px).astype(np.int64), np.floor(pz).astype(np.int64)
        cosine = np.zeros_like(x)
        sine = np.zeros_like(x)
        weight_sum = np.zeros_like(x)
        seed_x = _seed(world_seed, f"octave-{octave}-jitter-x")
        seed_z = _seed(world_seed, f"octave-{octave}-jitter-z")
        seed_phase = _seed(world_seed, f"octave-{octave}-phase")
        for ox in (-2, -1, 0, 1, 2):
            for oz in (-2, -1, 0, 1, 2):
                ix, iz = bx + ox, bz + oz
                rx = px - (ix + _random(ix, iz, seed_x))
                rz = pz - (iz + _random(ix, iz, seed_z))
                weight = np.maximum(1.0 - (rx * rx + rz * rz) / 2.25, 0.0) ** 2
                phase = 2.0 * np.pi * (rx * -dz + rz * dx + _random(ix, iz, seed_phase))
                cosine += weight * np.cos(phase)
                sine += weight * np.sin(phase)
                weight_sum += weight
        cosine /= np.maximum(weight_sum, 1e-12)
        sine /= np.maximum(weight_sum, 1e-12)
        # k2 partial normalization has a strictly positive denominator.
        k2 = 0.25
        wave = cosine / np.sqrt(cosine * cosine + sine * sine + k2)
        layer = fade * wave + (1.0 - fade) * target
        result += amplitude * mask * layer
        mask *= np.clip(1.0 - 0.7 * layer * layer, 0.0, 1.0)
        # Artistic direction feedback; bounded, normalized and never exported.
        dx_next = dx - 0.35 * sine * dz
        dz_next = dz + 0.35 * sine * dx
        direction_norm = np.hypot(dx_next, dz_next)
        dx, dz = dx_next / direction_norm, dz_next / direction_norm
    return np.asarray(result * strength, dtype=np.float64)
