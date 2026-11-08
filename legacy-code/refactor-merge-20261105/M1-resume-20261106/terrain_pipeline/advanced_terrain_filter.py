"""Advanced Terrain Erosion Filter, pointwise NumPy port.

Advanced Terrain Erosion Filter and Phacelle Noise copyright (c) 2025 Rune
Skovbo Johansen. C# conversion copyright (c) 2026 Luke Mitchell. This Source
Code Form is subject to the Mozilla Public License, v. 2.0:
https://mozilla.org/MPL/2.0/. Source and third-party notices are pinned at
third_party/runevision_advanced_terrain_erosion/.
Upstream: https://github.com/lpmitchell/AdvancedTerrainErosion/tree/57e79cc331d17e2a45c897bea9c4c022d1fc5551

Ports ErosionFilter and PhacelleNoise, not the Unity wrapper, FBM terrain,
cubemap projection or terrain-height offset. We accept supplied physical
slopes and structural fade target. Coordinates are divided by wavelength L,
heights by amplitude H, slopes multiplied by L/H; final deltas and artistic
slopes convert back with H and H/L. Upstream's scale and strength are chosen
so the first octave has cell spacing L and height amplitude H. The artistic
slope ignores derivatives of masks and is not a physical terrain derivative.
The upstream int seed is derived from the uint64 world seed using SHA-256
of ``advanced-terrain-filter-v1:{seed}:phacelle``; first four bytes little
endian, reduced modulo 1,000,000 for upstream mode. Stable mode uses the
first eight digest bytes as a little-endian uint64. The default lattice hash
replaces upstream Hash2 to preserve variation at large coordinates. Set
hash_mode="upstream" to retain the original floating-point Hash2 and its
2D seed offsets for reference comparisons; that hash loses spatial diversity
at large coordinates. This deliberate hash substitution changes the terrain.
This appearance filter models neither water nor sediment.
"""
from dataclasses import dataclass
import hashlib
import numbers

import numpy as np

ALGORITHM_ID = 'advanced-terrain-filter-v2-stable-hash'
SEED_DERIVATION_ID = 'advanced-terrain-filter-v1'
MAX_SAMPLES = 1_048_576
MAX_COORDINATE_M = 1_000_000_000.0


@dataclass(frozen=True)
class AdvancedFilterConfig:
    amplitude_m: float = 400.0
    wavelength_m: float = 1800.0
    octaves: int = 3
    gain: float = 0.5
    lacunarity: float = 2.0
    gully_weight: float = 0.5
    detail: float = 1.5
    rounding: tuple = (0.1, 0.0, 0.1, 2.0)
    onset: tuple = (1.25, 1.25, 2.8, 1.5)
    assumed_slope: tuple = (0.7, 1.0)
    cell_scale: float = 0.7
    normalization: float = 0.5
    hash_mode: str = 'stable'


def _check_config(c):
    if not isinstance(c, AdvancedFilterConfig):
        raise ValueError('config must be AdvancedFilterConfig')
    if c.hash_mode not in ('stable', 'upstream'):
        raise ValueError('hash_mode must be stable or upstream')
    for name, low, high in (('amplitude_m', 0, 1e6), ('wavelength_m', 1, 1e9),
                            ('gain', 0, 1), ('lacunarity', 1, 4),
                            ('gully_weight', 0, 1), ('detail', 0.01, 8),
                            ('cell_scale', 0.01, 4), ('normalization', 0, 0.999)):
        v = getattr(c, name)
        if isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real) or not np.isfinite(v) or not low <= v <= high:
            raise ValueError(f'invalid {name}')
    if 0 < c.amplitude_m < 0.001:
        raise ValueError('nonzero amplitude_m must be at least 0.001 m')
    if isinstance(c.octaves, bool) or not isinstance(c.octaves, numbers.Integral) or not 1 <= c.octaves <= 8:
        raise ValueError('octaves must be in [1, 8]')
    for name, n, upper in (('rounding', 4, 8), ('onset', 4, 8), ('assumed_slope', 2, 8)):
        a = np.asarray(getattr(c, name), dtype=np.float64)
        if a.shape != (n,) or not np.all(np.isfinite(a)) or np.any(a < 0) or np.any(a > upper):
            raise ValueError(f'invalid {name}')
    if c.assumed_slope[1] > 1:
        raise ValueError('assumed_slope mix must be in [0, 1]')


