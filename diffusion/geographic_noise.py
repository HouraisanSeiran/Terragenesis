"""Tile-independent smooth noise from absolute conditioning-grid coordinates."""
import numpy as np


def _mix(value):
    value = np.asarray(value, dtype=np.uint64)
    value = value ^ (value >> np.uint64(30))
    value = value * np.uint64(0xBF58476D1CE4E5B9)
    value = value ^ (value >> np.uint64(27))
    value = value * np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


def _hash(ix, iz, seed, salt):
    with np.errstate(over="ignore"):
        bits = (np.asarray(ix, dtype=np.int64).astype(np.uint64) * np.uint64(0x9E3779B185EBCA87))
        bits ^= np.asarray(iz, dtype=np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
        bits ^= np.uint64(seed & 0xFFFFFFFFFFFFFFFF) + np.uint64(salt)
        return ((_mix(bits) >> np.uint64(11)).astype(np.float64) / (1 << 53) * 2 - 1)


def smooth_noise(x, z, spacing, seed, salt):
    gx = x / spacing
    gz = z / spacing
    ix = np.floor(gx).astype(np.int64)
    iz = np.floor(gz).astype(np.int64)
    fx = gx - ix
    fz = gz - iz
    fx = fx * fx * (3 - 2 * fx)
    fz = fz * fz * (3 - 2 * fz)
    a = _hash(ix, iz, seed, salt)
    b = _hash(ix + 1, iz, seed, salt)
    c = _hash(ix, iz + 1, seed, salt)
    d = _hash(ix + 1, iz + 1, seed, salt)
    return ((a * (1 - fx) + b * fx) * (1 - fz)
            + (c * (1 - fx) + d * fx) * fz)


def field(x, z, seed, salt, scales):
    result = np.zeros_like(x, dtype=np.float64)
    total = 0.0
    for octave, (spacing, weight) in enumerate(scales):
        result += weight * smooth_noise(x, z, spacing, seed, salt + octave * 811)
        total += weight
    return result / total
