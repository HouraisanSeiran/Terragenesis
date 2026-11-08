"""Independent normal-depth bisection (Aliyun DeepSeek task b5975a3e)."""

def normal_depth_reference(q_m3_s, width_m, slope, manning_n):
    import math
    vals = (q_m3_s, width_m, slope, manning_n)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in vals):
        raise ValueError("inputs must be finite positive scalars")
    q, b, s, n = map(float, vals)
    if any(not math.isfinite(v) or v <= 0.0 for v in (q, b, s, n)):
        raise ValueError("inputs must be finite positive scalars")

    def flow(d):
        a = b * d
        return a * (a / (b + 2.0 * d)) ** (2.0 / 3.0) * math.sqrt(s) / n

    lo, hi = 0.0, 1.0
    while flow(hi) < q:
        hi *= 2.0
        if hi > 1.0e6:
            raise ValueError("no finite normal depth within 1e6 m")
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if flow(mid) < q:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))