def _hash2(x, z, seed):
    kx, kz = 1.0 / np.pi, np.exp(-1.0)
    x = (x + seed * 0.06711056) * kx + kz
    z = (z + seed * 0.00583715) * kz + kx
    q = x * z * (x + z)
    t = q - np.floor(q)
    a, b = 16 * kx * t, 16 * kz * t
    return -1 + 2 * (a - np.floor(a)), -1 + 2 * (b - np.floor(b))


def _stable_hash2(x, z, seed):
    """Hash signed integer lattice cells with independent uint64 lanes."""
    def lane(salt):
        with np.errstate(over='ignore'):
            v = x.astype(np.int64).astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
            v ^= z.astype(np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
            v ^= np.uint64(seed) + np.uint64(salt)
            v ^= v >> np.uint64(30)
            v *= np.uint64(0xBF58476D1CE4E5B9)
            v ^= v >> np.uint64(27)
            v *= np.uint64(0x94D049BB133111EB)
            v ^= v >> np.uint64(31)
        return -1.0 + (v >> np.uint64(11)).astype(np.float64) * (2.0 / 9007199254740992.0)
    return lane(0xA0761D6478BD642F), lane(0xE7037ED1A0B428DB)


def _phacelle(x, z, dx, dz, cell_scale, normalization, seed, hash_mode):
    side_x, side_z = -dz * cell_scale * (2 * np.pi), dx * cell_scale * (2 * np.pi)
    ix, iz = np.floor(x), np.floor(z)
    fx, fz = x - ix, z - iz
    co, si, total = np.zeros_like(x), np.zeros_like(x), np.zeros_like(x)
    for i in (-1, 0, 1, 2):
        for j in (-1, 0, 1, 2):
            hash_fn = _stable_hash2 if hash_mode == 'stable' else _hash2
            hx, hz = hash_fn(ix + i, iz + j, seed)
            rx, rz = fx - i - hx * 0.5, fz - j - hz * 0.5
            weight = np.maximum(0.0, np.exp(-2 * (rx * rx + rz * rz)) - 0.01111)
            phase = rx * side_x + rz * side_z + np.pi * 0.5
            co += np.cos(phase) * weight
            si += np.sin(phase) * weight
            total += weight
    co, si = co / total, si / total
    magnitude = np.maximum(1 - normalization, np.hypot(co, si))
    return co / magnitude, si / magnitude, side_x, side_z


def _ease(t):
    return 1 - (1 - np.clip(t, 0, 1)) ** 2


def _smooth_start(t, smoothing):
    # Upstream's branch avoids zero division when smoothing is zero.
    t, smoothing = np.broadcast_arrays(t, smoothing)
    result = t - 0.5 * smoothing
    curved = t < smoothing
    # Evaluate only where the quadratic branch applies; t / smoothing < 1.
    ratio = np.divide(t, smoothing, out=np.zeros_like(t), where=curved)
    return np.where(curved, 0.5 * t * ratio, result)


def filter_height(x_m, z_m, base_height_m, slope_x, slope_z, fade_target, *, world_seed, config=None):
    """Return height, delta, artistic slopes and ridge map at broadcast points.

    Coordinates are in [-1e9,1e9] metres; target is in [-1,1], slopes are
    dimensionless metres/metre. Seed is uint64; sample count is 1..1048576.
    """
    c = AdvancedFilterConfig() if config is None else config
    _check_config(c)
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, numbers.Integral) or not 0 <= world_seed < 2**64:
        raise ValueError('world_seed must be an unsigned 64-bit integer')
    try:
        x, z, h, sx, sz, target = np.broadcast_arrays(*[np.asarray(v, dtype=np.float64) for v in (x_m,z_m,base_height_m,slope_x,slope_z,fade_target)])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('inputs must be broadcastable real numbers') from exc
    if x.size == 0 or x.size > MAX_SAMPLES:
        raise ValueError('broadcast sample count must be in [1,1048576]')
    if any(not np.all(np.isfinite(v)) for v in (x,z,h,sx,sz,target)):
        raise ValueError('inputs must be finite')
    if np.any(np.abs(x) > MAX_COORDINATE_M) or np.any(np.abs(z) > MAX_COORDINATE_M):
        raise ValueError('coordinates exceed fixed domain')
    if np.any(np.abs(target) > 1):
        raise ValueError('fade_target must be in [-1,1]')
    if c.amplitude_m == 0:
        zero = np.zeros_like(x)
        return {'height_m': h.copy(), 'delta_m': zero, 'artistic_slope_x': sx.copy(), 'artistic_slope_z': sz.copy(), 'ridge_map': zero.copy()}
    # Bound extreme finite slopes so derived arithmetic cannot overflow.
    if np.any(np.abs(sx) > 1e6) or np.any(np.abs(sz) > 1e6):
        raise ValueError('slope magnitude component exceeds 1e6')
    digest = hashlib.sha256(f'{SEED_DERIVATION_ID}:{world_seed}:phacelle'.encode('ascii')).digest()
    seed = (int.from_bytes(digest[:8], 'little') if c.hash_mode == 'stable'
            else int.from_bytes(digest[:4], 'little') % 1_000_000)
    px, pz = x / c.wavelength_m, z / c.wavelength_m
    xs, zs = sx * (c.wavelength_m / c.amplitude_m), sz * (c.wavelength_m / c.amplitude_m)
    length = np.maximum(np.hypot(xs, zs), 1e-10)
    r, o = c.rounding, c.onset
    rounded = (r[1] + (r[0] - r[1]) * np.clip(target + 0.5, 0, 1)) * r[2]
    mask = _ease(_smooth_start(length * o[0], rounded * o[0]))
    ridge_mask, ridge_target = _ease(length * o[2]), target.copy()
    gx = xs * (1-c.assumed_slope[1]) + xs / length * c.assumed_slope[0] * c.assumed_slope[1]
    gz = zs * (1-c.assumed_slope[1]) + zs / length * c.assumed_slope[0] * c.assumed_slope[1]
    delta = np.zeros_like(x)
    freq, strength, rounding_mult = 1.0, 1.0, 1.0
    fade = target.copy()
    for _ in range(c.octaves):
        norm = np.hypot(gx, gz)
        dx = np.divide(gx, norm, out=np.zeros_like(gx), where=norm > 1e-10)
        dz = np.divide(gz, norm, out=np.zeros_like(gz), where=norm > 1e-10)
        co, si, side_x, side_z = _phacelle(px * freq, pz * freq, dx, dz, c.cell_scale, c.normalization, seed, c.hash_mode)
        side_x, side_z = -side_x * freq, -side_z * freq
        gx += np.sign(si) * side_x * strength * c.gully_weight
        gz += np.sign(si) * side_z * strength * c.gully_weight
        layer = fade * (1-mask) + co * c.gully_weight * mask
        delta += layer * strength
        xs += si * side_x * c.gully_weight * mask * strength
        zs += si * side_z * c.gully_weight * mask * strength
        fade = layer
        rounded = (r[1] + (r[0]-r[1]) * np.clip(co + 0.5, 0, 1)) * rounding_mult
        new_mask = _ease(_smooth_start(np.abs(si)*o[1], rounded*o[1]))
        mask = (1 - (1 - np.clip(mask, 0, 1)) ** c.detail) * new_mask
        ridge_target = ridge_target * (1-ridge_mask) + co * ridge_mask
        ridge_mask *= _ease(np.abs(si)*o[3])
        strength *= c.gain
        freq *= c.lacunarity
        rounding_mult *= r[3]
    delta = delta * c.amplitude_m
    return {'height_m': np.asarray(h + delta), 'delta_m': np.asarray(delta),
            'artistic_slope_x': np.asarray(xs * c.amplitude_m / c.wavelength_m),
            'artistic_slope_z': np.asarray(zs * c.amplitude_m / c.wavelength_m),
            'ridge_map': np.asarray(ridge_target * (1-ridge_mask))}
