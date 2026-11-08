import numpy as np


def audit_balance(storage, inputs, outputs, *, rtol=1e-10, atol=1e-12):
    if not isinstance(storage, np.ndarray) or storage.dtype != np.float64 or storage.ndim != 2:
        raise ValueError("storage must be float64 2D ndarray")
    if not isinstance(inputs, np.ndarray) or inputs.dtype != np.float64 or inputs.ndim != 2:
        raise ValueError("inputs must be float64 2D ndarray")
    if not isinstance(outputs, np.ndarray) or outputs.dtype != np.float64 or outputs.ndim != 2:
        raise ValueError("outputs must be float64 2D ndarray")
    Tp1, N = storage.shape
    T, Ni = inputs.shape
    if outputs.shape != (T, Ni):
        raise ValueError("inputs and outputs shapes must match")
    if N != Ni:
        raise ValueError("node counts must match")
    if T <= 0 or N <= 0 or T * N > 1000000:
        raise ValueError("invalid T,N bounds")
    if Tp1 != T + 1:
        raise ValueError("storage must be (T+1,N)")
    if not isinstance(rtol, (int, float)) or isinstance(rtol, bool) or not np.isfinite(rtol) or rtol < 0:
        raise ValueError("rtol must be finite nonnegative number")
    if not isinstance(atol, (int, float)) or isinstance(atol, bool) or not np.isfinite(atol) or atol < 0:
        raise ValueError("atol must be finite nonnegative number")
    for arr in (storage, inputs, outputs):
        if not np.all(np.isfinite(arr)) or np.any(arr < 0):
            raise ValueError("all values must be finite and >=0")
    s = storage.sum(axis=1)
    i = inputs.sum(axis=1)
    o = outputs.sum(axis=1)
    residual = s[:-1] + i - o - s[1:]
    scale = np.maximum.reduce([s[:-1], i, o, s[1:], np.full(T, 1e-300)])
    tol = atol + rtol * scale
    for arr in (s, i, o, residual, scale, tol):
        if not np.all(np.isfinite(arr)):
            raise ValueError("non-finite arithmetic result")
    absres = np.abs(residual)
    passed = bool(np.all(absres <= tol))
    return {
        "passed": passed,
        "residual_m3": residual,
        "max_abs_residual_m3": float(absres.max()),
        "worst_interval": int(absres.argmax()),
        "intervals": T,
        "nodes": N,
    }
