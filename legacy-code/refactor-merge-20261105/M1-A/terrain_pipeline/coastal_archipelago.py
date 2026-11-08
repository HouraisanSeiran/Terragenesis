"""Continuous source-supported, deterministic engineering coastal relief."""
import hashlib
import numpy as np
from diffusion.geographic_noise import smooth_noise
WORLD_SEED = 20261020
SUBSEED = int.from_bytes(hashlib.sha256(b'20261020:regional-coastal-relief-v3').digest()[:8], 'big')


def relief(bed, valid, support, origin_xz_m, spacing_m=30., strength=1.):
    bed, valid, support = np.asarray(bed), np.asarray(valid), np.asarray(support)
    if (bed.ndim != 2 or valid.shape != bed.shape or valid.dtype != np.bool_ or support.shape != bed.shape or
        not np.isfinite(bed).all() or not np.isfinite(support).all() or np.any((support < 0) | (support > 1)) or
        not np.isfinite(spacing_m) or spacing_m <= 0 or not np.isfinite(strength) or not 0 <= strength <= 1 or
        len(origin_xz_m) != 2 or not np.isfinite(origin_xz_m).all()):
        raise ValueError('invalid coastal relief inputs')
    out = np.zeros(bed.shape, np.float32)
    if strength == 0 or not support.any():
        return out
    x = origin_xz_m[0] + np.arange(bed.shape[1], dtype=np.float64)[None, :] * spacing_m
    for start in range(0, bed.shape[0], 128):
        end = min(start + 128, bed.shape[0])
        z = origin_xz_m[1] + np.arange(start, end, dtype=np.float64)[:, None] * spacing_m
        xx, zz = np.broadcast_arrays(x, z)
        envelope_noise = smooth_noise(xx, zz, 18000., SUBSEED, 10)
        envelope = np.clip((envelope_noise + 0.55) / 0.9, 0, 1) ** 2
        warp_x = 900. * smooth_noise(xx, zz, 4000., SUBSEED, 20)
        warp_z = 900. * smooth_noise(xx, zz, 4000., SUBSEED, 30)
        u = 0.8 * (xx + warp_x) + 0.6 * (zz + warp_z)
        w = -0.6 * (xx + warp_x) + 0.8 * (zz + warp_z)
        ridge = smooth_noise(u / 1.8, w, 850., SUBSEED, 50)
        detail = smooth_noise(xx, zz, 260., SUBSEED, 60)
        micro = smooth_noise(xx, zz, 150., SUBSEED, 70)
        shape = 0.78 * ridge + 0.17 * detail + 0.05 * micro
        depth = np.clip((450. - np.abs(bed[start:end])) / 250., 0, 1)
        out[start:end] = (strength * 300. * support[start:end] * depth * envelope * shape * valid[start:end]).astype(np.float32)
    return out
