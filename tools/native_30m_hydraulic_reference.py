"""Independent rectangular Manning reference (DeepSeek task 6280b7c1)."""

def manning_trace_reference(volume, length, width, roughness, slope, bed):
    import numpy as np
    volume = np.asarray(volume)
    length = np.asarray(length)
    width = np.asarray(width)
    roughness = np.asarray(roughness)
    slope = np.asarray(slope)
    bed = np.asarray(bed)
    if volume.ndim != 2:
        raise ValueError("volume must be 2D")
    if any(a.ndim != 1 for a in (length, width, roughness, slope, bed)):
        raise ValueError('network inputs must be 1D')
    if not (length.shape == width.shape == roughness.shape == slope.shape == bed.shape):
        raise ValueError("1D inputs must share shape")
    if volume.shape[1] != length.shape[0] or length.shape[0] < 1:
        raise ValueError("shape mismatch")
    for a in (volume, length, width, roughness, slope, bed):
        if not np.all(np.isfinite(a)):
            raise ValueError("non-finite input")
    if np.any(volume < 0):
        raise ValueError("volume must be nonnegative")
    if np.any(length <= 0) or np.any(width <= 0) or np.any(roughness <= 0) or np.any(slope <= 0):
        raise ValueError("positive parameters required")
    A = volume / length
    d = A / width
    stage = bed + d
    q = A * (A / (width + 2 * d)) ** (2 / 3) * np.sqrt(slope) / roughness
    for a in (A, d, stage, q):
        if not np.all(np.isfinite(a)):
            raise ValueError("non-finite output")
    return {'area_m2': A, 'depth_m': d, 'stage_m': stage, 'outflow_q_m3_s': q}
